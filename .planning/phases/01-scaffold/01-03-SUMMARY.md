---
phase: 01-scaffold
plan: 03
subsystem: infra
tags: [feature-management, scoring-models, python, json, autoresearch]

# Dependency graph
requires:
  - phase: 01-scaffold plan 02
    provides: _config/ files including data_registry.md which feature_rules.md references for registered sources

provides:
  - shared/feature_definitions.md with entry-time rule and registration template
  - stages/02-features/references/feature_rules.md with 5 autoresearch rules
  - stages/02-features/references/feature_catalog.md with active/dropped/dead-ends tracking
  - shared/scoring_models/_template.json JSON schema for frozen scoring models
  - shared/scoring_models/scoring_adapter.py Protocol + 3 adapter stubs + factory for Phase 4

affects:
  - 02-features (Stage 02 autoresearch reads feature_rules.md and feature_catalog.md before each experiment)
  - phase-4-engine (BinnedScoringAdapter interface consumed by backtest_engine.py)
  - all stages (feature_definitions.md is the registration contract for every new feature)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "ScoringAdapter Protocol with raise NotImplementedError — stubs must raise, not silently succeed (Pitfall 4)"
    - "Feature registration before use — feature_definitions.md as single source of truth"
    - "Frozen scoring model schema — bin_edges and weights in JSON, never modify after frozen_date"

key-files:
  created:
    - shared/feature_definitions.md
    - stages/02-features/references/feature_rules.md
    - stages/02-features/references/feature_catalog.md
    - shared/scoring_models/_template.json
    - shared/scoring_models/scoring_adapter.py
  modified: []

key-decisions:
  - "Adapter stubs raise NotImplementedError rather than pass/return None — enforces Phase 4 implementation, prevents silent failure"
  - "feature_rules.md kept to 15 lines (under 30-line limit) — operative content in first 5 lines per lost-in-middle constraint"
  - "feature_catalog.md has no line limit — it is a reference doc that grows as Stage 02 runs"

patterns-established:
  - "Entry-time computability: stated as PIPELINE RULE 3 in first 5 lines of feature_definitions.md"
  - "Scoring model template: all JSON scoring models follow _template.json schema with model_id, frozen_date, weights, bin_edges"
  - "Adapter protocol: ScoringAdapter Protocol ensures all adapter types expose identical score(touch_df) interface"

requirements-completed: [SCAF-11, SCAF-12, SCAF-13, SCAF-14]

# Metrics
duration: 8min
completed: 2026-03-14
---

# Phase 01 Plan 03: Feature Infrastructure and Scoring Adapter Stubs Summary

**Feature management contracts (entry-time rule, 5 autoresearch rules, 3-table catalog) and BinnedScoringAdapter Protocol with NotImplementedError stubs for Phase 4**

## Performance

- **Duration:** 8 min
- **Started:** 2026-03-14T00:57:30Z
- **Completed:** 2026-03-14T01:05:00Z
- **Tasks:** 2
- **Files modified:** 5

## Accomplishments

- Feature definitions file with entry-time rule at top and empty registration template for Stage 02 autoresearch
- Feature rules and catalog files in stages/02-features/references/ — Stage 02 reads these before each experiment
- Scoring model JSON template schema (model_id, frozen_date, weights, bin_edges) and Python adapter stubs for Phase 4

## Task Commits

Each task was committed atomically:

1. **Task 1: Create feature definitions, rules, and catalog** - `8136685` (feat)
2. **Task 2: Create scoring model template and adapter stubs** - `df7e95a` (feat)

**Plan metadata:** (docs commit — this SUMMARY.md)

## Files Created/Modified

- `shared/feature_definitions.md` - Entry-time rule, empty Registered Features, registration template
- `stages/02-features/references/feature_rules.md` - 5 rules (entry-time, registered sources, keep threshold, one-per-experiment, register-before-use), 15 lines
- `stages/02-features/references/feature_catalog.md` - Active features / Explored and dropped / Dead ends tables
- `shared/scoring_models/_template.json` - Frozen scoring model schema: model_id, frozen_date, max_score, threshold, weights, bin_edges
- `shared/scoring_models/scoring_adapter.py` - ScoringAdapter Protocol + BinnedScoringAdapter + SklearnScoringAdapter + ONNXScoringAdapter + load_scoring_adapter factory

## Decisions Made

- Adapter stubs raise NotImplementedError("Implement in Phase 4") rather than pass or return None. Enforces Phase 4 implementation requirement per Pitfall 4 from research — stubs that silently succeed hide unimplemented behavior.
- feature_rules.md held to 15 lines to respect the lost-in-middle constraint (operative instruction in first 5 lines, total <=30 lines per plan spec).

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Plan 04 (Stage 01 references) can now proceed — data_registry.md source_id pattern already established in Plan 02; feature_definitions.md is ready for Stage 01 references to cross-reference
- Phase 4 engine development unblocked for BinnedScoringAdapter implementation — Protocol and stub are in place
- Stage 02 autoresearch is fully scaffolded: CONTEXT.md (Plan 05), feature_rules.md, feature_catalog.md, and feature_definitions.md are all present

---
*Phase: 01-scaffold*
*Completed: 2026-03-14*
