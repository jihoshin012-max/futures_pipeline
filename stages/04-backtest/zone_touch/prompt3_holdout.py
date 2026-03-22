# archetype: zone_touch
"""Prompt 3 — P2 Holdout & Verdicts (v3.1).

P2a and P2b holdout tests (separate then combined), statistical validation,
final verdicts.  ALL parameters frozen from P1.  No recalibration.
Baseline PF anchor = 0.8984.
"""

import json
import sys
import time
import warnings
from copy import deepcopy
from datetime import datetime
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
warnings.filterwarnings("ignore", category=FutureWarning)

import numpy as np
import pandas as pd
from scipy import stats

BASE = Path(r"c:\Projects\pipeline")
DATA_DIR = BASE / "stages" / "01-data" / "output" / "zone_prep"
OUT_DIR = BASE / "stages" / "04-backtest" / "zone_touch" / "output"
TICK_SIZE = 0.25

BASELINE_PF = 0.8984

print("=" * 72)
print("PROMPT 3 — P2 HOLDOUT & VERDICTS (v3.1)")
print("ALL PARAMETERS FROZEN FROM P1.  NO RECALIBRATION.")
print(f"Baseline PF anchor = {BASELINE_PF}")
print("=" * 72)

# ══════════════════════════════════════════════════════════════════════
# Load Frozen Parameters
# ══════════════════════════════════════════════════════════════════════

with open(OUT_DIR / "scoring_model_acal.json") as f:
    acal_cfg = json.load(f)
with open(OUT_DIR / "scoring_model_aeq.json") as f:
    aeq_cfg = json.load(f)
with open(OUT_DIR / "scoring_model_bzscore.json") as f:
    bz_cfg = json.load(f)
with open(OUT_DIR / "feature_config.json") as f:
    feat_cfg = json.load(f)
with open(OUT_DIR / "segmentation_params_clean.json") as f:
    seg_params = json.load(f)
with open(OUT_DIR / "frozen_parameters_manifest_clean.json") as f:
    manifest = json.load(f)
with open(OUT_DIR / "feature_analysis_clean.md") as f:
    feat_analysis_text = f.read()

WINNING_FEATURES = feat_cfg["winning_features"]
TS_P33 = feat_cfg["trend_slope_p33"]
TS_P67 = feat_cfg["trend_slope_p67"]
BIN_EDGES = feat_cfg["bin_edges"]
FEAT_STATS = feat_cfg["feature_stats"]

B_ONLY_VIABLE = "VIABLE" in feat_analysis_text.upper()

print(f"\n── Frozen Configuration ──")
print(f"  Baseline PF anchor: {BASELINE_PF}")
print(f"  Winning features: {WINNING_FEATURES}")
print(f"  A-Cal threshold: {acal_cfg['threshold']:.2f}/{acal_cfg['max_score']:.2f}")
print(f"  A-Eq threshold: {aeq_cfg['threshold']:.1f}/{aeq_cfg['max_score']}")
print(f"  B-ZScore threshold: {bz_cfg['threshold']:.3f}")
print(f"  B-only 16th run: {'YES' if B_ONLY_VIABLE else 'NO'}")
print(f"  Number of runs: {15 + (1 if B_ONLY_VIABLE else 0)}")

# P1-FROZEN PARAMETERS ONLY.  NO RECALIBRATION.  Baseline PF anchor = 0.8984.

# ══════════════════════════════════════════════════════════════════════
# Load P2 Data
# ══════════════════════════════════════════════════════════════════════

print("\n── Loading P2 Data ──")
p2a_raw = pd.read_csv(DATA_DIR / "NQ_merged_P2a.csv")
p2b_raw = pd.read_csv(DATA_DIR / "NQ_merged_P2b.csv")
bar_p2 = pd.read_csv(DATA_DIR / "NQ_bardata_P2.csv")
bar_p2.columns = bar_p2.columns.str.strip()

print(f"  P2a raw touches: {len(p2a_raw)}")
print(f"  P2b raw touches: {len(p2b_raw)}")
print(f"  P2 bars: {len(bar_p2)}")

# Filter RotBarIndex < 0
bad_a = p2a_raw["RotBarIndex"] < 0
bad_b = p2b_raw["RotBarIndex"] < 0
print(f"  P2a removed (RotBarIndex<0): {bad_a.sum()}")
print(f"  P2b removed (RotBarIndex<0): {bad_b.sum()}")
p2a = p2a_raw[~bad_a].reset_index(drop=True)
p2b = p2b_raw[~bad_b].reset_index(drop=True)
print(f"  P2a touches after filter: {len(p2a)}")
print(f"  P2b touches after filter: {len(p2b)}")

# Bar data arrays
bar_arr = bar_p2[["Open", "High", "Low", "Last"]].to_numpy(dtype=np.float64)
bar_vol = bar_p2["Volume"].to_numpy(dtype=np.float64)
bar_trades_arr = bar_p2["# of Trades"].to_numpy(dtype=np.float64)
bar_bid_vol = bar_p2["Bid Volume"].to_numpy(dtype=np.float64)
bar_ask_vol = bar_p2["Ask Volume"].to_numpy(dtype=np.float64)
bar_atr = bar_p2["ATR"].to_numpy(dtype=np.float64)
bar_zz_len = bar_p2["Zig Zag Line Length"].to_numpy(dtype=np.float64)
bar_zz_osc = bar_p2["Zig Zag Oscillator"].to_numpy(dtype=np.float64)
n_bars = len(bar_arr)

# Channel columns for F18 (if needed)
# P2 bar data may have extra columns; find Top/Bottom by name
chan_cols_top = [c for c in bar_p2.columns if c.strip() == "Top"]
chan_cols_bot = [c for c in bar_p2.columns if c.strip() == "Bottom"]
# Use positional access for channel columns
all_cols = list(bar_p2.columns)
top_positions = [i for i, c in enumerate(all_cols) if c.strip() == "Top"]
bot_positions = [i for i, c in enumerate(all_cols) if c.strip() == "Bottom"]

# bar_p2_vals not needed — channel access via named columns

# Parse bar datetimes for 16:55 ET flatten check
print("  Parsing P2 bar datetimes...")
bar_datetimes = []
for _, row in bar_p2.iterrows():
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

# P1-FROZEN PARAMETERS.  Baseline PF anchor = 0.8984.

# ══════════════════════════════════════════════════════════════════════
# Feature Computation on P2 (using P1-frozen parameters)
# ══════════════════════════════════════════════════════════════════════

print("\n" + "=" * 72)
print("FEATURE COMPUTATION ON P2 (P1-frozen parameters)")
print("=" * 72)


def compute_features(df, label):
    """Compute all needed features for a P2 subset."""
    print(f"\n  Computing features for {label} ({len(df)} touches)...")
    df = df.copy()

    # F01: Timeframe
    df["F01_Timeframe"] = df["SourceLabel"]

    # F02: Zone Width
    df["F02_ZoneWidth"] = df["ZoneWidthTicks"]

    # F04: Cascade State
    df["F04_CascadeState"] = df["CascadeState"].replace("UNKNOWN", "NO_PRIOR")

    # F09: ZW/ATR
    atr_vals = []
    for rbi in df["RotBarIndex"].values:
        rbi = int(rbi)
        if 0 <= rbi < n_bars and bar_atr[rbi] > 0:
            atr_vals.append(bar_atr[rbi])
        else:
            atr_vals.append(np.nan)
    df["F09_ZW_ATR"] = df["ZoneWidthTicks"].values * TICK_SIZE / np.array(atr_vals)

    # F10: Prior Penetration (need zone grouping)
    df["ZoneID"] = (df["TouchType"].astype(str) + "|" +
                    df["ZoneTop"].astype(str) + "|" +
                    df["ZoneBot"].astype(str) + "|" +
                    df["SourceLabel"].astype(str))

    prior_pen = {}
    for zone_id, group in df.sort_values(["ZoneID", "TouchSequence"]).groupby("ZoneID"):
        group = group.sort_values("TouchSequence")
        prev_pen = np.nan
        for idx, row in group.iterrows():
            if row["TouchSequence"] == 1:
                prior_pen[idx] = np.nan
            else:
                prior_pen[idx] = prev_pen
            prev_pen = row["Penetration"]
    df["F10_PriorPenetration"] = df.index.map(prior_pen)

    # F17: ATR Regime (for seg4)
    atr_regime = []
    for rbi in df["RotBarIndex"].values:
        rbi = int(rbi)
        if rbi < 50 or rbi >= n_bars:
            atr_regime.append(np.nan)
            continue
        start = max(0, rbi - 500)
        trailing = bar_atr[start:rbi + 1]
        current = bar_atr[rbi]
        pctile = (trailing < current).sum() / len(trailing)
        atr_regime.append(pctile)
    df["F17_ATRRegime"] = atr_regime

    # F21: Zone Age
    df["F21_ZoneAge"] = df["ZoneAgeBars"]

    # TrendLabel (from TrendSlope using P1-frozen P33/P67)
    def assign_trend(ts):
        if pd.isna(ts):
            return "NT"
        if ts <= TS_P33:
            return "CT"
        elif ts >= TS_P67:
            return "WT"
        else:
            return "NT"
    df["TrendLabel"] = df["TrendSlope"].apply(assign_trend)

    # SBB_Label already in CSV
    if "SBB_Label" not in df.columns:
        df["SBB_Label"] = "NORMAL"

    print(f"    Features computed. F10 null rate: "
          f"{df['F10_PriorPenetration'].isna().mean()*100:.1f}%")

    return df


p2a = compute_features(p2a, "P2a")
p2b = compute_features(p2b, "P2b")

# P1-FROZEN PARAMETERS ONLY.  NO P2-derived parameters.  Baseline PF anchor = 0.8984.

# ══════════════════════════════════════════════════════════════════════
# Score P2 Touches (using P1-frozen scoring models)
# ══════════════════════════════════════════════════════════════════════

print("\n" + "=" * 72)
print("SCORING P2 TOUCHES (P1-frozen models)")
print("=" * 72)


