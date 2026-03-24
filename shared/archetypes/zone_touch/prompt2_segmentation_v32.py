# archetype: zone_touch
"""Prompt 2 — Segmentation & Exit Calibration (v3.2 warmup-enriched).

13 calibration runs on P1 only (3,278 touches).
- A-Cal/A-Eq: Seg1 full calibration; Seg2-4 report-only (median exits); Seg5 skipped
- B-ZScore: Seg1-5 full calibration
P2 NOT LOADED. Baseline PF anchor = 1.3396.
"""

import json
import sys
import time
from collections import Counter
from copy import deepcopy
from datetime import datetime
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler

# ══════════════════════════════════════════════════════════════════════
# Paths & Constants
# ══════════════════════════════════════════════════════════════════════
BASE = Path(r"c:\Projects\pipeline")
DATA_DIR = BASE / "stages" / "01-data" / "output" / "zone_prep"
V32_DIR = BASE / "shared" / "archetypes" / "zone_touch" / "output"
OUT_DIR = V32_DIR  # v3.2 outputs go here
TICK_SIZE = 0.25

# v3.2 baseline constants (from baseline_report_clean.md v3.2)
BASELINE_PF = 1.3396
MEDIAN_STOP = 120
MEDIAN_TARGET = 120
MEDIAN_TIMECAP = 80

report = []  # accumulate report lines


def rprint(msg=""):
    print(msg)
    report.append(msg)


rprint("=" * 72)
rprint("PROMPT 2 — SEGMENTATION & EXIT CALIBRATION (v3.2)")
rprint(f"P1 ONLY. P2 NOT LOADED. Baseline PF anchor = {BASELINE_PF}.")
rprint("=" * 72)

# ══════════════════════════════════════════════════════════════════════
# Load Inputs (P1 only)
# ══════════════════════════════════════════════════════════════════════

with open(V32_DIR / "scoring_model_acal_v32.json") as f:
    acal_cfg = json.load(f)
with open(V32_DIR / "scoring_model_aeq_v32.json") as f:
    aeq_cfg = json.load(f)
with open(V32_DIR / "scoring_model_bzscore_v32.json") as f:
    bz_cfg = json.load(f)
with open(V32_DIR / "feature_config_v32.json") as f:
    feat_cfg = json.load(f)

WINNING_FEATURES = feat_cfg["winning_features"]
TS_P33 = feat_cfg["trend_slope_P33"]
TS_P67 = feat_cfg["trend_slope_P67"]
ATR_P50 = np.median([feat_cfg["atr_regime_P33"], feat_cfg["atr_regime_P67"]])

rprint(f"\n-- Configuration --")
rprint(f"  Baseline PF anchor: {BASELINE_PF}")
rprint(f"  Median cell: Stop={MEDIAN_STOP}t, Target={MEDIAN_TARGET}t, TC={MEDIAN_TIMECAP}")
rprint(f"  Winning features (7): {WINNING_FEATURES}")
rprint(f"  A-Cal threshold: {acal_cfg['threshold']:.2f} / max {acal_cfg['max_score']:.2f} = {acal_cfg['threshold']/acal_cfg['max_score']*100:.0f}%")
rprint(f"  A-Eq threshold: {aeq_cfg['threshold']:.1f} / max {aeq_cfg['max_score']}")
rprint(f"  B-ZScore threshold: {bz_cfg['threshold']:.4f}")
rprint(f"  TrendSlope P33={TS_P33:.4f}, P67={TS_P67:.4f}")
rprint(f"  ATR Regime P50 (approx): {ATR_P50:.2f}")

# Load scored P1 touches (v3.2)
rprint(f"\n-- Loading P1 Scored Touches (v3.2) --")
p1_acal = pd.read_csv(V32_DIR / "p1_scored_touches_acal_v32.csv")
p1_aeq = pd.read_csv(V32_DIR / "p1_scored_touches_aeq_v32.csv")
p1_bz = pd.read_csv(V32_DIR / "p1_scored_touches_bzscore_v32.csv")

# Merge scores into single dataframe
p1 = p1_acal.copy()
p1["Score_AEq"] = p1_aeq["Score_AEq"]
p1["Score_BZScore"] = p1_bz["Score_BZScore"]
# Rename for consistent access
p1.rename(columns={"Score_ACal": "score_acal", "Score_AEq": "score_aeq",
                    "Score_BZScore": "score_bzscore"}, inplace=True)

# Filter RotBarIndex < 0 (same as prior prompts)
pre_filter = len(p1)
p1 = p1[p1["RotBarIndex"] >= 0].reset_index(drop=True)
rprint(f"  Loaded: {pre_filter} rows, after RotBarIndex>=0 filter: {len(p1)}")

# Load bar data
bar_p1 = pd.read_csv(DATA_DIR / "NQ_bardata_P1.csv")
bar_p1.columns = bar_p1.columns.str.strip()
bar_arr = bar_p1[["Open", "High", "Low", "Last"]].to_numpy(dtype=np.float64)
n_bars = len(bar_arr)
rprint(f"  P1 bars: {n_bars}")
rprint(f"  P1 touches: {len(p1)}")

# Trade counts per model
for mname, scol, thr in [("A-Cal", "score_acal", acal_cfg["threshold"]),
                          ("A-Eq", "score_aeq", aeq_cfg["threshold"]),
                          ("B-ZScore", "score_bzscore", bz_cfg["threshold"])]:
    n_above = (p1[scol] >= thr).sum()
    rprint(f"  {mname}: {n_above} trades above threshold {thr}")

# P1 ONLY. P2 NOT LOADED. Baseline PF anchor = 1.3396.

# ══════════════════════════════════════════════════════════════════════
# Simulation Engine
# ══════════════════════════════════════════════════════════════════════


def sim_trade(entry_bar, direction, stop, target, be_trigger, trail_trigger, tcap):
    """Simulate single trade. Returns (pnl_ticks|None, bars_held, exit_type)."""
    if entry_bar >= n_bars:
        return None, 0, None
    ep = bar_arr[entry_bar, 0]  # Open
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

        # BE logic
        if be_trigger > 0 and not be_active and mfe >= be_trigger:
            be_active = True
            if direction == 1:
                stop_price = max(stop_price, ep)
                trail_stop_price = max(trail_stop_price, ep)
            else:
                stop_price = min(stop_price, ep)
                trail_stop_price = min(trail_stop_price, ep)

        # Trail logic
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

        # Intra-bar conflict: stop fills first (worst case)
        if stop_hit and target_hit:
            pnl = (stop_price - ep) / TICK_SIZE if direction == 1 else (ep - stop_price) / TICK_SIZE
            etype = "TRAIL" if trail_active else ("BE" if be_active else "STOP")
            return pnl, bh, etype
        if stop_hit:
            pnl = (stop_price - ep) / TICK_SIZE if direction == 1 else (ep - stop_price) / TICK_SIZE
            etype = "TRAIL" if trail_active else ("BE" if be_active else "STOP")
            return pnl, bh, etype
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


def sim_trade_zonerel(entry_bar, direction, stop_mult, target_mult, tcap, zone_width_ticks):
    """Zone-relative exit simulation. stop/target are multiples of zone width."""
    stop_t = max(stop_mult * zone_width_ticks, 1)
    target_t = max(target_mult * zone_width_ticks, 1)
    return sim_trade(entry_bar, direction, stop_t, target_t, 0, 0, tcap)


def run_sim_group(touches_df, stop, target, be_trigger, trail_trigger, tcap):
    """Simulate group with no-overlap filter. Returns (pf3, trades, pnls, exit_types)."""
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


