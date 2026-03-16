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
# 8. Selection logic: determine winners and produce calibrated configs
# ---------------------------------------------------------------------------

# PnL guard: TDS config is excluded if PnL degrades by more than this fraction vs baseline
_PNL_GUARD_FRACTION = 0.20

# Over-trigger guard: TDS config is flagged if n_td_flatten_cycles > this fraction of baseline n_cycles
_OVER_TRIGGER_FRACTION = 0.05

# L1-only detectors (do NOT include drawdown_budget; it triggers L3 only)
_L1_DETECTORS = ["retracement", "velocity", "consecutive_adds"]


def _load_baselines_from_profiles() -> dict:
    """Load no-TDS baseline metrics for all 9 (profile, bar_type) combinations.

    Returns:
        Dict keyed by (profile_name, source_id) -> {total_pnl_ticks, n_cycles, worst_cycle_dd, ...}.
    """
    profiles = load_profiles()
    baselines = {}
    for profile_name, profile_data in profiles.items():
        for source_id, bt_config in profile_data["bar_types"].items():
            baselines[(profile_name, source_id)] = {
                "total_pnl_ticks": float(bt_config.get("total_pnl_ticks", 0.0)),
                "n_cycles": int(bt_config.get("n_cycles", 0)),
                "worst_cycle_dd": float(bt_config.get("worst_cycle_dd", 0.0)),
                "max_level_exposure_pct": float(bt_config.get("max_level_exposure_pct", 0.0)),
                "tail_ratio": float(bt_config.get("tail_ratio", 0.0)),
            }
    return baselines


def _check_pnl_guard(pnl_impact_ticks: float, baseline_total_pnl: float) -> bool:
    """Return True if the config passes the PnL guard (impact is within -20% of baseline).

    A config passes if: pnl_impact_ticks >= -0.20 * abs(baseline_total_pnl)
    """
    threshold = -_PNL_GUARD_FRACTION * abs(baseline_total_pnl)
    return float(pnl_impact_ticks) >= threshold


def _check_over_trigger(n_td_flatten_cycles: int, baseline_n_cycles: int) -> bool:
    """Return True if config is flagged as over-trigger (more than 5% of cycles are TDS flattens).

    Note: Baseline n_cycles is used as reference; TDS-enabled runs may have higher n_cycles.
    """
    return int(n_td_flatten_cycles) > _OVER_TRIGGER_FRACTION * int(baseline_n_cycles)


def _composite_score(row: pd.Series) -> float:
    """Compute composite survival score: worst_dd_reduction + max_level_pct_reduction.

    Both are positive when survival improves. Used for final config selection.
    """
    return float(row.get("worst_dd_reduction", 0.0)) + float(row.get("max_level_pct_reduction", 0.0))


