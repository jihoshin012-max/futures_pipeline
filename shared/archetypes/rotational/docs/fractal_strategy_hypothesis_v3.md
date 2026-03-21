# NQ Rotation Strategy — Fractal-Derived Baseline Hypothesis (v3)

## Foundation

Everything below is derived from the fractal decomposition analysis of 60.9M 1-tick NQ bars (Sept 2025 – Mar 2026). The goal is a mathematically grounded baseline that can be swept and then improved bottom-up.

**This document is the source of truth for the sweep design.** All implementation decisions, parameter choices, and validation procedures reference this document. If a downstream prompt or session contradicts something here, this document wins.

---

## The Six Structural Facts

These are empirical properties of NQ, not strategy parameters. They hold across all tested scales (3pt through 50pt).

**Fact 1: Self-Similarity.** The swing size distribution maintains the same shape at every scale. Mean/threshold ≈ 2.0x, median/threshold ≈ 1.7x, P90/threshold ≈ 3.3x, skewness ≈ 1.9.

**Fact 2: Completion Degradation.** After a parent-scale move begins, each child-scale retracement reduces the probability of completion:
- 0 retracements: 100%
- 1 retracement: ~75-80%
- 2 retracements: ~55-64%
- 3 retracements: ~48-56%
- 4 retracements: ~43-51%
- 5+ retracements: ~41-45%

The 50% crossover (EV = 0 before costs) occurs at 3-5 retracements depending on the pair.

**Fact 3: Optimal Parent/Child Ratio.** The highest 1-retracement completion rate (79.7%) occurs at a parent/child ratio of 2.5 (25→10). Ratios below 2.0 produce degenerate decomposition. Sweet spot: 2.0-2.5.

**Fact 4: Waste is Scale-Invariant.** ~40-52% of gross child-level movement is lost to retracements. Roughly constant across scales.

**Fact 5: Time-of-Day Structure is Stable.** Completion rates and waste% vary by only 7-12pp across RTH. The fractal structure is a persistent market property.

**Fact 6: Half-Block Completion Curve.** Completion probability is flat at ~70% from entry through 40% progress, then accelerates: 75% at 50%, 80% at 60%, 86% at 70%, 90% at 80%, 95% at 90%. This curve is identical across RTH, ETH, and Combined — a structural property of NQ.

---

## PHASE 0: CALIBRATION GATE (Must Pass Before Any Sweep)

⚠️ **NO SWEEP RUNS UNTIL THIS GATE PASSES. This is the single most important prerequisite.**

### Purpose

The Python simulator must reproduce the C++ V1.1 Sierra Chart results before we trust it on 220 configurations. If the simulator disagrees with live execution, sweep results are meaningless.

### Ground Truth Data

The calibration reference is `ATEAM_ROTATION_V1_1_log_live.csv` — a single-day C++ execution log from RTH March 20, 2026 with these settings:
- StepDist = 25
- InitialQty = 1
- MaxLevels = 1 (flat adds)
- MaxContractSize = 3

The log contains 166 event rows producing:
- 55 complete rotation cycles (+ 1 incomplete trailing cycle)
- 55 adds
- 43 winning cycles (total: +3,409.5 ticks)
- 12 losing cycles (total: -539.2 ticks)
- Net: +2,870.3 ticks
- Max position reached: 7 contracts
- Cycle distribution: 26 clean (0 adds), 17 one-add, 12 multi-add

### Calibration Procedure

1. **Extract the bar data** for the exact time window of the log (2026-03-20 08:29 through 2026-03-20 16:04) from the same bar source the sweep will use.
2. **Run the Python simulator** with identical settings (SD=25, ML=1, MCS=3, directional seed).
3. **Compare event-by-event:**
   - Every SEED, ADD, REVERSAL, and REVERSAL_ENTRY event must match in: timestamp (within 1 bar tolerance), price (within tick tolerance), side, position quantity, and add quantity.
   - Cycle-level PnL must match within rounding tolerance.
   - Total cycle count must be exact: 55 complete cycles.
   - Cycle-type distribution must match: 26/17/6/4/1/1 by add count.

4. **Pass/Fail criteria:**
   - **PASS:** ≥95% of events match, total PnL within 2% of ground truth, all cycle counts exact.
   - **CONDITIONAL PASS:** 90-95% match with explained discrepancies (e.g., bar boundary differences). Document each discrepancy.
   - **FAIL:** <90% match or unexplained PnL divergence. Do not proceed to sweep. Debug simulator first.

⚠️ **Reminder: The calibration log uses MCS=3 (max contract SIZE, not max total position). In V1.1, MCS resets add size but does NOT cap total position. Position grew to 7 contracts in the log. The Python simulator must replicate this behavior exactly — MCS is NOT MTP.**

