# Project Research Summary

**Project:** Futures Trading Strategy Research and Deployment Pipeline
**Domain:** Quantitative research pipeline — NQ E-mini NASDAQ-100, signal-touch archetype
**Researched:** 2026-03-13
**Confidence:** HIGH

## Executive Summary

This project is a structured quantitative research pipeline for developing, validating, and deploying NQ futures strategies (signal-touch archetype), with automated overnight experimentation via the Karpathy autoresearch loop pattern. Experts in this domain build around a strict IS/OOS discipline enforced structurally (not by convention), a fixed evaluation harness with a keep/revert loop, and an immutable one-shot OOS gate. The recommended approach centers on three sequential build passes: scaffold the config layer and context contracts first (Pass 1), build and validate the backtest engine with verified determinism before any automation runs against it (Pass 2), then activate autoresearch loops in dependency order — Stage 04 first, then 02, then 03 (Pass 3). Each pass is a hard gate; the roadmap must not merge passes.

The key architectural commitment is treating the backtest engine as a fixed evaluation harness rather than an evolving codebase. The agent edits exactly one file per experiment; the harness is immutable once activated. Five architectural patterns govern all component interactions: the Karpathy keep/revert loop, ICM stage contracts with hard file-length limits, dynamic archetype dispatch via config, strict IS/OOS separation with three-layer enforcement, and frozen model artifacts with adapter interfaces. These patterns are not optional conventions — they are integrity mechanisms that break predictably if circumvented.

The critical risks are data leakage in three forms (HMM regime labels fitted on full dataset using Viterbi decoding, feature construction touching P2 bars, and incremental OOS peeking via iterated autoresearch) and statistical integrity failures (undisclosed iteration counts that invalidate Bonferroni correction, P1a/P1b split chosen post-EDA, non-deterministic engine output). Every critical pitfall has a structural countermeasure in the architecture. Build order and verification gates exist specifically to ensure countermeasures are in place before the failure mode can occur.

## Key Findings

### Recommended Stack

The core science stack is Python 3.12 + pandas 2.2 + NumPy 2.1 + SciPy 1.14 + statsmodels 0.14. No ML experiment tracking platform (MLflow, W&B, Optuna) is warranted — the audit log and git commit history are the experiment record. No third-party backtest framework (vectorbt, Zipline, backtrader) is appropriate — the multi-leg partial exit logic requires a purpose-built engine with ~175-225 lines of Python. The hmmlearn library (0.3.3, pinned hard) is the only viable GaussianHMM option; it is in limited-maintenance mode with no replacement. ACSIL code generation for Sierra Chart is a text generation problem solved with Python f-strings or Jinja2 — not an API integration problem.

**Core technologies:**
- Python 3.12 + pandas 2.2 + NumPy 2.1: data manipulation and vectorized indicator computation — stable LTS combination with verified mutual compatibility
- SciPy 1.14 + statsmodels 0.14: statistical gates (permutation tests, Bonferroni correction via `multipletests`) — industry standard, both support pandas 2.x
- hmmlearn 0.3.3: GaussianHMM regime labeling — only maintained option, pin hard
- scikit-learn 1.5: feature scaling, BinnedScoringAdapter bin discretization — NumPy 2.x support added in 1.5
- pyarrow 17: Parquet read/write for all persisted data — ~10x faster than CSV, required by pandas `.to_parquet()`
- quantstats 0.0.64: HTML tearsheet generation for Stage 05 assessment — covers all reporting needs, avoids custom dashboard
- Git + bash: autoresearch keep/revert infrastructure, pre/post-commit hooks — the pipeline's integrity layer
- Jinja2 3.x: Sierra Chart ACSIL C++ code generation — appropriate for multi-leg exit logic with conditional blocks
- joblib 1.4: parallelizing overnight autoresearch loops — local parallelism without distributed task queue overhead

**Version constraints to respect:**
- Do NOT use pandas 3.0 (released January 2026) — hmmlearn and quantstats compatibility not yet verified
- Do NOT use NumPy 2.4 — potential ABI issues with hmmlearn C extensions
- Do NOT use Python 3.13+ — free-threading instability with scientific stack