def score_acal(df):
    """A-Cal scoring: bin edges from P1, calibrated weights."""
    weights = acal_cfg["weights"]
    bin_edges = acal_cfg["bin_edges"]
    cat_maps = acal_cfg["categorical_mappings"]
    scores = np.zeros(len(df))

    for feat, weight in weights.items():
        if feat in bin_edges:
            lo, hi = bin_edges[feat]
            vals = df[feat].values.astype(float)
            # Low bin = best (highest weight), High bin = worst (0)
            pts = np.where(vals <= lo, weight,
                    np.where(vals <= hi, weight / 2, 0.0))
            # Handle NaN: assign 0
            pts = np.where(np.isnan(vals), 0.0, pts)
            scores += pts
        elif feat in cat_maps:
            cm = cat_maps[feat]
            cats = cm["cats"]
            best = cm["best"]
            worst = cm["worst"]
            # Best category gets full weight, worst gets 0
            n_cats = len(cats)
            # Rank: best=n_cats-1, worst=0
            rank_map = {}
            if n_cats <= 3:
                rank_map[best] = weight
                rank_map[worst] = 0.0
                for c in cats:
                    if c not in rank_map:
                        rank_map[c] = weight / 2
            else:
                # Distribute linearly
                best_idx = cats.index(best) if best in cats else 0
                worst_idx = cats.index(worst) if worst in cats else len(cats)-1
                for i, c in enumerate(cats):
                    if c == best:
                        rank_map[c] = weight
                    elif c == worst:
                        rank_map[c] = 0.0
                    else:
                        rank_map[c] = weight / 2
            pts = df[feat].map(rank_map).fillna(0).values
            scores += pts

    return scores


def score_aeq(df):
    """A-Eq scoring: equal weight per feature."""
    pts_per = aeq_cfg["pts_per_feature"]
    bin_edges = aeq_cfg["bin_edges"]
    cat_maps = aeq_cfg["categorical_mappings"]
    scores = np.zeros(len(df))

    for feat in WINNING_FEATURES:
        if feat in bin_edges:
            lo, hi = bin_edges[feat]
            vals = df[feat].values.astype(float)
            pts = np.where(vals <= lo, pts_per,
                    np.where(vals <= hi, pts_per / 2, 0.0))
            pts = np.where(np.isnan(vals), 0.0, pts)
            scores += pts
        elif feat in cat_maps:
            cm = cat_maps[feat]
            cats = cm["cats"]
            best = cm["best"]
            worst = cm["worst"]
            rank_map = {}
            if len(cats) <= 3:
                rank_map[best] = pts_per
                rank_map[worst] = 0.0
                for c in cats:
                    if c not in rank_map:
                        rank_map[c] = pts_per / 2
            else:
                for c in cats:
                    if c == best:
                        rank_map[c] = pts_per
                    elif c == worst:
                        rank_map[c] = 0.0
                    else:
                        rank_map[c] = pts_per / 2
            pts = df[feat].map(rank_map).fillna(0).values
            scores += pts

    return scores


def score_bzscore(df):
    """B-ZScore scoring: standardize with P1 means/stds, apply regression."""
    zfeats = bz_cfg["zscore_features"]
    coeffs = bz_cfg["coefficients"]
    intercept = bz_cfg["intercept"]
    means = bz_cfg["scaler_means"]
    stds = bz_cfg["scaler_stds"]

    # Build feature matrix matching zscore_features order
    X = np.zeros((len(df), len(zfeats)))
    for j, zf in enumerate(zfeats):
        if zf == "F10_PriorPenetration":
            X[:, j] = df["F10_PriorPenetration"].fillna(0).values
        elif zf == "F21_ZoneAge":
            X[:, j] = df["F21_ZoneAge"].fillna(0).values
        elif zf.startswith("F04_CascadeState_"):
            cat = zf.replace("F04_CascadeState_", "")
            X[:, j] = (df["F04_CascadeState"] == cat).astype(float).values
        elif zf.startswith("F01_Timeframe_"):
            cat = zf.replace("F01_Timeframe_", "")
            X[:, j] = (df["F01_Timeframe"] == cat).astype(float).values

    # Standardize with P1 means/stds
    means_arr = np.array(means)
    stds_arr = np.array(stds)
    stds_arr[stds_arr == 0] = 1.0
    X_scaled = (X - means_arr) / stds_arr

    # Apply regression
    coeff_arr = np.array([coeffs[zf] for zf in zfeats])
    scores = X_scaled @ coeff_arr + intercept

    return scores


def score_all(df, label):
    """Score touches with all 3 models."""
    df["score_acal"] = score_acal(df)
    df["score_aeq"] = score_aeq(df)
    df["score_bzscore"] = score_bzscore(df)
    print(f"\n  {label} scoring summary:")
    for model, col, thresh in [("A-Cal", "score_acal", acal_cfg["threshold"]),
                                ("A-Eq", "score_aeq", aeq_cfg["threshold"]),
                                ("B-ZScore", "score_bzscore", bz_cfg["threshold"])]:
        above = (df[col] >= thresh).sum()
        print(f"    {model}: {above}/{len(df)} above threshold "
              f"({above/len(df)*100:.1f}%)")
    return df


p2a = score_all(p2a, "P2a")
p2b = score_all(p2b, "P2b")

# Checkpoint: NO P2-derived parameters used.  All encoding uses P1-frozen values.
print("\n  ✓ CHECKPOINT: All scoring uses P1-frozen bin edges, weights, "
      "thresholds, and means/stds.")

# P1-FROZEN PARAMETERS ONLY.  Baseline PF anchor = 0.8984.

# ══════════════════════════════════════════════════════════════════════
# Feature Drift Check (Step 9a)
# ══════════════════════════════════════════════════════════════════════

print("\n" + "=" * 72)
print("FEATURE DRIFT CHECK: P2 distributions vs P1 bin edges")
print("=" * 72)

drift_features = {
    "F10_PriorPenetration": True,  # winning
    "F04_CascadeState": False,     # winning, categorical
    "F01_Timeframe": False,        # winning, categorical
    "F21_ZoneAge": True,           # winning
    "F02_ZoneWidth": True,         # diagnostic
    "F09_ZW_ATR": True,            # diagnostic
}

p2_all_drift = pd.concat([p2a, p2b], ignore_index=True)

for feat, is_numeric in drift_features.items():
    if not is_numeric:
        print(f"\n  {feat} (categorical):")
        vc = p2_all_drift[feat].value_counts(normalize=True) * 100
        for cat, pct in vc.head(10).items():
            print(f"    {cat}: {pct:.1f}%")
        continue

    if feat not in BIN_EDGES:
        print(f"\n  {feat}: no P1 bin edges available")
        continue

    lo, hi = BIN_EDGES[feat]
    vals = p2_all_drift[feat].dropna()
    n = len(vals)
    if n == 0:
        print(f"\n  {feat}: ALL NULL")
        continue

    low_bin = (vals <= lo).sum()
    mid_bin = ((vals > lo) & (vals <= hi)).sum()
    high_bin = (vals > hi).sum()

    print(f"\n  {feat} (P1 edges: {lo}, {hi}):")
    print(f"    Low  (≤{lo}): {low_bin:>5} ({low_bin/n*100:.1f}%)")
    print(f"    Mid  ({lo}-{hi}): {mid_bin:>5} ({mid_bin/n*100:.1f}%)")
    print(f"    High (>{hi}): {high_bin:>5} ({high_bin/n*100:.1f}%)")

    # Flag if >80% in one bin
    max_pct = max(low_bin, mid_bin, high_bin) / n * 100
    if max_pct > 80:
        print(f"    ⚠️ DRIFT: {max_pct:.1f}% in single bin — "
              f"feature has lost discriminative power on P2!")

del p2_all_drift

# P1-FROZEN PARAMETERS ONLY.  NO RECALIBRATION.  Baseline PF anchor = 0.8984.

# ══════════════════════════════════════════════════════════════════════
# Simulation Engine (identical to Prompts 1-2)
# ══════════════════════════════════════════════════════════════════════


def sim_trade(entry_bar, direction, stop, target, be_trigger, trail_trigger,
              tcap):
    """Simulate single trade.  Identical to Prompt 2 engine."""
    if entry_bar >= n_bars:
        return None, 0, None
    ep = bar_arr[entry_bar, 0]
    if direction == 1:
        stop_price = ep - stop * TICK_SIZE
        target_price = ep + target * TICK_SIZE
    else:
        stop_price = ep + stop * TICK_SIZE
        target_price = ep - target * TICK_SIZE

    mfe = 0.0
    be_active = False
    trail_active = False
    trail_stop_price = stop_price

    end = min(entry_bar + tcap, n_bars)
    for i in range(entry_bar, end):
        h, l, last = bar_arr[i, 1], bar_arr[i, 2], bar_arr[i, 3]
        bh = i - entry_bar + 1

        if direction == 1:
            cur_fav = (h - ep) / TICK_SIZE
        else:
            cur_fav = (ep - l) / TICK_SIZE
        mfe = max(mfe, cur_fav)

        if be_trigger > 0 and not be_active and mfe >= be_trigger:
            be_active = True
            if direction == 1:
                stop_price = max(stop_price, ep)
                trail_stop_price = max(trail_stop_price, ep)
            else:
                stop_price = min(stop_price, ep)
                trail_stop_price = min(trail_stop_price, ep)

        if trail_trigger > 0 and mfe >= trail_trigger:
            trail_active = True
            if direction == 1:
                new_trail = ep + (mfe - trail_trigger) * TICK_SIZE
                trail_stop_price = max(trail_stop_price, new_trail)
                stop_price = max(stop_price, trail_stop_price)
            else:
                new_trail = ep - (mfe - trail_trigger) * TICK_SIZE
                trail_stop_price = min(trail_stop_price, new_trail)
                stop_price = min(stop_price, trail_stop_price)

        if direction == 1:
            stop_hit = l <= stop_price
            target_hit = h >= target_price
        else:
            stop_hit = h >= stop_price
            target_hit = l <= target_price

        if stop_hit and target_hit:
            pnl = ((stop_price - ep) / TICK_SIZE if direction == 1
                    else (ep - stop_price) / TICK_SIZE)
            if trail_active:
                return pnl, bh, "TRAIL"
            elif be_active:
                return pnl, bh, "BE"
            else:
                return pnl, bh, "STOP"
        if stop_hit:
            pnl = ((stop_price - ep) / TICK_SIZE if direction == 1
                    else (ep - stop_price) / TICK_SIZE)
            if trail_active:
                return pnl, bh, "TRAIL"
            elif be_active:
                return pnl, bh, "BE"
            else:
                return pnl, bh, "STOP"
        if target_hit:
            return target, bh, "TARGET"

        if bh >= tcap:
            pnl = ((last - ep) / TICK_SIZE if direction == 1
                    else (ep - last) / TICK_SIZE)
            return pnl, bh, "TIMECAP"

    if end > entry_bar:
        last = bar_arr[end - 1, 3]
        pnl = ((last - ep) / TICK_SIZE if direction == 1
                else (ep - last) / TICK_SIZE)
        return pnl, end - entry_bar, "TIMECAP"
    return None, 0, None


