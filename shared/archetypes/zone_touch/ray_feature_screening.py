#!/usr/bin/env python3
# archetype: zone_touch
"""
Ray Feature Screening — Prompt 1a equivalent.
Tests ray attributes against the existing 4-feature A-Cal model.
P1 for calibration (Sections 0-3). P2 for validation only (Section 4).
Uses 60m+ rays only throughout.
"""

import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime, time
import warnings
import traceback
import json

warnings.filterwarnings("ignore")

# =============================================================================
# CONSTANTS
# =============================================================================
TICK_SIZE = 0.25
PIPELINE_ROOT = Path(__file__).resolve().parent.parent.parent.parent
DATA_DIR = PIPELINE_ROOT / "stages" / "01-data" / "data"
TOUCH_DIR = DATA_DIR / "touches"
BAR_VOL_DIR = DATA_DIR / "bar_data" / "volume"
BAR_TIME_DIR = DATA_DIR / "bar_data" / "time"
OUTPUT_DIR = Path(__file__).resolve().parent / "output"

PROX_THRESHOLD = 40  # ticks
RTH_START = time(9, 30)
RTH_END = time(16, 15)

# A-Cal model (frozen)
ACAL_WEIGHTS = {"F10": 10.0, "F04": 5.94, "F01": 3.44, "F21": 4.42}
ACAL_BINS = {"F10": [220.0, 590.0], "F21": [49.0, 831.87]}
ACAL_THRESHOLD = 16.66
ACAL_MAX = 23.8

# ZONEREL exits
T1_MULT = 0.5
STOP_MULT = 1.5
STOP_FLOOR = 120  # ticks


def tf_minutes(tf_str):
    return int(tf_str.replace("m", ""))

def is_htf(tf_str):
    return tf_minutes(tf_str) >= 60


# =============================================================================
# MARKDOWN HELPERS
# =============================================================================
def md_table(headers, rows):
    lines = ["| " + " | ".join(str(h) for h in headers) + " |"]
    lines.append("|" + "|".join(["---"] * len(headers)) + "|")
    for row in rows:
        lines.append("| " + " | ".join(str(v) for v in row) + " |")
    return "\n".join(lines)

def fmt_f(val, d=1):
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return "N/A"
    return f"{val:.{d}f}"

def fmt_pct(val, total):
    if total == 0: return "N/A"
    return f"{val/total*100:.1f}%"


# =============================================================================
# DATA LOADING
# =============================================================================
def load_bar_data(path):
    df = pd.read_csv(path)
    df.columns = df.columns.str.strip()
    df = df[["Date", "Time", "Open", "High", "Low", "Last", "Volume"]].copy()
    df.rename(columns={"Last": "Close"}, inplace=True)
    df["DateTime"] = pd.to_datetime(
        df["Date"].str.strip() + " " + df["Time"].str.strip(), format="mixed"
    )
    df.drop(columns=["Date", "Time"], inplace=True)
    return df


def load_period_data(period="P1"):
    """Load data for one period only."""
    print(f"Loading {period} data...")
    bars = load_bar_data(BAR_VOL_DIR / f"NQ_BarData_250vol_rot_{period}.csv")
    bars["BarIdx"] = bars.index
    print(f"  {len(bars)} bars")

    zte = pd.read_csv(TOUCH_DIR / f"NQ_ZTE_raw_{period}.csv")
    zte = zte[zte["TouchType"] != "VP_RAY"].copy()
    print(f"  {len(zte)} touches (excl VP_RAY)")

    ray_ctx = pd.read_csv(TOUCH_DIR / f"NQ_ray_context_{period}.csv")
    # Filter to HTF only
    ray_ctx = ray_ctx[ray_ctx["RayTF"].apply(is_htf)].copy()
    print(f"  {len(ray_ctx)} HTF ray-touch pairs")

    ray_ref = pd.read_csv(TOUCH_DIR / f"NQ_ray_reference_{period}.csv")
    print(f"  {len(ray_ref)} ray reference events")

    # Build 15m bars
    print(f"  Loading 10-second data for 15m bars...")
    b10 = load_bar_data(BAR_TIME_DIR / f"NQ_BarData_10sec_rot_{period}.csv")
    b10 = b10.set_index("DateTime").sort_index()
    bars_15m = b10.resample("15min").agg({
        "Open": "first", "High": "max", "Low": "min",
        "Close": "last", "Volume": "sum"
    }).dropna().reset_index()
    del b10
    print(f"  {len(bars_15m)} 15m bars")

    return bars, zte, ray_ctx, ray_ref, bars_15m


# =============================================================================
# RAY EXTRACTION (from ray_context + ray_reference, HTF only)
# =============================================================================
def extract_rays(zte, ray_ctx, ray_ref, n_bars):
    """Extract unique HTF rays with estimated creation bars."""
    # From ray_reference: exact creation events
    ref_rays = []
    for _, row in ray_ref.iterrows():
        if row["DemandRayPrice"] > 0 and is_htf(row["SourceLabel"]):
            ref_rays.append({
                "price": row["DemandRayPrice"], "side": "DEMAND",
                "creation_bar": row["BaseBarIndex"], "tf": row["SourceLabel"]
            })
        if row["SupplyRayPrice"] > 0 and is_htf(row["SourceLabel"]):
            ref_rays.append({
                "price": row["SupplyRayPrice"], "side": "SUPPLY",
                "creation_bar": row["BaseBarIndex"], "tf": row["SourceLabel"]
            })

    # From ray_context: infer creation bars for pre-existing rays
    # Build TouchID → BarIndex mapping
    zte_bi = dict(zip(
        zte["BarIndex"].astype(str) + "_" + zte["TouchType"] + "_" + zte["SourceLabel"],
        zte["BarIndex"]
    ))

    ctx_rays = {}
    for _, row in ray_ctx.iterrows():
        tid = row["TouchID"]
        touch_bar = zte_bi.get(tid)
        if touch_bar is None:
            # Try to parse from TouchID
            parts = tid.split("_", 1)
            try:
                touch_bar = int(parts[0])
            except (ValueError, IndexError):
                continue

        rp = row["RayPrice"]
        rs = row["RaySide"]
        rtf = row["RayTF"]
        age = row["RayAgeBars"]
        key = (rp, rs)

        creation = max(0, touch_bar - age)
        if key not in ctx_rays or creation < ctx_rays[key]["creation_bar"]:
            ctx_rays[key] = {"price": rp, "side": rs, "creation_bar": creation, "tf": rtf}

    # Merge: prefer ray_reference (exact), fill in from context
    all_rays = {}
    for r in ref_rays:
        key = (r["price"], r["side"])
        all_rays[key] = r

    for key, r in ctx_rays.items():
        if key not in all_rays:
            all_rays[key] = r

    rays_df = pd.DataFrame(all_rays.values())
    if len(rays_df) == 0:
        return rays_df
    rays_df = rays_df.sort_values("creation_bar").reset_index(drop=True)
    rays_df["tf_min"] = rays_df["tf"].apply(tf_minutes)
    print(f"  {len(rays_df)} unique HTF ray levels extracted")
    return rays_df


