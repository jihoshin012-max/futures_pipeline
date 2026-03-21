# archetype: rotational
"""Pullback Entry Test — 9 configs (3 SD/RT × 3 re-entry options) on P1 1-tick data.

Usage:
    cd stages/04-backtest/rotational
    python run_pullback_test.py [--workers 4]

Tests whether a child-scale pullback entry captures the fractal 80% completion
edge that immediate entry misses.  Compares directly against frozen-anchor
baseline (immediate entry) from frozen_anchor_sweep/config_summary.csv.
"""
from __future__ import annotations

import json
import argparse
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from config_schema import FrozenAnchorConfig
from context_tagger import tag_context
from rotation_simulator import run_pullback_simulation

# ---------------------------------------------------------------------------
# Constants (shared with run_fa_sweep.py)
# ---------------------------------------------------------------------------
COST_TICKS = 2.0
TICK_SIZE = 0.25

_TICK_DIR = _SCRIPT_DIR.parents[1] / "01-data" / "data" / "bar_data" / "tick"
P1_DATA_PATH = _TICK_DIR / "NQ_BarData_1tick_rot_P1.csv"
P1_CONTEXT_PATH = _TICK_DIR / "NQ_BarData_250tick_rot_P1.csv"

OUTPUT_DIR = _SCRIPT_DIR / "pullback_test"
CYCLE_LOG_DIR = OUTPUT_DIR / "cycle_logs"
MISSED_DIR = OUTPUT_DIR / "missed_entries"

FA_SWEEP_SUMMARY = _SCRIPT_DIR / "frozen_anchor_sweep" / "config_summary.csv"

P1_START = pd.Timestamp("2025-09-21")
P1_END = pd.Timestamp("2025-12-17")
RTH_START_SEC = 9 * 3600 + 30 * 60
RTH_END_SEC = 16 * 3600 + 15 * 60


# ---------------------------------------------------------------------------
# Data loading (identical to run_fa_sweep.py)
# ---------------------------------------------------------------------------

def load_p1_bars() -> pd.DataFrame:
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
    dates = df["datetime"].dt.normalize()
    df = df[(dates >= P1_START) & (dates <= P1_END)].copy()
    time_sec = df["datetime"].dt.hour * 3600 + df["datetime"].dt.minute * 60 + df["datetime"].dt.second
    df = df[(time_sec >= RTH_START_SEC) & (time_sec < RTH_END_SEC)].copy()
    df = df.reset_index(drop=True)
    trading_days = df["datetime"].dt.date.nunique()
    print(f"  Total rows (RTH, P1): {len(df):,}, {trading_days} trading days")
    return df


def load_context_bars() -> pd.DataFrame:
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
# Config generation — 9 configs
# ---------------------------------------------------------------------------

def generate_configs() -> list[FrozenAnchorConfig]:
    configs = []
    param_sets = [
        (40.0, 16.0, 0.8, "SD40_RT80"),
        (35.0, 14.0, 1.0, "SD35_RT100"),
        (25.0, 10.0, 0.8, "SD25_RT80"),
    ]
    for sd, ad, rt, label in param_sets:
        for option in ["A", "B", "C"]:
            configs.append(FrozenAnchorConfig(
                config_id=f"PB_{label}_OPT{option}",
                step_dist=sd,
                add_dist=ad,
                max_adds=0,
                reversal_target=rt,
                cost_ticks=COST_TICKS,
                entry_mode="pullback",
                reentry_mode=option,
            ))
    return configs


# ---------------------------------------------------------------------------
# Per-config summary
# ---------------------------------------------------------------------------

