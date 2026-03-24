# archetype: zone_touch
"""Ray Conditional Analysis on Qualifying Trades (Analysis B) — v3.2

Tests whether ray context at time of entry can improve qualifying trade
outcomes via:
  Surface 2: Skip gate (filter predictable losers)
  Surface 3: Adaptive exits (modify exits based on ray environment)

The 7-feature scoring model is FROZEN throughout. This analysis adds
overlays, not model modifications.

Dependency: Analysis A complete (REDUNDANT verdict). Model stays at v3.2.
"""

import numpy as np
import pandas as pd
from pathlib import Path
import json, sys, time as time_mod, io, warnings, importlib.util
from datetime import datetime, time as dt_time
from copy import deepcopy

warnings.filterwarnings("ignore")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
np.random.seed(42)

# ============================================================
# CONSTANTS
# ============================================================
TICK = 0.25
PROX_THRESHOLD = 40   # ticks for backing ray
OBSTACLE_RANGE = 100  # ticks for obstacle ray search

BASE = Path(r"c:/Projects/pipeline")
DATA = BASE / "stages/01-data/output/zone_prep"
TOUCH_DIR = BASE / "stages/01-data/data/touches"
BAR_VOL_DIR = BASE / "stages/01-data/data/bar_data/volume"
BAR_TIME_DIR = BASE / "stages/01-data/data/bar_data/time"
OUT = BASE / "shared/archetypes/zone_touch/output"
PARAM_DIR = OUT
BACKTEST_DIR = BASE / "stages/04-backtest/zone_touch/output"

# Load ray_feature_screening module
_rfs_path = Path(__file__).parent / "ray_feature_screening.py"
_rfs_spec = importlib.util.spec_from_file_location("ray_feature_screening", str(_rfs_path))
rfs = importlib.util.module_from_spec(_rfs_spec)
_rfs_spec.loader.exec_module(rfs)

report = []
def rprint(msg=""):
    print(msg)
    report.append(str(msg))


# ============================================================
# LOAD FROZEN MODEL PARAMS
# ============================================================
with open(PARAM_DIR / "scoring_model_aeq_v32.json") as f:
    aeq_cfg = json.load(f)
with open(PARAM_DIR / "scoring_model_bzscore_v32.json") as f:
    bz_cfg = json.load(f)
with open(PARAM_DIR / "scoring_model_acal_v32.json") as f:
    acal_cfg = json.load(f)
with open(PARAM_DIR / "feature_config_v32.json") as f:
    feat_cfg = json.load(f)
with open(PARAM_DIR / "segmentation_params_clean_v32.json") as f:
    seg_params = json.load(f)

WINNING_FEATURES = feat_cfg["winning_features"]
BIN_EDGES = feat_cfg["feature_bin_edges"]

# Deployment waterfall parameters
M1_THRESHOLD = aeq_cfg["threshold"]  # 45.5
M1_EXIT = {"stop": 190, "target": 60, "be_trigger": 0, "trail_trigger": 0, "time_cap": 120}
M2_THRESHOLD = 0.50  # B-ZScore threshold
M2_ZONEREL = seg_params["seg2_B-ZScore"]["groups"]["ModeA_RTH"]["exit_params_zonerel"]
M2_FILTERS = seg_params["seg2_B-ZScore"]["groups"]["ModeA_RTH"]["filters"]

RTH_START = dt_time(9, 30)
RTH_END = dt_time(16, 15)


# ============================================================
# SCORING FUNCTIONS (from prompt3_holdout_v32.py)
# ============================================================
def _bin_numeric(vals, lo, hi):
    out = np.full(len(vals), "Mid", dtype=object)
    v = np.asarray(vals, dtype=float)
    out[v <= lo] = "Low"
    out[v > hi] = "High"
    out[np.isnan(v)] = "NA"
    return out

def score_aeq(df):
    bp = aeq_cfg["bin_points"]
    bin_edges = acal_cfg.get("bin_edges", BIN_EDGES)
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
    feat_cols = bz_cfg["feature_columns"]
    coeffs = bz_cfg["coefficients"]
    intercept = bz_cfg["intercept"]
    means = bz_cfg["scaler_mean"]
    stds = bz_cfg["scaler_std"]
    X = np.zeros((len(df), len(feat_cols)))
    for j, fc in enumerate(feat_cols):
        if fc in ("F10", "F09", "F21", "F13"):
            X[:, j] = df[fc].fillna(0).values
        elif fc.startswith("F04_"):
            cat = fc.replace("F04_", "")
            X[:, j] = (df["F04"] == cat).astype(float).values
        elif fc.startswith("F01_"):
            cat = fc.replace("F01_", "")
            X[:, j] = (df["F01"] == cat).astype(float).values
        elif fc.startswith("F05_"):
            cat = fc.replace("F05_", "")
            X[:, j] = (df["F05"] == cat).astype(float).values
    means_arr = np.array(means)
    stds_arr = np.array(stds)
    stds_arr[stds_arr == 0] = 1.0
    X_scaled = (X - means_arr) / stds_arr
    return X_scaled @ np.array(coeffs) + intercept


# ============================================================
# SIMULATION ENGINE (from prompt3_holdout_v32.py)
# ============================================================
def sim_trade(entry_bar, direction, stop, target, be_trigger, trail_trigger,
              tcap, bar_arr, n_bars_total):
    """Simulate single trade. Returns (pnl, bars_held, exit_type, mfe, mae)."""
    if entry_bar >= n_bars_total:
        return None, 0, None, 0, 0
    ep = bar_arr[entry_bar, 0]
    if direction == 1:
        stop_price = ep - stop * TICK
        target_price = ep + target * TICK
    else:
        stop_price = ep + stop * TICK
        target_price = ep - target * TICK

    mfe = 0.0
    mae = 0.0
    be_active = False
    trail_active = False
    trail_stop_price = stop_price

    end = min(entry_bar + tcap, n_bars_total)
    for i in range(entry_bar, end):
        h, l, last = bar_arr[i, 1], bar_arr[i, 2], bar_arr[i, 3]
        bh = i - entry_bar + 1

        if direction == 1:
            cur_fav = (h - ep) / TICK
            cur_adv = (ep - l) / TICK
        else:
            cur_fav = (ep - l) / TICK
            cur_adv = (h - ep) / TICK
        mfe = max(mfe, cur_fav)
        mae = max(mae, cur_adv)

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
                new_trail = ep + (mfe - trail_trigger) * TICK
                trail_stop_price = max(trail_stop_price, new_trail)
                stop_price = max(stop_price, trail_stop_price)
            else:
                new_trail = ep - (mfe - trail_trigger) * TICK
                trail_stop_price = min(trail_stop_price, new_trail)
                stop_price = min(stop_price, trail_stop_price)

        if direction == 1:
            stop_hit = l <= stop_price
            target_hit = h >= target_price
        else:
            stop_hit = h >= stop_price
            target_hit = l <= target_price

        if stop_hit and target_hit:
            pnl = ((stop_price - ep) / TICK if direction == 1
                   else (ep - stop_price) / TICK)
            etype = "TRAIL" if trail_active else ("BE" if be_active else "STOP")
            return pnl, bh, etype, mfe, mae
        if stop_hit:
            pnl = ((stop_price - ep) / TICK if direction == 1
                   else (ep - stop_price) / TICK)
            etype = "TRAIL" if trail_active else ("BE" if be_active else "STOP")
            return pnl, bh, etype, mfe, mae
        if target_hit:
            return target, bh, "TARGET", mfe, mae
        if bh >= tcap:
            pnl = ((last - ep) / TICK if direction == 1
                   else (ep - last) / TICK)
            return pnl, bh, "TIMECAP", mfe, mae

    if end > entry_bar:
        last = bar_arr[end - 1, 3]
        pnl = ((last - ep) / TICK if direction == 1
               else (ep - last) / TICK)
        return pnl, end - entry_bar, "TIMECAP", mfe, mae
    return None, 0, None, 0, 0


