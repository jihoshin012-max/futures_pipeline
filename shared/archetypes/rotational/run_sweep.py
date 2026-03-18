# archetype: rotational
# WARNING: OHLC-era harness. Functional but superseded by tick-data harness
# (run_tick_sweep.py). Do not use for parameter selection — OHLC results are
# not trustworthy for absolute PF. See .planning/lessons.md for details.
"""Parameter sweep runner for the rotational archetype.

Sweeps StepDist values [1.0, 1.5, ..., 6.0] across all 3 bar types on P1a data.
Loads bar data ONCE per bar type, then reuses across all StepDist values.
Outputs sweep_P1a.json (machine-readable) and sweep_P1a.tsv (human-readable).

Usage:
    python run_sweep.py [--output-dir shared/archetypes/rotational/baseline_results/]
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
from rotational_engine import compute_cycle_metrics  # noqa: E402

# ---------------------------------------------------------------------------
# Sweep configuration
# ---------------------------------------------------------------------------

STEP_VALUES = [round(v * 0.5, 1) for v in range(2, 14)]  # 1.0 to 6.5 step 0.5 — but spec says 1.0-6.0
STEP_VALUES = [1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0, 5.5, 6.0]  # 11 values, spec-locked

_CONFIG_PATH = _ARCHETYPE_DIR / "rotational_params.json"
_INSTRUMENTS_MD = _REPO_ROOT / "_config/instruments.md"


# ---------------------------------------------------------------------------
# Core sweep function
# ---------------------------------------------------------------------------

def run_sweep(
    config_template: dict,
    bar_data_dict: dict[str, pd.DataFrame],
    instrument_info: dict,
    step_values: list[float],
) -> dict:
    """Run parameter sweep across StepDist values for all bar types.

    Args:
        config_template: Base config dict (deep-copied per iteration — not mutated).
        bar_data_dict: {source_id: DataFrame} — pre-loaded bar data.
        instrument_info: {tick_size, tick_value, cost_ticks}.
        step_values: List of StepDist values to test.

    Returns:
        dict: {str(step_dist): {source_id: metrics_dict}}
    """
    cost_ticks = instrument_info["cost_ticks"]
    results: dict[str, dict] = {}

    for step_dist in step_values:
        key = str(step_dist)
        results[key] = {}

        for source_id, bars in bar_data_dict.items():
            t0 = time.time()

            # Deep copy config and set step_dist
            cfg = copy.deepcopy(config_template)
            cfg["hypothesis"]["trigger_params"]["step_dist"] = step_dist
            cfg["_instrument"] = instrument_info

            # Run simulation
            simulator = RotationalSimulator(config=cfg, bar_data=bars, reference_data=None)
            sim_result = simulator.run()

            # Compute metrics
            metrics = compute_cycle_metrics(sim_result.cycles, cost_ticks)
            metrics["bars_processed"] = sim_result.bars_processed

            elapsed = time.time() - t0
            print(
                f"  StepDist={step_dist:.1f} on {source_id}: "
                f"{metrics['n_cycles']} cycles, "
                f"PF={metrics['cycle_pf']}, "
                f"PnL={metrics['total_pnl_ticks']}t "
                f"({elapsed:.1f}s)"
            )

            results[key][source_id] = metrics

    return results


# ---------------------------------------------------------------------------
# Best-per-source selection
# ---------------------------------------------------------------------------

def select_best_per_source(
    results: dict[str, dict],
    step_values: list[float],
) -> dict:
    """For each bar type, select StepDist with highest cycle_pf.

    Tiebreaker on cycle_pf=inf: use highest total_pnl_ticks.

    Args:
        results: {str(step_dist): {source_id: metrics_dict}}
        step_values: Ordered list of step values tested.

    Returns:
        {source_id: {step_dist, cycle_pf, total_pnl_ticks, n_cycles, win_rate, sharpe}}
    """
    # Collect source_ids from the first step
    first_key = str(step_values[0])
    source_ids = list(results[first_key].keys())

    best: dict = {}
    for source_id in source_ids:
        best_step = None
        best_pf = -1.0
        best_pnl = -float("inf")
        best_metrics: dict = {}

        for step_dist in step_values:
            key = str(step_dist)
            m = results[key].get(source_id, {})
            pf = m.get("cycle_pf", 0.0)
            pnl = m.get("total_pnl_ticks", 0.0)

            # Compare: inf > any finite; among infs use pnl; among equal finite use pnl
            if pf == float("inf"):
                # inf beats any finite
                if best_pf != float("inf") or pnl > best_pnl:
                    best_step = step_dist
                    best_pf = pf
                    best_pnl = pnl
                    best_metrics = m
            elif best_pf != float("inf"):
                if pf > best_pf or (abs(pf - best_pf) < 1e-9 and pnl > best_pnl):
                    best_step = step_dist
                    best_pf = pf
                    best_pnl = pnl
                    best_metrics = m

        best[source_id] = {
            "step_dist": best_step,
            "cycle_pf": best_metrics.get("cycle_pf", 0.0),
            "total_pnl_ticks": best_metrics.get("total_pnl_ticks", 0.0),
            "n_cycles": best_metrics.get("n_cycles", 0),
            "win_rate": best_metrics.get("win_rate", 0.0),
            "sharpe": best_metrics.get("sharpe", 0.0),
            "max_drawdown_ticks": best_metrics.get("max_drawdown_ticks", 0.0),
        }

    return best


# ---------------------------------------------------------------------------
# Output writers
# ---------------------------------------------------------------------------

def write_json(output_path: Path, results: dict, best_per_source: dict, step_values: list[float]) -> None:
    """Write sweep results as JSON."""
    output = {
        "sweep_params": {
            "step_values": step_values,
            "period": "P1a",
        },
        "results": results,
        "best_per_source": best_per_source,
    }
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2)
    print(f"\nJSON written: {output_path}")


def write_tsv(output_path: Path, results: dict, step_values: list[float]) -> None:
    """Write sweep results as TSV flat table (33 rows + header)."""
    rows = []
    for step_dist in step_values:
        key = str(step_dist)
        source_results = results.get(key, {})
        for source_id, m in source_results.items():
            rows.append({
                "step_dist": step_dist,
                "source_id": source_id,
                "n_cycles": m.get("n_cycles", 0),
                "cycle_pf": m.get("cycle_pf", 0.0),
                "win_rate": m.get("win_rate", 0.0),
                "total_pnl_ticks": m.get("total_pnl_ticks", 0.0),
                "sharpe": m.get("sharpe", 0.0),
                "max_drawdown_ticks": m.get("max_drawdown_ticks", 0.0),
                "bars_processed": m.get("bars_processed", 0),
            })

    df = pd.DataFrame(rows)
    df.to_csv(output_path, sep="\t", index=False)
    print(f"TSV written: {output_path}")


# ---------------------------------------------------------------------------
# Summary printer
# ---------------------------------------------------------------------------

def print_summary(best_per_source: dict) -> None:
    """Print optimized baselines table."""
    print("\n=== Optimized Baselines (P1a) ===")
    for source_id, info in best_per_source.items():
        label = source_id.replace("bar_data_", "").replace("_rot", "")
        print(
            f"  {source_id:<28}: best StepDist={info['step_dist']:.1f}, "
            f"PF={info['cycle_pf']}, "
            f"PnL={info['total_pnl_ticks']}t, "
            f"N={info['n_cycles']} cycles"
        )


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Rotational archetype — fixed-step parameter sweep on P1a"
    )
    parser.add_argument(
        "--output-dir",
        default=str(_ARCHETYPE_DIR / "baseline_results"),
        help="Directory to write sweep_P1a.json and sweep_P1a.tsv",
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
    print(f"Instrument: {config_template['instrument']} — tick_size={instrument_info['tick_size']}, "
          f"cost_ticks={instrument_info['cost_ticks']}")

    # 3. Load all bar data ONCE per bar type
    print("\nLoading bar data...")
    bar_data_dict: dict[str, pd.DataFrame] = {}
    for source_id, path in config_template["bar_data_primary"].items():
        bars = load_bars(str(_REPO_ROOT / path))
        bar_data_dict[source_id] = bars
        print(f"  {source_id}: {len(bars)} total bars loaded")

    # 4. Run sweep: 11 StepDist x 3 bar types = 33 simulations
    print(f"\nRunning sweep: {len(STEP_VALUES)} StepDist values x {len(bar_data_dict)} bar types "
          f"= {len(STEP_VALUES) * len(bar_data_dict)} simulations")
    print(f"StepDist values: {STEP_VALUES}\n")

    t_sweep_start = time.time()
    results = run_sweep(config_template, bar_data_dict, instrument_info, STEP_VALUES)
    t_sweep_elapsed = time.time() - t_sweep_start

    print(f"\nSweep complete in {t_sweep_elapsed:.1f}s")

    # 5. Select best per source
    best_per_source = select_best_per_source(results, STEP_VALUES)

    # 6. Print summary
    print_summary(best_per_source)

    # 7. Write outputs
    write_json(output_dir / "sweep_P1a.json", results, best_per_source, STEP_VALUES)
    write_tsv(output_dir / "sweep_P1a.tsv", results, STEP_VALUES)

    print("\nDone.")


if __name__ == "__main__":
    main()
