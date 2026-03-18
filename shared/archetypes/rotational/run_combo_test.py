# archetype: rotational
"""Combo test: Asymmetric Rev=15/Add=40 + position cap + SpeedRead 10sec."""

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
from feature_engine import _compute_speedread_features

EXCLUDE_HOURS = {1, 19, 20}
_P1_MID = dt_mod.date(2025, 9, 21) + (dt_mod.date(2025, 12, 14) - dt_mod.date(2025, 9, 21)) / 2


def run_v11(prices, dts, n, sr=15.0, sa=40.0, cap=0, sr_arr=None, sr_th=None, ct=3):
    ts = 0.25
    state = -1
    wp = 0.0
    anc = 0.0
    pos = 0
    avg_e = 0.0
    cid = 0
    cs = 0
    trades = []
    cycles = []
    ctr = []
    cap_count = 0

    for i in range(n):
        p = prices[i]
        if state == -1:
            if sr_arr is not None and sr_th is not None and i < len(sr_arr):
                sv = sr_arr[i]
                if not np.isnan(sv) and sv >= sr_th:
                    continue
            if wp == 0.0:
                wp = p
                continue
            if p - wp >= sr:
                cid += 1; state = 1; anc = p; pos = 1; avg_e = p; cs = i
                trades.append({"i": i, "a": "SEED", "d": "L", "q": 1, "p": p, "c": ct, "cid": cid})
                ctr = [trades[-1]]
            elif wp - p >= sr:
                cid += 1; state = 2; anc = p; pos = 1; avg_e = p; cs = i
                trades.append({"i": i, "a": "SEED", "d": "S", "q": 1, "p": p, "c": ct, "cid": cid})
                ctr = [trades[-1]]
            continue

        dist = p - anc
        fav = (dist >= sr) if state == 1 else ((-dist) >= sr)
        adv = ((-dist) >= sa) if state == 1 else (dist >= sa)

        if fav:
            d = "L" if state == 1 else "S"
            nd = "S" if state == 1 else "L"
            ft = {"i": i, "a": "F", "d": d, "q": pos, "p": p, "c": ct * pos, "cid": cid}
            trades.append(ft); ctr.append(ft)
            ets = [t for t in ctr if t["a"] in ("SEED", "R", "ADD")]
            tq = sum(t["q"] for t in ets)
            wa = sum(t["p"] * t["q"] for t in ets) / tq if tq else p
            gr = ((p - wa) / ts * tq) if d == "L" else ((wa - p) / ts * tq)
            tc = sum(t["c"] for t in ctr)
            nt = gr - tc
            ac = sum(1 for t in ets if t["a"] == "ADD")
            mp = 0; rq = 0
            for t in ctr:
                if t["a"] == "F":
                    rq = 0
                else:
                    rq += t["q"]; mp = max(mp, rq)
            cycles.append({"cid": cid, "gr": round(gr, 4), "nt": round(nt, 4),
                           "ac": ac, "mp": mp, "dt": dts[cs], "er": "rev"})
            cid += 1
            state = 2 if d == "L" else 1
            anc = p; pos = 1; avg_e = p; cs = i
            trades.append({"i": i, "a": "R", "d": nd, "q": 1, "p": p, "c": ct, "cid": cid})
            ctr = [trades[-1]]

        elif adv:
            if cap > 0 and pos >= cap:
                d = "L" if state == 1 else "S"
                ft = {"i": i, "a": "F", "d": d, "q": pos, "p": p, "c": ct * pos, "cid": cid}
                trades.append(ft); ctr.append(ft)
                ets = [t for t in ctr if t["a"] in ("SEED", "R", "ADD")]
                tq = sum(t["q"] for t in ets)
                wa = sum(t["p"] * t["q"] for t in ets) / tq if tq else p
                gr = ((p - wa) / ts * tq) if d == "L" else ((wa - p) / ts * tq)
                tc = sum(t["c"] for t in ctr)
                nt = gr - tc
                ac = sum(1 for t in ets if t["a"] == "ADD")
                mp = 0; rq = 0
                for t in ctr:
                    if t["a"] == "F":
                        rq = 0
                    else:
                        rq += t["q"]; mp = max(mp, rq)
                cycles.append({"cid": cid, "gr": round(gr, 4), "nt": round(nt, 4),
                               "ac": ac, "mp": mp, "dt": dts[cs], "er": "cap"})
                cap_count += 1
                state = -1; wp = p; pos = 0
                continue

            anc = p; oq = pos; pos += 1
            avg_e = (avg_e * oq + p) / pos
            d = "L" if state == 1 else "S"
            trades.append({"i": i, "a": "ADD", "d": d, "q": 1, "p": p, "c": ct, "cid": cid})
            ctr.append(trades[-1])

    if state in (1, 2) and ctr:
        lp = prices[n - 1]
        d = "L" if state == 1 else "S"
        ets = [t for t in ctr if t["a"] in ("SEED", "R", "ADD")]
        tq = sum(t["q"] for t in ets)
        wa = sum(t["p"] * t["q"] for t in ets) / tq if tq else lp
        gr = ((lp - wa) / ts * tq) if d == "L" else ((wa - lp) / ts * tq)
        tc = sum(t["c"] for t in ctr)
        nt = gr - tc
        ac = sum(1 for t in ets if t["a"] == "ADD")
        mp = 0; rq = 0
        for t in ctr:
            if t["a"] == "F":
                rq = 0
            else:
                rq += t["q"]; mp = max(mp, rq)
        cycles.append({"cid": cid, "gr": round(gr, 4), "nt": round(nt, 4),
                       "ac": ac, "mp": mp, "dt": dts[cs], "er": "eod"})

    return cycles, trades, cap_count


