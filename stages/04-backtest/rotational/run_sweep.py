# archetype: rotational
"""Phase 1 Prompt 2 — Generate configs and run the full parameter sweep.

Usage:
    cd stages/04-backtest/rotational
    python run_sweep.py [--smoke-only] [--bar-type 1tick|250tick] [--workers 4]

Loads P1 bar data (default: 1-tick), generates 182 configs (A:7, B:84, C:35,
D:56), runs smoke test then full sweep with multiprocessing, saves results
to sweep_results/.

Context tagging:
  - 250-tick: context tags computed directly on bar data (OHLC meaningful).
  - 1-tick: context tags computed on 250-tick bars separately, then joined to
    cycle logs by timestamp after simulation. ATR/bar-range are meaningless on
    tick data (O=H=L=Last), so the simulator runs with context_bars=None.

Incomplete cycles:
  At session end, cycles in progress are mark-to-market'd and logged to
  {config_id}_incomplete.csv. Summary includes incomplete_cycles count and
  incomplete_unrealized_pnl (sum). This captures hidden risk masked by NPF=999.
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

from config_schema import RotationConfig
from context_tagger import tag_context
from rotation_simulator import run_simulation

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
COST_TICKS = 2.0   # Per-side cost in ticks (prompt spec; sensitivity at 3.0 in Prompt 3)
TICK_SIZE = 0.25    # NQ tick size from instruments.md

_TICK_DIR = _SCRIPT_DIR.parents[1] / "01-data" / "data" / "bar_data" / "tick"
P1_DATA_PATHS = {
    "1tick":   _TICK_DIR / "NQ_BarData_1tick_rot_P1.csv",
    "250tick": _TICK_DIR / "NQ_BarData_250tick_rot_P1.csv",
}
P1_CONTEXT_PATH = P1_DATA_PATHS["250tick"]  # Always use 250-tick for context

OUTPUT_DIR = _SCRIPT_DIR / "sweep_results"
CYCLE_LOG_DIR = OUTPUT_DIR / "cycle_logs"

# P1 date boundaries (inclusive)
P1_START = pd.Timestamp("2025-09-21")
P1_END = pd.Timestamp("2025-12-17")

# RTH boundaries (seconds from midnight)
RTH_START_SEC = 9 * 3600 + 30 * 60   # 09:30
RTH_END_SEC = 16 * 3600 + 15 * 60    # 16:15

# Temp file for sharing bars across worker processes (avoids pickling 1GB)
_BARS_FEATHER = OUTPUT_DIR / "_bars_tmp.feather"


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_p1_bars(bar_type: str = "1tick") -> pd.DataFrame:
    """Load P1 bar data, filter to RTH and P1 date range."""
    path = P1_DATA_PATHS[bar_type]
    print(f"Loading P1 {bar_type} bar data from: {path}")

    if bar_type == "1tick":
        header = pd.read_csv(path, nrows=0)
        header.columns = header.columns.str.strip()
        needed = ["Date", "Time", "Open", "High", "Low", "Last"]
        col_indices = [list(header.columns).index(c) for c in needed]
        df = pd.read_csv(path, usecols=col_indices, dtype={
            "Open": "float32", "High": "float32", "Low": "float32", "Last": "float32",
        })
    else:
        df = pd.read_csv(path)

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
# Config generation
# ---------------------------------------------------------------------------

def generate_all_configs() -> list[RotationConfig]:
    """Generate all 182 sweep configs (A:7, B:84, C:35, D:56)."""
    configs: list[RotationConfig] = []

    # Approach A: Pure Rotation (7)
    for sd in [15, 20, 25, 30, 35, 40, 50]:
        configs.append(RotationConfig(
            config_id=f"A_SD{sd}", approach="A",
            step_dist=float(sd), max_adds=0, cost_ticks=COST_TICKS,
        ))

    # Approach B: Traditional Martingale (84)
    for sd in [15, 20, 25, 30, 35, 40, 50]:
        for ad_ratio in [1.0, 0.5, 0.4]:
            ad = round(sd * ad_ratio, 2)
            for ma in [1, 2, 3, 4]:
                configs.append(RotationConfig(
                    config_id=f"B_SD{sd}_AD{ad}_MA{ma}", approach="B",
                    step_dist=float(sd), add_dist=float(ad),
                    max_adds=ma, cost_ticks=COST_TICKS,
                ))

    # Approach C: Anti-Martingale (35 after pruning)
    for sd in [15, 20, 25, 30, 35, 40, 50]:
        for cd_frac in [0.4, 0.5, 0.6, 0.7]:
            cd = round(sd * cd_frac, 2)
            for ma in [1, 2]:
                if ma == 2 and cd_frac >= 0.5:
                    continue
                configs.append(RotationConfig(
                    config_id=f"C_SD{sd}_CD{cd}_MA{ma}", approach="C",
                    step_dist=float(sd), confirm_dist=float(cd),
                    max_adds=ma, cost_ticks=COST_TICKS,
                ))

    # Approach D: Scaled Entry (56 after dedup)
    for sd in [15, 20, 25, 30, 35, 40, 50]:
        for cd_frac in [0.4, 0.5, 0.6, 0.7]:
            cd = round(sd * cd_frac, 2)
            for add_sz in [2, 3]:  # skip add_size=1 (dedup with C)
                configs.append(RotationConfig(
                    config_id=f"D_SD{sd}_CD{cd}_AS{add_sz}", approach="D",
                    step_dist=float(sd), confirm_dist=float(cd),
                    max_adds=1, add_size=add_sz, cost_ticks=COST_TICKS,
                ))

    return configs


def count_by_approach(configs: list[RotationConfig]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for c in configs:
        counts[c.approach] = counts.get(c.approach, 0) + 1
    return counts


# ---------------------------------------------------------------------------
# Per-config summary (includes incomplete cycle stats)
# ---------------------------------------------------------------------------

def compute_config_summary(
    cycles_df: pd.DataFrame,
    incomplete_df: pd.DataFrame,
    config: RotationConfig,
) -> dict:
    """Compute all summary metrics for one config's cycle log + incomplete cycles."""
    n_cycles = len(cycles_df)

    if n_cycles == 0:
        s = _empty_summary(config)
        s["incomplete_cycles"] = len(incomplete_df)
        s["incomplete_unrealized_pnl"] = round(
            incomplete_df["unrealized_pnl_ticks"].sum(), 4
        ) if not incomplete_df.empty else 0.0
        return s

    net_pnl = cycles_df["pnl_ticks_net"]
    gross_pnl = cycles_df["pnl_ticks_gross"]

    wins = cycles_df[net_pnl > 0]
    losses = cycles_df[net_pnl <= 0]

    gross_wins_sum = gross_pnl[net_pnl > 0].sum()
    gross_losses_sum = gross_pnl[net_pnl <= 0].sum()
    net_wins_sum = net_pnl[net_pnl > 0].sum()
    net_losses_sum = net_pnl[net_pnl <= 0].sum()

    npf_gross = gross_wins_sum / abs(gross_losses_sum) if gross_losses_sum != 0 else (999.0 if gross_wins_sum > 0 else 0.0)
    npf_net = net_wins_sum / abs(net_losses_sum) if net_losses_sum != 0 else (999.0 if net_wins_sum > 0 else 0.0)

    cumulative = net_pnl.cumsum()
    rolling_max = cumulative.cummax()
    drawdown = cumulative - rolling_max
    max_dd = abs(drawdown.min()) if len(drawdown) > 0 else 0.0

    total_net = net_pnl.sum()
    profit_per_dd = total_net / max_dd if max_dd > 0 else (999.0 if total_net > 0 else 0.0)

    add_counts = cycles_df["add_count"]
    mask_0 = add_counts == 0
    mask_1 = add_counts == 1
    mask_multi = add_counts >= 2

    max_pos = cycles_df["exit_position"].max() if "exit_position" in cycles_df.columns else 1

    frs_count = 0
    if config.approach == "B" and "would_flatten_reseed" in cycles_df.columns:
        frs_count = int(cycles_df["would_flatten_reseed"].sum())

    inc_count = len(incomplete_df)
    inc_pnl = round(incomplete_df["unrealized_pnl_ticks"].sum(), 4) if not incomplete_df.empty else 0.0

    return {
        "config_id": config.config_id,
        "approach": config.approach,
        "step_dist": config.step_dist,
        "add_dist": config.add_dist,
        "confirm_dist": config.confirm_dist,
        "max_adds": config.max_adds,
        "add_size": config.add_size,
        "cycle_count": n_cycles,
        "win_count": len(wins),
        "loss_count": len(losses),
        "win_rate": len(wins) / n_cycles,
        "gross_pnl": round(gross_pnl.sum(), 4),
        "net_pnl": round(total_net, 4),
        "total_costs": round(gross_pnl.sum() - total_net, 4),
        "npf_gross": round(npf_gross, 4),
        "npf_net": round(npf_net, 4),
        "avg_win_net": round(wins["pnl_ticks_net"].mean(), 4) if len(wins) > 0 else 0.0,
        "avg_loss_net": round(losses["pnl_ticks_net"].mean(), 4) if len(losses) > 0 else 0.0,
        "max_drawdown_ticks": round(max_dd, 4),
        "profit_per_dd": round(profit_per_dd, 4),
        "max_position": int(max_pos),
        "avg_cycle_duration_bars": round(cycles_df["duration_bars"].mean(), 2),
        "cycles_0_adds": int(mask_0.sum()),
        "cycles_1_add": int(mask_1.sum()),
        "cycles_multi_add": int(mask_multi.sum()),
        "pnl_0_adds": round(net_pnl[mask_0].sum(), 4),
        "pnl_1_add": round(net_pnl[mask_1].sum(), 4),
        "pnl_multi_add": round(net_pnl[mask_multi].sum(), 4),
        "flatten_reseed_would_fire": frs_count,
        "incomplete_cycles": inc_count,
        "incomplete_unrealized_pnl": inc_pnl,
    }


