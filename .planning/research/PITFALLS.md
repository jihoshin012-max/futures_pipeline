# Pitfalls Research

**Domain:** Futures trading strategy research pipeline (NQ, signal-touch archetype, IS/OOS discipline, autoresearch loop)
**Researched:** 2026-03-13
**Confidence:** HIGH (critical pitfalls verified across multiple sources; domain-specific items HIGH/MEDIUM)

---

## Critical Pitfalls

### Pitfall 1: HMM Regime Model Fitted on Full Dataset (Look-Ahead Leakage via Regime Labels)

**What goes wrong:**
The HMM is trained on the combined P1+P2 dataset to produce `regime_labels.csv`, but those labels are consumed during P1 calibration and P1a/P1b split. If the HMM was fit with Viterbi (smoothed/global path) rather than filtered (causal, forward-only) probabilities, every P1 label contains information from P2 — a form of look-ahead leakage that inflates apparent edge during IS and destroys OOS validity.

**Why it happens:**
HMM libraries default to Viterbi decoding (globally optimal path over the entire sequence). It is the more intuitive output and produces cleaner regime assignments. Practitioners see "IS and P2 covered" and proceed without checking whether the decoder used is causal. The distinction between filtered (forward algorithm, causal) and smoothed (forward-backward, non-causal) outputs is rarely emphasized in tutorials.

**How to avoid:**
- Use filtered (forward algorithm) probabilities exclusively for any label consumed in strategy logic or feature construction.
- Fit the HMM only on P1 data. If you need P2 regime labels for post-hoc OOS analysis, apply the frozen P1-fitted model to P2 using filtered inference — never refit on P2 data before the one-shot run.
- Serialize the fitted model immediately after P1-only training; load it read-only for all subsequent uses.
- Document in `hmm_regime_fitter.py` which decoder is used and why.

**Warning signs:**
- HMM training call uses the full concatenated dataset as input.
- `regime_labels.csv` generated as a single file covering both P1 and P2 before P2 OOS is initiated.
- Strategy performance degrades sharply between P1b and P2 for regime-conditioned signals specifically.
- Viterbi or `decode()` method used in production label generation rather than `predict_proba()` / forward pass.

**Phase to address:**
Pass 1 scaffold — `hmm_regime_fitter.py` spec and `period_config` must encode the P1-only fit boundary. Verify in Pass 1.5 pre-commit hook that regime label generation cannot silently consume P2 data.

---

### Pitfall 2: Autoresearch Loop Contaminates the OOS Period via Incremental Peeking

**What goes wrong:**
The Karpathy keep/revert loop runs many overnight experiments. If the harness evaluates even one metric that touches P2 data — even indirectly through shared feature normalization constants, regime labels, or scoring bin edges computed over both periods — every iteration has, in aggregate, optimized toward P2. The pipeline's "one-shot OOS" guarantee is void even though no single run consciously "used" P2.

**Why it happens:**
In ML autoresearch the validation set is fixed and small; any leakage affects only that set. In a trading pipeline the "validation set" is the OOS period (P2), which is also the _deployment gate_. Each nightly loop that computes features jointly across P1+P2 before splitting is equivalent to repeatedly peeking at P2 in small doses, which compounds over hundreds of runs.

**How to avoid:**
- The autoresearch harness must evaluate exclusively on P1 (P1b as the internal replicate). P2 data files must not be on the Python path during overnight runs.
- `holdout_locked_P2.flag` must be checked by the backtest engine at import time, not just at commit time.
- Feature engineering constants (bin edges, normalization stats, volatility scalers) must be derived from P1a training data only and frozen before any evaluation loop begins.
- The pre-commit hook should reject any commit where P2 data appears in experiment output artifacts.

**Warning signs:**
- `data_loader.py` accepts a single date range covering both P1 and P2 without a hard guard.
- Feature `fit()` calls reference DataFrames that include rows past `2025-12-14`.
- BinnedScoringAdapter bin edges computed on the full dataset before the P1/P2 split.
- Autoresearch loop log shows P2-period rows in any evaluation DataFrame.

**Phase to address:**
Pass 1.5 git infrastructure — `holdout_locked_P2.flag` creation, pre-commit engine guard, data_loader parameterization. Must be verified end-to-end before the autoresearch loop in Pass 3 is activated.

