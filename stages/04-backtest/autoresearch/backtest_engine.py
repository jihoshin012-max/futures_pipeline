#!/usr/bin/env python
"""Backtest engine — fixed harness. NEVER MODIFY after Phase 4.

Usage:
    python backtest_engine.py --config params.json --output result.json

Loads config, validates it, loads data, scores touches, dispatches to the
archetype-specific simulator, and writes result.json. All guard rails
(holdout, adapter validation, trail step validation) are active.
"""

import argparse
import importlib
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

# Add repo root so shared.* imports resolve from any working directory
# File is at stages/04-backtest/autoresearch/backtest_engine.py
# parents[0] = autoresearch/, parents[1] = 04-backtest/, parents[2] = stages/, parents[3] = repo root
_REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_REPO_ROOT))

from shared.data_loader import load_data, parse_instruments_md  # noqa: E402
from shared.scoring_models.scoring_adapter import load_scoring_adapter  # noqa: E402

# Holdout flag path — relative to repo root; always resolved from this file's location
HOLDOUT_FLAG = _REPO_ROOT / "stages/04-backtest/p2_holdout/holdout_locked_P2.flag"


# ---------------------------------------------------------------------------
# Config validation
# ---------------------------------------------------------------------------

def validate_trail_steps(steps: list, mode_label: str = "") -> None:
    """Enforce 5 trail step validation rules from config_schema.md.

    Rules:
    1. 0 to 6 steps allowed (empty list = no trail).
    2. trigger_ticks must be strictly monotonically increasing.
    3. For each step, new_stop_ticks must be strictly < trigger_ticks.
    4. new_stop_ticks must be monotonically non-decreasing across steps.
    5. new_stop_ticks[0] must be >= 0.

    Raises:
        SystemExit: If any rule is violated, with a descriptive message.
    """
    prefix = f"{mode_label} " if mode_label else ""
    if len(steps) > 6:
        raise SystemExit(
            f"{prefix}trail_steps: must have 0-6 steps, got {len(steps)}"
        )
    if len(steps) == 0:
        return  # Empty trail is valid (no-trail mode)

    triggers = [s["trigger_ticks"] for s in steps]
    new_stops = [s["new_stop_ticks"] for s in steps]

    # Rule 2: trigger_ticks strictly monotonically increasing
    for i in range(1, len(triggers)):
        if triggers[i] <= triggers[i - 1]:
            raise SystemExit(
                f"{prefix}trail_steps: trigger_ticks must be strictly monotonically "
                f"increasing. Got step {i - 1}={triggers[i - 1]}, step {i}={triggers[i]}"
            )

    # Rule 3: new_stop_ticks < trigger_ticks for each step
    for i, s in enumerate(steps):
        if s["new_stop_ticks"] >= s["trigger_ticks"]:
            raise SystemExit(
                f"{prefix}trail_steps[{i}]: new_stop_ticks ({s['new_stop_ticks']}) "
                f"must be < trigger_ticks ({s['trigger_ticks']})"
            )

    # Rule 4: new_stop_ticks monotonically non-decreasing
    for i in range(1, len(new_stops)):
        if new_stops[i] < new_stops[i - 1]:
            raise SystemExit(
                f"{prefix}trail_steps: new_stop_ticks must be monotonically "
                f"non-decreasing. Got step {i - 1}={new_stops[i - 1]}, step {i}={new_stops[i]}"
            )

    # Rule 5: new_stop_ticks[0] >= 0
    if new_stops[0] < 0:
        raise SystemExit(
            f"{prefix}trail_steps[0]: new_stop_ticks must be >= 0, got {new_stops[0]}"
        )


def load_and_validate_config(path: str) -> dict:
    """Load and validate config JSON. Raises SystemExit on any validation error."""
    with open(path, "r", encoding="utf-8") as f:
        config = json.load(f)

    # Validate required top-level keys
    required_keys = ["version", "instrument", "touches_csv", "bar_data",
                     "scoring_model_path", "archetype", "active_modes", "routing"]
    for key in required_keys:
        if key not in config:
            raise SystemExit(f"Config missing required key: '{key}'")

    if config.get("version") != "v1":
        raise SystemExit(
            f"Unsupported config version '{config.get('version')}'. Expected 'v1'."
        )

    # Validate per-mode trail_steps for each active mode
    for mode in config["active_modes"]:
        if mode not in config:
            raise SystemExit(
                f"Config references active_mode '{mode}' but no '{mode}' block found."
            )
        mode_cfg = config[mode]
        trail_steps = mode_cfg.get("trail_steps", [])
        validate_trail_steps(trail_steps, mode_label=f"[{mode}]")

    return config


# ---------------------------------------------------------------------------
# Holdout guard
# ---------------------------------------------------------------------------

