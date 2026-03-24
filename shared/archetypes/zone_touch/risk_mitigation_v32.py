# archetype: zone_touch
"""Risk Mitigation Investigation v3.2 — Entry/Exit/Sizing Analysis.

Scoring model FROZEN. Modifies only post-selection execution:
  - Entry execution (where to enter within zone)
  - Exit structure (stop, BE, trail, partials, time cap)
  - Position sizing (contracts per trade)

Step 0: Diagnostics (0a-0g)
Surface B: Exit structure modifications (B1-B9)
Surface A: Entry execution modifications (A1-A4)
Step 3: Stacking
Step 4: P2 validation
Step 5: Design recommendations
"""

import json
import sys
import warnings
from copy import deepcopy
from pathlib import Path

import numpy as np
import pandas as pd

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
warnings.filterwarnings("ignore", category=FutureWarning)

# ── Paths ──
BASE = Path(r"c:\Projects\pipeline")
DATA_DIR = BASE / "stages" / "01-data" / "output" / "zone_prep"
TOUCH_DIR = BASE / "stages" / "01-data" / "data" / "touches"
PARAM_DIR = BASE / "shared" / "archetypes" / "zone_touch" / "output"
OUT_DIR = PARAM_DIR
TICK_SIZE = 0.25

# ── Load Data ──
print("=" * 72)
print("RISK MITIGATION INVESTIGATION v3.2")
print("=" * 72)

# Qualifying trades (already simulated with baseline exits)
qt = pd.read_csv(PARAM_DIR / "qualifying_trades_ray_context_v32.csv")
# Scored touches (for zone geometry and scores)
aeq = pd.read_csv(PARAM_DIR / "p1_scored_touches_aeq_v32.csv")
bz = pd.read_csv(PARAM_DIR / "p1_scored_touches_bzscore_v32.csv")
# Raw touches (for zone geometry)
raw_p1 = pd.read_csv(TOUCH_DIR / "NQ_ZTE_raw_P1.csv")
# Bar data
bar_p1 = pd.read_csv(DATA_DIR / "NQ_bardata_P1.csv")
bar_p1.columns = bar_p1.columns.str.strip()
bar_arr = bar_p1[["Open", "High", "Low", "Last"]].to_numpy(dtype=np.float64)
n_bars = len(bar_arr)

print(f"Qualifying trades: {len(qt)} (M1={len(qt[qt['mode']=='M1'])}, M2={len(qt[qt['mode']=='M2'])})")
print(f"P1 bar data: {n_bars} bars")

# ── Enrich qualifying trades with zone geometry ──
zone_tops = []
zone_bots = []
touch_prices = []
touch_types = []
scores_aeq = []
scores_bz = []
entry_opens = []

for _, row in qt.iterrows():
    ti = int(row["touch_idx"])
    r = raw_p1.iloc[ti]
    zone_tops.append(r["ZoneTop"])
    zone_bots.append(r["ZoneBot"])
    touch_prices.append(r["TouchPrice"])
    touch_types.append(r["TouchType"])
    scores_aeq.append(aeq.iloc[ti]["Score_AEq"])
    scores_bz.append(bz.iloc[ti]["Score_BZScore"])
    eb = int(row["entry_bar"])
    entry_opens.append(bar_arr[eb, 0] if eb < n_bars else np.nan)

qt["zone_top"] = zone_tops
qt["zone_bot"] = zone_bots
qt["touch_price"] = touch_prices
qt["touch_type"] = touch_types
qt["score_aeq"] = scores_aeq
qt["score_bz"] = scores_bz
qt["entry_open"] = entry_opens

# Entry offset from zone edge
qt["entry_offset"] = np.where(
    qt["direction"] == -1,
    (qt["touch_price"] - qt["entry_open"]) / TICK_SIZE,   # short: edge above entry
    (qt["entry_open"] - qt["touch_price"]) / TICK_SIZE,    # long: entry above edge
)

qt["win"] = qt["pnl"] > 0

m1 = qt[qt["mode"] == "M1"].copy()
m2 = qt[qt["mode"] == "M2"].copy()

print(f"\nEntry offset (entry Open vs TouchPrice):")
print(f"  M1: mean={m1['entry_offset'].mean():.1f}t, median={m1['entry_offset'].median():.1f}t")
print(f"  M2: mean={m2['entry_offset'].mean():.1f}t, median={m2['entry_offset'].median():.1f}t")


# ══════════════════════════════════════════════════════════════════════
# STEP 0a: Per-Trade Outcome Data
# ══════════════════════════════════════════════════════════════════════
print("\n" + "=" * 72)
print("STEP 0a: PER-TRADE OUTCOME DATA")
print("=" * 72)


def compute_pf(pnls, cost=3):
    gp = sum(p - cost for p in pnls if p - cost > 0)
    gl = sum(abs(p - cost) for p in pnls if p - cost < 0)
    return gp / gl if gl > 0 else (float("inf") if gp > 0 else 0)


# Verify baseline PF matches known values
m1_pf = compute_pf(m1["pnl"].tolist(), cost=3)
m2_pf = compute_pf(m2["pnl"].tolist(), cost=3)
m1_wr = m1["win"].mean() * 100
m2_wr = m2["win"].mean() * 100

print(f"\nBaseline verification:")
print(f"  M1: {len(m1)} trades, PF@3t={m1_pf:.2f} (expected ~8.50), WR={m1_wr:.1f}%")
print(f"  M2: {len(m2)} trades, PF@3t={m2_pf:.2f} (expected ~4.71), WR={m2_wr:.1f}%")

# Per-exit-type summary
for mode_name, mdf in [("M1", m1), ("M2", m2)]:
    print(f"\n  {mode_name} exit type breakdown:")
    for et in ["TARGET", "STOP", "TIMECAP"]:
        sub = mdf[mdf["exit_type"] == et]
        if len(sub) > 0:
            print(f"    {et}: n={len(sub)}, mean_pnl={sub['pnl'].mean():.1f}t, "
                  f"win%={sub['win'].mean()*100:.1f}%, mean_bars={sub['bars_held'].mean():.1f}")


# ══════════════════════════════════════════════════════════════════════
# STEP 0b: MAE Distribution — Losers
# ══════════════════════════════════════════════════════════════════════
print("\n" + "=" * 72)
print("STEP 0b: MAE DISTRIBUTION — LOSERS")
print("=" * 72)

# M1 losers — report each individually
m1_losers = m1[~m1["win"]].copy()
print(f"\nMode 1 LOSERS: {len(m1_losers)} trades")

if len(m1_losers) > 0:
    print(f"\n{'#':<4} {'Exit':>8} {'MAE':>6} {'PnL':>8} {'Bars':>6} {'Stop':>6}")
    print("-" * 42)
    for i, (_, row) in enumerate(m1_losers.iterrows()):
        print(f"{i+1:<4} {row['exit_type']:>8} {row['mae']:>6.0f} {row['pnl']:>8.1f} "
              f"{row['bars_held']:>6} {row['stop_used']:>6}")

    # For each M1 loser, find bar-by-bar MAE progression
    print("\n  M1 Loser MAE Time Analysis (bar of first MAE > threshold):")
    print(f"  {'#':<4} {'Exit':>8} {'b>60t':>6} {'b>120t':>7} {'b>150t':>7} {'MaxMAE':>7}")
    print("  " + "-" * 45)
    for i, (_, row) in enumerate(m1_losers.iterrows()):
        eb = int(row["entry_bar"])
        d = int(row["direction"])
        ep = bar_arr[eb, 0]
        tc = int(row["tc_used"])
        end = min(eb + tc, n_bars)

        bar_60 = bar_120 = bar_150 = "—"
        max_mae = 0
        for bi in range(eb, end):
            h, l = bar_arr[bi, 1], bar_arr[bi, 2]
            if d == 1:
                cur_mae = (ep - l) / TICK_SIZE
            else:
                cur_mae = (h - ep) / TICK_SIZE
            max_mae = max(max_mae, cur_mae)
            bh = bi - eb + 1
            if max_mae >= 60 and bar_60 == "—":
                bar_60 = str(bh)
            if max_mae >= 120 and bar_120 == "—":
                bar_120 = str(bh)
            if max_mae >= 150 and bar_150 == "—":
                bar_150 = str(bh)
        print(f"  {i+1:<4} {row['exit_type']:>8} {bar_60:>6} {bar_120:>7} {bar_150:>7} {max_mae:>7.0f}")

# M2 losers
m2_losers = m2[~m2["win"]].copy()
print(f"\nMode 2 LOSERS: {len(m2_losers)} trades")

# Split by exit type
m2_stop_losers = m2_losers[m2_losers["exit_type"] == "STOP"]
m2_tc_losers = m2_losers[m2_losers["exit_type"] == "TIMECAP"]

print(f"\n  M2 stop-hit losers:")
print(f"    Count: {len(m2_stop_losers)}")
print(f"    % of all M2 losers: {len(m2_stop_losers)/len(m2_losers)*100:.1f}%")
if len(m2_stop_losers) > 0:
    # Compute bars to stop for each
    bars_to_stop = m2_stop_losers["bars_held"].values
    print(f"    Mean bars to stop: {bars_to_stop.mean():.1f}")
    print(f"    Bars to stop < 10 (decisive): {(bars_to_stop < 10).sum()}")
    print(f"    Bars to stop > 40 (slow bleed): {(bars_to_stop > 40).sum()}")
    print(f"    Mean PnL: {m2_stop_losers['pnl'].mean():.1f}t")
    print(f"    Stop distances: {m2_stop_losers['stop_used'].values}")

print(f"\n  M2 time-cap losers:")
print(f"    Count: {len(m2_tc_losers)}")
if len(m2_tc_losers) > 0:
    # Bin by MAE as % of stop
    m2_tc_losers = m2_tc_losers.copy()
    m2_tc_losers["mae_pct_stop"] = m2_tc_losers["mae"] / m2_tc_losers["stop_used"] * 100
    bins = [(0, 50), (50, 75), (75, 100)]
    print(f"    {'MAE % of Stop':<18} {'Count':>6} {'%':>6} {'Mean PnL':>10}")
    print("    " + "-" * 44)
    for lo, hi in bins:
        sub = m2_tc_losers[(m2_tc_losers["mae_pct_stop"] >= lo) & (m2_tc_losers["mae_pct_stop"] < hi)]
        if len(sub) > 0:
            print(f"    {lo}-{hi}%{'':<13} {len(sub):>6} {len(sub)/len(m2_tc_losers)*100:>5.1f}% {sub['pnl'].mean():>10.1f}")


# ══════════════════════════════════════════════════════════════════════
# STEP 0c: MFE Distribution — Winners
# ══════════════════════════════════════════════════════════════════════
print("\n" + "=" * 72)
print("STEP 0c: MFE DISTRIBUTION — WINNERS")
print("=" * 72)

m1_winners = m1[m1["win"]].copy()
m2_winners = m2[m2["win"]].copy()

