# NQ Zone Touch — Clean Data Pipeline: Prompt 2 of 4 (Segmentation & Calibration — Bottom-Up)

> **Version:** 3.1
> **Date:** 2026-03-20
> **Scope:** Parallel segmentation, exit calibration, feature analysis — all on P1
> **Prerequisite:** Prompt 0 (baseline) + Prompt 1a (screening) + Prompt 1b (scoring models) outputs must exist
> **Next:** Prompt 3 (P2 Holdout & Verdicts) consumes the outputs from this prompt

---

## Three Rules (non-negotiable — same as Prompts 1a/1b)

1. **P1 only for calibration.** All segmentation rules, exit parameters, filter gates from P1 data only (P1a + P1b combined, 4,701 touches).
2. **No iteration on holdout data.** P2a/P2b are tested exactly once in Prompt 3.
3. **All features computable at trade entry time.** Entry = next bar open after touch bar closes.

⚠️ P2a and P2b must NOT be loaded, read, or referenced in any way during this prompt.

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
| `baseline_report_clean.md` | Raw edge baseline PF (computed on ALL periods — no parameters fit). The anchor everything must beat. |

### From Prompt 1a (screening):

| File | Purpose |
|------|---------|
| `feature_screening_clean.md` | Single-feature screening: STRONG/MODERATE/WEAK classifications |
| `feature_mechanism_validation.md` | Mechanism classification per feature |

### From Prompt 1b (model building):

| File | Purpose |
|------|---------|
| `incremental_build_clean.md` | Winning feature set decision (elbow vs full) |
| `p1_scored_touches_acal.csv` | P1 touches scored with A-Cal model |
| `p1_scored_touches_aeq.csv` | P1 touches scored with A-Eq model |
| `p1_scored_touches_bzscore.csv` | P1 touches scored with B-ZScore model |
| `scoring_model_acal.json` | A-Cal weights, bin edges, threshold |
| `scoring_model_aeq.json` | A-Eq threshold |
| `scoring_model_bzscore.json` | B-ZScore weights, threshold, window |
| `feature_config.json` | Bin edges, TrendSlope P33/P67, Feature 18 threshold, P1 mean/std |

⚠️ Reminder: Prompt 1b produced 3 models (one per approach, all using the winning feature set). This prompt runs 5 segmentations × 3 models = 15 independent calibration runs. P2a/P2b are NOT loaded.

### From Data Prep:

| File | Purpose |
|------|---------|
| `NQ_merged_P1a.csv` | P1a touches (part of calibration set) |
| `NQ_merged_P1b.csv` | P1b touches (part of calibration set) |
| `NQ_bardata_P1.csv` | Rotational bar data for P1 simulation |
| `period_config.json` | Date boundaries and touch counts |

⚠️ **Concatenate P1a + P1b** into one P1 dataset at load time. All calibration uses the full P1 set (4,701 touches).

⚠️ Read `baseline_report_clean.md` first. Print the raw baseline PF anchor (median cell). Every result in this prompt is compared against it.

Print: baseline PF anchor (median cell), winning feature set, scoring thresholds for all 3 models, P1 touch count (4,701).

---

## Simulation Specifications (used throughout this prompt)

**Bar-by-bar simulation** using `NQ_bardata_P1.csv` as the price series.

**Entry:** Next bar open after touch bar closes. Entry price = Open of the bar following the touch bar.

**Intra-bar conflict:** If both stop and target could fill on the same bar, assume stop fills first (worst case).

**Cost model:** Report PF at 2t, 3t, 4t. Primary metric = PF at 3t.

**Position sizing:**
- 3-leg partial mode: 1/3 at T1, 1/3 at T2, 1/3 at T3. Track fractional position.
- Single-leg mode: 1 contract, 1 target.
- No overlapping trades — if in position, skip new signals until flat.

**Time cap:** Flatten all remaining legs at time cap bar count. Also flatten at 16:55 ET.

**Direction:** DEMAND_EDGE → long. SUPPLY_EDGE → short.

⚠️ These specs are identical to Prompts 1a/1b. Do not change them.

---

## Step 5: Parallel Segmentation & Exit Calibration (P1 only)

Load the P1 scored touches for each of the 3 models. Run 5 segmentation hypotheses in parallel = **15 independent calibration runs**.

⚠️ **Each segmentation is independent.** They share the scoring model from Prompt 1b but have different grouping logic and independently calibrated exit parameters.

⚠️ **All calibration in this step uses P1 data only (4,701 touches).**

---

### Segmentation 1: Score Only

Two groups:
- **Mode A:** Score ≥ threshold AND edge touch
- **Mode B:** Everything else

### Segmentation 2: Score + Session

