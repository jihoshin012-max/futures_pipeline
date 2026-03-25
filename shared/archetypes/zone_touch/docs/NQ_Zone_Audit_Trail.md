# NQ Zone Touch — Audit Trail & Session Journal

> **Date range:** 2026-03-20 through 2026-03-25
> **Status:** v3.2 replication gate PASSED (445/445). Model reproducibility fixed. Paper trade next.
> **Last updated:** 2026-03-25

---

## Pipeline Execution Log

### Prompt 0 — Baseline Establishment
- **First run:** Completed with incorrect R/P ratios (RxnBar columns were bar indices, not tick values)
- **Fix:** Recomputed horizon R/P from bar data OHLC. Added RotBarIndex < 0 filter (1 P2a touch removed). 16:55 ET flatten documented as deferred.
- **Rerun:** Completed. All 24 self-checks passed.
- **Key results:** Baseline PF 0.8984 (HIGH overfit risk, 0/120 cells > 1.0). NORMAL PF 1.3343 (edge exists). SBB PF 0.3684 (34% contamination). R/P @30/60/120/full: 0.960/1.007/1.038/1.155.

### Prompt 1a — Feature Screening
- **First run:** Completed. F08 Prior Reaction Speed had same bar-index bug — recomputed from bar data. F18 Channel Confluence dropped (all zeros, no channel data in export).
- **Fix:** F08 recomputed. Result: MODERATE (near-zero R/P spread, Cohen's d=0.32 — volatility proxy, not quality predictor).
- **Key results:** 4 STRONG (F10 R/P=0.977, F04=0.580, F05=0.470, F01=0.336). 3 SBB-MASKED (F21=0.432, F09=0.397, F02=0.396).
- **Innovation:** SBB-masked secondary screening — features invisible on full population but STRONG on NORMAL-only. Designed this session, threaded through all downstream prompts.

### Prompt 1b — Model Building
- **Run:** Completed. All self-checks passed.
- **Key results:** 4-feature elbow (F10, F04, F01, F21, all STRUCTURAL). A-Eq PF 2.69 (103 trades), A-Cal PF 2.08 (134), B-ZScore PF 1.50 (325). F21 Zone Age contributed largest dPF (+1.24).
- **F05 Session:** SKIPPED (negative dPF — collinear with existing features).

### Prompt 2 — Segmentation & Exit Calibration
- **Run:** Completed. 15 calibration runs (5 seg × 3 models). All self-checks passed.
- **Key results:** seg3×A-Cal ModeB (CT) PF=30.58 on 40 trades (P1). All top performers converged on Stop=190t, Target=60-120t, no BE/trail. SBB leak rate 1-5%.
- **B-only verdict:** Initially reported as NOT VIABLE (PF=0.93, 719 trades) in GSD chat summary. **CORRECTED** to VIABLE (PF=1.43, 414 trades) after checking the actual output file. GSD confused numbers across runs.
- **Exit type tracking:** Added to backtest engine mid-session (exit_type field: TARGET/STOP/BE/TRAIL/TIMECAP). P1 exit breakdown: 94% target, 2% stop, 0% BE/trail, 4% time cap.

### Prompt 3 — Holdout & Verdicts
- **Blocker:** holdout_locked_P2.flag existed. Removed by user after pre-holdout review.
- **Run:** Completed. All self-checks passed.
- **Key results:** 4 "Yes" verdicts (all A-Cal). Winner: seg3 ModeB (CT) PF@4t=5.00, 58 P2 trades, 91.4% WR, Profit/DD=16.51, MaxDD=193t.
- **A-Cal vs A-Eq reversal:** A-Eq was P1 champion but only got Conditional on P2. Calibrated weights generalized better than equal weights.
- **B-only 16th run:** Tested, verdict = No (PF@4t=1.07, below 1.5 threshold). Single-tier deployment confirmed.

### Prompt 4 — Cross-Reference & Gap Investigation
- **Run:** Completed. All self-checks passed.
- **Key results:** Counter-trend structural inversion confirmed (prior M3 CT+low score was dead, fresh CT+high score is winner). Feature reduction 14→4. No gaps found. All 11 prior lessons captured.

---

## Post-Pipeline Analysis Log

### Pre-Deployment Diagnostics (Items 1-5)
- **Item 1 (Per-trade features):** 312 trades across 4 Yes groups saved to p2_trade_details.csv
- **Item 2 (Loser profiles):** 7 losers: 5/7 within 2pts of threshold, 6/7 PRIOR_HELD, all 3 stops ETH
- **Item 3 (Threshold sensitivity):** SLOPE not cliff. -1pt: PF 2.76 (77 trades). -2pt: PF 1.92 (121 trades)
- **Item 4 (Time-of-day):** 53% afternoon, ETH PF 1.60 vs RTH 13.51
- **Item 5 (Loss sequences):** Max consecutive losses = 1. Max DD = one trade (193t). Zero compounding risk.

### Score-to-Move Correlation
- **Result:** Spearman rho = -0.05 (near zero). Score predicts direction only, not magnitude.
- **Implication:** Single target correct. No score-dependent exits needed. MFE flat across score bins (~85-89t).

### Expanded Exit Sweep
- **Phase 1 (3,100 combos):** 2-leg outperforms single-leg for both modes. CT: 40/80 (67/33). All: 60/80 (67/33) Stop=240t TC=160.
- **Phase 2 (800 combos):** Step-ups don't help. Losses are fast failures (MFE < 40t), not slow bleeds. 93% T2 fill rate means runner rarely needs protection.
- **Phase 3:** Skipped — 91-93% target fill rate means trail has nothing to improve.
- **CT 40t floor:** 95% of P2 trades reached 40t MFE. 100% on P1.

### RTH vs ETH Analysis
- **Finding:** All 3 P2 stop-outs are ETH. PF 1.76 (ETH) vs 13.51 (RTH). Identical scores (mean 18.27 ETH vs 17.94 RTH).
- **Score margin interaction:** Tested — ETH weakness is uniform across all margin bins. No surgical filter possible. Binary decision: full or RTH-only.
- **Resolution:** Paper trade both variants simultaneously. Don't filter pre-deployment.

### P2 Exit Breakdown (final gate before build)
- **Winner P2:** 87.9% target, 6.9% stop, 5.2% time cap. Stable vs P1 (89.5/2.6/7.9).
- **Time cap exits on P2:** Average PnL = +10.7t (profitable). Better than P1 time caps (-22.0t).
- **All 4 Yes groups:** 89-91% target rate across the board. Clean.

### VP Ray Investigation (2026-03-22)
- **MaxVPProfiles** was set to 50 (should be 0/500) — fixed
- **ZBV4 and ZRA proximity filters added** — stale values zeroed (>3x zone width from edge)
- **Root cause:** V4 subgraph 14 retains stale VP prices because SC purges VolumeAtPriceForBars data on historical bars
- V4 draws rays correctly from memory but subgraph is stale on recalc
- **P1:** 0% legitimate VP data. **P2:** 2.3%. Unusable for screening.
- **Resolution:** persist ImbalancePrice in ZoneData (queued item #11)
- **Pipeline v3.1 unaffected** — VP never used in scoring
- Full investigation: `acsil/VP_RAY_INVESTIGATION.md`

---

## Bugs Found & Fixed

| Bug | Where | Impact | Fix |
|-----|-------|--------|-----|
| RxnBar/PenBar columns are bar indices, not tick values | Prompt 0 R/P, Prompt 1a screening | All horizon R/P ratios were ~1.0 (meaningless) | Recomputed from bar data OHLC |
| F08 Prior Reaction Speed used bar indices | Prompt 1a | Feature screened on wrong values | Recomputed from bar data |
| RotBarIndex = -1 in P2a | Data prep | One touch simulated against wrong bar | Filter RotBarIndex < 0 in all prompts |
| F18 Channel Confluence all zeros | Prompt 1a | No channel data in bar export | Dropped (23 active features) |
| B-only GSD summary wrong | Prompt 2 chat | Reported PF=0.93 NOT VIABLE, actual file = PF=1.43 VIABLE | Corrected after file verification |
| Duplicate step number in Prompt 3 9a | Prompt 3 | Two items numbered "3." | Renumbered to 3,4,5,6,7 |
| Stale "6 scoring models" in Prompt 1b | Prompt 1b | Should be 3 | Fixed to 3 |
| F18 references in downstream prompts | Prompts 1b, 2, 3 | Referenced nonexistent threshold | Removed all F18 refs except definition |
| Broken markdown table in Prompt 3 | Prompt 3 inputs | Incomplete table row | Fixed |
| F10 spec said "Penetration / Zone Width" (ratio) | Build spec Part A | Would have caused wrong bin assignments | Corrected to raw PenetrationTicks. Bin edges [220, 590] confirmed as raw ticks. C++ build was already correct. |
| TrendSlope spec said "linear regression over 50 bars" | Build spec Part A | Wrong scale — pipeline uses ZBV4 pre-computed values | Corrected: C++ reads sig.TrendSlope from SignalRecord. |
| Trend classification spec said "direction-aware" | Build spec Part A | Would route demand CT wrong (pipeline is non-direction-aware) | Corrected: slope ≤ P33 → CT regardless of touch type. Confirmed on 79/79 trades. |
| VP subgraph 14 stale values | V4 + ZRA + ZBV4 | HasVPRay=1 always (stale), F19/F20 screened on garbage | VAP data purged on recalc. ZRA/ZBV4 proximity filter added. V4 persistence fix queued. |
| MaxVPProfiles set to 50 | V4 SC settings | Only 50/500 slots got VP profiles | Changed to 0 (=500). Not primary cause but compounded. |

---

## Design Decisions Made This Session

| Decision | Rationale | Where Documented |
|----------|-----------|-----------------|
| SBB-masked secondary screening | SBB noise (34%) drowns features that separate within NORMAL population | Prompt 1a Step 4.5b |
| P1a + P1b combined for calibration | Doubles calibration data. P2a/P2b as two independent holdouts. | Pipeline compaction summary |
| 6-prompt structure (added Prompt 0) | Baseline before features — honest measure of inherent edge | Pipeline compaction summary |
| Multi-horizon R/P for screening | Feature separating at 4/4 horizons is structural; 1/4 is fragile | Prompt 1a Step 4 |
| Combined-only verdict tier | Groups with < 20 per half but ≥ 20 combined get tested, capped at Conditional | Prompt 3 Step 13 |
| B-only as 16th run | VIABLE secondary mode needs holdout validation before deployment | Prompt 3 |
| 2-leg exits over single-leg | Lock majority at safe floor, let runner capture upside | Exit sweep Phase 1 |
| Skip Phase 3 trail | 91-93% target fill rate — trail has nothing to improve | Phase 2 conclusion |
| Don't filter ETH pre-deployment | 17 trades too small. Paper trade both variants. | RTH/ETH analysis |
| Score is gate not throttle | rho=-0.05. No score-dependent exits. | Score-to-move analysis |

---

## File Status

### ACTIVE — Current authoritative documents

| File | Purpose | Status |
|------|---------|--------|
| `NQ_Pipeline_Prompt_0_v31_BottomUp.md` | Baseline prompt (executed) | ✅ Complete — DO NOT MODIFY |
| `NQ_Pipeline_Prompt_1a_v31_BottomUp.md` | Feature screening prompt (executed) | ✅ Complete — DO NOT MODIFY |
| `NQ_Pipeline_Prompt_1b_v31_BottomUp.md` | Model building prompt (executed) | ✅ Complete — DO NOT MODIFY |
| `NQ_Pipeline_Prompt_2_v31_BottomUp.md` | Segmentation prompt (executed) | ✅ Complete — DO NOT MODIFY |
| `NQ_Pipeline_Prompt_3_v31_BottomUp.md` | Holdout prompt (executed) | ✅ Complete — DO NOT MODIFY |
| `NQ_Pipeline_Prompt_4_v31_BottomUp.md` | Cross-reference prompt (executed) | ✅ Complete — DO NOT MODIFY |
| `NQ_Zone_Autotrader_Build_Spec.md` | **AUTHORITATIVE** build document | ✅ Current — supersedes pipeline exit params |
| `NQ_Zone_Data_Capture_Spec.md` | 12-item data capture requirements | ✅ Items 1-5 executed. Items 6-12 build into autotrader. |
| `NQ_Zone_Expanded_Exit_Sweep_Spec.md` | Exit sweep specification (executed) | ✅ Complete — Phase 1-2 run, Phase 3 skipped |
| `NQ_Prior_Mode_Findings_Reference.md` | Historical reference from prior analysis | ✅ Reference only |
| `NQ_Study_Files_Checklist.md` | Sierra Chart study files status | ✅ Reference |
| `NQ_Zone_Audit_Trail.md` | This document — complete session journal | ✅ Current |

### SUPERSEDED — Old versions (kept for history, do not use)

| File | Superseded By | Reason |
|------|--------------|--------|
| `NQ_Clean_Data_Pipeline_Prompt.md` | v3.1 prompts (0-4) | Pre-split single-prompt version |
| `NQ_Clean_Data_Rebuild_Plan.md` | v3.1 prompts | Early planning doc |
| `NQ_Pipeline_Prompt_0_DataPrep.md` | Prompt 0 v3.1 | Separate data prep prompt (merged into Prompt 0) |
| `NQ_Pipeline_Prompt_1_Foundation.md` | Prompts 1a + 1b v3.1 | Pre-split single Prompt 1 |
| `NQ_Pipeline_Prompt_1_v31_BottomUp.md` | Prompts 1a + 1b v3.1 | v3.1 before 1a/1b split |
| `NQ_Pipeline_Prompt_2_Segmentation.md` | Prompt 2 v3.1 | Pre-v3.1 version |
| `NQ_Pipeline_Prompt_3_Holdout.md` | Prompt 3 v3.1 | Pre-v3.1 version |
| `NQ_Pipeline_Prompt_4_CrossReference.md` | Prompt 4 v3.1 | Pre-v3.1 version |

### GSD Output Files (on GSD's machine, not in this outputs folder)

| File | Source | Status |
|------|--------|--------|
| `baseline_report_clean.md` | Prompt 0 | ✅ Executed |
| `zone_lifecycle.csv` | Prompt 0 | ✅ Executed (3,131 zones) |
| `feature_screening_clean.md` | Prompt 1a | ✅ Executed |
| `feature_mechanism_validation.md` | Prompt 1a | ✅ Executed |
| `p1_features_computed.csv` | Prompt 1a | ✅ Executed (4,701 rows) |
| `feature_config_partial.json` | Prompt 1a | ✅ Executed |
| `incremental_build_clean.md` | Prompt 1b | ✅ Executed |
| `scoring_model_acal.json` | Prompt 1b | ✅ Executed |
| `scoring_model_aeq.json` | Prompt 1b | ✅ Executed |
| `scoring_model_bzscore.json` | Prompt 1b | ✅ Executed |
| `feature_config.json` | Prompt 1b | ✅ Executed |
| `p1_scored_touches_acal.csv` | Prompt 1b | ✅ Executed |
| `p1_scored_touches_aeq.csv` | Prompt 1b | ✅ Executed |
| `p1_scored_touches_bzscore.csv` | Prompt 1b | ✅ Executed |
| `segmentation_params_clean.json` | Prompt 2 | ✅ Executed |
| `p1_calibration_summary_clean.md` | Prompt 2 | ✅ Executed |
| `feature_analysis_clean.md` | Prompt 2 | ✅ Executed |
| `frozen_parameters_manifest_clean.json` | Prompt 2 | ✅ Executed |
| `verdict_report_clean.md` | Prompt 3 | ✅ Executed |
| `p2_holdout_clean.md` | Prompt 3 | ✅ Executed |
| `segmentation_comparison_clean.md` | Prompt 3 | ✅ Executed |
| `deployment_spec_clean.json` | Prompt 3 | ⚠️ SUPERSEDED for exits by Build Spec |
| `verdict_narrative.md` | Prompt 3 | ⚠️ Exit params superseded by Build Spec |
| `cross_reference_report_clean.md` | Prompt 4 | ✅ Executed |
| `gap_investigation_clean.md` | Prompt 4 | ✅ Executed |
| `combined_recommendation_clean.md` | Prompt 4 | ⚠️ Exit params superseded by Build Spec |
| `p2_trade_details.csv` | Item 1 | ✅ Extracted (312 trades) |
| `p2_trade_diagnostics.md` | Items 2, 4, 5 | ✅ Extracted |
| `threshold_sensitivity.md` / `near_miss_analysis.md` | Item 3 | ✅ Extracted |
| `consecutive_loss_analysis.md` | Item 5 | ✅ Extracted |
| `exit_sweep_phase1_results.md` | Exit sweep | ✅ Executed |
| `exit_sweep_phase1_configs.json` | Exit sweep | ✅ Executed |
| `exit_sweep_phase2_results.md` | Exit sweep Phase 2 | ✅ Executed (step-ups no improvement) |
| `losing_trade_profiles.md` | Item 2 | ✅ Extracted |
| `time_of_day_distribution.md` | Item 4 | ✅ Extracted |
| RTH vs ETH cross-tab | Score-margin × session analysis | ✅ Executed (ETH uniformly weak) |

---

## Transcripts

| File | Session Content |
|------|----------------|
| `2026-03-20-17-00-58-nq-zone-touch-clean-rebuild.txt` | Initial rebuild planning |
| `2026-03-20-19-20-26-nq-zone-touch-clean-rebuild.txt` | Continued planning |
| `2026-03-21-20-33-33-nq-zone-touch-pipeline-rebuild.txt` | Pipeline structure decisions |
| `2026-03-22-03-59-32-nq-zone-pipeline-rebuild-v31.txt` | Full v3.1 build, execution, exit sweep, diagnostics |

---

## Memory Items (13 total)

| # | Topic | Status |
|---|-------|--------|
| 1 | AI Agency Option A | Active — separate workstream |
| 2 | AI Agency Option B | Active — separate workstream |
| 3 | V1.4 rotation autotrader | Active — pending, priority is tight-rotation archetype |
| 4 | Lost-in-middle GSD prompt rule | Active — permanent |
| 5 | ZigZagRegime C++ study | Reference — built and verified |
| 6 | Autoresearch orchestration (rotation) | Queued — post rotation P2 validation |
| 7 | Zigzag-informed seed entry | Queued — post rotation validation |
| 8 | Rotation P1 date range | Reference — data availability note |
| 9 | Rotation fractal gap items | Active — some done, some queued |
| 10 | Frozen-anchor analysis | Active — queued for rotation Prompt 3 |
| 11 | Zone autoresearch candidates (10 items) | Queued — post paper trading |
| 12 | Zone break strategy | Queued — post bounce deployment |
| 13 | Zone touch strategy status | Active — pipeline complete, build next |

---

## Throughput Analysis — 2026-03-23

**Purpose:** Determine whether faster exits could increase total
profit by freeing position capacity for additional trades.

**Scope:** 12 sections across 2 prompts, 20+ configurations
tested on P1 (primary) with P2 cross-validation.

**Data:** P1 = 120 ZR trades / 130 fixed trades / 58-48 blocked.
P2 = 69 trades / 63 blocked.

**Key findings:**
1. Signal density too sparse for throughput gains (194-bar median
   gap, 12.4% clustering, 71% same-zone blocking)
2. Zone width is the only speed predictor — no secondary signal
3. Every stop/BE modification hurts PnL
4. Fixed exits lose throughput comparison (6,736 vs 8,803)
5. T2 runner adds 106t/trade on wide zones, only 20t on narrow
6. Hybrids (zone-width-based exit routing) all below baseline
7. Dynamic T2 exit: only config beating both periods (+0.4% P1,
   +1.4% P2) — deferred to v3.1, marginal improvement

**Decision:** Current ZR 2-leg confirmed optimal. No changes.
- T1 = 0.5 x zone_width_ticks (67%)
- T2 = 1.0 x zone_width_ticks (33%)
- Stop = max(1.5 x zone_width_ticks, 120t)
- TC = 160 bars

**Deferred:** Dynamic T2 exit queued for v3.1 post-paper-trading.
Stronger on P2 (+1.4%) — revisit if P3 zone distribution is
wider than P1.

**Files:** throughput_analysis_part1.md, throughput_analysis_part2.md,
throughput_prompt_1_v2.md, throughput_prompt_2_v2.md

### C++ Replication Gate — PASS
- **Date:** 2026-03-23
- **FIXED (v1.0):** 85/85 trades matched, 0 mismatched. CT 5t limit entry, WT market. CT 40/80/190, WT 60/80/240, TC=160.
- **ZONEREL (v3.0):** 77/77 trades matched, 0 mismatched. CT 5t limit entry, WT market. T1=0.5×ZW, T2=1.0×ZW, Stop=max(1.5×ZW,120), TC=160.
- **Test data:** P1 bar data + P1 merged touches (NQ_bardata_P1.csv, NQ_merged_P1a/b.csv)
- **Answer keys:** Generated by `generate_p1_answer_keys.py` using replication harness v3.0 scoring logic
- **Bugs fixed during gate:**
  - Answer key column mapping (24-col → 21-col Python format)
  - Data period mismatch (test loaded P2 data, answer keys from P1)
  - Answer key source (throughput pre-scored → replication harness runtime scoring)
  - FIXED missing CT limit entry (was market-only)
  - Python round() banker's rounding → int(x+0.5) half-up to match C++
  - TIMECAP leg_open not closed (END_OF_DATA overwrite)
  - TIMECAP off-by-one (bh > tc → bh >= tc)
- **Tags:** v1.0-pre-merge (FIXED), v3.0-pre-merge (ZONEREL)
- **Tags:** v1.0-pre-merge (FIXED), v3.0-pre-merge (ZONEREL)

### Throughput Re-examination — CONFIRMED
- **Date:** 2026-03-23
- **Trigger:** Throughput analysis used 120 ZR trades (pre-scored) vs 77 from replication harness — 36% population difference. 43 trades scored above threshold in pre-scored data but below threshold at runtime (F10 PriorPenetration divergence).
- **Method:** Re-ran 5 targeted checks on 77-trade population (signal density, T2 marginal, baseline stats, fixed comparison, dynamic T2). Sequential simulation with no-overlap and kill-switch.
- **Results:**
  - Signal density: median gap 756 bars (was 194), 0% clustering (was 12.4%) — sparser
  - Baseline: WR 92.2% (was ~84%), PF 11.96 (was ~7.25) — higher quality
  - Fixed vs ZR: ZR wins by 40.8% total PnL (6,541t vs 3,872t)
  - Dynamic T2: 0 early closes triggered (was 7) — no signal overlap on this population
- **Verdict:** All 6 original conclusions CONFIRMED. Dropped trades were disproportionately clustered and lower quality. No full re-run needed.
- **Files:** `throughput_reexamination.py`, `output/throughput_reexamination.md`

---

---

## v3.2 Pipeline Rebuild — 2026-03-24 through 2026-03-25

### Architecture Change: v3.1 → v3.2

v3.1 used a single A-Cal model with FIXED/ZONEREL exit variants.
v3.2 redesigned as dual-model waterfall: A-Eq (Mode 1, fixed exits with partials) + B-ZScore (Mode 2, zone-relative exits with ZW-conditional sizing). Feature set expanded from 4 to 7 features. All prompts re-executed on the same P1/P2 data.

### v3.2 Prompt Execution Log

| Prompt | Script | Date | Key Result |
|--------|--------|------|-----------|
| Prompt 0 — Baseline | `baseline_v32.py` | 03-24 07:42 | PF=1.34, 3278 touches |
| Prompt 1a/1b — Feature screening + model building | `feature_screening_v32.py`, `model_building_v32.py` | 03-24 08:12 | 7 winning features (F10,F01,F05,F09,F21,F13,F04). 3 scoring models (A-Cal, A-Eq, B-ZScore) |
| Prompt 2 — Segmentation + calibration | `prompt2_segmentation_v32.py` | 03-24 09:06 | Frozen manifest produced. A-Eq threshold=45.5, B-ZScore threshold=0.50 |
| Prompt 3 — Mode classification | `mode_classification_v32.py` | 03-24 09:20 | Dual-model waterfall: A-Eq M1 priority, B-ZScore M2 with RTH/seq/TF filters |
| Prompt 4 — P2 validation | supplemental prepend | 03-24 14:27 | P2 one-shot passed for both modes |

### v3.2 Post-Pipeline Investigations

| Investigation | Script | Date | Result |
|--------------|--------|------|--------|
| Ray Analysis A — Incremental elbow | `ray_elbow_test_v32.py` | 03-24 15:44 | REDUNDANT — no PF gain over 7-feature set |
| Ray Analysis B — Conditional overlay | `ray_conditional_analysis_v32.py` | 03-24 16:19 | NO VIABLE OVERLAY — no ray filter improves PF |
| Risk mitigation (includes position scaling) | `risk_mitigation_v32.py` | 03-24 17:41–19:59 | M1: 1+2 partial (1ct@60t + 2ct@120t, BE after T1, stop=190, TC=120). M2: stop=max(1.3xZW,100), target=1.0xZW, TC=80, ZW-conditional sizing (3/2/1 ct). Deeper entries REJECTED (68% fill rate at 10t depth). Zone-fixed geometry REJECTED (single-trade artifact). |
| Stress test + Monte Carlo | `stress_test_v32.py`, `stress_test_followup_v32.py` | 03-24 20:49–21:21 | 718 trades (P1=331*, P2=387). Combined PF: 5.33/4.52. MC 10k. Max DD: 1129t. Kelly half: M1=42.6%, M2=30.2%. WR compression survives -15%. |
| Simulation verification | `verify_simulation_v32.py`, `verify_simulation_v32_groundtruth.py` | 03-25 01:10–07:56 | 16 trades walked bar-by-bar. Zero discrepancies. All 20 parameters match spec. |

*P1=331 was based on old pre-scored CSV; corrected to 445 after B-ZScore fix (see below).

### Position Scaling Investigation — Resolved within Risk Mitigation

The `position_scaling_investigation_prompt.md` was queued as a standalone investigation (saved 03-24 09:47). Instead of running it separately, the risk mitigation investigation covered both topics:

- **Deeper entries:** REJECTED — median penetration 15-17t, fill rate 68% at 10t depth. Opportunity-adjusted PF shows selection bias from excluding unfilled trades.
- **Position scaling:** Implemented as **M2 ZW-conditional sizing** (3ct if ZW<150, 2ct if 150-250, 1ct if 250+). This is position scaling by zone structure rather than entry depth.
- **Verdict:** Position scaling prompt objectives fully addressed. No separate execution needed.

### v3.2 Replication Gate — PASS (2026-03-25)

- **C++ study:** `ATEAM_ZONE_TOUCH_V32.cpp` with CSV test mode
- **Result:** 445/445 trades matched on RotBarIndex, PF=4.93 both sides, 237/237 POSITION_OPEN skips matched
- **1 A-Eq divergence:** RBI=56480 (Python aeq=45.0/M2, C++ aeq=50.0/M1) — ATR-derived feature computation edge case
- **P2 unchanged:** 387 trades (M1=86, M2=301)

### v3.2 Bugs Found & Fixed

| # | Bug | Root Cause | Fix | Date |
|---|-----|-----------|-----|------|
| 1 | B-ZScore degenerate model | `model_building_v32.py` used rolling z-score + C=1.0/L2 | GSD refit with global StandardScaler + C=0.01/L1/liblinear (separate script). JSON saved with correct coefficients. | 03-24 08:34 |
| 2 | B-ZScore model code not updated | `model_building_v32.py` still had old degenerate settings | Updated code to C=0.01/L1/liblinear/global StandardScaler. Reproduces frozen JSON within float noise. | 03-25 10:39 |
| 3 | C++ missing sigmoid on B-ZScore | Returned raw linear score, not probability | Added `1/(1+exp(-z))` to both ComputeBZScore paths | 03-25 09:16 |
| 4 | C++ wrong B-ZScore threshold | V32Config had 0.5417 (Youden's J cutpoint) | Changed to 0.50 per frozen manifest and Python M2_THRESHOLD | 03-25 09:16 |
| 5 | Float32 precision at 0.5 boundary | Pre-scored values like 0.4999999999997 rounded to 0.5f | Changed PrescoredBZ to double; threshold comparison in double | 03-25 10:14 |
| 6 | P1 population 331 → 445 | Old pre-scored CSV (expanding-window) inconsistent with frozen JSON (global scaler) | Accepted 445 as correct. P2 unchanged (387). 16 ground-truth trades verified — no mode flips. | 03-25 10:43 |

### v3.2 Parameter Audit (2026-03-25)

Full cross-check across 8 sources (C++ V32Config, frozen manifest JSON, stress_test_v32.py, A-Eq JSON, B-ZScore JSON, risk mitigation report, stress test report, simulation verification report).

| Finding | Severity | Status |
|---------|----------|--------|
| F4: B-ZScore model reproducibility | HIGH | RESOLVED — model_building_v32.py updated |
| F7: Cost ticks P1=3 vs stress_test P2/live=4 | MEDIUM | Documented — conservative bias |
| F1: BE_after_T1 reporting ambiguity | MEDIUM | Documented — functionally correct |
| F8: IsRTH upper bound vs Close session | LOW | Unreachable due to 15:30 blackout |
| F2: A-Eq bin edge rounding (float32) | LOW | No practical impact |
| F3: B-ZScore threshold JSON vs runtime | INFO | Intentional override |

Full details: `output/v32_replication_gate_results.md`

---

## Next Steps (in order)

1. ~~v3.1 C++ autotrader~~ — DONE (FIXED v1.0 + ZONEREL v3.0)
2. ~~v3.1 replication gate~~ — DONE (85/85 FIXED, 77/77 ZONEREL)
3. ~~v3.2 pipeline rebuild~~ — DONE (Prompts 0-4, ray screening, risk mitigation, stress test)
4. ~~v3.2 C++ autotrader~~ — DONE (ATEAM_ZONE_TOUCH_V32.cpp)
5. ~~v3.2 replication gate~~ — DONE (445/445 PASS)
6. ~~v3.2 parameter audit~~ — DONE (F4 resolved, all findings documented)
7. **Re-run stress test** on 445-trade P1 population (deferred — will re-run after final model is locked)
8. **Paper trade P3** — both M1 and M2, weekly Friday reviews
9. **After P3:** ETH filter decision, autoresearch (10 items), zone break strategy
