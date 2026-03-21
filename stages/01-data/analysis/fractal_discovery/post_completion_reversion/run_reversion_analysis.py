#!/usr/bin/env python3
"""Post-completion reversion depth analysis.

Measures how far price reverses AFTER a parent-scale move completes its threshold.
Uses child-walk decomposition on P1 1-tick RTH data.

Parent thresholds: 25pt (child 10pt) and 40pt (child 16pt).
"""
import numpy as np
import numba as nb
import pandas as pd
from pathlib import Path
import sys
import time

_FRACTAL_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_FRACTAL_DIR))
from fractal_01_prepare import zigzag, compute_trading_dates, assign_session_ids

DATA_DIR = Path(r"C:\Projects\pipeline\stages\01-data\data\bar_data\tick")
P1_PATH = DATA_DIR / "NQ_BarData_1tick_rot_P1.csv"
OUT_DIR = Path(__file__).resolve().parent
OUT_DIR.mkdir(parents=True, exist_ok=True)

RTH_START = 9 * 3600 + 30 * 60
RTH_END = 16 * 3600 + 15 * 60

CONFIGS = [
    {"parent": 40, "child": 16},
    {"parent": 25, "child": 10},
]


def load_p1_rth():
    print(f"Loading P1 1-tick data from: {P1_PATH}")
    df = pd.read_csv(P1_PATH, usecols=[0, 1, 5], skipinitialspace=True,
                     header=0, low_memory=False)
    df.columns = ['date', 'time', 'price']
    t = df['time'].str.strip()
    parts = t.str.split(':', n=2, expand=True)
    time_secs = (parts[0].astype(np.int32) * 3600 +
                 parts[1].astype(np.int32) * 60 +
                 parts[2].astype(np.float64)).values.astype(np.float32)
    d = df['date'].str.strip()
    dparts = d.str.split('-', n=2, expand=True)
    cal_dates = (dparts[0].astype(np.int32) * 10000 +
                 dparts[1].astype(np.int32) * 100 +
                 dparts[2].astype(np.int32)).values.astype(np.int32)
    prices = df['price'].values.astype(np.float32)
    mask = (time_secs >= RTH_START) & (time_secs < RTH_END)
    prices = prices[mask].copy()
    time_secs = time_secs[mask].copy()
    cal_dates = cal_dates[mask].copy()
    print(f"  RTH rows: {len(prices):,}")
    return prices, time_secs, cal_dates