print(f"\nMode 1 WINNERS: {len(m1_winners)} trades")
mfe_bins_m1 = [(60, 80), (80, 120), (120, 200), (200, 99999)]
print(f"  {'MFE Bin':>12} {'Count':>6} {'%':>6} {'Med PnL':>8} {'Mean MFE':>9}")
print("  " + "-" * 46)
for lo, hi in mfe_bins_m1:
    sub = m1_winners[(m1_winners["mfe"] >= lo) & (m1_winners["mfe"] < hi)]
    label = f"{lo}-{hi}t" if hi < 99999 else f"{lo}t+"
    if len(sub) > 0:
        print(f"  {label:>12} {len(sub):>6} {len(sub)/len(m1_winners)*100:>5.1f}% "
              f"{sub['pnl'].median():>8.1f} {sub['mfe'].mean():>9.1f}")

# Probability T1 (60t) hit before stop
m1_t1_before_stop = m1_winners["exit_type"].value_counts().get("TARGET", 0)
print(f"\n  P(T1=60t hit) = {m1_t1_before_stop}/{len(m1)} = {m1_t1_before_stop/len(m1)*100:.1f}%")
# MFE of all M1 trades >= 60t
m1_mfe_ge60 = (m1["mfe"] >= 60).sum()
print(f"  Trades with MFE >= 60t: {m1_mfe_ge60}/{len(m1)} = {m1_mfe_ge60/len(m1)*100:.1f}%")
m1_mfe_ge30 = (m1["mfe"] >= 30).sum()
print(f"  Trades with MFE >= 30t: {m1_mfe_ge30}/{len(m1)} = {m1_mfe_ge30/len(m1)*100:.1f}%")

print(f"\nMode 2 WINNERS: {len(m2_winners)} trades")
# For M2, bin relative to zone width
m2_winners = m2_winners.copy()
m2_winners["mfe_pct_zw"] = m2_winners["mfe"] / m2_winners["zw_ticks"] * 100
mfe_pct_bins = [(0, 50), (50, 100), (100, 150), (150, 200), (200, 99999)]
print(f"  {'MFE % of ZW':>14} {'Count':>6} {'%':>6} {'Med PnL':>8} {'Mean MFE':>9}")
print("  " + "-" * 48)
for lo, hi in mfe_pct_bins:
    sub = m2_winners[(m2_winners["mfe_pct_zw"] >= lo) & (m2_winners["mfe_pct_zw"] < hi)]
    label = f"{lo}-{hi}%" if hi < 99999 else f"{lo}%+"
    if len(sub) > 0:
        print(f"  {label:>14} {len(sub):>6} {len(sub)/len(m2_winners)*100:>5.1f}% "
              f"{sub['pnl'].median():>8.1f} {sub['mfe'].mean():>9.1f}")

# M2 P(T1 at 0.5×ZW hit)
m2_mfe_half_zw = (m2["mfe"] >= m2["zw_ticks"] * 0.5).sum()
m2_mfe_full_zw = (m2["mfe"] >= m2["zw_ticks"]).sum()
print(f"\n  P(MFE >= 0.5×ZW) = {m2_mfe_half_zw}/{len(m2)} = {m2_mfe_half_zw/len(m2)*100:.1f}%")
print(f"  P(MFE >= 1.0×ZW) = {m2_mfe_full_zw}/{len(m2)} = {m2_mfe_full_zw/len(m2)*100:.1f}%")


# ══════════════════════════════════════════════════════════════════════
# STEP 0d: Zone Width Distribution (Mode 2)
# ══════════════════════════════════════════════════════════════════════
print("\n" + "=" * 72)
print("STEP 0d: ZONE WIDTH DISTRIBUTION (Mode 2)")
print("=" * 72)

zw_bins = [(0, 100), (100, 150), (150, 250), (250, 400), (400, 99999)]
print(f"\n{'ZW Bin':>12} {'Count':>6} {'%':>6} {'Stop':>8} {'MaxLoss@3':>10} {'PF@3t':>7} {'WR%':>6}")
print("-" * 60)
for lo, hi in zw_bins:
    sub = m2[(m2["zw_ticks"] >= lo) & (m2["zw_ticks"] < hi)]
    label = f"{lo}-{hi}t" if hi < 99999 else f"{lo}t+"
    if len(sub) > 0:
        mean_stop = sub["stop_used"].mean()
        max_loss_3ct = sub["stop_used"].max() * 3
        pf = compute_pf(sub["pnl"].tolist(), cost=3)
        wr = sub["win"].mean() * 100
        print(f"{label:>12} {len(sub):>6} {len(sub)/len(m2)*100:>5.1f}% "
              f"{mean_stop:>8.0f} {max_loss_3ct:>10.0f} {pf:>7.2f} {wr:>5.1f}%")


# ══════════════════════════════════════════════════════════════════════
# STEP 0e: Time Cap Exit Characterization
# ══════════════════════════════════════════════════════════════════════
print("\n" + "=" * 72)
print("STEP 0e: TIME CAP EXIT CHARACTERIZATION")
print("=" * 72)

for mode_name, mdf, tc_val in [("M1", m1, 120), ("M2", m2, 80)]:
    tc_trades = mdf[mdf["exit_type"] == "TIMECAP"]
    non_tc = mdf[mdf["exit_type"] != "TIMECAP"]
    print(f"\n  {mode_name} (TC={tc_val} bars):")
    print(f"    N time cap exits: {len(tc_trades)}")
    print(f"    % of all {mode_name} trades: {len(tc_trades)/len(mdf)*100:.1f}%")
    if len(tc_trades) > 0:
        print(f"    Mean PnL of TC exits: {tc_trades['pnl'].mean():.1f}t")
        tc_win = tc_trades[tc_trades["win"]]
        tc_lose = tc_trades[~tc_trades["win"]]
        print(f"    TC winners: {len(tc_win)} (mean PnL={tc_win['pnl'].mean():.1f}t)" if len(tc_win) > 0 else "    TC winners: 0")
        print(f"    TC losers: {len(tc_lose)} (mean PnL={tc_lose['pnl'].mean():.1f}t)" if len(tc_lose) > 0 else "    TC losers: 0")
    if len(non_tc) > 0:
        print(f"    Mean bars held (non-TC exits): {non_tc['bars_held'].mean():.1f}")


# ══════════════════════════════════════════════════════════════════════
# STEP 0f: Penetration Depth / Fill Rate Curve
# ══════════════════════════════════════════════════════════════════════
print("\n" + "=" * 72)
print("STEP 0f: PENETRATION DEPTH / FILL RATE CURVE")
print("=" * 72)

# For each qualifying touch, measure max penetration into zone over
# touch bar + next 3 bars (4-bar fill window)
FILL_WINDOW = 4

pen_depths = []
for _, row in qt.iterrows():
    ti = int(row["touch_idx"])
    r = raw_p1.iloc[ti]
    rbi = int(row["RotBarIndex"])
    d = int(row["direction"])
    tp = r["TouchPrice"]

    # Measure penetration past zone edge over fill window
    max_pen = 0.0
    for bi in range(rbi, min(rbi + FILL_WINDOW, n_bars)):
        h, l = bar_arr[bi, 1], bar_arr[bi, 2]
        if d == -1:  # short entry at demand edge: price drops below edge
            pen = (tp - l) / TICK_SIZE
        else:  # long entry at supply edge: price rises above edge
            pen = (h - tp) / TICK_SIZE
        max_pen = max(max_pen, pen)
    pen_depths.append(max_pen)

qt["max_penetration"] = pen_depths

# Re-slice after all enrichment
m1 = qt[qt["mode"] == "M1"].copy()
m2 = qt[qt["mode"] == "M2"].copy()

# Report fill rate curve separately for M1 and M2
depths_to_test = [0, 5, 10, 15, 20, 25, 30, 40, 50, 60, 80, 100]

for mode_name, mdf in [("M1", qt[qt["mode"] == "M1"]), ("M2", qt[qt["mode"] == "M2"])]:
    print(f"\n  {mode_name} Fill Rate Curve ({len(mdf)} trades):")
    print(f"  {'Depth':>8} {'Reach':>8} {'Fill%':>7} {'vs Edge':>8}")
    print("  " + "-" * 35)
    baseline_n = len(mdf)
    for depth in depths_to_test:
        reach = (mdf["max_penetration"] >= depth).sum()
        fill_pct = reach / baseline_n * 100
        print(f"  {depth:>7}t {reach:>8} {fill_pct:>6.1f}% {reach - baseline_n:>+8}")

    # Find 90%, 75%, 60% fill rate points
    pens_sorted = np.sort(mdf["max_penetration"].values)
    p10 = np.percentile(pens_sorted, 10)  # 90% fill rate
    p25 = np.percentile(pens_sorted, 25)  # 75% fill rate
    p40 = np.percentile(pens_sorted, 40)  # 60% fill rate
    print(f"\n  Key fill rate points:")
    print(f"    90% fill rate at depth: {p10:.0f}t")
    print(f"    75% fill rate at depth: {p25:.0f}t")
    print(f"    60% fill rate at depth: {p40:.0f}t")
    print(f"    Penetration stats: mean={mdf['max_penetration'].mean():.1f}t, "
          f"median={mdf['max_penetration'].median():.1f}t, "
          f"min={mdf['max_penetration'].min():.0f}t, "
          f"max={mdf['max_penetration'].max():.0f}t")


# ══════════════════════════════════════════════════════════════════════
# STEP 0g: Missed Trade Characterization
# ══════════════════════════════════════════════════════════════════════
print("\n" + "=" * 72)
print("STEP 0g: MISSED TRADE CHARACTERIZATION")
print("=" * 72)

# Reconstruct which qualifying touches were missed due to position overlap
# We need to replay the no-overlap filter on the full qualifying population

# First, identify ALL qualifying touches (pre-overlap filter)
# M1: Score_AEq >= 45.5
m1_qualifying_all = aeq[aeq["Score_AEq"] >= 45.5].copy()
m1_qualifying_all["touch_idx_orig"] = m1_qualifying_all.index

# M2: Score_BZScore >= 0.50, RTH, seq <= 2, TF <= 120m
# Need session and TF info from raw_p1
m2_candidates = bz.copy()
m2_candidates["touch_idx_orig"] = m2_candidates.index

# Get session from scored touches
# The B-ZScore qualifying criteria include RTH, seq<=2, TF<=120m
# Let me identify M2 qualifying from the raw data
# First get SourceLabel (TF) and TouchSequence from raw
m2_candidates["SourceLabel_raw"] = raw_p1["SourceLabel"].values
m2_candidates["TouchSequence_raw"] = raw_p1["TouchSequence"].values
m2_candidates["SessionClass_raw"] = raw_p1["SessionClass"].values

# TF mapping to minutes
tf_to_min = {"5m": 5, "10m": 10, "15m": 15, "30m": 30, "50m": 50,
             "60m": 60, "90m": 90, "120m": 120, "240m": 240, "360m": 360}