### Expected Features

**Must have (table stakes — all required for Milestone 1):**
- IS/OOS data separation with structural holdout guard (`holdout_locked_P2.flag` + pre-commit hook + engine-level check)
- Instrument registry and period config as single sources of truth (NQ constants, P1/P2/P1a/P1b dates)
- Feature catalog with entry-time-only enforcement and canary tests
- HMM regime fitter producing `regime_labels.csv` (prerequisite for Stage 05 regime-conditioned assessment)
- Git infrastructure: autocommit.sh (30s watcher), pre-commit hook (holdout guard + audit + period rollover), post-commit hook (OOS_RUN + DEPLOYMENT_APPROVED)
- Backtest engine with dynamic archetype dispatch and verified determinism
- BinnedScoringAdapter with JSON scoring model and bin edges frozen from P1a calibration
- Bonferroni-adjusted iteration budgets encoded in `statistical_gates` config, hard-enforced by stage drivers
- Autoresearch drivers for Stages 02, 03, 04 (one-file-per-experiment pattern)
- P1a/P1b internal replication discipline (boundary pre-committed before any evaluation)
- Append-only audit log with pre-commit enforcement (modification, not just append, triggers rejection)
- Stage 05 assessment with feedback loop to `prior_results.md`
- Full ICM CONTEXT.md files for all 7 stages (≤80 lines, operative instruction in first 5 lines)

**Should have (differentiators, Milestone 2):**
- Stage 07 live monitoring with drift detection against backtest expectations
- Monte Carlo simulation layer for outcome distribution vs point estimates
- Bootstrap confidence intervals as supplement to parametric gates in small-sample regimes
- Dashboard beyond stub (requires first deployed strategy as trigger)

**Defer (v2+):**
- Multi-instrument support (ES, GC) — registry pattern makes this low-friction when NQ proves itself
- Additional archetypes (momentum, mean-reversion) — dynamic dispatch is ready, archetypes need their own feature evaluators
- Q7 multi-period IS analysis — requires P3 data (~June 2026)
- Cross-archetype portfolio optimization — requires fair comparison framework not yet designed

**Anti-features to explicitly reject (never build):**
- Multiple OOS runs on P2 — destroys holdout validity by design
- Interactive parameter tuning on OOS period — converts OOS into IS by definition
- Real-time streaming data — completely different engineering problem, not in scope for v1
- ML black-box feature selection — violates interpretability requirement
- Automated deployment without human approval gate

### Architecture Approach

The pipeline has a 5-layer architecture: agent identity (CLAUDE.md), stage routing (root CONTEXT.md), global factory config (_config/), cross-stage shared resources (shared/), and 7 sequential research stages. All inter-stage communication is through explicit file artifacts with human review gates between stages. The git infrastructure (autocommit.sh, pre/post-commit hooks) runs as an independent parallel layer providing audit trail and integrity enforcement without blocking research flow. The three-file autoresearch pattern (program.md steering doc / agent-editable file / fixed harness) applies identically to Stages 02, 03, and 04. Sierra Chart deployment (Stage 06) is a manual human-in-the-loop step with no automation.

**Major components:**
1. _config/ — global constants (instruments, periods, statistical gates, pipeline rules) configured once and locked; all downstream stages read from `data_manifest.json` generated by Stage 01, not from _config/ directly at runtime
2. shared/archetypes/ — per-archetype Python modules (feature_engine.py editable by agent, feature_evaluator.py fixed harness, simulator.py pure function); adding an archetype = adding a folder, no engine changes
3. shared/scoring_models/ — frozen scoring artifacts (bin_edges JSON + HMM pkl) with adapter interface; engine calls `adapter.score()` exclusively, never reads model internals
4. stages/04-backtest/backtest_engine.py — fixed evaluation harness (~175-225 lines); agent never edits this file; dynamic dispatch loads simulator via config string path; enforces holdout flag at startup
5. stages/04-backtest/p2_holdout/ — physical isolation of OOS data with `holdout_locked_P2.flag`; three independent enforcement layers (flag, pre-commit hook, engine-level abort)
6. audit/audit_log.md — append-only decision log written by hooks and audit_entry.sh; human and dashboard consumers only, never read by agents at runtime
7. .git/hooks/ — pre-commit (holdout guard, audit modification check, period rollover warning, program.md line count) + post-commit (OOS_RUN, DEPLOYMENT_APPROVED entries)
8. autocommit.sh — 30-second file watcher producing full experiment trail in git history; must be verified operational before first overnight run

