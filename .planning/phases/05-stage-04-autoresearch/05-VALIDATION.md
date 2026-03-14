---
phase: 5
slug: stage-04-autoresearch
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-14
---

# Phase 5 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (existing, verified working in Phase 4) |
| **Config file** | none — pytest auto-discovers tests/ directory |
| **Quick run command** | `python -m pytest tests/test_driver.py -x -v` |
| **Full suite command** | `python -m pytest tests/ -v` |
| **Estimated runtime** | ~30 seconds |

---

## Sampling Rate

- **After every task commit:** Run `python -m pytest tests/test_driver.py -x -v`
- **After every plan wave:** Run `python -m pytest tests/ -v`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 30 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 05-01-01 | 01 | 1 | AUTO-01 | unit | `python -m pytest tests/test_driver.py::test_budget_enforcement -x -v` | ❌ W0 | ⬜ pending |
| 05-01-02 | 01 | 1 | AUTO-01 | unit | `python -m pytest tests/test_driver.py::test_revert_restores_prior -x -v` | ❌ W0 | ⬜ pending |
| 05-01-03 | 01 | 1 | AUTO-01 | unit | `python -m pytest tests/test_driver.py::test_experiment_anomaly -x -v` | ❌ W0 | ⬜ pending |
| 05-01-04 | 01 | 1 | AUTO-02 | doc | `python -m pytest tests/test_driver.py::test_program_md_format -x -v` | ❌ W0 | ⬜ pending |
| 05-02-01 | 02 | 1 | AUTO-04 | unit | `python -m pytest tests/test_evaluate_features.py -x -v` | ❌ W0 | ⬜ pending |
| 05-02-02 | 02 | 1 | AUTO-05 | unit | `python -m pytest tests/test_feature_evaluator.py -x -v` | ❌ W0 | ⬜ pending |
| 05-03-01 | 03 | 2 | AUTO-03 | integration | manual overnight run + `wc -l results.tsv` | N/A | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_driver.py` — stubs for AUTO-01, AUTO-02 (budget enforcement, keep/revert, anomaly handling, program.md format)
- [ ] `tests/test_evaluate_features.py` — stubs for AUTO-04
- [ ] `tests/test_feature_evaluator.py` — stubs for AUTO-05

*No new framework install needed — pytest already in use.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| 50-experiment overnight run completes unattended | AUTO-03 | Requires real time passage and full engine execution | Run `python driver.py` with budget=50, verify results.tsv has 50 rows with monotonic IDs |
| Kept experiment visible in git history | AUTO-03 | Requires autocommit.sh integration | Check `git log` after overnight run for autocommit entries |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 30s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