def report(cy, tr, label, n_base=None, cap_count=0):
    if not cy:
        print(f"{label}: no cycles")
        return
    cdf = pd.DataFrame(cy)
    tdf = pd.DataFrame(tr)
    cdf["hour"] = pd.to_datetime(cdf["dt"]).dt.hour
    cdf = cdf[~cdf["hour"].isin(EXCLUDE_HOURS)]
    if cdf.empty:
        print(f"{label}: no cycles after filter")
        return
    vids = set(cdf["cid"])
    tdf = tdf[tdf["cid"].isin(vids)]
    n = len(cdf)
    gross = cdf["gr"].sum()
    c3 = float(tdf["c"].sum())
    c2 = c3 * 2 / 3
    n3 = gross - c3
    n2 = gross - c2
    gw = cdf[cdf["gr"] > 0]["gr"].sum()
    gl = abs(cdf[cdf["gr"] <= 0]["gr"].sum())
    gpf = gw / gl if gl > 0 else float("inf")
    cdf = cdf.copy()
    cc = tdf.groupby("cid")["c"].sum()
    cdf["c3"] = cdf["cid"].map(cc).fillna(0)
    cdf["n3"] = cdf["gr"] - cdf["c3"]
    cdf["n2"] = cdf["gr"] - cdf["c3"] * 2 / 3
    nw3 = cdf[cdf["n3"] > 0]["n3"].sum()
    nl3 = abs(cdf[cdf["n3"] <= 0]["n3"].sum())
    nw2 = cdf[cdf["n2"] > 0]["n2"].sum()
    nl2 = abs(cdf[cdf["n2"] <= 0]["n2"].sum())
    npf3 = nw3 / nl3 if nl3 > 0 else 0
    npf2 = nw2 / nl2 if nl2 > 0 else 0
    wr = (cdf["gr"] > 0).sum() / n
    w = cdf[cdf["n3"] > 0]
    lo = cdf[cdf["n3"] < 0]
    aw = w["n3"].mean() if len(w) > 0 else 0
    al = lo["n3"].mean() if len(lo) > 0 else 0
    mp = int(cdf["mp"].max())
    aa = cdf["ac"].mean()
    ret = f"{n / n_base * 100:.0f}%" if n_base else ""
    m = "<<<" if npf3 > 1.2 else ("<<" if npf3 > 1.0 else "")
    extra = f" caps={cap_count}" if cap_count else ""
    print(
        f"{label:<38} {n:>6,} {gpf:>7.4f} {npf2:>7.4f} {npf3:>7.4f} "
        f"{n2:>+9,.0f} {n3:>+9,.0f} {wr:>5.1%} {aw:>+7.1f} {al:>+7.1f} "
        f"{mp:>4} {aa:>5.2f} {ret:>5} {m}{extra}"
    )


