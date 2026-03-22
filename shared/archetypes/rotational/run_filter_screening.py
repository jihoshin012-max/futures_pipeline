# archetype: rotational
# STATUS: ONE-TIME
# PURPOSE: Filter screening (SpeedRead, time-of-day, ATR/volume)
# LAST RUN: 2026-03

"""Filter screening: SpeedRead, H11 time-of-day, H13 ATR/volume conditions.

Tests on/off filters against 3 Mode B profiles on 250tick P1a.
Constraint: filters must retain >= 50% of baseline cycles.

Usage:
    python run_filter_screening.py --filter speedread
    python run_filter_screening.py --filter h13
    python run_filter_screening.py --filter all
"""

from __future__ import annotations

import argparse
import copy
import itertools
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

_ARCHETYPE_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _ARCHETYPE_DIR.parents[2]
sys.path.insert(0, str(_REPO_ROOT))
sys.path.insert(0, str(_ARCHETYPE_DIR))

from shared.data_loader import load_bars, parse_instruments_md  # noqa: E402
from rotational_simulator import RotationalSimulator  # noqa: E402
from rotational_engine import compute_extended_metrics  # noqa: E402
from feature_engine import _compute_speedread_features  # noqa: E402

_CONFIG_PATH = _ARCHETYPE_DIR / "rotational_params.json"
_PROFILES_DIR = _ARCHETYPE_DIR / "profiles"
_OUTPUT_DIR = _ARCHETYPE_DIR / "screening_results"

PROFILES = {
    "MOST_CONSISTENT": {"step_dist": 5.0, "max_levels": 1, "max_total_position": 1},
    "SAFEST": {"step_dist": 10.0, "max_levels": 1, "max_total_position": 1},
    "MAX_PROFIT": {"step_dist": 6.0, "max_levels": 1, "max_total_position": 8},
}

MIN_RETENTION = 0.50  # 50% minimum cycle retention


def _make_config(base_config: dict, profile: dict) -> dict:
    cfg = copy.deepcopy(base_config)
    cfg["hypothesis"]["trigger_params"]["step_dist"] = profile["step_dist"]
    cfg["martingale"] = {
        "initial_qty": 1,
        "max_levels": profile["max_levels"],
        "max_contract_size": 16,
        "max_total_position": profile["max_total_position"],
        "anchor_mode": "walking",
    }
    cfg["_instrument"] = {"tick_size": 0.25, "cost_ticks": 3}
    cfg["period"] = "P1a"
    cfg["bar_data_primary"] = {
        "bar_data_250tick_rot": base_config["bar_data_primary"]["bar_data_250tick_rot"]
    }
    return cfg


def _run_baseline(cfg: dict, bars: pd.DataFrame) -> tuple:
    """Run baseline simulation, return (cycles_df, trades_df)."""
    sim = RotationalSimulator(config=cfg, bar_data=bars, reference_data=None)
    result = sim.run()
    return result.cycles, result.trades


def _compute_pf(cycles: pd.DataFrame) -> float:
    if cycles.empty:
        return 0.0
    w = cycles[cycles["net_pnl_ticks"] > 0]["net_pnl_ticks"].sum()
    l = abs(cycles[cycles["net_pnl_ticks"] <= 0]["net_pnl_ticks"].sum())
    return w / l if l > 0 else float("inf")


def _compute_calmar(cycles: pd.DataFrame) -> float:
    if cycles.empty:
        return 0.0
    cum = cycles["net_pnl_ticks"].cumsum()
    dd = (cum - cum.cummax()).min()
    if dd >= 0:
        return float("inf")
    return cum.iloc[-1] / abs(dd)


# ---------------------------------------------------------------------------
# SpeedRead filter screening
# ---------------------------------------------------------------------------

