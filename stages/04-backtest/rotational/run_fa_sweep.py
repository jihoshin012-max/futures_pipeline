# archetype: rotational
"""Frozen-Anchor Sweep — Generate 210 configs and run on P1 1-tick data.

Usage:
    cd stages/04-backtest/rotational
    python run_fa_sweep.py [--smoke-only] [--workers 4]

Primary question: does ReversalTarget < 1.0 push the success rate above 50%
enough to create positive EV, and do adds amplify that through payoff asymmetry?

Config grid: 7 StepDists × 5 ReversalTargets × 6 add groups = 210 configs.

Context tagging:
  - 1-tick bars used for simulation (context_bars=None to simulator).
  - 250-tick bars used for context tags, joined to cycles by timestamp post-sim.

Incomplete cycles:
  At session end, cycles in progress are mark-to-market'd and logged to
  {config_id}_incomplete.csv. Summary includes incomplete_cycles count and
  incomplete_unrealized_pnl.
"""
from __future__ import annotations

import argparse
import json
import multiprocessing as mp
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

# Ensure local imports resolve
_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from config_schema import FrozenAnchorConfig
from context_tagger import tag_context
from rotation_simulator import run_frozen_anchor_simulation

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
COST_TICKS = 2.0   # Per-side cost in ticks (from instruments.md)
TICK_SIZE = 0.25    # NQ tick size from instruments.md

_TICK_DIR = _SCRIPT_DIR.parents[1] / "01-data" / "data" / "bar_data" / "tick"
P1_DATA_PATH = _TICK_DIR / "NQ_BarData_1tick_rot_P1.csv"
P1_CONTEXT_PATH = _TICK_DIR / "NQ_BarData_250tick_rot_P1.csv"

OUTPUT_DIR = _SCRIPT_DIR / "frozen_anchor_sweep"
CYCLE_LOG_DIR = OUTPUT_DIR / "cycle_logs"

# P1 date boundaries (inclusive)
P1_START = pd.Timestamp("2025-09-21")
P1_END = pd.Timestamp("2025-12-17")

# RTH boundaries (seconds from midnight)
RTH_START_SEC = 9 * 3600 + 30 * 60   # 09:30
RTH_END_SEC = 16 * 3600 + 15 * 60    # 16:15

# Temp file for sharing bars across worker processes
_BARS_FEATHER = OUTPUT_DIR / "_bars_tmp.feather"


# ---------------------------------------------------------------------------
# Data loading (same as V1.1 sweep)
# ---------------------------------------------------------------------------

def load_p1_bars() -> pd.DataFrame:
    """Load P1 1-tick bar data, filter to RTH and P1 date range."""
    print(f"Loading P1 1-tick bar data from: {P1_DATA_PATH}")

    header = pd.read_csv(P1_DATA_PATH, nrows=0)
    header.columns = header.columns.str.strip()
    needed = ["Date", "Time", "Open", "High", "Low", "Last"]
    col_indices = [list(header.columns).index(c) for c in needed]
    df = pd.read_csv(P1_DATA_PATH, usecols=col_indices, dtype={
        "Open": "float32", "High": "float32", "Low": "float32", "Last": "float32",
    })

    df.columns = df.columns.str.strip()
    df["datetime"] = pd.to_datetime(df["Date"].str.strip() + " " + df["Time"].str.strip())
    df.drop(columns=["Date", "Time"], inplace=True)

    # Filter to P1 date range
    dates = df["datetime"].dt.normalize()
    df = df[(dates >= P1_START) & (dates <= P1_END)].copy()

    # Filter to RTH
    time_sec = df["datetime"].dt.hour * 3600 + df["datetime"].dt.minute * 60 + df["datetime"].dt.second
    df = df[(time_sec >= RTH_START_SEC) & (time_sec < RTH_END_SEC)].copy()
    df = df.reset_index(drop=True)

    trading_days = df["datetime"].dt.date.nunique()
    mem_mb = df.memory_usage(deep=True).sum() / 1e6
    print(f"  Total rows (RTH, P1): {len(df):,}")
    print(f"  Date range: {df['datetime'].iloc[0]} to {df['datetime'].iloc[-1]}")
    print(f"  RTH trading days: {trading_days}")
    print(f"  Memory: {mem_mb:.0f} MB")

    return df