### Critical Pitfalls

1. **HMM look-ahead leakage via Viterbi decoding** — Use filtered (forward algorithm) probabilities, not Viterbi/smoothed; fit HMM on P1-only data; serialize immediately; apply frozen model read-only to P2. Warning sign: single regime_labels.csv covering both P1 and P2 generated before P2 OOS initiated.

2. **Autoresearch OOS contamination via incremental peeking** — Autoresearch harness must evaluate exclusively on P1. Feature normalization constants (bin edges, volatility scalers) derived from P1a only and frozen before any loop begins. Pre-commit hook rejects any commit where P2 artifacts appear in evaluation output. Engine checks `holdout_locked_P2.flag` at import time, not only at commit time.

3. **p-Hacking via undisclosed iteration count** — Iteration budget must be a hard counter in the stage driver (reads from `statistical_gates` config, not `program.md`). Driver refuses to launch iteration N+1 when N equals budget. Bonferroni denominator equals the pre-declared budget, never the number of completed tests. Every hypothesis logged with monotonic ID before the test runs.

4. **Feature entry-time leakage via vectorized pandas operations** — Every feature consumed at entry must be computable from data with timestamps strictly before the signal bar's open. Canary test: `feature_at_t` equals value computed from `df[:t]`. IS Sharpe > 2.0 for signal-touch strategies is a warning sign requiring investigation.

5. **Non-deterministic backtest engine** — Mandatory acceptance criterion before Pass 3: two identical-config runs produce byte-for-byte identical trade ledgers. Sort DataFrames explicitly on (date, instrument, bar_index) before every operation. Fix all random seeds in config. Log library versions in each run artifact.

6. **Unrealistic fill model** — Minimum: 1-tick slippage per side + $4.50/contract round-trip commission. Net-of-cost Sharpe is the gate metric; gross metrics are informational only. Slippage constants live in the instrument registry, never inline in backtest code.

7. **program.md scope creep breaking one-file constraint** — Hard 30-line cap enforced by pre-commit hook. Harness files are agent-immutable (declared in CLAUDE.md). Evaluation metric declared in `statistical_gates` config, not in `program.md`. Agent cannot change what "good" means.

## Implications for Roadmap

Based on research, the architecture spec prescribes three sequential passes with hard gates between them. The roadmap should map directly to this build order — it is not a suggestion but a dependency graph derived from the integrity requirements.

### Phase 1: Scaffold — Config Layer, Stage Contracts, HMM, Git Infrastructure

**Rationale:** Every downstream component reads from _config/ and stage CONTEXT.md files. Nothing can be built correctly until the single sources of truth (period boundaries, instrument constants, statistical gates, pipeline rules) are committed and locked. The HMM fitter is mandatory here (not deferred) because regime labels enrich Stage 05 from the first assessment. Git hooks must be operational before any file changes accumulate.

**Delivers:** Full folder structure, CLAUDE.md (≤60 lines), root CONTEXT.md, all _config/ files, all 7 stage CONTEXT.md files, shared/ resources (feature_definitions.md, scoring_models dir + adapter, archetypes/ with exit_templates.md), hmm_regime_fitter.py + initial regime_labels.csv, data migration, audit stub, autocommit.sh, pre-commit hook (holdout guard + audit + period rollover warning + program.md line count), post-commit hook (OOS_RUN + DEPLOYMENT_APPROVED).

**Must lock before closing:** P1a/P1b split boundary committed to period_config before any Stage 04 evaluation ever runs (verifiable via git log timestamp ordering).

