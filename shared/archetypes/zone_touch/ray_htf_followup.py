#!/usr/bin/env python3
# archetype: zone_touch
"""
Ray HTF Follow-up — Deconfounding and regime checks.
Resolves open questions from ray_baseline_analysis.md before feature screening.
Uses same P1+P2 combined data. Same definitions: 40t proximity, 15m bar close.
"""

import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime, time
import warnings
import traceback

warnings.filterwarnings("ignore")

# =============================================================================
# CONSTANTS (same as baseline)
# =============================================================================
TICK_SIZE = 0.25
PIPELINE_ROOT = Path(__file__).resolve().parent.parent.parent.parent
DATA_DIR = PIPELINE_ROOT / "stages" / "01-data" / "data"
TOUCH_DIR = DATA_DIR / "touches"
BAR_VOL_DIR = DATA_DIR / "bar_data" / "volume"
BAR_TIME_DIR = DATA_DIR / "bar_data" / "time"
OUTPUT_DIR = Path(__file__).resolve().parent / "output"

PROX_THRESHOLD = 40  # baseline close-based optimal
PROX_20T = 20        # for Check 8
MAX_OBS_BARS = 500
RTH_START = time(9, 30)
RTH_END = time(16, 15)

TF_BUCKET_MAP = {
    "15m": "15m", "30m": "30m", "60m": "60m", "90m": "90m",
    "120m": "120m", "240m": "240m+", "360m": "240m+", "480m": "240m+", "720m": "240m+"
}

HTF_TFS = {"60m", "90m", "120m", "240m", "360m", "480m", "720m"}


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


def fmt_pct(val, total):
    if total == 0:
        return "N/A"
    return f"{val / total * 100:.1f}%"


def fmt_f(val, decimals=1):
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return "N/A"
    return f"{val:.{decimals}f}"


# =============================================================================
# DATA LOADING (reused from baseline)
# =============================================================================
def load_bar_data(path):
    df = pd.read_csv(path)
    df.columns = df.columns.str.strip()
    cols_keep = ["Date", "Time", "Open", "High", "Low", "Last", "Volume"]
    df = df[cols_keep].copy()
    df.rename(columns={"Last": "Close"}, inplace=True)
    df["DateTime"] = pd.to_datetime(
        df["Date"].str.strip() + " " + df["Time"].str.strip(), format="mixed"
    )
    df.drop(columns=["Date", "Time"], inplace=True)
    return df


def load_all_data():
    print("Loading 250-vol bar data...")
    bars_p1 = load_bar_data(BAR_VOL_DIR / "NQ_BarData_250vol_rot_P1.csv")
    bars_p2 = load_bar_data(BAR_VOL_DIR / "NQ_BarData_250vol_rot_P2.csv")
    p1_count = len(bars_p1)
    print(f"  P1: {p1_count} bars, P2: {len(bars_p2)} bars")

    bars = pd.concat([bars_p1, bars_p2], ignore_index=True)
    bars["BarIdx"] = bars.index

    print("Loading ray reference data...")
    ray_ref_p1 = pd.read_csv(TOUCH_DIR / "NQ_ray_reference_P1.csv")
    ray_ref_p2 = pd.read_csv(TOUCH_DIR / "NQ_ray_reference_P2.csv")
    ray_ref_p2 = ray_ref_p2.copy()
    ray_ref_p2["BaseBarIndex"] = ray_ref_p2["BaseBarIndex"] + p1_count
    ray_ref = pd.concat([ray_ref_p1, ray_ref_p2], ignore_index=True)

    print("Loading ZTE raw data...")
    zte_p1 = pd.read_csv(TOUCH_DIR / "NQ_ZTE_raw_P1.csv")
    zte_p2 = pd.read_csv(TOUCH_DIR / "NQ_ZTE_raw_P2.csv")
    # Build TouchID from ORIGINAL BarIndex (matches ray_context)
    zte_p1["TouchID"] = (
        zte_p1["BarIndex"].astype(str) + "_" + zte_p1["TouchType"] + "_" + zte_p1["SourceLabel"]
    )
    zte_p2["TouchID"] = (
        zte_p2["BarIndex"].astype(str) + "_" + zte_p2["TouchType"] + "_" + zte_p2["SourceLabel"]
    )
    # Store original BarIndex for period splitting
    zte_p1["OrigBarIndex"] = zte_p1["BarIndex"]
    zte_p2["OrigBarIndex"] = zte_p2["BarIndex"]
    zte_p1["Period"] = "P1"
    zte_p2["Period"] = "P2"
    # Offset P2 for continuous timeline
    zte_p2 = zte_p2.copy()
    zte_p2["BarIndex"] = zte_p2["BarIndex"] + p1_count
    zte = pd.concat([zte_p1, zte_p2], ignore_index=True)
    zte = zte[zte["TouchType"] != "VP_RAY"].copy()
    print(f"  {len(zte)} zone touch events (excl VP_RAY)")

    print("Loading ray context data...")
    rc_p1 = pd.read_csv(TOUCH_DIR / "NQ_ray_context_P1.csv")
    rc_p2 = pd.read_csv(TOUCH_DIR / "NQ_ray_context_P2.csv")
    ray_ctx = pd.concat([rc_p1, rc_p2], ignore_index=True)
    print(f"  {len(ray_ctx)} ray-touch pairs")

    return bars, ray_ref, zte, ray_ctx, p1_count


def build_rays(ray_ref):
    events = []
    for _, row in ray_ref.iterrows():
        if row["DemandRayPrice"] > 0:
            events.append({
                "price": row["DemandRayPrice"], "side": "DEMAND",
                "creation_bar": row["BaseBarIndex"], "tf": row["SourceLabel"],
            })
        if row["SupplyRayPrice"] > 0:
            events.append({
                "price": row["SupplyRayPrice"], "side": "SUPPLY",
                "creation_bar": row["BaseBarIndex"], "tf": row["SourceLabel"],
            })
    events_df = pd.DataFrame(events)
    if events_df.empty:
        return events_df, events_df
    events_df = events_df.sort_values("creation_bar")
    rays = events_df.groupby(["price", "side"]).agg(
        creation_bar=("creation_bar", "min"),
        tf=("tf", "first"),
        event_count=("creation_bar", "count"),
    ).reset_index()
    rays["tf_min"] = rays["tf"].apply(tf_minutes)
    rays["tf_bucket"] = rays["tf"].map(TF_BUCKET_MAP).fillna("240m+")
    rays["is_htf"] = rays["tf_min"] >= 60
    rays = rays.sort_values("creation_bar").reset_index(drop=True)
    return rays, events_df


def load_15m_bars():
    print("Loading 10-second bar data for 15m construction...")
    b1 = load_bar_data(BAR_TIME_DIR / "NQ_BarData_10sec_rot_P1.csv")
    b2 = load_bar_data(BAR_TIME_DIR / "NQ_BarData_10sec_rot_P2.csv")
    bars_10s = pd.concat([b1, b2], ignore_index=True)
    bars_10s = bars_10s.set_index("DateTime").sort_index()
    bars_15m = bars_10s.resample("15min").agg({
        "Open": "first", "High": "max", "Low": "min",
        "Close": "last", "Volume": "sum"
    }).dropna().reset_index()
    del bars_10s
    print(f"  {len(bars_15m)} 15-minute bars constructed")
    return bars_15m


# =============================================================================
# INTERACTION DETECTION (reused from baseline, simplified)
# =============================================================================
def detect_interactions(bars_high, bars_low, bars_close, rays, threshold_ticks,
                        bars_dt=None, max_obs=MAX_OBS_BARS):
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

        start = creation_bar
        hi = bars_high[start:]
        lo = bars_low[start:]
        near = (lo <= ray_price + thresh_price) & (hi >= ray_price - thresh_price)
        near_int = near.astype(np.int8)
        transitions = np.diff(near_int, prepend=0)
        enter_indices = np.where(transitions == 1)[0]
        exit_indices = np.where(transitions == -1)[0]

        for ei_idx, enter_rel in enumerate(enter_indices):
            enter_abs = start + int(enter_rel)
            exits_after = exit_indices[exit_indices > enter_rel]
            if len(exits_after) > 0:
                exit_abs = start + int(exits_after[0])
            else:
                exit_abs = n_bars - 1

            dwell = exit_abs - enter_abs + 1

            if enter_abs > 0:
                prior_close = bars_close[enter_abs - 1]
                approach_from = "ABOVE" if prior_close > ray_price else "BELOW"
            else:
                approach_from = "BELOW"

            # 15m close-based outcome (governing method from baseline)
            # Use the bar close as proxy if 15m not available inline
            first_close = bars_close[enter_abs] if enter_abs < n_bars else ray_price
            if approach_from == "ABOVE":
                outcome = "BOUNCE" if first_close > ray_price else "BREAK"
            else:
                outcome = "BOUNCE" if first_close < ray_price else "BREAK"

            # Approach velocity
            vel_lookback = 5
            if enter_abs >= vel_lookback:
                approach_vel = abs(
                    bars_close[enter_abs] - bars_close[enter_abs - vel_lookback]
                ) / TICK_SIZE / vel_lookback
            else:
                approach_vel = 0

            # Session
            session = "UNKNOWN"
            if bars_dt is not None and enter_abs < len(bars_dt):
                dt = pd.Timestamp(bars_dt[enter_abs])
                t = dt.time()
                session = "RTH" if RTH_START <= t <= RTH_END else "ETH"

            interactions.append({
                "ray_idx": ray_idx, "ray_price": ray_price,
                "ray_side": ray_side, "ray_tf": ray_tf,
                "enter_bar": enter_abs, "exit_bar": exit_abs,
                "dwell": dwell, "approach_from": approach_from,
                "outcome": outcome, "approach_vel": approach_vel,
                "session": session, "first_close": first_close,
            })

    return pd.DataFrame(interactions)


