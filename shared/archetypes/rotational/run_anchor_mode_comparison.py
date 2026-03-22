# archetype: rotational
# STATUS: HISTORICAL
# PURPOSE: OHLC-era anchor mode comparison (superseded by tick-data harness)
# LAST RUN: unknown

# WARNING: OHLC-era harness. Functional but superseded by tick-data harness
# (run_tick_sweep.py). Do not use for parameter selection — OHLC results are
# not trustworthy for absolute PF. See .planning/lessons.md for details.
"""Anchor mode comparison harness — tests 3 anchor behaviors on MTP refusal.

Mode A (frozen):      Anchor stays at last successful trade price. Current default.
Mode B (walking):     Anchor updates to current price on MTP refusal.
Mode C (frozen_stop): Anchor frozen + hard stop at unrealized PnL threshold.

Runs against 3 winning configs (MAX_PROFIT profile) on P1a:
  - 250vol:  SD=7.0, ML=1, MTP=2
  - 250tick: SD=4.5, ML=1, MTP=1
  - 10sec:   SD=10.0, ML=1, MTP=4

Total: 3 (Mode A) + 3 (Mode B) + 9 (Mode C × 3 thresholds) = 15 runs.
Mode A uses existing baseline data from profiles; only 12 new simulator runs needed.

Usage:
    python run_anchor_mode_comparison.py
    python run_anchor_mode_comparison.py --dry-run
    python run_anchor_mode_comparison.py --output-dir anchor_comparison/
"""

from __future__ import annotations

import argparse
import copy
import json
import sys
import time
from pathlib import Path

import pandas as pd

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_REPO_ROOT))

_ARCHETYPE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_ARCHETYPE_DIR))

from shared.data_loader import load_bars, parse_instruments_md  # noqa: E402
from rotational_simulator import RotationalSimulator  # noqa: E402
from rotational_engine import compute_extended_metrics  # noqa: E402

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_CONFIG_PATH = _ARCHETYPE_DIR / "rotational_params.json"
_INSTRUMENTS_MD = _REPO_ROOT / "_config/instruments.md"
_PROFILES_DIR = _ARCHETYPE_DIR / "profiles"

# Mode C drawdown exit thresholds (in ticks, negative)
MODE_C_THRESHOLDS = [-40, -60, -80]

# The 3 winning configs from MAX_PROFIT profile
WINNING_CONFIGS = {
    "bar_data_250vol_rot": {"step_dist": 7.0, "max_levels": 1, "max_total_position": 2},
    "bar_data_250tick_rot": {"step_dist": 4.5, "max_levels": 1, "max_total_position": 1},
    "bar_data_10sec_rot": {"step_dist": 10.0, "max_levels": 1, "max_total_position": 4},
}

# Comparison output columns
COMPARISON_COLUMNS = [
    "anchor_mode", "mtp_dd_exit_ticks", "source_id",
    "step_dist", "max_levels", "max_total_position",
    "cycle_pf", "n_cycles", "win_rate", "total_pnl_ticks",
    "max_drawdown_ticks", "sharpe", "worst_cycle_dd",
    "max_level_exposure_pct", "tail_ratio",
    "calmar_ratio", "sortino_ratio", "winning_session_pct",
    "max_dd_duration_bars", "bars_processed",
    "avg_cycle_duration_bars", "n_mtp_dd_exit_cycles",
]


# ---------------------------------------------------------------------------
# Config builder
# ---------------------------------------------------------------------------