def compute_pb_summary(
    cycles_df: pd.DataFrame,
    incomplete_df: pd.DataFrame,
    missed_df: pd.DataFrame,
    config: FrozenAnchorConfig,
) -> dict:
    n_cycles = len(cycles_df)

    if n_cycles == 0:
        return {
            "config_id": config.config_id,
            "step_dist": config.step_dist, "add_dist": config.add_dist,
            "max_adds": config.max_adds, "reversal_target": config.reversal_target,
            "reentry_mode": config.reentry_mode,
            "cycle_count": 0, "success_count": 0, "failure_count": 0,
            "success_rate": 0.0, "win_count": 0, "loss_count": 0, "win_rate": 0.0,
            "gross_pnl": 0.0, "net_pnl": 0.0, "total_costs": 0.0,
            "avg_win_net": 0.0, "avg_loss_net": 0.0,
            "max_drawdown_ticks": 0.0, "profit_per_dd": 0.0,
            "avg_cycle_duration_bars": 0.0,
            "failure_after_failure": 0,
            "incomplete_cycles": len(incomplete_df),
            "incomplete_unrealized_pnl": round(incomplete_df["unrealized_pnl_ticks"].sum(), 4) if not incomplete_df.empty else 0.0,
            "adjusted_net_pnl": 0.0,
            "missed_entries": len(missed_df),
            "missed_pct": 0.0,
            "missed_hypothetical_pnl": round(missed_df["hypothetical_immediate_pnl"].sum(), 4) if not missed_df.empty else 0.0,
            "avg_confirming_duration_bars": 0.0,
            "avg_pullback_depth_pct": 0.0,
            "avg_hwm_at_entry": 0.0,
            "runaway_pct": 0.0,
            "first_cycle_success_rate": 0.0,
            "later_cycle_success_rate": 0.0,
            "avg_progress_hwm_success": 0.0,
            "avg_progress_hwm_failure": 0.0,
        }

    net_pnl = cycles_df["pnl_ticks_net"]
    gross_pnl = cycles_df["pnl_ticks_gross"]
    wins = cycles_df[net_pnl > 0]
    losses = cycles_df[net_pnl <= 0]

    # Drawdown
    cumulative = net_pnl.cumsum()
    max_dd = abs((cumulative - cumulative.cummax()).min()) if len(cumulative) > 0 else 0.0
    total_net = net_pnl.sum()
    profit_per_dd = total_net / max_dd if max_dd > 0 else (999.0 if total_net > 0 else 0.0)

    # Success/failure counts
    has_exit_type = "exit_type" in cycles_df.columns
    success_count = int((cycles_df["exit_type"] == "SUCCESS").sum()) if has_exit_type else 0
    failure_count = int((cycles_df["exit_type"] == "FAILURE").sum()) if has_exit_type else 0
    success_rate = success_count / n_cycles if n_cycles > 0 else 0.0

    # Failure cascade
    failure_after_failure = 0
    if has_exit_type:
        et = cycles_df["exit_type"].values
        for k in range(1, len(et)):
            if et[k] == "FAILURE" and et[k - 1] == "FAILURE":
                failure_after_failure += 1

    # Incomplete
    inc_count = len(incomplete_df)
    inc_pnl = round(incomplete_df["unrealized_pnl_ticks"].sum(), 4) if not incomplete_df.empty else 0.0
    adjusted_net = round(total_net + inc_pnl, 4)

    # Missed
    missed_count = len(missed_df)
    total_opportunities = n_cycles + missed_count
    missed_pct = missed_count / total_opportunities if total_opportunities > 0 else 0.0
    missed_hyp = round(missed_df["hypothetical_immediate_pnl"].sum(), 4) if not missed_df.empty else 0.0

    # Pullback diagnostics
    avg_confirm = 0.0
    avg_depth = 0.0
    avg_hwm = 0.0
    runaway_pct = 0.0
    if "confirming_duration_bars" in cycles_df.columns:
        pb_mask = cycles_df["entry_type"] == "PULLBACK"
        pb_df = cycles_df[pb_mask]
        if len(pb_df) > 0:
            avg_confirm = round(pb_df["confirming_duration_bars"].mean(), 1)
            avg_depth = round(pb_df["pullback_depth_pct"].mean(), 2)
            avg_hwm = round(pb_df["hwm_at_entry"].mean(), 2)
            runaway_pct = round(pb_df["runaway_flag"].mean() * 100, 1)

    # First vs later success rates
    first_sr = 0.0
    later_sr = 0.0
    if has_exit_type and "cycle_day_seq" in cycles_df.columns:
        first_mask = cycles_df["cycle_day_seq"] == 1
        later_mask = cycles_df["cycle_day_seq"] > 1
        if first_mask.any():
            first_sr = round((cycles_df.loc[first_mask, "exit_type"] == "SUCCESS").mean(), 4)
        if later_mask.any():
            later_sr = round((cycles_df.loc[later_mask, "exit_type"] == "SUCCESS").mean(), 4)

    # Progress HWM
    avg_hwm_s = 0.0
    avg_hwm_f = 0.0
    if has_exit_type and "progress_hwm" in cycles_df.columns:
        s_mask = cycles_df["exit_type"] == "SUCCESS"
        f_mask = cycles_df["exit_type"] == "FAILURE"
        if s_mask.any():
            avg_hwm_s = round(cycles_df.loc[s_mask, "progress_hwm"].mean(), 2)
        if f_mask.any():
            avg_hwm_f = round(cycles_df.loc[f_mask, "progress_hwm"].mean(), 2)

    return {
        "config_id": config.config_id,
        "step_dist": config.step_dist,
        "add_dist": config.add_dist,
        "max_adds": config.max_adds,
        "reversal_target": config.reversal_target,
        "reentry_mode": config.reentry_mode,
        "cycle_count": n_cycles,
        "success_count": success_count,
        "failure_count": failure_count,
        "success_rate": round(success_rate, 4),
        "win_count": len(wins),
        "loss_count": len(losses),
        "win_rate": round(len(wins) / n_cycles, 4),
        "gross_pnl": round(gross_pnl.sum(), 4),
        "net_pnl": round(total_net, 4),
        "total_costs": round(gross_pnl.sum() - total_net, 4),
        "avg_win_net": round(wins["pnl_ticks_net"].mean(), 4) if len(wins) > 0 else 0.0,
        "avg_loss_net": round(losses["pnl_ticks_net"].mean(), 4) if len(losses) > 0 else 0.0,
        "max_drawdown_ticks": round(max_dd, 4),
        "profit_per_dd": round(profit_per_dd, 4),
        "avg_cycle_duration_bars": round(cycles_df["duration_bars"].mean(), 2),
        "failure_after_failure": failure_after_failure,
        "incomplete_cycles": inc_count,
        "incomplete_unrealized_pnl": inc_pnl,
        "adjusted_net_pnl": adjusted_net,
        "missed_entries": missed_count,
        "missed_pct": round(missed_pct, 4),
        "missed_hypothetical_pnl": missed_hyp,
        "avg_confirming_duration_bars": avg_confirm,
        "avg_pullback_depth_pct": avg_depth,
        "avg_hwm_at_entry": avg_hwm,
        "runaway_pct": runaway_pct,
        "first_cycle_success_rate": first_sr,
        "later_cycle_success_rate": later_sr,
        "avg_progress_hwm_success": avg_hwm_s,
        "avg_progress_hwm_failure": avg_hwm_f,
    }


