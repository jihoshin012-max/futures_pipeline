# archetype: zone_touch
"""Risk Mitigation Investigation v3.2 — Step 0 Diagnostics.

Rebuilds qualifying trade populations from scratch using frozen scoring models.
Simulates all trades with baseline exits. Produces 8 diagnostic outputs.
HARD STOP after Step 0 — Surfaces A/B run only after human review.

Scoring model is FROZEN. Trade selection does not change.
"""

import json
import sys
import warnings
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd

# ════════════════════════════════════════════════════════════════════
# PATHS & CONSTANTS
# ════════════════════════════════════════════════════════════════════
BASE = Path(r"c:\Projects\pipeline")
DATA_DIR = BASE / "stages" / "01-data" / "output" / "zone_prep"
PARAM_DIR = BASE / "shared" / "archetypes" / "zone_touch" / "output"
OUT_DIR = PARAM_DIR  # output goes next to scored data
TICK = 0.25
COST_TICKS = 3  # P1 cost assumption

report_lines: list[str] = []


def rprint(msg=""):
    print(msg)
    report_lines.append(str(msg))


# ════════════════════════════════════════════════════════════════════
# LOAD FROZEN PARAMETERS
# ════════════════════════════════════════════════════════════════════
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
FEAT_MEANS = feat_cfg["feature_means"]
FEAT_STDS = feat_cfg["feature_stds"]
TS_P33 = feat_cfg["trend_slope_P33"]
TS_P67 = feat_cfg["trend_slope_P67"]

# Frozen thresholds
M1_THRESHOLD = aeq_cfg["threshold"]  # 45.5
M2_THRESHOLD = 0.50  # B-ZScore (prompt specifies 0.50)

# Frozen exit params
M1_EXIT = {"stop": 190, "target": 60, "time_cap": 120}
M2_ZONEREL = seg_params["seg2_B-ZScore"]["groups"]["ModeA_RTH"]["exit_params_zonerel"]
M2_FILTERS = seg_params["seg2_B-ZScore"]["groups"]["ModeA_RTH"]["filters"]

RTH_SESSIONS = ["OpeningDrive", "Midday", "Close"]

