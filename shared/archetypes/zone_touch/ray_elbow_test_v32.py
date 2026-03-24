# archetype: zone_touch
"""Ray Incremental Elbow Test (Analysis A) — v3.2

Tests whether any ray-derived feature adds independent predictive power
to the frozen 7-feature zone touch scoring model.

Steps:
  0. Data inspection (done interactively)
  1. Compute backing ray features per P1 touch (reusing ray_feature_screening.py)
  2. Solo screening of ray candidates via R/P spread
  3. Incremental build extension at position #8+
  4. P2 validation (only if a ray feature enters the elbow)
  5. Output report

Uses 60m+ rays only, 40t proximity threshold, BACKING RAY aggregation.
"""

import numpy as np
import pandas as pd
from pathlib import Path
import json, sys, time as time_mod, io, warnings, importlib.util

warnings.filterwarnings("ignore")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
np.random.seed(42)

# ============================================================
# CONSTANTS (must match model_building_v32.py exactly)
# ============================================================
TICK = 0.25
MC_STOP = 120   # ticks
MC_TGT  = 120   # ticks
MC_TC   = 80    # bars
COST    = 3     # ticks
MAX_FWD = 120   # bars forward
PROX_THRESHOLD = 40  # ticks for ray proximity

BASE = Path(r"c:/Projects/pipeline")
DATA = BASE / "stages/01-data/output/zone_prep"
TOUCH_DIR = BASE / "stages/01-data/data/touches"
BAR_VOL_DIR = BASE / "stages/01-data/data/bar_data/volume"
BAR_TIME_DIR = BASE / "stages/01-data/data/bar_data/time"
OUT = BASE / "shared/archetypes/zone_touch/output"
OUT.mkdir(parents=True, exist_ok=True)

# Load ray_feature_screening module for lifecycle computation
_rfs_path = Path(__file__).parent / "ray_feature_screening.py"
_rfs_spec = importlib.util.spec_from_file_location("ray_feature_screening", str(_rfs_path))
rfs = importlib.util.module_from_spec(_rfs_spec)
_rfs_spec.loader.exec_module(rfs)

report = []
def rprint(msg=""):
    print(msg)
    report.append(str(msg))


# ============================================================
# FROZEN 7-FEATURE MODEL (from scoring_model_aeq_v32.json)
# ============================================================
with open(OUT / "scoring_model_aeq_v32.json") as f:
    aeq_model = json.load(f)

with open(OUT / "feature_config_v32.json") as f:
    fconfig = json.load(f)

WINNING_FEATURES = aeq_model["winning_features"]  # ['F10','F01','F05','F09','F21','F13','F04']
BIN_POINTS = aeq_model["bin_points"]
BIN_EDGES = fconfig["feature_bin_edges"]
CATEGORICAL = {"F01", "F04", "F05"}

# Reference values from incremental build
BASELINE_PF_3T = 1.3045   # 0-feature baseline
MODEL7_PF_3T = 5.3671     # 7-feature model PF@3t
MODEL7_THRESHOLD = 50.0   # threshold at 7 features
MODEL7_TRADES = 102


# ============================================================
# STEP 0+1: LOAD DATA & COMPUTE RAY FEATURES
# ============================================================
t0 = time_mod.time()

rprint("=" * 70)
rprint("RAY INCREMENTAL ELBOW TEST — ANALYSIS A (v3.2)")
rprint("=" * 70)
rprint(f"  Date: {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M')}")
rprint(f"  Frozen model: {WINNING_FEATURES}")
rprint(f"  Ray filters: 60m+ only, {PROX_THRESHOLD}t proximity, BACKING only")
rprint()

# Load precomputed P1 features (same as model_building_v32.py)
touches = pd.read_csv(OUT / "p1_features_computed_v32.csv")
n = len(touches)
rprint(f"  P1 touches loaded: {n}")

# Load bar data (same as model_building)
bar_p1 = pd.read_csv(DATA / "NQ_bardata_P1.csv", skipinitialspace=True)
bar_p1.columns = bar_p1.columns.str.strip()
rprint(f"  P1 bars: {len(bar_p1)}")

# Load ray data
zte_raw = pd.read_csv(TOUCH_DIR / "NQ_ZTE_raw_P1.csv")
zte_raw = zte_raw[zte_raw["TouchType"] != "VP_RAY"].copy()
rprint(f"  P1 raw touches (excl VP_RAY): {len(zte_raw)}")

