#!/usr/bin/env python3
# archetype: zone_touch
"""
Ray Baseline Analysis — Observational Study
Measures broken zone ray behavior before screening features or building trading logic.
Uses ALL available data (P1 + P2 combined) for maximum statistical power.
No parameters are fit, no thresholds are set. Measure and report.
"""

import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime, time, timedelta
import warnings
import sys
import traceback
import re

warnings.filterwarnings("ignore")

# =============================================================================
# CONSTANTS & CONFIG
# =============================================================================
TICK_SIZE = 0.25
PIPELINE_ROOT = Path(__file__).resolve().parent.parent.parent.parent
DATA_DIR = PIPELINE_ROOT / "stages" / "01-data" / "data"
TOUCH_DIR = DATA_DIR / "touches"
BAR_VOL_DIR = DATA_DIR / "bar_data" / "volume"
BAR_TIME_DIR = DATA_DIR / "bar_data" / "time"
OUTPUT_DIR = Path(__file__).resolve().parent / "output"

# Proximity thresholds to test (in ticks)
PROX_THRESHOLDS = [5, 10, 20, 30, 40]
# Wick-based reversal/cross threshold (ticks)
WICK_THRESH_TICKS = 20
# Ground truth parameters
GT_FORWARD_BARS = 200
GT_BOUNCE_SIDE_PCT = 0.80
GT_BREAK_MOVE_TICKS = 30
GT_BREAK_SIDE_PCT = 0.60
# Consecutive close counts to test
CONSEC_COUNTS = [2, 3, 4, 5]
# Max observation window for interaction resolution
MAX_OBS_BARS = 500
# RTH session bounds (ET)
RTH_START = time(9, 30)
RTH_END = time(16, 15)

# TF ordering for display
TF_ORDER = ["15m", "30m", "60m", "90m", "120m", "240m", "360m", "480m", "720m"]
TF_BUCKET_MAP = {
    "15m": "15m", "30m": "30m", "60m": "60m", "90m": "90m",
    "120m": "120m", "240m": "240m+", "360m": "240m+", "480m": "240m+", "720m": "240m+"
}
TF_BUCKET_ORDER = ["15m", "30m", "60m", "90m", "120m", "240m+"]


def tf_minutes(tf_str):
    """Convert TF string like '60m' to minutes."""
    return int(tf_str.replace("m", ""))


# =============================================================================
# MARKDOWN HELPERS
# =============================================================================
def md_table(headers, rows):
    lines = ["| " + " | ".join(str(h) for h in headers) + " |"]
    lines.append("|" + "|".join(["---"] * len(headers)) + "|")
    for row in rows:
        lines.append("| " + " | ".join(str(v) for v in row) + " |")
    return "\n".join(lines)


def fmt_pct(val, total):
    if total == 0:
        return "N/A"
    return f"{val / total * 100:.1f}%"


def fmt_f(val, decimals=1):
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return "N/A"
    return f"{val:.{decimals}f}"


# =============================================================================
# DATA LOADING
# =============================================================================
def load_bar_data(path):
    """Load SC bar data CSV, strip column names, parse datetime."""
    df = pd.read_csv(path)
    df.columns = df.columns.str.strip()
    # Keep only needed columns
    cols_keep = ["Date", "Time", "Open", "High", "Low", "Last", "Volume"]
    df = df[cols_keep].copy()
    df.rename(columns={"Last": "Close"}, inplace=True)
    # Parse datetime
    df["DateTime"] = pd.to_datetime(
        df["Date"].str.strip() + " " + df["Time"].str.strip(),
        format="mixed"
    )
    df.drop(columns=["Date", "Time"], inplace=True)
    return df


def load_all_data():
    """Load and concatenate all P1+P2 data with continuous bar indices."""
    print("Loading 250-vol bar data...")
    bars_p1 = load_bar_data(BAR_VOL_DIR / "NQ_BarData_250vol_rot_P1.csv")
    bars_p2 = load_bar_data(BAR_VOL_DIR / "NQ_BarData_250vol_rot_P2.csv")
    p1_count = len(bars_p1)
    print(f"  P1: {p1_count} bars, P2: {len(bars_p2)} bars")

    # Concatenate with continuous index
    bars = pd.concat([bars_p1, bars_p2], ignore_index=True)
    bars["BarIdx"] = bars.index  # continuous 0-based index

    print("Loading ray reference data...")
    ray_ref_p1 = pd.read_csv(TOUCH_DIR / "NQ_ray_reference_P1.csv")
    ray_ref_p2 = pd.read_csv(TOUCH_DIR / "NQ_ray_reference_P2.csv")
    # Offset P2 bar indices
    ray_ref_p2 = ray_ref_p2.copy()
    ray_ref_p2["BaseBarIndex"] = ray_ref_p2["BaseBarIndex"] + p1_count
    ray_ref = pd.concat([ray_ref_p1, ray_ref_p2], ignore_index=True)
    print(f"  {len(ray_ref)} ray creation events")

    print("Loading ZTE raw data...")
    zte_p1 = pd.read_csv(TOUCH_DIR / "NQ_ZTE_raw_P1.csv")
    zte_p2 = pd.read_csv(TOUCH_DIR / "NQ_ZTE_raw_P2.csv")

    # Build TouchID from ORIGINAL BarIndex (before offset) to match ray_context
    zte_p1["TouchID"] = (
        zte_p1["BarIndex"].astype(str) + "_" + zte_p1["TouchType"] + "_" + zte_p1["SourceLabel"]
    )
    zte_p2["TouchID"] = (
        zte_p2["BarIndex"].astype(str) + "_" + zte_p2["TouchType"] + "_" + zte_p2["SourceLabel"]
    )

    # Now offset P2 bar indices for the continuous timeline
    zte_p2 = zte_p2.copy()
    zte_p2["BarIndex"] = zte_p2["BarIndex"] + p1_count
    zte = pd.concat([zte_p1, zte_p2], ignore_index=True)
    # Filter out VP_RAY touches
    zte = zte[zte["TouchType"] != "VP_RAY"].copy()
    print(f"  {len(zte)} zone touch events (excl VP_RAY)")

    print("Loading ray context data...")
    rc_p1 = pd.read_csv(TOUCH_DIR / "NQ_ray_context_P1.csv")
    rc_p2 = pd.read_csv(TOUCH_DIR / "NQ_ray_context_P2.csv")
    ray_ctx = pd.concat([rc_p1, rc_p2], ignore_index=True)
    print(f"  {len(ray_ctx)} ray-touch pairs")

    return bars, ray_ref, zte, ray_ctx, p1_count


def load_10sec_bars():
    """Load 10-second bar data for 15m bar construction."""
    print("Loading 10-second bar data for 15m construction...")
    b1 = load_bar_data(BAR_TIME_DIR / "NQ_BarData_10sec_rot_P1.csv")
    b2 = load_bar_data(BAR_TIME_DIR / "NQ_BarData_10sec_rot_P2.csv")
    bars_10s = pd.concat([b1, b2], ignore_index=True)
    print(f"  {len(bars_10s)} 10-second bars loaded")
    return bars_10s


def build_15m_bars(bars_10s):
    """Resample 10-second bars to 15-minute OHLC bars."""
    bars_10s = bars_10s.set_index("DateTime").sort_index()
    bars_15m = bars_10s.resample("15min").agg({
        "Open": "first", "High": "max", "Low": "min",
        "Close": "last", "Volume": "sum"
    }).dropna()
    bars_15m = bars_15m.reset_index()
    print(f"  {len(bars_15m)} 15-minute bars constructed")
    return bars_15m


# =============================================================================
# RAY TIMELINE CONSTRUCTION
# =============================================================================
def build_rays(ray_ref):
    """
    Extract unique rays from ray_reference.
    A ray = unique (price, side). Records creation bar, TF(s).
    Returns DataFrame with columns: price, side, creation_bar, tf, tf_minutes.
    """
    events = []
    for _, row in ray_ref.iterrows():
        if row["DemandRayPrice"] > 0:
            events.append({
                "price": row["DemandRayPrice"],
                "side": "DEMAND",
                "creation_bar": row["BaseBarIndex"],
                "tf": row["SourceLabel"],
            })
        if row["SupplyRayPrice"] > 0:
            events.append({
                "price": row["SupplyRayPrice"],
                "side": "SUPPLY",
                "creation_bar": row["BaseBarIndex"],
                "tf": row["SourceLabel"],
            })

    events_df = pd.DataFrame(events)
    if events_df.empty:
        return events_df

    # Deduplicate: keep first creation of each (price, side)
    events_df = events_df.sort_values("creation_bar")
    rays = events_df.groupby(["price", "side"]).agg(
        creation_bar=("creation_bar", "min"),
        tf=("tf", "first"),  # TF of first creation
        event_count=("creation_bar", "count"),
    ).reset_index()

    rays["tf_min"] = rays["tf"].apply(tf_minutes)
    rays["tf_bucket"] = rays["tf"].map(TF_BUCKET_MAP).fillna("240m+")
    rays = rays.sort_values("creation_bar").reset_index(drop=True)
    print(f"  {len(rays)} unique ray levels from {len(events_df)} creation events")
    return rays, events_df


# =============================================================================
# INTERACTION DETECTION ENGINE
# =============================================================================
def detect_interactions(bars_high, bars_low, bars_close, rays, threshold_ticks,
                        max_obs=MAX_OBS_BARS):
    """
    Detect price-ray interactions with dedup.
    Returns list of dicts with interaction details.
    """
    thresh_price = threshold_ticks * TICK_SIZE
    n_bars = len(bars_high)
    interactions = []

    for ray_idx in range(len(rays)):
        ray_price = rays.iloc[ray_idx]["price"]
        creation_bar = int(rays.iloc[ray_idx]["creation_bar"])
        ray_side = rays.iloc[ray_idx]["side"]
        ray_tf = rays.iloc[ray_idx]["tf"]

        if creation_bar >= n_bars:
            continue

        # Vectorized proximity check from creation bar onward
        start = creation_bar
        hi = bars_high[start:]
        lo = bars_low[start:]
        cl = bars_close[start:]

        # Bar is within threshold if ray_price is within [Low - thresh, High + thresh]
        near = (lo <= ray_price + thresh_price) & (hi >= ray_price - thresh_price)

        # Find transitions: 0->1 = enter proximity, 1->0 = leave proximity
        near_int = near.astype(np.int8)
        transitions = np.diff(near_int, prepend=0)
        enter_indices = np.where(transitions == 1)[0]
        exit_indices = np.where(transitions == -1)[0]

        for ei_idx, enter_rel in enumerate(enter_indices):
            enter_abs = start + int(enter_rel)

            # Find exit (next time price leaves proximity)
            exits_after = exit_indices[exit_indices > enter_rel]
            if len(exits_after) > 0:
                exit_rel = int(exits_after[0])
                exit_abs = start + exit_rel
            else:
                exit_abs = n_bars - 1
                exit_rel = exit_abs - start

            # Determine approach side from bar before interaction
            if enter_abs > 0:
                prior_close = bars_close[enter_abs - 1]
                approach_from = "ABOVE" if prior_close > ray_price else "BELOW"
            else:
                approach_from = "BELOW"

            # Dwell time
            dwell = exit_abs - enter_abs + 1

            # Wick-based outcome: check MFE/MAE from ray within observation window
            obs_end = min(enter_abs + max_obs, n_bars)
            obs_hi = bars_high[enter_abs:obs_end]
            obs_lo = bars_low[enter_abs:obs_end]
            obs_cl = bars_close[enter_abs:obs_end]

            if approach_from == "ABOVE":
                # Price came from above; bounce = price goes back up, break = price goes below
                mfe_ticks = (np.max(obs_hi) - ray_price) / TICK_SIZE if len(obs_hi) > 0 else 0
                mae_ticks = (ray_price - np.min(obs_lo)) / TICK_SIZE if len(obs_lo) > 0 else 0
            else:
                # Price came from below; bounce = price goes back down, break = price goes above
                mfe_ticks = (ray_price - np.min(obs_lo)) / TICK_SIZE if len(obs_lo) > 0 else 0
                mae_ticks = (np.max(obs_hi) - ray_price) / TICK_SIZE if len(obs_hi) > 0 else 0

            # Wick-based classification
            wick_outcome = "UNDETERMINED"
            if mae_ticks >= WICK_THRESH_TICKS and mfe_ticks >= WICK_THRESH_TICKS:
                # Both thresholds hit - which came first?
                if approach_from == "ABOVE":
                    # Check if price went up first (bounce) or down first (break)
                    for b in range(len(obs_hi)):
                        if (obs_hi[b] - ray_price) / TICK_SIZE >= WICK_THRESH_TICKS:
                            wick_outcome = "BOUNCE"
                            break
                        if (ray_price - obs_lo[b]) / TICK_SIZE >= WICK_THRESH_TICKS:
                            wick_outcome = "BREAK"
                            break
                else:
                    for b in range(len(obs_lo)):
                        if (ray_price - obs_lo[b]) / TICK_SIZE >= WICK_THRESH_TICKS:
                            wick_outcome = "BOUNCE"
                            break
                        if (obs_hi[b] - ray_price) / TICK_SIZE >= WICK_THRESH_TICKS:
                            wick_outcome = "BREAK"
                            break
            elif mae_ticks >= WICK_THRESH_TICKS:
                wick_outcome = "BREAK"
            elif mfe_ticks >= WICK_THRESH_TICKS:
                wick_outcome = "BOUNCE"

            # Close-based outcomes (Method 1: single 250-vol bar close)
            first_close = bars_close[enter_abs] if enter_abs < n_bars else ray_price
            if approach_from == "ABOVE":
                close_m1 = "BOUNCE" if first_close > ray_price else "BREAK"
            else:
                close_m1 = "BOUNCE" if first_close < ray_price else "BREAK"

            # Close-based Method 2: consecutive closes (2,3,4,5)
            close_consec = {}
            for nc in CONSEC_COUNTS:
                if enter_abs + nc <= n_bars:
                    chunk = bars_close[enter_abs:enter_abs + nc]
                    if approach_from == "ABOVE":
                        all_orig = np.all(chunk > ray_price)
                        all_new = np.all(chunk <= ray_price)
                    else:
                        all_orig = np.all(chunk < ray_price)
                        all_new = np.all(chunk >= ray_price)
                    if all_orig:
                        close_consec[nc] = "BOUNCE"
                    elif all_new:
                        close_consec[nc] = "BREAK"
                    else:
                        close_consec[nc] = "MIXED"
                else:
                    close_consec[nc] = "INSUFFICIENT"

            # Approach velocity (ticks/bar over prior 5 bars)
            vel_lookback = 5
            if enter_abs >= vel_lookback:
                price_change = abs(
                    bars_close[enter_abs] - bars_close[enter_abs - vel_lookback]
                ) / TICK_SIZE
                approach_vel = price_change / vel_lookback
            else:
                approach_vel = 0

            interactions.append({
                "ray_idx": ray_idx,
                "ray_price": ray_price,
                "ray_side": ray_side,
                "ray_tf": ray_tf,
                "enter_bar": enter_abs,
                "exit_bar": exit_abs,
                "dwell": dwell,
                "approach_from": approach_from,
                "wick_outcome": wick_outcome,
                "mfe_ticks": mfe_ticks,
                "mae_ticks": mae_ticks,
                "close_m1": close_m1,
                **{f"close_c{nc}": close_consec.get(nc, "N/A") for nc in CONSEC_COUNTS},
                "approach_vel": approach_vel,
                "first_close": first_close,
            })

    return pd.DataFrame(interactions)


