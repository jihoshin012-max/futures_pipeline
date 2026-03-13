# Requirements: Futures Pipeline

**Defined:** 2026-03-13
**Core Value:** Every deployed strategy traces back to a statistically validated, internally replicated hypothesis with frozen parameters — no unaudited shortcuts from idea to live trading.

## v1 Requirements

Requirements for initial release. Each maps to roadmap phases.

### Prerequisites

- [ ] **PREREQ-01**: RinDig ICM repo fetched and reviewed; any convention conflicts resolved in spec
- [ ] **PREREQ-02**: karpathy/autoresearch repo fetched and reviewed; program.md format, train.py keep/revert logic, overnight run protocol understood
- [ ] **PREREQ-03**: NQ bar data files migrated to 01-data/data/bar_data/ for P1 and P2
- [ ] **PREREQ-04**: Touch/signal data migrated to 01-data/data/touches/ for P1 and P2

### Scaffold

- [ ] **SCAF-01**: Root folder structure created (stages 01-07, _config, shared, dashboard, archive, audit)
- [ ] **SCAF-02**: CLAUDE.md written (≤60 lines, 5 rules in first 20, hard prohibitions)
- [ ] **SCAF-03**: Root CONTEXT.md routing file (active stage, stage status table, human checkpoints)
- [ ] **SCAF-04**: _config/instruments.md (NQ registered with all fields, template for new instruments)
- [ ] **SCAF-05**: _config/data_registry.md (all sources registered, type taxonomy, add-source workflow)
- [ ] **SCAF-06**: _config/period_config.md (P1 IS + P2 OOS boundaries, P1a/P1b split, rolling-forward rules)
- [ ] **SCAF-07**: _config/pipeline_rules.md (all 5 rules including Rule 4 + Rule 5, grandfathering note)
- [ ] **SCAF-08**: _config/statistical_gates.md (verdict thresholds, iteration budgets, Bonferroni gates, drawdown gate)
- [ ] **SCAF-09**: _config/regime_definitions.md (3 dimensions, Stage 05 usage rules)
- [ ] **SCAF-10**: _config/context_review_protocol.md (file length limits, front-loading rule, staleness flag)
- [ ] **SCAF-11**: shared/feature_definitions.md (entry-time rule, template, empty registered features)
- [ ] **SCAF-12**: 02-features/references/feature_rules.md (5 rules, ≤30 lines)
- [ ] **SCAF-13**: 02-features/references/feature_catalog.md (active/dropped/dead-end tables)
- [ ] **SCAF-14**: shared/scoring_models/ directory + _template.json + scoring_adapter.py (3 adapter stubs)
- [ ] **SCAF-15**: Stage 01 CONTEXT.md + reference schema files + data_manifest.json schema spec
- [ ] **SCAF-16**: Stage 02 CONTEXT.md
- [ ] **SCAF-17**: Stage 03 CONTEXT.md
- [ ] **SCAF-18**: Stage 04 CONTEXT.md + shared/archetypes/{archetype}/exit_templates.md
- [ ] **SCAF-19**: Stage 05 CONTEXT.md + verdict_criteria.md + statistical_tests.md
- [ ] **SCAF-20**: Stage 06 CONTEXT.md + context_package_spec.md + assemble_context.sh
- [ ] **SCAF-21**: Stage 07 CONTEXT.md + triggers/review_triggers.md
- [ ] **SCAF-22**: dashboard/results_master.tsv (header row, 24 columns)
- [ ] **SCAF-23**: dashboard/index.html stub
- [ ] **SCAF-24**: audit/audit_log.md stub (append-only header + first manual entry)
- [ ] **SCAF-25**: audit/audit_entry.sh (promote, deploy, note, fill commands)
- [ ] **SCAF-26**: 03-hypothesis/references/strategy_archetypes.md (template + simulator interface contract)

### HMM Regime

- [ ] **HMM-01**: hmm_regime_fitter.py written (fit on P1 only, apply frozen model to P2)
- [ ] **HMM-02**: regime_labels.csv generated covering P1 and P2 date ranges
- [ ] **HMM-03**: hmm_regime_v1.pkl serialized and registered in strategy_archetypes.md