📌 **The calibration log is from March 20, 2026 — this date is AFTER all sweep/validation periods (P1 ends Dec 17, P2b ends Mar 13). This is fine: calibration tests simulator fidelity (does Python match C++?), not data-period validity. The bar data for calibration must be sourced separately from the sweep data. Do NOT use the calibration time window in any sweep or validation period.**

📌 **The calibration log is from a single day on live data. The Python simulator runs on bar data (likely 250-tick bars). There WILL be differences due to bar resolution. The goal is not perfect tick-by-tick match but structural match: same number of cycles, same cycle types, same directional trades, PnL within tolerance. Document all bar-resolution-related discrepancies as known limitations.**

---

## Five Approaches to Test

The fractal data supports multiple distinct strategies, each exploiting different structural facts. All five will be swept. The data picks the winner.

### Approach A: Pure Rotation (No Adds)

**Structural basis:** Fact 2 — 70% baseline completion rate. Zero tail risk. No rescue scenarios.

**Mechanic:** Modified V1.1 state machine. Enter 1 contract on directional seed. Price moves ≥ StepDist in EITHER direction from anchor → flatten and reverse. No adds. Every StepDist move triggers a reversal, regardless of whether it's in favor or against.

⚠️ **This is NOT standard V1.1 behavior.** V1.1's against-trigger fires an ADD, not a reversal. With adds disabled, V1.1 would hold a losing position indefinitely (the frozen-anchor problem). Pure rotation requires modifying the state machine so the against-trigger also fires a reversal. This is a small code change: replace the ADD block with a REVERSAL when MaxAdds=0.

**Sweep parameters:**
| Parameter | Values |
|-----------|--------|
| StepDist | 15, 20, 25, 30, 35, 40, 50 |

**7 configurations.**

### Approach B: Traditional Martingale (Add Into Adverse)

**Structural basis:** Fact 2 — first child retracement has ~80% completion. Fact 3 — optimal ratio 2.5. Adds exploit child retracements by improving average entry.

**Mechanic:** V1.1 with decoupled StepDist/AddDist. Enter 1. Add 1 each time price moves AddDist against, up to MaxAdds. Reverse at StepDist in favor from anchor. Anchor resets on every action.

**Sweep parameters:**
| Parameter | Values |
|-----------|--------|
| StepDist | 15, 20, 25, 30, 35, 40, 50 |
| AddDist | StepDist, StepDist/2, StepDist/2.5 |
| MaxAdds | 1, 2, 3, 4 |

**7 × 3 × 4 = 84 configurations.**

### Approach C: Anti-Martingale (Add Into Favorable)

**Structural basis:** Fact 6 — completion probability rises steeply past 50% progress. Add when probability is rising, not falling.

**Mechanic:** V1.1 modified. Enter 1 on seed. When price moves ConfirmDist IN FAVOR, add 1. Reverse at StepDist from **original seed anchor** (not from the add point). MaxAdds applies. You only ever add into winning positions.

⚠️ **Anchor behavior differs from V1.1 here.** In V1.1, anchor resets on EVERY action including adds. For anti-martingale, the favorable add must NOT reset the anchor — otherwise the reversal distance grows (original StepDist + ConfirmDist from new anchor instead of just StepDist from original). Keep the anchor at the original seed/reversal entry. Only REVERSAL resets anchor. This is a deliberate departure from V1.1 and must be implemented correctly. Same applies to Approach D.

**Sweep parameters:**
| Parameter | Values |
|-----------|--------|
| StepDist | 15, 20, 25, 30, 35, 40, 50 |
| ConfirmDist (fraction of StepDist) | 0.4, 0.5, 0.6, 0.7 |
| MaxAdds | 1, 2 |

**7 × 4 × 2 = 56 configurations.** (After pruning dead MaxAdds=2 configs where ConfirmDist ≥ 0.5×SD: 35 configs. See Prompt 2 for details.)

⚠️ **Mid-document reminder: All five approaches use the same V1.1 core state machine. Approaches A-D differ only in WHEN and WHY adds fire. Approach E is the only one requiring a different simulator architecture (two concurrent state machines). The Python simulator from Phase 0 calibration is the foundation — Approaches A-D are parameterized variants of it.**

### Approach D: Scaled Entry (Half-Block Exploitation)

**Structural basis:** Fact 6 — flat 70% plateau at 0-40% progress then steep acceleration. Minimize exposure during uncertain phase, maximize during high-probability phase.

**Mechanic:** Enter 1 contract (probe). Add N contracts at ConfirmDist in favor (conviction). Reverse at StepDist. Loss on failed move is limited to probe size during uncertain phase.

**Note:** With AddSize=1 and MaxAdds=1, this produces identical results to Approach C. Include AddSize>1 to differentiate — the "conviction" position is larger than the probe.