def add_15m_outcome(ixns_df, bars_250v, bars_15m):
    """Override outcome with 15m bar close classification."""
    if bars_15m is None or ixns_df.empty:
        return ixns_df
    bar_dts = bars_250v["DateTime"].values
    m15_dts = bars_15m["DateTime"].values
    m15_closes = bars_15m["Close"].values

    outcomes = []
    for _, ix in ixns_df.iterrows():
        eb = int(ix["enter_bar"])
        if eb < len(bar_dts):
            bar_dt = bar_dts[eb]
            idx = np.searchsorted(m15_dts, bar_dt, side="right") - 1
            if 0 <= idx < len(m15_closes):
                m15c = m15_closes[idx]
                rp = ix["ray_price"]
                af = ix["approach_from"]
                if af == "ABOVE":
                    outcomes.append("BOUNCE" if m15c > rp else "BREAK")
                else:
                    outcomes.append("BOUNCE" if m15c < rp else "BREAK")
            else:
                outcomes.append(ix["outcome"])
        else:
            outcomes.append(ix["outcome"])

    ixns_df = ixns_df.copy()
    ixns_df["outcome"] = outcomes
    return ixns_df


# =============================================================================
# HELPER: compute R/P for ZTE subsets
# =============================================================================
def rp_stats(zte_sub):
    """Return (n, rp_median, wr%) for a ZTE subset."""
    v = zte_sub[(zte_sub["Reaction"] > 0) & (zte_sub["Penetration"] > 0)].copy()
    if len(v) == 0:
        return 0, None, None
    v["RP"] = v["Reaction"] / v["Penetration"]
    v["Win"] = (v["Reaction"] > v["Penetration"]).astype(int)
    return len(v), v["RP"].median(), v["Win"].mean() * 100


# =============================================================================
# CHECK 1: RAY DENSITY WITH HTF FILTER
# =============================================================================
def check_1(zte, ray_ctx, rays_df):
    out = []
    out.append("=" * 64)
    out.append("CHECK 1: RAY DENSITY WITH HTF FILTER")
    out.append("=" * 64)
    out.append("")

    # Filter ray_ctx to HTF only
    rc_htf = ray_ctx[ray_ctx["RayTF"].apply(is_htf)].copy()
    htf_rays = rays_df[rays_df["is_htf"]].copy()

    # 30t proximity filter
    rc_htf_30t = rc_htf[rc_htf["RayDistTicks"] <= 30]

    # Density per touch
    all_touch_ids = set(zte["TouchID"].unique())
    htf_per_touch = rc_htf_30t.groupby("TouchID").size()
    touches_with_htf = set(htf_per_touch.index) & all_touch_ids
    touches_no_htf = all_touch_ids - touches_with_htf

    # All-ray baseline for comparison
    rc_all_30t = ray_ctx[ray_ctx["RayDistTicks"] <= 30]
    all_per_touch = rc_all_30t.groupby("TouchID").size()

    out.append(md_table(
        ["Metric", "All rays (baseline)", "60m+ only"],
        [
            ["Active rays at end of period", len(rays_df), len(htf_rays)],
            ["Mean rays per touch (within 30t)",
             fmt_f(all_per_touch.reindex(pd.Index(all_touch_ids), fill_value=0).mean()),
             fmt_f(htf_per_touch.reindex(pd.Index(all_touch_ids), fill_value=0).mean())],
            ["Touches with 0 nearby rays",
             f"{len(all_touch_ids - set(all_per_touch.index) & all_touch_ids)}",
             f"{len(touches_no_htf)} ({fmt_pct(len(touches_no_htf), len(all_touch_ids))})"],
        ]
    ))
    out.append("")

    # Distribution of HTF rays within 30t
    htf_counts = htf_per_touch.reindex(pd.Index(all_touch_ids), fill_value=0)
    dist_rows = []
    for lo, hi, label in [(0, 0, "0"), (1, 2, "1-2"), (3, 5, "3-5"), (6, 9999, "6+")]:
        n = ((htf_counts >= lo) & (htf_counts <= hi)).sum()
        dist_rows.append([label, n, fmt_pct(n, len(all_touch_ids))])
    out.append(md_table(["HTF rays within 30t", "Touches", "%"], dist_rows))
    out.append("")

    # Decision gate
    pct_no_htf = len(touches_no_htf) / len(all_touch_ids) * 100
    use_continuous = pct_no_htf < 5
    if use_continuous:
        out.append(f"**DECISION GATE:** 0-HTF-ray group = {pct_no_htf:.1f}% < 5%. "
                   f"Density problem persists at HTF. Using CONTINUOUS features "
                   f"(nearest HTF ray distance, bounce streak) instead of binary presence/absence.")
    else:
        out.append(f"**DECISION GATE:** 0-HTF-ray group = {pct_no_htf:.1f}% >= 5%. "
                   f"Binary presence/absence comparisons are viable.")
    out.append("")

    # Per-TF selection: nearest + newest per TF, within zone_width + 30t
    out.append("**Per-TF selection (nearest ray per TF, within ZW + 30t):**\n")
    zte_valid = zte[(zte["Reaction"] > 0) & (zte["Penetration"] > 0)].copy()
    zte_valid["RP"] = zte_valid["Reaction"] / zte_valid["Penetration"]

    # For each touch, count distinct TFs with a ray within ZW+30t
    rc_htf_merged = rc_htf.merge(
        zte[["TouchID", "ZoneWidthTicks"]], on="TouchID", how="left"
    )
    rc_htf_merged = rc_htf_merged.dropna(subset=["ZoneWidthTicks"])
    rc_htf_merged["in_zone_buffer"] = (
        rc_htf_merged["RayDistTicks"] <= rc_htf_merged["ZoneWidthTicks"] + 30
    )
    rc_near = rc_htf_merged[rc_htf_merged["in_zone_buffer"]]

    # Cross-TF confluence: how many distinct TFs have rays within 20t of each other
    # Simplified: count distinct TFs with ray near zone
    tf_counts_per_touch = rc_near.groupby("TouchID")["RayTF"].nunique()
    tf_counts_all = tf_counts_per_touch.reindex(pd.Index(zte_valid["TouchID"]), fill_value=0)
    zte_valid["n_htf_tfs"] = tf_counts_all.values

    confluence_rows = []
    for lo, hi, label in [(0, 0, "0 TFs with ray near zone"),
                          (1, 1, "1 TF with ray near zone"),
                          (2, 2, "2 TFs converging"),
                          (3, 99, "3+ TFs converging")]:
        sub = zte_valid[(zte_valid["n_htf_tfs"] >= lo) & (zte_valid["n_htf_tfs"] <= hi)]
        n, rp, wr = rp_stats(sub)
        confluence_rows.append([label, len(sub), fmt_f(rp, 2) if rp else "N/A", n])

    out.append(md_table(
        ["Cross-TF confluence at zone", "Touches", "R/P", "n"],
        confluence_rows
    ))
    out.append("")

    return "\n".join(out), use_continuous, rc_htf, htf_rays