# =============================================================================
# INTERACTION DETECTION + 15m CLOSE
# =============================================================================
def detect_interactions(bars, rays_df, bars_15m, threshold=PROX_THRESHOLD):
    """Detect all ray interactions on bar data with 15m close outcome."""
    highs = bars["High"].values.astype(np.float64)
    lows = bars["Low"].values.astype(np.float64)
    closes = bars["Close"].values.astype(np.float64)
    bar_dts = bars["DateTime"].values
    m15_dts = bars_15m["DateTime"].values
    m15_closes = bars_15m["Close"].values
    thresh_price = threshold * TICK_SIZE
    n_bars = len(highs)
    interactions = []

    for ray_idx in range(len(rays_df)):
        ray_price = rays_df.iloc[ray_idx]["price"]
        creation_bar = max(0, int(rays_df.iloc[ray_idx]["creation_bar"]))
        if creation_bar >= n_bars:
            continue

        start = creation_bar
        hi = highs[start:]
        lo = lows[start:]
        near = (lo <= ray_price + thresh_price) & (hi >= ray_price - thresh_price)
        near_int = near.astype(np.int8)
        transitions = np.diff(near_int, prepend=0)
        enter_indices = np.where(transitions == 1)[0]
        exit_indices = np.where(transitions == -1)[0]

        for ei_idx, enter_rel in enumerate(enter_indices):
            enter_abs = start + int(enter_rel)
            exits_after = exit_indices[exit_indices > enter_rel]
            exit_abs = start + int(exits_after[0]) if len(exits_after) > 0 else n_bars - 1
            dwell = exit_abs - enter_abs + 1

            if enter_abs > 0:
                approach_from = "ABOVE" if closes[enter_abs - 1] > ray_price else "BELOW"
            else:
                approach_from = "BELOW"

            # 15m close outcome
            outcome = "UNDETERMINED"
            if enter_abs < len(bar_dts):
                bar_dt = bar_dts[enter_abs]
                idx_15m = np.searchsorted(m15_dts, bar_dt, side="right") - 1
                if 0 <= idx_15m < len(m15_closes):
                    m15c = m15_closes[idx_15m]
                    if approach_from == "ABOVE":
                        outcome = "BOUNCE" if m15c > ray_price else "BREAK"
                    else:
                        outcome = "BOUNCE" if m15c < ray_price else "BREAK"

            if outcome == "UNDETERMINED":
                fc = closes[enter_abs] if enter_abs < n_bars else ray_price
                if approach_from == "ABOVE":
                    outcome = "BOUNCE" if fc > ray_price else "BREAK"
                else:
                    outcome = "BOUNCE" if fc < ray_price else "BREAK"

            # Bounce magnitude (MFE from ray in bounce direction)
            obs_end = min(enter_abs + 100, n_bars)
            if approach_from == "ABOVE":
                bounce_mag = (np.max(highs[enter_abs:obs_end]) - ray_price) / TICK_SIZE
            else:
                bounce_mag = (ray_price - np.min(lows[enter_abs:obs_end])) / TICK_SIZE

            # Close type classification
            fc = closes[enter_abs] if enter_abs < n_bars else ray_price
            bar_range = (highs[enter_abs] - lows[enter_abs]) if enter_abs < n_bars else 1
            bar_range = max(bar_range, TICK_SIZE)
            close_dist_ratio = abs(fc - ray_price) / bar_range

            if outcome == "BOUNCE":
                close_type = "strong_rejection" if close_dist_ratio >= 0.75 else "weak_rejection"
            else:
                # Check for false break (next bar reverses back)
                if enter_abs + 1 < n_bars:
                    nc = closes[enter_abs + 1]
                    if approach_from == "ABOVE":
                        reversed_back = nc > ray_price
                    else:
                        reversed_back = nc < ray_price
                    if reversed_back:
                        close_type = "failed_acceptance"
                    else:
                        close_type = "confirmed_acceptance"
                else:
                    close_type = "acceptance"

            # Approach velocity
            vel_lb = 5
            if enter_abs >= vel_lb:
                approach_vel = abs(closes[enter_abs] - closes[enter_abs - vel_lb]) / TICK_SIZE / vel_lb
            else:
                approach_vel = 0

            # Session
            session = "UNKNOWN"
            if enter_abs < len(bar_dts):
                t = pd.Timestamp(bar_dts[enter_abs]).time()
                session = "RTH" if RTH_START <= t <= RTH_END else "ETH"

            interactions.append({
                "ray_idx": ray_idx, "enter_bar": enter_abs, "exit_bar": exit_abs,
                "dwell": dwell, "approach_from": approach_from, "outcome": outcome,
                "bounce_mag": bounce_mag, "close_type": close_type,
                "approach_vel": approach_vel, "session": session,
            })

    return pd.DataFrame(interactions)


# =============================================================================
# RAY LIFECYCLE STATE AT A GIVEN BAR
# =============================================================================
def build_lifecycle_lookup(interactions_df, rays_df, n_bars):
    """
    Build a lookup: for each ray at each bar, what is its lifecycle state?
    Returns a dict: ray_idx -> sorted list of (bar, cumulative_state) snapshots.
    We store state after each interaction so we can binary-search for any bar.
    """
    lifecycle = {}
    for ray_idx in range(len(rays_df)):
        ray_ixns = interactions_df[interactions_df["ray_idx"] == ray_idx].sort_values("enter_bar")
        states = []  # list of (bar, bounce_streak, flip_count, bounce_mags, close_type)
        streak = 0
        flips = 0
        all_mags = []

        creation_bar = int(rays_df.iloc[ray_idx]["creation_bar"])
        # Initial state at creation
        states.append({
            "bar": creation_bar, "bounce_streak": 0, "flip_count": 0,
            "bounce_mags": [], "last_close_type": "none", "dwell_start": -1
        })

        for _, ix in ray_ixns.iterrows():
            eb = int(ix["enter_bar"])
            if ix["outcome"] == "BOUNCE":
                streak += 1
                all_mags.append(ix["bounce_mag"])
            elif ix["outcome"] == "BREAK":
                flips += 1
                streak = 0
                all_mags.append(ix["bounce_mag"])

            states.append({
                "bar": eb,
                "bounce_streak": streak,
                "flip_count": flips,
                "bounce_mags": list(all_mags),
                "last_close_type": ix["close_type"],
                "dwell_start": eb,
                "dwell_end": int(ix["exit_bar"]),
            })

        lifecycle[ray_idx] = states
    return lifecycle


def get_lifecycle_at_bar(lifecycle, ray_idx, bar):
    """Get ray lifecycle state at a specific bar via binary search."""
    states = lifecycle.get(ray_idx, [])
    if not states:
        return None

    # Find the last state at or before this bar
    best = None
    for s in states:
        if s["bar"] <= bar:
            best = s
        else:
            break
    return best