def load_context_bars() -> pd.DataFrame:
    """Load 250-tick bars and pre-compute context tags."""
    print(f"Loading 250-tick context bars from: {P1_CONTEXT_PATH}")
    df = pd.read_csv(P1_CONTEXT_PATH)
    df.columns = df.columns.str.strip()
    df["datetime"] = pd.to_datetime(df["Date"].str.strip() + " " + df["Time"].str.strip())
    df.drop(columns=["Date", "Time"], inplace=True, errors="ignore")

    dates = df["datetime"].dt.normalize()
    df = df[(dates >= P1_START) & (dates <= P1_END)].copy()
    time_sec = df["datetime"].dt.hour * 3600 + df["datetime"].dt.minute * 60 + df["datetime"].dt.second
    df = df[(time_sec >= RTH_START_SEC) & (time_sec < RTH_END_SEC)].copy()
    df = df.reset_index(drop=True)

    print(f"  250-tick context bars: {len(df):,}")
    t0 = time.time()
    df = tag_context(df)
    print(f"  Context tagging complete ({time.time() - t0:.1f}s)")
    return df


def join_context_to_cycles(cycles_df: pd.DataFrame, ctx_bars: pd.DataFrame) -> pd.DataFrame:
    """Join pre-computed context from 250-tick bars to cycle records by nearest timestamp."""
    if cycles_df.empty or ctx_bars.empty:
        return cycles_df

    ctx_cols = ["atr_20", "atr_pct", "bar_range_median_20",
                "swing_median_20", "swing_p90_20", "directional_persistence"]
    available = [c for c in ctx_cols if c in ctx_bars.columns]
    if not available:
        return cycles_df

    ctx_dt = pd.to_datetime(ctx_bars["datetime"]).values
    ctx_vals = ctx_bars[available].values

    cycle_starts = pd.to_datetime(cycles_df["start_time"]).values
    indices = np.searchsorted(ctx_dt, cycle_starts, side="right") - 1
    indices = np.clip(indices, 0, len(ctx_vals) - 1)

    col_map = {"atr_20": "atr_20bar", "atr_pct": "atr_percentile"}
    for j, col in enumerate(available):
        target_col = col_map.get(col, col)
        cycles_df[target_col] = ctx_vals[indices, j]

    return cycles_df


# ---------------------------------------------------------------------------
# Config generation — 210 configs (7 SD × 5 RT × 6 add groups)
# ---------------------------------------------------------------------------

def generate_all_configs() -> list[FrozenAnchorConfig]:
    """Generate all 210 frozen-anchor sweep configs."""
    configs: list[FrozenAnchorConfig] = []

    for sd in [15, 20, 25, 30, 35, 40, 50]:
        for rt in [0.5, 0.6, 0.7, 0.8, 1.0]:
            rt_tag = int(rt * 100)

            # Group MA0: pure rotation (no adds)
            configs.append(FrozenAnchorConfig(
                config_id=f"FA_SD{sd}_MA0_RT{rt_tag}",
                step_dist=float(sd),
                add_dist=sd * 0.4,  # Unused but required > 0
                max_adds=0,
                reversal_target=rt,
                cost_ticks=COST_TICKS,
            ))

            # Group R04_MA1: ratio 0.4, 1 add
            ad4 = round(sd * 0.4, 2)
            configs.append(FrozenAnchorConfig(
                config_id=f"FA_SD{sd}_R04_MA1_RT{rt_tag}",
                step_dist=float(sd),
                add_dist=ad4,
                max_adds=1,
                reversal_target=rt,
                cost_ticks=COST_TICKS,
            ))

            # Group R04_MA2: ratio 0.4, 2 adds
            configs.append(FrozenAnchorConfig(
                config_id=f"FA_SD{sd}_R04_MA2_RT{rt_tag}",
                step_dist=float(sd),
                add_dist=ad4,
                max_adds=2,
                reversal_target=rt,
                cost_ticks=COST_TICKS,
            ))

            # Group R05_MA1: ratio 0.5, 1 add
            ad5 = round(sd * 0.5, 2)
            configs.append(FrozenAnchorConfig(
                config_id=f"FA_SD{sd}_R05_MA1_RT{rt_tag}",
                step_dist=float(sd),
                add_dist=ad5,
                max_adds=1,
                reversal_target=rt,
                cost_ticks=COST_TICKS,
            ))

            # Group R03_MA2: ratio 0.3, 2 adds
            ad3 = round(sd * 0.3, 2)
            configs.append(FrozenAnchorConfig(
                config_id=f"FA_SD{sd}_R03_MA2_RT{rt_tag}",
                step_dist=float(sd),
                add_dist=ad3,
                max_adds=2,
                reversal_target=rt,
                cost_ticks=COST_TICKS,
            ))

            # Group R03_MA3: ratio 0.3, 3 adds (max asymmetry)
            configs.append(FrozenAnchorConfig(
                config_id=f"FA_SD{sd}_R03_MA3_RT{rt_tag}",
                step_dist=float(sd),
                add_dist=ad3,
                max_adds=3,
                reversal_target=rt,
                cost_ticks=COST_TICKS,
            ))

    return configs


