# archetype: rotational
"""Rotational backtest engine — continuous state machine harness.

Purpose-built for the rotational archetype. Does NOT share code paths with
backtest_engine.py (zone_touch). Separated to preserve the zone_touch engine
freeze (CLAUDE.md hard prohibition) and because the rotational flow is
fundamentally different: no touches, no scoring adapter, multiple bar types,
continuous bar-by-bar simulation returning cycle-level results.

Usage:
    python rotational_engine.py --config rotational_params.json --output result.json

Flow:
    1. Load + validate rotational config
    2. Holdout guard (P2 one-shot protection)
    3. Load primary bar data + reference bar data
    4. Import and run RotationalSimulator (iterates all bars, returns cycles)
    5. Compute cycle-level metrics
    6. Write result.json
"""

import argparse
import importlib
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

# Repo root: shared/archetypes/rotational/ -> parents[3] = repo root
_REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_REPO_ROOT))

from shared.data_loader import load_bars, parse_instruments_md  # noqa: E402

# Holdout flag — same path as zone_touch engine, same P2 protection
HOLDOUT_FLAG = _REPO_ROOT / "stages/04-backtest/p2_holdout/holdout_locked_P2.flag"


# ---------------------------------------------------------------------------
# Config validation
# ---------------------------------------------------------------------------

_REQUIRED_KEYS = [
    "version", "instrument", "archetype", "bar_data_primary", "period",
]


def load_and_validate_config(path: str) -> dict:
    """Load and validate rotational config JSON.

    Required keys:
        version: "v1"
        instrument: "NQ"
        archetype: {name, simulator_module}
        bar_data_primary: dict mapping source_id -> file path
        period: "P1a" | "P1b" | "P1" | "P2"

    Optional keys:
        bar_data_reference: dict mapping source_id -> file path
        hypothesis_config: dict with trigger, filters, structural mods, TDS
        martingale: {initial_qty, max_levels, max_contract_size, progression}

    Raises SystemExit on validation error.
    """
    with open(path, "r", encoding="utf-8") as f:
        config = json.load(f)

    for key in _REQUIRED_KEYS:
        if key not in config:
            raise SystemExit(f"Config missing required key: '{key}'")

    if config.get("version") != "v1":
        raise SystemExit(
            f"Unsupported config version '{config.get('version')}'. Expected 'v1'."
        )

    archetype = config["archetype"]
    if not isinstance(archetype, dict) or "name" not in archetype:
        raise SystemExit("Config 'archetype' must be a dict with at least 'name'.")
    if archetype["name"] != "rotational":
        raise SystemExit(
            f"rotational_engine.py only handles archetype 'rotational', "
            f"got '{archetype['name']}'."
        )

    bar_data_primary = config["bar_data_primary"]
    if not isinstance(bar_data_primary, dict) or not bar_data_primary:
        raise SystemExit("Config 'bar_data_primary' must be a non-empty dict of source_id -> path.")

    return config


# ---------------------------------------------------------------------------
# Holdout guard
# ---------------------------------------------------------------------------

def check_holdout_flag(config: dict) -> None:
    """Abort if holdout flag is set and config targets P2 data.

    Checks: HOLDOUT_FLAG exists AND period contains "P2" (case-insensitive).
    Also checks all bar_data paths for P2 references.

    Raises SystemExit with HOLDOUT GUARD message if blocked.
    """
    if not HOLDOUT_FLAG.exists():
        return

    period = config.get("period", "").lower()
    if "p2" in period:
        raise SystemExit(
            f"HOLDOUT GUARD: holdout_locked_P2.flag is set. "
            f"Engine aborted — period '{config['period']}' is P2.\n"
            f"P2 runs exactly once with frozen params after human approval."
        )

    # Also check file paths for P2 references
    all_paths = list(config.get("bar_data_primary", {}).values())
    all_paths += list(config.get("bar_data_reference", {}).values())
    for p in all_paths:
        if "p2" in Path(p).name.lower():
            raise SystemExit(
                f"HOLDOUT GUARD: holdout_locked_P2.flag is set. "
                f"Engine aborted — P2 path detected: {p}\n"
                f"P2 runs exactly once with frozen params after human approval."
            )


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_bar_data(config: dict) -> tuple[dict[str, pd.DataFrame], dict[str, pd.DataFrame]]:
    """Load primary and reference bar DataFrames.

    Returns:
        (primary_bars, reference_bars) — each is a dict of source_id -> DataFrame.
        reference_bars may be empty if no reference sources configured.
    """
    primary = {}
    for source_id, path in config["bar_data_primary"].items():
        primary[source_id] = load_bars(path)

    reference = {}
    for source_id, path in config.get("bar_data_reference", {}).items():
        reference[source_id] = load_bars(path)

    return primary, reference