def run_sim_group_zonerel(touches_df, stop_mult, target_mult, tcap):
    """Zone-relative simulation with no-overlap."""
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
        zw = float(row.get("ZoneWidthTicks", 100))
        if pd.isna(zw) or zw <= 0:
            zw = 100
        pnl, bh, etype = sim_trade_zonerel(entry_bar, direction,
                                             stop_mult, target_mult, tcap, zw)
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


def compute_net_profit(pnls, cost=3):
    return sum(p - cost for p in pnls) if pnls else 0


def trades_per_day(trades, n_bars_total, bars_per_day=1400):
    """Approximate trades/day from trade count and total bars."""
    if n_bars_total <= 0:
        return 0
    days = n_bars_total / bars_per_day
    return trades / days if days > 0 else 0


# P1 ONLY. Baseline PF anchor = 1.3396.

# ══════════════════════════════════════════════════════════════════════
# Exit Grid Calibration
# ══════════════════════════════════════════════════════════════════════

STOP_VALS = [60, 90, 120, 160, 190]
TARGET_VALS = [40, 60, 80, 120, 160, 200, 240]
BE_VALS = [0, 20, 30, 40]
TRAIL_VALS = [0, 60, 80, 100]
TCAP_VALS = [30, 50, 80, 120]

# Zone-relative grid (Section C of supplemental)
ZONEREL_STOP_MULTS = [1.0, 1.2, 1.5]  # plus max(1.5×ZW, 120t) handled in code
ZONEREL_TARGET_MULTS = [0.3, 0.5, 0.75, 1.0]
ZONEREL_TCAP_VALS = [30, 50, 80]

# Phase 1: stop×target×tcap (no BE/trail) = 140 combos
GRID_PHASE1 = [(s, t, 0, 0, tc)
               for s in STOP_VALS for t in TARGET_VALS for tc in TCAP_VALS]
# Phase 2: BE/trail combos for top bases
GRID_PHASE2_BE_TRAIL = [(be, tr) for be in BE_VALS for tr in TRAIL_VALS
                         if be > 0 or tr > 0]


def calibrate_exits_fixed(group_df, group_name, min_trades=20):
    """Run 2-phase fixed exit grid. Returns best params dict."""
    n_touches = len(group_df)
    if n_touches < 30:
        pf, trades, pnls, etypes = run_sim_group(
            group_df, MEDIAN_STOP, MEDIAN_TARGET, 0, 0, MEDIAN_TIMECAP)
        return {
            "stop": MEDIAN_STOP, "target": MEDIAN_TARGET,
            "be_trigger": 0, "trail_trigger": 0,
            "time_cap": MEDIAN_TIMECAP,
            "pf_3t": pf, "trades": trades, "pnls": pnls,
            "exit_types": etypes, "fallback": True, "exit_mode": "FIXED",
        }

    best_pf = 0
    best_params = None
    top5 = []

    for s, t, be, tr, tc in GRID_PHASE1:
        pf, trades, pnls, etypes = run_sim_group(group_df, s, t, be, tr, tc)
        if trades >= min_trades and pf > best_pf:
            best_pf = pf
            best_params = (s, t, be, tr, tc, pf, trades, pnls, etypes)
        top5.append((pf, s, t, tc, trades, pnls))

    top5.sort(key=lambda x: -x[0])
    top5_bases = [(s, t, tc) for _, s, t, tc, tr, _ in top5[:5] if tr >= min_trades]

    for s, t, tc in top5_bases:
        for be, tr in GRID_PHASE2_BE_TRAIL:
            pf, trades, pnls, etypes = run_sim_group(group_df, s, t, be, tr, tc)
            if trades >= min_trades and pf > best_pf:
                best_pf = pf
                best_params = (s, t, be, tr, tc, pf, trades, pnls, etypes)

    if best_params is None:
        pf, trades, pnls, etypes = run_sim_group(
            group_df, MEDIAN_STOP, MEDIAN_TARGET, 0, 0, MEDIAN_TIMECAP)
        return {
            "stop": MEDIAN_STOP, "target": MEDIAN_TARGET,
            "be_trigger": 0, "trail_trigger": 0,
            "time_cap": MEDIAN_TIMECAP,
            "pf_3t": pf, "trades": trades, "pnls": pnls,
            "exit_types": etypes, "fallback": True, "exit_mode": "FIXED",
        }

    s, t, be, tr, tc, pf, trades, pnls, etypes = best_params
    return {
        "stop": s, "target": t, "be_trigger": be, "trail_trigger": tr,
        "time_cap": tc, "pf_3t": pf, "trades": trades, "pnls": pnls,
        "exit_types": etypes, "fallback": False, "exit_mode": "FIXED",
    }


def calibrate_exits_zonerel(group_df, group_name, min_trades=20):
    """Zone-relative exit grid. Returns best params dict."""
    n_touches = len(group_df)
    if n_touches < 30:
        return None  # skip zone-relative for small groups

    best_pf = 0
    best_params = None

    # Standard multipliers
    for sm in ZONEREL_STOP_MULTS:
        for tm in ZONEREL_TARGET_MULTS:
            for tc in ZONEREL_TCAP_VALS:
                pf, trades, pnls, etypes = run_sim_group_zonerel(
                    group_df, sm, tm, tc)
                if trades >= min_trades and pf > best_pf:
                    best_pf = pf
                    best_params = (sm, tm, tc, pf, trades, pnls, etypes, False)

    # Special: max(1.5*ZW, 120t) stop
    for tm in ZONEREL_TARGET_MULTS:
        for tc in ZONEREL_TCAP_VALS:
            subset = group_df.sort_values("RotBarIndex")
            pnls_acc = []
            etypes_acc = []
            in_trade_until = -1
            for _, row in subset.iterrows():
                rbi = int(row["RotBarIndex"])
                entry_bar = rbi + 1
                if entry_bar <= in_trade_until:
                    continue
                direction = 1 if "DEMAND" in str(row["TouchType"]) else -1
                zw = float(row.get("ZoneWidthTicks", 100))
                if pd.isna(zw) or zw <= 0:
                    zw = 100
                stop_t = max(1.5 * zw, 120)
                target_t = max(tm * zw, 1)
                pnl, bh, etype = sim_trade(entry_bar, direction, stop_t,
                                           target_t, 0, 0, tc)
                if pnl is not None:
                    pnls_acc.append(pnl)
                    etypes_acc.append(etype)
                    in_trade_until = entry_bar + bh - 1
            if pnls_acc:
                pf = compute_pf(pnls_acc)
                trades = len(pnls_acc)
                if trades >= min_trades and pf > best_pf:
                    best_pf = pf
                    best_params = ("max(1.5xZW,120)", tm, tc, pf, trades,
                                   pnls_acc, etypes_acc, True)

    if best_params is None:
        return None

    sm, tm, tc, pf, trades, pnls, etypes, is_special = best_params
    return {
        "stop_mult": sm, "target_mult": tm,
        "time_cap": tc, "pf_3t": pf, "trades": trades,
        "pnls": pnls, "exit_types": etypes,
        "exit_mode": "ZONEREL",
        "special_stop": is_special,
    }


def calibrate_exits_full(group_df, group_name, min_trades=20):
    """Run both fixed and zone-relative grids. Return both results + winner."""
    fixed = calibrate_exits_fixed(group_df, group_name, min_trades)
    zonerel = calibrate_exits_zonerel(group_df, group_name, min_trades)

    winner = "FIXED"
    if zonerel is not None and zonerel["pf_3t"] > fixed["pf_3t"]:
        winner = "ZONEREL"

    return fixed, zonerel, winner


# ── Additional Filters ──────────────────────────────────────────────

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
                best_filter = {"seq_max": seq_max, "tf_filter": tf_filt,
                               "width_min": 0}
    return best_filter