def count_by_group(configs: list[FrozenAnchorConfig]) -> dict[str, int]:
    """Count configs by add group (parsed from config_id)."""
    counts: dict[str, int] = {}
    for c in configs:
        # Extract group from config_id: FA_SD{sd}_{group}_RT{rt}
        parts = c.config_id.split("_")
        # Group is the part(s) between SD and RT
        sd_idx = next(i for i, p in enumerate(parts) if p.startswith("SD"))
        rt_idx = next(i for i, p in enumerate(parts) if p.startswith("RT"))
        group = "_".join(parts[sd_idx + 1 : rt_idx])
        counts[group] = counts.get(group, 0) + 1
    return counts


# ---------------------------------------------------------------------------
# Per-config summary (frozen-anchor specific)
# ---------------------------------------------------------------------------

def compute_fa_summary(
    cycles_df: pd.DataFrame,
    incomplete_df: pd.DataFrame,
    config: FrozenAnchorConfig,
) -> dict:
    """Compute all summary metrics for one frozen-anchor config."""
    n_cycles = len(cycles_df)

    if n_cycles == 0:
        s = _empty_fa_summary(config)
        s["incomplete_cycles"] = len(incomplete_df)
        s["incomplete_unrealized_pnl"] = round(
            incomplete_df["unrealized_pnl_ticks"].sum(), 4
        ) if not incomplete_df.empty else 0.0
        s["adjusted_net_pnl"] = s["incomplete_unrealized_pnl"]
        return s

    net_pnl = cycles_df["pnl_ticks_net"]
    gross_pnl = cycles_df["pnl_ticks_gross"]

    wins = cycles_df[net_pnl > 0]
    losses = cycles_df[net_pnl <= 0]

    net_wins_sum = net_pnl[net_pnl > 0].sum()
    net_losses_sum = net_pnl[net_pnl <= 0].sum()
    gross_wins_sum = gross_pnl[net_pnl > 0].sum()
    gross_losses_sum = gross_pnl[net_pnl <= 0].sum()

    npf_gross = gross_wins_sum / abs(gross_losses_sum) if gross_losses_sum != 0 else (999.0 if gross_wins_sum > 0 else 0.0)
    npf_net = net_wins_sum / abs(net_losses_sum) if net_losses_sum != 0 else (999.0 if net_wins_sum > 0 else 0.0)

    # Max drawdown (cycle-level cumulative)
    cumulative = net_pnl.cumsum()
    rolling_max = cumulative.cummax()
    drawdown = cumulative - rolling_max
    max_dd = abs(drawdown.min()) if len(drawdown) > 0 else 0.0

    total_net = net_pnl.sum()
    profit_per_dd = total_net / max_dd if max_dd > 0 else (999.0 if total_net > 0 else 0.0)

    # Add-count breakdown
    add_counts = cycles_df["add_count"]
    mask_0 = add_counts == 0
    mask_1 = add_counts == 1
    mask_multi = add_counts >= 2

    max_pos = cycles_df["exit_position"].max() if "exit_position" in cycles_df.columns else 1

    # --- Frozen-anchor specific metrics ---

    # Success rate (structural: exit_type based)
    has_exit_type = "exit_type" in cycles_df.columns
    if has_exit_type:
        success_count = int((cycles_df["exit_type"] == "SUCCESS").sum())
        failure_count = int((cycles_df["exit_type"] == "FAILURE").sum())
        success_rate = success_count / n_cycles if n_cycles > 0 else 0.0
    else:
        success_count = 0
        failure_count = 0
        success_rate = 0.0

    # Failure-after-failure cascading
    failure_after_failure = 0
    if has_exit_type:
        exit_types = cycles_df["exit_type"].values
        for i in range(1, len(exit_types)):
            if exit_types[i] == "FAILURE" and exit_types[i - 1] == "FAILURE":
                failure_after_failure += 1

    # Incomplete cycles
    inc_count = len(incomplete_df)
    inc_pnl = round(incomplete_df["unrealized_pnl_ticks"].sum(), 4) if not incomplete_df.empty else 0.0
    adjusted_net = round(total_net + inc_pnl, 4)

    # Progress HWM averages
    avg_hwm_success = 0.0
    avg_hwm_failure = 0.0
    if has_exit_type and "progress_hwm" in cycles_df.columns:
        success_mask = cycles_df["exit_type"] == "SUCCESS"
        failure_mask = cycles_df["exit_type"] == "FAILURE"
        if success_mask.any():
            avg_hwm_success = round(cycles_df.loc[success_mask, "progress_hwm"].mean(), 2)
        if failure_mask.any():
            avg_hwm_failure = round(cycles_df.loc[failure_mask, "progress_hwm"].mean(), 2)

    # Cycle waste average
    avg_waste = 0.0
    if "cycle_waste_pct" in cycles_df.columns:
        valid_waste = cycles_df["cycle_waste_pct"].dropna()
        if len(valid_waste) > 0:
            avg_waste = round(valid_waste.mean(), 2)

    # First-cycle vs later-cycle success rate
    first_sr = 0.0
    later_sr = 0.0
    if has_exit_type and "cycle_day_seq" in cycles_df.columns:
        first_mask = cycles_df["cycle_day_seq"] == 1
        later_mask = cycles_df["cycle_day_seq"] > 1
        if first_mask.any():
            first_sr = round(
                (cycles_df.loc[first_mask, "exit_type"] == "SUCCESS").mean(), 4
            )
        if later_mask.any():
            later_sr = round(
                (cycles_df.loc[later_mask, "exit_type"] == "SUCCESS").mean(), 4
            )

    return {
        # Config params
        "config_id": config.config_id,
        "step_dist": config.step_dist,
        "add_dist": config.add_dist,
        "max_adds": config.max_adds,
        "reversal_target": config.reversal_target,
        # Cycle counts
        "cycle_count": n_cycles,
        "success_count": success_count,
        "failure_count": failure_count,
        "success_rate": round(success_rate, 4),
        "win_count": len(wins),
        "loss_count": len(losses),
        "win_rate": round(len(wins) / n_cycles, 4),
        # PnL
        "gross_pnl": round(gross_pnl.sum(), 4),
        "net_pnl": round(total_net, 4),
        "total_costs": round(gross_pnl.sum() - total_net, 4),
        "npf_gross": round(npf_gross, 4),
        "npf_net": round(npf_net, 4),
        "avg_win_net": round(wins["pnl_ticks_net"].mean(), 4) if len(wins) > 0 else 0.0,
        "avg_loss_net": round(losses["pnl_ticks_net"].mean(), 4) if len(losses) > 0 else 0.0,
        # Risk
        "max_drawdown_ticks": round(max_dd, 4),
        "profit_per_dd": round(profit_per_dd, 4),
        "max_position": int(max_pos),
        "avg_cycle_duration_bars": round(cycles_df["duration_bars"].mean(), 2),
        # Add-count breakdown
        "cycles_0_adds": int(mask_0.sum()),
        "cycles_1_add": int(mask_1.sum()),
        "cycles_multi_add": int(mask_multi.sum()),
        "pnl_0_adds": round(net_pnl[mask_0].sum(), 4),
        "pnl_1_add": round(net_pnl[mask_1].sum(), 4),
        "pnl_multi_add": round(net_pnl[mask_multi].sum(), 4),
        # Failure dynamics
        "failure_after_failure": failure_after_failure,
        "incomplete_cycles": inc_count,
        "incomplete_unrealized_pnl": inc_pnl,
        "adjusted_net_pnl": adjusted_net,
        # Diagnostic aggregates
        "avg_progress_hwm_success": avg_hwm_success,
        "avg_progress_hwm_failure": avg_hwm_failure,
        "avg_cycle_waste_pct": avg_waste,
        "first_cycle_success_rate": first_sr,
        "later_cycle_success_rate": later_sr,
    }


