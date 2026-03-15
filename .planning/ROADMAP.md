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
| 1. Scaffold | 1/3 | In Progress|  | 2026-03-14 |
| 01.1. Scoring Adapter | v1.0 | 1/1 | Complete | 2026-03-14 |
| 01.2. Bar Type Registry | v1.0 | 1/1 | Complete | 2026-03-14 |
| 2. HMM Regime Fitter | v1.0 | 2/2 | Complete | 2026-03-14 |
| 3. Git Infrastructure | v1.0 | 2/2 | Complete | 2026-03-14 |
| 4. Backtest Engine | v1.0 | 4/4 | Complete | 2026-03-14 |
| 5. Stage 04 Autoresearch | v1.0 | 4/4 | Complete | 2026-03-14 |
| 6. Stage 02 Autoresearch | v1.0 | 3/3 | Complete | 2026-03-14 |
| 7. Stage 03 Autoresearch | v1.0 | 3/3 | Complete | 2026-03-14 |

### Phase 1: Rotational Simulator & Baseline

**Goal:** Build rotational_simulator.py (continuous state machine), FeatureComputer, TradeLogger with cycle tracking, verify determinism, implement RTH session filter, run C++ defaults baseline on all 3 bar types, execute fixed-step parameter sweep (StepDist 1.0-6.0) to establish per-bar-type optimized baselines
**Requirements**: ROT-SIM-01, ROT-SIM-02, ROT-SIM-03, ROT-SIM-04, ROT-SIM-05, ROT-SIM-06, ROT-SIM-07
**Depends on:** Phase A (Infrastructure — complete)
**Plans:** 1/3 plans executed

Plans:
- [ ] 01-01-PLAN.md — Build RotationalSimulator class with state machine, FeatureComputer, TradeLogger, RTH filter, date filtering, and unit tests
- [ ] 01-02-PLAN.md — Verify determinism on real data and run C++ defaults baseline (StepDist=2.0) on P1a
- [ ] 01-03-PLAN.md — Execute parameter sweep (StepDist 1.0-6.0) on P1a and identify per-bar-type optimized baselines
