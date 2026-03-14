---
phase: 02-hmm-regime-fitter
plan: 01
subsystem: data
tags: [hmmlearn, GaussianHMM, hmm, regime, pandas, numpy, pickle, tdd]

# Dependency graph
requires:
  - phase: 01-scaffold
    provides: bar data files (NQ_BarData_*.txt), period_config.md, regime_definitions.md, shared/scoring_models/ directory
  - phase: 01.1-scoring-adapter-scaffold-generator
    provides: tests/ directory at repo root, pytest infrastructure

provides:
  - stages/01-data/hmm_regime_fitter.py with 10 importable functions
  - stages/01-data/data/labels/regime_labels.csv (144 rows, P1+P2 labeled)
  - shared/scoring_models/hmm_regime_v1.pkl (trend + volatility GaussianHMM models)
  - tests/test_hmm_regime_fitter.py (7 test functions covering HMM-01, HMM-02, HMM-03)

affects:
  - 03-backtest-engine (consumes regime_labels.csv and hmm_regime_v1.pkl read-only)
  - stages/02 through stages/07 (regime_labels.csv is pipeline-wide read-only label source)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - P1-only fit pattern: fit() receives only P1 rows; frozen model applied forward to P1+P2
    - Filtered-posterior labeling: predict_proba().argmax() not Viterbi predict()
    - P1-stat standardization: mean/std from P1 only; same transform applied to P2 (no leakage)
    - Three independent HMMs: one per label dimension (trend, volatility); macro is calendar-based
    - State name assignment by feature ordering: sort states by mean feature value; log assignment for audit

key-files:
  created:
    - stages/01-data/hmm_regime_fitter.py
    - tests/test_hmm_regime_fitter.py
    - stages/01-data/data/labels/regime_labels.csv
    - shared/scoring_models/hmm_regime_v1.pkl
  modified: []

key-decisions:
  - "Three independent GaussianHMMs (trend 2-state, volatility 3-state) plus hard-coded macro calendar — not joint HMM — because regime_labels.csv requires independent per-dimension columns"
  - "predict_proba().argmax() (filtered posteriors) used for hard label assignment, not predict() (Viterbi) — per pipeline requirements"
  - "P1 standardization stats (mean, std) stored as _p1_mean/_p1_std on fitted model for explicit downstream traceability"
  - "State name assignment by sorting model.means_ on the relevant feature column — deterministic and logged for audit"
  - "Macro events hard-coded as Python set (FOMC/CPI/NFP for 2025-09-16 to 2026-03-02, 12 event days) — no reference file needed for ~12 events"
  - "test_fit_uses_p1_only uses calendar days (90) not trading days (77) because synthetic fixture uses consecutive calendar dates — docstring explains the distinction"

patterns-established:
  - "P1-only fit: slice with p1_mask BEFORE calling fit(); assert row count matches expected before fit()"
  - "Standardize using P1 stats inline: (X - X_p1.mean()) / (X_p1.std() + 1e-8) — no sklearn dependency needed"
  - "Convergence assertion: assert model.monitor_.converged immediately after model.fit()"
  - "Non-degenerate assertion: assert len(np.unique(labels)) == n_components after each predict"
  - "Pickle protocol=4 for model serialization — verified round-trip in main() before logging done"
  - "Named aggregation syntax for pandas 3.0: agg(col=('src', func)) — avoids FutureWarning"
  - "Pure pandas ADX: ewm-based smoothing of TR/+DM/-DM — no TA library required"

requirements-completed: [HMM-01, HMM-02, HMM-03]

# Metrics
duration: 4min
completed: 2026-03-14
---

# Phase 2 Plan 01: HMM Regime Fitter Summary

**GaussianHMM regime labeling system with P1-only fit, filtered-posterior labels, and pickle serialization — 144-day regime_labels.csv and hmm_regime_v1.pkl produced from real NQ bar data**

## Performance

- **Duration:** ~4 min
- **Started:** 2026-03-14T02:03:08Z
- **Completed:** 2026-03-14T02:06:55Z
- **Tasks:** 2 (TDD RED + GREEN)
- **Files created:** 4 (hmm_regime_fitter.py, test file, regime_labels.csv, hmm_regime_v1.pkl)

## Accomplishments

