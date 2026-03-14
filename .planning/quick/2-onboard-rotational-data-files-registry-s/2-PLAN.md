---
phase: quick-2
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - _config/data_registry.md
  - stages/01-data/references/bar_data_rot_schema.md
  - stages/01-data/validate.py
  - stages/01-data/output/data_manifest.json
  - shared/archetypes/rotational/simulation_rules.md
  - shared/archetypes/rotational/feature_engine.py
autonomous: true
requirements: []
must_haves:
  truths:
    - "data_registry.md lists bar_data_250vol_rot and bar_data_250tick_rot as registered sources"
    - "bar_data_rot_schema.md documents all 35 columns including duplicate channel names"
    - "validate.py reads data_registry.md, checks file existence, validates columns and date coverage"
    - "data_manifest.json contains archetypes.rotational.sources with both source entries"
    - "shared/archetypes/rotational/ exists with simulation_rules.md and feature_engine.py"
  artifacts:
    - path: "_config/data_registry.md"
      provides: "Registry entries for rotational bar data"
      contains: "bar_data_250vol_rot"
    - path: "stages/01-data/references/bar_data_rot_schema.md"
      provides: "35-column schema for rotational CSV files"
      contains: "ATR"
    - path: "stages/01-data/validate.py"
      provides: "Registry-aware validation with file/column/date checks"
    - path: "shared/archetypes/rotational/feature_engine.py"
      provides: "Archetype skeleton with compute_features stub"
      contains: "# archetype: rotational"
    - path: "shared/archetypes/rotational/simulation_rules.md"
      provides: "Bar-only archetype simulation rules stub"
  key_links:
    - from: "stages/01-data/validate.py"
      to: "_config/data_registry.md"
      via: "parse Registered Sources table"
      pattern: "data_registry"
    - from: "stages/01-data/validate.py"
      to: "stages/01-data/output/data_manifest.json"
      via: "writes archetypes.rotational.sources"
      pattern: "sources"
---

<objective>
Onboard rotational archetype data files into the pipeline: register two new bar data sources, document their 35-column schema, upgrade validate.py to be registry-aware (checking file existence, required columns, and date coverage), create the rotational archetype skeleton, and verify everything produces correct manifest output.

Purpose: Enable the rotational archetype to proceed through Stages 02-04 with properly registered and validated data.
Output: Updated registry, new schema doc, upgraded validate.py, archetype skeleton, validated manifest.
</objective>

<execution_context>
@C:/Users/jshin/.claude/get-shit-done/workflows/execute-plan.md
@C:/Users/jshin/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@_config/data_registry.md
@stages/01-data/validate.py
@stages/01-data/references/bar_data_volume_schema.md
@shared/archetypes/zone_touch/feature_engine.py (pattern reference)
@shared/archetypes/zone_touch/simulation_rules.md (pattern reference)
@stages/01-data/data/bar_data/volume/NQ_BarData_250vol_rot_P1.csv (header row only — for column names)
</context>

<tasks>

<task type="auto">
  <name>Task 1: Registry entries and schema documentation</name>
  <files>_config/data_registry.md, stages/01-data/references/bar_data_rot_schema.md</files>
  <action>
1. Edit `_config/data_registry.md` — append two rows to the Registered Sources table:

| bar_data_250vol_rot | price | 250-vol OHLCV+indicator bars for rotational archetype (35 cols). Different period boundaries than bar_data_volume (P1 starts 2025-09-21, P2 ends 2026-03-13) | P1, P2 | NQ_BarData_250vol_rot_*.csv | 02-features, 04-backtest |
| bar_data_250tick_rot | price | 250-tick OHLCV+indicator bars for rotational archetype (35 cols). Same period boundaries as bar_data_250vol_rot | P1, P2 | NQ_BarData_250tick_rot_*.csv | 02-features, 04-backtest |

2. Create `stages/01-data/references/bar_data_rot_schema.md` following the pattern of bar_data_volume_schema.md. Document all 35 columns from the actual CSV header:

Date, Time, Open, High, Low, Last, Volume, # of Trades, OHLC Avg, HLC Avg, HL Avg, Bid Volume, Ask Volume, Zig Zag, Text Labels, Reversal Price, Zig Zag Line Length, Zig Zag Num Bars, Zig Zag Mid-Point, Extension Lines, Zig Zag Oscillator, Sum, Top, Bottom, Top MovAvg, Bottom MovAvg, Top, Bottom, Top MovAvg, Bottom MovAvg, Top, Bottom, Top MovAvg, Bottom MovAvg, ATR

Note the duplicate column names: Top, Bottom, Top MovAvg, Bottom MovAvg appear 3 times each (from 3 different channel/band studies). Document them as Channel_1_Top, Channel_1_Bottom, etc. in the schema notes but preserve the raw header names. Include column index numbers (0-34) so readers can disambiguate duplicates.

Source IDs: bar_data_250vol_rot and bar_data_250tick_rot (both share this schema).
Files live in: stages/01-data/data/bar_data/volume/ and stages/01-data/data/bar_data/tick/
  </action>
  <verify>
    <automated>grep -c "bar_data_250vol_rot\|bar_data_250tick_rot" _config/data_registry.md | grep -q "2" && echo "PASS: both rows found" || echo "FAIL"</automated>
  </verify>
  <done>data_registry.md has both new rows; bar_data_rot_schema.md exists with all 35 columns documented including duplicate disambiguation</done>