Four groups:
- **Mode A:** Score ≥ threshold AND edge touch
- **Mode B:** Score < threshold AND edge touch AND session = Morning (8:30–12:00)
- **Mode C:** Edge touch AND session = Afternoon (12:00–17:00) AND not already in Mode A
- **Mode D:** Everything else

### Segmentation 3: Score + Trend Context

Three groups:
- **Mode A:** Score ≥ threshold AND edge touch AND (with-trend or neutral)
- **Mode B:** Score ≥ threshold AND edge touch AND counter-trend
- **Mode C:** Everything else

⚠️ Use trend labels (WT/CT/NT) computed in Prompt 1b using P1-frozen TrendSlope P33/P67.

### Segmentation 4: Score + Regime

Three groups:
- **Mode A:** Score ≥ threshold AND edge touch AND Feature 17 (ATR Regime) ≤ P50
- **Mode B:** Score ≥ threshold AND edge touch AND Feature 17 > P50
- **Mode C:** Everything else

⚠️ ATR Regime P50 from P1. Freeze.

### Segmentation 5: Data-Driven Clustering

Run k-means on P1 feature vectors (winning feature set, standardized using P1 mean/std from `feature_config.json`) for k = 2, 3, 4, 5, 6. For each k:
- Assign touches to clusters
- Compute mean R/P ratio per cluster
- Drop clusters where mean R/P < 1.0
- Keep remaining as modes

Select k maximizing combined PF of retained clusters (simulated with default exits). Freeze k and centroids.

⚠️ For P2, assign touches to nearest P1-frozen centroid.

---

⚠️ **Reminder: we are on P1 only (4,701 touches). Every parameter calibrated below is frozen. Baseline PF anchor = [X].**

---

### Exit Calibration (for EACH segmentation, EACH group with ≥ 30 touches)

**Single-leg exit grid:**

| Parameter | Values |
|-----------|--------|
| Stop | 60t, 90t, 120t, 160t, 190t |
| Target | 40t, 60t, 80t, 120t, 160t, 200t, 240t |
| BE trigger (MFE) | none, 20t, 30t, 40t |
| Trail trigger (MFE) | none, 60t, 80t, 100t |
| Time cap | 30, 50, 80, 120 bars |

**3-leg partial exit grid (highest-conviction group per segmentation only):**

| Parameter | Values |
|-----------|--------|
| T1 | 50t, 80t |
| T2 | 120t, 160t |
| T3 | 200t, 240t, 300t |
| Stop | 60t, 90t, 120t, 160t, 190t |
| BE trigger | none, 20t, 30t, 40t |
| Trail trigger | none, 60t, 80t, 100t |
| Time cap | 30, 50, 80, 120 bars |

⚠️ Reminder: entry = next bar open after touch bar. Intra-bar conflict = stop fills first. Cost = 3t.

Select best exit per group based on P1 PF @3t with ≥ 20 trades. Freeze.

### Additional Filters (per segmentation on P1)

**Seq threshold:** Test ≤ 2, ≤ 3, ≤ 5, no limit. Select based on P1 PF. Freeze.

**TF filter:** Test TF ≤ 120m (exclude 240m+) vs no filter. Select based on P1 PF. Freeze.

**Width filter:** Test flat ≥ 80t vs TF-specific thresholds (per SourceLabel: min width where ZoneBroken rate ≤ 15% on P1). Freeze winner.

⚠️ Reminder: all calibration on P1 only (4,701 touches). P2a/P2b do not exist in this prompt.

### Print per segmentation (after calibration):

- Group/mode population sizes (with SBB breakdown)
- Frozen exit parameters per group
- Frozen seq, TF, width filters
- P1 PF per group at 2t, 3t, 4t
- P1 trade count per group
- **P1 max drawdown (ticks) per group** — running cumulative PnL low point
- **P1 Profit/DD per group** — net PnL @3t / max drawdown. Risk-adjusted ranking metric alongside PF.
- Exit reason breakdown (target/stop/BE/trail/time cap %)
- **Improvement vs baseline:** best group P1 PF vs raw baseline PF anchor from Prompt 0

⚠️ **Profit/DD captures what PF misses.** A group with PF 2.5 and 800t drawdown is worse than PF 2.0 with 200t drawdown. Report both.

---

📌 **Mid-pipeline checkpoint:** After completing all 5 segmentations for all 3 models, print:

