---
phase: 04-backtest-engine
plan: 03
subsystem: backtest-engine, simulation
tags: [python, pandas, numpy, importlib, dataclass, tdd, pure-function, dynamic-dispatch]

# Dependency graph
requires:
  - phase: 04-backtest-engine
    plan: 02
    provides: "data_loader.py (load_data, parse_instruments_md), scoring_adapter.py (load_scoring_adapter, BinnedScoringAdapter)"
  - phase: 04-backtest-engine
    plan: 01
    provides: "config_schema.json, config_schema.md, backtest_engine_qa.md, simulation_rules.md"
  - phase: 01-scaffold
    provides: "_config/instruments.md registry, zone_touch archetype folder, exit_templates.md"
provides:
  - "shared/archetypes/zone_touch/zone_touch_simulator.py: pure function run() -> SimResult with full trail mechanics"
  - "stages/04-backtest/autoresearch/backtest_engine.py: fixed CLI harness with holdout guard, adapter validation, dynamic dispatch"
  - "tests/test_zone_touch_simulator.py: 13 unit tests for simulator"
  - "tests/test_backtest_engine.py: 15 integration and smoke tests for engine"
affects: [04-04, phase-05, phase-06, autoresearch-loop]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Simulator as pure function: no I/O, no global state, inputs only via args — run(bar_df, touch_row, config, bar_offset) -> SimResult"
    - "Stop tracked as absolute price (not ticks) to support trail ratchet above entry (BE and profitable stops)"
    - "Trail ratchet: iterate all triggered steps each bar, keep last (tightest) new_stop_ticks; stop only moves favorable"
    - "Engine dynamic dispatch: importlib.import_module(config.archetype.simulator_module) with archetype dir added to sys.path"
    - "Adapter validation: score() called on zero-row DataFrame with expected columns before any experiment data loads (ENGINE-09)"
    - "Holdout guard: Path(p).name.lower() check for 'p2' covers ZRA_Hist_P2.csv and NQ_BarData_250vol_P2.txt patterns"
    - "cost_ticks: always from parse_instruments_md() — injected into sim_config at run time, never hardcoded"
    - "Determinism: touches sorted by DateTime before processing, searchsorted for bar_offset"

key-files:
  created:
    - shared/archetypes/zone_touch/zone_touch_simulator.py
    - stages/04-backtest/autoresearch/backtest_engine.py
    - tests/test_zone_touch_simulator.py
    - tests/test_backtest_engine.py

key-decisions:
  - "Stop price tracked as absolute price, not stop_ticks distance — required because ratcheted stop can be above entry (positive pnl_ticks on stop hit)"
  - "Engine _REPO_ROOT uses parents[3] not parents[2]: file is at stages/04-backtest/autoresearch/backtest_engine.py, not two levels deep"
  - "engine line count ~427 (exceeds 250-line target) — inflated by docstrings/section headers for a 'fixed-forever' file; all functions correct and complete"
  - "validate_adapter uses zero-row DataFrame with known columns to avoid KeyError before NotImplementedError fires (Pitfall 6)"
  - "sim_config dict copied per-touch with tick_size injected — avoids mutating the original config"

patterns-established:
  - "TDD: test written first (RED), implementation second (GREEN), verified with pytest"
  - "Absolute-price stop tracking pattern: enables trail ratchets that move stop above entry"

requirements-completed: [ENGINE-03, ENGINE-09]

# Metrics
duration: 16min
completed: 2026-03-14
---

# Phase 04 Plan 03: Zone Touch Simulator and Backtest Engine Summary

**Pure-function zone_touch simulator with 4-step trail mechanics and a fixed CLI backtest engine with holdout guard, adapter stub validation, and dynamic archetype dispatch — together enabling `python backtest_engine.py --config params.json --output result.json`**

## Performance

- **Duration:** ~16 min
- **Started:** 2026-03-14T05:05:00Z
- **Completed:** 2026-03-14T05:21:00Z
- **Tasks:** 2
- **Files modified:** 4 (all created)

## Accomplishments
- `zone_touch_simulator.py` implements run() as a fully pure function: stop tracked as absolute price (not distance), trail ratchets correctly apply multiple steps per bar, BE trigger (new_stop_ticks=0) moves stop to entry, time cap exits at Last price
- `backtest_engine.py` implements the complete fixed harness: config load+validation, holdout guard, adapter validation (ENGINE-09), routing waterfall, dynamic simulator dispatch, per-mode metrics, net-of-cost PF
- 28 tests pass total: 13 simulator unit tests + 15 engine integration/smoke tests
- Engine reads cost_ticks from instruments.md via parse_instruments_md — zero hardcoded instrument constants

## Task Commits

Each task was committed atomically:

