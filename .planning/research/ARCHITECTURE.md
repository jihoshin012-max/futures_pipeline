# Architecture Research

**Domain:** Futures trading strategy research pipeline (NQ E-mini NASDAQ-100)
**Researched:** 2026-03-13
**Confidence:** HIGH — drawn directly from authoritative project specs (Futures_Pipeline_Architecture_ICM.md v2026-03-13, Futures_Pipeline_Functional_Spec.md v1.0)

---

## Standard Architecture

### System Overview

```
┌─────────────────────────────────────────────────────────────────────────┐
│  LAYER 0 — AGENT IDENTITY                                               │
│  CLAUDE.md (≤60 lines, five rules in first 20, hard prohibitions)       │
├─────────────────────────────────────────────────────────────────────────┤
│  LAYER 1 — ROUTING                                                      │
│  CONTEXT.md (root) → routes agent to current active stage               │
├─────────────────────────────────────────────────────────────────────────┤
│  LAYER 2 — FACTORY SETTINGS (configure once)                            │
│  _config/                                                               │
│  ┌──────────────┐ ┌────────────────┐ ┌──────────────┐ ┌─────────────┐  │
│  │instruments.md│ │period_config.md│ │data_registry │ │stat_gates.md│  │
│  └──────────────┘ └────────────────┘ └──────────────┘ └─────────────┘  │
│  ┌──────────────┐ ┌────────────────┐ ┌────────────────────────────────┐ │
│  │pipeline_rules│ │regime_defn.md  │ │context_review_protocol.md      │ │
│  └──────────────┘ └────────────────┘ └────────────────────────────────┘ │
├─────────────────────────────────────────────────────────────────────────┤
│  LAYER 3 — SHARED CROSS-STAGE RESOURCES                                 │
│  shared/                                                                │
│  ┌───────────────────────┐  ┌─────────────────────────────────────────┐ │
│  │ feature_definitions.md│  │ scoring_models/                         │ │
│  │ (entry-time rule here)│  │ scoring_adapter.py (BinnedScoring,      │ │
│  └───────────────────────┘  │ Sklearn, ONNX adapters)                 │ │
│                             │ zone_touch_variant_a.json (frozen)      │ │
│                             │ hmm_regime_v1.pkl (frozen, P1 fit only) │ │
│                             └─────────────────────────────────────────┘ │
│  ┌─────────────────────────────────────────────────────────────────────┐│
│  │ archetypes/zone_touch/                                              ││
│  │ feature_engine.py (agent edits) | feature_evaluator.py (fixed)     ││
│  │ simulation_rules.md | exit_templates.md                            ││
│  └─────────────────────────────────────────────────────────────────────┘│
├─────────────────────────────────────────────────────────────────────────┤
│  LAYER 4 — 7-STAGE RESEARCH PIPELINE                                    │
│  ┌────────┐  ┌────────┐  ┌────────┐  ┌────────┐                        │
│  │01-data │→ │02-feat │→ │03-hyp  │→ │04-back │                        │
│  │(manual)│  │(auto)  │  │(auto)  │  │(auto)  │                        │
│  └────────┘  └────────┘  └────────┘  └────┬───┘                        │
│                                           │                             │
│  ┌────────┐  ┌────────┐  ┌────────┐       │                             │
│  │07-live │← │06-deplo│← │05-assmt│←──────┘                            │
│  │(monitor│  │(manual)│  │(determ)│  feedback→03 prior_results.md      │
│  └────────┘  └────────┘  └────────┘                                    │
├─────────────────────────────────────────────────────────────────────────┤
│  LAYER 5 — INFRASTRUCTURE                                               │
│  ┌──────────────────────┐  ┌───────────────────────────────────────────┐│
│  │ audit/audit_log.md   │  │ dashboard/results_master.tsv (24-col TSV) ││
│  │ (append-only, never  │  │ dashboard/index.html (stub, M2)           ││
│  │  modified or deleted)│  └───────────────────────────────────────────┘│
│  └──────────────────────┘                                               │
│  ┌──────────────────────────────────────────────────────────────────────┐│
│  │ .git/hooks: pre-commit (holdout guard, audit entries, period warn)  ││
│  │ .git/hooks: post-commit (commit log, OOS_RUN, DEPLOYMENT_APPROVED)  ││
│  │ autocommit.sh (30s watcher — preserves full experiment trail)       ││
│  └──────────────────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────────────┘
```