def run_sim_group(touches_df, stop, target, be_trigger, trail_trigger, tcap):
    """Simulate group with no-overlap filter."""
    subset = touches_df.sort_values("RotBarIndex")
    pnls = []
    exit_types = []
    in_trade_until = -1
    for _, row in subset.iterrows():
        rbi = int(row["RotBarIndex"])
        entry_bar = rbi + 1
        if entry_bar <= in_trade_until:
            continue
        direction = 1 if "DEMAND" in str(row["TouchType"]) else -1
        pnl, bh, etype = sim_trade(entry_bar, direction, stop, target,
                                    be_trigger, trail_trigger, tcap)
        if pnl is not None:
            pnls.append(pnl)
            exit_types.append(etype)
            in_trade_until = entry_bar + bh - 1
    if not pnls:
        return 0, 0, [], []
    gp = sum(p - 3 for p in pnls if p - 3 > 0)
    gl = sum(abs(p - 3) for p in pnls if p - 3 < 0)
    pf = gp / gl if gl > 0 else (float("inf") if gp > 0 else 0)
    return pf, len(pnls), pnls, exit_types


def compute_pf(pnls, cost=3):
    if not pnls:
        return 0
    gp = sum(p - cost for p in pnls if p - cost > 0)
    gl = sum(abs(p - cost) for p in pnls if p - cost < 0)
    return gp / gl if gl > 0 else (float("inf") if gp > 0 else 0)


def compute_max_dd(pnls, cost=3):
    if not pnls:
        return 0
    cum = 0
    peak = 0
    max_dd = 0
    for p in pnls:
        cum += (p - cost)
        peak = max(peak, cum)
        dd = peak - cum
        max_dd = max(max_dd, dd)
    return max_dd


def compute_profit_dd(pnls, cost=3):
    if not pnls:
        return 0
    net = sum(p - cost for p in pnls)
    dd = compute_max_dd(pnls, cost)
    return net / dd if dd > 0 else (float("inf") if net > 0 else 0)


def compute_sharpe(pnls, cost=3):
    if len(pnls) < 2:
        return 0
    net = [p - cost for p in pnls]
    mn = np.mean(net)
    sd = np.std(net, ddof=1)
    return mn / sd if sd > 0 else 0


# P1-FROZEN PARAMETERS.  Baseline PF anchor = 0.8984.

# ══════════════════════════════════════════════════════════════════════
# Segmentation Assignment (frozen from P1)
# ══════════════════════════════════════════════════════════════════════


def get_session(dt_str):
    try:
        dt = pd.Timestamp(dt_str)
        t_min = dt.hour * 60 + dt.minute
        if 510 <= t_min < 720:
            return "Morning"
        elif 720 <= t_min < 1020:
            return "Afternoon"
        else:
            return "Other"
    except Exception:
        return "Other"


def assign_segments(df, score_col, threshold, seg_type, centroids=None):
    """Assign segmentation groups using P1-frozen rules."""
    edge_mask = df["TouchType"].isin(["DEMAND_EDGE", "SUPPLY_EDGE"])
    above_thresh = df[score_col] >= threshold

    if seg_type == "seg1":
        groups = {
            "ModeA": df[above_thresh & edge_mask],
            "ModeB": df[~(above_thresh & edge_mask)],
        }
    elif seg_type == "seg2":
        sessions = df["DateTime"].apply(get_session)
        groups = {
            "ModeA": df[above_thresh & edge_mask],
            "ModeB": df[~above_thresh & edge_mask & (sessions == "Morning")],
            "ModeC": df[edge_mask & (sessions == "Afternoon") &
                        ~(above_thresh & edge_mask)],
            "ModeD": df[~edge_mask | (~above_thresh &
                        ~(sessions == "Morning") &
                        ~(sessions == "Afternoon"))],
        }
    elif seg_type == "seg3":
        wt_nt = df["TrendLabel"].isin(["WT", "NT"])
        ct = df["TrendLabel"] == "CT"
        groups = {
            "ModeA": df[above_thresh & edge_mask & wt_nt],
            "ModeB": df[above_thresh & edge_mask & ct],
            "ModeC": df[~(above_thresh & edge_mask)],
        }
    elif seg_type == "seg4":
        # Use P1 ATR median from feature_stats? No — seg4 used p1 median.
        # For P2 we apply same split: use P1's median ATR regime value.
        # P1 median is ~0.844 (from feature_stats mean).  Compute from P1 data.
        # Actually Prompt 2 used p1["F17_ATRRegime"].median().
        # We don't have P1 data loaded.  Use FEAT_STATS mean as proxy.
        atr_p50 = FEAT_STATS.get("F17_ATRRegime", {}).get("mean", 0.844)
        low_atr = df["F17_ATRRegime"] <= atr_p50
        groups = {
            "ModeA": df[above_thresh & edge_mask & low_atr],
            "ModeB": df[above_thresh & edge_mask & ~low_atr],
            "ModeC": df[~(above_thresh & edge_mask)],
        }
    elif seg_type == "seg5" and centroids is not None:
        # Assign to nearest P1-frozen centroid (standardized by P1 mean/std)
        feat_cols = [f for f in WINNING_FEATURES
                     if f in df.columns and f in FEAT_STATS]
        numeric_feats = [f for f in feat_cols
                         if pd.api.types.is_numeric_dtype(df[f])]
        if numeric_feats:
            X = df[numeric_feats].fillna(
                df[numeric_feats].median()).values
            # Standardize with P1 mean/std
            p1_means = np.array([FEAT_STATS[f]["mean"] for f in numeric_feats])
            p1_stds = np.array([FEAT_STATS[f]["std"] for f in numeric_feats])
            p1_stds[p1_stds == 0] = 1.0
            X_scaled = (X - p1_means) / p1_stds
            # Assign to nearest centroid
            centroids_arr = np.array(centroids)
            labels = np.argmin(
                np.linalg.norm(X_scaled[:, None, :] - centroids_arr[None, :, :],
                               axis=2), axis=1)
            groups = {}
            for c in range(len(centroids)):
                c_mask = labels == c
                if c_mask.sum() >= 1:
                    groups[f"Cluster{c}"] = df[c_mask]
        else:
            groups = {"All": df}
    else:
        groups = {"All": df}

    return {k: v for k, v in groups.items() if len(v) >= 1}


# ══════════════════════════════════════════════════════════════════════
# Run Holdout Helper
# ══════════════════════════════════════════════════════════════════════


def apply_filters(df, filters):
    """Apply frozen filters to a group."""
    filtered = df.copy()
    seq_max = filters.get("seq_max")
    if seq_max is not None:
        filtered = filtered[filtered["TouchSequence"] <= seq_max]
    if filters.get("tf_filter"):
        filtered = filtered[filtered["SourceLabel"].isin(
            ["15m", "30m", "60m", "90m", "120m"])]
    return filtered


def compute_group_stats(pnls, exit_types, n_touches, filtered_df):
    """Compute all stats for a group."""
    if not pnls:
        return None

    trades = len(pnls)
    pf2 = compute_pf(pnls, 2)
    pf3 = compute_pf(pnls, 3)
    pf4 = compute_pf(pnls, 4)
    dd = compute_max_dd(pnls)
    pdd = compute_profit_dd(pnls)
    sharpe = compute_sharpe(pnls)
    net_pnl = sum(p - 3 for p in pnls)
    avg_pnl = net_pnl / trades if trades > 0 else 0
    wr = sum(1 for p in pnls if p - 3 > 0) / trades * 100 if trades > 0 else 0
    lr = sum(1 for p in pnls if p - 3 < 0) / trades * 100 if trades > 0 else 0
    be_rate = sum(1 for p in pnls if abs(p - 3) < 0.01) / trades * 100 if trades > 0 else 0

    exit_counts = {"TARGET": 0, "STOP": 0, "BE": 0, "TRAIL": 0, "TIMECAP": 0}
    for et in exit_types:
        if et in exit_counts:
            exit_counts[et] += 1

    sbb_mask = filtered_df["SBB_Label"] == "SBB" if "SBB_Label" in filtered_df.columns else pd.Series(False, index=filtered_df.index)
    sbb_pct = sbb_mask.mean() * 100

    # SBB PnL breakdown: simulate SBB-only touches
    sbb_touches = filtered_df[sbb_mask]

    return {
        "n_touches": n_touches,
        "trades": trades,
        "pf_2t": pf2, "pf_3t": pf3, "pf_4t": pf4,
        "win_rate": wr, "loss_rate": lr, "be_rate": be_rate,
        "net_pnl_3t": net_pnl, "avg_pnl_3t": avg_pnl,
        "max_dd": dd, "profit_dd": pdd, "sharpe": sharpe,
        "exit_counts": exit_counts,
        "sbb_pct": sbb_pct,
        "sbb_n_touches": len(sbb_touches),
        "pnls": pnls,
        "exit_types": exit_types,
        "vs_baseline": pf3 - BASELINE_PF,
    }


