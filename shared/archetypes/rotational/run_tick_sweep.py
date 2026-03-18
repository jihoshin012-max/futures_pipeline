# archetype: rotational
"""Tick-data sweep harness for rotational archetype.

Runs all candidate configs on P1a 1-tick data. Supports:
  - V1.1 (MTP=0): fixed asymmetric, ATR-normalized asymmetric
  - V2 (MTP>0): symmetric step with MTP cap + anchor mode
  - Flatten-reseed cap mode
  - Time-of-day filter (exclude hours)
  - Reports at 1-tick, 2-tick, and 3-tick cost levels

Usage:
    python run_tick_sweep.py [--dry-run]
"""

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
_P1_START = dt_mod.date(2025, 9, 21)
_P1_END = dt_mod.date(2025, 12, 14)
_P1_MID = _P1_START + (_P1_END - _P1_START) / 2


def build_sweep_grid():
    """Build the sweep grid. Returns list of (label, config_patch) tuples."""
    grid = []

    # --- GROUP A: V1.1 ATR-normalized asymmetric (MTP=0, ML=1) ---
    for rm in [1.5, 2.0, 2.5, 3.0]:
        for am in [4.0, 5.0, 6.0, 7.0]:
            grid.append((
                f"ATR R={rm}x A={am}x",
                {
                    "hypothesis.trigger_params.step_dist": 15.0,  # fallback
                    "hypothesis.trigger_params.atr_rev_mult": rm,
                    "hypothesis.trigger_params.atr_add_mult": am,
                    "martingale.max_total_position": 0,
                    "martingale.anchor_mode": "walking",
                    "martingale.flatten_reseed_cap": 0,
                },
            ))

    # --- GROUP B: V1.1 fixed asymmetric (MTP=0, ML=1) ---
    for rev, add in [(15, 40), (15, 35), (20, 40), (20, 50)]:
        grid.append((
            f"Fixed R={rev} A={add}",
            {
                "hypothesis.trigger_params.step_dist": rev,
                "hypothesis.trigger_params.step_dist_reversal": rev,
                "hypothesis.trigger_params.step_dist_add": add,
                "martingale.max_total_position": 0,
                "martingale.anchor_mode": "walking",
                "martingale.flatten_reseed_cap": 0,
            },
        ))

    # --- GROUP C: V2 symmetric (MTP=1,2,3; Mode A and B) ---
    for sd in [20, 25, 30]:
        for mtp in [1, 2, 3]:
            modes = ["walking"] if mtp == 1 else ["frozen", "walking"]
            for mode in modes:
                grid.append((
                    f"V2 SD={sd} MTP={mtp} {mode[:4]}",
                    {
                        "hypothesis.trigger_params.step_dist": sd,
                        "martingale.max_total_position": mtp,
                        "martingale.anchor_mode": mode,
                        "martingale.flatten_reseed_cap": 0,
                    },
                ))

    # --- GROUP D: Flatten-reseed cap (symmetric, MTP=0) ---
    for sd in [20, 25]:
        for cap in [2, 3]:
            grid.append((
                f"FRC SD={sd} cap={cap}",
                {
                    "hypothesis.trigger_params.step_dist": sd,
                    "martingale.max_total_position": 0,
                    "martingale.anchor_mode": "walking",
                    "martingale.flatten_reseed_cap": cap,
                },
            ))

    return grid


def apply_patch(base_config, patch):
    """Apply a flat key=value patch to a nested config dict."""
    cfg = copy.deepcopy(base_config)
    for key, val in patch.items():
        parts = key.split(".")
        d = cfg
        for p in parts[:-1]:
            d = d.setdefault(p, {})
        d[parts[-1]] = val
    # Ensure ML=1 everywhere
    cfg["martingale"]["max_levels"] = 1
    cfg["martingale"]["max_contract_size"] = 8
    cfg["martingale"]["initial_qty"] = 1
    cfg["_instrument"] = {"tick_size": 0.25, "cost_ticks": 1}
    cfg["period"] = "P1a"
    return cfg


