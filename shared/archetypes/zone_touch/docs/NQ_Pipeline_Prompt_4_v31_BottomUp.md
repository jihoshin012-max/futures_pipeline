# NQ Zone Touch — Clean Data Pipeline: Prompt 4 of 4 (Cross-Reference & Gap Investigation — Bottom-Up)

> **Version:** 3.1
> **Date:** 2026-03-20
> **Scope:** Compare fresh pipeline results against prior findings, investigate gaps, targeted follow-ups
> **Prerequisite:** Prompts 0, 1a, 1b, 2, 3 v3.1 complete. Prior findings reference doc loaded.
> **This prompt runs AFTER reviewing Prompt 3 verdicts.**

---

## Purpose

The fresh pipeline (Prompts 1-3) ran from scratch with a bottom-up methodology: baseline first, single-feature screening, incremental model building. This prompt checks whether anything valuable from the prior work was missed and whether the bottom-up approach surfaced new insights the top-down couldn't.

This is NOT re-running the old analysis. It's a targeted investigation of specific gaps.

---

## Rules

1. **Prompt 3 results are final.** Do not modify verdicts. This prompt produces supplementary findings only.
2. **Any new calibration uses P1 only.** Same holdout discipline as Prompts 1-3.
3. **Reference doc is informational, not authoritative.** Prior findings were based on incomplete data.

⚠️ Reminder: this prompt is supplementary. Prompt 3 verdicts are final. Every result here is compared against the baseline PF anchor from Prompt 0.

---

## Inputs Required

### From Prompts 0-3:

| File | Purpose |
|------|---------|
| `baseline_report_clean.md` | Raw baseline PF anchor (all periods) |
| `feature_screening_clean.md` | Single-feature STRONG/MODERATE/WEAK classifications |
| `incremental_build_clean.md` | Elbow model feature set |
| `verdict_report_clean.md` | Fresh pipeline verdicts and winner |
| `segmentation_comparison_clean.md` | All 15 runs compared |
| `feature_analysis_clean.md` | Ablation rankings |
| `feature_mechanism_validation.md` | Mechanism classifications |
| `frozen_parameters_clean.json` | Winning configuration |
| `scoring_model_acal.json` | Fresh A-Cal weights for comparison |
| `p1_scored_touches_acal.csv` | Scored P1 touches (for targeted follow-ups) |
| `NQ_bardata_P1.csv` | P1 bar data (for targeted simulations) |

⚠️ Reminder: baseline PF anchor was computed on ALL periods (no parameters fit). Everything else used P1 only.

### Reference Document:

| File | Purpose |
|------|---------|
| `NQ_Prior_Mode_Findings_Reference.md` | Prior M1/M3/M4/M5 findings, weights, ablation, SBB analysis |

---

## Step 14: Baseline Comparison

**This is new to the bottom-up approach.** The prior analysis had no explicit baseline — it went straight to feature scoring.

### 14a: Raw Edge Assessment

From `baseline_report_clean.md`, summarize:

| Metric | Value |
|--------|-------|
| Baseline PF (best grid cell @3t, all periods) | ? |
| Baseline PF range (min–max across grid) | ? |
| % of grid cells with PF > 1.0 | ? |
| Baseline verdict | LOW / MODERATE / HIGH overfit risk |
| Per-period stability | P1a=? P1b=? P2a=? P2b=? |
| Direction split | Demand=? Supply=? |

⚠️ Reminder: this baseline used ALL periods because no parameters were fit. It's the most honest measure of whether zone touches have an inherent edge.

### 14b: What the Baseline Tells Us About the Prior Analysis

The prior M1_A achieved PF 4.67 on 66 trades (v2 SBB-filtered). How much of that came from:
- The inherent zone edge (baseline)?
- Feature selection (scoring model)?
- Exit optimization?
- Sample size luck (66 trades)?

If baseline PF is 1.2 and M1_A was 4.67, features + exits contributed ~3.5 PF points. If baseline is 0.9, the feature selection created the entire edge — higher overfit risk than previously understood.

---

## Step 15: Structural Comparison

