# archetype: rotational
"""V1.1 test battery: 4 tests, 32 runs on P1a tick data.
Exclude hours 1, 19, 20. Directional seed. All V1.1 calibrated path."""

import sys
import json
import copy
import time
import datetime as dt_mod
from pathlib import Path

import numpy as np
import pandas as pd

_REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_REPO_ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from shared.data_loader import load_bars
from feature_engine import _compute_speedread_features

EXCLUDE_HOURS = {1, 19, 20}
_P1_START = dt_mod.date(2025, 9, 21)
_P1_MID = _P1_START + (dt_mod.date(2025, 12, 14) - _P1_START) / 2


def run_v11_tick(prices, dts, n, step_dist=25.0, step_rev=None, step_add=None,
                 pos_cap=0, reentry_delay=0, sr_arr=None, sr_thresh=None,
                 atr_arr=None, med_atr=None, atr_sf=None, cost_ticks=3):
    if step_rev is None:
        step_rev = step_dist
    if step_add is None:
        step_add = step_dist

    tick_size = 0.25
    state = -1  # -1=WATCHING, 1=LONG, 2=SHORT
    wp = 0.0
    anchor = 0.0
    level = 0
    pos = 0
    avg_e = 0.0
    cid = 0
    cstart = 0
    last_pnl = 0.0
    delay_rem = 0

    trades = []
    cycles = []
    ct = []  # cycle trades

    for i in range(n):
        p = prices[i]

        if delay_rem > 0:
            delay_rem -= 1
            continue

        # ATR-adaptive
        er = step_rev
        ea = step_add
        if atr_arr is not None and atr_sf is not None:
            a = atr_arr[i]
            if not np.isnan(a) and a > 0 and med_atr > 0:
                r = (a / med_atr) ** atr_sf
                er = step_rev * r
                ea = step_add * r

        if state == -1:
            # SpeedRead filter
            if sr_arr is not None and sr_thresh is not None and i < len(sr_arr):
                sv = sr_arr[i]
                if not np.isnan(sv) and sv >= sr_thresh:
                    continue

            if wp == 0.0:
                wp = p
                continue
            if p - wp >= step_rev:
                cid += 1; state = 1; anchor = p; pos = 1; avg_e = p; cstart = i
                t = {"i": i, "a": "SEED", "d": "L", "q": 1, "p": p, "c": cost_ticks, "cid": cid}
                trades.append(t); ct = [t]
            elif wp - p >= step_rev:
                cid += 1; state = 2; anchor = p; pos = 1; avg_e = p; cstart = i
                t = {"i": i, "a": "SEED", "d": "S", "q": 1, "p": p, "c": cost_ticks, "cid": cid}
                trades.append(t); ct = [t]
            continue

        dist = p - anchor
        if state == 1:
            fav = dist >= er
            adv = (-dist) >= ea
        else:
            fav = (-dist) >= er
            adv = dist >= ea

        if fav:
            d = "L" if state == 1 else "S"
            nd = "S" if state == 1 else "L"
            # FLATTEN
            ft = {"i": i, "a": "F", "d": d, "q": pos, "p": p, "c": cost_ticks * pos, "cid": cid}
            trades.append(ft); ct.append(ft)
            # Finalize
            ets = [t for t in ct if t["a"] in ("SEED", "R", "ADD")]
            tq = sum(t["q"] for t in ets)
            wa = sum(t["p"] * t["q"] for t in ets) / tq if tq else p
            gr = ((p - wa) / tick_size * tq) if d == "L" else ((wa - p) / tick_size * tq)
            tc = sum(t["c"] for t in ct)
            nt = gr - tc
            ac = sum(1 for t in ets if t["a"] == "ADD")
            mp = 0; rq = 0
            for t in ct:
                if t["a"] == "F":
                    rq = 0
                else:
                    rq += t["q"]; mp = max(mp, rq)
            cycles.append({"cid": cid, "gr": round(gr, 4), "nt": round(nt, 4),
                           "ac": ac, "mp": mp, "dt": dts[cstart], "er": "rev"})
            last_pnl = nt

            # Re-entry delay
            if reentry_delay > 0 and last_pnl < 0:
                delay_rem = reentry_delay
                state = -1; wp = 0.0; pos = 0
                continue

            # New cycle
            cid += 1; state = 2 if d == "L" else 1
            anchor = p; pos = 1; avg_e = p; cstart = i
            rt = {"i": i, "a": "R", "d": nd, "q": 1, "p": p, "c": cost_ticks, "cid": cid}
            trades.append(rt); ct = [rt]

        elif adv:
            # Position cap
            if pos_cap > 0 and pos >= pos_cap:
                d = "L" if state == 1 else "S"
                ft = {"i": i, "a": "F", "d": d, "q": pos, "p": p, "c": cost_ticks * pos, "cid": cid}
                trades.append(ft); ct.append(ft)
                ets = [t for t in ct if t["a"] in ("SEED", "R", "ADD")]
                tq = sum(t["q"] for t in ets)
                wa = sum(t["p"] * t["q"] for t in ets) / tq if tq else p
                gr = ((p - wa) / tick_size * tq) if d == "L" else ((wa - p) / tick_size * tq)
                tc = sum(t["c"] for t in ct)
                nt = gr - tc
                ac = sum(1 for t in ets if t["a"] == "ADD")
                mp = 0; rq = 0
                for t in ct:
                    if t["a"] == "F":
                        rq = 0
                    else:
                        rq += t["q"]; mp = max(mp, rq)
                cycles.append({"cid": cid, "gr": round(gr, 4), "nt": round(nt, 4),
                               "ac": ac, "mp": mp, "dt": dts[cstart], "er": "cap"})
                state = -1; wp = p; pos = 0
                continue

            # ADD (ML=1: always qty=1)
            anchor = p
            oq = pos; pos += 1
            avg_e = (avg_e * oq + p) / pos
            d = "L" if state == 1 else "S"
            at = {"i": i, "a": "ADD", "d": d, "q": 1, "p": p, "c": cost_ticks, "cid": cid}
            trades.append(at); ct.append(at)

    # Finalize open
    if state in (1, 2) and ct:
        lp = prices[n - 1]
        d = "L" if state == 1 else "S"
        ets = [t for t in ct if t["a"] in ("SEED", "R", "ADD")]
        tq = sum(t["q"] for t in ets)
        wa = sum(t["p"] * t["q"] for t in ets) / tq if tq else lp
        gr = ((lp - wa) / tick_size * tq) if d == "L" else ((wa - lp) / tick_size * tq)
        tc = sum(t["c"] for t in ct)
        nt = gr - tc
        ac = sum(1 for t in ets if t["a"] == "ADD")
        mp = 0; rq = 0
        for t in ct:
            if t["a"] == "F":
                rq = 0
            else:
                rq += t["q"]; mp = max(mp, rq)
        cycles.append({"cid": cid, "gr": round(gr, 4), "nt": round(nt, 4),
                       "ac": ac, "mp": mp, "dt": dts[cstart], "er": "eod"})

    return cycles, trades