def run_and_analyze(cfg, bars, tick_atr, dts_all, label):
    """Run simulator and return stats dict."""
    # Inject ATR array if ATR-normalized
    tp = cfg.get("hypothesis", {}).get("trigger_params", {})
    if tp.get("atr_rev_mult", 0) > 0:
        cfg["_tick_atr_array"] = tick_atr

    sim = RotationalSimulator(config=cfg, bar_data=bars, reference_data=None)
    result = sim.run()
    cycles = result.cycles
    trades = result.trades

    if cycles.empty:
        return None

    # Hour filter
    entry_t = trades[trades["action"].isin(["SEED", "REVERSAL"])]
    ce = entry_t.groupby("cycle_id")["datetime"].first().reset_index()
    ce.columns = ["cycle_id", "entry_dt"]
    cycles = cycles.merge(ce, on="cycle_id", how="left")
    cycles["hour"] = pd.to_datetime(cycles["entry_dt"]).dt.hour
    cf = cycles[~cycles["hour"].isin(EXCLUDE_HOURS)]
    valid_ids = set(cf["cycle_id"])
    tf = trades[trades["cycle_id"].isin(valid_ids)]

    nn = len(cf)
    if nn == 0:
        return None

    gross = cf["gross_pnl_ticks"].sum()
    cost1 = float(tf["cost_ticks"].sum())  # at 1t (cost_ticks=1 in config)
    gw = cf[cf["gross_pnl_ticks"] > 0]["gross_pnl_ticks"].sum()
    gl = abs(cf[cf["gross_pnl_ticks"] <= 0]["gross_pnl_ticks"].sum())
    gpf = gw / gl if gl > 0 else 0

    # Per-cycle cost for scaling
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
    w = cf[cf["n_1t"] > 0]
    lo = cf[cf["n_1t"] < 0]
    mp = int(cf["max_position_qty"].max())
    aa = cf["adds_count"].mean()

    return {
        "label": label,
        "cycles": nn,
        "gpf": round(gpf, 4),
        **{k: round(v, 4) if "npf" in k else int(v) for k, v in results.items()},
        "wr": round(wr, 4),
        "avg_w": round(w["n_1t"].mean(), 1) if len(w) > 0 else 0,
        "avg_l": round(lo["n_1t"].mean(), 1) if len(lo) > 0 else 0,
        "max_pos": mp,
        "adds_per_cyc": round(aa, 2),
    }


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    grid = build_sweep_grid()
    print(f"Sweep grid: {len(grid)} configs")

    if args.dry_run:
        for i, (label, patch) in enumerate(grid):
            print(f"  [{i+1:>3}] {label}")
        print(f"\nEstimated runtime: {len(grid) * 63 / 60:.0f} minutes")
        return

    with open(Path(__file__).parent / "rotational_params.json") as f:
        base_config = json.load(f)

    print("Loading tick data...")
    t0 = time.time()
    tick_bars = load_bars(base_config["bar_data_primary"]["bar_data_1tick_rot"])
    tick_p1a = tick_bars[tick_bars["datetime"].dt.date <= _P1_MID].reset_index(drop=True)
    print(f"Tick P1a: {len(tick_p1a):,} rows in {time.time()-t0:.1f}s")

    # ATR from 250tick mapped to ticks
    print("Computing ATR mapping...")
    ohlc = load_bars(base_config["bar_data_primary"]["bar_data_250tick_rot"])
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
    print(f"ATR mapped. Median: {np.nanmedian(atr20):.2f}")

    # Set bar_data_primary to tick only
    base_config["bar_data_primary"] = {
        "bar_data_1tick_rot": base_config["bar_data_primary"]["bar_data_1tick_rot"]
    }

    hdr = (
        f"{'#':>3} {'Config':<30} {'Cyc':>5} {'GrPF':>6}"
        f" {'NP@1':>6} {'NP@2':>6} {'NP@3':>6}"
        f" {'Net@1t':>8} {'WR':>5} {'AvgW':>6} {'AvgL':>6}"
        f" {'MP':>3} {'A/c':>4} {'Sec':>4}"
    )
    print(f"\n{hdr}")
    print("=" * 110)

    results = []
    for idx, (label, patch) in enumerate(grid):
        cfg = apply_patch(base_config, patch)
        t1 = time.time()
        r = run_and_analyze(cfg, tick_p1a, tick_atr, tick_p1a["datetime"].values, label)
        elapsed = time.time() - t1

        if r is None:
            print(f"{idx+1:>3} {label:<30} — no cycles —")
            continue

        m = "<<<" if r["npf_1t"] > 1.2 else ("<<" if r["npf_1t"] > 1.0 else "")
        print(
            f"{idx+1:>3} {label:<30} {r['cycles']:>5} {r['gpf']:>6.3f}"
            f" {r['npf_1t']:>6.3f} {r['npf_2t']:>6.3f} {r['npf_3t']:>6.3f}"
            f" {r['net_1t']:>+8,} {r['wr']:>5.1%} {r['avg_w']:>+6.0f} {r['avg_l']:>+6.0f}"
            f" {r['max_pos']:>3} {r['adds_per_cyc']:>4.1f} {elapsed:>4.0f} {m}"
        )
        results.append(r)

    # Write results
    if results:
        out = Path(__file__).parent / "screening_results" / "tick_sweep_results.tsv"
        out.parent.mkdir(exist_ok=True)
        pd.DataFrame(results).to_csv(out, sep="\t", index=False)
        print(f"\nResults written: {out}")

    print(f"\nTotal runtime: {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