# =============================================================================
# CHECK 2: FRESH RAY + FRESH ZONE COMBINATION
# =============================================================================
def check_2(zte, ray_ctx, use_continuous):
    out = []
    out.append("=" * 64)
    out.append("CHECK 2: FRESH RAY + FRESH ZONE COMBINATION")
    out.append("=" * 64)
    out.append("")

    rc_htf = ray_ctx[ray_ctx["RayTF"].apply(is_htf)].copy()
    rc_htf_30t = rc_htf[rc_htf["RayDistTicks"] <= 30]

    zte_valid = zte[(zte["Reaction"] > 0) & (zte["Penetration"] > 0)].copy()
    zte_valid["RP"] = zte_valid["Reaction"] / zte_valid["Penetration"]

    # For each touch, get nearest HTF ray info
    nearest_htf = rc_htf_30t.sort_values("RayDistTicks").groupby("TouchID").first().reset_index()
    zte_m = zte_valid.merge(
        nearest_htf[["TouchID", "RayAgeBars", "RayDistTicks", "RayTF"]],
        on="TouchID", how="left", suffixes=("", "_ray")
    )

    # Freshness cutpoints
    FRESH_CUT = 100
    STALE_CUT = 500

    # Check sample sizes and widen if needed
    fresh_ray_n = (zte_m["RayAgeBars"] < FRESH_CUT).sum()
    if fresh_ray_n < 30:
        FRESH_CUT = 200
        out.append(f"⚠️ Fresh cutpoint widened to {FRESH_CUT} bars (original 100 had n={fresh_ray_n})\n")

    zte_m["zone_fresh"] = zte_m["ZoneAgeBars"] < FRESH_CUT
    zte_m["zone_stale"] = zte_m["ZoneAgeBars"] > STALE_CUT
    zte_m["ray_fresh"] = zte_m["RayAgeBars"] < FRESH_CUT
    zte_m["ray_stale"] = zte_m["RayAgeBars"] > STALE_CUT
    zte_m["ray_absent"] = zte_m["RayAgeBars"].isna()

    combos = [
        ("Fresh zone + fresh HTF ray", zte_m["zone_fresh"] & zte_m["ray_fresh"]),
        ("Fresh zone + stale HTF ray", zte_m["zone_fresh"] & zte_m["ray_stale"]),
        ("Fresh zone + no HTF ray nearby", zte_m["zone_fresh"] & zte_m["ray_absent"]),
        ("Stale zone + fresh HTF ray", zte_m["zone_stale"] & zte_m["ray_fresh"]),
        ("Stale zone + stale HTF ray", zte_m["zone_stale"] & zte_m["ray_stale"]),
        ("Stale zone + no HTF ray nearby", zte_m["zone_stale"] & zte_m["ray_absent"]),
    ]

    combo_rows = []
    for label, mask in combos:
        sub = zte_m[mask]
        n, rp, wr = rp_stats(sub)
        combo_rows.append([label, len(sub), fmt_f(rp, 2) if rp else "N/A",
                           fmt_f(wr) if wr else "N/A", n])

    out.append(md_table(
        ["Combination", "Touches", "R/P", "WR", "n"],
        combo_rows
    ))
    out.append("")

    # Bounce streak of fresh vs stale rays (use ray_context RayAgeBars as proxy)
    out.append("**Ray freshness vs bounce streak proxy:**\n")
    # RayAgeBars in ray_context is age at touch time — low age = few prior interactions
    fresh_rays = rc_htf_30t[rc_htf_30t["RayAgeBars"] < FRESH_CUT]
    stale_rays = rc_htf_30t[rc_htf_30t["RayAgeBars"] > STALE_CUT]

    out.append(md_table(
        ["Ray freshness", "Mean age (bars)", "Median age", "n (ray-touch pairs)"],
        [
            [f"Fresh HTF ray (< {FRESH_CUT} bars)",
             fmt_f(fresh_rays["RayAgeBars"].mean()),
             fmt_f(fresh_rays["RayAgeBars"].median()),
             len(fresh_rays)],
            [f"Stale HTF ray (> {STALE_CUT} bars)",
             fmt_f(stale_rays["RayAgeBars"].mean()),
             fmt_f(stale_rays["RayAgeBars"].median()),
             len(stale_rays)],
        ]
    ))
    out.append("")
    out.append(f"(Fresh cutpoint used: {FRESH_CUT} bars)")
    out.append("")

    return "\n".join(out)


# =============================================================================
# CHECK 3: HTF RAY EFFECT ON ZONE TOUCH R/P (CLEANED)
# =============================================================================
def check_3(zte, ray_ctx):
    out = []
    out.append("=" * 64)
    out.append("CHECK 3: HTF RAY EFFECT ON ZONE TOUCH R/P (CLEANED)")
    out.append("=" * 64)
    out.append("")

    rc_htf = ray_ctx[ray_ctx["RayTF"].apply(is_htf)].copy()
    rc_htf_30t = rc_htf[rc_htf["RayDistTicks"] <= 30]

    zte_valid = zte[(zte["Reaction"] > 0) & (zte["Penetration"] > 0)].copy()
    zte_valid["RP"] = zte_valid["Reaction"] / zte_valid["Penetration"]

    # Nearest HTF ray info per touch
    nearest_htf = rc_htf_30t.sort_values("RayDistTicks").groupby("TouchID").first().reset_index()
    zte_m = zte_valid.merge(
        nearest_htf[["TouchID", "RayAgeBars", "RayDistTicks", "RayDirection"]],
        on="TouchID", how="left"
    )
    zte_m["has_htf"] = ~zte_m["RayAgeBars"].isna()

    # Classify ray position relative to zone (using RayDirection from ray_context)
    # RayDirection: ABOVE or BELOW relative to touch zone edge
    # For DEMAND_EDGE: entry at ZoneTop, target above → ABOVE ray = between entry and target
    # For SUPPLY_EDGE: entry at ZoneBot, target below → BELOW ray = between entry and target

    # Also check if ray is INSIDE zone using RayDistTicks and zone width
    rc_htf_merged = rc_htf.merge(
        zte[["TouchID", "ZoneTop", "ZoneBot", "ZoneWidthTicks", "TouchType"]],
        on="TouchID", how="left"
    ).dropna(subset=["ZoneTop"])

    # Ray inside zone: RayPrice between ZoneBot and ZoneTop
    # We don't have RayPrice directly in ray_ctx, but we can infer:
    # RayDistTicks is distance from zone edge. If RayDirection=ABOVE and dist < ZW, ray is inside
    rc_htf_merged["inside_zone"] = rc_htf_merged["RayDistTicks"] <= rc_htf_merged["ZoneWidthTicks"]

    # Per-touch classification
    touch_class = {}
    for tid, grp in rc_htf_merged.groupby("TouchID"):
        inside = grp[grp["inside_zone"]]
        fresh_inside = inside[inside["RayAgeBars"] < 200]
        # Check for ray between entry and T1
        tt = grp["TouchType"].iloc[0]
        zw = grp["ZoneWidthTicks"].iloc[0] * TICK_SIZE
        if tt == "DEMAND_EDGE":
            # T1 is 0.5*ZW above entry (ZoneTop)
            between_t1 = grp[(grp["RayDirection"] == "ABOVE") &
                             (grp["RayDistTicks"] <= 0.5 * grp["ZoneWidthTicks"])]
        else:
            between_t1 = grp[(grp["RayDirection"] == "BELOW") &
                             (grp["RayDistTicks"] <= 0.5 * grp["ZoneWidthTicks"])]

        touch_class[tid] = {
            "has_htf": True,
            "inside": len(inside) > 0,
            "fresh_inside": len(fresh_inside) > 0,
            "between_t1": len(between_t1) > 0,
        }

    tc_df = pd.DataFrame.from_dict(touch_class, orient="index")
    zte_c = zte_valid.merge(tc_df, left_on="TouchID", right_index=True, how="left")
    zte_c = zte_c.fillna(False)
    zte_c["no_htf"] = ~zte_c["has_htf"].astype(bool)

    context_rows = []
    for label, mask in [
        ("No HTF ray within 30t", zte_c["no_htf"]),
        ("HTF ray inside zone", zte_c["inside"].astype(bool)),
        ("Fresh HTF ray inside zone", zte_c["fresh_inside"].astype(bool)),
        ("HTF ray between entry and T1", zte_c["between_t1"].astype(bool)),
    ]:
        sub = zte_c[mask]
        n, rp, wr = rp_stats(sub)
        context_rows.append([label, len(sub), fmt_f(rp, 2) if rp else "N/A", n])

    out.append(md_table(
        ["Ray context (60m+ only)", "Touches", "R/P", "n"],
        context_rows
    ))
    out.append("")

    # Baseline comparison
    no_htf_rp = rp_stats(zte_c[zte_c["no_htf"]])
    out.append(f"**Baseline comparison:** No-ray R/P was 5.09 (n=79). "
               f"No-HTF-ray R/P = {fmt_f(no_htf_rp[1], 2)} (n={no_htf_rp[0]})")
    out.append("")

    # Split by zone width
    out.append("**Split by zone width:**\n")
    zw_bins = [(0, 150, "< 150t (narrow)"), (150, 250, "150-250t"), (250, 9999, "250t+ (wide)")]
    zw_rows = []
    for lo, hi, label in zw_bins:
        sub_no = zte_c[(zte_c["no_htf"]) &
                       (zte_c["ZoneWidthTicks"] >= lo) & (zte_c["ZoneWidthTicks"] < hi)]
        sub_yes = zte_c[(~zte_c["no_htf"]) &
                        (zte_c["ZoneWidthTicks"] >= lo) & (zte_c["ZoneWidthTicks"] < hi)]
        _, rp_no, _ = rp_stats(sub_no)
        _, rp_yes, _ = rp_stats(sub_yes)
        zw_rows.append([label,
                        fmt_f(rp_no, 2) if rp_no else "N/A",
                        fmt_f(rp_yes, 2) if rp_yes else "N/A",
                        len(sub_no), len(sub_yes)])

    out.append(md_table(
        ["Zone width", "No HTF ray R/P", "With HTF ray R/P", "n (no)", "n (with)"],
        zw_rows
    ))
    out.append("")

    return "\n".join(out)


