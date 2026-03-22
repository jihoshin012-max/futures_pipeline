# archetype: rotational
# STATUS: ONE-TIME
# PURPOSE: V2 mode and ATR-normalized asymmetric tests
# LAST RUN: unknown

"""Test 1: V2 modes at SD=25. Test 2: ATR-normalized asymmetric (V1.1)."""

import sys
import json
import time
import datetime as dt_mod
from pathlib import Path

import numpy as np
import pandas as pd

_REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_REPO))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from shared.data_loader import load_bars

EXCLUDE_HOURS = {1, 19, 20}
_P1_MID = dt_mod.date(2025, 9, 21) + (dt_mod.date(2025, 12, 14) - dt_mod.date(2025, 9, 21)) / 2


def run_v2(prices, dts, n, sd=25.0, mtp=1, mode="walking", ct=3):
    """V2 path: MTP cap with anchor mode. Directional seed."""
    ts = 0.25
    state = -1
    wp = 0.0; anc = 0.0; pos = 0; avg_e = 0.0
    cid = 0; cs = 0
    cyc = []; ctr = []
    stuck_count = 0
    ticks_at_cap = 0

    for i in range(n):
        p = prices[i]
        if state == -1:
            if wp == 0.0: wp = p; continue
            if p - wp >= sd:
                cid += 1; state = 1; anc = p; pos = 1; avg_e = p; cs = i
                ctr = [{"a": "S", "p": p, "q": 1, "c": ct}]
            elif wp - p >= sd:
                cid += 1; state = 2; anc = p; pos = 1; avg_e = p; cs = i
                ctr = [{"a": "S", "p": p, "q": 1, "c": ct}]
            continue

        # Track stuck cycles
        if mtp > 0 and pos >= mtp:
            ticks_at_cap += 1
        else:
            if ticks_at_cap >= 500:
                stuck_count += 1
            ticks_at_cap = 0

        dist = p - anc
        fav = (dist >= sd) if state == 1 else ((-dist) >= sd)
        adv = ((-dist) >= sd) if state == 1 else (dist >= sd)

        if fav:
            d = "L" if state == 1 else "S"
            nd = "S" if state == 1 else "L"
            ctr.append({"a": "F", "p": p, "q": pos, "c": ct * pos})
            ets = [t for t in ctr if t["a"] in ("S", "R", "A")]
            tq = sum(t["q"] for t in ets)
            wa = sum(t["p"] * t["q"] for t in ets) / tq if tq else p
            gr = ((p - wa) / ts * tq) if d == "L" else ((wa - p) / ts * tq)
            tc = sum(t["c"] for t in ctr); nt = gr - tc
            ac = sum(1 for t in ets if t["a"] == "A")
            mp = 0; rq = 0
            for t in ctr:
                if t["a"] == "F": rq = 0
                else: rq += t["q"]; mp = max(mp, rq)
            if ticks_at_cap >= 500:
                stuck_count += 1
            ticks_at_cap = 0
            cyc.append({"gr": gr, "nt": nt, "ac": ac, "mp": mp, "cs": cs})
            cid += 1; state = 2 if d == "L" else 1
            anc = p; pos = 1; avg_e = p; cs = i
            ctr = [{"a": "R", "p": p, "q": 1, "c": ct}]

        elif adv:
            if mtp > 0 and pos >= mtp:
                # MTP refusal
                if mode == "walking":
                    anc = p
                # frozen: do nothing
                continue
            # ADD (ML=1: always qty=1)
            anc = p; oq = pos; pos += 1
            avg_e = (avg_e * oq + p) / pos
            ctr.append({"a": "A", "p": p, "q": 1, "c": ct})

    # Finalize
    if state in (1, 2) and ctr:
        lp = prices[n - 1]; d = "L" if state == 1 else "S"
        ctr.append({"a": "F", "p": lp, "q": pos, "c": ct * pos})
        ets = [t for t in ctr if t["a"] in ("S", "R", "A")]
        tq = sum(t["q"] for t in ets)
        wa = sum(t["p"] * t["q"] for t in ets) / tq if tq else lp
        gr = ((lp - wa) / ts * tq) if d == "L" else ((wa - lp) / ts * tq)
        tc = sum(t["c"] for t in ctr); nt = gr - tc
        ac = sum(1 for t in ets if t["a"] == "A")
        mp = 0; rq = 0
        for t in ctr:
            if t["a"] == "F": rq = 0
            else: rq += t["q"]; mp = max(mp, rq)
        if ticks_at_cap >= 500:
            stuck_count += 1
        cyc.append({"gr": gr, "nt": nt, "ac": ac, "mp": mp, "cs": cs})

    return cyc, stuck_count


