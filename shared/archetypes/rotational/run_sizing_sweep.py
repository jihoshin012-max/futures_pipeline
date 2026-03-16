# archetype: rotational
"""Sizing sweep harness for the rotational archetype.

Joint 3-parameter sweep: StepDist x MaxLevels x MaxTotalPosition across all
3 bar types on P1a data. MaxContractSize is fixed at 16 per user decision.

Applies deduplication:
    - MTP=1: adds never fire, ML is irrelevant. Collapse all ML values to ML=1.
    - MTP=2 with ML>=2: only one ADD can fire before MTP cap. Keep ML=2 as
      representative, drop ML=3,4,5.

Raw combos: 14 x 5 x 6 = 420 (but MTP=0 unlimited is included as 6th value)
After dedup: ~308 unique per bar type -> ~924 total rows.

Outputs:
    sizing_sweep_results/sizing_sweep_P1a.tsv
    sizing_sweep_results/sizing_sweep_P1a.json

Usage:
    python run_sizing_sweep.py [--output-dir sizing_sweep_results/] [--config rotational_params.json]
"""

from __future__ import annotations

import argparse
import copy
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Path setup: repo root is 3 levels up from this file
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_REPO_ROOT))

# Add archetype dir so rotational_simulator and rotational_engine are importable
_ARCHETYPE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_ARCHETYPE_DIR))

from shared.data_loader import load_bars, parse_instruments_md  # noqa: E402
from rotational_simulator import RotationalSimulator  # noqa: E402
from rotational_engine import compute_extended_metrics  # noqa: E402

# ---------------------------------------------------------------------------
# Sweep parameters (locked per plan spec)
# ---------------------------------------------------------------------------

STEP_VALUES = [1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0, 5.5, 6.0, 7.0, 8.0, 10.0]  # 14 values
MAX_LEVELS_VALUES = [1, 2, 3, 4, 5]
MAX_TP_VALUES = [1, 2, 4, 8, 16, 0]  # 0=unlimited

# MaxContractSize fixed at 16 per user decision
MAX_CONTRACT_SIZE = 16

_CONFIG_PATH = _ARCHETYPE_DIR / "rotational_params.json"
_INSTRUMENTS_MD = _REPO_ROOT / "_config/instruments.md"

# TSV column order (locked per plan spec)
TSV_COLUMNS = [
    "step_dist", "max_levels", "max_total_position", "source_id",
    "cycle_pf", "n_cycles", "win_rate", "total_pnl_ticks",
    "max_drawdown_ticks", "sharpe",
    "worst_cycle_dd", "max_level_exposure_pct", "tail_ratio",
    "calmar_ratio", "sortino_ratio", "winning_session_pct",
    "max_dd_duration_bars", "bars_processed",
]


# ---------------------------------------------------------------------------
# Deduplication
# ---------------------------------------------------------------------------

def deduplicate_combos(combos: list[tuple]) -> list[tuple]:
    """Deduplicate (step_dist, max_levels, max_total_position) combos.

    Rules:
        - MTP=1: ML irrelevant (adds never fire). Keep only ML=1 per StepDist.
        - MTP=2, ML>=2: only one ADD can fire. Keep ML=2 as representative,
          drop ML=3,4,5.
        - All other combos kept as-is.

    Returns:
        Deduplicated list of (step_dist, max_levels, max_total_position) tuples.
    """
    raw_count = len(combos)
    seen: set = set()
    unique: list[tuple] = []

    for (sd, ml, mtp) in combos:
        # Normalize
        if mtp == 1:
            # ML is irrelevant — use ML=1 as canonical
            canonical = (sd, 1, mtp)
        elif mtp == 2 and ml >= 2:
            # Only one ADD can fire — use ML=2 as canonical
            canonical = (sd, 2, mtp)
        else:
            canonical = (sd, ml, mtp)

        if canonical not in seen:
            seen.add(canonical)
            unique.append(canonical)

    print(f"Deduplicated {raw_count} -> {len(unique)} combinations per bar type")
    return unique


