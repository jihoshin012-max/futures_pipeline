# C++ Autotrader Implementation — v3.2 Zone Touch Strategy

**Purpose:** Build the Sierra Chart ACSIL C++ autotrader study that implements 
the frozen v3.2 zone touch strategy for paper trading (P3 validation). The 
autotrader reads zone data from the ZoneTouchEngine (ZTE), scores touches using 
the frozen model parameters, manages entries/exits with the validated risk 
mitigation configuration, and enforces safety circuit breakers.

**Branch:** `main`
**Pipeline version:** 3.2 (all parameters frozen from backtesting)
**Date:** 2026-03-24
**Target:** Sierra Chart ACSIL study (.cpp), compilable as a custom study DLL

⚠️ ALL PARAMETERS ARE FROZEN from the backtesting pipeline. The C++ autotrader 
replicates the Python simulation logic exactly. Any deviation from the frozen 
config must be flagged in the replication gate (Step 2).

---

## Architecture Overview

The autotrader is a single Sierra Chart Advanced Custom Study that:

1. Reads zone touch signals from ZoneTouchEngine (ZTE) subgraphs
2. Scores each touch using the frozen A-Eq and B-ZScore models
3. Applies the priority waterfall (Mode 1 → Mode 2)
4. Manages entries, partial exits, stops, targets, time caps
5. Enforces position sizing by zone width
6. Monitors circuit breaker conditions
7. Logs all trade decisions for replication verification

```
ZTE (zones + touches)
    ↓
AutoTrader Study
    ├── Scoring (A-Eq / B-ZScore)
    ├── Waterfall (M1 priority over M2)
    ├── Entry Management (limit order with offset)
    ├── Exit Management (partials, BE, stops, TC)
    ├── Position Sizing (by zone width)
    ├── Circuit Breakers (daily loss, DD, consecutive)
    └── Logging (for replication gate)
```

---

## Study Inputs (configurable without recompile)

⚠️ All inputs should have defaults matching the frozen config. The trader can 
adjust during paper trading without recompiling.

📌 KEY PRINCIPLE: Every parameter below has a default from the backtested frozen 
config. Making them inputs allows live experimentation (e.g., EntryOffset, 
position sizing thresholds) without recompiling the DLL.

### Scoring Inputs

| Input | Type | Default | Description |
|-------|------|---------|------------|
| M1_Threshold | float | 45.5 | A-Eq score threshold for Mode 1 |
| M2_Threshold | float | 0.50 | B-ZScore threshold for Mode 2 |
| M2_MaxSeq | int | 2 | Maximum seq number for M2 trades |
| M2_MaxTF | int | 120 | Maximum timeframe in minutes for M2 |
| M2_RTHOnly | bool | true | Restrict M2 to RTH session |
| PreemptionEnabled | bool | false | If true, Mode 1 signal closes active Mode 2 position. Default false (skip mode) |

### Entry Inputs

| Input | Type | Default | Description |
|-------|------|---------|------------|
| EntryOffset | int | 0 | Ticks deeper into zone from touch edge for limit order. 0 = market order at bar Open after touch. >0 = limit order at edge + offset ticks into zone |
| EntryTimeout | int | 3 | Bars to wait for limit order fill before cancelling |

⚠️ EntryOffset = 0 replicates the backtested behavior (enter at bar Open after 
touch). Values > 0 place a limit order deeper into the zone. The limit order 
expires after EntryTimeout bars if not filled. This is for live testing of 
deeper entries without recompiling.

📌 REMINDER: The backtesting showed deeper entries reduce fill rate (68% at 10t, 
25% at 30t). The default should be 0. Only adjust during paper trading to 
evaluate fill rate in live conditions.

### Mode 1 Exit Inputs

| Input | Type | Default | Description |
|-------|------|---------|------------|
| M1_StopTicks | int | 190 | Stop distance from entry (ticks) |
| M1_T1_Ticks | int | 60 | First target distance (ticks) |
| M1_T2_Ticks | int | 120 | Second target distance (ticks) |
| M1_T1_Contracts | int | 1 | Contracts to exit at T1 |
| M1_T2_Contracts | int | 2 | Contracts to exit at T2 |
| M1_BE_After_T1 | bool | true | Move runner stop to entry after T1 hit |
| M1_TimeCap | int | 120 | Time cap in bars |
| M1_TotalContracts | int | 3 | Total contracts per M1 trade |