def _empty_fa_summary(config: FrozenAnchorConfig) -> dict:
    return {
        "config_id": config.config_id,
        "step_dist": config.step_dist,
        "add_dist": config.add_dist,
        "max_adds": config.max_adds,
        "reversal_target": config.reversal_target,
        "cycle_count": 0, "success_count": 0, "failure_count": 0, "success_rate": 0.0,
        "win_count": 0, "loss_count": 0, "win_rate": 0.0,
        "gross_pnl": 0.0, "net_pnl": 0.0, "total_costs": 0.0,
        "npf_gross": 0.0, "npf_net": 0.0,
        "avg_win_net": 0.0, "avg_loss_net": 0.0,
        "max_drawdown_ticks": 0.0, "profit_per_dd": 0.0,
        "max_position": 0, "avg_cycle_duration_bars": 0.0,
        "cycles_0_adds": 0, "cycles_1_add": 0, "cycles_multi_add": 0,
        "pnl_0_adds": 0.0, "pnl_1_add": 0.0, "pnl_multi_add": 0.0,
        "failure_after_failure": 0,
        "incomplete_cycles": 0, "incomplete_unrealized_pnl": 0.0,
        "adjusted_net_pnl": 0.0,
        "avg_progress_hwm_success": 0.0, "avg_progress_hwm_failure": 0.0,
        "avg_cycle_waste_pct": 0.0,
        "first_cycle_success_rate": 0.0, "later_cycle_success_rate": 0.0,
    }