# ---------------------------------------------------------------------------
# Simulator loading
# ---------------------------------------------------------------------------

def load_simulator(simulator_module: str):
    """Load rotational simulator module by name.

    The module must expose a RotationalSimulator class with:
        __init__(self, config, bar_data, reference_data=None)
        run(self) -> SimulationResult

    SimulationResult must have:
        trades: pd.DataFrame (individual actions)
        cycles: pd.DataFrame (reversal-to-reversal summaries)
        bars_processed: int
    """
    archetype_dir = _REPO_ROOT / "shared/archetypes/rotational"
    archetype_dir_str = str(archetype_dir)
    if archetype_dir_str not in sys.path:
        sys.path.insert(0, archetype_dir_str)

    try:
        mod = importlib.import_module(simulator_module)
    except ModuleNotFoundError:
        raise SystemExit(
            f"ERROR: Simulator module '{simulator_module}' not found. "
            f"Check config.archetype.simulator_module. "
            f"Searched: {archetype_dir_str}"
        )

    if not hasattr(mod, "RotationalSimulator"):
        raise SystemExit(
            f"ERROR: Module '{simulator_module}' has no RotationalSimulator class. "
            f"Expected: class with __init__(config, bar_data, reference_data) and run() -> SimulationResult"
        )

    return mod


# ---------------------------------------------------------------------------
# Cycle-level metrics
# ---------------------------------------------------------------------------

def compute_cycle_metrics(cycles: pd.DataFrame, cost_ticks: float) -> dict:
    """Compute cycle-level metrics from simulator output.

    Cycles DataFrame expected columns (from spec Section 6.4):
        cycle_id, direction, gross_pnl_ticks, net_pnl_ticks,
        adds_count, max_level_reached, duration_bars,
        max_adverse_excursion_ticks, max_favorable_excursion_ticks,
        time_at_max_level_bars, exit_reason

    Cost is already applied in net_pnl_ticks by the simulator (cost per action).
    This function computes aggregate metrics on the cycle series.

    Returns dict matching the universal metrics schema (cols 1-24 equivalent).
    """
    if cycles.empty:
        return {
            "cycle_pf": 0.0,
            "n_cycles": 0,
            "win_rate": 0.0,
            "total_pnl_ticks": 0.0,
            "max_drawdown_ticks": 0.0,
            "avg_cycle_duration_bars": 0,
            "sharpe": 0.0,
        }

    pnl = cycles["net_pnl_ticks"].values

    winners = pnl[pnl > 0]
    losers = pnl[pnl <= 0]
    gross_win = float(np.sum(winners))
    gross_loss = float(np.abs(np.sum(losers)))

    cycle_pf = gross_win / gross_loss if gross_loss > 0 else float("inf")
    win_rate = len(winners) / len(pnl) if len(pnl) > 0 else 0.0

    # Max drawdown on cumulative cycle PnL
    cum_pnl = np.cumsum(pnl)
    peak = np.maximum.accumulate(cum_pnl)
    drawdowns = peak - cum_pnl
    max_dd = float(np.max(drawdowns)) if len(drawdowns) > 0 else 0.0

    # Sharpe on cycle PnL series
    if len(pnl) > 1 and np.std(pnl) > 0:
        sharpe = float(np.mean(pnl) / np.std(pnl))
    else:
        sharpe = 0.0

    avg_duration = float(cycles["duration_bars"].mean()) if "duration_bars" in cycles.columns else 0

    return {
        "cycle_pf": round(cycle_pf, 4),
        "n_cycles": int(len(pnl)),
        "win_rate": round(win_rate, 4),
        "total_pnl_ticks": round(float(np.sum(pnl)), 2),
        "max_drawdown_ticks": round(max_dd, 2),
        "avg_cycle_duration_bars": round(avg_duration, 1),
        "sharpe": round(sharpe, 4),
        "avg_winner_ticks": round(float(np.mean(winners)), 2) if len(winners) > 0 else 0.0,
        "avg_loser_ticks": round(float(np.mean(losers)), 2) if len(losers) > 0 else 0.0,
        "max_consecutive_losing_cycles": _max_consecutive_losses(pnl),
    }


def _max_consecutive_losses(pnl: np.ndarray) -> int:
    """Count longest streak of consecutive losing cycles (net_pnl <= 0)."""
    max_streak = 0
    current = 0
    for p in pnl:
        if p <= 0:
            current += 1
            max_streak = max(max_streak, current)
        else:
            current = 0
    return max_streak