# ---------------------------------------------------------------------------
# Load frozen-anchor baseline
# ---------------------------------------------------------------------------

def load_baseline() -> dict[str, dict]:
    """Load frozen-anchor immediate-entry results for comparison."""
    if not FA_SWEEP_SUMMARY.exists():
        print(f"  WARNING: baseline not found at {FA_SWEEP_SUMMARY}")
        return {}

    df = pd.read_csv(FA_SWEEP_SUMMARY)
    baseline = {}
    # Map pullback configs to their frozen-anchor MA0 counterparts
    mapping = {
        "SD40_RT80": "FA_SD40_MA0_RT80",
        "SD35_RT100": "FA_SD35_MA0_RT100",
        "SD25_RT80": "FA_SD25_MA0_RT80",
    }
    for label, fa_id in mapping.items():
        row = df[df["config_id"] == fa_id]
        if not row.empty:
            baseline[label] = row.iloc[0].to_dict()
    return baseline


# ---------------------------------------------------------------------------
# Random walk prediction
# ---------------------------------------------------------------------------

def rw_prediction(rt: float) -> float:
    """Random walk first-passage success probability: SD / (RT×SD + SD) = 1 / (RT + 1)."""
    return 1.0 / (rt + 1.0)


# ---------------------------------------------------------------------------
# Comparison table
# ---------------------------------------------------------------------------

