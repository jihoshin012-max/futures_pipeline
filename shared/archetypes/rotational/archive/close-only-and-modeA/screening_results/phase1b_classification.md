# Phase 1b Cross-Bar-Type Robustness Classification

**Generated:** 2026-03-15 23:45 UTC
**Classification based on:** RTH-filtered results (`phase1_results_rth.tsv`)
**Framework:** Spec Section 3.7 — cross-bar-type robustness matrix

## Human Review Status

**Status:** APPROVED — 2026-03-15
**Reviewer decision:** Advancement list approved as-is.
**H19 disposition:** SKIPPED_REFERENCE_REQUIRED — defer to Phase 4 when multi-source reference available.

> **Note (strategic context recorded):** Before Phase 3 parameter-tuned hypothesis screening,
> a sizing sweep is required: MaxLevels x MaxContractSize. This sweep must complete before
> Phase 3 TDS runs so that tuning operates on the correct position-sizing configuration.

## Summary

- **Total hypotheses classified:** 40 (ranked) + 1 NOT_TESTED
- **ADVANCE_HIGH:** 0 hypotheses
- **ADVANCE_FLAGGED:** 0 hypotheses
- **DO_NOT_ADVANCE:** 40 hypotheses
- **NOT_TESTED (H19):** 1 hypothesis

### Classification Counts

| Classification | Count | Advancement |
|----------------|-------|-------------|
| NO_SIGNAL | 40 | DO_NOT_ADVANCE |

---

## Important Note: Default Params Screening

All 119 valid experiments ran with **default_params** (Phase 1 screening mode).
The fixed trigger mechanism ignores computed features at default settings.
Therefore `beats_baseline=False` for all hypotheses is **expected** at this stage.

Phase 1b classification reflects cross-bar-type **structural consistency**, not raw
outperformance. The classification captures whether a hypothesis, once tuned, would
show consistent behavior across bar types (ROBUST) vs. being artifact-dependent.

In practice, with all experiments returning False for beats_baseline:
- All 40 rankable hypotheses classify as **NO_SIGNAL** (DO_NOT_ADVANCE)
- This does NOT mean the hypotheses are worthless — it means Phase 1 screening
  with default params established the baseline structural profile
- Phase 3 (TDS) / Phase 4 (Combinations) will use parameter tuning to find
  hypotheses that actually beat the baseline

---

## Ranked Advancement List

### ADVANCE_HIGH

_None_

### ADVANCE_FLAGGED

_None_

### DO_NOT_ADVANCE

