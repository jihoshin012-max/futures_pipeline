# archetype: rotational
"""TDS hypothesis-driven calibration harness for 3 targeted experiments (~99 total runs).

Purpose: NOT a blind grid search. Hypothesis-driven calibration:
  Experiment 1: Which individual TDS detector helps most? (4 isolated-detector configs x 3 profiles x 3 bar types = 36 runs)
  Experiment 2: What drawdown budget threshold works best? (6 threshold configs x 3 profiles x 3 bar types = 54 runs)
  Experiment 3: Does the best L1 detector + best L3 threshold combination work? (1 config x 3 profiles x 3 bar types = 9 runs)

Total: 36 + 54 + 9 = 99 runs.

Usage:
    python run_tds_calibration.py --dry-run --experiment 1
    python run_tds_calibration.py --experiment 1
    python run_tds_calibration.py --experiment 2
    python run_tds_calibration.py --experiment 3 --best-l1 velocity --best-l3 100
    python run_tds_calibration.py --experiment all --output-dir tds_profiles/
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
# Path setup: repo root is 3 levels up from this file
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

MAX_CONTRACT_SIZE = 16  # fixed per Phase 02.1 decision

# Spec defaults for TDS parameters
_SPEC_VELOCITY_THRESHOLD_SEC = 60.0
_SPEC_CONSECUTIVE_ADDS_THRESHOLD = 3
_SPEC_DRAWDOWN_BUDGET_TICKS = 50.0
_SPEC_COOLDOWN_SEC = 300.0
_SPEC_STEP_WIDEN_FACTOR = 1.5
_SPEC_MAX_LEVELS_REDUCTION = 1
_SPEC_RETRACEMENT_RESET_PCT = 0.3

# Extreme "never fire" thresholds to disable individual detectors
_DISABLE_VELOCITY = 0.001          # converts to velocity_bars=0, never fires since bar_idx > 0
_DISABLE_CONSECUTIVE_ADDS = 999   # never reached
_DISABLE_DRAWDOWN = 999999.0      # never reached
_DISABLE_PRECURSOR = 99           # never reached

# Experiment 2 drawdown sweep thresholds
_DEFAULT_DRAWDOWN_THRESHOLDS = [30, 40, 50, 60, 80, 100]

# TSV column schema for calibration output
TDS_TSV_COLUMNS = [
    # Identity
    "experiment", "detector_name", "profile", "source_id",
    # TDS params
    "drawdown_budget_ticks", "velocity_threshold_sec", "consecutive_adds_threshold",
    "cooldown_sec", "step_widen_factor", "max_levels_reduction",
    "retracement_reset_pct", "precursor_min_signals",
    # Core metrics (from extended_metrics)
    "cycle_pf", "n_cycles", "win_rate", "total_pnl_ticks",
    "max_drawdown_ticks", "sharpe",
    "worst_cycle_dd", "max_level_exposure_pct", "tail_ratio",
    "calmar_ratio", "sortino_ratio", "winning_session_pct",
    "max_dd_duration_bars", "bars_processed",
    # TDS trigger counts
    "l1_triggers", "l2_triggers", "l3_triggers",
    # Survival deltas vs profile baseline
    "worst_dd_reduction", "max_level_pct_reduction",
    "pnl_impact_ticks", "tail_ratio_delta",
    "n_td_flatten_cycles", "l3_recovery_bars_avg",
]


# ---------------------------------------------------------------------------
# 1. Config builders
# ---------------------------------------------------------------------------

def _make_tds_config(
    enabled: bool = True,
    step_widen_factor: float = _SPEC_STEP_WIDEN_FACTOR,
    max_levels_reduction: int = _SPEC_MAX_LEVELS_REDUCTION,
    velocity_threshold_sec: float = _DISABLE_VELOCITY,
    consecutive_adds_threshold: int = _DISABLE_CONSECUTIVE_ADDS,
    retracement_reset_pct: float = _SPEC_RETRACEMENT_RESET_PCT,
    drawdown_budget_ticks: float = _DISABLE_DRAWDOWN,
    cooldown_sec: float = _SPEC_COOLDOWN_SEC,
    precursor_min_signals: int = _DISABLE_PRECURSOR,
    speed_threshold: float = 1.0,
    regime_accel_threshold: float = 1.0,
    adverse_speed_threshold: float = 1.0,
) -> dict:
    """Assemble a TDS config dict with all fields set explicitly."""
    return {
        "enabled": enabled,
        "level_1": {
            "step_widen_factor": step_widen_factor,
            "max_levels_reduction": max_levels_reduction,
        },
        "level_2": {
            "velocity_threshold_sec": velocity_threshold_sec,
            "consecutive_adds_threshold": consecutive_adds_threshold,
            "retracement_reset_pct": retracement_reset_pct,
        },
        "level_3": {
            "drawdown_budget_ticks": drawdown_budget_ticks,
            "cooldown_sec": cooldown_sec,
        },
        "precursor": {
            "precursor_min_signals": precursor_min_signals,
            "speed_threshold": speed_threshold,
            "regime_accel_threshold": regime_accel_threshold,
            "adverse_speed_threshold": adverse_speed_threshold,
        },
    }


def build_isolated_detector_configs() -> list[dict]:
    """Build 4 TDS configs where ONE detector is active and all others are disabled.

    Config A (retracement): Detector 1 is data-pattern-driven (cannot be controlled
        by threshold). Isolate by disabling Detectors 2/3/4/5. Detector 1 will fire
        based on actual retracement patterns.
    Config B (velocity): velocity_threshold_sec at spec default (60). Disable D3/D4/D5.
    Config C (consecutive_adds): consecutive_adds_threshold at spec default (3). Disable D2/D4/D5.
    Config D (drawdown_budget): drawdown_budget_ticks at spec default (50). Disable D2/D3/D5.
        NOTE: Detector 4 always triggers L3 directly (not L1).

    Returns:
        List of 4 config dicts, each with _name and trend_defense keys.
    """
    configs = []

    # Config A: Retracement quality only (Detector 1 is data-driven, no threshold to set)
    tds_a = _make_tds_config(
        velocity_threshold_sec=_DISABLE_VELOCITY,
        consecutive_adds_threshold=_DISABLE_CONSECUTIVE_ADDS,
        drawdown_budget_ticks=_DISABLE_DRAWDOWN,
        precursor_min_signals=_DISABLE_PRECURSOR,
    )
    configs.append({"_name": "retracement", "trend_defense": tds_a})

    # Config B: Velocity monitor only (Detector 2)
    tds_b = _make_tds_config(
        velocity_threshold_sec=_SPEC_VELOCITY_THRESHOLD_SEC,
        consecutive_adds_threshold=_DISABLE_CONSECUTIVE_ADDS,
        drawdown_budget_ticks=_DISABLE_DRAWDOWN,
        precursor_min_signals=_DISABLE_PRECURSOR,
    )
    configs.append({"_name": "velocity", "trend_defense": tds_b})

    # Config C: Consecutive add counter only (Detector 3)
    tds_c = _make_tds_config(
        velocity_threshold_sec=_DISABLE_VELOCITY,
        consecutive_adds_threshold=_SPEC_CONSECUTIVE_ADDS_THRESHOLD,
        drawdown_budget_ticks=_DISABLE_DRAWDOWN,
        precursor_min_signals=_DISABLE_PRECURSOR,
    )
    configs.append({"_name": "consecutive_adds", "trend_defense": tds_c})

    # Config D: Drawdown budget only (Detector 4) — CRITICAL: always triggers L3 directly
    tds_d = _make_tds_config(
        velocity_threshold_sec=_DISABLE_VELOCITY,
        consecutive_adds_threshold=_DISABLE_CONSECUTIVE_ADDS,
        drawdown_budget_ticks=_SPEC_DRAWDOWN_BUDGET_TICKS,
        precursor_min_signals=_DISABLE_PRECURSOR,
    )
    configs.append({"_name": "drawdown_budget", "trend_defense": tds_d})

    return configs


def build_drawdown_sweep_configs(
    thresholds: list[float] | None = None,
) -> list[dict]:
    """Build 6 TDS configs sweeping drawdown_budget_ticks, all other detectors disabled.

    Experiment 2: Tests which drawdown budget threshold produces the best survival delta.
    Only Detector 4 is active (drawdown_budget). Detectors 2/3/5 disabled.
    Same caveat as Detector 1 — it cannot be disabled via threshold.

    Args:
        thresholds: List of drawdown_budget_ticks values. Defaults to [30, 40, 50, 60, 80, 100].

    Returns:
        List of config dicts with _name and trend_defense keys.
    """
    if thresholds is None:
        thresholds = _DEFAULT_DRAWDOWN_THRESHOLDS

    configs = []
    for threshold in thresholds:
        tds = _make_tds_config(
            velocity_threshold_sec=_DISABLE_VELOCITY,
            consecutive_adds_threshold=_DISABLE_CONSECUTIVE_ADDS,
            drawdown_budget_ticks=float(threshold),
            precursor_min_signals=_DISABLE_PRECURSOR,
        )
        configs.append({
            "_name": f"drawdown_sweep_{threshold}",
            "trend_defense": tds,
        })

    return configs


def build_combined_config(best_l1_detector: str, best_l3_threshold: float) -> dict:
    """Build a combined TDS config with the winning L1 detector + best L3 threshold.

    Experiment 3: Tests whether the best L1 detector (from Exp 1) combined with
    the best L3 drawdown threshold (from Exp 2) produces additive survival benefit.

    Args:
        best_l1_detector: One of "retracement", "velocity", "consecutive_adds", "drawdown_budget"
        best_l3_threshold: The winning drawdown_budget_ticks from Experiment 2.

    Returns:
        Config dict with _name and trend_defense keys.
    """
    # Start with all detectors disabled
    velocity = _DISABLE_VELOCITY
    consecutive_adds = _DISABLE_CONSECUTIVE_ADDS

    # Re-enable the winning L1 detector at its spec default
    if best_l1_detector == "velocity":
        velocity = _SPEC_VELOCITY_THRESHOLD_SEC
    elif best_l1_detector == "consecutive_adds":
        consecutive_adds = _SPEC_CONSECUTIVE_ADDS_THRESHOLD
    elif best_l1_detector in ("retracement", "drawdown_budget"):
        # Retracement: data-driven, no threshold to set
        # Drawdown_budget: Exp 3 degenerates to a re-run of Exp 2 winner at best threshold
        pass

    tds = _make_tds_config(
        velocity_threshold_sec=velocity,
        consecutive_adds_threshold=consecutive_adds,
        drawdown_budget_ticks=float(best_l3_threshold),
        precursor_min_signals=_DISABLE_PRECURSOR,
    )

    return {
        "_name": f"combined_{best_l1_detector}_dd{best_l3_threshold}",
        "trend_defense": tds,
    }


def build_run_config(
    profile_data: dict,
    source_id: str,
    tds_config: dict,
    base_params: dict,
) -> dict:
    """Assemble a full simulator config from profile martingale params + TDS config.

    Reads instrument constants from base_params["_instrument"] (already resolved).
    Uses the exact config structure from RESEARCH.md "Full Config Assembly" code.

    Args:
        profile_data: Bar-type-specific profile entry (e.g., profiles/max_profit.json bar_types entry).
        source_id: Bar type source ID (e.g., "bar_data_250vol_rot").
        tds_config: Full TDS config dict (must have "enabled", level_1/2/3, precursor keys).
        base_params: Base rotational_params.json config plus _instrument constants.

    Returns:
        Full config dict ready for RotationalSimulator(config, bars).
    """
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
            "trigger_params": {"step_dist": float(profile_data["step_dist"])},
            "symmetry": "symmetric",
            "symmetry_params": {},
            "active_filters": [],
            "filter_params": {},
            "structural_mods": [],
            "structural_params": {},
        },
        "martingale": {
            "initial_qty": 1,
            "max_levels": int(profile_data["max_levels"]),
            "max_contract_size": MAX_CONTRACT_SIZE,
            "max_total_position": int(profile_data["max_total_position"]),
            "progression": "geometric",
        },
        "trend_defense": tds_config,
        "_instrument": base_params.get("_instrument", {"tick_size": 0.25, "cost_ticks": 3}),
    }


# ---------------------------------------------------------------------------
# 2. Profile loader
# ---------------------------------------------------------------------------

def load_profiles() -> dict:
    """Load all 3 profile JSONs from profiles/ directory.

    Returns:
        Dict: {profile_name: profile_data} for MAX_PROFIT, SAFEST, MOST_CONSISTENT.
    """
    profile_names = ["max_profit", "safest", "most_consistent"]
    profiles = {}
    for name in profile_names:
        path = _PROFILES_DIR / f"{name}.json"
        if path.exists():
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            profiles[data["profile"]] = data
        else:
            print(f"WARNING: Profile not found: {path}")
    return profiles


# ---------------------------------------------------------------------------
# 3. Survival metric computation
# ---------------------------------------------------------------------------

def count_td_flatten_cycles(cycles: pd.DataFrame) -> int:
    """Count cycles with exit_reason='td_flatten' in the cycles DataFrame.

    Args:
        cycles: DataFrame with at least 'exit_reason' column.

    Returns:
        Integer count of td_flatten cycles.
    """
    if cycles.empty or "exit_reason" not in cycles.columns:
        return 0
    return int((cycles["exit_reason"] == "td_flatten").sum())


def compute_survival_metrics(
    result,
    tds,
    baseline_metrics: dict,
    bars_df: pd.DataFrame,
    max_levels: int,
    cost_ticks: float,
) -> dict:
    """Compute survival delta metrics for a TDS experiment run.

    Computes extended metrics via compute_extended_metrics(), gets TDS summary,
    and computes deltas against the no-TDS baseline.

    Args:
        result: SimulationResult from RotationalSimulator.run().
        tds: TrendDefenseSystem instance (after run) or None if not TDS-enabled.
        baseline_metrics: Dict with baseline (no-TDS) metric values including:
            worst_cycle_dd, max_level_exposure_pct, total_pnl_ticks, tail_ratio.
        bars_df: Filtered bar DataFrame (same filter as simulator used).
        max_levels: Max levels setting from the profile.
        cost_ticks: Cost per trade in ticks (from instrument constants).

    Returns:
        Dict with: extended metrics + TDS triggers + survival deltas.
    """
    # Compute extended metrics on this run's cycles
    extended = compute_extended_metrics(
        result.cycles,
        cost_ticks,
        bars_df=bars_df,
        max_levels=max_levels,
    )

    # TDS trigger summary
    tds_summary = tds.get_summary() if tds is not None else {
        "l1_triggers": 0,
        "l2_triggers": 0,
        "l3_triggers": 0,
    }

    # Survival deltas (positive = improvement over baseline)
    worst_dd_reduction = (
        float(baseline_metrics.get("worst_cycle_dd", 0.0))
        - float(extended.get("worst_cycle_dd", 0.0))
    )
    max_level_pct_reduction = (
        float(baseline_metrics.get("max_level_exposure_pct", 0.0))
        - float(extended.get("max_level_exposure_pct", 0.0))
    )
    pnl_impact_ticks = (
        float(extended.get("total_pnl_ticks", 0.0))
        - float(baseline_metrics.get("total_pnl_ticks", 0.0))
    )
    tail_ratio_delta = (
        float(extended.get("tail_ratio", 0.0))
        - float(baseline_metrics.get("tail_ratio", 0.0))
    )

    # TDS-specific metrics
    n_td_flatten = count_td_flatten_cycles(result.cycles)
    td_flatten_cycles = result.cycles[result.cycles["exit_reason"] == "td_flatten"]
    if len(td_flatten_cycles) > 0 and "duration_bars" in td_flatten_cycles.columns:
        l3_recovery_avg = round(float(td_flatten_cycles["duration_bars"].mean()), 1)
    else:
        l3_recovery_avg = 0.0

    return {
        **extended,
        **tds_summary,
        "worst_dd_reduction": worst_dd_reduction,
        "max_level_pct_reduction": max_level_pct_reduction,
        "pnl_impact_ticks": pnl_impact_ticks,
        "tail_ratio_delta": tail_ratio_delta,
        "n_td_flatten_cycles": int(n_td_flatten),
        "l3_recovery_bars_avg": l3_recovery_avg,
    }


# ---------------------------------------------------------------------------
# 4. Filtered bar helper (replicates simulator's date+RTH filter logic)
# ---------------------------------------------------------------------------

def _get_filtered_bars(cfg: dict, bars: pd.DataFrame) -> pd.DataFrame:
    """Apply the same date+RTH filter the simulator uses, without running simulation.

    Needed for winning_session_pct and other per-date metrics.
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
# 5. Experiment runner
# ---------------------------------------------------------------------------