### Component Responsibilities

| Component | Responsibility | Communicates With |
|-----------|----------------|-------------------|
| CLAUDE.md | Agent identity, five rules, hard prohibitions | Read by agent at every stage entry |
| root CONTEXT.md | Routes agent to current active stage | Points to stage CONTEXT.md + program.md |
| _config/ | Global constants — never changes mid-run | Read by all stages; period_config.md → Stage 01 → data_manifest.json |
| Stage 01 data | Validate raw data, produce data_manifest.json, fit HMM regime model | Consumed by all downstream stages |
| Stage 02 features | Autoresearch: discover entry-time computable features | Reads data_manifest.json; writes frozen_features.json to Stage 03 |
| Stage 03 hypothesis | Autoresearch: explore strategy configurations on P1 IS data | Reads frozen_features.json; reads prior_results.md from Stage 05 |
| Stage 04 backtest | Autoresearch: optimize exit params; holds P2 one-shot | Reads promoted_hypothesis.json; writes frozen_params.json; enforces holdout flag |
| Stage 05 assessment | Deterministic statistical verdict; no exploration | Reads trade_log.csv from Stage 04; writes feedback to Stage 03 via prior_results.md |
| Stage 06 deployment | Assemble context package, generate Sierra Chart ACSIL | Reads frozen_params.json; requires human approval gate |
| Stage 07 live | Monitor paper/funded trades vs backtest expectations; detect drift | Reads live trade data; triggers human review at thresholds |
| shared/archetypes/ | Per-archetype Python modules (feature_engine, simulator, evaluator) | Used by Stage 02 evaluator, Stage 04 backtest engine |
| shared/scoring_models/ | Frozen scoring configs + adapter interface | Used by Stage 04 backtest_engine.py via adapter pattern |
| audit/audit_log.md | Append-only decision log: promotions, P2 runs, deployments, anomalies | Written by hooks and audit_entry.sh; never modified |
| dashboard/results_master.tsv | 24-col experiment ledger across all stages and runs | Written by Stage 05 assessment; read by dashboard index.html |
| autocommit.sh + git hooks | Full experiment trail preservation; holdout integrity enforcement | Fires on file changes / git operations |

---

## Recommended Project Structure