### Git Infrastructure

- [ ] **GIT-01**: autocommit.sh (30s poll, auto: prefix, nohup-compatible, run_id contract)
- [ ] **GIT-02**: .git/hooks/pre-commit (holdout guard, audit append-only, HYPOTHESIS_PROMOTED, PERIOD_CONFIG_CHANGED, period rollover warning)
- [ ] **GIT-03**: .git/hooks/post-commit (commit_log.txt, OOS_RUN, DEPLOYMENT_APPROVED auto-entries)
- [ ] **GIT-04**: Infrastructure verification (autocommit tested, holdout guard tested, commit log verified)

### Backtest Engine

- [ ] **ENGINE-01**: Q1-Q6 answers documented in backtest_engine_qa.md
- [ ] **ENGINE-02**: data_loader.py patched (5 hardcoded paths parameterized, existing callers updated)
- [ ] **ENGINE-03**: backtest_engine.py written (~175-225 lines, dynamic dispatch, holdout guard, per-mode breakdown)
- [ ] **ENGINE-04**: config_schema.json written (all fields, trail step validation rules)
- [ ] **ENGINE-05**: config_schema.md written (every field documented, FIXED vs CANDIDATE)
- [ ] **ENGINE-06**: Determinism verified (identical config → identical output, diffed)
- [ ] **ENGINE-07**: Manual end-to-end pass (01 → 04 → 05, verdict_report.md well-formed)
- [ ] **ENGINE-08**: shared/archetypes/{archetype}/simulation_rules.md written from actual source

### Autoresearch Loops

- [ ] **AUTO-01**: Stage 04 driver.py written (keep/revert loop, budget enforcement, EXPERIMENT_ANOMALY handling)
- [ ] **AUTO-02**: Stage 04 program.md written (≤30 lines, machine-readable METRIC/KEEP RULE/BUDGET)
- [ ] **AUTO-03**: Stage 04 overnight test (50 experiments, results.tsv populated, keep/revert verified)
- [ ] **AUTO-04**: evaluate_features.py dispatcher written (~30 lines, loads archetype evaluator)
- [ ] **AUTO-05**: shared/archetypes/{archetype}/feature_evaluator.py written (standard interface)
- [ ] **AUTO-06**: Stage 02 driver.py written (feature keep/revert, entry-time enforcement, 300 budget)
- [ ] **AUTO-07**: Stage 02 program.md written (≤30 lines)
- [ ] **AUTO-08**: Stage 02 overnight test (20 experiments, feature spread values, entry-time block verified)
- [ ] **AUTO-09**: hypothesis_generator.py written (Rule 4 P1a/P1b replication, Bonferroni gates)
- [ ] **AUTO-10**: Stage 03 driver.py written (hypothesis keep/revert, replication enforcement, 200 budget)
- [ ] **AUTO-11**: Stage 03 program.md written (≤30 lines)
- [ ] **AUTO-12**: Stage 03 overnight test (12 experiments, replication_pass column, Rule 4 enforced)
- [ ] **AUTO-13**: Feedback loop wired (Stage 05 feedback_to_hypothesis.md → Stage 03 prior_results.md)

## v2 Requirements

Deferred to future release. Tracked but not in current roadmap.

### Dashboard (Milestone 2)

- **DASH-01**: Results trend view (PF over time per archetype)
- **DASH-02**: Feature heatmap (predictive spread by feature)
- **DASH-03**: Regime breakdown visualization
- **DASH-04**: Interactive filtering by archetype, verdict, date range

### Multi-Instrument

- **INST-01**: ES (E-mini S&P 500) archetype support
- **INST-02**: GC (Gold Futures) archetype support

### Multi-Archetype

- **ARCH-01**: Orderflow scalp archetype alongside signal-touch

### Advanced Statistical

- **STAT-01**: Monte Carlo simulation (confidence intervals on PF)
- **STAT-02**: Q7 resolution — multi-period IS combined pool vs separate folds

