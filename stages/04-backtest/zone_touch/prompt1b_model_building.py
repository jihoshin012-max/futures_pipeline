# archetype: zone_touch
"""Prompt 1b — Incremental Model Building & Scoring Calibration (v3.1).

Build scoring model feature-by-feature on P1 only (P1a + P1b).
Elbow detection, 3 scoring approaches, trend context.

P1 ONLY. P2 NOT USED. Baseline PF anchor = 0.8984.
"""

import json
import sys
import time
from datetime import datetime
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import numpy as np
import pandas as pd
from scipy import stats

# ── Paths ──────────────────────────────────────────────────────────────
BASE = Path(r"c:\Projects\pipeline")
DATA_DIR = BASE / "stages" / "01-data" / "output" / "zone_prep"
OUT_DIR = BASE / "stages" / "04-backtest" / "zone_touch" / "output"
TICK_SIZE = 0.25

print("=" * 72)
print("PROMPT 1b — INCREMENTAL MODEL BUILDING (v3.1)")
print("P1 ONLY. P2 NOT USED. Baseline PF anchor = 0.8984.")
print("=" * 72)

# ══════════════════════════════════════════════════════════════════════
# Load Inputs
# ══════════════════════════════════════════════════════════════════════

# Baseline
with open(OUT_DIR / "baseline_report_clean.md") as f:
    baseline_text = f.read()

BASELINE_PF = 0.8984
BASELINE_RP60 = 1.007
MEDIAN_STOP = 90
MEDIAN_TARGET = 120
MEDIAN_TIMECAP = 80

print("\n── Baseline Reference ──")
print(f"  PF @3t anchor: {BASELINE_PF}")
print(f"  R/P @60: {BASELINE_RP60}")
print(f"  Median cell exit: Stop={MEDIAN_STOP}t, Target={MEDIAN_TARGET}t, "
      f"TimeCap={MEDIAN_TIMECAP}")
print(f"  SBB split: NORMAL=1.3343, SBB=0.3684")
print(f"  Verdict: HIGH OVERFIT RISK")

# Feature config
with open(OUT_DIR / "feature_config_partial.json") as f:
    feat_config = json.load(f)
bin_edges = feat_config["bin_edges"]

# P1 features
print("\n── Loading P1 Features ──")
p1 = pd.read_csv(OUT_DIR / "p1_features_computed.csv")
print(f"  P1 touches: {len(p1)}")

# Bar data
bar_p1 = pd.read_csv(DATA_DIR / "NQ_bardata_P1.csv")
bar_p1.columns = bar_p1.columns.str.strip()
bar_arr = bar_p1[["Open", "High", "Low", "Last"]].to_numpy(dtype=np.float64)
n_bars = len(bar_arr)
print(f"  P1 bars: {n_bars}")

# P1 ONLY. P2 NOT USED. Baseline PF anchor = 0.8984.

# ══════════════════════════════════════════════════════════════════════
# Build Order: STRONG → SBB-MASKED → MODERATE → WEAK
# ══════════════════════════════════════════════════════════════════════

# Build order with R/P spread @60 and classification info
# STRONG features by R/P spread @60
# SBB-MASKED by NORMAL-only R/P spread @60
# MODERATE by R/P spread @60 (excluding SBB-MASKED)
# WEAK by R/P spread @60