</task>

<task type="auto">
  <name>Task 2: Upgrade validate.py to registry-aware validation and create archetype skeleton</name>
  <files>stages/01-data/validate.py, shared/archetypes/rotational/simulation_rules.md, shared/archetypes/rotational/feature_engine.py</files>
  <action>
**Part A — Upgrade validate.py** to add registry-aware validation. Add these capabilities while preserving ALL existing functionality:

1. **Parse data_registry.md** — add a `parse_data_registry(path)` function that reads `_config/data_registry.md` and returns a list of dicts with keys: source_id, type, description, periods, file_pattern, required_by. Parse the Registered Sources markdown table (same pipe-delimited pattern used by parse_period_config).

2. **File existence check** — for each registry source with periods "P1, P2": glob for matching files in `stages/01-data/data/` (recurse subdirs). Use the file_pattern column. Report missing files as errors.

3. **Column validation** — for bar data sources (type=price): read the first line (header) of each found file and check that at minimum these columns exist: Date, Time, Open, High, Low, Last, Volume. Report missing required columns as errors.

4. **Date coverage check** — for each found file: determine which period it belongs to from the filename (contains _P1 or _P2). Look up the period dates from the archetype's resolved periods. Read the first and last data rows, parse the Date column (format: M/D/YYYY). Check: first row date >= period start, last row date <= period end. Report violations as warnings (not errors — files may have slightly different boundaries).

5. **Register in manifest** — after validation, for each registry source: determine which archetype it belongs to by matching source_id against strategy_archetypes.md "Required data" lines. Add to `archetypes.{archetype}.sources.{source_id}` in the manifest with keys: path (string), rows (int), date_range ({start, end} from actual data). Do this inside `build_manifest()` by accepting the parsed registry and found-file info.

The existing scan_data_sources() and flat periods structure must continue to work unchanged. The registry validation is additive.

**Part B — Create archetype skeleton:**

1. Create `shared/archetypes/rotational/simulation_rules.md`:
   - Line 1: `# archetype: rotational`
   - Title: Simulation Rules — rotational archetype
   - Content: stub noting this is a bar-only archetype (no external touch events). Signal logic lives in archetype code. Entry/exit mechanics TBD — will be defined during Stage 03 hypothesis development. No SimResult contract yet.

2. Create `shared/archetypes/rotational/feature_engine.py`:
   - Line 1: `# archetype: rotational`
   - Follow zone_touch pattern: docstring, imports (sys, pathlib), resolve _REPO_ROOT (parents[3] from shared/archetypes/rotational/), sys.path.insert, import parse_instruments_md, cache _NQ_CONSTANTS and _TICK_SIZE.
   - Empty `compute_features(bar_df)` function (takes bar_df only — no touch_row since rotational is bar-only). Return empty dict. Docstring: "Compute features for rotational archetype. Edit during Stage 02 autoresearch."
  </action>
  <verify>
    <automated>cd C:/Projects/pipeline && python stages/01-data/validate.py</automated>
  </verify>
  <done>
- validate.py reads data_registry.md and checks file existence, required columns, and date coverage for all registered sources
- data_manifest.json has archetypes.rotational.sources with bar_data_250vol_rot and bar_data_250tick_rot entries (each with path, rows, date_range)
- All 4 rotational data files pass validation
- shared/archetypes/rotational/ exists with simulation_rules.md and feature_engine.py
- feature_engine.py has "# archetype: rotational" on line 1 and imports parse_instruments_md
  </done>
</task>

</tasks>

<verification>
1. `grep "bar_data_250vol_rot" _config/data_registry.md` — row exists
2. `grep "bar_data_250tick_rot" _config/data_registry.md` — row exists
3. `cat stages/01-data/references/bar_data_rot_schema.md` — 35 columns documented
4. `python stages/01-data/validate.py` — exits 0, no errors
5. `python -c "import json; m=json.load(open('stages/01-data/output/data_manifest.json')); s=m['archetypes']['rotational']['sources']; assert 'bar_data_250vol_rot' in s and 'bar_data_250tick_rot' in s; print('PASS')"` — sources registered
6. `head -1 shared/archetypes/rotational/feature_engine.py` — shows "# archetype: rotational"
7. `test -f shared/archetypes/rotational/simulation_rules.md && echo PASS` — exists
</verification>

<success_criteria>
- data_registry.md has both new source rows
- bar_data_rot_schema.md documents all 35 columns with duplicate disambiguation
- validate.py is registry-aware: parses registry, checks files, validates columns and dates
- data_manifest.json has archetypes.rotational.sources with both source IDs, each having path/rows/date_range
- shared/archetypes/rotational/ has simulation_rules.md and feature_engine.py skeletons
- All 4 data files pass validation (exit 0)
</success_criteria>

<output>
After completion, create `.planning/quick/2-onboard-rotational-data-files-registry-s/2-SUMMARY.md`
</output>
