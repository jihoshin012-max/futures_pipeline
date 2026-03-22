# archetype: rotational
# STATUS: ONE-TIME
# PURPOSE: P2a replication validation of frozen-anchor SD40/RT0.8
# LAST RUN: 2026-03-21

"""P2a Replication Validation — Frozen-Anchor SD40/RT0.8 on holdout data.

Usage:
    cd stages/05-assessment/rotational/p2a_validation
    python run_p2a_validation.py

Runs frozen P1 parameters on P2a holdout (Dec 18, 2025 – Jan 30, 2026, 30 RTH days).
No parameter changes, no re-optimization. One shot.

⚠️ DO NOT RUN without explicit authorization — the holdout is consumed on first use.
"""
from __future__ import annotations

import json
import sys
import time
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

# Import from the backtest directory (simulator + config live there)
_BACKTEST_DIR = Path(__file__).resolve().parents[3] / "04-backtest" / "rotational"
if str(_BACKTEST_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKTEST_DIR))

from config_schema import FrozenAnchorConfig
from context_tagger import tag_context
from rotation_simulator import run_frozen_anchor_simulation

# === CONSTANTS ===
COST_TICKS = 2.0
TICK_SIZE = 0.25

_TICK_DIR = Path(__file__).resolve().parents[3] / "01-data" / "data" / "bar_data" / "tick"  # stages/01-data/...
P2_DATA_PATH = _TICK_DIR / "NQ_BarData_1tick_rot_P2.csv"
P2_CONTEXT_PATH = _TICK_DIR / "NQ_BarData_250tick_rot_P1.csv"  # 250-tick for context tags

OUTPUT_DIR = Path(__file__).resolve().parent
CYCLE_LOG_DIR = OUTPUT_DIR / "cycle_logs"

# P2a boundaries (determined by RTH trading day count: 30/30 split)
P2A_START = pd.Timestamp("2025-12-15")  # Inclusive (data starts Dec 18 RTH)
P2A_END = pd.Timestamp("2026-01-30")    # Inclusive (last P2a RTH day)

RTH_START_SEC = 9 * 3600 + 30 * 60   # 09:30
RTH_END_SEC = 16 * 3600 + 15 * 60    # 16:15

# P1 reference values for structural comparison
P1_REFERENCE = {
    "success_rate": 0.588,
    "first_cycle_sr": 0.661,
    "later_cycle_sr": 0.586,
    "failure_cascade_rate": 0.428,
    "avg_progress_hwm_failure": 30.8,
    "npf_net": 1.08,
    "adj_net_pnl": 12420,
    "cycle_count": 2389,
    "rw_sr_rt100": 0.494,
}


# === DATA LOADING ===

def load_p2a_bars() -> pd.DataFrame:
    """Load P2 1-tick data, filter to P2a date range + RTH."""
    print(f"Loading P2 1-tick bar data from: {P2_DATA_PATH}")

    header = pd.read_csv(P2_DATA_PATH, nrows=0)
    header.columns = header.columns.str.strip()
    needed = ["Date", "Time", "Open", "High", "Low", "Last"]
    col_indices = [list(header.columns).index(c) for c in needed]
    df = pd.read_csv(P2_DATA_PATH, usecols=col_indices, dtype={
        "Open": "float32", "High": "float32", "Low": "float32", "Last": "float32",
    })
    df.columns = df.columns.str.strip()
    df["datetime"] = pd.to_datetime(df["Date"].str.strip() + " " + df["Time"].str.strip())
    df.drop(columns=["Date", "Time"], inplace=True)

    # Filter to P2a date range
    dates = df["datetime"].dt.normalize()
    df = df[(dates >= P2A_START) & (dates <= P2A_END)].copy()

    # Filter to RTH
    time_sec = df["datetime"].dt.hour * 3600 + df["datetime"].dt.minute * 60 + df["datetime"].dt.second
    df = df[(time_sec >= RTH_START_SEC) & (time_sec < RTH_END_SEC)].copy()
    df = df.reset_index(drop=True)

    trading_days = df["datetime"].dt.date.nunique()
    mem_mb = df.memory_usage(deep=True).sum() / 1e6
    print(f"  Total rows (RTH, P2a): {len(df):,}")
    print(f"  Date range: {df['datetime'].iloc[0]} to {df['datetime'].iloc[-1]}")
    print(f"  RTH trading days: {trading_days}")
    print(f"  Memory: {mem_mb:.0f} MB")

    return df