def _empty_summary(config: RotationConfig) -> dict:
    return {
        "config_id": config.config_id,
        "approach": config.approach,
        "step_dist": config.step_dist,
        "add_dist": config.add_dist,
        "confirm_dist": config.confirm_dist,
        "max_adds": config.max_adds,
        "add_size": config.add_size,
        "cycle_count": 0, "win_count": 0, "loss_count": 0, "win_rate": 0.0,
        "gross_pnl": 0.0, "net_pnl": 0.0, "total_costs": 0.0,
        "npf_gross": 0.0, "npf_net": 0.0,
        "avg_win_net": 0.0, "avg_loss_net": 0.0,
        "max_drawdown_ticks": 0.0, "profit_per_dd": 0.0,
        "max_position": 0, "avg_cycle_duration_bars": 0.0,
        "cycles_0_adds": 0, "cycles_1_add": 0, "cycles_multi_add": 0,
        "pnl_0_adds": 0.0, "pnl_1_add": 0.0, "pnl_multi_add": 0.0,
        "flatten_reseed_would_fire": 0,
        "incomplete_cycles": 0, "incomplete_unrealized_pnl": 0.0,
    }


# ---------------------------------------------------------------------------
# Worker function for multiprocessing
# ---------------------------------------------------------------------------

# Module-level state for worker processes (loaded once per worker via initializer)
_worker_bars: pd.DataFrame | None = None
_worker_ctx_250: pd.DataFrame | None = None


