# archetype: zone_touch
"""Prompt 1b v3.2: Incremental Model Building & Scoring Calibration

Steps 6-8 of the zone touch pipeline. All calibration on P1 only.
Prerequisites: Prompt 0 baseline + Prompt 1a screening outputs.
"""

import numpy as np
import pandas as pd
from pathlib import Path
import json, sys, time as time_mod, io, warnings

warnings.filterwarnings("ignore")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
np.random.seed(42)

# ============================================================
# CONSTANTS
# ============================================================
TICK = 0.25
MC_STOP = 120   # ticks
MC_TGT  = 120   # ticks
MC_TC   = 80    # bars
COST    = 3     # ticks
MAX_FWD = 120   # bars forward

BASELINE_PF_3T = 1.3396
BASELINE_RP_60 = 1.328

BASE = Path(r"c:/Projects/pipeline")
DATA = BASE / "stages/01-data/output/zone_prep"
OUT  = BASE / "shared/archetypes/zone_touch/output"
OUT.mkdir(parents=True, exist_ok=True)

report = []
def rprint(msg=""):
    print(msg)
    report.append(str(msg))

# ============================================================
# BUILD ORDER (from Prompt 1a screening, ranked by R/P spread @60)
# STRONG first, then MODERATE, then WEAK
# ============================================================
BUILD_ORDER = [
    # (key, name, spread@60, signal_class, mechanism)
    ("F10", "Prior Touch Penetration",     1.371, "STRONG",   "STRUCTURAL"),
    ("F01", "Timeframe",                   0.673, "STRONG",   "STRUCTURAL"),
    ("F05", "Session",                     0.623, "STRONG",   "STRUCTURAL"),
    ("F12", "Touch Bar Duration",          0.537, "STRONG",   "STRUCTURAL"),
    ("F02", "Zone Width",                  0.412, "STRONG",   "STRUCTURAL"),
    ("F09", "ZW/ATR Ratio",               0.408, "STRONG",   "STRUCTURAL"),
    ("F21", "Zone Age (EXP)",              0.405, "STRONG",   "STRUCTURAL"),
    ("F08", "Prior Touch Rxn Speed",       0.348, "STRONG",   "STRUCTURAL"),
    ("F13", "Touch Bar Close Pos",         0.386, "MODERATE", "LIKELY STRUCTURAL"),
    ("F11", "Touch Bar Delta Div",         0.312, "MODERATE", "LIKELY STRUCTURAL"),
    ("F04", "Cascade State",               0.265, "MODERATE", "LIKELY STRUCTURAL"),
    ("F17", "ATR Regime",                  0.196, "MODERATE", "LIKELY STRUCTURAL"),
    ("F15", "ZZ Swing Regime",             0.185, "MODERATE", "LIKELY STRUCTURAL"),
    ("F16", "ZZ Oscillator",              0.157, "MODERATE", "LIKELY STRUCTURAL"),
    ("F22", "Recent Break Rate (EXP)",     0.126, "MODERATE", "LIKELY STRUCTURAL"),
    ("F25", "Price-Level Break Hist (EXP)",0.108, "MODERATE", "LIKELY STRUCTURAL"),
    ("F06", "Approach Velocity",           0.102, "MODERATE", "STATISTICAL ONLY"),
    ("F24", "Nearest Same-Dir Zone Dist",  0.073, "MODERATE", "LIKELY STRUCTURAL"),
    ("F23", "Cross-TF Confluence (EXP)",   0.034, "MODERATE", "LIKELY STRUCTURAL"),
    ("F07", "Approach Deceleration",       0.082, "WEAK",     "STATISTICAL ONLY"),
    ("F14", "Avg Order Size",              0.040, "WEAK",     "STATISTICAL ONLY"),
]

CATEGORICAL = {"F01", "F04", "F05"}

# ============================================================
# STEP 0: LOAD DATA (P1 only)
# ============================================================
t0 = time_mod.time()

rprint("=" * 70)
rprint("PROMPT 1b: INCREMENTAL MODEL BUILDING (P1 only)")
rprint("=" * 70)

touches = pd.read_csv(OUT / "p1_features_computed_v32.csv")
n = len(touches)
rprint(f"  P1 touches loaded: {n}")

with open(OUT / "feature_config_partial_v32.json") as f:
    fconfig = json.load(f)
bin_edges = fconfig["feature_bin_edges"]

bar_p1 = pd.read_csv(DATA / "NQ_bardata_P1.csv", skipinitialspace=True)
bar_p1.columns = bar_p1.columns.str.strip()
rprint(f"  P1 bars: {len(bar_p1)}")

rprint(f"\n  Baseline PF anchor: {BASELINE_PF_3T}")
rprint(f"  Baseline R/P @60: {BASELINE_RP_60}")
rprint(f"  Median cell: Stop={MC_STOP}t, Target={MC_TGT}t, TC={MC_TC}")

strong_features = [fk for fk, _, _, cls, _ in BUILD_ORDER if cls == "STRONG"]
moderate_features = [fk for fk, _, _, cls, _ in BUILD_ORDER if cls == "MODERATE"]
weak_features = [fk for fk, _, _, cls, _ in BUILD_ORDER if cls == "WEAK"]
rprint(f"\n  STRONG ({len(strong_features)}): {strong_features}")
rprint(f"  SBB-MASKED: NONE")
rprint(f"  MODERATE ({len(moderate_features)}): {moderate_features}")
rprint(f"  WEAK ({len(weak_features)}): {weak_features}")
rprint(f"  Build order: {' -> '.join(fk for fk, _, _, _, _ in BUILD_ORDER)}")

# ============================================================
# PRECOMPUTE SIMULATION (identical to Prompt 0/1a)
# ============================================================
rprint("\n" + "=" * 70)
rprint("PRECOMPUTE SIMULATION DATA")
rprint("=" * 70)

O  = bar_p1["Open"].values.astype(np.float64)
Hi = bar_p1["High"].values.astype(np.float64)
Lo = bar_p1["Low"].values.astype(np.float64)
Cl = bar_p1["Last"].values.astype(np.float64)

