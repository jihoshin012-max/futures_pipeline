# archetype: zone_touch
"""Pre-Deployment Diagnostics — extract per-trade details from P2 holdout.

No new simulations. Replays frozen P1 parameters on P2 data to capture
per-trade MFE/MAE, feature values, and diagnostic breakdowns that were
not saved during the original Prompt 3 holdout run.

Produces:
  ITEM 1: p2_trade_details.csv  (per-trade features + MFE/MAE)
  ITEM 2: losing_trade_profiles.md  (seg3 ModeB losers)
  ITEM 3: near_miss_analysis.md  (threshold sensitivity)
  ITEM 4: time_of_day_distribution.md  (seg3 ModeB by hour)
"""

import json
import sys
import warnings
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
warnings.filterwarnings("ignore", category=FutureWarning)

import numpy as np
import pandas as pd

BASE = Path(r"c:\Projects\pipeline")
DATA_DIR = BASE / "stages" / "01-data" / "output" / "zone_prep"
OUT_DIR = BASE / "stages" / "04-backtest" / "zone_touch" / "output"
DIAG_DIR = BASE / "stages" / "04-backtest" / "zone_touch" / "output"
TICK_SIZE = 0.25
COST_TICKS = 3

# ── Load frozen configs ─────────────────────────────────────────────
with open(OUT_DIR / "scoring_model_acal.json") as f:
    acal_cfg = json.load(f)
with open(OUT_DIR / "feature_config.json") as f:
    feat_cfg = json.load(f)
with open(OUT_DIR / "segmentation_params_clean.json") as f:
    seg_params = json.load(f)

WINNING_FEATURES = feat_cfg["winning_features"]
TS_P33 = feat_cfg["trend_slope_p33"]
TS_P67 = feat_cfg["trend_slope_p67"]
BIN_EDGES = feat_cfg["bin_edges"]
FEAT_STATS = feat_cfg["feature_stats"]
ACAL_THRESHOLD = acal_cfg["threshold"]

# The 4 "Yes" verdict groups (all use A-Cal scoring)
YES_GROUPS = {
    "seg3_ModeB": {
        "seg_type": "seg3", "group": "ModeB",
        "run_key": "seg3_A-Cal",
    },
    "seg1_ModeA": {
        "seg_type": "seg1", "group": "ModeA",
        "run_key": "seg1_A-Cal",
    },
    "seg2_ModeA": {
        "seg_type": "seg2", "group": "ModeA",
        "run_key": "seg2_A-Cal",
    },
    "seg4_ModeA": {
        "seg_type": "seg4", "group": "ModeA",
        "run_key": "seg4_A-Cal",
    },
}

print("=" * 72)
print("PRE-DEPLOYMENT DIAGNOSTICS")
print("All parameters frozen from P1.  No recalibration.")
print("=" * 72)

# ── Load P2 data ────────────────────────────────────────────────────
print("\n── Loading P2 data ──")
p2a_raw = pd.read_csv(DATA_DIR / "NQ_merged_P2a.csv")
p2b_raw = pd.read_csv(DATA_DIR / "NQ_merged_P2b.csv")
bar_p2 = pd.read_csv(DATA_DIR / "NQ_bardata_P2.csv")
bar_p2.columns = bar_p2.columns.str.strip()

p2a = p2a_raw[p2a_raw["RotBarIndex"] >= 0].reset_index(drop=True)
p2b = p2b_raw[p2b_raw["RotBarIndex"] >= 0].reset_index(drop=True)

bar_arr = bar_p2[["Open", "High", "Low", "Last"]].to_numpy(dtype=np.float64)
bar_atr = bar_p2["ATR"].to_numpy(dtype=np.float64)
n_bars = len(bar_arr)

# Parse bar datetimes
print("  Parsing bar datetimes...")
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

print(f"  P2a: {len(p2a)} touches, P2b: {len(p2b)} touches")
print(f"  P2 bars: {n_bars}")

# ── Feature computation (frozen from P1) ────────────────────────────


def compute_features(df, label):
    """Compute features for P2 subset using P1-frozen parameters."""
    df = df.copy()
    df["F01_Timeframe"] = df["SourceLabel"]
    df["F02_ZoneWidth"] = df["ZoneWidthTicks"]
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

    print(f"  {label}: features computed, F10 null={df['F10_PriorPenetration'].isna().mean()*100:.1f}%")
    return df


