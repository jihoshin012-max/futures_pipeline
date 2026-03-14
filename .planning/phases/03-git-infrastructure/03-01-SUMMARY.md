---
phase: 03-git-infrastructure
plan: 01
subsystem: infra
tags: [git, bash, hooks, pre-commit, post-commit, audit, autocommit, windows, msys2]

requires:
  - phase: 01-scaffold
    provides: audit/audit_log.md format and audit/audit_entry.sh pattern that hooks append to

provides:
  - autocommit.sh polling watcher (30s, auto: prefix)
  - .git/hooks/pre-commit (holdout guard + audit append-only + HYPOTHESIS_PROMOTED + PERIOD_CONFIG_CHANGED)
  - .git/hooks/post-commit (commit_log.txt + OOS_RUN + DEPLOYMENT_APPROVED)
  - tests/test_git_infrastructure.py (8 subprocess-based hook tests, all passing)

affects:
  - phase-04-backtest-engine (requires pre-commit holdout guard to protect p2_holdout/)
  - all-autoresearch-sessions (autocommit.sh must be running)
  - audit-trail (all audit auto-entries from hooks)

tech-stack:
  added: []
  patterns:
    - "bash heredoc append to audit/audit_log.md via cat >> then git add"
    - "lock file recursion guard for git commit --amend in post-commit hooks on Windows/MSYS2"
    - "subprocess-based git hook testing via tmp_path fixture with pre/post-commit hook installation"

key-files:
  created:
    - autocommit.sh
    - tests/test_git_infrastructure.py
  modified:
    - .git/hooks/pre-commit (new file, tracked as created)
    - .git/hooks/post-commit (new file, tracked as created)

key-decisions:
  - "Path-prefix holdout guard: grep -q stages/04-backtest/p2_holdout/ catches all files under the directory, not just the three named files in architecture doc — strictly safer"
  - "Grep pattern for audit append-only fixed: ^-[^-] fails on markdown list lines (- subject: seed becomes -- subject: seed in diff); use grep ^- | grep -v ^--- instead"
  - "Recursion guard added to post-commit: git commit --amend DOES re-fire post-commit on Windows/MSYS2 git 2.53 (contradicting architecture doc); lock file at .git/post-commit-amend.lock prevents infinite loop"
  - "python not python3 in all hook scripts: python3 resolves to Windows Store stub on this machine"
  - "sed instead of grep -oP for period extraction: grep -P unavailable on MSYS2 git bash"

patterns-established:
  - "Pattern: Recursion guard for amend-triggering hooks on Windows — touch .git/post-commit-amend.lock before amend, rm after"
  - "Pattern: Audit append-only diff check uses grep ^- | grep -v ^--- (not ^-[^-]) to handle markdown list items in diffs"
  - "Pattern: Subprocess hook tests disable pre-commit temporarily by renaming to .bak when testing post-commit-only behavior"

requirements-completed: [GIT-01, GIT-02, GIT-03]

duration: 13min
completed: 2026-03-14
---

# Phase 03 Plan 01: Git Infrastructure Summary

**Bash hooks enforcing holdout guard, append-only audit trail, and auto-generating OOS_RUN/HYPOTHESIS_PROMOTED audit entries — with Windows/MSYS2 recursion guard for git commit --amend**

## Performance

- **Duration:** 13 min
- **Started:** 2026-03-14T03:02:06Z
- **Completed:** 2026-03-14T03:15:24Z
- **Tasks:** 2 (TDD: RED + GREEN)
- **Files modified:** 4 (test file + autocommit.sh + 2 hooks)

## Accomplishments
- autocommit.sh polling watcher at repo root (30s interval, auto: prefix, nohup-compatible)
- pre-commit hook: holdout guard (path-prefix), audit append-only enforcement, HYPOTHESIS_PROMOTED + PERIOD_CONFIG_CHANGED auto-entries with rollover warning
- post-commit hook: commit_log.txt, OOS_RUN auto-entry on holdout flag creation, DEPLOYMENT_APPROVED auto-entry on deploy flag creation
- 8 subprocess-based tests covering all hook behaviors — all passing, full suite 31 passed 1 skipped

## Task Commits

Each task was committed atomically:

1. **Task 1: Create test scaffold for git infrastructure** - `c154841` (test)
2. **Task 2: Create autocommit.sh, pre-commit hook, and post-commit hook** - `98253eb` (feat)

