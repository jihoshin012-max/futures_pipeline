# Decision Log — Rotational Strategy V1.4

## Pipeline Summary

**Start:** Fixed SD=25 baseline (NPF=1.037, +8,134 ticks on P1 09:30-16:00)
**End:** V1.4 + 4C stop validated OOS (P2b NPF=1.230, +14,172 ticks)

---

## Phase 1: Base Parameter Calibration (P1 only)

### Step 1: Simulator Baseline
- Built daily-flatten tick simulator with rotation logic
- Validated on P1: 3,424 cycles, NPF=1.037

### Step 1b: Zigzag Sensitivity
- **Decision:** 5.25 pt reversal, HL-based zigzag
- **Why:** P90 shift = 10.4% (well under 15% threshold) between close-to-close and HL computation methods. Safe to use Sierra Chart's HL-based zigzag.

### Step 2: SD × AD Sweep
- **Decision:** Adaptive P90/P75 from rolling 200-swing zigzag
- **Why:** Adaptive configs outperformed all 30 fixed configs. P90 for StepDist, P75 for AddDist. The decoupling (AD < SD) transfers ticks from loss to profit on adds.
- **Killed:** Fixed distance configs (SD=16-26 × AD=10-26)

### Step 2b: ML/Cap Sweep
- **Decision:** ML=1, position cap=2, cap_action=walk
- **Why:** ML=1 minimizes position risk while allowing one add. Cap=2 prevents runaway position sizing. Walking anchor at cap preserves the cycle chain.

### Step 3: SeedDist
- **Decision:** SeedDist=15 pts fixed
- **Why:** Optimal from sweep. Decoupled from StepDist. All sigma-based alternatives performed similarly (±0.5% NPF). Fixed is simpler.

### Step 4: Session Window
- **Decision:** Full RTH (09:30-16:00) for Phase 1 base
- **Why:** Full RTH outperformed all sub-windows. Open block is unprofitable but contributes cycle volume. Revisited in Phase 2.

### Step 5: Phase 1 Freeze
- **Result:** NPF=1.037, +8,134 ticks, 3,424 cycles, 59 sessions
- **Config:** Adaptive P90/P75, Sd=15, ML=1, cap=2, full RTH, no SpeedRead

---

## Phase 2: Filter Layer (P1 only)

### P0-1: Clock-Time vs Count Window
- **Decision:** Keep 200-swing count window
- **Why:** Clock-time window did not improve NPF. Count-based adapts to regime.

### P0-2: Session Start Time
- **Decision:** 10:00 ET start (skip Open block)
- **Why:** Open block has NPF=0.83, 29.6% cap-walk rate. Removing it improved PnL +50%. Single largest source of losses (-8,335 ticks).

### P0-3: SpeedRead Block Diagnostic
- **Result:** Open block shows strong speed-quality gradient. Afternoon is flat (speed irrelevant when cycles already good).

### Step 1: SR Threshold Sweep
- **Decision:** Both seed + reversal SR ≥ 48
- **Why:** Reversal SR is the primary driver (+10% NPF). Seed-only adds <1%. Symmetric threshold simplifies.

### Step 2: Rolling SR (Hysteresis)
- **Decision:** Roll50 (50-tick rolling average of SpeedRead composite)
- **Why:** Roll50 Both≥48 (NPF=1.200) beats point-in-time Both≥48 (NPF=1.175) by +2.1%. Smooths spiky readings.

### Step 3: Feature Discovery
- **Decision:** No features adopted
- **Why:** 16/17 features pass 3% NPF threshold, but quintile patterns are non-monotonic. 59 sessions insufficient for reliable multi-feature selection. Overfitting risk too high.
- **Killed:** session_volume_ratio, current_sd_vs_p85, zigzag_reversal_distance, and 14 others

### Step 4: Risk Mitigation
- **Decision:** Deferred to post-P2 (requires simulator changes)
- **Identified:** max_cap_walks=3 and adaptive cycle stop (2.5σ) show potential
- **Killed:** Max daily loss stop — too aggressive, kills NPF to 1.08