```
futures-pipeline/
├── CLAUDE.md                              # Agent identity, ≤60 lines
├── CONTEXT.md                             # Router to active stage
│
├── _config/                               # Factory settings — configure once
│   ├── instruments.md                     # NQ/ES/GC tick sizes, costs, session times
│   ├── data_registry.md                   # Data sources: type, period, file pattern, consumers
│   ├── period_config.md                   # IS/OOS boundaries — single source of truth
│   ├── statistical_gates.md               # PF thresholds, p-value gates, iteration budgets
│   ├── pipeline_rules.md                  # Five rules (P1 calibrate, P2 one-shot, entry-time, replication, registry)
│   ├── regime_definitions.md              # Regime taxonomy (trend, vol, macro dimensions)
│   └── context_review_protocol.md         # File length limits, front-loading rule, staleness thresholds
│
├── shared/                                # Cross-stage resources
│   ├── feature_definitions.md             # All approved features: source, formula, bin_edges, entry-time flag
│   ├── archetypes/
│   │   └── zone_touch/                    # One folder per archetype
│   │       ├── feature_engine.py          # Stage 02 AGENT EDITS THIS
│   │       ├── feature_evaluator.py       # Fixed evaluation harness (never agent-edited)
│   │       ├── simulation_rules.md        # Entry/exit mechanics, cost_ticks from instruments.md
│   │       └── exit_templates.md          # Exit structure patterns for Stage 04 agent
│   └── scoring_models/
│       ├── scoring_adapter.py             # BinnedScoringAdapter | SklearnAdapter | ONNXAdapter
│       ├── _template.json                 # Schema for new scoring models
│       ├── zone_touch_variant_a.json      # Frozen weights + bin_edges for current archetype
│       └── hmm_regime_v1.pkl              # Frozen HMM model (fit on P1 only)
│
├── stages/
│   ├── 01-data/
│   │   ├── CONTEXT.md                     # Stage contract (≤80 lines)
│   │   ├── hmm_regime_fitter.py           # Fit on P1, apply frozen model to P2
│   │   ├── references/                    # Schema files per source_id + bar_data_schema.md
│   │   ├── data/
│   │   │   ├── touches/                   # Touch/signal CSVs (P1, P2, future periods)
│   │   │   ├── bar_data/                  # NQ 1-min OHLCV bars
│   │   │   └── labels/                    # SBB labels + regime_labels.csv
│   │   └── output/
│   │       ├── data_manifest.json         # What's available, period boundaries, row counts
│   │       └── validation_report.md       # Schema checks, coverage, bar offset
│   │
│   ├── 02-features/
│   │   ├── CONTEXT.md
│   │   ├── references/
│   │   │   ├── feature_rules.md           # Entry-time rule, registered sources only, keep threshold
│   │   │   └── feature_catalog.md         # Full exploration history (no line limit — reference only)
│   │   ├── autoresearch/
│   │   │   ├── program.md                 # Human steering (≤30 lines)
│   │   │   ├── evaluate_features.py       # Fixed dispatcher → calls archetype feature_evaluator.py
│   │   │   ├── results.tsv                # feature | spread | mwu_p | kept/reverted
│   │   │   └── current_best/
│   │   └── output/
│   │       ├── frozen_features.json       # Human-approved feature set
│   │       └── feature_report.md
│   │
│   ├── 03-hypothesis/
│   │   ├── CONTEXT.md
│   │   ├── references/
│   │   │   ├── prior_results.md           # Auto-fed from Stage 05: what passed/failed
│   │   │   ├── strategy_archetypes.md     # Registered archetypes with simulator + scoring paths
│   │   │   └── frozen_features.json       # From Stage 02 output
│   │   ├── autoresearch/
│   │   │   ├── program.md                 # Human steering (≤30 lines)
│   │   │   ├── hypothesis_config.json     # AGENT EDITS THIS — one strategy config per experiment
│   │   │   ├── hypothesis_generator.py    # Fixed harness: runs backtest+assess, enforces Rule 4
│   │   │   ├── results.tsv                # hypothesis | PF | replication_pass | verdict
│   │   │   └── current_best/
│   │   └── output/
│   │       ├── promoted_hypotheses/       # Human-approved configs to advance
│   │       └── hypothesis_report.md
│   │
│   ├── 04-backtest/
│   │   ├── CONTEXT.md
│   │   ├── references/
│   │   │   ├── promoted_hypothesis.json   # From Stage 03 output
│   │   │   └── backtest_engine_qa.md      # Q1–Q6 answered before engine written
│   │   ├── autoresearch/
│   │   │   ├── program.md                 # Human steering (≤30 lines)
│   │   │   ├── backtest_engine.py         # Fixed engine — AGENT NEVER EDITS (hard prohibition)
│   │   │   ├── exit_params.json           # AGENT EDITS THIS — exit config per experiment
│   │   │   ├── results.tsv                # stop | targets | PF | win_rate | n_trades | verdict
│   │   │   └── current_best/
│   │   ├── output/
│   │   │   ├── frozen_params.json         # Human-approved exit parameters
│   │   │   ├── trade_log.csv              # Per-trade: entry, exit, PnL, exit_reason
│   │   │   └── equity_curve.csv
│   │   └── p2_holdout/                    # ONE-SHOT — enforced at engine level + pre-commit hook
│   │       ├── holdout_locked_P2.flag     # Presence = P2 already tested, abort if detected
│   │       ├── trade_log_p2.csv
│   │       └── equity_curve_p2.csv
│   │
│   ├── 05-assessment/
│   │   ├── CONTEXT.md
│   │   ├── references/
│   │   │   ├── verdict_criteria.md        # Yes/Conditional/No gate definitions
│   │   │   └── statistical_tests.md       # MWU, permutation, percentile specs
│   │   └── output/
│   │       ├── verdict_report.md          # Full verdict with justification
│   │       ├── verdict_report.json        # Machine-readable (dashboard)
│   │       ├── statistical_summary.md     # Sharpe, DD, MWU, perm, regime breakdown
│   │       └── feedback_to_hypothesis.md  # Auto-copied to Stage 03 prior_results.md
│   │
│   ├── 06-deployment/
│   │   ├── CONTEXT.md
│   │   ├── assemble_context.sh            # Assembles context package for ACSIL generation
│   │   ├── references/
│   │   │   ├── M1B_AutoTrader.cpp         # Structural reference (never modified)
│   │   │   ├── context_package_spec.md    # Information contract for code generation
│   │   │   └── alignment_test.py          # ZB4 vs ZRA comparison — run before deployment
│   │   └── output/
│   │       ├── {strategy_id}/             # One folder per deployed strategy
│   │       └── deployment_ready.flag      # Human-created only, after all checks pass
│   │
│   └── 07-live/
│       ├── CONTEXT.md
│       ├── data/
│       │   ├── paper_trades.csv           # Running log from M1B_AutoTrader (manual export)
│       │   └── live_trades.csv            # Future: funded trades
│       ├── output/
│       │   ├── live_assessment.md         # Periodic comparison vs backtest expectations
│       │   └── drift_report.md            # Rolling PF vs backtest PF
│       └── triggers/
│           └── review_triggers.md         # Thresholds that force human pipeline review
│
├── dashboard/
│   ├── results_master.tsv                 # 24-col experiment ledger (all stages, all runs)
│   └── index.html                         # Filterable view — deferred to Milestone 2
│
├── audit/
│   ├── audit_log.md                       # Append-only: OOS_RUN, HYPOTHESIS_PROMOTED, etc.
│   └── audit_entry.sh                     # CLI for human-initiated entries
│
├── autocommit.sh                          # 30s watcher → auto-commit changed files
└── archive/                               # Completed runs, version history
    └── run_YYYY-MM-DD_{hypothesis}/
```