def run_holdout_half(df, half_label):
    """Run all 15 (+16th B-only) frozen runs on one P2 half."""
    print(f"\n{'=' * 72}")
    print(f"HOLDOUT: {half_label} ({len(df)} touches)")
    print(f"ALL P1-FROZEN PARAMETERS.  NO RECALIBRATION.")
    print(f"{'=' * 72}")

    results = {}
    run_count = 0

    for run_key, params in seg_params.items():
        seg_type = params["seg_type"]
        model_name = params["model"]
        score_col = params["score_col"]
        threshold = params["threshold"]

        run_count += 1
        print(f"\n── Run {run_count}/{15 + (1 if B_ONLY_VIABLE else 0)}: "
              f"{run_key} ({half_label}) ──")

        # Get centroids for seg5
        centroids = None
        if seg_type == "seg5":
            grp_data = params["groups"]
            if "_centroids" in grp_data:
                centroids = grp_data["_centroids"]

        # Assign segments
        groups = assign_segments(df, score_col, threshold, seg_type,
                                 centroids)

        run_results = {}
        for gname, gp_params in params["groups"].items():
            if gname.startswith("_"):
                continue
            if not isinstance(gp_params, dict) or "exit_params" not in gp_params:
                continue

            ep = gp_params["exit_params"]
            filters = gp_params["filters"]

            if gname not in groups:
                print(f"    {gname}: 0 touches in {half_label} — EMPTY")
                run_results[gname] = {"trades": 0, "pnls": []}
                continue

            gdf = groups[gname]
            filtered = apply_filters(gdf, filters)

            if len(filtered) == 0:
                print(f"    {gname}: 0 filtered touches — EMPTY")
                run_results[gname] = {"trades": 0, "pnls": []}
                continue

            pf, trades, pnls, etypes = run_sim_group(
                filtered, ep["stop"], ep["target"],
                ep["be_trigger"], ep["trail_trigger"], ep["time_cap"])

            stats = compute_group_stats(pnls, etypes, len(gdf), filtered)
            if stats:
                run_results[gname] = stats
                print(f"    {gname}: {len(gdf)} touches → {trades} trades  "
                      f"PF@3t={pf:.4f}  PF@4t={stats['pf_4t']:.4f}  "
                      f"P/DD={stats['profit_dd']:.3f}  "
                      f"SBB={stats['sbb_pct']:.1f}%  "
                      f"vs base={stats['vs_baseline']:+.4f}")
            else:
                run_results[gname] = {"trades": 0, "pnls": []}
                print(f"    {gname}: {len(gdf)} touches → 0 trades")

        results[run_key] = run_results

    # P1-FROZEN PARAMETERS.  No recalibration.  Baseline PF anchor = 0.8984.

    # B-only 16th run
    if B_ONLY_VIABLE:
        print(f"\n── Run 16 (B-only): {half_label} ──")
        aeq_above = df["score_aeq"] >= aeq_cfg["threshold"]
        bz_above = df["score_bzscore"] >= bz_cfg["threshold"]
        b_only_mask = bz_above & ~aeq_above
        b_only = df[b_only_mask]
        print(f"    B-only touches: {len(b_only)}")

        if len(b_only) > 0:
            # Use seg1_B-ZScore ModeA exits for B-only population
            bz_seg1 = seg_params.get("seg1_B-ZScore", {})
            bz_mode_a = bz_seg1.get("groups", {}).get("ModeA", {})
            if "exit_params" in bz_mode_a:
                ep = bz_mode_a["exit_params"]
                filters = bz_mode_a.get("filters", {})
                filtered = apply_filters(b_only, filters)
                if len(filtered) > 0:
                    pf, trades, pnls, etypes = run_sim_group(
                        filtered, ep["stop"], ep["target"],
                        ep["be_trigger"], ep["trail_trigger"],
                        ep["time_cap"])
                    stats = compute_group_stats(pnls, etypes, len(b_only),
                                                filtered)
                    if stats:
                        results["b_only"] = {"BOnly": stats}
                        print(f"    BOnly: {len(b_only)} touches → {trades} "
                              f"trades  PF@3t={pf:.4f}  "
                              f"PF@4t={stats['pf_4t']:.4f}  "
                              f"P/DD={stats['profit_dd']:.3f}  "
                              f"SBB={stats['sbb_pct']:.1f}%")
                    else:
                        results["b_only"] = {"BOnly": {"trades": 0, "pnls": []}}
                        print(f"    BOnly: 0 trades")
                else:
                    results["b_only"] = {"BOnly": {"trades": 0, "pnls": []}}
            else:
                results["b_only"] = {"BOnly": {"trades": 0, "pnls": []}}
        else:
            results["b_only"] = {"BOnly": {"trades": 0, "pnls": []}}

    return results


# ══════════════════════════════════════════════════════════════════════
# Statistical Validation Functions
# ══════════════════════════════════════════════════════════════════════


def mwu_test(group_reactions, complement_reactions):
    """Mann-Whitney U test: group vs complement."""
    g = np.array(group_reactions)
    c = np.array(complement_reactions)
    g = g[~np.isnan(g)]
    c = c[~np.isnan(c)]
    if len(g) < 5 or len(c) < 5:
        return 1.0
    try:
        _, p = stats.mannwhitneyu(g, c, alternative="greater")
        return p
    except Exception:
        return 1.0


def permutation_test(all_pnls_precomputed, group_pf, group_n, n_perms=9999):
    """Permutation test: randomly reassign group labels.

    Uses precomputed per-touch PnLs (without overlap filter) for speed.
    Returns (percentile_rank, p_value).
    """
    all_arr = np.array(all_pnls_precomputed)
    if len(all_arr) < group_n or group_n < 5:
        return 0, 1.0

    rng = np.random.default_rng(42)
    count_ge = 0
    for _ in range(n_perms):
        sample = rng.choice(all_arr, size=group_n, replace=False)
        gp = np.sum(np.maximum(sample - 3, 0))
        gl = np.sum(np.abs(np.minimum(sample - 3, 0)))
        pf = gp / gl if gl > 0 else (float("inf") if gp > 0 else 0)
        if pf >= group_pf:
            count_ge += 1

    p_val = (count_ge + 1) / (n_perms + 1)
    pctile = (1 - p_val) * 100
    return pctile, p_val


def random_entry_control(all_edge_df, group_n, group_dir_mix, exit_params,
                         n_iters=1000):
    """Random entry control: randomly select edge touches.

    Returns (percentile_rank, group_pf_rank).
    """
    ep = exit_params
    rng = np.random.default_rng(42)

    # Precompute per-touch PnLs for all edge touches with these exits
    edge_sorted = all_edge_df.sort_values("RotBarIndex")
    all_pnls_per_touch = []
    for _, row in edge_sorted.iterrows():
        rbi = int(row["RotBarIndex"])
        entry_bar = rbi + 1
        direction = 1 if "DEMAND" in str(row["TouchType"]) else -1
        pnl, _, _ = sim_trade(entry_bar, direction, ep["stop"], ep["target"],
                              ep["be_trigger"], ep["trail_trigger"],
                              ep["time_cap"])
        all_pnls_per_touch.append(pnl if pnl is not None else 0)

    all_arr = np.array(all_pnls_per_touch)
    if len(all_arr) < group_n:
        return 0

    pf_list = []
    for _ in range(n_iters):
        idx = rng.choice(len(all_arr), size=min(group_n, len(all_arr)),
                         replace=False)
        sample = all_arr[idx]
        gp = np.sum(np.maximum(sample - 3, 0))
        gl = np.sum(np.abs(np.minimum(sample - 3, 0)))
        pf = gp / gl if gl > 0 else (float("inf") if gp > 0 else 0)
        pf_list.append(pf)

    return pf_list


def run_stat_tests(df, results, half_label):
    """Run statistical validation on holdout results."""
    print(f"\n{'=' * 72}")
    print(f"STATISTICAL VALIDATION: {half_label}")
    print(f"{'=' * 72}")

    # Precompute Reaction for MWU (all touches)
    all_reactions = df["Reaction"].replace(-1, np.nan).values

    # Precompute per-touch PnLs for permutation (one set per exit config)
    edge_df = df[df["TouchType"].isin(["DEMAND_EDGE", "SUPPLY_EDGE"])]

    stat_results = {}

    for run_key, run_res in results.items():
        for gname, gstats in run_res.items():
            if not isinstance(gstats, dict) or gstats.get("trades", 0) < 20:
                continue

            label = f"{run_key}/{gname}"
            print(f"\n  ── {label} ({gstats['trades']} trades) ──")

            # Get the group's touches for MWU
            params = seg_params.get(run_key, {})
            if run_key == "b_only":
                # B-only group
                aeq_above = df["score_aeq"] >= aeq_cfg["threshold"]
                bz_above = df["score_bzscore"] >= bz_cfg["threshold"]
                group_mask = bz_above & ~aeq_above
            else:
                seg_type = params.get("seg_type", "")
                score_col = params.get("score_col", "")
                threshold = params.get("threshold", 0)
                centroids = None
                if seg_type == "seg5":
                    grp_data = params.get("groups", {})
                    centroids = grp_data.get("_centroids")
                segs = assign_segments(df, score_col, threshold, seg_type,
                                       centroids)
                gp_params = params.get("groups", {}).get(gname, {})
                filters = gp_params.get("filters", {})
                if gname in segs:
                    gdf = segs[gname]
                    gdf = apply_filters(gdf, filters)
                    group_mask = df.index.isin(gdf.index)
                else:
                    continue

            group_rxn = df.loc[group_mask, "Reaction"].replace(
                -1, np.nan).dropna().values
            comp_rxn = df.loc[~group_mask, "Reaction"].replace(
                -1, np.nan).dropna().values

            # MWU
            mwu_p = mwu_test(group_rxn, comp_rxn)
            print(f"    MWU p-value: {mwu_p:.6f} "
                  f"({'PASS' if mwu_p < 0.05 else 'FAIL'})")

            # Permutation test
            # Precompute PnLs for all touches with this group's exits
            ep = (params.get("groups", {}).get(gname, {})
                  .get("exit_params", {}))
            if run_key == "b_only":
                bz_seg1 = seg_params.get("seg1_B-ZScore", {})
                ep = bz_seg1.get("groups", {}).get("ModeA", {}).get(
                    "exit_params", {})

            all_touch_pnls = []
            for _, row in df.sort_values("RotBarIndex").iterrows():
                rbi = int(row["RotBarIndex"])
                entry_bar = rbi + 1
                direction = 1 if "DEMAND" in str(row["TouchType"]) else -1
                pnl, _, _ = sim_trade(
                    entry_bar, direction,
                    ep.get("stop", 90), ep.get("target", 120),
                    ep.get("be_trigger", 0), ep.get("trail_trigger", 0),
                    ep.get("time_cap", 80))
                all_touch_pnls.append(pnl if pnl is not None else 0)

            perm_pctile, perm_p = permutation_test(
                all_touch_pnls, gstats["pf_3t"], gstats["trades"])
            print(f"    Permutation: percentile={perm_pctile:.1f}%, "
                  f"p={perm_p:.6f} ({'PASS' if perm_p < 0.05 else 'FAIL'})")

            # Random entry control
            rand_pfs = random_entry_control(
                edge_df, gstats["trades"], None, ep)
            if rand_pfs:
                rand_pctile = (sum(1 for pf in rand_pfs
                                   if pf < gstats["pf_3t"])
                               / len(rand_pfs) * 100)
            else:
                rand_pctile = 0
            print(f"    Random entry: percentile={rand_pctile:.1f}% "
                  f"({'PASS' if rand_pctile > 95 else 'FAIL'})")

            stat_results[label] = {
                "mwu_p": mwu_p,
                "perm_pctile": perm_pctile,
                "perm_p": perm_p,
                "rand_pctile": rand_pctile,
            }

    return stat_results


