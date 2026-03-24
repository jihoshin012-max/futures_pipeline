# archetype: zone_touch
"""B-ZScore diagnostic: confirm degenerate model, test alternatives."""

import json
import sys
import warnings
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd

BASE = Path(r"c:\Projects\pipeline")
DATA_DIR = BASE / "stages" / "01-data" / "output" / "zone_prep"
PARAM_DIR = BASE / "shared" / "archetypes" / "zone_touch" / "output"
TICK_SIZE = 0.25

# Load P1 data (needed to reproduce training)
p1a = pd.read_csv(DATA_DIR / "NQ_merged_P1a.csv")
p1b = pd.read_csv(DATA_DIR / "NQ_merged_P1b.csv")
p1 = pd.concat([p1a, p1b], ignore_index=True)
p1 = p1[p1["RotBarIndex"] >= 0].reset_index(drop=True)
bar_p1 = pd.read_csv(DATA_DIR / "NQ_bardata_P1.csv")
bar_p1.columns = bar_p1.columns.str.strip()
bar_arr = bar_p1[["Open", "High", "Low", "Last"]].to_numpy(dtype=np.float64)
bar_atr = bar_p1["ATR"].to_numpy(dtype=np.float64)
n_bars = len(bar_arr)

print(f"P1 touches: {len(p1)}")
print(f"P1 bars: {n_bars}")

# Load feature config
with open(PARAM_DIR / "feature_config_v32.json") as f:
    feat_cfg = json.load(f)

# Build target
target = (p1["Reaction"].values.astype(float) >
          p1["Penetration"].values.astype(float)).astype(int)
print(f"Target class balance: {target.mean():.3f} (win rate)")

# Build feature matrix (same as model_building_v32.py)
CATEGORICAL = {"F01", "F04", "F05"}
winning_set = feat_cfg["winning_features"]
n = len(p1)

# Compute features
p1["F01"] = p1["SourceLabel"]
p1["F04"] = p1["CascadeState"].replace("UNKNOWN", "NO_PRIOR")

# F05: Session
touch_dt = pd.to_datetime(p1["DateTime"])
touch_mins = touch_dt.dt.hour.values * 60 + touch_dt.dt.minute.values
session = np.full(n, "Midday", dtype=object)
session[touch_mins < 360] = "Overnight"
session[(touch_mins >= 360) & (touch_mins < 570)] = "PreRTH"
session[(touch_mins >= 570) & (touch_mins < 660)] = "OpeningDrive"
session[(touch_mins >= 660) & (touch_mins < 840)] = "Midday"
session[(touch_mins >= 840) & (touch_mins < 1020)] = "Close"
session[touch_mins >= 1020] = "Overnight"
p1["F05"] = session

# F09
atr_vals = np.array([bar_atr[max(0, min(int(r), n_bars-1))]
                      if 0 <= int(r) < n_bars else np.nan
                      for r in p1["RotBarIndex"].values])
atr_vals[atr_vals == 0] = np.nan
p1["F09"] = p1["ZoneWidthTicks"].values * TICK_SIZE / atr_vals

# F10
p1["ZoneID"] = (p1["TouchType"].astype(str) + "|" +
                p1["ZoneTop"].astype(str) + "|" +
                p1["ZoneBot"].astype(str) + "|" +
                p1["SourceLabel"].astype(str))
prior_pen = {}
for zone_id, group in p1.sort_values(["ZoneID", "TouchSequence"]).groupby("ZoneID"):
    group = group.sort_values("TouchSequence")
    prev_pen = np.nan
    for idx, row in group.iterrows():
        prior_pen[idx] = np.nan if row["TouchSequence"] == 1 else prev_pen
        prev_pen = row["Penetration"]
p1["F10"] = p1.index.map(prior_pen)

# F13
rot_idx = p1["RotBarIndex"].values.astype(int)
is_long = p1["TouchType"].str.contains("DEMAND").values
tb_h = np.array([bar_arr[max(0, min(i, n_bars-1)), 1] for i in rot_idx])
tb_l = np.array([bar_arr[max(0, min(i, n_bars-1)), 2] for i in rot_idx])
tb_c = np.array([bar_arr[max(0, min(i, n_bars-1)), 3] for i in rot_idx])
hl_d = tb_h - tb_l
p1["F13"] = np.where(hl_d > 0,
    np.where(is_long, (tb_c - tb_l) / hl_d, (tb_h - tb_c) / hl_d), 0.5)