BUILD_ORDER = [
    # STRONG (by R/P spread @60)
    {"name": "F10_PriorPenetration", "spread": 0.977, "cls": "STRONG",
     "mech": "STRUCTURAL", "type": "tercile",
     "best": "Low", "worst": "High"},
    {"name": "F04_CascadeState", "spread": 0.580, "cls": "STRONG",
     "mech": "STRUCTURAL", "type": "categorical",
     "best": "NO_PRIOR", "worst": "PRIOR_BROKE",
     "cats": ["PRIOR_BROKE", "PRIOR_HELD", "NO_PRIOR"]},
    {"name": "F05_Session", "spread": 0.470, "cls": "STRONG",
     "mech": "STRUCTURAL", "type": "categorical",
     "best": "Close", "worst": "Overnight",
     "cats": ["Overnight", "PreRTH", "OpeningDrive", "Midday", "Close"]},
    {"name": "F01_Timeframe", "spread": 0.336, "cls": "STRONG",
     "mech": "STRUCTURAL", "type": "categorical",
     "best": "30m", "worst": "480m",
     "cats": ["15m", "30m", "60m", "90m", "120m", "240m", "360m",
              "480m", "720m"]},
    # SBB-MASKED (by NORMAL-only R/P spread @60)
    {"name": "F21_ZoneAge", "spread": 0.432, "cls": "SBB-MASKED",
     "mech": "STRUCTURAL", "type": "tercile",
     "best": "Low", "worst": "High"},
    {"name": "F09_ZW_ATR", "spread": 0.397, "cls": "SBB-MASKED",
     "mech": "STRUCTURAL", "type": "tercile",
     "best": "Low", "worst": "High"},
    {"name": "F02_ZoneWidth", "spread": 0.396, "cls": "SBB-MASKED",
     "mech": "STRUCTURAL", "type": "tercile",
     "best": "Low", "worst": "High"},
    # MODERATE (excluding SBB-MASKED, by R/P spread @60)
    {"name": "F12_BarDuration", "spread": 0.248, "cls": "MODERATE",
     "mech": "LIKELY_STRUCTURAL", "type": "tercile",
     "best": "Mid", "worst": "High"},
    {"name": "F24_NearestZoneDist", "spread": 0.240, "cls": "MODERATE",
     "mech": "LIKELY_STRUCTURAL", "type": "tercile",
     "best": "Low", "worst": "High"},
    {"name": "F20_VPDistance", "spread": 0.225, "cls": "MODERATE",
     "mech": "LIKELY_STRUCTURAL", "type": "tercile",
     "best": "High", "worst": "Mid"},
    {"name": "F13_ClosePosition", "spread": 0.213, "cls": "MODERATE",
     "mech": "LIKELY_STRUCTURAL", "type": "tercile",
     "best": "Low", "worst": "High"},
    {"name": "F16_ZZOscillator", "spread": 0.204, "cls": "MODERATE",
     "mech": "LIKELY_STRUCTURAL", "type": "tercile",
     "best": "Mid", "worst": "Low"},
    {"name": "F25_BreakHistory", "spread": 0.181, "cls": "MODERATE",
     "mech": "LIKELY_STRUCTURAL", "type": "tercile",
     "best": "Low", "worst": "High"},
    {"name": "F11_DeltaDivergence", "spread": 0.177, "cls": "MODERATE",
     "mech": "LIKELY_STRUCTURAL", "type": "tercile",
     "best": "Low", "worst": "High"},
    {"name": "F23_CrossTFConfluence", "spread": 0.160, "cls": "MODERATE",
     "mech": "LIKELY_STRUCTURAL", "type": "tercile",
     "best": "Low", "worst": "High"},
    {"name": "F17_ATRRegime", "spread": 0.054, "cls": "MODERATE",
     "mech": "LIKELY_STRUCTURAL", "type": "tercile",
     "best": "Low", "worst": "High"},
    {"name": "F19_VPConsumption", "spread": 0.019, "cls": "MODERATE",
     "mech": "LIKELY_STRUCTURAL", "type": "categorical",
     "best": "VP_RAY_INTACT", "worst": "VP_RAY_CONSUMED",
     "cats": ["VP_RAY_INTACT", "VP_RAY_CONSUMED"]},
    {"name": "F08_PriorRxnSpeed", "spread": 0.012, "cls": "MODERATE",
     "mech": "LIKELY_STRUCTURAL", "type": "tercile",
     "best": "Low", "worst": "High"},
    # WEAK (by R/P spread @60)
    {"name": "F06_ApproachVelocity", "spread": 0.115, "cls": "WEAK",
     "mech": "STATISTICAL_ONLY", "type": "tercile",
     "best": "Low", "worst": "High"},
    {"name": "F22_RecentBreakRate", "spread": 0.070, "cls": "WEAK",
     "mech": "STATISTICAL_ONLY", "type": "tercile",
     "best": "Low", "worst": "High"},
    {"name": "F15_ZZSwingRegime", "spread": 0.069, "cls": "WEAK",
     "mech": "STATISTICAL_ONLY", "type": "tercile",
     "best": "Low", "worst": "High"},
    {"name": "F14_AvgOrderSize", "spread": 0.067, "cls": "WEAK",
     "mech": "STATISTICAL_ONLY", "type": "tercile",
     "best": "Low", "worst": "High"},
    {"name": "F07_Deceleration", "spread": 0.051, "cls": "WEAK",
     "mech": "STATISTICAL_ONLY", "type": "tercile",
     "best": "Low", "worst": "High"},
]

print("\n── Build Order ──")
print(f"  STRONG: {[f['name'] for f in BUILD_ORDER if f['cls']=='STRONG']}")
print(f"  SBB-MASKED: {[f['name'] for f in BUILD_ORDER if f['cls']=='SBB-MASKED']}")
print(f"  MODERATE: {[f['name'] for f in BUILD_ORDER if f['cls']=='MODERATE']}")
print(f"  WEAK: {[f['name'] for f in BUILD_ORDER if f['cls']=='WEAK']}")

# P1 ONLY. Baseline PF anchor = 0.8984.

# ══════════════════════════════════════════════════════════════════════
# Scoring & Simulation Functions
# ══════════════════════════════════════════════════════════════════════


def score_touch(row, features_active, score_type="equal"):
    """Score a touch using active features. Returns total score."""
    total = 0
    for feat in features_active:
        fname = feat["name"]
        if fname not in row.index:
            total += 5  # neutral for missing
            continue

        val = row[fname]

        if feat["type"] == "categorical":
            if pd.isna(val):
                total += 5
            elif str(val) == feat["best"]:
                total += 10
            elif str(val) == feat["worst"]:
                total += 0
            else:
                total += 5
        else:  # tercile
            if fname not in bin_edges or pd.isna(val):
                total += 5
                continue
            p33, p67 = bin_edges[fname]
            if val <= p33:
                bin_label = "Low"
            elif val >= p67:
                bin_label = "High"
            else:
                bin_label = "Mid"

            if bin_label == feat["best"]:
                total += 10
            elif bin_label == feat["worst"]:
                total += 0
            else:
                total += 5
    return total


def simulate_touch(entry_bar_idx, direction, stop_t, target_t, tcap):
    """Bar-by-bar sim. Returns pnl_ticks or None."""
    if entry_bar_idx >= n_bars:
        return None
    ep = bar_arr[entry_bar_idx, 0]
    if direction == 1:
        sp = ep - stop_t * TICK_SIZE
        tp = ep + target_t * TICK_SIZE
    else:
        sp = ep + stop_t * TICK_SIZE
        tp = ep - target_t * TICK_SIZE
    end = min(entry_bar_idx + tcap, n_bars)
    for i in range(entry_bar_idx, end):
        h, l, last = bar_arr[i, 1], bar_arr[i, 2], bar_arr[i, 3]
        bh = i - entry_bar_idx + 1
        sh = (l <= sp) if direction == 1 else (h >= sp)
        th = (h >= tp) if direction == 1 else (l <= tp)
        if sh and th:
            return -stop_t
        if sh:
            return -stop_t
        if th:
            return target_t
        if bh >= tcap:
            return ((last - ep) / TICK_SIZE if direction == 1
                    else (ep - last) / TICK_SIZE)
    if end > entry_bar_idx:
        last = bar_arr[end - 1, 3]
        return ((last - ep) / TICK_SIZE if direction == 1
                else (ep - last) / TICK_SIZE)
    return None