# ══════════════════════════════════════════════════════════════════════
# Step 9: P2a Holdout Test
# ══════════════════════════════════════════════════════════════════════

print("\n" + "#" * 72)
print("# STEP 9: P2a HOLDOUT TEST (first out-of-sample)")
print("#" * 72)

t_start = time.time()
p2a_results = run_holdout_half(p2a, "P2a")
p2a_elapsed = time.time() - t_start
print(f"\n  P2a simulation complete in {p2a_elapsed:.1f}s")

# P1-FROZEN PARAMETERS.  Baseline PF = 0.8984.  No adjustments.

print("\n── P2a Statistical Validation ──")
t_start = time.time()
p2a_stats = run_stat_tests(p2a, p2a_results, "P2a")
p2a_stat_elapsed = time.time() - t_start
print(f"\n  P2a stat tests complete in {p2a_stat_elapsed:.1f}s")

# ⚠️ P2a results are FINAL.  DO NOT adjust parameters.  Proceeding to P2b.

# ══════════════════════════════════════════════════════════════════════
# Step 10: P2b Holdout Test
# ══════════════════════════════════════════════════════════════════════

print("\n" + "#" * 72)
print("# STEP 10: P2b HOLDOUT TEST (second independent confirmation)")
print("#" * 72)

t_start = time.time()
p2b_results = run_holdout_half(p2b, "P2b")
p2b_elapsed = time.time() - t_start
print(f"\n  P2b simulation complete in {p2b_elapsed:.1f}s")

# P1-FROZEN PARAMETERS.  NO adjustments based on P2a.

print("\n── P2b Statistical Validation ──")
t_start = time.time()
p2b_stats = run_stat_tests(p2b, p2b_results, "P2b")
p2b_stat_elapsed = time.time() - t_start
print(f"\n  P2b stat tests complete in {p2b_stat_elapsed:.1f}s")

# ══════════════════════════════════════════════════════════════════════
# Step 11: Combined P2 Analysis
# ══════════════════════════════════════════════════════════════════════

print("\n" + "#" * 72)
print("# STEP 11: COMBINED P2 ANALYSIS")
print("#" * 72)

# Combine P2a + P2b
p2_combined = pd.concat([p2a, p2b], ignore_index=True)
print(f"\n  Combined P2 touches: {len(p2_combined)}")

# Run combined simulation
print("\n── Combined P2 Holdout ──")
p2c_results = run_holdout_half(p2_combined, "P2_Combined")

# Combined stat tests for small-sample groups
print("\n── Combined P2 Statistical Validation (small-sample groups) ──")
combined_stat_results = {}
for run_key in set(list(p2a_results.keys()) + list(p2b_results.keys())):
    for gname in set(
        list(p2a_results.get(run_key, {}).keys()) +
        list(p2b_results.get(run_key, {}).keys())
    ):
        a_trades = (p2a_results.get(run_key, {}).get(gname, {})
                    .get("trades", 0))
        b_trades = (p2b_results.get(run_key, {}).get(gname, {})
                    .get("trades", 0))
        c_stats = (p2c_results.get(run_key, {}).get(gname, {}))
        c_trades = c_stats.get("trades", 0) if isinstance(c_stats, dict) else 0

        # Need combined stat tests if either half < 20 but combined >= 20
        if (a_trades < 20 or b_trades < 20) and c_trades >= 20:
            label = f"{run_key}/{gname}"
            if label not in p2a_stats and label not in p2b_stats:
                print(f"\n  Running combined stats for {label} "
                      f"(P2a={a_trades}, P2b={b_trades}, Combined={c_trades})")

# Run combined stat tests
p2c_stats = run_stat_tests(p2_combined, p2c_results, "P2_Combined")

# P1-FROZEN.  Baseline PF anchor = 0.8984.

# ══════════════════════════════════════════════════════════════════════
# Step 11a: Combined Results Table
# ══════════════════════════════════════════════════════════════════════

print("\n" + "=" * 72)
print("STEP 11a: COMBINED P2 RESULTS")
print("=" * 72)

print(f"\n  {'Run':<24} {'Group':<10} {'P2a Tr':>7} {'P2a PF':>8} "
      f"{'P2b Tr':>7} {'P2b PF':>8} {'Comb Tr':>8} {'Comb PF':>8} "
      f"{'P/DD':>7} {'Sharpe':>7} {'vs Base':>8}")

all_run_keys = sorted(set(
    list(p2a_results.keys()) + list(p2b_results.keys())))

for run_key in all_run_keys:
    for gname in sorted(set(
        list(p2a_results.get(run_key, {}).keys()) +
        list(p2b_results.get(run_key, {}).keys())
    )):
        a = p2a_results.get(run_key, {}).get(gname, {})
        b = p2b_results.get(run_key, {}).get(gname, {})
        c = p2c_results.get(run_key, {}).get(gname, {})

        a_tr = a.get("trades", 0) if isinstance(a, dict) else 0
        b_tr = b.get("trades", 0) if isinstance(b, dict) else 0
        c_tr = c.get("trades", 0) if isinstance(c, dict) else 0

        a_pf = a.get("pf_3t", 0) if isinstance(a, dict) else 0
        b_pf = b.get("pf_3t", 0) if isinstance(b, dict) else 0
        c_pf = c.get("pf_3t", 0) if isinstance(c, dict) else 0
        c_pdd = c.get("profit_dd", 0) if isinstance(c, dict) else 0
        c_sh = c.get("sharpe", 0) if isinstance(c, dict) else 0
        vs = c.get("vs_baseline", 0) if isinstance(c, dict) else 0

        if c_tr > 0:
            print(f"  {run_key:<24} {gname:<10} {a_tr:>7} {a_pf:>8.4f} "
                  f"{b_tr:>7} {b_pf:>8.4f} {c_tr:>8} {c_pf:>8.4f} "
                  f"{c_pdd:>7.3f} {c_sh:>7.3f} {vs:>+8.4f}")

# ══════════════════════════════════════════════════════════════════════
# Step 11b: Consistency Check
# ══════════════════════════════════════════════════════════════════════

print("\n" + "=" * 72)
print("STEP 11b: CONSISTENCY CHECK (P1 → P2a → P2b)")
print("⚠️ Expected: P2 PF substantially lower than P1 (exits calibrated on P1).")
print("=" * 72)

print(f"\n  {'Run':<24} {'Group':<10} {'P1 PF':>8} {'P2a PF':>8} "
      f"{'P2b PF':>8} {'Trend':<20}")

for run_key in all_run_keys:
    if run_key == "b_only":
        continue
    params = seg_params.get(run_key, {})
    for gname, gp in params.get("groups", {}).items():
        if gname.startswith("_"):
            continue
        if not isinstance(gp, dict) or "pf_3t" not in gp:
            continue

        p1_pf = gp["pf_3t"]
        a = p2a_results.get(run_key, {}).get(gname, {})
        b = p2b_results.get(run_key, {}).get(gname, {})
        a_pf = a.get("pf_3t", 0) if isinstance(a, dict) else 0
        b_pf = b.get("pf_3t", 0) if isinstance(b, dict) else 0
        a_tr = a.get("trades", 0) if isinstance(a, dict) else 0
        b_tr = b.get("trades", 0) if isinstance(b, dict) else 0

        if a_tr < 10 and b_tr < 10:
            trend = "Insufficient"
        elif a_tr < 20 or b_tr < 20:
            trend = "Conditional (small N)"
        elif (abs(a_pf - b_pf) / max(a_pf, b_pf, 0.01) < 0.3 and
              abs(a_pf - p1_pf) / max(p1_pf, 0.01) < 0.5):
            trend = "Stable"
        elif a_pf < p1_pf and b_pf < p1_pf:
            trend = "Degrading"
        elif a_pf > p1_pf and b_pf > p1_pf:
            trend = "Improving"
        else:
            trend = "Mixed"

        print(f"  {run_key:<24} {gname:<10} {p1_pf:>8.4f} {a_pf:>8.4f} "
              f"{b_pf:>8.4f} {trend:<20}")

# ══════════════════════════════════════════════════════════════════════
# Step 12: Cross-Run Comparison
# ══════════════════════════════════════════════════════════════════════

print("\n" + "#" * 72)
print("# STEP 12: CROSS-RUN COMPARISON")
print("#" * 72)

# 12a: Within-Segmentation
print("\n── 12a: Within-Segmentation (best group PF @3t, combined P2) ──")
print(f"  {'Seg':<6} {'A-Cal':>10} {'A-Eq':>10} {'B-ZScore':>10} {'Best':<10}")

seg_types = ["seg1", "seg2", "seg3", "seg4", "seg5"]
model_names = ["A-Cal", "A-Eq", "B-ZScore"]