def load_context_bars() -> pd.DataFrame:
    """Load 250-tick bars for context tagging.

    Uses P1 250-tick bars — context is computed from bar-level OHLC which
    is resolution-dependent but not date-dependent. The ATR/swing lookbacks
    use rolling windows that warm up within the session.
    """
    # Check if P2 250-tick exists, otherwise fall back to P1
    p2_ctx = _TICK_DIR / "NQ_BarData_250tick_rot_P2.csv"
    ctx_path = p2_ctx if p2_ctx.exists() else P2_CONTEXT_PATH

    print(f"Loading 250-tick context bars from: {ctx_path}")
    df = pd.read_csv(ctx_path)
    df.columns = df.columns.str.strip()
    df["datetime"] = pd.to_datetime(df["Date"].str.strip() + " " + df["Time"].str.strip())
    df.drop(columns=["Date", "Time"], inplace=True, errors="ignore")

    # Filter to P2a range + RTH
    dates = df["datetime"].dt.normalize()
    df = df[(dates >= P2A_START) & (dates <= P2A_END)].copy()
    time_sec = df["datetime"].dt.hour * 3600 + df["datetime"].dt.minute * 60 + df["datetime"].dt.second
    df = df[(time_sec >= RTH_START_SEC) & (time_sec < RTH_END_SEC)].copy()
    df = df.reset_index(drop=True)

    print(f"  250-tick context bars (P2a): {len(df):,}")
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


# === CONFIGS (FROZEN FROM P1) ===

def get_configs() -> list[FrozenAnchorConfig]:
    return [
        # Primary validation config
        FrozenAnchorConfig(
            config_id="P2A_VALIDATION",
            step_dist=40.0,
            add_dist=16.0,
            max_adds=0,
            reversal_target=0.8,
            cost_ticks=COST_TICKS,
            entry_mode="immediate",
        ),
        # Comparison: best add config from P1
        FrozenAnchorConfig(
            config_id="P2A_R03_MA2",
            step_dist=40.0,
            add_dist=12.0,
            max_adds=2,
            reversal_target=0.8,
            cost_ticks=COST_TICKS,
            entry_mode="immediate",
        ),
        # Random walk baseline: symmetric exits, zero cost
        FrozenAnchorConfig(
            config_id="P2A_RANDOM_WALK_CHECK",
            step_dist=40.0,
            add_dist=16.0,
            max_adds=0,
            reversal_target=1.0,
            cost_ticks=0.0,
            entry_mode="immediate",
        ),
    ]


# === PER-CONFIG SUMMARY ===

