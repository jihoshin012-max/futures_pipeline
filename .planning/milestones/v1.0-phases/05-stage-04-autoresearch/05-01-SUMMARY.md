---
phase: 05-stage-04-autoresearch
plan: 01
subsystem: autoresearch
tags: [driver, keep-revert-loop, budget-enforcement, tsv-logging, experiment-anomaly, trail-validation]

# Dependency graph
requires:
  - phase: 04-backtest-engine
    provides: backtest_engine.py fixed harness, config_schema.json, result.json schema, trail step validation rules

provides:
  - driver.py keep/revert loop with budget enforcement and EXPERIMENT_ANOMALY handling
  - program.md machine-readable steering file (METRIC/KEEP RULE/BUDGET)
  - current_best/exit_params.json seeded baseline config (score_threshold=0)
  - results.tsv with 24-column header and seeded row with real engine metrics
  - test_driver.py: 17 unit/integration tests covering all driver behaviors

affects:
  - 05-stage-04-autoresearch overnight test (plan 02+)
  - Any phase that reads results.tsv for n_prior_tests budget tracking

# Tech tracking
tech-stack:
  added: [subprocess, shutil, pathlib, json, random, copy, datetime (all stdlib)]
  patterns:
    - Keep/revert loop with per-iteration program.md re-read (budget adjustable mid-run)
    - n_prior_tests counted BEFORE experiment from TSV row count (not cached)
    - run_id captured immediately after engine completes (before autocommit.sh window)
    - EXPERIMENT_ANOMALY logged to audit_log.md on non-zero engine exit; loop continues
    - Trail step validation returns bool (non-raising) for driver-side retry logic
    - score_threshold=0 in seeded baseline (required for trades with uncalibrated BinnedScoringAdapter)

key-files:
  created:
    - stages/04-backtest/autoresearch/driver.py
    - stages/04-backtest/autoresearch/program.md
    - stages/04-backtest/autoresearch/current_best/exit_params.json
    - stages/04-backtest/autoresearch/results.tsv
    - tests/test_driver.py
  modified: []

key-decisions:
  - "validate_trail_steps() returns bool not raises — driver retries proposal with valid steps rather than propagating exceptions"
  - "score_threshold=0 in seeded baseline — BinnedScoringAdapter returns zeros; threshold=48 produces n_trades=0 for every experiment"
  - "Budget counts seeded row — n_prior_tests=1 at start of first experiment; budget=3 means 2 new experiments run"
  - "propose_next_params uses random perturbation within valid ranges — sufficient for loop health verification; smarter proposer is Phase 6+ work"
  - "run_id read via _get_run_id() helper — isolated for mocking in tests, called immediately after engine completes"

patterns-established:
  - "Pattern: Keep/revert loop — read program.md, count TSV rows, propose, run engine, keep or revert, append row"
  - "Pattern: Anomaly handling — non-zero exit code logs EXPERIMENT_ANOMALY, reverts params, continues loop"
  - "Pattern: Trail step mutation — sort by trigger, enforce strict monotonicity post-sort, retry up to 10x"

requirements-completed: [AUTO-01, AUTO-02]

# Metrics
duration: 10min
completed: 2026-03-14
---

# Phase 5 Plan 01: Autoresearch Driver Summary

**Keep/revert autoresearch driver for Stage 04 with budget enforcement, EXPERIMENT_ANOMALY handling, and seeded baseline (pf=0.453, n_trades=4674 with score_threshold=0)**

## Performance

- **Duration:** 10 min
- **Started:** 2026-03-14T14:31:14Z
- **Completed:** 2026-03-14T14:41:27Z
- **Tasks:** 2
- **Files modified:** 5

## Accomplishments
- driver.py: 200-line keep/revert loop with budget enforcement, trail step validation, TSV logging, and EXPERIMENT_ANOMALY audit handling
- program.md: machine-readable steering file with METRIC/KEEP RULE/BUDGET fields, parseable every iteration
- Seeded baseline: current_best/exit_params.json (score_threshold=0) + results.tsv with real engine metrics (pf=0.453, 4674 trades)
- test_driver.py: 17 tests covering all 8 behaviors specified in plan — all pass

## Task Commits

1. **Task 1: Write test_driver.py and implement driver.py with program.md** - `2836418` (feat)
2. **Task 2: Seed current_best and results.tsv baseline** - `5468603` (chore)

## Files Created/Modified
- `stages/04-backtest/autoresearch/driver.py` — keep/revert loop, parse_program_md, validate_trail_steps, propose_next_params, run_loop
- `stages/04-backtest/autoresearch/program.md` — machine-readable METRIC/KEEP RULE/BUDGET steering file
- `stages/04-backtest/autoresearch/current_best/exit_params.json` — seeded baseline with score_threshold=0
- `stages/04-backtest/autoresearch/results.tsv` — 24-column header + seeded row (pf=0.453, n_trades=4674)
- `tests/test_driver.py` — 17 unit/integration tests using mocked subprocess

## Decisions Made
- validate_trail_steps() returns bool (not raises) so the driver can retry proposal generation without catching exceptions
- score_threshold=0 in seeded baseline because BinnedScoringAdapter returns zeros; threshold=48 produces n_trades=0 for all experiments, preventing any keep/revert decisions
- Budget counting: seeded row counts as 1 prior test (n_prior_tests=1 at start of first experiment). With budget=3, only 2 new experiments run. This matches the spec: "count rows in results.tsv before experiment"
- propose_next_params uses random perturbation (not intelligent search) — deliberate simplification sufficient for loop health verification in Phase 5

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed test budget expectation — seeded row counts toward budget**
- **Found during:** Task 1 (TDD GREEN phase)
- **Issue:** Test expected `budget=1` to allow 1 experiment, but the seeded row already occupies n_prior_tests=1, so budget=1 triggers immediate stop before any experiment
- **Fix:** Changed test budgets from 1 to 2 where "run 1 experiment" is needed; updated budget_enforcement test comment to document actual behavior
- **Files modified:** tests/test_driver.py
- **Verification:** All 17 tests pass
- **Committed in:** 2836418 (Task 1 commit)

---

**Total deviations:** 1 auto-fixed (Rule 1 - bug in test expectations)
**Impact on plan:** Fix necessary for correct test coverage. No scope creep. Driver behavior is correct per spec.

## Issues Encountered
- None after the test budget expectation fix.

## User Setup Required
None — no external service configuration required.

## Next Phase Readiness
- driver.py is ready for overnight runs — seed is in place, tests pass
- Recommend running 50-experiment test (plan 02+) before scaling to 500 to verify loop health
- feature_evaluator.py (AUTO-05) and evaluate_features.py (AUTO-04) are in untracked state from a prior session — review before plan 02 scopes them

---
*Phase: 05-stage-04-autoresearch*
*Completed: 2026-03-14*