def resolve_zonerel_exits(zw_ticks, ep_zonerel):
    stop_spec = ep_zonerel.get("stop_mult")
    target_mult = ep_zonerel.get("target_mult", 0.5)
    tcap = ep_zonerel.get("time_cap", 80)
    target_ticks = max(1, round(zw_ticks * target_mult))
    if isinstance(stop_spec, str) and "max" in stop_spec.lower():
        stop_ticks = max(round(1.5 * zw_ticks), 120)
    else:
        stop_ticks = max(1, round(float(stop_spec) * zw_ticks))
    return stop_ticks, target_ticks, tcap


def simulate_population(touches_df, mode, bar_arr, n_bars_total,
                         exit_override=None):
    """Simulate qualifying trades with mode-specific exits.
    Returns list of per-trade dicts with outcomes."""
    subset = touches_df.sort_values("RotBarIndex").copy()
    results = []
    in_trade_until = -1

    for idx, row in subset.iterrows():
        rbi = int(row["RotBarIndex"])
        entry_bar = rbi + 1
        if entry_bar <= in_trade_until:
            continue
        direction = 1 if "DEMAND" in str(row["TouchType"]) else -1
        zw = row.get("ZoneWidthTicks", 100)

        if exit_override:
            stop, target, tcap = exit_override["stop"], exit_override["target"], exit_override["time_cap"]
            be_trig = exit_override.get("be_trigger", 0)
            trail_trig = exit_override.get("trail_trigger", 0)
        elif mode == "M1":
            stop = M1_EXIT["stop"]
            target = M1_EXIT["target"]
            tcap = M1_EXIT["time_cap"]
            be_trig = M1_EXIT["be_trigger"]
            trail_trig = M1_EXIT["trail_trigger"]
        elif mode == "M2":
            stop, target, tcap = resolve_zonerel_exits(zw, M2_ZONEREL)
            be_trig = 0
            trail_trig = 0
        else:
            stop, target, tcap = 120, 120, 80
            be_trig = 0
            trail_trig = 0

        pnl, bh, etype, mfe, mae = sim_trade(
            entry_bar, direction, stop, target, be_trig, trail_trig,
            tcap, bar_arr, n_bars_total)

        if pnl is not None:
            results.append({
                "touch_idx": idx, "BarIndex": row["BarIndex"],
                "RotBarIndex": rbi, "entry_bar": entry_bar,
                "direction": direction, "mode": mode,
                "pnl": pnl, "bars_held": bh, "exit_type": etype,
                "mfe": mfe, "mae": mae,
                "stop_used": stop, "target_used": target, "tc_used": tcap,
                "zw_ticks": zw,
            })
            in_trade_until = entry_bar + bh - 1

    return pd.DataFrame(results)


def compute_pf(pnls, cost=4):
    if len(pnls) == 0:
        return 0
    gp = sum(p - cost for p in pnls if p - cost > 0)
    gl = sum(abs(p - cost) for p in pnls if p - cost < 0)
    return gp / gl if gl > 0 else (float("inf") if gp > 0 else 0)

def compute_wr(pnls, cost=4):
    if len(pnls) == 0:
        return 0
    return sum(1 for p in pnls if p - cost > 0) / len(pnls) * 100

def compute_profit_dd(pnls, cost=4):
    if len(pnls) == 0:
        return 0
    cum = 0; peak = 0; max_dd = 0
    for p in pnls:
        cum += (p - cost)
        peak = max(peak, cum)
        max_dd = max(max_dd, peak - cum)
    net = sum(p - cost for p in pnls)
    return net / max_dd if max_dd > 0 else (float("inf") if net > 0 else 0)


# ============================================================
# MAIN ANALYSIS
# ============================================================
t0 = time_mod.time()

rprint("=" * 70)
rprint("RAY CONDITIONAL ANALYSIS — ANALYSIS B (v3.2)")
rprint("=" * 70)
rprint(f"  Date: {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M')}")
rprint(f"  Frozen model: {WINNING_FEATURES}")
rprint(f"  Analysis A verdict: REDUNDANT (model stays frozen)")
rprint(f"  Ray filters: 60m+ only, backing={PROX_THRESHOLD}t, obstacle={OBSTACLE_RANGE}t")
rprint()


# ============================================================
# STEP 0: LOAD DATA
# ============================================================
rprint("=" * 70)
rprint("STEP 0: LOAD DATA")
rprint("=" * 70)

# Load scored touches
aeq_df = pd.read_csv(OUT / "p1_scored_touches_aeq_v32.csv")
bz_df = pd.read_csv(OUT / "p1_scored_touches_bzscore_v32.csv")
n_total = len(aeq_df)
rprint(f"  Total P1 touches: {n_total}")

# Load ray candidates from Analysis A (has backing ray features)
ray_cand = pd.read_csv(OUT / "ray_elbow_candidates_v32.csv")
rprint(f"  Ray elbow candidates: {len(ray_cand)} rows")

# Load bar data
bar_p1 = pd.read_csv(DATA / "NQ_bardata_P1.csv", skipinitialspace=True)
bar_p1.columns = bar_p1.columns.str.strip()
bar_arr_p1 = bar_p1[["Open", "High", "Low", "Last"]].to_numpy(dtype=np.float64)
n_bars_p1 = len(bar_arr_p1)
rprint(f"  P1 bars: {n_bars_p1}")


# ============================================================
# STEP 1a: IDENTIFY QUALIFYING TRADES
# ============================================================
rprint("\n" + "=" * 70)
rprint("STEP 1a: IDENTIFY QUALIFYING TRADES")
rprint("=" * 70)

def tf_minutes(s):
    return int(str(s).replace('m', ''))

# Mode 1: A-Eq >= 45.5
m1_mask = aeq_df["Score_AEq"] >= M1_THRESHOLD
m1_touches = aeq_df[m1_mask].copy()
m1_touches["mode"] = "M1"
rprint(f"  Mode 1 (A-Eq >= {M1_THRESHOLD}): {len(m1_touches)} qualifying touches")

# Mode 2: seg2 B-ZScore ModeA_RTH (B-ZScore >= 0.50, RTH sessions, seq<=2, TF<=120m)
# Exclude Mode 1 overlaps (waterfall priority)
m1_keys = set(zip(m1_touches["BarIndex"], m1_touches["TouchType"], m1_touches["SourceLabel"]))
bz_keys = list(zip(bz_df["BarIndex"], bz_df["TouchType"], bz_df["SourceLabel"]))
is_m1 = pd.Series([k in m1_keys for k in bz_keys])

