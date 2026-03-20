# archetype: rotational
"""Replication Gate V2 (Section 7): C++ vs Python cycle-by-cycle comparison.

Data sources (all from E:\SierraChart\Data):
  - C++ log: ATEAM_ROTATION_V14_log.csv
  - 1-tick:  NQ1T.csv (prices + Zig Zag Line Length for ZZ regime)
  - 250-tick: NQ250T.csv (close + volume for SpeedRead computation)

ZZ regime built from NQ1T's Zig Zag Line Length column (1-tick resolution,
HL-based 5.25pt reversal — same data the C++ ZigZagRegime study reads).

SpeedRead computed from NQ250T close/volume (same bar resolution as C++ chart).

Usage:
    python run_replication_gate_v2.py
"""

import sys
import json
import time
from math import tanh
from pathlib import Path

import numpy as np
import pandas as pd

_REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_REPO))
sys.path.insert(0, str(Path(__file__).resolve().parent))

_SC_DATA = Path("E:/SierraChart/Data")
_OUTPUT_DIR = Path(__file__).parent / "phase1_results"

TICK_SIZE = 0.25
COST_TICKS = 1
SEED_DIST = 15.0
SR_THRESHOLD = 48.0
FLATTEN_TOD = 16 * 3600
RESUME_TOD = 18 * 3600
SEED_START_TOD = 10 * 3600
MAX_CAP_WALKS = 2
INIT_QTY = 1


# ---------------------------------------------------------------------------
# 1. Build ZZ regime from NQ1T (1-tick zigzag)
# ---------------------------------------------------------------------------

def build_zz_regime_from_1tick(nq1t_df):
    """Build rolling 200-swing percentile lookup from NQ1T Zig Zag Line Length.

    Returns adaptive_lookup dict compatible with simulate_daily_flatten.
    """
    print("  Building ZZ regime from NQ1T 1-tick Zig Zag Line Length...")
    zz = nq1t_df['Zig Zag Line Length'].values.astype(np.float64)
    dts = nq1t_df['datetime'].values

    # Detect swing completions (value changes between non-zero entries)
    window = 200
    min_warmup = 20
    buf = []
    last_val = 0.0

    pct_ts = []
    p90_vals = []
    p75_vals = []
    std_vals = []

    for i in range(len(zz)):
        v = zz[i]
        if v != 0 and v != last_val:
            # New completed swing
            buf.append(abs(v))
            if len(buf) > window:
                buf.pop(0)

            if len(buf) >= min_warmup:
                s = sorted(buf)
                n = len(s)

                def pct(p):
                    idx = (p / 100.0) * (n - 1)
                    lo = int(idx)
                    frac = idx - lo
                    if lo + 1 < n:
                        return s[lo] + frac * (s[lo + 1] - s[lo])
                    return s[lo]

                pct_ts.append(dts[i].astype('int64'))
                p90_vals.append(pct(90))
                p75_vals.append(pct(75))
                std_vals.append(float(np.std(buf)))

        if v != 0:
            last_val = v

    print(f"    Swings in buffer: {len(buf)}, Percentile points: {len(pct_ts)}")

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


# ---------------------------------------------------------------------------
# 2. SpeedRead from NQ250T
# ---------------------------------------------------------------------------