def _worker_init(bars_feather_path: str, ctx_250_feather_path: str | None) -> None:
    """Initialize worker process: load bars from feather (fast deserialization)."""
    global _worker_bars, _worker_ctx_250
    _worker_bars = pd.read_feather(bars_feather_path)
    if ctx_250_feather_path:
        _worker_ctx_250 = pd.read_feather(ctx_250_feather_path)
    else:
        _worker_ctx_250 = None


def _run_one_config(config: RotationConfig) -> dict[str, Any]:
    """Run a single config in a worker process. Returns dict with results."""
    global _worker_bars, _worker_ctx_250

    t0 = time.time()
    result = run_simulation(config, _worker_bars, context_bars=None, tick_size=TICK_SIZE)
    elapsed = time.time() - t0

    cycles = result.cycles
    incomplete = result.incomplete_cycles

    # Join context from 250-tick bars
    if _worker_ctx_250 is not None and not cycles.empty:
        cycles = join_context_to_cycles(cycles, _worker_ctx_250)

    # Compute summary
    summary = compute_config_summary(cycles, incomplete, config)

    return {
        "config": config,
        "cycles": cycles,
        "incomplete": incomplete,
        "summary": summary,
        "elapsed": elapsed,
    }


# ---------------------------------------------------------------------------
# Smoke test (sequential — always runs in main process)
# ---------------------------------------------------------------------------

