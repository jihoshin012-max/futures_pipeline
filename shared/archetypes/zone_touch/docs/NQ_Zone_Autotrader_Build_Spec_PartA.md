# NQ Zone Touch — Autotrader Build Spec: Part A (Build)

> **Version:** 2.0
> **Date:** 2026-03-22
> **Scope:** C++ autotrader implementation — scoring, features, exits, logic flow, position tracking, logging
> **Prerequisite:** Pipeline Prompts 0-4 complete. Exit sweep complete. Pre-deployment diagnostics complete.
> **Next:** Part B (Replication Gate), then Part C (Paper Trading Protocol)
> **AUTHORITATIVE** — supersedes `deployment_spec_clean.json` for exit parameters only. Scoring model, features, and segmentation unchanged from pipeline.

---

## Build Paths

**Primary build location (ACSIL project):**
`C:\Projects\sierrachart\`

This is where all Sierra Chart ACSIL studies live (ZigZagRegime, SpeedRead V2 Roll50, ATEAM_ROTATION_V14, SupplyDemandZonesV4, etc.). The new autotrader study is built here, compiled here, and runs from here.

**Pipeline copy (version tracking):**
`C:\Projects\pipeline\shared\archetypes\zone_touch\acsil\`

After build + replication gate pass, copy the final `.cpp` file(s) to the pipeline repo. This ensures the pipeline has a versioned record of the deployed code alongside the Python simulation it was verified against.

**Files to create:**

| File | Location | Purpose |
|------|----------|---------|
| `ATEAM_ZONE_BOUNCE_V1.cpp` | `C:\Projects\sierrachart\` | Primary ACSIL autotrader study |
| `zone_bounce_config.h` | `C:\Projects\sierrachart\` | Config struct — hardcoded P1-frozen thresholds, bin edges, exits, with CONFIG_VERSION tag |
| `ATEAM_ZONE_BOUNCE_V1.cpp` | `C:\Projects\pipeline\...\acsil\` | Copy for version tracking |
| `zone_bounce_config.h` | `C:\Projects\pipeline\...\acsil\` | Copy for version tracking |

⚠️ The primary build is always in `C:\Projects\sierrachart\`. The pipeline copy is a snapshot — never edit the pipeline copy directly. Edit in sierrachart, recompile, verify, then copy.

**Naming convention:** `ATEAM_ZONE_BOUNCE_V1` — consistent with existing `ATEAM_ROTATION_V14`. Version tag in filename for clear identification on chart.

⚠️ **FRESH BUILD — do not copy or modify M1A_AutoTrader or M1B_AutoTrader.** The prior autotraders used a completely different architecture (14 features, equal weights, 4 modes, 3-leg exits, TF-specific width gates). Copying that code carries over logic branches and assumptions that don't apply. Build `ATEAM_ZONE_BOUNCE_V1` from scratch. The ONLY thing to reference from M1B is the V4 data interface pattern — how to read zone touch events from the V4 study in ACSIL. That's plumbing, not trading logic.

---

## Strategy Summary

**What it trades:** NQ E-mini futures zone touches — supply/demand zones identified by Sierra Chart's SupplyDemandZonesV4 study.

**Edge mechanism:** Fresh zones (F21 Zone Age) with low prior penetration (F10), held cascade state (F04), from favorable timeframes (F01), tested under counter-trend pressure — bounce reliably.

**Holdout result:** PF 5.10 @3t, 58 P2 trades, 91.4% WR, Profit/DD 16.51, MaxDD 193t, SBB leak 0.0%.

**Instrument:** NQ E-mini. Tick size = 0.25 pts. Tick value = $5.00/tick/contract. Bar type = 250-volume bars.

**Cost model:** 3 ticks per TRADE ENTRY (not per contract, not per leg). For a 3-contract 2-leg trade, the total cost is 3t × $5.00 = $15.00. This matches the Python simulation which applied 3t to the weighted PnL of each trade. The cost is deducted once from the combined weighted PnL, not separately per leg.

---

## Scoring Model (P1-frozen — do not modify)

**Approach:** A-Cal (calibrated weights proportional to R/P spread)

⚠️ All bin edges, weights, and thresholds are P1-frozen. Hardcode in `zone_bounce_config.h` with a version tag (e.g., `CONFIG_VERSION = "P1_2026-03-22"`). Do not load from JSON at runtime — ACSIL JSON parsing adds unnecessary complexity and file-path dependencies. The header file IS the config file. Verify the hardcoded values match `scoring_model_acal.json` and `feature_config.json` exactly during the replication gate (Part B).

**Features (4, all STRUCTURAL):**

| Feature | Description | Weight Source |
|---------|------------|-------------|
| F10 Prior Penetration | Raw ticks price penetrated zone on prior touch (NOT a ratio) | R/P spread 0.977 |
| F04 CascadeState | Was prior zone at this price level held or broke? | R/P spread 0.580 |
| F01 Timeframe | Zone timeframe (30m best, 480m+ worst) | R/P spread 0.336 |
| F21 Zone Age | Bars since zone creation (SBB-MASKED) | NORMAL-only R/P spread 0.432 |

**Threshold:** 16.66 / 23.80 (70% of max score)

**Bin edges and weight table:** Hardcode in `zone_bounce_config.h` from `scoring_model_acal.json` and `feature_config.json`

### Feature Computation Details (for C++ implementation)

⚠️ Each feature must be computed identically to the Python pipeline. Any deviation invalidates the scoring model. Part B (Replication Gate) verifies this on specific sample touches.

**F10 Prior Penetration:**
- Definition: On the PRIOR touch of this zone (seq-1), how far did price penetrate past the zone edge?
- Compute: Raw PenetrationTicks from the prior touch on the same zone. NOT divided by zone width — the raw tick value is used directly.
- Units: Ticks (e.g., 405 = price penetrated 405 ticks past zone edge on prior touch)
- Bin edges: [220, 590] — these are raw tick values, confirming the raw-ticks interpretation
- Null handling: Value = 0 if seq = 1 (no prior touch exists — assign to lowest bin)
- Source: V4 study tracks per-zone touch history. `PenetrationTicks` from the prior SignalRecord.

**F04 CascadeState:**
- Definition: Did a prior zone at approximately this price level hold or break?
- Values: NO_PRIOR (no prior zone existed here), PRIOR_HELD (prior zone held), PRIOR_BROKE (prior zone broke)
- Source: V4 study's cascade tracking. `CascadeState` column.

⚠️ Reminder: all features must match Python exactly. Bin edge boundary handling (< vs ≤) is a common C++ divergence point.

**F01 Timeframe:**
- Definition: The timeframe of the zone (which chart created it)
- Values: 15m, 30m, 60m, 90m, 120m (only these pass the TF filter)
- Source: `SourceLabel` column from V4 study

**F21 Zone Age:**
- Definition: Number of 250-volume bars since zone was created
- Compute: Current bar index minus zone birth bar index
- Source: `ZoneAgeBars` column, or computed from zone birth timestamp vs current bar
- Note: SBB-MASKED feature — scoring model handles via bin weights

**Scoring computation:**
1. For each feature, look up which P1-frozen bin the raw value falls into (bin edges in `feature_config.json`)
2. Assign points per bin (weights in `scoring_model_acal.json`)
3. Sum all 4 feature points = A-Cal score
4. Compare to threshold (16.66)

### Edge Touch Definition

- V4 study detects when price reaches a zone's edge (demand bottom or supply top)
- `TouchType` = DEMAND_EDGE or SUPPLY_EDGE only — internal touches are ignored
- In Sierra Chart: maps to V4 study's alert/subgraph that fires on edge touch at bar close

⚠️ Reminder: the autotrader only trades EDGE touches. A zone touch that doesn't reach the edge is not a signal.

### V4 Study Interaction (ACSIL architecture)

**How the autotrader reads zone data from V4:**

The autotrader needs these fields from V4 on each zone touch event:
- TouchType (DEMAND_EDGE / SUPPLY_EDGE)
- TouchSequence (seq number for this zone)
- ZoneWidthTicks
- CascadeState (NO_PRIOR / PRIOR_HELD / PRIOR_BROKE)
- ZoneAgeBars (or zone birth bar index)
- Penetration (from prior touch, for F10)
- SourceLabel (zone TF: 15m, 30m, etc.)

⚠️ **GSD task:** Examine the existing V4 study and ZB4 alignment study in `C:\Projects\sierrachart\` to determine which subgraph indices or persistent data structures expose these fields. The M1B_AutoTrader already reads from V4 — reference its ACSIL code for the V4 data interface pattern ONLY (how to access subgraphs and persistent data). Do NOT copy M1B's trading logic, scoring, or mode routing.

### Multi-Timeframe Zone Access

Zones come from 5 timeframes (15m, 30m, 60m, 90m, 120m). In the current Sierra Chart setup, these are detected by V4 study instances. The autotrader needs to receive zone touch events from ALL 5 timeframes.

⚠️ **GSD task:** Check the existing chart configuration:
- Are there separate V4 studies per TF, or one V4 that tracks all TFs?
- Does the existing M1B_AutoTrader already handle multi-TF zones? If yes, reference the same chart setup and V4 data access pattern (not M1B's trading logic).
- The `SourceLabel` field identifies which TF produced the zone — the autotrader uses this for the TF filter (reject 240m+).

---

## Segmentation (P1-frozen — do not modify)

**Winning segmentation:** Seg3 (Score + Trend Context)

**Mode routing:**

| Mode | Rule | Purpose |
|------|------|---------|
| **CT mode (ModeB)** | Score ≥ threshold AND edge touch AND counter-trend (CT) | Highest conviction |
| **WT/NT mode (ModeA)** | Score ≥ threshold AND edge touch AND (WT or NT) AND seq ≤ 5 | Lower conviction, more volume |

**Trend label computation:**
- TrendSlope = pre-computed by ZBV4 study in Sierra Chart (NOT linear regression from bar data — different scale)
- P1-frozen cutoffs: P33 = -0.3076, P67 = +0.3403
- **Non-direction-aware:** slope ≤ P33 → CT, slope ≥ P67 → WT, otherwise → NT. Same classification regardless of demand/supply direction.
- The C++ autotrader reads TrendSlope from the SignalRecord (`sig.TrendSlope`), does NOT compute it.

⚠️ **ERRATUM:** Earlier versions of this spec said "direction-aware" (demand CT = falling, supply CT = rising). The actual pipeline uses non-direction-aware classification — slope ≤ P33 is always CT regardless of touch type. The replication harness confirmed this on 79/79 matched trades.

---

## Exit Parameters (from exit sweep — supersedes pipeline)

⚠️ Pipeline validated with single-leg exits. Post-pipeline exit sweep found 2-leg exits outperform. These are the authoritative exits.

### CT Mode Exits

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| **Legs** | 2 | Lock profit at safe floor, let runner capture upside |
| **T1** | 40t (67% of position) | 95% of P2 trades reached 40t MFE |
| **T2** | 80t (33% of position) | 88% of P2 trades reached 80t |
| **Stop** | 190t | Wide catastrophe backstop — 2.4% RTH stop rate |
| **BE/Trail** | None | Step-up testing showed no improvement |
| **Time cap** | 160 bars | Wider than pipeline's 120 |

### WT/NT Mode Exits

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| **Legs** | 2 | Same architecture as CT |
| **T1** | 60t (67% of position) | 90%+ fill rate |
| **T2** | 80t (33% of position) | Runner target |
| **Stop** | 240t | Wider — sweep found 240t outperforms 190t for this mode |
| **BE/Trail** | None | No improvement found |
| **Time cap** | 160 bars | Same as CT |

⚠️ Reminder: these exit params are from the exit sweep, not the original pipeline. The replication gate (Part B) verifies against sweep results.

---

## Core Logic Flow

```
1. Zone touch detected (V4 study fires on DEMAND_EDGE or SUPPLY_EDGE)
2. Touch bar closes
3. Determine direction: DEMAND_EDGE → LONG, SUPPLY_EDGE → SHORT
4. Compute 4 features (F10, F04, F01, F21) using P1-frozen bin edges
5. Compute A-Cal score (weighted sum of bin points)
6. If score < 16.66: SKIP (log reason=BELOW_THRESHOLD)
7. Check TF filter (must be ≤ 120m): if fails, SKIP (reason=TF_FILTER)
8. Read TrendSlope from SignalRecord (pre-computed by ZBV4, NOT from bar regression)
9. Assign trend label (slope ≤ P33 → CT, slope ≥ P67 → WT, else NT — non-direction-aware)
10. Route to mode:
    - CT → 2-leg T1=40t(67%), T2=80t(33%), Stop=190t, TC=160
    - WT/NT + seq ≤ 5 → 2-leg T1=60t(67%), T2=80t(33%), Stop=240t, TC=160
    - WT/NT + seq > 5 → SKIP (reason=SEQ_FILTER)