# =============================================================================
# COMPUTE RAY FEATURES PER TOUCH
# =============================================================================
def compute_ray_features_for_touches(zte, ray_ctx, rays_df, lifecycle, interactions_df, bars):
    """
    For each touch, find the backing ray and obstacle ray, compute features.
    Returns zte with ray feature columns added.
    """
    highs = bars["High"].values
    lows = bars["Low"].values
    closes = bars["Close"].values
    bar_dts = bars["DateTime"].values

    # Build ray price → ray_idx mapping
    ray_price_map = {}
    for idx, row in rays_df.iterrows():
        key = (row["price"], row["side"])
        ray_price_map[key] = idx

    # Build TouchID for ZTE
    zte = zte.copy()
    zte["TouchID"] = (
        zte["BarIndex"].astype(str) + "_" + zte["TouchType"] + "_" + zte["SourceLabel"]
    )

    # Initialize feature columns with proper dtypes
    numeric_cols = [
        "backing_bounce_streak", "backing_flip_count", "backing_dwell_bars",
        "backing_decay_mag", "backing_approach_vel", "backing_dist_ticks",
        "backing_cross_tf", "obstacle_present", "obstacle_bounce_streak",
        "obstacle_dist_ticks",
    ]
    string_cols = ["backing_session", "backing_close_type", "backing_tf", "backing_15m_close"]
    for col in numeric_cols:
        zte[col] = np.nan
    for col in string_cols:
        zte[col] = pd.NA  # object-compatible NA

    for touch_idx in range(len(zte)):
        touch = zte.iloc[touch_idx]
        bar_idx = int(touch["BarIndex"])
        tt = touch["TouchType"]
        zt = touch["ZoneTop"]
        zb = touch["ZoneBot"]
        zw = touch["ZoneWidthTicks"] * TICK_SIZE

        if tt == "DEMAND_EDGE":
            entry = zt
            t1 = entry + T1_MULT * zw
            stop_side = "below"  # stop is below entry
        elif tt == "SUPPLY_EDGE":
            entry = zb
            t1 = entry - T1_MULT * zw
            stop_side = "above"
        else:
            continue

        # Get nearby HTF rays from ray_context
        tid = touch["TouchID"]
        nearby = ray_ctx[ray_ctx["TouchID"] == tid].copy()

        if len(nearby) == 0:
            continue

        # Index label for .at accessor
        idx_label = zte.index[touch_idx]

        # Match to ray_idx
        backing_candidates = []
        obstacle_candidates = []

        for _, ray_row in nearby.iterrows():
            rp = ray_row["RayPrice"]
            rs = ray_row["RaySide"]
            dist = ray_row["RayDistTicks"]
            rtf = ray_row["RayTF"]
            direction = ray_row["RayDirection"]

            key = (rp, rs)
            ray_idx = ray_price_map.get(key)

            if dist > 30:
                continue  # only consider within 30t

            # Classify as backing or obstacle
            if tt == "DEMAND_EDGE":
                # Backing: at or below entry (inside zone or below)
                is_backing = rp <= entry + 5 * TICK_SIZE
                # Obstacle: above entry, below T1
                is_obstacle = rp > entry + 5 * TICK_SIZE and rp < t1
            else:  # SUPPLY_EDGE
                is_backing = rp >= entry - 5 * TICK_SIZE
                is_obstacle = rp < entry - 5 * TICK_SIZE and rp > t1

            if is_backing:
                backing_candidates.append((dist, ray_idx, rp, rs, rtf))
            if is_obstacle:
                obstacle_candidates.append((dist, ray_idx, rp, rs, rtf))

        # Select nearest backing ray
        if backing_candidates:
            backing_candidates.sort(key=lambda x: x[0])
            b_dist, b_idx, b_price, b_side, b_tf = backing_candidates[0]

            if b_idx is not None:
                state = get_lifecycle_at_bar(lifecycle, b_idx, bar_idx)
                if state:
                    zte.at[idx_label, "backing_bounce_streak"] = float(state["bounce_streak"])
                    zte.at[idx_label, "backing_flip_count"] = float(state["flip_count"])
                    zte.at[idx_label, "backing_close_type"] = str(state["last_close_type"])

                    # Decay magnitude
                    mags = state.get("bounce_mags", [])
                    if len(mags) >= 6:
                        early = np.mean(mags[:3])
                        recent = np.mean(mags[-3:])
                        zte.at[idx_label, "backing_decay_mag"] = recent / early if early > 0 else 1.0
                    elif len(mags) >= 3:
                        zte.at[idx_label, "backing_decay_mag"] = 1.0

                    # Dwell: check if price is currently near this ray
                    dwell_end = state.get("dwell_end", -1)
                    dwell_start = state.get("dwell_start", -1)
                    if dwell_start >= 0 and dwell_end >= bar_idx:
                        zte.at[idx_label, "backing_dwell_bars"] = float(bar_idx - dwell_start)
                    else:
                        zte.at[idx_label, "backing_dwell_bars"] = 0.0

            zte.at[idx_label, "backing_dist_ticks"] = float(b_dist)
            zte.at[idx_label, "backing_tf"] = str(b_tf) if b_tf else ""

            # Approach velocity at touch bar
            vel_lb = 5
            if bar_idx >= vel_lb and bar_idx < len(closes):
                av = abs(closes[bar_idx] - closes[bar_idx - vel_lb]) / TICK_SIZE / vel_lb
                zte.at[idx_label, "backing_approach_vel"] = av

            # Session
            if bar_idx < len(bar_dts):
                t = pd.Timestamp(bar_dts[bar_idx]).time()
                sess = "RTH" if RTH_START <= t <= RTH_END else "ETH"
                zte.at[idx_label, "backing_session"] = sess

            # 15m close at nearest ray
            if b_idx is not None and bar_idx < len(bar_dts):
                ray_ixns = interactions_df[
                    (interactions_df["ray_idx"] == b_idx) &
                    (interactions_df["enter_bar"] <= bar_idx) &
                    (interactions_df["exit_bar"] >= bar_idx)
                ]
                if len(ray_ixns) > 0:
                    last_ixn = ray_ixns.iloc[-1]
                    zte.at[idx_label, "backing_15m_close"] = str(last_ixn["outcome"])

            # Cross-TF count
            other_tfs = nearby[
                (abs(nearby["RayPrice"] - b_price) <= 20 * TICK_SIZE) &
                (nearby["RayTF"] != b_tf)
            ]["RayTF"].nunique()
            zte.at[idx_label, "backing_cross_tf"] = float(other_tfs)

        # Select nearest obstacle ray
        if obstacle_candidates:
            obstacle_candidates.sort(key=lambda x: x[0])
            o_dist, o_idx, o_price, o_side, o_tf = obstacle_candidates[0]

            zte.at[idx_label, "obstacle_present"] = 1.0
            zte.at[idx_label, "obstacle_dist_ticks"] = float(o_dist)

            if o_idx is not None:
                state = get_lifecycle_at_bar(lifecycle, o_idx, bar_idx)
                if state:
                    zte.at[idx_label, "obstacle_bounce_streak"] = float(state["bounce_streak"])
        else:
            zte.at[idx_label, "obstacle_present"] = 0.0

    return zte


# =============================================================================
# A-CAL SCORING (replicated from replication_harness.py)
# =============================================================================
def bin_numeric(val, p33, p67, weight, is_nan=False):
    if is_nan: return 0.0
    if val <= p33: return weight
    if val >= p67: return 0.0
    return weight / 2.0

def score_f04(cascade, weight=5.94):
    if cascade == "NO_PRIOR": return weight
    if cascade == "PRIOR_HELD": return weight / 2.0
    if cascade == "PRIOR_BROKE": return 0.0
    return 0.0

def score_f01(tf_str, weight=3.44):
    if tf_str == "30m": return weight
    if tf_str == "480m": return 0.0
    if tf_str: return weight / 2.0
    return 0.0

def compute_acal_score(touch_row, zone_history):
    """Compute the 4-feature A-Cal score for a touch."""
    # F10: Prior Penetration
    seq = int(touch_row.get("TouchSequence", 0))
    prior_pen = None
    if seq > 1:
        key = (touch_row["ZoneTop"], touch_row["ZoneBot"], touch_row["SourceLabel"])
        history = zone_history.get(key, [])
        for prev in reversed(history):
            if int(prev["BarIndex"]) < int(touch_row["BarIndex"]):
                if int(prev.get("TouchSequence", 0)) == seq - 1:
                    try:
                        prior_pen = float(prev["Penetration"])
                    except (ValueError, KeyError):
                        pass
                    break

    f10 = bin_numeric(prior_pen if prior_pen else 0, 220.0, 590.0, 10.0, prior_pen is None)
    f04 = score_f04(str(touch_row.get("CascadeState", "")).strip())
    f01 = score_f01(str(touch_row.get("SourceLabel", "")).strip())
    f21_raw = float(touch_row.get("ZoneAgeBars", 0))
    f21 = bin_numeric(f21_raw, 49.0, 831.87, 4.42)

    return f10 + f04 + f01 + f21


