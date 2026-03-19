# Phase 1/2 Update Specification — Complete Requirements (Revised)

This document captures EVERY detail for the updated prompts.
**Key change:** Base parameter calibration comes FIRST. Filters and refinements are layered on top AFTER the base economics are sound.

---

## A. Settled Items (Carry Forward, Do NOT Retest)

| Item | Value | Evidence |
|------|-------|---------|
| Walking anchor on cap hit | Yes | Frozen anchor was survivorship bias |
| Tick data = ground truth | Yes | OHLC simulator was 6x over-optimistic |
| Fast markets help rotation | Yes | Confirmed on P1a and P1b independently |
| Watch price at 09:30 ET | User constraint | RTH-only trading, lifestyle choice |
| SR-block: watch price stays fixed | Yes | F/G tested and degraded — "stale" = accumulated directional signal |
| HMM regime detection | Deferred | GMMHMM barely improved over SpeedRead |
| Daily flatten at 16:00 ET | Yes (hard backstop) | If session window ends earlier, flatten at window end. 16:00 is absolute latest. |
| cost_ticks | 1 | ~$4-5/RT on NQ |
| Zigzag settings | 5.25 pt reversal (21 ticks), calc mode 3, no bar filter, no daily reset | Sierra Chart study. **Validated by sensitivity check in Phase 1 Step 1b — if percentile mappings shift >15% across reversal settings 4.0/5.25/7.0, the zigzag setting itself becomes a parameter.** |

### Reopened for Re-Evaluation (Previously Settled)

| Item | Old Value | Why Reopened |
|------|-----------|-------------|
| ML | 1 | Was tested with AddDist=StepDist=25. With decoupled AddDist=15, adds fire at better prices. ML=2 at entry-15 gives avg entry of entry-10 — fundamentally different economics than ML=2 at entry-25. |
| Position cap | 2 | With AddDist=15, cap=2 hits after just 15 pts adverse (vs 25 before). Cap=3 with AddDist=15 means 3rd add at 30 pts adverse — comparable dollar risk to cap=2 at AddDist=25 but better average entry. Cap-walk probability at cap=3/AD=15: 0.29³=2.4% vs cap=2/AD=15: 0.29²=8.4%. |

**These are NOT in the main sweep.** They are tested as a follow-up on the top 2-3 winners from the StepDist × AddDist sweep (Phase 1 Step 2b). This keeps the search space manageable.

> **⚠️ KEY STRUCTURAL CHANGE: StepDist reopened. AddDist is a NEW decoupled parameter. Session window is a formal parameter. ML and cap are reopened for follow-up testing after the main sweep. These five changes are the core of the Phase 1 investigation.**

## B. What's Changed

### B1. StepDist is NO LONGER settled at 25.
- RTH P90 = 22.25. SD=25 requires a top-9% swing. 48% of cycles are messy.
- EV analysis: SD=20 with AddDist=15 → EV≈+30.3 ticks/cycle vs SD=25 → EV≈+13.4 ticks/cycle.
- Sweep 16-26 on full P1 tick simulation (fixed and adaptive percentile).

### B2. AddDist is decoupled from StepDist (NEW parameter).
- Currently AddDist = StepDist = 25. Adds fire at worst possible moment (mean MAE = 25.23).
- Every 1 pt of AddDist reduction transfers 4 ticks from loss to profit on contract 1.
- AddDist < StepDist makes 1-add cycles as profitable as clean cycles.
- Sweep 12-20, also test as rolling zigzag percentile (P65-P75).
- **Requires simulator modification** — V1.1 uses StepDist for both triggers.

### B3. Session window is a formal parameter.
- Open: 15.7 cycles/hr, Morning: 10.0, Midday: 6.7, Afternoon: 4.6, Close: 4.3.
- Open+Morning (09:30-11:30) = 3.6x more productive than Afternoon+Close.
- Test: 09:30-11:30 vs 09:30-13:30 vs 09:30-16:00.

