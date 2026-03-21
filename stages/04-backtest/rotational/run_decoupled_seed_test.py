# archetype: rotational
"""Decoupled Seed Test — Small detection (seed_dist), large target (step_dist).

Usage:
    cd stages/04-backtest/rotational
    python run_decoupled_seed_test.py

Tests whether separating detection scale from trading scale preserves enough
parent displacement at entry for the fractal edge to translate into strategy SR.

9 configs: 3 SeedDist × 2 RT + 2 baselines + 1 scale-transfer test.
All use Option C (pullback seed for first trade, immediate re-seed after).
"""
from __future__ import annotations

import json
import sys
import time
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from config_schema import FrozenAnchorConfig
from context_tagger import tag_context
from rotation_simulator import run_pullback_simulation

COST_TICKS = 2.0
TICK_SIZE = 0.25

_TICK_DIR = _SCRIPT_DIR.parents[1] / "01-data" / "data" / "bar_data" / "tick"
P1_DATA_PATH = _TICK_DIR / "NQ_BarData_1tick_rot_P1.csv"
P1_CONTEXT_PATH = _TICK_DIR / "NQ_BarData_250tick_rot_P1.csv"

OUTPUT_DIR = _SCRIPT_DIR / "decoupled_seed_test"
CYCLE_LOG_DIR = OUTPUT_DIR / "cycle_logs"
MISSED_DIR = OUTPUT_DIR / "missed_entries"

PB_SUMMARY = _SCRIPT_DIR / "pullback_test" / "config_summary.csv"

P1_START = pd.Timestamp("2025-09-21")
P1_END = pd.Timestamp("2025-12-17")
RTH_START_SEC = 9 * 3600 + 30 * 60
RTH_END_SEC = 16 * 3600 + 15 * 60


# ---------------------------------------------------------------------------
# Data loading (same as other test runners)
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

    # SeedDist sweep at SD=40
    for seed in [10, 15, 20]:
        for rt in [0.8, 1.0]:
            ad = round(seed * 0.4, 1)
            configs.append(FrozenAnchorConfig(
                config_id=f"DS_SD40_SEED{seed}_AD{int(ad)}_RT{int(rt*100)}",
                step_dist=40.0,
                add_dist=ad,
                max_adds=0,
                reversal_target=rt,
                cost_ticks=COST_TICKS,
                entry_mode="pullback",
                reentry_mode="C",
                seed_dist=float(seed),
            ))

    # Baselines: SeedDist = StepDist (same as pullback test Option C)
    for rt in [0.8, 1.0]:
        configs.append(FrozenAnchorConfig(
            config_id=f"DS_SD40_SEED40_AD16_RT{int(rt*100)}",
            step_dist=40.0,
            add_dist=16.0,
            max_adds=0,
            reversal_target=rt,
            cost_ticks=COST_TICKS,
            entry_mode="pullback",
            reentry_mode="C",
            seed_dist=40.0,
        ))

    # Scale transfer: SD=25 with small seed
    configs.append(FrozenAnchorConfig(
        config_id="DS_SD25_SEED10_AD4_RT80",
        step_dist=25.0,
        add_dist=4.0,
        max_adds=0,
        reversal_target=0.8,
        cost_ticks=COST_TICKS,
        entry_mode="pullback",
        reentry_mode="C",
        seed_dist=10.0,
    ))

    return configs


# ---------------------------------------------------------------------------
# Per-config summary
# ---------------------------------------------------------------------------

