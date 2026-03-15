---
phase: 02-feature-evaluator-screening
plan: "03"
subsystem: rotational-archetype
tags: [phase1b, classification, robustness, screening, advancement]
dependency_graph:
  requires: [02-02]
  provides: [phase1b_classification.md, phase1b_classification.json]
  affects: [Phase 3 TDS sizing sweep, Phase 4 combinations]
tech_stack:
  added: []
  patterns: [spec-section-3.7-classification-matrix, RTH-filtered-cross-bar-type-comparison]
key_files:
  created:
    - shared/archetypes/rotational/run_phase1b_classification.py
    - shared/archetypes/rotational/test_phase1b_classification.py
    - shared/archetypes/rotational/screening_results/phase1b_classification.md
    - shared/archetypes/rotational/screening_results/phase1b_classification.json
  modified: []
decisions:
  - "H19 disposition: SKIPPED_REFERENCE_REQUIRED — defer to Phase 4 when multi-source reference available"
  - "Phase 1b classification uses RTH-filtered results for cross-bar-type consistency (spec Section 3.7 Pitfall 6)"
  - "All 40 rankable hypotheses classify as NO_SIGNAL at default params — expected, fixed trigger ignores computed features"
  - "Strategic: before Phase 3 TDS, a sizing sweep (MaxLevels x MaxContractSize) is required"
metrics:
  duration: ~20 minutes
  completed_date: "2026-03-15"
  tasks_completed: 2
  files_created: 4
  files_modified: 0
---

# Phase 02 Plan 03: Phase 1b Cross-Bar-Type Classification Summary

**One-liner:** Phase 1b robustness classification of all 41 hypotheses via spec Section 3.7 matrix using RTH-filtered results, with human approval and H19 deferred to Phase 4.

## What Was Built

Applied the Phase 1b cross-bar-type robustness framework (spec Section 3.7) to classify all 41 hypotheses from Phase 1 screening. The classification uses RTH-filtered results (`phase1_results_rth.tsv`) to ensure a consistent time window across the three bar types for fair comparison.

**Script:** `run_phase1b_classification.py` reads RTH-filtered TSV, applies the classification matrix, and outputs human-readable markdown and machine-readable JSON.

**Tests:** `test_phase1b_classification.py` covers all 8 classification branches, H37 special handling (2-bar-type framework), H19 SKIPPED_REFERENCE_REQUIRED handling, and beats_baseline string-to-bool conversion.

## Classification Results

| Category | Count | Advancement Decision |
|----------|-------|----------------------|
| NO_SIGNAL | 40 | DO_NOT_ADVANCE |
| SKIPPED_REFERENCE_REQUIRED | 1 (H19) | NOT_TESTED |

**All 40 rankable hypotheses classified as NO_SIGNAL** — this is the expected result at default params. The fixed trigger mechanism ignores computed features, so `beats_baseline=False` for all experiments is by design. Phase 1b establishes the structural baseline profile; Phase 3 (TDS) / Phase 4 (Combinations) will use parameter tuning to find hypotheses that beat the baseline.

## Human Review Outcome

**Status:** APPROVED (2026-03-15)

- Advancement list approved as-is
- **H19 disposition:** SKIPPED_REFERENCE_REQUIRED — skip H19 in current phases; add to Phase 4 when multi-source reference is available

## Strategic Context Recorded

Human provided important context for sequencing:
- Before Phase 3 parameter-tuned hypothesis screening, a **sizing sweep is required**: MaxLevels x MaxContractSize
- This sizing sweep must complete first so Phase 3 TDS tuning operates on the correct position-sizing configuration

## Decisions Made

1. **H19 deferred to Phase 4** — Bar-type divergence signal requires simultaneous multi-source access not available in the single-source runner. Will re-evaluate when runner is extended.

2. **RTH filtering is the correct basis for Phase 1b classification** — vol/tick bars are pre-filtered to RTH window via `_apply_rth_filter()`, ensuring apples-to-apples cross-bar-type comparison per spec Section 3.7 Pitfall 6.

3. **NO_SIGNAL for all hypotheses at default params is expected** — confirmed by human review. Phase 1 screening established structural baseline; the signal discovery happens in Phase 3.

4. **Sizing sweep before Phase 3** — strategic gate added to sequencing.

## Deviations from Plan

None — plan executed exactly as written. Human checkpoint approved without reclassification requests.

## Verification

- All 41 hypotheses classified (40 ranked + 1 NOT_TESTED)
- H37 classified using 2-bar-type framework (vol + tick only, 10sec=N/A)
- H19 excluded from ranking with SKIPPED_REFERENCE_REQUIRED
- beats_baseline string-to-bool conversion tested and working
- Human reviewed and approved advancement decisions
- phase1b_classification.json ready for Phase 4 consumption

## Self-Check: PASSED

Files confirmed present:
- shared/archetypes/rotational/run_phase1b_classification.py
- shared/archetypes/rotational/test_phase1b_classification.py
- shared/archetypes/rotational/screening_results/phase1b_classification.md
- shared/archetypes/rotational/screening_results/phase1b_classification.json

Commits confirmed:
- 7e4c911: feat(02-03): build Phase 1b classification script and generate results
- 5e74eec: feat(02-03): record human approval of Phase 1b classification results
