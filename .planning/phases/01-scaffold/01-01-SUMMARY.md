---
phase: 01-scaffold
plan: 01
subsystem: infra
tags: [git, directory-structure, ICM, autoresearch, NQ-data]

# Dependency graph
requires: []
provides:
  - "Full pipeline directory tree: stages/01-data through 07-live with canonical subdirs"
  - "ICM repo (../Interpreted-Context-Methdology/) cloned and conventions reviewed"
  - "autoresearch repo (../autoresearch/) cloned and keep/revert loop pattern understood"
  - "Canonical data paths created: stages/01-data/data/{bar_data,touches,labels}/"
affects: [01-02, 01-03, 01-04, 01-05, 01-06]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "ICM 5-layer routing: CLAUDE.md > CONTEXT.md > stage CONTEXT.md > references > artifacts"
    - "ICM stage contract shape: Inputs table / Process steps / Outputs table"
    - "ICM one-way cross-references: downstream points upstream, never reverse"
    - "autoresearch keep/revert loop: commit -> run -> log val_bpb -> keep if improved else git reset"

key-files:
  created:
    - "stages/ (full tree with .gitkeep stubs)"
    - "_config/.gitkeep"
    - "shared/archetypes/zone_touch/.gitkeep"
    - "shared/scoring_models/.gitkeep"
    - "dashboard/.gitkeep"
    - "archive/.gitkeep"
    - "audit/.gitkeep"
  modified: []

key-decisions:
  - "Used zone_touch as archetype name per architecture doc convention (shared/archetypes/zone_touch/)"
  - "ICM CONTEXT.md files should stay under 80 lines and contain routing only, not content — matches functional spec intent"
  - "autoresearch keep/revert uses git reset (not branches) for discards — Phase 2-4 driver scripts must mirror this in their experiment tracking"
  - "Data migration (Task 2) requires human action — source paths known only to user; canonical destinations are stages/01-data/data/bar_data/ and stages/01-data/data/touches/"

patterns-established:
  - "Pipeline root structure: stages/{01-07}/, _config/, shared/, dashboard/, archive/, audit/"
  - "Each stage: references/, data/ (stage 1 only), output/, autoresearch/current_best/ (stages 2-4)"
  - "Empty dirs preserved via .gitkeep"

requirements-completed: [PREREQ-01, PREREQ-02]

# Metrics
duration: 15min
completed: 2026-03-14
---

# Phase 1 Plan 01: Reference Repos + Directory Scaffold Summary

**ICM and autoresearch repos cloned, reviewed for conventions; full 7-stage pipeline directory tree created with .gitkeep stubs; data migration to canonical paths pending user action**

## Performance

- **Duration:** ~15 min
- **Started:** 2026-03-14T00:31:54Z
- **Completed:** 2026-03-14T00:46:00Z
- **Tasks:** 1 of 2 completed (Task 2 is checkpoint:human-action)
- **Files modified:** 43 (.gitkeep stubs)

## Accomplishments
- Cloned RinDig/Interpreted-Context-Methdology repo — reviewed all 15 ICM patterns in CONVENTIONS.md; key pattern for pipeline: stage contracts with Inputs/Process/Outputs tables, selective section routing to keep token cost low
- Cloned karpathy/autoresearch repo — reviewed program.md; key pattern: keep/revert loop using git reset when val_bpb does not improve; phases 2-4 driver scripts must mirror this
- Created full pipeline directory tree (stages/01-07, _config, shared, dashboard, archive, audit) with all canonical subdirectories including data/bar_data, data/touches, data/labels, p2_holdout, output/promoted_hypotheses

## Task Commits

1. **Task 1: Clone reference repos and create pipeline directory structure** - `3540340` (chore)

**Plan metadata:** pending (docs commit at plan close)

## Files Created/Modified
- `stages/` - Full 7-stage pipeline tree with all canonical subdirs
- `_config/.gitkeep` - Config directory stub
- `shared/archetypes/zone_touch/.gitkeep` - Archetype directory per architecture convention
- `shared/scoring_models/.gitkeep` - Scoring models directory stub
- `dashboard/.gitkeep`, `archive/.gitkeep`, `audit/.gitkeep` - Top-level dirs

## Decisions Made
- `zone_touch` used as archetype folder name per architecture doc (not `zone-touch` hyphenated)
- ICM keeps CONTEXT.md files under 80 lines, routing-only — this matches what the functional spec describes for stage CONTEXT.md files; no conflict
- autoresearch experiment loop uses `git reset` for discards (not branch switching) — pipeline phases 2-4 must track experiments via results.tsv and reset on regression

## Deviations from Plan

None — Task 1 executed exactly as written. Task 2 is a planned checkpoint:human-action.

## User Setup Required

**Task 2 (data migration) requires manual action before continuing to plan 01-02.**

Steps:
1. Copy NQ bar data files (pattern: `NQ_BarData_*.txt`) for P1 and P2 into `stages/01-data/data/bar_data/`
2. Copy touch/signal data files for P1 and P2 into `stages/01-data/data/touches/`
3. If derived label files exist, copy them to `stages/01-data/data/labels/`

Verify both directories contain files:
```
ls stages/01-data/data/bar_data/
ls stages/01-data/data/touches/
```

Both should show files covering P1 (2025-09-16 to 2025-12-14) and P2 (2025-12-15 to 2026-03-02).

After migration is complete, PREREQ-03 and PREREQ-04 will be satisfied and 01-02 can begin.

## Next Phase Readiness
- Directory scaffold complete — 01-02 can begin creating CONTEXT.md and config files once data is migrated
- PREREQ-01 (ICM cloned/reviewed) and PREREQ-02 (autoresearch cloned/reviewed) satisfied
- PREREQ-03 (bar data in place) and PREREQ-04 (touch data in place) blocked on Task 2 human action

---
*Phase: 01-scaffold*
*Completed: 2026-03-14*
