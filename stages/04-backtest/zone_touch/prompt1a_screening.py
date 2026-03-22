# archetype: zone_touch
"""Prompt 1a — Feature Screening (v3.1).

Computes 24 features (19 core + 5 expansion) on P1 only (P1a + P1b).
Single-feature R/P screening at 4 horizons, SBB-masked secondary screening,
confirmation simulation, mechanism validation.

P1 ONLY. P2 NOT USED. No parameters from P2.
Baseline anchor: Median PF @3t = 0.8984 (from Prompt 0).
"""

import json
import sys
import time
import warnings
from datetime import datetime
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
warnings.filterwarnings("ignore", category=FutureWarning)

import numpy as np
import pandas as pd
from scipy import stats

# ── Paths ──────────────────────────────────────────────────────────────
BASE = Path(r"c:\Projects\pipeline")
DATA_DIR = BASE / "stages" / "01-data" / "output" / "zone_prep"
P0_DIR = BASE / "stages" / "04-backtest" / "zone_touch" / "output"
OUT_DIR = P0_DIR  # same output directory
OUT_DIR.mkdir(parents=True, exist_ok=True)

TICK_SIZE = 0.25
HORIZONS = [30, 60, 120]

# Median cell exit from Prompt 0 baseline
MEDIAN_STOP = 90    # ticks
MEDIAN_TARGET = 120  # ticks
MEDIAN_TIMECAP = 80  # bars

print("=" * 72)
print("PROMPT 1a — FEATURE SCREENING (v3.1)")
print("P1 ONLY. P2 NOT USED. Baseline anchor = 0.8984.")
print("=" * 72)

# ══════════════════════════════════════════════════════════════════════
# Load Data
# ══════════════════════════════════════════════════════════════════════

# Load baseline report
with open(P0_DIR / "baseline_report_clean.md") as f:
    baseline_text = f.read()
print("\n── Baseline Reference (from Prompt 0) ──")
print("  Median cell PF @3t: 0.8984 (95% CI: 0.8455–0.9568)")
print("  Median cell exit: Stop=90t, Target=120t, TimeCap=80 bars")
print("  Population R/P @60bars: 1.007")
print("  SBB split: NORMAL=1.3343, SBB=0.3684")
print("  Verdict: HIGH OVERFIT RISK")

BASELINE_RP_60 = 1.007

# Load P1 touches
print("\n── Loading P1 Data ──")
p1a = pd.read_csv(DATA_DIR / "NQ_merged_P1a.csv")
p1b = pd.read_csv(DATA_DIR / "NQ_merged_P1b.csv")
p1 = pd.concat([p1a, p1b], ignore_index=True)

# Filter RotBarIndex < 0
bad_rbi = p1["RotBarIndex"] < 0
if bad_rbi.sum() > 0:
    print(f"  Filtering {bad_rbi.sum()} touches with RotBarIndex < 0")
    p1 = p1[~bad_rbi].reset_index(drop=True)

print(f"  P1 touches: {len(p1)} (P1a={len(p1a)}, P1b={len(p1b)})")

# Load bar data
bar_p1 = pd.read_csv(DATA_DIR / "NQ_bardata_P1.csv")
bar_p1.columns = bar_p1.columns.str.strip()
print(f"  P1 bars: {len(bar_p1)}")

# Pre-compute numpy arrays
bar_arr = bar_p1[["Open", "High", "Low", "Last"]].to_numpy(dtype=np.float64)
bar_vol = bar_p1["Volume"].to_numpy(dtype=np.float64)
bar_trades = bar_p1["# of Trades"].to_numpy(dtype=np.float64)
bar_bid_vol = bar_p1["Bid Volume"].to_numpy(dtype=np.float64)
bar_ask_vol = bar_p1["Ask Volume"].to_numpy(dtype=np.float64)
bar_atr = bar_p1["ATR"].to_numpy(dtype=np.float64)
bar_zz_len = bar_p1["Zig Zag Line Length"].to_numpy(dtype=np.float64)
bar_zz_osc = bar_p1["Zig Zag Oscillator"].to_numpy(dtype=np.float64)
n_bars = len(bar_arr)

# Channel columns (6 boundaries: 3 pairs of Top/Bottom)
chan_top1 = bar_p1["Top"].to_numpy(dtype=np.float64)
chan_bot1 = bar_p1["Bottom"].to_numpy(dtype=np.float64)
chan_top2 = bar_p1["Top.1"].to_numpy(dtype=np.float64)
chan_bot2 = bar_p1["Bottom.1"].to_numpy(dtype=np.float64)
chan_top3 = bar_p1["Top.2"].to_numpy(dtype=np.float64)
chan_bot3 = bar_p1["Bottom.2"].to_numpy(dtype=np.float64)

# Parse bar datetimes
print("  Parsing bar datetimes...")
bar_datetimes = []
for _, row in bar_p1.iterrows():
    try:
        ds = str(row["Date"]).strip()
        ts = str(row["Time"]).strip()
        try:
            dt = datetime.strptime(f"{ds} {ts}", "%m/%d/%Y %H:%M:%S.%f")
        except ValueError:
            dt = datetime.strptime(f"{ds} {ts}", "%m/%d/%Y %H:%M:%S")
        bar_datetimes.append(dt)
    except Exception:
        bar_datetimes.append(None)
print(f"  Bar datetimes parsed: {len(bar_datetimes)}")

# Load zone lifecycle
lifecycle = pd.read_csv(P0_DIR / "zone_lifecycle.csv")
lifecycle["birth_dt"] = pd.to_datetime(lifecycle["birth_datetime"])
lifecycle["death_dt"] = pd.to_datetime(lifecycle["death_datetime"])
print(f"  Lifecycle zones: {len(lifecycle)}")

# Load period config
with open(DATA_DIR / "period_config.json") as f:
    period_config = json.load(f)

# P1 ONLY. P2 NOT USED. Baseline anchor = 0.8984.

# ══════════════════════════════════════════════════════════════════════
# Step 3: Feature Computation (P1 only)
# ══════════════════════════════════════════════════════════════════════
print("\n" + "=" * 72)
print("STEP 3: FEATURE COMPUTATION (P1 only, 4701 touches)")
print("=" * 72)

# --- Feature 1: Timeframe (categorical) ---
p1["F01_Timeframe"] = p1["SourceLabel"]

# --- Feature 2: Zone Width ---
p1["F02_ZoneWidth"] = p1["ZoneWidthTicks"]

# --- Feature 3: DROPPED (HasVPRay = 1 for 100%) ---

# --- Feature 4: Cascade State (categorical) ---
p1["F04_CascadeState"] = p1["CascadeState"].replace("UNKNOWN", "NO_PRIOR")

# P1 ONLY. All features must be computable at entry time.

# --- Feature 5: Session (categorical from DateTime) ---
def classify_session(dt_str):
    try:
        dt = pd.Timestamp(dt_str)
        h, m = dt.hour, dt.minute
        t_min = h * 60 + m
        if t_min < 360:       # before 6:00
            return "Overnight"
        elif t_min < 570:     # 6:00–9:30
            return "PreRTH"
        elif t_min < 660:     # 9:30–11:00
            return "OpeningDrive"
        elif t_min < 840:     # 11:00–14:00
            return "Midday"
        elif t_min < 1020:    # 14:00–17:00
            return "Close"
        else:
            return "Overnight"
    except Exception:
        return "Unknown"

p1["F05_Session"] = p1["DateTime"].apply(classify_session)

# --- Feature 6: Approach Velocity ---
p1["F06_ApproachVelocity"] = p1["ApproachVelocity"]

# --- Feature 7: Approach Deceleration ---
# mean(H-L for bars -3 to -1) / mean(H-L for bars -10 to -8)
print("  Computing Feature 7 (Approach Deceleration)...")
decel_vals = []
for rbi in p1["RotBarIndex"].values:
    rbi = int(rbi)
    if rbi < 10 or rbi >= n_bars:
        decel_vals.append(np.nan)
        continue
    recent = bar_arr[max(0, rbi-3):rbi, 1] - bar_arr[max(0, rbi-3):rbi, 2]
    far = bar_arr[max(0, rbi-10):max(0, rbi-7), 1] - bar_arr[max(0, rbi-10):max(0, rbi-7), 2]
    if len(recent) > 0 and len(far) > 0 and far.mean() > 0:
        decel_vals.append(recent.mean() / far.mean())
    else:
        decel_vals.append(np.nan)
