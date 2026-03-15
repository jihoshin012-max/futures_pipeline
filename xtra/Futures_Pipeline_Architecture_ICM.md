# Futures Pipeline Architecture — ICM + Autoresearch

> **Created:** 2026-03-11
> **Updated:** 2026-03-13 (multi-instrument rename, five rules, scoring adapter, feature catalog, 24-col TSV, data_manifest/frozen_params cross-stage, open items refresh)
> **Status:** Ready to build — Pass 1 / Pass 1.5 starting
> **Framework:** ICM (Interpreted Context Methodology) with autoresearch inner loops
> **ICM repo:** https://github.com/RinDig/Interpreted-Context-Methdology
> **Autoresearch repo:** https://github.com/karpathy/autoresearch (confirmed real — reviewed README)
> **M1_A status:** Live in paper trading (zone_touch archetype, Variant A weights)

---

## Overview

A full idea-to-deployment pipeline for futures trading strategies (NQ, ES, GC — extensible). Sequential ICM stages provide structure, human review, and observability. Autoresearch inner loops within selected stages enable autonomous overnight experimentation. One agent, reading the right files at the right moment, does the work that would otherwise require a multi-agent framework.

**The core loop:** Hypothesis → Backtest → Assessment → (repeat) → Deploy

**What runs autonomously:** Feature exploration, hypothesis iteration, parameter optimization

**What requires human review:** Data configuration, hypothesis promotion, deployment approval

---

## Extensibility Convention

The pipeline is designed to accommodate any strategy type and any data source without structural changes. New strategies and data sources plug in at defined extension points; everything outside those points is unchanged.

### The Rule

> **New data → extend Stage 01 only.**
> **New strategy → extend `shared/archetypes/{name}/` only.**
> **New features → extend Stage 02 only.**
> **Stages 04, 05, 06 never change shape — only their inputs change.**

This is what makes the pipeline durable. You can add a mean-reversion strategy, a vol breakout strategy, an orderflow scalp, or anything else — the assessment, parameter optimization, and deployment machinery is reused as-is.

---

### Data Extensibility

Every data source gets a registered entry in `_config/data_registry.md`. This is the single source of truth for what data exists, what period it covers, and where it lives. No stage hardcodes paths — all paths come from the registry.

**`_config/data_registry.md` schema:**

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

Note: Add one row per data source your archetype requires. source_id must be unique and
match the schema file name in 01-data/references/{source_id}_schema.md.

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
3. Re-run Stage 01 validation (regenerates data_manifest.json automatically)
4. Human checkpoint: review validation report
```

**To add a new data source:**
1. Drop files into `01-data/data/<source_id>/`
2. Add a row to `data_registry.md` with source_id, type, description, periods, file pattern, and which stages use it
3. Re-run Stage 01 validation — this generates the updated `data_manifest.json` automatically (never hand-edit data_manifest.json directly)
4. Human checkpoint: review validation report before any downstream stage uses the new source

No other files change. Stages that don't use the new source ignore it entirely.

**Data type taxonomy** (use consistent type labels in the registry):

| type | description | examples |
|------|-------------|---------|
| `touches`    | Per-touch or per-signal event data | ZRA CSVs, signal event files |
| `price` | OHLCV bar data | NQ_BarData files |
| `label` | Classification labels derived from other sources | SBB labels |
| `orderflow` | Intrabar volume/delta data | Cumulative delta, VAP, footprint |
| `fundamental` | Macro/economic data | COT reports, economic calendar |
| `alt` | Alternative data not fitting above | Sentiment, news, etc. |

Add new types to this taxonomy as needed. The type field is used by stage 02 `feature_rules.md` to constrain which features can be built from which sources.

---

### Strategy Extensibility

Every strategy gets a registered archetype in `03-hypothesis/references/strategy_archetypes.md`. This file defines the strategy family, its required data sources, its simulator module, and its optimization surface.

**`strategy_archetypes.md` schema:**

```markdown
# Strategy Archetypes
last_reviewed: 2026-03-11
# Add new archetype here before running Stage 03 autoresearch for it.

## zone_touch
- Description: Trade futures at supply/demand zone edges detected by V4/ZRA
- Instrument: NQ (default; ES, GC supported via instruments.md)
- Periods: P1, P2
- Required data: zone_csv_v2, bar_data_volume
- Simulator module: `shared/archetypes/zone_touch/m1_simulator.py`
- Scoring model: `shared/scoring_models/zone_touch_variant_a.json`
- Scoring adapter: BinnedScoringAdapter
- feature_evaluator: `shared/archetypes/zone_touch/feature_evaluator.py`
- feature_engine: `shared/archetypes/zone_touch/feature_engine.py`
- Optimization surface: stop, targets, trail_steps, time_cap_bars, score_threshold
- Structural reference: `stages/06-deployment/references/zone_touch_reference.cpp`
- Current status: Variant A live in paper trading (M1_A)

## [future archetype template]
- Description: [what this strategy does]
- Instrument: [symbol from _config/instruments.md]
- Periods: [period_ids from period_config.md — e.g. P1, P2 or archetype-specific ids]
- Required data: [source_ids from data_registry.md]
- Simulator module: [shared/archetypes/{name}/{name}_simulator.py]
- Scoring model: [shared/scoring_models/{name}_v1.json — or none if no scoring]
- Scoring adapter: [BinnedScoringAdapter | SklearnScoringAdapter | ONNXScoringAdapter]
- feature_evaluator: shared/archetypes/{name}/feature_evaluator.py
- feature_engine: shared/archetypes/{name}/feature_engine.py
- Optimization surface: [params the agent may vary in Stage 04]
- Structural reference: [stages/06-deployment/references/{name}_reference.cpp or equivalent]
- Current status: hypothesis stage
```

**To add a new strategy archetype:**
1. Add entry to `strategy_archetypes.md` — instrument, description, required data, simulator module path, scoring model path, scoring adapter type, optimization surface
2. Create `shared/archetypes/{name}/` with four required files: `feature_engine.py`, `feature_evaluator.py`, `simulation_rules.md`, `exit_templates.md`
3. If new simulator needed: add to archetype folder — pure function, interface `run(bar_df, touch_row, config, bar_offset) → SimResult`
4. If new scoring model format needed: add adapter class to `shared/scoring_models/scoring_adapter.py` — implement `score(touch_df) → pd.Series`
5. If new features needed: run stage 02 autoresearch with new data source available
6. Complete the new archetype intake checklist (in functional spec) before Stage 03 can run
7. Run normally through stages 04 → 05 → 06

The key constraint on new simulators: **pure functions only**. No I/O, no side effects, no global state. Takes data + config, returns SimResult dataclass. Loaded at runtime by `backtest_engine.py` via `config.archetype.simulator_module` (Option B dynamic dispatch) — drop-in compatible with autoresearch loops.

---

### Feature Extensibility

Features are the bridge between data sources and strategies. Every feature is registered in `shared/feature_definitions.md` with its source data, computation method, bin edges, and which strategies use it.

**`shared/feature_definitions.md` schema:**

```markdown
# Feature Definitions
last_reviewed: {date}
# Entry-time computability is a HARD RULE. Features marked NO are blocked from use.
# Populate this file as Stage 02 autoresearch discovers and approves features.
# From scratch: this file starts with the template only — no pre-registered features.

## Registered Features
(empty — features added here as Stage 02 autoresearch approves them)
(if migrating existing strategy: populate from source code — do not invent)

## Template for new features
### [feature_name]
- Source: [source_id from data_registry.md]
- Computation: [formula — must be computable at entry time, no look-ahead]
- Bin edges: [calibrated on P1 IS data — tercile or custom; frozen in scoring model JSON]
- Entry-time computable: YES / NO
- Used by: [archetype names]
```

**The entry-time rule is enforced here.** If a feature cannot be computed at entry time (e.g., it requires future bar data), it is flagged `Entry-time computable: NO` and blocked from use by `feature_rules.md`. This is a hard constraint — not a guideline.

---

### Extension Checklist (any new data source or strategy)

```
New data source:
  [ ] Files in 01-data/data/<source_id>/
  [ ] Row added to _config/data_registry.md
  [ ] Stage 01 validation re-run and reviewed (regenerates data_manifest.json automatically — never hand-edit it)

New strategy archetype:
  [ ] Entry in 03-hypothesis/references/strategy_archetypes.md (instrument, simulator_module, scoring_adapter)
  [ ] shared/archetypes/{name}/ created with: feature_engine.py, feature_evaluator.py, simulation_rules.md, exit_templates.md
  [ ] Simulator added to archetype folder (pure function, standard interface)
  [ ] Scoring adapter registered in shared/scoring_models/scoring_adapter.py (if new format)
  [ ] Features registered in shared/feature_definitions.md
  [ ] New archetype intake checklist completed (in functional spec)
  [ ] Stage 04 backtest_engine.py supports the new simulator (config.archetype.simulator_module)

New feature:
  [ ] Entry in shared/feature_definitions.md
  [ ] Entry-time computability confirmed
  [ ] Bin edges calibrated on P1
  [ ] feature_engine.py updated
```

---

## IS/OOS Period Control

IS and OOS boundaries are defined in exactly one place: `_config/period_config.md`. No stage, script, or config JSON hardcodes dates or period labels. Everything reads from this file. Rolling the pipeline forward to a new quarter is a one-file edit with no code changes.

### `_config/period_config.md` — full spec

```markdown
# Period Configuration
last_reviewed: 2026-03-11
# NEVER edit this file mid-run. Only update between complete pipeline runs.
# After editing: re-run Stage 01 validation. data_manifest.json is regenerated automatically.

## Active Periods

| period_id | archetype   | role | start_date | end_date   | notes                         |
|-----------|-------------|------|------------|------------|-------------------------------|
| P1        | zone_touch  | IS   | 2025-09-16 | 2025-12-14 | Calibration — used freely     |
| P2        | zone_touch  | OOS  | 2025-12-15 | 2026-03-02 | Holdout — one-shot only       |
| P1        | rotational  | IS   | 2025-09-21 | 2025-12-14 | Calibration — used freely     |
| P2        | rotational  | OOS  | 2025-12-15 | 2026-03-13 | Holdout — one-shot only       |

# Use archetype: '*' to apply a period row to all archetypes.
# Archetype-specific rows take precedence over '*' rows.
# Stage 01 writes per-archetype period boundaries into
# data_manifest.json["archetypes"][{name}]["periods"].