### Structure Rationale

- **_config/:** Global constants separated so that rolling forward to a new period (P3) requires editing only `period_config.md` — no code changes anywhere else. Stages that consume these read from `data_manifest.json` (Stage 01 output), which is regenerated automatically.
- **shared/archetypes/:** Each archetype owns its Python modules (feature_engine, feature_evaluator, simulator). Adding a new strategy = add a new subfolder. Stages 04 and 05 never change shape — only their inputs change. This is the extensibility contract.
- **shared/scoring_models/:** Scoring models frozen at calibration time. Adapter pattern (BinnedScoringAdapter / SklearnAdapter / ONNXAdapter) means backtest_engine.py never touches model internals — model format can change without engine changes.
- **stages/{N}/autoresearch/:** Each autoresearch stage has three key files: `program.md` (human steering, ≤30 lines), the one file the agent edits (feature_engine.py / hypothesis_config.json / exit_params.json), and the fixed harness (evaluate_features.py / hypothesis_generator.py / backtest_engine.py). The agent only touches the middle file.
- **stages/04-backtest/p2_holdout/:** Physical isolation of P2 outputs with a `holdout_locked_P2.flag` that both the engine and pre-commit hook check. Two independent enforcement points means holdout discipline does not depend on any human remembering.
- **audit/:** Separate from stages — append-only log captures decisions that git history and results TSVs cannot: why a hypothesis was promoted, full chain from experiment to deployment, period boundary changes.

---

## Architectural Patterns

### Pattern 1: Karpathy Keep/Revert Autoresearch Loop

**What:** Agent edits one file per experiment, runs fixed harness, compares metric to prior best, keeps if improved, reverts if not, appends to TSV, repeats overnight.
**When to use:** Any stage where autonomous exploration is desired (02-features, 03-hypothesis, 04-backtest). Not used in deterministic stages (01, 05, 06, 07).
**Trade-offs:** Maximizes overnight experiment throughput with full reversibility. Requires clear metric definition and improvement threshold. Budget enforcement (iteration limits) prevents p-hacking.

**Three-file pattern per autoresearch stage:**
```
program.md          ← human steering doc (≤30 lines, updated each evening)
{one_editable_file} ← the only file agent modifies per experiment
{fixed_harness}.py  ← never modified by agent; runs evaluation; returns metric
```

**Mapping across stages:**
```
Stage 02: feature_engine.py (edit) | evaluate_features.py (fixed)  | metric: spread > 0.15 + MWU p < 0.10
Stage 03: hypothesis_config.json   | hypothesis_generator.py (fixed)| metric: P1 PF@3t (budget 200)
Stage 04: exit_params.json         | backtest_engine.py (fixed)     | metric: P1 PF@3t > prior + 0.05 (budget 500)
```

### Pattern 2: ICM Stage Contracts