# ---------------------------------------------------------------------------
# Worker function for multiprocessing
# ---------------------------------------------------------------------------

_worker_bars: pd.DataFrame | None = None
_worker_ctx_250: pd.DataFrame | None = None


def _worker_init(bars_feather_path: str, ctx_250_feather_path: str | None) -> None:
    """Initialize worker process: load bars from feather."""
    global _worker_bars, _worker_ctx_250
    _worker_bars = pd.read_feather(bars_feather_path)
    if ctx_250_feather_path:
        _worker_ctx_250 = pd.read_feather(ctx_250_feather_path)
    else:
        _worker_ctx_250 = None


def _run_one_config(config: FrozenAnchorConfig) -> dict[str, Any]:
    """Run a single frozen-anchor config in a worker process."""
    global _worker_bars, _worker_ctx_250

    t0 = time.time()
    result = run_frozen_anchor_simulation(config, _worker_bars, context_bars=None, tick_size=TICK_SIZE)
    elapsed = time.time() - t0

    cycles = result.cycles
    incomplete = result.incomplete_cycles

    # Join context from 250-tick bars
    if _worker_ctx_250 is not None and not cycles.empty:
        cycles = join_context_to_cycles(cycles, _worker_ctx_250)

    # Compute summary
    summary = compute_fa_summary(cycles, incomplete, config)

    return {
        "config": config,
        "cycles": cycles,
        "incomplete": incomplete,
        "summary": summary,
        "elapsed": elapsed,
    }


# ---------------------------------------------------------------------------
# Smoke test — 5 configs, one per RT at SD=25, R04_MA2
# ---------------------------------------------------------------------------

