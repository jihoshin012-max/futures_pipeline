---
phase: 02
slug: feature-evaluator-screening
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-15
---

# Phase 02 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (existing, same as Phase 1) |
| **Config file** | none — pytest auto-discovers tests |
| **Quick run command** | `pytest shared/archetypes/rotational/ -x -q` |
| **Full suite command** | `pytest tests/ shared/archetypes/rotational/ -v` |
| **Estimated runtime** | ~90 seconds (including slow real-data tests) |

---

## Sampling Rate

- **After every task commit:** Run `pytest shared/archetypes/rotational/ -x -q`
- **After every plan wave:** Run `pytest tests/ shared/archetypes/rotational/ -v`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 90 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 02-01-01 | 01 | 1 | ROT-RES-01 | unit | `pytest shared/archetypes/rotational/test_feature_evaluator.py -x` | ❌ W0 | ⬜ pending |
| 02-01-02 | 01 | 1 | ROT-RES-01 | unit | `pytest shared/archetypes/rotational/test_feature_evaluator.py -x -k "entry_time"` | ❌ W0 | ⬜ pending |
| 02-01-03 | 01 | 1 | ROT-RES-01 | unit | `pytest shared/archetypes/rotational/test_feature_evaluator.py -x -k "mwu"` | ❌ W0 | ⬜ pending |
| 02-02-01 | 02 | 2 | ROT-RES-02 | integration | `pytest shared/archetypes/rotational/test_hypothesis_screening.py -x` | ❌ W0 | ⬜ pending |
| 02-02-02 | 02 | 2 | ROT-RES-02 | unit | `pytest shared/archetypes/rotational/test_hypothesis_screening.py -x -k "h37"` | ❌ W0 | ⬜ pending |
| 02-02-03 | 02 | 2 | ROT-RES-02 | unit | `pytest shared/archetypes/rotational/test_hypothesis_screening.py -x -k "tsv"` | ❌ W0 | ⬜ pending |
| 02-03-01 | 03 | 3 | ROT-RES-03 | unit | `pytest shared/archetypes/rotational/test_phase1b_classification.py -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `shared/archetypes/rotational/test_feature_evaluator.py` — stubs for ROT-RES-01 (outcome types, entry-time safety, MWU)
- [ ] `shared/archetypes/rotational/test_hypothesis_screening.py` — stubs for ROT-RES-02 (3 bar types, H37 exclusion, TSV schema)
- [ ] `shared/archetypes/rotational/test_phase1b_classification.py` — stubs for ROT-RES-03 (robustness classification)

*Existing infrastructure covers pytest framework — no new framework install needed.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Phase 1b advancement decisions | ROT-RES-03 | Requires human judgment on borderline hypotheses | Review ranked advancement list, verify classification rationale |
| Tooling checkpoint: profile feature compute time | Phase note | Performance profiling not automatable | Time one experiment, check feature compute % of wall clock |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 90s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