| Seg | Model | # Groups | P1 Trades | Combined P1 PF @3t | Best Group PF | Best Group Profit/DD | Max DD (ticks) | vs Baseline |
|-----|-------|----------|----------|---------------------|---------------|---------------------|---------------|-------------|
| 1 | A-Cal | ? | ? | ? | ? | ? | ? | +? |
| 1 | A-Eq | ? | ? | ? | ? | ? | ? | +? |
| 1 | B-ZScore | ? | ? | ? | ? | ? | ? | +? |
| 2 | A-Cal | ? | ? | ? | ? | ? | ? | +? |
| ... | ... | ... | ... | ... | ... | ... | ... | ... |

⚠️ Reminder: 15 runs total (5 seg × 3 models). All on P1. Baseline PF anchor = [X].

Confirm: "All 15 calibration runs used P1 data only (4,701 touches). All parameters are frozen. Baseline PF anchor = [X]."

---

## Step 6: Feature Analysis (P1 only)

For the best-performing group in each segmentation (pick single best across models):

**Score ablation:** Remove each feature one at a time, re-score, re-assign, re-simulate. Report dPF per feature.

**Within-group predictive power:** Best-bin vs worst-bin mean Reaction per feature within the group.

**Correlation check:** Flag pairs with |r| > 0.7 where one contributes less.

**SBB analysis:** For each group, report SBB vs NORMAL touch PF separately. Does the scoring model naturally filter SBB touches (lower scores) or do they leak through?

⚠️ Reminder: P1 only. All parameters still frozen from Step 5. Feature analysis is observational — does NOT change any frozen parameters.

Print per segmentation:
- Ablation ranking
- Within-group power table
- Correlation flags
- SBB leak rate and SBB-specific PF

⚠️ Checkpoint: all parameters still frozen from Step 5. Feature analysis is observational only. Baseline PF anchor = [X].

---

📌 **Pre-P2 checkpoint (critical — handoff to Prompt 3):**

Reprint ALL frozen parameters for ALL 15 runs:

For each run, print:
- Scoring model reference (A-Cal / A-Eq / B-ZScore with threshold)
- Winning feature set (from Prompt 1b Step 6d)
- Segmentation rules (group definitions)
- Per-group: exit structure, seq gate, TF filter, width filter
- For Seg 5: cluster centroids, k value
- P1 PF and P1 Profit/DD

State: **"All parameters derived from P1 only (4,701 touches, P1a + P1b combined). P2a and P2b have not been loaded. Proceeding to save outputs."**

---

## Required Outputs (saved to files for Prompt 3)

| Output File | Contents |
|-------------|----------|
| `segmentation_params_clean.json` | All 15 frozen parameter sets (5 seg × 3 models) |
| `p1_calibration_summary_clean.md` | Mid-pipeline checkpoint table + per-group P1 results |
| `feature_analysis_clean.md` | Ablation rankings, within-group power, correlation flags, SBB analysis |
| `frozen_parameters_manifest_clean.json` | Complete parameter dump with P1 PF and P1 Profit/DD per run |

⚠️ **Handoff contract to Prompt 3:** These files plus Prompt 0, 1a, 1b and data prep outputs. Prompt 3 will:
1. Load P2a and P2b merged CSVs + P2 rotational bar data
2. Compute features using P1-frozen bin edges / z-score windows / cluster centroids
3. Apply all 15 frozen parameter sets to P2a and P2b separately
4. Report results and verdicts

Prompt 3 does NOT recalibrate anything.

---

## Context Reminders

⚠️ **Every 25–35 lines of code, reinforce:**
- Are we calibrating on P1 only? (YES — 4,701 touches, P1a + P1b combined)
- Is this simulation using the correct specs? (next bar open entry, worst-case intra-bar, 3t cost)
- Are we modifying any frozen parameters? (NO — after Step 5 calibration, everything is locked)
- Is every result compared against baseline PF anchor? (YES)

⚠️ **After each segmentation completes:** Print the frozen parameters for that segmentation before moving to the next.

✅ **Prompt 2 self-check (run before saving outputs):**
- [ ] P2a and P2b NOT loaded, read, or referenced
- [ ] P1a and P1b concatenated into P1 (4,701 touches) for all calibration
- [ ] Only 3 scoring models received (one per approach, winning feature set)
- [ ] All exit parameters from P1 simulation only
- [ ] All seq/TF/width gates from P1 only
- [ ] Cluster centroids from P1 only
- [ ] ATR Regime P50 from P1 only
- [ ] Each segmentation calibrated independently (no cross-contamination)
- [ ] Feature analysis did NOT modify any frozen parameters
- [ ] SBB breakdown included in feature analysis
- [ ] Profit/DD reported for every group alongside PF
- [ ] All 15 runs have frozen parameters saved
- [ ] Mid-pipeline checkpoint table printed with baseline comparison
- [ ] Pre-P2 checkpoint statement printed
- [ ] All output files saved