rth_sessions = ["OpeningDrive", "Midday", "Close"]
m2_mask = (
    (bz_df["Score_BZScore"] >= M2_THRESHOLD) &
    (bz_df["F05"].isin(rth_sessions)) &
    (bz_df["TouchSequence"] <= M2_FILTERS.get("seq_max", 2)) &
    (bz_df["SourceLabel"].apply(tf_minutes) <= 120) &
    ~is_m1
)
m2_touches = bz_df[m2_mask].copy()
m2_touches["mode"] = "M2"
rprint(f"  Mode 2 (B-ZScore RTH, excl M1): {len(m2_touches)} qualifying touches")
rprint(f"  Combined: {len(m1_touches) + len(m2_touches)}")


# ============================================================
# STEP 1b: JOIN RAY CONTEXT
# ============================================================
rprint("\n" + "=" * 70)
rprint("STEP 1b: JOIN RAY CONTEXT")
rprint("=" * 70)

# Build join key
ray_cand["_jk"] = (
    ray_cand["BarIndex"].astype(str) + "_" +
    ray_cand["TouchType"] + "_" +
    ray_cand["SourceLabel"]
)

BACKING_COLS = [
    "backing_bounce_streak", "backing_flip_count", "backing_dwell_bars",
    "backing_decay_mag", "backing_approach_vel", "backing_dist_ticks",
    "backing_cross_tf",
]

ray_feats = ray_cand[["_jk"] + BACKING_COLS].drop_duplicates(subset="_jk")

# Join to Mode 1 and Mode 2 touches
for df_label, touches_df in [("M1", m1_touches), ("M2", m2_touches)]:
    touches_df["_jk"] = (
        touches_df["BarIndex"].astype(str) + "_" +
        touches_df["TouchType"] + "_" +
        touches_df["SourceLabel"]
    )
    before_len = len(touches_df)
    touches_df_merged = touches_df.merge(ray_feats, on="_jk", how="left")
    # Update in-place via index
    for col in BACKING_COLS:
        if df_label == "M1":
            m1_touches[col] = touches_df_merged[col].values
        else:
            m2_touches[col] = touches_df_merged[col].values

    has_backing = touches_df_merged["backing_bounce_streak"].notna().sum()
    pct = has_backing / len(touches_df_merged) * 100
    rprint(f"  {df_label} backing ray coverage: {has_backing}/{len(touches_df_merged)} ({pct:.1f}%)")

# Now compute OBSTACLE ray features
# Need to load ray data and compute obstacle rays for qualifying touches
rprint("\n  Computing OBSTACLE ray features...")

# Load raw ray data for obstacle computation
zte_raw = pd.read_csv(TOUCH_DIR / "NQ_ZTE_raw_P1.csv")
zte_raw = zte_raw[zte_raw["TouchType"] != "VP_RAY"].copy()
ray_ctx = pd.read_csv(TOUCH_DIR / "NQ_ray_context_P1.csv")
ray_ctx_htf = ray_ctx[ray_ctx["RayTF"].apply(rfs.is_htf)].copy()

# Build TouchID → obstacle ray mapping from ray_context
# For each qualifying touch, find nearest 60m+ ray AHEAD of entry
def compute_obstacle_features(touches_df, ray_ctx_htf, zte_raw):
    """Compute obstacle ray features for qualifying touches."""
    # Build TouchID for zte_raw
    zte_raw_ids = (
        zte_raw["BarIndex"].astype(str) + "_" +
        zte_raw["TouchType"] + "_" +
        zte_raw["SourceLabel"]
    )
    zte_raw["TouchID_rfs"] = zte_raw_ids

    # Build TouchID for qualifying touches
    touches_df["TouchID_rfs"] = (
        touches_df["BarIndex"].astype(str) + "_" +
        touches_df["TouchType"] + "_" +
        touches_df["SourceLabel"]
    )

    obstacle_dist = []
    obstacle_streak = []
    obstacle_flips = []
    has_obstacle = []

    for _, touch in touches_df.iterrows():
        tid = touch["TouchID_rfs"]
        tt = touch["TouchType"]
        zt = touch["ZoneTop"]
        zb = touch["ZoneBot"]
        zw = touch.get("ZoneWidthTicks", 100) * TICK

        if tt == "DEMAND_EDGE":
            entry = zt
        elif tt == "SUPPLY_EDGE":
            entry = zb
        else:
            obstacle_dist.append(np.nan)
            obstacle_streak.append(np.nan)
            obstacle_flips.append(np.nan)
            has_obstacle.append(0)
            continue

        # Get nearby HTF rays from ray_context
        nearby = ray_ctx_htf[ray_ctx_htf["TouchID"] == tid].copy()

        if len(nearby) == 0:
            obstacle_dist.append(np.nan)
            obstacle_streak.append(np.nan)
            obstacle_flips.append(np.nan)
            has_obstacle.append(0)
            continue

        # Find obstacle rays (ahead of entry, profit direction)
        best_obstacle_dist = 9999
        best_obstacle_streak = np.nan
        best_obstacle_flips = np.nan
        found = False

        for _, ray_row in nearby.iterrows():
            rp = ray_row["RayPrice"]
            dist = ray_row["RayDistTicks"]
            age = ray_row["RayAgeBars"]

            # Obstacle = AHEAD of entry (profit side)
            if tt == "DEMAND_EDGE":
                # Profit is above entry
                is_obstacle = rp > entry + 5 * TICK
            else:
                # Profit is below entry
                is_obstacle = rp < entry - 5 * TICK

            if not is_obstacle:
                continue

            # Distance from entry to obstacle
            obs_dist = abs(rp - entry) / TICK
            if obs_dist > OBSTACLE_RANGE:
                continue

            if obs_dist < best_obstacle_dist:
                best_obstacle_dist = obs_dist
                # Use age as proxy for streak (ray_context doesn't have lifecycle)
                # but we can estimate: older rays likely have more interactions
                best_obstacle_streak = age  # placeholder
                best_obstacle_flips = np.nan
                found = True

        if found:
            obstacle_dist.append(best_obstacle_dist)
            obstacle_streak.append(best_obstacle_streak)
            obstacle_flips.append(best_obstacle_flips)
            has_obstacle.append(1)
        else:
            obstacle_dist.append(np.nan)
            obstacle_streak.append(np.nan)
            obstacle_flips.append(np.nan)
            has_obstacle.append(0)

    touches_df["obstacle_dist_ticks"] = obstacle_dist
    touches_df["obstacle_age_bars"] = obstacle_streak
    touches_df["has_obstacle"] = has_obstacle
    return touches_df

m1_touches = compute_obstacle_features(m1_touches, ray_ctx_htf, zte_raw)
m2_touches = compute_obstacle_features(m2_touches, ray_ctx_htf, zte_raw)

m1_obs = m1_touches["has_obstacle"].sum()
m2_obs = m2_touches["has_obstacle"].sum()
rprint(f"  M1 obstacle ray coverage: {m1_obs}/{len(m1_touches)} ({m1_obs/len(m1_touches)*100:.1f}%)")
rprint(f"  M2 obstacle ray coverage: {m2_obs}/{len(m2_touches)} ({m2_obs/len(m2_touches)*100:.1f}%)")

# Also compute ray density (count of 60m+ rays within 50t)
def compute_ray_density(touches_df, ray_ctx_htf):
    density = []
    for _, touch in touches_df.iterrows():
        tid = touch["TouchID_rfs"]
        nearby = ray_ctx_htf[ray_ctx_htf["TouchID"] == tid]
        n_within_50 = (nearby["RayDistTicks"] <= 50).sum()
        density.append(n_within_50)
    touches_df["ray_count_50t"] = density
    return touches_df

