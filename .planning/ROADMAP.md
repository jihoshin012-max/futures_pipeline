# Roadmap: Futures Pipeline

## Overview

Build a structured futures trading strategy research pipeline from scratch: starting with a static scaffold of config files, stage contracts, and data migration (Pass 1), adding git integrity infrastructure (Pass 1.5), then a deterministic backtest engine (Pass 2), and finally three autoresearch loops in dependency order — Stage 04 exit optimization first, Stage 02 feature engineering second, Stage 03 hypothesis generation last (Pass 3). Each phase is a hard gate; the next phase cannot start until the prior one is verified operational.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [x] **Phase 1: Scaffold** - Create all static config files, stage CONTEXT.md files, shared resources, and migrate data (completed 2026-03-14)
- [x] **Phase 2: HMM Regime Fitter** - Fit, serialize, and validate the regime labeling model before any research begins (completed 2026-03-14)
- [x] **Phase 3: Git Infrastructure** - Autocommit watcher, holdout guard hook, and post-commit audit entries operational (completed 2026-03-14)
- [ ] **Phase 4: Backtest Engine** - Deterministic, dynamically dispatching engine verified with a manual end-to-end pass
- [ ] **Phase 5: Stage 04 Autoresearch** - Exit parameter keep/revert loop with overnight test confirming operational
- [ ] **Phase 6: Stage 02 Autoresearch** - Feature engineering keep/revert loop with entry-time enforcement verified
- [ ] **Phase 7: Stage 03 Autoresearch** - Hypothesis generation loop with replication enforcement and feedback loop wired

## Phase Details

### Phase 1: Scaffold
**Goal**: The complete static layer of the pipeline exists — every config file, stage routing document, and shared resource is committed and readable by any downstream component
**Depends on**: Nothing (first phase)
**Requirements**: PREREQ-01, PREREQ-02, PREREQ-03, PREREQ-04, SCAF-01, SCAF-02, SCAF-03, SCAF-04, SCAF-05, SCAF-06, SCAF-07, SCAF-08, SCAF-09, SCAF-10, SCAF-11, SCAF-12, SCAF-13, SCAF-14, SCAF-15, SCAF-16, SCAF-17, SCAF-18, SCAF-19, SCAF-20, SCAF-21, SCAF-22, SCAF-23, SCAF-24, SCAF-25, SCAF-26
**Success Criteria** (what must be TRUE):
  1. All 7 stage directories exist under the project root and each contains a CONTEXT.md that opens with its operative instruction in the first 5 lines
  2. All _config/ files (instruments.md, data_registry.md, period_config.md, pipeline_rules.md, statistical_gates.md, regime_definitions.md, context_review_protocol.md) are present and NQ is registered as the active instrument
  3. NQ bar data and touch/signal data are present in 01-data/data/bar_data/ and 01-data/data/touches/ for both P1 and P2 date ranges
  4. shared/scoring_models/ contains _template.json and scoring_adapter.py with three adapter stubs; shared/archetypes/ contains exit_templates.md for the signal-touch archetype
  5. The P1a/P1b split boundary is committed in period_config.md before any evaluation file exists in the repository
**Plans:** 6/6 plans complete

Plans:
- [x] 01-01-PLAN.md — Prerequisites: clone reference repos and migrate data
- [x] 01-02-PLAN.md — Root structure, CLAUDE.md, CONTEXT.md, and all _config/ files
- [x] 01-03-PLAN.md — Shared resources: feature definitions, rules, catalog, scoring models
- [x] 01-04-PLAN.md — Stage 01-04 CONTEXT.md files and reference docs
- [x] 01-05-PLAN.md — Stage 05-07 CONTEXT.md files and supporting files
- [x] 01-06-PLAN.md — Dashboard stubs, audit infrastructure, strategy archetypes

### Phase 01.2: Bar type registry and subfolder structure (INSERTED)

