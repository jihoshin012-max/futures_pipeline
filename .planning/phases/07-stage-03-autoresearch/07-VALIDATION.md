---
phase: 7
slug: stage-03-autoresearch
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-14
---

# Phase 7 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (existing, tests/ at repo root) |
| **Config file** | none — run from repo root |
| **Quick run command** | `pytest tests/test_stage03_driver.py tests/test_hypothesis_generator.py -x -q` |
| **Full suite command** | `pytest tests/ -x -q` |
| **Estimated runtime** | ~30 seconds |

---

## Sampling Rate

- **After every task commit:** Run `pytest tests/test_stage03_driver.py tests/test_hypothesis_generator.py -x -q`
- **After every plan wave:** Run `pytest tests/ -x -q`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 30 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 07-01-01 | 01 | 1 | AUTO-09 | unit | `pytest tests/test_hypothesis_generator.py::TestRunnerOutputs -x` | ❌ W0 | ⬜ pending |
| 07-01-02 | 01 | 1 | AUTO-09 | unit | `pytest tests/test_hypothesis_generator.py::TestP1bFilter -x` | ❌ W0 | ⬜ pending |
| 07-01-03 | 01 | 1 | AUTO-10 | unit | `pytest tests/test_stage03_driver.py::TestBudgetEnforcement -x` | ❌ W0 | ⬜ pending |
| 07-01-04 | 01 | 1 | AUTO-10 | unit | `pytest tests/test_stage03_driver.py::TestReplicationEnforcement::test_p1b_fail_reverts` | ❌ W0 | ⬜ pending |
| 07-01-05 | 01 | 1 | AUTO-10 | unit | `pytest tests/test_stage03_driver.py::TestReplicationEnforcement::test_p1b_pass_keeps` | ❌ W0 | ⬜ pending |
| 07-01-06 | 01 | 1 | AUTO-11 | unit | `pytest tests/test_stage03_driver.py::test_parse_program_md -x` | ❌ W0 | ⬜ pending |
| 07-02-01 | 02 | 2 | AUTO-12 | integration | `pytest tests/test_stage03_driver.py::TestOvernightSmoke -x` | ❌ W0 | ⬜ pending |
| 07-03-01 | 03 | 2 | AUTO-13 | unit | `pytest tests/test_assess_feedback.py::TestFeedbackOutput -x` | ❌ W0 | ⬜ pending |
| 07-03-02 | 03 | 2 | AUTO-13 | unit | `pytest tests/test_assess_feedback.py::TestFeedbackWiring -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_stage03_driver.py` — stubs for AUTO-10, AUTO-11, AUTO-12 driver tests
- [ ] `tests/test_hypothesis_generator.py` — stubs for AUTO-09 generator tests
- [ ] `tests/test_assess_feedback.py` — stubs for AUTO-13 feedback wiring tests

*Existing test infrastructure (`tests/test_driver.py`, `tests/test_stage02_driver.py`) requires no changes.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| 12-experiment overnight run completes end-to-end | AUTO-12 | Requires real data + engine + ~30min runtime | Run `python stages/03-hypothesis/autoresearch/driver.py --budget 12` and verify results.tsv |
| current_best/hypothesis_config.json seeded correctly | AUTO-10 | One-time human setup prerequisite | Copy Stage 04 current_best/exit_params.json |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 30s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
