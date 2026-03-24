# Risk Mitigation Investigation — Entry Execution, Exit Structure & Position Sizing

**Purpose:** Investigate modifications to entry execution, exit structure, and position 
sizing that reduce risk asymmetry on the v3.2 qualifying trade population. The scoring 
model and trade selection are FROZEN. This analysis modifies only what happens AFTER 
the waterfall selects a trade: where to enter, how to exit, and how much to risk.

**Branch:** `main` (post `v3.2-post-ray` tag)
**Pipeline version:** 3.2 (model frozen, entry/exit execution under investigation)
**Date:** 2026-03-24

**PRIOR RUN LESSONS (critical — read before starting):**
A prior run of this investigation produced valid Surface B results but had three 
errors that invalidate Surface A, stacking, and P2 validation:
1. **Surface A geometry was inverted.** The GSD incorrectly claimed deeper entries 
   at demand zones worsen R:R because "shorts at demand zones" have growing stops. 
   Demand zones are LONGS, not shorts, and deeper entry ALWAYS shrinks stop distance 
   and grows target distance for both zone types. Surface A MUST include a mandatory 
   geometry verification step before any simulation.
2. **P2 population was wrong.** M2 P2 showed 419 trades instead of the correct ~309. 
   The waterfall filters (RTH, seq≤2, TF≤120m, Mode 1 overlap exclusion) were not 
   applied consistently. P1 population (239 M2 trades) was not independently verified. 
   Both P1 AND P2 populations must be verified against the correct non-overlapping 
   waterfall before any simulation runs.
3. **M2 target reduction was never tested.** 54% of M2 trades exit at time cap, 
   including winners. The 1.0×ZW target may be too ambitious. This run includes 
   target reduction as an additional Surface B test.

**Nothing from the prior run is carried forward.** All surfaces run fresh.

**The problem this investigation addresses:**
- Mode 1: 1 loss (194t net) erases 3.5 wins (56t net each). At 94.8% WR this works, 
  but WR compression to 88% cuts PF from 6.26 to ~2.0.
- Mode 2: Absolute loss on wide zones is severe. A 400t zone → 600t stop → 1,800t 
  loss at 3 contracts. Even with 1.5:1 R:R, the dollar magnitude is dangerous.
- Both modes use flat 3-contract entries at zone edge with no BE, no trail, no partials.

---

## Corrected Baseline (from Analysis B non-overlapping waterfall)

| Metric | Mode 1 (A-Eq ModeA) | Mode 2 (B-ZScore RTH) | Combined |
|--------|---------------------|----------------------|----------|
| P1 trades | 107 | 239 | 346 |
| P1 PF @3t | 8.50 | 4.71 | — |
| P2 trades | 96 | 309 | 405 |
| P2 PF @4t | 6.26 | 4.10 | 4.30 |
| WR | 96.3% (P1) / 94.8% (P2) | 74.5% (P1) | — |
| Stop | 190t fixed | max(1.5×ZW, 120t) | — |
| Target | 60t fixed | 1.0×ZW | — |
| Time cap | 120 bars | 80 bars | — |
| Max DD | 193t | 576t | — |
| Current entry | Zone edge, 3 contracts | Zone edge, 3 contracts | — |

⚠️ THE SCORING MODEL IS FROZEN. Trade selection does not change. All modifications 
operate on the SAME qualifying trade population. The goal is to improve risk-adjusted 
returns (reduce loss magnitude, improve R:R) while preserving or improving PF on P2.

---

## Four Investigation Surfaces

| Surface | What Changes | What's Frozen | Goal |
|---------|-------------|--------------|------|
| A: Entry Execution | Where within the zone to enter, how to build position | Which trades to take | Improve R:R by entering deeper |
| B: Exit Structure | Stop size, BE, trail, partials, time cap | Entry point, trade selection | Reduce loss magnitude |
| C: Position Sizing | Contracts per trade, conditional on risk | Entry, exits, selection | Cap dollar exposure per event |
| D: Loss Cap | Maximum ticks risked per trade | Everything else | Hard ceiling on worst-case loss |

⚠️ INVESTIGATION ORDER: Step 0 (diagnostics) → Surface B (exit structure) → 
Surface A (entry execution) → Stacking (best of A + B) → Surface C+D (design 
decisions from results). This order is deliberate: B can run immediately on existing 
trade outcomes. A requires penetration depth data verified first. C+D are informed 
by A+B results, not independent simulations.

---

## File Locations

```
QUALIFYING TRADE DATA:
  c:\Projects\pipeline\shared\archetypes\zone_touch\output\p1_scored_touches_aeq_v32.csv
  c:\Projects\pipeline\shared\archetypes\zone_touch\output\p1_scored_touches_bzscore_v32.csv
  c:\Projects\pipeline\shared\archetypes\zone_touch\output\qualifying_trades_ray_context_v32.csv

RAW TOUCH + BAR DATA:
  c:\Projects\pipeline\stages\01-data\data\touches\NQ_ZTE_raw_P1.csv
  c:\Projects\pipeline\stages\01-data\data\touches\NQ_ZTE_raw_P2.csv

SIMULATION SCRIPTS:
  c:\Projects\pipeline\shared\archetypes\zone_touch\zone_touch_simulator.py
  c:\Projects\pipeline\stages\04-backtest\zone_touch\prompt3_holdout_v32.py

SCORING MODELS:
  c:\Projects\pipeline\shared\archetypes\zone_touch\output\scoring_model_aeq_v32.json
  c:\Projects\pipeline\shared\archetypes\zone_touch\output\scoring_model_bzscore_v32.json
  c:\Projects\pipeline\shared\archetypes\zone_touch\output\feature_config_v32.json
```

⚠️ INSPECT `zone_touch_simulator.py` BEFORE writing any simulation code. Understand:
1. How entry price is determined (zone edge? touch bar close? some offset?)
2. Whether it supports multi-contract entries at different prices
3. Whether it enforces position overlap constraints (only one trade at a time)
4. How MFE/MAE/exit_type/bars_held are computed and recorded

---

## Step 0: Diagnostics (MANDATORY FIRST STEP)

⚠️ This step produces the data foundation for ALL subsequent surfaces. Do NOT 
skip any sub-step.

### 0-pre: Population Verification (MANDATORY BEFORE ANYTHING ELSE)

⚠️ THE PRIOR RUN HAD WRONG P2 POPULATION. Verify BOTH P1 and P2 before proceeding.

**P1 waterfall construction:**
1. Score ALL P1 touches using frozen A-Eq model (`scoring_model_aeq_v32.json`)
2. Score ALL P1 touches using frozen B-ZScore model (`scoring_model_bzscore_v32.json` 
   — use frozen mean/std, do NOT refit StandardScaler)
3. Flag Mode 1: A-Eq score ≥ 45.5
4. Flag Mode 2: B-ZScore ≥ 0.50 AND RTH AND seq ≤ 2 AND TF ≤ 120m
5. EXCLUDE Mode 1 trades from Mode 2 (A-Eq has priority)
6. Combined = Mode 1 + Mode 2 (non-overlapping)

**P1 count verification:**
| Population | Expected | Actual | Pass? |
|-----------|----------|--------|-------|
| P1 Mode 1 qualifying | ~127 | ? | ? |
| P1 Mode 2 qualifying (excl overlap) | ~215-230 | ? | ? |
| P1 Mode 1 traded (after position overlap) | ~107 | ? | ? |
| P1 Mode 2 traded (after position overlap) | ~239 | ? | ? |