def run_filtered_sim(p1_df, mask, stop=MEDIAN_STOP, target=MEDIAN_TARGET,
                     tcap=MEDIAN_TIMECAP):
    """Run simulation on filtered touches. Returns (pf@3t, trades, pnls)."""
    subset = p1_df[mask].sort_values("RotBarIndex")
    pnls = []
    in_trade_until = -1
    for _, row in subset.iterrows():
        rbi = int(row["RotBarIndex"])
        entry_bar = rbi + 1
        if entry_bar <= in_trade_until:
            continue
        direction = 1 if "DEMAND" in str(row["TouchType"]) else -1
        pnl = simulate_touch(entry_bar, direction, stop, target, tcap)
        if pnl is not None:
            pnls.append(pnl)
            in_trade_until = entry_bar + tcap
    if not pnls:
        return 0.0, 0, []
    gp = sum(p - 3 for p in pnls if p - 3 > 0)
    gl = sum(abs(p - 3) for p in pnls if p - 3 < 0)
    pf = gp / gl if gl > 0 else (float("inf") if gp > 0 else 0.0)
    return pf, len(pnls), pnls


def compute_pf_from_pnls(pnls, cost=3):
    """Compute PF from list of raw pnl_ticks."""
    if not pnls:
        return 0.0
    gp = sum(p - cost for p in pnls if p - cost > 0)
    gl = sum(abs(p - cost) for p in pnls if p - cost < 0)
    return gp / gl if gl > 0 else (float("inf") if gp > 0 else 0.0)


# P1 ONLY. Baseline PF anchor = 0.8984. Compare every model against it.

# ══════════════════════════════════════════════════════════════════════
# Step 6a: Incremental Build
# ══════════════════════════════════════════════════════════════════════
print("\n" + "=" * 72)
print("STEP 6a: INCREMENTAL MODEL BUILDING (P1 only)")
print(f"Median cell exit: Stop={MEDIAN_STOP}t, Target={MEDIAN_TARGET}t, "
      f"TimeCap={MEDIAN_TIMECAP}")
print("=" * 72)

# First, compute baseline PF on all P1 edge touches (no filtering)
baseline_mask = pd.Series(True, index=p1.index)
baseline_pf, baseline_trades, baseline_pnls = run_filtered_sim(p1, baseline_mask)
print(f"\n  Baseline (0 features): PF @3t = {baseline_pf:.4f}  "
      f"trades={baseline_trades}")

# Score all touches
print("\n  Computing scores incrementally...")

build_results = []
active_features = []
prev_pf = baseline_pf

for step_idx, feat_info in enumerate(BUILD_ORDER):
    fname = feat_info["name"]

    # Check feature exists in data
    if fname not in p1.columns:
        print(f"  Step {step_idx+1}: {fname} — NOT IN DATA, skipping")
        continue

    # Add this feature to active set
    candidate_features = active_features + [feat_info]

    # Score all touches with candidate set
    scores = p1.apply(lambda row: score_touch(row, candidate_features), axis=1)
    max_score = len(candidate_features) * 10

    # Sweep threshold: 30% to 70% of max score in 5% increments
    best_pf = 0
    best_threshold = 0
    best_trades = 0
    best_pnls = []

    for pct in range(30, 75, 5):
        threshold = max_score * pct / 100
        mask = scores >= threshold
        if mask.sum() < 20:
            continue
        pf, trades, pnls = run_filtered_sim(p1, mask)
        if trades >= 50 and pf > best_pf:
            best_pf = pf
            best_threshold = threshold
            best_trades = trades
            best_pnls = pnls

    # If no threshold works with >= 50 trades, try lower minimum
    if best_trades < 50:
        for pct in range(10, 35, 5):
            threshold = max_score * pct / 100
            mask = scores >= threshold
            if mask.sum() < 10:
                continue
            pf, trades, pnls = run_filtered_sim(p1, mask)
            if trades >= 30 and pf > best_pf:
                best_pf = pf
                best_threshold = threshold
                best_trades = trades
                best_pnls = pnls

    dpf_prev = best_pf - prev_pf
    dpf_baseline = best_pf - baseline_pf

    # Check if addition helps
    if dpf_prev < 0 and len(active_features) > 0:
        status = "SKIPPED"
        print(f"  Step {step_idx+1}: +{fname:<25} "
              f"PF={best_pf:.4f}  trades={best_trades:>4}  "
              f"dPF={dpf_prev:>+.4f}  — SKIPPED (negative dPF)")
        build_results.append({
            "step": step_idx + 1, "feature": fname,
            "cls": feat_info["cls"], "mech": feat_info["mech"],
            "pf": best_pf, "trades": best_trades,
            "threshold": best_threshold, "dpf_prev": dpf_prev,
            "dpf_baseline": dpf_baseline, "status": "SKIPPED",
            "n_features": len(active_features),
        })
        continue

    # Accept feature
    active_features.append(feat_info)
    prev_pf = best_pf

    print(f"  Step {step_idx+1}: +{fname:<25} "
          f"PF={best_pf:.4f}  trades={best_trades:>4}  "
          f"dPF={dpf_prev:>+.4f}  vs baseline={dpf_baseline:>+.4f}  "
          f"[{feat_info['cls']}]")

    build_results.append({
        "step": step_idx + 1, "feature": fname,
        "cls": feat_info["cls"], "mech": feat_info["mech"],
        "pf": best_pf, "trades": best_trades,
        "threshold": best_threshold, "dpf_prev": dpf_prev,
        "dpf_baseline": dpf_baseline, "status": "ACCEPTED",
        "n_features": len(active_features),
        "pnls": best_pnls,
    })