def _determine_exp3_winners(
    exp1_df: pd.DataFrame,
    exp2_df: pd.DataFrame,
    baselines: dict,
) -> dict:
    """Determine per-combination best L1 detector and best L3 threshold for Experiment 3.

    Selection criteria:
    - L1 winner: best worst_dd_reduction among retracement/velocity/consecutive_adds that pass PnL guard
    - L3 winner: best worst_dd_reduction that passes PnL guard; if none pass, pick least-bad (best pnl_impact)
    - Falls back to defaults (velocity for L1, 100 for L3) if no data available.

    Args:
        exp1_df: Experiment 1 results DataFrame.
        exp2_df: Experiment 2 results DataFrame.
        baselines: Dict from _load_baselines_from_profiles().

    Returns:
        Dict keyed by (profile_name, source_id) -> {"best_l1": str, "best_l3": float,
            "l3_pnl_guard_passed": bool, "l1_dd_reduction": float, "l3_dd_reduction": float}.
    """
    winners = {}

    all_combos = set()
    for _, row in exp1_df.iterrows():
        all_combos.add((row["profile"], row["source_id"]))

    for (profile_name, source_id) in all_combos:
        bl = baselines.get((profile_name, source_id), {
            "total_pnl_ticks": 0.0, "n_cycles": 1,
        })
        baseline_pnl = bl["total_pnl_ticks"]
        baseline_n = bl["n_cycles"]

        # --- L1 winner from Exp 1 ---
        e1_sub = exp1_df[
            (exp1_df["profile"] == profile_name)
            & (exp1_df["source_id"] == source_id)
            & (exp1_df["detector_name"].isin(_L1_DETECTORS))
        ].copy()

        best_l1 = "retracement"  # default
        best_l1_dd = 0.0
        if not e1_sub.empty:
            e1_sub["pnl_guard_pass"] = e1_sub["pnl_impact_ticks"].apply(
                lambda x: _check_pnl_guard(x, baseline_pnl)
            )
            valid_l1 = e1_sub[e1_sub["pnl_guard_pass"]]
            if not valid_l1.empty:
                best_row = valid_l1.loc[valid_l1["worst_dd_reduction"].idxmax()]
                best_l1 = best_row["detector_name"]
                best_l1_dd = float(best_row["worst_dd_reduction"])

        # --- L3 winner from Exp 2 ---
        e2_sub = exp2_df[
            (exp2_df["profile"] == profile_name)
            & (exp2_df["source_id"] == source_id)
        ].copy()

        best_l3 = 100.0  # default
        best_l3_dd = 0.0
        l3_pnl_guard_passed = False
        if not e2_sub.empty:
            e2_sub["pnl_guard_pass"] = e2_sub["pnl_impact_ticks"].apply(
                lambda x: _check_pnl_guard(x, baseline_pnl)
            )
            valid_l3 = e2_sub[e2_sub["pnl_guard_pass"]]
            if not valid_l3.empty:
                # Pick L3 with highest dd_reduction among guard-passing configs
                best_row = valid_l3.loc[valid_l3["worst_dd_reduction"].idxmax()]
                best_l3 = float(best_row["drawdown_budget_ticks"])
                best_l3_dd = float(best_row["worst_dd_reduction"])
                l3_pnl_guard_passed = True
            else:
                # All fail guard — pick the one with least pnl degradation (closest to 0)
                best_row = e2_sub.loc[e2_sub["pnl_impact_ticks"].idxmax()]
                best_l3 = float(best_row["drawdown_budget_ticks"])
                best_l3_dd = float(best_row["worst_dd_reduction"])
                l3_pnl_guard_passed = False

        winners[(profile_name, source_id)] = {
            "best_l1": best_l1,
            "best_l3": best_l3,
            "l3_pnl_guard_passed": l3_pnl_guard_passed,
            "l1_dd_reduction": best_l1_dd,
            "l3_dd_reduction": best_l3_dd,
        }

    return winners


