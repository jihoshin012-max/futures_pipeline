# Full-P1 Phase 1 — Base Parameter Calibration

> **⚠️ CRITICAL — READ BEFORE AND AFTER IMPLEMENTATION**
> 1. **Full P1 (Sep 21 – Dec 14, 2025).** Both P1a and P1b regimes included.
> 2. **NO SpeedRead. NO feature filters.** This is pure base economics. If the config doesn't show positive EV unfiltered, no amount of filtering saves it.
> 3. **AddDist is a NEW parameter, decoupled from StepDist.** The simulator must be modified BEFORE any sweeps run.
> 4. **Fixed AND adaptive (rolling zigzag percentile) configs tested side by side.**
> 5. **P2 is UNTOUCHED.** P2a/P2b validation happens in a separate prompt after Phase 2.
> 6. **cost_ticks = 1** for all net PF calculations.
> 7. **250-tick CSV extends beyond P1 into P2 — FILTER ALL DATA to P1 dates only.**

---

## Background: Why This Investigation Exists

The rotation strategy's parameters were originally set at StepDist=25, AddDist=25 (coupled), ML=1, cap=2. Zigzag distribution analysis of RTH 250-tick bars revealed:

- RTH median swing = 11.0 pts, P85 = 19.5, P90 = 22.25
- StepDist=25 requires a top-9% swing to complete → only 52% clean cycles
- Mean MAE = 25.23 pts — the average cycle goes 25 against you
- P1a P90 ≈ 20.5, P1b P90 ≈ 23.25 — fixed params are regime-fragile
- **EV at SD=25/AD=25 ≈ +13.4 ticks/cycle. EV at SD=20/AD=15 ≈ +30.3 ticks/cycle (2.3x improvement)**

The mathematical framework:

**Completion probability:** P(swing ≥ StepDist) from zigzag CDF. At SD=25: ~6.5%. At SD=20: ~14%. At SD=16: ~22.5%.

**Why AddDist < StepDist transforms economics:** With AD=15, SD=20 — add at entry-15, anchor resets, reversal at entry+5. Contract 1: +5 pts (+20 ticks). Contract 2: +20 pts (+80 ticks). Total +100 ticks. The 1-add cycle becomes as profitable as a clean cycle.

**Every 1 pt of AddDist reduction = 4 ticks transferred from loss to profit on contract 1.**

> **⚠️ NOTE: These EV estimates assume independent zigzag swings. Real swings have serial correlation. The tick simulation is ground truth. If simulation EV differs from estimates, serial correlation is the likely explanation.**

---

## Settled Items (Do NOT Retest)

- Walking anchor on cap hit
- Tick data = ground truth
- Fast markets help rotation
- Watch price at 09:30 ET (user constraint)
- SR-block: watch price stays fixed (F/G killed)
- HMM deferred
- Daily flatten at 16:00 ET (hard backstop; session window end flattens earlier if applicable)
- cost_ticks = 1
- Zigzag: 5.25 pt reversal, calc mode 3 (validated by Step 1b sensitivity check)

**Reopened:** ML (was 1) and position cap (was 2) — tested in Step 2b after main sweep.

---

## Data

- **1-tick data:** `bar_data_1tick_rot` (full P1)
- **250-tick bars:** `NQ_BarData_250tick_rot_P1.csv` (127,567 bars). Close=`Last` (col 6), Volume (col 7). Zigzag: cols 14, 16, 17, 18. **Headers have leading spaces — strip whitespace.**
- **Simulator:** `run_seed_investigation.py` (needs AddDist modification)

> **⚠️ CSV extends beyond P1. FILTER to Sep 21 – Dec 14 before ANY computation. Zigzag sanity check: RTH median ≈ 11.0, P85 ≈ 19.5, P90 ≈ 22.25.**

---

## Step 1: Simulator Enhancement

Modify `run_seed_investigation.py` to accept separate AddDist parameter.

**Three distance triggers (all from current anchor):**
- **AddDist:** price moves AddDist AGAINST → add 1 contract (if below cap)
- **StepDist:** price moves StepDist IN FAVOR → flatten and reverse
- **StepDist:** price moves StepDist AGAINST when at cap → walk anchor (NOT AddDist)

**Session window:** When window end reached (e.g., 11:30), flatten immediately, full state reset, stop accepting entries. Same behavior as daily flatten.

**ML support:** ML=1 → all adds are 1 contract. ML=2 → first add = 1, second add = 2 (doubling). Cap limits total position.

**Verify:** SD=25, AddDist=25, ML=1, cap=2, window=09:30-16:00 must exactly match the known V1.1 baseline.

> **⚠️ DO NOT PROCEED TO STEP 2 UNTIL VERIFICATION PASSES. The AddDist decoupling changes core simulator logic — any bug here invalidates all downstream results.**

---

## Step 1b: Zigzag Sensitivity Check

> **⚠️ This validates the foundation. If it fails, the entire percentile framework needs rethinking.**

Compute RTH P50, P75, P85, P90, P95 using three zigzag reversal settings: **4.0, 5.25, 7.0 points.** Same 250-tick bars, P1 dates only.