def check_holdout_flag(config: dict) -> None:
    """Abort if holdout flag is set and any config path references P2 data.

    Checks: HOLDOUT_FLAG exists AND any of touches_csv, bar_data filenames
    contain case-insensitive "p2" in Path.name.

    Raises:
        SystemExit: With "HOLDOUT GUARD" if blocked.
    """
    if not HOLDOUT_FLAG.exists():
        return

    paths_to_check = [config.get("touches_csv", ""), config.get("bar_data", "")]
    for p in paths_to_check:
        if "p2" in Path(p).name.lower():
            raise SystemExit(
                f"HOLDOUT GUARD: holdout_locked_P2.flag is set. "
                f"Engine aborted — P2 path detected in config: {p}\n"
                f"P2 runs exactly once with frozen params after human approval."
            )


# ---------------------------------------------------------------------------
# Adapter validation (ENGINE-09)
# ---------------------------------------------------------------------------

def validate_adapter(adapter) -> None:
    """Call score() with empty DataFrame to surface NotImplementedError stubs immediately.

    Passes a zero-row DataFrame with known touch columns to avoid KeyError before
    NotImplementedError fires (per RESEARCH.md Pitfall 6).

    Raises:
        SystemExit: If adapter.score() raises any exception, naming the adapter class.
    """
    # Use expected touch columns (zero rows avoids KeyError in column-accessing stubs)
    stub_df = pd.DataFrame(columns=[
        "DateTime", "BarIndex", "TouchType", "ApproachDir", "TouchPrice",
        "ZoneTop", "ZoneBot"
    ])
    adapter_type = type(adapter).__name__
    try:
        adapter.score(stub_df)
    except NotImplementedError as e:
        raise SystemExit(
            f"ERROR: Scoring adapter '{adapter_type}' is an unimplemented stub. "
            f"Implement score() in shared/scoring_models/scoring_adapter.py "
            f"before running engine."
        ) from e
    except Exception as e:
        raise SystemExit(
            f"ERROR: Scoring adapter '{adapter_type}' raised {type(e).__name__} "
            f"during validation: {e}"
        ) from e


# ---------------------------------------------------------------------------
# Routing waterfall
# ---------------------------------------------------------------------------

def route_waterfall(touches: pd.DataFrame, routing: dict, active_modes: list) -> None:
    """Assign a 'mode' column to touches in-place based on routing config.

    Touches above score_threshold are assigned to active_modes[0] (the primary mode).
    The seq_limit prevents more than seq_limit consecutive touches going to the same mode.
    Touches that don't qualify get mode=None.

    Modifies touches in-place.
    """
    score_threshold = routing.get("score_threshold", 0)
    seq_limit = routing.get("seq_limit", 999)

    modes = [None] * len(touches)
    consecutive = 0
    current_mode_idx = 0

    for i in range(len(touches)):
        score = touches.iloc[i].get("score", 0.0)
        if score >= score_threshold and active_modes:
            if consecutive < seq_limit:
                modes[i] = active_modes[current_mode_idx % len(active_modes)]
                consecutive += 1
            else:
                # Exceeded seq_limit — skip this touch
                modes[i] = None
                consecutive = 0
                current_mode_idx += 1
        else:
            modes[i] = None
            consecutive = 0

    touches["mode"] = modes


# ---------------------------------------------------------------------------
# Simulator loading (dynamic dispatch)
# ---------------------------------------------------------------------------

def load_simulator(simulator_module: str, archetype_name: str):
    """Load simulator module by name. Aborts with clear error if module not found.

    Adds archetype directory to sys.path for module resolution.
    """
    # Add archetype directory to sys.path
    archetype_dir = _REPO_ROOT / "shared/archetypes" / archetype_name
    archetype_dir_str = str(archetype_dir)
    if archetype_dir_str not in sys.path:
        sys.path.insert(0, archetype_dir_str)

    try:
        mod = importlib.import_module(simulator_module)
    except ModuleNotFoundError:
        raise SystemExit(
            f"ERROR: Simulator module '{simulator_module}' not found. "
            f"Check config.archetype.simulator_module and PYTHONPATH. "
            f"Searched archetype dir: {archetype_dir_str}"
        )

    if not hasattr(mod, "run"):
        raise SystemExit(
            f"ERROR: Module '{simulator_module}' has no run() function. "
            f"Simulator must expose: run(bar_df, touch_row, config, bar_offset) -> SimResult"
        )

    return mod


# ---------------------------------------------------------------------------
# Simulation loop
# ---------------------------------------------------------------------------