### B4. Rolling window is 200 zigzag swings.
- ≈1 hour during Open, 2+ hours during Afternoon. Adaptive by design.
- **Scope: rolling window computes from ALL RTH zigzag swings (09:30-16:00), regardless of the trading session window.** The market's oscillation structure exists whether you're trading or not. If you trade 09:30-11:30, the adaptive parameters still see the full RTH distribution.

### B5. P2 data leak protection.
- 250-tick CSV extends to March 2026. ALL data MUST be filtered to P1 (Sep 21 – Dec 14).

### B6. Ordering: base parameters FIRST, refinements SECOND.
- Phase 1 = StepDist, AddDist, SeedDist, session window. No filters. Pure economics.
- Phase 2 = SpeedRead, features, hysteresis, risk mitigation. Layered on validated base.

> **⚠️ SUMMARY OF CHANGES: (1) StepDist reopened for sweep 16-26. (2) AddDist decoupled as NEW parameter, sweep 12-20. (3) Session window is formal parameter. (4) ML and cap reopened for re-evaluation after main sweep. (5) Rolling 200-swing zigzag window for adaptive versions. (6) P2 data leak protection required. (7) Base params first, refinements second.**

---

## C. Reference Data

### Zigzag RTH Distribution
| Percentile | Value (pts) | Potential Use |
|-----------|-------------|---------------|
| P50 (median) | 11.0 | Regime health check |
| P65 | ~14 | AddDist lower bound |
| P70 | ~15 | AddDist candidate |
| P75 | 16.0 | AddDist candidate |
| P80 | 17.5 | AddDist upper / StepDist lower |
| P85 | 19.5 | StepDist candidate |
| P90 | 22.25 | StepDist candidate |
| P95 | 26.75 | Current SD=25 territory |
| P97+ | ~30-35 | Stop territory |

### Regime Shift (P90)
| Period | RTH P90 | Implication |
|--------|---------|-------------|
| P1a | ~20.5 | SD=25 is top-5% swing → low completion |
| P1b | ~23.25 | SD=25 is top-10% swing → better completion |
| Shift | +2.75 pts | Fixed params are regime-fragile |

> **⚠️ REMINDER: Phase 1 = base parameter calibration (StepDist, AddDist, SeedDist, session window). No SpeedRead. No feature filters. Phase 2 = refinements layered on top. This ordering is non-negotiable.**

### EV Per Cycle (Estimated from Distribution Math)
| Config | EV/Cycle | Rationale |
|--------|----------|-----------|
| SD=25, AddDist=25 (current) | ≈+13.4 ticks | 52% clean, adds at worst moment |
| SD=20, AddDist=15 | ≈+30.3 ticks | 57% clean, 1-add cycles profitable |
| Improvement | 2.3x | Parameter calibration alone |

### Mathematical Framework (Guides the Sweep Logic)

> **⚠️ NOTE: The EV estimates below assume independent zigzag swings. Real market swings have serial correlation (trending regimes produce consecutive large swings, mean-reverting regimes produce alternating small swings). These numbers are DIRECTIONAL GUIDES for the sweep ranges. The tick simulation in Phase 1 Step 2 is the ground truth — it captures serial correlation, partial fills, and all microstructure effects. If simulation EV differs significantly from the estimates below, serial correlation is the likely explanation.**

**EV Formula per cycle (4 outcomes):**
```
EV = P_clean × (4×SD - 2×cost)
   + P_1add_recover × (recovery_profit - 2×cost)  
   + P_capwalk × (cap_walk_loss - 2×cost)
   + P_deep_loss × (deep_loss - 2×cost)
```
Phase 1 Step 2 should compute these probabilities and PnL components for each config in the sweep, not just aggregate NPF.

**Completion probability principle:**
P(swing ≥ StepDist) from the zigzag CDF gives the probability that any given swing completes a cycle. At SD=25 on RTH, P(completion) ≈ 6.5%. At SD=20, ≈14%. At SD=16, ≈22.5%. Higher completion probability = more clean cycles, fewer messy cycles.

**Breakeven clean rate is ~51% for all StepDists** because loss magnitude scales proportionally with profit. The margin of safety above breakeven is what matters — SD=25 has 1% margin (52% vs 51%), SD=20 has ~6% margin (57% vs 51%).

