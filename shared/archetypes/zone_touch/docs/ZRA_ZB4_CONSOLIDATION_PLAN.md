# ZRA + ZB4 Consolidation Plan
last_reviewed: 2026-03-23
revision: 2 (decisions incorporated, issues 1-4 addressed)

## Decisions (Resolved)

| # | Question | Decision | Rationale |
|---|----------|----------|-----------|
| 1 | Retag to HEAD? | YES | 4 doc-only commits, zero C++ changes |
| 2 | Session-scoped vs persistent rays? | PERSISTENT | Rays don't have VP's staleness problem (no VAP recalc purge). V4 draws them indefinitely. Capture everything, filter in Python. |
| 3 | M1A/M1B autotraders? | DEAD CODE | Not active on any chart. Move to _deprecated/ in Phase 4. Excluded from Phase 2 test matrix. |
| 4 | SG 0-5 exposure? | FETCH AND STORE ONLY | No output subgraphs or CSV columns in v4.0. Add later if analytical need arises. |
| 5 | CSV filename? | KEEP NQ_ZRA_Hist_*.csv | Minimizes downstream path changes. Rename in a later cleanup pass. |

---

## Step 0: Baseline Tag Status

**Action:** Retag both to current HEAD (de66bfe).

```
git tag -d v1.0-pre-merge
git tag -d v3.0-pre-merge
git tag -a v1.0-pre-merge -m "FIXED autotrader — C++ replication PASS 85/85 on P1. SC deploy base + CSV test mode. CT 40/80/190, WT 60/80/240. Before ZRA+ZB4 consolidation."
git tag -a v3.0-pre-merge -m "ZONEREL autotrader — C++ replication PASS 77/77 on P1. SC deploy infrastructure + CSV test mode. T1=0.5xZW, T2=1.0xZW, Stop=max(1.5xZW,120). Before ZRA+ZB4 consolidation."
```

Verify: `git show-ref --tags | grep pre-merge` — both must show de66bfe.

---

## Step 1: Dependency Map

### A. ZRA Dependencies

**Source:** `shared/archetypes/zone_touch/acsil/ZoneReactionAnalyzer.cpp` (v3.2)

**V4 subgraphs fetched:** 6, 7, 8, 9, 10, 11, 14 (7 of 15)

**Output subgraphs (5):**

| Index | Name | DrawStyle | Purpose |
|-------|------|-----------|---------|
| 0 | Demand Edge | ARROW_UP | Demand edge touch markers |
| 1 | Supply Edge | ARROW_DOWN | Supply edge touch markers |
| 2 | VP Ray Touch | DIAMOND | VP ray touch markers |
| 3 | Reaction | IGNORE | Reaction magnitude (data only) |
| 4 | Penetration | IGNORE | Penetration magnitude (data only) |

**CSV output:** `ZoneReactionAnalysis_MultiTF.csv` → pipeline copies to `NQ_ZRA_Hist_*.csv`

**33 CSV columns:**
```
DateTime, BarIndex, TouchType, ApproachDir, TouchPrice, ZoneTop, ZoneBot,
HasVPRay, VPRayPrice, Reaction, Penetration, ReactionPeakBar,
ZoneBroken, BreakBarIndex, BarsObserved, TouchSequence, ZoneAgeBars,
ApproachVelocity, TrendSlope, SourceChart, SourceStudyID, SourceLabel,
RxnBar_30, RxnBar_50, RxnBar_80, RxnBar_120, RxnBar_160, RxnBar_240,
RxnBar_360, PenBar_30, PenBar_50, PenBar_80, PenBar_120
```

**Python consumers of ZRA CSV:**

| File | Dependency | Details |
|------|-----------|---------|
| `shared/data_loader.py` | `load_touches()` | Loads ZRA CSV, parses DateTime |
| `shared/archetypes/zone_touch/feature_evaluator.py` | Column names | Strips lookahead cols (Reaction, Penetration, RxnBar_*, PenBar_*) |
| `stages/01-data/scripts/run_zone_prep.py` | Primary data source | ZRA is left side of ZRA+ZB4 merge |
| `stages/04-backtest/zone_touch/generate_p1_answer_keys.py` | Reads merged CSV | Via NQ_merged_P1a/b.csv (ZRA + ZB4 post-merge) |
| `tests/test_data_loader.py` | 33-column assertion | `test_load_touches_columns()` |
| `tests/test_backtest_engine.py` | Path reference | NQ_ZRA_Hist_P1.csv, P2 |
| `tests/test_driver.py` | Config reference | touches_csv path |
| `tests/test_feature_evaluator.py` | CSV load | Via load_touches() |
| `tests/test_hypothesis_generator.py` | Config reference | touches_csv path |
| `tests/test_stage03_driver.py` | Config reference | touches_csv path |

**Autotrader dependency on ZRA: NONE.** Both autotraders read ZB4 persistent storage, not ZRA.

### B. ZB4 Dependencies

