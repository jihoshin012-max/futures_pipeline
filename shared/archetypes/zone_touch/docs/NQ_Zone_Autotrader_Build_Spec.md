# NQ Zone Touch — Autotrader Build Specification

> **Version:** 1.0
> **Date:** 2026-03-22
> **Status:** AUTHORITATIVE — supersedes deployment sections of `deployment_spec_clean.json`, `verdict_narrative.md`, and `combined_recommendation_clean.md` for exit parameters only. Scoring model, features, and segmentation are unchanged from pipeline.
> **Source:** Pipeline Prompts 0-4 (edge validation) + post-pipeline exit sweep + pre-deployment diagnostics

---

## What This Document Is

The pipeline (Prompts 0-4) validated the zone touch strategy's edge: scoring model, features, segmentation, and holdout results. After the pipeline completed, three additional analyses refined the deployment configuration:

1. **Pre-deployment diagnostics** (Items 1-5) — loser profiles, threshold sensitivity, session distribution, loss sequences
2. **Expanded exit sweep** (Phases 1-2) — found 2-leg exits outperform single-leg
3. **Score-to-move correlation** — confirmed score is a gate, not a magnitude predictor
4. **RTH vs ETH analysis** — found all stop-outs concentrate in ETH

This document consolidates everything into one autotrader build spec.

---

## Strategy Summary

**What it trades:** NQ E-mini futures zone touches — supply/demand zones identified by Sierra Chart's SupplyDemandZonesV4 study.

**Edge mechanism:** Fresh zones (F21 Zone Age) with low prior penetration (F10), held cascade state (F04), from favorable timeframes (F01), tested under counter-trend pressure — these bounce reliably.

**Holdout result:** PF 5.10 @3t on 58 combined P2 trades, 91.4% win rate, Profit/DD 16.51, max DD 193t, SBB leak 0.0%.

---

## Scoring Model (unchanged from pipeline)

⚠️ This section is identical to the pipeline output. Do not modify.

**Approach:** A-Cal (calibrated weights proportional to R/P spread)

**Features (4, all STRUCTURAL):**

| Feature | Description | Weight Source |
|---------|------------|-------------|
| F10 Prior Penetration | Raw ticks price penetrated zone on prior touch (NOT a ratio) | R/P spread 0.977 |
| F04 CascadeState | Was prior zone at this price held or broke? | R/P spread 0.580 |
| F01 Timeframe | Zone timeframe (30m best, 480m+ worst) | R/P spread 0.336 |
| F21 Zone Age | Bars since zone creation (SBB-MASKED) | NORMAL-only R/P spread 0.432 |

**Threshold:** 16.66 / 23.80 (70% of max score)

**Bin edges and weight table:** See `scoring_model_acal.json` (frozen from P1)

### Feature Computation Details (for C++ implementation)

⚠️ Each feature must be computed identically to the Python pipeline. Any deviation invalidates the scoring model.

**F10 Prior Penetration:**
- Definition: On the PRIOR touch of this zone (seq-1), how far did price penetrate past the zone edge?
- Compute: Raw PenetrationTicks from the prior touch on the same zone. NOT divided by zone width. Value = 0 if seq = 1 (no prior touch — assign to lowest bin).
- Units: Ratio (0.0 = no penetration, 1.0 = penetrated full zone width, >1.0 = penetrated beyond zone)
- Source: V4 study tracks per-zone touch history. `Penetration` and `ZoneWidthTicks` columns.

**F04 CascadeState:**
- Definition: Did a prior zone at approximately this price level hold or break?
- Values: NO_PRIOR (no prior zone existed here), PRIOR_HELD (prior zone at this level was touched and held), PRIOR_BROKE (prior zone at this level broke)
- Source: V4 study's cascade tracking. `CascadeState` column.

**F01 Timeframe:**
- Definition: The timeframe of the zone (which chart created it)
- Values: 15m, 30m, 60m, 90m, 120m (only these pass the TF filter)
- Source: `SourceLabel` column from V4 study

**F21 Zone Age:**
- Definition: Number of 250-volume bars since zone was created
- Compute: Current bar index minus zone birth bar index
- Source: `ZoneAgeBars` column, or computed from zone birth timestamp vs current bar
- Note: SBB-MASKED feature — its signal was hidden by SBB noise on the full population but STRONG on NORMAL-only. The scoring model handles this via bin weights.