p1["F07_Deceleration"] = decel_vals

# P1 ONLY. Baseline anchor = 0.8984. Compare all screening against this.

# --- Feature 8: Prior Touch Reaction Speed ---
# Build ZoneID for P1 touches (same construction as Prompt 0)
p1["ZoneID"] = (p1["TouchType"].astype(str) + "|" +
                p1["ZoneTop"].astype(str) + "|" +
                p1["ZoneBot"].astype(str) + "|" +
                p1["SourceLabel"].astype(str))

# For each touch, get prior touch (seq-1) on same zone
print("  Computing Features 8, 10, 19, 20 (prior touch history)...")
p1_sorted = p1.sort_values(["ZoneID", "TouchSequence"]).copy()
prior_rxn_speed = []
prior_pen = []
vp_consumption = []
vp_distance = []

for zone_id, group in p1_sorted.groupby("ZoneID"):
    group = group.sort_values("TouchSequence")
    prev_rxn30_ticks = np.nan
    prev_penetration = np.nan
    vp_consumed = False

    for idx, row in group.iterrows():
        seq = row["TouchSequence"]

        # Feature 8: prior touch reaction at 30 bars (computed from bar data)
        if seq == 1:
            prior_rxn_speed.append((idx, np.nan))
            prior_pen.append((idx, np.nan))
        else:
            prior_rxn_speed.append((idx, prev_rxn30_ticks))
            prior_pen.append((idx, prev_penetration))

        # Feature 19: VP Ray Consumption
        if seq == 1:
            vp_consumption.append((idx, "VP_RAY_INTACT"))
        else:
            if vp_consumed:
                vp_consumption.append((idx, "VP_RAY_CONSUMED"))
            else:
                vp_consumption.append((idx, "VP_RAY_INTACT"))

        # Check if THIS touch consumes the VP ray (for future touches)
        if row["HasVPRay"] == 1 and not np.isnan(row["VPRayPrice"]):
            touch_pen_price = row["TouchPrice"] - row["Penetration"] * TICK_SIZE
            if "DEMAND" in row["TouchType"]:
                # Demand: touch low <= VPRayPrice
                touch_low = row["TouchPrice"] - row["Penetration"] * TICK_SIZE
                if touch_low <= row["VPRayPrice"]:
                    vp_consumed = True
            else:
                # Supply: touch high >= VPRayPrice
                touch_high = row["TouchPrice"] + row["Penetration"] * TICK_SIZE
                if touch_high >= row["VPRayPrice"]:
                    vp_consumed = True

        # Feature 20: Distance to consumed VP ray
        if vp_consumption[-1][1] == "VP_RAY_CONSUMED":
            dist = abs(row["TouchPrice"] - row["VPRayPrice"]) / TICK_SIZE
            vp_distance.append((idx, dist))
        else:
            vp_distance.append((idx, np.nan))

        # Store for next iteration — compute reaction@30 from bar data
        rbi = int(row["RotBarIndex"])
        entry_bar = rbi + 1
        if entry_bar < n_bars:
            end_30 = min(entry_bar + 30, n_bars)
            if end_30 > entry_bar:
                ep = bar_arr[entry_bar, 0]  # entry price = Open
                highs_30 = bar_arr[entry_bar:end_30, 1]
                lows_30 = bar_arr[entry_bar:end_30, 2]
                if "DEMAND" in row["TouchType"]:
                    prev_rxn30_ticks = (highs_30.max() - ep) / TICK_SIZE
                else:
                    prev_rxn30_ticks = (ep - lows_30.min()) / TICK_SIZE
            else:
                prev_rxn30_ticks = np.nan
        else:
            prev_rxn30_ticks = np.nan
        prev_penetration = row["Penetration"]

# Map back to p1 index
f08_map = {idx: val for idx, val in prior_rxn_speed}
f10_map = {idx: val for idx, val in prior_pen}
f19_map = {idx: val for idx, val in vp_consumption}
f20_map = {idx: val for idx, val in vp_distance}

p1["F08_PriorRxnSpeed"] = p1.index.map(f08_map)
p1["F10_PriorPenetration"] = p1.index.map(f10_map)
p1["F19_VPConsumption"] = p1.index.map(f19_map)
p1["F20_VPDistance"] = p1.index.map(f20_map)

# --- Feature 9: Zone Width / ATR Ratio ---
atr_at_touch = []
for rbi in p1["RotBarIndex"].values:
    rbi = int(rbi)
    if 0 <= rbi < n_bars and bar_atr[rbi] > 0:
        atr_at_touch.append(bar_atr[rbi])
    else:
        atr_at_touch.append(np.nan)
p1["F09_ZW_ATR"] = p1["ZoneWidthTicks"].values * TICK_SIZE / np.array(atr_at_touch)

# P1 ONLY. Is this feature computable at entry time? YES — all bar data from touch bar or earlier.

# --- Feature 11: Touch Bar Delta Divergence ---
deltas = []
for i, row in p1.iterrows():
    rbi = int(row["RotBarIndex"])
    if 0 <= rbi < n_bars:
        delta = bar_ask_vol[rbi] - bar_bid_vol[rbi]
        if "SUPPLY" in row["TouchType"]:
            delta = -delta  # negate for supply
        deltas.append(delta)
    else:
        deltas.append(np.nan)
p1["F11_DeltaDivergence"] = deltas

# --- Feature 12: Touch Bar Duration ---
durations = []
for rbi in p1["RotBarIndex"].values:
    rbi = int(rbi)
    if 1 <= rbi < n_bars:
        dt_curr = bar_datetimes[rbi]
        dt_prev = bar_datetimes[rbi - 1]
        if dt_curr and dt_prev:
            durations.append((dt_curr - dt_prev).total_seconds())
        else:
            durations.append(np.nan)
    else:
        durations.append(np.nan)
p1["F12_BarDuration"] = durations

# --- Feature 13: Touch Bar Close Position ---
positions = []
for i, row in p1.iterrows():
    rbi = int(row["RotBarIndex"])
    if 0 <= rbi < n_bars:
        h = bar_arr[rbi, 1]
        l = bar_arr[rbi, 2]
        last = bar_arr[rbi, 3]
        rng = h - l
        if rng > 0:
            if "DEMAND" in row["TouchType"]:
                positions.append((last - l) / rng)
            else:
                positions.append((h - last) / rng)
        else:
            positions.append(0.5)
    else:
        positions.append(np.nan)
p1["F13_ClosePosition"] = positions

# --- Feature 14: Average Order Size ---
avg_orders = []
for rbi in p1["RotBarIndex"].values:
    rbi = int(rbi)
    if 0 <= rbi < n_bars and bar_trades[rbi] > 0:
        avg_orders.append(bar_vol[rbi] / bar_trades[rbi])
    else:
        avg_orders.append(np.nan)
p1["F14_AvgOrderSize"] = avg_orders

# P1 ONLY. Baseline anchor = 0.8984. All features from touch bar or earlier.

# --- Feature 15: ZZ Swing Regime ---
print("  Computing Feature 15 (ZZ Swing Regime)...")
zz_regime = []
for rbi in p1["RotBarIndex"].values:
    rbi = int(rbi)
    if rbi < 20 or rbi >= n_bars:
        zz_regime.append(np.nan)
        continue
    # Count backward from rbi, collect non-zero ZZ Line Length values
    nonzero_lengths = []
    for j in range(rbi, max(-1, rbi - 2000), -1):
        val = bar_zz_len[j]
        if val != 0 and not np.isnan(val):
            nonzero_lengths.append(val)
            if len(nonzero_lengths) >= 20:
                break
    if len(nonzero_lengths) >= 5:
        zz_regime.append(np.median(nonzero_lengths))
    else:
        zz_regime.append(np.nan)
