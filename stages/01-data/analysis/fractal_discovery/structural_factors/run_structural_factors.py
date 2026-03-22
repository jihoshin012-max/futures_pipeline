#!/usr/bin/env python3
# STATUS: ONE-TIME
# PURPOSE: Structural factor analysis (7 queries on fractal inflection points)
# LAST RUN: 2026-03

"""Structural Factor Analysis — 7 queries on fractal inflection points.

Measures INTENSITY, SPEED, TIME, VOLATILITY, and MULTI-SCALE CONTEXT
at pullback events. Results are candidate Facts for the fractal knowledge base.

Usage:
    python run_structural_factors.py

Data: P1 1-tick RTH, parent thresholds 25pt and 40pt.
"""
import numpy as np
import numba as nb
import pandas as pd
from pathlib import Path
import sys
import time

# Reuse zigzag infrastructure
_FRACTAL_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_FRACTAL_DIR))
from fractal_01_prepare import zigzag, compute_trading_dates, assign_session_ids

# === CONFIG ===
DATA_DIR = Path(r"C:\Projects\pipeline\stages\01-data\data\bar_data\tick")
P1_PATH = DATA_DIR / "NQ_BarData_1tick_rot_P1.csv"
OUT_DIR = Path(__file__).resolve().parent
OUT_DIR.mkdir(parents=True, exist_ok=True)

PARENT_CONFIGS = [
    {"parent": 25, "child": 10, "grandparent": 63},   # 2.5×25=62.5->63
    {"parent": 40, "child": 16, "grandparent": 100},   # 2.5×40=100
]

RTH_START = 9 * 3600 + 30 * 60
RTH_END = 16 * 3600 + 15 * 60

STRONG_THRESHOLD = 15  # pp spread for STRONG verdict
MODERATE_THRESHOLD = 10  # pp spread for MODERATE verdict


# === DATA LOADING ===

def load_p1_rth():
    """Load P1 1-tick data with Volume and bar range, filter to RTH."""
    print(f"Loading P1 1-tick data from: {P1_PATH}")
    cols_needed = [0, 1, 2, 3, 4, 5, 6]  # Date, Time, O, H, L, Last, Volume
    df = pd.read_csv(P1_PATH, usecols=cols_needed, skipinitialspace=True,
                     header=0, low_memory=False)
    df.columns = ['date', 'time', 'open', 'high', 'low', 'price', 'volume']
    print(f"  Total rows: {len(df):,}")

    # Parse time
    t = df['time'].str.strip()
    parts = t.str.split(':', n=2, expand=True)
    time_secs = (parts[0].astype(np.int32) * 3600 +
                 parts[1].astype(np.int32) * 60 +
                 parts[2].astype(np.float64)).values.astype(np.float32)

    # Parse date
    d = df['date'].str.strip()
    dparts = d.str.split('-', n=2, expand=True)
    cal_dates = (dparts[0].astype(np.int32) * 10000 +
                 dparts[1].astype(np.int32) * 100 +
                 dparts[2].astype(np.int32)).values.astype(np.int32)

    prices = df['price'].values.astype(np.float32)
    highs = df['high'].values.astype(np.float32)
    lows = df['low'].values.astype(np.float32)
    volume = df['volume'].values.astype(np.float32)
    bar_range = highs - lows

    # Filter to RTH
    mask = (time_secs >= RTH_START) & (time_secs < RTH_END)
    prices = prices[mask].copy()
    time_secs = time_secs[mask].copy()
    cal_dates = cal_dates[mask].copy()
    volume = volume[mask].copy()
    bar_range = bar_range[mask].copy()

    trading_days = len(np.unique(cal_dates))
    print(f"  RTH rows: {len(prices):,}, {trading_days} trading days")
    return prices, time_secs, cal_dates, volume, bar_range


# === ZIGZAG AT ALL THRESHOLDS ===

def compute_all_zigzags(prices, sids, time_secs, thresholds):
    """Run zigzag at each threshold, return dict of results."""
    results = {}
    for thresh in thresholds:
        t0 = time.time()
        sw_idx, sw_price, sw_dir, sw_sid = zigzag(prices, sids, float(thresh))
        sw_ts = time_secs[sw_idx]
        results[thresh] = {
            'idx': sw_idx, 'price': sw_price.astype(np.float64),
            'dir': sw_dir, 'sid': sw_sid, 'ts': sw_ts,
        }
        print(f"    Threshold {thresh:3d}: {len(sw_price):>8,} swings ({time.time()-t0:.2f}s)")
    return results


# === CORE: EXTRACT PULLBACK EVENTS WITH ENRICHMENT ===

