# archetype: zone_touch
"""Exit-type breakdown for 4 'Yes' groups on P2 holdout data.

Re-simulates the 4 groups using frozen P1 parameters against P2 bar data.
Also re-runs the winner (seg3 A-Cal ModeB) against P1 for comparison.
Does NOT modify any frozen parameters.

Groups:
  1. seg3 × A-Cal ModeB (winner — CT, 58 P2 trades)
  2. seg1 × A-Cal ModeA (91 P2 trades)
  3. seg2 × A-Cal ModeA (91 P2 trades — confirm if identical to seg1)
  4. seg4 × A-Cal ModeA (72 P2 trades)
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
with open(OUT_DIR / "scoring_model_acal.json") as f:
    acal_cfg = json.load(f)

TS_P33 = feat_cfg["trend_slope_p33"]
TS_P67 = feat_cfg["trend_slope_p67"]
WINNING_FEATURES = feat_cfg["winning_features"]

# ══════════════════════════════════════════════════════════════════════
# Load data
# ══════════════════════════════════════════════════════════════════════

# P1 (for comparison)
p1_acal = pd.read_csv(OUT_DIR / "p1_scored_touches_acal.csv")

bar_p1 = pd.read_csv(DATA_DIR / "NQ_bardata_P1.csv")
bar_p1.columns = bar_p1.columns.str.strip()
bar_p1_arr = bar_p1[["Open", "High", "Low", "Last"]].to_numpy(dtype=np.float64)
bar_p1_atr = bar_p1["ATR"].to_numpy(dtype=np.float64)
n_bars_p1 = len(bar_p1_arr)

# P2
p2a_raw = pd.read_csv(DATA_DIR / "NQ_merged_P2a.csv")
p2b_raw = pd.read_csv(DATA_DIR / "NQ_merged_P2b.csv")
bar_p2 = pd.read_csv(DATA_DIR / "NQ_bardata_P2.csv")
bar_p2.columns = bar_p2.columns.str.strip()
bar_p2_arr = bar_p2[["Open", "High", "Low", "Last"]].to_numpy(dtype=np.float64)
bar_p2_atr = bar_p2["ATR"].to_numpy(dtype=np.float64)
n_bars_p2 = len(bar_p2_arr)

# Filter RotBarIndex < 0
p2a = p2a_raw[p2a_raw["RotBarIndex"] >= 0].reset_index(drop=True)
p2b = p2b_raw[p2b_raw["RotBarIndex"] >= 0].reset_index(drop=True)
p2_all = pd.concat([p2a, p2b], ignore_index=True)

print(f"P1 scored touches: {len(p1_acal)}")
print(f"P2a touches: {len(p2a)}, P2b touches: {len(p2b)}, P2 combined: {len(p2_all)}")
print(f"P1 bars: {n_bars_p1}, P2 bars: {n_bars_p2}")


# ══════════════════════════════════════════════════════════════════════
# Feature computation on P2 (P1-frozen params)
# ══════════════════════════════════════════════════════════════════════

def compute_features_p2(df):
    df = df.copy()
    df["F01_Timeframe"] = df["SourceLabel"]
    df["F04_CascadeState"] = df["CascadeState"].replace("UNKNOWN", "NO_PRIOR")

    # F10: Prior Penetration
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

    # F21: Zone Age
    df["F21_ZoneAge"] = df["ZoneAgeBars"]

    # F17: ATR Regime (for seg4)
    atr_regime = []
    for rbi in df["RotBarIndex"].values:
        rbi = int(rbi)
        if rbi < 50 or rbi >= n_bars_p2:
            atr_regime.append(np.nan)
            continue
        start = max(0, rbi - 500)
        trailing = bar_p2_atr[start:rbi + 1]
        current = bar_p2_atr[rbi]
        pctile = (trailing < current).sum() / len(trailing)
        atr_regime.append(pctile)
    df["F17_ATRRegime"] = atr_regime

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

    return df


# ══════════════════════════════════════════════════════════════════════
# A-Cal scoring (P1-frozen)
# ══════════════════════════════════════════════════════════════════════

def score_acal(df):
    weights = acal_cfg["weights"]
    bin_edges = acal_cfg["bin_edges"]
    cat_maps = acal_cfg["categorical_mappings"]
    scores = np.zeros(len(df))

    for feat, weight in weights.items():
        if feat in bin_edges:
            lo, hi = bin_edges[feat]
            vals = df[feat].values.astype(float)
            pts = np.where(vals <= lo, weight,
                    np.where(vals <= hi, weight / 2, 0.0))
            pts = np.where(np.isnan(vals), 0.0, pts)
            scores += pts
        elif feat in cat_maps:
            cm = cat_maps[feat]
            cats = cm["cats"]
            best = cm["best"]
            worst = cm["worst"]
            rank_map = {}
            if len(cats) <= 3:
                rank_map[best] = weight
                rank_map[worst] = 0.0
                for c in cats:
                    if c not in rank_map:
                        rank_map[c] = weight / 2
            else:
                for c in cats:
                    if c == best:
                        rank_map[c] = weight
                    elif c == worst:
                        rank_map[c] = 0.0
                    else:
                        rank_map[c] = weight / 2
            pts = df[feat].map(rank_map).fillna(0).values
            scores += pts

    return scores


# ══════════════════════════════════════════════════════════════════════
# Simulation (identical to prompt3)
# ══════════════════════════════════════════════════════════════════════

def sim_trade(entry_bar, direction, stop, target, be_trigger, trail_trigger,
              tcap, bar_data, total_bars):
    if entry_bar >= total_bars:
        return None, 0, None
    ep = bar_data[entry_bar, 0]
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

    end = min(entry_bar + tcap, total_bars)
    for i in range(entry_bar, end):
        h, l, last = bar_data[i, 1], bar_data[i, 2], bar_data[i, 3]
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
        last = bar_data[end - 1, 3]
        pnl = (last - ep) / TICK_SIZE if direction == 1 else (ep - last) / TICK_SIZE
        return pnl, end - entry_bar, "TIMECAP"
    return None, 0, None


def run_sim_group(touches_df, stop, target, be_trigger, trail_trigger, tcap,
                  bar_data, total_bars):
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
                                    be_trigger, trail_trigger, tcap,
                                    bar_data, total_bars)
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


# ══════════════════════════════════════════════════════════════════════
# Segmentation helpers
# ══════════════════════════════════════════════════════════════════════

def assign_segments(df, score_col, threshold, seg_type):
    edge_mask = df["TouchType"].isin(["DEMAND_EDGE", "SUPPLY_EDGE"])
    above_thresh = df[score_col] >= threshold

    if seg_type == "seg1":
        groups = {
            "ModeA": df[above_thresh & edge_mask],
            "ModeB": df[~(above_thresh & edge_mask)],
        }
    elif seg_type == "seg2":
        sessions = df["DateTime"].apply(get_session) if "DateTime" in df.columns else pd.Series("Other", index=df.index)
        groups = {
            "ModeA": df[above_thresh & edge_mask],
            "ModeB": df[~above_thresh & edge_mask &
                        (sessions == "Morning")],
            "ModeC": df[edge_mask & (sessions == "Afternoon") &
                        ~(above_thresh & edge_mask)],
            "ModeD": df[~edge_mask | (~above_thresh &
                        ~(sessions == "Morning") &
                        ~(sessions == "Afternoon"))],
        }
    elif seg_type == "seg3":
        wt_nt = df["TrendLabel"].isin(["WT", "NT"]) if "TrendLabel" in df.columns else True
        ct = (df["TrendLabel"] == "CT") if "TrendLabel" in df.columns else False
        groups = {
            "ModeA": df[above_thresh & edge_mask & wt_nt],
            "ModeB": df[above_thresh & edge_mask & ct],
            "ModeC": df[~(above_thresh & edge_mask)],
        }
    elif seg_type == "seg4":
        atr_p50 = df["F17_ATRRegime"].median() if "F17_ATRRegime" in df.columns else 0.5
        low_atr = (df["F17_ATRRegime"] <= atr_p50) if "F17_ATRRegime" in df.columns else True
        groups = {
            "ModeA": df[above_thresh & edge_mask & low_atr],
            "ModeB": df[above_thresh & edge_mask & ~low_atr],
            "ModeC": df[~(above_thresh & edge_mask)],
        }
    else:
        groups = {"All": df}

    return {k: v for k, v in groups.items() if len(v) >= 1}


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


# ══════════════════════════════════════════════════════════════════════
# Apply filters (same as prompt3)
# ══════════════════════════════════════════════════════════════════════

def apply_filters(gdf, filt):
    filtered = gdf.copy()
    if filt.get("seq_max") is not None:
        filtered = filtered[filtered["TouchSequence"] <= filt["seq_max"]]
    if filt.get("tf_filter"):
        filtered = filtered[filtered["SourceLabel"].isin(
            ["15m", "30m", "60m", "90m", "120m"])]
    if len(filtered) < 1:
        filtered = gdf
    return filtered


# ══════════════════════════════════════════════════════════════════════
# Main: compute P2 features, score, segment, simulate
# ══════════════════════════════════════════════════════════════════════

print("\n── Computing P2 features (P1-frozen params) ──")
p2_all = compute_features_p2(p2_all)
p2_all["score_acal"] = score_acal(p2_all)

above = (p2_all["score_acal"] >= acal_cfg["threshold"]).sum()
print(f"P2 A-Cal: {above}/{len(p2_all)} above threshold ({above/len(p2_all)*100:.1f}%)")

# 4 runs to analyze
RUNS = [
    ("seg3", "A-Cal", "score_acal", 16.66, "ModeB"),
    ("seg1", "A-Cal", "score_acal", 16.66, "ModeA"),
    ("seg2", "A-Cal", "score_acal", 16.66, "ModeA"),
    ("seg4", "A-Cal", "score_acal", 16.66, "ModeA"),
]

print("\n" + "=" * 95)
print("EXIT TYPE BREAKDOWN — 4 'Yes' Groups on P2 (frozen P1 params)")
print("=" * 95)

p2_results = []

for seg_type, model_name, score_col, threshold, group_name in RUNS:
    run_key = f"{seg_type}_{model_name}"
    params = seg_params[run_key]["groups"][group_name]
    ep = params["exit_params"]
    filt = params["filters"]

    groups = assign_segments(p2_all, score_col, threshold, seg_type)
    if group_name not in groups:
        print(f"\n  {run_key}/{group_name}: NO TRADES (group empty)")
        continue
    gdf = groups[group_name]
    filtered = apply_filters(gdf, filt)

    pnls, exit_types = run_sim_group(
        filtered, ep["stop"], ep["target"],
        ep["be_trigger"], ep["trail_trigger"], ep["time_cap"],
        bar_p2_arr, n_bars_p2)

    total = len(exit_types)
    counts = {"TARGET": 0, "STOP": 0, "BE": 0, "TRAIL": 0, "TIMECAP": 0}
    for et in exit_types:
        if et in counts:
            counts[et] += 1

    pcts = {k: (v / total * 100 if total > 0 else 0) for k, v in counts.items()}
    pf3 = compute_pf(pnls, 3)

    # Average PnL by exit type
    pnl_by_type = {"TARGET": [], "STOP": [], "BE": [], "TRAIL": [], "TIMECAP": []}
    for p, et in zip(pnls, exit_types):
        if et in pnl_by_type:
            pnl_by_type[et].append(p - 3)  # net of cost

    label = f"{seg_type} x A-Cal"
    p2_results.append((label, group_name, pcts["TARGET"], pcts["STOP"],
                        pcts["BE"], pcts["TRAIL"], pcts["TIMECAP"], total, pf3,
                        pnl_by_type))

    print(f"\n  {label} / {group_name}:")
    print(f"    Exit: stop={ep['stop']}  target={ep['target']}  "
          f"BE={ep['be_trigger']}  trail={ep['trail_trigger']}  "
          f"tcap={ep['time_cap']}")
    print(f"    Trades: {total}  (PF @3t = {pf3:.4f})")
    for k in ["TARGET", "STOP", "BE", "TRAIL", "TIMECAP"]:
        avg_pnl = np.mean(pnl_by_type[k]) if pnl_by_type[k] else 0
        print(f"    {k:>8}: {counts[k]:>4} ({pcts[k]:>5.1f}%)  "
              f"avg PnL @3t: {avg_pnl:>+7.1f}t")


# ── Summary table ────────────────────────────────────────────────────
print("\n" + "=" * 95)
print(f"{'Run':<18} {'Group':<8} {'Target%':>8} {'Stop%':>7} "
      f"{'BE%':>6} {'Trail%':>7} {'TCap%':>7} {'Trades':>7} {'PF@3t':>8}")
print("-" * 95)
for label, gname, tgt, stp, be, trail, tcap_pct, total, pf, _ in p2_results:
    print(f"{label:<18} {gname:<8} {tgt:>7.1f}% {stp:>6.1f}% "
          f"{be:>5.1f}% {trail:>6.1f}% {tcap_pct:>6.1f}% {total:>7} {pf:>8.4f}")
print("-" * 95)

# ── Check seg1 vs seg2 ModeA identity ────────────────────────────────
print("\n── seg1 vs seg2 ModeA Identity Check ──")
seg1_grp = assign_segments(p2_all, "score_acal", 16.66, "seg1")
seg2_grp = assign_segments(p2_all, "score_acal", 16.66, "seg2")
if "ModeA" in seg1_grp and "ModeA" in seg2_grp:
    s1_idx = set(seg1_grp["ModeA"].index)
    s2_idx = set(seg2_grp["ModeA"].index)
    overlap = len(s1_idx & s2_idx)
    print(f"  seg1 ModeA: {len(s1_idx)} touches, seg2 ModeA: {len(s2_idx)} touches")
    print(f"  Overlap: {overlap} ({overlap/max(len(s1_idx),1)*100:.0f}%)")
    print(f"  IDENTICAL: {'YES' if s1_idx == s2_idx else 'NO'}")


# ══════════════════════════════════════════════════════════════════════
# P1 vs P2 comparison for the winner (seg3 A-Cal ModeB)
# ══════════════════════════════════════════════════════════════════════

print("\n" + "=" * 95)
print("P1 vs P2 COMPARISON — Winner: seg3 x A-Cal / ModeB")
print("=" * 95)

# P1 run
p1 = p1_acal.copy()
p1["F01_Timeframe"] = p1["SourceLabel"]
p1["F04_CascadeState"] = p1["CascadeState"].replace("UNKNOWN", "NO_PRIOR") if "CascadeState" in p1.columns else "NO_PRIOR"
if "TrendSlope" in p1.columns:
    def assign_trend_p1(ts):
        if pd.isna(ts):
            return "NT"
        if ts <= TS_P33:
            return "CT"
        elif ts >= TS_P67:
            return "WT"
        else:
            return "NT"
    p1["TrendLabel"] = p1["TrendSlope"].apply(assign_trend_p1)
elif "TrendLabel" not in p1.columns:
    p1["TrendLabel"] = "NT"

seg3_params = seg_params["seg3_A-Cal"]["groups"]["ModeB"]
ep_winner = seg3_params["exit_params"]
filt_winner = seg3_params["filters"]

# P1 group
p1_groups = assign_segments(p1, "score_acal", 16.66, "seg3")
if "ModeB" in p1_groups:
    p1_gdf = p1_groups["ModeB"]
    p1_filtered = apply_filters(p1_gdf, filt_winner)
    p1_pnls, p1_exits = run_sim_group(
        p1_filtered, ep_winner["stop"], ep_winner["target"],
        ep_winner["be_trigger"], ep_winner["trail_trigger"], ep_winner["time_cap"],
        bar_p1_arr, n_bars_p1)

    p1_total = len(p1_exits)
    p1_counts = {"TARGET": 0, "STOP": 0, "BE": 0, "TRAIL": 0, "TIMECAP": 0}
    for et in p1_exits:
        if et in p1_counts:
            p1_counts[et] += 1
    p1_pcts = {k: (v / p1_total * 100 if p1_total > 0 else 0) for k, v in p1_counts.items()}
    p1_pf3 = compute_pf(p1_pnls, 3)

    # P1 timecap avg PnL
    p1_tcap_pnls = [p - 3 for p, et in zip(p1_pnls, p1_exits) if et == "TIMECAP"]
    p1_tcap_avg = np.mean(p1_tcap_pnls) if p1_tcap_pnls else 0

    # P2 winner (already computed, get from p2_results)
    p2_winner = [r for r in p2_results if r[1] == "ModeB" and "seg3" in r[0]]
    if p2_winner:
        p2w = p2_winner[0]
        p2_pnl_by_type = p2w[9]
        p2_tcap_avg = np.mean(p2_pnl_by_type["TIMECAP"]) if p2_pnl_by_type["TIMECAP"] else 0

        print(f"\n{'Period':<10} {'Target%':>8} {'Stop%':>7} {'BE%':>6} "
              f"{'Trail%':>7} {'TCap%':>7} {'Trades':>7} {'PF@3t':>8}")
        print("-" * 70)
        print(f"{'P1':<10} {p1_pcts['TARGET']:>7.1f}% {p1_pcts['STOP']:>6.1f}% "
              f"{p1_pcts['BE']:>5.1f}% {p1_pcts['TRAIL']:>6.1f}% "
              f"{p1_pcts['TIMECAP']:>6.1f}% {p1_total:>7} {p1_pf3:>8.2f}")
        print(f"{'P2':<10} {p2w[2]:>7.1f}% {p2w[3]:>6.1f}% "
              f"{p2w[4]:>5.1f}% {p2w[5]:>6.1f}% "
              f"{p2w[6]:>6.1f}% {p2w[7]:>7} {p2w[8]:>8.2f}")
        print("-" * 70)

        # Delta analysis
        tgt_delta = p2w[2] - p1_pcts["TARGET"]
        stop_delta = p2w[3] - p1_pcts["STOP"]
        tcap_delta = p2w[6] - p1_pcts["TIMECAP"]

        print(f"\n  Target rate delta (P2 - P1): {tgt_delta:>+.1f} pp")
        print(f"  Stop rate delta (P2 - P1):   {stop_delta:>+.1f} pp")
        print(f"  TCap rate delta (P2 - P1):   {tcap_delta:>+.1f} pp")

        if abs(tgt_delta) > 10:
            print(f"\n  *** FLAG: Target rate shifted by {tgt_delta:+.1f} pp (>10%) ***")
            if stop_delta > 2:
                print(f"    -> Stop exits INCREASED by {stop_delta:+.1f} pp (deeper adverse excursions)")
            if tcap_delta > 2:
                print(f"    -> Time cap exits INCREASED by {tcap_delta:+.1f} pp (slower/stalled trades)")
            print(f"    -> P1 time cap avg PnL @3t: {p1_tcap_avg:>+.1f}t "
                  f"({'partial wins' if p1_tcap_avg > 0 else 'slow losers'})")
            print(f"    -> P2 time cap avg PnL @3t: {p2_tcap_avg:>+.1f}t "
                  f"({'partial wins' if p2_tcap_avg > 0 else 'slow losers'})")
        else:
            print(f"\n  Exit profile STABLE: target rate delta within +/-10 pp.")

        print(f"\n  P1 time cap avg PnL @3t: {p1_tcap_avg:>+.1f}t")
        print(f"  P2 time cap avg PnL @3t: {p2_tcap_avg:>+.1f}t")
else:
    print("  WARNING: seg3 ModeB not found in P1 data")

print("\n" + "=" * 95)
print("All simulations used frozen P1 parameters. No parameters modified.")
print("=" * 95)