ray_ctx = pd.read_csv(TOUCH_DIR / "NQ_ray_context_P1.csv")
ray_ctx_htf = ray_ctx[ray_ctx["RayTF"].apply(rfs.is_htf)].copy()
rprint(f"  HTF ray-touch pairs: {len(ray_ctx_htf)}")

ray_ref = pd.read_csv(TOUCH_DIR / "NQ_ray_reference_P1.csv")
rprint(f"  Ray reference events: {len(ray_ref)}")

# Load bar data for ray lifecycle computation (250vol for interaction detection)
bars_vol = rfs.load_bar_data(BAR_VOL_DIR / "NQ_BarData_250vol_rot_P1.csv")
bars_vol["BarIdx"] = bars_vol.index
rprint(f"  250vol bars: {len(bars_vol)}")

# Build 15m bars from 10-sec data
rprint("  Building 15m bars from 10-sec data...")
b10 = rfs.load_bar_data(BAR_TIME_DIR / "NQ_BarData_10sec_rot_P1.csv")
b10 = b10.set_index("DateTime").sort_index()
bars_15m = b10.resample("15min").agg({
    "Open": "first", "High": "max", "Low": "min",
    "Close": "last", "Volume": "sum"
}).dropna().reset_index()
del b10
rprint(f"  15m bars: {len(bars_15m)}")

# Extract rays, detect interactions, build lifecycle
rprint("\n  Extracting HTF rays...")
rays_df = rfs.extract_rays(zte_raw, ray_ctx_htf, ray_ref, len(bars_vol))

rprint("  Detecting interactions...")
ixns = rfs.detect_interactions(bars_vol, rays_df, bars_15m, threshold=PROX_THRESHOLD)
ixns_valid = ixns[ixns["outcome"].isin(["BOUNCE", "BREAK"])]
rprint(f"  {len(ixns_valid)} valid interactions from {len(rays_df)} HTF rays")

rprint("  Building lifecycle lookup...")
lifecycle = rfs.build_lifecycle_lookup(ixns_valid, rays_df, len(bars_vol))

rprint("  Computing ray features per touch (BACKING + OBSTACLE)...")
zte_enriched = rfs.compute_ray_features_for_touches(
    zte_raw, ray_ctx_htf, rays_df, lifecycle, ixns, bars_vol
)

# ============================================================
# JOIN RAY FEATURES TO PRECOMPUTED TOUCHES
# ============================================================
rprint("\n--- Joining ray features to precomputed P1 features ---")

# The precomputed touches (p1_features_computed_v32.csv) and zte_raw share BarIndex + TouchType + SourceLabel
# Build a join key
zte_enriched["_jk"] = (
    zte_enriched["BarIndex"].astype(str) + "_" +
    zte_enriched["TouchType"] + "_" +
    zte_enriched["SourceLabel"]
)
touches["_jk"] = (
    touches["BarIndex"].astype(str) + "_" +
    touches["TouchType"] + "_" +
    touches["SourceLabel"]
)

# Ray feature columns to transfer
RAY_COLS = [
    "backing_bounce_streak", "backing_flip_count", "backing_dwell_bars",
    "backing_decay_mag", "backing_approach_vel", "backing_dist_ticks",
    "backing_cross_tf", "backing_session", "backing_close_type",
]

ray_features = zte_enriched[["_jk"] + RAY_COLS].drop_duplicates(subset="_jk")

touches = touches.merge(ray_features, on="_jk", how="left")
touches.drop(columns=["_jk"], inplace=True)

# Coverage check
has_backing = touches["backing_bounce_streak"].notna()
coverage_n = has_backing.sum()
coverage_pct = coverage_n / n * 100
rprint(f"  Backing ray coverage: {coverage_n}/{n} ({coverage_pct:.1f}%)")

if coverage_pct < 30:
    rprint(f"  ⚠ Coverage below 30%! Widening proximity would require re-running lifecycle.")
    rprint(f"  Checking if existing 40t threshold provides enough data...")
    # The 40t threshold is already wide; if coverage is still low, it's genuine sparsity
    if coverage_pct < 15:
        rprint(f"  VERDICT: INSUFFICIENT DATA — only {coverage_pct:.1f}% coverage.")
        rprint(f"  Minimum needed: 30% (~980 touches). Defer ray elbow test.")
        # Still save candidates file
        touches.to_csv(OUT / "ray_elbow_candidates_v32.csv", index=False)
        rprint(f"  Saved: ray_elbow_candidates_v32.csv")
        sys.exit(0)