def run_experiment(
    experiment_num: int,
    args,
    config_template: dict,
    bar_data_dict: dict,
    profiles: dict,
    instrument_info: dict,
) -> pd.DataFrame:
    """Run one experiment and return a DataFrame of results.

    For each profile x bar_type x experiment config:
        1. Load no-TDS baseline from profile JSON (do NOT re-run simulator for baseline).
        2. Build full run config with TDS enabled.
        3. Run RotationalSimulator, verify TDS is active (sim._tds is not None).
        4. Compute survival metrics vs baseline.
        5. Append result row.

    Args:
        experiment_num: 1 (isolated detectors), 2 (drawdown sweep), 3 (combined).
        args: Parsed CLI args (for --best-l1, --best-l3, --profile filters).
        config_template: Base rotational_params.json dict.
        bar_data_dict: {source_id: DataFrame} pre-loaded bar data.
        profiles: {profile_name: profile_json_data} from load_profiles().
        instrument_info: {tick_size, cost_ticks} from parse_instruments_md().

    Returns:
        DataFrame with columns matching TDS_TSV_COLUMNS.
    """
    cost_ticks = instrument_info["cost_ticks"]

    # Build experiment configs
    if experiment_num == 1:
        exp_configs = build_isolated_detector_configs()
        exp_label = "isolated_detector"
    elif experiment_num == 2:
        exp_configs = build_drawdown_sweep_configs()
        exp_label = "drawdown_sweep"
    elif experiment_num == 3:
        best_l1 = getattr(args, "best_l1", "velocity") or "velocity"
        best_l3 = float(getattr(args, "best_l3", "100") or "100")
        exp_configs = [build_combined_config(best_l1, best_l3)]
        exp_label = "combined"
    else:
        raise ValueError(f"Unknown experiment_num: {experiment_num}")

    rows = []
    t_start = time.time()
    run_count = 0

    profile_filter = getattr(args, "profile", None)

    for profile_name, profile_data in profiles.items():
        if profile_filter and profile_name.lower() != profile_filter.lower():
            continue

        for source_id, bt_config in profile_data["bar_types"].items():
            if source_id not in bar_data_dict:
                print(f"  WARNING: no bar data for {source_id} — skipping")
                continue

            bars = bar_data_dict[source_id]

            for tds_exp_cfg in exp_configs:
                # Merge base_params with instrument info
                base_params = copy.deepcopy(config_template)
                base_params["_instrument"] = instrument_info

                # Build full simulator config
                tds_config_dict = tds_exp_cfg["trend_defense"]
                cfg = build_run_config(bt_config, source_id, tds_config_dict, base_params)

                # Run simulation
                sim = RotationalSimulator(config=cfg, bar_data=bars, reference_data=None)
                result = sim.run()

                # Verify TDS is active (Pitfall 1 from RESEARCH.md)
                if sim._tds is None:
                    print(
                        f"  WARNING: TDS not active for {profile_name}/{source_id}/"
                        f"{tds_exp_cfg['_name']} — skipping"
                    )
                    continue

                # Get filtered bars for extended metrics
                filtered_bars = _get_filtered_bars(cfg, bars)

                # Compute survival metrics (baseline from profile JSON)
                survival = compute_survival_metrics(
                    result,
                    sim._tds,
                    bt_config,  # profile JSON metrics ARE the no-TDS baseline
                    filtered_bars,
                    max_levels=int(bt_config["max_levels"]),
                    cost_ticks=cost_ticks,
                )

                # Extract TDS params from config for TSV row
                tds_l2 = tds_config_dict.get("level_2", {})
                tds_l3 = tds_config_dict.get("level_3", {})
                tds_l1 = tds_config_dict.get("level_1", {})
                tds_prec = tds_config_dict.get("precursor", {})

                row = {
                    "experiment": experiment_num,
                    "detector_name": tds_exp_cfg["_name"],
                    "profile": profile_name,
                    "source_id": source_id,
                    "drawdown_budget_ticks": tds_l3.get("drawdown_budget_ticks", _DISABLE_DRAWDOWN),
                    "velocity_threshold_sec": tds_l2.get("velocity_threshold_sec", _DISABLE_VELOCITY),
                    "consecutive_adds_threshold": tds_l2.get("consecutive_adds_threshold", _DISABLE_CONSECUTIVE_ADDS),
                    "cooldown_sec": tds_l3.get("cooldown_sec", _SPEC_COOLDOWN_SEC),
                    "step_widen_factor": tds_l1.get("step_widen_factor", _SPEC_STEP_WIDEN_FACTOR),
                    "max_levels_reduction": tds_l1.get("max_levels_reduction", _SPEC_MAX_LEVELS_REDUCTION),
                    "retracement_reset_pct": tds_l2.get("retracement_reset_pct", _SPEC_RETRACEMENT_RESET_PCT),
                    "precursor_min_signals": tds_prec.get("precursor_min_signals", _DISABLE_PRECURSOR),
                    "bars_processed": result.bars_processed,
                    **survival,
                }
                rows.append(row)

                run_count += 1
                elapsed = time.time() - t_start
                if run_count % 10 == 0:
                    print(f"  Progress: {run_count} runs ({elapsed:.0f}s)")

    elapsed_total = time.time() - t_start
    print(f"Experiment {experiment_num} complete: {run_count} runs in {elapsed_total:.1f}s")

    if not rows:
        return pd.DataFrame(columns=TDS_TSV_COLUMNS)

    df = pd.DataFrame(rows)
    # Ensure column order (add any missing with NaN)
    for col in TDS_TSV_COLUMNS:
        if col not in df.columns:
            df[col] = None
    return df[TDS_TSV_COLUMNS]