⚠️ All 4 features above must produce identical values to the Python pipeline. The replication gate (Phase 1) verifies this on 20 sample touches before paper trading begins.

**Scoring computation:**
1. For each feature, look up which P1-frozen bin the raw value falls into (bin edges in `feature_config.json`)
2. Assign points per bin (weights in `scoring_model_acal.json`)
3. Sum all 4 feature points = A-Cal score
4. Compare to threshold (16.66)

### Edge Touch Definition

**What triggers a zone touch signal:**
- The V4 study detects when price reaches a zone's edge (demand bottom or supply top)
- `TouchType` = DEMAND_EDGE (price reached bottom of demand zone) or SUPPLY_EDGE (price reached top of supply zone)
- The autotrader only trades EDGE touches — internal zone touches (DEMAND_INTERNAL, SUPPLY_INTERNAL) are ignored
- In Sierra Chart: this maps to the V4 study's alert/subgraph that fires when an edge touch occurs on a bar close

---

## Segmentation (unchanged from pipeline)

⚠️ This section is identical to the pipeline output. Do not modify.

**Winning segmentation:** Seg3 (Score + Trend Context)

**Mode routing:**

| Mode | Rule | Purpose |
|------|------|---------|
| **CT mode (ModeB)** | Score ≥ threshold AND edge touch AND counter-trend (CT) | Highest conviction — zones under pressure that hold |
| **WT/NT mode (ModeA)** | Score ≥ threshold AND edge touch AND with-trend or neutral | Lower conviction — zones aligned with or neutral to trend |

**Global filters:**
- TF filter: SourceLabel ∈ {15m, 30m, 60m, 90m, 120m} — exclude 240m+
- CT mode: No seq gate
- WT/NT mode: Seq ≤ 5

**Trend label computation:** TrendSlope pre-computed by ZBV4 study (NOT linear regression from bar data). P1-frozen cutoffs: P33 = -0.3076, P67 = +0.3403. Non-direction-aware: slope ≤ P33 → CT, slope ≥ P67 → WT, otherwise → NT. Same classification regardless of demand/supply direction.

---

## Exit Parameters (UPDATED from exit sweep — supersedes pipeline)

⚠️ **This section supersedes `deployment_spec_clean.json`.** The pipeline validated with single-leg exits. The post-pipeline exit sweep found 2-leg exits outperform.

### CT Mode Exits

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| **Legs** | 2 | Lock profit at safe floor, let runner capture upside |
| **T1** | 40t (67% of position) | 95% of P2 trades reached 40t MFE — near-certain floor |
| **T2** | 80t (33% of position) | 88% of P2 trades reached 80t — strong runner target |
| **Stop** | 190t | Wide catastrophe backstop — 2.4% stop rate on P2 RTH |
| **BE/Trail** | None | Step-up testing showed no improvement (93% T2 fill rate) |
| **Time cap** | 160 bars | Wider than pipeline's 120 — captures more time cap winners |

**P1 performance:** PF 264, MaxDD 7t, net profit 1,901t (40 trades)
**Expected P2 performance:** Lower than P1 (in-sample calibration). P2 single-leg was PF 5.10 — 2-leg should be in the same range with better risk profile.

### WT/NT Mode Exits

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| **Legs** | 2 | Same architecture as CT |
| **T1** | 60t (67% of position) | Conservative first target — 90%+ fill rate |
| **T2** | 80t (33% of position) | Runner target |
| **Stop** | 240t | Wider than CT — sweep found 240t outperforms 190t for All mode |
| **BE/Trail** | None | No improvement found in Phase 2 |
| **Time cap** | 160 bars | Same as CT |

**P1 performance:** PF 11.74, MaxDD 243t, P/DD 28.61, net profit 6,953t (129 trades)

---

## ETH Variant (parallel paper trading)

⚠️ **Do not filter ETH in the primary deployment.** Paper trade both variants simultaneously to collect data.

**Finding:** All 3 P2 stop-outs occurred during ETH. PF 1.76 (ETH) vs 13.51 (RTH) despite identical scores (mean 18.27 ETH vs 17.94 RTH). The scoring model cannot distinguish ETH weakness — the zones score identically but behave differently overnight.

**Implementation:** The autotrader takes all trades (RTH + ETH). Log a `session` field (RTH/ETH) on every trade. After 3 months, analyze:
- Did ETH stop-outs continue to dominate?
- What is the RTH-only PF?
- How many trades per month does the ETH filter cost?