**P2 waterfall construction (same filters, same thresholds):**
Apply identical steps 1-6 to P2 data.

**P2 count verification:**
| Population | Expected | Actual | Pass? |
|-----------|----------|--------|-------|
| P2 Mode 1 qualifying | ~108 | ? | ? |
| P2 Mode 2 qualifying (excl overlap) | ~330-350 | ? | ? |
| P2 Mode 1 traded | ~96 | ? | ? |
| P2 Mode 2 traded | ~309 | ? | ? |

⚠️ IF P2 M2 TRADED IS NOT ~309 (±15), STOP. The most likely issues:
- RTH filter not applied (includes ETH/overnight → too many trades)
- seq ≤ 2 gate not applied
- TF ≤ 120m filter not applied
- Mode 1 overlap not excluded from Mode 2
Compare to `ray_conditional_analysis_v32.py` which produced 309 on P2.

⚠️ IF P1 COUNTS DIFFER BY >10% FROM EXPECTED, STOP and investigate before 
proceeding. All subsequent analysis depends on correct populations.

📌 REMINDER: The scoring model is FROZEN. Use frozen thresholds (A-Eq 45.5, 
B-ZScore 0.50) and frozen StandardScaler parameters. Do NOT refit anything.

### 0a: Per-Trade Outcome Data

For ALL P1 qualifying trades (Mode 1: 107 trades, Mode 2: 239 trades), extract 
or compute per-trade outcomes using the BASELINE exit parameters:

| Column | Description |
|--------|------------|
| trade_id | Unique identifier |
| mode | 1 or 2 |
| entry_price | Exact entry price used by simulator |
| zone_edge_price | Zone boundary price |
| zone_width | Zone width in ticks |
| stop_price | Exact stop price |
| target_price | Exact target price |
| stop_dist | Entry-to-stop distance in ticks |
| target_dist | Entry-to-target distance in ticks |
| pnl_ticks | Per-contract PnL in ticks |
| exit_type | TARGET_HIT, STOP_HIT, TIME_CAP |
| mfe_ticks | Maximum favorable excursion from entry |
| mae_ticks | Maximum adverse excursion from entry |
| bars_held | Bars from entry to exit |
| win | Boolean |

⚠️ CHECK: Does the simulator entry = zone_edge_price exactly? If there's an offset, 
document it. The entry execution analysis (Surface A) depends on knowing the exact 
relationship between entry_price and zone boundaries.

📌 REMINDER: Use BASELINE exits (Mode 1: FIXED 190t/60t/TC120, Mode 2: ZONEREL). 
Verify aggregate PF matches known values (M1 PF@3t ≈ 8.50, M2 PF@3t ≈ 4.71).

### 0b: MAE Distribution — The Critical Diagnostic

⚠️ THIS IS THE MOST IMPORTANT OUTPUT OF STEP 0. The MAE distribution of LOSERS 
tells you exactly how much room the stop has to tighten.

For Mode 1 LOSERS (107 × 5.2% ≈ 6 trades):

⚠️ MAE INTERPRETATION: Stop-hit losers will ALL have MAE = stop distance (190t) 
because that's where they exited. Time-cap losers may have MAE < 190t (they were 
losing at TC but never reached the stop). The table below captures BOTH types. 
The key diagnostic is the TIME dimension: at what bar did MAE first exceed each 
threshold? Fast breaches (< 5 bars) = decisive failures. Slow breaches (> 60 bars) 
= time decay failures that could be caught by TC tightening.

| Loser # | Exit Type | MAE (ticks) | Bar MAE > 60t | Bar MAE > 120t | Bar MAE > 150t | PnL |
|---------|-----------|-------------|---------------|----------------|----------------|-----|
| 1 | ? | ? | ? | ? | ? | ? |
| 2 | ? | ? | ? | ? | ? | ? |
| 3 | ? | ? | ? | ? | ? | ? |
| 4 | ? | ? | ? | ? | ? | ? |
| 5 | ? | ? | ? | ? | ? | ? |
| 6 | ? | ? | ? | ? | ? | ? |

(Adjust row count to actual number of P1 Mode 1 losers)

For Mode 2 LOSERS (239 × 25.5% ≈ 61 trades):

⚠️ Split by exit type first, then bin. Stop-hit losers all have MAE = stop 
distance by definition. TC-exit losers have variable MAE < stop distance.

**Mode 2 stop-hit losers:**
| Metric | Value |
|--------|-------|
| Count | ? |
| % of all Mode 2 losers | ? |
| Mean bars to stop hit | ? |
| Bars to stop < 10 (decisive failures) | ? |
| Bars to stop > 40 (slow bleed) | ? |

**Mode 2 time-cap losers:**
| MAE Bin (as % of stop) | Count | % of TC Losers | Mean PnL |
|------------------------|-------|----------------|----------|
| 0-50% of stop | ? | ? | ? |
| 50-75% of stop | ? | ? | ? |
| 75-100% of stop | ? | ? | ? |

⚠️ Mode 1 has only ~6 P1 losers. Report exact values for EACH loser (MAE, bar of 
max MAE, exit bar, exit type). With this few losers, individual trade profiles are 
more informative than distributions.

### 0c: MFE Distribution — Winner Capture Efficiency

For Mode 1 WINNERS:

| MFE Bin | Count | % | Median PnL | Interpretation |
|---------|-------|---|-----------|----------------|
| 60-80t | ? | ? | ? | Barely reached target |
| 80-120t | ? | ? | ? | Could have captured more |
| 120-200t | ? | ? | ? | Significant money left on table |
| 200t+ | ? | ? | ? | Large continuation missed |

⚠️ This tells you whether a partial exit (T1 at 60t, T2 at 120t+) would capture 
meaningful additional profit. If 80% of winners have MFE within 10t of the 60t 
target, there's nothing to capture. If 40% have MFE > 120t, partials are valuable.

For Mode 2 WINNERS: Same bins relative to zone width.

📌 REMINDER: The scoring model is FROZEN. We are characterizing the outcome 
distribution of existing qualifying trades, not selecting new trades.

### 0d: Zone Width Distribution (Mode 2 Risk Characterization)

For Mode 2 qualifying trades:

| Zone Width Bin | Count | % | Stop Distance | Max Loss @3ct | PF in Bin |
|---------------|-------|---|--------------|---------------|-----------|
| < 100t | ? | ? | 120t (floor) | 360t | ? |
| 100-150t | ? | ? | 150-225t | 450-675t | ? |
| 150-250t | ? | ? | 225-375t | 675-1125t | ? |
| 250-400t | ? | ? | 375-600t | 1125-1800t | ? |
| 400t+ | ? | ? | 600t+ | 1800t+ | ? |

⚠️ KEY QUESTION: Is PF consistent across zone width bins, or do wide zones 
underperform? If wide zones have lower PF AND higher absolute risk, they should 
be position-reduced or skipped. If wide zones have equal PF, the risk is 
proportional and position sizing (Surface C) is the right tool.

### 0e: Time Cap Exit Characterization

For Mode 1 time cap exits (120-bar TC):

| Metric | Value |
|--------|-------|
| N time cap exits | ? |
| % of all Mode 1 trades | ? |
| Mean PnL of TC exits | ? |
| TC exits that were winning (PnL > 0) | ? |
| TC exits that were losing (PnL < 0) | ? |
| Mean bars held before TC (non-TC exits) | ? |