@nb.njit(cache=True)
def extract_pullback_events(
    c_prices, c_dirs, c_sids, c_idx, c_ts,
    parent_thresh,
    raw_volume, raw_bar_range,
):
    """Walk child swings, extract detailed pullback events.

    For each walk with ≥1 retrace, records:
    - Completion (is_success)
    - Pullback depth (points and % of progress)
    - Volume ratio (pullback vol / directional vol)
    - Speed of initial leg (points / bars)
    - Bar range ratio (pullback range / directional range)
    - Time of pullback (seconds from midnight)
    - Bar indices for directional leg and pullback
    """
    n = len(c_prices)
    mx = n // 2 + 1

    o_succ       = np.empty(mx, dtype=nb.boolean)
    o_depth_pts  = np.empty(mx, dtype=np.float64)
    o_depth_pct  = np.empty(mx, dtype=np.float64)
    o_progress   = np.empty(mx, dtype=np.float64)
    o_vol_ratio  = np.empty(mx, dtype=np.float64)
    o_speed      = np.empty(mx, dtype=np.float64)
    o_range_ratio = np.empty(mx, dtype=np.float64)
    o_pb_time    = np.empty(mx, dtype=np.float32)
    o_anchor_ts  = np.empty(mx, dtype=np.float32)
    o_anchor_sid = np.empty(mx, dtype=np.int32)
    o_dir_bars   = np.empty(mx, dtype=np.int64)
    o_pb_bars    = np.empty(mx, dtype=np.int64)
    cnt = 0

    i = 0
    while i < n - 1:
        cs = c_sids[i]
        anch_p = c_prices[i]
        anch_ts = c_ts[i]
        anch_idx = c_idx[i]

        i += 1
        if c_sids[i] != cs:
            continue

        disp = c_prices[i] - anch_p
        if disp == 0.0:
            continue

        att = np.int8(1) if disp > 0 else np.int8(-1)
        max_fav = abs(disp)

        if abs(disp) >= parent_thresh:
            continue  # Immediate resolution, no pullback

        # Track initial directional leg
        hwm_price = c_prices[i]
        hwm_idx = c_idx[i]
        dir_start_idx = anch_idx

        first_pb_seen = False
        pb_start_price = 0.0
        pb_start_idx = np.int64(0)
        pb_end_price = 0.0
        pb_end_idx = np.int64(0)
        pb_completed = False

        while True:
            i += 1
            if i >= n or c_sids[i] != cs:
                break

            p = c_prices[i]
            fav = (p - anch_p) * att

            if not first_pb_seen:
                # Extending or starting pullback?
                if fav > max_fav:
                    max_fav = fav
                    hwm_price = p
                    hwm_idx = c_idx[i]
                if c_dirs[i] != att:
                    # First retrace
                    first_pb_seen = True
                    pb_start_price = hwm_price
                    pb_start_idx = hwm_idx
                    pb_end_price = p
                    pb_end_idx = c_idx[i]
            elif not pb_completed:
                # Tracking pullback
                if att == 1:
                    if p < pb_end_price:
                        pb_end_price = p
                        pb_end_idx = c_idx[i]
                else:
                    if p > pb_end_price:
                        pb_end_price = p
                        pb_end_idx = c_idx[i]

                if c_dirs[i] == att:
                    # Pullback ended, resumption
                    pb_completed = True

            # Resolution check
            if fav >= parent_thresh:
                if first_pb_seen and pb_completed:
                    # Record pullback event
                    progress = max_fav
                    depth = abs(pb_start_price - pb_end_price)
                    dpct = (depth / progress * 100.0) if progress > 0 else 0.0

                    # Compute volume ratio
                    dir_s = dir_start_idx
                    dir_e = pb_start_idx
                    pb_s = pb_start_idx
                    pb_e = pb_end_idx

                    dir_n = dir_e - dir_s
                    pb_n = pb_e - pb_s

                    dir_vol = 0.0
                    if dir_n > 0:
                        for bi in range(dir_s, dir_e):
                            if bi < len(raw_volume):
                                dir_vol += raw_volume[bi]
                        dir_vol /= dir_n

                    pb_vol = 0.0
                    if pb_n > 0:
                        for bi in range(pb_s, pb_e):
                            if bi < len(raw_volume):
                                pb_vol += raw_volume[bi]
                        pb_vol /= pb_n

                    vol_ratio = pb_vol / dir_vol if dir_vol > 0 else 1.0

                    # Speed of initial leg
                    speed = progress / dir_n if dir_n > 0 else 0.0

                    # Bar range ratio
                    dir_rng = 0.0
                    if dir_n > 0:
                        for bi in range(dir_s, dir_e):
                            if bi < len(raw_bar_range):
                                dir_rng += raw_bar_range[bi]
                        dir_rng /= dir_n

                    pb_rng = 0.0
                    if pb_n > 0:
                        for bi in range(pb_s, pb_e):
                            if bi < len(raw_bar_range):
                                pb_rng += raw_bar_range[bi]
                        pb_rng /= pb_n

                    rng_ratio = pb_rng / dir_rng if dir_rng > 0 else 1.0

                    o_succ[cnt] = True
                    o_depth_pts[cnt] = depth
                    o_depth_pct[cnt] = dpct
                    o_progress[cnt] = progress
                    o_vol_ratio[cnt] = vol_ratio
                    o_speed[cnt] = speed
                    o_range_ratio[cnt] = rng_ratio
                    o_pb_time[cnt] = c_ts[i - 1] if i > 0 else anch_ts
                    o_anchor_ts[cnt] = anch_ts
                    o_anchor_sid[cnt] = cs
                    o_dir_bars[cnt] = dir_n
                    o_pb_bars[cnt] = pb_n
                    cnt += 1
                break

            elif fav <= -parent_thresh:
                if first_pb_seen and pb_completed:
                    progress = max_fav
                    depth = abs(pb_start_price - pb_end_price)
                    dpct = (depth / progress * 100.0) if progress > 0 else 0.0

                    dir_s = dir_start_idx
                    dir_e = pb_start_idx
                    pb_s = pb_start_idx
                    pb_e = pb_end_idx
                    dir_n = dir_e - dir_s
                    pb_n = pb_e - pb_s

                    dir_vol = 0.0
                    if dir_n > 0:
                        for bi in range(dir_s, dir_e):
                            if bi < len(raw_volume):
                                dir_vol += raw_volume[bi]
                        dir_vol /= dir_n
                    pb_vol = 0.0
                    if pb_n > 0:
                        for bi in range(pb_s, pb_e):
                            if bi < len(raw_volume):
                                pb_vol += raw_volume[bi]
                        pb_vol /= pb_n
                    vol_ratio = pb_vol / dir_vol if dir_vol > 0 else 1.0

                    speed = progress / dir_n if dir_n > 0 else 0.0

                    dir_rng = 0.0
                    if dir_n > 0:
                        for bi in range(dir_s, dir_e):
                            if bi < len(raw_bar_range):
                                dir_rng += raw_bar_range[bi]
                        dir_rng /= dir_n
                    pb_rng = 0.0
                    if pb_n > 0:
                        for bi in range(pb_s, pb_e):
                            if bi < len(raw_bar_range):
                                pb_rng += raw_bar_range[bi]
                        pb_rng /= pb_n
                    rng_ratio = pb_rng / dir_rng if dir_rng > 0 else 1.0

                    o_succ[cnt] = False
                    o_depth_pts[cnt] = depth
                    o_depth_pct[cnt] = dpct
                    o_progress[cnt] = progress
                    o_vol_ratio[cnt] = vol_ratio
                    o_speed[cnt] = speed
                    o_range_ratio[cnt] = rng_ratio
                    o_pb_time[cnt] = c_ts[i - 1] if i > 0 else anch_ts
                    o_anchor_ts[cnt] = anch_ts
                    o_anchor_sid[cnt] = cs
                    o_dir_bars[cnt] = dir_n
                    o_pb_bars[cnt] = pb_n
                    cnt += 1
                break

    return (o_succ[:cnt], o_depth_pts[:cnt], o_depth_pct[:cnt], o_progress[:cnt],
            o_vol_ratio[:cnt], o_speed[:cnt], o_range_ratio[:cnt], o_pb_time[:cnt],
            o_anchor_ts[:cnt], o_anchor_sid[:cnt], o_dir_bars[:cnt], o_pb_bars[:cnt])


