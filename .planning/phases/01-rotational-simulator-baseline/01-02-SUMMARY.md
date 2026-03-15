---
phase: 01-rotational-simulator-baseline
plan: 02
subsystem: simulation
tags: [rotational, determinism, baseline, pytest, pandas]

# Dependency graph
requires:
  - phase: 01-01
    provides: RotationalSimulator class with run() -> SimulationResult contract

provides:
  - Determinism verification on real P1a 250-vol bar data (3 @pytest.mark.slow tests)
  - baseline_P1a.json: raw baseline metrics for all 3 bar types at StepDist=2.0
  - RTH filter scope bug fix in rotational_engine.py

affects:
  - 01-03 (parameter sweep uses same engine; correct per-source config now in place)
  - Phase C (hypothesis comparison against these baseline numbers)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - Per-source config injection in engine loop (bar_data_primary scoped to single key)
    - @pytest.mark.slow for tests requiring real CSV file I/O

key-files:
  created:
    - shared/archetypes/rotational/baseline_results/baseline_P1a.json
  modified:
    - shared/archetypes/rotational/test_rotational_simulator.py
    - shared/archetypes/rotational/rotational_engine.py

key-decisions:
  - "Engine now passes per-source config (bar_data_primary with one key) to each simulator instantiation so RTH filter only activates for the 10sec source"
  - "Determinism tests use check_exact=True for trade/cycle DataFrames — no floating-point tolerance allowed"
  - "retracement_depths (Python list column) verified separately via list equality, not assert_frame_equal"

requirements-completed: [ROT-SIM-05, ROT-SIM-06]

# Metrics
duration: 9min
completed: 2026-03-15
---

# Phase 1 Plan 02: Determinism Verification and C++ Defaults Baseline Summary

**Determinism verified on real P1a 250-vol data (66 539 bars, 2 runs bit-for-bit identical); C++ defaults baseline (StepDist=2.0, MaxLevels=4) captured for all 3 bar types at P1a, stored in baseline_P1a.json**

## Performance

- **Duration:** 9 min
- **Started:** 2026-03-15T21:32:02Z
- **Completed:** 2026-03-15T21:41:05Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments

- Added `TestDeterminismRealData` class with 3 `@pytest.mark.slow` tests using real 250-vol P1a bar data (66 539 bars): `bars_processed`, `trades` DataFrame, and `cycles` DataFrame are all bit-for-bit identical across two consecutive runs
- Fixed RTH filter scope bug in `rotational_engine.py`: engine previously passed full config (all 3 `bar_data_primary` keys) to each simulator, causing vol/tick bars to be incorrectly RTH-filtered (since `bar_data_10sec_rot` key was present in config). Fix: engine now scopes `bar_data_primary` to the single source being processed
- Ran C++ defaults baseline (StepDist=2.0, MaxLevels=4) on all 3 P1a bar types; results captured in `baseline_results/baseline_P1a.json`

## Baseline Results (StepDist=2.0, MaxLevels=4, P1a)

| Bar Type             | n_cycles | cycle_pf | win_rate | total_pnl_ticks | sharpe  | max_dd_ticks | bars_processed |
|----------------------|----------|----------|----------|-----------------|---------|--------------|----------------|
| bar_data_250vol_rot  | 21 604   | 0.5075   | 0.7274   | -391 975        | -0.0843 | 392 657      | 66 539         |
| bar_data_250tick_rot | 20 448   | 0.5071   | 0.7331   | -382 635        | -0.0720 | 384 082      | 61 085         |
| bar_data_10sec_rot   | 17 939   | 0.5032   | 0.7029   | -246 516        | -0.0869 | 246 722      | 70 200         |

**Interpretation:** All 3 bar types show negative PnL at the C++ defaults — expected, since StepDist=2.0 is not optimized for NQ. High win rate (~70-73%) with poor PF (~0.50) indicates the ADD martingale is absorbing large losses. These numbers serve as the reference floor for Phase C hypothesis comparison.

## Task Commits

1. **Task 1: Determinism test + RTH filter bug fix** - `cc3dd82` (feat)
2. **Task 2: Baseline run on all 3 bar types** - `2f32952` (feat)

## Files Created/Modified

- `shared/archetypes/rotational/test_rotational_simulator.py` — Added `TestDeterminismRealData` class (3 slow tests using real P1a data)
- `shared/archetypes/rotational/rotational_engine.py` — Fixed per-source config scoping in simulation loop
- `shared/archetypes/rotational/baseline_results/baseline_P1a.json` — C++ defaults baseline metrics for all 3 bar types at P1a

## Decisions Made

- Per-source config scoping in engine: narrowest fix that corrects the RTH filter bug without changing the simulator interface or requiring a `source_id` parameter
- Determinism uses `check_exact=True` (no float tolerance): two runs with same inputs must produce identical bits, not approximately equal results
- `retracement_depths` list column verified separately via `list()` equality since `assert_frame_equal` cannot directly compare list-type columns

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] RTH filter incorrectly applied to vol/tick bars**
- **Found during:** Task 1 (while running determinism test setup)
- **Issue:** `rotational_engine.py` passed the full config (all 3 `bar_data_primary` keys) to each simulator. The simulator's RTH filter logic checked `if any("10sec" in key for key in bar_data_primary)` — always True when running any source — so vol/tick bars had RTH session filter applied, silently dropping pre-market and post-market vol/tick bars
- **Fix:** Engine now creates a `source_config = dict(config)` with `bar_data_primary` scoped to `{source_id: path}` before passing to each simulator
- **Files modified:** `shared/archetypes/rotational/rotational_engine.py`
- **Commit:** `cc3dd82`

## Issues Encountered

None beyond the auto-fixed RTH filter bug.

## User Setup Required

None.

## Next Phase Readiness

- Baseline metrics established and committed; 01-03 can run parameter sweep (StepDist 1.0-6.0, step 0.5) on all 3 bar types
- The per-source config fix is now baked into the engine; 01-03 will benefit from it automatically
- All 46 determinism tests pass (43 synthetic + 3 real-data)

---
*Phase: 01-rotational-simulator-baseline*
*Completed: 2026-03-15*

## Self-Check: PASSED

- `shared/archetypes/rotational/baseline_results/baseline_P1a.json` — EXISTS
- `shared/archetypes/rotational/test_rotational_simulator.py` — EXISTS (modified)
- `shared/archetypes/rotational/rotational_engine.py` — EXISTS (modified)
- Commit `cc3dd82` — FOUND (feat(01-02): verify determinism on real P1a data; fix RTH filter scope bug)
- Commit `2f32952` — FOUND (feat(01-02): run C++ defaults baseline (StepDist=2.0) on P1a all 3 bar types)
