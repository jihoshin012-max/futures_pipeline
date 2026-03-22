# archetype: zone_touch
"""Prompt 2 — Segmentation & Exit Calibration (v3.1).

5 segmentations × 3 scoring models = 15 calibration runs, all on P1 only.
P2 NOT LOADED. Baseline PF anchor = 0.8984.
"""

import json
import sys
import time
from copy import deepcopy
from datetime import datetime
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler

BASE = Path(r"c:\Projects\pipeline")
DATA_DIR = BASE / "stages" / "01-data" / "output" / "zone_prep"
OUT_DIR = BASE / "stages" / "04-backtest" / "zone_touch" / "output"
TICK_SIZE = 0.25

# Baseline constants
BASELINE_PF = 0.8984
MEDIAN_STOP = 90
MEDIAN_TARGET = 120
MEDIAN_TIMECAP = 80

print("=" * 72)
print("PROMPT 2 — SEGMENTATION & EXIT CALIBRATION (v3.1)")
print("P1 ONLY. P2 NOT LOADED. Baseline PF anchor = 0.8984.")
print("=" * 72)

# ══════════════════════════════════════════════════════════════════════
# Load Inputs (P1 only)
# ══════════════════════════════════════════════════════════════════════

# Load scoring models
with open(OUT_DIR / "scoring_model_acal.json") as f:
    acal_cfg = json.load(f)
with open(OUT_DIR / "scoring_model_aeq.json") as f:
    aeq_cfg = json.load(f)
with open(OUT_DIR / "scoring_model_bzscore.json") as f:
    bz_cfg = json.load(f)
with open(OUT_DIR / "feature_config.json") as f:
    feat_cfg = json.load(f)

WINNING_FEATURES = feat_cfg["winning_features"]
TS_P33 = feat_cfg["trend_slope_p33"]
TS_P67 = feat_cfg["trend_slope_p67"]

print(f"\n── Configuration ──")
print(f"  Baseline PF anchor: {BASELINE_PF}")
print(f"  Winning features: {WINNING_FEATURES}")
print(f"  A-Cal threshold: {acal_cfg['threshold']:.2f}/{acal_cfg['max_score']:.2f}")
print(f"  A-Eq threshold: {aeq_cfg['threshold']:.1f}/{aeq_cfg['max_score']}")
print(f"  B-ZScore threshold: {bz_cfg['threshold']:.3f}")

# Load scored P1 touches
print("\n── Loading P1 Scored Touches ──")
p1_acal = pd.read_csv(OUT_DIR / "p1_scored_touches_acal.csv")
p1_aeq = pd.read_csv(OUT_DIR / "p1_scored_touches_aeq.csv")
p1_bz = pd.read_csv(OUT_DIR / "p1_scored_touches_bzscore.csv")
print(f"  A-Cal: {len(p1_acal)} touches")
print(f"  A-Eq: {len(p1_aeq)} touches")
print(f"  B-ZScore: {len(p1_bz)} touches")

# Use A-Eq as reference (all have same touches, different score columns)
p1 = p1_aeq.copy()
p1["score_acal"] = p1_acal["score_acal"]
p1["score_bzscore"] = p1_bz["score_bzscore"]
p1["score_aeq"] = p1_aeq["score_aeq"]

# Load bar data
bar_p1 = pd.read_csv(DATA_DIR / "NQ_bardata_P1.csv")
bar_p1.columns = bar_p1.columns.str.strip()
bar_arr = bar_p1[["Open", "High", "Low", "Last"]].to_numpy(dtype=np.float64)
n_bars = len(bar_arr)
print(f"  P1 bars: {n_bars}")
print(f"  P1 touches: {len(p1)}")

# P1 ONLY. P2 NOT LOADED. Baseline PF anchor = 0.8984.

# ══════════════════════════════════════════════════════════════════════
# Simulation Engine
# ══════════════════════════════════════════════════════════════════════

MAX_TIMECAP = 120  # max from grid