def run_v11_atr(prices, dts, n, rev_mult, add_mult, atr_arr, ct=3):
    """V1.1 with ATR-normalized asymmetric distances. MTP=0, ML=1."""
    ts = 0.25
    state = -1
    wp = 0.0; anc = 0.0; pos = 0; avg_e = 0.0
    cid = 0; cs = 0
    cyc = []; ctr = []
    rev_dists_used = []
    add_dists_used = []

    for i in range(n):
        p = prices[i]
        atr = atr_arr[i] if i < len(atr_arr) else 7.0

        if np.isnan(atr) or atr <= 0:
            atr = 7.0  # fallback

        sr = rev_mult * atr
        sa = add_mult * atr

        if state == -1:
            if wp == 0.0: wp = p; continue
            if p - wp >= sr:
                cid += 1; state = 1; anc = p; pos = 1; avg_e = p; cs = i
                ctr = [{"a": "S", "p": p, "q": 1, "c": ct}]
                rev_dists_used.append(sr)
            elif wp - p >= sr:
                cid += 1; state = 2; anc = p; pos = 1; avg_e = p; cs = i
                ctr = [{"a": "S", "p": p, "q": 1, "c": ct}]
                rev_dists_used.append(sr)
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
            tc = sum(t["c"] for t in ctr); nt = gr - tc
            ac = sum(1 for t in ets if t["a"] == "A")
            mp = 0; rq = 0
            for t in ctr:
                if t["a"] == "F": rq = 0
                else: rq += t["q"]; mp = max(mp, rq)
            cyc.append({"gr": gr, "nt": nt, "ac": ac, "mp": mp, "cs": cs})
            rev_dists_used.append(sr)
            cid += 1; state = 2 if d == "L" else 1
            anc = p; pos = 1; avg_e = p; cs = i
            ctr = [{"a": "R", "p": p, "q": 1, "c": ct}]

        elif adv:
            anc = p; oq = pos; pos += 1
            avg_e = (avg_e * oq + p) / pos
            ctr.append({"a": "A", "p": p, "q": 1, "c": ct})
            add_dists_used.append(sa)

    # Finalize
    if state in (1, 2) and ctr:
        lp = prices[n - 1]; d = "L" if state == 1 else "S"
        ctr.append({"a": "F", "p": lp, "q": pos, "c": ct * pos})
        ets = [t for t in ctr if t["a"] in ("S", "R", "A")]
        tq = sum(t["q"] for t in ets)
        wa = sum(t["p"] * t["q"] for t in ets) / tq if tq else lp
        gr = ((lp - wa) / ts * tq) if d == "L" else ((wa - lp) / ts * tq)
        tc = sum(t["c"] for t in ctr); nt = gr - tc
        ac = sum(1 for t in ets if t["a"] == "A")
        mp = 0; rq = 0
        for t in ctr:
            if t["a"] == "F": rq = 0
            else: rq += t["q"]; mp = max(mp, rq)
        cyc.append({"gr": gr, "nt": nt, "ac": ac, "mp": mp, "cs": cs})

    avg_rev = np.mean(rev_dists_used) if rev_dists_used else 0
    avg_add = np.mean(add_dists_used) if add_dists_used else 0
    return cyc, avg_rev, avg_add