**What:** Every stage has a CONTEXT.md with Inputs / Process / Outputs tables, operative instruction in first 5 lines, ≤80 lines total. Agent reads CONTEXT.md before acting and does not load data or files outside its stage contract.
**When to use:** All 7 stages. This is the core lost-in-middle mitigation — layered context loading prevents the agent from conflating stage responsibilities.
**Trade-offs:** Requires discipline during authoring (file length limits are hard constraints, not guidelines). Local repetition of constraints in each CONTEXT.md is intentional redundancy — not DRY — because agent cannot be trusted to remember constraints from a different file.

```
File limits (hard — trim before run if over):
  CLAUDE.md:        ≤60 lines
  stage CONTEXT.md: ≤80 lines
  program.md:       ≤30 lines
  results.tsv:      no limit (structured data)
  feature_catalog:  no limit (reference doc, not runtime)
```

### Pattern 3: Dynamic Dispatch via Config (Option B)

**What:** `backtest_engine.py` loads the simulator module at runtime from `config.archetype.simulator_module` (a string path). New archetype = drop in new simulator file. Engine never changes.
**When to use:** Any time a new strategy archetype is added. The engine calls `simulator.run(bar_df, touch_row, config, bar_offset)` — every simulator must implement this exact interface.
**Trade-offs:** Pure functions only (no I/O, no global state). Returns `SimResult` dataclass. If a simulator breaks the interface contract, the engine fails at load time, not mid-run.

```python
# backtest_engine.py call sequence (simplified)
check_holdout_flag(config)                         # abort if P2 paths + flag exists
data = load_data(config.touches_csv, config.bar_data)
adapter = load_scoring_adapter(config.scoring_model_path, config.archetype.scoring_adapter)
data["score"] = adapter.score(data)                # single call regardless of model format
simulator = load_simulator(config.archetype.simulator_module)  # dynamic dispatch
for touch in route_waterfall(data, config.routing):
    result = simulator.run(bars, touch, mode_config, bar_offset)
write_result_json(results)                         # top-level PF + per-mode breakdown
```

### Pattern 4: IS/OOS Strict Separation

**What:** All IS/OOS boundaries defined in exactly one file (`_config/period_config.md`). Stage 01 reads it once, writes period table into `data_manifest.json`. All downstream stages read from the manifest. P2 holdout enforced at three independent levels: `holdout_locked_P2.flag` presence, pre-commit hook, and engine-level abort. Rolling to a new period = edit `period_config.md`, re-run Stage 01. No code changes.
**When to use:** Every experiment and every period-scoped data access.
**Trade-offs:** Three-layer enforcement is redundant by design. Any single layer failing is caught by the others. The flag is the most robust: it is a filesystem artifact that survives crashes, hook failures, and agent misbehavior.

### Pattern 5: Frozen Model + Adapter Interface

**What:** Scoring models (bin_edges + weights) are frozen at calibration time. The adapter interface (`score(touch_df) → pd.Series`) is the only API the engine calls. Engine never reads bin_edges directly. Adding a new model format = write a new adapter class, no engine changes.
**When to use:** Every backtest run, both IS and OOS. The same frozen model handles both periods (never refit on P2 data).
**Trade-offs:** Prevents accidental data leakage from OOS periods into scoring model weights. The HMM regime model follows the same pattern: fit on P1, serialize, apply frozen model to P2.

---

## Data Flow

### Primary Research Flow (IS data)

```
raw files (touches CSV, bar data)
    ↓ Stage 01: validate, register, fit HMM
data_manifest.json + regime_labels.csv + hmm_regime_v1.pkl
    ↓ Stage 02 autoresearch (≤300 experiments on P1)
frozen_features.json (human-approved)
    ↓ Stage 03 autoresearch (≤200 experiments on P1)
promoted_hypotheses/ (human-approved)
    ↓ Stage 04 autoresearch (≤500 experiments on P1)
frozen_params.json (human-approved)
    ↓ Stage 05 assessment (deterministic)
verdict_report.json + feedback_to_hypothesis.md
    ↓ (if passed) Stage 04 P2 holdout (exactly once)
trade_log_p2.csv + holdout_locked_P2.flag
    ↓ Stage 05 assessment (P2 verdict)
verdict_report_P2.json
    ↓ (if approved) Stage 06 deployment
{strategy_id}/ ACSIL code + deployment_ready.flag (human-created)
    ↓ Stage 07 live monitoring
live_assessment.md + drift_report.md
```

### Feedback Loop (Stage 05 → Stage 03)