def run_speedread_screening(
    base_config: dict, bars: pd.DataFrame
) -> pd.DataFrame:
    """Sweep SpeedRead parameters as on/off filter for each profile."""
    lookbacks = [5, 10, 15, 20, 30]
    vol_avg_lens = [20, 50, 100]
    weight_combos = [(70, 30), (50, 50), (30, 70)]
    thresholds = [25, 30, 35, 40, 45, 50]
    smoothing_vals = [1, 3, 5]

    rows = []
    total_combos = (
        len(PROFILES)
        * len(lookbacks)
        * len(vol_avg_lens)
        * len(weight_combos)
        * len(thresholds)
        * len(smoothing_vals)
    )
    print(f"SpeedRead: {total_combos} total experiments")

    run_count = 0
    t0 = time.time()

    for pname, pconf in PROFILES.items():
        cfg = _make_config(base_config, pconf)
        cycles, trades = _run_baseline(cfg, bars)
        n_baseline = len(cycles)
        pf_baseline = _compute_pf(cycles)
        pnl_baseline = cycles["net_pnl_ticks"].sum()

        # Get entry datetime for each cycle
        entry_trades = trades[trades["action"].isin(["SEED", "REVERSAL"])].copy()
        cycle_entry = entry_trades.groupby("cycle_id").first().reset_index()

        # Precompute SpeedRead features for all parameter combos on the bars
        for lb in lookbacks:
            for val in vol_avg_lens:
                for pw, vw in weight_combos:
                    for sm in smoothing_vals:
                        params = {
                            "lookback": lb,
                            "vol_avg_len": val,
                            "price_weight": pw,
                            "vol_weight": vw,
                            "smoothing_bars": sm,
                            "atr_length": 20,
                        }
                        bars_feat = _compute_speedread_features(bars.copy(), params)
                        composite = bars_feat["speed_composite"].values

                        # Map bar_idx to composite value
                        for thresh in thresholds:
                            # Filter cycles: at entry bar, check composite < threshold
                            mask = []
                            for _, ce in cycle_entry.iterrows():
                                bidx = ce["bar_idx"]
                                if bidx > 0 and bidx < len(composite):
                                    # Use PREVIOUS bar's composite (entry-time safe)
                                    val_at_entry = composite[bidx - 1]
                                    mask.append(
                                        not np.isnan(val_at_entry)
                                        and val_at_entry < thresh
                                    )
                                else:
                                    mask.append(True)  # no data = allow

                            filtered_cycle_ids = cycle_entry[mask]["cycle_id"].values
                            filtered = cycles[cycles["cycle_id"].isin(filtered_cycle_ids)]

                            n_filtered = len(filtered)
                            retention = n_filtered / n_baseline if n_baseline > 0 else 0

                            if retention < MIN_RETENTION:
                                continue  # skip, below 50% retention

                            pf_filtered = _compute_pf(filtered)
                            pnl_filtered = filtered["net_pnl_ticks"].sum()
                            calmar = _compute_calmar(filtered)

                            rows.append({
                                "filter": "SPEEDREAD",
                                "profile": pname,
                                "lookback": lb,
                                "vol_avg_len": val,
                                "price_weight": pw,
                                "vol_weight": vw,
                                "smoothing": sm,
                                "threshold": thresh,
                                "n_baseline": n_baseline,
                                "n_filtered": n_filtered,
                                "retention": round(retention, 4),
                                "pf_baseline": round(pf_baseline, 4),
                                "pf_filtered": round(pf_filtered, 4),
                                "pf_delta": round(pf_filtered - pf_baseline, 4),
                                "pnl_baseline": pnl_baseline,
                                "pnl_filtered": pnl_filtered,
                                "calmar": round(calmar, 2),
                            })

                            run_count += 1
                            if run_count % 200 == 0:
                                elapsed = time.time() - t0
                                print(
                                    f"  {run_count} filter evaluations in {elapsed:.0f}s"
                                )

    df = pd.DataFrame(rows)
    print(f"SpeedRead complete: {len(df)} valid results (>= 50% retention)")
    return df


# ---------------------------------------------------------------------------
# H13 ATR/Volume filter screening
# ---------------------------------------------------------------------------