m1_touches = compute_ray_density(m1_touches, ray_ctx_htf)
m2_touches = compute_ray_density(m2_touches, ray_ctx_htf)
rprint(f"  M1 mean ray density (50t): {m1_touches['ray_count_50t'].mean():.1f}")
rprint(f"  M2 mean ray density (50t): {m2_touches['ray_count_50t'].mean():.1f}")


# ============================================================
# STEP 1c: SIMULATE TRADE OUTCOMES
# ============================================================
rprint("\n" + "=" * 70)
rprint("STEP 1c: SIMULATE TRADE OUTCOMES (P1)")
rprint("=" * 70)

m1_trades = simulate_population(m1_touches, "M1", bar_arr_p1, n_bars_p1)
m2_trades = simulate_population(m2_touches, "M2", bar_arr_p1, n_bars_p1)

rprint(f"  Mode 1 P1 trades: {len(m1_trades)}")
if len(m1_trades) > 0:
    m1_pf4 = compute_pf(m1_trades["pnl"].tolist(), cost=4)
    m1_wr = compute_wr(m1_trades["pnl"].tolist(), cost=4)
    rprint(f"    PF@4t={m1_pf4:.2f}, WR={m1_wr:.1f}%")

rprint(f"  Mode 2 P1 trades: {len(m2_trades)}")
if len(m2_trades) > 0:
    m2_pf4 = compute_pf(m2_trades["pnl"].tolist(), cost=4)
    m2_wr = compute_wr(m2_trades["pnl"].tolist(), cost=4)
    rprint(f"    PF@4t={m2_pf4:.2f}, WR={m2_wr:.1f}%")

# Join ray features to trade results
for trades_df, touches_df in [(m1_trades, m1_touches), (m2_trades, m2_touches)]:
    if len(trades_df) == 0:
        continue
    # Join on touch_idx (which is the original DataFrame index)
    ray_cols = BACKING_COLS + ["obstacle_dist_ticks", "obstacle_age_bars",
                                "has_obstacle", "ray_count_50t"]
    for col in ray_cols:
        if col in touches_df.columns:
            col_map = touches_df[col]
            trades_df[col] = trades_df["touch_idx"].map(col_map)


# ============================================================
# STEP 1d: BACKING STREAK PARADOX DIAGNOSTIC
# ============================================================
rprint("\n" + "=" * 70)
rprint("STEP 1d: BACKING STREAK PARADOX DIAGNOSTIC")
rprint("=" * 70)
rprint("  Testing whether high backing streak = worse outcomes for qualifying trades")
rprint("  (Analysis A found dPF = -1.8116 for R1 backing bounce streak)")
rprint()

def streak_diagnostic(trades_df, mode_label):
    """Compute PF by backing streak bin."""
    rprint(f"  --- {mode_label} ({len(trades_df)} trades) ---")
    if len(trades_df) == 0:
        rprint(f"    No trades.")
        return "INSUFFICIENT"

    streak = trades_df["backing_bounce_streak"].copy()
    has_data = streak.notna()

    bins = [
        ("0 (just flipped)", streak == 0),
        ("1-2", (streak >= 1) & (streak <= 2)),
        ("3-5", (streak >= 3) & (streak <= 5)),
        ("6+", streak >= 6),
        ("No backing ray", ~has_data),
    ]

    rprint(f"  {'Streak':<20} {'N':>5} {'WR%':>7} {'PF@4t':>8} {'Mean PnL':>10}")
    rprint(f"  {'-'*55}")

    pf_by_streak = []
    for label, mask in bins:
        sub = trades_df[mask]
        n = len(sub)
        if n == 0:
            rprint(f"  {label:<20} {0:>5} {'N/A':>7} {'N/A':>8} {'N/A':>10}")
            continue
        pnls = sub["pnl"].tolist()
        pf = compute_pf(pnls, cost=4)
        wr = compute_wr(pnls, cost=4)
        mean_pnl = np.mean([p - 4 for p in pnls])
        rprint(f"  {label:<20} {n:>5} {wr:>6.1f}% {pf:>8.2f} {mean_pnl:>+10.1f}")
        if label != "No backing ray":
            pf_by_streak.append((label, pf, n))

    # Determine paradox status
    if len(pf_by_streak) < 2:
        rprint(f"  Paradox status: INSUFFICIENT DATA")
        return "INSUFFICIENT"

    # Check if high streak has lower PF than low streak
    low_streak_pf = pf_by_streak[0][1] if pf_by_streak[0][2] >= 5 else None
    high_streak_pf = None
    for label, pf, n in reversed(pf_by_streak):
        if n >= 5:
            high_streak_pf = pf
            break

    if low_streak_pf is None or high_streak_pf is None:
        rprint(f"  Paradox status: INSUFFICIENT DATA (bins too small)")
        return "INSUFFICIENT"

    if high_streak_pf < low_streak_pf * 0.7:
        rprint(f"  Paradox: CONFIRMED (high streak PF < 70% of low streak PF)")
        return "CONFIRMED"
    elif high_streak_pf > low_streak_pf * 1.3:
        rprint(f"  Paradox: NOT CONFIRMED (high streak outperforms)")
        return "NOT_CONFIRMED"
    else:
        rprint(f"  Paradox: NEUTRAL (no clear directional relationship)")
        return "NEUTRAL"

rprint()
m1_paradox = streak_diagnostic(m1_trades, "Mode 1 (A-Eq ModeA)")
rprint()
m2_paradox = streak_diagnostic(m2_trades, "Mode 2 (B-ZScore RTH)")

# Overall paradox status
if m1_paradox == "CONFIRMED" and m2_paradox == "CONFIRMED":
    paradox_status = "CONFIRMED"
elif m1_paradox == "CONFIRMED" or m2_paradox == "CONFIRMED":
    paradox_status = "MODE_DEPENDENT"
elif m1_paradox == "NOT_CONFIRMED" and m2_paradox == "NOT_CONFIRMED":
    paradox_status = "NOT_CONFIRMED"
else:
    paradox_status = "NEUTRAL"

rprint(f"\n  OVERALL PARADOX STATUS: {paradox_status}")
if paradox_status == "CONFIRMED":
    rprint(f"  -> High backing streak = WORSE outcomes for qualifying trades")
    rprint(f"  -> Surface 2: 'strong backing' becomes potential SKIP signal")
elif paradox_status == "MODE_DEPENDENT":
    rprint(f"  -> Paradox confirmed for one mode, not the other")
    rprint(f"  -> Apply backing streak signals only where relationship holds")
elif paradox_status == "NOT_CONFIRMED":
    rprint(f"  -> High backing streak = protective (original hypothesis holds)")
    rprint(f"  -> Surface 2: 'weak backing' is the skip candidate")


# ============================================================
# STEP 1e: SAVE QUALIFYING TRADES WITH RAY CONTEXT
# ============================================================
all_trades = pd.concat([m1_trades, m2_trades], ignore_index=True)
qual_save_path = OUT / "qualifying_trades_ray_context_v32.csv"
all_trades.to_csv(qual_save_path, index=False)
rprint(f"\n  Saved: {qual_save_path} ({len(all_trades)} trades)")


