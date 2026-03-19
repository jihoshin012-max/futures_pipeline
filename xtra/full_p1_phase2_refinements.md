# Full-P1 Phase 2 — Refinements on Validated Base

> **⚠️ CRITICAL — READ BEFORE AND AFTER IMPLEMENTATION**
> 1. **This is Phase 2 of 2.** It layers refinements onto the Phase 1 base config. Do NOT recompute base parameters.
> 2. **Every refinement must demonstrably improve the base config or be DROPPED.** Simpler wins ties.
> 3. **Full P1 (Sep 21 – Dec 14).** RTH only, daily flatten.
> 4. **cost_ticks = 1.**
> 5. **P2 is NOT touched.** Frozen config goes to P2a validation in a separate prompt.
> 6. **All features RECOMPUTED on Phase 1 cycle data.** NOT on the old SD=25 baseline.
> 7. **Adapt to Phase 1 results.** If adaptive won, use adaptive. If fixed won, use fixed. Read Phase 1 outputs before starting.

---

## Phase 1 Inputs Required

Before starting, confirm these exist:

- [ ] `phase1_base_config.json` — frozen base config with all parameters
- [ ] `full_p1_base_cycles.parquet` — cycle dataset with all fields
- [ ] Step 1b result — zigzag sensitivity pass/fail

**Read and state the Phase 1 base config before proceeding:**
- StepDist: fixed value or adaptive percentile?
- AddDist: fixed value or adaptive percentile?
- SeedDist: fixed value or sigma-band?
- ML: 1 or 2?
- Cap: 2 or 3?
- Session window: 09:30-??

> **⚠️ ALL Phase 2 work builds on this config. Do not change base parameters. Only add or remove refinement layers.**

---

## Step 1: SpeedRead RTH Recalibration

### 1A: RTH Distribution
Filter existing SpeedRead composite (`speedread_250tick.parquet`) to the session window from Phase 1.
Report: mean, median, P10, P25, P75, P90 within that window.

### 1B: Quintile Diagnostic
Using Phase 1's base cycle dataset:
1. Tag each cycle with SpeedRead composite at entry
2. Split into 5 quintiles (Q1=slowest, Q5=fastest within session window)
3. Report per quintile: cycles, gross PF, net PF @1t

> **⚠️ KILL CONDITION: If gross PF spread across quintiles < 0.15, SpeedRead does NOT help for RTH with the optimized base. Mark as killed, skip Steps 1C and 2. NOTE: SpeedRead may be less useful now — the session window restriction already concentrates trading in high-speed periods, and smaller StepDist (higher completion probability) reduces dependency on market speed.**

### 1C: Threshold Sweep (If Signal Exists)
Test BOTH directions:
- Remove slow: composite < T → skip. Sweep T from P20 to P50 of cycle-entry composites.
- Remove fast: composite > T → skip. Sweep T from P50 to P80.

Report: threshold, retained cycles, retention %, gross PF, net PF @1t.

**Save as:** `phase2_speedread_rth.json`

---

## Step 2: SpeedRead Hysteresis (If SpeedRead Survived Step 1)

> **⚠️ Skip entirely if SpeedRead killed in Step 1.**

Using best threshold T from Step 1C:
- Entry requires SR ≥ T+2, stay active until SR < T-3
- Entry requires SR ≥ T+3, stay active until SR < T-3
- Entry requires SR ≥ T+5, stay active until SR < T-5
- Hard cutoff at T (baseline)

Report: net PF, filter state changes per session, net PnL.

**Value is stability, not PF.** Hysteresis that matches hard-cutoff PF with 50% fewer state changes is better for live trading.

---

> **📌 MID-DOCUMENT REMINDER:**
> - Phase 2 layers refinements on Phase 1 base config
> - Step 1-2: SpeedRead (may be killed)
> - Step 3: Feature discovery (17 features)
> - Step 4: Risk mitigation (stops, daily loss, cap-walk limits)
> - Step 5: Final config assembly
> - Step 6: C++ replication plan
> - Each layer must improve or be dropped. P2 untouched. cost_ticks=1.

---

## Step 3: Feature Discovery

Using Phase 1's base cycle dataset (`full_p1_base_cycles.parquet`).

> **⚠️ Features MUST be recomputed on this dataset. The StepDist/AddDist/ML/cap may have changed from the old SD=25 baseline, which changes cycle timing, adds, MAE — all feature values shift. Do NOT use features from any prior investigation.**

Compute at each cycle entry time:

**Distance features:**
1. **distance_vwap:** Distance from session VWAP at entry (points). VWAP = cumulative(price×volume)/cumulative(volume), reset at session open.
2. **distance_vwap_atr:** distance_vwap / current ATR. Regime-invariant.
3. **distance_session_mid:** Distance from (session_high + session_low) / 2.

**Structure features:**
4. **retracement_pct:** % of most recent zigzag swing retraced at entry.
5. **zigzag_num_bars:** Bars in most recent completed zigzag swing.
6. **zigzag_reversal_distance:** Distance from last confirmed zigzag reversal price.

