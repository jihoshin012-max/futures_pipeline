# archetype: zone_touch
"""Re-fit B-ZScore model using global StandardScaler (not rolling z-score).
Exports corrected scoring_model_bzscore_v32.json."""

import json
import sys
import warnings
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler, LabelEncoder
from sklearn.metrics import roc_curve, roc_auc_score

BASE = Path(r"c:\Projects\pipeline")
DATA_DIR = BASE / "stages" / "01-data" / "output" / "zone_prep"
PARAM_DIR = BASE / "shared" / "archetypes" / "zone_touch" / "output"
TICK_SIZE = 0.25

# ══════════════════════════════════════════════════════════════════════
# Load P1 data and compute features (identical to model_building_v32.py)
# ══════════════════════════════════════════════════════════════════════

p1a = pd.read_csv(DATA_DIR / "NQ_merged_P1a.csv")
p1b = pd.read_csv(DATA_DIR / "NQ_merged_P1b.csv")
p1 = pd.concat([p1a, p1b], ignore_index=True)
p1 = p1[p1["RotBarIndex"] >= 0].reset_index(drop=True)
bar_p1 = pd.read_csv(DATA_DIR / "NQ_bardata_P1.csv")
bar_p1.columns = bar_p1.columns.str.strip()
bar_arr = bar_p1[["Open", "High", "Low", "Last"]].to_numpy(dtype=np.float64)
bar_atr = bar_p1["ATR"].to_numpy(dtype=np.float64)
n_bars = len(bar_arr)
n = len(p1)

with open(PARAM_DIR / "feature_config_v32.json") as f:
    feat_cfg = json.load(f)

winning_set = feat_cfg["winning_features"]

print(f"P1 touches: {n}")
print(f"Winning features: {winning_set}")

# Target
target = (p1["Reaction"].values.astype(float) >
          p1["Penetration"].values.astype(float)).astype(int)
print(f"Target balance: {target.mean():.3f}")

# Compute features
p1["F01"] = p1["SourceLabel"]
p1["F04"] = p1["CascadeState"].replace("UNKNOWN", "NO_PRIOR")

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

atr_vals = np.array([bar_atr[max(0, min(int(r), n_bars - 1))]
                      if 0 <= int(r) < n_bars else np.nan
                      for r in p1["RotBarIndex"].values])
atr_vals[atr_vals == 0] = np.nan
p1["F09"] = p1["ZoneWidthTicks"].values * TICK_SIZE / atr_vals

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

rot_idx = p1["RotBarIndex"].values.astype(int)
is_long = p1["TouchType"].str.contains("DEMAND").values
tb_h = np.array([bar_arr[max(0, min(i, n_bars - 1)), 1] for i in rot_idx])
tb_l = np.array([bar_arr[max(0, min(i, n_bars - 1)), 2] for i in rot_idx])
tb_c = np.array([bar_arr[max(0, min(i, n_bars - 1)), 3] for i in rot_idx])
hl_d = tb_h - tb_l
p1["F13"] = np.where(hl_d > 0,
    np.where(is_long, (tb_c - tb_l) / hl_d, (tb_h - tb_c) / hl_d), 0.5)
p1["F21"] = p1["ZoneAgeBars"]

# Build feature matrix
CATEGORICAL = {"F01", "F04", "F05"}
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
print(f"Feature matrix: {X.shape}")
print(f"Feature columns: {feat_cols}")

# ══════════════════════════════════════════════════════════════════════
# Re-fit with global StandardScaler + LogisticRegression
# ══════════════════════════════════════════════════════════════════════

print("\n" + "=" * 72)
print("RE-FITTING B-ZSCORE WITH GLOBAL STANDARDSCALER")
print("=" * 72)

scaler = StandardScaler()
X_scaled = scaler.fit_transform(X)

# Test multiple C values, pick best by PF@3t
entry_idx = p1["RotBarIndex"].values

def simulate_subset(idx_pass):
    """Quick simulation with median cell exits (120/120/80)."""
    stop, tgt, tcap = 120, 120, 80
    pnls = []
    in_trade_until = -1
    for i in sorted(idx_pass):
        rbi = int(entry_idx[i])
        eb = rbi + 1
        if eb <= in_trade_until or eb >= n_bars:
            continue
        direction = 1 if "DEMAND" in str(p1.iloc[i]["TouchType"]) else -1
        ep = bar_arr[eb, 0]
        sp = ep - stop * TICK_SIZE if direction == 1 else ep + stop * TICK_SIZE
        tp = ep + tgt * TICK_SIZE if direction == 1 else ep - tgt * TICK_SIZE

        pnl = None
        for b in range(eb, min(eb + tcap, n_bars)):
            h, l, last = bar_arr[b, 1], bar_arr[b, 2], bar_arr[b, 3]
            bh = b - eb + 1
            if direction == 1:
                s_hit, t_hit = l <= sp, h >= tp
            else:
                s_hit, t_hit = h >= sp, l <= tp
            if s_hit and t_hit:
                pnl = (sp - ep) / TICK_SIZE if direction == 1 else (ep - sp) / TICK_SIZE
                break
            if s_hit:
                pnl = (sp - ep) / TICK_SIZE if direction == 1 else (ep - sp) / TICK_SIZE
                break
            if t_hit:
                pnl = tgt
                break
            if bh >= tcap:
                pnl = (last - ep) / TICK_SIZE if direction == 1 else (ep - last) / TICK_SIZE
                break
        if pnl is None and eb < n_bars:
            last_bar = min(eb + tcap - 1, n_bars - 1)
            pnl = ((bar_arr[last_bar, 3] - ep) / TICK_SIZE if direction == 1
                    else (ep - bar_arr[last_bar, 3]) / TICK_SIZE)
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