**Sweep parameters:**
| Parameter | Values |
|-----------|--------|
| StepDist | 15, 20, 25, 30, 35, 40, 50 |
| ConfirmDist (fraction of StepDist) | 0.4, 0.5, 0.6, 0.7 |
| AddSize at confirmation | 1, 2, 3 |

**7 × 4 × 3 = 84 configurations.** (Deduplicate: AddSize=1 rows overlap with Approach C MaxAdds=1. Net ~56 unique after dedup.)

### Approach E: Multi-Scale Stacking (Parent + Child Rotation)

**Structural basis:** Facts 1-4 together. A 50pt parent move contains 25pt child rotations. Hold a core position for the parent scale, actively trade child rotations within it.

**Mechanic:** Two concurrent rotation state machines:
- **Core layer:** StepDist = ParentSD. Enter 1, reverse at ParentSD. No adds.
- **Active layer:** StepDist = ChildSD. Enter 1, reverse at ChildSD. Independent.
- **AlignmentMode:** HEDGE (net 0 when conflicting) or NET_PARENT (always hold parent direction ±1).

**Sweep parameters:**
| Parameter | Values |
|-----------|--------|
| ParentSD | 35, 50, 75 |
| ChildSD | ParentSD/2, ParentSD/2.5, ParentSD/3 |
| AlignmentMode | HEDGE, NET_PARENT |

**3 × 3 × 2 = 18 configurations.**

⚠️ **Approach E requires a different simulator architecture — two concurrent state machines tracking separate anchors and directions. Build this AFTER Approaches A-D results are in. If A-D produce a clear winner with strong risk-adjusted returns, E may not be worth the build cost.**

---

## Shared Fixed Parameters (All Approaches)

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| ML (MaxLevels) | 1 | Flat adds only. Geometric martingale definitively harmful per V1.4 sweep. |
| InitialQty | 1 | Base size. Scaling is capital management, not structural. |
| Seed | Directional (V1.1) | Wait for StepDist move to determine initial direction. |
| Time Gate | None (full RTH) | Fact 5: structure is stable across the day. |
| Cost model | Realistic cost_ticks per instruments.md | Every config evaluated net of costs. |

---

## Secondary Parameters (Phase 2 — on top 3-5 winners per approach)

| Parameter | Values | Applies To |
|-----------|--------|-----------|
| FlattenReseed | OFF, 3×AddDist, 4×AddDist, 5×AddDist | B, E (adverse-move exposure) |
| ReversalTarget | 1.0×StepDist, 0.7×StepDist, 0.5×StepDist | All approaches |

📌 **Reminder: FlattenReseed only applies to approaches that hold positions through adverse moves (B and E). Approaches A, C, D never build adverse positions — they either don't add (A) or add into favorable moves (C, D). ReversalTarget applies to all — it's about when to take profit, not when to cut losses.**

---

## Total Sweep Size

| Approach | Configs | Notes |
|----------|---------|-------|
| A: Pure Rotation | 7 | Simplest baseline |
| B: Traditional Martingale | 84 | Decoupled StepDist/AddDist |
| C: Anti-Martingale | 35 | After pruning dead MaxAdds=2 configs |
| D: Scaled Entry | ~56 unique | After dedup with C |
| E: Multi-Scale Stacking | 18 | Deferred build, two state machines |
| **Phase 1 Total** | **~200** | **A-D: ~182, E: 18 (deferred)** |
| Phase 2 (secondary) | ~180-300 | ~12 per winner × 15-25 winners |

---

## Period Structure

⚠️ **CRITICAL: The holdout discipline below must be followed exactly. No exceptions.**

| Period | Date Range | Purpose | Rule |
|--------|-----------|---------|------|
| **P1 (full)** | Sept 21, 2025 – Dec 17, 2025 | Calibration + Sweep | All 182 configs run here (A-D). Parameter selection happens here. This is the ONLY period where parameters are tuned. |
| **P2a** | Dec 17, 2025 – ~Jan/Feb 2026 | Replication Gate | Frozen parameters from P1. NO re-tuning. If P2a fails, investigate why — do NOT re-optimize. |
| **P2b** | ~Jan/Feb 2026 – Mar 13, 2026 | Final Validation | Frozen parameters. One shot. If P2b fails after P2a passed, the edge may be regime-dependent. If both pass, proceed to paper trading. |

**Why P1 (full) instead of P1a/P1b:** The sweep has 182 configs across 4 approaches (A-D), with Approach E (18 configs) deferred. With ~3 months of P1 data, the 50pt StepDist configs get ~1,200+ parent swings — sufficient to reliably differentiate signal from noise. Splitting P1 in half would leave ~600 swings at the 50pt scale, marginal for a 182-config sweep. The P2a replication gate provides the early warning that a P1a/P1b split would have provided.