**Sigma-band features:**
7. **rotation_mean:** Rolling mean of last 200 zigzag swing distances (ALL RTH, not just session window).
8. **rotation_std:** Rolling std of last 200 zigzag swing distances.
9. **entry_sigma_level:** (price distance from watch price) / rotation_std. **Seed entries ONLY — NaN for reversals.**

**Volume features:**
10. **session_volume_ratio:** Cumulative session volume vs average at same time-of-day.
11. **volume_rate:** SpeedRead volume component at entry.

**Path-dependent (RANK SEPARATELY — session risk management, not per-cycle quality):**
12. **session_pnl:** Cumulative session PnL before this cycle.
13. **session_cycle_count:** Cycles completed this session so far.
14. **prior_cycle_pnl:** PnL of immediately preceding cycle.

> **⚠️ Features 15-17 use STRATEGY cycle windows (last 20 cycles). Features 7-9 use ZIGZAG swing windows (last 200 swings). Different data sources, different time horizons. Do not confuse them.**

**New from cycle analysis:**
15. **clean_cycle_probability:** Rolling % of clean (no-add) cycles over last 20 STRATEGY cycles.
16. **current_sd_vs_p85:** StepDist / rolling zigzag P85. Calibration health monitor.
17. **mae_risk_ratio:** Rolling mean MAE / StepDist over last 20 strategy cycles.

### Quintile Diagnostic
For each feature on full P1 base cycles:
- 5 quintiles, report: cycles, gross PF, net PF per quintile
- Spearman correlation with cycle gross PnL
- **SpeedRead redundancy check:** correlation with SR composite. |r| > 0.7 → likely redundant.
- **Path-dependent features (12-14):** rank separately from 1-11 and 15-17.

**Kill condition per feature:** < 3% NPF improvement when used as filter → drop it.

**Save as:** `phase2_feature_discovery.json`

---

## Step 4: Risk Mitigation

> **⚠️ Evaluate by TAIL-RISK REDUCTION vs mean PnL cost, NOT by net PF alone. A stop that reduces NPF by 2% but cuts worst-day loss by 40% is valuable.**

Using Phase 1 base config:

### 4A: Adaptive Cycle Stop
Flatten cycle if adverse excursion > N × rolling zigzag std (200-swing window).
Sweep N: 1.5, 2.0, 2.5, 3.0, no stop (baseline).

Report: NPF, PnL, cycles stopped, **worst session PnL**, max single-cycle loss.

**Counterfactual analysis:** For each stopped cycle, continue simulation WITHOUT the stop. Report: % that would have recovered, mean PnL recovered vs non-recovered. This quantifies the cost (good cycles killed) vs benefit (bad cycles cut).

### 4B: Max Daily Loss Stop
Flatten and stop for day if session PnL < -X ticks.
Sweep X: 100, 150, 200, 250, no stop.

Report: NPF, PnL, sessions stopped, **worst session PnL** (capped vs uncapped), cycles forfeited.

### 4C: Max Cap-Walks Per Cycle
Flatten if cycle accumulates > N cap-walks.
Sweep N: 2, 3, 4, 5, no limit.

Report same as 4A.

> **⚠️ Test 4A, 4B, 4C INDEPENDENTLY first. Then test the best of each COMBINED — interactions matter.**

---

> **📌 LATE-DOCUMENT REMINDER:**
> - Phase 2 layers: SpeedRead → features → risk mitigation
> - Each must improve or be dropped
> - All work on Phase 1 base cycles, NOT old SD=25 data
> - V1.3 logic spec is OBSOLETE — Phase 2 produces V1.4 from scratch
> - P2 untouched. cost_ticks=1.

---

## Step 5: Final Config Assembly & Freeze

### 5A: Layered Improvement Table

| Layer | Config | Net PF | Net PnL | Worst Day | Improvement |
|-------|--------|--------|---------|-----------|-------------|
| 0 | Phase 1 base (unfiltered) | ? | ? | ? | — |
| 1 | + SpeedRead (if survived) | ? | ? | ? | +?% |
| 2 | + Feature filter(s) (if survived) | ? | ? | ? | +?% |
| 3 | + Risk mitigation | ? | ? | ? | PF: ?%, worst day: ?% |
| 4 | + Hysteresis (if applicable) | ? | ? | ? | stability |

> **⚠️ EACH LAYER MUST IMPROVE OR BE DROPPED. If a layer doesn't help, proceed with the simpler config.**

### 5B: Frozen Config Table

> **⚠️ EVERY parameter must have a specific value. No TBD. This is the single source of truth for P2a validation AND C++ implementation.**