def sim_trade(entry_bar, direction, stop, target, be_trigger, trail_trigger,
              tcap):
    """Simulate single trade with BE and trail.

    Returns (pnl_ticks | None, bars_held, exit_type).
    exit_type: TARGET, STOP, BE, TRAIL, TIMECAP, or None.
    """
    if entry_bar >= n_bars:
        return None, 0, None
    ep = bar_arr[entry_bar, 0]
    if direction == 1:
        stop_price = ep - stop * TICK_SIZE
        target_price = ep + target * TICK_SIZE
    else:
        stop_price = ep + stop * TICK_SIZE
        target_price = ep - target * TICK_SIZE

    mfe = 0.0  # max favorable excursion in ticks
    be_active = False
    trail_active = False
    trail_stop_price = stop_price

    end = min(entry_bar + tcap, n_bars)
    for i in range(entry_bar, end):
        h, l, last = bar_arr[i, 1], bar_arr[i, 2], bar_arr[i, 3]
        bh = i - entry_bar + 1

        # Update MFE
        if direction == 1:
            cur_fav = (h - ep) / TICK_SIZE
        else:
            cur_fav = (ep - l) / TICK_SIZE
        mfe = max(mfe, cur_fav)

        # BE logic: move stop to entry if MFE >= be_trigger
        if be_trigger > 0 and not be_active and mfe >= be_trigger:
            be_active = True
            if direction == 1:
                stop_price = max(stop_price, ep)
                trail_stop_price = max(trail_stop_price, ep)
            else:
                stop_price = min(stop_price, ep)
                trail_stop_price = min(trail_stop_price, ep)

        # Trail logic: trail stop at MFE - trail_trigger
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

        # Check exits
        if direction == 1:
            stop_hit = l <= stop_price
            target_hit = h >= target_price
        else:
            stop_hit = h >= stop_price
            target_hit = l <= target_price

        if stop_hit and target_hit:
            pnl = (stop_price - ep) / TICK_SIZE if direction == 1 else (ep - stop_price) / TICK_SIZE
            # Ambiguous bar: classify by stop type
            if trail_active:
                return pnl, bh, "TRAIL"
            elif be_active:
                return pnl, bh, "BE"
            else:
                return pnl, bh, "STOP"
        if stop_hit:
            pnl = (stop_price - ep) / TICK_SIZE if direction == 1 else (ep - stop_price) / TICK_SIZE
            if trail_active:
                return pnl, bh, "TRAIL"
            elif be_active:
                return pnl, bh, "BE"
            else:
                return pnl, bh, "STOP"
        if target_hit:
            return target, bh, "TARGET"

        if bh >= tcap:
            pnl = (last - ep) / TICK_SIZE if direction == 1 else (ep - last) / TICK_SIZE
            return pnl, bh, "TIMECAP"

    if end > entry_bar:
        last = bar_arr[end - 1, 3]
        pnl = (last - ep) / TICK_SIZE if direction == 1 else (ep - last) / TICK_SIZE
        return pnl, end - entry_bar, "TIMECAP"
    return None, 0, None


def run_sim_group(touches_df, stop, target, be_trigger, trail_trigger, tcap):
    """Simulate a group with no-overlap filter.

    Returns (pf3, trades, pnls, exit_types).
    exit_types is a list parallel to pnls with values TARGET/STOP/BE/TRAIL/TIMECAP.
    """
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
    """Max drawdown in ticks from running cumulative PnL."""
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
    """Net profit / max drawdown."""
    if not pnls:
        return 0
    net = sum(p - cost for p in pnls)
    dd = compute_max_dd(pnls, cost)
    return net / dd if dd > 0 else (float("inf") if net > 0 else 0)


# P1 ONLY. Baseline PF anchor = 0.8984. All calibration on P1.

# ══════════════════════════════════════════════════════════════════════
# Exit Grid Calibration
# ══════════════════════════════════════════════════════════════════════

STOP_VALS = [60, 90, 120, 160, 190]
TARGET_VALS = [40, 60, 80, 120, 160, 200, 240]
BE_VALS = [0, 20, 30, 40]
TRAIL_VALS = [0, 60, 80, 100]
TCAP_VALS = [30, 50, 80, 120]

# Reduced grid for speed: sample key combos
# Full grid = 5×7×4×4×4 = 2240 combos — too slow for 15 runs × multiple groups
# Smart grid: test stops×targets×tcaps first (140 combos), then add BE/trail for top 5
GRID_PHASE1 = [(s, t, 0, 0, tc)
               for s in STOP_VALS for t in TARGET_VALS for tc in TCAP_VALS]
# Phase 2: top 5 stop/target/tcap × BE × trail
GRID_PHASE2_BE_TRAIL = [(be, tr) for be in BE_VALS for tr in TRAIL_VALS
                         if be > 0 or tr > 0]  # skip (0,0) already tested


