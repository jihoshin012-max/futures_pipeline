# archetype: rotational
"""Hypothesis screening runner for the rotational archetype Phase 1 experiments.

Runs all 122 Phase 1 independent screening experiments (41 hypotheses × 3 bar types,
H37 excluded from 10sec), plus adds an N/A_10SEC placeholder for H37 on 10sec.

H37 on bar_data_10sec_rot: bar_formation_rate is constant on fixed-cadence 10-sec series.
H19: SKIPPED_REFERENCE_REQUIRED — needs all 3 bar types loaded simultaneously.

Outputs:
    screening_results/phase1_results.tsv      — unfiltered metrics
    screening_results/phase1_results_rth.tsv  — RTH-filtered metrics (for Phase 1b)
    screening_results/timing_profile.txt      — feature_compute vs simulator breakdown

Usage:
    python run_hypothesis_screening.py [--output-dir screening_results/]
                                       [--single H1]
                                       [--dry-run]
                                       [--rth-only]
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
# Path setup
# ---------------------------------------------------------------------------

_ARCHETYPE_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _ARCHETYPE_DIR.parents[3]
sys.path.insert(0, str(_REPO_ROOT))
sys.path.insert(0, str(_ARCHETYPE_DIR))

from shared.data_loader import load_bars, parse_instruments_md  # noqa: E402
from rotational_simulator import RotationalSimulator  # noqa: E402
from rotational_engine import compute_cycle_metrics  # noqa: E402
from hypothesis_configs import (  # noqa: E402
    HYPOTHESIS_REGISTRY,
    build_experiment_config,
    get_screening_experiments,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_CONFIG_PATH = _ARCHETYPE_DIR / "rotational_params.json"
_INSTRUMENTS_MD = _REPO_ROOT / "_config/instruments.md"
_BASELINE_PATH = _ARCHETYPE_DIR / "baseline_results" / "sweep_P1a.json"

_ALL_SOURCES = [
    "bar_data_250vol_rot",
    "bar_data_250tick_rot",
    "bar_data_10sec_rot",
]

# RTH session limits for vol/tick bars (09:30-16:00 ET)
_RTH_START_HOUR = 9
_RTH_START_MIN = 30
_RTH_END_HOUR = 16
_RTH_END_MIN = 0

# TSV column order
_TSV_COLUMNS = [
    "hypothesis_id",
    "hypothesis_name",
    "dimension",
    "source_id",
    "cycle_pf",
    "delta_pf",
    "total_pnl_ticks",
    "delta_pnl",
    "n_cycles",
    "win_rate",
    "sharpe",
    "max_drawdown_ticks",
    "avg_winner_ticks",
    "avg_loser_ticks",
    "beats_baseline",
    "feature_compute_sec",
    "simulator_sec",
    "total_sec",
    "classification",
]


# ---------------------------------------------------------------------------
# Baseline loading
# ---------------------------------------------------------------------------


def load_baselines(path: str | None = None) -> dict:
    """Load and validate sweep_P1a.json baseline metrics.

    Preflight validation:
        - Top-level key 'best_per_source' must exist
        - Must contain all 3 source IDs

    Args:
        path: Optional path to sweep_P1a.json. Defaults to _BASELINE_PATH.

    Returns:
        dict mapping source_id -> baseline metrics dict.

    Raises:
        ValueError: If schema is invalid or source IDs are missing.
    """
    if path is None:
        path = str(_BASELINE_PATH)

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    if "best_per_source" not in data:
        raise ValueError(
            f"baseline JSON missing required top-level key 'best_per_source'. "
            f"Found keys: {list(data.keys())}"
        )

    best = data["best_per_source"]

    missing_sources = [s for s in _ALL_SOURCES if s not in best]
    if missing_sources:
        raise ValueError(
            f"baseline 'best_per_source' missing source IDs: {missing_sources}. "
            f"Found: {list(best.keys())}"
        )

    return best


# ---------------------------------------------------------------------------
# Config helpers
# ---------------------------------------------------------------------------


def get_base_config() -> dict:
    """Load rotational_params.json and set P1a period + StepDist=6.0 baseline.

    Returns:
        Base config dict with period='P1a' and step_dist=6.0.
    """
    with open(str(_CONFIG_PATH), "r", encoding="utf-8") as f:
        cfg = json.load(f)

    cfg["period"] = "P1a"
    cfg["hypothesis"]["trigger_params"]["step_dist"] = 6.0

    return cfg


def _prepare_single_source_config(
    base_config: dict,
    source_id: str,
    instrument_info: dict,
) -> dict:
    """Return a config dict set up for a single bar source.

    Sets bar_data_primary to the single source_id with the correct path,
    and injects _instrument dict.

    Args:
        base_config: Base config (will be deep-copied).
        source_id: e.g. 'bar_data_250vol_rot'
        instrument_info: {tick_size, cost_ticks, tick_value}

    Returns:
        Config dict ready for RotationalSimulator.
    """
    cfg = copy.deepcopy(base_config)

    # Build bar_data_primary with the single source_id -> path from original config
    original_paths = base_config.get("bar_data_primary", {})
    if source_id in original_paths:
        cfg["bar_data_primary"] = {source_id: original_paths[source_id]}
    else:
        cfg["bar_data_primary"] = {source_id: f"UNKNOWN_PATH/{source_id}.csv"}

    cfg["_instrument"] = instrument_info

    return cfg


def _apply_rth_filter(bar_df: pd.DataFrame) -> pd.DataFrame:
    """Apply RTH filter (09:30-16:00 ET) to vol/tick bar data.

    For vol/tick bars, RTH filter is normally not applied (they're session-filtered
    at construction). This function forces RTH filtering for the force_rth=True mode
    to ensure cross-bar-type comparisons use the same time window (spec 3.7, Pitfall 6).

    Args:
        bar_df: DataFrame with 'datetime' or 'Time' column.

    Returns:
        Filtered DataFrame (reset index).
    """
    import datetime

    rth_start = datetime.time(_RTH_START_HOUR, _RTH_START_MIN, 0)
    rth_end = datetime.time(_RTH_END_HOUR, _RTH_END_MIN, 0)

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

    # If no time column found, return unchanged
    return bar_df


# ---------------------------------------------------------------------------
# Single experiment runner
# ---------------------------------------------------------------------------


def run_single_experiment(
    base_config: dict,
    hypothesis: dict,
    source_id: str,
    bar_data: pd.DataFrame,
    instrument_info: dict,
    baseline_metrics: dict,
    force_rth: bool = False,
) -> dict:
    """Run a single hypothesis experiment and return result dict.

    Handles special cases:
        - H37 on 10sec: returns N/A_10SEC skip record
        - H19 (requires_reference=True): returns SKIPPED_REFERENCE_REQUIRED record

    Args:
        base_config: Source-specific config (from _prepare_single_source_config).
        hypothesis: Hypothesis definition from HYPOTHESIS_REGISTRY.
        source_id: Bar source ID (e.g. 'bar_data_250vol_rot').
        bar_data: Pre-loaded bar DataFrame for this source.
        instrument_info: {tick_size, cost_ticks, tick_value}.
        baseline_metrics: Dict of source_id -> baseline metrics.
        force_rth: If True, apply RTH filter to vol/tick bars before simulation.

    Returns:
        Result dict with all fields in _TSV_COLUMNS schema.
    """
    h_id = hypothesis["id"]
    h_name = hypothesis["name"]
    dimension = hypothesis["dimension"]

    t_start = time.time()

    # --- Special case: H37 on 10sec ---
    if hypothesis.get("exclude_10sec", False) and "10sec" in source_id:
        return {
            "hypothesis_id": h_id,
            "hypothesis_name": h_name,
            "dimension": dimension,
            "source_id": source_id,
            "cycle_pf": None,
            "delta_pf": None,
            "total_pnl_ticks": None,
            "delta_pnl": None,
            "n_cycles": None,
            "win_rate": None,
            "sharpe": None,
            "max_drawdown_ticks": None,
            "avg_winner_ticks": None,
            "avg_loser_ticks": None,
            "beats_baseline": None,
            "feature_compute_sec": 0.0,
            "simulator_sec": 0.0,
            "total_sec": 0.0,
            "classification": "N/A_10SEC",
        }

    # --- Special case: H19 requires reference data ---
    if hypothesis.get("requires_reference", False):
        return {
            "hypothesis_id": h_id,
            "hypothesis_name": h_name,
            "dimension": dimension,
            "source_id": source_id,
            "cycle_pf": None,
            "delta_pf": None,
            "total_pnl_ticks": None,
            "delta_pnl": None,
            "n_cycles": None,
            "win_rate": None,
            "sharpe": None,
            "max_drawdown_ticks": None,
            "avg_winner_ticks": None,
            "avg_loser_ticks": None,
            "beats_baseline": None,
            "feature_compute_sec": 0.0,
            "simulator_sec": 0.0,
            "total_sec": 0.0,
            "classification": "SKIPPED_REFERENCE_REQUIRED",
        }

    # --- Build experiment config ---
    exp_config = build_experiment_config(
        base_config,
        hypothesis,
        hypothesis.get("default_params") or None,
    )

    # Apply force_rth to vol/tick bars (10sec bars are handled by simulator's RTH filter)
    bars = bar_data
    if force_rth and "10sec" not in source_id:
        bars = _apply_rth_filter(bars)

    # --- Time feature computation ---
    t_feature_start = time.time()
    try:
        from rotational_simulator import FeatureComputer  # noqa: PLC0415
        fc = FeatureComputer(exp_config)
        bars_with_features = fc.compute_static_features(bars.copy())
    except Exception:
        bars_with_features = bars
    feature_compute_sec = time.time() - t_feature_start

    # --- Run simulator (timing excludes feature compute done above) ---
    # Note: RotationalSimulator will call FeatureComputer again internally,
    # but for timing accuracy we measure the full simulator.run() wall time.
    t_sim_start = time.time()
    try:
        simulator = RotationalSimulator(config=exp_config, bar_data=bars, reference_data=None)
        sim_result = simulator.run()
    except Exception as e:
        # Experiment failed — record error
        total_sec = time.time() - t_start
        return {
            "hypothesis_id": h_id,
            "hypothesis_name": h_name,
            "dimension": dimension,
            "source_id": source_id,
            "cycle_pf": None,
            "delta_pf": None,
            "total_pnl_ticks": None,
            "delta_pnl": None,
            "n_cycles": None,
            "win_rate": None,
            "sharpe": None,
            "max_drawdown_ticks": None,
            "avg_winner_ticks": None,
            "avg_loser_ticks": None,
            "beats_baseline": None,
            "feature_compute_sec": feature_compute_sec,
            "simulator_sec": 0.0,
            "total_sec": total_sec,
            "classification": f"ERROR: {type(e).__name__}: {e}",
        }
    simulator_sec = time.time() - t_sim_start
    total_sec = time.time() - t_start

    # --- Compute metrics ---
    cost_ticks = instrument_info.get("cost_ticks", 3)
    metrics = compute_cycle_metrics(sim_result.cycles, cost_ticks)

    # --- Compute delta vs baseline ---
    baseline = baseline_metrics.get(source_id, {})
    baseline_pf = baseline.get("cycle_pf", 0.0)
    baseline_pnl = baseline.get("total_pnl_ticks", 0.0)

    cycle_pf = metrics.get("cycle_pf", 0.0)
    total_pnl = metrics.get("total_pnl_ticks", 0.0)

    delta_pf = round(cycle_pf - baseline_pf, 4) if cycle_pf is not None else None
    delta_pnl = round(total_pnl - baseline_pnl, 2) if total_pnl is not None else None

    beats_baseline = bool(cycle_pf > baseline_pf) if cycle_pf is not None else False

    return {
        "hypothesis_id": h_id,
        "hypothesis_name": h_name,
        "dimension": dimension,
        "source_id": source_id,
        "cycle_pf": cycle_pf,
        "delta_pf": delta_pf,
        "total_pnl_ticks": total_pnl,
        "delta_pnl": delta_pnl,
        "n_cycles": metrics.get("n_cycles", 0),
        "win_rate": metrics.get("win_rate", 0.0),
        "sharpe": metrics.get("sharpe", 0.0),
        "max_drawdown_ticks": metrics.get("max_drawdown_ticks", 0.0),
        "avg_winner_ticks": metrics.get("avg_winner_ticks", 0.0),
        "avg_loser_ticks": metrics.get("avg_loser_ticks", 0.0),
        "beats_baseline": beats_baseline,
        "feature_compute_sec": round(feature_compute_sec, 4),
        "simulator_sec": round(simulator_sec, 4),
        "total_sec": round(total_sec, 4),
        "classification": "OK",
    }


# ---------------------------------------------------------------------------
# Full screening runner
# ---------------------------------------------------------------------------


def run_screening(
    experiments: list[dict],
    base_config: dict,
    bar_data_dict: dict[str, pd.DataFrame],
    instrument_info: dict,
    baselines: dict,
    force_rth: bool = False,
) -> list[dict]:
    """Run all experiments and collect results.

    Args:
        experiments: List from get_screening_experiments() (122 items).
        base_config: Base config with StepDist=6.0 and period=P1a.
        bar_data_dict: {source_id: DataFrame} — bar data loaded once per source.
        instrument_info: {tick_size, cost_ticks, tick_value}.
        baselines: {source_id: baseline_metrics} from load_baselines().
        force_rth: If True, pre-filter vol/tick bars to RTH window.

    Returns:
        List of result dicts.
    """
    results = []
    n = len(experiments)

    for i, exp in enumerate(experiments, 1):
        h_id = exp["hypothesis_id"]
        source_id = exp["source_id"]
        hypothesis = HYPOTHESIS_REGISTRY[h_id]

        bars = bar_data_dict.get(source_id)
        if bars is None:
            print(f"  [{i}/{n}] SKIP {h_id} on {source_id}: bar data not loaded")
            continue

        cfg = _prepare_single_source_config(base_config, source_id, instrument_info)

        result = run_single_experiment(
            base_config=cfg,
            hypothesis=hypothesis,
            source_id=source_id,
            bar_data=bars,
            instrument_info=instrument_info,
            baseline_metrics=baselines,
            force_rth=force_rth,
        )

        results.append(result)

        classification = result["classification"]
        if classification == "OK":
            pf = result.get("cycle_pf")
            delta = result.get("delta_pf")
            print(
                f"  [{i}/{n}] {h_id} on {source_id}: "
                f"PF={pf}, delta_PF={delta:+.4f}, beats={result.get('beats_baseline')}"
                if delta is not None
                else f"  [{i}/{n}] {h_id} on {source_id}: PF={pf}"
            )
        else:
            print(f"  [{i}/{n}] {h_id} on {source_id}: {classification}")

    return results


# ---------------------------------------------------------------------------
# TSV writer
# ---------------------------------------------------------------------------


def write_results_tsv(results: list[dict], output_path: str) -> None:
    """Write results to TSV file with fixed column order.

    beats_baseline is written as 'True' or 'False' string.
    None values are written as empty string.

    Args:
        results: List of result dicts from run_single_experiment.
        output_path: Output .tsv file path.
    """
    rows = []
    for r in results:
        row = {}
        for col in _TSV_COLUMNS:
            val = r.get(col)
            if col == "beats_baseline":
                # Write as 'True' / 'False' / '' for None
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
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_path, sep="\t", index=False)
    print(f"Written: {output_path} ({len(df)} rows)")


# ---------------------------------------------------------------------------
# Timing profile
# ---------------------------------------------------------------------------


def print_timing_profile(results: list[dict]) -> str:
    """Summarize feature_compute_sec vs simulator_sec across all results.

    Args:
        results: List of result dicts.

    Returns:
        Timing profile string (also prints to stdout).
    """
    ok_results = [r for r in results if r.get("classification") == "OK"]
    if not ok_results:
        msg = "No OK results for timing profile."
        print(msg)
        return msg

    feature_times = [r.get("feature_compute_sec", 0.0) or 0.0 for r in ok_results]
    sim_times = [r.get("simulator_sec", 0.0) or 0.0 for r in ok_results]
    total_times = [r.get("total_sec", 0.0) or 0.0 for r in ok_results]

    total_feature = sum(feature_times)
    total_sim = sum(sim_times)
    total_wall = sum(total_times)

    feature_pct = 100 * total_feature / total_wall if total_wall > 0 else 0
    sim_pct = 100 * total_sim / total_wall if total_wall > 0 else 0

    lines = [
        "=== Timing Profile ===",
        f"Experiments run: {len(ok_results)}",
        f"Total wall time: {total_wall:.1f}s",
        f"Feature compute: {total_feature:.1f}s ({feature_pct:.1f}%)",
        f"Simulator:       {total_sim:.1f}s ({sim_pct:.1f}%)",
        f"Avg per run:     {total_wall / len(ok_results):.2f}s",
        f"Avg feature:     {sum(feature_times) / len(ok_results):.3f}s",
        f"Avg simulator:   {sum(sim_times) / len(ok_results):.3f}s",
    ]

    msg = "\n".join(lines)
    print(msg)
    return msg


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(description="Run rotational hypothesis screening")
    parser.add_argument(
        "--output-dir",
        default="screening_results/",
        help="Output directory for TSV results",
    )
    parser.add_argument(
        "--single",
        default=None,
        help="Run only a single hypothesis (e.g. --single H1)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print experiments without running",
    )
    parser.add_argument(
        "--rth-only",
        action="store_true",
        help="Force RTH filter on all bar types (for Phase 1b consistency)",
    )
    args = parser.parse_args()

    output_dir = Path(_ARCHETYPE_DIR) / args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.rth_only:
        output_file = str(output_dir / "phase1_results_rth.tsv")
        mode_label = "RTH-filtered"
    else:
        output_file = str(output_dir / "phase1_results.tsv")
        mode_label = "Unfiltered"

    print(f"\n=== Rotational Hypothesis Screening — {mode_label} ===")
    print(f"Output: {output_file}")

    # --- Load baselines ---
    print("\n[1/5] Loading baselines...")
    baselines = load_baselines()
    for sid, m in baselines.items():
        print(f"  {sid}: cycle_pf={m['cycle_pf']}")

    # --- Build base config ---
    print("\n[2/5] Building base config (StepDist=6.0, P1a)...")
    base_config = get_base_config()

    # --- Load instrument info ---
    print("\n[3/5] Loading instrument info...")
    instrument_info = parse_instruments_md(str(_INSTRUMENTS_MD), "NQ")
    print(f"  tick_size={instrument_info['tick_size']}, cost_ticks={instrument_info['cost_ticks']}")

    # --- Load bar data once per source ---
    print("\n[4/5] Loading bar data...")
    bar_data_dict: dict[str, pd.DataFrame] = {}
    for source_id, path in base_config.get("bar_data_primary", {}).items():
        full_path = _REPO_ROOT / path
        print(f"  Loading {source_id}...", end=" ", flush=True)
        t0 = time.time()
        bar_data_dict[source_id] = load_bars(str(full_path))
        print(f"{len(bar_data_dict[source_id])} bars ({time.time() - t0:.1f}s)")

    # --- Get experiments ---
    experiments = get_screening_experiments()  # 122 meaningful experiments

    # Add H37/10sec as explicit N/A record (excluded from get_screening_experiments
    # but included in TSV as documentation)
    h37_10sec_exp = {
        "hypothesis_id": "H37",
        "source_id": "bar_data_10sec_rot",
        "params": {},
        "requires_reference": False,
    }
    # Insert after last H37 entry
    experiments_with_na = []
    h37_inserted = False
    for exp in experiments:
        experiments_with_na.append(exp)
        if exp["hypothesis_id"] == "H37" and not h37_inserted:
            experiments_with_na.append(h37_10sec_exp)
            h37_inserted = True
    if not h37_inserted:
        experiments_with_na.append(h37_10sec_exp)
    experiments = experiments_with_na

    if args.single:
        experiments = [e for e in experiments if e["hypothesis_id"] == args.single]
        print(f"\nSingle mode: {len(experiments)} experiments for {args.single}")

    if args.dry_run:
        print(f"\nDry run: {len(experiments)} experiments would run")
        for exp in experiments[:5]:
            print(f"  {exp['hypothesis_id']} on {exp['source_id']}")
        if len(experiments) > 5:
            print(f"  ... and {len(experiments) - 5} more")
        return

    # --- Run screening ---
    print(f"\n[5/5] Running {len(experiments)} experiments ({mode_label})...")
    t_all = time.time()
    results = run_screening(
        experiments=experiments,
        base_config=base_config,
        bar_data_dict=bar_data_dict,
        instrument_info=instrument_info,
        baselines=baselines,
        force_rth=args.rth_only,
    )
    elapsed = time.time() - t_all
    print(f"\nCompleted {len(results)} experiments in {elapsed:.1f}s")

    # --- Write results ---
    write_results_tsv(results, output_file)

    # --- Timing profile ---
    timing_msg = print_timing_profile(results)
    timing_file = str(output_dir / "timing_profile.txt")
    with open(timing_file, "w", encoding="utf-8") as f:
        f.write(timing_msg + "\n")
    print(f"Timing profile: {timing_file}")

    # --- Summary stats ---
    df = pd.read_csv(output_file, sep="\t")
    ok_df = df[df["classification"] == "OK"]
    bb = ok_df["beats_baseline"].astype(str).str.strip().str.lower()
    n_beat = (bb == "true").sum()

    print(f"\n=== Summary ({mode_label}) ===")
    print(f"Total rows: {len(df)}")
    print(f"OK experiments: {len(ok_df)}")
    print(f"Beat baseline: {n_beat}/{len(ok_df)}")

    for source_id in _ALL_SOURCES:
        src_ok = ok_df[ok_df["source_id"] == source_id]
        src_bb = src_ok["beats_baseline"].astype(str).str.strip().str.lower()
        n_src_beat = (src_bb == "true").sum()
        top5 = src_ok.nlargest(5, "delta_pf")[["hypothesis_id", "delta_pf", "cycle_pf"]]
        print(f"\n  {source_id}: {n_src_beat}/{len(src_ok)} beat baseline")
        if not top5.empty:
            print(f"  Top 5 by delta_pf:")
            for _, row in top5.iterrows():
                print(f"    {row['hypothesis_id']}: delta_pf={row['delta_pf']:+.4f}, pf={row['cycle_pf']:.4f}")


if __name__ == "__main__":
    main()