# ---------------------------------------------------------------------------
# Core sweep
# ---------------------------------------------------------------------------

def run_sizing_sweep(
    config_template: dict,
    bar_data_dict: dict[str, pd.DataFrame],
    instrument_info: dict,
    unique_combos: list[tuple],
) -> dict:
    """Execute the sizing sweep across all unique parameter combos and bar types.

    Args:
        config_template: Base config dict (deep-copied per iteration — not mutated).
        bar_data_dict: {source_id: DataFrame} — pre-loaded bar data.
        instrument_info: {tick_size, tick_value, cost_ticks}.
        unique_combos: List of (step_dist, max_levels, max_total_position) tuples.

    Returns:
        dict: {(sd, ml, mtp): {source_id: metrics_dict}}
    """
    cost_ticks = instrument_info["cost_ticks"]
    results: dict = {}

    total_runs = len(unique_combos) * len(bar_data_dict)
    run_count = 0
    t_start = time.time()

    for (sd, ml, mtp) in unique_combos:
        combo_key = (sd, ml, mtp)
        results[combo_key] = {}

        for source_id, bars in bar_data_dict.items():
            # Deep copy config and set sweep params
            cfg = copy.deepcopy(config_template)
            cfg["hypothesis"]["trigger_params"]["step_dist"] = sd
            cfg["martingale"]["max_levels"] = ml
            cfg["martingale"]["max_contract_size"] = MAX_CONTRACT_SIZE
            cfg["martingale"]["initial_qty"] = 1
            cfg["martingale"]["max_total_position"] = mtp
            cfg["_instrument"] = instrument_info
            # Per-source config so RTH filter activates correctly
            cfg["bar_data_primary"] = {source_id: config_template["bar_data_primary"].get(source_id, "")}

            # Run simulation
            simulator = RotationalSimulator(config=cfg, bar_data=bars, reference_data=None)
            sim_result = simulator.run()

            # Compute filtered bars using same filter logic as the simulator.
            # Needed for winning_session_pct (maps start_bar -> trading date).
            filtered_bars = _get_filtered_bars(cfg, bars)

            # Compute extended metrics
            metrics = compute_extended_metrics(
                sim_result.cycles,
                cost_ticks,
                bars_df=filtered_bars,
                max_levels=ml,
            )
            metrics["bars_processed"] = sim_result.bars_processed

            results[combo_key][source_id] = metrics

            run_count += 1
            if run_count % 50 == 0:
                elapsed = time.time() - t_start
                print(f"Progress: {run_count}/{total_runs} runs completed ({elapsed:.0f}s)")

    elapsed_total = time.time() - t_start
    print(f"\nSweep complete: {run_count} runs in {elapsed_total:.1f}s")
    return results


def _get_filtered_bars(cfg: dict, bars: pd.DataFrame) -> pd.DataFrame:
    """Apply the same date+RTH filter the simulator uses, without running simulation.

    This is needed to map start_bar indices (which are in filtered space) back
    to trading dates for winning_session_pct computation.
    """
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
# Output writers
# ---------------------------------------------------------------------------

