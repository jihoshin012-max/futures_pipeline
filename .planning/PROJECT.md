# Futures Pipeline

## What This Is

A structured research and deployment pipeline for futures trading strategies on NQ (E-mini NASDAQ-100). It applies the Karpathy autoresearch pattern — agent edits one file, fixed harness evaluates, human steers via program.md — across a 7-stage workflow (data → features → hypothesis → backtest → assessment → deployment → live monitoring). The pipeline enforces rigorous IS/OOS discipline, multiple testing controls, and full audit lineage from experiment to deployment.

## Core Value

Every deployed strategy traces back to a statistically validated, internally replicated hypothesis with frozen parameters — no unaudited shortcuts from idea to live trading.

## Requirements

### Validated

- ✓ P0 prerequisites: reference repos fetched, NQ bar/touch data migrated — v1.0
- ✓ Pass 1 scaffold: root structure, all _config files, 7 stage CONTEXT.md files, shared resources, audit infrastructure — v1.0
- ✓ HMM regime fitter: regime_labels.csv (144 days) + hmm_regime_v1.pkl with P1-only fit — v1.0
- ✓ Pass 1.5 git infrastructure: autocommit, holdout guard hook, audit auto-entries — v1.0
- ✓ Pass 2 backtest engine: deterministic engine, dynamic dispatch, config schema, cost modeling — v1.0
- ✓ Pass 3 autoresearch loops: Stage 04/02/03 drivers with budget enforcement, keep/revert, P1b replication — v1.0
- ✓ Assessment feedback loop: Stage 05 → prior_results.md → Stage 03 — v1.0

### Active

(None yet — define with `/gsd:new-milestone`)

### Out of Scope

- Dashboard beyond stub — deferred to Milestone 2 (Futures_Pipeline_Dashboard_Spec.md)
- Multiple instruments (ES, GC) — NQ only for v1
- Multiple archetypes — signal-touch only for v1
- Real-time chat/streaming data — batch pipeline only
- OAuth/web auth — no web UI beyond dashboard stub
- Mobile app — not applicable
- Q7 (multi-period IS combined pool vs separate folds) — deferred until P3 data arrives ~Jun 2026
- MWU/permutation/percentile rank statistical tests in assess.py — v1.0 uses PF-only verdicts; reference specs ready for future implementation
- results_master.tsv consolidation — each stage has its own results.tsv; master aggregation deferred

## Context

Shipped v1.0 with 9,208 Python LOC across 236 files.
Tech stack: Python 3, hmmlearn (GaussianHMM), pandas, scipy (MWU), bash (git hooks/autocommit).

**Current codebase state:**
- 3 autoresearch drivers operational (Stages 02, 03, 04) with keep/revert loops and budget enforcement
- Deterministic backtest engine with zone_touch simulator, BinnedScoringAdapter, and holdout guard
- HMM regime labels and serialized model ready but not yet consumed by scoring/hypothesis code
- 9,208 LOC Python, ~160 commits, full test suite passing (1 known broken mock in test_hypothesis_generator.py)

**Known tech debt (from v1.0 audit):**
- assess.py: PF-only verdicts — MWU, permutation, percentile rank tests specified but unimplemented
- HMM artifacts (regime_labels.csv, hmm_regime_v1.pkl): exist but not consumed by downstream code
- results_master.tsv: header-only, no aggregation mechanism
- 1 failing unit test: test_temp_files_cleaned_up_on_failure (mock detection broken)
- Reaction proxy used as outcome variable in feature evaluation (precomputed pnl_ticks not yet available)

## Constraints

- **Five pipeline rules:** P1 calibrate freely, P2 one-shot only, entry-time features only, internal replication before P2, instrument constants from registry
- **Lost-in-middle:** CLAUDE.md ≤60 lines, CONTEXT.md ≤80 lines, program.md ≤30 lines. Operative instruction in first 5 lines of every agent-read file.
- **Holdout discipline:** holdout_locked_P2.flag enforces OOS one-shot structurally via pre-commit hook + engine guard
- **Append-only audit:** audit_log.md never modified, only appended. Pre-commit hook enforces.

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Dynamic simulator dispatch (Option B) | New archetype = new module, no engine changes | ✓ Good — importlib dispatch works cleanly |
| BinnedScoringAdapter as default | JSON scoring model with frozen bin_edges from P1 | ✓ Good — placeholder returns score=0 correctly |
| Karpathy autoresearch pattern | Proven keep/revert loop, overnight-steerable via program.md | ✓ Good — all 3 stages operational |
| Signal-touch as first archetype on NQ | Scored entries + multi-leg exits, well-understood domain | ✓ Good — zone_touch simulator verified |
| Dashboard deferred to Milestone 2 | Different skill set (frontend JS), zero pipeline dependency | ✓ Good — kept scope manageable |
| Event-driven git commits in drivers | Replaces reliance on autocommit.sh polling during experiments | ✓ Good — lockfile coordination works |
| Reaction proxy for outcome variable | Precomputed pnl_ticks not yet in touch CSV | ⚠️ Revisit — needs recalibration when pnl_ticks available |
| PF-only verdicts in assess.py | MWU/permutation specs ready but deferred | ⚠️ Revisit — statistical rigor gap |
| P1b replication as flag_and_review | Allows kept_weak_replication while pipeline matures | — Pending (may switch to hard_block) |

---
*Last updated: 2026-03-14 after v1.0 milestone*
