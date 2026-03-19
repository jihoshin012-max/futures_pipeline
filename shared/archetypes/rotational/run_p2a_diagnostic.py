# archetype: rotational
"""P2a Failure Diagnostic — Four-prong analysis.

Prong 1: Base config (SR OFF) on P2a — isolate SpeedRead contribution
Prong 2: Tail concentration — concentrated vs distributed loss
Prong 3: Rolling variance — P2a within P1 distribution?
Prong 4: Reversal chain economics — cap-walk degradation analysis

All prongs use V1.4 ADAPTIVE config:
  StepDist = rolling zigzag P90 (200-swing), AddDist = P75
  SeedDist = 15 fixed, 10:00-16:00, Roll50 SR>=48, ML=1, cap=2

Usage:
    python run_p2a_diagnostic.py
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
    COST_TICKS, TICK_SIZE, RTH_OPEN_TOD, FLATTEN_TOD,
    _P1_START, _P1_END, FLATTEN_CAP, MAX_LEVELS,
)
from run_phase1_sweep import (
    build_zigzag_lookup, make_adaptive_lookup, analyze_step2,
)
from run_p2a_validation import (
    build_combined_speedread, build_combined_zigzag_lookup,
    load_p2a_tick_data,
    SEED_DIST, STEP_DIST_INIT, ADD_DIST_INIT, SEED_START, SR_THRESHOLD,
    P2A_RTH_FIRST, P2A_RTH_LAST,
    EXCLUDE_HOURS,
)

_OUTPUT_DIR = Path(__file__).parent / "phase1_results"
_P1_MID = _P1_START + (_P1_END - _P1_START) / 2


# ============================================================
# Shared helpers
# ============================================================

def build_filtered_cycles(sim):
    """Build hour-filtered cycle DataFrame with net PnL from simulation output."""
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

    # Tag entry action (SEED vs REVERSAL)
    first_actions = trades.groupby('cycle_id')['action'].first()
    cf['entry_action'] = cf['cycle_id'].map(first_actions)

    return cf, trades


def compute_session_pnl(cf, total_sessions):
    """Compute per-session PnL from filtered cycles."""
    session_pnl = cf.groupby('session_id')['net_1t'].sum()
    all_sids = range(1, total_sessions + 1)
    return session_pnl.reindex(all_sids, fill_value=0.0)


def get_session_dates(trades):
    """Map session_id to calendar date from trade records."""
    trades = trades.copy()
    trades['dt'] = pd.to_datetime(trades['datetime'])
    rth = trades[(trades['dt'].dt.hour >= 9) & (trades['dt'].dt.hour < 17)]
    return rth.groupby('session_id')['dt'].first().apply(lambda x: x.date()).to_dict()


def compute_npf(cf):
    nw = cf.loc[cf['net_1t'] > 0, 'net_1t'].sum()
    nl = abs(cf.loc[cf['net_1t'] <= 0, 'net_1t'].sum())
    return nw / nl if nl > 0 else 0.0


def compute_gpf(cf):
    gw = cf.loc[cf['gross_pnl_ticks'] > 0, 'gross_pnl_ticks'].sum()
    gl = abs(cf.loc[cf['gross_pnl_ticks'] <= 0, 'gross_pnl_ticks'].sum())
    return gw / gl if gl > 0 else 0.0


# ============================================================
# PRONG 1: Base Config (SR OFF) on P2a
# ============================================================

def prong_1():
    print("\n" + "=" * 70)
    print("PRONG 1: Base Config (SR OFF) on P2a")
    print("  Adaptive P90/P75, SeedDist=15, 10:00-16:00, ML=1, cap=2")
    print("  SpeedRead filter DISABLED (thresholds = -999)")
    print("=" * 70)

    t0 = time.time()

    # Build P2a data (same warm-up as validation run)
    sr_bar_dts, sr_composite = build_combined_speedread()
    zz_lookup = build_combined_zigzag_lookup()
    adaptive = make_adaptive_lookup(zz_lookup, 5, 2)  # P90, P75
    prices, tod_secs, sr_roll50, dts = load_p2a_tick_data(sr_bar_dts, sr_composite)

    # --- SR-OFF run ---
    print("\n  Running P2a with SR OFF (thresholds=-999)...")
    sim_off = simulate_daily_flatten(
        prices, tod_secs, sr_roll50, dts,
        seed_dist=SEED_DIST, step_dist=STEP_DIST_INIT, add_dist=ADD_DIST_INIT,
        flatten_reseed_cap=FLATTEN_CAP, max_levels=MAX_LEVELS,
        seed_sr_thresh=-999.0, rev_sr_thresh=-999.0,
        watch_mode='rth_open', cap_action='walk',
        seed_start_tod=SEED_START,
        adaptive_lookup=adaptive,
    )

    r_off = analyze_step2(sim_off, "P2a_SR_OFF")
    cf_off, trades_off = build_filtered_cycles(sim_off)

    # Load saved SR-ON results for comparison
    cf_on = pd.read_parquet(str(_OUTPUT_DIR / "p2a_validation_cycles.parquet"))
    p2a_on = json.load(open(_OUTPUT_DIR / "p2a_validation_result.json"))
    m_on = p2a_on['p2a_metrics']

    gross_off = float(cf_off['gross_pnl_ticks'].sum())
    gross_on = float(cf_on['gross_pnl_ticks'].sum())
    capwalk_rate_off = (cf_off['cycle_cap_walks'] > 0).mean()
    capwalk_rate_on = (cf_on['cycle_cap_walks'] > 0).mean() if 'cycle_cap_walks' in cf_on.columns else 0

    print(f"\n  {'Metric':<28} {'SR OFF':>12} {'SR ON (V1.4)':>12} {'P1 (ref)':>12}")
    print(f"  {'-' * 64}")
    print(f"  {'Net PF @1t':<28} {r_off['npf_1t']:>12.4f} {m_on['npf_1t']:>12.4f} {'1.2000':>12}")
    print(f"  {'Gross PF':<28} {r_off['gpf']:>12.4f} {m_on['gpf']:>12.4f} {'1.2597':>12}")
    print(f"  {'Net ticks':<28} {r_off['net_pnl']:>12,.0f} {m_on['net_pnl']:>12,.0f} {'+20,919':>12}")
    print(f"  {'Gross ticks':<28} {gross_off:>12,.0f} {gross_on:>12,.0f} {'—':>12}")
    print(f"  {'Cycles':<28} {r_off['cycles']:>12,} {m_on['cycles']:>12,} {'1,847':>12}")
    print(f"  {'Mean gross/cycle':<28} {gross_off / r_off['cycles']:>12.2f}"
          f" {gross_on / m_on['cycles']:>12.2f} {'—':>12}")
    print(f"  {'Cap-walk rate':<28} {capwalk_rate_off:>12.1%} {capwalk_rate_on:>12.1%} {'—':>12}")
    print(f"  {'Session win %':<28} {r_off['session_win_pct']:>12.1%}"
          f" {m_on['session_win_pct']:>12.1%} {'69.5%':>12}")

    # Adaptive ranges
    print(f"\n  Adaptive ranges (SR OFF P2a):")
    print(f"    StepDist: min={r_off['sd_range']['min']:.1f},"
          f" max={r_off['sd_range']['max']:.1f}, mean={r_off['sd_range']['mean']:.1f}")
    print(f"    AddDist:  min={r_off['ad_range']['min']:.1f},"
          f" max={r_off['ad_range']['max']:.1f}, mean={r_off['ad_range']['mean']:.1f}")

    # SR distribution at cycle entries (SR-OFF run, post-hoc analysis)
    entry_trades_off = trades_off[trades_off['action'].isin(['SEED', 'REVERSAL'])].copy()
    entry_trades_off['sr_at_entry'] = sr_roll50[entry_trades_off['bar_idx'].values]
    sr_at_entry = entry_trades_off.groupby('cycle_id')['sr_at_entry'].first()
    cf_off['sr_at_entry'] = cf_off['cycle_id'].map(sr_at_entry)

    sr_valid = cf_off['sr_at_entry'].dropna()
    print(f"\n  Roll50 SR at cycle entry (P2a, all cycles, n={len(sr_valid)}):")
    print(f"    Mean:   {sr_valid.mean():.1f}")
    print(f"    Median: {sr_valid.median():.1f}")
    print(f"    P25:    {sr_valid.quantile(0.25):.1f}")
    print(f"    P75:    {sr_valid.quantile(0.75):.1f}")
    print(f"    % below 48: {(sr_valid < 48).mean():.1%}")

    # Would-pass vs would-fail classification
    would_pass = cf_off[cf_off['sr_at_entry'] >= SR_THRESHOLD]
    would_fail = cf_off[cf_off['sr_at_entry'] < SR_THRESHOLD]

    n_pass = len(would_pass)
    n_fail = len(would_fail)
    print(f"\n  Post-hoc SR classification (threshold=48):")
    print(f"    Would pass (SR>=48): {n_pass} cycles,"
          f" mean net = {would_pass['net_1t'].mean():+.1f} ticks")
    print(f"    Would fail (SR<48):  {n_fail} cycles,"
          f" mean net = {would_fail['net_1t'].mean():+.1f} ticks")

    print(f"\n  Time: {time.time() - t0:.1f}s")

    result = {
        "sr_off": {
            "npf": r_off['npf_1t'], "gpf": r_off['gpf'],
            "net_ticks": r_off['net_pnl'],
            "gross_ticks": round(gross_off, 1),
            "cycles": r_off['cycles'], "sessions": r_off['sessions'],
            "mean_gross_per_cycle": round(gross_off / r_off['cycles'], 2),
            "capwalk_rate": round(float(capwalk_rate_off), 4),
            "session_win_pct": r_off['session_win_pct'],
            "sd_range": r_off['sd_range'], "ad_range": r_off['ad_range'],
            "ev_clean": r_off['ev_clean'], "ev_capwalk": r_off['ev_capwalk'],
        },
        "sr_on": {
            "npf": m_on['npf_1t'], "gpf": m_on['gpf'],
            "net_ticks": m_on['net_pnl'],
            "gross_ticks": round(gross_on, 1),
            "cycles": m_on['cycles'],
            "mean_gross_per_cycle": round(float(gross_on / m_on['cycles']), 2),
            "capwalk_rate": round(float(capwalk_rate_on), 4),
        },
        "sr_distribution_p2a": {
            "mean": round(float(sr_valid.mean()), 1),
            "median": round(float(sr_valid.median()), 1),
            "p25": round(float(sr_valid.quantile(0.25)), 1),
            "p75": round(float(sr_valid.quantile(0.75)), 1),
            "pct_below_48": round(float((sr_valid < 48).mean()), 3),
        },
        "sr_classification": {
            "would_pass_n": n_pass,
            "would_pass_mean_net": round(float(would_pass['net_1t'].mean()), 1),
            "would_fail_n": n_fail,
            "would_fail_mean_net": round(float(would_fail['net_1t'].mean()), 1),
        },
        "p1_ref": {"npf": 1.2000, "gpf": 1.2597, "cycles": 1847},
    }
    return result


# ============================================================
# PRONG 2: Tail Concentration
# ============================================================

def prong_2():
    print("\n" + "=" * 70)
    print("PRONG 2: Tail Concentration Check")
    print("=" * 70)

    sessions = json.load(open(_OUTPUT_DIR / "p2a_validation_sessions.json"))
    cf = pd.read_parquet(str(_OUTPUT_DIR / "p2a_validation_cycles.parquet"))

    # Ensure net_1t exists
    if 'net_1t' not in cf.columns:
        cf['net_1t'] = cf['gross_pnl_ticks'] - cf['cost']

    sess_df = pd.DataFrame(sessions)
    sess_df = sess_df[sess_df['date'].notna()].copy()
    total_sessions = len(sess_df)

    # --- Remove worst N sessions ---
    print(f"\n  Removing WORST sessions:")
    print(f"  {'Removed':>8} {'NPF':>8} {'Net Ticks':>12} {'Cycles':>8} {'Sess Left':>10}")
    print(f"  {'-' * 54}")

    sorted_worst = sess_df.sort_values('net_pnl')['session_id'].values
    worst_table = []

    for n in range(6):
        if n == 0:
            rem = cf.copy()
        else:
            rem = cf[~cf['session_id'].isin(sorted_worst[:n])].copy()
        if len(rem) == 0:
            break
        npf = compute_npf(rem)
        net = float(rem['net_1t'].sum())
        nc = len(rem)
        left = total_sessions - n
        row = {"removed": n, "npf": round(npf, 4), "net_ticks": round(net, 0),
               "cycles": nc, "sessions_left": left}
        worst_table.append(row)
        label = "baseline" if n == 0 else str(n)
        print(f"  {label:>8} {npf:>8.4f} {net:>12,.0f} {nc:>8,} {left:>10}")

    # --- Remove best N sessions (symmetry) ---
    print(f"\n  Removing BEST sessions (symmetry):")
    print(f"  {'Removed':>8} {'NPF':>8} {'Net Ticks':>12} {'Cycles':>8}")
    print(f"  {'-' * 44}")

    sorted_best = sess_df.sort_values('net_pnl', ascending=False)['session_id'].values
    best_table = []

    for n in range(4):
        if n == 0:
            rem = cf.copy()
        else:
            rem = cf[~cf['session_id'].isin(sorted_best[:n])].copy()
        if len(rem) == 0:
            break
        npf = compute_npf(rem)
        net = float(rem['net_1t'].sum())
        nc = len(rem)
        row = {"removed": n, "npf": round(npf, 4), "net_ticks": round(net, 0),
               "cycles": nc}
        best_table.append(row)
        label = "baseline" if n == 0 else str(n)
        print(f"  {label:>8} {npf:>8.4f} {net:>12,.0f} {nc:>8,}")

    # --- Worst session detail ---
    worst_sid = sorted_worst[0]
    worst_row = sess_df[sess_df['session_id'] == worst_sid].iloc[0]
    worst_cycles = cf[cf['session_id'] == worst_sid]
    cw_count = worst_cycles['cycle_cap_walks'].sum() if 'cycle_cap_walks' in worst_cycles.columns else 0

    print(f"\n  Worst session: {worst_row['date']} (sid={worst_sid})")
    print(f"    Net PnL: {worst_row['net_pnl']:+,.0f} ticks")
    print(f"    Cycles: {worst_row['cycles']}, clean: {worst_row['clean_cycles']}")
    print(f"    Total cap-walks: {cw_count}")
    if 'stepdist_used' in worst_cycles.columns:
        print(f"    Mean StepDist: {worst_cycles['stepdist_used'].mean():.1f} pts")

    # --- Worst 3 detail ---
    print(f"\n  Worst 3 sessions:")
    worst3_details = []
    for sid in sorted_worst[:3]:
        row = sess_df[sess_df['session_id'] == sid].iloc[0]
        sc = cf[cf['session_id'] == sid]
        cw = sc['cycle_cap_walks'].sum() if 'cycle_cap_walks' in sc.columns else 0
        sd_mean = sc['stepdist_used'].mean() if 'stepdist_used' in sc.columns else 0
        ad_mean = sc['adddist_used'].mean() if 'adddist_used' in sc.columns else 0
        detail = {
            "date": row['date'], "net_pnl": float(row['net_pnl']),
            "cycles": int(row['cycles']), "clean": int(row['clean_cycles']),
            "cap_walks": int(cw),
            "mean_stepdist": round(float(sd_mean), 1),
            "mean_adddist": round(float(ad_mean), 1),
        }
        worst3_details.append(detail)
        print(f"    {row['date']}: {row['net_pnl']:+,.0f} ticks, "
              f"{row['cycles']} cyc, {row['clean_cycles']} clean, "
              f"CW={cw}, SD={sd_mean:.1f}, AD={ad_mean:.1f}")

    result = {
        "remove_worst": worst_table,
        "remove_best": best_table,
        "worst_session": {
            "date": worst_row['date'], "net_pnl": float(worst_row['net_pnl']),
            "cycles": int(worst_row['cycles']), "cap_walks": int(cw_count),
        },
        "worst3_details": worst3_details,
        "total_sessions": total_sessions,
    }
    return result


# ============================================================
# PRONG 3: Rolling 28-Session Variance (P1 → P2a)
# ============================================================

def prong_3():
    print("\n" + "=" * 70)
    print("PRONG 3: Rolling 28-Session Variance (full P1)")
    print("=" * 70)

    t0 = time.time()

    # Run V1.4 on full P1 (59 sessions)
    print("  Loading full P1 data...")
    prices, tod_secs, sr_vals, dts = load_data(period='full_p1', use_speedread=True)
    zz_lookup = build_zigzag_lookup()
    adaptive = make_adaptive_lookup(zz_lookup, 5, 2)

    cs = np.cumsum(np.insert(sr_vals, 0, 0))
    w = 50
    sr_roll50 = np.empty_like(sr_vals)
    sr_roll50[:w] = cs[1:w + 1] / np.arange(1, w + 1)
    sr_roll50[w:] = (cs[w + 1:] - cs[1:len(sr_vals) - w + 1]) / w

    print("  Running V1.4 on full P1...")
    sim_p1 = simulate_daily_flatten(
        prices, tod_secs, sr_roll50, dts,
        seed_dist=SEED_DIST, step_dist=STEP_DIST_INIT, add_dist=ADD_DIST_INIT,
        flatten_reseed_cap=FLATTEN_CAP, max_levels=MAX_LEVELS,
        seed_sr_thresh=SR_THRESHOLD, rev_sr_thresh=SR_THRESHOLD,
        watch_mode='rth_open', cap_action='walk',
        seed_start_tod=SEED_START,
        adaptive_lookup=adaptive,
    )

    cf_p1, trades_p1 = build_filtered_cycles(sim_p1)
    sdates_p1 = get_session_dates(trades_p1)
    n_total = sim_p1['total_sessions']
    spnl_p1 = compute_session_pnl(cf_p1, n_total)

    # Only keep sessions that have dates (exclude trailing partial)
    valid_sids = sorted([s for s in spnl_p1.index if s in sdates_p1])
    n_sessions = len(valid_sids)
    print(f"  P1 sessions with RTH trades: {n_sessions}")

    session_net = np.array([float(spnl_p1[s]) for s in valid_sids])

    # Rolling 28-session NPF and gross PF
    WINDOW = 28
    n_windows = n_sessions - WINDOW + 1
    if n_windows <= 0:
        print("  ERROR: Not enough sessions for 28-session window")
        return None

    rolling_npf = []
    rolling_gpf = []
    rolling_capwalk_rate = []
    rolling_labels = []

    for i in range(n_windows):
        w_sids = valid_sids[i:i + WINDOW]
        w_cf = cf_p1[cf_p1['session_id'].isin(w_sids)]
        if len(w_cf) == 0:
            continue
        npf = compute_npf(w_cf)
        gpf = compute_gpf(w_cf)
        cw_rate = (w_cf['cycle_cap_walks'] > 0).mean() if 'cycle_cap_walks' in w_cf.columns else 0

        rolling_npf.append(npf)
        rolling_gpf.append(gpf)
        rolling_capwalk_rate.append(cw_rate)
        d0 = str(sdates_p1[w_sids[0]])
        d1 = str(sdates_p1[w_sids[-1]])
        rolling_labels.append(f"{d0} to {d1}")

    rolling_npf = np.array(rolling_npf)
    rolling_gpf = np.array(rolling_gpf)
    rolling_cwr = np.array(rolling_capwalk_rate)

    P2A_NPF = 0.9577
    P2A_GPF = 1.0058

    print(f"\n  Rolling {WINDOW}-session NPF (P1, n={len(rolling_npf)} windows):")
    print(f"    Mean:   {rolling_npf.mean():.4f}")
    print(f"    Median: {np.median(rolling_npf):.4f}")
    print(f"    Std:    {rolling_npf.std():.4f}")
    print(f"    Min:    {rolling_npf.min():.4f}")
    print(f"    Max:    {rolling_npf.max():.4f}")
    print(f"    P5:     {np.percentile(rolling_npf, 5):.4f}")
    print(f"    P25:    {np.percentile(rolling_npf, 25):.4f}")
    print(f"    P75:    {np.percentile(rolling_npf, 75):.4f}")
    print(f"    P95:    {np.percentile(rolling_npf, 95):.4f}")

    pct_rank = (rolling_npf < P2A_NPF).mean() * 100
    print(f"\n  P2a NPF ({P2A_NPF}) at P{pct_rank:.0f} of P1 distribution")

    n_below_1 = int((rolling_npf < 1.0).sum())
    print(f"  P1 windows with NPF < 1.0: {n_below_1} / {len(rolling_npf)}")
    if n_below_1 > 0:
        below_vals = rolling_npf[rolling_npf < 1.0]
        print(f"    Min NPF among those: {below_vals.min():.4f}")
        for j in range(len(rolling_npf)):
            if rolling_npf[j] < 1.0:
                print(f"    Window {j}: {rolling_labels[j]}, NPF={rolling_npf[j]:.4f}")

    print(f"\n  Rolling {WINDOW}-session Gross PF:")
    print(f"    Mean: {rolling_gpf.mean():.4f}, Min: {rolling_gpf.min():.4f},"
          f" Max: {rolling_gpf.max():.4f}")
    gpf_pct = (rolling_gpf < P2A_GPF).mean() * 100
    print(f"    P2a Gross PF ({P2A_GPF}) at P{gpf_pct:.0f}")
    n_gpf_low = int((rolling_gpf < 1.05).sum())
    print(f"    P1 windows with Gross PF < 1.05: {n_gpf_low}")

    print(f"\n  Rolling {WINDOW}-session cap-walk rate:")
    print(f"    Mean: {rolling_cwr.mean():.1%}, Min: {rolling_cwr.min():.1%},"
          f" Max: {rolling_cwr.max():.1%}")

    # Full series table
    print(f"\n  Rolling NPF series:")
    print(f"  {'Window':<6} {'Dates':<28} {'NPF':>8} {'GPF':>8} {'CW%':>6}")
    print(f"  {'-' * 58}")
    for i in range(len(rolling_npf)):
        marker = " <--- P2a" if i == len(rolling_npf) - 1 else ""
        print(f"  {i:<6} {rolling_labels[i]:<28} {rolling_npf[i]:>8.4f}"
              f" {rolling_gpf[i]:>8.4f} {rolling_cwr[i]:>6.1%}{marker}")

    print(f"\n  Time: {time.time() - t0:.1f}s")

    result = {
        "n_windows": len(rolling_npf),
        "p1_rolling_npf": {
            "mean": round(float(rolling_npf.mean()), 4),
            "median": round(float(np.median(rolling_npf)), 4),
            "std": round(float(rolling_npf.std()), 4),
            "min": round(float(rolling_npf.min()), 4),
            "max": round(float(rolling_npf.max()), 4),
            "p5": round(float(np.percentile(rolling_npf, 5)), 4),
            "p25": round(float(np.percentile(rolling_npf, 25)), 4),
            "p75": round(float(np.percentile(rolling_npf, 75)), 4),
            "p95": round(float(np.percentile(rolling_npf, 95)), 4),
        },
        "p1_rolling_gpf": {
            "mean": round(float(rolling_gpf.mean()), 4),
            "min": round(float(rolling_gpf.min()), 4),
            "max": round(float(rolling_gpf.max()), 4),
        },
        "p1_rolling_capwalk": {
            "mean": round(float(rolling_cwr.mean()), 4),
            "min": round(float(rolling_cwr.min()), 4),
            "max": round(float(rolling_cwr.max()), 4),
        },
        "p2a_npf": P2A_NPF,
        "p2a_gpf": P2A_GPF,
        "p2a_npf_percentile": round(pct_rank, 1),
        "p2a_gpf_percentile": round(gpf_pct, 1),
        "p1_windows_npf_below_1": n_below_1,
        "p1_windows_gpf_below_105": n_gpf_low,
        "rolling_series": [
            {"window": i, "dates": rolling_labels[i],
             "npf": round(float(rolling_npf[i]), 4),
             "gpf": round(float(rolling_gpf[i]), 4),
             "capwalk_rate": round(float(rolling_cwr[i]), 4)}
            for i in range(len(rolling_npf))
        ],
    }
    return result


# ============================================================
# PRONG 4: Reversal Chain Economics
# ============================================================

def prong_4():
    print("\n" + "=" * 70)
    print("PRONG 4: Reversal Chain Economics (P2a vs P1)")
    print("=" * 70)

    # --- P2a cycle data ---
    cf_p2a = pd.read_parquet(str(_OUTPUT_DIR / "p2a_validation_cycles.parquet"))
    if 'net_1t' not in cf_p2a.columns:
        cf_p2a['net_1t'] = cf_p2a['gross_pnl_ticks'] - cf_p2a['cost']

    # Tag entry action: first cycle in each session = SEED, rest = REVERSAL
    # (In V1.4 with SR, reversal_sr_skip creates additional seeds)
    cf_p2a = cf_p2a.sort_values('cycle_id').reset_index(drop=True)
    cf_p2a['prev_session'] = cf_p2a['session_id'].shift(1).fillna(-1).astype(int)
    cf_p2a['prev_exit'] = cf_p2a['exit_reason'].shift(1).fillna('')
    cf_p2a['is_seed'] = (
        (cf_p2a['prev_session'] != cf_p2a['session_id']) |
        (~cf_p2a['prev_exit'].isin(['reversal'])) |
        (cf_p2a.index == 0)
    )

    rev_p2a = cf_p2a[~cf_p2a['is_seed']]
    seed_p2a = cf_p2a[cf_p2a['is_seed']]

    # --- P1 cycle data (re-run to get cycle-level detail) ---
    # Reuse Prong 3 P1 run - but we need cycle data, so re-run
    print("  Loading P1 for reversal chain comparison...")
    prices, tod_secs, sr_vals, dts = load_data(period='full_p1', use_speedread=True)
    zz_lookup = build_zigzag_lookup()
    adaptive = make_adaptive_lookup(zz_lookup, 5, 2)
    cs = np.cumsum(np.insert(sr_vals, 0, 0))
    w = 50
    sr_roll50 = np.empty_like(sr_vals)
    sr_roll50[:w] = cs[1:w + 1] / np.arange(1, w + 1)
    sr_roll50[w:] = (cs[w + 1:] - cs[1:len(sr_vals) - w + 1]) / w

    print("  Running V1.4 on full P1...")
    sim_p1 = simulate_daily_flatten(
        prices, tod_secs, sr_roll50, dts,
        seed_dist=SEED_DIST, step_dist=STEP_DIST_INIT, add_dist=ADD_DIST_INIT,
        flatten_reseed_cap=FLATTEN_CAP, max_levels=MAX_LEVELS,
        seed_sr_thresh=SR_THRESHOLD, rev_sr_thresh=SR_THRESHOLD,
        watch_mode='rth_open', cap_action='walk',
        seed_start_tod=SEED_START,
        adaptive_lookup=adaptive,
    )

    cf_p1, _ = build_filtered_cycles(sim_p1)

    # Tag P1 cycles
    cf_p1 = cf_p1.sort_values('cycle_id').reset_index(drop=True)
    cf_p1['prev_session'] = cf_p1['session_id'].shift(1).fillna(-1).astype(int)
    cf_p1['prev_exit'] = cf_p1['exit_reason'].shift(1).fillna('')
    cf_p1['is_seed'] = (
        (cf_p1['prev_session'] != cf_p1['session_id']) |
        (~cf_p1['prev_exit'].isin(['reversal'])) |
        (cf_p1.index == 0)
    )

    rev_p1 = cf_p1[~cf_p1['is_seed']]
    seed_p1 = cf_p1[cf_p1['is_seed']]

    # --- Comparison ---
    def chain_stats(df, label):
        n = len(df)
        if n == 0:
            return {}
        gpf = compute_gpf(df)
        npf = compute_npf(df)
        mean_net = float(df['net_1t'].mean())
        mean_gross = float(df['gross_pnl_ticks'].mean())
        has_cw = 'cycle_cap_walks' in df.columns
        cw_rate = float((df['cycle_cap_walks'] > 0).mean()) if has_cw else 0
        clean_pct = float((df['adds_count'] == 0).mean())
        # Cap-walk cycle stats
        if has_cw:
            cw_cycles = df[df['cycle_cap_walks'] > 0]
            cw_mean_loss = float(cw_cycles['net_1t'].mean()) if len(cw_cycles) > 0 else 0
            cw_mean_walks = float(cw_cycles['cycle_cap_walks'].mean()) if len(cw_cycles) > 0 else 0
            cw_mean_mae = float(cw_cycles['mae'].mean()) if len(cw_cycles) > 0 else 0
        else:
            cw_mean_loss = cw_mean_walks = cw_mean_mae = 0
        return {
            "count": n, "gpf": round(gpf, 4), "npf": round(npf, 4),
            "mean_net": round(mean_net, 1), "mean_gross": round(mean_gross, 1),
            "capwalk_rate": round(cw_rate, 4), "clean_pct": round(clean_pct, 4),
            "cw_mean_loss": round(cw_mean_loss, 1),
            "cw_mean_walks": round(cw_mean_walks, 2),
            "cw_mean_mae": round(cw_mean_mae, 2),
        }

    r_rev_p2a = chain_stats(rev_p2a, "P2a reversal")
    r_rev_p1 = chain_stats(rev_p1, "P1 reversal")
    r_seed_p2a = chain_stats(seed_p2a, "P2a seed")
    r_seed_p1 = chain_stats(seed_p1, "P1 seed")

    print(f"\n  REVERSAL CHAIN:")
    print(f"  {'Metric':<28} {'P1':>12} {'P2a':>12} {'Delta':>12}")
    print(f"  {'-' * 64}")
    for key, label in [('count', 'Cycles'), ('gpf', 'Gross PF'), ('npf', 'Net PF'),
                       ('mean_net', 'Mean net/cycle'), ('mean_gross', 'Mean gross/cycle'),
                       ('capwalk_rate', 'Cap-walk rate'), ('clean_pct', 'Clean %'),
                       ('cw_mean_loss', 'CW cycle mean loss'),
                       ('cw_mean_walks', 'CW mean walks/cycle'),
                       ('cw_mean_mae', 'CW mean MAE')]:
        v1, v2 = r_rev_p1.get(key, 0), r_rev_p2a.get(key, 0)
        delta = v2 - v1
        if isinstance(v1, float):
            print(f"  {label:<28} {v1:>12.2f} {v2:>12.2f} {delta:>+12.2f}")
        else:
            print(f"  {label:<28} {v1:>12,} {v2:>12,} {delta:>+12,}")

    print(f"\n  SEED CYCLES (for reference):")
    print(f"    P1: {r_seed_p1.get('count', 0)} cycles, mean net={r_seed_p1.get('mean_net', 0):+.1f}")
    print(f"    P2a: {r_seed_p2a.get('count', 0)} cycles, mean net={r_seed_p2a.get('mean_net', 0):+.1f}")

    # --- Cap-walk excursion vs P90 at entry ---
    has_sd = 'stepdist_used' in cf_p2a.columns
    if has_sd:
        cw_p2a = rev_p2a[rev_p2a['cycle_cap_walks'] > 0] if 'cycle_cap_walks' in rev_p2a.columns else pd.DataFrame()
        cw_p1 = rev_p1[rev_p1['cycle_cap_walks'] > 0] if 'cycle_cap_walks' in rev_p1.columns else pd.DataFrame()

        if len(cw_p2a) > 0:
            p2a_excess = cw_p2a['mae'].values - cw_p2a['stepdist_used'].values
            print(f"\n  Cap-walk MAE vs StepDist (P90) at entry — REVERSAL chain:")
            print(f"    P2a: mean excess = {p2a_excess.mean():+.2f} pts"
                  f" (MAE exceeds P90 by this much)")
            print(f"    P2a: % where MAE > 2x StepDist: {(cw_p2a['mae'] > 2 * cw_p2a['stepdist_used']).mean():.0%}")

        if len(cw_p1) > 0:
            p1_excess = cw_p1['mae'].values - cw_p1['stepdist_used'].values
            print(f"    P1:  mean excess = {p1_excess.mean():+.2f} pts")
            print(f"    P1:  % where MAE > 2x StepDist: {(cw_p1['mae'] > 2 * cw_p1['stepdist_used']).mean():.0%}")

        # Did cap-walks get WORSE (larger loss) or MORE FREQUENT (same loss)?
        if len(cw_p2a) > 0 and len(cw_p1) > 0:
            worse = r_rev_p2a['cw_mean_loss'] < r_rev_p1['cw_mean_loss']
            more_freq = r_rev_p2a['capwalk_rate'] > r_rev_p1['capwalk_rate']
            print(f"\n  Cap-walk diagnosis:")
            print(f"    Larger losses per CW cycle: {'YES' if worse else 'NO'}"
                  f" (P2a={r_rev_p2a['cw_mean_loss']:+.1f} vs P1={r_rev_p1['cw_mean_loss']:+.1f})")
            print(f"    More frequent CW cycles:    {'YES' if more_freq else 'NO'}"
                  f" (P2a={r_rev_p2a['capwalk_rate']:.1%} vs P1={r_rev_p1['capwalk_rate']:.1%})")

    result = {
        "reversal_p1": r_rev_p1,
        "reversal_p2a": r_rev_p2a,
        "seed_p1": r_seed_p1,
        "seed_p2a": r_seed_p2a,
    }
    return result


# ============================================================
# Decision Tree
# ============================================================

def evaluate_decision(p1r, p2r, p3r, p4r):
    print("\n" + "=" * 70)
    print("DECISION TREE EVALUATION")
    print("=" * 70)

    # Prong 1
    base_neg = p1r['sr_off']['net_ticks'] <= 0
    base_gpf = p1r['sr_off']['gpf']
    sr_on_better = p1r['sr_on']['net_ticks'] > p1r['sr_off']['net_ticks']

    # Prong 2
    remove2_npf = p2r['remove_worst'][2]['npf'] if len(p2r['remove_worst']) > 2 else 0
    concentrated = remove2_npf > 1.0

    # Prong 3
    p1_min_npf = p3r['p1_rolling_npf']['min']
    inside_range = p3r['p2a_npf'] >= p1_min_npf
    p1_had_below_1 = p3r['p1_windows_npf_below_1'] > 0

    # Prong 4
    cw_worse = p4r['reversal_p2a'].get('cw_mean_loss', 0) < p4r['reversal_p1'].get('cw_mean_loss', 0)
    cw_more_freq = p4r['reversal_p2a'].get('capwalk_rate', 0) > p4r['reversal_p1'].get('capwalk_rate', 0)

    print(f"\n  Prong 1: Base (SR OFF) net ticks = {p1r['sr_off']['net_ticks']:+,.0f}")
    print(f"    Base also negative: {'YES' if base_neg else 'NO'}")
    print(f"    Base gross PF: {base_gpf:.4f}")
    print(f"  Prong 2: NPF after removing worst 2 = {remove2_npf:.4f}")
    print(f"    Concentrated in 2-3 sessions: {'YES' if concentrated else 'NO'}")
    print(f"  Prong 3: P2a NPF at P{p3r['p2a_npf_percentile']:.0f}, P1 min NPF = {p1_min_npf:.4f}")
    print(f"    Inside P1 range: {'YES' if inside_range else 'NO'}")
    print(f"    P1 had windows with NPF < 1.0: {'YES' if p1_had_below_1 else 'NO'}")
    print(f"  Prong 4: CW losses worse: {'YES' if cw_worse else 'NO'},"
          f" CW more frequent: {'YES' if cw_more_freq else 'NO'}")

    # Match decision tree
    if base_neg and not concentrated and not inside_range:
        if cw_worse and cw_more_freq:
            diag = "Structural breakdown — rotation economics don't transfer."
            nxt = "Investigate regime difference. Edge may be P1-specific."
        else:
            diag = "Gross edge degraded beyond P1 range."
            nxt = "Regime-dependent edge magnitude. Consider regime detection."
    elif base_neg and not concentrated and inside_range:
        diag = ("High variance — P2a is a cold streak within P1's own range. "
                "Edge is real but noisy.")
        nxt = "Accept variance. Validate P2b for combined sample."
    elif base_neg and concentrated and inside_range:
        diag = "Bad draw driven by tail events, not systematic breakdown."
        nxt = "Implement stops (4A/4C) to cap tails. Validate P2b."
    elif base_neg and concentrated and not inside_range:
        diag = "Regime shift + tail concentration."
        nxt = "Strategy may need regime detection. Park and wait for P3."
    elif not base_neg:
        if not sr_on_better:
            diag = "SR filtering OUT profitable cycles in P2a regime."
            nxt = ("Roll50 composite misclassifying P2a conditions. "
                   "Investigate mechanism, don't recalibrate with P2a data.")
        else:
            diag = "Base positive, SR helps — mixed signals."
            nxt = "Further investigation needed."
    else:
        diag = "Unclassified."
        nxt = "Manual review."

    if cw_worse and not cw_more_freq:
        diag += " Market trended harder (larger CW losses, same frequency)."
        nxt += " Stops (4A: max adverse sigma) are the direct answer."
    elif not cw_worse and cw_more_freq:
        diag += " More CW episodes but similar loss magnitude."

    print(f"\n  {'=' * 60}")
    print(f"  DIAGNOSIS: {diag}")
    print(f"  NEXT STEP: {nxt}")
    print(f"  {'=' * 60}")

    return {"diagnosis": diag, "next_step": nxt,
            "base_negative": base_neg, "concentrated": concentrated,
            "inside_range": inside_range, "cw_worse": cw_worse,
            "cw_more_frequent": cw_more_freq}


# ============================================================
# Save
# ============================================================

def save_all(p1r, p2r, p3r, p4r, dec):
    _OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    for name, data in [("prong1_base", p1r), ("prong2_tails", p2r),
                        ("prong3_rolling", p3r), ("prong4_revchain", p4r)]:
        path = _OUTPUT_DIR / f"p2a_diagnostic_{name}.json"
        with open(path, 'w') as f:
            json.dump(data, f, indent=2, default=str)

    # Summary markdown
    md = f"""# P2a Diagnostic Summary — V1.4 Adaptive Config