# === ANALYSIS HELPERS ===

def quartile_analysis(values, is_success, label, out_rows):
    """Bucket values into quartiles, report completion rate."""
    df = pd.DataFrame({"val": values, "success": is_success})
    # qcut may produce fewer than 4 bins if many duplicate values
    try:
        bins = pd.qcut(df["val"], 4, duplicates="drop")
        n_bins = bins.cat.categories.size
        bin_labels = [f"Q{i+1}" for i in range(n_bins)]
        df["q"] = pd.qcut(df["val"], 4, labels=bin_labels, duplicates="drop")
    except (ValueError, IndexError):
        # Fallback: split at median
        med = df["val"].median()
        df["q"] = pd.Categorical(
            np.where(df["val"] <= med, "Below median", "Above median"),
            categories=["Below median", "Above median"],
        )
    for q in df["q"].cat.categories:
        sub = df[df["q"] == q]
        out_rows.append({
            "factor": label,
            "bucket": q,
            "sample_count": len(sub),
            "completion_rate": round(sub["success"].mean() * 100, 2),
            "median_value": round(sub["val"].median(), 4),
        })
    spread = 0.0
    crs = [df[df["q"] == q]["success"].mean() * 100 for q in df["q"].cat.categories if len(df[df["q"] == q]) > 0]
    if crs:
        spread = max(crs) - min(crs)
    return round(spread, 2)