---

### Pitfall 3: p-Hacking via Undisclosed Iteration Count (False Statistical Significance)

**What goes wrong:**
The pipeline applies Bonferroni-adjusted p-value gates. But Bonferroni requires knowing the total number of hypotheses tested. If the iteration budget per stage is not enforced structurally (only by convention), an agent running 200 feature evaluations where the budget is 20 inflates the effective alpha by 10×. The surviving strategy appears significant at the declared threshold but is not.

**Why it happens:**
Iteration budgets feel like soft limits. The agent (or human operator) sees "almost significant" results at iteration 18 and runs 2 more. Or the overnight loop runs to completion regardless of how many hypotheses it has tested. Nothing structurally stops this.

**How to avoid:**
- Encode the iteration budget as a hard counter in the stage driver, not a config comment. The driver must refuse to launch iteration N+1 when N equals the budget.
- Log every hypothesis evaluated with a monotonically incrementing ID in the append-only audit log before the test runs, not after.
- Bonferroni correction denominator must equal the declared budget, not the number of tests that "survived" preliminary screening.
- Define the budget in `statistical_gates` config and reference it from the driver — no inline constants.

**Warning signs:**
- Stage 04 or Stage 03 drivers have a `max_iterations` parameter that is read from a config file that the agent can edit.
- Audit log entries for the same stage span more experiment IDs than the declared budget.
- p-value gate is applied to the best-of-N result where N was not pre-registered.

**Phase to address:**
Pass 3 autoresearch loops — stage drivers for Stages 04, 02, 03. Budget counter and Bonferroni denominator must be locked before any overnight run.

---

### Pitfall 4: Feature Leakage via Entry-Time Discipline Violations

**What goes wrong:**
A feature computed at bar close uses information that would not be available until after the bar closes in live trading — e.g., the high/low of the current 1-min bar used to generate a signal at the open of that bar, or a rolling statistic computed with `min_periods=1` that implicitly uses a future bar's data during the first window. The strategy shows unrealistic IS performance that cannot be replicated live.

**Why it happens:**
Vectorized pandas operations are natural but dangerous. `df['feature'] = df['col'].rolling(20).mean()` at row T uses rows T-19 through T, which is correct. But `shift(1)` mistakes, `fillna(method='ffill')` applied before the split, or using `df.resample().agg()` without `.shift(1)` all smuggle future information in ways that look plausible in code review.

**How to avoid:**
- Rule: every feature consumed at entry time must be computable using only data with timestamps strictly less than the signal bar's open.
- Write a canary test: for each feature, assert that `feature_at_t` equals the value computed from `df[:t]` at the moment of signal generation. Any discrepancy is a leak.
- The `feature_rules` config should encode the required lag for each feature family. The harness enforces it, not the individual feature function.
- Use event-driven feature construction (compute on bar-close event) rather than vectorized post-hoc computation wherever possible.

**Warning signs:**
- Feature functions receive the full DataFrame rather than a slice.
- IS Sharpe ratio is implausibly high (> 3.0 on 1-min bars for a discretionary-style signal).
- Live simulation shows a 30%+ drop from IS performance with identical parameters.
- Rolling windows with `min_periods` set to values smaller than the window size.

**Phase to address:**
Pass 1 scaffold (`feature_rules`, `feature_catalog`) and Pass 2 backtest engine. The engine must enforce entry-time discipline structurally, not by developer discipline.

---

### Pitfall 5: Non-Deterministic Backtest Engine Producing Unreproducible Results

**What goes wrong:**
Two runs with identical inputs produce different P&L figures. This makes it impossible to verify replication (P1a vs P1b), meaningless to track which iteration "kept" vs "reverted," and impossible to audit a deployed strategy's historical performance.

**Why it happens:**
Common sources: floating-point operations on unordered DataFrames (sort order depends on insertion), Python `dict` iteration before 3.7, random seeds not fixed in any HMM or scoring model, pandas operations that differ across versions, or multiprocessing with non-deterministic task scheduling.

**How to avoid:**
- Pass 2 must include a determinism test: run the same config twice, assert byte-for-byte identical trade ledgers.
- Fix all random seeds in config (HMM init, any Monte Carlo, any stochastic feature).
- Sort DataFrames explicitly on (date, instrument, bar_index) before any operation.
- Log the exact library versions in each run artifact.
- Prohibit in-place DataFrame mutations; use explicit copies with a naming convention.