**Goal:** Bar data files are organized in typed subfolders (volume/time/tick) with per-type source_ids in data_registry.md and matching schema files — enabling Phase 4 backtest engine config paths to resolve correctly
**Requirements**: BAR-01, BAR-02, BAR-03, BAR-04
**Depends on:** Phase 1
**Success Criteria** (what must be TRUE):
  1. Bar data files live in `bar_data/volume/` subfolder, not flat `bar_data/`
  2. `data_registry.md` uses typed source_ids (`bar_data_volume`, `bar_data_time`, `bar_data_tick`), not bare `bar_data`
  3. Schema file `bar_data_volume_schema.md` exists with correct source_id naming convention
  4. Placeholder subfolders (`time/`, `tick/`) exist for future bar types
**Plans:** 1/1 plans complete

Plans:
- [x] 01.2-01-PLAN.md — Migrate bar files to volume/ subfolder, update registry with typed source_ids, rename schema

### Phase 01.1: Scoring Adapter Scaffold Generator (INSERTED)

**Goal**: A scaffold generator exists that auto-creates scoring adapter stubs, adapter tests, and audit entries when a new archetype is registered with an unrecognized scoring_adapter value — reducing manual friction and enforcing the adapter interface contract
**Requirements**: SCAF-27
**Depends on:** Phase 1
**Plans:** 1/1 plans complete

Plans:
- [x] 01.1-01-PLAN.md — Commit scaffold_adapter.py and create integration test for SCAF-27

### Phase 2: HMM Regime Fitter
**Goal**: The regime fitter is written, validated for P1-only fitting with no look-ahead, and has produced a serialized model and regime_labels.csv that later stages can consume read-only
**Depends on**: Phase 1
**Requirements**: HMM-01, HMM-02, HMM-03
**Success Criteria** (what must be TRUE):
  1. hmm_regime_fitter.py runs without error and fits the GaussianHMM exclusively on P1 bar data (P2 rows are never passed to fit())
  2. regime_labels.csv exists covering the full P1+P2 date range, with labels generated from the frozen P1-fitted model applied forward (filtered probabilities, not Viterbi)
  3. hmm_regime_v1.pkl is serialized to shared/scoring_models/hmm_regime_v1.pkl
**Plans:** 2/2 plans complete

Plans:
- [x] 02-01-PLAN.md — TDD: Write tests and implement hmm_regime_fitter.py (fit, label, serialize)
- [x] 02-02-PLAN.md — Run fitter on real data, validate outputs, register model

### Phase 3: Git Infrastructure
**Goal**: Every file change during autoresearch is automatically committed, the holdout flag structurally blocks P2 data commits, and audit entries are appended automatically on OOS runs and deployments
**Depends on**: Phase 1
**Requirements**: GIT-01, GIT-02, GIT-03, GIT-04
**Success Criteria** (what must be TRUE):
  1. A file change followed by a 30-second wait produces a new git commit prefixed "auto:" in git log — verified by watching git log in real time
  2. A commit that touches any file under 04-backtest/p2_holdout/ is rejected by the pre-commit hook with a holdout guard message
  3. A commit that modifies (not appends to) audit/audit_log.md is rejected by the pre-commit hook
  4. A commit tagged OOS_RUN or DEPLOYMENT_APPROVED causes the post-commit hook to write the corresponding entry into audit_log.md automatically
**Plans:** 2/2 plans complete

Plans:
- [x] 03-01-PLAN.md — TDD: Create test scaffold and implement autocommit.sh, pre-commit hook, post-commit hook
- [x] 03-02-PLAN.md — Run automated verification suite and manual end-to-end verification

### Phase 4: Backtest Engine
**Goal**: The backtest engine is a fixed, deterministic evaluation harness that any autoresearch loop can run safely — verified by two identical-config runs producing byte-identical output and a manual 01-to-05 pass succeeding
**Depends on**: Phase 1, Phase 3
**Requirements**: ENGINE-01, ENGINE-02, ENGINE-03, ENGINE-04, ENGINE-05, ENGINE-06, ENGINE-07, ENGINE-08, ENGINE-09
**Success Criteria** (what must be TRUE):
  1. Running the engine twice with the same config.json produces byte-for-byte identical trade ledgers (verified by diff returning empty)
  2. The engine aborts at import time if holdout_locked_P2.flag is present and the mode is not explicitly OOS — this cannot be bypassed by config
  3. A manual run from Stage 01 through Stage 04 through Stage 05 produces a well-formed verdict_report.md with a net-of-cost Sharpe that is less than 80% of the gross Sharpe, confirming realistic cost modeling
  4. config_schema.json and config_schema.md document every field, distinguish FIXED from CANDIDATE parameters, and trail step validation rules are enforced by the engine on load
  5. Loading the engine with a config pointing to an unimplemented adapter stub aborts at load time with a clear error naming the adapter — not silently failing mid-experiment
