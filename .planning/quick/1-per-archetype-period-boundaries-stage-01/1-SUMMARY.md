---
phase: quick
plan: 1
subsystem: stage-01-data
tags: [period-config, data-manifest, archetypes, zone_touch, rotational]
dependency_graph:
  requires: []
  provides: [per-archetype-periods, data-manifest-archetypes-key]
  affects: [stages/03-hypothesis, stages/04-backtest, feature_evaluator]
tech_stack:
  added: []
  patterns: [markdown-table-parsing, stdlib-only-python]
key_files:
  created:
    - stages/01-data/validate.py
    - stages/01-data/output/data_manifest.json
    - stages/01-data/output/validation_report.md
  modified:
    - _config/period_config.md
    - stages/03-hypothesis/references/strategy_archetypes.md
    - stages/01-data/references/data_manifest_schema.md
decisions:
  - "Midpoint split uses ceiling division — (end-start).days+1)//2 offset — so both archetypes match pre-existing config comment dates exactly"
  - "Flat periods structure retained using zone_touch dates as backwards-compatible alias for downstream consumers"
  - "Simulator Interface Contract section excluded from archetype parser via explicit skip-list to avoid spurious warnings"
metrics:
  duration: ~12min
  completed_date: "2026-03-14"
  tasks_completed: 2
  files_changed: 6
---

# Quick Task 1: Per-Archetype Period Boundaries (Stage 01) Summary

One-liner: Added archetype column to period_config.md and a new validate.py that generates per-archetype P1/P2/P1a/P1b boundaries in data_manifest.json while retaining backwards-compatible flat periods.

## What Was Built

Zone_touch and rotational archetypes have different IS/OOS date boundaries. The pipeline previously stored a flat period table that could not represent this. This task:

1. Extended `_config/period_config.md` with an `archetype` column and four rows (zone_touch P1/P2, rotational P1/P2).
2. Registered zone_touch (active) and rotational (intake) entries in `strategy_archetypes.md` with a Periods field.
3. Created `stages/01-data/validate.py` — a stdlib-only Python script that parses both config files and writes `data_manifest.json` with the new `archetypes` top-level key plus backwards-compatible flat `periods`.
4. Updated `data_manifest_schema.md` to document the new `archetypes` key and P1a/P1b sub-period fields.

## Verification

```
python stages/01-data/validate.py
```

Output: Status PASS, 0 warnings, 0 errors.

Key assertions confirmed:
- archetypes.zone_touch.periods.P1.start == "2025-09-16"
- archetypes.rotational.periods.P1.start == "2025-09-21"
- archetypes.zone_touch.periods.P2.end == "2026-03-02"
- archetypes.rotational.periods.P2.end == "2026-03-13"
- flat periods.P1 present (backwards compat)

## Commits

| Task | Commit  | Description                                               |
|------|---------|-----------------------------------------------------------|
| 1    | ebf28cb | feat(quick-1): add per-archetype period boundaries to config files |
| 2    | d0c7eec | feat(quick-1): validate.py generates per-archetype data_manifest.json |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed midpoint split formula to match config comment dates**
- **Found during:** Task 2 — first run produced zone_touch P1a end = 2025-10-30 instead of 2025-10-31
- **Issue:** Floor division `(end-start).days // 2` gives offset 44; correct is ceiling `(end-start).days + 1) // 2 = 45`
- **Fix:** Changed midpoint formula to `(total_days + 1) // 2` (ceiling division); verified both archetypes match plan-specified dates
- **Files modified:** stages/01-data/validate.py
- **Commit:** d0c7eec (included in same task commit)

**2. [Rule 2 - Missing] Excluded non-archetype section headings from archetype parser**
- **Found during:** Task 2 — "Simulator Interface Contract" parsed as an archetype, generating spurious warnings
- **Fix:** Added explicit skip-list `{"Shared Scoring Models", "Simulator Interface Contract"}` in `parse_archetypes()`
- **Files modified:** stages/01-data/validate.py
- **Commit:** d0c7eec (included in same task commit)

## Self-Check: PASSED

All created files verified on disk. Both task commits (ebf28cb, d0c7eec) confirmed in git log.