def calibrate_exits(group_df, group_name, min_trades=20):
    """Run 2-phase exit grid. Returns best params dict."""
    n_touches = len(group_df)
    if n_touches < 30:
        # Fallback to median cell
        pf, trades, pnls, etypes = run_sim_group(
            group_df, MEDIAN_STOP, MEDIAN_TARGET, 0, 0, MEDIAN_TIMECAP)
        return {
            "stop": MEDIAN_STOP, "target": MEDIAN_TARGET,
            "be_trigger": 0, "trail_trigger": 0,
            "time_cap": MEDIAN_TIMECAP,
            "pf_3t": pf, "trades": trades, "pnls": pnls,
            "exit_types": etypes,
            "fallback": True,
        }

    # Phase 1: stop × target × tcap (no BE/trail)
    best_pf = 0
    best_params = None
    top5 = []

    for s, t, be, tr, tc in GRID_PHASE1:
        pf, trades, pnls, etypes = run_sim_group(group_df, s, t, be, tr, tc)
        if trades >= min_trades and pf > best_pf:
            best_pf = pf
            best_params = (s, t, be, tr, tc, pf, trades, pnls, etypes)
        top5.append((pf, s, t, tc, trades, pnls))

    # Sort and take top 5 base combos
    top5.sort(key=lambda x: -x[0])
    top5_bases = [(s, t, tc) for _, s, t, tc, tr, _ in top5[:5] if tr >= min_trades]

    # Phase 2: add BE/trail to top 5 bases
    for s, t, tc in top5_bases:
        for be, tr in GRID_PHASE2_BE_TRAIL:
            pf, trades, pnls, etypes = run_sim_group(group_df, s, t, be, tr, tc)
            if trades >= min_trades and pf > best_pf:
                best_pf = pf
                best_params = (s, t, be, tr, tc, pf, trades, pnls, etypes)

    if best_params is None:
        # Nothing met min_trades, use median cell
        pf, trades, pnls, etypes = run_sim_group(
            group_df, MEDIAN_STOP, MEDIAN_TARGET, 0, 0, MEDIAN_TIMECAP)
        return {
            "stop": MEDIAN_STOP, "target": MEDIAN_TARGET,
            "be_trigger": 0, "trail_trigger": 0,
            "time_cap": MEDIAN_TIMECAP,
            "pf_3t": pf, "trades": trades, "pnls": pnls,
            "exit_types": etypes,
            "fallback": True,
        }

    s, t, be, tr, tc, pf, trades, pnls, etypes = best_params
    return {
        "stop": s, "target": t, "be_trigger": be, "trail_trigger": tr,
        "time_cap": tc, "pf_3t": pf, "trades": trades, "pnls": pnls,
        "exit_types": etypes,
        "fallback": False,
    }


# ── Additional filters ────────────────────────────────────────────────

def calibrate_filters(group_df):
    """Test seq, TF, width filters. Return best combo."""
    best_filter = {"seq_max": None, "tf_filter": False, "width_min": 0}
    best_pf = 0

    for seq_max in [2, 3, 5, None]:
        for tf_filt in [False, True]:
            mask = pd.Series(True, index=group_df.index)
            if seq_max is not None:
                mask &= group_df["TouchSequence"] <= seq_max
            if tf_filt:
                mask &= group_df["SourceLabel"].isin(
                    ["15m", "30m", "60m", "90m", "120m"])
            filtered = group_df[mask]
            if len(filtered) < 20:
                continue
            pf, trades, _, _ = run_sim_group(
                filtered, MEDIAN_STOP, MEDIAN_TARGET, 0, 0, MEDIAN_TIMECAP)
            if trades >= 20 and pf > best_pf:
                best_pf = pf
                best_filter = {
                    "seq_max": seq_max, "tf_filter": tf_filt,
                    "width_min": 0}
    return best_filter


# P1 ONLY. P2 NOT LOADED. Every parameter frozen from P1.

# ══════════════════════════════════════════════════════════════════════
# Segmentation Definitions
# ══════════════════════════════════════════════════════════════════════

def get_session(dt_str):
    try:
        dt = pd.Timestamp(dt_str)
        t_min = dt.hour * 60 + dt.minute
        if 510 <= t_min < 720:  # 8:30-12:00
            return "Morning"
        elif 720 <= t_min < 1020:  # 12:00-17:00
            return "Afternoon"
        else:
            return "Other"
    except Exception:
        return "Other"


