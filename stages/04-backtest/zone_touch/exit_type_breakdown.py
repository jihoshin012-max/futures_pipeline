# archetype: zone_touch
"""Exit-type breakdown for top 5 calibration runs (by PF).

Re-simulates ONLY the 5 specified (seg × model × group) combos using
frozen parameters from segmentation_params_clean.json. Does NOT re-run
all 15 calibration runs. Does NOT modify any frozen parameters.

Output: exit reason table (TARGET / STOP / BE / TRAIL / TIMECAP %).
"""

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = Path(r"c:\Projects\pipeline")
DATA_DIR = BASE / "stages" / "01-data" / "output" / "zone_prep"
OUT_DIR = BASE / "stages" / "04-backtest" / "zone_touch" / "output"
TICK_SIZE = 0.25

# ── Load frozen params ───────────────────────────────────────────────
with open(OUT_DIR / "segmentation_params_clean.json") as f:
    seg_params = json.load(f)
with open(OUT_DIR / "feature_config.json") as f:
    feat_cfg = json.load(f)

TS_P33 = feat_cfg["trend_slope_p33"]
TS_P67 = feat_cfg["trend_slope_p67"]

# ── Load scored P1 touches ───────────────────────────────────────────
p1_acal = pd.read_csv(OUT_DIR / "p1_scored_touches_acal.csv")
p1_aeq = pd.read_csv(OUT_DIR / "p1_scored_touches_aeq.csv")
p1_bz = pd.read_csv(OUT_DIR / "p1_scored_touches_bzscore.csv")

p1 = p1_aeq.copy()
p1["score_acal"] = p1_acal["score_acal"]
p1["score_bzscore"] = p1_bz["score_bzscore"]
p1["score_aeq"] = p1_aeq["score_aeq"]

# ── Load bar data ────────────────────────────────────────────────────
bar_p1 = pd.read_csv(DATA_DIR / "NQ_bardata_P1.csv")
bar_p1.columns = bar_p1.columns.str.strip()
bar_arr = bar_p1[["Open", "High", "Low", "Last"]].to_numpy(dtype=np.float64)
n_bars = len(bar_arr)

# ── sim_trade with exit_type (same as updated prompt2) ───────────────

def sim_trade(entry_bar, direction, stop, target, be_trigger, trail_trigger,
              tcap):
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
            pnl = (stop_price - ep) / TICK_SIZE if direction == 1 else (ep - stop_price) / TICK_SIZE
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


# ── Segmentation helpers (same as prompt2) ───────────────────────────

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


def assign_segments(p1_df, score_col, threshold, seg_type):
    edge_mask = p1_df["TouchType"].isin(["DEMAND_EDGE", "SUPPLY_EDGE"])
    above_thresh = p1_df[score_col] >= threshold

    if seg_type == "seg1":
        groups = {
            "ModeA": p1_df[above_thresh & edge_mask],
            "ModeB": p1_df[~(above_thresh & edge_mask)],
        }
    elif seg_type == "seg3":
        wt_nt = p1_df["TrendLabel"].isin(["WT", "NT"]) if "TrendLabel" in p1_df.columns else True
        ct = (p1_df["TrendLabel"] == "CT") if "TrendLabel" in p1_df.columns else False
        groups = {
            "ModeA": p1_df[above_thresh & edge_mask & wt_nt],
            "ModeB": p1_df[above_thresh & edge_mask & ct],
            "ModeC": p1_df[~(above_thresh & edge_mask)],
        }
    elif seg_type == "seg4":
        atr_p50 = p1_df["F17_ATRRegime"].median() if "F17_ATRRegime" in p1_df.columns else 0.5
        low_atr = (p1_df["F17_ATRRegime"] <= atr_p50) if "F17_ATRRegime" in p1_df.columns else True
        groups = {
            "ModeA": p1_df[above_thresh & edge_mask & low_atr],
            "ModeB": p1_df[above_thresh & edge_mask & ~low_atr],
            "ModeC": p1_df[~(above_thresh & edge_mask)],
        }
    else:
        groups = {"All": p1_df}

    return {k: v for k, v in groups.items() if len(v) >= 10}