⚠️ If TC exits are predominantly small losers or scratches, they represent 
indecisive trades that consumed capacity without producing results. Tightening 
TC would free capacity for better trades. If TC exits include meaningful winners, 
tightening TC costs profit.

Same analysis for Mode 2 (80-bar TC).

### 0f: Penetration Depth at Touch (Surface A prerequisite)

⚠️ This is the data Surface A needs. For each qualifying touch, measure how far 
price actually penetrated into the zone.

| Column | Definition |
|--------|-----------|
| touch_id | Links to qualifying trade |
| max_penetration_ticks | Maximum depth price reached past zone edge within the FILL WINDOW |
| time_to_max_penetration | Bars from touch to max penetration |

⚠️ FILL WINDOW DEFINITION: Measure penetration over the touch bar PLUS the next 
3 bars (4 bars total). This is the same window Surface A uses for entry fills. 
If the simulator uses a different fill convention (discovered in Step 0a), match 
that convention instead and document it. The penetration measurement and the 
Surface A fill simulation MUST use the same window — otherwise the fill rate 
curve from 0f won't match the actual entry results in A1-A4.

📌 IMPORTANT: "Penetration" = how far PAST the zone edge price went toward the 
opposite zone edge. For a demand zone touch, this is how far price dropped below 
the zone top. For a supply zone touch, how far price rose above the zone bottom.

Report the fill rate curve — if entry is placed at zone_edge + N ticks deeper:

| Entry Depth (past edge) | Trades That Reach | Fill Rate | vs Edge Entry |
|------------------------|------------------|-----------|---------------|
| 0t (edge, current) | 107 / 239 | 100% | baseline |
| 10t | ? | ? | ? |
| 20t | ? | ? | ? |
| 30t | ? | ? | ? |
| 40t | ? | ? | ? |
| 50t | ? | ? | ? |
| 60t | ? | ? | ? |
| 80t | ? | ? | ? |
| 100t | ? | ? | ? |

⚠️ Report Mode 1 and Mode 2 SEPARATELY. Mode 2 has wider zones on average, 
so penetration depth may be systematically different.

### 0g: Missed Trade Characterization

⚠️ The simulator skips qualifying touches when a position is already open. 
Characterize these missed trades.

| Metric | Mode 1 | Mode 2 |
|--------|--------|--------|
| Qualifying touches | 127 | 325 (pre-overlap) |
| Traded | 107 | 239 |
| Missed (position overlap) | 20 | 86 |
| Miss rate | 15.7% | 26.5% |

For the missed trades, compare to traded population:

| Attribute | Traded (mean) | Missed (mean) | Different? |
|-----------|--------------|---------------|-----------|
| A-Eq / B-ZScore score | ? | ? | ? |
| Zone width | ? | ? | ? |
| Session distribution | ? | ? | ? |
| Timeframe distribution | ? | ? | ? |

⚠️ If missed trades look identical to traded trades, throughput matters — faster 
exits would capture real additional value. If missed trades are systematically 
weaker (lower scores, off-session), the position overlap is a beneficial filter 
and throughput gains are illusory.

**Also measure: what was the simulator doing when it missed the trade?** Was the 
active position a winner in progress, a loser in progress, or a TC-bound drift? 
If most misses happen during long-held drifting trades, tightening TC would 
capture the missed trades AND reduce the drifter's bleed.

📌 STEP 0 PRODUCES 8 OUTPUTS. Verify all 8 are complete before proceeding:
- [0-pre] P1 AND P2 population counts verified
- [0a] Per-trade outcome CSV
- [0b] MAE distribution (losers)
- [0c] MFE distribution (winners)
- [0d] Zone width distribution with per-bin PF (Mode 2)
- [0e] Time cap exit characterization
- [0f] Penetration depth / fill rate curve
- [0g] Missed trade characterization

**If running as a single session:** Print all Step 0 outputs, review them yourself, 
and only proceed to Surface B once you have confirmed: (a) aggregate PF matches 
baseline, (b) MAE/MFE distributions make sense, (c) fill rate curve is smooth, 
(d) missed trade characterization is complete. If anything is unexpected, STOP.

**If running as a multi-turn session:** Post Step 0 results and wait for confirmation 
before proceeding.

---

## Surface B: Exit Structure Modifications

⚠️ ENTRIES ARE UNCHANGED IN THIS SECTION. All trades enter at zone edge, 
3 contracts, exactly as in the baseline. Only exit behavior changes.

⚠️ THROUGHPUT INFLATION WARNING: Any modification that shortens hold times will 
mechanically increase trade count by freeing position capacity. Analysis B proved 
this effect is real (obstacle ceiling added 44 phantom trades). To control for 
this, report BOTH:
- Per-trade metrics (PF, WR, mean PnL on the SAME trade population)
- Aggregate metrics (including any additional trades from freed capacity)
Mark any trade count change from baseline as THROUGHPUT EFFECT.

### B1: Stop Reduction (Mode 1)

⚠️ Use the MAE distribution from Step 0b to guide which stop levels to test. 
Only test stops where the MAE data suggests meaningful loss savings without 
excessive additional stop-outs.

Test tighter stops on Mode 1 P1 qualifying trades (107 trades):

| Stop | P1 PF @3t | P1 Trades | WR% | Mean Win | Mean Loss | Loss:Win | New Stop-Outs |
|------|----------|-----------|-----|----------|-----------|----------|---------------|
| 190t (baseline) | 8.50 | 107 | 96.3 | +60t | -190t | 3.17:1 | — |
| 170t | ? | ? | ? | ? | ? | ? | ? |
| 150t | ? | ? | ? | ? | ? | ? | ? |
| 130t | ? | ? | ? | ? | ? | ? | ? |
| 120t | ? | ? | ? | ? | ? | ? | ? |
| 100t | ? | ? | ? | ? | ? | ? | ? |

⚠️ "New Stop-Outs" = trades that were WINNERS at 190t but become LOSERS at the 
tighter stop. These are the cost of tightening. If a stop at 150t converts 2 
winners to losers but saves 40t on each of the 4 existing losers, net impact = 
-2×210t + 4×40t = -260t → worse. The math must be done explicitly per stop level.

📌 REMINDER: The model is FROZEN. We are testing exits on the SAME 107 trades. 
Trade count should NOT change (same entries). If trade count changes, it's a 
throughput artifact — flag it.

### B2: Stop Reduction (Mode 2)

Test tighter stops on Mode 2 P1 qualifying trades (239 trades):

| Stop Multiplier | P1 PF @3t | WR% | Mean Loss | New Stop-Outs |
|----------------|----------|-----|-----------|---------------|
| 1.5×ZW floor 120t (baseline) | 4.71 | 74.5 | ? | — |
| 1.3×ZW floor 100t | ? | ? | ? | ? |
| 1.2×ZW floor 100t | ? | ? | ? | ? |
| 1.0×ZW floor 80t | ? | ? | ? | ? |
| **Conditional: 1.5×ZW if ZW<200t, 1.2×ZW if ZW≥200t** | ? | ? | ? | ? |
| **Conditional: 1.5×ZW if ZW<200t, 1.0×ZW if ZW≥200t** | ? | ? | ? | ? |

