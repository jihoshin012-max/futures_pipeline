# Requirements: Rotational Archetype Milestone

Source: xtra/Rotational_Archetype_Spec.md

## Phase 1: Simulator & Baseline

- **ROT-SIM-01** ✅: Build RotationalSimulator class implementing the state machine (FLAT/POSITIONED states, SEED/REVERSAL/ADD actions) per spec Section 1.2 — completed 01-01
- **ROT-SIM-02** ✅: Build FeatureComputer with compute_static_features() for baseline (reads ATR, SD bands from CSV columns) — completed 01-01
- **ROT-SIM-03** ✅: Build TradeLogger with cycle tracking — cycle record per spec Section 6.4 with all required fields — completed 01-01
- **ROT-SIM-04** ✅: Implement RTH session filter for 10-sec bars (9:30-16:00 ET) — completed 01-01
- **ROT-SIM-05** ✅: Verify determinism — identical config+data produces identical output — completed 01-02
- **ROT-SIM-06** ✅: Run C++ defaults baseline (StepDist=2.0, MaxLevels=4) on all 3 bar types P1a, produce raw baseline metrics — completed 01-02
- **ROT-SIM-07** ✅: Execute fixed-step parameter sweep (StepDist 1.0-6.0, step 0.5) on P1a all 3 bar types, establish per-bar-type optimized baseline — completed 01-03

## Phase 02.1: Sizing Sweep Baseline

- **ROT-SIZ-01**: Add MaxTotalPosition cap to RotationalSimulator._add() — refuse add entirely when position + proposed_qty exceeds cap; 0=unlimited (backward compatible)
- **ROT-SIZ-02**: Build run_sizing_sweep.py — joint 3-parameter sweep (StepDist x MaxLevels x MaxTotalPosition) with pre-run deduplication, extended metrics computation, TSV/JSON output
- **ROT-SIZ-03**: Compute extended profile metrics (worst_cycle_dd, max_level_exposure_pct, tail_ratio, calmar_ratio, sortino_ratio, winning_session_pct, max_dd_duration_bars) from cycles DataFrame
- **ROT-SIZ-04**: Identify 3 baseline profiles per bar type (MAX_PROFIT, SAFEST, MOST_CONSISTENT) and store as permanent pipeline infrastructure in profiles/ directory
- **ROT-SIZ-05**: Add --profile flag to rotational_engine.py to load profile configs and override martingale/step_dist parameters

## Phase 2: Research Execution (future)

- **ROT-RES-01**: Build rotational_feature_evaluator.py for Stage 02
- **ROT-RES-02**: Phase 1 research — 41 hypotheses x 3 bar types independent screening
- **ROT-RES-03**: Phase 1b cross-bar-type robustness classification
- **ROT-RES-04**: Build trend_defense.py
- **ROT-RES-05**: Phase 2 research — combine winners across dimensions
- **ROT-RES-06**: Phase 3 research — best combination + best TDS configuration
- **ROT-RES-07**: P1b replication gate on final candidates

## Phase 3: Assessment & Deployment (future)

- **ROT-ASS-01**: P2 one-shot run with frozen parameters
- **ROT-ASS-02**: Stage 05 verdict using rotational-specific thresholds
- **ROT-ASS-03**: Stage 06 deployment preparation (if PASS/CONDITIONAL)