def compute_extended_metrics(
    cycles: pd.DataFrame,
    cost_ticks: float,
    bars_df: pd.DataFrame,
    max_levels: int,
) -> dict:
    """Compute extended metrics for sizing sweep scoring.

    Calls compute_cycle_metrics() for base metrics, then adds 7 extended
    metrics required for profile scoring in Plan 03.

    Args:
        cycles: Cycles DataFrame from RotationalSimulator.run().
        cost_ticks: Per-action round-trip cost in ticks.
        bars_df: Full filtered bar DataFrame (used for winning_session_pct).
        max_levels: MaxLevels config value (used for max_level_exposure_pct).

    Returns:
        Merged dict: {**base_metrics, **extended_metrics}.
        All values are scalars (no NaN except where mathematically undefined).
    """
    # Base metrics via existing function
    base = compute_cycle_metrics(cycles, cost_ticks)

    # Edge case: no cycles
    if cycles.empty:
        extended = {
            "worst_cycle_dd": 0.0,
            "max_level_exposure_pct": 0.0,
            "tail_ratio": 0.0,
            "calmar_ratio": 0.0,
            "sortino_ratio": 0.0,
            "winning_session_pct": 0.0,
            "max_dd_duration_bars": 0,
        }
        return {**base, **extended}

    pnl = cycles["net_pnl_ticks"].values

    # 1. worst_cycle_dd: worst single-cycle loss (absolute value of min net_pnl)
    worst_cycle_dd = float(abs(min(pnl))) if len(pnl) > 0 else 0.0

    # 2. max_level_exposure_pct: % of cycles that hit the max level cap
    if "max_level_reached" in cycles.columns and max_levels > 0:
        max_level_exposure_pct = float(
            (cycles["max_level_reached"] == max_levels).sum() / len(cycles) * 100
        )
    else:
        max_level_exposure_pct = 0.0

    # 3. tail_ratio: avg_winner / |avg_loser| — guard divide-by-zero
    avg_winner = base.get("avg_winner_ticks", 0.0)
    avg_loser = base.get("avg_loser_ticks", 0.0)
    if avg_loser != 0.0:
        tail_ratio = float(avg_winner / abs(avg_loser))
    else:
        tail_ratio = 0.0

    # 4. calmar_ratio: total_pnl / max_drawdown — guard divide-by-zero
    total_pnl = base.get("total_pnl_ticks", 0.0)
    max_dd = base.get("max_drawdown_ticks", 0.0)
    if max_dd != 0.0:
        calmar_ratio = float(total_pnl / max_dd)
    else:
        calmar_ratio = 0.0

    # 5. sortino_ratio: mean(pnl) / std(losing pnl) — guard std==0
    losing_pnl = pnl[pnl < 0]
    if len(losing_pnl) > 0 and float(np.std(losing_pnl)) > 0:
        sortino_ratio = float(np.mean(pnl) / np.std(losing_pnl))
    else:
        sortino_ratio = 0.0

    # 6. winning_session_pct: % of trading dates with positive total net PnL
    winning_session_pct = _compute_winning_session_pct(cycles, bars_df)

    # 7. max_dd_duration_bars: longest stretch (in bars) between cumPnL peak and recovery
    max_dd_duration_bars = _compute_max_dd_duration_bars(cycles)

    extended = {
        "worst_cycle_dd": round(worst_cycle_dd, 2),
        "max_level_exposure_pct": round(max_level_exposure_pct, 2),
        "tail_ratio": round(tail_ratio, 4),
        "calmar_ratio": round(calmar_ratio, 4),
        "sortino_ratio": round(sortino_ratio, 4),
        "winning_session_pct": round(winning_session_pct, 2),
        "max_dd_duration_bars": int(max_dd_duration_bars),
    }

    return {**base, **extended}


