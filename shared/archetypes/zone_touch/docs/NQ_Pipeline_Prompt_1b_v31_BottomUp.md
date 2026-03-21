# NQ Zone Touch — Clean Data Pipeline: Prompt 1b (Model Building)

> **Version:** 3.1
> **Date:** 2026-03-20
> **Scope:** Incremental feature building, elbow detection, scoring model calibration — all on P1
> **Prerequisite:** Prompt 1a outputs (baseline, screening, features computed)
> **Next:** Prompt 2 (Segmentation & Exit Calibration)
> **Only proceed here after reviewing Prompt 1a results at the review gate. If baseline PF < 1.0 AND zero STRONG features, stop. Otherwise, user decides.**

---

## Three Rules (non-negotiable)

1. **P1 only for calibration.** All model building and scoring calibration from P1 data only (P1a + P1b combined).
2. **No iteration on holdout data.** P2a/P2b are tested exactly once in Prompt 3. No adjustments after seeing results.
3. **All features computable at trade entry time.** Entry = next bar open after touch bar closes.

⚠️ P2a, P2b are NOT loaded or referenced in this prompt.

---

## Instrument Constants (repeated for context)

- **Tick size:** 0.25 points
- **Tick value:** $5.00 per tick per contract
- **Cost model:** 3 ticks ($15.00) per round-turn per contract
- **Bar type:** 250-volume bars

---

## Inputs

### From Prompt 0 (baseline):

| File | Purpose |
|------|---------|
| `baseline_report_clean.md` | Baseline PF anchor (MEDIAN cell PF @3t with 95% CI) + SBB split + per-period + direction + session + TF + seq. Every model must beat the median. |

### From Prompt 1a (screening):

| File | Purpose |
|------|---------|
| `feature_screening_clean.md` | STRONG/MODERATE/WEAK classifications + rank order |
| `feature_mechanism_validation.md` | STRUCTURAL/LIKELY/STATISTICAL per feature |
| `p1_features_computed.csv` | P1 touches with all 19 features |
| `feature_config_partial.json` | Bin edges, Feature 18 threshold, P1 mean/std |

### From Data Prep:

| File | Purpose |
|------|---------|
| `NQ_bardata_P1.csv` | Rotational bar data for simulation |

⚠️ Read `baseline_report_clean.md` first. Print the baseline PF anchor. Every result below is compared against it.

⚠️ Read `feature_screening_clean.md`. Print the STRONG/MODERATE/WEAK lists and rank order. This determines the feature addition sequence in Step 6.

Print: baseline PF anchor (median cell), baseline R/P at 60-bar horizon, number of STRONG features, number of MODERATE features, elbow build order (STRONG first by R/P spread, then MODERATE, then WEAK).

⚠️ Note: Prompt 1a screened features using exit-independent R/P ratios. This prompt (1b) builds scoring models using simulated PF — the strategy-level metric. The transition from touch-level screening to strategy-level building is intentional. Features ranked by R/P spread are tested in PF order to confirm the R/P signal translates to tradeable edge.

---

## Simulation Specifications (same as Prompt 1a)

**Bar-by-bar simulation** using `NQ_bardata_P1.csv` as the price series.

**Entry:** Next bar open after touch bar closes.

**Intra-bar conflict:** Stop fills first (worst case).

**Cost model:** Report PF at 2t, 3t, 4t. Primary = PF at 3t.

**Direction:** DEMAND_EDGE → long. SUPPLY_EDGE → short.

**No overlapping trades.** Flatten at time cap or 16:55 ET.

⚠️ Same specs as Prompt 1a. Do not change them. P1a data only.

---

## Step 6: Incremental Model Building (P1 only)

**Purpose:** Build the scoring model feature-by-feature, starting from the strongest. Each addition must demonstrably improve PF over the previous step. This answers: "what's the minimum feature set, and does adding more help or just add noise?"

⚠️ Reminder: P1 only. All bin edges, weights, thresholds frozen from P1. Baseline PF anchor = [X].

### 6a: Start with the #1 ranked feature from Step 4

Use the single strongest feature (highest R/P spread at 60-bar horizon, STRONG classification). Apply its best/worst bin split as a binary filter: trade only touches in the best bin(s).