If confirmed, adding a session filter is a one-line change.

---

## Pre-Deployment Diagnostics Summary

### Threshold Sensitivity (Item 3)

| Threshold | Trades | PF @3t | Win Rate |
|-----------|--------|--------|----------|
| 16.66 (baseline) | 58 | 5.10 | 91.4% |
| 15.66 (-1pt) | 77 | 2.76 | 85.7% |
| 14.66 (-2pt) | 121 | 1.92 | 79.3% |

**Verdict: SLOPE, not cliff.** The strategy degrades gracefully. Small scoring noise won't destroy the edge. Safety margin exists.

### Loser Profile (Item 2)

7 non-target exits out of 58 trades (4 stops, 3 time caps):
- **Score margin:** 5/7 losers within 2 points of threshold. 3/4 stop-outs at margin < 1 point.
- **Cascade state:** 6/7 losers are PRIOR_HELD (middle bin, not best NO_PRIOR).
- **Session:** All 3 stops are ETH. Time caps split across sessions.
- **MFE:** Mean 43.9t — none reached the 80t target. Max MFE of losers = 63t.

**Key takeaway:** Low score margin + PRIOR_HELD + ETH = the losing trade profile. The barely-qualifying trades are the ones that fail.

⚠️ Reminder: These diagnostic findings are informational — they do NOT change the deployment config. The autotrader uses P1-frozen parameters. Diagnostics inform what to monitor during paper trading.

### Score-to-Move Correlation

**Verdict: SCORE PREDICTS DIRECTION ONLY (Spearman rho = -0.05)**

MFE is flat across score bins (~85-89t). Higher scores improve PF through win rate (88% → 100%) and lower MAE (65t → 56t), not bigger moves. Single target is correct — no score-dependent exit logic needed.

### Consecutive Loss Sequences (Item 5)

- **Max consecutive losses:** 1 (P2 combined, P2a, P2b all = 1)
- **Max single loss:** 193t ($965/ct)
- **Max DD = max single loss** — drawdown IS the single worst trade, no compounding
- **Recovery:** 222 bars (~5 calendar days)
- **Kill-switch recommendation:** 3 consecutive losses (never triggered on P2, 2-loss buffer)

### Time-of-Day Distribution (Item 4)

| Session | Trades | PF @3t |
|---------|--------|--------|
| RTH Morning (9-12) | 11 | inf |
| RTH Afternoon (12-16) | 31 | 11.01 |
| RTH Close (16-18) | 6 | 1.99 |
| ETH/Overnight | 10 | 1.60 |

Peak hour: 14:00 (13 trades, 22% of total). 53% of trades are RTH afternoon.

⚠️ Reminder: All diagnostics above are from P2 holdout data. The autotrader implements the configuration that produced these results. Any modification invalidates the holdout.

---

## Exit Sweep Conclusions

### What was tested:
- Phase 1: Single-leg, 2-leg, 3-leg with size splits across stops, targets, time caps (~3,100 combos)
- Phase 2: Graduated stop step-up on Phase 1 top 3 (~800 combos)
- Phase 3: Skipped — 91-93% target fill rates mean trail has nothing to improve

### What was found:
1. **2-leg outperforms single-leg** for both modes — locks majority at safe floor, runner captures upside
2. **Step-ups don't help** — losses are fast failures (MFE < 40t then hard reversal), not slow bleeds. Step-up triggers above T1 never fire on losing trades.
3. **Trail skipped** — same reasoning as step-up. 91-93% of trades reach target before any trail would activate.
4. **Wider stops and time caps help All mode** — Stop 240t and TC 160 outperform 190t/120
5. **CT mode 40t floor:** 95% of P2 trades reached 40t MFE. 100% on P1. T1=40t is near-certain.

⚠️ Reminder: The 2-leg exit structure came from the exit sweep (post-pipeline). The replication gate Phase 3 must verify the C++ autotrader reproduces the 2-leg sweep results, not the original single-leg pipeline results.

---

## Autotrader Build Requirements

### Core Logic Flow