### 15a: Did the Fresh Pipeline Rediscover M1/M3/M4/M5?

| Prior Mode | Prior Population Rule | Fresh Equivalent? | Fresh Group | Match Quality |
|-----------|----------------------|-------------------|------------|---------------|
| M1 (Zone Bounce) | Score ≥ threshold + edge + seq ≤ 3 + TF ≤ 120m | ? | ? | Exact / Similar / None |
| M3 (Tight-Risk) | Score < threshold + CT/NT + edge + Morning | ? | ? | Exact / Similar / None |
| M4 (Scalp) | Afternoon session | ? | ? | Exact / Similar / None |
| M5 (Structural) | Catch-all | ? | ? | Exact / Similar / None |

### 15b: Bottom-Up vs Top-Down Feature Selection

⚠️ Reminder: the bottom-up approach screened each feature independently (Prompt 1a Step 4), then built incrementally. The prior top-down calibrated all 14 simultaneously. Differences between the two reveal which features were genuinely structural vs which benefited from combination effects.

| Feature | Prior M1_A Weight (top-down) | Fresh Screening Class (bottom-up) | Fresh Elbow Included? | Agrees? |
|---------|----------------------------|----------------------------------|----------------------|---------|
| cascade | 20 (1st) | ? | ? | ? |
| zone_width | 13 (2nd) | ? | ? | ? |
| ~~vp_ray~~ | ~~10 (3rd)~~ | **DROPPED** | N/A | N/A |
| timeframe | 9 (4th) | ? | ? | ? |
| prior_penetration | 7 (5th) | ? | ? | ? |
| zw_atr_ratio | 6 (6th) | ? | ? | ? |
| session | 6 (7th) | ? | ? | ? |
| touch_bar_duration | 4 (8th) | ? | ? | ? |
| approach_decel | 2 (9th) | ? | ? | ? |
| approach_velocity | 1 (10th) | ? | ? | ? |
| delta_divergence | 1 (11th) | ? | ? | ? |
| close_position | 1 (12th) | ? | ? | ? |
| avg_order_size | 1 (13th) | ? | ? | ? |
| prior_rxn_speed | 1 (14th) | ? | ? | ? |
| *zz_swing_regime* | N/A (new) | ? | ? | — |
| *zz_oscillator* | N/A (new) | ? | ? | — |
| *atr_regime* | N/A (new) | ? | ? | — |
| *channel_confluence* | N/A (new) | ? | ? | — |
| *vp_ray_consumption* | N/A (new) | ? | ? | — |
| *distance_to_consumed_vp_ray* | N/A (new) | ? | ? | — |

⚠️ Reminder: the prior top-down analysis calibrated all 14 features simultaneously. The bottom-up screened each independently first. If a feature was important in the prior analysis but classified WEAK in bottom-up screening, it was likely benefiting from combination effects — not independently structural.

Key questions:
- Did cascade stay the strongest independent signal?
- Did any prior low-weight features become STRONG in independent screening?
- Did any of the 6 new features (15-20) rank STRONG?
- How many elbow features overlap with the prior top-6?

### 15c: Mechanism Cross-Check

Load `feature_mechanism_validation.md`. Cross-reference:

| Feature | Screening Class | Mechanism Class | In Elbow? | Deployment Confidence |
|---------|----------------|----------------|-----------|----------------------|
| cascade | ? | ? | ? | ? |
| zone_width | ? | ? | ? | ? |
| ... | ... | ... | ... | ... |

⚠️ Reminder: STRONG signal + STRUCTURAL mechanism = highest confidence. WEAK signal + STATISTICAL ONLY = lowest confidence. Flag any elbow feature that is STATISTICAL ONLY.

**Flag combinations:**
- **STRONG + STRUCTURAL in elbow:** Trustworthy. High deployment confidence.
- **STRONG + STATISTICAL ONLY in elbow:** The feature works independently but may not generalize. Monitor in paper trading.
- **WEAK + STRUCTURAL not in elbow:** Mechanistically grounded but didn't show independent separation. May be valuable in combination — test in Step 17.
- **New features (15-20) STRONG + STRUCTURAL:** The zigzag/regime/VP Ray features add real value.
- **New features (15-20) WEAK across the board:** They don't help. The original 14 (minus VP Ray) were sufficient.

