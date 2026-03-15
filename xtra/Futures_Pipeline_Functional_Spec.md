# Futures Pipeline — Functional Specification
> **Version:** 1.0 | **Date:** 2026-03-11 | **Status:** Ready to build
> **Architecture ref:** Futures_Pipeline_Architecture_ICM.md
> **Anti-lost-in-middle design:** Master checklist at top AND bottom. Each task: constraint first, spec second, done-check last. Sections ≤40 lines.

---

## MASTER BUILD CHECKLIST (authoritative — check here, not the body)

### Before anything:
- [ ] P0-1: Existing strategy deployment (parallel — skip for new strategy from scratch)
- [ ] P0-2: RinDig ICM repo fetched and reviewed
- [ ] P0-3: karpathy/autoresearch repo fetched and reviewed
- [ ] P0-4: Q1–Q6 answered (needed for Pass 2 only — don't block Pass 1)

### Pass 1 — Scaffold:
- [ ] 1-01: Root folder structure created
- [ ] 1-02: `CLAUDE.md` written (≤60 lines, five rules in first 20)
- [ ] 1-03: Root `CONTEXT.md` routing file written
- [ ] 1-04: `_config/instruments.md`
- [ ] 1-05: `_config/data_registry.md`
- [ ] 1-06: `_config/period_config.md`
- [ ] 1-07: `_config/pipeline_rules.md` (all five rules including Rule 4 + Rule 5)
- [ ] 1-08: `_config/statistical_gates.md` (includes multiple testing limits)
- [ ] 1-09: `_config/regime_definitions.md`
- [ ] 1-09b: `stages/01-data/hmm_regime_fitter.py` + initial `regime_labels.csv`
- [ ] 1-10: `_config/context_review_protocol.md` (includes lost-in-middle rules)
- [ ] 1-11: `shared/feature_definitions.md`
- [ ] 1-11b: `02-features/references/feature_rules.md`
- [ ] 1-11c: `02-features/references/feature_catalog.md`
- [ ] 1-12: `shared/scoring_models/` directory + scoring model template schema
- [ ] 1-13: `shared/scoring_models/` — archetype-specific supplementary configs (if needed)
- [ ] 1-14: Stage 01 folder + `CONTEXT.md`
- [ ] 1-14b: Stage 01 reference files (schema doc per source_id + `bar_data_schema.md`)
- [ ] 1-14c: `data_manifest.json` schema specification
- [ ] 1-15: Stage 02 folder + `CONTEXT.md`
- [ ] 1-16: Stage 03 folder + `CONTEXT.md`
- [ ] 1-17: Stage 04 folder + `CONTEXT.md`
- [ ] 1-17b: `shared/archetypes/{archetype}/exit_templates.md`
- [ ] 1-18: Stage 05 folder + `CONTEXT.md`
- [ ] 1-18b: Stage 05 reference files (`verdict_criteria.md`, `statistical_tests.md`)
- [ ] 1-19: Stage 06 folder + `CONTEXT.md`
- [ ] 1-19b: Stage 06 supporting files (`context_package_spec.md`, `assemble_context.sh`)
- [ ] 1-20: Stage 07 folder + `CONTEXT.md`
- [ ] 1-20b: `07-live/triggers/review_triggers.md`
- [ ] 1-21: `dashboard/results_master.tsv` schema stub
- [ ] 1-22: `dashboard/index.html` stub
- [ ] 1-23: Migrate existing data files to `01-data/data/`
- [ ] 1-24: Migrate existing verdict reports to `05-assessment/output/`
- [ ] 1-25: `audit/audit_log.md` stub
- [ ] 1-26: `audit/audit_entry.sh`
- [ ] 1-27: `03-hypothesis/references/strategy_archetypes.md`

### Pass 1.5 — Git + audit infrastructure:
- [ ] 1.5-01: `autocommit.sh`
- [ ] 1.5-02: `.git/hooks/pre-commit` (holdout guard + audit auto-entries + period rollover warning)
- [ ] 1.5-03: `.git/hooks/post-commit` (commit log + OOS_RUN + DEPLOYMENT_APPROVED)
- [ ] 1.5-04: Hooks verified working (chmod, test run)

### Pass 2 — Backtest engine (blocked on Q1–Q6):
- [ ] 2-01: Q1–Q6 answered and documented
- [ ] 2-02: `data_loader.py` patched (5 hardcoded paths parameterized)
- [ ] 2-03: `backtest_engine.py` written (~175–225 lines)
- [ ] 2-04: `config_schema.json` reference config written
- [ ] 2-05: `config_schema.md` field documentation written
- [ ] 2-06: Determinism verified (identical config → identical output, diffed)
- [ ] 2-07: Manual end-to-end pass run (01 → 04 → 05)
- [ ] 2-08: `shared/archetypes/{archetype}/simulation_rules.md` written

### Pass 3 — Autoresearch loops:
- [ ] 3-01: Stage 04 driver script written + overnight test run
- [ ] 3-02: `02-features/autoresearch/evaluate_features.py` written
- [ ] 3-03: Stage 02 driver script written + overnight test run
- [ ] 3-04: `03-hypothesis/autoresearch/hypothesis_generator.py` written
- [ ] 3-05: Stage 03 driver script written + overnight test run
- [ ] 3-06: Feedback loop wired (Stage 05 → `prior_results.md` → Stage 03)
- [ ] 3-07: Dashboard — DEFERRED to Milestone 2 (see Futures_Pipeline_Dashboard_Spec.md)

---

## PART 0: PREREQUISITES

**P0-1, P0-2, P0-3 must be done before Pass 1 starts. P0-4 (Q1–Q6) is Pass 2 only — do not block scaffold work.**

### P0-1: Existing strategy deployment (PARALLEL — skip entirely for new strategy from scratch)

**If building from scratch with no prior strategy: skip this task. Stage 07 starts empty.**

If migrating an existing strategy into the pipeline:
These items run in parallel with Pass 1. They do not block scaffold work.
The only dependency: `07-live/data/paper_trades.csv` needs the live strategy to populate.

- Implement the strategy in its ACSIL `.cpp` file
- Resolve any pending system state (e.g. buffered signals, indicator resets)
- Copy the `.cpp` file to `stages/06-deployment/references/{strategy_id}_reference.cpp` — this becomes the archetype's structural reference for future ACSIL generation

**Target:** Complete before end of Pass 1 so Stage 07 monitoring starts immediately.
**Does NOT block:** Pass 1 scaffold, Pass 1.5 git hooks, Pass 2 backtest engine, Pass 3 loops.
**From scratch:** Stage 07 monitoring begins only after Pass 3 + first strategy deployed.

---

### P0-2: Fetch RinDig ICM repo
```
git clone https://github.com/RinDig/Interpreted-Context-Methdology
```
Review: CLAUDE.md format, CONTEXT.md stage contract format, any naming conventions that differ from this spec. Update this spec before writing any CONTEXT.md files if conventions differ.

**DONE CHECK:** ICM repo reviewed, any convention conflicts resolved in this spec.

---

### P0-3: Fetch karpathy/autoresearch repo
```
git clone https://github.com/karpathy/autoresearch
```
Review specifically:
- `program.md` format — how steering instructions are written
- `train.py` keep/revert logic — exact pattern the driver scripts in Pass 3 must mirror
- Overnight run protocol — any conventions around logging, exit conditions, error handling

The three autoresearch driver scripts (Tasks 3-01, 3-02, 3-03) are direct implementations of this pattern. Read the source before writing any driver.

**DONE CHECK:** `program.md` and keep/revert logic reviewed. Any deviations from Karpathy's pattern intentional and documented in driver script comments.

---

### P0-4: Answer Q1–Q6 (Pass 2 only — do not block Pass 1)
Document answers in `04-backtest/references/backtest_engine_qa.md` before writing `backtest_engine.py`.

| Q | Question | Answer |
|---|----------|--------|
| Q1 | Does data_loader load P1+P2 simultaneously or one period at a time? | One at a time. Path-based API — engine takes explicit file paths, no period awareness. |
| Q2 | Is the scoring model grid dynamic (percentile bins) or static (fixed param grid)? | Hybrid. 7 features static, 7 use P1 tercile bins. Bins frozen in scoring model JSON (bin_edges field). Engine calls `adapter.score()` via `BinnedScoringAdapter` — never recomputes bins from data. |
| Q3 | TrailStep fields? Should trail rules be optimizable or frozen? | Optimizable. Array of {trigger_ticks, new_stop_ticks} in config. be_trigger_ticks removed — redundant with trail_steps[0]. Validation rules in config_schema.md. |
| Q4 | Does routing waterfall run all modes or skip inactive ones? Single-mode flag needed? | Route all, simulate selectively. Config presence = mode active. No router changes needed. |
| Q5 | Should backtest_engine.py inherit the holdout_locked.flag guard? | Yes. Engine aborts if flag exists and P2 paths detected in config. |
| Q6 | Does output JSON need per-mode PF breakdown, or top-level PF + n_trades sufficient? | Per-mode breakdown required. Top-level PF drives keep/revert; per-mode is diagnostic. |

**DONE CHECK:** All six rows filled. Answers committed to `backtest_engine_qa.md`.

---

## PART 1: PASS 1 — SCAFFOLD

**Constraint: no pipeline Python code required for any task in this pass.**
**Constraint: apply lost-in-middle authoring rules to every file written.**
  - Operative instruction in first 5 lines
  - CLAUDE.md ≤60 lines, CONTEXT.md ≤80 lines, program.md ≤30 lines
  - Local repetition: each CONTEXT.md restates its own critical constraints

---

### Task 1-01: Create root folder structure

```bash
mkdir -p futures-pipeline/{_config,shared/{scoring_models,archetypes/{archetype},onboarding},dashboard,archive}
mkdir -p futures-pipeline/shared/archetypes/{archetype}  # feature_evaluator.py + feature_engine.py live here
mkdir -p futures-pipeline/stages/{01-data/{references,data/{touches,bar_data/{volume,time,tick},labels},output},02-features/{references,autoresearch/current_best,output},03-hypothesis/{references,autoresearch/current_best,output/promoted_hypotheses},04-backtest/{references,autoresearch/current_best,output,p2_holdout},05-assessment/{references,output},06-deployment/{references,output},07-live/{data,output,triggers}}
mkdir -p futures-pipeline/audit
git init futures-pipeline && cd futures-pipeline
```

Create `requirements.txt` in the repo root immediately after git init — before writing any pipeline code:

```
# Futures Pipeline — Python dependencies
# Install: pip install -r requirements.txt
# Update this file when adding new stages or adapters.

# Core data
pandas>=2.0.0
numpy>=1.24.0
scipy>=1.10.0          # MWU test, permutation test (Stage 02, Stage 05)

# Machine learning
scikit-learn>=1.3.0    # SklearnScoringAdapter, feature bin calibration (Stage 02, Stage 04)
hmmlearn>=0.3.0        # HMM regime fitter (Stage 01 Task 1-09b — mandatory Pass 1)

# Technical analysis
pandas-ta>=0.3.14b     # Technical indicators for Stage 02 feature_engine.py
                       # and Stage 01 HMM regime fitter (ADX, ATR, VWAP etc.)
                       # Entry-time rule still applies — truncate bar_df at
                       # entry bar before calling any pandas-ta function

# Visualization
matplotlib>=3.7.0      # Stage 05 equity curves, Stage 07 drift reports
                       # Not required for core pipeline execution
```

Then install:
```bash
pip install -r requirements.txt
```

**DONE CHECK:** `find . -type d | head -40` shows full tree. Git initialized. `pip install -r requirements.txt` completes without error.

---

### Task 1-02: CLAUDE.md

**CRITICAL: Five rules and hard prohibitions in first 20 lines. ≤60 lines total.**

```markdown
# CLAUDE.md — Futures Pipeline Agent Identity
last_reviewed: 2026-03-11

## YOU ARE
A trading strategy research assistant operating inside the futures pipeline.
You run inside specific stage directories. You do not have visibility across all stages.

## FIVE PIPELINE RULES (never violate)
1. P1 calibrate — IS data used freely for calibration and search
2. P2 one-shot — OOS runs exactly once with frozen params; never re-run
3. Entry-time only — features must be computable at entry time; no lookahead
4. Internal replication — strategy must pass P1b before P2 is unlocked
5. Instrument constants from registry — read tick size, cost_ticks, session times from _config/instruments.md; never hardcode

## HARD PROHIBITIONS
- NEVER modify backtest_engine.py
- NEVER run any script against P2 data if holdout_locked_P2.flag exists
- NEVER delete or modify audit/audit_log.md entries
- NEVER modify _config/ files without human instruction
- NEVER hardcode instrument constants (tick size, cost_ticks, session times) — read from _config/instruments.md

## STAGE ROUTING
Read your stage's CONTEXT.md to understand your current task.
Each stage CONTEXT.md tells you: what to read, what to edit, what metric to optimize.

## AUTORESEARCH RULE
You edit exactly ONE file per experiment (specified in your stage CONTEXT.md).
You run the fixed harness. You read the result. You keep or revert. You log to results.tsv.

## CONVENTIONS
Every archetype-specific Python file you write must include on line 1: `# archetype: {name}`
```

**DONE CHECK:** Line count ≤60. Five rules present in first 20 lines. Hard prohibitions present.

---

### Task 1-03: Root CONTEXT.md (routing file)

**CRITICAL: First 5 lines identify current active stage. ≤80 lines.**

```markdown
---
last_reviewed: 2026-03-11
reviewed_by: Ji
---
# CONTEXT.md — Pipeline Router

## CURRENT ACTIVE STAGE
→ Stage 01: Data Foundation (Pass 1 scaffold — no autoresearch yet)

## TO START WORK
1. Read CLAUDE.md (global rules)
2. Read stages/{active_stage}/CONTEXT.md (your task)
3. Read stages/{active_stage}/autoresearch/program.md (if autoresearch stage)

## STAGE STATUS
| Stage | Status | Notes |
|-------|--------|-------|
| 01-data | Active | Scaffold complete; awaiting data migration |
| 02-features | Not started | Pending Pass 2 |
| 03-hypothesis | Not started | Pending Pass 3 |
| 04-backtest | Not started | Pending Pass 2 |
| 05-assessment | Not started | |
| 06-deployment | Not started | |
| 07-live | Active — monitor only | Paper trades accumulating |

## HUMAN CHECKPOINTS (never skip)
- Before P2 run: confirm holdout_locked_P2.flag does NOT exist
- Before hypothesis promotion: review results.tsv top 3–5 manually
- Before deployment: compile, verify on replay, confirm params match frozen_params.json
```

**DONE CHECK:** Active stage correctly set. File ≤80 lines.

---

### Task 1-04: `_config/instruments.md`

```markdown
# Instrument Registry
last_reviewed: 2026-03-11

## THE RULE
Every instrument-specific constant must be read from this file.
No pipeline script may hardcode tick size, dollar value, session times, or cost_ticks.
If the value is not here, add it first, then reference it.

## Registered Instruments

### NQ
- Symbol: NQ (CME E-mini NASDAQ-100)
- Tick size: 0.25 points
- Tick value: $5.00
- Session: RTH 09:30–16:15 ET | ETH 18:00–09:30 ET
- Cost model (round trip): 3 ticks = $15.00
- Bar data prefix: NQ_BarData
- Margin: check current at CME (varies)

### ES
- Symbol: ES (CME E-mini S&P 500)
- Tick size: 0.25 points
- Tick value: $12.50
- Session: RTH 09:30–16:15 ET | ETH 18:00–09:30 ET
- Cost model (round trip): 1 tick = $12.50
- Bar data prefix: ES_BarData
- Margin: check current at CME (varies)

### GC
- Symbol: GC (CME Gold Futures)
- Tick size: 0.10 points
- Tick value: $10.00
- Session: 18:00–17:00 ET (nearly 24hr, Sunday–Friday)
- Cost model (round trip): 2 ticks = $20.00
- Bar data prefix: GC_BarData
- Margin: check current at CME (varies)

## To Add a New Instrument
1. Add a block above following the template
2. Add bar data files to 01-data/data/bar_data/{volume|time|tick}/ — use the subfolder matching the bar type
3. Re-run Stage 01 validation
Cost model values require human approval — changing them affects all historical PF calculations.

## Template for new instrument
### {SYMBOL}
- Symbol: {SYMBOL} ({exchange} {full name})
- Tick size: {N} points
- Tick value: ${N}
- Session: {session hours}
- Cost model (round trip): {N} ticks = ${N}
- Bar data prefix: {SYMBOL}_BarData
- Margin: check current at {exchange} (varies)
```

**DONE CHECK:** File exists. At least one instrument block present with all required fields. Cost model present with warning note.

---

### Task 1-05: `_config/data_registry.md`

**CRITICAL: This is the only place data sources are registered. No stage hardcodes paths.**

```markdown
# Data Registry
last_reviewed: 2026-03-11

## THE RULE
No stage hardcodes file paths. All paths come from data_manifest.json (Stage 01 output),
which is generated from this registry.

## Registered Sources

| source_id    | type       | description                         | periods | file_pattern                    | required_by              |
|--------------|------------|-------------------------------------|---------|----------------------------------|--------------------------|
| {source_id}  | {type}     | {description}                       | P1, P2  | {source_id}_*.{ext}             | {stage list}             |
| bar_data_volume | price   | 250-vol OHLCV bars (zone_touch)     | P1, P2  | {SYMBOL}_BarData_250vol_*.txt   | 02-features, 04-backtest |
| bar_data_time   | price   | 1-min time OHLCV bars               | P1, P2  | {SYMBOL}_BarData_1min_*.txt     | {future strategies}      |
| bar_data_tick   | price   | Tick OHLCV bars                     | P1, P2  | {SYMBOL}_BarData_tick_*.txt     | {future strategies}      |

Note: Add one row per data source your archetype requires. `source_id` must be unique and
match the schema file name in `01-data/references/{source_id}_schema.md`.
The `periods` column lists which period_ids (from period_config.md) this source covers.
Use archetype-specific period_ids (e.g. P1_rot) if the source only covers that archetype's date range.

## Data Type Taxonomy
| type        | description                            |
|-------------|----------------------------------------|
| touches     | Per-touch or per-signal event data     |
| price       | OHLCV bar data                         |
| label       | Derived classification labels          |
| orderflow   | Intrabar volume/delta data             |
| fundamental | Macro/economic data                    |
| alt         | Anything else                          |

## To Add a New Source
1. Drop files into 01-data/data/<source_id>/
2. Add row to this table
3. Re-run Stage 01 validation
4. Human checkpoint: review validation report
```

**DONE CHECK:** File exists. All archetype data sources registered. Bar data registered with typed source_ids (bar_data_volume, bar_data_time, bar_data_tick) — not a single bar_data row. Each source_id has a matching schema file in `01-data/references/`.

---

### Task 1-06: `_config/period_config.md`

**CRITICAL: This is the ONLY place IS/OOS boundaries are defined. Never edit mid-run.**

```markdown
# Period Configuration
last_reviewed: 2026-03-11
# NEVER edit this file mid-run. Only update between complete pipeline runs.
# After editing: re-run Stage 01, update data_manifest.json.

## Active Periods

| period_id | archetype   | role | start_date | end_date   | notes                         |
|-----------|-------------|------|------------|------------|-------------------------------|
| P1        | zone_touch  | IS   | 2025-09-16 | 2025-12-14 | Calibration — used freely     |
| P2        | zone_touch  | OOS  | 2025-12-15 | 2026-03-02 | Holdout — one-shot only       |
| P1        | rotational  | IS   | 2025-09-21 | 2025-12-14 | Calibration — used freely     |
| P2        | rotational  | OOS  | 2025-12-15 | 2026-03-13 | Holdout — one-shot only       |

# archetype column is optional — use '*' to apply a period to all archetypes.
# If an archetype is not listed, it inherits the '*' rows.
# Archetype-specific rows take precedence over '*' rows.
# Stage 01 reads this table and writes per-archetype period boundaries
# into data_manifest.json["archetypes"][{name}]["periods"].

## Rules (do not change)
- IS: used freely for calibration, hypothesis search, parameter optimization
- OOS: used for final one-shot validation only; never re-run after first use
- OOS periods become IS when a new OOS period is designated

## Rolling Forward (when P3 arrives ~Jun 2026)
1. Add P3 row per archetype (role: OOS) — or a single P3 row with archetype: '*' if dates are the same
2. Change P2 role to IS per archetype (after each archetype's one-shot OOS test is complete)
3. Re-run Stage 01 validation
4. No code changes needed

## Internal Replication Sub-periods (Rule 4)
p1_split_rule: midpoint
# Stage 01 computes P1a and P1b dynamically from P1 start/end using this rule.
# p1_split_rule options: midpoint | 60_40 | fixed_days:<N>
#   midpoint   — P1a = first half of P1, P1b = second half (default)
#   60_40      — P1a = first 60% of P1, P1b = last 40%
#   fixed_days:<N> — P1a = first N days, P1b = remainder
# When P1 rolls forward the split auto-updates — no manual date editing.
# Current computed split (informational, written by Stage 01 into data_manifest.json):
#   P1a = 2025-09-16 to 2025-10-31 | P1b = 2025-11-01 to 2025-12-14
replication_gate: flag_and_review
# replication_gate options: hard_block | flag_and_review
#   hard_block     — P1b fail = NO verdict, do not advance to P2
#   flag_and_review — P1b fail = WEAK_REPLICATION flag, human decides whether to advance
# flag_and_review is recommended when P1 trade count is thin (n_trades_p1b < 50).
# hypothesis_generator.py reads this value and applies accordingly.
Any strategy calibrated on full P1 before Rule 4 was introduced is grandfathered — its existing P2 result stands. Rule 4 applies to all new hypotheses.
```

**DONE CHECK:** File exists. Period rows present for all registered archetypes (or wildcard). archetype column present. Rolling-forward instructions present.

---

### Task 1-07: `_config/pipeline_rules.md`

**CRITICAL: These five rules are absolute. They override any program.md instruction.**

```markdown
# Pipeline Rules
last_reviewed: 2026-03-11
# These rules cannot be overridden by any program.md or CONTEXT.md instruction.

## Rule 1 — P1 Calibrate
IS data (P1) is used freely for feature calibration, hypothesis search, and parameter
optimization. No restrictions on number of runs against IS data except the iteration
budget in statistical_gates.md.

## Rule 2 — P2 One-Shot
OOS data runs exactly once, with frozen parameters, after internal replication passes.
The holdout_locked_P2.flag enforces this structurally. Do not run OOS if flag exists.

## Rule 3 — Entry-Time Only
Every feature used in scoring or routing must be computable at the moment of entry.
No feature may use data from bars after entry. feature_rules.md enforces this.
Features marked "Entry-time computable: NO" in feature_definitions.md are blocked.

## Rule 4 — Internal Replication
Before any P2 run, the strategy must pass internal replication on P1a and P1b.
P1a = calibration half. P1b = replication half (never used during calibration).
Stage 01 computes P1a/P1b boundaries dynamically from p1_split_rule in period_config.md.

Gate behaviour is controlled by replication_gate in period_config.md:
  hard_block     — P1b fail → verdict NO, do not advance to P2.
  flag_and_review — P1b fail → WEAK_REPLICATION flag logged, human decides.

flag_and_review is recommended when n_trades_p1b < 50 — thin trade counts make
P1b pass/fail unreliable as a hard gate. A genuine edge may fail P1b by variance
alone. Human review distinguishes variance from genuine lack of edge.

GRANDFATHERING: Any strategy calibrated on full P1 before Rule 4 was introduced is
grandfathered — its existing P2 result stands. Rule 4 applies to all new hypotheses.

## Rule 5 — Instrument Constants from Registry
Every instrument-specific constant (tick size, dollar value per tick, session times,
cost_ticks) must be read from `_config/instruments.md`. No pipeline script may hardcode
these values. If the value is not in instruments.md, add it there first, then reference it.
```

**DONE CHECK:** All five rules present. Grandfathering note present.

---

### Task 1-08: `_config/statistical_gates.md`

**CRITICAL: Write this before any autoresearch run. Multiple testing controls are mandatory.**

```markdown
# Statistical Gates
last_reviewed: 2026-03-11
# These gates are enforced by Stage 05. Do not bypass.

## Baseline Verdict Thresholds
| Metric          | Yes       | Conditional   | No       |
|-----------------|-----------|---------------|----------|
| Profit Factor   | ≥ 2.5     | 1.5 – 2.49    | < 1.5    |
| Min trades      | ≥ 50      | 30 – 49       | < 30     |
| MWU p-value     | < 0.05    | < 0.10        | ≥ 0.10   |
| Permutation p   | < 0.05    | < 0.10        | ≥ 0.10   |
| Percentile rank | ≥ 99th    | 95th – 98th   | < 95th   |
| Max drawdown    | < 3x avg winner | 3x – 5x avg winner | > 5x avg winner |

## Drawdown Gate Notes
- Expressed as a multiple of average winning trade (ticks) — no capital assumption needed
- avg_winner computed from trade_log.csv at assessment time
- Rationale: a strategy with PF 3.0 but DD 20x average winner is unliveable regardless of PF
- Do not use absolute tick values — these would need updating as strategy params change

## Multiple Testing Controls (Gap A — mandatory before autoresearch)

### Iteration Budgets (per archetype per IS period)
| Stage          | Max P1 iterations | Action at limit                          |
|----------------|-------------------|------------------------------------------|
| 02-features    | 300               | Freeze feature set or retire candidates  |
| 03-hypothesis  | 200               | Advance best to P2 or retire archetype   |
| 04-backtest    | 500               | Freeze best params or retire             |

### Bonferroni-Adjusted P-value Gates (Stage 05 reads n_prior_tests from results_master.tsv)
| n_prior_tests for archetype | MWU p threshold |
|-----------------------------|-----------------|
| ≤ 10                        | < 0.05 (standard) |
| 11 – 50                     | < 0.02 (tightened) |
| 51 – 200                    | < 0.01 (strict) |
| > 200                       | Do not advance — budget exhausted |

## n_prior_tests Implementation
Written by the autoresearch driver loop — NOT by a git hook.
Driver counts rows in results.tsv for the current archetype before appending each new row.
Stage 05 reads n_prior_tests from results_master.tsv when computing verdict.
```

**DONE CHECK:** Baseline thresholds, iteration budgets, and Bonferroni gates all present.

---

### Task 1-09: `_config/regime_definitions.md`

```markdown
# Regime Definitions
last_reviewed: 2026-03-11

## Purpose
Regime labels are available to:
- Stage 01: generated by hmm_regime_fitter.py (Task 1-09b) — mandatory Pass 1 infrastructure
- Stage 02: hmm_regime_state as a feature candidate (entry-time computable)
- Stage 05: breakdown dimension in assessment reports
- Stage 07: live drift detection by regime

## Tagging
Regimes are tagged per trading day in: 01-data/data/labels/regime_labels.csv
Columns: date | trend | volatility | macro
Generated by: stages/01-data/hmm_regime_fitter.py (see Task 1-09b)

## Regime Dimensions (tag each day independently on all three)

Note: These thresholds describe the intended semantic meaning of each regime state.
The HMM fitter discovers latent states from bar data — use these thresholds as sanity-check
references when assigning human-readable names to HMM states (e.g. state 0 → "trending"
if it predominantly covers high-ADX days). They are not the generative algorithm.

### Trend
- trending: ADX > 25
- ranging: ADX ≤ 25

### Volatility (relative to 20-day average ATR)
- high_vol: daily ATR > 1.5x average
- normal_vol: daily ATR 0.75x – 1.5x average
- low_vol: daily ATR < 0.75x average

### Macro
- event_day: FOMC, CPI, NFP, or other tier-1 macro release
- normal_day: no tier-1 release

## Stage 05 Usage
If n_trades ≥ 20 per regime bucket: include regime breakdown in statistical_summary.md
If PF > 2.0 in one regime but < 1.0 in another: flag as regime-dependent in verdict_report.md
Do not disqualify a strategy for regime-dependence — document it clearly.
```

**DONE CHECK:** File exists. Three dimensions defined. Stage 05 usage rule present.

---

### Task 1-09b: `stages/01-data/hmm_regime_fitter.py` + initial `regime_labels.csv`

**Build during Pass 1 — before any autoresearch runs. This is mandatory infrastructure, not a deferred step.**

The HMM fitter generates regime labels where `regime_definitions.md` previously only defined semantic thresholds. It consumes bar data and writes `regime_labels.csv`. Stage 05 regime breakdown uses whatever is in that file regardless of how the labels were generated, so building this during Pass 1 gives you richer diagnostics from the first assessment onward.

**IS/OOS discipline (identical to scoring model):**
- Fit HMM on P1 bar data only → serialize to `shared/scoring_models/hmm_regime_v1.pkl`
- Generate P1 labels by applying the frozen model to P1 bars
- Generate P2 labels by applying the **same frozen model** to P2 bars — never refit on P2

Register the serialized model path in `strategy_archetypes.md` under the archetype entry.

```
stages/01-data/hmm_regime_fitter.py
  Inputs:  stages/01-data/data/bar_data/volume/{SYMBOL}_BarData_250vol_P1.txt  (fit on P1 only)
           stages/01-data/data/bar_data/volume/{SYMBOL}_BarData_250vol_P2.txt  (apply frozen model to generate P2 labels)
  Outputs: shared/scoring_models/hmm_regime_v1.pkl
           stages/01-data/data/labels/regime_labels.csv  (P1 + P2, frozen model applied to both)
```

**DONE CHECK:** Script runs without error. `regime_labels.csv` exists and covers both P1 and P2 date ranges. `hmm_regime_v1.pkl` serialized and registered in `strategy_archetypes.md`. Spot-check 10 rows — labels are plausible (not all one state).

---

### The Regime Research Flow (Pass 1 → human decision → Pass 2)

This describes how regime identification integrates with the autoresearch pipeline. The HMM fitter above is built once in Pass 1. What follows is the research pattern that uses it.

**Pass 1 — regime bypasses the scoring path:**
Stage 02 feature search runs without regime state as a candidate. Stage 04 optimizes params on a non-regime-conditioned strategy. Stage 05 generates its verdict plus regime breakdown using `regime_labels.csv`.

**Human decision point after Stage 05:**
Read `verdict_report.md`. If PF diverges significantly across regime buckets (e.g. PF > 2.0 in trending, < 1.0 in ranging), the strategy has latent regime sensitivity worth exploiting. This is a human judgment call — not every regime split warrants a second pass. Once you decide to proceed, everything that follows is prescribed pipeline behavior.

**Pass 2 — regime enters the scoring path:**
This is not a manual process — it is the same pipeline run again with one additional feature candidate. No special handling required.

1. Add `hmm_regime_state` as a feature candidate in Stage 02 — run through the evaluator as normal
2. If it passes the keep threshold, it is registered and flows into Stage 03/04 as any approved feature would
3. Stage 03/04 re-optimize with regime-conditioned scoring using the same autoresearch loop

**Two constraints carry forward from Pass 1 into Pass 2:**

*Seed carry-forward:* Do not restart Stage 04 from scratch. Load the best `exit_params.json` from Pass 1 into `results.tsv` with `verdict: seeded` before the first Pass 2 overnight run. Exit structure does not change — only the scoring inputs change.

*Budget accumulation:* `n_prior_tests` counts all experiments for this archetype across both passes. The Bonferroni gate tightens on Pass 2 by construction. If Pass 1 consumed 300 of 500 Stage 04 experiments, Pass 2 has 200 remaining. This is correct behavior — more tests against P1 means a higher significance bar.

**P2 runs exactly once — after the regime-aware version passes both P1a and P1b.** Both passes happen entirely within IS territory.

---

### Task 1-10: `_config/context_review_protocol.md`

**CRITICAL: This file defines the lost-in-middle mitigations. It IS the mitigation.**

```markdown
# Context Review Protocol
last_reviewed: 2026-03-11

## FILE LENGTH LIMITS (hard — trim before run if over limit)
| File             | Limit    | Archive excess to        |
|------------------|----------|--------------------------|
| CLAUDE.md        | 60 lines | n/a — never grows        |
| stage CONTEXT.md | 80 lines | context_history.md       |
| program.md       | 30 lines | program_history.md       |
| results.tsv      | no limit | structured data, not prose |
| feature_catalog  | no limit | reference doc, not runtime |

## FRONT-LOADING RULE
Every file an agent reads at runtime: operative instruction in first 5 lines.
Structure: WHAT TO DO → constraints → metric → rationale.

Good: "Only modify exit_params.json. Metric: PF@3t on P1. Min 30 trades.
       Do not touch backtest_engine.py. [rationale follows]"
Bad:  "[paragraphs of context] ... Only modify exit_params.json."

## LOCAL REPETITION RULE
Each stage CONTEXT.md restates its own critical constraints directly.
Do not rely on the agent remembering constraints from CLAUDE.md.
Redundancy is intentional.

## STALENESS FLAG
All CONTEXT.md files must have front matter:
  last_reviewed: YYYY-MM-DD
  reviewed_by: Ji

## WHEN TO REVIEW
- Every period rollover (pre-commit hook reminds you)
- New stage or archetype added
- CONTEXT.md not touched in > 90 days
- EXPERIMENT_ANOMALY suggests agent misunderstood task

## REVIEW CHECKLIST (per CONTEXT.md)
- [ ] Inputs table matches what Stage 01 actually produces
- [ ] Outputs table matches what stage actually writes
- [ ] File paths match actual filesystem
- [ ] program.md constraints match current research direction
- [ ] File is within length limit

## PERSISTENT STATE VS WORKING MEMORY
Agent does not hold experiment history in context — results.tsv does.
Driver loop reads TSV fresh each iteration.
program.md must never accumulate past experiments.
```

**DONE CHECK:** File length limits table present. Front-loading rule present. Staleness flag spec present.

---

### Task 1-11: `shared/feature_definitions.md`

```markdown
# Feature Definitions
last_reviewed: {date}
# Entry-time computability is a HARD RULE. Features marked NO are blocked from use.
# Populate this file as Stage 02 autoresearch discovers and approves features.
# From scratch: this file starts with the template only — no pre-registered features.

## Registered Features
(empty — features added here as Stage 02 autoresearch approves them)

## Template for new features
### [feature_name]
- Source: [source_id from data_registry.md]
- Computation: [formula — must be computable at entry time, no look-ahead]
- Bin edges: [calibrated on P1 IS data — tercile or custom; frozen in scoring model JSON]
- Entry-time computable: YES / NO
- Used by: [archetype names]
```

**If migrating an existing strategy:** Populate Registered Features with the known feature set from that strategy. Transcribe from source code — do not invent.

**DONE CHECK:** File exists. Entry-time rule stated at top. Template present. Any migrated features have Entry-time computable field set.

---

### Task 1-11b: `02-features/references/feature_rules.md`

**CONSTRAINT: This file is read by Stage 02 agent before every experiment. Keep it ≤30 lines.**

```markdown
# Feature Rules
last_reviewed: 2026-03-11
# Stage 02 agent reads this before each experiment. Keep ≤30 lines.

## Rule 1 — Entry-time only (Pipeline Rule 3)
Every feature must be computable at the moment of trade entry.
No feature may use data from bars after the entry bar.
If Entry-time computable = NO in feature_definitions.md: BLOCKED. Do not use.

## Rule 2 — Registered sources only
Features must be computed from registered sources in _config/data_registry.md.
Do not invent data sources. Do not load files not in data_manifest.json.

## Rule 3 — Keep threshold
Keep a new feature only if:
  best-bin vs worst-bin predictive spread > 0.15 AND MWU p-value < 0.10
Below threshold: revert feature_engine.py, log as failed in results.tsv.

## Rule 4 — One feature per experiment
Add or modify exactly one feature per experiment.
Do not batch multiple feature changes into a single run.

## Rule 5 — Register before use
After a feature passes the keep threshold:
  - Add entry to shared/feature_definitions.md
  - Confirm Entry-time computable: YES before adding
```

**DONE CHECK:** File exists. All five rules present. Keep threshold values match statistical_gates.md intent.

---

### Task 1-11c: `02-features/references/feature_catalog.md`

**Reference doc — no line limit. All known features explored, including failures.**
**Purpose:** Agent reads this to avoid repeating dead ends. Human updates after each overnight run.

```markdown
# Feature Catalog
last_reviewed: {date}
# Complete history of features explored. No line limit — reference doc, not runtime context.
# Update after every overnight run. Agent reads this via program.md direction.
# From scratch: starts empty. Populate as Stage 02 autoresearch runs.

## Active features (currently in frozen_features.json)
| Feature | Source | Status |
|---------|--------|--------|
| [none yet — add as Stage 02 approves features] | | |

## Explored and dropped
| Feature | Spread | p-value | Reason dropped | Date |
|---------|--------|---------|---------------|------|
| [populate as Stage 02 autoresearch runs] | | | | |

## Dead ends — do not retry
(Human fills this after overnight runs — explains why ideas failed so agent doesn't repeat)
```

**If migrating an existing strategy:** Populate Active features with the known feature set. This gives Stage 02 autoresearch a starting catalog to build from rather than an empty slate.

**DONE CHECK:** File exists. Template structure present. Any migrated features in Active table.

---

### Task 1-12: `shared/scoring_models/` — directory + schema template

**From scratch:** Create the directory and a scoring model template. Do NOT populate with archetype-specific weights yet — that happens during archetype intake (see NEW ARCHETYPE INTAKE checklist).

```bash
mkdir -p futures-pipeline/shared/scoring_models
```

Create `shared/scoring_models/_template.json` showing the required schema:
```json
{
  "model_id": "{archetype}_{variant}",
  "frozen_date": "YYYY-MM-DD",
  "max_score": 0,
  "threshold": 0,
  "description": "Frozen scoring weights for {archetype} {variant} — do not modify after freezing",
  "weights": {
    "{feature_name}": { "bins": ["low","mid","high"], "scores": [0, 0, 0] }
  },
  "bin_edges": {
    "{feature_name}": [0.0, 0.0]
  }
}
```

**bin_edges contract (Q2 answer):** Tercile cutoffs are computed once from P1 IS data during archetype intake and frozen here. `BinnedScoringAdapter` reads `bin_edges` internally to bin features before scoring — `backtest_engine.py` never touches `bin_edges` directly. This is how the scoring model stays stable across P1/P2.

**Scoring adapter interface (write before Pass 2):**
`backtest_engine.py` must never load scoring models directly — it loads an adapter. The adapter wraps whatever model format the archetype uses and exposes one method to the engine. Write `shared/scoring_models/scoring_adapter.py` containing:

```python
# shared/scoring_models/scoring_adapter.py
# All adapters expose: score(touch_df) -> pd.Series[float]
# Engine calls adapter.score() — never touches model internals directly.

from typing import Protocol
import pandas as pd

class ScoringAdapter(Protocol):
    def score(self, touch_df: pd.DataFrame) -> pd.Series: ...

class BinnedScoringAdapter:
    """Wraps the existing JSON scoring model (bin_edges + weights). Current default."""
    def __init__(self, model_path: str): ...
    def score(self, touch_df: pd.DataFrame) -> pd.Series: ...

class SklearnScoringAdapter:
    """Wraps a scikit-learn model (RF, XGBoost). Future path for Stage 02 ML scoring."""
    def __init__(self, model_path: str): ...
    def score(self, touch_df: pd.DataFrame) -> pd.Series: ...

class ONNXScoringAdapter:
    """Wraps an ONNX model. Future path for neural net scoring."""
    def __init__(self, model_path: str): ...
    def score(self, touch_df: pd.DataFrame) -> pd.Series: ...

def load_scoring_adapter(model_path: str, adapter_type: str) -> ScoringAdapter:
    """Factory — reads adapter_type from archetype config. Returns the right adapter."""
    ...
```

All three adapters must conform to the same interface. Adding a new model format = write a new adapter class — no engine changes needed. `adapter_type` is registered per-archetype in `strategy_archetypes.md` (see Task 1-27).

**If migrating an existing strategy:** Also populate `shared/scoring_models/{archetype}_{variant}.json` from the existing scoring source. Transcribe actual values from source code — do not invent them.

**DONE CHECK:** Directory exists. `_template.json` present with all required fields. `scoring_adapter.py` written with all three adapter stubs. `BinnedScoringAdapter` fully implemented and tested against at least one known scoring model JSON. Any migrated model files have frozen_date set and weights/bin_edges fully populated.

---

### Task 1-13: `shared/scoring_models/` — archetype-specific supplementary configs

**From scratch:** Skip. This task only applies when the archetype requires supplementary filter configs beyond the main scoring model (e.g. per-timeframe thresholds, secondary filter tables).

**If migrating an archetype with supplementary filter configs:** Create the config file from existing source. This is archetype-specific — other archetypes may not need it.

```json
{
  "model_id": "{filter_name}_v1",
  "frozen_date": "YYYY-MM-DD",
  "description": "Archetype-specific supplementary filter — frozen",
  "config": { }
}
```

**General rule:** Any archetype-specific filter config that is NOT part of the main scoring model weights goes in `shared/scoring_models/` with a descriptive name. Register it in `strategy_archetypes.md` under the archetype entry.

**DONE CHECK (if applicable):** File exists. Values transcribed from actual source, not invented. Registered in strategy_archetypes.md.

---

### Tasks 1-14 through 1-20: Stage CONTEXT.md files
- Front matter: `last_reviewed` + `reviewed_by`
- First 5 lines after front matter: what the agent does, what it edits, what metric
- Local repetition: restate the one hard constraint specific to this stage
- ≤80 lines

---

### Task 1-14: Stage 01 folder + `CONTEXT.md`

**Stage 01 CONTEXT.md** — `stages/01-data/CONTEXT.md`
```markdown
---
last_reviewed: 2026-03-11
reviewed_by: Ji
---
# Stage 01: Data Foundation
## YOUR TASK: Validate and register data. Do not modify any _config/ files.

| | |
|---|---|
| **Inputs** | Raw source files (archetype touch data, bar data) in 01-data/data/ |
| **Process** | Validate schemas, check date coverage, discover bar offsets, register periods |
| **Outputs** | data_manifest.json, validation_report.md |
| **Human checkpoint** | Review validation_report.md before any downstream stage runs |

## CONSTRAINT
You do not run backtests. You do not touch _config/. Your only output is data_manifest.json
and validation_report.md.

## VALIDATION CHECKLIST
- [ ] Schema check: required columns present in all CSVs
- [ ] Date coverage: P1 and P2 fully covered, no gaps
- [ ] Row counts: logged in data_manifest.json
- [ ] Bar offset: verified and documented
- [ ] Label columns: spot-check 10 rows against source files (if archetype uses derived labels)
- [ ] regime_labels.csv: exists, covers both P1 and P2 date ranges, not all-one-state
- [ ] data_manifest.json: all registered periods present, all sources PASS, bar_offset verified

## NEW DATA TYPES
When a new archetype requires data not in data_registry.md:
1. Add schema doc to 01-data/references/{format}_schema.md
2. Add validation block to Stage 01 validation script for that schema
3. Add row to data_registry.md
4. Re-run Stage 01 — new source must pass before archetype intake proceeds
Stage 01 validation is NOT automatic for new formats — human writes the schema and validation block.
```

---

### Task 1-14b: Stage 01 reference files

Two schema files Stage 01 validation uses as column contracts.

**`stages/01-data/references/{source_id}_schema.md`** — one schema file per data source type.

**From scratch:** Create a schema file for each data source your archetype requires. The schema is the column contract — Stage 01 validation checks every data file against it.

**Schema file template:**
```markdown
# {Source Name} Schema
last_reviewed: {date}
# Required columns for {source_id} data files. Validation fails if any column is missing.
# Source ID must match data_registry.md.

| Column | Type | Description |
|--------|------|-------------|
| {column_name} | {type} | {description} |
```

**If migrating an existing archetype:** Document your source data's column schema using the template above. Create one schema file per `source_id`. Include any derived label columns (e.g. classification labels added in a later data version). Create this as `stages/01-data/references/{source_id}_schema.md` — the filename must match the `source_id` in `data_registry.md`.

**`stages/01-data/references/bar_data_volume_schema.md`** (and equivalents for bar_data_time, bar_data_tick)
```markdown
# Bar Data Schema — {bar_type} (e.g. bar_data_volume)
last_reviewed: 2026-03-11
# Required columns for {SYMBOL}_BarData_{bar_type} files. Validation fails if any column is missing.
# source_id must match data_registry.md (bar_data_volume | bar_data_time | bar_data_tick).
# Bar data prefix is registered per instrument in _config/instruments.md.

| Column | Type | Description |
|--------|------|-------------|
| datetime | str | Bar datetime YYYY-MM-DD HH:MM:SS |
| open | float | Bar open price |
| high | float | Bar high price |
| low | float | Bar low price |
| close | float | Bar close price |
| volume | int | Bar volume |

Resolution: source_id determines bar type — bar_data_volume (250-vol), bar_data_time (1-min), bar_data_tick (N-tick).
One schema file per source_id: bar_data_volume_schema.md, bar_data_time_schema.md, bar_data_tick_schema.md.
Gaps > 5 bars flagged in validation_report.md.
Bar offset: validated in Stage 01 — signal bar index must align to correct bar type.
```

**DONE CHECK:** Schema file(s) exist in `01-data/references/`, one per registered source_id. Column names match actual data file headers. data_manifest.json schema (Task 1-14c) documented.

---

### Task 1-14c: `data_manifest.json` schema specification

**data_manifest.json** is produced by Stage 01 validation and consumed by every downstream stage. Its schema must be defined before Stage 01 is built.

**Location:** `stages/01-data/output/data_manifest.json`
**Created by:** Stage 01 validation script (never hand-edited)
**Read by:** feature_evaluator.py (per-archetype), hypothesis_generator.py, backtest_engine.py (for path resolution), Stage 05

```json
{
  "generated": "YYYY-MM-DD HH:MM:SS",
  "archetypes": {
    "{archetype_name}": {
      "periods": {
        "P1": {
          "start": "YYYY-MM-DD",
          "end": "YYYY-MM-DD",
          "p1a_start": "YYYY-MM-DD",
          "p1a_end": "YYYY-MM-DD",
          "p1b_start": "YYYY-MM-DD",
          "p1b_end": "YYYY-MM-DD",
          "sources": {
            "{source_id}": {
              "path": "stages/01-data/data/{source_folder}/{filename}",
              "row_count": 0,
              "schema_version": "{schema_doc_filename}",
              "validation_status": "PASS"
            }
          }
        },
        "P2": {
          "start": "YYYY-MM-DD",
          "end": "YYYY-MM-DD",
          "sources": { ... }
        }
      }
    }
  },
  "replication_gate": "flag_and_review",
  "bar_offset": {
    "verified": true,
    "offset_bars": 0,
    "verified_date": "YYYY-MM-DD",
    "method": "[how offset was determined]"
  },
  "validation_summary": {
    "status": "PASS",
    "warnings": [],
    "errors": []
  }
}
```

**How downstream stages use it:**
- `feature_evaluator.py`: reads `archetypes.{archetype}.periods.P1.sources.{source_id}.path` to load IS data — no hardcoded paths
- `hypothesis_generator.py`: reads P1a/P1b boundaries from `archetypes.{archetype}.periods.P1.p1a_start` etc. — dynamically computed by Stage 01 from p1_split_rule
- `backtest_engine.py`: does NOT read data_manifest.json — it takes explicit paths in config (Q1 answer). Paths in data_manifest.json are what the caller passes into config.
- `Stage 05`: reads paths for any supplementary validation only

**Source IDs** match data_registry.md entries. Each archetype's feature_evaluator reads only the source_ids it needs.

**DONE CHECK (Task 1-14c):** `cat stages/01-data/output/data_manifest.json` shows: per-archetype periods block, correct paths per source_id, row_counts, p1a/p1b boundaries computed, bar_offset verified. Schema matches this spec exactly.

---

### Task 1-15: Stage 02 folder + `CONTEXT.md`

**Stage 02 CONTEXT.md** — `stages/02-features/CONTEXT.md`
```markdown
---
last_reviewed: 2026-03-11
reviewed_by: Ji
---
# Stage 02: Feature Engineering
## YOUR TASK: Edit feature_engine.py only. Metric: predictive spread on P1.
## CONSTRAINT: Do not touch evaluate_features.py (fixed harness).

| | |
|---|---|
| **You edit** | shared/archetypes/{archetype}/feature_engine.py (one file only) |
| **Dispatcher** | autoresearch/evaluate_features.py — loads archetype evaluator, never touch |
| **Evaluator** | shared/archetypes/{archetype}/feature_evaluator.py — archetype-specific harness, never touch |
| **Metric** | Best-bin vs worst-bin predictive spread on P1 (archetype-specific metric — see feature_evaluator.py) |
| **Keep rule** | spread > threshold in program.md → keep; else revert |
| **Outputs** | results.tsv (every experiment), output/frozen_features.json (human-approved) |

## ARCHETYPE REFERENCES
Read program.md to identify the active archetype.
You edit: shared/archetypes/{archetype}/feature_engine.py
Do not edit feature_engine.py files belonging to other archetypes.
Read shared/archetypes/{archetype}/feature_evaluator.py to understand what data is available.

## ENTRY-TIME RULE (Rule 3 — local repeat)
Every feature you add must be computable at the moment of entry.
No feature may use data from bars after entry. Check feature_rules.md before adding.

## ITERATION BUDGET (from statistical_gates.md)
Max 300 experiments per IS period. Driver logs n_prior_tests on each row.
Stop and report to human when budget is reached.

## PROGRAM
Read autoresearch/program.md before each experiment. It steers your direction.

## AFTER HUMAN PROMOTION
When human approves features and creates output/frozen_features.json:
  cp stages/02-features/output/frozen_features.json \
     stages/03-hypothesis/references/frozen_features.json
This makes the approved feature set available to Stage 03 hypothesis agent.
```

---

### Task 1-16: Stage 03 folder + `CONTEXT.md`

**Stage 03 CONTEXT.md** — `stages/03-hypothesis/CONTEXT.md`
```markdown
---
last_reviewed: 2026-03-11
reviewed_by: Ji
---
# Stage 03: Hypothesis Generation
## YOUR TASK: Edit hypothesis_config.json only. Metric: P1 PF at 3t cost.
## CONSTRAINT: Do not touch hypothesis_generator.py (fixed harness).

| | |
|---|---|
| **You edit** | autoresearch/hypothesis_config.json (one file only) |
| **Fixed harness** | autoresearch/hypothesis_generator.py (calls backtest + assess internally) |
| **Metric** | P1 PF at 3t minimum cost, minimum 30 trades |
| **Keep rule** | PF improves by > 0.1 → keep; else revert |
| **Outputs** | results.tsv, output/promoted_hypotheses/ (human-approved only) |
| **Reads** | references/frozen_features.json (from Stage 02), references/prior_results.md (from Stage 05) |

## INTERNAL REPLICATION RULE (Rule 4 — local repeat)
A hypothesis can only advance to P2 after passing both P1a and P1b independently.
The generator enforces this. Do not manually advance a hypothesis that failed P1b.

## ITERATION BUDGET
Max 200 experiments per archetype per IS period.

## PROGRAM
Read autoresearch/program.md before each experiment. It steers your direction.
Read references/prior_results.md to avoid repeating failures.
```

---

### Task 1-17: Stage 04 folder + `CONTEXT.md`

**Stage 04 CONTEXT.md** — `stages/04-backtest/CONTEXT.md`
```markdown
---
last_reviewed: 2026-03-11
reviewed_by: Ji
---
# Stage 04: Backtest Simulation
## YOUR TASK: Edit exit params JSON only. Metric: P1 PF at 3t, min 30 trades.
## CONSTRAINT: Do NOT edit backtest_engine.py. It is a fixed engine.

| | |
|---|---|
| **You edit** | autoresearch/current_best/exit_params.json (one file only) |
| **Fixed engine** | autoresearch/backtest_engine.py — NEVER MODIFY |
| **Call signature** | python backtest_engine.py --config params.json --output result.json |
| **Metric** | PF at 3t on P1, minimum 30 trades |
| **Keep rule** | PF improves by > 0.05 → keep; else revert |

## ARCHETYPE REFERENCES
Read program.md to identify the active archetype.
All archetype-specific rules are in: shared/archetypes/{archetype_name}/
For {archetype}: shared/archetypes/{archetype}/simulation_rules.md
For {archetype}: shared/archetypes/{archetype}/exit_templates.md
Read these files before proposing any param changes.
Do not apply rules from a different archetype's folder.

## P2 HOLDOUT RULE (Rule 2 — local repeat)
If p2_holdout/holdout_locked_P2.flag exists: STOP. Do not run any backtest against P2.
P2 runs exactly once, with frozen params, after human approval.

## ITERATION BUDGET
Max 500 experiments per archetype per IS period.
```

---

### Task 1-17b: `shared/archetypes/{archetype}/exit_templates.md`

**Reference doc for Stage 04 agent — exit structure patterns for this archetype. ≤40 lines.**
**Location:** `shared/archetypes/{archetype}/exit_templates.md` — archetype-specific. New archetypes get their own copy under `shared/archetypes/{name}/`.

```markdown
# Exit Templates
last_reviewed: [date]
# Reference patterns for exit structure. Agent reads before proposing param changes.
# Do not modify these templates — they describe what the simulator supports.

## Multi-leg partial exit (if archetype supports multiple targets)
- Leg 1: smallest target — earliest exit, highest probability
- Leg 2: mid target — core of the trade
- Leg 3: largest target — runner leg (add/remove legs per archetype design)
- All legs share same stop. BE trigger activates after first leg fills.
- Trail applies after BE trigger: trigger price → new stop level.
- Time cap: if no fill by time_cap_bars, exit at market.

## Single-leg exit (if archetype supports single-target mode)
- One target, one stop.
- BE trigger: trail_steps[0] with new_stop_ticks=0 moves stop to entry (zero risk).
- Time cap: same pattern as multi-leg.

## Trail mechanics + BE (unified)
- trail_steps is a list of {trigger_ticks, new_stop_ticks} pairs
- Once MFE hits trigger_ticks, stop ratchets to new_stop_ticks above entry — never moves back
- BE is trail_steps[0] where new_stop_ticks=0 (stop moves to entry = zero risk)
- There is no separate be_trigger_ticks field — trail_steps[0] IS the BE trigger
- Agent may vary step count (1–6) and trigger/new_stop values within validation rules

## Optimization surface (what agent varies in Stage 04)
- stop_ticks, targets, trail_steps (full array), time_cap_bars
- FIXED: cost_ticks, score thresholds, any archetype-specific filter configs, simulator_module
```

**DONE CHECK:** File exists at `shared/archetypes/{archetype}/exit_templates.md`. All exit patterns documented. Optimization surface vs fixed fields clear.

---

### Task 1-18: Stage 05 folder + `CONTEXT.md`

**Stage 05 CONTEXT.md** — `stages/05-assessment/CONTEXT.md`
```markdown
---
last_reviewed: 2026-03-11
reviewed_by: Ji
---
# Stage 05: Statistical Assessment
## YOUR TASK: Compute metrics and render verdict. Deterministic — no exploration.
## CONSTRAINT: You do not modify backtest outputs. You read them and compute.

| | |
|---|---|
| **Inputs** | 04-backtest/output/trade_log.csv, data_manifest.json |
| **Process** | Compute PF, MWU, permutation test, percentile rank; apply adjusted p-value gate |
| **Outputs** | verdict_report.md, verdict_report.json, statistical_summary.md, feedback_to_hypothesis.md |
| **Human checkpoint** | None — deterministic. Human reads verdict_report.md and decides whether to promote. |

## MULTIPLE TESTING (Gap A — local repeat)
Read n_prior_tests from results_master.tsv for this archetype.
Apply adjusted p-value gate from _config/statistical_gates.md (not the baseline).
If n_prior_tests > 200: verdict is automatically NO regardless of p-value.

## statistical_summary.md OUTPUT SPEC
Compute and report all of these. Verdict gates apply to the top block only.
Sharpe is a REPORTING METRIC — informational, not a verdict gate.

### Verdict metrics (gates apply)
- profit_factor, n_trades, win_rate
- mwu_p, permutation_p, percentile_rank
- max_drawdown_ticks, avg_winner_ticks, drawdown_multiple (DD / avg winner)

### Reporting metrics (logged, not gated)
- sharpe_ratio: (mean_trade_pnl / std_trade_pnl) * sqrt(n_trades)
  Note: trade-level Sharpe — no annualization, no capital assumption
- avg_loser_ticks, avg_winner_ticks, win_loss_ratio
- longest_losing_streak, longest_flat_bars
- regime_breakdown: PF per regime bucket (if n_trades ≥ 20 per bucket)

### Sharpe implementation note
Use trade-level Sharpe only. Do NOT annualize. Do NOT assume account size.
Formula: mean(trade_pnl_ticks) / std(trade_pnl_ticks) * sqrt(n_trades)
This is comparable across strategies on the same instrument without capital assumptions.
Flag as unreliable if n_trades < 30.
```

---

### Task 1-18b: Stage 05 reference files

Two files Stage 05 agent reads when computing verdicts. Both must exist before any assessment runs.

**`stages/05-assessment/references/verdict_criteria.md`**
```markdown
# Verdict Criteria
last_reviewed: 2026-03-11
# Stage 05 reads this to determine Yes / Conditional / No.
# Source of truth: _config/statistical_gates.md. This file is a local copy for agent access.

## Verdict logic (all gates must pass for the verdict to hold)
YES: PF ≥ 2.5 AND trades ≥ 50 AND MWU p < 0.05 AND perm p < 0.05 AND pctile ≥ 99 AND dd_multiple < 3
CONDITIONAL: PF ≥ 1.5 AND trades ≥ 30 AND MWU p < 0.10 AND perm p < 0.10 AND pctile ≥ 95 AND dd_multiple < 5
NO: anything below Conditional thresholds, OR n_prior_tests > 200, OR replication_pass == false

## Drawdown gate
dd_multiple = max_drawdown_ticks / avg_winner_ticks
Compute from trade_log.csv at assessment time. Do not use absolute tick values.

## Multiple testing adjustment
Read n_prior_tests from results_master.tsv for this archetype.
Apply Bonferroni-adjusted MWU threshold from _config/statistical_gates.md.
```

**`stages/05-assessment/references/statistical_tests.md`**
```markdown
# Statistical Tests
last_reviewed: 2026-03-11
# Specifications for tests Stage 05 must run. All three required for every verdict.

## Mann-Whitney U test
- Null hypothesis: live PnL distribution is not different from zero-mean
- Input: trade_pnl_ticks column from trade_log.csv
- Two-tailed. Report p-value to 4 decimal places.
- Flag as unreliable if n_trades < 20.

## Permutation test
- Method: shuffle trade outcomes 10,000 times, recompute PF each time
- Report: percentile rank of actual PF vs permuted distribution
- p-value: fraction of permuted PFs ≥ actual PF
- Budget: 10,000 permutations minimum

## Random percentile rank
- Compare strategy PF to 10,000 random strategies on same data
- Random strategy: random entry/exit on same bars, same trade count
- Report: percentile rank of actual PF (99th = top 1% of random)
```

**DONE CHECK:** Both files exist. Verdict thresholds in `verdict_criteria.md` match `statistical_gates.md`. All three test specs present in `statistical_tests.md`.

---

### Task 1-19: Stage 06 folder + `CONTEXT.md`

**Stage 06 CONTEXT.md** — `stages/06-deployment/CONTEXT.md`
```markdown
---
last_reviewed: 2026-03-11
reviewed_by: Ji
---
# Stage 06: Deployment Builder
## YOUR TASK: Assemble context package for ACSIL generation. Human fires the prompt.
## CONSTRAINT: Human must create deployment_ready.flag. You never create it.

| | |
|---|---|
| **Inputs** | 04-backtest/output/frozen_params.json, shared/scoring_models/, shared/feature_definitions.md |
| **Process** | Run assemble_context.sh → human fires Claude Code prompt → human compiles + verifies |
| **Outputs** | output/{strategy_id}/*.cpp, output/{strategy_id}/deployment_checklist.md |
| **Human gate** | Compile, verify on replay, create deployment_ready.flag |

## WHAT THIS STAGE IS
Context assembly. The pipeline gathers everything Claude Code needs in one place.
Human fires the generation prompt. Human reviews .cpp output. Human compiles and verifies.
No automated tests. No templates required. Output file count determined by Claude Code.

## DEPLOYMENT CHECKLIST (human completes — do not skip)
- [ ] assemble_context.sh run — context_package.md reviewed for completeness
- [ ] Claude Code generation prompt fired with context_package.md loaded
- [ ] Generated .cpp file(s) reviewed — no magic numbers, params match frozen_params.json
- [ ] Compiled in Sierra Chart without warnings
- [ ] Replay verification: entries match expected signals on known dates
- [ ] audit/audit_entry.sh deploy invoked
- [ ] deployment_ready.flag created
```

---

### Task 1-19b: Stage 06 supporting files

Two files needed beyond CONTEXT.md.

**`stages/06-deployment/references/context_package_spec.md`**

Defines what gets assembled into the generation prompt for any strategy.
```markdown
# ACSIL Generation Context Package Spec
last_reviewed: 2026-03-11
# This is the information contract between the pipeline and Claude Code.
# assemble_context.sh reads this spec and builds the prompt from it.

## Required sections (in order)

### 1. Strategy identity
- hypothesis_id (from audit_log.md HYPOTHESIS_PROMOTED entry)
- archetype (from strategy_archetypes.md)
- verdict + period (from 05-assessment/output/verdict_report.json)

### 2. Frozen parameters (copy verbatim)
- 04-backtest/output/frozen_params.json — all exit params, exactly as optimized
- shared/scoring_models/{model_id}.json — scoring weights and thresholds

### 3. Features used
- Relevant entries from shared/feature_definitions.md
- Only features active in this strategy — not the full list

### 4. Structural reference
- Point Claude Code at archetype structural reference file (from strategy_archetypes.md)
- Read structural_reference path from strategy_archetypes.md for the active archetype
- Instruction: preserve entry logic; replace exit params with frozen_params.json values only
- Example: stages/06-deployment/references/{strategy_id}_reference.cpp

### 5. Output instructions
- Output folder: stages/06-deployment/output/{strategy_id}/
- Determine number of .cpp files needed (1 study or multiple coordinated studies)
- No magic numbers — every param value traces to frozen_params.json
- Each file must be compile-ready: no placeholders, no TODOs

## What NOT to include
- Experiment history or rejected hypotheses
- P1/P2 trade logs
- IS/OOS period config (not relevant to code structure)
```

**`stages/06-deployment/assemble_context.sh`**

Assembles all files into a single printout ready to paste into a Claude Code session:
```bash
#!/bin/bash
# Usage: bash assemble_context.sh <strategy_id>
# Prints assembled context package to stdout.
# Example: bash assemble_context.sh {strategy_id} | tee context_package.md

STRATEGY_ID=${1:?Usage: assemble_context.sh <strategy_id>}
ROOT="$(git rev-parse --show-toplevel)"

echo "# ACSIL Generation Context Package"
echo "# Strategy: $STRATEGY_ID | $(date)"
echo ""
echo "## Verdict"
cat "$ROOT/stages/05-assessment/output/verdict_report.json"
echo ""
echo "## Frozen Parameters"
cat "$ROOT/stages/04-backtest/output/frozen_params.json"
echo ""
echo "## Scoring Model"
# Scoring model path is in frozen_params.json under scoring_model_path
SCORING_MODEL=$(python3 -c "import json; print(json.load(open('$ROOT/stages/04-backtest/output/frozen_params.json'))['scoring_model_path'])")
cat "$ROOT/$SCORING_MODEL"
echo ""
echo "## Features Used"
cat "$ROOT/shared/feature_definitions.md"
echo ""
echo "## Generation Instructions"
cat "$ROOT/stages/06-deployment/references/context_package_spec.md"
echo ""
echo "## Structural Reference"
echo "# Read this file for ACSIL API patterns, entry logic, and data-feed conventions."
echo "# Preserve entry logic. Replace exit params with frozen_params.json values only."
# Structural reference path is registered per-archetype in strategy_archetypes.md
ARCHETYPE=$(python3 -c "import json; print(json.load(open('$ROOT/stages/04-backtest/output/frozen_params.json'))['archetype']['name'])")
STRUCT_REF=$(grep -A 20 "^## $ARCHETYPE" "$ROOT/stages/03-hypothesis/references/strategy_archetypes.md" | grep "^- Structural reference:" | head -1 | sed 's/.*: //')
cat "$ROOT/$STRUCT_REF"
```

**DONE CHECK:** `bash assemble_context.sh {strategy_id}` prints all six sections without errors. No "file not found" on any cat — structural reference resolves correctly from strategy_archetypes.md. `context_package_spec.md` exists with all five required sections.

---

### Task 1-20: Stage 07 folder + `CONTEXT.md`

**Stage 07 CONTEXT.md** — `stages/07-live/CONTEXT.md`
```markdown
---
last_reviewed: 2026-03-11
reviewed_by: Ji
---
# Stage 07: Live Performance Monitor
## YOUR TASK: Compare live trades to backtest expectations. Monitor only.
## CONSTRAINT: No autoresearch. No code generation. No backtest runs.

| | |
|---|---|
| **Inputs** | data/paper_trades.csv (manual export from live trading system) |
| **Baseline** | 05-assessment/output/verdict_report.json (backtest expectations) |
| **Outputs** | output/live_assessment.md (periodic), output/drift_report.md (rolling) |
| **Human checkpoint** | Monthly review of live_assessment.md; immediate if any trigger fires |

## REVIEW TRIGGERS
See `triggers/review_triggers.md` for full thresholds and escalation rules.
Check after every trade log update. If any trigger fires, create MANUAL_NOTE in audit_log.md first.

## LIVE DATA PROMOTION
After 200+ trades: evaluate for IS promotion via PERIOD_CONFIG_CHANGED audit entry.
This is a human decision. You flag it; human decides.
```

**DONE CHECK (all 7 stages):** Each CONTEXT.md ≤80 lines, front matter present, operative task in first 5 lines, local constraint repeat present.

---

### Task 1-20b: `07-live/triggers/review_triggers.md`

**Separate file — not embedded in CONTEXT.md. Thresholds will expand over time; a separate file keeps CONTEXT.md within its 80-line limit.**

```markdown
# Review Triggers
last_reviewed: 2026-03-11
# Conditions that force a pipeline review. Check after every trade log update.
# Do not change thresholds without a MANUAL_NOTE audit entry explaining the reason.

## Active Triggers

| Trigger | Threshold | Action |
|---------|-----------|--------|
| Live PF vs backtest PF | Diverges > 40% after 50+ trades | Review hypothesis; consider retiring |
| Consecutive stop-outs | 8 or more | Pause trading; review signal filter and entry conditions |
| Max drawdown exceeded | > 2x backtest DD | Pause trading immediately |
| Trade count below expected | < 5 signals/month | Check signal detection alignment and live system config |

## Escalation
If any trigger fires: create MANUAL_NOTE in audit/audit_log.md before doing anything else.
This creates a timestamped record before any investigation changes the system state.

## Promotion Trigger (not a problem — a milestone)
After 200+ live trades: flag for IS promotion evaluation via PERIOD_CONFIG_CHANGED audit entry.
Human decides whether to promote. Stage 07 flags it; pipeline does not act automatically.
```

**DONE CHECK:** File exists in `07-live/triggers/`. Stage 07 CONTEXT.md references this file (not the inline table). Thresholds in both files match.

---

### Task 1-21: `dashboard/results_master.tsv` schema stub

Create file with header row only:
```
run_id	stage	timestamp	hypothesis_name	archetype	version	features	pf_p1	pf_p2	trades_p1	trades_p2	mwu_p	perm_p	pctile	n_prior_tests	verdict	sharpe_p1	max_dd_ticks	avg_winner_ticks	dd_multiple	win_rate	regime_breakdown	api_cost_usd	notes
```

Column notes:
- `run_id` — git short hash at time of experiment (7 chars). Same value written to autocommit.sh commit message. Enables direct `git show <run_id>` lookup of any result row.
- `version` — archetype version string (e.g. `v1`, `v2`). Matches `version` field in `frozen_params.json`. Allows filtering results by archetype generation when params structure changes significantly.
- `sharpe_p1` — trade-level Sharpe on P1. Informational, not a gate.
- `dd_multiple` — max_dd_ticks / avg_winner_ticks. Gate applies (see statistical_gates.md).
- `regime_breakdown` — pipe-delimited `regime:pf:n_trades:win_rate` per bucket e.g. `trending:4.1:22:0.36|ranging:1.2:28:0.24`
- `pf_p2`, `trades_p2` — blank until P2 run; never backfilled after gate
- `api_cost_usd` — cumulative Claude API cost for this experiment in USD. Driver writes this from usage metadata returned by the API. Used to track overnight run cost and inform budget decisions. Leave blank for non-API experiments (e.g. pure Python backtest runs with no LLM call).

**DONE CHECK:** File exists with exactly one header row, 24 columns.

---

### Task 1-22: `dashboard/index.html`

Stub only — full implementation later:
```html
<!DOCTYPE html>
<html>
<head><title>Futures Pipeline Dashboard</title></head>
<body>
<h1>Futures Pipeline Results</h1>
<p>Dashboard stub — implement after first autoresearch run produces results.</p>
<p>Load: results_master.tsv | Sort by: PF, verdict, date | Filter by: archetype, verdict</p>
</body>
</html>
```

**DONE CHECK:** File exists. Placeholder renders in browser.

---

### Task 1-23: Migrate existing data files

```bash
# Touch/signal data → 01-data/data/touches/
cp /path/to/{source_id}_*.{ext} stages/01-data/data/touches/

# Bar data → 01-data/data/bar_data/{bar_type}/
# Use the subfolder matching the bar type registered in data_registry.md:
#   volume bars (250-vol)  → bar_data/volume/
#   time bars (1-min)      → bar_data/time/
#   tick bars              → bar_data/tick/
cp /path/to/{SYMBOL}_BarData_250vol_*.txt stages/01-data/data/bar_data/volume/

# Derived labels → 01-data/data/labels/  (if archetype uses derived label files)
cp /path/to/{label_source}_*.csv stages/01-data/data/labels/
```

**DONE CHECK:** `ls stages/01-data/data/touches/` shows source files for P1 and P2. `ls stages/01-data/data/bar_data/volume/` shows 250-vol bar data for both periods.

---

### Task 1-24: Archive pre-pipeline work (skip for new strategy from scratch)

**From scratch (no prior strategy):** Skip this task. `05-assessment/output/` starts empty.

**If migrating an existing strategy:** Copy prior verdict reports and output files into the pipeline structure so they become part of the auditable record.

```bash
# Copy existing verdict reports into assessment output
cp /path/to/verdict_*.md stages/05-assessment/output/
cp /path/to/verdict_*.json stages/05-assessment/output/

# Archive completed pipeline runs
mkdir -p archive/run_{YYYY}-pre-pipeline
cp -r /path/to/prior_outputs archive/run_{YYYY}-pre-pipeline/
```

**DONE CHECK:** If migrating: `ls stages/05-assessment/output/` shows prior verdict reports. If from scratch: directory exists and is empty — that is correct.

---

### Task 1-25: `audit/audit_log.md` stub

```markdown
# Futures Pipeline Audit Log
# APPEND-ONLY. Never delete or modify entries. Add correction notes instead.
# Entries are generated by: pre-commit hook, post-commit hook, audit_entry.sh

---

## {YYYY-MM-DD} | MANUAL_NOTE
- subject: Pipeline created
- detail: Futures Pipeline scaffold built per Futures_Pipeline_Functional_Spec.md v1.0.
          Pass 1 complete. All five pipeline rules in effect.
          No strategies in autoresearch yet. Gap A controls will activate before first autoresearch run.
          [Note any existing strategies already in paper trading, if applicable.]
- human: {your_name}
```

**DONE CHECK:** File exists. Header present. First manual note present.

---

### Task 1-26: `audit/audit_entry.sh`

Transcribe full script from architecture doc (lines 1150–1229). Key commands: `promote`, `deploy`, `note`, `fill`.

**DONE CHECK:** `bash audit/audit_entry.sh note` runs and prompts for subject/detail. Entry appears in audit_log.md.

---

### Task 1-27: `03-hypothesis/references/strategy_archetypes.md`

**CONSTRAINT: This file defines what the Stage 03 agent is allowed to explore. Never add an archetype without a registered simulator.**

```markdown
# Strategy Archetypes
last_reviewed: 2026-03-11
# Add new archetype here before running Stage 03 autoresearch for it.
# Required fields: simulator module, required data, optimization surface.

## [Add first archetype here after completing NEW ARCHETYPE INTAKE checklist]

## [future archetype template — copy this block for each new archetype]
# Description: [what this strategy does]
# Instrument: [symbol from _config/instruments.md — e.g. NQ, ES, GC]
# Required data: [source_ids from data_registry.md — register new sources before intake]
# simulator_module: [module name — must conform to run(bar_df, touch_row, config, bar_offset) -> SimResult]
# scoring_adapter: [BinnedScoringAdapter | SklearnScoringAdapter | ONNXScoringAdapter]
# feature_evaluator: shared/archetypes/{name}/feature_evaluator.py
# feature_engine: shared/archetypes/{name}/feature_engine.py
# Scoring model: [shared/scoring_models/{name}_v1.json — or none if no scoring model]
# Optimization surface: [params the agent may vary in Stage 04]
# Structural reference: [stages/06-deployment/references/{name}_reference.cpp or equivalent]
# Current status: [intake / hypothesis stage / IS / paper trading / live]

## Example entry (for reference only — shows completed format):
# {archetype_name}
# - Instrument: {SYMBOL}
# - Periods: P1, P2  (or archetype-specific period_ids from period_config.md)
# - Required data: {source_id_1}, bar_data_volume  (use the specific bar type source_id)
# - simulator_module: {archetype}_simulator
# - scoring_adapter: BinnedScoringAdapter
# - feature_evaluator: shared/archetypes/{archetype}/feature_evaluator.py
# - feature_engine: shared/archetypes/{archetype}/feature_engine.py
# - Scoring model: shared/scoring_models/{archetype}_{variant}.json
# - Optimization surface: stop, targets, trail_steps, time_cap, score_threshold
# - Structural reference: stages/06-deployment/references/{strategy_id}_reference.cpp
# - Current status: [intake / hypothesis stage / IS / paper trading / live]

## [future archetype template]
- Description:
- Instrument: [symbol from _config/instruments.md — e.g. NQ, ES, GC]
- Periods: [period_ids from period_config.md — e.g. P1, P2 or P1_rot, P2_rot]
- Required data: [source_ids from data_registry.md — register new sources before intake]
- simulator_module: [module name — must conform to run(bar_df, touch_row, config, bar_offset) -> SimResult]
- scoring_adapter: [BinnedScoringAdapter | SklearnScoringAdapter | ONNXScoringAdapter]
- feature_evaluator: shared/archetypes/{name}/feature_evaluator.py
- feature_engine: shared/archetypes/{name}/feature_engine.py
- Scoring model: [shared/scoring_models/{name}_v1.json — or none if no scoring]
- Optimization surface: [params the agent may vary]
- Structural reference: [stages/06-deployment/references/{name}_reference.cpp or equivalent]
- Current status: hypothesis stage

## Simulator Interface Contract (Option B — dynamic dispatch)
backtest_engine.py loads simulators by module name at runtime via config.archetype.simulator_module.
Every simulator MUST expose this exact interface:

  def run(bar_df, touch_row, config, bar_offset) -> SimResult

Rules:
- Pure function — no I/O, no side effects, no global state
- Returns a SimResult dataclass with: pnl_ticks, win (bool), exit_reason, bars_held
- Violation of this contract breaks backtest_engine.py and all autoresearch loops
- Adding a new strategy = write a new module conforming to this interface, register in strategy_archetypes.md
```

**DONE CHECK:** File exists. First archetype entry complete with current status noted.

---

## PART 1.5: GIT + AUDIT INFRASTRUCTURE

**Run during Pass 1, before any autoresearch. All three components required.**

---

### Task 1.5-01: `autocommit.sh`

Transcribe script from architecture doc. Key params:
- `POLL_INTERVAL=30` (seconds) — increase to 300 for overnight runs
- Commits with prefix `auto:` + timestamp + changed files
- Run as: `nohup bash autocommit.sh &` (survives terminal close)
- **run_id contract:** each commit's short hash (7 chars) is the `run_id` for any results written in that window. Driver scripts must call `git rev-parse --short HEAD` immediately after each experiment and write the value to the `run_id` column in results.tsv before the next commit fires.

**Commit message conventions (all commits in this repo):**
| Prefix | Used by | Example |
|--------|---------|---------|
| `auto:` | autocommit.sh | `auto: 2026-03-15 02:14 \| results.tsv` |
| `manual:` | Human | `manual: end-to-end baseline verified` |
| `promote:` | Human | `promote: {hypothesis_id} → 05-assessment` |
| `deploy:` | Human | `deploy: {strategy_id}_AutoTrader_v1 approved` |

These prefixes are used by lineage reconstruction grep commands and dashboard filtering. Use them consistently.

**DONE CHECK:** Start watcher, edit any file, wait 31 seconds, `git log --oneline | head -3` shows auto-commit with timestamp.

---

### Task 1.5-02: `.git/hooks/pre-commit`

Five responsibilities (in order):
1. Block commits that modify P2 holdout files (hard abort)
2. Enforce audit_log.md append-only (block line deletions)
3. Auto-generate `HYPOTHESIS_PROMOTED` audit entry on file move to `promoted_hypotheses/`
4. Auto-generate `PERIOD_CONFIG_CHANGED` audit entry on `period_config.md` change
5. Warn (not block) on period rollover: "Review all CONTEXT.md files"

Transcribe from architecture doc (lines 1236–1287). `chmod +x .git/hooks/pre-commit`.

**DONE CHECK:**
- Test 1: Stage a change to `p2_holdout/holdout_locked_P2.flag` → commit should abort with error message.
- Test 2: Stage a deletion in `audit_log.md` → commit should abort.
- Test 3: Change `period_config.md` → commit proceeds but prints reminder about CONTEXT.md review.

---

### Task 1.5-03: `.git/hooks/post-commit`

Three responsibilities:
1. Append to `.git/commit_log.txt` (every commit)
2. Auto-generate `OOS_RUN` audit entry when `holdout_locked_P2.flag` file is created
3. Auto-generate `DEPLOYMENT_APPROVED` audit entry when `deployment_ready.flag` is created

Transcribe from architecture doc (lines 1291–1334). `chmod +x .git/hooks/post-commit`.

**Note:** Post-commit hook uses `git commit --amend --no-edit` to add the audit entry to the same commit. This is correct behavior — don't change it.

**EXPERIMENT_ANOMALY entries** are generated by the autoresearch driver scripts (not hooks) when harness returns non-zero exit. Template:
```markdown
## {timestamp} | EXPERIMENT_ANOMALY
- stage: {stage_id}
- run_id: {run_id}
- detected_by: {exit_code / stale_results_tsv / empty_output}
- error_output: {last 20 lines of stderr}
- investigation: # TODO: fill in
- resolution: # TODO: fill in
- resolution_commit: # TODO: fill in
- generated_by: autoresearch driver
```
Driver writes this to `audit/audit_log.md` directly, then calls `git add audit/audit_log.md`. Does not abort the loop — reverts to prior best and continues.

**DONE CHECK:**
- After any commit: `.git/commit_log.txt` has a new entry.
- Simulate OOS_RUN: create `holdout_locked_P2.flag`, commit it → `audit_log.md` shows OOS_RUN entry.

---

### Task 1.5-04: Infrastructure verification

```bash
# Full verification sequence
echo "test" >> README.md
sleep 35 && git log --oneline | head -5   # should show auto-commit

# Pre-commit guard test
echo "deleted line" > /tmp/test_hook.sh
git diff HEAD -- audit/audit_log.md       # ensure no deletions staged

# Confirm hooks are executable
ls -la .git/hooks/pre-commit .git/hooks/post-commit
```

**DONE CHECK:** All three tests pass. autocommit.sh running in background (`ps aux | grep autocommit`).

---

## PART 2: BACKTEST ENGINE CLI WRAP

**BLOCKED until Q1–Q6 answered. Can proceed in parallel with paper trading.**

---

### Task 2-01: Answer Q1–Q6

Fill `stages/04-backtest/references/backtest_engine_qa.md` (template in Part 0, Task P0-4). Commit with `manual:` prefix.

**DONE CHECK:** All six rows filled. No empty cells.

---

### Task 2-02: Patch `data_loader.py`

**Constraint: change only path handling. Do not modify any simulation logic.**

Current issue: 5 paths hardcoded at module level. Fix: accept paths as function arguments.

```python
# Before (module-level constants — broken for headless calling):
P1_CSV_PATH = "C:/Projects/..."

# After (parameterized):
def load_source_data(csv_path: str, bars_path: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    ...
```

Update all 5 hardcoded paths. Update existing callers (`run_*.py` files) to pass paths explicitly. Verify existing entry points still work.

**DONE CHECK:** Run the existing entry-point script(s) that invoke data_loader with explicit paths → same output as before patch. Diff output files confirm identical results. If no prior entry-point exists (new strategy from scratch), confirm the patched data_loader functions are callable with path arguments and return the expected data frames.

---

### Task 2-03: Write `backtest_engine.py`

**Location:** `stages/04-backtest/autoresearch/backtest_engine.py`
**Size:** ~175–225 lines
**Call signature:** `python backtest_engine.py --config config.json --output result.json`

Internal call sequence (do not deviate):
```
check_holdout_flag(config)                     # abort if P2 paths + flag exists (A5)
load_data(config.touches_csv, config.bar_data) # explicit paths, no period awareness (A1)
adapter = load_scoring_adapter(               # adapter wraps model format — engine never
    config.scoring_model_path,                #   touches bin_edges or weights directly (A2)
    config.archetype.scoring_adapter)
touches["score"] = adapter.score(touches)     # single call regardless of model format
route_waterfall(touches, config.routing)
simulator = load_simulator(config.archetype.simulator_module)  # dynamic dispatch (Option B)
for each touch where touch.mode in config.active_modes:        # simulate selectively (A4)
    simulator.run(bars, touch, mode_config, bar_offset)
compute_trade_metrics(trade_results)
write result.json                              # top-level PF + per_mode breakdown (A6)
```

**Dynamic dispatch (Option B):** Engine never hardcodes simulator imports or scoring model logic. It loads the simulator module named in `config.archetype.simulator_module` at runtime, and loads the scoring adapter named in `config.archetype.scoring_adapter` via `load_scoring_adapter()`. Both are registered per-archetype in `strategy_archetypes.md`. Adding a new strategy = write a conforming simulator + adapter (if model format differs) — no engine changes needed.

**Output schema:**
```json
{
  "pf": 2.3, "n_trades": 66, "win_rate": 0.58,
  "total_pnl_ticks": 840, "max_drawdown_ticks": 120,
  "per_mode": {
    "{mode_name_1}": {"pf": 3.1, "n_trades": 42, "win_rate": 0.62},
    "{mode_name_2}": {"pf": 1.4, "n_trades": 14, "win_rate": 0.50}
  }
  // Keys are the mode names from config.active_modes — not hardcoded by the engine
}
```

**DONE CHECK:** `python backtest_engine.py --config config_schema.json --output test_result.json` produces output. PF and n_trades are non-zero and within plausible range for the archetype. Per-mode breakdown present in output (keys match config.active_modes). Holdout guard fires correctly when flag exists and P2 path in config. If migrating an existing strategy, compare PF to prior known result — should match within 0.01.

---

### Task 2-04 & 2-05: Config schema files

**`config_schema.json`:** Reference config showing all required fields and their types. Populate param values from the archetype's actual calibrated params — or use placeholder values for new archetype builds. This file is the structural contract; the values are what the autoresearch driver optimizes.

Structure:
```json
{
  "version": "v1",
  "instrument": "{SYMBOL}",
  "touches_csv": "stages/01-data/data/touches/{source_id}_P1.{ext}",
  "bar_data":    "stages/01-data/data/bar_data/volume/{SYMBOL}_BarData_250vol_P1.txt",
  "scoring_model_path": "shared/scoring_models/{archetype}_{variant}.json",
  "archetype": {
    "name": "{archetype}",
    "simulator_module": "{archetype}_simulator",
    "scoring_adapter": "BinnedScoringAdapter"
  },
  "active_modes": ["{mode_name}"],  // mode names defined per archetype in strategy_archetypes.md
  "routing": { "score_threshold": 0, "seq_limit": 0 },
  "{mode_name}": {
    "stop_ticks": 0,
    "leg_targets": [],
    "trail_steps": [
      {"trigger_ticks": 0, "new_stop_ticks": 0}
    ],
    "time_cap_bars": 0
  }
}
```

Note: `be_trigger_ticks` is NOT a separate field — it is `trail_steps[0].trigger_ticks`. One source of truth.

**`config_schema.md`:** Document every field:
| Field | Type | Valid range | Autoresearch candidate? | Notes |
|-------|------|-------------|-------------------------|-------|
| version | str | semver e.g. v1, v2 | FIXED | Increment when param structure changes; written to results_master.tsv |
| instrument | str | symbol from _config/instruments.md | FIXED | Drives cost_ticks and tick value lookups — must match a registered instrument |
| touches_csv | str | valid path | FIXED | Caller sets per period |
| bar_data | str | valid path | FIXED | Caller sets per period |
| scoring_model_path | str | valid path | FIXED | Frozen from P1 calibration |
| archetype.simulator_module | str | module name | FIXED | Set per archetype |
| archetype.scoring_adapter | str | BinnedScoringAdapter \| SklearnScoringAdapter \| ONNXScoringAdapter | FIXED | Set per archetype; determines which adapter class load_scoring_adapter() returns |
| active_modes | list[str] | archetype mode names (see strategy_archetypes.md) | FIXED | Determines which touches simulate — only modes present in config are simulated |
| routing.score_threshold | int | 30–82 | FIXED | Frozen from scoring model |
| {mode_name}.stop_ticks | int | archetype-defined range | YES | |
| {mode_name}.leg_targets | list[int] | archetype-defined range | YES | Count and values per archetype design |
| {mode_name}.trail_steps | list[{trigger,new_stop}] | see rules below | YES | 1–6 steps |
| {mode_name}.trail_steps[i].trigger_ticks | int | monotonically increasing | YES | |
| {mode_name}.trail_steps[i].new_stop_ticks | int | < trigger, non-decreasing | YES | |
| {mode_name}.time_cap_bars | int | archetype-defined range | YES | |

Trail step validation rules (enforced at config load, not in engine):
- Minimum 1 step, maximum 6 steps
- trigger_ticks strictly monotonically increasing across steps
- new_stop_ticks < trigger_ticks on each step
- new_stop_ticks monotonically non-decreasing across steps
- new_stop_ticks[0] >= 0

**DONE CHECK:** Every field in config_schema.json has a row in config_schema.md. FIXED vs CANDIDATE column complete. Trail step validation rules present.

---

### Task 2-06: Verify determinism

```bash
python backtest_engine.py --config config_schema.json --output run1.json
python backtest_engine.py --config config_schema.json --output run2.json
diff run1.json run2.json   # must show no differences
```

**DONE CHECK:** `diff` shows zero differences. Commit with `manual: determinism verified`.

---

### Task 2-07: Manual end-to-end pass

Run stages 01 → 04 → 05 manually. No autoresearch.
- Stage 01: generate `data_manifest.json` from registered data
- Stage 04: run `backtest_engine.py` with archetype P1 config (any reasonable starting params)
- Stage 05: run assessment on output, generate `verdict_report.md`

**If migrating an existing strategy:** Compare Stage 05 output to prior known result — should match. Any divergence means the engine or config has a bug.
**If building from scratch:** No prior result to compare against. Instead confirm: PF and n_trades are non-zero, verdict_report.md is well-formed, all five sections present. This establishes your first baseline.

**DONE CHECK:** `verdict_report.md` exists and is well-formed. All five statistical_summary.md sections present. If migrating: results match prior known values. Commit with `manual: end-to-end baseline verified`.

---

### Task 2-08: `shared/archetypes/{archetype}/simulation_rules.md`

**CONSTRAINT: This is a documentation task — transcribe actual engine behavior. Do not invent rules. Read the source first.**
**Location:** `shared/archetypes/{archetype}/simulation_rules.md` — archetype-specific. New archetypes get their own copy.

Read the archetype's simulator module(s) and routing logic and document what they actually do. This file becomes the agent's reference for what the engine enforces and what it doesn't.

Required sections:
```markdown
# Simulation Rules
last_reviewed: [date]
# Transcribed from backtest_engine.py source. Do not edit to match desired behavior —
# edit to match actual behavior. If actual behavior is wrong, fix the code, then update here.

## Entry Mechanics
- Entry trigger: [how a signal event becomes a trade]
- Bar offset: [how bar_offset is applied — verified in Stage 01 validation]
- Entry price: [first bar open after signal, or same bar close, etc.]

## Cost Model
- Transaction cost: [N ticks per trade, round trip], applied at exit
- Source: _config/instruments.md (Rule 5 — never hardcode in config JSON)
- Changing this value changes all historical PF calculations

## Exit Mechanics — [mode_name_1]
- [Document each active mode's exit logic: targets, stops, trail rules, time cap]

## Exit Mechanics — [mode_name_2]
- [Repeat for each additional mode defined in active_modes]

## Routing Waterfall
- Order: [mode priority sequence]
- Seq limit: [how sequential touches are counted and capped]
- Inactive modes: [how skipped — absent from config or explicit flag?]

## What the Engine Does NOT Enforce
- P2 holdout guard: enforced by backtest_engine.py (A5 — guard is in the engine, not just the hook)
- Feature entry-time rule: [enforced by feature_rules.md, not engine]
- Iteration budget: [enforced by driver loop, not engine]
```

**DONE CHECK:** File exists at `shared/archetypes/{archetype}/simulation_rules.md`. Entry mechanics, cost model, and exit mechanics sections complete. Reviewed against actual source — no invented behavior.

**Note — calibration scripts are the baseline:** If the archetype has existing grid-sweep or calibration scripts, run them on P1 IS data before starting the Stage 04 driver. Load their top results into `stages/04-backtest/autoresearch/results.tsv` as the seeded baseline. Stage 04 autoresearch extends beyond what grid sweeps can reach (trail step shape optimization, cross-parameter interaction search, fine-grained post-Stage-03 tuning) — it does not replace them. For new archetypes with no prior calibration: seed with 3–5 manually-chosen starting configs from domain knowledge. See Task 3-01 seeding step.

---

## PART 3: PASS 3 — AUTORESEARCH LOOPS

**Build in order: Stage 04 → Stage 02 → Stage 03. Lowest risk first.**
**Do not build Stage 02 or 03 until Stage 04 overnight test passes.**

---

### How the Karpathy Pattern Maps to This Pipeline

The three driver scripts below are direct implementations of the `karpathy/autoresearch` pattern. Before writing any driver, read P0-3. The mapping is:

| Karpathy concept | Stage 02 | Stage 03 | Stage 04 |
|-----------------|----------|----------|----------|
| `train.py` — the ONE file the agent edits | `feature_engine.py` | `hypothesis_config.json` | `exit_params.json` |
| `prepare.py` — fixed harness, agent never touches | `evaluate_features.py` | `hypothesis_generator.py` | `backtest_engine.py` |
| `program.md` — human steers research direction | `autoresearch/program.md` | `autoresearch/program.md` | `autoresearch/program.md` |
| `val_bpb` metric (lower = better) | predictive spread (higher = better) | P1 PF at 3t (higher = better) | P1 PF at 3t (higher = better) |
| Training budget (5-min limit) | 300 experiment budget | 200 experiment budget | 500 experiment budget |
| Keep/revert logic | spread > threshold | PF improves > 0.1 | PF improves > 0.05 |
| Overnight log | `results.tsv` | `results.tsv` | `results.tsv` |

**The invariant across all three stages:** The agent edits exactly one file. The harness is fixed. The human programs `program.md`, not the Python files. The driver loop reads `program.md` at the start of each experiment — that's what makes overnight runs steerable without code changes.

**What `program.md` controls (human writes this each evening):**
- Current search direction ("vary stop distance 100–200t, leave targets fixed")
- Any dead ends to avoid ("session filter tried, no lift")
- Any constraints to tighten ("score threshold must stay ≥ 48")

**Machine-readable fields (driver parses these at loop start — do not rename them):**
- `METRIC:` — name of the field the driver extracts from harness output (e.g. `pf`, `spread`)
- `KEEP RULE:` — improvement threshold the driver applies to the keep/revert decision
- `BUDGET:` — experiment budget limit (driver stops when n_prior_tests reaches this)

Keeping these in program.md rather than in driver code means you can change the optimization target for a stage without touching Python — edit program.md the evening before and the next run picks it up.

**What `program.md` does NOT contain:**
- History of past experiments (that's `results.tsv`)
- Results or metrics (driver writes these)
- Code or implementation details

**The keep/revert loop (identical pattern in all three drivers):**
```python
metric_field, improvement_threshold, budget = read_loop_config(program_md)  # parse METRIC/KEEP RULE/BUDGET
result = run_harness()
if result[metric_field] > current_best + improvement_threshold:
    current_best = result[metric_field]
    save_current_best()       # copy edited file to current_best/
else:
    revert_to_prior_best()    # restore from current_best/
append_to_tsv(result, n_prior_tests, verdict)
```

**Failure handling (add to all three drivers):**
If harness returns non-zero exit code: log `EXPERIMENT_ANOMALY` to audit_log, revert, continue loop. Do not abort the overnight run on a single failure.

---

### Task 3-01: Stage 04 autoresearch driver

**Location:** `stages/04-backtest/autoresearch/driver.py`
**Constraint:** Driver never modifies `backtest_engine.py`. It only modifies exit_params.json.

Core loop:
```python
metric_field, improvement_threshold, budget_limit = read_loop_config(program_md)
while experiment_count < MAX_EXPERIMENTS:
    # Read n_prior_tests = count rows in results.tsv for this archetype
    n_prior_tests = count_prior_tests(results_tsv, archetype)
    if n_prior_tests >= budget_limit:  # from program.md BUDGET line
        log("Budget exhausted. Stopping.")
        break
    params = propose_next_params(results_tsv, current_best, program_md)
    write_params(exit_params_json, params)
    result = subprocess.run(["python", "backtest_engine.py",
                             "--config", "exit_params.json",
                             "--output", "result.json"], capture_output=True)
    if result.returncode != 0:
        log_experiment_anomaly(result.stderr)
        revert_to_prior_best()
        continue
    metric_value = read_metric("result.json", metric_field)
    n_trades = read_n_trades("result.json")
    verdict = "kept" if (metric_value > current_best_metric + improvement_threshold
                         and n_trades >= MIN_TRADES) else "reverted"
    if verdict == "kept":
        current_best_metric = metric_value
        save_current_best(params)
    else:
        revert_to_prior_best()
    append_tsv(results_tsv, params, metric_value, n_trades, n_prior_tests, verdict)
    experiment_count += 1
```

**`program.md`** (≤30 lines):
```markdown
# Stage 04 Parameter Optimization
EDIT: exit_params.json only. DO NOT touch backtest_engine.py.
METRIC: PF@3t on P1. MIN TRADES: 30. BUDGET: 500 experiments.
KEEP RULE: PF improves by > 0.05 AND n_trades ≥ 30.

## Current search direction
[Human updates this each evening before overnight run]
Examples of what to write here:
  "Vary: stop_ticks (80–200), leave targets fixed."
  "Vary: trail_steps trigger values only. Stop and targets frozen at current best."
  "Do not vary: cost_ticks (fixed at 3), score_threshold (frozen from scoring model)."
What NOT to write here: strategy names, specific tick values unique to one archetype,
or anything that wouldn't apply if the archetype were swapped out.

## Prior best
[Driver updates this automatically from results.tsv]
```

**Before first overnight test — seed the baseline:**

**If migrating an existing strategy with prior calibration scripts:**
1. Run the existing calibration/grid-sweep script on P1 data
2. Take top 5–10 results from its output
3. Manually append those rows to `stages/04-backtest/autoresearch/results.tsv` with `verdict: seeded`
4. Set `current_best/` to the best result as the starting params

**If building from scratch (no prior calibration):**
1. Manually write 3–5 plausible starting configs into `results.tsv` with `verdict: seeded`
   — Use domain knowledge to pick reasonable initial values (e.g. stop 2–3x ATR, targets at key Fibonacci levels)
2. Set `current_best/` to the most promising of those configs
3. The first overnight run will explore from there

The seeding step is critical either way — the driver searches from a starting point, not from a random initialization. A good seed means the first overnight run explores useful territory. A bad seed wastes the first 50–100 experiments on obviously wrong params.

**First overnight test:**
- Set `MAX_EXPERIMENTS=50` for first run (not 500)
- Morning review: confirm results.tsv has ~50 rows, PF values vary, keep/revert logic worked
- Expand to 500 after confirming loop is healthy

**DONE CHECK:** Calibration results seeded into results.tsv. 50-experiment test run completes. At least one "kept" entry. n_prior_tests increments correctly. No EXPERIMENT_ANOMALY in audit_log.

---

### Task 3-02: Write `02-features/autoresearch/evaluate_features.py` (dispatcher)

**Build before the Stage 02 driver. This is the fixed dispatcher — agent never edits it.**
**CONSTRAINT: Pure dispatcher. No data loading, no metric logic. Delegates entirely to archetype evaluator.**

```python
# evaluate_features.py — fixed dispatcher (~30 lines)
archetype = read_archetype_from_program_md()
evaluator = load_module(f"shared/archetypes/{archetype}/feature_evaluator.py")
result = evaluator.evaluate()   # standard interface — returns feature_evaluation.json content
write_evaluation_json(result)
```

**`shared/archetypes/{archetype}/feature_evaluator.py`** — write alongside dispatcher.
This is the archetype-specific harness. Agent never edits it directly.

Responsibilities of feature_evaluator.py:
- Load P1 data via `data_manifest.json` (no hardcoded paths)
- Call `shared/archetypes/{archetype}/feature_engine.py` to compute features
- For each feature: compute best-bin vs worst-bin predictive spread
- Compute Mann-Whitney U p-value for spread significance
- Return evaluation dict (dispatcher writes to `feature_evaluation.json`)

**Standard interface contract** (all feature_evaluator.py files must conform):
```python
def evaluate() -> dict:
    # Returns: {"features": [{name, spread, mwu_p, kept}], "n_touches": int}
```

New archetype = write new feature_evaluator.py + feature_engine.py in its archetypes folder.
No changes to evaluate_features.py dispatcher needed.

Write `feature_evaluation.json`:
```json
{
  "timestamp": "...",
  "features_evaluated": [
    {"name": "{feature_name_1}", "spread": 0.34, "p_value": 0.02, "bins": 3, "result": "kept"},
    {"name": "{feature_name_2}", "spread": 0.08, "p_value": 0.41, "result": "reverted"}
  ]
}
```

**DONE CHECK:** `python evaluate_features.py` runs on existing feature_engine.py. Output JSON contains spread and p_value for each registered feature. No hardcoded paths.

---

### Task 3-03: Stage 02 autoresearch driver

**Build only after Stage 04 overnight test passes.**

**Location:** `stages/02-features/autoresearch/driver.py`
**Metric:** Best-bin vs worst-bin predictive spread (not PF — different from Stage 04)
**Agent edits:** `feature_engine.py` only
**Fixed harness:** `evaluate_features.py` (must be written before driver)

`evaluate_features.py` responsibilities:
- Load P1 data via `data_manifest.json`
- Call `feature_engine.py` to compute features on P1
- For each feature: compute best-bin vs worst-bin predictive spread
- Write `feature_evaluation.json`: `{feature_name, spread, p_value, kept}`

`program.md` (≤30 lines):
```markdown
# Stage 02 Feature Engineering
EDIT: feature_engine.py only. DO NOT touch evaluate_features.py.
METRIC: Best-bin vs worst-bin predictive spread on P1.
KEEP RULE: spread > threshold in references/feature_rules.md.
ENTRY-TIME RULE: Every feature must be computable at entry time. Check before adding.
BUDGET: 300 experiments.

## Current search direction
[Human updates this each evening]
```

**DONE CHECK:** 20-experiment test run completes. `results.tsv` shows spread values. At least one feature kept. Entry-time check not bypassed (add a test feature with `Entry-time computable: NO` and confirm it's blocked). Run feature promotion: copy `frozen_features.json` to `03-hypothesis/references/` — confirm Stage 03 CONTEXT.md `Reads` row resolves correctly.

---

### Task 3-04: Write `03-hypothesis/autoresearch/hypothesis_generator.py`

**Build before the Stage 03 driver. This is the fixed harness — agent never edits it.**
**CONSTRAINT: Enforces Rule 4 (P1b replication) structurally. Gate behaviour is controlled by
`replication_gate` in `period_config.md` — read it at runtime, do not hardcode the gate logic.**

Responsibilities:
- Read `hypothesis_config.json`
- Read P1a/P1b boundaries from `data_manifest.json` (Stage 01 computes them from p1_split_rule)
- Run `backtest_engine.py` on P1a (calibration half — dates from manifest)
- Run `backtest_engine.py` on P1b (replication half — dates from manifest, never used during calibration)
- Run Stage 05 assessment inline on P1a result (Bonferroni-adjusted gates)
- Write result JSON:
```json
{
  "hypothesis_id": "...",
  "pf_p1a": 3.2,
  "pf_p1b": 2.1,
  "pf_p1_combined": 2.8,
  "n_trades_p1a": 38,
  "n_trades_p1b": 28,
  "mwu_p": 0.03,
  "replication_pass": true,
  "replication_gate": "flag_and_review",
  "verdict": "Conditional"
}
```
- Read `replication_gate` from `period_config.md` at runtime
- If `replication_pass == false` AND `replication_gate == hard_block`: verdict is `NO`
- If `replication_pass == false` AND `replication_gate == flag_and_review`: verdict is `WEAK_REPLICATION` — log flag, do not auto-block, surface for human review
- If `n_trades_p1b < 15`: replication inconclusive — log `replication_pass: inconclusive`, treat as `flag_and_review` regardless of gate setting

**DONE CHECK:** Run with a known-good hypothesis config → `replication_pass: true`. Set `replication_gate: hard_block`, manually set P1b to empty date range → `verdict: NO`. Set `replication_gate: flag_and_review`, same P1b failure → `verdict: WEAK_REPLICATION`, not NO. Set `n_trades_p1b < 15` → `replication_pass: inconclusive`. All three behaviours verified.

---

### Task 3-05: Stage 03 autoresearch driver

**Build only after Stage 02 overnight test passes.**

**Location:** `stages/03-hypothesis/autoresearch/driver.py`
**Agent edits:** `hypothesis_config.json` only
**Fixed harness:** `hypothesis_generator.py`

`hypothesis_generator.py` responsibilities:
- Read `hypothesis_config.json`
- Run Stage 04 backtest on P1a (calibration)
- Run Stage 04 backtest on P1b (replication — Rule 4 enforcement)
- Run Stage 05 assessment with Bonferroni-adjusted gates
- Write result: `{pf_p1a, pf_p1b, pf_p1_combined, n_trades, mwu_p, verdict, replication_pass}`
- If `replication_pass == false` and `replication_gate == hard_block`: verdict is NO
- If `replication_pass == false` and `replication_gate == flag_and_review`: verdict is WEAK_REPLICATION, surface for human review

`program.md` (≤30 lines):
```markdown
# Stage 03 Hypothesis Generation
EDIT: hypothesis_config.json only. DO NOT touch hypothesis_generator.py.
METRIC: P1 PF at 3t, min 30 trades, passing P1b replication.
KEEP RULE: PF improves by > 0.1 AND replication_pass != false (inconclusive allowed; WEAK_REPLICATION requires human review).
BUDGET: 200 experiments per archetype.

## Current search direction
[Human updates this each evening]
Read references/prior_results.md before each run — avoid repeating failures.
```

**DONE CHECK:** 12-experiment test run completes. results.tsv shows replication_pass column populated. A hypothesis that passes P1a but fails P1b shows `replication_pass: false` and `verdict: WEAK_REPLICATION` (with default `replication_gate: flag_and_review`). Switching gate to `hard_block` → same failure shows `verdict: NO`.

---

### Task 3-06: Wire Stage 05 → Stage 03 feedback loop

**CONSTRAINT: Stage 05 writes `feedback_to_hypothesis.md`. Stage 03 reads `prior_results.md`. These are the same content — wire the copy.**

After each Stage 05 assessment run, the output must flow back to Stage 03 so the hypothesis agent doesn't repeat failures. This is a one-line shell copy, but it must be explicit and tested.

Add to Stage 05 assessment script (or as a post-assessment shell step):
```bash
# After every Stage 05 run — wire feedback to Stage 03
cp stages/05-assessment/output/feedback_to_hypothesis.md \
   stages/03-hypothesis/references/prior_results.md
git add stages/03-hypothesis/references/prior_results.md
# autocommit.sh picks this up within 30s
```

`feedback_to_hypothesis.md` content (Stage 05 generates this):
```markdown
# Feedback to Hypothesis Stage
Generated: {timestamp} | Run: {run_id}

## What passed
- {hypothesis_id}: PF {pf}, {n_trades} trades, verdict {verdict}

## What failed and why
- {hypothesis_id}: PF {pf} — below threshold
- {hypothesis_id}: replication_pass false — P1b PF {pf_p1b}

## Patterns in failures
[Stage 05 summary of common failure modes]

## Suggested next directions
[Stage 05 suggestions based on what worked]
```

**DONE CHECK:** Run Stage 05 assessment. Confirm `feedback_to_hypothesis.md` created in `05-assessment/output/`. Run copy step. Confirm `03-hypothesis/references/prior_results.md` updated. Stage 03 `program.md` references this file — confirm agent will read it.

---

### Task 3-07: Dashboard — DEFERRED TO MILESTONE 2

Full dashboard buildout is scoped in a separate spec: **Futures_Pipeline_Dashboard_Spec.md**.

Rationale for deferral:
- Different skill set from pipeline Python — frontend JS
- Zero dependency on pipeline code — reads TSV only
- Can be built in parallel with Pass 2, giving visibility the moment results flow
- Scope (trend view, feature heatmap, regime breakdown) warrants its own milestone

**What remains in this spec:** Task 1-22 stub HTML placeholder.
**What moves to Milestone 2:** everything else — see Futures_Pipeline_Dashboard_Spec.md.

**Gate to start Milestone 2:** Pass 1 complete + at least one row in results_master.tsv.

---

## DONE CRITERIA BY PASS

### Pass 1 complete when:
- All 27 tasks checked plus sub-tasks 1-09b, 1-11b, 1-11c, 1-14b, 1-14c, 1-17b, 1-18b, 1-19b, 1-20b
- All 7 stage CONTEXT.md files ≤80 lines, front matter present
- `audit/audit_log.md` has first manual entry
- Data files migrated and visible in `01-data/data/`
- `regime_labels.csv` exists covering P1 and P2; `hmm_regime_v1.pkl` serialized

### Pass 1.5 complete when:
- autocommit.sh running (`ps aux | grep autocommit` shows process)
- Pre-commit holdout guard tested and verified
- Post-commit log verified (`cat .git/commit_log.txt` shows entries)

### Pass 2 complete when:
- Q1–Q6 answered and committed
- `shared/archetypes/{archetype}/simulation_rules.md` written from actual source
- `shared/archetypes/{archetype}/exit_templates.md` exists at correct path
- End-to-end manual run completes without error; verdict_report.md is well-formed (if migrating: matches prior known result)
- Determinism verified (diff shows zero)

### Pass 3 complete when:
- Stage 04 overnight test: 50-experiment first run completes healthy; keep/revert logic verified; expand to 500 for mature runs
- `evaluate_features.py` runs cleanly on existing feature_engine.py
- Stage 02 overnight test: features evaluated, entry-time block verified
- `hypothesis_generator.py` enforces Rule 4 (P1b replication) structurally
- Stage 03 overnight test: replication enforced, budget tracked
- Feedback loop wired (Stage 05 → prior_results.md → Stage 03)
- Dashboard: deferred — see Futures_Pipeline_Dashboard_Spec.md (Milestone 2)

---

## OVERNIGHT RUN PROTOCOL

**Follow this every time you start an autoresearch run. Takes 5 minutes. Saves hours of debugging.**

### Evening (before starting run)
```
1. Update program.md for the target stage (≤30 lines — trim if over)
   - Set current search direction
   - Note any dead ends from prior run
2. Check n_prior_tests in results.tsv — confirm budget not exhausted
3. Confirm backtest_engine.py is unmodified: git diff HEAD -- backtest_engine.py
4. Set MAX_EXPERIMENTS (50 for first run of any new loop, budget limit for mature runs)
5. Start run: nohup python driver.py > run.log 2>&1 &
6. Confirm process started: tail -f run.log (should see experiment 1 starting)
```

### Morning (reviewing results)
```
1. Check run completed: tail run.log (should show "experiment N complete" or budget message)
2. Check for anomalies: grep "ANOMALY\|ERROR" run.log
3. Open results.tsv — sort by PF descending
4. Review top 3–5 results in detail (not just PF — check n_trades, win_rate)
5. If any keepers: promote to output/ folder with manual audit entry
6. Update program.md with new direction for next run
7. Update root CONTEXT.md active stage if advancing
```

### Cost estimate (Claude Max subscription — usage included)
| Loop | Experiments/hr | Per experiment | 8hr overnight |
|------|---------------|----------------|---------------|
| Stage 04 params | ~200 | ~$0.02 | ~$32 |
| Stage 02 features | ~50 | ~$0.04 | ~$16 |
| Stage 03 hypothesis | ~12 | ~$0.06 | ~$6 |

---

## LINEAGE RECONSTRUCTION

**How to trace any deployed strategy back to its origin.**

```bash
# Full chain for any hypothesis
grep -A 20 "{hypothesis_id}" audit/audit_log.md

# All OOS runs ever
grep "^## " audit/audit_log.md | grep "OOS_RUN"

# All deployments ever
grep "^## " audit/audit_log.md | grep "DEPLOYMENT_APPROVED"

# All unfilled TODOs in audit log
grep -n "# TODO" audit/audit_log.md

# Trace a deployment back to its source
grep -A 10 "DEPLOYMENT_APPROVED" audit/audit_log.md
# → get hypothesis_id
grep -A 10 "HYPOTHESIS_PROMOTED.*{hypothesis_id}" audit/audit_log.md
# → get source run_id
grep "{run_id}" stages/03-hypothesis/autoresearch/results.tsv
# → get param optimization run
grep "{hypothesis_id}" stages/04-backtest/autoresearch/results.tsv
# → get OOS verdict
grep -A 10 "OOS_RUN.*{period_id}" audit/audit_log.md
```

---

## NEW ARCHETYPE INTAKE (human gate — precedes Stage 03 for new archetype)

**Every new strategy archetype requires this checklist before Stage 03 autoresearch can run.**
**This is not automated. Each item requires human judgment and verification.**

### Data layer (Stage 01 + data_registry.md)
- [ ] Identify required data sources — are they already registered in `data_registry.md`?
- [ ] If new source: add row to `data_registry.md`, drop files into `01-data/data/{source_id}/`
- [ ] If new data format: write schema doc in `01-data/references/{format}_schema.md`
- [ ] Re-run Stage 01 validation — confirm new data passes schema check and date coverage

### Archetype folder (shared/archetypes/{name}/)
- [ ] Create `shared/archetypes/{name}/` folder
- [ ] Write `feature_engine.py` — starting template with at least one working feature
- [ ] Write `feature_evaluator.py` — loads archetype-specific data, calls feature_engine, computes spread metric, returns standard dict
- [ ] Confirm `feature_evaluator.py` conforms to interface: `evaluate() -> {"features": [...], "n_touches": int}`
- [ ] Write `simulation_rules.md` — transcribed from simulator source, not invented
- [ ] Write `exit_templates.md` — exit patterns this archetype supports

### Simulator
- [ ] Write `{name}_simulator.py` (or equivalent) conforming to: `run(bar_df, touch_row, config, bar_offset) -> SimResult`
- [ ] Write unit tests against at least 3 known trade scenarios (win, loss, time-cap exit)
- [ ] Register `simulator_module` in `strategy_archetypes.md`

### Scoring model (if archetype has one)
- [ ] Write `shared/scoring_models/{archetype}_v1.json` with weights + bin_edges
- [ ] Register in `strategy_archetypes.md` under scoring_model field
- [ ] Set `scoring_adapter` field in `strategy_archetypes.md` — default is `BinnedScoringAdapter` for JSON models

### Verification gate
- [ ] Run one manual Stage 04 backtest with a simple config — confirm simulator produces plausible PF and trade count
- [ ] Run `evaluate_features.py` dispatcher with new archetype in program.md — confirm it calls the right evaluator
- [ ] Commit with `manual: {archetype} archetype intake complete`

**Only after all items checked:** Stage 03 autoresearch may generate hypotheses for this archetype.

---

## GROWTH PATH

### Now (Pass 1 — scaffold phase)
- Build scaffold, config files, CONTEXT.md files
- Register data sources and validate data
- If migrating an existing strategy: archive prior outputs and begin `paper_trades.csv` immediately
- Write `statistical_gates.md` with multiple testing controls before any autoresearch

### Medium-term (after first archetype in paper trading)
- Complete Pass 2: backtest engine CLI
- Complete Pass 3: stage 04 param optimization autoresearch
- Run first `live_assessment.md` comparing live vs backtest PF
- Add stage 02 feature autoresearch

### Long-term (P3 data available ~Jun 2026)
- Stage 03 hypothesis autoresearch fully live
- P3 as new OOS forward validation
- Multiple archetypes (e.g. orderflow scalp alongside signal-touch)
- Evaluate live data (200+ trades) for IS promotion
- Regime-conditional assessment active in Stage 05
- Decide Q7: combined IS pool vs separate folds

---

## OPEN QUESTIONS (unresolved as of spec v1.0)

These block specific tasks. Do not proceed past their gate without answers.

| ID | Blocks | Question | Status |
|----|--------|----------|--------|
| Q1 | Task 2-03 | Does data_loader load P1+P2 simultaneously or one at a time? | **ANSWERED** — path-based, period-agnostic |
| Q2 | Task 2-03 | Is the scoring model grid dynamic (percentile bins) or static? | **ANSWERED** — hybrid; engine loads frozen model, never recomputes |
| Q3 | Task 2-03 | TrailStep fields? Optimizable or frozen in autoresearch? | **ANSWERED** — optimizable array; be_trigger_ticks removed |
| Q4 | Task 2-03 | Routing waterfall: all modes or skip inactive? Single-mode flag needed? | **ANSWERED** — route all, simulate selectively; config presence = active |
| Q5 | Task 2-03 | Should backtest_engine.py inherit holdout_locked.flag guard? | **ANSWERED** — yes, guard in engine |
| Q6 | Task 2-04 | Per-mode PF breakdown needed in output JSON? | **ANSWERED** — yes, per-mode required |
| Q7 | Future P3 | Multi-period IS: combined pool or separate folds? Decide before P3 arrives. | Open |
| Gap 3 | Task 1-14 to 1-20 | RinDig ICM repo conventions — fetch before writing CONTEXT.md files | Open |

---

## MASTER BUILD CHECKLIST (mirrored — same as top)

### Before anything:
- [ ] P0-1: Existing strategy deployment (parallel — skip for new strategy from scratch)
- [ ] P0-2: RinDig ICM repo fetched and reviewed
- [ ] P0-3: karpathy/autoresearch repo fetched and reviewed
- [ ] P0-4: Q1–Q6 answered (Pass 2 only)

### Pass 1:
- [ ] 1-01 through 1-27 + 1-09b + 1-11b + 1-11c + 1-14b + 1-17b + 1-18b + 1-19b + 1-20b (see top checklist)

### Pass 1.5:
- [ ] 1.5-01: autocommit.sh
- [ ] 1.5-02: pre-commit hook (holdout guard + audit auto-entries + period rollover warning)
- [ ] 1.5-03: post-commit hook
- [ ] 1.5-04: verification passed

### Pass 2:
- [ ] 2-01: Q1–Q6 answered
- [ ] 2-02: data_loader.py patched
- [ ] 2-03: backtest_engine.py written
- [ ] 2-04: config_schema.json written
- [ ] 2-05: config_schema.md written
- [ ] 2-06: determinism verified
- [ ] 2-07: end-to-end manual pass
- [ ] 2-08: `shared/archetypes/{archetype}/simulation_rules.md` written

### Pass 3:
- [ ] 3-01: Stage 04 driver + overnight test
- [ ] 3-02: evaluate_features.py written
- [ ] 3-03: Stage 02 driver + overnight test
- [ ] 3-04: hypothesis_generator.py written
- [ ] 3-05: Stage 03 driver + overnight test
- [ ] 3-06: feedback loop wired (Stage 05 → prior_results.md)
- [ ] 3-07: Dashboard — DEFERRED to Milestone 2 (see Futures_Pipeline_Dashboard_Spec.md)