⚠️ The frozen config is 1+2 partial: 1ct exits at 60t (T1), remaining 2ct 
exit at 120t (T2). After T1 is hit, the stop on the remaining 2ct moves to 
breakeven (entry price). If T1 is never hit, all 3ct stop at 190t.

⚠️ The 1+1+1 config (P2 PF 8.31) is also validated. To switch: set 
M1_T1_Contracts=1, M1_T2_Contracts=1, add a third target at 180t. The study 
should support up to 3 target legs.

### Mode 2 Exit Inputs

| Input | Type | Default | Description |
|-------|------|---------|------------|
| M2_StopMultiplier | float | 1.3 | Stop = max(multiplier × ZW, floor) |
| M2_StopFloor | int | 100 | Minimum stop distance (ticks) |
| M2_TargetMultiplier | float | 1.0 | Target = multiplier × ZW |
| M2_TimeCap | int | 80 | Time cap in bars |

### Mode 2 Position Sizing Inputs

| Input | Type | Default | Description |
|-------|------|---------|------------|
| M2_Size_Narrow | int | 3 | Contracts when ZW < M2_Size_Threshold1 |
| M2_Size_Mid | int | 2 | Contracts when ZW between thresholds |
| M2_Size_Wide | int | 1 | Contracts when ZW > M2_Size_Threshold2 |
| M2_Size_Threshold1 | int | 150 | ZW boundary: narrow → mid (ticks) |
| M2_Size_Threshold2 | int | 250 | ZW boundary: mid → wide (ticks) |

📌 REMINDER: Position sizing is by zone width, not account equity. The frozen 
config: 3ct if ZW<150, 2ct if 150-250, 1ct if 250+.

### Circuit Breaker Inputs

| Input | Type | Default | Description |
|-------|------|---------|------------|
| CB_DailyLossLimit | int | 700 | Max daily loss in ticks. Disable trading for day if exceeded |
| CB_MaxConsecLosses | int | 5 | Pause after N consecutive losses. Require manual re-enable |
| CB_MaxDrawdown | int | 1541 | Max drawdown from equity peak (ticks). Hard disable |
| CB_RollingPF_Window | int | 30 | Rolling window for PF check (trades) |
| CB_RollingPF_Floor | float | 1.0 | Disable if rolling PF drops below this |
| CB_Enabled | bool | true | Master enable/disable for circuit breakers |

⚠️ CIRCUIT BREAKER BEHAVIOR:
- **Daily loss:** Resets at session open. Trading resumes next day automatically.
- **Consecutive losses:** Requires manual re-enable (set a study input to reset). 
  Does NOT reset automatically — the trader must confirm they've reviewed.
- **Max drawdown:** Requires manual re-enable. This is the "something is 
  structurally wrong" circuit breaker. Computed from equity high-water mark.
- **Rolling PF:** Requires manual re-enable. Computed over the last N completed 
  trades. Only activates after CB_RollingPF_Window trades have been completed.

📌 REMINDER: These defaults come from the stress test results:
- 700t daily loss > historical worst day (598t)
- 5 consecutive losses > historical max (4)
- 1,541t DD = HMM 95th percentile (worst across 3 MC methods)
- Rolling 30-trade PF < 1.0 has never occurred historically (min 60-trade was 1.89)

### Logging Inputs

| Input | Type | Default | Description |
|-------|------|---------|------------|
| LogEnabled | bool | true | Enable trade decision logging |
| LogPath | string | C:\Logs\ZoneTouch\ | Directory for log files |

### Session & Timing Inputs

| Input | Type | Default | Description |
|-------|------|---------|------------|
| EOD_CloseTime | time | 15:50 ET | Force close all positions at this time. Cancel pending limit orders |
| EOD_EntryBlackout | time | 15:30 ET | No new entries after this time (avoids opening trades that will be force-closed) |
| NewsBlackout_Enabled | bool | false | Skip entries within N minutes of scheduled news times |
| NewsBlackout_Minutes | int | 30 | Minutes before/after 08:30 and 14:00 to skip |