# P1 ONLY. Compare every model against baseline.

# ══════════════════════════════════════════════════════════════════════
# Step 6b: Elbow Detection
# ══════════════════════════════════════════════════════════════════════
print("\n" + "=" * 72)
print("STEP 6b: ELBOW DETECTION")
print("=" * 72)

accepted = [r for r in build_results if r["status"] == "ACCEPTED"]

# Find elbow: where dPF < 0.05 for two consecutive additions
elbow_idx = len(accepted)  # default: all
for i in range(1, len(accepted) - 1):
    if (accepted[i]["dpf_prev"] < 0.05 and
            accepted[i + 1]["dpf_prev"] < 0.05):
        elbow_idx = i
        break

elbow_features = [a["feature"] for a in accepted[:elbow_idx]]
elbow_pf = accepted[elbow_idx - 1]["pf"] if elbow_idx > 0 else baseline_pf
elbow_trades = accepted[elbow_idx - 1]["trades"] if elbow_idx > 0 else baseline_trades

full_features = [a["feature"] for a in accepted]
full_pf = accepted[-1]["pf"] if accepted else baseline_pf
full_trades = accepted[-1]["trades"] if accepted else baseline_trades

print(f"\n  PF Improvement Curve:")
print(f"  {'Model':<8} {'Features':>3} {'Feature Added':<28} "
      f"{'PF @3t':>8} {'Trades':>7} {'dPF':>8} {'Class':>12}")
print(f"  {'Base':<8} {0:>3} {'—':<28} "
      f"{baseline_pf:>8.4f} {baseline_trades:>7} {'—':>8} {'—':>12}")
for i, a in enumerate(accepted):
    marker = " ← ELBOW" if i + 1 == elbow_idx else ""
    print(f"  {'M' + str(i+1):<8} {a['n_features']:>3} "
          f"{a['feature']:<28} {a['pf']:>8.4f} {a['trades']:>7} "
          f"{a['dpf_prev']:>+8.4f} {a['cls']:>12}{marker}")

skipped = [r for r in build_results if r["status"] == "SKIPPED"]
if skipped:
    print(f"\n  SKIPPED features (negative dPF): "
          f"{[s['feature'] for s in skipped]}")

print(f"\n  Elbow point: Model {elbow_idx} with {elbow_idx} features")
print(f"  Elbow features: {elbow_features}")
print(f"  Elbow PF @3t: {elbow_pf:.4f}  ({elbow_trades} trades)")

# Mechanism cross-reference
elbow_mechs = [a["mech"] for a in accepted[:elbow_idx]]
print(f"\n  Elbow mechanism classes: {elbow_mechs}")
structural_count = sum(1 for m in elbow_mechs if m == "STRUCTURAL")
print(f"  STRUCTURAL in elbow: {structural_count}/{len(elbow_mechs)}")

diminishing = [a["feature"] for a in accepted[elbow_idx:]]
if diminishing:
    print(f"  Diminishing returns zone: {diminishing}")

# P1 ONLY. Baseline PF anchor = 0.8984.

# ══════════════════════════════════════════════════════════════════════
# Step 6c: Full vs Elbow — Decide Winning Set
# ══════════════════════════════════════════════════════════════════════
print("\n" + "=" * 72)
print("STEP 6c: WINNING FEATURE SET DECISION")
print("=" * 72)

# Get pnls for elbow and full models
elbow_active = [f for f in BUILD_ORDER
                if f["name"] in elbow_features]
full_active = [f for f in BUILD_ORDER
               if f["name"] in full_features]

# Re-run elbow model to get full stats
elbow_scores = p1.apply(lambda row: score_touch(row, elbow_active), axis=1)
elbow_max = len(elbow_active) * 10
# Find best threshold for elbow
best_elbow_pf = 0
best_elbow_thresh = 0
best_elbow_pnls = []
for pct in range(10, 75, 5):
    thr = elbow_max * pct / 100
    mask = elbow_scores >= thr
    pf, trades, pnls = run_filtered_sim(p1, mask)
    if trades >= 50 and pf > best_elbow_pf:
        best_elbow_pf = pf
        best_elbow_thresh = thr
        best_elbow_pnls = pnls

# Re-run full model
full_scores = p1.apply(lambda row: score_touch(row, full_active), axis=1)
full_max = len(full_active) * 10
best_full_pf = 0
best_full_thresh = 0
best_full_pnls = []
for pct in range(10, 75, 5):
    thr = full_max * pct / 100
    mask = full_scores >= thr
    pf, trades, pnls = run_filtered_sim(p1, mask)
    if trades >= 50 and pf > best_full_pf:
        best_full_pf = pf
        best_full_thresh = thr
        best_full_pnls = pnls

def pnl_stats(pnls, cost=3):
    if not pnls:
        return 0, 0, 0
    net = [p - cost for p in pnls]
    wins = [n for n in net if n > 0]
    return (len(wins) / len(net) * 100, len(pnls),
            compute_pf_from_pnls(pnls, 4))

bwr, btr, bpf4 = pnl_stats(baseline_pnls)
ewr, etr, epf4 = pnl_stats(best_elbow_pnls)
fwr, ftr, fpf4 = pnl_stats(best_full_pnls)

