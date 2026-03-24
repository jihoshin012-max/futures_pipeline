ZRA + ZB4 consolidation — planning phase.

⚠️ Do NOT build anything yet. Produce a plan for review.

CONTEXT:
Two studies currently do overlapping work against V4:

ZRA (ZoneReactionAnalyzer.cpp) — measurement tool:
- Detects zone touches (demand edge, supply edge, VP ray)
- Tracks reaction and penetration over time
- Exports CSV for offline backtesting (pipeline data source)
- No scoring, no mode assignment, no trading logic

ZB4 (ZoneBounceSignalsV4_aligned.cpp) — scoring + signals:
- Detects zone touches (demand edge, supply edge only)
- Computes A-Cal scoring (quality score, context score, modes)
- TF confluence, cascade state, session, trend context
- Draws stop/target rays and signal labels on chart
- Exports CSV with scoring columns

OVERLAP:
- Both fetch V4 subgraphs 6-11 and 14
- Both detect zone touches using nearly identical logic
- Both run on the same chart against the same V4 instance
- VP proximity filter had to be applied to both separately

⚠️ The consolidation eliminates this duplication. One study, 
one touch detection pass, one CSV export, one place to maintain.

WHAT'S MISSING FROM BOTH:
V4 exposes 15 subgraphs (0-14). Both studies skip:
- SG 0: DemandSignal
- SG 1: DemandZoneTop
- SG 2: DemandZoneBot
- SG 3: SupplySignal
- SG 4: SupplyZoneTop
- SG 5: SupplyZoneBotB
- SG 12: DemandRayPrice (broken zone edge levels)
- SG 13: SupplyRayPrice (broken zone edge levels)

The ray subgraphs (12, 13) store the price level where broken 
zones sit. This data has analytical value — a bounce zone 
with a broken zone ray 30t overhead faces resistance. Connects 
to autoresearch item 6 (screening rejects as filters) and the 
zone break strategy seeds.

GOAL:
Merge ZRA + ZB4 into a single consolidated study that:
1. Fetches ALL 15 V4 subgraphs (0-14) — never silently drops 
   useful data again
2. Performs touch detection ONCE (shared logic)
3. Computes scoring (A-Cal, mode routing)
4. Tracks reaction/penetration (ZRA's measurement function)
5. Exports a single unified CSV with both scoring AND 
   measurement columns, plus ray price data
6. Draws chart overlays (signals, stop/target levels)
7. Does NOT break either autotrader (FIXED or ZONEREL)

⚠️ This is a PLANNING prompt. Do not write any code. Produce 
a plan document for review before any implementation begins.

CONSTRAINTS:
- Tags v1.0-pre-merge and v3.0-pre-merge mark the baseline
- After consolidation, both autotraders must re-pass their 
  C++ test modes (FIXED 85/85, ZONEREL 77/77)
- The autotraders read from the consolidated study's subgraphs 
  and/or CSV output — any subgraph index change breaks them
- _v31 backup files of ZRA and ZB4 exist (gitignored) as 
  rollback — do not delete these until consolidation passes

================================================================
STEP 1: DEPENDENCY MAPPING
================================================================

Before designing the consolidated study, map what depends 
on ZRA and ZB4:

⚠️ Be thorough here — missing a dependency means a silent 
break after migration. Check every .cpp, .py, and .h file 
in the pipeline.

A) For ZRA, list:
   - Every file that imports/reads ZRA CSV output
   - Every study that references ZRA subgraphs on the chart
   - The autotrader's dependency on ZRA (if any)
   - The replication harness dependency on ZRA output

B) For ZB4, list:
   - Every file that imports/reads ZB4 CSV output
   - Every study that references ZB4 subgraphs on the chart
   - The autotrader's dependency on ZB4 (subgraph indices, 
     signal data)
   - The replication harness dependency on ZB4 output

C) For V4, list:
   - All 15 subgraph indices and names
   - Which are currently fetched by ZRA
   - Which are currently fetched by ZB4
   - Which subgraphs the autotraders read directly from V4 
     (vs through ZRA/ZB4)