def run_smoke_test(bars: pd.DataFrame, ctx_250: pd.DataFrame | None = None) -> bool:
    """Run 4 smoke configs (one per approach). Return True if all pass."""
    smoke_configs = [
        RotationConfig("SMOKE_A", "A", step_dist=25.0, cost_ticks=COST_TICKS),
        RotationConfig("SMOKE_B", "B", step_dist=25.0, add_dist=10.0, max_adds=2, cost_ticks=COST_TICKS),
        RotationConfig("SMOKE_C", "C", step_dist=25.0, confirm_dist=10.0, max_adds=1, cost_ticks=COST_TICKS),
        RotationConfig("SMOKE_D", "D", step_dist=25.0, confirm_dist=10.0, max_adds=1, add_size=2, cost_ticks=COST_TICKS),
    ]

    report_lines = [
        "# Smoke Test Report",
        f"**Date:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"**Bars:** {len(bars):,} (RTH, P1)",
        "",
    ]
    all_pass = True

    for cfg in smoke_configs:
        print(f"\n  Smoke: {cfg.config_id} ...", end=" ", flush=True)
        t0 = time.time()
        result = run_simulation(cfg, bars, context_bars=None, tick_size=TICK_SIZE)
        elapsed = time.time() - t0
        cycles = result.cycles
        incomplete = result.incomplete_cycles

        if ctx_250 is not None and not cycles.empty:
            cycles = join_context_to_cycles(cycles, ctx_250)

        n = len(cycles)
        n_inc = len(incomplete)
        issues: list[str] = []

        if n == 0:
            issues.append("0 cycles produced")

        expected_cols = {"config_id", "approach", "pnl_ticks_gross", "pnl_ticks_net",
                         "add_count", "exit_position", "mfe_points", "mae_points",
                         "would_flatten_reseed", "half_block_profit"}
        missing = expected_cols - set(cycles.columns)
        if missing:
            issues.append(f"Missing columns: {missing}")

        if n > 0:
            if cycles["pnl_ticks_net"].sum() >= cycles["pnl_ticks_gross"].sum():
                issues.append("Net PnL >= Gross PnL (costs not applied?)")

            if cfg.approach == "A":
                if (cycles["exit_position"] != 1).any():
                    issues.append("Approach A: exit_position != 1 found")
            elif cfg.approach == "B":
                if (cycles["add_count"] > 0).sum() == 0:
                    issues.append("Approach B: no cycles with adds")
            elif cfg.approach == "D":
                adds_mask = cycles["add_count"] > 0
                if adds_mask.any():
                    d_exit_pos = cycles.loc[adds_mask, "exit_position"]
                    expected_exit = 1 + cfg.add_size
                    if (d_exit_pos != expected_exit).any():
                        issues.append(f"Approach D: exit_position != {expected_exit} on add cycles")

        # Check incomplete cycles are captured
        if n_inc == 0:
            issues.append("0 incomplete cycles (expected some at session boundaries)")

        status = "PASS" if not issues else "FAIL"
        if issues:
            all_pass = False

        inc_pnl = incomplete["unrealized_pnl_ticks"].sum() if n_inc > 0 else 0.0
        print(f"{status} ({n} cycles, {n_inc} incomplete, {elapsed:.1f}s)")

        report_lines.append(f"## {cfg.config_id}: **{status}**")
        report_lines.append(f"- Cycles: {n}")
        report_lines.append(f"- Runtime: {elapsed:.1f}s")
        if n > 0:
            report_lines.append(f"- Gross PnL: {cycles['pnl_ticks_gross'].sum():.1f}")
            report_lines.append(f"- Net PnL: {cycles['pnl_ticks_net'].sum():.1f}")
            report_lines.append(f"- Max position: {cycles['exit_position'].max()}")
            report_lines.append(f"- Adds > 0: {(cycles['add_count'] > 0).sum()} cycles")
        report_lines.append(f"- Incomplete cycles: {n_inc}")
        report_lines.append(f"- Incomplete unrealized PnL: {inc_pnl:.1f}")
        if issues:
            for iss in issues:
                report_lines.append(f"- **ISSUE:** {iss}")
        report_lines.append("")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUTPUT_DIR / "smoke_test_report.md").write_text("\n".join(report_lines), encoding="utf-8")
    print(f"\n  Smoke report saved to sweep_results/smoke_test_report.md")

    return all_pass


# ---------------------------------------------------------------------------
# Full sweep with multiprocessing
# ---------------------------------------------------------------------------