```
05-assessment/output/feedback_to_hypothesis.md
    ↓ (auto-copied by driver)
03-hypothesis/references/prior_results.md
    ↓ (read by agent before each experiment)
avoids repeating known failures in next overnight run
```

### Audit Trail (parallel, non-blocking)

```
every file change → autocommit.sh (30s poll) → git auto-commit
every P2 run → post-commit hook → OOS_RUN entry in audit_log.md
every deployment approval → post-commit hook → DEPLOYMENT_APPROVED entry
every promotion → pre-commit hook → HYPOTHESIS_PROMOTED entry
every period config change → pre-commit hook → PERIOD_CONFIG_CHANGED entry
human decisions → audit_entry.sh → MANUAL_NOTE entry
```

### Key Data Flows

1. **period_config.md → data_manifest.json:** Stage 01 is the only consumer of period_config.md at runtime. It resolves periods and writes the manifest. Downstream stages read only the manifest — period_config.md becomes a human-controlled contract.
2. **data_manifest.json → backtest_engine.py:** Engine takes explicit file paths via config JSON (not period-aware). Caller resolves period to path using manifest; engine is period-agnostic (Q1 answer).
3. **scoring model (frozen) → BinnedScoringAdapter → engine:** Engine calls `adapter.score()` — never touches bin_edges or weights. Freezing happens once at calibration. P1 and P2 runs use identical model state.
4. **results.tsv → driver loop (each iteration):** Driver reads TSV fresh each experiment to count n_prior_tests and identify current best. Agent has no persistent memory — the TSV is the state.
5. **frozen_params.json → Stage 06 assemble_context.sh:** All exit parameters, scoring model path, archetype, instrument constants assembled into a context package. Claude Code generates ACSIL from this package.

---

## Build Order

The project spec defines three sequential passes. Order is strict — each pass creates prerequisites for the next.

### Pass 1 — Scaffold (no Python code required)

**Deliverables:** Full folder structure, CLAUDE.md, root CONTEXT.md, all _config/ files, all 7 stage CONTEXT.md files, shared/ files (feature_definitions, scoring_models dir + adapter, archetypes/ with exit_templates.md), hmm_regime_fitter.py + initial regime_labels.csv, data migration, audit stub.

**Why first:** Everything downstream depends on the config layer and stage contracts existing. The HMM fitter is mandatory Pass 1 (not deferred) because regime breakdown enriches Stage 05 from the first assessment onward.

**Dependencies within Pass 1:**
```
instruments.md → data_registry.md → period_config.md → Stage 01 CONTEXT.md
period_config.md → hmm_regime_fitter.py (must know P1 date bounds)
strategy_archetypes.md → exit_templates.md (archetype must be registered before templates)
data migration → Stage 01 validation (can't validate what isn't there)
```

### Pass 1.5 — Git Infrastructure (parallel with Pass 1)

**Deliverables:** autocommit.sh, pre-commit hook (holdout guard + audit entries + period rollover warning), post-commit hook (commit log + OOS_RUN + DEPLOYMENT_APPROVED).

**Why this order:** Git hooks must be running before any autoresearch loop touches files. Overnight runs produce 100+ auto-commits — the hooks must be verified before the first overnight run.

**Critical verification:** `chmod +x` both hooks. Make a file change, wait 30s, confirm auto-commit in `git log`. The holdout guard must be tested with a simulated P2 path commit attempt.

### Pass 2 — Backtest Engine (blocked on Q1–Q6, already answered)

**Deliverables:** backtest_engine_qa.md (Q1–Q6 committed first), data_loader.py patched (5 hardcoded paths parameterized), backtest_engine.py (~175–225 lines), config_schema.json, config_schema.md, determinism verified, manual end-to-end pass (01→04→05), simulation_rules.md.

**Why this order:** Engine must be manually validated (identical config → identical output) before any autoresearch loop runs against it. The manual end-to-end pass is a gate — do not start Pass 3 before it completes.

**Build order within Pass 2:**
```
backtest_engine_qa.md committed (commit before writing engine code — audit artifact)
    ↓
data_loader.py patched (~15 min change)
    ↓
backtest_engine.py written (Q1–Q6 spec already complete, see architecture doc)
    ↓
config_schema.json + config_schema.md
    ↓
determinism verification (diff two identical-config runs)
    ↓
manual end-to-end pass (01 → 04 → 05) — GATE before Pass 3
```