# =============================================================================
# CHECK 4: BOUNCE STREAK DECONFOUNDED FROM AGE
# =============================================================================
def check_4(ixns, rays_df):
    out = []
    out.append("=" * 64)
    out.append("CHECK 4: BOUNCE STREAK DECONFOUNDED FROM AGE")
    out.append("=" * 64)
    out.append("")

    # Filter to HTF rays
    htf_ray_indices = set(rays_df[rays_df["is_htf"]].index)
    ixns_htf = ixns[ixns["ray_idx"].isin(htf_ray_indices)].copy()
    ixns_htf = ixns_htf[ixns_htf["outcome"].isin(["BOUNCE", "BREAK"])].copy()

    # Compute bounce streak and age at each interaction
    ixns_htf = ixns_htf.sort_values("enter_bar")

    # Merge ray creation bar
    ixns_htf = ixns_htf.merge(
        rays_df[["creation_bar"]], left_on="ray_idx", right_index=True, how="left"
    )
    ixns_htf["age"] = ixns_htf["enter_bar"] - ixns_htf["creation_bar"]

    # Compute bounce streak per ray
    streak_data = []
    for ray_idx in ixns_htf["ray_idx"].unique():
        ray_ixns = ixns_htf[ixns_htf["ray_idx"] == ray_idx].sort_values("enter_bar")
        consec = 0
        for _, ix in ray_ixns.iterrows():
            streak_data.append({
                "ray_idx": ray_idx,
                "enter_bar": ix["enter_bar"],
                "outcome": ix["outcome"],
                "bounce_streak": consec,
                "age": ix["age"],
            })
            if ix["outcome"] == "BOUNCE":
                consec += 1
            else:
                consec = 0

    sd = pd.DataFrame(streak_data)
    if len(sd) == 0:
        out.append("No HTF interactions found.\n")
        return "\n".join(out)

    sd["fresh"] = sd["age"] < 100
    sd["stale"] = sd["age"] > 500
    sd["has_streak"] = sd["bounce_streak"] >= 1

    # 2x2 table
    combos = [
        ("Fresh (< 100 bars)", "0 bounces", sd["fresh"] & ~sd["has_streak"]),
        ("Fresh (< 100 bars)", "1+ bounces", sd["fresh"] & sd["has_streak"]),
        ("Stale (> 500 bars)", "0 bounces", sd["stale"] & ~sd["has_streak"]),
        ("Stale (> 500 bars)", "1+ bounces", sd["stale"] & sd["has_streak"]),
    ]

    combo_rows = []
    for age_label, streak_label, mask in combos:
        sub = sd[mask]
        n = len(sub)
        nb = (sub["outcome"] == "BOUNCE").sum()
        combo_rows.append([age_label, streak_label, fmt_pct(nb, n), n])

    out.append(md_table(["Age", "Bounce streak", "Bounce %", "n"], combo_rows))
    out.append("")

    # Interpretation
    fresh_0 = sd[sd["fresh"] & ~sd["has_streak"]]
    fresh_1 = sd[sd["fresh"] & sd["has_streak"]]
    stale_0 = sd[sd["stale"] & ~sd["has_streak"]]
    stale_1 = sd[sd["stale"] & sd["has_streak"]]

    f0_pct = (fresh_0["outcome"] == "BOUNCE").mean() * 100 if len(fresh_0) > 0 else None
    f1_pct = (fresh_1["outcome"] == "BOUNCE").mean() * 100 if len(fresh_1) > 0 else None
    s0_pct = (stale_0["outcome"] == "BOUNCE").mean() * 100 if len(stale_0) > 0 else None
    s1_pct = (stale_1["outcome"] == "BOUNCE").mean() * 100 if len(stale_1) > 0 else None

    out.append("**Interpretation:**")
    if f1_pct and s1_pct and abs(f1_pct - s1_pct) < 5:
        out.append("- Fresh+1bounce ≈ Stale+1bounce → Age fully explained by streak. "
                    "**Drop age, keep streak only.**")
    elif f1_pct and s1_pct and f1_pct > s1_pct + 5:
        out.append("- Fresh+1bounce > Stale+1bounce → Freshness adds signal beyond streak. "
                    "**Both are features.**")
    elif f0_pct and s0_pct and f0_pct > s0_pct + 5:
        out.append("- Fresh+0bounce > Stale+0bounce → Fresh rays hold better even without "
                    "confirmation. **Freshness is independent.**")
    else:
        out.append("- No clear pattern. Review cell sizes.")
    out.append("")

    return "\n".join(out)


# =============================================================================
# CHECK 5: LIFECYCLE AT HTF ONLY
# =============================================================================
def check_5(ixns, rays_df):
    out = []
    out.append("=" * 64)
    out.append("CHECK 5: LIFECYCLE AT HTF ONLY")
    out.append("=" * 64)
    out.append("")

    htf_ray_indices = set(rays_df[rays_df["is_htf"]].index)
    ixns_htf = ixns[ixns["ray_idx"].isin(htf_ray_indices)].copy()
    ixns_htf = ixns_htf[ixns_htf["outcome"].isin(["BOUNCE", "BREAK"])].copy()
    ixns_htf = ixns_htf.sort_values("enter_bar")

    # Bounce streak
    streak_data = []
    flip_counts = {}
    for ray_idx in ixns_htf["ray_idx"].unique():
        ray_ixns = ixns_htf[ixns_htf["ray_idx"] == ray_idx].sort_values("enter_bar")
        consec = 0
        flips = 0
        for _, ix in ray_ixns.iterrows():
            streak_data.append({
                "bounce_streak": min(consec, 3),
                "outcome": ix["outcome"],
            })
            if ix["outcome"] == "BOUNCE":
                consec += 1
            else:
                consec = 0
                flips += 1
        flip_counts[ray_idx] = flips

    sd = pd.DataFrame(streak_data)

    out.append("**Bounce streak (60m+ only):**\n")
    streak_rows = []
    for ns, label in [(0, "0 (just flipped)"), (1, "1 confirmed"),
                      (2, "2 confirmed"), (3, "3+ confirmed")]:
        sub = sd[sd["bounce_streak"] == ns]
        n = len(sub)
        nb = (sub["outcome"] == "BOUNCE").sum()
        streak_rows.append([label, fmt_pct(nb, n), n])
    out.append(md_table(["Bounce streak (60m+ only)", "Next bounce %", "n"], streak_rows))
    out.append("")

    # Compare to baseline
    s0 = sd[sd["bounce_streak"] == 0]
    s1 = sd[sd["bounce_streak"] == 1]
    s3 = sd[sd["bounce_streak"] == 3]
    b0 = (s0["outcome"] == "BOUNCE").mean() * 100 if len(s0) > 0 else 0
    b1 = (s1["outcome"] == "BOUNCE").mean() * 100 if len(s1) > 0 else 0
    b3 = (s3["outcome"] == "BOUNCE").mean() * 100 if len(s3) > 0 else 0
    jump_01 = b1 - b0

    out.append(md_table(
        ["Metric", "Baseline (all TFs)", "60m+ only"],
        [
            ["0→1 jump magnitude", "29.0pp", f"{jump_01:.1f}pp"],
            ["3+ bounce rate", "79.2%", f"{b3:.1f}%"],
            ["0 bounce rate", "48.5%", f"{b0:.1f}%"],
        ]
    ))
    out.append("")

    if jump_01 > 29:
        out.append("→ 0→1 jump is LARGER for 60m+ rays. Bounce streak is a stronger "
                    "signal at HTF.")
    elif jump_01 > 25:
        out.append("→ 0→1 jump is similar at HTF. Bounce streak effect is consistent.")
    else:
        out.append("→ 0→1 jump is SMALLER at HTF. Bounce streak may be weaker for HTF rays.")
    out.append("")

    # Flip frequency
    out.append("**Flip frequency (60m+ rays):**\n")
    fc = pd.Series(flip_counts)
    fc_dist = fc.value_counts().sort_index()
    flip_rows = []
    for nf in [0, 1, 2]:
        flip_rows.append([f"Rays with {nf} flips", fc_dist.get(nf, 0)])
    three_plus = sum(v for k, v in fc_dist.items() if k >= 3)
    flip_rows.append(["Rays with 3+ flips", three_plus])
    flip_rows.append(["Max flips", int(fc.max()) if len(fc) > 0 else 0])

    out.append(md_table(["Metric (60m+ rays)", "Value"], flip_rows))
    out.append("")

    return "\n".join(out)


