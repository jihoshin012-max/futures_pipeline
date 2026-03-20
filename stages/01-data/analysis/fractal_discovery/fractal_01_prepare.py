#!/usr/bin/env python3
"""
fractal_01_prepare.py — Load NQ 1T data and compute zig-zag swings at all thresholds.
Saves intermediate results for fractal_02_analyze.py.
"""
import numpy as np
import pandas as pd
import numba as nb
from pathlib import Path
import pickle
import time

# === CONFIG ===
DATA_DIR = Path(r"C:\Projects\pipeline\stages\01-data\data\bar_data\tick")
OUT_DIR = Path(r"C:\Projects\pipeline\stages\01-data\analysis\fractal_discovery")
OUT_DIR.mkdir(parents=True, exist_ok=True)

FILES = [
    DATA_DIR / "NQ_BarData_1tick_rot_P1.csv",
    DATA_DIR / "NQ_BarData_1tick_rot_P2.csv",
]
THRESHOLDS = [3, 5, 7, 10, 15, 25, 50]
SPLITS = ['RTH', 'ETH', 'Combined']

RTH_START = 9 * 3600 + 30 * 60    # 09:30 = 34200s
RTH_END   = 16 * 3600 + 15 * 60   # 16:15 = 58500s
ETH_EVENING = 18 * 3600           # 18:00 = 64800s


# === NUMBA HELPERS ===

@nb.njit(cache=True)
def next_day(yyyymmdd):
    """Next calendar day from YYYYMMDD integer."""
    y = yyyymmdd // 10000
    m = (yyyymmdd // 100) % 100
    d = yyyymmdd % 100
    days_in = np.array([0, 31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31])
    dim = days_in[m]
    if m == 2 and (y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)):
        dim = 29
    d += 1
    if d > dim:
        d = 1
        m += 1
        if m > 12:
            m = 1
            y += 1
    return y * 10000 + m * 100 + d


@nb.njit(cache=True)
def compute_trading_dates(cal_dates, time_secs):
    """Evening (>=18:00) belongs to next day's trading session."""
    n = len(cal_dates)
    td = np.empty(n, dtype=np.int32)
    for i in range(n):
        if time_secs[i] >= 64800.0:
            td[i] = next_day(cal_dates[i])
        else:
            td[i] = cal_dates[i]
    return td


@nb.njit(cache=True)
def assign_session_ids(keys):
    """Incrementing session ID when key value changes."""
    n = len(keys)
    sids = np.empty(n, dtype=np.int32)
    sid = 0
    sids[0] = sid
    for i in range(1, n):
        if keys[i] != keys[i - 1]:
            sid += 1
        sids[i] = sid
    return sids


@nb.njit(cache=True)
def zigzag(prices, session_ids, threshold):
    """Zig-zag swing detection with session boundary resets.

    Returns (swing_idx, swing_price, swing_dir, swing_sid).
    swing_dir: +1 = confirmed high, -1 = confirmed low.
    """
    n = len(prices)
    max_out = 5_000_000
    out_idx   = np.empty(max_out, dtype=np.int64)
    out_price = np.empty(max_out, dtype=np.float64)
    out_dir   = np.empty(max_out, dtype=np.int8)
    out_sid   = np.empty(max_out, dtype=np.int32)
    cnt = 0

    INIT, UP, DOWN = 0, 1, -1
    state = INIT
    ep = 0.0; ei = np.int64(0)
    sh = 0.0; sl = 0.0
    hi_i = np.int64(0); lo_i = np.int64(0)
    cs = np.int32(-999)

    for i in range(n):
        p = prices[i]
        s = session_ids[i]

        if s != cs:
            cs = s
            state = INIT
            sh = p; sl = p
            hi_i = np.int64(i); lo_i = np.int64(i)
            continue

        if state == INIT:
            if p > sh:
                sh = p; hi_i = np.int64(i)
            if p < sl:
                sl = p; lo_i = np.int64(i)
            if sh - sl >= threshold:
                if cnt >= max_out:
                    break
                if hi_i > lo_i:
                    out_idx[cnt] = lo_i; out_price[cnt] = sl
                    out_dir[cnt] = np.int8(-1); out_sid[cnt] = cs
                    cnt += 1
                    state = UP; ep = sh; ei = hi_i
                else:
                    out_idx[cnt] = hi_i; out_price[cnt] = sh
                    out_dir[cnt] = np.int8(1); out_sid[cnt] = cs
                    cnt += 1
                    state = DOWN; ep = sl; ei = lo_i

        elif state == UP:
            if p > ep:
                ep = p; ei = np.int64(i)
            elif ep - p >= threshold:
                if cnt >= max_out:
                    break
                out_idx[cnt] = ei; out_price[cnt] = ep
                out_dir[cnt] = np.int8(1); out_sid[cnt] = cs
                cnt += 1
                state = DOWN; ep = p; ei = np.int64(i)

        else:  # DOWN
            if p < ep:
                ep = p; ei = np.int64(i)
            elif p - ep >= threshold:
                if cnt >= max_out:
                    break
                out_idx[cnt] = ei; out_price[cnt] = ep
                out_dir[cnt] = np.int8(-1); out_sid[cnt] = cs
                cnt += 1
                state = UP; ep = p; ei = np.int64(i)

    return out_idx[:cnt], out_price[:cnt], out_dir[:cnt], out_sid[:cnt]


