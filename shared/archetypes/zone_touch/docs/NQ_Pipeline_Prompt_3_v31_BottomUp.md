# NQ Zone Touch — Clean Data Pipeline: Prompt 3 of 4 (Holdout & Verdicts — Bottom-Up)

> **Version:** 3.1
> **Date:** 2026-03-20
> **Scope:** P2a and P2b holdout tests (separate then combined), statistical validation, final verdicts
> **Prerequisite:** Prompts 0, 1a, 1b, and 2 v3.1 outputs must exist
> **Next:** Prompt 4 (Cross-Reference & Gap Investigation)
> **This is where the answer comes from.**

---

## Three Rules (non-negotiable — same as Prompts 1 and 2)

1. **P1 only for calibration.** All calibration happened in Prompts 1-2. This prompt applies frozen parameters only.
2. **No iteration on P2.** Each run is tested on P2a and P2b exactly once. No adjustments after seeing results.
3. **All features computable at trade entry time.** Same definitions as Prompt 1a.

⚠️ **This prompt is purely evaluation.** No parameters are calibrated, adjusted, or modified.

---

## Instrument Constants (repeated for context)

- **Tick size:** 0.25 points
- **Tick value:** $5.00 per tick per contract
- **Cost model:** 3 ticks ($15.00) per round-turn per contract
- **Bar type:** 250-volume bars

---

## Inputs Required

### From Prompts 0 + 1a + 1b:

| File | Purpose |
|------|---------|
| `baseline_report_clean.md` | Raw baseline PF anchor (all periods) — the reference for all results |
| `scoring_model_acal.json` | A-Cal weights, bin edges, threshold |
| `scoring_model_aeq.json` | A-Eq thresholds |
| `scoring_model_bzscore.json` | B-ZScore weights, threshold, window |
| `feature_config.json` | Bin edges, TrendSlope P33/P67, P1 mean/std for all active features |
| `incremental_build_clean.md` | Elbow point, winning feature set decision, dPF per feature (for narrative report) |

⚠️ Reminder: all scoring/segmentation parameters were frozen from P1. This prompt applies them — no recalibration. Baseline PF anchor from Prompt 0 is the reference throughout.

### From Prompt 2 (bottom-up):

| File | Purpose |
|------|---------|
| `segmentation_params_clean.json` | Frozen parameter sets for all 15 runs (+ B-only exits if VIABLE) |
| `frozen_parameters_manifest_clean.json` | Complete parameter dump with P1 PF and Profit/DD |
| `feature_analysis_clean.md` | Ablation rankings, SBB analysis, B-only overlap verdict |

Print: baseline PF anchor, number of runs (15 + B-only 16th if VIABLE), P2a touch count, P2b touch count.

⚠️ **B-only 16th run:** If `feature_analysis_clean.md` shows B-only verdict = VIABLE, add a 16th run: the B-only population (touches that pass B-ZScore threshold but fail A-Eq threshold). Use B-ZScore's best segmentation and its frozen exits from Prompt 2. This run is tested on P2 with the same process as the other 15 — same stat tests, same verdict criteria. The B-only tier needs holdout validation before deployment.

### From Data Prep:

| File | Purpose |
|------|---------|
| `NQ_merged_P2a.csv` | P2a zone touches — **first holdout** |
| `NQ_merged_P2b.csv` | P2b zone touches — **second holdout** |
| `NQ_bardata_P2.csv` | P2 rotational bar data for simulation |
| `period_config.json` | Date boundaries |

⚠️ **This is the first and only time P2 data is used for evaluation.** P2 was used in Prompt 0 (baseline) where no parameters were fit. Now it's used to test frozen parameters.

---

## Simulation Specifications (same as Prompts 1 and 2)

**Bar-by-bar simulation** using `NQ_bardata_P2.csv` as the price series.

**Entry:** Next bar open after touch bar closes.

**Intra-bar conflict:** Stop fills first (worst case).

**Cost model:** Report PF at 2t, 3t, 4t. Primary = PF @3t.

**Position sizing:** 3-leg partial or single-leg per frozen group parameters. No overlapping trades.

**Time cap:** Flatten at time cap. **16:55 ET flatten:** If bar DateTime is available, also flatten when bar DateTime ≥ 16:55 ET. If not available, rely on time_cap only (same deferral as Prompt 0).