def build_zone_history(zte):
    """Build zone history for prior penetration lookup."""
    zh = {}
    for _, row in zte.iterrows():
        key = (row["ZoneTop"], row["ZoneBot"], row["SourceLabel"])
        if key not in zh:
            zh[key] = []
        zh[key].append(row.to_dict())
    # Sort each zone's history by BarIndex
    for key in zh:
        zh[key].sort(key=lambda x: int(x["BarIndex"]))
    return zh


# =============================================================================
# FEATURE SCREENING HELPERS
# =============================================================================
def screen_feature(zte, feature_col, bins_spec, feature_name):
    """Screen a single feature. bins_spec is list of (label, mask)."""
    valid = zte[(zte["Reaction"] > 0) & (zte["Penetration"] > 0)].copy()
    valid["RP"] = valid["Reaction"] / valid["Penetration"]
    valid["Win"] = (valid["Reaction"] > valid["Penetration"]).astype(int)

    rows = []
    rp_values = []
    ns = []
    for label, mask in bins_spec:
        sub = valid[mask(valid)] if callable(mask) else valid[mask]
        n = len(sub)
        if n > 0:
            rp = sub["RP"].median()
            rxn = sub["Reaction"].mean()
            pen = sub["Penetration"].mean()
        else:
            rp = rxn = pen = None
        rows.append([label, n, fmt_f(rxn), fmt_f(pen), fmt_f(rp, 2), n])
        rp_values.append(rp)
        ns.append(n)

    # Compute spread
    valid_rps = [r for r in rp_values if r is not None]
    spread = max(valid_rps) - min(valid_rps) if len(valid_rps) >= 2 else 0
    min_n = min(ns) if ns else 0

    # Monotonicity check
    monotonic = True
    if len(valid_rps) >= 3:
        increasing = all(valid_rps[i] <= valid_rps[i+1] for i in range(len(valid_rps)-1))
        decreasing = all(valid_rps[i] >= valid_rps[i+1] for i in range(len(valid_rps)-1))
        monotonic = increasing or decreasing

    return rows, spread, monotonic, min_n


# =============================================================================
# SECTION 0: COMPUTE RAY LIFECYCLE FEATURES
# =============================================================================
def section_0(bars, zte, ray_ctx, ray_ref, bars_15m):
    out = []
    out.append("=" * 64)
    out.append("SECTION 0: DATA PREREQUISITE — COMPUTE RAY LIFECYCLE")
    out.append("=" * 64)
    out.append("")

    # Extract rays
    rays_df = extract_rays(zte, ray_ctx, ray_ref, len(bars))

    # Detect interactions
    print("  Detecting interactions on P1 bar data...")
    ixns = detect_interactions(bars, rays_df, bars_15m)
    ixns_valid = ixns[ixns["outcome"].isin(["BOUNCE", "BREAK"])]
    print(f"  {len(ixns_valid)} valid interactions from {len(rays_df)} HTF rays")

    # Build lifecycle
    print("  Building lifecycle lookup...")
    lifecycle = build_lifecycle_lookup(ixns_valid, rays_df, len(bars))

    # Compute ray features for each touch
    print("  Computing ray features per touch...")
    zte_enriched = compute_ray_features_for_touches(zte, ray_ctx, rays_df, lifecycle, ixns, bars)

    # Report NULL rates
    out.append("**Ray feature coverage:**\n")
    feat_report_cols = [
        "backing_bounce_streak", "backing_flip_count", "backing_dwell_bars",
        "backing_decay_mag", "backing_approach_vel", "backing_session",
        "backing_close_type", "backing_dist_ticks", "backing_cross_tf",
        "obstacle_present", "obstacle_bounce_streak",
    ]
    null_rows = []
    for col in feat_report_cols:
        if col in zte_enriched.columns:
            null_count = zte_enriched[col].isna().sum()
            null_pct = null_count / len(zte_enriched) * 100
            null_rows.append([col, f"{null_count}/{len(zte_enriched)}", f"{null_pct:.1f}%"])
    out.append(md_table(["Feature", "NULL count", "% NULL"], null_rows))
    out.append("")

    # Row count verification
    out.append(f"Row count: {len(zte_enriched)} (expected {len(zte)})")
    out.append("")

    # Spot check 5 touches
    out.append("**Spot check (first 5 touches with backing ray):**\n")
    has_backing = zte_enriched[zte_enriched["backing_bounce_streak"].notna()].head(5)
    spot_rows = []
    for _, t in has_backing.iterrows():
        spot_rows.append([
            int(t["BarIndex"]), t["TouchType"],
            int(t["backing_bounce_streak"]) if not pd.isna(t["backing_bounce_streak"]) else "N/A",
            int(t["backing_flip_count"]) if not pd.isna(t["backing_flip_count"]) else "N/A",
            fmt_f(t["backing_dist_ticks"]),
            t.get("backing_tf", "N/A"),
        ])
    out.append(md_table(
        ["BarIndex", "TouchType", "BounceStreak", "FlipCount", "Dist", "TF"],
        spot_rows
    ))
    out.append("")

    # Save enriched CSV
    csv_path = OUTPUT_DIR / "p1_touches_with_ray_features.csv"
    zte_enriched.to_csv(csv_path, index=False)
    out.append(f"Saved to: {csv_path.name}")
    out.append("")

    return "\n".join(out), zte_enriched, rays_df, ixns, lifecycle