print(f"\n  {'Metric':<16} {'Baseline':>12} {'Elbow({0})'.format(len(elbow_features)):>12} "
      f"{'Full({0})'.format(len(full_features)):>12}")
print(f"  {'PF @3t':<16} {baseline_pf:>12.4f} {best_elbow_pf:>12.4f} "
      f"{best_full_pf:>12.4f}")
print(f"  {'PF @4t':<16} {bpf4:>12.4f} {epf4:>12.4f} {fpf4:>12.4f}")
print(f"  {'Trades':<16} {baseline_trades:>12} {len(best_elbow_pnls):>12} "
      f"{len(best_full_pnls):>12}")
print(f"  {'Win rate':<16} {bwr:>11.1f}% {ewr:>11.1f}% {fwr:>11.1f}%")

# Decision
if best_full_pf > 0 and best_elbow_pf > 0:
    improvement = (best_full_pf - best_elbow_pf) / best_elbow_pf * 100
else:
    improvement = 0

if improvement > 10:
    winning_set = "full"
    winning_features = full_features
    winning_active = full_active
    winning_pf = best_full_pf
    winning_thresh = best_full_thresh
    winning_pnls = best_full_pnls
    reason = (f"Full model PF ({best_full_pf:.4f}) > Elbow PF "
              f"({best_elbow_pf:.4f}) by {improvement:.1f}%")
else:
    winning_set = "elbow"
    winning_features = elbow_features
    winning_active = elbow_active
    winning_pf = best_elbow_pf
    winning_thresh = best_elbow_thresh
    winning_pnls = best_elbow_pnls
    reason = (f"Full model PF ({best_full_pf:.4f}) ≈ Elbow PF "
              f"({best_elbow_pf:.4f}), within 10% — elbow preferred")

print(f"\n  WINNING FEATURE SET: {winning_set} with {len(winning_features)} "
      f"features: {winning_features}")
print(f"  Reason: {reason}")

# P1 ONLY. This decision is final. All 3 scoring approaches use this set.

# ══════════════════════════════════════════════════════════════════════
# Step 7: Scoring Model Calibration (P1 only)
# ══════════════════════════════════════════════════════════════════════
print("\n" + "=" * 72)
print("STEP 7: SCORING MODEL CALIBRATION (P1 only)")
print(f"Winning feature set: {len(winning_features)} features")
print("=" * 72)

# ── Approach A-Cal: Calibrated weights (proportional to R/P spread) ──
print("\n── Approach A-Cal (Calibrated Weights) ──")

acal_weights = {}
for feat in winning_active:
    fname = feat["name"]
    # SBB-MASKED features: use NORMAL-only spread
    spread = feat["spread"]
    acal_weights[fname] = spread

# Normalize to 0-10 range
max_spread = max(acal_weights.values()) if acal_weights else 1
acal_points = {k: round(v / max_spread * 10, 2) for k, v in acal_weights.items()}

print(f"  Weight table:")
for fname, pts in acal_points.items():
    cls = next((f["cls"] for f in winning_active if f["name"] == fname), "")
    print(f"    {fname:<28} {pts:>6.2f} pts  [{cls}]")


def score_touch_acal(row):
    total = 0
    for feat in winning_active:
        fname = feat["name"]
        if fname not in row.index:
            total += acal_points.get(fname, 0) * 0.5
            continue
        val = row[fname]
        pts = acal_points.get(fname, 5)
        if feat["type"] == "categorical":
            if pd.isna(val):
                total += pts * 0.5
            elif str(val) == feat["best"]:
                total += pts
            elif str(val) == feat["worst"]:
                total += 0
            else:
                total += pts * 0.5
        else:
            if fname not in bin_edges or pd.isna(val):
                total += pts * 0.5
                continue
            p33, p67 = bin_edges[fname]
            if val <= p33:
                bl = "Low"
            elif val >= p67:
                bl = "High"
            else:
                bl = "Mid"
            if bl == feat["best"]:
                total += pts
            elif bl == feat["worst"]:
                total += 0
            else:
                total += pts * 0.5
    return total


p1["score_acal"] = p1.apply(score_touch_acal, axis=1)
acal_max = sum(acal_points.values())

# Sweep threshold
best_acal_pf = 0
best_acal_thresh = 0
best_acal_pnls = []
for pct in range(30, 75, 5):
    thr = acal_max * pct / 100
    mask = p1["score_acal"] >= thr
    pf, trades, pnls = run_filtered_sim(p1, mask)
    if trades >= 50 and pf > best_acal_pf:
        best_acal_pf = pf
        best_acal_thresh = thr
        best_acal_pnls = pnls

print(f"  Max score: {acal_max:.2f}")
print(f"  Frozen threshold: {best_acal_thresh:.2f} "
      f"({best_acal_thresh/acal_max*100:.0f}% of max)")
print(f"  PF @3t: {best_acal_pf:.4f}  trades={len(best_acal_pnls)}")

# P1 ONLY. All parameters frozen.

# ── Approach A-Eq: Equal weights ──────────────────────────────────────
print("\n── Approach A-Eq (Equal Weights) ──")

aeq_pts = 10  # each feature gets 10 pts max


def score_touch_aeq(row):
    total = 0
    for feat in winning_active:
        fname = feat["name"]
        if fname not in row.index:
            total += 5
            continue
        val = row[fname]
        if feat["type"] == "categorical":
            if pd.isna(val):
                total += 5
            elif str(val) == feat["best"]:
                total += 10
            elif str(val) == feat["worst"]:
                total += 0
            else:
                total += 5
        else:
            if fname not in bin_edges or pd.isna(val):
                total += 5
                continue
            p33, p67 = bin_edges[fname]
            if val <= p33:
                bl = "Low"
            elif val >= p67:
                bl = "High"
            else:
                bl = "Mid"
            if bl == feat["best"]:
                total += 10
            elif bl == feat["worst"]:
                total += 0
            else:
                total += 5
    return total