⚠️ The conditional stops directly address the absolute loss problem on wide zones 
without hurting narrow-zone trades. These are the HIGHEST PRIORITY Mode 2 tests.

### B3: Breakeven Stop (Mode 1)

After MFE reaches a trigger level, move stop to entry (scratch on reversal instead 
of full loss). Test multiple BE trigger levels:

| BE Trigger (MFE) | P1 PF @3t | WR% | Scratch Count | Full Losses Saved | Mean Win |
|-----------------|----------|-----|---------------|-------------------|----------|
| No BE (baseline) | 8.50 | 96.3 | 0 | 0 | +60t |
| 20t | ? | ? | ? | ? | ? |
| 30t | ? | ? | ? | ? | ? |
| 40t | ? | ? | ? | ? | ? |
| 50t | ? | ? | ? | ? | ? |

⚠️ The cost of BE: some trades that would have won get stopped at BE during a 
normal pullback before reaching the 60t target. Report "BE whipsaw count" — 
trades that hit BE stop, then price later reaches the 60t target level.

### B4: Breakeven Stop (Mode 2)

Same tests on Mode 2. Note that Mode 2 targets are wider (1.0×ZW), so the BE 
trigger should be proportional or tested at fixed levels:

| BE Trigger | P1 PF @3t | WR% | Scratches | Whipsaws |
|-----------|----------|-----|-----------|----------|
| No BE (baseline) | 4.71 | — | 0 | 0 |
| 0.3×ZW | ? | ? | ? | ? |
| 0.5×ZW | ? | ? | ? | ? |
| 30t fixed | ? | ? | ? | ? |
| 50t fixed | ? | ? | ? | ? |

📌 MID-DOCUMENT REMINDER: The scoring model is FROZEN. All modifications are exit 
structure only. Entries unchanged (zone edge, 3 contracts).

### B5: Partial Exits (Mode 1)

Test two-leg structure: close some contracts at T1, hold remainder for T2 with 
tightened stop. All PnL values below are PER-POSITION (all contracts combined).

| Config | Leg 1 | Leg 2 | P1 PF @3t | WR% | Mean Win | Mean Loss | Loss:Win |
|--------|-------|-------|----------|-----|----------|-----------|----------|
| Baseline | 3ct@60t | — | 8.50 | 96.3 | +180t (3×60) | -570t (3×190) | 3.17:1 |
| 2+1 | 2ct@60t | 1ct@120t, stop→entry | ? | ? | ? | ? | ? |
| 2+1 wide | 2ct@60t | 1ct@180t, stop→entry | ? | ? | ? | ? | ? |
| 1+2 | 1ct@60t | 2ct@120t, stop→entry | ? | ? | ? | ? | ? |
| 1+1+1 | 1ct@60t | 1ct@120t | 1ct@180t, stop→entry | ? | ? | ? |

⚠️ PnL COMPUTATION FOR PARTIALS: Each leg has its own entry, exit, and P&L. 
Sum across legs for per-position totals. Example for 2+1 winner that reaches T2:
- Leg 1: 2ct × +60t = +120t
- Leg 2: 1ct × +120t = +120t  
- Total win: +240t (vs baseline +180t)
Example for 2+1 loser where T1 is never hit:
- Leg 1: 2ct × -190t = -380t
- Leg 2: 1ct × -190t = -190t
- Total loss: -570t (same as baseline — partials only help AFTER T1 is hit)

⚠️ The prior M1_A used 3-leg partial exits. This is a return to that concept 
but on the v3.2 qualifying population with different scoring. Report whether the 
runner leg (T2) captures real continuation or just adds risk.

⚠️ CRITICAL: For partial exits, "stop→entry" means the remaining leg's stop 
moves to breakeven after T1 is hit. The maximum loss on the full position is 
therefore: (all legs × stop distance) ONLY if T1 is never hit. If T1 is hit 
first, the remaining legs have zero-risk or positive-risk stops. Report the 
probability that T1 is hit before stop is hit (from MFE analysis in 0c).

### B6: Partial Exits (Mode 2)

Same concept adapted to ZONEREL. All PnL values are PER-POSITION (all contracts).

| Config | Leg 1 | Leg 2 | P1 PF @3t | WR% | Mean Win | Mean Loss | Loss:Win |
|--------|-------|-------|----------|-----|----------|-----------|----------|
| Baseline | 3ct @ 1.0×ZW | — | 4.71 | 74.5 | ? | ? | ~1.5:1 |
| 2+1 half | 2ct @ 0.5×ZW | 1ct @ 1.0×ZW, stop→entry | ? | ? | ? | ? | ? |
| 2+1 full | 2ct @ 0.5×ZW | 1ct @ 1.5×ZW, stop→entry | ? | ? | ? | ? | ? |
| 1+2 | 1ct @ 0.5×ZW | 2ct @ 1.0×ZW, stop→entry | ? | ? | ? | ? | ? |
| 1+1+1 | 1ct @ 0.5×ZW | 1ct @ 1.0×ZW | 1ct @ 1.5×ZW, stop→entry | ? | ? | ? |

⚠️ PnL EXAMPLE for Mode 2 partial (150t zone, stop=225t, 2+1 half):
- Winner reaching T2: Leg 1: 2ct × 75t = +150t, Leg 2: 1ct × 150t = +150t → +300t
- Winner reaching T1 only: Leg 1: 2ct × 75t = +150t, Leg 2: 1ct × 0t (BE) = 0t → +150t
- Loser (T1 never hit): 3ct × -225t = -675t (same as baseline)
- Report probability T1 hit before stop (from Mode 2 MFE analysis in 0c)

⚠️ The key question for Mode 2 partials: does the first target (0.5×ZW) get hit 
often enough to make the runner leg's BE protection meaningful? If Mode 2 MFE 
shows 80%+ of winners exceed 0.5×ZW, partials are viable.

### B7: Time Cap Tightening

Based on Step 0e characterization:

| TC | P1 PF @3t | WR% | TC Exits | Mean TC PnL | Trades Freed |
|----|----------|-----|----------|-------------|--------------|
| 120/80 bar (baseline) | — | — | ? | ? | 0 |
| 90/60 bar | ? | ? | ? | ? | ? |
| 60/40 bar | ? | ? | ? | ? | ? |

⚠️ "Trades Freed" = additional trades that would enter because the TC exit freed 
position capacity. Report these as THROUGHPUT EFFECT — do not count them in 
per-trade PF comparison.

### B8: Trailing Stop (Mode 1)

After target is hit (60t), convert remaining contracts to a trailing stop:

| Trail Distance | P1 PF @3t | Mean Win | Max Win | Trail Captures |
|---------------|----------|----------|---------|----------------|
| No trail (baseline) | 8.50 | +60t | +60t | 0 |
| 25t trail | ? | ? | ? | ? |
| 40t trail | ? | ? | ? | ? |

⚠️ Only relevant for partial exit configs (B5) where a runner leg remains after 
T1. If using single-leg baseline, all contracts exit at 60t and there's nothing 
to trail. Skip this test if B5 partial exits don't improve PF.

### B9: Trailing Stop (Mode 2)

Same concept for Mode 2 runner leg (from B6 partials):

| Trail Distance | P1 PF @3t | Mean Win | Max Win | Trail Captures |
|---------------|----------|----------|---------|----------------|
| No trail (baseline) | 4.71 | ? | ? | 0 |
| 0.3×ZW trail | ? | ? | ? | ? |
| 0.5×ZW trail | ? | ? | ? | ? |
| 50t fixed trail | ? | ? | ? | ? |