- Implemented `hmm_regime_fitter.py` with 10 importable functions covering data loading, daily aggregation, feature engineering, HMM fitting, state name assignment, label generation, and main orchestration
- All 7 tests pass in 2.92 seconds covering HMM-01 (P1-only fit, convergence, non-degenerate), HMM-02 (label coverage, label value validity), HMM-03 (pkl round-trip, loaded model predicts)
- Script runs end-to-end on real NQ bar data: 256,322 bar rows -> 144 daily bars -> P1 slice 77 trading days confirmed -> both HMMs converge -> 144-row regime_labels.csv with 3 valid columns saved -> hmm_regime_v1.pkl verified

## Task Commits

Each task was committed atomically:

1. **RED: Failing tests** - `97a6a8b` (test: 7 failing test functions for hmm_regime_fitter)
2. **GREEN: Implementation** - `e4036a2` (feat: hmm_regime_fitter.py with all 10 functions, all 7 tests green)

## Files Created/Modified

- `stages/01-data/hmm_regime_fitter.py` - 10-function HMM regime fitter: load_all_bars, aggregate_to_daily, compute_trend_features (ADX14 + 5-day return direction), compute_volatility_features (ATR ratio + log vol change), compute_macro_flags (FOMC/CPI/NFP hard-coded), fit_hmm (P1-only, convergence asserted), assign_state_names_trend, assign_state_names_volatility, generate_labels (predict_proba), main orchestrator
- `tests/test_hmm_regime_fitter.py` - 7 test functions with synthetic data fixtures, covering all three requirement groups (HMM-01, HMM-02, HMM-03)
- `stages/01-data/data/labels/regime_labels.csv` - 144-row output: date, trend (trending/ranging), volatility (high_vol/normal_vol/low_vol), macro (event_day/normal_day), 12 event days
- `shared/scoring_models/hmm_regime_v1.pkl` - Serialized {'trend': GaussianHMM(n_components=2), 'volatility': GaussianHMM(n_components=3)} dict, protocol=4

## Decisions Made

- Three independent GaussianHMMs (trend 2-state, volatility 3-state) plus hard-coded macro calendar, not joint HMM, because regime_labels.csv requires independent per-dimension columns
- predict_proba().argmax() for hard labels (filtered posteriors), not Viterbi predict() — per pipeline requirements
- State name assignment by sorting model.means_ on the relevant feature column — deterministic and logged for audit
- Macro events (FOMC/CPI/NFP) hard-coded as Python set — 12 events in scope, no reference file needed
- Test fixture uses calendar days; test_fit_uses_p1_only asserts 90 (calendar) not 77 (trading) with clear docstring explaining the distinction

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed test_fit_uses_p1_only assertion from 77 to 90**
- **Found during:** GREEN phase (test run)
- **Issue:** Test asserted X_p1.shape[0] == 77 (trading days) but synthetic fixture generates consecutive calendar days, yielding 90 calendar days in P1 range
- **Fix:** Updated assertion to CALENDAR_P1_DAYS = 90 with docstring explaining calendar vs trading day distinction; added P2 complement assertion to fully verify mask correctness
- **Files modified:** tests/test_hmm_regime_fitter.py
- **Verification:** All 7 tests pass after fix
- **Committed in:** e4036a2 (GREEN commit)

---

**Total deviations:** 1 auto-fixed (Rule 1 - test assertion bug)
**Impact on plan:** Minor — test assertion value corrected to match fixture design. Test still proves P1-masking works correctly. No scope creep.

## Issues Encountered

- HMM convergence WARNING logged on trend model ("Current: -22.78 is not greater than -22.77") — this is a normal hmmlearn EM oscillation warning on the final iteration; model.monitor_.converged is True because the delta is within tolerance. Not a failure.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- `regime_labels.csv` is ready for read-only consumption by all downstream stages
- `hmm_regime_v1.pkl` is serialized and round-trip verified — ready for downstream scoring integration
- `hmm_regime_fitter.py` is runnable as `python stages/01-data/hmm_regime_fitter.py` from repo root to regenerate labels if bar data is updated (P1 only — do not re-run after P2 OOS test)
- 13 total tests pass (7 HMM + 6 scaffold adapter)

---
*Phase: 02-hmm-regime-fitter*
*Completed: 2026-03-14*