| Parameter | Value | Source |
|-----------|-------|--------|
| StepDist | ? (fixed or adaptive percentile) | Phase 1 Step 2 |
| AddDist | ? (fixed or adaptive percentile) | Phase 1 Step 2 |
| SeedDist | ? (fixed or sigma-band) | Phase 1 Step 3 |
| Session window | ? (09:30-??) | Phase 1 Step 4 |
| Position cap | ? (2 or 3) | Phase 1 Step 2b |
| ML | ? (1 or 2) | Phase 1 Step 2b |
| Anchor mode | Walking | Settled |
| Watch price | 09:30 ET first tick | Settled |
| SR block behavior | Watch stays fixed | Settled |
| SpeedRead filter | ? (threshold/hysteresis/killed) | Steps 1-2 |
| Feature filter(s) | ? (or none) | Step 3 |
| Adaptive cycle stop | ? (Nσ or none) | Step 4A |
| Max daily loss | ? (ticks or none) | Step 4B |
| Max cap-walks | ? (or unlimited) | Step 4C |
| Daily flatten | 16:00 ET (or session window end) | Settled |
| cost_ticks | 1 | Settled |

### 5C: Save Artifacts
- `phase2_frozen_config.json`
- `phase2_speedread_rth.json`
- `phase2_feature_discovery.json`
- `phase2_hysteresis.json` (if applicable)
- `phase2_risk_mitigation.json`
- `phase2_incremental_layers.json`
- Update contamination ledger: "Full P1 Phase 1+2: optimized Sep 21 – Dec 14 | NOT validated"

---

## Step 6: C++ Replication Plan

> **⚠️ The V1.3 logic spec is OBSOLETE. It assumed SD=25 fixed, AddDist=StepDist, no session window. Produce a NEW V1.4 spec from scratch.**

For each component in the frozen config, document:

1. **Can it be computed in real-time C++?** (Yes/No)
2. **What data does it need?**
3. **Persistent state required?** (rolling windows, cycle counters)
4. **Persistent variable count?** (Sierra Chart has limited slots)
5. **Warm-up requirement?**

**Specific concerns:**
- **AddDist:** new input parameter, separate from StepDist
- **ML and cap:** configurable inputs (no longer hardcoded)
- **Session window:** start/end time inputs with flatten-at-window-end
- **ZigZagRegime study (if adaptive):** 200-swing circular buffer, P50/P65/P70/P75/P80/P85/P90/std as subgraphs. Autotrader reads via GetStudyArrayUsingID.
- **VWAP:** Sierra Chart has built-in VWAP study, or compute internally
- **Retracement/zigzag features:** read via GetStudyArrayUsingID from zigzag study
- **Session volume ratio:** needs historical average — lookup table or rolling computation

For anything that CAN'T be done in C++, flag and recommend an alternative.

---

## Pipeline Rules (Absolute)

> **⚠️ REMINDER: Each refinement layer must improve the base or be dropped. Features recomputed on Phase 1 data. C++ feasibility is a hard constraint. P2 untouched.**

1. **Full P1 for all work.** Both regimes.
2. **RTH only.** Session window from Phase 1.
3. **P2 UNTOUCHED.** P2a/P2b validation separate.
4. **cost_ticks = 1.**
5. **Simpler wins ties.** Every layer must earn its place.
6. **Risk mitigation by tail risk, not just PF.**
7. **C++ feasibility is a hard constraint.**
8. **Adapt to Phase 1 results.** Don't test dead paths.
9. **Watch price 09:30 settled.** Do not re-sweep.
10. **SR-block watch stays fixed.** F/G killed.
11. **HMM deferred.** Not in this prompt.
12. **V1.3 spec OBSOLETE.** V1.4 from scratch.
13. **Features recomputed on Phase 1 cycle data, NOT old SD=25.**

---

## ⚠️ Common Mistakes — Self-Check

**Step 1:**
- [ ] SpeedRead distribution filtered to Phase 1 session window (not all RTH)
- [ ] Quintile diagnostic on Phase 1 base cycles
- [ ] Kill condition checked: Q5-Q1 spread > 0.15?
- [ ] Both filter directions tested
- [ ] cost_ticks = 1

**Step 2:**
- [ ] Skipped if SpeedRead killed
- [ ] Hysteresis evaluated by state changes, not just PF

**Step 3:**
- [ ] Features computed on Phase 1 base cycles (NOT old SD=25 data)
- [ ] VWAP computed from bar data (not a CSV column)
- [ ] entry_sigma_level: seed entries only, NaN for reversals
- [ ] Features 7-9 use 200-swing zigzag window; features 15-17 use 20-cycle strategy window
- [ ] Path-dependent (12-14) ranked separately
- [ ] SpeedRead redundancy check (|r| > 0.7)
- [ ] Kill condition: < 3% NPF improvement → drop
- [ ] Data filtered to P1 dates (CSV extends into P2)

**Step 4:**
- [ ] Each stop type tested independently FIRST
- [ ] Best of each combined AFTER
- [ ] Counterfactual analysis for adaptive stop
- [ ] Evaluated by worst-day improvement, not just NPF

**Step 5:**
- [ ] Every parameter has a specific value
- [ ] Each layer demonstrably improves or is dropped
- [ ] All artifacts saved
- [ ] Contamination ledger updated
- [ ] P2 NOT touched

**Step 6:**
- [ ] V1.4 spec (NOT update to V1.3)
- [ ] AddDist as separate input
- [ ] ML/cap configurable
- [ ] C++ feasibility confirmed for every component
- [ ] ZigZagRegime study specified if adaptive validated