## Prong 1: Base Config (SR OFF) on P2a
- SR OFF: NPF={p1r['sr_off']['npf']:.4f}, GPF={p1r['sr_off']['gpf']:.4f}, net={p1r['sr_off']['net_ticks']:+,.0f} ticks, {p1r['sr_off']['cycles']} cycles
- SR ON:  NPF={p1r['sr_on']['npf']:.4f}, GPF={p1r['sr_on']['gpf']:.4f}, net={p1r['sr_on']['net_ticks']:+,.0f} ticks, {p1r['sr_on']['cycles']} cycles
- P1 ref: NPF=1.200, GPF=1.260, 1,847 cycles
- SR-skipped cycles (would fail SR<48): n={p1r['sr_classification']['would_fail_n']}, mean net={p1r['sr_classification']['would_fail_mean_net']:+.1f}

## Prong 2: Tail Concentration
| Worst Removed | NPF | Net Ticks | Cycles | Sessions Left |
|---------------|-----|-----------|--------|---------------|
"""
    for row in p2r['remove_worst']:
        md += f"| {row['removed']} | {row['npf']:.4f} | {row['net_ticks']:+,.0f} | {row['cycles']} | {row['sessions_left']} |\n"

    md += f"""
| Best Removed | NPF | Net Ticks | Cycles |
|--------------|-----|-----------|--------|
"""
    for row in p2r['remove_best']:
        md += f"| {row['removed']} | {row['npf']:.4f} | {row['net_ticks']:+,.0f} | {row['cycles']} |\n"

    md += f"""