def run_smoke_test(bars: pd.DataFrame, ctx_250: pd.DataFrame | None = None) -> bool:
    """Run 5 smoke configs (one per RT value). Return True if all pass."""
    smoke_configs = [
        FrozenAnchorConfig("SMOKE_RT50", 25.0, 10.0, 2, 0.5, COST_TICKS),
        FrozenAnchorConfig("SMOKE_RT60", 25.0, 10.0, 2, 0.6, COST_TICKS),
        FrozenAnchorConfig("SMOKE_RT70", 25.0, 10.0, 2, 0.7, COST_TICKS),
        FrozenAnchorConfig("SMOKE_RT80", 25.0, 10.0, 2, 0.8, COST_TICKS),
        FrozenAnchorConfig("SMOKE_RT100", 25.0, 10.0, 2, 1.0, COST_TICKS),
    ]

    report_lines = [
        "# Frozen-Anchor Smoke Test Report",
        f"**Date:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"**Bars:** {len(bars):,} (RTH, P1, 1-tick)",
        f"**Config:** SD=25, AD=10 (R04), MA=2, cost=2.0t/side",
        "",
        "## RT Comparison (Key Question: Does success rate increase as RT decreases?)",
        "",
        "| RT | Cycles | Success% | Failure% | Win% | Net PnL | Adj Net | Avg HWM(S) | Avg HWM(F) | Time |",
        "|----|--------|----------|----------|------|---------|---------|------------|------------|------|",
    ]

    all_pass = True
    smoke_results: list[dict] = []

    for cfg in smoke_configs:
        print(f"\n  Smoke: {cfg.config_id} ...", end=" ", flush=True)
        t0 = time.time()
        result = run_frozen_anchor_simulation(cfg, bars, context_bars=None, tick_size=TICK_SIZE)
        elapsed = time.time() - t0
        cycles = result.cycles
        incomplete = result.incomplete_cycles

        if ctx_250 is not None and not cycles.empty:
            cycles = join_context_to_cycles(cycles, ctx_250)

        summary = compute_fa_summary(cycles, incomplete, cfg)
        smoke_results.append(summary)

        n = summary["cycle_count"]
        issues: list[str] = []

        if n == 0:
            issues.append("0 cycles produced")

        # Check expected columns present
        if not cycles.empty:
            expected_cols = {"exit_type", "progress_hwm", "cycle_day_seq",
                             "cycle_start_hour", "prev_cycle_exit_type",
                             "pnl_ticks_gross", "pnl_ticks_net"}
            missing = expected_cols - set(cycles.columns)
            if missing:
                issues.append(f"Missing columns: {missing}")

            # Check exit_type values are valid
            valid_types = {"SUCCESS", "FAILURE", "SESSION_END"}
            actual_types = set(cycles["exit_type"].unique())
            invalid = actual_types - valid_types
            if invalid:
                issues.append(f"Invalid exit_type values: {invalid}")

            # Check costs applied
            if cycles["pnl_ticks_net"].sum() >= cycles["pnl_ticks_gross"].sum():
                issues.append("Net PnL >= Gross PnL (costs not applied?)")

        # Check incomplete cycles captured
        if len(incomplete) == 0:
            issues.append("0 incomplete cycles (expected some at session boundaries)")

        status = "PASS" if not issues else "FAIL"
        if issues:
            all_pass = False

        sr = summary["success_rate"]
        fr = summary["failure_count"] / n if n > 0 else 0
        print(f"{status} ({n} cycles, SR={sr:.1%}, net={summary['net_pnl']:.0f}, {elapsed:.1f}s)")

        # Table row
        report_lines.append(
            f"| {cfg.reversal_target} | {n} | {sr:.1%} | {fr:.1%} "
            f"| {summary['win_rate']:.1%} | {summary['net_pnl']:.0f} "
            f"| {summary['adjusted_net_pnl']:.0f} "
            f"| {summary['avg_progress_hwm_success']:.1f} "
            f"| {summary['avg_progress_hwm_failure']:.1f} "
            f"| {elapsed:.1f}s |"
        )

        if issues:
            for iss in issues:
                report_lines.append(f"\n**{cfg.config_id} ISSUE:** {iss}")

    # Check monotonicity: success rate should increase as RT decreases
    report_lines.append("")
    report_lines.append("## Monotonicity Check")
    srs = [(r["reversal_target"], r["success_rate"]) for r in smoke_results]
    srs_sorted = sorted(srs, key=lambda x: x[0])  # ascending RT
    monotonic = all(srs_sorted[i][1] >= srs_sorted[i + 1][1]
                     for i in range(len(srs_sorted) - 1))

    if monotonic:
        report_lines.append("**PASS**: Success rate monotonically decreases as RT increases.")
    else:
        report_lines.append("**WARNING**: Success rate is NOT monotonically decreasing with RT.")
        report_lines.append(f"Values: {srs_sorted}")
        # This is a warning, not a hard fail — small RT differences may cause noise

    for rt, sr in srs_sorted:
        report_lines.append(f"- RT={rt}: success_rate={sr:.4f}")

    # Core thesis check
    report_lines.append("")
    rt50_sr = next(r["success_rate"] for r in smoke_results if r["reversal_target"] == 0.5)
    rt100_sr = next(r["success_rate"] for r in smoke_results if r["reversal_target"] == 1.0)
    report_lines.append(f"**RT=0.5 success rate: {rt50_sr:.1%}** vs **RT=1.0: {rt100_sr:.1%}**")
    if rt50_sr > rt100_sr:
        report_lines.append("Core thesis SUPPORTED: lower RT produces higher success rate.")
    else:
        report_lines.append("**CORE THESIS BROKEN: lower RT does NOT produce higher success rate.**")
        all_pass = False

    # First vs later cycle comparison
    report_lines.append("")
    report_lines.append("## First Cycle vs Later Cycle Success Rate")
    report_lines.append("| RT | First Cycle SR | Later Cycle SR |")
    report_lines.append("|----|---------------|----------------|")
    for r in smoke_results:
        report_lines.append(
            f"| {r['reversal_target']} | {r['first_cycle_success_rate']:.1%} "
            f"| {r['later_cycle_success_rate']:.1%} |"
        )

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUTPUT_DIR / "smoke_test_report.md").write_text("\n".join(report_lines), encoding="utf-8")
    print(f"\n  Smoke report saved to frozen_anchor_sweep/smoke_test_report.md")

    return all_pass


# ---------------------------------------------------------------------------
# Full sweep with multiprocessing
# ---------------------------------------------------------------------------