# =============================================================================
# CHECK 6: REGIME STABILITY (P1 vs P2)
# =============================================================================
def check_6(ixns, rays_df, bars, p1_count):
    out = []
    out.append("=" * 64)
    out.append("CHECK 6: REGIME STABILITY (P1 vs P2 INDEPENDENT)")
    out.append("=" * 64)
    out.append("")

    ixns_valid = ixns[ixns["outcome"].isin(["BOUNCE", "BREAK"])].copy()
    ixns_valid["period"] = np.where(ixns_valid["enter_bar"] < p1_count, "P1", "P2")

    # Compute bounce streak for all interactions
    ixns_sorted = ixns_valid.sort_values("enter_bar")
    streak_map = {}
    for ray_idx in ixns_sorted["ray_idx"].unique():
        ray_ixns = ixns_sorted[ixns_sorted["ray_idx"] == ray_idx].sort_values("enter_bar")
        consec = 0
        flips = 0
        for idx, ix in ray_ixns.iterrows():
            streak_map[idx] = {"bounce_streak": consec, "flips_so_far": flips}
            if ix["outcome"] == "BOUNCE":
                consec += 1
            else:
                consec = 0
                flips += 1

    streak_df = pd.DataFrame.from_dict(streak_map, orient="index")
    ixns_valid = ixns_valid.join(streak_df, how="left")
    ixns_valid["bounce_streak"] = ixns_valid["bounce_streak"].fillna(0).astype(int)

    results = []

    def compute_metric(name, p1_sub, p2_sub, metric_fn):
        p1_val, p1_n = metric_fn(p1_sub)
        p2_val, p2_n = metric_fn(p2_sub)
        low = "LOW CONFIDENCE" if p1_n < 50 else ""
        if p1_val is None or p2_val is None:
            stable = "INSUFFICIENT"
        elif low:
            stable = "LOW CONFIDENCE"
        else:
            same_dir = (p1_val > 0 and p2_val > 0) or (p1_val < 0 and p2_val < 0) or \
                       (abs(p1_val) < 3 and abs(p2_val) < 3)
            if same_dir and abs(p2_val) > 0:
                stable = "STABLE" if abs(p1_val) > abs(p2_val) * 0.5 else "UNSTABLE"
            else:
                stable = "REVERSED" if not same_dir else "UNSTABLE"
        results.append([name, fmt_f(p1_val), p1_n, fmt_f(p2_val), p2_n,
                         f"{stable} {low}".strip()])

    p1 = ixns_valid[ixns_valid["period"] == "P1"]
    p2 = ixns_valid[ixns_valid["period"] == "P2"]

    # 1. Bounce streak 0→1 jump
    def streak_jump(sub):
        s0 = sub[sub["bounce_streak"] == 0]
        s1 = sub[sub["bounce_streak"] == 1]
        if len(s0) == 0 or len(s1) == 0:
            return None, 0
        b0 = (s0["outcome"] == "BOUNCE").mean() * 100
        b1 = (s1["outcome"] == "BOUNCE").mean() * 100
        return b1 - b0, len(s0) + len(s1)
    compute_metric("Bounce streak 0→1 jump (pp)", p1, p2, streak_jump)

    # 2. Bounce streak 3+ bounce %
    def streak_3plus(sub):
        s3 = sub[sub["bounce_streak"] >= 3]
        if len(s3) == 0:
            return None, 0
        return (s3["outcome"] == "BOUNCE").mean() * 100, len(s3)
    compute_metric("Bounce streak 3+ bounce %", p1, p2, streak_3plus)

    # 3. Dwell 1-2 bar
    def dwell_12(sub):
        d = sub[(sub["dwell"] >= 1) & (sub["dwell"] <= 2)]
        if len(d) == 0:
            return None, 0
        return (d["outcome"] == "BOUNCE").mean() * 100, len(d)
    compute_metric("Dwell time 1-2 bar bounce %", p1, p2, dwell_12)

    # 4. Dwell 10+
    def dwell_10p(sub):
        d = sub[sub["dwell"] >= 10]
        if len(d) == 0:
            return None, 0
        return (d["outcome"] == "BOUNCE").mean() * 100, len(d)
    compute_metric("Dwell time 10+ bar bounce %", p1, p2, dwell_10p)

    # 5. ETH vs RTH spread
    def eth_rth_spread(sub):
        eth = sub[sub["session"] == "ETH"]
        rth = sub[sub["session"] == "RTH"]
        if len(eth) == 0 or len(rth) == 0:
            return None, 0
        be = (eth["outcome"] == "BOUNCE").mean() * 100
        br = (rth["outcome"] == "BOUNCE").mean() * 100
        return be - br, len(eth) + len(rth)
    compute_metric("ETH vs RTH spread (pp)", p1, p2, eth_rth_spread)

    # 6. Flip count 0 bounce %
    def flip_0(sub):
        f0 = sub[sub["flips_so_far"] == 0]
        if len(f0) == 0:
            return None, 0
        return (f0["outcome"] == "BOUNCE").mean() * 100, len(f0)
    compute_metric("Flip count 0-flip bounce %", p1, p2, flip_0)

    # 7. Overall bounce %
    def overall_bounce(sub):
        if len(sub) == 0:
            return None, 0
        return (sub["outcome"] == "BOUNCE").mean() * 100, len(sub)
    compute_metric("Overall bounce % at 40t", p1, p2, overall_bounce)

    out.append(md_table(
        ["Finding", "P1 value", "P1 n", "P2 value", "P2 n", "Stable?"],
        results
    ))
    out.append("")

    # Flag unstable findings
    unstable = [r for r in results if "UNSTABLE" in r[5] or "REVERSED" in r[5]]
    if unstable:
        out.append("**⚠️ UNSTABLE/REVERSED findings — do NOT advance without investigation:**")
        for r in unstable:
            out.append(f"- {r[0]}: P1={r[1]} vs P2={r[3]} → {r[5]}")
    else:
        out.append("All findings either STABLE or LOW CONFIDENCE (P1 sample limitation).")
    out.append("")

    return "\n".join(out)


# =============================================================================
# CHECK 7: DWELL TIME SURVIVAL CURVE
# =============================================================================
def check_7(ixns):
    out = []
    out.append("=" * 64)
    out.append("CHECK 7: DWELL TIME SURVIVAL CURVE")
    out.append("=" * 64)
    out.append("")

    ixns_valid = ixns[ixns["outcome"].isin(["BOUNCE", "BREAK"])].copy()

    checkpoints = [1, 2, 3, 5, 8, 10, 15, 20]
    surv_rows = []
    for cp in checkpoints:
        # Interactions where dwell >= cp (still in proximity at bar cp)
        still_in = ixns_valid[ixns_valid["dwell"] >= cp]
        n = len(still_in)
        nb = (still_in["outcome"] == "BOUNCE").sum()
        surv_rows.append([
            cp, n, fmt_pct(nb, n), n
        ])

    out.append(md_table(
        ["Bars dwelling so far", "Still unresolved", "Eventually bounce %", "n"],
        surv_rows
    ))
    out.append("")

    # Interpretation
    if len(surv_rows) >= 3:
        pcts = []
        for row in surv_rows:
            pct_str = row[2]
            if pct_str != "N/A":
                pcts.append(float(pct_str.replace("%", "")))
            else:
                pcts.append(None)

        valid_pcts = [p for p in pcts if p is not None]
        if len(valid_pcts) >= 4:
            spread = valid_pcts[0] - valid_pcts[-1]
            # Check for sudden drop
            max_drop = 0
            drop_at = 0
            for i in range(1, len(valid_pcts)):
                d = valid_pcts[i - 1] - valid_pcts[i]
                if d > max_drop:
                    max_drop = d
                    drop_at = checkpoints[i]

            if spread > 10 and max_drop < spread * 0.6:
                out.append(f"→ **Steady decay pattern.** Bounce % drops {spread:.1f}pp from bar 1 to "
                           f"bar {checkpoints[len(valid_pcts)-1]}. Dwell time is a REAL-TIME decay signal. "
                           f"Usable as a live exit trigger.")
            elif max_drop > 8:
                out.append(f"→ **Threshold pattern.** Largest drop ({max_drop:.1f}pp) at bar {drop_at}. "
                           f"Before bar {drop_at}, interaction is viable. After, probability degrades sharply.")
            else:
                out.append(f"→ **Flat pattern.** Only {spread:.1f}pp spread. Dwell time is an outcome "
                           f"characteristic, not a real-time signal. Useful post-hoc only.")
    out.append("")

    return "\n".join(out)


