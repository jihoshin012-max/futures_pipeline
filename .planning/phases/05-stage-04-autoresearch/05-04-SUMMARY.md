---
phase: 05-stage-04-autoresearch
plan: 04
subsystem: autoresearch-driver
tags: [git-commits, run-id, hypothesis-name, lockfile, autocommit]
dependency_graph:
  requires: [05-01]
  provides: [event-driven-git-commits, unique-run-id, hypothesis-name-population, lockfile-coordination]
  affects: [autocommit.sh, stages/04-backtest/autoresearch/driver.py]
tech_stack:
  added: [hashlib]
  patterns: [event-driven-commits, try/finally-lockfile, hash-based-id]
key_files:
  created: []
  modified:
    - stages/04-backtest/autoresearch/driver.py
    - autocommit.sh
    - tests/test_driver.py
decisions:
  - "_generate_run_id uses SHA-256 hash of archetype:timestamp:experiment_n truncated to 8 hex chars — deterministic, unique, no git subprocess needed"
  - "hypothesis_name populated from promoted_hypothesis.json if present; falls back to archetype name (not empty string) — always non-empty in TSV"
  - "_git_commit failures are non-fatal (try/except pass) — git errors must not abort the experiment loop"
  - "Budget-exhausted git commit fires before break — final TSV state is committed even when no experiments are kept"
  - "Lockfile uses try/finally in run_loop — guaranteed cleanup on both normal completion and exceptions"
  - "test_program_md_reread updated to distinguish git vs engine calls via args[0] check — git calls must not be counted as engine calls"
metrics:
  duration_minutes: 25
  completed_date: "2026-03-14"
  tasks_completed: 2
  files_modified: 3
---

# Phase 05 Plan 04: Event-Driven Git Commits for Autoresearch Driver Summary

**One-liner:** Hash-based unique run_id, event-driven git commits at kept/exhausted/anomaly events, hypothesis_name from JSON, and lockfile suppression of autocommit.sh polling during autoresearch runs.

## What Was Built

### CHANGE 1 — `_generate_run_id(archetype, timestamp, experiment_n)`
Replaced `_get_run_id()` (git HEAD hash, same for all experiments in same commit) with a deterministic per-experiment hash. Uses `hashlib.sha256` on `archetype:timestamp:experiment_n`, truncated to 8 hex chars. No subprocess needed.

### CHANGE 2 — `_read_hypothesis_name(autoresearch_dir)`
Reads `promoted_hypothesis.json` from the autoresearch directory. Returns the `name` field if present, empty string if not. In `run_loop`, the TSV row uses the file value if non-empty, otherwise falls back to the archetype name (so the `hypothesis_name` column is always populated).

### CHANGE 3 — `_git_commit(repo_root, files, message)`
Non-fatal helper: calls `git add <files>` then `git commit -m <message>`. Exceptions are silently caught — git failures must not abort the experiment loop. Called at three events:
- **Kept:** `"auto: kept experiment N | pf=X.XXX | archetype | stage=04"`
- **Budget exhausted:** `"auto: stage-04 budget exhausted | N experiments | best pf=X.XXX | archetype"`
- **Anomaly:** `"auto: ANOMALY stage-04 experiment N | archetype | see audit_log.md"`

Reverted experiments produce NO commit.

### CHANGE 4 — Lockfile in `run_loop`
`repo_root / ".autoresearch_running"` is created at loop start and removed via `try/finally`. Guarantees removal even on exceptions.

### CHANGE 5 — `autocommit.sh` lockfile check
Added `if [ -f ".autoresearch_running" ]; then continue; fi` at the top of the polling loop. Prevents commit spam when autoresearch manages its own commits.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 (RED) | Failing tests for all new behaviors | 7515971 | tests/test_driver.py |
| 1 (GREEN) | Implement event-driven commits, run_id, hypothesis_name, lockfile | d47ef16 | driver.py, autocommit.sh, tests/test_driver.py |
| 2 | Integration: 10-experiment run, verify event-driven commits | e192a47 | results.tsv (restored) |

## Verification Results

### Automated tests
```
26 passed in 0.27s
```
All 26 driver tests pass — 17 pre-existing + 9 new.

### Integration run (10 experiments, budget=10)
- results.tsv: 11 rows (header + seed + 10 experiments) confirmed
- run_ids: all 8-char hex hashes, all unique (verified with assertion script)
- hypothesis_name: `zone_touch` (archetype fallback, no promoted_hypothesis.json present)
- git log: `auto: kept experiment 2 | pf=0.810 | zone_touch | stage=04` + `auto: stage-04 budget exhausted | 10 experiments | best pf=0.810 | zone_touch` — only event-driven commits, no time-based autocommit entries
- .autoresearch_running: absent after completion (ls returns no such file)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] test_program_md_reread counted git calls as engine calls**
- **Found during:** Task 1 GREEN — test failed because `_mock_run_and_update` incremented `call_count[0]` for all subprocess.run calls
- **Issue:** After adding event-driven git commits, `subprocess.run` is called for both git and engine operations; the original mock didn't distinguish them
- **Fix:** Updated mock to check `args[0] == "git"` — git calls return rc=0 without incrementing `engine_call_count`; renamed `call_count` to `engine_call_count` for clarity
- **Files modified:** tests/test_driver.py
- **Commit:** d47ef16 (included in GREEN commit)

## Self-Check: PASSED

- `stages/04-backtest/autoresearch/driver.py` — exists, contains `_generate_run_id`, `_read_hypothesis_name`, `_git_commit`, lockfile logic
- `autocommit.sh` — exists, contains `.autoresearch_running` check
- `tests/test_driver.py` — exists, 26 tests all pass
- Commits 7515971, d47ef16, e192a47 — all present in git log