def analyze(cycles_list, trades_list, label, n_baseline=None):
    if not cycles_list:
        print(f"{label:<35} — no cycles —")
        return

    cdf = pd.DataFrame(cycles_list)
    tdf = pd.DataFrame(trades_list)

    # Hour filter
    cdf["hour"] = pd.to_datetime(cdf["dt"]).dt.hour
    cdf = cdf[~cdf["hour"].isin(EXCLUDE_HOURS)]
    if cdf.empty:
        print(f"{label:<35} — no cycles after hour filter —")
        return
    valid_ids = set(cdf["cid"])
    tdf = tdf[tdf["cid"].isin(valid_ids)]

    n = len(cdf)
    gross = cdf["gr"].sum()
    cost3 = float(tdf["c"].sum())
    cost2 = cost3 * 2 / 3
    net3 = gross - cost3
    net2 = gross - cost2

    gw = cdf[cdf["gr"] > 0]["gr"].sum()
    gl = abs(cdf[cdf["gr"] <= 0]["gr"].sum())
    gpf = gw / gl if gl > 0 else float("inf")

    # Per-cycle net at 2t and 3t
    cc3 = tdf.groupby("cid")["c"].sum()
    cdf = cdf.copy()
    cdf["c3"] = cdf["cid"].map(cc3).fillna(0)
    cdf["n3"] = cdf["gr"] - cdf["c3"]
    cdf["n2"] = cdf["gr"] - cdf["c3"] * 2 / 3

    nw3 = cdf[cdf["n3"] > 0]["n3"].sum()
    nl3 = abs(cdf[cdf["n3"] <= 0]["n3"].sum())
    npf3 = nw3 / nl3 if nl3 > 0 else float("inf")
    nw2 = cdf[cdf["n2"] > 0]["n2"].sum()
    nl2 = abs(cdf[cdf["n2"] <= 0]["n2"].sum())
    npf2 = nw2 / nl2 if nl2 > 0 else float("inf")

    wr = (cdf["gr"] > 0).sum() / n
    w = cdf[cdf["n3"] > 0]
    l = cdf[cdf["n3"] < 0]
    aw = w["n3"].mean() if len(w) > 0 else 0
    al = l["n3"].mean() if len(l) > 0 else 0
    mp = int(cdf["mp"].max())
    aa = cdf["ac"].mean()
    ret = f"{n / n_baseline * 100:.0f}%" if n_baseline else ""

    m3 = "<<<" if npf3 > 1.2 else ("<<" if npf3 > 1.0 else "")
    print(
        f"{label:<35} {n:>6,} {gpf:>7.4f} {npf2:>7.4f} {npf3:>7.4f} "
        f"{net2:>+9,.0f} {net3:>+9,.0f} {wr:>5.1%} {aw:>+7.1f} {al:>+7.1f} "
        f"{mp:>4} {aa:>5.2f} {ret:>5} {m3}"
    )