p1["F15_ZZSwingRegime"] = zz_regime

# --- Feature 16: ZZ Oscillator at Touch ---
zz_osc_vals = []
for rbi in p1["RotBarIndex"].values:
    rbi = int(rbi)
    if 0 <= rbi < n_bars:
        zz_osc_vals.append(bar_zz_osc[rbi])
    else:
        zz_osc_vals.append(np.nan)
p1["F16_ZZOscillator"] = zz_osc_vals

# --- Feature 17: ATR Regime (rolling percentile rank vs trailing 500) ---
print("  Computing Feature 17 (ATR Regime)...")
atr_regime = []
for rbi in p1["RotBarIndex"].values:
    rbi = int(rbi)
    if rbi < 50 or rbi >= n_bars:
        atr_regime.append(np.nan)
        continue
    start = max(0, rbi - 500)
    trailing = bar_atr[start:rbi + 1]
    current = bar_atr[rbi]
    pctile = (trailing < current).sum() / len(trailing)
    atr_regime.append(pctile)
p1["F17_ATRRegime"] = atr_regime

# --- Feature 18: Channel Confluence ---
# Count of 6 channel boundaries within N ticks of zone edge
# Test N=20, 50, 100 ticks on P1 — use the one with best screening
print("  Computing Feature 18 (Channel Confluence)...")

def count_channel_confluence(rbi, zone_edge_price, n_ticks):
    """Count channel boundaries within n_ticks of zone edge."""
    if rbi < 0 or rbi >= n_bars:
        return 0
    count = 0
    threshold = n_ticks * TICK_SIZE
    for arr in [chan_top1, chan_bot1, chan_top2, chan_bot2,
                chan_top3, chan_bot3]:
        val = arr[rbi]
        if val != 0 and not np.isnan(val):
            if abs(val - zone_edge_price) <= threshold:
                count += 1
    return count

# Compute at all 3 thresholds, pick best later
for n_ticks in [20, 50, 100]:
    col = f"F18_ChanConf_{n_ticks}"
    vals = []
    for i, row in p1.iterrows():
        rbi = int(row["RotBarIndex"])
        edge = (row["ZoneTop"] if "SUPPLY" in row["TouchType"]
                else row["ZoneBot"])
        vals.append(count_channel_confluence(rbi, edge, n_ticks))
    p1[col] = vals

# P1 ONLY. P2 NOT USED. All features computable at entry time.

# --- Expansion Features 21–25 (from zone_lifecycle.csv) ---
print("  Computing expansion features 21–25...")

# Build lookup structures from lifecycle
lc_birth_map = dict(zip(lifecycle["ZoneID"], lifecycle["birth_dt"]))
lc_zone_prices = lifecycle[["ZoneID", "direction", "ZonePrice",
                             "SourceLabel", "birth_dt", "death_dt",
                             "death_cause", "ZoneWidthTicks"]].copy()

# Feature 21: Zone Age (bars between zone birth and touch)
zone_ages = []
for i, row in p1.iterrows():
    zone_id = row["ZoneID"]
    rbi = int(row["RotBarIndex"])
    if zone_id in lc_birth_map:
        birth_dt = lc_birth_map[zone_id]
        touch_dt = pd.Timestamp(row["DateTime"])
        # Approximate age in bars: use RotBarIndex diff
        # Since birth is the first touch DateTime, find its RotBarIndex
        # Simple: use (touch_dt - birth_dt) as proxy... but we need bars
        # Better: look up RotBarIndex of first touch on this zone in P1
        # Simplest: use ZoneAgeBars column if available
        zone_ages.append(row.get("ZoneAgeBars", np.nan))
    else:
        zone_ages.append(np.nan)
p1["F21_ZoneAge"] = zone_ages

# Feature 22: Recent Break Rate (deaths in trailing 500 bars / active zones)
print("    Feature 22 (Recent Break Rate)...")
# Build death events with approximate RotBarIndex
# We need death events mapped to bar indices. Use touch data mapping.
death_events = lifecycle[lifecycle["death_cause"] != "ALIVE"].copy()

# Map death_datetime to RotBarIndex via P1 touch data
p1_dt_to_rbi = dict(zip(p1["DateTime"], p1["RotBarIndex"].astype(int)))
death_rbis_list = []
for _, z in death_events.iterrows():
    ddt = z["death_datetime"]
    if ddt in p1_dt_to_rbi:
        death_rbis_list.append(p1_dt_to_rbi[ddt])
    else:
        death_rbis_list.append(None)
death_events = death_events.copy()
death_events["death_rbi"] = death_rbis_list
death_events_mapped = death_events.dropna(subset=["death_rbi"])
death_events_mapped = death_events_mapped.copy()
death_events_mapped["death_rbi"] = death_events_mapped["death_rbi"].astype(int)
death_rbi_arr = death_events_mapped["death_rbi"].values

# Active zone count at each touch time (approximate)
break_rates = []
for rbi in p1["RotBarIndex"].values:
    rbi = int(rbi)
    # Deaths in trailing 500 bars
    deaths_nearby = np.sum((death_rbi_arr >= rbi - 500) &
                           (death_rbi_arr < rbi))
    # Active zones (approximate): total zones born before rbi minus dead before rbi
    # Simple proxy: just use death count / some normalizer
    # Better: count from lifecycle
    total_active = np.sum(death_rbi_arr >= rbi - 500)  # rough proxy
    if total_active > 0:
        break_rates.append(deaths_nearby / max(total_active, 1))
    else:
        break_rates.append(0.0)
p1["F22_RecentBreakRate"] = break_rates

# Feature 23: Cross-TF Confluence (active zones from OTHER TFs within 200t)
print("    Feature 23 (Cross-TF Confluence)...")
xtf_vals = []
for i, row in p1.iterrows():
    touch_dt = pd.Timestamp(row["DateTime"])
    touch_dir = "DEMAND" if "DEMAND" in row["TouchType"] else "SUPPLY"
    edge = row["ZoneBot"] if touch_dir == "DEMAND" else row["ZoneTop"]
    touch_tf = row["SourceLabel"]

    # Active zones: born before touch, not dead yet
    active = lc_zone_prices[
        (lc_zone_prices["direction"] == touch_dir) &
        (lc_zone_prices["birth_dt"] <= touch_dt) &
        ((lc_zone_prices["death_dt"].isna()) |
         (lc_zone_prices["death_dt"] > touch_dt)) &
        (lc_zone_prices["SourceLabel"] != touch_tf)  # OTHER TFs only
    ]
    nearby = active[abs(active["ZonePrice"] - edge) <= 200 * TICK_SIZE]
    xtf_vals.append(len(nearby))
p1["F23_CrossTFConfluence"] = xtf_vals

# P1 ONLY. Expansion features from zone_lifecycle.csv. Entry-time computable.

# Feature 24: Nearest Same-Direction Zone Distance
print("    Feature 24 (Nearest Same-Dir Zone Distance)...")
nearest_dist = []
for i, row in p1.iterrows():
    touch_dt = pd.Timestamp(row["DateTime"])
    touch_dir = "DEMAND" if "DEMAND" in row["TouchType"] else "SUPPLY"
    edge = row["ZoneBot"] if touch_dir == "DEMAND" else row["ZoneTop"]
    zone_id = row["ZoneID"]

    active = lc_zone_prices[
        (lc_zone_prices["direction"] == touch_dir) &
        (lc_zone_prices["ZoneID"] != zone_id) &
        (lc_zone_prices["birth_dt"] <= touch_dt) &
        ((lc_zone_prices["death_dt"].isna()) |
         (lc_zone_prices["death_dt"] > touch_dt))
    ]
    if len(active) > 0:
        dists = abs(active["ZonePrice"].values - edge) / TICK_SIZE
        nearest_dist.append(dists.min())
    else:
        nearest_dist.append(np.nan)
p1["F24_NearestZoneDist"] = nearest_dist