def _compute_winning_session_pct(cycles: pd.DataFrame, bars_df: pd.DataFrame) -> float:
    """Compute % of trading dates where total net PnL > 0.

    Maps each cycle to a trading date using the start_bar column in cycles.
    Falls back to cycle index if start_bar not available or bars_df empty.
    """
    if cycles.empty:
        return 0.0

    # Check if start_bar column is available and bars_df has datetime
    if (
        "start_bar" in cycles.columns
        and bars_df is not None
        and not bars_df.empty
        and "datetime" in bars_df.columns
    ):
        # Map start_bar -> trading date via bars_df
        dates = []
        for sb in cycles["start_bar"].values:
            try:
                sb_int = int(sb)
                if 0 <= sb_int < len(bars_df):
                    d = bars_df.iloc[sb_int]["datetime"]
                    dates.append(pd.Timestamp(d).date())
                else:
                    dates.append(None)
            except (ValueError, TypeError, IndexError):
                dates.append(None)

        cycles_copy = cycles.copy()
        cycles_copy["_trade_date"] = dates

        # Filter cycles where we got a valid date
        valid = cycles_copy.dropna(subset=["_trade_date"])
        if valid.empty:
            return 0.0

        daily_pnl = valid.groupby("_trade_date")["net_pnl_ticks"].sum()
        winning_days = (daily_pnl > 0).sum()
        total_days = len(daily_pnl)
        return float(winning_days / total_days * 100) if total_days > 0 else 0.0
    else:
        # Fallback: no date information available, return 0
        return 0.0


def _compute_max_dd_duration_bars(cycles: pd.DataFrame) -> int:
    """Compute max drawdown duration in bars.

    From cumulative PnL series: find the longest stretch between a peak and
    recovery to that peak level. If no recovery, duration extends to end of series.

    Uses duration_bars column to estimate bar counts per cycle.
    """
    if cycles.empty or "duration_bars" not in cycles.columns:
        return 0

    pnl = cycles["net_pnl_ticks"].values
    durations = cycles["duration_bars"].values

    # Build cumulative PnL and bar index arrays
    cum_pnl = np.cumsum(pnl)

    # Compute cumulative bar count at each cycle end
    cum_bars = np.cumsum(durations)

    n = len(cum_pnl)
    if n == 0:
        return 0

    max_duration = 0
    peak_val = cum_pnl[0]
    peak_bar = 0  # bar index at peak (using cumulative bars as proxy)

    for i in range(n):
        # Update peak
        if cum_pnl[i] > peak_val:
            peak_val = cum_pnl[i]
            peak_bar = int(cum_bars[i])

        # Current bar position
        current_bar = int(cum_bars[i])

        # Duration from peak to current (drawdown duration)
        if cum_pnl[i] < peak_val:
            duration = current_bar - peak_bar
            max_duration = max(max_duration, duration)

    return int(max_duration)


# ---------------------------------------------------------------------------
# Result writer
# ---------------------------------------------------------------------------

def write_result(output_path: str, metrics: dict, config: dict) -> None:
    """Write result JSON with metrics and config metadata."""
    result = {
        "archetype": "rotational",
        "period": config.get("period", "unknown"),
        "metrics": metrics,
    }

    # Include bar type info for traceability
    result["bar_data_primary"] = list(config.get("bar_data_primary", {}).keys())
    result["bar_data_reference"] = list(config.get("bar_data_reference", {}).keys())

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def load_profile_config(profile_name: str, bar_type: str | None) -> dict:
    """Load a named profile JSON and return the config for the given bar type.

    Args:
        profile_name: Profile name (e.g., "max_profit", "safest", "most_consistent").
        bar_type: Bar type key (e.g., "bar_data_250vol_rot"). If None, uses the first
                  bar type in the profile's bar_types dict.

    Returns:
        Dict with keys: step_dist, max_levels, max_total_position, cycle_pf, ...
        This dict is the winning config entry from the profile JSON.

    Raises:
        SystemExit if profile JSON not found or bar_type not in profile.
    """
    profiles_dir = Path(__file__).resolve().parent / "profiles"
    profile_path = profiles_dir / f"{profile_name.lower()}.json"

    if not profile_path.exists():
        raise SystemExit(
            f"Profile not found: {profile_path}\n"
            f"Run 'python run_sizing_sweep.py --score-profiles' to generate profiles."
        )

    with open(profile_path, "r", encoding="utf-8") as f:
        profile_data = json.load(f)

    bar_types = profile_data.get("bar_types", {})
    if not bar_types:
        raise SystemExit(f"Profile '{profile_name}' has no bar_types entries.")

    # Resolve bar_type
    if bar_type is None:
        bar_type = next(iter(bar_types))
        print(f"  --bar-type not specified; using first bar type: {bar_type}")

    if bar_type not in bar_types:
        available = list(bar_types.keys())
        raise SystemExit(
            f"Bar type '{bar_type}' not in profile '{profile_name}'.\n"
            f"Available bar types: {available}"
        )

    return bar_types[bar_type], bar_type