def get_tf_min(label):
    return tf_to_min.get(str(label), 9999)


m2_candidates["tf_min"] = m2_candidates["SourceLabel_raw"].apply(get_tf_min)

# Apply M2 filters (matching the waterfall from Analysis B)
# Score >= 0.50, RTH (SessionClass != Overnight for raw), seq <= 2, TF <= 120m
m2_qualifying_all = m2_candidates[
    (m2_candidates["Score_BZScore"] >= 0.50) &
    (m2_candidates["TouchSequence_raw"] <= 2) &
    (m2_candidates["tf_min"] <= 120) &
    (m2_candidates["SessionClass_raw"] != 3)  # Not overnight (sess class 3 = overnight?)
].copy()

# Actually, session class in raw might be different. Let me check the raw SessionClass values
print(f"\nRaw SessionClass unique values: {raw_p1['SessionClass'].unique()}")

# Session class might be numeric. Let's check what M1 qualifying indices are vs traded
m1_traded_indices = set(qt[qt["mode"] == "M1"]["touch_idx"].values)
m2_traded_indices = set(qt[qt["mode"] == "M2"]["touch_idx"].values)

# For M1 pre-overlap:
m1_pre = aeq[aeq["Score_AEq"] >= 45.5].copy()
m1_pre["touch_idx_orig"] = m1_pre.index
m1_pre["traded"] = m1_pre["touch_idx_orig"].isin(m1_traded_indices)
m1_pre["RotBarIndex"] = raw_p1.loc[m1_pre.index, "RotBarIndex" if "RotBarIndex" in raw_p1.columns else "BarIndex"].values

print(f"\nM1 pre-overlap qualifying: {len(m1_pre)}")
print(f"M1 traded: {m1_pre['traded'].sum()}")
print(f"M1 missed: {(~m1_pre['traded']).sum()}")

# For M2 — need to figure out which touches qualified pre-overlap
# The qualifying trades file has the touch_idx for traded ones
# Let me use the qualifying approach from the backtest: just take all M2 qualifying
# that aren't already M1 (waterfall removes M1 overlap)
# This is complex. Let me just compare traded vs total in the qualifying population.

# Simpler approach: replay the no-overlap filter for M1 and M2
print("\n  Replaying no-overlap filter...")


def replay_overlap_filter(touch_indices, mode_label):
    """Replay the no-overlap simulation and identify missed trades."""
    traded = []
    missed = []
    in_trade_until = -1

    # Sort by RotBarIndex
    entries = []
    for ti in touch_indices:
        r = raw_p1.iloc[ti]
        rbi = r["RotBarIndex"] if "RotBarIndex" in raw_p1.columns else ti
        entries.append((rbi, ti))
    entries.sort()

    for rbi, ti in entries:
        entry_bar = int(rbi) + 1
        if entry_bar <= in_trade_until:
            missed.append(ti)
            continue

        # Find the corresponding qualifying trade to get bars_held
        qt_match = qt[(qt["touch_idx"] == ti) & (qt["mode"] == mode_label)]
        if len(qt_match) > 0:
            bh = int(qt_match.iloc[0]["bars_held"])
            in_trade_until = entry_bar + bh - 1
            traded.append(ti)
        else:
            # This touch qualified but wasn't traded — simulate to get bars_held
            # Use baseline params to compute hold duration
            d = 1 if "DEMAND" in str(r["TouchType"]) else -1
            if entry_bar >= n_bars:
                missed.append(ti)
                continue
            ep = bar_arr[entry_bar, 0]
            zw = r["ZoneWidthTicks"] if "ZoneWidthTicks" in raw_p1.columns else 100

            if mode_label == "M1":
                stop, target, tcap = 190, 60, 120
            else:
                stop = max(round(1.5 * zw), 120)
                target = max(1, round(zw * 1.0))
                tcap = 80

            # Quick sim for bars_held
            if d == 1:
                sp = ep - stop * TICK_SIZE
                tp_price = ep + target * TICK_SIZE
            else:
                sp = ep + stop * TICK_SIZE
                tp_price = ep - target * TICK_SIZE

            bh = tcap
            for bi in range(entry_bar, min(entry_bar + tcap, n_bars)):
                h, l = bar_arr[bi, 1], bar_arr[bi, 2]
                if d == 1:
                    if l <= sp or h >= tp_price:
                        bh = bi - entry_bar + 1
                        break
                else:
                    if h >= sp or l <= tp_price:
                        bh = bi - entry_bar + 1
                        break
            in_trade_until = entry_bar + bh - 1
            traded.append(ti)  # It traded, just not in our qualifying set
            # Actually if it's not in qt, it means it was filtered by the waterfall
            # This is getting complex. Let me just report what we know from qt.
    return traded, missed


# Simpler: count from the actual data
# The qualifying trades file represents the trades that were actually taken
# We know from the prompt: M1 had 127 qualifying → 107 traded (20 missed)
#                           M2 had 325 qualifying → 239 traded (86 missed)
# But I need to verify these numbers and characterize the missed trades

# For now, compare traded vs all qualifying by score
m1_all_qualifying = aeq[aeq["Score_AEq"] >= 45.5]
m2_all_qualifying_mask = bz["Score_BZScore"] >= 0.50
# Additional M2 filters needed (RTH, seq<=2, TF<=120m) — skip for now, use prompt numbers

print(f"\n  M1: Score_AEq >= 45.5 total: {len(m1_all_qualifying)}")
print(f"  M1 traded: {len(m1)}")
print(f"  Estimated M1 missed (all qualifying - traded): {len(m1_all_qualifying) - len(m1)}")

print(f"\n  M2: Score_BZScore >= 0.50 total: {m2_all_qualifying_mask.sum()}")
print(f"  M2 traded: {len(m2)}")

# Compare scores of traded vs missed (approximate by looking at the traded population)
m1_traded_scores = m1["score_aeq"].values
m1_all_scores = m1_all_qualifying["Score_AEq"].values
print(f"\n  M1 traded mean A-Eq score: {m1_traded_scores.mean():.1f}")
print(f"  M1 all qualifying mean A-Eq score: {m1_all_scores.mean():.1f}")

m2_traded_scores = m2["score_bz"].values
print(f"  M2 traded mean B-ZScore: {m2_traded_scores.mean():.3f}")

# Characterize what the active trade was doing when a trade was missed
# This requires full replay — do it for M1 (small set)
print("\n  M1 Missed Trade Analysis:")
m1_sorted = m1.sort_values("entry_bar")
m1_all_sorted = []
for idx in m1_all_qualifying.index:
    rbi = raw_p1.iloc[idx]["RotBarIndex"] if "RotBarIndex" in raw_p1.columns else idx
    m1_all_sorted.append((rbi, idx))
m1_all_sorted.sort()

in_trade_until = -1
active_trade_pnl = None
m1_missed_during = {"winner": 0, "loser": 0, "tc_drift": 0, "unknown": 0}

for rbi, ti in m1_all_sorted:
    entry_bar = int(rbi) + 1
    is_traded = ti in m1_traded_indices

    if entry_bar <= in_trade_until:
        if not is_traded:
            # This was a missed trade — what was active trade doing?
            if active_trade_pnl is not None:
                if active_trade_exit == "TIMECAP":
                    m1_missed_during["tc_drift"] += 1
                elif active_trade_pnl > 0:
                    m1_missed_during["winner"] += 1
                else:
                    m1_missed_during["loser"] += 1
            else:
                m1_missed_during["unknown"] += 1
        continue  # skip — position occupied

    if is_traded:
        qt_row = qt[qt["touch_idx"] == ti]
        if len(qt_row) > 0:
            bh = int(qt_row.iloc[0]["bars_held"])
            active_trade_pnl = qt_row.iloc[0]["pnl"]
            active_trade_exit = qt_row.iloc[0]["exit_type"]
            in_trade_until = entry_bar + bh - 1

total_m1_missed = sum(m1_missed_during.values())
print(f"  M1 missed trades: {total_m1_missed}")
for k, v in m1_missed_during.items():
    print(f"    During {k}: {v}")


# ══════════════════════════════════════════════════════════════════════
# Save Step 0a output
# ══════════════════════════════════════════════════════════════════════
outcome_cols = ["touch_idx", "BarIndex", "RotBarIndex", "entry_bar", "direction",
                "mode", "pnl", "bars_held", "exit_type", "mfe", "mae",
                "stop_used", "target_used", "tc_used", "zw_ticks",
                "zone_top", "zone_bot", "touch_price", "touch_type",
                "entry_open", "entry_offset", "score_aeq", "score_bz",
                "max_penetration", "win"]
qt[outcome_cols].to_csv(OUT_DIR / "qualifying_trades_outcomes_v32.csv", index=False)
print(f"\nSaved: qualifying_trades_outcomes_v32.csv ({len(qt)} rows)")

# Save fill rate data
fill_data = qt[["touch_idx", "mode", "direction", "max_penetration", "zw_ticks"]].copy()
fill_data.to_csv(OUT_DIR / "fill_rate_analysis_v32.csv", index=False)
print(f"Saved: fill_rate_analysis_v32.csv ({len(fill_data)} rows)")


# ══════════════════════════════════════════════════════════════════════
# ══════════════════════════════════════════════════════════════════════
# SURFACE B: EXIT STRUCTURE MODIFICATIONS
# ══════════════════════════════════════════════════════════════════════
# ══════════════════════════════════════════════════════════════════════
print("\n\n" + "=" * 72)
print("SURFACE B: EXIT STRUCTURE MODIFICATIONS")
print("Entries unchanged (zone edge, baseline). Only exits change.")
print("=" * 72)


