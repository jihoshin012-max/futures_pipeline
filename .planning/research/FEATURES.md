# Feature Research

**Domain:** Futures trading strategy research pipeline (NQ, signal-touch archetype)
**Researched:** 2026-03-13
**Confidence:** HIGH (domain well-established; specific autoresearch+trading pipeline combination is novel but components are individually well-documented)

---

## Feature Landscape

### Table Stakes (Users Expect These)

Features a quant researcher assumes exist in any credible pipeline. Missing these makes the pipeline feel amateur or dangerous.

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| IS/OOS data separation with holdout guard | Foundation of any honest backtest; without it results are meaningless | MEDIUM | Must be structural enforcement, not convention. Pre-commit hook + engine flag (`holdout_locked_P2.flag`) is the right pattern. |
| Lookahead bias prevention | Researchers assume any production system enforces entry-time-only feature access | MEDIUM | All features must be computable from data available at bar-close before entry. Requires explicit validation in feature catalog. |
| Slippage and commission modeling | Backtest P&L without friction is fiction | LOW | For NQ futures: per-contract commission + 1-tick slippage minimum. Must be configurable per instrument. |
| Deterministic backtest replay | Results must be reproducible bit-for-bit across runs | MEDIUM | Fixed random seeds, ordered execution, no floating-point nondeterminism from parallelism. |
| Structured audit log | Experiment → decision traceability is expected in any professional pipeline | MEDIUM | Append-only. Every hypothesis evaluated, every parameter frozen, every OOS run recorded. Never editable. |
| Data registry with instrument constants | Point value, tick size, session hours must come from one authoritative source | LOW | NQ: $20/point, 0.25 tick. Config file, never hardcoded. Registry prevents per-file divergence. |
| Period configuration (IS/OOS date ranges) | Researcher must know which data is live and which is holdout | LOW | Single config drives all stage ingestion. Period rollover warning in pre-commit hook. |
| Feature catalog with definitions | Researchers expect documented, versioned feature definitions | MEDIUM | `feature_definitions.md` + `feature_catalog` + `feature_rules.md`. Prevents silent feature drift between runs. |
| Statistical significance gating | Any pipeline without p-value gates is just exploratory | MEDIUM | Minimum: two-sided t-test with explicit p-value. Bonferroni adjustment mandatory when running multiple hypotheses. |
| Multi-leg exit modeling | Signal-touch archetype requires partial exits, trail steps, and time cap | HIGH | Vectorized multi-leg logic is non-trivial. Must handle partial fills, trailing stops, time-based exits in same engine. |
| Backtest performance metrics | Sharpe, max drawdown, win rate, avg winner/loser, trade count | LOW | Without these, there is nothing to gate on. Drawdown gate as multiple of avg winner is the specific constraint here. |
| Scored entry system | BinnedScoringAdapter expects JSON model with frozen bin_edges | MEDIUM | Score → position size or go/no-go decision. Bin edges must be frozen from P1, not refit on P2. |
| Git-based experiment versioning | Each experiment state must be recoverable | LOW | Strategy configs, results, and model artifacts committed at each stage gate. autocommit.sh pattern. |

### Differentiators (Competitive Advantage)

