# Phase 3: Git Infrastructure - Research

**Researched:** 2026-03-13
**Domain:** Git hooks, file-watching autocommit, append-only audit enforcement, Windows/MSYS2 bash
**Confidence:** HIGH — all specs are fully transcribed in architecture and functional spec docs in-repo

---

## Summary

Phase 3 builds three tightly coupled components: a polling autocommit watcher (`autocommit.sh`), a pre-commit hook enforcing holdout guard and audit integrity, and a post-commit hook maintaining a commit log and auto-generating audit entries. All three components are fully specified in `Futures_Pipeline_Architecture_ICM.md` and `Futures_Pipeline_Functional_Spec.md` — this is a transcription-and-verify phase, not a design phase.

The critical environmental fact: this repo runs on Windows 10 with Git for Windows (MSYS2 bash 5.2, git 2.53). The hook scripts run inside git's embedded bash, not a separate WSL shell. `grep -P` (Perl regex) is unavailable — the architecture doc uses it once for period extraction from the lockfile path, and a `sed`-based alternative must be substituted. `nohup` and `python` (resolves to `/c/Python314/python`) are both available in MSYS2 bash.

Post-commit hooks that call `git commit --amend --no-edit` do NOT re-trigger the post-commit hook in git — this is standard git behavior and the architecture relies on it correctly. The planner must not introduce a recursion guard unless testing reveals otherwise.

**Primary recommendation:** Transcribe hook code verbatim from architecture doc, apply the one grep-P fix, chmod both hooks, and run the four-step verification sequence. Do not deviate from the architecture's design.

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| GIT-01 | autocommit.sh — 30s poll, auto: prefix, nohup-compatible, run_id contract | Full script in Architecture doc lines 546-563; run_id contract in Functional Spec Task 1.5-01 |
| GIT-02 | .git/hooks/pre-commit — holdout guard, audit append-only, HYPOTHESIS_PROMOTED, PERIOD_CONFIG_CHANGED, period rollover warning | Full script in Architecture doc lines 573-592 (holdout) + lines 1313-1363 (audit additions) |
| GIT-03 | .git/hooks/post-commit — commit_log.txt, OOS_RUN, DEPLOYMENT_APPROVED auto-entries | Full script in Architecture doc lines 566-570 (log) + lines 1369-1411 (audit additions) |
| GIT-04 | Infrastructure verification — autocommit tested, holdout guard tested, commit log verified | Verification sequence in Functional Spec Task 1.5-04 (lines 1711-1726) |
</phase_requirements>

---

## Standard Stack

### Core
| Tool | Version | Purpose | Why Standard |
|------|---------|---------|--------------|
| bash | 5.2 (MSYS2) | Hook scripts and autocommit watcher | Required by git hooks on this system |
| git | 2.53 (Windows) | VCS, hook execution, diff/log commands | Project VCS |
| python | 3.14.2 | JSON parsing in post-commit hook (OOS_RUN verdict read) | Already installed, used by existing pipeline |
| pytest | 9.0.2 | Test harness for verification tests | Already in use (tests/ directory) |

### Supporting
| Tool | Version | Purpose | When to Use |
|------|---------|---------|-------------|
| nohup | MSYS2 built-in | Run autocommit.sh as background process surviving terminal close | Starting the watcher |
| git add -A | — | Stage all changes inside autocommit.sh | Captures new and modified files each poll cycle |
| git commit --amend --no-edit | — | Attach audit entry to same commit as flag creation | Post-commit hook OOS_RUN and DEPLOYMENT_APPROVED only |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Polling every 30s | inotifywait (Linux) | inotifywait not available on this Windows/MSYS2 setup — polling is the correct approach |
| grep -P for period extraction | sed / grep -o | grep -P fails with "supports only unibyte and UTF-8" on this MSYS2 build — use `sed 's/.*locked_\([^.]*\).*/\1/'` instead |
| python3 command | python command | python3 resolves to Microsoft Store stub (non-functional); `python` resolves to `/c/Python314/python` — use `python` in all hook scripts |

**Installation:** No new packages needed. All tools are already present.

---

## Architecture Patterns

