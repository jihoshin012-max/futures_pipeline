# archetype: rotational
# STATUS: ONE-TIME
# PURPOSE: Tests D (hard stop) and E (direction fade) on ATR configs
# LAST RUN: unknown

"""Tests D (hard stop) and E (direction fade) on ATR R=2.0x/A=4.0x."""

import sys
import json
import time
import datetime as dt_mod
from pathlib import Path

import numpy as np
import pandas as pd

_REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_REPO))
from shared.data_loader import load_bars

EXCLUDE_HOURS = {1, 19, 20}
_P1_MID = dt_mod.date(2025, 9, 21) + (dt_mod.date(2025, 12, 14) - dt_mod.date(2025, 9, 21)) / 2


def run_v11(prices, dts, n, tick_atr, rm=2.0, am=4.0, ct=1,
            hard_stop_mult=0, max_dir_fades=0):
    ts = 0.25
    state = -1; wp = 0.0; anc = 0.0; pos = 0; avg_e = 0.0
    cid = 0; cs = 0; cyc = []; ctr = []
    stop_count = 0
    consec_loss_dir = None; consec_loss_count = 0
    blocked_dir = None; fade_block_count = 0

    for i in range(n):
        p = prices[i]
        atr = tick_atr[i] if i < len(tick_atr) else 7.0
        if np.isnan(atr) or atr <= 0:
            atr = 7.0
        sr = rm * atr
        sa = am * atr

        if state == -1:
            if wp == 0.0:
                wp = p; continue
            seed_dir = None
            if p - wp >= sr:
                seed_dir = 1
            elif wp - p >= sr:
                seed_dir = 2
            if seed_dir is not None:
                d_name = "Long" if seed_dir == 1 else "Short"
                if max_dir_fades > 0 and blocked_dir == d_name:
                    continue
                cid += 1; state = seed_dir; anc = p; pos = 1; avg_e = p; cs = i
                ctr = [{"a": "S", "p": p, "q": 1, "c": ct}]
            continue

        # Hard stop check
        if hard_stop_mult > 0 and pos > 0:
            direction_sign = 1.0 if state == 1 else -1.0
            unrealized_pts = (p - avg_e) * direction_sign
            stop_thresh_pts = -hard_stop_mult * atr
            if unrealized_pts <= stop_thresh_pts:
                d = "L" if state == 1 else "S"
                ctr.append({"a": "F", "p": p, "q": pos, "c": ct * pos})
                ets = [t for t in ctr if t["a"] in ("S", "R", "A")]
                tq = sum(t["q"] for t in ets)
                wa = sum(t["p"] * t["q"] for t in ets) / tq if tq else p
                gr = ((p - wa) / ts * tq) if d == "L" else ((wa - p) / ts * tq)
                tc = sum(t["c"] for t in ctr)
                nt = gr - tc
                cyc.append({"gr": gr, "nt": nt, "cs": cs, "d": d})
                stop_count += 1
                if max_dir_fades > 0 and nt < 0:
                    if consec_loss_dir == d:
                        consec_loss_count += 1
                    else:
                        consec_loss_dir = d; consec_loss_count = 1
                    if consec_loss_count >= max_dir_fades:
                        blocked_dir = "Long" if d == "L" else "Short"
                        fade_block_count += 1
                elif max_dir_fades > 0:
                    consec_loss_count = 0; blocked_dir = None
                state = -1; wp = p; pos = 0
                continue

        dist = p - anc
        fav = (dist >= sr) if state == 1 else ((-dist) >= sr)
        adv = ((-dist) >= sa) if state == 1 else (dist >= sa)

        if fav:
            d = "L" if state == 1 else "S"
            ctr.append({"a": "F", "p": p, "q": pos, "c": ct * pos})
            ets = [t for t in ctr if t["a"] in ("S", "R", "A")]
            tq = sum(t["q"] for t in ets)
            wa = sum(t["p"] * t["q"] for t in ets) / tq if tq else p
            gr = ((p - wa) / ts * tq) if d == "L" else ((wa - p) / ts * tq)
            tc = sum(t["c"] for t in ctr)
            nt = gr - tc
            cyc.append({"gr": gr, "nt": nt, "cs": cs, "d": d})

            if max_dir_fades > 0:
                if nt < 0:
                    if consec_loss_dir == d:
                        consec_loss_count += 1
                    else:
                        consec_loss_dir = d; consec_loss_count = 1
                    if consec_loss_count >= max_dir_fades:
                        blocked_dir = "Long" if d == "L" else "Short"
                        fade_block_count += 1
                else:
                    consec_loss_count = 0; blocked_dir = None

            nd = "S" if d == "L" else "L"
            nd_full = "Long" if nd == "L" else "Short"
            if max_dir_fades > 0 and blocked_dir == nd_full:
                state = -1; wp = p; pos = 0; continue

            cid += 1; state = 2 if d == "L" else 1
            anc = p; pos = 1; avg_e = p; cs = i
            ctr = [{"a": "R", "p": p, "q": 1, "c": ct}]

        elif adv:
            anc = p; oq = pos; pos += 1
            avg_e = (avg_e * oq + p) / pos
            ctr.append({"a": "A", "p": p, "q": 1, "c": ct})

    return cyc, stop_count, fade_block_count