**Source:** `shared/archetypes/zone_touch/acsil/ZoneBounceSignalsV4_aligned.cpp` (v3.2)

**V4 subgraphs fetched:** 6, 7, 8, 9, 10, 11, 14 (identical to ZRA)

**Output subgraphs (15):**

| Index | Name | DrawStyle | Purpose |
|-------|------|-----------|---------|
| 0 | M1 Demand (Full) | ARROW_UP | M1F demand signal |
| 1 | M1 Supply (Full) | ARROW_DOWN | M1F supply signal |
| 2 | M3 Demand | ARROW_UP | M3 demand signal |
| 3 | M3 Supply | ARROW_DOWN | M3 supply signal |
| 4 | M4 Demand | ARROW_UP | M4 demand signal |
| 5 | M4 Supply | ARROW_DOWN | M4 supply signal |
| 6 | Skip Demand | ARROW_UP | Skipped demand |
| 7 | Skip Supply | ARROW_DOWN | Skipped supply |
| 8 | M5 Demand | ARROW_UP | M5 demand signal |
| 9 | M5 Supply | ARROW_DOWN | M5 supply signal |
| 10 | Trend Slope | COLOR_BAR | Trend context bar coloring |
| 11 | Trend Zero | IGNORE | Reference line at 0 |
| 12 | (unused) | — | — |
| 13 | M1H Demand | ARROW_UP | M1 Half demand signal |
| 14 | M1H Supply | ARROW_DOWN | M1 Half supply signal |

**CSV output:** `ZB4_signals.csv` → pipeline copies to `NQ_ZB4_signals_*.csv`

**30 CSV columns:**
```
DateTime, BarIndex, TouchType, ApproachDir, TouchPrice, ZoneTop, ZoneBot,
HasVPRay, VPRayPrice, ZoneWidthTicks, PenetrationTicks, TouchSequence,
ZoneAgeBars, ApproachVelocity, TrendSlope, SourceLabel, TFWeightScore,
TFConfluence, CascadeState, CascadeActive, SessionClass, DayOfWeek,
ModeAssignment, QualityScore, ContextScore, TotalScore, SourceSlot,
ConfirmedBar, HtfConfirmed, Active
```

**Python consumers of ZB4 CSV:**

| File | Dependency | Details |
|------|-----------|---------|
| `stages/01-data/scripts/run_zone_prep.py` | CascadeState, TFConfluence | Left-joins these 2 cols into ZRA via key match |

Note: run_zone_prep.py explicitly REJECTS ZB4 scoring columns (ModeAssignment, QualityScore, ContextScore, TotalScore) from the merge — assertion at line 220.

**Autotrader dependency on ZB4: CRITICAL.**

Both autotraders read ZB4 via `GetPersistentPointerFromChartStudy()`:
- Magic number: `0x5A425634` ("ZBV4")
- Storage: `SignalStorage` struct containing `SignalRecord[5000]` + `TrackedZone[10000]`
- Read fields: TouchPrice, ZoneTop, ZoneBot, TrendSlope, VPRayPrice, ZoneWidthTicks, PenetrationTicks, TouchSequence, ZoneAgeBars, SourceSlot, SourceLabel, CascadeState, ModeAssignment, QualityScore, ContextScore, TotalScore, etc.
- Autotraders do NOT read ZB4 chart subgraphs — purely persistent storage.

**M1A/M1B autotraders:** Dead code. Not active on any chart. Will be moved to `_deprecated/` in Phase 4.

### C. V4 Subgraph Map

| SG | Name | Fetched by ZRA | Fetched by ZB4 | Notes |
|----|------|:-:|:-:|-------|
| 0 | DemandSignal | — | — | Fires on zone creation bar (signal=1) |
| 1 | DemandZoneTop | — | — | Zone top price on creation bar |
| 2 | DemandZoneBot | — | — | Zone bottom price on creation bar |
| 3 | SupplySignal | — | — | Fires on zone creation bar (signal=1) |
| 4 | SupplyZoneTop | — | — | Zone top price on creation bar |
| 5 | SupplyZoneBot | — | — | Zone bottom price on creation bar |
| 6 | DemandBroken | YES | YES | Cumulative break count |
| 7 | SupplyBroken | YES | YES | Cumulative break count |
| 8 | NearestDemandTop | YES | YES | Updated every bar — nearest active |
| 9 | NearestDemandBot | YES | YES | Updated every bar — nearest active |
| 10 | NearestSupplyTop | YES | YES | Updated every bar — nearest active |
| 11 | NearestSupplyBot | YES | YES | Updated every bar — nearest active |
| 12 | DemandRayPrice | — | — | Broken demand zone's TopPrice, set on break bar |
| 13 | SupplyRayPrice | — | — | Broken supply zone's BottomPrice, set on break bar |
| 14 | VPImbalancePrice | YES | YES | VP ray price within zone |

**Key distinction for SG 12/13:** These fire *on the break bar* and contain the broken zone's edge price (demand ray = TopPrice, supply ray = BottomPrice). They are NOT persistent — they are zero on non-break bars. To track active broken zone rays, the consolidated study must accumulate them into a persistent array. Rays are kept indefinitely (Decision #2).