# ── 5 runs to re-simulate ───────────────────────────────────────────
RUNS = [
    ("seg1", "A-Cal",    "score_acal",    16.66,  "ModeA"),
    ("seg3", "A-Cal",    "score_acal",    16.66,  "ModeB"),
    ("seg3", "A-Eq",     "score_aeq",     26.0,   "ModeA"),
    ("seg3", "B-ZScore", "score_bzscore", 0.75,   "ModeA"),
    ("seg4", "A-Cal",    "score_acal",    16.66,  "ModeA"),
]

print("=" * 90)
print("EXIT TYPE BREAKDOWN — Top 5 Runs by PF (P1 only, frozen params)")
print("=" * 90)

rows = []
for seg_type, model_name, score_col, threshold, group_name in RUNS:
    run_key = f"{seg_type}_{model_name}"
    params = seg_params[run_key]["groups"][group_name]
    ep = params["exit_params"]
    filt = params["filters"]

    # Reconstruct group
    groups = assign_segments(p1, score_col, threshold, seg_type)
    gdf = groups[group_name]

    # Apply filters
    filtered = gdf.copy()
    if filt["seq_max"] is not None:
        filtered = filtered[filtered["TouchSequence"] <= filt["seq_max"]]
    if filt["tf_filter"]:
        filtered = filtered[filtered["SourceLabel"].isin(
            ["15m", "30m", "60m", "90m", "120m"])]
    if len(filtered) < 10:
        filtered = gdf

    # Simulate with frozen exit params
    pnls, exit_types = run_sim_group(
        filtered, ep["stop"], ep["target"],
        ep["be_trigger"], ep["trail_trigger"], ep["time_cap"])

    total = len(exit_types)
    counts = {"TARGET": 0, "STOP": 0, "BE": 0, "TRAIL": 0, "TIMECAP": 0}
    for et in exit_types:
        if et in counts:
            counts[et] += 1

    pcts = {k: (v / total * 100 if total > 0 else 0) for k, v in counts.items()}

    label = f"{seg_type} × {model_name}"
    rows.append((label, group_name, pcts["TARGET"], pcts["STOP"],
                 pcts["BE"], pcts["TRAIL"], pcts["TIMECAP"], total,
                 params["pf_3t"]))

    print(f"\n  {label} / {group_name}:")
    print(f"    Frozen exit: stop={ep['stop']}  target={ep['target']}  "
          f"BE={ep['be_trigger']}  trail={ep['trail_trigger']}  "
          f"tcap={ep['time_cap']}")
    print(f"    Trades: {total}  (PF @3t = {params['pf_3t']:.4f})")
    for k in ["TARGET", "STOP", "BE", "TRAIL", "TIMECAP"]:
        print(f"    {k:>8}: {counts[k]:>4} ({pcts[k]:>5.1f}%)")

# ── Summary table ────────────────────────────────────────────────────
print("\n" + "=" * 90)
print(f"{'Run':<22} {'Group':<8} {'Target%':>8} {'Stop%':>7} "
      f"{'BE%':>6} {'Trail%':>7} {'TCap%':>7} {'Trades':>7} {'PF@3t':>8}")
print("-" * 90)
for label, gname, tgt, stp, be, trail, tcap, total, pf in rows:
    print(f"{label:<22} {gname:<8} {tgt:>7.1f}% {stp:>6.1f}% "
          f"{be:>5.1f}% {trail:>6.1f}% {tcap:>6.1f}% {total:>7} {pf:>8.4f}")
print("-" * 90)
print("All simulations used P1 data only with frozen parameters.")
print("No parameters were modified. exit_type tags from sim_trade().")
