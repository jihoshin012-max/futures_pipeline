---
phase: 01-scaffold
plan: 05
subsystem: scaffold
tags: [stage-contracts, statistical-assessment, deployment, live-monitoring, bash, ACSIL]

# Dependency graph
requires:
  - phase: 01-scaffold plan 02
    provides: _config/statistical_gates.md with verdict thresholds and Bonferroni gates
provides:
  - Stage 05 assessment contract with deterministic verdict logic
  - Stage 06 deployment builder contract with assemble_context.sh
  - Stage 07 live monitoring contract with review triggers
  - verdict_criteria.md thresholds matching statistical_gates.md
  - statistical_tests.md specs for MWU, permutation, and random percentile rank
  - context_package_spec.md 5-section ACSIL generation spec
  - assemble_context.sh reading archetype from frozen_params.json at runtime
  - review_triggers.md with 4 active trigger thresholds and escalation rules
affects: [02-hmm, 04-engine, phases using Stage 05 assessment verdicts]

# Tech tracking
tech-stack:
  added: [bash script for context assembly]
  patterns:
    - Stage CONTEXT.md files <=80 lines with operative instruction in first 5 lines
    - Reference files separate from CONTEXT.md for threshold tables that may expand
    - Archetype resolved at runtime from frozen_params.json — never hardcoded in scripts

key-files:
  created:
    - stages/05-assessment/CONTEXT.md
    - stages/05-assessment/references/verdict_criteria.md
    - stages/05-assessment/references/statistical_tests.md
    - stages/06-deployment/CONTEXT.md
    - stages/06-deployment/references/context_package_spec.md
    - stages/06-deployment/assemble_context.sh
    - stages/07-live/CONTEXT.md
    - stages/07-live/triggers/review_triggers.md
  modified: []

key-decisions:
  - "verdict_criteria.md is a local copy for agent access; source of truth remains _config/statistical_gates.md"
  - "assemble_context.sh reads archetype from frozen_params.json at runtime, not hardcoded (Pitfall 6 prevention)"
  - "Stage 07 review triggers kept in separate file to allow threshold expansion without exceeding CONTEXT.md 80-line limit"
  - "Sharpe ratio is a reporting metric only — not a verdict gate — consistent with statistical_gates.md design"

patterns-established:
  - "Threshold files reference source of truth and label themselves as local copies"
  - "Scripts derive all strategy-specific values from frozen_params.json, not from file/folder names"
  - "Human gate stages (06, 07) use explicit checklists with unchecked boxes that human must complete"

requirements-completed: [SCAF-19, SCAF-20, SCAF-21]

# Metrics
duration: 2min
completed: 2026-03-14
---

# Phase 1 Plan 05: Stage 05-07 CONTEXT.md and Supporting Files Summary

**Stage contracts for statistical assessment (deterministic verdict with MWU + permutation + percentile), deployment builder (context assembly + human gate), and live monitor (trigger-based review) — 8 files across 3 stages**

## Performance

- **Duration:** 2 min
- **Started:** 2026-03-14T00:57:56Z
- **Completed:** 2026-03-14T01:00:07Z
- **Tasks:** 2
- **Files modified:** 8

## Accomplishments
- Stage 05 CONTEXT.md with deterministic assessment contract: I/O table, multiple testing section, statistical_summary output spec distinguishing verdict metrics from reporting metrics
- Stage 05 reference files: verdict_criteria.md with YES/CONDITIONAL/NO thresholds mirroring statistical_gates.md, plus Bonferroni adjustment table; statistical_tests.md specifying all 3 required tests
- Stage 06 CONTEXT.md with deployment builder contract, 7-item human deployment checklist, and clear "what this stage is" section
- Stage 06 supporting files: context_package_spec.md with 5 ordered sections and "what NOT to include" guardrails; assemble_context.sh assembling 6 sections with runtime archetype resolution
- Stage 07 CONTEXT.md monitor-only contract referencing external triggers file
- review_triggers.md with 4 active triggers (PF divergence, consecutive stop-outs, drawdown, trade count), escalation rules, and IS promotion milestone trigger

## Task Commits

Each task was committed atomically:

1. **Task 1: Create Stage 05 CONTEXT.md and reference files** - `49e8be1` (feat)
2. **Task 2: Create Stage 06-07 CONTEXT.md files and supporting files** - `7d7e2c2` (feat)

**Plan metadata:** (docs commit — see below)

## Files Created/Modified
- `stages/05-assessment/CONTEXT.md` - Deterministic assessment contract with multiple testing controls and statistical_summary output spec
- `stages/05-assessment/references/verdict_criteria.md` - YES/CONDITIONAL/NO verdict thresholds, Bonferroni adjustment table, local copy of statistical_gates.md
- `stages/05-assessment/references/statistical_tests.md` - MWU, permutation test, and random percentile rank specifications
- `stages/06-deployment/CONTEXT.md` - Deployment builder contract with 7-item human checklist
- `stages/06-deployment/references/context_package_spec.md` - 5-section ACSIL generation context spec with what-not-to-include guardrails
- `stages/06-deployment/assemble_context.sh` - Context assembly script reading archetype from frozen_params.json at runtime
- `stages/07-live/CONTEXT.md` - Monitor-only contract with review triggers reference and IS promotion trigger
- `stages/07-live/triggers/review_triggers.md` - 4 active trigger thresholds, escalation rules, promotion milestone

## Decisions Made
- verdict_criteria.md labeled as local copy with source-of-truth pointer to _config/statistical_gates.md — prevents drift if gates change
- assemble_context.sh resolves ARCHETYPE from frozen_params.json at runtime (avoids Pitfall 6: hardcoded archetype names)
- Triggers separated into triggers/review_triggers.md so Stage 07 CONTEXT.md stays under 80 lines as the trigger table grows
- Sharpe ratio placed in "reporting metrics" block in statistical_summary output spec, not a verdict gate

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None.

## Next Phase Readiness
- All 3 stage CONTEXT.md files under 80 lines with front matter and operative instruction in first 5 lines
- Stage 05 verdict logic directly traceable to statistical_gates.md
- Stage 06 assemble_context.sh executable and ready to use when pipeline reaches assessment stage
- Stage 07 review triggers file expandable without touching CONTEXT.md

---
*Phase: 01-scaffold*
*Completed: 2026-03-14*