def compute_summary(
    cycles_df: pd.DataFrame,
    incomplete_df: pd.DataFrame,
    missed_df: pd.DataFrame,
    config: FrozenAnchorConfig,
) -> dict:
    n = len(cycles_df)
    has_et = "exit_type" in cycles_df.columns and n > 0

    if n == 0:
        return _empty(config, incomplete_df, missed_df)

    net_pnl = cycles_df["pnl_ticks_net"]
    gross_pnl = cycles_df["pnl_ticks_gross"]
    wins = cycles_df[net_pnl > 0]
    losses = cycles_df[net_pnl <= 0]

    total_net = net_pnl.sum()
    cumulative = net_pnl.cumsum()
    max_dd = abs((cumulative - cumulative.cummax()).min()) if len(cumulative) > 0 else 0.0

    success_count = int((cycles_df["exit_type"] == "SUCCESS").sum()) if has_et else 0
    failure_count = int((cycles_df["exit_type"] == "FAILURE").sum()) if has_et else 0
    sr = success_count / n if n > 0 else 0.0

    # First vs later cycle SR
    first_sr = later_sr = 0.0
    if has_et and "cycle_day_seq" in cycles_df.columns:
        fm = cycles_df["cycle_day_seq"] == 1
        lm = cycles_df["cycle_day_seq"] > 1
        if fm.any():
            first_sr = (cycles_df.loc[fm, "exit_type"] == "SUCCESS").mean()
        if lm.any():
            later_sr = (cycles_df.loc[lm, "exit_type"] == "SUCCESS").mean()

    # Remaining to parent target (first cycles only)
    med_remaining = np.nan
    if "remaining_to_parent_target" in cycles_df.columns:
        rtp = cycles_df.loc[
            (cycles_df["cycle_day_seq"] == 1) &
            (cycles_df["remaining_to_parent_target"].notna()),
            "remaining_to_parent_target"
        ]
        if len(rtp) > 0:
            med_remaining = round(float(rtp.median()), 2)

    # Fractal-aligned completion rate (first cycles reaching parent target)
    fractal_cr = np.nan
    if "remaining_to_parent_target" in cycles_df.columns and "mfe_points" in cycles_df.columns:
        first_pb = cycles_df[
            (cycles_df["cycle_day_seq"] == 1) &
            (cycles_df["remaining_to_parent_target"].notna()) &
            (cycles_df["entry_type"] == "PULLBACK")
        ]
        if len(first_pb) > 0:
            reached = first_pb["mfe_points"] >= first_pb["remaining_to_parent_target"]
            fractal_cr = round(float(reached.mean()), 4)

    # Failure cascade
    faf = 0
    if has_et:
        et = cycles_df["exit_type"].values
        for k in range(1, len(et)):
            if et[k] == "FAILURE" and et[k - 1] == "FAILURE":
                faf += 1

    inc_count = len(incomplete_df)
    inc_pnl = round(incomplete_df["unrealized_pnl_ticks"].sum(), 4) if not incomplete_df.empty else 0.0
    missed_count = len(missed_df)
    total_opp = n + missed_count
    missed_pct = missed_count / total_opp if total_opp > 0 else 0.0
    missed_hyp = round(missed_df["hypothetical_immediate_pnl"].sum(), 4) if not missed_df.empty else 0.0

    # Pullback diagnostics
    avg_confirm = avg_depth = avg_hwm = 0.0
    if "confirming_duration_bars" in cycles_df.columns:
        pb = cycles_df[cycles_df["entry_type"] == "PULLBACK"]
        if len(pb) > 0:
            avg_confirm = round(pb["confirming_duration_bars"].mean(), 1)
            avg_depth = round(pb["pullback_depth_pct"].mean(), 2)
            avg_hwm = round(pb["hwm_at_entry"].mean(), 2)

    return {
        "config_id": config.config_id,
        "step_dist": config.step_dist,
        "seed_dist": config.seed_dist,
        "add_dist": config.add_dist,
        "reversal_target": config.reversal_target,
        "cycle_count": n,
        "success_count": success_count,
        "failure_count": failure_count,
        "success_rate": round(sr, 4),
        "win_count": len(wins),
        "loss_count": len(losses),
        "win_rate": round(len(wins) / n, 4),
        "gross_pnl": round(gross_pnl.sum(), 4),
        "net_pnl": round(total_net, 4),
        "total_costs": round(gross_pnl.sum() - total_net, 4),
        "max_drawdown_ticks": round(max_dd, 4),
        "adjusted_net_pnl": round(total_net + inc_pnl, 4),
        "first_cycle_success_rate": round(first_sr, 4),
        "later_cycle_success_rate": round(later_sr, 4),
        "med_remaining_to_parent": med_remaining,
        "fractal_aligned_cr": fractal_cr,
        "failure_after_failure": faf,
        "incomplete_cycles": inc_count,
        "incomplete_unrealized_pnl": inc_pnl,
        "missed_entries": missed_count,
        "missed_pct": round(missed_pct, 4),
        "missed_hypothetical_pnl": missed_hyp,
        "avg_confirming_duration_bars": avg_confirm,
        "avg_pullback_depth_pct": avg_depth,
        "avg_hwm_at_entry": avg_hwm,
    }