Features that separate a rigorous pipeline from a notebook-and-gut-feel approach. These are where this project competes on research quality.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Karpathy autoresearch keep/revert loop | Autonomous overnight experimentation with human morning review. Compress weeks of manual iteration into hours. | HIGH | `program.md` steers agent direction. Agent edits one file, fixed harness evaluates, ratchets on improvement. Approximately 100 experiments per overnight run. |
| Internal P1a/P1b replication discipline | Strategies must replicate internally before consuming OOS. Eliminates most false discoveries before they reach P2. | HIGH | P1a calibrates, P1b replicates with frozen parameters. Only P1b-passing strategies proceed. This is rare in practitioner pipelines. |
| Bonferroni-adjusted iteration budgets | Structural enforcement of multiple testing control. Not a convention — baked into statistical_gates config. | MEDIUM | Budget per stage limits total hypotheses tested. Adjusted alpha = 0.05 / N_tests. Prevents p-hacking by exhaustion. |
| HMM regime labeling | Regime-conditioned strategy evaluation. Strategies that only work in one regime are flagged before deployment. | HIGH | Fits HMM on P1+P2, produces `regime_labels.csv`. Serialized model enables consistent labeling across periods. |
| ICM context methodology (RinDig pattern) | Structured context files enforce agent reading discipline. Prevents lost-in-middle failures for large pipelines. | MEDIUM | CLAUDE.md ≤60 lines, CONTEXT.md ≤80 lines, program.md ≤30 lines. Operative instruction in first 5 lines. This keeps agent context clean across 7 stages. |
| Dynamic archetype dispatch | New strategy archetype = new simulator module, zero engine changes. | HIGH | `backtest_engine.py` dynamically dispatches to archetype-specific simulator. Signal-touch is v1; architecture accommodates ES, GC, momentum without engine rewrites. |
| Feedback loop from assessment to hypothesis | Stage 05 assessment results feed `prior_results.md` which informs Stage 03 hypothesis generation. | HIGH | Closes the research loop. Prevents re-testing failed ideas. Accumulates institutional memory across overnight runs. |
| Append-only audit with pre-commit enforcement | Cannot modify audit log even by accident. Git hook enforces. | MEDIUM | Pre-commit rejects commits that modify (vs append to) `audit_log.md`. OOS run and deployment approval written by post-commit hook. |
| Scoring model with frozen bin edges | BinnedScoringAdapter stores calibrated bins from P1 as JSON artifact. No refitting on OOS data. | MEDIUM | Enforces that the scoring model used in P2 is exactly the model validated in P1b. Frozen artifact is committed before holdout unlock. |
| Overnight-steerable via program.md | Human writes a 30-line markdown file before sleep; agent executes all night; human reviews results in morning. | MEDIUM | Operationalizes the research cycle. Human leverage ratio: 1 hour of direction → 8 hours of machine execution. |
| Full lineage from hypothesis to deployment | Every deployed strategy traces back to: hypothesis text, P1a result, P1b replication, P2 OOS run, and deployment commit. | HIGH | Audit log + git log + stage artifacts together constitute the lineage. No unaudited shortcuts. |

### Anti-Features (Commonly Requested, Often Problematic)

Features that seem useful but undermine pipeline integrity or create complexity without proportionate value.

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|-----------------|-------------|
| Multiple OOS runs on P2 data | "I just want to check one more thing" | Destroys OOS validity. Each additional look inflates familywise error rate. P2 is one-shot by design. | Run on P1 subdivisions. Save P2 for final validation only. |
| Interactive parameter tuning on OOS period | Faster iteration on live data | Parameters tuned on OOS become IS parameters. The strategy is now overfit to the future. | Freeze parameters in P1b. If OOS fails, start a new strategy — don't adjust. |
| Real-time streaming data integration | "Why not make it live?" | Completely different engineering problem. Adds latency concerns, websocket infrastructure, and failure modes unrelated to research validity. | Batch pipeline only for v1. Streaming is a Milestone 3+ problem. |
| Dashboard beyond stub | Visual appeal, demo-ability | Different skill set (frontend JS), zero pipeline dependency, creates premature commitment to UI before research workflow is validated. | Dashboard deferred to Milestone 2 with its own spec. Stub is sufficient placeholder. |
| Multi-instrument support (ES, GC) in v1 | More data = more signal | Multiplies data management complexity and dilutes focus. NQ signal-touch needs to prove itself first. | NQ only for v1. Registry pattern makes adding instruments later low-friction. |
| ML black-box feature selection | Automated feature discovery sounds efficient | Violates the interpretability requirement. Features selected by black-box cannot be audited or explain why a strategy works. | Hand-specified feature catalog with explicit rationale. Autoresearch explores combinations, not definitions. |
| Global parameter optimization (grid search over P1+P2) | "Find the best parameters" | Classic overfitting. Parameters that maximize performance over the full IS period will be overfit. | P1a calibration with explicit iteration budget. P1b replication with frozen parameters. |
| Soft OOS enforcement (warning, not block) | "Trust the researcher" | The value of a holdout is precisely that it cannot be contaminated. Soft enforcement becomes no enforcement under pressure. | Hard structural block: `holdout_locked_P2.flag` checked by engine and pre-commit hook. |
| Strategy performance ranking across archetypes in v1 | Seems like good portfolio thinking | Comparing signal-touch vs other archetypes requires a fair comparison framework that doesn't exist yet. Premature optimization. | Score within archetype only. Cross-archetype comparison is Milestone 3+. |
| Automated deployment without human approval | "Why not full automation?" | Removes the human-in-the-loop checkpoint that protects against automation errors propagating to live capital. | Post-commit hook writes OOS_RUN and requires explicit DEPLOYMENT_APPROVED entry before live. |