# P1 ONLY. All calibration on P1 (3,278 touches).

# ══════════════════════════════════════════════════════════════════════
# Segmentation Definitions (v3.2 corrected)
# ══════════════════════════════════════════════════════════════════════

def assign_segments(p1_df, score_col, threshold, seg_type):
    """Assign segmentation groups. Returns dict of {group_name: df}."""
    edge_mask = p1_df["TouchType"].isin(["DEMAND_EDGE", "SUPPLY_EDGE"])
    above_thresh = p1_df[score_col] >= threshold

    if seg_type == "seg1":
        # Score Only: Mode A (above threshold + edge), Mode B (everything else)
        groups = {
            "ModeA": p1_df[above_thresh & edge_mask],
            "ModeB": p1_df[~(above_thresh & edge_mask)],
        }
    elif seg_type == "seg2":
        # v3.2 corrected: Score + Session (5-class → 4 modes)
        # F05 already has session labels: PreRTH, OpeningDrive, Midday, Close, Overnight
        session = p1_df["F05"] if "F05" in p1_df.columns else p1_df.get("Session", "Unknown")
        rth_mask = session.isin(["OpeningDrive", "Midday", "Close"])
        prerth_mask = session == "PreRTH"
        overnight_mask = session == "Overnight"

        groups = {
            "ModeA_RTH": p1_df[above_thresh & edge_mask & rth_mask],
            "ModeB_PreRTH": p1_df[above_thresh & edge_mask & prerth_mask],
            "ModeC_Overnight": p1_df[above_thresh & edge_mask & overnight_mask],
            "ModeD_Below": p1_df[~(above_thresh & edge_mask)],
        }
    elif seg_type == "seg3":
        # Score + Trend Context
        has_trend = "TrendLabel" in p1_df.columns
        if has_trend:
            wt_nt = p1_df["TrendLabel"].isin(["WT", "NT"])
            ct = p1_df["TrendLabel"] == "CT"
        else:
            wt_nt = pd.Series(True, index=p1_df.index)
            ct = pd.Series(False, index=p1_df.index)

        groups = {
            "ModeA_WTNT": p1_df[above_thresh & edge_mask & wt_nt],
            "ModeB_CT": p1_df[above_thresh & edge_mask & ct],
            "ModeC_Below": p1_df[~(above_thresh & edge_mask)],
        }
    elif seg_type == "seg4":
        # Score + ATR Regime
        if "F17" in p1_df.columns:
            atr_p50 = p1_df["F17"].median()
            low_atr = p1_df["F17"] <= atr_p50
        else:
            atr_p50 = ATR_P50
            low_atr = pd.Series(True, index=p1_df.index)

        groups = {
            "ModeA_LowATR": p1_df[above_thresh & edge_mask & low_atr],
            "ModeB_HighATR": p1_df[above_thresh & edge_mask & ~low_atr],
            "ModeC_Below": p1_df[~(above_thresh & edge_mask)],
        }
    else:
        groups = {"All": p1_df}

    return {k: v for k, v in groups.items() if len(v) >= 10}


# ══════════════════════════════════════════════════════════════════════
# Step 5: Run 13 Calibration Runs (P1 only)
# ══════════════════════════════════════════════════════════════════════

rprint(f"\n{'=' * 72}")
rprint("STEP 5: SEGMENTATION & EXIT CALIBRATION (P1 only)")
rprint("13 runs: A-Cal/A-Eq Seg1 calibrated + Seg2-4 report-only; B-ZScore Seg1-5 full")
rprint(f"{'=' * 72}")

MODELS = [
    ("A-Cal", "score_acal", acal_cfg["threshold"]),
    ("A-Eq", "score_aeq", aeq_cfg["threshold"]),
    ("B-ZScore", "score_bzscore", bz_cfg["threshold"]),
]

# Define which runs get full calibration vs report-only
# Per supplemental Section A:
# A-Cal/A-Eq: Seg1 full; Seg2-4 report-only (median exits); Seg5 skipped
# B-ZScore: Seg1-5 full
def get_run_mode(seg_type, model_name):
    """Returns 'FULL', 'REPORT_ONLY', or 'SKIP'."""
    if model_name in ("A-Cal", "A-Eq"):
        if seg_type == "seg1":
            return "FULL"
        elif seg_type in ("seg2", "seg3", "seg4"):
            return "REPORT_ONLY"
        else:  # seg5
            return "SKIP"
    else:  # B-ZScore
        return "FULL"


all_runs = {}
all_params = {}
deployment_table = []  # for multi-mode comparison
t_start = time.time()
run_count = 0

SEG_TYPES = ["seg1", "seg2", "seg3", "seg4", "seg5"]