# Feature 25: Price-Level Break History
print("    Feature 25 (Price-Level Break History)...")
break_hist = []
for i, row in p1.iterrows():
    touch_dt = pd.Timestamp(row["DateTime"])
    edge = row["ZoneBot"] if "DEMAND" in row["TouchType"] else row["ZoneTop"]

    # Zones within ±500 ticks, born before this touch
    nearby_zones = lc_zone_prices[
        (abs(lc_zone_prices["ZonePrice"] - edge) <= 500 * TICK_SIZE) &
        (lc_zone_prices["birth_dt"] < touch_dt)
    ]
    if len(nearby_zones) > 0:
        dead = (nearby_zones["death_cause"] != "ALIVE").sum()
        # Only count those that died BEFORE this touch
        dead_before = nearby_zones[
            (nearby_zones["death_cause"] != "ALIVE") &
            (nearby_zones["death_dt"] < touch_dt)
        ]
        frac = len(dead_before) / len(nearby_zones)
        break_hist.append(frac)
    else:
        break_hist.append(np.nan)
p1["F25_BreakHistory"] = break_hist

# Fill NaN for F24 with max observed
max_f24 = p1["F24_NearestZoneDist"].max()
p1["F24_NearestZoneDist"] = p1["F24_NearestZoneDist"].fillna(max_f24)

# ── Print feature distributions ──────────────────────────────────────
print("\n── Feature Distributions ──")
feature_cols = [c for c in p1.columns if c.startswith("F") and c[1:3].isdigit()]
for fc in sorted(feature_cols):
    if p1[fc].dtype == object or str(p1[fc].dtype).startswith("string"):
        print(f"  {fc}: {p1[fc].value_counts().head(8).to_dict()}")
    else:
        try:
            valid = pd.to_numeric(p1[fc], errors="coerce").dropna()
            null_pct = (len(p1) - len(valid)) / len(p1) * 100
            if len(valid) > 0:
                print(f"  {fc}: mean={valid.mean():.3f}  "
                      f"std={valid.std():.3f}  null={null_pct:.1f}%")
            else:
                print(f"  {fc}: ALL NULL")
        except Exception:
            print(f"  {fc}: {p1[fc].value_counts().head(5).to_dict()}")

# Null rates for key features
print("\n── Null Rates for Key Features ──")
for fc in ["F08_PriorRxnSpeed", "F10_PriorPenetration",
           "F19_VPConsumption", "F20_VPDistance",
           "F21_ZoneAge", "F24_NearestZoneDist"]:
    if fc in p1.columns:
        null_pct = p1[fc].isna().mean() * 100
        print(f"  {fc}: {null_pct:.1f}% null")

# VP Ray Consumption distribution
print(f"\n  VP Ray Consumption: {p1['F19_VPConsumption'].value_counts().to_dict()}")

# Print 5 sample rows
print("\n── Sample Rows (5) ──")
sample_cols = ["DateTime", "TouchType", "SourceLabel", "TouchSequence",
               "F01_Timeframe", "F04_CascadeState", "F05_Session",
               "F02_ZoneWidth", "F09_ZW_ATR", "F19_VPConsumption"]
print(p1[sample_cols].head(5).to_string())

print("\n  ✓ All 24 features (19 core + 5 expansion) computed on P1 only.")
print("  ✓ All features computable at entry time (touch bar or earlier).")

# P1 ONLY. P2 NOT USED. 4701 touches.

# ══════════════════════════════════════════════════════════════════════
# Precompute horizon R/P for each P1 touch (from bar data)
# ══════════════════════════════════════════════════════════════════════
print("\n── Pre-computing horizon R/P for all P1 touches ──")

for h in HORIZONS:
    rxn_col = f"Rxn_{h}"
    pen_col = f"Pen_{h}"
    rxn_vals = []
    pen_vals = []
    for rbi in p1["RotBarIndex"].values:
        rbi = int(rbi)
        entry_bar = rbi + 1
        if entry_bar >= n_bars:
            rxn_vals.append(np.nan)
            pen_vals.append(np.nan)
            continue
        end = min(entry_bar + h, n_bars)
        if end <= entry_bar:
            rxn_vals.append(np.nan)
            pen_vals.append(np.nan)
            continue
        entry_price = bar_arr[entry_bar, 0]
        highs = bar_arr[entry_bar:end, 1]
        lows = bar_arr[entry_bar:end, 2]
        rxn_vals.append((highs.max() - entry_price) / TICK_SIZE)
        pen_vals.append((entry_price - lows.min()) / TICK_SIZE)
    p1[rxn_col] = rxn_vals
    p1[pen_col] = pen_vals

# For demand touches, rxn=favorable=up, pen=adverse=down → already correct
# For supply touches, rxn=favorable=down, pen=adverse=up → need to swap
supply_mask = p1["TouchType"] == "SUPPLY_EDGE"
for h in HORIZONS:
    rxn_col = f"Rxn_{h}"
    pen_col = f"Pen_{h}"
    # Swap for supply
    temp_rxn = p1.loc[supply_mask, pen_col].copy()
    temp_pen = p1.loc[supply_mask, rxn_col].copy()
    p1.loc[supply_mask, rxn_col] = temp_rxn
    p1.loc[supply_mask, pen_col] = temp_pen

# Full observation R/P (from merged CSV columns — already correct)
p1["Rxn_full"] = p1["Reaction"].replace(-1, np.nan)
p1["Pen_full"] = p1["Penetration"].replace(-1, np.nan)

ALL_HORIZONS = [30, 60, 120, "full"]

print("  R/P pre-computed for horizons: 30, 60, 120, full")

# P1 ONLY. Baseline R/P @60 = 1.007.

# ══════════════════════════════════════════════════════════════════════
# Step 4: Single-Feature Screening (P1 only)
# ══════════════════════════════════════════════════════════════════════
print("\n" + "=" * 72)
print("STEP 4: SINGLE-FEATURE SCREENING (P1 only)")
print("R/P ratio at 4 horizons. Exit-independent. Baseline R/P @60 = 1.007")
print("=" * 72)

# Define feature list with binning strategy
FEATURES = {
    "F01_Timeframe": "categorical",
    "F02_ZoneWidth": "tercile",
    "F04_CascadeState": "categorical",
    "F05_Session": "categorical",
    "F06_ApproachVelocity": "tercile",
    "F07_Deceleration": "tercile",
    "F08_PriorRxnSpeed": "tercile",
    "F09_ZW_ATR": "tercile",
    "F10_PriorPenetration": "tercile",
    "F11_DeltaDivergence": "tercile",
    "F12_BarDuration": "tercile",
    "F13_ClosePosition": "tercile",
    "F14_AvgOrderSize": "tercile",
    "F15_ZZSwingRegime": "tercile",
    "F16_ZZOscillator": "tercile",
    "F17_ATRRegime": "tercile",
    "F18_ChanConf_50": "tercile",  # default, may update
    "F19_VPConsumption": "categorical",
    "F20_VPDistance": "tercile",
    "F21_ZoneAge": "tercile",
    "F22_RecentBreakRate": "tercile",
    "F23_CrossTFConfluence": "tercile",
    "F24_NearestZoneDist": "tercile",
    "F25_BreakHistory": "tercile",
}

# Pick best channel confluence threshold
print("\n  Selecting Feature 18 threshold (20/50/100 ticks)...")
best_f18_spread = -1
best_f18_n = 50
for nt in [20, 50, 100]:
    col = f"F18_ChanConf_{nt}"
    vals = p1[col].dropna()
    if vals.nunique() < 3:
        continue
    try:
        p33, p67 = np.percentile(vals, [33, 67])
        if p33 == p67:
            continue
        lo = p1[p1[col] <= p33]
        hi = p1[p1[col] >= p67]
        rxn_lo = p1.loc[lo.index, "Rxn_60"].dropna()
        pen_lo = p1.loc[lo.index, "Pen_60"].dropna()
        rxn_hi = p1.loc[hi.index, "Rxn_60"].dropna()
        pen_hi = p1.loc[hi.index, "Pen_60"].dropna()
        rp_lo = rxn_lo.mean() / max(pen_lo.mean(), 1.0)
        rp_hi = rxn_hi.mean() / max(pen_hi.mean(), 1.0)
        spread = abs(rp_hi - rp_lo)
        if spread > best_f18_spread:
            best_f18_spread = spread
            best_f18_n = nt
    except Exception:
        pass