# ============================================================
# STEP 2: SURFACE 2 — SKIP GATE ANALYSIS
# ============================================================
rprint("\n" + "=" * 70)
rprint("STEP 2: SURFACE 2 — SKIP GATE ANALYSIS")
rprint("=" * 70)
rprint(f"  Focus: Mode 2 ({len(m2_trades)} trades)")
rprint(f"  Mode 1 has {len(m1_trades)} trades — too few losers for segment analysis")
rprint(f"  Paradox status: {paradox_status}")
rprint()

def segment_analysis(trades_df, segments, mode_label):
    """Analyze PF by ray context segments."""
    baseline_pf = compute_pf(trades_df["pnl"].tolist(), cost=4)
    baseline_wr = compute_wr(trades_df["pnl"].tolist(), cost=4)
    baseline_n = len(trades_df)

    rprint(f"  --- {mode_label} Segment Analysis ---")
    rprint(f"  Baseline: N={baseline_n}, PF@4t={baseline_pf:.2f}, WR={baseline_wr:.1f}%")
    rprint()
    rprint(f"  {'Segment':<35} {'N':>5} {'WR%':>7} {'PF@4t':>8} {'vs Pop':>8}")
    rprint(f"  {'-'*68}")

    skip_candidates = []
    for seg_name, mask in segments:
        sub = trades_df[mask]
        n = len(sub)
        if n < 5:
            rprint(f"  {seg_name:<35} {n:>5} {'<5':>7} {'N/A':>8} {'N/A':>8}")
            continue
        pnls = sub["pnl"].tolist()
        pf = compute_pf(pnls, cost=4)
        wr = compute_wr(pnls, cost=4)
        delta = pf - baseline_pf
        rprint(f"  {seg_name:<35} {n:>5} {wr:>6.1f}% {pf:>8.2f} {delta:>+8.2f}")

        # Flag skip candidates: PF < 50% of baseline, N >= 15
        if pf < baseline_pf * 0.5 and n >= 15:
            skip_candidates.append((seg_name, n, pf, wr, delta))

    return skip_candidates

# Define segments for Mode 2
m2_segments = []

# Obstacle ray segments
has_obs = m2_trades["has_obstacle"] == 1
obs_dist = m2_trades["obstacle_dist_ticks"]
m2_segments.append(("Strong obstacle (<=40t)", has_obs & (obs_dist <= 40)))
m2_segments.append(("Mid obstacle (40-80t)", has_obs & (obs_dist > 40) & (obs_dist <= 80)))
m2_segments.append(("Far obstacle (80-100t)", has_obs & (obs_dist > 80) & (obs_dist <= 100)))
m2_segments.append(("No obstacle ray", ~has_obs))

# Backing ray segments (interpretation depends on paradox)
has_back = m2_trades["backing_bounce_streak"].notna()
streak = m2_trades["backing_bounce_streak"]
m2_segments.append(("Strong backing (streak>=5)", has_back & (streak >= 5)))
m2_segments.append(("Moderate backing (streak 1-4)", has_back & (streak >= 1) & (streak <= 4)))
m2_segments.append(("Weak backing (streak=0)", has_back & (streak == 0)))
m2_segments.append(("No backing ray", ~has_back))

# Density segments
density = m2_trades["ray_count_50t"]
m2_segments.append(("Dense rays (>=5 within 50t)", density >= 5))
m2_segments.append(("Sparse rays (<3 within 50t)", density < 3))

# Combined congestion (backing + density)
m2_segments.append(("Congested (streak>=3 + dense)", has_back & (streak >= 3) & (density >= 5)))

skip_candidates_m2 = segment_analysis(m2_trades, m2_segments, "Mode 2")

if skip_candidates_m2:
    rprint(f"\n  SKIP GATE CANDIDATES (Mode 2):")
    for name, n, pf, wr, delta in skip_candidates_m2:
        rprint(f"    {name}: N={n}, PF@4t={pf:.2f}, delta={delta:+.2f}")
else:
    rprint(f"\n  No viable skip gate candidates found (no segment with PF < 50% baseline AND N >= 15)")

# Mode 1 for completeness (expected: too few losers)
rprint()
m1_segments = [
    ("Has obstacle (any)", m1_trades["has_obstacle"] == 1),
    ("No obstacle", m1_trades["has_obstacle"] == 0),
    ("Strong backing (streak>=5)", m1_trades["backing_bounce_streak"].notna() & (m1_trades["backing_bounce_streak"] >= 5)),
    ("Weak/No backing", ~m1_trades["backing_bounce_streak"].notna() | (m1_trades["backing_bounce_streak"] == 0)),
]
skip_candidates_m1 = segment_analysis(m1_trades, m1_segments, "Mode 1 (reference only)")


# ============================================================
# STEP 3: SURFACE 3 — ADAPTIVE EXIT ANALYSIS
# ============================================================
rprint("\n" + "=" * 70)
rprint("STEP 3: SURFACE 3 — ADAPTIVE EXIT ANALYSIS")
rprint("=" * 70)

# 3a: Winner-only analysis (obstacle ray focus)
rprint("\n--- 3a: Winner MFE vs Obstacle Ray (Mode 2) ---")

m2_winners = m2_trades[m2_trades["pnl"] - 4 > 0].copy()
m2_losers = m2_trades[m2_trades["pnl"] - 4 <= 0].copy()
rprint(f"  Mode 2 winners: {len(m2_winners)}, losers: {len(m2_losers)}")

if len(m2_winners) >= 20:
    obs_bins = [
        ("Obstacle <=30t", m2_winners["has_obstacle"].eq(1) & m2_winners["obstacle_dist_ticks"].le(30)),
        ("Obstacle 30-60t", m2_winners["has_obstacle"].eq(1) & m2_winners["obstacle_dist_ticks"].between(30, 60, inclusive="right")),
        ("Obstacle 60-100t", m2_winners["has_obstacle"].eq(1) & m2_winners["obstacle_dist_ticks"].gt(60)),
        ("No obstacle", m2_winners["has_obstacle"].eq(0)),
    ]

    rprint(f"  {'Obstacle Context':<25} {'N':>5} {'Med MFE':>10} {'Med PnL':>10} {'Efficiency':>12}")
    rprint(f"  {'-'*67}")
    for label, mask in obs_bins:
        sub = m2_winners[mask]
        n = len(sub)
        if n < 5:
            rprint(f"  {label:<25} {n:>5} {'<5':>10} {'N/A':>10} {'N/A':>12}")
            continue
        med_mfe = sub["mfe"].median()
        med_pnl = sub["pnl"].median()
        eff = (sub["pnl"] / sub["mfe"].clip(lower=1)).median()
        rprint(f"  {label:<25} {n:>5} {med_mfe:>10.1f} {med_pnl:>10.1f} {eff:>11.1%}")

# 3b: Loser analysis (backing ray focus, Mode 2)
rprint(f"\n--- 3b: Loser Analysis vs Backing Ray (Mode 2, {len(m2_losers)} losers) ---")

if len(m2_losers) >= 10:
    back_bins = [
        ("Streak 0", m2_losers["backing_bounce_streak"].eq(0)),
        ("Streak 1-2", m2_losers["backing_bounce_streak"].between(1, 2)),
        ("Streak 3-5", m2_losers["backing_bounce_streak"].between(3, 5)),
        ("Streak 6+", m2_losers["backing_bounce_streak"].ge(6)),
        ("No backing", m2_losers["backing_bounce_streak"].isna()),
    ]

    rprint(f"  {'Backing Context':<25} {'N':>5} {'Med MAE':>10} {'Med PnL':>10} {'Pct of Losers':>15}")
    rprint(f"  {'-'*70}")
    for label, mask in back_bins:
        sub = m2_losers[mask]
        n = len(sub)
        if n < 3:
            rprint(f"  {label:<25} {n:>5} {'<3':>10} {'N/A':>10} {'N/A':>15}")
            continue
        med_mae = sub["mae"].median()
        med_pnl = sub["pnl"].median()
        pct = n / len(m2_losers) * 100
        rprint(f"  {label:<25} {n:>5} {med_mae:>10.1f} {med_pnl:>10.1f} {pct:>14.1f}%")