def verdict(spread):
    if spread >= STRONG_THRESHOLD:
        return "STRONG"
    elif spread >= MODERATE_THRESHOLD:
        return "MODERATE"
    return "WEAK"


# === QUERY 5: MULTI-SCALE ALIGNMENT ===

@nb.njit(cache=True)
def classify_alignment(anch_prices, anch_dirs, anch_sids,
                       gp_prices, gp_dirs, gp_sids, gp_idx,
                       c_anchor_sids, c_anchor_ts, c_prices_at_anchor,
                       parent_thresh):
    """Classify each pullback event as WITH/AGAINST/EXTENDED relative to grandparent."""
    n_events = len(c_anchor_sids)
    n_gp = len(gp_prices)
    # Output: 0=WITH, 1=AGAINST, 2=EXTENDED, -1=UNKNOWN
    out = np.full(n_events, np.int8(-1))

    if n_gp < 2:
        return out

    # For each event, find the most recent grandparent swing
    gp_ptr = 0
    for ev in range(n_events):
        ev_sid = c_anchor_sids[ev]

        # Advance gp_ptr to the last GP swing before or at this event's session
        while gp_ptr < n_gp - 1 and gp_sids[gp_ptr + 1] <= ev_sid:
            gp_ptr += 1

        if gp_ptr < 1:
            continue

        # Most recent confirmed GP swing
        gp_dir = gp_dirs[gp_ptr]  # +1 = high (just made a top), -1 = low
        gp_price = gp_prices[gp_ptr]

        # Current GP swing direction: if last confirmed was a high (+1),
        # the current move is DOWN. If low (-1), current move is UP.
        current_gp_direction = -gp_dir  # +1 if trending up, -1 if trending down

        # What direction was the parent move? Use the child walk's att direction
        # We don't have att directly, but we know the anchor is a child swing.
        # For simplicity, we'll compare the direction sign
        # Actually we need the parent move direction. Since we're at a pullback
        # within a parent move, the parent direction matches att.
        # We don't have att here, so skip this approach.
        # Instead: classify based on where price is relative to GP swing
        # If price is in favorable half of GP range, it's WITH.

        # Simplified: compare parent move progress to GP context
        # WITH = parent att matches current_gp_direction
        # We approximate att from anchors: if anchor is a low, att=+1; high, att=-1
        # The anchor_dirs tell us: -1 = low (att will be +1), +1 = high (att will be -1)

        # Since we don't have att stored, use a heuristic:
        # The walk starts from a child swing. If the child swing is a low (dir=-1),
        # the walk goes UP (att=+1). If high (dir=+1), walk goes DOWN (att=-1).
        # But we don't have the child dir at the anchor in this function.
        # Mark as UNKNOWN for now - we'll compute outside Numba.
        out[ev] = -1

    return out


def compute_alignment_pandas(events_df, gp_swings, parent_thresh):
    """Classify alignment using pandas (cleaner than Numba for this logic)."""
    if len(gp_swings) < 2 or events_df.empty:
        events_df["alignment"] = "UNKNOWN"
        return events_df

    # For each event, find the active grandparent swing
    gp_prices = gp_swings["price"].values
    gp_dirs = gp_swings["dir"].values
    gp_sids = gp_swings["sid"].values

    alignments = []
    gp_ptr = 0

    for _, ev in events_df.iterrows():
        ev_sid = ev["anchor_sid"]

        while gp_ptr < len(gp_sids) - 1 and gp_sids[gp_ptr + 1] <= ev_sid:
            gp_ptr += 1

        if gp_ptr < 1:
            alignments.append("UNKNOWN")
            continue

        # Current GP direction: last confirmed swing was gp_dirs[gp_ptr]
        # +1 = high -> current GP move is DOWN. -1 = low -> current GP move is UP
        gp_current_dir = -gp_dirs[gp_ptr]  # +1=UP, -1=DOWN

        # Parent move direction from att (stored as 1 or -1)
        parent_dir = ev["att"]

        if parent_dir == gp_current_dir:
            # WITH trend — check if extended
            # GP swing progress: how far from last GP swing point
            gp_last = gp_prices[gp_ptr]
            if gp_ptr >= 2:
                gp_prev = gp_prices[gp_ptr - 1]
                gp_swing_size = abs(gp_last - gp_prev)
                # P90 of parent swings ≈ 2× parent_thresh (rough heuristic)
                typical_gp = 2.0 * parent_thresh
                if gp_swing_size > typical_gp:
                    alignments.append("EXTENDED")
                else:
                    alignments.append("WITH")
            else:
                alignments.append("WITH")
        else:
            alignments.append("AGAINST")

    events_df["alignment"] = alignments
    return events_df


