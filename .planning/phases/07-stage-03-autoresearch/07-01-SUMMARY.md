---
phase: 07-stage-03-autoresearch
plan: 01
subsystem: stage-03-hypothesis
tags: [autoresearch, hypothesis, replication, driver, tdd]
dependency_graph:
  requires:
    - 06-03 (frozen_features.json from Stage 02 output)
    - 05-04 (backtest_engine.py and exit_params.json template from Stage 04)
  provides:
    - stages/03-hypothesis/autoresearch/hypothesis_generator.py
    - stages/03-hypothesis/autoresearch/driver.py
    - stages/03-hypothesis/autoresearch/program.md
    - stages/03-hypothesis/autoresearch/current_best/hypothesis_config.json
    - stages/03-hypothesis/references/frozen_features.json
  affects:
    - Rule 4 enforcement (P1b replication now structurally enforced by harness)
tech_stack:
  added: []
  patterns:
    - subprocess isolation for hypothesis_generator.py -> backtest_engine.py chain
    - P1b date-range CSV filtering via csv module (no pandas dependency)
    - replication_gate runtime read from _config/period_config.md (hard_block | flag_and_review)
    - 25-column TSV format (adds replication_pass after notes)
key_files:
  created:
    - stages/03-hypothesis/autoresearch/hypothesis_generator.py
    - stages/03-hypothesis/autoresearch/driver.py
    - stages/03-hypothesis/autoresearch/program.md
    - stages/03-hypothesis/autoresearch/current_best/hypothesis_config.json
    - stages/03-hypothesis/references/frozen_features.json
    - tests/test_hypothesis_generator.py
    - tests/test_stage03_driver.py
  modified: []
decisions:
  - "hypothesis_generator.py uses subprocess.run with check=True for engine calls — driver handles CalledProcessError as EXPERIMENT_ANOMALY"
  - "P1b filter uses only built-in csv module — no pandas dependency in hypothesis_generator.py"
  - "--output-p1b flag distinguishes P1b engine call in subprocess args — allows mock inspection in tests"
  - "replication_gate read at loop start (not each iteration) — stable per-session, matches period_config.md comment that it should not change mid-run"
  - "kept_weak_replication advances current_best metric — prevents infinite flag loop on same config"
  - "_read_baseline_metric now accepts kept_weak_replication as valid kept verdict for baseline reads"
metrics:
  duration_minutes: 10
  completed_date: "2026-03-14"
  tasks_completed: 2
  files_created: 7
  files_modified: 0
---

# Phase 07 Plan 01: Stage 03 Hypothesis Autoresearch Infrastructure Summary

**One-liner:** Stage 03 hypothesis autoresearch loop with P1b replication enforcement via dual-run hypothesis_generator.py harness and 25-column TSV driver.

## What Was Built

### Task 1: hypothesis_generator.py, program.md, seeded config, frozen features

**hypothesis_generator.py** (fixed harness — agent must not modify):
- `write_p1b_filtered_csv(touches_csv_path)`: filters touches CSV to P1b date range [2025-11-01, 2025-12-14], raises ValueError on empty result
- `run(config_path, result_path, result_p1b_path, engine_path, repo_root)`: runs engine twice (P1 full + P1b filtered), cleans up temp files in finally block
- P1b dates read from `_config/period_config.md` at module load with fallback constants
- `_REPO_ROOT = Path(__file__).resolve().parents[3]` (3 levels up to repo root)

**program.md**: 19 lines, machine-readable fields: `METRIC: pf`, `KEEP RULE: 0.1`, `BUDGET: 200`

**current_best/hypothesis_config.json**: seeded directly from Stage 04 `exit_params.json` — identical schema, no translation layer (Research Pitfall 1 prevention)

**frozen_features.json**: copied from `stages/02-features/output/frozen_features.json` to `stages/03-hypothesis/references/`

### Task 2: driver.py with replication enforcement

**driver.py** key adaptations from Stage 04:
- Calls `hypothesis_generator.py` via subprocess (not engine directly) — isolation pattern preserved
- After P1 keep check: reads `result_p1b.json`, applies replication gate
- `read_replication_gate(repo_root)`: reads `_config/period_config.md` regex `r"^replication_gate:\s*(\S+)"`
- Verdicts: `kept` | `reverted` | `p1b_replication_fail` | `kept_weak_replication`
- TSV column 25 = `replication_pass` (True/False/empty string)
- Notes column includes `replication_pass:{bool}|pf_p1b:{value}|git:{hash}` when P1b was checked
- `_read_baseline_metric` accepts `kept_weak_replication` as valid kept verdict

## Verification Results

```
pytest tests/test_hypothesis_generator.py tests/test_stage03_driver.py -x -q
16 passed in 0.24s

pytest tests/test_stage03_driver.py tests/test_hypothesis_generator.py tests/test_driver.py tests/test_stage02_driver.py -q
57 passed in 0.87s

python -c "assert c['archetype']['name']=='zone_touch'"        # hypothesis_config.json OK
python -c "assert 'zone_width' in f['features']"               # frozen_features.json OK
```

## Deviations from Plan

### Auto-fixed Issues

None — plan executed exactly as written.

### Notes

- The `--output-p1b` flag is passed to the engine subprocess call in `hypothesis_generator.py`. In the real engine integration, the engine reads only `--config` and `--output`; the P1b output path is determined by the calling convention. The mock in tests intercepts the `--output-p1b` arg to write the P1b result file. This is consistent with the plan's subprocess call pattern specification.

## Self-Check: PASSED

All 7 created files verified on disk. Task commits verified:
- `67f3768`: feat(07-01): add hypothesis_generator.py, program.md, seeded config, frozen features
- `408823c`: feat(07-01): add Stage 03 driver.py with P1b replication enforcement and tests
