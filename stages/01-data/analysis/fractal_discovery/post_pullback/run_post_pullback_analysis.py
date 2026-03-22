#!/usr/bin/env python3
# STATUS: ONE-TIME
# PURPOSE: Post-pullback displacement and completion by depth
# LAST RUN: 2026-03

"""Post-pullback displacement + completion by depth analysis.

Runs on P1 RTH 1-tick data using zigzag infrastructure from fractal_01_prepare.
Child threshold = 10 pts for all parent thresholds (25, 35, 40).

Query 1: Post-pullback favorable displacement distribution
Query 2: Completion rate conditioned on pullback depth

Usage:
    python run_post_pullback_analysis.py
"""
import numpy as np
import numba as nb
import pandas as pd
from pathlib import Path
import time
import sys

# Reuse zigzag infrastructure
_FRACTAL_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_FRACTAL_DIR))
from fractal_01_prepare import zigzag, compute_trading_dates, assign_session_ids

# === CONFIG ===
DATA_DIR = Path(r"C:\Projects\pipeline\stages\01-data\data\bar_data\tick")
P1_PATH = DATA_DIR / "NQ_BarData_1tick_rot_P1.csv"
OUT_DIR = Path(__file__).resolve().parent
OUT_DIR.mkdir(parents=True, exist_ok=True)

CHILD_THRESH = 10  # Child zigzag threshold (matches AD=10 at SD=25)
PARENT_THRESHOLDS = [25, 35, 40]  # Strategy StepDist values

RTH_START = 9 * 3600 + 30 * 60   # 09:30
RTH_END = 16 * 3600 + 15 * 60    # 16:15

DISP_THRESHOLDS = [10, 15, 20, 25, 30, 40]  # Points for displacement distribution


# === DATA LOADING (P1 only, RTH only) ===

def load_p1_rth():
    """Load P1 1-tick data, filter to RTH, return (prices, time_secs, cal_dates)."""
    print(f"Loading P1 1-tick data from: {P1_PATH}")
    df = pd.read_csv(
        P1_PATH, usecols=[0, 1, 5], skipinitialspace=True,
        header=0, low_memory=False,
    )
    df.columns = ['date', 'time', 'price']
    print(f"  Total rows: {len(df):,}")

    # Parse time → seconds since midnight
    t = df['time'].str.strip()
    parts = t.str.split(':', n=2, expand=True)
    time_secs = (parts[0].astype(np.int32) * 3600 +
                 parts[1].astype(np.int32) * 60 +
                 parts[2].astype(np.float64)).values.astype(np.float32)

    # Parse date → YYYYMMDD integer
    d = df['date'].str.strip()
    dparts = d.str.split('-', n=2, expand=True)
    cal_dates = (dparts[0].astype(np.int32) * 10000 +
                 dparts[1].astype(np.int32) * 100 +
                 dparts[2].astype(np.int32)).values.astype(np.int32)

    prices = df['price'].values.astype(np.float32)

    # Filter to RTH
    mask = (time_secs >= RTH_START) & (time_secs < RTH_END)
    prices = prices[mask].copy()
    time_secs = time_secs[mask].copy()
    cal_dates = cal_dates[mask].copy()

    trading_days = len(np.unique(cal_dates))
    print(f"  RTH rows: {len(prices):,}, {trading_days} trading days")
    return prices, time_secs, cal_dates


# === NUMBA: POST-PULLBACK ANALYSIS ===

