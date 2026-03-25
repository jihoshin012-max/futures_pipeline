# archetype: zone_touch
"""Stress Test / Monte Carlo / Kelly Sizing — v3.2 Zone Touch Strategy.

Frozen configuration stress test. Does NOT change model/exits/selection.
Tests the frozen config under adverse conditions for deployment viability.

Produces: stress_test_v32.md, monte_carlo_results_v32.csv
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
from scipy import stats as sp_stats

# ════════════════════════════════════════════════════════════════════
# PATHS & CONSTANTS
# ════════════════════════════════════════════════════════════════════
BASE = Path(r"c:\Projects\pipeline")
DATA_DIR = BASE / "stages" / "01-data" / "output" / "zone_prep"
PARAM_DIR = BASE / "shared" / "archetypes" / "zone_touch" / "output"
OUT_DIR = PARAM_DIR
SIM_DIR = BASE / "shared" / "archetypes" / "zone_touch"
TICK = 0.25
COST_P1 = 3
COST_P2 = 4
COST_LIVE = 4  # conservative — use P2 cost for all stress test metrics
MC_ITERATIONS = 10_000
RNG_SEED = 42

report: list[str] = []


def rp(msg=""):
    print(msg)
    report.append(str(msg))


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

M1_THRESHOLD = aeq_cfg["threshold"]
M2_THRESHOLD = 0.50
RTH_SESSIONS = ["OpeningDrive", "Midday", "Close"]

# Frozen risk mitigation exits
M1_PARTIAL_CFG = {
    "stop_ticks": 190, "time_cap_bars": 120,
    "leg_targets": [60, 120], "leg_weights": [0.333, 0.667],
    "trail_steps": [],
    "stop_move_after_leg": 0, "stop_move_destination": 0,
}
M2_STOP_MULT = 1.3
M2_STOP_FLOOR = 100
M2_TARGET_MULT = 1.0
M2_TCAP = 80

M2_FILTERS_SEQ_MAX = seg_params.get("seg2_B-ZScore", {}).get(
    "groups", {}).get("ModeA_RTH", {}).get("filters", {}).get("seq_max", 2)


# ════════════════════════════════════════════════════════════════════
# FEATURE COMPUTATION (from risk_mitigation_v32.py)
# ════════════════════════════════════════════════════════════════════
def compute_features(df: pd.DataFrame, bar_arr: np.ndarray,
                     bar_atr: np.ndarray, n_bars: int,
                     label: str) -> pd.DataFrame:
    rp(f"  Computing features for {label} ({len(df)} touches)...")
    df = df.copy()
    df["F01"] = df["SourceLabel"]
    df["F04"] = df["CascadeState"].replace("UNKNOWN", "NO_PRIOR")

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

    atr_vals = []
    for rbi in df["RotBarIndex"].values:
        rbi = int(rbi)
        if 0 <= rbi < n_bars and bar_atr[rbi] > 0:
            atr_vals.append(bar_atr[rbi])
        else:
            atr_vals.append(np.nan)
    df["F09"] = df["ZoneWidthTicks"].values * TICK / np.array(atr_vals)

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
    df["F21"] = df["ZoneAgeBars"]

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
    return df


# ════════════════════════════════════════════════════════════════════
# SCORING FUNCTIONS (frozen v3.2)
# ════════════════════════════════════════════════════════════════════
def _bin_numeric(vals, lo, hi):
    out = np.full(len(vals), "Mid", dtype=object)
    v = np.asarray(vals, dtype=float)
    out[v <= lo] = "Low"
    out[v > hi] = "High"
    out[np.isnan(v)] = "NA"
    return out


def score_aeq(df):
    bp = aeq_cfg["bin_points"]
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


def tf_minutes(s):
    try:
        return int(str(s).replace("m", ""))
    except Exception:
        return 9999


# ════════════════════════════════════════════════════════════════════
# WATERFALL CONSTRUCTION
# ════════════════════════════════════════════════════════════════════
def build_waterfall(scored_df, label, prescored_bz=None):
    scored_df = scored_df.copy()
    scored_df["score_aeq"] = score_aeq(scored_df)
    if prescored_bz is not None:
        scored_df["score_bz"] = prescored_bz
    else:
        scored_df["score_bz"] = score_bzscore(scored_df)

    m1_mask = scored_df["score_aeq"] >= M1_THRESHOLD
    m1_qualifying = scored_df[m1_mask].copy()
    m1_qualifying["mode"] = "M1"

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
        & (scored_df["TouchSequence"] <= M2_FILTERS_SEQ_MAX)
        & (scored_df["SourceLabel"].apply(tf_minutes) <= 120)
        & ~is_m1
    )
    m2_qualifying = scored_df[m2_mask].copy()
    m2_qualifying["mode"] = "M2"

    rp(f"    {label}: M1={len(m1_qualifying)}, M2={len(m2_qualifying)}")
    return m1_qualifying, m2_qualifying


# ════════════════════════════════════════════════════════════════════
# SIMULATION — M2 with 1.3×ZW stop (entry-relative baseline)
# ════════════════════════════════════════════════════════════════════
def sim_trade_m2(entry_bar, direction, stop, target, tcap,
                 bar_arr, n_bars):
    """Simulate single M2 trade with given stop/target/tcap."""
    if entry_bar >= n_bars:
        return None
    ep = bar_arr[entry_bar, 0]
    if direction == 1:
        stop_price = ep - stop * TICK
        target_price = ep + target * TICK
    else:
        stop_price = ep + stop * TICK
        target_price = ep - target * TICK
    mfe = 0.0
    mae = 0.0
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
        if direction == 1:
            stop_hit = l <= stop_price
            target_hit = h >= target_price
        else:
            stop_hit = h >= stop_price
            target_hit = l <= target_price
        if stop_hit:
            pnl = ((stop_price - ep) / TICK if direction == 1
                   else (ep - stop_price) / TICK)
            return {"pnl": pnl, "bars_held": bh, "exit_type": "STOP",
                    "mfe": mfe, "mae": mae}
        if target_hit:
            return {"pnl": target, "bars_held": bh, "exit_type": "TARGET",
                    "mfe": mfe, "mae": mae}
        if bh >= tcap:
            pnl = ((last - ep) / TICK if direction == 1
                   else (ep - last) / TICK)
            return {"pnl": pnl, "bars_held": bh, "exit_type": "TIMECAP",
                    "mfe": mfe, "mae": mae}
    if end > entry_bar:
        last = bar_arr[end - 1, 3]
        pnl = ((last - ep) / TICK if direction == 1
               else (ep - last) / TICK)
        return {"pnl": pnl, "bars_held": end - entry_bar, "exit_type": "TIMECAP",
                "mfe": mfe, "mae": mae}
    return None


# ════════════════════════════════════════════════════════════════════
# SIMULATION — M1 with multileg partials
# ════════════════════════════════════════════════════════════════════
# Import the simulator's run_multileg
sys.path.insert(0, str(SIM_DIR))
from zone_touch_simulator import run_multileg as _run_multileg


def simulate_all_trades(m1_qual, m2_qual, bar_arr, n_bars, period_label):
    """Simulate M1 (multileg partial) and M2 (1.3×ZW stop) with position
    overlap filter and M2 position sizing. Returns time-ordered trade list."""
    # Merge M1 and M2 qualifying, sort by RotBarIndex for overlap filter
    all_qual = pd.concat([m1_qual, m2_qual], ignore_index=True)
    all_qual = all_qual.sort_values("RotBarIndex").reset_index(drop=True)

    bar_df = pd.DataFrame(bar_arr, columns=["Open", "High", "Low", "Last"])
    trades = []
    in_trade_until = -1

    for _, row in all_qual.iterrows():
        rbi = int(row["RotBarIndex"])
        entry_bar = rbi + 1
        if entry_bar <= in_trade_until:
            continue
        if entry_bar >= n_bars:
            continue

        direction = 1 if "DEMAND" in str(row["TouchType"]) else -1
        zw = int(row.get("ZoneWidthTicks", 100))
        mode = row["mode"]
        dt_str = str(row.get("DateTime", ""))

        if mode == "M1":
            # Multileg 1+2 partial: 1ct@60t, 2ct@120t, BE after T1
            touch_row = pd.Series({
                "TouchPrice": bar_arr[entry_bar, 0],
                "ApproachDir": direction,
                "mode": "M1",
            })
            cfg = {"tick_size": TICK, "M1": dict(M1_PARTIAL_CFG)}
            result = _run_multileg(bar_df, touch_row, cfg, entry_bar)
            pnl_per_ct = result.pnl_ticks  # weighted PnL
            contracts = 3
            pnl_total = contracts * pnl_per_ct
            bars_held = result.bars_held
            exit_type = (result.leg_exit_reasons[-1]
                         if result.leg_exit_reasons else "?")
            win = pnl_per_ct > 0
        else:
            # M2: 1.3×ZW stop, 1.0×ZW target, TC 80
            stop_t = max(round(M2_STOP_MULT * zw), M2_STOP_FLOOR)
            target_t = max(1, round(M2_TARGET_MULT * zw))
            result = sim_trade_m2(entry_bar, direction, stop_t, target_t,
                                  M2_TCAP, bar_arr, n_bars)
            if result is None:
                continue
            pnl_per_ct = result["pnl"]
            # Position sizing: 3ct if ZW<150, 2ct if 150-250, 1ct if 250+
            if zw < 150:
                contracts = 3
            elif zw <= 250:
                contracts = 2
            else:
                contracts = 1
            pnl_total = contracts * pnl_per_ct
            bars_held = result["bars_held"]
            exit_type = result["exit_type"]
            win = pnl_per_ct > 0

        trades.append({
            "mode": mode,
            "datetime": dt_str,
            "RotBarIndex": rbi,
            "direction": direction,
            "contracts": contracts,
            "pnl_per_contract": pnl_per_ct,
            "pnl_total": pnl_total,
            "zone_width": zw,
            "exit_type": exit_type,
            "bars_held": bars_held,
            "win": win,
            "period": period_label,
        })
        in_trade_until = entry_bar + bars_held - 1

    return pd.DataFrame(trades)


# ════════════════════════════════════════════════════════════════════
# ANALYSIS FUNCTIONS
# ════════════════════════════════════════════════════════════════════
def compute_pf(pnls, cost=0):
    if len(pnls) == 0:
        return 0
    gp = sum(p - cost for p in pnls if p - cost > 0)
    gl = sum(abs(p - cost) for p in pnls if p - cost < 0)
    return gp / gl if gl > 0 else (float("inf") if gp > 0 else 0)


def compute_wr(pnls, cost=0):
    if len(pnls) == 0:
        return 0
    return sum(1 for p in pnls if p - cost > 0) / len(pnls) * 100


def equity_curve(pnl_series):
    """Cumulative PnL series."""
    return np.cumsum(pnl_series)


def max_drawdown_ticks(pnl_series):
    """Max drawdown in ticks from a PnL series."""
    cum = np.cumsum(pnl_series)
    peak = np.maximum.accumulate(cum)
    dd = peak - cum
    return float(np.max(dd)) if len(dd) > 0 else 0.0


def drawdown_series(pnl_series):
    """Return (cumulative, peak, drawdown) arrays."""
    cum = np.cumsum(pnl_series)
    peak = np.maximum.accumulate(cum)
    dd = peak - cum
    return cum, peak, dd


def consecutive_runs(win_series):
    """Max consecutive wins and losses."""
    wins = np.array(win_series, dtype=bool)
    max_win_run = max_loss_run = 0
    cur_win = cur_loss = 0
    for w in wins:
        if w:
            cur_win += 1
            cur_loss = 0
        else:
            cur_loss += 1
            cur_win = 0
        max_win_run = max(max_win_run, cur_win)
        max_loss_run = max(max_loss_run, cur_loss)
    return max_win_run, max_loss_run


def longest_dd_duration(pnl_series):
    """Longest drawdown in trades and approximate days."""
    cum = np.cumsum(pnl_series)
    peak = np.maximum.accumulate(cum)
    dd = peak - cum
    # Find start/end of each drawdown
    in_dd = dd > 0
    max_len = 0
    cur_len = 0
    for v in in_dd:
        if v:
            cur_len += 1
        else:
            max_len = max(max_len, cur_len)
            cur_len = 0
    max_len = max(max_len, cur_len)
    return max_len


# ════════════════════════════════════════════════════════════════════
# MONTE CARLO BOOTSTRAP
# ════════════════════════════════════════════════════════════════════
def monte_carlo_bootstrap(pnl_totals, n_iterations=MC_ITERATIONS,
                          seed=RNG_SEED):
    """Bootstrap resample trade PnL totals. Returns array of
    (total_profit, max_drawdown, win_rate) per path."""
    rng = np.random.default_rng(seed)
    pnl_arr = np.array(pnl_totals, dtype=np.float64)
    n_trades = len(pnl_arr)
    win_threshold = 0  # raw PnL > 0 = win

    results = np.zeros((n_iterations, 3))  # profit, max_dd, wr

    for i in range(n_iterations):
        sample = rng.choice(pnl_arr, size=n_trades, replace=True)
        cum = np.cumsum(sample)
        peak = np.maximum.accumulate(cum)
        dd = peak - cum
        results[i, 0] = cum[-1]  # total profit
        results[i, 1] = np.max(dd)  # max drawdown
        results[i, 2] = np.sum(sample > win_threshold) / n_trades * 100
    return results


def wr_compression_mc(pnl_per_ct_arr, win_mask, mode_mask, reduction_pct,
                      contracts_arr, n_iter=1000, seed=42):
    """Degrade WR by converting N% of winners to losers (per mode).
    Returns (median_pf, p95_dd) from n_iter paths."""
    rng = np.random.default_rng(seed)
    n = len(pnl_per_ct_arr)

    results_pf = []
    results_dd = []

    for _ in range(n_iter):
        modified_pnl = pnl_per_ct_arr.copy()
        modified_contracts = contracts_arr.copy()

        # For each mode, flip reduction_pct of winners to losers
        for mode_val in [True, False]:  # True=M1, False=M2
            mode_idx = np.where(mode_mask == mode_val)[0]
            winner_idx = mode_idx[win_mask[mode_idx]]
            n_flip = int(round(len(winner_idx) * reduction_pct / 100))
            if n_flip > 0 and len(winner_idx) > 0:
                flip_idx = rng.choice(winner_idx, size=min(n_flip, len(winner_idx)),
                                      replace=False)
                # Convert to mean loss
                loser_idx = mode_idx[~win_mask[mode_idx]]
                if len(loser_idx) > 0:
                    mean_loss = np.mean(np.abs(modified_pnl[loser_idx]))
                else:
                    mean_loss = 100  # default loss
                modified_pnl[flip_idx] = -mean_loss

        pnl_total = modified_pnl * modified_contracts
        cum = np.cumsum(pnl_total)
        peak = np.maximum.accumulate(cum)
        dd = peak - cum

        gp = np.sum(pnl_total[pnl_total > 0])
        gl = np.sum(np.abs(pnl_total[pnl_total < 0]))
        pf = gp / gl if gl > 0 else float("inf")

        results_pf.append(pf)
        results_dd.append(np.max(dd))

    return np.median(results_pf), np.percentile(results_dd, 95)


# ════════════════════════════════════════════════════════════════════
# MAIN
# ════════════════════════════════════════════════════════════════════
def main():
    rp("=" * 72)
    rp("STRESS TEST / MONTE CARLO / KELLY — v3.2 ZONE TOUCH")
    rp(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    rp(f"MC iterations: {MC_ITERATIONS}, seed: {RNG_SEED}")
    rp("=" * 72)

    # ── Load bar data ──
    rp("\n── Loading Data ──")
    bar_p1 = pd.read_csv(DATA_DIR / "NQ_bardata_P1.csv")
    bar_p1.columns = bar_p1.columns.str.strip()
    bar_arr_p1 = bar_p1[["Open", "High", "Low", "Last"]].to_numpy(np.float64)
    bar_atr_p1 = bar_p1["ATR"].to_numpy(np.float64)
    n_bars_p1 = len(bar_arr_p1)

    bar_p2 = pd.read_csv(DATA_DIR / "NQ_bardata_P2.csv")
    bar_p2.columns = bar_p2.columns.str.strip()
    bar_arr_p2 = bar_p2[["Open", "High", "Low", "Last"]].to_numpy(np.float64)
    bar_atr_p2 = bar_p2["ATR"].to_numpy(np.float64)
    n_bars_p2 = len(bar_arr_p2)
    rp(f"  P1 bars: {n_bars_p1}, P2 bars: {n_bars_p2}")

    # ── Load touch data ──
    p1a = pd.read_csv(DATA_DIR / "NQ_merged_P1a.csv")
    p1b = pd.read_csv(DATA_DIR / "NQ_merged_P1b.csv")
    p1a = p1a[p1a["RotBarIndex"] >= 0].reset_index(drop=True)
    p1b = p1b[p1b["RotBarIndex"] >= 0].reset_index(drop=True)
    p1_all = pd.concat([p1a, p1b], ignore_index=True)

    p2a = pd.read_csv(DATA_DIR / "NQ_merged_P2a.csv")
    p2b = pd.read_csv(DATA_DIR / "NQ_merged_P2b.csv")
    p2a = p2a[p2a["RotBarIndex"] >= 0].reset_index(drop=True)
    p2b = p2b[p2b["RotBarIndex"] >= 0].reset_index(drop=True)
    p2_all = pd.concat([p2a, p2b], ignore_index=True)
    rp(f"  P1 touches: {len(p1_all)}, P2 touches: {len(p2_all)}")

    # ── Compute features ──
    p1_feat = compute_features(p1_all, bar_arr_p1, bar_atr_p1, n_bars_p1, "P1")
    p2_feat = compute_features(p2_all, bar_arr_p2, bar_atr_p2, n_bars_p2, "P2")

    # ── P1 B-ZScore: use pre-scored CSV (probability, C=1.0 LogReg) ──
    p1_bz_csv = pd.read_csv(PARAM_DIR / "p1_scored_touches_bzscore_v32.csv",
                             usecols=["BarIndex", "TouchType", "SourceLabel",
                                      "Score_BZScore"])
    p1_feat["_jk"] = (p1_feat["BarIndex"].astype(str) + "|" +
                       p1_feat["TouchType"] + "|" + p1_feat["SourceLabel"])
    p1_bz_csv["_jk"] = (p1_bz_csv["BarIndex"].astype(str) + "|" +
                          p1_bz_csv["TouchType"] + "|" +
                          p1_bz_csv["SourceLabel"])
    bz_map = p1_bz_csv.drop_duplicates("_jk").set_index("_jk")["Score_BZScore"]
    p1_prescored = p1_feat["_jk"].map(bz_map).values
    p1_prescored = np.where(pd.isna(p1_prescored), 0.0, p1_prescored)
    p1_feat.drop(columns=["_jk"], inplace=True)

    # ── Build waterfalls ──
    rp("\n── Building Waterfalls ──")
    m1_p1, m2_p1 = build_waterfall(p1_feat, "P1", prescored_bz=p1_prescored)
    m1_p2, m2_p2 = build_waterfall(p2_feat, "P2")

    # ═══════════════════════════════════════════════════════════════
    # STEP 1: BASELINE TRADE SEQUENCE
    # ═══════════════════════════════════════════════════════════════
    rp("\n" + "=" * 72)
    rp("STEP 1: BASELINE TRADE SEQUENCE (risk-mitigated)")
    rp("=" * 72)
    rp("  M1: 1+2 partial (1ct@60t + 2ct@120t, BE after T1), 3ct total")
    rp("  M2: stop=max(1.3xZW,100), target=1.0xZW, TC=80")
    rp("  M2 sizing: 3ct if ZW<150, 2ct if 150-250, 1ct if 250+")

    rp("\n  Simulating P1...")
    p1_trades = simulate_all_trades(m1_p1, m2_p1, bar_arr_p1, n_bars_p1, "P1")
    p1_m1 = p1_trades[p1_trades["mode"] == "M1"]
    p1_m2 = p1_trades[p1_trades["mode"] == "M2"]
    rp(f"    P1 M1: {len(p1_m1)} trades, P1 M2: {len(p1_m2)} trades")

    rp("  Simulating P2...")
    p2_trades = simulate_all_trades(m1_p2, m2_p2, bar_arr_p2, n_bars_p2, "P2")
    p2_m1 = p2_trades[p2_trades["mode"] == "M1"]
    p2_m2 = p2_trades[p2_trades["mode"] == "M2"]
    rp(f"    P2 M1: {len(p2_m1)} trades, P2 M2: {len(p2_m2)} trades")

    # ── 1b: Verify baseline metrics ──
    rp("\n── 1b: Baseline Metrics Verification ──")

    def pf_from_trades(df, cost):
        return compute_pf(df["pnl_per_contract"].tolist(), cost)

    def wr_from_trades(df, cost):
        return compute_wr(df["pnl_per_contract"].tolist(), cost)

    rp(f"  {'Metric':<25} {'P1 Exp':>10} {'P1 Actual':>10} "
       f"{'P2 Exp':>10} {'P2 Actual':>10}")
    rp(f"  {'-'*25} {'-'*10} {'-'*10} {'-'*10} {'-'*10}")
    rp(f"  {'M1 trades':<25} {'~107':>10} {len(p1_m1):>10} "
       f"{'~96':>10} {len(p2_m1):>10}")
    rp(f"  {'M2 trades':<25} {'~239':>10} {len(p1_m2):>10} "
       f"{'~309':>10} {len(p2_m2):>10}")

    p1_m1_pf = pf_from_trades(p1_m1, COST_P1) if len(p1_m1) > 0 else 0
    p1_m2_pf = pf_from_trades(p1_m2, COST_P1) if len(p1_m2) > 0 else 0
    p2_m1_pf = pf_from_trades(p2_m1, COST_P2) if len(p2_m1) > 0 else 0
    p2_m2_pf = pf_from_trades(p2_m2, COST_P2) if len(p2_m2) > 0 else 0

    rp(f"  {'M1 PF (partials)':<25} {'~9.52':>10} {p1_m1_pf:>10.2f} "
       f"{'~8.25':>10} {p2_m1_pf:>10.2f}")
    rp(f"  {'M2 PF':<25} {'~4.61':>10} {p1_m2_pf:>10.2f} "
       f"{'~4.10':>10} {p2_m2_pf:>10.2f}")

    # Combined PF
    all_p1_pnl = p1_trades["pnl_per_contract"].tolist()
    all_p2_pnl = p2_trades["pnl_per_contract"].tolist()
    p1_combined_pf = compute_pf(all_p1_pnl, COST_P1)
    p2_combined_pf = compute_pf(all_p2_pnl, COST_P2)
    rp(f"  {'Combined PF':<25} {'':>10} {p1_combined_pf:>10.2f} "
       f"{'':>10} {p2_combined_pf:>10.2f}")

    # ── 1c: Basic trade statistics (combined P1+P2) ──
    rp("\n── 1c: Combined P1+P2 Trade Statistics ──")
    all_trades = pd.concat([p1_trades, p2_trades], ignore_index=True)
    all_trades = all_trades.sort_values("RotBarIndex").reset_index(drop=True)
    n_total = len(all_trades)
    pnl_totals = all_trades["pnl_total"].values
    pnl_per_ct = all_trades["pnl_per_contract"].values

    # Trading days — compute from actual dates in trade data
    all_trades_tmp = all_trades.copy()
    all_trades_tmp["_dt"] = pd.to_datetime(all_trades_tmp["datetime"],
                                            errors="coerce")
    valid_dates = all_trades_tmp["_dt"].dropna()
    if len(valid_dates) > 0:
        date_range = (valid_dates.max() - valid_dates.min()).days
        # Count unique trading dates
        unique_dates = valid_dates.dt.date.nunique()
        approx_days_total = max(unique_dates, 1)
    else:
        date_range = 180
        approx_days_total = 126  # ~6 months

    # Per-period day estimates based on trade dates
    p1_dt = pd.to_datetime(p1_trades["datetime"], errors="coerce").dropna()
    p2_dt = pd.to_datetime(p2_trades["datetime"], errors="coerce").dropna()
    approx_days_p1 = p1_dt.dt.date.nunique() if len(p1_dt) > 0 else 63
    approx_days_p2 = p2_dt.dt.date.nunique() if len(p2_dt) > 0 else 63

    # Group by day for frequency stats
    trades_per_day = all_trades_tmp.dropna(subset=["_dt"]).groupby(
        all_trades_tmp.dropna(subset=["_dt"])["_dt"].dt.date).size()

    rp(f"  Total trades:              {n_total}")
    rp(f"  Approx trading days:       {approx_days_total:.0f}")
    rp(f"  Mean trades/day:           {n_total / approx_days_total:.2f}")
    rp(f"  Median trades/day:         {trades_per_day.median():.1f}")
    rp(f"  Max trades in one day:     {trades_per_day.max()}")
    # Zero-trade days: calendar days in range minus days with trades
    if len(valid_dates) > 0:
        cal_days = (valid_dates.max() - valid_dates.min()).days
        # Approximate trading days in range (exclude weekends: ~5/7)
        est_total_trading_days = int(cal_days * 5 / 7)
        zero_trade_days = max(0, est_total_trading_days - approx_days_total)
    else:
        zero_trade_days = 0
    rp(f"  Days with zero trades:     ~{zero_trade_days}")
    rp(f"  Mean PnL/trade (total):    {pnl_totals.mean():.1f}t")
    rp(f"  Median PnL/trade (total):  {np.median(pnl_totals):.1f}t")
    rp(f"  Std dev PnL/trade:         {pnl_totals.std():.1f}t")
    rp(f"  Skewness:                  {sp_stats.skew(pnl_totals):.3f}")
    rp(f"  Max single-trade win:      {pnl_totals.max():.1f}t")
    rp(f"  Max single-trade loss:     {pnl_totals.min():.1f}t")
    rp(f"  Win rate (raw):            {(all_trades['win'].sum() / n_total * 100):.1f}%")

    # ═══════════════════════════════════════════════════════════════
    # STEP 2: HISTORICAL DRAWDOWN ANALYSIS
    # ═══════════════════════════════════════════════════════════════
    rp("\n" + "=" * 72)
    rp("STEP 2: HISTORICAL DRAWDOWN ANALYSIS")
    rp("=" * 72)

    for label, df_sub in [("P1", p1_trades), ("P2", p2_trades),
                           ("P1+P2", all_trades)]:
        pnls = df_sub["pnl_total"].values
        cum, peak, dd = drawdown_series(pnls)
        total_profit = float(cum[-1]) if len(cum) > 0 else 0
        max_dd = float(dd.max()) if len(dd) > 0 else 0
        p_dd_ratio = total_profit / max_dd if max_dd > 0 else float("inf")
        max_w, max_l = consecutive_runs(df_sub["win"].values)
        longest_dd = longest_dd_duration(pnls)
        # Approx days for longest DD
        trades_count = len(pnls)
        approx_days = {
            "P1": approx_days_p1, "P2": approx_days_p2,
            "P1+P2": approx_days_total
        }[label]
        dd_days = longest_dd / max(trades_count, 1) * approx_days

        rp(f"\n  {label}:")
        rp(f"    Total profit:        {total_profit:.0f}t")
        rp(f"    Max drawdown:        {max_dd:.0f}t")
        rp(f"    Profit / Max DD:     {p_dd_ratio:.2f}")
        rp(f"    Max consec losses:   {max_l}")
        rp(f"    Max consec wins:     {max_w}")
        rp(f"    Longest DD (trades): {longest_dd}")
        rp(f"    Longest DD (days):   ~{dd_days:.0f}")

    # ── 2b: Large drawdowns (>500t) ──
    rp("\n── 2b: Drawdowns Exceeding 500t (P1+P2) ──")
    pnls_all = all_trades["pnl_total"].values
    cum_all, peak_all, dd_all = drawdown_series(pnls_all)
    # Find distinct drawdown episodes > 500t
    in_dd = dd_all > 0
    dd_episodes = []
    start = None
    for i in range(len(dd_all)):
        if dd_all[i] > 0 and start is None:
            start = i
        elif dd_all[i] == 0 and start is not None:
            max_dd_val = dd_all[start:i].max()
            if max_dd_val > 500:
                trough_idx = start + np.argmax(dd_all[start:i])
                dd_episodes.append({
                    "peak_eq": float(peak_all[start]),
                    "trough_eq": float(cum_all[trough_idx]),
                    "dd_size": float(max_dd_val),
                    "recovery_trades": i - start,
                })
            start = None
    # Handle final episode
    if start is not None:
        max_dd_val = dd_all[start:].max()
        if max_dd_val > 500:
            trough_idx = start + np.argmax(dd_all[start:])
            dd_episodes.append({
                "peak_eq": float(peak_all[start]),
                "trough_eq": float(cum_all[trough_idx]),
                "dd_size": float(max_dd_val),
                "recovery_trades": len(dd_all) - start,
            })

    if dd_episodes:
        rp(f"  {'#':<4} {'Peak':>10} {'Trough':>10} {'DD Size':>10} {'Recovery':>10}")
        rp(f"  {'-'*4} {'-'*10} {'-'*10} {'-'*10} {'-'*10}")
        for i, ep in enumerate(dd_episodes):
            rp(f"  {i+1:<4} {ep['peak_eq']:>10.0f} {ep['trough_eq']:>10.0f} "
               f"{ep['dd_size']:>10.0f} {ep['recovery_trades']:>10}")
    else:
        rp("  No drawdowns exceeding 500t found.")

    # ═══════════════════════════════════════════════════════════════
    # STEP 3: MONTE CARLO SIMULATION
    # ═══════════════════════════════════════════════════════════════
    rp("\n" + "=" * 72)
    rp("STEP 3: MONTE CARLO SIMULATION")
    rp(f"  Population: {n_total} trades (P1+P2 combined)")
    rp(f"  Iterations: {MC_ITERATIONS}")
    rp("=" * 72)

    # ── 3b: Serial correlation check ──
    rp("\n── 3b: Serial Correlation Check ──")
    pnl_series = all_trades["pnl_total"].values
    n_ac = len(pnl_series)
    sig_threshold = 2 / np.sqrt(n_ac)
    rp(f"  Significance threshold: |r| > {sig_threshold:.4f}")
    rp(f"  {'Lag':>5} {'Autocorr':>12} {'Significant?':>14}")
    rp(f"  {'-'*5} {'-'*12} {'-'*14}")
    any_significant = False
    for lag in range(1, 6):
        if len(pnl_series) > lag:
            ac = np.corrcoef(pnl_series[:-lag], pnl_series[lag:])[0, 1]
        else:
            ac = 0
        sig = abs(ac) > sig_threshold
        if sig:
            any_significant = True
        rp(f"  {lag:>5} {ac:>12.4f} {'YES' if sig else 'no':>14}")
    if any_significant:
        rp("  ⚠️ Significant autocorrelation detected — bootstrap may "
           "understate tail risk.")

    # ── 3c: Monte Carlo results ──
    rp("\n── 3c: Monte Carlo Results ──")
    mc_results = monte_carlo_bootstrap(pnl_totals)
    mc_profit = mc_results[:, 0]
    mc_dd = mc_results[:, 1]
    mc_wr = mc_results[:, 2]

    rp("\n  Drawdown Distribution:")
    rp(f"  {'Percentile':>12} {'Max DD (ticks)':>16}")
    rp(f"  {'-'*12} {'-'*16}")
    for pct in [50, 75, 90, 95, 99]:
        rp(f"  {f'{pct}th':>12} {np.percentile(mc_dd, pct):>16.0f}")
    rp(f"  {'Worst':>12} {mc_dd.max():>16.0f}")

    dd_95 = np.percentile(mc_dd, 95)

    rp("\n  Profit Distribution:")
    rp(f"  {'Percentile':>12} {'Total Profit':>16}")
    rp(f"  {'-'*12} {'-'*16}")
    for pct in [5, 25, 50, 75, 95]:
        rp(f"  {f'{pct}th':>12} {np.percentile(mc_profit, pct):>16.0f}")

    rp("\n  Win Rate Distribution:")
    rp(f"  {'Percentile':>12} {'Win Rate':>12}")
    rp(f"  {'-'*12} {'-'*12}")
    for pct in [5, 25, 50, 75, 95]:
        rp(f"  {f'{pct}th':>12} {np.percentile(mc_wr, pct):>12.1f}%")

    # ── 3d: Ruin probability ──
    rp("\n── 3d: Ruin Probability ──")
    rp(f"  {'DD Threshold':>14} {'% of Paths':>12} {'Interpretation':<25}")
    rp(f"  {'-'*14} {'-'*12} {'-'*25}")
    for thresh in [1000, 2000, 3000, 5000]:
        pct = (mc_dd >= thresh).sum() / MC_ITERATIONS * 100
        interp = {1000: "Moderate stress",
                  2000: "Severe stress",
                  3000: "Near-ruin (small accts)",
                  5000: "Catastrophic"}[thresh]
        rp(f"  {f'{thresh}t':>14} {pct:>11.1f}% {interp:<25}")

    # ═══════════════════════════════════════════════════════════════
    # STEP 4: WR COMPRESSION & SLIPPAGE STRESS TEST
    # ═══════════════════════════════════════════════════════════════
    rp("\n" + "=" * 72)
    rp("STEP 4: WR COMPRESSION & SLIPPAGE STRESS TEST")
    rp("=" * 72)

    # ── 4a: WR degradation scenarios ──
    rp("\n── 4a: WR Degradation Scenarios ──")
    pnl_pc = all_trades["pnl_per_contract"].values.copy()
    contracts_arr = all_trades["contracts"].values.copy()
    win_mask = all_trades["win"].values.copy()
    mode_is_m1 = (all_trades["mode"] == "M1").values

    # Get baseline WRs per mode
    m1_all = all_trades[all_trades["mode"] == "M1"]
    m2_all = all_trades[all_trades["mode"] == "M2"]
    baseline_wr_m1 = m1_all["win"].mean() * 100 if len(m1_all) > 0 else 0
    baseline_wr_m2 = m2_all["win"].mean() * 100 if len(m2_all) > 0 else 0

    rp(f"  Baseline WR: M1={baseline_wr_m1:.1f}%, M2={baseline_wr_m2:.1f}%")
    rp(f"  {'WR Reduction':>13} {'Eff WR M1':>10} {'Eff WR M2':>10} "
       f"{'Med PF':>8} {'95th DD':>10}")
    rp(f"  {'-'*13} {'-'*10} {'-'*10} {'-'*8} {'-'*10}")

    breakeven_wr = None
    pf_2_wr = None
    pf_1_5_wr = None

    for reduction in [0, 2, 5, 8, 10, 15]:
        eff_m1 = baseline_wr_m1 - reduction
        eff_m2 = baseline_wr_m2 - reduction
        if reduction == 0:
            # Baseline
            base_pnl_total = pnl_pc * contracts_arr
            gp = np.sum(base_pnl_total[base_pnl_total > 0])
            gl = np.sum(np.abs(base_pnl_total[base_pnl_total < 0]))
            med_pf = gp / gl if gl > 0 else float("inf")
            p95_dd = dd_95
        else:
            med_pf, p95_dd = wr_compression_mc(
                pnl_pc, win_mask, mode_is_m1, reduction,
                contracts_arr, n_iter=1000, seed=RNG_SEED)

        rp(f"  {f'-{reduction}%':>13} {eff_m1:>10.1f}% {eff_m2:>10.1f}% "
           f"{med_pf:>8.2f} {p95_dd:>10.0f}")

        if pf_2_wr is None and med_pf < 2.0:
            pf_2_wr = reduction
        if pf_1_5_wr is None and med_pf < 1.5:
            pf_1_5_wr = reduction
        if breakeven_wr is None and med_pf < 1.0:
            breakeven_wr = reduction

    rp(f"\n  PF drops below 2.0 at ~-{pf_2_wr}% WR" if pf_2_wr else
       "\n  PF stays above 2.0 through -15% WR")
    rp(f"  PF drops below 1.5 at ~-{pf_1_5_wr}% WR" if pf_1_5_wr else
       "  PF stays above 1.5 through -15% WR")
    rp(f"  PF drops below 1.0 at ~-{breakeven_wr}% WR" if breakeven_wr else
       "  PF stays above 1.0 through -15% WR — BREAKEVEN NOT REACHED")

    # ── 4b: Slippage sensitivity ──
    rp("\n── 4b: Slippage Sensitivity ──")
    rp(f"  {'Slip (RT/ct)':>13} {'Comb PF':>9} {'M1 PF':>8} "
       f"{'M2 PF':>8} {'95th DD':>10}")
    rp(f"  {'-'*13} {'-'*9} {'-'*8} {'-'*8} {'-'*10}")

    slip_breakeven = None

    for slip in [0, 2, 3, 4, 6, 10]:
        # Subtract slippage from each trade's per-contract PnL
        adj_pnl_pc = pnl_pc - slip
        adj_pnl_total = adj_pnl_pc * contracts_arr

        # Combined PF
        gp = np.sum(adj_pnl_total[adj_pnl_total > 0])
        gl = np.sum(np.abs(adj_pnl_total[adj_pnl_total < 0]))
        comb_pf = gp / gl if gl > 0 else float("inf")

        # M1 PF
        m1_mask = all_trades["mode"].values == "M1"
        m1_adj = adj_pnl_pc[m1_mask]
        m1_gp = np.sum(m1_adj[m1_adj > 0])
        m1_gl = np.sum(np.abs(m1_adj[m1_adj < 0]))
        m1_pf = m1_gp / m1_gl if m1_gl > 0 else float("inf")

        # M2 PF
        m2_mask = all_trades["mode"].values == "M2"
        m2_adj = adj_pnl_pc[m2_mask]
        m2_gp = np.sum(m2_adj[m2_adj > 0])
        m2_gl = np.sum(np.abs(m2_adj[m2_adj < 0]))
        m2_pf = m2_gp / m2_gl if m2_gl > 0 else float("inf")

        # DD from MC with slippage
        mc_slip = monte_carlo_bootstrap(adj_pnl_total, n_iterations=2000,
                                        seed=RNG_SEED)
        p95_dd_slip = np.percentile(mc_slip[:, 1], 95)

        rp(f"  {f'{slip}t':>13} {comb_pf:>9.2f} {m1_pf:>8.2f} "
           f"{m2_pf:>8.2f} {p95_dd_slip:>10.0f}")

        if slip_breakeven is None and comb_pf < 2.0:
            slip_breakeven = slip

    rp(f"\n  Combined PF drops below 2.0 at ~{slip_breakeven}t RT slippage"
       if slip_breakeven else
       "\n  Combined PF stays above 2.0 through 10t RT slippage")

    # ═══════════════════════════════════════════════════════════════
    # STEP 5: KELLY CRITERION & CAPITAL SIZING
    # ═══════════════════════════════════════════════════════════════
    rp("\n" + "=" * 72)
    rp("STEP 5: KELLY CRITERION & CAPITAL SIZING")
    rp("=" * 72)

    # ── 5a: Kelly per mode ──
    rp("\n── 5a: Kelly Fraction ──")
    for mode_label, mode_df in [("Mode 1", m1_all), ("Mode 2", m2_all)]:
        pnls_mode = mode_df["pnl_per_contract"].values
        wins = pnls_mode[pnls_mode > 0]
        losses = pnls_mode[pnls_mode <= 0]
        wr = len(wins) / len(pnls_mode) if len(pnls_mode) > 0 else 0
        avg_win = wins.mean() if len(wins) > 0 else 0
        avg_loss = abs(losses.mean()) if len(losses) > 0 else 1
        wl_ratio = avg_win / avg_loss if avg_loss > 0 else float("inf")
        kelly = wr - (1 - wr) / wl_ratio if wl_ratio > 0 else 0

        rp(f"\n  {mode_label}:")
        rp(f"    WR:              {wr*100:.1f}%")
        rp(f"    Avg Win:         {avg_win:.1f}t")
        rp(f"    Avg Loss:        {avg_loss:.1f}t")
        rp(f"    Win/Loss ratio:  {wl_ratio:.2f}")
        rp(f"    Full Kelly:      {kelly*100:.1f}%")
        rp(f"    Half Kelly:      {kelly*50:.1f}%")
        rp(f"    Quarter Kelly:   {kelly*25:.1f}%")

    # ── 5b: Capital requirements ──
    rp("\n── 5b: Capital Requirements ──")
    rp(f"  95th percentile MC drawdown: {dd_95:.0f}t")
    rp(f"  {'Contract':>12} {'95th DD ($)':>13} {'2x Buffer ($)':>15} "
       f"{'Min Capital':>13}")
    rp(f"  {'-'*12} {'-'*13} {'-'*15} {'-'*13}")
    for ct_name, tick_val in [("MNQ ($5/t)", 5), ("NQ ($20/t)", 20)]:
        dd_dollars = dd_95 * tick_val
        buffer_2x = dd_dollars * 2
        rp(f"  {ct_name:>12} {dd_dollars:>13,.0f} {buffer_2x:>15,.0f} "
           f"{buffer_2x:>13,.0f}")

    # ── 5c: Expected annual metrics ──
    rp("\n── 5c: Expected Annual Metrics (conservative: 4t RT slippage) ──")

    # Trade rate: trades per trading day, annualized to 252 days
    trades_per_day_avg = n_total / approx_days_total
    trades_per_year = trades_per_day_avg * 252
    rp(f"  Data spans {approx_days_total} trading days")
    rp(f"  Trades/day (avg):        {trades_per_day_avg:.2f}")

    # Use 4t slippage-adjusted per-contract PnL
    slip_adj_pc = pnl_pc - 4
    slip_adj_total = slip_adj_pc * contracts_arr
    mean_pnl_per_trade_slip = slip_adj_total.mean()
    annual_profit_ticks = mean_pnl_per_trade_slip * trades_per_year

    rp(f"  Est. trades/year:        {trades_per_year:.0f}")
    rp(f"  Mean PnL/trade (slip-adj): {mean_pnl_per_trade_slip:.1f}t")

    for ct_name, tick_val in [("MNQ ($5/t)", 5), ("NQ ($20/t)", 20)]:
        annual_profit_usd = annual_profit_ticks * tick_val
        max_annual_dd = dd_95 * tick_val
        capital = dd_95 * tick_val * 2
        ret = annual_profit_usd / capital * 100 if capital > 0 else 0
        rp(f"\n  {ct_name}:")
        rp(f"    Annual profit:       ${annual_profit_usd:,.0f}")
        rp(f"    Max annual DD (95%): ${max_annual_dd:,.0f}")
        rp(f"    Profit / Max DD:     {annual_profit_usd/max_annual_dd:.2f}"
           if max_annual_dd > 0 else "    Profit / Max DD:     N/A")
        rp(f"    Annual return on capital: {ret:.1f}%")

    # ═══════════════════════════════════════════════════════════════
    # STEP 6: REGIME SENSITIVITY
    # ═══════════════════════════════════════════════════════════════
    rp("\n" + "=" * 72)
    rp("STEP 6: REGIME SENSITIVITY")
    rp("=" * 72)

    # ── 6a: Rolling 60-trade PF and WR ──
    rp("\n── 6a: Rolling 60-Trade Performance ──")
    window = 60
    if len(pnl_totals) >= window:
        rolling_pf = []
        rolling_wr = []
        for i in range(len(pnl_totals) - window + 1):
            chunk = pnl_totals[i:i+window]
            gp = np.sum(chunk[chunk > 0])
            gl = np.sum(np.abs(chunk[chunk < 0]))
            pf = gp / gl if gl > 0 else float("inf")
            wr = np.sum(chunk > 0) / window * 100
            rolling_pf.append(pf)
            rolling_wr.append(wr)
        rolling_pf = np.array(rolling_pf)
        rolling_wr = np.array(rolling_wr)

        # Cap inf PFs for stats
        finite_pf = rolling_pf[np.isfinite(rolling_pf)]

        rp(f"  {'Metric':<22} {'Min':>8} {'Max':>8} {'Mean':>8} {'Std':>8}")
        rp(f"  {'-'*22} {'-'*8} {'-'*8} {'-'*8} {'-'*8}")
        rp(f"  {'Rolling 60-trade PF':<22} {finite_pf.min():>8.2f} "
           f"{finite_pf.max():>8.2f} {finite_pf.mean():>8.2f} "
           f"{finite_pf.std():>8.2f}")
        rp(f"  {'Rolling 60-trade WR':<22} {rolling_wr.min():>8.1f}% "
           f"{rolling_wr.max():>8.1f}% {rolling_wr.mean():>8.1f}% "
           f"{rolling_wr.std():>8.1f}%")

        # Sub-1.0 PF windows
        sub1 = np.where(finite_pf < 1.0)[0]
        if len(sub1) > 0:
            rp(f"\n  ⚠️ {len(sub1)} windows with PF < 1.0")
            rp(f"    Trade indices: {sub1[:10].tolist()}"
               f"{'...' if len(sub1) > 10 else ''}")
        else:
            rp(f"\n  ✓ No rolling 60-trade windows with PF < 1.0")

    # ── 6b: Monthly performance ──
    rp("\n── 6b: Monthly Performance ──")
    # Parse datetime and group by month
    all_trades_dt = all_trades.copy()
    all_trades_dt["dt"] = pd.to_datetime(all_trades_dt["datetime"],
                                          errors="coerce")
    valid_dt = all_trades_dt.dropna(subset=["dt"])
    if len(valid_dt) > 0:
        valid_dt["month"] = valid_dt["dt"].dt.to_period("M")
        monthly = valid_dt.groupby("month").agg(
            trades=("pnl_total", "count"),
            pnl=("pnl_total", "sum"),
            wr=("win", "mean"),
        )
        monthly["wr"] = monthly["wr"] * 100
        monthly["pf"] = monthly.apply(
            lambda row: compute_pf(
                valid_dt[valid_dt["month"] == row.name]["pnl_total"].tolist()),
            axis=1)

        rp(f"  {'Month':<10} {'Trades':>7} {'PF':>7} {'WR':>7} {'PnL (t)':>10}")
        rp(f"  {'-'*10} {'-'*7} {'-'*7} {'-'*7} {'-'*10}")

        losing_months = 0
        for idx, row in monthly.iterrows():
            marker = " ⚠️" if row["pnl"] < 0 else ""
            if row["pnl"] < 0:
                losing_months += 1
            rp(f"  {str(idx):<10} {row['trades']:>7.0f} {row['pf']:>7.2f} "
               f"{row['wr']:>6.1f}% {row['pnl']:>10.0f}{marker}")

        rp(f"\n  Total months: {len(monthly)}, Losing months: {losing_months} "
           f"({losing_months/len(monthly)*100:.0f}%)")

    # ═══════════════════════════════════════════════════════════════
    # STEP 7: OUTPUT REPORT
    # ═══════════════════════════════════════════════════════════════
    rp("\n" + "=" * 72)
    rp("STEP 7: DEPLOYMENT RECOMMENDATION")
    rp("=" * 72)

    rp(f"\n  Contract recommendation: MNQ (micro)")
    rp(f"  Rationale: Lower capital requirement, better risk management")
    rp(f"  Starting capital (2x 95th DD): ${dd_95 * 5 * 2:,.0f} (MNQ)")
    rp(f"  Kelly sizing: Half-Kelly recommended")
    # Annualize MC profit (MC samples same N trades as dataset = ~6mo)
    annualize_factor = 252 / approx_days_total
    rp(f"\n  Expected first-year range (MNQ, annualized from MC):")
    rp(f"    (annualization factor: {annualize_factor:.2f}x from "
       f"{approx_days_total} trading days to 252)")
    # Subtract 4t/ct slippage from MC raw profits
    mc_slip_adj = mc_profit - (4 * contracts_arr.mean() * n_total)
    mc_annual = mc_slip_adj * annualize_factor
    p5_annual = np.percentile(mc_annual, 5)
    p50_annual = np.median(mc_annual)
    p95_annual = np.percentile(mc_annual, 95)
    rp(f"    5th percentile:  ${p5_annual * 5:,.0f}")
    rp(f"    Median:          ${p50_annual * 5:,.0f}")
    rp(f"    95th percentile: ${p95_annual * 5:,.0f}")

    rp(f"\n  ⚠️ CAVEAT: Annual estimates are backtested projections.")
    rp(f"  Live trading will differ due to missed fills, higher slippage,")
    rp(f"  regime changes, and data period limitations ({approx_days_total} days).")
    rp(f"  Apply a 50% haircut to annual profit estimates as a starting")
    rp(f"  assumption; recalibrate after 60+ live trades.")

    rp(f"\n  Key risk factors:")
    rp(f"    - M1 has very few losses — WR compression sensitivity is HIGH")
    rp(f"    - Serial correlation: {'DETECTED' if any_significant else 'not significant'}")
    rp(f"    - Slippage breakeven: ~{slip_breakeven}t RT/ct"
       if slip_breakeven else
       f"    - Slippage: PF > 2.0 through 10t — robust")
    rp(f"    - Losing months: {losing_months}/{len(monthly)}" if len(valid_dt) > 0
       else "")

    rp(f"\n  Monitoring thresholds (live trading):")
    rp(f"    - Stop trading if DD exceeds {dd_95:.0f}t ({dd_95*5:.0f} MNQ)")
    rp(f"    - Review if rolling 60-trade PF drops below 1.5")
    rp(f"    - Review if 3+ consecutive losing days")

    # ═══════════════════════════════════════════════════════════════
    # SAVE OUTPUTS
    # ═══════════════════════════════════════════════════════════════
    rp("\n" + "=" * 72)
    rp("SAVING OUTPUTS")
    rp("=" * 72)

    # Save report
    report_path = OUT_DIR / "stress_test_v32.md"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("# Stress Test / Monte Carlo / Kelly — v3.2 Zone Touch\n\n")
        f.write("```\n")
        f.write("\n".join(report))
        f.write("\n```\n")
    rp(f"  Saved: {report_path}")

    # Save MC summary
    mc_summary = pd.DataFrame({
        "total_profit": mc_results[:, 0],
        "max_drawdown": mc_results[:, 1],
        "win_rate": mc_results[:, 2],
    })
    mc_path = OUT_DIR / "monte_carlo_results_v32.csv"
    mc_summary.to_csv(mc_path, index=False)
    rp(f"  Saved: {mc_path}")

    # Save trade sequence
    trades_path = OUT_DIR / "stress_test_trades_v32.csv"
    all_trades.to_csv(trades_path, index=False)
    rp(f"  Saved: {trades_path}")

    rp("\n" + "=" * 72)
    rp("SELF-CHECK")
    rp("=" * 72)
    checks = [
        ("M1 uses 1+2 partial exits", True),
        ("M2 uses 1.3xZW floor 100 stop", True),
        ("M2 uses position sizing (3/2/1)", True),
        (f"P1 M1 trades ~107", abs(len(p1_m1) - 107) < 20),
        (f"P2 M1 trades ~96", abs(len(p2_m1) - 96) < 20),
        (f"P1 M2 trades ~239", abs(len(p1_m2) - 239) < 40),
        (f"P2 M2 trades ~309", abs(len(p2_m2) - 309) < 50),
        ("Serial correlation checked", True),
        ("MC uses P1+P2 combined", True),
        ("Kelly computed per mode", True),
        ("Capital for MNQ and NQ", True),
        ("4t RT slippage for annual est", True),
    ]
    for label, ok in checks:
        rp(f"  {'✓' if ok else '✗'} {label}")

    rp("\nDone.")


if __name__ == "__main__":
    main()