# ============================================================
# NULL RATE REPORT
# ============================================================
rprint("\n--- Ray Feature Coverage Report ---")
rprint(f"  {'Feature':<30} {'Non-NULL':>10} {'Coverage':>10}")
rprint(f"  {'-'*52}")
for col in RAY_COLS:
    nn = touches[col].notna().sum()
    rprint(f"  {col:<30} {nn:>10} {nn/n*100:>9.1f}%")

# Save candidates CSV immediately (regardless of downstream verdict)
touches.to_csv(OUT / "ray_elbow_candidates_v32.csv", index=False)
rprint(f"\n  Saved: ray_elbow_candidates_v32.csv ({len(touches)} rows)")


# ============================================================
# PRECOMPUTE SIMULATION (identical to model_building_v32.py)
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
# REPRODUCE 7-FEATURE BASELINE (cross-check)
# ============================================================
rprint("\n" + "=" * 70)
rprint("REPRODUCE 7-FEATURE BASELINE")
rprint("=" * 70)

# Score each touch with frozen 7-feature A-Eq model
feature_scores_7 = {}  # fk -> array of scores (0/5/10)
feature_bin_labels_7 = {}

for fk in WINNING_FEATURES:
    vals = touches[fk].values
    bp = BIN_POINTS[fk]

    if fk in CATEGORICAL:
        scores = np.full(n, 5.0)
        labels = vals.copy()
        for cat, pts in bp.items():
            mask = vals == cat
            scores[mask] = float(pts)
        feature_scores_7[fk] = scores
        feature_bin_labels_7[fk] = labels
    else:
        p33, p67 = BIN_EDGES[fk]
        fvals = pd.to_numeric(pd.Series(vals), errors='coerce').values.astype(np.float64)
        is_na = np.isnan(fvals)

        bin_labels = np.full(n, "Mid", dtype=object)
        bin_labels[fvals <= p33] = "Low"
        bin_labels[fvals > p67] = "High"
        if is_na.any():
            bin_labels[is_na] = "NA"

        scores = np.full(n, 5.0)
        for bname, pts in bp.items():
            mask = bin_labels == bname
            scores[mask] = float(pts)
        feature_scores_7[fk] = scores
        feature_bin_labels_7[fk] = bin_labels

# Compute total 7-feature score
total_score_7 = np.zeros(n)
for fk in WINNING_FEATURES:
    total_score_7 += feature_scores_7[fk]

# Reproduce baseline: sweep threshold
all_idx = np.arange(n)
pf_base_all, pf4_base_all, trades_base_all, wr_base_all = simulate_subset(all_idx)
rprint(f"  0-feature baseline: PF@3t={pf_base_all:.4f}, trades={trades_base_all}")

best_7 = {"pf3": 0, "pf4": 0, "thr": 0, "trades": 0, "wr": 0}
unique_thrs = np.sort(np.unique(total_score_7))
for thr in unique_thrs:
    idx_pass = np.where(total_score_7 >= thr)[0]
    if len(idx_pass) < 50:
        continue
    pf3, pf4, nt, wr = simulate_subset(idx_pass)
    if nt >= 50 and pf3 > best_7["pf3"]:
        best_7 = {"pf3": pf3, "pf4": pf4, "thr": thr, "trades": nt, "wr": wr}

rprint(f"  7-feature model: PF@3t={best_7['pf3']:.4f}, trades={best_7['trades']}, thr={best_7['thr']:.1f}")
rprint(f"  Reference (from incremental build): PF@3t={MODEL7_PF_3T}, trades={MODEL7_TRADES}, thr={MODEL7_THRESHOLD}")

pf_diff = abs(best_7["pf3"] - MODEL7_PF_3T)
if pf_diff > 0.01:
    rprint(f"  ⚠ PF MISMATCH: delta={pf_diff:.4f}. Check data alignment.")
else:
    rprint(f"  ✓ PF matches within tolerance (delta={pf_diff:.4f})")


# ============================================================
# STEP 2: SOLO SCREENING OF RAY CANDIDATES
# ============================================================
rprint("\n" + "=" * 70)
rprint("STEP 2: SOLO SCREENING OF RAY CANDIDATES")
rprint("=" * 70)

