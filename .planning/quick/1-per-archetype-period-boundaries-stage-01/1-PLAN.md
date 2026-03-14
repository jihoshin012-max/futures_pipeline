---
phase: quick
plan: 1
type: execute
wave: 1
depends_on: []
files_modified:
  - _config/period_config.md
  - stages/03-hypothesis/references/strategy_archetypes.md
  - stages/01-data/references/data_manifest_schema.md
  - stages/01-data/validate.py
  - stages/01-data/output/data_manifest.json
autonomous: true
requirements: [PM-01]
must_haves:
  truths:
    - "period_config.md has per-archetype rows for zone_touch and rotational"
    - "data_manifest.json contains archetypes.zone_touch.periods with correct dates"
    - "data_manifest.json contains archetypes.rotational.periods with correct dates"
    - "data_manifest.json retains backwards-compatible flat periods structure"
    - "strategy_archetypes.md has Periods field on archetype entries"
  artifacts:
    - path: "_config/period_config.md"
      provides: "Per-archetype period table"
      contains: "archetype"
    - path: "stages/01-data/validate.py"
      provides: "Stage 01 validation script"
    - path: "stages/01-data/output/data_manifest.json"
      provides: "Generated manifest with per-archetype periods"
      contains: "archetypes"
  key_links:
    - from: "stages/01-data/validate.py"
      to: "_config/period_config.md"
      via: "markdown table parser reads archetype column"
      pattern: "archetype"
    - from: "stages/01-data/validate.py"
      to: "stages/01-data/output/data_manifest.json"
      via: "writes per-archetype periods to manifest"
      pattern: "archetypes.*periods"
---

<objective>
Add per-archetype period boundaries to the pipeline config and Stage 01 validation.

Purpose: Different strategy archetypes have different IS/OOS date boundaries (zone_touch P1 starts 2025-09-16, rotational P1 starts 2025-09-21; zone_touch P2 ends 2026-03-02, rotational P2 ends 2026-03-13). The pipeline currently uses a flat period table that cannot represent this.

Output: Updated period_config.md with archetype column, new validate.py that generates per-archetype data_manifest.json, updated strategy_archetypes.md with Periods fields.
</objective>

<execution_context>
@C:/Users/jshin/.claude/get-shit-done/workflows/execute-plan.md
@C:/Users/jshin/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@_config/period_config.md
@stages/01-data/references/data_manifest_schema.md
@stages/01-data/CONTEXT.md
@stages/03-hypothesis/references/strategy_archetypes.md

<interfaces>
<!-- Existing period_config.md table format (to be extended): -->
| period_id | role | start_date | end_date   | notes |

<!-- Existing data_manifest_schema.md JSON structure (to be extended): -->
{
  "generated": "YYYY-MM-DD HH:MM:SS",
  "periods": { "P1": { "start", "end", "sources": {} }, "P2": { ... } },
  "bar_offset": { "verified", "offset_bars", "verified_date", "method" },
  "validation_summary": { "status", "warnings", "errors" }
}

<!-- Downstream consumers read data_manifest.json via: -->
<!-- feature_evaluator.py: periods.P1.sources.{source_id}.path -->
<!-- hypothesis_generator.py: periods.P1, then date-slices P1a/P1b -->
<!-- backtest_engine.py: does NOT read data_manifest.json -->
</interfaces>
</context>

<tasks>

<task type="auto">
  <name>Task 1: Update config files — period_config.md and strategy_archetypes.md</name>
  <files>_config/period_config.md, stages/03-hypothesis/references/strategy_archetypes.md</files>
  <action>
CHANGE 1 — _config/period_config.md:
Replace the Active Periods table with the archetype-aware version. Keep all other sections (Rules, Rolling Forward, Internal Replication) unchanged.

New table:

| period_id | archetype  | role | start_date | end_date   | notes                     |
|-----------|------------|------|------------|------------|---------------------------|
| P1        | zone_touch | IS   | 2025-09-16 | 2025-12-14 | Calibration — used freely |
| P2        | zone_touch | OOS  | 2025-12-15 | 2026-03-02 | Holdout — one-shot only   |
| P1        | rotational | IS   | 2025-09-21 | 2025-12-14 | Calibration — used freely |
| P2        | rotational | OOS  | 2025-12-15 | 2026-03-13 | Holdout — one-shot only   |