---

## Feature Dependencies

```
[IS/OOS Data Separation + holdout_locked flag]
    └──required by──> [P2 OOS One-Shot Run]
    └──required by──> [P1a/P1b Internal Replication]
                          └──required by──> [Scoring Model with Frozen Bins]
                                                └──required by──> [P2 OOS One-Shot Run]

[Data Registry + Period Config]
    └──required by──> [Feature Catalog]
                          └──required by──> [Backtest Engine]
                                                └──required by──> [IS/OOS Separation]

[HMM Regime Fitter]
    └──required by──> [Regime-Conditioned Evaluation in Stage 05]
    └──enhances──> [Hypothesis Generator (Stage 03)]

[Backtest Engine with Dynamic Dispatch]
    └──required by──> [Autoresearch Keep/Revert Loop]
    └──required by──> [Bonferroni Budget Enforcement]

[Stage 05 Assessment (feedback)]
    └──feeds──> [prior_results.md]
                    └──feeds──> [Stage 03 Hypothesis Generator]
                                    └──feeds──> [Autoresearch Loop]

[Append-Only Audit Log]
    └──required by──> [Deployment Lineage]
    └──enforced by──> [Pre-Commit Hook]
                          └──also enforces──> [Holdout Guard]
                          └──also enforces──> [Period Rollover Warning]

[Autoresearch Loop (Stage 04 feature eval)]
    └──feeds──> [Autoresearch Loop (Stage 02 feature discovery)]
                    └──feeds──> [Autoresearch Loop (Stage 03 hypothesis)]
```

### Dependency Notes

- **Holdout guard requires structural enforcement:** Pre-commit hook and engine guard are co-dependencies. Either alone can be bypassed; together they create defense-in-depth.
- **HMM regime fitter is a prerequisite for Stage 05 assessment:** Assessment without regime conditioning produces misleading aggregate statistics for regime-sensitive strategies.
- **Frozen bin edges require P1a/P1b split:** Cannot freeze scoring model bins until P1b replication confirms the model generalizes within IS. Freezing after P1a only risks overfit scoring.
- **Feedback loop depends on Stage 05 format consistency:** `prior_results.md` schema must remain stable so Stage 03 can reliably ingest it. Schema changes break the loop.
- **Stage 04 must precede Stage 02:** Feature evaluation (04) informs which features are worth combining in hypotheses (02). Running hypothesis generation before feature evaluation wastes iteration budget.

---

## MVP Definition

### Launch With (v1 — Milestone 1)

Minimum viable pipeline: proves a strategy can be researched, validated, and deployed with full lineage.