def run_simulations(simulator, bars: pd.DataFrame, touches: pd.DataFrame,
                    config: dict, instrument_info: dict) -> list:
    """Run simulator for each touch with an assigned mode.

    Finds bar_offset via searchsorted on bar datetime index.
    Passes tick_size through config dict for simulator use.

    Returns:
        List of dicts with: pnl_ticks, win, exit_reason, bars_held, mode.
    """
    tick_size = instrument_info["tick_size"]

    # Build bar datetime array for searchsorted (sorted ascending from load_bars)
    bar_datetimes = bars["datetime"].values

    results = []
    for _, touch in touches[touches["mode"].notna()].iterrows():
        touch_dt = touch["DateTime"]
        # Find the bar index for this touch's entry time
        bar_offset = int(np.searchsorted(bar_datetimes, touch_dt, side="left"))

        # Clamp to valid range
        if bar_offset >= len(bars):
            continue  # No bar data after this touch — skip

        # Build per-touch config with tick_size injected
        sim_config = dict(config)
        sim_config["tick_size"] = tick_size

        sim_result = simulator.run(bars, touch, sim_config, bar_offset)
        results.append({
            "pnl_ticks": sim_result.pnl_ticks,
            "win": sim_result.win,
            "exit_reason": sim_result.exit_reason,
            "bars_held": sim_result.bars_held,
            "mode": touch["mode"],
        })

    return results


# ---------------------------------------------------------------------------
# Metrics computation
# ---------------------------------------------------------------------------

def compute_metrics(results: list, active_modes: list, cost_ticks: float) -> dict:
    """Compute aggregate and per-mode metrics.

    PF = sum(gross winners net of cost) / abs(sum(gross losers net of cost)).
    Total PnL and individual pnl_ticks are net of cost_ticks.

    Returns:
        Dict matching Q6 output schema.
    """
    if not results:
        return {
            "pf": 0.0,
            "n_trades": 0,
            "win_rate": 0.0,
            "total_pnl_ticks": 0.0,
            "max_drawdown_ticks": 0.0,
            "per_mode": {mode: {"pf": 0.0, "n_trades": 0, "win_rate": 0.0}
                         for mode in active_modes},
        }

    # Apply cost: net_pnl = raw_pnl - cost_ticks (per trade)
    net_pnl_list = [r["pnl_ticks"] - cost_ticks for r in results]

    def _compute_pf_and_stats(net_pnls):
        winners = [p for p in net_pnls if p > 0]
        losers = [p for p in net_pnls if p <= 0]
        gross_win = sum(winners)
        gross_loss = abs(sum(losers))
        pf = gross_win / gross_loss if gross_loss > 0 else float("inf")
        win_rate = len(winners) / len(net_pnls) if net_pnls else 0.0
        return pf, win_rate

    def _max_drawdown(net_pnls):
        """Max peak-to-trough cumulative drawdown in ticks."""
        if not net_pnls:
            return 0.0
        cum = np.cumsum(net_pnls)
        peak = np.maximum.accumulate(cum)
        drawdowns = peak - cum
        return float(np.max(drawdowns)) if len(drawdowns) > 0 else 0.0

    overall_pf, overall_wr = _compute_pf_and_stats(net_pnl_list)
    total_pnl = sum(net_pnl_list)
    max_dd = _max_drawdown(net_pnl_list)

    per_mode = {}
    for mode in active_modes:
        mode_results = [r["pnl_ticks"] - cost_ticks
                        for r in results if r.get("mode") == mode]
        if mode_results:
            mpf, mwr = _compute_pf_and_stats(mode_results)
        else:
            mpf, mwr = 0.0, 0.0
        per_mode[mode] = {
            "pf": mpf,
            "n_trades": len(mode_results),
            "win_rate": mwr,
        }

    return {
        "pf": overall_pf,
        "n_trades": len(results),
        "win_rate": overall_wr,
        "total_pnl_ticks": total_pnl,
        "max_drawdown_ticks": max_dd,
        "per_mode": per_mode,
    }


# ---------------------------------------------------------------------------
# Result writer
# ---------------------------------------------------------------------------

def write_result(output_path: str, metrics: dict) -> None:
    """Write metrics dict to output_path as JSON with indent=2."""
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(metrics, f, indent=2)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def main(config_path: str, output_path: str) -> None:
    """Main engine pipeline. Called by CLI or tests."""
    config = load_and_validate_config(config_path)
    check_holdout_flag(config)

    instrument_info = parse_instruments_md(
        config["instrument"],
        config_path=str(_REPO_ROOT / "_config/instruments.md"),
    )

    touches, bars = load_data(config["touches_csv"], config["bar_data"])

    # Sort touches by DateTime for determinism (Pitfall 5)
    touches = touches.sort_values("DateTime").reset_index(drop=True)

    adapter = load_scoring_adapter(
        config["scoring_model_path"],
        config["archetype"]["scoring_adapter"],
    )
    validate_adapter(adapter)

    touches["score"] = adapter.score(touches)
    route_waterfall(touches, config["routing"], config["active_modes"])

    simulator = load_simulator(
        config["archetype"]["simulator_module"],
        config["archetype"]["name"],
    )

    results = run_simulations(simulator, bars, touches, config, instrument_info)
    metrics = compute_metrics(results, config["active_modes"], instrument_info["cost_ticks"])
    write_result(output_path, metrics)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Backtest engine — fixed harness. NEVER MODIFY after Phase 4."
    )
    parser.add_argument("--config", required=True, help="Path to config JSON file")
    parser.add_argument("--output", required=True, help="Path to write result.json")
    args = parser.parse_args()
    main(args.config, args.output)