### D. Chart Study Execution Order

Per STUDY_CHAIN_REFERENCE.md and chart configuration:
```
1. SupplyDemandZonesV4 (V4)        — creates zones
2. SupplyDemandZonesV4_history      — batch zone export (optional)
3. ZoneReactionAnalyzer (ZRA)       — measurement
4. ZoneBounceSignalsV4_aligned (ZB4) — scoring + signals
5a. ATEAM_ZONE_BOUNCE_FIXED         — autotrader
5b. ATEAM_ZONE_BOUNCE_ZONEREL       — autotrader
```

**Sierra Chart ordering:** Studies execute in insertion order, NOT alphabetically. If the consolidated study replaces ZRA+ZB4, it must be inserted BEFORE the autotraders. Renaming does not automatically reorder — manual chart configuration is required.

**Required chain after consolidation:**
```
1. V4 → 2. Consolidated study → 3. Autotrader(s)
```

### E. CSV Terminology (Issue 2 — clarified)

Two distinct CSVs are in play throughout this plan:

| Label | Producer | Columns | Consumers |
|-------|----------|---------|-----------|
| **Raw CSV** | Consolidated study (C++) | 52 columns (unified ZRA+ZB4+ray) | `run_zone_prep.py` (Python) |
| **Merged CSV** | `run_zone_prep.py` (Python) | 37 columns (raw CSV subset + SBB_Label, RotBarIndex, Period) | Autotrader CSV test mode, `generate_p1_answer_keys.py` |