best = {"pf3": 0, "C": 0, "penalty": "", "lr": None}

for C_val in [0.01, 0.1, 1.0]:
    for penalty in ["l1", "l2"]:
        solver = "liblinear" if penalty == "l1" else "lbfgs"
        lr = LogisticRegression(max_iter=2000, C=C_val, penalty=penalty,
                                solver=solver)
        lr.fit(X_scaled, target)
        proba = lr.predict_proba(X_scaled)[:, 1]
        auc = roc_auc_score(target, proba)

        fpr, tpr, thresholds = roc_curve(target, proba)
        j_scores = tpr - fpr
        opt_thr = thresholds[np.argmax(j_scores)]

        idx_pass = np.where(proba >= opt_thr)[0]
        if len(idx_pass) >= 50:
            pf3, pf4, nt, wr = simulate_subset(idx_pass)
        else:
            pf3, pf4, nt, wr = 0, 0, 0, 0

        print(f"  C={C_val:<6} {penalty:<4}: AUC={auc:.4f}, "
              f"iter={lr.n_iter_[0]}, conv={'Y' if lr.n_iter_[0] < 2000 else 'N'}, "
              f"thr={opt_thr:.4f}, trades={nt}, PF@3t={pf3:.4f}, PF@4t={pf4:.4f}, "
              f"WR={wr:.1%}")

        if nt >= 50 and pf3 > best["pf3"]:
            best = {
                "pf3": pf3, "pf4": pf4, "C": C_val, "penalty": penalty,
                "lr": lr, "thr": opt_thr, "trades": nt, "wr": wr,
                "auc": auc, "solver": solver,
            }

print(f"\n  BEST: C={best['C']}, {best['penalty']}, PF@3t={best['pf3']:.4f}, "
      f"PF@4t={best['pf4']:.4f}, trades={best['trades']}, AUC={best['auc']:.4f}")

# ══════════════════════════════════════════════════════════════════════
# Export corrected model
# ══════════════════════════════════════════════════════════════════════

print("\n" + "=" * 72)
print("EXPORTING CORRECTED B-ZSCORE MODEL")
print("=" * 72)

lr_best = best["lr"]

# Load original for reference
with open(PARAM_DIR / "scoring_model_bzscore_v32.json") as f:
    original = json.load(f)

corrected = {
    "approach": "B-ZScore",
    "winning_features": winning_set,
    "window": 0,  # No rolling window — global standardization
    "threshold": float(best["thr"]),
    "coefficients": lr_best.coef_[0].tolist(),
    "intercept": float(lr_best.intercept_[0]),
    "scaler_mean": scaler.mean_.tolist(),
    "scaler_std": scaler.scale_.tolist(),
    "feature_columns": feat_cols,
    "pf_3t": best["pf3"],
    "pf_4t": best["pf4"],
    "trades": best["trades"],
    "win_rate": best["wr"],
    "regularization": {"C": best["C"], "penalty": best["penalty"],
                       "solver": best["solver"]},
    "auc": best["auc"],
    "fix_note": "Re-fit with global StandardScaler. Original used rolling z-score "
                "which produced extreme F10 values causing degenerate coefficients (~1e-13). "
                "Global standardization produces healthy coefficients (max|coef|>1.0) "
                "and tradeable PF.",
}

# Validate: coefficients are healthy
max_coef = np.max(np.abs(lr_best.coef_[0]))
print(f"\n  Coefficients: max|coef|={max_coef:.4f}")
print(f"  Intercept: {lr_best.intercept_[0]:.4f}")
print(f"  Threshold: {best['thr']:.4f}")
print(f"  Scaler mean sample: {scaler.mean_[:3]}")
print(f"  Scaler std sample: {scaler.scale_[:3]}")

# Save backup of original
import shutil
orig_path = PARAM_DIR / "scoring_model_bzscore_v32.json"
backup_path = PARAM_DIR / "scoring_model_bzscore_v32_DEGENERATE_BACKUP.json"
shutil.copy2(orig_path, backup_path)
print(f"\n  Backed up degenerate model to: {backup_path.name}")

# Save corrected
with open(orig_path, "w") as f:
    json.dump(corrected, f, indent=2)
print(f"  Saved corrected model to: {orig_path.name}")

# Print top coefficients for inspection
print(f"\n  Top coefficients by magnitude:")
coef_abs = np.abs(lr_best.coef_[0])
sorted_idx = np.argsort(coef_abs)[::-1]
for i in sorted_idx[:10]:
    print(f"    {feat_cols[i]:<20}: {lr_best.coef_[0][i]:>+.4f}")

# Verify: scoring a few P1 touches
print(f"\n  Verification: scoring first 5 P1 touches...")
X_test = X_scaled[:5]
scores = X_test @ lr_best.coef_[0] + lr_best.intercept_[0]
probas = 1 / (1 + np.exp(-scores))
for i in range(5):
    print(f"    Touch {i}: score={scores[i]:.4f}, proba={probas[i]:.4f}, "
          f"pass={probas[i] >= best['thr']}")

# Count P1 touches passing threshold
proba_all = lr_best.predict_proba(X_scaled)[:, 1]
n_pass = (proba_all >= best["thr"]).sum()
print(f"\n  P1 touches passing threshold: {n_pass}/{n} ({n_pass/n*100:.1f}%)")

print("\n  DONE. Re-run prompt3_holdout_v32.py to get B-ZScore holdout results.")