11. Check no-overlap (not in ANY position, either mode): if in trade, SKIP
    (reason=IN_POSITION or CROSS_MODE_OVERLAP)
12. Enter at next bar open (3 contracts: 2ct leg 1, 1ct leg 2)
13. Manage exit per mode (2-leg partial exits, stop-first on intra-bar conflict)
14. 16:55 ET: flatten any open position (exit_type=FLATTEN_EOD)
```

⚠️ Stop-first rule: if both stop and target are hit on the same bar, stop fills first (worst-case assumption). This matches the Python simulation.

---

## Multi-Leg Position Tracking

The autotrader must track:
- Position size per leg (67% = 2ct, 33% = 1ct at 3ct base)
- Separate target prices per leg
- Shared stop price (all legs exit at same stop)
- Time cap applies to ALL remaining legs
- When T1 fills: reduce position to 1ct, continue holding for T2
- Exit types per leg: TARGET_1, TARGET_2, STOP, TIMECAP, FLATTEN_EOD

### Position Sizing in Contracts

| Base Size | Leg 1 (67%) | Leg 2 (33%) | Notes |
|-----------|-------------|-------------|-------|
| 3 contracts | 2ct | 1ct | Minimum viable for 2-leg |
| 6 contracts | 4ct | 2ct | Better granularity |
| 1 contract | 1ct | — | Fallback: single-leg with T1 only (40t CT / 60t WT/NT). Log as SINGLE_CT_FALLBACK. |

Paper trading: use 3 contracts.

⚠️ Reminder: all exit parameters are P1-frozen. No recalibration during paper trading.

### 16:55 ET Flatten Rule

- At 16:55 ET, flatten all open positions at market
- Exit type = FLATTEN_EOD (distinct from TIMECAP)
- Overrides time cap: if TC=160 would expire at 17:30 but 16:55 arrives first, flatten at 16:55
- Log separately — do not mix with time cap statistics

### Cross-Mode Overlap Rule

- No simultaneous positions. If a CT trade is open, WT/NT signal is SKIPPED (and vice versa).
- Log skipped cross-mode signals with reason = CROSS_MODE_OVERLAP in signal_log.csv

### SBB Handling

- No explicit SBB filter needed. Scoring model achieves 0.0% SBB leak on deployed groups.
- **SBB detection:** A touch is SBB (same-bar-break) if the zone broke on the same bar it was touched. Check if V4 exposes an `SBB_Label` field on the touch event, or check if the zone's death bar = touch bar. Reference the `SBB_Label` column in the scored touches CSV for the Python definition.
- Log SBB_label (NORMAL/SBB) on every touch for monitoring. If SBB touches start scoring above threshold during paper trading, flag for investigation.

---

## Kill-Switch

⚠️ All exit parameters and scoring thresholds are P1-frozen. The kill-switch is the only adaptive element.

- **3 consecutive losses:** Halt trading for remainder of session. A "loss" = weighted_pnl < 0 for the trade (the combined weighted PnL after 3t cost is negative). A trade where T1 hits target but T2 stops out is a loss if the net is negative.
- **Daily loss limit:** -400t ($2,000) — halt for day
- **Weekly loss limit:** -800t ($4,000) — halt for week, manual review required

---

## Data Logging (build from day one)

⚠️ Build all logging into the autotrader during construction. Retrofitting after paper trading begins means lost data.

### trade_log.csv (per trade — MOST IMPORTANT FOR REPLICATION)

Every completed trade writes one row. This is the primary replication verification file.

| Column | Type | Description |
|--------|------|------------|
| trade_id | string | Unique ID |
| mode | string | CT or WTNT |
| datetime | timestamp | Touch bar close time |
| direction | string | LONG or SHORT |
| touch_type | string | DEMAND_EDGE or SUPPLY_EDGE |
| source_label | string | Zone timeframe (15m, 30m, etc.) |
| touch_sequence | int | Seq number of this touch on this zone |
| F10_raw | float | Prior penetration raw ticks (NOT a ratio) |
| F04_raw | string | NO_PRIOR / PRIOR_HELD / PRIOR_BROKE |
| F01_raw | string | Timeframe label |
| F21_raw | float | Zone age in bars |
| F10_bin | int | Which bin (0, 1, 2) |
| F04_bin | int | Which bin |
| F01_bin | int | Which bin |
| F21_bin | int | Which bin |
| F10_points | float | Points assigned |
| F04_points | float | Points assigned |
| F01_points | float | Points assigned |
| F21_points | float | Points assigned |
| acal_score | float | Total A-Cal score |
| score_margin | float | score - threshold |
| trend_slope | float | Raw TrendSlope value |
| trend_label | string | CT / WT / NT |
| sbb_label | string | NORMAL / SBB |
| session | string | RTH / ETH |

⚠️ Columns above are scoring/classification fields. Columns below are trade execution fields. Both sets are needed for replication (Part B).

| entry_bar_index | int | Bar index of entry |
| entry_price | float | Entry price (next bar open) |
| stop_price | float | Computed stop price |
| t1_target_price | float | Leg 1 target price |
| t2_target_price | float | Leg 2 target price |
| leg1_exit_type | string | TARGET_1 / STOP / TIMECAP / FLATTEN_EOD |
| leg1_exit_price | float | Exit price for leg 1 |
| leg1_exit_bar | int | Bar index of leg 1 exit |
| leg1_pnl_ticks | float | RAW PnL ticks for leg 1 (before cost). E.g., if T1=40t hit, leg1_pnl = +40. |
| leg2_exit_type | string | TARGET_2 / STOP / TIMECAP / FLATTEN_EOD |
| leg2_exit_price | float | Exit price for leg 2 |
| leg2_exit_bar | int | Bar index of leg 2 exit |
| leg2_pnl_ticks | float | RAW PnL ticks for leg 2 (before cost). E.g., if T2=80t hit, leg2_pnl = +80. |
| weighted_pnl | float | (0.67 × leg1_pnl + 0.33 × leg2_pnl) - 3t. Cost deducted ONCE from the weighted total, not per leg. |
| bars_held | int | Bars from entry to final exit |
| mfe_ticks | float | Max favorable excursion from entry |
| mae_ticks | float | Max adverse excursion from entry |
| slippage_ticks | float | Actual fill - simulated entry (live only, 0 in replay) |
| latency_ms | int | Signal to fill latency (live only, 0 in replay) |

⚠️ The per-feature bin and points columns are critical for replication. If C++ assigns F10 to bin 2 but Python assigned bin 1, the replication gate catches it at the column level without debugging the scoring logic.

### signal_log.csv (per signal — including skipped)

Every zone touch that reaches step 3 (feature computation) writes one row, whether traded or skipped.

| Column | Type | Description |
|--------|------|------------|
| datetime | timestamp | Touch bar close time |
| touch_type | string | DEMAND_EDGE / SUPPLY_EDGE |
| source_label | string | Zone TF |
| acal_score | float | Score (even if below threshold) |
| score_margin | float | score - threshold (negative if rejected) |
| trend_label | string | CT / WT / NT |
| sbb_label | string | NORMAL / SBB |
| action | string | TRADE / SKIP |
| skip_reason | string | BELOW_THRESHOLD / TF_FILTER / SEQ_FILTER / IN_POSITION / CROSS_MODE_OVERLAP / null |
| current_position_pnl | float | If skipped due to IN_POSITION, unrealized PnL of current trade |

### Additional logs (lower priority but build from day one)

| Log | Frequency | Key fields |
|-----|-----------|-----------|
| `microstructure_log.csv` | Per zone touch (all, not just trades) | Bid/ask spread, volume, delta, book depth |
| `speedread_log.csv` | Per zone touch | SpeedRead Roll50 value (requires SC export fix) |
| `zone_stability_log.csv` | Daily | Zones created, died, active count, recompilation flag, feed gaps |
| `macro_calendar.csv` | Per trade | News day flag, event name, minutes to event |

⚠️ Reminder: trade_log.csv and signal_log.csv are the critical files for replication (Part B) and weekly review (Part C). The additional logs are for future autoresearch — build them now, analyze later.

---

## Configuration Source Files (for verifying hardcoded values)

| File | Contains | Verify against |
|------|----------|---------------|
| `scoring_model_acal.json` | Weights per bin, threshold | `zone_bounce_config.h` weight arrays and THRESHOLD constant |
| `feature_config.json` | Bin edges, TrendSlope P33/P67 | `zone_bounce_config.h` bin edge arrays and P33/P67 constants |

⚠️ These JSON files are the source of truth. The hardcoded values in `zone_bounce_config.h` must match exactly. Part B replication gate Phase 1 verifies this by checking individual scores.

---

## Output Files Summary

| File | Created by |
|------|-----------|
| `trade_log.csv` | Autotrader (per trade) |
| `signal_log.csv` | Autotrader (per signal) |
| `microstructure_log.csv` | Autotrader (per touch) |
| `speedread_log.csv` | Autotrader (per touch) |
| `zone_stability_log.csv` | Autotrader (daily) |
| `macro_calendar.csv` | Pre-populated + autotrader annotates per trade |
| `weekly_summary.md` | Manual or script, every Friday |

---

## Part A Self-Check

✅ **Before moving to Part B (Replication Gate):**
- [ ] Scoring model hardcoded in `zone_bounce_config.h` — verified against `scoring_model_acal.json`
- [ ] Feature bin edges hardcoded in `zone_bounce_config.h` — verified against `feature_config.json`
- [ ] TrendSlope P33/P67 hardcoded in `zone_bounce_config.h` — verified against `feature_config.json`
- [ ] F10 computation matches spec (raw PenetrationTicks from prior touch, NOT divided by zone width, 0 for seq=1)
- [ ] F04 values match spec (NO_PRIOR / PRIOR_HELD / PRIOR_BROKE)
- [ ] F01 values match spec (SourceLabel)
- [ ] F21 computation matches spec (bar count since zone birth)
- [ ] Edge touch detection: DEMAND_EDGE and SUPPLY_EDGE only
- [ ] V4 study data interface working (all 7 fields readable: TouchType, TouchSequence, ZoneWidthTicks, CascadeState, ZoneAgeBars, Penetration, SourceLabel)
- [ ] Multi-TF zones accessible (touches from 15m, 30m, 60m, 90m, 120m all reach the autotrader)
- [ ] Direction mapping: DEMAND_EDGE → LONG, SUPPLY_EDGE → SHORT
- [ ] 2-leg exit logic implemented (67/33 split, separate targets per leg)
- [ ] CT mode exits: T1=40t, T2=80t, Stop=190t, TC=160
- [ ] WT/NT mode exits: T1=60t, T2=80t, Stop=240t, TC=160
- [ ] Trend label: non-direction-aware (slope ≤ P33 → CT, ≥ P67 → WT, else NT). Reads from SignalRecord, not computed from bars.
- [ ] No-overlap rule enforced across BOTH modes
- [ ] TF filter: ≤ 120m only
- [ ] Seq gate: none for CT, ≤ 5 for WT/NT
- [ ] 16:55 ET flatten implemented (exit_type=FLATTEN_EOD)
- [ ] Position sizing: 3ct minimum (2+1). 1ct fallback to single-leg.
- [ ] Stop-first intra-bar conflict rule
- [ ] Cost model: 3t per trade entry (not per contract, not per leg) — matches Python simulation
- [ ] Kill-switch: 3 consecutive losses, -400t daily, -800t weekly
- [ ] trade_log.csv includes ALL columns (per-feature raw, bin, points, per-leg exits, MFE/MAE, slippage, latency)
- [ ] signal_log.csv includes ALL signals (traded + skipped with reason)
- [ ] SBB_label logged on every touch
- [ ] Cross-mode overlap skips logged
- [ ] Session (RTH/ETH) logged on every trade
- [ ] Additional logs configured (microstructure, speedread, zone stability, macro)
- [ ] Study compiles in `C:\Projects\sierrachart\` and loads on Sierra Chart
- [ ] Pipeline copy made to `C:\Projects\pipeline\shared\archetypes\zone_touch\acsil\`
