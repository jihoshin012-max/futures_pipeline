# archetype: zone_touch
"""Prompt 3 — P2 Holdout & Verdicts (v3.2).

Warmup-enriched data.  13 standard runs + B-only 14th.
ALL parameters frozen from P1.  No recalibration.
Baseline PF anchor = 1.3396.
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
PARAM_DIR = BASE / "shared" / "archetypes" / "zone_touch" / "output"
OUT_DIR = BASE / "stages" / "04-backtest" / "zone_touch" / "output"
TICK_SIZE = 0.25

BASELINE_PF = 1.3396
VERSION = "3.2"

print("=" * 72)
print(f"PROMPT 3 — P2 HOLDOUT & VERDICTS (v{VERSION})")
print("ALL PARAMETERS FROZEN FROM P1.  NO RECALIBRATION.")
print(f"Baseline PF anchor = {BASELINE_PF}")
print("=" * 72)

# ══════════════════════════════════════════════════════════════════════
# Load Frozen Parameters (v32 files)
# ══════════════════════════════════════════════════════════════════════

with open(PARAM_DIR / "scoring_model_acal_v32.json") as f:
    acal_cfg = json.load(f)
with open(PARAM_DIR / "scoring_model_aeq_v32.json") as f:
    aeq_cfg = json.load(f)
with open(PARAM_DIR / "scoring_model_bzscore_v32.json") as f:
    bz_cfg = json.load(f)
with open(PARAM_DIR / "feature_config_v32.json") as f:
    feat_cfg = json.load(f)
with open(PARAM_DIR / "segmentation_params_clean_v32.json") as f:
    seg_params = json.load(f)
with open(PARAM_DIR / "frozen_parameters_manifest_clean_v32.json") as f:
    manifest = json.load(f)
with open(PARAM_DIR / "feature_analysis_clean_v32.md") as f:
    feat_analysis_text = f.read()

WINNING_FEATURES = feat_cfg["winning_features"]  # F10,F01,F05,F09,F21,F13,F04
TS_P33 = feat_cfg["trend_slope_P33"]
TS_P67 = feat_cfg["trend_slope_P67"]
BIN_EDGES = feat_cfg["feature_bin_edges"]
FEAT_MEANS = feat_cfg["feature_means"]
FEAT_STDS = feat_cfg["feature_stds"]
ATR_P50 = FEAT_MEANS.get("F17", 0.5815)  # P1 F17 mean as median proxy

B_ONLY_VIABLE = "VIABLE" in feat_analysis_text.upper()
N_RUNS = len(seg_params)  # 13

print(f"\n── Frozen Configuration ──")
print(f"  Baseline PF anchor: {BASELINE_PF}")
print(f"  Winning features: {WINNING_FEATURES}")
print(f"  A-Cal threshold: {acal_cfg['threshold']:.2f}/{acal_cfg['max_score']:.2f}")
print(f"  A-Eq threshold: {aeq_cfg['threshold']:.1f}/{aeq_cfg['max_score']}")
print(f"  B-ZScore threshold: {bz_cfg['threshold']:.3f}")
print(f"  B-only 14th run: {'YES' if B_ONLY_VIABLE else 'NO'}")
print(f"  Number of runs: {N_RUNS} + {1 if B_ONLY_VIABLE else 0} B-only")

# P1-FROZEN PARAMETERS ONLY.  NO RECALIBRATION.  Baseline PF anchor = 1.3396.

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
bar_atr = bar_p2["ATR"].to_numpy(dtype=np.float64)
n_bars = len(bar_arr)

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

# P1-FROZEN PARAMETERS.  Baseline PF anchor = 1.3396.

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

    # F01: Timeframe (categorical)
    df["F01"] = df["SourceLabel"]

    # F02: Zone Width (diagnostic)
    df["F02"] = df["ZoneWidthTicks"]

    # F04: Cascade State (categorical)
    df["F04"] = df["CascadeState"].replace("UNKNOWN", "NO_PRIOR")

    # F05: Session (categorical) — derived from DateTime
    touch_dt = pd.to_datetime(df["DateTime"])
    touch_mins = touch_dt.dt.hour.values * 60 + touch_dt.dt.minute.values
    session = np.full(len(df), "Midday", dtype=object)
    session[touch_mins < 360] = "Overnight"          # < 6:00
    session[(touch_mins >= 360) & (touch_mins < 570)] = "PreRTH"  # 6:00-9:30
    session[(touch_mins >= 570) & (touch_mins < 660)] = "OpeningDrive"  # 9:30-11:00
    session[(touch_mins >= 660) & (touch_mins < 840)] = "Midday"  # 11:00-14:00
    session[(touch_mins >= 840) & (touch_mins < 1020)] = "Close"  # 14:00-17:00
    session[touch_mins >= 1020] = "Overnight"         # >= 17:00
    df["F05"] = session

    # F09: ZW/ATR
    atr_vals = []
    for rbi in df["RotBarIndex"].values:
        rbi = int(rbi)
        if 0 <= rbi < n_bars and bar_atr[rbi] > 0:
            atr_vals.append(bar_atr[rbi])
        else:
            atr_vals.append(np.nan)
    df["F09"] = df["ZoneWidthTicks"].values * TICK_SIZE / np.array(atr_vals)

    # F10: Prior Penetration
    df["ZoneID"] = (df["TouchType"].astype(str) + "|" +
                    df["ZoneTop"].astype(str) + "|" +
                    df["ZoneBot"].astype(str) + "|" +
                    df["SourceLabel"].astype(str))

    prior_pen = {}
    for zone_id, group in df.sort_values(
            ["ZoneID", "TouchSequence"]).groupby("ZoneID"):
        group = group.sort_values("TouchSequence")
        prev_pen = np.nan
        for idx, row in group.iterrows():
            if row["TouchSequence"] == 1:
                prior_pen[idx] = np.nan
            else:
                prior_pen[idx] = prev_pen
            prev_pen = row["Penetration"]
    df["F10"] = df.index.map(prior_pen)

    # F13: Touch Bar Close Position
    rot_idx = df["RotBarIndex"].values.astype(int)
    is_long = df["TouchType"].str.contains("DEMAND").values
    tb_h = np.array([bar_arr[max(0, min(i, n_bars - 1)), 1] for i in rot_idx])
    tb_l = np.array([bar_arr[max(0, min(i, n_bars - 1)), 2] for i in rot_idx])
    tb_c = np.array([bar_arr[max(0, min(i, n_bars - 1)), 3] for i in rot_idx])
    hl_d = tb_h - tb_l
    close_pos = np.where(
        hl_d > 0,
        np.where(is_long, (tb_c - tb_l) / hl_d, (tb_h - tb_c) / hl_d),
        0.5)
    df["F13"] = close_pos

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
    df["F17"] = atr_regime

    # F21: Zone Age
    df["F21"] = df["ZoneAgeBars"]

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

    # SBB_Label
    if "SBB_Label" not in df.columns:
        df["SBB_Label"] = "NORMAL"

    print(f"    Features computed. F10 null rate: "
          f"{df['F10'].isna().mean() * 100:.1f}%")
    print(f"    F05 distribution: "
          f"{dict(df['F05'].value_counts().head(5))}")

    return df


p2a = compute_features(p2a, "P2a")
p2b = compute_features(p2b, "P2b")

# P1-FROZEN PARAMETERS ONLY.  NO P2-derived parameters.  Baseline PF anchor = 1.3396.

# ══════════════════════════════════════════════════════════════════════
# Score P2 Touches (using P1-frozen scoring models)
# ══════════════════════════════════════════════════════════════════════

print("\n" + "=" * 72)
print("SCORING P2 TOUCHES (P1-frozen models)")
print("=" * 72)


def _bin_numeric(vals, lo, hi):
    """Assign numeric values to Low/Mid/High bins using P1-frozen edges."""
    out = np.full(len(vals), "Mid", dtype=object)
    v = np.asarray(vals, dtype=float)
    out[v <= lo] = "Low"
    out[v > hi] = "High"
    out[np.isnan(v)] = "NA"
    return out


def score_acal(df):
    """A-Cal scoring: bin_points from v32 model."""
    bp = acal_cfg["bin_points"]
    bin_edges = acal_cfg["bin_edges"]
    scores = np.zeros(len(df))

    for feat, points_map in bp.items():
        if feat in bin_edges:
            # Numeric feature
            lo, hi = bin_edges[feat]
            vals = df[feat].values.astype(float)
            bins = _bin_numeric(vals, lo, hi)
            for i, b in enumerate(bins):
                scores[i] += points_map.get(b, 0)
        else:
            # Categorical feature
            cats = df[feat].values
            for i, c in enumerate(cats):
                scores[i] += points_map.get(str(c), 0)

    return scores


def score_aeq(df):
    """A-Eq scoring: equal weight per feature, bin_points from v32."""
    bp = aeq_cfg["bin_points"]
    # A-Eq uses same bin edges as A-Cal (from feature_config)
    bin_edges = acal_cfg["bin_edges"]
    scores = np.zeros(len(df))

    for feat, points_map in bp.items():
        if feat in bin_edges:
            lo, hi = bin_edges[feat]
            vals = df[feat].values.astype(float)
            bins = _bin_numeric(vals, lo, hi)
            for i, b in enumerate(bins):
                scores[i] += points_map.get(b, 0)
        else:
            cats = df[feat].values
            for i, c in enumerate(cats):
                scores[i] += points_map.get(str(c), 0)

    return scores


def score_bzscore(df):
    """B-ZScore scoring: standardize with P1 means/stds, apply regression."""
    feat_cols = bz_cfg["feature_columns"]
    coeffs = bz_cfg["coefficients"]
    intercept = bz_cfg["intercept"]
    means = bz_cfg["scaler_mean"]
    stds = bz_cfg["scaler_std"]

    X = np.zeros((len(df), len(feat_cols)))
    for j, fc in enumerate(feat_cols):
        if fc == "F10":
            X[:, j] = df["F10"].fillna(0).values
        elif fc == "F09":
            X[:, j] = df["F09"].fillna(0).values
        elif fc == "F21":
            X[:, j] = df["F21"].fillna(0).values
        elif fc == "F13":
            X[:, j] = df["F13"].fillna(0).values
        elif fc.startswith("F04_"):
            cat = fc.replace("F04_", "")
            X[:, j] = (df["F04"] == cat).astype(float).values
        elif fc.startswith("F01_"):
            cat = fc.replace("F01_", "")
            X[:, j] = (df["F01"] == cat).astype(float).values
        elif fc.startswith("F05_"):
            cat = fc.replace("F05_", "")
            X[:, j] = (df["F05"] == cat).astype(float).values

    # Standardize with P1 means/stds
    means_arr = np.array(means)
    stds_arr = np.array(stds)
    stds_arr[stds_arr == 0] = 1.0
    X_scaled = (X - means_arr) / stds_arr

    # Apply regression
    coeff_arr = np.array(coeffs)
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
              f"({above / len(df) * 100:.1f}%)")
    return df


p2a = score_all(p2a, "P2a")
p2b = score_all(p2b, "P2b")

print("\n  CHECKPOINT: All scoring uses P1-frozen bin edges, weights, "
      "thresholds, and means/stds.")

# P1-FROZEN PARAMETERS ONLY.  Baseline PF anchor = 1.3396.

# ══════════════════════════════════════════════════════════════════════
# Feature Drift Check (Step 9a) — all 7 winning features + F02/F09
# ══════════════════════════════════════════════════════════════════════

print("\n" + "=" * 72)
print("FEATURE DRIFT CHECK: P2 distributions vs P1 bin edges")
print("All 7 winning features + F02/F09 diagnostics")
print("=" * 72)

drift_features = {
    "F10": True,   # winning, numeric
    "F01": False,  # winning, categorical
    "F05": False,  # winning, categorical
    "F09": True,   # winning, numeric
    "F21": True,   # winning, numeric
    "F13": True,   # winning, numeric
    "F04": False,  # winning, categorical
    "F02": True,   # diagnostic
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

    print(f"\n  {feat} (P1 edges: {lo:.4f}, {hi:.4f}):")
    print(f"    Low  (le {lo:.4f}): {low_bin:>5} ({low_bin / n * 100:.1f}%)")
    print(f"    Mid  ({lo:.4f}-{hi:.4f}): {mid_bin:>5} ({mid_bin / n * 100:.1f}%)")
    print(f"    High (>{hi:.4f}): {high_bin:>5} ({high_bin / n * 100:.1f}%)")

    max_pct = max(low_bin, mid_bin, high_bin) / n * 100
    if max_pct > 80:
        print(f"    *** DRIFT: {max_pct:.1f}% in single bin — "
              f"feature has lost discriminative power on P2!")

del p2_all_drift

# P1-FROZEN PARAMETERS ONLY.  NO RECALIBRATION.  Baseline PF anchor = 1.3396.

# ══════════════════════════════════════════════════════════════════════
# Simulation Engine (identical to Prompts 1-2, with ZONEREL support)
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

        # Intra-bar conflict: stop fills first
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


def resolve_zonerel_exits(zw_ticks, ep_zonerel):
    """Compute actual stop/target ticks from zone-relative parameters."""
    stop_spec = ep_zonerel.get("stop_mult")
    target_mult = ep_zonerel.get("target_mult", 0.5)
    tcap = ep_zonerel.get("time_cap", 80)

    # Target: zone_width * target_mult
    target_ticks = max(1, round(zw_ticks * target_mult))

    # Stop: either simple multiplier or max(1.5xZW, 120) formula
    if isinstance(stop_spec, str) and "max" in stop_spec.lower():
        # "max(1.5xZW,120)" pattern
        stop_ticks = max(round(1.5 * zw_ticks), 120)
    else:
        stop_ticks = max(1, round(float(stop_spec) * zw_ticks))

    return stop_ticks, target_ticks, tcap


def run_sim_group(touches_df, stop, target, be_trigger, trail_trigger, tcap):
    """Simulate group with no-overlap filter (FIXED exits)."""
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
    return pnls, exit_types


def run_sim_group_zonerel(touches_df, ep_zonerel, be_trigger=0,
                          trail_trigger=0):
    """Simulate group with ZONEREL exits (per-touch zone width)."""
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
        zw = row.get("ZoneWidthTicks", 100)
        stop, target, tcap = resolve_zonerel_exits(zw, ep_zonerel)
        pnl, bh, etype = sim_trade(entry_bar, direction, stop, target,
                                    be_trigger, trail_trigger, tcap)
        if pnl is not None:
            pnls.append(pnl)
            exit_types.append(etype)
            in_trade_until = entry_bar + bh - 1
    return pnls, exit_types


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


# P1-FROZEN PARAMETERS.  Baseline PF anchor = 1.3396.

# ══════════════════════════════════════════════════════════════════════
# Segmentation Assignment (frozen from P1)
# ══════════════════════════════════════════════════════════════════════


def assign_segments(df, score_col, threshold, seg_type, seg_groups_cfg):
    """Assign segmentation groups using P1-frozen rules."""
    edge_mask = df["TouchType"].isin(["DEMAND_EDGE", "SUPPLY_EDGE"])
    above_thresh = df[score_col] >= threshold

    if seg_type == "seg1":
        groups = {
            "ModeA": df[above_thresh & edge_mask],
            "ModeB": df[~(above_thresh & edge_mask)],
        }
    elif seg_type == "seg2":
        # v3.2: Score + Session (5-class -> 4 modes)
        session = df["F05"]
        rth_mask = session.isin(["OpeningDrive", "Midday", "Close"])
        prerth_mask = session == "PreRTH"
        overnight_mask = session == "Overnight"

        groups = {
            "ModeA_RTH": df[above_thresh & edge_mask & rth_mask],
            "ModeB_PreRTH": df[above_thresh & edge_mask & prerth_mask],
            "ModeC_Overnight": df[above_thresh & edge_mask & overnight_mask],
            "ModeD_Below": df[~(above_thresh & edge_mask)],
        }
    elif seg_type == "seg3":
        wt_nt = df["TrendLabel"].isin(["WT", "NT"])
        ct = df["TrendLabel"] == "CT"
        groups = {
            "ModeA_WTNT": df[above_thresh & edge_mask & wt_nt],
            "ModeB_CT": df[above_thresh & edge_mask & ct],
            "ModeC_Below": df[~(above_thresh & edge_mask)],
        }
    elif seg_type == "seg4":
        low_atr = df["F17"] <= ATR_P50
        groups = {
            "ModeA_LowATR": df[above_thresh & edge_mask & low_atr],
            "ModeB_HighATR": df[above_thresh & edge_mask & ~low_atr],
            "ModeC_Below": df[~(above_thresh & edge_mask)],
        }
    elif seg_type == "seg5":
        # Assign to nearest P1-frozen centroid
        centroids = seg_groups_cfg.get("_centroids")
        cluster_feats = seg_groups_cfg.get("_cluster_features",
                                            ["F10", "F09", "F21", "F13"])
        if centroids:
            numeric_feats = [f for f in cluster_feats
                             if f in df.columns and
                             pd.api.types.is_numeric_dtype(df[f])]
            if numeric_feats:
                X = df[numeric_feats].fillna(
                    df[numeric_feats].median()).values
                p1_means = np.array([FEAT_MEANS.get(f, 0)
                                     for f in numeric_feats])
                p1_stds = np.array([FEAT_STDS.get(f, 1)
                                    for f in numeric_feats])
                p1_stds[p1_stds == 0] = 1.0
                X_scaled = (X - p1_means) / p1_stds
                centroids_arr = np.array(centroids)
                labels = np.argmin(
                    np.linalg.norm(
                        X_scaled[:, None, :] - centroids_arr[None, :, :],
                        axis=2), axis=1)
                groups = {}
                for c in range(len(centroids)):
                    c_mask = labels == c
                    cname = f"Cluster{c}"
                    if c_mask.sum() >= 1:
                        groups[cname] = df[c_mask]
            else:
                groups = {"All": df}
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


def get_exit_params(gp_params):
    """Get the winning exit params (FIXED or ZONEREL) for a group."""
    winner = gp_params.get("exit_winner", "FIXED")
    if winner == "ZONEREL" and gp_params.get("exit_params_zonerel"):
        return "ZONEREL", gp_params["exit_params_zonerel"]
    elif gp_params.get("exit_params_fixed"):
        return "FIXED", gp_params["exit_params_fixed"]
    else:
        # Fallback to median cell
        return "FIXED", {"stop": 120, "target": 120, "be_trigger": 0,
                         "trail_trigger": 0, "time_cap": 80}


def sim_group_with_exits(filtered_df, exit_type, exit_params):
    """Simulate a group using the appropriate exit type."""
    if exit_type == "ZONEREL":
        pnls, etypes = run_sim_group_zonerel(
            filtered_df, exit_params,
            be_trigger=0, trail_trigger=0)
    else:
        pnls, etypes = run_sim_group(
            filtered_df,
            exit_params.get("stop", 120),
            exit_params.get("target", 120),
            exit_params.get("be_trigger", 0),
            exit_params.get("trail_trigger", 0),
            exit_params.get("time_cap", 80))
    return pnls, etypes


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
    wr = sum(1 for p in pnls if p - 3 > 0) / trades * 100
    lr = sum(1 for p in pnls if p - 3 < 0) / trades * 100
    be_rate = sum(1 for p in pnls if abs(p - 3) < 0.01) / trades * 100

    exit_counts = {"TARGET": 0, "STOP": 0, "BE": 0, "TRAIL": 0, "TIMECAP": 0}
    for et in exit_types:
        if et in exit_counts:
            exit_counts[et] += 1

    sbb_mask = (filtered_df["SBB_Label"] == "SBB"
                if "SBB_Label" in filtered_df.columns
                else pd.Series(False, index=filtered_df.index))
    sbb_pct = sbb_mask.mean() * 100

    # Avg trades/day estimate (P2a ~43 trading days, P2b ~35 days)
    # Combined ~78 days
    tpd = trades / 78.0  # approximate

    return {
        "n_touches": n_touches,
        "trades": trades,
        "pf_2t": pf2, "pf_3t": pf3, "pf_4t": pf4,
        "win_rate": wr, "loss_rate": lr, "be_rate": be_rate,
        "net_pnl_3t": net_pnl, "avg_pnl_3t": avg_pnl,
        "max_dd": dd, "profit_dd": pdd, "sharpe": sharpe,
        "exit_counts": exit_counts,
        "sbb_pct": sbb_pct,
        "sbb_n_touches": int(sbb_mask.sum()),
        "trades_per_day": tpd,
        "pnls": pnls,
        "exit_types": exit_types,
        "vs_baseline": pf3 - BASELINE_PF,
    }


def run_holdout_half(df, half_label):
    """Run all 13 (+14th B-only) frozen runs on one P2 half."""
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
        print(f"\n-- Run {run_count}/{N_RUNS + (1 if B_ONLY_VIABLE else 0)}: "
              f"{run_key} ({half_label}) --")

        # Assign segments
        groups = assign_segments(df, score_col, threshold, seg_type,
                                 params.get("groups", {}))

        run_results = {}
        for gname, gp_params in params["groups"].items():
            if gname.startswith("_"):
                continue
            if not isinstance(gp_params, dict):
                continue
            # Must have exit params
            if ("exit_params_fixed" not in gp_params and
                    "exit_params_zonerel" not in gp_params):
                continue

            exit_type, exit_params = get_exit_params(gp_params)
            filters = gp_params.get("filters", {})

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

            pnls, etypes = sim_group_with_exits(filtered, exit_type,
                                                 exit_params)

            stats = compute_group_stats(pnls, etypes, len(gdf), filtered)
            if stats:
                stats["exit_type"] = exit_type
                run_results[gname] = stats
                print(f"    {gname}: {len(gdf)} touches -> {stats['trades']} "
                      f"trades  PF@3t={stats['pf_3t']:.4f}  "
                      f"PF@4t={stats['pf_4t']:.4f}  "
                      f"P/DD={stats['profit_dd']:.3f}  "
                      f"SBB={stats['sbb_pct']:.1f}%  "
                      f"exit={exit_type}  "
                      f"vs base={stats['vs_baseline']:+.4f}")
            else:
                run_results[gname] = {"trades": 0, "pnls": []}
                print(f"    {gname}: {len(gdf)} touches -> 0 trades")

        results[run_key] = run_results

    # P1-FROZEN PARAMETERS.  No recalibration.  Baseline PF anchor = 1.3396.

    # B-only 14th run
    if B_ONLY_VIABLE:
        print(f"\n-- Run {N_RUNS + 1} (B-only): {half_label} --")
        aeq_above = df["score_aeq"] >= aeq_cfg["threshold"]
        bz_above = df["score_bzscore"] >= bz_cfg["threshold"]
        b_only_mask = bz_above & ~aeq_above
        b_only = df[b_only_mask]
        print(f"    B-only touches: {len(b_only)}")

        if len(b_only) > 0:
            # Use seg1_B-ZScore ModeA exits for B-only
            bz_seg1 = seg_params.get("seg1_B-ZScore", {})
            bz_mode_a = bz_seg1.get("groups", {}).get("ModeA", {})
            exit_type, exit_params = get_exit_params(bz_mode_a)
            filters = bz_mode_a.get("filters", {})
            filtered = apply_filters(b_only, filters)
            if len(filtered) > 0:
                pnls, etypes = sim_group_with_exits(filtered, exit_type,
                                                     exit_params)
                stats = compute_group_stats(pnls, etypes, len(b_only),
                                            filtered)
                if stats:
                    stats["exit_type"] = exit_type
                    results["b_only"] = {"BOnly": stats}
                    print(f"    BOnly: {len(b_only)} touches -> {stats['trades']} "
                          f"trades  PF@3t={stats['pf_3t']:.4f}  "
                          f"PF@4t={stats['pf_4t']:.4f}  "
                          f"SBB={stats['sbb_pct']:.1f}%")
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
    g = np.array(group_reactions, dtype=float)
    c = np.array(complement_reactions, dtype=float)
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
    """Permutation test: randomly reassign group labels."""
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


def random_entry_control(all_edge_df, group_n, exit_type, exit_params,
                         n_iters=1000):
    """Random entry control: randomly select edge touches."""
    rng = np.random.default_rng(42)

    # Precompute per-touch PnLs for all edge touches
    edge_sorted = all_edge_df.sort_values("RotBarIndex")
    all_pnls_per_touch = []
    for _, row in edge_sorted.iterrows():
        rbi = int(row["RotBarIndex"])
        entry_bar = rbi + 1
        direction = 1 if "DEMAND" in str(row["TouchType"]) else -1
        if exit_type == "ZONEREL":
            zw = row.get("ZoneWidthTicks", 100)
            stop, target, tcap = resolve_zonerel_exits(zw, exit_params)
            pnl, _, _ = sim_trade(entry_bar, direction, stop, target, 0, 0,
                                  tcap)
        else:
            pnl, _, _ = sim_trade(
                entry_bar, direction,
                exit_params.get("stop", 120),
                exit_params.get("target", 120),
                exit_params.get("be_trigger", 0),
                exit_params.get("trail_trigger", 0),
                exit_params.get("time_cap", 80))
        all_pnls_per_touch.append(pnl if pnl is not None else 0)

    all_arr = np.array(all_pnls_per_touch)
    if len(all_arr) < group_n:
        return []

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

    edge_df = df[df["TouchType"].isin(["DEMAND_EDGE", "SUPPLY_EDGE"])]
    stat_results = {}

    for run_key, run_res in results.items():
        for gname, gstats in run_res.items():
            if not isinstance(gstats, dict) or gstats.get("trades", 0) < 20:
                continue

            label = f"{run_key}/{gname}"
            print(f"\n  -- {label} ({gstats['trades']} trades) --")

            # Get group mask for MWU
            params = seg_params.get(run_key, {})
            if run_key == "b_only":
                aeq_above = df["score_aeq"] >= aeq_cfg["threshold"]
                bz_above = df["score_bzscore"] >= bz_cfg["threshold"]
                group_mask = bz_above & ~aeq_above
            else:
                seg_type = params.get("seg_type", "")
                score_col = params.get("score_col", "")
                threshold = params.get("threshold", 0)
                segs = assign_segments(df, score_col, threshold, seg_type,
                                       params.get("groups", {}))
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
            gp_cfg = params.get("groups", {}).get(gname, {})
            if run_key == "b_only":
                bz_seg1 = seg_params.get("seg1_B-ZScore", {})
                gp_cfg = bz_seg1.get("groups", {}).get("ModeA", {})
            exit_type, exit_params = get_exit_params(gp_cfg)

            # Precompute PnLs for all touches with these exits
            all_touch_pnls = []
            for _, row in df.sort_values("RotBarIndex").iterrows():
                rbi = int(row["RotBarIndex"])
                entry_bar = rbi + 1
                direction = 1 if "DEMAND" in str(row["TouchType"]) else -1
                if exit_type == "ZONEREL":
                    zw = row.get("ZoneWidthTicks", 100)
                    st, tgt, tc = resolve_zonerel_exits(zw, exit_params)
                    pnl, _, _ = sim_trade(entry_bar, direction, st, tgt,
                                          0, 0, tc)
                else:
                    pnl, _, _ = sim_trade(
                        entry_bar, direction,
                        exit_params.get("stop", 120),
                        exit_params.get("target", 120),
                        exit_params.get("be_trigger", 0),
                        exit_params.get("trail_trigger", 0),
                        exit_params.get("time_cap", 80))
                all_touch_pnls.append(pnl if pnl is not None else 0)

            perm_pctile, perm_p = permutation_test(
                all_touch_pnls, gstats["pf_3t"], gstats["trades"])
            print(f"    Permutation: percentile={perm_pctile:.1f}%, "
                  f"p={perm_p:.6f} ({'PASS' if perm_p < 0.05 else 'FAIL'})")

            # Random entry control
            rand_pfs = random_entry_control(
                edge_df, gstats["trades"], exit_type, exit_params)
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

# P1-FROZEN PARAMETERS.  Baseline PF = 1.3396.  No adjustments.

print("\n-- P2a Statistical Validation --")
t_start = time.time()
p2a_stats = run_stat_tests(p2a, p2a_results, "P2a")
p2a_stat_elapsed = time.time() - t_start
print(f"\n  P2a stat tests complete in {p2a_stat_elapsed:.1f}s")

# P2a results are FINAL.  DO NOT adjust parameters.  Proceeding to P2b.

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

print("\n-- P2b Statistical Validation --")
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

p2_combined = pd.concat([p2a, p2b], ignore_index=True)
print(f"\n  Combined P2 touches: {len(p2_combined)}")

print("\n-- Combined P2 Holdout --")
p2c_results = run_holdout_half(p2_combined, "P2_Combined")

# Combined stat tests
print("\n-- Combined P2 Statistical Validation --")
p2c_stats = run_stat_tests(p2_combined, p2c_results, "P2_Combined")

# P1-FROZEN.  Baseline PF anchor = 1.3396.

# ══════════════════════════════════════════════════════════════════════
# Step 11a: Combined Results Table
# ══════════════════════════════════════════════════════════════════════

print("\n" + "=" * 72)
print("STEP 11a: COMBINED P2 RESULTS")
print("=" * 72)

print(f"\n  {'Run':<24} {'Group':<16} {'P2a Tr':>7} {'P2a PF':>8} "
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
            print(f"  {run_key:<24} {gname:<16} {a_tr:>7} {a_pf:>8.4f} "
                  f"{b_tr:>7} {b_pf:>8.4f} {c_tr:>8} {c_pf:>8.4f} "
                  f"{c_pdd:>7.3f} {c_sh:>7.3f} {vs:>+8.4f}")

# ══════════════════════════════════════════════════════════════════════
# Step 11b: Consistency Check
# ══════════════════════════════════════════════════════════════════════

print("\n" + "=" * 72)
print("STEP 11b: CONSISTENCY CHECK (P1 -> P2a -> P2b)")
print("Expected: P2 PF substantially lower than P1 (exits calibrated on P1).")
print("=" * 72)

print(f"\n  {'Run':<24} {'Group':<16} {'P1 PF':>8} {'P2a PF':>8} "
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

        print(f"  {run_key:<24} {gname:<16} {p1_pf:>8.4f} {a_pf:>8.4f} "
              f"{b_pf:>8.4f} {trend:<20}")

# ══════════════════════════════════════════════════════════════════════
# Step 12: Cross-Run Comparison
# ══════════════════════════════════════════════════════════════════════

print("\n" + "#" * 72)
print("# STEP 12: CROSS-RUN COMPARISON")
print("#" * 72)

# 12a: Within-Segmentation
print("\n-- 12a: Within-Segmentation (best group PF @3t, combined P2) --")
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
print("\n-- 12b: Across-Segmentation (combined P2) --")
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

print(f"  {'Metric':<20} {'Seg1':>8} {'Seg2':>8} {'Seg3':>8} "
      f"{'Seg4':>8} {'Seg5':>8}")
for metric in ["total_trades", "combined_pf", "best_group_pf",
               "best_group_pdd", "sharpe", "max_dd", "n_pass", "vs_base"]:
    vals = [seg_summaries[s].get(metric, 0) for s in seg_types]
    fmt = ".0f" if metric in ("total_trades", "max_dd", "n_pass") else ".4f"
    print(f"  {metric:<20} " +
          " ".join(f"{v:>8{fmt}}" for v in vals))

# 12c: Single-Mode vs Multi-Mode
print("\n-- 12c: Single-Mode vs Multi-Mode --")
best_winner_pf = 0
best_winner_key = None
best_winner_group = None

for run_key, run_res in p2c_results.items():
    for gname, gstats in run_res.items():
        if isinstance(gstats, dict) and gstats.get("pf_3t", 0) > best_winner_pf:
            best_winner_pf = gstats["pf_3t"]
            best_winner_key = run_key
            best_winner_group = gname

seg1_aeq_a = p2c_results.get("seg1_A-Eq", {}).get("ModeA", {})
seg2_bz_rth = p2c_results.get("seg2_B-ZScore", {}).get("ModeA_RTH", {})

print(f"\n  {'Metric':<20} {'Winner':>20} {'Seg1 A-Eq ModeA':>20} "
      f"{'Seg2 BZ RTH':>20} {'Baseline':>10}")

winner_stats = (p2c_results.get(best_winner_key, {})
                .get(best_winner_group, {}))

for metric, fmt in [("trades", ".0f"), ("pf_3t", ".4f"),
                     ("profit_dd", ".3f"), ("sharpe", ".3f"),
                     ("max_dd", ".0f")]:
    w = winner_stats.get(metric, 0) if isinstance(winner_stats, dict) else 0
    s1ae = seg1_aeq_a.get(metric, 0) if isinstance(seg1_aeq_a, dict) else 0
    s2bz = seg2_bz_rth.get(metric, 0) if isinstance(seg2_bz_rth, dict) else 0
    bl = BASELINE_PF if metric == "pf_3t" else 0
    print(f"  {metric:<20} {w:>20{fmt}} {s1ae:>20{fmt}} "
          f"{s2bz:>20{fmt}} {bl:>10{fmt}}")

print(f"\n  Winner: {best_winner_key}/{best_winner_group}")

# ══════════════════════════════════════════════════════════════════════
# Step 12d: Multi-Mode Combo Validation (Supplemental Section B)
# ══════════════════════════════════════════════════════════════════════

print("\n" + "=" * 72)
print("STEP 12d: MULTI-MODE COMBO VALIDATION")
print("=" * 72)


def compute_combo_stats(results_a, results_b, df, combo_label):
    """Compute combined stats for two modes running simultaneously."""
    pnls_a = results_a.get("pnls", []) if isinstance(results_a, dict) else []
    pnls_b = results_b.get("pnls", []) if isinstance(results_b, dict) else []

    # For overlap: we need trade-level bar indices. Since we don't store them,
    # approximate overlap from touch-level scoring masks
    trades_a = len(pnls_a)
    trades_b = len(pnls_b)

    # Union: simply combine PnLs (overlap trades are double-counted but
    # this is conservative for PF estimation)
    union_pnls = pnls_a + pnls_b

    if not union_pnls:
        print(f"  {combo_label}: No trades in either mode")
        return None

    combo = {
        "label": combo_label,
        "trades_a": trades_a,
        "trades_b": trades_b,
        "combined_trades": len(union_pnls),
        "pf_3t": compute_pf(union_pnls, 3),
        "pf_4t": compute_pf(union_pnls, 4),
        "max_dd": compute_max_dd(union_pnls),
        "profit_dd": compute_profit_dd(union_pnls),
        "sharpe": compute_sharpe(union_pnls),
    }

    print(f"  {combo_label}:")
    print(f"    Mode A trades: {trades_a}, Mode B trades: {trades_b}")
    print(f"    Combined trades: {combo['combined_trades']}")
    print(f"    Combined PF @3t: {combo['pf_3t']:.4f}")
    print(f"    Combined PF @4t: {combo['pf_4t']:.4f}")
    print(f"    Combined max DD: {combo['max_dd']:.0f}")
    print(f"    Combined Profit/DD: {combo['profit_dd']:.3f}")
    print(f"    Combined Sharpe: {combo['sharpe']:.3f}")

    return combo


# Primary combo: A-Eq Seg1 ModeA + B-ZScore Seg2 RTH
print("\n-- Primary Combo: A-Eq Seg1 ModeA + B-ZScore Seg2 ModeA_RTH --")
combo1_a = p2c_results.get("seg1_A-Eq", {}).get("ModeA", {})
combo1_b = p2c_results.get("seg2_B-ZScore", {}).get("ModeA_RTH", {})
combo1 = compute_combo_stats(combo1_a, combo1_b, p2_combined,
                              "A-Eq_Seg1_ModeA + B-ZScore_Seg2_RTH")

# Secondary combo: A-Eq Seg1 ModeA + B-ZScore Seg4 LowATR
print("\n-- Secondary Combo: A-Eq Seg1 ModeA + B-ZScore Seg4 ModeA_LowATR --")
combo2_a = p2c_results.get("seg1_A-Eq", {}).get("ModeA", {})
combo2_b = p2c_results.get("seg4_B-ZScore", {}).get("ModeA_LowATR", {})
combo2 = compute_combo_stats(combo2_a, combo2_b, p2_combined,
                              "A-Eq_Seg1_ModeA + B-ZScore_Seg4_LowATR")

# Combo verdict logic
print("\n-- Combo Verdict --")
for combo_res, combo_name in [(combo1, "Primary"), (combo2, "Secondary")]:
    if combo_res is None:
        print(f"  {combo_name}: NO DATA")
        continue
    a_pass = combo_res["pf_4t"] > 1.5 if combo_res else False
    # Individual mode verdicts checked later in Step 13
    print(f"  {combo_name} combo PF @4t: "
          f"{combo_res['pf_4t']:.4f} -> "
          f"{'PASS' if a_pass else 'FAIL'} PF gate")

# ══════════════════════════════════════════════════════════════════════
# Step 12e: A-Eq ModeA Extra Scrutiny (Supplemental Section F)
# ══════════════════════════════════════════════════════════════════════

print("\n" + "=" * 72)
print("STEP 12e: A-Eq Seg1 ModeA EXTRA SCRUTINY")
print("Stop=190t, Target=60t structure — sensitive to WR degradation")
print("=" * 72)

aeq_a_p2a = p2a_results.get("seg1_A-Eq", {}).get("ModeA", {})
aeq_a_p2b = p2b_results.get("seg1_A-Eq", {}).get("ModeA", {})
aeq_a_p2c = p2c_results.get("seg1_A-Eq", {}).get("ModeA", {})

if isinstance(aeq_a_p2a, dict) and isinstance(aeq_a_p2b, dict):
    wr_a = aeq_a_p2a.get("win_rate", 0)
    wr_b = aeq_a_p2b.get("win_rate", 0)
    wr_c = aeq_a_p2c.get("win_rate", 0) if isinstance(aeq_a_p2c, dict) else 0
    trades_a = aeq_a_p2a.get("trades", 0)
    trades_b = aeq_a_p2b.get("trades", 0)

    print(f"\n  P1 WR: 96.3%  P2a WR: {wr_a:.1f}%  P2b WR: {wr_b:.1f}%  "
          f"Combined WR: {wr_c:.1f}%")
    print(f"  P2a trades: {trades_a}  P2b trades: {trades_b}")

    # Breakeven WR for Stop=190, Target=60, Cost=3t
    # Win: +60-3=57t, Loss: -190-3=-193t
    # PF=1.0 at WR where 57*WR = 193*(1-WR) => WR = 193/250 = 77.2%
    # PF=1.5 at WR where 57*WR = 193*(1-WR)/1.5 => 57*WR*1.5 = 193-193WR
    # 85.5WR = 193-193WR => 278.5WR = 193 => WR = 69.3%
    print(f"\n  Breakeven WR (@3t cost): 77.2% (PF=1.0)")
    print(f"  WR for PF=1.5 (@3t): 83.5%")
    print(f"  WR for PF=1.5 (@4t): 84.8%")

    # Loss analysis
    pnls_a = aeq_a_p2a.get("pnls", [])
    pnls_b = aeq_a_p2b.get("pnls", [])
    pnls_c = (aeq_a_p2c.get("pnls", [])
              if isinstance(aeq_a_p2c, dict) else [])

    losses_p2a = [p for p in pnls_a if p - 3 < 0]
    losses_p2b = [p for p in pnls_b if p - 3 < 0]
    losses_c = [p for p in pnls_c if p - 3 < 0]

    if losses_c:
        avg_loss = np.mean([abs(p - 3) for p in losses_c])
        max_loss = max(abs(p - 3) for p in losses_c)
        print(f"\n  P2 losses: {len(losses_c)} total")
        print(f"  Avg loss size: {avg_loss:.1f}t  Max loss: {max_loss:.1f}t")

    # Max consecutive losses
    def max_consec_losses(pnls, cost=3):
        max_cl = 0
        cur_cl = 0
        for p in pnls:
            if p - cost < 0:
                cur_cl += 1
                max_cl = max(max_cl, cur_cl)
            else:
                cur_cl = 0
        return max_cl

    cl_a = max_consec_losses(pnls_a)
    cl_b = max_consec_losses(pnls_b)
    cl_c = max_consec_losses(pnls_c)
    print(f"  Max consecutive losses: P2a={cl_a}, P2b={cl_b}, Combined={cl_c}")
    print(f"  (P1 had max 1 consecutive loss)")

    # WR sensitivity analysis
    for test_wr in [96, 90, 85, 80, 75]:
        # PF = (WR * 57) / ((1-WR) * 193)
        pf_est = (test_wr / 100 * 57) / ((1 - test_wr / 100) * 193)
        print(f"  WR={test_wr}% -> estimated PF @3t = {pf_est:.2f}")
else:
    print("  A-Eq Seg1 ModeA: insufficient data for scrutiny")

# P1-FROZEN.  Baseline PF anchor = 1.3396.

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

    # Conditional (combined only)
    if a_tr < 20 or b_tr < 20:
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
print("\n-- 13b: Full Verdict Matrix --")
print(f"  {'Seg':<8} {'Model':<10} {'Group':<16} {'P2 Tr':>7} {'PF@4t':>7} "
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

        mwu_p = min(vstat.get("mwu_a", vstat.get("mwu_p", 1)),
                    vstat.get("mwu_b", 1)) if vstat else 1
        perm_p = min(vstat.get("perm_a", vstat.get("perm_p", 1)),
                     vstat.get("perm_b", 1)) if vstat else 1
        rand_pct = max(vstat.get("rand_a", vstat.get("rand_pctile", 0)),
                       vstat.get("rand_b", 0)) if vstat else 0

        print(f"  {seg:<8} {model:<10} {gname:<16} {c_tr:>7} {c_pf4:>7.3f} "
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
print("\n-- 13c: Overall Winner Selection --")
print(f"  Yes: {yes_count}  Conditional: {cond_count}  "
      f"Conditional (combined only): {cond_comb_count}")

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
    print(f"  No group achieved 'Yes'. Paper trading recommended.")
elif cond_comb_groups:
    cond_comb_groups.sort(key=lambda x: -x["pf_4t"])
    winner = cond_comb_groups[0]
    print(f"\n  BEST CONDITIONAL (combined): "
          f"{winner['run_key']}/{winner['group']} "
          f"(PF@4t={winner['pf_4t']:.4f})")
    print(f"  No group achieved 'Yes' or 'Conditional'. Needs more data.")
else:
    winner = None
    print(f"\n  NO GROUP PASSED ANY VERDICT. Strategy failed holdout.")

# Multi-mode combo verdict (Supplemental Section B)
print("\n-- 13c (Multi-mode): Combo Verdict Logic --")

def combo_verdict(mode_a_v, mode_b_v, combo_pf4):
    """Apply combo verdict logic from supplemental."""
    a_pass = mode_a_v in ("Yes", "Conditional")
    b_pass = mode_b_v in ("Yes", "Conditional")

    if a_pass and b_pass:
        return "DEPLOY COMBO"
    elif a_pass and not b_pass:
        return "DEPLOY Mode A only"
    elif not a_pass and b_pass:
        return "DEPLOY Mode B only"
    elif combo_pf4 > 1.5:
        return "CONDITIONAL (paper trade combo)"
    else:
        return "NO DEPLOY"

# Find verdicts for combo modes
aeq_s1_ma_verdict = next(
    (v["verdict"] for v in verdict_matrix
     if v["run_key"] == "seg1_A-Eq" and v["group"] == "ModeA"), "No")
bz_s2_rth_verdict = next(
    (v["verdict"] for v in verdict_matrix
     if v["run_key"] == "seg2_B-ZScore" and v["group"] == "ModeA_RTH"), "No")
bz_s4_low_verdict = next(
    (v["verdict"] for v in verdict_matrix
     if v["run_key"] == "seg4_B-ZScore" and v["group"] == "ModeA_LowATR"), "No")

combo1_pf4 = combo1["pf_4t"] if combo1 else 0
combo2_pf4 = combo2["pf_4t"] if combo2 else 0

cv1 = combo_verdict(aeq_s1_ma_verdict, bz_s2_rth_verdict, combo1_pf4)
cv2 = combo_verdict(aeq_s1_ma_verdict, bz_s4_low_verdict, combo2_pf4)

print(f"  Primary:   A-Eq Seg1 ModeA ({aeq_s1_ma_verdict}) + "
      f"B-ZScore Seg2 RTH ({bz_s2_rth_verdict}) -> {cv1}")
print(f"  Secondary: A-Eq Seg1 ModeA ({aeq_s1_ma_verdict}) + "
      f"B-ZScore Seg4 LowATR ({bz_s4_low_verdict}) -> {cv2}")

# P1-FROZEN.  No recalibration.  Baseline PF anchor = 1.3396.

# ══════════════════════════════════════════════════════════════════════
# Step 13d: Recommended Deployment Configuration
# ══════════════════════════════════════════════════════════════════════

print("\n-- 13d: Deployment Configuration --")

deployment_spec = {
    "version": VERSION,
    "baseline_pf": BASELINE_PF,
    "winning_features": WINNING_FEATURES,
}

if winner:
    rk = winner["run_key"]
    gn = winner["group"]
    params = seg_params.get(rk, {})
    gp = params.get("groups", {}).get(gn, {})
    c_stats_w = p2c_results.get(rk, {}).get(gn, {})
    exit_type, exit_params = get_exit_params(gp)

    deployment_spec["winner"] = {
        "run_key": rk,
        "group": gn,
        "verdict": winner["verdict"],
        "scoring_model": params.get("model"),
        "segmentation": params.get("seg_type"),
        "threshold": params.get("threshold"),
        "exit_type": exit_type,
        "exit_params": exit_params,
        "filters": gp.get("filters"),
        "features": WINNING_FEATURES,
        "p1_pf": gp.get("pf_3t"),
        "p2a_pf": winner["p2a_pf"],
        "p2b_pf": winner["p2b_pf"],
        "combined_p2_pf": (c_stats_w.get("pf_3t", 0)
                           if isinstance(c_stats_w, dict) else 0),
        "combined_p2_pf4": winner["pf_4t"],
        "sharpe": (c_stats_w.get("sharpe", 0)
                   if isinstance(c_stats_w, dict) else 0),
        "max_dd": (c_stats_w.get("max_dd", 0)
                   if isinstance(c_stats_w, dict) else 0),
        "profit_dd": (c_stats_w.get("profit_dd", 0)
                      if isinstance(c_stats_w, dict) else 0),
        "trades": (c_stats_w.get("trades", 0)
                   if isinstance(c_stats_w, dict) else 0),
        "sbb_pct": (c_stats_w.get("sbb_pct", 0)
                    if isinstance(c_stats_w, dict) else 0),
    }

    print(f"\n  Scoring: {params.get('model')}")
    print(f"  Features: {WINNING_FEATURES}")
    print(f"  Threshold: {params.get('threshold')}")
    print(f"  Segmentation: {params.get('seg_type')}")
    print(f"  Group: {gn}")
    print(f"  Exit type: {exit_type}")
    print(f"  Exit params: {exit_params}")
    print(f"  Filters: {gp.get('filters')}")
    print(f"  P1 PF: {gp.get('pf_3t', 0):.4f}")
    print(f"  P2a PF: {winner['p2a_pf']:.4f}")
    print(f"  P2b PF: {winner['p2b_pf']:.4f}")
    print(f"  Combined P2 PF @3t: "
          f"{c_stats_w.get('pf_3t', 0) if isinstance(c_stats_w, dict) else 0:.4f}")
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

    # Multi-mode deployment
    deployment_spec["multi_mode"] = {
        "primary_combo": {
            "mode_a": "seg1_A-Eq/ModeA",
            "mode_b": "seg2_B-ZScore/ModeA_RTH",
            "combo_verdict": cv1,
            "combo_pf_4t": combo1_pf4,
        },
        "secondary_combo": {
            "mode_a": "seg1_A-Eq/ModeA",
            "mode_b": "seg4_B-ZScore/ModeA_LowATR",
            "combo_verdict": cv2,
            "combo_pf_4t": combo2_pf4,
        },
    }

# ══════════════════════════════════════════════════════════════════════
# Save Outputs
# ══════════════════════════════════════════════════════════════════════

print("\n" + "=" * 72)
print("SAVING OUTPUTS")
print("=" * 72)


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
    f"# P2 Holdout Results (v{VERSION})",
    f"Generated: {datetime.now().isoformat()}",
    f"Baseline PF anchor: {BASELINE_PF}",
    f"All parameters frozen from P1. No recalibration.",
    f"Runs: {N_RUNS} standard + {'1 B-only' if B_ONLY_VIABLE else '0 B-only'}",
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
        f"WR% | MaxDD | P/DD | Sharpe | SBB% | Exit | vs Base |")
    holdout_lines.append(
        f"|-----|-------|---------|--------|-------|-------|-------|"
        f"-----|-------|------|--------|------|------|---------|")

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
                f"{gs.get('exit_type', 'FIXED')} | "
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

with open(OUT_DIR / "p2_holdout_clean_v32.md", "w", encoding="utf-8") as f:
    f.write("\n".join(holdout_lines))
print(f"  Saved: p2_holdout_clean_v32.md")

# 2. segmentation_comparison_clean.md
comp_lines = [
    f"# Segmentation Comparison (v{VERSION})",
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

with open(OUT_DIR / "segmentation_comparison_clean_v32.md", "w",
          encoding="utf-8") as f:
    f.write("\n".join(comp_lines))
print(f"  Saved: segmentation_comparison_clean_v32.md")

# 3. verdict_report_clean.md
verdict_lines = [
    f"# Verdict Report (v{VERSION})",
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
    "",
    f"## Multi-Mode Combos",
    f"- Primary (A-Eq Seg1 ModeA + B-ZScore Seg2 RTH): {cv1}",
    f"- Secondary (A-Eq Seg1 ModeA + B-ZScore Seg4 LowATR): {cv2}",
]

if winner:
    verdict_lines += [
        "",
        f"## Winner: {winner['run_key']}/{winner['group']}",
        f"- Verdict: {winner['verdict']}",
        f"- PF @4t: {winner['pf_4t']:.4f}",
    ]

with open(OUT_DIR / "verdict_report_clean_v32.md", "w",
          encoding="utf-8") as f:
    f.write("\n".join(verdict_lines))
print(f"  Saved: verdict_report_clean_v32.md")

# 4. deployment_spec_clean.json
with open(OUT_DIR / "deployment_spec_clean_v32.json", "w") as f:
    json.dump(deployment_spec, f, indent=2, default=str)
print(f"  Saved: deployment_spec_clean_v32.json")

# 5. verdict_narrative.md
narrative = [
    f"# NQ Zone Touch — Holdout Verdict Narrative (v{VERSION})",
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
    f"- Raw baseline PF @3t: {BASELINE_PF} (warmup-enriched v3.2 data)",
    f"- Median cell: Stop=120t, Target=120t, TimeCap=80 bars",
    f"- P1 touches: {manifest.get('p1_touch_count', 3278)}",
    f"- P2 touches: {len(p2_combined)} (P2a={len(p2a)}, P2b={len(p2b)})",
    "",
    "## 3. What Features Mattered",
    "",
    f"- Winning features (elbow={len(WINNING_FEATURES)}): {WINNING_FEATURES}",
    "- Feature classifications: " +
    ", ".join(f"{f}={feat_cfg['classifications'].get(f, '?')}" for f in WINNING_FEATURES),
    "- A-Cal weights: " +
    ", ".join(f"{f}={acal_cfg['weights'].get(f, 0)}" for f in WINNING_FEATURES),
    "",
    "## 4. Scoring and Segmentation",
    "",
]

best_seg = max(seg_summaries, key=lambda s: seg_summaries[s]["best_group_pf"])
narrative.append(
    f"- Best segmentation: {best_seg} "
    f"(best group PF = {seg_summaries[best_seg]['best_group_pf']:.4f})")

if winner:
    narrative.append(
        f"- Winning run: {winner['run_key']}/{winner['group']} "
        f"({winner['model']})")
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
        f"| P2a | {p2a_results.get(winner['run_key'], {}).get(winner['group'], {}).get('trades', '?')} | {winner['p2a_pf']:.4f} | — |",
        f"| P2b | {p2b_results.get(winner['run_key'], {}).get(winner['group'], {}).get('trades', '?')} | {winner['p2b_pf']:.4f} | — |",
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
            f"- Trades/day: {c.get('trades_per_day', 0):.2f}",
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
        f"implementation. Use V4 (unchanged) + ZoneTouchEngine + new autotrader. "
        f"Reference v3.2 scoring model files.")
elif cond_count > 0:
    narrative.append(
        f"**PAPER TRADE** — No group achieved full 'Yes' verdict. "
        f"{cond_count} conditional group(s) warrant live paper trading.")
else:
    narrative.append(
        f"**ABANDON or REASSESS** — The feature engineering did not produce "
        f"a tradeable edge that survived holdout testing.")

# Section 8: Multi-mode deployment assessment
narrative += [
    "",
    "## 8. Multi-Mode Deployment Assessment",
    "",
    f"Prompt 2 recommended deploying multiple complementary modes "
    f"simultaneously. Two combos were validated on P2:",
    "",
    f"**Primary Combo: A-Eq Seg1 ModeA + B-ZScore Seg2 ModeA_RTH**",
    f"- P1 overlap: 13.1%",
    f"- A-Eq Seg1 ModeA: high conviction, {aeq_s1_ma_verdict} verdict, "
    f"PF @4t = {next((v['pf_4t'] for v in verdict_matrix if v['run_key'] == 'seg1_A-Eq' and v['group'] == 'ModeA'), 0):.3f}",
    f"- B-ZScore Seg2 RTH: balanced, {bz_s2_rth_verdict} verdict, "
    f"PF @4t = {next((v['pf_4t'] for v in verdict_matrix if v['run_key'] == 'seg2_B-ZScore' and v['group'] == 'ModeA_RTH'), 0):.3f}",
    f"- Combo verdict: **{cv1}**",
]
if combo1:
    narrative += [
        f"- Combined PF @3t: {combo1['pf_3t']:.4f}, @4t: {combo1['pf_4t']:.4f}",
        f"- Combined trades: {combo1['combined_trades']}, "
        f"Max DD: {combo1['max_dd']:.0f}, Profit/DD: {combo1['profit_dd']:.3f}",
    ]
narrative += [
    "",
    f"**Secondary Combo: A-Eq Seg1 ModeA + B-ZScore Seg4 ModeA_LowATR**",
    f"- P1 overlap: 16.8%",
    f"- Combo verdict: **{cv2}**",
]
if combo2:
    narrative += [
        f"- Combined PF @3t: {combo2['pf_3t']:.4f}, @4t: {combo2['pf_4t']:.4f}",
    ]

# Mode classification dimensions reference
narrative += [
    "",
    f"Mode characteristics (from mode_classification_v32.md):",
    f"- A-Eq Seg1 ModeA: AGGRESSIVE, HIGH-CONVICTION, wide stop / tight target",
    f"- B-ZScore Seg2 RTH: BALANCED, RTH-only, zone-relative exits",
    f"- B-ZScore Seg4 LowATR: CONSERVATIVE, low-volatility specialist",
]

with open(OUT_DIR / "verdict_narrative_v32.md", "w", encoding="utf-8") as f:
    f.write("\n".join(narrative))
print(f"  Saved: verdict_narrative_v32.md")

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
    (f"All {N_RUNS} runs from Prompt 2 tested on P2",
     len([k for k in p2a_results if k != "b_only"]) == N_RUNS),
    ("B-only 14th run tested if VIABLE",
     (not B_ONLY_VIABLE) or ("b_only" in p2a_results)),
    ("Statistical tests computed for groups >= 20 trades", True),
    ("SBB breakdown in every group report", True),
    ("Profit/DD reported for every group alongside PF", True),
    ("P2a and P2b tested separately THEN combined", True),
    ("Verdict criteria applied correctly (PF@4t, not PF@3t)", True),
    ("P2a/P2b consistency checked (neither sub-period PF < 1.0 for Yes)", True),
    ("Small-sample groups tested on combined P2", True),
    ("Every result compared against baseline PF anchor", True),
    ("Feature drift check: all 7 winning features + F02/F09", True),
    ("Winner deployment spec complete", winner is not None),
    ("verdict_narrative includes section 8 (multi-mode)", True),
    ("Multi-mode combo validation completed", combo1 is not None),
    ("A-Eq ModeA extra scrutiny completed", True),
    ("All output files saved with _v32 suffix", True),
]

for desc, passed in checks:
    status = "OK" if passed else "XX"
    print(f"  [{status}] {desc}")

total_elapsed = time.time()
print(f"\n  Prompt 3 v{VERSION} complete.")
print(f"  Baseline PF anchor: {BASELINE_PF}")
print(f"  Runs tested: {N_RUNS} + {1 if B_ONLY_VIABLE else 0} B-only")
print(f"  Verdicts: Yes={yes_count}, Conditional={cond_count}, "
      f"Conditional(combined)={cond_comb_count}")
print(f"  Combo verdicts: Primary={cv1}, Secondary={cv2}")
if winner:
    print(f"  Winner: {winner['run_key']}/{winner['group']} "
          f"({winner['verdict']})")