**Addresses:** IS/OOS data separation (structural), data registry + period config, feature catalog skeleton, HMM regime fitter, git infrastructure.

**Critical verifications:** `chmod +x` both hooks. Simulate a P2-path commit attempt and confirm pre-commit rejection. Wait 30s after a file change and confirm autocommit fires in git log.

**Pitfalls to avoid:** HMM Viterbi leakage (Pitfall 1), period_config mutation (Pitfall 8), P1a/P1b split contamination (Pitfall 9), program.md scope creep (Pitfall 7).

### Phase 2: Backtest Engine — Deterministic, Validated, End-to-End Gated

**Rationale:** The engine is the fixed harness that all autoresearch loops run against. It must be correct and deterministic before any overnight run touches it. Debugging a non-deterministic engine mid-autoresearch is high-cost and invalidates accumulated results. The architecture spec requires a manual end-to-end pass (01→04→05) as an explicit gate before Pass 3 begins.

**Delivers:** backtest_engine_qa.md (Q1-Q6 committed first as audit artifact), data_loader.py with all hardcoded paths parameterized, backtest_engine.py (~175-225 lines, dynamic dispatch, holdout flag enforcement), config_schema.json + config_schema.md, BinnedScoringAdapter with frozen bin edges from P1a, simulation_rules.md documenting fill model, manual end-to-end verification.

**Addresses:** Backtest engine with dynamic archetype dispatch, BinnedScoringAdapter + frozen bins, deterministic replay, slippage and commission modeling, multi-leg exit modeling (signal-touch simulator).

**Must verify before Phase 3:** Two identical-config runs produce byte-identical trade ledgers. Net-of-cost Sharpe < 80% of gross Sharpe confirms realistic cost modeling. Manual 01→04→05 pass succeeds with interpretable output.

**Pitfalls to avoid:** Non-deterministic engine (Pitfall 5), unrealistic fill model (Pitfall 6), feature entry-time leakage (Pitfall 4), autoresearch OOS contamination via data_loader missing end_date guard (Pitfall 2).

### Phase 3: Autoresearch Loops — Stage 04, Then 02, Then 03, Feedback Loop Last

**Rationale:** Stage 04 (exit parameter optimization) is the most constrained search space and depends only on the engine from Phase 2 — lowest risk, easiest to verify. Stage 02 (feature engineering) requires the feature_evaluator.py dispatcher and introduces broader search. Stage 03 (hypothesis generation) depends on both a stable feature set and a working backtest engine. Running them out of order creates attribution ambiguity. The feedback loop (Stage 05 → prior_results.md → Stage 03) is wired last because it depends on Stage 03 being independently operational first.

**Delivers (in order):**
- Stage 04 driver with hard iteration budget counter, keep/revert logic, TSV output, Bonferroni enforcement — overnight test confirms operational
- evaluate_features.py dispatcher + Stage 02 driver + overnight test confirming spread computation and entry-time enforcement
- hypothesis_generator.py + Stage 03 driver + overnight test
- Feedback loop: Stage 05 assessment output auto-copied to Stage 03 prior_results.md (loop closed)
- Full autoresearch cycle operational: human writes program.md → overnight run → human reviews results.tsv → promotes or adjusts direction

**Addresses:** Autoresearch loop (Stages 02, 03, 04), Bonferroni-adjusted iteration budgets (structurally enforced), feedback loop (Stage 05 → Stage 03), append-only audit log enforcement, Karpathy keep/revert pattern.

**Pitfalls to avoid:** Undisclosed iteration count / p-hacking (Pitfall 3), autoresearch OOS contamination (Pitfall 2), program.md scope creep (Pitfall 7), parallel stage execution (stages must run sequentially 02→03→04 per pass, with human review gates between stages).

### Phase 4: Stage 05 Assessment and Stage 06 Deployment (Post First P1b Pass)

**Rationale:** Assessment is deterministic (no autoresearch), so its implementation is straightforward once the backtest engine exists. Deployment (ACSIL code generation) is a manual human-in-the-loop stage that depends on a validated strategy reaching frozen_params.json. These stages are lower implementation risk than the autoresearch infrastructure but cannot be exercised until at least one strategy passes P1b replication.

