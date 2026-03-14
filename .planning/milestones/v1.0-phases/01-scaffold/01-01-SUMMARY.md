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
  - "NQ bar data in stages/01-data/data/bar_data/ for P1 and P2"
  - "Touch/signal data in stages/01-data/data/touches/ for P1 and P2"
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
    - "stages/01-data/data/bar_data/NQ_BarData_20250916_20251214.txt (P1 bar data)"
    - "stages/01-data/data/bar_data/NQ_BarData_20251215_20260302.txt (P2 bar data)"
    - "stages/01-data/data/touches/ZRA_Hist_20250916_20251214.csv (P1 touch data)"
    - "stages/01-data/data/touches/ZRA_Hist_20251215_20260302.csv (P2 touch data)"
  modified: []

key-decisions:
  - "Used zone_touch as archetype name per architecture doc convention (shared/archetypes/zone_touch/)"
  - "ICM CONTEXT.md files should stay under 80 lines and contain routing only, not content — matches functional spec intent"
  - "autoresearch keep/revert uses git reset (not branches) for discards — Phase 2-4 driver scripts must mirror this in their experiment tracking"
  - "Bar data format: Date/Time/OHLCV/Trades/BidVol/AskVol tick bars — confirmed valid on spot check"
  - "Touch data format: ZRA_Hist CSV with 32 columns including Reaction, Penetration, ReactionPeakBar — confirmed valid on spot check"

patterns-established:
  - "Pipeline root structure: stages/{01-07}/, _config/, shared/, dashboard/, archive/, audit/"
  - "Each stage: references/, data/ (stage 1 only), output/, autoresearch/current_best/ (stages 2-4)"
  - "Empty dirs preserved via .gitkeep"
  - "Data files named with period suffix: NQ_BarData_{start}_{end}.txt, ZRA_Hist_{start}_{end}.csv"

requirements-completed: [PREREQ-01, PREREQ-02, PREREQ-03, PREREQ-04]

# Metrics
duration: 30min
completed: 2026-03-13
---

# Phase 1 Plan 01: Reference Repos + Directory Scaffold Summary

**ICM and autoresearch repos cloned and reviewed; full 7-stage pipeline directory tree created; NQ bar data and touch/signal data migrated to canonical locations for P1 and P2**

## Performance

- **Duration:** ~30 min (including human-action checkpoint for data migration)
- **Completed:** 2026-03-13
- **Tasks:** 2 of 2 completed
- **Files modified:** 47 (43 .gitkeep stubs + 4 data files)

## Accomplishments

- Cloned RinDig/Interpreted-Context-Methdology repo — reviewed all ICM patterns in CONVENTIONS.md; key pattern for pipeline: stage contracts with Inputs/Process/Outputs tables, selective section routing to keep token cost low
- Cloned karpathy/autoresearch repo — reviewed program.md; key pattern: keep/revert loop using git reset when val_bpb does not improve; phases 2-4 driver scripts must mirror this
- Created full pipeline directory tree (stages/01-07, _config, shared, dashboard, archive, audit) with all canonical subdirectories including data/bar_data, data/touches, data/labels, p2_holdout, output/promoted_hypotheses
- Migrated 4 data files to canonical locations: 2x NQ bar data (P1: 12.4 MB, P2: 9.3 MB) and 2x ZRA touch/signal data (P1: 1.1 MB, P2: 1.0 MB); spot-checked format on all files

## Task Commits

1. **Task 1: Clone reference repos and create pipeline directory structure** - `3540340` (chore)
2. **Task 2: Migrate NQ bar data and touch data** - `75bf9a9` (chore)

**Plan metadata:** pending (docs commit at plan close)

## Files Created/Modified

- `stages/` - Full 7-stage pipeline tree with all canonical subdirs
- `_config/.gitkeep` - Config directory stub
- `shared/archetypes/zone_touch/.gitkeep` - Archetype directory per architecture convention
- `shared/scoring_models/.gitkeep` - Scoring models directory stub
- `dashboard/.gitkeep`, `archive/.gitkeep`, `audit/.gitkeep` - Top-level dirs
- `stages/01-data/data/bar_data/NQ_BarData_20250916_20251214.txt` - P1 NQ bar data (12.4 MB)
- `stages/01-data/data/bar_data/NQ_BarData_20251215_20260302.txt` - P2 NQ bar data (9.3 MB)
- `stages/01-data/data/touches/ZRA_Hist_20250916_20251214.csv` - P1 touch/signal data (1.1 MB)
- `stages/01-data/data/touches/ZRA_Hist_20251215_20260302.csv` - P2 touch/signal data (1.0 MB)

## Decisions Made

- `zone_touch` used as archetype folder name per architecture doc (not `zone-touch` hyphenated)
- ICM keeps CONTEXT.md files under 80 lines, routing-only — this matches what the functional spec describes for stage CONTEXT.md files; no conflict
- autoresearch experiment loop uses `git reset` for discards (not branch switching) — pipeline phases 2-4 must track experiments via results.tsv and reset on regression
- Bar data validated: Date/Time/OHLCV/NumberOfTrades/BidVolume/AskVolume format, tick bars starting 2025-09-16
- Touch data validated: ZRA_Hist CSV with 32 columns including TouchType, Reaction, Penetration, RxnBar_* fields; starts 2025-09-16

## Deviations from Plan

None — both tasks executed exactly as written. Task 2 required a planned checkpoint:human-action which the user completed.

## Next Phase Readiness

- All 4 PREREQ requirements satisfied: repos cloned/reviewed (PREREQ-01, PREREQ-02), bar data migrated (PREREQ-03), touch data migrated (PREREQ-04)
- 01-02 can now begin: CONTEXT.md files, config files, archetype templates, and data_registry can all reference canonical paths

## Self-Check: PASSED

- SUMMARY.md: FOUND
- stages/01-data/data/bar_data/NQ_BarData_20250916_20251214.txt: FOUND
- stages/01-data/data/bar_data/NQ_BarData_20251215_20260302.txt: FOUND
- stages/01-data/data/touches/ZRA_Hist_20250916_20251214.csv: FOUND
- stages/01-data/data/touches/ZRA_Hist_20251215_20260302.csv: FOUND
- Task 1 commit 3540340: FOUND
- Task 2 commit 75bf9a9: FOUND

---
*Phase: 01-scaffold*
*Completed: 2026-03-13*