D) Chart study execution order:
   - What is the current study order on the chart?
   - Which studies must run BEFORE the autotrader?
     (V4 → ZB4 → autotrader is the expected chain)
   - If the consolidated study has a different name, does 
     Sierra Chart reorder studies alphabetically or by 
     insertion order?
   - Confirm the autotrader will still execute AFTER the 
     consolidated study in the chain

⚠️ The autotrader subgraph dependencies are the critical 
path. If ATEAM_ZONE_BOUNCE_FIXED.cpp reads ZB4 subgraph 
index 3 for signal data, the consolidated study MUST expose 
the same data at the same index — or the autotrader needs 
updating too.

================================================================
STEP 2: CONSOLIDATED STUDY DESIGN
================================================================

Propose the architecture:

A) Name: what should the consolidated study be called?

B) Subgraph layout: list every output subgraph the 
   consolidated study will expose, with index numbers. 
   Ensure backward compatibility with autotrader expectations 
   OR list every autotrader line that needs updating.

C) CSV output format: define the unified column set.
   - All current ZRA columns (measurement)
   - All current ZB4 columns (scoring)
   - New columns: DemandRayPrice, SupplyRayPrice, plus any 
     other V4 data currently dropped (SG 0-5)
   - Column ordering
   ⚠️ The replication harness and autotrader CSV test modes 
   read specific columns by name. List any column renames.

D) Touch detection: describe the shared touch detection logic.
   - Where ZRA and ZB4 touch detection differs currently
   - How to unify (pick one, merge both, or refactor)
   - VP proximity filter location

E) Code structure: 
   - Single .cpp file or .cpp + .h?
   - Estimated line count
   - Which ZRA functions are preserved, which ZB4 functions 
     are preserved, what's new

📌 REMINDER: The autotraders must re-pass their C++ test 
modes after this change. Any subgraph index shift or CSV 
column change that affects the autotrader's data path must 
be explicitly called out.

================================================================
STEP 3: MIGRATION PLAN
================================================================

A) What is the exact sequence of changes?
   - New files created
   - Old files deprecated (not deleted — kept as _v31 backups)
   - Autotrader files modified (if subgraph indices change)
   - Pipeline Python files modified (if CSV columns change)
   - Chart configuration changes (studies to add/remove)
   - Chart study ordering: confirm consolidated study runs 
     BEFORE autotrader in the execution chain. If renaming 
     changes the order, document the manual reorder step.

B) What tests confirm the migration succeeded?
   - FIXED C++ test mode: 85/85 must still pass
   - ZONEREL C++ test mode: 77/77 must still pass
   - Any additional tests (CSV column validation, etc.)

C) What's the rollback plan if the migration fails?
   - git checkout to v1.0-pre-merge / v3.0-pre-merge tags
   - Restore ZRA + ZB4 _v31 backups on chart
   - Any chart configuration to undo

⚠️ The consolidated study should be additive at first — 
produce a SUPERSET of what ZRA and ZB4 currently produce. 
Do not remove any existing output column or subgraph until 
after both autotraders re-pass their tests. Deprecate, then 
remove in a later commit.

================================================================
STEP 4: RAY INTEGRATION DESIGN
================================================================

For the new ray subgraphs (SG 12, 13):

A) How should the ray data be exposed?
   - As consolidated study subgraphs (chart-visible)?
   - As CSV columns only (pipeline consumption)?
   - Both?

B) What derived features could be computed from ray data?
   - Distance from current price to nearest broken zone ray
   - Number of broken zone rays between entry and target
   - Ray as resistance/support for bounce target estimation
   - Any other analytical value

⚠️ Do NOT implement derived features now. Just document 
what's possible. These feed the autoresearch queue.

C) For subgraphs 0-5 (zone signal, zone top/bot):
   - Are these useful for the consolidated study or redundant 
     with subgraphs 8-11 (nearest zone boundaries)?
   - Should they be fetched and stored but not exposed as 
     output subgraphs?

================================================================
STEP 5: DELIVERABLE
================================================================

Produce: ZRA_ZB4_CONSOLIDATION_PLAN.md containing:
- Dependency map (Step 1)
- Architecture design (Step 2) 
- Migration sequence (Step 3)
- Ray integration design (Step 4)
- Estimated effort (number of files changed, lines of code)
- Risk assessment (what's most likely to break)

Do NOT write any code. This is a planning document for review.