```
1. Zone touch detected (V4 study fires on DEMAND_EDGE or SUPPLY_EDGE)
2. Touch bar closes
3. Compute 4 features (F10, F04, F01, F21) using P1-frozen bin edges
4. Compute A-Cal score (weighted sum of bin points)
5. If score < 16.66: SKIP (log to signal_log with reason=BELOW_THRESHOLD)
6. Check TF filter (must be ≤ 120m): if fails, SKIP (reason=TF_FILTER)
7. Read TrendSlope from SignalRecord (pre-computed by ZBV4)
8. Assign trend label (slope ≤ P33 → CT, slope ≥ P67 → WT, else NT — non-direction-aware)
9. Route to mode:
   - CT → 2-leg T1=40t(67%), T2=80t(33%), Stop=190t, TC=160
   - WT/NT + seq ≤ 5 → 2-leg T1=60t(67%), T2=80t(33%), Stop=240t, TC=160
   - WT/NT + seq > 5 → SKIP (reason=SEQ_FILTER)
10. Check no-overlap (not already in ANY position, either mode): if in trade, SKIP (reason=IN_POSITION or CROSS_MODE_OVERLAP)
11. Enter at next bar open (3 contracts: 2ct leg 1, 1ct leg 2)
12. Manage exit per mode (2-leg partial exits, stop-first on intra-bar conflict)
13. 16:55 ET: flatten any open position (exit_type=FLATTEN_EOD, overrides time cap)
```

### Multi-Leg Position Tracking

The autotrader must track:
- Position size per leg (67% leg 1, 33% leg 2)
- Separate target prices per leg
- Shared stop price (all legs exit at same stop)
- Time cap applies to ALL remaining legs
- When T1 fills: reduce position to 33%, continue holding for T2
- Exit types per leg: TARGET_1, TARGET_2, STOP, TIMECAP

### Position Sizing in Contracts

The 67/33 split requires minimum 3 contracts per trade:
- **3 contracts:** Leg 1 = 2ct (67%), Leg 2 = 1ct (33%). Minimum viable.
- **6 contracts:** Leg 1 = 4ct (67%), Leg 2 = 2ct (33%). Better granularity.
- **1 contract:** Cannot split — fall back to single-leg with T1 target only (40t for CT, 60t for WT/NT). Log as "SINGLE_CT_FALLBACK" for tracking.

Paper trading should use 3 contracts to validate the 2-leg mechanics.

### 16:55 ET Flatten Rule

⚠️ **Required for live trading.** The Python simulation deferred this (DateTime not always available in bar data). The C++ autotrader has real-time timestamps.

- At 16:55 ET, flatten all open positions at market
- Exit type = FLATTEN_EOD (distinct from TIMECAP)
- Log separately — do not mix with time cap statistics
- This overrides the time cap: if TC=160 would expire at 17:30 but 16:55 arrives first, flatten at 16:55

### Cross-Mode Overlap Rule

- **No simultaneous positions.** If a CT trade is open, a WT/NT signal is SKIPPED (and vice versa).
- The no-overlap rule applies across modes, not just within a mode.
- Log skipped cross-mode signals with reason = CROSS_MODE_OVERLAP in `signal_log.csv`
- This matches the Python simulation which processed touches sequentially with a single `in_trade_until` gate.

### SBB Handling

- **No explicit SBB filter needed.** The scoring model achieves 0.0% SBB leak rate on the deployed groups — the feature combination (especially F21 Zone Age) naturally excludes SBB touches.
- The autotrader does NOT need to detect or filter SBB touches.
- Log `SBB_label` (NORMAL/SBB) on every touch in `signal_log.csv` for monitoring. If SBB leak appears during paper trading (SBB touches scoring above threshold), flag for investigation.

### Kill-Switch

⚠️ Reminder: All exit parameters, scoring thresholds, and filters are P1-frozen. The autotrader applies them — no recalibration during paper trading.

- **3 consecutive losses:** Halt trading for remainder of session
- **Daily loss limit:** -400t ($2,000) — halt for day
- **Weekly loss limit:** -800t ($4,000) — halt for week, manual review required

### Data Logging (Items 6-12 from Data Capture Spec)

Build these into the autotrader from day one:

| Log | Per-trade fields | Purpose |
|-----|-----------------|---------|
| `trade_log.csv` | All 4 features, score, margin, entry/exit prices, slippage, latency, exit_type per leg, PnL per leg, MFE, MAE, bars held, session (RTH/ETH) | Primary analysis |
| `signal_log.csv` | Score, trend label, skip reason (IN_POSITION/BELOW_THRESHOLD/TF_FILTER/SEQ_FILTER), current position PnL if skipped | Skip rate analysis |
| `microstructure_log.csv` | Bid/ask spread, volume, delta, book depth at touch time (all touches, not just trades) | Future entry optimization |
| `speedread_log.csv` | SpeedRead Roll50 value at touch (requires Sierra Chart export fix) | Future feature screening |
| `zone_stability_log.csv` | Daily: zones created, died, active count, any recompilation, data feed gaps | Study health monitoring |
| `macro_calendar.csv` | News day flag, event name, minutes to event | News filter investigation |

### Weekly Summary

Generate `weekly_summary.md` every Friday:
- Trades taken / signals fired / skip rate
- PF @3t (week), PF @3t (cumulative)
- Mean slippage, max slippage
- Mean latency
- RTH vs ETH breakdown
- Any kill-switch activations
- Zone stability anomalies

---

## Replication Gate (MANDATORY before paper trading)

⚠️ **The C++ autotrader must reproduce the Python pipeline's signals and trades before going live.** Any discrepancy means either the C++ implementation or the Python pipeline has a bug. Do not paper trade until this gate passes.

### Phase 1: Signal Replication (score matching)

Pick 20 sample touches from P1 scored data (`p1_scored_touches_acal.csv`), stratified:
- 5 high-score (margin > 3)
- 5 near-threshold (margin 0-1)
- 5 below-threshold (rejects)
- 5 SBB touches

For each sample, run the C++ autotrader's scoring logic on the same bar and confirm:

| Field | Python Value | C++ Value | Match? |
|-------|-------------|-----------|--------|
| F10 raw value | ? | ? | ✓/✗ |
| F10 bin assignment | ? | ? | ✓/✗ |
| F10 points | ? | ? | ✓/✗ |
| F04 raw value | ? | ? | ✓/✗ |
| F04 bin assignment | ? | ? | ✓/✗ |
| F04 points | ? | ? | ✓/✗ |
| F01 raw value | ? | ? | ✓/✗ |
| F01 bin assignment | ? | ? | ✓/✗ |
| F01 points | ? | ? | ✓/✗ |
| F21 raw value | ? | ? | ✓/✗ |
| F21 bin assignment | ? | ? | ✓/✗ |
| F21 points | ? | ? | ✓/✗ |
| A-Cal total score | ? | ? | ✓/✗ |
| Pass/fail threshold | ? | ? | ✓/✗ |
| TrendSlope value | ? | ? | ✓/✗ |
| Trend label (CT/WT/NT) | ? | ? | ✓/✗ |

**Pass criteria:** All 20 samples match on total score (within ±0.01 for floating point) and pass/fail decision. All trend labels match.

**If mismatch:** Identify which feature diverges. Most likely causes: bin edge boundary handling (< vs ≤), TrendSlope computation (different regression window or method), or F10 null handling (seq=1 touches).

### Phase 2: Trade Replication (entry + exit matching)

Using P1 bar data and scored touches, replay 10 specific trades that the Python pipeline took:
- 5 from CT mode (seg3 ModeB)
- 5 from All mode (seg1 ModeA)

Include at least 1 stop-out, 1 time-cap exit, and 1 target hit.

For each trade, confirm:

| Field | Python Value | C++ Value | Match? |
|-------|-------------|-----------|--------|
| Touch bar index | ? | ? | ✓/✗ |
| Entry bar (touch + 1) | ? | ? | ✓/✗ |
| Entry price (bar open) | ? | ? | ✓/✗ |
| Direction (long/short) | ? | ? | ✓/✗ |
| Stop price | ? | ? | ✓/✗ |
| T1 target price | ? | ? | ✓/✗ |
| T2 target price | ? | ? | ✓/✗ |
| Exit bar | ? | ? | ✓/✗ |
| Exit type (per leg) | ? | ? | ✓/✗ |
| PnL (per leg) | ? | ? | ✓/✗ |
| Bars held | ? | ? | ✓/✗ |

**Pass criteria:** All 10 trades match on entry price, exit type, and PnL (within ±1 tick for floating point rounding). No trade taken by Python but missed by C++, or vice versa.

**If mismatch:** Most likely causes: intra-bar stop-first rule (C++ checking target before stop), time cap counting (off-by-one on bar count), no-overlap gate (different `in_trade_until` logic), or 16:55 flatten firing on a trade Python didn't flatten.