⚠️ Mode 2 has wider targets and typically larger MFE. Trailing on the runner 
leg may capture meaningful continuation that Mode 1's tight geometry doesn't 
offer. Skip if B6 partials don't improve PF.

### B10: Target Reduction (Mode 2)

⚠️ NEW TEST — not in the prior run. The prior run found 54% of M2 trades exit 
at time cap, including winners. The 1.0×ZW target may be too ambitious — price 
bounces but often doesn't reach the full zone width within 80 bars.

Test smaller targets on M2 P1 qualifying trades (239 trades):

| Target | P1 PF @3t | WR% | TC Exits | TC Exit % | Mean Win | Mean Loss | L:W |
|--------|----------|-----|----------|-----------|----------|-----------|-----|
| 1.0×ZW (baseline) | 4.71 | 74.5% | ? | ? | ? | ? | ? |
| 0.9×ZW | ? | ? | ? | ? | ? | ? | ? |
| 0.8×ZW | ? | ? | ? | ? | ? | ? | ? |
| 0.75×ZW | ? | ? | ? | ? | ? | ? | ? |
| 0.6×ZW | ? | ? | ? | ? | ? | ? | ? |
| 0.5×ZW | ? | ? | ? | ? | ? | ? | ? |

⚠️ KEY METRICS TO WATCH:
- **TC exit count**: Should drop as target shrinks (more trades hit target before TC)
- **WR**: Should rise (closer target = more winners)
- **Mean Win**: Will drop (smaller target = less per winner)
- **PF**: The net effect — does higher WR × lower win beat lower WR × higher win?
- **L:W ratio**: Should improve (smaller target BUT also fewer TC exits that were 
  intermediate losses)

📌 REMINDER: The model is FROZEN. Only the target multiplier changes. Stop remains 
at baseline for this individual test (1.5×ZW floor 120t, not yet the B2 tightened 
version — test target reduction independently first, stack with B2 later).

⚠️ If target reduction improves PF, it ALSO affects the M2 partial exit analysis 
(B6). A tighter target (e.g., 0.8×ZW) with partials at 0.4×ZW + 0.8×ZW might 
be viable where the prior run's 0.5×ZW + 1.0×ZW partials failed. Re-test B6 
with the best reduced target ONLY if the reduced target improves PF:

| Config | Leg 1 | Leg 2 | PF @3t | WR% | L:W |
|--------|-------|-------|--------|-----|-----|
| Reduced target alone | 3ct @ [best]×ZW | — | ? | ? | ? |
| 2+1 partial | 2ct @ [best/2]×ZW | 1ct @ [best]×ZW, stop→entry | ? | ? | ? |

### B/A Interaction Notes for Stacking

⚠️ BE + PARTIALS INTERACTION: If both B3 (BE stop) and B5 (partial exits) 
individually improve PF, combining them creates ambiguity. In the partial exit 
structure, the runner leg's stop already moves to entry after T1 is hit — that IS 
a breakeven stop for the runner. Adding a separate BE trigger on top means: does 
the BE fire for ALL contracts before T1 is hit, or only the runner after T1? 
Clarify: in stacking, if both B3 and B5 are candidates, the partial exit's 
"stop→entry after T1" REPLACES the standalone BE for the runner leg. The 
standalone BE (B3) only applies to the pre-T1 phase (all contracts). Test this 
specific combined logic explicitly.

📌 REMINDER: Test each modification individually against the baseline first. 
Do NOT combine modifications until Step 3 (Stacking).

---

## Surface A: Entry Execution Modifications

⚠️ Prerequisites: Step 0f (penetration depth / fill rate) must be complete. 
If fill rate drops below 70% at the tested depth, the entry is impractical — 
you miss too many trades.

⚠️ EXITS UNCHANGED IN THIS SECTION (use baseline exit parameters). Only entry 
location and contract allocation change.

### A0: Geometry Verification (MANDATORY BEFORE ANY SURFACE A SIMULATION)

⚠️ THE PRIOR RUN GOT THIS WRONG. The geometry was inverted, producing invalid 
Surface A results. This verification step is NON-NEGOTIABLE.

**The correct geometry for ALL zone types:**

"Deeper" = entering further into the zone interior (away from the touched edge, 
toward the opposite edge). Stop and target LEVELS stay fixed relative to zone 
geometry (not entry price).

For a DEMAND zone (price drops to zone, entry = LONG):
- Zone TOP = touched edge. Zone BOTTOM = opposite edge.
- Baseline entry: at zone TOP
- Stop level: zone_top - 190t (fixed, below zone)
- Target level: zone_top + 60t (fixed, above zone)
- Deeper entry at +20t: enter at zone_top - 20t
- New stop distance: (zone_top - 20t) - (zone_top - 190t) = 170t ← SHRINKS ✓
- New target distance: (zone_top + 60t) - (zone_top - 20t) = 80t ← GROWS ✓
- Loss:Win = 170:80 = 2.13 (improved from 3.17)

For a SUPPLY zone (price rises to zone, entry = SHORT):
- Zone BOTTOM = touched edge. Zone TOP = opposite edge.
- Baseline entry: at zone BOTTOM
- Stop level: zone_bottom + 190t (fixed, above zone)
- Target level: zone_bottom - 60t (fixed, below zone)
- Deeper entry at +20t: enter at zone_bottom + 20t
- New stop distance: (zone_bottom + 190t) - (zone_bottom + 20t) = 170t ← SHRINKS ✓
- New target distance: (zone_bottom + 20t) - (zone_bottom - 60t) = 80t ← GROWS ✓
- Loss:Win = 170:80 = 2.13 (improved from 3.17)

**BOTH zone types: deeper entry = stop shrinks, target grows, R:R improves.**

⚠️ VERIFY ON TWO SPECIFIC TRADES before running any simulation:

**Verification Trade 1 — pick one DEMAND zone Mode 1 trade:**
```
Print:
  Zone type: DEMAND
  Zone top (touched edge): [price]
  Baseline entry price: [price]
  Stop level: [price] (should be 190t below zone top)
  Target level: [price] (should be 60t above zone top)
  Baseline stop distance: [ticks] (should be ~190t)
  Baseline target distance: [ticks] (should be ~60t)
  
  At +20t deeper:
  New entry price: [zone_top - 20t]
  Stop distance: [ticks] (MUST be < baseline, ~170t)
  Target distance: [ticks] (MUST be > baseline, ~80t)
```

**Verification Trade 2 — pick one SUPPLY zone Mode 1 trade:**

⚠️ Supply zone: entry is SHORT. Stop is ABOVE entry, target is BELOW. Deeper 
entry = higher price (further into zone). SHRINKS stop distance, GROWS target.
```
Print:
  Zone type: SUPPLY
  Zone bottom (touched edge): [price]
  Baseline entry price: [price]
  Stop level: [price] (should be 190t above zone bottom)
  Target level: [price] (should be 60t below zone bottom)
  Baseline stop distance: [ticks] (should be ~190t)
  Baseline target distance: [ticks] (should be ~60t)
  
  At +20t deeper:
  New entry price: [zone_bottom + 20t]
  Stop distance: [ticks] (MUST be < baseline, ~170t)
  Target distance: [ticks] (MUST be > baseline, ~80t)
```