def report(cyc_list, dts, label, extra=""):
    if not cyc_list:
        print(f"{label:<40} — no cycles —")
        return
    cdf = pd.DataFrame(cyc_list)
    cdf["hour"] = pd.to_datetime([dts[c["cs"]] for c in cyc_list]).hour
    cf = cdf[~cdf["hour"].isin(EXCLUDE_HOURS)]
    if cf.empty:
        print(f"{label:<40} — no cycles after filter —")
        return
    nn = len(cf)
    gw = cf[cf["gr"] > 0]["gr"].sum()
    gl = abs(cf[cf["gr"] <= 0]["gr"].sum())
    gpf = gw / gl if gl > 0 else 0

    # Compute net PF at 1t, 2t, 3t by scaling cost
    results = []
    for ct_scale, ct_label in [(1, "1t"), (2, "2t"), (3, "3t")]:
        cf2 = cf.copy()
        # nt was computed at whatever ct was passed. Recompute:
        # gross is fixed. cost = nt_original - gr... no, nt = gr - cost.
        # We don't have raw cost per cycle here. Use the fact that
        # the run was done at ct=1. Cost at ct=1 = gr - nt.
        cost1 = cf2["gr"] - cf2["nt"]  # cost at 1t
        cf2[f"nt_{ct_label}"] = cf2["gr"] - cost1 * ct_scale
        col = f"nt_{ct_label}"
        nw = cf2[cf2[col] > 0][col].sum()
        nl = abs(cf2[cf2[col] <= 0][col].sum())
        npf = nw / nl if nl > 0 else 0
        net = cf2[col].sum()
        results.append((npf, net))

    wr = (cf["gr"] > 0).sum() / nn
    w = cf[cf["nt"] > 0]
    lo = cf[cf["nt"] < 0]
    aw = w["nt"].mean() if len(w) > 0 else 0
    al = lo["nt"].mean() if len(lo) > 0 else 0
    mp = int(cf["mp"].max())
    aa = cf["ac"].mean()

    m = "<<<" if results[0][0] > 1.2 else ("<<" if results[0][0] > 1.0 else "")
    print(
        f"{label:<40} {nn:>5} {gpf:>6.3f}"
        f" {results[0][0]:>6.3f} {results[1][0]:>6.3f} {results[2][0]:>6.3f}"
        f" {results[0][1]:>+8,.0f} {wr:>5.1%} {aw:>+6.0f} {al:>+6.0f}"
        f" {mp:>3} {aa:>4.1f} {extra} {m}"
    )