def generate_comparison_table(summaries: list[dict], baseline: dict[str, dict]) -> str:
    lines = [
        "# Pullback Entry Test — Comparison Table",
        f"**Date:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "## Side-by-Side: Immediate vs Pullback Entry",
        "",
        "| Config | Option | SR | RW Pred | Delta | Cycles | Gross PnL | Adj Net | Missed | Missed% |",
        "|--------|--------|-----|---------|-------|--------|----------|---------|--------|---------|",
    ]

    # Group by parameter set
    for label in ["SD40_RT80", "SD35_RT100", "SD25_RT80"]:
        bl = baseline.get(label)
        if bl:
            rt = bl.get("reversal_target", 1.0)
            rw = rw_prediction(rt)
            bl_sr = bl.get("success_rate", 0)
            bl_delta = bl_sr - rw
            bl_adj = bl.get("adjusted_net_pnl", bl.get("net_pnl", 0))
            lines.append(
                f"| {label} | Immediate | {bl_sr:.1%} | {rw:.1%} | {bl_delta:+.1%} "
                f"| {int(bl.get('cycle_count', 0)):,} | {bl.get('gross_pnl', 0):.0f} "
                f"| {bl_adj:.0f} | n/a | n/a |"
            )

        for s in summaries:
            if label in s["config_id"]:
                opt = s["reentry_mode"]
                rt = s["reversal_target"]
                rw = rw_prediction(rt)
                sr = s["success_rate"]
                delta = sr - rw
                opt_label = {"A": "A (rewatch)", "B": "B (confirm)", "C": "C (seed only)"}[opt]
                lines.append(
                    f"| {label} | {opt_label} | {sr:.1%} | {rw:.1%} | {delta:+.1%} "
                    f"| {s['cycle_count']:,} | {s['gross_pnl']:.0f} "
                    f"| {s['adjusted_net_pnl']:.0f} | {s['missed_entries']} "
                    f"| {s['missed_pct']:.1%} |"
                )
        lines.append("")

    # Option comparison summary
    lines.append("## Option Comparison Summary")
    lines.append("")
    lines.append("| Config | Best SR Option | Best Adj Net Option | Fewest Cascades |")
    lines.append("|--------|---------------|--------------------|-----------------| ")
    for label in ["SD40_RT80", "SD35_RT100", "SD25_RT80"]:
        opts = [s for s in summaries if label in s["config_id"]]
        if opts:
            best_sr = max(opts, key=lambda x: x["success_rate"])
            best_pnl = max(opts, key=lambda x: x["adjusted_net_pnl"])
            best_casc = min(opts, key=lambda x: x["failure_after_failure"])
            lines.append(
                f"| {label} | {best_sr['reentry_mode']} ({best_sr['success_rate']:.1%}) "
                f"| {best_pnl['reentry_mode']} ({best_pnl['adjusted_net_pnl']:.0f}) "
                f"| {best_casc['reentry_mode']} ({best_casc['failure_after_failure']}) |"
            )

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Pullback analysis
# ---------------------------------------------------------------------------