# 3c-d: Candidate adaptive exit rules (Mode 2)
rprint(f"\n--- 3c/3d: Adaptive Exit Rule Testing (Mode 2) ---")
rprint(f"  Baseline Mode 2: {len(m2_trades)} trades, PF@4t={compute_pf(m2_trades['pnl'].tolist(), 4):.2f}")
rprint()

# Test candidate rules by re-simulating with modified exits
def test_adaptive_exit(m2_touches_df, rule_name, exit_modifier, bar_arr, n_bars_total):
    """Re-simulate Mode 2 with modified exits."""
    subset = m2_touches_df.sort_values("RotBarIndex").copy()
    pnls = []
    in_trade_until = -1

    for _, row in subset.iterrows():
        rbi = int(row["RotBarIndex"])
        entry_bar = rbi + 1
        if entry_bar <= in_trade_until:
            continue
        direction = 1 if "DEMAND" in str(row["TouchType"]) else -1
        zw = row.get("ZoneWidthTicks", 100)

        # Base ZONEREL exits
        stop, target, tcap = resolve_zonerel_exits(zw, M2_ZONEREL)

        # Apply modifier
        stop, target, tcap = exit_modifier(row, stop, target, tcap)

        pnl, bh, etype, mfe, mae = sim_trade(
            entry_bar, direction, stop, target, 0, 0,
            tcap, bar_arr, n_bars_total)

        if pnl is not None:
            pnls.append(pnl)
            in_trade_until = entry_bar + bh - 1

    pf4 = compute_pf(pnls, 4)
    wr = compute_wr(pnls, 4)
    return pnls, pf4, wr

# Rule 1: Obstacle ceiling — tighten target if obstacle ray is closer
def obstacle_ceiling(row, stop, target, tcap):
    obs_dist = row.get("obstacle_dist_ticks", np.nan)
    if not np.isnan(obs_dist) and obs_dist < target:
        target = max(int(obs_dist - 5), 10)  # min 10t target
    return stop, target, tcap

# Rule 2: No-obstacle extension — widen target by 20% if no obstacle
def no_obstacle_extension(row, stop, target, tcap):
    has_obs = row.get("has_obstacle", 0)
    if has_obs == 0:
        target = int(target * 1.2)
    return stop, target, tcap

# Rule 3: Dense ray caution — tighten time cap in congested areas
def dense_ray_caution(row, stop, target, tcap):
    density = row.get("ray_count_50t", 0)
    if density >= 5:
        tcap = max(int(tcap * 0.6), 30)
    return stop, target, tcap

rules = [
    ("Obstacle ceiling", obstacle_ceiling),
    ("No-obstacle extension (+20%)", no_obstacle_extension),
    ("Dense ray caution (TC 60%)", dense_ray_caution),
]

baseline_m2_pf4 = compute_pf(m2_trades["pnl"].tolist(), 4)
baseline_m2_n = len(m2_trades)

rprint(f"  {'Rule':<35} {'PF@4t':>8} {'Trades':>7} {'WR%':>7} {'dPF':>8}")
rprint(f"  {'-'*70}")
rprint(f"  {'Baseline (ZONEREL)':<35} {baseline_m2_pf4:>8.2f} {baseline_m2_n:>7} {compute_wr(m2_trades['pnl'].tolist(), 4):>6.1f}% {'---':>8}")

rule_results = []
for rule_name, modifier in rules:
    pnls, pf4, wr = test_adaptive_exit(m2_touches, rule_name, modifier, bar_arr_p1, n_bars_p1)
    dpf = pf4 - baseline_m2_pf4
    rprint(f"  {rule_name:<35} {pf4:>8.2f} {len(pnls):>7} {wr:>6.1f}% {dpf:>+8.2f}")
    rule_results.append({"name": rule_name, "pf4": pf4, "trades": len(pnls),
                          "wr": wr, "dpf": dpf, "pnls": pnls})

# Identify rules that improved PF
improved_rules = [r for r in rule_results if r["dpf"] > 0]
if improved_rules:
    rprint(f"\n  Rules with positive dPF: {len(improved_rules)}")
    for r in improved_rules:
        rprint(f"    {r['name']}: dPF={r['dpf']:+.2f}")
else:
    rprint(f"\n  No adaptive exit rule improved PF@4t on P1.")


# ============================================================
# STEP 4: P2 VALIDATION (if any skip gate or exit rule improved P1)
# ============================================================
rprint("\n" + "=" * 70)
rprint("STEP 4: P2 VALIDATION")
rprint("=" * 70)

has_p2_candidates = bool(skip_candidates_m2) or bool(improved_rules)

