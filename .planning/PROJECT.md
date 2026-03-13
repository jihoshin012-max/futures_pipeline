# Futures Pipeline

## What This Is

A structured research and deployment pipeline for futures trading strategies on NQ (E-mini NASDAQ-100). It applies the Karpathy autoresearch pattern — agent edits one file, fixed harness evaluates, human steers via program.md — across a 7-stage workflow (data → features → hypothesis → backtest → assessment → deployment → live monitoring). The pipeline enforces rigorous IS/OOS discipline, multiple testing controls, and full audit lineage from experiment to deployment.

## Core Value

Every deployed strategy traces back to a statistically validated, internally replicated hypothesis with frozen parameters — no unaudited shortcuts from idea to live trading.

## Requirements

### Validated

(None yet — ship to validate)

### Active

- [ ] P0 prerequisites: fetch and review RinDig ICM + karpathy/autoresearch repos; NQ bar data + touch data migrated
- [ ] Pass 1 scaffold: root folder structure, CLAUDE.md, root CONTEXT.md, all _config/ files (instruments, data_registry, period_config, pipeline_rules, statistical_gates, regime_definitions, context_review_protocol), shared/ files (feature_definitions, feature_rules, feature_catalog, scoring_models + adapter, archetypes), all 7 stage CONTEXT.md files with reference docs, dashboard stubs, audit infrastructure stubs, strategy_archetypes.md
- [ ] HMM regime fitter (hmm_regime_fitter.py) producing regime_labels.csv covering P1+P2 and serialized model
- [ ] Pass 1.5 git infrastructure: autocommit.sh, pre-commit hook (holdout guard + audit auto-entries + period rollover warning), post-commit hook (commit log + OOS_RUN + DEPLOYMENT_APPROVED), verification
- [ ] Pass 2 backtest engine: Q1-Q6 documented, data_loader.py patched (parameterized paths), backtest_engine.py (~175-225 lines, dynamic dispatch), config_schema.json + config_schema.md, determinism verified, end-to-end manual pass, simulation_rules.md
- [ ] Pass 3 autoresearch loops: Stage 04 driver + overnight test, evaluate_features.py dispatcher + archetype feature_evaluator.py, Stage 02 driver + overnight test, hypothesis_generator.py (Rule 4 enforcement), Stage 03 driver + overnight test, feedback loop wired (Stage 05 → prior_results.md → Stage 03)

### Out of Scope

- Dashboard beyond stub — deferred to Milestone 2 (Futures_Pipeline_Dashboard_Spec.md)
- Multiple instruments (ES, GC) — NQ only for v1
- Multiple archetypes — signal-touch only for v1
- Real-time chat/streaming data — batch pipeline only
- OAuth/web auth — no web UI beyond dashboard stub
- Mobile app — not applicable
- Q7 (multi-period IS combined pool vs separate folds) — deferred until P3 data arrives ~Jun 2026

## Context

- **Architecture:** Signal-touch archetype on NQ. Scored entries via BinnedScoringAdapter, multi-leg partial exits with trail steps, time cap. Routing waterfall across modes.
- **IS/OOS periods:** P1 (IS: 2025-09-16 to 2025-12-14), P2 (OOS: 2025-12-15 to 2026-03-02). Internal replication: P1a (calibrate) / P1b (replicate) split.
- **Statistical rigor:** Bonferroni-adjusted p-value gates, iteration budgets per stage, drawdown gate as multiple of avg winner. All enforced structurally, not by convention.
- **Autoresearch pattern:** Karpathy keep/revert loop. Agent edits one file, fixed harness evaluates, program.md steers direction. Overnight runs with human morning review.
- **Data:** NQ bar data (1-min OHLCV) + archetype-specific touch/signal data for P1 and P2. Data ready to migrate.
- **Reference repos:** RinDig ICM (context methodology conventions) and karpathy/autoresearch (driver loop pattern) — to be fetched and reviewed as prerequisites.
- **Spec source:** Futures_Pipeline_Functional_Spec.md (v1.0, 2026-03-11) is the authoritative build spec. Architecture doc (Futures_Pipeline_Architecture_ICM.md) provides hook/audit script implementations.

## Constraints

- **Five pipeline rules:** P1 calibrate freely, P2 one-shot only, entry-time features only, internal replication before P2, instrument constants from registry
- **Lost-in-middle:** CLAUDE.md ≤60 lines, CONTEXT.md ≤80 lines, program.md ≤30 lines. Operative instruction in first 5 lines of every agent-read file.
- **Holdout discipline:** holdout_locked_P2.flag enforces OOS one-shot structurally via pre-commit hook + engine guard
- **Append-only audit:** audit_log.md never modified, only appended. Pre-commit hook enforces.
- **Build order:** Pass 1 → 1.5 → 2 (blocked on Q1-Q6, already answered) → 3 (Stage 04 first, then 02, then 03). Dashboard deferred to Milestone 2.
- **From scratch:** No prior strategy to migrate. Pipeline starts empty. Stage 07 monitoring begins after first deployment.

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Dynamic simulator dispatch (Option B) | New archetype = new module, no engine changes | — Pending |
| BinnedScoringAdapter as default | JSON scoring model with frozen bin_edges from P1 | — Pending |
| Karpathy autoresearch pattern | Proven keep/revert loop, overnight-steerable via program.md | — Pending |
| Signal-touch as first archetype on NQ | Scored entries + multi-leg exits, well-understood domain | — Pending |
| Dashboard deferred to Milestone 2 | Different skill set (frontend JS), zero pipeline dependency, separate spec | — Pending |
| All Q1-Q6 answered in spec | Unblocks Pass 2 immediately after Pass 1.5 | — Pending |

---
*Last updated: 2026-03-13 after initialization*