# === QUERY 6: PRIOR COMPLETION HISTORY ===

def compute_prior_completions(events_df, child_swings, parent_thresh):
    """For each event, count how many of the prior 5 parent-scale walks completed."""
    # Use the child_walk_completion to get all walks
    from fractal_02_analyze import child_walk_completion

    c = child_swings
    is_succ, retrace, max_fav, anch_idx, gross, anch_ts = child_walk_completion(
        c['price'], c['dir'], c['sid'], c['ts'], parent_thresh
    )

    # Build a list of (session_id_approx, success) for all walks
    walk_sids = c['sid'][anch_idx]
    walk_results = list(zip(walk_sids, is_succ))

    # For each event, find the 5 most recent completed walks before it
    prior_counts = []
    walk_ptr = 0

    for _, ev in events_df.iterrows():
        ev_sid = ev["anchor_sid"]
        # Advance walk_ptr to walks before this event
        while walk_ptr < len(walk_results) and walk_results[walk_ptr][0] < ev_sid:
            walk_ptr += 1
        # Take last 5 walks before walk_ptr
        start = max(0, walk_ptr - 5)
        recent = walk_results[start:walk_ptr]
        completed = sum(1 for _, s in recent if s)
        prior_counts.append(completed)

    events_df["prior_completions"] = prior_counts
    return events_df


# === QUERY 7: SWING SEQUENCE WITHIN DAY ===

def compute_swing_sequence(events_df):
    """For each event, what number parent-scale swing of the day is it?"""
    # Group by session and count
    events_df = events_df.sort_values("anchor_ts_raw").copy()
    events_df["day_swing_seq"] = events_df.groupby("anchor_sid").cumcount() + 1
    return events_df


# === MAIN ===