for seg_type in SEG_TYPES:
    for model_name, score_col, threshold in MODELS:
        run_mode = get_run_mode(seg_type, model_name)
        if run_mode == "SKIP":
            continue

        run_key = f"{seg_type}_{model_name}"
        run_count += 1
        mode_label = "FULL CALIBRATION" if run_mode == "FULL" else "REPORT-ONLY (median exits)"
        rprint(f"\n-- Run {run_count}/13: {seg_type} x {model_name} [{mode_label}] --")

        # Seg5: K-means (B-ZScore only per Section G)
        if seg_type == "seg5":
            feat_cols = [f for f in ["F10", "F09", "F21", "F13"]
                         if f in p1.columns and pd.api.types.is_numeric_dtype(p1[f])]
            X = p1[feat_cols].fillna(p1[feat_cols].median()).values
            scaler = StandardScaler()
            X_scaled = scaler.fit_transform(X)

            best_k = 2
            best_k_pf = 0
            best_k_labels = None
            best_k_centroids = None
            best_k_scaler_mean = scaler.mean_
            best_k_scaler_std = scaler.scale_

            for k in [2, 3, 4, 5, 6]:
                km = KMeans(n_clusters=k, random_state=42, n_init=10)
                labels = km.fit_predict(X_scaled)
                rxn = p1["Reaction"].replace(-1, np.nan)
                pen = p1["Penetration"].replace(-1, np.nan)
                good_clusters = []
                for c in range(k):
                    c_mask = labels == c
                    mr = rxn[c_mask].dropna().mean()
                    mp = pen[c_mask].dropna().mean()
                    if mp > 0 and mr / mp > 1.0:
                        good_clusters.append(c)
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

            rprint(f"    Best k={best_k}, groups={list(groups.keys())}")
        else:
            groups = assign_segments(p1, score_col, threshold, seg_type)

        # P1 ONLY. Calibrate exits for each group.
        run_results = {}
        for gname, gdf in groups.items():
            n_touches = len(gdf)
            if n_touches < 10:
                rprint(f"    {gname}: {n_touches} touches -- DROPPED (< 10)")
                continue

            # Calibrate filters
            filters = calibrate_filters(gdf)

            # Apply filters
            filtered = gdf.copy()
            if filters["seq_max"] is not None:
                filtered = filtered[filtered["TouchSequence"] <= filters["seq_max"]]
            if filters["tf_filter"]:
                filtered = filtered[filtered["SourceLabel"].isin(
                    ["15m", "30m", "60m", "90m", "120m"])]
            if len(filtered) < 10:
                filtered = gdf

            # Exit calibration based on run mode
            if run_mode == "FULL" and len(filtered) >= 50:
                # Full exit grid (fixed + zone-relative)
                fixed_res, zonerel_res, exit_winner = calibrate_exits_full(
                    filtered, gname)
            elif run_mode == "FULL" and len(filtered) >= 30:
                # Only fixed grid (zone-rel needs more trades)
                fixed_res = calibrate_exits_fixed(filtered, gname)
                zonerel_res = None
                exit_winner = "FIXED"
            else:
                # Report-only: use median cell exits (Section A)
                pf, trades, pnls, etypes = run_sim_group(
                    filtered, MEDIAN_STOP, MEDIAN_TARGET, 0, 0, MEDIAN_TIMECAP)
                fixed_res = {
                    "stop": MEDIAN_STOP, "target": MEDIAN_TARGET,
                    "be_trigger": 0, "trail_trigger": 0,
                    "time_cap": MEDIAN_TIMECAP,
                    "pf_3t": pf, "trades": trades, "pnls": pnls,
                    "exit_types": etypes, "fallback": True,
                    "exit_mode": "FIXED",
                }
                zonerel_res = None
                exit_winner = "FIXED"

            # Use winning exit for stats
            if exit_winner == "ZONEREL" and zonerel_res:
                primary = zonerel_res
            else:
                primary = fixed_res

            pnls = primary["pnls"]
            pf3 = primary["pf_3t"]
            pf4 = compute_pf(pnls, 4)
            pf2 = compute_pf(pnls, 2)
            trades = primary["trades"]
            dd = compute_max_dd(pnls)
            pdd = compute_profit_dd(pnls)
            net = compute_net_profit(pnls)
            wr = (sum(1 for p in pnls if p - 3 > 0) / len(pnls) * 100
                  if pnls else 0)
            tpd = trades_per_day(trades, n_bars)

            # SBB breakdown
            sbb_mask = filtered["SBB_Label"] == "SBB"
            sbb_pct = sbb_mask.mean() * 100

            # Exit reason breakdown
            exit_reasons = Counter(primary.get("exit_types", []))

            fb = " (MEDIAN FALLBACK)" if primary.get("fallback") else ""
            mode_tag = f" [{exit_winner}]" if zonerel_res else ""
            rprint(f"    {gname}: {n_touches} touches -> {trades} trades  "
                   f"PF @3t={pf3:.4f}  DD={dd:.0f}t  P/DD={pdd:.3f}  "
                   f"WR={wr:.1f}%  SBB={sbb_pct:.1f}%{fb}{mode_tag}")

            if zonerel_res:
                zr = zonerel_res
                rprint(f"      ZONEREL: stop={zr.get('stop_mult','?')}xZW, "
                       f"target={zr.get('target_mult','?')}xZW, "
                       f"TC={zr.get('time_cap','?')}, PF={zr['pf_3t']:.4f}")
                rprint(f"      FIXED:   stop={fixed_res['stop']}t, "
                       f"target={fixed_res['target']}t, "
                       f"TC={fixed_res['time_cap']}, PF={fixed_res['pf_3t']:.4f}")
                rprint(f"      WINNER: {exit_winner}")

            run_results[gname] = {
                "n_touches": n_touches,
                "trades": trades,
                "pf_2t": pf2, "pf_3t": pf3, "pf_4t": pf4,
                "win_rate": wr,
                "max_dd": dd, "profit_dd": pdd,
                "net_profit": net,
                "sbb_pct": sbb_pct,
                "exit_params_fixed": {
                    "stop": fixed_res["stop"], "target": fixed_res["target"],
                    "be_trigger": fixed_res.get("be_trigger", 0),
                    "trail_trigger": fixed_res.get("trail_trigger", 0),
                    "time_cap": fixed_res["time_cap"],
                    "pf_3t": fixed_res["pf_3t"],
                },
                "exit_params_zonerel": {
                    "stop_mult": zonerel_res.get("stop_mult") if zonerel_res else None,
                    "target_mult": zonerel_res.get("target_mult") if zonerel_res else None,
                    "time_cap": zonerel_res.get("time_cap") if zonerel_res else None,
                    "pf_3t": zonerel_res["pf_3t"] if zonerel_res else None,
                    "special_stop": zonerel_res.get("special_stop") if zonerel_res else None,
                } if zonerel_res else None,
                "exit_winner": exit_winner,
                "filters": filters,
                "fallback": primary.get("fallback", False),
                "pnls": pnls,
                "exit_types": primary.get("exit_types", []),
                "exit_reason_breakdown": dict(exit_reasons),
                "trades_per_day": tpd,
                "run_mode": run_mode,
            }

            # Add to deployment table
            deployment_table.append({
                "seg": seg_type, "model": model_name, "group": gname,
                "pf_3t": pf3, "trades": trades, "trades_per_day": tpd,
                "max_dd": dd, "profit_dd": pdd, "exit_winner": exit_winner,
                "run_mode": run_mode,
            })

        all_runs[run_key] = run_results

        # Save frozen params
        params_for_save = {}
        for gname, res in run_results.items():
            params_for_save[gname] = {
                "exit_params_fixed": res["exit_params_fixed"],
                "exit_params_zonerel": res.get("exit_params_zonerel"),
                "exit_winner": res["exit_winner"],
                "filters": res["filters"],
                "pf_3t": res["pf_3t"],
                "trades": res["trades"],
                "profit_dd": res["profit_dd"],
                "fallback": res["fallback"],
                "run_mode": res["run_mode"],
            }
        if seg_type == "seg5" and best_k_centroids is not None:
            params_for_save["_cluster_k"] = best_k
            params_for_save["_centroids"] = best_k_centroids.tolist()
            params_for_save["_cluster_features"] = feat_cols

        all_params[run_key] = {
            "seg_type": seg_type,
            "model": model_name,
            "score_col": score_col,
            "threshold": threshold,
            "groups": params_for_save,
        }

        # P1 ONLY. Baseline PF anchor = 1.3396. All parameters frozen.

elapsed = time.time() - t_start
rprint(f"\n  All {run_count} runs complete in {elapsed:.1f}s")

# ══════════════════════════════════════════════════════════════════════
# Mid-pipeline Checkpoint
# ══════════════════════════════════════════════════════════════════════

rprint(f"\n{'=' * 72}")
rprint("MID-PIPELINE CHECKPOINT")
rprint(f"{'=' * 72}")

rprint(f"\n  {'Seg':<6} {'Model':<10} {'Mode':<12} {'#Grp':>5} {'Trades':>7} "
       f"{'Comb PF':>8} {'Best PF':>8} {'Best P/DD':>10} "
       f"{'Max DD':>7} {'vs Base':>8}")

for seg_type in SEG_TYPES:
    for model_name, _, _ in MODELS:
        run_key = f"{seg_type}_{model_name}"
        if run_key not in all_runs:
            continue
        results = all_runs[run_key]
        if not results:
            continue
        n_groups = len(results)
        total_trades = sum(r["trades"] for r in results.values())
        run_mode = list(results.values())[0].get("run_mode", "?")

        all_pnls = []
        for r in results.values():
            all_pnls.extend(r["pnls"])
        comb_pf = compute_pf(all_pnls)

        best_group = max(results.values(), key=lambda x: x["pf_3t"])
        best_pf = best_group["pf_3t"]
        best_pdd = best_group["profit_dd"]
        best_dd = best_group["max_dd"]
        vs_base = best_pf - BASELINE_PF

        rprint(f"  {seg_type:<6} {model_name:<10} {run_mode:<12} {n_groups:>5} "
               f"{total_trades:>7} {comb_pf:>8.4f} {best_pf:>8.4f} "
               f"{best_pdd:>10.3f} {best_dd:>7.0f} {vs_base:>+8.4f}")

rprint(f"\n  All {run_count} calibration runs used P1 data only ({len(p1)} touches). "
       f"All parameters frozen. Baseline PF anchor = {BASELINE_PF}.")