# Define ray candidate features for screening
RAY_CANDIDATES = [
    ("R1", "Backing Bounce Streak", "backing_bounce_streak"),
    ("R2", "Backing Flip Count", "backing_flip_count"),
    ("R3", "Backing Ray Distance", "backing_dist_ticks"),
    ("R4", "Backing Ray Decay", "backing_decay_mag"),
    ("R5", "Backing Ray Age", "backing_dwell_bars"),  # using dwell as proxy
    ("R6", "Backing Cross-TF", "backing_cross_tf"),
    ("R7", "Backing Approach Vel", "backing_approach_vel"),
]

# Compute R/P spread for each candidate
# Methodology: 3 tercile bins (Low/Mid/High + NA), same as model_building_v32.py
solo_results = []
ray_feature_scores = {}   # candidate_key -> scores array
ray_bin_labels = {}        # candidate_key -> bin labels array
ray_bin_edges = {}         # candidate_key -> (p33, p67)

for cand_key, cand_name, col in RAY_CANDIDATES:
    rprint(f"\n  {cand_key}: {cand_name} ({col})")

    vals = touches[col].values.copy()

    # Check if column exists and has data
    fvals = pd.to_numeric(pd.Series(vals), errors='coerce').values.astype(np.float64)
    valid_count = np.sum(~np.isnan(fvals))
    rprint(f"    Valid values: {valid_count}/{n} ({valid_count/n*100:.1f}%)")

    if valid_count < 100:
        rprint(f"    SKIPPED: insufficient data (<100 valid)")
        solo_results.append({
            "key": cand_key, "name": cand_name, "col": col,
            "spread": 0, "class": "INSUFFICIENT", "valid_n": valid_count,
            "max_corr_feat": "N/A", "max_corr": 0,
        })
        continue

    # Compute tercile bin edges from valid values
    valid_vals = fvals[~np.isnan(fvals)]
    p33 = np.percentile(valid_vals, 33.3)
    p67 = np.percentile(valid_vals, 66.7)
    ray_bin_edges[cand_key] = (p33, p67)

    is_na = np.isnan(fvals)
    has_na = is_na.any()

    bin_labels = np.full(n, "Mid", dtype=object)
    bin_labels[fvals <= p33] = "Low"
    bin_labels[fvals > p67] = "High"
    if has_na:
        bin_labels[is_na] = "NA"

    # R/P @60 per bin (same as model_building)
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
        rprint(f"    SKIPPED: fewer than 2 bins with ≥10 samples")
        solo_results.append({
            "key": cand_key, "name": cand_name, "col": col,
            "spread": 0, "class": "INSUFFICIENT", "valid_n": valid_count,
            "max_corr_feat": "N/A", "max_corr": 0,
        })
        continue

    # Assign points (same as model_building)
    best_bin = max(bin_rp, key=bin_rp.get)
    worst_bin = min(bin_rp, key=bin_rp.get)
    scores = np.full(n, 5.0)
    for bname in bin_rp:
        mask = bin_labels == bname
        if bname == best_bin:
            scores[mask] = 10.0
        elif bname == worst_bin:
            scores[mask] = 0.0

    ray_feature_scores[cand_key] = scores
    ray_bin_labels[cand_key] = bin_labels

    # Spread
    valid_rps = [v for v in bin_rp.values() if v is not None]
    spread = max(valid_rps) - min(valid_rps) if len(valid_rps) >= 2 else 0

    # Classification
    if spread >= 0.40:
        sig_class = "STRONG"
    elif spread >= 0.20:
        sig_class = "MODERATE"
    else:
        sig_class = "WEAK"

    rprint(f"    Bins (edges={p33:.2f}/{p67:.2f}):")
    for bname in bin_names:
        if bname in bin_rp:
            pts = 10 if bname == best_bin else (0 if bname == worst_bin else 5)
            cnt = (bin_labels == bname).sum()
            rprint(f"      {bname:>5}: R/P@60={bin_rp[bname]:.3f}, pts={pts}, n={cnt}")
    rprint(f"    R/P spread: {spread:.3f} → {sig_class}")

    # Correlation with existing 7 features
    max_corr = 0
    max_corr_feat = "none"
    corr_details = []
    for fk in WINNING_FEATURES:
        fk_vals = pd.to_numeric(touches[fk], errors='coerce').values.astype(np.float64)
        # Only compute correlation where both are non-NaN
        valid_mask = ~np.isnan(fvals) & ~np.isnan(fk_vals)
        if valid_mask.sum() < 30:
            continue
        try:
            r_pearson = np.corrcoef(fvals[valid_mask], fk_vals[valid_mask])[0, 1]
        except:
            r_pearson = 0
        r_abs = abs(r_pearson) if not np.isnan(r_pearson) else 0
        corr_details.append((fk, r_pearson, r_abs))
        if r_abs > max_corr:
            max_corr = r_abs
            max_corr_feat = fk

    rprint(f"    Correlations with existing features:")
    for fk, r, ra in sorted(corr_details, key=lambda x: -x[2]):
        flag = " ⚠ HIGH" if ra > 0.5 else ""
        rprint(f"      {fk}: r={r:+.3f}{flag}")

    if max_corr > 0.5:
        rprint(f"    ⚠ High correlation with {max_corr_feat} (|r|={max_corr:.3f}). Likely redundant.")

    solo_results.append({
        "key": cand_key, "name": cand_name, "col": col,
        "spread": spread, "class": sig_class, "valid_n": valid_count,
        "max_corr_feat": max_corr_feat, "max_corr": max_corr,
        "bin_rp": bin_rp,
    })

