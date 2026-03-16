---
phase: 03-tds-build-testing
plan: 02
subsystem: trading-system
tags: [trend-defense, simulator-integration, dynamic-features, tds-wiring, pytest]

# Dependency graph
requires:
  - phase: 03-tds-build-testing
    plan: 01
    provides: TrendDefenseSystem class with evaluate()/apply_response()/update_cycle_metrics() interface
  - phase: 01-rotational-simulator-baseline
    provides: RotationalSimulator with trend_defense_level_max placeholder and cycle record schema

provides:
  - RotationalSimulator with TDS integration seam (self._tds, TDS evaluate per-bar)
  - H36 (adverse_speed) and H39 (adverse_velocity_ratio) dynamic features computed inside simulation loop
  - TDS Level 3 forced flatten producing cycles with exit_reason='td_flatten'
  - trend_defense_level_max in cycle records reflecting actual TDS activity
  - 8 integration tests validating TDS through full simulator path

affects: [phase-04-tds-calibration, feature-evaluator-tds-signals]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - TDS evaluation before state machine transitions (Pattern 3 from research)
    - _compute_dynamic_features() computing H36/H39 per-bar inside simulation loop
    - action_modifiers dict applied within existing POSITIONED branch (step_widen, refuse_adds)
    - Cooldown period: decrement cooldown_remaining per bar, can_reengage() check before re-seeding
    - finalize_cycle() extended with trend_defense_level_max=0 default (backward compat)
    - Cycle record patching after reversal for correct tds_level_max attribution

key-files:
  created: []
  modified:
    - shared/archetypes/rotational/rotational_simulator.py
    - shared/archetypes/rotational/test_trend_defense.py

key-decisions:
  - "Import TrendDefenseSystem with _TDS_AVAILABLE guard so simulator loads even if trend_defense.py is missing — safe degradation"
  - "bar_duration_stats computed from actual bar timestamps (median of first 1000 diffs) at run() time, not init time — bars available only then"
  - "trend_defense_level_max patched onto cycle record after _reversal() call because finalize_cycle() is called inside _reversal() before tds_level_max is reset"
  - "Cooldown bars skipped entirely (continue) rather than going through FLAT->SEED — prevents premature re-entry during cooldown window"
  - "_avg_entry_price tracked as running attribute updated on SEED, ADD, and reset on reversal — required by TDS sim_state dict"

requirements-completed: [ROT-RES-04]

# Metrics
duration: ~11min
completed: 2026-03-16
---

# Phase 03 Plan 02: TDS Simulator Integration Summary

**TrendDefenseSystem wired into RotationalSimulator loop with H36/H39 dynamic features, Level 3 forced-flatten producing td_flatten cycles, and 8 integration tests validating all behaviors**

## Performance

- **Duration:** ~11 min
- **Started:** 2026-03-16T05:10:00Z
- **Completed:** 2026-03-16T05:20:50Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments

- Modified `rotational_simulator.py` to import and initialize `TrendDefenseSystem` when `trend_defense.enabled=true` in config
- Added `_get_sim_state()` helper returning all TDS-required keys including `avg_entry_price` (new tracked attribute)
- Added `_compute_dynamic_features()` computing H36 (adverse_speed) and H39 (adverse_velocity_ratio) per-bar from price deltas and bar timestamps
- Added `_finalize_current_cycle_as_tds_exit()` for Level 3 forced-flatten producing `exit_reason='td_flatten'`
- Modified simulation loop: TDS evaluate+apply_response before state machine; cooldown period skips bars; step_widen_factor and refuse_adds applied in POSITIONED branch
- Extended `finalize_cycle()` with `trend_defense_level_max=0` default parameter (fully backward compatible)
- Added 8 integration tests in `test_trend_defense.py` covering: basic integration, survival improvement, bar-type conversion, summary metrics, hypothesis feedins graceful fallback, dynamic feature wiring, determinism, backward compat passthrough
- Full test suite: 156 tests pass (50 simulator + 22 TDS + 84 other)

## Task Commits

1. **Task 1: TDS integration into RotationalSimulator** - `bf6de20`
2. **Task 2: 8 integration tests for TDS-in-simulator** - `4ea8d20`

## Files Created/Modified

- `shared/archetypes/rotational/rotational_simulator.py` — TDS import guard, `_get_sim_state()`, `_compute_dynamic_features()`, `_finalize_current_cycle_as_tds_exit()`, modified simulation loop, `finalize_cycle()` parameter extension
- `shared/archetypes/rotational/test_trend_defense.py` — `_make_sim_config()`, `_make_sim_tds_config()`, `_make_sim_bars()`, `_run_sim()` helpers + `TestTDSSimulatorIntegration` class with 8 tests

## Decisions Made

- **Import guard for TrendDefenseSystem:** `try/except ImportError` sets `_TDS_AVAILABLE` flag so the simulator file loads cleanly even if `trend_defense.py` is absent. Prevents circular import or missing-module crashes at load time.
- **bar_duration_stats computed at run() time:** Bars are only available after `_filter_bars()` so TDS initialization happens inside `run()`, not `__init__()`. Computes median of first 1000 bar timestamp diffs for efficiency on large datasets.
- **Cycle patching pattern for tds_level_max:** `_reversal()` calls `logger.finalize_cycle()` internally. To set `trend_defense_level_max` correctly on the just-finalized cycle, we patch `logger._cycles[-1]` after the call. Alternative (passing the level as parameter to `_reversal`) would require changing the method signature in ways that break the existing tests.
- **Cooldown enforcement via `continue`:** During cooldown, the entire bar is skipped (no SEED allowed). This is a stronger gate than just preventing adds — prevents re-entry mid-cooldown even at FLAT.
- **avg_entry_price as running attribute:** Required by TDS's `update_cycle_metrics()` which computes unrealized PnL. Updated on SEED, each ADD (weighted average), and reset on reversal/TDS exit. No additional cost since it's O(1) per add.

## Deviations from Plan

None — plan executed exactly as written. All 8 integration tests implemented and pass. The `_avg_entry_price` tracking (plan item 4 note) was confirmed as needing implementation — it did not exist as a running attribute before. Added cleanly to SEED, ADD, and reset paths.

## Issues Encountered

None — integration was straightforward following research Pattern 3. The cycle-patching approach for `tds_level_max` on reversals was the one implementation detail that required a brief reasoning step (noted in Decisions Made above).

## User Setup Required

None — no external service configuration required.

## Next Phase Readiness

- Full TDS integration is operational and validated
- Dynamic features H36/H39 computed inside loop (not static pass) — ready for Phase 4 TDS calibration
- Determinism confirmed with TDS enabled (identical config+data → identical output)
- Backward compatibility confirmed (TDS disabled/absent → identical behavior to pre-TDS baseline)
- Bar-type parameter conversion validated for both 10sec and vol-like cadences
- 156 tests passing — no regressions

---
*Phase: 03-tds-build-testing*
*Completed: 2026-03-16*