Update the informational P1a/P1b comment to note it is now per-archetype:
  zone_touch: P1a = 2025-09-16 to 2025-10-31 | P1b = 2025-11-01 to 2025-12-14
  rotational: P1a = 2025-09-21 to 2025-11-02 | P1b = 2025-11-03 to 2025-12-14

Update the Rolling Forward example to include archetype column (use '*' wildcard in the example since future periods may apply to all).

Update the "Example — end of Q2 2026" section's Before/After tables to include the archetype column matching current rows.

CHANGE 2 — strategy_archetypes.md:
Replace the placeholder `## [Add first archetype here...]` section with a real zone_touch entry:

## zone_touch
- Description: Zone-rejection scalp on NQ futures
- Instrument: NQ (from _config/instruments.md)
- Required data: zone_touch_v2 (touches), volume_bar (bar data)
- Simulator module: shared/archetypes/zone_touch/zone_touch_simulator.py
- feature_evaluator: shared/archetypes/zone_touch/feature_evaluator.py
- feature_engine: shared/archetypes/zone_touch/feature_engine.py
- Periods: P1, P2
- Current status: active

Add a rotational entry (stub — minimal fields):

## rotational
- Description: Rotational momentum strategy on NQ futures
- Instrument: NQ (from _config/instruments.md)
- Required data: tick_bar (bar data)
- Periods: P1, P2
- Current status: intake

Keep the [future archetype template] section and Simulator Interface Contract section unchanged.
  </action>
  <verify>
    <automated>grep -c "archetype" _config/period_config.md && grep -c "Periods:" stages/03-hypothesis/references/strategy_archetypes.md</automated>
  </verify>
  <done>period_config.md has 4 archetype-specific rows (zone_touch P1, P2; rotational P1, P2). strategy_archetypes.md has zone_touch and rotational entries with Periods field.</done>
</task>

<task type="auto">
  <name>Task 2: Create validate.py and generate data_manifest.json with per-archetype periods</name>
  <files>stages/01-data/validate.py, stages/01-data/output/data_manifest.json, stages/01-data/references/data_manifest_schema.md</files>
  <action>
Create stages/01-data/validate.py — a standalone script that:

1. PARSE period_config.md:
   - Read _config/period_config.md
   - Parse the Active Periods markdown table (pipe-delimited)
   - Extract columns: period_id, archetype, role, start_date, end_date, notes
   - Handle archetype='*' as wildcard (applies to all archetypes unless overridden)