### File Locations
```
C:/Projects/pipeline/
├── autocommit.sh                          # GIT-01: root-level watcher script
├── .git/
│   ├── hooks/
│   │   ├── pre-commit                     # GIT-02: holdout guard + audit enforcement
│   │   └── post-commit                    # GIT-03: commit log + audit auto-entries
│   └── commit_log.txt                     # Written by post-commit hook (auto-created)
├── audit/
│   └── audit_log.md                       # Append-only audit trail
└── stages/04-backtest/p2_holdout/
    └── holdout_locked_P2.flag             # Protected file — pre-commit blocks modification
```

### Pattern 1: Polling Autocommit
**What:** A `while true; sleep 30` loop that checks `git diff`, `git diff --cached`, and untracked files, then does `git add -A` + `git commit` if anything changed.
**When to use:** Always running during autoresearch sessions.
**Canonical source:** Architecture doc lines 546-563.
```bash
# Source: Futures_Pipeline_Architecture_ICM.md lines 546-563
#!/bin/bash
WATCH_DIR="$(git rev-parse --show-toplevel)"
POLL_INTERVAL=30

while true; do
    sleep $POLL_INTERVAL
    cd "$WATCH_DIR"
    if ! git diff --quiet || ! git diff --cached --quiet || [ -n "$(git ls-files --others --exclude-standard)" ]; then
        CHANGED=$(git diff --name-only; git ls-files --others --exclude-standard)
        TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')
        git add -A
        git commit -m "auto: $TIMESTAMP | $(echo $CHANGED | tr '\n' ' ' | cut -c1-80)"
    fi
done
```
**run_id contract:** Driver scripts must call `git rev-parse --short HEAD` immediately after each experiment and write the 7-char hash to the `run_id` column in results.tsv before the next 30s commit fires.

### Pattern 2: Pre-Commit Guard (Five Responsibilities)
**What:** Exits non-zero to abort commit on policy violations; auto-stages audit entries before commit finalizes.
**Order of checks (must match this order per spec):**
1. Block commits that touch any file under `stages/04-backtest/p2_holdout/` — hard abort
2. Block line deletions from `audit/audit_log.md` — hard abort
3. Auto-generate `HYPOTHESIS_PROMOTED` entry when file appears in `03-hypothesis/output/promoted_hypotheses/`
4. Auto-generate `PERIOD_CONFIG_CHANGED` entry when `_config/period_config.md` is in staged diff
5. Print rollover warning when period_config.md changes — does NOT abort

**Canonical source:** Architecture doc lines 573-592 (holdout block) + lines 1313-1363 (audit additions).

### Pattern 3: Post-Commit Hook (Three Responsibilities)
**What:** Runs after every commit. Appends to commit_log.txt unconditionally; auto-generates audit entries for flag file creations using `git diff-tree`.
**Amend behavior:** When `holdout_locked_P2.flag` or `deployment_ready.flag` is committed, the hook appends to audit_log.md and runs `git commit --amend --no-edit` to fold the audit entry into the same commit. Git does NOT re-fire the post-commit hook on amend — no infinite loop.

**Canonical source:** Architecture doc lines 566-570 (commit log) + lines 1366-1411 (audit additions).

### Pattern 4: Commit Message Conventions
All commits must follow prefix conventions used by dashboard filtering and lineage reconstruction grep commands:

| Prefix | Author | Example |
|--------|--------|---------|
| `auto:` | autocommit.sh | `auto: 2026-03-15 02:14:33 \| results.tsv` |
| `manual:` | Human | `manual: end-to-end baseline verified` |
| `promote:` | Human | `promote: {hypothesis_id} → 05-assessment` |
| `deploy:` | Human | `deploy: {strategy_id} approved` |

### Anti-Patterns to Avoid
- **Using `grep -P` in hook scripts:** Fails silently or with error on this MSYS2 build. Use `grep -o` + `sed` for pattern extraction.
- **Using `python3` in hook scripts:** Resolves to Windows Store stub, produces no output. Use `python`.
- **Recursive amend:** Do not add a guard inside post-commit that checks for amend — git's own design prevents re-firing on amend.
- **Blocking on period rollover:** The spec says warn (print to stderr), do NOT exit 1, for the period_config.md reminder.
- **Blocking the entire `p2_holdout/` path vs specific files:** The spec says block any file under `stages/04-backtest/p2_holdout/` — use a path prefix check, not a fixed list of three specific files.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead |
|---------|-------------|-------------|
| File change detection | Custom inotify/fsevents wrapper | 30-second polling with `git diff --quiet` — sufficient for this use case and portable |
| Audit entry generation | Custom templating system | Bash heredoc into audit_log.md — already established pattern in audit_entry.sh |
| JSON parsing in hooks | bash string manipulation | `python -c "import json; ..."` — one-liner already in architecture doc |
| Commit log | External logging service | `.git/commit_log.txt` append via echo — simple, local, sufficient |

