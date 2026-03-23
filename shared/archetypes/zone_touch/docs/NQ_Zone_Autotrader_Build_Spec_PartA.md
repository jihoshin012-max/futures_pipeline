# NQ Zone Touch — Autotrader Build Spec: Part A (Build)

> **Version:** 3.0
> **Date:** 2026-03-23
> **Scope:** C++ autotrader implementation — scoring, features, exits, logic flow, position tracking, logging
> **Prerequisite:** Pipeline Prompts 0-4 complete. Exit sweep complete. Exit investigation complete. P1 validation of zone-relative framework PASSED.
> **Next:** Part B (Replication Gate — must re-run with zone-relative exits), then Part C (Paper Trading Protocol)
> **AUTHORITATIVE** — supersedes ALL prior exit specs. Scoring model, features, and segmentation unchanged from pipeline.
> **Change from v2.0:** Zone-relative exit framework replaces fixed exits. CT 5t limit entry added. See Exit Investigation Report for full evidence.

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

**Edge mechanism:** Fresh zones (F21 Zone Age) with low prior penetration (F10), held cascade state (F04), from favorable timeframes (F01), tested under counter-trend pressure — bounce reliably. Zone width determines the natural scale of the bounce — exits scale to the zone structure.

**Validation results:**
- P2 zone-relative (exclusive routing): PF 33.35, 69 trades (41 CT + 28 WT), 94.2% WR
- P1 zone-relative: PF 7.25, ~121 trades, 83.6% WR (lower due to 42.6% narrow zone composition vs P2's 11.9%)
- CT 5t limit: 41 CT fills on P2 (91.1% fill rate), 4 LIMIT_EXPIRED. Zero real CT losses across P1+P2.
- ⚠️ NOTE: Earlier exit investigation reported "312 trades, PF 28.69" — those were 312 ROWS across 4 segmentation groups, not 312 unique trades. The 69-trade count reflects exclusive CT/WT routing as the autotrader actually operates.

**Instrument:** NQ E-mini. Tick size = 0.25 pts. Tick value = $5.00/tick/contract. Bar type = 250-volume bars.

**Cost model:** 3 ticks per TRADE ENTRY (not per contract, not per leg). For a 3-contract 2-leg trade, the total cost is 3t × $5.00 = $15.00. This matches the Python simulation which applied 3t to the weighted PnL of each trade. The cost is deducted once from the combined weighted PnL, not separately per leg.

---

## Scoring Model (P1-frozen — do not modify)

**Approach:** A-Cal (calibrated weights proportional to R/P spread)

⚠️ All bin edges, weights, and thresholds are P1-frozen. Hardcode in `zone_bounce_config.h` with a version tag (e.g., `CONFIG_VERSION = "P1_2026-03-23_v3"`). Do not load from JSON at runtime — ACSIL JSON parsing adds unnecessary complexity and file-path dependencies. The header file IS the config file. Verify the hardcoded values match `scoring_model_acal.json` and `feature_config.json` exactly during the replication gate (Part B).

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
- ZoneTop, ZoneBot (zone boundaries — needed for zone-relative exit computation)

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

## Exit Parameters (Zone-Relative Framework)

⚠️ **v3.0 CHANGE:** Zone-relative exits replace the fixed exits from v2.0. Targets and stops scale with zone width. This is validated on both P1 (PF 7.25, WR 83.6%) and P2 (PF 33.35, WR 94.2%, 69 exclusively-routed trades). See `exit_investigation_report.md` for full evidence.

⚠️ **Why zone-relative:** The fixed 40-80t targets captured only ~20% of the available bounce in wide zones (200t+). Zone-relative exits scale to the structure — a 200t zone gets a 200t T2 target, a 50t zone gets a 50t T2 target. This produced 2.5x EV improvement over fixed exits on P2.

### Zone Width Computation

- `zone_width_ticks = (ZoneTop - ZoneBot) / tick_size` where tick_size = 0.25
- Example: ZoneTop = 24850.00, ZoneBot = 24800.00 → zone_width_ticks = 200
- All exit levels are computed from zone_width_ticks at entry time and DO NOT change during the trade

### Exit Parameters (both modes use same framework)

| Parameter | Formula | Example (200t zone) | Example (80t zone) |
|-----------|---------|--------------------|--------------------|
| **T1 (67%)** | 0.5 × zone_width_ticks | 100t | 40t |
| **T2 (33%)** | 1.0 × zone_width_ticks | 200t | 80t |
| **Stop** | max(1.5 × zone_width_ticks, 120) | 300t | 120t (floor) |
| **Time cap** | 160 bars | 160 bars | 160 bars |

⚠️ **Stop floor:** The stop is `max(1.5 × zone_width, 120t)`. The 120t floor protects narrow zones (< 80t wide) where 1.5x would be too tight. On P1, the floor improved 50-100t zone WR from 80.6% to 85.7%.

### CT Mode Entry

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| **Entry type** | Limit order, 5t inside zone edge | 237 CT trades across P1+P2, zero real losses |
| **Entry price** | DEMAND: ZoneTop - (5 × tick_size). SUPPLY: ZoneBot + (5 × tick_size) | 5t confirms price commitment to zone |
| **Fill window** | 20 bars after touch bar close | Captures ~85% of fills |
| **If not filled** | Cancel limit, log as LIMIT_EXPIRED in signal_log | Skip — do not convert to market |

⚠️ The 5t limit eliminates all edge-skimmer losses (price barely nicks zone and reverses). P1: 50/50 CT 100% WR. P2: 186/187 CT 100% WR (one unfilled). The 0.5% miss rate is negligible.

### WT/NT Mode Entry

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| **Entry type** | Market at next bar open | WT 5t limit did not eliminate losses on P1 (different failure mode) |
| **Entry price** | Open of bar following touch bar close | Same as v2.0 |

⚠️ Reminder: the zone-relative EXIT multipliers (0.5x, 1.0x, 1.5x, 120t floor) are the same for BOTH modes. Only the ENTRY method differs (CT: 5t limit, WT: market).

### Exit Computation Example

DEMAND_EDGE touch, ZoneTop = 24850.00, ZoneBot = 24800.00:
- zone_width_ticks = (24850.00 - 24800.00) / 0.25 = 200
- Direction: LONG
- CT 5t limit entry price: 24850.00 - (5 × 0.25) = 24848.75
- T1 target: 24848.75 + (100 × 0.25) = 24873.75 (0.5 × 200 = 100t from entry)
- T2 target: 24848.75 + (200 × 0.25) = 24898.75 (1.0 × 200 = 200t from entry)
- Stop: 24848.75 - (300 × 0.25) = 24773.75 (max(1.5 × 200, 120) = 300t from entry)

SUPPLY_EDGE touch, ZoneTop = 25100.00, ZoneBot = 25080.00:
- zone_width_ticks = (25100.00 - 25080.00) / 0.25 = 80
- Direction: SHORT
- WT market entry price: Open of next bar (e.g., 25080.50)
- T1 target: 25080.50 - (40 × 0.25) = 25070.50 (0.5 × 80 = 40t from entry)
- T2 target: 25080.50 - (80 × 0.25) = 25060.50 (1.0 × 80 = 80t from entry)
- Stop: 25080.50 + (120 × 0.25) = 25110.50 (max(1.5 × 80 = 120, 120) = 120t from entry — floor applied)

⚠️ **Targets and stops are measured from ENTRY PRICE, not from zone edge.** For CT 5t limit, the entry is 5t inside the zone, so all levels shift 5t relative to the edge. For WT market, entry is approximately at the edge.

---

## Core Logic Flow

```
1. Zone touch detected (V4 study fires on DEMAND_EDGE or SUPPLY_EDGE)
2. Touch bar closes
3. Determine direction: DEMAND_EDGE → LONG, SUPPLY_EDGE → SHORT
4. Read ZoneTop, ZoneBot from SignalRecord
5. Compute zone_width_ticks = (ZoneTop - ZoneBot) / tick_size
6. Compute 4 features (F10, F04, F01, F21) using P1-frozen bin edges
7. Compute A-Cal score (weighted sum of bin points)
8. If score < 16.66: SKIP (log reason=BELOW_THRESHOLD)
9. Check TF filter (must be ≤ 120m): if fails, SKIP (reason=TF_FILTER)
10. Read TrendSlope from SignalRecord (pre-computed by ZBV4, NOT from bar regression)
11. Assign trend label (slope ≤ P33 → CT, slope ≥ P67 → WT, else NT — non-direction-aware)
12. Route to mode:
    - CT → compute zone-relative exits, place 5t LIMIT ORDER inside zone edge
      Fill window = 20 bars. If unfilled after 20 bars: cancel, log LIMIT_EXPIRED.
    - WT/NT + seq ≤ 5 → compute zone-relative exits, MARKET entry at next bar open
    - WT/NT + seq > 5 → SKIP (reason=SEQ_FILTER)
13. Compute exit levels from entry price:
    - T1 = entry ± (0.5 × zone_width_ticks × tick_size)
    - T2 = entry ± (1.0 × zone_width_ticks × tick_size)
    - Stop = entry ∓ (max(1.5 × zone_width_ticks, 120) × tick_size)
    (± for LONG targets, ∓ for LONG stop; reverse for SHORT)
14. Check no-overlap (not in ANY position, either mode): if in trade, SKIP
    (reason=IN_POSITION or CROSS_MODE_OVERLAP)
15. Enter position (3 contracts: 2ct leg 1, 1ct leg 2)
16. Manage exit (2-leg partial exits, stop-first on intra-bar conflict)
17. 16:55 ET: flatten any open position (exit_type=FLATTEN_EOD)
```

⚠️ Stop-first rule: if both stop and target are hit on the same bar, stop fills first (worst-case assumption). This matches the Python simulation.

⚠️ **CT limit order management:** The limit order is placed on the bar AFTER the touch bar closes (same timing as the old market order). It sits for up to 20 bars. During these 20 bars, the no-overlap rule still applies — if a WT/NT signal fires while the CT limit is pending, the WT/NT is SKIPPED (reason=LIMIT_PENDING). The CT limit has priority.

---

## Multi-Leg Position Tracking

The autotrader must track:
- Position size per leg (67% = 2ct, 33% = 1ct at 3ct base)
- Separate target prices per leg (T1 = 0.5x zw, T2 = 1.0x zw from entry)
- Shared stop price (all legs exit at same stop = max(1.5x zw, 120t) from entry)
- Time cap applies to ALL remaining legs (160 bars from entry)
- When T1 fills: reduce position to 1ct, continue holding for T2
- Exit types per leg: TARGET_1, TARGET_2, STOP, TIMECAP, FLATTEN_EOD, LIMIT_EXPIRED

### Position Sizing in Contracts

| Base Size | Leg 1 (67%) | Leg 2 (33%) | Notes |
|-----------|-------------|-------------|-------|
| 3 contracts | 2ct | 1ct | Minimum viable for 2-leg |
| 6 contracts | 4ct | 2ct | Better granularity |
| 1 contract | 1ct | — | Fallback: single-leg with T1 only (0.5x zw). Log as SINGLE_LEG_FALLBACK. |

Paper trading: use 3 contracts.

⚠️ Reminder: all exit MULTIPLIERS are frozen. Zone width varies per trade but the multipliers (0.5x, 1.0x, 1.5x, 120t floor) do not change.

### 16:55 ET Flatten Rule

- At 16:55 ET, flatten all open positions at market
- Exit type = FLATTEN_EOD (distinct from TIMECAP)
- Overrides time cap: if TC=160 would expire at 17:30 but 16:55 arrives first, flatten at 16:55
- Also cancels any pending CT limit orders that haven't filled
- Log separately — do not mix with time cap statistics

### Cross-Mode Overlap Rule

- No simultaneous positions. If a CT trade is open, WT/NT signal is SKIPPED (and vice versa).
- If a CT LIMIT ORDER is pending (not yet filled), WT/NT signal is SKIPPED (reason=LIMIT_PENDING)
- Log skipped cross-mode signals with reason = CROSS_MODE_OVERLAP or LIMIT_PENDING in signal_log.csv

### SBB Handling

- No explicit SBB filter needed. Scoring model achieves 0.0% SBB leak on deployed groups.
- **SBB detection:** A touch is SBB (same-bar-break) if the zone broke on the same bar it was touched. Check if V4 exposes an `SBB_Label` field on the touch event, or check if the zone's death bar = touch bar. Reference the `SBB_Label` column in the scored touches CSV for the Python definition.
- Log SBB_label (NORMAL/SBB) on every touch for monitoring. If SBB touches start scoring above threshold during paper trading, flag for investigation.

---

## Kill-Switch

⚠️ All exit multipliers and scoring thresholds are P1-frozen. The kill-switch is the only adaptive element.

⚠️ **v3.0 note:** Zone-relative stops vary by zone width. Max single-trade loss depends on zone width: a 300t zone has a 450t stop (1.5x), while a 50t zone has a 120t stop (floor). Kill-switch thresholds are set for worst-case (widest zones).

- **3 consecutive losses:** Halt trading for remainder of session. A "loss" = weighted_pnl < 0 for the trade (the combined weighted PnL after 3t cost is negative). A trade where T1 hits target but T2 stops out is a loss if the net is negative.
- **Daily loss limit:** -600t ($3,000) — halt for day. Increased from v2.0's -400t to accommodate wider zone-relative stops on wide zones.
- **Weekly loss limit:** -1200t ($6,000) — halt for week, manual review required. Increased from v2.0's -800t.

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
| zone_top | float | Zone upper boundary |
| zone_bot | float | Zone lower boundary |
| zone_width_ticks | int | (ZoneTop - ZoneBot) / tick_size |
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

| entry_type | string | LIMIT_5T (CT) or MARKET (WT/NT) |
| limit_depth_ticks | int | 5 for CT, 0 for WT/NT |
| entry_bar_index | int | Bar index of entry (fill bar for limit, next bar for market) |
| entry_price | float | Actual entry price |
| stop_price | float | Computed stop price = entry ∓ max(1.5 × zw, 120) × tick_size |
| stop_ticks | int | max(1.5 × zone_width_ticks, 120) |
| t1_target_price | float | Leg 1 target = entry ± 0.5 × zw × tick_size |
| t1_ticks | int | 0.5 × zone_width_ticks |
| t2_target_price | float | Leg 2 target = entry ± 1.0 × zw × tick_size |
| t2_ticks | int | 1.0 × zone_width_ticks |
| leg1_exit_type | string | TARGET_1 / STOP / TIMECAP / FLATTEN_EOD |
| leg1_exit_price | float | Exit price for leg 1 |
| leg1_exit_bar | int | Bar index of leg 1 exit |
| leg1_pnl_ticks | float | RAW PnL ticks for leg 1 (before cost) |
| leg2_exit_type | string | TARGET_2 / STOP / TIMECAP / FLATTEN_EOD |
| leg2_exit_price | float | Exit price for leg 2 |
| leg2_exit_bar | int | Bar index of leg 2 exit |
| leg2_pnl_ticks | float | RAW PnL ticks for leg 2 (before cost) |
| weighted_pnl | float | (0.67 × leg1_pnl + 0.33 × leg2_pnl) - 3t. Cost deducted ONCE from the weighted total, not per leg. |
| bars_held | int | Bars from entry to final exit |
| mfe_ticks | float | Max favorable excursion from entry |
| mae_ticks | float | Max adverse excursion from entry |
| slippage_ticks | float | Actual fill - simulated entry (live only, 0 in replay) |
| latency_ms | int | Signal to fill latency (live only, 0 in replay) |

⚠️ The per-feature bin and points columns are critical for replication. The zone_width_ticks, stop_ticks, t1_ticks, t2_ticks columns verify the zone-relative computation at the per-trade level.

### signal_log.csv (per signal — including skipped)

Every zone touch that reaches step 6 (feature computation) writes one row, whether traded or skipped.

| Column | Type | Description |
|--------|------|------------|
| datetime | timestamp | Touch bar close time |
| touch_type | string | DEMAND_EDGE / SUPPLY_EDGE |
| source_label | string | Zone TF |
| zone_width_ticks | int | Zone width in ticks |
| acal_score | float | Score (even if below threshold) |
| score_margin | float | score - threshold (negative if rejected) |
| trend_label | string | CT / WT / NT |
| sbb_label | string | NORMAL / SBB |
| action | string | TRADE / SKIP |
| skip_reason | string | BELOW_THRESHOLD / TF_FILTER / SEQ_FILTER / IN_POSITION / CROSS_MODE_OVERLAP / LIMIT_PENDING / LIMIT_EXPIRED / null |
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

⚠️ These JSON files are the source of truth for SCORING. The zone-relative exit multipliers (0.5x, 1.0x, 1.5x, 120t floor) are also hardcoded in `zone_bounce_config.h` and verified during the replication gate.

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

Scoring:
- [ ] Scoring model hardcoded in `zone_bounce_config.h` — verified against `scoring_model_acal.json`
- [ ] Feature bin edges hardcoded in `zone_bounce_config.h` — verified against `feature_config.json`
- [ ] TrendSlope P33/P67 hardcoded in `zone_bounce_config.h` — verified against `feature_config.json`
- [ ] F10 computation matches spec (raw PenetrationTicks from prior touch, NOT divided by zone width, 0 for seq=1)
- [ ] F04 values match spec (NO_PRIOR / PRIOR_HELD / PRIOR_BROKE)
- [ ] F01 values match spec (SourceLabel)
- [ ] F21 computation matches spec (bar count since zone birth)

Zone data:
- [ ] Edge touch detection: DEMAND_EDGE and SUPPLY_EDGE only
- [ ] V4 study data interface working (all fields readable: TouchType, TouchSequence, ZoneWidthTicks, CascadeState, ZoneAgeBars, Penetration, SourceLabel, ZoneTop, ZoneBot)
- [ ] Multi-TF zones accessible (touches from 15m, 30m, 60m, 90m, 120m all reach the autotrader)
- [ ] Direction mapping: DEMAND_EDGE → LONG, SUPPLY_EDGE → SHORT

Zone-relative exits:
- [ ] zone_width_ticks computed correctly: (ZoneTop - ZoneBot) / tick_size
- [ ] T1 = 0.5 × zone_width_ticks from entry price
- [ ] T2 = 1.0 × zone_width_ticks from entry price
- [ ] Stop = max(1.5 × zone_width_ticks, 120) from entry price
- [ ] Stop floor (120t) activates for zones < 80t wide
- [ ] Time cap = 160 bars from entry
- [ ] Exit levels computed once at entry and do NOT change during trade

Entry:
- [ ] CT mode: 5t limit order inside zone edge (DEMAND: ZoneTop - 5×tick, SUPPLY: ZoneBot + 5×tick)
- [ ] CT limit fill window: 20 bars, cancel if unfilled (log LIMIT_EXPIRED)
- [ ] WT/NT mode: market entry at next bar open
- [ ] Trend label: non-direction-aware (slope ≤ P33 → CT, ≥ P67 → WT, else NT). Reads from SignalRecord, not computed from bars.

Position management:
- [ ] 2-leg exit logic implemented (67/33 split, separate targets per leg)
- [ ] No-overlap rule enforced across BOTH modes
- [ ] Pending CT limit blocks WT/NT signals (LIMIT_PENDING)
- [ ] TF filter: ≤ 120m only
- [ ] Seq gate: none for CT, ≤ 5 for WT/NT
- [ ] 16:55 ET flatten implemented (exit_type=FLATTEN_EOD), cancels pending limits
- [ ] Position sizing: 3ct minimum (2+1). 1ct fallback to single-leg (0.5x zw target).
- [ ] Stop-first intra-bar conflict rule
- [ ] Cost model: 3t per trade entry (not per contract, not per leg)

Kill-switch:
- [ ] 3 consecutive losses halt session
- [ ] Daily limit: -600t
- [ ] Weekly limit: -1200t

Logging:
- [ ] trade_log.csv includes ALL columns (zone_width_ticks, stop_ticks, t1_ticks, t2_ticks, entry_type, limit_depth, per-feature raw/bin/points, per-leg exits, MFE/MAE, slippage, latency)
- [ ] signal_log.csv includes ALL signals (traded + skipped with reason, including LIMIT_EXPIRED and LIMIT_PENDING)
- [ ] SBB_label logged on every touch
- [ ] Cross-mode overlap and limit-pending skips logged
- [ ] Session (RTH/ETH) logged on every trade
- [ ] Additional logs configured (microstructure, speedread, zone stability, macro)

Build:
- [ ] Study compiles in `C:\Projects\sierrachart\` and loads on Sierra Chart
- [ ] Pipeline copy made to `C:\Projects\pipeline\shared\archetypes\zone_touch\acsil\`