def _empty(config, incomplete_df, missed_df):
    inc_pnl = round(incomplete_df["unrealized_pnl_ticks"].sum(), 4) if not incomplete_df.empty else 0.0
    return {
        "config_id": config.config_id,
        "step_dist": config.step_dist, "seed_dist": config.seed_dist,
        "add_dist": config.add_dist, "reversal_target": config.reversal_target,
        "cycle_count": 0, "success_count": 0, "failure_count": 0, "success_rate": 0.0,
        "win_count": 0, "loss_count": 0, "win_rate": 0.0,
        "gross_pnl": 0.0, "net_pnl": 0.0, "total_costs": 0.0,
        "max_drawdown_ticks": 0.0, "adjusted_net_pnl": inc_pnl,
        "first_cycle_success_rate": 0.0, "later_cycle_success_rate": 0.0,
        "med_remaining_to_parent": np.nan, "fractal_aligned_cr": np.nan,
        "failure_after_failure": 0,
        "incomplete_cycles": len(incomplete_df), "incomplete_unrealized_pnl": inc_pnl,
        "missed_entries": len(missed_df), "missed_pct": 0.0, "missed_hypothetical_pnl": 0.0,
        "avg_confirming_duration_bars": 0.0, "avg_pullback_depth_pct": 0.0, "avg_hwm_at_entry": 0.0,
    }


# ---------------------------------------------------------------------------
# Random walk prediction
# ---------------------------------------------------------------------------

def rw_pred(rt: float) -> float:
    return 1.0 / (rt + 1.0)


# ---------------------------------------------------------------------------
# Reports
# ---------------------------------------------------------------------------

def generate_comparison_table(summaries: list[dict]) -> str:
    lines = [
        "# Decoupled Seed Test — Comparison Table",
        f"**Date:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "## SeedDist Effect on First-Cycle SR and Remaining Displacement",
        "",
        "| SeedDist | SD | RT | First SR | RW Pred | Delta | Med Remaining | Fractal CR | Cycles | Adj Net |",
        "|----------|-----|-----|---------|---------|-------|--------------|------------|--------|---------|",
    ]
    for s in summaries:
        rw = rw_pred(s["reversal_target"])
        delta = s["first_cycle_success_rate"] - rw
        lines.append(
            f"| {s['seed_dist']:.0f} | {s['step_dist']:.0f} | {s['reversal_target']} "
            f"| {s['first_cycle_success_rate']:.1%} | {rw:.1%} | {delta:+.1%} "
            f"| {s['med_remaining_to_parent']} pts "
            f"| {s['fractal_aligned_cr']:.1%} " if not np.isnan(s.get('fractal_aligned_cr', np.nan)) else f"| n/a "
            f"| {s['cycle_count']:,} | {s['adjusted_net_pnl']:.0f} |"
        )

    lines.extend(["", "## Later-Cycle SR (Immediate Re-seed — SeedDist Irrelevant)", ""])
    lines.append("| Config | Later SR | RW Pred | Delta |")
    lines.append("|--------|---------|---------|-------|")
    for s in summaries:
        rw = rw_pred(s["reversal_target"])
        delta = s["later_cycle_success_rate"] - rw
        lines.append(
            f"| {s['config_id']} | {s['later_cycle_success_rate']:.1%} "
            f"| {rw:.1%} | {delta:+.1%} |"
        )

    return "\n".join(lines)