Simulate with the **median cell exit from Prompt 0** (the exit where the population edge is centered — screening used R/P ratios, but building uses simulation to confirm tradeable PF).

| Model | Features | PF @3t | Trades | Improvement vs Baseline |
|-------|----------|--------|--------|------------------------|
| Baseline (Step 2) | None | ? | ? | — |
| Model 1 | [feature #1] | ? | ? | +? |

### 6b: Add features one at a time, in Step 4 rank order

⚠️ Reminder: P1 only. Features ranked by Step 4 R/P spread at 60-bar horizon (STRONG first). Each model compared against baseline PF anchor from Step 2.

For each subsequent feature (ranked by Step 4 R/P spread):

1. Add it to the model (as a scoring component, not just a filter)
2. For Approach A (tercile bins): assign points based on bin, sum with existing features, apply threshold
3. Re-simulate
4. Record PF @3t, trade count, improvement over previous model

| Model | Features Added | Cumulative Features | PF @3t | Trades | dPF vs Previous | dPF vs Baseline |
|-------|---------------|--------------------|---------| -------|-----------------|-----------------|
| Baseline | — | 0 | ? | ? | — | — |
| Model 1 | [#1] | 1 | ? | ? | +? | +? |
| Model 2 | [#2] | 2 | ? | ? | +? | +? |
| Model 3 | [#3] | 3 | ? | ? | +? | +? |
| ... | ... | ... | ... | ... | ... | ... |
| Model 19 | [#19] | 19 | ? | ? | +? | +? |

⚠️ **At each step, calibrate the threshold** to maximize PF while retaining ≥ 50 trades. The threshold may change as features are added.

⚠️ **If adding a feature DECREASES PF (dPF < 0):** Skip it and try the next feature in rank order. A feature with strong independent R/P that hurts combined PF is likely collinear with a feature already in the model — it adds noise, not signal. Record it as "SKIPPED — negative dPF" in the build table. Do NOT include skipped features in the elbow model.

⚠️ Reminder: P1 only. Compare every model against baseline anchor.

### 6c: Identify the elbow

Find the point where adding more features stops helping:

- **Elbow point:** The model number where dPF vs Previous drops below 0.05 for two consecutive additions. Features beyond this point are noise.
- **Minimum viable model:** The model at the elbow point. Report its feature set.
- **Diminishing returns zone:** Features added after the elbow. Flag these as overfit risks.

Print:
- PF improvement curve (model number vs cumulative PF)
- Elbow point and minimum viable feature set
- Features in the diminishing returns zone
- Cross-reference with Step 5 classifications: do the minimum viable features align with STRUCTURAL classifications? If the elbow model relies on STATISTICAL ONLY features, flag as risk.

### 6d: Compare against full model and DECIDE

⚠️ Reminder: P1 only. The elbow model is the minimum viable feature set. The full model includes all 19 features. Both use P1-calibrated parameters.

| Metric | Baseline (0 features) | Elbow Model (N features) | Full Model (19 features) |
|--------|-----------------------|--------------------------|--------------------------|
| PF @3t | ? | ? | ? |
| PF @4t | ? | ? | ? |
| Trades | ? | ? | ? |
| Win rate | ? | ? | ? |

**Decision rule — select the winning feature set:**
- If Full Model PF ≈ Elbow Model PF (within 10%): **select elbow** — fewer features, lower overfit risk, same performance.
- If Full Model PF > Elbow Model PF by >10%: **select full** — the additional features carry signal, but note the higher overfit risk.

⚠️ **This decision is final.** The winning feature set is used for all 3 scoring approaches in Step 7. Prompt 2 receives 3 models (one per approach), not 6.

Print: "WINNING FEATURE SET: [elbow/full] with [N] features: [list]. Reason: [PF comparison]."

---

## Step 7: Scoring Model Calibration (P1 only)

Based on Step 6 results, calibrate the final scoring model(s).

⚠️ Reminder: all calibration on P1 only. Baseline PF anchor = [X].

**Run three approaches on the WINNING feature set (from Step 6d):**

### Approach A-Cal (calibrated weights)
- Assign points per feature proportional to Step 4 R/P spread at 60-bar horizon
- Sweep threshold from 30% to 70% of max score in 5% increments
- Select threshold maximizing PF @3t with ≥ 50 trades. Freeze.

### Approach A-Eq (equal weights)
- Same max points per feature (e.g., 10 pts each)
- Same threshold sweep. Freeze.

### Approach B-ZScore (z-score)
- Rolling window calibrated on P1 (test 100, 250, 500, 1000 bars)
- Logistic regression on P1: P(Reaction > Penetration)
- Threshold from ROC curve (Youden's J). Freeze.

⚠️ Reminder: P1 only. All parameters frozen after this step.

This produces **3 scoring models** (one per approach), all using the winning feature set.

Print per model: weight table, max score, frozen threshold.

⚠️ **Final Checkpoint:** All scoring parameters frozen. Print in a single summary block. Confirm: "These scoring models were calibrated entirely on P1 data."

---

## Step 8: Trend Context & Supplementary Computations (P1 only)

**Trend Context** (used by Prompt 2 segmentation):
- TrendSlope P33/P67 from P1
- WT/CT/NT labels for all P1 touches
- Freeze cutoffs.

**ATR Regime percentile** for all P1 touches (needed for Segmentation 4 in Prompt 2).

**Null rate report:** Features 8, 10, 19, 20 null rates and seq 1 percentage on P1.

**Zone width drift warning:** Compare Feature 2 bin edges vs Feature 9 bin edges. Report whether ZW/ATR absorbs the drift.

**Save P1 feature distributions** to `p1_feature_distributions.json` for downstream comparison.

⚠️ Reminder: all computations in Step 8 use P1 only. Baseline PF anchor = [X].

---

## Required Outputs (saved for Prompt 2)

| Output File | Contents |
|-------------|----------|
| `incremental_build_clean.md` | Feature addition curve, elbow point, winning feature set decision, full vs elbow comparison |
| `p1_scored_touches_acal.csv` | P1 touches scored with A-Cal model (winning feature set) |
| `p1_scored_touches_aeq.csv` | P1 touches scored with A-Eq model (winning feature set) |
| `p1_scored_touches_bzscore.csv` | P1 touches scored with B-ZScore model (winning feature set) |
| `scoring_model_acal.json` | A-Cal weights, bin edges, threshold |
| `scoring_model_aeq.json` | A-Eq threshold |
| `scoring_model_bzscore.json` | B-ZScore weights, threshold, window |
| `feature_config.json` | Bin edges, TrendSlope P33/P67, Feature 18 threshold, P1 mean/std |

⚠️ **Handoff contract to Prompt 2:** These files PLUS Prompt 0 (baseline) and Prompt 1a (screening, mechanism validation). Prompt 2 receives 3 scoring models (one per approach, all using the winning feature set), runs 5 segmentations = 15 runs.

---

## Context Reminders

⚠️ **Every 25–35 lines of code, reinforce:**
- P1 only — no other period data
- Compare against baseline PF anchor from Prompt 0
- Is the incremental build following Step 4 rank order?

⚠️ **After Step 6c (elbow):** Print the elbow model feature set and compare against mechanism classifications. Are the elbow features STRUCTURAL?

⚠️ **After Step 7 (calibration):** Print all 6 frozen scoring models. Confirm P1 only.

✅ **Prompt 1b self-check (run before saving outputs):**
- [ ] Only P1 data used throughout (P1a + P1b combined)
- [ ] P2a, P2b NOT loaded or referenced
- [ ] Incremental build started from strongest single feature (Step 4 rank order)
- [ ] Features with negative dPF skipped (not included in elbow model)
- [ ] Elbow point identified — minimum viable feature set documented
- [ ] Full model compared against elbow — winning feature set explicitly decided
- [ ] All 3 scoring models use the SAME winning feature set
- [ ] All 3 scoring models calibrated and frozen from P1
- [ ] Trend context (TrendSlope P33/P67) frozen from P1
- [ ] Feature 18 proximity threshold frozen from P1
- [ ] Baseline PF anchor printed and referenced throughout
- [ ] All output files saved