def main():
    with open(Path(__file__).parent / "rotational_params.json") as f:
        cfg = json.load(f)

    print("Loading data...")
    t0 = time.time()
    tick = load_bars(cfg["bar_data_primary"]["bar_data_1tick_rot"])
    tick_p1a = tick[tick["datetime"].dt.date <= _P1_MID].reset_index(drop=True)
    prices = tick_p1a["Last"].values.astype(np.float64)
    dts = tick_p1a["datetime"].values
    nn = len(prices)

    # ATR from 250tick bars mapped to ticks
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
    ohlc_idx = np.clip(np.searchsorted(ohlc_ts, tick_ts, side="right") - 1, 0, len(ohlc_p1a) - 1)
    tick_atr = atr20[ohlc_idx]

    print(f"Loaded in {time.time()-t0:.1f}s. Tick P1a: {nn:,}, Median ATR: {np.nanmedian(atr20):.2f}")

    hdr = (
        f"{'Config':<40} {'Cyc':>5} {'GrPF':>6}"
        f" {'NP@1':>6} {'NP@2':>6} {'NP@3':>6}"
        f" {'Net@1t':>8} {'WR':>5} {'AvgW':>6} {'AvgL':>6}"
        f" {'MP':>3} {'A/c':>4}"
    )

    # ================================================================
    # TEST 1: V2 modes at SD=25
    # ================================================================
    print(f"\n{'='*100}")
    print("TEST 1: V2 modes at SD=25 (ML=1, directional seed)")
    print(f"{'='*100}")
    print(hdr)
    print("-" * 100)

    # MTP=1 (identical for both modes)
    cyc, stuck = run_v2(prices, dts, nn, sd=25.0, mtp=1, mode="walking", ct=1)
    report(cyc, dts, "SD=25 MTP=1 (both modes)")

    # MTP=2,3 for both modes
    for mtp in [2, 3]:
        for mode in ["frozen", "walking"]:
            cyc, stuck = run_v2(prices, dts, nn, sd=25.0, mtp=mtp, mode=mode, ct=1)
            report(cyc, dts, f"SD=25 MTP={mtp} {mode}", extra=f"stk={stuck}")

    # ================================================================
    # TEST 2: ATR-normalized asymmetric (V1.1)
    # ================================================================
    print(f"\n{'='*100}")
    print("TEST 2: ATR-normalized asymmetric (V1.1, MTP=0, ML=1)")
    print(f"{'='*100}")
    print(hdr + "  AvgRev AvgAdd")
    print("-" * 115)

    for rm in [1.5, 2.0, 2.5, 3.0]:
        for am in [4.0, 5.0, 6.0, 7.0]:
            cyc, avg_r, avg_a = run_v11_atr(prices, dts, nn, rm, am, tick_atr, ct=1)
            cdf = pd.DataFrame(cyc) if cyc else pd.DataFrame()
            if not cdf.empty:
                cdf["hour"] = pd.to_datetime([dts[c["cs"]] for c in cyc]).hour
                cf = cdf[~cdf["hour"].isin(EXCLUDE_HOURS)]
                nn_f = len(cf)
                if nn_f > 0:
                    gw = cf[cf["gr"] > 0]["gr"].sum()
                    gl = abs(cf[cf["gr"] <= 0]["gr"].sum())
                    gpf = gw / gl if gl > 0 else 0
                    cost1 = cf["gr"] - cf["nt"]
                    results = []
                    for sc in [1, 2, 3]:
                        nt_s = cf["gr"] - cost1 * sc
                        nw = nt_s[nt_s > 0].sum()
                        nl = abs(nt_s[nt_s <= 0].sum())
                        npf = nw / nl if nl > 0 else 0
                        results.append((npf, nt_s.sum()))
                    wr = (cf["gr"] > 0).sum() / nn_f
                    w = cf[cf["nt"] > 0]; lo2 = cf[cf["nt"] < 0]
                    aw = w["nt"].mean() if len(w) > 0 else 0
                    al2 = lo2["nt"].mean() if len(lo2) > 0 else 0
                    mp = int(cf["mp"].max()); aa = cf["ac"].mean()
                    m = "<<<" if results[0][0] > 1.2 else ("<<" if results[0][0] > 1.0 else "")
                    print(
                        f"R={rm:.1f}x A={am:.1f}x"
                        f"{' '*(32-len(f'R={rm:.1f}x A={am:.1f}x'))}"
                        f" {nn_f:>5} {gpf:>6.3f}"
                        f" {results[0][0]:>6.3f} {results[1][0]:>6.3f} {results[2][0]:>6.3f}"
                        f" {results[0][1]:>+8,.0f} {wr:>5.1%} {aw:>+6.0f} {al2:>+6.0f}"
                        f" {mp:>3} {aa:>4.1f}  {avg_r:>5.1f} {avg_a:>5.1f} {m}"
                    )
                else:
                    print(f"R={rm:.1f}x A={am:.1f}x — no cycles after filter —")
            else:
                print(f"R={rm:.1f}x A={am:.1f}x — no cycles —")

    print("\nDone.")


if __name__ == "__main__":
    main()