**Why AddDist < StepDist transforms cycle economics:**
With AddDist=15, StepDist=20: add fires at entry-15, anchor resets to entry-15. Reversal fires at entry-15+20 = entry+5. Contract 1 entered at entry, exits at entry+5 → +5 pts (+20 ticks). Contract 2 entered at entry-15, exits at entry+5 → +20 pts (+80 ticks). Total = +100 ticks gross. This makes the 1-add outcome as profitable as a clean cycle — the "messy" label becomes economically irrelevant.

**Cap-walk probability:**
P(cap-walk) depends on both AddDist and cap:
- Cap=2, AddDist=15: cap-walk requires 2 consecutive adverse swings ≥ AddDist → 0.29² = 8.4%.
- Cap=2, AddDist=25: 0.065² = 0.4%.
- Cap=3, AddDist=15: cap-walk requires 3 consecutive adverse swings ≥ AddDist → 0.29³ = 2.4%.
Higher cap with smaller AddDist exponentially reduces cap-walk frequency while giving more contracts at better average prices. The tradeoff is higher total position risk if cap-walk does occur.

**Optimization objective:**
The optimal StepDist/AddDist is NOT the highest NPF — it's the point where:
`P(completion) × profit_per_cycle - P(failure) × failure_cost` is maximized.
This is what the Phase 1 heatmap should reveal.

**Rolling percentile rationale:**
A fixed StepDist at P85 of P1a (≈19.5) maintains ~15% completion probability in P1a. When the regime shifts to P1b, P85 expands to ≈22.5 — the rolling percentile tracks this automatically, maintaining constant ~15% completion probability. Fixed StepDist=20 would have 15% completion in P1a but 18% in P1b — still functional but suboptimal.

> **📌 MID-DOCUMENT REMINDER — Block Cycle Throughput & Cycle Quality:**

### Block Cycle Throughput (at SD=25)
| Block | Time | Cycles/Hr | Rank |
|-------|------|-----------|------|
| Open | 09:30-10:00 | 15.7 | 1 |
| Morning | 10:00-11:30 | 10.0 | 2 |
| Midday | 11:30-13:30 | 6.7 | 3 |
| Afternoon | 13:30-15:00 | 4.6 | 5 |
| Close | 15:00-16:00 | 4.3 | 4 |

Swing amplitude is uniform across blocks (median=11.0 in all except Close=10.25). The difference is entirely clock-time speed — Open has 325 swings/hr, Afternoon has 95. This was validated by clock-time analysis.

### Cycle Quality at SD=25
- Clean cycles: 52% (1,447/2,789)
- Messy cycles: 48% (1,342/2,789)
- Mean MAE: 25.23 pts
- P75 MAE: 47.0 pts
- ~20 zigzag swings per completed cycle (stable across blocks)
- MFE mechanically capped at StepDist (median MFE = 25.0 at SD=25)

---

## D. Phase 1 Structure — Base Parameter Calibration

**Goal:** Find the StepDist/AddDist/SeedDist combination and session window that maximize cycle EV on full P1, UNFILTERED. No SpeedRead. No feature filters. Pure base economics.

> **⚠️ CRITICAL: Simulator must be modified BEFORE any sweeps run. AddDist decoupling is a prerequisite for Step 2. Verify the modification by confirming SD=25/AD=25 matches the known baseline.**

### Step 1: Simulator Enhancement
- Modify `run_seed_investigation.py` to accept separate AddDist parameter.
- **Three distance triggers (all measured from current anchor):**
  - **AddDist:** price moves AddDist AGAINST → add 1 contract (if below cap). This is the NEW decoupled parameter.
  - **StepDist:** price moves StepDist IN FAVOR → flatten and reverse (reversal trigger).
  - **StepDist:** price moves StepDist AGAINST when already at cap → walk anchor (cap-walk trigger). Cap-walk uses StepDist, NOT AddDist. Rationale: once at cap, you're in damage control — wider spacing (StepDist ≥ AddDist) gives more room for recovery before walking the anchor further away.
