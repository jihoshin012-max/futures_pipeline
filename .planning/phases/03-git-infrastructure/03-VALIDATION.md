---
phase: 3
slug: git-infrastructure
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-13
---

# Phase 3 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.0.2 |
| **Config file** | none — discovered automatically |
| **Quick run command** | `python -m pytest tests/test_git_infrastructure.py -x -q` |
| **Full suite command** | `python -m pytest tests/ -x -q` |
| **Estimated runtime** | ~15 seconds |

---

## Sampling Rate

- **After every task commit:** Run `python -m pytest tests/test_git_infrastructure.py -x -q`
- **After every plan wave:** Run `python -m pytest tests/ -x -q`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 15 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 03-01-01 | 01 | 1 | GIT-01 | manual smoke | `bash autocommit.sh &; sleep 35; git log --oneline \| head -3` | ❌ W0 | ⬜ pending |
| 03-01-02 | 01 | 1 | GIT-02 | unit (subprocess) | `python -m pytest tests/test_git_infrastructure.py::test_holdout_guard -x` | ❌ W0 | ⬜ pending |
| 03-01-03 | 01 | 1 | GIT-02 | unit (subprocess) | `python -m pytest tests/test_git_infrastructure.py::test_audit_append_only -x` | ❌ W0 | ⬜ pending |
| 03-01-04 | 01 | 1 | GIT-03 | unit (subprocess) | `python -m pytest tests/test_git_infrastructure.py::test_commit_log -x` | ❌ W0 | ⬜ pending |
| 03-01-05 | 01 | 1 | GIT-03 | integration | `python -m pytest tests/test_git_infrastructure.py::test_oos_run_entry -x` | ❌ W0 | ⬜ pending |
| 03-01-06 | 01 | 1 | GIT-04 | manual | see verification sequence in RESEARCH.md | manual | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_git_infrastructure.py` — subprocess-based hook tests in temp git repo (GIT-01 through GIT-03)
- [ ] No new framework install needed — pytest 9.0.2 already present

*Existing infrastructure covers framework requirements.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| autocommit.sh fires within 30s | GIT-01 | Requires background process and real-time observation | Start `bash autocommit.sh &`, modify a file, wait 35s, check `git log --oneline` |
| Full end-to-end verification sequence | GIT-04 | Integration of all components in running repo | Follow verification sequence in RESEARCH.md |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 15s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
