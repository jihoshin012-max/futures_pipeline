# archetype: rotational
# STATUS: ONE-TIME
# PURPOSE: P2a one-shot validation of frozen V1.4 config
# LAST RUN: 2026-03

"""P2a Validation: One-shot frozen V1.4 config on P2a holdout.

Three steps (run in order):
  Step 0: Verify compute_speedread() matches existing parquet (spot-check)
  Step 1: P1 sanity check (NPF approx 1.200 +/- 5%)
  Step 2: P2a one-shot (frozen params, no re-runs)

Usage:
    python run_p2a_validation.py --verify-sr    # Step 0 only
    python run_p2a_validation.py --p1-sanity    # Step 1 only
    python run_p2a_validation.py --p2a          # Step 2 only
    python run_p2a_validation.py --all          # All steps sequentially
"""

import sys
import json
import time
import argparse
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
    _P1_START, _P1_END, FLATTEN_CAP, MAX_LEVELS, INIT_QTY,
)
from run_phase1_sweep import (
    build_zigzag_lookup, make_adaptive_lookup, analyze_step2,
)
from run_speedread_investigation import compute_speedread

# ============================================================
# Constants
# ============================================================

_P1_250TICK = _REPO / "stages/01-data/data/bar_data/tick/NQ_BarData_250tick_rot_P1.csv"
_P2_250TICK = _REPO / "stages/01-data/data/bar_data/tick/NQ_BarData_250tick_rot_P2.csv"
_P2_1TICK = _REPO / "stages/01-data/data/bar_data/tick/NQ_BarData_1tick_rot_P2.csv"
_SR_PARQUET = Path(__file__).parent / "speedread_results" / "speedread_250tick.parquet"
_OUTPUT_DIR = Path(__file__).parent / "phase1_results"

# P2a/P2b split: 30 sessions each (60 total P2 sessions)
P2A_RTH_FIRST = dt_mod.date(2025, 12, 18)
P2A_RTH_LAST = dt_mod.date(2026, 1, 30)
P2A_DATA_START = dt_mod.date(2025, 12, 17)  # Evening session before first P2a RTH
P2A_DATA_END = dt_mod.date(2026, 1, 30)     # Through last P2a RTH day

# Frozen V1.4 parameters
SEED_DIST = 15.0
STEP_DIST_INIT = 25.0   # Initial (overridden by adaptive lookup at each entry)
ADD_DIST_INIT = 25.0     # Initial (overridden by adaptive lookup at each entry)
SEED_START = 10 * 3600   # 10:00 ET = 36000
SR_THRESHOLD = 48.0

EXCLUDE_HOURS = {1, 19, 20}

# P1 known values for sanity check (V1.4 Roll50 SR>=48)
P1_EXPECTED_NPF = 1.200
P1_EXPECTED_PNL = 20919
P1_NPF_TOLERANCE = 0.05  # +/- 5%


# ============================================================
# Step 0: SpeedRead Verification
# ============================================================