def generate_analysis(summaries: list[dict], all_cycles: pd.DataFrame) -> str:
    lines = [
        "# Decoupled Seed Analysis",
        f"**Date:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "",
    ]

    # 1. Remaining displacement by SeedDist
    lines.append("## Remaining Displacement by SeedDist")
    lines.append("")
    lines.append("| Config | SeedDist | Med Remaining | P25 | P75 |")
    lines.append("|--------|----------|--------------|-----|-----|")
    for cfg_id in sorted(all_cycles["config_id"].unique()):
        c = all_cycles[(all_cycles["config_id"] == cfg_id) &
                        (all_cycles["cycle_day_seq"] == 1) &
                        (all_cycles["remaining_to_parent_target"].notna())]
        if len(c) > 0:
            sd_val = c["step_dist"].iloc[0]
            # Extract seed_dist from config_id
            rtp = c["remaining_to_parent_target"]
            lines.append(
                f"| {cfg_id} | see id | {rtp.median():.1f} "
                f"| {rtp.quantile(0.25):.1f} | {rtp.quantile(0.75):.1f} |"
            )
    lines.append("")

    # 2. Fractal-aligned completion by SeedDist
    lines.append("## Fractal-Aligned Completion Rate (First Cycles)")
    lines.append("")
    lines.append("| Config | First Cycles | Reached Parent | CR |")
    lines.append("|--------|-------------|----------------|------|")
    for cfg_id in sorted(all_cycles["config_id"].unique()):
        first_pb = all_cycles[
            (all_cycles["config_id"] == cfg_id) &
            (all_cycles["cycle_day_seq"] == 1) &
            (all_cycles["entry_type"] == "PULLBACK") &
            (all_cycles["remaining_to_parent_target"].notna())
        ]
        if len(first_pb) > 0:
            reached = first_pb["mfe_points"] >= first_pb["remaining_to_parent_target"]
            lines.append(
                f"| {cfg_id} | {len(first_pb)} | {int(reached.sum())} "
                f"| {reached.mean():.1%} |"
            )
    lines.append("")

    # 3. Pullback depth distribution by SeedDist
    lines.append("## Pullback Depth Distribution (First Cycles)")
    lines.append("")
    lines.append("| Config | Mean Depth | Median Depth | P25 | P75 |")
    lines.append("|--------|-----------|-------------|-----|-----|")
    for cfg_id in sorted(all_cycles["config_id"].unique()):
        pb = all_cycles[
            (all_cycles["config_id"] == cfg_id) &
            (all_cycles["entry_type"] == "PULLBACK")
        ]
        if len(pb) > 0:
            d = pb["pullback_depth_pct"].dropna()
            if len(d) > 0:
                lines.append(
                    f"| {cfg_id} | {d.mean():.1f}% | {d.median():.1f}% "
                    f"| {d.quantile(0.25):.1f}% | {d.quantile(0.75):.1f}% |"
                )
    lines.append("")

    # 4. Cycle count comparison
    lines.append("## Cycle Count by SeedDist")
    lines.append("")
    lines.append("| Config | Total Cycles | First Cycles | Later Cycles | Missed |")
    lines.append("|--------|-------------|-------------|-------------|--------|")
    for s in summaries:
        first_n = 0
        c = all_cycles[all_cycles["config_id"] == s["config_id"]]
        if len(c) > 0:
            first_n = int((c["cycle_day_seq"] == 1).sum())
        later_n = s["cycle_count"] - first_n
        lines.append(
            f"| {s['config_id']} | {s['cycle_count']:,} | {first_n} "
            f"| {later_n:,} | {s['missed_entries']} |"
        )
    lines.append("")

    # 5. First-cycle SR by remaining_to_parent quartile (across all configs)
    lines.append("## First-Cycle SR by Remaining-to-Parent Quartile (All Configs Pooled)")
    lines.append("")
    first_all = all_cycles[
        (all_cycles["cycle_day_seq"] == 1) &
        (all_cycles["entry_type"] == "PULLBACK") &
        (all_cycles["remaining_to_parent_target"].notna())
    ].copy()
    if len(first_all) > 10:
        first_all["rem_q"] = pd.qcut(first_all["remaining_to_parent_target"], 4,
                                      labels=["Q1 (least)", "Q2", "Q3", "Q4 (most)"],
                                      duplicates="drop")
        lines.append("| Quartile | Count | SR | Med Remaining |")
        lines.append("|----------|-------|-----|--------------|")
        for q in first_all["rem_q"].cat.categories:
            qdf = first_all[first_all["rem_q"] == q]
            if len(qdf) > 0:
                q_sr = (qdf["exit_type"] == "SUCCESS").mean()
                med_r = qdf["remaining_to_parent_target"].median()
                lines.append(f"| {q} | {len(qdf)} | {q_sr:.1%} | {med_r:.1f} pts |")
    lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------