**Direction:** DEMAND_EDGE → long. SUPPLY_EDGE → short.

⚠️ These specs are identical to Prompts 1 and 2. Do not change them.

---

## Step 9: P2a Holdout Test (first out-of-sample)

### 9a: P2a Data Preparation

1. Load `NQ_merged_P2a.csv` and `NQ_bardata_P2.csv`
2. **Filter out touches with RotBarIndex < 0** (invalid bar mapping — same filter as Prompts 0/1a/2). Report how many removed.
3. Compute all features for P2a touches (same feature definitions as Prompt 1a). Raw feature values are computed identically regardless of scoring approach.
4. Score all P2a touches using each of the 3 frozen scoring models:
   - A-Cal / A-Eq: apply P1 bin edges from `feature_config.json`, assign points per bin, sum, compare to threshold
   - B-ZScore: standardize using P1 mean/std, apply P1-frozen regression weights, compare to threshold
5. Compute trend labels (WT/CT/NT) using P1-frozen TrendSlope P33/P67
6. For Seg 5: assign to nearest P1-frozen centroid, standardized by P1 mean/std
7. Label SBB touches

⚠️ Checkpoint: confirm NO P2a-derived parameters used. All encoding/standardization uses P1-frozen values.

⚠️ **Feature drift check:** Compare P2a feature distributions against P1 bin edges for ALL winning features (F10, F04, F01, F21) plus F02 and F09 (diagnostics). Report what % of P2a touches fall in each P1-calibrated bin per feature. Key drift risks:
- **F02 Zone Width / F09 ZW/ATR:** P1 median width ~170t, P2 may be ~280t — most P2 touches could land in one bin
- **F21 Zone Age:** If P2 period has proportionally more mature zones, age distribution shifts
- **F10 Prior Penetration:** Null rate for seq=1 touches — if P2 has different seq distribution, null handling matters
If >80% of P2a touches land in a single bin for any winning feature, that feature has lost discriminative power on P2 — flag for the narrative.

⚠️ Reminder: no parameters recalibrated. Frozen from P1. Baseline PF anchor = [X].

### 9b: Apply all runs to P2a (15 standard + B-only 16th if VIABLE)

For each run:
1. Route P2a touches to groups using frozen segmentation rules
2. Simulate each group using frozen exit parameters on P2 bar data

**For each group with ≥ 1 P2a trade, report:**

- N qualifying touches, N trades taken
- Win rate, loss rate, BE rate
- PF at 2t, 3t, 4t
- Total P&L at 3t, avg P&L per trade
- Max drawdown (ticks), Sharpe ratio
- **Profit/DD** — net PnL @3t / max drawdown (ticks). Risk-adjusted metric alongside PF.
- Exit reason breakdown (target/stop/BE/trail/time cap %)
- **SBB breakdown:** N SBB touches that entered trades, their PF separately
- Average trades per day
- **Improvement vs baseline:** group PF @3t vs raw baseline PF anchor

⚠️ Reminder: no overlapping trades. Same rule as Prompts 1-2 calibration. No parameter adjustments.

### 9c: P2a Statistical Validation (per group with ≥ 20 trades)

**Mann-Whitney U test:** Group's Reaction distribution vs complement (all P2a touches NOT in group). Report p-value.

**Permutation test:** 9,999 resamples. Randomly reassign group labels, re-simulate, compute PF. Report percentile rank and p-value.

**Random entry control:** 1,000 iterations. Randomly select same number of P2a edge touches (matching direction mix), simulate with same exit parameters. Report percentile rank.

---

⚠️ **Reminder: P2a results are final. Do NOT adjust parameters. Proceed to P2b.**

---

## Step 10: P2b Holdout Test (second independent confirmation)

### 10a: P2b Data Preparation

Same process as 9a but on `NQ_merged_P2b.csv`. All P1-frozen parameters applied.

⚠️ Checkpoint: NO P2b-derived parameters. NO adjustments based on P2a results. Same frozen parameters.

### 10b: Apply all runs to P2b

Same reporting as 9b. For each group:
- Full trade-level results
- SBB breakdown
- Improvement vs baseline

