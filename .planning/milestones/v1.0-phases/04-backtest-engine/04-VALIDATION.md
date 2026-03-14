---
phase: 4
slug: backtest-engine
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-14
---

# Phase 4 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (already in use — tests/test_scaffold_adapter.py, test_hmm_regime_fitter.py) |
| **Config file** | none (no pytest.ini or conftest.py yet; tests run from repo root) |
| **Quick run command** | `python -m pytest tests/test_backtest_engine.py -x -v` |
| **Full suite command** | `python -m pytest tests/ -v` |
| **Estimated runtime** | ~15 seconds |

---

## Sampling Rate

- **After every task commit:** Run `python -m pytest tests/test_backtest_engine.py -x -v`
- **After every plan wave:** Run `python -m pytest tests/ -v`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 15 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 04-01-01 | 01 | 1 | ENGINE-01 | smoke | `python -m pytest tests/test_backtest_engine.py::test_qa_doc_complete -x` | ❌ W0 | ⬜ pending |
| 04-01-02 | 01 | 1 | ENGINE-02 | unit | `python -m pytest tests/test_data_loader.py -x` | ❌ W0 | ⬜ pending |
| 04-01-03 | 01 | 1 | ENGINE-03 | integration | `python -m pytest tests/test_backtest_engine.py::test_engine_produces_output -x` | ❌ W0 | ⬜ pending |
| 04-01-04 | 01 | 1 | ENGINE-04 | unit | `python -m pytest tests/test_backtest_engine.py::test_config_validation -x` | ❌ W0 | ⬜ pending |
| 04-01-05 | 01 | 1 | ENGINE-05 | smoke | `python -m pytest tests/test_backtest_engine.py::test_schema_doc_coverage -x` | ❌ W0 | ⬜ pending |
| 04-01-06 | 01 | 1 | ENGINE-06 | integration | `python -m pytest tests/test_backtest_engine.py::test_determinism -x` | ❌ W0 | ⬜ pending |
| 04-01-07 | 01 | 1 | ENGINE-07 | manual | Manual review after end-to-end pass | N/A | ⬜ pending |
| 04-01-08 | 01 | 1 | ENGINE-08 | smoke | `python -m pytest tests/test_backtest_engine.py::test_simulation_rules_doc -x` | ❌ W0 | ⬜ pending |
| 04-01-09 | 01 | 1 | ENGINE-09 | unit | `python -m pytest tests/test_backtest_engine.py::test_adapter_validation_aborts -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_backtest_engine.py` — stubs for ENGINE-01, ENGINE-03, ENGINE-04, ENGINE-05, ENGINE-06, ENGINE-08, ENGINE-09
- [ ] `tests/test_data_loader.py` — stubs for ENGINE-02
- [ ] No framework install needed (pytest already present from prior phases)

*Existing infrastructure covers framework requirements.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| verdict_report.md is well-formed with net-of-cost Sharpe < 80% gross Sharpe | ENGINE-07 | End-to-end pass requires full pipeline run (Stage 01→04→05) with real data | Run manual 01-to-05 pass, inspect verdict_report.md for well-formedness and Sharpe ratio comparison |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 15s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