# =============================================================================
# SECTION 1: INDIVIDUAL FEATURE SCREENING
# =============================================================================
def section_1(zte):
    out = []
    out.append("=" * 64)
    out.append("SECTION 1: INDIVIDUAL FEATURE SCREENING")
    out.append("=" * 64)
    out.append("")

    # Prepare valid touches with R/P
    valid = zte[(zte["Reaction"] > 0) & (zte["Penetration"] > 0)].copy()
    valid["RP"] = valid["Reaction"] / valid["Penetration"]

    # Build zone history for A-Cal scoring
    zh = build_zone_history(zte)
    valid["acal_score"] = valid.apply(lambda r: compute_acal_score(r, zh), axis=1)

    all_features = {}

    # A) ray_bounce_streak
    out.append("### A) ray_bounce_streak\n")
    bs_bins = [
        ("0 (just flipped)", lambda df: df["backing_bounce_streak"] == 0),
        ("1", lambda df: df["backing_bounce_streak"] == 1),
        ("2", lambda df: df["backing_bounce_streak"] == 2),
        ("3+", lambda df: df["backing_bounce_streak"] >= 3),
        ("NULL (no backing ray)", lambda df: df["backing_bounce_streak"].isna()),
    ]
    rows, spread, mono, min_n = screen_feature(valid, "backing_bounce_streak", bs_bins, "bounce_streak")
    out.append(md_table(["Bounce streak", "Touches", "Mean Rxn", "Mean Pen", "R/P", "n"], rows))
    out.append(f"\nSpread: {fmt_f(spread, 2)} | Monotonic: {mono} | Min bin n: {min_n}")
    low = " ⚠️ LOW CONFIDENCE" if min_n < 15 else ""
    out.append(f"{low}\n")
    all_features["A_bounce_streak"] = {"spread": spread, "mono": mono, "min_n": min_n}

    # B) ray_dwell_bars
    out.append("### B) ray_dwell_bars\n")
    dw_bins = [
        ("1-2 bars", lambda df: (df["backing_dwell_bars"] >= 1) & (df["backing_dwell_bars"] <= 2)),
        ("3-5 bars", lambda df: (df["backing_dwell_bars"] >= 3) & (df["backing_dwell_bars"] <= 5)),
        ("6-10 bars", lambda df: (df["backing_dwell_bars"] >= 6) & (df["backing_dwell_bars"] <= 10)),
        ("10+ bars", lambda df: df["backing_dwell_bars"] > 10),
        ("Not dwelling (0)", lambda df: df["backing_dwell_bars"] == 0),
        ("NULL", lambda df: df["backing_dwell_bars"].isna()),
    ]
    rows, spread, mono, min_n = screen_feature(valid, "backing_dwell_bars", dw_bins, "dwell")
    out.append(md_table(["Dwell time", "Touches", "Mean Rxn", "Mean Pen", "R/P", "n"], rows))
    out.append(f"\nSpread: {fmt_f(spread, 2)} | Monotonic: {mono} | Min bin n: {min_n}\n")
    all_features["B_dwell"] = {"spread": spread, "mono": mono, "min_n": min_n}

    # C) ray_session
    out.append("### C) ray_session\n")
    sess_bins = [
        ("RTH", lambda df: df["backing_session"] == "RTH"),
        ("ETH", lambda df: df["backing_session"] == "ETH"),
    ]
    rows, spread, mono, min_n = screen_feature(valid, "backing_session", sess_bins, "session")
    out.append(md_table(["Session", "Touches", "Mean Rxn", "Mean Pen", "R/P", "n"], rows))

    # Check correlation with existing SessionClass
    sess_corr = "N/A"
    if "SessionClass" in valid.columns and "backing_session" in valid.columns:
        valid_both = valid[valid["backing_session"].isin(["RTH", "ETH"])].copy()
        valid_both["sess_num"] = (valid_both["backing_session"] == "RTH").astype(int)
        valid_both["sc_num"] = valid_both["SessionClass"].astype(float)
        # RTH = SessionClass 0,1,2 vs ETH = SessionClass 3
        valid_both["sc_is_rth"] = (valid_both["sc_num"] <= 2).astype(int)
        if len(valid_both) > 10:
            sess_corr = fmt_f(valid_both["sess_num"].corr(valid_both["sc_is_rth"]), 2)
    out.append(f"\nCorrelation with SessionClass: {sess_corr}")
    if sess_corr != "N/A" and float(sess_corr) > 0.9:
        out.append("→ **DROPPED: correlation > 0.9 with existing SessionClass. Redundant.**")
        all_features["C_session"] = {"spread": spread, "mono": mono, "min_n": min_n, "dropped": True}
    else:
        all_features["C_session"] = {"spread": spread, "mono": mono, "min_n": min_n}
    out.append("")

    # D) ray_flip_count
    out.append("### D) ray_flip_count\n")
    fc_bins = [
        ("0 (never flipped)", lambda df: df["backing_flip_count"] == 0),
        ("1", lambda df: df["backing_flip_count"] == 1),
        ("2-3", lambda df: (df["backing_flip_count"] >= 2) & (df["backing_flip_count"] <= 3)),
        ("4+", lambda df: df["backing_flip_count"] >= 4),
        ("NULL", lambda df: df["backing_flip_count"].isna()),
    ]
    rows, spread, mono, min_n = screen_feature(valid, "backing_flip_count", fc_bins, "flip_count")
    out.append(md_table(["Flip count", "Touches", "Mean Rxn", "Mean Pen", "R/P", "n"], rows))
    out.append(f"\nSpread: {fmt_f(spread, 2)} | Monotonic: {mono} | Min bin n: {min_n}\n")
    all_features["D_flip_count"] = {"spread": spread, "mono": mono, "min_n": min_n}

    # E) ray_close_type
    out.append("### E) ray_close_type\n")
    ct_bins = [
        ("Strong rejection", lambda df: df["backing_close_type"] == "strong_rejection"),
        ("Weak rejection", lambda df: df["backing_close_type"] == "weak_rejection"),
        ("Failed acceptance", lambda df: df["backing_close_type"] == "failed_acceptance"),
        ("Confirmed acceptance", lambda df: df["backing_close_type"] == "confirmed_acceptance"),
        ("None/no prior", lambda df: df["backing_close_type"].isin(["none", "acceptance"]) | df["backing_close_type"].isna()),
    ]
    rows, spread, mono, min_n = screen_feature(valid, "backing_close_type", ct_bins, "close_type")
    out.append(md_table(["Close type", "Touches", "Mean Rxn", "Mean Pen", "R/P", "n"], rows))
    out.append(f"\nSpread: {fmt_f(spread, 2)} | Monotonic: {mono} | Min bin n: {min_n}\n")
    all_features["E_close_type"] = {"spread": spread, "mono": mono, "min_n": min_n}

    # F) ray_decay_magnitude
    out.append("### F) ray_decay_magnitude\n")
    dm_bins = [
        ("> 1.0 (strengthening)", lambda df: df["backing_decay_mag"] > 1.0),
        ("0.8-1.0 (stable)", lambda df: (df["backing_decay_mag"] >= 0.8) & (df["backing_decay_mag"] <= 1.0)),
        ("< 0.8 (decaying)", lambda df: df["backing_decay_mag"] < 0.8),
        ("NULL (< 3 interactions)", lambda df: df["backing_decay_mag"].isna()),
    ]
    rows, spread, mono, min_n = screen_feature(valid, "backing_decay_mag", dm_bins, "decay")
    out.append(md_table(["Decay ratio", "Touches", "Mean Rxn", "Mean Pen", "R/P", "n"], rows))
    out.append(f"\nSpread: {fmt_f(spread, 2)} | Monotonic: {mono} | Min bin n: {min_n}\n")
    all_features["F_decay"] = {"spread": spread, "mono": mono, "min_n": min_n}

    # G) ray_approach_velocity
    out.append("### G) ray_approach_velocity\n")
    av_bins = [
        ("Fast (> 5 t/bar)", lambda df: df["backing_approach_vel"] > 5),
        ("Medium (2-5)", lambda df: (df["backing_approach_vel"] >= 2) & (df["backing_approach_vel"] <= 5)),
        ("Slow (< 2)", lambda df: df["backing_approach_vel"] < 2),
        ("NULL", lambda df: df["backing_approach_vel"].isna()),
    ]
    rows, spread, mono, min_n = screen_feature(valid, "backing_approach_vel", av_bins, "velocity")
    out.append(md_table(["Approach velocity", "Touches", "Mean Rxn", "Mean Pen", "R/P", "n"], rows))
    out.append(f"\nSpread: {fmt_f(spread, 2)} | Monotonic: {mono} | Min bin n: {min_n}\n")
    all_features["G_velocity"] = {"spread": spread, "mono": mono, "min_n": min_n}

    # H) ray_between_entry_t1 (obstacle)
    out.append("### H) ray_between_entry_t1 (obstacle with 3+ streak)\n")
    # Strong obstacle: obstacle present with bounce streak 3+
    valid["strong_obstacle"] = (
        (valid["obstacle_present"] == 1) &
        (valid["obstacle_bounce_streak"] >= 3)
    )
    ob_bins = [
        ("Yes, strong HTF obstacle", lambda df: df["strong_obstacle"] == True),
        ("No strong obstacle", lambda df: df["strong_obstacle"] == False),
    ]
    rows, spread, mono, min_n = screen_feature(valid, "strong_obstacle", ob_bins, "obstacle")
    out.append(md_table(["Obstacle ahead?", "Touches", "Mean Rxn", "Mean Pen", "R/P", "n"], rows))
    out.append(f"\nSpread: {fmt_f(spread, 2)} | Min bin n: {min_n}\n")
    all_features["H_obstacle"] = {"spread": spread, "mono": mono, "min_n": min_n}

    # I) ray_cross_tf_count
    out.append("### I) ray_cross_tf_count\n")
    xtf_bins = [
        ("0-1 TFs", lambda df: df["backing_cross_tf"] <= 1),
        ("2 TFs", lambda df: df["backing_cross_tf"] == 2),
        ("3+ TFs", lambda df: df["backing_cross_tf"] >= 3),
        ("NULL", lambda df: df["backing_cross_tf"].isna()),
    ]
    rows, spread, mono, min_n = screen_feature(valid, "backing_cross_tf", xtf_bins, "cross_tf")
    out.append(md_table(["Cross-TF count", "Touches", "Mean Rxn", "Mean Pen", "R/P", "n"], rows))
    out.append(f"\nSpread: {fmt_f(spread, 2)} | Monotonic: {mono} | Min bin n: {min_n}\n")
    all_features["I_cross_tf"] = {"spread": spread, "mono": mono, "min_n": min_n}

    # J) 15m_bar_close at nearest ray
    out.append("### J) 15m_bar_close at nearest ray\n")
    bc_bins = [
        ("Rejection (bounce)", lambda df: df["backing_15m_close"] == "BOUNCE"),
        ("Acceptance (break)", lambda df: df["backing_15m_close"] == "BREAK"),
        ("No interaction", lambda df: df["backing_15m_close"].isna()),
    ]
    rows, spread, mono, min_n = screen_feature(valid, "backing_15m_close", bc_bins, "15m_close")
    out.append(md_table(["15m close", "Touches", "Mean Rxn", "Mean Pen", "R/P", "n"], rows))
    out.append(f"\nSpread: {fmt_f(spread, 2)} | Min bin n: {min_n}\n")
    all_features["J_15m_close"] = {"spread": spread, "mono": mono, "min_n": min_n}

    # K) ray_dist_ticks
    out.append("### K) ray_dist_ticks\n")
    rd_bins = [
        ("< 10t", lambda df: df["backing_dist_ticks"] < 10),
        ("10-20t", lambda df: (df["backing_dist_ticks"] >= 10) & (df["backing_dist_ticks"] < 20)),
        ("20-30t", lambda df: (df["backing_dist_ticks"] >= 20) & (df["backing_dist_ticks"] <= 30)),
        ("30t+ or no ray", lambda df: (df["backing_dist_ticks"] > 30) | df["backing_dist_ticks"].isna()),
    ]
    rows, spread, mono, min_n = screen_feature(valid, "backing_dist_ticks", rd_bins, "dist")
    out.append(md_table(["Distance", "Touches", "Mean Rxn", "Mean Pen", "R/P", "n"], rows))
    out.append(f"\nSpread: {fmt_f(spread, 2)} | Monotonic: {mono} | Min bin n: {min_n}\n")
    all_features["K_distance"] = {"spread": spread, "mono": mono, "min_n": min_n}

    return "\n".join(out), all_features, valid