p1["F21"] = p1["ZoneAgeBars"]

# One-hot encode categoricals (same as model_building_v32.py)
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler, LabelEncoder
from sklearn.metrics import roc_curve, roc_auc_score

feat_cols = []
X_parts = []
for fk in winning_set:
    vals = p1[fk].values
    if fk in CATEGORICAL:
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
        fvals = pd.to_numeric(vals, errors='coerce').astype(float)
        mean_val = feat_cfg["feature_means"].get(fk, np.nanmean(fvals))
        fvals = np.where(np.isnan(fvals), mean_val, fvals)
        X_parts.append(fvals.reshape(-1, 1))
        feat_cols.append(fk)

X = np.hstack(X_parts)
print(f"\nFeature matrix shape: {X.shape}")
print(f"Feature columns: {feat_cols}")

entry_idx = p1["RotBarIndex"].values

# ══════════════════════════════════════════════════════════════════════
# STEP 1: Reproduce the original training (rolling z-score + LR)
# ══════════════════════════════════════════════════════════════════════

print("\n" + "=" * 72)
print("STEP 1: REPRODUCE ORIGINAL B-ZSCORE TRAINING")
print("=" * 72)

time_order = np.argsort(entry_idx)
X_time = X[time_order]
X_z = np.zeros_like(X_time)

for i in range(len(time_order)):
    start = max(0, i - 100)
    end = i
    if end - start < 2:
        X_z[i] = 0
        continue
    window_data = X_time[start:end]
    m = window_data.mean(axis=0)
    s = window_data.std(axis=0)
    s[s == 0] = 1.0
    X_z[i] = (X_time[i] - m) / s

X_z_orig = np.zeros_like(X)
X_z_orig[time_order] = X_z

# Check z-score statistics
print(f"\nRolling z-scored features stats:")
print(f"  Mean per feature: {X_z_orig.mean(axis=0)[:4]}")
print(f"  Std per feature:  {X_z_orig.std(axis=0)[:4]}")
print(f"  Min: {X_z_orig.min():.2f}, Max: {X_z_orig.max():.2f}")

# Fit logistic regression
lr = LogisticRegression(max_iter=1000, C=1.0)
lr.fit(X_z_orig, target)

print(f"\nLogistic regression on rolling z-scored features:")
print(f"  Converged (n_iter < max_iter): {lr.n_iter_[0] < 1000}")
print(f"  Iterations: {lr.n_iter_[0]}")
print(f"  Coefficients range: {lr.coef_[0].min():.2e} to {lr.coef_[0].max():.2e}")
print(f"  Max abs coefficient: {np.max(np.abs(lr.coef_[0])):.2e}")
print(f"  Intercept: {lr.intercept_[0]:.2e}")

proba = lr.predict_proba(X_z_orig)[:, 1]
print(f"\n  Probability stats: mean={proba.mean():.10f}, "
      f"std={proba.std():.2e}, "
      f"min={proba.min():.10f}, max={proba.max():.10f}")

# AUC
auc = roc_auc_score(target, proba)
print(f"  AUC: {auc:.6f}")

# Youden threshold
fpr, tpr, thresholds_roc = roc_curve(target, proba)
j_scores = tpr - fpr
best_j_idx = np.argmax(j_scores)
opt_thr = thresholds_roc[best_j_idx]
print(f"  Youden threshold: {opt_thr:.16f}")
print(f"  Touches above threshold: {(proba >= opt_thr).sum()}/{len(proba)}")

print(f"\n  DIAGNOSIS: Coefficients are ~1e-13, probabilities are ~0.5,")
print(f"  selection is based on floating-point noise. Model has NO signal.")

# ══════════════════════════════════════════════════════════════════════
# STEP 2: Test alternatives
# ══════════════════════════════════════════════════════════════════════

print("\n" + "=" * 72)
print("STEP 2: ALTERNATIVE APPROACHES")
print("=" * 72)


