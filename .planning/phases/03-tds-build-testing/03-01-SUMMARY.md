---
phase: 03-tds-build-testing
plan: 01
subsystem: trading-system
tags: [trend-defense, tdd, detectors, escalation, bar-type-conversion, pytest]

# Dependency graph
requires:
  - phase: 02.1-sizing-sweep-baseline
    provides: baseline configs (250vol SD=7.0 ML=1 PF=2.20, 250tick SD=4.5 ML=1 PF=1.84, 10sec SD=10.0 ML=1 PF=1.72) and bar-type cadence knowledge
  - phase: 01-rotational-simulator-baseline
    provides: RotationalSimulator with trend_defense_level_max placeholder and cycle record schema

provides:
  - TrendDefenseSystem class (trend_defense.py) with TDSState dataclass
  - 5 detectors: retracement quality, velocity monitor, consecutive add counter, drawdown budget, trend precursor composite
  - 3-level escalation: step_widen (L1), refuse_adds (L2), force_flatten+cooldown (L3)
  - Bar-type-aware initialization converting seconds to bar counts via median_bar_sec
  - 14 unit tests covering all detectors and response levels
  - tds_results/ output directory for future TDS testing artifacts

affects: [03-02-simulator-integration, phase-04, feature-evaluator-tds-signals]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - Stateful defense system as standalone class (no direct simulator mutation)
    - Seconds-to-bars conversion at init time using median_bar_sec for bar-type portability
    - Return action_modifiers dict pattern (simulator applies, TDS does not mutate)
    - Qualifying-retracement reset for consecutive_adds (Pitfall 5 prevention)

key-files:
  created:
    - shared/archetypes/rotational/trend_defense.py
    - shared/archetypes/rotational/test_trend_defense.py
    - shared/archetypes/rotational/tds_results/.gitkeep
  modified: []

key-decisions:
  - "TDS timing thresholds stored in seconds, converted to bar counts via max(1, round(sec/median_bar_sec)) at init — ensures cross-bar-type comparability"
  - "consecutive_adds resets on qualifying retracement (>= retracement_reset_pct * step_dist in-favor from _last_add_price) in addition to reversal — avoids premature Level 2 trigger on healthy cycles"
  - "can_reengage() is pure bar-count-based (cooldown_remaining <= 0) — avoids chicken-and-egg feature computation during cooldown"
  - "TDS does not mutate simulator state — returns action_modifiers dict, simulator applies — keeps TDS independently testable"

patterns-established:
  - "Pattern: archetype line 1 convention — all rotational Python files begin with # archetype: rotational"
  - "Pattern: bar-type parameter portability — all timing thresholds in seconds, converted at init, never hardcoded as bar counts"
  - "Pattern: action_modifiers dict interface — TDS returns {step_widen_factor, max_levels_reduction, refuse_adds, force_flatten, reduced_reversal_threshold}"

requirements-completed: [ROT-RES-04]

# Metrics
duration: 10min
completed: 2026-03-16
---

# Phase 03 Plan 01: TDS Build (TDD) Summary

**Standalone TrendDefenseSystem class with 5 detectors and 3-level escalation, seconds-based timing thresholds converting to bar counts via median_bar_sec, and 14 passing unit tests**

## Performance

- **Duration:** ~10 min
- **Started:** 2026-03-16T04:49:24Z
- **Completed:** 2026-03-16T04:59:17Z
- **Tasks:** 1 (TDD: RED + GREEN phases)
- **Files modified:** 3 created

## Accomplishments

- Created `trend_defense.py` with `TDSState` dataclass and `TrendDefenseSystem` class implementing all 5 detectors and 3 escalation levels
- Created `test_trend_defense.py` with 14 unit tests, all passing after GREEN phase implementation
- Implemented bar-type-aware parameter initialization: velocity_threshold_sec and cooldown_sec convert to bar counts using `max(1, round(sec / median_bar_sec))`
- Applied Pitfall 5 fix: consecutive_adds resets on qualifying retracement mid-cycle, not only on reversal
- TDS returns action_modifiers dict; simulator applies it — no direct state mutation (independently testable)

## Task Commits

1. **Task 1 (TDD RED+GREEN): TrendDefenseSystem with 5 detectors and 3-level escalation** - `989eb26` (feat)

## Files Created/Modified

- `shared/archetypes/rotational/trend_defense.py` — TDSState dataclass + TrendDefenseSystem class (5 detectors, 3-level escalation, bar-type conversion, qualifying-retracement reset)
- `shared/archetypes/rotational/test_trend_defense.py` — 14 unit tests: init, 5 detector tests, 3 level response tests, re-engagement, bar-type conversion, summary metrics, on_reversal, on_add
- `shared/archetypes/rotational/tds_results/.gitkeep` — output directory for TDS testing artifacts

## Decisions Made

- **Seconds-based thresholds at init:** All timing params (velocity_threshold_sec, cooldown_sec) stored in seconds in config, converted to bar counts via `max(1, round(sec / median_bar_sec))`. Makes configs interpretable and portable across 10sec/250vol/250tick bar types.
- **Qualifying retracement reset:** Consecutive adds counter resets when price moves >= `retracement_reset_pct * step_dist_ticks` in-favor from `_last_add_price`. Prevents premature Level 2 firing on cycles with healthy retracements between adds (Pitfall 5 from research).
- **Pure cooldown check:** `can_reengage()` returns `cooldown_remaining <= 0` without feature-based secondary gating. Avoids chicken-and-egg problem where features would need to be computed during bars skipped by cooldown.
- **No simulator mutation:** TDS returns action_modifiers dict and the simulator applies them. Enables isolated unit testing with mock sim_state dicts.

## Deviations from Plan

None — plan executed exactly as written. All 14 tests in the behavior spec were implemented and pass. The on_add signature was extended with an optional `price` parameter (not specified in spec but required by Pitfall 5 qualifying-retracement logic — this is correctness, not scope creep).

## Issues Encountered

None — implementation was straightforward following the research patterns. All 14 tests went RED then GREEN as expected.

## User Setup Required

None — no external service configuration required.

## Next Phase Readiness

- `TrendDefenseSystem` and `TDSState` are ready for import by the simulator integration plan (03-02)
- The action_modifiers dict interface contract is established and tested
- Bar-type conversion is validated for both 10sec (median=10.0) and vol/tick-like (median=3.0) cadences
- tds_results/ directory exists for future output artifacts
- No blockers for Plan 02 (simulator integration)

---
*Phase: 03-tds-build-testing*
*Completed: 2026-03-16*
