---
phase: 2
slug: hmm-regime-fitter
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-13
---

# Phase 2 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (installed; tests/ directory exists at repo root) |
| **Config file** | none — run from repo root |
| **Quick run command** | `python -m pytest tests/test_hmm_regime_fitter.py -v` |
| **Full suite command** | `python -m pytest tests/ -v` |
| **Estimated runtime** | ~15 seconds |

---

## Sampling Rate

- **After every task commit:** Run `python -m pytest tests/test_hmm_regime_fitter.py -x`
- **After every plan wave:** Run `python -m pytest tests/ -v`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 15 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 02-01-01 | 01 | 1 | HMM-01 | unit | `python -m pytest tests/test_hmm_regime_fitter.py::test_fit_uses_p1_only -x` | ❌ W0 | ⬜ pending |
| 02-01-02 | 01 | 1 | HMM-01 | unit | `python -m pytest tests/test_hmm_regime_fitter.py::test_model_converges -x` | ❌ W0 | ⬜ pending |
| 02-01-03 | 01 | 1 | HMM-01 | unit | `python -m pytest tests/test_hmm_regime_fitter.py::test_no_degenerate_states -x` | ❌ W0 | ⬜ pending |
| 02-01-04 | 01 | 1 | HMM-02 | unit | `python -m pytest tests/test_hmm_regime_fitter.py::test_labels_cover_full_range -x` | ❌ W0 | ⬜ pending |
| 02-01-05 | 01 | 1 | HMM-02 | unit | `python -m pytest tests/test_hmm_regime_fitter.py::test_label_values_valid -x` | ❌ W0 | ⬜ pending |
| 02-01-06 | 01 | 1 | HMM-03 | unit | `python -m pytest tests/test_hmm_regime_fitter.py::test_pkl_round_trip -x` | ❌ W0 | ⬜ pending |
| 02-01-07 | 01 | 1 | HMM-03 | unit | `python -m pytest tests/test_hmm_regime_fitter.py::test_pkl_model_predicts -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_hmm_regime_fitter.py` — stubs for HMM-01, HMM-02, HMM-03 (7 test functions)

*Existing `tests/test_scaffold_adapter.py` has 6 passing tests and covers no HMM requirements.*

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