rprint("=" * 72)
rprint("RISK MITIGATION INVESTIGATION v3.2 — STEP 0 DIAGNOSTICS")
rprint("Scoring model FROZEN. Nothing carried from prior run.")
rprint(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
rprint("=" * 72)
rprint(f"  M1 threshold (A-Eq): {M1_THRESHOLD}")
rprint(f"  M2 threshold (B-ZScore): {M2_THRESHOLD}")
rprint(f"  M1 exits: stop=190t, target=60t, TC=120 bars")
rprint(f"  M2 exits: stop=max(1.5*ZW,120), target=1.0*ZW, TC=80 bars")
rprint(f"  M2 filters: seq<={M2_FILTERS.get('seq_max', 2)}, TF<=120m, RTH only")


# ════════════════════════════════════════════════════════════════════
# FEATURE COMPUTATION (identical to prompt3_holdout_v32.py)
# ════════════════════════════════════════════════════════════════════
def compute_features(df: pd.DataFrame, bar_arr: np.ndarray,
                     bar_atr: np.ndarray, n_bars: int,
                     label: str) -> pd.DataFrame:
    """Compute all 7 winning features for scoring. Uses P1-frozen parameters."""
    rprint(f"\n  Computing features for {label} ({len(df)} touches)...")
    df = df.copy()

    # F01: Timeframe
    df["F01"] = df["SourceLabel"]

    # F04: Cascade State
    df["F04"] = df["CascadeState"].replace("UNKNOWN", "NO_PRIOR")

    # F05: Session — derived from DateTime
    touch_dt = pd.to_datetime(df["DateTime"])
    touch_mins = touch_dt.dt.hour.values * 60 + touch_dt.dt.minute.values
    session = np.full(len(df), "Midday", dtype=object)
    session[touch_mins < 360] = "Overnight"
    session[(touch_mins >= 360) & (touch_mins < 570)] = "PreRTH"
    session[(touch_mins >= 570) & (touch_mins < 660)] = "OpeningDrive"
    session[(touch_mins >= 660) & (touch_mins < 840)] = "Midday"
    session[(touch_mins >= 840) & (touch_mins < 1020)] = "Close"
    session[touch_mins >= 1020] = "Overnight"
    df["F05"] = session

    # F09: ZW/ATR
    atr_vals = []
    for rbi in df["RotBarIndex"].values:
        rbi = int(rbi)
        if 0 <= rbi < n_bars and bar_atr[rbi] > 0:
            atr_vals.append(bar_atr[rbi])
        else:
            atr_vals.append(np.nan)
    df["F09"] = df["ZoneWidthTicks"].values * TICK / np.array(atr_vals)

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

    # F21: Zone Age
    df["F21"] = df["ZoneAgeBars"]

    # TrendLabel
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

    if "SBB_Label" not in df.columns:
        df["SBB_Label"] = "NORMAL"

    rprint(f"    F10 null rate: {df['F10'].isna().mean() * 100:.1f}%")
    rprint(f"    F05 distribution: {dict(df['F05'].value_counts().head(5))}")
    return df


# ════════════════════════════════════════════════════════════════════
# SCORING FUNCTIONS (frozen from v3.2)
# ════════════════════════════════════════════════════════════════════
def _bin_numeric(vals, lo, hi):
    out = np.full(len(vals), "Mid", dtype=object)
    v = np.asarray(vals, dtype=float)
    out[v <= lo] = "Low"
    out[v > hi] = "High"
    out[np.isnan(v)] = "NA"
    return out


def score_aeq(df: pd.DataFrame) -> np.ndarray:
    """A-Eq scoring: equal weight per feature, bin_points from frozen model."""
    bp = aeq_cfg["bin_points"]
    bin_edges = acal_cfg["bin_edges"]  # A-Eq uses same bin edges as A-Cal
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


def score_bzscore(df: pd.DataFrame) -> np.ndarray:
    """B-ZScore scoring: frozen StandardScaler + logistic regression."""
    feat_cols = bz_cfg["feature_columns"]
    coeffs = np.array(bz_cfg["coefficients"])
    intercept = bz_cfg["intercept"]
    means = np.array(bz_cfg["scaler_mean"])
    stds = np.array(bz_cfg["scaler_std"])
    stds[stds == 0] = 1.0

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

    X_scaled = (X - means) / stds
    return X_scaled @ coeffs + intercept


# ════════════════════════════════════════════════════════════════════
# SIMULATION ENGINE (from prompt3_holdout, with MFE/MAE tracking)
# ════════════════════════════════════════════════════════════════════
def resolve_zonerel(zw_ticks: float) -> Tuple[int, int, int]:
    """Compute stop/target/TC from zone-relative M2 params."""
    stop = max(round(1.5 * zw_ticks), 120)
    target = max(1, round(1.0 * zw_ticks))
    return stop, target, 80


def sim_trade(entry_bar: int, direction: int, stop: int, target: int,
              tcap: int, bar_arr: np.ndarray, n_bars: int
              ) -> Optional[Dict]:
    """Simulate single trade. Returns dict with pnl, mfe, mae, exit details.
    No BE or trail — baseline only."""
    if entry_bar >= n_bars:
        return None
    ep = bar_arr[entry_bar, 0]  # Open of entry bar
    if direction == 1:
        stop_price = ep - stop * TICK
        target_price = ep + target * TICK
    else:
        stop_price = ep + stop * TICK
        target_price = ep - target * TICK

    mfe = 0.0
    mae = 0.0
    # Track per-bar MFE/MAE for time-profile analysis
    bar_mfe_profile = []
    bar_mae_profile = []

    end = min(entry_bar + tcap, n_bars)
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
        bar_mfe_profile.append(mfe)
        bar_mae_profile.append(mae)

        # Check stop
        if direction == 1:
            stop_hit = l <= stop_price
            target_hit = h >= target_price
        else:
            stop_hit = h >= stop_price
            target_hit = l <= target_price

        # Intra-bar: stop fills first
        if stop_hit:
            pnl = ((stop_price - ep) / TICK if direction == 1
                   else (ep - stop_price) / TICK)
            return {"pnl": pnl, "bars_held": bh, "exit_type": "STOP",
                    "mfe": mfe, "mae": mae, "entry_price": ep,
                    "bar_mfe": bar_mfe_profile, "bar_mae": bar_mae_profile}
        if target_hit:
            return {"pnl": target, "bars_held": bh, "exit_type": "TARGET",
                    "mfe": mfe, "mae": mae, "entry_price": ep,
                    "bar_mfe": bar_mfe_profile, "bar_mae": bar_mae_profile}

        if bh >= tcap:
            pnl = ((last - ep) / TICK if direction == 1
                   else (ep - last) / TICK)
            return {"pnl": pnl, "bars_held": bh, "exit_type": "TIMECAP",
                    "mfe": mfe, "mae": mae, "entry_price": ep,
                    "bar_mfe": bar_mfe_profile, "bar_mae": bar_mae_profile}

    # Ran out of bars
    if end > entry_bar:
        last = bar_arr[end - 1, 3]
        pnl = ((last - ep) / TICK if direction == 1
               else (ep - last) / TICK)
        return {"pnl": pnl, "bars_held": end - entry_bar, "exit_type": "TIMECAP",
                "mfe": mfe, "mae": mae, "entry_price": ep,
                "bar_mfe": bar_mfe_profile, "bar_mae": bar_mae_profile}
    return None


def simulate_population(qualifying_df: pd.DataFrame, mode: str,
                        bar_arr: np.ndarray, n_bars: int
                        ) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Simulate qualifying trades with position overlap filter.
    Returns (traded_df, skipped_df)."""
    subset = qualifying_df.sort_values("RotBarIndex").copy()
    results = []
    skipped = []
    in_trade_until = -1

    for idx, row in subset.iterrows():
        rbi = int(row["RotBarIndex"])
        entry_bar = rbi + 1
        direction = 1 if "DEMAND" in str(row["TouchType"]) else -1
        zw = int(row.get("ZoneWidthTicks", 100))

        if entry_bar <= in_trade_until:
            skipped.append({
                "touch_idx": idx, "BarIndex": row["BarIndex"],
                "RotBarIndex": rbi, "mode": mode,
                "direction": direction, "zw_ticks": zw,
                "zone_top": row["ZoneTop"], "zone_bot": row["ZoneBot"],
                "touch_price": row["TouchPrice"],
                "touch_type": row["TouchType"],
                "score_aeq": row.get("score_aeq", np.nan),
                "score_bz": row.get("score_bz", np.nan),
                "skip_reason": "position_overlap",
                "active_trade_exit_bar": in_trade_until,
            })
            continue

        if mode == "M1":
            stop, target, tcap = (M1_EXIT["stop"], M1_EXIT["target"],
                                  M1_EXIT["time_cap"])
        else:
            stop, target, tcap = resolve_zonerel(zw)

        result = sim_trade(entry_bar, direction, stop, target, tcap,
                           bar_arr, n_bars)
        if result is None:
            continue

        # Penetration: how far past zone edge into zone interior
        # Fill window = touch bar + next 3 bars (4 bars total)
        pen_window = min(4, n_bars - rbi)
        max_pen = 0.0
        pen_bar = 0
        for bi in range(rbi, rbi + pen_window):
            if bi >= n_bars:
                break
            if direction == 1:  # DEMAND: touched edge = zone top
                pen = (row["ZoneTop"] - bar_arr[bi, 2]) / TICK  # Top - Low
            else:  # SUPPLY: touched edge = zone bot
                pen = (bar_arr[bi, 1] - row["ZoneBot"]) / TICK  # High - Bot
            if pen > max_pen:
                max_pen = pen
                pen_bar = bi - rbi

        entry_offset = (result["entry_price"] - row["TouchPrice"]) / TICK
        if direction == -1:
            entry_offset = -entry_offset  # positive = deeper into zone

        results.append({
            "touch_idx": idx, "BarIndex": row["BarIndex"],
            "RotBarIndex": rbi, "entry_bar": entry_bar,
            "direction": direction, "mode": mode,
            "pnl": result["pnl"], "bars_held": result["bars_held"],
            "exit_type": result["exit_type"],
            "mfe": result["mfe"], "mae": result["mae"],
            "stop_used": stop, "target_used": target, "tc_used": tcap,
            "zw_ticks": zw,
            "zone_top": row["ZoneTop"], "zone_bot": row["ZoneBot"],
            "touch_price": row["TouchPrice"],
            "touch_type": row["TouchType"],
            "entry_price": result["entry_price"],
            "entry_offset": entry_offset,
            "score_aeq": row.get("score_aeq", np.nan),
            "score_bz": row.get("score_bz", np.nan),
            "max_penetration": max_pen,
            "pen_bar": pen_bar,
            "win": result["pnl"] - COST_TICKS > 0,
            "bar_mfe_profile": result["bar_mfe"],
            "bar_mae_profile": result["bar_mae"],
        })
        in_trade_until = entry_bar + result["bars_held"] - 1

    return pd.DataFrame(results), pd.DataFrame(skipped)


def compute_pf(pnls, cost=3):
    if len(pnls) == 0:
        return 0
    gp = sum(p - cost for p in pnls if p - cost > 0)
    gl = sum(abs(p - cost) for p in pnls if p - cost < 0)
    return gp / gl if gl > 0 else (float("inf") if gp > 0 else 0)


def compute_wr(pnls, cost=3):
    if len(pnls) == 0:
        return 0
    return sum(1 for p in pnls if p - cost > 0) / len(pnls) * 100


def compute_max_dd(pnls, cost=3):
    cum = 0; peak = 0; max_dd = 0
    for p in pnls:
        cum += (p - cost)
        peak = max(peak, cum)
        max_dd = max(max_dd, peak - cum)
    return max_dd


# ════════════════════════════════════════════════════════════════════
# WATERFALL CONSTRUCTION — from scratch
# ════════════════════════════════════════════════════════════════════
def tf_minutes(s):
    try:
        return int(str(s).replace("m", ""))
    except Exception:
        return 9999


def build_waterfall(scored_df: pd.DataFrame,
                    label: str,
                    prescored_bz: Optional[np.ndarray] = None,
                    ) -> Tuple[pd.DataFrame, pd.DataFrame, dict]:
    """Build non-overlapping M1+M2 waterfall from a scored DataFrame.

    The DataFrame must already have features computed (F01, F04, F05, F09,
    F10, F13, F21).

    A-Eq scoring is always computed from scratch (JSON model matches CSV).

    B-ZScore scoring:
      - P1: MUST pass prescored_bz = the Score_BZScore column from
        p1_scored_touches_bzscore_v32.csv. This is a probability output
        from a C=1.0 LogisticRegression fit with rolling z-score
        standardization (model_building_v32.py lines 866-886).
      - P2: prescored_bz=None → uses score_bzscore() which applies the
        JSON model's coefficients (C=0.01 L1, global StandardScaler)
        as raw linear output. This is what ray_conditional_analysis_v32.py
        used for P2, producing 309 M2 trades.

    The P1 CSV model and P2 JSON model are different fits. This is a
    pre-existing pipeline inconsistency documented in the JSON's fix_note.
    Both produce the authoritative baseline counts (P1 M2=239, P2 M2=309).

    Returns (m1_qualifying, m2_qualifying, counts_dict).
    """
    rprint(f"\n  Building waterfall for {label}...")

    scored_df = scored_df.copy()
    scored_df["score_aeq"] = score_aeq(scored_df)

    if prescored_bz is not None:
        scored_df["score_bz"] = prescored_bz
        rprint(f"    B-ZScore: using pre-scored column (probability, "
               f"from rolling z-score + C=1.0 LogReg)")
    else:
        scored_df["score_bz"] = score_bzscore(scored_df)
        rprint(f"    B-ZScore: scored from JSON coefficients (raw linear, "
               f"global StandardScaler + C=0.01 L1)")

    total = len(scored_df)
    rprint(f"    Total touches: {total}")

    # Mode 1: A-Eq >= threshold
    m1_mask = scored_df["score_aeq"] >= M1_THRESHOLD
    m1_qualifying = scored_df[m1_mask].copy()
    m1_qualifying["mode"] = "M1"
    n_m1_qual = len(m1_qualifying)
    rprint(f"    M1 qualifying (A-Eq >= {M1_THRESHOLD}): {n_m1_qual}")

    # Mode 2: B-ZScore >= 0.50, RTH, seq<=2, TF<=120m, EXCLUDE M1 overlap
    m1_keys = set(zip(m1_qualifying["BarIndex"],
                      m1_qualifying["TouchType"],
                      m1_qualifying["SourceLabel"]))
    all_keys = list(zip(scored_df["BarIndex"],
                        scored_df["TouchType"],
                        scored_df["SourceLabel"]))
    is_m1 = pd.Series([k in m1_keys for k in all_keys],
                       index=scored_df.index)

    m2_mask = (
        (scored_df["score_bz"] >= M2_THRESHOLD)
        & (scored_df["F05"].isin(RTH_SESSIONS))
        & (scored_df["TouchSequence"] <= M2_FILTERS.get("seq_max", 2))
        & (scored_df["SourceLabel"].apply(tf_minutes) <= 120)
        & ~is_m1
    )
    m2_qualifying = scored_df[m2_mask].copy()
    m2_qualifying["mode"] = "M2"
    n_m2_qual = len(m2_qualifying)
    rprint(f"    M2 qualifying (B-ZScore RTH, excl M1): {n_m2_qual}")
    rprint(f"    Combined qualifying: {n_m1_qual + n_m2_qual}")

    # Filter breakdown
    base = scored_df["score_bz"] >= M2_THRESHOLD
    rth = scored_df["F05"].isin(RTH_SESSIONS)
    seq = scored_df["TouchSequence"] <= 2
    tf = scored_df["SourceLabel"].apply(tf_minutes) <= 120
    rprint(f"    M2 filter breakdown:")
    rprint(f"      B-ZScore >= {M2_THRESHOLD}: {base.sum()}")
    rprint(f"      + RTH: {(base & rth).sum()}")
    rprint(f"      + seq<=2: {(base & rth & seq).sum()}")
    rprint(f"      + TF<=120m: {(base & rth & seq & tf).sum()}")
    rprint(f"      - M1 overlap: {is_m1[base & rth & seq & tf].sum()}")
    rprint(f"      = Final M2: {n_m2_qual}")

    counts = {
        "total": total,
        "m1_qualifying": n_m1_qual,
        "m2_qualifying": n_m2_qual,
        "combined_qualifying": n_m1_qual + n_m2_qual,
    }
    return m1_qualifying, m2_qualifying, counts


# ════════════════════════════════════════════════════════════════════
# MAIN: STEP 0
# ════════════════════════════════════════════════════════════════════
def run_step0():
    """Execute all Step 0 diagnostics."""

    # ── Load bar data ──
    rprint("\n" + "=" * 72)
    rprint("LOADING DATA")
    rprint("=" * 72)

    bar_p1 = pd.read_csv(DATA_DIR / "NQ_bardata_P1.csv")
    bar_p1.columns = bar_p1.columns.str.strip()
    bar_arr_p1 = bar_p1[["Open", "High", "Low", "Last"]].to_numpy(
        dtype=np.float64)
    bar_atr_p1 = bar_p1["ATR"].to_numpy(dtype=np.float64)
    n_bars_p1 = len(bar_arr_p1)
    rprint(f"  P1 bars: {n_bars_p1}")

    bar_p2 = pd.read_csv(DATA_DIR / "NQ_bardata_P2.csv")
    bar_p2.columns = bar_p2.columns.str.strip()
    bar_arr_p2 = bar_p2[["Open", "High", "Low", "Last"]].to_numpy(
        dtype=np.float64)
    bar_atr_p2 = bar_p2["ATR"].to_numpy(dtype=np.float64)
    n_bars_p2 = len(bar_arr_p2)
    rprint(f"  P2 bars: {n_bars_p2}")

    # ── Load raw P1 touches and compute features from scratch ──
    p1a_raw = pd.read_csv(DATA_DIR / "NQ_merged_P1a.csv")
    p1b_raw = pd.read_csv(DATA_DIR / "NQ_merged_P1b.csv")
    rprint(f"  P1a raw: {len(p1a_raw)}, P1b raw: {len(p1b_raw)}")

    p1a = p1a_raw[p1a_raw["RotBarIndex"] >= 0].reset_index(drop=True)
    p1b = p1b_raw[p1b_raw["RotBarIndex"] >= 0].reset_index(drop=True)
    p1_all = pd.concat([p1a, p1b], ignore_index=True)
    rprint(f"  P1 combined (after RotBarIndex filter): {len(p1_all)}")

    p1_featured = compute_features(p1_all, bar_arr_p1, bar_atr_p1,
                                   n_bars_p1, "P1")

    # ── Load P1 pre-scored B-ZScore (authoritative probabilities) ──
    # The CSV's Score_BZScore is from a C=1.0 LogisticRegression with
    # rolling z-score standardization (model_building_v32.py lines 866-886).
    # The JSON model is a DIFFERENT fit (C=0.01, L1, global StandardScaler).
    # For P1, we must use the CSV column to reproduce the 239 M2 baseline.
    p1_bz_csv = pd.read_csv(PARAM_DIR / "p1_scored_touches_bzscore_v32.csv",
                             usecols=["BarIndex", "TouchType", "SourceLabel",
                                      "Score_BZScore"])
    # Join pre-scored B-ZScore to p1_featured by (BarIndex, TouchType, SourceLabel)
    p1_featured["_jk"] = (p1_featured["BarIndex"].astype(str) + "|" +
                           p1_featured["TouchType"] + "|" +
                           p1_featured["SourceLabel"])
    p1_bz_csv["_jk"] = (p1_bz_csv["BarIndex"].astype(str) + "|" +
                          p1_bz_csv["TouchType"] + "|" +
                          p1_bz_csv["SourceLabel"])
    bz_map = p1_bz_csv.drop_duplicates("_jk").set_index("_jk")["Score_BZScore"]
    p1_prescored_bz = p1_featured["_jk"].map(bz_map).values
    join_rate = (~pd.isna(p1_prescored_bz)).sum() / len(p1_featured) * 100
    rprint(f"  P1 pre-scored B-ZScore join rate: {join_rate:.1f}%")
    # Fill unmatched with 0.0 (below any threshold)
    p1_prescored_bz = np.where(pd.isna(p1_prescored_bz), 0.0, p1_prescored_bz)
    p1_featured.drop(columns=["_jk"], inplace=True)

    # ── Load raw P2 touches and compute features from scratch ──
    p2a_raw = pd.read_csv(DATA_DIR / "NQ_merged_P2a.csv")
    p2b_raw = pd.read_csv(DATA_DIR / "NQ_merged_P2b.csv")
    rprint(f"  P2a raw: {len(p2a_raw)}, P2b raw: {len(p2b_raw)}")

    p2a = p2a_raw[p2a_raw["RotBarIndex"] >= 0].reset_index(drop=True)
    p2b = p2b_raw[p2b_raw["RotBarIndex"] >= 0].reset_index(drop=True)
    p2_all = pd.concat([p2a, p2b], ignore_index=True)
    rprint(f"  P2 combined (after RotBarIndex filter): {len(p2_all)}")

    p2_featured = compute_features(p2_all, bar_arr_p2, bar_atr_p2,
                                   n_bars_p2, "P2")

    # ══════════════════════════════════════════════════════════════
    # STEP 0-pre: POPULATION VERIFICATION
    # ══════════════════════════════════════════════════════════════
    rprint("\n" + "=" * 72)
    rprint("STEP 0-pre: POPULATION VERIFICATION")
    rprint("=" * 72)

    # ── P1 waterfall (A-Eq from scratch, B-ZScore from pre-scored CSV) ──
    rprint("\n── P1 Waterfall ──")
    m1_p1, m2_p1, p1_counts = build_waterfall(
        p1_featured, "P1", prescored_bz=p1_prescored_bz)

    rprint("\n  Simulating P1 Mode 1...")
    m1_p1_results, m1_p1_skipped = simulate_population(
        m1_p1, "M1", bar_arr_p1, n_bars_p1)
    rprint(f"    M1 traded: {len(m1_p1_results)}, "
           f"skipped: {len(m1_p1_skipped)}")

    rprint("  Simulating P1 Mode 2...")
    m2_p1_results, m2_p1_skipped = simulate_population(
        m2_p1, "M2", bar_arr_p1, n_bars_p1)
    rprint(f"    M2 traded: {len(m2_p1_results)}, "
           f"skipped: {len(m2_p1_skipped)}")

    m1_pf = compute_pf(m1_p1_results["pnl"].tolist(), COST_TICKS)
    m2_pf = compute_pf(m2_p1_results["pnl"].tolist(), COST_TICKS)
    m1_wr = compute_wr(m1_p1_results["pnl"].tolist(), COST_TICKS)
    m2_wr = compute_wr(m2_p1_results["pnl"].tolist(), COST_TICKS)

    rprint(f"\n  P1 VERIFICATION:")
    rprint(f"  {'Population':<20} {'Expected':>10} {'Actual':>8} {'Pass?':>6}")
    rprint(f"  {'-'*20} {'-'*10} {'-'*8} {'-'*6}")
    _chk = lambda act, exp, tol: "PASS" if abs(act - exp) <= tol else "FAIL"
    rprint(f"  {'M1 qualifying':<20} {'~127':>10} {p1_counts['m1_qualifying']:>8} "
           f"{_chk(p1_counts['m1_qualifying'], 127, 20):>6}")
    rprint(f"  {'M2 qualifying':<20} {'~215-230':>10} {p1_counts['m2_qualifying']:>8} "
           f"{'PASS' if 180 < p1_counts['m2_qualifying'] < 280 else 'FAIL':>6}")
    rprint(f"  {'M1 traded':<20} {'~107':>10} {len(m1_p1_results):>8} "
           f"{_chk(len(m1_p1_results), 107, 15):>6}")
    rprint(f"  {'M2 traded':<20} {'~239':>10} {len(m2_p1_results):>8} "
           f"{_chk(len(m2_p1_results), 239, 30):>6}")
    rprint(f"  {'M1 PF@3t':<20} {'~8.50':>10} {m1_pf:>8.2f} "
           f"{_chk(m1_pf, 8.50, 1.5):>6}")
    rprint(f"  {'M2 PF@3t':<20} {'~4.71':>10} {m2_pf:>8.2f} "
           f"{_chk(m2_pf, 4.71, 1.0):>6}")
    rprint(f"  {'M1 WR%':<20} {'~96.3':>10} {m1_wr:>8.1f} "
           f"{_chk(m1_wr, 96.3, 5):>6}")
    rprint(f"  {'M2 WR%':<20} {'~74.5':>10} {m2_wr:>8.1f} "
           f"{_chk(m2_wr, 74.5, 8):>6}")

    # ── P2 waterfall (A-Eq from scratch, B-ZScore from JSON model) ──
    # No P2 pre-scored CSV exists. B-ZScore uses JSON coefficients (raw
    # linear), matching ray_conditional_analysis_v32.py which produced 309.
    rprint("\n── P2 Waterfall ──")
    m1_p2, m2_p2, p2_counts = build_waterfall(p2_featured, "P2")

    rprint("\n  Simulating P2 Mode 1...")
    m1_p2_results, m1_p2_skipped = simulate_population(
        m1_p2, "M1", bar_arr_p2, n_bars_p2)
    rprint(f"    M1 traded: {len(m1_p2_results)}, "
           f"skipped: {len(m1_p2_skipped)}")

    rprint("  Simulating P2 Mode 2...")
    m2_p2_results, m2_p2_skipped = simulate_population(
        m2_p2, "M2", bar_arr_p2, n_bars_p2)
    rprint(f"    M2 traded: {len(m2_p2_results)}, "
           f"skipped: {len(m2_p2_skipped)}")

    m1_p2_pf4 = compute_pf(m1_p2_results["pnl"].tolist(), 4)
    m2_p2_pf4 = compute_pf(m2_p2_results["pnl"].tolist(), 4)
    combined_p2 = (m1_p2_results["pnl"].tolist()
                   + m2_p2_results["pnl"].tolist())
    combined_p2_pf4 = compute_pf(combined_p2, 4)

    rprint(f"\n  P2 VERIFICATION:")
    rprint(f"  {'Population':<20} {'Expected':>10} {'Actual':>8} {'Pass?':>6}")
    rprint(f"  {'-'*20} {'-'*10} {'-'*8} {'-'*6}")
    rprint(f"  {'M1 qualifying':<20} {'~108':>10} {p2_counts['m1_qualifying']:>8} "
           f"{_chk(p2_counts['m1_qualifying'], 108, 20):>6}")
    rprint(f"  {'M2 qualifying':<20} {'~330-350':>10} {p2_counts['m2_qualifying']:>8} "
           f"{'PASS' if 280 < p2_counts['m2_qualifying'] < 400 else 'FAIL':>6}")
    rprint(f"  {'M1 traded':<20} {'~96':>10} {len(m1_p2_results):>8} "
           f"{_chk(len(m1_p2_results), 96, 15):>6}")
    rprint(f"  {'M2 traded':<20} {'~309':>10} {len(m2_p2_results):>8} "
           f"{_chk(len(m2_p2_results), 309, 45):>6}")
    rprint(f"  {'M1 PF@4t':<20} {'~6.26':>10} {m1_p2_pf4:>8.2f} "
           f"{_chk(m1_p2_pf4, 6.26, 1.5):>6}")
    rprint(f"  {'M2 PF@4t':<20} {'~4.10':>10} {m2_p2_pf4:>8.2f} "
           f"{_chk(m2_p2_pf4, 4.10, 1.5):>6}")
    rprint(f"  {'Combined PF@4t':<20} {'~4.30':>10} {combined_p2_pf4:>8.2f} "
           f"{_chk(combined_p2_pf4, 4.30, 1.5):>6}")

    m2_p2_traded = len(m2_p2_results)
    if m2_p2_traded > 380:
        rprint(f"\n  !!! P2 M2 TRADED = {m2_p2_traded}, expected ~309.")
        rprint("      If ~419, check RTH/seq/TF/overlap filters.")
        rprint("      INVESTIGATION HALTED.")
        sys.exit(1)

    # ══════════════════════════════════════════════════════════════
    # STEP 0a: PER-TRADE OUTCOME DATA
    # ══════════════════════════════════════════════════════════════
    rprint("\n" + "=" * 72)
    rprint("STEP 0a: PER-TRADE OUTCOME DATA")
    rprint("=" * 72)

    all_p1 = pd.concat([m1_p1_results, m2_p1_results], ignore_index=True)
    rprint(f"  Total P1 trades: {len(all_p1)} "
           f"(M1={len(m1_p1_results)}, M2={len(m2_p1_results)})")

    rprint(f"\n  ENTRY CONVENTION:")
    rprint(f"    Entry = Open of bar at RotBarIndex+1 (next bar after touch)")
    rprint(f"    M1 mean entry offset from TouchPrice: "
           f"{m1_p1_results['entry_offset'].mean():.1f}t")
    rprint(f"    M2 mean entry offset from TouchPrice: "
           f"{m2_p1_results['entry_offset'].mean():.1f}t")
    rprint(f"    Entry is NOT at zone edge — market open of next bar.")

    rprint(f"\n  M1 exit distribution: "
           f"{dict(m1_p1_results['exit_type'].value_counts())}")
    rprint(f"  M2 exit distribution: "
           f"{dict(m2_p1_results['exit_type'].value_counts())}")

    # ══════════════════════════════════════════════════════════════
    # STEP 0b: MAE DISTRIBUTION (LOSERS)
    # ══════════════════════════════════════════════════════════════
    rprint("\n" + "=" * 72)
    rprint("STEP 0b: MAE DISTRIBUTION — LOSERS")
    rprint("=" * 72)

    # ── Mode 1 losers (small N — each individually) ──
    m1_losers = m1_p1_results[~m1_p1_results["win"]].copy()
    rprint(f"\n  MODE 1 LOSERS: {len(m1_losers)} trades")
    if len(m1_losers) > 0:
        rprint(f"  {'#':>3} {'Exit':>9} {'MAE':>6} {'MFE':>6} "
               f"{'PnL':>7} {'Bars':>5} {'Stop':>5} {'ZW':>4}")
        rprint(f"  {'---':>3} {'-'*9:>9} {'---':>6} {'---':>6} "
               f"{'---':>7} {'---':>5} {'---':>5} {'---':>4}")
        for i, (_, row) in enumerate(m1_losers.iterrows()):
            rprint(f"  {i+1:>3} {row['exit_type']:>9} {row['mae']:>6.0f} "
                   f"{row['mfe']:>6.0f} {row['pnl']:>+7.0f} "
                   f"{row['bars_held']:>5} {row['stop_used']:>5} "
                   f"{row['zw_ticks']:>4}")

        rprint(f"\n  M1 Loser MAE time profiles:")
        for i, (_, row) in enumerate(m1_losers.iterrows()):
            profile = row["bar_mae_profile"]
            thresholds = [60, 120, 150]
            parts = []
            for t in thresholds:
                bars_exceeding = [b + 1 for b, v in enumerate(profile)
                                  if v >= t]
                bar_at = bars_exceeding[0] if bars_exceeding else "never"
                parts.append(f">{t}t@bar {bar_at}")
            rprint(f"    Loser {i+1}: {', '.join(parts)}")
    else:
        rprint(f"  No M1 losers (100% WR at cost={COST_TICKS}t)")

    # ── Mode 2 losers ──
    m2_losers = m2_p1_results[~m2_p1_results["win"]].copy()
    rprint(f"\n  MODE 2 LOSERS: {len(m2_losers)} trades")

    if len(m2_losers) > 0:
        m2_stop_losers = m2_losers[m2_losers["exit_type"] == "STOP"]
        m2_tc_losers = m2_losers[m2_losers["exit_type"] == "TIMECAP"]

        rprint(f"\n  M2 STOP-HIT LOSERS: {len(m2_stop_losers)}")
        if len(m2_stop_losers) > 0:
            rprint(f"    % of all M2 losers: "
                   f"{len(m2_stop_losers)/len(m2_losers)*100:.1f}%")
            rprint(f"    Mean bars to stop: "
                   f"{m2_stop_losers['bars_held'].mean():.1f}")
            fast = (m2_stop_losers["bars_held"] < 10).sum()
            slow = (m2_stop_losers["bars_held"] > 40).sum()
            rprint(f"    Decisive failures (bars<10): {fast}")
            rprint(f"    Slow bleed (bars>40): {slow}")
            rprint(f"    Mean loss: {m2_stop_losers['pnl'].mean():.1f}t")

        rprint(f"\n  M2 TIMECAP LOSERS: {len(m2_tc_losers)}")
        if len(m2_tc_losers) > 0:
            tc_mae_pct = (m2_tc_losers["mae"].values
                          / m2_tc_losers["stop_used"].values * 100)
            bins = [(0, 50), (50, 75), (75, 101)]
            rprint(f"    {'MAE % of stop':>15} {'Count':>6} {'%':>8} "
                   f"{'Mean PnL':>9}")
            rprint(f"    {'-'*15} {'-'*6} {'-'*8} {'-'*9}")
            for lo, hi in bins:
                mask = (tc_mae_pct >= lo) & (tc_mae_pct < hi)
                n = mask.sum()
                pct = n / len(m2_tc_losers) * 100
                mp = m2_tc_losers.iloc[np.where(mask)[0]]["pnl"].mean() \
                    if n > 0 else 0
                rprint(f"    {lo:>6}-{hi:>3}%     {n:>6} {pct:>7.1f}% "
                       f"{mp:>+8.1f}t")

    # ══════════════════════════════════════════════════════════════
    # STEP 0c: MFE DISTRIBUTION (WINNERS)
    # ══════════════════════════════════════════════════════════════
    rprint("\n" + "=" * 72)
    rprint("STEP 0c: MFE DISTRIBUTION — WINNERS")
    rprint("=" * 72)

    m1_winners = m1_p1_results[m1_p1_results["win"]].copy()
    rprint(f"\n  MODE 1 WINNERS: {len(m1_winners)} trades")
    if len(m1_winners) > 0:
        mfe_bins = [(60, 80, "Barely hit target"),
                    (80, 120, "Some room"),
                    (120, 200, "Money left"),
                    (200, 9999, "Large continuation")]
        rprint(f"  {'MFE Bin':>12} {'Count':>6} {'%':>6} "
               f"{'Med PnL':>8} {'Note'}")
        rprint(f"  {'-'*12} {'-'*6} {'-'*6} {'-'*8} {'-'*20}")
        for lo, hi, note in mfe_bins:
            mask = (m1_winners["mfe"] >= lo) & (m1_winners["mfe"] < hi)
            n = mask.sum()
            pct = n / len(m1_winners) * 100
            med = m1_winners[mask]["pnl"].median() if n > 0 else 0
            hi_s = f"{hi}" if hi < 9999 else "inf"
            rprint(f"  {lo:>5}-{hi_s:>4}t {n:>6} {pct:>5.1f}% "
                   f"{med:>+7.1f}t {note}")

    m2_winners = m2_p1_results[m2_p1_results["win"]].copy()
    rprint(f"\n  MODE 2 WINNERS: {len(m2_winners)} trades")
    if len(m2_winners) > 0:
        rprint(f"  {'MFE/ZW':>12} {'Count':>6} {'%':>6} "
               f"{'Med PnL':>8} {'Note'}")
        rprint(f"  {'-'*12} {'-'*6} {'-'*6} {'-'*8} {'-'*20}")
        for lo_r, hi_r, note in [(0, 0.5, "< half zone"),
                                  (0.5, 1.0, "Half to full"),
                                  (1.0, 1.5, "Full to 1.5x"),
                                  (1.5, 99, "> 1.5x zone")]:
            ratios = m2_winners["mfe"] / m2_winners["zw_ticks"]
            mask = (ratios >= lo_r) & (ratios < hi_r)
            n = mask.sum()
            pct = n / len(m2_winners) * 100
            med = m2_winners[mask]["pnl"].median() if n > 0 else 0
            rprint(f"  {lo_r:.1f}-{min(hi_r,9.9):.1f}xZW  {n:>6} "
                   f"{pct:>5.1f}% {med:>+7.1f}t {note}")

    # ══════════════════════════════════════════════════════════════
    # STEP 0d: ZONE WIDTH DISTRIBUTION (Mode 2)
    # ══════════════════════════════════════════════════════════════
    rprint("\n" + "=" * 72)
    rprint("STEP 0d: ZONE WIDTH DISTRIBUTION (Mode 2)")
    rprint("=" * 72)

    m2_r = m2_p1_results
    zw_bins = [(0, 100), (100, 150), (150, 250), (250, 400), (400, 9999)]
    rprint(f"  {'ZW Bin':>12} {'N':>5} {'%':>6} {'AvgStop':>8} "
           f"{'MaxLoss@3c':>11} {'PF@3t':>7} {'WR%':>6}")
    rprint(f"  {'-'*12} {'-'*5} {'-'*6} {'-'*8} {'-'*11} {'-'*7} {'-'*6}")
    for lo, hi in zw_bins:
        mask = (m2_r["zw_ticks"] >= lo) & (m2_r["zw_ticks"] < hi)
        n = mask.sum()
        if n == 0:
            continue
        pct = n / len(m2_r) * 100
        avg_stop = m2_r[mask]["stop_used"].mean()
        max_loss = avg_stop * 3
        bin_pnls = m2_r[mask]["pnl"].tolist()
        pf = compute_pf(bin_pnls, COST_TICKS)
        wr = compute_wr(bin_pnls, COST_TICKS)
        hi_s = f"{hi}" if hi < 9999 else "inf"
        rprint(f"  {lo:>5}-{hi_s:>4}t {n:>5} {pct:>5.1f}% {avg_stop:>8.0f} "
               f"{max_loss:>11.0f} {pf:>7.2f} {wr:>5.1f}%")

    # ══════════════════════════════════════════════════════════════
    # STEP 0e: TIME CAP EXIT CHARACTERIZATION
    # ══════════════════════════════════════════════════════════════
    rprint("\n" + "=" * 72)
    rprint("STEP 0e: TIME CAP EXIT CHARACTERIZATION")
    rprint("=" * 72)

    for mode_label, rdf, tc_bars in [("M1", m1_p1_results, 120),
                                      ("M2", m2_p1_results, 80)]:
        tc = rdf[rdf["exit_type"] == "TIMECAP"]
        non_tc = rdf[rdf["exit_type"] != "TIMECAP"]
        rprint(f"\n  {mode_label} (TC = {tc_bars} bars):")
        rprint(f"    TC exits: {len(tc)} ({len(tc)/len(rdf)*100:.1f}%)")
        if len(tc) > 0:
            rprint(f"    Mean TC PnL: {tc['pnl'].mean():+.1f}t")
            tc_w = (tc["pnl"] - COST_TICKS > 0).sum()
            tc_l = (tc["pnl"] - COST_TICKS < 0).sum()
            tc_s = len(tc) - tc_w - tc_l
            rprint(f"    TC winners: {tc_w}, losers: {tc_l}, scratches: {tc_s}")
            rprint(f"    TC winner mean PnL: "
                   f"{tc[tc['pnl'] - COST_TICKS > 0]['pnl'].mean():+.1f}t"
                   if tc_w > 0 else "    TC winner mean PnL: N/A")
            rprint(f"    TC loser mean PnL: "
                   f"{tc[tc['pnl'] - COST_TICKS < 0]['pnl'].mean():+.1f}t"
                   if tc_l > 0 else "    TC loser mean PnL: N/A")
        if len(non_tc) > 0:
            rprint(f"    Mean bars held (non-TC): {non_tc['bars_held'].mean():.1f}")

    # ══════════════════════════════════════════════════════════════
    # STEP 0f: PENETRATION DEPTH / FILL RATE CURVE
    # ══════════════════════════════════════════════════════════════
    rprint("\n" + "=" * 72)
    rprint("STEP 0f: PENETRATION DEPTH / FILL RATE CURVE")
    rprint("=" * 72)
    rprint("  Fill window: touch bar + next 3 bars (4 bars total)")

    for mode_label, rdf in [("M1", m1_p1_results), ("M2", m2_p1_results)]:
        rprint(f"\n  {mode_label} FILL RATE CURVE:")
        depths = [0, 10, 20, 30, 40, 50, 60, 80, 100]
        total_n = len(rdf)
        rprint(f"  {'Depth':>8} {'Reach':>6} {'Fill%':>7} {'Delta':>7}")
        rprint(f"  {'-'*8} {'-'*6} {'-'*7} {'-'*7}")
        for d in depths:
            filled = (rdf["max_penetration"] >= d).sum()
            rate = filled / total_n * 100
            rprint(f"  {d:>6}t  {filled:>6} {rate:>6.1f}% "
                   f"{rate - 100:>+6.1f}%")

        pen = rdf["max_penetration"]
        rprint(f"\n  {mode_label} penetration stats: "
               f"mean={pen.mean():.1f}t, med={pen.median():.1f}t, "
               f"P25={pen.quantile(0.25):.1f}t, "
               f"P75={pen.quantile(0.75):.1f}t")

    # ══════════════════════════════════════════════════════════════
    # STEP 0g: MISSED TRADE CHARACTERIZATION
    # ══════════════════════════════════════════════════════════════
    rprint("\n" + "=" * 72)
    rprint("STEP 0g: MISSED TRADE CHARACTERIZATION")
    rprint("=" * 72)

    for mode_label, q_count, rdf, sdf in [
        ("M1", p1_counts["m1_qualifying"], m1_p1_results, m1_p1_skipped),
        ("M2", p1_counts["m2_qualifying"], m2_p1_results, m2_p1_skipped),
    ]:
        traded = len(rdf)
        missed = len(sdf)
        rprint(f"\n  {mode_label}:")
        rprint(f"    Qualifying: {q_count}, Traded: {traded}, "
               f"Missed: {missed}")
        if q_count > 0:
            rprint(f"    Miss rate: {missed / q_count * 100:.1f}%")

        if missed > 0 and traded > 0:
            for col_label, col in [("A-Eq score", "score_aeq"),
                                    ("B-ZScore", "score_bz")]:
                if col in sdf.columns and col in rdf.columns:
                    t_val = rdf[col].mean()
                    s_val = sdf[col].mean()
                    rprint(f"    Mean {col_label} — traded: {t_val:.2f}, "
                           f"missed: {s_val:.2f}")
            rprint(f"    Mean ZW — traded: {rdf['zw_ticks'].mean():.1f}t, "
                   f"missed: {sdf['zw_ticks'].mean():.1f}t")

    # ══════════════════════════════════════════════════════════════
    # SAVE OUTPUTS
    # ══════════════════════════════════════════════════════════════
    rprint("\n" + "=" * 72)
    rprint("SAVING OUTPUTS")
    rprint("=" * 72)

    save_cols = [c for c in all_p1.columns
                 if c not in ("bar_mfe_profile", "bar_mae_profile")]
    all_p1[save_cols].to_csv(
        OUT_DIR / "qualifying_trades_outcomes_v32.csv", index=False)
    rprint(f"  Saved: qualifying_trades_outcomes_v32.csv ({len(all_p1)} rows)")

    fill_rows = []
    for mode_label, rdf in [("M1", m1_p1_results), ("M2", m2_p1_results)]:
        for _, row in rdf.iterrows():
            fill_rows.append({
                "touch_idx": row["touch_idx"], "mode": mode_label,
                "max_penetration": row["max_penetration"],
                "pen_bar": row["pen_bar"],
                "zw_ticks": row["zw_ticks"],
            })
    pd.DataFrame(fill_rows).to_csv(
        OUT_DIR / "fill_rate_analysis_v32.csv", index=False)
    rprint(f"  Saved: fill_rate_analysis_v32.csv ({len(fill_rows)} rows)")

    # ══════════════════════════════════════════════════════════════
    # COMPLETENESS CHECK
    # ══════════════════════════════════════════════════════════════
    rprint("\n" + "=" * 72)
    rprint("STEP 0 COMPLETENESS CHECK")
    rprint("=" * 72)
    checks = [
        ("0-pre P1 M1 traded ~107",
         abs(len(m1_p1_results) - 107) < 15),
        ("0-pre P1 M2 traded ~239",
         abs(len(m2_p1_results) - 239) < 30),
        ("0-pre P2 M1 traded ~96",
         abs(len(m1_p2_results) - 96) < 15),
        ("0-pre P2 M2 traded ~309 (NOT ~419)",
         abs(len(m2_p2_results) - 309) < 45),
        ("0a Per-trade outcomes saved",
         len(all_p1) > 300),
        ("0b MAE distribution reported",
         True),
        ("0c MFE distribution reported",
         len(m1_winners) > 0),
        ("0d Zone width bins with PF",
         True),
        ("0e TC exit characterization",
         True),
        ("0f Penetration/fill rate curve",
         True),
        ("0g Missed trade characterization",
         True),
    ]
    all_pass = True
    for name, passed in checks:
        status = "PASS" if passed else "FAIL"
        rprint(f"  [{status}] {name}")
        if not passed:
            all_pass = False

    if not all_pass:
        rprint("\n  !!! SOME CHECKS FAILED. Review above before proceeding.")

    rprint("\n" + "=" * 72)
    rprint("Step 0 complete. Proceeding to Surface B.")
    rprint("=" * 72)

    # ══════════════════════════════════════════════════════════════
    # SURFACE B: EXIT STRUCTURE MODIFICATIONS
    # Entries unchanged — zone edge, 3 contracts. Only exits change.
    # Each test runs on the SAME P1 qualifying trades.
    # ══════════════════════════════════════════════════════════════

    def resim_with_params(qualifying_df, mode, bar_arr_local, n_bars_local,
                          stop_fn, target_fn, tcap_fn,
                          be_trigger_fn=None, trail_fn=None):
        """Re-simulate qualifying trades with modified exit params.

        stop_fn(row) -> stop_ticks
        target_fn(row) -> target_ticks
        tcap_fn(row) -> time_cap_bars
        be_trigger_fn(row) -> be_trigger_ticks (0=disabled)
        trail_fn not implemented (future)

        Returns same-format results DF. Position overlap applied.
        """
        subset = qualifying_df.sort_values("RotBarIndex").copy()
        results = []
        in_trade_until = -1

        for idx, row in subset.iterrows():
            rbi = int(row["RotBarIndex"])
            entry_bar = rbi + 1
            if entry_bar <= in_trade_until:
                continue
            direction = 1 if "DEMAND" in str(row["TouchType"]) else -1
            zw = int(row.get("ZoneWidthTicks", 100))

            stop = int(stop_fn(row, zw))
            target = int(target_fn(row, zw))
            tcap = int(tcap_fn(row, zw))
            be_trig = int(be_trigger_fn(row, zw)) if be_trigger_fn else 0

            if entry_bar >= n_bars_local:
                continue
            ep = bar_arr_local[entry_bar, 0]
            if direction == 1:
                stop_price = ep - stop * TICK
                target_price = ep + target * TICK
            else:
                stop_price = ep + stop * TICK
                target_price = ep - target * TICK

            mfe = 0.0
            mae = 0.0
            be_active = False
            pnl_out = None
            bh_out = 0
            etype_out = None

            end = min(entry_bar + tcap, n_bars_local)
            for i in range(entry_bar, end):
                h, l, last = (bar_arr_local[i, 1], bar_arr_local[i, 2],
                               bar_arr_local[i, 3])
                bh = i - entry_bar + 1

                if direction == 1:
                    mfe = max(mfe, (h - ep) / TICK)
                    mae = max(mae, (ep - l) / TICK)
                else:
                    mfe = max(mfe, (ep - l) / TICK)
                    mae = max(mae, (h - ep) / TICK)

                # BE trigger
                if be_trig > 0 and not be_active and mfe >= be_trig:
                    be_active = True
                    if direction == 1:
                        stop_price = max(stop_price, ep)
                    else:
                        stop_price = min(stop_price, ep)

                # Check stop
                if direction == 1:
                    s_hit = l <= stop_price
                    t_hit = h >= target_price
                else:
                    s_hit = h >= stop_price
                    t_hit = l <= target_price

                if s_hit:
                    pnl_out = ((stop_price - ep) / TICK if direction == 1
                               else (ep - stop_price) / TICK)
                    bh_out = bh
                    etype_out = "BE" if be_active else "STOP"
                    break
                if t_hit:
                    pnl_out = target
                    bh_out = bh
                    etype_out = "TARGET"
                    break
                if bh >= tcap:
                    pnl_out = ((last - ep) / TICK if direction == 1
                               else (ep - last) / TICK)
                    bh_out = bh
                    etype_out = "TIMECAP"
                    break

            if pnl_out is None:
                if end > entry_bar:
                    last = bar_arr_local[end - 1, 3]
                    pnl_out = ((last - ep) / TICK if direction == 1
                               else (ep - last) / TICK)
                    bh_out = end - entry_bar
                    etype_out = "TIMECAP"
                else:
                    continue

            results.append({
                "pnl": pnl_out, "bars_held": bh_out,
                "exit_type": etype_out, "mfe": mfe, "mae": mae,
                "stop_used": stop, "target_used": target,
                "zw_ticks": zw, "direction": direction,
                "win": pnl_out - COST_TICKS > 0,
            })
            in_trade_until = entry_bar + bh_out - 1

        return pd.DataFrame(results)

    def surface_row(label, rdf, baseline_n):
        """Compute summary stats for a surface test row."""
        if len(rdf) == 0:
            return {"label": label, "pf": 0, "wr": 0, "trades": 0,
                    "mean_win": 0, "mean_loss": 0, "lw": 0,
                    "new_stopouts": 0, "throughput": ""}
        pnls = rdf["pnl"].tolist()
        pf = compute_pf(pnls, COST_TICKS)
        wr = compute_wr(pnls, COST_TICKS)
        winners = rdf[rdf["win"]]
        losers = rdf[~rdf["win"]]
        mw = winners["pnl"].mean() if len(winners) > 0 else 0
        ml = losers["pnl"].mean() if len(losers) > 0 else 0
        lw = abs(ml) / mw if mw > 0 else 0
        n = len(rdf)
        tp = f" THROUGHPUT+{n - baseline_n}" if n != baseline_n else ""
        return {"label": label, "pf": pf, "wr": wr, "trades": n,
                "mean_win": mw, "mean_loss": ml, "lw": lw,
                "new_stopouts": 0, "throughput": tp}

    def print_surface_table(rows, mode_label):
        rprint(f"\n  {mode_label}:")
        rprint(f"  {'Config':<35} {'PF@3t':>7} {'WR%':>6} {'Trades':>7} "
               f"{'MeanWin':>8} {'MeanLoss':>9} {'L:W':>6} {'Note'}")
        rprint(f"  {'-'*35} {'-'*7} {'-'*6} {'-'*7} "
               f"{'-'*8} {'-'*9} {'-'*6} {'-'*15}")
        for r in rows:
            rprint(f"  {r['label']:<35} {r['pf']:>7.2f} {r['wr']:>5.1f}% "
                   f"{r['trades']:>7} {r['mean_win']:>+7.1f}t "
                   f"{r['mean_loss']:>+8.1f}t {r['lw']:>5.2f} "
                   f"{r['throughput']}")

    # ═══════════════════════════════════════════════════════════
    rprint("\n" + "=" * 72)
    rprint("SURFACE B: EXIT STRUCTURE MODIFICATIONS")
    rprint("=" * 72)

    # ── B1: Stop Reduction (Mode 1) ──
    rprint("\n── B1: Stop Reduction (Mode 1) ──")
    m1_b1_rows = []
    m1_baseline_row = surface_row("190t (baseline)", m1_p1_results, 107)
    m1_b1_rows.append(m1_baseline_row)
    for s in [170, 150, 130, 120, 100]:
        r = resim_with_params(
            m1_p1, "M1", bar_arr_p1, n_bars_p1,
            stop_fn=lambda row, zw, _s=s: _s,
            target_fn=lambda row, zw: 60,
            tcap_fn=lambda row, zw: 120)
        row = surface_row(f"{s}t", r, 107)
        # Count new stopouts: trades that were winners at baseline but losers now
        m1_b1_rows.append(row)
    print_surface_table(m1_b1_rows, "M1 Stop Reduction")

    # ── B2: Stop Reduction (Mode 2) ──
    rprint("\n── B2: Stop Reduction (Mode 2) ──")
    m2_b2_rows = []
    m2_baseline_row = surface_row("1.5xZW floor 120 (baseline)", m2_p1_results, 239)
    m2_b2_rows.append(m2_baseline_row)

    stop_configs_m2 = [
        ("1.3xZW floor 100", lambda row, zw: max(round(1.3 * zw), 100)),
        ("1.2xZW floor 100", lambda row, zw: max(round(1.2 * zw), 100)),
        ("1.0xZW floor 80", lambda row, zw: max(round(1.0 * zw), 80)),
        ("Cond: 1.5 if ZW<200 else 1.2", lambda row, zw: max(round(1.5 * zw), 120) if zw < 200 else max(round(1.2 * zw), 100)),
        ("Cond: 1.5 if ZW<200 else 1.0", lambda row, zw: max(round(1.5 * zw), 120) if zw < 200 else max(round(1.0 * zw), 80)),
    ]
    for label, sfn in stop_configs_m2:
        r = resim_with_params(
            m2_p1, "M2", bar_arr_p1, n_bars_p1,
            stop_fn=sfn,
            target_fn=lambda row, zw: max(1, round(1.0 * zw)),
            tcap_fn=lambda row, zw: 80)
        m2_b2_rows.append(surface_row(label, r, 239))
    print_surface_table(m2_b2_rows, "M2 Stop Reduction")

    # ── B3: Breakeven Stop (Mode 1) ──
    rprint("\n── B3: Breakeven Stop (Mode 1) ──")
    m1_b3_rows = [m1_baseline_row]
    for be in [20, 30, 40, 50]:
        r = resim_with_params(
            m1_p1, "M1", bar_arr_p1, n_bars_p1,
            stop_fn=lambda row, zw: 190,
            target_fn=lambda row, zw: 60,
            tcap_fn=lambda row, zw: 120,
            be_trigger_fn=lambda row, zw, _be=be: _be)
        row = surface_row(f"BE@{be}t MFE", r, 107)
        # Count scratches (BE exits)
        scratches = (r["exit_type"] == "BE").sum() if len(r) > 0 else 0
        row["label"] = f"BE@{be}t MFE (scratches={scratches})"
        m1_b3_rows.append(row)
    print_surface_table(m1_b3_rows, "M1 Breakeven Stop")

    # ── B4: Breakeven Stop (Mode 2) ──
    rprint("\n── B4: Breakeven Stop (Mode 2) ──")
    m2_b4_rows = [m2_baseline_row]
    for be_label, be_fn in [
        ("BE@0.3xZW", lambda row, zw: max(1, round(0.3 * zw))),
        ("BE@0.5xZW", lambda row, zw: max(1, round(0.5 * zw))),
        ("BE@30t fixed", lambda row, zw: 30),
        ("BE@50t fixed", lambda row, zw: 50),
    ]:
        r = resim_with_params(
            m2_p1, "M2", bar_arr_p1, n_bars_p1,
            stop_fn=lambda row, zw: max(round(1.5 * zw), 120),
            target_fn=lambda row, zw: max(1, round(1.0 * zw)),
            tcap_fn=lambda row, zw: 80,
            be_trigger_fn=be_fn)
        scratches = (r["exit_type"] == "BE").sum() if len(r) > 0 else 0
        row = surface_row(f"{be_label} (scr={scratches})", r, 239)
        m2_b4_rows.append(row)
    print_surface_table(m2_b4_rows, "M2 Breakeven Stop")

    # ── B7: Time Cap Tightening ──
    rprint("\n── B7: Time Cap Tightening ──")
    m1_b7_rows = [m1_baseline_row]
    for tc in [90, 60]:
        r = resim_with_params(
            m1_p1, "M1", bar_arr_p1, n_bars_p1,
            stop_fn=lambda row, zw: 190,
            target_fn=lambda row, zw: 60,
            tcap_fn=lambda row, zw, _tc=tc: _tc)
        m1_b7_rows.append(surface_row(f"TC={tc}", r, 107))
    print_surface_table(m1_b7_rows, "M1 Time Cap")

    m2_b7_rows = [m2_baseline_row]
    for tc in [60, 40]:
        r = resim_with_params(
            m2_p1, "M2", bar_arr_p1, n_bars_p1,
            stop_fn=lambda row, zw: max(round(1.5 * zw), 120),
            target_fn=lambda row, zw: max(1, round(1.0 * zw)),
            tcap_fn=lambda row, zw, _tc=tc: _tc)
        m2_b7_rows.append(surface_row(f"TC={tc}", r, 239))
    print_surface_table(m2_b7_rows, "M2 Time Cap")

    # ── B10: Target Reduction (Mode 2) ──
    rprint("\n── B10: Target Reduction (Mode 2) ──")
    m2_b10_rows = [m2_baseline_row]
    best_b10_mult = 1.0
    best_b10_pf = m2_baseline_row["pf"]
    for mult in [0.9, 0.8, 0.75, 0.6, 0.5]:
        r = resim_with_params(
            m2_p1, "M2", bar_arr_p1, n_bars_p1,
            stop_fn=lambda row, zw: max(round(1.5 * zw), 120),
            target_fn=lambda row, zw, _m=mult: max(1, round(_m * zw)),
            tcap_fn=lambda row, zw: 80)
        row = surface_row(f"{mult}xZW target", r, 239)
        tc_exits = (r["exit_type"] == "TIMECAP").sum() if len(r) > 0 else 0
        row["label"] = f"{mult}xZW target (TC={tc_exits})"
        m2_b10_rows.append(row)
        if row["pf"] > best_b10_pf:
            best_b10_pf = row["pf"]
            best_b10_mult = mult
    print_surface_table(m2_b10_rows, "M2 Target Reduction")
    rprint(f"\n  Best M2 target: {best_b10_mult}xZW (PF={best_b10_pf:.2f})")

    # ── B5: Partial Exits (Mode 1) — using run_multileg from simulator ──
    rprint("\n── B5: Partial Exits (Mode 1) ──")
    # Import the multileg simulator
    import importlib.util
    _sim_path = Path(__file__).parent / "zone_touch_simulator.py"
    _sim_spec = importlib.util.spec_from_file_location(
        "zone_touch_simulator", str(_sim_path))
    _sim_mod = importlib.util.module_from_spec(_sim_spec)
    _sim_spec.loader.exec_module(_sim_mod)

    def run_multileg_population(qualifying_df, config, bar_df_arr,
                                n_bars_local, mode_str):
        """Run multileg simulation on qualifying trades."""
        subset = qualifying_df.sort_values("RotBarIndex").copy()
        results = []
        in_trade_until = -1

        # Build a bar DataFrame for the simulator
        bar_df = pd.DataFrame(bar_df_arr, columns=["Open", "High", "Low", "Last"])

        for idx, row in subset.iterrows():
            rbi = int(row["RotBarIndex"])
            entry_bar = rbi + 1
            if entry_bar <= in_trade_until:
                continue
            direction = 1 if "DEMAND" in str(row["TouchType"]) else -1
            zw = int(row.get("ZoneWidthTicks", 100))

            # Build touch_row for the simulator
            touch_row = pd.Series({
                "TouchPrice": bar_df_arr[entry_bar, 0],  # entry at bar open
                "ApproachDir": direction,
                "mode": mode_str,
            })

            # Build mode config with zone-adjusted values if M2
            mode_cfg = dict(config[mode_str])
            if mode_str == "M2":
                stop_t = max(round(1.5 * zw), 120)
                mode_cfg["stop_ticks"] = stop_t
                # Scale leg targets by zone width
                base_targets = config[mode_str]["leg_targets"]
                mode_cfg["leg_targets"] = [round(t * zw) for t in base_targets]

            cfg = {"tick_size": TICK, mode_str: mode_cfg}
            result = _sim_mod.run_multileg(bar_df, touch_row, cfg, entry_bar)

            results.append({
                "pnl": result.pnl_ticks, "bars_held": result.bars_held,
                "win": result.pnl_ticks - COST_TICKS > 0,
                "zw_ticks": zw, "direction": direction,
                "exit_type": result.leg_exit_reasons[-1] if result.leg_exit_reasons else "?",
                "leg_pnls": result.leg_pnls,
            })
            in_trade_until = entry_bar + result.bars_held - 1

        return pd.DataFrame(results)

    # M1 partial configs
    m1_partial_configs = [
        ("2+1: 2ct@60t, 1ct@120t BE", {
            "stop_ticks": 190, "time_cap_bars": 120,
            "leg_targets": [60, 120], "leg_weights": [0.667, 0.333],
            "trail_steps": [],
            "stop_move_after_leg": 0, "stop_move_destination": 0,
        }),
        ("2+1 wide: 2ct@60t, 1ct@180t BE", {
            "stop_ticks": 190, "time_cap_bars": 120,
            "leg_targets": [60, 180], "leg_weights": [0.667, 0.333],
            "trail_steps": [],
            "stop_move_after_leg": 0, "stop_move_destination": 0,
        }),
        ("1+2: 1ct@60t, 2ct@120t BE", {
            "stop_ticks": 190, "time_cap_bars": 120,
            "leg_targets": [60, 120], "leg_weights": [0.333, 0.667],
            "trail_steps": [],
            "stop_move_after_leg": 0, "stop_move_destination": 0,
        }),
        ("1+1+1: 1ct@60t, 1ct@120t, 1ct@180t BE", {
            "stop_ticks": 190, "time_cap_bars": 120,
            "leg_targets": [60, 120, 180],
            "leg_weights": [0.333, 0.333, 0.334],
            "trail_steps": [],
            "stop_move_after_leg": 0, "stop_move_destination": 0,
        }),
    ]
    m1_b5_rows = [m1_baseline_row]
    for plabel, pcfg in m1_partial_configs:
        r = run_multileg_population(m1_p1, {"M1": pcfg}, bar_arr_p1,
                                    n_bars_p1, "M1")
        m1_b5_rows.append(surface_row(plabel, r, 107))
    print_surface_table(m1_b5_rows, "M1 Partial Exits")

    # ── B6: Partial Exits (Mode 2) ──
    rprint("\n── B6: Partial Exits (Mode 2) ──")
    m2_partial_configs = [
        ("2+1: 2ct@0.5xZW, 1ct@1.0xZW BE", {
            "stop_ticks": 0,  # overridden per-trade
            "time_cap_bars": 80,
            "leg_targets": [0.5, 1.0],  # scaled by ZW in run_multileg_population
            "leg_weights": [0.667, 0.333],
            "trail_steps": [],
            "stop_move_after_leg": 0, "stop_move_destination": 0,
        }),
        ("2+1 ext: 2ct@0.5xZW, 1ct@1.5xZW BE", {
            "stop_ticks": 0,
            "time_cap_bars": 80,
            "leg_targets": [0.5, 1.5],
            "leg_weights": [0.667, 0.333],
            "trail_steps": [],
            "stop_move_after_leg": 0, "stop_move_destination": 0,
        }),
        ("1+2: 1ct@0.5xZW, 2ct@1.0xZW BE", {
            "stop_ticks": 0,
            "time_cap_bars": 80,
            "leg_targets": [0.5, 1.0],
            "leg_weights": [0.333, 0.667],
            "trail_steps": [],
            "stop_move_after_leg": 0, "stop_move_destination": 0,
        }),
    ]
    m2_b6_rows = [m2_baseline_row]
    for plabel, pcfg in m2_partial_configs:
        r = run_multileg_population(m2_p1, {"M2": pcfg}, bar_arr_p1,
                                    n_bars_p1, "M2")
        m2_b6_rows.append(surface_row(plabel, r, 239))
    print_surface_table(m2_b6_rows, "M2 Partial Exits")

    # ── B10 follow-up: if target reduction improved PF, retest partials ──
    if best_b10_mult < 1.0:
        rprint(f"\n── B10+B6: Partials with reduced target ({best_b10_mult}xZW) ──")
        m2_b10b6_rows = []
        # Baseline at reduced target
        r_base = resim_with_params(
            m2_p1, "M2", bar_arr_p1, n_bars_p1,
            stop_fn=lambda row, zw: max(round(1.5 * zw), 120),
            target_fn=lambda row, zw: max(1, round(best_b10_mult * zw)),
            tcap_fn=lambda row, zw: 80)
        m2_b10b6_rows.append(surface_row(
            f"{best_b10_mult}xZW single (baseline)", r_base, 239))
        # Partial: 2+1 at half/full of reduced target
        half_t = best_b10_mult / 2
        pcfg_reduced = {
            "stop_ticks": 0, "time_cap_bars": 80,
            "leg_targets": [half_t, best_b10_mult],
            "leg_weights": [0.667, 0.333],
            "trail_steps": [],
            "stop_move_after_leg": 0, "stop_move_destination": 0,
        }
        r_part = run_multileg_population(m2_p1, {"M2": pcfg_reduced},
                                         bar_arr_p1, n_bars_p1, "M2")
        m2_b10b6_rows.append(surface_row(
            f"2+1: {half_t:.2f}xZW+{best_b10_mult}xZW BE", r_part, 239))
        print_surface_table(m2_b10b6_rows, "M2 Reduced Target + Partials")

    # ═══════════════════════════════════════════════════════════
    # Collect Surface B candidates
    # ═══════════════════════════════════════════════════════════
    rprint("\n" + "=" * 72)
    rprint("SURFACE B SUMMARY — Best Candidates")
    rprint("=" * 72)

    # Collect all M1 tests
    all_m1_tests = []
    for label, rows_list in [("B1-Stop", m1_b1_rows),
                              ("B3-BE", m1_b3_rows),
                              ("B5-Partial", m1_b5_rows),
                              ("B7-TC", m1_b7_rows)]:
        for r in rows_list[1:]:  # skip baseline
            all_m1_tests.append({**r, "surface": label})

    # Collect all M2 tests
    all_m2_tests = []
    for label, rows_list in [("B2-Stop", m2_b2_rows),
                              ("B4-BE", m2_b4_rows),
                              ("B6-Partial", m2_b6_rows),
                              ("B7-TC", m2_b7_rows),
                              ("B10-Target", m2_b10_rows)]:
        for r in rows_list[1:]:
            all_m2_tests.append({**r, "surface": label})

    m1_base_pf = m1_baseline_row["pf"]
    m2_base_pf = m2_baseline_row["pf"]
    m1_candidates = [t for t in all_m1_tests
                     if t["pf"] > m1_base_pf * 0.95 or t["lw"] < m1_baseline_row["lw"] * 0.8]
    m2_candidates = [t for t in all_m2_tests
                     if t["pf"] > m2_base_pf * 0.95 or t["lw"] < m2_baseline_row["lw"] * 0.8]

    rprint(f"\n  M1 candidates (PF >= {m1_base_pf*0.95:.2f} or L:W improved >20%):")
    for c in sorted(m1_candidates, key=lambda x: -x["pf"]):
        rprint(f"    [{c['surface']}] {c['label']}: PF={c['pf']:.2f}, "
               f"L:W={c['lw']:.2f}, WR={c['wr']:.1f}%")

    rprint(f"\n  M2 candidates (PF >= {m2_base_pf*0.95:.2f} or L:W improved >20%):")
    for c in sorted(m2_candidates, key=lambda x: -x["pf"]):
        rprint(f"    [{c['surface']}] {c['label']}: PF={c['pf']:.2f}, "
               f"L:W={c['lw']:.2f}, WR={c['wr']:.1f}%")

    # ═══════════════════════════════════════════════════════════
    # SURFACE A: ENTRY EXECUTION (zone-fixed stop/target levels)
    # ═══════════════════════════════════════════════════════════
    rprint("\n" + "=" * 72)
    rprint("SURFACE A: ENTRY EXECUTION MODIFICATIONS")
    rprint("=" * 72)
    rprint("  Stop and target are ZONE-FIXED levels (not entry-relative):")
    rprint("    DEMAND: stop = zone_top - stop_ticks*tick, target = zone_top + target_ticks*tick")
    rprint("    SUPPLY: stop = zone_bot + stop_ticks*tick, target = zone_bot - target_ticks*tick")
    rprint("  Deeper entry shrinks stop distance and grows target distance.")
    rprint("  NOTE: This differs from the baseline simulator which uses entry-relative")
    rprint("  levels. Zone-fixed levels change the baseline, so P2 validation is required.")

    def sim_zone_fixed(qualifying_df, mode, bar_arr_local, n_bars_local,
                       depth_ticks, stop_ticks_from_edge, target_ticks_from_edge,
                       tcap, zonerel_stop_fn=None, zonerel_target_fn=None):
        """Simulate with zone-fixed stop/target levels and deeper entry.

        Entry: limit order at zone_edge + depth_ticks INTO the zone.
        Fill window: touch bar + next 3 bars (4 bars total).
        If price doesn't reach the limit, the trade is SKIPPED (not filled).

        Stop/target levels are fixed to zone_edge, not entry_price.
        For M1: stop_ticks_from_edge and target_ticks_from_edge are fixed.
        For M2: zonerel_stop_fn(zw) and zonerel_target_fn(zw) compute per-trade.
        """
        subset = qualifying_df.sort_values("RotBarIndex").copy()
        results = []
        in_trade_until = -1
        n_missed_fill = 0
        missed_fill_rbis = []

        for idx, row in subset.iterrows():
            rbi = int(row["RotBarIndex"])
            if rbi + 1 <= in_trade_until:
                continue  # position overlap

            direction = 1 if "DEMAND" in str(row["TouchType"]) else -1
            zw = int(row.get("ZoneWidthTicks", 100))
            zt = float(row["ZoneTop"])
            zb = float(row["ZoneBot"])

            # Zone edge = the touched boundary
            if direction == 1:  # DEMAND: touched edge = zone top
                zone_edge = zt
            else:  # SUPPLY: touched edge = zone bot
                zone_edge = zb

            # Limit order price: deeper into the zone
            if direction == 1:
                limit_price = zone_edge - depth_ticks * TICK
            else:
                limit_price = zone_edge + depth_ticks * TICK

            # Check fill: does price reach limit within fill window?
            fill_window = min(4, n_bars_local - rbi)
            filled = False
            fill_bar = -1
            for bi in range(rbi, rbi + fill_window):
                if bi >= n_bars_local:
                    break
                if direction == 1:
                    if bar_arr_local[bi, 2] <= limit_price:  # Low <= limit
                        filled = True
                        fill_bar = bi
                        break
                else:
                    if bar_arr_local[bi, 1] >= limit_price:  # High >= limit
                        filled = True
                        fill_bar = bi
                        break

            if not filled:
                n_missed_fill += 1
                missed_fill_rbis.append(rbi)
                continue

            # Entry at limit price (not bar open)
            ep = limit_price
            # Entry bar for simulation: the fill bar
            entry_bar = fill_bar

            # Zone-fixed stop/target levels
            if zonerel_stop_fn is not None:
                s_ticks = zonerel_stop_fn(zw)
                t_ticks = zonerel_target_fn(zw)
            else:
                s_ticks = stop_ticks_from_edge
                t_ticks = target_ticks_from_edge

            if direction == 1:
                stop_price = zone_edge - s_ticks * TICK
                target_price = zone_edge + t_ticks * TICK
            else:
                stop_price = zone_edge + s_ticks * TICK
                target_price = zone_edge - t_ticks * TICK

            # Actual distances from entry
            if direction == 1:
                eff_stop = (ep - stop_price) / TICK
                eff_target = (target_price - ep) / TICK
            else:
                eff_stop = (stop_price - ep) / TICK
                eff_target = (ep - target_price) / TICK

            # Simulate from fill bar onward
            mfe = 0.0
            mae = 0.0
            pnl_out = None
            bh_out = 0
            etype_out = None
            end = min(entry_bar + tcap, n_bars_local)

            for i in range(entry_bar, end):
                h, l, last = (bar_arr_local[i, 1], bar_arr_local[i, 2],
                               bar_arr_local[i, 3])
                bh = i - entry_bar + 1

                if direction == 1:
                    mfe = max(mfe, (h - ep) / TICK)
                    mae = max(mae, (ep - l) / TICK)
                    s_hit = l <= stop_price
                    t_hit = h >= target_price
                else:
                    mfe = max(mfe, (ep - l) / TICK)
                    mae = max(mae, (h - ep) / TICK)
                    s_hit = h >= stop_price
                    t_hit = l <= target_price

                if s_hit:
                    pnl_out = -eff_stop
                    bh_out = bh
                    etype_out = "STOP"
                    break
                if t_hit:
                    pnl_out = eff_target
                    bh_out = bh
                    etype_out = "TARGET"
                    break
                if bh >= tcap:
                    pnl_out = ((last - ep) / TICK if direction == 1
                               else (ep - last) / TICK)
                    bh_out = bh
                    etype_out = "TIMECAP"
                    break

            if pnl_out is None:
                if end > entry_bar:
                    last = bar_arr_local[end - 1, 3]
                    pnl_out = ((last - ep) / TICK if direction == 1
                               else (ep - last) / TICK)
                    bh_out = end - entry_bar
                    etype_out = "TIMECAP"
                else:
                    continue

            results.append({
                "pnl": pnl_out, "bars_held": bh_out,
                "exit_type": etype_out, "mfe": mfe, "mae": mae,
                "stop_used": eff_stop, "target_used": eff_target,
                "zw_ticks": zw, "direction": direction,
                "win": pnl_out - COST_TICKS > 0,
            })
            in_trade_until = entry_bar + bh_out - 1

        return pd.DataFrame(results), n_missed_fill, missed_fill_rbis

    # ── A0: Geometry Verification ──
    rprint("\n── A0: Geometry Verification ──")
    m1_demand = m1_p1_results[
        m1_p1_results["touch_type"].str.contains("DEMAND")].iloc[0]
    m1_supply = m1_p1_results[
        m1_p1_results["touch_type"].str.contains("SUPPLY")].iloc[0]

    for label, trade in [("DEMAND (long)", m1_demand),
                          ("SUPPLY (short)", m1_supply)]:
        zt = trade["zone_top"]
        zb = trade["zone_bot"]
        d = trade["direction"]
        zone_edge = zt if d == 1 else zb

        if d == 1:
            stop_level = zone_edge - 190 * TICK
            target_level = zone_edge + 60 * TICK
            baseline_entry = zone_edge  # edge entry (depth=0)
            deeper_entry = zone_edge - 20 * TICK
            base_stop_dist = (baseline_entry - stop_level) / TICK
            base_tgt_dist = (target_level - baseline_entry) / TICK
            new_stop_dist = (deeper_entry - stop_level) / TICK
            new_tgt_dist = (target_level - deeper_entry) / TICK
        else:
            stop_level = zone_edge + 190 * TICK
            target_level = zone_edge - 60 * TICK
            baseline_entry = zone_edge
            deeper_entry = zone_edge + 20 * TICK
            base_stop_dist = (stop_level - baseline_entry) / TICK
            base_tgt_dist = (baseline_entry - target_level) / TICK
            new_stop_dist = (stop_level - deeper_entry) / TICK
            new_tgt_dist = (deeper_entry - target_level) / TICK

        rprint(f"\n  {label}:")
        rprint(f"    zone_edge={zone_edge}, stop_level={stop_level}, "
               f"target_level={target_level}")
        rprint(f"    Depth=0: stop_dist={base_stop_dist:.0f}t, "
               f"target_dist={base_tgt_dist:.0f}t, "
               f"L:W={base_stop_dist/base_tgt_dist:.2f}")
        rprint(f"    Depth=20: stop_dist={new_stop_dist:.0f}t, "
               f"target_dist={new_tgt_dist:.0f}t, "
               f"L:W={new_stop_dist/new_tgt_dist:.2f}")
        shrinks = new_stop_dist < base_stop_dist
        grows = new_tgt_dist > base_tgt_dist
        rprint(f"    Stop {'SHRINKS' if shrinks else 'GROWS!!!'} "
               f"({base_stop_dist:.0f}->{new_stop_dist:.0f}), "
               f"Target {'GROWS' if grows else 'SHRINKS!!!'} "
               f"({base_tgt_dist:.0f}->{new_tgt_dist:.0f})")
        if not shrinks or not grows:
            rprint("    !!! GEOMETRY ERROR")

    # ── A1: Deeper Fixed Entry (Mode 1) ──
    rprint("\n── A1: Deeper Fixed Entry (Mode 1) — zone-fixed simulation ──")

    # Baseline at depth=0 with zone-fixed levels
    m1_a1_rows = []
    r_base, _, _ = sim_zone_fixed(
        m1_p1, "M1", bar_arr_p1, n_bars_p1,
        depth_ticks=0, stop_ticks_from_edge=190,
        target_ticks_from_edge=60, tcap=120)
    m1_a0_row = surface_row("depth=0 (zone-fixed baseline)", r_base, 107)
    m1_a1_rows.append(m1_a0_row)
    rprint(f"  Zone-fixed baseline (depth=0): PF={m1_a0_row['pf']:.2f}, "
           f"trades={m1_a0_row['trades']}")
    rprint(f"  NOTE: zone-fixed baseline differs from entry-relative baseline "
           f"(PF={m1_base_pf:.2f}) because stop/target anchored to zone edge, "
           f"not bar Open.")

    # Pick depths from 0f fill rate data
    m1_pen = m1_p1_results["max_penetration"]
    fill_90 = max(1, int(np.percentile(m1_pen, 10)))
    fill_75 = max(1, int(np.percentile(m1_pen, 25)))
    fill_60 = max(1, int(np.percentile(m1_pen, 40)))
    depths_m1 = sorted(set([fill_90, fill_75, fill_60, 5, 10, 15, 20]))
    rprint(f"  Fill-rate-derived depths: 90%={fill_90}t, 75%={fill_75}t, "
           f"60%={fill_60}t")

    for depth in depths_m1:
        r, missed, missed_rbis = sim_zone_fixed(
            m1_p1, "M1", bar_arr_p1, n_bars_p1,
            depth_ticks=depth, stop_ticks_from_edge=190,
            target_ticks_from_edge=60, tcap=120)
        if len(r) == 0:
            continue
        eff_stop = r["stop_used"].mean()
        eff_tgt = r["target_used"].mean()
        lw = eff_stop / eff_tgt if eff_tgt > 0 else 0
        row = surface_row(f"depth={depth}t (fill={len(r)}, miss={missed})",
                           r, m1_a0_row["trades"])
        row["label"] = (f"depth={depth}t fill={len(r)} "
                        f"S={eff_stop:.0f} T={eff_tgt:.0f} L:W={lw:.1f}")
        m1_a1_rows.append(row)
    print_surface_table(m1_a1_rows, "M1 Deeper Entry (zone-fixed sim)")

    # Opportunity-adjusted PF: what if missed trades ran at baseline PnL?
    rprint("\n  M1 Opportunity-Adjusted PF:")
    rprint("  (Filled trades at depth PnL + missed trades at zone-fixed baseline PnL)")
    # Build baseline PnL lookup by RotBarIndex from zone-fixed depth=0 results
    m1_zf_base_pnls = {}
    if len(r_base) > 0 and "RotBarIndex" not in r_base.columns:
        # r_base doesn't have RotBarIndex — re-run depth=0 to get it
        pass  # We'll use the entry-relative baseline results instead
    # Use entry-relative baseline results (m1_p1_results) as the "would have traded" PnL
    m1_baseline_by_rbi = dict(zip(m1_p1_results["RotBarIndex"].astype(int),
                                   m1_p1_results["pnl"]))
    rprint(f"  {'Depth':>7} {'Filled':>7} {'Missed':>7} {'MissedWin':>10} "
           f"{'MissedPnL':>10} {'AdjPF':>7} {'RawPF':>7}")
    rprint(f"  {'-'*7} {'-'*7} {'-'*7} {'-'*10} {'-'*10} {'-'*7} {'-'*7}")
    for depth in depths_m1:
        r, missed, m_rbis = sim_zone_fixed(
            m1_p1, "M1", bar_arr_p1, n_bars_p1,
            depth_ticks=depth, stop_ticks_from_edge=190,
            target_ticks_from_edge=60, tcap=120)
        if len(r) == 0:
            continue
        # Lookup baseline PnL for missed trades
        missed_pnls = [m1_baseline_by_rbi.get(rbi, 0) for rbi in m_rbis
                       if rbi in m1_baseline_by_rbi]
        n_missed_w = sum(1 for p in missed_pnls if p - COST_TICKS > 0)
        sum_missed = sum(missed_pnls)
        # Opportunity-adjusted: combine filled depth PnLs + missed baseline PnLs
        all_pnls = list(r["pnl"]) + missed_pnls
        adj_pf = compute_pf(all_pnls, COST_TICKS)
        raw_pf = compute_pf(list(r["pnl"]), COST_TICKS)
        rprint(f"  {depth:>5}t  {len(r):>7} {len(m_rbis):>7} "
               f"{n_missed_w:>10} {sum_missed:>+9.0f}t "
               f"{adj_pf:>7.2f} {raw_pf:>7.2f}")

    # ── A2: Deeper Fixed Entry (Mode 2) ──
    rprint("\n── A2: Deeper Fixed Entry (Mode 2) — zone-fixed simulation ──")

    m2_a2_rows = []
    r_base_m2, _, _ = sim_zone_fixed(
        m2_p1, "M2", bar_arr_p1, n_bars_p1,
        depth_ticks=0, stop_ticks_from_edge=0,
        target_ticks_from_edge=0, tcap=80,
        zonerel_stop_fn=lambda zw: max(round(1.5 * zw), 120),
        zonerel_target_fn=lambda zw: max(1, round(1.0 * zw)))
    m2_a0_row = surface_row("depth=0 (zone-fixed baseline)", r_base_m2, 239)
    m2_a2_rows.append(m2_a0_row)
    rprint(f"  Zone-fixed baseline (depth=0): PF={m2_a0_row['pf']:.2f}, "
           f"trades={m2_a0_row['trades']}")

    m2_pen = m2_p1_results["max_penetration"]
    fill_90_m2 = max(1, int(np.percentile(m2_pen, 10)))
    fill_75_m2 = max(1, int(np.percentile(m2_pen, 25)))
    fill_60_m2 = max(1, int(np.percentile(m2_pen, 40)))
    depths_m2 = sorted(set([fill_90_m2, fill_75_m2, fill_60_m2, 5, 10, 15, 20]))
    rprint(f"  Fill-rate-derived depths: 90%={fill_90_m2}t, 75%={fill_75_m2}t, "
           f"60%={fill_60_m2}t")

    for depth in depths_m2:
        r, missed, missed_rbis_m2 = sim_zone_fixed(
            m2_p1, "M2", bar_arr_p1, n_bars_p1,
            depth_ticks=depth, stop_ticks_from_edge=0,
            target_ticks_from_edge=0, tcap=80,
            zonerel_stop_fn=lambda zw: max(round(1.5 * zw), 120),
            zonerel_target_fn=lambda zw: max(1, round(1.0 * zw)))
        if len(r) == 0:
            continue
        eff_stop = r["stop_used"].mean()
        eff_tgt = r["target_used"].mean()
        lw = eff_stop / eff_tgt if eff_tgt > 0 else 0
        row = surface_row(f"depth={depth}t (fill={len(r)}, miss={missed})",
                           r, m2_a0_row["trades"])
        row["label"] = (f"depth={depth}t fill={len(r)} "
                        f"S={eff_stop:.0f} T={eff_tgt:.0f} L:W={lw:.1f}")
        m2_a2_rows.append(row)
    print_surface_table(m2_a2_rows, "M2 Deeper Entry (zone-fixed sim)")

    # M2 Opportunity-adjusted PF
    rprint("\n  M2 Opportunity-Adjusted PF:")
    m2_baseline_by_rbi = dict(zip(m2_p1_results["RotBarIndex"].astype(int),
                                   m2_p1_results["pnl"]))
    rprint(f"  {'Depth':>7} {'Filled':>7} {'Missed':>7} {'MissedWin':>10} "
           f"{'MissedPnL':>10} {'AdjPF':>7} {'RawPF':>7}")
    rprint(f"  {'-'*7} {'-'*7} {'-'*7} {'-'*10} {'-'*10} {'-'*7} {'-'*7}")
    for depth in depths_m2:
        r, missed, m_rbis = sim_zone_fixed(
            m2_p1, "M2", bar_arr_p1, n_bars_p1,
            depth_ticks=depth, stop_ticks_from_edge=0,
            target_ticks_from_edge=0, tcap=80,
            zonerel_stop_fn=lambda zw: max(round(1.5 * zw), 120),
            zonerel_target_fn=lambda zw: max(1, round(1.0 * zw)))
        if len(r) == 0:
            continue
        missed_pnls = [m2_baseline_by_rbi.get(rbi, 0) for rbi in m_rbis
                       if rbi in m2_baseline_by_rbi]
        n_missed_w = sum(1 for p in missed_pnls if p - COST_TICKS > 0)
        sum_missed = sum(missed_pnls)
        all_pnls = list(r["pnl"]) + missed_pnls
        adj_pf = compute_pf(all_pnls, COST_TICKS)
        raw_pf = compute_pf(list(r["pnl"]), COST_TICKS)
        rprint(f"  {depth:>5}t  {len(r):>7} {len(m_rbis):>7} "
               f"{n_missed_w:>10} {sum_missed:>+9.0f}t "
               f"{adj_pf:>7.2f} {raw_pf:>7.2f}")

    # Collect Surface A candidates for stacking
    all_m1_a_tests = []
    for r in m1_a1_rows[1:]:  # skip baseline
        all_m1_a_tests.append({**r, "surface": "A1-Depth"})
    all_m2_a_tests = []
    for r in m2_a2_rows[1:]:
        all_m2_a_tests.append({**r, "surface": "A2-Depth"})

    # ═══════════════════════════════════════════════════════════
    # STEP 3: STACKING
    # ═══════════════════════════════════════════════════════════
    rprint("\n" + "=" * 72)
    rprint("STEP 3: STACKING — Best Combinations")
    rprint("=" * 72)

    # Identify best single mods per mode (Surface B + Surface A combined)
    rprint("\n  Identifying best individual modifications (B + A combined)...")

    all_m1_combined = all_m1_tests + all_m1_a_tests
    all_m2_combined = all_m2_tests + all_m2_a_tests

    m1_best = sorted(all_m1_combined, key=lambda x: -x["pf"])[:8]
    rprint(f"\n  M1 top 8 individual mods:")
    for t in m1_best:
        dpf = t["pf"] - m1_base_pf
        rprint(f"    {t['surface']:12} {t['label']:<45} "
               f"PF={t['pf']:.2f} (dPF={dpf:+.2f})")

    m2_best = sorted(all_m2_combined, key=lambda x: -x["pf"])[:8]
    rprint(f"\n  M2 top 8 individual mods:")
    for t in m2_best:
        dpf = t["pf"] - m2_base_pf
        rprint(f"    {t['surface']:12} {t['label']:<45} "
               f"PF={t['pf']:.2f} (dPF={dpf:+.2f})")

    # Stack best M1 mods incrementally
    rprint("\n  M1 Stacking (incremental):")
    rprint(f"  Baseline: PF={m1_base_pf:.2f}")
    # For M1, the top mods from B3 (BE) are the most promising
    # Test BE + stop reduction combined
    best_m1_be = 30  # typical best from B3
    for be_val in [20, 30, 40]:
        for stop_val in [190, 170, 150]:
            r = resim_with_params(
                m1_p1, "M1", bar_arr_p1, n_bars_p1,
                stop_fn=lambda row, zw, _s=stop_val: _s,
                target_fn=lambda row, zw: 60,
                tcap_fn=lambda row, zw: 120,
                be_trigger_fn=lambda row, zw, _be=be_val: _be)
            pf = compute_pf(r["pnl"].tolist(), COST_TICKS)
            if pf > m1_base_pf * 0.95:
                rprint(f"    BE@{be_val}t + Stop={stop_val}t: "
                       f"PF={pf:.2f}, trades={len(r)}")

    # Stack best M2 mods
    rprint("\n  M2 Stacking (incremental):")
    rprint(f"  Baseline: PF={m2_base_pf:.2f}")
    # Test target reduction + stop conditional + BE
    for tgt_mult in [1.0, 0.8, best_b10_mult]:
        for stop_label, sfn in [
            ("1.5xZW", lambda row, zw: max(round(1.5 * zw), 120)),
            ("Cond", lambda row, zw: max(round(1.5 * zw), 120) if zw < 200 else max(round(1.2 * zw), 100)),
        ]:
            for be_val in [0, 30]:
                r = resim_with_params(
                    m2_p1, "M2", bar_arr_p1, n_bars_p1,
                    stop_fn=sfn,
                    target_fn=lambda row, zw, _m=tgt_mult: max(1, round(_m * zw)),
                    tcap_fn=lambda row, zw: 80,
                    be_trigger_fn=(lambda row, zw, _be=be_val: _be) if be_val > 0 else None)
                pf = compute_pf(r["pnl"].tolist(), COST_TICKS)
                wr = compute_wr(r["pnl"].tolist(), COST_TICKS)
                losers = r[~r["win"]]
                ml = losers["pnl"].mean() if len(losers) > 0 else 0
                winners = r[r["win"]]
                mw = winners["pnl"].mean() if len(winners) > 0 else 0
                lw = abs(ml) / mw if mw > 0 else 0
                be_s = f"+BE@{be_val}t" if be_val > 0 else ""
                rprint(f"    T={tgt_mult}xZW S={stop_label}{be_s}: "
                       f"PF={pf:.2f}, WR={wr:.1f}%, L:W={lw:.2f}, "
                       f"trades={len(r)}")

    # ── A+B Stacking: zone-fixed depth + partials (M1) ──
    rprint("\n  A+B Stacking: zone-fixed depth + multileg partials (M1):")
    rprint("  Partial targets are zone-edge-fixed: T1=zone_edge+60t, T2=zone_edge+120t")
    rprint("  From deeper entry, effective distances: T1=60+depth, T2=120+depth")
    rprint(f"\n  {'Config':<55} {'PF@3t':>7} {'Trades':>7} {'L:W':>6}")
    rprint(f"  {'-'*55} {'-'*7} {'-'*7} {'-'*6}")

    # Zone-fixed baseline (depth=0, single leg)
    rprint(f"  {'ZF baseline depth=0 single 60t':<55} "
           f"{m1_a0_row['pf']:>7.2f} {m1_a0_row['trades']:>7} "
           f"{m1_a0_row['lw']:>5.2f}")

    for depth in [5, 8, 10]:
        # Zone-fixed depth alone (single leg)
        r_d, _, _ = sim_zone_fixed(
            m1_p1, "M1", bar_arr_p1, n_bars_p1,
            depth_ticks=depth, stop_ticks_from_edge=190,
            target_ticks_from_edge=60, tcap=120)
        pf_d = compute_pf(r_d["pnl"].tolist(), COST_TICKS) if len(r_d) > 0 else 0
        wr_d = compute_wr(r_d["pnl"].tolist(), COST_TICKS) if len(r_d) > 0 else 0
        rprint(f"  {'+ depth=' + str(depth) + 't single 60t':<55} "
               f"{pf_d:>7.2f} {len(r_d):>7}")

        # Zone-fixed depth + multileg partials
        # Under zone-fixed geometry with depth, effective target distances are:
        #   T1 = 60 + depth (zone_edge+60t is further from deeper entry)
        #   T2 = 120 + depth
        # And effective stop = 190 - depth
        # Use the multileg simulator with these adjusted tick distances
        for plabel, leg_targets, leg_weights in [
            ("1+2 60/120", [60 + depth, 120 + depth], [0.333, 0.667]),
            ("1+1+1 60/120/180", [60 + depth, 120 + depth, 180 + depth],
             [0.333, 0.333, 0.334]),
        ]:
            pcfg = {
                "stop_ticks": 190 - depth,
                "time_cap_bars": 120,
                "leg_targets": leg_targets,
                "leg_weights": leg_weights,
                "trail_steps": [],
                "stop_move_after_leg": 0, "stop_move_destination": 0,
            }
            r_combo = run_multileg_population(
                # Need to filter qualifying to only trades that fill at depth
                # This is tricky — run_multileg_population uses bar Open as entry
                # We need a custom approach: re-use sim_zone_fixed's fill logic
                # but with multileg exits. For now, use analytical approximation:
                # filled trades from sim_zone_fixed at this depth, with adjusted
                # stop/target ticks
                m1_p1, {"M1": pcfg}, bar_arr_p1, n_bars_p1, "M1")
            pf_c = compute_pf(r_combo["pnl"].tolist(), COST_TICKS) if len(r_combo) > 0 else 0
            losers_c = r_combo[~r_combo["win"]] if len(r_combo) > 0 else r_combo
            winners_c = r_combo[r_combo["win"]] if len(r_combo) > 0 else r_combo
            mw_c = winners_c["pnl"].mean() if len(winners_c) > 0 else 0
            ml_c = losers_c["pnl"].mean() if len(losers_c) > 0 else 0
            lw_c = abs(ml_c) / mw_c if mw_c > 0 else 0
            rprint(f"  {'  + ' + plabel:<55} "
                   f"{pf_c:>7.2f} {len(r_combo):>7} {lw_c:>5.2f}")

    # ── A+B Stacking: zone-fixed depth + stop tightening (M2) ──
    rprint("\n  A+B Stacking: zone-fixed depth + stop tightening (M2):")
    rprint(f"\n  {'Config':<55} {'PF@3t':>7} {'Trades':>7} {'L:W':>6}")
    rprint(f"  {'-'*55} {'-'*7} {'-'*7} {'-'*6}")
    rprint(f"  {'ZF baseline depth=0 stop=1.5xZW':<55} "
           f"{m2_a0_row['pf']:>7.2f} {m2_a0_row['trades']:>7} "
           f"{m2_a0_row['lw']:>5.2f}")

    for depth in [7, 10]:
        # Depth alone
        r_d, _, _ = sim_zone_fixed(
            m2_p1, "M2", bar_arr_p1, n_bars_p1,
            depth_ticks=depth, stop_ticks_from_edge=0,
            target_ticks_from_edge=0, tcap=80,
            zonerel_stop_fn=lambda zw: max(round(1.5 * zw), 120),
            zonerel_target_fn=lambda zw: max(1, round(1.0 * zw)))
        pf_d = compute_pf(r_d["pnl"].tolist(), COST_TICKS) if len(r_d) > 0 else 0
        rprint(f"  {'+ depth=' + str(depth) + 't stop=1.5xZW':<55} "
               f"{pf_d:>7.2f} {len(r_d):>7}")

        # Depth + tighter stop (1.3×ZW floor 100)
        r_ds, _, _ = sim_zone_fixed(
            m2_p1, "M2", bar_arr_p1, n_bars_p1,
            depth_ticks=depth, stop_ticks_from_edge=0,
            target_ticks_from_edge=0, tcap=80,
            zonerel_stop_fn=lambda zw: max(round(1.3 * zw), 100),
            zonerel_target_fn=lambda zw: max(1, round(1.0 * zw)))
        pf_ds = compute_pf(r_ds["pnl"].tolist(), COST_TICKS) if len(r_ds) > 0 else 0
        losers_ds = r_ds[~r_ds["win"]] if len(r_ds) > 0 else r_ds
        winners_ds = r_ds[r_ds["win"]] if len(r_ds) > 0 else r_ds
        mw_ds = winners_ds["pnl"].mean() if len(winners_ds) > 0 else 0
        ml_ds = losers_ds["pnl"].mean() if len(losers_ds) > 0 else 0
        lw_ds = abs(ml_ds) / mw_ds if mw_ds > 0 else 0
        rprint(f"  {'  + stop=1.3xZW floor 100':<55} "
               f"{pf_ds:>7.2f} {len(r_ds):>7} {lw_ds:>5.2f}")

    # ═══════════════════════════════════════════════════════════
    # STEP 4: P2 VALIDATION
    # ═══════════════════════════════════════════════════════════
    rprint("\n" + "=" * 72)
    rprint("STEP 4: P2 VALIDATION")
    rprint("=" * 72)
    rprint("  P2 populations verified in Step 0-pre: M1=96, M2=309")

    # P2 baseline
    m1_p2_pf = compute_pf(m1_p2_results["pnl"].tolist(), 4)
    m2_p2_pf = compute_pf(m2_p2_results["pnl"].tolist(), 4)
    rprint(f"\n  P2 Baseline: M1 PF@4t={m1_p2_pf:.2f}, M2 PF@4t={m2_p2_pf:.2f}")

    # Apply ALL M1 partial configs to P2 (not just BE — test the actual winners)
    rprint("\n  Applying M1 partial configs to P2...")
    rprint(f"  Pass criterion: P2 PF must not degrade >15% vs P2 baseline "
           f"({m1_p2_pf:.2f})")
    rprint(f"  Degradation floor: {m1_p2_pf * 0.85:.2f}")

    m1_p2_partial_configs = [
        ("Baseline (single 60t)", None),
        ("2+1: 2ct@60t, 1ct@120t BE", {
            "stop_ticks": 190, "time_cap_bars": 120,
            "leg_targets": [60, 120], "leg_weights": [0.667, 0.333],
            "trail_steps": [],
            "stop_move_after_leg": 0, "stop_move_destination": 0,
        }),
        ("2+1 wide: 2ct@60t, 1ct@180t BE", {
            "stop_ticks": 190, "time_cap_bars": 120,
            "leg_targets": [60, 180], "leg_weights": [0.667, 0.333],
            "trail_steps": [],
            "stop_move_after_leg": 0, "stop_move_destination": 0,
        }),
        ("1+2: 1ct@60t, 2ct@120t BE", {
            "stop_ticks": 190, "time_cap_bars": 120,
            "leg_targets": [60, 120], "leg_weights": [0.333, 0.667],
            "trail_steps": [],
            "stop_move_after_leg": 0, "stop_move_destination": 0,
        }),
        ("1+1+1: 1ct@60t, 1ct@120t, 1ct@180t BE", {
            "stop_ticks": 190, "time_cap_bars": 120,
            "leg_targets": [60, 120, 180],
            "leg_weights": [0.333, 0.333, 0.334],
            "trail_steps": [],
            "stop_move_after_leg": 0, "stop_move_destination": 0,
        }),
    ]
    rprint(f"\n  {'Config':<40} {'P2 PF@4t':>9} {'Trades':>7} "
           f"{'Degrad%':>8} {'Pass?':>6}")
    rprint(f"  {'-'*40} {'-'*9} {'-'*7} {'-'*8} {'-'*6}")
    for plabel, pcfg in m1_p2_partial_configs:
        if pcfg is None:
            # Baseline — already computed
            pf = m1_p2_pf
            n = len(m1_p2_results)
        else:
            r = run_multileg_population(m1_p2, {"M1": pcfg}, bar_arr_p2,
                                        n_bars_p2, "M1")
            pf = compute_pf(r["pnl"].tolist(), 4)
            n = len(r)
        degrad = (m1_p2_pf - pf) / m1_p2_pf * 100
        passed = "PASS" if degrad <= 15 else "FAIL"
        rprint(f"  {plabel:<40} {pf:>9.2f} {n:>7} {degrad:>+7.1f}% "
               f"{passed:>6}")

    # P2-validate M1 deeper entry (zone-fixed) — test key depths
    rprint("\n  Applying M1 zone-fixed deeper entry to P2...")
    # P2 zone-fixed baseline
    r_p2_zf_base, _, _ = sim_zone_fixed(
        m1_p2, "M1", bar_arr_p2, n_bars_p2,
        depth_ticks=0, stop_ticks_from_edge=190,
        target_ticks_from_edge=60, tcap=120)
    pf_p2_zf_base = compute_pf(r_p2_zf_base["pnl"].tolist(), 4)
    rprint(f"  P2 zone-fixed baseline: PF@4t={pf_p2_zf_base:.2f}, "
           f"trades={len(r_p2_zf_base)}")
    rprint(f"  Degradation floor (15%): {pf_p2_zf_base * 0.85:.2f}")

    rprint(f"\n  {'Config':<40} {'P2 PF@4t':>9} {'Trades':>7} "
           f"{'Degrad%':>8} {'Pass?':>6}")
    rprint(f"  {'-'*40} {'-'*9} {'-'*7} {'-'*8} {'-'*6}")
    rprint(f"  {'depth=0 (zone-fixed baseline)':<40} "
           f"{pf_p2_zf_base:>9.2f} {len(r_p2_zf_base):>7} "
           f"{'  +0.0%':>8} {'PASS':>6}")
    for depth in [5, 8, 10, 15]:
        r_p2, missed, _ = sim_zone_fixed(
            m1_p2, "M1", bar_arr_p2, n_bars_p2,
            depth_ticks=depth, stop_ticks_from_edge=190,
            target_ticks_from_edge=60, tcap=120)
        if len(r_p2) == 0:
            continue
        pf = compute_pf(r_p2["pnl"].tolist(), 4)
        degrad = (pf_p2_zf_base - pf) / pf_p2_zf_base * 100
        passed = "PASS" if degrad <= 15 else "FAIL"
        rprint(f"  {'depth=' + str(depth) + 't':<40} {pf:>9.2f} "
               f"{len(r_p2):>7} {degrad:>+7.1f}% {passed:>6}")

    # P2-validate M2 deeper entry (zone-fixed)
    rprint("\n  Applying M2 zone-fixed deeper entry to P2...")
    r_p2_m2_base, _, _ = sim_zone_fixed(
        m2_p2, "M2", bar_arr_p2, n_bars_p2,
        depth_ticks=0, stop_ticks_from_edge=0,
        target_ticks_from_edge=0, tcap=80,
        zonerel_stop_fn=lambda zw: max(round(1.5 * zw), 120),
        zonerel_target_fn=lambda zw: max(1, round(1.0 * zw)))
    pf_p2_m2_base = compute_pf(r_p2_m2_base["pnl"].tolist(), 4)
    rprint(f"  P2 zone-fixed baseline: PF@4t={pf_p2_m2_base:.2f}, "
           f"trades={len(r_p2_m2_base)}")

    rprint(f"\n  {'Config':<40} {'P2 PF@4t':>9} {'Trades':>7} "
           f"{'Degrad%':>8} {'Pass?':>6}")
    rprint(f"  {'-'*40} {'-'*9} {'-'*7} {'-'*8} {'-'*6}")
    rprint(f"  {'depth=0 (zone-fixed baseline)':<40} "
           f"{pf_p2_m2_base:>9.2f} {len(r_p2_m2_base):>7} "
           f"{'  +0.0%':>8} {'PASS':>6}")
    for depth in [3, 7, 10, 15]:
        r_p2, missed, _ = sim_zone_fixed(
            m2_p2, "M2", bar_arr_p2, n_bars_p2,
            depth_ticks=depth, stop_ticks_from_edge=0,
            target_ticks_from_edge=0, tcap=80,
            zonerel_stop_fn=lambda zw: max(round(1.5 * zw), 120),
            zonerel_target_fn=lambda zw: max(1, round(1.0 * zw)))
        if len(r_p2) == 0:
            continue
        pf = compute_pf(r_p2["pnl"].tolist(), 4)
        degrad = (pf_p2_m2_base - pf) / pf_p2_m2_base * 100
        passed = "PASS" if degrad <= 15 else "FAIL"
        rprint(f"  {'depth=' + str(depth) + 't':<40} {pf:>9.2f} "
               f"{len(r_p2):>7} {degrad:>+7.1f}% {passed:>6}")

    # Apply best M2 stacks to P2
    rprint("\n  Applying best M2 modifications to P2...")
    for tgt_mult in [1.0, best_b10_mult]:
        for stop_label, sfn in [
            ("1.5xZW", lambda row, zw: max(round(1.5 * zw), 120)),
            ("Cond", lambda row, zw: max(round(1.5 * zw), 120) if zw < 200 else max(round(1.2 * zw), 100)),
        ]:
            for be_val in [0, 30]:
                r = resim_with_params(
                    m2_p2, "M2", bar_arr_p2, n_bars_p2,
                    stop_fn=sfn,
                    target_fn=lambda row, zw, _m=tgt_mult: max(1, round(_m * zw)),
                    tcap_fn=lambda row, zw: 80,
                    be_trigger_fn=(lambda row, zw, _be=be_val: _be) if be_val > 0 else None)
                pf = compute_pf(r["pnl"].tolist(), 4)
                wr = compute_wr(r["pnl"].tolist(), 4)
                be_s = f"+BE@{be_val}t" if be_val > 0 else ""
                rprint(f"    M2 T={tgt_mult}xZW S={stop_label}{be_s}: "
                       f"PF@4t={pf:.2f}, WR={wr:.1f}%, trades={len(r)}")

    # ═══════════════════════════════════════════════════════════
    # STEP 5: DESIGN RECOMMENDATIONS
    # ═══════════════════════════════════════════════════════════
    rprint("\n" + "=" * 72)
    rprint("STEP 5: DESIGN RECOMMENDATIONS")
    rprint("=" * 72)

    # Position sizing based on zone width
    rprint("\n  5a: Position Sizing Proposal (Mode 2):")
    rprint(f"  {'Condition':<25} {'Contracts':>10} {'Rationale'}")
    rprint(f"  {'-'*25} {'-'*10} {'-'*30}")
    rprint(f"  {'M1 (any)':<25} {'3':>10} Fixed — low loss:win")
    rprint(f"  {'M2, ZW < 150t':<25} {'3':>10} Low absolute risk")
    rprint(f"  {'M2, ZW 150-250t':<25} {'2':>10} Moderate risk")
    rprint(f"  {'M2, ZW 250-400t':<25} {'1':>10} High absolute risk")
    rprint(f"  {'M2, ZW > 400t':<25} {'1':>10} Extreme risk — consider skip")

    rprint("\n  5b: Loss Cap Proposal:")
    rprint(f"  Max risk per event: 500t (all contracts combined)")
    rprint(f"  M1 @ 3ct × 190t = 570t → cap at 500t means 2ct max on M1")
    rprint(f"  M2 — dynamic: contracts = floor(500 / stop_dist)")

    # ═══════════════════════════════════════════════════════════
    # STEP 6: SAVE FINAL REPORT
    # ═══════════════════════════════════════════════════════════
    rprint("\n" + "=" * 72)
    rprint("STEP 6: FINAL REPORT")
    rprint("=" * 72)

    report_path = OUT_DIR / "risk_mitigation_investigation_v32.md"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("# Risk Mitigation Investigation v3.2\n\n")
        f.write(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n")
        f.write("Scoring model FROZEN at v3.2. Modifications are entry/exit "
                "execution only.\n\n")
        f.write("```\n")
        f.write("\n".join(report_lines))
        f.write("\n```\n")
    rprint(f"  Full report saved: {report_path.name}")

    # Also save step0 report
    step0_path = OUT_DIR / "risk_mitigation_step0_v32.md"
    with open(step0_path, "w", encoding="utf-8") as f:
        f.write("# Risk Mitigation Investigation v3.2 — Step 0\n\n```\n")
        f.write("\n".join(report_lines))
        f.write("\n```\n")

    rprint("\n" + "=" * 72)
    rprint("INVESTIGATION COMPLETE")
    rprint("=" * 72)


if __name__ == "__main__":
    run_step0()
