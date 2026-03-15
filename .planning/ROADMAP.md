# Roadmap: Futures Pipeline

## Milestones

- ✅ **v1.0 Futures Pipeline** — Phases 1-7 (shipped 2026-03-14)

## Phases

<details>
<summary>✅ v1.0 Futures Pipeline (Phases 1-7) — SHIPPED 2026-03-14</summary>

- [x] Phase 1: Scaffold (6/6 plans) — completed 2026-03-14
- [x] Phase 01.1: Scoring Adapter Scaffold Generator (1/1 plan) — completed 2026-03-14
- [x] Phase 01.2: Bar Type Registry (1/1 plan) — completed 2026-03-14
- [x] Phase 2: HMM Regime Fitter (2/2 plans) — completed 2026-03-14
- [x] Phase 3: Git Infrastructure (2/2 plans) — completed 2026-03-14
- [x] Phase 4: Backtest Engine (4/4 plans) — completed 2026-03-14
- [x] Phase 5: Stage 04 Autoresearch (4/4 plans) — completed 2026-03-14
- [x] Phase 6: Stage 02 Autoresearch (3/3 plans) — completed 2026-03-14
- [x] Phase 7: Stage 03 Autoresearch (3/3 plans) — completed 2026-03-14

See: `.planning/milestones/v1.0-ROADMAP.md` for full phase details.

</details>

## Progress

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 1. Scaffold | 3/3 | Complete   | 2026-03-15 | 2026-03-14 |
| 01.1. Scoring Adapter | v1.0 | 1/1 | Complete | 2026-03-14 |
| 01.2. Bar Type Registry | v1.0 | 1/1 | Complete | 2026-03-14 |
| 2. HMM Regime Fitter | v1.0 | 2/2 | Complete | 2026-03-14 |
| 3. Git Infrastructure | v1.0 | 2/2 | Complete | 2026-03-14 |
| 4. Backtest Engine | v1.0 | 4/4 | Complete | 2026-03-14 |
| 5. Stage 04 Autoresearch | v1.0 | 4/4 | Complete | 2026-03-14 |
| 6. Stage 02 Autoresearch | v1.0 | 3/3 | Complete | 2026-03-14 |
| 7. Stage 03 Autoresearch | v1.0 | 3/3 | Complete | 2026-03-14 |
| 2. Feature Evaluator + Screening | Rotational | 0/3 | Planning complete | - |
| 3. TDS Build + Testing | Rotational | 0/0 | Not started | - |
| 4. Combination Testing + Replication | Rotational | 0/0 | Not started | - |
| 5. Assessment & Deployment | Rotational | 0/0 | Not started | - |

### Phase 1: Rotational Simulator & Baseline

**Goal:** Build rotational_simulator.py (continuous state machine), FeatureComputer, TradeLogger with cycle tracking, verify determinism, implement RTH session filter, run C++ defaults baseline on all 3 bar types, execute fixed-step parameter sweep (StepDist 1.0-6.0) to establish per-bar-type optimized baselines
**Requirements**: ROT-SIM-01, ROT-SIM-02, ROT-SIM-03, ROT-SIM-04, ROT-SIM-05, ROT-SIM-06, ROT-SIM-07
**Depends on:** Phase A (Infrastructure — complete)
**Plans:** 3/3 plans complete

Plans:
- [x] 01-01-PLAN.md — Build RotationalSimulator class with state machine, FeatureComputer, TradeLogger, RTH filter, date filtering, and unit tests
- [x] 01-02-PLAN.md — Verify determinism on real data and run C++ defaults baseline (StepDist=2.0) on P1a
- [x] 01-03-PLAN.md — Execute parameter sweep (StepDist 1.0-6.0) on P1a and identify per-bar-type optimized baselines

### Phase 2: Feature Evaluator + Phase 1 Screening