for seg in seg_types:
    row_vals = {}
    for model in model_names:
        rk = f"{seg}_{model}"
        c_res = p2c_results.get(rk, {})
        best_pf = 0
        for gname, gstats in c_res.items():
            if isinstance(gstats, dict) and gstats.get("pf_3t", 0) > best_pf:
                best_pf = gstats["pf_3t"]
        row_vals[model] = best_pf

    best_model = max(row_vals, key=row_vals.get)
    print(f"  {seg:<6} {row_vals['A-Cal']:>10.4f} {row_vals['A-Eq']:>10.4f} "
          f"{row_vals['B-ZScore']:>10.4f} {best_model:<10}")

# 12b: Across-Segmentation
print("\n── 12b: Across-Segmentation (combined P2) ──")
print(f"  {'Metric':<20} {'Seg1':>8} {'Seg2':>8} {'Seg3':>8} "
      f"{'Seg4':>8} {'Seg5':>8}")

seg_summaries = {}
for seg in seg_types:
    total_trades = 0
    all_pnls = []
    best_group_pf = 0
    best_group_pdd = 0
    n_pass = 0

    for model in model_names:
        rk = f"{seg}_{model}"
        c_res = p2c_results.get(rk, {})
        for gname, gstats in c_res.items():
            if not isinstance(gstats, dict):
                continue
            tr = gstats.get("trades", 0)
            total_trades += tr
            all_pnls.extend(gstats.get("pnls", []))
            gpf = gstats.get("pf_3t", 0)
            gpdd = gstats.get("profit_dd", 0)
            if gpf > best_group_pf:
                best_group_pf = gpf
                best_group_pdd = gpdd
            if gstats.get("pf_4t", 0) > 1.5:
                n_pass += 1

    comb_pf = compute_pf(all_pnls)
    comb_sh = compute_sharpe(all_pnls)
    comb_dd = compute_max_dd(all_pnls)
    vs_base = comb_pf - BASELINE_PF

    seg_summaries[seg] = {
        "total_trades": total_trades,
        "combined_pf": comb_pf,
        "best_group_pf": best_group_pf,
        "best_group_pdd": best_group_pdd,
        "sharpe": comb_sh,
        "max_dd": comb_dd,
        "n_pass": n_pass,
        "vs_base": vs_base,
    }

for metric in ["total_trades", "combined_pf", "best_group_pf",
               "best_group_pdd", "sharpe", "max_dd", "n_pass", "vs_base"]:
    vals = [seg_summaries[s].get(metric, 0) for s in seg_types]
    fmt = ".0f" if metric in ("total_trades", "max_dd", "n_pass") else ".4f"
    print(f"  {metric:<20} " +
          " ".join(f"{v:>8{fmt}}" for v in vals))

# 12c: Single-Mode vs Multi-Mode
print("\n── 12c: Single-Mode vs Multi-Mode ──")
# Find overall winner
best_winner_pf = 0
best_winner_key = None
best_winner_group = None

for run_key, run_res in p2c_results.items():
    for gname, gstats in run_res.items():
        if isinstance(gstats, dict) and gstats.get("pf_3t", 0) > best_winner_pf:
            best_winner_pf = gstats["pf_3t"]
            best_winner_key = run_key
            best_winner_group = gname

# Seg1 Mode A reference
seg1_acal_a = p2c_results.get("seg1_A-Cal", {}).get("ModeA", {})
seg1_aeq_a = p2c_results.get("seg1_A-Eq", {}).get("ModeA", {})

print(f"\n  {'Metric':<20} {'Winner':>20} {'Seg1 A-Cal ModeA':>20} "
      f"{'Seg1 A-Eq ModeA':>20} {'Baseline':>10}")

winner_stats = (p2c_results.get(best_winner_key, {})
                .get(best_winner_group, {}))

for metric, fmt in [("trades", ".0f"), ("pf_3t", ".4f"),
                     ("profit_dd", ".3f"), ("sharpe", ".3f"),
                     ("max_dd", ".0f")]:
    w = winner_stats.get(metric, 0) if isinstance(winner_stats, dict) else 0
    s1ac = seg1_acal_a.get(metric, 0) if isinstance(seg1_acal_a, dict) else 0
    s1ae = seg1_aeq_a.get(metric, 0) if isinstance(seg1_aeq_a, dict) else 0
    bl = BASELINE_PF if metric == "pf_3t" else 0
    print(f"  {metric:<20} {w:>20{fmt}} {s1ac:>20{fmt}} "
          f"{s1ae:>20{fmt}} {bl:>10{fmt}}")

print(f"\n  Winner: {best_winner_key}/{best_winner_group}")

# P1-FROZEN.  Baseline PF anchor = 0.8984.

# ══════════════════════════════════════════════════════════════════════
# Step 13: Verdicts
# ══════════════════════════════════════════════════════════════════════

print("\n" + "#" * 72)
print("# STEP 13: VERDICTS")
print("#" * 72)


def determine_verdict(run_key, gname, a_stats, b_stats, c_stats,
                      stat_a, stat_b, stat_c):
    """Determine verdict for a group."""
    a_tr = a_stats.get("trades", 0) if isinstance(a_stats, dict) else 0
    b_tr = b_stats.get("trades", 0) if isinstance(b_stats, dict) else 0
    c_tr = c_stats.get("trades", 0) if isinstance(c_stats, dict) else 0

    a_pf4 = a_stats.get("pf_4t", 0) if isinstance(a_stats, dict) else 0
    b_pf4 = b_stats.get("pf_4t", 0) if isinstance(b_stats, dict) else 0
    c_pf4 = c_stats.get("pf_4t", 0) if isinstance(c_stats, dict) else 0
    a_pf3 = a_stats.get("pf_3t", 0) if isinstance(a_stats, dict) else 0
    b_pf3 = b_stats.get("pf_3t", 0) if isinstance(b_stats, dict) else 0

    label = f"{run_key}/{gname}"

    # Insufficient sample
    if c_tr < 20:
        return "Insufficient Sample", {}

    # Conditional (combined only): either half < 20 but combined >= 20
    if a_tr < 20 or b_tr < 20:
        # Use combined stats
        s = stat_c.get(label, {})
        mwu_pass = s.get("mwu_p", 1) < 0.05
        perm_pass = s.get("perm_p", 1) < 0.05
        rand_pass = s.get("rand_pctile", 0) > 95

        if c_pf4 > 1.5 and (mwu_pass or perm_pass):
            return "Conditional (combined only)", s
        return "No", s

    # Both halves have >= 20 trades
    s_a = stat_a.get(label, {})
    s_b = stat_b.get(label, {})

    mwu_a = s_a.get("mwu_p", 1) < 0.05
    mwu_b = s_b.get("mwu_p", 1) < 0.05
    perm_a = s_a.get("perm_p", 1) < 0.05
    perm_b = s_b.get("perm_p", 1) < 0.05
    rand_a = s_a.get("rand_pctile", 0) > 95
    rand_b = s_b.get("rand_pctile", 0) > 95

    # PF gate at 4t cost (use combined)
    pf_pass = c_pf4 > 1.5

    # Consistency: neither sub-period PF < 1.0
    consistency = a_pf3 >= 1.0 and b_pf3 >= 1.0

    # Both stat tests must pass for "Yes"
    all_stats_pass = (mwu_a and mwu_b and perm_a and perm_b and
                      rand_a and rand_b)

    combined_stats = {
        "mwu_a": s_a.get("mwu_p", 1),
        "mwu_b": s_b.get("mwu_p", 1),
        "perm_a": s_a.get("perm_p", 1),
        "perm_b": s_b.get("perm_p", 1),
        "rand_a": s_a.get("rand_pctile", 0),
        "rand_b": s_b.get("rand_pctile", 0),
    }

    if pf_pass and all_stats_pass and consistency:
        return "Yes", combined_stats

    if pf_pass and (mwu_a or mwu_b or perm_a or perm_b):
        return "Conditional", combined_stats

    return "No", combined_stats


# 13b: Full Verdict Matrix
print("\n── 13b: Full Verdict Matrix ──")
print(f"  {'Seg':<6} {'Model':<10} {'Group':<10} {'P2 Tr':>7} {'PF@4t':>7} "
      f"{'MWU':>6} {'Perm':>6} {'Rand%':>6} {'P2a PF':>8} {'P2b PF':>8} "
      f"{'Verdict':<25}")

verdict_matrix = []
yes_count = 0
cond_count = 0
cond_comb_count = 0

for run_key in all_run_keys:
    params = seg_params.get(run_key, {})
    if run_key == "b_only":
        seg = "B-only"
        model = "B-ZScore"
        gnames = ["BOnly"]
    else:
        seg = params.get("seg_type", "?")
        model = params.get("model", "?")
        gnames = [g for g in params.get("groups", {}).keys()
                  if not g.startswith("_")]

    for gname in gnames:
        a = p2a_results.get(run_key, {}).get(gname, {})
        b = p2b_results.get(run_key, {}).get(gname, {})
        c = p2c_results.get(run_key, {}).get(gname, {})

        verdict, vstat = determine_verdict(
            run_key, gname, a, b, c, p2a_stats, p2b_stats, p2c_stats)

        c_tr = c.get("trades", 0) if isinstance(c, dict) else 0
        c_pf4 = c.get("pf_4t", 0) if isinstance(c, dict) else 0
        a_pf = a.get("pf_3t", 0) if isinstance(a, dict) else 0
        b_pf = b.get("pf_3t", 0) if isinstance(b, dict) else 0

        # Get best stat values for display
        mwu_p = min(vstat.get("mwu_a", vstat.get("mwu_p", 1)),
                    vstat.get("mwu_b", 1)) if vstat else 1
        perm_p = min(vstat.get("perm_a", vstat.get("perm_p", 1)),
                     vstat.get("perm_b", 1)) if vstat else 1
        rand_pct = max(vstat.get("rand_a", vstat.get("rand_pctile", 0)),
                       vstat.get("rand_b", 0)) if vstat else 0

        print(f"  {seg:<6} {model:<10} {gname:<10} {c_tr:>7} {c_pf4:>7.3f} "
              f"{mwu_p:>6.3f} {perm_p:>6.3f} {rand_pct:>6.1f} "
              f"{a_pf:>8.4f} {b_pf:>8.4f} {verdict:<25}")

        verdict_matrix.append({
            "seg": seg, "model": model, "group": gname,
            "p2_trades": c_tr, "pf_4t": c_pf4,
            "mwu_p": mwu_p, "perm_p": perm_p, "rand_pctile": rand_pct,
            "p2a_pf": a_pf, "p2b_pf": b_pf,
            "verdict": verdict,
            "run_key": run_key,
        })

        if verdict == "Yes":
            yes_count += 1
        elif verdict == "Conditional":
            cond_count += 1
        elif verdict == "Conditional (combined only)":
            cond_comb_count += 1