def build_speedread_from_250tick(nq250t_df):
    """Compute SpeedRead composite and Roll50 from NQ250T close/volume.

    Returns (bar_datetimes, roll50_values) for mapping to tick level.
    """
    print("  Computing SpeedRead from NQ250T...")
    close = nq250t_df['Last'].values.astype(np.float64)
    volume = nq250t_df['Volume'].values.astype(np.float64)
    bar_dts = nq250t_df['datetime'].values
    n = len(close)

    lookback = 10
    vol_avg_len = 50
    median_window = 200

    # Price travel
    price_travel = np.full(n, np.nan)
    for i in range(lookback, n):
        travel = 0.0
        for j in range(lookback):
            travel += abs(close[i - j] - close[i - j - 1])
        price_travel[i] = travel

    # Median normalization
    pt = pd.Series(price_travel)
    median_pt = pt.rolling(median_window, min_periods=median_window).median().values

    price_scaled = np.full(n, np.nan)
    for i in range(n):
        if not np.isnan(price_travel[i]) and not np.isnan(median_pt[i]) and median_pt[i] > 0:
            vel = price_travel[i] / median_pt[i]
            price_scaled[i] = 50.0 * (1.0 + tanh((vel - 1.0) * 1.5))

    # Volume rate
    vol_scaled = np.full(n, np.nan)
    for i in range(vol_avg_len + 1, n):
        avg_vol = np.mean(volume[i - vol_avg_len:i])
        if avg_vol > 0:
            recent_bars = min(lookback, 5)
            recent_vol = np.mean(volume[max(0, i - recent_bars + 1):i + 1])
            rate = recent_vol / avg_vol
            vol_scaled[i] = 50.0 * (1.0 + tanh((rate - 1.0) * 1.5))

    # Raw composite
    composite_raw = np.full(n, np.nan)
    for i in range(n):
        if not np.isnan(price_scaled[i]) and not np.isnan(vol_scaled[i]):
            composite_raw[i] = (price_scaled[i] + vol_scaled[i]) / 2.0

    # Roll50 of raw composite
    raw_filled = np.where(np.isnan(composite_raw), 0.0, composite_raw)
    cs = np.cumsum(np.insert(raw_filled, 0, 0))
    w = 50
    roll50 = np.empty(n)
    roll50[:w] = cs[1:w + 1] / np.arange(1, w + 1)
    roll50[w:] = (cs[w + 1:] - cs[1:n - w + 1]) / w

    print(f"    {n} bars, Roll50 range: [{roll50[w:].min():.1f}, {roll50[w:].max():.1f}]")
    return bar_dts, roll50


# ---------------------------------------------------------------------------
# 3. Map SpeedRead to tick level
# ---------------------------------------------------------------------------

def map_roll50_to_ticks(bar_dts, roll50, tick_dts):
    """Map 250-tick bar Roll50 to 1-tick level via timestamp lookup."""
    bar_ts = bar_dts.astype('int64') // 10**9
    tick_ts = tick_dts.astype('int64') // 10**9
    idx = np.clip(np.searchsorted(bar_ts, tick_ts, side='right') - 1,
                  0, len(roll50) - 1)
    return roll50[idx]


# ---------------------------------------------------------------------------
# 4. Parse C++ log into cycles
# ---------------------------------------------------------------------------