- **Session window behavior:** When session window end is reached (e.g., 11:30 if window is 09:30-11:30):
  - If a position is open: FLATTEN immediately at market, same as daily flatten. Do NOT let cycles run past the window.
  - Stop accepting new seeds/entries.
  - Full state reset (same as daily flatten logic).
  - Rationale: holding a position through Midday (low throughput) to recover defeats the purpose of the window restriction.
- Verify: run SD=25, AddDist=25, ML=1, cap=2, window=09:30-16:00 and confirm it matches the known baseline (these should be identical to current V1.1 behavior).
- **The simulator must also support ML=2 and cap=3 for Step 2b.** With ML=2: first add = 1 contract, second add = 2 contracts (doubling). With cap=3: three adds possible before cap-walk. Verify add quantity logic handles ML correctly with the new AddDist decoupling.

### Step 1b: Zigzag Sensitivity Check
- The entire percentile framework is built on a 5.25-point reversal zigzag. Verify this choice is robust.
- Compute RTH P50, P75, P85, P90, P95 using three reversal settings: 4.0, 5.25, 7.0 points.
- Use the same 250-tick bar data, P1 dates only.
- **Stability test:** If P85 and P90 shift by >15% across the three settings (e.g., P85 at 5.25pt = 19.5 but P85 at 7.0pt = 24.0 → 23% shift), the zigzag reversal amount materially affects the framework and must be treated as a parameter in the sweep.
- **Expected outcome:** Larger reversal filters out small swings, shifting the distribution right. P85 should increase but by less than the reversal increase — the tradeable swings (15+ pts) should be relatively stable across settings since they're well above all three reversal thresholds.
- **Kill condition:** If P85/P90 shift >15%, STOP and reconsider whether the percentile framework is robust enough to drive parameter selection. The zigzag reversal itself would need optimization, which adds a layer of fragility.
- **Pass condition:** P85/P90 shift ≤15% → 5.25pt setting is fine, proceed with the sweep.

### Note: Cap-Walk Distance (Future Investigation, NOT in This Sweep)
- Currently cap-walk distance = StepDist. When cap is hit and price moves StepDist against, anchor walks.
- With smaller StepDist (e.g., 20), cap-walks are closer together — potentially walking the anchor too aggressively.
- A future refinement could decouple cap-walk distance as a separate parameter (e.g., set it to P90 or P95 of zigzag distribution, wider than StepDist, giving more recovery room in damage control).
- **NOT included in Phase 1 sweep** — too many parameters already. If cap-walk losses remain problematic after optimization, revisit as a Phase 2 or post-P2 investigation.

### Step 2: StepDist × AddDist Sweep (Fixed AND Adaptive)

> **⚠️ PREREQUISITE: Step 1 simulator modification AND Step 1b zigzag sensitivity check must BOTH pass before running this sweep. If Step 1b kills the percentile framework, run fixed configs ONLY.**

**Fixed configs (30 simulations):**
- StepDist: 16, 18, 20, 22, 24, 26
- AddDist for each StepDist: SD-8, SD-6, SD-4, SD-2, SD (coupled baseline)
  - Example: SD=20 → AddDist = 12, 14, 16, 18, 20
  - Constraint: AddDist ≥ 10 (floor), AddDist ≤ StepDist

**Adaptive configs (9 simulations):**
- StepDist = rolling zigzag percentile: P80, P85, P90
- AddDist = rolling zigzag percentile: P65, P70, P75
- Constraint: AddDist percentile < StepDist percentile always
- 200-swing rolling window, computed from ALL RTH zigzag swings (09:30-16:00)
- Floor of 10 pts for both StepDist and AddDist (clamp if rolling value drops below)
- For each adaptive config, report the effective range (min/max/mean across P1) to verify actual adaptation. If range < 4 pts, the adaptation is marginal.

**Total: ~39 full-P1 tick simulations.** Plan execution time accordingly.

**All configs share:**
- SeedDist = StepDist for this step (fixed configs: SeedDist = fixed SD; adaptive configs: SeedDist = rolling percentile. Coupled to isolate StepDist/AddDist effect.)
- Session window = 09:30-16:00 (full RTH, to isolate parameter effect)
- ML=1, cap=2 (reopened in Step 2b on winners only)
- No SpeedRead filter
- Full P1 (Sep 21 – Dec 14), daily flatten 16:00, cost_ticks=1