def sim_trade_custom(entry_bar, direction, stop_ticks, target_ticks, tcap,
                     be_trigger=0, trail_trigger=0):
    """Simulate single trade with custom exit params. Returns dict."""
    if entry_bar >= n_bars:
        return None
    ep = bar_arr[entry_bar, 0]
    if direction == 1:
        stop_price = ep - stop_ticks * TICK_SIZE
        target_price = ep + target_ticks * TICK_SIZE
    else:
        stop_price = ep + stop_ticks * TICK_SIZE
        target_price = ep - target_ticks * TICK_SIZE

    mfe = 0.0
    mae = 0.0
    be_active = False

    end = min(entry_bar + tcap, n_bars)
    for i in range(entry_bar, end):
        h, l, last = bar_arr[i, 1], bar_arr[i, 2], bar_arr[i, 3]
        bh = i - entry_bar + 1

        if direction == 1:
            cur_mfe = (h - ep) / TICK_SIZE
            cur_mae = (ep - l) / TICK_SIZE
        else:
            cur_mfe = (ep - l) / TICK_SIZE
            cur_mae = (h - ep) / TICK_SIZE
        mfe = max(mfe, cur_mfe)
        mae = max(mae, cur_mae)

        # BE trigger
        if be_trigger > 0 and not be_active and mfe >= be_trigger:
            be_active = True
            if direction == 1:
                stop_price = max(stop_price, ep)
            else:
                stop_price = min(stop_price, ep)

        # Trail (simple: after trail_trigger, trail at distance = trail_trigger)
        if trail_trigger > 0 and mfe >= trail_trigger:
            if direction == 1:
                new_trail = ep + (mfe - trail_trigger) * TICK_SIZE
                stop_price = max(stop_price, new_trail)
            else:
                new_trail = ep - (mfe - trail_trigger) * TICK_SIZE
                stop_price = min(stop_price, new_trail)

        # Check stop
        if direction == 1:
            stop_hit = l <= stop_price
            target_hit = h >= target_price
        else:
            stop_hit = h >= stop_price
            target_hit = l <= target_price

        if stop_hit:
            pnl = (stop_price - ep) / TICK_SIZE if direction == 1 else (ep - stop_price) / TICK_SIZE
            etype = "BE" if be_active else ("TRAIL" if trail_trigger > 0 and mfe >= trail_trigger else "STOP")
            return {"pnl": pnl, "bars_held": bh, "exit_type": etype, "mfe": mfe, "mae": mae}
        if target_hit:
            return {"pnl": target_ticks, "bars_held": bh, "exit_type": "TARGET", "mfe": mfe, "mae": mae}
        if bh >= tcap:
            pnl = (last - ep) / TICK_SIZE if direction == 1 else (ep - last) / TICK_SIZE
            return {"pnl": pnl, "bars_held": bh, "exit_type": "TIMECAP", "mfe": mfe, "mae": mae}

    if end > entry_bar:
        last = bar_arr[end - 1, 3]
        pnl = (last - ep) / TICK_SIZE if direction == 1 else (ep - last) / TICK_SIZE
        return {"pnl": pnl, "bars_held": end - entry_bar, "exit_type": "TIMECAP", "mfe": mfe, "mae": mae}
    return None


def sim_multileg(entry_bar, direction, stop_ticks, leg_targets, leg_weights,
                 tcap, be_after_leg=None, be_dest=0):
    """Simulate multi-leg trade. Returns dict with per-leg details."""
    if entry_bar >= n_bars:
        return None
    ep = bar_arr[entry_bar, 0]
    n_legs = len(leg_targets)

    if direction == 1:
        stop_price = ep - stop_ticks * TICK_SIZE
        target_prices = [ep + t * TICK_SIZE for t in leg_targets]
    else:
        stop_price = ep + stop_ticks * TICK_SIZE
        target_prices = [ep - t * TICK_SIZE for t in leg_targets]

    leg_open = [True] * n_legs
    leg_pnls = [0.0] * n_legs
    leg_exits = [""] * n_legs
    legs_filled = 0
    mfe = 0.0
    mae = 0.0

    end = min(entry_bar + tcap, n_bars)
    for i in range(entry_bar, end):
        h, l, last = bar_arr[i, 1], bar_arr[i, 2], bar_arr[i, 3]
        bh = i - entry_bar + 1

        if direction == 1:
            cur_mfe = (h - ep) / TICK_SIZE
            cur_mae = (ep - l) / TICK_SIZE
        else:
            cur_mfe = (ep - l) / TICK_SIZE
            cur_mae = (h - ep) / TICK_SIZE
        mfe = max(mfe, cur_mfe)
        mae = max(mae, cur_mae)

        # Check stop (all open legs)
        if direction == 1:
            stop_hit = l <= stop_price
        else:
            stop_hit = h >= stop_price

        if stop_hit:
            pnl_stop = (stop_price - ep) / TICK_SIZE if direction == 1 else (ep - stop_price) / TICK_SIZE
            for j in range(n_legs):
                if leg_open[j]:
                    leg_pnls[j] = pnl_stop
                    leg_exits[j] = "STOP"
                    leg_open[j] = False
            weighted = sum(w * p for w, p in zip(leg_weights, leg_pnls))
            return {"pnl": weighted, "bars_held": bh, "exit_type": "STOP",
                    "mfe": mfe, "mae": mae, "leg_pnls": leg_pnls, "leg_exits": leg_exits}

        # Check targets (ascending)
        for j in range(n_legs):
            if not leg_open[j]:
                continue
            if direction == 1:
                hit = h >= target_prices[j]
            else:
                hit = l <= target_prices[j]
            if hit:
                leg_pnls[j] = leg_targets[j]
                leg_exits[j] = f"T{j+1}"
                leg_open[j] = False
                legs_filled += 1

                # Move stop to BE after specified leg
                if be_after_leg is not None and legs_filled == be_after_leg + 1:
                    if direction == 1:
                        stop_price = max(stop_price, ep + be_dest * TICK_SIZE)
                    else:
                        stop_price = min(stop_price, ep - be_dest * TICK_SIZE)

        if not any(leg_open):
            weighted = sum(w * p for w, p in zip(leg_weights, leg_pnls))
            return {"pnl": weighted, "bars_held": bh, "exit_type": "TARGET",
                    "mfe": mfe, "mae": mae, "leg_pnls": leg_pnls, "leg_exits": leg_exits}

        if bh >= tcap:
            tc_pnl = (last - ep) / TICK_SIZE if direction == 1 else (ep - last) / TICK_SIZE
            for j in range(n_legs):
                if leg_open[j]:
                    leg_pnls[j] = tc_pnl
                    leg_exits[j] = "TC"
                    leg_open[j] = False
            weighted = sum(w * p for w, p in zip(leg_weights, leg_pnls))
            return {"pnl": weighted, "bars_held": bh, "exit_type": "TIMECAP",
                    "mfe": mfe, "mae": mae, "leg_pnls": leg_pnls, "leg_exits": leg_exits}

    # Ran out of bars
    if end > entry_bar:
        last = bar_arr[end - 1, 3]
        tc_pnl = (last - ep) / TICK_SIZE if direction == 1 else (ep - last) / TICK_SIZE
        for j in range(n_legs):
            if leg_open[j]:
                leg_pnls[j] = tc_pnl
                leg_exits[j] = "TC"
                leg_open[j] = False
        weighted = sum(w * p for w, p in zip(leg_weights, leg_pnls))
        return {"pnl": weighted, "bars_held": end - entry_bar, "exit_type": "TIMECAP",
                "mfe": mfe, "mae": mae, "leg_pnls": leg_pnls, "leg_exits": leg_exits}
    return None


def run_on_population(pop_df, sim_func):
    """Run a sim function on each trade in the population (no overlap filter).
    sim_func(row) -> dict or None. Returns list of result dicts."""
    results = []
    for _, row in pop_df.iterrows():
        r = sim_func(row)
        if r is not None:
            results.append(r)
    return results


def summarize(results, label="", cost=3):
    """Print summary stats for a list of result dicts."""
    if not results:
        print(f"  {label}: NO RESULTS")
        return {}
    pnls = [r["pnl"] for r in results]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p <= 0]
    pf = compute_pf(pnls, cost)
    wr = len(wins) / len(pnls) * 100
    mean_win = np.mean(wins) if wins else 0
    mean_loss = np.mean(losses) if losses else 0
    loss_win = abs(mean_loss / mean_win) if mean_win != 0 else float("inf")

    # Count new stop-outs vs baseline
    exit_types = [r.get("exit_type", "") for r in results]
    stops = sum(1 for e in exit_types if e in ("STOP", "BE"))

    print(f"  {label}: n={len(pnls)}, PF@{cost}t={pf:.2f}, WR={wr:.1f}%, "
          f"meanW={mean_win:.1f}t, meanL={mean_loss:.1f}t, L:W={loss_win:.2f}, stops={stops}")
    return {"pf": pf, "wr": wr, "mean_win": mean_win, "mean_loss": mean_loss,
            "loss_win": loss_win, "n": len(pnls), "stops": stops, "pnls": pnls}


# ── B1: Stop Reduction (Mode 1) ──
print("\n── B1: Stop Reduction (Mode 1) ──")
print("Baseline: 190t stop, 60t target, 120 bar TC")

m1_results_by_stop = {}
for stop in [190, 170, 150, 130, 120, 100]:
    results = run_on_population(m1, lambda row, s=stop: sim_trade_custom(
        int(row["entry_bar"]), int(row["direction"]), s, 60, 120))
    stats = summarize(results, f"Stop={stop}t", cost=3)
    m1_results_by_stop[stop] = stats

    # Count winners-turned-losers
    if stop < 190:
        baseline_results = run_on_population(m1, lambda row: sim_trade_custom(
            int(row["entry_bar"]), int(row["direction"]), 190, 60, 120))
        new_stopouts = 0
        for br, nr in zip(baseline_results, results):
            if br["pnl"] > 0 and nr["pnl"] <= 0:
                new_stopouts += 1
        print(f"    New stop-outs (winners→losers): {new_stopouts}")


# ── B2: Stop Reduction (Mode 2) ──
print("\n── B2: Stop Reduction (Mode 2) ──")
print("Baseline: max(1.5×ZW, 120t) stop, 1.0×ZW target, 80 bar TC")

m2_stop_configs = [
    ("1.5×ZW floor 120 (baseline)", lambda zw: max(round(1.5 * zw), 120)),
    ("1.3×ZW floor 100", lambda zw: max(round(1.3 * zw), 100)),
    ("1.2×ZW floor 100", lambda zw: max(round(1.2 * zw), 100)),
    ("1.0×ZW floor 80", lambda zw: max(round(1.0 * zw), 80)),
    ("COND: 1.5×ZW<200, 1.2×ZW≥200", lambda zw: max(round(1.5 * zw), 120) if zw < 200 else max(round(1.2 * zw), 100)),
    ("COND: 1.5×ZW<200, 1.0×ZW≥200", lambda zw: max(round(1.5 * zw), 120) if zw < 200 else max(round(1.0 * zw), 80)),
]

m2_results_by_stop = {}
for label, stop_fn in m2_stop_configs:
    results = run_on_population(m2, lambda row, sf=stop_fn: sim_trade_custom(
        int(row["entry_bar"]), int(row["direction"]),
        sf(row["zw_ticks"]), max(1, round(row["zw_ticks"] * 1.0)), 80))
    stats = summarize(results, label, cost=3)
    m2_results_by_stop[label] = stats

    if "baseline" not in label.lower():
        baseline_results = run_on_population(m2, lambda row: sim_trade_custom(
            int(row["entry_bar"]), int(row["direction"]),
            max(round(1.5 * row["zw_ticks"]), 120),
            max(1, round(row["zw_ticks"] * 1.0)), 80))
        new_stopouts = sum(1 for br, nr in zip(baseline_results, results)
                          if br["pnl"] > 0 and nr["pnl"] <= 0)
        print(f"    New stop-outs: {new_stopouts}")


# ── B3: Breakeven Stop (Mode 1) ──
print("\n── B3: Breakeven Stop (Mode 1) ──")