def parse_cpp_cycles(log_path):
    """Parse ATEAM_ROTATION_V14_log.csv into cycle records."""
    df = pd.read_csv(str(log_path))
    df.columns = [c.strip() for c in df.columns]
    key = df[~df['Event'].isin(['SR_BLOCK_SEED', 'WATCH_SET'])].copy()
    key['DateTime'] = pd.to_datetime(key['DateTime'])

    cycles = []
    cur = None

    for _, row in key.iterrows():
        evt = row['Event']

        if evt in ('SEED_ENTRY', 'REVERSAL_ENTRY'):
            if cur is not None and cur.get('exit_time') is None:
                cur['exit_time'] = row['DateTime']
                cur['exit_reason'] = 'implied'
                cycles.append(cur)
            cur = {
                'entry_time': row['DateTime'],
                'entry_type': evt.replace('_ENTRY', ''),
                'direction': row['Side'],
                'entry_price': row['Price'],
                'step_dist': row['CycleStepDist'],
                'add_dist': row['CycleAddDist'],
                'roll50_sr': row['Roll50SR'],
                'adds': 0, 'cap_walks': 0,
                'exit_time': None, 'exit_price': None,
                'exit_reason': None, 'pnl_ticks': None,
            }
        elif evt == 'ADD' and cur:
            cur['adds'] += 1
        elif evt == 'CAP_WALK' and cur:
            cur['cap_walks'] += 1
        elif evt == 'REVERSAL_TRIGGER' and cur:
            cur['exit_time'] = row['DateTime']
            cur['exit_price'] = row['Price']
            cur['exit_reason'] = 'reversal'
            cur['pnl_ticks'] = row['PnlTicks']
            cycles.append(cur)
            cur = None
        elif evt == 'CAPWALK_STOP' and cur:
            cur['exit_time'] = row['DateTime']
            cur['exit_price'] = row['Price']
            cur['exit_reason'] = 'stop_4c'
            cur['pnl_ticks'] = row['PnlTicks']
            cycles.append(cur)
            cur = None
        elif evt == 'SR_BLOCK_REVERSAL' and cur:
            cur['exit_time'] = row['DateTime']
            cur['exit_price'] = row['Price']
            cur['exit_reason'] = 'sr_block'
            cycles.append(cur)
            cur = None
        elif evt == 'DAILY_FLATTEN' and cur:
            cur['exit_time'] = row['DateTime']
            cur['exit_price'] = row['Price']
            cur['exit_reason'] = 'daily_flatten'
            cycles.append(cur)
            cur = None

    if cur:
        cur['exit_reason'] = 'end_of_data'
        cycles.append(cur)

    return pd.DataFrame(cycles)


# ---------------------------------------------------------------------------
# 5. Run Python simulator
# ---------------------------------------------------------------------------

def run_python_sim(prices, tod_secs, sr_roll50, dts, adaptive, std_lu):
    from run_seed_investigation import simulate_daily_flatten
    return simulate_daily_flatten(
        prices, tod_secs, sr_roll50, dts,
        seed_dist=SEED_DIST, step_dist=25.0, add_dist=25.0,
        flatten_reseed_cap=2, max_levels=1,
        seed_sr_thresh=SR_THRESHOLD, rev_sr_thresh=SR_THRESHOLD,
        watch_mode='rth_open', cap_action='walk',
        seed_start_tod=SEED_START_TOD,
        adaptive_lookup=adaptive,
        max_adverse_sigma=None,
        max_cap_walks=MAX_CAP_WALKS,
        std_lookup=std_lu,
    )


def parse_python_cycles(sim):
    """Extract cycles from Python simulation."""
    trades = pd.DataFrame(sim['trade_records'])
    cycles_raw = pd.DataFrame(sim['cycle_records'])
    if len(cycles_raw) == 0:
        return pd.DataFrame()

    entry_trades = trades[trades['action'].isin(['SEED', 'REVERSAL'])]
    ce = entry_trades.groupby('cycle_id').first().reset_index()

    py = []
    for _, cr in cycles_raw.iterrows():
        entry = ce[ce['cycle_id'] == cr['cycle_id']]
        if len(entry) == 0:
            continue
        e = entry.iloc[0]
        py.append({
            'entry_time': pd.to_datetime(e['datetime']),
            'entry_type': e['action'],
            'direction': e['direction'],
            'entry_price': e['price'],
            'step_dist': cr.get('stepdist_used', 0),
            'add_dist': cr.get('adddist_used', 0),
            'adds': cr.get('adds_count', 0),
            'cap_walks': cr.get('cycle_cap_walks', 0),
            'exit_reason': cr['exit_reason'],
            'gross_pnl': cr['gross_pnl_ticks'],
        })
    return pd.DataFrame(py)


# ---------------------------------------------------------------------------
# 6. Compare
# ---------------------------------------------------------------------------