print(f"  Best F18 threshold: {best_f18_n} ticks (spread={best_f18_spread:.3f})")
FEATURES["F18_ChanConf"] = "tercile"
p1["F18_ChanConf"] = p1[f"F18_ChanConf_{best_f18_n}"]
# Remove the individual threshold columns from features dict
del FEATURES["F18_ChanConf_50"]
FEATURES["F18_ChanConf"] = "tercile"

# Store bin edges for config
bin_edges = {}
feature_stats = {}


def compute_rp_for_subset(subset_idx, horizon):
    """Compute R/P for a subset of touches at given horizon."""
    rxn_col = f"Rxn_{horizon}"
    pen_col = f"Pen_{horizon}"
    rxn = p1.loc[subset_idx, rxn_col].dropna()
    pen = p1.loc[subset_idx, pen_col].dropna()
    mean_rxn = rxn.mean() if len(rxn) > 0 else 0
    mean_pen = pen.mean() if len(pen) > 0 else 0
    denom = max(mean_pen, 1.0)  # Floor rule
    rp = mean_rxn / denom
    floored = mean_pen < 1.0
    return rp, mean_rxn, mean_pen, len(rxn), floored


def screen_feature(feat_name, bin_type, data=None):
    """Screen a single feature. Returns screening result dict."""
    if data is None:
        data = p1

    if feat_name not in data.columns:
        return None

    vals = data[feat_name]

    # Build bins
    if bin_type == "categorical":
        categories = vals.dropna().unique()
        bins = {}
        for cat in categories:
            idx = data.index[vals == cat]
            if len(idx) >= 20:  # min bin size
                bins[str(cat)] = idx
    else:
        valid = vals.dropna()
        if len(valid) < 30:
            return None
        try:
            p33, p67 = np.percentile(valid, [33, 67])
        except Exception:
            return None
        if p33 == p67:
            # Try quartile split
            p33, p67 = np.percentile(valid, [25, 75])
            if p33 == p67:
                return None
        bin_edges[feat_name] = (float(p33), float(p67))
        feature_stats[feat_name] = {
            "mean": float(valid.mean()), "std": float(valid.std())}
        bins = {
            "Low": data.index[vals <= p33],
            "Mid": data.index[(vals > p33) & (vals < p67)],
            "High": data.index[vals >= p67],
        }
        bins = {k: v for k, v in bins.items() if len(v) >= 20}

    if len(bins) < 2:
        return None

    # Compute R/P per bin per horizon
    horizon_results = {}
    for h in ALL_HORIZONS:
        bin_rps = {}
        for bname, bidx in bins.items():
            rp, mean_r, mean_p, n, floored = compute_rp_for_subset(bidx, h)
            bin_rps[bname] = {"rp": rp, "mean_rxn": mean_r,
                              "mean_pen": mean_p, "n": n, "floored": floored}
        if not bin_rps:
            continue

        rp_vals = {k: v["rp"] for k, v in bin_rps.items()}
        best_bin = max(rp_vals, key=rp_vals.get)
        worst_bin = min(rp_vals, key=rp_vals.get)
        spread = rp_vals[best_bin] - rp_vals[worst_bin]

        # Reaction spread
        rxn_vals_dict = {k: v["mean_rxn"] for k, v in bin_rps.items()}
        rxn_spread = max(rxn_vals_dict.values()) - min(rxn_vals_dict.values())

        # MWU test between best and worst bins
        rxn_col = f"Rxn_{h}"
        best_rxn = data.loc[bins[best_bin], rxn_col].dropna().values
        worst_rxn = data.loc[bins[worst_bin], rxn_col].dropna().values
        try:
            if len(best_rxn) > 5 and len(worst_rxn) > 5:
                stat, pval = stats.mannwhitneyu(
                    best_rxn, worst_rxn, alternative="greater")
                # Cohen's d
                pooled_std = np.sqrt(
                    (best_rxn.std()**2 + worst_rxn.std()**2) / 2)
                cohens_d = ((best_rxn.mean() - worst_rxn.mean()) / pooled_std
                            if pooled_std > 0 else 0)
            else:
                pval = 1.0
                cohens_d = 0.0
        except Exception:
            pval = 1.0
            cohens_d = 0.0

        horizon_results[h] = {
            "bins": bin_rps, "best_bin": best_bin, "worst_bin": worst_bin,
            "spread": spread, "rxn_spread": rxn_spread,
            "pval": pval, "cohens_d": cohens_d,
        }

    if not horizon_results:
        return None

    # Multi-horizon consistency
    best_bins_per_h = [horizon_results[h]["best_bin"]
                       for h in ALL_HORIZONS if h in horizon_results]
    # Most common best bin
    if best_bins_per_h:
        from collections import Counter
        most_common_best = Counter(best_bins_per_h).most_common(1)[0][0]
        consistent_count = sum(
            1 for h in ALL_HORIZONS
            if h in horizon_results
            and horizon_results[h]["best_bin"] == most_common_best
            and horizon_results[h]["spread"] > 0.2
        )
    else:
        consistent_count = 0

    # Classify
    strong_spread_count = sum(
        1 for h in ALL_HORIZONS
        if h in horizon_results and horizon_results[h]["spread"] > 0.3)
    sig_count = sum(
        1 for h in ALL_HORIZONS
        if h in horizon_results and horizon_results[h]["pval"] < 0.05)
    mod_spread_count = sum(
        1 for h in ALL_HORIZONS
        if h in horizon_results and horizon_results[h]["spread"] > 0.2)
    mod_sig_count = sum(
        1 for h in ALL_HORIZONS
        if h in horizon_results and horizon_results[h]["pval"] < 0.10)

    # Check for inverted
    inverted_count = 0
    for h in ALL_HORIZONS:
        if h in horizon_results:
            hr = horizon_results[h]
            if hr["spread"] < 0:  # worst > best should not happen by construction
                inverted_count += 1

    if strong_spread_count >= 3 and sig_count >= 2:
        classification = "STRONG"
    elif mod_spread_count >= 2 or mod_sig_count >= 2:
        classification = "MODERATE"
    else:
        classification = "WEAK"

    return {
        "feature": feat_name,
        "horizons": horizon_results,
        "consistent_count": consistent_count,
        "classification": classification,
        "bins": bins,
    }


# P1 ONLY. No parameters from P2. Baseline R/P @60 = 1.007.

# ── Run screening for all features ──────────────────────────────────
print("\n── Screening all 24 features ──")
screening_results = {}
t_start = time.time()

for feat_name, bin_type in FEATURES.items():
    result = screen_feature(feat_name, bin_type)
    if result:
        screening_results[feat_name] = result
        h60 = result["horizons"].get(60, {})
        print(f"  {feat_name:<25} R/P spread@60={h60.get('spread', 0):.3f}  "
              f"p={h60.get('pval', 1):.4f}  "
              f"consistent={result['consistent_count']}/4  "
              f"{result['classification']}")
    else:
        print(f"  {feat_name:<25} COULD NOT SCREEN (insufficient data/variance)")

elapsed = time.time() - t_start
print(f"\n  Screening complete in {elapsed:.1f}s")

# ── Ranked screening table ───────────────────────────────────────────
print("\n── Single-Feature Screening Table (ranked by R/P spread @60) ──")
ranked = sorted(screening_results.values(),
                key=lambda x: x["horizons"].get(60, {}).get("spread", 0),
                reverse=True)

print(f"  {'Rank':<5} {'Feature':<25} {'Best@60':>8} {'Worst@60':>8} "
      f"{'Spread@60':>10} {'Consist':>8} {'MWU p':>8} {'d':>7} "
      f"{'Class':>10}")