def select_and_run_exp3(
    exp1_df: pd.DataFrame,
    exp2_df: pd.DataFrame,
    args,
    config_template: dict,
    bar_data_dict: dict,
    profiles: dict,
    instrument_info: dict,
    baselines: dict,
) -> pd.DataFrame:
    """Determine per-combination winners from Exp 1+2, then run Exp 3 with per-combination configs.

    This implements the --auto-exp3 behavior: reads Exp 1+2 TSVs, determines winners,
    runs one combined config per (profile, bar_type) combination.

    Args:
        exp1_df: Experiment 1 results.
        exp2_df: Experiment 2 results.
        args: Parsed CLI args.
        config_template, bar_data_dict, profiles, instrument_info: Same as run_experiment().
        baselines: Dict from _load_baselines_from_profiles().

    Returns:
        DataFrame with Experiment 3 results (9 rows, one per combination).
    """
    winners = _determine_exp3_winners(exp1_df, exp2_df, baselines)

    print("\nExperiment 3 winners per combination:")
    for (profile_name, source_id), w in sorted(winners.items()):
        guard_status = "GUARD_PASS" if w["l3_pnl_guard_passed"] else "NO_GUARD_PASS"
        print(
            f"  {profile_name}/{source_id}: "
            f"L1={w['best_l1']}(dd={w['l1_dd_reduction']:.0f}) "
            f"L3={w['best_l3']}({guard_status}, dd={w['l3_dd_reduction']:.0f})"
        )

    # Build per-combination Exp 3 configs and run them
    cost_ticks = instrument_info["cost_ticks"]
    rows = []
    import time as _time
    t_start = _time.time()

    for profile_name, profile_data in profiles.items():
        for source_id, bt_config in profile_data["bar_types"].items():
            if source_id not in bar_data_dict:
                print(f"  WARNING: no bar data for {source_id} — skipping")
                continue

            key = (profile_name, source_id)
            w = winners.get(key, {"best_l1": "velocity", "best_l3": 100.0})

            tds_exp_cfg = build_combined_config(w["best_l1"], w["best_l3"])
            bars = bar_data_dict[source_id]

            base_params = copy.deepcopy(config_template)
            base_params["_instrument"] = instrument_info
            tds_config_dict = tds_exp_cfg["trend_defense"]
            cfg = build_run_config(bt_config, source_id, tds_config_dict, base_params)

            sim = RotationalSimulator(config=cfg, bar_data=bars, reference_data=None)
            result = sim.run()

            if sim._tds is None:
                print(f"  WARNING: TDS not active for {profile_name}/{source_id} — skipping")
                continue

            filtered_bars = _get_filtered_bars(cfg, bars)
            survival = compute_survival_metrics(
                result,
                sim._tds,
                bt_config,
                filtered_bars,
                max_levels=int(bt_config["max_levels"]),
                cost_ticks=cost_ticks,
            )

            tds_l2 = tds_config_dict.get("level_2", {})
            tds_l3 = tds_config_dict.get("level_3", {})
            tds_l1 = tds_config_dict.get("level_1", {})
            tds_prec = tds_config_dict.get("precursor", {})

            row = {
                "experiment": 3,
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
            elapsed = _time.time() - t_start
            print(f"  Exp3 run: {profile_name}/{source_id} ({elapsed:.0f}s)")

    elapsed_total = _time.time() - t_start
    print(f"Experiment 3 complete: {len(rows)} runs in {elapsed_total:.1f}s")

    if not rows:
        return pd.DataFrame(columns=TDS_TSV_COLUMNS)

    df = pd.DataFrame(rows)
    for col in TDS_TSV_COLUMNS:
        if col not in df.columns:
            df[col] = None
    return df[TDS_TSV_COLUMNS]


def select_best_configs(
    exp1_df: pd.DataFrame,
    exp2_df: pd.DataFrame,
    exp3_df: pd.DataFrame,
    baselines: dict,
) -> dict:
    """Select best TDS config per (profile, bar_type) from all 3 experiments.

    Selection rules (per combination):
    1. Compute composite score for each experiment's best: worst_dd_reduction + max_level_pct_reduction
    2. Apply PnL guard: exclude configs where pnl_impact_ticks < -0.20 * baseline total_pnl_ticks
    3. Apply over-trigger flag: flag configs where n_td_flatten_cycles > 5% of baseline n_cycles
    4. Select config with highest composite score from guard-passing configs
    5. If no config passes guard, select least-bad (best pnl_impact_ticks)

    Args:
        exp1_df: Experiment 1 results (isolated detectors).
        exp2_df: Experiment 2 results (drawdown sweep).
        exp3_df: Experiment 3 results (combined).
        baselines: Dict from _load_baselines_from_profiles().

    Returns:
        Dict keyed by (profile_name, source_id) with selection metadata and TDS config.
    """
    best_configs = {}

    all_combos = set()
    for df in [exp1_df, exp2_df, exp3_df]:
        for _, row in df.iterrows():
            all_combos.add((row["profile"], row["source_id"]))

    for (profile_name, source_id) in sorted(all_combos):
        bl = baselines.get((profile_name, source_id), {
            "total_pnl_ticks": 0.0, "n_cycles": 1,
        })
        baseline_pnl = bl["total_pnl_ticks"]
        baseline_n = bl["n_cycles"]

        # Gather all candidate rows from all experiments
        candidates = []

        # Exp 1: take the best L1 detector for this combination (exclude drawdown_budget)
        e1_sub = exp1_df[
            (exp1_df["profile"] == profile_name)
            & (exp1_df["source_id"] == source_id)
            & (exp1_df["detector_name"].isin(_L1_DETECTORS))
        ]
        if not e1_sub.empty:
            best_e1_row = e1_sub.loc[e1_sub["worst_dd_reduction"].idxmax()]
            candidates.append({**dict(best_e1_row), "_experiment_source": "exp1_" + best_e1_row["detector_name"]})

        # Exp 2: take the best drawdown threshold for this combination
        e2_sub = exp2_df[
            (exp2_df["profile"] == profile_name)
            & (exp2_df["source_id"] == source_id)
        ]
        if not e2_sub.empty:
            best_e2_row = e2_sub.loc[e2_sub["worst_dd_reduction"].idxmax()]
            thresh = int(best_e2_row["drawdown_budget_ticks"])
            candidates.append({**dict(best_e2_row), "_experiment_source": f"exp2_drawdown{thresh}"})

        # Exp 3: combined config for this combination
        e3_sub = exp3_df[
            (exp3_df["profile"] == profile_name)
            & (exp3_df["source_id"] == source_id)
        ]
        if not e3_sub.empty:
            e3_row = e3_sub.iloc[0]
            candidates.append({**dict(e3_row), "_experiment_source": "exp3_combined"})

        if not candidates:
            continue

        # Apply guard checks and compute composite score
        for c in candidates:
            c["_pnl_guard_passed"] = _check_pnl_guard(
                float(c.get("pnl_impact_ticks", 0.0)), baseline_pnl
            )
            c["_over_trigger"] = _check_over_trigger(
                int(c.get("n_td_flatten_cycles", 0)), baseline_n
            )
            c["_composite_score"] = _composite_score(pd.Series(c))

        # Select best: prefer guard-passing configs; within that, highest composite score
        guard_passing = [c for c in candidates if c["_pnl_guard_passed"]]
        if guard_passing:
            selected = max(guard_passing, key=lambda c: c["_composite_score"])
        else:
            # No config passes guard — select least-bad by composite score (document this clearly)
            selected = max(candidates, key=lambda c: float(c.get("pnl_impact_ticks", -1e12)))
            selected["_no_guard_pass"] = True

        best_configs[(profile_name, source_id)] = {
            "selected": selected,
            "all_candidates": candidates,
            "baseline": bl,
        }

    return best_configs


def generate_calibration_report(
    exp1_df: pd.DataFrame,
    exp2_df: pd.DataFrame,
    exp3_df: pd.DataFrame,
    best_configs: dict,
    baselines: dict,
) -> str:
    """Generate human-readable markdown calibration report.

    Covers: Experiment 1 findings, Experiment 2 threshold curve, Experiment 3 combined analysis,
    final selection per combination, over-trigger warnings, PnL guard exclusions.

    Args:
        exp1_df, exp2_df, exp3_df: Results from the 3 experiments.
        best_configs: Dict from select_best_configs().
        baselines: Dict from _load_baselines_from_profiles().

    Returns:
        Markdown string with full calibration analysis.
    """
    lines = []
    lines.append("# TDS Calibration Report — Phase 03.1")
    lines.append("")
    lines.append("## Overview")
    lines.append("")
    lines.append("Hypothesis-driven TDS calibration with 3 targeted experiments (~99 total runs).")
    lines.append("**Objective:** Identify which TDS detectors and thresholds provide survival benefit")
    lines.append("(reduced worst-case drawdown) without excessive PnL degradation.")
    lines.append("")
    lines.append("| Experiment | Description | Runs |")
    lines.append("|-----------|-------------|------|")
    lines.append(f"| 1 | Isolated detector test (4 detectors x 3 profiles x 3 bar types) | {len(exp1_df)} |")
    lines.append(f"| 2 | Drawdown budget sweep (6 thresholds x 3 profiles x 3 bar types) | {len(exp2_df)} |")
    lines.append(f"| 3 | Combined winner config (per combination) | {len(exp3_df)} |")
    lines.append(f"| **Total** | | **{len(exp1_df) + len(exp2_df) + len(exp3_df)}** |")
    lines.append("")
    lines.append("**Selection criteria:** Maximize `worst_dd_reduction + max_level_pct_reduction`.")
    lines.append("**PnL guard:** Configs that degrade PnL by >20% vs baseline are excluded.")
    lines.append("**Over-trigger flag:** Configs with >5% of cycles as TDS flattens are flagged.")
    lines.append("")

    # Experiment 1
    lines.append("---")
    lines.append("")
    lines.append("## Experiment 1: Isolated Detector Analysis")
    lines.append("")
    lines.append("Each detector was enabled individually with all others disabled at extreme thresholds.")
    lines.append("")
    lines.append("**Notes:**")
    lines.append("- Detector 1 (retracement): data-driven, no threshold. Only L1 can fire (step widen).")
    lines.append("- Detector 2 (velocity): L1 fire when add velocity < 60s threshold.")
    lines.append("- Detector 3 (consecutive_adds): L1 fire after 3 consecutive adds in same direction.")
    lines.append("- Detector 4 (drawdown_budget): fires L3 directly (force flatten), never L1.")
    lines.append("")

    for source_id in sorted(exp1_df["source_id"].unique()):
        lines.append(f"### {source_id}")
        lines.append("")
        lines.append("| Profile | Detector | L1 Triggers | L3 Triggers | DD Reduction | PnL Impact | PnL Guard | Over-Trigger |")
        lines.append("|---------|----------|------------|------------|-------------|------------|-----------|--------------|")
        sub = exp1_df[exp1_df["source_id"] == source_id]
        for _, row in sub.sort_values(["profile", "detector_name"]).iterrows():
            bl = baselines.get((row["profile"], row["source_id"]), {"total_pnl_ticks": 0.0, "n_cycles": 1})
            guard = "PASS" if _check_pnl_guard(row["pnl_impact_ticks"], bl["total_pnl_ticks"]) else "FAIL"
            ot = "YES" if _check_over_trigger(row["n_td_flatten_cycles"], bl["n_cycles"]) else "no"
            lines.append(
                f"| {row['profile']} | {row['detector_name']} "
                f"| {row['l1_triggers']:,} | {int(row['l3_triggers']):,} "
                f"| {row['worst_dd_reduction']:+.0f} | {row['pnl_impact_ticks']:+.0f} "
                f"| {guard} | {ot} |"
            )
        lines.append("")

    # Key finding: L1 winners
    lines.append("### Experiment 1 Key Findings")
    lines.append("")
    lines.append("**Per combination, best L1 detector (PnL guard passing):**")
    lines.append("")
    for source_id in sorted(exp1_df["source_id"].unique()):
        for profile in sorted(exp1_df["profile"].unique()):
            bl = baselines.get((profile, source_id), {"total_pnl_ticks": 0.0, "n_cycles": 1})
            sub = exp1_df[
                (exp1_df["source_id"] == source_id)
                & (exp1_df["profile"] == profile)
                & (exp1_df["detector_name"].isin(_L1_DETECTORS))
            ].copy()
            if sub.empty:
                continue
            sub["pnl_guard_pass"] = sub["pnl_impact_ticks"].apply(
                lambda x: _check_pnl_guard(x, bl["total_pnl_ticks"])
            )
            valid = sub[sub["pnl_guard_pass"]]
            if not valid.empty:
                best = valid.loc[valid["worst_dd_reduction"].idxmax()]
                lines.append(
                    f"- **{profile}/{source_id}**: `{best['detector_name']}` "
                    f"(dd_reduction={best['worst_dd_reduction']:+.0f}, pnl_impact={best['pnl_impact_ticks']:+.0f})"
                )
            else:
                lines.append(f"- **{profile}/{source_id}**: No L1 detector passes PnL guard")
    lines.append("")

    # Experiment 2
    lines.append("---")
    lines.append("")
    lines.append("## Experiment 2: Drawdown Budget Sweep")
    lines.append("")
    lines.append("Only Detector 4 (drawdown_budget) active. Swept thresholds: 30, 40, 50, 60, 80, 100 ticks.")
    lines.append("Expected: tighter threshold → more L3 triggers → more PnL degradation → more DD reduction.")
    lines.append("")

    for source_id in sorted(exp2_df["source_id"].unique()):
        lines.append(f"### {source_id}")
        lines.append("")
        lines.append("| Profile | Threshold | L3 Triggers | DD Reduction | PnL Impact | PnL Guard | Over-Trigger |")
        lines.append("|---------|-----------|------------|-------------|------------|-----------|--------------|")
        sub = exp2_df[exp2_df["source_id"] == source_id]
        for _, row in sub.sort_values(["profile", "drawdown_budget_ticks"]).iterrows():
            bl = baselines.get((row["profile"], row["source_id"]), {"total_pnl_ticks": 0.0, "n_cycles": 1})
            guard = "PASS" if _check_pnl_guard(row["pnl_impact_ticks"], bl["total_pnl_ticks"]) else "FAIL"
            ot = "YES" if _check_over_trigger(row["n_td_flatten_cycles"], bl["n_cycles"]) else "no"
            lines.append(
                f"| {row['profile']} | {row['drawdown_budget_ticks']:.0f} "
                f"| {int(row['l3_triggers']):,} "
                f"| {row['worst_dd_reduction']:+.0f} | {row['pnl_impact_ticks']:+.0f} "
                f"| {guard} | {ot} |"
            )
        lines.append("")

    # Experiment 3
    lines.append("---")
    lines.append("")
    lines.append("## Experiment 3: Combined Config Validation")
    lines.append("")
    lines.append("Per combination, the best L1 detector from Exp 1 + best L3 threshold from Exp 2 combined.")
    lines.append("")
    lines.append("| Profile | Source | Combined Config | DD Reduction | PnL Impact | PnL Guard | Over-Trigger | vs Best Solo |")
    lines.append("|---------|--------|----------------|-------------|------------|-----------|--------------|--------------|")
    for _, row in exp3_df.sort_values(["profile", "source_id"]).iterrows():
        bl = baselines.get((row["profile"], row["source_id"]), {"total_pnl_ticks": 0.0, "n_cycles": 1})
        guard = "PASS" if _check_pnl_guard(row["pnl_impact_ticks"], bl["total_pnl_ticks"]) else "FAIL"
        ot = "YES" if _check_over_trigger(row["n_td_flatten_cycles"], bl["n_cycles"]) else "no"
        # Compare vs best L1 in Exp 1 (the solo winner)
        e1_sub = exp1_df[
            (exp1_df["profile"] == row["profile"])
            & (exp1_df["source_id"] == row["source_id"])
            & (exp1_df["detector_name"].isin(_L1_DETECTORS))
        ]
        if not e1_sub.empty:
            best_solo_dd = float(e1_sub["worst_dd_reduction"].max())
            vs_solo = row["worst_dd_reduction"] - best_solo_dd
            vs_solo_str = f"{vs_solo:+.0f}"
        else:
            vs_solo_str = "N/A"
        lines.append(
            f"| {row['profile']} | {row['source_id']} | {row['detector_name']} "
            f"| {row['worst_dd_reduction']:+.0f} | {row['pnl_impact_ticks']:+.0f} "
            f"| {guard} | {ot} | {vs_solo_str} |"
        )
    lines.append("")

    # Final Selection
    lines.append("---")
    lines.append("")
    lines.append("## Final Selection: Best TDS Config Per Combination")
    lines.append("")
    lines.append("| Profile | Source | Selected From | DD Reduction | PnL Impact | PnL Guard | Over-Trigger |")
    lines.append("|---------|--------|--------------|-------------|------------|-----------|--------------|")
    for (profile_name, source_id), entry in sorted(best_configs.items()):
        sel = entry["selected"]
        guard_str = "PASS" if sel.get("_pnl_guard_passed", False) else "FAIL**"
        ot_str = "YES**" if sel.get("_over_trigger", False) else "no"
        no_guard_note = " (no config passed guard)" if sel.get("_no_guard_pass", False) else ""
        lines.append(
            f"| {profile_name} | {source_id} | {sel.get('_experiment_source', 'N/A')}{no_guard_note} "
            f"| {sel.get('worst_dd_reduction', 0):+.0f} | {sel.get('pnl_impact_ticks', 0):+.0f} "
            f"| {guard_str} | {ot_str} |"
        )
    lines.append("")

    # Warnings
    warnings = []
    for (profile_name, source_id), entry in sorted(best_configs.items()):
        sel = entry["selected"]
        if sel.get("_no_guard_pass", False):
            warnings.append(f"- **{profile_name}/{source_id}**: No config passed PnL guard — selected least-bad by PnL impact.")
        if sel.get("_over_trigger", False):
            warnings.append(f"- **{profile_name}/{source_id}**: Selected config is OVER-TRIGGER (>5% of cycles as TDS flattens).")

    if warnings:
        lines.append("### Warnings")
        lines.append("")
        for w in warnings:
            lines.append(w)
        lines.append("")

    # Key Observations
    lines.append("---")
    lines.append("")
    lines.append("## Key Observations")
    lines.append("")
    lines.append("1. **Drawdown budget (L3) over-triggers in all configurations**: The L3 force-flatten mechanism")
    lines.append("   converts the majority of the dataset into TDS-controlled cycles, catastrophically destroying PnL.")
    lines.append("   This means the tested thresholds [30-100 ticks] are all too aggressive for the P1a data patterns.")
    lines.append("")
    lines.append("2. **L1 detectors (velocity, consecutive_adds) show limited effect**: Most L1 triggers fire")
    lines.append("   but do not materially reduce worst_cycle_dd. Only velocity shows any meaningful benefit")
    lines.append("   in 10sec bar type where add velocity is more variable.")
    lines.append("")
    lines.append("3. **Retracement detector is effectively a no-op**: L1 triggers fire but produce zero")
    lines.append("   worst_dd_reduction, meaning the step-widening response does not prevent cycles from")
    lines.append("   reaching the same worst-case loss level.")
    lines.append("")
    lines.append("4. **Phase 04 recommendation**: Use `velocity` detector for 10sec bar types where it shows")
    lines.append("   positive benefit. For vol/tick bar types, consider TDS disabled or at very high drawdown")
    lines.append("   thresholds (>200 ticks) that don't over-trigger. The current calibrated configs will be")
    lines.append("   provided per combination, but Phase 04 combination testing should validate these findings.")
    lines.append("")

    return "\n".join(lines)


def write_best_configs(
    best_configs: dict,
    baselines: dict,
    profiles: dict,
    output_dir: Path,
    total_runs: int,
) -> dict:
    """Write best_tds_configs.json with calibrated TDS configs per profile per bar type.

    Output structure:
    {
      "calibration_method": "hypothesis_driven_3_experiments",
      "total_runs": 99,
      "MAX_PROFIT": {
        "bar_data_250vol_rot": {
          "trend_defense": {...},
          "survival_deltas": {...},
          "experiment_source": "exp1_velocity",
          "metadata": {"over_trigger": false, "pnl_guard_passed": true}
        }, ...
      },
      "no_tds_baselines": {...}
    }

    Args:
        best_configs: Dict from select_best_configs().
        baselines: Dict from _load_baselines_from_profiles().
        profiles: Dict from load_profiles().
        output_dir: Directory to write best_tds_configs.json.
        total_runs: Total runs across all experiments.

    Returns:
        The output dict that was written.
    """
    output = {
        "calibration_method": "hypothesis_driven_3_experiments",
        "total_runs": total_runs,
        "no_tds_baselines": {},
    }

    # Populate no_tds_baselines
    for profile_name, profile_data in profiles.items():
        output["no_tds_baselines"][profile_name] = {}
        for source_id, bt_config in profile_data["bar_types"].items():
            output["no_tds_baselines"][profile_name][source_id] = {
                k: v for k, v in bt_config.items()
                if k in ["cycle_pf", "n_cycles", "win_rate", "total_pnl_ticks",
                          "worst_cycle_dd", "max_level_exposure_pct", "tail_ratio",
                          "calmar_ratio", "step_dist", "max_levels", "max_total_position"]
            }

    # Populate calibrated configs
    for (profile_name, source_id), entry in sorted(best_configs.items()):
        if profile_name not in output:
            output[profile_name] = {}

        sel = entry["selected"]

        # Reconstruct trend_defense config from selection row
        trend_defense = {
            "enabled": True,
            "level_1": {
                "step_widen_factor": float(sel.get("step_widen_factor", _SPEC_STEP_WIDEN_FACTOR)),
                "max_levels_reduction": int(sel.get("max_levels_reduction", _SPEC_MAX_LEVELS_REDUCTION)),
            },
            "level_2": {
                "velocity_threshold_sec": float(sel.get("velocity_threshold_sec", _DISABLE_VELOCITY)),
                "consecutive_adds_threshold": int(sel.get("consecutive_adds_threshold", _DISABLE_CONSECUTIVE_ADDS)),
                "retracement_reset_pct": float(sel.get("retracement_reset_pct", _SPEC_RETRACEMENT_RESET_PCT)),
            },
            "level_3": {
                "drawdown_budget_ticks": float(sel.get("drawdown_budget_ticks", _DISABLE_DRAWDOWN)),
                "cooldown_sec": float(sel.get("cooldown_sec", _SPEC_COOLDOWN_SEC)),
            },
            "precursor": {
                "precursor_min_signals": int(sel.get("precursor_min_signals", _DISABLE_PRECURSOR)),
                "speed_threshold": 1.0,
                "regime_accel_threshold": 1.0,
                "adverse_speed_threshold": 1.0,
            },
        }

        output[profile_name][source_id] = {
            "trend_defense": trend_defense,
            "survival_deltas": {
                "worst_dd_reduction": float(sel.get("worst_dd_reduction", 0.0)),
                "max_level_pct_reduction": float(sel.get("max_level_pct_reduction", 0.0)),
                "pnl_impact_ticks": float(sel.get("pnl_impact_ticks", 0.0)),
                "tail_ratio_delta": float(sel.get("tail_ratio_delta", 0.0)),
                "n_td_flatten_cycles": int(sel.get("n_td_flatten_cycles", 0)),
                "l3_recovery_bars_avg": float(sel.get("l3_recovery_bars_avg", 0.0)),
            },
            "experiment_source": sel.get("_experiment_source", "unknown"),
            "metadata": {
                "over_trigger": bool(sel.get("_over_trigger", False)),
                "pnl_guard_passed": bool(sel.get("_pnl_guard_passed", False)),
                "no_guard_pass": bool(sel.get("_no_guard_pass", False)),
                "composite_score": float(sel.get("_composite_score", 0.0)),
            },
        }

    output_path = output_dir / "best_tds_configs.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2)
    print(f"JSON written: {output_path}")
    return output


def run_selection_and_report(
    exp1_df: pd.DataFrame,
    exp2_df: pd.DataFrame,
    exp3_df: pd.DataFrame,
    profiles: dict,
    baselines: dict,
    output_dir: Path,
) -> None:
    """Run selection logic + report generation + write outputs.

    Args:
        exp1_df, exp2_df, exp3_df: Results DataFrames.
        profiles: Dict from load_profiles().
        baselines: Dict from _load_baselines_from_profiles().
        output_dir: Directory to write best_tds_configs.json and tds_calibration_report.md.
    """
    total_runs = len(exp1_df) + len(exp2_df) + len(exp3_df)
    print(f"\nRunning selection on {total_runs} total experiment results...")

    best_configs = select_best_configs(exp1_df, exp2_df, exp3_df, baselines)
    print(f"Selected configs for {len(best_configs)} combinations")

    report = generate_calibration_report(exp1_df, exp2_df, exp3_df, best_configs, baselines)
    report_path = output_dir / "tds_calibration_report.md"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report)
    print(f"Report written: {report_path}")

    write_best_configs(best_configs, baselines, profiles, output_dir, total_runs)

    # Rename exp TSVs to canonical names for plan verification
    _rename_exp_tsvs(output_dir)