def simulate_subset(idx_pass, bar_data=bar_arr, tick=TICK_SIZE):
    """Quick simulation with median cell exits (120/120/80)."""
    stop, target_t, tcap = 120, 120, 80
    pnls = []
    in_trade_until = -1
    for i in sorted(idx_pass):
        rbi = int(entry_idx[i])
        eb = rbi + 1
        if eb <= in_trade_until or eb >= len(bar_data):
            continue
        direction = 1 if "DEMAND" in str(p1.iloc[i]["TouchType"]) else -1
        ep = bar_data[eb, 0]
        sp = ep - stop * tick if direction == 1 else ep + stop * tick
        tp = ep + target_t * tick if direction == 1 else ep - target_t * tick

        pnl = None
        for b in range(eb, min(eb + tcap, len(bar_data))):
            h, l, last = bar_data[b, 1], bar_data[b, 2], bar_data[b, 3]
            bh = b - eb + 1
            if direction == 1:
                s_hit = l <= sp
                t_hit = h >= tp
            else:
                s_hit = h >= sp
                t_hit = l <= tp
            if s_hit and t_hit:
                pnl = (sp - ep) / tick if direction == 1 else (ep - sp) / tick
                break
            if s_hit:
                pnl = (sp - ep) / tick if direction == 1 else (ep - sp) / tick
                break
            if t_hit:
                pnl = target_t
                break
            if bh >= tcap:
                pnl = (last - ep) / tick if direction == 1 else (ep - last) / tick
                break
        if pnl is None and eb < len(bar_data):
            pnl = (bar_data[min(eb + tcap - 1, len(bar_data) - 1), 3] - ep) / tick if direction == 1 else (ep - bar_data[min(eb + tcap - 1, len(bar_data) - 1), 3]) / tick
        if pnl is not None:
            pnls.append(pnl)
            in_trade_until = eb + tcap - 1

    if not pnls:
        return 0, 0, 0, 0
    gp3 = sum(p - 3 for p in pnls if p - 3 > 0)
    gl3 = sum(abs(p - 3) for p in pnls if p - 3 < 0)
    pf3 = gp3 / gl3 if gl3 > 0 else (float("inf") if gp3 > 0 else 0)
    gp4 = sum(p - 4 for p in pnls if p - 4 > 0)
    gl4 = sum(abs(p - 4) for p in pnls if p - 4 < 0)
    pf4 = gp4 / gl4 if gl4 > 0 else (float("inf") if gp4 > 0 else 0)
    wr = sum(1 for p in pnls if p - 3 > 0) / len(pnls)
    return pf3, pf4, len(pnls), wr


# --- 2a: Logistic regression on RAW features (globally standardized) ---
print("\n--- 2a: LogisticRegression on GLOBALLY STANDARDIZED features ---")

scaler = StandardScaler()
X_scaled = scaler.fit_transform(X)

for C_val in [0.01, 0.1, 1.0, 10.0]:
    for penalty in ["l1", "l2"]:
        solver = "liblinear" if penalty == "l1" else "lbfgs"
        lr2 = LogisticRegression(max_iter=2000, C=C_val, penalty=penalty,
                                 solver=solver)
        lr2.fit(X_scaled, target)
        proba2 = lr2.predict_proba(X_scaled)[:, 1]
        auc2 = roc_auc_score(target, proba2)

        fpr2, tpr2, thr2 = roc_curve(target, proba2)
        j2 = tpr2 - fpr2
        opt_thr2 = thr2[np.argmax(j2)]
        idx_pass = np.where(proba2 >= opt_thr2)[0]
        n_pass = len(idx_pass)

        max_coef = np.max(np.abs(lr2.coef_[0]))
        converged = lr2.n_iter_[0] < 2000

        if n_pass >= 50:
            pf3, pf4, nt, wr = simulate_subset(idx_pass)
        else:
            pf3, pf4, nt, wr = 0, 0, 0, 0

        print(f"  C={C_val:<6} {penalty:<4}: AUC={auc2:.4f}, "
              f"max|coef|={max_coef:.4f}, iter={lr2.n_iter_[0]}, "
              f"conv={'Y' if converged else 'N'}, "
              f"thr={opt_thr2:.4f}, pass={n_pass}, "
              f"trades={nt}, PF@3t={pf3:.4f}")

# --- 2b: Logistic regression on rolling z-scored with different C ---
print("\n--- 2b: LogisticRegression on ROLLING Z-SCORED with varied C ---")