⚠️ EOD_EntryBlackout prevents entering trades that have no chance of reaching 
target before forced close. A trade entered at 15:45 with a 120-bar time cap 
would be force-closed 5 minutes later. Default blackout at 15:30 gives at least 
20 minutes of trade life before forced close.

### Visual Display Inputs

| Input | Type | Default | Description |
|-------|------|---------|------------|
| ShowEntryArrows | bool | true | Draw arrows at entry points on chart |
| ShowStopTargetLines | bool | true | Draw horizontal stop/target lines while position is open |
| ShowLabels | bool | true | Show mode (M1/M2) and score text at entry arrows |

---

## Scoring Implementation

### A-Eq Score (Mode 1)

The A-Eq model uses equal-weight scoring across 7 features. Each feature is 
binned and mapped to a weight. The total score is the sum of weights.

⚠️ LOAD FEATURE CONFIGURATION FROM: 
`c:\Projects\pipeline\shared\archetypes\zone_touch\output\feature_config_v32.json`
This file contains: feature names, bin edges, bin weights for the A-Eq model.

⚠️ FEATURE COMPUTATION: The 7 features (F10, F01, F05, F09, F21, F13, F04) are 
computed from zone and touch data available in the ZTE subgraphs. The EXISTING 
reference autotraders (ATEAM_ZONE_BOUNCE_FIXED and ATEAM_ZONE_BOUNCE_ZONEREL) 
already implement feature computation from ZTE subgraph values. READ THESE FILES 
to understand how each feature is derived from the ZTE output. If the reference 
files do not compute all 7 features, check `feature_config_v32.json` for feature 
definitions and the Python feature computation in:
`c:\Projects\pipeline\shared\archetypes\zone_touch\zone_touch_simulator.py`

The feature mapping (feature code → what it measures → ZTE subgraph source) must 
be documented in the code comments for each feature.

```
For each touch:
  score = 0
  for each feature in [F10, F01, F05, F09, F21, F13, F04]:
    value = compute_feature(touch_data)
    bin = find_bin(value, feature.bin_edges)
    score += feature.bin_weights[bin]
  
  if score >= M1_Threshold (45.5):
    → Mode 1 qualifying
```

⚠️ The features must be computed from the ZTE output. Map each feature to the 
corresponding ZTE subgraph or computed value. Document the exact mapping for 
each of the 7 features.

📌 REMINDER: Feature computation must EXACTLY match the Python pipeline. Any 
difference in binning, rounding, or feature calculation will produce different 
qualifying populations. The replication gate (Step 2) catches this.

### B-ZScore Score (Mode 2)

⚠️ CRITICAL INCONSISTENCY: The Python pipeline uses TWO DIFFERENT B-ZScore 
models for P1 and P2. For the C++ autotrader, use the JSON model (C=0.01 L1, 
global StandardScaler) since this is what will be applied to live data going 
forward.

Load from `c:\Projects\pipeline\shared\archetypes\zone_touch\output\scoring_model_bzscore_v32.json`:
- Coefficients (7 features)
- Intercept
- StandardScaler mean and std per feature

```
For each touch:
  raw_features = compute_7_features(touch_data)
  scaled = (raw_features - scaler_mean) / scaler_std
  linear_output = dot(scaled, coefficients) + intercept
  
  if linear_output >= M2_Threshold (0.50):
    → check additional filters (RTH, seq ≤ 2, TF ≤ 120m)
    → if all pass: Mode 2 qualifying
```

⚠️ Do NOT apply sigmoid. The threshold (0.50) was calibrated against the raw 
linear output, not probabilities. This matches the `ray_conditional_analysis` 
script that produced the validated P2 population of 309 trades.

---

## Waterfall Logic

```
On each new touch signal from ZTE:

  1. Check circuit breakers → if ANY triggered, skip
  
  2. Check EOD blackout → if current_time >= EOD_EntryBlackout, skip
  
  3. Compute A-Eq score
     if score >= M1_Threshold:
       → Mode 1 trade candidate
       → check if position already open
         → if open with same or higher priority: SKIP
         → if open with lower priority (Mode 2): depends on preemption setting
         → if no position: ENTER Mode 1
  
  4. If not Mode 1, compute B-ZScore
     if score >= M2_Threshold AND RTH AND seq ≤ M2_MaxSeq AND TF ≤ M2_MaxTF:
       → Mode 2 trade candidate
       → check if position already open
         → if open: SKIP (Mode 2 never preempts)
         → if no position: ENTER Mode 2
  
  5. If neither: SKIP (log as "below threshold")
```