**Key insight:** All complexity in this domain is in the edge cases of hook ordering and git internals. The architecture doc has already solved these — transcribe faithfully rather than redesigning.

---

## Common Pitfalls

### Pitfall 1: grep -P Unavailable on MSYS2
**What goes wrong:** `grep -oP 'locked_\K[^.]+'` in the post-commit hook returns exit code 2 with "grep: -P supports only unibyte and UTF-8 locales" on this system's MSYS2 bash.
**Why it happens:** Git for Windows ships its own grep that does not support Perl-mode regex.
**How to avoid:** Replace with `sed 's/.*locked_\([^.]*\).*/\1/'` for period extraction. Verified working on this system.
**Affected line:** Architecture doc line 1374 — the `PERIOD=$(echo "$LOCKFILE" | grep -oP ...)` line in the post-commit OOS_RUN block.

### Pitfall 2: python3 vs python in Hook Scripts
**What goes wrong:** `python3` in hook scripts launches the Windows Store stub that produces no output and exits with an error.
**Why it happens:** `/c/Users/jshin/AppData/Local/Microsoft/WindowsApps/python3` is a stub installer, not the real interpreter.
**How to avoid:** Use `python` which resolves to `/c/Python314/python` (Python 3.14.2, functional).
**Affected lines:** Architecture doc lines 1377-1379 — the three `python3 -c` calls in OOS_RUN verdict reading.

### Pitfall 3: Post-Commit Infinite Loop (Theoretical — Not Actual)
**What goes wrong:** If a guard isn't in place, `git commit --amend --no-edit` inside post-commit could re-trigger post-commit infinitely.
**Why it doesn't happen:** Git does not re-trigger the post-commit hook when `--amend` is used from within a hook. This is documented git behavior.
**How to avoid:** Do not add a recursion guard (it would be dead code and confusing). If unexpected behavior appears during testing, investigate git version first.

### Pitfall 4: Audit Log Append-Only Check False Positives
**What goes wrong:** The append-only check `git diff --cached -- audit/audit_log.md | grep -q "^-[^-]"` fires on the diff header lines (`---`) as well as actual deletions.
**Why it happens:** The grep pattern `^-[^-]` correctly excludes `---` header lines (second char is `-`). But if the audit log contains lines starting with `-` followed by `-` for some other reason, they'd be excluded. The pattern is correct for markdown content.
**How to avoid:** Use the exact pattern from the architecture doc. Do not simplify to `grep -q "^-"` which would catch diff headers.

### Pitfall 5: autocommit.sh Commits .planning/ and Other Meta Files
**What goes wrong:** `git add -A` stages everything including planning docs, research files, and any temp files — all go into auto-commits.
**Why it's acceptable:** This is intentional per the architecture. Full experiment trail is preserved. The commit message truncates to 80 chars so large file lists don't break commit messages.
**How to avoid:** Don't add a `.gitignore` exception for planning files unless explicitly instructed. The dense commit history is a feature.

### Pitfall 6: Pre-Commit Hook Modifies audit_log.md But Append-Only Check Already Passed
**What goes wrong:** The pre-commit hook itself appends to audit_log.md and then stages it with `git add audit/audit_log.md`. If the append-only check runs AFTER this staging, it would see the hook's own additions as legitimate. If the order is wrong, the hook checks the wrong state.
**Why it's safe:** Append-only check runs FIRST (step 2), before any auto-generation (steps 3-4). The hook's own appends only add lines, never delete — they pass the check trivially. Order matters and the architecture doc specifies it correctly.

---

## Code Examples

### autocommit.sh (complete, with Windows fix applied)
```bash
# Source: Futures_Pipeline_Architecture_ICM.md lines 546-563
# Windows fix: no changes needed — all commands available in MSYS2 bash
#!/bin/bash
WATCH_DIR="$(git rev-parse --show-toplevel)"
POLL_INTERVAL=30

while true; do
    sleep $POLL_INTERVAL
    cd "$WATCH_DIR"
    if ! git diff --quiet || ! git diff --cached --quiet || [ -n "$(git ls-files --others --exclude-standard)" ]; then
        CHANGED=$(git diff --name-only; git ls-files --others --exclude-standard)
        TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')
        git add -A
        git commit -m "auto: $TIMESTAMP | $(echo $CHANGED | tr '\n' ' ' | cut -c1-80)"
    fi
done
```