def build_run_config(
    source_id: str,
    winning_cfg: dict,
    anchor_mode: str,
    mtp_dd_exit_ticks: float,
    base_params: dict,
    instrument_info: dict,
) -> dict:
    """Assemble a full simulator config for one anchor mode comparison run."""
    return {
        "version": base_params.get("version", "v1"),
        "instrument": base_params.get("instrument", "NQ"),
        "archetype": base_params.get("archetype", {
            "name": "rotational",
            "simulator_module": "rotational_simulator",
        }),
        "period": "P1a",
        "bar_data_primary": {
            source_id: base_params["bar_data_primary"].get(source_id, "")
        },
        "bar_data_reference": {},
        "hypothesis": {
            "trigger_mechanism": "fixed",
            "trigger_params": {"step_dist": float(winning_cfg["step_dist"])},
            "symmetry": "symmetric",
            "symmetry_params": {},
            "active_filters": [],
            "filter_params": {},
            "structural_mods": [],
            "structural_params": {},
        },
        "martingale": {
            "initial_qty": 1,
            "max_levels": int(winning_cfg["max_levels"]),
            "max_contract_size": 16,
            "max_total_position": int(winning_cfg["max_total_position"]),
            "progression": "geometric",
            "anchor_mode": anchor_mode,
            "mtp_dd_exit_ticks": float(mtp_dd_exit_ticks),
        },
        # No TDS for this comparison — isolating anchor behavior
        "trend_defense": {"enabled": False},
        "_instrument": instrument_info,
    }


# ---------------------------------------------------------------------------
# Filtered bar helper (same as run_tds_calibration.py)
# ---------------------------------------------------------------------------

def _get_filtered_bars(cfg: dict, bars: pd.DataFrame) -> pd.DataFrame:
    """Apply the same date+RTH filter the simulator uses."""
    import datetime

    _P1_START = datetime.date(2025, 9, 21)
    _P1_END = datetime.date(2025, 12, 14)
    _P1_MIDPOINT = _P1_START + (_P1_END - _P1_START) / 2
    _RTH_START = datetime.time(9, 30, 0)
    _RTH_END = datetime.time(16, 0, 0)

    mask = pd.Series(True, index=bars.index)
    period = cfg.get("period", "").lower()

    if period in ("p1a", "p1b"):
        dates = bars["datetime"].dt.date
        if period == "p1a":
            mask &= (dates >= _P1_START) & (dates <= _P1_MIDPOINT)
        else:
            mask &= (dates > _P1_MIDPOINT) & (dates <= _P1_END)

    source_ids = list(cfg.get("bar_data_primary", {}).keys())
    is_10sec_source = any("10sec" in sid for sid in source_ids)

    if is_10sec_source and "Time" in bars.columns:
        def _parse_time(t_str: str) -> datetime.time:
            parts = str(t_str).strip().split(":")
            h = int(parts[0])
            m = int(parts[1])
            s = int(float(parts[2])) if len(parts) > 2 else 0
            return datetime.time(h, m, s)

        times = bars["Time"].apply(_parse_time)
        mask &= (times >= _RTH_START) & (times < _RTH_END)

    return bars[mask].reset_index(drop=True)


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def run_single(
    source_id: str,
    winning_cfg: dict,
    anchor_mode: str,
    mtp_dd_exit_ticks: float,
    bars: pd.DataFrame,
    base_params: dict,
    instrument_info: dict,
) -> dict:
    """Run one anchor mode comparison and return metrics dict."""
    cfg = build_run_config(
        source_id, winning_cfg, anchor_mode, mtp_dd_exit_ticks,
        base_params, instrument_info,
    )

    sim = RotationalSimulator(config=cfg, bar_data=bars, reference_data=None)
    result = sim.run()

    filtered_bars = _get_filtered_bars(cfg, bars)
    cost_ticks = instrument_info["cost_ticks"]

    extended = compute_extended_metrics(
        result.cycles,
        cost_ticks,
        bars_df=filtered_bars,
        max_levels=int(winning_cfg["max_levels"]),
    )

    # Count mtp_dd_exit cycles
    n_mtp_dd_exit = 0
    if not result.cycles.empty and "exit_reason" in result.cycles.columns:
        n_mtp_dd_exit = int((result.cycles["exit_reason"] == "mtp_dd_exit").sum())

    # Average cycle duration
    avg_cycle_dur = 0.0
    if not result.cycles.empty and "duration_bars" in result.cycles.columns:
        avg_cycle_dur = round(float(result.cycles["duration_bars"].mean()), 1)

    return {
        "anchor_mode": anchor_mode,
        "mtp_dd_exit_ticks": mtp_dd_exit_ticks,
        "source_id": source_id,
        "step_dist": winning_cfg["step_dist"],
        "max_levels": winning_cfg["max_levels"],
        "max_total_position": winning_cfg["max_total_position"],
        "bars_processed": result.bars_processed,
        "avg_cycle_duration_bars": avg_cycle_dur,
        "n_mtp_dd_exit_cycles": n_mtp_dd_exit,
        **extended,
    }