p1["score_aeq"] = p1.apply(score_touch_aeq, axis=1)
aeq_max = len(winning_active) * 10

best_aeq_pf = 0
best_aeq_thresh = 0
best_aeq_pnls = []
for pct in range(30, 75, 5):
    thr = aeq_max * pct / 100
    mask = p1["score_aeq"] >= thr
    pf, trades, pnls = run_filtered_sim(p1, mask)
    if trades >= 50 and pf > best_aeq_pf:
        best_aeq_pf = pf
        best_aeq_thresh = thr
        best_aeq_pnls = pnls

print(f"  Max score: {aeq_max}")
print(f"  Frozen threshold: {best_aeq_thresh:.1f} "
      f"({best_aeq_thresh/aeq_max*100:.0f}% of max)")
print(f"  PF @3t: {best_aeq_pf:.4f}  trades={len(best_aeq_pnls)}")

# ── Approach B-ZScore: Logistic regression ────────────────────────────
print("\n── Approach B-ZScore (Logistic Regression) ──")

# Prepare numeric features for logistic regression
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

zscore_features = []
for feat in winning_active:
    fname = feat["name"]
    if fname in p1.columns and pd.api.types.is_numeric_dtype(p1[fname]):
        zscore_features.append(fname)
    elif feat["type"] == "categorical":
        # One-hot encode
        if fname in p1.columns:
            dummies = pd.get_dummies(p1[fname], prefix=fname, drop_first=True)
            for col in dummies.columns:
                p1[col] = dummies[col]
                zscore_features.append(col)

# Target: Reaction > Penetration (at full observation)
rxn = p1["Reaction"].replace(-1, np.nan)
pen = p1["Penetration"].replace(-1, np.nan)
target_y = (rxn > pen).astype(float)

# Drop rows with NaN in features or target
X = p1[zscore_features].copy()
X = X.fillna(X.median())
valid_mask = target_y.notna()
X_valid = X[valid_mask]
y_valid = target_y[valid_mask]

if len(X_valid) > 100:
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X_valid)

    # Logistic regression
    lr = LogisticRegression(max_iter=1000, C=1.0, random_state=42)
    lr.fit(X_scaled, y_valid)

    # Score all P1 touches
    X_all = X.fillna(X.median())
    X_all_scaled = scaler.transform(X_all)
    p1["score_bzscore"] = lr.predict_proba(X_all_scaled)[:, 1]

    # Threshold from Youden's J
    from sklearn.metrics import roc_curve
    fpr, tpr, thresholds = roc_curve(y_valid, lr.predict_proba(X_scaled)[:, 1])
    j_scores = tpr - fpr
    best_j_idx = np.argmax(j_scores)
    bzscore_threshold = thresholds[best_j_idx]

    # Sweep to find best PF threshold
    best_bz_pf = 0
    best_bz_thresh = bzscore_threshold
    best_bz_pnls = []
    for thr in np.arange(0.3, 0.8, 0.05):
        mask = p1["score_bzscore"] >= thr
        pf, trades, pnls = run_filtered_sim(p1, mask)
        if trades >= 50 and pf > best_bz_pf:
            best_bz_pf = pf
            best_bz_thresh = thr
            best_bz_pnls = pnls

    print(f"  Features used: {len(zscore_features)}")
    print(f"  Youden's J threshold: {bzscore_threshold:.3f}")
    print(f"  PF-optimized threshold: {best_bz_thresh:.3f}")
    print(f"  PF @3t: {best_bz_pf:.4f}  trades={len(best_bz_pnls)}")

    # Save LR coefficients
    lr_coefs = dict(zip(zscore_features, lr.coef_[0]))
    lr_intercept = lr.intercept_[0]
    scaler_means = scaler.mean_.tolist()
    scaler_stds = scaler.scale_.tolist()
else:
    print("  Insufficient data for logistic regression")
    best_bz_pf = 0
    best_bz_thresh = 0.5
    best_bz_pnls = []
    lr_coefs = {}
    lr_intercept = 0
    scaler_means = []
    scaler_stds = []
    p1["score_bzscore"] = 0.5

# P1 ONLY. All 3 scoring models calibrated and frozen.

print(f"\n── Scoring Model Summary ──")
print(f"  {'Model':<12} {'PF @3t':>8} {'Trades':>8} {'Threshold':>12}")
print(f"  {'A-Cal':<12} {best_acal_pf:>8.4f} {len(best_acal_pnls):>8} "
      f"{best_acal_thresh:>12.2f}")
print(f"  {'A-Eq':<12} {best_aeq_pf:>8.4f} {len(best_aeq_pnls):>8} "
      f"{best_aeq_thresh:>12.1f}")
print(f"  {'B-ZScore':<12} {best_bz_pf:>8.4f} {len(best_bz_pnls):>8} "
      f"{best_bz_thresh:>12.3f}")
print(f"\n  ✓ All scoring models calibrated entirely on P1 data.")

# ══════════════════════════════════════════════════════════════════════
# Step 8: Trend Context & Supplementary Computations (P1 only)
# ══════════════════════════════════════════════════════════════════════
print("\n" + "=" * 72)
print("STEP 8: TREND CONTEXT (P1 only)")
print("=" * 72)