⚠️ **Reminder: P2a and P2b use FROZEN parameters from P1. "Frozen" means: no re-optimization, no parameter adjustment, no adding/removing filters. The exact configuration that won on P1 runs unchanged on P2a and P2b. The only acceptable action on P2a failure is investigation (understanding WHY), not re-tuning.**

---

## Execution Sequence

```
PHASE 0: Calibration Gate
  └─ Python sim matches V1.1 C++ log → PASS required
      └─ If FAIL → debug simulator, do not proceed

PHASE 1: Primary Sweep (P1 data, ~182 configs)
  └─ Run Approaches A-D (~182 configs)
  └─ Evaluate: NPF, cycle count, max DD, win rate by type, profit/maxDD
  └─ Identify top 3-5 per approach
  └─ [Decision point: build Approach E or skip based on A-D results]
  └─ Run Approach E if warranted (18 configs)

PHASE 2: Secondary Sweep (P1 data, ~180-300 configs)
  └─ FlattenReseed + ReversalTarget on Phase 1 winners
  └─ Final parameter selection

PHASE 3: Replication (P2a data, frozen params)
  └─ PASS → proceed to Phase 4
  └─ FAIL → investigate, do NOT re-tune
  └─ WEAK → flag and review

PHASE 4: Validation (P2b data, frozen params)
  └─ PASS → proceed to paper trading
  └─ FAIL → edge may be regime-dependent, reassess
```

📌 **Final reminder: Phase 0 (calibration) is the foundation. Phase 1 (sweep) selects parameters. Phase 2 (secondary) refines. Phase 3 (P2a) replicates. Phase 4 (P2b) validates. At no point do later phases feed back into earlier ones. Data flows forward only.**

---

## What This Baseline Does NOT Include (Deferred Improvements)

Each should be added individually on top of a validated baseline, tested through the same P1→P2a→P2b pipeline:

1. **SpeedRead filter** — on/off gate based on market speed composite.
2. **Adaptive StepDist** — ZigZagRegime-driven dynamic adjustment.
3. **Time-of-day gate** — slight improvement in afternoon at 25pt+ scales (5-10pp effect).
4. **Zigzag-informed seed entry** — enter at leg confirmation rather than fixed distance.
5. **Approach hybridization** — combining elements of multiple approaches. Only after individual approaches validated.

---

## Self-Check

### Phase 0 (Calibration)
- [ ] V1.1 C++ trade log available (`ATEAM_ROTATION_V1_1_log_live.csv`, 166 rows, 55 complete cycles)
- [ ] Bar data extracted for matching time window (2026-03-20 08:29 – 2026-03-20 16:04)
- [ ] Python simulator configured with SD=25, ML=1, MCS=3, directional seed
- [ ] Event-by-event comparison completed
- [ ] Pass/Fail criteria applied: ≥95% event match, PnL within 2%, cycle counts exact
- [ ] MCS behavior verified: resets add SIZE, does NOT cap total position (position reached 7 in live log)
- [ ] All discrepancies documented with root cause

### Phase 1 (Primary Sweep)
- [ ] All 5 approaches implemented (E can be deferred)
- [ ] Approach A: against-trigger modified to fire REVERSAL when MaxAdds=0 (not standard V1.1)
- [ ] Decoupled StepDist/AddDist implemented for Approach B
- [ ] ConfirmDist (add into favorable) implemented for Approaches C and D
- [ ] Approaches C and D: anchor does NOT reset on favorable add (only on REVERSAL)
- [ ] Deduplication between C and D applied
- [ ] Cost model active (cost_ticks from instruments.md)
- [ ] All configs run on P1 data only
- [ ] Risk-adjusted comparison across approaches (not just total PnL)
- [ ] Top 3-5 per approach identified

### Phase 2 (Secondary Sweep)
- [ ] FlattenReseed applied only to Approaches B and E
- [ ] ReversalTarget applied to all approaches
- [ ] Still on P1 data only

### Phase 3 (Replication)
- [ ] Parameters frozen — zero changes from Phase 1+2 winners
- [ ] Run on P2a data
- [ ] Pass/Fail/Weak verdict applied per config

### Phase 4 (Validation)
- [ ] Parameters frozen — same configs as Phase 3
- [ ] Run on P2b data
- [ ] Final verdict

### Structural Integrity
- [ ] Every parameter has structural justification from fractal data
- [ ] Sweep space is bounded (~182 primary + E deferred, not thousands)
- [ ] No parameters cherry-picked from single-day results
- [ ] Multiple approaches tested — data picks winner
- [ ] Improvements explicitly deferred to post-validation
- [ ] Period structure enforced: P1 calibrate → P2a replicate → P2b validate → no feedback loops