> **⚠️ REMINDER: AddDist controls the ADD trigger only. StepDist controls REVERSAL and CAP-WALK triggers. They are separate parameters. For adaptive configs, both are read from the rolling zigzag distribution at each cycle entry — they change dynamically throughout P1.**

Report per config:
- Cycles, clean %, gross PF, net PF @1t, net PnL
- Mean MAE, P75 MAE, max single-cycle loss
- Daily mean PnL, daily std dev, session win%
- Cycles/hour
- **EV components:** P_clean, P_1add_recover, P_capwalk, P_deep_loss, and mean PnL for each outcome category. This validates the distribution-based EV estimates against actual simulation.
- **For adaptive configs ALSO report:** effective StepDist range (min/max/mean), effective AddDist range, and whether the P1a→P1b regime shift is visible in the rolling values.

**Present as:**
- Heatmap: Fixed StepDist (rows) × Fixed AddDist (columns) → net PF
- Heatmap: Fixed StepDist × AddDist → EV per cycle
- Table: Adaptive configs ranked alongside the top fixed configs

**Key comparison:** Does the best adaptive config beat the best fixed config? If adaptive wins by <3% NPF AND adaptation range is <4 pts, prefer fixed (simpler, easier to implement in C++). If adaptive wins by >3% OR shows >4 pt adaptation range across regimes, adaptive is the stronger foundation.

### Step 2b: ML and Position Cap Re-Evaluation
- **Run ONLY on the top 2-3 StepDist/AddDist winners from Step 2.** Not a full grid.
- ML sweep: 1, 2 (with ML=2, add quantity doubles: first add = 1 contract, second add = 2 contracts if cap allows)
- Cap sweep: 2, 3
- This is 2 ML × 2 cap × 2-3 configs = 8-12 additional simulations.
- All other settings same as Step 2 (SeedDist = StepDist, full RTH, no SpeedRead).

> **⚠️ WHY THESE ARE REOPENED: ML and cap were tested with AddDist=StepDist=25. With decoupled AddDist (likely 12-18 from Step 2), adds fire at better prices. ML=2 adds 2 contracts at entry-15 instead of entry-25 — the average entry is much closer to the market. Cap=3 with AddDist=15 means the third add fires at 30 pts adverse — comparable total dollar risk to old cap=2/AD=25 but 3 contracts with better average entry.**

Report per config (same metrics as Step 2) plus:
- Max position size reached (should never exceed cap)
- Mean position size at cycle exit
- Total dollar risk at worst point (position × max adverse per contract)

**Kill condition:** If ML=2 or cap=3 doesn't improve EV per cycle by >10% over ML=1/cap=2, keep the simpler config. Higher ML and cap add implementation complexity and margin requirements.

### Step 3: SeedDist Optimization
- Using the top 2-3 StepDist/AddDist/ML/cap combos from Steps 2 + 2b
- SeedDist sweep: 10, 12, 15, 18, 20, SD (= StepDist)
- Also test sigma-band: mean + Nσ of rolling zigzag (200-swing window, ALL RTH swings), N = 0.5, 0.75, 1.0, 1.25, 1.5
  - Floor of 10 pts
- Report same metrics as Step 2 plus seed accuracy

### Step 4: Session Window Optimization
- Using best StepDist/AddDist/ML/cap/SeedDist from Steps 2-3
- Test: 09:30-11:30 vs 09:30-13:30 vs 09:30-16:00
- Report: NPF, PnL, PnL per clock-hour (efficiency metric), worst day, cycles/hr
- **Key metric: PnL per clock-hour, not total PnL.** A window that produces +400 ticks in 2 hours (200/hr) beats one that produces +500 in 6.5 hours (77/hr) because you're exposed to less risk for more return per unit time.

> **📌 LATE-SPEC REMINDER: Phase 1 tests base economics ONLY. No SpeedRead. No feature filters. The base config must show positive EV unfiltered. If it doesn't, no amount of filtering saves it. Phase 2 layers refinements on top.**