⚠️ Reminder: P2b is independent from P2a. Both use the same frozen parameters but different data. If a run worked on P2a but fails on P2b (or vice versa), that's important information about edge stability.

### 10c: P2b Statistical Validation

Same tests as 9c (MWU, permutation, random entry control) on P2b data.

---

## Step 11: Combined P2 Analysis

### 11a: P2a + P2b Combined Results

For each run, combine P2a and P2b results:

| Metric | P2a | P2b | Combined | Baseline |
|--------|-----|-----|----------|----------|
| Trades | ? | ? | ? | ? |
| PF @3t | ? | ? | ? | ? |
| PF @4t | ? | ? | ? | ? |
| Profit/DD | ? | ? | ? | — |
| Sharpe | ? | ? | ? | — |
| Max DD | ? | ? | ? | — |
| Win rate | ? | ? | ? | — |
| vs Baseline | +? | +? | +? | — |

⚠️ Reminder: baseline PF anchor was computed on ALL periods including P2. The combined P2 result can be compared directly.

### 11b: Consistency Check

⚠️ **Expected degradation:** P1 PFs of 9-14 reflect exit parameters calibrated on the SAME data they're tested on. P2 PFs will be substantially lower — this is normal. A P1 PF of 9.39 becoming P2 PF of 2.0 is healthy degradation (the edge is real but smaller than in-sample). P2 PF below 1.0 means the edge didn't survive. Do NOT treat large P1→P2 PF drops as errors — they're expected. The verdict criteria (PF > 1.5 @4t) is calibrated for realistic out-of-sample performance, not P1 replication.

For each run's best group:

| Run | P1 PF | P2a PF | P2b PF | Trend |
|-----|-------|--------|--------|-------|
| ? | ? | ? | ? | Stable / Degrading / Improving |

**Stable:** All 3 PFs within 30% of each other. Strong confidence.
**Degrading:** P2 PFs consistently lower than P1. Possible overfit or regime shift.
**Improving:** P2 PFs higher than P1. Unusual — investigate (possibly favorable regime in P2).
**N/A:** For "Conditional (combined only)" groups — per-half PFs are unreliable due to small samples. Report combined P2 PF vs P1 PF only.

### 11c: Combined P2 Statistical Validation (for small-sample groups only)

For groups where either P2a or P2b had < 20 trades BUT combined P2 has ≥ 20 trades:

Run the same 3 stat tests from Steps 9c/10c on the **combined P2 population**:
- MWU on combined P2 Reaction distribution vs complement
- Permutation test (9,999 resamples) on combined P2
- Random entry control (1,000 iterations) on combined P2

These results feed the "Conditional (combined only)" verdict in Step 13. Without them, the verdict has no stat test inputs.

⚠️ Groups that already have ≥ 20 trades in BOTH halves do NOT need combined stat tests — they have per-half results from Steps 9c/10c.

---

## Step 12: Cross-Run Comparison

⚠️ Reminder: all results below use P1-frozen parameters applied to P2. No recalibration. Compare every metric against baseline PF anchor.

### 12a: Within-Segmentation Comparison

For each segmentation, compare the 3 models (one per approach):

| Seg | A-Cal PF @3t | A-Eq PF @3t | B-ZScore PF @3t | Best |
|-----|-------------|-----------|----------------|------|
| 1 | ? | ? | ? | ? |
| 2 | ? | ? | ? | ? |
| 3 | ? | ? | ? | ? |
| 4 | ? | ? | ? | ? |
| 5 | ? | ? | ? | ? |

### 12b: Across-Segmentation Comparison (combined P2)

| Metric | Seg1 | Seg2 | Seg3 | Seg4 | Seg5 |
|--------|------|------|------|------|------|
| Total P2 trades | ? | ? | ? | ? | ? |
| Combined PF @3t | ? | ? | ? | ? | ? |
| Best group PF | ? | ? | ? | ? | ? |
| Best group Profit/DD | ? | ? | ? | ? | ? |
| Combined Sharpe | ? | ? | ? | ? | ? |
| Max DD | ? | ? | ? | ? | ? |
| # groups passing | ? | ? | ? | ? | ? |
| SBB leak rate | ? | ? | ? | ? | ? |
| vs Baseline | +? | +? | +? | +? | +? |

⚠️ Reminder: every result compared against baseline PF anchor. A segmentation that barely beats baseline may not justify its complexity.