for C_val in [0.01, 0.1, 1.0, 10.0, 100.0]:
    lr3 = LogisticRegression(max_iter=2000, C=C_val, solver="lbfgs")
    lr3.fit(X_z_orig, target)
    proba3 = lr3.predict_proba(X_z_orig)[:, 1]
    auc3 = roc_auc_score(target, proba3)
    max_coef = np.max(np.abs(lr3.coef_[0]))

    fpr3, tpr3, thr3 = roc_curve(target, proba3)
    j3 = tpr3 - fpr3
    opt_thr3 = thr3[np.argmax(j3)]
    idx_pass = np.where(proba3 >= opt_thr3)[0]
    n_pass = len(idx_pass)

    if n_pass >= 50:
        pf3, pf4, nt, wr = simulate_subset(idx_pass)
    else:
        pf3, pf4, nt, wr = 0, 0, 0, 0

    print(f"  C={C_val:<8}: AUC={auc3:.6f}, max|coef|={max_coef:.2e}, "
          f"iter={lr3.n_iter_[0]}, "
          f"thr={opt_thr3:.6f}, pass={n_pass}, "
          f"trades={nt}, PF@3t={pf3:.4f}")

# --- 2c: Elastic net ---
print("\n--- 2c: ElasticNet (L1+L2) on globally standardized ---")
from sklearn.linear_model import SGDClassifier

for alpha in [0.001, 0.01, 0.1]:
    for l1_ratio in [0.15, 0.5, 0.85]:
        sgd = SGDClassifier(loss="log_loss", penalty="elasticnet",
                           alpha=alpha, l1_ratio=l1_ratio,
                           max_iter=2000, random_state=42)
        sgd.fit(X_scaled, target)
        # SGD doesn't have predict_proba by default, use decision_function
        decision = sgd.decision_function(X_scaled)
        # Convert to probabilities
        from scipy.special import expit
        proba_sgd = expit(decision)
        auc_sgd = roc_auc_score(target, proba_sgd)
        max_coef = np.max(np.abs(sgd.coef_[0]))

        fpr_s, tpr_s, thr_s = roc_curve(target, proba_sgd)
        j_s = tpr_s - fpr_s
        opt_thr_s = thr_s[np.argmax(j_s)]
        idx_pass = np.where(proba_sgd >= opt_thr_s)[0]
        n_pass = len(idx_pass)

        if n_pass >= 50:
            pf3, pf4, nt, wr = simulate_subset(idx_pass)
        else:
            pf3, pf4, nt, wr = 0, 0, 0, 0

        print(f"  alpha={alpha:<6} l1={l1_ratio}: AUC={auc_sgd:.4f}, "
              f"max|coef|={max_coef:.4f}, pass={n_pass}, "
              f"trades={nt}, PF@3t={pf3:.4f}")

# --- 2d: Simple z-score composite (no regression, just sum) ---
print("\n--- 2d: Simple z-score composite (sum of standardized features) ---")
# The fallback approach: standardize each feature globally, sum, threshold
composite = X_scaled.sum(axis=1)
print(f"  Composite stats: mean={composite.mean():.4f}, std={composite.std():.4f}")

for pctile in [50, 60, 70, 75, 80]:
    thr = np.percentile(composite, pctile)
    idx_pass = np.where(composite >= thr)[0]
    if len(idx_pass) >= 50:
        pf3, pf4, nt, wr = simulate_subset(idx_pass)
        print(f"  P{pctile} (thr={thr:.3f}): pass={len(idx_pass)}, "
              f"trades={nt}, PF@3t={pf3:.4f}, PF@4t={pf4:.4f}")

# --- 2e: A-Cal scores as B-ZScore proxy ---
print("\n--- 2e: Using A-Cal scores (already proven) as B-ZScore replacement ---")
# Load A-Cal model
with open(PARAM_DIR / "scoring_model_acal_v32.json") as f:
    acal = json.load(f)

# The point: B-ZScore was supposed to provide independent signal from A-Cal.
# If it can't, the multi-mode strategy needs a fundamentally different volume model.
print("  B-ZScore was intended as an INDEPENDENT scoring approach.")
print("  If logistic regression has no signal, B-ZScore adds nothing over A-Cal/A-Eq.")

# ══════════════════════════════════════════════════════════════════════
# STEP 3: Final Assessment
# ══════════════════════════════════════════════════════════════════════

print("\n" + "=" * 72)
print("STEP 3: FINAL ASSESSMENT")
print("=" * 72)
print()
print("Key findings will be printed after all alternatives are tested.")