**Warning signs:**
- Two backtest runs on the same data produce P&L that differs by small amounts (floating-point noise can mask the real issue).
- P1a and P1b results differ in ways inconsistent with their data split.
- The audit log shows different trade counts between two runs of the "same" experiment.

**Phase to address:**
Pass 2 backtest engine — determinism verification is a required acceptance criterion before Pass 3 begins.

---

### Pitfall 6: Unrealistic Slippage and Fill Model Inflate IS Performance

**What goes wrong:**
NQ is liquid but not perfectly liquid for intraday signal-touch strategies. A backtest that fills every signal at the exact signal-bar close price (or worse, mid-price) systematically overstates edge. On high-volatility days where signal-touch strategies generate the most trades, slippage is highest and the fill model diverges most from reality. The strategy deploys, real fills are 1-2 ticks worse, and the edge evaporates.

**Why it happens:**
Exact-price fills are the default in simple backtest engines. The actual NQ spread is 1 tick ($5 per contract on NQ, $0.50 on MNQ). Round-trip commission is ~$4-5 per NQ contract. These look small but at 3-5 trades/day over 60 days, they consume a meaningful fraction of gross edge on a short-duration signal strategy.

**How to avoid:**
- Model at minimum: 1-tick slippage per side on entry + exit, plus $4.50/contract round-trip commission.
- For signal-touch strategies specifically, use a conservative assumption that limit orders at touch price are not guaranteed fills — require the market to trade through the limit by 1 tick before counting a fill.
- Encode slippage and commission constants in the instrument registry (`instruments` config), not inline in backtest code.
- Net-of-cost Sharpe ratio must be the primary evaluation metric. Gross metrics may be logged but not used for go/no-go gates.

**Warning signs:**
- Backtest engine fills at bar close without any slippage offset.
- IS Sharpe ratio drops > 40% when realistic costs are applied post-hoc.
- Commission constants set to zero or commented out in config.
- Limit-order fills assumed whenever price touches the limit level (no through-trade requirement).

**Phase to address:**
Pass 2 backtest engine. `simulation_rules.md` must document the fill model and slippage assumptions before any strategy evaluation begins.

---

### Pitfall 7: Autoresearch `program.md` Scope Creep Breaks the One-File Constraint

**What goes wrong:**
The Karpathy pattern requires the agent to edit exactly one file per iteration, evaluated against a fixed harness and metric. If `program.md` instructions are ambiguous or grow over successive overnight sessions, the agent begins editing multiple files, changing the harness, or rewriting the evaluation metric. The keep/revert logic becomes unreliable because the baseline changes between iterations.

**Why it happens:**
Human operators updating `program.md` in the morning try to "help" by adding nuance. Each addition is small and reasonable. After a week, the file constrains nothing. The agent has learned to modify the feature catalog, the scoring model, and the evaluation harness in the same iteration, which is indistinguishable from overfitting the harness itself.

**How to avoid:**
- `program.md` has a 30-line hard cap (already in project constraints). Enforce it with a pre-commit hook lint check.
- The harness file (evaluate_features.py and each stage driver) must be read-only to the agent — either by file permission or by explicit instruction in the first 5 lines of CLAUDE.md.
- The evaluation metric is declared once in `statistical_gates` config, not in `program.md`. The agent cannot change what "good" means.
- Any `program.md` edit should be audited in the commit log with a note about what strategic direction changed.

**Warning signs:**
- `program.md` exceeds 30 lines.
- Git diff after an overnight run shows changes to both a feature file and the evaluation harness.
- IS performance jumps abnormally (+50% in one night) without a corresponding interpretable feature change.
- The harness `evaluate_features.py` has been modified by the agent.

**Phase to address:**
Pass 1 scaffold (CLAUDE.md, program.md stub, file permission strategy) and Pass 1.5 pre-commit hooks.

---

### Pitfall 8: Holdout Period Rolled Into IS via Accidental Period Config Mutation

**What goes wrong:**
The `period_config` defines IS and OOS boundaries. If the agent is ever permitted to edit `period_config`, an accidental or intentional extension of the IS end date past `2025-12-14` incorporates P2 data into calibration. This is not caught by a Bonferroni gate or a p-value threshold — it bypasses all statistical controls silently.