def run_h13_screening(
    base_config: dict, bars: pd.DataFrame
) -> pd.DataFrame:
    """Test ATR spike and volume spike as on/off filters."""
    rows = []

    # Precompute ATR and volume features
    close = bars["Last"].values.astype(float)
    high = bars["High"].values.astype(float)
    low = bars["Low"].values.astype(float)
    volume = bars["Volume"].values.astype(float)

    prev_close = np.empty(len(bars))
    prev_close[0] = close[0]
    prev_close[1:] = close[:-1]
    tr = np.maximum(high - low, np.maximum(np.abs(high - prev_close), np.abs(low - prev_close)))

    # Rolling ATR (20-bar)
    atr_20 = pd.Series(tr).rolling(20, min_periods=20).mean().values
    # Longer-term ATR average (100-bar)
    atr_100 = pd.Series(tr).rolling(100, min_periods=100).mean().values
    # ATR ratio
    atr_ratio = np.where((atr_100 > 0) & ~np.isnan(atr_100), atr_20 / atr_100, np.nan)

    # Volume average (50-bar)
    vol_avg_50 = pd.Series(volume).rolling(50, min_periods=50).mean().values
    vol_ratio = np.where((vol_avg_50 > 0) & ~np.isnan(vol_avg_50), volume / vol_avg_50, np.nan)

    for pname, pconf in PROFILES.items():
        cfg = _make_config(base_config, pconf)
        cycles, trades = _run_baseline(cfg, bars)
        n_baseline = len(cycles)
        pf_baseline = _compute_pf(cycles)
        pnl_baseline = cycles["net_pnl_ticks"].sum()

        entry_trades = trades[trades["action"].isin(["SEED", "REVERSAL"])].copy()
        cycle_entry = entry_trades.groupby("cycle_id").first().reset_index()

        # ATR spike filter
        for atr_mult in [1.5, 2.0, 2.5, 3.0]:
            mask = []
            for _, ce in cycle_entry.iterrows():
                bidx = ce["bar_idx"]
                if bidx > 0 and bidx < len(atr_ratio):
                    val = atr_ratio[bidx - 1]
                    mask.append(np.isnan(val) or val < atr_mult)
                else:
                    mask.append(True)

            filtered_ids = cycle_entry[mask]["cycle_id"].values
            filtered = cycles[cycles["cycle_id"].isin(filtered_ids)]
            n_f = len(filtered)
            ret = n_f / n_baseline if n_baseline > 0 else 0
            if ret < MIN_RETENTION:
                continue

            rows.append({
                "filter": "H13_ATR",
                "profile": pname,
                "param": f"atr_mult={atr_mult}",
                "n_baseline": n_baseline,
                "n_filtered": n_f,
                "retention": round(ret, 4),
                "pf_baseline": round(pf_baseline, 4),
                "pf_filtered": round(_compute_pf(filtered), 4),
                "pf_delta": round(_compute_pf(filtered) - pf_baseline, 4),
                "pnl_baseline": pnl_baseline,
                "pnl_filtered": filtered["net_pnl_ticks"].sum(),
                "calmar": round(_compute_calmar(filtered), 2),
            })

        # Volume spike filter
        for vol_mult in [2.0, 3.0, 4.0, 5.0]:
            mask = []
            for _, ce in cycle_entry.iterrows():
                bidx = ce["bar_idx"]
                if bidx > 0 and bidx < len(vol_ratio):
                    val = vol_ratio[bidx - 1]
                    mask.append(np.isnan(val) or val < vol_mult)
                else:
                    mask.append(True)

            filtered_ids = cycle_entry[mask]["cycle_id"].values
            filtered = cycles[cycles["cycle_id"].isin(filtered_ids)]
            n_f = len(filtered)
            ret = n_f / n_baseline if n_baseline > 0 else 0
            if ret < MIN_RETENTION:
                continue

            rows.append({
                "filter": "H13_VOL",
                "profile": pname,
                "param": f"vol_mult={vol_mult}",
                "n_baseline": n_baseline,
                "n_filtered": n_f,
                "retention": round(ret, 4),
                "pf_baseline": round(pf_baseline, 4),
                "pf_filtered": round(_compute_pf(filtered), 4),
                "pf_delta": round(_compute_pf(filtered) - pf_baseline, 4),
                "pnl_baseline": pnl_baseline,
                "pnl_filtered": filtered["net_pnl_ticks"].sum(),
                "calmar": round(_compute_calmar(filtered), 2),
            })

    df = pd.DataFrame(rows)
    print(f"H13 complete: {len(df)} valid results")
    return df


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Filter screening for Mode B profiles")
    parser.add_argument(
        "--filter",
        choices=["speedread", "h13", "all"],
        default="all",
        help="Which filter to run",
    )
    args = parser.parse_args()

    with open(_CONFIG_PATH) as f:
        base_config = json.load(f)

    instrument_info = parse_instruments_md("NQ")
    print(f"Instrument: NQ, cost_ticks={instrument_info['cost_ticks']}")

    bars = load_bars(base_config["bar_data_primary"]["bar_data_250tick_rot"])
    print(f"Loaded {len(bars)} bars (250tick)")

    _OUTPUT_DIR.mkdir(exist_ok=True)

    if args.filter in ("speedread", "all"):
        print("\n--- SpeedRead Screening ---")
        sr_df = run_speedread_screening(base_config, bars)
        sr_path = _OUTPUT_DIR / "speedread_screening.tsv"
        sr_df.to_csv(sr_path, sep="\t", index=False)
        print(f"Written: {sr_path}")

        # Print top 5 per profile
        for pname in PROFILES:
            sub = sr_df[sr_df["profile"] == pname].sort_values("pf_delta", ascending=False)
            print(f"\n  Top 5 SpeedRead for {pname}:")
            for _, r in sub.head(5).iterrows():
                print(
                    f"    lb={r['lookback']} va={r['vol_avg_len']} "
                    f"w={r['price_weight']}/{r['vol_weight']} "
                    f"sm={r['smoothing']} th={r['threshold']} "
                    f"-> PF {r['pf_baseline']:.2f}->{r['pf_filtered']:.2f} "
                    f"(+{r['pf_delta']:.2f}) ret={r['retention']:.0%}"
                )

    if args.filter in ("h13", "all"):
        print("\n--- H13 ATR/Volume Screening ---")
        h13_df = run_h13_screening(base_config, bars)
        h13_path = _OUTPUT_DIR / "h13_screening.tsv"
        h13_df.to_csv(h13_path, sep="\t", index=False)
        print(f"Written: {h13_path}")

        for pname in PROFILES:
            sub = h13_df[h13_df["profile"] == pname].sort_values("pf_delta", ascending=False)
            print(f"\n  H13 results for {pname}:")
            for _, r in sub.iterrows():
                print(
                    f"    {r['filter']} {r['param']} "
                    f"-> PF {r['pf_baseline']:.2f}->{r['pf_filtered']:.2f} "
                    f"(+{r['pf_delta']:.2f}) ret={r['retention']:.0%} "
                    f"PnL={r['pnl_filtered']:,.0f}"
                )

    print("\nDone.")


if __name__ == "__main__":
    main()
