# Project Retrospective

*A living document updated after each milestone. Lessons feed forward into future planning.*

## Milestone: v1.0 — Futures Pipeline

**Shipped:** 2026-03-14
**Phases:** 9 | **Plans:** 26 | **Timeline:** 2 days

### What Was Built
- Complete 7-stage pipeline scaffold with all config files, stage contracts, and shared resources
- HMM regime fitter with P1-only fit producing regime_labels.csv (144 days) and serialized model
- Git infrastructure: autocommit watcher, holdout guard, audit auto-entries
- Deterministic backtest engine with zone_touch simulator, dynamic dispatch, holdout guard
- Three autoresearch loops (Stages 04/02/03) with keep/revert drivers, budget enforcement
- P1b replication enforcement (Rule 4) in Stage 03 hypothesis generation
- Assessment feedback loop: Stage 05 verdict → prior_results.md → Stage 03

### What Worked
- TDD pattern for infrastructure phases (02, 03, 04) — RED → GREEN → artifact delivery created clean verification stories
- Event-driven git commits in drivers replaced unreliable autocommit polling during experiments
- Lockfile coordination between drivers and autocommit.sh prevented commit conflicts
- Phase verification before proceeding caught real issues (01.2 traceability gap, Phase 05 autocommit uncertainty)
- Budget smoke tests (budget=3) before overnight runs caught bugs cheaply
- Subprocess isolation for engine/evaluator/generator calls — each autoresearch stage calls fixed harness as subprocess, preventing import side effects

### What Was Inefficient
- Phase 05 ROADMAP plan checkboxes not updated after execution (showed 2/3 when 4/4 complete) — created confusion during audit
- SUMMARY.md files lack `requirements_completed` frontmatter — made 3-source cross-reference degrade to 2-source
- Phase 01.2 was inserted urgently for bar type subfolder migration — could have been anticipated in initial scaffold planning if data loader paths were checked earlier
- 17 EXPERIMENT_ANOMALY entries in audit log during Stage 03 smoke test — all from P1b engine call bugs that should have been caught by unit tests

### Patterns Established
- `# archetype: zone_touch` header on line 1 of every archetype-specific Python file
- Stage autoresearch directory structure: `driver.py`, `program.md`, `current_best/`, `results.tsv`
- 24-column (Stage 02/04) and 25-column (Stage 03) TSV format for experiment results
- Lockfile `.autoresearch_running` suppresses autocommit polling during driver runs
- `parse_instruments_md()` shared function for reading instrument constants — no hardcoding
- Feature evaluation dispatcher pattern: `evaluate_features.py` → `importlib` → archetype-specific `feature_evaluator.py`

### Key Lessons
1. Budget smoke tests before overnight runs are essential — they catch parameter range bugs and subprocess wiring issues for ~1 minute of compute instead of hours
2. Event-driven git commits from driver code are more reliable than background polling — autocommit.sh is a fallback, not the primary mechanism
3. Entry-time enforcement must be structural (bar_df truncation + column stripping), not convention-based — the canary test pattern in feature_evaluator.py is the right approach
4. Decimal phase insertions (01.1, 01.2) worked well for urgent fixes but should be used sparingly — they complicate roadmap numbering
5. VERIFICATION.md files need updating when gaps are closed — stale `gaps_found` status caused confusion during milestone audit

### Cost Observations
- Model mix: balanced profile (sonnet for most agents, opus for orchestration)
- Sessions: ~15-20 across 2 days
- Notable: Parallelized phase research + planning significantly reduced wall clock time; overnight experiment runs were the longest wall-clock items

---

## Cross-Milestone Trends

### Process Evolution

| Milestone | Timeline | Phases | Key Change |
|-----------|----------|--------|------------|
| v1.0 | 2 days | 9 | Initial build — TDD, autoresearch pattern, budget smoke tests |

### Cumulative Quality

| Milestone | Tests | Passing | Tech Debt Items |
|-----------|-------|---------|-----------------|
| v1.0 | ~137 | 136/137 | 13 |

### Top Lessons (Verified Across Milestones)

1. Budget smoke tests before overnight runs catch subprocess wiring bugs cheaply
2. Structural enforcement > convention enforcement for data integrity rules