**Why it happens:**
Config files look like legitimate targets for "optimization." An agent searching for better signal conditions might extend the training window to capture a volatile Q4 2025 period that's actually in P2. The mutation is a one-line change that looks innocuous.

**How to avoid:**
- `period_config` must be read-only to the autoresearch agent. Include it in the list of harness/config files that are agent-immutable.
- `holdout_locked_P2.flag` creation should be timestamped and checked against `period_config` end date at engine startup.
- The pre-commit hook should reject any commit that modifies `period_config` outside of a human-initiated session (e.g., check for a `--allow-period-change` flag that is never set in the autoresearch driver).

**Warning signs:**
- `period_config` appears in the diff of an autoresearch-generated commit.
- IS start or end dates in `period_config` differ from those in `holdout_locked_P2.flag`.
- P2 bar data rows appear in the IS feature matrix.

**Phase to address:**
Pass 1 scaffold (period_config locked contents) and Pass 1.5 git infrastructure (pre-commit guard on config mutation).

---

### Pitfall 9: P1a/P1b Split Chosen After Seeing Feature Performance (Internal Replication Invalidated)

**What goes wrong:**
The P1a/P1b split is supposed to be a pre-registered internal replication: calibrate on P1a, validate on P1b. If the split boundary is chosen after any exploratory analysis of P1 features, the split is no longer independent. The researcher unconsciously picks a P1b window where the promising signal happens to generalize. This passes the internal replication gate but predicts nothing about P2.

**Why it happens:**
Exploratory EDA on P1 is tempting before committing to a split. It feels responsible to "understand the data" before deciding where to split. But any exposure to P1 signal distributions contaminates the split decision.

**How to avoid:**
- The P1a/P1b split boundary must be defined in `period_config` before any feature evaluation begins. It is a config value, not derived from data.
- Use a time-based split (first 60-70% of P1 calendar days = P1a) rather than a performance-based or regime-based split.
- Document in the audit log that the split boundary was set before Stage 04 ran any evaluation.

**Warning signs:**
- P1a/P1b split boundary appears in a commit that also includes feature evaluation results.
- The split boundary coincides with a regime boundary identified by the HMM (which implies regime-informed split selection).
- P1b Sharpe is suspiciously close to P1a Sharpe — this can indicate the split was tuned to minimize the gap.

**Phase to address:**
Pass 1 scaffold — `period_config` must contain the P1a/P1b boundary as a fixed constant before any autoresearch pass runs.

---

## Technical Debt Patterns

Shortcuts that seem reasonable but create long-term problems.

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| Compute features over full P1+P2 dataframe, split after | Simpler code, one pass | All features leak future data into IS period | Never |
| Inline slippage constants in backtest code | Faster to write | Slippage silently changes between experiments; no single source of truth | Never |
| Log only the winning experiment run | Cleaner audit log | Cannot compute effective alpha adjustment; p-hacking is invisible | Never |
| Use Viterbi (smoothed) regime labels for strategy features | Cleaner, more stable labels | Look-ahead leakage; labels change retroactively when new data arrives | Never for live features; acceptable for post-hoc analysis only |
| Set iteration budget in `program.md` (agent-editable) | Easy to adjust | Agent raises its own budget; Bonferroni denominator drifts | Never |
| Hardcode P2 date range in a utility script "just for analysis" | Convenient one-off | Creates an unguarded P2 access path that autoresearch can discover | Never during live pipeline runs |
| Skip the P1b replication gate if P1a results look good | Saves time | Removes the only pre-P2 overfitting signal; one-shot OOS becomes the only check | Never |

---

## Integration Gotchas

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| HMM fitter → feature pipeline | Passing the fitted model's full emission/transition matrix to the feature pipeline without freezing; refit occurs on each run | Serialize model after P1-only fit; load read-only; assert model hash at engine startup |
| BinnedScoringAdapter → backtest engine | Bin edges derived from full P1+P2 scoring distribution | Derive bin edges from P1a scoring distribution only; freeze in a JSON artifact before P1b validation |
| Autoresearch driver → data_loader | Driver calls `data_loader` without passing `end_date`; loader defaults to latest available bar | `data_loader` must require an explicit `end_date` param; no default; engine raises on missing arg |
| pre-commit hook → audit_log.md | Hook appends to audit log but can be bypassed with `--no-verify` | Audit log append is also done by the engine at run-completion time, not only at commit time; two-layer enforcement |
| Stage 05 feedback → Stage 03 | `prior_results.md` updated with absolute metric values; agent anchors on magnitude rather than relative improvement | `prior_results.md` records ranked experiment IDs and delta-vs-baseline; no raw Sharpe ratios that could anchor the agent |