---

## Step 16: Performance Comparison

### 16a: Best Mode Comparison

⚠️ Reminder: prior M1_A was on incomplete data (SBB excluded, 66 trades). Fresh results use complete data with bottom-up feature selection. Baseline column shows the no-feature reference.

| Metric | Prior M1_A (v2 SBB-filtered) | Fresh Winner | Baseline (no features) |
|--------|------------------------------|-------------|----------------------|
| PF @3t | 4.67 | ? | ? |
| PF @4t | ? | ? | ? |
| P2 Trades | 66 | ? | ? |
| Win Rate | 60.6% | ? | ? |
| Profit/DD | ? | ? | — |
| Max DD (ticks) | ? | ? | — |
| MWU p | 0.054 | ? | — |
| Perm p | 0.031 | ? | — |
| Random %ile | 99.5th | ? | — |
| Verdict | Conditional | ? | — |
| Feature count | 14 | ? (elbow) | 0 |
| vs Baseline | ? | +? | — |

### 16b: What Changed and Why

For each significant difference (PF delta > 0.5 or verdict changed):
- Is the change due to SBB zones in training data?
- Is the change due to new features (15-20)?
- Is the change due to bottom-up methodology (fewer, stronger features)?
- Is the change due to the larger baseline sample (9,361 vs ~2,000)?

⚠️ Reminder: prior results were on incomplete data (SBB excluded). Clean data results are the honest numbers.

---

## Step 17: Gap Investigation

### 17a: Identify Gaps

Review the prior reference doc's "Key Lessons" section:

| Prior Lesson | Captured by Fresh Pipeline? | If No, Why? |
|-------------|---------------------------|-------------|
| 1. Cascade dominant | ? | |
| 2. SBB zones identifiable by width+TF | ? | |
| 3. Equal weights can't handle SBB | ? | |
| 4. 66 trades is thin | ? | |
| 5. M3 is likely noise | ? | |
| 6. M4 afternoon scalp borderline | ? | |
| 7. M5 catch-all no edge | ? | |
| 8. HTF best R/P but worst SBB | ? | |
| 9. Seq ≤ 3 sweet spot | ? | |
| 10. 14 features mechanistically grounded | ? | |
| 11. Feature 3 dropped, replaced by 19/20 | ? | |

### 17b: Targeted Follow-Up Tests

For each gap where a prior finding looks promising but wasn't captured:

⚠️ Reminder: targeted tests use P1-calibrate / P2-one-shot protocol. No iteration on P2. Compare against baseline PF anchor.

**Candidate tests (run only those where gap is real):**

| # | Test | Prior Result | Why Fresh May Have Missed |
|---|------|-------------|--------------------------|
| A | M4 afternoon scalp: afternoon + edge + 30t target / 10-bar cap | PF 1.49-1.54 | Seg 2 Mode C may differ with SBB included |
| B | HTF-only (240m+) with strict width ≥ 500t + score ≥ threshold | R/P 3.22-3.97 | TF filter may have excluded HTF in fresh pipeline |
| C | Counter-trend morning: CT + morning + edge + below threshold | PF 1.06 (dead) | Confirm still dead on clean data |
| D | Direct M1_A replication with TF-specific width gates | PF 4.67 | Does the old config work on clean data? |
| E | WEAK+STRUCTURAL features forced into elbow model | — | Do mechanistically grounded features add value when combined with STRONG features? |

⚠️ Each test follows P1-calibrate / P2-one-shot. No iteration on P2.

---

## Step 18: Synthesis

### 18a: Final Assessment (9 questions)

