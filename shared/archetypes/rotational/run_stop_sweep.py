# archetype: rotational
"""Task 2: Stop parameter sweep on P1.

2A: Independent sweeps for 4A (max_adverse_sigma) and 4C (max_cap_walks)
2B: Combined sweep of best candidates
2C: Select best stop config

Usage:
    python run_stop_sweep.py
"""

import sys
import json
import time
from pathlib import Path

import numpy as np
import pandas as pd

_REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_REPO))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from run_seed_investigation import (
    simulate_daily_flatten, load_data,
    COST_TICKS, TICK_SIZE, FLATTEN_CAP, MAX_LEVELS,
)
from run_phase1_sweep import (
    build_zigzag_lookup, make_adaptive_lookup, make_std_lookup, analyze_step2,
)

_OUTPUT_DIR = Path(__file__).parent / "phase1_results"
EXCLUDE_HOURS = {1, 19, 20}

# Frozen V1.4
SEED_DIST = 15.0
STEP_DIST_INIT = 25.0
ADD_DIST_INIT = 25.0
SEED_START = 10 * 3600
SR_THRESHOLD = 48.0


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


def run_config(prices, tod_secs, sr_roll50, dts, adaptive, std_lu,
               max_adverse_sigma=None, max_cap_walks=None, label=""):
    sim = simulate_daily_flatten(
        prices, tod_secs, sr_roll50, dts,
        seed_dist=SEED_DIST, step_dist=STEP_DIST_INIT, add_dist=ADD_DIST_INIT,
        flatten_reseed_cap=FLATTEN_CAP, max_levels=MAX_LEVELS,
        seed_sr_thresh=SR_THRESHOLD, rev_sr_thresh=SR_THRESHOLD,
        watch_mode='rth_open', cap_action='walk',
        seed_start_tod=SEED_START,
        adaptive_lookup=adaptive,
        max_adverse_sigma=max_adverse_sigma,
        max_cap_walks=max_cap_walks,
        std_lookup=std_lu,
    )
    r = analyze_step2(sim, label)
    cf, trades = build_filtered_cycles(sim)

    # Session-level stats
    session_pnl = cf.groupby('session_id')['net_1t'].sum()
    all_sids = range(1, sim['total_sessions'] + 1)
    session_pnl = session_pnl.reindex(all_sids, fill_value=0.0)
    worst_day = float(session_pnl.min())
    max_cycle_loss = float(cf['net_1t'].min())

    # Stopped cycles
    stopped_4a = cf[cf['exit_reason'] == 'stop_4a']
    stopped_4c = cf[cf['exit_reason'] == 'stop_4c']
    n_stopped = len(stopped_4a) + len(stopped_4c)
    pct_stopped = n_stopped / len(cf) if len(cf) > 0 else 0

    # Consecutive losing days
    daily = session_pnl.values
    max_consec_loss = 0
    cur_consec = 0
    for d in daily:
        if d < 0:
            cur_consec += 1
            max_consec_loss = max(max_consec_loss, cur_consec)
        else:
            cur_consec = 0

    return {
        "label": label,
        "max_adverse_sigma": max_adverse_sigma,
        "max_cap_walks": max_cap_walks,
        "npf": r['npf_1t'], "gpf": r['gpf'],
        "net_pnl": r['net_pnl'], "gross_pnl": round(float(cf['gross_pnl_ticks'].sum()), 1),
        "cycles": r['cycles'],
        "stopped_4a": len(stopped_4a), "stopped_4c": len(stopped_4c),
        "pct_stopped": round(pct_stopped, 4),
        "worst_day": round(worst_day, 1),
        "max_cycle_loss": round(max_cycle_loss, 1),
        "session_win_pct": r['session_win_pct'],
        "clean_pct": r['clean_pct'],
        "mean_daily": r['mean_daily'],
        "std_daily": r['std_daily'],
        "max_consec_loss": max_consec_loss,
        "mean_stopped_pnl": round(float(pd.concat([stopped_4a, stopped_4c])['net_1t'].mean()), 1)
            if n_stopped > 0 else 0,
    }, cf, sim


def print_sweep_table(results, sweep_name):
    print(f"\n  {sweep_name}:")
    print(f"  {'Config':<20} {'NPF':>7} {'Net PnL':>10} {'Stopped':>8} {'%Stop':>6}"
          f" {'Worst Day':>10} {'Max Loss':>9} {'ConsecL':>8}")
    print(f"  {'-' * 89}")
    for r in results:
        label = r['label']
        print(f"  {label:<20} {r['npf']:>7.4f} {r['net_pnl']:>10,.0f}"
              f" {r['stopped_4a'] + r['stopped_4c']:>8}"
              f" {r['pct_stopped']:>6.1%} {r['worst_day']:>10,.0f}"
              f" {r['max_cycle_loss']:>9,.0f} {r['max_consec_loss']:>8}")