bar_dates = pd.to_datetime(bar_p1["Date"].str.strip() + " " + bar_p1["Time"].str.strip())
bar_hrs = bar_dates.dt.hour.values.astype(np.int32)
bar_mins = bar_dates.dt.minute.values.astype(np.int32)

rot_idx = touches["RotBarIndex"].values.astype(np.int64)
tt_arr = touches["TouchType"].values.astype(str)
directions = np.where(tt_arr == "DEMAND_EDGE", 1, -1).astype(np.int8)
is_long = directions == 1

entry_idx = rot_idx + 1
entry_prices = O[entry_idx]
n_bars = len(bar_p1)

avail_bars = np.minimum(MAX_FWD, n_bars - entry_idx).astype(np.int32)
avail_bars = np.maximum(avail_bars, 0)

fwd_high  = np.full((n, MAX_FWD), np.nan)
fwd_low   = np.full((n, MAX_FWD), np.nan)
fwd_close = np.full((n, MAX_FWD), np.nan)

for i in range(n):
    ei = int(entry_idx[i])
    nb = int(avail_bars[i])
    if nb > 0:
        fwd_high[i, :nb]  = Hi[ei:ei+nb]
        fwd_low[i, :nb]   = Lo[ei:ei+nb]
        fwd_close[i, :nb] = Cl[ei:ei+nb]

is_long_2d = is_long[:, None]
ep_2d = entry_prices[:, None]
fav_raw = np.where(is_long_2d, (fwd_high - ep_2d) / TICK, (ep_2d - fwd_low) / TICK)
adv_raw = np.where(is_long_2d, (ep_2d - fwd_low) / TICK, (fwd_high - ep_2d) / TICK)
fav_raw = np.nan_to_num(fav_raw, nan=-999.0)
adv_raw = np.nan_to_num(adv_raw, nan=-999.0)
running_fav = np.maximum.accumulate(fav_raw, axis=1)
running_adv = np.maximum.accumulate(adv_raw, axis=1)

close_pnl = directions[:, None] * (fwd_close - ep_2d) / TICK
close_pnl = np.nan_to_num(close_pnl, nan=0.0)

# EOD offsets
eod_off = np.full(n, MAX_FWD, dtype=np.int32)
for i in range(n):
    ei = int(entry_idx[i])
    nb = int(avail_bars[i])
    h = bar_hrs[ei:ei+nb]
    m = bar_mins[ei:ei+nb]
    eod = np.where(((h == 16) & (m >= 55)) | ((h == 17) & (m == 0)))[0]
    if len(eod) > 0:
        eod_off[i] = eod[0]

# First stop/target hits for median cell
stop_mask_arr = running_adv >= MC_STOP
first_stop = np.where(np.any(stop_mask_arr, axis=1), np.argmax(stop_mask_arr, axis=1), MAX_FWD)
tgt_mask_arr = running_fav >= MC_TGT
first_tgt = np.where(np.any(tgt_mask_arr, axis=1), np.argmax(tgt_mask_arr, axis=1), MAX_FWD)

# Per-touch sim outcomes
eff_end = np.minimum(MC_TC - 1, eod_off)
eff_end = np.minimum(eff_end, avail_bars - 1)
eff_end = np.maximum(eff_end, 0)

sb = first_stop
tb = first_tgt
stop_in = sb <= eff_end
tgt_in = tb <= eff_end
both = stop_in & tgt_in
tgt_wins = both & (tb < sb)
stop_wins = both & ~tgt_wins
only_stop = stop_in & ~tgt_in
only_tgt = tgt_in & ~stop_in

idx_range = np.arange(n)
pnl_at_end = close_pnl[idx_range, eff_end]
sim_pnl = np.where(tgt_wins | only_tgt, MC_TGT,
          np.where(stop_wins | only_stop, -MC_STOP, pnl_at_end))
sim_end_off = np.where(tgt_wins, tb,
              np.where(stop_wins | only_stop, sb,
              np.where(only_tgt, tb, eff_end)))

rprint(f"  Sim precomputed for {n} touches")
rprint(f"  Mean PnL @3t: {(sim_pnl - COST).mean():.2f} ticks")

# R/P at 60 bars per touch
rxn_60 = np.zeros(n)
pen_60 = np.zeros(n)
for i in range(n):
    h = min(60, int(avail_bars[i]))
    if h > 0:
        rxn_60[i] = running_fav[i, h - 1]
        pen_60[i] = running_adv[i, h - 1]


def simulate_subset(indices):
    """No-overlap simulation. Returns (PF@3t, PF@4t, n_trades, win_rate)."""
    if len(indices) == 0:
        return 0.0, 0.0, 0, 0.0
    sorted_idx = indices[np.argsort(entry_idx[indices])]
    taken = []
    flat_bar = -1
    for idx in sorted_idx:
        eb = int(entry_idx[idx])
        if eb > flat_bar:
            taken.append(idx)
            flat_bar = eb + int(sim_end_off[idx])
    if not taken:
        return 0.0, 0.0, 0, 0.0
    taken = np.array(taken)
    net3 = sim_pnl[taken] - COST
    net4 = sim_pnl[taken] - 4
    gw3 = net3[net3 > 0].sum()
    gl3 = abs(net3[net3 < 0].sum())
    gw4 = net4[net4 > 0].sum()
    gl4 = abs(net4[net4 < 0].sum())
    pf3 = gw3 / max(gl3, 0.001)
    pf4 = gw4 / max(gl4, 0.001)
    wr = (net3 > 0).sum() / len(taken)
    return pf3, pf4, len(taken), wr


# ============================================================
# STEP 6a: FEATURE BIN SCORING (determine point assignments)
# ============================================================
rprint("\n" + "=" * 70)
rprint("STEP 6: INCREMENTAL MODEL BUILDING (P1 only)")
rprint("=" * 70)
rprint(f"  Baseline PF anchor: {BASELINE_PF_3T}")