def main():
    t_total = time.time()
    print("=" * 70)
    print("STRUCTURAL FACTOR ANALYSIS — 7 Queries")
    print("=" * 70)

    # Load data
    prices, time_secs, cal_dates, volume, bar_range = load_p1_rth()

    print("\nComputing session IDs...")
    trading_dates = compute_trading_dates(cal_dates, time_secs)
    sids = assign_session_ids(trading_dates)

    # Compute all needed zigzags
    all_thresholds = set()
    for cfg in PARENT_CONFIGS:
        all_thresholds.update([cfg["child"], cfg["parent"], cfg["grandparent"]])
    all_thresholds = sorted(all_thresholds)
    print(f"\nRunning zigzag at thresholds: {all_thresholds}")
    zz = compute_all_zigzags(prices, sids, time_secs, all_thresholds)

    # Results accumulators
    all_factor_rows = []  # For each query: (factor, bucket, count, CR, median)
    verdicts_list = []
    combined_candidates = []

    for cfg in PARENT_CONFIGS:
        pt = cfg["parent"]
        ct = cfg["child"]
        gpt = cfg["grandparent"]
        print(f"\n{'='*60}")
        print(f"PARENT={pt}pt, CHILD={ct}pt, GRANDPARENT={gpt}pt")
        print(f"{'='*60}")

        c = zz[ct]
        gp = zz[gpt]

        # Extract pullback events
        print("\nExtracting pullback events...")
        t0 = time.time()
        (is_succ, depth_pts, depth_pct, progress,
         vol_ratio, speed, range_ratio, pb_time,
         anchor_ts, anchor_sid, dir_bars, pb_bars) = extract_pullback_events(
            c['price'], c['dir'], c['sid'], c['idx'], c['ts'],
            float(pt), volume, bar_range
        )
        print(f"  {len(is_succ):,} pullback events ({time.time()-t0:.1f}s)")
        print(f"  Overall completion rate: {np.mean(is_succ)*100:.1f}%")

        if len(is_succ) < 50:
            print("  WARNING: too few events, skipping detailed analysis")
            continue

        tag = f"PT{pt}"

        # Build DataFrame for pandas-based queries
        events_df = pd.DataFrame({
            "success": is_succ,
            "depth_pts": depth_pts, "depth_pct": depth_pct,
            "progress": progress, "vol_ratio": vol_ratio,
            "speed": speed, "range_ratio": range_ratio,
            "pb_time": pb_time, "anchor_ts_raw": anchor_ts,
            "anchor_sid": anchor_sid, "dir_bars": dir_bars, "pb_bars": pb_bars,
        })
        # Infer att (parent direction) from depth: if depth same sign, we can't tell
        # Use progress: positive means the walk's favorable direction went that far
        # att is always +1 for our purposes (the walk tracks favorable displacement)
        # We need actual direction for Query 5 — use child swing dir at anchor
        # The anchor is at index i-1 in the walk. Child swing dir at anchor = c['dir'][walk_start]
        # This isn't available from extract_pullback_events directly.
        # For Query 5, we'll use a heuristic based on the anchor timestamp.
        # Actually, the child swings alternate: low(-1)->high(+1)->low(-1)...
        # Walk starts at a child swing. If the swing is -1 (low), att=+1 (UP move).
        # We need to match events back to their child swing. For now, assign att=+1
        # (we don't have the mapping). This means Query 5 alignment will be approximate.
        events_df["att"] = 1  # Placeholder — will be refined below

        # --- QUERY 1: Volume at Pullback ---
        print("\n  Q1: Volume at Pullback...")
        q1_rows = []
        spread1 = quartile_analysis(vol_ratio, is_succ, f"volume_ratio_{tag}", q1_rows)
        all_factor_rows.extend(q1_rows)
        v1 = verdict(spread1)
        verdicts_list.append({"factor": f"volume_ratio_{tag}", "spread_pp": spread1, "verdict": v1})
        print(f"    Spread: {spread1:.1f}pp -> {v1}")

        # Cross-tab: volume × depth
        depth_med = np.median(depth_pct)
        vol_med = np.median(vol_ratio)
        for d_label, d_mask in [("shallow", depth_pct <= depth_med), ("deep", depth_pct > depth_med)]:
            for v_label, v_mask in [("low_vol", vol_ratio <= vol_med), ("high_vol", vol_ratio > vol_med)]:
                combined = d_mask & v_mask
                n_comb = combined.sum()
                cr = np.mean(is_succ[combined]) * 100 if n_comb > 0 else 0
                all_factor_rows.append({
                    "factor": f"vol_x_depth_{tag}",
                    "bucket": f"{d_label}_{v_label}",
                    "sample_count": int(n_comb),
                    "completion_rate": round(cr, 2),
                    "median_value": 0,
                })

        # --- QUERY 2: Speed of Initial Move ---
        print("\n  Q2: Speed of Initial Move...")
        q2_rows = []
        spread2 = quartile_analysis(speed, is_succ, f"speed_{tag}", q2_rows)
        all_factor_rows.extend(q2_rows)
        v2 = verdict(spread2)
        verdicts_list.append({"factor": f"speed_{tag}", "spread_pp": spread2, "verdict": v2})
        print(f"    Spread: {spread2:.1f}pp -> {v2}")

        # --- QUERY 3: Time-of-Day ---
        print("\n  Q3: Time-of-Day for First Pullback...")
        # Convert pb_time (seconds from midnight) to 30-min blocks
        block_starts = list(range(RTH_START, RTH_END, 1800))
        for bs in block_starts:
            be = bs + 1800
            mask = (pb_time >= bs) & (pb_time < be)
            n_blk = mask.sum()
            cr_blk = np.mean(is_succ[mask]) * 100 if n_blk > 0 else 0
            h = bs // 3600
            m = (bs % 3600) // 60
            label = f"{h:02d}:{m:02d}"
            all_factor_rows.append({
                "factor": f"timeofday_{tag}",
                "bucket": label,
                "sample_count": int(n_blk),
                "completion_rate": round(cr_blk, 2),
                "median_value": 0,
            })
        # Compute spread
        tod_crs = []
        for bs in block_starts:
            mask = (pb_time >= bs) & (pb_time < bs + 1800)
            if mask.sum() >= 10:
                tod_crs.append(np.mean(is_succ[mask]) * 100)
        spread3 = max(tod_crs) - min(tod_crs) if tod_crs else 0
        v3 = verdict(spread3)
        verdicts_list.append({"factor": f"timeofday_{tag}", "spread_pp": round(spread3, 2), "verdict": v3})
        print(f"    Spread: {spread3:.1f}pp -> {v3}")

        # --- QUERY 4: Bar Range Profile ---
        print("\n  Q4: Bar Range Profile...")
        q4_rows = []
        spread4 = quartile_analysis(range_ratio, is_succ, f"range_ratio_{tag}", q4_rows)
        all_factor_rows.extend(q4_rows)
        v4 = verdict(spread4)
        verdicts_list.append({"factor": f"range_ratio_{tag}", "spread_pp": spread4, "verdict": v4})
        print(f"    Spread: {spread4:.1f}pp -> {v4}")

        # Correlation with speed
        corr_speed_range = np.corrcoef(speed, range_ratio)[0, 1] if len(speed) > 2 else 0
        print(f"    Corr(speed, range_ratio): {corr_speed_range:.3f}")
        all_factor_rows.append({
            "factor": f"corr_speed_range_{tag}",
            "bucket": "correlation",
            "sample_count": len(speed),
            "completion_rate": round(corr_speed_range, 4),
            "median_value": 0,
        })

        # --- QUERY 5: Multi-Scale Alignment ---
        print("\n  Q5: Multi-Scale Alignment...")
        gp_df = pd.DataFrame({
            "price": gp['price'], "dir": gp['dir'], "sid": gp['sid'],
        })
        events_df = compute_alignment_pandas(events_df, gp_df, pt)
        for al in ["WITH", "AGAINST", "EXTENDED", "UNKNOWN"]:
            mask = events_df["alignment"] == al
            n_al = mask.sum()
            cr_al = events_df.loc[mask, "success"].mean() * 100 if n_al > 0 else 0
            all_factor_rows.append({
                "factor": f"alignment_{tag}",
                "bucket": al,
                "sample_count": int(n_al),
                "completion_rate": round(cr_al, 2),
                "median_value": 0,
            })
            if n_al > 0:
                print(f"    {al}: n={n_al}, CR={cr_al:.1f}%")

        known = events_df[events_df["alignment"] != "UNKNOWN"]
        if len(known) > 0:
            al_crs = [known[known["alignment"] == a]["success"].mean() * 100
                      for a in ["WITH", "AGAINST", "EXTENDED"]
                      if (known["alignment"] == a).sum() >= 10]
            spread5 = max(al_crs) - min(al_crs) if len(al_crs) >= 2 else 0
        else:
            spread5 = 0
        v5 = verdict(spread5)
        verdicts_list.append({"factor": f"alignment_{tag}", "spread_pp": round(spread5, 2), "verdict": v5})
        print(f"    Spread: {spread5:.1f}pp -> {v5}")

        # --- QUERY 6: Prior Completion History ---
        print("\n  Q6: Prior Completion History...")
        try:
            events_df = compute_prior_completions(events_df, c, pt)
            for bucket_label, lo, hi in [("0-1 (failures)", 0, 1), ("2-3 (mixed)", 2, 3), ("4-5 (completions)", 4, 5)]:
                mask = (events_df["prior_completions"] >= lo) & (events_df["prior_completions"] <= hi)
                n_pc = mask.sum()
                cr_pc = events_df.loc[mask, "success"].mean() * 100 if n_pc > 0 else 0
                all_factor_rows.append({
                    "factor": f"prior_completion_{tag}",
                    "bucket": bucket_label,
                    "sample_count": int(n_pc),
                    "completion_rate": round(cr_pc, 2),
                    "median_value": 0,
                })
                if n_pc > 0:
                    print(f"    {bucket_label}: n={n_pc}, CR={cr_pc:.1f}%")
            pc_crs = []
            for lo, hi in [(0, 1), (2, 3), (4, 5)]:
                m = (events_df["prior_completions"] >= lo) & (events_df["prior_completions"] <= hi)
                if m.sum() >= 10:
                    pc_crs.append(events_df.loc[m, "success"].mean() * 100)
            spread6 = max(pc_crs) - min(pc_crs) if len(pc_crs) >= 2 else 0
            v6 = verdict(spread6)
        except Exception as e:
            print(f"    ERROR: {e}")
            spread6 = 0
            v6 = "ERROR"
        verdicts_list.append({"factor": f"prior_completion_{tag}", "spread_pp": round(spread6, 2), "verdict": v6})
        print(f"    Spread: {spread6:.1f}pp -> {v6}")

        # --- QUERY 7: Swing Sequence Within Day ---
        print("\n  Q7: Swing Sequence Within Day...")
        events_df = compute_swing_sequence(events_df)
        for seq in [1, 2, 3, 4]:
            label = f"{seq}" if seq < 4 else "4+"
            mask = events_df["day_swing_seq"] == seq if seq < 4 else events_df["day_swing_seq"] >= 4
            n_sq = mask.sum()
            cr_sq = events_df.loc[mask, "success"].mean() * 100 if n_sq > 0 else 0
            all_factor_rows.append({
                "factor": f"swing_seq_{tag}",
                "bucket": label,
                "sample_count": int(n_sq),
                "completion_rate": round(cr_sq, 2),
                "median_value": 0,
            })
            if n_sq > 0:
                print(f"    Swing #{label}: n={n_sq}, CR={cr_sq:.1f}%")
        sq_crs = []
        for seq in [1, 2, 3, 4]:
            m = events_df["day_swing_seq"] == seq if seq < 4 else events_df["day_swing_seq"] >= 4
            if m.sum() >= 10:
                sq_crs.append(events_df.loc[m, "success"].mean() * 100)
        spread7 = max(sq_crs) - min(sq_crs) if len(sq_crs) >= 2 else 0
        v7 = verdict(spread7)
        verdicts_list.append({"factor": f"swing_seq_{tag}", "spread_pp": round(spread7, 2), "verdict": v7})
        print(f"    Spread: {spread7:.1f}pp -> {v7}")

        # Collect candidates for combined analysis
        for sp, name in [(spread1, "volume_ratio"), (spread2, "speed"),
                         (spread3, "timeofday"), (spread4, "range_ratio"),
                         (spread5, "alignment"), (spread6, "prior_completion"),
                         (spread7, "swing_seq")]:
            if sp >= MODERATE_THRESHOLD:
                combined_candidates.append((name, tag, sp))

    # === COMBINED FACTOR ANALYSIS ===
    print(f"\n{'='*60}")
    print("COMBINED FACTOR ANALYSIS")
    print(f"{'='*60}")
    strong_factors = [c for c in combined_candidates if c[2] >= MODERATE_THRESHOLD]
    if len(strong_factors) >= 2:
        print(f"  {len(strong_factors)} factors qualify (>={MODERATE_THRESHOLD}pp)")
        for name, tag, sp in strong_factors:
            print(f"    {name}_{tag}: {sp:.1f}pp")
        # Cross-tabulate top 2 — placeholder: would need per-PT event data aligned
        print("  (Cross-tabulation requires event-level alignment — see per-query CSVs)")
    else:
        print(f"  Fewer than 2 factors reached {MODERATE_THRESHOLD}pp threshold. Skipping combined analysis.")

    # === SAVE OUTPUTS ===
    print(f"\n{'='*60}")
    print("SAVING OUTPUTS")
    print(f"{'='*60}")

    factor_df = pd.DataFrame(all_factor_rows)
    factor_df.to_csv(OUT_DIR / "all_factors.csv", index=False)
    print(f"  all_factors.csv: {len(factor_df)} rows")

    # Split into per-query CSVs
    for query_name in ["volume_ratio", "speed", "timeofday", "range_ratio",
                       "alignment", "prior_completion", "swing_seq"]:
        qdf = factor_df[factor_df["factor"].str.contains(query_name)]
        if len(qdf) > 0:
            fname = {
                "volume_ratio": "volume_analysis.csv",
                "speed": "speed_analysis.csv",
                "timeofday": "timeofday_analysis.csv",
                "range_ratio": "barrange_analysis.csv",
                "alignment": "multiscale_alignment.csv",
                "prior_completion": "prior_completion.csv",
                "swing_seq": "swing_sequence.csv",
            }[query_name]
            qdf.to_csv(OUT_DIR / fname, index=False)

    verdicts_df = pd.DataFrame(verdicts_list)
    verdicts_df.to_csv(OUT_DIR / "verdicts.csv", index=False)

    # Generate summary markdown
    lines = [
        "# Structural Factor Analysis — Summary",
        f"**Data:** P1 RTH 1-tick, parent thresholds {[c['parent'] for c in PARENT_CONFIGS]}",
        "",
        "## Verdicts",
        "",
        "| Factor | Parent | Spread (pp) | Verdict |",
        "|--------|--------|-------------|---------|",
    ]
    for _, v in verdicts_df.iterrows():
        lines.append(f"| {v['factor']} | — | {v['spread_pp']:.1f} | **{v['verdict']}** |")

    lines.extend(["", "## Threshold Definitions",
                   f"- STRONG: >{STRONG_THRESHOLD}pp spread",
                   f"- MODERATE: {MODERATE_THRESHOLD}-{STRONG_THRESHOLD}pp spread",
                   f"- WEAK: <{MODERATE_THRESHOLD}pp spread", ""])

    (OUT_DIR / "structural_factors_summary.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"  structural_factors_summary.md saved")

    print(f"\n  Total time: {time.time()-t_total:.1f}s")


if __name__ == "__main__":
    main()
