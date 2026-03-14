---
phase: quick-2
plan: 01
subsystem: data-pipeline
tags: [data-registry, validation, rotational, archetype-skeleton]
dependency_graph:
  requires: [quick-1]
  provides: [rotational-data-registered, validate-registry-aware, rotational-archetype-skeleton]
  affects: [stages/01-data, stages/02-features, stages/04-backtest, shared/archetypes/rotational]
tech_stack:
  added: []
  patterns: [registry-driven validation, archetype skeleton]
key_files:
  created:
    - stages/01-data/references/bar_data_rot_schema.md
    - shared/archetypes/rotational/simulation_rules.md
    - shared/archetypes/rotational/feature_engine.py
  modified:
    - _config/data_registry.md
    - stages/01-data/validate.py
    - stages/01-data/output/data_manifest.json
    - stages/01-data/output/validation_report.md
decisions:
  - "Tick rotational files (NQ_BarData_250tick_rot_*.csv) live in stages/01-data/data/bar_data/tick/ subdirectory, not volume/"
  - "zone_touch required_data in strategy_archetypes.md uses display names not registry IDs — benign pre-existing mismatch; zone_touch downstream consumers use flat periods.P1.sources"
  - "bar_data_volume and zone_csv_v2 date parsing returns None (different date format from rotational CSVs) — date coverage check is warnings-only, so no regression"
  - "Rotational sources aggregated across P1+P2 in manifest sources dict; path is a list when multiple files match"
metrics:
  duration_minutes: 20
  completed_date: "2026-03-14"
  tasks_completed: 2
  files_changed: 7
---

# Quick Task 2: Onboard Rotational Data Files, Registry, and Skeleton — Summary

**One-liner:** Two rotational bar data sources registered in data_registry.md with 35-column schema doc, validate.py upgraded to registry-aware file/column/date validation, and rotational archetype skeleton created.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Registry entries and schema documentation | 1527415 | _config/data_registry.md, stages/01-data/references/bar_data_rot_schema.md |
| 2 | Upgrade validate.py + archetype skeleton | 954c253 | stages/01-data/validate.py, shared/archetypes/rotational/*, stages/01-data/output/* |

## What Was Built

### Task 1: Registry + Schema

- Added `bar_data_250vol_rot` and `bar_data_250tick_rot` to `_config/data_registry.md` with period boundaries (P1 starts 2025-09-21, P2 ends 2026-03-13)
- Created `stages/01-data/references/bar_data_rot_schema.md` documenting all 35 columns with index-based disambiguation for the 4×3=12 duplicate column names (Top, Bottom, Top MovAvg, Bottom MovAvg repeated across 3 channel/band studies)

### Task 2: Validate.py + Skeleton

**validate.py additions (fully additive, existing functionality preserved):**
- `parse_data_registry(path)` — parses pipe-delimited Registered Sources table from _config/data_registry.md
- `validate_registry_sources()` — for each P1/P2 registry source: glob for matching files, check required columns (Date, Time, Open, High, Low, Last, Volume), check date coverage (warnings only), collect rows and date_range
- `build_manifest()` extended — accepts `registry` and `registry_found_files`; populates `archetypes.{arch}.sources` dict with path/rows/date_range for each required source ID from strategy_archetypes.md

**Rotational archetype skeleton:**
- `shared/archetypes/rotational/simulation_rules.md` — bar-only stub; entry/exit TBD in Stage 03
- `shared/archetypes/rotational/feature_engine.py` — `# archetype: rotational` on line 1, imports `parse_instruments_md`, caches `_NQ_CONSTANTS` and `_TICK_SIZE`, empty `compute_features(bar_df)` stub

## Verification Results

```
Status: PASS
FOUND bar_data_250vol_rot [P1]: 138704 rows, 2025-09-21 to 2025-12-14
FOUND bar_data_250vol_rot [P2]: 131709 rows, 2025-12-15 to 2026-03-13
FOUND bar_data_250tick_rot [P1]: 127567 rows, 2025-09-21 to 2025-12-14
FOUND bar_data_250tick_rot [P2]: 121595 rows, 2025-12-15 to 2026-03-13
```

Manifest `archetypes.rotational.sources`:
- `bar_data_250vol_rot`: 270,413 total rows, 2025-09-21 to 2026-03-13
- `bar_data_250tick_rot`: 249,162 total rows, 2025-09-21 to 2026-03-13

## Deviations from Plan

### Discovery: Tick files are in a separate subdirectory

**Found during:** Task 2
**Issue:** The plan assumed all rotational files were in `stages/01-data/data/bar_data/volume/`. The tick files (NQ_BarData_250tick_rot_P1.csv, NQ_BarData_250tick_rot_P2.csv) are actually in `stages/01-data/data/bar_data/tick/`.
**Fix:** `validate_registry_sources()` uses `data_dir.rglob(file_pattern)` (recursive glob), so it finds files in any subdirectory automatically. No special handling needed.
**Impact:** None — both sources validate and appear correctly in manifest.

## Self-Check: PASSED

Files exist:
- FOUND: C:/Projects/pipeline/_config/data_registry.md (modified)
- FOUND: C:/Projects/pipeline/stages/01-data/references/bar_data_rot_schema.md
- FOUND: C:/Projects/pipeline/stages/01-data/validate.py (modified)
- FOUND: C:/Projects/pipeline/shared/archetypes/rotational/simulation_rules.md
- FOUND: C:/Projects/pipeline/shared/archetypes/rotational/feature_engine.py

Commits exist:
- 1527415: feat(quick-2-01): register rotational bar data sources and document 35-col schema
- 954c253: feat(quick-2-02): registry-aware validate.py and rotational archetype skeleton
