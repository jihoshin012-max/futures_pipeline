---
phase: 04-backtest-engine
plan: 01
subsystem: backtest
tags: [backtest-engine, config-schema, simulation-rules, zone-touch, documentation]

# Dependency graph
requires:
  - phase: 03-git-infrastructure
    provides: holdout guard pattern and audit infrastructure the engine doc references
  - phase: 01-scaffold
    provides: exit_templates.md (zone_touch trail mechanics), strategy_archetypes.md (SimResult interface)
provides:
  - backtest_engine_qa.md with Q1-Q6 answers for engine design decisions
  - simulation_rules.md for zone_touch archetype simulator behavior
  - config_schema.json as the contract config for Plan 03 engine implementation
  - config_schema.md with every config field documented and FIXED/CANDIDATE designation
affects: [04-02, 04-03, 04-04, stages/04-backtest autoresearch]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Config JSON contract: all engine fields specified before implementation begins"
    - "FIXED vs CANDIDATE field designation: separates research-variable fields from structural ones"
    - "Trail step validation rules: 5 rules enforced at load time, documented before engine is written"

key-files:
  created:
    - stages/04-backtest/references/backtest_engine_qa.md
    - stages/04-backtest/references/config_schema.json
    - stages/04-backtest/references/config_schema.md
    - shared/archetypes/zone_touch/simulation_rules.md
  modified: []

key-decisions:
  - "Q4 cost_ticks resolution: engine reads from _config/instruments.md at startup — never hardcoded (CLAUDE.md Rule 5)"
  - "Q3 BE trigger: trail_steps[0] with new_stop_ticks=0 is the BE trigger — no separate be_trigger_ticks field"
  - "Q5 holdout guard: dual-condition (flag file + case-insensitive p2 in path) — cannot be bypassed by config"
  - "Q1 data loading: engine takes explicit path strings from config JSON, never reads data_manifest.json"
  - "Trail step validation: 5 rules (count 0-6, monotonic triggers, stop<trigger, non-decreasing stops, non-negative first stop)"
  - "Cost model: individual trade pnl_ticks is raw; cost_ticks applied during metrics aggregation only"

patterns-established:
  - "Pattern 1: FIXED/CANDIDATE designation — separates structural config from autoresearch candidate fields"
  - "Pattern 2: Trail step validation at config load time — abort before simulation, never mid-run"
  - "Pattern 3: simulation_rules.md as archetype contract — one file per archetype describing all simulator behaviors"

requirements-completed: [ENGINE-01, ENGINE-04, ENGINE-05, ENGINE-08]

# Metrics
duration: 8min
completed: 2026-03-14
---

# Phase 04 Plan 01: Backtest Engine Reference Documents Summary

**Four reference documents establishing the engine config contract, Q&A decisions, and zone_touch simulator behavior rules using the exact structure from the architecture spec and RESEARCH.md**

## Performance

- **Duration:** ~8 min
- **Started:** 2026-03-14T04:56:00Z
- **Completed:** 2026-03-14T05:04:00Z
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments
- `backtest_engine_qa.md`: All six Q&A sections (Q1-Q6) with non-empty answers — data path resolution, BinnedScoringAdapter behavior, BE trigger, cost_ticks resolution, holdout guard logic, and output schema
- `simulation_rules.md`: zone_touch simulator behavior reference covering entry mechanics, multi-leg vs single-leg exits, trail ratchet mechanics, time cap, cost model (raw pnl vs net aggregation), and SimResult pure-function contract
- `config_schema.json`: Valid reference config with all required fields — M1 mode with 4-step trail, archetype block, routing block, explicit file paths
- `config_schema.md`: Field-by-field documentation table with FIXED/CANDIDATE designation for every key plus 5 trail step validation rules

## Task Commits

Each task was committed atomically:

1. **Task 1: Write backtest_engine_qa.md and simulation_rules.md** - `c1eccdb` (feat)
2. **Task 2: Write config_schema.json and config_schema.md** - `3c1eb94` (feat)

## Files Created/Modified
- `stages/04-backtest/references/backtest_engine_qa.md` - Q1-Q6 design decisions for engine implementation
- `stages/04-backtest/references/config_schema.json` - Reference config; Plan 03 validate_config() is implemented against this contract
- `stages/04-backtest/references/config_schema.md` - FIXED/CANDIDATE field docs with trail step validation rules
- `shared/archetypes/zone_touch/simulation_rules.md` - Simulator behavior reference for zone_touch archetype

## Decisions Made
- `cost_ticks` stays out of config JSON entirely — engine reads from `_config/instruments.md` at startup using `config.instrument` lookup (CLAUDE.md Rule 5 compliance)
- `trail_steps` empty list (`[]`) is valid for modes without trailing stops (M3 single-leg pattern)
- Individual trade `pnl_ticks` in `SimResult` is raw; cost deducted only during metrics aggregation — this preserves trade-level data integrity for analysis
- `simulation_rules.md` uses `# archetype: zone_touch` on line 1 per CLAUDE.md conventions for archetype-specific files

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- All four prerequisites for Plan 03 (engine implementation) and Plan 04 (end-to-end verification) are now on disk
- `config_schema.json` provides the exact contract that `validate_config()` must enforce
- `simulation_rules.md` provides the behavior spec the zone_touch simulator must implement
- Plan 02 (data_loader.py) can proceed in parallel — no dependency on these docs

---
*Phase: 04-backtest-engine*
*Completed: 2026-03-14*