### 12c: Single-Mode vs Multi-Mode

Compare the overall winner against Segmentation 1 Mode A (single high-conviction filter):

| Metric | Winner (multi-mode) | Seg1 Mode A (single-mode) | Baseline (no filter) |
|--------|--------------------|--------------------------|---------------------|
| P2 trades | ? | ? | ? |
| PF @3t | ? | ? | ? |
| Profit/DD | ? | ? | ? |
| Sharpe | ? | ? | ? |
| Max DD | ? | ? | ? |

Does multi-mode add value over single-mode? Does single-mode add value over baseline?

---

## Step 13: Verdicts

### 13a: Per-Group Verdicts

For each group under each run:

**Yes** = PF > 1.5 @4t cost AND MWU p < 0.05 AND permutation p < 0.05 AND random percentile > 95th AND consistent across P2a/P2b (neither sub-period PF < 1.0)

**Conditional** = PF > 1.5 @4t cost AND at least 1 of 2 stat tests passes. OR: one sub-period passes fully but the other is borderline.

**Conditional (combined only)** = Either P2a or P2b has < 20 trades individually, BUT combined P2 has ≥ 20 trades. Run verdict criteria on combined P2: if PF > 1.5 @4t AND at least 1 stat test passes → Conditional (combined only). **Cannot earn "Yes"** because P2a/P2b consistency cannot be verified. This is the ceiling for small-sample groups — a paper trading candidate, not a deployment candidate.

**No** = Failed PF gate (PF ≤ 1.5 @4t) OR both stat tests failed OR (for groups with ≥ 20 trades in each half) PF < 1.0 in either sub-period.

**Insufficient Sample** = < 20 combined P2 trades (P2a + P2b together). Cannot validate at any level.

⚠️ Reminder: PF gate is at 4t cost (not 3t). Both stat tests must pass for "Yes". P2a/P2b consistency is a new requirement — prevents a run that only works in one half.

### 13b: Full Verdict Matrix

| Seg | Model | Group | P2 Trades | PF@4t | MWU p | Perm p | Random %ile | P2a PF | P2b PF | Verdict |
|-----|-------|-------|-----------|-------|-------|--------|-------------|--------|--------|---------|
| 1 | A-Cal | A | ? | ? | ? | ? | ? | ? | ? | ? |
| ... | ... | ... | ... | ... | ... | ... | ... | ... | ... | ... |
| B-only | B-ZScore | — | ? | ? | ? | ? | ? | ? | ? | ? |

### 13c: Overall Winner Selection

1. Rank by number of "Yes" groups
2. Ties: prefer higher combined P2 PF @3t
3. Ties: prefer fewer groups (simpler)
4. Ties: prefer higher trade count

⚠️ If NO group achieves "Yes": report honestly. Identify "Conditional" and "Conditional (combined only)" results as P3 paper trading candidates. "Conditional (combined only)" groups need more data before deployment — they passed on combined P2 but couldn't verify period consistency. Compare against baseline — if even the best group barely beats baseline, the feature engineering adds no value.

### 13d: Recommended Deployment Configuration

For the overall winner, print complete frozen specification:

**Scoring Model:**
- Approach (A-Cal / A-Eq / B-ZScore)
- Feature set (elbow or full — which features, how many)
- Weight table or regression coefficients
- Threshold
- Bin edges or z-score window

**Segmentation:**
- Which segmentation won
- Group definitions
- How many groups deployed

**Per Deployed Group:**
- Exit structure (single-leg or 3-leg, all parameter values)
- Seq gate, TF filter, width filter

**Performance Summary:**
- Baseline PF anchor: [X]
- P1 PF / P2a PF / P2b PF / Combined P2 PF
- Sharpe, max DD, trades per day
- SBB behavior

**If B-only 16th run also passed verdict (Yes or Conditional):**

Print a two-tier deployment spec:
- **Tier 1 (high conviction):** The overall winner from the 15 standard runs — A-Eq/A-Cal with its exits
- **Tier 2 (B-only, lower conviction):** Touches that pass B-ZScore but fail A-Eq — with B-ZScore's frozen exits
- Combined portfolio: Tier 1 + Tier 2 trade count, combined PF, combined Profit/DD
- Note the SBB leak rate difference (Tier 1: ~1-5%, Tier 2: ~18%)