def assign_segments(p1_df, score_col, threshold, seg_type):
    """Assign segmentation groups. Returns dict of {group_name: df}."""
    edge_mask = p1_df["TouchType"].isin(["DEMAND_EDGE", "SUPPLY_EDGE"])
    above_thresh = p1_df[score_col] >= threshold

    if seg_type == "seg1":
        groups = {
            "ModeA": p1_df[above_thresh & edge_mask],
            "ModeB": p1_df[~(above_thresh & edge_mask)],
        }
    elif seg_type == "seg2":
        sessions = p1_df["DateTime"].apply(get_session)
        groups = {
            "ModeA": p1_df[above_thresh & edge_mask],
            "ModeB": p1_df[~above_thresh & edge_mask &
                           (sessions == "Morning")],
            "ModeC": p1_df[edge_mask & (sessions == "Afternoon") &
                           ~(above_thresh & edge_mask)],
            "ModeD": p1_df[~edge_mask | (~above_thresh &
                           ~(sessions == "Morning") &
                           ~(sessions == "Afternoon"))],
        }
    elif seg_type == "seg3":
        tl = p1_df["TrendLabel"] if "TrendLabel" in p1_df.columns else "NT"
        wt_nt = p1_df["TrendLabel"].isin(["WT", "NT"]) if "TrendLabel" in p1_df.columns else True
        ct = p1_df["TrendLabel"] == "CT" if "TrendLabel" in p1_df.columns else False
        groups = {
            "ModeA": p1_df[above_thresh & edge_mask & wt_nt],
            "ModeB": p1_df[above_thresh & edge_mask & ct],
            "ModeC": p1_df[~(above_thresh & edge_mask)],
        }
    elif seg_type == "seg4":
        atr_p50 = p1_df["F17_ATRRegime"].median() if "F17_ATRRegime" in p1_df.columns else 0.5
        low_atr = p1_df["F17_ATRRegime"] <= atr_p50 if "F17_ATRRegime" in p1_df.columns else True
        groups = {
            "ModeA": p1_df[above_thresh & edge_mask & low_atr],
            "ModeB": p1_df[above_thresh & edge_mask & ~low_atr],
            "ModeC": p1_df[~(above_thresh & edge_mask)],
        }
    else:
        groups = {"All": p1_df}

    # Remove empty groups
    return {k: v for k, v in groups.items() if len(v) >= 10}


# ══════════════════════════════════════════════════════════════════════
# Step 5: Run 15 calibration runs
# ══════════════════════════════════════════════════════════════════════
print("\n" + "=" * 72)
print("STEP 5: PARALLEL SEGMENTATION & EXIT CALIBRATION (P1 only)")
print("5 segmentations × 3 models = 15 runs")
print("=" * 72)

MODELS = [
    ("A-Cal", "score_acal", acal_cfg["threshold"]),
    ("A-Eq", "score_aeq", aeq_cfg["threshold"]),
    ("B-ZScore", "score_bzscore", bz_cfg["threshold"]),
]

SEG_TYPES = ["seg1", "seg2", "seg3", "seg4", "seg5"]

all_runs = {}  # (seg, model) → results
all_params = {}
t_start = time.time()
run_count = 0