---

## Performance Traps

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| Full P1 feature matrix recomputed on every autoresearch iteration | 60-second per-iteration overhead that multiplies to hours overnight | Precompute and cache the P1 feature matrix; agent edits only the scoring/signal logic, not feature computation | At > ~20 iterations per night |
| HMM regime detection refit every backtest run | Regime labels are non-deterministic across runs (random init); performance comparison across iterations is noise | Fit HMM once, freeze labels in `regime_labels.csv`; reload from file on every run | First run with multiple overnight iterations |
| Trade log stored in memory, written at end of run | OOM on long IS periods with high-frequency signal-touch strategies | Write trade log incrementally with buffered I/O; flush every N bars | At > ~5000 trades in a single backtest |
| pandas `iterrows()` in the simulation loop | 100× slower than vectorized ops; overnight run budget consumed by a single backtest | Use vectorized signal generation; reserve iterrows only for event-driven exit logic where unavoidable | At > 50,000 bar rows (approximately 35 trading days of 1-min NQ data) |

---

## "Looks Done But Isn't" Checklist

- [ ] **HMM fitter:** Appears to produce `regime_labels.csv` but uses Viterbi on full dataset — verify that `filtered` (forward-only) probabilities are used and that fit was called on P1 data only.
- [ ] **Holdout guard:** `holdout_locked_P2.flag` exists and pre-commit hook references it — verify that the backtest engine also checks the flag at runtime, not only the hook.
- [ ] **Audit log enforcement:** Append-only rule declared in CLAUDE.md — verify that the pre-commit hook rejects any commit where `audit_log.md` lines were deleted or modified (not just appended).
- [ ] **Iteration budget counter:** `statistical_gates` config has a `max_iterations` value — verify that the stage driver reads this value and hard-stops, not just logs a warning.
- [ ] **Bonferroni denominator:** p-value gate applied — verify that the denominator equals the pre-declared budget, not the number of completed tests.
- [ ] **Slippage/commission model:** Backtest produces P&L — verify that net-of-cost metrics are the gate criteria, not gross metrics.
- [ ] **Determinism:** Backtest engine runs — verify with two identical runs producing byte-identical trade ledgers before Pass 3 begins.
- [ ] **P1a/P1b split boundary:** `period_config` exists — verify that the boundary was committed before any Stage 04 evaluation ran (check git log timestamp ordering).
- [ ] **program.md line count:** File updated — verify it is <= 30 lines; verify the pre-commit hook enforces this limit.
- [ ] **Agent-immutable files:** CLAUDE.md lists harness files — verify that `evaluate_features.py`, `period_config`, and `statistical_gates` carry a file-permission or hook guard preventing agent modification.

---

## Recovery Strategies

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| HMM look-ahead leakage discovered after P1 calibration | HIGH | Refit HMM on P1-only with filtered inference; regenerate regime_labels.csv; invalidate all P1 experiment results; restart Stage 04 loop with fresh iteration budget |
| P2 contamination discovered mid-pipeline | CRITICAL | Stop all autoresearch runs; audit every feature computation for P2 rows; regenerate all artifacts from raw data; reset iteration budgets; document in audit log |
| Iteration budget exceeded without Bonferroni re-adjustment | MEDIUM | Apply post-hoc correction with denominator = actual tests run; gates that passed but would fail at corrected alpha are invalidated; must re-evaluate or accept degraded confidence |
| Backtest non-determinism discovered | MEDIUM | Bisect to find the source (sort order, random seed, library version); add determinism test to CI; re-run all affected experiments from scratch |
| `program.md` scope creep detected | LOW-MEDIUM | Revert to last known-good `program.md` state; audit agent commits for harness changes; rerun affected overnight sessions with scoped instructions |
| P1a/P1b split contaminated by prior EDA | HIGH | Re-declare split boundary with no reference to feature distributions; document rationale; invalidate P1b results; re-run P1b evaluation |