def run_full_sweep(
    configs: list[FrozenAnchorConfig],
    bars: pd.DataFrame,
    ctx_250: pd.DataFrame | None = None,
    n_workers: int = 4,
) -> pd.DataFrame:
    """Run all configs with multiprocessing, save cycle logs + incomplete logs."""
    CYCLE_LOG_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    total = len(configs)

    # Save bars to feather for fast worker loading
    print(f"  Serializing bars to feather for worker processes...")
    t0 = time.time()
    bars.to_feather(_BARS_FEATHER)
    ctx_feather = OUTPUT_DIR / "_ctx250_tmp.feather"
    ctx_feather_path: str | None = None
    if ctx_250 is not None:
        ctx_250.to_feather(ctx_feather)
        ctx_feather_path = str(ctx_feather)
    print(f"  Feather serialization: {time.time() - t0:.1f}s")

    print(f"  Starting {n_workers} worker processes...")
    t_start = time.time()

    summaries: list[dict] = []
    zero_cycle_configs: list[str] = []
    completed = 0

    with mp.Pool(
        processes=n_workers,
        initializer=_worker_init,
        initargs=(str(_BARS_FEATHER), ctx_feather_path),
    ) as pool:
        for result in pool.imap_unordered(_run_one_config, configs):
            completed += 1
            config = result["config"]
            cycles = result["cycles"]
            incomplete = result["incomplete"]
            summary = result["summary"]
            elapsed = result["elapsed"]

            # Save cycle log
            cycles.to_csv(CYCLE_LOG_DIR / f"{config.config_id}.csv", index=False)

            # Save incomplete cycle log
            if not incomplete.empty:
                incomplete.to_csv(CYCLE_LOG_DIR / f"{config.config_id}_incomplete.csv", index=False)

            summaries.append(summary)

            n = summary["cycle_count"]
            n_inc = summary["incomplete_cycles"]
            if n == 0:
                zero_cycle_configs.append(config.config_id)
                print(f"  [{completed:3d}/{total}] {config.config_id}: "
                      f"*** 0 CYCLES *** ({n_inc} inc, {elapsed:.1f}s)")
            else:
                sr = summary["success_rate"]
                adj = summary["adjusted_net_pnl"]
                print(f"  [{completed:3d}/{total}] {config.config_id}: "
                      f"{n} cyc, SR={sr:.1%}, adj_net={adj:.0f}, "
                      f"inc={n_inc} ({elapsed:.1f}s)")

    total_runtime = time.time() - t_start
    print(f"\n  Sweep complete: {total} configs in {total_runtime:.0f}s ({total_runtime/60:.1f}min)")

    if zero_cycle_configs:
        print(f"  WARNING: {len(zero_cycle_configs)} configs produced 0 cycles: {zero_cycle_configs}")

    # Clean up temp feather files
    _BARS_FEATHER.unlink(missing_ok=True)
    ctx_feather.unlink(missing_ok=True)

    # Sort summaries by config_id for deterministic output
    summaries.sort(key=lambda s: s["config_id"])

    # Save config_summary.csv
    summary_df = pd.DataFrame(summaries)
    summary_df.to_csv(OUTPUT_DIR / "config_summary.csv", index=False)
    print(f"  config_summary.csv: {len(summary_df)} rows")

    # Save metadata
    by_group = count_by_group(configs)
    trading_days = bars["datetime"].dt.date.nunique()
    metadata = {
        "run_timestamp": datetime.now().isoformat(),
        "strategy": "frozen_anchor",
        "p1_date_range": f"{bars['datetime'].iloc[0].strftime('%Y-%m-%d')} to "
                         f"{bars['datetime'].iloc[-1].strftime('%Y-%m-%d')}",
        "bar_type": "1tick",
        "total_bars": len(bars),
        "rth_trading_days": int(trading_days),
        "total_configs": total,
        "config_groups": by_group,
        "cost_ticks": COST_TICKS,
        "context_thresholds": {"swing_zigzag": 5, "persistence_zigzag": 10},
        "total_runtime_seconds": round(total_runtime, 1),
        "n_workers": n_workers,
        "zero_cycle_configs": zero_cycle_configs,
        "verification": {
            "success_rate_at_rt100": "see smoke_test_report.md",
            "fractal_check": "add_count != retracement_count (survivorship bias)",
        },
    }
    with open(OUTPUT_DIR / "sweep_metadata.json", "w") as f:
        json.dump(metadata, f, indent=2)
    print(f"  sweep_metadata.json saved")

    return summary_df


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Frozen-Anchor Sweep: 210 configs on P1 1-tick data")
    parser.add_argument("--smoke-only", action="store_true",
                        help="Run only smoke test, skip full sweep")
    parser.add_argument("--workers", type=int, default=4,
                        help="Number of worker processes (default: 4)")
    args = parser.parse_args()

    print("=" * 70)
    print(f"FROZEN-ANCHOR SWEEP (1-tick, {args.workers} workers)")
    print("=" * 70)

    # Step 1: Load P1 bar data
    print(f"\n[1/5] Loading P1 1-tick bar data...")
    bars = load_p1_bars()

    # Step 2: Context tags (from 250-tick bars)
    print("\n[2/5] Pre-computing context tags on 250-tick reference bars...")
    ctx_250 = load_context_bars()

    # Step 3: Generate configs
    print("\n[3/5] Generating configs...")
    configs = generate_all_configs()
    by_group = count_by_group(configs)
    print(f"  Total configs: {len(configs)}")
    print(f"  By group: {by_group}")
    assert len(configs) == 210, f"Expected 210 configs, got {len(configs)}"

    # Step 4: Smoke test (sequential in main process)
    print("\n[4/5] Running smoke test (5 RT values at SD=25, R04_MA2)...")
    smoke_ok = run_smoke_test(bars, ctx_250=ctx_250)

    if not smoke_ok:
        print("\n  *** SMOKE TEST FAILED — aborting full sweep ***")
        sys.exit(1)

    if args.smoke_only:
        print("\n  --smoke-only flag set. Skipping full sweep.")
        return

    # Step 5: Full sweep with multiprocessing
    print(f"\n[5/5] Running full sweep (210 configs, {args.workers} workers)...")
    summary_df = run_full_sweep(configs, bars, ctx_250=ctx_250, n_workers=args.workers)

    # Final validation
    print("\n" + "=" * 70)
    print("SELF-CHECK")
    print("=" * 70)
    cycle_log_files = [f for f in CYCLE_LOG_DIR.glob("*.csv") if "_incomplete" not in f.name]
    inc_files = list(CYCLE_LOG_DIR.glob("*_incomplete.csv"))
    print(f"  config_summary.csv rows: {len(summary_df)} (expected: 210)")
    print(f"  cycle_log CSVs: {len(cycle_log_files)} (expected: 210)")
    print(f"  incomplete CSVs: {len(inc_files)}")
    print(f"  All config_ids have cycle log: "
          f"{all((CYCLE_LOG_DIR / f'{cid}.csv').exists() for cid in summary_df['config_id'])}")

    # Aggregate stats
    total_inc = summary_df["incomplete_cycles"].sum()
    total_inc_pnl = summary_df["incomplete_unrealized_pnl"].sum()
    print(f"  Total incomplete cycles across all configs: {total_inc}")
    print(f"  Total incomplete unrealized PnL: {total_inc_pnl:.0f} ticks")

    # Group-level stats
    print("\n  By add group:")
    for group_tag in ["MA0", "R04_MA1", "R04_MA2", "R05_MA1", "R03_MA2", "R03_MA3"]:
        mask = summary_df["config_id"].str.contains(f"_{group_tag}_")
        group_df = summary_df[mask]
        if len(group_df) > 0:
            avg_sr = group_df["success_rate"].mean()
            total_adj = group_df["adjusted_net_pnl"].sum()
            print(f"    {group_tag:10s}: {len(group_df):3d} configs, "
                  f"avg SR={avg_sr:.1%}, total adj_net={total_adj:.0f}")

    # RT-level stats
    print("\n  By reversal target:")
    for rt in [0.5, 0.6, 0.7, 0.8, 1.0]:
        rt_tag = f"RT{int(rt * 100)}"
        mask = summary_df["config_id"].str.endswith(rt_tag)
        rt_df = summary_df[mask]
        if len(rt_df) > 0:
            avg_sr = rt_df["success_rate"].mean()
            avg_wr = rt_df["win_rate"].mean()
            total_adj = rt_df["adjusted_net_pnl"].sum()
            print(f"    RT={rt}: avg SR={avg_sr:.1%}, avg WR={avg_wr:.1%}, "
                  f"total adj_net={total_adj:.0f}")

    # Verify success_rate and win_rate are different
    sr_eq_wr = (summary_df["success_rate"] == summary_df["win_rate"]).all()
    print(f"\n  success_rate == win_rate everywhere: {sr_eq_wr} "
          f"(expected False — they measure different things)")

    print(f"\n  Cost ticks uniform: "
          f"{(summary_df['total_costs'] > 0).all() if len(summary_df) > 0 else 'N/A'}")
    print("\n  SWEEP COMPLETE.")


if __name__ == "__main__":
    main()