**Plans**: TBD

### Phase 5: Stage 04 Autoresearch
**Goal**: The Stage 04 overnight loop runs unattended against the fixed backtest engine, enforces its iteration budget from statistical_gates config, and populates results.tsv with keep/revert decisions that a human can review in the morning
**Depends on**: Phase 4
**Requirements**: AUTO-01, AUTO-02, AUTO-03, AUTO-04, AUTO-05
**Success Criteria** (what must be TRUE):
  1. An overnight test of 50 experiments completes without human intervention and results.tsv has 50 rows with monotonically increasing experiment IDs
  2. The driver refuses to launch experiment N+1 when N equals the budget declared in statistical_gates config — verified by setting budget to 3 and confirming the driver stops after 3 runs
  3. A kept experiment's config change is visible in git history (autocommit captured it); a reverted experiment's config is identical to the prior kept state
**Plans**: TBD

### Phase 6: Stage 02 Autoresearch
**Goal**: The Stage 02 overnight loop evaluates feature candidates using MWU spread, enforces the entry-time-only rule structurally, and produces a feature catalog update after each overnight run
**Depends on**: Phase 5
**Requirements**: AUTO-06, AUTO-07, AUTO-08
**Success Criteria** (what must be TRUE):
  1. An overnight test of 20 experiments completes and each row in results.tsv contains a spread value computed from MWU on P1a vs P1b feature distributions
  2. A feature that reads a bar-close value (post-entry-time data) is detected by the canary test in feature_evaluator.py and logged as an entry-time violation, blocking the keep decision
  3. The driver stops at the 300-experiment budget declared in statistical_gates and does not run experiment 301 even if program.md instructs continued iteration
**Plans**: TBD

### Phase 7: Stage 03 Autoresearch
**Goal**: The Stage 03 overnight loop generates and tests hypotheses with P1a/P1b replication enforcement, and the feedback loop from Stage 05 assessment automatically informs the next hypothesis generation pass
**Depends on**: Phase 6
**Requirements**: AUTO-09, AUTO-10, AUTO-11, AUTO-12, AUTO-13
**Success Criteria** (what must be TRUE):
  1. An overnight test of 12 experiments completes and results.tsv contains a replication_pass column — each hypothesis that passed P1a also shows P1b replication result
  2. A hypothesis that passes P1a but fails P1b replication is marked failed and the driver reverts, enforcing Rule 4 structurally
  3. The driver enforces the 200-experiment budget from statistical_gates and rejects launch of experiment 201
  4. After a Stage 05 assessment run, feedback_to_hypothesis.md is automatically present in Stage 03's prior_results.md location so the next Stage 03 run can condition on it without human intervention
**Plans**: TBD

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 3 → 4 → 5 → 6 → 7

Note: Phase 2 (HMM) and Phase 3 (Git Infrastructure) both depend only on Phase 1 and can be planned in parallel, but Phase 4 depends on Phase 3 being complete.

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Scaffold | 6/6 | Complete   | 2026-03-14 |
| 01.1. Scoring Adapter Scaffold Generator | 1/1 | Complete    | 2026-03-14 |
| 01.2. Bar Type Registry | 1/1 | Complete    | 2026-03-14 |
| 2. HMM Regime Fitter | 2/2 | Complete | 2026-03-14 |
| 3. Git Infrastructure | 2/2 | Complete | 2026-03-14 |
| 4. Backtest Engine | 0/TBD | Not started | - |
| 5. Stage 04 Autoresearch | 0/TBD | Not started | - |
| 6. Stage 02 Autoresearch | 0/TBD | Not started | - |
| 7. Stage 03 Autoresearch | 0/TBD | Not started | - |
