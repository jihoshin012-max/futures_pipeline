---
phase: 01-rotational-simulator-baseline
plan: 03
subsystem: simulation
tags: [rotational, parameter-sweep, baseline, pandas, numpy, json, tsv]

# Dependency graph
requires:
  - phase: 01-01
    provides: RotationalSimulator class with run() -> SimulationResult (trades, cycles, bars_processed)
  - phase: 01-01
    provides: rotational_engine.py with compute_cycle_metrics()

provides:
  - run_sweep.py: parameter sweep runner (StepDist 1.0-6.0, step 0.5, all 3 bar types, P1a)
  - sweep_P1a.json: full sweep results for all 33 StepDist x bar_type combinations
  - sweep_P1a.tsv: human-readable flat sweep summary (33 rows + header)
  - Per-bar-type optimized baselines: all 3 bar types best at StepDist=6.0 on P1a

affects:
  - Phase C (hypothesis research — hypotheses must beat these per-bar-type baselines)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - Load bar data once per bar type, reuse across all StepDist values (sweep efficiency)
    - Deep-copy config template per simulation (avoids mutation side effects)
    - Dual output format: JSON for machine consumption, TSV for human review
    - Best-per-source selection: highest cycle_pf, pnl tiebreaker for inf values

key-files:
  created:
    - shared/archetypes/rotational/run_sweep.py
    - shared/archetypes/rotational/baseline_results/sweep_P1a.json
    - shared/archetypes/rotational/baseline_results/sweep_P1a.tsv
  modified:
    - shared/archetypes/rotational/rotational_simulator.py (fix fractional seconds in Time parser)

key-decisions:
  - "All 3 bar types peak at StepDist=6.0 for cycle_pf on P1a — sweep topped out at upper bound; Phase C hypotheses must beat these baselines"
  - "10-sec bar Time column format is 'HH:MM:SS.ffffff' — fixed _parse_time to use int(float(parts[2])) not int(parts[2])"
  - "bars_processed after P1a+RTH filtering: vol=52028, tick=47837, 10sec=70200 — consistent across all StepDist values as expected"

patterns-established:
  - "Pattern: Sweep runner loads data once, deep-copies config per iteration — O(n_data) not O(n_sim * n_data)"
  - "Pattern: Per-bar-type optimized baseline = best StepDist by cycle_pf; stored in best_per_source for downstream use"

requirements-completed: [ROT-SIM-07]

# Metrics
duration: 10min
completed: 2026-03-15
---

# Phase 1 Plan 03: Parameter Sweep — StepDist 1.0-6.0 on P1a Summary

**Fixed-step parameter sweep (StepDist 1.0-6.0, step 0.5) across all 3 bar types on P1a, producing sweep_P1a.json and sweep_P1a.tsv with per-bar-type optimized baselines (all peak at StepDist=6.0)**

## Performance

- **Duration:** 10 min (including 5.5 min sweep runtime for 33 simulations)
- **Started:** 2026-03-15T21:32:10Z
- **Completed:** 2026-03-15T21:42:10Z
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments

- Built `run_sweep.py` (302 lines): loads bar data once per type, deep-copies config per iteration, runs 33 simulations (11 StepDist x 3 bar types), selects best-per-source, writes JSON and TSV outputs
- Executed full sweep in ~5.5 minutes; n_cycles monotonically decreasing as StepDist increases (verified), bars_processed identical per bar type across all StepDist values (verified)
- Per-bar-type optimized baselines: vol PF=0.6714 (StepDist=6.0), tick PF=0.7339 (StepDist=6.0), 10sec PF=0.755 (StepDist=6.0) — all cycle_pf values are sub-1.0, showing baseline is unprofitable as expected for unoptimized parameters
- Fixed fractional seconds bug in `rotational_simulator.py` `_parse_time` — 10-sec bar Time format is `HH:MM:SS.ffffff`, which `int(parts[2])` cannot parse; fixed with `int(float(parts[2]))`

## Task Commits

Each task was committed atomically:

1. **Task 1: Build parameter sweep runner script** - `cc319f2` (feat)
2. **Task 2: Execute parameter sweep on P1a and capture results** - `3506eaa` (feat)

## Files Created/Modified

- `shared/archetypes/rotational/run_sweep.py` — Sweep runner: loads data once, iterates 11 StepDist x 3 bar types, writes JSON + TSV (302 lines)
- `shared/archetypes/rotational/baseline_results/sweep_P1a.json` — Full 33-combination sweep results with best_per_source section
- `shared/archetypes/rotational/baseline_results/sweep_P1a.tsv` — Human-readable flat table (33 rows + header)
- `shared/archetypes/rotational/rotational_simulator.py` — 1-line fix: fractional seconds in `_parse_time`

## Decisions Made

- Best StepDist peaks at 6.0 for all 3 bar types — the sweep hit the upper bound. This means Phase C hypotheses must improve on these sub-optimal baselines. The result is expected: a raw reversal state machine without hypothesis signal is structurally unprofitable.
- Sweep runtime ~5.5 min is acceptable; no parallelization needed at this scale.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed fractional seconds parsing in rotational_simulator.py**
- **Found during:** Task 2 (Execute parameter sweep)
- **Issue:** `_parse_time` in `_filter_bars` used `int(parts[2])` on the Time column of 10-sec bars; the format is `HH:MM:SS.ffffff` so `parts[2]` is `"00.000000"`, which raises `ValueError: invalid literal for int()`
- **Fix:** Changed to `int(float(parts[2]))` to first parse as float (handling fractional seconds), then truncate to int
- **Files modified:** `shared/archetypes/rotational/rotational_simulator.py` (line 400)
- **Verification:** Sweep ran to completion; all 46 existing unit tests still pass
- **Committed in:** `3506eaa` (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (1 bug)
**Impact on plan:** Required fix — sweep was blocked without it. No scope creep. Simulator fix improves correctness for production use.

## Issues Encountered

The 10-sec bar Time format (`HH:MM:SS.ffffff`) was not handled by `_parse_time`. Fixed inline per Rule 1. All unit tests remained green after the fix.

## User Setup Required

None — no external service configuration required.

## Next Phase Readiness

- Per-bar-type optimized baselines established and stored in `baseline_results/sweep_P1a.json`
- `best_per_source` section identifies StepDist=6.0 as best for all 3 bar types on P1a
- Phase C hypothesis research can now compare against these baselines using the same simulator
- `run_sweep.py` can be reused for Phase C hypothesis sweeps with minimal modification
- Phase 1 (Rotational Simulator & Baseline) is now complete: all 3 plans executed

---
*Phase: 01-rotational-simulator-baseline*
*Completed: 2026-03-15*