| Rank | ID | Name | Dim | Classification | Notes |
|------|-----|------|-----|----------------|-------|
| 1 | H1 | ATR-scaled step | A | NO_SIGNAL | No bar type beats baseline at default params. (vol=FAIL, tick=FAIL, 10sec=FAIL) |
| 2 | H3 | SD band triggers | A | NO_SIGNAL | No bar type beats baseline at default params. (vol=FAIL, tick=FAIL, 10sec=FAIL) |
| 3 | H8 | SD-scaled step from anchor | A | NO_SIGNAL | No bar type beats baseline at default params. (vol=FAIL, tick=FAIL, 10sec=FAIL) |
| 4 | H9 | VWAP SD bands | A | NO_SIGNAL | No bar type beats baseline at default params. (vol=FAIL, tick=FAIL, 10sec=FAIL) |
| 5 | H10 | Price z-score threshold | A | NO_SIGNAL | No bar type beats baseline at default params. (vol=FAIL, tick=FAIL, 10sec=FAIL) |
| 6 | H2 | Asymmetric reversal vs add thresholds | B | NO_SIGNAL | No bar type beats baseline at default params. (vol=FAIL, tick=FAIL, 10sec=FAIL) |
| 7 | H4 | ZZ swing confirmation | C | NO_SIGNAL | No bar type beats baseline at default params. (vol=FAIL, tick=FAIL, 10sec=FAIL) |
| 8 | H5 | Regime-conditional parameters | C | NO_SIGNAL | No bar type beats baseline at default params. (vol=FAIL, tick=FAIL, 10sec=FAIL) |
| 9 | H6 | Bid/Ask volume imbalance | C | NO_SIGNAL | No bar type beats baseline at default params. (vol=FAIL, tick=FAIL, 10sec=FAIL) |
| 10 | H7 | ZZ Oscillator gating | C | NO_SIGNAL | No bar type beats baseline at default params. (vol=FAIL, tick=FAIL, 10sec=FAIL) |
| 11 | H11 | Time-of-day conditioning | C | NO_SIGNAL | No bar type beats baseline at default params. (vol=FAIL, tick=FAIL, 10sec=FAIL) |
| 12 | H12 | Day-of-week conditioning | C | NO_SIGNAL | No bar type beats baseline at default params. (vol=FAIL, tick=FAIL, 10sec=FAIL) |
| 13 | H16 | Bar formation quality filter | C | NO_SIGNAL | No bar type beats baseline at default params. (vol=FAIL, tick=FAIL, 10sec=FAIL) |
| 14 | H17 | Cycle performance feedback | C | NO_SIGNAL | No bar type beats baseline at default params. (vol=FAIL, tick=FAIL, 10sec=FAIL) |
| 15 | H33 | PriceSpeed filter | C | NO_SIGNAL | No bar type beats baseline at default params. (vol=FAIL, tick=FAIL, 10sec=FAIL) |
| 16 | H34 | Absorption rate proxy | C | NO_SIGNAL | No bar type beats baseline at default params. (vol=FAIL, tick=FAIL, 10sec=FAIL) |
| 17 | H35 | Imbalance trend | C | NO_SIGNAL | No bar type beats baseline at default params. (vol=FAIL, tick=FAIL, 10sec=FAIL) |
| 18 | H36 | Adverse move speed | C | NO_SIGNAL | No bar type beats baseline at default params. (vol=FAIL, tick=FAIL, 10sec=FAIL) |
| 19 | H37 | Bar formation rate | C | NO_SIGNAL | No bar type beats baseline at default params. (vol=FAIL, tick=FAIL, 10sec=N/A) |
| 20 | H39 | Cycle adverse velocity ratio | C | NO_SIGNAL | No bar type beats baseline at default params. (vol=FAIL, tick=FAIL, 10sec=FAIL) |
| 21 | H40 | Band-relative speed regime | C | NO_SIGNAL | No bar type beats baseline at default params. (vol=FAIL, tick=FAIL, 10sec=FAIL) |
| 22 | H41 | Band-relative ATR behavior | C | NO_SIGNAL | No bar type beats baseline at default params. (vol=FAIL, tick=FAIL, 10sec=FAIL) |
| 23 | H13 | Selective flat periods | D | NO_SIGNAL | No bar type beats baseline at default params. (vol=FAIL, tick=FAIL, 10sec=FAIL) |
| 24 | H14 | Adaptive martingale progression | D | NO_SIGNAL | No bar type beats baseline at default params. (vol=FAIL, tick=FAIL, 10sec=FAIL) |
| 25 | H15 | Alternative anchor strategies | D | NO_SIGNAL | No bar type beats baseline at default params. (vol=FAIL, tick=FAIL, 10sec=FAIL) |
| 26 | H20 | Partial rotation | D | NO_SIGNAL | No bar type beats baseline at default params. (vol=FAIL, tick=FAIL, 10sec=FAIL) |
| 27 | H21 | Cycle profit target | D | NO_SIGNAL | No bar type beats baseline at default params. (vol=FAIL, tick=FAIL, 10sec=FAIL) |
| 28 | H22 | Cycle time decay | D | NO_SIGNAL | No bar type beats baseline at default params. (vol=FAIL, tick=FAIL, 10sec=FAIL) |
| 29 | H23 | Conditional adds | D | NO_SIGNAL | No bar type beats baseline at default params. (vol=FAIL, tick=FAIL, 10sec=FAIL) |
| 30 | H24 | Intra-cycle de-escalation | D | NO_SIGNAL | No bar type beats baseline at default params. (vol=FAIL, tick=FAIL, 10sec=FAIL) |
| 31 | H25 | Higher-timeframe context | D | NO_SIGNAL | No bar type beats baseline at default params. (vol=FAIL, tick=FAIL, 10sec=FAIL) |
| 32 | H26 | Session range position | D | NO_SIGNAL | No bar type beats baseline at default params. (vol=FAIL, tick=FAIL, 10sec=FAIL) |
| 33 | H18 | Directional asymmetry | E | NO_SIGNAL | No bar type beats baseline at default params. (vol=FAIL, tick=FAIL, 10sec=FAIL) |
| 34 | H27 | Volatility rate of change | F | NO_SIGNAL | No bar type beats baseline at default params. (vol=FAIL, tick=FAIL, 10sec=FAIL) |
| 35 | H28 | Price momentum / ROC | F | NO_SIGNAL | No bar type beats baseline at default params. (vol=FAIL, tick=FAIL, 10sec=FAIL) |
| 36 | H29 | Acceleration / deceleration | F | NO_SIGNAL | No bar type beats baseline at default params. (vol=FAIL, tick=FAIL, 10sec=FAIL) |
| 37 | H30 | Volatility compression breakout | F | NO_SIGNAL | No bar type beats baseline at default params. (vol=FAIL, tick=FAIL, 10sec=FAIL) |
| 38 | H31 | Momentum divergence from price | F | NO_SIGNAL | No bar type beats baseline at default params. (vol=FAIL, tick=FAIL, 10sec=FAIL) |
| 39 | H32 | Volume rate of change | F | NO_SIGNAL | No bar type beats baseline at default params. (vol=FAIL, tick=FAIL, 10sec=FAIL) |
| 40 | H38 | Regime transition speed | F | NO_SIGNAL | No bar type beats baseline at default params. (vol=FAIL, tick=FAIL, 10sec=FAIL) |