def run_full_sweep(
    configs: list[RotationConfig],
    bars: pd.DataFrame,
    bar_type: str,
    ctx_250: pd.DataFrame | None = None,
    n_workers: int = 4,
) -> pd.DataFrame:
    """Run all configs with multiprocessing, save cycle logs + incomplete logs."""
    CYCLE_LOG_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    total = len(configs)

    # Save bars to feather for fast worker loading (avoids pickling 1GB)
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

    # Use multiprocessing Pool with initializer
    with mp.Pool(
        processes=n_workers,
        initializer=_worker_init,
        initargs=(str(_BARS_FEATHER), ctx_feather_path),
    ) as pool:
        # imap_unordered for best throughput; results arrive as they complete
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

            n = len(cycles)
            n_inc = len(incomplete)
            if n == 0:
                zero_cycle_configs.append(config.config_id)
                print(f"  [{completed:3d}/{total}] {config.config_id}: "
                      f"*** 0 CYCLES *** ({n_inc} inc, {elapsed:.1f}s)")
            else:
                npf = summary["npf_net"]
                inc_pnl = summary["incomplete_unrealized_pnl"]
                print(f"  [{completed:3d}/{total}] {config.config_id}: "
                      f"{n} cycles, NPF={npf:.3f}, net={summary['net_pnl']:.0f}, "
                      f"inc={n_inc}({inc_pnl:.0f}) ({elapsed:.1f}s)")

    total_runtime = time.time() - t_start
    print(f"\n  Sweep complete: {total} configs in {total_runtime:.0f}s ({total_runtime/60:.1f}min)")

    if zero_cycle_configs:
        print(f"  WARNING: {len(zero_cycle_configs)} configs produced 0 cycles: {zero_cycle_configs}")

    # Clean up temp feather files
    _BARS_FEATHER.unlink(missing_ok=True)
    ctx_feather.unlink(missing_ok=True)

    # Sort summaries by config_id for deterministic output (imap_unordered doesn't preserve order)
    summaries.sort(key=lambda s: s["config_id"])

    # Save config_summary.csv
    summary_df = pd.DataFrame(summaries)
    summary_df.to_csv(OUTPUT_DIR / "config_summary.csv", index=False)
    print(f"  config_summary.csv: {len(summary_df)} rows")

    # Save metadata
    by_approach = count_by_approach(configs)
    trading_days = bars["datetime"].dt.date.nunique()
    metadata = {
        "run_timestamp": datetime.now().isoformat(),
        "p1_date_range": f"{bars['datetime'].iloc[0].strftime('%Y-%m-%d')} to "
                         f"{bars['datetime'].iloc[-1].strftime('%Y-%m-%d')}",
        "bar_type": bar_type,
        "total_bars": len(bars),
        "rth_trading_days": int(trading_days),
        "total_configs": total,
        "configs_by_approach": by_approach,
        "cost_ticks": COST_TICKS,
        "context_thresholds": {"swing_zigzag": 5, "persistence_zigzag": 10},
        "total_runtime_seconds": round(total_runtime, 1),
        "n_workers": n_workers,
        "zero_cycle_configs": zero_cycle_configs,
    }
    with open(OUTPUT_DIR / "sweep_metadata.json", "w") as f:
        json.dump(metadata, f, indent=2)
    print(f"  sweep_metadata.json saved")

    return summary_df


# ---------------------------------------------------------------------------
# Context spot-check
# ---------------------------------------------------------------------------

