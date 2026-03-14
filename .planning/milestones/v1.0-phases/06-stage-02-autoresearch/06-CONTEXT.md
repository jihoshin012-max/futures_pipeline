# Phase 6: Stage 02 Autoresearch - Context

**Gathered:** 2026-03-14
**Status:** Ready for planning

<domain>
## Phase Boundary

Feature engineering keep/revert loop for Stage 02. The autoresearch agent edits feature_engine.py, the fixed harness (evaluate_features.py + feature_evaluator.py) computes MWU predictive spread, and the driver enforces entry-time-only rule, keep/revert decisions, and 300-experiment budget. Produces results.tsv with per-feature metrics. Human freezes approved features into frozen_features.json after review.

</domain>

<decisions>
## Implementation Decisions

### Entry-time enforcement
- Runtime bar-index guard: feature_evaluator.py truncates bar_df at the touch row's entry bar index before passing to feature_engine.py
- Features only see bars up to and including entry bar close — structural, not convention
- Truncation applied per touch row (every P1 touch, no sampling)
- On violation (NaN/error from truncated data): keep is blocked, results.tsv logs kept=false with reason='entry_time_violation'
- No static AST scan — runtime guard is sufficient and non-brittle

### MWU spread computation
- Metric: best-bin vs worst-bin mean trade PnL in ticks
- Binning: terciles (3 bins) — low/mid/high
- Bin edges computed on P1a feature values, applied to P1b touches
- MWU test compares P1a best-bin PnL distribution vs P1b best-bin PnL distribution
- Keep threshold (from feature_rules.md): spread > 0.15 AND MWU p < 0.10
- Outcome variable: trade PnL in ticks (same as backtest engine output)

### Driver keep/revert flow
- Agent (Claude) writes/edits feature_engine.py per program.md direction — Karpathy pattern: agent proposes, harness judges
- Driver does NOT propose features itself — it runs the harness, evaluates keep/revert, logs results
- current_best/ directory holds the last kept feature_engine.py copy (same pattern as Stage 04)
- On keep: copy feature_engine.py to current_best/. On revert: restore from current_best/
- Baseline controlled by program.md and current_best/ contents — not hardcoded in driver
- For zone_touch: human seeds current_best/ with zone_width feature before first run
- For new archetypes with no prior features: current_best/ starts empty, compute_features() returns empty dict
- Budget: 300 experiments, enforced from statistical_gates.md — driver refuses experiment 301

### Feature accumulation
- Stacking model: each experiment adds or modifies one feature in a growing feature_engine.py
- Spread and MWU p measured on the new/modified feature only — not the combined set
- compute_features(bar_df, touch_row) returns dict keyed by feature name: {'zone_width': 3.5, 'vol_ratio': 1.2, ...}
- Driver tells evaluator which key is new (from program.md or diff against current_best/)
- Prior kept features remain untouched in feature_engine.py across experiments
- results.tsv logs per-feature metrics (one row per experiment, feature_name column)

### Archetype-agnostic design
- evaluate_features.py dispatcher remains archetype-agnostic — loads evaluator via importlib with --archetype flag (already implemented in Phase 5)
- feature_evaluator.py's evaluate() interface documented as: returns dict with at minimum {spread, mwu_p} — harness does not care how spread is computed internally
- Same Phase 6 infrastructure (driver, dispatcher, keep/revert loop) runs against any archetype's feature_evaluator.py without modification
- No zone_touch-specific logic in driver or dispatcher

### Human freeze workflow
- After reviewing results.tsv and feature_catalog.md, human runs a freeze script
- Freeze reads current_best/feature_engine.py, extracts feature names + bin edges, writes frozen_features.json to stages/02-features/output/
- Human copies frozen_features.json to stages/03-hypothesis/references/ (per Stage 02 CONTEXT.md)
- Not automated — human approval gate required

### Claude's Discretion
- results.tsv column layout and exact format
- program.md template content and steering instructions
- Error handling and anomaly detection patterns (following Phase 5 conventions)
- Freeze script implementation details
- feature_engine.py template structure

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- Stage 04 driver.py: Complete keep/revert loop with budget enforcement, run_id generation, git commit integration — pattern to follow
- evaluate_features.py: Archetype-agnostic dispatcher already built (Phase 5) — loads evaluator via importlib, writes feature_evaluation.json
- feature_evaluator.py (zone_touch): Placeholder with correct interface contract — needs MWU spread logic added
- shared/data_loader.py: load_touches() function for P1 touch data loading
- feature_rules.md: Keep thresholds already defined (spread > 0.15, MWU p < 0.10)
- feature_catalog.md: Empty template ready for population
- feature_definitions.md: Empty template with registration format

### Established Patterns
- Karpathy autoresearch: agent edits one file, fixed harness evaluates, program.md steers — Stage 04 implements this fully
- current_best/ directory for revert state — Stage 04 uses this
- importlib.util.spec_from_file_location for path-based module loading — no sys.path mutation
- _generate_run_id() using SHA hash — reuse pattern from Stage 04
- results.tsv append-only logging with n_prior_tests count
- Non-fatal git commits (try/except pass) — Stage 04 convention

### Integration Points
- feature_evaluator.py loads P1 touch data via shared.data_loader.load_touches()
- P1a/P1b split boundary from _config/period_config.md — evaluator needs to split P1 touches
- statistical_gates.md provides 300-experiment budget
- program.md steers agent direction each iteration
- frozen_features.json flows to stages/03-hypothesis/references/ for Stage 03 consumption

</code_context>

<specifics>
## Specific Ideas

- Seeded baseline for zone_touch: zone_width feature from M1_A calibration — human places in current_best/ before first run
- Rotational archetype (future) may use rank correlation instead of bin spread — evaluate() interface is agnostic to internal computation method
- "The harness does not care how spread is computed internally, only that it returns a comparable float" — key design principle for archetype extensibility

</specifics>

<deferred>
## Deferred Ideas

- Rotational strategy archetype support — future archetype registration, not Phase 6 work (infrastructure is archetype-agnostic by design)
- Combined feature set evaluation (multi-feature composite signal) — could be a Phase 6 extension or separate phase
- Automated freeze after budget exhaustion — intentionally deferred; human gate preferred

</deferred>

---

*Phase: 06-stage-02-autoresearch*
*Context gathered: 2026-03-14*