- [x] IS/OOS data separation with structural holdout guard (holdout_locked_P2.flag)
- [x] Instrument registry and period config (NQ constants, P1/P2 dates)
- [x] Feature catalog with definitions and rules (entry-time-only enforcement)
- [x] HMM regime fitter producing regime_labels.csv (prerequisite for Stage 05)
- [x] Git infrastructure: autocommit.sh, pre-commit hook (holdout + audit + rollover), post-commit hook (OOS_RUN + DEPLOYMENT_APPROVED)
- [x] Backtest engine with dynamic archetype dispatch (~175-225 lines, signal-touch simulator)
- [x] BinnedScoringAdapter with JSON scoring model and frozen bin edges
- [x] Bonferroni-adjusted statistical gates in pipeline_rules config
- [x] Autoresearch drivers for Stages 02, 03, 04 (overnight loop operational)
- [x] Stage 05 assessment feeding prior_results.md (feedback loop closed)
- [x] Append-only audit log with pre-commit enforcement
- [x] Full 7-stage CONTEXT.md files (agent reading discipline)

### Add After Validation (v1.x — Milestone 2)

Features to add once the research cycle has produced at least one validated, deployed strategy.

- [ ] Dashboard beyond stub — trigger: first deployed strategy needs monitoring visibility
- [ ] Stage 07 live monitoring — trigger: first live deployment (pipeline starts empty, monitoring begins after first deployment)
- [ ] Monte Carlo simulation layer — trigger: need distribution of outcomes, not just point estimates
- [ ] Bootstrap confidence intervals as supplement to parametric p-value gates — trigger: small sample sizes in specific regimes reveal parametric test weakness

### Future Consideration (v2+)

Features to defer until multiple strategies have been validated and the pipeline's workflow is proven.

- [ ] Multi-instrument support (ES, GC) — defer: NQ pipeline must prove end-to-end first; registry pattern makes extension low-friction later
- [ ] Multiple archetypes (momentum, mean-reversion) — defer: signal-touch archetype must be fully exercised; dynamic dispatch is ready but archetypes need their own feature evaluators
- [ ] Cross-archetype portfolio optimization — defer: requires fair comparison framework that doesn't exist yet
- [ ] Reinforcement learning signal generation — defer: interpretability requirement conflicts with RL black-box; only relevant if signal-touch archetype proves insufficient
- [ ] Q7 multi-period IS combined pool vs separate folds — defer: requires P3 data (arrives ~Jun 2026)

---

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority |
|---------|------------|---------------------|----------|
| IS/OOS holdout guard (structural) | HIGH | MEDIUM | P1 |
| Data registry + period config | HIGH | LOW | P1 |
| Feature catalog with entry-time enforcement | HIGH | MEDIUM | P1 |
| HMM regime fitter | HIGH | HIGH | P1 (prerequisite for Stage 05) |
| Git hooks (pre/post-commit) | HIGH | MEDIUM | P1 |
| Backtest engine with dynamic dispatch | HIGH | HIGH | P1 |
| BinnedScoringAdapter + frozen bins | HIGH | MEDIUM | P1 |
| Bonferroni gates in config | HIGH | LOW | P1 |
| Autoresearch loop (Stages 02, 03, 04) | HIGH | HIGH | P1 |
| P1a/P1b internal replication | HIGH | MEDIUM | P1 |
| Append-only audit log + enforcement | HIGH | MEDIUM | P1 |
| Feedback loop (Stage 05 → prior_results → Stage 03) | HIGH | MEDIUM | P1 |
| ICM context files (all 7 stages) | HIGH | MEDIUM | P1 |
| Stage 07 live monitoring | HIGH | HIGH | P2 (post first deployment) |
| Dashboard (beyond stub) | MEDIUM | HIGH | P2 (Milestone 2) |
| Monte Carlo simulation | MEDIUM | MEDIUM | P2 |
| Bootstrap confidence intervals | MEDIUM | MEDIUM | P2 |
| Multi-instrument support | MEDIUM | HIGH | P3 |
| Additional archetypes | MEDIUM | HIGH | P3 |
| Q7 multi-period IS analysis | LOW | HIGH | P3 (data not available until Jun 2026) |