def load_mode_a_baselines() -> list[dict]:
    """Load Mode A (frozen anchor) baseline metrics from MAX_PROFIT profile JSON.

    These are the existing no-TDS, no-anchor-mode results — identical to frozen anchor
    since anchor_mode defaults to 'frozen' and was the behavior when profiles were generated.
    """
    profile_path = _PROFILES_DIR / "max_profit.json"
    with open(profile_path, "r", encoding="utf-8") as f:
        profile = json.load(f)

    rows = []
    for source_id, bt_config in profile["bar_types"].items():
        if source_id not in WINNING_CONFIGS:
            continue
        winning = WINNING_CONFIGS[source_id]
        row = {
            "anchor_mode": "frozen",
            "mtp_dd_exit_ticks": 0,
            "source_id": source_id,
            "step_dist": winning["step_dist"],
            "max_levels": winning["max_levels"],
            "max_total_position": winning["max_total_position"],
            "bars_processed": 0,  # not re-run, use profile data
            "avg_cycle_duration_bars": 0.0,
            "n_mtp_dd_exit_cycles": 0,
        }
        # Copy all metric columns from profile
        for col in ["cycle_pf", "n_cycles", "win_rate", "total_pnl_ticks",
                     "max_drawdown_ticks", "sharpe", "worst_cycle_dd",
                     "max_level_exposure_pct", "tail_ratio", "calmar_ratio",
                     "sortino_ratio", "winning_session_pct", "max_dd_duration_bars"]:
            row[col] = bt_config.get(col, 0.0)
        rows.append(row)

    return rows


def run_comparison(
    base_params: dict,
    bar_data_dict: dict,
    instrument_info: dict,
) -> pd.DataFrame:
    """Run all anchor mode comparison runs and return results DataFrame."""
    rows = []
    run_count = 0
    t_start = time.time()

    # Mode A: load from profile baselines (no re-run needed)
    print("\n--- Mode A (frozen): loading from profile baselines ---")
    mode_a_rows = load_mode_a_baselines()
    rows.extend(mode_a_rows)
    print(f"  Loaded {len(mode_a_rows)} baseline rows from MAX_PROFIT profile")

    # Mode B: walking anchor (3 runs)
    print("\n--- Mode B (walking): running 3 configs ---")
    for source_id, winning_cfg in WINNING_CONFIGS.items():
        if source_id not in bar_data_dict:
            print(f"  WARNING: no bar data for {source_id}")
            continue
        bars = bar_data_dict[source_id]
        result = run_single(
            source_id, winning_cfg, "walking", 0,
            bars, base_params, instrument_info,
        )
        rows.append(result)
        run_count += 1
        elapsed = time.time() - t_start
        print(f"  [{run_count}] {source_id}: cycle_pf={result['cycle_pf']:.4f}, "
              f"n_cycles={result['n_cycles']}, worst_dd={result['worst_cycle_dd']:.0f} ({elapsed:.0f}s)")

    # Mode C: frozen_stop with 3 thresholds × 3 configs (9 runs)
    print("\n--- Mode C (frozen_stop): running 9 configs (3 thresholds × 3 bar types) ---")
    for threshold in MODE_C_THRESHOLDS:
        for source_id, winning_cfg in WINNING_CONFIGS.items():
            if source_id not in bar_data_dict:
                continue
            bars = bar_data_dict[source_id]
            result = run_single(
                source_id, winning_cfg, "frozen_stop", threshold,
                bars, base_params, instrument_info,
            )
            rows.append(result)
            run_count += 1
            elapsed = time.time() - t_start
            print(f"  [{run_count}] {source_id} threshold={threshold}: "
                  f"cycle_pf={result['cycle_pf']:.4f}, n_cycles={result['n_cycles']}, "
                  f"worst_dd={result['worst_cycle_dd']:.0f}, "
                  f"mtp_dd_exits={result['n_mtp_dd_exit_cycles']} ({elapsed:.0f}s)")

    elapsed_total = time.time() - t_start
    print(f"\nAll runs complete: {run_count} new runs in {elapsed_total:.1f}s")

    df = pd.DataFrame(rows)
    # Ensure column order
    for col in COMPARISON_COLUMNS:
        if col not in df.columns:
            df[col] = None
    return df[COMPARISON_COLUMNS]