⚠️ ONE POSITION AT A TIME. The autotrader manages a single position. If a 
position is open (any mode), new signals are skipped unless preemption applies.

⚠️ PREEMPTION: The stress test showed no persistent adverse regime and minimal 
M1/M2 correlation (0.123). Preemption adds complexity without proven benefit. 
DEFAULT: simple skip (no preemption). Add a configurable PreemptionEnabled 
input for future testing.

📌 REMINDER: Mode 1 has priority. If a touch qualifies for BOTH Mode 1 and 
Mode 2, it is a Mode 1 trade. The waterfall is sequential — check Mode 1 first.

---

## Entry Management

### Market Entry (EntryOffset = 0, default)

```
On the bar AFTER the qualifying touch:
  entry_price = bar Open
  place_order(entry_price, contracts, direction)
```

Direction:
- Demand zone touch → LONG (buy)
- Supply zone touch → SHORT (sell)

### Limit Entry (EntryOffset > 0)

```
On the bar AFTER the qualifying touch:
  if demand zone: limit_price = zone_top - EntryOffset * tick_size
  if supply zone: limit_price = zone_bottom + EntryOffset * tick_size
  
  place_limit_order(limit_price, contracts, direction)
  
  Monitor for EntryTimeout bars:
    if filled → proceed to exit management
    if not filled → cancel order, log as "limit not filled"
```

⚠️ When using EntryOffset > 0, the stop and target distances are STILL measured 
from the ACTUAL FILL PRICE (entry-relative), not from the zone edge. The 
backtesting rejected zone-fixed geometry (single-trade artifact). Entry-relative 
is the frozen architecture.

📌 REMINDER: The limit order uses the zone edge as reference. "Deeper" means 
toward the zone interior: lower for demand zones (buying lower), higher for 
supply zones (selling higher).

---

## Exit Management

### Mode 1: Partial Exits (1+2)

```
State machine for M1 exits:
  
  INITIAL STATE: 3 contracts open
    Stop = entry - M1_StopTicks (for longs) or entry + M1_StopTicks (for shorts)
    T1 = entry + M1_T1_Ticks (for longs) or entry - M1_T1_Ticks (for shorts)
    T2 = entry + M1_T2_Ticks (for longs) or entry - M1_T2_Ticks (for shorts)
    TC countdown = M1_TimeCap bars
  
  On each bar:
    Check stop → if hit: exit ALL remaining contracts at stop price
    Check T1 → if hit AND T1 not yet taken:
      Exit M1_T1_Contracts at T1 price
      if M1_BE_After_T1: move stop to entry price (breakeven)
      T1_taken = true
    Check T2 → if hit AND T1_taken:
      Exit M1_T2_Contracts at T2 price
      Position fully closed
    Check TC → if bars_held >= M1_TimeCap:
      Exit ALL remaining contracts at market
  
  Priority: EOD Close > Stop > Target > Time Cap (check in this order per bar)
```

⚠️ EOD close has HIGHEST priority. If 15:50 hits while in a position, close 
immediately regardless of stop/target proximity.

⚠️ The stop check must happen BEFORE the target check on each bar. If the same 
bar hits both stop and target (wide range bar), the stop takes priority. This 
is conservative — it assumes the worst case.

⚠️ After T1 is hit and BE is set, the stop for remaining contracts is at entry 
price. If price reverses and hits entry, the remaining 2ct exit at breakeven 
(0 PnL on those contracts, +60t captured on the T1 contract).

### Mode 2: Single Exit

```
  Stop = entry ± max(M2_StopMultiplier × zone_width, M2_StopFloor)
  Target = entry ± M2_TargetMultiplier × zone_width
  TC countdown = M2_TimeCap bars
  
  On each bar:
    Check stop → if hit: exit ALL contracts at stop
    Check target → if hit: exit ALL contracts at target
    Check TC → if bars_held >= M2_TimeCap: exit at market
```