**Priority key:**
- P1: Must have for Milestone 1 (research pipeline operational)
- P2: Should have after first validated deployment
- P3: Future consideration (v2+)

---

## Competitor Feature Analysis

This pipeline's primary "competitors" are informal practitioner approaches and open-source frameworks. The differentiator is structural rigor, not breadth.

| Feature | Practitioner Notebook Approach | Open-Source Frameworks (Zipline, Backtrader, VectorBT) | This Pipeline |
|---------|-------------------------------|-------------------------------------------------------|---------------|
| IS/OOS enforcement | Convention only, easily violated | Configurable but not structurally enforced | Structural via pre-commit hook + engine flag |
| Multiple testing control | Rarely applied | Not built-in | Bonferroni in config, iteration budget per stage |
| Internal replication | Almost never done | Not supported | P1a/P1b split as first-class pipeline concept |
| Overnight autoresearch | Manual iteration | Not applicable | Karpathy keep/revert loop with program.md steering |
| Regime conditioning | Ad hoc | Available but manual | HMM fitter produces labels; Stage 05 stratifies by regime |
| Audit lineage | None | Basic logging | Append-only audit_log.md with git commit enforcement |
| Scored entry system | Manual logic | Not standard | BinnedScoringAdapter with frozen JSON artifact |
| Multi-leg exit modeling | Manual implementation | Basic order types | Archetype-specific simulator with partial fills, trail steps, time cap |
| Context discipline for agents | N/A | N/A | ICM CONTEXT.md files, 60/80/30 line limits |

---

## Sources

- Interpretable Hypothesis-Driven Trading: Rigorous Walk-Forward Validation Framework — [arxiv.org/html/2512.12924v1](https://arxiv.org/html/2512.12924v1) (HIGH confidence — peer-reviewed, directly relevant)
- QuantEvolve: Automating Quantitative Strategy Discovery — [arxiv.org/html/2510.18569v1](https://arxiv.org/html/2510.18569v1) (HIGH confidence — peer-reviewed, autoresearch pattern applied to trading)
- Karpathy autoresearch GitHub and community analysis — [github.com/karpathy/autoresearch](https://github.com/karpathy/autoresearch) (HIGH confidence — primary source)
- Karpathy autoresearch pattern explanation — [kingy.ai/ai/autoresearch-karpathys-minimal-agent-loop](https://kingy.ai/ai/autoresearch-karpathys-minimal-agent-loop/) (MEDIUM confidence — secondary analysis)
- Market Regime Detection using HMM in QSTrader — [quantstart.com/articles/market-regime-detection-using-hidden-markov-models-in-qstrader/](https://www.quantstart.com/articles/market-regime-detection-using-hidden-markov-models-in-qstrader/) (HIGH confidence — practitioner implementation guide)
- Walk-Forward Analysis — Interactive Brokers — [interactivebrokers.com/campus/ibkr-quant-news/the-future-of-backtesting-a-deep-dive-into-walk-forward-analysis/](https://www.interactivebrokers.com/campus/ibkr-quant-news/the-future-of-backtesting-a-deep-dive-into-walk-forward-analysis/) (MEDIUM confidence — practitioner source)
- Backtesting Algorithmic Futures Strategies — QuantStrategy.io — [quantstrategy.io/blog/backtesting-algorithmic-futures-strategies-avoiding-curve/](https://quantstrategy.io/blog/backtesting-algorithmic-futures-strategies-avoiding-curve/) (MEDIUM confidence — practitioner source)
- PROJECT.md — C:/Projects/pipeline/.planning/PROJECT.md (HIGH confidence — authoritative project spec)

---

*Feature research for: Futures trading strategy research pipeline (NQ signal-touch)*
*Researched: 2026-03-13*