# ---------------------------------------------------------------------------
# Analysis and reporting
# ---------------------------------------------------------------------------

def generate_report(df: pd.DataFrame, output_dir: Path) -> str:
    """Generate comparison report from results DataFrame. Returns report text."""
    lines = [
        "# Anchor Mode Comparison Report",
        f"",
        f"**Configs tested:** MAX_PROFIT profile winning configs on P1a",
        f"**Modes:** A (frozen), B (walking), C (frozen_stop @ {MODE_C_THRESHOLDS})",
        f"**Total runs:** {len(df)}",
        "",
    ]

    # Summary table per bar type
    for source_id in WINNING_CONFIGS:
        sub = df[df["source_id"] == source_id].copy()
        if sub.empty:
            continue

        bar_label = source_id.replace("bar_data_", "").replace("_rot", "")
        wcfg = WINNING_CONFIGS[source_id]
        lines.append(f"## {bar_label} (SD={wcfg['step_dist']}, ML={wcfg['max_levels']}, MTP={wcfg['max_total_position']})")
        lines.append("")
        lines.append("| Mode | Threshold | Cycle PF | N Cycles | Win Rate | Total PnL | Worst DD | Avg Cycle Dur | MTP DD Exits |")
        lines.append("|------|-----------|----------|----------|----------|-----------|----------|---------------|-------------|")

        for _, row in sub.iterrows():
            mode = row["anchor_mode"]
            thr = int(row["mtp_dd_exit_ticks"]) if row["mtp_dd_exit_ticks"] != 0 else "—"
            mode_label = f"{mode}" if mode != "frozen_stop" else f"frozen_stop"
            lines.append(
                f"| {mode_label} | {thr} | "
                f"{row['cycle_pf']:.4f} | {int(row['n_cycles'])} | "
                f"{row['win_rate']:.4f} | {row['total_pnl_ticks']:.0f} | "
                f"{row['worst_cycle_dd']:.0f} | "
                f"{row.get('avg_cycle_duration_bars', 0):.0f} | "
                f"{int(row.get('n_mtp_dd_exit_cycles', 0))} |"
            )
        lines.append("")

    # Cross-mode comparison: best risk-adjusted per bar type
    lines.append("## Winner Selection")
    lines.append("")
    lines.append("Criteria: highest cycle_pf with lowest worst_cycle_dd (risk-adjusted).")
    lines.append("Composite score = cycle_pf / (worst_cycle_dd / 1000) — higher is better.")
    lines.append("")

    df_scored = df.copy()
    df_scored["composite"] = df_scored.apply(
        lambda r: r["cycle_pf"] / max(r["worst_cycle_dd"] / 1000.0, 0.001), axis=1
    )

    lines.append("| Bar Type | Best Mode | Threshold | Composite | Cycle PF | Worst DD | PnL |")
    lines.append("|----------|-----------|-----------|-----------|----------|----------|-----|")

    overall_winners = {}
    for source_id in WINNING_CONFIGS:
        sub = df_scored[df_scored["source_id"] == source_id]
        if sub.empty:
            continue
        best = sub.loc[sub["composite"].idxmax()]
        bar_label = source_id.replace("bar_data_", "").replace("_rot", "")
        thr = int(best["mtp_dd_exit_ticks"]) if best["mtp_dd_exit_ticks"] != 0 else "—"
        lines.append(
            f"| {bar_label} | {best['anchor_mode']} | {thr} | "
            f"{best['composite']:.4f} | {best['cycle_pf']:.4f} | "
            f"{best['worst_cycle_dd']:.0f} | {best['total_pnl_ticks']:.0f} |"
        )
        overall_winners[source_id] = {
            "anchor_mode": best["anchor_mode"],
            "mtp_dd_exit_ticks": float(best["mtp_dd_exit_ticks"]),
            "composite": float(best["composite"]),
        }

    # Overall recommendation
    lines.append("")
    lines.append("## Recommendation")
    lines.append("")

    # Count which mode wins most bar types
    mode_counts = {}
    for w in overall_winners.values():
        mode_counts[w["anchor_mode"]] = mode_counts.get(w["anchor_mode"], 0) + 1

    if mode_counts:
        dominant_mode = max(mode_counts, key=mode_counts.get)
        lines.append(f"**Dominant winner: `{dominant_mode}`** (wins {mode_counts[dominant_mode]}/3 bar types)")
        lines.append("")
        for source_id, w in overall_winners.items():
            bar_label = source_id.replace("bar_data_", "").replace("_rot", "")
            thr_str = f" @ {int(w['mtp_dd_exit_ticks'])} ticks" if w["mtp_dd_exit_ticks"] != 0 else ""
            lines.append(f"- {bar_label}: `{w['anchor_mode']}`{thr_str}")

    report = "\n".join(lines)

    # Write report
    report_path = output_dir / "anchor_mode_comparison_report.md"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report)
    print(f"\nReport written: {report_path}")

    # Write winners JSON
    winners_path = output_dir / "anchor_mode_winners.json"
    with open(winners_path, "w", encoding="utf-8") as f:
        json.dump(overall_winners, f, indent=2)
    print(f"Winners JSON written: {winners_path}")

    return report


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Anchor mode comparison: 3 modes × 3 winning configs on P1a"
    )
    parser.add_argument(
        "--output-dir",
        default=str(_ARCHETYPE_DIR / "anchor_comparison"),
        help="Directory to write results",
    )
    parser.add_argument(
        "--config",
        default=str(_CONFIG_PATH),
        help="Path to rotational_params.json",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print run plan without executing",
    )
    args = parser.parse_args()

    output_dir = Path(args.output_dir)

    if args.dry_run:
        print("=== Anchor Mode Comparison — Dry Run ===\n")
        print("Mode A (frozen): 3 runs (loaded from MAX_PROFIT profile baseline)")
        print("Mode B (walking): 3 runs")
        print(f"Mode C (frozen_stop): 9 runs (thresholds: {MODE_C_THRESHOLDS})")
        print(f"Total: 15 data points (12 new simulator runs)\n")
        for source_id, wcfg in WINNING_CONFIGS.items():
            print(f"  {source_id}: SD={wcfg['step_dist']}, ML={wcfg['max_levels']}, MTP={wcfg['max_total_position']}")
        return

    output_dir.mkdir(parents=True, exist_ok=True)

    # Load config
    with open(args.config, "r", encoding="utf-8") as f:
        config_template = json.load(f)
    config_template["period"] = "P1a"

    # Load instrument constants
    instrument_info = parse_instruments_md(
        config_template["instrument"],
        config_path=str(_INSTRUMENTS_MD),
    )
    print(
        f"Instrument: {config_template['instrument']} — "
        f"tick_size={instrument_info['tick_size']}, "
        f"cost_ticks={instrument_info['cost_ticks']}"
    )

    # Load bar data once
    print("\nLoading bar data...")
    bar_data_dict: dict = {}
    for source_id in WINNING_CONFIGS:
        path = config_template["bar_data_primary"].get(source_id, "")
        if path:
            bars = load_bars(str(_REPO_ROOT / path))
            bar_data_dict[source_id] = bars
            print(f"  {source_id}: {len(bars)} total bars loaded")
        else:
            print(f"  WARNING: no path for {source_id} in config")

    # Run comparison
    df = run_comparison(config_template, bar_data_dict, instrument_info)

    # Write TSV
    tsv_path = output_dir / "anchor_mode_comparison_P1a.tsv"
    df.to_csv(tsv_path, sep="\t", index=False)
    print(f"\nTSV written: {tsv_path} ({len(df)} rows)")

    # Generate report
    report = generate_report(df, output_dir)
    print("\n" + report)


if __name__ == "__main__":
    main()
