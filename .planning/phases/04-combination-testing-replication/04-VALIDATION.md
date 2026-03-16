---
phase: 4
slug: combination-testing-replication
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-16
---

# Phase 4 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (verified — all 60+ existing tests use pytest) |
| **Config file** | none required — run from archetype directory |
| **Quick run command** | `pytest shared/archetypes/rotational/test_combination_sweep.py -x -q` |
| **Full suite command** | `pytest shared/archetypes/rotational/ -x -q` |
| **Estimated runtime** | ~15 seconds (unit/smoke tests only) |

---

## Sampling Rate

- **After every task commit:** Run `pytest shared/archetypes/rotational/test_combination_sweep.py -x -q`
- **After every plan wave:** Run `pytest shared/archetypes/rotational/ -x -q`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 15 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 04-01-01 | 01 | 1 | ROT-RES-05 | smoke | `python run_combination_sweep.py --plan 1 --dry-run --limit 5` | ❌ W0 | ⬜ pending |
| 04-01-02 | 01 | 1 | ROT-RES-05 | unit | `pytest test_combination_sweep.py::test_inject_profile_martingale -x` | ❌ W0 | ⬜ pending |
| 04-01-03 | 01 | 1 | ROT-RES-05 | unit | `pytest test_combination_sweep.py::test_select_dimensional_winners -x` | ❌ W0 | ⬜ pending |
| 04-01-04 | 01 | 1 | ROT-RES-05 | unit | `pytest test_combination_sweep.py::test_h37_exclusion -x` | ❌ W0 | ⬜ pending |
| 04-02-01 | 02 | 2 | ROT-RES-06 | unit | `pytest test_combination_sweep.py::test_inject_tds_disabled_for_vol_tick -x` | ❌ W0 | ⬜ pending |
| 04-02-02 | 02 | 2 | ROT-RES-06 | unit | `pytest test_combination_sweep.py::test_inject_tds_velocity_l1_10sec -x` | ❌ W0 | ⬜ pending |
| 04-03-01 | 03 | 3 | ROT-RES-07 | unit | `pytest test_p1b_replication.py::test_p1b_period_used -x` | ❌ W0 | ⬜ pending |
| 04-03-02 | 03 | 3 | ROT-RES-07 | unit | `pytest test_p1b_replication.py::test_weak_replication_is_soft_gate -x` | ❌ W0 | ⬜ pending |
| 04-03-03 | 03 | 3 | ROT-RES-07 | unit | `pytest test_p1b_replication.py::test_classify_replication -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `shared/archetypes/rotational/test_combination_sweep.py` — unit + smoke tests for Plan 01/02 harness
- [ ] `shared/archetypes/rotational/test_p1b_replication.py` — unit tests for Plan 03 replication runner
- [ ] `shared/archetypes/rotational/combination_results/` — output directory (create at harness init)
- [ ] Verify `feature_engine.py` CBT support before H19 implementation

*All existing tests in test_hypothesis_configs.py, test_hypothesis_screening.py, test_tds_calibration.py, test_trend_defense.py, test_rotational_simulator.py remain as regression coverage.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Human review of Phase 4 report before Phase 5 | ROT-RES-07 | Judgment call on WEAK_REPLICATION candidates | Read combination_results/phase4_report.md, approve/reject candidates |
| Cross-bar-type consistency of winning combinations | ROT-RES-05 | Interpretation of statistical significance | Compare delta_pf across 3 bar types in phase4_combinations.tsv |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 15s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