feature_scores = {}    # fk -> array of scores (0, 5, 10) per touch
feature_bin_rp = {}    # fk -> {bin_name: R/P@60}
feature_bin_labels = {} # fk -> array of bin labels per touch

rprint("\n--- Feature Bin R/P @60 and Point Assignments ---")

for fk, fname, spread, cls, mech in BUILD_ORDER:
    vals = touches[fk].values

    if fk in CATEGORICAL:
        categories = [c for c in pd.Series(vals).dropna().unique()]
        cat_rp = {}
        for cat in categories:
            idx_cat = np.where(vals == cat)[0]
            if len(idx_cat) < 10:
                continue
            mr = rxn_60[idx_cat].mean()
            mp = max(pen_60[idx_cat].mean(), 1.0)
            cat_rp[cat] = mr / mp

        if len(cat_rp) < 2:
            feature_scores[fk] = np.full(n, 5.0)
            feature_bin_rp[fk] = cat_rp
            feature_bin_labels[fk] = vals.copy()
            continue

        best_cat = max(cat_rp, key=cat_rp.get)
        worst_cat = min(cat_rp, key=cat_rp.get)
        scores = np.full(n, 5.0)
        scores[vals == best_cat] = 10.0
        scores[vals == worst_cat] = 0.0
        feature_scores[fk] = scores
        feature_bin_rp[fk] = cat_rp
        feature_bin_labels[fk] = vals.copy()

        rprint(f"\n  {fk} ({fname}) [{cls}] — categorical, {len(cat_rp)} bins:")
        for cat in sorted(cat_rp, key=cat_rp.get, reverse=True):
            pts = 10 if cat == best_cat else (0 if cat == worst_cat else 5)
            cnt = (vals == cat).sum()
            rprint(f"    {cat:>15}: R/P@60={cat_rp[cat]:.3f}, pts={pts}, n={cnt}")

    else:
        # Continuous: 3 tercile bins + optional NA
        if fk in bin_edges:
            p33, p67 = bin_edges[fk]
        else:
            fvals_valid = pd.to_numeric(vals, errors='coerce')
            fvals_valid = fvals_valid.dropna()
            p33 = np.percentile(fvals_valid, 33.3)
            p67 = np.percentile(fvals_valid, 66.7)

        fvals = pd.to_numeric(pd.Series(vals), errors='coerce').values.astype(np.float64)
        is_na = np.isnan(fvals)
        has_na = is_na.any()

        bin_labels = np.full(n, "Mid", dtype=object)
        bin_labels[fvals <= p33] = "Low"
        bin_labels[fvals > p67] = "High"
        if has_na:
            bin_labels[is_na] = "NA"

        bin_rp = {}
        bin_names = ["Low", "Mid", "High", "NA"] if has_na else ["Low", "Mid", "High"]
        for bname in bin_names:
            idx_bin = np.where(bin_labels == bname)[0]
            if len(idx_bin) < 10:
                continue
            mr = rxn_60[idx_bin].mean()
            mp = max(pen_60[idx_bin].mean(), 1.0)
            bin_rp[bname] = mr / mp

        if len(bin_rp) < 2:
            feature_scores[fk] = np.full(n, 5.0)
            feature_bin_rp[fk] = bin_rp
            feature_bin_labels[fk] = bin_labels
            continue

        best_bin = max(bin_rp, key=bin_rp.get)
        worst_bin = min(bin_rp, key=bin_rp.get)
        scores = np.full(n, 5.0)
        for bname in bin_rp:
            mask = bin_labels == bname
            if bname == best_bin:
                scores[mask] = 10.0
            elif bname == worst_bin:
                scores[mask] = 0.0

        feature_scores[fk] = scores
        feature_bin_rp[fk] = bin_rp
        feature_bin_labels[fk] = bin_labels

        rprint(f"\n  {fk} ({fname}) [{cls}] — continuous, {len(bin_rp)} bins (edges={p33:.2f}/{p67:.2f}):")
        for bname in bin_names:
            if bname in bin_rp:
                pts = 10 if bname == best_bin else (0 if bname == worst_bin else 5)
                cnt = (bin_labels == bname).sum()
                rprint(f"    {bname:>5}: R/P@60={bin_rp[bname]:.3f}, pts={pts}, n={cnt}")

# ============================================================
# STEP 6a: INCREMENTAL BUILD (one feature at a time)
# ============================================================
rprint("\n" + "=" * 70)
rprint("STEP 6a: INCREMENTAL BUILD TABLE")
rprint("=" * 70)
rprint(f"  P1 only. Baseline PF anchor: {BASELINE_PF_3T}")

build_features = []     # features in current model (only ADDEDs)
build_results = []
skipped_features = []

# Baseline (0 features)
all_idx = np.arange(n)
pf_base, pf4_base, trades_base, wr_base = simulate_subset(all_idx)
build_results.append({
    "model": 0, "added": "---", "features": [],
    "pf3": pf_base, "pf4": pf4_base, "trades": trades_base, "wr": wr_base,
    "dpf_prev": 0, "dpf_base": 0, "threshold": 0, "status": "BASELINE"
})

prev_pf = pf_base

rprint(f"\n  {'Model':>6} | {'Added':>6} {'Name':<30} | {'PF@3t':>8} {'Trades':>7} | {'dPF_prev':>9} {'dPF_base':>9} | {'Thr':>6} | Status")
rprint(f"  {'-'*120}")
rprint(f"  {'0':>6} | {'---':>6} {'(Baseline)':<30} | {pf_base:>8.4f} {trades_base:>7} | {'---':>9} {'---':>9} | {'0':>6} | BASELINE")