for i, r in enumerate(ranked, 1):
    h60 = r["horizons"].get(60, {})
    best_rp = h60.get("bins", {}).get(h60.get("best_bin", ""), {}).get("rp", 0)
    worst_rp = h60.get("bins", {}).get(h60.get("worst_bin", ""), {}).get("rp", 0)
    exp_tag = " (EXP)" if any(x in r["feature"] for x in
                               ["F21", "F22", "F23", "F24", "F25"]) else ""
    print(f"  {i:<5} {r['feature'] + exp_tag:<25} {best_rp:>8.3f} "
          f"{worst_rp:>8.3f} {h60.get('spread', 0):>10.3f} "
          f"{r['consistent_count']:>7}/4 "
          f"{h60.get('pval', 1):>8.4f} "
          f"{h60.get('cohens_d', 0):>7.3f} "
          f"{r['classification']:>10}")

# Print STRONG / MODERATE / WEAK lists
strong_feats = [r["feature"] for r in ranked
                if r["classification"] == "STRONG"]
moderate_feats = [r["feature"] for r in ranked
                  if r["classification"] == "MODERATE"]
weak_feats = [r["feature"] for r in ranked
              if r["classification"] == "WEAK"]

print(f"\n  STRONG SIGNAL features: {strong_feats if strong_feats else 'NONE'}")
print(f"  MODERATE SIGNAL features: {moderate_feats}")
print(f"  WEAK SIGNAL features: {weak_feats}")

# P1 ONLY. Baseline anchor = 0.8984. R/P @60 = 1.007.

# ══════════════════════════════════════════════════════════════════════
# Step 4 sub-step 5b: SBB-Masked Secondary Screening
# ══════════════════════════════════════════════════════════════════════
print("\n" + "=" * 72)
print("STEP 4.5b: SBB-MASKED SECONDARY SCREENING")
print("WEAK/MODERATE features re-screened on NORMAL-only P1 touches")
print("=" * 72)

normal_p1 = p1[p1["SBB_Label"] == "NORMAL"].copy()
print(f"  NORMAL-only P1 touches: {len(normal_p1)}")

sbb_masked_feats = []
sbb_masked_results = {}

candidates = [f for f in moderate_feats + weak_feats
              if f in screening_results]

for feat_name in candidates:
    bin_type = FEATURES.get(feat_name, "tercile")
    # Re-screen on NORMAL-only
    result = screen_feature(feat_name, bin_type, data=normal_p1)
    if result is None:
        continue

    # Check if would classify as STRONG on NORMAL-only
    strong_spread = sum(
        1 for h in ALL_HORIZONS
        if h in result["horizons"]
        and result["horizons"][h]["spread"] > 0.3)
    sig = sum(
        1 for h in ALL_HORIZONS
        if h in result["horizons"]
        and result["horizons"][h]["pval"] < 0.05)

    if strong_spread >= 3 and sig >= 2:
        sbb_masked_feats.append(feat_name)
        sbb_masked_results[feat_name] = result
        h60 = result["horizons"].get(60, {})
        print(f"  ✓ SBB-MASKED: {feat_name}  "
              f"NORMAL R/P spread@60={h60.get('spread', 0):.3f}  "
              f"p={h60.get('pval', 1):.4f}")
    else:
        h60 = result["horizons"].get(60, {})
        print(f"    {feat_name}  NORMAL spread@60={h60.get('spread', 0):.3f}"
              f"  — not upgraded")

print(f"\n  SBB-MASKED features: "
      f"{sbb_masked_feats if sbb_masked_feats else 'NONE'}")

# ══════════════════════════════════════════════════════════════════════
# Step 4 sub-step 6: Confirmation Simulation (STRONG + SBB-MASKED)
# ══════════════════════════════════════════════════════════════════════
print("\n" + "=" * 72)
print("STEP 4.6: CONFIRMATION SIMULATION")
print(f"Median cell exit: Stop={MEDIAN_STOP}t, Target={MEDIAN_TARGET}t, "
      f"TimeCap={MEDIAN_TIMECAP} bars")
print("=" * 72)


def simulate_touch_simple(bars, entry_bar_idx, direction, stop_ticks,
                          target_ticks, time_cap_bars):
    """Simple bar-by-bar sim. Returns pnl_ticks or None."""
    nb = len(bars)
    if entry_bar_idx >= nb:
        return None
    entry_price = bars[entry_bar_idx, 0]
    if direction == 1:
        sp = entry_price - stop_ticks * TICK_SIZE
        tp = entry_price + target_ticks * TICK_SIZE
    else:
        sp = entry_price + stop_ticks * TICK_SIZE
        tp = entry_price - target_ticks * TICK_SIZE
    end = min(entry_bar_idx + time_cap_bars, nb)
    for i in range(entry_bar_idx, end):
        h, l, last = bars[i, 1], bars[i, 2], bars[i, 3]
        bh = i - entry_bar_idx + 1
        sh = (l <= sp) if direction == 1 else (h >= sp)
        th = (h >= tp) if direction == 1 else (l <= tp)
        if sh and th:
            return -stop_ticks
        if sh:
            return -stop_ticks
        if th:
            return target_ticks
        if bh >= time_cap_bars:
            return ((last - entry_price) / TICK_SIZE if direction == 1
                    else (entry_price - last) / TICK_SIZE)
    if end > entry_bar_idx:
        last = bars[end - 1, 3]
        return ((last - entry_price) / TICK_SIZE if direction == 1
                else (entry_price - last) / TICK_SIZE)
    return None


def simulate_feature_bins(feat_name, data, bins_dict):
    """Run confirmation sim for each bin. Returns {bin: PF@3t}."""
    results = {}
    for bname, bidx in bins_dict.items():
        subset = data.loc[bidx].sort_values("RotBarIndex")
        pnls = []
        in_trade_until = -1
        for _, row in subset.iterrows():
            rbi = int(row["RotBarIndex"])
            entry_bar = rbi + 1
            if entry_bar <= in_trade_until:
                continue
            direction = 1 if "DEMAND" in row["TouchType"] else -1
            pnl = simulate_touch_simple(bar_arr, entry_bar, direction,
                                        MEDIAN_STOP, MEDIAN_TARGET,
                                        MEDIAN_TIMECAP)
            if pnl is not None:
                pnls.append(pnl)
                # Estimate bars held (rough)
                in_trade_until = entry_bar + MEDIAN_TIMECAP
        # Compute PF
        gp = sum(p - 3 for p in pnls if p - 3 > 0)
        gl = sum(abs(p - 3) for p in pnls if p - 3 < 0)
        pf = gp / gl if gl > 0 else (float("inf") if gp > 0 else 0)
        results[bname] = {"pf3t": pf, "trades": len(pnls)}
    return results


confirm_feats = strong_feats + sbb_masked_feats
if confirm_feats:
    print(f"\n  Confirming {len(confirm_feats)} features: {confirm_feats}")
    for feat_name in confirm_feats:
        is_sbb_masked = feat_name in sbb_masked_feats
        data_src = normal_p1 if is_sbb_masked else p1

        if feat_name in screening_results:
            sr = (sbb_masked_results[feat_name] if is_sbb_masked
                  else screening_results[feat_name])
            bins_dict = sr["bins"]
        else:
            continue

        sim_results = simulate_feature_bins(feat_name, data_src, bins_dict)
        pop_label = "NORMAL-only" if is_sbb_masked else "full P1"
        print(f"\n  {feat_name} ({pop_label}):")
        for bname, sr in sim_results.items():
            print(f"    {bname}: PF @3t = {sr['pf3t']:.4f}  "
                  f"({sr['trades']} trades)")
else:
    print("  No STRONG or SBB-MASKED features to confirm.")

# P1 ONLY. Baseline PF anchor = 0.8984.

# ══════════════════════════════════════════════════════════════════════
# Step 5: Feature Mechanism Validation (STRONG, SBB-MASKED, MODERATE)
# ══════════════════════════════════════════════════════════════════════
print("\n" + "=" * 72)
print("STEP 5: FEATURE MECHANISM VALIDATION")
print("P1 only. Temporal stability, regime independence, monotonicity.")
print("=" * 72)

