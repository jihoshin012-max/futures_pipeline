# archetype: rotational
# WARNING: OHLC-era harness. Functional but superseded by tick-data harness
# (run_tick_sweep.py). Do not use for parameter selection — OHLC results are
# not trustworthy for absolute PF. See .planning/lessons.md for details.
"""Per-hypothesis parameter sweep harness for Phase 4 combination testing.

Runs each hypothesis over its full param_grid with profile-specific martingale
params to discover which hypotheses genuinely improve on the tuned baselines from
Phase 02.1. Produces dimensional_winners.json as input to Plan 02 combination testing.

Hypotheses excluded:
  - H19: requires_reference=True (deferred to Plan 02 multi-source testing)
  - H37: exclude_10sec=True (constant bar_formation_rate on 10sec series)

delta_pf is computed against no_tds_baselines from best_tds_configs.json
(NOT the Phase 01 sweep_P1a.json baselines).

Outputs:
    combination_results/phase4_param_sweep.tsv  — all ~1800 rows
    combination_results/phase4_param_sweep.json — same data as JSON
    combination_results/dimensional_winners.json — hypotheses beating baseline on >= 2 bar types

Usage:
    python run_combination_sweep.py --plan 1
    python run_combination_sweep.py --plan 1 --dry-run
    python run_combination_sweep.py --plan 1 --limit 20
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

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------

_ARCHETYPE_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _ARCHETYPE_DIR.parents[2]  # rotational -> archetypes -> shared -> pipeline
sys.path.insert(0, str(_REPO_ROOT))
sys.path.insert(0, str(_ARCHETYPE_DIR))

from shared.data_loader import load_bars, parse_instruments_md  # noqa: E402
from rotational_simulator import RotationalSimulator  # noqa: E402
from rotational_engine import compute_extended_metrics  # noqa: E402
from hypothesis_configs import (  # noqa: E402
    HYPOTHESIS_REGISTRY,
    _ALL_SOURCES,
    build_experiment_config,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_CONFIG_PATH = _ARCHETYPE_DIR / "rotational_params.json"
_INSTRUMENTS_MD = _REPO_ROOT / "_config/instruments.md"
_BEST_TDS_CONFIGS_PATH = _ARCHETYPE_DIR / "tds_profiles" / "best_tds_configs.json"
_PROFILES_DIR = _ARCHETYPE_DIR / "profiles"
_OUTPUT_DIR = _ARCHETYPE_DIR / "combination_results"

_PROFILE_NAMES = ["MAX_PROFIT", "SAFEST", "MOST_CONSISTENT"]

# TSV column order for phase4_param_sweep.tsv
_TSV_COLUMNS = [
    "hypothesis_id",
    "hypothesis_name",
    "dimension",
    "profile",
    "source_id",
    "params_str",
    "cycle_pf",
    "delta_pf",
    "beats_baseline",
    "n_cycles",
    "win_rate",
    "total_pnl_ticks",
    "worst_cycle_dd",
    "max_drawdown_ticks",
    "sharpe",
    "max_level_exposure_pct",
    "tail_ratio",
    "calmar_ratio",
    "classification",
    "run_sec",
]


# ---------------------------------------------------------------------------
# Profile injection
# ---------------------------------------------------------------------------


def inject_profile_martingale(config: dict, profile_bar_type_data: dict) -> dict:
    """Deep-copy config and inject profile martingale params for a given bar type.

    Sets:
        hypothesis.trigger_params.step_dist  (from profile bar_type step_dist)
        martingale.max_levels               (from profile bar_type max_levels)
        martingale.max_total_position       (from profile bar_type max_total_position)
        martingale.max_contract_size = 16   (fixed across all profiles per plan spec)

    Args:
        config: Base config dict (will NOT be mutated).
        profile_bar_type_data: Profile data for a specific bar type (e.g. profiles["bar_types"]["bar_data_250vol_rot"]).

    Returns:
        New deep-copied config with profile params injected.
    """
    cfg = copy.deepcopy(config)

    # Ensure nested dicts exist
    if "hypothesis" not in cfg:
        cfg["hypothesis"] = {}
    if "trigger_params" not in cfg["hypothesis"]:
        cfg["hypothesis"]["trigger_params"] = {}
    if "martingale" not in cfg:
        cfg["martingale"] = {}

    # Inject step_dist from profile
    cfg["hypothesis"]["trigger_params"]["step_dist"] = profile_bar_type_data["step_dist"]

    # Inject martingale params
    cfg["martingale"]["max_levels"] = profile_bar_type_data["max_levels"]
    cfg["martingale"]["max_total_position"] = profile_bar_type_data["max_total_position"]
    cfg["martingale"]["max_contract_size"] = 16  # fixed per plan spec

    return cfg


# ---------------------------------------------------------------------------
# Baseline loading
# ---------------------------------------------------------------------------


def load_param_sweep_baselines() -> dict:
    """Load no_tds_baselines from best_tds_configs.json.

    Returns:
        dict keyed by profile_name -> source_id -> metrics dict.
        e.g. baselines["MAX_PROFIT"]["bar_data_250vol_rot"]["cycle_pf"] = 2.2037

    Raises:
        FileNotFoundError: If best_tds_configs.json is not found.
        KeyError: If no_tds_baselines key is missing.
    """
    with open(str(_BEST_TDS_CONFIGS_PATH), "r", encoding="utf-8") as f:
        data = json.load(f)

    if "no_tds_baselines" not in data:
        raise KeyError(
            f"best_tds_configs.json missing 'no_tds_baselines' key. "
            f"Found keys: {list(data.keys())}"
        )

    return data["no_tds_baselines"]


# ---------------------------------------------------------------------------
# Profile loading
# ---------------------------------------------------------------------------


def load_all_profiles() -> dict:
    """Load all 3 profile JSON files.

    Returns:
        dict keyed by profile_name -> full profile dict.
        e.g. profiles["MAX_PROFIT"]["bar_types"]["bar_data_250vol_rot"] = {...}

    Raises:
        FileNotFoundError: If any profile JSON is not found.
    """
    name_to_file = {
        "MAX_PROFIT": "max_profit.json",
        "SAFEST": "safest.json",
        "MOST_CONSISTENT": "most_consistent.json",
    }

    profiles = {}
    for profile_name, filename in name_to_file.items():
        path = _PROFILES_DIR / filename
        with open(str(path), "r", encoding="utf-8") as f:
            profiles[profile_name] = json.load(f)

    return profiles


# ---------------------------------------------------------------------------
# Base config
# ---------------------------------------------------------------------------


def _get_base_config() -> dict:
    """Load rotational_params.json with P1a period."""
    with open(str(_CONFIG_PATH), "r", encoding="utf-8") as f:
        cfg = json.load(f)
    cfg["period"] = "P1a"
    return cfg


def _prepare_source_config(base_config: dict, source_id: str, instrument_info: dict) -> dict:
    """Build a source-specific config dict.

    Sets bar_data_primary to the single source and injects _instrument dict.
    """
    cfg = copy.deepcopy(base_config)
    original_paths = base_config.get("bar_data_primary", {})
    if source_id in original_paths:
        cfg["bar_data_primary"] = {source_id: original_paths[source_id]}
    else:
        cfg["bar_data_primary"] = {source_id: f"UNKNOWN_PATH/{source_id}.csv"}
    cfg["_instrument"] = instrument_info
    return cfg


# ---------------------------------------------------------------------------
# RTH filter (reuse from run_hypothesis_screening)
# ---------------------------------------------------------------------------


def _apply_rth_filter(bar_df: pd.DataFrame) -> pd.DataFrame:
    """Apply RTH filter (09:30-16:00 ET) to bar data."""
    import datetime

    rth_start = datetime.time(9, 30, 0)
    rth_end = datetime.time(16, 0, 0)

    if "datetime" in bar_df.columns:
        times = bar_df["datetime"].dt.time
        mask = (times >= rth_start) & (times < rth_end)
        return bar_df[mask].reset_index(drop=True)
    elif "Time" in bar_df.columns:
        def _parse_time(t_str: str) -> datetime.time:
            parts = str(t_str).strip().split(":")
            h = int(parts[0])
            m = int(parts[1])
            s = int(float(parts[2])) if len(parts) > 2 else 0
            return datetime.time(h, m, s)
        times = bar_df["Time"].apply(_parse_time)
        mask = (times >= rth_start) & (times < rth_end)
        return bar_df[mask].reset_index(drop=True)

    return bar_df


def _get_filtered_bars(bar_df: pd.DataFrame, source_id: str) -> pd.DataFrame:
    """Return bars filtered for winning_session_pct computation.

    10sec bars: apply RTH filter (simulator handles internally, but we need the
    same filtered set for metrics).
    vol/tick bars: return as-is (they are already RTH-filtered at construction).
    """
    if "10sec" in source_id:
        return _apply_rth_filter(bar_df)
    return bar_df


# ---------------------------------------------------------------------------
# Main sweep loop
# ---------------------------------------------------------------------------


def _build_all_experiments() -> list[dict]:
    """Build a flat list of all experiments to run (excluding H19, H37-on-10sec).

    Each entry: {hypothesis_id, params, profile_name, source_id, params_str}
    Used for indexing with --start-idx / --limit.
    """
    experiments = []
    for h_id, hypothesis in HYPOTHESIS_REGISTRY.items():
        if hypothesis.get("requires_reference", False):
            continue
        param_grid = hypothesis.get("param_grid", [])
        param_values = param_grid if param_grid else [{}]
        for params in param_values:
            for profile_name in _PROFILE_NAMES:
                for source_id in _ALL_SOURCES:
                    if hypothesis.get("exclude_10sec", False) and "10sec" in source_id:
                        continue
                    experiments.append({
                        "hypothesis_id": h_id,
                        "hypothesis": hypothesis,
                        "params": params,
                        "profile_name": profile_name,
                        "source_id": source_id,
                        "params_str": json.dumps(params, sort_keys=True),
                    })
    return experiments


def run_param_sweep(
    profiles: dict,
    baselines: dict,
    dry_run: bool = False,
    limit: int = 0,
    start_idx: int = 0,
    incremental_output: str | None = None,
) -> list[dict]:
    """Run the full per-hypothesis parameter sweep on P1a data.

    For each hypothesis (minus H19), for each param in param_grid, for each
    profile, for each source_id (skipping H37 on 10sec), runs the simulator
    with profile-injected martingale params and records results.

    Args:
        profiles: Dict from load_all_profiles() — keyed by profile_name -> profile dict.
        baselines: Dict from load_param_sweep_baselines() — keyed by profile_name -> source_id -> metrics.
        dry_run: If True, print config summary without running simulation.
        limit: If > 0, stop after this many experiments from start_idx.
        start_idx: Start at this experiment index (for batching / resume).
        incremental_output: If set, append each row to this TSV path as completed.

    Returns:
        List of result dicts with all _TSV_COLUMNS fields.
    """
    # Load instrument info from registry (never hardcode)
    instrument_info = parse_instruments_md("NQ", str(_INSTRUMENTS_MD))
    cost_ticks = instrument_info["cost_ticks"]
    print(f"  Instrument: tick_size={instrument_info['tick_size']}, cost_ticks={cost_ticks}", flush=True)

    # Load base config
    base_config = _get_base_config()

    # Build full experiment list
    all_experiments = _build_all_experiments()
    total_experiments = len(all_experiments)
    print(f"  Total experiments planned: {total_experiments}", flush=True)

    if dry_run:
        end_idx = min(start_idx + limit, total_experiments) if limit > 0 else total_experiments
        for i, exp in enumerate(all_experiments[start_idx:end_idx], start=start_idx):
            print(
                f"  DRY RUN [{i+1}/{total_experiments}] {exp['hypothesis_id']} | "
                f"{exp['profile_name']} | {exp['source_id']} | params={exp['params_str']}"
            )
        return []

    # Load bar data once per source_id
    print("  Loading bar data...", flush=True)
    bar_data_dict: dict[str, pd.DataFrame] = {}
    for source_id, path in base_config.get("bar_data_primary", {}).items():
        full_path = _REPO_ROOT / path
        t0 = time.time()
        bar_data_dict[source_id] = load_bars(str(full_path))
        print(f"    {source_id}: {len(bar_data_dict[source_id])} bars ({time.time() - t0:.1f}s)", flush=True)

    # Setup incremental output
    incremental_file = None
    if incremental_output:
        out_path = Path(incremental_output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        write_header = not out_path.exists() or start_idx == 0
        incremental_file = open(str(out_path), "a", encoding="utf-8", newline="")
        if write_header:
            incremental_file.write("\t".join(_TSV_COLUMNS) + "\n")
            incremental_file.flush()

    results = []
    n_run = 0
    end_idx = total_experiments

    # Slice experiments for this batch
    exp_slice = all_experiments[start_idx:]
    if limit > 0:
        exp_slice = exp_slice[:limit]

    for global_idx, exp in enumerate(exp_slice, start=start_idx):
        h_id = exp["hypothesis_id"]
        hypothesis = exp["hypothesis"]
        params = exp["params"]
        profile_name = exp["profile_name"]
        source_id = exp["source_id"]
        params_str = exp["params_str"]

        profile = profiles[profile_name]
        profile_bar_types = profile.get("bar_types", {})

        if source_id not in profile_bar_types:
            continue

        profile_bt_data = profile_bar_types[source_id]

        # Build experiment config
        source_cfg = _prepare_source_config(base_config, source_id, instrument_info)
        exp_config = build_experiment_config(source_cfg, hypothesis, params if params else None)
        exp_config = inject_profile_martingale(exp_config, profile_bt_data)

        # Get bar data
        bars = bar_data_dict.get(source_id)
        if bars is None:
            row = _make_error_row(h_id, hypothesis, profile_name, source_id, params_str, "BAR_DATA_NOT_LOADED", 0.0)
            results.append(row)
            _write_incremental_row(incremental_file, row)
            continue

        # Get max_levels from injected config
        max_levels = exp_config.get("martingale", {}).get("max_levels", 1)

        # Run simulator
        t0 = time.time()
        try:
            simulator = RotationalSimulator(
                config=exp_config,
                bar_data=bars,
                reference_data=None,
            )
            sim_result = simulator.run()
        except Exception as e:
            run_sec = time.time() - t0
            row = _make_error_row(
                h_id, hypothesis, profile_name, source_id, params_str,
                f"ERROR: {type(e).__name__}: {e}", run_sec
            )
            results.append(row)
            _write_incremental_row(incremental_file, row)
            n_run += 1
            continue
        run_sec = time.time() - t0

        # Compute extended metrics
        filtered_bars = _get_filtered_bars(bars, source_id)
        metrics = compute_extended_metrics(
            sim_result.cycles,
            cost_ticks,
            filtered_bars,
            max_levels,
        )

        # Compute delta_pf vs profile baseline (NOT Phase 01 baselines)
        baseline_pf = baselines.get(profile_name, {}).get(source_id, {}).get("cycle_pf", 0.0)
        cycle_pf = metrics.get("cycle_pf", 0.0)
        delta_pf = round(cycle_pf - baseline_pf, 4) if cycle_pf is not None else None
        beats_baseline = bool(cycle_pf > baseline_pf) if cycle_pf is not None else False

        row = {
            "hypothesis_id": h_id,
            "hypothesis_name": hypothesis["name"],
            "dimension": hypothesis["dimension"],
            "profile": profile_name,
            "source_id": source_id,
            "params_str": params_str,
            "cycle_pf": metrics.get("cycle_pf"),
            "delta_pf": delta_pf,
            "beats_baseline": beats_baseline,
            "n_cycles": metrics.get("n_cycles", 0),
            "win_rate": metrics.get("win_rate"),
            "total_pnl_ticks": metrics.get("total_pnl_ticks"),
            "worst_cycle_dd": metrics.get("worst_cycle_dd"),
            "max_drawdown_ticks": metrics.get("max_drawdown_ticks"),
            "sharpe": metrics.get("sharpe"),
            "max_level_exposure_pct": metrics.get("max_level_exposure_pct"),
            "tail_ratio": metrics.get("tail_ratio"),
            "calmar_ratio": metrics.get("calmar_ratio"),
            "classification": "OK",
            "run_sec": round(run_sec, 4),
        }
        results.append(row)
        _write_incremental_row(incremental_file, row)
        n_run += 1

        if n_run % 10 == 0:
            print(
                f"  [{global_idx + 1}/{total_experiments}] {h_id} | {profile_name} | {source_id} "
                f"| delta_pf={delta_pf:+.4f} | {run_sec:.1f}s"
                if delta_pf is not None
                else f"  [{global_idx + 1}/{total_experiments}] {h_id} | {profile_name} | {source_id} | {run_sec:.1f}s",
                flush=True
            )

    if incremental_file:
        incremental_file.close()

    return results


def _write_incremental_row(file_handle, row: dict) -> None:
    """Write a single result row to an open incremental TSV file handle."""
    if file_handle is None:
        return
    values = []
    for col in _TSV_COLUMNS:
        val = row.get(col)
        if col == "beats_baseline":
            values.append("" if val is None else str(bool(val)))
        elif val is None:
            values.append("")
        else:
            values.append(str(val))
    file_handle.write("\t".join(values) + "\n")
    file_handle.flush()


def _make_error_row(
    h_id: str,
    hypothesis: dict,
    profile_name: str,
    source_id: str,
    params_str: str,
    classification: str,
    run_sec: float,
) -> dict:
    """Return an error/skip row with all required columns."""
    return {
        "hypothesis_id": h_id,
        "hypothesis_name": hypothesis.get("name", h_id),
        "dimension": hypothesis.get("dimension", "?"),
        "profile": profile_name,
        "source_id": source_id,
        "params_str": params_str,
        "cycle_pf": None,
        "delta_pf": None,
        "beats_baseline": None,
        "n_cycles": None,
        "win_rate": None,
        "total_pnl_ticks": None,
        "worst_cycle_dd": None,
        "max_drawdown_ticks": None,
        "sharpe": None,
        "max_level_exposure_pct": None,
        "tail_ratio": None,
        "calmar_ratio": None,
        "classification": classification,
        "run_sec": run_sec,
    }


# ---------------------------------------------------------------------------
# Dimensional winner selection
# ---------------------------------------------------------------------------


def select_dimensional_winners(
    results_df: pd.DataFrame,
    min_bar_types: int = 2,
) -> dict:
    """Select dimensional winners from sweep results.

    For each hypothesis, a winner requires:
    - beats_baseline=True on >= min_bar_types bar types for a given profile
    - Best params selected by highest delta_pf among beats_baseline=True rows

    Args:
        results_df: DataFrame with columns from _TSV_COLUMNS.
        min_bar_types: Minimum number of bar types that must beat baseline (default 2).

    Returns:
        Nested dict: {hypothesis_id: {profile_name: {source_id: {best_params, delta_pf, cycle_pf}}}}
        Only includes hypotheses/profiles that meet the min_bar_types requirement.
    """
    winners: dict = {}

    # Filter to OK rows only (skip errors, skips)
    ok_df = results_df.copy()
    if "classification" in ok_df.columns:
        ok_df = ok_df[ok_df["classification"] == "OK"]

    # Convert beats_baseline to bool (handle string 'True'/'False' from TSV)
    if ok_df.empty:
        return winners

    if ok_df["beats_baseline"].dtype == object:
        ok_df = ok_df.copy()
        ok_df["beats_baseline"] = ok_df["beats_baseline"].map(
            lambda x: x if isinstance(x, bool) else str(x).strip().lower() == "true"
        )

    for h_id in ok_df["hypothesis_id"].unique():
        h_df = ok_df[ok_df["hypothesis_id"] == h_id]

        for profile_name in h_df["profile"].unique() if "profile" in h_df.columns else ["MAX_PROFIT"]:
            p_df = h_df[h_df["profile"] == profile_name] if "profile" in h_df.columns else h_df

            # Find bar types where this hypothesis beats baseline at any param value
            beating_df = p_df[p_df["beats_baseline"] == True]  # noqa: E712
            if beating_df.empty:
                continue

            beating_sources = beating_df["source_id"].unique()
            n_beating = len(beating_sources)

            if n_beating < min_bar_types:
                continue

            # Hypothesis qualifies — find best params per source_id
            if h_id not in winners:
                winners[h_id] = {}
            if profile_name not in winners[h_id]:
                winners[h_id][profile_name] = {}

            for source_id in p_df["source_id"].unique():
                src_beating = p_df[
                    (p_df["source_id"] == source_id) & (p_df["beats_baseline"] == True)  # noqa: E712
                ]
                if src_beating.empty:
                    # No winning params for this source, but hypothesis still qualifies overall
                    continue

                # Best params = highest delta_pf
                best_row = src_beating.loc[src_beating["delta_pf"].idxmax()]
                winners[h_id][profile_name][source_id] = {
                    "params_str": str(best_row.get("params_str", "{}")),
                    "delta_pf": float(best_row["delta_pf"]),
                    "cycle_pf": float(best_row["cycle_pf"]),
                    "n_cycles": int(best_row.get("n_cycles", 0)) if pd.notna(best_row.get("n_cycles")) else 0,
                }

    return winners


# ---------------------------------------------------------------------------
# Output writers
# ---------------------------------------------------------------------------


def write_param_sweep_results(results: list[dict], output_dir: str) -> None:
    """Write phase4_param_sweep.tsv and phase4_param_sweep.json to output_dir.

    Args:
        results: List of result dicts from run_param_sweep().
        output_dir: Directory path to write outputs.
    """
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    # Build rows with fixed column order
    rows = []
    for r in results:
        row = {}
        for col in _TSV_COLUMNS:
            val = r.get(col)
            if col == "beats_baseline":
                if val is None:
                    row[col] = ""
                else:
                    row[col] = str(bool(val))
            elif val is None:
                row[col] = ""
            else:
                row[col] = val
        rows.append(row)

    df = pd.DataFrame(rows, columns=_TSV_COLUMNS)
    tsv_path = out / "phase4_param_sweep.tsv"
    df.to_csv(str(tsv_path), sep="\t", index=False)
    print(f"Written: {tsv_path} ({len(df)} rows)")

    # Also write JSON
    json_path = out / "phase4_param_sweep.json"
    with open(str(json_path), "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"Written: {json_path}")


def write_dimensional_winners(winners: dict, output_dir: str) -> None:
    """Write dimensional_winners.json to output_dir.

    Args:
        winners: Dict from select_dimensional_winners().
        output_dir: Directory path to write output.
    """
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    json_path = out / "dimensional_winners.json"
    with open(str(json_path), "w", encoding="utf-8") as f:
        json.dump(winners, f, indent=2)
    print(f"Written: {json_path} ({len(winners)} qualifying hypotheses)")


# ---------------------------------------------------------------------------
# Summary reporting
# ---------------------------------------------------------------------------


def print_sweep_summary(results: list[dict], winners: dict) -> None:
    """Print a summary of sweep results to stdout."""
    print("\n=== Phase 4 Parameter Sweep Summary ===")
    ok_results = [r for r in results if r.get("classification") == "OK"]
    print(f"Total runs: {len(results)}")
    print(f"OK runs: {len(ok_results)}")
    print(f"Error/skip runs: {len(results) - len(ok_results)}")

    h_tested = len({r["hypothesis_id"] for r in ok_results})
    h_beating = len(winners)
    print(f"Hypotheses tested: {h_tested}")
    print(f"Dimensional winners (>= 2 bar types beat baseline): {h_beating}")

    if not winners:
        print("\nNOTE: Zero hypotheses beat profile baselines at any param value on >= 2 bar types.")
        print("This means combination testing in Plan 02 has no material to combine.")
        print("The tuned profile baselines are already optimal for these hypotheses.")
        return

    # Per-dimension breakdown
    from hypothesis_configs import HYPOTHESIS_REGISTRY
    dim_winners: dict[str, list[str]] = {}
    for h_id in winners:
        if h_id in HYPOTHESIS_REGISTRY:
            dim = HYPOTHESIS_REGISTRY[h_id]["dimension"]
            dim_winners.setdefault(dim, []).append(h_id)

    print("\nWinners by dimension:")
    for dim in sorted(dim_winners.keys()):
        print(f"  Dim {dim}: {dim_winners[dim]}")

    # Best delta_pf per dimension
    if ok_results:
        ok_df = pd.DataFrame(ok_results)
        beating = ok_df[ok_df["beats_baseline"] == True]  # noqa: E712
        if not beating.empty and "delta_pf" in beating.columns:
            print("\nBest delta_pf across all runs:")
            top10 = beating.nlargest(10, "delta_pf")[
                ["hypothesis_id", "profile", "source_id", "params_str", "delta_pf", "cycle_pf"]
            ]
            for _, row in top10.iterrows():
                print(
                    f"  {row['hypothesis_id']} | {row['profile']} | {row['source_id']} | "
                    f"delta_pf={row['delta_pf']:+.4f} | pf={row['cycle_pf']:.4f}"
                )


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Phase 4 per-hypothesis parameter sweep harness"
    )
    parser.add_argument(
        "--plan",
        type=int,
        default=1,
        help="Plan number (currently only 1 is supported — param sweep)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print configs without running simulations",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Cap experiments at N (0 = no limit)",
    )
    parser.add_argument(
        "--start-idx",
        type=int,
        default=0,
        help="Start at this experiment index (for batching)",
    )
    parser.add_argument(
        "--output-dir",
        default=str(_OUTPUT_DIR),
        help="Output directory for results",
    )
    args = parser.parse_args()

    if args.plan != 1:
        print(f"ERROR: Only --plan 1 (param sweep) is implemented. Got --plan {args.plan}")
        sys.exit(1)

    print("\n=== Phase 4 Plan 01: Per-Hypothesis Parameter Sweep ===")
    print(f"Output dir: {args.output_dir}")
    if args.dry_run:
        print("Mode: DRY RUN (no simulations)")
    if args.limit > 0:
        print(f"Limit: {args.limit} experiments")

    # Load profiles and baselines
    print("\n[1/4] Loading profiles...")
    profiles = load_all_profiles()
    for pname, pdata in profiles.items():
        bt = pdata.get("bar_types", {})
        print(f"  {pname}: {list(bt.keys())}")

    print("\n[2/4] Loading baselines (no_tds_baselines from best_tds_configs.json)...")
    baselines = load_param_sweep_baselines()
    for profile_name, sources in baselines.items():
        for src, metrics in sources.items():
            print(f"  {profile_name}/{src}: cycle_pf={metrics['cycle_pf']}")

    # Incremental output path for batched runs
    incremental_tsv = str(Path(args.output_dir) / "phase4_param_sweep.tsv")

    print("\n[3/4] Running parameter sweep...")
    if args.start_idx > 0:
        print(f"  Resuming from experiment index {args.start_idx}")
    t_start = time.time()
    results = run_param_sweep(
        profiles=profiles,
        baselines=baselines,
        dry_run=args.dry_run,
        limit=args.limit,
        start_idx=args.start_idx,
        incremental_output=None if args.dry_run else incremental_tsv,
    )
    elapsed = time.time() - t_start
    print(f"\nCompleted {len(results)} experiments in {elapsed:.1f}s")

    if args.dry_run:
        print("(Dry run complete — no files written)")
        return

    print("\n[4/4] Processing results and selecting dimensional winners...")

    # TSV was already written incrementally; also write JSON
    tsv_path = Path(args.output_dir) / "phase4_param_sweep.tsv"
    if tsv_path.exists():
        results_df = pd.read_csv(str(tsv_path), sep="\t")
        print(f"  TSV rows: {len(results_df)} (includes all prior batches)")

        # Also write JSON from the full TSV
        json_path = Path(args.output_dir) / "phase4_param_sweep.json"
        with open(str(json_path), "w", encoding="utf-8") as f:
            json.dump(results_df.to_dict(orient="records"), f, indent=2, default=str)
        print(f"  Written: {json_path}")
    else:
        # Fallback: write from in-memory results
        write_param_sweep_results(results, args.output_dir)
        results_df = pd.DataFrame(results)

    # Select dimensional winners from full TSV
    winners = select_dimensional_winners(results_df, min_bar_types=2)
    write_dimensional_winners(winners, args.output_dir)

    # Print summary (use in-memory results if available, else load from TSV)
    all_results = results if results else results_df.to_dict(orient="records")
    print_sweep_summary(all_results, winners)

    print(f"\nDone. Total wall time: {elapsed:.1f}s")


if __name__ == "__main__":
    main()