if has_p2_candidates:
    rprint("  Loading P2 data for validation...")

    # Load P2 bar data
    bar_p2 = pd.read_csv(DATA / "NQ_bardata_P2.csv", skipinitialspace=True)
    bar_p2.columns = bar_p2.columns.str.strip()
    bar_arr_p2 = bar_p2[["Open", "High", "Low", "Last"]].to_numpy(dtype=np.float64)
    n_bars_p2 = len(bar_arr_p2)
    rprint(f"  P2 bars: {n_bars_p2}")

    # Load P2 touch data (merged files used by prompt3)
    p2a_raw = pd.read_csv(DATA / "NQ_merged_P2a.csv")
    p2b_raw = pd.read_csv(DATA / "NQ_merged_P2b.csv")
    p2a = p2a_raw[p2a_raw["RotBarIndex"] >= 0].reset_index(drop=True)
    p2b = p2b_raw[p2b_raw["RotBarIndex"] >= 0].reset_index(drop=True)
    p2_all = pd.concat([p2a, p2b], ignore_index=True)
    rprint(f"  P2 touches (after RotBarIndex filter): {len(p2_all)}")

    # Compute features on P2 using P1-frozen params
    # F01, F04, F05, F09, F10, F13, F21
    touch_dt = pd.to_datetime(p2_all["DateTime"])
    touch_mins = touch_dt.dt.hour.values * 60 + touch_dt.dt.minute.values
    session = np.full(len(p2_all), "Midday", dtype=object)
    session[touch_mins < 360] = "Overnight"
    session[(touch_mins >= 360) & (touch_mins < 570)] = "PreRTH"
    session[(touch_mins >= 570) & (touch_mins < 660)] = "OpeningDrive"
    session[(touch_mins >= 660) & (touch_mins < 840)] = "Midday"
    session[(touch_mins >= 840) & (touch_mins < 1020)] = "Close"
    session[touch_mins >= 1020] = "Overnight"
    p2_all["F05"] = session
    p2_all["F01"] = p2_all["SourceLabel"]
    p2_all["F04"] = p2_all["CascadeState"].replace("UNKNOWN", "NO_PRIOR")
    p2_all["F21"] = p2_all["ZoneAgeBars"]
    p2_all["F02"] = p2_all["ZoneWidthTicks"]

    # F09: ZW/ATR
    bar_atr_p2 = bar_p2["ATR"].to_numpy(dtype=np.float64)
    atr_vals = []
    for rbi in p2_all["RotBarIndex"].values:
        rbi = int(rbi)
        if 0 <= rbi < n_bars_p2 and bar_atr_p2[rbi] > 0:
            atr_vals.append(bar_atr_p2[rbi])
        else:
            atr_vals.append(np.nan)
    p2_all["F09"] = p2_all["ZoneWidthTicks"].values * TICK / np.array(atr_vals)

    # F10: Prior Penetration
    p2_all["ZoneID"] = (p2_all["TouchType"].astype(str) + "|" +
                         p2_all["ZoneTop"].astype(str) + "|" +
                         p2_all["ZoneBot"].astype(str) + "|" +
                         p2_all["SourceLabel"].astype(str))
    prior_pen = {}
    for zone_id, group in p2_all.sort_values(["ZoneID", "TouchSequence"]).groupby("ZoneID"):
        group = group.sort_values("TouchSequence")
        prev_pen = np.nan
        for idx, row in group.iterrows():
            if row["TouchSequence"] == 1:
                prior_pen[idx] = np.nan
            else:
                prior_pen[idx] = prev_pen
            prev_pen = row["Penetration"]
    p2_all["F10"] = p2_all.index.map(prior_pen)

    # F13: Close position
    rot_idx_p2 = p2_all["RotBarIndex"].values.astype(int)
    is_long_p2 = p2_all["TouchType"].str.contains("DEMAND").values
    tb_h = np.array([bar_arr_p2[max(0, min(i, n_bars_p2-1)), 1] for i in rot_idx_p2])
    tb_l = np.array([bar_arr_p2[max(0, min(i, n_bars_p2-1)), 2] for i in rot_idx_p2])
    tb_c = np.array([bar_arr_p2[max(0, min(i, n_bars_p2-1)), 3] for i in rot_idx_p2])
    hl_d = tb_h - tb_l
    p2_all["F13"] = np.where(
        hl_d > 0,
        np.where(is_long_p2, (tb_c - tb_l) / hl_d, (tb_h - tb_c) / hl_d),
        0.5)

    # Score P2 touches
    p2_all["Score_AEq"] = score_aeq(p2_all)
    p2_all["Score_BZScore"] = score_bzscore(p2_all)

    # P2 waterfall
    p2_m1_mask = p2_all["Score_AEq"] >= M1_THRESHOLD
    p2_m1 = p2_all[p2_m1_mask].copy()
    p2_m1["mode"] = "M1"

    p2_m1_keys = set(zip(p2_m1["BarIndex"], p2_m1["TouchType"], p2_m1["SourceLabel"]))
    p2_bz_keys = list(zip(p2_all["BarIndex"], p2_all["TouchType"], p2_all["SourceLabel"]))
    p2_is_m1 = pd.Series([k in p2_m1_keys for k in p2_bz_keys])

    p2_m2_mask = (
        (p2_all["Score_BZScore"] >= M2_THRESHOLD) &
        (p2_all["F05"].isin(rth_sessions)) &
        (p2_all["TouchSequence"] <= M2_FILTERS.get("seq_max", 2)) &
        (p2_all["SourceLabel"].apply(tf_minutes) <= 120) &
        ~p2_is_m1
    )
    p2_m2 = p2_all[p2_m2_mask].copy()
    p2_m2["mode"] = "M2"

    rprint(f"  P2 Mode 1 qualifying: {len(p2_m1)}")
    rprint(f"  P2 Mode 2 qualifying: {len(p2_m2)}")

    # Compute ray features for P2
    rprint("  Computing P2 ray features...")
    ray_ctx_p2 = pd.read_csv(TOUCH_DIR / "NQ_ray_context_P2.csv")
    ray_ctx_p2_htf = ray_ctx_p2[ray_ctx_p2["RayTF"].apply(rfs.is_htf)].copy()

    # Compute backing features from P2 ray context
    # Use same framework as P1
    zte_raw_p2 = pd.read_csv(TOUCH_DIR / "NQ_ZTE_raw_P2.csv")
    zte_raw_p2 = zte_raw_p2[zte_raw_p2["TouchType"] != "VP_RAY"].copy()

    ray_ref_p2 = pd.read_csv(TOUCH_DIR / "NQ_ray_reference_P2.csv")

    # Extract rays and build lifecycle for P2
    bars_vol_p2 = rfs.load_bar_data(BAR_VOL_DIR / "NQ_BarData_250vol_rot_P2.csv")
    bars_vol_p2["BarIdx"] = bars_vol_p2.index
    b10_p2 = rfs.load_bar_data(BAR_TIME_DIR / "NQ_BarData_10sec_rot_P2.csv")
    b10_p2 = b10_p2.set_index("DateTime").sort_index()
    bars_15m_p2 = b10_p2.resample("15min").agg({
        "Open": "first", "High": "max", "Low": "min",
        "Close": "last", "Volume": "sum"
    }).dropna().reset_index()
    del b10_p2

    rays_df_p2 = rfs.extract_rays(zte_raw_p2, ray_ctx_p2_htf, ray_ref_p2, len(bars_vol_p2))
    ixns_p2 = rfs.detect_interactions(bars_vol_p2, rays_df_p2, bars_15m_p2, threshold=PROX_THRESHOLD)
    ixns_p2_valid = ixns_p2[ixns_p2["outcome"].isin(["BOUNCE", "BREAK"])]
    lifecycle_p2 = rfs.build_lifecycle_lookup(ixns_p2_valid, rays_df_p2, len(bars_vol_p2))
    zte_p2_enriched = rfs.compute_ray_features_for_touches(
        zte_raw_p2, ray_ctx_p2_htf, rays_df_p2, lifecycle_p2, ixns_p2, bars_vol_p2)

    # Join P2 ray features to qualifying touches
    zte_p2_enriched["_jk"] = (
        zte_p2_enriched["BarIndex"].astype(str) + "_" +
        zte_p2_enriched["TouchType"] + "_" +
        zte_p2_enriched["SourceLabel"]
    )
    p2_ray_feats = zte_p2_enriched[["_jk"] + BACKING_COLS].drop_duplicates(subset="_jk")

    for df_label, p2_df in [("M1", p2_m1), ("M2", p2_m2)]:
        p2_df["_jk"] = (
            p2_df["BarIndex"].astype(str) + "_" +
            p2_df["TouchType"] + "_" +
            p2_df["SourceLabel"]
        )
        merged = p2_df.merge(p2_ray_feats, on="_jk", how="left", suffixes=("", "_ray"))
        for col in BACKING_COLS:
            ray_col = col + "_ray" if col + "_ray" in merged.columns else col
            if ray_col in merged.columns:
                p2_df[col] = merged[ray_col].values

    # Compute P2 obstacle features
    p2_m2 = compute_obstacle_features(p2_m2, ray_ctx_p2_htf, zte_raw_p2)
    p2_m2 = compute_ray_density(p2_m2, ray_ctx_p2_htf)

    # P2 baseline simulation
    p2_m1_trades = simulate_population(p2_m1, "M1", bar_arr_p2, n_bars_p2)
    p2_m2_trades = simulate_population(p2_m2, "M2", bar_arr_p2, n_bars_p2)

    rprint(f"  P2 Mode 1 trades: {len(p2_m1_trades)}")
    rprint(f"  P2 Mode 2 trades: {len(p2_m2_trades)}")

    if len(p2_m1_trades) > 0:
        p2_m1_pf4 = compute_pf(p2_m1_trades["pnl"].tolist(), 4)
        rprint(f"    M1 PF@4t: {p2_m1_pf4:.2f}")
    if len(p2_m2_trades) > 0:
        p2_m2_pf4 = compute_pf(p2_m2_trades["pnl"].tolist(), 4)
        rprint(f"    M2 PF@4t: {p2_m2_pf4:.2f}")

    # P2 combined baseline
    p2_combined_pnls = list(p2_m1_trades["pnl"]) + list(p2_m2_trades["pnl"])
    p2_combined_pf4 = compute_pf(p2_combined_pnls, 4)
    p2_combined_n = len(p2_combined_pnls)
    rprint(f"  P2 combined: {p2_combined_n} trades, PF@4t={p2_combined_pf4:.2f}")

    # Validate adaptive exit rules on P2
    if improved_rules:
        rprint(f"\n  --- P2 Adaptive Exit Validation ---")
        rprint(f"  {'Rule':<35} {'P1 PF@4t':>9} {'P2 PF@4t':>9} {'P2 Trades':>10} {'Verdict':>10}")
        rprint(f"  {'-'*78}")

        for r in improved_rules:
            rule_name = r["name"]
            # Find the modifier function
            modifier = None
            for rn, mod in rules:
                if rn == rule_name:
                    modifier = mod
                    break
            if modifier is None:
                continue

            p2_pnls, p2_pf4_rule, p2_wr = test_adaptive_exit(
                p2_m2, rule_name, modifier, bar_arr_p2, n_bars_p2)
            p2_dpf = p2_pf4_rule - p2_m2_pf4
            verdict = "PASS" if p2_dpf >= 0 else "FAIL (overfit)"
            rprint(f"  {rule_name:<35} {r['pf4']:>9.2f} {p2_pf4_rule:>9.2f} {len(p2_pnls):>10} {verdict:>10}")

    # Validate skip gates on P2
    if skip_candidates_m2:
        rprint(f"\n  --- P2 Skip Gate Validation ---")
        # Join ray features to P2 M2 trades
        for col in BACKING_COLS + ["obstacle_dist_ticks", "has_obstacle", "ray_count_50t"]:
            if col in p2_m2.columns:
                col_map = p2_m2[col]
                if "touch_idx" in p2_m2_trades.columns:
                    p2_m2_trades[col] = p2_m2_trades["touch_idx"].map(col_map)

        for seg_name, n_p1, pf_p1, wr_p1, delta_p1 in skip_candidates_m2:
            # Reconstruct mask for P2
            # (simplified — actual implementation would use same segment definitions)
            rprint(f"  Skip gate '{seg_name}': P1 PF={pf_p1:.2f} (N={n_p1})")
            rprint(f"    P2 validation requires matching segment definition")