# ---------------------------------------------------------------------------
# 6. Output writers
# ---------------------------------------------------------------------------

def write_tsv(output_path: Path, df: pd.DataFrame) -> None:
    """Write experiment results as TSV."""
    df.to_csv(output_path, sep="\t", index=False)
    print(f"TSV written: {output_path} ({len(df)} rows)")


def write_json(output_path: Path, df: pd.DataFrame, meta: dict) -> None:
    """Write experiment results as JSON with metadata."""
    output = {
        "metadata": meta,
        "results": df.to_dict(orient="records"),
    }
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2)
    print(f"JSON written: {output_path}")


# ---------------------------------------------------------------------------
# 7. CLI entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="TDS hypothesis-driven calibration harness (3 experiments, ~99 runs)"
    )
    parser.add_argument(
        "--experiment",
        choices=["1", "2", "3", "all"],
        default="all",
        help="Which experiment to run: 1=isolated detectors, 2=drawdown sweep, 3=combined, all=all",
    )
    parser.add_argument(
        "--output-dir",
        default=str(_ARCHETYPE_DIR / "tds_profiles"),
        help="Directory to write results TSV and JSON",
    )
    parser.add_argument(
        "--config",
        default=str(_CONFIG_PATH),
        help="Path to rotational_params.json",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print experiment configs without running simulator, then exit 0",
    )
    parser.add_argument(
        "--profile",
        default=None,
        help="Run only one profile (e.g., MAX_PROFIT). Default: all",
    )
    parser.add_argument(
        "--best-l1",
        default="velocity",
        dest="best_l1",
        help="For Experiment 3: which L1 detector won Experiment 1 (e.g., 'velocity')",
    )
    parser.add_argument(
        "--best-l3",
        default="100",
        dest="best_l3",
        help="For Experiment 3: which drawdown threshold won Experiment 2 (e.g., '100')",
    )
    args = parser.parse_args()

    # --- Dry-run mode ---
    if args.dry_run:
        _dry_run(args)
        return

    # --- Normal execution ---
    output_dir = Path(args.output_dir)
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
    for source_id, path in config_template["bar_data_primary"].items():
        bars = load_bars(str(_REPO_ROOT / path))
        bar_data_dict[source_id] = bars
        print(f"  {source_id}: {len(bars)} total bars loaded")

    # Load profiles
    profiles = load_profiles()
    print(f"\nProfiles loaded: {list(profiles.keys())}")

    # Determine which experiments to run
    if args.experiment == "all":
        experiments = [1, 2, 3]
    else:
        experiments = [int(args.experiment)]

    all_results = []

    for exp_num in experiments:
        print(f"\n--- Running Experiment {exp_num} ---")
        df = run_experiment(exp_num, args, config_template, bar_data_dict, profiles, instrument_info)
        all_results.append(df)

        # Write per-experiment TSV
        exp_tsv = output_dir / f"tds_exp{exp_num}_P1a.tsv"
        write_tsv(exp_tsv, df)

    # Combine all experiments if running all
    if len(all_results) > 1:
        combined_df = pd.concat(all_results, ignore_index=True)
        combined_tsv = output_dir / "tds_calibration_P1a.tsv"
        write_tsv(combined_tsv, combined_df)
        write_json(
            output_dir / "tds_calibration_P1a.json",
            combined_df,
            {
                "experiments": experiments,
                "period": "P1a",
                "total_runs": len(combined_df),
                "profiles": list(profiles.keys()),
            },
        )

    print("\nDone.")