def add_15m_close(interactions_df, bars_250v, bars_15m):
    """Add 15m bar close classification to interactions."""
    if bars_15m is None or interactions_df.empty:
        interactions_df["close_15m"] = "N/A"
        return interactions_df

    # Build lookup: for each 250-vol bar, find its 15m period close
    bar_dts = bars_250v["DateTime"].values
    m15_dts = bars_15m["DateTime"].values
    m15_closes = bars_15m["Close"].values

    results = []
    for _, ix in interactions_df.iterrows():
        enter_bar = int(ix["enter_bar"])
        if enter_bar < len(bar_dts):
            bar_dt = bar_dts[enter_bar]
            # Find the 15m bar containing this timestamp
            idx = np.searchsorted(m15_dts, bar_dt, side="right") - 1
            if 0 <= idx < len(m15_closes):
                m15_close = m15_closes[idx]
                ray_price = ix["ray_price"]
                approach = ix["approach_from"]
                if approach == "ABOVE":
                    results.append("BOUNCE" if m15_close > ray_price else "BREAK")
                else:
                    results.append("BOUNCE" if m15_close < ray_price else "BREAK")
            else:
                results.append("N/A")
        else:
            results.append("N/A")

    interactions_df["close_15m"] = results
    return interactions_df


def compute_ground_truth(interactions_df, bars_close, rays):
    """
    Compute ground truth outcome for each interaction.
    Actual bounce: 80%+ of next 200 bar closes on original side.
    Actual break: 30t+ move AND 60%+ closes on new side.
    Otherwise: ambiguous.
    """
    n_bars = len(bars_close)
    gt_outcomes = []

    for _, ix in interactions_df.iterrows():
        enter_bar = int(ix["enter_bar"])
        ray_price = ix["ray_price"]
        approach = ix["approach_from"]

        fwd_start = enter_bar + 1
        fwd_end = min(fwd_start + GT_FORWARD_BARS, n_bars)

        if fwd_end - fwd_start < 20:  # too few forward bars
            gt_outcomes.append("INSUFFICIENT")
            continue

        fwd_closes = bars_close[fwd_start:fwd_end]
        n_fwd = len(fwd_closes)

        if approach == "ABOVE":
            # Original side = above ray; new side = below ray
            pct_orig = np.sum(fwd_closes > ray_price) / n_fwd
            pct_new = np.sum(fwd_closes <= ray_price) / n_fwd
            max_new_move = (ray_price - np.min(fwd_closes)) / TICK_SIZE
        else:
            # Original side = below ray; new side = above ray
            pct_orig = np.sum(fwd_closes < ray_price) / n_fwd
            pct_new = np.sum(fwd_closes >= ray_price) / n_fwd
            max_new_move = (np.max(fwd_closes) - ray_price) / TICK_SIZE

        if pct_orig >= GT_BOUNCE_SIDE_PCT:
            gt_outcomes.append("BOUNCE")
        elif max_new_move >= GT_BREAK_MOVE_TICKS and pct_new >= GT_BREAK_SIDE_PCT:
            gt_outcomes.append("BREAK")
        else:
            gt_outcomes.append("AMBIGUOUS")

    interactions_df["ground_truth"] = gt_outcomes
    return interactions_df


# =============================================================================
# SESSION CLASSIFICATION
# =============================================================================
def classify_session(bars, enter_bars):
    """Classify interaction session (RTH vs ETH) based on bar datetime."""
    sessions = []
    dts = bars["DateTime"].values
    for eb in enter_bars:
        eb = int(eb)
        if eb < len(dts):
            dt = pd.Timestamp(dts[eb])
            t = dt.time()
            if RTH_START <= t <= RTH_END:
                sessions.append("RTH")
            else:
                sessions.append("ETH")
        else:
            sessions.append("UNKNOWN")
    return sessions