def compare(cpp_df, py_df):
    n_cpp, n_py = len(cpp_df), len(py_df)
    print(f"\n{'=' * 100}")
    print(f"CYCLE-BY-CYCLE COMPARISON (Section 7)")
    print(f"{'=' * 100}")
    print(f"  C++ cycles: {n_cpp}")
    print(f"  Python cycles: {n_py}")

    if n_cpp == 0 or n_py == 0:
        print("  ERROR: No cycles!")
        return

    # Match by entry time (±5s)
    matches = []
    used_py = set()
    for i, cpp in cpp_df.iterrows():
        best_j, best_dt = None, pd.Timedelta(seconds=999)
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

    n_m = len(matches)
    print(f"  Matched (±5s): {n_m} / {n_cpp}")

    # Score each criterion
    dir_ok = time_ok = sd_ok = ad_ok = pnl_ok = exit_ok = 0
    pnl_total = 0

    print(f"\n  {'#':>3} {'C++Time':<20} {'PyTime':<20} {'dt':>4} {'Dir':>5} "
          f"{'SD_C':>7} {'SD_P':>7} {'AD_C':>7} {'AD_P':>7} "
          f"{'PnL_C':>7} {'PnL_P':>7} {'ExC':>10} {'ExP':>16} {'Flags'}")
    print(f"  {'-' * 140}")

    for idx, (ci, pi, dt) in enumerate(matches):
        c, p = cpp_df.loc[ci], py_df.loc[pi]
        flags = []

        # Direction
        cd = c['direction'].upper().strip()
        pd_dir = p['direction'].upper().strip()
        d = cd == pd_dir
        if d: dir_ok += 1
        else: flags.append("DIR")

        # Time (±2s for 1-tick)
        t = dt <= pd.Timedelta(seconds=2)
        if t: time_ok += 1
        else: flags.append("TIME")

        # StepDist (±1.0 pt)
        sd_d = abs(c['step_dist'] - p['step_dist'])
        if sd_d <= 1.0: sd_ok += 1
        else: flags.append(f"SD({sd_d:+.1f})")

        # AddDist (±1.0 pt)
        ad_d = abs(c['add_dist'] - p['add_dist'])
        if ad_d <= 1.0: ad_ok += 1
        else: flags.append(f"AD({ad_d:+.1f})")

        # PnL (±2 ticks)
        cpnl = c.get('pnl_ticks')
        ppnl = p.get('gross_pnl')
        if cpnl is not None and ppnl is not None and not np.isnan(cpnl) and not np.isnan(ppnl):
            pnl_total += 1
            if abs(cpnl - ppnl) <= 2:
                pnl_ok += 1
            else:
                flags.append(f"PNL({cpnl:+.0f}v{ppnl:+.0f})")
        else:
            flags.append("PNL?")

        # Exit type
        ce_reason = str(c.get('exit_reason', '')).replace('_', '')
        pe_reason = str(p.get('exit_reason', '')).replace('_', '')
        if ce_reason == pe_reason or (ce_reason.startswith('rev') and pe_reason.startswith('rev')):
            exit_ok += 1

        cpnl_s = f"{cpnl:+.0f}" if cpnl is not None and not np.isnan(cpnl) else "N/A"
        ppnl_s = f"{ppnl:+.0f}" if ppnl is not None and not np.isnan(ppnl) else "N/A"
        flag_str = " ".join(flags) if flags else "OK"

        print(f"  {idx+1:>3} {str(c['entry_time']):<20} {str(p['entry_time']):<20} "
              f"{dt.total_seconds():>4.1f} {cd+'/'+pd_dir:>5} "
              f"{c['step_dist']:>7.2f} {p['step_dist']:>7.2f} "
              f"{c['add_dist']:>7.2f} {p['add_dist']:>7.2f} "
              f"{cpnl_s:>7} {ppnl_s:>7} "
              f"{str(c.get('exit_reason','')):>10} {str(p.get('exit_reason','')):>16} {flag_str}")

    # Unmatched
    unmatched_cpp = set(range(n_cpp)) - {ci for ci, _, _ in matches}
    unmatched_py = set(range(n_py)) - used_py
    if unmatched_cpp:
        print(f"\n  UNMATCHED C++ ({len(unmatched_cpp)}):")
        for i in sorted(unmatched_cpp):
            r = cpp_df.iloc[i]
            print(f"    {r['entry_time']}  {r['direction']:<6} SD={r['step_dist']:.2f} AD={r['add_dist']:.2f} exit={r.get('exit_reason','')}")
    if unmatched_py:
        print(f"\n  UNMATCHED Python ({len(unmatched_py)}):")
        for i in sorted(unmatched_py):
            r = py_df.iloc[i]
            print(f"    {r['entry_time']}  {r['direction']:<6} SD={r['step_dist']:.2f} AD={r['add_dist']:.2f} exit={r.get('exit_reason','')}")

    # Assessment
    print(f"\n{'=' * 100}")
    print(f"REPLICATION GATE ASSESSMENT (Section 7)")
    print(f"{'=' * 100}")

    cycle_pct = 1 - abs(n_cpp - n_py) / max(n_cpp, n_py)
    checks = [
        ("Cycle count ±1%", abs(n_cpp - n_py) / max(n_cpp, n_py) <= 0.01,
         f"C++={n_cpp} Py={n_py} ({cycle_pct:.1%})"),
        ("Direction >98%", dir_ok / n_m >= 0.98 if n_m else False,
         f"{dir_ok}/{n_m} = {dir_ok/n_m:.1%}" if n_m else "N/A"),
        ("Entry time ±2s >98%", time_ok / n_m >= 0.98 if n_m else False,
         f"{time_ok}/{n_m} = {time_ok/n_m:.1%}" if n_m else "N/A"),
        ("StepDist ±1.0 >95%", sd_ok / n_m >= 0.95 if n_m else False,
         f"{sd_ok}/{n_m} = {sd_ok/n_m:.1%}" if n_m else "N/A"),
        ("AddDist ±1.0 >95%", ad_ok / n_m >= 0.95 if n_m else False,
         f"{ad_ok}/{n_m} = {ad_ok/n_m:.1%}" if n_m else "N/A"),
        ("PnL ±2 ticks >98%", pnl_ok / pnl_total >= 0.98 if pnl_total else False,
         f"{pnl_ok}/{pnl_total} = {pnl_ok/pnl_total:.1%}" if pnl_total else "N/A"),
        ("Exit type >95%", exit_ok / n_m >= 0.95 if n_m else False,
         f"{exit_ok}/{n_m} = {exit_ok/n_m:.1%}" if n_m else "N/A"),
    ]

    all_pass = True
    for label, ok, detail in checks:
        s = "PASS" if ok else "FAIL"
        if not ok:
            all_pass = False
        print(f"  [{s}] {label}: {detail}")

    print(f"\n  VERDICT: {'PASS' if all_pass else 'FAIL'}")
    return matches


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    t0 = time.time()
    _OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 100)
    print("REPLICATION GATE V2 — C++ vs Python (Section 7)")
    print("  ZZ regime from NQ1T (1-tick zigzag)")
    print("  SpeedRead from NQ250T (250-tick bars)")
    print("=" * 100)

    # Load NQ1T
    print("\n  Loading NQ1T.csv...")
    nq1t = pd.read_csv(str(_SC_DATA / "NQ1T.csv"))
    nq1t.columns = [c.strip() for c in nq1t.columns]
    nq1t['datetime'] = pd.to_datetime(nq1t['Date'] + ' ' + nq1t['Time'])
    print(f"    {len(nq1t):,} ticks: {nq1t['datetime'].iloc[0]} to {nq1t['datetime'].iloc[-1]}")

    prices = nq1t['Last'].values.astype(np.float64)
    dts = nq1t['datetime'].values
    hours = nq1t['datetime'].dt.hour.values.astype(np.int32)
    minutes = nq1t['datetime'].dt.minute.values.astype(np.int32)
    seconds = nq1t['datetime'].dt.second.values.astype(np.int32)
    tod_secs = hours * 3600 + minutes * 60 + seconds

    # Build ZZ regime from NQ1T 1-tick zigzag
    adaptive, std_lu = build_zz_regime_from_1tick(nq1t)

    # Validate ZZ against C++ log
    cpp_log = pd.read_csv(str(_SC_DATA / "ATEAM_ROTATION_V14_log.csv"))
    cpp_log.columns = [c.strip() for c in cpp_log.columns]
    cpp_entries = cpp_log[cpp_log['Event'].isin(['SEED_ENTRY', 'REVERSAL_ENTRY'])]
    print(f"\n  ZZ regime spot-checks vs C++ log:")
    for _, row in cpp_entries.head(5).iterrows():
        ts = pd.Timestamp(row['DateTime']).value
        aidx = np.searchsorted(adaptive['timestamps'], ts, side='right') - 1
        if aidx >= 0:
            py_sd = max(float(adaptive['sd_values'][aidx]), 10.0)
            py_ad = max(float(adaptive['ad_values'][aidx]), 10.0)
            py_ad = min(py_ad, py_sd)
            print(f"    {row['DateTime']}: C++ SD={row['CycleStepDist']:.2f} Py SD={py_sd:.2f} "
                  f"(d={py_sd - row['CycleStepDist']:+.2f})  "
                  f"C++ AD={row['CycleAddDist']:.2f} Py AD={py_ad:.2f} "
                  f"(d={py_ad - row['CycleAddDist']:+.2f})")

    # Load NQ250T and build SpeedRead
    print("\n  Loading NQ250T.csv...")
    nq250t = pd.read_csv(str(_SC_DATA / "NQ250T.csv"))
    nq250t.columns = [c.strip() for c in nq250t.columns]
    nq250t['datetime'] = pd.to_datetime(nq250t['Date'] + ' ' + nq250t['Time'])
    print(f"    {len(nq250t):,} bars")

    bar_dts, roll50_bars = build_speedread_from_250tick(nq250t)

    # Map Roll50 to tick level
    sr_roll50 = map_roll50_to_ticks(bar_dts, roll50_bars, dts)
    print(f"  Roll50 mapped to {len(sr_roll50):,} ticks")

    # Validate SpeedRead vs C++
    print(f"\n  SpeedRead spot-checks vs C++ log:")
    for _, row in cpp_entries.head(5).iterrows():
        ts = pd.Timestamp(row['DateTime'])
        mask = (nq1t['datetime'] >= ts - pd.Timedelta(seconds=1)) & (nq1t['datetime'] <= ts + pd.Timedelta(seconds=1))
        idx = nq1t[mask].index
        if len(idx) > 0:
            print(f"    {row['DateTime']}: C++ Roll50={row['Roll50SR']:.2f}  Py Roll50={sr_roll50[idx[0]]:.2f} "
                  f"(d={sr_roll50[idx[0]] - row['Roll50SR']:+.2f})")

    # Parse C++ cycles
    print(f"\n  Parsing C++ log...")
    cpp_cycles = parse_cpp_cycles(_SC_DATA / "ATEAM_ROTATION_V14_log.csv")
    print(f"    {len(cpp_cycles)} cycles")

    # Run Python sim
    print(f"\n  Running Python simulator...")
    t_sim = time.time()
    sim = run_python_sim(prices, tod_secs, sr_roll50, dts, adaptive, std_lu)
    print(f"    Done in {time.time() - t_sim:.1f}s")
    print(f"    Sessions: {sim['total_sessions']}, Cap walks: {sim['cap_walks']}, "
          f"4C stops: {sim['stops_4c']}")

    py_cycles = parse_python_cycles(sim)
    print(f"    {len(py_cycles)} cycles")

    # Compare
    compare(cpp_cycles, py_cycles)

    print(f"\n  Total time: {time.time() - t0:.1f}s")


if __name__ == "__main__":
    main()