def generate_pullback_analysis(all_cycles: pd.DataFrame, summaries: list[dict]) -> str:
    lines = [
        "# Pullback Entry Analysis",
        f"**Date:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "",
    ]

    pb_mask = all_cycles["entry_type"] == "PULLBACK"
    pb = all_cycles[pb_mask].copy()

    if pb.empty:
        lines.append("No pullback entries found.")
        return "\n".join(lines)

    # 1. Pullback depth distribution
    lines.append("## Pullback Depth Distribution")
    lines.append("")
    depth = pb["pullback_depth_pct"].dropna()
    if len(depth) > 0:
        lines.append(f"- Count: {len(depth)}")
        lines.append(f"- Mean: {depth.mean():.1f}%")
        lines.append(f"- Median: {depth.median():.1f}%")
        lines.append(f"- P25: {depth.quantile(0.25):.1f}%")
        lines.append(f"- P75: {depth.quantile(0.75):.1f}%")
        lines.append(f"- Min: {depth.min():.1f}%, Max: {depth.max():.1f}%")
    lines.append("")

    # 2. SR by pullback depth quartile
    lines.append("## Success Rate by Pullback Depth Quartile")
    lines.append("")
    if len(depth) > 10 and "exit_type" in pb.columns:
        pb_with_depth = pb.dropna(subset=["pullback_depth_pct"]).copy()
        pb_with_depth["depth_q"] = pd.qcut(pb_with_depth["pullback_depth_pct"], 4,
                                            labels=["Q1 (shallow)", "Q2", "Q3", "Q4 (deep)"],
                                            duplicates="drop")
        lines.append("| Quartile | Count | SR | Avg Depth |")
        lines.append("|----------|-------|-----|-----------|")
        for q in pb_with_depth["depth_q"].cat.categories:
            qdf = pb_with_depth[pb_with_depth["depth_q"] == q]
            if len(qdf) > 0:
                q_sr = (qdf["exit_type"] == "SUCCESS").mean()
                q_depth = qdf["pullback_depth_pct"].mean()
                lines.append(f"| {q} | {len(qdf)} | {q_sr:.1%} | {q_depth:.1f}% |")
    lines.append("")

    # 3. Confirming duration distribution
    lines.append("## Confirming Duration Distribution")
    lines.append("")
    dur = pb["confirming_duration_bars"].dropna()
    if len(dur) > 0:
        lines.append(f"- Count: {len(dur)}")
        lines.append(f"- Median: {dur.median():.0f} bars")
        lines.append(f"- Mean: {dur.mean():.0f} bars")
        lines.append(f"- P25: {dur.quantile(0.25):.0f}, P75: {dur.quantile(0.75):.0f}")
    lines.append("")

    # 4. SR by confirming duration
    lines.append("## Success Rate by Confirming Duration")
    lines.append("")
    if len(dur) > 10 and "exit_type" in pb.columns:
        median_dur = dur.median()
        quick = pb[pb["confirming_duration_bars"] <= median_dur]
        slow = pb[pb["confirming_duration_bars"] > median_dur]
        q_sr = (quick["exit_type"] == "SUCCESS").mean() if len(quick) > 0 else 0
        s_sr = (slow["exit_type"] == "SUCCESS").mean() if len(slow) > 0 else 0
        lines.append(f"- Quick pullback (<= {median_dur:.0f} bars): SR = {q_sr:.1%} ({len(quick)} cycles)")
        lines.append(f"- Slow pullback (> {median_dur:.0f} bars): SR = {s_sr:.1%} ({len(slow)} cycles)")
    lines.append("")

    # 5. Runaway entries
    lines.append("## Runaway Entries (HWM > 2×StepDist)")
    lines.append("")
    if "runaway_flag" in pb.columns:
        runaway = pb[pb["runaway_flag"] == True]
        normal = pb[pb["runaway_flag"] == False]
        lines.append(f"- Runaway entries: {len(runaway)} ({len(runaway)/len(pb)*100:.1f}%)")
        if len(runaway) > 0 and "exit_type" in pb.columns:
            r_sr = (runaway["exit_type"] == "SUCCESS").mean()
            n_sr = (normal["exit_type"] == "SUCCESS").mean() if len(normal) > 0 else 0
            lines.append(f"- Runaway SR: {r_sr:.1%} vs Normal SR: {n_sr:.1%}")
    lines.append("")

    # 6. Failure cascade comparison
    lines.append("## Failure Cascade Rate by Option")
    lines.append("")
    lines.append("| Config | Option | Cycles | Failure-after-Failure | Cascade Rate |")
    lines.append("|--------|--------|--------|----------------------|--------------|")
    for s in summaries:
        n = s["cycle_count"]
        faf = s["failure_after_failure"]
        rate = faf / n if n > 0 else 0
        lines.append(f"| {s['config_id']} | {s['reentry_mode']} | {n} | {faf} | {rate:.1%} |")
    lines.append("")

    # 7. First cycle vs later cycle
    lines.append("## First Cycle vs Later Cycle Success Rate")
    lines.append("")
    lines.append("| Config | Option | First Cycle SR | Later Cycle SR |")
    lines.append("|--------|--------|---------------|----------------|")
    for s in summaries:
        lines.append(
            f"| {s['config_id']} | {s['reentry_mode']} "
            f"| {s['first_cycle_success_rate']:.1%} "
            f"| {s['later_cycle_success_rate']:.1%} |"
        )

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Run all configs
# ---------------------------------------------------------------------------