_Note: TDD tasks: Task 1 = RED commit, Task 2 = GREEN commit (hooks + autocommit.sh)_

## Files Created/Modified
- `tests/test_git_infrastructure.py` - 9 test functions, subprocess-based hook testing in tmp_path temp repos
- `autocommit.sh` - 30s polling watcher at repo root
- `.git/hooks/pre-commit` - holdout guard + audit append-only + HYPOTHESIS_PROMOTED + PERIOD_CONFIG_CHANGED
- `.git/hooks/post-commit` - commit_log.txt + OOS_RUN + DEPLOYMENT_APPROVED + Windows recursion guard

## Decisions Made
- Path-prefix holdout guard replaces three-file list — per RESEARCH.md recommendation, strictly safer
- Audit append-only grep pattern fixed from `^-[^-]` to `grep "^-" | grep -v "^---"` — the original architecture doc pattern fails on markdown list items in diffs (a `- subject:` line becomes `-- subject:` in the diff, which `^-[^-]` excludes incorrectly)
- Recursion guard added to post-commit — architecture doc and RESEARCH.md both stated git does NOT re-trigger post-commit on --amend, but empirical testing on this Windows/MSYS2 git 2.53 system proved it DOES; lock file prevents infinite loop

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed audit append-only grep pattern for markdown list content**
- **Found during:** Task 2 (running tests GREEN)
- **Issue:** `grep -q "^-[^-]"` does not match deleted lines whose content starts with `- ` (markdown list syntax). In git diff, a deleted line `- subject: seed` appears as `-- subject: seed` — the second char is `-`, so `^-[^-]` excludes it, allowing the deletion silently.
- **Fix:** Changed to `git diff --cached -- audit/audit_log.md | grep "^-" | grep -qv "^---"` — matches all deletion lines (starting with single `-`) and excludes only diff headers (`---`).
- **Files modified:** `.git/hooks/pre-commit`
- **Verification:** `test_audit_append_only_blocks_deletion` passes; `test_audit_append_only_allows_append` still passes (no false positives)
- **Committed in:** `98253eb` (Task 2 commit)

**2. [Rule 1 - Bug] Added recursion guard to post-commit hook for Windows/MSYS2**
- **Found during:** Task 2 (running tests GREEN — test_oos_run_entry was hanging)
- **Issue:** Architecture doc states `git commit --amend --no-edit` inside post-commit does NOT re-trigger post-commit. This is FALSE on Windows/MSYS2 git 2.53 — the hook fires again causing infinite recursion and process hang.
- **Fix:** Added lock file guard: `AMEND_LOCK="$(git rev-parse --git-dir)/post-commit-amend.lock"`. Before each amend: `touch $AMEND_LOCK`. On re-entry: `[ -f $AMEND_LOCK ] && exit 0`. After amend: `rm -f $AMEND_LOCK`.
- **Files modified:** `.git/hooks/post-commit`
- **Verification:** `test_oos_run_entry` now passes in 13 seconds with no hanging processes
- **Committed in:** `98253eb` (Task 2 commit)

---

**Total deviations:** 2 auto-fixed (2 Rule 1 bugs)
**Impact on plan:** Both fixes necessary for correctness. First fix makes the audit guard actually work on this project's audit log format. Second fix prevents infinite process recursion on Windows. No scope creep.

## Issues Encountered
- Architecture doc and RESEARCH.md both contained incorrect claims about git --amend hook behavior on Windows/MSYS2. Discovered through empirical testing during GREEN phase. Fixed inline via deviation Rule 1.

## User Setup Required
None — no external service configuration required. To start the autocommit watcher: `bash autocommit.sh &`

## Next Phase Readiness
- Git infrastructure complete. Phase 4 (backtest engine) may now rely on pre-commit holdout guard.
- To activate autocommit during autoresearch: `bash autocommit.sh &` or `nohup bash autocommit.sh &`
- Hooks are installed in .git/hooks/ and active immediately

---
*Phase: 03-git-infrastructure*
*Completed: 2026-03-14*

## Self-Check: PASSED

- tests/test_git_infrastructure.py: FOUND
- autocommit.sh: FOUND
- .git/hooks/pre-commit: FOUND
- .git/hooks/post-commit: FOUND
- 03-01-SUMMARY.md: FOUND
- Commit c154841: FOUND
- Commit 98253eb: FOUND