@nb.njit(cache=True)
def post_pullback_walk(c_prices, c_dirs, c_sids, c_time_secs, parent_thresh):
    """Walk child swings and extract first-pullback metrics per walk.

    For each walk from an anchor point:
    1. Track initial favorable move
    2. When first retrace occurs, record pullback depth
    3. When retrace ends (resumption), measure max favorable displacement
       FROM THE PULLBACK POINT until walk resolves

    Returns per-pullback arrays (only walks with ≥1 retrace):
      is_success:         did walk reach +parent_thresh from anchor?
      progress_pts:       favorable displacement from anchor when pullback started
      pullback_depth_pts: depth of first pullback in points
      pullback_depth_pct: depth as % of progress (depth/progress × 100)
      post_pb_max_fav:    max favorable displacement from pullback point (points)
      anchor_ts:          timestamp of anchor
    """
    n = len(c_prices)
    mx = n // 2 + 1

    o_succ   = np.empty(mx, dtype=nb.boolean)
    o_prog   = np.empty(mx, dtype=np.float64)   # progress at pullback start
    o_depth  = np.empty(mx, dtype=np.float64)   # pullback depth (points)
    o_dpct   = np.empty(mx, dtype=np.float64)   # depth as % of progress
    o_pfav   = np.empty(mx, dtype=np.float64)   # post-pullback max favorable (pts)
    o_ts     = np.empty(mx, dtype=np.float32)    # anchor timestamp
    cnt = 0

    i = 0
    while i < n - 1:
        cs = c_sids[i]
        anch_p = c_prices[i]
        anch_ts = c_time_secs[i]

        i += 1
        if c_sids[i] != cs:
            continue

        disp = c_prices[i] - anch_p
        if disp == 0.0:
            continue

        att = np.int8(1) if disp > 0 else np.int8(-1)
        max_fav = abs(disp)  # max favorable from anchor

        # Check immediate resolution (no pullback possible)
        if abs(disp) >= parent_thresh:
            i -= 0  # no pullback in this walk
            continue

        # Track whether we've seen the first pullback
        first_pb_seen = False
        progress_at_pb = 0.0
        pb_extreme = 0.0  # the pullback extreme price
        pb_point_price = 0.0  # price at pullback resumption
        post_pb_max_fav = 0.0

        while True:
            i += 1
            if i >= n or c_sids[i] != cs:
                break

            p = c_prices[i]
            disp_now = (p - anch_p) * att
            fav = disp_now

            if fav > max_fav:
                max_fav = fav

            if not first_pb_seen:
                # Looking for first retrace
                if c_dirs[i] != att:
                    # First retrace detected!
                    first_pb_seen = True
                    progress_at_pb = max_fav  # how far we got before pullback
                    pb_extreme = p  # start tracking pullback depth
                else:
                    # Still moving favorably, update max_fav
                    pass
            else:
                # After first retrace detected
                if pb_point_price == 0.0:
                    # Still in pullback — tracking pullback extreme
                    if att == 1:
                        if p < pb_extreme:
                            pb_extreme = p
                    else:
                        if p > pb_extreme:
                            pb_extreme = p

                    if c_dirs[i] == att:
                        # Pullback ended — resumption
                        pb_point_price = pb_extreme  # use the extreme as the pullback point
                        # Compute post-pullback favorable displacement from pb point
                        post_pb_fav = (p - pb_point_price) * att
                        if post_pb_fav > post_pb_max_fav:
                            post_pb_max_fav = post_pb_fav
                else:
                    # After pullback resumption — track max favorable from pb point
                    post_pb_fav = (p - pb_point_price) * att
                    if post_pb_fav > post_pb_max_fav:
                        post_pb_max_fav = post_pb_fav

            # Check resolution
            if fav >= parent_thresh:
                if first_pb_seen and pb_point_price != 0.0:
                    # Resolved as success WITH a pullback
                    depth = progress_at_pb - ((pb_point_price - anch_p) * att)
                    if progress_at_pb > 0:
                        dpct = depth / progress_at_pb * 100.0
                    else:
                        dpct = 0.0
                    o_succ[cnt] = True
                    o_prog[cnt] = progress_at_pb
                    o_depth[cnt] = depth
                    o_dpct[cnt] = dpct
                    o_pfav[cnt] = post_pb_max_fav
                    o_ts[cnt] = anch_ts
                    cnt += 1
                break
            elif fav <= -parent_thresh:
                if first_pb_seen and pb_point_price != 0.0:
                    depth = progress_at_pb - ((pb_point_price - anch_p) * att)
                    if progress_at_pb > 0:
                        dpct = depth / progress_at_pb * 100.0
                    else:
                        dpct = 0.0
                    o_succ[cnt] = False
                    o_prog[cnt] = progress_at_pb
                    o_depth[cnt] = depth
                    o_dpct[cnt] = dpct
                    o_pfav[cnt] = post_pb_max_fav
                    o_ts[cnt] = anch_ts
                    cnt += 1
                break

    return (o_succ[:cnt], o_prog[:cnt], o_depth[:cnt],
            o_dpct[:cnt], o_pfav[:cnt], o_ts[:cnt])


# === ANALYSIS FUNCTIONS ===