def run_all(
    configs: list[FrozenAnchorConfig],
    bars: pd.DataFrame,
    ctx_250: pd.DataFrame | None = None,
) -> tuple[list[dict], pd.DataFrame]:
    """Run all configs sequentially. Return summaries + combined cycle DataFrame."""
    CYCLE_LOG_DIR.mkdir(parents=True, exist_ok=True)
    MISSED_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    summaries: list[dict] = []
    all_cycles_parts: list[pd.DataFrame] = []

    for cfg in configs:
        print(f"\n  Running: {cfg.config_id} ...", end=" ", flush=True)
        t0 = time.time()
        result = run_pullback_simulation(cfg, bars, context_bars=None, tick_size=TICK_SIZE)
        elapsed = time.time() - t0

        cycles = result.cycles
        incomplete = result.incomplete_cycles
        missed = result.missed_entries

        if ctx_250 is not None and not cycles.empty:
            cycles = join_context_to_cycles(cycles, ctx_250)

        summary = compute_pb_summary(cycles, incomplete, missed, cfg)
        summaries.append(summary)

        # Save logs
        cycles.to_csv(CYCLE_LOG_DIR / f"{cfg.config_id}.csv", index=False)
        if not incomplete.empty:
            incomplete.to_csv(CYCLE_LOG_DIR / f"{cfg.config_id}_incomplete.csv", index=False)
        if not missed.empty:
            missed.to_csv(MISSED_DIR / f"{cfg.config_id}_missed.csv", index=False)

        if not cycles.empty:
            all_cycles_parts.append(cycles)

        sr = summary["success_rate"]
        n = summary["cycle_count"]
        adj = summary["adjusted_net_pnl"]
        m = summary["missed_entries"]
        print(f"({n} cyc, SR={sr:.1%}, adj_net={adj:.0f}, missed={m}, {elapsed:.1f}s)")

    all_cycles = pd.concat(all_cycles_parts, ignore_index=True) if all_cycles_parts else pd.DataFrame()
    return summaries, all_cycles


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Pullback Entry Test: 9 configs on P1 1-tick data")
    args = parser.parse_args()

    print("=" * 70)
    print("PULLBACK ENTRY TEST (1-tick, sequential)")
    print("=" * 70)

    # Step 1: Load data
    print("\n[1/4] Loading P1 1-tick bar data...")
    bars = load_p1_bars()

    print("\n[2/4] Pre-computing context tags on 250-tick reference bars...")
    ctx_250 = load_context_bars()

    # Step 2: Generate configs
    print("\n[3/4] Generating configs...")
    configs = generate_configs()
    print(f"  Total configs: {len(configs)}")
    for c in configs:
        print(f"    {c.config_id}: SD={c.step_dist}, AD={c.add_dist}, RT={c.reversal_target}, reentry={c.reentry_mode}")
    assert len(configs) == 9, f"Expected 9 configs, got {len(configs)}"

    # Step 3: Run all configs
    print("\n[4/4] Running all 9 configs...")
    t_start = time.time()
    summaries, all_cycles = run_all(configs, bars, ctx_250=ctx_250)
    total_time = time.time() - t_start
    print(f"\n  All 9 configs complete in {total_time:.0f}s ({total_time/60:.1f}min)")

    # Save config_summary.csv
    summary_df = pd.DataFrame(summaries)
    summary_df.to_csv(OUTPUT_DIR / "config_summary.csv", index=False)
    print(f"  config_summary.csv: {len(summary_df)} rows")

    # Load baseline for comparison
    print("\n  Loading frozen-anchor baseline for comparison...")
    baseline = load_baseline()
    if baseline:
        print(f"  Baseline loaded: {list(baseline.keys())}")
    else:
        print("  WARNING: no baseline found — comparison table will be incomplete")

    # Generate comparison table
    comparison = generate_comparison_table(summaries, baseline)
    (OUTPUT_DIR / "comparison_table.md").write_text(comparison, encoding="utf-8")
    print(f"  comparison_table.md saved")

    # Generate pullback analysis
    analysis = generate_pullback_analysis(all_cycles, summaries)
    (OUTPUT_DIR / "pullback_analysis.md").write_text(analysis, encoding="utf-8")
    print(f"  pullback_analysis.md saved")

    # Save metadata
    metadata = {
        "run_timestamp": datetime.now().isoformat(),
        "strategy": "frozen_anchor_pullback",
        "total_configs": len(configs),
        "total_runtime_seconds": round(total_time, 1),
        "cost_ticks": COST_TICKS,
        "entry_mode": "pullback",
        "reentry_modes": ["A", "B", "C"],
        "param_sets": ["SD40_RT80", "SD35_RT100", "SD25_RT80"],
    }
    with open(OUTPUT_DIR / "sweep_metadata.json", "w") as f:
        json.dump(metadata, f, indent=2)

    # Self-check
    print("\n" + "=" * 70)
    print("SELF-CHECK")
    print("=" * 70)
    cycle_files = list(CYCLE_LOG_DIR.glob("*.csv"))
    missed_files = list(MISSED_DIR.glob("*.csv"))
    print(f"  config_summary.csv rows: {len(summary_df)} (expected: 9)")
    print(f"  cycle_log CSVs: {len([f for f in cycle_files if '_incomplete' not in f.name])}")
    print(f"  missed_entry CSVs: {len(missed_files)}")
    print(f"  comparison_table.md: exists={( OUTPUT_DIR / 'comparison_table.md').exists()}")
    print(f"  pullback_analysis.md: exists={(OUTPUT_DIR / 'pullback_analysis.md').exists()}")

    for s in summaries:
        print(f"  {s['config_id']}: {s['cycle_count']} cycles, SR={s['success_rate']:.1%}, "
              f"adj_net={s['adjusted_net_pnl']:.0f}, missed={s['missed_entries']}")

    print("\n  TEST COMPLETE.")


if __name__ == "__main__":
    main()
