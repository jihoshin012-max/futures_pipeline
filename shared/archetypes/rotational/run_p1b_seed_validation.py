# archetype: rotational
"""ONE-SHOT P1b validation of seed-optimized rotational config.

Frozen config: SeedDist=15, Variant D (9:30 watch price), daily flatten 16:00 ET,
SpeedRead>=48 for seed and reversal, StepDist=25, cap=2, ML=1, walking anchor.

Steps:
  1. P1a sanity check (must reproduce known values within 5%)
  2. P1b one-shot validation
  3. Save all artifacts

Usage:
    python run_p1b_seed_validation.py
"""

import sys
import json
import time
import datetime as dt_mod
from pathlib import Path

import numpy as np
import pandas as pd

_REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_REPO))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from shared.data_loader import load_bars
from run_seed_investigation import (
    simulate_daily_flatten, _finalize_cycle,
    TICK_SIZE, STEP_DIST, FLATTEN_CAP, MAX_LEVELS, COST_TICKS,
    EXCLUDE_HOURS, FLATTEN_TOD, RESUME_TOD, RTH_OPEN_TOD,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_P1_START = dt_mod.date(2025, 9, 21)
_P1_END = dt_mod.date(2025, 12, 14)
_P1_MID = _P1_START + (_P1_END - _P1_START) / 2  # ~Nov 2

# Frozen config
SEED_DIST = 15.0
SEED_SR_THRESH = 48.0
REV_SR_THRESH = 48.0
WATCH_MODE = 'rth_open'  # Variant D

_1TICK_PATH = "stages/01-data/data/bar_data/tick/NQ_BarData_1tick_rot_P1.csv"
_SR_PARQUET = Path(__file__).parent / "speedread_results" / "speedread_250tick.parquet"
_OUTPUT_DIR = Path(__file__).parent / "seed_investigation_results"


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_period_data(period):
    """Load tick data and SpeedRead for a specific period ('P1a' or 'P1b')."""
    print(f"Loading tick data ({period})...")
    t0 = time.time()
    tick_bars = load_bars(str(_REPO / _1TICK_PATH))

    if period == "P1a":
        tick = tick_bars[tick_bars["datetime"].dt.date <= _P1_MID].reset_index(drop=True)
    else:
        tick = tick_bars[tick_bars["datetime"].dt.date > _P1_MID].reset_index(drop=True)

    print(f"  {period} ticks: {len(tick):,} rows in {time.time() - t0:.1f}s")

    prices = tick["Last"].values.astype(np.float64)
    dts = tick["datetime"].values
    hours = tick["datetime"].dt.hour.values.astype(np.int32)
    minutes = tick["datetime"].dt.minute.values.astype(np.int32)
    seconds = tick["datetime"].dt.second.values.astype(np.int32)
    tod_secs = hours * 3600 + minutes * 60 + seconds

    # SpeedRead mapping
    print("  Mapping SpeedRead composite...")
    sr_df = pd.read_parquet(_SR_PARQUET)
    sr_ts = pd.to_datetime(sr_df["datetime"]).values.astype("int64") // 10**9
    sr_comp = sr_df["speedread_composite"].values.astype(np.float64)
    sr_comp = np.nan_to_num(sr_comp, nan=-1.0)

    tick_ts = tick["datetime"].values.astype("int64") // 10**9
    sr_idx = np.clip(np.searchsorted(sr_ts, tick_ts, side="right") - 1, 0, len(sr_df) - 1)
    tick_sr = sr_comp[sr_idx]

    valid = (tick_sr >= 0).sum()
    print(f"  SpeedRead valid: {valid:,} / {len(tick_sr):,}")
    print(f"  Date range: {tick['datetime'].iloc[0]} to {tick['datetime'].iloc[-1]}")
    print(f"  Load complete in {time.time() - t0:.1f}s")

    return prices, tod_secs, tick_sr, dts


# ---------------------------------------------------------------------------
# Analysis (extended for P1b reporting)
# ---------------------------------------------------------------------------

def full_analysis(sim_result, label):
    """Comprehensive analysis for P1b validation reporting."""
    trade_records = sim_result["trade_records"]
    cycle_records = sim_result["cycle_records"]
    total_sessions = sim_result["total_sessions"]

    if not cycle_records:
        return None

    trades_df = pd.DataFrame(trade_records)
    cycles_df = pd.DataFrame(cycle_records)

    # Post-hoc hour filter
    entry_trades = trades_df[trades_df["action"].isin(["SEED", "REVERSAL"])]
    ce = entry_trades.groupby("cycle_id")["datetime"].first().reset_index()
    ce.columns = ["cycle_id", "entry_dt"]
    cycles_df = cycles_df.merge(ce, on="cycle_id", how="left")
    cycles_df["hour"] = pd.to_datetime(cycles_df["entry_dt"]).dt.hour
    cf = cycles_df[~cycles_df["hour"].isin(EXCLUDE_HOURS)].copy()

    if len(cf) == 0:
        return None

    valid_ids = set(cf["cycle_id"])
    tf = trades_df[trades_df["cycle_id"].isin(valid_ids)]
    cc = tf.groupby("cycle_id")["cost_ticks"].sum()
    cf["cost"] = cf["cycle_id"].map(cc).fillna(0)
    cf["net_1t"] = cf["gross_pnl_ticks"] - cf["cost"]

    nn = len(cf)
    gw = cf[cf["gross_pnl_ticks"] > 0]["gross_pnl_ticks"].sum()
    gl = abs(cf[cf["gross_pnl_ticks"] <= 0]["gross_pnl_ticks"].sum())
    gpf = gw / gl if gl else 0

    nw = cf[cf["net_1t"] > 0]["net_1t"].sum()
    nl = abs(cf[cf["net_1t"] <= 0]["net_1t"].sum())
    npf = nw / nl if nl else 0

    net_pnl = cf["net_1t"].sum()

    # Per-session PnL
    all_sids = range(1, total_sessions + 1)
    session_pnl_raw = cf.groupby("session_id")["net_1t"].sum()
    session_pnl = session_pnl_raw.reindex(all_sids, fill_value=0.0)

    cycles_per_session = cf.groupby("session_id").size().reindex(all_sids, fill_value=0)

    mean_daily = session_pnl.mean()
    std_daily = session_pnl.std()
    session_win_pct = (session_pnl > 0).mean()

    pvals = session_pnl.values
    if len(pvals) >= 5:
        p10, p25, p50, p75, p90 = np.percentile(pvals, [10, 25, 50, 75, 90])
    else:
        p10 = p25 = p50 = p75 = p90 = 0.0

    # Best and worst 5 sessions
    worst5 = session_pnl.nsmallest(5)
    best5 = session_pnl.nlargest(5)

    # Longest consecutive losing streak
    pnl_series = session_pnl.values
    max_streak = 0
    cur_streak = 0
    for v in pnl_series:
        if v <= 0:
            cur_streak += 1
            max_streak = max(max_streak, cur_streak)
        else:
            cur_streak = 0

    # Seed accuracy
    first_actions = trades_df.groupby("cycle_id")["action"].first()
    seed_cids = first_actions[first_actions == "SEED"].index
    seed_cf = cf[cf["cycle_id"].isin(seed_cids)]
    seed_accuracy = (seed_cf["gross_pnl_ticks"] > 0).mean() if len(seed_cf) > 0 else 0

    # SpeedRead filter activity: count SR-block seeds and SR-block reversals
    # SR-block seed = seed that was BLOCKED (would have fired but SR < 48)
    # We can't count blocked events directly, but we can count reversal_sr_skip exits
    sr_skip_count = (cf["exit_reason"] == "reversal_sr_skip").sum()

    # SR-block episodes during WATCHING: we don't have per-tick diagnostics here,
    # but we report the reversal_sr_skip count as a proxy for SR filter activity

    return {
        "label": label,
        "cycles": nn,
        "gpf": round(gpf, 4),
        "npf_1t": round(npf, 4),
        "net_pnl": int(net_pnl),
        "sessions": total_sessions,
        "mean_daily": round(mean_daily, 1),
        "std_daily": round(std_daily, 1),
        "session_win_pct": round(session_win_pct, 4),
        "cycles_per_session": round(cycles_per_session.mean(), 1),
        "seed_accuracy": round(seed_accuracy, 4),
        "p10": round(p10, 1), "p25": round(p25, 1), "p50": round(p50, 1),
        "p75": round(p75, 1), "p90": round(p90, 1),
        "worst5": {str(k): round(v, 1) for k, v in worst5.items()},
        "best5": {str(k): round(v, 1) for k, v in best5.items()},
        "max_losing_streak": max_streak,
        "reversal_sr_skips": int(sr_skip_count),
        "session_pnl": {str(k): round(v, 1) for k, v in session_pnl.items()},
        # For parquet export
        "_cycles_df": cf,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("=" * 70)
    print("P1b VALIDATION — Seed-Optimized Rotational Config (ONE-SHOT)")
    print("=" * 70)
    print("\nFrozen config:")
    print(f"  SeedDist={SEED_DIST}, StepDist={STEP_DIST}, cap={FLATTEN_CAP}, ML={MAX_LEVELS}")
    print(f"  Watch price: 09:30 ET (Variant D), Daily flatten: 16:00 ET")
    print(f"  Seed SR>={SEED_SR_THRESH}, Reversal SR>={REV_SR_THRESH}")
    print(f"  Anchor=walking, cost_ticks={COST_TICKS}")

    # ===================================================================
    # STEP 1: P1a Sanity Check
    # ===================================================================
    print("\n" + "=" * 70)
    print("STEP 1: P1a Sanity Check")
    print("=" * 70)

    p1a_data = load_period_data("P1a")

    t0 = time.time()
    sim_p1a = simulate_daily_flatten(
        *p1a_data,
        seed_dist=SEED_DIST, step_dist=STEP_DIST,
        seed_sr_thresh=SEED_SR_THRESH, rev_sr_thresh=REV_SR_THRESH,
        watch_mode=WATCH_MODE, reset_on_reversal=False,
    )
    print(f"  P1a simulation: {time.time() - t0:.1f}s")

    r_p1a = full_analysis(sim_p1a, "P1a sanity check")
    if r_p1a is None:
        print("  FATAL: No valid P1a cycles. Cannot proceed.")
        return

    # Known P1a values
    known = {"npf_1t": 1.361, "net_pnl": 15997, "cycles": 773}

    print(f"\n  {'Metric':<20} {'Expected':>10} {'Got':>10} {'Delta':>8}")
    print(f"  {'-'*50}")
    all_pass = True
    for key, expected in known.items():
        got = r_p1a[key]
        if expected != 0:
            delta_pct = abs(got - expected) / abs(expected) * 100
        else:
            delta_pct = 0
        status = "OK" if delta_pct <= 5 else "FAIL"
        if status == "FAIL":
            all_pass = False
        print(f"  {key:<20} {expected:>10} {got:>10} {delta_pct:>7.1f}% {status}")

    if not all_pass:
        print("\n  *** SANITY CHECK FAILED. Deviations > 5%. DO NOT PROCEED TO P1B. ***")
        return

    print(f"\n  SANITY CHECK PASSED. All metrics within 5%. Proceeding to P1b.")

    # ===================================================================
    # STEP 2: P1b One-Shot Validation
    # ===================================================================
    print("\n" + "=" * 70)
    print("STEP 2: P1b ONE-SHOT Validation")
    print("  *** THIS IS THE ONE AND ONLY P1B RUN ***")
    print("=" * 70)

    p1b_data = load_period_data("P1b")

    t0 = time.time()
    sim_p1b = simulate_daily_flatten(
        *p1b_data,
        seed_dist=SEED_DIST, step_dist=STEP_DIST,
        seed_sr_thresh=SEED_SR_THRESH, rev_sr_thresh=REV_SR_THRESH,
        watch_mode=WATCH_MODE, reset_on_reversal=False,
    )
    print(f"  P1b simulation: {time.time() - t0:.1f}s")

    r_p1b = full_analysis(sim_p1b, "P1b validation")
    if r_p1b is None:
        print("  FATAL: No valid P1b cycles.")
        _save_validation_result(r_p1a, None, "FAIL", "No valid P1b cycles")
        return

    # ===================================================================
    # Report
    # ===================================================================
    print(f"\n--- P1b Primary Metrics ---")
    print(f"  Total completed cycles: {r_p1b['cycles']}")
    print(f"  Gross PF:               {r_p1b['gpf']:.4f}")
    print(f"  Net PF @1t:             {r_p1b['npf_1t']:.4f}")
    print(f"  Net PnL (ticks):        {r_p1b['net_pnl']:+,}")
    print(f"  Trading sessions:       {r_p1b['sessions']}")
    print(f"  Daily mean PnL:         {r_p1b['mean_daily']:+.1f}")
    print(f"  Daily StdDev:           {r_p1b['std_daily']:.1f}")
    print(f"  Session win %:          {r_p1b['session_win_pct']:.1%}")
    print(f"  Seed accuracy:          {r_p1b['seed_accuracy']:.1%}")
    print(f"  Cycles/session:         {r_p1b['cycles_per_session']:.1f}")
    print(f"  Reversal SR skips:      {r_p1b['reversal_sr_skips']}")
    print(f"  Max losing streak:      {r_p1b['max_losing_streak']} sessions")

    # P1a vs P1b comparison
    print(f"\n--- P1a vs P1b Comparison ---")
    print(f"  {'Metric':<20} {'P1a':>10} {'P1b':>10} {'Delta':>10}")
    print(f"  {'-'*55}")
    comparisons = [
        ("Net PF @1t", r_p1a["npf_1t"], r_p1b["npf_1t"]),
        ("Net PnL", r_p1a["net_pnl"], r_p1b["net_pnl"]),
        ("Cycles", r_p1a["cycles"], r_p1b["cycles"]),
        ("Sessions", r_p1a["sessions"], r_p1b["sessions"]),
        ("Daily mean", r_p1a["mean_daily"], r_p1b["mean_daily"]),
        ("Session win%", r_p1a["session_win_pct"], r_p1b["session_win_pct"]),
        ("Seed accuracy", r_p1a["seed_accuracy"], r_p1b["seed_accuracy"]),
    ]
    for name, p1a_v, p1b_v in comparisons:
        if isinstance(p1a_v, float) and p1a_v != 0:
            delta = f"{(p1b_v - p1a_v) / abs(p1a_v) * 100:+.1f}%"
        elif isinstance(p1a_v, int) and p1a_v != 0:
            delta = f"{(p1b_v - p1a_v) / abs(p1a_v) * 100:+.1f}%"
        else:
            delta = "—"
        p1a_s = f"{p1a_v:.4f}" if isinstance(p1a_v, float) and abs(p1a_v) < 10 else f"{p1a_v:+,}" if isinstance(p1a_v, int) else str(p1a_v)
        p1b_s = f"{p1b_v:.4f}" if isinstance(p1b_v, float) and abs(p1b_v) < 10 else f"{p1b_v:+,}" if isinstance(p1b_v, int) else str(p1b_v)
        print(f"  {name:<20} {p1a_s:>10} {p1b_s:>10} {delta:>10}")

    # Prior P1b comparison (context only)
    print(f"\n--- Context: Prior P1b (SpeedRead-only, continuous) ---")
    print(f"  {'Metric':<20} {'Prior P1b':>10} {'This P1b':>10}")
    print(f"  {'-'*45}")
    print(f"  {'Net PF @1t':<20} {'1.117':>10} {r_p1b['npf_1t']:>10.4f}")
    print(f"  {'Net PnL':<20} {'+12,653':>10} {r_p1b['net_pnl']:>+10,}")
    print(f"  {'Cycles':<20} {'1,584':>10} {r_p1b['cycles']:>10,}")

    # Distribution
    print(f"\n--- Per-Session PnL Distribution ---")
    print(f"  P10:    {r_p1b['p10']:+.1f}")
    print(f"  P25:    {r_p1b['p25']:+.1f}")
    print(f"  Median: {r_p1b['p50']:+.1f}")
    print(f"  P75:    {r_p1b['p75']:+.1f}")
    print(f"  P90:    {r_p1b['p90']:+.1f}")

    print(f"\n  Worst 5 sessions:")
    for sid, pnl in r_p1b["worst5"].items():
        print(f"    Session {sid}: {pnl:+.1f} ticks")

    print(f"\n  Best 5 sessions:")
    for sid, pnl in r_p1b["best5"].items():
        print(f"    Session {sid}: {pnl:+.1f} ticks")

    print(f"\n  Max consecutive losing sessions: {r_p1b['max_losing_streak']}")

    # ===================================================================
    # Pass/Fail Determination
    # ===================================================================
    print(f"\n--- Pass/Fail Determination ---")

    checks = {
        "Net PF > 1.0": r_p1b["npf_1t"] > 1.0,
        "Gross PF > 1.05": r_p1b["gpf"] > 1.05,
        "Session win% > 55%": r_p1b["session_win_pct"] > 0.55,
        "Net PnL > 0": r_p1b["net_pnl"] > 0,
        "NPF within 30% of P1a": r_p1b["npf_1t"] > r_p1a["npf_1t"] * 0.70,
    }

    all_pass = True
    for check_name, passed in checks.items():
        status = "PASS" if passed else "FAIL"
        if not passed:
            all_pass = False
        print(f"  [{status}] {check_name}")

    # Conditional flags
    flags = []
    if 1.0 < r_p1b["npf_1t"] <= 1.05:
        flags.append("Net PF between 1.0-1.05: edge exists but very thin")
    if 0.50 < r_p1b["session_win_pct"] <= 0.55:
        flags.append("Session win% between 50-55%: high daily variance")
    if r_p1b["seed_accuracy"] < 0.70:
        flags.append(f"Seed accuracy {r_p1b['seed_accuracy']:.1%} < 70%: weaker directional detection")

    if all_pass and not flags:
        verdict = "PASS"
        print(f"\n  *** VERDICT: PASS ***")
    elif all_pass and flags:
        verdict = "CONDITIONAL_PASS"
        print(f"\n  *** VERDICT: CONDITIONAL PASS ***")
        for f in flags:
            print(f"  FLAG: {f}")
    else:
        verdict = "FAIL"
        failed = [k for k, v in checks.items() if not v]
        print(f"\n  *** VERDICT: FAIL ***")
        print(f"  Failed criteria: {', '.join(failed)}")

    # ===================================================================
    # STEP 3/4: Save Everything
    # ===================================================================
    print(f"\n--- Saving Artifacts ---")
    _OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # 1. Cycle-level parquet
    cycles_df = r_p1b.pop("_cycles_df")
    cyc_path = _OUTPUT_DIR / "p1b_seed_optimized_cycles.parquet"
    cycles_df.to_parquet(cyc_path, index=False)
    print(f"  Saved: {cyc_path} ({len(cycles_df)} cycles)")

    # 2. Session-level JSON
    session_data = {
        "sessions": r_p1b["session_pnl"],
        "total_sessions": r_p1b["sessions"],
        "mean_daily": r_p1b["mean_daily"],
        "std_daily": r_p1b["std_daily"],
        "session_win_pct": r_p1b["session_win_pct"],
    }
    sess_path = _OUTPUT_DIR / "p1b_seed_optimized_sessions.json"
    with open(sess_path, "w") as f:
        json.dump(session_data, f, indent=2, default=str)
    print(f"  Saved: {sess_path}")

    # 3. Validation result JSON
    # Remove non-serializable _cycles_df if still present
    r_p1a_clean = {k: v for k, v in r_p1a.items() if k != "_cycles_df"}
    r_p1b_clean = {k: v for k, v in r_p1b.items() if k != "_cycles_df"}

    validation = {
        "verdict": verdict,
        "flags": flags,
        "frozen_config": {
            "SeedDist": SEED_DIST,
            "StepDist": STEP_DIST,
            "flatten_reseed_cap": FLATTEN_CAP,
            "max_levels": MAX_LEVELS,
            "watch_mode": WATCH_MODE,
            "seed_sr_threshold": SEED_SR_THRESH,
            "reversal_sr_threshold": REV_SR_THRESH,
            "daily_flatten": "16:00 ET",
            "session_resume": "09:30 ET",
            "anchor_mode": "walking",
            "cost_ticks": COST_TICKS,
        },
        "p1a": r_p1a_clean,
        "p1b": r_p1b_clean,
        "pass_criteria": checks,
        "comparison_p1a_vs_p1b": {
            "npf_degradation_pct": round(
                (r_p1b["npf_1t"] - r_p1a["npf_1t"]) / r_p1a["npf_1t"] * 100, 2
            ),
            "net_pnl_delta": r_p1b["net_pnl"] - r_p1a["net_pnl"],
        },
    }
    val_path = _OUTPUT_DIR / "p1b_seed_validation_result.json"
    with open(val_path, "w") as f:
        json.dump(validation, f, indent=2, default=str)
    print(f"  Saved: {val_path}")

    print(f"\n{'='*70}")
    print(f"  FINAL VERDICT: {verdict}")
    print(f"{'='*70}")


if __name__ == "__main__":
    main()
