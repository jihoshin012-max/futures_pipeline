---
phase: 04-backtest-engine
plan: 02
subsystem: data-loading, scoring
tags: [pandas, json, regex, data-loader, scoring-adapter, tdd]

# Dependency graph
requires:
  - phase: 01-scaffold
    provides: "scoring_adapter.py stub classes, instruments.md registry, bar/touch data files"
  - phase: 03-git-infrastructure
    provides: "git infrastructure enabling atomic commits per task"
provides:
  - "shared/data_loader.py: load_bars, load_touches, load_data, parse_instruments_md"
  - "shared/scoring_models/scoring_adapter.py: load_scoring_adapter factory + BinnedScoringAdapter implementation"
  - "shared/scoring_models/zone_touch_v1.json: uncalibrated placeholder scoring model"
  - "tests/test_data_loader.py: 11 tests for data loader"
  - "tests/test_scoring_adapter_impl.py: 11 tests for scoring adapter"
affects: [04-03, 04-backtest-engine, phase-05]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "parse_instruments_md reads tick constants from _config/instruments.md via regex — never hardcoded"
    - "BinnedScoringAdapter.score() always returns pd.Series aligned to input index (Pitfall 4 pattern)"
    - "load_scoring_adapter factory raises SystemExit on unknown adapter_type (fail-fast pattern)"
    - "All data loader paths come from function arguments — zero hardcoded paths in module"

key-files:
  created:
    - shared/data_loader.py
    - shared/scoring_models/zone_touch_v1.json
    - tests/test_data_loader.py
    - tests/test_scoring_adapter_impl.py
  modified:
    - shared/scoring_models/scoring_adapter.py

key-decisions:
  - "Touch file ZRA_Hist_P1.csv has 33 columns (not 32 as stated in plan spec) — test corrected to file ground truth"
  - "parse_instruments_md regex uses 'ticks?' (optional s) to handle both '1 tick' and '3 ticks' formats in instruments.md"
  - "Section boundary regex uses \\n## to stop at any heading level, not just ### — handles ES section ending before 'To Add' h2"
  - "BinnedScoringAdapter.score() returns pd.Series(0.0, index=touch_df.index) for placeholder — correct because all weights={}"
  - "zone_touch_v1.json uses frozen_date='uncalibrated' with empty weights/bin_edges to signal pre-calibration state"

patterns-established:
  - "TDD: test file written first (RED), then implementation (GREEN), then verify all pass"
  - "All adapter test files use MODEL_PATH constant pointing to zone_touch_v1.json for fixture isolation"

requirements-completed: [ENGINE-02, ENGINE-09]

# Metrics
duration: 3min
completed: 2026-03-14
---

# Phase 04 Plan 02: Data Loader and Scoring Adapter Summary

**Parameterized CSV data loading with datetime parsing + scoring adapter factory dispatching BinnedScoringAdapter (placeholder zeros), SklearnScoringAdapter stub, ONNXScoringAdapter stub via string type key**

## Performance

- **Duration:** 3 min
- **Started:** 2026-03-14T04:54:53Z
- **Completed:** 2026-03-14T04:58:14Z
- **Tasks:** 2
- **Files modified:** 5 (4 created, 1 updated)

## Accomplishments
- `shared/data_loader.py` implements load_bars (strips columns, parses datetime, sorts), load_touches, load_data tuple wrapper, and parse_instruments_md regex parser for tick constants
- `shared/scoring_models/scoring_adapter.py` updated with working load_scoring_adapter factory and BinnedScoringAdapter that loads JSON and returns pd.Series(0.0) placeholder scores
- `zone_touch_v1.json` created as uncalibrated placeholder (empty weights/bin_edges, frozen_date="uncalibrated")
- 22 tests pass: 11 for data loader, 11 for scoring adapter

## Task Commits

Each task was committed atomically:

1. **Task 1: Create data_loader.py with tests** - `f0633b2` (feat)
2. **Task 2: Implement scoring adapter factory and BinnedScoringAdapter placeholder** - `09e9824` (feat)

_Note: TDD tasks — tests written first (RED), then implementation (GREEN)_

## Files Created/Modified
- `shared/data_loader.py` - Parameterized bar/touch data loader with instruments.md parser
- `shared/scoring_models/scoring_adapter.py` - Factory + BinnedScoringAdapter implementation (stubs preserved)
- `shared/scoring_models/zone_touch_v1.json` - Uncalibrated placeholder scoring model
- `tests/test_data_loader.py` - 11 tests covering columns, datetime, sorting, instruments parse
- `tests/test_scoring_adapter_impl.py` - 11 tests covering factory dispatch, Series alignment, stub raises

## Decisions Made
- Touch file has 33 columns (not 32 per plan spec) — test corrected to match file ground truth
- `parse_instruments_md` regex uses `ticks?` to handle both "1 tick" (ES) and "3 ticks" (NQ) format variants
- Section boundary regex uses `\n##` (any heading) not `\n###` to correctly stop at `## To Add a New Instrument`
- `BinnedScoringAdapter.score()` returns `pd.Series(0.0, index=touch_df.index)` — correct for all-zero weights placeholder

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Touch file column count corrected from 32 to 33**
- **Found during:** Task 1 (test_load_touches_columns)
- **Issue:** Plan spec stated "32 cols" but actual ZRA_Hist_P1.csv has 33 columns; test would have permanently failed
- **Fix:** Updated test assertion to match verified file ground truth (33 columns with key column name assertions)
- **Files modified:** tests/test_data_loader.py
- **Verification:** test_load_touches_columns passes against actual file
- **Committed in:** f0633b2 (Task 1 commit)

**2. [Rule 1 - Bug] Fixed parse_instruments_md regex for singular "tick" form**
- **Found during:** Task 1 (test_parse_instruments_es)
- **Issue:** Regex matched `ticks` (plural) but ES entry says `1 tick = $12.50` (singular)
- **Fix:** Changed pattern to `ticks?` to handle both singular and plural
- **Files modified:** shared/data_loader.py
- **Verification:** test_parse_instruments_es passes (cost_ticks=1)
- **Committed in:** f0633b2 (Task 1 commit)

**3. [Rule 1 - Bug] Fixed section boundary regex for instruments.md parser**
- **Found during:** Task 1 (test_parse_instruments_es)
- **Issue:** `(?=\n### |\Z)` didn't stop at `## To Add a New Instrument` heading, causing ES section to include the template section text and miss cost_ticks
- **Fix:** Changed to `(?=\n##|\Z)` to stop at any heading level
- **Files modified:** shared/data_loader.py
- **Verification:** test_parse_instruments_es passes
- **Committed in:** f0633b2 (Task 1 commit)

---

**Total deviations:** 3 auto-fixed (all Rule 1 — bugs: wrong assertion + two regex pattern errors)
**Impact on plan:** All three fixes necessary for correctness. No scope creep. Core behavior matches plan intent exactly.

## Issues Encountered
None beyond the three auto-fixed regex/assertion issues above.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- `load_data()` and `load_scoring_adapter()` are ready for the engine to import in Plan 03
- `BinnedScoringAdapter` returns correctly typed pd.Series — engine can call `.score()` without type guards
- `parse_instruments_md` tested for NQ, ES — engine config can pass any registered instrument symbol
- No hardcoded paths anywhere in data_loader.py or scoring_adapter.py

---
*Phase: 04-backtest-engine*
*Completed: 2026-03-14*