## Rules (do not change)
- IS periods: used for feature calibration, hypothesis search, parameter optimization
- OOS periods: used for final one-shot validation only — never re-run after first use
- A period cannot be both IS and OOS in the same run
- OOS periods become IS when a new OOS period is designated (see Rolling Forward below)

## Rolling Forward (when P3 arrives ~Jun 2026)
1. Add P3 row per archetype (role: OOS) — or single P3 row with archetype: '*' if dates are the same
2. Change P2 role to IS per archetype (after each archetype's one-shot OOS test is complete)
3. Re-run Stage 01 validation
4. No code changes needed

## Example — end of Q2 2026 (P3 arrives)

Before:
| P1 | IS  | 2025-09-16 | 2025-12-14 |
| P2 | OOS | 2025-12-15 | 2026-03-02 |

After (P2 tested, P3 arrives):
| P1 | IS  | 2025-09-16 | 2025-12-14 |
| P2 | IS  | 2025-12-15 | 2026-03-02 | promoted after one-shot OOS test |
| P3 | OOS | 2026-03-03 | 2026-06-30 | new holdout                      |

No code changes. Stage 01 re-reads this file and updates data_manifest.json automatically.

## Example — irregular interval (e.g. 6-week OOS)

| P1 | IS  | 2025-09-16 | 2025-12-14 |
| P2 | IS  | 2025-12-15 | 2026-03-02 |
| P3 | OOS | 2026-03-03 | 2026-04-14 | 6-week window, not quarterly    |

Interval length is unconstrained. The pipeline doesn't care — it reads start/end dates,
not period lengths.

## Internal Replication Sub-periods (Rule 4)
p1_split_rule: midpoint
# Stage 01 computes P1a/P1b dynamically from P1 start/end using this rule.
# Options: midpoint | 60_40 | fixed_days:<N>
# When P1 rolls forward the split auto-updates — no manual date editing.
# Current computed split (written by Stage 01 into data_manifest.json):
#   P1a = 2025-09-16 to 2025-10-31 | P1b = 2025-11-01 to 2025-12-14
replication_gate: flag_and_review
# Options: hard_block | flag_and_review
# flag_and_review recommended when n_trades_p1b < 50 (thin counts make hard gate unreliable).
Any strategy calibrated on full P1 before Rule 4 was introduced is grandfathered — its
existing P2 result stands. Rule 4 applies to all new hypotheses.
```

### How stages consume period_config.md

- **Stage 01** reads period_config.md and writes per-archetype period boundaries into `data_manifest.json` under `archetypes.{name}.periods`. Each archetype gets its own P1/P2 date range (and computed P1a/P1b boundaries). Archetypes without explicit rows inherit wildcard (*) rows. All downstream stages read from the manifest — never from period_config.md directly.

- **Stage 04** `backtest_engine.py` takes explicit file paths in config (`touches_csv`, `bar_data`) with no period awareness (Q1 answer). The driver loop is responsible for passing the correct period's paths. Switching periods = the caller changes the paths in config — the engine itself never reads `data_manifest.json` or resolves period labels.

- **Stage 04** holdout flags are keyed per OOS period: `p2_holdout/holdout_locked_P2.flag` for P2. When P3 becomes OOS, a new `p3_holdout/` folder is created automatically by the pre-commit hook scaffold. P2's flag is unaffected.

- **Stage 05** verdict reports are tagged with `period_id` in their filename and in `results_master.tsv`. Historical verdicts remain attributable to the period they were run against even after that period is promoted to IS.

### What never changes regardless of period rollover

- Frozen scoring models (bin_edges + weights stay frozen per archetype)
- The pipeline rules — all five: P1 calibrate, one-shot OOS, entry-time only, P1a/P1b replication (gate softness controlled by replication_gate), instruments.md
- Any code — no Python files need editing when periods roll forward

**Note on M1_A grandfathering:** M1_A's scoring weights, TF width thresholds, and SBB thresholds were calibrated on all of P1 before Rule 4 (internal replication) was added. These remain frozen as-is. Rule 4 applies to new hypotheses starting from the next autoresearch cycle. M1_A's P2 result stands as its one-shot validation record.

### Clarifying question logged

**Q7 — Multi-period IS calibration:** When P1 and P2 are both IS (after P3 arrives as new OOS), should feature calibration and hypothesis search use the combined IS pool (P1+P2 concatenated) or keep them as separate folds? Combined gives more data; separate folds allow checking for regime drift between periods. This is a design decision to make before P3 arrives — does not need to be answered now.

---

## Gap Analysis (session 2)

Three gaps were identified before building. Status:

### Gap 1: Autoresearch loop implementation — CLOSED
Previously unclear whether `karpathy/autoresearch` existed. Confirmed real. The loop design in this doc is correct and maps directly to Karpathy's pattern. No redesign needed. Implementation is straightforward: a Python driver script that calls the target file modifier, runs the backtest as a subprocess, reads the result JSON, compares to prior best, keeps/reverts, appends to TSV, repeats.

The pattern is deliberately minimal — three files that matter:
- **`prepare.py`** — fixed setup utilities, never touched by the agent
- **`train.py`** — the single file the agent edits each experiment
- **`program.md`** — human-editable steering doc the agent reads before acting

| Karpathy's setup | This pipeline |
|---|---|
| `train.py` (agent edits) | `feature_engine.py` (stage 02), `hypothesis_config.json` (stage 03), exit params JSON (stage 04) |
| `program.md` (human steers) | `program.md` per stage (same name, same concept) |
| `val_bpb` metric (lower = better) | `PF@3t on P1` (higher = better) |
| 5-minute training budget | One backtest run (~seconds for zone CSV backtest) |
| Keep/revert logic | PF improvement threshold per stage |
| Overnight log of experiments | `results.tsv` per stage |

**Key principle:** The human programs `program.md`, not the Python files. The agent edits Python/JSON files within the constraints in `program.md`. This is what makes overnight runs safe.

### Gap 2: Backtest engine headless callability — CLOSED (Q1–Q6 answered)

Audit completed. The library layer is solid and requires zero changes. The problem is entirely in entry points and data loading. This is a wiring job, not a rewrite. Estimated effort: ~2-3 hours.

#### File Inventory (from audit)

| File | Role | Entry Point | Lines |
|------|------|-------------|-------|
| `m1_simulator.py` | M1 3-leg simulator | Library | ~281 |
| `single_simulator.py` | M3/M4/M5 simulator | Library | ~200 |
| `m1_calibration.py` | M1 grid sweep | Library | ~378 |
| `single_calibration.py` | M3/M4/M5 grid sweep | Library | ~284 |
| `data_loader.py` | Load CSVs + bar data | Library | ~199 |
| `feature_engine.py` | 14-feature computation | Library | ~100+ |
| `scoring.py` | Dual-variant scoring | Library | ~100+ |
| `routing.py` | M1→M3→M4→M5 waterfall | Library | ~150+ |
| `p2_holdout.py` | P2 backtest wrapper | Library | ~200+ |
| `run_m1_calibration.py` | M1 calibration runner | main() | ~241 |
| `run_m345_calibration.py` | M3/M4/M5 calibration runner | main() | ~154 |
| `run_p2_holdout.py` | P2 holdout runner | main() | ~189 |
| `run_sbb_rerun.py` | SBB rerun (Steps 1-11) | main() | ~1200+ |
| + 6 more `run_*.py` | Stats, features, verdicts | main() | varies |

#### Core Simulation Functions (what autoresearch calls)

Both are pure functions — no I/O, no side effects. Ready for headless calling as-is.

- `simulate_m1_trade(bar_df, touch_row, config, bar_offset)` — `m1_simulator.py:71`
  Returns `M1TradeResult` with `weighted_pnl`, `overall_outcome`, 3x `LegResult`
- `simulate_single_trade(bar_df, touch_row, config, bar_offset)` — `single_simulator.py:51`
  Returns `SingleTradeResult` with `pnl_ticks`, `outcome`, `exit_reason`

#### Config Dataclasses (the optimization surface)

```python
@dataclass
class M1Config:
    stop_ticks: int                    # e.g. 135
    leg_targets: list[int]             # e.g. [50, 120, 240]
    trail_steps: list[TrailStep] = []  # TrailStep(trigger_ticks, new_stop_ticks)
    time_cap_bars: int = 50
    # Note: be_trigger_ticks removed (Q3) — BE is trail_steps[0] with new_stop_ticks=0

@dataclass
class SingleConfig:
    stop_ticks: int                    # e.g. 80
    target_ticks: int                  # e.g. 160
    trail_steps: list[TrailStep] = []  # BE via trail_steps[0] — no separate be_trigger_ticks
    time_cap_bars: int = 50
```

#### Current Frozen Values (from p2_holdout.py)

| Param | M1-A | M1-B | M3-A | M4-A | M5-A |
|-------|------|------|------|------|------|
| stop | 135 | 90 | 80 | 80 | 120 |
| targets | 50/120/240 | 50/120/240 | 160 | 30 | 80 |
| BE trigger | 30 | 40 | 20 | 30 | 20 |
| time cap | 80 | 120 | 80 | 10 | 30 |
| trail | 4-step | 1-step | — | — | — |

#### Additional Optimizable Params (not yet in config objects)

- Score threshold (per variant, in `scoring.py`)
- Seq threshold (hardcoded sweep [2, 3, 5, None])
- TF ≤ 120m cap (hardcoded in `routing.py:145`)
- TF-specific SBB width thresholds (hardcoded in `run_sbb_rerun.py`)
- Transaction cost: 3 ticks (hardcoded in `m1_calibration.py:22`)

#### Callability Verdict by Layer

| Layer | Headless? | Issue |
|-------|-----------|-------|
| Simulators | YES | Pure functions, zero changes needed |
| Grid sweeps | PARTIAL | Functions clean, M1 grid built dynamically from data |
| Data loading | NO | 5 paths hardcoded at module level in `data_loader.py` |
| Routing | PARTIAL | TF cap, seq limit parameterized in function sig but called with hardcoded values |
| Entry points | NO | Zero CLI arg support, zero config file support |
| **Overall** | **NO** | Library layer clean; problem is entirely entry points + data_loader |

#### backtest_engine.py Build Spec

New file, ~175–225 lines. Plumbs existing library functions together behind a CLI.

**Call signature:**
```
python backtest_engine.py --config config.json --output result.json
```

**Config JSON schema** (final — per Q1–Q6 answers, matches Task 2-04 in functional spec):
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
  "active_modes": ["{mode_name}"],
  "routing": { "score_threshold": 0, "seq_limit": 0 },
  "{mode_name}": {
    "stop_ticks": 0,
    "leg_targets": [],
    "trail_steps": [{"trigger_ticks": 0, "new_stop_ticks": 0}],
    "time_cap_bars": 0
  }
}
```
Notes: No separate `be_trigger_ticks` field (Q3 — BE is `trail_steps[0]` with `new_stop_ticks=0`).
Paths are per-period (Q1 — engine takes explicit paths, no period awareness). Mode names are
archetype-defined (Q4 — config presence = mode active; engine simulates selectively).

**Output JSON schema** (per Q6 — per-mode breakdown required):
```json
{
  "pf": 4.67, "n_trades": 66, "win_rate": 0.318,
  "total_pnl_ticks": 1240, "max_drawdown_ticks": 320,
  "per_mode": {
    "{mode_name_1}": {"pf": 4.67, "n_trades": 66, "win_rate": 0.62},
    "{mode_name_2}": {"pf": 0.0,  "n_trades": 0,  "win_rate": 0.0}
  }
}
```

**Internal call sequence** (Option B dynamic dispatch — per Task 2-03):
```
check_holdout_flag(config)                      # abort if P2 paths + flag exists (Q5)
load_data(config.touches_csv, config.bar_data)  # explicit paths, no period awareness (Q1)
adapter = load_scoring_adapter(                 # adapter wraps model — engine never
    config.scoring_model_path,                 #   touches bin_edges directly (Q2)
    config.archetype.scoring_adapter)
touches["score"] = adapter.score(touches)       # single call regardless of model format
route_waterfall(touches, config.routing)
simulator = load_simulator(config.archetype.simulator_module)  # dynamic dispatch (Option B)
for each touch where touch.mode in config.active_modes:        # simulate selectively (Q4)
    simulator.run(bars, touch, mode_config, bar_offset)
compute_trade_metrics(trade_results)
write result.json                               # top-level PF + per_mode breakdown (Q6)
```

**data_loader.py fix:** Accept paths as function arguments instead of module-level constants. ~15 min change. Existing callers updated to pass paths explicitly.

#### Clarifying Questions — ALL ANSWERED (see Open Items section for full answers)

| Q | Question summary | Answer |
|---|-----------------|--------|
| Q1 | Does data_loader load P1+P2 simultaneously or one period at a time? | One at a time — engine takes explicit file paths, no period awareness |
| Q2 | Is scoring model grid dynamic (percentile bins) or static? | Hybrid; 7 features static, 7 use P1 tercile bins. Bins frozen in scoring model JSON. Engine calls `adapter.score()` — never recomputes bins |
| Q3 | TrailStep fields? Optimizable or frozen? | Optimizable. `{trigger_ticks, new_stop_ticks}`. `be_trigger_ticks` removed — BE is `trail_steps[0]` with `new_stop_ticks=0` |
| Q4 | Routing waterfall — all modes or skip inactive? Single-mode flag needed? | Route all, simulate selectively. Config presence = mode active. No router changes needed |
| Q5 | Should backtest_engine.py inherit holdout guard? | Yes — guard in engine itself, not just hook. Aborts if flag + P2 paths detected |
| Q6 | Per-mode breakdown in output or top-level only? | Per-mode required. Top-level PF drives keep/revert; per-mode is diagnostic |

### Gap 3: ICM repo conventions (RinDig) — OPEN
The RinDig ICM repo was not fetched this session. The CLAUDE.md → CONTEXT.md routing pattern and stage contract format are inferred from this doc, but the actual repo conventions may have specific file format expectations that matter for Claude Code integration. **Fetch and review before writing CONTEXT.md files.**

---

## Build Plan (three passes)

Build in three sequential passes. Each pass has a clear deliverable before the next begins.

### Pass 1 — Scaffold + static content (no pipeline code required)

Can be done entirely from this doc. No dependency on existing Python files.

Deliverables:
- Full folder structure created at `futures-pipeline/`
- `CLAUDE.md` and top-level `CONTEXT.md` routing file
- `_config/` files: `instruments.md`, `data_registry.md`, `period_config.md`, `statistical_gates.md`, `pipeline_rules.md`, `regime_definitions.md`, `context_review_protocol.md`
- `CONTEXT.md` written for all 7 stages (stage contracts: inputs, process, outputs)
- `shared/feature_definitions.md`, `02-features/references/feature_rules.md`, `02-features/references/feature_catalog.md` (seed with known features + dead ends), `shared/scoring_models/` directory + `_template.json` schema, `shared/scoring_models/scoring_adapter.py`
- `shared/archetypes/{archetype}/exit_templates.md` — exit structure patterns for Stage 04 agent (Task 1-17b)
- `dashboard/results_master.tsv` schema + `dashboard/index.html` stub
- Existing verdict reports migrated into `05-assessment/output/`
- `stages/01-data/hmm_regime_fitter.py` + initial `regime_labels.csv` — mandatory Pass 1 infrastructure (fit on P1 only, apply frozen model to P2)
- `03-hypothesis/references/strategy_archetypes.md` — defines what Stage 03 agent is allowed to explore; never add archetype without registered simulator
- `stages/01-data/references/{source_id}_schema.md` (one per data source) + `bar_data_volume_schema.md` (and equivalents for bar_data_time, bar_data_tick) — column contracts Stage 01 validation checks against (Task 1-14b)
- `data_manifest.json` schema specification documented before Stage 01 built (Task 1-14c)
- `stages/05-assessment/references/verdict_criteria.md` + `statistical_tests.md` — Stage 05 reads before every verdict (Task 1-18b)
- `stages/06-deployment/references/context_package_spec.md` — information contract for ACSIL generation (Task 1-19b)
- `stages/06-deployment/assemble_context.sh` — assembles context package; lives at stage root, not in references/
- `stages/07-live/triggers/review_triggers.md` — thresholds that force human review (Task 1-20b)
- Migrate existing data files to `stages/01-data/data/` (touches/, bar_data/volume/, labels/) (Task 1-23) — bar data goes into the subfolder matching its bar type
- `audit/audit_log.md` stub (header + first manual entry documenting pipeline creation)
- `audit/audit_entry.sh` script

**Gate:** Review all CONTEXT.md files before proceeding. If RinDig ICM repo conventions differ, update before Pass 2.

### Pass 2 — Backtest engine CLI wrap (Q1–Q6 answered — ready to build)

Audit done. Library layer requires zero changes. Work is:

1. **Document Q1–Q6 answers** in `stages/04-backtest/references/backtest_engine_qa.md` — commit with `manual:` prefix before writing any engine code
2. **Patch `data_loader.py`** — parameterize 5 hardcoded paths (~15 min)
3. **Write `04-backtest/autoresearch/backtest_engine.py`** — ~175–225 lines; loads simulator_module and scoring_adapter from config.archetype at runtime (Option B dynamic dispatch)
4. **Write `config_schema.json`** — reference config with all fields and types
5. **Write `config_schema.md`** — documents every field, valid ranges, FIXED vs autoresearch candidate
6. **Verify determinism** — run identical config twice, diff outputs, confirm zero differences
7. **Manual end-to-end pass** (Stage 01 → 04 → 05) before adding autoresearch
8. **Write `shared/archetypes/{name}/feature_engine.py`** — starting template with one working feature (used in Pass 3 Stage 02; not required for Stage 01 → 04 → 05 end-to-end pass)
   **Write `shared/archetypes/{name}/simulation_rules.md`** — transcribed from actual simulator, cost_ticks from instruments.md (Rule 5)
   **Register** simulator_module, scoring_adapter paths in strategy_archetypes.md
   Note: feature_evaluator.py is written in Pass 3 (Task 3-02) alongside evaluate_features.py dispatcher
   Note: exit_templates.md is a Pass 1 item (Task 1-17b) — must exist before Pass 2 starts

**Gate:** Run one manual end-to-end pass (stage 01 → 04 → 05) before adding autoresearch.

### Pass 1.5 — Git auto-commit infrastructure (alongside Pass 1)

Git hooks fire on git operations, not on file saves. Auto-commit requires a file watcher that detects changes and triggers commits. Build this during Pass 1 so it's running before any autoresearch loops touch files.

**Three components:**

**1. `autocommit.sh` — the watcher script**
```bash
#!/bin/bash
# Watches futures-pipeline/ for changes and auto-commits with timestamp + changed files
# Run once in background: bash autocommit.sh &

WATCH_DIR="$(git rev-parse --show-toplevel)"
POLL_INTERVAL=30  # seconds

while true; do
    sleep $POLL_INTERVAL
    cd "$WATCH_DIR"
    if ! git diff --quiet || ! git diff --cached --quiet || [ -n "$(git ls-files --others --exclude-standard)" ]; then
        CHANGED=$(git diff --name-only; git ls-files --others --exclude-standard)
        TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')
        git add -A
        git commit -m "auto: $TIMESTAMP | $(echo $CHANGED | tr '\n' ' ' | cut -c1-80)"
    fi
done
```

**2. `.git/hooks/post-commit` — commit log hook**
```bash
#!/bin/bash
# Appends every commit (auto or manual) to a local log for auditability
echo "$(date '+%Y-%m-%d %H:%M:%S') | $(git log -1 --pretty='%h %s')" >> .git/commit_log.txt
```

**3. `.git/hooks/pre-commit` — guard against committing locked files**
```bash
#!/bin/bash
# Prevents accidental commits that modify holdout_locked_P2.flag or p2_holdout/ outputs
# These must never be overwritten once created

PROTECTED=(
    "stages/04-backtest/p2_holdout/holdout_locked_P2.flag"
    "stages/04-backtest/p2_holdout/trade_log_p2.csv"
    "stages/04-backtest/p2_holdout/equity_curve_p2.csv"
)

for f in "${PROTECTED[@]}"; do
    if git diff --cached --name-only | grep -q "$f"; then
        echo "ERROR: Attempted commit modifies protected P2 holdout file: $f"
        echo "P2 holdout is write-once. Aborting commit."
        exit 1
    fi
done
exit 0
```

**Commit message conventions (for dashboard filtering):**
- Auto-commits: `auto: 2026-03-15 02:14:33 | stages/04-backtest/autoresearch/results.tsv`
- Manual commits: `manual: descriptive message` (human writes these)
- Stage promotions: `promote: m1a_v2_sbb_filtered → 05-assessment`
- Deployment approvals: `deploy: M1A_AutoTrader_v1 approved`

**Setup steps (during Pass 1):**
1. Copy `autocommit.sh` to project root
2. Copy hook files to `.git/hooks/` and `chmod +x` both
3. Add `autocommit.sh` to project `README.md` with start instructions
4. Start watcher: `bash autocommit.sh &` — runs in background, survives terminal session if started in `nohup` or tmux
5. Verify: make a change to any file, wait 30s, confirm auto-commit appears in `git log`

**Note on autoresearch runs:** During overnight autoresearch, the watcher will commit every 30s if files changed. With ~100+ experiments per night each writing to `results.tsv`, this produces a dense commit history. That's intentional — full experiment trail is preserved and recoverable. If commit noise is a concern, increase `POLL_INTERVAL` to 300s (5 min) for overnight runs.

**Relationship to existing GitNexus setup:** GitNexus is already installed on `C:\Projects\sierrachart` and provides a knowledge graph of the codebase. The auto-commit hook ensures GitNexus always has current state to index. Run `gitnexus analyze` after overnight runs to re-index the updated pipeline.

---

### Pass 3 — Autoresearch loop (start with stage 04)

Build in order: stage 04 (param optimization) → stage 02 (feature engineering) → stage 03 (hypothesis iteration). Lowest risk first.

Stage 04 autoresearch driver script (per spec Task 3-01):
```python
# stages/04-backtest/autoresearch/driver.py
metric_field, improvement_threshold, budget_limit = read_loop_config(program_md)
while experiment_count < MAX_EXPERIMENTS:
    n_prior_tests = count_prior_tests(results_tsv, archetype)
    if n_prior_tests >= budget_limit:          # BUDGET: line from program.md
        log("Budget exhausted. Stopping.")
        break
    params = propose_next_params(results_tsv, current_best, program_md)
    write_params(exit_params_json, params)     # file is exit_params.json, not params.json
    result = subprocess.run(["python", "backtest_engine.py",
                             "--config", "exit_params.json",
                             "--output", "result.json"], capture_output=True)
    if result.returncode != 0:                 # anomaly handling — do not abort loop
        log_experiment_anomaly(result.stderr)
        revert_to_prior_best()
        continue
    metric_value = read_metric("result.json", metric_field)   # METRIC: from program.md
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

**Gate:** Run one overnight test with stage 04 before building stages 02 and 03 loops. Verify TSV output, keep/revert logic, and experiment count match expectations.

---

## External Resources

### Relevant to this build

**karpathy/autoresearch** — The reference implementation for the autoresearch loop pattern. Review `program.md` and the keep/revert logic in `train.py` before writing the stage 02/03/04 driver scripts. The overnight protocol section of this doc is modeled on this repo.

**ML for Algorithmic Trading (Stefan Jansen, GitHub)** — Relevant for `feature_engine.py` and `evaluate_features.py` in stage 02. His approach to train/test discipline, feature importance, and avoiding lookahead is methodologically sound and applicable to the feature engineering stage. Not relevant for strategy ideas (equities-focused).

**Python for Data Analysis (Wes McKinney)** — Reference for pandas patterns in pipeline scripts. The zone CSV processing, TF×width groupby analysis, and results TSV aggregation are all heavy pandas work.

### Not relevant

All other resources reviewed (PyQuant News, Awesome Quant, Tidy Finance, 150+ Python Quant Programs, Quant Trading GitHub) are equities/portfolio-focused and do not map to NQ futures zone touch mechanics, Sierra Chart ACSIL, or this specific backtest engine. Discard.

---

## Architecture

```
futures-pipeline/
│
├── CLAUDE.md                              # Layer 0: agent identity and global rules
├── CONTEXT.md                             # Layer 1: routes to current stage
│
├── _config/                               # Factory settings (configure once)
│   ├── instruments.md                     # Multi-instrument registry: NQ, ES, GC — tick size, point value, cost_ticks
│   ├── data_registry.md                   # Data sources: types, file patterns, which stages use them
│   ├── period_config.md                   # IS/OOS boundaries — THE ONLY PLACE periods are defined
│   ├── statistical_gates.md               # PF threshold, p-value cutoffs, min trades, iteration limits
│   ├── pipeline_rules.md                  # Five Rules: P1 calibrate, P2 one-shot, entry-time only, internal replication, instruments.md
│   ├── regime_definitions.md             # Regime taxonomy and tagging protocol
│   └── context_review_protocol.md        # When and how to review CONTEXT.md files for staleness
│
├── shared/                                # Cross-stage resources
│   ├── feature_definitions.md             # All features: name, computation, P1-frozen bin edges
│   ├── archetypes/                        # Archetype-specific modules and rules
│   │   └── zone_touch/                   # One folder per archetype
│   │       ├── feature_engine.py         # Stage 02 agent edits this (archetype-specific)
│   │       ├── feature_evaluator.py      # Fixed harness: loads data, calls feature_engine, returns spread
│   │       ├── simulation_rules.md       # Entry/exit mechanics — cost_ticks from instruments.md (Rule 5)
│   │       └── exit_templates.md         # Exit patterns for zone_touch
│   └── scoring_models/                    # Frozen scoring configs
│       ├── scoring_adapter.py             # Adapter interface: BinnedScoringAdapter, SklearnAdapter, ONNXAdapter
│       ├── zone_touch_variant_a.json      # Variant A weights (bin_edges + weights)
│       └── hmm_regime_v1.pkl              # Frozen HMM regime model (fit on P1 only)
│
├── dashboard/                             # Results browser
│   ├── results_master.tsv                 # 24-col ledger: all experiments across all stages/runs
│   └── index.html                         # Filterable dashboard — requires python -m http.server 8000
│   # Note: data_manifest.json → stages/01-data/output/ | frozen_params.json → stages/04-backtest/output/
│
├── stages/
│   ├── 01-data/                           # DATA FOUNDATION
│   ├── 02-features/                       # FEATURE ENGINEERING (autoresearch)
│   ├── 03-hypothesis/                     # HYPOTHESIS GENERATION (autoresearch)
│   ├── 04-backtest/                       # BACKTEST SIMULATION (autoresearch for params)
│   ├── 05-assessment/                     # STATISTICAL ASSESSMENT (deterministic)
│   ├── 06-deployment/                     # SC STUDY GENERATION (manual gate)
│   └── 07-live/                           # LIVE PERFORMANCE MONITOR (paper + funded)
│
├── audit/                                 # Append-only decision + event log
│   ├── audit_log.md                       # Human decisions + auto-generated event entries
│   └── audit_entry.sh                     # CLI script for human-initiated entries
│
└── archive/                               # Completed runs, version history
    ├── run_2026-03-15_m1a_baseline/
    └── run_2026-04-01_feature_expansion/
```

---

## Stage Details

### Stage 01: Data Foundation

**Purpose:** Load, validate, and register all data. Configure once, everything else builds on top.

**Human effort:** Manual setup, then hands-off. No autoresearch.

```
01-data/
├── CONTEXT.md                    # Stage contract
├── references/
│   ├── zone_csv_v2_schema.md     # Column contract for zone_csv_v2 source (filename = source_id)
│   ├── sbb_labels_schema.md      # Column contract for sbb_labels source (filename = source_id)
│   └── bar_data_volume_schema.md # Column contract for bar_data_volume (and equivalents for _time, _tick)
│   # Rule: one schema file per source_id — filename must match source_id in data_registry.md
├── data/
│   ├── touches/                  # Touch/signal data: v1 and v2 ZRA CSVs (P1, P2, future P3+)
│   ├── bar_data/                 # OHLCV bar files — subfolders by bar type
│   ├── volume/               # 250-vol bars (zone_touch current)
│   ├── time/                 # 1-min time bars (future strategies)
│   └── tick/                 # Tick bars (future strategies)
│   └── labels/                   # SBB labels (v2-only-broken, normal, v2-only-held)
└── output/
    ├── data_manifest.json        # What's available, period boundaries, row counts
    └── validation_report.md      # Schema checks, offset verification, date coverage
```

**Stage contract:**
- Inputs: raw CSV and bar data files
- Process: validate schemas, discover bar offsets, label SBB touches, register periods, fit+apply HMM regime model (P1 fit only, frozen model applied to P2)
- Outputs: data_manifest.json, validation_report.md, regime_labels.csv, hmm_regime_v1.pkl
- Human checkpoint: review validation report before proceeding

**Growth:** As new data arrives (P3 Jun 2026, P4 Sep 2026, etc.), drop files into `data/`, re-run stage. New periods auto-register.

---

### Stage 02: Feature Engineering

**Purpose:** Explore and define features computable at entry time.

**Autoresearch: YES.** Agent proposes features, measures predictive spread, keeps or reverts.

**Autoresearch pattern (maps to karpathy):**
- `feature_engine.py` = `train.py` (the file the agent edits)
- `evaluate_features.py` = the fixed evaluation harness (maps to `prepare.py`)
- `program.md` = human steering doc (same concept, same name)
- Metric: best-bin vs worst-bin predictive spread on P1 (keep rule: spread > 0.15 AND MWU p < 0.10)

```
02-features/
├── CONTEXT.md
├── references/
│   ├── feature_rules.md          # Constraints: must be entry-time computable
│   └── feature_catalog.md        # Complete failure history: active / dropped / dead ends (no line limit)
├── autoresearch/
│   ├── program.md                # "Only modify feature_engine.py. Measure predictive spread."
│   ├── evaluate_features.py      # Fixed dispatcher: calls shared/archetypes/{name}/feature_evaluator.py
│   ├── results.tsv               # feature name | spread | mwu_p | kept/reverted
│   └── current_best/             # Best feature set so far
│   # Note: feature_engine.py lives in shared/archetypes/{name}/ (agent edits there)
└── output/
    ├── frozen_features.json      # Human-approved feature set for downstream stages
    └── feature_report.md         # What was explored, what survived, what was dropped
```

**Autoresearch program (overnight):**
- Agent reads `02-features/references/feature_catalog.md` to avoid dead ends before proposing
- Agent proposes a new feature and edits `shared/archetypes/{name}/feature_engine.py`
- Runs `evaluate_features.py` dispatcher → calls archetype's `feature_evaluator.py` on P1
- If spread > 0.15 AND MWU p < 0.10: keep, log to `results.tsv`
- If below threshold: revert, log as failed, try next idea
- Human updates `02-features/references/feature_catalog.md` after each overnight run
- ~100–300 experiments overnight (budget: 300)

**Human checkpoint:** Morning review of `results.tsv`. Promote best features to `output/frozen_features.json`.

---

### Stage 03: Hypothesis Generation

**Purpose:** Generate and iterate trading strategy hypotheses.

**Autoresearch: YES.** Agent explores strategy archetypes, routing rules, scoring configurations.

**Autoresearch pattern (maps to karpathy):**
- `hypothesis_config.json` = the one file the agent edits (maps to `train.py`) — the agent writes a new strategy config each experiment
- `hypothesis_generator.py` = fixed harness that receives the config, runs backtest + assessment, returns a PF score (maps to `prepare.py`) — agent never edits this
- `program.md` = human steering (what to explore: "test session filters", "try orderflow features")
- Metric: P1 PF at 3t cost

```
03-hypothesis/
├── CONTEXT.md
├── references/
│   ├── prior_results.md          # Auto-fed from 05-assessment: what passed/failed
│   ├── strategy_archetypes.md    # Known patterns: zone bounce, SBB-filtered, orderflow
│   └── frozen_features.json      # From 02-features output
├── autoresearch/
│   ├── program.md                # Steering doc: "Write hypothesis_config.json. Run generator."
│   ├── hypothesis_config.json    # The ONE file the agent edits — strategy config per experiment
│   ├── hypothesis_generator.py   # Fixed harness: receives config, runs backtest+assess, returns PF
│   ├── results.tsv               # hypothesis | PF | verdict | trade_count | kept/reverted
│   └── current_best/             # Best strategy configs so far
└── output/
    ├── promoted_hypotheses/      # Human-approved configs to advance to param opt
    └── hypothesis_report.md      # Summary of exploration, themes, dead ends
```

**Autoresearch program (overnight):**
- Agent reads `autoresearch/program.md` for direction (human updates each evening)
- Agent reads `prior_results.md` to avoid repeating failures
- Generates a strategy config (scoring weights, routing rules, gates)
- Runs stages 04+05 inline (backtest + assessment on P1)
- If PF > prior best by 0.1: keep, else discard
- Logs to `results.tsv`
- ~12 experiments/hour, ~100 overnight

**Human checkpoint:** Review `results.tsv`. Pick winners. Update `autoresearch/program.md` to steer next run.

---

### Stage 04: Backtest Simulation

**Purpose:** Bar-by-bar simulation with actual entries, stops, targets, partial exits.

**Autoresearch: YES (parameter optimization).** Once a hypothesis is promoted, agent optimizes exit params.

**Autoresearch pattern (maps to karpathy):**
- Exit params JSON = `train.py` (what the agent varies)
- `backtest_engine.py` = fixed engine, never modified by agent (maps to `prepare.py`)
- `program.md` = constraints ("vary stop 100-300t, targets must sum to 1.0")
- Metric: P1 PF at 3t, minimum 30 trades

**Gap 2 status: CLOSED.** All six clarifying questions answered. backtest_engine.py spec complete — see Gap 2 section. Build proceeds per Pass 2 sequence.

```
04-backtest/
├── CONTEXT.md
├── references/
│   ├── promoted_hypothesis.json  # From 03-hypothesis output
│   ├── backtest_engine_qa.md     # Q1–Q6 answers committed before engine code written (Task 2-01)
│   # simulation_rules.md → shared/archetypes/{archetype}/simulation_rules.md (Rule 5 compliant)
│   # exit_templates.md  → shared/archetypes/{archetype}/exit_templates.md
├── autoresearch/
│   ├── program.md                # "Only modify exit params. Measure PF at 3t on P1."
│   ├── backtest_engine.py        # Fixed simulation engine — agent never edits this
│   ├── results.tsv               # stop | targets | PF | win_rate | trade_count
│   └── current_best/             # Best param set so far
├── output/
│   ├── frozen_params.json        # Human-approved exit parameters
│   ├── trade_log.csv             # Every trade: entry, exit, PnL, exit reason
│   └── equity_curve.csv          # Cumulative PnL over time
└── p2_holdout/                   # ONE-SHOT — never re-run
    ├── trade_log_p2.csv
    ├── equity_curve_p2.csv
    └── holdout_locked_P2.flag     # Presence = P2 already tested, do not repeat (enforced at engine level)
```

**Autoresearch program:**
- Strategy archetype fixed (from promoted hypothesis)
- Agent varies: stop distance, target ratios, BE trigger, trail rules, time cap
- Runs P1 backtest for each param set
- Maximizes PF at 3t while maintaining ≥ 30 trades
- ~hundreds of experiments/hour (fast — just param changes)

**Relationship to existing calibration scripts:** `m1_calibration.py` already performs a grid sweep over the stop/target/BE/time-cap space on P1 data. For M1_A, this sweep has likely already found the good region of those parameters. Stage 04 autoresearch is not a replacement — it extends into areas the grid can't reach efficiently: trail step shape optimization (combinatorially large, structurally irregular), cross-parameter interaction search (adaptive rather than exhaustive), and param tuning for new archetypes produced by Stage 03. Run the calibration scripts first and seed their top results into `results.tsv` as the starting baseline. The driver searches from there.

**Critical:** P2 holdout is NOT part of autoresearch. P2 runs exactly once with frozen params. The `holdout_locked_P2.flag` prevents re-runs. This enforces Rule 2 structurally — enforced at engine level, not just hook level.

---

### Stage 05: Statistical Assessment

**Purpose:** Compute statistical metrics and render verdicts. Purely deterministic — no exploration.

**No autoresearch.**

```
05-assessment/
├── CONTEXT.md
├── references/
│   ├── verdict_criteria.md       # Yes/Conditional/No gate definitions
│   └── statistical_tests.md      # MWU, permutation, random percentile specs
└── output/
    ├── verdict_report.md         # Full verdict with justification
    ├── verdict_report.json       # Machine-readable for dashboard
    ├── statistical_summary.md    # Sharpe, DD, MWU p, perm p, percentile, regime breakdown
    └── feedback_to_hypothesis.md # Auto-generated: what worked, what didn't, suggestions
```

**Feedback loop:** After assessment, `feedback_to_hypothesis.md` is copied to `03-hypothesis/references/prior_results.md`. The hypothesis agent reads this on the next run to avoid repeating failures.

---

### Stage 06: Deployment Builder

**Purpose:** Generate Sierra Chart ACSIL study code from frozen strategy parameters. Manual gate — human approves every deployment.

**No autoresearch.**

```
06-deployment/
├── CONTEXT.md
├── assemble_context.sh           # Assembles context package — run from 06-deployment/ root
├── references/
│   ├── M1B_AutoTrader.cpp        # Structural reference — copied from Trading Modes pipeline
│   ├── context_package_spec.md   # Information contract for ACSIL generation prompt
│   └── alignment_test.py         # ZB4 vs ZRA comparison script — run before deployment
└── output/
    ├── {strategy_id}/            # One folder per deployed strategy
    └── deployment_ready.flag     # Created only after all checks pass
```

**Note on templates:** `acsil_templates/` with static C++ snippets is replaced by `assemble_context.sh` + Claude Code. `assemble_context.sh` assembles the full context package from pipeline outputs; Claude Code determines output file structure.

**Human checkpoint:** Review generated code, run alignment test, compile, verify on replay. Only human creates `deployment_ready.flag`.

---

### Stage 07: Live Performance Monitor

**Purpose:** Track paper and funded trade results against backtest expectations. Detect drift, trigger human reviews, and maintain the feedback path from live execution back into the pipeline.

**No autoresearch. No code generation. Monitor only.**

```
07-live/
├── CONTEXT.md
├── data/
│   ├── paper_trades.csv          # Running log of all paper trades from M1B
│   └── live_trades.csv           # Future: live funded trades
├── output/
│   ├── live_assessment.md        # Periodic comparison vs backtest expectations
│   └── drift_report.md           # Is live PF tracking backtest PF over time?
└── triggers/
    └── review_triggers.md        # Conditions that force a pipeline review
```

**Stage contract:**
- Inputs: trade logs from Sierra Chart M1B_AutoTrader (manual export), `05-assessment/output/verdict_report.json` (backtest expectations baseline)
- Process: compare live metrics to backtest metrics, check trigger thresholds, flag anomalies
- Outputs: `live_assessment.md` (periodic), `drift_report.md` (rolling), MANUAL_NOTE audit entries when triggers fire
- Human checkpoint: monthly review of `live_assessment.md`; immediate review when any trigger fires

**Growth:** Paper trading starts immediately at M1_A deployment. Live funded trades added to `live_trades.csv` when paper trading phase completes. After 200+ trades, evaluate for IS promotion via `PERIOD_CONFIG_CHANGED` audit entry.

---

## Autoresearch Integration

### Where Autoresearch Runs

| Stage | Autoresearch | Agent edits | Fixed harness | Metric |
|-------|-------------|-------------|---------------|--------|
| 01-data | No | — | — | — |
| 02-features | Yes | `shared/archetypes/{name}/feature_engine.py` | `evaluate_features.py` → `feature_evaluator.py` | Predictive spread (spread > 0.15, MWU p < 0.10, budget 300) |
| 03-hypothesis | Yes | `hypothesis_config.json` | `hypothesis_generator.py` (enforces Rule 4 — gate behaviour from replication_gate in period_config.md) | P1 PF@3t, replication_pass not false, WEAK_REPLICATION → human review (budget 200) |
| 04-backtest | Yes | `exit_params.json` | `backtest_engine.py` (Option B dynamic dispatch) | P1 PF@3t, improve > 0.05 (budget 500) |
| 05-assessment | No | — | — | — |
| 06-deployment | No | — | — | — |
| 07-live | No | — | — | — |

### Run Order

1. Feature engineering first (02) — expand signal vocabulary
2. Hypothesis loop second (03) — explore strategies with expanded features
3. Parameter optimization last (04) — fine-tune the winners

Don't run all three simultaneously. Each produces inputs for the next. Running them in parallel creates a combinatorial explosion where improvements can't be attributed.

### Overnight Run Protocol

```
Evening:
  1. Update autoresearch/program.md for the target stage (≤30 lines — trim if over)
     - Set current search direction; note dead ends from prior run
  2. Check n_prior_tests in results.tsv — confirm budget not exhausted
  3. Confirm backtest_engine.py is unmodified: git diff HEAD -- backtest_engine.py
  4. Set MAX_EXPERIMENTS (50 for first run of any new loop; budget limit for mature runs)
  5. Start run: nohup python driver.py > run.log 2>&1 &
  6. Confirm process started: tail -f run.log (should see experiment 1 starting)

Morning:
  1. Check run completed: tail run.log ("experiment N complete" or budget message)
  2. Check for anomalies: grep "ANOMALY\|ERROR" run.log
  3. Open results.tsv — sort by metric descending
  4. Review top 3–5 results in detail (not just metric — check n_trades, win_rate)
  5. If any keepers: promote to output/ folder with manual audit entry
  6. Update autoresearch/program.md with new direction for next run
  7. Update root CONTEXT.md active stage if advancing
```

### Cost Estimate (Sonnet 4.6)

| Loop type | Experiments/hour | Cost/experiment | 8hr overnight |
|-----------|-----------------|-----------------|---------------|
| Feature engineering | ~50 | ~$0.04 | ~$16 |
| Hypothesis iteration | ~12 | ~$0.06 | ~$6 |
| Parameter optimization | ~200 | ~$0.02 | ~$32 |

With Claude Max subscription ($100/month), Claude Code usage is included.

---

## Dashboard

`dashboard/results_master.tsv` aggregates across all stages and runs:

```
run_id | stage | timestamp | hypothesis_name | archetype | version | features | pf_p1 | pf_p2 | trades_p1 | trades_p2 | mwu_p | perm_p | pctile | n_prior_tests | verdict | sharpe_p1 | max_dd_ticks | avg_winner_ticks | dd_multiple | win_rate | regime_breakdown | api_cost_usd | notes
```

`dashboard/index.html` reads this TSV and provides:
- Sort by any column
- Filter by verdict (Yes/Conditional/No), stage, archetype
- Click a row to see full assessment output
- Trend view: PF over time across runs
- Feature heatmap: which features appear in passing strategies

Requires `python -m http.server 8000` — fetch() is blocked on file:// protocol. Open at http://localhost:8000.

---

## ICM Conventions Applied

| ICM Principle | How It Applies |
|---|---|
| One stage, one job | Each stage has a single responsibility |
| Plain text interface | All configs, results, handoffs are markdown/JSON/TSV |
| Layered context loading | Agent at stage 03 doesn't load bar data; agent at stage 04 doesn't load hypothesis history |
| Every output is an edit surface | Edit any output file before advancing — next stage picks up your changes |
| Configure the factory, not the product | `_config/` sets rules once; individual runs follow them |
| Stage contracts | Every CONTEXT.md has Inputs, Process, Outputs tables |
| Human checkpoints | Autoresearch results reviewed before promotion |
| One-way dependencies | Stages reference prior stages, never forward |
| Agent edits one file | Per autoresearch pattern: each loop has one and only one file the agent modifies |
| Human programs the program.md | Research direction is human-controlled; execution is agent-controlled |

---

## Growth Path

### Near-term (M1_A paper trading phase)
- Complete Pass 1: scaffold + static content, migrate existing data/code
- Dashboard populated with completed runs (v1, v2, SBB verdict reports)
- Manual hypothesis iteration (no autoresearch yet)
- Build `07-live/` scaffold, begin populating `paper_trades.csv` immediately
- Write `_config/statistical_gates.md` with multiple testing limits (Gap A) — before any autoresearch run
- Write `_config/context_review_protocol.md` with staleness thresholds (Gap D)

### Medium-term (after 100 M1_A paper trades)
- Complete Pass 2: audit backtest engine, add CLI wrapper
- Complete Pass 3: stage 04 autoresearch for exit optimization (ITER-02)
- Add stage 02 autoresearch for feature exploration (ITER-04 candidates)
- Run first `live_assessment.md` comparing live vs backtest PF (Gap B)
- Add regime labels to `01-data/data/labels/` — compute from existing bar data (Gap C)

### Long-term (P3 data available, Jun 2026)
- Stage 03 autoresearch: full autonomous hypothesis loop
- P3 as new OOS forward validation period
- Multiple archetypes running in parallel
- Evaluate live data (200+ trades) for IS promotion (Gap B)
- Regime-conditional assessment active in stage 05 (Gap C)
- Orderflow scalp strategies alongside zone touch strategies

---

## Relationship to Existing Work

| Existing asset | Where it lives in pipeline |
|---|---|
| v1/v2 ZRA CSVs | `01-data/data/touches/` |
| NQ bar data (250-vol) | `01-data/data/bar_data/volume/` |
| SBB labels | `01-data/data/labels/` |
| M1_A scoring weights | `shared/scoring_models/zone_touch_variant_a.json` (renamed to archetype convention) |
| TF width thresholds | Absorbed into `shared/archetypes/zone_touch/simulation_rules.md` and `_config/instruments.md` (Rule 5) |
| Trading Modes pipeline (Python) | `04-backtest/autoresearch/backtest_engine.py` |
| M1B_AutoTrader.cpp | `06-deployment/references/M1B_AutoTrader.cpp` (structural reference for ACSIL generation) |
| ZB4/ZRA/V4 source | `06-deployment/references/` (via alignment_test.py) |
| Context transfer doc | `_config/` (absorbed into stage configs) |
| Verdict reports (v1, v2, SBB) | `05-assessment/output/` and `archive/` |

---

## Audit Tracker

### Design

The audit tracker captures what git history and results TSVs cannot: decision-level events, cross-stage lineage, and human reasoning. It is append-only — no entry is ever modified or deleted once written.

**What's already covered elsewhere (not duplicated here):**
- Every file change → git auto-commit (autocommit.sh)
- Every experiment result → `results.tsv` per stage
- P2 holdout integrity → `holdout_locked_P2.flag` + pre-commit hook + engine-level guard

**What the audit tracker adds:**
- Why a hypothesis was promoted over alternatives
- Full chain: experiment → hypothesis → params → P2 run → deployment
- Human decisions distinguished from agent decisions
- Period boundary changes with reasoning
- Anomaly record when overnight runs fail
- Immutable P2 run record independent of file system state

---

### Automation Level by Event Type

| Event | Auto-generation | Human fields |
|-------|----------------|--------------|
| `OOS_RUN` | Full — hook reads result JSON, creates entry on flag creation | None — self-documenting |
| `PERIOD_CONFIG_CHANGED` | Full — hook diffs period_config.md, captures before/after | `reason` if commit message omits it |
| `EXPERIMENT_ANOMALY` | Partial — autoresearch driver script detects non-zero exit, fills stage/run_id/error | `investigation`, `resolution` — fill later |
| `HYPOTHESIS_PROMOTED` | Partial — hook detects file move into promoted_hypotheses/, fills metrics | `reason`, `alternatives_considered` |
| `DEPLOYMENT_APPROVED` | Partial — hook detects deployment_ready.flag creation, fills files/hashes | `note` |
| `MANUAL_NOTE` | None — human-only via audit_entry.sh | All fields |

**Rule for partial entries:** Auto-generated fields are filled immediately. Human fields are written as `# TODO: fill in` placeholders. Human completes them at next convenient moment — not required to block the pipeline.

---

### Event Templates

#### OOS_RUN — fully automatic
```markdown
## {timestamp} | OOS_RUN
- period: {period_id}
- hypothesis_id: {hypothesis_id}
- frozen_params_commit: {git_hash of frozen_params.json}
- result_file: {path to trade_log_p2.csv} (commit {git_hash})
- pf_{period_id_lower}: {pf from result JSON}
- n_trades: {n_trades from result JSON}
- verdict: {verdict from verdict_report.json}
- holdout_flag_created: {timestamp}
- generated_by: post-commit hook
```

#### PERIOD_CONFIG_CHANGED — fully automatic
```markdown
## {timestamp} | PERIOD_CONFIG_CHANGED
- file: _config/period_config.md
- commit: {git_hash}
- before:
  {prior table snapshot}
- after:
  {new table snapshot}
- reason: {from commit message, or "# TODO: fill in"}
- generated_by: pre-commit hook
```

#### EXPERIMENT_ANOMALY — partially automatic
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

#### HYPOTHESIS_PROMOTED — partially automatic
```markdown
## {timestamp} | HYPOTHESIS_PROMOTED
- hypothesis_id: {from filename}
- promoted_from: 03-hypothesis/autoresearch/current_best/
- promoted_to: 03-hypothesis/output/promoted_hypotheses/
- commit: {git_hash}
- pf_p1: {from results.tsv}
- n_trades_p1: {from results.tsv}
- mwu_p: {from results.tsv if present}
- reason: # TODO: fill in
- alternatives_considered: # TODO: fill in
- generated_by: pre-commit hook
```

#### DEPLOYMENT_APPROVED — partially automatic
```markdown
## {timestamp} | DEPLOYMENT_APPROVED
- hypothesis_id: {from context}
- output_file: 06-deployment/output/{filename}
- output_commit: {git_hash}
- alignment_report: 06-deployment/output/alignment_report.md
- checklist_completed: YES
- note: # TODO: fill in
- generated_by: post-commit hook (deployment_ready.flag detected)
```

#### MANUAL_NOTE — human only via audit_entry.sh
```markdown
## {timestamp} | MANUAL_NOTE
- subject: {free text}
- detail: {free text}
- human: {name}
```

---

### audit_entry.sh — CLI for human-initiated entries

```bash
#!/bin/bash
# Usage: bash audit_entry.sh <event_type>
# event_type: promote | deploy | note | fill <line_number>
# Appends a templated entry to audit/audit_log.md or fills a TODO placeholder

AUDIT_LOG="$(git rev-parse --show-toplevel)/audit/audit_log.md"
TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')

case "$1" in
  promote)
    echo "hypothesis_id:"
    read HYP_ID
    echo "pf_p1 (from results.tsv):"
    read PF
    echo "n_trades_p1:"
    read N
    echo "reason (1-2 sentences):"
    read REASON
    echo "alternatives_considered:"
    read ALT
    cat >> "$AUDIT_LOG" << EOF

## $TIMESTAMP | HYPOTHESIS_PROMOTED
- hypothesis_id: $HYP_ID
- pf_p1: $PF
- n_trades_p1: $N
- reason: $REASON
- alternatives_considered: $ALT
- human: $(git config user.name)
EOF
    echo "Entry appended to audit_log.md"
    ;;

  deploy)
    echo "hypothesis_id:"
    read HYP_ID
    echo "note (alignment checks, replay verification):"
    read NOTE
    cat >> "$AUDIT_LOG" << EOF

## $TIMESTAMP | DEPLOYMENT_APPROVED
- hypothesis_id: $HYP_ID
- output_commit: $(git rev-parse --short HEAD)
- checklist_completed: YES
- note: $NOTE
- human: $(git config user.name)
EOF
    echo "Entry appended to audit_log.md"
    ;;

  note)
    echo "subject:"
    read SUBJECT
    echo "detail:"
    read DETAIL
    cat >> "$AUDIT_LOG" << EOF

## $TIMESTAMP | MANUAL_NOTE
- subject: $SUBJECT
- detail: $DETAIL
- human: $(git config user.name)
EOF
    echo "Entry appended to audit_log.md"
    ;;

  fill)
    # Open audit_log.md at first TODO line in editor
    TODO_LINE=$(grep -n "# TODO" "$AUDIT_LOG" | head -1 | cut -d: -f1)
    if [ -z "$TODO_LINE" ]; then
      echo "No TODO placeholders found in audit_log.md"
    else
      ${EDITOR:-nano} +"$TODO_LINE" "$AUDIT_LOG"
    fi
    ;;

  *)
    echo "Usage: bash audit_entry.sh <promote|deploy|note|fill>"
    ;;
esac
```

---

### Pre-commit hook additions (appended to existing hook)

```bash
# --- AUDIT LOG: append-only enforcement ---
# Prevent any deletions from audit_log.md
if git diff --cached -- audit/audit_log.md | grep -q "^-[^-]"; then
    echo "ERROR: audit_log.md is append-only. Line deletions not permitted."
    echo "If you need to correct an entry, append a correction note instead."
    exit 1
fi

# --- AUDIT LOG: auto-generate HYPOTHESIS_PROMOTED entry ---
# Detect files moving into promoted_hypotheses/
PROMOTED=$(git diff --cached --name-only | grep "03-hypothesis/output/promoted_hypotheses/")
if [ -n "$PROMOTED" ]; then
    TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')
    HYP_ID=$(basename "$PROMOTED" .json)
    # Attempt to read PF from results.tsv — last entry for this hypothesis
    PF=$(grep "$HYP_ID" stages/03-hypothesis/autoresearch/results.tsv 2>/dev/null | tail -1 | cut -f3)
    N=$(grep "$HYP_ID" stages/03-hypothesis/autoresearch/results.tsv 2>/dev/null | tail -1 | cut -f4)
    cat >> audit/audit_log.md << EOF

## $TIMESTAMP | HYPOTHESIS_PROMOTED
- hypothesis_id: $HYP_ID
- promoted_from: 03-hypothesis/autoresearch/current_best/
- promoted_to: 03-hypothesis/output/promoted_hypotheses/
- pf_p1: ${PF:-unknown}
- n_trades_p1: ${N:-unknown}
- reason: # TODO: fill in (run: bash audit/audit_entry.sh fill)
- alternatives_considered: # TODO: fill in
- generated_by: pre-commit hook
EOF
    git add audit/audit_log.md
fi

# --- AUDIT LOG: auto-generate PERIOD_CONFIG_CHANGED entry ---
if git diff --cached --name-only | grep -q "_config/period_config.md"; then
    TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')
    BEFORE=$(git show HEAD:_config/period_config.md 2>/dev/null | grep "^|" || echo "n/a")
    AFTER=$(git diff --cached -- _config/period_config.md | grep "^+" | grep "|" | sed 's/^+//')
    REASON=$(cat "$(git rev-parse --git-dir)/COMMIT_EDITMSG" 2>/dev/null | head -1 || echo "# TODO: fill in")
    cat >> audit/audit_log.md << EOF

## $TIMESTAMP | PERIOD_CONFIG_CHANGED
- file: _config/period_config.md
- commit: $(git rev-parse --short HEAD 2>/dev/null || echo "pending")
- before: $BEFORE
- after: $AFTER
- reason: $REASON
- generated_by: pre-commit hook
EOF
    git add audit/audit_log.md
fi
```

### Post-commit hook additions (appended to existing hook)

```bash
# --- AUDIT LOG: auto-generate OOS_RUN entry ---
# Detect holdout_locked_P2.flag creation
LOCKFILE=$(git diff-tree --no-commit-id -r --name-only HEAD | grep "holdout_locked")
if [ -n "$LOCKFILE" ]; then
    TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')
    PERIOD=$(echo "$LOCKFILE" | grep -oP 'locked_\K[^.]+')
    # Read result from verdict_report.json
    VERDICT_FILE="stages/05-assessment/output/verdict_report.json"
    PF=$(python3 -c "import json; d=json.load(open('$VERDICT_FILE')); print(d.get('pf','unknown'))" 2>/dev/null || echo "unknown")
    N=$(python3 -c "import json; d=json.load(open('$VERDICT_FILE')); print(d.get('n_trades','unknown'))" 2>/dev/null || echo "unknown")
    VERDICT=$(python3 -c "import json; d=json.load(open('$VERDICT_FILE')); print(d.get('verdict','unknown'))" 2>/dev/null || echo "unknown")
    cat >> audit/audit_log.md << EOF

## $TIMESTAMP | OOS_RUN
- period: $PERIOD
- pf: $PF
- n_trades: $N
- verdict: $VERDICT
- lockfile_created: $LOCKFILE
- result_commit: $(git rev-parse --short HEAD)
- generated_by: post-commit hook
EOF
    git add audit/audit_log.md
    git commit --amend --no-edit
fi

# --- AUDIT LOG: auto-generate DEPLOYMENT_APPROVED entry ---
DEPLOYFLAG=$(git diff-tree --no-commit-id -r --name-only HEAD | grep "deployment_ready.flag")
if [ -n "$DEPLOYFLAG" ]; then
    TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')
    CPP_FILE=$(ls stages/06-deployment/output/*.cpp 2>/dev/null | head -1)
    cat >> audit/audit_log.md << EOF

## $TIMESTAMP | DEPLOYMENT_APPROVED
- output_file: ${CPP_FILE:-unknown}
- output_commit: $(git rev-parse --short HEAD)
- checklist_completed: YES
- note: # TODO: fill in (run: bash audit/audit_entry.sh fill)
- generated_by: post-commit hook
EOF
    git add audit/audit_log.md
    git commit --amend --no-edit
fi
```

---

### Lineage reconstruction

Given any deployed strategy, trace back through the full chain:

```bash
# Find all audit entries for a hypothesis
grep -A 20 "zone_touch_m1a_v3" audit/audit_log.md

# Find all OOS runs
grep "^## " audit/audit_log.md | grep "OOS_RUN"

# Find all TODO placeholders still unfilled
grep -n "# TODO" audit/audit_log.md

# Full chain for a deployment
grep -A 10 "DEPLOYMENT_APPROVED" audit/audit_log.md
# → get hypothesis_id → grep HYPOTHESIS_PROMOTED → get source run_id
# → check results.tsv in 03-hypothesis for that run_id
# → check results.tsv in 04-backtest for param optimization
# → check OOS_RUN entry for P2 verdict
```

---

## Conceptual Gaps (session 4)

Four structural gaps identified that cut across multiple stages. Each requires a documented position and/or protocol before the relevant pipeline phase is live. Ordered by urgency.

---

### Gap A: Multiple Testing / P2 Contamination Risk — CRITICAL (before first autoresearch run)

**The problem:** The three rules (P1 calibrate, P2 one-shot, entry-time only) protect P2 from being re-run. But they don't protect against P1 being exhausted by chance. If stage 03 autoresearch runs 1,000 hypothesis iterations all tested against the same P1 data, the probability that one passes purely by luck grows substantially. When that lucky hypothesis advances to P2, the P2 "validation" is meaningless — it's just another sample from the same selection process. This is the multiple comparisons problem and it is the single biggest validity threat in the pipeline.

**The current state:** `statistical_gates.md` has fixed p-value thresholds (MWU 0.05, permutation 0.05, 99th percentile) with no awareness of how many hypotheses have been tested. A hypothesis that passes at p=0.049 after 500 P1 iterations is far less credible than one that passes at p=0.049 after 5 iterations.

**Resolution — three controls to implement:**

**Control 1: Iteration budget per hypothesis family**
Define a maximum number of P1 iterations per archetype per period. Once the budget is exhausted, the archetype must either advance to P2 or be retired. Prevents indefinite P1 mining.

The full `_config/statistical_gates.md` file (spec Task 1-08):
```markdown
# Statistical Gates
last_reviewed: 2026-03-11
# These gates are enforced by Stage 05. Do not bypass.

## Baseline Verdict Thresholds
| Metric          | Yes             | Conditional        | No       |
|-----------------|-----------------|-------------------|----------|
| Profit Factor   | ≥ 2.5           | 1.5 – 2.49        | < 1.5    |
| Min trades      | ≥ 50            | 30 – 49           | < 30     |
| MWU p-value     | < 0.05          | < 0.10            | ≥ 0.10   |
| Permutation p   | < 0.05          | < 0.10            | ≥ 0.10   |
| Percentile rank | ≥ 99th          | 95th – 98th       | < 95th   |
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
| n_prior_tests for archetype | MWU p threshold            |
|-----------------------------|----------------------------|
| ≤ 10                        | < 0.05 (standard)          |
| 11 – 50                     | < 0.02 (tightened)         |
| 51 – 200                    | < 0.01 (strict)            |
| > 200                       | Do not advance — budget exhausted |

## n_prior_tests Implementation
Written by the autoresearch driver loop — NOT by a git hook.
Driver counts rows in results.tsv for the current archetype before appending each new row.
Stage 05 reads n_prior_tests from results_master.tsv when computing verdict.
```

**Control 3: Independent replication on held-out IS sub-period**
Before advancing to P2, split P1 into two halves (P1a calibrate, P1b replicate). If the strategy passes P1a but fails P1b, do not advance to P2. This adds one internal replication step that costs nothing in real OOS data.

Add to `_config/pipeline_rules.md` as Rule 4:
```markdown
Rule 4 — Internal Replication: Before any P2 run, strategy must replicate on a held-out
sub-period of IS data not used during calibration. P1a (first half) = calibration.
P1b (second half) = internal replication. Both must show positive PF before P2 is unlocked.

Grandfathering note: M1_A's existing calibration used all of P1. Its P2 result (the one-shot
OOS test already run) stands as its validation record. Rule 4 applies to new hypotheses
going forward — it does not require recalibrating M1_A.
```

**Iteration counter implementation:**
`results_master.tsv` gains a `n_prior_tests` column. The autoresearch driver loop is responsible for writing this value — it counts existing rows in `results.tsv` for the current archetype before appending a new result row. Stage 05 reads `n_prior_tests` from the TSV when computing the adjusted p-value verdict. No git hook is involved — the driver already has full visibility into experiment count at the moment it logs each result.

---

### Gap B: Live Performance Feedback Loop — HIGH (before 100 paper trade target)

**The problem:** The pipeline ends at deployment. After M1_A goes live and accumulates paper trades, that data is genuinely new OOS signal — uncontaminated, real-time, forward. But currently there's no defined path for that data to flow back into the pipeline. After 100 trades, you'll assess manually. But there's no protocol for what happens next: does the data become a new IS period? Does it inform the next hypothesis cycle? Does a live underperformance trigger a review?

**Resolution — live performance protocol:**

Add a new `07-live/` stage (monitor only — no autoresearch, no code generation):

```
07-live/
├── CONTEXT.md                    # Stage contract
├── data/
│   ├── paper_trades.csv          # Running log of all paper trades from M1B
│   └── live_trades.csv           # Future: live funded trades
├── output/
│   ├── live_assessment.md        # Periodic assessment vs backtest expectations
│   └── drift_report.md           # Is live PF tracking backtest PF?
└── triggers/
    └── review_triggers.md        # Conditions that force a pipeline review
```

**`review_triggers.md` — conditions that force human review:**
```markdown
## Live Review Triggers

Any of the following force a MANUAL_NOTE audit entry and human review:

| Trigger | Threshold | Action |
|---------|-----------|--------|
| Live PF vs backtest PF | Diverges > 40% after 50+ trades | Review hypothesis; consider retiring |
| Consecutive stop-outs | 8 or more | Pause trading; review signal filter and entry conditions |
| Max drawdown exceeded | > 2x backtest DD | Pause trading immediately |
| Trade count below expected | < 5 signals/month | Check signal detection alignment and live system config |
```

**Feedback into IS data pool:**
After a defined minimum live trade count (suggested: 200 trades, ~6 months), live data can be proposed for promotion into the IS pool via a `PERIOD_CONFIG_CHANGED` audit entry. This is a human decision — not automatic. The live period gets a `period_id` (e.g., `P_LIVE_1`) and is treated like any other IS period for feature calibration.

**Growth path update:**
- Near-term: build `07-live/` scaffold during Pass 1, start populating `paper_trades.csv` immediately
- Medium-term: after 100 trades, run first `live_assessment.md`
- Long-term: after 200+ trades, evaluate live data for IS promotion

---

### Gap C: Regime Awareness — MEDIUM (before stage 03 autoresearch is live)

**The problem:** The pipeline treats all P1 data uniformly. NQ behaves differently across regimes — trending vs ranging, low vs high volatility, pre/post macro events. M1_A's 66-trade Conditional verdict is thin enough that regime composition differences between P1 and P2 could partially explain PF variance. As the strategy library grows and hypotheses accumulate, regime-dependent edges will become harder to detect without explicit regime tags.

**This is not a blocker for initial deployment.** It becomes material when: (a) a strategy passes P1 but fails P2 and you need to understand why, or (b) the autoresearch loop starts exploring session/volatility features in stage 02 and you need regime-conditional evaluation.

**Resolution — lightweight regime tagging:**

Add `_config/regime_definitions.md`:
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
The HMM fitter discovers latent states from bar data — use these thresholds as
sanity-check references when assigning human-readable names to HMM states (e.g.
state 0 → "trending" if it predominantly covers high-ADX days). They are not
the generative algorithm.

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

**Implementation cost:** Low. Regime labels are computed once per day from existing bar data. A small Python script in `01-data/` tags each trading day. No changes to simulators, scoring, or routing.

---

### Gap D: Agent Drift / Stale Context — LOW (ongoing maintenance protocol)

**The problem:** As the pipeline evolves over months — new stages added, archetypes retired, autoresearch conventions updated — the `CLAUDE.md` and stage `CONTEXT.md` files can become stale. A stale CONTEXT.md doesn't throw an error; it quietly degrades agent output quality. The agent at stage 03 reads a description of how the pipeline works that no longer matches reality and makes subtly wrong decisions as a result.

This is the same problem documented in the CI/CD for agentic coding literature — stale context is worse than no context because it actively misdirects.

**Resolution — context review protocol:**

Add `_config/context_review_protocol.md`:
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

---

## Lost-in-the-Middle Mitigations

LLM attention degrades for content in the middle of long contexts. The ICM routing pattern
is the primary mitigation — agents at runtime read short stage files, not the full
architecture doc. These rules reinforce that.

### File length limits

| File | Hard limit | Rationale |
|------|-----------|-----------|
| CLAUDE.md | 60 lines | Global rules — short enough to be fully attended |
| stage CONTEXT.md | 80 lines | One stage's contract — no room for sprawl |
| program.md (any stage) | 30 lines | Last thing agent reads before acting — must be dense and clear |
| 02-features/references/feature_catalog.md | No limit | Reference doc, not active agent context |
| results.tsv | No limit | Structured data, not narrative context |

If a review finds any file over its limit: trim first, then run. Archive removed content
to a corresponding _history.md file (e.g., program_history.md) so nothing is lost.

### Front-loading rule
Within any file the agent reads at runtime, the operative instruction must appear in the
first 5 lines. Structure is always: WHAT TO DO → constraints → metric → rationale.
Never bury the constraint at the end.

Good:
  "Only modify exit_params.json. Metric: PF@3t on P1. Min 30 trades.
   Do not touch backtest_engine.py under any circumstances.
   [rationale and context follow]"

Bad:
  "[3 paragraphs of context and history]
   [paragraph about the strategy]
   Only modify exit_params.json."

### Local repetition rule
Each stage CONTEXT.md must restate the constraints critical to that stage directly —
do not rely on the agent cross-referencing CLAUDE.md or pipeline_rules.md from memory.
Example: the 04-backtest CONTEXT.md must say "Do not edit backtest_engine.py" even
though it is also in CLAUDE.md. Redundancy is intentional here.

### Persistent state vs working memory
The agent does not need to hold experiment history in context — that is what results.tsv
is for. The driver loop reads the TSV fresh each iteration. program.md should never
accumulate a log of past experiments; that belongs in results.tsv or program_history.md.
```

**Pre-commit hook addition:**
```bash
# Warn on period rollover to review CONTEXT.md files
if git diff --cached --name-only | grep -q "_config/period_config.md"; then
    echo "REMINDER: Period rollover detected."
    echo "Review all stage CONTEXT.md files per _config/context_review_protocol.md"
    echo "before running next autoresearch cycle."
fi
```

---

## Open Items Before Build

### Gaps — STATUS

**Gap A — Multiple testing controls: CLOSED**
- `n_prior_tests` column in results_master.tsv (24-col schema) ✓
- Bonferroni-adjusted thresholds in `statistical_gates.md` ✓
- Rule 4 (P1a/P1b internal replication) in `pipeline_rules.md` ✓ — enforced in `hypothesis_generator.py`, gate softness controlled by replication_gate in period_config.md
- Grandfathering note for M1_A (calibrated before Rule 4) ✓

**Gap B — Live performance feedback loop: CLOSED (scaffolded)**
- `07-live/` stage in spec ✓
- `review_triggers.md` defined ✓
- M1_A paper trading active, `paper_trades.csv` being populated ✓

**Gap C — Regime awareness: CLOSED**
- `_config/regime_definitions.md` specified ✓
- HMM regime fitter assigned to Stage 01 (Task 1-09b) ✓
- Regime breakdown in Stage 05 statistical_summary.md (n≥20 per bucket) ✓

**Gap D — Agent drift / stale context: CLOSED**
- `_config/context_review_protocol.md` specified ✓
- `last_reviewed` + `reviewed_by` front-matter on all CONTEXT.md files ✓
- Pre-commit hook CONTEXT.md review reminder on period_config.md changes ✓
- Line caps and front-loading rule documented ✓

**Gap 2 — Clarifying questions: CLOSED (Q1–Q6 all answered)**
- Q1: backtest_engine takes explicit period paths from config (data_manifest.json not read directly by engine)
- Q2: Scoring model bin edges frozen from P1 — static, not recomputed at runtime
- Q3: TrailStep = {trigger_ticks, new_stop_ticks}; BE = trail_steps[0] with new_stop_ticks=0; trail_steps are optimizable (1–6 steps)
- Q4: M1-only flag — backtest_engine runs the simulator_module named in config.archetype (Option B dynamic dispatch); no waterfall during autoresearch
- Q5: Holdout guard lives in backtest_engine.py at engine level (not just runner script) — aborts if holdout_locked_P2.flag + P2 paths detected
- Q6: Per-mode breakdown required in output JSON — top-level PF drives keep/revert, per-mode is diagnostic

**Gap 3 — RinDig ICM repo conventions: OPEN**
- Needed before writing CONTEXT.md files
- Not a blocker for Pass 1 Python infrastructure
- Fetch when reaching CONTEXT.md authoring step in Pass 1

**Q7 — Multi-period IS calibration: OPEN**
- Combined pool or separate folds when P1+P2 both IS?
- Decide before P3 arrives (~Jun 2026). No action needed now.

---

### Build Sequence

**Now (Pass 1 + Pass 1.5 — ready to start):**
- Full folder structure at `futures-pipeline/`
- `CLAUDE.md` — five rules, CONVENTIONS block, hard prohibitions (Gap 3 note: draft now, refine after RinDig fetch)
- `_config/` files: instruments.md (NQ/ES/GC), data_registry.md, period_config.md, statistical_gates.md (Bonferroni thresholds + budgets), pipeline_rules.md (five rules + grandfathering), regime_definitions.md, context_review_protocol.md
- `shared/feature_definitions.md`, `02-features/references/feature_catalog.md` (seed with known features + dead ends), `shared/scoring_models/scoring_adapter.py` (BinnedScoringAdapter + factory)
- `shared/archetypes/zone_touch/` — simulation_rules.md, exit_templates.md (from existing M1_A behaviour)
- `shared/scoring_models/zone_touch_variant_a.json` (Variant A weights)
- `dashboard/results_master.tsv` schema (24 cols), `dashboard/index.html` stub
- `audit/audit_log.md` stub + `audit/audit_entry.sh`
- `autocommit.sh`, `pre-commit` hook, `post-commit` hook (Pass 1.5)
- Stage CONTEXT.md files for all 7 stages (after Gap 3 fetch)

**Next (Pass 2 — backtest engine):**
- `04-backtest/references/backtest_engine_qa.md` — commit Q1–Q6 answers first
- `04-backtest/autoresearch/backtest_engine.py` — Option B dynamic dispatch
- `shared/archetypes/zone_touch/feature_engine.py` + `simulation_rules.md`
- Determinism verification, config_schema.json, config_schema.md
- Manual end-to-end pass (Stage 01 → 04 → 05) before adding autoresearch
- Note: feature_evaluator.py written in Pass 3 alongside evaluate_features.py dispatcher

**After Pass 2 (Pass 3 — autoresearch loops):**
- Stage 04 driver first → overnight test → Stage 02 → Stage 03
- Do not build 02 or 03 until Stage 04 overnight test passes cleanly