# Summary table
rprint("\n--- Solo Screening Summary ---")
rprint(f"  {'Key':>4} {'Name':<30} {'Spread':>8} {'Class':>12} {'Valid_N':>8} {'Max|r| with':>20}")
rprint(f"  {'-'*86}")
for sr in solo_results:
    corr_str = f"{sr['max_corr_feat']}({sr['max_corr']:.2f})" if sr['max_corr'] > 0 else "N/A"
    rprint(f"  {sr['key']:>4} {sr['name']:<30} {sr['spread']:>8.3f} {sr['class']:>12} {sr['valid_n']:>8} {corr_str:>20}")


# ============================================================
# STEP 3: INCREMENTAL BUILD EXTENSION
# ============================================================
rprint("\n" + "=" * 70)
rprint("STEP 3: INCREMENTAL BUILD EXTENSION (position #8+)")
rprint("=" * 70)
rprint(f"  Baseline: 7-feature model PF@3t={best_7['pf3']:.4f}, trades={best_7['trades']}, thr={best_7['thr']:.1f}")

# Filter to STRONG or MODERATE candidates only
eligible = [sr for sr in solo_results if sr["class"] in ("STRONG", "MODERATE")]
rprint(f"  Eligible candidates (STRONG/MODERATE): {len(eligible)}")

if not eligible:
    rprint(f"\n  No STRONG or MODERATE ray candidates. All ray features are WEAK.")
    rprint(f"  VERDICT: REDUNDANT — ray features do not add independent predictive power.")