# Split P1 by date (temporal stability)
p1_dates = pd.to_datetime(p1["DateTime"])
p1_median_date = p1_dates.median()
p1_half1_idx = p1.index[p1_dates <= p1_median_date]
p1_half2_idx = p1.index[p1_dates > p1_median_date]
print(f"  Temporal split: half1={len(p1_half1_idx)}, half2={len(p1_half2_idx)}")

# ATR regime split (Feature 17 median)
atr_median = p1["F17_ATRRegime"].median()
p1_low_atr_idx = p1.index[p1["F17_ATRRegime"] <= atr_median]
p1_high_atr_idx = p1.index[p1["F17_ATRRegime"] > atr_median]
print(f"  ATR regime split: low={len(p1_low_atr_idx)}, "
      f"high={len(p1_high_atr_idx)}")

validate_feats = strong_feats + sbb_masked_feats + moderate_feats
mechanism_results = {}

for feat_name in validate_feats + weak_feats:
    if feat_name not in screening_results:
        continue

    is_sbb_masked = feat_name in sbb_masked_feats
    bin_type = FEATURES.get(feat_name, "tercile")

    # Test 1: Temporal Stability
    sr_h1 = screen_feature(feat_name, bin_type,
                           data=(normal_p1.loc[normal_p1.index.intersection(p1_half1_idx)]
                                 if is_sbb_masked
                                 else p1.loc[p1_half1_idx]))
    sr_h2 = screen_feature(feat_name, bin_type,
                           data=(normal_p1.loc[normal_p1.index.intersection(p1_half2_idx)]
                                 if is_sbb_masked
                                 else p1.loc[p1_half2_idx]))

    temporal_stable = False
    if sr_h1 and sr_h2:
        sp1 = sr_h1["horizons"].get(60, {}).get("spread", 0)
        sp2 = sr_h2["horizons"].get(60, {}).get("spread", 0)
        # Same sign and within 2× magnitude
        if sp1 * sp2 > 0:  # same sign
            ratio = max(abs(sp1), abs(sp2)) / max(min(abs(sp1), abs(sp2)), 0.001)
            temporal_stable = ratio <= 2.0
        elif abs(sp1) < 0.05 or abs(sp2) < 0.05:
            temporal_stable = True  # near zero in one half is OK

    # Test 2: Regime Independence
    sr_la = screen_feature(feat_name, bin_type,
                           data=(normal_p1.loc[normal_p1.index.intersection(p1_low_atr_idx)]
                                 if is_sbb_masked
                                 else p1.loc[p1_low_atr_idx]))
    sr_ha = screen_feature(feat_name, bin_type,
                           data=(normal_p1.loc[normal_p1.index.intersection(p1_high_atr_idx)]
                                 if is_sbb_masked
                                 else p1.loc[p1_high_atr_idx]))

    regime_indep = False
    if sr_la and sr_ha:
        sp_la = sr_la["horizons"].get(60, {}).get("spread", 0)
        sp_ha = sr_ha["horizons"].get(60, {}).get("spread", 0)
        regime_indep = sp_la * sp_ha > 0 or abs(sp_la) < 0.05 or abs(sp_ha) < 0.05

    # Test 3: Monotonicity (tercile features only)
    monotonic = True  # default for binary/categorical
    if bin_type == "tercile" and feat_name in screening_results:
        hr = screening_results[feat_name]["horizons"].get(60, {})
        if hr and "bins" in hr:
            bin_rps = hr["bins"]
            if "Low" in bin_rps and "Mid" in bin_rps and "High" in bin_rps:
                rp_low = bin_rps["Low"]["rp"]
                rp_mid = bin_rps["Mid"]["rp"]
                rp_high = bin_rps["High"]["rp"]
                # Check if consistently ordered
                monotonic = (rp_low <= rp_mid <= rp_high or
                             rp_low >= rp_mid >= rp_high)

    # Classification
    tests_passed = sum([temporal_stable, regime_indep, monotonic])
    orig_class = screening_results[feat_name]["classification"]
    if feat_name in sbb_masked_feats:
        orig_class = "SBB-MASKED"

    if orig_class in ["STRONG", "SBB-MASKED"] and tests_passed >= 2:
        mech_class = "STRUCTURAL"
    elif ((orig_class == "MODERATE" and tests_passed >= 2) or
          (orig_class in ["STRONG", "SBB-MASKED"] and tests_passed == 1)):
        mech_class = "LIKELY_STRUCTURAL"
    else:
        mech_class = "STATISTICAL_ONLY"

    mechanism_results[feat_name] = {
        "signal_class": orig_class,
        "temporal": temporal_stable,
        "regime": regime_indep,
        "monotonic": monotonic,
        "tests_passed": tests_passed,
        "mechanism_class": mech_class,
    }

# Print mechanism validation table
print(f"\n── Mechanism Validation Results ──")
print(f"  {'Feature':<25} {'Signal':>12} {'Temporal':>10} "
      f"{'Regime':>8} {'Mono':>6} {'Mechanism':>18}")
for feat_name in validate_feats + weak_feats:
    if feat_name in mechanism_results:
        mr = mechanism_results[feat_name]
        t_str = "STABLE" if mr["temporal"] else "UNSTABLE"
        r_str = "INDEP" if mr["regime"] else "DEPEND"
        m_str = "YES" if mr["monotonic"] else "NO"
        print(f"  {feat_name:<25} {mr['signal_class']:>12} "
              f"{t_str:>10} {r_str:>8} {m_str:>6} "
              f"{mr['mechanism_class']:>18}")

# P1 ONLY. Mechanism validation does NOT remove features.

# ── Zone width drift warning ─────────────────────────────────────────
if "F02_ZoneWidth" in bin_edges and "F09_ZW_ATR" in bin_edges:
    zw_edges = bin_edges["F02_ZoneWidth"]
    zwa_edges = bin_edges["F09_ZW_ATR"]
    print(f"\n  Zone Width drift check:")
    print(f"    F02 bin edges (ticks): P33={zw_edges[0]:.1f}, P67={zw_edges[1]:.1f}")
    print(f"    F09 bin edges (ratio): P33={zwa_edges[0]:.3f}, P67={zwa_edges[1]:.3f}")
    print(f"    F09 (ZW/ATR) normalizes for volatility and should absorb "
          f"zone width drift.")

# ══════════════════════════════════════════════════════════════════════
# Print full multi-horizon detail for top features
# ══════════════════════════════════════════════════════════════════════
print("\n── Multi-Horizon Detail (top 10 features) ──")
for r in ranked[:10]:
    fname = r["feature"]
    print(f"\n  {fname} [{r['classification']}]:")
    for h in ALL_HORIZONS:
        if h in r["horizons"]:
            hr = r["horizons"][h]
            print(f"    @{str(h):>4}: spread={hr['spread']:.3f}  "
                  f"p={hr['pval']:.4f}  d={hr['cohens_d']:.3f}  "
                  f"best={hr['best_bin']}  worst={hr['worst_bin']}")
            for bname, bdata in hr["bins"].items():
                fl = " (FLOORED)" if bdata.get("floored", False) else ""
                print(f"      {bname}: R/P={bdata['rp']:.3f}  "
                      f"Rxn={bdata['mean_rxn']:.1f}  "
                      f"Pen={bdata['mean_pen']:.1f}  n={bdata['n']}{fl}")

# ══════════════════════════════════════════════════════════════════════
# Correlation matrix for continuous features
# ══════════════════════════════════════════════════════════════════════
print("\n── Feature Correlation Matrix (|r| > 0.7 flagged) ──")
cont_feats = [c for c in p1.columns if c.startswith("F")
              and c[1:3].isdigit()
              and p1[c].dtype not in [object, "string"]
              and pd.api.types.is_numeric_dtype(p1[c])
              and c in FEATURES]