⚠️ The 2-leg exits are NEW (exit sweep found them post-pipeline). Python's Phase 1 sweep script (`exit_sweep_phase1.py`) is the authoritative reference for 2-leg simulation logic, not the original single-leg `zone_touch_simulator.py`.

⚠️ Reminder: Replication gate must PASS before paper trading. Do not skip phases. A C++ autotrader that produces different signals than the Python pipeline is trading an unvalidated strategy.

### Phase 3: Full Period Replay (aggregate matching)

Run the C++ autotrader on the full P1 bar data with all scoring/filtering/exits active. Compare aggregate stats:

| Metric | Python | C++ | Tolerance |
|--------|--------|-----|-----------|
| CT mode total trades | ~40 | ? | Exact match |
| All mode total trades | ~134 | ? | Exact match |
| CT mode PF @3t | 264.35 (2-leg) | ? | Within ±5% |
| All mode PF @3t | 11.74 (2-leg) | ? | Within ±5% |
| Total signals fired | ? | ? | Exact match |
| Total signals skipped (in-position) | ? | ? | Exact match |

**Pass criteria:** Trade count exact match. PF within ±5% (floating point and bar-boundary timing can cause small differences). Signal count exact match.

⚠️ Reminder: The P1 reference numbers for 2-leg configs are: CT mode PF=264.35 (40 trades), All mode PF=11.74 (129 trades). These are from `exit_sweep_phase1_results.md`.

**If aggregate matches but individual trades differ:** Likely a bar-alignment issue. The C++ autotrader processes bars in real-time; the Python pipeline processes from CSV. Confirm the CSV bar timestamps match what Sierra Chart produces live.

### Replication Gate Verdict

- **PASS:** All 3 phases pass → proceed to paper trading
- **PARTIAL PASS:** Phase 1 and 2 pass, Phase 3 has minor PF deviation (within ±10%) but trade count matches → investigate, likely acceptable
- **FAIL:** Any phase fails → fix before paper trading. Do not proceed.

Save replication results to `replication_gate_results.md`.

---

## Paper Trading Protocol (P3: Mar–Jun 2026)

### Duration: 3 months minimum (60+ RTH trading days)

### Expected trade volume:
- CT mode: ~0.4 trades/RTH day (~24 trades in 60 days)
- WT/NT mode: ~0.35 trades/RTH day (~21 additional)
- Combined: ~0.75 trades/RTH day (~45 total)

### Success criteria after paper trading:

| Metric | Minimum for live deployment | Stretch goal |
|--------|---------------------------|-------------|
| Combined PF @3t | > 1.5 | > 2.5 |
| Win rate | > 70% | > 85% |
| Max consecutive losses | ≤ 5 | ≤ 3 |
| Max DD | < 600t | < 300t |
| Slippage | < 3t mean | < 1t mean |
| ETH analysis | Conclusive (confirm or reject filter) | — |

### Variants to track:
- **Variant A (full):** All touches, RTH + ETH
- **Variant B (RTH only):** Session filter applied — no ETH trades

Both use identical scoring, features, and exits. Compare weekly.

---

## Queued Post-Paper-Trading Work

### Autoresearch (10 items):
1. Bin granularity (tercile vs quintile)
2. Interaction terms (F10×F04, etc.)
3. Feature transforms (log/sqrt on F21)
4. Categorical remapping (non-tercile TF scoring)
5. Volatility-adjusted exits (ATR multiples)
6. Screening rejects as filters (F22 Break Rate gate)
7. Conditional SBB scoring
8. Entry variations (limit inside zone, volume confirmation, retest)
9. SpeedRead as feature (speed regime distinct from ATR)
10. ETH filter (pending paper trading data)

### Zone break strategy:
Inverted feature polarity. SBB touches (1,411) + bounce near-miss touches (269 within 2pts below threshold) as candidate populations. Same Prompt 0-4 structure. Queue after bounce autotrader is paper trading.

---

## File References

### Pipeline outputs (DO NOT MODIFY — historical record):