The raw CSV filename is `NQ_ZRA_Hist_*.csv` (Decision #5 — keep existing name).
The merged CSV filename is `NQ_merged_P1a.csv` / `NQ_merged_P1b.csv`.

The prep script reads the raw CSV and produces the merged CSV. It still needs to:
1. Add SBB_Label (from V4_history)
2. Add RotBarIndex (bar rotation mapping)
3. Add Period label
4. Filter VP_RAY touches

But it no longer needs to merge ZB4 columns — they're already in the raw CSV.

**Critical constraint:** The merged CSV column order (indices 0-36) must NOT change, or the autotrader C++ parsers break. The prep script must output the same 37-column merged format regardless of the raw CSV's internal column order.

**Merged CSV layout (37 columns, by index — frozen):**
```
 0: DateTime           16: ZoneAgeBars        32: CascadeState
 1: BarIndex           17: ApproachVelocity   33: TFConfluence
 2: TouchType          18: TrendSlope         34: SBB_Label
 3: ApproachDir        19: SourceLabel        35: RotBarIndex
 4: TouchPrice         20: RxnBar_120         36: Period
 5: ZoneTop            21: RxnBar_160
 6: ZoneBot            22: RxnBar_240
 7: HasVPRay           23: RxnBar_30
 8: VPRayPrice         24: RxnBar_360
 9: Reaction           25: RxnBar_50
10: Penetration        26: RxnBar_80
11: ReactionPeakBar    27: PenBar_120
12: ZoneBroken         28: PenBar_30
13: BreakBarIndex      29: PenBar_50
14: BarsObserved       30: PenBar_80
15: TouchSequence      31: ZoneWidthTicks
```

**Autotrader reads these column indices:** 0, 1, 2, 4, 5, 6, 10, 15, 16, 18, 19, 31, 32, 34, 35

---

## Step 2: Consolidated Study Design

### A. Name

**Name:** `ZoneTouchEngine.cpp`

**Graph name:** `"Zone Touch Engine [v4.0]"`

Version bumped to v4.0 (major) to distinguish from the v3.x lineage of both ZRA and ZB4.

### B. Subgraph Layout

The consolidated study must preserve ZB4's persistent storage interface (how autotraders read data) while adding ZRA's measurement subgraphs.

**Proposed output subgraphs (20 total):**

| Index | Name | Source | DrawStyle | Purpose |
|-------|------|--------|-----------|---------|
| 0 | M1 Demand (Full) | ZB4[0] | ARROW_UP | M1F demand signal |
| 1 | M1 Supply (Full) | ZB4[1] | ARROW_DOWN | M1F supply signal |
| 2 | M3 Demand | ZB4[2] | ARROW_UP | M3 demand signal |
| 3 | M3 Supply | ZB4[3] | ARROW_DOWN | M3 supply signal |
| 4 | M4 Demand | ZB4[4] | ARROW_UP | M4 demand signal |
| 5 | M4 Supply | ZB4[5] | ARROW_DOWN | M4 supply signal |
| 6 | Skip Demand | ZB4[6] | ARROW_UP | Skipped demand |
| 7 | Skip Supply | ZB4[7] | ARROW_DOWN | Skipped supply |
| 8 | M5 Demand | ZB4[8] | ARROW_UP | M5 demand signal |
| 9 | M5 Supply | ZB4[9] | ARROW_DOWN | M5 supply signal |
| 10 | Trend Slope | ZB4[10] | COLOR_BAR | Trend bar coloring |
| 11 | Trend Zero | ZB4[11] | IGNORE | Reference at 0 |
| 12 | Demand Edge | ZRA[0] | ARROW_UP | Demand edge markers |
| 13 | M1H Demand | ZB4[13] | ARROW_UP | M1 Half demand |
| 14 | M1H Supply | ZB4[14] | ARROW_DOWN | M1 Half supply |
| 15 | Supply Edge | ZRA[1] | ARROW_DOWN | Supply edge markers |
| 16 | VP Ray Touch | ZRA[2] | DIAMOND | VP ray touch markers |
| 17 | Reaction | ZRA[3] | IGNORE | Reaction magnitude |
| 18 | Penetration | ZRA[4] | IGNORE | Penetration magnitude |
| 19 | (reserved) | — | IGNORE | Future use |

**Backward compatibility:**
- ZB4 subgraphs 0-11, 13-14: **Preserved at same indices.** No autotrader impact.
- ZRA subgraphs 0-4: **Relocated to indices 12, 15-18.** No consumers depend on ZRA subgraph indices.
- ZB4 index 12 was unused — now holds Demand Edge (ZRA[0]). No conflict.

**Autotrader impact: ZERO subgraph changes required.** Autotraders read persistent storage, not chart subgraphs. The `SignalStorage` struct and magic number (`0x5A425634`) must be preserved identically.

### C. Raw CSV Output Format

**Strategy:** Export a SINGLE unified raw CSV that is a superset of both ZRA and ZB4 columns, plus ray summary data.

**Proposed raw CSV (52 columns):**

```
 0: DateTime                    — from ZRA/ZB4 (shared)
 1: BarIndex                    — from ZRA/ZB4 (shared)
 2: TouchType                   — from ZRA/ZB4 (shared)
 3: ApproachDir                 — from ZRA/ZB4 (shared)
 4: TouchPrice                  — from ZRA/ZB4 (shared)
 5: ZoneTop                     — from ZRA/ZB4 (shared)
 6: ZoneBot                     — from ZRA/ZB4 (shared)
 7: HasVPRay                    — from ZRA/ZB4 (shared)
 8: VPRayPrice                  — from ZRA/ZB4 (shared)
 9: Reaction                    — from ZRA (measurement)
10: Penetration                 — from ZRA (measurement)
11: ReactionPeakBar             — from ZRA (measurement)
12: ZoneBroken                  — from ZRA (measurement)
13: BreakBarIndex               — from ZRA (measurement)
14: BarsObserved                — from ZRA (measurement)
15: TouchSequence               — from ZRA/ZB4 (shared)
16: ZoneAgeBars                 — from ZRA/ZB4 (shared)
17: ApproachVelocity            — from ZRA/ZB4 (shared)
18: TrendSlope                  — from ZRA/ZB4 (shared)
19: SourceLabel                 — from ZRA/ZB4 (shared)
20: SourceChart                 — from ZRA
21: SourceStudyID               — from ZRA
22: RxnBar_30                   — from ZRA (measurement)
23: RxnBar_50                   — from ZRA (measurement)
24: RxnBar_80                   — from ZRA (measurement)
25: RxnBar_120                  — from ZRA (measurement)
26: RxnBar_160                  — from ZRA (measurement)
27: RxnBar_240                  — from ZRA (measurement)
28: RxnBar_360                  — from ZRA (measurement)
29: PenBar_30                   — from ZRA (measurement)
30: PenBar_50                   — from ZRA (measurement)
31: PenBar_80                   — from ZRA (measurement)
32: PenBar_120                  — from ZRA (measurement)
33: ZoneWidthTicks              — from ZB4 (scoring)
34: CascadeState                — from ZB4 (scoring)
35: CascadeActive               — from ZB4 (scoring)
36: TFWeightScore               — from ZB4 (scoring)
37: TFConfluence                — from ZB4 (scoring)
38: SessionClass                — from ZB4 (scoring)
39: DayOfWeek                   — from ZB4 (scoring)
40: ModeAssignment              — from ZB4 (scoring)
41: QualityScore                — from ZB4 (scoring)
42: ContextScore                — from ZB4 (scoring)
43: TotalScore                  — from ZB4 (scoring)
44: SourceSlot                  — from ZB4 (scoring)
45: ConfirmedBar                — from ZB4 (scoring)
46: HtfConfirmed                — from ZB4 (scoring)
47: Active                      — from ZB4 (scoring)
48: DemandRayPrice              — NEW (V4 SG 12, nearest to touch)
49: SupplyRayPrice              — NEW (V4 SG 13, nearest to touch)
50: DemandRayDistTicks          — NEW (distance from zone edge to nearest demand ray)
51: SupplyRayDistTicks          — NEW (distance from zone edge to nearest supply ray)
```

**Column count:** 52

**Removed from original plan (Issue 3):**
- ~~RaysBetweenEntryTarget~~ — requires entry/exit context that depends on autotrader config. Computed in Python.
- ~~NearestRayDir~~ — requires entry context. Computed in Python.

**Kept in C++ raw CSV:**
- DemandRayPrice, SupplyRayPrice — raw nearest ray prices (framework-independent)
- DemandRayDistTicks, SupplyRayDistTicks — distance from zone edge (framework-independent)

### D. Ray Context File (Issue 1 — long format)

Alongside the main raw CSV, the consolidated study exports a second file:

**Filename:** `ray_context.csv`
**Format:** Long format — one row per ray-touch pair.

**Columns:**
```
TouchID          — unique touch identifier (BarIndex_TouchType_SourceLabel)
RayPrice         — broken zone edge price
RaySide          — DEMAND or SUPPLY (which type of broken zone)
RayDirection     — ABOVE or BELOW (relative to touch zone edge)
RayDistTicks     — distance from touch zone edge to ray price
RayTF            — source timeframe of the broken zone (inferred from TrackedZone)
RayAgeBars       — bars since the zone broke
```

**Proximity filter:** Only include rays within `2 × max_zone_width` of the touch price, where `max_zone_width` is the widest active zone width at the time of the touch. This bounds the row count without losing analytically relevant rays.

**Example:** A demand edge touch at 21450 with 6 nearby broken zone rays produces 6 rows, each with the ray's price, type, direction, distance, TF, and age.

**Pipeline consumption:** Python groups by TouchID and aggregates into features:
- RaysBetweenEntryTarget (computed with correct entry/exit context per autotrader)
- NearestRayDir (computed relative to entry price)
- RayDensity (count of rays within N ticks)
- RayCluster (are rays concentrated in a narrow band?)

This is the analytical data source for ray feature screening. The 2 summary columns in the main raw CSV (DemandRayPrice, SupplyRayPrice) serve as quick-reference only.

### E. Touch Detection: Unification

**Current differences between ZRA and ZB4 touch detection:**

| Aspect | ZRA | ZB4 | Unified approach |
|--------|-----|-----|------------------|
| Touch types | DEMAND_EDGE, SUPPLY_EDGE, VP_RAY | DEMAND_EDGE, SUPPLY_EDGE only | Keep all 3 (VP_RAY filtered in pipeline) |
| Zone consistency | zone_consistent check | Same check | Shared |
| Debounce | 3 ticks, 20-bar window | 3 ticks, 20-bar window | Shared (identical) |
| VP proximity | 3x zone width threshold | 3x zone width threshold | Shared (identical, both v3.2) |
| Reaction tracking | Full (multi-bar tracking) | None | Preserved from ZRA |
| Scoring | None | A-Cal (quality + context + mode) | Preserved from ZB4 |
| Signal routing | None | M1F/M1H/M3/M4/M5/Skip | Preserved from ZB4 |

**Unification plan:** Single touch detection pass using the shared logic (both are already identical post-v3.2 alignment). On each touch:
1. Record touch event (shared fields)
2. Compute scoring (ZB4 logic)
3. Start reaction/penetration tracking (ZRA logic)
4. Snapshot ray context (all accumulated rays near this touch → ray_context.csv)
5. Write to persistent storage (for autotrader)
6. Write to raw CSV (unified format)
7. Draw chart overlays (signals + edge markers)

### F. Code Structure

**Single file:** `ZoneTouchEngine.cpp` — no .h file.

SC remote build constraint: single .cpp, lowercase `sierrachart.h`, no custom headers.

**Estimated structure:**

| Section | Lines (est.) | Source |
|---------|-------------|--------|
| Constants + structs | 200 | Merged from both |
| Storage (SignalStorage, TrackedZone) | 150 | From ZB4 (must match autotrader) |
| V4 subgraph fetch (all 15) | 50 | Expanded from 7→15 |
| Touch detection (unified) | 250 | Merged ZRA+ZB4 |
| A-Cal scoring + mode routing | 300 | From ZB4 |
| Reaction/penetration tracking | 200 | From ZRA |
| Ray accumulation (persistent, all rays) | 150 | NEW |
| Ray context snapshot (per-touch) | 80 | NEW |
| CSV export (raw CSV, 52 cols) | 80 | Merged |
| CSV export (ray_context.csv) | 60 | NEW |
| Chart overlays (signals, rays) | 150 | From ZB4 + new ray drawing |
| Subgraph setup + init | 100 | Merged |
| **Total** | **~1770** | ZRA was ~1000, ZB4 was ~1800 |

**Functions preserved from ZRA:**
- Touch detection loop (per-slot)
- Reaction/penetration tracking state machine
- Multi-TF CSV export with SourceLabel

**Functions preserved from ZB4:**
- A-Cal scoring (quality, context, total)
- Mode assignment routing
- TF confluence computation
- Cascade state tracking
- Signal drawing (arrows, stop/target rays)
- Persistent storage management (SignalStorage/SignalRecord)

**New code:**
- V4 SG 0-5 fetch + zone creation event tracking (stored internally, not exposed)
- V4 SG 12-13 fetch + persistent ray accumulation
- Ray context snapshot at touch time → ray_context.csv export
- Ray summary columns (nearest ray price + distance) for raw CSV
- Ray chart drawing (horizontal lines at broken zone edges)

---

## Step 3: Migration Plan

### A. Exact Sequence of Changes

**Phase 1: Create consolidated study + ray validator (additive)**
1. Create `RayValidator.cpp` — minimal test study that reads V4 SG 12/13 and writes reference CSV (Issue 4 — moved here from Phase 5)
2. Deploy RayValidator to chart, export ray reference data for P1
3. Create `ZoneTouchEngine.cpp` in `shared/archetypes/zone_touch/acsil/`
4. Verify it compiles via SC remote build
5. Deploy to chart alongside existing ZRA + ZB4 (all three running)
6. Compare outputs: consolidated raw CSV vs ZRA CSV + ZB4 CSV
7. Compare consolidated ray output vs RayValidator reference CSV
8. No files deleted, no autotrader changes

**Phase 2: Switch autotrader data source**
1. Update autotrader Input[0] to point to consolidated study's ID (chart config)
2. Verify persistent storage magic number matches (`0x5A425634`)
3. Run FIXED CSV test mode → must PASS 85/85
4. Run ZONEREL CSV test mode → must PASS 77/77
5. If fail: revert Input[0] to ZB4, investigate

**Phase 3: Switch pipeline data source**
1. Update `run_zone_prep.py` to read consolidated raw CSV instead of separate ZRA + ZB4
2. Verify merged CSV output is column-identical to current (37-column format preserved)
3. Run `generate_p1_answer_keys.py` → output must match existing answer keys byte-for-byte
4. Run pipeline test suite (`pytest tests/`)

**Phase 4: Deprecate ZRA + ZB4 + dead code**
1. Remove ZRA and ZB4 from chart (leave consolidated study)
2. Move to `_deprecated/` subfolder:
   - `ZoneReactionAnalyzer.cpp`
   - `ZoneBounceSignalsV4_aligned.cpp`
   - `M1A_AutoTrader.cpp` (dead code — Decision #3)
   - `M1B_AutoTrader.cpp` (dead code — Decision #3)
3. Keep `_v31` backups untouched
4. Update STUDY_CHAIN_REFERENCE.md
5. Update `_config/data_registry.md` — keep `zone_csv_v2` source_id (filename unchanged per Decision #5)
6. Update schema docs

**Phase 5: Ray data verification (new data — no prior baseline)**
1. Run ray verification protocol using RayValidator reference CSV (built in Phase 1)
2. Verify ray_context.csv completeness and TF tagging
3. Enable ray CSV columns and chart drawing
4. Update pipeline schema for new columns

### Files changed:

| File | Change | Phase |
|------|--------|-------|
| `acsil/RayValidator.cpp` | CREATE (~100 lines) | 1 |
| `acsil/ZoneTouchEngine.cpp` | CREATE (~1770 lines) | 1 |
| Chart configuration (SC) | Add studies, reorder | 1 |
| Chart configuration (SC) | Switch autotrader input | 2 |
| `stages/01-data/scripts/run_zone_prep.py` | Read unified raw CSV (drop ZB4 merge) | 3 |
| `stages/01-data/references/zone_csv_unified_schema.md` | CREATE | 3 |
| `_config/data_registry.md` | Update zone_csv_v2 description | 3 |
| `tests/test_data_loader.py` | Update column count assertion (33→52) | 3 |
| `acsil/STUDY_CHAIN_REFERENCE.md` | Update chain description | 4 |
| `acsil/ZoneReactionAnalyzer.cpp` | Move to _deprecated/ | 4 |
| `acsil/ZoneBounceSignalsV4_aligned.cpp` | Move to _deprecated/ | 4 |
| `acsil/M1A_AutoTrader.cpp` | Move to _deprecated/ | 4 |
| `acsil/M1B_AutoTrader.cpp` | Move to _deprecated/ | 4 |

**Autotrader .cpp files (FIXED, ZONEREL): NO CHANGES REQUIRED.** They read persistent storage by study ID (chart config), not by filename. The struct layout and magic number are preserved.

### B. Verification Tests

**Test 1: FIXED autotrader replication (Phase 2)**
- Enable CSV test mode (Input[14]) on ATEAM_ZONE_BOUNCE_FIXED
- Load NQ_merged_P1a.csv + NQ_merged_P1b.csv (unchanged 37-column merged format)
- Must produce 85/85 matching trades
- Compare `ATEAM_CSV_TEST_FIXED_trades.csv` against baseline

**Test 2: ZONEREL autotrader replication (Phase 2)**
- Same procedure, must produce 77/77 matching trades
- Compare `ATEAM_CSV_TEST_ZONEREL_trades.csv` against baseline

**Test 3: Raw CSV column validation (Phase 1/3)**
- Consolidated raw CSV must contain all 33 ZRA columns (same names)
- Consolidated raw CSV must contain all 30 ZB4 columns (same names)
- 17 overlapping columns must have identical values (cross-check on P1 data)
- New columns (48-51) must be present; non-zero on bars with nearby broken zones

**Test 4: Merged CSV preservation (Phase 3)**
- `run_zone_prep.py` output must produce identical 37-column merged CSV
- Column order frozen at indices 0-36
- Diff against current NQ_merged_P1a.csv — must match

**Test 5: Pipeline regression (Phase 3)**
- `pytest tests/` — all tests pass
- `generate_p1_answer_keys.py` — output matches existing answer keys byte-for-byte

**Test 6: Ray verification (Phase 5)**

> V4 SG 12/13 were never fetched before — no Python answer key exists.
> RayValidator.cpp (built in Phase 1) provides the reference data.

**Ray verification approach:**

a) **Raw ray price validation:**
   - Compare consolidated study's ray accumulator output against RayValidator reference CSV
   - Every non-zero value in RayValidator CSV must appear in the consolidated study's accumulated ray list
   - No phantom rays (rays not in reference)

b) **TF tagging for broken zone rays:**
   - V4 SG 12/13 output the broken zone's edge price but NOT the zone's source timeframe
   - The timeframe is inferred: on break detection (SG 6/7 increment), look up the breaking zone in the TrackedZone array by matching TopPrice/BottomPrice. The zone's SourceSlot gives the TF.
   - **Verification:** On a sample day, manually check 5-10 broken zones on chart — confirm the TF label in ray_context.csv matches the zone's visual timeframe on the V4 display

c) **Completeness check:**
   - Pick 3 sample days from P1 with known zone breaks (ZoneBroken=1 in ZRA CSV)
   - Count broken zones per day in ZRA CSV (ZoneBroken column)
   - Count ray events per day in RayValidator reference CSV
   - Count ray entries in ray_context.csv
   - All three counts must be consistent

d) **ray_context.csv validation:**
   - For each touch, verify proximity filter: no ray outside 2x max zone width
   - Verify RayDirection (ABOVE/BELOW) is correct relative to touch zone edge
   - Verify RayAgeBars = touch bar - break bar

