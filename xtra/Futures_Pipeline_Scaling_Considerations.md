# Futures Pipeline — Scaling Considerations
> **Created:** 2026-03-13
> **Purpose:** Forward-looking observations on where the pipeline will need deliberate attention as strategy count, instrument coverage, and research volume grow. Each section identifies the current state, the scaling pressure, and concrete suggestions.
> **Audience:** Pipeline architect (Ji). Not a build spec — a thinking document.

---

## Contents

1. [Regime Awareness](#1-regime-awareness)
2. [Scoring Adapter Architecture](#2-scoring-adapter-architecture)
3. [Live Feedback Loop](#3-live-feedback-loop)
4. [Multiple Testing as Strategy Library Grows](#4-multiple-testing-as-strategy-library-grows)
5. [Context Management at Scale](#5-context-management-at-scale)
6. [Data Infrastructure](#6-data-infrastructure)
7. [Hypothesis Search Space](#7-hypothesis-search-space)
8. [Deployment and Live Operations](#8-deployment-and-live-operations)

---

## 1. Regime Awareness

### Current state
Regime labeling is implemented — three dimensions (trend, volatility, macro), HMM-fitted on P1 only, day-level granularity. Stage 05 includes regime breakdown in assessment reports when n_trades ≥ 20 per bucket. The infrastructure is sound.

### Scaling pressure
Currently regime is **descriptive** — it tells you how a strategy performed across regimes after the fact. As the strategy library grows, the more valuable question becomes **prescriptive**: which regimes should Stage 03 be searching in, and should the hypothesis search be regime-conditional from the start?

With one strategy this doesn't matter much. With five strategies, you'll start seeing patterns — some archetypes work in trending regimes, others in ranging — and the current setup has no mechanism to exploit that cross-strategy signal in the search process.

### Suggestions

**Near-term (before adding second archetype):**
- Add `regime_filter` as an optional field in `hypothesis_config.json` — the agent can propose hypotheses that only trade in specified regime conditions. Stage 03 autoresearch searches this dimension alongside routing and scoring config.
- Add regime conditional PF to `results_master.tsv` so the dashboard shows which regimes each strategy is sensitive to.

**Medium-term (after 3+ archetypes):**
- Build a cross-strategy regime summary — a simple view showing which archetype performs best in each regime combination. This becomes the input to human steering of Stage 03 search direction.
- Consider intraday regime labeling (not just day-level). NQ can shift regime within a session. A half-day granularity using rolling ATR and trend indicators would be a meaningful signal improvement.

**Long-term:**
- Regime-conditional feature calibration in Stage 02. Currently bin edges are calibrated on all of P1 uniformly. Calibrating separately per regime (where trade counts allow) would produce sharper scoring models for regime-specific strategies.
- Feed regime state into Stage 07 live drift detection as a first-class dimension. A strategy underperforming live is much easier to diagnose if you can see it's underperforming specifically in high-vol macro days rather than uniformly.

---

## 2. Scoring Adapter Architecture

### Current state
Three adapters: BinnedScoringAdapter, SklearnScoringAdapter, ONNXScoringAdapter. All share the same interface: `score(touch_df) → pd.Series`. Dynamic dispatch via `config.archetype.scoring_adapter`. A scaffold generator creates stubs for new adapters. The design is extensible.

### Scaling pressure
The current interface assumes **per-signal scoring** — each row in touch_df gets an independent score. This works for zone_touch and any strategy that filters a list of candidate signals.

Two strategy types break this assumption cleanly:
1. **Rotational strategies** — the decision is comparative across instruments at a point in time, not absolute per signal. Requires a RankingAdapter with a fundamentally different interface.
2. **Portfolio strategies** — position sizing depends on the full set of active signals simultaneously, not each signal in isolation. A PositionSizingAdapter would need to see all concurrent opportunities.

Both require not just a new adapter class but a new dispatch path in `backtest_engine.py` alongside the existing one.

### Suggestions

**Before adding any non-zone-touch archetype:**
- Define the adapter interface contract more explicitly. Current implicit contract is: input is a DataFrame of candidate signals, output is a pd.Series of float scores with same index. Document this formally in `scoring_adapter.py` as an abstract base class with type annotations.
- Add an `adapter_type` field to `strategy_archetypes.md` alongside `scoring_adapter`: `per_signal` (current) vs `ranking` vs `portfolio`. `backtest_engine.py` dispatches to the appropriate execution path based on this.

**When building RankingAdapter:**
- Define it as a separate interface from the start rather than trying to fit it into the existing `score()` signature. A ranking adapter receives a snapshot dict of `{instrument: features_df}` and returns `{instrument: allocation_weight}`. Clean separation avoids retrofitting.
- The simulator for rotation is also different — it manages position switches rather than individual trade entries. Build the simulator and adapter as a pair, not separately.

**Long-term:**
- Consider an adapter registry — a lightweight YAML or JSON file in `shared/scoring_models/` that maps adapter names to their type, interface version, and which archetypes use them. As the adapter library grows, this registry becomes the source of truth for what's available, just as `data_registry.md` is for data sources.

---

## 3. Live Feedback Loop

### Current state
Stage 07 is scaffolded — `paper_trades.csv`, `live_assessment.md`, `drift_report.md`, `review_triggers.md`. M1_A paper trading is active. The feedback path from Stage 07 back into Stage 03 (via prior_results.md) is specified but not yet operational.

### Scaling pressure
This is the loop that turns the pipeline from a one-time discovery system into a continuously improving one. Currently the pipeline discovers a strategy, deploys it, and the connection back to the research process is entirely manual. At one strategy that's fine. At five strategies running live simultaneously, the volume of live signal becomes genuinely informative — you're accumulating real forward-validated data faster than the IS research cycle can produce hypotheses.

### Suggestions

**Near-term (after 100 M1_A paper trades):**
- Complete the feedback wiring: Stage 05 assessment automatically copies `feedback_to_hypothesis.md` to `03-hypothesis/references/prior_results.md`. The hypothesis agent reads this before each run. This is specified in the spec but verify it's actually wired end-to-end in the built pipeline.
- Add a `live_pf_vs_backtest_pf` metric to the dashboard. The single most useful early signal is whether live PF is tracking backtest PF directionally. A simple ratio plotted over rolling 20-trade windows shows drift before it becomes a problem.

**Medium-term (after 200 M1_A paper trades):**
- Implement the IS promotion evaluation formally. Live data after 200+ trades with no lookahead is arguably higher quality than IS data — it's forward-validated, untouched by the research process. Build the protocol for evaluating it as a candidate IS period (`PERIOD_CONFIG_CHANGED` audit entry, human decision gate).
- Add regime breakdown to Stage 07 drift analysis. "Live PF diverged 40% from backtest" is less actionable than "live PF diverged specifically in ranging low-vol regimes." The regime labels already exist — wire them into the drift report.

**Long-term:**
- Automated Stage 03 re-triggering. When Stage 07 detects sustained underperformance (e.g. live PF < 0.7x backtest PF for 50+ trades), it generates a `RESEARCH_TRIGGER` audit entry and proposes re-running Stage 03 with updated prior_results.md. Human approves but the evidence gathering and framing is automated.
- Cross-strategy live learning. If two archetypes both underperform in the same regime conditions in live trading, that's a signal that the regime model itself may need updating — not just the strategies. Build a cross-strategy live assessment that flags this class of systematic failure.

---

## 4. Multiple Testing as Strategy Library Grows

### Current state
Multiple testing controls are serious: Bonferroni-adjusted p-value gates, iteration budgets per archetype per IS period (Stage 02: 300, Stage 03: 200, Stage 04: 500), n_prior_tests tracked in results_master.tsv. The P1a/P1b replication check adds an internal validity gate. These controls are well-designed for a single archetype.

### Scaling pressure
The budgets and gates are currently per-archetype per IS period. With one archetype running on one IS period, the family-wise error rate is manageable. With five archetypes each running 200 hypothesis iterations, the total number of tests against P1 data is 1,000+ — and the Bonferroni correction as currently designed applies per-archetype, not across the full family of tests.

Additionally, when P2 becomes IS (after P3 arrives), P2 data is no longer clean — it's been observed. Using it as IS data for subsequent research is methodologically valid but the Bonferroni budgets don't currently reset or adjust to reflect the expanded IS pool.

### Suggestions

**Before running multi-archetype autoresearch:**
- Add a cross-archetype test count to `statistical_gates.md`. When total tests across all archetypes in an IS period exceeds a threshold (suggested: 1,000), tighten all p-value gates by an additional factor regardless of per-archetype counts.
- Document the family-wise error rate explicitly in `statistical_gates.md` so it's a living number, not an implicit assumption.

**When P2 is promoted to IS:**
- Reset n_prior_tests counters for all archetypes against the new combined IS pool. Prior tests against P1-only don't carry over — the new IS pool is P1+P2 combined, and the budget restarts.
- Add a note to `period_config.md` rolling-forward instructions: "After promotion, reset iteration budgets in statistical_gates.md for all active archetypes."

**Long-term:**
- Consider a global experiment ledger separate from per-stage results.tsv files. As the strategy library grows, understanding the total research spend against each IS period becomes important for interpreting any individual result. The current dashboard aggregates across stages but not across archetype generations.

---

## 5. Context Management at Scale

### Current state
ICM conventions are well-designed: CLAUDE.md (60-line cap), stage CONTEXT.md (80-line cap), program.md (30-line cap), front-loading rule, staleness flags with last_reviewed dates. The context_review_protocol.md formalizes the maintenance protocol. This is one of the most thoughtful parts of the current design.

### Scaling pressure
The current context files describe one archetype (zone_touch) and one active research direction. With three archetypes and multiple concurrent autoresearch runs, the CONTEXT.md files need to remain archetype-agnostic at the stage level while being specific enough to steer each run correctly. That tension gets harder to manage as complexity grows.

The 80-line cap on stage CONTEXT.md becomes a genuine constraint when Stage 03 has three archetypes with different routing rules, different scoring configurations, and different dead-end histories that the agent needs to avoid.

### Suggestions

**Before adding second archetype:**
- Verify that stage CONTEXT.md files are written at the archetype-agnostic level — they describe the stage contract, not zone_touch-specific behavior. Zone_touch-specific context belongs in `shared/archetypes/zone_touch/simulation_rules.md` and `exit_templates.md`, not in the stage CONTEXT.md.
- Add `active_archetype` as a field in `program.md` for Stage 03 and Stage 04. The agent reads which archetype it's currently working on from program.md, not from CONTEXT.md. This keeps CONTEXT.md stable while program.md carries the run-specific context.

**Medium-term:**
- Build a CONTEXT.md validation script — a simple Python script that checks all CONTEXT.md files are within line limits, have current last_reviewed dates, and front-load their operative instruction in the first 5 lines. Run this as part of the pre-commit hook on period rollover, not just as a manual reminder.
- Consider per-archetype program_history.md files in addition to per-stage ones. As each archetype's research history grows, the compressed dead-end history in program.md becomes harder to trim meaningfully. Per-archetype history keeps the pruning context-appropriate.

**Long-term:**
- As the pipeline adds stages or substages (e.g. a dedicated regime-conditional assessment substage), the CLAUDE.md routing layer will need a more structured routing protocol than the current linear stage progression. The ICM repo conventions (Gap 3) become more important to resolve as complexity grows.

---

## 6. Data Infrastructure

### Current state
Bar data typed by bar type (volume/time/tick subfolders), touches coupled to bar type through BarIndex (documented), data_registry.md as single source of truth, data_manifest.json as runtime resolution layer, Stage 01 as the only place data is validated. Clean design.

### Scaling pressure
Currently one instrument (NQ), one touches source (zone_csv_v2), one bar type (250-vol). As instruments and data sources multiply, the Stage 01 validation job grows significantly. A failed schema check on one of five instruments' data shouldn't block the pipeline from running on the other four.

The bar offset computation (`_find_bar_offset`) samples the first ~10 touches to compute a global offset. This works for a single instrument with consistent bar boundaries. With multiple instruments running simultaneously, each with its own bar data and touches files, the offset computation needs to be per-instrument per-period, not global.

### Suggestions

**Before adding second instrument:**
- Make Stage 01 validation instrument-aware. Validation should produce a per-instrument section in `validation_report.md` with pass/fail per source_id. A failed instrument is flagged and excluded from data_manifest.json for that run, but other instruments proceed.
- Make `_find_bar_offset()` accept an explicit instrument parameter and compute offsets per-instrument. Cache per-instrument offsets in data_manifest.json rather than recomputing each run.

**When adding orderflow data:**
- Orderflow data (cumulative delta, VAP, footprint) typically has different temporal resolution than bar data and different alignment requirements. Before registering it in data_registry.md, define the alignment contract explicitly: is it aligned to bar boundaries, to touch timestamps, or to something else? Add an `alignment` column to data_registry.md alongside `type`.

**Long-term:**
- Consider a data quality score per source per period — a simple metric (% rows passing schema, % timestamps with valid bar alignment, gap rate) that Stage 01 writes into data_manifest.json. Stage 05 assessment can then weight results by data quality, and the dashboard can surface data quality alongside strategy performance. A Conditional verdict on clean data means something different from a Conditional verdict on data with 15% gaps.

---

## 7. Hypothesis Search Space

### Current state
Stage 03 autoresearch explores `hypothesis_config.json` — scoring weights, routing rules, scoring gates. Stage 04 explores exit parameters. Stage 02 explores features. Three separate loops, well-sequenced.

### Scaling pressure
The current search space is the zone_touch parameter surface: scoring configuration variations and exit parameter combinations. This is a well-bounded space that autoresearch can cover meaningfully in 200 experiments. When genuinely different archetypes are added (orderflow scalp, mean reversion, breakout), the search space expands in ways that 200 experiments may not adequately cover — particularly when the archetype has structural differences in routing or signal generation rather than just parameter variations.

### Suggestions

**Before Stage 03 autoresearch first run:**
- Seed `results.tsv` with the existing M1_A calibration results as the baseline. Stage 04 autoresearch should start from the known-good region of the parameter space, not from a cold start. This dramatically improves search efficiency.
- Build a dead-end taxonomy in `feature_catalog.md` — not just a list of failed features but a classification of *why* they failed (no predictive spread, entry-time violation, data coverage too thin, regime-specific only). The agent reads this taxonomy before proposing, which guides it away from entire classes of failure rather than individual failed attempts.

**Medium-term:**
- Add a `hypothesis_template` concept to Stage 03. Rather than fully free-form hypothesis generation, define 4-6 structural templates (e.g. "zone touch with session filter", "zone touch with volatility gate", "zone touch with SBB confirmation") that the agent varies within. This constrains the search to structurally valid hypothesis families and dramatically reduces wasted experiments on structurally broken configs.
- Add cross-archetype feature sharing. A feature that works for zone_touch (e.g. regime state at entry) may also work for a future orderflow archetype. The current design stores features per-archetype in `feature_definitions.md`. Consider a `shared_features` section for features validated across multiple archetypes — these become high-confidence candidates for any new archetype's Stage 02 search.

**Long-term:**
- When P1+P2 are both IS (after P3 arrives), run a retrospective: which features and hypothesis configurations that passed P1 also held on P2? This retrospective IS analysis doesn't contaminate anything (P2 is now IS) and produces high-quality signal about which parts of the search space are genuinely robust versus P1-specific.

---

## 8. Deployment and Live Operations

### Current state
Stage 06 generates Sierra Chart ACSIL code from frozen parameters, with `assemble_context.sh` assembling the context package and M1B_AutoTrader.cpp as the structural reference. Manual gate — human approves every deployment. Alignment test (`alignment_test.py`) runs before deployment.

### Scaling pressure
The current deployment path produces one ACSIL study per strategy. With three or four strategies running live simultaneously, the operational complexity grows: multiple studies running in the same Sierra Chart instance, potential for signal overlap, different review trigger thresholds to monitor, separate paper_trades.csv files to maintain.

### Suggestions

**Before second strategy deployment:**
- Define a signal isolation protocol — what happens when two strategies simultaneously signal on the same instrument in opposite directions? Document the resolution rule in `_config/pipeline_rules.md` as Rule 6: strategies are position-independent by default; simultaneous opposing signals are flagged in the audit log but neither is blocked.
- Add a deployment registry — a simple markdown file in `06-deployment/` listing all currently deployed strategies, their deployment date, their live status (paper/funded), and their current review trigger thresholds. One file to answer "what is running right now."

**Medium-term:**
- Standardize the alignment test interface. Currently `alignment_test.py` is a ZB4 vs ZRA comparison script specific to zone_touch. When new archetypes are deployed, they need their own alignment tests. Define a standard alignment test interface: takes frozen_params.json and a small replay dataset, returns pass/fail with a brief summary. Each archetype's `06-deployment/references/` folder contains its own alignment test implementing this interface.
- Add a deployment diff tool — given two versions of the same strategy (e.g. M1_A v1 and M1_A v2), show exactly which parameters changed and by how much. This makes reviewing parameter updates faster and creates a clear record of what changed between deployments.

**Long-term:**
- Consider a unified live monitor dashboard separate from the research dashboard. The research dashboard (`results_master.tsv`) is optimized for comparing experiments. The live dashboard should be optimized for operational monitoring: all active strategies, their live vs backtest PF, current drawdown vs limit, days since last trigger review. These are different views on different data.
- When funded trading begins, add position-level tracking to Stage 07 — not just trade-level. The current design tracks individual trades. Position-level tracking (entry, current mark, unrealized PnL, time in position) adds the operational view needed for real-time risk management alongside the statistical view.

---

## Summary Priority Table

| Area | Priority | When it becomes critical | Effort |
|------|----------|--------------------------|--------|
| Regime-conditional hypothesis search | High | Before second archetype | Medium |
| Adapter architecture extension | High | Before non-zone-touch archetype | High |
| Live feedback loop wiring | High | After 100 M1_A paper trades | Low |
| Cross-archetype multiple testing | Medium | Before multi-archetype autoresearch | Low |
| CONTEXT.md validation script | Medium | Before second archetype | Low |
| Instrument-aware Stage 01 validation | Medium | Before second instrument | Medium |
| Bar offset per-instrument caching | Medium | Before second instrument | Low |
| Hypothesis template library | Medium | Before Stage 03 first run | Low |
| Signal isolation protocol | Medium | Before second deployment | Low |
| Deployment registry | Low | Before second deployment | Low |
| Intraday regime labeling | Low | After 3+ archetypes | High |
| Cross-strategy live learning | Low | After 3+ strategies live | High |
| Unified live operations dashboard | Low | When funded trading begins | Medium |