⚠️ Mode 2 has NO partial exits and NO breakeven stop. Single exit at stop, 
target, or time cap. Position sizing is the risk management tool for M2.

📌 REMINDER: Zone width is in ticks. M2 stop = max(1.3 × ZW, 100) ticks from 
entry. M2 target = 1.0 × ZW ticks from entry. Contracts = 3/2/1 based on ZW.

### End-of-Day Forced Close

```
  On each bar:
    if current_time >= EOD_CloseTime:
      if position is open:
        Exit ALL remaining contracts at market
        log exit_type = "EOD_CLOSE"
      
      Block new entries until next session open
```

⚠️ Trades must be closed before RTH end (16:00 ET). The default EOD_CloseTime 
is 15:50 ET — this gives 10 minutes of buffer to avoid MOC order flow and 
spread widening in the final minutes. Do NOT use 15:59 — execution risk is 
too high near the close.

⚠️ The EOD close also applies to pending limit orders (EntryOffset > 0). If 
a limit order is unfilled at EOD_CloseTime, cancel it.

⚠️ EOD close is checked BEFORE stop/target/TC on each bar. If EOD_CloseTime 
hits while a position is open with unrealized profit, the position closes at 
market — it does not wait for the target.

---

## Circuit Breaker Implementation

```
Persistent state (survives across bars):
  daily_pnl = 0          // reset at session open
  consec_losses = 0       // reset on any win
  equity_hwm = 0          // high water mark, never resets
  current_equity = 0      // running total
  completed_trades = []   // ring buffer of last N trades
  
  cb_daily_triggered = false    // auto-resets at session open
  cb_consec_triggered = false   // manual reset required
  cb_dd_triggered = false       // manual reset required
  cb_pf_triggered = false       // manual reset required

On trade completion:
  daily_pnl += trade_pnl
  current_equity += trade_pnl
  equity_hwm = max(equity_hwm, current_equity)
  drawdown = equity_hwm - current_equity
  
  if trade is loss:
    consec_losses += 1
  else:
    consec_losses = 0
  
  completed_trades.append(trade_pnl)
  
  // ⚠️ Check ALL breakers on every trade completion — not just the first one triggered
  // Check breakers
  if daily_pnl <= -CB_DailyLossLimit:
    cb_daily_triggered = true
    log("CIRCUIT BREAKER: Daily loss limit hit")
  
  if consec_losses >= CB_MaxConsecLosses:
    cb_consec_triggered = true
    log("CIRCUIT BREAKER: Max consecutive losses hit")
  
  if drawdown >= CB_MaxDrawdown:
    cb_dd_triggered = true
    log("CIRCUIT BREAKER: Max drawdown hit")
  
  if len(completed_trades) >= CB_RollingPF_Window:
    rolling_pf = compute_pf(last N trades)
    if rolling_pf < CB_RollingPF_Floor:
      cb_pf_triggered = true
      log("CIRCUIT BREAKER: Rolling PF below floor")

On session open:
  daily_pnl = 0
  cb_daily_triggered = false
  // Other breakers do NOT auto-reset

Before any new entry:
  if CB_Enabled AND (cb_daily_triggered OR cb_consec_triggered 
                     OR cb_dd_triggered OR cb_pf_triggered):
    skip entry, log reason
```

⚠️ The equity high-water mark and completed trades buffer must persist across 
chart reloads. Use Sierra Chart persistent variables (sc.GetPersistentInt, 
sc.GetPersistentFloat) or write to a file.

📌 REMINDER: Manual reset for consec/dd/pf breakers should be a study input 
toggle (e.g., CB_Reset input that the trader sets to 1, the study reads it, 
resets the breakers, then sets it back to 0).

---

## Logging

Every trade decision should be logged to a CSV file for replication verification:

