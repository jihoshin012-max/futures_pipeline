# archetype: rotational
# STATUS: ONE-TIME
# PURPOSE: V1.1 SD=50 exploratory diagnostic
# LAST RUN: 2026-03

"""Exploratory diagnostic: V1.1 config with SD=50, INIT_QTY=2, ML=4.

No optimization — diagnostic runs on P1, P2a, P2b with block analysis.

Config:
  StepDist=50 fixed, AddDist=50 (coupled), SeedDist=50
  INIT_QTY=2, ML=4 (geometric: 2->2->4->8), MAX_CS=10
  No SpeedRead filter, Full RTH (09:30-16:00)
  cap_action=flatten_reseed (V1.1), flatten_reseed_cap=10
  cost_ticks=1

Usage:
    python run_v11_sd50_diagnostic.py
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

# Monkey-patch module constants BEFORE importing simulation function
import run_seed_investigation as rsi
rsi.INIT_QTY = 2
rsi.MAX_CS = 10

from run_seed_investigation import simulate_daily_flatten, load_data, FLATTEN_TOD
from shared.data_loader import load_bars
from run_seed_investigation import _P1_START, _P1_END

_OUTPUT_DIR = Path(__file__).parent / "phase1_results"
_P2_1TICK = _REPO / "stages/01-data/data/bar_data/tick/NQ_BarData_1tick_rot_P2.csv"

# V1.1 SD=50 config
SD = 50.0
ML = 4
CAP = 10         # flatten_reseed_cap (max position)
CAP_ACTION = 'flatten_reseed'
COST = 1

# Date boundaries
P2A_START = dt_mod.date(2025, 12, 17)
P2A_END = dt_mod.date(2026, 1, 30)
P2B_START = dt_mod.date(2026, 2, 1)
P2B_END = dt_mod.date(2026, 3, 13)

EXCLUDE_HOURS = {1, 19, 20}

# Block definitions (seconds from midnight)
BLOCKS = {
    'Open':      (9*3600+30*60, 10*3600),
    'Morning':   (10*3600,      11*3600+30*60),
    'Midday':    (11*3600+30*60, 13*3600+30*60),
    'Afternoon': (13*3600+30*60, 15*3600),
    'Close':     (15*3600,       16*3600),
}


def run_period(prices, tod_secs, dts, label, seed_start_tod=None):
    """Run V1.1 SD=50 on a data period. Returns (metrics_dict, cf, sim)."""
    # No SpeedRead — all pass
    sr_vals = np.full(len(prices), 100.0, dtype=np.float64)

    watch_mode = 'rth_open' if seed_start_tod is not None else 'current'

    sim = simulate_daily_flatten(
        prices, tod_secs, sr_vals, dts,
        seed_dist=SD, step_dist=SD, add_dist=SD,
        flatten_reseed_cap=CAP, max_levels=ML,
        seed_sr_thresh=-999.0, rev_sr_thresh=-999.0,
        watch_mode=watch_mode, cap_action=CAP_ACTION,
        seed_start_tod=seed_start_tod,
        cost_ticks=COST,
    )

    trades = pd.DataFrame(sim['trade_records'])
    cycles = pd.DataFrame(sim['cycle_records'])
    if len(cycles) == 0:
        return None, None, sim

    entry_trades = trades[trades['action'].isin(['SEED', 'REVERSAL'])]
    ce = entry_trades.groupby('cycle_id')['datetime'].first().reset_index()
    ce.columns = ['cycle_id', 'entry_dt']
    cycles = cycles.merge(ce, on='cycle_id', how='left')
    cycles['hour'] = pd.to_datetime(cycles['entry_dt']).dt.hour
    cf = cycles[~cycles['hour'].isin(EXCLUDE_HOURS)].copy()
    if len(cf) == 0:
        return None, None, sim

    valid_ids = set(cf['cycle_id'])
    tf = trades[trades['cycle_id'].isin(valid_ids)]
    cc = tf.groupby('cycle_id')['cost_ticks'].sum()
    cf['cost'] = cf['cycle_id'].map(cc).fillna(0)
    cf['net_1t'] = cf['gross_pnl_ticks'] - cf['cost']

    # Max position reached
    max_pos = cf['max_position_qty'].max() if 'max_position_qty' in cf.columns else 0

    # Session PnL
    spnl = cf.groupby('session_id')['net_1t'].sum()
    all_sids = range(1, sim['total_sessions'] + 1)
    spnl = spnl.reindex(all_sids, fill_value=0.0)

    gw = cf.loc[cf['gross_pnl_ticks'] > 0, 'gross_pnl_ticks'].sum()
    gl = abs(cf.loc[cf['gross_pnl_ticks'] <= 0, 'gross_pnl_ticks'].sum())
    gpf = gw / gl if gl > 0 else 0
    nw = cf.loc[cf['net_1t'] > 0, 'net_1t'].sum()
    nl = abs(cf.loc[cf['net_1t'] <= 0, 'net_1t'].sum())
    npf = nw / nl if nl > 0 else 0

    metrics = {
        'label': label,
        'npf': round(npf, 4), 'gpf': round(gpf, 4),
        'net_pnl': round(float(cf['net_1t'].sum()), 0),
        'gross_pnl': round(float(cf['gross_pnl_ticks'].sum()), 0),
        'cycles': len(cf),
        'sessions': sim['total_sessions'],
        'worst_day': round(float(spnl.min()), 0),
        'max_position': int(max_pos),
        'max_mae': round(float(cf['mae'].max()), 2),
        'mean_mae': round(float(cf['mae'].mean()), 2),
        'session_win_pct': round(float((spnl > 0).mean()), 4),
        'mean_daily': round(float(spnl.mean()), 1),
    }

    # Entry/exit time for block analysis
    exit_trades = trades[trades['action'] == 'FLATTEN']
    exit_map = exit_trades.groupby('cycle_id')['datetime'].last().reset_index()
    exit_map.columns = ['cycle_id', 'exit_dt']
    cf = cf.merge(exit_map, on='cycle_id', how='left')
    cf['entry_tod'] = pd.to_datetime(cf['entry_dt']).dt.hour * 3600 + \
                      pd.to_datetime(cf['entry_dt']).dt.minute * 60
    cf['exit_tod'] = pd.to_datetime(cf['exit_dt']).dt.hour * 3600 + \
                     pd.to_datetime(cf['exit_dt']).dt.minute * 60

    # Classify entry/exit block
    def classify_block(tod_val):
        for name, (start, end) in BLOCKS.items():
            if start <= tod_val < end:
                return name
        return 'Other'

    cf['entry_block'] = cf['entry_tod'].apply(classify_block)
    cf['exit_block'] = cf['exit_tod'].apply(classify_block)
    cf['spillover'] = cf['entry_block'] != cf['exit_block']

    return metrics, cf, sim


def block_analysis(cf, label):
    """Per-block breakdown."""
    print(f"\n  Block breakdown ({label}):")
    print(f"  {'Block':<12} {'NPF':>7} {'Cycles':>7} {'MeanPnL':>9} {'CW%':>6}"
          f" {'MeanPos':>8} {'Spill%':>7}")
    print(f"  {'-' * 64}")

    block_results = {}
    for block_name in ['Open', 'Morning', 'Midday', 'Afternoon', 'Close']:
        bc = cf[cf['entry_block'] == block_name]
        n = len(bc)
        if n == 0:
            print(f"  {block_name:<12} {'—':>7} {0:>7} {'—':>9} {'—':>6} {'—':>8} {'—':>7}")
            block_results[block_name] = {'cycles': 0}
            continue

        nw = bc.loc[bc['net_1t'] > 0, 'net_1t'].sum()
        nl = abs(bc.loc[bc['net_1t'] <= 0, 'net_1t'].sum())
        npf = nw / nl if nl > 0 else 0
        mean_pnl = bc['net_1t'].mean()
        cw_rate = (bc['cycle_cap_walks'] > 0).mean() if 'cycle_cap_walks' in bc.columns else 0
        mean_pos = bc['max_position_qty'].mean() if 'max_position_qty' in bc.columns else 0
        spill_pct = bc['spillover'].mean()

        print(f"  {block_name:<12} {npf:>7.3f} {n:>7} {mean_pnl:>+9.1f} {cw_rate:>6.1%}"
              f" {mean_pos:>8.1f} {spill_pct:>7.1%}")

        block_results[block_name] = {
            'cycles': n, 'npf': round(npf, 4), 'mean_pnl': round(float(mean_pnl), 1),
            'cw_rate': round(float(cw_rate), 4), 'mean_pos': round(float(mean_pos), 2),
            'spill_pct': round(float(spill_pct), 4),
        }

    # Spillover matrix
    spill = cf[cf['spillover']]
    if len(spill) > 0:
        print(f"\n  Spillover matrix (entry -> exit):")
        xt = pd.crosstab(spill['entry_block'], spill['exit_block'])
        for eb in ['Open', 'Morning', 'Midday', 'Afternoon', 'Close']:
            if eb in xt.index:
                vals = [f"{xt.loc[eb, xb]:>3}" if xb in xt.columns else "  0"
                        for xb in ['Open', 'Morning', 'Midday', 'Afternoon', 'Close']]
                print(f"    {eb:<12} -> {' '.join(vals)}")
        print(f"  Total spillover cycles: {len(spill)} ({len(spill)/len(cf):.0%})")

    return block_results


def load_p2_period(start_date, end_date):
    """Load P2 1-tick data for a date range, return (prices, tod, dts)."""
    print(f"  Loading P2 1-tick data ({start_date} to {end_date})...")
    t0 = time.time()
    tick_bars = load_bars(str(_P2_1TICK))
    tick_data = tick_bars[
        (tick_bars['datetime'].dt.date >= start_date) &
        (tick_bars['datetime'].dt.date <= end_date)
    ].reset_index(drop=True)
    print(f"    {len(tick_data):,} ticks in {time.time() - t0:.1f}s")

    prices = tick_data['Last'].values.astype(np.float64)
    dts = tick_data['datetime'].values
    hours = tick_data['datetime'].dt.hour.values.astype(np.int32)
    minutes = tick_data['datetime'].dt.minute.values.astype(np.int32)
    seconds = tick_data['datetime'].dt.second.values.astype(np.int32)
    tod_secs = hours * 3600 + minutes * 60 + seconds
    return prices, tod_secs, dts


def main():
    t0 = time.time()
    print("=" * 70)
    print("V1.1 SD=50 DIAGNOSTIC")
    print("  SD=50, AD=50, SeedDist=50, INIT_QTY=2, ML=4, MAX_CS=10")
    print("  cap=10 (flatten_reseed), no SpeedRead, cost=1")
    print("=" * 70)

    all_results = {}

    # ================================================================
    # P1 (09:30 and 10:00 start)
    # ================================================================
    print("\n--- Loading P1 data ---")
    prices_p1, tod_p1, sr_p1, dts_p1 = load_data(period='full_p1', use_speedread=False)

    for start_label, start_tod in [("P1_0930", None), ("P1_1000", 10*3600)]:
        print(f"\n{'='*70}")
        print(f"  {start_label}")
        print(f"{'='*70}")
        m, cf, sim = run_period(prices_p1, tod_p1, dts_p1, start_label,
                                seed_start_tod=start_tod)
        if m is None:
            print("  No cycles.")
            continue

        print(f"  NPF={m['npf']:.4f}  GPF={m['gpf']:.4f}  Net={m['net_pnl']:+,.0f}"
              f"  Cycles={m['cycles']}  Sessions={m['sessions']}")
        print(f"  Worst day={m['worst_day']:+,.0f}  Max pos={m['max_position']}"
              f"  Max MAE={m['max_mae']:.1f}  Session win={m['session_win_pct']:.1%}")

        block_results = block_analysis(cf, start_label)
        m['blocks'] = block_results
        all_results[start_label] = m

    # ================================================================
    # P2a (09:30 and 10:00 start)
    # ================================================================
    print("\n--- Loading P2a data ---")
    prices_p2a, tod_p2a, dts_p2a = load_p2_period(P2A_START, P2A_END)

    for start_label, start_tod in [("P2a_0930", None), ("P2a_1000", 10*3600)]:
        print(f"\n{'='*70}")
        print(f"  {start_label}")
        print(f"{'='*70}")
        m, cf, sim = run_period(prices_p2a, tod_p2a, dts_p2a, start_label,
                                seed_start_tod=start_tod)
        if m is None:
            print("  No cycles.")
            continue

        print(f"  NPF={m['npf']:.4f}  GPF={m['gpf']:.4f}  Net={m['net_pnl']:+,.0f}"
              f"  Cycles={m['cycles']}  Sessions={m['sessions']}")
        print(f"  Worst day={m['worst_day']:+,.0f}  Max pos={m['max_position']}"
              f"  Max MAE={m['max_mae']:.1f}  Session win={m['session_win_pct']:.1%}")

        block_results = block_analysis(cf, start_label)
        m['blocks'] = block_results
        all_results[start_label] = m

    # ================================================================
    # P2b (09:30 and 10:00 start)
    # ================================================================
    print("\n--- Loading P2b data ---")
    prices_p2b, tod_p2b, dts_p2b = load_p2_period(P2B_START, P2B_END)

    for start_label, start_tod in [("P2b_0930", None), ("P2b_1000", 10*3600)]:
        print(f"\n{'='*70}")
        print(f"  {start_label}")
        print(f"{'='*70}")
        m, cf, sim = run_period(prices_p2b, tod_p2b, dts_p2b, start_label,
                                seed_start_tod=start_tod)
        if m is None:
            print("  No cycles.")
            continue

        print(f"  NPF={m['npf']:.4f}  GPF={m['gpf']:.4f}  Net={m['net_pnl']:+,.0f}"
              f"  Cycles={m['cycles']}  Sessions={m['sessions']}")
        print(f"  Worst day={m['worst_day']:+,.0f}  Max pos={m['max_position']}"
              f"  Max MAE={m['max_mae']:.1f}  Session win={m['session_win_pct']:.1%}")

        block_results = block_analysis(cf, start_label)
        m['blocks'] = block_results
        all_results[start_label] = m

    # ================================================================
    # Summary comparison
    # ================================================================
    print(f"\n{'='*70}")
    print("SUMMARY COMPARISON")
    print(f"{'='*70}")
    print(f"  {'Config':<14} {'NPF':>7} {'GPF':>7} {'Net PnL':>10} {'Cycles':>7}"
          f" {'Worst':>8} {'MaxPos':>7} {'MaxMAE':>7} {'Win%':>6}")
    print(f"  {'-' * 83}")
    for label in ['P1_0930', 'P1_1000', 'P2a_0930', 'P2a_1000', 'P2b_0930', 'P2b_1000']:
        r = all_results.get(label)
        if r is None:
            continue
        print(f"  {label:<14} {r['npf']:>7.4f} {r['gpf']:>7.4f} {r['net_pnl']:>+10,.0f}"
              f" {r['cycles']:>7} {r['worst_day']:>+8,.0f} {r['max_position']:>7}"
              f" {r['max_mae']:>7.0f} {r['session_win_pct']:>6.0%}")

    # Save
    _OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    with open(_OUTPUT_DIR / "v11_sd50_diagnostic.json", 'w') as f:
        json.dump(all_results, f, indent=2, default=str)
    print(f"\n  Saved: v11_sd50_diagnostic.json")
    print(f"\nTotal time: {time.time() - t0:.1f}s")


if __name__ == "__main__":
    main()