def verify_speedread():
    """Verify compute_speedread() matches existing parquet on P1 data.

    Spot-checks 500 bars from mid-P1. Max composite deviation must be <= 0.5.
    """
    print("\n" + "=" * 70)
    print("STEP 0: SpeedRead Verification (500-bar spot-check)")
    print("=" * 70)

    t0 = time.time()

    print("  Loading P1 250-tick bars...")
    p1_bars = load_bars(str(_P1_250TICK))
    close = p1_bars["Last"].values.astype(np.float64)
    volume = p1_bars["Volume"].values.astype(np.float64)
    n_bars = len(close)
    print(f"  P1 250-tick bars: {n_bars:,}")

    print("  Computing SpeedRead from Python...")
    composite, raw, ps, vs, _, _, _ = compute_speedread(close, volume)

    print("  Loading existing SpeedRead parquet...")
    sr_df = pd.read_parquet(_SR_PARQUET)
    parquet_comp = sr_df["speedread_composite"].values
    n_parquet = len(parquet_comp)
    print(f"  Parquet rows: {n_parquet:,}")

    if n_bars != n_parquet:
        print(f"  WARNING: Row count mismatch — CSV {n_bars:,} vs parquet {n_parquet:,}")
        print(f"  Aligning by datetime for comparison...")
        # Align by datetime
        bar_dts = p1_bars["datetime"].values
        pq_dts = pd.to_datetime(sr_df["datetime"]).values
        # Find mid-P1 timestamp and search both arrays
        mid_dt = bar_dts[n_bars // 2]
        csv_start = max(0, n_bars // 2 - 250)
        csv_end = csv_start + 500
        pq_start = np.searchsorted(pq_dts, bar_dts[csv_start])
        pq_end = pq_start + 500
        py_slice = composite[csv_start:csv_end]
        pq_slice = parquet_comp[pq_start:pq_end]
    else:
        # 1:1 alignment by index
        mid = n_bars // 2
        start = mid - 250
        end = mid + 250
        py_slice = composite[start:end]
        pq_slice = parquet_comp[start:end]
        print(f"  Spot-check window: bars {start:,} to {end:,}")

    # Compare only where both are valid (not NaN)
    valid = ~np.isnan(py_slice) & ~np.isnan(pq_slice)
    n_valid = valid.sum()

    if n_valid == 0:
        print("  ERROR: No valid overlapping values in spot-check window!")
        return False

    delta = np.abs(py_slice[valid] - pq_slice[valid])
    max_delta = delta.max()
    mean_delta = delta.mean()
    p95_delta = np.percentile(delta, 95)

    print(f"  Valid comparisons: {n_valid} / 500")
    print(f"  Max  |delta|: {max_delta:.6f}")
    print(f"  P95  |delta|: {p95_delta:.6f}")
    print(f"  Mean |delta|: {mean_delta:.6f}")
    print(f"  Time: {time.time() - t0:.1f}s")

    if max_delta > 0.5:
        print(f"\n  FAIL: Max delta {max_delta:.4f} > 0.5 threshold!")
        # Show worst disagreements for debugging
        worst_idx = np.argsort(delta)[-5:]
        print(f"  Worst 5 disagreements:")
        for wi in worst_idx:
            actual_idx = np.where(valid)[0][wi]
            print(f"    bar offset {actual_idx}: py={py_slice[actual_idx]:.4f}, "
                  f"pq={pq_slice[actual_idx]:.4f}, delta={delta[wi]:.4f}")
        return False

    print(f"\n  PASS: Max delta {max_delta:.6f} <= 0.5")
    return True


# ============================================================
# Step 1: P1 Sanity Check
# ============================================================

def p1_sanity_check():
    """Reproduce V1.4 frozen config on full P1. Verify NPF approx 1.200 +/- 5%."""
    print("\n" + "=" * 70)
    print("STEP 1: P1 Sanity Check (V1.4 frozen config)")
    print("=" * 70)

    t0 = time.time()

    # Exact same code path as run_phase2_risk.py
    print("  Loading P1 tick data with SpeedRead...")
    prices, tod_secs, sr_vals, dts = load_data(period='full_p1', use_speedread=True)

    print("  Building zigzag lookup (P1 only)...")
    zz_lookup = build_zigzag_lookup()
    adaptive = make_adaptive_lookup(zz_lookup, 5, 2)  # P90, P75

    # Roll50 — identical to run_phase2_risk.py lines 40-44
    cs = np.cumsum(np.insert(sr_vals, 0, 0))
    w = 50
    sr_roll50 = np.empty_like(sr_vals)
    sr_roll50[:w] = cs[1:w + 1] / np.arange(1, w + 1)
    sr_roll50[w:] = (cs[w + 1:] - cs[1:len(sr_vals) - w + 1]) / w

    # Run simulation — identical call to run_phase2_risk.py lines 48-56
    print("  Running frozen V1.4 on full P1...")
    sim = simulate_daily_flatten(
        prices, tod_secs, sr_roll50, dts,
        seed_dist=SEED_DIST, step_dist=STEP_DIST_INIT, add_dist=ADD_DIST_INIT,
        flatten_reseed_cap=FLATTEN_CAP, max_levels=MAX_LEVELS,
        seed_sr_thresh=SR_THRESHOLD, rev_sr_thresh=SR_THRESHOLD,
        watch_mode='rth_open', cap_action='walk',
        seed_start_tod=SEED_START,
        adaptive_lookup=adaptive,
    )

    r = analyze_step2(sim, "P1_sanity_check")

    print(f"\n  P1 Results:")
    print(f"    NPF @1t:     {r['npf_1t']:.4f}  (expected ~ {P1_EXPECTED_NPF:.3f})")
    print(f"    Net PnL:     {r['net_pnl']:,.0f}  (expected ~ {P1_EXPECTED_PNL:,})")
    print(f"    Gross PF:    {r['gpf']:.4f}")
    print(f"    Cycles:      {r['cycles']:,}")
    print(f"    Sessions:    {r['sessions']}")
    print(f"    Session win: {r['session_win_pct']:.2%}")
    print(f"    Clean %:     {r['clean_pct']:.2%}")
    print(f"    Mean MAE:    {r['mean_mae']:.2f}")
    print(f"    SD range:    {r['sd_range']['min']:.1f} - {r['sd_range']['max']:.1f} (mean {r['sd_range']['mean']:.1f})")
    print(f"    AD range:    {r['ad_range']['min']:.1f} - {r['ad_range']['max']:.1f} (mean {r['ad_range']['mean']:.1f})")
    print(f"    Time:        {time.time() - t0:.1f}s")

    npf_delta = abs(r['npf_1t'] - P1_EXPECTED_NPF) / P1_EXPECTED_NPF
    if npf_delta > P1_NPF_TOLERANCE:
        print(f"\n  FAIL: NPF deviation {npf_delta:.1%} > {P1_NPF_TOLERANCE:.0%} tolerance!")
        print(f"    Expected: ~{P1_EXPECTED_NPF:.4f}, Got: {r['npf_1t']:.4f}")
        print("  Simulator code may have changed since Phase 2.")
        return None

    print(f"\n  PASS: NPF deviation {npf_delta:.1%} within +/-{P1_NPF_TOLERANCE:.0%}")
    return r


# ============================================================
# Step 2: P2a Validation — Data Builders
# ============================================================

def build_combined_speedread():
    """Compute SpeedRead on concatenated P1+P2 250-tick bars.

    P1 bars provide warm-up (200-bar median normalization window).
    Returns (bar_datetimes_int64_ns, composite_values) for tick-level mapping.
    """
    print("  Loading P1 250-tick bars (SpeedRead warm-up)...")
    p1_bars = load_bars(str(_P1_250TICK))
    print(f"    P1: {len(p1_bars):,} bars")

    print("  Loading P2 250-tick bars...")
    p2_bars = load_bars(str(_P2_250TICK))
    print(f"    P2: {len(p2_bars):,} bars")

    # Concatenate on common columns, sorted by time
    cols = ['datetime', 'Last', 'Volume']
    combined = pd.concat([p1_bars[cols], p2_bars[cols]], ignore_index=True)
    combined = combined.sort_values('datetime').reset_index(drop=True)
    n_combined = len(combined)
    print(f"    Combined: {n_combined:,} bars")

    close = combined['Last'].values.astype(np.float64)
    volume = combined['Volume'].values.astype(np.float64)

    print("  Computing SpeedRead on combined P1+P2...")
    t0 = time.time()
    composite, _, _, _, _, _, _ = compute_speedread(close, volume)
    print(f"    Done in {time.time() - t0:.1f}s")

    # Return int64 nanosecond timestamps (same format load_data uses)
    bar_dts = combined['datetime'].values
    return bar_dts, composite


def build_combined_zigzag_lookup():
    """Build rolling 200-swing zigzag percentiles spanning P1 through P2.

    Uses ALL P1 RTH bars (09:30-16:00) for warm-up + ALL P2 RTH bars.
    Swing extraction logic is identical to build_zigzag_lookup() in
    run_phase1_sweep.py — processing the concatenated series ensures
    the P1→P2 boundary swing is handled correctly.
    """
    print("  Loading P1 250-tick bars (zigzag warm-up)...")
    p1_bars = load_bars(str(_P1_250TICK))

    print("  Loading P2 250-tick bars (zigzag)...")
    p2_bars = load_bars(str(_P2_250TICK))

    # Concatenate on common columns
    cols = ['datetime', 'Zig Zag Line Length']
    combined = pd.concat([p1_bars[cols], p2_bars[cols]], ignore_index=True)
    combined = combined.sort_values('datetime').reset_index(drop=True)

    # Filter to RTH (09:30-16:00 ET)
    tod = combined['datetime'].dt.hour * 3600 + combined['datetime'].dt.minute * 60
    rth_mask = (tod >= RTH_OPEN_TOD) & (tod < FLATTEN_TOD)
    rth = combined[rth_mask].copy()
    print(f"    RTH bars (P1+P2): {len(rth):,}")

    # Extract swing completions — identical logic to build_zigzag_lookup()
    zz_len = rth['Zig Zag Line Length'].values
    dts_arr = rth['datetime'].values

    swings = []
    curr_sign, curr_max, curr_dt = 0, 0.0, None
    for i in range(len(zz_len)):
        v = zz_len[i]
        if v == 0:
            if curr_max > 0:
                swings.append((curr_dt, curr_max))
            curr_max, curr_sign = 0.0, 0
        else:
            s = 1 if v > 0 else -1
            av = abs(v)
            if s != curr_sign:
                if curr_max > 0:
                    swings.append((curr_dt, curr_max))
                curr_sign, curr_max, curr_dt = s, av, dts_arr[i]
            elif av > curr_max:
                curr_max, curr_dt = av, dts_arr[i]
    if curr_max > 0:
        swings.append((curr_dt, curr_max))

    swing_dts = np.array([s[0] for s in swings])
    swing_lens = np.array([s[1] for s in swings], dtype=np.float64)
    print(f"    Total RTH swings (P1+P2): {len(swing_lens):,}")

    # Rolling 200-swing percentiles — identical to build_zigzag_lookup()
    WINDOW = 200
    pct_levels = [65, 70, 75, 80, 85, 90]
    start_idx = WINDOW
    n_pts = len(swing_lens) - start_idx

    pct_ts = np.empty(n_pts, dtype='int64')
    pct_vals = np.empty((n_pts, len(pct_levels)), dtype=np.float64)

    for j in range(n_pts):
        idx = start_idx + j
        window = swing_lens[idx - WINDOW:idx]
        pct_ts[j] = swing_dts[idx].astype('int64')
        pct_vals[j] = np.percentile(window, pct_levels)

    print(f"    Rolling percentile points: {n_pts:,}")

    return {
        'swing_dts': swing_dts, 'swing_lens': swing_lens,
        'pct_ts': pct_ts, 'pct_vals': pct_vals, 'pct_levels': pct_levels,
    }


def load_p2a_tick_data(sr_bar_dts, sr_composite):
    """Load P2a 1-tick data and map SpeedRead composite to tick level.

    SpeedRead mapping is identical to load_data() in run_seed_investigation.py:
    binary search on 250-tick bar timestamps, NaN replaced with -1.0.
    Roll50 computation is identical to run_phase2_risk.py lines 40-44.

    Returns (prices, tod_secs, sr_roll50, dts).
    """
    print("  Loading P2 1-tick data...")
    t0 = time.time()
    tick_bars = load_bars(str(_P2_1TICK))
    print(f"    Total P2 ticks: {len(tick_bars):,} in {time.time() - t0:.1f}s")

    # Filter to P2a dates
    tick_data = tick_bars[
        (tick_bars['datetime'].dt.date >= P2A_DATA_START) &
        (tick_bars['datetime'].dt.date <= P2A_DATA_END)
    ].reset_index(drop=True)
    print(f"    P2a ticks (after filter): {len(tick_data):,}")

    # Extract arrays — same as load_data()
    prices = tick_data['Last'].values.astype(np.float64)
    dts = tick_data['datetime'].values
    hours = tick_data['datetime'].dt.hour.values.astype(np.int32)
    minutes = tick_data['datetime'].dt.minute.values.astype(np.int32)
    seconds = tick_data['datetime'].dt.second.values.astype(np.int32)
    tod_secs = hours * 3600 + minutes * 60 + seconds

    # Map SpeedRead to tick level — identical to load_data() lines 705-712
    print("  Mapping SpeedRead to P2a tick data...")
    sr_ts = sr_bar_dts.astype('int64') // 10**9
    sr_comp = sr_composite.astype(np.float64)
    tick_ts = dts.astype('int64') // 10**9
    sr_idx = np.clip(np.searchsorted(sr_ts, tick_ts, side='right') - 1,
                     0, len(sr_comp) - 1)
    tick_sr = sr_comp[sr_idx]
    tick_sr = np.nan_to_num(tick_sr, nan=-1.0)

    valid_sr = (tick_sr >= 0).sum()
    print(f"    SpeedRead mapped. Valid: {valid_sr:,} / {len(tick_sr):,}")

    # Roll50 — identical to run_phase2_risk.py lines 40-44
    cs = np.cumsum(np.insert(tick_sr, 0, 0))
    w = 50
    sr_roll50 = np.empty_like(tick_sr)
    sr_roll50[:w] = cs[1:w + 1] / np.arange(1, w + 1)
    sr_roll50[w:] = (cs[w + 1:] - cs[1:len(tick_sr) - w + 1]) / w

    first_dt = tick_data['datetime'].iloc[0]
    last_dt = tick_data['datetime'].iloc[-1]
    print(f"    Date range: {first_dt} to {last_dt}")

    dead_mask = (tod_secs >= FLATTEN_TOD) & (tod_secs < RESUME_TOD)
    print(f"    Ticks in dead zone (16:00-18:00): {dead_mask.sum():,}")

    return prices, tod_secs, sr_roll50, dts


# ============================================================
# Step 2: P2a Validation — Run & Report
# ============================================================

def run_p2a_validation(p1_result):
    """Run frozen V1.4 on P2a data. ONE-SHOT. No re-runs."""
    print("\n" + "=" * 70)
    print("STEP 2: P2a Validation (ONE-SHOT)")
    print("  Config: Adaptive P90/P75, SeedDist=15, 10:00-16:00 ET,")
    print("          Roll50 SR>=48 (seed+rev), ML=1, cap=2, cost_ticks=1")
    print(f"  P2a: {P2A_RTH_FIRST} to {P2A_RTH_LAST} (30 sessions)")
    print("=" * 70)

    t0_total = time.time()

    # Build SpeedRead from P1+P2 250-tick bars (P1 = warm-up)
    sr_bar_dts, sr_composite = build_combined_speedread()

    # Build zigzag lookup from P1+P2 250-tick bars (P1 = warm-up)
    zz_lookup = build_combined_zigzag_lookup()
    adaptive = make_adaptive_lookup(zz_lookup, 5, 2)  # idx 5 = P90, idx 2 = P75

    # Load P2a tick data with SpeedRead mapping and Roll50
    prices, tod_secs, sr_roll50, dts = load_p2a_tick_data(sr_bar_dts, sr_composite)

    # Run simulation — frozen V1.4 params, ONE-SHOT
    print("\n  Running frozen V1.4 on P2a (ONE-SHOT)...")
    t0_sim = time.time()
    sim = simulate_daily_flatten(
        prices, tod_secs, sr_roll50, dts,
        seed_dist=SEED_DIST,
        step_dist=STEP_DIST_INIT,
        add_dist=ADD_DIST_INIT,
        flatten_reseed_cap=FLATTEN_CAP,
        max_levels=MAX_LEVELS,
        seed_sr_thresh=SR_THRESHOLD,
        rev_sr_thresh=SR_THRESHOLD,
        watch_mode='rth_open',
        cap_action='walk',
        seed_start_tod=SEED_START,
        adaptive_lookup=adaptive,
    )
    print(f"  Simulation done in {time.time() - t0_sim:.1f}s")

    r = analyze_step2(sim, "P2a_validation")
    if r is None:
        print("  ERROR: No valid cycles in P2a simulation!")
        return None

    # ---- Extended analysis ----
    trades_df = pd.DataFrame(sim['trade_records'])
    cycles_df = pd.DataFrame(sim['cycle_records'])

    # Hour filter (same as analyze_step2)
    entry_trades = trades_df[trades_df['action'].isin(['SEED', 'REVERSAL'])]
    ce = entry_trades.groupby('cycle_id')['datetime'].first().reset_index()
    ce.columns = ['cycle_id', 'entry_dt']
    cycles_df = cycles_df.merge(ce, on='cycle_id', how='left')
    cycles_df['hour'] = pd.to_datetime(cycles_df['entry_dt']).dt.hour
    cf = cycles_df[~cycles_df['hour'].isin(EXCLUDE_HOURS)].copy()

    valid_ids = set(cf['cycle_id'])
    tf = trades_df[trades_df['cycle_id'].isin(valid_ids)]
    cc = tf.groupby('cycle_id')['cost_ticks'].sum()
    cf['cost'] = cf['cycle_id'].map(cc).fillna(0)
    cf['net_1t'] = cf['gross_pnl_ticks'] - cf['cost']

    # Map session_id to date
    trades_df['dt'] = pd.to_datetime(trades_df['datetime'])
    trades_df['hour_val'] = trades_df['dt'].dt.hour
    rth_trades = trades_df[(trades_df['hour_val'] >= 9) & (trades_df['hour_val'] < 17)]
    session_date_map = (rth_trades.groupby('session_id')['dt']
                        .first()
                        .apply(lambda x: x.strftime('%Y-%m-%d'))
                        .to_dict())

    # Per-session PnL
    session_pnl = cf.groupby('session_id')['net_1t'].sum()
    all_sids = range(1, sim['total_sessions'] + 1)
    session_pnl_full = session_pnl.reindex(all_sids, fill_value=0.0)

    pvals = session_pnl_full.values
    p10, p25, p50, p75, p90 = np.percentile(pvals, [10, 25, 50, 75, 90])

    worst5 = session_pnl_full.nsmallest(5)
    best5 = session_pnl_full.nlargest(5)

    # Seed accuracy
    first_actions = trades_df.groupby('cycle_id')['action'].first()
    seed_cids = first_actions[first_actions == 'SEED'].index
    seed_cf = cf[cf['cycle_id'].isin(seed_cids)]
    seed_accuracy = (seed_cf['gross_pnl_ticks'] > 0).mean() if len(seed_cf) > 0 else 0

    # SR filter activity
    sr_skips = len(cf[cf['exit_reason'] == 'reversal_sr_skip'])

    # ---- Print results ----
    print(f"\n  {'=' * 60}")
    print(f"  P2a RESULTS (ONE-SHOT, FROZEN V1.4)")
    print(f"  {'=' * 60}")
    print(f"  Cycles:          {r['cycles']:,}")
    print(f"  Gross PF:        {r['gpf']:.4f}")
    print(f"  Net PF @1t:      {r['npf_1t']:.4f}")
    print(f"  Net PnL:         {r['net_pnl']:,.0f} ticks")
    print(f"  Sessions:        {r['sessions']}")
    print(f"  Mean daily PnL:  {r['mean_daily']:.1f}")
    print(f"  Std daily:       {r['std_daily']:.1f}")
    print(f"  Session win %:   {r['session_win_pct']:.2%}")
    print(f"  Seed accuracy:   {seed_accuracy:.2%}")
    print(f"  Clean %:         {r['clean_pct']:.2%}")
    print(f"  Mean MAE:        {r['mean_mae']:.2f}")

    print(f"\n  Adaptive ranges on P2a:")
    print(f"    StepDist: min={r['sd_range']['min']:.2f}, "
          f"max={r['sd_range']['max']:.2f}, mean={r['sd_range']['mean']:.2f}")
    print(f"    AddDist:  min={r['ad_range']['min']:.2f}, "
          f"max={r['ad_range']['max']:.2f}, mean={r['ad_range']['mean']:.2f}")

    print(f"\n  Distribution (per-session PnL):")
    print(f"    P10={p10:.1f}  P25={p25:.1f}  P50={p50:.1f}  "
          f"P75={p75:.1f}  P90={p90:.1f}")

    print(f"\n  Worst 5 sessions:")
    for sid, pnl in worst5.items():
        dt_str = session_date_map.get(sid, f"sid={sid}")
        print(f"    {dt_str}: {pnl:,.1f} ticks")

    print(f"\n  Best 5 sessions:")
    for sid, pnl in best5.items():
        dt_str = session_date_map.get(sid, f"sid={sid}")
        print(f"    {dt_str}: {pnl:,.1f} ticks")

    print(f"\n  EV components:")
    print(f"    Clean:    {r['ev_clean']['pct']:.2%}, "
          f"mean PnL={r['ev_clean']['mean_pnl']:.1f}")
    print(f"    1-Add:    {r['ev_1add']['pct']:.2%}, "
          f"recovery={r['ev_1add']['recover_pct']:.2%}, "
          f"mean PnL={r['ev_1add']['mean_pnl']:.1f}")
    print(f"    CapWalk:  {r['ev_capwalk']['pct']:.2%}, "
          f"mean PnL={r['ev_capwalk']['mean_pnl']:.1f}")
    print(f"    Deep:     {r['ev_deep']['pct']:.2%}, "
          f"mean PnL={r['ev_deep']['mean_pnl']:.1f}")

    print(f"\n  SpeedRead filter activity:")
    print(f"    Reversal SR skips: {sr_skips}")

    # ---- P1 vs P2a comparison ----
    p1_npf = p1_result['npf_1t']
    p1_pnl = p1_result['net_pnl']
    p1_cycles = p1_result['cycles']
    p1_daily = p1_result['mean_daily']
    p1_winpct = p1_result['session_win_pct']
    p1_clean = p1_result['clean_pct']
    p1_mae = p1_result['mean_mae']

    print(f"\n  {'=' * 60}")
    print(f"  P1 vs P2a COMPARISON")
    print(f"  {'=' * 60}")
    hdr = f"  {'Metric':<20} {'P1':>12} {'P2a':>12} {'Delta':>12}"
    print(hdr)
    print(f"  {'-' * 56}")
    print(f"  {'Net PF @1t':<20} {p1_npf:>12.4f} {r['npf_1t']:>12.4f} "
          f"{r['npf_1t'] - p1_npf:>+12.4f}")
    print(f"  {'Net PnL':<20} {p1_pnl:>12,.0f} {r['net_pnl']:>12,.0f} "
          f"{r['net_pnl'] - p1_pnl:>+12,.0f}")
    print(f"  {'Cycles':<20} {p1_cycles:>12,} {r['cycles']:>12,} "
          f"{r['cycles'] - p1_cycles:>+12,}")
    print(f"  {'Daily mean':<20} {p1_daily:>12.1f} {r['mean_daily']:>12.1f} "
          f"{r['mean_daily'] - p1_daily:>+12.1f}")
    print(f"  {'Session win %':<20} {p1_winpct:>12.2%} {r['session_win_pct']:>12.2%} "
          f"{r['session_win_pct'] - p1_winpct:>+12.2%}")
    print(f"  {'Clean %':<20} {p1_clean:>12.2%} {r['clean_pct']:>12.2%} "
          f"{r['clean_pct'] - p1_clean:>+12.2%}")
    print(f"  {'Mean MAE':<20} {p1_mae:>12.2f} {r['mean_mae']:>12.2f} "
          f"{r['mean_mae'] - p1_mae:>+12.2f}")

    # ---- Pass/Fail determination ----
    print(f"\n  {'=' * 60}")
    print(f"  PASS/FAIL DETERMINATION")
    print(f"  {'=' * 60}")

    pass_all = True
    flags = []
    fail_reasons = []

    # Hard pass criteria
    if r['npf_1t'] > 1.0:
        print(f"  [PASS] NPF @1t = {r['npf_1t']:.4f} > 1.0")
    else:
        print(f"  [FAIL] NPF @1t = {r['npf_1t']:.4f} < 1.0")
        fail_reasons.append(f"NPF {r['npf_1t']:.4f} < 1.0")
        pass_all = False

    if r['gpf'] > 1.05:
        print(f"  [PASS] Gross PF = {r['gpf']:.4f} > 1.05")
    else:
        print(f"  [FAIL] Gross PF = {r['gpf']:.4f} < 1.05")
        fail_reasons.append(f"Gross PF {r['gpf']:.4f} < 1.05")
        pass_all = False

    if r['session_win_pct'] > 0.50:
        print(f"  [PASS] Session win % = {r['session_win_pct']:.2%} > 50%")
    elif r['session_win_pct'] >= 0.45:
        print(f"  [FLAG] Session win % = {r['session_win_pct']:.2%} between 45-50%")
        flags.append(f"Session win% {r['session_win_pct']:.2%} between 45-50%")
    else:
        print(f"  [FAIL] Session win % = {r['session_win_pct']:.2%} < 45%")
        fail_reasons.append(f"Session win% {r['session_win_pct']:.2%} < 45%")
        pass_all = False

    if r['net_pnl'] > 0:
        print(f"  [PASS] Net PnL = {r['net_pnl']:,.0f} > 0")
    else:
        print(f"  [FAIL] Net PnL = {r['net_pnl']:,.0f} <= 0")
        fail_reasons.append(f"Net PnL {r['net_pnl']:,.0f} <= 0")
        pass_all = False

    # Conditional flags
    if 1.0 < r['npf_1t'] <= 1.05:
        flags.append(f"NPF {r['npf_1t']:.4f} between 1.0-1.05 — edge very thin")

    if r['clean_pct'] < 0.40:
        flags.append(f"Clean% {r['clean_pct']:.2%} < 40% — strategy struggling")

    npf_degrade = (p1_npf - r['npf_1t']) / p1_npf
    if npf_degrade > 0.30:
        flags.append(f"NPF degraded {npf_degrade:.1%} from P1 — heavy P1 overfitting")

    # Verdict
    if pass_all and not fail_reasons:
        verdict = "CONDITIONAL PASS" if flags else "PASS"
    else:
        verdict = "FAIL"

    print(f"\n  VERDICT: {verdict}")
    if flags:
        for f in flags:
            print(f"    FLAG: {f}")
    if fail_reasons:
        for f in fail_reasons:
            print(f"    REASON: {f}")

    print(f"\n  Total time: {time.time() - t0_total:.1f}s")

    # ---- Build result dict ----
    result = {
        "validation": "P2a",
        "verdict": verdict,
        "run_date": dt_mod.datetime.now().isoformat(),
        "frozen_config": {
            "version": "V1.4",
            "step_dist": "rolling_zigzag_P90 (floor 10)",
            "add_dist": "rolling_zigzag_P75 (floor 10)",
            "seed_dist": SEED_DIST,
            "session": "10:00-16:00 ET",
            "speedread": f"Roll50 >= {SR_THRESHOLD} (seed + reversal)",
            "max_levels": MAX_LEVELS,
            "position_cap": FLATTEN_CAP,
            "cap_action": "walk",
            "cost_ticks": COST_TICKS,
            "tick_size": TICK_SIZE,
        },
        "p2a_date_range": {
            "first_rth": str(P2A_RTH_FIRST),
            "last_rth": str(P2A_RTH_LAST),
            "sessions": r['sessions'],
        },
        "p2a_metrics": {
            "cycles": r['cycles'],
            "gpf": r['gpf'],
            "npf_1t": r['npf_1t'],
            "net_pnl": r['net_pnl'],
            "mean_daily": r['mean_daily'],
            "std_daily": r['std_daily'],
            "session_win_pct": r['session_win_pct'],
            "seed_accuracy": round(float(seed_accuracy), 4),
            "clean_pct": r['clean_pct'],
            "mean_mae": r['mean_mae'],
            "p75_mae": r['p75_mae'],
            "max_single_cycle_loss": r['max_single_cycle_loss'],
            "cycles_per_hour": r['cycles_per_hour'],
        },
        "p1_metrics": {
            "npf_1t": p1_npf,
            "net_pnl": p1_pnl,
            "cycles": p1_cycles,
            "mean_daily": p1_daily,
            "session_win_pct": p1_winpct,
            "clean_pct": p1_clean,
            "mean_mae": p1_mae,
        },
        "adaptive_ranges_p2a": {
            "stepdist": r['sd_range'],
            "adddist": r['ad_range'],
        },
        "distribution_per_session": {
            "p10": round(p10, 1), "p25": round(p25, 1), "p50": round(p50, 1),
            "p75": round(p75, 1), "p90": round(p90, 1),
        },
        "worst5_sessions": {session_date_map.get(k, f"sid={k}"): round(v, 1)
                            for k, v in worst5.items()},
        "best5_sessions": {session_date_map.get(k, f"sid={k}"): round(v, 1)
                           for k, v in best5.items()},
        "ev_components": {
            "clean": r['ev_clean'],
            "one_add": r['ev_1add'],
            "capwalk": r['ev_capwalk'],
            "deep": r['ev_deep'],
        },
        "sr_filter": {
            "reversal_sr_skips": sr_skips,
        },
        "pass_fail": {
            "verdict": verdict,
            "flags": flags,
            "fail_reasons": fail_reasons,
        },
        "contamination_update": (
            f"P2a validation: Frozen V1.4 config | {verdict} | "
            f"P2a dates {P2A_RTH_FIRST} to {P2A_RTH_LAST} now consumed. "
            f"P2b UNTOUCHED."
        ),
    }

    return result, sim, cf


def save_results(result, sim, cf):
    """Save all P2a validation artifacts."""
    print("\n  Saving results...")

    _OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # 1. Cycle parquet
    cycles_path = _OUTPUT_DIR / "p2a_validation_cycles.parquet"
    cf.to_parquet(str(cycles_path), index=False)
    print(f"    {cycles_path.name}")

    # 2. Per-session summary JSON
    session_pnl = cf.groupby('session_id')['net_1t'].sum()
    all_sids = range(1, sim['total_sessions'] + 1)
    session_pnl_full = session_pnl.reindex(all_sids, fill_value=0.0)

    # Map session dates
    trades_df = pd.DataFrame(sim['trade_records'])
    trades_df['dt'] = pd.to_datetime(trades_df['datetime'])
    trades_df['hour_val'] = trades_df['dt'].dt.hour
    rth_trades = trades_df[(trades_df['hour_val'] >= 9) & (trades_df['hour_val'] < 17)]
    session_date_map = (rth_trades.groupby('session_id')['dt']
                        .first()
                        .apply(lambda x: x.strftime('%Y-%m-%d'))
                        .to_dict())

    session_summary = []
    for sid in all_sids:
        s_cycles = cf[cf['session_id'] == sid]
        session_summary.append({
            "session_id": int(sid),
            "date": session_date_map.get(sid, None),
            "net_pnl": round(float(session_pnl_full.get(sid, 0)), 1),
            "cycles": len(s_cycles),
            "clean_cycles": int((s_cycles['adds_count'] == 0).sum())
            if len(s_cycles) > 0 else 0,
        })

    sessions_path = _OUTPUT_DIR / "p2a_validation_sessions.json"
    with open(sessions_path, 'w') as f:
        json.dump(session_summary, f, indent=2)
    print(f"    {sessions_path.name}")

    # 3. Full result JSON
    result_path = _OUTPUT_DIR / "p2a_validation_result.json"
    with open(result_path, 'w') as f:
        json.dump(result, f, indent=2, default=str)
    print(f"    {result_path.name}")

    print(f"\n  Contamination ledger:")
    print(f"    {result['contamination_update']}")


# ============================================================
# Main
# ============================================================

def main():
    parser = argparse.ArgumentParser(
        description="P2a Validation: One-shot frozen V1.4 config on P2a holdout")
    parser.add_argument('--verify-sr', action='store_true',
                        help='Step 0: SpeedRead verification only')
    parser.add_argument('--p1-sanity', action='store_true',
                        help='Step 1: P1 sanity check only')
    parser.add_argument('--p2a', action='store_true',
                        help='Step 2: P2a one-shot only')
    parser.add_argument('--all', action='store_true',
                        help='Run all steps sequentially')
    args = parser.parse_args()

    if not any([args.verify_sr, args.p1_sanity, args.p2a, args.all]):
        parser.print_help()
        return

    # Step 0: SpeedRead verification
    if args.all or args.verify_sr:
        sr_ok = verify_speedread()
        if not sr_ok:
            print("\nABORTING: SpeedRead verification failed. Fix before proceeding.")
            sys.exit(1)

    # Step 1: P1 sanity check
    p1_result = None
    if args.all or args.p1_sanity:
        p1_result = p1_sanity_check()
        if p1_result is None:
            print("\nABORTING: P1 sanity check failed. Simulator may have changed.")
            sys.exit(1)

    # Step 2: P2a one-shot
    if args.all or args.p2a:
        if p1_result is None:
            # Need P1 result for comparison table
            print("\n  Running P1 sanity check for comparison baseline...")
            p1_result = p1_sanity_check()
            if p1_result is None:
                print("\nABORTING: P1 sanity check failed.")
                sys.exit(1)

        result_tuple = run_p2a_validation(p1_result)
        if result_tuple is None:
            print("\nP2a validation produced no results.")
            sys.exit(1)

        result, sim, cf = result_tuple
        save_results(result, sim, cf)

        print(f"\n{'=' * 60}")
        print(f"P2a VALIDATION COMPLETE: {result['pass_fail']['verdict']}")
        print(f"P2b remains UNTOUCHED.")
        print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