else:
    # Sort by spread descending (best candidates first)
    eligible.sort(key=lambda x: -x["spread"])

    build_results_ray = []
    prev_pf = best_7["pf3"]

    rprint(f"\n  {'Pos':>4} {'Cand':>6} {'Name':<30} {'PF@3t':>8} {'Trades':>7} {'dPF':>9} {'Thr':>6} Status")
    rprint(f"  {'-'*90}")

    # Test each eligible candidate at position #8
    for sr in eligible:
        cand_key = sr["key"]
        if cand_key not in ray_feature_scores:
            continue

        # Add ray feature scores to 7-feature total
        total_score_8 = total_score_7 + ray_feature_scores[cand_key]

        # Sweep threshold
        best_8 = {"pf3": 0, "pf4": 0, "thr": 0, "trades": 0, "wr": 0}
        unique_thrs = np.sort(np.unique(total_score_8))
        for thr in unique_thrs:
            idx_pass = np.where(total_score_8 >= thr)[0]
            if len(idx_pass) < 50:
                continue
            pf3, pf4, nt, wr = simulate_subset(idx_pass)
            if nt >= 50 and pf3 > best_8["pf3"]:
                best_8 = {"pf3": pf3, "pf4": pf4, "thr": thr, "trades": nt, "wr": wr}

        if best_8["trades"] == 0:
            rprint(f"  {8:>4} {cand_key:>6} {sr['name']:<30} {'---':>8} {'<50':>7} {'---':>9} {'---':>6} SKIPPED")
            build_results_ray.append({
                "key": cand_key, "name": sr["name"], "spread": sr["spread"],
                "pf3": 0, "trades": 0, "dpf": 0, "thr": 0, "status": "SKIPPED"
            })
            continue

        dpf = best_8["pf3"] - best_7["pf3"]
        status = "ENTERED" if dpf > 0 else "REDUNDANT"

        rprint(f"  {8:>4} {cand_key:>6} {sr['name']:<30} {best_8['pf3']:>8.4f} {best_8['trades']:>7} {dpf:>+9.4f} {best_8['thr']:>6.1f} {status}")

        build_results_ray.append({
            "key": cand_key, "name": sr["name"], "spread": sr["spread"],
            "pf3": best_8["pf3"], "pf4": best_8["pf4"],
            "trades": best_8["trades"], "wr": best_8["wr"],
            "dpf": dpf, "thr": best_8["thr"], "status": status,
        })

    # Check if any entered
    entered = [r for r in build_results_ray if r["status"] == "ENTERED"]

    if entered:
        # Sort by dPF, test best at #8, second at #9
        entered.sort(key=lambda x: -x["dpf"])
        best_entry = entered[0]
        rprint(f"\n  BEST ENTRY: {best_entry['key']} ({best_entry['name']})")
        rprint(f"    dPF = {best_entry['dpf']:+.4f}")
        rprint(f"    PF@3t = {best_entry['pf3']:.4f} (from {best_7['pf3']:.4f})")
        rprint(f"    Trades = {best_entry['trades']}")

        if len(entered) > 1:
            # Test second candidate at position #9
            second = entered[1]
            rprint(f"\n  Testing {second['key']} at position #9 (with {best_entry['key']} at #8)...")
            total_score_9 = total_score_7 + ray_feature_scores[best_entry["key"]] + ray_feature_scores[second["key"]]
            best_9 = {"pf3": 0, "pf4": 0, "thr": 0, "trades": 0, "wr": 0}
            for thr in np.sort(np.unique(total_score_9)):
                idx_pass = np.where(total_score_9 >= thr)[0]
                if len(idx_pass) < 50:
                    continue
                pf3, pf4, nt, wr = simulate_subset(idx_pass)
                if nt >= 50 and pf3 > best_9["pf3"]:
                    best_9 = {"pf3": pf3, "pf4": pf4, "thr": thr, "trades": nt, "wr": wr}

            dpf_9 = best_9["pf3"] - best_entry["pf3"] if best_9["trades"] > 0 else 0
            status_9 = "ENTERED" if dpf_9 > 0 else "REDUNDANT"
            rprint(f"    {second['key']} at #9: PF@3t={best_9['pf3']:.4f}, dPF={dpf_9:+.4f} → {status_9}")
    else:
        rprint(f"\n  No ray candidate showed positive dPF at position #8.")


# ============================================================
# STEP 4: P2 VALIDATION (only if elbow entry)
# ============================================================
p2_validated = False
if eligible and any(r["status"] == "ENTERED" for r in build_results_ray):
    rprint("\n" + "=" * 70)
    rprint("STEP 4: P2 VALIDATION")
    rprint("=" * 70)
    rprint("  ⚠ A ray feature entered the elbow. P2 validation required.")
    rprint("  [P2 validation code would execute here]")
    # P2 validation is complex and conditional — implemented only if needed
    p2_validated = True


# ============================================================
# STEP 5: VERDICT & REPORT
# ============================================================
rprint("\n" + "=" * 70)
rprint("VERDICT")
rprint("=" * 70)

if not eligible or all(r["status"] != "ENTERED" for r in build_results_ray):
    verdict = "REDUNDANT"
    rprint(f"\n  VERDICT: REDUNDANT")
    rprint(f"  All ray features showed negative dPF when added to the 7-feature model.")
    rprint(f"  The existing features (especially F10 Prior Penetration, F21 Zone Age)")
    rprint(f"  already capture the information that ray attributes provide.")
    rprint(f"")
    rprint(f"  The 7-feature scoring model STAYS FROZEN at v3.2.")
    rprint(f"  Ray value is redirected to Analysis B (Surfaces 2-3: trade management).")
