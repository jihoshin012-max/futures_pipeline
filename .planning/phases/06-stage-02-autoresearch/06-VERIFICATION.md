---
phase: 06-stage-02-autoresearch
verified: 2026-03-14T00:00:00Z
status: passed
score: 11/11 must-haves verified
re_verification: false
---

# Phase 6: Stage 02 Autoresearch Verification Report

**Phase Goal:** The Stage 02 overnight loop evaluates feature candidates using MWU spread, enforces the entry-time-only rule structurally, and produces a feature catalog update after each overnight run
**Verified:** 2026-03-14
**Status:** passed
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths (from ROADMAP Success Criteria)

| # | Truth | Status | Evidence |
|---|-------|--------|---------|
| 1 | An overnight test of 20 experiments completes and each row in results.tsv contains a spread value computed from MWU on P1a vs P1b feature distributions | VERIFIED | results.tsv has 23 data rows (3 budget test + 20 smoke); all rows have spread=44.094, mwu_p=1.48e-07, verdict=kept, stage=02-features; all 24 columns present |
| 2 | A feature that reads a post-entry-time bar value is detected by the canary test and logged as entry_time_violation, blocking the keep decision | VERIFIED | feature_evaluator.py truncates bar_df at iloc[:BarIndex] per touch; IndexError caught per-feature sets entry_time_violation=True; driver reads per-feature flag and sets verdict='entry_time_violation' blocking keep; TestEntryTimeCanary tests confirm this (3 tests) |
| 3 | The driver stops at the 300-experiment budget declared in statistical_gates and does not run experiment 301 | VERIFIED | driver.py checks n_prior_tests >= budget before each iteration (line 214); TestBudgetEnforcement::test_stops_at_budget confirms 0 engine calls when budget exhausted; program.md has BUDGET: 300; smoke test verified budget=3 stop |

**Score:** 3/3 ROADMAP success criteria verified

---

### Plan Must-Have Truths

#### Plan 01 Must-Haves

| # | Truth | Status | Evidence |
|---|-------|--------|---------|
| 1 | feature_engine.py compute_features(bar_df, touch_row) returns {'zone_width': float} | VERIFIED | shared/archetypes/zone_touch/feature_engine.py line 28-49; returns {'zone_width': float(zone_width_ticks)}; tick_size read from _config/instruments.md via parse_instruments_md('NQ') |
| 2 | feature_evaluator.py evaluate() returns spread and mwu_p for zone_width feature using P1a/P1b split | VERIFIED | feature_evaluator.py lines 182-308; P1a/P1b split at 2025-10-31/2025-11-01 boundary; 12 tests pass including test_zone_width_spread_positive |
| 3 | Entry-time truncation guard slices bar_df at BarIndex before calling compute_features — verified by canary test | VERIFIED | feature_evaluator.py line 230: bar_df_full.iloc[:bar_index]; TestEntryTimeCanary::test_lookahead_feature_blocked passes |
| 4 | Post-entry touch_row columns (Reaction, Penetration, RxnBar_*, PenBar_*, etc.) are stripped before passing to compute_features | VERIFIED | SAFE_TOUCH_COLUMNS list defined lines 61-66; safe_touch_row = touch_row[safe_cols_present] at lines 232, 262; TestEntryTimeCanary::test_post_entry_columns_stripped confirms stripping |
| 5 | Each feature result dict contains entry_time_violation boolean — flows through evaluate_features.py dispatcher unchanged | VERIFIED | entry_time_violation embedded inside each feature dict (not top-level); dispatcher only forwards result["features"]; TestEntryTimeCanary::test_violation_flag_per_feature confirms per-feature flag |
| 6 | program.md has machine-readable METRIC, KEEP RULE, BUDGET, NEW_FEATURE fields and a max-30-lines comment | VERIFIED | program.md is 19 lines (under 30-line limit); has all 4 fields: METRIC: spread, KEEP RULE: 0.15, BUDGET: 300, NEW_FEATURE: zone_width |

#### Plan 02 Must-Haves