def main():
    with open(Path(__file__).parent / "rotational_params.json") as f:
        base_config = json.load(f)

    print("Loading tick data...")
    t0 = time.time()
    tick_bars = load_bars(base_config["bar_data_primary"]["bar_data_1tick_rot"])
    print(f"Tick: {len(tick_bars):,} rows in {time.time()-t0:.1f}s")

    print("Loading 250tick bar data...")
    ohlc_bars = load_bars(base_config["bar_data_primary"]["bar_data_250tick_rot"])
    ohlc_p1a = ohlc_bars[ohlc_bars["datetime"].dt.date <= _P1_MID].copy().reset_index(drop=True)
    print(f"250tick P1a: {len(ohlc_p1a):,} bars")

    # Tick P1a
    tick_p1a = tick_bars[tick_bars["datetime"].dt.date <= _P1_MID].copy().reset_index(drop=True)
    prices = tick_p1a["Last"].values.astype(np.float64)
    dts = tick_p1a["datetime"].values
    n_ticks = len(prices)
    print(f"Tick P1a: {n_ticks:,} rows")

    # 250tick -> tick timestamp mapping
    print("Building 250tick->tick map...")
    ohlc_ts = ohlc_p1a["datetime"].values.astype("int64") // 10**9
    tick_ts = tick_p1a["datetime"].values.astype("int64") // 10**9
    ohlc_idx = np.clip(np.searchsorted(ohlc_ts, tick_ts, side="right") - 1, 0, len(ohlc_p1a) - 1)

    # SpeedRead on 250tick
    print("Computing SpeedRead...")
    sr_params = {"lookback": 10, "vol_avg_len": 50, "price_weight": 50,
                 "vol_weight": 50, "smoothing_bars": 3, "atr_length": 20}
    ohlc_sr = _compute_speedread_features(ohlc_p1a.copy(), sr_params)
    sr_composite = ohlc_sr["speed_composite"].values
    tick_sr = sr_composite[ohlc_idx]

    # ATR on 250tick
    print("Computing ATR...")
    c = ohlc_p1a["Last"].values.astype(float)
    h = ohlc_p1a["High"].values.astype(float)
    lo = ohlc_p1a["Low"].values.astype(float)
    pc = np.empty(len(c)); pc[0] = c[0]; pc[1:] = c[:-1]
    tr = np.maximum(h - lo, np.maximum(np.abs(h - pc), np.abs(lo - pc)))
    atr20 = pd.Series(tr).rolling(20, min_periods=20).mean().values
    med_atr = float(np.nanmedian(atr20))
    tick_atr = atr20[ohlc_idx]
    print(f"Median ATR: {med_atr:.4f}")

    hdr = (
        f"{'Config':<35} {'Cyc':>6} {'GrPF':>7} {'NP@2':>7} {'NP@3':>7} "
        f"{'Net@2t':>9} {'Net@3t':>9} {'WR':>5} {'AvgW':>7} {'AvgL':>7} "
        f"{'MP':>4} {'A/c':>5} {'Ret':>5}"
    )
    print(f"\n{hdr}")
    print("=" * 130)

    # TEST 2
    print("--- TEST 2: Position cap flatten-and-reseed ---")
    for sd in [10.0, 15.0, 20.0, 25.0]:
        for cap in [2, 3, 4, 5]:
            t1 = time.time()
            cy, tr = run_v11_tick(prices, dts, n_ticks, step_dist=sd, pos_cap=cap)
            analyze(cy, tr, f"SD={sd:.0f} cap={cap}")

    # TEST 3: SpeedRead
    print("\n--- TEST 3: SpeedRead on Rev=15/Add=40 ---")
    cy_b, tr_b = run_v11_tick(prices, dts, n_ticks, step_rev=15.0, step_add=40.0)
    cdf_b = pd.DataFrame(cy_b)
    cdf_b["hour"] = pd.to_datetime(cdf_b["dt"]).dt.hour
    n_base = len(cdf_b[~cdf_b["hour"].isin(EXCLUDE_HOURS)])
    analyze(cy_b, tr_b, "Baseline (no filter)", n_baseline=n_base)
    for thresh in [25, 30, 35, 40, 45, 50]:
        cy, tr = run_v11_tick(prices, dts, n_ticks, step_rev=15.0, step_add=40.0,
                              sr_arr=tick_sr, sr_thresh=thresh)
        analyze(cy, tr, f"SR thresh={thresh}", n_baseline=n_base)

    # TEST 4: Re-entry delay
    print("\n--- TEST 4: Re-entry delay on Rev=15/Add=40 ---")
    for delay in [25, 50, 100, 200, 400]:
        cy, tr = run_v11_tick(prices, dts, n_ticks, step_rev=15.0, step_add=40.0,
                              reentry_delay=delay)
        analyze(cy, tr, f"Delay={delay} ticks", n_baseline=n_base)

    # TEST 5: ATR-adaptive
    print("\n--- TEST 5: ATR-adaptive on Rev=15/Add=40 ---")
    for sf in [0.5, 0.75, 1.0, 1.25, 1.5]:
        cy, tr = run_v11_tick(prices, dts, n_ticks, step_rev=15.0, step_add=40.0,
                              atr_arr=tick_atr, med_atr=med_atr, atr_sf=sf)
        analyze(cy, tr, f"ATR scale={sf:.2f}", n_baseline=n_base)

    print("\nDone.")


if __name__ == "__main__":
    main()