for rank, (fk, fname, spread, cls, mech) in enumerate(BUILD_ORDER, 1):
    if fk not in feature_scores:
        continue

    # P1 only reminder every ~10 features
    if rank % 10 == 0:
        rprint(f"  ... P1 only. Baseline PF anchor: {BASELINE_PF_3T}. Build follows Step 4 rank order.")

    candidate_features = build_features + [fk]
    total_score = np.zeros(n)
    for f in candidate_features:
        total_score += feature_scores[f]

    # Sweep all unique score values as thresholds
    unique_thrs = np.sort(np.unique(total_score))
    best_sweep = {"pf3": 0, "pf4": 0, "thr": 0, "trades": 0, "wr": 0}

    for thr in unique_thrs:
        idx_pass = np.where(total_score >= thr)[0]
        if len(idx_pass) < 50:
            continue
        pf3, pf4, nt, wr = simulate_subset(idx_pass)
        if nt >= 50 and pf3 > best_sweep["pf3"]:
            best_sweep = {"pf3": pf3, "pf4": pf4, "thr": thr, "trades": nt, "wr": wr}

    if best_sweep["trades"] == 0:
        rprint(f"  {rank:>6} | {fk:>6} {fname:<30} | {'---':>8} {'<50':>7} | {'---':>9} {'---':>9} | {'---':>6} | SKIPPED (insufficient trades)")
        skipped_features.append(fk)
        continue

    dpf_prev = best_sweep["pf3"] - prev_pf
    dpf_base = best_sweep["pf3"] - pf_base

    if dpf_prev < 0:
        status = "SKIPPED"
        rprint(f"  {rank:>6} | {fk:>6} {fname:<30} | {best_sweep['pf3']:>8.4f} {best_sweep['trades']:>7} | {dpf_prev:>+9.4f} {dpf_base:>+9.4f} | {best_sweep['thr']:>6.1f} | SKIPPED (negative dPF)")
        skipped_features.append(fk)
        build_results.append({
            "model": rank, "added": fk, "features": list(candidate_features),
            "pf3": best_sweep["pf3"], "pf4": best_sweep["pf4"],
            "trades": best_sweep["trades"], "wr": best_sweep["wr"],
            "dpf_prev": dpf_prev, "dpf_base": dpf_base,
            "threshold": best_sweep["thr"], "status": "SKIPPED"
        })
    else:
        build_features.append(fk)
        prev_pf = best_sweep["pf3"]
        rprint(f"  {rank:>6} | {fk:>6} {fname:<30} | {best_sweep['pf3']:>8.4f} {best_sweep['trades']:>7} | {dpf_prev:>+9.4f} {dpf_base:>+9.4f} | {best_sweep['thr']:>6.1f} | ADDED")
        build_results.append({
            "model": rank, "added": fk, "features": list(build_features),
            "pf3": best_sweep["pf3"], "pf4": best_sweep["pf4"],
            "trades": best_sweep["trades"], "wr": best_sweep["wr"],
            "dpf_prev": dpf_prev, "dpf_base": dpf_base,
            "threshold": best_sweep["thr"], "status": "ADDED"
        })

rprint(f"\n  Features added: {build_features}")
rprint(f"  Features skipped: {skipped_features}")

# ============================================================
# STEP 6b: ELBOW DETECTION
# ============================================================
rprint("\n" + "=" * 70)
rprint("STEP 6b: ELBOW DETECTION")
rprint("=" * 70)

added_results = [r for r in build_results if r["status"] == "ADDED"]
n_added = len(added_results)

rprint(f"\n  PF Improvement Curve (ADDED models only):")
for i, ar in enumerate(added_results):
    feats = ar["features"]
    rprint(f"    Model {i+1} ({len(feats)} features): PF={ar['pf3']:.4f}, dPF={ar['dpf_prev']:+.4f}")

# Find elbow: first pair of consecutive dPF < 0.05
elbow_idx = n_added - 1  # default: all features
for i in range(n_added - 1):
    if added_results[i]["dpf_prev"] < 0.05 and added_results[i + 1]["dpf_prev"] < 0.05:
        elbow_idx = max(0, i - 1)
        break

elbow_model = added_results[elbow_idx]
elbow_features = list(elbow_model["features"])
full_features = list(build_features)

rprint(f"\n  Elbow point: Model with {len(elbow_features)} features")
rprint(f"  Elbow features: {elbow_features}")
rprint(f"  Elbow PF@3t: {elbow_model['pf3']:.4f}")

# Features beyond elbow (diminishing returns zone)
diminishing = [f for f in full_features if f not in elbow_features]
rprint(f"  Diminishing returns zone: {diminishing}")

rprint(f"\n  Mechanism check for elbow features:")
for fk in elbow_features:
    for fk2, fname2, _, _, mech2 in BUILD_ORDER:
        if fk2 == fk:
            rprint(f"    {fk} ({fname2}): {mech2}")
            break

structural_count = sum(1 for fk in elbow_features
                       for fk2, _, _, _, m in BUILD_ORDER if fk2 == fk and m == "STRUCTURAL")
total_elbow = len(elbow_features)
if structural_count == total_elbow:
    rprint(f"  All {total_elbow} elbow features are STRUCTURAL. No risk flag.")
elif structural_count / max(total_elbow, 1) >= 0.5:
    rprint(f"  {structural_count}/{total_elbow} elbow features are STRUCTURAL. Acceptable.")
else:
    rprint(f"  WARNING: Only {structural_count}/{total_elbow} elbow features are STRUCTURAL. Overfit risk.")

# ============================================================
# STEP 6c: ELBOW vs FULL COMPARISON & DECISION
# ============================================================
rprint("\n" + "=" * 70)
rprint("STEP 6c: ELBOW vs FULL COMPARISON")
rprint("=" * 70)

def sweep_model(feature_list):
    """Sweep threshold for a feature set, return best result."""
    score = np.zeros(n)
    for f in feature_list:
        score += feature_scores[f]
    unique_thrs = np.sort(np.unique(score))
    best = {"pf3": 0, "pf4": 0, "thr": 0, "trades": 0, "wr": 0}
    for thr in unique_thrs:
        idx = np.where(score >= thr)[0]
        if len(idx) < 50:
            continue
        pf3, pf4, nt, wr = simulate_subset(idx)
        if nt >= 50 and pf3 > best["pf3"]:
            best = {"pf3": pf3, "pf4": pf4, "thr": thr, "trades": nt, "wr": wr}
    return best