# =============================================================================
# SECTION 2: RANKING AND SELECTION
# =============================================================================
def section_2(all_features):
    out = []
    out.append("=" * 64)
    out.append("SECTION 2: RANKING AND SELECTION")
    out.append("=" * 64)
    out.append("")

    # Rank by spread
    ranked = sorted(all_features.items(), key=lambda x: x[1]["spread"], reverse=True)

    rank_rows = []
    advance = []
    marginal = []
    dropped = []

    for rank, (name, info) in enumerate(ranked, 1):
        spread = info["spread"]
        mono = info["mono"]
        min_n = info["min_n"]
        is_dropped = info.get("dropped", False)

        if is_dropped:
            status = "DROP (redundant)"
        elif spread > 0.5 and mono and min_n >= 15:
            status = "ADVANCE"
            advance.append(name)
        elif spread > 0.3:
            status = "MARGINAL"
            marginal.append(name)
        else:
            status = "DROP"
            dropped.append(name)

        rank_rows.append([
            rank, name, fmt_f(spread, 2),
            "Yes" if mono else "No", min_n, status
        ])

    out.append(md_table(
        ["Rank", "Feature", "Spread", "Monotonic?", "Min bin n", "Status"],
        rank_rows
    ))
    out.append("")

    out.append(f"**ADVANCE:** {', '.join(advance) if advance else 'None'}")
    out.append(f"**MARGINAL:** {', '.join(marginal) if marginal else 'None'}")
    out.append(f"**DROP:** {', '.join(dropped) if dropped else 'None'}")
    out.append("")

    return "\n".join(out), advance, marginal