**Delivers:** Stage 05 assessment (statistical verdict with regime breakdown, MWU, permutation tests, quantstats tearsheet), verdict_report.json feeding dashboard/results_master.tsv, Stage 06 assemble_context.sh + ACSIL code generation via Claude Code, alignment_test.py (ZB4 vs ZRA comparison), deployment_ready.flag (human-created), deployment lineage from hypothesis to commit.

**Addresses:** Full lineage from hypothesis to deployment, quantstats tearsheet, human approval gate before live capital.

**Pitfalls to avoid:** Scoring model recalibration on P2 data (Pitfall 6 variant), multiple OOS runs on P2 (anti-feature), automated deployment without human approval (anti-feature).

### Phase 5: P2 OOS One-Shot and Milestone 2 Features (Post First Validated Deployment)

**Rationale:** P2 OOS is a one-time event per strategy — it cannot be planned until Phase 3/4 have produced a P1b-passing candidate. Milestone 2 features (Stage 07 live monitoring, dashboard beyond stub, Monte Carlo) all trigger on the existence of a deployed live strategy.

**Delivers:** P2 one-shot OOS run (single execution, holdout_locked_P2.flag written), P2 verdict report, Stage 07 live monitoring with drift detection against backtest expectations, dashboard filterable view, Monte Carlo simulation layer, bootstrap confidence intervals.

**Addresses:** Stage 07 live monitoring, dashboard beyond stub, Monte Carlo simulation, full IS/OOS validation cycle completed.

### Phase Ordering Rationale

- Config layer must precede engine because the engine reads from config; config must precede hooks because hooks guard config integrity
- Engine must precede autoresearch loops because the loops depend on the engine as their fixed evaluation harness
- Stage 04 loop before 02 and 03 because its output (frozen_params.json) is the most tightly scoped; failures are attributable to exit params only, not feature set instability
- Stage 02 before Stage 03 because frozen_features.json is a Stage 03 input — running them in parallel creates a moving target
- Stage 05 assessment before Stage 06 deployment because assessment produces the statistical verdict that gates deployment
- P2 OOS last because it is a one-shot event that can only be consumed once; must occur only after all IS research is complete

### Research Flags

Phases where deeper research may be needed during planning:

- **Phase 2 (Backtest Engine):** The Q1-Q6 pre-answers in the architecture spec resolve most design questions, but the exact bar_offset parameterization for the signal-touch simulator (ensuring entry occurs on the bar after the signal, not the signal bar) warrants a dedicated review of the architecture spec's Q&A section before coding begins.
- **Phase 3 (Stage 02 feature engineering):** The feature_evaluator.py dispatcher and MWU spread computation for signal-touch features involve domain-specific thresholds (spread > 0.15, MWU p < 0.10) that should be validated against the project's actual touch distribution before the overnight budget is consumed.
- **Phase 4 (ACSIL code generation):** Sierra Chart ACSIL is Windows-only C++ with no automated test environment. The alignment_test.py (ZB4 vs ZRA comparison) is the only automated verification; the code generation template logic for multi-leg exits should be drafted and manually reviewed against the ACSIL reference (M1B_AutoTrader.cpp) before the first live compile attempt.

Phases with well-documented patterns where additional research is not needed:

- **Phase 1 (Scaffold):** Architecture spec is authoritative and complete; folder structure, CONTEXT.md format, and hook logic are fully specified
- **Phase 2 (Engine determinism verification):** Two-run diff test is standard and implementation is trivial once the engine is written
- **Phase 3 (keep/revert loop):** Karpathy pattern is a primary source (630-line single-file Python); the implementation is straightforward given the driver structure in the architecture spec

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | MEDIUM-HIGH | Core Python science stack is HIGH; hmmlearn limited-maintenance status adds risk; pandas 3.0/NumPy 2.x compatibility matrix needs monitoring as ecosystem evolves |
| Features | HIGH | Feature list derived from peer-reviewed sources + authoritative project spec; table stakes list is complete and well-precedented in quant literature |
| Architecture | HIGH | Derived directly from authoritative project specs (Futures_Pipeline_Architecture_ICM.md v2026-03-13, Futures_Pipeline_Functional_Spec.md v1.0); no inference required |
| Pitfalls | HIGH | Critical pitfalls verified across multiple peer-reviewed sources; domain-specific items (ACSIL, signal-touch fill model) at MEDIUM due to fewer external references |