1. **Task 1: Implement zone_touch_simulator.py** - `e562d13` (feat)
2. **Task 2: Implement backtest_engine.py** - `cc15cf4` (feat)

_Note: TDD tasks — tests written first (RED), then implementation (GREEN)_

## Files Created/Modified
- `shared/archetypes/zone_touch/zone_touch_simulator.py` - Pure function simulator: run(bar_df, touch_row, config, bar_offset) -> SimResult with trail ratchet, BE trigger, time cap
- `stages/04-backtest/autoresearch/backtest_engine.py` - Fixed CLI engine with 8 functions covering full pipeline from config load to result.json write
- `tests/test_zone_touch_simulator.py` - 13 unit tests: stop_hit, target_hit, BE_trigger, trail_ratchet, time_cap, determinism, pure_function
- `tests/test_backtest_engine.py` - 15 tests: holdout guard (2 block + 1 allow), trail validation (3), adapter stubs (2), unknown simulator (1), output schema (1), determinism (1), docs (3)

## Decisions Made
- Stop price tracked as absolute price (not distance from entry) — necessary because after trail ratchet, stop can be above entry price (e.g., new_stop_ticks=20 long means stop at entry+20*tick_size). Tracking as ticks-from-entry would require signed arithmetic and direction-aware comparison. Absolute price is simpler and correct.
- `_REPO_ROOT = Path(__file__).resolve().parents[3]` — engine is 3 levels deep under repo root (stages/04-backtest/autoresearch/), not 2.
- Engine line count ~427 lines (exceeded 250-line target) — the "fixed-forever" nature of this file warrants thorough docstrings for future agents; functional logic is complete and correct.
- `validate_adapter` passes zero-row DataFrame with known column names to avoid KeyError before NotImplementedError (RESEARCH.md Pitfall 6).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Stop logic rewritten to use absolute price tracking**
- **Found during:** Task 1 (TestTrailRatchet::test_trail_ratchet_long)
- **Issue:** Initial implementation tracked stop as `current_stop_ticks` (distance from entry), which cannot represent a stop above entry (e.g., new_stop_ticks=20 for long = stop at entry+20*tick). `bar_adverse_ticks = (entry - low) / tick_size` is negative when low > entry, so the stop check `bar_adverse_ticks >= current_stop_ticks` never fires.
- **Fix:** Rewrote stop to track `stop_price` as absolute price. For LONG: initial `stop_price = entry - stop_ticks * tick_size`; after ratchet to new_stop=20: `stop_price = entry + 20 * tick_size`. Stop check: `low <= stop_price` (LONG) / `high >= stop_price` (SHORT).
- **Files modified:** shared/archetypes/zone_touch/zone_touch_simulator.py
- **Verification:** TestTrailRatchet::test_trail_ratchet_long passes; all 13 simulator tests pass
- **Committed in:** e562d13 (Task 1 commit, implementation rewrite before final commit)

**2. [Rule 3 - Blocking] Engine _REPO_ROOT depth corrected from parents[2] to parents[3]**
- **Found during:** Task 2 (TestHoldoutGuard::test_holdout_guard_blocks_p2)
- **Issue:** `Path(__file__).resolve().parents[2]` from `stages/04-backtest/autoresearch/backtest_engine.py` resolves to `stages/` (not repo root). Engine was constructing `stages/_config/instruments.md` — a FileNotFoundError on first run.
- **Fix:** Changed to `parents[3]` which correctly resolves to repo root `C:/Projects/pipeline`.
- **Files modified:** stages/04-backtest/autoresearch/backtest_engine.py
- **Verification:** TestHoldoutGuard::test_holdout_guard_blocks_p2 passes; all 15 engine tests pass
- **Committed in:** cc15cf4 (Task 2 commit)

---

**Total deviations:** 2 auto-fixed (both Rule 1/3 — bugs: stop price tracking logic + path depth)
**Impact on plan:** Both fixes necessary for correctness. No scope creep. Core behavior matches plan intent exactly.

## Issues Encountered
- Integration tests (test_engine_produces_output, test_engine_determinism) each take ~3 minutes because they load full P1 touch/bar data and run simulation against all touches. Determinism test runs the engine twice = ~6 minutes. Normal for real-data integration tests.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- `backtest_engine.py` is now the fixed harness — ready for autoresearch use with `--config params.json --output result.json`
- `zone_touch_simulator.py` implements all trail mechanics including multi-step ratchet and BE trigger
- cost_ticks flows correctly from instruments.md → engine → metrics aggregation
- All 28 tests pass; engine is deterministic and holdout-guarded
- Phase 4 Plan 04 (if any) or Phase 5 autoresearch can begin immediately

---
*Phase: 04-backtest-engine*
*Completed: 2026-03-14*