## Prong 3: Rolling 28-Session Variance
- P1 rolling NPF: mean={p3r['p1_rolling_npf']['mean']:.4f}, min={p3r['p1_rolling_npf']['min']:.4f}, max={p3r['p1_rolling_npf']['max']:.4f}, std={p3r['p1_rolling_npf']['std']:.4f}
- P2a NPF ({p3r['p2a_npf']}) at P{p3r['p2a_npf_percentile']:.0f} of P1 distribution
- P1 windows with NPF < 1.0: {p3r['p1_windows_npf_below_1']}
- P1 rolling Gross PF: mean={p3r['p1_rolling_gpf']['mean']:.4f}, min={p3r['p1_rolling_gpf']['min']:.4f}
- P1 rolling cap-walk rate: mean={p3r['p1_rolling_capwalk']['mean']:.1%}, min={p3r['p1_rolling_capwalk']['min']:.1%}, max={p3r['p1_rolling_capwalk']['max']:.1%}

## Prong 4: Reversal Chain Economics
| Metric | P1 Rev | P2a Rev |
|--------|--------|---------|
| Cycles | {p4r['reversal_p1']['count']} | {p4r['reversal_p2a']['count']} |
| Gross PF | {p4r['reversal_p1']['gpf']:.4f} | {p4r['reversal_p2a']['gpf']:.4f} |
| Net PF | {p4r['reversal_p1']['npf']:.4f} | {p4r['reversal_p2a']['npf']:.4f} |
| Mean net/cycle | {p4r['reversal_p1']['mean_net']:+.1f} | {p4r['reversal_p2a']['mean_net']:+.1f} |
| Cap-walk rate | {p4r['reversal_p1']['capwalk_rate']:.1%} | {p4r['reversal_p2a']['capwalk_rate']:.1%} |
| CW mean loss | {p4r['reversal_p1']['cw_mean_loss']:+.1f} | {p4r['reversal_p2a']['cw_mean_loss']:+.1f} |
| CW mean MAE | {p4r['reversal_p1']['cw_mean_mae']:.1f} | {p4r['reversal_p2a']['cw_mean_mae']:.1f} |

## Decision
**Diagnosis:** {dec['diagnosis']}

**Next step:** {dec['next_step']}
"""
    with open(_OUTPUT_DIR / "p2a_diagnostic_summary.md", 'w') as f:
        f.write(md)

    print("\n  Saved: prong1_base, prong2_tails, prong3_rolling, prong4_revchain, summary.md")


# ============================================================
# Main
# ============================================================

def main():
    t0 = time.time()
    print("=" * 70)
    print("P2a FAILURE DIAGNOSTIC — V1.4 Adaptive Config")
    print("  (P90/P75, SeedDist=15, 10:00-16:00, Roll50 SR>=48, ML=1, cap=2)")
    print("=" * 70)

    p1r = prong_1()
    p2r = prong_2()
    p3r = prong_3()
    p4r = prong_4()
    dec = evaluate_decision(p1r, p2r, p3r, p4r)
    save_all(p1r, p2r, p3r, p4r, dec)

    print(f"\nTotal diagnostic time: {time.time() - t0:.1f}s")


if __name__ == "__main__":
    main()