**If automated ray verification is not feasible in Phase 5:**
Manual spot-check protocol:
- Check 3 trading days (1 low-volatility, 1 medium, 1 high)
- For each day: count all V4 rays visible on chart, count all ray prices in CSV
- Verify 5 ray prices match V4's drawn ray levels exactly (to tick)
- Document results in `ray_verification_spotcheck.md`
- Flag automated verification as follow-up task

### C. Rollback Plan

**If consolidation fails at any phase:**

| Phase | Rollback |
|-------|----------|
| Phase 1 (additive) | Remove consolidated study + RayValidator from chart. ZRA + ZB4 still running. No data impact. |
| Phase 2 (autotrader switch) | Revert autotrader Input[0] to ZB4 study ID. Re-run test mode to confirm 85/85 and 77/77. |
| Phase 3 (pipeline switch) | `git checkout` run_zone_prep.py and test files. Re-run pipeline tests. |
| Phase 4 (deprecation) | Move files back from `_deprecated/`. Re-add ZRA + ZB4 to chart. |
| Nuclear | `git checkout v1.0-pre-merge` (or v3.0-pre-merge). Restore _v31 backups to chart. Full revert. |

**Safety:** Phase 1 is fully additive — the consolidated study runs alongside ZRA+ZB4 with no impact. The dangerous moment is Phase 2 (autotrader switch). Keep ZB4 on chart but disabled during Phase 2 testing so it can be re-enabled instantly.