| # | Truth | Status | Evidence |
|---|-------|--------|---------|
| 7 | Driver enforces 300-experiment budget from statistical_gates.md — refuses experiment 301 | VERIFIED | driver.py line 214: n_prior_tests >= budget check; parse_program_md reads BUDGET from program.md; TestBudgetEnforcement::test_stops_at_budget passes |
| 8 | Driver copies feature_engine.py to current_best/ on keep, restores from current_best/ on revert | VERIFIED | driver.py lines 292-302: shutil.copy2 in both directions; TestKeepRevert::test_keep_copies_to_current_best and test_revert_restores_from_current_best pass |
| 9 | Driver runs evaluate_features.py dispatcher as subprocess with --archetype flag | VERIFIED | driver.py lines 229-238: subprocess.run([sys.executable, evaluate_features_path, "--archetype", archetype, "--output", result_json_path]) |
| 10 | Driver reads per-feature entry_time_violation boolean from feature_evaluation.json features_evaluated list | VERIFIED | driver.py line 286: entry_time_violation = bool(feature_dict.get("entry_time_violation", False)); TestEntryTimeViolation::test_violation_blocks_keep passes |

#### Plan 03 Must-Haves

| # | Truth | Status | Evidence |
|---|-------|--------|---------|
| 11 | Freeze script reads current_best/feature_engine.py and writes frozen_features.json | VERIFIED | freeze_features.py lines 107-155; uses importlib introspection to load current_best/feature_engine.py, calls compute_features with dummy inputs to discover feature keys; frozen_features.json exists at stages/02-features/output/frozen_features.json with {"features": ["zone_width"], "frozen_date": "2026-03-14", "source": "current_best/feature_engine.py"} |

---

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `shared/archetypes/zone_touch/feature_engine.py` | Seeded baseline with compute_features | VERIFIED | Exists, 50 lines, `def compute_features` present, line 1 `# archetype: zone_touch`, zone_width computes (ZoneTop-ZoneBot)/tick_size |
| `shared/archetypes/zone_touch/feature_evaluator.py` | MWU spread with entry-time guard | VERIFIED | Exists, 309 lines, imports mannwhitneyu, full MWU implementation, SAFE_TOUCH_COLUMNS defined, per-feature entry_time_violation |
| `stages/02-features/autoresearch/program.md` | Machine-readable steering | VERIFIED | Exists, 19 lines (under 30), all 4 fields present, 30-line constraint comment on line 2 |
| `tests/test_feature_evaluator.py` | MWU spread + canary tests | VERIFIED | Exists, TestMWUSpread (4 tests), TestEntryTimeCanary (3 tests), TestFeatureEvaluatorInterface (5 tests); 12 tests total |
| `stages/02-features/autoresearch/driver.py` | Keep/revert loop, budget enforcement | VERIFIED | Exists, 389 lines (exceeds min_lines: 150), `def run_loop` present, 15 tests pass |
| `tests/test_stage02_driver.py` | Driver unit tests | VERIFIED | Exists, TestBudgetEnforcement (3 tests), TestKeepRevert (4 tests), TestEntryTimeViolation (1 test), parse tests (3), TSV structure tests (4); 15 tests total |
| `stages/02-features/autoresearch/results.tsv` | Experiment log with spread values | VERIFIED | Exists, 23 data rows, stage=02-features in all rows, spread=44.094 (numeric, non-empty), all 24 columns |
| `stages/02-features/autoresearch/current_best/feature_engine.py` | Seeded baseline for overnight run | VERIFIED | Exists, identical to shared/archetypes/zone_touch/feature_engine.py, `compute_features` present |
| `stages/02-features/freeze_features.py` | Human-triggered freeze script | VERIFIED | Exists, writes frozen_features.json via importlib introspection, "frozen_features.json" present in source |
| `stages/02-features/output/.gitkeep` | Output directory tracking | VERIFIED | Exists (0 bytes), output/frozen_features.json also present |

