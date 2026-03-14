---
phase: 06-stage-02-autoresearch
plan: 02
subsystem: feature-autoresearch
tags: [driver, keep-revert, budget-enforcement, entry-time-violation, tdd]
dependency_graph:
  requires: [stages/02-features/autoresearch/evaluate_features.py, shared/archetypes/zone_touch/feature_evaluator.py]
  provides: [stages/02-features/autoresearch/driver.py]
  affects: [stages/02-features/autoresearch/results.tsv, stages/02-features/autoresearch/current_best/feature_engine.py]
tech_stack:
  added: []
  patterns: [keep-revert-loop, budget-enforcement, subprocess-dispatch, sha-run-id, non-fatal-git-commit]
key_files:
  created:
    - stages/02-features/autoresearch/driver.py
    - tests/test_stage02_driver.py
  modified: []
decisions:
  - entry_time_violation read per-feature from features_evaluated list (not top-level key) — dispatcher drops top-level keys
  - pf_p1 TSV column carries spread value (Stage 02 metric reuses dashboard column)
  - Keep rule is threshold-based (spread > keep_rule AND mwu_p < 0.10), not improvement-based like Stage 04
  - parse_program_md requires 4 fields (metric, keep_rule, budget, new_feature) — Stage 04 only required 3
  - feature_engine.py path resolved as repo_root/shared/archetypes/{archetype}/feature_engine.py
metrics:
  duration_minutes: 10
  completed_date: "2026-03-14"
  tasks_completed: 1
  files_created: 2
---

# Phase 6 Plan 2: Stage 02 Driver Keep/Revert Loop Summary

Stage 02 driver.py implementing the feature autoresearch keep/revert loop with budget enforcement, entry-time violation detection, and 4-field program.md parsing (METRIC, KEEP RULE, BUDGET, NEW_FEATURE).

## What Was Built

### stages/02-features/autoresearch/driver.py (new, 247 lines)

Adapted from Stage 04 driver with these key differences:

- **No parameter proposal**: agent edits feature_engine.py directly; driver only runs harness, evaluates, logs
- **Subprocess target**: runs `evaluate_features.py --archetype {archetype} --output feature_evaluation.json`
- **File copied**: feature_engine.py (not exit_params.json); copies to/from `current_best/`
- **Keep rule**: `spread > keep_rule AND mwu_p < 0.10` (threshold-based, not improvement over baseline)
- **Entry-time violation**: reads `entry_dict.get("entry_time_violation", False)` from the matching feature in `features_evaluated` list — does NOT check top-level key (dispatcher drops top-level keys from `evaluate()` return value)
- **program.md**: 4 required fields (adds `NEW_FEATURE` vs Stage 04's 3 fields)
- **TSV column mapping**: `pf_p1` carries spread, `mwu_p` carries MWU p-value, `features` carries feature name

Reused verbatim from Stage 04: `_generate_run_id()`, `_git_commit()`, `_count_tsv_rows()`, `_append_tsv_row()`, `TSV_HEADER` (24-column standard), lockfile pattern, anomaly logging pattern.

### tests/test_stage02_driver.py (new, 15 tests)

TDD: tests written first (RED), driver written to pass (GREEN).

Test classes and functions:
- `TestBudgetEnforcement`: 3 tests — stops at budget, runs under budget, re-reads program.md mid-run
- `TestKeepRevert`: 4 tests — copies to current_best on keep, restores from current_best on revert, verdict='kept' in TSV, verdict='reverted' in TSV
- `TestEntryTimeViolation`: 1 test — entry_time_violation=True blocks keep regardless of spread/mwu_p
- `test_parse_program_md`, `test_parse_program_md_missing_field`, `test_parse_program_md_missing_budget`: 3 parse tests
- `test_tsv_row_has_24_columns`, `test_tsv_stage_column_is_02_features`, `test_tsv_spread_in_pf_p1_column`, `test_tsv_mwu_p_column`: 4 structure tests

## Verification

```
pytest tests/test_stage02_driver.py -q
15 passed in 0.30s

pytest tests/test_stage02_driver.py tests/test_driver.py tests/test_evaluate_features.py tests/test_feature_evaluator.py tests/test_git_infrastructure.py tests/test_scaffold_adapter.py -q
64 passed, 1 skipped in 12.12s
```

No regressions in related test files.

## Deviations from Plan

None — plan executed exactly as written.

The driver implemented all must_haves:
- Budget enforcement from program.md, refuses experiment when n_prior_tests >= budget
- Copies feature_engine.py to current_best/ on keep, restores from current_best/ on revert
- Runs evaluate_features.py dispatcher as subprocess with --archetype flag
- Reads per-feature entry_time_violation from features_evaluated list
- Parses program.md with METRIC, KEEP RULE, BUDGET, NEW_FEATURE fields
- Generates unique run_id per experiment via SHA hash
- Appends one TSV row per experiment with Stage 02 column mapping (24 columns)

## Commits

| Hash | Message |
|------|---------|
| da9f58d | feat(06-02): implement Stage 02 driver.py keep/revert loop |

## Self-Check: PASSED