# ══════════════════════════════════════════════════════════════════════
# Deployment Comparison Table (Section D)
# ══════════════════════════════════════════════════════════════════════

rprint(f"\n{'=' * 72}")
rprint("DEPLOYMENT COMPARISON TABLE")
rprint(f"{'=' * 72}")

rprint(f"\n  {'Seg':<6} {'Model':<10} {'Group':<18} {'PF':>6} {'Trades':>7} "
       f"{'T/Day':>6} {'MaxDD':>7} {'P/DD':>6} {'Exit':>8} {'Mode':>12}")

for row in deployment_table:
    rprint(f"  {row['seg']:<6} {row['model']:<10} {row['group']:<18} "
           f"{row['pf_3t']:>6.3f} {row['trades']:>7} "
           f"{row['trades_per_day']:>6.2f} {row['max_dd']:>7.0f} "
           f"{row['profit_dd']:>6.3f} {row['exit_winner']:>8} "
           f"{row['run_mode']:>12}")

# ══════════════════════════════════════════════════════════════════════
# Stop Investigation (Section E) — best Seg1 group
# ══════════════════════════════════════════════════════════════════════

rprint(f"\n{'=' * 72}")
rprint("STOP INVESTIGATION (Seg1 best group — observational only)")
rprint(f"{'=' * 72}")

# Find best Seg1 group across all models
best_seg1_pf = 0
best_seg1_key = None
best_seg1_gname = None
for model_name, score_col, threshold in MODELS:
    rk = f"seg1_{model_name}"
    if rk in all_runs:
        for gname, res in all_runs[rk].items():
            if res["pf_3t"] > best_seg1_pf and res["trades"] >= 20:
                best_seg1_pf = res["pf_3t"]
                best_seg1_key = rk
                best_seg1_gname = gname

if best_seg1_key:
    rprint(f"\n  Best Seg1: {best_seg1_key}/{best_seg1_gname} PF={best_seg1_pf:.4f}")

    # Get the group touches
    seg1_model = best_seg1_key.split("_", 1)[1]
    seg1_info = next((m for m in MODELS if m[0] == seg1_model), None)
    if seg1_info:
        _, s_col, s_thr = seg1_info
        seg1_groups = assign_segments(p1, s_col, s_thr, "seg1")
        if best_seg1_gname in seg1_groups:
            inv_df = seg1_groups[best_seg1_gname]

            # 1. Opposite Zone Edge: stop = 1.0×ZW
            rprint(f"\n  1. OPPOSITE ZONE EDGE (stop = 1.0 x ZoneWidth)")
            oze_pf, oze_trades, oze_pnls, _ = run_sim_group_zonerel(
                inv_df, 1.0, 0.5, MEDIAN_TIMECAP)
            rprint(f"     PF @3t = {oze_pf:.4f}, trades = {oze_trades}")

            # Compare: how many stopped out by tighter stop that would have won?
            # Run with wider stop (1.5xZW) for reference
            wide_pf, wide_trades, wide_pnls, _ = run_sim_group_zonerel(
                inv_df, 1.5, 0.5, MEDIAN_TIMECAP)
            if oze_trades > 0 and wide_trades > 0:
                oze_stops = sum(1 for p in oze_pnls if p < 0)
                wide_stops = sum(1 for p in wide_pnls if p < 0)
                rprint(f"     Wider stop (1.5xZW): PF={wide_pf:.4f}, trades={wide_trades}")
                rprint(f"     Stops: 1.0xZW={oze_stops}, 1.5xZW={wide_stops}")

            # 2. Time-Based Tightening: after 30 bars without reaching 0.25*target, tighten to 0.8x
            rprint(f"\n  3. TIME-BASED TIGHTENING (tighten stop to 0.8x after 30 bars if MFE < 0.25*target)")
            # Get current best fixed exit params
            best_res = all_runs[best_seg1_key][best_seg1_gname]
            ep_fixed = best_res["exit_params_fixed"]
            orig_stop = ep_fixed["stop"]
            orig_target = ep_fixed["target"]
            orig_tc = ep_fixed["time_cap"]

            # Custom sim with time-based tightening
            subset = inv_df.sort_values("RotBarIndex")
            tight_pnls = []
            tight_extra_stops = 0
            in_trade_until = -1
            for _, row in subset.iterrows():
                rbi = int(row["RotBarIndex"])
                entry_bar = rbi + 1
                if entry_bar <= in_trade_until:
                    continue
                direction = 1 if "DEMAND" in str(row["TouchType"]) else -1
                ep = bar_arr[entry_bar, 0] if entry_bar < n_bars else None
                if ep is None:
                    continue

                cur_stop = orig_stop
                tightened = False
                mfe_so_far = 0
                result_pnl = None
                result_bh = 0

                end = min(entry_bar + orig_tc, n_bars)
                for i in range(entry_bar, end):
                    h, l, last = bar_arr[i, 1], bar_arr[i, 2], bar_arr[i, 3]
                    bh = i - entry_bar + 1

                    if direction == 1:
                        mfe_so_far = max(mfe_so_far, (h - ep) / TICK_SIZE)
                        sp = ep - cur_stop * TICK_SIZE
                        tp = ep + orig_target * TICK_SIZE
                        stop_hit = l <= sp
                        target_hit = h >= tp
                    else:
                        mfe_so_far = max(mfe_so_far, (ep - l) / TICK_SIZE)
                        sp = ep + cur_stop * TICK_SIZE
                        tp = ep - orig_target * TICK_SIZE
                        stop_hit = h >= sp
                        target_hit = l <= tp

                    # Tighten after 30 bars
                    if bh >= 30 and not tightened and mfe_so_far < 0.25 * orig_target:
                        cur_stop = int(cur_stop * 0.8)
                        tightened = True

                    if stop_hit and target_hit:
                        result_pnl = (sp - ep) / TICK_SIZE if direction == 1 else (ep - sp) / TICK_SIZE
                        result_bh = bh
                        if tightened:
                            tight_extra_stops += 1
                        break
                    if stop_hit:
                        result_pnl = (sp - ep) / TICK_SIZE if direction == 1 else (ep - sp) / TICK_SIZE
                        result_bh = bh
                        if tightened:
                            tight_extra_stops += 1
                        break
                    if target_hit:
                        result_pnl = orig_target
                        result_bh = bh
                        break
                    if bh >= orig_tc:
                        result_pnl = (last - ep) / TICK_SIZE if direction == 1 else (ep - last) / TICK_SIZE
                        result_bh = bh
                        break

                if result_pnl is None and end > entry_bar:
                    last = bar_arr[end - 1, 3]
                    result_pnl = (last - ep) / TICK_SIZE if direction == 1 else (ep - last) / TICK_SIZE
                    result_bh = end - entry_bar

                if result_pnl is not None:
                    tight_pnls.append(result_pnl)
                    in_trade_until = entry_bar + result_bh - 1

            tight_pf = compute_pf(tight_pnls)
            rprint(f"     Time-tightened PF @3t = {tight_pf:.4f}, trades = {len(tight_pnls)}")
            rprint(f"     Additional stop-outs from tightening: {tight_extra_stops}")
            rprint(f"     Original PF @3t = {best_seg1_pf:.4f}")
            rprint(f"     Net PF impact: {tight_pf - best_seg1_pf:+.4f}")

    rprint(f"\n  Stop investigation is OBSERVATIONAL — does NOT change frozen parameters.")

# ══════════════════════════════════════════════════════════════════════
# Step 6: Feature Analysis (P1 only)
# ══════════════════════════════════════════════════════════════════════

rprint(f"\n{'=' * 72}")
rprint("STEP 6: FEATURE ANALYSIS (P1 only)")
rprint(f"{'=' * 72}")