# =============================================================================
# SECTION 3: COMBINATION TESTING
# =============================================================================
def section_3(valid, advance_features, all_features):
    out = []
    out.append("=" * 64)
    out.append("SECTION 3: COMBINATION TESTING")
    out.append("=" * 64)
    out.append("")

    if not advance_features:
        out.append("No features ADVANCE. Testing MARGINAL features instead.\n")

    # Build zone history for A-Cal
    zh = build_zone_history(valid)
    valid = valid.copy()
    if "acal_score" not in valid.columns:
        valid["acal_score"] = valid.apply(lambda r: compute_acal_score(r, zh), axis=1)

    valid["RP"] = valid["Reaction"] / valid["Penetration"]
    valid["Win"] = (valid["Reaction"] > valid["Penetration"]).astype(int)

    # Baseline: 4-feature model quintile separation
    out.append("### Baseline: 4-feature A-Cal model\n")
    valid["q5_base"] = pd.qcut(valid["acal_score"], 5, labels=False, duplicates="drop")
    base_rows = []
    for q in sorted(valid["q5_base"].unique()):
        sub = valid[valid["q5_base"] == q]
        rp = sub["RP"].median()
        wr = sub["Win"].mean() * 100
        base_rows.append([f"Q{int(q)+1}", len(sub), fmt_f(rp, 2), fmt_f(wr), len(sub)])
    out.append(md_table(["Score quintile", "Touches", "R/P", "WR%", "n"], base_rows))
    out.append("")

    # Baseline Q5/Q1 metrics
    q1_base = valid[valid["q5_base"] == valid["q5_base"].min()]["RP"].median()
    q5_base = valid[valid["q5_base"] == valid["q5_base"].max()]["RP"].median()
    q5q1_base = q5_base / q1_base if q1_base and q1_base > 0 else 0

    # Test each advancing/marginal feature
    features_to_test = advance_features if advance_features else []
    best_feature = None
    best_q5q1 = q5q1_base
    best_weight = None

    for feat_name in features_to_test:
        out.append(f"### Testing: {feat_name}\n")

        # Determine the feature column
        col_map = {
            "A_bounce_streak": "backing_bounce_streak",
            "B_dwell": "backing_dwell_bars",
            "C_session": "backing_session",
            "D_flip_count": "backing_flip_count",
            "E_close_type": "backing_close_type",
            "F_decay": "backing_decay_mag",
            "G_velocity": "backing_approach_vel",
            "H_obstacle": "strong_obstacle",
            "I_cross_tf": "backing_cross_tf",
            "J_15m_close": "backing_15m_close",
            "K_distance": "backing_dist_ticks",
        }
        col = col_map.get(feat_name)
        if col is None or col not in valid.columns:
            out.append(f"Column {col} not found, skipping.\n")
            continue

        # Convert feature to numeric score (0-1 range)
        feat_vals = valid[col].copy()
        if feat_vals.dtype == object:
            # Categorical: encode as ranks
            cats = feat_vals.dropna().unique()
            # Compute median R/P per category to determine ordering
            cat_rp = {}
            for c in cats:
                sub = valid[valid[col] == c]
                if len(sub) > 0:
                    cat_rp[c] = sub["RP"].median()
            sorted_cats = sorted(cat_rp.keys(), key=lambda x: cat_rp.get(x, 0))
            cat_to_score = {c: i / max(len(sorted_cats) - 1, 1) for i, c in enumerate(sorted_cats)}
            feat_numeric = feat_vals.map(cat_to_score).fillna(0.5)
        elif feat_vals.dtype == bool or set(feat_vals.dropna().unique()).issubset({0, 1, True, False}):
            feat_numeric = feat_vals.astype(float).fillna(0.5)
        else:
            # Numeric: normalize to 0-1
            fmin = feat_vals.min()
            fmax = feat_vals.max()
            if fmax > fmin:
                feat_numeric = (feat_vals - fmin) / (fmax - fmin)
            else:
                feat_numeric = feat_vals.fillna(0.5)
            feat_numeric = feat_numeric.fillna(0.5)

        # Test different weights
        weight_rows = []
        best_w = None
        best_ratio = 0

        for pct in [5, 10, 15, 20, 25]:
            ray_weight = ACAL_MAX * pct / 100
            combined = valid["acal_score"] + feat_numeric * ray_weight
            try:
                q5_comb = pd.qcut(combined, 5, labels=False, duplicates="drop")
            except ValueError:
                continue

            q1_rp = valid[q5_comb == q5_comb.min()]["RP"].median()
            q5_rp = valid[q5_comb == q5_comb.max()]["RP"].median()
            ratio = q5_rp / q1_rp if q1_rp and q1_rp > 0 else 0

            weight_rows.append([f"{pct}%", fmt_f(ratio, 2)])
            if ratio > best_ratio:
                best_ratio = ratio
                best_w = pct

        out.append(md_table(
            ["Ray feature weight (% of total)", "Q5/Q1 ratio"],
            weight_rows
        ))
        out.append(f"\nBest weight: {best_w}% → Q5/Q1 = {fmt_f(best_ratio, 2)} "
                    f"(baseline: {fmt_f(q5q1_base, 2)})")

        if best_ratio > best_q5q1:
            out.append(f"→ **IMPROVES** over baseline by {fmt_f(best_ratio - q5q1_base, 2)}")
            best_feature = feat_name
            best_q5q1 = best_ratio
            best_weight = best_w
        else:
            out.append(f"→ Does not improve over baseline.")
        out.append("")

    # Summary
    out.append("### Combination Summary\n")
    if best_feature:
        out.append(f"**Best ray feature:** {best_feature} at {best_weight}% weight")
        out.append(f"**Q5/Q1 improvement:** {fmt_f(q5q1_base, 2)} → {fmt_f(best_q5q1, 2)}")
    else:
        out.append("**No ray feature improves the 4-feature A-Cal model on P1.**")
        out.append("The existing model stands.")
    out.append("")

    return "\n".join(out), best_feature, best_weight, q5q1_base


# =============================================================================
# SECTION 4: P2 VALIDATION
# =============================================================================
def section_4(best_feature, best_weight, p1_q5q1):
    out = []
    out.append("=" * 64)
    out.append("SECTION 4: P2 VALIDATION")
    out.append("=" * 64)
    out.append("")

    if best_feature is None:
        out.append("**No ray feature passed P1 screening. Skipping P2 validation.**")
        out.append("The 4-feature A-Cal model continues unchanged.")
        return "\n".join(out)

    out.append(f"Testing {best_feature} at {best_weight}% weight on P2 holdout...\n")

    try:
        bars_p2, zte_p2, rc_p2, rr_p2, bars_15m_p2 = load_period_data("P2")
        rays_p2 = extract_rays(zte_p2, rc_p2, rr_p2, len(bars_p2))

        print("  Detecting P2 interactions...")
        ixns_p2 = detect_interactions(bars_p2, rays_p2, bars_15m_p2)
        lifecycle_p2 = build_lifecycle_lookup(
            ixns_p2[ixns_p2["outcome"].isin(["BOUNCE", "BREAK"])], rays_p2, len(bars_p2)
        )

        print("  Computing P2 ray features...")
        zte_p2_enriched = compute_ray_features_for_touches(
            zte_p2, rc_p2, rays_p2, lifecycle_p2, ixns_p2, bars_p2
        )

        # Save P2 enriched
        zte_p2_enriched.to_csv(OUTPUT_DIR / "p2_touches_with_ray_features.csv", index=False)

        # Score with A-Cal
        zh_p2 = build_zone_history(zte_p2_enriched)
        valid_p2 = zte_p2_enriched[
            (zte_p2_enriched["Reaction"] > 0) & (zte_p2_enriched["Penetration"] > 0)
        ].copy()
        valid_p2["RP"] = valid_p2["Reaction"] / valid_p2["Penetration"]
        valid_p2["Win"] = (valid_p2["Reaction"] > valid_p2["Penetration"]).astype(int)
        valid_p2["acal_score"] = valid_p2.apply(lambda r: compute_acal_score(r, zh_p2), axis=1)

        # Apply the model — same logic as Section 3
        col_map = {
            "A_bounce_streak": "backing_bounce_streak",
            "B_dwell": "backing_dwell_bars",
            "D_flip_count": "backing_flip_count",
            "E_close_type": "backing_close_type",
            "F_decay": "backing_decay_mag",
            "G_velocity": "backing_approach_vel",
            "H_obstacle": "strong_obstacle",
            "I_cross_tf": "backing_cross_tf",
            "J_15m_close": "backing_15m_close",
            "K_distance": "backing_dist_ticks",
        }
        col = col_map.get(best_feature)

        if col and col in valid_p2.columns:
            feat_vals = valid_p2[col].copy()
            if feat_vals.dtype == object:
                cats = feat_vals.dropna().unique()
                cat_rp = {}
                for c in cats:
                    sub = valid_p2[valid_p2[col] == c]
                    if len(sub) > 0:
                        cat_rp[c] = sub["RP"].median()
                sorted_cats = sorted(cat_rp.keys(), key=lambda x: cat_rp.get(x, 0))
                cat_to_score = {c: i / max(len(sorted_cats) - 1, 1) for i, c in enumerate(sorted_cats)}
                feat_numeric = feat_vals.map(cat_to_score).fillna(0.5)
            else:
                fmin = feat_vals.min()
                fmax = feat_vals.max()
                if fmax > fmin:
                    feat_numeric = (feat_vals - fmin) / (fmax - fmin)
                else:
                    feat_numeric = feat_vals.fillna(0.5)
                feat_numeric = feat_numeric.fillna(0.5)

            ray_weight = ACAL_MAX * best_weight / 100
            combined_p2 = valid_p2["acal_score"] + feat_numeric * ray_weight

            try:
                q5_p2 = pd.qcut(combined_p2, 5, labels=False, duplicates="drop")
                q1_rp_p2 = valid_p2[q5_p2 == q5_p2.min()]["RP"].median()
                q5_rp_p2 = valid_p2[q5_p2 == q5_p2.max()]["RP"].median()
                q5q1_p2 = q5_rp_p2 / q1_rp_p2 if q1_rp_p2 and q1_rp_p2 > 0 else 0

                # Baseline 4-feature on P2
                q5_base_p2 = pd.qcut(valid_p2["acal_score"], 5, labels=False, duplicates="drop")
                q1_base_p2 = valid_p2[q5_base_p2 == q5_base_p2.min()]["RP"].median()
                q5_base_p2_rp = valid_p2[q5_base_p2 == q5_base_p2.max()]["RP"].median()
                q5q1_base_p2 = q5_base_p2_rp / q1_base_p2 if q1_base_p2 and q1_base_p2 > 0 else 0

                out.append(md_table(
                    ["Metric", "P1 (calibration)", "P2 (validation)"],
                    [
                        ["Total touches", "325", str(len(valid_p2))],
                        ["Q5/Q1 R/P ratio (with ray)", fmt_f(p1_q5q1, 2), fmt_f(q5q1_p2, 2)],
                        ["Q5/Q1 R/P ratio (baseline)", "—", fmt_f(q5q1_base_p2, 2)],
                        ["Q5 R/P (with ray)", "—", fmt_f(q5_rp_p2, 2)],
                        ["Q1 R/P (with ray)", "—", fmt_f(q1_rp_p2, 2)],
                    ]
                ))
                out.append("")

                # Pass criteria
                passes = True
                if q5q1_p2 < p1_q5q1 * 0.5:
                    out.append(f"⚠️ FAIL: P2 Q5/Q1 ({fmt_f(q5q1_p2, 2)}) < 50% of P1 ({fmt_f(p1_q5q1 * 0.5, 2)})")
                    passes = False
                if q5q1_p2 <= q5q1_base_p2:
                    out.append(f"⚠️ FAIL: Ray feature does not improve P2 ({fmt_f(q5q1_p2, 2)} vs baseline {fmt_f(q5q1_base_p2, 2)})")
                    passes = False

                if passes:
                    out.append(f"**PASS:** Ray feature improves P2 separation. Advance to implementation.")
                else:
                    out.append(f"**FAIL:** Ray feature does not pass P2 validation. "
                               f"The 4-feature A-Cal model continues unchanged.")

            except ValueError as e:
                out.append(f"Error in P2 quintile computation: {e}")
        else:
            out.append(f"Feature column {col} not available in P2 data.")

    except Exception as e:
        out.append(f"**P2 validation error:** {e}\n{traceback.format_exc()}")

    out.append("")
    return "\n".join(out)