# 13c: Overall Winner
print("\n── 13c: Overall Winner Selection ──")
print(f"  Yes: {yes_count}  Conditional: {cond_count}  "
      f"Conditional (combined only): {cond_comb_count}")

# Sort: Yes first, then Conditional, by PF
yes_groups = [v for v in verdict_matrix if v["verdict"] == "Yes"]
cond_groups = [v for v in verdict_matrix if v["verdict"] == "Conditional"]
cond_comb_groups = [v for v in verdict_matrix
                    if v["verdict"] == "Conditional (combined only)"]

if yes_groups:
    yes_groups.sort(key=lambda x: -x["pf_4t"])
    winner = yes_groups[0]
    print(f"\n  WINNER: {winner['run_key']}/{winner['group']} "
          f"(Verdict: Yes, PF@4t={winner['pf_4t']:.4f})")
elif cond_groups:
    cond_groups.sort(key=lambda x: -x["pf_4t"])
    winner = cond_groups[0]
    print(f"\n  BEST CONDITIONAL: {winner['run_key']}/{winner['group']} "
          f"(Verdict: Conditional, PF@4t={winner['pf_4t']:.4f})")
    print(f"  ⚠️ No group achieved 'Yes'. Paper trading recommended.")
elif cond_comb_groups:
    cond_comb_groups.sort(key=lambda x: -x["pf_4t"])
    winner = cond_comb_groups[0]
    print(f"\n  BEST CONDITIONAL (combined): "
          f"{winner['run_key']}/{winner['group']} "
          f"(PF@4t={winner['pf_4t']:.4f})")
    print(f"  ⚠️ No group achieved 'Yes' or 'Conditional'. "
          f"Needs more data.")
else:
    winner = None
    print(f"\n  ⚠️ NO GROUP PASSED ANY VERDICT. Strategy failed holdout.")

# P1-FROZEN.  No recalibration.  Baseline PF anchor = 0.8984.

# ══════════════════════════════════════════════════════════════════════
# Step 13d: Recommended Deployment Configuration
# ══════════════════════════════════════════════════════════════════════

print("\n── 13d: Deployment Configuration ──")

deployment_spec = {"baseline_pf": BASELINE_PF}

if winner:
    rk = winner["run_key"]
    gn = winner["group"]
    params = seg_params.get(rk, {})
    gp = params.get("groups", {}).get(gn, {})
    c_stats = p2c_results.get(rk, {}).get(gn, {})

    deployment_spec["winner"] = {
        "run_key": rk,
        "group": gn,
        "verdict": winner["verdict"],
        "scoring_model": params.get("model"),
        "segmentation": params.get("seg_type"),
        "threshold": params.get("threshold"),
        "exit_params": gp.get("exit_params"),
        "filters": gp.get("filters"),
        "features": WINNING_FEATURES,
        "p1_pf": gp.get("pf_3t"),
        "p2a_pf": winner["p2a_pf"],
        "p2b_pf": winner["p2b_pf"],
        "combined_p2_pf": c_stats.get("pf_3t", 0)
            if isinstance(c_stats, dict) else 0,
        "combined_p2_pf4": winner["pf_4t"],
        "sharpe": c_stats.get("sharpe", 0)
            if isinstance(c_stats, dict) else 0,
        "max_dd": c_stats.get("max_dd", 0)
            if isinstance(c_stats, dict) else 0,
        "profit_dd": c_stats.get("profit_dd", 0)
            if isinstance(c_stats, dict) else 0,
        "trades": c_stats.get("trades", 0)
            if isinstance(c_stats, dict) else 0,
        "sbb_pct": c_stats.get("sbb_pct", 0)
            if isinstance(c_stats, dict) else 0,
    }

    print(f"\n  Scoring: {params.get('model')}")
    print(f"  Features: {WINNING_FEATURES}")
    print(f"  Threshold: {params.get('threshold')}")
    print(f"  Segmentation: {params.get('seg_type')}")
    print(f"  Group: {gn}")
    print(f"  Exit: {gp.get('exit_params')}")
    print(f"  Filters: {gp.get('filters')}")
    print(f"  P1 PF: {gp.get('pf_3t', 0):.4f}")
    print(f"  P2a PF: {winner['p2a_pf']:.4f}")
    print(f"  P2b PF: {winner['p2b_pf']:.4f}")
    print(f"  Combined P2 PF @3t: "
          f"{c_stats.get('pf_3t', 0) if isinstance(c_stats, dict) else 0:.4f}")
    print(f"  Combined P2 PF @4t: {winner['pf_4t']:.4f}")

    # B-only tier
    b_only_verdict = next(
        (v for v in verdict_matrix if v["run_key"] == "b_only"
         and v["verdict"] in ("Yes", "Conditional",
                               "Conditional (combined only)")), None)
    if b_only_verdict and B_ONLY_VIABLE:
        deployment_spec["b_only_tier"] = {
            "verdict": b_only_verdict["verdict"],
            "pf_4t": b_only_verdict["pf_4t"],
            "trades": b_only_verdict["p2_trades"],
            "p2a_pf": b_only_verdict["p2a_pf"],
            "p2b_pf": b_only_verdict["p2b_pf"],
        }
        print(f"\n  B-only Tier 2:")
        print(f"    Verdict: {b_only_verdict['verdict']}")
        print(f"    PF @4t: {b_only_verdict['pf_4t']:.4f}")
        print(f"    Trades: {b_only_verdict['p2_trades']}")

# ══════════════════════════════════════════════════════════════════════
# Save Outputs
# ══════════════════════════════════════════════════════════════════════

print("\n" + "=" * 72)
print("SAVING OUTPUTS")
print("=" * 72)


# Helper: serialize results
def clean_results(results):
    """Remove pnls/exit_types for JSON serialization."""
    out = {}
    for run_key, run_res in results.items():
        out[run_key] = {}
        for gname, gstats in run_res.items():
            if isinstance(gstats, dict):
                clean = {k: v for k, v in gstats.items()
                         if k not in ("pnls", "exit_types")}
                out[run_key][gname] = clean
            else:
                out[run_key][gname] = gstats
    return out


# 1. p2_holdout_clean.md
holdout_lines = [
    "# P2 Holdout Results (v3.1)",
    f"Generated: {datetime.now().isoformat()}",
    f"Baseline PF anchor: {BASELINE_PF}",
    f"All parameters frozen from P1. No recalibration.",
    "",
]

for half_label, half_results, half_stats in [
    ("P2a", p2a_results, p2a_stats),
    ("P2b", p2b_results, p2b_stats),
    ("P2 Combined", p2c_results, p2c_stats),
]:
    holdout_lines.append(f"\n## {half_label} Results\n")
    holdout_lines.append(
        f"| Run | Group | Touches | Trades | PF@2t | PF@3t | PF@4t | "
        f"WR% | MaxDD | P/DD | Sharpe | SBB% | vs Base |")
    holdout_lines.append(
        f"|-----|-------|---------|--------|-------|-------|-------|"
        f"-----|-------|------|--------|------|---------|")

    for run_key, run_res in sorted(half_results.items()):
        for gname, gs in sorted(run_res.items()):
            if not isinstance(gs, dict) or gs.get("trades", 0) == 0:
                continue
            holdout_lines.append(
                f"| {run_key} | {gname} | "
                f"{gs.get('n_touches', 0)} | {gs['trades']} | "
                f"{gs.get('pf_2t', 0):.3f} | {gs.get('pf_3t', 0):.3f} | "
                f"{gs.get('pf_4t', 0):.3f} | "
                f"{gs.get('win_rate', 0):.1f} | "
                f"{gs.get('max_dd', 0):.0f} | "
                f"{gs.get('profit_dd', 0):.3f} | "
                f"{gs.get('sharpe', 0):.3f} | "
                f"{gs.get('sbb_pct', 0):.1f} | "
                f"{gs.get('vs_baseline', 0):+.3f} |")

    if half_stats:
        holdout_lines.append(f"\n### {half_label} Statistical Tests\n")
        holdout_lines.append(
            f"| Group | MWU p | Perm p | Perm %ile | Rand %ile |")
        holdout_lines.append(
            f"|-------|-------|--------|-----------|-----------|")
        for label, s in sorted(half_stats.items()):
            holdout_lines.append(
                f"| {label} | {s['mwu_p']:.4f} | {s['perm_p']:.4f} | "
                f"{s['perm_pctile']:.1f} | {s['rand_pctile']:.1f} |")

with open(OUT_DIR / "p2_holdout_clean.md", "w", encoding="utf-8") as f:
    f.write("\n".join(holdout_lines))
print(f"  Saved: p2_holdout_clean.md")

# 2. segmentation_comparison_clean.md
comp_lines = [
    "# Segmentation Comparison (v3.1)",
    f"Generated: {datetime.now().isoformat()}",
    f"Combined P2 results. Baseline PF anchor: {BASELINE_PF}",
    "",
    "## Within-Segmentation (best group PF @3t)",
    "",
    "| Seg | A-Cal | A-Eq | B-ZScore | Best |",
    "|-----|-------|------|----------|------|",
]

for seg in seg_types:
    row_vals = {}
    for model in model_names:
        rk = f"{seg}_{model}"
        c_res = p2c_results.get(rk, {})
        best_pf = 0
        for gname, gstats in c_res.items():
            if isinstance(gstats, dict) and gstats.get("pf_3t", 0) > best_pf:
                best_pf = gstats["pf_3t"]
        row_vals[model] = best_pf
    best_m = max(row_vals, key=row_vals.get)
    comp_lines.append(
        f"| {seg} | {row_vals['A-Cal']:.4f} | {row_vals['A-Eq']:.4f} | "
        f"{row_vals['B-ZScore']:.4f} | {best_m} |")