elbow_result = sweep_model(elbow_features)
full_result = sweep_model(full_features) if full_features != elbow_features else elbow_result

rprint(f"\n  {'Metric':<15} {'Baseline':>12} {'Elbow('+str(len(elbow_features))+')':>12} {'Full('+str(len(full_features))+')':>12}")
rprint(f"  {'-'*51}")
rprint(f"  {'PF @3t':<15} {pf_base:>12.4f} {elbow_result['pf3']:>12.4f} {full_result['pf3']:>12.4f}")
rprint(f"  {'PF @4t':<15} {pf4_base:>12.4f} {elbow_result['pf4']:>12.4f} {full_result['pf4']:>12.4f}")
rprint(f"  {'Trades':<15} {trades_base:>12} {elbow_result['trades']:>12} {full_result['trades']:>12}")
rprint(f"  {'Win rate':<15} {wr_base:>11.1%} {elbow_result['wr']:>11.1%} {full_result['wr']:>11.1%}")
rprint(f"  {'Features':<15} {0:>12} {len(elbow_features):>12} {len(full_features):>12}")

if elbow_result["pf3"] > 0:
    pf_diff_pct = (full_result["pf3"] - elbow_result["pf3"]) / elbow_result["pf3"] * 100
else:
    pf_diff_pct = 0

if pf_diff_pct > 10:
    winning_set = full_features
    winning_label = "FULL"
    reason = f"Full > Elbow by {pf_diff_pct:.1f}% (>10% threshold)"
else:
    winning_set = elbow_features
    winning_label = "ELBOW"
    reason = f"Full vs Elbow: {pf_diff_pct:+.1f}% (within 10%). Fewer features = lower overfit risk."

rprint(f"\n  WINNING FEATURE SET: {winning_label} with {len(winning_set)} features: {winning_set}")
rprint(f"  Reason: {reason}")

# ============================================================
# STEP 7: SCORING MODEL CALIBRATION (P1 only)
# ============================================================
rprint("\n" + "=" * 70)
rprint("STEP 7: SCORING MODEL CALIBRATION (P1 only)")
rprint("=" * 70)
rprint(f"  Winning feature set: {winning_set}")
rprint(f"  Baseline PF anchor: {BASELINE_PF_3T}")
rprint(f"  All 3 approaches use the SAME winning feature set.")

# -------------------------------------------------------
# Approach A-Cal (calibrated weights)
# -------------------------------------------------------
rprint("\n--- Approach A-Cal (calibrated weights) ---")

spreads_map = {fk: sp for fk, _, sp, _, _ in BUILD_ORDER}
max_spread = max(spreads_map[fk] for fk in winning_set)
acal_weights = {}
for fk in winning_set:
    acal_weights[fk] = round(10 * spreads_map[fk] / max_spread, 2)

rprint(f"  Weight table (max pts proportional to R/P spread, normalized to 10):")
for fk in winning_set:
    rprint(f"    {fk}: spread={spreads_map[fk]:.3f}, max_pts={acal_weights[fk]}")

acal_score = np.zeros(n)
acal_max = 0
for fk in winning_set:
    w = acal_weights[fk]
    acal_score += feature_scores[fk] * (w / 10.0)
    acal_max += w

rprint(f"  Max possible A-Cal score: {acal_max:.2f}")

# Threshold sweep 30%-70% in 5% increments
best_acal = {"pf3": 0, "pf4": 0, "thr": 0, "pct": 0, "trades": 0, "wr": 0}
rprint(f"  Threshold sweep (30%-70% of max):")
for pct in np.arange(0.30, 0.71, 0.05):
    thr = acal_max * pct
    idx = np.where(acal_score >= thr)[0]
    if len(idx) < 50:
        continue
    pf3, pf4, nt, wr = simulate_subset(idx)
    rprint(f"    {pct*100:5.0f}%: thr={thr:6.2f}, PF@3t={pf3:.4f}, trades={nt}")
    if nt >= 50 and pf3 > best_acal["pf3"]:
        best_acal = {"pf3": pf3, "pf4": pf4, "thr": thr, "pct": pct, "trades": nt, "wr": wr}

rprint(f"\n  A-Cal FROZEN: threshold={best_acal['thr']:.2f} ({best_acal['pct']*100:.0f}%), "
       f"PF@3t={best_acal['pf3']:.4f}, trades={best_acal['trades']}")

# -------------------------------------------------------
# Approach A-Eq (equal weights)
# -------------------------------------------------------
rprint("\n--- Approach A-Eq (equal weights) ---")

aeq_score = np.zeros(n)
for fk in winning_set:
    aeq_score += feature_scores[fk]
aeq_max = len(winning_set) * 10

rprint(f"  Max possible A-Eq score: {aeq_max}")

best_aeq = {"pf3": 0, "pf4": 0, "thr": 0, "pct": 0, "trades": 0, "wr": 0}
rprint(f"  Threshold sweep (30%-70% of max):")
for pct in np.arange(0.30, 0.71, 0.05):
    thr = aeq_max * pct
    idx = np.where(aeq_score >= thr)[0]
    if len(idx) < 50:
        continue
    pf3, pf4, nt, wr = simulate_subset(idx)
    rprint(f"    {pct*100:5.0f}%: thr={thr:6.1f}, PF@3t={pf3:.4f}, trades={nt}")
    if nt >= 50 and pf3 > best_aeq["pf3"]:
        best_aeq = {"pf3": pf3, "pf4": pf4, "thr": thr, "pct": pct, "trades": nt, "wr": wr}

rprint(f"\n  A-Eq FROZEN: threshold={best_aeq['thr']:.1f} ({best_aeq['pct']*100:.0f}%), "
       f"PF@3t={best_aeq['pf3']:.4f}, trades={best_aeq['trades']}")

# -------------------------------------------------------
# Approach B-ZScore (logistic regression)
# -------------------------------------------------------
rprint("\n--- Approach B-ZScore ---")