2. PARSE strategy_archetypes.md:
   - Read stages/03-hypothesis/references/strategy_archetypes.md
   - Extract registered archetype names (## headings that are not templates/shared)
   - For each archetype, read its "Periods:" field

3. RESOLVE per-archetype periods:
   - For each registered archetype, find matching rows in period_config:
     a. First look for rows where archetype == archetype_name
     b. Fall back to rows where archetype == '*'
     c. Archetype-specific rows take precedence over '*' rows (per period_id)

4. COMPUTE P1a/P1b sub-periods per archetype:
   - Read p1_split_rule from period_config.md (currently: midpoint)
   - For each archetype's P1, compute P1a and P1b dates using the split rule
   - midpoint: P1a = first half, P1b = second half (split at midpoint date)

5. SCAN data sources:
   - Walk stages/01-data/data/ for CSV/TXT files
   - For each file found, record path and row count
   - Check if file covers the expected date range (best-effort; warn if cannot determine)

6. BUILD data_manifest.json:
   - "generated": current ISO timestamp
   - "periods": backwards-compatible flat structure using zone_touch dates (P1 start=2025-09-16, end=2025-12-14; P2 start=2025-12-15, end=2026-03-02) with sources populated from data scan
   - "archetypes": {
       "zone_touch": {
         "periods": {
           "P1": {"start": "2025-09-16", "end": "2025-12-14", "role": "IS"},
           "P1a": {"start": "2025-09-16", "end": "2025-10-31"},
           "P1b": {"start": "2025-11-01", "end": "2025-12-14"},
           "P2": {"start": "2025-12-15", "end": "2026-03-02", "role": "OOS"}
         }
       },
       "rotational": {
         "periods": {
           "P1": {"start": "2025-09-21", "end": "2025-12-14", "role": "IS"},
           "P1a": {"start": "2025-09-21", "end": "2025-11-02"},
           "P1b": {"start": "2025-11-03", "end": "2025-12-14"},
           "P2": {"start": "2025-12-15", "end": "2026-03-13", "role": "OOS"}
         }
       }
     }
   - "bar_offset": {"verified": false, "offset_bars": 0, "verified_date": null, "method": "not yet verified"}
   - "validation_summary": {"status": "PASS" or "FAIL", "warnings": [...], "errors": [...]}

7. WRITE validation_report.md:
   - Summary of all checks: period parsing, archetype resolution, data source scan
   - Per-archetype period boundaries displayed
   - Any warnings or errors

8. WRITE data_manifest.json to stages/01-data/output/data_manifest.json

Script requirements:
- Python 3, stdlib only (no pandas, no external deps)
- Use re for markdown table parsing
- Use json for manifest output
- Use pathlib for paths
- _REPO_ROOT = Path(__file__).resolve().parents[2] (pipeline root)
- Print summary to stdout
- Exit 0 on PASS, exit 1 on FAIL

ALSO update stages/01-data/references/data_manifest_schema.md:
Add the "archetypes" key to the JSON schema documentation. Add a note that "periods" (flat) is kept as backwards-compatible alias pointing to zone_touch dates. Document the per-archetype structure including P1a/P1b sub-periods.

After creating validate.py, RUN IT:
  cd to repo root, then: python stages/01-data/validate.py

Review the output. If it fails, fix and re-run. Confirm:
- data_manifest.json written to stages/01-data/output/
- archetypes.zone_touch.periods.P1.start == "2025-09-16"
- archetypes.rotational.periods.P1.start == "2025-09-21"
- archetypes.zone_touch.periods.P2.end == "2026-03-02"
- archetypes.rotational.periods.P2.end == "2026-03-13"
- flat periods.P1 still present (backwards compat)
  </action>
  <verify>
    <automated>python stages/01-data/validate.py && python -c "import json; m=json.load(open('stages/01-data/output/data_manifest.json')); assert m['archetypes']['zone_touch']['periods']['P1']['start']=='2025-09-16'; assert m['archetypes']['rotational']['periods']['P1']['start']=='2025-09-21'; assert m['archetypes']['zone_touch']['periods']['P2']['end']=='2026-03-02'; assert m['archetypes']['rotational']['periods']['P2']['end']=='2026-03-13'; assert 'P1' in m['periods']; print('ALL CHECKS PASS')"</automated>
  </verify>
  <done>
- validate.py exists and runs successfully
- data_manifest.json has archetypes.zone_touch.periods and archetypes.rotational.periods with correct dates
- data_manifest.json has backwards-compatible flat periods structure
- data_manifest_schema.md documents the new archetypes structure
- validation_report.md generated
  </done>
</task>

</tasks>

<verification>
Run validate.py and check manifest:
```bash
python stages/01-data/validate.py
python -c "import json; m=json.load(open('stages/01-data/output/data_manifest.json')); print(json.dumps(m['archetypes'], indent=2))"
```
Confirm zone_touch P1 start=2025-09-16, rotational P1 start=2025-09-21.
Confirm flat periods.P1 still exists for backwards compatibility.
</verification>

<success_criteria>
- period_config.md has archetype column with zone_touch and rotational rows
- strategy_archetypes.md has Periods field on zone_touch and rotational entries
- validate.py runs cleanly (exit 0)
- data_manifest.json shows correct per-archetype period boundaries
- Flat periods structure retained for backwards compatibility
- Commit message: manual: PM-01 per-archetype period boundaries
</success_criteria>

<output>
After completion, create `.planning/quick/1-per-archetype-period-boundaries-stage-01/1-SUMMARY.md`
</output>