⚠️ IF EITHER VERIFICATION SHOWS STOP GROWING OR TARGET SHRINKING, STOP. 
Debug the zone type mapping and stop/target level computation before proceeding.

📌 REMINDER: Entry price in the simulator is at the OPEN of the bar after touch 
(bar_offset = RotBarIndex + 1), a few ticks past zone edge. "Deeper entry" adds 
an ADDITIONAL offset into the zone interior on top of the simulator's baseline.

### A1: Deeper Fixed Entry (Mode 1)

⚠️ ONLY proceed after A0 verification confirms correct geometry.

Instead of entering at zone edge, enter at edge + N ticks deeper into the zone.
Stop and target LEVELS (absolute prices) stay fixed to zone geometry.

⚠️ NOTE: Deeper entry effectively reduces stop distance — this overlaps with 
Surface B1 (stop reduction). In stacking (Step 3), do NOT combine A1 with B1 
naively. The reductions compound.

| Entry Depth | Fill Rate | Stop Dist | Target Dist | Loss:Win | P1 PF @3t | Trades |
|------------|-----------|-----------|-------------|----------|----------|--------|
| 0t (baseline) | 100% | 190t | 60t | 3.17 | 8.50 | 107 |
| 10t | ? | ? | ? | ? | ? | ? |
| 20t | ? | ? | ? | ? | ? | ? |
| 30t | ? | ? | ? | ? | ? | ? |
| 40t | ? | ? | ? | ? | ? | ? |

⚠️ ADJUST DEPTHS FROM STEP 0f DATA: The depths above (10t-40t) are starting 
points. After reviewing the Mode 1 penetration fill rate curve from Step 0f, 
replace these with the depths that correspond to the 90%, 75%, and 60% fill rate 
points from the actual distribution. These are the natural test points — they 
represent the tradeoff frontier between R:R improvement and fill rate cost.

⚠️ The Stop Dist and Target Dist columns above should be computed from ACTUAL 
simulator data, not assumed. If Step 0a confirms entry = zone_edge exactly, then 
Stop Dist = 190 - depth and Target Dist = 60 + depth. If the simulator uses a 
different entry convention, the distances will differ. Compute from actual 
entry_price vs stop_price and target_price for each depth level.

⚠️ KEY TRADEOFF: Deeper entry improves R:R but reduces fill rate. If entering 
20t deeper loses 15% of trades and improves R:R from 3.17 to 2.13, is the net 
PF higher? The simulation answers this. Report both filled-only PF and 
opportunity-adjusted PF (accounting for missed trades that would have won).

⚠️ IMPORTANT: "Fill" means price reaches the deeper entry level within the FILL 
WINDOW defined in Step 0f (touch bar + next 3 bars, or the simulator's convention 
if different). Use the SAME window as 0f — do not change the definition here.

### A2: Deeper Fixed Entry (Mode 2)

Same design choice as A1: stop and target LEVELS fixed to zone geometry. Entry 
depth expressed as proportion of zone width (since Mode 2 zones vary in width):

| Entry Depth (% of ZW) | Fill Rate | Stop Dist | Target Dist | Loss:Win | P1 PF @3t |
|-----------------------|-----------|-----------|-------------|----------|----------|
| 0% (edge, baseline) | 100% | max(1.5×ZW,120) | 1.0×ZW | ~1.5 | 4.71 |
| 10% of ZW | ? | ? | ? | ? | ? |
| 20% of ZW | ? | ? | ? | ? | ? |
| 30% of ZW | ? | ? | ? | ? | ? |

⚠️ ADJUST DEPTHS FROM STEP 0f DATA: The depths above (10%-30% of ZW) are starting 
points. After reviewing the Mode 2 penetration fill rate curve from Step 0f, 
replace these with the depths that correspond to the 90%, 75%, and 60% fill rate 
points from the actual distribution.

📌 REMINDER: Mode 2 stop and target are zone-relative. Entering deeper changes 
the distance to both stop and target LEVELS. Compute the actual distances at 
each entry depth for each trade (zone widths vary).

### A3: Scaled Entry (Mode 1)

Instead of 3 contracts at zone edge, distribute across multiple entry points:

| Config | Entry 1 | Entry 2 | Entry 3 | Fill Rate | Avg Entry | Eff Stop | Eff Target | Loss:Win |
|--------|---------|---------|---------|-----------|-----------|----------|-----------|----------|
| Baseline | 3ct @ edge | — | — | 100% | edge | 190t | 60t | 3.17 |
| 1+1+1 even | 1ct @ edge | 1ct @ +15t | 1ct @ +30t | ? | ? | ? | ? | ? |
| 1+1+1 deep | 1ct @ edge | 1ct @ +20t | 1ct @ +40t | ? | ? | ? | ? | ? |
| 2+1 | 2ct @ edge | 1ct @ +30t | — | ? | ? | ? | ? | ? |
| 1+2 | 1ct @ edge | 2ct @ +20t | — | ? | ? | ? | ? | ? |

⚠️ Eff Stop and Eff Target depend on which legs fill and their contract-weighted 
average entry price. Compute from actual per-leg fill data, not assumed.

⚠️ ADJUST SCALED DEPTHS FROM STEP 0f DATA: The add distances above (15t, 20t, 
30t, 40t) are starting points. After reviewing the Mode 1 fill rate curve, adjust 
the deepest add leg to the 75% fill rate point from Step 0f. The intermediate legs 
should be evenly spaced between edge and the deepest add.

⚠️ PARTIAL FILL LOGIC: For scaled entries, the first leg always fills (edge 
entry). Deeper legs may not fill. Report the partial fill rate — how often do 
all legs fill vs only leg 1 vs legs 1+2?

When not all legs fill, the trade runs with fewer contracts. The P&L must be 
computed contract-by-contract:
- If only 1 of 3 contracts fills: exposure is 1/3, loss is 1/3
- If 2 of 3 fill: exposure is 2/3
- Average across all outcomes gives the effective risk profile

⚠️ DOES THE SIMULATOR SUPPORT MULTI-ENTRY? If `zone_touch_simulator.py` only 
handles single-entry-price trades, you will need to extend it or compute scaled 
entries analytically from the per-bar price data. Document which approach is used.

### A4: Scaled Entry (Mode 2)

Same concept adapted to ZONEREL zone widths:

| Config | Entry 1 | Entry 2 | Entry 3 | Fill Rate | Avg Entry | Eff Stop | Eff Target | Loss:Win | P1 PF @3t |
|--------|---------|---------|---------|-----------|-----------|----------|-----------|----------|----------|
| Baseline | 3ct @ edge | — | — | 100% | edge | max(1.5×ZW,120) | 1.0×ZW | ~1.5 | 4.71 |
| 1+1+1 | 1ct @ edge | 1ct @ +0.1×ZW | 1ct @ +0.2×ZW | ? | ? | ? | ? | ? | ? |
| 2+1 | 2ct @ edge | 1ct @ +0.15×ZW | — | ? | ? | ? | ? | ? | ? |

⚠️ ADJUST SCALED DEPTHS FROM STEP 0f DATA: The add distances above (0.1×ZW, 
0.15×ZW, 0.2×ZW) are starting points. After reviewing the Mode 2 fill rate curve, 
adjust the deepest add leg to the 75% fill rate point from Step 0f. The intermediate 
legs should be evenly spaced between edge and the deepest add.