def query1_displacement(is_succ, post_pb_fav, parent_thresh):
    """Query 1: Post-pullback favorable displacement distribution."""
    n = len(post_pb_fav)
    if n == 0:
        return {}

    return {
        "parent_thresh": parent_thresh,
        "child_thresh": CHILD_THRESH,
        "sample_count": n,
        "median_pts": round(float(np.median(post_pb_fav)), 2),
        "p25_pts": round(float(np.percentile(post_pb_fav, 25)), 2),
        "p75_pts": round(float(np.percentile(post_pb_fav, 75)), 2),
        "p90_pts": round(float(np.percentile(post_pb_fav, 90)), 2),
        "mean_pts": round(float(np.mean(post_pb_fav)), 2),
        **{
            f"pct_gte_{t}pts": round(float(np.mean(post_pb_fav >= t) * 100), 2)
            for t in DISP_THRESHOLDS
        },
        "completion_rate": round(float(np.mean(is_succ) * 100), 2),
    }


def query2_completion_by_depth(is_succ, depth_pct, post_pb_fav, parent_thresh):
    """Query 2: Completion rate conditioned on pullback depth."""
    rows = []
    buckets = [
        ("Shallow (<=25%)", 0, 25),
        ("Moderate (25-50%)", 25, 50),
        ("Deep (50-75%)", 50, 75),
        ("Very deep (75-100%)", 75, 100),
    ]

    for label, lo, hi in buckets:
        if hi == 100:
            mask = (depth_pct >= lo) & (depth_pct <= hi + 50)  # include >100%
        else:
            mask = (depth_pct >= lo) & (depth_pct < hi)

        n = int(np.sum(mask))
        if n == 0:
            rows.append({
                "parent_thresh": parent_thresh,
                "depth_bucket": label,
                "sample_count": 0,
                "completion_rate": 0.0,
                "median_post_pb_fav_pts": 0.0,
                "mean_post_pb_fav_pts": 0.0,
            })
            continue

        rows.append({
            "parent_thresh": parent_thresh,
            "depth_bucket": label,
            "sample_count": n,
            "completion_rate": round(float(np.mean(is_succ[mask]) * 100), 2),
            "median_post_pb_fav_pts": round(float(np.median(post_pb_fav[mask])), 2),
            "mean_post_pb_fav_pts": round(float(np.mean(post_pb_fav[mask])), 2),
        })

    return rows


# === MAIN ===