### Pre-commit holdout guard block (complete)
```bash
# Source: Futures_Pipeline_Architecture_ICM.md lines 573-592
#!/bin/bash
PROTECTED=(
    "stages/04-backtest/p2_holdout/holdout_locked_P2.flag"
    "stages/04-backtest/p2_holdout/trade_log_p2.csv"
    "stages/04-backtest/p2_holdout/equity_curve_p2.csv"
)

for f in "${PROTECTED[@]}"; do
    if git diff --cached --name-only | grep -q "$f"; then
        echo "ERROR: Attempted commit modifies protected P2 holdout file: $f"
        echo "P2 holdout is write-once. Aborting commit."
        exit 1
    fi
done
```

### Post-commit OOS_RUN block (with Windows grep-P fix)
```bash
# Source: Futures_Pipeline_Architecture_ICM.md lines 1369-1393
# Windows fix applied: grep -oP replaced with sed
LOCKFILE=$(git diff-tree --no-commit-id -r --name-only HEAD | grep "holdout_locked")
if [ -n "$LOCKFILE" ]; then
    TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')
    PERIOD=$(echo "$LOCKFILE" | sed 's/.*locked_\([^.]*\).*/\1/')   # <-- fixed from grep -oP
    VERDICT_FILE="stages/05-assessment/output/verdict_report.json"
    PF=$(python -c "import json; d=json.load(open('$VERDICT_FILE')); print(d.get('pf','unknown'))" 2>/dev/null || echo "unknown")
    N=$(python -c "import json; d=json.load(open('$VERDICT_FILE')); print(d.get('n_trades','unknown'))" 2>/dev/null || echo "unknown")
    VERDICT=$(python -c "import json; d=json.load(open('$VERDICT_FILE')); print(d.get('verdict','unknown'))" 2>/dev/null || echo "unknown")
    # ... append to audit/audit_log.md, git add, git commit --amend --no-edit
fi
```

### Verification sequence (GIT-04)
```bash
# Source: Futures_Pipeline_Functional_Spec.md Task 1.5-04 (lines 1711-1726)

# Test GIT-01: autocommit fires within 30s
echo "test autocommit" >> README.md
sleep 35 && git log --oneline | head -5   # should show auto: commit

# Test GIT-02: holdout guard blocks
touch stages/04-backtest/p2_holdout/holdout_locked_P2.flag
git add stages/04-backtest/p2_holdout/holdout_locked_P2.flag
git commit -m "test: should be blocked"  # must abort

# Test GIT-02: audit append-only blocks deletions
# (stage a deletion in audit_log.md and attempt commit — must abort)

# Confirm hooks are executable
ls -la .git/hooks/pre-commit .git/hooks/post-commit

# Confirm autocommit running
ps aux | grep autocommit
```

---

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.0.2 |
| Config file | none — discovered automatically |
| Quick run command | `python -m pytest tests/test_git_infrastructure.py -x -q` |
| Full suite command | `python -m pytest tests/ -x -q` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| GIT-01 | autocommit.sh starts, polls, commits on change | manual smoke | `bash autocommit.sh &; sleep 35; git log --oneline \| head -3` | ❌ Wave 0 |
| GIT-02 | pre-commit blocks p2_holdout modification | unit (subprocess) | `python -m pytest tests/test_git_infrastructure.py::test_holdout_guard -x` | ❌ Wave 0 |
| GIT-02 | pre-commit blocks audit_log.md deletions | unit (subprocess) | `python -m pytest tests/test_git_infrastructure.py::test_audit_append_only -x` | ❌ Wave 0 |
| GIT-03 | post-commit writes to commit_log.txt | unit (subprocess) | `python -m pytest tests/test_git_infrastructure.py::test_commit_log -x` | ❌ Wave 0 |
| GIT-03 | post-commit writes OOS_RUN on flag creation | integration | `python -m pytest tests/test_git_infrastructure.py::test_oos_run_entry -x` | ❌ Wave 0 |
| GIT-04 | Full verification sequence passes | manual | see verification sequence above | manual |