def apply_profile_overrides(config: dict, profile_cfg: dict, profile_name: str, bar_type: str) -> None:
    """Apply profile config overrides to the engine config in-place.

    Overrides:
        config["hypothesis"]["trigger_params"]["step_dist"]
        config["martingale"]["max_levels"]
        config["martingale"]["max_total_position"]
        config["martingale"]["max_contract_size"] = 16 (fixed per sweep)

    If bar_type is provided, also filters bar_data_primary to only that bar type.

    Prints a summary of the applied overrides.
    """
    # Ensure hypothesis and martingale sections exist
    if "hypothesis" not in config:
        config["hypothesis"] = {}
    if "trigger_params" not in config["hypothesis"]:
        config["hypothesis"]["trigger_params"] = {}
    if "martingale" not in config:
        config["martingale"] = {}

    step_dist = profile_cfg["step_dist"]
    max_levels = profile_cfg["max_levels"]
    max_total_position = profile_cfg["max_total_position"]

    config["hypothesis"]["trigger_params"]["step_dist"] = step_dist
    config["martingale"]["max_levels"] = max_levels
    config["martingale"]["max_total_position"] = max_total_position
    config["martingale"]["max_contract_size"] = 16  # fixed per sweep spec

    print(
        f"Loaded profile {profile_name} for {bar_type}: "
        f"StepDist={step_dist}, ML={max_levels}, MTP={max_total_position}"
    )


def main(config_path: str, output_path: str, profile_name: str | None = None, bar_type: str | None = None) -> None:
    """Main rotational engine pipeline."""
    config = load_and_validate_config(config_path)
    check_holdout_flag(config)

    instrument_info = parse_instruments_md(
        config["instrument"],
        config_path=str(_REPO_ROOT / "_config/instruments.md"),
    )

    # Inject instrument constants into config for simulator use
    config["_instrument"] = instrument_info

    # Apply profile overrides if --profile provided
    if profile_name is not None:
        profile_cfg, resolved_bar_type = load_profile_config(profile_name, bar_type)
        apply_profile_overrides(config, profile_cfg, profile_name, resolved_bar_type)
        # If --bar-type given, filter bar_data_primary to only that bar type
        if bar_type is not None and bar_type in config.get("bar_data_primary", {}):
            config["bar_data_primary"] = {bar_type: config["bar_data_primary"][bar_type]}

    primary_bars, reference_bars = load_bar_data(config)

    # Load simulator module
    simulator_module = config["archetype"].get("simulator_module", "rotational_simulator")
    sim_mod = load_simulator(simulator_module)

    # Run simulation for each primary bar type independently
    all_results = {}
    for source_id, bars in primary_bars.items():
        print(f"Running simulation on {source_id} ({len(bars)} bars)...")

        # Pass a per-source config so the simulator's RTH filter only activates
        # for the source actually being processed (not because another source in
        # bar_data_primary happens to have "10sec" in its key).
        source_config = dict(config)
        source_config["bar_data_primary"] = {source_id: config["bar_data_primary"][source_id]}

        simulator = sim_mod.RotationalSimulator(
            config=source_config,
            bar_data=bars,
            reference_data=reference_bars if reference_bars else None,
        )
        sim_result = simulator.run()

        metrics = compute_cycle_metrics(
            sim_result.cycles,
            cost_ticks=instrument_info["cost_ticks"],
        )
        metrics["bars_processed"] = sim_result.bars_processed

        all_results[source_id] = metrics
        print(f"  {source_id}: {metrics['n_cycles']} cycles, PF={metrics['cycle_pf']}, "
              f"PnL={metrics['total_pnl_ticks']}t")

    # Write results — if single primary source, flatten; if multiple, nest by source
    if len(all_results) == 1:
        write_result(output_path, next(iter(all_results.values())), config)
    else:
        result = {
            "archetype": "rotational",
            "period": config.get("period", "unknown"),
            "bar_data_primary": list(config.get("bar_data_primary", {}).keys()),
            "bar_data_reference": list(config.get("bar_data_reference", {}).keys()),
            "per_source": all_results,
        }
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Rotational backtest engine — continuous state machine harness."
    )
    parser.add_argument("--config", required=True, help="Path to rotational config JSON")
    parser.add_argument("--output", required=True, help="Path to write result.json")
    parser.add_argument(
        "--profile",
        default=None,
        help="Profile name to load (e.g., max_profit, safest, most_consistent). "
             "Overrides martingale params in config with profile winning config.",
    )
    parser.add_argument(
        "--bar-type",
        default=None,
        dest="bar_type",
        help="Bar type for profile config (e.g., bar_data_250vol_rot). "
             "Also filters bar_data_primary to only this bar type.",
    )
    args = parser.parse_args()
    main(args.config, args.output, profile_name=args.profile, bar_type=args.bar_type)