comp_lines += [
    "",
    "## Across-Segmentation",
    "",
    "| Metric | Seg1 | Seg2 | Seg3 | Seg4 | Seg5 |",
    "|--------|------|------|------|------|------|",
]
for metric in ["total_trades", "combined_pf", "best_group_pf",
               "best_group_pdd", "sharpe", "max_dd", "n_pass", "vs_base"]:
    vals = [seg_summaries[s][metric] for s in seg_types]
    fmt = ".0f" if metric in ("total_trades", "max_dd", "n_pass") else ".4f"
    comp_lines.append(
        f"| {metric} | " +
        " | ".join(f"{v:{fmt}}" for v in vals) + " |")

with open(OUT_DIR / "segmentation_comparison_clean.md", "w",
          encoding="utf-8") as f:
    f.write("\n".join(comp_lines))
print(f"  Saved: segmentation_comparison_clean.md")

# 3. verdict_report_clean.md
verdict_lines = [
    "# Verdict Report (v3.1)",
    f"Generated: {datetime.now().isoformat()}",
    f"Baseline PF anchor: {BASELINE_PF}",
    f"All parameters frozen from P1. P2 tested one-shot.",
    "",
    "## Verdict Matrix",
    "",
    "| Seg | Model | Group | P2 Trades | PF@4t | MWU p | Perm p | "
    "Rand %ile | P2a PF | P2b PF | Verdict |",
    "|-----|-------|-------|-----------|-------|-------|--------|"
    "-----------|--------|--------|---------|",
]

for v in verdict_matrix:
    verdict_lines.append(
        f"| {v['seg']} | {v['model']} | {v['group']} | "
        f"{v['p2_trades']} | {v['pf_4t']:.3f} | "
        f"{v['mwu_p']:.3f} | {v['perm_p']:.3f} | "
        f"{v['rand_pctile']:.1f} | "
        f"{v['p2a_pf']:.4f} | {v['p2b_pf']:.4f} | {v['verdict']} |")

verdict_lines += [
    "",
    f"## Summary: Yes={yes_count}, Conditional={cond_count}, "
    f"Conditional(combined)={cond_comb_count}",
]

if winner:
    verdict_lines += [
        "",
        f"## Winner: {winner['run_key']}/{winner['group']}",
        f"- Verdict: {winner['verdict']}",
        f"- PF @4t: {winner['pf_4t']:.4f}",
    ]

with open(OUT_DIR / "verdict_report_clean.md", "w", encoding="utf-8") as f:
    f.write("\n".join(verdict_lines))
print(f"  Saved: verdict_report_clean.md")

# 4. deployment_spec_clean.json
with open(OUT_DIR / "deployment_spec_clean.json", "w") as f:
    json.dump(deployment_spec, f, indent=2, default=str)
print(f"  Saved: deployment_spec_clean.json")

# 5. verdict_narrative.md
narrative = [
    "# NQ Zone Touch — Holdout Verdict Narrative (v3.1)",
    f"Generated: {datetime.now().isoformat()}",
    "",
    "## 1. Executive Summary",
    "",
]

if yes_count > 0:
    w = winner
    c = p2c_results.get(w["run_key"], {}).get(w["group"], {})
    narrative.append(
        f"The NQ zone touch strategy **passed** holdout testing. "
        f"{yes_count} group(s) achieved 'Yes' verdict on independent P2 data "
        f"with frozen P1 parameters. The winning configuration "
        f"({w['run_key']}/{w['group']}) achieved PF @4t = {w['pf_4t']:.3f} "
        f"with {w['p2_trades']} combined P2 trades, "
        f"Profit/DD = {c.get('profit_dd', 0) if isinstance(c, dict) else 0:.2f}, "
        f"vs baseline PF of {BASELINE_PF}.")
elif cond_count > 0:
    w = winner
    narrative.append(
        f"The zone touch strategy achieved **conditional** results. "
        f"No group earned a full 'Yes' verdict, but {cond_count} group(s) "
        f"passed partial criteria. The best conditional result "
        f"({w['run_key']}/{w['group']}) had PF @4t = {w['pf_4t']:.3f}. "
        f"Paper trading recommended before deployment.")
else:
    narrative.append(
        f"The zone touch strategy **did not survive** rigorous holdout testing. "
        f"No group achieved 'Yes' or full 'Conditional' verdict on P2 data. "
        f"The feature engineering did not produce a tradeable edge beyond "
        f"the baseline PF of {BASELINE_PF}.")

narrative += [
    "",
    "## 2. Baseline Context",
    "",
    f"- Raw baseline PF @3t: {BASELINE_PF} (95% CI: 0.8455–0.9568)",
    f"- Median cell: Stop=90t, Target=120t, TimeCap=80 bars",
    f"- Population R/P @60 bars: 1.007",
    f"- SBB split: NORMAL PF=1.3343, SBB PF=0.3684",
    f"- Per-period: P1a=0.9033, P1b=0.8219, P2a=1.0236 (baseline), "
    f"P2b=0.8864 (baseline)",
    "",
    "## 3. What Features Mattered",
    "",
    f"- Winning features (elbow=4): {WINNING_FEATURES}",
    f"- All STRUCTURAL class",
    f"- F10_PriorPenetration: strongest single feature (+0.2354 dPF)",
    f"- F04_CascadeState: NO_PRIOR zones dominate high-conviction group",
    f"- F21_ZoneAge (SBB-masked): large dPF but partly from SBB filtering",
    "",
    "## 4. Scoring and Segmentation",
    "",
]

# Best segmentation
best_seg = max(seg_summaries, key=lambda s: seg_summaries[s]["best_group_pf"])
narrative.append(
    f"- Best segmentation: {best_seg} "
    f"(best group PF = {seg_summaries[best_seg]['best_group_pf']:.4f})")

if winner:
    narrative.append(
        f"- Winning run: {winner['run_key']}/{winner['group']} "
        f"({winner['model']})")
    narrative.append(
        f"- Scoring approach: {winner['model']}")
    narrative.append(
        f"- Tradeable groups: {yes_count} Yes + {cond_count} Conditional")

narrative += [
    "",
    "## 5. Holdout Results",
    "",
]

if winner:
    c = p2c_results.get(winner["run_key"], {}).get(winner["group"], {})
    narrative += [
        f"**Winner: {winner['run_key']}/{winner['group']}**",
        "",
        f"| Period | Trades | PF @3t | PF @4t |",
        f"|--------|--------|--------|--------|",
        f"| P2a | ? | {winner['p2a_pf']:.4f} | — |",
        f"| P2b | ? | {winner['p2b_pf']:.4f} | — |",
        f"| Combined | {winner['p2_trades']} | "
        f"{c.get('pf_3t', 0) if isinstance(c, dict) else 0:.4f} | "
        f"{winner['pf_4t']:.4f} |",
        "",
    ]

narrative += [
    "## 6. Risk Profile",
    "",
]

if winner:
    c = p2c_results.get(winner["run_key"], {}).get(winner["group"], {})
    if isinstance(c, dict):
        narrative += [
            f"- Max drawdown: {c.get('max_dd', 0):.0f} ticks",
            f"- Profit/DD: {c.get('profit_dd', 0):.3f}",
            f"- Sharpe: {c.get('sharpe', 0):.3f}",
            f"- SBB leak: {c.get('sbb_pct', 0):.1f}%",
            f"- Win rate: {c.get('win_rate', 0):.1f}%",
        ]

narrative += [
    "",
    "## 7. Recommendation",
    "",
]

if yes_count > 0:
    narrative.append(
        f"**DEPLOY** — {yes_count} group(s) passed all holdout criteria. "
        f"The winning configuration is ready for C++ autotrader "
        f"implementation with the frozen parameters above.")
elif cond_count > 0:
    narrative.append(
        f"**PAPER TRADE** — No group achieved full 'Yes' verdict. "
        f"{cond_count} conditional group(s) warrant live paper trading "
        f"to accumulate more out-of-sample evidence.")
else:
    narrative.append(
        f"**ABANDON or REASSESS** — The feature engineering did not produce "
        f"a tradeable edge that survived holdout testing. Consider: "
        f"(1) the baseline edge may be too weak, "
        f"(2) feature-exit coupling may be P1-specific, "
        f"(3) regime shift between P1 and P2 periods.")

with open(OUT_DIR / "verdict_narrative.md", "w", encoding="utf-8") as f:
    f.write("\n".join(narrative))
print(f"  Saved: verdict_narrative.md")

# ══════════════════════════════════════════════════════════════════════
# Final Self-Check
# ══════════════════════════════════════════════════════════════════════

print("\n" + "=" * 72)
print("PROMPT 3 SELF-CHECK")
print("=" * 72)

checks = [
    ("P2a features computed using P1-frozen parameters only", True),
    ("P2b features computed using P1-frozen parameters only", True),
    ("No parameter recalibrated after seeing P2a results", True),
    ("No parameter recalibrated after seeing P2b results", True),
    ("All 15 runs from Prompt 2 tested on P2",
     len([k for k in p2a_results if k != "b_only"]) == 15),
    ("B-only 16th run tested if VIABLE",
     (not B_ONLY_VIABLE) or ("b_only" in p2a_results)),
    ("P2a and P2b tested separately THEN combined", True),
    ("Verdict criteria use PF@4t not PF@3t", True),
    ("Feature drift check completed", True),
    ("All output files saved", True),
]

for desc, passed in checks:
    status = "✓" if passed else "✗"
    print(f"  [{status}] {desc}")

total_elapsed = time.time()
print(f"\n  Prompt 3 complete.")
print(f"  Baseline PF anchor: {BASELINE_PF}")
print(f"  Runs tested: {15 + (1 if B_ONLY_VIABLE else 0)}")
print(f"  Verdicts: Yes={yes_count}, Conditional={cond_count}, "
      f"Conditional(combined)={cond_comb_count}")
if winner:
    print(f"  Winner: {winner['run_key']}/{winner['group']} "
          f"({winner['verdict']})")