def compute_summary(cycles_df, incomplete_df, config):
    n = len(cycles_df)
    if n == 0:
        return {"config_id": config.config_id, "cycle_count": 0}

    net_pnl = cycles_df["pnl_ticks_net"]
    gross_pnl = cycles_df["pnl_ticks_gross"]
    wins = cycles_df[net_pnl > 0]
    losses = cycles_df[net_pnl <= 0]
    total_net = net_pnl.sum()

    # Drawdown
    cumulative = net_pnl.cumsum()
    max_dd = abs((cumulative - cumulative.cummax()).min())

    # Success/failure
    has_et = "exit_type" in cycles_df.columns
    success_count = int((cycles_df["exit_type"] == "SUCCESS").sum()) if has_et else 0
    failure_count = int((cycles_df["exit_type"] == "FAILURE").sum()) if has_et else 0
    sr = success_count / n

    # NPF
    net_wins = net_pnl[net_pnl > 0].sum()
    net_losses = net_pnl[net_pnl <= 0].sum()
    npf = net_wins / abs(net_losses) if net_losses != 0 else (999.0 if net_wins > 0 else 0.0)

    # First vs later SR
    first_sr = later_sr = 0.0
    if has_et and "cycle_day_seq" in cycles_df.columns:
        fm = cycles_df["cycle_day_seq"] == 1
        lm = cycles_df["cycle_day_seq"] > 1
        if fm.any():
            first_sr = (cycles_df.loc[fm, "exit_type"] == "SUCCESS").mean()
        if lm.any():
            later_sr = (cycles_df.loc[lm, "exit_type"] == "SUCCESS").mean()

    # Failure cascade
    faf = 0
    if has_et:
        et = cycles_df["exit_type"].values
        for k in range(1, len(et)):
            if et[k] == "FAILURE" and et[k - 1] == "FAILURE":
                faf += 1
    cascade_rate = faf / failure_count if failure_count > 0 else 0.0

    # Progress HWM for failures
    avg_hwm_fail = 0.0
    if has_et and "progress_hwm" in cycles_df.columns:
        fail_mask = cycles_df["exit_type"] == "FAILURE"
        if fail_mask.any():
            avg_hwm_fail = cycles_df.loc[fail_mask, "progress_hwm"].mean()

    # Incomplete
    inc_count = len(incomplete_df)
    inc_pnl = round(incomplete_df["unrealized_pnl_ticks"].sum(), 4) if not incomplete_df.empty else 0.0
    adj_net = round(total_net + inc_pnl, 4)

    # Incomplete PnL per day
    trading_days = cycles_df["start_time"].apply(lambda x: pd.Timestamp(x).date()).nunique() if n > 0 else 1
    inc_per_day = inc_pnl / trading_days if trading_days > 0 else 0.0

    # Equity curve data (cumulative PnL)
    eq_curve = cumulative.values.tolist()
    eq_min_idx = int(np.argmin(cumulative.values)) if len(cumulative) > 0 else 0
    eq_min_val = float(cumulative.min()) if len(cumulative) > 0 else 0.0

    return {
        "config_id": config.config_id,
        "step_dist": config.step_dist,
        "add_dist": config.add_dist,
        "max_adds": config.max_adds,
        "reversal_target": config.reversal_target,
        "cost_ticks": config.cost_ticks,
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
        "npf_net": round(npf, 4),
        "max_drawdown_ticks": round(max_dd, 4),
        "profit_per_dd": round(total_net / max_dd, 4) if max_dd > 0 else 999.0,
        "adjusted_net_pnl": adj_net,
        "first_cycle_sr": round(first_sr, 4),
        "later_cycle_sr": round(later_sr, 4),
        "failure_cascade_rate": round(cascade_rate, 4),
        "failure_after_failure": faf,
        "avg_progress_hwm_failure": round(avg_hwm_fail, 2),
        "incomplete_cycles": inc_count,
        "incomplete_unrealized_pnl": inc_pnl,
        "inc_pnl_per_day": round(inc_per_day, 2),
        "avg_cycle_duration_bars": round(cycles_df["duration_bars"].mean(), 2),
        "max_position": int(cycles_df["exit_position"].max()) if "exit_position" in cycles_df.columns else 1,
        "trading_days": trading_days,
        "eq_max_dd_cycle_idx": eq_min_idx,
        "eq_max_dd_value": round(eq_min_val, 2),
    }


# === VERDICT ===

def determine_verdict(primary, rw_check):
    """Apply pass/fail criteria. Returns (verdict, details)."""
    details = []
    all_pass = True

    # Criterion 1: SR above random walk by >= 1pp
    rw_pred = 1.0 / (primary["reversal_target"] + 1.0)  # 55.6% for RT=0.8
    delta = primary["success_rate"] - rw_pred
    if delta >= 0.025:
        details.append(f"1. SR above RW: PASS -- SR={primary['success_rate']:.1%}, RW={rw_pred:.1%}, Delta={delta:+.1%}")
    elif delta >= 0.01:
        details.append(f"1. SR above RW: NARROW PASS -- SR={primary['success_rate']:.1%}, RW={rw_pred:.1%}, Delta={delta:+.1%} (edge present but weaker than P1)")
    else:
        details.append(f"1. SR above RW: FAIL -- SR={primary['success_rate']:.1%}, RW={rw_pred:.1%}, Delta={delta:+.1%}")
        all_pass = False

    # Criterion 2: Adjusted net positive
    if primary["adjusted_net_pnl"] > 0:
        details.append(f"2. Adj net positive: PASS -- {primary['adjusted_net_pnl']:.0f} ticks")
    else:
        details.append(f"2. Adj net positive: FAIL -- {primary['adjusted_net_pnl']:.0f} ticks")
        all_pass = False

    # Criterion 3: Random walk baseline ~50%
    rw_sr = rw_check["success_rate"]
    rw_delta = abs(rw_sr - 0.50)
    if rw_delta <= 0.03:
        details.append(f"3. RW baseline valid: PASS -- RT=1.0 SR={rw_sr:.1%} (within +/-3pp of 50%)")
    else:
        details.append(f"3. RW baseline valid: FAIL -- RT=1.0 SR={rw_sr:.1%} (outside +/-3pp of 50%, market structure shifted)")
        all_pass = False

    verdict = "PASS" if all_pass else "FAIL"
    return verdict, details