**Note:** Hook tests require subprocess calls into a temp git repo with installed hooks. This is the standard pattern for testing git hooks in Python — create a temp repo, install hooks, stage changes, assert outcomes.

### Sampling Rate
- **Per task commit:** `python -m pytest tests/test_git_infrastructure.py -x -q`
- **Per wave merge:** `python -m pytest tests/ -x -q`
- **Phase gate:** Full suite green + manual verification sequence (GIT-04) before marking phase complete

### Wave 0 Gaps
- [ ] `tests/test_git_infrastructure.py` — covers GIT-01 through GIT-03 (subprocess-based hook testing in temp repo)
- [ ] No new framework install needed — pytest 9.0.2 already present

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| inotify-based file watching (Linux) | 30s polling loop | N/A (Windows project) | Polling is the only viable approach on Windows/MSYS2 without additional tools |
| grep -P for Perl regex | sed or grep -o alternatives | MSYS2 git bash limitation | One line in post-commit hook needs substitution |

**No deprecated items.** The architecture is freshly specified for this project.

---

## Open Questions

1. **The success criteria says "a commit that touches any file under 04-backtest/p2_holdout/" — but the architecture doc's pre-commit guard only lists three specific files**
   - What we know: Architecture doc lines 579-583 list `holdout_locked_P2.flag`, `trade_log_p2.csv`, `equity_curve_p2.csv` as the protected files
   - What's unclear: Does "any file under p2_holdout/" mean we need a path-prefix block instead of the three-file list?
   - Recommendation: Implement a path-prefix check (`grep -q "stages/04-backtest/p2_holdout/"`) that covers the entire folder, satisfying both the success criteria and the spirit of the architecture. This is strictly safer than the three-file list.

2. **The post-commit OOS_RUN hook reads `stages/05-assessment/output/verdict_report.json` — this file doesn't exist yet**
   - What we know: verdict_report.json is created by the backtest engine (Phase 4, not yet built)
   - What's unclear: Should the hook gracefully degrade when the file is absent?
   - Recommendation: The architecture already handles this — the `|| echo "unknown"` fallbacks on all three python calls produce "unknown" values if the file is missing. This is correct behavior for Phase 3.

3. **The `deployment_ready.flag` path is not explicitly stated in the architecture**
   - What we know: It's detected by `grep "deployment_ready.flag"` on diff-tree output; the post-commit reads `stages/06-deployment/output/*.cpp`
   - What's unclear: Which subdirectory of `stages/06-deployment/` the flag lives in
   - Recommendation: The grep pattern matches any path containing "deployment_ready.flag" so the exact location doesn't need to be hardcoded in the hook. Use the architecture's grep approach and document that the flag should be placed in `stages/06-deployment/output/` by convention.

---

## Sources

### Primary (HIGH confidence)
- `Futures_Pipeline_Architecture_ICM.md` lines 540-612 — autocommit.sh full script, basic hook scripts, setup steps, commit message conventions
- `Futures_Pipeline_Architecture_ICM.md` lines 1311-1411 — full pre-commit audit additions (HYPOTHESIS_PROMOTED, PERIOD_CONFIG_CHANGED, append-only check) and post-commit audit additions (OOS_RUN, DEPLOYMENT_APPROVED)
- `Futures_Pipeline_Functional_Spec.md` lines 1640-1726 — Task 1.5-01 through 1.5-04, done-checks, run_id contract, verification sequence

### Secondary (MEDIUM confidence)
- Live MSYS2 bash testing: `grep -P` failure confirmed, `sed` alternative verified, `python` vs `python3` confirmed, `nohup` confirmed available
- Git behavior: `git commit --amend` from within post-commit hook does not re-trigger the hook (standard git design, confirmed by absence of guard in architecture doc)

### Tertiary (LOW confidence — flag for validation)
- Assumption that `git diff --cached --name-only | grep -q "stages/04-backtest/p2_holdout/"` (path prefix) is a correct expansion of the three-file list — needs human confirmation during GIT-02 implementation

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all tools confirmed present and functional on this machine
- Architecture: HIGH — fully specified in in-repo documents; one grep-P fix confirmed with live testing
- Pitfalls: HIGH — grep-P and python3 issues confirmed by live execution; other pitfalls derived from architecture doc analysis

**Research date:** 2026-03-13
**Valid until:** Stable — no external dependencies; valid until architecture docs are revised