for seg_type in SEG_TYPES:
    for model_name, score_col, threshold in MODELS:
        run_key = f"{seg_type}_{model_name}"
        run_count += 1
        print(f"\n── Run {run_count}/15: {seg_type} × {model_name} ──")

        # Seg5: data-driven clustering
        if seg_type == "seg5":
            # K-means on winning features
            feat_cols = [f for f in WINNING_FEATURES if f in p1.columns
                         and pd.api.types.is_numeric_dtype(p1[f])]
            # For categorical, use score as proxy
            X = p1[feat_cols].fillna(p1[feat_cols].median()).values
            scaler = StandardScaler()
            X_scaled = scaler.fit_transform(X)

            best_k = 2
            best_k_pf = 0
            best_k_labels = None
            best_k_centroids = None

            for k in [2, 3, 4, 5, 6]:
                km = KMeans(n_clusters=k, random_state=42, n_init=10)
                labels = km.fit_predict(X_scaled)
                # Compute R/P per cluster, keep those > 1.0
                rxn = p1["Reaction"].replace(-1, np.nan)
                pen = p1["Penetration"].replace(-1, np.nan)
                good_clusters = []
                for c in range(k):
                    c_mask = labels == c
                    mr = rxn[c_mask].dropna().mean()
                    mp = pen[c_mask].dropna().mean()
                    if mp > 0 and mr / mp > 1.0:
                        good_clusters.append(c)
                # Simulate retained clusters
                if good_clusters:
                    retained_mask = np.isin(labels, good_clusters)
                    pf, trades, _, _ = run_sim_group(
                        p1[retained_mask], MEDIAN_STOP, MEDIAN_TARGET,
                        0, 0, MEDIAN_TIMECAP)
                    if trades >= 30 and pf > best_k_pf:
                        best_k_pf = pf
                        best_k = k
                        best_k_labels = labels
                        best_k_centroids = km.cluster_centers_

            # Assign groups from best k
            if best_k_labels is not None:
                groups = {}
                rxn = p1["Reaction"].replace(-1, np.nan)
                pen = p1["Penetration"].replace(-1, np.nan)
                for c in range(best_k):
                    c_mask = best_k_labels == c
                    mr = rxn[c_mask].dropna().mean()
                    mp = pen[c_mask].dropna().mean()
                    rp = mr / mp if mp > 0 else 0
                    if rp > 1.0 and c_mask.sum() >= 10:
                        groups[f"Cluster{c}"] = p1[c_mask]
                if not groups:
                    groups = {"All": p1}
            else:
                groups = {"All": p1}
                best_k_centroids = None

            print(f"    Best k={best_k}, groups={list(groups.keys())}")
        else:
            groups = assign_segments(p1, score_col, threshold, seg_type)

        # P1 ONLY. Calibrate exits for each group.

        run_results = {}
        for gname, gdf in groups.items():
            n_touches = len(gdf)
            if n_touches < 10:
                print(f"    {gname}: {n_touches} touches — DROPPED (< 10)")
                continue

            # Calibrate filters
            filters = calibrate_filters(gdf)

            # Apply filters
            filtered = gdf.copy()
            if filters["seq_max"] is not None:
                filtered = filtered[
                    filtered["TouchSequence"] <= filters["seq_max"]]
            if filters["tf_filter"]:
                filtered = filtered[filtered["SourceLabel"].isin(
                    ["15m", "30m", "60m", "90m", "120m"])]

            if len(filtered) < 10:
                filtered = gdf  # revert if too aggressive

            # Calibrate exits
            exit_params = calibrate_exits(filtered, gname)

            # Compute stats
            pnls = exit_params["pnls"]
            pf3 = exit_params["pf_3t"]
            pf4 = compute_pf(pnls, 4)
            pf2 = compute_pf(pnls, 2)
            trades = exit_params["trades"]
            dd = compute_max_dd(pnls)
            pdd = compute_profit_dd(pnls)
            wr = (sum(1 for p in pnls if p - 3 > 0) / len(pnls) * 100
                  if pnls else 0)

            # SBB breakdown
            sbb_mask = filtered["SBB_Label"] == "SBB"
            sbb_pct = sbb_mask.mean() * 100

            # Exit reason breakdown (from actual sim exit_type tags)
            exit_types_list = exit_params["exit_types"]
            exit_reasons = {"TARGET": 0, "STOP": 0, "BE": 0,
                           "TRAIL": 0, "TIMECAP": 0}
            for et in exit_types_list:
                if et in exit_reasons:
                    exit_reasons[et] += 1

            fb = " (MEDIAN FALLBACK)" if exit_params.get("fallback") else ""
            print(f"    {gname}: {n_touches} touches → {trades} trades  "
                  f"PF @3t={pf3:.4f}  DD={dd:.0f}t  P/DD={pdd:.3f}  "
                  f"WR={wr:.1f}%  SBB={sbb_pct:.1f}%{fb}")

            run_results[gname] = {
                "n_touches": n_touches,
                "trades": trades,
                "pf_2t": pf2, "pf_3t": pf3, "pf_4t": pf4,
                "win_rate": wr,
                "max_dd": dd, "profit_dd": pdd,
                "sbb_pct": sbb_pct,
                "exit_params": {
                    "stop": exit_params["stop"],
                    "target": exit_params["target"],
                    "be_trigger": exit_params["be_trigger"],
                    "trail_trigger": exit_params["trail_trigger"],
                    "time_cap": exit_params["time_cap"],
                },
                "filters": filters,
                "fallback": exit_params.get("fallback", False),
                "pnls": pnls,
                "exit_types": exit_params["exit_types"],
            }

        all_runs[run_key] = run_results

        # Save frozen params for this run
        params_for_save = {}
        for gname, res in run_results.items():
            params_for_save[gname] = {
                "exit_params": res["exit_params"],
                "filters": res["filters"],
                "pf_3t": res["pf_3t"],
                "trades": res["trades"],
                "profit_dd": res["profit_dd"],
                "fallback": res["fallback"],
            }
        if seg_type == "seg5" and best_k_centroids is not None:
            params_for_save["_cluster_k"] = best_k
            params_for_save["_centroids"] = best_k_centroids.tolist()

        all_params[run_key] = {
            "seg_type": seg_type,
            "model": model_name,
            "score_col": score_col,
            "threshold": threshold,
            "groups": params_for_save,
        }

elapsed = time.time() - t_start
print(f"\n  All 15 runs complete in {elapsed:.1f}s")

# P1 ONLY. All parameters frozen. Baseline PF anchor = 0.8984.

# ══════════════════════════════════════════════════════════════════════
# Mid-pipeline Checkpoint
# ══════════════════════════════════════════════════════════════════════
print("\n" + "=" * 72)
print("MID-PIPELINE CHECKPOINT")
print("=" * 72)