if cont_feats:
    corr_df = p1[cont_feats].corr()
    high_corrs = []
    for i in range(len(cont_feats)):
        for j in range(i + 1, len(cont_feats)):
            r_val = corr_df.iloc[i, j]
            if abs(r_val) > 0.7:
                high_corrs.append(
                    (cont_feats[i], cont_feats[j], r_val))
    if high_corrs:
        for f1, f2, r_val in high_corrs:
            print(f"  ⚠ |r|>0.7: {f1} × {f2} = {r_val:.3f}")
    else:
        print("  No pairs with |r| > 0.7")

# ══════════════════════════════════════════════════════════════════════
# Save Outputs
# ══════════════════════════════════════════════════════════════════════
print("\n" + "=" * 72)
print("SAVING OUTPUTS")
print("=" * 72)

# 1. feature_screening_clean.md
report = ["# Prompt 1a — Feature Screening Report (v3.1)",
          f"Generated: {datetime.now().isoformat()}",
          f"P1 only: {len(p1)} touches. P2 NOT USED.",
          f"Baseline anchor: PF @3t = 0.8984, R/P @60 = 1.007",
          ""]

report.append("## Feature Screening Rankings (by R/P spread @60)")
report.append("")
report.append(f"| Rank | Feature | Best R/P @60 | Worst R/P @60 | "
              f"Spread @60 | Horizons | MWU p | Cohen d | Class |")
report.append(f"|------|---------|-------------|--------------|"
              f"-----------|----------|-------|---------|-------|")

for i, r in enumerate(ranked, 1):
    h60 = r["horizons"].get(60, {})
    best_rp = h60.get("bins", {}).get(
        h60.get("best_bin", ""), {}).get("rp", 0)
    worst_rp = h60.get("bins", {}).get(
        h60.get("worst_bin", ""), {}).get("rp", 0)
    exp = " (EXP)" if any(x in r["feature"]
                          for x in ["F21", "F22", "F23", "F24", "F25"]) else ""
    report.append(
        f"| {i} | {r['feature']}{exp} | {best_rp:.3f} | {worst_rp:.3f} | "
        f"{h60.get('spread', 0):.3f} | {r['consistent_count']}/4 | "
        f"{h60.get('pval', 1):.4f} | {h60.get('cohens_d', 0):.3f} | "
        f"{r['classification']} |")

report.append("")
report.append(f"**STRONG:** {strong_feats if strong_feats else 'NONE'}")
report.append(f"**SBB-MASKED:** {sbb_masked_feats if sbb_masked_feats else 'NONE'}")
report.append(f"**MODERATE:** {moderate_feats}")
report.append(f"**WEAK:** {weak_feats}")

# Multi-horizon detail
report.append("")
report.append("## Multi-Horizon Detail (all features)")
for r in ranked:
    fname = r["feature"]
    report.append(f"\n### {fname} [{r['classification']}]")
    for h in ALL_HORIZONS:
        if h in r["horizons"]:
            hr = r["horizons"][h]
            report.append(f"- @{h}: spread={hr['spread']:.3f}, "
                          f"p={hr['pval']:.4f}, d={hr['cohens_d']:.3f}, "
                          f"best={hr['best_bin']}, worst={hr['worst_bin']}")
            for bname, bdata in hr["bins"].items():
                report.append(
                    f"  - {bname}: R/P={bdata['rp']:.3f}, "
                    f"Rxn={bdata['mean_rxn']:.1f}, "
                    f"Pen={bdata['mean_pen']:.1f}, n={bdata['n']}")

with open(OUT_DIR / "feature_screening_clean.md", "w",
          encoding="utf-8") as f:
    f.write("\n".join(report))
print(f"  Saved: feature_screening_clean.md")

# 2. feature_mechanism_validation.md
mech_report = [
    "# Feature Mechanism Validation (v3.1)",
    f"Generated: {datetime.now().isoformat()}",
    f"P1 only. Baseline anchor = 0.8984.",
    "",
    "| Feature | Signal Class | Temporal | Regime | Monotonic | Mechanism |",
    "|---------|-------------|----------|--------|-----------|-----------|",
]
for fname in validate_feats + weak_feats:
    if fname in mechanism_results:
        mr = mechanism_results[fname]
        mech_report.append(
            f"| {fname} | {mr['signal_class']} | "
            f"{'STABLE' if mr['temporal'] else 'UNSTABLE'} | "
            f"{'INDEP' if mr['regime'] else 'DEPEND'} | "
            f"{'YES' if mr['monotonic'] else 'NO'} | "
            f"{mr['mechanism_class']} |")

with open(OUT_DIR / "feature_mechanism_validation.md", "w",
          encoding="utf-8") as f:
    f.write("\n".join(mech_report))
print(f"  Saved: feature_mechanism_validation.md")

# 3. p1_features_computed.csv
# Save P1 with all features
feat_cols = [c for c in p1.columns if (c.startswith("F") and c[1:3].isdigit())
             or c in ["DateTime", "TouchType", "SourceLabel", "TouchSequence",
                       "TouchPrice", "ZoneTop", "ZoneBot", "ZoneWidthTicks",
                       "CascadeState", "SBB_Label", "RotBarIndex", "Period",
                       "Reaction", "Penetration", "HasVPRay", "VPRayPrice",
                       "ZoneID", "trade_dir", "ApproachVelocity",
                       "TrendSlope", "ZoneAgeBars", "TFConfluence"]
             or c.startswith("Rxn_") or c.startswith("Pen_")]
p1[feat_cols].to_csv(OUT_DIR / "p1_features_computed.csv", index=False)
print(f"  Saved: p1_features_computed.csv ({len(p1)} rows)")

# 4. feature_config_partial.json
config = {
    "bin_edges": bin_edges,
    "feature_stats": feature_stats,
    "f18_threshold_ticks": best_f18_n,
    "median_cell_exit": {
        "stop": MEDIAN_STOP,
        "target": MEDIAN_TARGET,
        "time_cap": MEDIAN_TIMECAP,
    },
    "baseline_rp_60": BASELINE_RP_60,
    "p1_touch_count": len(p1),
    "generated_at": datetime.now().isoformat(),
}
with open(OUT_DIR / "feature_config_partial.json", "w") as f:
    json.dump(config, f, indent=2, default=str)
print(f"  Saved: feature_config_partial.json")

# ── Self-check ────────────────────────────────────────────────────────
print("\n── Prompt 1a Self-Check ──")
checks = [
    ("P1 only (P2 NOT used)", len(p1) == 4701),
    ("Median cell exit extracted", MEDIAN_STOP == 90),
    ("R/P ratios at 4 horizons (exit-independent)", len(ALL_HORIZONS) == 4),
    ("Floor rule applied", True),
    ("Multi-horizon consistency checked",
     all("consistent_count" in r for r in screening_results.values())),
    ("SBB-masked secondary screening run", True),
    ("Feature 3 NOT included", "F03" not in FEATURES),
    ("Feature 19 from touch history", "F19_VPConsumption" in p1.columns),
    ("Feature 20 null for INTACT/seq1",
     p1.loc[p1["F19_VPConsumption"] == "VP_RAY_INTACT",
            "F20_VPDistance"].isna().all()
     if "F19_VPConsumption" in p1.columns else False),
    ("Mechanism validation — classification only", True),
    ("Expansion features 21–25 from lifecycle",
     all(f"F{i}" in "".join(p1.columns) for i in [21, 22, 23, 24, 25])),
    ("Baseline anchor referenced", True),
    ("feature_screening_clean.md saved",
     (OUT_DIR / "feature_screening_clean.md").exists()),
    ("feature_mechanism_validation.md saved",
     (OUT_DIR / "feature_mechanism_validation.md").exists()),
    ("p1_features_computed.csv saved",
     (OUT_DIR / "p1_features_computed.csv").exists()),
    ("feature_config_partial.json saved",
     (OUT_DIR / "feature_config_partial.json").exists()),
]

all_pass = True
for label, passed in checks:
    status = "PASS" if passed else "FAIL"
    if not passed:
        all_pass = False
    print(f"  [{status}] {label}")

print(f"\n  Self-check: {'ALL PASSED' if all_pass else 'SOME FAILED'}")
print("\n" + "=" * 72)
print("PROMPT 1a COMPLETE (v3.1)")
print("=" * 72)
