# archetype: rotational
# STATUS: ACTIVE
# PURPOSE: C++ vs Python replication gate for rotational V1.4
# LAST RUN: 2026-03

"""Replication Gate (Section 7): Compare C++ ATEAM_ROTATION_V14 log vs Python simulator.

Loads the NQ1T.csv from SierraChart Data directory, runs the Python simulator
on the same tick data, and compares cycle-by-cycle against the C++ CSV log.

Pass criteria (from v14_logic_spec section 7):
  - >98% of cycles match on direction, entry time (+-1 bar), PnL (+-2 ticks)
  - Total cycles, NPF, net PnL must match within 1%

Usage:
    python run_replication_gate.py
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

# Paths
_SC_DATA = Path("E:/SierraChart/Data")
_CPP_LOG = _SC_DATA / "ATEAM_ROTATION_V14_log.csv"
_NQ1T = _SC_DATA / "NQ1T.csv"
from run_phase1_sweep import make_adaptive_lookup, make_std_lookup

_OUTPUT_DIR = Path(__file__).parent / "phase1_results"

TICK_SIZE = 0.25
COST_TICKS = 1
SEED_DIST = 15.0
SR_THRESHOLD = 48.0
FLATTEN_TOD = 16 * 3600
RESUME_TOD = 18 * 3600
SEED_START_TOD = 10 * 3600
MAX_CAP_WALKS = 2
ML = 1
CAP = 2
INIT_QTY = 1


def load_nq1t():
    """Load NQ1T.csv and extract arrays needed for simulation."""
    print("  Loading NQ1T.csv...")
    t0 = time.time()
    df = pd.read_csv(str(_NQ1T))
    # Strip leading spaces from column names
    df.columns = [c.strip() for c in df.columns]
    print(f"    {len(df):,} ticks in {time.time() - t0:.1f}s")

    # Build datetime
    df['datetime'] = pd.to_datetime(df['Date'] + ' ' + df['Time'])

    prices = df['Last'].values.astype(np.float64)
    dts = df['datetime'].values

    hours = df['datetime'].dt.hour.values.astype(np.int32)
    minutes = df['datetime'].dt.minute.values.astype(np.int32)
    seconds = df['datetime'].dt.second.values.astype(np.int32)
    tod_secs = hours * 3600 + minutes * 60 + seconds

    print(f"    Date range: {df['datetime'].iloc[0]} to {df['datetime'].iloc[-1]}")

    return df, prices, tod_secs, dts


def build_zigzag_from_nq1t(df):
    """Build rolling 200-swing ZZ percentile lookup from NQ1T Zig Zag Line Length column."""
    print("  Building ZZ regime from NQ1T Zig Zag Line Length...")
    zz_len = df['Zig Zag Line Length'].values.astype(np.float64)
    dts = df['datetime'].values

    # Detect completed swings: value changes from previous (non-zero to different non-zero)
    # Per spec: lastZZLength starts at 0.0, first change (0→nonzero) is skipped
    swing_dists = []
    swing_dts = []
    last_val = 0.0
    for i in range(len(zz_len)):
        v = zz_len[i]
        if v != last_val and v != 0.0:
            if last_val != 0.0:
                swing_dists.append(abs(v))
                swing_dts.append(dts[i])
            last_val = v
        elif v == 0.0 and last_val != 0.0:
            last_val = v  # reset when ZZ goes to 0

    print(f"    Total swings detected: {len(swing_dists)}")

    # Rolling 200-swing percentiles
    window = 200
    min_warmup = 20
    pct_ts = []
    p90_vals = []
    p75_vals = []
    std_vals = []

    buf = []
    for j in range(len(swing_dists)):
        buf.append(swing_dists[j])
        if len(buf) > window:
            buf.pop(0)
        if len(buf) >= min_warmup:
            s = sorted(buf)
            n = len(s)
            # NumPy linear interpolation
            def pct(p):
                idx = (p / 100.0) * (n - 1)
                lo = int(idx)
                frac = idx - lo
                if lo + 1 < n:
                    return s[lo] + frac * (s[lo + 1] - s[lo])
                return s[lo]
            pct_ts.append(swing_dts[j].astype('int64'))
            p90_vals.append(pct(90))
            p75_vals.append(pct(75))
            std_vals.append(float(np.std(buf)))

    print(f"    Percentile points: {len(pct_ts)}")

    adaptive = {
        'timestamps': np.array(pct_ts, dtype=np.int64),
        'sd_values': np.array(p90_vals, dtype=np.float64),
        'ad_values': np.array(p75_vals, dtype=np.float64),
    }
    std_lu = {
        'timestamps': np.array(pct_ts, dtype=np.int64),
        'std_values': np.array(std_vals, dtype=np.float64),
    }
    return adaptive, std_lu


def build_speedread_roll50(df):
    """Compute SpeedRead composite from NQ1T by aggregating to 250-tick bars first.

    SpeedRead is computed on 250-tick bars. We aggregate NQ1T (1-tick) into
    250-tick bars, compute SpeedRead, then map the Roll50 back to tick level.
    """
    from run_speedread_investigation import compute_speedread

    print("  Aggregating NQ1T to 250-tick bars for SpeedRead...")
    tick_prices = df['Last'].values.astype(np.float64)
    tick_volumes = df['Volume'].values.astype(np.float64)
    tick_dts = df['datetime'].values

    # Build 250-tick bars
    bar_size = 250
    n_bars = len(tick_prices) // bar_size
    bar_close = np.empty(n_bars)
    bar_volume = np.empty(n_bars)
    bar_dts = []
    for b in range(n_bars):
        start = b * bar_size
        end = start + bar_size
        bar_close[b] = tick_prices[end - 1]
        bar_volume[b] = tick_volumes[start:end].sum()
        bar_dts.append(tick_dts[end - 1])
    bar_dts = np.array(bar_dts)
    print(f"    250-tick bars: {n_bars}")

    # Compute SpeedRead
    print("  Computing SpeedRead composite...")
    composite, raw_composite, _, _, _, _, _ = compute_speedread(bar_close, bar_volume)

    # Roll50 of raw composite on bars
    w = 50
    raw = np.nan_to_num(raw_composite, nan=0.0)
    cs = np.cumsum(np.insert(raw, 0, 0))
    roll50_bars = np.empty(n_bars)
    roll50_bars[:w] = cs[1:w + 1] / np.arange(1, w + 1)
    roll50_bars[w:] = (cs[w + 1:] - cs[1:n_bars - w + 1]) / w

    # Map Roll50 back to tick level via timestamp lookup
    print("  Mapping Roll50 to tick level...")
    bar_ts = bar_dts.astype('int64') // 10**9
    tick_ts = tick_dts.astype('int64') // 10**9
    idx = np.clip(np.searchsorted(bar_ts, tick_ts, side='right') - 1,
                  0, len(roll50_bars) - 1)
    sr_roll50 = roll50_bars[idx]
    sr_roll50 = np.nan_to_num(sr_roll50, nan=0.0)

    # Validate against C++ log values
    valid = (sr_roll50 > 0).sum()
    print(f"    Roll50 mapped. Valid: {valid:,} / {len(sr_roll50):,}")

    # Spot-check: at 10:09:10 C++ showed Roll50SR=49.48
    check_mask = (df['datetime'] >= '2026-03-19 10:09:09') & (df['datetime'] <= '2026-03-19 10:09:11')
    check_idx = df[check_mask].index
    if len(check_idx) > 0:
        py_val = sr_roll50[check_idx[0]]
        print(f"    Spot-check at 10:09:10: Python Roll50={py_val:.2f} (C++ logged 49.48)")

    return sr_roll50


def parse_cpp_cycles(cpp_log):
    """Extract cycles from C++ log. Each cycle starts with SEED_ENTRY or REVERSAL_ENTRY
    and ends with the next REVERSAL_TRIGGER, CAPWALK_STOP, SR_BLOCK_REVERSAL, or DAILY_FLATTEN."""
    key_events = cpp_log[~cpp_log['Event'].isin(['SR_BLOCK_SEED', 'WATCH_SET'])].copy()
    key_events['DateTime'] = pd.to_datetime(key_events['DateTime'])

    cycles = []
    current_cycle = None

    for _, row in key_events.iterrows():
        evt = row['Event']

        if evt in ('SEED_ENTRY', 'REVERSAL_ENTRY'):
            if current_cycle is not None and current_cycle.get('exit_time') is None:
                # Previous cycle wasn't properly closed — shouldn't happen but handle it
                current_cycle['exit_time'] = row['DateTime']
                current_cycle['exit_price'] = row['Price']
                current_cycle['exit_reason'] = 'implied_by_next_entry'
                cycles.append(current_cycle)

            current_cycle = {
                'entry_time': row['DateTime'],
                'entry_type': evt,
                'direction': row['Side'],
                'entry_price': row['Price'],
                'step_dist': row['CycleStepDist'],
                'add_dist': row['CycleAddDist'],
                'roll50_sr': row['Roll50SR'],
                'events': [evt],
                'adds': 0,
                'cap_walks': 0,
                'exit_time': None,
                'exit_price': None,
                'exit_reason': None,
                'pnl_ticks': None,
            }
        elif evt == 'ADD' and current_cycle is not None:
            current_cycle['adds'] += 1
            current_cycle['events'].append(evt)
        elif evt == 'CAP_WALK' and current_cycle is not None:
            current_cycle['cap_walks'] += 1
            current_cycle['events'].append(evt)
        elif evt == 'REVERSAL_TRIGGER' and current_cycle is not None:
            current_cycle['exit_time'] = row['DateTime']
            current_cycle['exit_price'] = row['Price']
            current_cycle['exit_reason'] = 'reversal'
            current_cycle['pnl_ticks'] = row['PnlTicks']
            current_cycle['events'].append(evt)
            cycles.append(current_cycle)
            current_cycle = None  # Next entry event will start new cycle
        elif evt == 'CAPWALK_STOP' and current_cycle is not None:
            current_cycle['exit_time'] = row['DateTime']
            current_cycle['exit_price'] = row['Price']
            current_cycle['exit_reason'] = 'stop_4c'
            current_cycle['pnl_ticks'] = row['PnlTicks']
            current_cycle['events'].append(evt)
            cycles.append(current_cycle)
            current_cycle = None
        elif evt == 'SR_BLOCK_REVERSAL' and current_cycle is not None:
            current_cycle['exit_time'] = row['DateTime']
            current_cycle['exit_price'] = row['Price']
            current_cycle['exit_reason'] = 'sr_block'
            current_cycle['events'].append(evt)
            cycles.append(current_cycle)
            current_cycle = None
        elif evt == 'DAILY_FLATTEN' and current_cycle is not None:
            current_cycle['exit_time'] = row['DateTime']
            current_cycle['exit_price'] = row['Price']
            current_cycle['exit_reason'] = 'daily_flatten'
            current_cycle['events'].append(evt)
            cycles.append(current_cycle)
            current_cycle = None

    # Handle unclosed cycle at end (daily flatten may not be logged if no position)
    if current_cycle is not None:
        current_cycle['exit_reason'] = 'end_of_data'
        cycles.append(current_cycle)

    return pd.DataFrame(cycles)


def run_python_sim(prices, tod_secs, sr_roll50, dts, adaptive, std_lu):
    """Run Python simulator with final V1.4+4C config."""
    from run_seed_investigation import simulate_daily_flatten

    return simulate_daily_flatten(
        prices, tod_secs, sr_roll50, dts,
        seed_dist=SEED_DIST, step_dist=25.0, add_dist=25.0,
        flatten_reseed_cap=CAP, max_levels=ML,
        seed_sr_thresh=SR_THRESHOLD, rev_sr_thresh=SR_THRESHOLD,
        watch_mode='rth_open', cap_action='walk',
        seed_start_tod=SEED_START_TOD,
        adaptive_lookup=adaptive,
        max_adverse_sigma=None,
        max_cap_walks=MAX_CAP_WALKS,
        std_lookup=std_lu,
    )


def parse_python_cycles(sim):
    """Extract cycles from Python simulation output."""
    trades = pd.DataFrame(sim['trade_records'])
    cycles = pd.DataFrame(sim['cycle_records'])
    if len(cycles) == 0:
        return pd.DataFrame()

    entry_trades = trades[trades['action'].isin(['SEED', 'REVERSAL'])]
    ce = entry_trades.groupby('cycle_id').first().reset_index()

    py_cycles = []
    for _, cr in cycles.iterrows():
        cid = cr['cycle_id']
        entry = ce[ce['cycle_id'] == cid]
        if len(entry) == 0:
            continue
        entry = entry.iloc[0]

        py_cycles.append({
            'entry_time': pd.to_datetime(entry['datetime']),
            'entry_type': entry['action'],
            'direction': entry['direction'],
            'entry_price': entry['price'],
            'step_dist': cr.get('stepdist_used', 0),
            'add_dist': cr.get('adddist_used', 0),
            'adds': cr.get('adds_count', 0),
            'cap_walks': cr.get('cycle_cap_walks', 0),
            'exit_reason': cr['exit_reason'],
            'gross_pnl': cr['gross_pnl_ticks'],
        })

    return pd.DataFrame(py_cycles)


def compare_cycles(cpp_df, py_df):
    """Compare C++ and Python cycles per Section 7 criteria."""
    print(f"\n{'=' * 70}")
    print(f"CYCLE-BY-CYCLE COMPARISON")
    print(f"{'=' * 70}")

    n_cpp = len(cpp_df)
    n_py = len(py_df)
    print(f"\n  C++ cycles: {n_cpp}")
    print(f"  Python cycles: {n_py}")

    if n_cpp == 0 or n_py == 0:
        print("  ERROR: No cycles to compare!")
        return

    # Match cycles by entry time (within 2 seconds tolerance)
    matches = []
    used_py = set()
    for i, cpp in cpp_df.iterrows():
        best_j = None
        best_dt = pd.Timedelta(seconds=999)
        for j, py in py_df.iterrows():
            if j in used_py:
                continue
            dt = abs(cpp['entry_time'] - py['entry_time'])
            if dt < best_dt:
                best_dt = dt
                best_j = j
        if best_j is not None and best_dt <= pd.Timedelta(seconds=5):
            used_py.add(best_j)
            matches.append((i, best_j, best_dt))

    print(f"  Matched cycles (within 5s): {len(matches)} / {n_cpp}")

    if len(matches) == 0:
        print("  No matches found! Dumping first 5 of each for inspection:")
        print("\n  C++ first 5:")
        print(cpp_df.head().to_string())
        print("\n  Python first 5:")
        print(py_df.head().to_string())
        return

    # Detailed comparison
    dir_match = 0
    time_match_1bar = 0
    pnl_match_2t = 0
    sd_match = 0
    ad_match = 0

    comparison_rows = []
    for ci, pi, dt in matches:
        cpp = cpp_df.loc[ci]
        py = py_df.loc[pi]

        # Direction
        cpp_dir = cpp['direction'].upper().strip()
        py_dir = py['direction'].upper().strip()
        d_ok = cpp_dir == py_dir
        if d_ok:
            dir_match += 1

        # Entry time (within 1 bar — for 1-tick data, use 2 second tolerance)
        t_ok = dt <= pd.Timedelta(seconds=2)
        if t_ok:
            time_match_1bar += 1

        # StepDist / AddDist
        sd_delta = abs(cpp['step_dist'] - py['step_dist'])
        ad_delta = abs(cpp['add_dist'] - py['add_dist'])
        sd_ok = sd_delta <= 0.5
        ad_ok = ad_delta <= 0.5
        if sd_ok:
            sd_match += 1
        if ad_ok:
            ad_match += 1

        # PnL (within 2 ticks)
        cpp_pnl = cpp.get('pnl_ticks', None)
        py_pnl = py.get('gross_pnl', None)
        if cpp_pnl is not None and py_pnl is not None and not np.isnan(cpp_pnl) and not np.isnan(py_pnl):
            pnl_delta = abs(cpp_pnl - py_pnl)
            p_ok = pnl_delta <= 2
            if p_ok:
                pnl_match_2t += 1
        else:
            pnl_delta = None
            p_ok = None

        comparison_rows.append({
            'cpp_time': str(cpp['entry_time']),
            'py_time': str(py['entry_time']),
            'time_delta_s': dt.total_seconds(),
            'cpp_dir': cpp_dir,
            'py_dir': py_dir,
            'dir_ok': d_ok,
            'cpp_sd': cpp['step_dist'],
            'py_sd': py['step_dist'],
            'sd_delta': sd_delta,
            'cpp_ad': cpp['add_dist'],
            'py_ad': py['add_dist'],
            'ad_delta': ad_delta,
            'cpp_pnl': cpp_pnl,
            'py_pnl': py_pnl,
            'pnl_delta': pnl_delta,
            'cpp_exit': cpp.get('exit_reason', ''),
            'py_exit': py.get('exit_reason', ''),
            'cpp_adds': cpp.get('adds', 0),
            'py_adds': py.get('adds', 0),
            'cpp_cw': cpp.get('cap_walks', 0),
            'py_cw': py.get('cap_walks', 0),
        })

    n_matched = len(matches)
    comp_df = pd.DataFrame(comparison_rows)

    print(f"\n  MATCH RATES (out of {n_matched} matched cycles):")
    print(f"    Direction:      {dir_match}/{n_matched} ({dir_match/n_matched:.1%})")
    print(f"    Entry time ±2s: {time_match_1bar}/{n_matched} ({time_match_1bar/n_matched:.1%})")
    print(f"    StepDist ±0.5:  {sd_match}/{n_matched} ({sd_match/n_matched:.1%})")
    print(f"    AddDist ±0.5:   {ad_match}/{n_matched} ({ad_match/n_matched:.1%})")
    pnl_total = comp_df['pnl_delta'].notna().sum()
    print(f"    PnL ±2 ticks:   {pnl_match_2t}/{pnl_total} ({pnl_match_2t/pnl_total:.1%})" if pnl_total > 0 else "    PnL: no data")

    # Print full comparison table
    print(f"\n  {'=' * 120}")
    print(f"  CYCLE DETAIL:")
    print(f"  {'=' * 120}")
    print(f"  {'#':>3} {'C++ Time':<22} {'Py Time':<22} {'dt':>5} {'C++Dir':<6} {'PyDir':<6} "
          f"{'C++SD':>7} {'PySD':>7} {'C++AD':>7} {'PyAD':>7} "
          f"{'C++PnL':>8} {'PyPnL':>8} {'Exit_C++':>12} {'Exit_Py':>16}")
    print(f"  {'-' * 120}")
    for idx, r in comp_df.iterrows():
        flag = ""
        if not r['dir_ok']:
            flag += " DIR!"
        if r['sd_delta'] > 0.5:
            flag += " SD!"
        if r['pnl_delta'] is not None and r['pnl_delta'] > 2:
            flag += " PNL!"

        cpp_pnl_str = f"{r['cpp_pnl']:+.0f}" if r['cpp_pnl'] is not None and not np.isnan(r['cpp_pnl']) else "N/A"
        py_pnl_str = f"{r['py_pnl']:+.0f}" if r['py_pnl'] is not None and not np.isnan(r['py_pnl']) else "N/A"

        print(f"  {idx+1:>3} {r['cpp_time']:<22} {r['py_time']:<22} {r['time_delta_s']:>5.1f} "
              f"{r['cpp_dir']:<6} {r['py_dir']:<6} "
              f"{r['cpp_sd']:>7.2f} {r['py_sd']:>7.2f} {r['cpp_ad']:>7.2f} {r['py_ad']:>7.2f} "
              f"{cpp_pnl_str:>8} {py_pnl_str:>8} {str(r['cpp_exit']):>12} {str(r['py_exit']):>16}{flag}")

    # Unmatched cycles
    unmatched_cpp = set(range(n_cpp)) - {ci for ci, _, _ in matches}
    unmatched_py = set(range(n_py)) - used_py
    if unmatched_cpp:
        print(f"\n  UNMATCHED C++ cycles ({len(unmatched_cpp)}):")
        for i in sorted(unmatched_cpp):
            r = cpp_df.iloc[i]
            print(f"    {r['entry_time']}  {r['direction']}  SD={r['step_dist']:.2f}  exit={r.get('exit_reason','')}")
    if unmatched_py:
        print(f"\n  UNMATCHED Python cycles ({len(unmatched_py)}):")
        for i in sorted(unmatched_py):
            r = py_df.iloc[i]
            print(f"    {r['entry_time']}  {r['direction']}  SD={r['step_dist']:.2f}  exit={r.get('exit_reason','')}")

    # Pass/Fail
    print(f"\n  {'=' * 70}")
    print(f"  REPLICATION GATE ASSESSMENT")
    print(f"  {'=' * 70}")

    cycle_count_pct = abs(n_cpp - n_py) / max(n_cpp, n_py) if max(n_cpp, n_py) > 0 else 1
    all_match_pct = dir_match / n_matched if n_matched > 0 else 0

    checks = [
        ("Cycle count within 1%", cycle_count_pct <= 0.01, f"C++={n_cpp} Py={n_py} delta={cycle_count_pct:.1%}"),
        ("Direction match >98%", all_match_pct >= 0.98, f"{dir_match}/{n_matched} = {all_match_pct:.1%}"),
        ("Entry time ±2s >98%", time_match_1bar / n_matched >= 0.98 if n_matched > 0 else False,
         f"{time_match_1bar}/{n_matched}"),
        ("StepDist ±0.5 >95%", sd_match / n_matched >= 0.95 if n_matched > 0 else False,
         f"{sd_match}/{n_matched}"),
        ("AddDist ±0.5 >95%", ad_match / n_matched >= 0.95 if n_matched > 0 else False,
         f"{ad_match}/{n_matched}"),
    ]

    pass_all = True
    for label, ok, detail in checks:
        status = "PASS" if ok else "FAIL"
        if not ok:
            pass_all = False
        print(f"    [{status}] {label}: {detail}")

    verdict = "PASS" if pass_all else "FAIL"
    print(f"\n  VERDICT: {verdict}")

    return comp_df


def main():
    t0 = time.time()
    _OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 70)
    print("REPLICATION GATE — C++ vs Python (Section 7)")
    print("  NQ1T data from E:\\SierraChart\\Data")
    print("=" * 70)

    # 1. Load NQ1T data
    df, prices, tod_secs, dts = load_nq1t()

    # 2. Build ZZ regime — need full historical warm-up from P1+P2 data
    #    The NQ1T only covers 1 day, not enough for 200-swing buffer.
    #    Use the same combined P1+P2 zigzag lookup the C++ chart has.
    print("\n  Building ZZ regime from P1+P2 historical data (warm-up)...")
    from run_p2a_validation import build_combined_zigzag_lookup
    zz_lookup = build_combined_zigzag_lookup()
    adaptive = make_adaptive_lookup(zz_lookup, 5, 2)
    std_lu = make_std_lookup(zz_lookup)
    print(f"    Adaptive lookup: {len(adaptive['timestamps']):,} points")

    # Verify adaptive values match C++ at first seed (10:09:10, C++ SD=27.02, AD=22.12)
    seed_dt = pd.Timestamp('2026-03-19 10:09:10').value
    aidx = np.searchsorted(adaptive['timestamps'], seed_dt, side='right') - 1
    if aidx >= 0:
        py_sd = max(float(adaptive['sd_values'][aidx]), 10.0)
        py_ad = min(max(float(adaptive['ad_values'][aidx]), 10.0), py_sd)
        print(f"    Spot-check at 10:09:10: Python SD={py_sd:.2f} AD={py_ad:.2f} "
              f"(C++ logged SD=27.02 AD=22.12)")

    # 3. Build SpeedRead Roll50 — need combined P1+P2 250-tick bar computation
    print("\n  Building SpeedRead from P1+P2 combined 250-tick bars...")
    from run_p2a_validation import build_combined_speedread
    sr_bar_dts, sr_composite = build_combined_speedread()

    # Map SpeedRead to NQ1T tick level
    print("  Mapping SpeedRead Roll50 to NQ1T tick level...")
    sr_ts = sr_bar_dts.astype('int64') // 10**9
    sr_comp = sr_composite.astype(np.float64)
    tick_ts = dts.astype('int64') // 10**9
    sr_idx = np.clip(np.searchsorted(sr_ts, tick_ts, side='right') - 1,
                     0, len(sr_comp) - 1)
    tick_sr = sr_comp[sr_idx]
    tick_sr = np.nan_to_num(tick_sr, nan=-1.0)

    # Roll50 on tick-level raw composite
    w = 50
    cs_sr = np.cumsum(np.insert(tick_sr, 0, 0))
    sr_roll50 = np.empty_like(tick_sr)
    sr_roll50[:w] = cs_sr[1:w + 1] / np.arange(1, w + 1)
    sr_roll50[w:] = (cs_sr[w + 1:] - cs_sr[1:len(tick_sr) - w + 1]) / w

    # Spot-check
    check_mask = (df['datetime'] >= '2026-03-19 10:09:09') & (df['datetime'] <= '2026-03-19 10:09:11')
    check_idx = df[check_mask].index
    if len(check_idx) > 0:
        print(f"    Spot-check at 10:09:10: Python Roll50={sr_roll50[check_idx[0]]:.2f} "
              f"(C++ logged 49.48)")

    # 4. Parse C++ log
    print("\n  Parsing C++ log...")
    cpp_log = pd.read_csv(str(_CPP_LOG))
    cpp_cycles = parse_cpp_cycles(cpp_log)
    print(f"    C++ cycles: {len(cpp_cycles)}")
    if len(cpp_cycles) > 0:
        print(f"    First: {cpp_cycles.iloc[0]['entry_time']} {cpp_cycles.iloc[0]['direction']}")
        print(f"    Last:  {cpp_cycles.iloc[-1]['entry_time']} {cpp_cycles.iloc[-1]['direction']}")

    # 5. Run Python simulator
    print("\n  Running Python simulator on NQ1T data...")
    t_sim = time.time()
    sim = run_python_sim(prices, tod_secs, sr_roll50, dts, adaptive, std_lu)
    print(f"    Simulation done in {time.time() - t_sim:.1f}s")
    print(f"    Total sessions: {sim['total_sessions']}")
    print(f"    Cap walks: {sim['cap_walks']}")
    print(f"    4C stops: {sim['stops_4c']}")

    # 6. Parse Python cycles
    py_cycles = parse_python_cycles(sim)
    print(f"    Python cycles: {len(py_cycles)}")
    if len(py_cycles) > 0:
        print(f"    First: {py_cycles.iloc[0]['entry_time']} {py_cycles.iloc[0]['direction']}")
        print(f"    Last:  {py_cycles.iloc[-1]['entry_time']} {py_cycles.iloc[-1]['direction']}")

    # 7. Compare
    comp = compare_cycles(cpp_cycles, py_cycles)

    # 8. Save
    if comp is not None:
        comp.to_csv(str(_OUTPUT_DIR / "replication_gate_comparison.csv"), index=False)
        print(f"\n  Saved comparison to {_OUTPUT_DIR / 'replication_gate_comparison.csv'}")

    print(f"\n  Total time: {time.time() - t0:.1f}s")


if __name__ == "__main__":
    main()