# =============================================================================
# CHECK 8: FLIP COUNT AT TIGHTER THRESHOLD (20t)
# =============================================================================
def check_8(bars, rays_df, bars_15m):
    out = []
    out.append("=" * 64)
    out.append("CHECK 8: FLIP COUNT AT TIGHTER THRESHOLD (20t)")
    out.append("=" * 64)
    out.append("")

    highs = bars["High"].values.astype(np.float64)
    lows = bars["Low"].values.astype(np.float64)
    closes = bars["Close"].values.astype(np.float64)
    dts = bars["DateTime"].values

    print("  Detecting interactions at 20t threshold...")
    ixns_20t = detect_interactions(highs, lows, closes, rays_df, PROX_20T, bars_dt=dts)
    ixns_20t = add_15m_outcome(ixns_20t, bars, bars_15m)
    ixns_20t_valid = ixns_20t[ixns_20t["outcome"].isin(["BOUNCE", "BREAK"])].copy()
    ixns_20t_valid = ixns_20t_valid.sort_values("enter_bar")

    # A) Flip frequency
    out.append("### A) Flip frequency at 20t\n")
    flip_counts = {}
    streak_data = []
    retest_data = []

    for ray_idx in ixns_20t_valid["ray_idx"].unique():
        ray_ixns = ixns_20t_valid[ixns_20t_valid["ray_idx"] == ray_idx].sort_values("enter_bar")
        flips = 0
        consec = 0
        pre_flip_bounces = 0
        ixn_list = list(ray_ixns.iterrows())

        for i, (_, ix) in enumerate(ixn_list):
            streak_data.append({
                "bounce_streak": min(consec, 3),
                "outcome": ix["outcome"],
            })

            if ix["outcome"] == "BOUNCE":
                consec += 1
                pre_flip_bounces += 1
            elif ix["outcome"] == "BREAK":
                flips += 1
                # Retest data
                if i + 1 < len(ixn_list):
                    _, next_ix = ixn_list[i + 1]
                    retest_data.append({
                        "pre_flip_bounces": min(pre_flip_bounces, 3),
                        "retest_outcome": next_ix["outcome"],
                    })
                consec = 0
                pre_flip_bounces = 0

        flip_counts[ray_idx] = flips

    fc = pd.Series(flip_counts)
    fc_dist = fc.value_counts().sort_index()

    flip_rows = []
    for nf in [0, 1, 2]:
        flip_rows.append([f"Rays with {nf} flips", fc_dist.get(nf, 0)])
    three_plus = sum(v for k, v in fc_dist.items() if k >= 3)
    flip_rows.append(["Rays with 3+ flips", three_plus])
    flip_rows.append(["Max flips", int(fc.max()) if len(fc) > 0 else 0])

    out.append(md_table(["Metric (20t)", "Value"], flip_rows))
    out.append("")

    # B) Bounce streak at 20t
    out.append("### B) Bounce streak at 20t\n")
    sd = pd.DataFrame(streak_data)
    streak_rows = []
    for ns, label in [(0, "0 (just flipped)"), (1, "1 confirmed"),
                      (2, "2 confirmed"), (3, "3+ confirmed")]:
        sub = sd[sd["bounce_streak"] == ns]
        n = len(sub)
        nb = (sub["outcome"] == "BOUNCE").sum()
        streak_rows.append([label, fmt_pct(nb, n), n])
    out.append(md_table(["Bounce streak (20t)", "Next bounce %", "n"], streak_rows))
    out.append("")

    # C) Compare to baseline
    out.append("### C) Comparison to 40t baseline\n")
    s0 = sd[sd["bounce_streak"] == 0]
    s1 = sd[sd["bounce_streak"] == 1]
    s3 = sd[sd["bounce_streak"] == 3]
    b0 = (s0["outcome"] == "BOUNCE").mean() * 100 if len(s0) > 0 else 0
    b1 = (s1["outcome"] == "BOUNCE").mean() * 100 if len(s1) > 0 else 0
    b3 = (s3["outcome"] == "BOUNCE").mean() * 100 if len(s3) > 0 else 0
    jump_20t = b1 - b0

    out.append(md_table(
        ["Metric", "40t baseline", "20t follow-up"],
        [
            ["Bounce streak 0→1 jump", "29.0pp", f"{jump_20t:.1f}pp"],
            ["3+ bounce rate", "79.2%", f"{b3:.1f}%"],
            ["Max flips per ray", "313", str(int(fc.max()) if len(fc) > 0 else 0)],
            ["Rays with 3+ flips", "302", str(three_plus)],
        ]
    ))
    out.append("")

    if jump_20t > 29:
        out.append("→ Bounce streak spread is WIDER at 20t. **Use 20t for lifecycle/flip tracking.**")
    elif jump_20t > 25:
        out.append("→ Bounce streak spread is similar at 20t. Both thresholds produce valid lifecycle.")
    elif jump_20t < 15:
        out.append("→ Bounce streak spread NARROWS at 20t. **40t is correct** despite high flip counts.")
    else:
        out.append("→ Moderate narrowing. Review flip counts for guidance.")

    if fc.max() < 50:
        out.append(f"→ Max flips dropped dramatically (313 → {int(fc.max())}). "
                    f"**40t was counting noise as flips. 20t is the correct lifecycle threshold.**")
    out.append("")

    # D) Retest at 20t
    out.append("### D) Retest after flip at 20t\n")
    rd = pd.DataFrame(retest_data)
    if len(rd) > 0:
        rd_valid = rd[rd["retest_outcome"].isin(["BOUNCE", "BREAK"])]
        retest_rows = []
        for nb_label, nb_val in [(0, "0 (broke on first)"), (1, "1 bounce before break"),
                                  (2, "2 bounces before break"), (3, "3+ bounces before break")]:
            sub = rd_valid[rd_valid["pre_flip_bounces"] == nb_val if isinstance(nb_val, int) else
                           rd_valid["pre_flip_bounces"] == nb_label]
            # Fix: use numeric comparison
            sub = rd_valid[rd_valid["pre_flip_bounces"] == nb_label]
            n = len(sub)
            nbo = (sub["retest_outcome"] == "BOUNCE").sum()
            retest_rows.append([nb_val, fmt_pct(nbo, n), n])
        out.append(md_table(
            ["Pre-flip bounces (20t)", "Retest bounce %", "n"],
            retest_rows
        ))
        out.append("")

        # Check for carryover
        r0 = rd_valid[rd_valid["pre_flip_bounces"] == 0]
        r3 = rd_valid[rd_valid["pre_flip_bounces"] == 3]
        if len(r0) > 10 and len(r3) > 10:
            b_r0 = (r0["retest_outcome"] == "BOUNCE").mean() * 100
            b_r3 = (r3["retest_outcome"] == "BOUNCE").mean() * 100
            if b_r3 > b_r0 + 5:
                out.append("→ **Pre-flip strength CARRIES OVER at 20t.** The 40t flips were too "
                            "noisy to detect this effect.")
            else:
                out.append("→ No carryover effect at 20t either. Polarity resets are complete "
                            "regardless of threshold.")
    else:
        out.append("No retest data available at 20t.\n")
    out.append("")

    return "\n".join(out), ixns_20t