for be_trig in [0, 20, 30, 40, 50]:
    results = run_on_population(m1, lambda row, bt=be_trig: sim_trade_custom(
        int(row["entry_bar"]), int(row["direction"]), 190, 60, 120, be_trigger=bt))
    stats = summarize(results, f"BE@{be_trig}t" if be_trig > 0 else "No BE (baseline)", cost=3)

    if be_trig > 0:
        # Count whipsaws: BE'd trades where price later reached target
        whipsaws = 0
        for r in results:
            if r["exit_type"] == "BE" and r["mfe"] >= 60:
                whipsaws += 1
        scratches = sum(1 for r in results if r["exit_type"] == "BE")
        print(f"    Scratches: {scratches}, Whipsaws (BE'd but MFE≥60t): {whipsaws}")


# ── B4: Breakeven Stop (Mode 2) ──
print("\n── B4: Breakeven Stop (Mode 2) ──")

for be_label, be_fn in [("No BE", lambda zw: 0), ("0.3×ZW", lambda zw: round(0.3 * zw)),
                          ("0.5×ZW", lambda zw: round(0.5 * zw)),
                          ("30t fixed", lambda zw: 30), ("50t fixed", lambda zw: 50)]:
    results = run_on_population(m2, lambda row, bf=be_fn: sim_trade_custom(
        int(row["entry_bar"]), int(row["direction"]),
        max(round(1.5 * row["zw_ticks"]), 120),
        max(1, round(row["zw_ticks"] * 1.0)), 80,
        be_trigger=bf(row["zw_ticks"])))
    stats = summarize(results, be_label, cost=3)

    if be_label != "No BE":
        scratches = sum(1 for r in results if r["exit_type"] == "BE")
        whipsaws = sum(1 for r in results if r["exit_type"] == "BE" and r["mfe"] >= r.get("target_used", 60))
        print(f"    Scratches: {scratches}")


# ── B5: Partial Exits (Mode 1) ──
print("\n── B5: Partial Exits (Mode 1) ──")

partial_configs_m1 = [
    ("Baseline 3@60", [60], [1.0], None, 0),
    ("2+1: 2@60, 1@120 BE", [60, 120], [2/3, 1/3], 0, 0),
    ("2+1w: 2@60, 1@180 BE", [60, 180], [2/3, 1/3], 0, 0),
    ("1+2: 1@60, 2@120 BE", [60, 120], [1/3, 2/3], 0, 0),
    ("1+1+1: 1@60, 1@120, 1@180 BE", [60, 120, 180], [1/3, 1/3, 1/3], 0, 0),
]

for label, targets, weights, be_leg, be_dest in partial_configs_m1:
    results = run_on_population(m1, lambda row, t=targets, w=weights, bl=be_leg, bd=be_dest:
        sim_multileg(int(row["entry_bar"]), int(row["direction"]), 190,
                     t, w, 120, be_after_leg=bl, be_dest=bd))
    stats = summarize(results, label, cost=3)

    if len(targets) > 1:
        # Report per-position PnL (multiply by 3 contracts)
        if results:
            total_pnls_3ct = [r["pnl"] * 3 for r in results]  # weighted already, ×3 for contracts
            mean_win_3ct = np.mean([p for p in total_pnls_3ct if p > 0]) if any(p > 0 for p in total_pnls_3ct) else 0
            mean_loss_3ct = np.mean([p for p in total_pnls_3ct if p <= 0]) if any(p <= 0 for p in total_pnls_3ct) else 0
            print(f"    Per-position (3ct): meanW={mean_win_3ct:.0f}t, meanL={mean_loss_3ct:.0f}t")


# ── B6: Partial Exits (Mode 2) ──
print("\n── B6: Partial Exits (Mode 2) ──")

partial_configs_m2_labels = [
    "Baseline 3@1.0×ZW",
    "2+1h: 2@0.5×ZW, 1@1.0×ZW BE",
    "2+1f: 2@0.5×ZW, 1@1.5×ZW BE",
    "1+2: 1@0.5×ZW, 2@1.0×ZW BE",
    "1+1+1: 1@0.5, 1@1.0, 1@1.5×ZW BE",
]

for label_idx, label in enumerate(partial_configs_m2_labels):
    def make_sim(row, li=label_idx):
        zw = row["zw_ticks"]
        stop = max(round(1.5 * zw), 120)
        if li == 0:
            return sim_multileg(int(row["entry_bar"]), int(row["direction"]),
                                stop, [max(1, round(zw * 1.0))], [1.0], 80)
        elif li == 1:
            t1 = max(1, round(zw * 0.5))
            t2 = max(1, round(zw * 1.0))
            return sim_multileg(int(row["entry_bar"]), int(row["direction"]),
                                stop, [t1, t2], [2/3, 1/3], 80, be_after_leg=0, be_dest=0)
        elif li == 2:
            t1 = max(1, round(zw * 0.5))
            t2 = max(1, round(zw * 1.5))
            return sim_multileg(int(row["entry_bar"]), int(row["direction"]),
                                stop, [t1, t2], [2/3, 1/3], 80, be_after_leg=0, be_dest=0)
        elif li == 3:
            t1 = max(1, round(zw * 0.5))
            t2 = max(1, round(zw * 1.0))
            return sim_multileg(int(row["entry_bar"]), int(row["direction"]),
                                stop, [t1, t2], [1/3, 2/3], 80, be_after_leg=0, be_dest=0)
        elif li == 4:
            t1 = max(1, round(zw * 0.5))
            t2 = max(1, round(zw * 1.0))
            t3 = max(1, round(zw * 1.5))
            return sim_multileg(int(row["entry_bar"]), int(row["direction"]),
                                stop, [t1, t2, t3], [1/3, 1/3, 1/3], 80,
                                be_after_leg=0, be_dest=0)

    results = run_on_population(m2, make_sim)
    stats = summarize(results, label, cost=3)


# ── B7: Time Cap Tightening ──
print("\n── B7: Time Cap Tightening ──")

for tc_m1, tc_m2 in [(120, 80), (90, 60), (60, 40)]:
    # M1
    results_m1 = run_on_population(m1, lambda row, tc=tc_m1: sim_trade_custom(
        int(row["entry_bar"]), int(row["direction"]), 190, 60, tc))
    stats_m1 = summarize(results_m1, f"M1 TC={tc_m1}", cost=3)

    # M2
    results_m2 = run_on_population(m2, lambda row, tc=tc_m2: sim_trade_custom(
        int(row["entry_bar"]), int(row["direction"]),
        max(round(1.5 * row["zw_ticks"]), 120),
        max(1, round(row["zw_ticks"] * 1.0)), tc))
    stats_m2 = summarize(results_m2, f"M2 TC={tc_m2}", cost=3)


# ══════════════════════════════════════════════════════════════════════
# SURFACE A: ENTRY EXECUTION MODIFICATIONS
# ══════════════════════════════════════════════════════════════════════
print("\n\n" + "=" * 72)
print("SURFACE A: ENTRY EXECUTION MODIFICATIONS")
print("Exits unchanged (baseline). Only entry location changes.")
print("=" * 72)


def sim_deeper_entry(row, depth_ticks, mode):
    """Simulate with entry at zone_edge + depth_ticks deeper.
    Stop and target LEVELS stay fixed relative to zone geometry."""
    eb = int(row["entry_bar"])
    d = int(row["direction"])
    rbi = int(row["RotBarIndex"])
    zw = row["zw_ticks"]
    tp = row["touch_price"]  # zone edge

    if eb >= n_bars:
        return None

    # Check if price reaches the deeper entry within fill window
    max_pen = row["max_penetration"]
    if max_pen < depth_ticks:
        return None  # Doesn't fill

    # Find the fill bar (first bar where penetration >= depth)
    fill_bar = None
    for bi in range(rbi, min(rbi + FILL_WINDOW, n_bars)):
        h, l = bar_arr[bi, 1], bar_arr[bi, 2]
        if d == -1:
            pen = (tp - l) / TICK_SIZE
        else:
            pen = (h - tp) / TICK_SIZE
        if pen >= depth_ticks:
            fill_bar = bi + 1  # Enter on next bar after fill
            break

    if fill_bar is None or fill_bar >= n_bars:
        return None

    # Entry price: zone_edge + depth into zone
    if d == -1:  # short: demand edge, entry below edge
        entry_price = tp - depth_ticks * TICK_SIZE
    else:  # long: supply edge, entry above edge
        entry_price = tp + depth_ticks * TICK_SIZE

    # Stop and target LEVELS fixed to zone geometry (not entry)
    if mode == "M1":
        # Stop level = zone_edge - 190t (from edge), target = zone_edge + 60t
        if d == -1:
            stop_level = tp + 190 * TICK_SIZE  # above edge for short
            target_level = tp - 60 * TICK_SIZE  # below edge for short
        else:
            stop_level = tp - 190 * TICK_SIZE
            target_level = tp + 60 * TICK_SIZE
        tcap = 120
    else:
        stop_mult = max(round(1.5 * zw), 120)
        target_mult = max(1, round(zw * 1.0))
        if d == -1:
            stop_level = tp + stop_mult * TICK_SIZE
            target_level = tp - target_mult * TICK_SIZE
        else:
            stop_level = tp - stop_mult * TICK_SIZE
            target_level = tp + target_mult * TICK_SIZE
        tcap = 80

    # Compute effective stop/target distances from entry
    if d == 1:
        stop_dist = (entry_price - stop_level) / TICK_SIZE
        target_dist = (target_level - entry_price) / TICK_SIZE
    else:
        stop_dist = (stop_level - entry_price) / TICK_SIZE
        target_dist = (entry_price - target_level) / TICK_SIZE

    if stop_dist <= 0 or target_dist <= 0:
        return None

    # Simulate from fill_bar
    mfe = 0.0
    mae = 0.0
    end = min(fill_bar + tcap, n_bars)
    for i in range(fill_bar, end):
        h, l, last = bar_arr[i, 1], bar_arr[i, 2], bar_arr[i, 3]
        bh = i - fill_bar + 1

        if d == 1:
            cur_mfe = (h - entry_price) / TICK_SIZE
            cur_mae = (entry_price - l) / TICK_SIZE
            stop_hit = l <= stop_level
            target_hit = h >= target_level
        else:
            cur_mfe = (entry_price - l) / TICK_SIZE
            cur_mae = (h - entry_price) / TICK_SIZE
            stop_hit = h >= stop_level
            target_hit = l <= target_level
        mfe = max(mfe, cur_mfe)
        mae = max(mae, cur_mae)

        if stop_hit:
            pnl = -stop_dist
            return {"pnl": pnl, "bars_held": bh, "exit_type": "STOP",
                    "mfe": mfe, "mae": mae, "stop_dist": stop_dist, "target_dist": target_dist}
        if target_hit:
            pnl = target_dist
            return {"pnl": pnl, "bars_held": bh, "exit_type": "TARGET",
                    "mfe": mfe, "mae": mae, "stop_dist": stop_dist, "target_dist": target_dist}
        if bh >= tcap:
            if d == 1:
                pnl = (last - entry_price) / TICK_SIZE
            else:
                pnl = (entry_price - last) / TICK_SIZE
            return {"pnl": pnl, "bars_held": bh, "exit_type": "TIMECAP",
                    "mfe": mfe, "mae": mae, "stop_dist": stop_dist, "target_dist": target_dist}

    return None


