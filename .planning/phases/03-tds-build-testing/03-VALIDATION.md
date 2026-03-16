---
phase: 3
slug: tds-build-testing
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-16
---

# Phase 3 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.0.2 |
| **Config file** | none (no pytest.ini — tests run from working directory) |
| **Quick run command** | `cd shared/archetypes/rotational && python -m pytest test_trend_defense.py -q` |
| **Full suite command** | `cd shared/archetypes/rotational && python -m pytest -q` |
| **Estimated runtime** | ~15 seconds |

---

## Sampling Rate

- **After every task commit:** Run `cd shared/archetypes/rotational && python -m pytest test_trend_defense.py -q`
- **After every plan wave:** Run `cd shared/archetypes/rotational && python -m pytest -q`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 15 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 03-01-01 | 01 | 1 | ROT-RES-04 | unit | `pytest test_trend_defense.py::test_tds_init -x` | ❌ W0 | ⬜ pending |
| 03-01-02 | 01 | 1 | ROT-RES-04 | unit | `pytest test_trend_defense.py::test_detector_retracement_quality -x` | ❌ W0 | ⬜ pending |
| 03-01-03 | 01 | 1 | ROT-RES-04 | unit | `pytest test_trend_defense.py::test_detector_velocity_monitor -x` | ❌ W0 | ⬜ pending |
| 03-01-04 | 01 | 1 | ROT-RES-04 | unit | `pytest test_trend_defense.py::test_detector_consecutive_adds -x` | ❌ W0 | ⬜ pending |
| 03-01-05 | 01 | 1 | ROT-RES-04 | unit | `pytest test_trend_defense.py::test_detector_drawdown_budget -x` | ❌ W0 | ⬜ pending |
| 03-01-06 | 01 | 1 | ROT-RES-04 | unit | `pytest test_trend_defense.py::test_detector_trend_precursor -x` | ❌ W0 | ⬜ pending |
| 03-01-07 | 01 | 1 | ROT-RES-04 | unit | `pytest test_trend_defense.py::test_level1_response -x` | ❌ W0 | ⬜ pending |
| 03-01-08 | 01 | 1 | ROT-RES-04 | unit | `pytest test_trend_defense.py::test_level2_response -x` | ❌ W0 | ⬜ pending |
| 03-01-09 | 01 | 1 | ROT-RES-04 | unit | `pytest test_trend_defense.py::test_level3_response -x` | ❌ W0 | ⬜ pending |
| 03-01-10 | 01 | 1 | ROT-RES-04 | unit | `pytest test_trend_defense.py::test_level3_reengage -x` | ❌ W0 | ⬜ pending |
| 03-02-01 | 02 | 2 | ROT-RES-04 | integration | `pytest test_trend_defense.py::test_simulator_integration -x` | ❌ W0 | ⬜ pending |
| 03-02-02 | 02 | 2 | ROT-RES-04 | integration | `pytest test_trend_defense.py::test_survival_metrics_improvement -x` | ❌ W0 | ⬜ pending |
| 03-02-03 | 02 | 2 | ROT-RES-04 | unit | `pytest test_trend_defense.py::test_bar_type_param_conversion -x` | ❌ W0 | ⬜ pending |
| 03-02-04 | 02 | 2 | ROT-RES-04 | unit | `pytest test_trend_defense.py::test_summary_metrics -x` | ❌ W0 | ⬜ pending |
| 03-02-05 | 02 | 2 | ROT-RES-04 | integration | `pytest test_trend_defense.py::test_hypothesis_feedins -x` | ❌ W0 | ⬜ pending |
| 03-02-06 | 02 | 2 | ROT-RES-04 | integration | `pytest test_trend_defense.py::test_dynamic_feature_wiring -x` | ❌ W0 | ⬜ pending |
| 03-02-07 | 02 | 2 | ROT-RES-04 | unit | `pytest test_trend_defense.py::test_determinism_tds -x` | ❌ W0 | ⬜ pending |
| 03-02-08 | 02 | 2 | ROT-RES-04 | unit | `pytest test_trend_defense.py::test_tds_disabled_passthrough -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `shared/archetypes/rotational/test_trend_defense.py` — all 18 test case stubs
- [ ] `shared/archetypes/rotational/trend_defense.py` — TDS implementation module
- [ ] `shared/archetypes/rotational/tds_results/` — output directory (create empty with .gitkeep)

*Existing test files `test_rotational_simulator.py`, `test_hypothesis_screening.py`, etc. continue to pass — no regressions expected since TDS is an additive feature behind `enabled=false` default.*

---

## Manual-Only Verifications

*All phase behaviors have automated verification.*

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 15s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