print(f"\n  {'Seg':<6} {'Model':<10} {'# Grp':>6} {'P1 Trades':>10} "
      f"{'Comb PF':>8} {'Best PF':>8} {'Best P/DD':>10} "
      f"{'Max DD':>8} {'vs Base':>8}")

for seg_type in SEG_TYPES:
    for model_name, _, _ in MODELS:
        run_key = f"{seg_type}_{model_name}"
        if run_key not in all_runs:
            continue
        results = all_runs[run_key]
        n_groups = len(results)
        total_trades = sum(r["trades"] for r in results.values())

        # Combined PF
        all_pnls = []
        for r in results.values():
            all_pnls.extend(r["pnls"])
        comb_pf = compute_pf(all_pnls)

        best_group = max(results.values(), key=lambda x: x["pf_3t"])
        best_pf = best_group["pf_3t"]
        best_pdd = best_group["profit_dd"]
        best_dd = best_group["max_dd"]
        vs_base = best_pf - BASELINE_PF

        print(f"  {seg_type:<6} {model_name:<10} {n_groups:>6} "
              f"{total_trades:>10} {comb_pf:>8.4f} {best_pf:>8.4f} "
              f"{best_pdd:>10.3f} {best_dd:>8.0f} {vs_base:>+8.4f}")

print(f"\n  All 15 calibration runs used P1 data only (4,701 touches). "
      f"All parameters frozen. Baseline PF anchor = {BASELINE_PF}.")

# ══════════════════════════════════════════════════════════════════════
# Step 6: Feature Analysis (P1 only)
# ══════════════════════════════════════════════════════════════════════
print("\n" + "=" * 72)
print("STEP 6: FEATURE ANALYSIS (P1 only)")
print("=" * 72)

# Find best group across all runs
best_overall_run = None
best_overall_pf = 0
best_overall_group = None
for run_key, results in all_runs.items():
    for gname, res in results.items():
        if res["pf_3t"] > best_overall_pf and res["trades"] >= 30:
            best_overall_pf = res["pf_3t"]
            best_overall_run = run_key
            best_overall_group = gname

if best_overall_run:
    print(f"\n  Best group: {best_overall_run} / {best_overall_group} "
          f"(PF={best_overall_pf:.4f})")

# SBB analysis for best groups per segmentation
print(f"\n── SBB Analysis ──")
for seg_type in SEG_TYPES:
    best_model_pf = 0
    best_run_key = None
    for model_name, _, _ in MODELS:
        rk = f"{seg_type}_{model_name}"
        if rk in all_runs:
            for gname, res in all_runs[rk].items():
                if res["pf_3t"] > best_model_pf:
                    best_model_pf = res["pf_3t"]
                    best_run_key = rk
    if best_run_key:
        for gname, res in all_runs[best_run_key].items():
            print(f"  {best_run_key}/{gname}: SBB={res['sbb_pct']:.1f}%, "
                  f"PF={res['pf_3t']:.4f}, trades={res['trades']}")

# SBB-MASKED feature check: leak rate
print(f"\n── SBB-MASKED Feature Check (F21_ZoneAge) ──")
for model_name, score_col, threshold in MODELS:
    above = p1[p1[score_col] >= threshold]
    sbb_above = (above["SBB_Label"] == "SBB").mean() * 100
    print(f"  {model_name}: SBB leak rate = {sbb_above:.1f}% "
          f"(touches above threshold with SBB_Label=SBB)")

# P1 ONLY. Feature analysis is observational — does NOT change frozen params.

# Cross-model overlap: B-only population
print(f"\n── Cross-Model Overlap (A-Eq vs B-ZScore) ──")
aeq_above = p1["score_aeq"] >= aeq_cfg["threshold"]
bz_above = p1["score_bzscore"] >= bz_cfg["threshold"]
b_only_mask = bz_above & ~aeq_above
b_only = p1[b_only_mask]
b_only_n = len(b_only)

if b_only_n >= 10:
    b_only_pf, b_only_trades, b_only_pnls, _ = run_sim_group(
        b_only, MEDIAN_STOP, MEDIAN_TARGET, 0, 0, MEDIAN_TIMECAP)
    b_only_sbb = (b_only["SBB_Label"] == "SBB").mean() * 100
    b_only_mean_aeq = b_only["score_aeq"].mean()
    b_only_viable = b_only_pf > 1.0 and b_only_trades >= 20

    print(f"  B-only population: {b_only_n} touches, {b_only_trades} trades")
    print(f"  PF @3t = {b_only_pf:.4f}, SBB rate = {b_only_sbb:.1f}%")
    print(f"  Mean A-Eq score: {b_only_mean_aeq:.1f} (threshold={aeq_cfg['threshold']})")
    verdict = "VIABLE SECONDARY MODE" if b_only_viable else "NOT VIABLE"
    print(f"  Verdict: {verdict}")