### Pass 3 — Autoresearch Loops (lowest risk first)

**Deliverables:** Stage 04 driver + overnight test, evaluate_features.py dispatcher + Stage 02 driver + overnight test, hypothesis_generator.py + Stage 03 driver + overnight test, feedback loop wired.

**Build order within Pass 3:**
```
Stage 04 (param optimization) first — lowest risk, most constrained search space
    ↓ overnight test confirms keep/revert logic, TSV output, budget enforcement
Stage 02 (feature engineering) second — requires feature_evaluator.py
    ↓ overnight test confirms spread computation, entry-time enforcement
Stage 03 (hypothesis iteration) last — depends on both feature set and backtest working
    ↓ feedback loop: wire Stage 05 → prior_results.md → Stage 03 at this point
```

**Why this order:** Stage 04 is built first because its search space is the most tightly constrained (exit params only, budget 500) and the backtest engine is already verified from Pass 2. Stage 02 and 03 have broader search spaces and introduce more failure modes. Running them before Stage 04 is verified creates debugging ambiguity.

---

## Anti-Patterns

### Anti-Pattern 1: Period Leakage via Hardcoded Paths

**What people do:** Write `data_loader.py` with module-level path constants like `TOUCHES_CSV = "data/touches/NQ_P1.csv"`.
**Why it's wrong:** Any script calling the module implicitly runs against that specific period. When rolling forward to P3, every file with hardcoded paths must be hunted down. The P2 holdout guard cannot detect period through hardcoded paths — only through the paths actually passed to the engine.
**Do this instead:** Pass all file paths explicitly through function arguments. Caller resolves period to path using data_manifest.json. Engine is period-agnostic.

### Anti-Pattern 2: Fat CONTEXT.md

**What people do:** Write verbose CONTEXT.md files that explain background, history, rationale, prior attempts.
**Why it's wrong:** Violates the ≤80 line limit. More critically, operative instructions get buried — agent reads first 5 lines, then context drops off as prompt grows. A 200-line CONTEXT.md is worse than no CONTEXT.md because it creates false confidence that the agent has been well-instructed.
**Do this instead:** Operative instruction in first 5 lines. Constraints directly below. Cut anything that is not: what to do, what metric, what not to touch, what triggers human review. Archive excess to context_history.md.

### Anti-Pattern 3: Modifying backtest_engine.py During Autoresearch

**What people do:** "Just a small fix" edit to backtest_engine.py while an autoresearch loop is running or has been running against it.
**Why it's wrong:** Changes the evaluation function mid-run. All prior results.tsv entries are now from a different harness. PF comparisons are invalid — the keep/revert logic is comparing results from two different evaluation environments.
**Do this instead:** Treat backtest_engine.py as immutable once autoresearch starts. If a fix is needed: stop the loop, commit the fix with a `manual:` prefix, archive existing results.tsv to current_best/, reset the loop, start fresh.

### Anti-Pattern 4: Running OOS (P2) More Than Once

**What people do:** Run P2, get a borderline result, tweak one parameter "just slightly," run P2 again.
**Why it's wrong:** Multiple P2 runs is p-hacking against the holdout. The first run is the valid test. Every subsequent run inflates the false positive rate. A pipeline with OOS discipline that allows re-runs has no statistical validity.
**Do this instead:** The holdout_locked_P2.flag (plus engine-level abort, plus pre-commit hook) makes re-runs structurally impossible. If you find yourself trying to work around these guards, stop and do the correct thing: advance to P3 when it arrives, or retire the archetype.

### Anti-Pattern 5: Running Stage 02/03/04 Autoresearch Loops in Parallel

**What people do:** Run feature exploration and hypothesis search simultaneously to save time.
**Why it's wrong:** Stage 02 outputs (frozen_features.json) are inputs to Stage 03. Running them in parallel creates a moving target: the hypothesis generator is running against an unstable feature set. Improvements cannot be attributed. Budget counters are inconsistent.
**Do this instead:** Sequential in order: 02 → 03 → 04. Each pass is gated by human review of results.tsv before proceeding.

### Anti-Pattern 6: Scoring Model Recalibration on P2 Data