def main():
    with open(Path(__file__).parent / "rotational_params.json") as f:
        cfg = json.load(f)

    print("Loading data...")
    tick = load_bars(cfg["bar_data_primary"]["bar_data_1tick_rot"])
    tick_p1a = tick[tick["datetime"].dt.date <= _P1_MID].reset_index(drop=True)
    prices = tick_p1a["Last"].values.astype(np.float64)
    dts = tick_p1a["datetime"].values
    n = len(prices)

    ohlc = load_bars(cfg["bar_data_primary"]["bar_data_250tick_rot"])
    ohlc_p1a = ohlc[ohlc["datetime"].dt.date <= _P1_MID].reset_index(drop=True)
    c = ohlc_p1a["Last"].values.astype(float)
    h = ohlc_p1a["High"].values.astype(float)
    lo = ohlc_p1a["Low"].values.astype(float)
    pc = np.empty(len(c)); pc[0] = c[0]; pc[1:] = c[:-1]
    tr = np.maximum(h - lo, np.maximum(np.abs(h - pc), np.abs(lo - pc)))
    atr20 = pd.Series(tr).rolling(20, min_periods=20).mean().values
    ohlc_ts = ohlc_p1a["datetime"].values.astype("int64") // 10**9
    tick_ts = tick_p1a["datetime"].values.astype("int64") // 10**9
    oi = np.clip(np.searchsorted(ohlc_ts, tick_ts, side="right") - 1, 0, len(ohlc_p1a) - 1)
    tick_atr = atr20[oi]

    print(f"Tick P1a: {n:,}")

    hdr = (
        f"  {'Config':<35} {'Cyc':>5} {'GrPF':>6}"
        f" {'NP@1':>6} {'NP@2':>6} {'NP@3':>6}"
        f" {'Net@1t':>8} {'WR':>5} {'Ret%':>5} {'Extra':>15}"
    )
    print(f"\n{hdr}")
    print("=" * 100)

    # Baseline
    cyc_b, _, _ = run_v11(prices, dts, n, tick_atr)
    cdf_b = pd.DataFrame(cyc_b)
    cdf_b["hour"] = pd.to_datetime([dts[c["cs"]] for c in cyc_b]).hour
    n_base = len(cdf_b[~cdf_b["hour"].isin(EXCLUDE_HOURS)])

    def report(cyc_list, label, sc=0, fc=0):
        if not cyc_list:
            print(f"  {label:<35} -- no cycles --"); return
        cdf = pd.DataFrame(cyc_list)
        cdf["hour"] = pd.to_datetime([dts[c["cs"]] for c in cyc_list]).hour
        cf = cdf[~cdf["hour"].isin(EXCLUDE_HOURS)]
        nn = len(cf)
        if nn == 0:
            print(f"  {label:<35} -- no cycles after filter --"); return

        gw = cf[cf["gr"] > 0]["gr"].sum()
        gl = abs(cf[cf["gr"] <= 0]["gr"].sum())
        gpf = gw / gl if gl > 0 else 0
        cost1 = cf["gr"] - cf["nt"]
        res = []
        for s in [1, 2, 3]:
            nt_s = cf["gr"] - cost1 * s
            nw = nt_s[nt_s > 0].sum()
            nl = abs(nt_s[nt_s <= 0].sum())
            res.append((nw / nl if nl > 0 else 0, nt_s.sum()))
        wr = (cf["gr"] > 0).sum() / nn
        ret = nn / n_base * 100
        extra = ""
        if sc:
            extra = f"stops={sc}"
        if fc:
            extra = f"fades={fc}"
        m = "<<<" if res[0][0] > 1.2 else ("<<" if res[0][0] > 1.0 else "")
        print(
            f"  {label:<35} {nn:>5} {gpf:>6.3f}"
            f" {res[0][0]:>6.3f} {res[1][0]:>6.3f} {res[2][0]:>6.3f}"
            f" {res[0][1]:>+8,.0f} {wr:>5.1%} {ret:>5.1f}% {extra:>15} {m}"
        )

    report(cyc_b, "Baseline R=2.0x/A=4.0x")

    print("\n--- TEST D: ATR hard stop ---")
    for hs in [2.0, 3.0, 4.0, 5.0]:
        cyc, sc, _ = run_v11(prices, dts, n, tick_atr, hard_stop_mult=hs)
        report(cyc, f"HardStop={hs}x ATR", sc=sc)

    print("\n--- TEST E: Direction fade ---")
    for nf in [2, 3, 4, 5]:
        cyc, _, fc = run_v11(prices, dts, n, tick_atr, max_dir_fades=nf)
        report(cyc, f"DirFade after {nf} losses", fc=fc)

    print("\nDone.")


if __name__ == "__main__":
    main()