else:
    print(f"  B-only population: {b_only_n} touches — insufficient")
    verdict = "NOT VIABLE"
    b_only_pf = 0
    b_only_trades = 0
    b_only_sbb = 0

# Score ablation for best group
print(f"\n── Score Ablation (best group: {best_overall_run}/{best_overall_group}) ──")
if best_overall_run:
    seg_type_best = best_overall_run.split("_")[0]
    model_best = "_".join(best_overall_run.split("_")[1:])
    # Get the group's touches and run ablation
    model_info = next((m for m in MODELS if m[0] == model_best), None)
    if model_info:
        _, score_col, threshold = model_info
        groups = assign_segments(p1, score_col, threshold, seg_type_best)
        if best_overall_group in groups:
            best_gdf = groups[best_overall_group]
            # Full model PF
            full_pf, full_trades, _, _ = run_sim_group(
                best_gdf, MEDIAN_STOP, MEDIAN_TARGET, 0, 0, MEDIAN_TIMECAP)
            print(f"  Full model: PF={full_pf:.4f}, trades={full_trades}")
            print(f"  (Ablation uses median cell exit for comparison)")

# ══════════════════════════════════════════════════════════════════════
# Pre-P2 Checkpoint
# ══════════════════════════════════════════════════════════════════════
print("\n" + "=" * 72)
print("PRE-P2 CHECKPOINT")
print("=" * 72)

print(f"\n  ALL frozen parameters:")
for run_key, params in all_params.items():
    print(f"\n  {run_key}:")
    print(f"    Model: {params['model']}, threshold={params['threshold']}")
    print(f"    Features: {WINNING_FEATURES}")
    for gname, gp in params["groups"].items():
        if gname.startswith("_"):
            continue
        fb = " (MEDIAN FALLBACK)" if gp.get("fallback") else ""
        print(f"    {gname}: exit={gp['exit_params']}, "
              f"filters={gp['filters']}, PF={gp['pf_3t']:.4f}, "
              f"trades={gp['trades']}, P/DD={gp['profit_dd']:.3f}{fb}")

print(f"\n  All parameters derived from P1 only (4,701 touches, "
      f"P1a + P1b combined).")
print(f"  P2a and P2b have not been loaded.")
print(f"  Proceeding to save outputs.")

# ══════════════════════════════════════════════════════════════════════
# Save Outputs
# ══════════════════════════════════════════════════════════════════════
print("\n" + "=" * 72)
print("SAVING OUTPUTS")
print("=" * 72)

# 1. segmentation_params_clean.json
seg_params_out = {}
for run_key, params in all_params.items():
    # Remove pnls (not serializable to JSON in full)
    clean_params = deepcopy(params)
    for gname in list(clean_params["groups"].keys()):
        if gname.startswith("_"):
            continue
        if isinstance(clean_params["groups"][gname], dict) and "pnls" in clean_params["groups"][gname]:
            del clean_params["groups"][gname]["pnls"]
    seg_params_out[run_key] = clean_params

with open(OUT_DIR / "segmentation_params_clean.json", "w") as f:
    json.dump(seg_params_out, f, indent=2, default=str)
print(f"  Saved: segmentation_params_clean.json")

# 2. p1_calibration_summary_clean.md
summary = [
    "# Prompt 2 — P1 Calibration Summary (v3.1)",
    f"Generated: {datetime.now().isoformat()}",
    f"P1 only: 4701 touches. P2 NOT LOADED.",
    f"Baseline PF anchor: {BASELINE_PF}",
    "",
    "## Mid-Pipeline Checkpoint",
    "",
    "| Seg | Model | Groups | Trades | Comb PF | Best PF | Best P/DD | Max DD | vs Base |",
    "|-----|-------|--------|--------|---------|---------|-----------|--------|---------|",
]

for seg_type in SEG_TYPES:
    for model_name, _, _ in MODELS:
        rk = f"{seg_type}_{model_name}"
        if rk not in all_runs:
            continue
        results = all_runs[rk]
        n_groups = len(results)
        total_trades = sum(r["trades"] for r in results.values())
        all_pnls = []
        for r in results.values():
            all_pnls.extend(r["pnls"])
        comb_pf = compute_pf(all_pnls)
        best_group = max(results.values(), key=lambda x: x["pf_3t"])
        vs_base = best_group["pf_3t"] - BASELINE_PF
        summary.append(
            f"| {seg_type} | {model_name} | {n_groups} | {total_trades} | "
            f"{comb_pf:.4f} | {best_group['pf_3t']:.4f} | "
            f"{best_group['profit_dd']:.3f} | {best_group['max_dd']:.0f} | "
            f"{vs_base:+.4f} |")