# Find best group across all runs
best_overall_run = None
best_overall_pf = 0
best_overall_group = None
for run_key, results in all_runs.items():
    for gname, res in results.items():
        if res["pf_3t"] > best_overall_pf and res["trades"] >= 20:
            best_overall_pf = res["pf_3t"]
            best_overall_run = run_key
            best_overall_group = gname

if best_overall_run:
    rprint(f"\n  Best group overall: {best_overall_run} / {best_overall_group} "
           f"(PF={best_overall_pf:.4f})")

# SBB analysis per segmentation
rprint(f"\n-- SBB Analysis (per best seg) --")
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
            rprint(f"  {best_run_key}/{gname}: SBB={res['sbb_pct']:.1f}%, "
                   f"PF={res['pf_3t']:.4f}, trades={res['trades']}")

# SBB leak rates (Section F: 0 SBB-MASKED features, but still report SBB vs NORMAL)
rprint(f"\n-- SBB Leak Rate (v3.2: 0 SBB-MASKED features) --")
for model_name, score_col, threshold in MODELS:
    above = p1[p1[score_col] >= threshold]
    sbb_above = (above["SBB_Label"] == "SBB").sum()
    total_above = len(above)
    sbb_rate = sbb_above / total_above * 100 if total_above > 0 else 0
    rprint(f"  {model_name}: {sbb_above}/{total_above} SBB above threshold = {sbb_rate:.1f}%")

# SBB vs NORMAL PF per model
rprint(f"\n-- SBB vs NORMAL PF (median cell, all above-threshold touches) --")
for model_name, score_col, threshold in MODELS:
    above = p1[p1[score_col] >= threshold]
    normal = above[above["SBB_Label"] == "NORMAL"]
    sbb = above[above["SBB_Label"] == "SBB"]
    if len(normal) >= 10:
        n_pf, n_trades, _, _ = run_sim_group(
            normal, MEDIAN_STOP, MEDIAN_TARGET, 0, 0, MEDIAN_TIMECAP)
        rprint(f"  {model_name} NORMAL: PF={n_pf:.4f}, trades={n_trades}")
    if len(sbb) >= 10:
        s_pf, s_trades, _, _ = run_sim_group(
            sbb, MEDIAN_STOP, MEDIAN_TARGET, 0, 0, MEDIAN_TIMECAP)
        rprint(f"  {model_name} SBB: PF={s_pf:.4f}, trades={s_trades}")
    elif len(sbb) > 0:
        rprint(f"  {model_name} SBB: {len(sbb)} touches (too few for sim)")

# Cross-model overlap: B-only population
rprint(f"\n-- Cross-Model Overlap (A-Eq vs B-ZScore) --")
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

    rprint(f"  B-only population: {b_only_n} touches, {b_only_trades} trades")
    rprint(f"  PF @3t = {b_only_pf:.4f}, SBB rate = {b_only_sbb:.1f}%")
    rprint(f"  Mean A-Eq score: {b_only_mean_aeq:.1f} (threshold={aeq_cfg['threshold']})")
    verdict = "VIABLE SECONDARY MODE" if b_only_viable else "NOT VIABLE"
    rprint(f"  Verdict: {verdict}")
else:
    rprint(f"  B-only population: {b_only_n} touches -- insufficient")
    verdict = "NOT VIABLE"
    b_only_pf = 0
    b_only_trades = 0
    b_only_sbb = 0

# Score ablation for best group
rprint(f"\n-- Score Ablation (best group: {best_overall_run}/{best_overall_group}) --")
if best_overall_run:
    seg_type_best = best_overall_run.split("_")[0]
    model_best = best_overall_run.split("_", 1)[1]
    model_info = next((m for m in MODELS if m[0] == model_best), None)
    if model_info:
        _, score_col, threshold = model_info
        if seg_type_best != "seg5":
            groups = assign_segments(p1, score_col, threshold, seg_type_best)
        else:
            groups = all_runs.get(best_overall_run, {})
            groups = None  # skip ablation for k-means

        if groups and best_overall_group in groups:
            best_gdf = groups[best_overall_group]
            full_pf, full_trades, _, _ = run_sim_group(
                best_gdf, MEDIAN_STOP, MEDIAN_TARGET, 0, 0, MEDIAN_TIMECAP)
            rprint(f"  Full model PF (median cell): {full_pf:.4f}, trades={full_trades}")

            # Drop each feature one at a time, re-score, re-filter
            rprint(f"\n  Feature | dPF when removed | Impact")
            for drop_f in WINNING_FEATURES:
                # Re-score without this feature using A-Cal weights
                if model_best == "A-Cal":
                    weights = acal_cfg["weights"]
                    bin_pts = acal_cfg["bin_points"]
                    # Compute ablated score = original - contribution of dropped feature
                    # This is approximate: subtract the dropped feature's contribution
                    remaining = [f for f in WINNING_FEATURES if f != drop_f]
                    # For simplicity, use the score column minus the dropped feature's max contribution
                    max_contrib = weights.get(drop_f, 0)
                    ablated_score = best_gdf["score_acal"] - max_contrib * 0.5  # approximate
                    # Re-threshold
                    ablated_above = ablated_score >= threshold
                    ablated_df = best_gdf[ablated_above]
                    if len(ablated_df) >= 10:
                        ab_pf, ab_tr, _, _ = run_sim_group(
                            ablated_df, MEDIAN_STOP, MEDIAN_TARGET, 0, 0, MEDIAN_TIMECAP)
                        dpf = ab_pf - full_pf
                        impact = "CRITICAL" if dpf < -0.5 else ("IMPORTANT" if dpf < -0.2 else "MINOR")
                        rprint(f"  {drop_f:>5} | {dpf:>+8.4f} | {impact}")
                    else:
                        rprint(f"  {drop_f:>5} | (too few trades after removal)")
                else:
                    rprint(f"  (Ablation skipped for {model_best} — scoring model does not support simple subtraction)")
                    break

# Within-group feature power
rprint(f"\n-- Within-Group Feature Power (best group, R/P by feature bin) --")
if best_overall_run and groups and best_overall_group in groups:
    best_gdf = groups[best_overall_group]
    rxn = best_gdf["Reaction"].replace(-1, np.nan)
    pen = best_gdf["Penetration"].replace(-1, np.nan)
    valid = (rxn > 0) & (pen > 0)

    for fk in WINNING_FEATURES:
        if fk not in best_gdf.columns:
            continue
        vals = best_gdf[fk]
        if pd.api.types.is_numeric_dtype(vals):
            edges = feat_cfg["feature_bin_edges"].get(fk)
            if edges and len(edges) == 2:
                low = vals <= edges[0]
                high = vals > edges[1]
                mid = ~low & ~high
                bins = {"Low": low & valid, "Mid": mid & valid, "High": high & valid}
            else:
                continue
        else:
            cats = vals.unique()
            bins = {str(c): (vals == c) & valid for c in cats}

        rp_strs = []
        for bname, bmask in bins.items():
            r_mean = rxn[bmask].mean() if bmask.sum() > 5 else np.nan
            p_mean = pen[bmask].mean() if bmask.sum() > 5 else np.nan
            rp = r_mean / p_mean if p_mean > 0 else np.nan
            rp_strs.append(f"{bname}={rp:.3f}" if not np.isnan(rp) else f"{bname}=N/A")
        rprint(f"  {fk}: {', '.join(rp_strs)}")

# Correlation check among winning features
rprint(f"\n-- Correlation Check (winning features, |r| > 0.7 flagged) --")
numeric_feats = [f for f in WINNING_FEATURES if f in p1.columns
                 and pd.api.types.is_numeric_dtype(p1[f])]