**Goal:** Build rotational_feature_evaluator.py (bar-level MWU, Gap G-04). Run 122 meaningful experiments (41 hypotheses x 3 bar types, H37 excluded from 10-sec). Run Phase 1b cross-bar-type robustness classification (Section 3.7 of spec): classify each hypothesis as Robust / Activity-dependent / Sampling-coupled / Time-dependent / No signal. Output: ranked advancement list with bar-type-specific notes. All runs on P1a only.
**Requirements**: ROT-RES-01, ROT-RES-02, ROT-RES-03
**Depends on:** Phase 1
**Plans:** 3 plans

Plans:
- [ ] 02-01-PLAN.md — Build hypothesis config registry, extend feature_engine with vectorized computation, extend FeatureComputer dispatch
- [ ] 02-02-PLAN.md — Build hypothesis screening runner and execute 122 experiments on P1a
- [ ] 02-03-PLAN.md — Phase 1b cross-bar-type robustness classification and ranked advancement list

> **Tooling checkpoint:** During planning, profile feature_compute vs simulator time per experiment. If feature compute >50% of wall clock, evaluate Kand (github.com/kand-ta/kand) before executing full sweep. See xtra/AI_Context_Architecture_Notes.md § Kand.

### Phase 3: TDS Build + Testing

**Goal:** Build trend_defense.py with 5 detectors and 3-level escalation (Section 4 of spec). Include hypothesis feed-ins (H33, H36, H38, H39, H40 into TDS detectors). Test TDS levels 1, 2, 3 independently against baseline on all 3 bar types. TDS velocity thresholds and cooldown periods may need bar-type-specific tuning (10-sec has ~5x more bars per unit time). Measure on survival metrics: worst-cycle DD, max-level exposure %, tail ratio, drawdown budget hit count.
**Requirements**: ROT-RES-04
**Depends on:** Phase 1
**Plans:** 0 plans

### Phase 4: Combination Testing + Replication

**Goal:** Combine Phase 2 winners (robust signals prioritized) across dimensions: Dimension A winner x H2 on/off x Dimension C winners x Dimension D winners x H18/H19. Run on all 3 bar types — combinations must show consistent improvement to advance. Integrate best combination with best TDS configuration from Phase 3. Run P1b replication gate on final candidates — soft gate (flag_and_review), WEAK_REPLICATION surfaces for human review, not a hard block. Cross-bar-type analysis repeated on combinations. All research on P1a only; P1b strictly for replication check.
**Requirements**: ROT-RES-05, ROT-RES-06, ROT-RES-07
**Depends on:** Phase 2, Phase 3
**Plans:** 0 plans
> **Tooling checkpoint:** Combination sweep multiplies experiment count significantly. If Phase 2 showed feature compute was a bottleneck, Kand adoption is blocking here. Also: if codebase has grown past ~15K LOC or cross-stage refactoring is needed, evaluate GitNexus indexing. See xtra/AI_Context_Architecture_Notes.md.

### Phase 5: Assessment & Deployment

**Goal:** P2 one-shot run with frozen parameters on all 3 bar types (Pipeline Rule 2 — NEVER re-run). Stage 05 verdict using rotational 5-tier logic: primary gates, survival gates, robustness gates (slippage sensitivity, breakeven removal, asymmetry ratio), multiple testing correction (G-10 Bonferroni), replication gate. Compute all 11 extended metric categories. Cross-bar-type consistency is a factor in verdict confidence. If PASS/CONDITIONAL -> Stage 06 deployment prep.
**Requirements**: ROT-ASS-01, ROT-ASS-02, ROT-ASS-03
**Depends on:** Phase 4
**Plans:** 0 plans
> **Tooling checkpoint:** If deploying to Stage 06/07 live, Kand's O(1) incremental update model becomes directly relevant for real-time bar processing. Evaluate before building Stage 07 live feed. Also review full tooling tally in xtra/AI_Context_Architecture_Notes.md — dashboard milestone triggers SocratiCode and mcp2cli evaluation.