1. **Did the clean data pipeline find an edge?** (Yes/No, cite Prompt 3 verdicts)
2. **Is the edge stronger or weaker than prior findings?** (Compare PF, Profit/DD, trade count, max drawdown)
3. **Did the prior mode structure (M1-M5) survive clean data?** (Full/Partial/No, cite Step 15a)
4. **Did the new features (15-20) add value?** (Yes/No, cite screening and elbow)
5. **Were there gaps — prior findings the fresh pipeline missed?** (Yes/No, cite Step 17)
6. **Did targeted follow-ups recover any missed edge?** (Yes/No, cite Step 17b)
7. **What is the recommended deployment configuration?** (Prompt 3 winner, modified by any Step 17b)
8. **Is the winning model mechanistically sound?** (Cite Step 15c — % of score weight from STRUCTURAL features)
9. **What does the baseline tell us about overfit risk?** (If winner PF is 3× baseline, moderate risk. If winner PF is 10× baseline, high risk — much of the edge comes from optimization.)

⚠️ Reminder: question 9 is new to the bottom-up approach. The baseline gives an objective measure of how much value the features add vs how much they might be fitting noise.

### 18b: Combined Recommendation

If Prompt 3 found a winner AND Step 17b found additional viable groups:
- Can they combine into a multi-mode portfolio?
- Does the combination improve Sharpe or reduce drawdown vs single-mode?
- Define combined routing waterfall.

If Prompt 3 found nothing AND Step 17b found nothing:
- The zone touch edge does not survive complete data with rigorous methodology.
- State clearly.
- Reference baseline: if baseline shows PF > 1.0, the edge exists but features can't reliably select for it. If baseline shows PF < 1.0, there is no edge.

### 18c: Deployment Readiness Summary

⚠️ Reminder: deployment spec uses Prompt 3 winner (frozen P1 parameters). Any modifications from Step 17b targeted tests also use P1-calibrate / P2-one-shot. Baseline PF anchor provides the overfit risk reference.

| Component | Status | Next Step |
|-----------|--------|-----------|
| Scoring model | Frozen from Prompt 3 (or modified by 17b) | Implement in C++ |
| Mode/group definitions | Frozen | Implement routing logic |
| Exit parameters | Frozen per group | Implement per-mode exits |
| Study files for live | V4 v1 (unmodified) + ZB4 aligned + new autotrader | Compile and deploy |
| Paper trading | P3: Mar–Jun 2026 | Collect live signals, compare to P2 PF |
| Live deployment | After P3 validation | Staged scale-up |

---

## Output Naming

- `cross_reference_report_clean.md` — Steps 14-18 full report
- `gap_investigation_clean.md` — Step 17b targeted test results
- `combined_recommendation_clean.md` — Step 18 synthesis and final deployment spec

Do NOT overwrite any Prompt 1-3 outputs.

---

## Context Reminders

⚠️ **Every 25–35 lines of code, reinforce:**
- Prompt 3 verdicts are final — this prompt adds information, not overrides
- Any targeted tests use P1-calibrate / P2-one-shot
- Every result compared against baseline PF anchor
- The reference doc is from incomplete data — prior numbers aren't directly comparable

⚠️ **Before targeted tests (Step 17b):** Restate: "These are supplementary. They do not replace Prompt 3 verdicts."

⚠️ **Before synthesis (Step 18):** Re-read all 9 questions. Ensure baseline comparison (question 9) is answered — this is the unique contribution of the bottom-up methodology.

✅ **Prompt 4 self-check:**
- [ ] Prompt 3 verdicts not modified
- [ ] Baseline comparison (Step 14) completed — overfit risk assessed
- [ ] Structural comparison (Step 15a, 15b) completed
- [ ] Mechanism cross-check (Step 15c) completed — deployment confidence per feature
- [ ] Performance comparison (Step 16) completed with baseline reference and Profit/DD
- [ ] Gaps identified (Step 17a) — all 11 prior lessons assessed
- [ ] Targeted follow-ups (Step 17b) used P1-calibrate / P2-one-shot protocol
- [ ] Synthesis (Step 18) answers all 9 questions including baseline overfit assessment
- [ ] Combined recommendation produced
- [ ] `combined_recommendation_clean.md` is standalone readable (supplements Prompt 3's `verdict_narrative.md`)
- [ ] Output files saved