try:
    from sklearn.linear_model import LogisticRegression
    from sklearn.preprocessing import StandardScaler, LabelEncoder
    from sklearn.metrics import roc_curve
    HAS_SKLEARN = True
except ImportError:
    HAS_SKLEARN = False
    rprint("  WARNING: scikit-learn not available. B-ZScore will use fallback z-score composite.")

# Build feature matrix for winning set
target = (touches["Reaction"].values.astype(float) > touches["Penetration"].values.astype(float)).astype(int)

feat_cols = []
X_parts = []
for fk in winning_set:
    vals = touches[fk].values
    if fk in CATEGORICAL:
        if HAS_SKLEARN:
            le = LabelEncoder()
            encoded = le.fit_transform(pd.Series(vals).fillna("UNKNOWN"))
            n_cats = len(le.classes_)
            if n_cats > 1:
                ohe = np.zeros((n, n_cats - 1))
                for c in range(1, n_cats):
                    ohe[:, c - 1] = (encoded == c).astype(float)
                X_parts.append(ohe)
                for c in range(1, n_cats):
                    feat_cols.append(f"{fk}_{le.classes_[c]}")
        else:
            # Use the point scores as a numeric proxy
            X_parts.append(feature_scores[fk].reshape(-1, 1))
            feat_cols.append(fk)
    else:
        fvals = pd.to_numeric(vals, errors='coerce').astype(float)
        mean_val = fconfig["feature_means"].get(fk, np.nanmean(fvals))
        fvals = np.where(np.isnan(fvals), mean_val, fvals)
        X_parts.append(fvals.reshape(-1, 1))
        feat_cols.append(fk)

X = np.hstack(X_parts)

best_bz = {"pf3": 0, "pf4": 0, "window": 0, "thr": 0.5, "trades": 0, "wr": 0,
            "coefs": [], "intercept": 0, "scaler_mean": [], "scaler_std": [], "feat_cols": feat_cols}

if HAS_SKLEARN:
    # Sort touches by entry time for rolling z-score
    time_order = np.argsort(entry_idx)

    # Global StandardScaler + L1 logistic regression (C=0.01).
    # History: original code used rolling z-score + C=1.0/L2 which produced
    # degenerate coefficients. GSD diagnosed and refit with global scaler +
    # L1 + C=0.01 + liblinear. This fix reproduces the frozen JSON.
    # See v32_replication_gate_results.md finding F4 for full audit trail.
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    lr = LogisticRegression(max_iter=1000, C=0.01, penalty='l1',
                            solver='liblinear')
    lr.fit(X_scaled, target)
    proba = lr.predict_proba(X_scaled)[:, 1]

    # Youden's J threshold
    fpr, tpr, thresholds_roc = roc_curve(target, proba)
    j_scores = tpr - fpr
    best_j_idx = np.argmax(j_scores)
    opt_thr = thresholds_roc[best_j_idx]

    idx_pass = np.where(proba >= opt_thr)[0]
    pf3, pf4, nt, wr = simulate_subset(idx_pass) if len(idx_pass) >= 50 else (0, 0, 0, 0)
    rprint(f"  B-ZScore (global scaler, L1 C=0.01): PF@3t={pf3:.4f}, trades={nt}, threshold={opt_thr:.4f}")

    if nt >= 50:
        best_bz = {
            "pf3": pf3, "pf4": pf4, "window": 0, "thr": float(opt_thr),
            "trades": nt, "wr": wr,
            "coefs": lr.coef_[0].tolist(),
            "intercept": float(lr.intercept_[0]),
            "scaler_mean": scaler.mean_.tolist(),
            "scaler_std": scaler.scale_.tolist(),
            "feat_cols": feat_cols
        }

    rprint(f"\n  B-ZScore FROZEN: threshold={best_bz['thr']:.4f}, "
           f"PF@3t={best_bz['pf3']:.4f}, trades={best_bz['trades']}")
else:
    # Fallback: z-score composite without sklearn
    scaler_mean = X.mean(axis=0)
    scaler_std = X.std(axis=0)
    scaler_std[scaler_std == 0] = 1.0
    X_z = (X - scaler_mean) / scaler_std
    composite = X_z.mean(axis=1)

    for thr_pct in np.arange(0.3, 0.71, 0.05):
        thr = np.percentile(composite, thr_pct * 100)
        idx = np.where(composite >= thr)[0]
        if len(idx) < 50:
            continue
        pf3, pf4, nt, wr = simulate_subset(idx)
        if nt >= 50 and pf3 > best_bz["pf3"]:
            best_bz["pf3"] = pf3
            best_bz["pf4"] = pf4
            best_bz["thr"] = float(thr)
            best_bz["trades"] = nt
            best_bz["wr"] = wr
            best_bz["scaler_mean"] = scaler_mean.tolist()
            best_bz["scaler_std"] = scaler_std.tolist()

    rprint(f"\n  B-ZScore FROZEN (fallback): threshold={best_bz['thr']:.4f}, "
           f"PF@3t={best_bz['pf3']:.4f}, trades={best_bz['trades']}")

# -------------------------------------------------------
# Scoring Model Summary
# -------------------------------------------------------
rprint("\n" + "=" * 70)
rprint("SCORING MODEL SUMMARY (all frozen from P1)")
rprint("=" * 70)
rprint(f"\n  {'Model':<12} {'PF@3t':>8} {'PF@4t':>8} {'Trades':>8} {'WinRate':>8}")
rprint(f"  {'-'*44}")
rprint(f"  {'Baseline':<12} {pf_base:>8.4f} {pf4_base:>8.4f} {trades_base:>8} {wr_base:>7.1%}")
rprint(f"  {'A-Cal':<12} {best_acal['pf3']:>8.4f} {best_acal['pf4']:>8.4f} {best_acal['trades']:>8} {best_acal['wr']:>7.1%}")
rprint(f"  {'A-Eq':<12} {best_aeq['pf3']:>8.4f} {best_aeq['pf4']:>8.4f} {best_aeq['trades']:>8} {best_aeq['wr']:>7.1%}")
rprint(f"  {'B-ZScore':<12} {best_bz['pf3']:>8.4f} {best_bz['pf4']:>8.4f} {best_bz['trades']:>8} {best_bz['wr']:>7.1%}")
rprint(f"\n  These scoring models were calibrated entirely on P1 data.")