**Pass condition:** P85 and P90 shift ≤ 15% across the three settings → 5.25 pt is robust, proceed.
**Kill condition:** P85/P90 shift > 15% → STOP. Zigzag reversal is itself a parameter, which adds fragility.

**Expected:** Larger reversal filters small swings, shifting distribution right. But tradeable swings (15+ pts) should be stable since they're well above all three thresholds.

---

> **📌 CONTEXT REMINDER:**
> - Phase 1 = base parameter calibration. No SpeedRead. No features.
> - Three triggers: AddDist (add), StepDist (reversal), StepDist (cap-walk)
> - Full P1, RTH, daily flatten, cost_ticks=1
> - Adaptive and fixed configs tested side by side in Step 2
> - ML and cap reopened in Step 2b on winners only

---

## Step 2: StepDist × AddDist Sweep (Fixed AND Adaptive)

> **⚠️ PREREQUISITE: Step 1 verification AND Step 1b pass BOTH required. If Step 1b kills percentile framework, run fixed configs ONLY.**

### Fixed Configs (30 simulations)

| StepDist | AddDist values (SD-8 through SD) |
|----------|--------------------------------|
| 16 | 10*, 10*, 12, 14, 16 |
| 18 | 10, 12, 14, 16, 18 |
| 20 | 12, 14, 16, 18, 20 |
| 22 | 14, 16, 18, 20, 22 |
| 24 | 16, 18, 20, 22, 24 |
| 26 | 18, 20, 22, 24, 26 |

*Floor: AddDist ≥ 10. Constraint: AddDist ≤ StepDist.

### Adaptive Configs (9 simulations)

| StepDist Percentile | AddDist Percentile |
|--------------------|-------------------|
| P80 | P65, P70, P75 |
| P85 | P65, P70, P75 |
| P90 | P65, P70, P75 |

Rolling 200-swing window from ALL RTH zigzag swings. Floor 10 pts for both.

### All Configs Share
- SeedDist = StepDist (coupled in this step — decoupled in Step 3)
- Session window = 09:30-16:00 (full RTH — narrowed in Step 4)
- ML=1, cap=2 (reopened in Step 2b)
- No SpeedRead, full P1, daily flatten 16:00, cost_ticks=1

> **⚠️ AddDist ≠ StepDist. AddDist = ADD trigger. StepDist = REVERSAL and CAP-WALK triggers. For adaptive: both read from rolling zigzag at each cycle entry.**

### Report Per Config
- Cycles, clean %, gross PF, net PF @1t, net PnL
- Mean MAE, P75 MAE, max single-cycle loss
- Daily mean PnL, daily std dev, session win%
- Cycles/hour
- **EV components:** P_clean, P_1add_recover, P_capwalk, P_deep_loss + mean PnL per category
- **Adaptive also:** effective StepDist range (min/max/mean), AddDist range, regime shift visible?

### Present As
- Heatmap: Fixed SD (rows) × AD (cols) → net PF
- Heatmap: Fixed SD × AD → EV per cycle
- Table: Adaptive configs ranked alongside top fixed configs

**Key comparison:** Adaptive wins by >3% NPF OR >4 pt adaptation range → adaptive is the foundation. Otherwise prefer fixed (simpler).

---

## Step 2b: ML and Position Cap Re-Evaluation

> **⚠️ Run ONLY on top 2-3 winners from Step 2. NOT a full grid.**

- ML: 1, 2. Cap: 2, 3. → 4 combos × 2-3 configs = 8-12 sims.
- All other settings from Step 2 winner.

**Why reopened:** ML and cap were tested with AddDist=StepDist=25. With decoupled AddDist (~15), adds fire at better prices. ML=2 at entry-15 gives avg entry ≈ entry-10 vs entry-17 at AddDist=25. Cap=3/AD=15: cap-walk probability = 0.29³ = 2.4% vs cap=2/AD=15: 0.29² = 8.4%.

Report same metrics as Step 2, plus: max position, mean position at exit, total dollar risk at worst point.

**Kill condition:** ML=2 or cap=3 must improve EV by >10% over ML=1/cap=2. Otherwise keep simpler.

---

> **📌 MID-DOCUMENT REMINDER:**
> - Step 2 found best StepDist/AddDist (fixed or adaptive)
> - Step 2b found best ML/cap on those winners
> - Step 3 next: optimize SeedDist
> - Step 4: session window
> - Step 5: freeze base config
> - NO SpeedRead, NO features — Phase 2 handles those

---

## Step 3: SeedDist Optimization

Using top 2-3 configs from Steps 2 + 2b.

**Fixed SeedDist:** 10, 12, 15, 18, 20, SD (= StepDist)
**Sigma-band:** mean + Nσ of rolling zigzag (200-swing, ALL RTH). N = 0.5, 0.75, 1.0, 1.25, 1.5. Floor 10 pts.

Report same metrics as Step 2, plus seed accuracy (% of seeds where first rotation completes profitably).

> **⚠️ SeedDist determines DIRECTION DETECTION only. It does NOT affect adds, reversals, or cap-walks. A smaller SeedDist means faster direction detection but potentially more false signals.**