### Step 5: Summary and Freeze Base Config
- Present the best base config with all metrics
- Compare against SD=25/AddDist=25 baseline (the "old" config)
- Save complete cycle dataset as `full_p1_base_cycles.parquet` with fields:
  entry_time, exit_time, direction, gross_pnl, net_pnl, adds, cap_walks, mfe, mae, cycle_duration, block, stepdist_used, adddist_used, seeddist_used
- Save config as `phase1_base_config.json`
- State clearly: fixed or adaptive? What values?

**This config must show positive EV unfiltered. If it doesn't, no amount of filtering will save it.**

---

## E. Phase 2 Structure — Refinements on Validated Base

**Goal:** Layer improvements onto the Phase 1 base config. Each layer must demonstrably improve or be dropped. Simpler wins ties.

> **⚠️ CRITICAL: All Phase 2 work uses the cycle dataset from Phase 1 Step 5. Features must be RECOMPUTED on the new cycle data (not the old SD=25 baseline). The StepDist/AddDist may have changed, which changes cycle timing, adds, MAE — all feature values shift.**

### Step 1: SpeedRead RTH Recalibration
- RTH distribution analysis (filter existing composite to session window from Phase 1)
- Quintile diagnostic on Phase 1's base cycles
- Kill condition: Q5-Q1 spread < 0.15 → SpeedRead dead for RTH
- Threshold sweep (both directions) if signal exists
- NOTE: SpeedRead may be less useful now — the session window restriction already concentrates trading in high-speed periods

### Step 2: SpeedRead Hysteresis (if SpeedRead survived Step 1)
- Hysteresis bands on the best threshold
- Evaluate by stability (fewer state changes), not just PF

### Step 3: Feature Discovery
Using Phase 1's base cycle dataset (NOT the old SD=25 cycles), compute and evaluate:

**Distance features:**
1-3: Distance from VWAP, VWAP/ATR, session midpoint

**Structure features:**
4-6: Retracement %, zigzag num bars, zigzag reversal distance

**Sigma-band features:**
7-9: Rotation mean (200-swing zigzag, ALL RTH), rotation std, entry sigma level (seed-only, NaN for reversals)

**Volume features:**
10-11: Session volume ratio, volume rate

**Path-dependent (rank separately):**
12-14: Session PnL, cycle count, prior cycle PnL

> **⚠️ REMINDER: Features 15-17 below use STRATEGY cycle windows (last 20 cycles). Features 7-9 use ZIGZAG swing windows (last 200 swings). These are different data sources and different time horizons. Do not confuse them.**

**New from cycle analysis:**
15: clean_cycle_probability (rolling % of clean cycles — no adds — over last 20 STRATEGY cycles, NOT zigzag swings. Different window from the 200-swing zigzag window for features 7-9.)
16: current_sd_vs_p85 (StepDist / rolling zigzag P85 — calibration health monitor)
17: mae_risk_ratio (rolling mean MAE / StepDist over last 20 strategy cycles)

Quintile diagnostic per feature. SpeedRead redundancy check (|r| > 0.7).
Kill condition per feature: < 3% NPF improvement over base.

### Step 4: Risk Mitigation
- Adaptive cycle stop: N × rolling zigzag std (N = 1.5, 2.0, 2.5, 3.0)
- Max daily loss: -100, -150, -200, -250 ticks
- Max cap-walks per cycle: 2, 3, 4, 5
- Evaluate by tail-risk reduction vs mean PnL cost
- **Counterfactual analysis for adaptive stop:** For each stopped cycle, continue the simulation from the stop point WITHOUT the stop to determine if price eventually reversed StepDist in favor. Report % of stopped cycles that would have recovered and mean PnL of recovered vs non-recovered. This quantifies cost of the stop (good cycles killed) vs benefit (bad cycles cut).
- Test individually then best combination

> **⚠️ REMINDER: Phase 2 layers refinements on the Phase 1 base. Each layer must demonstrably improve or be DROPPED. Simpler configs generalize better. Do NOT include a layer "because we tested it."**