@nb.njit(cache=True)
def measure_post_completion_reversion(
    c_prices, c_dirs, c_sids, c_ts, parent_thresh,
    raw_prices, raw_sids, raw_ts,
):
    """For each child-walk that reaches +parent_thresh (completion),
    measure the max reversion from the completion point.

    Returns per-completion arrays:
      max_reversion_pts: max adverse move from completion point
      bars_to_max_rev: bars from completion to max reversion
      bars_to_recovery: bars from completion to price returning to completion level (0 = never)
      full_recovery: True if price returned to completion level before session end
      continued_reversal: True if price reversed >= parent_thresh from completion
      completion_price: price at completion
      completion_ts: timestamp at completion
    """
    n_c = len(c_prices)
    n_raw = len(raw_prices)
    mx = n_c // 2 + 1

    o_max_rev    = np.empty(mx, dtype=np.float64)
    o_bars_max   = np.empty(mx, dtype=np.int64)
    o_bars_recov = np.empty(mx, dtype=np.int64)
    o_recovered  = np.empty(mx, dtype=nb.boolean)
    o_continued  = np.empty(mx, dtype=nb.boolean)
    o_comp_price = np.empty(mx, dtype=np.float64)
    o_comp_ts    = np.empty(mx, dtype=np.float32)
    cnt = 0

    i = 0
    while i < n_c - 1:
        cs = c_sids[i]
        anch_p = c_prices[i]

        i += 1
        if c_sids[i] != cs:
            continue

        disp = c_prices[i] - anch_p
        if disp == 0.0:
            continue

        att = np.int8(1) if disp > 0 else np.int8(-1)

        # Walk until completion or failure
        if abs(disp) >= parent_thresh:
            # Immediate completion
            comp_price = c_prices[i]
            comp_ts = c_ts[i]
            # Find this point in raw data to measure reversion
            # Use the child swing's orig_idx... we don't have it here.
            # Instead, approximate: completion happens at child swing i.
            # We'll measure reversion using remaining child swings.
            pass
        else:
            # Walk child swings to resolution
            comp_price = 0.0
            comp_ts = np.float32(0.0)
            found_completion = False

            while True:
                i += 1
                if i >= n_c or c_sids[i] != cs:
                    break
                fav = (c_prices[i] - anch_p) * att
                if fav >= parent_thresh:
                    comp_price = c_prices[i]
                    comp_ts = c_ts[i]
                    found_completion = True
                    break
                elif fav <= -parent_thresh:
                    break  # Failure, no completion

            if not found_completion:
                continue

        if comp_price == 0.0:
            # Immediate completion case
            comp_price = c_prices[i]
            comp_ts = c_ts[i]

        # Now measure reversion from comp_price using remaining child swings
        max_rev = 0.0
        bars_to_max = np.int64(0)
        bars_to_recov = np.int64(0)
        recovered = False
        continued_rev = False
        comp_bar = i  # child swing index at completion

        j = i + 1
        bar_count = 0
        while j < n_c and c_sids[j] == cs:
            bar_count += 1
            # Reversion = movement AGAINST original direction from completion
            rev = (comp_price - c_prices[j]) * att  # positive = reversion
            if rev > max_rev:
                max_rev = rev
                bars_to_max = np.int64(bar_count)

            # Check if price returned to completion level
            if not recovered:
                # Recovery = price back at or beyond completion in original direction
                resume = (c_prices[j] - comp_price) * att
                if resume >= 0 and bar_count > 1:
                    recovered = True
                    bars_to_recov = np.int64(bar_count)

            # Check if reversion became a new parent move
            if rev >= parent_thresh:
                continued_rev = True

            j += 1

        o_max_rev[cnt] = max_rev
        o_bars_max[cnt] = bars_to_max
        o_bars_recov[cnt] = bars_to_recov if recovered else np.int64(0)
        o_recovered[cnt] = recovered
        o_continued[cnt] = continued_rev
        o_comp_price[cnt] = comp_price
        o_comp_ts[cnt] = comp_ts
        cnt += 1

    return (o_max_rev[:cnt], o_bars_max[:cnt], o_bars_recov[:cnt],
            o_recovered[:cnt], o_continued[:cnt],
            o_comp_price[:cnt], o_comp_ts[:cnt])


def analyze_reversion(max_rev, bars_max, bars_recov, recovered, continued, parent_thresh):
    n = len(max_rev)
    if n == 0:
        return {}

    thresholds = [8, 12, 16, 20, 24]
    result = {
        "parent_thresh": parent_thresh,
        "sample_count": n,
        "median_reversion_pts": round(float(np.median(max_rev)), 2),
        "p25_reversion": round(float(np.percentile(max_rev, 25)), 2),
        "p75_reversion": round(float(np.percentile(max_rev, 75)), 2),
        "p90_reversion": round(float(np.percentile(max_rev, 90)), 2),
        "mean_reversion_pts": round(float(np.mean(max_rev)), 2),
    }
    for t in thresholds:
        result[f"pct_gte_{t}pt"] = round(float(np.mean(max_rev >= t) * 100), 2)

    result["median_bars_to_max_rev"] = int(np.median(bars_max[bars_max > 0])) if (bars_max > 0).any() else 0
    recov_mask = recovered
    result["median_bars_to_recovery"] = int(np.median(bars_recov[recov_mask])) if recov_mask.any() else 0
    result["pct_full_recovery"] = round(float(np.mean(recovered) * 100), 2)
    result["pct_continued_reversal"] = round(float(np.mean(continued) * 100), 2)
    result["pct_pullback_only"] = round(float(np.mean(recovered & ~continued) * 100), 2)

    return result