else:
    rprint("  No candidates to validate on P2 (no skip gates or adaptive exits improved P1).")
    rprint("  Skipping P2 validation.")


# ============================================================
# STEP 5: VERDICT
# ============================================================
rprint("\n" + "=" * 70)
rprint("VERDICT")
rprint("=" * 70)

has_skip_gate = bool(skip_candidates_m2)
has_adaptive = bool(improved_rules)

if has_skip_gate and has_adaptive:
    verdict = "BOTH_CANDIDATES"
    rprint(f"\n  VERDICT: BOTH — skip gate and adaptive exit candidates identified")
    rprint(f"  P2 validation determines final status.")
elif has_skip_gate:
    verdict = "SKIP_GATE_CANDIDATE"
    rprint(f"\n  VERDICT: SKIP GATE CANDIDATE identified")
elif has_adaptive:
    verdict = "ADAPTIVE_EXIT_CANDIDATE"
    rprint(f"\n  VERDICT: ADAPTIVE EXIT CANDIDATE identified")
else:
    verdict = "NO_VIABLE_OVERLAY"
    rprint(f"\n  VERDICT: NO VIABLE OVERLAY")
    rprint(f"  Ray context does not meaningfully improve qualifying trade outcomes.")
    rprint(f"  The 7-feature model captures sufficient information.")
    rprint(f"  Ray value is redirected to Surface 4 (ray-only archetype, separate pipeline).")

rprint(f"\n  Paradox status: {paradox_status}")
rprint(f"  Model: FROZEN at v3.2 (7 features)")
rprint(f"  Elapsed: {time_mod.time() - t0:.1f}s")


# ============================================================
# WRITE REPORT
# ============================================================
report_path = OUT / "ray_conditional_analysis_v32.md"
report_md = ["# Ray Conditional Analysis on Qualifying Trades — Analysis B (v3.2)\n"]
report_md.append(f"Generated: {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M')}\n")
report_md.append("```")
report_md.extend(report)
report_md.append("```\n")

# Structured sections
report_md.append("## Section 1: Qualifying Population\n")
report_md.append(f"- Mode 1 (A-Eq ModeA): {len(m1_touches)} touches, {len(m1_trades)} trades")
report_md.append(f"- Mode 2 (B-ZScore RTH): {len(m2_touches)} touches, {len(m2_trades)} trades")
report_md.append(f"- Backing ray coverage: M1={m1_touches['backing_bounce_streak'].notna().sum()}/{len(m1_touches)}, M2={m2_touches['backing_bounce_streak'].notna().sum()}/{len(m2_touches)}")
report_md.append(f"- Obstacle ray coverage: M1={m1_obs}/{len(m1_touches)}, M2={m2_obs}/{len(m2_touches)}")
report_md.append(f"- **Paradox diagnostic: {paradox_status}**")
report_md.append("")

report_md.append("## Section 2: Surface 2 (Skip Gate)\n")
if skip_candidates_m2:
    report_md.append("**Skip gate candidates identified:**\n")
    for name, n, pf, wr, delta in skip_candidates_m2:
        report_md.append(f"- {name}: N={n}, PF@4t={pf:.2f}, delta={delta:+.2f}")
else:
    report_md.append("No viable skip gate found. No segment showed PF < 50% of baseline with N >= 15.\n")

report_md.append("\n## Section 3: Surface 3 (Adaptive Exits)\n")
if improved_rules:
    report_md.append("**Rules that improved P1 PF:**\n")
    for r in improved_rules:
        report_md.append(f"- {r['name']}: PF@4t={r['pf4']:.2f} (dPF={r['dpf']:+.2f})")
else:
    report_md.append("No adaptive exit rule improved PF@4t on P1.\n")

report_md.append(f"\n## Section 4: Verdict\n")
report_md.append(f"**{verdict}**\n")
if verdict == "NO_VIABLE_OVERLAY":
    report_md.append("Ray context does not meaningfully improve qualifying trade outcomes. ")
    report_md.append("The 7-feature scoring model captures sufficient information through ")
    report_md.append("the existing feature set. Ray value redirected to Surface 4 ")
    report_md.append("(ray-only archetype).\n")
report_md.append(f"\n- Model: **FROZEN** at v3.2")
report_md.append(f"- Paradox: **{paradox_status}**")
report_md.append("")

with open(report_path, "w", encoding="utf-8") as f:
    f.write("\n".join(report_md))

rprint(f"\n  Report saved: {report_path}")
rprint(f"  Done.")