def write_tsv(output_path: Path, results: dict, unique_combos: list[tuple], source_ids: list[str]) -> None:
    """Write sweep results as flat TSV (locked column order from plan spec)."""
    rows = []
    for (sd, ml, mtp) in unique_combos:
        combo_key = (sd, ml, mtp)
        source_results = results.get(combo_key, {})
        for source_id in source_ids:
            m = source_results.get(source_id, {})
            if not m:
                continue
            row = {
                "step_dist": sd,
                "max_levels": ml,
                "max_total_position": mtp,
                "source_id": source_id,
                "cycle_pf": m.get("cycle_pf", 0.0),
                "n_cycles": m.get("n_cycles", 0),
                "win_rate": m.get("win_rate", 0.0),
                "total_pnl_ticks": m.get("total_pnl_ticks", 0.0),
                "max_drawdown_ticks": m.get("max_drawdown_ticks", 0.0),
                "sharpe": m.get("sharpe", 0.0),
                "worst_cycle_dd": m.get("worst_cycle_dd", 0.0),
                "max_level_exposure_pct": m.get("max_level_exposure_pct", 0.0),
                "tail_ratio": m.get("tail_ratio", 0.0),
                "calmar_ratio": m.get("calmar_ratio", 0.0),
                "sortino_ratio": m.get("sortino_ratio", 0.0),
                "winning_session_pct": m.get("winning_session_pct", 0.0),
                "max_dd_duration_bars": m.get("max_dd_duration_bars", 0),
                "bars_processed": m.get("bars_processed", 0),
            }
            rows.append(row)

    df = pd.DataFrame(rows, columns=TSV_COLUMNS)
    df.to_csv(output_path, sep="\t", index=False)
    print(f"TSV written: {output_path} ({len(df)} rows)")


def write_json(
    output_path: Path,
    results: dict,
    unique_combos: list[tuple],
    source_ids: list[str],
) -> None:
    """Write sweep results as JSON with metadata."""
    # Convert tuple keys to string for JSON serialization
    serializable_results = {}
    for (sd, ml, mtp) in unique_combos:
        combo_key = (sd, ml, mtp)
        key_str = f"sd={sd}_ml={ml}_mtp={mtp}"
        serializable_results[key_str] = results.get(combo_key, {})

    output = {
        "sweep_params": {
            "step_values": STEP_VALUES,
            "max_levels_values": MAX_LEVELS_VALUES,
            "max_tp_values": MAX_TP_VALUES,
            "max_contract_size": MAX_CONTRACT_SIZE,
            "period": "P1a",
            "total_unique_combos": len(unique_combos),
            "total_runs": len(unique_combos) * len(source_ids),
        },
        "results": serializable_results,
    }
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2)
    print(f"JSON written: {output_path}")


# ---------------------------------------------------------------------------
# Summary printer
# ---------------------------------------------------------------------------