# =============================================================================
# CHECK 9: HTF RAYS AS STOP / TARGET / ENTRY
# =============================================================================
def check_9(zte, ray_ctx, rays_df, bars):
    out = []
    out.append("=" * 64)
    out.append("CHECK 9: HTF RAYS AS STOP / TARGET / ENTRY REFINEMENT")
    out.append("=" * 64)
    out.append("")

    highs = bars["High"].values.astype(np.float64)
    lows = bars["Low"].values.astype(np.float64)
    closes = bars["Close"].values.astype(np.float64)

    rc_htf = ray_ctx[ray_ctx["RayTF"].apply(is_htf)].copy()
    htf_rays = rays_df[rays_df["is_htf"]].copy()
    ray_prices_htf = htf_rays["price"].values
    ray_creation_bars_htf = htf_rays["creation_bar"].values

    zte_valid = zte[
        (zte["TouchType"] != "VP_RAY") & (zte["QualityScore"] > 0) & (zte["Reaction"] > 0)
    ].copy()

    out.append(f"Qualifying touches: {len(zte_valid)}\n")

    # A) TIGHTER STOPS VIA ADVERSE-SIDE HTF RAY
    out.append("### 9A) Tighter stops via adverse-side HTF ray\n")

    adverse_data = []
    for _, touch in zte_valid.iterrows():
        bar_idx = int(touch["BarIndex"])
        zw = touch["ZoneWidthTicks"] * TICK_SIZE
        tt = touch["TouchType"]
        stop_dist = max(1.5 * zw, 120 * TICK_SIZE)

        if tt == "DEMAND_EDGE":
            entry = touch["ZoneTop"]
            stop_price = entry - stop_dist
            # Adverse side is below entry
            active = ray_prices_htf[ray_creation_bars_htf <= bar_idx]
            adverse_rays = active[(active < entry) & (active > stop_price)]
        elif tt == "SUPPLY_EDGE":
            entry = touch["ZoneBot"]
            stop_price = entry + stop_dist
            active = ray_prices_htf[ray_creation_bars_htf <= bar_idx]
            adverse_rays = active[(active > entry) & (active < stop_price)]
        else:
            continue

        if len(adverse_rays) > 0:
            # Nearest adverse ray
            if tt == "DEMAND_EDGE":
                nearest = adverse_rays[np.argmax(adverse_rays)]  # closest to entry (highest)
                ray_dist = (entry - nearest) / TICK_SIZE
            else:
                nearest = adverse_rays[np.argmin(adverse_rays)]
                ray_dist = (nearest - entry) / TICK_SIZE

            # Check if price breaks through the adverse ray
            obs_end = min(bar_idx + 200, len(closes))
            if tt == "DEMAND_EDGE":
                broke_ray = np.any(lows[bar_idx:obs_end] < nearest)
                hit_stop = np.any(lows[bar_idx:obs_end] < stop_price + TICK_SIZE)
            else:
                broke_ray = np.any(highs[bar_idx:obs_end] > nearest)
                hit_stop = np.any(highs[bar_idx:obs_end] > stop_price - TICK_SIZE)

            adverse_data.append({
                "has_adverse": True,
                "ray_dist": ray_dist,
                "stop_dist": stop_dist / TICK_SIZE,
                "reduction": (stop_dist / TICK_SIZE) - ray_dist,
                "broke_ray": broke_ray,
                "hit_stop": hit_stop,
                "broke_then_stop": broke_ray and hit_stop,
            })
        else:
            adverse_data.append({"has_adverse": False})

    ad = pd.DataFrame(adverse_data)
    has_adv = ad[ad["has_adverse"] == True]

    out.append(md_table(
        ["Metric", "Value"],
        [
            ["Qualifying touches with adverse HTF ray within stop",
             f"{len(has_adv)} ({fmt_pct(len(has_adv), len(ad))})"],
            ["Mean adverse HTF ray distance from entry (ticks)",
             fmt_f(has_adv["ray_dist"].mean()) if len(has_adv) > 0 else "N/A"],
            ["Mean current stop distance (ticks)",
             fmt_f(has_adv["stop_dist"].mean()) if len(has_adv) > 0 else "N/A"],
            ["Potential stop reduction (ticks)",
             fmt_f(has_adv["reduction"].mean()) if len(has_adv) > 0 else "N/A"],
        ]
    ))
    out.append("")

    if len(has_adv) > 0:
        broke = has_adv[has_adv["broke_ray"]]
        out.append("**After adverse HTF ray break:**\n")
        n_broke = len(broke)
        n_cont_stop = broke["hit_stop"].sum()
        n_reversed = n_broke - n_cont_stop
        out.append(md_table(
            ["After adverse HTF ray break", "Count", "%"],
            [
                ["Price continues to full stop level", n_cont_stop,
                 fmt_pct(n_cont_stop, n_broke)],
                ["Price reverses before reaching stop", n_reversed,
                 fmt_pct(n_reversed, n_broke)],
            ]
        ))
        out.append("")

    # B) HTF RAY AS EARLIER TARGET
    out.append("### 9B) HTF ray as earlier target\n")

    # HTF ray spacing
    sorted_htf = np.sort(ray_prices_htf)
    if len(sorted_htf) > 1:
        spacings = np.diff(sorted_htf) / TICK_SIZE
        spacings = spacings[spacings > 0]
    else:
        spacings = np.array([0])

    target_data = []
    for _, touch in zte_valid.iterrows():
        bar_idx = int(touch["BarIndex"])
        zw = touch["ZoneWidthTicks"] * TICK_SIZE
        tt = touch["TouchType"]
        stop_dist = max(1.5 * zw, 120 * TICK_SIZE)

        if tt == "DEMAND_EDGE":
            entry = touch["ZoneTop"]
            t1 = entry + 0.5 * zw
            stop_price = entry - stop_dist
        elif tt == "SUPPLY_EDGE":
            entry = touch["ZoneBot"]
            t1 = entry - 0.5 * zw
            stop_price = entry + stop_dist
        else:
            continue

        active = ray_prices_htf[ray_creation_bars_htf <= bar_idx]

        if tt == "DEMAND_EDGE":
            between = active[(active > entry + 5 * TICK_SIZE) & (active < t1)]
        else:
            between = active[(active < entry - 5 * TICK_SIZE) & (active > t1)]

        if len(between) > 0:
            if tt == "DEMAND_EDGE":
                nearest_target_ray = between[np.argmin(between)]  # nearest above entry
                ray_dist_from_entry = (nearest_target_ray - entry) / TICK_SIZE
            else:
                nearest_target_ray = between[np.argmax(between)]
                ray_dist_from_entry = (entry - nearest_target_ray) / TICK_SIZE

            t1_dist = abs(t1 - entry) / TICK_SIZE
            ray_pct_of_t1 = ray_dist_from_entry / t1_dist * 100 if t1_dist > 0 else 0

            # Check outcome at the ray
            obs_end = min(bar_idx + 200, len(closes))
            obs_hi = highs[bar_idx:obs_end]
            obs_lo = lows[bar_idx:obs_end]

            if tt == "DEMAND_EDGE":
                reached_ray = np.any(obs_hi >= nearest_target_ray - 5 * TICK_SIZE)
                reached_t1 = np.any(obs_hi >= t1)
                hit_stop = np.any(obs_lo <= stop_price + TICK_SIZE)
            else:
                reached_ray = np.any(obs_lo <= nearest_target_ray + 5 * TICK_SIZE)
                reached_t1 = np.any(obs_lo <= t1)
                hit_stop = np.any(obs_hi >= stop_price - TICK_SIZE)

            # Stall = reached ray but then stayed near for 3+ bars
            stalled = False
            if reached_ray:
                for b in range(len(obs_hi)):
                    if tt == "DEMAND_EDGE":
                        near = abs(obs_hi[b] - nearest_target_ray) < 10 * TICK_SIZE
                    else:
                        near = abs(obs_lo[b] - nearest_target_ray) < 10 * TICK_SIZE
                    if near:
                        consec = 1
                        for b2 in range(b + 1, min(b + 5, len(obs_hi))):
                            if tt == "DEMAND_EDGE":
                                if abs(obs_hi[b2] - nearest_target_ray) < 10 * TICK_SIZE:
                                    consec += 1
                            else:
                                if abs(obs_lo[b2] - nearest_target_ray) < 10 * TICK_SIZE:
                                    consec += 1
                        if consec >= 3:
                            stalled = True
                        break

            if reached_ray and reached_t1 and not stalled:
                outcome = "passes_to_t1"
            elif reached_ray and reached_t1 and stalled:
                outcome = "stalls_then_t1"
            elif reached_ray and not reached_t1 and hit_stop:
                outcome = "stalls_reverses_to_stop"
            elif reached_ray and not reached_t1:
                outcome = "stalls_reverses_no_t1"
            else:
                outcome = "no_reach_ray"

            # PnL comparison
            if outcome in ["stalls_reverses_to_stop", "stalls_reverses_no_t1"]:
                pnl_at_ray = ray_dist_from_entry  # profit in ticks if exited at ray
                pnl_at_t1 = -stop_dist / TICK_SIZE if hit_stop else 0  # loss if held to stop
            else:
                pnl_at_ray = ray_dist_from_entry if reached_ray else 0
                pnl_at_t1 = t1_dist if reached_t1 else (-stop_dist / TICK_SIZE if hit_stop else 0)

            target_data.append({
                "has_target_ray": True,
                "ray_dist": ray_dist_from_entry,
                "ray_pct_of_t1": ray_pct_of_t1,
                "outcome": outcome,
                "pnl_at_ray": pnl_at_ray,
                "pnl_at_t1": pnl_at_t1,
            })
        else:
            target_data.append({"has_target_ray": False})

    td = pd.DataFrame(target_data)
    has_target = td[td["has_target_ray"] == True]

    out.append(md_table(
        ["Metric (60m+ rays only)", "Value"],
        [
            ["Mean distance between adjacent HTF rays",
             fmt_f(spacings.mean()) if len(spacings) > 0 else "N/A"],
            ["Median distance between adjacent HTF rays",
             fmt_f(np.median(spacings)) if len(spacings) > 0 else "N/A"],
            ["% of qualifying touches with HTF ray between entry and T1",
             fmt_pct(len(has_target), len(td))],
            ["Mean HTF ray distance from entry (as % of T1)",
             fmt_f(has_target["ray_pct_of_t1"].mean()) if len(has_target) > 0 else "N/A"],
        ]
    ))
    out.append("")

    if len(has_target) > 0:
        outcomes = has_target["outcome"].value_counts()
        outcome_rows = [
            ["Price passes through ray, reaches T1",
             outcomes.get("passes_to_t1", 0),
             fmt_pct(outcomes.get("passes_to_t1", 0), len(has_target))],
            ["Price stalls at ray, eventually reaches T1",
             outcomes.get("stalls_then_t1", 0),
             fmt_pct(outcomes.get("stalls_then_t1", 0), len(has_target))],
            ["Price stalls at ray, reverses (never T1)",
             outcomes.get("stalls_reverses_no_t1", 0),
             fmt_pct(outcomes.get("stalls_reverses_no_t1", 0), len(has_target))],
            ["Price stalls at ray, reverses to stop",
             outcomes.get("stalls_reverses_to_stop", 0),
             fmt_pct(outcomes.get("stalls_reverses_to_stop", 0), len(has_target))],
        ]
        out.append(md_table(
            ["Outcome at the HTF ray", "Count", "%"],
            outcome_rows
        ))
        out.append("")

        # PnL comparison for stall-reversal trades
        stall_rev = has_target[has_target["outcome"].isin([
            "stalls_reverses_to_stop", "stalls_reverses_no_t1"
        ])]
        if len(stall_rev) > 0:
            out.append("**PnL comparison for stall-reversal trades:**\n")
            out.append(f"- PnL taking profit at HTF ray: {fmt_f(stall_rev['pnl_at_ray'].mean())} ticks/trade")
            out.append(f"- PnL under current T1 target: {fmt_f(stall_rev['pnl_at_t1'].mean())} ticks/trade")
            out.append(f"- Net improvement from ray-based early exit: "
                       f"{fmt_f(stall_rev['pnl_at_ray'].mean() - stall_rev['pnl_at_t1'].mean())} ticks/trade")
            out.append(f"- n = {len(stall_rev)} trades")
            out.append("")

    # C) PRECISION ENTRY VIA HTF RAY INSIDE ZONE
    out.append("### 9C) Precision entry via HTF ray inside zone\n")

    wide_zte = zte_valid[zte_valid["ZoneWidthTicks"] > 200].copy()
    out.append(f"Wide zone touches (ZW > 200t): {len(wide_zte)}\n")

    entry_data = []
    for _, touch in wide_zte.iterrows():
        bar_idx = int(touch["BarIndex"])
        zw = touch["ZoneWidthTicks"] * TICK_SIZE
        zt = touch["ZoneTop"]
        zb = touch["ZoneBot"]
        tt = touch["TouchType"]
        stop_dist = max(1.5 * zw, 120 * TICK_SIZE)

        active = ray_prices_htf[ray_creation_bars_htf <= bar_idx]
        inside = active[(active >= zb) & (active <= zt)]

        if len(inside) > 0:
            if tt == "DEMAND_EDGE":
                entry_edge = zt
                t1 = entry_edge + 0.5 * zw
                # Pick ray closest to center of zone
                center = (zt + zb) / 2
                best_ray = inside[np.argmin(np.abs(inside - center))]
                depth = (entry_edge - best_ray) / TICK_SIZE  # positive = deeper into zone
                entry_ray = best_ray
                t1_from_ray = (t1 - entry_ray) / TICK_SIZE
                stop_from_ray = (entry_ray - (entry_edge - stop_dist)) / TICK_SIZE
            elif tt == "SUPPLY_EDGE":
                entry_edge = zb
                t1 = entry_edge - 0.5 * zw
                center = (zt + zb) / 2
                best_ray = inside[np.argmin(np.abs(inside - center))]
                depth = (best_ray - entry_edge) / TICK_SIZE
                entry_ray = best_ray
                t1_from_ray = (entry_ray - t1) / TICK_SIZE
                stop_from_ray = ((entry_edge + stop_dist) - entry_ray) / TICK_SIZE
            else:
                continue

            t1_from_edge = abs(t1 - entry_edge) / TICK_SIZE
            stop_from_edge = stop_dist / TICK_SIZE
            rr_edge = t1_from_edge / stop_from_edge if stop_from_edge > 0 else 0
            rr_ray = t1_from_ray / stop_from_ray if stop_from_ray > 0 else 0

            # Did price reach the ray inside?
            obs_end = min(bar_idx + 50, len(closes))
            if tt == "DEMAND_EDGE":
                reached = np.any(lows[bar_idx:obs_end] <= entry_ray + 5 * TICK_SIZE)
            else:
                reached = np.any(highs[bar_idx:obs_end] >= entry_ray - 5 * TICK_SIZE)

            entry_data.append({
                "has_inside_ray": True,
                "depth_ticks": depth,
                "depth_pct": depth / (zw / TICK_SIZE) * 100,
                "t1_from_edge": t1_from_edge,
                "t1_from_ray": t1_from_ray,
                "stop_from_edge": stop_from_edge,
                "stop_from_ray": stop_from_ray,
                "rr_edge": rr_edge,
                "rr_ray": rr_ray,
                "price_reached": reached,
            })
        else:
            entry_data.append({"has_inside_ray": False})

    ed = pd.DataFrame(entry_data)
    has_inside = ed[ed["has_inside_ray"] == True]

    if len(has_inside) > 0:
        out.append(md_table(
            ["Metric", "Value"],
            [
                ["Wide zone touches with HTF ray inside zone",
                 f"{len(has_inside)} ({fmt_pct(len(has_inside), len(ed))})"],
                ["Mean ray depth inside zone (ticks from edge)",
                 fmt_f(has_inside["depth_ticks"].mean())],
                ["Mean ray depth (as % of zone width)",
                 f"{fmt_f(has_inside['depth_pct'].mean())}%"],
            ]
        ))
        out.append("")

        out.append("**Geometry comparison:**\n")
        out.append(md_table(
            ["Metric", "Edge entry (current)", "Ray entry (shifted)"],
            [
                ["Mean entry to T1 distance",
                 fmt_f(has_inside["t1_from_edge"].mean()),
                 fmt_f(has_inside["t1_from_ray"].mean())],
                ["Mean entry to stop distance",
                 fmt_f(has_inside["stop_from_edge"].mean()),
                 fmt_f(has_inside["stop_from_ray"].mean())],
                ["Risk:reward ratio",
                 fmt_f(has_inside["rr_edge"].mean(), 2),
                 fmt_f(has_inside["rr_ray"].mean(), 2)],
            ]
        ))
        out.append("")

        reached = has_inside[has_inside["price_reached"] == True]
        missed = has_inside[has_inside["price_reached"] == False]
        out.append(md_table(
            ["Metric", "Value"],
            [
                ["Wide zone touches where price reaches HTF ray inside",
                 f"{len(reached)} ({fmt_pct(len(reached), len(has_inside))})"],
                ["Trades missed by waiting for ray entry",
                 f"{len(missed)} ({fmt_pct(len(missed), len(has_inside))})"],
            ]
        ))
    else:
        out.append("No wide zone touches with HTF ray inside zone.\n")
    out.append("")

    return "\n".join(out)