def main():
    t0 = time.time()
    print("=" * 60)
    print("POST-COMPLETION REVERSION ANALYSIS")
    print("=" * 60)

    prices, time_secs, cal_dates = load_p1_rth()
    trading_dates = compute_trading_dates(cal_dates, time_secs)
    sids = assign_session_ids(trading_dates)

    all_results = []

    for cfg in CONFIGS:
        pt = cfg["parent"]
        ct = cfg["child"]
        print(f"\n--- Parent={pt}pt, Child={ct}pt ---")

        t1 = time.time()
        sw_idx, sw_price, sw_dir, sw_sid = zigzag(prices, sids, float(ct))
        sw_ts = time_secs[sw_idx]
        print(f"  {len(sw_price):,} child swings ({time.time()-t1:.1f}s)")

        t2 = time.time()
        (max_rev, bars_max, bars_recov, recovered, continued,
         comp_price, comp_ts) = measure_post_completion_reversion(
            sw_price.astype(np.float64), sw_dir, sw_sid, sw_ts,
            float(pt), prices, sids, time_secs
        )
        print(f"  {len(max_rev):,} completions analyzed ({time.time()-t2:.1f}s)")

        result = analyze_reversion(max_rev, bars_max, bars_recov, recovered, continued, pt)
        all_results.append(result)

        print(f"  Median reversion: {result['median_reversion_pts']:.1f} pts")
        print(f"  P75: {result['p75_reversion']:.1f}, P90: {result['p90_reversion']:.1f}")
        for t_val in [8, 12, 16, 20, 24]:
            print(f"    >= {t_val}pt: {result[f'pct_gte_{t_val}pt']:.1f}%")
        print(f"  Full recovery (price returns to completion): {result['pct_full_recovery']:.1f}%")
        print(f"  Continued reversal (>= parent thresh): {result['pct_continued_reversal']:.1f}%")
        print(f"  Pullback only (recovered, no continuation): {result['pct_pullback_only']:.1f}%")

        # Save CSV
        pd.DataFrame([result]).to_csv(OUT_DIR / f"reversion_{pt}pt.csv", index=False)

    # Summary markdown
    lines = [
        "# Post-Completion Reversion Analysis",
        f"**Data:** P1 RTH 1-tick",
        "",
    ]
    for r in all_results:
        pt = r["parent_thresh"]
        lines.extend([
            f"## Parent = {pt}pt",
            "",
            f"| Metric | Value |",
            f"|--------|-------|",
            f"| Sample count | {r['sample_count']:,} |",
            f"| Median reversion | {r['median_reversion_pts']:.1f} pts |",
            f"| P25 reversion | {r['p25_reversion']:.1f} pts |",
            f"| P75 reversion | {r['p75_reversion']:.1f} pts |",
            f"| P90 reversion | {r['p90_reversion']:.1f} pts |",
        ])
        for t_val in [8, 12, 16, 20, 24]:
            lines.append(f"| >= {t_val}pt reversion | {r[f'pct_gte_{t_val}pt']:.1f}% |")
        lines.extend([
            f"| Median bars to max reversion | {r['median_bars_to_max_rev']} |",
            f"| Median bars to recovery | {r['median_bars_to_recovery']} |",
            f"| Full recovery (pullback within continuation) | {r['pct_full_recovery']:.1f}% |",
            f"| Continued reversal (new parent move) | {r['pct_continued_reversal']:.1f}% |",
            f"| Pullback only | {r['pct_pullback_only']:.1f}% |",
            "",
        ])

    (OUT_DIR / "post_completion_summary.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"\n  post_completion_summary.md saved")
    print(f"  Total time: {time.time()-t0:.1f}s")


if __name__ == "__main__":
    main()