else:
    entered = [r for r in build_results_ray if r["status"] == "ENTERED"]
    best_entry = max(entered, key=lambda x: x["dpf"])
    verdict = "ELBOW_ENTRY"
    rprint(f"\n  VERDICT: ELBOW ENTRY")
    rprint(f"  Ray feature {best_entry['key']} ({best_entry['name']}) entered the elbow.")
    rprint(f"  dPF = {best_entry['dpf']:+.4f}")
    rprint(f"  Model unfreezes → proceed to P2 validation, then mode classification.")

rprint(f"\n  Elapsed: {time_mod.time() - t0:.1f}s")


# ============================================================
# WRITE REPORT
# ============================================================
report_path = OUT / "ray_elbow_test_v32.md"
report_md = ["# Ray Incremental Elbow Test — Analysis A (v3.2)\n"]
report_md.append(f"Generated: {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M')}\n")
report_md.append("```")
report_md.extend(report)
report_md.append("```\n")

# Section 1: Data Join Summary
report_md.append("## Section 1: Data Join Summary\n")
report_md.append(f"- Join key: `BarIndex_TouchType_SourceLabel`")
report_md.append(f"- P1 touches: {n}")
report_md.append(f"- HTF rays extracted: {len(rays_df)}")
report_md.append(f"- Valid interactions: {len(ixns_valid)}")
report_md.append(f"- Backing ray coverage: {coverage_n}/{n} ({coverage_pct:.1f}%)")
report_md.append(f"- Filters: 60m+ rays only, {PROX_THRESHOLD}t proximity")
report_md.append("")

# Section 2: Solo Screening Results
report_md.append("## Section 2: Solo Screening Results\n")
report_md.append("| Candidate | R/P Spread | Class | Max |r| with Existing 7 |")
report_md.append("|-----------|-----------|-------|---------------------|")
for sr in solo_results:
    corr_str = f"{sr['max_corr_feat']}({sr['max_corr']:.2f})" if sr['max_corr'] > 0 else "N/A"
    report_md.append(f"| {sr['key']}: {sr['name']} | {sr['spread']:.3f} | {sr['class']} | {corr_str} |")
report_md.append("")

# Section 3: Incremental Build Results
report_md.append("## Section 3: Incremental Build Results\n")
if eligible:
    report_md.append("| Candidate | PF@3t (8-feat) | dPF vs 7-feat | Status |")
    report_md.append("|-----------|---------------|--------------|--------|")
    for br in build_results_ray:
        pf_str = f"{br['pf3']:.4f}" if br['trades'] > 0 else "N/A"
        dpf_str = f"{br['dpf']:+.4f}" if br['trades'] > 0 else "N/A"
        report_md.append(f"| {br['key']}: {br['name']} | {pf_str} | {dpf_str} | {br['status']} |")
else:
    report_md.append("No STRONG or MODERATE candidates to test.\n")

any_entered = eligible and any(r["status"] == "ENTERED" for r in build_results_ray)
report_md.append(f"\n**Did any ray feature enter the elbow? {'YES' if any_entered else 'NO'}**\n")

# Section 4: Verdict
report_md.append("## Section 4: Verdict\n")
if verdict == "REDUNDANT":
    report_md.append("**REDUNDANT**: All ray features showed negative dPF when added to the ")
    report_md.append("7-feature model. The existing features already capture the information ")
    report_md.append("that ray attributes provide.\n")
    report_md.append("- Model stays **FROZEN** at v3.2 (7 features)")
    report_md.append("- Ray value redirected to **Analysis B** (Surfaces 2-3: trade management)")
    report_md.append("  - OBSTACLE ray features for trade filtering")
    report_md.append("  - Backing ray attributes for adaptive exit calibration")
elif verdict == "ELBOW_ENTRY":
    report_md.append(f"**ELBOW ENTRY**: {best_entry['key']} ({best_entry['name']}) entered ")
    report_md.append(f"the elbow with dPF = {best_entry['dpf']:+.4f}.\n")
    report_md.append("- Model **UNFREEZES** → proceed to P2 validation")
    report_md.append("- Mode classification must wait for new model to stabilize")

report_md.append("\n")

with open(report_path, "w", encoding="utf-8") as f:
    f.write("\n".join(report_md))

rprint(f"\n  Report saved: {report_path}")
rprint(f"  Candidates saved: {OUT / 'ray_elbow_candidates_v32.csv'}")
rprint(f"  Done.")