---

## Pitfall-to-Phase Mapping

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| HMM look-ahead leakage (Pitfall 1) | Pass 1 scaffold + Pass 1.5 hook | Audit `hmm_regime_fitter.py` decoder choice; assert `regime_labels.csv` was generated from P1-only fit |
| Autoresearch OOS contamination (Pitfall 2) | Pass 1.5 git infrastructure | Run autoresearch driver in dry-run mode; confirm P2 data files are unreachable; check pre-commit hook rejects P2 artifacts |
| p-Hacking / undisclosed iteration count (Pitfall 3) | Pass 3 stage drivers | Confirm stage driver hard-stops at budget; audit log shows no more IDs than budget |
| Feature entry-time leakage (Pitfall 4) | Pass 1 scaffold + Pass 2 engine | Canary test: feature at T equals feature computed from df[:T]; IS Sharpe sanity check < 2.0 for signal-touch |
| Non-deterministic engine (Pitfall 5) | Pass 2 engine | Run identical config twice; diff trade ledgers; assert zero diff |
| Unrealistic fill/slippage model (Pitfall 6) | Pass 2 engine | Apply 1-tick slippage + $4.50 commission; verify net Sharpe is < 80% of gross Sharpe |
| program.md scope creep (Pitfall 7) | Pass 1 scaffold + Pass 1.5 hook | Pre-commit hook enforces <= 30 lines; harness files are agent-immutable |
| period_config mutation (Pitfall 8) | Pass 1 scaffold + Pass 1.5 hook | Pre-commit hook rejects period_config changes without human flag; flag cross-check against holdout_locked_P2.flag |
| Contaminated P1a/P1b split (Pitfall 9) | Pass 1 scaffold | Git log shows period_config commit predates any Stage 04 evaluation commit |

---

## Sources

- Bailey, D.H. et al., "Backtest Overfitting in Financial Markets" — [PDF](https://www.davidhbailey.com/dhbpapers/overfit-tools-at.pdf) — HIGH confidence, peer-reviewed
- Portfolio Optimization Book, Ch. 8.3 "Dangers of Backtesting" — [bookdown.org](https://bookdown.org/palomar/portfoliooptimizationbook/8.3-dangers-backtesting.html) — HIGH confidence
- arXiv:2512.12924 "Interpretable Hypothesis-Driven Trading: Walk-Forward Validation" — [arxiv.org](https://arxiv.org/html/2512.12924v1) — HIGH confidence, 2024/2025
- "The Hidden Trap in Algorithmic Trading: Data Leakage in Backtesting" — [Medium](https://medium.com/@wl8380/the-hidden-trap-in-algorithmic-trading-data-leakage-in-backtesting-622a13e01cb9) — MEDIUM confidence
- "Market Regime Detection using HMMs" — [QuantStart](https://www.quantstart.com/articles/market-regime-detection-using-hidden-markov-models-in-qstrader/) — HIGH confidence, practitioner-verified
- karpathy/autoresearch GitHub repo — [github.com](https://github.com/karpathy/autoresearch) — HIGH confidence, primary source
- "The Frozen Metric of Autoresearch" — [Hybrid Horizons](https://hybridhorizons.substack.com/p/the-frozen-metric-of-autoresearch) — MEDIUM confidence, secondary analysis
- "P-Hacking and Backtest Overfitting" — [mathinvestor.org](https://mathinvestor.org/2019/04/p-hacking-and-backtest-overfitting/) — HIGH confidence
- QuantConnect Slippage/Fill Model docs — [quantconnect.com](https://www.quantconnect.com/docs/v2/writing-algorithms/reality-modeling/slippage/key-concepts) — HIGH confidence, official docs
- "Backtesting Limitations: Slippage and Liquidity" — [LuxAlgo](https://www.luxalgo.com/blog/backtesting-limitations-slippage-and-liquidity-explained/) — MEDIUM confidence
- "Walk-Forward Optimization: How It Works" — [QuantInsti](https://blog.quantinsti.com/walk-forward-optimization-introduction/) — HIGH confidence

---
*Pitfalls research for: Futures trading strategy research pipeline (NQ, signal-touch, IS/OOS, autoresearch)*
*Researched: 2026-03-13*