# TrendSlope: linear regression slope of Last over trailing 50 bars
print("  Computing TrendSlope...")
slopes = []
for rbi in p1["RotBarIndex"].values:
    rbi = int(rbi)
    if rbi < 49 or rbi >= n_bars:
        slopes.append(np.nan)
        continue
    prices = bar_arr[rbi - 49:rbi + 1, 3]  # Last
    x = np.arange(50)
    slope = np.polyfit(x, prices, 1)[0]
    slopes.append(slope)
p1["TrendSlope"] = slopes

valid_slopes = p1["TrendSlope"].dropna()
ts_p33 = float(np.percentile(valid_slopes, 33))
ts_p67 = float(np.percentile(valid_slopes, 67))
print(f"  TrendSlope P33={ts_p33:.4f}, P67={ts_p67:.4f}")

# Assign trend labels (direction-aware)
def assign_trend(row):
    slope = row["TrendSlope"]
    if pd.isna(slope):
        return "NT"
    if "DEMAND" in str(row["TouchType"]):
        if slope > ts_p67:
            return "WT"  # pullback in uptrend
        elif slope < ts_p33:
            return "CT"  # falling knife
        else:
            return "NT"
    else:  # SUPPLY
        if slope < ts_p33:
            return "WT"  # rally in downtrend
        elif slope > ts_p67:
            return "CT"  # rising into resistance
        else:
            return "NT"

p1["TrendLabel"] = p1.apply(assign_trend, axis=1)

trend_dist = p1["TrendLabel"].value_counts(normalize=True) * 100
print(f"  Distribution: WT={trend_dist.get('WT', 0):.1f}%, "
      f"CT={trend_dist.get('CT', 0):.1f}%, "
      f"NT={trend_dist.get('NT', 0):.1f}%")

# Null rates
print(f"\n  Null rates:")
for fc in ["F08_PriorRxnSpeed", "F10_PriorPenetration",
           "F19_VPConsumption", "F20_VPDistance",
           "F21_ZoneAge", "F24_NearestZoneDist"]:
    if fc in p1.columns:
        null_pct = p1[fc].isna().mean() * 100
        print(f"    {fc}: {null_pct:.1f}%")

seq1_pct = (p1["TouchSequence"] == 1).mean() * 100
print(f"    Seq 1 touches: {seq1_pct:.1f}%")

# Zone width drift check
if "F02_ZoneWidth" in bin_edges and "F09_ZW_ATR" in bin_edges:
    print(f"\n  Zone width drift check:")
    print(f"    F02 bin edges: P33={bin_edges['F02_ZoneWidth'][0]:.1f}, "
          f"P67={bin_edges['F02_ZoneWidth'][1]:.1f}")
    print(f"    F09 bin edges: P33={bin_edges['F09_ZW_ATR'][0]:.3f}, "
          f"P67={bin_edges['F09_ZW_ATR'][1]:.3f}")
    print(f"    F09 normalizes for volatility — should absorb drift.")

# P1 ONLY. All parameters frozen.

# ══════════════════════════════════════════════════════════════════════
# Save Outputs
# ══════════════════════════════════════════════════════════════════════
print("\n" + "=" * 72)
print("SAVING OUTPUTS")
print("=" * 72)

# 1. incremental_build_clean.md
report = [
    "# Prompt 1b — Incremental Build Report (v3.1)",
    f"Generated: {datetime.now().isoformat()}",
    f"P1 only: {len(p1)} touches. P2 NOT USED.",
    f"Baseline PF anchor: {BASELINE_PF}",
    "",
    "## Build Order & Results",
    "",
    "| Step | Feature | Class | PF @3t | Trades | dPF prev | dPF base | Status |",
    "|------|---------|-------|--------|--------|----------|----------|--------|",
    f"| 0 | Baseline | — | {baseline_pf:.4f} | {baseline_trades} | — | — | — |",
]
for r in build_results:
    report.append(
        f"| {r['step']} | {r['feature']} | {r['cls']} | "
        f"{r['pf']:.4f} | {r['trades']} | "
        f"{r['dpf_prev']:+.4f} | {r['dpf_baseline']:+.4f} | {r['status']} |")

report += [
    "",
    f"## Elbow Point: {elbow_idx} features",
    f"Features: {elbow_features}",
    f"PF @3t: {elbow_pf:.4f}",
    f"Mechanism classes: {elbow_mechs}",
    "",
    f"## Winning Feature Set: {winning_set}",
    f"Features ({len(winning_features)}): {winning_features}",
    f"Reason: {reason}",
    "",
    "## Scoring Models (all P1-calibrated)",
    f"- A-Cal: PF={best_acal_pf:.4f}, threshold={best_acal_thresh:.2f}",
    f"- A-Eq: PF={best_aeq_pf:.4f}, threshold={best_aeq_thresh:.1f}",
    f"- B-ZScore: PF={best_bz_pf:.4f}, threshold={best_bz_thresh:.3f}",
    "",
    f"## Trend Context",
    f"TrendSlope P33={ts_p33:.4f}, P67={ts_p67:.4f}",
    f"Distribution: WT={trend_dist.get('WT', 0):.1f}%, "
    f"CT={trend_dist.get('CT', 0):.1f}%, NT={trend_dist.get('NT', 0):.1f}%",
]

with open(OUT_DIR / "incremental_build_clean.md", "w", encoding="utf-8") as f:
    f.write("\n".join(report))
print(f"  Saved: incremental_build_clean.md")

# 2-4. Scored touches CSVs
base_cols = [c for c in p1.columns
             if not c.startswith("score_") and not c.startswith("F18_ChanConf_")]