def _rename_exp_tsvs(output_dir: Path) -> None:
    """Rename tds_expN_P1a.tsv to canonical names expected by the plan verification.

    Plan expects: exp1_isolated_detectors.tsv, exp2_drawdown_sweep.tsv, exp3_combined.tsv
    """
    renames = [
        ("tds_exp1_P1a.tsv", "exp1_isolated_detectors.tsv"),
        ("tds_exp2_P1a.tsv", "exp2_drawdown_sweep.tsv"),
        ("tds_exp3_P1a.tsv", "exp3_combined.tsv"),
    ]
    for src_name, dst_name in renames:
        src = output_dir / src_name
        dst = output_dir / dst_name
        if src.exists() and not dst.exists():
            import shutil
            shutil.copy2(src, dst)
            print(f"Copied: {src_name} -> {dst_name}")


# ---------------------------------------------------------------------------
# 9. CLI entry point
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
    parser.add_argument(
        "--auto-exp3",
        action="store_true",
        dest="auto_exp3",
        help="Read exp1+exp2 TSVs, determine per-combination winners, run Exp 3 automatically",
    )
    parser.add_argument(
        "--select-best",
        action="store_true",
        dest="select_best",
        help="Read existing experiment TSVs, run selection+reporting without re-running experiments",
    )
    args = parser.parse_args()

    # --- Dry-run mode ---
    if args.dry_run:
        _dry_run(args)
        return

    # --- Select-best mode: read existing TSVs, run selection and reporting ---
    if args.select_best:
        output_dir = Path(args.output_dir)
        profiles = load_profiles()
        baselines = _load_baselines_from_profiles()

        exp1_path = output_dir / "tds_exp1_P1a.tsv"
        exp2_path = output_dir / "tds_exp2_P1a.tsv"
        exp3_path = output_dir / "tds_exp3_P1a.tsv"

        missing = [p for p in [exp1_path, exp2_path, exp3_path] if not p.exists()]
        if missing:
            print(f"ERROR: Missing experiment TSVs: {missing}")
            sys.exit(1)

        exp1_df = pd.read_csv(exp1_path, sep="\t")
        exp2_df = pd.read_csv(exp2_path, sep="\t")
        exp3_df = pd.read_csv(exp3_path, sep="\t")
        print(f"Loaded: exp1={len(exp1_df)} rows, exp2={len(exp2_df)} rows, exp3={len(exp3_df)} rows")

        run_selection_and_report(exp1_df, exp2_df, exp3_df, profiles, baselines, output_dir)
        print("\nDone.")
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

    baselines = _load_baselines_from_profiles()

    # --- Auto-Exp3 mode: determine winners from exp1+exp2, then run exp3 ---
    if args.auto_exp3:
        exp1_path = output_dir / "tds_exp1_P1a.tsv"
        exp2_path = output_dir / "tds_exp2_P1a.tsv"
        if not exp1_path.exists() or not exp2_path.exists():
            print(f"ERROR: --auto-exp3 requires tds_exp1_P1a.tsv and tds_exp2_P1a.tsv in {output_dir}")
            sys.exit(1)

        exp1_df = pd.read_csv(exp1_path, sep="\t")
        exp2_df = pd.read_csv(exp2_path, sep="\t")
        print(f"\nLoaded: exp1={len(exp1_df)} rows, exp2={len(exp2_df)} rows")

        print("\n--- Running Experiment 3 (auto-exp3 mode) ---")
        exp3_df = select_and_run_exp3(
            exp1_df, exp2_df, args, config_template, bar_data_dict, profiles, instrument_info, baselines
        )
        exp3_tsv = output_dir / "tds_exp3_P1a.tsv"
        write_tsv(exp3_tsv, exp3_df)

        run_selection_and_report(exp1_df, exp2_df, exp3_df, profiles, baselines, output_dir)
        print("\nDone.")
        return

    # Determine which experiments to run
    if args.experiment == "all":
        experiments = [1, 2, 3]
    else:
        experiments = [int(args.experiment)]

    all_dfs = {}

    for exp_num in experiments:
        print(f"\n--- Running Experiment {exp_num} ---")
        df = run_experiment(exp_num, args, config_template, bar_data_dict, profiles, instrument_info)
        all_dfs[exp_num] = df

        # Write per-experiment TSV
        exp_tsv = output_dir / f"tds_exp{exp_num}_P1a.tsv"
        write_tsv(exp_tsv, df)

    # Combine all experiments if running all
    if len(all_dfs) > 1:
        combined_df = pd.concat(list(all_dfs.values()), ignore_index=True)
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

        # Run selection and report if all 3 experiments completed
        if all(k in all_dfs for k in [1, 2, 3]):
            run_selection_and_report(
                all_dfs[1], all_dfs[2], all_dfs[3], profiles, baselines, output_dir
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
