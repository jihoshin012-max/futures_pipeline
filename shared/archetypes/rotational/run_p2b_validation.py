# archetype: rotational
# STATUS: ONE-TIME
# PURPOSE: P2b final holdout validation (one run, no re-runs)
# LAST RUN: 2026-03

"""P2b Validation: One-shot V1.4 + 4C stop (max_cap_walks=2) on P2b holdout.

P2b = Feb 2, 2026 to Mar 13, 2026 (30 sessions).
This is the FINAL holdout. ONE RUN. NO RE-RUNS.

Steps:
  1. P1 sanity check with stops (must match NPF=1.1724)
  2. P2b one-shot

Usage:
    python run_p2b_validation.py
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
    simulate_daily_flatten, load_data,
    COST_TICKS, TICK_SIZE, RTH_OPEN_TOD, FLATTEN_TOD, RESUME_TOD,
    _P1_START, _P1_END, FLATTEN_CAP, MAX_LEVELS,
)
from run_phase1_sweep import (
    build_zigzag_lookup, make_adaptive_lookup, make_std_lookup, analyze_step2,
)
from run_p2a_validation import (
    build_combined_speedread, build_combined_zigzag_lookup,
    SEED_DIST, STEP_DIST_INIT, ADD_DIST_INIT, SEED_START, SR_THRESHOLD,
    EXCLUDE_HOURS,
)

_OUTPUT_DIR = Path(__file__).parent / "phase1_results"
_P2_1TICK = _REPO / "stages/01-data/data/bar_data/tick/NQ_BarData_1tick_rot_P2.csv"

# P2b dates (second half of P2)
P2B_RTH_FIRST = dt_mod.date(2026, 2, 2)
P2B_RTH_LAST = dt_mod.date(2026, 3, 13)
P2B_DATA_START = dt_mod.date(2026, 2, 1)   # Include Sunday evening ETH
P2B_DATA_END = dt_mod.date(2026, 3, 13)

# Stop config from Task 2C
MAX_CAP_WALKS = 2

# P1 with stops known values
P1_STOPS_NPF = 1.1724
P1_STOPS_PNL = 18944


def load_p2b_tick_data(sr_bar_dts, sr_composite):
    """Load P2b 1-tick data and map SpeedRead. Same protocol as P2a."""
    print("  Loading P2 1-tick data...")
    t0 = time.time()
    tick_bars = load_bars(str(_P2_1TICK))
    print(f"    Total P2 ticks: {len(tick_bars):,} in {time.time() - t0:.1f}s")

    tick_data = tick_bars[
        (tick_bars['datetime'].dt.date >= P2B_DATA_START) &
        (tick_bars['datetime'].dt.date <= P2B_DATA_END)
    ].reset_index(drop=True)
    print(f"    P2b ticks (after filter): {len(tick_data):,}")

    prices = tick_data['Last'].values.astype(np.float64)
    dts = tick_data['datetime'].values
    hours = tick_data['datetime'].dt.hour.values.astype(np.int32)
    minutes = tick_data['datetime'].dt.minute.values.astype(np.int32)
    seconds = tick_data['datetime'].dt.second.values.astype(np.int32)
    tod_secs = hours * 3600 + minutes * 60 + seconds

    print("  Mapping SpeedRead to P2b tick data...")
    sr_ts = sr_bar_dts.astype('int64') // 10**9
    sr_comp = sr_composite.astype(np.float64)
    tick_ts = dts.astype('int64') // 10**9
    sr_idx = np.clip(np.searchsorted(sr_ts, tick_ts, side='right') - 1,
                     0, len(sr_comp) - 1)
    tick_sr = sr_comp[sr_idx]
    tick_sr = np.nan_to_num(tick_sr, nan=-1.0)

    valid_sr = (tick_sr >= 0).sum()
    print(f"    SpeedRead mapped. Valid: {valid_sr:,} / {len(tick_sr):,}")

    cs = np.cumsum(np.insert(tick_sr, 0, 0))
    w = 50
    sr_roll50 = np.empty_like(tick_sr)
    sr_roll50[:w] = cs[1:w + 1] / np.arange(1, w + 1)
    sr_roll50[w:] = (cs[w + 1:] - cs[1:len(tick_sr) - w + 1]) / w

    print(f"    Date range: {tick_data['datetime'].iloc[0]} to {tick_data['datetime'].iloc[-1]}")
    dead_mask = (tod_secs >= FLATTEN_TOD) & (tod_secs < RESUME_TOD)
    print(f"    Ticks in dead zone: {dead_mask.sum():,}")

    return prices, tod_secs, sr_roll50, dts


def run_sim(prices, tod_secs, sr_roll50, dts, adaptive, std_lu):
    """Run V1.4 + 4C stop."""
    return simulate_daily_flatten(
        prices, tod_secs, sr_roll50, dts,
        seed_dist=SEED_DIST, step_dist=STEP_DIST_INIT, add_dist=ADD_DIST_INIT,
        flatten_reseed_cap=FLATTEN_CAP, max_levels=MAX_LEVELS,
        seed_sr_thresh=SR_THRESHOLD, rev_sr_thresh=SR_THRESHOLD,
        watch_mode='rth_open', cap_action='walk',
        seed_start_tod=SEED_START,
        adaptive_lookup=adaptive,
        max_adverse_sigma=None,
        max_cap_walks=MAX_CAP_WALKS,
        std_lookup=std_lu,
    )


def build_filtered_cycles(sim):
    trades = pd.DataFrame(sim['trade_records'])
    cycles = pd.DataFrame(sim['cycle_records'])
    if len(cycles) == 0:
        return None, trades
    entry_trades = trades[trades['action'].isin(['SEED', 'REVERSAL'])]
    ce = entry_trades.groupby('cycle_id')['datetime'].first().reset_index()
    ce.columns = ['cycle_id', 'entry_dt']
    cycles = cycles.merge(ce, on='cycle_id', how='left')
    cycles['hour'] = pd.to_datetime(cycles['entry_dt']).dt.hour
    cf = cycles[~cycles['hour'].isin(EXCLUDE_HOURS)].copy()
    if len(cf) == 0:
        return None, trades
    valid_ids = set(cf['cycle_id'])
    tf = trades[trades['cycle_id'].isin(valid_ids)]
    cc = tf.groupby('cycle_id')['cost_ticks'].sum()
    cf['cost'] = cf['cycle_id'].map(cc).fillna(0)
    cf['net_1t'] = cf['gross_pnl_ticks'] - cf['cost']
    return cf, trades


def main():
    t0_total = time.time()
    print("=" * 70)
    print("P2b VALIDATION (ONE-SHOT) — V1.4 + 4C Stop (max_cap_walks=2)")
    print("  Adaptive P90/P75, SeedDist=15, 10:00-16:00 ET,")
    print("  Roll50 SR>=48 (seed+rev), ML=1, cap=2, cost_ticks=1")
    print(f"  P2b: {P2B_RTH_FIRST} to {P2B_RTH_LAST}")
    print("=" * 70)

    # ================================================================
    # Step 1: P1 sanity check WITH stops
    # ================================================================
    print("\n" + "=" * 70)
    print("STEP 1: P1 Sanity Check (V1.4 + 4C stop)")
    print("=" * 70)

    print("  Loading P1 data...")
    prices_p1, tod_p1, sr_p1, dts_p1 = load_data(period='full_p1', use_speedread=True)
    zz_p1 = build_zigzag_lookup()
    adaptive_p1 = make_adaptive_lookup(zz_p1, 5, 2)
    std_p1 = make_std_lookup(zz_p1)

    cs = np.cumsum(np.insert(sr_p1, 0, 0))
    w = 50
    sr_roll50_p1 = np.empty_like(sr_p1)
    sr_roll50_p1[:w] = cs[1:w + 1] / np.arange(1, w + 1)
    sr_roll50_p1[w:] = (cs[w + 1:] - cs[1:len(sr_p1) - w + 1]) / w

    print("  Running V1.4 + 4C on P1...")
    sim_p1 = run_sim(prices_p1, tod_p1, sr_roll50_p1, dts_p1, adaptive_p1, std_p1)
    r_p1 = analyze_step2(sim_p1, "P1_with_stops")

    print(f"\n  P1 + stops: NPF={r_p1['npf_1t']:.4f} (expected {P1_STOPS_NPF:.4f}),"
          f" PnL={r_p1['net_pnl']:+,.0f} (expected {P1_STOPS_PNL:+,})")
    print(f"  Stops 4C: {sim_p1['stops_4c']}")

    npf_delta = abs(r_p1['npf_1t'] - P1_STOPS_NPF) / P1_STOPS_NPF
    if npf_delta > 0.05:
        print(f"\n  FAIL: NPF deviation {npf_delta:.1%} > 5%")
        sys.exit(1)
    print(f"  PASS: NPF deviation {npf_delta:.1%}")

    # ================================================================
    # Step 2: P2b ONE-SHOT
    # ================================================================
    print("\n" + "=" * 70)
    print("STEP 2: P2b Validation (ONE-SHOT)")
    print("=" * 70)

    # Build P2b data (same warm-up protocol as P2a)
    sr_bar_dts, sr_composite = build_combined_speedread()
    zz_lookup = build_combined_zigzag_lookup()
    adaptive = make_adaptive_lookup(zz_lookup, 5, 2)
    std_lu = make_std_lookup(zz_lookup)

    prices, tod_secs, sr_roll50, dts = load_p2b_tick_data(sr_bar_dts, sr_composite)

    print("\n  Running V1.4 + 4C on P2b (ONE-SHOT)...")
    t0_sim = time.time()
    sim = run_sim(prices, tod_secs, sr_roll50, dts, adaptive, std_lu)
    print(f"  Simulation done in {time.time() - t0_sim:.1f}s")

    r = analyze_step2(sim, "P2b_validation")
    if r is None:
        print("  ERROR: No valid cycles!")
        sys.exit(1)

    cf, trades_df = build_filtered_cycles(sim)

    # Session-level analysis
    session_pnl = cf.groupby('session_id')['net_1t'].sum()
    all_sids = range(1, sim['total_sessions'] + 1)
    session_pnl_full = session_pnl.reindex(all_sids, fill_value=0.0)

    trades_df['dt'] = pd.to_datetime(trades_df['datetime'])
    rth_trades = trades_df[(trades_df['dt'].dt.hour >= 9) & (trades_df['dt'].dt.hour < 17)]
    session_date_map = (rth_trades.groupby('session_id')['dt']
                        .first().apply(lambda x: x.strftime('%Y-%m-%d')).to_dict())

    pvals = session_pnl_full.values
    p10, p25, p50, p75, p90 = np.percentile(pvals, [10, 25, 50, 75, 90])
    worst5 = session_pnl_full.nsmallest(5)
    best5 = session_pnl_full.nlargest(5)

    gross_pnl = float(cf['gross_pnl_ticks'].sum())
    gw = cf.loc[cf['gross_pnl_ticks'] > 0, 'gross_pnl_ticks'].sum()
    gl = abs(cf.loc[cf['gross_pnl_ticks'] <= 0, 'gross_pnl_ticks'].sum())
    gpf = gw / gl if gl > 0 else 0

    stopped_4c = cf[cf['exit_reason'] == 'stop_4c']
    capwalk_rate = (cf['cycle_cap_walks'] > 0).mean() if 'cycle_cap_walks' in cf.columns else 0
    worst_day = float(session_pnl_full.min())

    # ---- Print results ----
    print(f"\n  {'=' * 60}")
    print(f"  P2b RESULTS (ONE-SHOT, V1.4 + 4C max_cap_walks=2)")
    print(f"  {'=' * 60}")
    print(f"  Cycles:          {r['cycles']:,}")
    print(f"  Gross PF:        {gpf:.4f}")
    print(f"  Net PF @1t:      {r['npf_1t']:.4f}")
    print(f"  Net PnL:         {r['net_pnl']:+,.0f} ticks")
    print(f"  Gross PnL:       {gross_pnl:+,.0f} ticks")
    print(f"  Sessions:        {r['sessions']}")
    print(f"  Mean daily PnL:  {r['mean_daily']:.1f}")
    print(f"  Std daily:       {r['std_daily']:.1f}")
    print(f"  Session win %:   {r['session_win_pct']:.2%}")
    print(f"  Clean %:         {r['clean_pct']:.2%}")
    print(f"  Cap-walk rate:   {capwalk_rate:.1%}")
    print(f"  Mean MAE:        {r['mean_mae']:.2f}")
    print(f"  Worst day:       {worst_day:+,.0f}")
    print(f"  Max cycle loss:  {r['max_single_cycle_loss']:,.0f}")
    print(f"  Stopped by 4C:   {len(stopped_4c)}")

    print(f"\n  Adaptive ranges on P2b:")
    print(f"    StepDist: min={r['sd_range']['min']:.1f},"
          f" max={r['sd_range']['max']:.1f}, mean={r['sd_range']['mean']:.1f}")
    print(f"    AddDist:  min={r['ad_range']['min']:.1f},"
          f" max={r['ad_range']['max']:.1f}, mean={r['ad_range']['mean']:.1f}")

    print(f"\n  Distribution (per-session PnL):")
    print(f"    P10={p10:.0f}  P25={p25:.0f}  P50={p50:.0f}  P75={p75:.0f}  P90={p90:.0f}")

    print(f"\n  Worst 5 sessions:")
    for sid, pnl in worst5.items():
        print(f"    {session_date_map.get(sid, f'sid={sid}')}: {pnl:+,.0f}")

    print(f"\n  Best 5 sessions:")
    for sid, pnl in best5.items():
        print(f"    {session_date_map.get(sid, f'sid={sid}')}: {pnl:+,.0f}")

    print(f"\n  EV components:")
    print(f"    Clean:   {r['ev_clean']['pct']:.2%}, mean PnL={r['ev_clean']['mean_pnl']:.1f}")
    print(f"    1-Add:   {r['ev_1add']['pct']:.2%}, mean PnL={r['ev_1add']['mean_pnl']:.1f}")
    print(f"    CapWalk: {r['ev_capwalk']['pct']:.2%}, mean PnL={r['ev_capwalk']['mean_pnl']:.1f}")
    print(f"    Deep:    {r['ev_deep']['pct']:.2%}, mean PnL={r['ev_deep']['mean_pnl']:.1f}")

    # ---- Comparison table ----
    print(f"\n  {'=' * 60}")
    print(f"  COMPARISON TABLE")
    print(f"  {'=' * 60}")
    print(f"  {'Metric':<20} {'P1 (stops)':>12} {'P2a (no stops)':>14} {'P2b (stops)':>12}")
    print(f"  {'-' * 58}")
    print(f"  {'NPF @1t':<20} {r_p1['npf_1t']:>12.4f} {'0.9577':>14} {r['npf_1t']:>12.4f}")
    print(f"  {'Net PnL':<20} {r_p1['net_pnl']:>12,.0f} {'-1,797':>14} {r['net_pnl']:>12,.0f}")
    print(f"  {'Gross PF':<20} {r_p1['gpf']:>12.4f} {'1.0058':>14} {gpf:>12.4f}")
    print(f"  {'Cycles':<20} {r_p1['cycles']:>12,} {'667':>14} {r['cycles']:>12,}")
    print(f"  {'Session win %':<20} {r_p1['session_win_pct']:>12.1%} {'46.4%':>14} {r['session_win_pct']:>12.1%}")
    print(f"  {'Worst day':<20} {'-':>12} {'-3,055':>14} {worst_day:>12,.0f}")
    print(f"  {'Cap-walk %':<20} {'-':>12} {'28.0%':>14} {capwalk_rate:>12.1%}")
    print(f"  {'Stopped 4C':<20} {sim_p1['stops_4c']:>12} {'N/A':>14} {len(stopped_4c):>12}")

    # ---- Pass/Fail ----
    print(f"\n  {'=' * 60}")
    print(f"  PASS/FAIL DETERMINATION")
    print(f"  {'=' * 60}")

    pass_all = True
    flags = []
    fail_reasons = []

    if r['npf_1t'] > 1.0:
        print(f"  [PASS] NPF = {r['npf_1t']:.4f} > 1.0")
    else:
        print(f"  [FAIL] NPF = {r['npf_1t']:.4f} < 1.0")
        fail_reasons.append(f"NPF {r['npf_1t']:.4f} < 1.0")
        pass_all = False

    if gpf > 1.05:
        print(f"  [PASS] Gross PF = {gpf:.4f} > 1.05")
    else:
        print(f"  [FAIL] Gross PF = {gpf:.4f} < 1.05")
        fail_reasons.append(f"Gross PF {gpf:.4f} < 1.05")
        pass_all = False

    if r['session_win_pct'] > 0.50:
        print(f"  [PASS] Session win % = {r['session_win_pct']:.2%} > 50%")
    elif r['session_win_pct'] >= 0.45:
        print(f"  [FLAG] Session win % = {r['session_win_pct']:.2%} between 45-50%")
        flags.append(f"Session win% {r['session_win_pct']:.2%}")
    else:
        print(f"  [FAIL] Session win % = {r['session_win_pct']:.2%} < 45%")
        fail_reasons.append(f"Session win% < 45%")
        pass_all = False

    if r['net_pnl'] > 0:
        print(f"  [PASS] Net PnL = {r['net_pnl']:+,.0f} > 0")
    else:
        print(f"  [FAIL] Net PnL = {r['net_pnl']:+,.0f} <= 0")
        fail_reasons.append(f"Net PnL <= 0")
        pass_all = False

    if worst_day > -3055:
        print(f"  [PASS] Worst day = {worst_day:+,.0f} > P2a worst (-3,055)")
    else:
        print(f"  [FLAG] Worst day = {worst_day:+,.0f} not better than P2a")
        flags.append(f"Worst day {worst_day:+,.0f}")

    # Conditional flags
    if 1.0 < r['npf_1t'] <= 1.05:
        flags.append(f"NPF {r['npf_1t']:.4f} thin (1.0-1.05)")
    if gpf < 1.05 and gpf > 1.0:
        flags.append(f"Gross PF {gpf:.4f} marginal — stops masking structural weakness")

    verdict = "PASS" if pass_all and not fail_reasons else ("CONDITIONAL PASS" if pass_all else "FAIL")
    if flags and pass_all:
        verdict = "CONDITIONAL PASS"

    print(f"\n  VERDICT: {verdict}")
    for f in flags:
        print(f"    FLAG: {f}")
    for f in fail_reasons:
        print(f"    REASON: {f}")

    # Interpretation
    print(f"\n  Gross PF interpretation:")
    if gpf > 1.15:
        print(f"    Gross PF {gpf:.4f} > 1.15 (P1-like) — P2a was a regime dip.")
    elif gpf > 1.0:
        print(f"    Gross PF {gpf:.4f} moderate — rotation edge exists but thinner than P1.")
    else:
        print(f"    Gross PF {gpf:.4f} < 1.0 — regime compression continues.")

    # ---- Save ----
    print(f"\n  Saving results...")
    _OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Cycle parquet
    cf.to_parquet(str(_OUTPUT_DIR / "p2b_validation_cycles.parquet"), index=False)

    # Session JSON
    session_summary = []
    for sid in all_sids:
        s_cycles = cf[cf['session_id'] == sid]
        session_summary.append({
            "session_id": int(sid),
            "date": session_date_map.get(sid, None),
            "net_pnl": round(float(session_pnl_full.get(sid, 0)), 1),
            "cycles": len(s_cycles),
            "clean_cycles": int((s_cycles['adds_count'] == 0).sum()) if len(s_cycles) > 0 else 0,
        })
    with open(_OUTPUT_DIR / "p2b_validation_sessions.json", 'w') as f:
        json.dump(session_summary, f, indent=2)

    # Result JSON
    result = {
        "validation": "P2b",
        "verdict": verdict,
        "run_date": dt_mod.datetime.now().isoformat(),
        "frozen_config": {
            "version": "V1.4 + 4C stop",
            "step_dist": "rolling_zigzag_P90 (floor 10)",
            "add_dist": "rolling_zigzag_P75 (floor 10)",
            "seed_dist": SEED_DIST,
            "session": "10:00-16:00 ET",
            "speedread": f"Roll50 >= {SR_THRESHOLD}",
            "max_levels": MAX_LEVELS,
            "position_cap": FLATTEN_CAP,
            "cap_action": "walk",
            "cost_ticks": COST_TICKS,
            "max_cap_walks": MAX_CAP_WALKS,
            "max_adverse_sigma": None,
        },
        "p2b_date_range": {
            "first_rth": str(P2B_RTH_FIRST),
            "last_rth": str(P2B_RTH_LAST),
            "sessions": r['sessions'],
        },
        "p2b_metrics": {
            "cycles": r['cycles'], "gpf": round(gpf, 4),
            "npf_1t": r['npf_1t'], "net_pnl": r['net_pnl'],
            "gross_pnl": round(gross_pnl, 1),
            "mean_daily": r['mean_daily'], "std_daily": r['std_daily'],
            "session_win_pct": r['session_win_pct'],
            "clean_pct": r['clean_pct'], "mean_mae": r['mean_mae'],
            "worst_day": round(worst_day, 1),
            "max_single_cycle_loss": r['max_single_cycle_loss'],
            "capwalk_rate": round(float(capwalk_rate), 4),
            "stopped_4c": len(stopped_4c),
        },
        "p1_with_stops": {
            "npf_1t": r_p1['npf_1t'], "net_pnl": r_p1['net_pnl'],
            "gpf": r_p1['gpf'], "cycles": r_p1['cycles'],
            "stopped_4c": sim_p1['stops_4c'],
        },
        "adaptive_ranges": {
            "stepdist": r['sd_range'], "adddist": r['ad_range'],
        },
        "distribution": {
            "p10": round(p10, 1), "p25": round(p25, 1), "p50": round(p50, 1),
            "p75": round(p75, 1), "p90": round(p90, 1),
        },
        "worst5": {session_date_map.get(k, f"sid={k}"): round(v, 1)
                   for k, v in worst5.items()},
        "best5": {session_date_map.get(k, f"sid={k}"): round(v, 1)
                  for k, v in best5.items()},
        "ev_components": {
            "clean": r['ev_clean'], "one_add": r['ev_1add'],
            "capwalk": r['ev_capwalk'], "deep": r['ev_deep'],
        },
        "pass_fail": {"verdict": verdict, "flags": flags, "fail_reasons": fail_reasons},
        "contamination_update": (
            f"P2b: V1.4 + 4C(maxcw=2) | {verdict} | "
            f"P2b dates {P2B_RTH_FIRST} to {P2B_RTH_LAST} consumed. "
            f"NO CLEAN HOLDOUT REMAINING."
        ),
    }
    with open(_OUTPUT_DIR / "p2b_validation_result.json", 'w') as f:
        json.dump(result, f, indent=2, default=str)

    print(f"    p2b_validation_cycles.parquet")
    print(f"    p2b_validation_sessions.json")
    print(f"    p2b_validation_result.json")

    print(f"\n  Contamination ledger:")
    print(f"    {result['contamination_update']}")

    print(f"\n{'=' * 60}")
    print(f"P2b VALIDATION COMPLETE: {verdict}")
    print(f"NO CLEAN HOLDOUT REMAINING.")
    print(f"{'=' * 60}")
    print(f"\nTotal time: {time.time() - t0_total:.1f}s")


if __name__ == "__main__":
    main()