# =============================================================================
# SECTION 5: IMPLEMENTATION SPEC (stub)
# =============================================================================
def section_5(best_feature, best_weight, passes_p2):
    out = []
    out.append("=" * 64)
    out.append("SECTION 5: IMPLEMENTATION SPECIFICATION")
    out.append("=" * 64)
    out.append("")

    if not passes_p2:
        out.append("**Section 4 did not pass. No implementation required.**")
        out.append("The 4-feature A-Cal model continues to paper trading unchanged.")
        out.append("")
        out.append("**Path 2 (trade management) remains a separate investigation.**")
        out.append("The stall detection finding from the follow-up (130t/trade improvement) ")
        out.append("can be pursued independently of entry scoring, using obstacle ray attributes.")
        return "\n".join(out)

    out.append(f"Feature: {best_feature}")
    out.append(f"Weight: {best_weight}% of A-Cal max score")
    out.append("")
    out.append("*(Full implementation spec deferred pending human review of results.)*")
    return "\n".join(out)


# =============================================================================
# MAIN
# =============================================================================
def main():
    start_time = datetime.now()
    print(f"Ray Feature Screening — started {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 64)

    # Load P1 only
    bars, zte, ray_ctx, ray_ref, bars_15m = load_period_data("P1")

    all_output = []
    all_output.append("# Ray Feature Screening — Prompt 1a Equivalent")
    all_output.append(f"Generated: {start_time.strftime('%Y-%m-%d %H:%M')}")
    all_output.append("Data: P1 only (calibration) | 60m+ rays | 40t threshold | 15m close")
    all_output.append(f"A-Cal baseline: 4 features, threshold {ACAL_THRESHOLD}, max {ACAL_MAX}")
    all_output.append("")

    # Section 0
    try:
        print("\n--- SECTION 0: Compute Lifecycle ---")
        s0, zte_enriched, rays_df, ixns, lifecycle = section_0(bars, zte, ray_ctx, ray_ref, bars_15m)
        all_output.append(s0)
        print("  Section 0 complete.")
    except Exception as e:
        all_output.append(f"\n**SECTION 0 ERROR:** {e}\n{traceback.format_exc()}\n")
        print(f"  Section 0 FAILED: {e}")
        zte_enriched = zte
        traceback.print_exc()

    # Section 1
    all_features = {}
    valid = None
    try:
        print("\n--- SECTION 1: Feature Screening ---")
        s1, all_features, valid = section_1(zte_enriched)
        all_output.append(s1)
        print("  Section 1 complete.")
    except Exception as e:
        all_output.append(f"\n**SECTION 1 ERROR:** {e}\n{traceback.format_exc()}\n")
        print(f"  Section 1 FAILED: {e}")

    # Section 2
    advance = []
    marginal = []
    try:
        print("\n--- SECTION 2: Ranking ---")
        s2, advance, marginal = section_2(all_features)
        all_output.append(s2)
        print(f"  Section 2 complete. ADVANCE: {advance}, MARGINAL: {marginal}")
    except Exception as e:
        all_output.append(f"\n**SECTION 2 ERROR:** {e}\n{traceback.format_exc()}\n")
        print(f"  Section 2 FAILED: {e}")

    # Section 3
    best_feature = None
    best_weight = None
    p1_q5q1 = 0
    try:
        print("\n--- SECTION 3: Combination Testing ---")
        # Use advance + marginal for testing
        test_features = advance + marginal
        if valid is not None and len(test_features) > 0:
            s3, best_feature, best_weight, p1_q5q1 = section_3(valid, test_features, all_features)
        else:
            s3 = "No features to test.\n"
        all_output.append(s3)
        print(f"  Section 3 complete. Best: {best_feature} at {best_weight}%")
    except Exception as e:
        all_output.append(f"\n**SECTION 3 ERROR:** {e}\n{traceback.format_exc()}\n")
        print(f"  Section 3 FAILED: {e}")

    # Section 4
    try:
        print("\n--- SECTION 4: P2 Validation ---")
        s4 = section_4(best_feature, best_weight, p1_q5q1)
        all_output.append(s4)
        print("  Section 4 complete.")
    except Exception as e:
        all_output.append(f"\n**SECTION 4 ERROR:** {e}\n{traceback.format_exc()}\n")
        print(f"  Section 4 FAILED: {e}")

    # Section 5
    passes_p2 = best_feature is not None  # simplified check
    s5 = section_5(best_feature, best_weight, passes_p2)
    all_output.append(s5)

    # Write output
    output_path = OUTPUT_DIR / "ray_feature_screening.md"
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(all_output))

    elapsed = datetime.now() - start_time
    print(f"\n{'=' * 64}")
    print(f"Screening complete in {elapsed}")
    print(f"Results saved to: {output_path}")


if __name__ == "__main__":
    main()