| Column | Description |
|--------|------------|
| datetime | Bar datetime of the decision |
| touch_id | Zone touch identifier |
| zone_type | DEMAND or SUPPLY |
| zone_edge | Zone edge price |
| zone_width | Zone width in ticks |
| zone_tf | Zone timeframe |
| seq | Touch sequence number |
| aeq_score | A-Eq score |
| bzscore | B-ZScore linear output |
| mode | 1, 2, or SKIP |
| skip_reason | If skipped: threshold, filter, overlap, circuit_breaker |
| entry_price | Actual fill price |
| contracts | Position size |
| stop_price | Stop level |
| target_price | Target level(s) |
| exit_price | Actual exit price |
| exit_type | TARGET_T1, TARGET_T2, BE_RUNNER, STOP, TIMECAP, EOD_CLOSE |
| pnl_ticks | Per-contract PnL |
| pnl_total | Total PnL (all contracts) |
| bars_held | Duration |
| cb_state | Circuit breaker status at decision time |

⚠️ Log EVERY touch, including skips. The replication gate needs to compare the 
C++ decision log against the Python simulation output touch-by-touch.

---

## Visual Display (Chart Annotations)

The autotrader draws visual indicators on the chart for trade monitoring:

### Entry Arrows

On trade entry, draw a directional arrow at the entry bar:
- **Long (demand zone):** UP arrow below the bar low
- **Short (supply zone):** DOWN arrow above the bar high
- **Color:** Green for M1, Blue for M2

### Entry Labels

Above the arrow (for longs) or below the arrow (for shorts), display a text 
label with:
```
M1 52.3    ← mode + score (A-Eq score for M1)
M2 0.67    ← mode + score (B-ZScore for M2)
```

⚠️ Use `sc.AddUseTool()` with DRAWING_TEXT for labels. The score should be 
formatted to 1-2 decimal places. Place the label close to the arrow but offset 
enough to not overlap price bars.

### Stop and Target Lines

While a position is open, draw horizontal lines at:
- **Stop level:** Red dashed line
- **Target level(s):** Green dashed line(s)
  - M1: two target lines (T1 at 60t, T2 at 120t from entry)
  - M2: one target line (1.0×ZW from entry)
- **BE level (after T1):** Yellow dashed line at entry price (M1 only, after T1 hit)

```
On position open:
  Draw stop line at stop_price (red)
  Draw T1 line at t1_price (green)
  Draw T2 line at t2_price (green, M1 only)

On T1 hit (M1):
  Remove T1 line
  Draw BE line at entry_price (yellow)
  
On position close (any exit type):
  Remove ALL lines (stop, target, BE)
```

⚠️ Lines must DISAPPEAR when hit or when the position closes. Do not leave 
stale lines on the chart. Use `sc.DeleteACSChartDrawing()` or manage line 
IDs to remove them cleanly.

📌 REMINDER: Sierra Chart tool drawings persist across chart reloads unless 
explicitly deleted. The study should clean up lines on position close AND 
on study removal/recalculation.

---

## Step 1: Implementation

⚠️ BEFORE WRITING ANY CODE, read the existing autotrader and study files for 
ACSIL patterns, order management conventions, and subgraph reading logic. The 
GSD has had issues with Sierra Chart C++ implementation — these files are the 
authoritative reference for how this codebase handles ACSIL.

**Reference files (READ FIRST):**
```
EXISTING AUTOTRADERS (order management, entry/exit patterns, persistent state):
  C:\Projects\pipeline\shared\archetypes\zone_touch\acsil\ATEAM_ZONE_BOUNCE_FIXED.cpp
  C:\Projects\pipeline\shared\archetypes\zone_touch\acsil\ATEAM_ZONE_BOUNCE_ZONEREL.cpp

ZONE TOUCH ENGINE (subgraph layout, touch detection, zone data access):
  c:\Projects\sierra\studies\ZoneTouchEngine.cpp
```

⚠️ ATEAM_ZONE_BOUNCE_FIXED is the Mode 1 autotrader (fixed stop/target). 
ATEAM_ZONE_BOUNCE_ZONEREL is the Mode 2 autotrader (zone-relative stop/target). 
The v3.2 autotrader COMBINES both into a single study with a priority waterfall. 
Use these two files as the SOLE reference for:
1. How to read ZTE subgraphs (which subgraph index = which field)
2. Order management (entry, position tracking, exit)
3. Stop/target computation for both FIXED and ZONEREL modes
4. Input registration patterns
5. Session handling (RTH detection)
6. Persistent variable usage across chart reloads

