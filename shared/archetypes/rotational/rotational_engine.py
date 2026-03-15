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

def main(config_path: str, output_path: str) -> None:
    """Main rotational engine pipeline."""
    config = load_and_validate_config(config_path)
    check_holdout_flag(config)

    instrument_info = parse_instruments_md(
        config["instrument"],
        config_path=str(_REPO_ROOT / "_config/instruments.md"),
    )

    # Inject instrument constants into config for simulator use
    config["_instrument"] = instrument_info

    primary_bars, reference_bars = load_bar_data(config)

    # Load simulator module
    simulator_module = config["archetype"].get("simulator_module", "rotational_simulator")
    sim_mod = load_simulator(simulator_module)

    # Run simulation for each primary bar type independently
    all_results = {}
    for source_id, bars in primary_bars.items():
        print(f"Running simulation on {source_id} ({len(bars)} bars)...")

        simulator = sim_mod.RotationalSimulator(
            config=config,
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
    args = parser.parse_args()
    main(args.config, args.output)
