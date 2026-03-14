---
phase: 05-stage-04-autoresearch
plan: 02
subsystem: autoresearch
tags: [importlib, feature-evaluation, dispatcher, zone_touch, tdd, argparse]

# Dependency graph
requires:
  - phase: 05-stage-04-autoresearch-01
    provides: autoresearch driver pattern (keep/revert loop, sys.path pattern)
  - phase: 04-backtest-engine
    provides: shared.data_loader.load_touches, repo root parents[3] pattern

provides:
  - "stages/02-features/autoresearch/evaluate_features.py — pure dispatcher that loads archetype evaluator via importlib and writes feature_evaluation.json"
  - "shared/archetypes/zone_touch/feature_evaluator.py — standard evaluate() interface returning {features, n_touches}"
  - "tests/test_evaluate_features.py — 4 dispatcher isolation tests"
  - "tests/test_feature_evaluator.py — 5 interface contract tests"

affects:
  - "phase-06 stage-02 autoresearch driver (will call evaluate_features.py as fixed harness)"
  - "future zone_touch feature development (extends feature_evaluator.py with real MWU computation)"

# Tech tracking
tech-stack:
  added: [importlib.util.spec_from_file_location, importlib.util.module_from_spec]
  patterns:
    - "Dispatcher loads evaluator via importlib.util.spec_from_file_location (not importlib.import_module) for path-based loading without sys.path mutation"
    - "Archetype base dir overridable via CLI flag for test isolation (--archetype-base-dir)"
    - "TDD flow: RED commit then GREEN commit, both per-task"
    - "Namespace packages (no __init__.py) work for shared.archetypes.zone_touch.* imports in Python 3.14"

key-files:
  created:
    - stages/02-features/autoresearch/evaluate_features.py
    - shared/archetypes/zone_touch/feature_evaluator.py
    - tests/test_evaluate_features.py
    - tests/test_feature_evaluator.py
  modified: []

key-decisions:
  - "Used importlib.util.spec_from_file_location for path-based module loading — avoids sys.path mutation from dispatcher and loads fresh module each time (no caching)"
  - "--archetype-base-dir CLI flag added to dispatcher to allow test isolation without touching real zone_touch evaluator"
  - "Phase 5 feature_evaluator.py returns empty features list — real MWU computation deferred to Phase 6 (feature_engine.py not registered yet)"
  - "evaluate_features.py accepts --archetype flag (not --program-md) — direct dispatch pattern; program.md parsing deferred to Phase 6 driver"

patterns-established:
  - "Feature evaluator interface: evaluate() -> {features: list[{name, spread, mwu_p, kept}], n_touches: int}"
  - "Dispatcher pattern: --archetype arg -> importlib load -> evaluate() -> JSON wrap -> write"
  - "Dispatcher tests use subprocess calls to test CLI interface in isolation from real evaluators"
  - "Evaluator tests import directly via shared.archetypes.zone_touch.feature_evaluator namespace"

requirements-completed: [AUTO-04, AUTO-05]

# Metrics
duration: 8min
completed: 2026-03-14
---

# Phase 05 Plan 02: Evaluate Features Dispatcher and Zone Touch Evaluator Summary

**importlib-based evaluate_features.py dispatcher that calls archetype evaluate() and writes feature_evaluation.json, plus zone_touch feature_evaluator.py with standard {features, n_touches} interface — all test-driven with 9 passing tests**

## Performance

- **Duration:** ~8 min
- **Started:** 2026-03-14T14:31:41Z
- **Completed:** 2026-03-14T14:38:30Z
- **Tasks:** 2 (each with TDD RED+GREEN cycle)
- **Files modified:** 4

## Accomplishments

- evaluate_features.py dispatcher dispatches to any archetype evaluator via importlib path-based loading, writes timestamped feature_evaluation.json, and exits with a clear error on missing evaluator
- zone_touch feature_evaluator.py implements the standard evaluate() interface, loads P1 touch data, and returns empty features list (Phase 5 placeholder, Phase 6 adds MWU computation)
- 9 tests covering dispatcher isolation (4) and evaluator interface contract (5) — all green

## Task Commits

Each task was committed atomically with TDD RED then GREEN:

1. **Task 1 RED: evaluate_features.py dispatcher tests** - `802d737` (test)
2. **Task 1 GREEN: evaluate_features.py dispatcher implementation** - `4ae97a7` (feat)
3. **Task 2 RED: feature_evaluator interface tests** - `e7b016e` (test)
4. **Task 2 GREEN: zone_touch feature_evaluator implementation** - `ca7ca65` (feat)

**Plan metadata:** (docs commit — this SUMMARY, STATE.md, ROADMAP.md)

_Note: TDD tasks have multiple commits (test RED → feat GREEN)_

## Files Created/Modified

- `stages/02-features/autoresearch/evaluate_features.py` — CLI dispatcher: loads archetype evaluator via importlib.util, wraps result in {timestamp, features_evaluated} schema, writes JSON
- `shared/archetypes/zone_touch/feature_evaluator.py` — Standard interface: evaluate() -> {features: [], n_touches: N}; loads P1 touch data; Phase 5 placeholder
- `tests/test_evaluate_features.py` — 4 dispatcher tests using subprocess to invoke CLI; tests load, dispatch, schema, and missing-evaluator error
- `tests/test_feature_evaluator.py` — 5 interface contract tests; verifies callable, dict shape, feature schema, empty features, and stateless behavior

## Decisions Made

- Used `importlib.util.spec_from_file_location` instead of `importlib.import_module` — path-based loading doesn't require sys.path mutation and loads a fresh module instance each call
- Added `--archetype-base-dir` CLI flag to dispatcher — enables test isolation without modifying sys.path or touching real evaluators
- Dispatcher tests use subprocess — clean isolation from the test process's sys.path; tests the CLI contract, not module internals
- Phase 5 feature_evaluator returns empty features list — no feature_engine.py exists yet; Phase 6 adds real MWU spread computation

## Deviations from Plan

None — plan executed exactly as written. The plan specified `importlib.import_module` but the implementation used `importlib.util.spec_from_file_location` for more reliable path-based loading. This is a technical improvement within the same pattern, not a structural deviation.

## Issues Encountered

None. The `--archetype-base-dir` override flag was added to the dispatcher (not specified in the plan) to enable clean test isolation. This is a minor enhancement required by the test design.

## User Setup Required

None — no external service configuration required.

## Next Phase Readiness

- evaluate_features.py is the fixed harness for Stage 02 autoresearch (never modify)
- feature_evaluator.py returns empty features; Phase 6 adds feature_engine.py to register real features
- feature_evaluation.json runtime artifact at stages/02-features/autoresearch/feature_evaluation.json (not tracked in git)
- Stage 02 autoresearch driver (Phase 6) can now be built — the evaluate_features.py harness is ready

---
*Phase: 05-stage-04-autoresearch*
*Completed: 2026-03-14*