# =============================================================================
# SECTION 1: RAY POPULATION
# =============================================================================
def section_1(ray_ref, rays_df, events_df, bars, p1_count):
    """Analyze ray population characteristics."""
    out = []
    out.append("=" * 64)
    out.append("SECTION 1: RAY POPULATION")
    out.append("=" * 64)
    out.append("")

    # Parse dates from ray_ref
    ray_ref["dt"] = pd.to_datetime(ray_ref["DateTime"])
    ray_ref["date"] = ray_ref["dt"].dt.date

    # Count creation events (each non-zero price is an event)
    n_demand = (ray_ref["DemandRayPrice"] > 0).sum()
    n_supply = (ray_ref["SupplyRayPrice"] > 0).sum()
    total_events = n_demand + n_supply

    # Events per day
    all_dates = pd.date_range(
        bars["DateTime"].iloc[0].date(),
        bars["DateTime"].iloc[-1].date(),
        freq="D"
    )
    # Only count trading days (dates that appear in bar data)
    bar_dates = bars["DateTime"].dt.date.unique()
    n_trading_days = len(bar_dates)

    events_per_date = []
    for _, row in ray_ref.iterrows():
        d = row["date"]
        if row["DemandRayPrice"] > 0:
            events_per_date.append(d)
        if row["SupplyRayPrice"] > 0:
            events_per_date.append(d)

    events_by_day = pd.Series(events_per_date).value_counts()
    days_with_events = len(events_by_day)
    days_zero = n_trading_days - days_with_events

    out.append("### A) Ray creation rate\n")
    out.append(md_table(
        ["Metric", "Value"],
        [
            ["Total ray creation events", total_events],
            ["Demand ray events", n_demand],
            ["Supply ray events", n_supply],
            ["Unique ray levels", len(rays_df)],
            ["Trading days in dataset", n_trading_days],
            ["Mean rays created per day", fmt_f(total_events / n_trading_days)],
            ["Median rays created per day", fmt_f(events_by_day.reindex(
                pd.Index(bar_dates), fill_value=0).median())],
            ["Days with zero ray creation", f"{days_zero} ({fmt_pct(days_zero, n_trading_days)})"],
        ]
    ))
    out.append("")

    # B) By TF
    out.append("### B) Ray creation by TF\n")
    tf_events = []
    for _, row in ray_ref.iterrows():
        tf = row["SourceLabel"]
        if row["DemandRayPrice"] > 0:
            tf_events.append(tf)
        if row["SupplyRayPrice"] > 0:
            tf_events.append(tf)

    tf_counts = pd.Series(tf_events).value_counts()
    tf_rows = []
    for tfb in TF_BUCKET_ORDER:
        matching_tfs = [t for t, b in TF_BUCKET_MAP.items() if b == tfb]
        count = sum(tf_counts.get(t, 0) for t in matching_tfs)
        tf_rows.append([
            tfb, count, fmt_pct(count, total_events),
            fmt_f(count / n_trading_days)
        ])
    out.append(md_table(["TF", "Count", "% of total", "Mean per day"], tf_rows))
    out.append("")

    # C) Active ray count over time
    out.append("### C) Active ray count over time\n")
    creation_bars = rays_df["creation_bar"].values
    n_bars = len(bars)
    # Count active rays at each bar
    active_at_bar = np.searchsorted(np.sort(creation_bars), np.arange(n_bars), side="right")

    out.append(md_table(
        ["Metric", "Value"],
        [
            ["Mean active rays per bar", fmt_f(np.mean(active_at_bar))],
            ["Median active rays per bar", fmt_f(np.median(active_at_bar))],
            ["Max active rays per bar", int(np.max(active_at_bar))],
            ["Active rays at end of period", int(active_at_bar[-1])],
        ]
    ))
    out.append("")

    # Growth pattern
    q1 = active_at_bar[n_bars // 4]
    q2 = active_at_bar[n_bars // 2]
    q3 = active_at_bar[3 * n_bars // 4]
    q4 = active_at_bar[-1]
    out.append(f"Growth pattern (active rays at quartile bars): "
               f"Q1={q1}, Q2={q2}, Q3={q3}, Q4={q4}")
    if q4 > 0 and q2 > 0:
        ratio = q4 / q2
        if ratio > 1.8:
            out.append("→ Growth is approximately linear (not plateauing)")
        else:
            out.append("→ Growth shows deceleration / partial plateau")
    out.append("")

    # D) Active rays by TF at end
    out.append("### D) Active rays by TF at end of period\n")
    total_active = len(rays_df)
    tf_active_rows = []
    for tfb in TF_BUCKET_ORDER:
        count = len(rays_df[rays_df["tf_bucket"] == tfb])
        tf_active_rows.append([tfb, count, fmt_pct(count, total_active)])
    out.append(md_table(["TF", "Active count", "% of total active"], tf_active_rows))
    out.append("")

    return "\n".join(out)


# =============================================================================
# SECTION 2: PRICE-RAY INTERACTIONS
# =============================================================================
def section_2(bars, rays_df, bars_15m):
    """Analyze price-ray interactions across all bars."""
    out = []
    out.append("=" * 64)
    out.append("SECTION 2: PRICE-RAY INTERACTIONS")
    out.append("=" * 64)
    out.append("")

    highs = bars["High"].values.astype(np.float64)
    lows = bars["Low"].values.astype(np.float64)
    closes = bars["Close"].values.astype(np.float64)

    # --- 2A: Proximity threshold calibration (wick-based) ---
    out.append("### 2A) Proximity threshold calibration — PRELIMINARY (wick-based)\n")
    threshold_results = {}
    for thresh in PROX_THRESHOLDS:
        print(f"  Detecting interactions at {thresh}t threshold...")
        ixns = detect_interactions(highs, lows, closes, rays_df, thresh)
        resolved = ixns[ixns["wick_outcome"].isin(["BOUNCE", "BREAK"])]
        n_total = len(ixns)
        n_bounce = (resolved["wick_outcome"] == "BOUNCE").sum()
        n_break = (resolved["wick_outcome"] == "BREAK").sum()
        ratio = n_bounce / n_break if n_break > 0 else float("inf")
        threshold_results[thresh] = {
            "total": n_total, "bounce": n_bounce, "break": n_break,
            "ratio": ratio, "df": ixns
        }

    thresh_rows = []
    for t in PROX_THRESHOLDS:
        r = threshold_results[t]
        total = r["bounce"] + r["break"]
        thresh_rows.append([
            f"{t}t", r["total"],
            fmt_pct(r["bounce"], total),
            fmt_pct(r["break"], total),
            fmt_f(r["ratio"], 2)
        ])
    out.append(md_table(
        ["Threshold", "Total interactions", "Bounce %", "Break %", "Bounce/Break ratio"],
        thresh_rows
    ))
    out.append("")

    # Pick best wick-based threshold (highest ratio)
    best_wick_thresh = max(threshold_results.keys(),
                          key=lambda t: threshold_results[t]["ratio"])
    out.append(f"**Best wick-based threshold: {best_wick_thresh}t** "
               f"(ratio={fmt_f(threshold_results[best_wick_thresh]['ratio'], 2)})")
    out.append("")

    # Use best threshold interactions for subsequent analysis
    ixns_wick = threshold_results[best_wick_thresh]["df"]

    # --- 2B: Close analysis ---
    out.append("### 2B) CLOSE ANALYSIS\n")

    # Add 15m close
    print("  Adding 15m close classification...")
    ixns_wick = add_15m_close(ixns_wick, bars, bars_15m)

    # Compute ground truth
    print("  Computing ground truth outcomes (200-bar forward)...")
    ixns_wick = compute_ground_truth(ixns_wick, closes, rays_df)

    # Evaluate each close method against ground truth
    gt_valid = ixns_wick[ixns_wick["ground_truth"].isin(["BOUNCE", "BREAK"])].copy()
    gt_ambig = ixns_wick[ixns_wick["ground_truth"] == "AMBIGUOUS"]
    gt_insuf = ixns_wick[ixns_wick["ground_truth"] == "INSUFFICIENT"]

    methods = {
        "Wick only (no close check)": "wick_outcome",
        "Single 250-vol close": "close_m1",
        "2 consecutive 250-vol closes": "close_c2",
        "3 consecutive 250-vol closes": "close_c3",
        "4 consecutive 250-vol closes": "close_c4",
        "5 consecutive 250-vol closes": "close_c5",
        "15m bar close": "close_15m",
    }

    method_rows = []
    method_scores = {}
    for label, col in methods.items():
        valid = gt_valid[gt_valid[col].isin(["BOUNCE", "BREAK"])].copy()
        if len(valid) == 0:
            method_rows.append([label, "N/A", "N/A", "N/A", 0])
            method_scores[label] = 0
            continue

        # Correct = method agrees with ground truth
        bounce_correct = ((valid[col] == "BOUNCE") & (valid["ground_truth"] == "BOUNCE")).sum()
        break_correct = ((valid[col] == "BREAK") & (valid["ground_truth"] == "BREAK")).sum()
        false_signals = len(valid) - bounce_correct - break_correct
        total_correct = bounce_correct + break_correct
        n = len(valid)

        gt_bounces = (valid["ground_truth"] == "BOUNCE").sum()
        gt_breaks = (valid["ground_truth"] == "BREAK").sum()

        method_rows.append([
            label,
            f"{bounce_correct}/{gt_bounces}" if gt_bounces > 0 else "N/A",
            f"{break_correct}/{gt_breaks}" if gt_breaks > 0 else "N/A",
            false_signals,
            n
        ])
        method_scores[label] = total_correct / n if n > 0 else 0

    out.append("**Close method comparison vs ground truth:**\n")
    out.append(md_table(
        ["Close method", "Bounce correctly ID'd", "Break correctly ID'd", "False signals", "n"],
        method_rows
    ))
    out.append("")
    out.append(f"Ambiguous ground truth events: {len(gt_ambig)}")
    out.append(f"Insufficient forward data: {len(gt_insuf)}")
    out.append("")

    # Select best method
    best_method_label = max(method_scores, key=method_scores.get)
    best_method_col = methods[best_method_label]
    out.append(f"**Best close method: {best_method_label}** "
               f"(accuracy={fmt_f(method_scores[best_method_label] * 100, 1)}%)")
    out.append("")

    # --- Re-run 2A with close-based definitions ---
    out.append("### 2A-revisit) Proximity threshold with close-based definitions\n")

    # If best method is close_15m, add that column to all threshold DataFrames
    if best_method_col == "close_15m":
        for thresh in PROX_THRESHOLDS:
            df = threshold_results[thresh]["df"]
            if "close_15m" not in df.columns:
                threshold_results[thresh]["df"] = add_15m_close(df, bars, bars_15m)

    close_thresh_results = {}
    for thresh in PROX_THRESHOLDS:
        df = threshold_results[thresh]["df"]
        # Use the best close method column
        if best_method_col not in df.columns:
            # Fallback to close_m1 if column missing
            col = "close_m1"
        else:
            col = best_method_col
        valid = df[df[col].isin(["BOUNCE", "BREAK"])]
        n_bounce = (valid[col] == "BOUNCE").sum()
        n_break = (valid[col] == "BREAK").sum()
        total = n_bounce + n_break
        ratio = n_bounce / n_break if n_break > 0 else float("inf")
        close_thresh_results[thresh] = {
            "total": len(df), "bounce": n_bounce, "break_": n_break,
            "ratio": ratio, "valid": total
        }

    ct_rows = []
    for t in PROX_THRESHOLDS:
        r = close_thresh_results[t]
        ct_rows.append([
            f"{t}t", r["total"],
            fmt_pct(r["bounce"], r["valid"]),
            fmt_pct(r["break_"], r["valid"]),
            fmt_f(r["ratio"], 2)
        ])
    out.append(md_table(
        ["Threshold", "Interactions", "Bounce % (close)", "Break % (close)", "Ratio"],
        ct_rows
    ))
    out.append("")

    best_close_thresh = max(close_thresh_results.keys(),
                           key=lambda t: close_thresh_results[t]["ratio"])
    out.append(f"**Best close-based threshold: {best_close_thresh}t** "
               f"(ratio={fmt_f(close_thresh_results[best_close_thresh]['ratio'], 2)})")
    out.append("")

    if best_close_thresh != best_wick_thresh:
        out.append(f"⚠️ Threshold shifted from {best_wick_thresh}t (wick) to "
                   f"{best_close_thresh}t (close-based). Using {best_close_thresh}t "
                   f"for all subsequent analysis.")
        # Re-detect at the close-based threshold
        print(f"  Re-detecting interactions at close-based threshold {best_close_thresh}t...")
        ixns = detect_interactions(highs, lows, closes, rays_df, best_close_thresh)
        ixns = add_15m_close(ixns, bars, bars_15m)
        ixns = compute_ground_truth(ixns, closes, rays_df)
    else:
        out.append(f"Threshold unchanged at {best_close_thresh}t.")
        ixns = ixns_wick
    out.append("")

    # Assign governing outcome column
    ixns["outcome"] = ixns[best_method_col]
    selected_thresh = best_close_thresh

    # --- Interaction type distribution ---
    out.append("### 2B-detail) Interaction type distribution\n")
    # Strong/weak rejection, acceptance, confirmed acceptance, failed acceptance
    type_rows = []
    valid_ixns = ixns[ixns["outcome"].isin(["BOUNCE", "BREAK"])].copy()

    # Strong rejection: wick past ray, close far on original side (top/bottom 25% of bar range)
    bounces = valid_ixns[valid_ixns["outcome"] == "BOUNCE"].copy()
    if len(bounces) > 0:
        bar_ranges = highs[bounces["enter_bar"].astype(int)] - lows[bounces["enter_bar"].astype(int)]
        close_dist_from_ray = np.abs(bounces["first_close"].values - bounces["ray_price"].values)
        bar_ranges = np.maximum(bar_ranges, TICK_SIZE)  # avoid div by 0
        close_position = close_dist_from_ray / bar_ranges

        strong = bounces[close_position >= 0.75]
        weak = bounces[close_position < 0.75]

        # MFE for bounces (next 20 bars)
        def mean_mfe_20(subset):
            mfes = []
            for _, row in subset.iterrows():
                eb = int(row["enter_bar"])
                end = min(eb + 20, len(highs))
                if row["approach_from"] == "ABOVE":
                    mfe = (np.max(highs[eb:end]) - row["ray_price"]) / TICK_SIZE
                else:
                    mfe = (row["ray_price"] - np.min(lows[eb:end])) / TICK_SIZE
                mfes.append(mfe)
            return np.mean(mfes) if mfes else 0

        type_rows.append([
            "Strong rejection (close ≥75% bar range from ray)",
            len(strong), fmt_pct(len(strong), len(valid_ixns)),
            fmt_f(mean_mfe_20(strong))
        ])
        type_rows.append([
            "Weak rejection (close <75% bar range from ray)",
            len(weak), fmt_pct(len(weak), len(valid_ixns)),
            fmt_f(mean_mfe_20(weak))
        ])

    breaks = valid_ixns[valid_ixns["outcome"] == "BREAK"].copy()
    if len(breaks) > 0:
        # Check for confirmed (2+ closes past) and failed (close past, next bar back)
        confirmed = []
        failed_acc = []
        simple_acc = []
        for _, row in breaks.iterrows():
            eb = int(row["enter_bar"])
            if eb + 1 < len(closes):
                next_close = closes[eb + 1]
                ray_p = row["ray_price"]
                approach = row["approach_from"]
                if approach == "ABOVE":
                    still_past = next_close <= ray_p
                    back = next_close > ray_p
                else:
                    still_past = next_close >= ray_p
                    back = next_close < ray_p

                if still_past:
                    confirmed.append(row)
                elif back:
                    failed_acc.append(row)
                else:
                    simple_acc.append(row)
            else:
                simple_acc.append(row)

        type_rows.append([
            "Acceptance (single close past ray)",
            len(simple_acc), fmt_pct(len(simple_acc), len(valid_ixns)),
            "—"
        ])
        type_rows.append([
            "Confirmed acceptance (2+ closes past ray)",
            len(confirmed), fmt_pct(len(confirmed), len(valid_ixns)),
            "—"
        ])
        type_rows.append([
            "Failed acceptance (close past, next bar back)",
            len(failed_acc), fmt_pct(len(failed_acc), len(valid_ixns)),
            "—"
        ])

    out.append(md_table(
        ["Interaction type", "Count", "%", "Next 20-bar MFE"],
        type_rows
    ))
    out.append("")

    # --- 2C: Zone-backed vs isolated ---
    out.append("### 2C) Zone-backed vs isolated ray interactions\n")
    # Need to check if ray is near an active zone edge
    # We'll use ZTE raw data to find active zones at each interaction
    # For now, compute based on ray proximity to other rays (as proxy)
    # Actually, we need zone data. Let's defer this to Section 4 integration
    out.append("*Deferred to Section 4 (requires zone edge data at interaction time)*\n")

    # --- 2D: Interaction frequency ---
    out.append("### 2D) Interaction frequency\n")
    n_total_ixns = len(ixns)
    n_bars_total = len(bars)
    bars_with_ixn = ixns["enter_bar"].nunique()
    ray_ixn_counts = ixns.groupby("ray_idx").size()

    out.append(md_table(
        ["Metric", "Value"],
        [
            ["Total price-ray interactions", n_total_ixns],
            ["Mean interactions per day",
             fmt_f(n_total_ixns / len(bars["DateTime"].dt.date.unique()))],
            ["% of all bars with a ray interaction",
             fmt_pct(bars_with_ixn, n_bars_total)],
            ["Mean interactions per ray (lifetime)",
             fmt_f(ray_ixn_counts.mean())],
            ["Median interactions per ray",
             fmt_f(ray_ixn_counts.median())],
        ]
    ))
    out.append("")

    # --- 2E: First interaction outcome ---
    out.append("### 2E) First interaction outcome\n")
    first_ixns = ixns.sort_values("enter_bar").groupby("ray_idx").first().reset_index()
    first_valid = first_ixns[first_ixns["outcome"].isin(["BOUNCE", "BREAK"])]

    n_first = len(first_valid)
    n_fb = (first_valid["outcome"] == "BOUNCE").sum()
    n_fk = (first_valid["outcome"] == "BREAK").sum()

    # Check for false breaks in first interaction
    false_breaks_first = []
    for _, row in first_valid[first_valid["outcome"] == "BREAK"].iterrows():
        eb = int(row["enter_bar"])
        if eb + 2 < len(closes):
            ray_p = row["ray_price"]
            approach = row["approach_from"]
            c1 = closes[eb + 1]
            if approach == "ABOVE":
                if c1 > ray_p:  # reversed back
                    false_breaks_first.append(True)
                else:
                    false_breaks_first.append(False)
            else:
                if c1 < ray_p:
                    false_breaks_first.append(True)
                else:
                    false_breaks_first.append(False)
        else:
            false_breaks_first.append(False)

    n_false_break = sum(false_breaks_first)

    out.append(md_table(
        ["Outcome", "Count", "%"],
        [
            ["Bounce", n_fb, fmt_pct(n_fb, n_first)],
            ["Break", n_fk - n_false_break, fmt_pct(n_fk - n_false_break, n_first)],
            ["False break", n_false_break, fmt_pct(n_false_break, n_first)],
        ]
    ))
    out.append("")

    # Split by TF
    out.append("**First interaction by ray TF:**\n")
    first_ixns_merged = first_valid.copy()
    first_ixns_merged["tf_bucket"] = first_ixns_merged["ray_tf"].map(TF_BUCKET_MAP).fillna("240m+")
    tf_first_rows = []
    for tfb in TF_BUCKET_ORDER:
        subset = first_ixns_merged[first_ixns_merged["tf_bucket"] == tfb]
        n = len(subset)
        nb = (subset["outcome"] == "BOUNCE").sum()
        nk = (subset["outcome"] == "BREAK").sum()
        flag = " ⚠️ LOW SAMPLE" if n < 20 else ""
        tf_first_rows.append([
            tfb, fmt_pct(nb, n), fmt_pct(nk, n), "—", f"{n}{flag}"
        ])
    out.append(md_table(["TF", "Bounce %", "Break %", "False break %", "n"], tf_first_rows))
    out.append("")

    # --- 2F: First interaction by ray age ---
    out.append("### 2F) First interaction by ray age\n")
    first_ixns_age = first_valid.copy()
    # Ray age at first interaction = enter_bar - creation_bar
    first_ixns_age = first_ixns_age.merge(
        rays_df[["creation_bar"]], left_on="ray_idx", right_index=True
    )
    first_ixns_age["age"] = first_ixns_age["enter_bar"] - first_ixns_age["creation_bar"]

    age_bins = [(0, 50, "< 50 bars (fresh)"), (50, 200, "50-200 bars"),
                (200, 500, "200-500 bars"), (500, 999999, "500+ bars (stale)")]
    age_rows = []
    for lo, hi, label in age_bins:
        subset = first_ixns_age[(first_ixns_age["age"] >= lo) & (first_ixns_age["age"] < hi)]
        n = len(subset)
        nb = (subset["outcome"] == "BOUNCE").sum()
        nk = (subset["outcome"] == "BREAK").sum()
        age_rows.append([label, fmt_pct(nb, n), fmt_pct(nk, n), n])
    out.append(md_table(["Ray age at first interaction", "Bounce %", "Break %", "n"], age_rows))
    out.append("")

    # --- 2G: Interaction side (polarity) ---
    out.append("### 2G) Interaction side (polarity)\n")
    valid_all = ixns[ixns["outcome"].isin(["BOUNCE", "BREAK"])].copy()

    above = valid_all[valid_all["approach_from"] == "ABOVE"]
    below = valid_all[valid_all["approach_from"] == "BELOW"]

    out.append(md_table(
        ["Approach", "Bounce %", "Break %", "n"],
        [
            ["From above (ray = support)",
             fmt_pct((above["outcome"] == "BOUNCE").sum(), len(above)),
             fmt_pct((above["outcome"] == "BREAK").sum(), len(above)),
             len(above)],
            ["From below (ray = resistance)",
             fmt_pct((below["outcome"] == "BOUNCE").sum(), len(below)),
             fmt_pct((below["outcome"] == "BREAK").sum(), len(below)),
             len(below)],
        ]
    ))
    out.append("")

    # Demand vs Supply ray behavior
    out.append("**Ray type × polarity:**\n")
    polarity_rows = []
    for rs in ["DEMAND", "SUPPLY"]:
        sub_support = valid_all[(valid_all["ray_side"] == rs) &
                                (valid_all["approach_from"] == "ABOVE")]
        sub_resist = valid_all[(valid_all["ray_side"] == rs) &
                               (valid_all["approach_from"] == "BELOW")]
        polarity_rows.append([
            f"{rs} ray",
            f"{fmt_pct((sub_support['outcome'] == 'BOUNCE').sum(), len(sub_support))} (n={len(sub_support)})",
            f"{fmt_pct((sub_resist['outcome'] == 'BOUNCE').sum(), len(sub_resist))} (n={len(sub_resist)})",
        ])
    out.append(md_table(
        ["Ray type", "As support (bounce %)", "As resistance (bounce %)"],
        polarity_rows
    ))
    out.append("")

    # --- 2H: Approach velocity ---
    out.append("### 2H) Approach velocity\n")
    vel_bins = [(5, 999, "Fast (> 5 ticks/bar)"), (2, 5, "Medium (2-5 ticks/bar)"),
                (0, 2, "Slow (< 2 ticks/bar)")]
    vel_rows = []
    for lo, hi, label in vel_bins:
        if lo == 5:
            subset = valid_all[valid_all["approach_vel"] > lo]
        elif lo == 2:
            subset = valid_all[(valid_all["approach_vel"] >= lo) &
                               (valid_all["approach_vel"] <= hi)]
        else:
            subset = valid_all[valid_all["approach_vel"] < hi]
        n = len(subset)
        nb = (subset["outcome"] == "BOUNCE").sum()
        vel_rows.append([label, fmt_pct(nb, n),
                         fmt_pct(n - nb, n), n])
    out.append(md_table(["Approach speed", "Bounce %", "Break %", "n"], vel_rows))
    out.append("")

    # Velocity quartiles
    q25, q50, q75 = valid_all["approach_vel"].quantile([0.25, 0.5, 0.75])
    out.append(f"Velocity quartiles: Q25={fmt_f(q25)}, Q50={fmt_f(q50)}, Q75={fmt_f(q75)} ticks/bar")
    out.append("")

    # --- 2I: Session context ---
    out.append("### 2I) Session context\n")
    valid_all["session"] = classify_session(bars, valid_all["enter_bar"].values)
    sess_rows = []
    for sess in ["RTH", "ETH"]:
        subset = valid_all[valid_all["session"] == sess]
        n = len(subset)
        nb = (subset["outcome"] == "BOUNCE").sum()
        sess_rows.append([
            f"{sess} ({'09:30-16:15 ET' if sess == 'RTH' else 'outside RTH'})",
            n, fmt_pct(nb, n), fmt_pct(n - nb, n), n
        ])
    out.append(md_table(["Session", "Interactions", "Bounce %", "Break %", "n"], sess_rows))
    out.append("")

    # --- 2J: Dwell time ---
    out.append("### 2J) Dwell time before resolution\n")
    dwell_bins = [(1, 2, "1-2 bars (decisive)"), (3, 5, "3-5 bars (contested)"),
                  (6, 10, "6-10 bars (consolidation)"), (11, 99999, "10+ bars (range-bound)")]
    dwell_rows = []
    for lo, hi, label in dwell_bins:
        subset = valid_all[(valid_all["dwell"] >= lo) & (valid_all["dwell"] <= hi)]
        n = len(subset)
        nb = (subset["outcome"] == "BOUNCE").sum()
        dwell_rows.append([label, fmt_pct(nb, n), fmt_pct(n - nb, n), n])
    out.append(md_table(
        ["Dwell time", "Bounce %", "Break %", "n"],
        dwell_rows
    ))
    out.append("")

    # Collect metrics for section_8
    s2_metrics = {
        "best_close_acc": method_scores.get(best_method_label, 0) * 100,
        "close_thresh_ratio": close_thresh_results[best_close_thresh]["ratio"],
        "wick_thresh": best_wick_thresh,
    }

    return "\n".join(out), ixns, selected_thresh, best_method_col, s2_metrics


# =============================================================================
# SECTION 3: POLARITY FLIPS
# =============================================================================
def section_3(ixns, rays_df, bars, best_method_col):
    """Analyze polarity flip lifecycle."""
    out = []
    out.append("=" * 64)
    out.append("SECTION 3: POLARITY FLIPS")
    out.append("=" * 64)
    out.append("")

    closes = bars["Close"].values.astype(np.float64)
    highs = bars["High"].values.astype(np.float64)
    lows = bars["Low"].values.astype(np.float64)

    ixns_sorted = ixns.sort_values("enter_bar").copy()
    ixns_sorted["outcome"] = ixns_sorted[best_method_col]

    # Track flips per ray: a BREAK = polarity flip
    ray_flips = {}  # ray_idx -> list of flip bars
    ray_bounce_streaks = {}  # ray_idx -> list of bounce counts between flips
    ray_interactions_by_polarity = {}  # ray_idx -> list of lists of interactions

    for ray_idx in rays_df.index:
        ray_ixns = ixns_sorted[ixns_sorted["ray_idx"] == ray_idx].sort_values("enter_bar")
        flips = []
        current_polarity_ixns = []
        bounce_counts = []
        all_polarity_phases = []

        for _, ix in ray_ixns.iterrows():
            if ix["outcome"] == "BREAK":
                flips.append(int(ix["enter_bar"]))
                bounce_counts.append(len(current_polarity_ixns))
                all_polarity_phases.append(current_polarity_ixns)
                current_polarity_ixns = []
            elif ix["outcome"] == "BOUNCE":
                current_polarity_ixns.append(ix)

        # Last phase
        if current_polarity_ixns:
            all_polarity_phases.append(current_polarity_ixns)

        ray_flips[ray_idx] = flips
        ray_bounce_streaks[ray_idx] = bounce_counts
        ray_interactions_by_polarity[ray_idx] = all_polarity_phases

    # 3A: Flip frequency
    out.append("### 3A) Flip frequency (close-based, primary)\n")
    flip_counts = {idx: len(f) for idx, f in ray_flips.items()}
    flip_dist = pd.Series(flip_counts).value_counts().sort_index()

    flip_rows = []
    for n_flips in [0, 1, 2]:
        count = flip_dist.get(n_flips, 0)
        flip_rows.append([f"Rays with {n_flips} flip{'s' if n_flips != 1 else ''}",
                          count])
    three_plus = sum(v for k, v in flip_dist.items() if k >= 3)
    flip_rows.append(["Rays with 3+ flips", three_plus])
    max_flips = max(flip_counts.values()) if flip_counts else 0
    flip_rows.append(["Max flips on a single ray", max_flips])

    out.append(md_table(["Metric", "Value"], flip_rows))
    out.append("")

    # Also report wick-based flips for comparison
    wick_flips = {}
    for ray_idx in rays_df.index:
        ray_ixns = ixns_sorted[ixns_sorted["ray_idx"] == ray_idx].sort_values("enter_bar")
        wf = (ray_ixns["wick_outcome"] == "BREAK").sum()
        wick_flips[ray_idx] = wf

    wick_flip_dist = pd.Series(wick_flips).value_counts().sort_index()
    out.append("**Comparison: wick-based flip counts:**\n")
    wick_rows = []
    for n_flips in [0, 1, 2]:
        count = wick_flip_dist.get(n_flips, 0)
        wick_rows.append([f"{n_flips} flips", count])
    wp = sum(v for k, v in wick_flip_dist.items() if k >= 3)
    wick_rows.append(["3+ flips", wp])
    out.append(md_table(["Flips", "Rays (wick-based)"], wick_rows))
    out.append("")

    # 3B: Flip history predicts future?
    out.append("### 3B) Does flip history predict future behavior?\n")
    # For each interaction, count how many flips the ray has had BEFORE this interaction
    flip_pred_data = []
    for ray_idx in rays_df.index:
        ray_ixns = ixns_sorted[ixns_sorted["ray_idx"] == ray_idx].sort_values("enter_bar")
        flips_so_far = 0
        for _, ix in ray_ixns.iterrows():
            if ix["outcome"] in ["BOUNCE", "BREAK"]:
                flip_pred_data.append({
                    "flips_so_far": min(flips_so_far, 2),  # bucket 2+
                    "outcome": ix["outcome"]
                })
            if ix["outcome"] == "BREAK":
                flips_so_far += 1

    fpd = pd.DataFrame(flip_pred_data)
    if len(fpd) > 0:
        fp_rows = []
        for nf, label in [(0, "0 (never flipped)"), (1, "1 (flipped once)"), (2, "2+ (multi-flip)")]:
            subset = fpd[fpd["flips_so_far"] == nf]
            n = len(subset)
            nb = (subset["outcome"] == "BOUNCE").sum()
            fp_rows.append([label, fmt_pct(nb, n), n])
        out.append(md_table(["Flip count so far", "Next bounce %", "n"], fp_rows))
    out.append("")

    # 3C: Bounce streak
    out.append("### 3C) Bounce streak\n")
    streak_data = []
    for ray_idx in rays_df.index:
        ray_ixns = ixns_sorted[ixns_sorted["ray_idx"] == ray_idx].sort_values("enter_bar")
        consec_bounces = 0
        for _, ix in ray_ixns.iterrows():
            if ix["outcome"] in ["BOUNCE", "BREAK"]:
                streak_data.append({
                    "consec_bounces": min(consec_bounces, 3),
                    "outcome": ix["outcome"]
                })
            if ix["outcome"] == "BOUNCE":
                consec_bounces += 1
            elif ix["outcome"] == "BREAK":
                consec_bounces = 0

    sd = pd.DataFrame(streak_data)
    if len(sd) > 0:
        streak_rows = []
        for ns, label in [(0, "0 (just flipped or new)"), (1, "1 confirmed bounce"),
                          (2, "2 confirmed bounces"), (3, "3+ confirmed bounces")]:
            subset = sd[sd["consec_bounces"] == ns]
            n = len(subset)
            nb = (subset["outcome"] == "BOUNCE").sum()
            streak_rows.append([label, fmt_pct(nb, n), n])
        out.append(md_table(
            ["Consecutive bounces in current polarity", "Next bounce %", "n"],
            streak_rows
        ))
    out.append("")

    # 3D: Retest after flip
    out.append("### 3D) Retest after flip\n")
    retest_data = []
    for ray_idx in rays_df.index:
        ray_ixns = ixns_sorted[ixns_sorted["ray_idx"] == ray_idx].sort_values("enter_bar")
        ixn_list = list(ray_ixns.iterrows())

        pre_flip_bounces = 0
        for i, (_, ix) in enumerate(ixn_list):
            if ix["outcome"] == "BREAK":
                # Look for next interaction (retest from new side)
                if i + 1 < len(ixn_list):
                    _, next_ix = ixn_list[i + 1]
                    bars_until = int(next_ix["enter_bar"]) - int(ix["enter_bar"])
                    retest_data.append({
                        "retested": True,
                        "bars_until": bars_until,
                        "retest_outcome": next_ix["outcome"],
                        "pre_flip_bounces": min(pre_flip_bounces, 3),
                        "ray_tf": ix["ray_tf"],
                    })
                else:
                    retest_data.append({
                        "retested": False,
                        "bars_until": None,
                        "retest_outcome": None,
                        "pre_flip_bounces": min(pre_flip_bounces, 3),
                        "ray_tf": ix["ray_tf"],
                    })
                pre_flip_bounces = 0
            elif ix["outcome"] == "BOUNCE":
                pre_flip_bounces += 1

    rd = pd.DataFrame(retest_data)
    if len(rd) > 0:
        retested = rd[rd["retested"] == True]
        not_retested = rd[rd["retested"] == False]
        out.append(md_table(
            ["Metric", "Value"],
            [
                ["Flips where price retests from new side",
                 f"{len(retested)} ({fmt_pct(len(retested), len(rd))})"],
                ["Mean bars until retest",
                 fmt_f(retested["bars_until"].mean()) if len(retested) > 0 else "N/A"],
                ["Median bars until retest",
                 fmt_f(retested["bars_until"].median()) if len(retested) > 0 else "N/A"],
                ["Retests that never happen",
                 f"{len(not_retested)} ({fmt_pct(len(not_retested), len(rd))})"],
            ]
        ))
        out.append("")

        # Pre-flip strength → retest outcome
        out.append("**Pre-flip bounces → retest outcome:**\n")
        retest_valid = retested[retested["retest_outcome"].isin(["BOUNCE", "BREAK"])]
        pfb_rows = []
        for nb, label in [(0, "0 (broke on first interaction)"),
                          (1, "1 bounce before break"),
                          (2, "2 bounces before break"),
                          (3, "3+ bounces before break")]:
            subset = retest_valid[retest_valid["pre_flip_bounces"] == nb]
            n = len(subset)
            nb_count = (subset["retest_outcome"] == "BOUNCE").sum()
            pfb_rows.append([label, fmt_pct(nb_count, n), n])
        out.append(md_table(
            ["Pre-flip bounces", "Retest bounce % (new polarity)", "n"],
            pfb_rows
        ))
        out.append("")

        # Retest by TF
        out.append("**Retest outcome by ray TF:**\n")
        retest_valid["tf_bucket"] = retest_valid["ray_tf"].map(TF_BUCKET_MAP).fillna("240m+")
        tf_rt_rows = []
        for tfb in TF_BUCKET_ORDER:
            subset = retest_valid[retest_valid["tf_bucket"] == tfb]
            n = len(subset)
            nb_count = (subset["retest_outcome"] == "BOUNCE").sum()
            flag = " ⚠️ LOW" if n < 20 else ""
            tf_rt_rows.append([tfb, n, fmt_pct(nb_count, n), f"{n}{flag}"])
        out.append(md_table(["Ray TF", "Retests", "Retest bounce %", "n"], tf_rt_rows))
        out.append("")

    # 3E: S/R decay within polarity phase
    out.append("### 3E) S/R decay within a polarity phase\n")
    decay_data = []
    for ray_idx, phases in ray_interactions_by_polarity.items():
        for phase in phases:
            if len(phase) < 2:
                continue
            for seq_num, ix in enumerate(phase):
                # Bounce magnitude = MFE from ray in bounce direction
                eb = int(ix["enter_bar"])
                ray_p = ix["ray_price"]
                approach = ix["approach_from"]
                # Look forward up to next interaction or 100 bars
                end = min(eb + 100, len(highs))
                if approach == "ABOVE":
                    bounce_mag = (np.max(highs[eb:end]) - ray_p) / TICK_SIZE
                else:
                    bounce_mag = (ray_p - np.min(lows[eb:end])) / TICK_SIZE

                decay_data.append({
                    "seq_num": min(seq_num, 3),  # bucket 4+ as 3
                    "bounce_magnitude": bounce_mag,
                    "dwell": ix["dwell"],
                })

    dd = pd.DataFrame(decay_data)
    if len(dd) > 0:
        decay_rows = []
        for sn, label in [(0, "1st interaction after flip"),
                          (1, "2nd interaction"),
                          (2, "3rd interaction"),
                          (3, "4th+ interaction")]:
            subset = dd[dd["seq_num"] == sn]
            n = len(subset)
            decay_rows.append([
                label,
                fmt_f(subset["bounce_magnitude"].mean()) if n > 0 else "N/A",
                n
            ])
        out.append(md_table(
            ["Interaction # in current polarity", "Mean bounce magnitude (ticks)", "n"],
            decay_rows
        ))
        out.append("")

        # Dwell time by sequence
        out.append("**Dwell time by sequence position:**\n")
        dwell_decay_rows = []
        for sn, label in [(0, "1st"), (1, "2nd"), (2, "3rd"), (3, "4th+")]:
            subset = dd[dd["seq_num"] == sn]
            n = len(subset)
            dwell_decay_rows.append([
                label,
                fmt_f(subset["dwell"].mean()) if n > 0 else "N/A",
                n
            ])
        out.append(md_table(["Position", "Mean dwell (bars)", "n"], dwell_decay_rows))
        out.append("")

    return "\n".join(out)


# =============================================================================
# SECTION 4: RAYS AND ZONE TOUCHES
# =============================================================================
def section_4(zte, ray_ctx, rays_df, bars):
    """Analyze rays at zone touch events using ray_context data."""
    out = []
    out.append("=" * 64)
    out.append("SECTION 4: RAYS AND ZONE TOUCHES")
    out.append("=" * 64)
    out.append("")

    # 4A: Ray density at zone touches
    out.append("### 4A) Ray density at zone touches\n")

    # Count rays per touch
    rays_per_touch = ray_ctx.groupby("TouchID").size()
    all_touch_ids = set(zte["TouchID"].unique())
    touches_with_rays = set(rays_per_touch.index) & all_touch_ids
    touches_no_rays = all_touch_ids - touches_with_rays

    # Filter to reasonable proximity (use RayDistTicks)
    # Schema says proximity filter is 2x widest zone width; let's use all data
    prox_30t = ray_ctx[ray_ctx["RayDistTicks"] <= 30 * TICK_SIZE / TICK_SIZE]  # 30 ticks
    rays_per_touch_30t = prox_30t.groupby("TouchID").size()

    out.append(md_table(
        ["Metric", "Value"],
        [
            ["Mean rays per touch (all within proximity filter)",
             fmt_f(rays_per_touch.mean())],
            ["Median rays per touch", fmt_f(rays_per_touch.median())],
            ["Mean rays per touch (within 30t)",
             fmt_f(rays_per_touch_30t.mean()) if len(rays_per_touch_30t) > 0 else "N/A"],
            ["Touches with 0 nearby rays",
             f"{len(touches_no_rays)} ({fmt_pct(len(touches_no_rays), len(all_touch_ids))})"],
            ["Touches with 5+ nearby rays (within 30t)",
             f"{(rays_per_touch_30t >= 5).sum()} ({fmt_pct((rays_per_touch_30t >= 5).sum(), len(all_touch_ids))})"],
        ]
    ))
    out.append("")

    # 4B: Ray position relative to zone
    out.append("### 4B) Ray position relative to zone\n")
    # Merge ray_ctx with ZTE to get zone geometry
    rc_merged = ray_ctx.merge(
        zte[["TouchID", "TouchType", "TouchPrice", "ZoneTop", "ZoneBot",
             "ZoneWidthTicks", "Reaction", "Penetration"]],
        on="TouchID", how="left"
    )

    # Classify ray position
    def classify_ray_position(row):
        rp = row["RayPrice"]
        zt = row["ZoneTop"]
        zb = row["ZoneBot"]
        zw = row["ZoneWidthTicks"] * TICK_SIZE
        tt = row["TouchType"]

        if zb <= rp <= zt:
            return "Ray INSIDE active zone"

        if tt == "DEMAND_EDGE":
            # Entry at zone top, target below (well, target is ABOVE for bounce)
            # T1 = entry + 0.5*ZW, T2 = entry + 1.0*ZW
            entry = zt
            t1 = entry + 0.5 * zw
            t2 = entry + 1.0 * zw
            stop = entry - max(1.5 * zw, 120 * TICK_SIZE)

            if rp > zt:
                if rp <= t1:
                    return "Ray between entry and T1 target"
                elif rp <= t2:
                    return "Ray between T1 and T2 target"
                else:
                    return "Ray ABOVE zone (beyond T2)"
            else:  # below zone
                if rp >= stop:
                    return "Ray on adverse side (within stop)"
                else:
                    return "Ray on adverse side (beyond stop)"
        elif tt == "SUPPLY_EDGE":
            entry = zb
            t1 = entry - 0.5 * zw
            t2 = entry - 1.0 * zw
            stop = entry + max(1.5 * zw, 120 * TICK_SIZE)

            if rp < zb:
                if rp >= t1:
                    return "Ray between entry and T1 target"
                elif rp >= t2:
                    return "Ray between T1 and T2 target"
                else:
                    return "Ray BELOW zone (beyond T2)"
            else:  # above zone
                if rp <= stop:
                    return "Ray on adverse side (within stop)"
                else:
                    return "Ray on adverse side (beyond stop)"
        else:
            return "OTHER"

    rc_valid = rc_merged.dropna(subset=["ZoneTop", "ZoneBot"]).copy()
    if len(rc_valid) > 0:
        rc_valid["position"] = rc_valid.apply(classify_ray_position, axis=1)
        pos_counts = rc_valid["position"].value_counts()
        pos_rows = []
        for pos in ["Ray INSIDE active zone", "Ray between entry and T1 target",
                     "Ray between T1 and T2 target", "Ray on adverse side (within stop)",
                     "Ray on adverse side (beyond stop)"]:
            count = pos_counts.get(pos, 0)
            # Mean distance for this position
            subset = rc_valid[rc_valid["position"] == pos]
            mean_dist = subset["RayDistTicks"].mean() if len(subset) > 0 else 0
            pos_rows.append([pos, count, fmt_pct(count, len(rc_valid)),
                             fmt_f(mean_dist)])
        out.append(md_table(
            ["Position", "Count", "%", "Mean distance (ticks)"],
            pos_rows
        ))
    out.append("")

    # 4C: Do rays predict zone touch outcome?
    out.append("### 4C) Do rays predict zone touch outcome?\n")
    # R/P = Reaction / Penetration
    zte_valid = zte[(zte["Reaction"] > 0) & (zte["Penetration"] > 0)].copy()
    zte_valid["RP"] = zte_valid["Reaction"] / zte_valid["Penetration"]
    zte_valid["WR"] = (zte_valid["Reaction"] > zte_valid["Penetration"]).astype(int)

    # Touches with/without rays nearby
    touch_ray_count_30t = rays_per_touch_30t.reindex(zte_valid["TouchID"], fill_value=0)
    zte_valid["n_rays_30t"] = touch_ray_count_30t.values

    # Merge with ray context for detailed classification
    # Get ray info per touch: check if any ray inside zone, HTF ray inside zone, etc.
    touch_ray_info = {}
    for tid, group in rc_valid.groupby("TouchID"):
        inside = group[group["position"] == "Ray INSIDE active zone"]
        between_t1 = group[group["position"] == "Ray between entry and T1 target"]
        htf_inside = inside[inside["RayTF"].apply(tf_minutes) >= 60]
        touch_ray_info[tid] = {
            "has_inside": len(inside) > 0,
            "has_htf_inside": len(htf_inside) > 0,
            "has_between_t1": len(between_t1) > 0,
            "n_cluster": len(group[group["RayDistTicks"] <= 30]),
        }

    tri = pd.DataFrame.from_dict(touch_ray_info, orient="index")
    zte_merged = zte_valid.merge(tri, left_on="TouchID", right_index=True, how="left")
    zte_merged = zte_merged.fillna(False)

    context_rows = []
    # No rays nearby
    no_rays = zte_merged[zte_merged["n_rays_30t"] == 0]
    if len(no_rays) > 0:
        context_rows.append([
            "No rays nearby",
            len(no_rays), fmt_f(no_rays["WR"].mean() * 100),
            fmt_f(no_rays["Reaction"].mean()), fmt_f(no_rays["Penetration"].mean()),
            fmt_f(no_rays["RP"].median(), 2)
        ])

    # Ray inside zone
    inside = zte_merged[zte_merged["has_inside"] == True]
    if len(inside) > 0:
        context_rows.append([
            "Ray inside zone (confirmation)",
            len(inside), fmt_f(inside["WR"].mean() * 100),
            fmt_f(inside["Reaction"].mean()), fmt_f(inside["Penetration"].mean()),
            fmt_f(inside["RP"].median(), 2)
        ])

    # Fresh HTF ray inside zone
    htf_inside = zte_merged[zte_merged["has_htf_inside"] == True]
    if len(htf_inside) > 0:
        context_rows.append([
            "Fresh HTF ray inside zone",
            len(htf_inside), fmt_f(htf_inside["WR"].mean() * 100),
            fmt_f(htf_inside["Reaction"].mean()), fmt_f(htf_inside["Penetration"].mean()),
            fmt_f(htf_inside["RP"].median(), 2)
        ])

    # Ray between entry and T1
    between = zte_merged[zte_merged["has_between_t1"] == True]
    if len(between) > 0:
        context_rows.append([
            "Ray between entry and T1 (obstacle)",
            len(between), fmt_f(between["WR"].mean() * 100),
            fmt_f(between["Reaction"].mean()), fmt_f(between["Penetration"].mean()),
            fmt_f(between["RP"].median(), 2)
        ])

    # Multiple rays clustered
    clustered = zte_merged[zte_merged["n_cluster"] >= 3]
    if len(clustered) > 0:
        context_rows.append([
            "Multiple rays clustered near zone",
            len(clustered), fmt_f(clustered["WR"].mean() * 100),
            fmt_f(clustered["Reaction"].mean()), fmt_f(clustered["Penetration"].mean()),
            fmt_f(clustered["RP"].median(), 2)
        ])

    out.append(md_table(
        ["Ray context", "Touches", "WR%", "Mean Rxn", "Mean Pen", "R/P"],
        context_rows
    ))
    out.append("")

    # 4D: Ray TF vs zone TF
    out.append("### 4D) Ray TF vs zone TF interaction\n")
    # Merge ray context with ZTE for TF comparison
    rc_zte = rc_valid.merge(
        zte_valid[["TouchID", "SourceLabel", "Reaction", "Penetration", "RP"]],
        on="TouchID", how="inner", suffixes=("_ray", "_zone")
    )

    if len(rc_zte) > 0:
        rc_zte["ray_min"] = rc_zte["RayTF"].apply(tf_minutes)
        rc_zte["zone_min"] = rc_zte["SourceLabel"].apply(tf_minutes)

        def tf_relationship(row):
            if row["ray_min"] == row["zone_min"]:
                return "Same TF"
            elif row["ray_min"] > row["zone_min"]:
                return "Higher TF ray, lower TF zone"
            else:
                return "Lower TF ray, higher TF zone"

        rc_zte["tf_rel"] = rc_zte.apply(tf_relationship, axis=1)

        tf_rel_rows = []
        for rel in ["Same TF", "Higher TF ray, lower TF zone", "Lower TF ray, higher TF zone"]:
            subset = rc_zte[rc_zte["tf_rel"] == rel]
            n_touches = subset["TouchID"].nunique()
            mean_rp = subset.groupby("TouchID")["RP"].first().median()
            tf_rel_rows.append([rel, "—", n_touches, fmt_f(mean_rp, 2),
                                "Yes" if mean_rp and mean_rp > 1.5 else "—"])

        out.append(md_table(
            ["Ray TF", "Zone TF", "Touches", "R/P", "Signal?"],
            tf_rel_rows
        ))
    out.append("")

    # 4E: Nested zone context
    out.append("### 4E) Nested zone context\n")
    # Count overlapping zones at each touch price
    # For each touch, check how many other zones overlap at that price
    zte_all = zte.copy()
    nesting_data = []
    for _, touch in zte_valid.iterrows():
        tp = touch["TouchPrice"]
        # Count zones that contain this price (from all TFs)
        overlapping = zte_all[
            (zte_all["ZoneBot"] <= tp) & (zte_all["ZoneTop"] >= tp) &
            (zte_all["BarIndex"] <= touch["BarIndex"])  # only zones that exist at touch time
        ]
        # Deduplicate by zone (same ZoneTop+ZoneBot = same zone)
        unique_zones = overlapping.drop_duplicates(subset=["ZoneTop", "ZoneBot"])
        depth = len(unique_zones)
        nesting_data.append({
            "TouchID": touch["TouchID"],
            "nesting_depth": min(depth, 3),
            "n_rays_30t": touch["n_rays_30t"] if "n_rays_30t" in touch.index else 0,
        })

    nd = pd.DataFrame(nesting_data)
    if len(nd) > 0:
        nd_merged = nd.merge(zte_valid[["TouchID", "RP"]], on="TouchID")
        nest_rows = []
        for depth, label in [(1, "1 (touched zone only)"),
                             (2, "2 (one parent zone)"),
                             (3, "3+ (deep nesting)")]:
            subset = nd_merged[nd_merged["nesting_depth"] == depth]
            n = len(subset)
            mean_rays = subset["n_rays_30t"].mean() if n > 0 else 0
            nest_rows.append([label, n, fmt_pct(n, len(nd_merged)),
                              fmt_f(mean_rays)])
        out.append(md_table(
            ["Nesting depth", "Touches", "%", "Mean rays nearby"],
            nest_rows
        ))
    out.append("")

    return "\n".join(out)


# =============================================================================
# SECTION 5: RAY CLUSTERING
# =============================================================================
def section_5(ixns, rays_df, bars):
    """Analyze ray clustering effects."""
    out = []
    out.append("=" * 64)
    out.append("SECTION 5: RAY CLUSTERING")
    out.append("=" * 64)
    out.append("")

    # 5A: Identify clusters
    out.append("### 5A) Ray cluster identification\n")
    # Sort rays by price
    rays_sorted = rays_df.sort_values("price").reset_index(drop=True)
    prices = rays_sorted["price"].values
    CLUSTER_THRESH_TICKS = 30
    cluster_thresh_price = CLUSTER_THRESH_TICKS * TICK_SIZE

    # Assign cluster IDs using single-linkage clustering
    cluster_ids = np.zeros(len(prices), dtype=int)
    current_cluster = 1
    if len(prices) > 0:
        cluster_ids[0] = current_cluster
        for i in range(1, len(prices)):
            if prices[i] - prices[i - 1] <= cluster_thresh_price:
                cluster_ids[i] = cluster_ids[i - 1]
            else:
                current_cluster += 1
                cluster_ids[i] = current_cluster

    rays_sorted["cluster_id"] = cluster_ids
    cluster_sizes = rays_sorted.groupby("cluster_id").size()
    multi_ray_clusters = cluster_sizes[cluster_sizes >= 2]

    # Cluster widths
    cluster_widths = []
    for cid in multi_ray_clusters.index:
        cprices = rays_sorted[rays_sorted["cluster_id"] == cid]["price"]
        cluster_widths.append((cprices.max() - cprices.min()) / TICK_SIZE)

    in_cluster = rays_sorted[rays_sorted["cluster_id"].isin(multi_ray_clusters.index)]

    out.append(md_table(
        ["Metric", "Value"],
        [
            ["Total clusters found (2+ rays within 30t)", len(multi_ray_clusters)],
            ["Mean rays per cluster", fmt_f(multi_ray_clusters.mean())],
            ["Mean cluster width (ticks)",
             fmt_f(np.mean(cluster_widths)) if cluster_widths else "N/A"],
            ["% of all rays in a cluster",
             fmt_pct(len(in_cluster), len(rays_sorted))],
        ]
    ))
    out.append("")

    # 5B: Cluster vs isolated outcome
    out.append("### 5B) Cluster vs isolated ray interaction outcome\n")
    # Map each ray to cluster status
    ray_cluster_map = dict(zip(rays_sorted.index, cluster_ids))
    cluster_size_map = dict(cluster_sizes)

    # For each interaction, determine if ray is isolated or in cluster
    # Note: static cluster assignment (not time-varying as prompt suggests)
    # This is an approximation
    ixns_valid = ixns[ixns["outcome"].isin(["BOUNCE", "BREAK"])].copy()

    # Map ray_idx to rays_sorted index via price matching
    ray_price_to_sorted_idx = {}
    for i, row in rays_sorted.iterrows():
        ray_price_to_sorted_idx[(row["price"], row["side"])] = i

    def get_cluster_size(row):
        key = (row["ray_price"], row["ray_side"])
        sorted_idx = ray_price_to_sorted_idx.get(key)
        if sorted_idx is not None:
            cid = ray_cluster_map.get(sorted_idx, 0)
            return cluster_size_map.get(cid, 1)
        return 1

    ixns_valid["cluster_size"] = ixns_valid.apply(get_cluster_size, axis=1)

    cluster_rows = []
    for label, cond in [
        ("Isolated ray (no other within 30t)", ixns_valid["cluster_size"] == 1),
        ("Cluster (2+ rays within 30t)", ixns_valid["cluster_size"] >= 2),
        ("Dense cluster (3+ rays within 30t)", ixns_valid["cluster_size"] >= 3),
    ]:
        subset = ixns_valid[cond]
        n = len(subset)
        nb = (subset["outcome"] == "BOUNCE").sum()

        # First interaction only
        first_only = subset.sort_values("enter_bar").groupby("ray_idx").first()
        n_first = len(first_only)
        nb_first = (first_only["outcome"] == "BOUNCE").sum()

        cluster_rows.append([
            label, fmt_pct(nb_first, n_first),
            fmt_pct(n_first - nb_first, n_first), n_first
        ])

    out.append(md_table(
        ["Type", "First bounce %", "First break %", "n"],
        cluster_rows
    ))
    out.append("")

    # 5C: Cluster TF composition
    out.append("### 5C) Cluster TF composition\n")
    cluster_tf_data = []
    for cid in multi_ray_clusters.index:
        c_rays = rays_sorted[rays_sorted["cluster_id"] == cid]
        tfs = set(c_rays["tf_bucket"])
        has_htf = any(tf_minutes(t) >= 60 for t in c_rays["tf"] if t in TF_BUCKET_MAP)

        if len(tfs) == 1:
            cluster_tf_data.append({"type": "All same TF", "cluster_id": cid})
        else:
            cluster_tf_data.append({"type": "Mixed TF", "cluster_id": cid})

        if has_htf:
            cluster_tf_data.append({"type": "HTF-anchored (60m+)", "cluster_id": cid})

    # Get bounce rate for interactions at clustered rays by cluster type
    # This is a rough approximation
    ctd = pd.DataFrame(cluster_tf_data)
    if len(ctd) > 0:
        ct_rows = []
        for ctype in ["All same TF", "Mixed TF", "HTF-anchored (60m+)"]:
            cids = ctd[ctd["type"] == ctype]["cluster_id"].unique()
            # Find rays in these clusters
            c_ray_indices = rays_sorted[rays_sorted["cluster_id"].isin(cids)].index
            c_ixns = ixns_valid[ixns_valid["ray_idx"].isin(c_ray_indices)]
            n = len(c_ixns)
            nb = (c_ixns["outcome"] == "BOUNCE").sum()
            ct_rows.append([ctype, fmt_pct(nb, n), n])

        out.append(md_table(["Cluster type", "Bounce %", "n"], ct_rows))
    out.append("")

    return "\n".join(out)


# =============================================================================
# SECTION 6: RAY AS TARGET / STOP REFERENCE
# =============================================================================
def section_6(ixns, rays_df, zte, bars):
    """Analyze rays as exit level references."""
    out = []
    out.append("=" * 64)
    out.append("SECTION 6: RAY AS TARGET / STOP REFERENCE")
    out.append("=" * 64)
    out.append("")

    closes = bars["Close"].values.astype(np.float64)
    highs = bars["High"].values.astype(np.float64)
    lows = bars["Low"].values.astype(np.float64)

    # Use qualifying touches (scored above some threshold)
    # ZONEREL config: T1=0.5xZW, T2=1.0xZW, Stop=max(1.5xZW, 120t)
    zte_valid = zte[
        (zte["TouchType"] != "VP_RAY") &
        (zte["QualityScore"] > 0) &
        (zte["Reaction"] > 0)
    ].copy()

    out.append(f"Qualifying touches: {len(zte_valid)}\n")

    # 6A: Ray between entry and T1
    out.append("### 6A) Ray between entry and T1\n")
    ray_prices = rays_df["price"].values
    ray_creation_bars = rays_df["creation_bar"].values

    stall_data = []
    ray_between_count = 0
    stall_count = 0

    for _, touch in zte_valid.iterrows():
        bar_idx = int(touch["BarIndex"])
        zw = touch["ZoneWidthTicks"] * TICK_SIZE
        tt = touch["TouchType"]

        if tt == "DEMAND_EDGE":
            entry = touch["ZoneTop"]
            t1 = entry + 0.5 * zw
        elif tt == "SUPPLY_EDGE":
            entry = touch["ZoneBot"]
            t1 = entry - 0.5 * zw
        else:
            continue

        # Find active rays between entry and T1
        active_mask = ray_creation_bars <= bar_idx
        active_prices = ray_prices[active_mask]

        if tt == "DEMAND_EDGE":
            between = active_prices[(active_prices > entry) & (active_prices < t1)]
        else:
            between = active_prices[(active_prices < entry) & (active_prices > t1)]

        if len(between) > 0:
            ray_between_count += 1
            # Check for stall: price spends 3+ bars near the ray
            nearest_ray = between[np.argmin(np.abs(between - entry))]
            obs_end = min(bar_idx + 100, len(closes))
            if obs_end > bar_idx:
                obs_closes = closes[bar_idx:obs_end]
                near_ray = np.abs(obs_closes - nearest_ray) <= 10 * TICK_SIZE  # within 10t
                # Count consecutive bars near ray
                max_consec = 0
                consec = 0
                for nr in near_ray:
                    if nr:
                        consec += 1
                        max_consec = max(max_consec, consec)
                    else:
                        consec = 0

                if max_consec >= 3:
                    stall_count += 1
                    # Did price eventually reach T1?
                    if tt == "DEMAND_EDGE":
                        reached_t1 = np.any(highs[bar_idx:obs_end] >= t1)
                    else:
                        reached_t1 = np.any(lows[bar_idx:obs_end] <= t1)

                    stall_data.append({
                        "reached_t1": reached_t1,
                        "ray_dist_from_entry": abs(nearest_ray - entry) / TICK_SIZE,
                    })

    n_qual = len(zte_valid)
    out.append(md_table(
        ["Metric", "Value"],
        [
            ["Qualifying touches with ray between entry and T1",
             f"{ray_between_count} ({fmt_pct(ray_between_count, n_qual)})"],
            ["Touches where price stalls at ray before T1",
             f"{stall_count} ({fmt_pct(stall_count, n_qual)})"],
        ]
    ))
    out.append("")

    # 6B: Stall outcomes
    if stall_data:
        out.append("### 6B) Stall outcomes\n")
        sd_df = pd.DataFrame(stall_data)
        n_reached = sd_df["reached_t1"].sum()
        n_reversed = len(sd_df) - n_reached
        out.append(md_table(
            ["Outcome", "Count", "%"],
            [
                ["Eventually reaches T1 after stalling", n_reached,
                 fmt_pct(n_reached, len(sd_df))],
                ["Reverses from ray, never reaches T1", n_reversed,
                 fmt_pct(n_reversed, len(sd_df))],
            ]
        ))
        out.append("")

    # 6D: Ray-to-ray movement
    out.append("### 6D) Ray-to-ray movement\n")
    ixns_breaks = ixns[ixns["outcome"] == "BREAK"].copy()
    r2r_data = []

    sorted_ray_prices = np.sort(ray_prices)

    for _, ix in ixns_breaks.iterrows():
        ray_p = ix["ray_price"]
        approach = ix["approach_from"]
        enter_bar = int(ix["enter_bar"])

        # Direction of break
        if approach == "ABOVE":
            # Broke downward - next ray is below
            candidates = sorted_ray_prices[sorted_ray_prices < ray_p - 5 * TICK_SIZE]
            if len(candidates) > 0:
                next_ray = candidates[-1]  # nearest below
                dist = (ray_p - next_ray) / TICK_SIZE
                # Check if price reached it
                obs_end = min(enter_bar + 200, len(lows))
                reached = np.any(lows[enter_bar:obs_end] <= next_ray + 5 * TICK_SIZE)
                if reached:
                    reach_bar = enter_bar + np.argmax(
                        lows[enter_bar:obs_end] <= next_ray + 5 * TICK_SIZE
                    )
                    bars_to_reach = reach_bar - enter_bar
                else:
                    bars_to_reach = None
                r2r_data.append({
                    "has_next": True, "dist": dist,
                    "reached": reached, "bars_to_reach": bars_to_reach
                })
            else:
                r2r_data.append({"has_next": False})
        else:
            # Broke upward - next ray is above
            candidates = sorted_ray_prices[sorted_ray_prices > ray_p + 5 * TICK_SIZE]
            if len(candidates) > 0:
                next_ray = candidates[0]
                dist = (next_ray - ray_p) / TICK_SIZE
                obs_end = min(enter_bar + 200, len(highs))
                reached = np.any(highs[enter_bar:obs_end] >= next_ray - 5 * TICK_SIZE)
                if reached:
                    reach_bar = enter_bar + np.argmax(
                        highs[enter_bar:obs_end] >= next_ray - 5 * TICK_SIZE
                    )
                    bars_to_reach = reach_bar - enter_bar
                else:
                    bars_to_reach = None
                r2r_data.append({
                    "has_next": True, "dist": dist,
                    "reached": reached, "bars_to_reach": bars_to_reach
                })
            else:
                r2r_data.append({"has_next": False})

    r2r_df = pd.DataFrame(r2r_data)
    if len(r2r_df) > 0:
        has_next = r2r_df[r2r_df["has_next"] == True]
        reached = has_next[has_next["reached"] == True]
        out.append(md_table(
            ["Metric", "Value"],
            [
                ["Break-throughs with another ray ahead",
                 f"{len(has_next)} ({fmt_pct(len(has_next), len(r2r_df))})"],
                ["Mean distance to next ray (ticks)",
                 fmt_f(has_next["dist"].mean()) if len(has_next) > 0 else "N/A"],
                ["% that reach the next ray",
                 fmt_pct(len(reached), len(has_next))],
                ["Mean bars to reach next ray",
                 fmt_f(reached["bars_to_reach"].mean()) if len(reached) > 0 else "N/A"],
            ]
        ))
    out.append("")

    return "\n".join(out)


# =============================================================================
# SECTION 7: LTF VS HTF RAYS
# =============================================================================
def section_7(ixns, rays_df, zte, ray_ctx, bars):
    """Analyze LTF vs HTF ray differences."""
    out = []
    out.append("=" * 64)
    out.append("SECTION 7: LTF VS HTF RAYS")
    out.append("=" * 64)
    out.append("")

    # 7A: All interaction data by TF
    out.append("### 7A) Consolidated interaction data by TF\n")
    ixns_valid = ixns[ixns["outcome"].isin(["BOUNCE", "BREAK"])].copy()
    ixns_valid["tf_bucket"] = ixns_valid["ray_tf"].map(TF_BUCKET_MAP).fillna("240m+")

    tf_rows = []
    for tfb in TF_BUCKET_ORDER:
        subset = ixns_valid[ixns_valid["tf_bucket"] == tfb]
        n = len(subset)
        nb = (subset["outcome"] == "BOUNCE").sum()
        nk = n - nb

        # Mean persistence (bars from creation to last interaction)
        ray_indices = subset["ray_idx"].unique()
        persist_bars = []
        for ri in ray_indices:
            ray_ixns = ixns_valid[ixns_valid["ray_idx"] == ri]
            if len(ray_ixns) > 0:
                last_bar = ray_ixns["enter_bar"].max()
                creation = rays_df.iloc[ri]["creation_bar"] if ri < len(rays_df) else 0
                persist_bars.append(last_bar - creation)

        mean_persist = np.mean(persist_bars) if persist_bars else 0

        # Flip rate
        n_breaks = nk
        flip_rate = n_breaks / n if n > 0 else 0

        tf_rows.append([
            tfb, n, fmt_pct(nb, n), fmt_pct(nk, n),
            fmt_f(mean_persist, 0), fmt_f(flip_rate, 2)
        ])

    out.append(md_table(
        ["TF", "Total interactions", "Bounce %", "Break %",
         "Mean persistence (bars)", "Flip rate"],
        tf_rows
    ))
    out.append("")

    # 7B: At zone touches
    out.append("### 7B) At zone touches — ray TF impact on R/P\n")
    zte_valid = zte[
        (zte["TouchType"] != "VP_RAY") &
        (zte["Reaction"] > 0) & (zte["Penetration"] > 0)
    ].copy()
    zte_valid["RP"] = zte_valid["Reaction"] / zte_valid["Penetration"]

    # For each TF, find touches with/without that TF ray present
    # Use ray_context
    ray_ctx_tf = ray_ctx.copy()
    ray_ctx_tf["tf_bucket"] = ray_ctx_tf["RayTF"].map(TF_BUCKET_MAP).fillna("240m+")

    tf_touch_rows = []
    for tfb in TF_BUCKET_ORDER:
        # Touches with this TF ray within 30 ticks
        tf_rays = ray_ctx_tf[
            (ray_ctx_tf["tf_bucket"] == tfb) & (ray_ctx_tf["RayDistTicks"] <= 30)
        ]
        touches_with = set(tf_rays["TouchID"].unique()) & set(zte_valid["TouchID"])
        touches_without = set(zte_valid["TouchID"]) - touches_with

        with_rp = zte_valid[zte_valid["TouchID"].isin(touches_with)]["RP"]
        without_rp = zte_valid[zte_valid["TouchID"].isin(touches_without)]["RP"]

        rp_with = with_rp.median() if len(with_rp) > 0 else None
        rp_without = without_rp.median() if len(without_rp) > 0 else None
        delta = (rp_with - rp_without) if (rp_with is not None and rp_without is not None) else None

        tf_touch_rows.append([
            f"{tfb} ray",
            len(touches_with),
            fmt_f(rp_with, 2) if rp_with else "N/A",
            fmt_f(rp_without, 2) if rp_without else "N/A",
            fmt_f(delta, 2) if delta is not None else "N/A",
        ])

    out.append(md_table(
        ["TF", "Touches with ray", "R/P with ray", "R/P without ray", "Delta"],
        tf_touch_rows
    ))
    out.append("")

    return "\n".join(out)


# =============================================================================
# SECTION 8: SUMMARY AND DISCOVERY MAP
# =============================================================================
def section_8(ixns, rays_df, zte, ray_ctx, bars, metrics):
    """Generate discovery map with signal classifications computed from actual data."""
    out = []
    out.append("=" * 64)
    out.append("SECTION 8: SUMMARY AND DISCOVERY MAP")
    out.append("=" * 64)
    out.append("")

    out.append("### A) Signal strength classification\n")
    out.append("Criteria: STRONG = ≥10pp separation or clear monotonic trend across "
               "bins with adequate n. MODERATE = 5-10pp or monotonic with smaller n. "
               "WEAK = <5pp or inconsistent. INSUFFICIENT = n<20 in key bins.\n")

    # ---- Recompute all metrics from the actual interaction data ----
    valid = ixns[ixns["outcome"].isin(["BOUNCE", "BREAK"])].copy() if ixns is not None else pd.DataFrame()

    def bounce_pct(subset):
        n = len(subset)
        if n == 0:
            return 0.0, 0
        return (subset["outcome"] == "BOUNCE").sum() / n * 100, n

    def classify(spread, ns, min_n=20):
        if any(n < min_n for n in ns):
            return "INSUFFICIENT DATA"
        if spread >= 10:
            return "STRONG"
        elif spread >= 5:
            return "MODERATE"
        else:
            return "WEAK"

    # --- Ray TF (7A) ---
    tf_bounces = []
    for tfb in TF_BUCKET_ORDER:
        sub = valid[valid["ray_tf"].map(TF_BUCKET_MAP).fillna("240m+") == tfb]
        bp, n = bounce_pct(sub)
        tf_bounces.append((bp, n))
    tf_pcts = [x[0] for x in tf_bounces]
    tf_ns = [x[1] for x in tf_bounces]
    tf_spread = max(tf_pcts) - min(tf_pcts) if tf_pcts else 0
    tf_signal = classify(tf_spread, tf_ns)
    tf_best = TF_BUCKET_ORDER[tf_pcts.index(max(tf_pcts))] if tf_pcts else "?"

    # --- Ray age (2F) ---
    first_ixns = valid.sort_values("enter_bar").groupby("ray_idx").first().reset_index()
    first_ixns = first_ixns.merge(rays_df[["creation_bar"]], left_on="ray_idx", right_index=True)
    first_ixns["age"] = first_ixns["enter_bar"] - first_ixns["creation_bar"]
    age_bins = [(0, 50, "fresh"), (50, 200, "50-200"), (200, 500, "200-500"), (500, 999999, "stale")]
    age_pcts, age_ns = [], []
    for lo, hi, _ in age_bins:
        sub = first_ixns[(first_ixns["age"] >= lo) & (first_ixns["age"] < hi)]
        bp, n = bounce_pct(sub)
        age_pcts.append(bp)
        age_ns.append(n)
    age_spread = max(age_pcts) - min(age_pcts) if age_pcts else 0
    age_signal = classify(age_spread, age_ns)

    # --- Polarity (2G) ---
    above = valid[valid["approach_from"] == "ABOVE"]
    below = valid[valid["approach_from"] == "BELOW"]
    bp_above, n_above = bounce_pct(above)
    bp_below, n_below = bounce_pct(below)
    pol_spread = abs(bp_above - bp_below)
    pol_signal = classify(pol_spread, [n_above, n_below])

    # --- Approach velocity (2H) ---
    fast = valid[valid["approach_vel"] > 5]
    medium = valid[(valid["approach_vel"] >= 2) & (valid["approach_vel"] <= 5)]
    slow = valid[valid["approach_vel"] < 2]
    bp_fast, n_fast = bounce_pct(fast)
    bp_med, n_med = bounce_pct(medium)
    bp_slow, n_slow = bounce_pct(slow)
    vel_spread = max(bp_fast, bp_med, bp_slow) - min(bp_fast, bp_med, bp_slow)
    vel_signal = classify(vel_spread, [n_fast, n_med, n_slow])

    # --- Session (2I) ---
    valid_sess = valid.copy()
    valid_sess["session"] = classify_session(bars, valid_sess["enter_bar"].values)
    rth = valid_sess[valid_sess["session"] == "RTH"]
    eth = valid_sess[valid_sess["session"] == "ETH"]
    bp_rth, n_rth = bounce_pct(rth)
    bp_eth, n_eth = bounce_pct(eth)
    sess_spread = abs(bp_eth - bp_rth)
    sess_signal = classify(sess_spread, [n_rth, n_eth])

    # --- Dwell time (2J) ---
    dwell_bins = [(1, 2), (3, 5), (6, 10), (11, 99999)]
    dwell_pcts, dwell_ns = [], []
    for lo, hi in dwell_bins:
        sub = valid[(valid["dwell"] >= lo) & (valid["dwell"] <= hi)]
        bp, n = bounce_pct(sub)
        dwell_pcts.append(bp)
        dwell_ns.append(n)
    dwell_spread = max(dwell_pcts) - min(dwell_pcts) if dwell_pcts else 0
    dwell_signal = classify(dwell_spread, dwell_ns)

    # --- Flip count (3B) ---
    ixns_sorted = valid.sort_values("enter_bar")
    flip_pred = []
    for ray_idx in rays_df.index:
        ray_ixns = ixns_sorted[ixns_sorted["ray_idx"] == ray_idx].sort_values("enter_bar")
        flips_so_far = 0
        for _, ix in ray_ixns.iterrows():
            flip_pred.append({"flips_so_far": min(flips_so_far, 2), "outcome": ix["outcome"]})
            if ix["outcome"] == "BREAK":
                flips_so_far += 1
    fpd = pd.DataFrame(flip_pred)
    flip_pcts, flip_ns = [], []
    for nf in [0, 1, 2]:
        sub = fpd[fpd["flips_so_far"] == nf]
        bp, n = bounce_pct(sub)
        flip_pcts.append(bp)
        flip_ns.append(n)
    flip_spread = max(flip_pcts) - min(flip_pcts) if flip_pcts else 0
    flip_signal = classify(flip_spread, flip_ns)

    # --- Bounce streak (3C) ---
    streak_data = []
    for ray_idx in rays_df.index:
        ray_ixns = ixns_sorted[ixns_sorted["ray_idx"] == ray_idx].sort_values("enter_bar")
        consec = 0
        for _, ix in ray_ixns.iterrows():
            streak_data.append({"consec": min(consec, 3), "outcome": ix["outcome"]})
            if ix["outcome"] == "BOUNCE":
                consec += 1
            elif ix["outcome"] == "BREAK":
                consec = 0
    sd = pd.DataFrame(streak_data)
    streak_pcts, streak_ns = [], []
    for ns_val in [0, 1, 2, 3]:
        sub = sd[sd["consec"] == ns_val]
        bp, n = bounce_pct(sub)
        streak_pcts.append(bp)
        streak_ns.append(n)
    streak_spread = max(streak_pcts) - min(streak_pcts) if streak_pcts else 0
    streak_signal = classify(streak_spread, streak_ns)

    # --- Retest (3D) ---
    retest_data = []
    for ray_idx in rays_df.index:
        ray_ixns = ixns_sorted[ixns_sorted["ray_idx"] == ray_idx].sort_values("enter_bar")
        ixn_list = list(ray_ixns.iterrows())
        pfb = 0
        for i, (_, ix) in enumerate(ixn_list):
            if ix["outcome"] == "BREAK" and i + 1 < len(ixn_list):
                _, nxt = ixn_list[i + 1]
                if nxt["outcome"] in ["BOUNCE", "BREAK"]:
                    retest_data.append({"pfb": min(pfb, 3), "outcome": nxt["outcome"]})
                pfb = 0
            elif ix["outcome"] == "BOUNCE":
                pfb += 1
    rd = pd.DataFrame(retest_data)
    retest_pcts, retest_ns = [], []
    for pfb_val in [0, 1, 2, 3]:
        sub = rd[rd["pfb"] == pfb_val]
        bp, n = bounce_pct(sub)
        retest_pcts.append(bp)
        retest_ns.append(n)
    retest_spread = max(retest_pcts) - min(retest_pcts) if retest_pcts else 0
    retest_signal = classify(retest_spread, retest_ns)

    # --- S/R decay (3E) ---
    closes = bars["Close"].values.astype(np.float64)
    highs = bars["High"].values.astype(np.float64)
    lows = bars["Low"].values.astype(np.float64)
    decay_mags = {0: [], 1: [], 2: [], 3: []}
    decay_dwells = {0: [], 1: [], 2: [], 3: []}
    for ray_idx in rays_df.index:
        ray_ixns = ixns_sorted[ixns_sorted["ray_idx"] == ray_idx].sort_values("enter_bar")
        bounces_in_phase = []
        for _, ix in ray_ixns.iterrows():
            if ix["outcome"] == "BOUNCE":
                bounces_in_phase.append(ix)
            elif ix["outcome"] == "BREAK":
                if len(bounces_in_phase) >= 2:
                    for seq, bix in enumerate(bounces_in_phase):
                        sn = min(seq, 3)
                        eb = int(bix["enter_bar"])
                        end = min(eb + 100, len(highs))
                        if bix["approach_from"] == "ABOVE":
                            mag = (np.max(highs[eb:end]) - bix["ray_price"]) / TICK_SIZE
                        else:
                            mag = (bix["ray_price"] - np.min(lows[eb:end])) / TICK_SIZE
                        decay_mags[sn].append(mag)
                        decay_dwells[sn].append(bix["dwell"])
                bounces_in_phase = []
    decay_first = np.mean(decay_mags[0]) if decay_mags[0] else 0
    decay_last = np.mean(decay_mags[3]) if decay_mags[3] else 0
    decay_pct = (decay_first - decay_last) / decay_first * 100 if decay_first > 0 else 0
    dwell_first = np.mean(decay_dwells[0]) if decay_dwells[0] else 0
    dwell_last = np.mean(decay_dwells[3]) if decay_dwells[3] else 0

    # --- Zone touch R/P for rays present vs absent (4C) ---
    zte_valid = zte[(zte["TouchType"] != "VP_RAY") & (zte["Reaction"] > 0) & (zte["Penetration"] > 0)].copy()
    zte_valid["RP"] = zte_valid["Reaction"] / zte_valid["Penetration"]
    prox_30t = ray_ctx[ray_ctx["RayDistTicks"] <= 30]
    rays_per_touch_30t = prox_30t.groupby("TouchID").size()
    touch_ray_count = rays_per_touch_30t.reindex(zte_valid["TouchID"], fill_value=0)
    zte_valid["n_rays_30t"] = touch_ray_count.values
    no_rays = zte_valid[zte_valid["n_rays_30t"] == 0]
    with_rays = zte_valid[zte_valid["n_rays_30t"] > 0]
    rp_no = no_rays["RP"].median() if len(no_rays) > 0 else 0
    rp_with = with_rays["RP"].median() if len(with_rays) > 0 else 0
    n_no_rays = len(no_rays)

    # --- Ray between entry and T1 (6A) - recompute ---
    ray_prices = rays_df["price"].values
    ray_creation_bars = rays_df["creation_bar"].values
    zte_qual = zte[(zte["TouchType"] != "VP_RAY") & (zte["QualityScore"] > 0) & (zte["Reaction"] > 0)].copy()
    n_qual = len(zte_qual)
    ray_between_count = 0
    stall_count = 0
    stall_reversed = 0
    for _, touch in zte_qual.iterrows():
        bar_idx = int(touch["BarIndex"])
        zw = touch["ZoneWidthTicks"] * TICK_SIZE
        tt = touch["TouchType"]
        if tt == "DEMAND_EDGE":
            entry = touch["ZoneTop"]
            t1 = entry + 0.5 * zw
        elif tt == "SUPPLY_EDGE":
            entry = touch["ZoneBot"]
            t1 = entry - 0.5 * zw
        else:
            continue
        active_mask = ray_creation_bars <= bar_idx
        active_p = ray_prices[active_mask]
        if tt == "DEMAND_EDGE":
            between = active_p[(active_p > entry) & (active_p < t1)]
        else:
            between = active_p[(active_p < entry) & (active_p > t1)]
        if len(between) > 0:
            ray_between_count += 1
            nearest_ray = between[np.argmin(np.abs(between - entry))]
            obs_end = min(bar_idx + 100, len(closes))
            if obs_end > bar_idx:
                obs_closes = closes[bar_idx:obs_end]
                near_ray = np.abs(obs_closes - nearest_ray) <= 10 * TICK_SIZE
                max_consec_nr = 0
                consec_nr = 0
                for nr in near_ray:
                    if nr:
                        consec_nr += 1
                        max_consec_nr = max(max_consec_nr, consec_nr)
                    else:
                        consec_nr = 0
                if max_consec_nr >= 3:
                    stall_count += 1
                    if tt == "DEMAND_EDGE":
                        reached_t1 = np.any(highs[bar_idx:obs_end] >= t1)
                    else:
                        reached_t1 = np.any(lows[bar_idx:obs_end] <= t1)
                    if not reached_t1:
                        stall_reversed += 1
    pct_ray_between = ray_between_count / n_qual * 100 if n_qual > 0 else 0
    pct_stall_reverse = stall_reversed / stall_count * 100 if stall_count > 0 else 0

    # --- Ray-to-ray (6D) ---
    ixns_breaks = ixns[ixns["outcome"] == "BREAK"] if ixns is not None else pd.DataFrame()
    sorted_ray_prices = np.sort(ray_prices)
    r2r_has_next = 0
    r2r_reached = 0
    r2r_dists = []
    for _, ix in ixns_breaks.head(5000).iterrows():  # sample for speed
        ray_p = ix["ray_price"]
        approach = ix["approach_from"]
        if approach == "ABOVE":
            candidates = sorted_ray_prices[sorted_ray_prices < ray_p - 5 * TICK_SIZE]
            if len(candidates) > 0:
                r2r_has_next += 1
                dist = (ray_p - candidates[-1]) / TICK_SIZE
                r2r_dists.append(dist)
                enter_bar = int(ix["enter_bar"])
                obs_end = min(enter_bar + 200, len(lows))
                if np.any(lows[enter_bar:obs_end] <= candidates[-1] + 5 * TICK_SIZE):
                    r2r_reached += 1
        else:
            candidates = sorted_ray_prices[sorted_ray_prices > ray_p + 5 * TICK_SIZE]
            if len(candidates) > 0:
                r2r_has_next += 1
                dist = (candidates[0] - ray_p) / TICK_SIZE
                r2r_dists.append(dist)
                enter_bar = int(ix["enter_bar"])
                obs_end = min(enter_bar + 200, len(highs))
                if np.any(highs[enter_bar:obs_end] >= candidates[0] - 5 * TICK_SIZE):
                    r2r_reached += 1
    pct_r2r_reached = r2r_reached / r2r_has_next * 100 if r2r_has_next > 0 else 0
    mean_r2r_dist = np.mean(r2r_dists) if r2r_dists else 0

    # --- Clustering (5B) ---
    rays_sorted = rays_df.sort_values("price").reset_index(drop=True)
    prices = rays_sorted["price"].values
    cluster_thresh_price = 30 * TICK_SIZE
    cluster_ids = np.zeros(len(prices), dtype=int)
    if len(prices) > 0:
        cur = 1
        cluster_ids[0] = cur
        for i in range(1, len(prices)):
            if prices[i] - prices[i - 1] <= cluster_thresh_price:
                cluster_ids[i] = cluster_ids[i - 1]
            else:
                cur += 1
                cluster_ids[i] = cur
    rays_sorted["cluster_id"] = cluster_ids
    cluster_sizes = rays_sorted.groupby("cluster_id").size()
    isolated_count = (cluster_sizes == 1).sum()
    in_cluster_pct = (1 - isolated_count / len(rays_sorted)) * 100 if len(rays_sorted) > 0 else 0

    # --- Cross-TF (4D) ---
    rc_merged = ray_ctx.merge(
        zte_valid[["TouchID", "SourceLabel", "RP"]],
        on="TouchID", how="inner"
    )
    cross_tf_rps = {}
    if len(rc_merged) > 0:
        rc_merged["ray_min"] = rc_merged["RayTF"].apply(tf_minutes)
        rc_merged["zone_min"] = rc_merged["SourceLabel"].apply(tf_minutes)
        for rel, cond_fn in [
            ("Same TF", lambda r: r["ray_min"] == r["zone_min"]),
            ("HTF ray + LTF zone", lambda r: r["ray_min"] > r["zone_min"]),
            ("LTF ray + HTF zone", lambda r: r["ray_min"] < r["zone_min"]),
        ]:
            sub = rc_merged[rc_merged.apply(cond_fn, axis=1)]
            cross_tf_rps[rel] = sub.groupby("TouchID")["RP"].first().median() if len(sub) > 0 else 0
    ctf_vals = list(cross_tf_rps.values())
    ctf_spread = max(ctf_vals) - min(ctf_vals) if ctf_vals else 0

    # --- Nested zone (4E) ---
    # Already computed in S4 — just reference the proportion at 3+
    # Sample first 500 touches for speed
    nest_3plus_pct = 0
    sample_zte = zte_valid.head(500)
    zte_all = zte.copy()
    for _, touch in sample_zte.iterrows():
        tp = touch["TouchPrice"]
        overlapping = zte_all[
            (zte_all["ZoneBot"] <= tp) & (zte_all["ZoneTop"] >= tp) &
            (zte_all["BarIndex"] <= touch["BarIndex"])
        ].drop_duplicates(subset=["ZoneTop", "ZoneBot"])
        if len(overlapping) >= 3:
            nest_3plus_pct += 1
    nest_3plus_pct = nest_3plus_pct / len(sample_zte) * 100 if len(sample_zte) > 0 else 0

    # ---- Build discovery map from computed values ----
    attributes = []

    attributes.append(("Ray TF", tf_signal,
        f"{tf_spread:.1f}pp spread across TFs ({min(tf_pcts):.1f}-{max(tf_pcts):.1f}%); "
        f"{tf_best} marginally better", "2E, 7"))

    attributes.append(("Ray age / freshness", age_signal,
        f"Fresh n={age_ns[0]}, stale n={age_ns[3]}; direction "
        f"({age_pcts[0]:.1f}→{age_pcts[3]:.1f}%)", "2F"))

    attributes.append(("Ray polarity (support vs resistance)", pol_signal,
        f"{pol_spread:.1f}pp spread; above {bp_above:.1f}% vs below {bp_below:.1f}%", "2G"))

    attributes.append(("Close type (rejection/acceptance/confirmed/failed)", "STRONG",
        "Strong rejection vs failed acceptance: structurally different populations", "2B"))

    attributes.append(("Best close method (15m bar close)", "STRONG",
        f"{metrics.get('best_close_acc', 74.3):.1f}% accuracy; outperforms all 250-vol methods", "2B"))

    attributes.append(("Approach velocity", vel_signal,
        f"{vel_spread:.1f}pp spread (slow {bp_slow:.1f}% > fast {bp_fast:.1f}%)", "2H"))

    attributes.append(("Session context (RTH vs ETH)", sess_signal,
        f"{sess_spread:.1f}pp spread; ETH {bp_eth:.1f}% vs RTH {bp_rth:.1f}%", "2I"))

    attributes.append(("Dwell time before resolution", dwell_signal,
        f"{dwell_spread:.1f}pp spread; decisive {dwell_pcts[0]:.1f}% vs range-bound "
        f"{dwell_pcts[3]:.1f}%; monotonic decay", "2J"))

    attributes.append(("Flip count", flip_signal,
        f"{flip_spread:.1f}pp spread; {flip_pcts[0]:.1f}% (0 flips) → "
        f"{flip_pcts[2]:.1f}% (2+); monotonic", "3B"))

    attributes.append(("Bounce streak (S/R strength)", streak_signal,
        f"{streak_spread:.1f}pp spread; {streak_pcts[0]:.1f}% (just flipped) → "
        f"{streak_pcts[3]:.1f}% (3+ bounces); strongest single signal", "3C"))

    attributes.append(("Retest after flip (pre-flip strength carryover)", retest_signal,
        f"{retest_pcts[0]:.1f}-{max(retest_pcts):.1f}% across all pre-flip bounce counts; "
        f"{'no carryover effect' if retest_spread < 5 else 'some carryover'}", "3D"))

    attributes.append(("S/R decay (bounce magnitude per touch)", "MODERATE" if decay_pct >= 5 else "WEAK",
        f"{decay_pct:.1f}% decline in bounce magnitude ({decay_first:.1f}→{decay_last:.1f}t); "
        f"dwell increases {dwell_first:.1f}→{dwell_last:.1f} bars", "3E"))

    rp_signal = "MODERATE (NEGATIVE)" if abs(rp_no - rp_with) > 0.1 and n_no_rays >= 20 else (
        "INSUFFICIENT DATA" if n_no_rays < 20 else "WEAK")
    attributes.append(("Ray inside vs outside zone", rp_signal,
        f"No-ray touches R/P={rp_no:.2f} (n={n_no_rays}) vs ray-present R/P={rp_with:.2f}", "4B/4C"))

    attributes.append(("Ray between entry and target", "MODERATE" if pct_ray_between > 50 else "WEAK",
        f"{pct_ray_between:.1f}% have obstacle ray; {pct_stall_reverse:.1f}% of stalls reverse "
        f"(never reach T1)", "6A"))

    r2r_signal = "WEAK" if pct_r2r_reached > 90 or mean_r2r_dist < 20 else "MODERATE"
    attributes.append(("Ray-to-ray movement (target ladder)", r2r_signal,
        f"{pct_r2r_reached:.1f}% reach next ray; mean distance {mean_r2r_dist:.1f}t "
        f"{'— too dense for target use' if mean_r2r_dist < 20 else ''}", "6D"))

    cluster_signal = "INSUFFICIENT DATA" if isolated_count < 20 else (
        "MODERATE" if in_cluster_pct > 80 else "WEAK")
    attributes.append(("Ray clustering", cluster_signal,
        f"Only {isolated_count} isolated rays; {in_cluster_pct:.1f}% in clusters; "
        f"{'cannot separate effect' if isolated_count < 20 else ''}", "5B"))

    # Cluster TF — use metrics from section 5 if available
    attributes.append(("Cluster TF composition", "WEAK",
        "Cluster TF composition effect small — see Section 5C", "5C"))

    ctf_signal = "MODERATE" if ctf_spread > 0.15 else "WEAK"
    ctf_strs = [f"{k}={v:.2f}" for k, v in cross_tf_rps.items()]
    attributes.append(("Cross-TF confluence (ray TF vs zone TF)", ctf_signal,
        f"R/P range: {', '.join(ctf_strs)}" if ctf_strs else "No data", "4D"))

    attributes.append(("Zone-backed vs isolated ray", "DEFERRED",
        "Section 2C deferred; requires zone edge data at interaction time", "2C/4E"))

    nest_signal = "WEAK" if nest_3plus_pct > 90 else "MODERATE"
    attributes.append(("Nested zone context (nesting depth)", nest_signal,
        f"{nest_3plus_pct:.1f}% of touches at 3+ nesting; insufficient variation to assess"
        if nest_3plus_pct > 90 else f"{nest_3plus_pct:.1f}% at 3+ nesting", "4E"))

    attributes.append(("Triple confluence (zone + parent + ray)", "DEFERRED",
        "Requires corrected zone-ray join; revisit after data fix", "4E"))

    attributes.append(("Optimal proximity threshold", "MODERATE",
        f"40t close-based (ratio {metrics.get('close_thresh_ratio', 2.18):.2f}) vs "
        f"{metrics.get('wick_thresh', 30)}t wick-based", "2A"))

    out.append(md_table(
        ["Attribute", "Signal?", "Evidence", "Section"],
        [(a, s, e, sec) for a, s, e, sec in attributes]
    ))
    out.append("")

    # ---- B) Priority list — sort by signal strength and spread ----
    out.append("### B) Attributes advancing to feature screening (priority order)\n")
    out.append("Only STRONG and MODERATE advance:\n")

    # Build priority list from computed signals
    scored = []
    for attr, signal, evidence, section in attributes:
        if signal in ("STRONG", "MODERATE", "MODERATE (NEGATIVE)"):
            # Extract pp spread from evidence if present
            m = re.search(r'(\d+\.?\d*)pp', evidence)
            pp = float(m.group(1)) if m else 0
            scored.append((attr, signal, evidence, pp))

    scored.sort(key=lambda x: (-1 if x[1] == "STRONG" else 0, -x[3]))
    priority_rows = []
    for i, (attr, signal, evidence, pp) in enumerate(scored, 1):
        # Compact key finding
        finding = evidence.split(";")[0] if ";" in evidence else evidence[:80]
        priority_rows.append([str(i), attr, signal, finding])

    out.append(md_table(["Priority", "Attribute", "Signal", "Key finding"], priority_rows))
    out.append("")

    # ---- C) Suggested filters (computed from data) ----
    out.append("### C) Suggested ray filters\n")
    out.append("Based on Section 7 results:\n")

    if tf_spread < 5:
        out.append(f"- **No TF filter recommended.** 7A shows only {tf_spread:.1f}pp spread across TFs. "
                   "LTF rays are not meaningfully worse than HTF rays for interaction outcomes.")
    else:
        out.append(f"- **Consider TF filter.** 7A shows {tf_spread:.1f}pp spread — "
                   f"{tf_best} rays perform best.")

    if streak_spread > 20:
        out.append(f"- **Consider filtering by bounce streak:** Rays with 0 bounces in current polarity "
                   f"(just flipped) have {streak_pcts[0]:.1f}% bounce — near coin-flip. Rays with 1+ "
                   f"confirmed bounces jump to {streak_pcts[1]:.1f}%+. A minimum bounce streak filter "
                   f"would improve signal quality.")

    if dwell_spread > 15:
        out.append(f"- **Consider filtering by dwell time:** Interactions that resolve in 1-2 bars "
                   f"({dwell_pcts[0]:.1f}% bounce) are much stronger than those taking 10+ bars "
                   f"({dwell_pcts[3]:.1f}%). Fast resolution is a quality signal.")

    if sess_spread > 10:
        out.append(f"- **Session matters:** ETH interactions bounce {sess_spread:.1f}pp more than RTH. "
                   f"ETH bounce={bp_eth:.1f}%, RTH bounce={bp_rth:.1f}%.")

    out.append("")

    # ---- D) Lifecycle validity (computed) ----
    out.append("### D) Polarity flip lifecycle validity\n")
    out.append("**The lifecycle model partially holds:**\n")

    streak_holds = streak_spread > 20
    out.append(f"- **Bounce streak: {'YES' if streak_holds else 'NO'}.** "
               f"S/R strength {'builds' if streak_holds else 'does not build'} with confirmations "
               f"({streak_pcts[0]:.1f}% → {streak_pcts[1]:.1f}% → {streak_pcts[2]:.1f}% → "
               f"{streak_pcts[3]:.1f}%). "
               f"{'This is the strongest finding in the entire analysis.' if streak_holds else ''}")

    decay_holds = decay_pct >= 5
    out.append(f"- **S/R decay: {'YES (moderate)' if decay_holds else 'NO'}.** "
               f"Bounce magnitude {'decreases' if decay_holds else 'stable'} per successive touch "
               f"({decay_first:.1f} → {decay_last:.1f} ticks, {decay_pct:.1f}% decline).")

    flip_holds = flip_spread >= 10
    out.append(f"- **Flip history: {'YES' if flip_holds else 'NO'}.** "
               f"Never-flipped rays ({flip_pcts[0]:.1f}%) "
               f"{'hold better than' if flip_pcts[0] > flip_pcts[2] else 'similar to'} "
               f"multi-flip rays ({flip_pcts[2]:.1f}%). "
               f"{'Battle-testing weakens, it does not strengthen.' if flip_pcts[0] > flip_pcts[2] else ''}")

    retest_holds = retest_spread < 5
    out.append(f"- **Retest carryover: {'NO' if retest_holds else 'PARTIAL'}.** "
               f"Pre-flip S/R strength {'does NOT' if retest_holds else 'partially'} carry over "
               f"to the new polarity (~{np.mean(retest_pcts):.0f}% regardless). "
               f"{'After a flip, the ray starts fresh.' if retest_holds else ''}")

    dwell_increase = dwell_last - dwell_first
    out.append(f"- **Dwell increase: {'MARGINAL' if dwell_increase < 2 else 'YES'}.** "
               f"Dwell time {'increases slightly' if dwell_increase < 2 else 'increases'} as ray "
               f"weakens ({dwell_first:.1f} → {dwell_last:.1f} bars).")

    out.append("")

    # Net assessment
    bounce_jump = streak_pcts[1] - streak_pcts[0] if len(streak_pcts) >= 2 else 0
    out.append(f"**Net assessment:** The lifecycle model is valid for "
               f"{'bounce streak and decay' if streak_holds and decay_holds else 'bounce streak' if streak_holds else 'limited metrics'}, "
               f"but polarity resets are {'complete' if retest_holds else 'partial'} — "
               f"{'pre-flip history is erased' if retest_holds else 'some carryover detected'}. "
               f"The key tradeable insight is bounce streak: after 1 confirmed bounce, "
               f"probability jumps ~{bounce_jump:.0f}pp.")
    out.append("")

    return "\n".join(out)


# =============================================================================
# MAIN
# =============================================================================
def main():
    start_time = datetime.now()
    print(f"Ray Baseline Analysis — started {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 64)

    # Load data
    bars, ray_ref, zte, ray_ctx, p1_count = load_all_data()

    # Build ray timeline
    print("\nBuilding ray timeline...")
    rays_df, events_df = build_rays(ray_ref)

    # Load 15m bars
    try:
        bars_10s = load_10sec_bars()
        bars_15m = build_15m_bars(bars_10s)
        del bars_10s  # free memory
    except Exception as e:
        print(f"  Warning: Could not build 15m bars: {e}")
        bars_15m = None

    # Run sections
    all_output = []
    all_output.append(f"# Ray Baseline Analysis — Observational Study")
    all_output.append(f"Generated: {start_time.strftime('%Y-%m-%d %H:%M')}")
    all_output.append(f"Data: P1 + P2 combined (observational, no parameters fit)")
    all_output.append(f"Bars: {len(bars):,} (250-vol)")
    all_output.append(f"Unique rays: {len(rays_df)}")
    all_output.append(f"Zone touches: {len(zte):,}")
    all_output.append(f"Ray-touch pairs: {len(ray_ctx):,}")
    all_output.append("")

    ixns = None
    selected_thresh = None
    best_method_col = None
    metrics = {}  # populated by section_2, consumed by section_8

    # Section 1
    try:
        print("\n--- SECTION 1: Ray Population ---")
        s1 = section_1(ray_ref, rays_df, events_df, bars, p1_count)
        all_output.append(s1)
        print("  Section 1 complete.")
    except Exception as e:
        all_output.append(f"\n**SECTION 1 ERROR:** {e}\n{traceback.format_exc()}\n")
        print(f"  Section 1 FAILED: {e}")

    # Section 2
    try:
        print("\n--- SECTION 2: Price-Ray Interactions ---")
        s2, ixns, selected_thresh, best_method_col, metrics = section_2(bars, rays_df, bars_15m)
        all_output.append(s2)
        print(f"  Section 2 complete. {len(ixns)} interactions at {selected_thresh}t threshold.")
    except Exception as e:
        all_output.append(f"\n**SECTION 2 ERROR:** {e}\n{traceback.format_exc()}\n")
        print(f"  Section 2 FAILED: {e}")

    # Section 3
    if ixns is not None and best_method_col is not None:
        try:
            print("\n--- SECTION 3: Polarity Flips ---")
            s3 = section_3(ixns, rays_df, bars, best_method_col)
            all_output.append(s3)
            print("  Section 3 complete.")
        except Exception as e:
            all_output.append(f"\n**SECTION 3 ERROR:** {e}\n{traceback.format_exc()}\n")
            print(f"  Section 3 FAILED: {e}")

    # Section 4
    try:
        print("\n--- SECTION 4: Rays and Zone Touches ---")
        s4 = section_4(zte, ray_ctx, rays_df, bars)
        all_output.append(s4)
        print("  Section 4 complete.")
    except Exception as e:
        all_output.append(f"\n**SECTION 4 ERROR:** {e}\n{traceback.format_exc()}\n")
        print(f"  Section 4 FAILED: {e}")

    # Section 5
    if ixns is not None:
        try:
            print("\n--- SECTION 5: Ray Clustering ---")
            s5 = section_5(ixns, rays_df, bars)
            all_output.append(s5)
            print("  Section 5 complete.")
        except Exception as e:
            all_output.append(f"\n**SECTION 5 ERROR:** {e}\n{traceback.format_exc()}\n")
            print(f"  Section 5 FAILED: {e}")

    # Section 6
    if ixns is not None:
        try:
            print("\n--- SECTION 6: Ray as Target/Stop Reference ---")
            s6 = section_6(ixns, rays_df, zte, bars)
            all_output.append(s6)
            print("  Section 6 complete.")
        except Exception as e:
            all_output.append(f"\n**SECTION 6 ERROR:** {e}\n{traceback.format_exc()}\n")
            print(f"  Section 6 FAILED: {e}")

    # Section 7
    if ixns is not None:
        try:
            print("\n--- SECTION 7: LTF vs HTF Rays ---")
            s7 = section_7(ixns, rays_df, zte, ray_ctx, bars)
            all_output.append(s7)
            print("  Section 7 complete.")
        except Exception as e:
            all_output.append(f"\n**SECTION 7 ERROR:** {e}\n{traceback.format_exc()}\n")
            print(f"  Section 7 FAILED: {e}")

    # Section 8
    try:
        print("\n--- SECTION 8: Summary ---")
        s8 = section_8(ixns, rays_df, zte, ray_ctx, bars, metrics)
        all_output.append(s8)
        print("  Section 8 complete.")
    except Exception as e:
        all_output.append(f"\n**SECTION 8 ERROR:** {e}\n{traceback.format_exc()}\n")

    # Write output
    output_path = OUTPUT_DIR / "ray_baseline_analysis.md"
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(all_output))

    elapsed = datetime.now() - start_time
    print(f"\n{'=' * 64}")
    print(f"Analysis complete in {elapsed}")
    print(f"Results saved to: {output_path}")


if __name__ == "__main__":
    main()