def main():
    with open(Path(__file__).parent / "rotational_params.json") as f:
        base_config = json.load(f)

    print("Loading data...")
    t0 = time.time()
    tick_bars = load_bars(base_config["bar_data_primary"]["bar_data_1tick_rot"])
    tick_p1a = tick_bars[tick_bars["datetime"].dt.date <= _P1_MID].copy().reset_index(drop=True)
    prices = tick_p1a["Last"].values.astype(np.float64)
    dts = tick_p1a["datetime"].values
    n_ticks = len(prices)

    # 10sec bars for SpeedRead
    sec_bars = load_bars(base_config["bar_data_primary"]["bar_data_10sec_rot"])
    sec_p1a = sec_bars[sec_bars["datetime"].dt.date <= _P1_MID].copy()
    if "Time" in sec_p1a.columns:
        def _pt(t):
            parts = str(t).strip().split(":")
            return dt_mod.time(int(parts[0]), int(parts[1]),
                               int(float(parts[2])) if len(parts) > 2 else 0)
        times = sec_p1a["Time"].apply(_pt)
        sec_p1a = sec_p1a[(times >= dt_mod.time(9, 30, 0)) & (times < dt_mod.time(16, 0, 0))]
    sec_p1a = sec_p1a.reset_index(drop=True)

    sr_params = {"lookback": 10, "vol_avg_len": 50, "price_weight": 50,
                 "vol_weight": 50, "smoothing_bars": 3, "atr_length": 20}
    sec_sr = _compute_speedread_features(sec_p1a.copy(), sr_params)
    sr_10s = sec_sr["speed_composite"].values

    print(f"10sec SpeedRead: min={np.nanmin(sr_10s):.1f} max={np.nanmax(sr_10s):.1f} "
          f"med={np.nanmedian(sr_10s):.1f}")
    for th in [25, 30, 35, 40, 45, 50]:
        pct = (sr_10s > th).sum() / len(sr_10s) * 100
        print(f"  >{th}: {pct:.1f}%")

    sec_ts = sec_p1a["datetime"].values.astype("int64") // 10**9
    tick_ts = tick_p1a["datetime"].values.astype("int64") // 10**9
    sec_idx = np.clip(np.searchsorted(sec_ts, tick_ts, side="right") - 1, 0, len(sec_p1a) - 1)
    tick_sr_10s = sr_10s[sec_idx]

    print(f"\nLoaded in {time.time()-t0:.1f}s. Tick P1a: {n_ticks:,}")

    hdr = (
        f"{'Config':<38} {'Cyc':>6} {'GrPF':>7} {'NP@2':>7} {'NP@3':>7} "
        f"{'Net@2t':>9} {'Net@3t':>9} {'WR':>5} {'AvgW':>7} {'AvgL':>7} "
        f"{'MP':>4} {'A/c':>5} {'Ret':>5}"
    )
    print(f"\n{hdr}")
    print("=" * 135)

    # Baseline
    print("--- COMBINATION: Asymmetric + Position Cap ---")
    cy_b, tr_b, _ = run_v11(prices, dts, n_ticks, sr=15.0, sa=40.0)
    cdf_b = pd.DataFrame(cy_b)
    cdf_b["hour"] = pd.to_datetime(cdf_b["dt"]).dt.hour
    n_base = len(cdf_b[~cdf_b["hour"].isin(EXCLUDE_HOURS)])
    report(cy_b, tr_b, "Rev=15/Add=40 (baseline)", n_base)

    for cap in [2, 3]:
        cy, tr, cc = run_v11(prices, dts, n_ticks, sr=15.0, sa=40.0, cap=cap)
        report(cy, tr, f"Rev=15/Add=40 cap={cap}", n_base, cap_count=cc)

    # SpeedRead 10sec
    print("\n--- SPEEDREAD (10sec bars) on Rev=15/Add=40 ---")
    for thresh in [25, 30, 35, 40, 45, 50]:
        cy, tr, _ = run_v11(prices, dts, n_ticks, sr=15.0, sa=40.0,
                            sr_arr=tick_sr_10s, sr_th=thresh)
        report(cy, tr, f"SR(10s) thresh={thresh}", n_base)

    # Also: SpeedRead on Rev=15/Add=40 cap=2
    print("\n--- SPEEDREAD (10sec) on Rev=15/Add=40 cap=2 ---")
    for thresh in [30, 40, 50]:
        cy, tr, cc = run_v11(prices, dts, n_ticks, sr=15.0, sa=40.0, cap=2,
                             sr_arr=tick_sr_10s, sr_th=thresh)
        report(cy, tr, f"R15/A40 cap2 SR={thresh}", n_base, cap_count=cc)

    print("\nDone.")


if __name__ == "__main__":
    main()