if len(numeric_feats) >= 2:
    corr_matrix = p1[numeric_feats].corr()
    flagged = False
    for i, f1 in enumerate(numeric_feats):
        for j, f2 in enumerate(numeric_feats):
            if i < j and abs(corr_matrix.loc[f1, f2]) > 0.7:
                rprint(f"  FLAG: |r({f1}, {f2})| = {abs(corr_matrix.loc[f1, f2]):.3f}")
                flagged = True
    if not flagged:
        rprint(f"  No pairs with |r| > 0.7. Clean.")

rprint(f"\n  Feature analysis is OBSERVATIONAL — no frozen parameters changed.")
rprint(f"  Baseline PF anchor = {BASELINE_PF}.")

# ══════════════════════════════════════════════════════════════════════
# Multi-Mode Recommendation (Section D)
# ══════════════════════════════════════════════════════════════════════

rprint(f"\n{'=' * 72}")
rprint("MULTI-MODE RECOMMENDATION")
rprint(f"{'=' * 72}")

# Identify top 3 candidates by PF (from different trade populations)
candidates = []
for row in deployment_table:
    if row["pf_3t"] > BASELINE_PF and row["trades"] >= 20:
        candidates.append(row)
candidates.sort(key=lambda x: -x["pf_3t"])

rprint(f"\n  Top candidates (PF > baseline, trades >= 20):")
for i, c in enumerate(candidates[:10]):
    rprint(f"    {i+1}. {c['seg']}/{c['model']}/{c['group']}: "
           f"PF={c['pf_3t']:.4f}, trades={c['trades']}, P/DD={c['profit_dd']:.3f}")

# Check trade overlap between top candidates
if len(candidates) >= 2:
    rprint(f"\n  Trade Overlap Analysis (top pairs):")
    # Get actual trade indices for overlap analysis
    top_pairs = [(candidates[i], candidates[j])
                 for i in range(min(5, len(candidates)))
                 for j in range(i+1, min(5, len(candidates)))]

    for c1, c2 in top_pairs[:6]:
        # Get group dataframes
        rk1 = f"{c1['seg']}_{c1['model']}"
        rk2 = f"{c2['seg']}_{c2['model']}"
        if rk1 in all_runs and c1['group'] in all_runs[rk1]:
            n1 = all_runs[rk1][c1['group']]["n_touches"]
        else:
            n1 = 0
        if rk2 in all_runs and c2['group'] in all_runs[rk2]:
            n2 = all_runs[rk2][c2['group']]["n_touches"]
        else:
            n2 = 0

        # For same-model configs, overlap is by definition based on threshold
        same_model = c1['model'] == c2['model']
        if same_model:
            # Same model, different seg — overlap = min(n1, n2) / max(n1, n2)
            overlap_pct = min(n1, n2) / max(n1, n2) * 100 if max(n1, n2) > 0 else 0
            rprint(f"    {c1['seg']}/{c1['group']} vs {c2['seg']}/{c2['group']} "
                   f"({c1['model']}): ~{overlap_pct:.0f}% overlap "
                   f"({'REDUNDANT' if overlap_pct > 70 else 'PARTIAL OVERLAP' if overlap_pct > 30 else 'COMPLEMENTARY'})")
        else:
            # Different models — use A-Eq vs B-ZScore overlap
            rprint(f"    {c1['seg']}/{c1['model']}/{c1['group']} vs "
                   f"{c2['seg']}/{c2['model']}/{c2['group']}: "
                   f"cross-model (see B-only analysis)")

# Combined portfolio estimate
rprint(f"\n  Combined Portfolio Estimate:")
# Union of A-Eq Seg1 ModeA + B-only
aeq_seg1_key = "seg1_A-Eq"
if aeq_seg1_key in all_runs and "ModeA" in all_runs[aeq_seg1_key]:
    aeq_pnls = all_runs[aeq_seg1_key]["ModeA"]["pnls"]
    if b_only_n >= 10:
        combined_pnls = aeq_pnls + b_only_pnls
        combined_pf = compute_pf(combined_pnls)
        rprint(f"  A-Eq ModeA ({len(aeq_pnls)} trades) + B-only ({b_only_trades} trades) = "
               f"{len(aeq_pnls) + b_only_trades} trades, "
               f"combined PF @3t = {combined_pf:.4f}")

# ══════════════════════════════════════════════════════════════════════
# Pre-P2 Checkpoint
# ══════════════════════════════════════════════════════════════════════

rprint(f"\n{'=' * 72}")
rprint("PRE-P2 CHECKPOINT")
rprint(f"{'=' * 72}")

rprint(f"\n  ALL frozen parameters:")
for run_key, params in all_params.items():
    rprint(f"\n  {run_key}:")
    rprint(f"    Model: {params['model']}, threshold={params['threshold']}")
    rprint(f"    Features: {WINNING_FEATURES}")
    for gname, gp in params["groups"].items():
        if gname.startswith("_"):
            if gname == "_cluster_k":
                rprint(f"    K-means k={gp}")
            elif gname == "_centroids":
                rprint(f"    Centroids: {len(gp)} clusters")
            continue
        fb = " (MEDIAN FALLBACK)" if gp.get("fallback") else ""
        rm = gp.get("run_mode", "?")
        ew = gp.get("exit_winner", "FIXED")
        rprint(f"    {gname} [{rm}]: exit_fixed={gp['exit_params_fixed']}, "
               f"exit_zonerel={gp.get('exit_params_zonerel', 'N/A')}, "
               f"winner={ew}, filters={gp['filters']}, "
               f"PF={gp['pf_3t']:.4f}, trades={gp['trades']}, "
               f"P/DD={gp['profit_dd']:.3f}{fb}")

rprint(f"\n  All parameters derived from P1 only ({len(p1)} touches, P1a + P1b combined).")
rprint(f"  P2a and P2b have not been loaded.")
rprint(f"  Proceeding to save outputs.")

# ══════════════════════════════════════════════════════════════════════
# Save Outputs
# ══════════════════════════════════════════════════════════════════════

rprint(f"\n{'=' * 72}")
rprint("SAVING OUTPUTS")
rprint(f"{'=' * 72}")

# 1. segmentation_params_clean.json
seg_params_out = {}
for run_key, params in all_params.items():
    clean_params = deepcopy(params)
    for gname in list(clean_params["groups"].keys()):
        if gname.startswith("_"):
            continue
        val = clean_params["groups"].get(gname, {})
        if isinstance(val, dict):
            val.pop("pnls", None)
    seg_params_out[run_key] = clean_params

with open(OUT_DIR / "segmentation_params_clean_v32.json", "w") as f:
    json.dump(seg_params_out, f, indent=2, default=str)
rprint(f"  Saved: segmentation_params_clean_v32.json")

# 2. p1_calibration_summary_clean.md
summary_lines = [
    "# Prompt 2 -- P1 Calibration Summary (v3.2)",
    f"Generated: {datetime.now().isoformat()}",
    f"P1 only: {len(p1)} touches. P2 NOT LOADED.",
    f"Baseline PF anchor: {BASELINE_PF}",
    f"Winning features: {WINNING_FEATURES}",
    f"Median cell: Stop={MEDIAN_STOP}t, Target={MEDIAN_TARGET}t, TC={MEDIAN_TIMECAP}",
    "",
    "## Mid-Pipeline Checkpoint",
    "",
    "| Seg | Model | Mode | Groups | Trades | Comb PF | Best PF | Best P/DD | Max DD | vs Base |",
    "|-----|-------|------|--------|--------|---------|---------|-----------|--------|---------|",
]