### Step 5: V1.4 Freeze
- **Result:** NPF=1.200, +20,919 ticks, 1,847 cycles, 59 sessions
- **Config:** Adaptive P90/P75, Sd=15, 10:00-16:00, Roll50 SR≥48, ML=1, cap=2

---

## P2a Validation (One-Shot, V1.4 without stops)

- **Result:** FAIL — NPF=0.958, -1,797 ticks, 667 cycles, 28 sessions
- **Gross PF:** 1.006 (near zero edge before costs)
- **Key finding:** Clean cycle economics transferred (47% clean at +78.7). Gross edge collapsed — winning cycles got smaller while cap-walk losses stayed constant.

### P2a Four-Prong Diagnostic
1. **SR ON vs OFF:** Both negative. SR not the problem (helped slightly).
2. **Tail concentration:** Removing worst session (Jan 21: -3,055) flips NPF to 1.035. Removing worst 2 gives NPF=1.086.
3. **Rolling variance:** P2a NPF at P0 of P1 distribution. P1 never had NPF < 1.128 in any 28-session window. P2a is OUTSIDE the P1 envelope.
4. **Reversal chain:** Cap-walk rate identical (26.1% vs 26.2%). Per-CW losses slightly worse (-228 vs -207). Mean gross/cycle collapsed from +18.5 to +5.9.

**Diagnosis:** Regime shift + tail concentration. P2a market produced smaller rotational swings.

---

## Stop Implementation & Sweep (P1 only)

### 4A: Adaptive Cycle Stop (max_adverse_sigma)
- **KILLED** at all sigma levels (1.5, 2.0, 2.5, 3.0)
- **Why:** NPF < 0.89 at every level. Counterfactual: 50-60% of stopped cycles eventually recovered. The rotation mechanism inherently needs to absorb large adverse excursions. Rolling zigzag std (mean=6.60) is too small relative to typical MAE (27.2 pts).

### 4C: Max Cap-Walks Per Cycle
- **Selected:** max_cap_walks=2
- **Why:** 0% recovery rate on stopped cycles (CW > 2 never recover). Pure tail-risk insurance with zero false positives. NPF cost: 1.200 → 1.172 (2.3%). Worst-day improvement: -2,210 → -1,556 (29.6%). 99 cycles stopped (5.3%).
- **Kill condition override:** 29.6% < 30% threshold, but 0% recovery rate satisfies the intent (no false positives). User approved override.

---

## P2b Validation (One-Shot, V1.4 + 4C)

- **Result:** PASS — NPF=1.230, +14,172 ticks, 995 cycles, 29 sessions
- **Gross PF:** 1.286 (P1-like — rotation edge returned)
- **Session win %:** 65.5%
- **Worst day:** -2,135 (better than P2a's -3,055)
- **Stopped by 4C:** 51 cycles
- **Adaptive ranges:** SD mean=23.7 (wider than P2a=20.3, closer to P1=21.7)

**Interpretation:** P2a was a regime dip, not structural breakdown. P2b shows P1-like gross edge with stops capping tail events. Strategy + stops = viable for paper trading.

---

## Killed Approaches (Not Adopted)

| Approach | Reason |
|----------|--------|
| Fixed SD/AD distances | Adaptive P90/P75 outperforms all fixed configs |
| ML > 1 (martingale) | Increases position risk without NPF improvement |
| Cap > 2 | Excessive position sizing |
| 09:30 session start | Open block NPF=0.83, biggest loss source |
| Clock-time zigzag window | No improvement over 200-swing count |
| Feature filters (17 features) | Non-monotonic quintiles, overfitting risk on 59 sessions |
| Max daily loss stop | Too aggressive, kills NPF to 1.08 |
| 4A adaptive cycle stop | 50-60% of stopped cycles recover — expensive false positives |
| Point-in-time SR | Roll50 outperforms by +2.1% NPF |
| SR recalibration on P2a | Would burn P2b holdout |