def spot_check_context(bars: pd.DataFrame) -> None:
    """Print 5 random mid-data bars to verify context columns."""
    valid = bars.dropna(subset=["atr_pct"])
    if len(valid) < 5:
        print("  WARNING: fewer than 5 bars with valid atr_pct")
        return

    sample = valid.sample(5, random_state=42)
    ctx_cols = ["atr_20", "atr_pct", "bar_range", "bar_range_median_20",
                "swing_median_20", "swing_p90_20", "directional_persistence"]
    print("\n  Context spot-check (5 random bars):")
    for _, row in sample.iterrows():
        vals = {c: round(row[c], 2) if isinstance(row[c], float) else row[c] for c in ctx_cols}
        print(f"    {row['datetime']}: {vals}")

    nan_count = bars["atr_pct"].isna().sum()
    print(f"  NaN atr_pct rows: {nan_count} (expected: ~first 500 bars)")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Phase 1 Prompt 2: Run rotation sweep")
    parser.add_argument("--smoke-only", action="store_true",
                        help="Run only smoke test, skip full sweep")
    parser.add_argument("--bar-type", choices=["1tick", "250tick"], default="1tick",
                        help="Bar data resolution (default: 1tick)")
    parser.add_argument("--workers", type=int, default=4,
                        help="Number of worker processes (default: 4)")
    args = parser.parse_args()

    bar_type: str = args.bar_type

    print("=" * 70)
    print(f"PHASE 1 PROMPT 2 — ROTATION PARAMETER SWEEP ({bar_type}, {args.workers} workers)")
    print("=" * 70)

    # Step 1: Load P1 bar data
    print(f"\n[1/5] Loading P1 {bar_type} bar data...")
    bars = load_p1_bars(bar_type)

    # Step 2: Context tags (always from 250-tick bars)
    ctx_250: pd.DataFrame | None = None

    if bar_type == "250tick":
        print("\n[2/5] Pre-computing context tags on 250-tick bars...")
        t0 = time.time()
        bars = tag_context(bars)
        print(f"  Context tagging complete ({time.time() - t0:.1f}s)")
        spot_check_context(bars)
        # For 250-tick, ctx_250 is bars itself (already tagged)
        ctx_250 = bars
    else:
        print("\n[2/5] Pre-computing context tags on 250-tick reference bars...")
        ctx_250 = load_context_bars()
        spot_check_context(ctx_250)
        print("  (Context will be joined to cycles by timestamp after simulation)")

    # Step 3: Generate configs
    print("\n[3/5] Generating configs...")
    configs = generate_all_configs()
    by_approach = count_by_approach(configs)
    print(f"  Total configs: {len(configs)}")
    print(f"  By approach: {by_approach}")
    assert len(configs) == 182, f"Expected 182 configs, got {len(configs)}"

    # Step 4: Smoke test (sequential in main process)
    print("\n[4/5] Running smoke test...")
    smoke_ok = run_smoke_test(bars, ctx_250=ctx_250)

    if not smoke_ok:
        print("\n  *** SMOKE TEST FAILED — aborting full sweep ***")
        sys.exit(1)

    if args.smoke_only:
        print("\n  --smoke-only flag set. Skipping full sweep.")
        return

    # Step 5: Full sweep with multiprocessing
    print(f"\n[5/5] Running full sweep (182 configs on {bar_type}, {args.workers} workers)...")
    summary_df = run_full_sweep(configs, bars, bar_type=bar_type,
                                ctx_250=ctx_250, n_workers=args.workers)

    # Final validation
    print("\n" + "=" * 70)
    print("SELF-CHECK")
    print("=" * 70)
    cycle_log_files = [f for f in CYCLE_LOG_DIR.glob("*.csv") if "_incomplete" not in f.name]
    inc_files = list(CYCLE_LOG_DIR.glob("*_incomplete.csv"))
    print(f"  config_summary.csv rows: {len(summary_df)} (expected: 182)")
    print(f"  cycle_log CSVs: {len(cycle_log_files)} (expected: 182)")
    print(f"  incomplete CSVs: {len(inc_files)}")
    print(f"  All config_ids have cycle log: "
          f"{all((CYCLE_LOG_DIR / f'{cid}.csv').exists() for cid in summary_df['config_id'])}")

    # Incomplete cycle stats
    total_inc = summary_df["incomplete_cycles"].sum()
    total_inc_pnl = summary_df["incomplete_unrealized_pnl"].sum()
    print(f"  Total incomplete cycles across all configs: {total_inc}")
    print(f"  Total incomplete unrealized PnL: {total_inc_pnl:.0f} ticks")

    # Approach-level incomplete stats
    for app in ["A", "B", "C", "D"]:
        app_df = summary_df[summary_df["approach"] == app]
        print(f"    {app}: {app_df['incomplete_cycles'].sum()} incomplete, "
              f"unrealized PnL = {app_df['incomplete_unrealized_pnl'].sum():.0f}")

    # Config integrity checks
    d_configs = [c for c in configs if c.approach == "D"]
    assert all(c.add_size > 1 for c in d_configs), "Found D config with add_size=1"
    assert all(c.max_adds == 1 for c in d_configs), "Found D config with max_adds != 1"

    print(f"\n  Cost ticks uniform: "
          f"{(summary_df.get('total_costs', pd.Series([0])) > 0).all() if len(summary_df) > 0 else 'N/A'}")
    print("\n  SWEEP COMPLETE.")


if __name__ == "__main__":
    main()
