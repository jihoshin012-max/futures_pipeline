---
phase: 6
slug: stage-02-autoresearch
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-14
---

# Phase 6 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (existing, tests/ at repo root) |
| **Config file** | none — run from repo root |
| **Quick run command** | `pytest tests/test_feature_evaluator.py tests/test_stage02_driver.py -x -q` |
| **Full suite command** | `pytest tests/ -x -q` |
| **Estimated runtime** | ~30 seconds |

---

## Sampling Rate

- **After every task commit:** Run `pytest tests/test_feature_evaluator.py tests/test_stage02_driver.py -x -q`
- **After every plan wave:** Run `pytest tests/ -x -q`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 30 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 06-01-01 | 01 | 1 | AUTO-06 | unit | `pytest tests/test_stage02_driver.py::TestBudgetEnforcement -x` | ❌ W0 | ⬜ pending |
| 06-01-02 | 01 | 1 | AUTO-06 | unit | `pytest tests/test_stage02_driver.py::TestKeepRevert -x` | ❌ W0 | ⬜ pending |
| 06-01-03 | 01 | 1 | AUTO-06 | unit | `pytest tests/test_stage02_driver.py::TestEntryTimeViolation -x` | ❌ W0 | ⬜ pending |
| 06-01-04 | 01 | 1 | AUTO-07 | unit | `pytest tests/test_stage02_driver.py::test_parse_program_md -x` | ❌ W0 | ⬜ pending |
| 06-02-01 | 02 | 1 | AUTO-08 | integration | `pytest tests/test_feature_evaluator.py::TestMWUSpread -x` | ❌ W0 | ⬜ pending |
| 06-02-02 | 02 | 1 | AUTO-08 | integration | `pytest tests/test_feature_evaluator.py::TestEntryTimeCanary -x` | ❌ W0 | ⬜ pending |
| 06-03-01 | 03 | 2 | AUTO-08 | integration | `pytest tests/test_stage02_driver.py::TestOvernightSmoke -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_stage02_driver.py` — new file; covers AUTO-06, AUTO-07, AUTO-08 driver tests
- [ ] `tests/test_feature_evaluator.py` — extends existing Phase 5 file; add MWU spread and canary tests for Phase 6
- [ ] `shared/archetypes/zone_touch/feature_engine.py` — seeded baseline with zone_width before tests can run

*Existing `tests/test_evaluate_features.py` and `tests/test_feature_evaluator.py` from Phase 5 require no changes to pass.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| 20-experiment overnight smoke test produces valid results.tsv | AUTO-08 | Requires full pipeline run with real data | Run driver.py with --n-experiments 20, verify results.tsv has 20 rows with spread values |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 30s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