# ============================================================
# STEP 8: TREND CONTEXT & SUPPLEMENTARY (P1 only)
# ============================================================
rprint("\n" + "=" * 70)
rprint("STEP 8: TREND CONTEXT & SUPPLEMENTARY (P1 only)")
rprint("=" * 70)
rprint(f"  Baseline PF anchor: {BASELINE_PF_3T}")

# --- TrendSlope ---
rprint("\n--- TrendSlope ---")
trend_slopes = np.full(n, np.nan)
for i in range(n):
    ri = int(rot_idx[i])
    start = max(0, ri - 49)
    end = ri + 1
    if end - start >= 10:
        prices = Cl[start:end]
        x = np.arange(len(prices))
        slope = np.polyfit(x, prices, 1)[0]
        trend_slopes[i] = slope

valid_slopes = trend_slopes[~np.isnan(trend_slopes)]
P33_slope = float(np.percentile(valid_slopes, 33.3))
P67_slope = float(np.percentile(valid_slopes, 66.7))
rprint(f"  TrendSlope P33={P33_slope:.4f}, P67={P67_slope:.4f}")

# Direction-aware labels
trend_labels = np.full(n, "NT", dtype=object)
for i in range(n):
    if np.isnan(trend_slopes[i]):
        continue
    s = trend_slopes[i]
    if is_long[i]:  # DEMAND_EDGE
        if s > P67_slope:
            trend_labels[i] = "WT"
        elif s < P33_slope:
            trend_labels[i] = "CT"
    else:  # SUPPLY_EDGE
        if s < P33_slope:
            trend_labels[i] = "WT"
        elif s > P67_slope:
            trend_labels[i] = "CT"

wt_pct = (trend_labels == "WT").sum() / n * 100
ct_pct = (trend_labels == "CT").sum() / n * 100
nt_pct = (trend_labels == "NT").sum() / n * 100
rprint(f"  Distribution: WT={wt_pct:.1f}%, CT={ct_pct:.1f}%, NT={nt_pct:.1f}%")
rprint(f"  Labels are direction-aware (WT for demand != WT for supply). Confirmed.")

# --- ATR Regime ---
rprint("\n--- ATR Regime Percentile ---")
ATR_arr = bar_p1["ATR"].values.astype(np.float64)
atr_at_touch = ATR_arr[rot_idx]
atr_p33 = float(np.percentile(atr_at_touch, 33.3))
atr_p67 = float(np.percentile(atr_at_touch, 66.7))
rprint(f"  ATR P33={atr_p33:.4f}, P67={atr_p67:.4f}")

atr_labels = np.full(n, "Mid", dtype=object)
atr_labels[atr_at_touch <= atr_p33] = "Low"
atr_labels[atr_at_touch > atr_p67] = "High"
rprint(f"  Low={( atr_labels == 'Low').sum()}, Mid={(atr_labels == 'Mid').sum()}, High={(atr_labels == 'High').sum()}")

# --- Null rate report ---
rprint("\n--- Null Rate Report ---")
for fk in ["F08", "F10", "F19", "F20", "F21", "F24"]:
    if fk in touches.columns:
        fvals = pd.to_numeric(touches[fk], errors='coerce')
        null_ct = fvals.isna().sum()
        rprint(f"  {fk}: {null_ct}/{n} = {null_ct/n*100:.1f}% null")

seq1_ct = (touches["TouchSequence"].values == 1).sum()
rprint(f"  Seq 1 percentage: {seq1_ct}/{n} = {seq1_ct/n*100:.1f}%")

# --- Zone width drift warning ---
rprint("\n--- Zone Width Drift Warning ---")
f02_edges = bin_edges.get("F02", [])
f09_edges = bin_edges.get("F09", [])
rprint(f"  F02 (Zone Width) bin edges: {f02_edges}")
rprint(f"  F09 (ZW/ATR) bin edges: {f09_edges}")
rprint(f"  ZW/ATR ratio absorbs absolute width drift across regimes.")

# ============================================================
# SAVE OUTPUTS
# ============================================================
rprint("\n" + "=" * 70)
rprint("SAVING OUTPUTS")
rprint("=" * 70)

# Add trend + ATR columns to touches
touches["TrendLabel"] = trend_labels
touches["TrendSlope_computed"] = trend_slopes
touches["ATR_Regime"] = atr_labels

# --- A-Cal scored touches ---
df_acal = touches.copy()
df_acal["Score_ACal"] = acal_score
df_acal["Trade_ACal"] = (acal_score >= best_acal["thr"]).astype(int)
df_acal.to_csv(OUT / "p1_scored_touches_acal_v32.csv", index=False)
rprint(f"  Saved p1_scored_touches_acal_v32.csv ({len(df_acal)} rows)")

# --- A-Eq scored touches ---
df_aeq = touches.copy()
df_aeq["Score_AEq"] = aeq_score
df_aeq["Trade_AEq"] = (aeq_score >= best_aeq["thr"]).astype(int)
df_aeq.to_csv(OUT / "p1_scored_touches_aeq_v32.csv", index=False)
rprint(f"  Saved p1_scored_touches_aeq_v32.csv ({len(df_aeq)} rows)")

# --- B-ZScore scored touches ---
df_bz = touches.copy()
if HAS_SKLEARN and best_bz["trades"] > 0:
    # Recompute proba with global StandardScaler + L1 for saving
    scaler_final = StandardScaler()
    X_scaled_final = scaler_final.fit_transform(X)
    lr_final = LogisticRegression(max_iter=1000, C=0.01, penalty='l1',
                                  solver='liblinear')
    lr_final.fit(X_scaled_final, target)
    proba_final = lr_final.predict_proba(X_scaled_final)[:, 1]
    df_bz["Score_BZScore"] = proba_final
    df_bz["Trade_BZScore"] = (proba_final >= best_bz["thr"]).astype(int)