# === DATA LOADING ===

def load_raw_data():
    """Load P1+P2 CSVs, return (prices, time_secs, cal_dates) as numpy arrays."""
    frames = []
    for f in FILES:
        print(f"  Loading {f.name}...", flush=True)
        df = pd.read_csv(
            f, usecols=[0, 1, 5], skipinitialspace=True,
            header=0, dtype={' Last': np.float32, 'Last': np.float32},
            low_memory=False,
        )
        # Normalise column names (some have leading spaces)
        df.columns = ['date', 'time', 'price']
        frames.append(df)

    df = pd.concat(frames, ignore_index=True)
    del frames
    print(f"  Total rows: {len(df):,}", flush=True)

    # Parse time → seconds since midnight
    print("  Parsing time...", flush=True)
    t = df['time'].str.strip()
    parts = t.str.split(':', n=2, expand=True)
    time_secs = (parts[0].astype(np.int32) * 3600 +
                 parts[1].astype(np.int32) * 60 +
                 parts[2].astype(np.float64)).values.astype(np.float32)
    del parts, t

    # Parse date → YYYYMMDD integer
    print("  Parsing date...", flush=True)
    d = df['date'].str.strip()
    dparts = d.str.split('-', n=2, expand=True)
    cal_dates = (dparts[0].astype(np.int32) * 10000 +
                 dparts[1].astype(np.int32) * 100 +
                 dparts[2].astype(np.int32)).values.astype(np.int32)
    del dparts, d

    prices = df['price'].values.astype(np.float32)
    del df
    return prices, time_secs, cal_dates


# === MAIN ===

def main():
    t0 = time.time()

    print("=== PHASE 1: Load Data ===", flush=True)
    prices, time_secs, cal_dates = load_raw_data()
    print(f"  Loaded in {time.time()-t0:.1f}s", flush=True)

    print("\n=== PHASE 2: Compute Trading Dates ===", flush=True)
    t1 = time.time()
    # Warm up numba JIT
    _ = next_day(np.int32(20250101))
    _ = compute_trading_dates(
        np.array([20250101], dtype=np.int32),
        np.array([70000.0], dtype=np.float32),
    )
    _ = assign_session_ids(np.array([1, 1, 2], dtype=np.int32))
    # Warm up zigzag
    _p = np.array([100.0, 103.0, 100.0, 104.0], dtype=np.float32)
    _s = np.array([0, 0, 0, 0], dtype=np.int32)
    _ = zigzag(_p, _s, 3.0)
    del _p, _s

    trading_dates = compute_trading_dates(cal_dates, time_secs)
    print(f"  Done in {time.time()-t1:.1f}s", flush=True)

    print("\n=== PHASE 3: Run Zig-Zags ===", flush=True)
    results = {}

    for split in SPLITS:
        t2 = time.time()
        print(f"\n  --- {split} ---", flush=True)

        if split == 'RTH':
            mask = (time_secs >= RTH_START) & (time_secs < RTH_END)
        elif split == 'ETH':
            mask = (time_secs >= ETH_EVENING) | (time_secs < RTH_START)
        else:
            mask = np.ones(len(prices), dtype=np.bool_)

        p  = prices[mask].copy()
        ts = time_secs[mask].copy()
        td = trading_dates[mask].copy()
        sids = assign_session_ids(td)

        print(f"    Rows: {len(p):,}", flush=True)

        for thresh in THRESHOLDS:
            t3 = time.time()
            sw_idx, sw_price, sw_dir, sw_sid = zigzag(p, sids, float(thresh))
            sw_ts = ts[sw_idx]

            results[(split, thresh)] = {
                'price':     sw_price.astype(np.float64),
                'dir':       sw_dir,
                'sid':       sw_sid,
                'time_secs': sw_ts.astype(np.float32),
                'orig_idx':  sw_idx,
            }
            dt = time.time() - t3
            print(f"    Threshold {thresh:2d}: {len(sw_price):>8,} swings  ({dt:.2f}s)", flush=True)

        print(f"  {split} total: {time.time()-t2:.1f}s", flush=True)
        del p, ts, td, sids

    # Save
    print("\n=== PHASE 4: Save Results ===", flush=True)
    outfile = OUT_DIR / 'zigzag_results.pkl'
    with open(outfile, 'wb') as f:
        pickle.dump(results, f, protocol=pickle.HIGHEST_PROTOCOL)

    # Print summary
    print(f"\n  Saved to {outfile}")
    for split in SPLITS:
        for thresh in THRESHOLDS:
            n = len(results[(split, thresh)]['price'])
            print(f"    {split:>8s} / {thresh:2d}pt: {n:>8,} swings")

    print(f"\n  Total time: {time.time()-t0:.1f}s", flush=True)


if __name__ == '__main__':
    main()
