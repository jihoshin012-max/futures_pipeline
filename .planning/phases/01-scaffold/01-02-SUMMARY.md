---
phase: 01-scaffold
plan: 02
subsystem: infra
tags: [pipeline, config, scaffold, instruments, period-config, statistical-gates, regime]

# Dependency graph
requires:
  - phase: 01-scaffold plan 01
    provides: Directory structure, data files, reference repos cloned
provides:
  - CLAUDE.md with five pipeline rules and hard prohibitions
  - CONTEXT.md routing file with stage status table
  - _config/period_config.md with P1/P2 periods and P1a/P1b replication split (STATE.md blocker cleared)
  - _config/instruments.md with NQ/ES/GC registered (tick size, cost model, session times)
  - _config/data_registry.md with bar_data and zone_csv_v2 registered
  - _config/pipeline_rules.md with all 5 rules including Rule 4 grandfathering
  - _config/statistical_gates.md with verdict thresholds, iteration budgets, Bonferroni gates
  - _config/regime_definitions.md with 3 regime dimensions and Stage 05 usage rules
  - _config/context_review_protocol.md with file length limits and front-loading rules
affects:
  - All downstream phases (every stage reads _config/)
  - Phase 02 (HMM): instruments.md for NQ tick size; period_config.md for P1 dates
  - Phase 03 (engine): statistical_gates.md for verdict thresholds; pipeline_rules.md for holdout enforcement
  - Phase 04 (autoresearch): all _config files are single sources of truth

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "ICM CONTEXT.md pattern: front-matter staleness flag + operative instruction in first 5 lines"
    - "Lost-in-middle authoring: file length limits enforced at 60/80/30 lines"
    - "Single source of truth: _config/ files only — no hardcoded constants anywhere else"
    - "Instrument constants registry pattern: all tick size/cost model values must come from instruments.md"
    - "source_id naming: matches schema file name in 01-data/references/{source_id}_schema.md"

key-files:
  created:
    - CLAUDE.md
    - CONTEXT.md
    - _config/period_config.md
    - _config/instruments.md
    - _config/data_registry.md
    - _config/pipeline_rules.md
    - _config/statistical_gates.md
    - _config/regime_definitions.md
    - _config/context_review_protocol.md
  modified: []

key-decisions:
  - "zone_csv_v2 used as source_id for ZRA touch data (matches architecture doc; files on disk use ZRA_Hist_*.csv prefix)"
  - "period_config.md committed in Task 1 before any evaluation file — STATE.md P1a/P1b blocker cleared"
  - "data_registry.md registers zone_csv_v2 source; corresponding schema file (zone_csv_v2_schema.md) must be created in Plan 04 (Stage 01 references)"

patterns-established:
  - "Five pipeline rules: P1 Calibrate, P2 One-Shot, Entry-Time Only, Internal Replication, Instrument Constants from Registry"
  - "Rule 4 grandfathering: M1_A is grandfathered; all new hypotheses require P1a/P1b replication before P2"
  - "Iteration budgets: Stage 02 = 300, Stage 03 = 200, Stage 04 = 500 (Bonferroni gates tighten as n_prior_tests grows)"

requirements-completed: [SCAF-01, SCAF-02, SCAF-03, SCAF-04, SCAF-05, SCAF-06, SCAF-07, SCAF-08, SCAF-09, SCAF-10]

# Metrics
duration: 3min
completed: 2026-03-13
---

# Phase 1 Plan 2: Root Config Foundation Summary

**Nine pipeline foundation files — CLAUDE.md, root CONTEXT.md, and all 7 _config/ files — with period P1a/P1b split committed before any evaluation file exists**

## Performance

- **Duration:** 3 min
- **Started:** 2026-03-14T00:52:00Z
- **Completed:** 2026-03-14T00:55:00Z
- **Tasks:** 2
- **Files created:** 9

## Accomplishments
- Created CLAUDE.md (31 lines) with five pipeline rules in first 20 lines and hard prohibitions section — agent identity file for all downstream stages
- Created root CONTEXT.md (29 lines) routing file with Stage 01 as active stage, stage status table, and human checkpoints
- Created _config/period_config.md with P1/P2 dates, P1a/P1b replication split, rolling-forward instructions, and grandfathering note — STATE.md blocker cleared
- Created all 6 remaining _config/ files: instruments.md (NQ/ES/GC), data_registry.md (bar_data + zone_csv_v2), pipeline_rules.md (5 rules), statistical_gates.md (verdict thresholds + Bonferroni gates), regime_definitions.md (3 dimensions), context_review_protocol.md (lost-in-middle mitigations)

## Task Commits

Each task was committed atomically:

1. **Task 1: Create root structure, CLAUDE.md, CONTEXT.md, and period_config.md** - `f4a08f6` (feat)
2. **Task 2: Create all remaining _config/ files** - `6412ab1` (feat)

**Plan metadata:** (docs commit — see state update)

## Files Created/Modified
- `CLAUDE.md` - Agent identity, five pipeline rules, hard prohibitions, stage routing, autoresearch rule
- `CONTEXT.md` - Pipeline router, active stage indicator, stage status table, human checkpoints
- `_config/period_config.md` - IS/OOS period boundaries, P1a=2025-09-16/2025-10-31, P1b=2025-11-01/2025-12-14, rolling-forward instructions
- `_config/instruments.md` - NQ (tick 0.25, $5, cost 3t), ES (tick 0.25, $12.50, cost 1t), GC (tick 0.10, $10, cost 2t)
- `_config/data_registry.md` - bar_data (price, NQ_BarData_*.txt) and zone_csv_v2 (touches, ZRA_Hist_*.csv) registered
- `_config/pipeline_rules.md` - All 5 rules with Rule 4 grandfathering note for M1_A
- `_config/statistical_gates.md` - PF/trades/MWU/permutation/percentile/drawdown thresholds; budgets 300/200/500; Bonferroni gates (4 rows)
- `_config/regime_definitions.md` - Trend (ADX), Volatility (ATR relative), Macro (event/normal); Stage 05 usage rules
- `_config/context_review_protocol.md` - File length limits, front-loading rule, local repetition rule, staleness flag, review checklist

## Decisions Made
- Used `zone_csv_v2` as the source_id for ZRA touch data, matching the architecture doc which lists it as the zone_touch archetype's required data source. Files on disk use `ZRA_Hist_*.csv` prefix — the file_pattern column in data_registry.md reflects the actual file pattern.
- period_config.md was committed as the first task in this plan, satisfying the STATE.md blocker that required P1a/P1b split to be in version control before any Stage 04 evaluation file exists.
- data_registry.md notes that zone_csv_v2_schema.md must be created in Plan 04 (Stage 01 references task). The source_id string in the registry must exactly match the schema filename.

## Deviations from Plan

None — plan executed exactly as written.

## Issues Encountered
None.

## Next Phase Readiness
- All _config/ foundation files are in place; every downstream stage can now read instrument constants, period boundaries, pipeline rules, and statistical gate thresholds from canonical locations
- STATE.md blocker cleared: period_config.md with P1a/P1b split is committed before any evaluation file
- Plan 03 (shared/ files: feature_definitions.md, scoring model template) and Plan 04 (stage CONTEXT.md files) can now proceed
- Remaining blocker from STATE.md: zone_csv_v2_schema.md must be created in Plan 04 to complete the data_registry.md contract

---
*Phase: 01-scaffold*
*Completed: 2026-03-13*