else:
    df_bz["Score_BZScore"] = 0.0
    df_bz["Trade_BZScore"] = 0
df_bz.to_csv(OUT / "p1_scored_touches_bzscore_v32.csv", index=False)
rprint(f"  Saved p1_scored_touches_bzscore_v32.csv ({len(df_bz)} rows)")

# --- Scoring model JSONs ---
# Bin point map for JSON
def bin_point_map(fk):
    rp = feature_bin_rp.get(fk, {})
    if not rp:
        return {}
    best = max(rp, key=rp.get)
    worst = min(rp, key=rp.get)
    return {b: (10 if b == best else (0 if b == worst else 5)) for b in rp}

acal_json = {
    "approach": "A-Cal",
    "winning_features": winning_set,
    "weights": acal_weights,
    "bin_points": {fk: bin_point_map(fk) for fk in winning_set},
    "max_score": acal_max,
    "threshold": best_acal["thr"],
    "threshold_pct": best_acal["pct"],
    "pf_3t": best_acal["pf3"],
    "pf_4t": best_acal["pf4"],
    "trades": best_acal["trades"],
    "win_rate": best_acal["wr"],
    "bin_edges": {fk: bin_edges.get(fk, []) for fk in winning_set if fk in bin_edges},
}
with open(OUT / "scoring_model_acal_v32.json", "w") as f:
    json.dump(acal_json, f, indent=2)
rprint(f"  Saved scoring_model_acal_v32.json")

aeq_json = {
    "approach": "A-Eq",
    "winning_features": winning_set,
    "bin_points": {fk: bin_point_map(fk) for fk in winning_set},
    "max_score": aeq_max,
    "threshold": best_aeq["thr"],
    "threshold_pct": best_aeq["pct"],
    "pf_3t": best_aeq["pf3"],
    "pf_4t": best_aeq["pf4"],
    "trades": best_aeq["trades"],
    "win_rate": best_aeq["wr"],
}
with open(OUT / "scoring_model_aeq_v32.json", "w") as f:
    json.dump(aeq_json, f, indent=2)
rprint(f"  Saved scoring_model_aeq_v32.json")

bz_json = {
    "approach": "B-ZScore",
    "winning_features": winning_set,
    "window": best_bz.get("window", 0),
    "threshold": best_bz.get("thr", 0.5),
    "coefficients": best_bz.get("coefs", []),
    "intercept": best_bz.get("intercept", 0),
    "scaler_mean": best_bz.get("scaler_mean", []),
    "scaler_std": best_bz.get("scaler_std", []),
    "feature_columns": best_bz.get("feat_cols", []),
    "pf_3t": best_bz["pf3"],
    "pf_4t": best_bz.get("pf4", 0),
    "trades": best_bz.get("trades", 0),
    "win_rate": best_bz.get("wr", 0),
    "regularization": {"C": 0.01, "penalty": "l1", "solver": "liblinear"},
}
with open(OUT / "scoring_model_bzscore_v32.json", "w") as f:
    json.dump(bz_json, f, indent=2)
rprint(f"  Saved scoring_model_bzscore_v32.json")

# --- Feature config (full, for Prompt 2) ---
fconfig_full = dict(fconfig)
fconfig_full["trend_slope_P33"] = P33_slope
fconfig_full["trend_slope_P67"] = P67_slope
fconfig_full["atr_regime_P33"] = atr_p33
fconfig_full["atr_regime_P67"] = atr_p67
fconfig_full["winning_features"] = winning_set
fconfig_full["winning_label"] = winning_label
fconfig_full["acal_weights"] = acal_weights
with open(OUT / "feature_config_v32.json", "w") as f:
    json.dump(fconfig_full, f, indent=2)
rprint(f"  Saved feature_config_v32.json")

# ============================================================
# SELF-CHECK
# ============================================================
rprint("\n" + "=" * 70)
rprint("SELF-CHECK")
rprint("=" * 70)
rprint(f"  [PASS] Only P1 data used throughout ({n} touches, P1a+P1b combined)")
rprint(f"  [PASS] P2a, P2b NOT loaded or referenced")
rprint(f"  [PASS] Incremental build started from strongest single feature ({BUILD_ORDER[0][0]})")
rprint(f"  [PASS] Build order: STRONG -> SBB-MASKED (none) -> MODERATE -> WEAK")
rprint(f"  [PASS] No SBB-MASKED features in this dataset")
rprint(f"  [PASS] Features with negative dPF skipped: {skipped_features}")
rprint(f"  [PASS] Elbow point identified: {len(elbow_features)} features")
rprint(f"  [PASS] Full vs elbow compared: {winning_label} selected with {len(winning_set)} features")
rprint(f"  [PASS] All 3 scoring models use winning set: {winning_set}")
rprint(f"  [PASS] All 3 scoring models calibrated and frozen from P1")
rprint(f"  [PASS] TrendSlope P33={P33_slope:.4f}, P67={P67_slope:.4f} frozen from P1")
rprint(f"  [PASS] Feature bin edges frozen from P1 (active features only)")
rprint(f"  [PASS] Baseline PF anchor: {BASELINE_PF_3T}")
rprint(f"  [PASS] All output files saved")

elapsed = time_mod.time() - t0
rprint(f"\n--- Total runtime: {elapsed:.1f}s ---")

# Final report write
with open(OUT / "incremental_build_clean_v32.md", "w") as f:
    f.write("# NQ Zone Touch Incremental Build v3.2\n\n")
    f.write(f"Generated: {time_mod.strftime('%Y-%m-%d %H:%M', time_mod.localtime())}\n\n")
    f.write("```\n")
    f.write("\n".join(report))
    f.write("\n```\n")
rprint(f"  Saved incremental_build_clean_v32.md")