def main():
    t0 = time.time()

    # Load data
    print("=" * 60)
    print("POST-PULLBACK DISPLACEMENT + COMPLETION BY DEPTH")
    print("=" * 60)

    prices, time_secs, cal_dates = load_p1_rth()

    # Compute trading dates and session IDs
    print("\nComputing session IDs...")
    trading_dates = compute_trading_dates(cal_dates, time_secs)
    sids = assign_session_ids(trading_dates)

    # Run zigzag at child threshold
    print(f"\nRunning zigzag at threshold {CHILD_THRESH}...")
    t1 = time.time()
    sw_idx, sw_price, sw_dir, sw_sid = zigzag(prices, sids, float(CHILD_THRESH))
    sw_ts = time_secs[sw_idx]
    print(f"  {len(sw_price):,} child swings ({time.time()-t1:.1f}s)")

    # Run analysis for each parent threshold
    all_q1_rows = []
    all_q2_rows = []

    for pt in PARENT_THRESHOLDS:
        print(f"\n--- Parent threshold = {pt} pts ---")
        t2 = time.time()

        is_succ, progress, depth, depth_pct, post_pb_fav, anchor_ts = post_pullback_walk(
            sw_price.astype(np.float64),
            sw_dir,
            sw_sid,
            sw_ts,
            float(pt),
        )
        elapsed = time.time() - t2
        print(f"  Pullback walks: {len(is_succ):,} ({elapsed:.1f}s)")

        if len(is_succ) == 0:
            print("  WARNING: no pullback walks found")
            continue

        # Query 1: Displacement distribution
        q1 = query1_displacement(is_succ, post_pb_fav, pt)
        all_q1_rows.append(q1)

        print(f"  Completion rate: {q1['completion_rate']:.1f}%")
        print(f"  Post-PB displacement: median={q1['median_pts']:.1f}, "
              f"P75={q1['p75_pts']:.1f}, P90={q1['p90_pts']:.1f}")
        for t_val in DISP_THRESHOLDS:
            pct = q1[f"pct_gte_{t_val}pts"]
            print(f"    >= {t_val:2d} pts: {pct:.1f}%")

        # Query 2: Completion by depth
        q2 = query2_completion_by_depth(is_succ, depth_pct, post_pb_fav, pt)
        all_q2_rows.extend(q2)

        print(f"\n  Completion by pullback depth:")
        for row in q2:
            print(f"    {row['depth_bucket']:22s}: n={row['sample_count']:5d}, "
                  f"CR={row['completion_rate']:.1f}%, "
                  f"med_fav={row['median_post_pb_fav_pts']:.1f}pts")

    # Save outputs
    print("\n" + "=" * 60)
    print("SAVING OUTPUTS")
    print("=" * 60)

    q1_df = pd.DataFrame(all_q1_rows)
    q1_df.to_csv(OUT_DIR / "post_pullback_displacement.csv", index=False)
    print(f"  post_pullback_displacement.csv: {len(q1_df)} rows")

    q2_df = pd.DataFrame(all_q2_rows)
    q2_df.to_csv(OUT_DIR / "completion_by_depth.csv", index=False)
    print(f"  completion_by_depth.csv: {len(q2_df)} rows")

    # Generate summary markdown
    summary_lines = [
        "# Post-Pullback Displacement + Completion Analysis",
        f"**Data:** P1 RTH 1-tick, child threshold = {CHILD_THRESH} pts",
        f"**Parent thresholds:** {PARENT_THRESHOLDS}",
        "",
        "## Query 1: Post-Pullback Favorable Displacement",
        "",
        "From the pullback resumption point, how far does price typically travel favorably?",
        "",
        "| Parent | Samples | Median | P25 | P75 | P90 | Completion% |",
        "|--------|---------|--------|-----|-----|-----|-------------|",
    ]

    for q1 in all_q1_rows:
        pt = q1["parent_thresh"]
        summary_lines.append(
            f"| {pt} | {q1['sample_count']:,} | {q1['median_pts']:.1f} "
            f"| {q1['p25_pts']:.1f} | {q1['p75_pts']:.1f} | {q1['p90_pts']:.1f} "
            f"| {q1['completion_rate']:.1f}% |"
        )

    summary_lines.append("")
    summary_lines.append("### Displacement thresholds (% of pullbacks reaching each level)")
    summary_lines.append("")
    summary_lines.append("| Parent | >=10pts | >=15pts | >=20pts | >=25pts | >=30pts | >=40pts |")
    summary_lines.append("|--------|---------|---------|---------|---------|---------|---------|")
    for q1 in all_q1_rows:
        pt = q1["parent_thresh"]
        vals = " | ".join(f"{q1[f'pct_gte_{t}pts']:.1f}%" for t in DISP_THRESHOLDS)
        summary_lines.append(f"| {pt} | {vals} |")

    summary_lines.extend([
        "",
        "## Query 2: Completion Rate by Pullback Depth",
        "",
        "Does shallow pullback → higher completion rate?",
        "",
    ])

    for pt in PARENT_THRESHOLDS:
        pt_rows = [r for r in all_q2_rows if r["parent_thresh"] == pt]
        summary_lines.append(f"### Parent = {pt} pts")
        summary_lines.append("")
        summary_lines.append("| Depth Bucket | Samples | Completion% | Median Post-PB Fav |")
        summary_lines.append("|-------------|---------|-------------|-------------------|")
        for r in pt_rows:
            summary_lines.append(
                f"| {r['depth_bucket']} | {r['sample_count']:,} "
                f"| {r['completion_rate']:.1f}% | {r['median_post_pb_fav_pts']:.1f} pts |"
            )
        summary_lines.append("")

    # Strategy implications
    summary_lines.extend([
        "## Strategy Implications",
        "",
        "Key questions answered:",
        "",
        "1. **Is the success target reachable from the pullback point?**",
        "   Compare P75 post-pullback displacement against RT×SD:",
        "   - SD=25, RT=0.8: target = 20 pts from entry",
        "   - SD=35, RT=1.0: target = 35 pts from entry",
        "   - SD=40, RT=0.8: target = 32 pts from entry",
        "",
        "2. **Do shallow pullbacks complete more reliably?**",
        "   If shallow >> deep completion rate, pullback_depth_pct is a viable filter.",
        "",
        "3. **What is the structural completion rate after a pullback?**",
        "   If completion rate ≈ random walk prediction, pullback entry adds no edge.",
        "   Random walk: SD/(RT×SD + SD) = 1/(RT+1).",
        "   - RT=0.8: RW = 55.6%",
        "   - RT=1.0: RW = 50.0%",
    ])

    (OUT_DIR / "post_pullback_summary.md").write_text("\n".join(summary_lines), encoding="utf-8")
    print(f"  post_pullback_summary.md saved")

    print(f"\n  Total time: {time.time()-t0:.1f}s")


if __name__ == "__main__":
    main()
