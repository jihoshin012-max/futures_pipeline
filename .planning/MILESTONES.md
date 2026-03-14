# Milestones

## v1.0 Futures Pipeline (Shipped: 2026-03-14)

**Phases completed:** 9 phases, 26 plans, 4 tasks

**Key accomplishments:**
1. Complete 7-stage pipeline scaffold with all _config files, stage CONTEXT.md routing, shared resources, and audit infrastructure
2. HMM regime fitter producing regime_labels.csv (144 trading days) and serialized model with P1-only fit guarantee
3. Git infrastructure: autocommit watcher, holdout guard pre-commit hook, audit auto-entries in post-commit hook
4. Deterministic backtest engine with zone_touch simulator, dynamic dispatch, holdout guard, and cost modeling from instruments.md
5. Three autoresearch loops operational (Stages 04/02/03) with keep/revert drivers, budget enforcement, and event-driven git commits
6. P1b replication enforcement (Rule 4) structurally enforced in Stage 03 hypothesis generation
7. Assessment feedback loop wired: Stage 05 verdict flows back to Stage 03 prior_results.md

**Tech debt accepted:** 13 items (see v1.0-MILESTONE-AUDIT.md) including 1 broken test mock, MWU/permutation tests unimplemented in assess.py, HMM artifacts not yet consumed downstream, results_master.tsv header-only

**Timeline:** 2 days (2026-03-13 to 2026-03-14) | 160 commits | 9,208 Python LOC

---