⚠️ Reminder: this spec is ready to implement in C++ autotrader. For live: use unmodified V4 + ZB4 aligned + new autotrader.

---

## Output Naming

- `verdict_report_clean.md` — full verdict matrix, winner spec, deployment notes
- `p2_holdout_clean.md` — all per-group P2a and P2b results, statistical tests
- `segmentation_comparison_clean.md` — Step 12 comparison tables
- `deployment_spec_clean.json` — machine-readable frozen parameters for autotrader build
- `verdict_narrative.md` — **standalone narrative report** (see below)

### Narrative Report: `verdict_narrative.md`

This is the primary human-readable deliverable. Someone who hasn't seen any raw data should understand the results after reading this document. Structure:

1. **Executive summary** (3-5 sentences): Did the zone touch strategy survive rigorous testing? What's the headline PF, trade count, and risk profile?
2. **Baseline context:** What was the raw edge before features? (Median PF, CI, SBB split, direction split, session split — summarized from Prompt 0)
3. **What features mattered:** Which features were STRONG/STRUCTURAL? How many elbow features? Did the minimum viable model outperform the full model? (Summarized from Prompts 1a/1b)
4. **Scoring and segmentation:** Which approach won (A-Cal/A-Eq/B-ZScore)? Which segmentation? How many groups are tradeable? (Summarized from Prompt 2)
5. **Holdout results:** P2a and P2b performance, consistency, statistical significance. Did it pass or fail? (Steps 9-11)
6. **Risk profile:** Max drawdown, Profit/DD, trades per day, SBB leak rate. Can you actually trade this? (Steps 9-12)
7. **Recommendation:** Deploy / Paper trade / Abandon — with explicit reasoning. If deploy: what's the configuration? If two-tier (B-only also passed): describe both tiers with their trade counts, PFs, and SBB profiles. If abandon: what does the baseline tell you about why?

⚠️ **The narrative report includes key tables inline** (verdict matrix, winner comparison, performance summary). The CSVs are supporting data for reproducibility. The narrative is what gets read.

Do NOT overwrite any Prompt 1-2 outputs.

---

## Context Reminders

⚠️ **Every 25–35 lines of code, reinforce:**
- Are we applying P1-frozen parameters only? (YES)
- Have we recalibrated based on P2a or P2b? (NO)
- Is every result compared against baseline PF anchor? (YES)
- Is the simulation using same specs as Prompts 1-2? (YES)

⚠️ **After Step 9 (P2a):** Print P2a results. Do NOT adjust before running P2b.

⚠️ **After Step 10 (P2b):** Print P2b results. Compare consistency with P2a.

⚠️ **Before verdicts (Step 13):** Re-read verdict criteria. PF > 1.5 @4t (not 3t). Both stat tests for "Yes". P2a/P2b consistency required for "Yes". Groups with < 20 trades on either half but ≥ 20 combined get "Conditional (combined only)" at best.

✅ **Prompt 3 self-check:**
- [ ] P2a features computed using P1-frozen parameters only
- [ ] P2b features computed using P1-frozen parameters only
- [ ] No parameter recalibrated after seeing P2a results
- [ ] No parameter recalibrated after seeing P2b results
- [ ] All 15 runs from Prompt 2 tested on P2
- [ ] B-only 16th run tested on P2 if Prompt 2 verdict was VIABLE
- [ ] Statistical tests computed for all groups with ≥ 20 trades
- [ ] SBB breakdown in every group report
- [ ] Profit/DD reported for every group alongside PF
- [ ] P2a and P2b tested separately THEN combined
- [ ] Verdict criteria applied correctly (PF@4t, not PF@3t)
- [ ] P2a/P2b consistency checked (neither sub-period PF < 1.0 for "Yes")
- [ ] Small-sample groups tested on combined P2 before being dropped — capped at "Conditional (combined only)"
- [ ] Every result compared against baseline PF anchor
- [ ] Feature drift check: P2 distributions vs P1 bin edges reported for all winning features + F02/F09
- [ ] Winner deployment spec complete and ready for C++ implementation
- [ ] `verdict_narrative.md` is standalone readable — covers all 7 sections
- [ ] All output files saved