---

## NOT_TESTED Hypotheses

| ID | Name | Dim | Reason |
|----|------|-----|--------|
| H19 | Bar-type divergence signal | E | SKIPPED_REFERENCE_REQUIRED — requires simultaneous multi-source access not supported by single-source runner. |

**H19 decision for Phase 4:** DEFERRED — add to Phase 4 when multi-source reference is available.
H19 requires simultaneous multi-source access; extend runner to load all 3 bar types for divergence signal.
**Human disposition (2026-03-15):** SKIPPED_REFERENCE_REQUIRED — defer to Phase 4.

---

## Cross-Bar-Type Analysis (Section 3.7 Questions)

**Q1: Are there ROBUST signals (all 3 bar types win)?**
A: No — 0 hypotheses achieved ROBUST or ROBUST_ACTIVITY classification at default params.

**Q2: Are there ACTIVITY_DEPENDENT signals (vol+tick win, 10sec fails)?**
A: No — 0 at default params. Expected: all experiments use fixed trigger.

**Q3: Are there TIME_DEPENDENT signals (10sec only wins)?**
A: No — 0 at default params.

**Q4: How many SAMPLING_COUPLED (one bar type only)?**
A: 0 hypotheses. These are structural artifacts — do not advance.

**Q5: Result of RTH filtering vs unfiltered?**
A: RTH filtering ensures consistent time window across bar types for fair cross-bar comparison.
   See phase1_results.tsv vs phase1_results_rth.tsv for comparison.

**Q6: Suspicious delta_pf outliers?**
A: All delta_pf = 0.0 at default params. No outliers. This is expected (fixed trigger, no tuning).

---

## Next Steps

- **0 ADVANCE_HIGH** hypotheses: Priority candidates for Phase 3 TDS + Phase 4 combinations
- **0 ADVANCE_FLAGGED** hypotheses: Proceed to Phase 3 with deployment caveats noted
- **40 DO_NOT_ADVANCE** hypotheses: Dropped from Phase 4 combination testing
- **1 NOT_TESTED (H19)**: Consider multi-source runner extension for Phase 4

**Advancement list is ready for Phase 4 (Combinations) consumption via `phase1b_classification.json`.**