⚠️ For Mode 2 scaled entries, the effective stop and target distances change 
per-contract because zone widths vary. Report the MEAN effective distances across 
the qualifying population, not a single example.

📌 REMINDER: Test each entry configuration with BASELINE exits first. Do NOT 
combine entry modifications with exit modifications until Step 3 (Stacking).

---

## Step 3: Stacking — Best Combinations

⚠️ ONLY proceed to stacking after Surfaces A and B are individually complete. 
Select the modifications that individually improved P1 PF or improved loss:win 
ratio without material PF degradation.

### 3a: Identify candidates for stacking

From Surface B, list modifications with P1 dPF > 0 or loss:win improvement > 20%:

| Modification | P1 PF @3t | P1 dPF | Loss:Win Change | Candidate? |
|-------------|----------|--------|-----------------|-----------|
| B1: Stop at Xt (M1) | ? | ? | ? | ? |
| B2: Stop at X×ZW (M2) | ? | ? | ? | ? |
| B3: BE at Xt (M1) | ? | ? | ? | ? |
| B5: Partial config (M1) | ? | ? | ? | ? |
| B6: Partial config (M2) | ? | ? | ? | ? |
| B10: Target X×ZW (M2) | ? | ? | ? | ? |

From Surface A:

| Modification | P1 PF @3t | P1 dPF | Fill Rate | Loss:Win Change | Candidate? |
|-------------|----------|--------|-----------|-----------------|-----------|
| A1: Depth Xt (M1) | ? | ? | ? | ? | ? |
| A2: Depth X%ZW (M2) | ? | ? | ? | ? | ? |
| A3: Scaled (M1) | ? | ? | ? | ? | ? |
| A4: Scaled (M2) | ? | ? | ? | ? | ? |

### 3b: Test combinations incrementally

⚠️ SAME METHODOLOGY AS INCREMENTAL FEATURE BUILD. Add one modification at a time, 
in order of individual dPF magnitude. Check whether each additional modification 
improves combined PF or if the interaction is negative.

⚠️ KNOWN INTERACTIONS — handle these explicitly:

**A1/B1 OVERLAP:** Deeper entry already reduces effective stop distance. If 
combining A1 with B1, compute the ACTUAL stop distance from the deeper entry to 
the tightened stop level. They compound: A1 at 20t + B1 at 150t = 130t effective.

**A2/B2 OVERLAP (Mode 2 equivalent):** Same principle for Mode 2. A2 was tested 
with baseline stop (1.5×ZW). B2 tightens to 1.3×ZW. When stacked, the effective 
stop distance from the deeper entry is (1.3×ZW - depth), not (1.5×ZW - depth) or 
(1.3×ZW). Compute the actual combined geometry.

**B3/B5 OVERLAP:** Partial exits include BE for runner leg after T1. Standalone 
BE (B3) only applies to the pre-T1 phase when combined with partials.

**A1/B5 PARTIAL TARGETS:** If combining deeper entry with partials, the partial 
targets are ZONE-EDGE-FIXED (same convention as Surface A). From deeper entry:
- T1 at zone_edge + 60t = now (60 + depth)t from entry
- T2 at zone_edge + 120t = now (120 + depth)t from entry  
- T3 at zone_edge + 180t = now (180 + depth)t from entry
- Stop at zone_edge - 190t = now (190 - depth)t from entry
Compute per-leg PnL with these actual distances.

**B2/B10 OVERLAP:** If both stop tightening (B2) and target reduction (B10) pass 
individually for M2, test them together — tighter stop + smaller target changes 
the full risk geometry.

| Stack | Components | P1 PF @3t | P1 dPF vs Previous | Trades | Loss:Win |
|-------|-----------|----------|-------------------|--------|----------|
| Baseline | — | 8.50 / 4.71 | — | 107 / 239 | 3.17 / 1.5 |
| +Best B mod | ? | ? | ? | ? | ? |
| +Best A mod | ? | ? | ? | ? | ? |
| +Next best | ? | ? | ? | ? | ? |

⚠️ If adding a modification REDUCES combined PF (negative interaction), STOP 
stacking. Report the negative interaction and why it occurs.

⚠️ THROUGHPUT CHECK: If stacked trade count differs from baseline by >5%, the 
difference is throughput effect. Report and separate genuine per-trade improvement 
from throughput inflation.

📌 REMINDER: Mode 1 and Mode 2 are stacked INDEPENDENTLY. A modification that 
helps Mode 1 may hurt Mode 2 (different exit structures, different risk profiles). 
The final stack may be different for each mode.

---

## Step 4: P2 Validation

⚠️ HOLDOUT GATE. Run this step ONLY after stacking is complete and the final 
configuration is frozen from P1.

### 4a: Use the P2 population verified in Step 0-pre

⚠️ The P2 qualifying population was already built and verified in Step 0-pre. 
Use that SAME population. Do NOT rebuild the waterfall — it was already verified 
against the correct counts (M1≈96 trades, M2≈309 trades).

If Step 0-pre was not run on P2 (only P1), run the waterfall now:
1. Score ALL P2 touches using frozen A-Eq and B-ZScore models
2. Apply waterfall: Mode 1 (A-Eq ≥ 45.5) first, Mode 2 (B-ZScore ≥ 0.50, 
   RTH, seq ≤ 2, TF ≤ 120m, excluding Mode 1 overlap) second
3. Verify: P2 Mode 1 ≈ 96 trades, P2 Mode 2 ≈ 309 trades (NOT 419)

⚠️ IF P2 M2 IS ~419, THE FILTERS ARE WRONG. The prior run had this exact error. 
Check RTH, seq≤2, TF≤120m gates and Mode 1 overlap exclusion. Reference 
`ray_conditional_analysis_v32.py` which produced 309 on P2.

### 4b: P2 Baseline on correct population

Simulate P2 qualifying trades with BASELINE exits:

| Metric | P2 M1 | P2 M2 | Combined |
|--------|-------|-------|----------|
| Trades | ~96 | ~309 | ~405 |
| PF @4t | ~6.26 | ~4.10 | ~4.30 |
| WR% | ? | ? | ? |

⚠️ If M2 P2 PF differs from ~4.10 by more than 0.5, investigate — the population 
is likely still wrong.

### 4c: Apply best stack to P2

For each mode's best stack from Step 3:
1. Apply the P1-frozen exit/entry modifications to P2 qualifying trades
2. Simulate with identical parameters (no recalibration)

| Metric | P2 Baseline | P2 Modified (Mode 1) | P2 Modified (Mode 2) | P2 Combined |
|--------|------------|---------------------|---------------------|-------------|
| Trades | 96 / 309 | ? | ? | ? |
| PF @4t | 6.26 / 4.10 | ? | ? | ? |
| WR% | 94.8 / — | ? | ? | ? |
| Max DD | 193 / — | ? | ? | ? |
| Loss:Win | 3.17 / 1.5 | ? | ? | ? |
| Profit/DD | — | ? | ? | ? |

⚠️ PASS CRITERIA:
- P2 PF must not degrade by more than 15% vs baseline
- P2 loss:win ratio must improve (this is the primary objective)
- If PF degrades but loss:win improves materially, report as TRADEOFF — 
  acceptable if the reduction in tail risk justifies the PF cost

⚠️ P2 is ONE-SHOT. No recalibration. No parameter adjustment after seeing P2.