def run_all(configs, bars, ctx_250):
    CYCLE_LOG_DIR.mkdir(parents=True, exist_ok=True)
    MISSED_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    summaries = []
    all_parts = []

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

        summary = compute_summary(cycles, incomplete, missed, cfg)
        summaries.append(summary)

        cycles.to_csv(CYCLE_LOG_DIR / f"{cfg.config_id}.csv", index=False)
        if not incomplete.empty:
            incomplete.to_csv(CYCLE_LOG_DIR / f"{cfg.config_id}_incomplete.csv", index=False)
        if not missed.empty:
            missed.to_csv(MISSED_DIR / f"{cfg.config_id}_missed.csv", index=False)
        if not cycles.empty:
            all_parts.append(cycles)

        sr = summary["success_rate"]
        fsr = summary["first_cycle_success_rate"]
        adj = summary["adjusted_net_pnl"]
        mr = summary["med_remaining_to_parent"]
        print(f"({summary['cycle_count']} cyc, SR={sr:.1%}, 1st={fsr:.1%}, "
              f"rem={mr}, adj={adj:.0f}, {elapsed:.1f}s)")

    all_cycles = pd.concat(all_parts, ignore_index=True) if all_parts else pd.DataFrame()
    return summaries, all_cycles


def main():
    print("=" * 70)
    print("DECOUPLED SEED TEST (1-tick, sequential)")
    print("=" * 70)

    print("\n[1/4] Loading P1 1-tick bar data...")
    bars = load_p1_bars()

    print("\n[2/4] Pre-computing context tags...")
    ctx_250 = load_context_bars()

    print("\n[3/4] Generating configs...")
    configs = generate_configs()
    print(f"  Total configs: {len(configs)}")
    for c in configs:
        print(f"    {c.config_id}: SD={c.step_dist}, SEED={c.seed_dist}, "
              f"AD={c.add_dist}, RT={c.reversal_target}")
    assert len(configs) == 9, f"Expected 9 configs, got {len(configs)}"

    print("\n[4/4] Running all 9 configs...")
    t_start = time.time()
    summaries, all_cycles = run_all(configs, bars, ctx_250)
    total_time = time.time() - t_start
    print(f"\n  All 9 configs complete in {total_time:.0f}s ({total_time/60:.1f}min)")

    # Save summary
    summary_df = pd.DataFrame(summaries)
    summary_df.to_csv(OUTPUT_DIR / "config_summary.csv", index=False)
    print(f"  config_summary.csv: {len(summary_df)} rows")

    # Generate reports
    comparison = generate_comparison_table(summaries)
    (OUTPUT_DIR / "comparison_table.md").write_text(comparison, encoding="utf-8")
    print(f"  comparison_table.md saved")

    analysis = generate_analysis(summaries, all_cycles)
    (OUTPUT_DIR / "decoupled_seed_analysis.md").write_text(analysis, encoding="utf-8")
    print(f"  decoupled_seed_analysis.md saved")

    # Metadata
    metadata = {
        "run_timestamp": datetime.now().isoformat(),
        "strategy": "frozen_anchor_decoupled_seed",
        "total_configs": len(configs),
        "total_runtime_seconds": round(total_time, 1),
        "cost_ticks": COST_TICKS,
        "entry_mode": "pullback",
        "reentry_mode": "C",
    }
    with open(OUTPUT_DIR / "sweep_metadata.json", "w") as f:
        json.dump(metadata, f, indent=2)

    # Self-check
    print("\n" + "=" * 70)
    print("SELF-CHECK")
    print("=" * 70)
    for s in summaries:
        rw = rw_pred(s["reversal_target"])
        delta = s["first_cycle_success_rate"] - rw
        print(f"  {s['config_id']}: {s['cycle_count']} cyc, "
              f"1st_SR={s['first_cycle_success_rate']:.1%} (delta={delta:+.1%}), "
              f"later_SR={s['later_cycle_success_rate']:.1%}, "
              f"rem={s['med_remaining_to_parent']}, adj={s['adjusted_net_pnl']:.0f}")

    print("\n  TEST COMPLETE.")


if __name__ == "__main__":
    main()