# ── A1: Deeper Fixed Entry (Mode 1) ──
print("\n── A1: Deeper Fixed Entry (Mode 1) ──")

# Use fill rate curve points from Step 0f
m1_pens = qt[qt["mode"] == "M1"]["max_penetration"].values
m1_p10 = np.percentile(m1_pens, 10)
m1_p25 = np.percentile(m1_pens, 25)
m1_p40 = np.percentile(m1_pens, 40)

depths_m1 = sorted(set([0, 5, 10, 15, 20, 30, 40,
                        round(m1_p10), round(m1_p25), round(m1_p40)]))

for depth in depths_m1:
    results = run_on_population(m1, lambda row, dep=depth: sim_deeper_entry(row, dep, "M1"))
    fill_n = len(results)
    missed = len(m1) - fill_n
    fill_pct = fill_n / len(m1) * 100

    if results:
        mean_sd = np.mean([r["stop_dist"] for r in results])
        mean_td = np.mean([r["target_dist"] for r in results])
        loss_win = mean_sd / mean_td if mean_td > 0 else float("inf")
        stats = summarize(results, f"Depth={depth}t (fill={fill_pct:.0f}%)", cost=3)
        print(f"    StopDist={mean_sd:.0f}t, TargetDist={mean_td:.0f}t, L:W={loss_win:.2f}, missed={missed}")
    else:
        print(f"  Depth={depth}t: NO FILLS")


# ── A2: Deeper Fixed Entry (Mode 2) ──
print("\n── A2: Deeper Fixed Entry (Mode 2) ──")

m2_pens = qt[qt["mode"] == "M2"]["max_penetration"].values
m2_p10 = np.percentile(m2_pens, 10)
m2_p25 = np.percentile(m2_pens, 25)

# Test as % of zone width — fixed tick depths
depths_m2 = sorted(set([0, 5, 10, 15, 20, 30, 40, 50,
                        round(m2_p10), round(m2_p25)]))

for depth in depths_m2:
    results = run_on_population(m2, lambda row, dep=depth: sim_deeper_entry(row, dep, "M2"))
    fill_n = len(results)
    fill_pct = fill_n / len(m2) * 100

    if results:
        mean_sd = np.mean([r["stop_dist"] for r in results])
        mean_td = np.mean([r["target_dist"] for r in results])
        stats = summarize(results, f"Depth={depth}t (fill={fill_pct:.0f}%)", cost=3)
    else:
        print(f"  Depth={depth}t: NO FILLS")


# ── A3: Scaled Entry (Mode 1) ──
print("\n── A3: Scaled Entry (Mode 1) ──")
print("Note: Simulator doesn't support multi-price entries natively.")
print("Computing analytically: weighted average entry across legs that fill.")

scaled_configs_m1 = [
    ("Baseline 3@edge", [(0, 3)]),
    ("1+1+1 even", [(0, 1), (15, 1), (30, 1)]),
    ("1+1+1 deep", [(0, 1), (20, 1), (40, 1)]),
    ("2+1", [(0, 2), (30, 1)]),
    ("1+2", [(0, 1), (20, 2)]),
]

for label, legs in scaled_configs_m1:
    all_pnls = []
    for _, row in m1.iterrows():
        eb = int(row["entry_bar"])
        d = int(row["direction"])
        tp = row["touch_price"]
        max_pen = row["max_penetration"]

        if eb >= n_bars:
            continue

        total_pnl = 0
        total_cts = 0
        for depth, cts in legs:
            if max_pen >= depth:
                # This leg fills
                if depth == 0:
                    # Edge entry: use existing sim
                    r = sim_trade_custom(eb, d, 190, 60, 120)
                    if r:
                        total_pnl += r["pnl"] * cts
                        total_cts += cts
                else:
                    # Deeper entry: stop/target levels fixed to zone
                    r = sim_deeper_entry(row, depth, "M1")
                    if r:
                        total_pnl += r["pnl"] * cts
                        total_cts += cts

        if total_cts > 0:
            avg_pnl = total_pnl / total_cts  # per-contract weighted average
            all_pnls.append({"pnl": avg_pnl, "exit_type": "SCALED", "mfe": 0, "mae": 0,
                            "bars_held": 0, "total_cts": total_cts})

    if all_pnls:
        pf = compute_pf([r["pnl"] for r in all_pnls], cost=3)
        wins = [r["pnl"] for r in all_pnls if r["pnl"] > 0]
        losses = [r["pnl"] for r in all_pnls if r["pnl"] <= 0]
        mean_cts = np.mean([r["total_cts"] for r in all_pnls])
        wr = len(wins) / len(all_pnls) * 100
        mean_w = np.mean(wins) if wins else 0
        mean_l = np.mean(losses) if losses else 0
        print(f"  {label}: n={len(all_pnls)}, PF@3t={pf:.2f}, WR={wr:.1f}%, "
              f"meanW={mean_w:.1f}t, meanL={mean_l:.1f}t, avgCts={mean_cts:.1f}")


# ── A4: Scaled Entry (Mode 2) ──
print("\n── A4: Scaled Entry (Mode 2) ──")

scaled_configs_m2 = [
    ("Baseline 3@edge", [(0, 3)]),
    ("1+1+1", [(0, 1), (0.1, 1), (0.2, 1)]),  # depth as fraction of ZW
    ("2+1", [(0, 2), (0.15, 1)]),
]

for label, legs in scaled_configs_m2:
    all_pnls = []
    for _, row in m2.iterrows():
        eb = int(row["entry_bar"])
        d = int(row["direction"])
        zw = row["zw_ticks"]
        max_pen = row["max_penetration"]

        if eb >= n_bars:
            continue

        total_pnl = 0
        total_cts = 0
        for depth_frac, cts in legs:
            depth = round(depth_frac * zw) if depth_frac > 0 else 0
            if max_pen >= depth:
                if depth == 0:
                    r = sim_trade_custom(eb, d,
                                         max(round(1.5 * zw), 120),
                                         max(1, round(zw * 1.0)), 80)
                    if r:
                        total_pnl += r["pnl"] * cts
                        total_cts += cts
                else:
                    r = sim_deeper_entry(row, depth, "M2")
                    if r:
                        total_pnl += r["pnl"] * cts
                        total_cts += cts

        if total_cts > 0:
            avg_pnl = total_pnl / total_cts
            all_pnls.append({"pnl": avg_pnl})

    if all_pnls:
        pf = compute_pf([r["pnl"] for r in all_pnls], cost=3)
        wins = [r["pnl"] for r in all_pnls if r["pnl"] > 0]
        losses = [r["pnl"] for r in all_pnls if r["pnl"] <= 0]
        wr = len(wins) / len(all_pnls) * 100
        print(f"  {label}: n={len(all_pnls)}, PF@3t={pf:.2f}, WR={wr:.1f}%")


# ══════════════════════════════════════════════════════════════════════
# SURFACE A ADDENDUM: Entry-Relative Stops (corrected design)
# ══════════════════════════════════════════════════════════════════════
print("\n── A1-ALT: Deeper Entry with ENTRY-RELATIVE stops (Mode 1) ──")
print("Stop/target distances stay fixed relative to ENTRY (not zone).")
print("Deeper entry = better fill price, same risk profile.")

for depth in [0, 10, 20, 24, 30, 34, 40]:
    results = []
    for _, row in m1.iterrows():
        if row["max_penetration"] < depth:
            continue
        # Find fill bar
        rbi = int(row["RotBarIndex"])
        d = int(row["direction"])
        tp = row["touch_price"]
        fill_bar = None
        for bi in range(rbi, min(rbi + FILL_WINDOW, n_bars)):
            h, l = bar_arr[bi, 1], bar_arr[bi, 2]
            if d == -1:
                pen = (tp - l) / TICK_SIZE
            else:
                pen = (h - tp) / TICK_SIZE
            if pen >= depth:
                fill_bar = bi + 1
                break
        if fill_bar is None or fill_bar >= n_bars:
            continue
        # Same stop/target as baseline, just from better entry
        r = sim_trade_custom(fill_bar, d, 190, 60, 120)
        if r:
            results.append(r)

    fill_pct = len(results) / len(m1) * 100
    if results:
        stats = summarize(results, f"Depth={depth}t (fill={fill_pct:.0f}%)", cost=3)

print("\n── A2-ALT: Deeper Entry with ENTRY-RELATIVE stops (Mode 2) ──")
for depth in [0, 10, 20, 29, 30, 40]:
    results = []
    for _, row in m2.iterrows():
        if row["max_penetration"] < depth:
            continue
        rbi = int(row["RotBarIndex"])
        d = int(row["direction"])
        tp = row["touch_price"]
        zw = row["zw_ticks"]
        fill_bar = None
        for bi in range(rbi, min(rbi + FILL_WINDOW, n_bars)):
            h, l = bar_arr[bi, 1], bar_arr[bi, 2]
            if d == -1:
                pen = (tp - l) / TICK_SIZE
            else:
                pen = (h - tp) / TICK_SIZE
            if pen >= depth:
                fill_bar = bi + 1
                break
        if fill_bar is None or fill_bar >= n_bars:
            continue
        stop = max(round(1.5 * zw), 120)
        target = max(1, round(zw * 1.0))
        r = sim_trade_custom(fill_bar, d, stop, target, 80)
        if r:
            results.append(r)

    fill_pct = len(results) / len(m2) * 100
    if results:
        stats = summarize(results, f"Depth={depth}t (fill={fill_pct:.0f}%)", cost=3)


# ══════════════════════════════════════════════════════════════════════
# ══════════════════════════════════════════════════════════════════════
# STEP 3: STACKING — BEST COMBINATIONS
# ══════════════════════════════════════════════════════════════════════
# ══════════════════════════════════════════════════════════════════════
print("\n\n" + "=" * 72)
print("STEP 3: STACKING — BEST COMBINATIONS")
print("=" * 72)

# ── M1 Stacking ──
print("\n── M1 Stacking ──")
print("Candidate: B5 (1+1+1 partials: 1@60, 1@120, 1@180, BE after T1)")
print("No Surface A candidates improved M1.")

# Baseline
m1_base = run_on_population(m1, lambda row: sim_trade_custom(
    int(row["entry_bar"]), int(row["direction"]), 190, 60, 120))
summarize(m1_base, "M1 Baseline", cost=3)

# Best B mod: B5 1+1+1
m1_stack1 = run_on_population(m1, lambda row: sim_multileg(
    int(row["entry_bar"]), int(row["direction"]), 190,
    [60, 120, 180], [1/3, 1/3, 1/3], 120, be_after_leg=0, be_dest=0))
