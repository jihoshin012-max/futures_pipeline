---
phase: 02-feature-evaluator-screening
plan: 01
subsystem: rotational-feature-infrastructure
tags: [hypothesis-registry, feature-engine, feature-evaluator, tdd, vectorized]
dependency_graph:
  requires: [01-rotational-simulator-baseline]
  provides: [hypothesis-configs, compute-hypothesis-features, 3-outcome-evaluator]
  affects: [02-02-experiment-runner]
tech_stack:
  added: []
  patterns: [vectorized-pandas-rolling, dotted-path-config-patch, tdd-red-green]
key_files:
  created:
    - shared/archetypes/rotational/hypothesis_configs.py
    - shared/archetypes/rotational/test_hypothesis_configs.py
    - shared/archetypes/rotational/test_feature_evaluator_rotational.py
  modified:
    - shared/archetypes/rotational/feature_engine.py
    - shared/archetypes/rotational/rotational_simulator.py
    - shared/archetypes/rotational/feature_evaluator.py
decisions:
  - "H23 placed in Dimension D (Conditional adds, structural modification) per spec Section 3.4 — not a filter"
  - "H17/H36/H39 return NaN placeholders since they require simulator state; documented as dynamic features"
  - "H19 returns NaN with SKIPPED_REFERENCE_REQUIRED when _h19_skip=True in config; requires multi-source loading"
  - "FeatureComputer dispatches to feature_engine only for non-baseline configs (trigger != fixed OR active_filters OR structural_mods)"
  - "evaluate() outcome_type defaults to 'direction' for full backward compatibility with Stage 02 dispatcher"
  - "Rolling windows use min_periods=lookback (not min_periods=1) for strict entry-time safety — warmup period is NaN"
metrics:
  duration_minutes: 30
  completed_date: "2026-03-15"
  tasks_completed: 3
  files_created: 3
  files_modified: 3
  tests_added: 53
  tests_passing: 53
requirements_satisfied: [ROT-RES-01]
---

# Phase 2 Plan 01: Hypothesis Config Registry + Feature Engine + Evaluator Upgrade Summary

**One-liner:** Built 41-hypothesis registry (A=5,B=1,C=16,D=10,E=2,F=7), vectorized feature engine for all hypotheses, and upgraded MWU evaluator with direction/reversal_quality/add_quality outcome types.

---

## What Was Built

### Task 1: Hypothesis Config Registry (hypothesis_configs.py)

`HYPOTHESIS_REGISTRY` defines all 41 hypotheses from spec Sections 3.1-3.6:

- Each entry has: `id`, `name`, `dimension`, `config_patch`, `param_grid`, `default_params`, `computed_features`, `exclude_10sec`, `requires_reference`, `requires_dynamic_features`, `description`
- `build_experiment_config(base_config, hypothesis, params)` deep-copies base and applies dotted-path overrides
- `get_screening_experiments()` returns exactly 122 experiment definitions (41×3 - 1 for H37/10sec)
- Registry validated at import time via `_validate_registry()`

Key dimension decisions verified against spec:
- **H23 = Dimension D** (Conditional adds) — NOT Dimension C. Spec Section 3.4 lists it under "Structural Modifications".
- **H37 `exclude_10sec=True`** — bar formation rate is constant on fixed-cadence 10-sec series
- **H19 `requires_reference=True`** — needs all 3 bar types loaded simultaneously

### Task 2: Feature Engine + FeatureComputer Dispatch

`feature_engine.compute_hypothesis_features(bar_df, hypothesis_config)` dispatches on `trigger_mechanism` and `active_filters`:

**Dimension A triggers:** H1 (`atr_scaled_step`), H8 (`rolling_sd`, `sd_scaled_step`), H9 (VWAP+bands with session reset), H10 (`price_zscore`, `rolling_mean`, `rolling_sd`), H3 (no new columns, uses CSV bands)

**Active filters (Dimension C/F):** H27 (`atr_roc`), H28 (`price_roc`), H29 (`price_acceleration`), H30 (`volatility_squeeze_state`), H31 (`momentum_divergence`), H32 (`volume_roc`), H33 (`price_speed`, `bar_duration_sec`), H34 (`ask/bid_absorption_rate`), H35 (`imbalance_ratio`, `imbalance_slope`), H37 (`bar_formation_rate`), H38 (`regime_transition_speed`), H40 (`band_speed_state`), H41 (`band_atr_state`)

**Dynamic feature placeholders (NaN):** H17 (`cycle_feedback_state`), H36 (`adverse_speed`), H39 (`adverse_velocity_ratio`) — require simulator internal state, documented with `attrs` metadata

`FeatureComputer.compute_static_features()` in `rotational_simulator.py` updated to dispatch to feature_engine for non-baseline configs. Baseline (fixed trigger, no filters, no structural_mods) returns bar_df unchanged — all 46 existing simulator tests pass.

### Task 3: Feature Evaluator Upgrade (Gap G-04)

`feature_evaluator.evaluate()` now accepts `outcome_type` parameter (backward compatible, default="direction"):

- **direction** (existing): +1 if next N bars moved up, -1 if down
- **reversal_quality** (new): +1 if price reversed from prior N-bar direction within N bars, -1 if continuation
- **add_quality** (new): +1 if price mean-reverted within N bars (add was justified), -1 if continuation

Dynamic dispatch via `evaluate_features.py` works by path (Gap G-09 satisfied — the dispatcher loads `shared/archetypes/rotational/feature_evaluator.py` via importlib by path).

---

## Test Coverage

| File | Tests | Status |
|------|-------|--------|
| test_hypothesis_configs.py | 18 | PASS |
| test_feature_evaluator_rotational.py | 35 | PASS |
| test_rotational_simulator.py (regression) | 46 | PASS |
| **Total** | **99** | **ALL PASS** |

---

## Deviations from Plan

None — plan executed exactly as written.

The only design choice made implicitly: `rolling(lookback, min_periods=lookback)` rather than `min_periods=1` for rolling features. This is stricter entry-time safety (NaN during warmup) per spec requirement. The plan specified "rolling features have NaN for warmup period" and this was the natural implementation.

---

## Self-Check: PASSED

Files exist:
- FOUND: shared/archetypes/rotational/hypothesis_configs.py
- FOUND: shared/archetypes/rotational/test_hypothesis_configs.py
- FOUND: shared/archetypes/rotational/test_feature_evaluator_rotational.py

Commits exist (from `git log --oneline -5`):
- 59a5282 feat(02-01): upgrade feature_evaluator with reversal_quality and add_quality outcome types
- ca618f9 feat(02-01): extend feature_engine with vectorized hypothesis features and FeatureComputer dispatch
- 4b0db36 feat(02-01): build hypothesis config registry with all 41 hypothesis definitions