def main():
    t0 = time.time()
    print("=" * 70)
    print("TASK 2: Stop Parameter Sweep (P1 only)")
    print("  V1.4 adaptive + SR>=48, stops added on top")
    print("=" * 70)

    # Load P1 data once
    print("\nLoading P1 data...")
    prices, tod_secs, sr_vals, dts = load_data(period='full_p1', use_speedread=True)
    zz_lookup = build_zigzag_lookup()
    adaptive = make_adaptive_lookup(zz_lookup, 5, 2)
    std_lu = make_std_lookup(zz_lookup)
    print(f"  Rolling zigzag std: mean={std_lu['std_values'].mean():.2f},"
          f" min={std_lu['std_values'].min():.2f}, max={std_lu['std_values'].max():.2f}")

    cs = np.cumsum(np.insert(sr_vals, 0, 0))
    w = 50
    sr_roll50 = np.empty_like(sr_vals)
    sr_roll50[:w] = cs[1:w + 1] / np.arange(1, w + 1)
    sr_roll50[w:] = (cs[w + 1:] - cs[1:len(sr_vals) - w + 1]) / w

    args = (prices, tod_secs, sr_roll50, dts, adaptive, std_lu)

    # ================================================================
    # 2A: Independent sweeps
    # ================================================================
    print("\n" + "=" * 70)
    print("2A: Independent Sweeps")
    print("=" * 70)

    # Baseline
    print("\n  Running baseline...")
    r_base, cf_base, sim_base = run_config(*args, label="baseline")

    # 4A sweep
    print("\n  Running 4A sweep (max_adverse_sigma)...")
    results_4a = [r_base]
    for sigma in [1.5, 2.0, 2.5, 3.0]:
        label = f"4A_sigma={sigma}"
        print(f"    {label}...")
        r, cf, sim = run_config(*args, max_adverse_sigma=sigma, label=label)
        results_4a.append(r)

    print_sweep_table(results_4a, "4A: Max Adverse Sigma")

    # 4C sweep
    print("\n  Running 4C sweep (max_cap_walks)...")
    results_4c = [r_base]
    for mcw in [1, 2, 3, 4]:
        label = f"4C_maxcw={mcw}"
        print(f"    {label}...")
        r, cf, sim = run_config(*args, max_cap_walks=mcw, label=label)
        results_4c.append(r)

    print_sweep_table(results_4c, "4C: Max Cap-Walks")

    # Counterfactual: compare stopped cycle losses with baseline cycle losses
    # For each stopped cycle, find the cycle at the same position in the baseline
    # This is approximate since the chains diverge, but we can look at
    # baseline cap-walk cycle statistics for comparison
    cw_base = cf_base[cf_base['cycle_cap_walks'] > 0]
    print(f"\n  Baseline cap-walk cycle stats (counterfactual reference):")
    print(f"    Cap-walk cycles: {len(cw_base)}")
    print(f"    Mean net PnL: {cw_base['net_1t'].mean():+.1f}")
    print(f"    % eventually positive: {(cw_base['net_1t'] > 0).mean():.1%}")
    print(f"    Mean MAE: {cw_base['mae'].mean():.1f}")

    # For 4C specifically: baseline cycles with cap_walks > N
    for mcw in [1, 2, 3, 4]:
        excess = cf_base[cf_base['cycle_cap_walks'] > mcw]
        if len(excess) > 0:
            recovered = (excess['net_1t'] > 0).mean()
            print(f"    Cycles with CW > {mcw}: {len(excess)},"
                  f" {recovered:.0%} eventually recovered,"
                  f" mean net = {excess['net_1t'].mean():+.1f}")

    # For 4A: baseline cycles with MAE > N * std at their entry
    # We need to compute the std at each cycle entry
    entry_trades_base = pd.DataFrame(sim_base['trade_records'])
    entry_trades_base = entry_trades_base[entry_trades_base['action'].isin(['SEED', 'REVERSAL'])]
    # Get bar_idx for std lookup
    bar_idx_map = entry_trades_base.groupby('cycle_id')['bar_idx'].first()
    cf_base['entry_bar_idx'] = cf_base['cycle_id'].map(bar_idx_map)

    _std_ts = std_lu['timestamps']
    _std_vals = std_lu['std_values']

    cf_base_std = []
    for _, row in cf_base.iterrows():
        bi = row.get('entry_bar_idx', None)
        if bi is not None and not np.isnan(bi):
            ts = dts[int(bi)].astype('int64')
            sidx = np.searchsorted(_std_ts, ts, side='right') - 1
            if sidx >= 0:
                cf_base_std.append(_std_vals[sidx])
            else:
                cf_base_std.append(np.nan)
        else:
            cf_base_std.append(np.nan)
    cf_base['entry_std'] = cf_base_std

    print(f"\n  Counterfactual for 4A (baseline cycles that WOULD be stopped):")
    for sigma in [1.5, 2.0, 2.5, 3.0]:
        excess = cf_base[(cf_base['entry_std'] > 0) &
                         (cf_base['mae'] > sigma * cf_base['entry_std'])]
        if len(excess) > 0:
            recovered = (excess['net_1t'] > 0).mean()
            print(f"    Cycles with MAE > {sigma}*std: {len(excess)},"
                  f" {recovered:.0%} eventually recovered,"
                  f" mean net = {excess['net_1t'].mean():+.1f}")

    # ================================================================
    # 2B: Combined sweep
    # ================================================================
    print("\n" + "=" * 70)
    print("2B: Combined Sweep")
    print("=" * 70)

    # Pick best 2 from each independent sweep (by worst-day improvement)
    sorted_4a = sorted(results_4a[1:], key=lambda x: x['worst_day'], reverse=True)[:2]
    sorted_4c = sorted(results_4c[1:], key=lambda x: x['worst_day'], reverse=True)[:2]

    print(f"\n  Best 4A candidates (by worst-day): "
          f"{[r['label'] for r in sorted_4a]}")
    print(f"  Best 4C candidates (by worst-day): "
          f"{[r['label'] for r in sorted_4c]}")

    results_combined = [r_base]
    # Each alone (already have these)
    for r in sorted_4a + sorted_4c:
        results_combined.append(r)

    # Grid: 2x2
    for r4a in sorted_4a:
        for r4c in sorted_4c:
            sigma = r4a['max_adverse_sigma']
            mcw = r4c['max_cap_walks']
            label = f"4A={sigma}+4C={mcw}"
            print(f"    {label}...")
            r, cf, sim = run_config(*args, max_adverse_sigma=sigma,
                                     max_cap_walks=mcw, label=label)
            results_combined.append(r)

    print_sweep_table(results_combined, "Combined Sweep (baseline + individuals + grid)")

    # ================================================================
    # 2C: Select best
    # ================================================================
    print("\n" + "=" * 70)
    print("2C: Best Stop Config Selection")
    print("=" * 70)

    baseline_worst = r_base['worst_day']
    candidates = [r for r in results_combined[1:] if r['npf'] > 1.10]

    if not candidates:
        print(f"\n  NO candidate with NPF > 1.10 found.")
        print(f"  Kill condition: stops not effective on P1.")
        all_results = {"4a_sweep": results_4a, "4c_sweep": results_4c,
                       "combined": results_combined, "selected": None,
                       "kill_condition": True}
        with open(_OUTPUT_DIR / "stop_sweep_results.json", 'w') as f:
            json.dump(all_results, f, indent=2, default=str)
        return

    # Sort by worst-day improvement (larger = better)
    for c in candidates:
        c['worst_day_improvement'] = 1.0 - c['worst_day'] / baseline_worst

    candidates.sort(key=lambda x: x['worst_day_improvement'], reverse=True)
    best = candidates[0]

    print(f"\n  Baseline worst day: {baseline_worst:,.0f}")
    print(f"\n  Top candidates (NPF > 1.10, sorted by worst-day improvement):")
    print(f"  {'Config':<20} {'NPF':>7} {'Worst Day':>10} {'Improvement':>12} {'Net PnL':>10}")
    print(f"  {'-' * 69}")
    for c in candidates[:5]:
        print(f"  {c['label']:<20} {c['npf']:>7.4f} {c['worst_day']:>10,.0f}"
              f" {c['worst_day_improvement']:>12.1%} {c['net_pnl']:>10,.0f}")

    # Kill condition: > 30% worst-day reduction?
    if best['worst_day_improvement'] < 0.30:
        print(f"\n  KILL: Best improvement = {best['worst_day_improvement']:.1%} < 30% threshold")
        print(f"  Stops are NOT effective enough on P1.")
        all_results = {"4a_sweep": results_4a, "4c_sweep": results_4c,
                       "combined": results_combined, "selected": None,
                       "kill_condition": True,
                       "best_improvement": best['worst_day_improvement']}
        with open(_OUTPUT_DIR / "stop_sweep_results.json", 'w') as f:
            json.dump(all_results, f, indent=2, default=str)
        return

    print(f"\n  SELECTED: {best['label']}")
    print(f"    NPF: {best['npf']:.4f} (baseline {r_base['npf']:.4f})")
    print(f"    Net PnL: {best['net_pnl']:+,.0f} (baseline {r_base['net_pnl']:+,.0f})")
    print(f"    Worst day: {best['worst_day']:,.0f} (baseline {baseline_worst:,.0f},"
          f" improvement {best['worst_day_improvement']:.1%})")
    print(f"    Stopped cycles: {best['stopped_4a'] + best['stopped_4c']}"
          f" ({best['pct_stopped']:.1%})")
    print(f"    Max consecutive losing days: {best['max_consec_loss']}"
          f" (baseline {r_base['max_consec_loss']})")

    all_results = {"4a_sweep": results_4a, "4c_sweep": results_4c,
                   "combined": results_combined, "selected": best,
                   "kill_condition": False,
                   "baseline_worst_day": baseline_worst}

    with open(_OUTPUT_DIR / "stop_sweep_results.json", 'w') as f:
        json.dump(all_results, f, indent=2, default=str)
    print(f"\n  Saved: stop_sweep_results.json")

    print(f"\nTotal sweep time: {time.time() - t0:.1f}s")


if __name__ == "__main__":
    main()