def print_sweep_summary(results: dict, unique_combos: list[tuple], source_ids: list[str]) -> None:
    """Print summary stats: best/worst configs, MTP=1 vs martingale, notable PFs."""
    print("\n=== Sizing Sweep Summary (P1a) ===")

    for source_id in source_ids:
        label = source_id.replace("bar_data_", "").replace("_rot", "")
        source_data = [
            ((sd, ml, mtp), results.get((sd, ml, mtp), {}).get(source_id, {}))
            for (sd, ml, mtp) in unique_combos
        ]
        source_data = [(k, v) for k, v in source_data if v]

        if not source_data:
            continue

        # Best and worst by cycle_pf
        sorted_by_pf = sorted(source_data, key=lambda x: x[1].get("cycle_pf", 0.0), reverse=True)
        best_combo, best_m = sorted_by_pf[0]
        worst_combo, worst_m = sorted_by_pf[-1]

        print(f"\n  [{label}]")
        print(
            f"    Best:  SD={best_combo[0]}, ML={best_combo[1]}, MTP={best_combo[2]} "
            f"-> PF={best_m.get('cycle_pf', 0.0)}, PnL={best_m.get('total_pnl_ticks', 0.0)}t"
        )
        print(
            f"    Worst: SD={worst_combo[0]}, ML={worst_combo[1]}, MTP={worst_combo[2]} "
            f"-> PF={worst_m.get('cycle_pf', 0.0)}, PnL={worst_m.get('total_pnl_ticks', 0.0)}t"
        )

        # MTP=1 pure reversal vs best martingale
        mtp1_data = [(k, v) for k, v in source_data if k[2] == 1]
        mtp_gt1_data = [(k, v) for k, v in source_data if k[2] != 1]
        if mtp1_data:
            best_mtp1 = max(mtp1_data, key=lambda x: x[1].get("cycle_pf", 0.0))
            print(
                f"    MTP=1 (pure reversal) best: PF={best_mtp1[1].get('cycle_pf', 0.0)} "
                f"(SD={best_mtp1[0][0]})"
            )
        if mtp_gt1_data:
            best_mart = max(mtp_gt1_data, key=lambda x: x[1].get("cycle_pf", 0.0))
            print(
                f"    Best martingale:             PF={best_mart[1].get('cycle_pf', 0.0)} "
                f"(SD={best_mart[0][0]}, ML={best_mart[0][1]}, MTP={best_mart[0][2]})"
            )

    # Flag notable configs (PF >= 1.0)
    notable = [
        (combo, source_id, m)
        for (sd, ml, mtp) in unique_combos
        for source_id, m in results.get((sd, ml, mtp), {}).items()
        for combo in [(sd, ml, mtp)]
        if m.get("cycle_pf", 0.0) >= 1.0
    ]
    if notable:
        print(f"\n  Notable configs (PF >= 1.0): {len(notable)}")
        for combo, src, m in notable[:10]:  # show top 10
            print(
                f"    SD={combo[0]}, ML={combo[1]}, MTP={combo[2]}, {src} -> "
                f"PF={m.get('cycle_pf', 0.0)}"
            )
    else:
        print("\n  No configs with PF >= 1.0")


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Rotational archetype — 3-parameter sizing sweep on P1a"
    )
    parser.add_argument(
        "--output-dir",
        default=str(_ARCHETYPE_DIR / "sizing_sweep_results"),
        help="Directory to write sizing_sweep_P1a.tsv and .json",
    )
    parser.add_argument(
        "--config",
        default=str(_CONFIG_PATH),
        help="Path to rotational_params.json",
    )
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # 1. Load config template
    with open(args.config, "r", encoding="utf-8") as f:
        config_template = json.load(f)

    # Ensure period is P1a for sweep
    config_template["period"] = "P1a"

    # 2. Load instrument constants
    instrument_info = parse_instruments_md(
        config_template["instrument"],
        config_path=str(_INSTRUMENTS_MD),
    )
    print(
        f"Instrument: {config_template['instrument']} — "
        f"tick_size={instrument_info['tick_size']}, "
        f"cost_ticks={instrument_info['cost_ticks']}"
    )

    # 3. Load all bar data ONCE per bar type
    print("\nLoading bar data...")
    bar_data_dict: dict[str, pd.DataFrame] = {}
    for source_id, path in config_template["bar_data_primary"].items():
        bars = load_bars(str(_REPO_ROOT / path))
        bar_data_dict[source_id] = bars
        print(f"  {source_id}: {len(bars)} total bars loaded")

    source_ids = list(bar_data_dict.keys())

    # 4. Build raw combos
    raw_combos = [
        (sd, ml, mtp)
        for sd in STEP_VALUES
        for ml in MAX_LEVELS_VALUES
        for mtp in MAX_TP_VALUES
    ]
    print(f"\nRaw combos: {len(raw_combos)} (before dedup)")

    # 5. Deduplicate
    unique_combos = deduplicate_combos(raw_combos)
    total_runs = len(unique_combos) * len(source_ids)
    print(
        f"Running sweep: {len(unique_combos)} unique combos x {len(source_ids)} bar types "
        f"= {total_runs} simulations"
    )

    # 6. Run sweep
    t0 = time.time()
    results = run_sizing_sweep(config_template, bar_data_dict, instrument_info, unique_combos)
    elapsed = time.time() - t0
    print(f"Total sweep time: {elapsed:.1f}s")

    # 7. Print summary
    print_sweep_summary(results, unique_combos, source_ids)

    # 8. Write outputs
    write_tsv(output_dir / "sizing_sweep_P1a.tsv", results, unique_combos, source_ids)
    write_json(output_dir / "sizing_sweep_P1a.json", results, unique_combos, source_ids)

    print("\nDone.")


if __name__ == "__main__":
    main()