p2a = compute_features(p2a, "P2a")
p2b = compute_features(p2b, "P2b")

# ── A-Cal scoring (frozen) ──────────────────────────────────────────


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
            best, worst = cm["best"], cm["worst"]
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


p2a["score_acal"] = score_acal(p2a)
p2b["score_acal"] = score_acal(p2b)
print(f"\n  A-Cal above threshold: P2a={( p2a['score_acal'] >= ACAL_THRESHOLD).sum()}, "
      f"P2b={(p2b['score_acal'] >= ACAL_THRESHOLD).sum()}")

# ── Segmentation assignment ─────────────────────────────────────────


def assign_segments(df, seg_type):
    """Assign A-Cal segmentation groups (frozen from P1)."""
    edge_mask = df["TouchType"].isin(["DEMAND_EDGE", "SUPPLY_EDGE"])
    above_thresh = df["score_acal"] >= ACAL_THRESHOLD

    if seg_type == "seg1":
        return {
            "ModeA": df[above_thresh & edge_mask],
            "ModeB": df[~(above_thresh & edge_mask)],
        }
    elif seg_type == "seg2":
        sessions = df["DateTime"].apply(_get_session)
        return {
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
        return {
            "ModeA": df[above_thresh & edge_mask & wt_nt],
            "ModeB": df[above_thresh & edge_mask & ct],
            "ModeC": df[~(above_thresh & edge_mask)],
        }
    elif seg_type == "seg4":
        atr_p50 = FEAT_STATS.get("F17_ATRRegime", {}).get("mean", 0.844)
        low_atr = df["F17_ATRRegime"] <= atr_p50
        return {
            "ModeA": df[above_thresh & edge_mask & low_atr],
            "ModeB": df[above_thresh & edge_mask & ~low_atr],
            "ModeC": df[~(above_thresh & edge_mask)],
        }
    return {"All": df}


def _get_session(dt_str):
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


def apply_filters(df, filters):
    filtered = df.copy()
    seq_max = filters.get("seq_max")
    if seq_max is not None:
        filtered = filtered[filtered["TouchSequence"] <= seq_max]
    if filters.get("tf_filter"):
        filtered = filtered[filtered["SourceLabel"].isin(
            ["15m", "30m", "60m", "90m", "120m"])]
    return filtered


# ── Enhanced sim_trade with MFE/MAE tracking ────────────────────────


def sim_trade_detailed(entry_bar, direction, stop, target, be_trigger,
                       trail_trigger, tcap):
    """Simulate single trade, returning MFE/MAE in ticks."""
    if entry_bar >= n_bars:
        return None

    ep = bar_arr[entry_bar, 0]  # Open of next bar
    if direction == 1:
        stop_price = ep - stop * TICK_SIZE
        target_price = ep + target * TICK_SIZE
    else:
        stop_price = ep + stop * TICK_SIZE
        target_price = ep - target * TICK_SIZE

    mfe = 0.0
    mae = 0.0
    be_active = False
    trail_active = False
    trail_stop_price = stop_price

    end = min(entry_bar + tcap, n_bars)
    for i in range(entry_bar, end):
        h, l, last = bar_arr[i, 1], bar_arr[i, 2], bar_arr[i, 3]
        bh = i - entry_bar + 1

        if direction == 1:
            cur_fav = (h - ep) / TICK_SIZE
            cur_adv = (ep - l) / TICK_SIZE
        else:
            cur_fav = (ep - l) / TICK_SIZE
            cur_adv = (h - ep) / TICK_SIZE
        mfe = max(mfe, cur_fav)
        mae = max(mae, cur_adv)

        # Breakeven
        if be_trigger > 0 and not be_active and mfe >= be_trigger:
            be_active = True
            if direction == 1:
                stop_price = max(stop_price, ep)
                trail_stop_price = max(trail_stop_price, ep)
            else:
                stop_price = min(stop_price, ep)
                trail_stop_price = min(trail_stop_price, ep)

        # Trail
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
            etype = "TRAIL" if trail_active else ("BE" if be_active else "STOP")
            exit_price = stop_price
            return {
                "entry_price": ep, "exit_price": exit_price,
                "pnl_raw": pnl, "exit_type": etype,
                "bars_held": bh, "mfe_ticks": mfe, "mae_ticks": mae,
            }
        if stop_hit:
            pnl = ((stop_price - ep) / TICK_SIZE if direction == 1
                    else (ep - stop_price) / TICK_SIZE)
            etype = "TRAIL" if trail_active else ("BE" if be_active else "STOP")
            return {
                "entry_price": ep, "exit_price": stop_price,
                "pnl_raw": pnl, "exit_type": etype,
                "bars_held": bh, "mfe_ticks": mfe, "mae_ticks": mae,
            }
        if target_hit:
            return {
                "entry_price": ep, "exit_price": target_price,
                "pnl_raw": target, "exit_type": "TARGET",
                "bars_held": bh, "mfe_ticks": mfe, "mae_ticks": mae,
            }
        if bh >= tcap:
            pnl = ((last - ep) / TICK_SIZE if direction == 1
                    else (ep - last) / TICK_SIZE)
            return {
                "entry_price": ep, "exit_price": last,
                "pnl_raw": pnl, "exit_type": "TIMECAP",
                "bars_held": bh, "mfe_ticks": mfe, "mae_ticks": mae,
            }

    # Fell through (shouldn't happen with tcap logic above)
    if end > entry_bar:
        last = bar_arr[end - 1, 3]
        pnl = ((last - ep) / TICK_SIZE if direction == 1
                else (ep - last) / TICK_SIZE)
        return {
            "entry_price": ep, "exit_price": last,
            "pnl_raw": pnl, "exit_type": "TIMECAP",
            "bars_held": end - entry_bar, "mfe_ticks": mfe, "mae_ticks": mae,
        }
    return None


# ══════════════════════════════════════════════════════════════════════
# ITEM 1: Per-Trade Feature Values
# ══════════════════════════════════════════════════════════════════════

print("\n" + "=" * 72)
print("ITEM 1: Per-Trade Feature Values for 4 Yes Groups")
print("=" * 72)

all_trades = []
trade_id = 0

for yg_label, yg_info in YES_GROUPS.items():
    run_key = yg_info["run_key"]
    seg_type = yg_info["seg_type"]
    group_name = yg_info["group"]

    run_params = seg_params[run_key]
    gp_params = run_params["groups"][group_name]
    ep = gp_params["exit_params"]
    filters = gp_params["filters"]

    print(f"\n  Processing {yg_label} ({seg_type}/{group_name})...")

    for period_label, pdf in [("P2a", p2a), ("P2b", p2b)]:
        groups = assign_segments(pdf, seg_type)
        if group_name not in groups or len(groups[group_name]) == 0:
            print(f"    {period_label}: 0 touches in {group_name}")
            continue

        gdf = groups[group_name]
        filtered = apply_filters(gdf, filters)
        if len(filtered) == 0:
            print(f"    {period_label}: 0 filtered touches")
            continue

        # Simulate with no-overlap filter
        subset = filtered.sort_values("RotBarIndex")
        in_trade_until = -1
        period_trades = 0

        for _, row in subset.iterrows():
            rbi = int(row["RotBarIndex"])
            entry_bar = rbi + 1
            if entry_bar <= in_trade_until:
                continue
            direction = 1 if "DEMAND" in str(row["TouchType"]) else -1

            result = sim_trade_detailed(
                entry_bar, direction,
                ep["stop"], ep["target"],
                ep["be_trigger"], ep["trail_trigger"], ep["time_cap"])

            if result is None:
                continue

            in_trade_until = entry_bar + result["bars_held"] - 1
            trade_id += 1
            period_trades += 1

            # Get bar datetime for entry
            entry_dt = bar_datetimes[entry_bar] if entry_bar < len(bar_datetimes) else None

            pnl_net = result["pnl_raw"] - COST_TICKS

            all_trades.append({
                "trade_id": trade_id,
                "seg_model_group": yg_label,
                "period": period_label,
                "datetime": entry_dt.strftime("%Y-%m-%d %H:%M:%S") if entry_dt else str(row["DateTime"]),
                "direction": "LONG" if direction == 1 else "SHORT",
                "F10_PriorPenetration": row.get("F10_PriorPenetration", np.nan),
                "F04_CascadeState": row.get("F04_CascadeState", ""),
                "F01_Timeframe": row.get("F01_Timeframe", ""),
                "F21_ZoneAge": row.get("F21_ZoneAge", np.nan),
                "acal_score": row.get("score_acal", np.nan),
                "acal_threshold": ACAL_THRESHOLD,
                "score_margin": row.get("score_acal", np.nan) - ACAL_THRESHOLD,
                "trend_label": row.get("TrendLabel", ""),
                "SBB_label": row.get("SBB_Label", ""),
                "entry_price": result["entry_price"],
                "exit_price": result["exit_price"],
                "exit_type": result["exit_type"],
                "pnl_ticks": round(pnl_net, 2),
                "bars_held": result["bars_held"],
                "mfe_ticks": round(result["mfe_ticks"], 2),
                "mae_ticks": round(result["mae_ticks"], 2),
            })

        print(f"    {period_label}: {period_trades} trades")

trades_df = pd.DataFrame(all_trades)
trades_csv_path = DIAG_DIR / "p2_trade_details.csv"
trades_df.to_csv(trades_csv_path, index=False)
print(f"\n  ✓ Saved {len(trades_df)} trades to {trades_csv_path.name}")

# Per-group summary
print("\n  Per-group trade counts:")
for grp, cnt in trades_df.groupby("seg_model_group")["trade_id"].count().items():
    print(f"    {grp}: {cnt} trades")

# ══════════════════════════════════════════════════════════════════════
# ITEM 2: Losing Trade Profiles (seg3 ModeB)
# ══════════════════════════════════════════════════════════════════════

print("\n" + "=" * 72)
print("ITEM 2: Losing Trade Profiles — seg3_ModeB (winner)")
print("=" * 72)

winner = trades_df[trades_df["seg_model_group"] == "seg3_ModeB"]
losers = winner[winner["exit_type"].isin(["STOP", "TIMECAP"])]

print(f"\n  Winner total trades: {len(winner)}")
print(f"  Losers (STOP+TIMECAP): {len(losers)}")

lines = []
lines.append("# Losing Trade Profiles — seg3_A-Cal/ModeB (Winner)")
lines.append(f"Generated: {datetime.now().isoformat()}")
lines.append(f"Total winner trades: {len(winner)}")
lines.append(f"Losers (STOP + TIMECAP): {len(losers)}")
lines.append("")

if len(losers) > 0:
    lines.append("## Individual Losing Trades")
    lines.append("")
    lines.append("| # | datetime | dir | TF | Cascade | F10_Pen | F21_Age | SBB | score | margin | exit | pnl | mfe | mae | bars |")
    lines.append("|---|----------|-----|----|---------|---------|------------|-----|-------|--------|------|-----|-----|-----|------|")

    for i, (_, r) in enumerate(losers.iterrows(), 1):
        lines.append(
            f"| {i} | {r['datetime']} | {r['direction']} | {r['F01_Timeframe']} | "
            f"{r['F04_CascadeState']} | {r['F10_PriorPenetration']:.0f} | "
            f"{r['F21_ZoneAge']:.0f} | {r['SBB_label']} | "
            f"{r['acal_score']:.2f} | {r['score_margin']:.2f} | {r['exit_type']} | "
            f"{r['pnl_ticks']:.1f} | {r['mfe_ticks']:.1f} | {r['mae_ticks']:.1f} | "
            f"{r['bars_held']} |"
        )

    lines.append("")
    lines.append("## Pattern Analysis")
    lines.append("")

    # Timeframe distribution
    tf_counts = losers["F01_Timeframe"].value_counts()
    lines.append("### Timeframe Distribution (losers)")
    for tf, cnt in tf_counts.items():
        pct = cnt / len(losers) * 100
        winner_pct = (winner["F01_Timeframe"] == tf).sum() / len(winner) * 100
        lines.append(f"- {tf}: {cnt} ({pct:.0f}%) — vs {winner_pct:.0f}% of all winner trades")

    # Cascade state
    lines.append("")
    lines.append("### Cascade State (losers)")
    cs_counts = losers["F04_CascadeState"].value_counts()
    for cs, cnt in cs_counts.items():
        pct = cnt / len(losers) * 100
        lines.append(f"- {cs}: {cnt} ({pct:.0f}%)")

    # Direction
    lines.append("")
    lines.append("### Direction (losers)")
    dir_counts = losers["direction"].value_counts()
    for d, cnt in dir_counts.items():
        pct = cnt / len(losers) * 100
        lines.append(f"- {d}: {cnt} ({pct:.0f}%)")

    # Session
    lines.append("")
    lines.append("### Session (losers)")
    def get_hour_session(dt_str):
        try:
            dt = datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S")
            h = dt.hour
            if 9 <= h < 12:
                return "Morning (9-12)"
            elif 12 <= h < 16:
                return "Afternoon (12-16)"
            else:
                return "Overnight/Other"
        except Exception:
            return "Unknown"
    sess_counts = losers["datetime"].apply(get_hour_session).value_counts()
    for s, cnt in sess_counts.items():
        lines.append(f"- {s}: {cnt}")

    # Score margin
    lines.append("")
    lines.append("### Score Margin (losers)")
    lines.append(f"- Mean margin: {losers['score_margin'].mean():.2f}")
    lines.append(f"- Min margin: {losers['score_margin'].min():.2f}")
    lines.append(f"- Max margin: {losers['score_margin'].max():.2f}")
    low_margin = (losers["score_margin"] < 2).sum()
    lines.append(f"- Within 2 pts of threshold: {low_margin} ({low_margin/len(losers)*100:.0f}%)")

    # SBB
    lines.append("")
    lines.append("### SBB Label (losers)")
    sbb_counts = losers["SBB_label"].value_counts()
    for lb, cnt in sbb_counts.items():
        lines.append(f"- {lb}: {cnt}")

    # Exit type breakdown
    lines.append("")
    lines.append("### Exit Type (losers)")
    et_counts = losers["exit_type"].value_counts()
    for et, cnt in et_counts.items():
        lines.append(f"- {et}: {cnt}")

    # MFE of losers — did they get close to target?
    lines.append("")
    lines.append("### MFE of Losers (did they approach target=80t?)")
    winner_target = seg_params["seg3_A-Cal"]["groups"]["ModeB"]["exit_params"]["target"]
    lines.append(f"- Mean MFE: {losers['mfe_ticks'].mean():.1f} ticks (target={winner_target})")
    lines.append(f"- Max MFE: {losers['mfe_ticks'].max():.1f} ticks")
    near_target = (losers["mfe_ticks"] >= winner_target * 0.5).sum()
    lines.append(f"- MFE >= 50% of target ({winner_target*0.5:.0f}t): {near_target}")

else:
    lines.append("No losing trades found! (All trades were winners.)")

losing_path = DIAG_DIR / "losing_trade_profiles.md"
with open(losing_path, "w", encoding="utf-8") as f:
    f.write("\n".join(lines))
print(f"  ✓ Saved to {losing_path.name}")


# ══════════════════════════════════════════════════════════════════════
# ITEM 3: Near-Miss Touches (threshold sensitivity)
# ══════════════════════════════════════════════════════════════════════

print("\n" + "=" * 72)
print("ITEM 3: Near-Miss Touches (A-Cal threshold sensitivity)")
print("=" * 72)

# Combine P2a and P2b for near-miss analysis
p2_all = pd.concat([p2a, p2b], ignore_index=True)

# P1 scored touches
p1_scored = pd.read_csv(OUT_DIR / "p1_scored_touches_acal.csv")
if "score_acal" not in p1_scored.columns:
    # Try to find the score column
    score_cols = [c for c in p1_scored.columns if "score" in c.lower() or "acal" in c.lower()]
    if score_cols:
        p1_scored["score_acal"] = p1_scored[score_cols[0]]

# Edge touches only (since winner groups filter on edges)
p1_edges = p1_scored[p1_scored["TouchType"].isin(["DEMAND_EDGE", "SUPPLY_EDGE"])]
p2_edges = p2_all[p2_all["TouchType"].isin(["DEMAND_EDGE", "SUPPLY_EDGE"])]

# Near misses: within 2 points below threshold
p1_near = p1_edges[(p1_edges["score_acal"] >= ACAL_THRESHOLD - 2) &
                    (p1_edges["score_acal"] < ACAL_THRESHOLD)]
p1_above = p1_edges[p1_edges["score_acal"] >= ACAL_THRESHOLD]

p2_near = p2_edges[(p2_edges["score_acal"] >= ACAL_THRESHOLD - 2) &
                    (p2_edges["score_acal"] < ACAL_THRESHOLD)]
p2_above = p2_edges[p2_edges["score_acal"] >= ACAL_THRESHOLD]

print(f"  P1 near-misses (edges, score {ACAL_THRESHOLD-2:.2f}-{ACAL_THRESHOLD:.2f}): {len(p1_near)}")
print(f"  P1 above threshold (edges): {len(p1_above)}")
print(f"  P2 near-misses (edges): {len(p2_near)}")
print(f"  P2 above threshold (edges): {len(p2_above)}")

# R/P @60 comparison
# Use Rxn_60 and Pen_60 columns if available
rp_cols = ["Rxn_60", "Pen_60"]
has_rp = all(c in p1_scored.columns for c in rp_cols) and all(c in p2_all.columns for c in rp_cols)

nm_lines = []
nm_lines.append("# Near-Miss Touches — A-Cal Threshold Sensitivity")
nm_lines.append(f"Generated: {datetime.now().isoformat()}")
nm_lines.append(f"A-Cal threshold: {ACAL_THRESHOLD}")
nm_lines.append("")
nm_lines.append("## Counts")
nm_lines.append(f"| Period | Near-Miss (T-2 to T) | Above Threshold |")
nm_lines.append(f"|--------|---------------------|-----------------|")
nm_lines.append(f"| P1 (edges) | {len(p1_near)} | {len(p1_above)} |")
nm_lines.append(f"| P2 (edges) | {len(p2_near)} | {len(p2_above)} |")
nm_lines.append("")

if has_rp:
    p1_near_rp = p1_near["Rxn_60"] / p1_near["Pen_60"].replace(0, np.nan)
    p1_above_rp = p1_above["Rxn_60"] / p1_above["Pen_60"].replace(0, np.nan)
    p2_near_rp = p2_near["Rxn_60"] / p2_near["Pen_60"].replace(0, np.nan)
    p2_above_rp = p2_above["Rxn_60"] / p2_above["Pen_60"].replace(0, np.nan)

    nm_lines.append("## Mean R/P @60 (Reaction / Penetration)")
    nm_lines.append(f"| Group | Mean R/P @60 | Median R/P @60 | N |")
    nm_lines.append(f"|-------|-------------|----------------|---|")
    nm_lines.append(f"| P1 near-miss | {p1_near_rp.mean():.3f} | {p1_near_rp.median():.3f} | {p1_near_rp.notna().sum()} |")
    nm_lines.append(f"| P1 above | {p1_above_rp.mean():.3f} | {p1_above_rp.median():.3f} | {p1_above_rp.notna().sum()} |")
    nm_lines.append(f"| P2 near-miss | {p2_near_rp.mean():.3f} | {p2_near_rp.median():.3f} | {p2_near_rp.notna().sum()} |")
    nm_lines.append(f"| P2 above | {p2_above_rp.mean():.3f} | {p2_above_rp.median():.3f} | {p2_above_rp.notna().sum()} |")
    nm_lines.append("")

# Simulate PF at threshold - 1 and threshold - 2 for winner's exits
nm_lines.append("## Threshold Sensitivity Simulation (winner's frozen exits: seg3_ModeB)")
nm_lines.append("Using seg3_A-Cal/ModeB exit params (stop=190, target=80, time_cap=120)")
nm_lines.append("")

winner_ep = seg_params["seg3_A-Cal"]["groups"]["ModeB"]["exit_params"]
winner_filters = seg_params["seg3_A-Cal"]["groups"]["ModeB"]["filters"]

for delta_label, delta in [("Threshold (baseline)", 0), ("Threshold - 1pt", -1), ("Threshold - 2pt", -2)]:
    shifted_thresh = ACAL_THRESHOLD + delta

    pnls_shifted = []
    for period_label, pdf in [("P2a", p2a), ("P2b", p2b)]:
        # Recompute seg3 with shifted threshold
        edge_mask = pdf["TouchType"].isin(["DEMAND_EDGE", "SUPPLY_EDGE"])
        above = pdf["score_acal"] >= shifted_thresh
        ct = pdf["TrendLabel"] == "CT"
        mode_b = pdf[above & edge_mask & ct]

        filtered = apply_filters(mode_b, winner_filters)
        subset = filtered.sort_values("RotBarIndex")
        in_trade_until = -1

        for _, row in subset.iterrows():
            rbi = int(row["RotBarIndex"])
            entry_bar = rbi + 1
            if entry_bar <= in_trade_until:
                continue
            direction = 1 if "DEMAND" in str(row["TouchType"]) else -1
            result = sim_trade_detailed(
                entry_bar, direction,
                winner_ep["stop"], winner_ep["target"],
                winner_ep["be_trigger"], winner_ep["trail_trigger"],
                winner_ep["time_cap"])
            if result:
                pnls_shifted.append(result["pnl_raw"])
                in_trade_until = entry_bar + result["bars_held"] - 1

    if pnls_shifted:
        gp = sum(p - COST_TICKS for p in pnls_shifted if p - COST_TICKS > 0)
        gl = sum(abs(p - COST_TICKS) for p in pnls_shifted if p - COST_TICKS < 0)
        pf = gp / gl if gl > 0 else (float("inf") if gp > 0 else 0)
        wr = sum(1 for p in pnls_shifted if p - COST_TICKS > 0) / len(pnls_shifted) * 100
        nm_lines.append(f"| {delta_label} (>={shifted_thresh:.2f}) | {len(pnls_shifted)} trades | PF@3t={pf:.3f} | WR={wr:.1f}% |")
    else:
        nm_lines.append(f"| {delta_label} (>={shifted_thresh:.2f}) | 0 trades | — | — |")

nm_lines.append("")

# Cliff vs slope assessment
nm_lines.append("## Cliff vs Slope Assessment")
nm_lines.append("If PF degrades sharply with -1pt: CLIFF (threshold is load-bearing).")
nm_lines.append("If PF degrades gradually: SLOPE (threshold has margin).")

nm_path = DIAG_DIR / "near_miss_analysis.md"
with open(nm_path, "w", encoding="utf-8") as f:
    f.write("\n".join(nm_lines))
print(f"  ✓ Saved to {nm_path.name}")


# ══════════════════════════════════════════════════════════════════════
# ITEM 4: Time-of-Day Distribution (seg3 ModeB)
# ══════════════════════════════════════════════════════════════════════

print("\n" + "=" * 72)
print("ITEM 4: Time-of-Day Distribution — seg3_ModeB (58 trades)")
print("=" * 72)

winner_trades = trades_df[trades_df["seg_model_group"] == "seg3_ModeB"].copy()

# Parse hour from datetime
def extract_hour(dt_str):
    try:
        dt = datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S")
        return dt.hour
    except Exception:
        return -1

winner_trades["hour"] = winner_trades["datetime"].apply(extract_hour)

tod_lines = []
tod_lines.append("# Time-of-Day Distribution — seg3_A-Cal/ModeB (Winner)")
tod_lines.append(f"Generated: {datetime.now().isoformat()}")
tod_lines.append(f"Total trades: {len(winner_trades)}")
tod_lines.append("")

# Hourly breakdown
tod_lines.append("## Hourly Breakdown")
tod_lines.append("")
tod_lines.append("| Hour (ET) | Trades | Win% | Mean PnL (3t) | Mean MFE | Mean MAE | PF@3t |")
tod_lines.append("|-----------|--------|------|---------------|----------|----------|-------|")

for hour in sorted(winner_trades["hour"].unique()):
    if hour < 0:
        continue
    h_trades = winner_trades[winner_trades["hour"] == hour]
    n = len(h_trades)
    if n == 0:
        continue
    wins = (h_trades["pnl_ticks"] > 0).sum()
    wr = wins / n * 100
    mean_pnl = h_trades["pnl_ticks"].mean()
    mean_mfe = h_trades["mfe_ticks"].mean()
    mean_mae = h_trades["mae_ticks"].mean()
    gp = h_trades[h_trades["pnl_ticks"] > 0]["pnl_ticks"].sum()
    gl = abs(h_trades[h_trades["pnl_ticks"] < 0]["pnl_ticks"].sum())
    pf = gp / gl if gl > 0 else (float("inf") if gp > 0 else 0)

    hour_label = f"{hour:02d}:00"
    tod_lines.append(f"| {hour_label} | {n} | {wr:.0f}% | {mean_pnl:.1f} | {mean_mfe:.1f} | {mean_mae:.1f} | {pf:.2f} |")

# Session summary
tod_lines.append("")
tod_lines.append("## Session Summary")
tod_lines.append("")

def classify_session(h):
    if 9 <= h < 12:
        return "RTH Morning (09-12)"
    elif 12 <= h < 16:
        return "RTH Afternoon (12-16)"
    elif 16 <= h < 18:
        return "RTH Close (16-18)"
    elif h >= 18 or h < 9:
        return "ETH/Overnight"
    return "Other"

winner_trades["session"] = winner_trades["hour"].apply(classify_session)

tod_lines.append("| Session | Trades | Win% | Mean PnL | PF@3t |")
tod_lines.append("|---------|--------|------|----------|-------|")

for sess in ["ETH/Overnight", "RTH Morning (09-12)", "RTH Afternoon (12-16)", "RTH Close (16-18)"]:
    s_trades = winner_trades[winner_trades["session"] == sess]
    if len(s_trades) == 0:
        continue
    n = len(s_trades)
    wr = (s_trades["pnl_ticks"] > 0).sum() / n * 100
    mean_pnl = s_trades["pnl_ticks"].mean()
    gp = s_trades[s_trades["pnl_ticks"] > 0]["pnl_ticks"].sum()
    gl = abs(s_trades[s_trades["pnl_ticks"] < 0]["pnl_ticks"].sum())
    pf = gp / gl if gl > 0 else (float("inf") if gp > 0 else 0)
    tod_lines.append(f"| {sess} | {n} | {wr:.0f}% | {mean_pnl:.1f} | {pf:.2f} |")

# Direction × session
tod_lines.append("")
tod_lines.append("## Direction x Session")
tod_lines.append("")
tod_lines.append("| Session | Dir | Trades | Win% | Mean PnL |")
tod_lines.append("|---------|-----|--------|------|----------|")

for sess in ["ETH/Overnight", "RTH Morning (09-12)", "RTH Afternoon (12-16)"]:
    for d in ["LONG", "SHORT"]:
        sub = winner_trades[(winner_trades["session"] == sess) & (winner_trades["direction"] == d)]
        if len(sub) == 0:
            continue
        n = len(sub)
        wr = (sub["pnl_ticks"] > 0).sum() / n * 100
        mean_pnl = sub["pnl_ticks"].mean()
        tod_lines.append(f"| {sess} | {d} | {n} | {wr:.0f}% | {mean_pnl:.1f} |")

# P2a vs P2b
tod_lines.append("")
tod_lines.append("## P2a vs P2b Stability")
tod_lines.append("")
tod_lines.append("| Period | Trades | Win% | Mean PnL | PF@3t |")
tod_lines.append("|--------|--------|------|----------|-------|")
for per in ["P2a", "P2b"]:
    p_trades = winner_trades[winner_trades["period"] == per]
    if len(p_trades) == 0:
        continue
    n = len(p_trades)
    wr = (p_trades["pnl_ticks"] > 0).sum() / n * 100
    mean_pnl = p_trades["pnl_ticks"].mean()
    gp = p_trades[p_trades["pnl_ticks"] > 0]["pnl_ticks"].sum()
    gl = abs(p_trades[p_trades["pnl_ticks"] < 0]["pnl_ticks"].sum())
    pf = gp / gl if gl > 0 else (float("inf") if gp > 0 else 0)
    tod_lines.append(f"| {per} | {n} | {wr:.0f}% | {mean_pnl:.1f} | {pf:.2f} |")

tod_path = DIAG_DIR / "time_of_day_distribution.md"
with open(tod_path, "w", encoding="utf-8") as f:
    f.write("\n".join(tod_lines))
print(f"  ✓ Saved to {tod_path.name}")


# ══════════════════════════════════════════════════════════════════════
# FINAL SUMMARY
# ══════════════════════════════════════════════════════════════════════

print("\n" + "=" * 72)
print("DIAGNOSTICS COMPLETE")
print("=" * 72)
print(f"  ITEM 1: {trades_csv_path.name} ({len(trades_df)} trades)")
print(f"  ITEM 2: {losing_path.name}")
print(f"  ITEM 3: {nm_path.name}")
print(f"  ITEM 4: {tod_path.name}")
print("=" * 72)