### Step 5: Final Config Assembly & Freeze
- Layered improvement table (base → +SpeedRead → +features → +risk mitigation)
- Each layer must improve or be dropped
- Complete frozen parameter table
- C++ replication plan
- All artifacts saved
- Contamination ledger updated

**Frozen Config Table:**

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
| SpeedRead filter | ? (threshold/hysteresis/killed) | Phase 2 Steps 1-2 |
| Feature filter(s) | ? (or none) | Phase 2 Step 3 |
| Adaptive cycle stop | ? (Nσ or none) | Phase 2 Step 4 |
| Max daily loss | ? (ticks or none) | Phase 2 Step 4 |
| Max cap-walks | ? (or unlimited) | Phase 2 Step 4 |
| Daily flatten | 16:00 ET (or session window end) | Settled |
| cost_ticks | 1 | Settled |

> **📌 REMINDER: The frozen config table above is the SINGLE SOURCE OF TRUTH for P2a validation and C++ implementation. Every "?" must be filled with a specific value by the end of Phase 2. AddDist is a separate row from StepDist. Session window specifies the end time.**

### Step 6: C++ Replication Plan
- **NOTE: The V1.3 logic spec created earlier in this conversation is OBSOLETE.** It assumed StepDist=25 fixed, AddDist=StepDist, and no session window parameter. Phase 2 must produce a new V1.4 logic spec from scratch based on the frozen config. Do NOT reference or update the V1.3 doc.
- AddDist as new input parameter (separate from StepDist)
- ML and Position cap as configurable inputs (no longer hardcoded to 1 and 2)
- Session window start/end as inputs (with flatten-at-window-end behavior)
- ZigZagRegime study (if adaptive validated): 200-swing circular buffer, rolling percentiles as subgraphs
- Adaptive StepDist/AddDist reads from ZigZagRegime subgraphs
- Adaptive stop reads from ZigZagRegime std subgraph
- All via GetStudyArrayUsingID
- Flag anything that can't be done in Sierra Chart

---

## F. P2 Holdout Structure

- P2a: replication gate (one-shot, frozen config from Phase 2)
- P2b: final holdout (only if P2a passes)
- Date range TBD from actual P2 data
- UNTOUCHED until Phase 2 completes

## G. Data Files

- **1-tick data:** `bar_data_1tick_rot` covering full P1 (Sep 21 – Dec 14)
- **250-tick bars:** `NQ_BarData_250tick_rot_P1.csv` (127,567 bars)
  - Close = `Last` (col 6), Volume (col 7). Headers have leading spaces.
  - Zigzag cols: `Zig Zag` (14), `Reversal Price` (16), `Line Length` (17), `Num Bars` (18)
  - VWAP must be computed: cumulative(price × volume) / cumulative(volume), reset at session open
  - **File extends beyond P1 into P2 — FILTER to P1 dates**
- **SpeedRead composite:** `speedread_250tick.parquet` (existing, all hours)
- **Simulator:** `run_seed_investigation.py` (needs AddDist modification for Phase 1)
- **Reference data:** `rth_swing_block_summary.json`, `rth_swing_block_clocktime.json`, `cycle_vs_zigzag_comparison.json`, `cycle_distances_full_p1_rth.parquet`

> **⚠️ FINAL REMINDER: The zigzag sanity checks are RTH median≈11.0, P85≈19.5, P90≈22.25. If computed values don't match, check date filtering (P2 leak) or zigzag column parsing (leading spaces in headers).**

## H. Lost-in-Middle Requirements for the Prompts

- Reminders every 25-35 lines maximum
- ⚠️ inline at every critical parameter, decision point, kill condition
- 📌 mid/late-document context summaries
- Bottom self-check checklists per step
- P2 data leak warning repeated in both prompts
- "AddDist ≠ StepDist" reminder near every distance threshold check
- Simulator modification prerequisite flagged before any sweep runs
- Zigzag sanity checks: RTH median≈11.0, P85≈19.5, P90≈22.25
- EV components (P_clean, P_1add, P_capwalk, P_deep) required in sweep reporting
- Feature recomputation reminder in Phase 2 (use Phase 1 cycle data, not old SD=25 data)