---

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| feature_evaluator.py | feature_engine.py | importlib.util.spec_from_file_location | WIRED | Line 87: spec = importlib.util.spec_from_file_location("feature_engine", str(engine_path)) |
| feature_evaluator.py | shared/data_loader.py | from shared.data_loader import | WIRED | Line 44: from shared.data_loader import load_bars, load_touches |
| feature_evaluator.py | evaluate_features.py dispatcher | entry_time_violation per-feature | WIRED | entry_time_violation embedded inside each feature dict, not top-level; dispatcher forwards result["features"] list unchanged |
| driver.py | evaluate_features.py | subprocess with --archetype flag | WIRED | Lines 229-238: subprocess.run([sys.executable, evaluate_features_path, "--archetype", archetype, "--output", result_json_path]) |
| driver.py | current_best/feature_engine.py | shutil.copy2 | WIRED | Lines 292-302: copy in both directions for keep and revert |
| driver.py | feature_evaluation.json | reads features_evaluated, checks entry_time_violation per feature | WIRED | Lines 260, 264-267, 286: json.loads, iterates features_evaluated, feature_dict.get("entry_time_violation", False) |
| driver.py | results.tsv | _append_tsv_row | WIRED | Lines 347: _append_tsv_row(results_tsv_path, row) with 24-column row |

---

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|---------|
| AUTO-06 | Plans 02, 03 | Stage 02 driver.py written (feature keep/revert, entry-time enforcement, 300 budget) | SATISFIED | driver.py exists (389 lines), shutil.copy2 keep/revert, budget check line 214, entry_time_violation per-feature, 15 tests pass |
| AUTO-07 | Plan 01 | Stage 02 program.md written (<=30 lines) | SATISFIED | program.md exists, 19 lines, all 4 machine-readable fields present |
| AUTO-08 | Plans 01, 03 | Stage 02 overnight test (20 experiments, feature spread values, entry-time block verified) | SATISFIED | results.tsv has 23 rows (3 budget + 20 smoke); all spreads numeric (44.094); entry-time canary tested by TestEntryTimeCanary (3 tests); human approval confirmed in 06-03-SUMMARY.md |

No orphaned requirements found. All Phase 6 requirements (AUTO-06, AUTO-07, AUTO-08) are claimed by plans and fully implemented.

---

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| feature_evaluator.py | 8, 209 | TODO: Replace Reaction fallback with precomputed pnl_ticks | Info | Known design decision: outcome variable is Reaction until precomputed PnL column is available. Documented in 06-01-SUMMARY.md as user-confirmed choice (precomputed-pnl selected, Reaction used as fallback). Does not block goal. |
| driver.py | 145-147 | `# TODO: fill in` inside audit log template string | Info | These TODOs are inside the audit log entry format string — they are instructions to the human reviewer, not implementation gaps. The log template is correct. Does not block goal. |

No blockers or warnings. Both patterns are intentional and documented.

---

### Human Verification Required

#### 1. Entry-time canary manual confirmation (optional)

**Test:** Temporarily edit feature_engine.py to add `bar_df.iloc[int(touch_row['BarIndex']) + 100]` and run one experiment with `python stages/02-features/autoresearch/driver.py --archetype zone_touch --n-experiments 1`
**Expected:** results.tsv last row shows verdict='entry_time_violation'
**Why human:** Automated tests (TestEntryTimeCanary) already verify this programmatically. Manual confirmation is only needed if additional confidence is required.

#### 2. Outcome variable recalibration

**Test:** Once a precomputed PnL column (`pnl_ticks`) is added to the touch CSV (as the user selected in Task 0), re-run feature evaluation and compare spread values to current Reaction-proxy values.
**Expected:** Spread values will change; keep threshold (0.15) may need recalibration against true PnL.
**Why human:** Requires running a reference backtest to generate pnl_ticks column, which is out of scope for Phase 6.

---

### Gaps Summary

No gaps. All 11 must-haves verified, all 3 ROADMAP success criteria verified. Phase goal achieved.

The one design caveat (Reaction proxy instead of precomputed PnL) is a documented, user-confirmed decision captured in 06-01-SUMMARY.md. The TODO comment exists to prompt future action, not to indicate incomplete implementation.

All commits verified:
- f8c2ac3 — feat(06-01): implement MWU spread evaluator and feature_engine.py baseline
- 14c2041 — feat(06-01): create Stage 02 program.md with machine-readable steering fields
- da9f58d — feat(06-02): implement Stage 02 driver.py keep/revert loop
- 2bed885 — feat(06-03): seed current_best, create freeze script, verify budget enforcement
- 4eda1df — feat(06-03): run 20-experiment smoke test and fix freeze script path resolution

---

_Verified: 2026-03-14_
_Verifier: Claude (gsd-verifier)_