| File | Prompt | Purpose |
|------|--------|---------|
| `baseline_report_clean.md` | 0 | Raw edge baseline |
| `feature_screening_clean.md` | 1a | Feature classifications |
| `feature_mechanism_validation.md` | 1a | Mechanism validation |
| `incremental_build_clean.md` | 1b | Elbow model, winning features |
| `scoring_model_acal.json` | 1b | A-Cal weights + threshold |
| `feature_config.json` | 1b | Bin edges, TrendSlope cutoffs |
| `segmentation_params_clean.json` | 2 | All 15 run parameters |
| `frozen_parameters_manifest_clean.json` | 2 | Complete parameter dump |
| `feature_analysis_clean.md` | 2 | Ablation, SBB, B-only verdict |
| `verdict_report_clean.md` | 3 | Verdict matrix |
| `verdict_narrative.md` | 3 | Standalone narrative |
| `deployment_spec_clean.json` | 3 | Original deployment spec (SUPERSEDED for exits by this document) |
| `cross_reference_report_clean.md` | 4 | Gap investigation |

### Post-pipeline outputs:

| File | Source | Purpose |
|------|--------|---------|
| `p2_trade_details.csv` | Item 1 | Per-trade features + MFE/MAE |
| `p2_trade_diagnostics.md` | Items 2,4,5 | Loser profiles, time-of-day, loss sequences |
| `threshold_sensitivity.md` | Item 3 | Near-miss analysis |
| `exit_sweep_phase1_results.md` | Exit sweep | Phase 1 top 10 per population |
| `exit_sweep_phase1_configs.json` | Exit sweep | Machine-readable top 3 configs |
| `NQ_Zone_Expanded_Exit_Sweep_Spec.md` | This session | Full sweep specification |
| `NQ_Zone_Data_Capture_Spec.md` | This session | Data capture requirements |
| **This document** | This session | Authoritative build spec |
| `replication_gate_results.md` | Replication gate | C++ vs Python match verification (created during build) |

---

## Self-Check

✅ **Before starting autotrader build, confirm:**
- [ ] Scoring model loaded from `scoring_model_acal.json` (P1-frozen)
- [ ] Feature bin edges loaded from `feature_config.json` (P1-frozen)
- [ ] TrendSlope P33/P67 loaded from `feature_config.json` (P1-frozen)
- [ ] F10 computation matches Python (raw PenetrationTicks from prior touch, NOT ratio, 0 for seq=1)
- [ ] F04 values match Python (NO_PRIOR / PRIOR_HELD / PRIOR_BROKE from V4 cascade)
- [ ] F01 values match Python (SourceLabel from V4 study)
- [ ] F21 computation matches Python (bar count since zone birth)
- [ ] Edge touch detection: only DEMAND_EDGE and SUPPLY_EDGE, not internal touches
- [ ] 2-leg exit logic implemented (67/33 split, separate targets per leg)
- [ ] CT mode exits: T1=40t, T2=80t, Stop=190t, TC=160
- [ ] WT/NT mode exits: T1=60t, T2=80t, Stop=240t, TC=160
- [ ] Trend label: non-direction-aware (slope ≤ P33 → CT, ≥ P67 → WT). Reads from SignalRecord.
- [ ] No-overlap rule enforced across BOTH modes (skip if any position open)
- [ ] TF filter: ≤ 120m only
- [ ] Seq gate: none for CT, ≤ 5 for WT/NT
- [ ] 16:55 ET flatten implemented (overrides time cap, logged as FLATTEN_EOD)
- [ ] Position sizing: minimum 3 contracts for 2-leg split (2+1). 1ct fallback to single-leg.
- [ ] Kill-switch: 3 consecutive losses, -400t daily, -800t weekly
- [ ] All 6 log files configured (trade, signal, microstructure, speedread, zone stability, macro)
- [ ] SBB_label logged on every touch (monitoring, not filtering)
- [ ] Cross-mode overlap skips logged with reason
- [ ] Weekly summary template created
- [ ] RTH/ETH session field logged on every trade
- [ ] SpeedRead export added to Sierra Chart (or flagged as TODO)
- [ ] Macro calendar pre-populated for Mar-Jun 2026

✅ **Replication gate (MANDATORY before paper trading):**
- [ ] Phase 1: 20 sample touches — scores match within ±0.01, all pass/fail decisions match
- [ ] Phase 2: 10 sample trades — entry price, exit type, PnL match within ±1 tick
- [ ] Phase 3: Full P1 replay — trade count exact match, PF within ±5%
- [ ] Replication results saved to `replication_gate_results.md`
- [ ] Verdict: PASS / PARTIAL PASS / FAIL