📌 REMINDER: Do NOT copy deprecated files from other directories. These two 
files in the `acsil\` directory are the authoritative ACSIL references. The 
frozen v3.2 parameters (partials, 1.3×ZW stop, circuit breakers, EOD close) 
are NEW functionality not in these files — implement from this spec using 
the ACSIL patterns from the reference files.

Build the study as `ATEAM_ZONE_TOUCH_V32.cpp` following the same ACSIL 
conventions used in the reference files:

- Use `sc.` API for bar data, order management, persistent variables
- Register all inputs with `sc.Input[]` (follow the input registration pattern 
  from ATEAM_ZONE_BOUNCE_FIXED / ZONEREL)
- Use `sc.Subgraph[]` for visual indicators
- Order management: follow the entry/exit/position tracking pattern from 
  the FIXED and ZONEREL autotraders (not generic ACSIL examples)
- Subgraph reading: follow the ZTE subgraph access pattern from the 
  FIXED/ZONEREL autotraders

⚠️ IMPORTANT: The ZTE study must be on the same chart (or a referenced chart) 
so the autotrader can read its subgraph values. Document which ZTE subgraphs 
map to which data fields (zone edge, zone width, zone type, touch signal, 
seq number, timeframe).

📌 REMINDER: Sierra Chart studies process bar-by-bar. The autotrader's logic 
must handle:
- Partial chart recalculation (when chart reloads)
- Study warm-up period (ZTE needs N bars before producing valid zones)
- Multiple touches on the same bar (pick highest priority)
- Session transitions (RTH open/close for M2 filter)

---

## Step 2: Replication Gate

⚠️ MANDATORY before paper trading. The C++ autotrader must produce IDENTICAL 
trade decisions to the Python simulation on the SAME historical data.

### 2a: Run C++ on P1 historical data

Load the P1 data period in Sierra Chart with the ZTE + autotrader studies. 
Let the autotrader process all bars and produce its trade log.

### 2b: Compare to Python baseline

| Metric | Python | C++ | Match? |
|--------|--------|-----|--------|
| M1 qualifying touches | 127 | ? | ? |
| M2 qualifying touches | 325 | ? | ? |
| M1 traded (after overlap) | 107 | ? | ? |
| M2 traded (after overlap) | 239 | ? | ? |
| M1 PF @3t (flat exits) | 8.50 | ? | ? |
| M2 PF @3t | 4.61 | ? | ? |

⚠️ The C++ uses the JSON B-ZScore model (raw linear, threshold 0.50) for ALL 
periods, while Python P1 used the CSV probability model. This means the C++ M2 
qualifying count on P1 may differ from Python's 325. This is EXPECTED and 
acceptable — the C++ is forward-looking and uses the same model for all data.

The replication check should compare:
1. A-Eq scores match (these use the same feature config)
2. B-ZScore raw linear output matches the JSON model's output
3. Waterfall routing is consistent (same priority, same overlap logic)
4. Exit timing matches (same stop/target/TC trigger bars)

📌 REMINDER: Small differences (1-3 trades) are acceptable due to:
- Bar boundary handling (C++ processes bar-by-bar, Python may use vectorized)
- Floating point rounding in feature computation
- ZTE warm-up differences

Large differences (>5% of trades) indicate a logic error. Debug before 
proceeding to paper trading.

### 2c: Verify partial exits

Specifically for M1 partial exits, verify on 5 random M1 trades:
- T1 fires at the correct bar
- Correct number of contracts exit at T1
- Stop moves to BE after T1
- T2 fires at the correct bar (or stop/TC)
- PnL matches Python per-leg

---

## Step 3: Paper Trading (P3)

### 3a: Setup

- Enable autotrader on a live NQ chart with ZTE
- Set all inputs to frozen defaults
- Enable logging
- Set CB_Enabled = true
- Use paper trading mode (Sierra Chart simulated orders)

### 3b: Monitoring during P3

⚠️ All circuit breaker thresholds come from the stress test. Do NOT adjust 
them during paper trading unless the stress test is re-run on new data.

| Metric | Check Frequency | Action Threshold |
|--------|----------------|-----------------|
| Daily PnL | End of each day | < -700t → auto-stops |
| Rolling 30-trade PF | After each trade | < 1.0 → review |
| Cumulative DD | After each trade | > 1,541t → hard stop |
| Fill rate (if using EntryOffset) | Weekly | < 70% → reduce offset |
| Trade count vs expected | Weekly | ±30% → investigate |

### 3c: P3 validation criteria

After 60+ trades (approximately 10 trading days at 6.24 trades/day):

| Metric | Pass | Marginal | Fail |
|--------|------|----------|------|
| PF | > 2.0 | 1.5-2.0 | < 1.5 |
| WR (combined) | > 70% | 60-70% | < 60% |
| Max DD | < 1,541t | 1,541-2,000t | > 2,000t |
| M1 WR | > 85% | 80-85% | < 80% |

⚠️ 60 trades is the MINIMUM for a directional read. Statistical significance 
requires 200+ trades (~30 trading days). The 60-trade check is a sanity check, 
not a definitive validation.

📌 REMINDER: Live trading introduces slippage, missed fills, and data feed 
differences. A 10-20% PF reduction from backtested values is expected and 
acceptable. A 50%+ reduction signals a problem.

---

## Output Files

Save to: `C:\Projects\pipeline\shared\archetypes\zone_touch\acsil\`
- `ATEAM_ZONE_TOUCH_V32.cpp` — the autotrader study source
- `zone_touch_v32_inputs.txt` — default input values for reference
- `replication_log_p1.csv` — C++ trade log on P1 data (for replication gate)

**Scoring model files (READ ONLY — do not modify):**
- `c:\Projects\pipeline\shared\archetypes\zone_touch\output\feature_config_v32.json`
- `c:\Projects\pipeline\shared\archetypes\zone_touch\output\scoring_model_aeq_v32.json`
- `c:\Projects\pipeline\shared\archetypes\zone_touch\output\scoring_model_bzscore_v32.json`

---

## Self-Check Before Paper Trading

- [ ] All study inputs registered with correct defaults
- [ ] ATEAM_ZONE_BOUNCE_FIXED.cpp read for FIXED mode ACSIL patterns
- [ ] ATEAM_ZONE_BOUNCE_ZONEREL.cpp read for ZONEREL mode ACSIL patterns
- [ ] ZTE subgraph index mapping confirmed from reference files
- [ ] A-Eq scoring matches feature_config_v32.json
- [ ] All 7 features: code → meaning → ZTE source documented in code comments
- [ ] Feature computation matches Python pipeline (verified on sample touches)
- [ ] B-ZScore uses JSON model (raw linear, no sigmoid, threshold 0.50)
- [ ] Waterfall: Mode 1 checked before Mode 2
- [ ] One position at a time enforced
- [ ] PreemptionEnabled input present (default false)
- [ ] M1 partial exits: 1ct@T1, 2ct@T2, BE after T1
- [ ] M1 stop checked before target on each bar
- [ ] M2 stop = max(1.3×ZW, 100t) from entry
- [ ] M2 target = 1.0×ZW from entry
- [ ] M2 position sizing by zone width (3/2/1)
- [ ] EntryOffset parameter functional (default 0)
- [ ] Entry-relative stop/target (not zone-fixed)
- [ ] EOD forced close at configurable time (default 15:50 ET)
- [ ] EOD entry blackout prevents late entries (default 15:30 ET)
- [ ] Pending limit orders cancelled at EOD
- [ ] Entry arrows drawn (up for long/green M1, blue M2; down for short)
- [ ] Entry labels show mode + score (e.g., "M1 52.3")
- [ ] Stop/target lines drawn while position open (red stop, green target)
- [ ] M1 T1 line removed and BE line added after T1 hit
- [ ] ALL lines removed on position close (no stale lines)
- [ ] Daily loss circuit breaker resets at session open
- [ ] Consecutive loss circuit breaker requires manual reset
- [ ] Drawdown circuit breaker requires manual reset
- [ ] Rolling PF circuit breaker requires manual reset
- [ ] All touch decisions logged (including skips)
- [ ] Replication gate passed on P1 data (±5% trade count)
- [ ] Partial exit verified on 5 random M1 trades
- [ ] Persistent variables survive chart reload