---

## Step 4: Session Window Optimization

Using best full config from Steps 2-3.

Test: **09:30-11:30** vs **09:30-13:30** vs **09:30-16:00**

Report: NPF, PnL, **PnL per clock-hour** (primary efficiency metric), worst day, cycles/hr, daily std dev.

**Key insight:** Open = 15.7 cycles/hr, Morning = 10.0, Midday = 6.7, Afternoon = 4.6. The first 2 hours have 3.6x the throughput of the last 2.5 hours. A window producing +400 ticks in 2 hours (200/hr) beats +500 in 6.5 hours (77/hr) — less risk exposure, more return per unit time.

**Session window end = flatten trigger.** Position open at 11:30 → flatten at market, full reset.

---

> **📌 LATE-DOCUMENT REMINDER:**
> - Phase 1 = base economics ONLY. No filters.
> - Steps: 1 (sim mod) → 1b (zigzag gate) → 2 (SD×AD fixed+adaptive) → 2b (ML/cap) → 3 (SeedDist) → 4 (session window) → 5 (freeze)
> - The base config MUST show positive EV unfiltered.
> - P2 untouched. cost_ticks=1. All data filtered to P1 dates.

---

## Step 5: Summary and Freeze Base Config

Present the best config with all metrics. Compare against SD=25/AD=25 baseline.

**Save:**
- `full_p1_base_cycles.parquet` with fields: entry_time, exit_time, direction, gross_pnl, net_pnl, adds, cap_walks, mfe, mae, cycle_duration, block, stepdist_used, adddist_used, seeddist_used, ml_used, cap_used
- `phase1_base_config.json` with every parameter specified
- State clearly: fixed or adaptive? What values? What ML/cap?

**This config must show positive EV unfiltered. If it doesn't, no amount of filtering will save it.**

---

## Pipeline Rules (Absolute)

> **⚠️ REMINDER: AddDist ≠ StepDist throughout. Three triggers: AddDist (add), StepDist (reversal), StepDist (cap-walk). All data filtered to P1 dates. No SpeedRead, no features. cost_ticks=1.**

1. **Full P1** for all work. Sep 21 – Dec 14.
2. **RTH only.** 09:30-16:00 (or narrower window from Step 4).
3. **P2 UNTOUCHED.**
4. **cost_ticks = 1.**
5. **No SpeedRead, no feature filters.** Pure base economics.
6. **AddDist ≠ StepDist.** Three separate triggers.
7. **Simulator verified before sweeps.** SD=25/AD=25 must match baseline.
8. **Zigzag sensitivity must pass before adaptive configs run.**
9. **All data filtered to P1 dates.** CSV extends into P2.
10. **Simpler wins ties.** Fixed beats adaptive at <3% improvement. ML=1/cap=2 beats higher at <10%.

---

## ⚠️ Common Mistakes — Self-Check

**Step 1:**
- [ ] Simulator accepts separate AddDist parameter
- [ ] Three triggers implemented: AddDist (add), StepDist (reversal), StepDist (cap-walk)
- [ ] Cap-walk uses StepDist, NOT AddDist
- [ ] Session window flatten works (position open at window end → flatten)
- [ ] ML=2 add quantity logic correct (1st add=1, 2nd add=2 if cap allows)
- [ ] Baseline verification: SD=25/AD=25/ML=1/cap=2 matches known V1.1

**Step 1b:**
- [ ] Three reversal settings tested: 4.0, 5.25, 7.0
- [ ] RTH only, P1 dates only
- [ ] P85/P90 shift computed — pass if ≤15%

**Step 2:**
- [ ] 30 fixed + 9 adaptive = ~39 configs
- [ ] AddDist ≥ 10 floor enforced
- [ ] AddDist ≤ StepDist enforced
- [ ] SeedDist = StepDist (coupled in this step)
- [ ] Session window = 09:30-16:00 (not narrowed yet)
- [ ] ML=1, cap=2 (not reopened yet)
- [ ] EV components reported (P_clean, P_1add, P_capwalk, P_deep)
- [ ] Adaptive range (min/max/mean) reported
- [ ] cost_ticks = 1
- [ ] Data filtered to P1 dates

**Step 2b:**
- [ ] Only top 2-3 winners from Step 2
- [ ] ML: 1, 2. Cap: 2, 3. 8-12 sims total.
- [ ] Kill condition: >10% EV improvement required

**Step 3:**
- [ ] Uses top configs from Steps 2 + 2b
- [ ] Both fixed SeedDist and sigma-band tested
- [ ] Sigma-band floor = 10 pts
- [ ] Seed accuracy reported

**Step 4:**
- [ ] Three windows tested: 11:30, 13:30, 16:00
- [ ] PnL per clock-hour is primary metric, not total PnL
- [ ] Session window end = flatten trigger

**Step 5:**
- [ ] Complete cycle dataset saved with ALL fields including ml_used, cap_used
- [ ] Config JSON has every parameter — no TBD
- [ ] Fixed vs adaptive verdict stated explicitly
- [ ] Positive EV confirmed unfiltered
- [ ] P2 not touched