**What people do:** After seeing P2 results, "tune" the bin_edges or weights in the scoring model.
**Why it's wrong:** Any adjustment to the scoring model after seeing P2 results contaminates the OOS test. The bin_edges must be frozen at P1 calibration time. The frozen_date field in the scoring model JSON is the evidence that this was done correctly.
**Do this instead:** Freeze the scoring model (with frozen_date) before Stage 04 autoresearch begins. The model is immutable after that point. If a new scoring approach is needed, it applies to the next archetype iteration, calibrated on whatever IS data is available at that future time.

---

## Integration Points

### External Services

| Service | Integration Pattern | Notes |
|---------|---------------------|-------|
| Sierra Chart | Manual: assemble_context.sh generates context package, Claude Code writes ACSIL, human compiles + verifies | No automated API. deployment_ready.flag is human-created |
| Git | autocommit.sh polls for changes every 30s; pre/post-commit hooks fire on git operations | Hooks must be chmod +x and verified before first overnight run |

### Internal Boundaries

| Boundary | Communication | Notes |
|----------|---------------|-------|
| _config/ → stages | All stages read from data_manifest.json (Stage 01 output), never from _config/ directly at runtime | period_config.md is the one exception: Stage 01 reads it to generate the manifest |
| Stage 02 → Stage 03 | frozen_features.json file (human review gate between stages) | Agent at Stage 03 reads frozen_features.json from Stage 02 output |
| Stage 03 → Stage 04 | promoted_hypothesis.json file (human review gate) | Agent at Stage 04 reads from Stage 03 promoted_hypotheses/ folder |
| Stage 04 → Stage 05 | trade_log.csv + equity_curve.csv | Assessment reads trade-level detail to compute all metrics |
| Stage 05 → Stage 03 | feedback_to_hypothesis.md auto-copied to prior_results.md | Closes the research loop: failures inform next hypothesis cycle |
| Stage 04 → Stage 06 | frozen_params.json + trade_log_p2.csv (human review gate) | Deployment requires human approval; deployment_ready.flag human-created |
| shared/archetypes/ ↔ Stage 02 | evaluate_features.py dispatcher calls archetype's feature_evaluator.py | Dispatcher is fixed harness; evaluator is archetype-specific |
| shared/archetypes/ ↔ Stage 04 | backtest_engine.py loads simulator via dynamic dispatch (config.archetype.simulator_module) | Pure function interface — simulator never has I/O or side effects |
| audit_log.md ↔ all stages | Append-only writes from hooks and audit_entry.sh | Never read by agents at runtime — only human + dashboard consumers |

---

## Scaling Considerations

This is a single-researcher pipeline, not a user-scaling problem. "Scale" here means expanding the research surface.

| Dimension | Current (v1) | Near-term | Long-term |
|-----------|-------------|-----------|-----------|
| Instruments | NQ only | Add ES, GC (instruments.md + data_registry row + data migration) | Any CME futures |
| Archetypes | zone_touch only | Mean-reversion, orderflow scalp (new shared/archetypes/ folder) | Any strategy with pure-function simulator |
| Periods | P1 IS + P2 OOS | P3 OOS (~Jun 2026) — one period_config.md edit, Stage 01 re-run | Rolling quarterly, no code changes |
| Autoresearch budget | 300/200/500 per archetype | Budget accumulates across passes (Bonferroni tightening) | Multiple archetypes share dashboard, each with own budget counter |

### Scaling Priorities

1. **First bottleneck (adding a new archetype):** The intake checklist (strategy_archetypes.md registration + shared/archetypes/ creation + data validation + scoring model freeze) is the bottleneck. This is intentional — it is the quality gate. Budget 4–8 hours for a new archetype intake.
2. **Second bottleneck (multiple overnight loops):** Running Stage 02 + Stage 03 + Stage 04 for two archetypes simultaneously requires careful budget tracking. The dashboard/results_master.tsv filters by archetype — each archetype's n_prior_tests is independent.

---

## Sources

- `C:/Projects/pipeline/Futures_Pipeline_Architecture_ICM.md` (v2026-03-13) — authoritative build spec, all stage contracts, autoresearch loop design, audit tracker, extensibility convention
- `C:/Projects/pipeline/Futures_Pipeline_Functional_Spec.md` (v1.0, 2026-03-11) — master build checklist, all Pass 1/1.5/2/3 task specs, Q1–Q6 answers, ICM file length constraints
- `C:/Projects/pipeline/.planning/PROJECT.md` — active requirements, build order, constraints, key decisions

---
*Architecture research for: futures trading strategy research pipeline*
*Researched: 2026-03-13*