📌 REMINDER: The scoring model is FROZEN throughout. Only entry execution and 
exit structure parameters change. If P2 fails, revert to baseline exits.

---

## Step 5: Design Recommendations (Surfaces C + D)

⚠️ This step does NOT require simulation. It uses the results from Steps 0-4 
to make design recommendations.

### 5a: Position Sizing (Surface C)

Based on Step 0d (zone width distribution) and Step 4 results:

Propose a contracts-per-trade rule:

| Condition | Contracts | Rationale |
|-----------|-----------|-----------|
| Mode 1 (any) | ? | Based on Mode 1 loss:win from best stack |
| Mode 2, ZW < 150t | ? | Low absolute risk |
| Mode 2, ZW 150-250t | ? | Moderate risk |
| Mode 2, ZW 250-400t | ? | High absolute risk |
| Mode 2, ZW > 400t | ? | Extreme risk — consider skip |

### 5b: Loss Cap (Surface D)

Based on the worst-case loss from the best stack configuration:

| Total Risk Cap (all contracts) | Mode 1 Max Contracts | Mode 2 Max Contracts (varies) |
|-------------------------------|---------------------|------------------------------|
| 300t | ? | ? |
| 400t | ? | ? |
| 500t | ? | ? |
| 600t | ? | ? |

### 5c: Net Impact Summary

📌 REMINDER: Compare all results to corrected baseline (P2: 96 + 309 = 405 trades, 
PF 4.30). Mode 1 max loss at 3ct = 582t. Mode 2 max loss varies with zone width.

| Metric | Current Baseline | After Best Stack + Sizing | Change |
|--------|-----------------|--------------------------|--------|
| Mode 1 max loss per event | 582t (3ct) | ? | ? |
| Mode 2 max loss per event | varies (up to 1800t+) | ? | ? |
| Mode 1 loss:win ratio | 3.17:1 | ? | ? |
| Mode 2 loss:win ratio | ~1.5:1 | ? | ? |
| Combined P2 PF @4t | 4.30 | ? | ? |
| Combined P2 Profit/DD | — | ? | ? |

---

## Step 6: Output Report

⚠️ The report must clearly distinguish per-trade improvements from throughput 
effects. Any modification that changed trade count should be flagged.

Produce `risk_mitigation_investigation_v32.md` with:

### Section 1: Population Verification & Diagnostic Summary (Step 0)
- P1 AND P2 population counts (verified against expected)
- MAE/MFE distributions for both modes
- Zone width risk distribution
- TC exit characterization
- Penetration depth / fill rate curves
- Missed trade analysis

### Section 2: Exit Structure Results (Surface B)
- Per-modification P1 results for both modes (B1-B9)
- M2 target reduction results (B10) with TC exit conversion tracking
- M2 partials re-tested with reduced target (if B10 improved PF)
- Best exit modifications identified

### Section 3: Entry Execution Results (Surface A)
- Geometry verification outputs (demand + supply trade)
- Fill rate analysis
- Per-modification P1 results for both modes
- Best entry modifications identified
- Comparison to prior run's (incorrect) Surface A results

### Section 4: Stacking Results
- Incremental stacking table per mode
- All interaction effects documented (A1/B1, A2/B2, B3/B5, A1/B5, B2/B10)
- Final recommended stack per mode

⚠️ REMINDER: Mode 1 and Mode 2 stacks may be different. Report each mode's 
recommended configuration separately, then the combined P2 impact.

### Section 5: P2 Validation
- P2 population verified (96 + 309 = 405, NOT 419 for M2)
- P2 baseline PF on correct population
- P2 stacked results
- Pass/fail per criteria

### Section 6: Design Recommendations
- Position sizing proposal
- Loss cap proposal
- Net impact summary

⚠️ IMPORTANT: If no modifications pass P2 validation, the baseline exits are 
correct and the risk asymmetry is managed through position sizing (Surface C) 
alone. This is a valid outcome — it means the exits are already well-calibrated 
and the R:R problem is addressed by trading smaller, not by changing exit levels.

📌 FINAL REMINDER: The scoring model is FROZEN at v3.2. The 7-feature model, 
thresholds, and waterfall routing are unchanged. This investigation modifies 
ONLY entry execution, exit structure, and position sizing. Every modification 
must pass P1-calibrate / P2-one-shot protocol.

---

## Output Files

Save to: `c:\Projects\pipeline\shared\archetypes\zone_touch\output\`
- `risk_mitigation_investigation_v32.md` — full report
- `qualifying_trades_outcomes_v32.csv` — per-trade outcomes with MAE/MFE (Step 0a)
- `fill_rate_analysis_v32.csv` — penetration depth data (Step 0f)

⚠️ Save script as: 
`c:\Projects\pipeline\shared\archetypes\zone_touch\risk_mitigation_v32.py`
Commit to `main` branch with message:
"Add risk mitigation investigation (entry/exit/sizing)"

---

## Self-Check Before Submitting

- [ ] Step 0-pre: P1 AND P2 populations verified (M1≈107/96, M2≈239/309)
- [ ] Step 0-pre: P2 M2 is NOT 419 (prior run error)
- [ ] Step 0 all 8 diagnostics completed and reported (including 0-pre)
- [ ] Simulator entry convention documented (zone edge? offset?)
- [ ] Simulator multi-entry capability checked
- [ ] MAE of every Mode 1 loser individually reported (small N)
- [ ] Zone width bins include per-bin PF (Mode 2)
- [ ] Missed trade population compared to traded population
- [ ] Surface B modifications tested individually (not combined)
- [ ] Surface B zone-width-conditional stops tested for Mode 2
- [ ] Surface B Mode 2 partials (B6) have same detail level as Mode 1 (B5)
- [ ] Surface B trailing stop tested for Mode 2 (B9) if B6 partials improve PF
- [ ] Surface B M2 target reduction tested (B10) with TC exit conversion tracking
- [ ] Surface B M2 partials re-tested with reduced target if B10 improves PF
- [ ] Surface A geometry verification printed for 1 demand + 1 supply trade (A0)
- [ ] Surface A verified: stop SHRINKS and target GROWS at deeper entry for BOTH zone types
- [ ] Surface A stop/target distances computed from ACTUAL simulator data
- [ ] Surface A depths adjusted from 0f fill rate data (90%/75%/60% points)
- [ ] Surface A fill rates reported per mode
- [ ] Throughput inflation flagged on any modification that changes trade count
- [ ] Stacking follows incremental methodology (one at a time)
- [ ] Stacking accounts for A1/B1 overlap (deeper entry + stop reduction compound)
- [ ] Stacking accounts for A2/B2 overlap (Mode 2 equivalent of A1/B1)
- [ ] Stacking accounts for B3/B5 overlap (BE + partials — pre-T1 vs post-T1)
- [ ] Stacking accounts for A1/B5 partial targets (zone-edge-fixed distances)
- [ ] Stacking accounts for B2/B10 overlap (stop + target both change M2 geometry)
- [ ] Mode 1 and Mode 2 stacked independently
- [ ] Partial exit PnL computed per-position (all contracts summed)
- [ ] P2 population matches Step 0-pre verified counts
- [ ] P2 validation is one-shot (no recalibration)
- [ ] Pass criteria includes both PF and loss:win assessment
- [ ] Position sizing recommendations based on actual data, not arbitrary
- [ ] All files saved to correct directories
- [ ] Script committed to main branch