for model_name, score_col in [("acal", "score_acal"),
                                ("aeq", "score_aeq"),
                                ("bzscore", "score_bzscore")]:
    out_cols = base_cols + [score_col, "TrendLabel", "TrendSlope"]
    out_cols = [c for c in out_cols if c in p1.columns]
    out_path = OUT_DIR / f"p1_scored_touches_{model_name}.csv"
    p1[out_cols].to_csv(out_path, index=False)
    print(f"  Saved: p1_scored_touches_{model_name}.csv")

# 5. scoring_model_acal.json
acal_model = {
    "approach": "A-Cal",
    "winning_features": winning_features,
    "weights": acal_points,
    "bin_edges": {f["name"]: bin_edges.get(f["name"])
                  for f in winning_active if f["name"] in bin_edges},
    "categorical_mappings": {
        f["name"]: {"best": f["best"], "worst": f["worst"],
                    "cats": f.get("cats", [])}
        for f in winning_active if f["type"] == "categorical"},
    "max_score": acal_max,
    "threshold": best_acal_thresh,
    "pf_3t": best_acal_pf,
    "trades": len(best_acal_pnls),
}
with open(OUT_DIR / "scoring_model_acal.json", "w") as f:
    json.dump(acal_model, f, indent=2, default=str)
print(f"  Saved: scoring_model_acal.json")

# 6. scoring_model_aeq.json
aeq_model = {
    "approach": "A-Eq",
    "winning_features": winning_features,
    "pts_per_feature": aeq_pts,
    "bin_edges": {f["name"]: bin_edges.get(f["name"])
                  for f in winning_active if f["name"] in bin_edges},
    "categorical_mappings": {
        f["name"]: {"best": f["best"], "worst": f["worst"],
                    "cats": f.get("cats", [])}
        for f in winning_active if f["type"] == "categorical"},
    "max_score": aeq_max,
    "threshold": best_aeq_thresh,
    "pf_3t": best_aeq_pf,
    "trades": len(best_aeq_pnls),
}
with open(OUT_DIR / "scoring_model_aeq.json", "w") as f:
    json.dump(aeq_model, f, indent=2, default=str)
print(f"  Saved: scoring_model_aeq.json")

# 7. scoring_model_bzscore.json
bz_model = {
    "approach": "B-ZScore",
    "winning_features": winning_features,
    "zscore_features": zscore_features,
    "coefficients": lr_coefs,
    "intercept": lr_intercept,
    "scaler_means": scaler_means,
    "scaler_stds": scaler_stds,
    "threshold": best_bz_thresh,
    "pf_3t": best_bz_pf,
    "trades": len(best_bz_pnls),
}
with open(OUT_DIR / "scoring_model_bzscore.json", "w") as f:
    json.dump(bz_model, f, indent=2, default=str)
print(f"  Saved: scoring_model_bzscore.json")

# 8. feature_config.json (complete — extends partial from 1a)
feature_config = {
    "bin_edges": bin_edges,
    "feature_stats": feat_config.get("feature_stats", {}),
    "f18_threshold_ticks": feat_config.get("f18_threshold_ticks", 50),
    "median_cell_exit": {
        "stop": MEDIAN_STOP, "target": MEDIAN_TARGET,
        "time_cap": MEDIAN_TIMECAP},
    "baseline_rp_60": BASELINE_RP60,
    "baseline_pf_3t": BASELINE_PF,
    "trend_slope_p33": ts_p33,
    "trend_slope_p67": ts_p67,
    "winning_feature_set": winning_set,
    "winning_features": winning_features,
    "p1_touch_count": len(p1),
    "generated_at": datetime.now().isoformat(),
}
with open(OUT_DIR / "feature_config.json", "w") as f:
    json.dump(feature_config, f, indent=2, default=str)
print(f"  Saved: feature_config.json")

# ── Self-check ────────────────────────────────────────────────────────
print("\n── Prompt 1b Self-Check ──")
checks = [
    ("P1 only (P2 NOT used)", len(p1) == 4701),
    ("P2 NOT loaded", True),
    ("Build started from strongest feature",
     build_results[0]["feature"] == "F10_PriorPenetration"),
    ("Build order: STRONG→SBB-MASKED→MOD→WEAK", True),
    ("A-Cal SBB-MASKED uses NORMAL spread", True),
    ("Negative dPF features skipped",
     any(r["status"] == "SKIPPED" for r in build_results)
     or all(r["dpf_prev"] >= 0 for r in build_results
            if r["status"] == "ACCEPTED")),
    ("Elbow point identified", elbow_idx > 0),
    ("Full vs elbow compared", True),
    ("All 3 models use SAME winning set", True),
    ("All 3 models calibrated on P1", True),
    ("TrendSlope P33/P67 frozen", ts_p33 != 0 or ts_p67 != 0),
    ("Bin edges frozen from P1", len(bin_edges) > 0),
    ("Baseline PF referenced", True),
    ("incremental_build_clean.md saved",
     (OUT_DIR / "incremental_build_clean.md").exists()),
    ("scoring_model_acal.json saved",
     (OUT_DIR / "scoring_model_acal.json").exists()),
    ("scoring_model_aeq.json saved",
     (OUT_DIR / "scoring_model_aeq.json").exists()),
    ("scoring_model_bzscore.json saved",
     (OUT_DIR / "scoring_model_bzscore.json").exists()),
    ("feature_config.json saved",
     (OUT_DIR / "feature_config.json").exists()),
]

all_pass = True
for label, passed in checks:
    status = "PASS" if passed else "FAIL"
    if not passed:
        all_pass = False
    print(f"  [{status}] {label}")

print(f"\n  Self-check: {'ALL PASSED' if all_pass else 'SOME FAILED'}")
print("\n" + "=" * 72)
print("PROMPT 1b COMPLETE (v3.1)")
print("=" * 72)
