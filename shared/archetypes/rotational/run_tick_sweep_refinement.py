# archetype: rotational
"""Refinement sweep: 17 runs around ATR R=2.0x/A=4.0x winner."""

import sys
import json
import copy
import time
import datetime as dt_mod
from pathlib import Path

import numpy as np
import pandas as pd

_REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_REPO))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from shared.data_loader import load_bars
from rotational_simulator import RotationalSimulator

EXCLUDE_HOURS = {1, 19, 20}
_P1_MID = dt_mod.date(2025, 9, 21) + (dt_mod.date(2025, 12, 14) - dt_mod.date(2025, 9, 21)) / 2


def run_config(tick_p1a, tick_atr, base_config, label,
               atr_rev=2.0, atr_add=4.0, atr_period=20, cap=0):
    cfg = copy.deepcopy(base_config)
    cfg["hypothesis"]["trigger_params"]["step_dist"] = 15.0
    cfg["hypothesis"]["trigger_params"]["atr_rev_mult"] = atr_rev
    cfg["hypothesis"]["trigger_params"]["atr_add_mult"] = atr_add
    cfg["martingale"] = {
        "initial_qty": 1, "max_levels": 1, "max_contract_size": 8,
        "max_total_position": 0, "anchor_mode": "walking",
        "flatten_reseed_cap": cap,
    }
    cfg["_instrument"] = {"tick_size": 0.25, "cost_ticks": 1}
    cfg["period"] = "P1a"
    cfg["bar_data_primary"] = {
        "bar_data_1tick_rot": base_config["bar_data_primary"]["bar_data_1tick_rot"]
    }
    cfg["_tick_atr_array"] = tick_atr

    sim = RotationalSimulator(config=cfg, bar_data=tick_p1a, reference_data=None)
    result = sim.run()
    cycles = result.cycles
    trades = result.trades

    if cycles.empty:
        return None

    et = trades[trades["action"].isin(["SEED", "REVERSAL"])]
    ce = et.groupby("cycle_id")["datetime"].first().reset_index()
    ce.columns = ["cycle_id", "entry_dt"]
    cycles = cycles.merge(ce, on="cycle_id", how="left")
    cycles["hour"] = pd.to_datetime(cycles["entry_dt"]).dt.hour
    cf = cycles[~cycles["hour"].isin(EXCLUDE_HOURS)]
    valid_ids = set(cf["cycle_id"])
    tf = trades[trades["cycle_id"].isin(valid_ids)]

    nn = len(cf)
    if nn == 0:
        return None

    gw = cf[cf["gross_pnl_ticks"] > 0]["gross_pnl_ticks"].sum()
    gl = abs(cf[cf["gross_pnl_ticks"] <= 0]["gross_pnl_ticks"].sum())
    gpf = gw / gl if gl > 0 else 0

    cc1 = tf.groupby("cycle_id")["cost_ticks"].sum()
    cf = cf.copy()
    cf["c1"] = cf["cycle_id"].map(cc1).fillna(0)

    results = {}
    for scale, lbl in [(1, "1t"), (2, "2t"), (3, "3t")]:
        cf[f"n_{lbl}"] = cf["gross_pnl_ticks"] - cf["c1"] * scale
        col = f"n_{lbl}"
        nw = cf[cf[col] > 0][col].sum()
        nl = abs(cf[cf[col] <= 0][col].sum())
        results[f"npf_{lbl}"] = nw / nl if nl > 0 else 0
        results[f"net_{lbl}"] = cf[col].sum()

    wr = (cf["gross_pnl_ticks"] > 0).sum() / nn
    mp = int(cf["max_position_qty"].max())
    cap_count = len(cf[cf["exit_reason"] == "flatten_reseed"]) if "exit_reason" in cf.columns else 0

    return {
        "label": label, "cycles": nn, "gpf": round(gpf, 4),
        **{k: round(v, 4) if "npf" in k else int(v) for k, v in results.items()},
        "wr": round(wr, 4), "max_pos": mp, "caps": cap_count,
    }