## Out of Scope

| Feature | Reason |
|---------|--------|
| Real-time streaming data | Batch pipeline only; Sierra Chart handles live execution |
| Multiple OOS looks | Destroys one-shot OOS guarantee — structural anti-feature |
| Soft holdout enforcement | Must be structural (flag + hook + engine guard), not convention |
| Interactive parameter tuning on OOS data | Invalidates statistical validation |
| Web authentication / user management | Single-user research tool, no web UI beyond dashboard stub |
| Mobile app | Not applicable to desktop trading research workflow |
| ML model auto-selection | BinnedScoringAdapter is v1 default; Sklearn/ONNX adapters are stubs for future |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| PREREQ-01 | Phase 1 | Pending |
| PREREQ-02 | Phase 1 | Pending |
| PREREQ-03 | Phase 1 | Pending |
| PREREQ-04 | Phase 1 | Pending |
| SCAF-01 | Phase 1 | Pending |
| SCAF-02 | Phase 1 | Pending |
| SCAF-03 | Phase 1 | Pending |
| SCAF-04 | Phase 1 | Pending |
| SCAF-05 | Phase 1 | Pending |
| SCAF-06 | Phase 1 | Pending |
| SCAF-07 | Phase 1 | Pending |
| SCAF-08 | Phase 1 | Pending |
| SCAF-09 | Phase 1 | Pending |
| SCAF-10 | Phase 1 | Pending |
| SCAF-11 | Phase 1 | Pending |
| SCAF-12 | Phase 1 | Pending |
| SCAF-13 | Phase 1 | Pending |
| SCAF-14 | Phase 1 | Pending |
| SCAF-15 | Phase 1 | Pending |
| SCAF-16 | Phase 1 | Pending |
| SCAF-17 | Phase 1 | Pending |
| SCAF-18 | Phase 1 | Pending |
| SCAF-19 | Phase 1 | Pending |
| SCAF-20 | Phase 1 | Pending |
| SCAF-21 | Phase 1 | Pending |
| SCAF-22 | Phase 1 | Pending |
| SCAF-23 | Phase 1 | Pending |
| SCAF-24 | Phase 1 | Pending |
| SCAF-25 | Phase 1 | Pending |
| SCAF-26 | Phase 1 | Pending |
| HMM-01 | Phase 2 | Pending |
| HMM-02 | Phase 2 | Pending |
| HMM-03 | Phase 2 | Pending |
| GIT-01 | Phase 3 | Pending |
| GIT-02 | Phase 3 | Pending |
| GIT-03 | Phase 3 | Pending |
| GIT-04 | Phase 3 | Pending |
| ENGINE-01 | Phase 4 | Pending |
| ENGINE-02 | Phase 4 | Pending |
| ENGINE-03 | Phase 4 | Pending |
| ENGINE-04 | Phase 4 | Pending |
| ENGINE-05 | Phase 4 | Pending |
| ENGINE-06 | Phase 4 | Pending |
| ENGINE-07 | Phase 4 | Pending |
| ENGINE-08 | Phase 4 | Pending |
| AUTO-01 | Phase 5 | Pending |
| AUTO-02 | Phase 5 | Pending |
| AUTO-03 | Phase 5 | Pending |
| AUTO-04 | Phase 5 | Pending |
| AUTO-05 | Phase 5 | Pending |
| AUTO-06 | Phase 6 | Pending |
| AUTO-07 | Phase 6 | Pending |
| AUTO-08 | Phase 6 | Pending |
| AUTO-09 | Phase 7 | Pending |
| AUTO-10 | Phase 7 | Pending |
| AUTO-11 | Phase 7 | Pending |
| AUTO-12 | Phase 7 | Pending |
| AUTO-13 | Phase 7 | Pending |

**Coverage:**
- v1 requirements: 57 total
- Mapped to phases: 57
- Unmapped: 0 ✓

---
*Requirements defined: 2026-03-13*
*Last updated: 2026-03-13 after initial definition*