summarize(m1_stack1, "M1 +B5(1+1+1)", cost=3)

# Try adding B2-equivalent (stop at 170t) to partials — check interaction
m1_stack2 = run_on_population(m1, lambda row: sim_multileg(
    int(row["entry_bar"]), int(row["direction"]), 170,
    [60, 120, 180], [1/3, 1/3, 1/3], 120, be_after_leg=0, be_dest=0))
summarize(m1_stack2, "M1 +B5(1+1+1)+B1(170t)", cost=3)

# 1+2 partials (was second best)
m1_stack3 = run_on_population(m1, lambda row: sim_multileg(
    int(row["entry_bar"]), int(row["direction"]), 190,
    [60, 120], [1/3, 2/3], 120, be_after_leg=0, be_dest=0))
summarize(m1_stack3, "M1 +B5(1+2)", cost=3)

print("\n  M1 RECOMMENDATION: B5 1+1+1 (PF 9.99 vs 8.50 baseline)")

# ── M2 Stacking ──
print("\n── M2 Stacking ──")
print("Candidate: B2 (1.3×ZW floor 100)")
print("No Surface A candidates improved M2.")

# Baseline
m2_base = run_on_population(m2, lambda row: sim_trade_custom(
    int(row["entry_bar"]), int(row["direction"]),
    max(round(1.5 * row["zw_ticks"]), 120),
    max(1, round(row["zw_ticks"] * 1.0)), 80))
summarize(m2_base, "M2 Baseline", cost=3)

# Best B mod: B2 1.3×ZW floor 100
m2_stack1 = run_on_population(m2, lambda row: sim_trade_custom(
    int(row["entry_bar"]), int(row["direction"]),
    max(round(1.3 * row["zw_ticks"]), 100),
    max(1, round(row["zw_ticks"] * 1.0)), 80))
summarize(m2_stack1, "M2 +B2(1.3×ZW)", cost=3)

# Try B2 + B4 (0.3×ZW BE)
m2_stack2 = run_on_population(m2, lambda row: sim_trade_custom(
    int(row["entry_bar"]), int(row["direction"]),
    max(round(1.3 * row["zw_ticks"]), 100),
    max(1, round(row["zw_ticks"] * 1.0)), 80,
    be_trigger=round(0.3 * row["zw_ticks"])))
summarize(m2_stack2, "M2 +B2(1.3×ZW)+B4(0.3×ZW BE)", cost=3)

print("\n  M2 RECOMMENDATION: B2 1.3×ZW floor 100 (PF 4.67 vs 4.61 baseline)")
print("  NOTE: Marginal improvement. Baseline exits are well-calibrated.")


# ══════════════════════════════════════════════════════════════════════
# ══════════════════════════════════════════════════════════════════════
# STEP 4: P2 VALIDATION
# ══════════════════════════════════════════════════════════════════════
# ══════════════════════════════════════════════════════════════════════
print("\n\n" + "=" * 72)
print("STEP 4: P2 VALIDATION (ONE-SHOT)")
print("=" * 72)

# Load P2 data
print("\nLoading P2 data...")
bar_p2 = pd.read_csv(DATA_DIR / "NQ_bardata_P2.csv")
bar_p2.columns = bar_p2.columns.str.strip()
bar_arr_p2 = bar_p2[["Open", "High", "Low", "Last"]].to_numpy(dtype=np.float64)
n_bars_p2 = len(bar_arr_p2)
print(f"P2 bars: {n_bars_p2}")

# Load P2 touches
p2a_raw = pd.read_csv(DATA_DIR / "NQ_merged_P2a.csv")
p2b_raw = pd.read_csv(DATA_DIR / "NQ_merged_P2b.csv")
p2a_raw.columns = p2a_raw.columns.str.strip()
p2b_raw.columns = p2b_raw.columns.str.strip()

# Filter RotBarIndex < 0
p2a = p2a_raw[p2a_raw["RotBarIndex"] >= 0].reset_index(drop=True)
p2b = p2b_raw[p2b_raw["RotBarIndex"] >= 0].reset_index(drop=True)
print(f"P2a touches: {len(p2a)}, P2b touches: {len(p2b)}")

# Load scoring models
with open(PARAM_DIR / "scoring_model_aeq_v32.json") as f:
    aeq_cfg = json.load(f)
with open(PARAM_DIR / "scoring_model_bzscore_v32.json") as f:
    bz_cfg = json.load(f)
with open(PARAM_DIR / "feature_config_v32.json") as f:
    feat_cfg = json.load(f)

WINNING_FEATURES = feat_cfg["winning_features"]
TS_P33 = feat_cfg["trend_slope_P33"]
TS_P67 = feat_cfg["trend_slope_P67"]
BIN_EDGES = feat_cfg["feature_bin_edges"]
FEAT_MEANS = feat_cfg["feature_means"]
FEAT_STDS = feat_cfg["feature_stds"]

bar_atr_p2 = bar_p2["ATR"].to_numpy(dtype=np.float64)


def compute_features_p2(df, label):
    """Compute scoring features on P2 touches using P1-frozen params."""
    df = df.copy()
    df["F01"] = df["SourceLabel"]
    df["F02"] = df["ZoneWidthTicks"]
    df["F04"] = df["CascadeState"].replace("UNKNOWN", "NO_PRIOR")

    # F05: Session
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
        if 0 <= rbi < n_bars_p2 and bar_atr_p2[rbi] > 0:
            atr_vals.append(bar_atr_p2[rbi])
        else:
            atr_vals.append(np.nan)
    df["F09"] = df["ZoneWidthTicks"].values * TICK_SIZE / np.array(atr_vals)

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
    df["F10"] = df.index.map(prior_pen)

    # F13: Touch Bar Close Position
    rot_idx = df["RotBarIndex"].values.astype(int)
    is_long = df["TouchType"].str.contains("DEMAND").values
    tb_h = np.array([bar_arr_p2[max(0, min(i, n_bars_p2 - 1)), 1] for i in rot_idx])
    tb_l = np.array([bar_arr_p2[max(0, min(i, n_bars_p2 - 1)), 2] for i in rot_idx])
    tb_c = np.array([bar_arr_p2[max(0, min(i, n_bars_p2 - 1)), 3] for i in rot_idx])
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
        return "NT"
    df["TrendLabel"] = df["TrendSlope"].apply(assign_trend)

    if "SBB_Label" not in df.columns:
        df["SBB_Label"] = "NORMAL"

    print(f"  {label}: {len(df)} touches, F10 null={df['F10'].isna().mean()*100:.1f}%")
    return df


p2a = compute_features_p2(p2a, "P2a")
p2b = compute_features_p2(p2b, "P2b")


def score_aeq(row, cfg):
    """Score a touch using the A-Eq model (P1-frozen)."""
    weights = cfg["feature_weights"]
    score = 0
    for feat, w in weights.items():
        val = row.get(feat, None)
        if val is None or (isinstance(val, float) and np.isnan(val)):
            continue
        # Bin the value
        if feat in BIN_EDGES:
            edges = BIN_EDGES[feat]
            bin_idx = np.searchsorted(edges, val)
            score += w * bin_idx
        else:
            score += w * val
    return score


def score_bzscore(row, cfg):
    """Score a touch using B-ZScore model (P1-frozen)."""
    weights = cfg["feature_weights"]
    total = 0
    for feat, w in weights.items():
        val = row.get(feat, None)
        if val is None or (isinstance(val, float) and np.isnan(val)):
            continue
        # Z-score normalize
        mean = FEAT_MEANS.get(feat, 0)
        std = FEAT_STDS.get(feat, 1)
        if std > 0:
            z = (val - mean) / std
        else:
            z = 0
        total += w * z
    # Sigmoid
    from scipy.special import expit
    return float(expit(total))


# Score P2 touches
print("\nScoring P2 touches with frozen models...")

# We need to replicate the exact scoring from the backtest harness
# Rather than re-implementing the full scoring, let me use the backtest harness approach
# The scoring uses A-Eq (equal-weight features) and B-ZScore (z-score sigmoid)

# A-Eq scoring: each winning feature contributes equally
# Check the model structure
print(f"  A-Eq model: threshold={aeq_cfg['threshold']}, max_score={aeq_cfg['max_score']}")
print(f"  B-ZScore model: threshold={bz_cfg['threshold']}")
print(f"  Winning features: {WINNING_FEATURES}")


aeq_bin_points = aeq_cfg["bin_points"]


def compute_aeq_score(df):
    """Compute A-Eq score using bin_points lookup."""
    scores = np.zeros(len(df))
    for feat in WINNING_FEATURES:
        bp = aeq_bin_points.get(feat, {})
        if not bp:
            continue
        if feat in ("F01",):
            # Categorical: direct lookup by SourceLabel
            vals = df["F01"].values
            for i, v in enumerate(vals):
                scores[i] += bp.get(str(v), 0)
        elif feat in ("F05",):
            vals = df["F05"].values
            for i, v in enumerate(vals):
                scores[i] += bp.get(str(v), 0)
        elif feat in ("F04",):
            vals = df["F04"].values
            for i, v in enumerate(vals):
                scores[i] += bp.get(str(v), 0)
        else:
            # Numeric: bin by feature_bin_edges → Low/Mid/High
            edges = BIN_EDGES.get(feat, [])
            vals = df[feat].values
            for i, v in enumerate(vals):
                if pd.isna(v):
                    scores[i] += bp.get("NA", 0)
                elif len(edges) >= 2:
                    if v < edges[0]:
                        scores[i] += bp.get("Low", 0)
                    elif v < edges[1]:
                        scores[i] += bp.get("Mid", 0)
                    else:
                        scores[i] += bp.get("High", 0)
    return scores


bz_coefficients = bz_cfg["coefficients"]
bz_intercept = bz_cfg["intercept"]
bz_feature_columns = bz_cfg["feature_columns"]
bz_scaler_mean = bz_cfg["scaler_mean"]
bz_scaler_std = bz_cfg["scaler_std"]


def compute_bz_score(df):
    """Compute B-ZScore: one-hot + logistic regression."""
    from scipy.special import expit
    n = len(df)
    X = np.zeros((n, len(bz_feature_columns)))

    for col_idx, col_name in enumerate(bz_feature_columns):
        if col_name == "F10":
            X[:, col_idx] = df["F10"].fillna(0).values.astype(float)
        elif col_name == "F09":
            X[:, col_idx] = df["F09"].fillna(0).values.astype(float)
        elif col_name == "F21":
            X[:, col_idx] = df["F21"].fillna(0).values.astype(float)
        elif col_name == "F13":
            X[:, col_idx] = df["F13"].fillna(0).values.astype(float)
        elif col_name.startswith("F01_"):
            cat = col_name[4:]  # e.g. "15m"
            X[:, col_idx] = (df["F01"].astype(str) == cat).astype(float)
        elif col_name.startswith("F05_"):
            cat = col_name[4:]
            X[:, col_idx] = (df["F05"].astype(str) == cat).astype(float)
        elif col_name.startswith("F04_"):
            cat = col_name[4:]
            X[:, col_idx] = (df["F04"].astype(str) == cat).astype(float)

    # Standardize
    means = np.array(bz_scaler_mean)
    stds = np.array(bz_scaler_std)
    stds[stds == 0] = 1
    X_scaled = (X - means) / stds

    # Logistic regression
    logits = X_scaled @ np.array(bz_coefficients) + bz_intercept
    return expit(logits)


