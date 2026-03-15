---
phase: 01-rotational-simulator-baseline
plan: 01
subsystem: simulation
tags: [rotational, state-machine, simulator, pytest, pandas, numpy]

# Dependency graph
requires:
  - phase: Phase A (Infrastructure)
    provides: rotational_engine.py, data_loader.py, bar data files, instruments.md registry

provides:
  - RotationalSimulator class with run() -> SimulationResult (trades, cycles, bars_processed)
  - FeatureComputer with compute_static_features() pass-through (extensible for Phase C)
  - TradeLogger with finalize_cycle() producing all spec Section 6.4 cycle record fields
  - RTH session filter for 10-sec bars (09:30-16:00 ET)
  - P1a/P1b date filtering via P1 midpoint bisection
  - 43 unit tests covering all state machine paths

affects:
  - 01-02 (determinism verification and baseline run)
  - 01-03 (parameter sweep)
  - Phase C (hypothesis integration — FeatureComputer extensibility)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - SimulationResult dataclass contract (trades DataFrame + cycles DataFrame + bars_processed int)
    - State machine FLAT/POSITIONED with SEED/REVERSAL/ADD actions
    - Level-based geometric qty progression with cap reset
    - Bar-by-bar MAE/MFE and retracement_depths tracking

key-files:
  created:
    - shared/archetypes/rotational/rotational_simulator.py
    - shared/archetypes/rotational/test_rotational_simulator.py
  modified: []

key-decisions:
  - "RTH filter applies only when bar_data_primary key contains '10sec'; vol/tick bars are inherently session-filtered"
  - "ADD level recorded at time of action (before increment); cap reset records level=0 and qty=initial_qty"
  - "REVERSAL costs are two actions: FLATTEN (cost*flatten_qty) + REVERSAL_entry (cost*initial_qty)"
  - "P1 midpoint computed as start + (end-start)/2 using Python timedelta arithmetic"
  - "FeatureComputer is a no-op pass-through for baseline — ATR and SD bands already in CSV columns"

patterns-established:
  - "Pattern 1: All instrument constants (tick_size, cost_ticks) extracted from config._instrument — never hardcoded"
  - "Pattern 2: Simulation state reset at run() start — safe for multiple run() calls in tests"
  - "Pattern 3: Synthetic DataFrames in tests — no CSV file dependencies for unit tests"

requirements-completed: [ROT-SIM-01, ROT-SIM-02, ROT-SIM-03, ROT-SIM-04]

# Metrics
duration: 4min
completed: 2026-03-15
---

# Phase 1 Plan 01: Rotational Simulator — Core State Machine Summary

**RotationalSimulator implementing FLAT/POSITIONED state machine (SEED/REVERSAL/ADD) with geometric martingale sizing, RTH session filter, P1a/P1b date filtering, per-cycle MAE/MFE/retracement tracking, and 43 passing unit tests**

## Performance

- **Duration:** 4 min
- **Started:** 2026-03-15T21:25:48Z
- **Completed:** 2026-03-15T21:29:46Z
- **Tasks:** 1
- **Files modified:** 2

## Accomplishments

- Built complete RotationalSimulator class satisfying engine contract: `RotationalSimulator(config, bar_data, reference_data=None).run() -> SimulationResult`
- Implemented full state machine: SEED on first flat bar (always Long), REVERSAL on in-favor price movement, ADD on against movement with geometric doubling (1, 2, 4, 8) and cap reset
- TradeLogger produces cycle records with all 19 spec Section 6.4 fields including MAE, MFE, retracement_depths, time_at_max_level_bars, and trend_defense_level_max
- Cost model verified: SEED costs cost_ticks * qty; REVERSAL costs double (FLATTEN + entry); ADD costs cost_ticks * add_qty
- RTH filter correctly includes 09:30-15:59 and excludes 16:00+ for 10-sec sources; vol/tick sources are unfiltered
- P1a/P1b date filtering bisects P1 window (2025-09-21 to 2025-12-14) at midpoint (~2025-11-02)
- 43 unit tests pass covering: SEED, REVERSAL, ADD, ADD CAP, cycle record completeness, cost model arithmetic, RTH filter edge cases, date filter for P1a/P1b/P1, SimulationResult contract, and determinism

## Task Commits

Each task was committed atomically:

1. **Task 1: RotationalSimulator with state machine, FeatureComputer, TradeLogger, RTH filter, date filtering** - `2a854f8` (feat)

## Files Created/Modified

- `shared/archetypes/rotational/rotational_simulator.py` — Core simulator: RotationalSimulator, FeatureComputer, TradeLogger, SimulationResult (622 lines)
- `shared/archetypes/rotational/test_rotational_simulator.py` — Unit test suite: 43 tests across 9 test classes (639 lines)

## Decisions Made

- RTH filter keyed on config `bar_data_primary` containing "10sec" in any source ID — avoids adding a new config field and matches the bar type naming convention
- Level recorded in ADD trade row at the level value before the increment (so level=0 means "first add", level=1 means "second add", etc.)
- Reversal trade rows record the new cycle's direction (Short or Long after flip) — FLATTEN rows record prior direction
- Empty bar input (0 rows after filtering) returns empty trades/cycles DataFrames and bars_processed=0 without error
- retracement_depths stored as Python list per cycle row (JSON-serializable for downstream TSV/JSON output)

## Deviations from Plan

None — plan executed exactly as written. One minor implementation detail resolved: ADD level recording clarified as "level at time of action" (before increment) to produce meaningful level numbers in trade logs. This matches the spec intent and was not a deviation.

## Issues Encountered

None.

## User Setup Required

None — no external service configuration required.

## Next Phase Readiness

- RotationalSimulator is ready for plan 01-02: determinism verification on real bar data and C++ defaults baseline run (StepDist=2.0 on all 3 bar types, P1a)
- Engine import chain verified: `from rotational_simulator import RotationalSimulator, SimulationResult` works from the archetype directory
- The `_filter_bars` RTH detection relies on `bar_data_primary` keys containing "10sec" — this works correctly when the engine passes a single source_id at a time (as it does in the main loop)

---
*Phase: 01-rotational-simulator-baseline*
*Completed: 2026-03-15*