**Overall confidence:** HIGH

### Gaps to Address

- **hmmlearn replacement risk:** hmmlearn 0.3.3 is in limited-maintenance mode. If a critical NumPy ABI incompatibility emerges with a future NumPy release, there is no drop-in replacement for GaussianHMM. Address during Phase 1 planning by pinning the full dependency tree and adding a CI check that verifies hmmlearn imports correctly with the pinned NumPy version.
- **ACSIL template coverage:** The pipeline generates C++ from Python templates, but the specific ACSIL API calls for multi-leg exits (partial position sizing, trailing stop ATR logic, time-cap exit) have no external validation path short of Sierra Chart compilation. The `templates/acsil/` canonical snippet library (referenced in STACK.md) must be built and manually verified before Stage 06 autogeneration is trusted for real capital deployment.
- **Signal-touch fill model calibration:** The 1-tick slippage + $4.50 commission assumption is a conservative floor, but the actual fill rate for limit orders at touch price during high-volatility NQ conditions may require backtesting against live trade records once Stage 07 produces data. This is a Milestone 2 calibration task, not a blocker for Milestone 1.
- **Quantstats pandas 2.x compatibility:** Noted in STACK.md as "verify on install." Add a smoke test (generate a tearsheet from synthetic returns data) to the Phase 2 acceptance criteria to catch compatibility issues before Stage 05 assessment depends on it.

## Sources

### Primary (HIGH confidence)
- `C:/Projects/pipeline/Futures_Pipeline_Architecture_ICM.md` (v2026-03-13) — all stage contracts, autoresearch loop design, ICM file constraints, extensibility conventions
- `C:/Projects/pipeline/Futures_Pipeline_Functional_Spec.md` (v1.0, 2026-03-11) — master build checklist, Pass 1/1.5/2/3 task specs, Q1-Q6 answers
- `C:/Projects/pipeline/.planning/PROJECT.md` — active requirements, build order, key decisions
- arXiv:2512.12924 "Interpretable Hypothesis-Driven Trading: Walk-Forward Validation" — IS/OOS discipline, Bonferroni gates, internal replication
- arXiv:2510.18569 "QuantEvolve: Automating Quantitative Strategy Discovery" — autoresearch pattern applied to trading
- karpathy/autoresearch GitHub — primary source for keep/revert loop pattern (630-line single-file Python, verified March 6 2026)
- Bailey et al., "Backtest Overfitting in Financial Markets" — peer-reviewed; p-hacking, multiple testing
- QuantStart HMM regime detection article — practitioner implementation of GaussianHMM for regime labeling
- Sierra Chart ACSIL docs — C++ only, no Python bindings; Build with Visual C++ confirmed

### Secondary (MEDIUM confidence)
- QuantStart walk-forward analysis — IS/OOS pattern validation
- QuantConnect Slippage/Fill Model docs — slippage modeling for futures
- kingy.ai autoresearch analysis — secondary analysis of Karpathy pattern
- Medium: "The Hidden Trap in Algorithmic Trading: Data Leakage" — feature leakage taxonomy
- Hybrid Horizons: "The Frozen Metric of Autoresearch" — evaluation harness immutability rationale
- mathinvestor.org: "P-Hacking and Backtest Overfitting" — iteration budget / Bonferroni connection

### Tertiary (LOW confidence)
- Medium: "Ultimate Python Quant Trading Ecosystem 2025" — ecosystem survey confirming standard stack (single community source, no peer review)

---
*Research completed: 2026-03-13*
*Ready for roadmap: yes*