def main():
    with open(Path(__file__).parent / "rotational_params.json") as f:
        base_config = json.load(f)

    print("Loading data...")
    t0 = time.time()
    tick_bars = load_bars(base_config["bar_data_primary"]["bar_data_1tick_rot"])
    tick_p1a = tick_bars[tick_bars["datetime"].dt.date <= _P1_MID].reset_index(drop=True)

    ohlc = load_bars(base_config["bar_data_primary"]["bar_data_250tick_rot"])
    ohlc_p1a = ohlc[ohlc["datetime"].dt.date <= _P1_MID].reset_index(drop=True)

    print(f"Tick P1a: {len(tick_p1a):,}, 250tick P1a: {len(ohlc_p1a):,}")

    # Build ATR arrays for different periods
    c = ohlc_p1a["Last"].values.astype(float)
    h = ohlc_p1a["High"].values.astype(float)
    lo = ohlc_p1a["Low"].values.astype(float)
    pc = np.empty(len(c)); pc[0] = c[0]; pc[1:] = c[:-1]
    tr = np.maximum(h - lo, np.maximum(np.abs(h - pc), np.abs(lo - pc)))

    ohlc_ts = ohlc_p1a["datetime"].values.astype("int64") // 10**9
    tick_ts = tick_p1a["datetime"].values.astype("int64") // 10**9
    ohlc_idx = np.clip(np.searchsorted(ohlc_ts, tick_ts, side="right") - 1, 0, len(ohlc_p1a) - 1)

    atr_by_period = {}
    for period in [10, 14, 20, 30, 50]:
        atr = pd.Series(tr).rolling(period, min_periods=period).mean().values
        atr_by_period[period] = atr[ohlc_idx]
        print(f"  ATR({period}): median={np.nanmedian(atr):.2f}")

    tick_atr_20 = atr_by_period[20]
    print(f"Loaded in {time.time()-t0:.1f}s")

    hdr = (
        f"{'#':>3} {'Config':<35} {'Cyc':>5} {'GrPF':>6}"
        f" {'NP@1':>6} {'NP@2':>6} {'NP@3':>6}"
        f" {'Net@1t':>8} {'WR':>5} {'MP':>3} {'Caps':>4}"
    )
    print(f"\n{hdr}")
    print("=" * 100)

    idx = 0

    # TEST A: Flatten-reseed cap on ATR R=2.0x/A=4.0x
    print("--- TEST A: Flatten-reseed cap ---")
    for cap in [2, 3, 4]:
        idx += 1
        r = run_config(tick_p1a, tick_atr_20, base_config,
                        f"ATR R=2/A=4 cap={cap}", cap=cap)
        if r:
            m = "<<<" if r["npf_1t"] > 1.2 else ("<<" if r["npf_1t"] > 1.0 else "")
            print(
                f"{idx:>3} {r['label']:<35} {r['cycles']:>5} {r['gpf']:>6.3f}"
                f" {r['npf_1t']:>6.3f} {r['npf_2t']:>6.3f} {r['npf_3t']:>6.3f}"
                f" {r['net_1t']:>+8,} {r['wr']:>5.1%} {r['max_pos']:>3} {r['caps']:>4} {m}"
            )

    # TEST B: ATR lookback sweep
    print("\n--- TEST B: ATR lookback period ---")
    for period in [10, 14, 20, 30, 50]:
        idx += 1
        r = run_config(tick_p1a, atr_by_period[period], base_config,
                        f"ATR(p={period}) R=2/A=4")
        if r:
            m = "<<<" if r["npf_1t"] > 1.2 else ("<<" if r["npf_1t"] > 1.0 else "")
            print(
                f"{idx:>3} {r['label']:<35} {r['cycles']:>5} {r['gpf']:>6.3f}"
                f" {r['npf_1t']:>6.3f} {r['npf_2t']:>6.3f} {r['npf_3t']:>6.3f}"
                f" {r['net_1t']:>+8,} {r['wr']:>5.1%} {r['max_pos']:>3} {r['caps']:>4} {m}"
            )

    # TEST C: Finer ratio grid
    print("\n--- TEST C: Finer ratio grid ---")
    for rm in [1.75, 2.0, 2.25]:
        for am in [3.5, 4.0, 4.5]:
            idx += 1
            r = run_config(tick_p1a, tick_atr_20, base_config,
                            f"ATR R={rm}x A={am}x", atr_rev=rm, atr_add=am)
            if r:
                m = "<<<" if r["npf_1t"] > 1.2 else ("<<" if r["npf_1t"] > 1.0 else "")
                print(
                    f"{idx:>3} {r['label']:<35} {r['cycles']:>5} {r['gpf']:>6.3f}"
                    f" {r['npf_1t']:>6.3f} {r['npf_2t']:>6.3f} {r['npf_3t']:>6.3f}"
                    f" {r['net_1t']:>+8,} {r['wr']:>5.1%} {r['max_pos']:>3} {r['caps']:>4} {m}"
                )

    print(f"\nTotal runtime: {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