---

## Step 4: Ray Integration Design

### A. Ray Data Exposure

**Both chart drawing AND CSV columns.**

Chart drawing — the trader needs to see broken zone rays visually:
- Draw horizontal rays at DemandRayPrice (blue, dashed) and SupplyRayPrice (red, dashed)
- Drawn via `sc.UseTool()` (same pattern V4 uses for its own rays)
- The consolidated study's ray drawing is separate from V4's — gives the trader control over visibility

CSV columns — the pipeline needs ray data for analysis:
- Raw CSV: nearest ray prices + distances (4 summary columns, cols 48-51)
- ray_context.csv: full long-format ray picture for feature engineering

Note: Output subgraphs (0-19) do NOT include ray prices as subgraph data — rays are drawn as chart tools, not subgraph values. The CSV is the analytical data path.

### B. Ray Accumulation Logic

V4 SG 12/13 only emit on break bars (zero otherwise). The consolidated study maintains a persistent array of all broken zone ray prices:

- On each bar, check if SG 12 or SG 13 is non-zero → add to ray accumulator
- Each accumulated ray stores: price, side (DEMAND/SUPPLY), break bar index, source TF (inferred from TrackedZone), source zone top/bot
- **Rays persist indefinitely** (Decision #2). No session purge. V4 draws them indefinitely by design. Python pipeline filters by age/distance during analysis.
- Max ray capacity: 2000 (same order as TrackedZone[10000] — broken zones are a subset of all zones)

### C. Ray-Derived Data

**In C++ raw CSV (framework-independent):**

| Column | Type | Description |
|--------|------|-------------|
| DemandRayPrice | float | Nearest broken demand zone ray price to TouchPrice |
| SupplyRayPrice | float | Nearest broken supply zone ray price to TouchPrice |
| DemandRayDistTicks | float | `abs(TouchPrice - DemandRayPrice) / TickSize` |
| SupplyRayDistTicks | float | `abs(TouchPrice - SupplyRayPrice) / TickSize` |

**In C++ ray_context.csv (long format):**

| Column | Type | Description |
|--------|------|-------------|
| TouchID | str | `BarIndex_TouchType_SourceLabel` |
| RayPrice | float | Broken zone edge price |
| RaySide | str | DEMAND or SUPPLY |
| RayDirection | str | ABOVE or BELOW (relative to touch zone edge) |
| RayDistTicks | float | Distance from touch zone edge |
| RayTF | str | Source timeframe of broken zone (e.g. 30m, 120m) |
| RayAgeBars | int | Bars since zone broke |

Proximity filter: rays within `2 × max_zone_width` of TouchPrice.

**Computed in Python (entry-context-dependent — Issue 3):**

| Feature | Description | Why Python |
|---------|-------------|-----------|
| RaysBetweenEntryTarget | Count of rays in [entry, T1] range | Depends on autotrader config (FIXED vs ZONEREL) |
| NearestRayDir | +1 overhead / -1 below / 0 none | Relative to entry price, not touch price |
| RayDensity | Rays within N ticks of entry | Aggregated from ray_context.csv |
| RayCluster | Are rays concentrated in a narrow band? | Statistical computation |

### D. Subgraphs 0-5 (Zone Creation Signals)

**Decision:** Fetch and store internally only (Decision #4).

SG 0-5 fire on the bar where V4 creates a new zone (signal=1, zone top/bot). Useful for zone formation pattern analysis but redundant for touch detection (SG 8-11 provide nearest active zone). Not exposed as output subgraphs or CSV columns in v4.0. Add later if analytical need arises.

---

## Step 5: Summary

### Estimated Effort

| Item | Files | Est. Lines |
|------|-------|-----------|
| ZoneTouchEngine.cpp (new) | 1 | ~1770 new |
| RayValidator.cpp (test tool) | 1 | ~100 new |
| run_zone_prep.py (simplify merge) | 1 | ~50 changed |
| test_data_loader.py (column count) | 1 | ~5 changed |
| data_registry.md | 1 | ~10 changed |
| zone_csv_unified_schema.md (new) | 1 | ~60 new |
| STUDY_CHAIN_REFERENCE.md | 1 | ~30 changed |
| Chart configuration (manual) | — | Manual SC steps |
| **Total** | **7 files** | **~2025 lines** |

### Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Persistent storage struct mismatch | Medium | **CRITICAL** — autotrader reads garbage | Byte-for-byte struct comparison; test mode gate |
| Magic number mismatch | Low | CRITICAL — autotrader gets nullptr | Compile-time constant; same value in both files |
| Merged CSV column order shift | Medium | HIGH — autotrader CSV parser reads wrong fields | run_zone_prep.py must emit identical 37-col merged format; diff test |
| SC study execution order wrong | Medium | HIGH — autotrader reads stale data | Manual verification; document chart setup steps |
| Ray accumulator unbounded growth | Low | Medium — memory pressure over long sessions | Cap at 2000 rays; oldest evicted if full |
| Touch detection subtle divergence | Low | Medium — different touch count | Side-by-side comparison during Phase 1 (all three studies running) |
| SC remote build failure (file too large) | Low | Low — can split into sections | 1770 lines is well within SC limits |
| ray_context.csv large file size | Low | Low — proximity filter bounds row count | 2x max zone width filter; ~6 rays/touch × ~5000 touches = ~30K rows max |

### Critical Path

```
Phase 1 (additive + ray validator — safe)
  └→ Phase 2 (autotrader switch — highest risk)
       └→ Phase 3 (pipeline switch)
            └→ Phase 4 (deprecation + dead code cleanup)
                 └→ Phase 5 (ray verification using Phase 1 reference data)
```

Phase 2 is the single highest-risk step. The persistent storage struct layout between ZoneTouchEngine and the autotraders must be byte-identical. Any padding, alignment, or field order difference causes silent data corruption.

### Revision History

| Rev | Date | Changes |
|-----|------|---------|
| 1 | 2026-03-23 | Initial plan |
| 2 | 2026-03-23 | Decisions 1-5 incorporated. Issue 1: ray_context.csv long format added. Issue 2: raw vs merged CSV terminology clarified throughout. Issue 3: RaysBetweenEntryTarget + NearestRayDir removed from C++ output, noted as Python-computed. Issue 4: RayValidator.cpp moved to Phase 1. Column count 54→52. |