def _dry_run(args) -> None:
    """Print experiment configs and counts without running simulator."""
    experiment = args.experiment

    if experiment in ("1", "all"):
        configs = build_isolated_detector_configs()
        print(f"Experiment 1 — Isolated Detector Configs: {len(configs)} configs")
        for i, cfg in enumerate(configs, 1):
            tds = cfg["trend_defense"]
            l2 = tds.get("level_2", {})
            l3 = tds.get("level_3", {})
            print(
                f"  [{i}] {cfg['_name']}: "
                f"vel={l2.get('velocity_threshold_sec')}, "
                f"consec={l2.get('consecutive_adds_threshold')}, "
                f"dd={l3.get('drawdown_budget_ticks')}"
            )
        print(f"  Run count: {len(configs)} configs x 3 profiles x 3 bar_types = {len(configs)*9} runs")

    if experiment in ("2", "all"):
        configs = build_drawdown_sweep_configs()
        print(f"\nExperiment 2 — Drawdown Sweep Configs: {len(configs)} configs")
        for i, cfg in enumerate(configs, 1):
            tds = cfg["trend_defense"]
            l3 = tds.get("level_3", {})
            print(f"  [{i}] {cfg['_name']}: drawdown_budget_ticks={l3.get('drawdown_budget_ticks')}")
        print(f"  Run count: {len(configs)} configs x 3 profiles x 3 bar_types = {len(configs)*9} runs")

    if experiment in ("3", "all"):
        best_l1 = getattr(args, "best_l1", "velocity") or "velocity"
        best_l3 = float(getattr(args, "best_l3", "100") or "100")
        cfg = build_combined_config(best_l1, best_l3)
        tds = cfg["trend_defense"]
        l2 = tds.get("level_2", {})
        l3 = tds.get("level_3", {})
        print(f"\nExperiment 3 — Combined Config: 1 config")
        print(
            f"  [1] {cfg['_name']}: "
            f"vel={l2.get('velocity_threshold_sec')}, "
            f"consec={l2.get('consecutive_adds_threshold')}, "
            f"dd={l3.get('drawdown_budget_ticks')}"
        )
        print(f"  Run count: 1 config x 3 profiles x 3 bar_types = 9 runs")

    if experiment == "all":
        total = 4 * 9 + 6 * 9 + 1 * 9
        print(f"\nTotal runs (all experiments): {total}")


if __name__ == "__main__":
    main()