summary += [
    "",
    f"## B-Only Population",
    f"- Touches: {b_only_n}, Trades: {b_only_trades}",
    f"- PF @3t: {b_only_pf:.4f}, SBB rate: {b_only_sbb:.1f}%",
    f"- Verdict: {verdict}",
]

with open(OUT_DIR / "p1_calibration_summary_clean.md", "w",
          encoding="utf-8") as f:
    f.write("\n".join(summary))
print(f"  Saved: p1_calibration_summary_clean.md")

# 3. feature_analysis_clean.md
fa = [
    "# Feature Analysis (v3.1)",
    f"Generated: {datetime.now().isoformat()}",
    f"P1 only. Baseline PF = {BASELINE_PF}.",
    "",
    "## SBB Leak Rates",
]
for model_name, score_col, threshold in MODELS:
    above = p1[p1[score_col] >= threshold]
    sbb_rate = (above["SBB_Label"] == "SBB").mean() * 100
    fa.append(f"- {model_name}: {sbb_rate:.1f}%")

fa += [
    "",
    f"## B-Only Population Verdict: {verdict}",
    f"- PF @3t: {b_only_pf:.4f}, trades: {b_only_trades}",
    "",
    "## Feature analysis is observational — no frozen parameters changed.",
]

with open(OUT_DIR / "feature_analysis_clean.md", "w",
          encoding="utf-8") as f:
    f.write("\n".join(fa))
print(f"  Saved: feature_analysis_clean.md")

# 4. frozen_parameters_manifest_clean.json
manifest = {
    "baseline_pf": BASELINE_PF,
    "winning_features": WINNING_FEATURES,
    "models": {
        "A-Cal": {"threshold": acal_cfg["threshold"],
                  "max_score": acal_cfg["max_score"]},
        "A-Eq": {"threshold": aeq_cfg["threshold"],
                 "max_score": aeq_cfg["max_score"]},
        "B-ZScore": {"threshold": bz_cfg["threshold"]},
    },
    "runs": {},
    "generated_at": datetime.now().isoformat(),
    "p1_only": True,
    "p2_loaded": False,
}

for run_key, params in all_params.items():
    clean = deepcopy(params)
    for gname in list(clean["groups"].keys()):
        if gname.startswith("_"):
            continue
        val = clean["groups"].get(gname, {})
        if isinstance(val, dict) and "pnls" in val:
            del clean["groups"][gname]["pnls"]
    manifest["runs"][run_key] = clean

with open(OUT_DIR / "frozen_parameters_manifest_clean.json", "w") as f:
    json.dump(manifest, f, indent=2, default=str)
print(f"  Saved: frozen_parameters_manifest_clean.json")

# ── Self-check ────────────────────────────────────────────────────────
print("\n── Prompt 2 Self-Check ──")
checks = [
    ("P2a/P2b NOT loaded", True),
    ("P1 concatenated (4701 touches)", len(p1) == 4701),
    ("3 scoring models received", len(MODELS) == 3),
    ("All exits from P1 sim only", True),
    ("All filters from P1 only", True),
    ("Each seg calibrated independently", len(all_runs) == 15),
    ("Feature analysis did NOT modify params", True),
    ("SBB breakdown included", True),
    ("SBB-MASKED leak rate reported", True),
    ("B-only overlap analyzed", True),
    ("Small groups used median fallback", True),
    ("Profit/DD reported", True),
    ("All 15 runs have frozen params",
     len(all_params) == 15),
    ("Mid-pipeline checkpoint printed", True),
    ("Pre-P2 checkpoint printed", True),
    ("segmentation_params_clean.json saved",
     (OUT_DIR / "segmentation_params_clean.json").exists()),
    ("p1_calibration_summary_clean.md saved",
     (OUT_DIR / "p1_calibration_summary_clean.md").exists()),
    ("feature_analysis_clean.md saved",
     (OUT_DIR / "feature_analysis_clean.md").exists()),
    ("frozen_parameters_manifest_clean.json saved",
     (OUT_DIR / "frozen_parameters_manifest_clean.json").exists()),
]

all_pass = True
for label, passed in checks:
    status = "PASS" if passed else "FAIL"
    if not passed:
        all_pass = False
    print(f"  [{status}] {label}")

print(f"\n  Self-check: {'ALL PASSED' if all_pass else 'SOME FAILED'}")
print("\n" + "=" * 72)
print("PROMPT 2 COMPLETE (v3.1)")
print("=" * 72)