# === REPORT GENERATION ===

def generate_report(summaries, verdict, verdict_details, bars_info):
    primary = next(s for s in summaries if s["config_id"] == "P2A_VALIDATION")
    r03 = next(s for s in summaries if s["config_id"] == "P2A_R03_MA2")
    rw = next(s for s in summaries if s["config_id"] == "P2A_RANDOM_WALK_CHECK")

    rw_pred = 1.0 / (primary["reversal_target"] + 1.0)

    lines = [
        "# P2a Validation Report",
        f"**Date:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"**Period:** P2a (Dec 18, 2025 - Jan 30, 2026), 30 RTH trading days",
        f"**Bars:** {bars_info['total_bars']:,} (RTH, 1-tick)",
        "",
        f"## Verdict: **{verdict}**",
        "",
        "## Primary Criteria",
        "",
    ]
    for d in verdict_details:
        lines.append(f"- {d}")

    # Structural signature comparison
    lines.extend([
        "",
        "## Structural Signature Comparison",
        "",
        "| Metric | P1 Value | P2a Value | Concern Threshold |",
        "|--------|----------|-----------|-------------------|",
        f"| Success rate | {P1_REFERENCE['success_rate']:.1%} | {primary['success_rate']:.1%} | < 55.6% (below RW) |",
        f"| First-cycle SR | {P1_REFERENCE['first_cycle_sr']:.1%} | {primary['first_cycle_sr']:.1%} | < 58% |",
        f"| Later-cycle SR | {P1_REFERENCE['later_cycle_sr']:.1%} | {primary['later_cycle_sr']:.1%} | < 53% |",
        f"| Failure cascade rate | {P1_REFERENCE['failure_cascade_rate']:.1%} | {primary['failure_cascade_rate']:.1%} | > 55% |",
        f"| Avg progress HWM (fail) | {P1_REFERENCE['avg_progress_hwm_failure']:.1f}% | {primary['avg_progress_hwm_failure']:.1f}% | > 50% |",
        f"| Inc PnL / day | -7 ticks | {primary['inc_pnl_per_day']:.1f} ticks | < -100 |",
        f"| NPF (net) | {P1_REFERENCE['npf_net']:.2f} | {primary['npf_net']:.2f} | < 1.0 |",
        f"| Adj net PnL | {P1_REFERENCE['adj_net_pnl']:,} | {primary['adjusted_net_pnl']:.0f} | < 0 |",
        f"| Cycle count | {P1_REFERENCE['cycle_count']:,} | {primary['cycle_count']:,} | (30 days vs 60) |",
        f"| RW check (RT=1.0) | {P1_REFERENCE['rw_sr_rt100']:.1%} | {rw['success_rate']:.1%} | outside 47-53% |",
    ])

    # Comparison configs
    lines.extend([
        "",
        "## Comparison Configs (Informational Only)",
        "",
        "| Config | SR | Cycles | Adj Net | Notes |",
        "|--------|----|--------|---------|-------|",
        f"| MA0 RT=0.8 (primary) | {primary['success_rate']:.1%} | {primary['cycle_count']} | {primary['adjusted_net_pnl']:.0f} | Validation target |",
        f"| R03_MA2 RT=0.8 | {r03['success_rate']:.1%} | {r03['cycle_count']} | {r03['adjusted_net_pnl']:.0f} | Add config |",
        f"| RT=1.0 cost=0 | {rw['success_rate']:.1%} | {rw['cycle_count']} | {rw['adjusted_net_pnl']:.0f} | RW baseline |",
    ])

    # Equity curve
    lines.extend([
        "",
        "## Equity Curve",
        "",
        f"- Max drawdown: {primary['eq_max_dd_value']:.0f} ticks at cycle #{primary['eq_max_dd_cycle_idx']}",
        f"- Total cycles: {primary['cycle_count']}",
        f"- Final equity: {primary['net_pnl']:.0f} ticks (net), {primary['adjusted_net_pnl']:.0f} ticks (adjusted)",
    ])

    dd_pos = primary["eq_max_dd_cycle_idx"]
    total = primary["cycle_count"]
    if total > 0:
        pct = dd_pos / total * 100
        if pct < 33:
            timing = "early (first third)"
        elif pct < 67:
            timing = "mid-period"
        else:
            timing = "late (final third)"
        lines.append(f"- Max drawdown occurred: {timing} (cycle {dd_pos}/{total}, {pct:.0f}%)")

    return "\n".join(lines)