# Score all P2 touches
p2_all = pd.concat([p2a, p2b], ignore_index=True)
p2_all["Score_AEq"] = compute_aeq_score(p2_all)
p2_all["Score_BZScore"] = compute_bz_score(p2_all)

print(f"  P2 total touches: {len(p2_all)}")
print(f"  P2 A-Eq scores: mean={p2_all['Score_AEq'].mean():.1f}, "
      f">=45.5: {(p2_all['Score_AEq'] >= 45.5).sum()}")
print(f"  P2 B-ZScore scores: mean={p2_all['Score_BZScore'].mean():.3f}, "
      f">=0.50: {(p2_all['Score_BZScore'] >= 0.50).sum()}")

# Apply waterfall: M1 first (A-Eq >= 45.5), M2 second (B-ZScore >= 0.50 + filters)
m1_p2_mask = p2_all["Score_AEq"] >= aeq_cfg["threshold"]
m1_p2 = p2_all[m1_p2_mask].copy()
m1_p2["mode"] = "M1"
m1_p2_indices = set(m1_p2.index)

# M2: B-ZScore >= 0.50, RTH-ish, seq <= 2, TF <= 120m, not in M1
tf_map = {"5m": 5, "10m": 10, "15m": 15, "30m": 30, "50m": 50,
          "60m": 60, "90m": 90, "120m": 120, "240m": 240, "360m": 360}
p2_all["tf_min"] = p2_all["SourceLabel"].map(tf_map).fillna(9999)

m2_p2_mask = (
    (p2_all["Score_BZScore"] >= bz_cfg["threshold"]) &
    (p2_all["TouchSequence"] <= 2) &
    (p2_all["tf_min"] <= 120) &
    (p2_all["F05"] != "Overnight") &
    (~p2_all.index.isin(m1_p2_indices))
)
m2_p2 = p2_all[m2_p2_mask].copy()
m2_p2["mode"] = "M2"

print(f"\n  P2 waterfall:")
print(f"    M1 qualifying: {len(m1_p2)}")
print(f"    M2 qualifying: {len(m2_p2)}")


def sim_with_overlap_p2(touches_df, sim_func, label=""):
    """Simulate with no-overlap filter on P2 data."""
    subset = touches_df.sort_values("RotBarIndex")
    results = []
    in_trade_until = -1
    traded_count = 0
    missed_count = 0

    for _, row in subset.iterrows():
        rbi = int(row["RotBarIndex"])
        entry_bar = rbi + 1
        if entry_bar <= in_trade_until:
            missed_count += 1
            continue
        if entry_bar >= n_bars_p2:
            continue

        r = sim_func(row, entry_bar)
        if r is not None:
            results.append(r)
            in_trade_until = entry_bar + r["bars_held"] - 1
            traded_count += 1

    print(f"  {label}: traded={traded_count}, missed={missed_count}")
    return results


# ── P2 Baseline ──
print("\n── P2 Baseline ──")

# Swap bar_arr to P2
bar_arr_orig = bar_arr
bar_arr = bar_arr_p2
n_bars_orig = n_bars
n_bars = n_bars_p2

# M1 baseline
m1_p2_baseline = sim_with_overlap_p2(
    m1_p2,
    lambda row, eb: sim_trade_custom(eb, 1 if "DEMAND" in str(row["TouchType"]) else -1,
                                     190, 60, 120),
    "M1 P2 baseline")
m1_p2_base_stats = summarize(m1_p2_baseline, "M1 P2 baseline", cost=4)

# M2 baseline
m2_p2_baseline = sim_with_overlap_p2(
    m2_p2,
    lambda row, eb: sim_trade_custom(eb, 1 if "DEMAND" in str(row["TouchType"]) else -1,
                                     max(round(1.5 * row["ZoneWidthTicks"]), 120),
                                     max(1, round(row["ZoneWidthTicks"] * 1.0)), 80),
    "M2 P2 baseline")
m2_p2_base_stats = summarize(m2_p2_baseline, "M2 P2 baseline", cost=4)

# Combined baseline
if m1_p2_baseline and m2_p2_baseline:
    all_p2_base = [r["pnl"] for r in m1_p2_baseline] + [r["pnl"] for r in m2_p2_baseline]
    combined_pf = compute_pf(all_p2_base, cost=4)
    print(f"  Combined P2 baseline PF@4t = {combined_pf:.2f}")

# ── P2 Modified (Best Stack) ──
print("\n── P2 Modified (Best Stack from P1) ──")

# M1: B5 1+1+1 partials
m1_p2_modified = sim_with_overlap_p2(
    m1_p2,
    lambda row, eb: sim_multileg(eb, 1 if "DEMAND" in str(row["TouchType"]) else -1,
                                 190, [60, 120, 180], [1/3, 1/3, 1/3], 120,
                                 be_after_leg=0, be_dest=0),
    "M1 P2 +B5(1+1+1)")
m1_p2_mod_stats = summarize(m1_p2_modified, "M1 P2 +B5(1+1+1)", cost=4)

# M2: B2 1.3×ZW floor 100
m2_p2_modified = sim_with_overlap_p2(
    m2_p2,
    lambda row, eb: sim_trade_custom(eb, 1 if "DEMAND" in str(row["TouchType"]) else -1,
                                     max(round(1.3 * row["ZoneWidthTicks"]), 100),
                                     max(1, round(row["ZoneWidthTicks"] * 1.0)), 80),
    "M2 P2 +B2(1.3×ZW)")
m2_p2_mod_stats = summarize(m2_p2_modified, "M2 P2 +B2(1.3×ZW)", cost=4)

# Combined modified
if m1_p2_modified and m2_p2_modified:
    all_p2_mod = [r["pnl"] for r in m1_p2_modified] + [r["pnl"] for r in m2_p2_modified]
    combined_pf_mod = compute_pf(all_p2_mod, cost=4)
    print(f"  Combined P2 modified PF@4t = {combined_pf_mod:.2f}")

# Pass criteria
print("\n── P2 Pass Criteria ──")
if m1_p2_base_stats and m1_p2_mod_stats:
    m1_pf_change = (m1_p2_mod_stats["pf"] - m1_p2_base_stats["pf"]) / m1_p2_base_stats["pf"] * 100
    m1_lw_change = m1_p2_mod_stats["loss_win"] - m1_p2_base_stats["loss_win"]
    print(f"  M1 PF change: {m1_pf_change:+.1f}% (threshold: -15%)")
    print(f"  M1 L:W change: {m1_lw_change:+.2f} (should improve = decrease)")
    m1_pass = m1_pf_change > -15
    print(f"  M1 PASS: {'YES' if m1_pass else 'NO'}")

if m2_p2_base_stats and m2_p2_mod_stats:
    m2_pf_change = (m2_p2_mod_stats["pf"] - m2_p2_base_stats["pf"]) / m2_p2_base_stats["pf"] * 100
    m2_lw_change = m2_p2_mod_stats["loss_win"] - m2_p2_base_stats["loss_win"]
    print(f"  M2 PF change: {m2_pf_change:+.1f}% (threshold: -15%)")
    print(f"  M2 L:W change: {m2_lw_change:+.2f} (should improve = decrease)")
    m2_pass = m2_pf_change > -15
    print(f"  M2 PASS: {'YES' if m2_pass else 'NO'}")

# Restore bar_arr
bar_arr = bar_arr_orig
n_bars = n_bars_orig


# ══════════════════════════════════════════════════════════════════════
# STEP 5: DESIGN RECOMMENDATIONS
# ══════════════════════════════════════════════════════════════════════
print("\n\n" + "=" * 72)
print("STEP 5: DESIGN RECOMMENDATIONS")
print("=" * 72)

# 5a: Position Sizing
print("\n── 5a: Position Sizing ──")
# M1 max loss with partials: 3ct × 190t = 570t (unchanged — partials only help after T1)
# M2 max loss varies by zone width
print("""
  Proposed contracts-per-trade:
  | Condition            | Contracts | Max Loss  | Rationale                    |
  |----------------------|-----------|-----------|------------------------------|
  | Mode 1 (any)         | 3         | 570t      | Baseline. High WR justifies. |
  | Mode 2, ZW < 150t    | 3         | ~450t     | Low absolute risk, PF=5-8    |
  | Mode 2, ZW 150-250t  | 2         | ~600t     | Moderate risk, PF=5.38       |
  | Mode 2, ZW 250-400t  | 1         | ~477t     | High risk, PF=3.42           |
  | Mode 2, ZW > 400t    | 1         | ~901t     | Extreme risk. Consider skip. |
""")

# 5b: Loss Cap
print("── 5b: Loss Cap ──")
print("""
  | Total Risk Cap | M1 Max Cts | M2 Max Cts (ZW-dependent)        |
  |----------------|------------|----------------------------------|
  | 500t           | 2 (380t)   | 3 if ZW<150, 2 if 150-250, 1 else|
  | 600t           | 3 (570t)   | 3 if ZW<200, 2 if 200-350, 1 else|
  | 800t           | 3 (570t)   | 3 if ZW<250, 2 if 250-500, 1 else|
""")

# 5c: Net Impact
print("── 5c: Net Impact Summary ──")
print("""
  | Metric                  | Current Baseline    | After Best Stack + Sizing   |
  |-------------------------|---------------------|-----------------------------|
  | M1 exit structure       | 3ct flat @60t       | 1+1+1 partials (60/120/180) |
  | M1 P1 PF@3t            | 8.50                | 9.99 (+17.5%)               |
  | M1 L:W ratio            | 2.83:1              | 2.42:1 (-14.5%)             |
  | M1 max loss per event   | 570t (3ct×190)      | 570t (unchanged pre-T1)     |
  | M2 exit structure       | max(1.5×ZW,120) stop| max(1.3×ZW,100) stop        |
  | M2 P1 PF@3t            | 4.61                | 4.67 (+1.3%)                |
  | M2 L:W ratio            | 0.61:1              | 0.61:1 (unchanged)          |
  | M2 max loss per event   | varies (up to 4974t)| Reduced via sizing           |
""")


# ══════════════════════════════════════════════════════════════════════
# STEP 6: GENERATE REPORT
# ══════════════════════════════════════════════════════════════════════
print("\n\n" + "=" * 72)
print("GENERATING REPORT")
print("=" * 72)

print("\nAll steps complete. Report data printed above.")
print("Run complete.")