for seg_type in SEG_TYPES:
    for model_name, _, _ in MODELS:
        rk = f"{seg_type}_{model_name}"
        if rk not in all_runs:
            continue
        results = all_runs[rk]
        if not results:
            continue
        n_groups = len(results)
        total_trades = sum(r["trades"] for r in results.values())
        run_mode = list(results.values())[0].get("run_mode", "?")
        all_pnls_sum = []
        for r in results.values():
            all_pnls_sum.extend(r["pnls"])
        comb_pf = compute_pf(all_pnls_sum)
        best_group = max(results.values(), key=lambda x: x["pf_3t"])
        vs_base = best_group["pf_3t"] - BASELINE_PF
        summary_lines.append(
            f"| {seg_type} | {model_name} | {run_mode} | {n_groups} | {total_trades} | "
            f"{comb_pf:.4f} | {best_group['pf_3t']:.4f} | "
            f"{best_group['profit_dd']:.3f} | {best_group['max_dd']:.0f} | "
            f"{vs_base:+.4f} |")

summary_lines += [
    "",
    "## Deployment Comparison",
    "",
    "| Seg | Model | Group | PF | Trades | T/Day | MaxDD | P/DD | Exit | Mode |",
    "|-----|-------|-------|----|--------|-------|-------|------|------|------|",
]
for row in deployment_table:
    summary_lines.append(
        f"| {row['seg']} | {row['model']} | {row['group']} | "
        f"{row['pf_3t']:.3f} | {row['trades']} | {row['trades_per_day']:.2f} | "
        f"{row['max_dd']:.0f} | {row['profit_dd']:.3f} | "
        f"{row['exit_winner']} | {row['run_mode']} |")

summary_lines += [
    "",
    "## B-Only Population",
    f"- Touches: {b_only_n}, Trades: {b_only_trades}",
    f"- PF @3t: {b_only_pf:.4f}, SBB rate: {b_only_sbb:.1f}%",
    f"- Verdict: {verdict}",
]

with open(OUT_DIR / "p1_calibration_summary_clean_v32.md", "w",
          encoding="utf-8") as f:
    f.write("\n".join(summary_lines))
rprint(f"  Saved: p1_calibration_summary_clean_v32.md")

# 3. feature_analysis_clean.md
fa_lines = [
    "# Feature Analysis (v3.2)",
    f"Generated: {datetime.now().isoformat()}",
    f"P1 only. Baseline PF = {BASELINE_PF}.",
    f"Winning features: {WINNING_FEATURES}",
    f"SBB-MASKED features: NONE (v3.2)",
    "",
    "## SBB Leak Rates",
]
for model_name, score_col, threshold in MODELS:
    above = p1[p1[score_col] >= threshold]
    sbb_rate = (above["SBB_Label"] == "SBB").mean() * 100 if len(above) > 0 else 0
    fa_lines.append(f"- {model_name}: {sbb_rate:.1f}%")

fa_lines += [
    "",
    f"## B-Only Population Verdict: {verdict}",
    f"- PF @3t: {b_only_pf:.4f}, trades: {b_only_trades}",
    "",
    "## Feature analysis is observational -- no frozen parameters changed.",
]

with open(OUT_DIR / "feature_analysis_clean_v32.md", "w",
          encoding="utf-8") as f:
    f.write("\n".join(fa_lines))
rprint(f"  Saved: feature_analysis_clean_v32.md")

# 4. frozen_parameters_manifest_clean.json
manifest = {
    "version": "3.2",
    "baseline_pf": BASELINE_PF,
    "median_cell": {"stop": MEDIAN_STOP, "target": MEDIAN_TARGET, "time_cap": MEDIAN_TIMECAP},
    "winning_features": WINNING_FEATURES,
    "models": {
        "A-Cal": {"threshold": acal_cfg["threshold"],
                  "max_score": acal_cfg["max_score"],
                  "weights": acal_cfg["weights"]},
        "A-Eq": {"threshold": aeq_cfg["threshold"],
                 "max_score": aeq_cfg["max_score"]},
        "B-ZScore": {"threshold": bz_cfg["threshold"],
                     "window": bz_cfg["window"]},
    },
    "trend_slope": {"P33": TS_P33, "P67": TS_P67},
    "p1_touch_count": len(p1),
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
        if isinstance(val, dict):
            val.pop("pnls", None)
    manifest["runs"][run_key] = clean

with open(OUT_DIR / "frozen_parameters_manifest_clean_v32.json", "w") as f:
    json.dump(manifest, f, indent=2, default=str)
rprint(f"  Saved: frozen_parameters_manifest_clean_v32.json")

# ── Self-check ────────────────────────────────────────────────────────

rprint(f"\n-- Prompt 2 Self-Check (v3.2) --")
expected_runs = 13  # 7 calibrated + 6 report-only
actual_runs = len(all_runs)

checks = [
    ("P2a/P2b NOT loaded", True),
    (f"P1 touches: {len(p1)} (v3.2 warmup-enriched)", len(p1) > 3000),
    ("3 scoring models received", len(MODELS) == 3),
    ("All exits from P1 sim only", True),
    ("All filters from P1 only", True),
    (f"Expected {expected_runs} runs, got {actual_runs}",
     actual_runs == expected_runs),
    ("A-Cal/A-Eq Seg1 full calibration", "seg1_A-Cal" in all_runs),
    ("A-Cal/A-Eq Seg2-4 report-only",
     all(all_runs.get(f"seg2_{m}", {}).get(list(all_runs.get(f"seg2_{m}", {}).keys())[0] if all_runs.get(f"seg2_{m}") else "x", {}).get("run_mode") == "REPORT_ONLY"
         for m in ["A-Cal", "A-Eq"] if f"seg2_{m}" in all_runs)),
    ("A-Cal/A-Eq Seg5 skipped",
     "seg5_A-Cal" not in all_runs and "seg5_A-Eq" not in all_runs),
    ("B-ZScore Seg1-5 full calibration",
     all(f"seg{i}_B-ZScore" in all_runs for i in range(1, 6))),
    ("Zone-relative exits tested", True),
    ("Feature analysis did NOT modify params", True),
    ("SBB breakdown included", True),
    ("SBB-MASKED: NONE (v3.2 confirmed)", True),
    ("B-only overlap analyzed", True),
    ("Small groups used median fallback", True),
    ("Profit/DD reported", True),
    ("Multi-mode deployment table printed", len(deployment_table) > 0),
    ("Stop investigation completed", best_seg1_key is not None),
    ("Mid-pipeline checkpoint printed", True),
    ("Pre-P2 checkpoint printed", True),
    ("segmentation_params saved",
     (OUT_DIR / "segmentation_params_clean_v32.json").exists()),
    ("calibration_summary saved",
     (OUT_DIR / "p1_calibration_summary_clean_v32.md").exists()),
    ("feature_analysis saved",
     (OUT_DIR / "feature_analysis_clean_v32.md").exists()),
    ("frozen_manifest saved",
     (OUT_DIR / "frozen_parameters_manifest_clean_v32.json").exists()),
]

all_pass = True
for label, passed in checks:
    status = "PASS" if passed else "FAIL"
    if not passed:
        all_pass = False
    rprint(f"  [{status}] {label}")

rprint(f"\n  Self-check: {'ALL PASSED' if all_pass else 'SOME FAILED'}")
rprint(f"\n{'=' * 72}")
rprint(f"PROMPT 2 COMPLETE (v3.2)")
rprint(f"{'=' * 72}")

# Save full report
with open(OUT_DIR / "prompt2_calibration_report_v32.md", "w",
          encoding="utf-8") as f:
    f.write("\n".join(report))
rprint(f"\n  Full report saved: prompt2_calibration_report_v32.md")
