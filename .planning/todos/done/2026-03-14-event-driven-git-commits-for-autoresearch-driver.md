---
created: 2026-03-14T17:15:47.157Z
title: Event-driven git commits for autoresearch driver
area: autoresearch
files:
  - stages/04-backtest/autoresearch/driver.py
  - autocommit.sh
---

## Problem

Phase 5 verification identified that the 50-experiment run produced a single batch commit rather than per-experiment commits. Batch commit was approved for Phase 5, but the autocommit.sh polling approach will produce commit spam at higher experiment counts in Phase 6 (budget 300) and Phase 7 (budget 200). Must fix before Phase 6 starts.

## Solution

Three coordinated changes:

**CHANGE 1 — driver.py:** Add explicit git commit calls at meaningful events only.

On kept experiment:
```
git add autoresearch/current_best/exit_params.json autoresearch/results.tsv
git commit -m "auto: kept experiment {n} | pf={pf:.3f} | {archetype} | stage=04"
```

On budget exhausted:
```
git add autoresearch/results.tsv
git commit -m "auto: stage-04 budget exhausted | {n} experiments | best pf={best_pf:.3f} | {archetype}"
```

On anomaly:
```
git add audit/audit_log.md autoresearch/results.tsv
git commit -m "auto: ANOMALY stage-04 experiment {n} | {archetype} | see audit_log.md"
```

**CHANGE 2 — autocommit.sh:** Suppress polling during autoresearch runs via lockfile check. Add at top of polling loop:
```bash
if [ -f ".autoresearch_running" ]; then
    sleep $POLL_INTERVAL
    continue
fi
```

**CHANGE 3 — driver.py:** Create and remove lockfile around the experiment loop:
- `touch .autoresearch_running` at loop start
- `rm -f .autoresearch_running` on completion or error (use try/finally)

**Note for Phase 6 and 7:** Apply the same pattern to Stage 02 and Stage 03 drivers when built. Use stage=02 and stage=03 in commit message prefixes.

## Done Check

- Run 10-experiment test
- git log shows only kept-experiment commits, not per-30s time-based commits
- results.tsv has all 10 rows regardless of keep/revert verdict
- .autoresearch_running lockfile present during run, removed on completion
- autocommit.sh skips polling while lockfile present
- Re-run Phase 5 success criterion: kept experiment config change visible in git log as individual commit