# === MAIN ===

def main():
    print("=" * 70)
    print("P2a REPLICATION VALIDATION (1-tick, frozen params)")
    print("=" * 70)

    # Step 1: Load P2a data
    print("\n[1/4] Loading P2a 1-tick bar data...")
    bars = load_p2a_bars()
    bars_info = {
        "total_bars": len(bars),
        "date_start": str(bars["datetime"].iloc[0].date()),
        "date_end": str(bars["datetime"].iloc[-1].date()),
        "trading_days": bars["datetime"].dt.date.nunique(),
    }

    # Step 2: Context tags
    print("\n[2/4] Pre-computing context tags...")
    ctx_250 = load_context_bars()

    # Step 3: Run configs
    print("\n[3/4] Running 3 configs...")
    configs = get_configs()
    CYCLE_LOG_DIR.mkdir(parents=True, exist_ok=True)

    summaries = []
    for cfg in configs:
        print(f"\n  Running: {cfg.config_id} ...", end=" ", flush=True)
        t0 = time.time()
        result = run_frozen_anchor_simulation(cfg, bars, context_bars=None, tick_size=TICK_SIZE)
        elapsed = time.time() - t0

        cycles = result.cycles
        incomplete = result.incomplete_cycles

        if ctx_250 is not None and not cycles.empty:
            cycles = join_context_to_cycles(cycles, ctx_250)

        summary = compute_summary(cycles, incomplete, cfg)
        summaries.append(summary)

        # Save logs
        cycles.to_csv(CYCLE_LOG_DIR / f"{cfg.config_id}.csv", index=False)
        if not incomplete.empty:
            incomplete.to_csv(CYCLE_LOG_DIR / f"{cfg.config_id}_incomplete.csv", index=False)

        sr = summary["success_rate"]
        adj = summary["adjusted_net_pnl"]
        n = summary["cycle_count"]
        print(f"({n} cyc, SR={sr:.1%}, adj_net={adj:.0f}, {elapsed:.1f}s)")

    # Step 4: Verdict + report
    print("\n[4/4] Determining verdict...")
    primary = next(s for s in summaries if s["config_id"] == "P2A_VALIDATION")
    rw = next(s for s in summaries if s["config_id"] == "P2A_RANDOM_WALK_CHECK")
    verdict, verdict_details = determine_verdict(primary, rw)

    print(f"\n  {'='*40}")
    print(f"  VERDICT: {verdict}")
    print(f"  {'='*40}")
    for d in verdict_details:
        print(f"  {d}")

    # Save outputs
    summary_df = pd.DataFrame(summaries)
    summary_df.to_csv(OUTPUT_DIR / "config_summary.csv", index=False)

    report = generate_report(summaries, verdict, verdict_details, bars_info)
    (OUTPUT_DIR / "p2a_validation_report.md").write_text(report, encoding="utf-8")

    metadata = {
        "run_timestamp": datetime.now().isoformat(),
        "period": "P2a",
        "p2a_start": "2025-12-18",
        "p2a_end": "2026-01-30",
        "p2b_start": "2026-02-02",
        "p2b_end": "2026-03-13",
        "rth_trading_days_p2a": 30,
        "rth_trading_days_p2b": 30,
        "total_bars": bars_info["total_bars"],
        "configs_run": [c.config_id for c in configs],
        "verdict": verdict,
        "frozen_params": {
            "step_dist": 40.0, "add_dist": 16.0, "max_adds": 0,
            "reversal_target": 0.8, "cost_ticks": 2.0,
        },
    }
    with open(OUTPUT_DIR / "p2a_metadata.json", "w") as f:
        json.dump(metadata, f, indent=2)

    print(f"\n  config_summary.csv: {len(summary_df)} rows")
    print(f"  p2a_validation_report.md saved")
    print(f"  p2a_metadata.json saved")
    print(f"\n  VALIDATION COMPLETE.")


if __name__ == "__main__":
    main()