# =============================================================================
# SUMMARY
# =============================================================================
def build_summary(all_results):
    out = []
    out.append("=" * 64)
    out.append("SUMMARY")
    out.append("=" * 64)
    out.append("")

    out.append("| Check | Finding | Status |")
    out.append("|---|---|---|")
    for check, finding, status in all_results:
        out.append(f"| {check} | {finding} | {status} |")
    out.append("")
    return "\n".join(out)


# =============================================================================
# MAIN
# =============================================================================
def main():
    start_time = datetime.now()
    print(f"Ray HTF Follow-up — started {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 64)

    bars, ray_ref, zte, ray_ctx, p1_count = load_all_data()
    print("\nBuilding ray timeline...")
    rays_df, events_df = build_rays(ray_ref)

    print("Loading 15m bars...")
    try:
        bars_15m = load_15m_bars()
    except Exception as e:
        print(f"  Warning: {e}")
        bars_15m = None

    # Detect interactions at 40t (baseline threshold)
    print("\nDetecting interactions at 40t threshold...")
    highs = bars["High"].values.astype(np.float64)
    lows = bars["Low"].values.astype(np.float64)
    closes = bars["Close"].values.astype(np.float64)
    dts = bars["DateTime"].values
    ixns = detect_interactions(highs, lows, closes, rays_df, PROX_THRESHOLD, bars_dt=dts)
    ixns = add_15m_outcome(ixns, bars, bars_15m)
    print(f"  {len(ixns)} interactions detected")

    all_output = []
    all_output.append("# Ray HTF Follow-up — Deconfounding and Regime Checks")
    all_output.append(f"Generated: {start_time.strftime('%Y-%m-%d %H:%M')}")
    all_output.append(f"Data: P1 + P2 combined | Threshold: 40t (close-based) | 15m bar close")
    all_output.append("")

    summary_results = []

    # Check 1
    try:
        print("\n--- CHECK 1: HTF Density ---")
        c1, use_continuous, rc_htf, htf_rays = check_1(zte, ray_ctx, rays_df)
        all_output.append(c1)
        summary_results.append(("1. HTF density",
                                 f"60m+ filter: use_continuous={use_continuous}",
                                 "REFINED" if not use_continuous else "NEW FINDING"))
        print("  Check 1 complete.")
    except Exception as e:
        all_output.append(f"\n**CHECK 1 ERROR:** {e}\n{traceback.format_exc()}\n")
        use_continuous = True
        print(f"  Check 1 FAILED: {e}")

    # Check 2
    try:
        print("\n--- CHECK 2: Fresh + Fresh ---")
        c2 = check_2(zte, ray_ctx, use_continuous)
        all_output.append(c2)
        summary_results.append(("2. Fresh + fresh", "Ray×zone freshness interaction", "See data"))
        print("  Check 2 complete.")
    except Exception as e:
        all_output.append(f"\n**CHECK 2 ERROR:** {e}\n{traceback.format_exc()}\n")
        print(f"  Check 2 FAILED: {e}")

    # Check 3
    try:
        print("\n--- CHECK 3: HTF R/P ---")
        c3 = check_3(zte, ray_ctx)
        all_output.append(c3)
        summary_results.append(("3. HTF R/P", "Congestion vs confluence (cleaned)", "See data"))
        print("  Check 3 complete.")
    except Exception as e:
        all_output.append(f"\n**CHECK 3 ERROR:** {e}\n{traceback.format_exc()}\n")
        print(f"  Check 3 FAILED: {e}")

    # Check 4
    try:
        print("\n--- CHECK 4: Age vs Streak ---")
        c4 = check_4(ixns, rays_df)
        all_output.append(c4)
        summary_results.append(("4. Age vs streak", "Deconfounding freshness from bounce streak", "See data"))
        print("  Check 4 complete.")
    except Exception as e:
        all_output.append(f"\n**CHECK 4 ERROR:** {e}\n{traceback.format_exc()}\n")
        print(f"  Check 4 FAILED: {e}")

    # Check 5
    try:
        print("\n--- CHECK 5: HTF Lifecycle ---")
        c5 = check_5(ixns, rays_df)
        all_output.append(c5)
        summary_results.append(("5. HTF lifecycle", "Bounce streak at 60m+", "See data"))
        print("  Check 5 complete.")
    except Exception as e:
        all_output.append(f"\n**CHECK 5 ERROR:** {e}\n{traceback.format_exc()}\n")
        print(f"  Check 5 FAILED: {e}")

    # Check 6
    try:
        print("\n--- CHECK 6: Regime Stability ---")
        c6 = check_6(ixns, rays_df, bars, p1_count)
        all_output.append(c6)
        summary_results.append(("6. Regime stability", "P1 vs P2 independent", "See data"))
        print("  Check 6 complete.")
    except Exception as e:
        all_output.append(f"\n**CHECK 6 ERROR:** {e}\n{traceback.format_exc()}\n")
        print(f"  Check 6 FAILED: {e}")

    # Check 7
    try:
        print("\n--- CHECK 7: Dwell Survival ---")
        c7 = check_7(ixns)
        all_output.append(c7)
        summary_results.append(("7. Dwell survival", "Real-time usability of dwell time", "See data"))
        print("  Check 7 complete.")
    except Exception as e:
        all_output.append(f"\n**CHECK 7 ERROR:** {e}\n{traceback.format_exc()}\n")
        print(f"  Check 7 FAILED: {e}")

    # Check 8
    try:
        print("\n--- CHECK 8: Tighter Flips (20t) ---")
        c8, ixns_20t = check_8(bars, rays_df, bars_15m)
        all_output.append(c8)
        summary_results.append(("8. Tighter flips", "20t lifecycle vs 40t baseline", "See data"))
        print("  Check 8 complete.")
    except Exception as e:
        all_output.append(f"\n**CHECK 8 ERROR:** {e}\n{traceback.format_exc()}\n")
        print(f"  Check 8 FAILED: {e}")

    # Check 9
    try:
        print("\n--- CHECK 9: HTF Stop/Target/Entry ---")
        c9 = check_9(zte, ray_ctx, rays_df, bars)
        all_output.append(c9)
        summary_results.append(("9a. HTF stop", "Adverse HTF ray as stop", "See data"))
        summary_results.append(("9b. HTF target", "HTF ray between entry and T1", "See data"))
        summary_results.append(("9c. Precision entry", "HTF ray inside zone entry", "See data"))
        print("  Check 9 complete.")
    except Exception as e:
        all_output.append(f"\n**CHECK 9 ERROR:** {e}\n{traceback.format_exc()}\n")
        print(f"  Check 9 FAILED: {e}")

    # Summary
    all_output.append(build_summary(summary_results))

    # Write output
    output_path = OUTPUT_DIR / "ray_htf_followup.md"
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(all_output))

    elapsed = datetime.now() - start_time
    print(f"\n{'=' * 64}")
    print(f"Follow-up complete in {elapsed}")
    print(f"Results saved to: {output_path}")


if __name__ == "__main__":
    main()
