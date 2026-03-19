# C++ V1.4 Replication Plan — Sierra Chart

## Architecture: Three Studies

V1.4 requires **three separate Sierra Chart studies**. Each is a distinct .cpp file compiled independently. The autotrader reads from the other two via `GetStudyArrayUsingID()`.

```
[Study 1: ZigZagRegime]     [Study 2: SpeedReadFilter]     [Study 3: ATEAM_ROTATION_V1_4]
  200-swing rolling buffer      50-bar rolling SR avg           Reads from Studies 1 & 2
  Outputs: P75, P90 subgraphs   Output: RollingSR subgraph      All trading logic lives here
  Updates: per completed swing   Updates: per bar/tick
```

**Why three studies, not one:**
- Sierra Chart persistent storage is limited (~50 slots). A 200-element rolling buffer in persistent slots is infeasible.
- Studies communicate cleanly via subgraphs — the autotrader reads final values, not raw data.
- Each study can be tested and validated independently.
- Matches the production pattern: studies run on the chart, autotrader consumes their outputs.

---

## Study 1: ZigZagRegime

**Purpose:** Maintain a rolling 200-swing window of completed RTH zigzag leg distances. Output P75 (AddDist) and P90 (StepDist) as subgraph arrays.

**Input:** Sierra Chart's built-in Zig Zag study (5.25 pt reversal, calc mode 3, HL-based).

**Data source:** `Zig Zag Line Length` column from the built-in zigzag. Use `abs()` — both up and down legs.

**Rolling window:** 200 completed swings (count-based, NOT time-based).

### Implementation

```
Subgraphs:
  [0] P75_AddDist  — rolling 200-swing P75 (floor 10.0)
  [1] P90_StepDist — rolling 200-swing P90 (floor 10.0)
  [2] Mean         — rolling mean
  [3] Std          — rolling std

Inputs:
  [0] ZigZag Study ID (int) — reference to the built-in zigzag study on the same chart
  [1] Rolling Window Size (int, default=200)
  [2] P_Low Percentile (float, default=75)
  [3] P_High Percentile (float, default=90)
  [4] Floor (float, default=10.0)

Persistent State:
  Use a float array allocated via sc.GetPersistentPointer() or a static circular buffer.
  - swing_buffer[200] — circular buffer of completed swing lengths
  - buffer_idx — current write position
  - buffer_count — number of swings stored (max 200)

Logic (per bar):
  1. Read zigzag study's "Zig Zag Line Length" via GetStudyArrayUsingID
  2. Detect swing completion: value transitions from nonzero to zero, OR sign changes
  3. On swing completion: push abs(length) into circular buffer
  4. If buffer_count >= window_size: compute P75, P90, mean, std
  5. Write to subgraph arrays for the current bar
  6. Else: write NaN (warmup period)

RTH filter: Only process bars within 09:30-16:00 ET.
```

### Swing Detection Logic

```cpp
float zz_len = ZigZagArray[sc.Index];
float prev_zz = (sc.Index > 0) ? ZigZagArray[sc.Index - 1] : 0;

// Detect completed swing: nonzero -> zero, or sign change
bool swing_completed = false;
float swing_length = 0;

if (zz_len == 0 && prev_zz != 0) {
    swing_completed = true;
    swing_length = fabs(prev_zz);
} else if (zz_len != 0 && prev_zz != 0) {
    int sign_curr = (zz_len > 0) ? 1 : -1;
    int sign_prev = (prev_zz > 0) ? 1 : -1;
    if (sign_curr != sign_prev) {
        swing_completed = true;
        swing_length = fabs(prev_zz);
    }
}
```

### Percentile Computation

Sort the 200-element buffer and index. For P90 with 200 elements: index = 200 * 0.90 - 1 = 179. Use linear interpolation for fractional indices.

Alternatively, use a selection algorithm (O(n) vs O(n log n) sort). For 200 elements, sort is fast enough.

---

## Study 2: SpeedReadFilter

**Purpose:** Compute a 50-bar rolling average of the SpeedRead composite value. Output as a subgraph.

**Input:** SpeedRead composite (from a SpeedRead study already running on the chart, OR computed internally if SpeedRead.cpp is available).

**Data source:** SpeedRead composite value per bar/tick.

### Implementation

```
Subgraphs:
  [0] RollingSR — 50-bar rolling average of SpeedRead composite

Inputs:
  [0] SpeedRead Study ID (int) — reference to SpeedRead study
  [1] SpeedRead Subgraph (int, default=0) — which subgraph has the composite
  [2] Rolling Window (int, default=50)

Logic (per bar):
  1. Read SpeedRead composite via GetStudyArrayUsingID
  2. Maintain running sum of last N values (subtract oldest, add newest)
  3. Write rolling average to subgraph[0]
```

This is simple — a standard SMA computation. No circular buffer needed; just maintain a running sum and subtract the value N bars back.

```cpp
float sr_val = SpeedReadArray[sc.Index];
float old_val = (sc.Index >= RollingWindow) ? SpeedReadArray[sc.Index - RollingWindow] : 0;

// Running sum (use persistent double)
double& running_sum = sc.GetPersistentDouble(0);
int& bar_count = sc.GetPersistentInt(0);

if (sc.Index == 0) {
    running_sum = sr_val;
    bar_count = 1;
} else {
    running_sum += sr_val;
    bar_count++;
    if (bar_count > RollingWindow) {
        running_sum -= old_val;
        bar_count = RollingWindow;
    }
}

RollingSR[sc.Index] = (float)(running_sum / min(bar_count, RollingWindow));
```

---

## Study 3: ATEAM_ROTATION_V1_4 (Autotrader)

**Purpose:** The trading study. Reads from Studies 1 and 2. Executes all rotation logic.

### Input Parameters

```
Inputs:
  [0]  SeedDist (float, default=15.0) — fixed, decoupled from StepDist
  [1]  InitialQty (int, default=1)
  [2]  MaxLevels (int, default=1) — ML=1: flat adds, ML=2: doubling
  [3]  PositionCap (int, default=2)
  [4]  CostTicks (float, default=1.0) — for logging only, not used in execution
  [5]  Enable (YesNo, default=Yes)
  [6]  CSVLog (YesNo, default=Yes)
  [7]  ZigZagRegime Study ID (int) — reference to Study 1
  [8]  SpeedReadFilter Study ID (int) — reference to Study 2
  [9]  SR Threshold (float, default=48.0) — seed + reversal threshold
  [10] Session Start TOD (time, default=10:00) — earliest seed acceptance
  [11] Session End TOD (time, default=16:00) — flatten and stop
```

### Persistent State

```
PersistentDouble:
  [0] AnchorPrice
  [1] WatchPrice
  [2] AvgEntryPrice
  [3] CurrentStepDist (set at cycle entry from Study 1 P90)
  [4] CurrentAddDist  (set at cycle entry from Study 1 P75)

PersistentInt:
  [0] Direction (0=flat, 1=long, -1=short)
  [1] Level (martingale depth)
  [2] PositionQty
  [3] State (IDLE=-2, PRE_RTH=-3, WATCHING=-1, LONG=1, SHORT=2)
  [4] OrderPending
  [5] FlattenPending
  [6] CycleCapWalks (reset per cycle)
  [7] SessionID
  [8] CSVHeaderWritten
```

### State Machine

```
States: IDLE → PRE_RTH → WATCHING → LONG/SHORT

IDLE:
  - Waiting for session start (18:00 ET resume)
  - On first tick after 18:00: go to PRE_RTH

PRE_RTH:
  - Waiting for seed_start_tod (10:00 ET)
  - On first tick at/after 10:00: set WatchPrice = price, go to WATCHING

WATCHING:
  - Compute up_dist = price - WatchPrice, down_dist = WatchPrice - price
  - Read RollingSR from Study 2. If < SR_Threshold: skip seed.
  - If up_dist >= SeedDist AND RollingSR >= SR_Threshold:
      Read CurrentStepDist from Study 1 P90 subgraph
      Read CurrentAddDist from Study 1 P75 subgraph
      Apply floor (max with 10.0)
      SEED LONG: enter 1 contract, set anchor = price, go to LONG
  - If down_dist >= SeedDist AND RollingSR >= SR_Threshold:
      (same as above but SHORT)

LONG/SHORT (positioned):
  - distance = price - anchor
  - For LONG: in_favor = distance >= CurrentStepDist
               adverse = -distance
  - For SHORT: in_favor = -distance >= CurrentStepDist
               adverse = distance

  - If in_favor:
      Read RollingSR from Study 2
      FLATTEN current position
      If RollingSR >= SR_Threshold:
        Read new CurrentStepDist, CurrentAddDist from Study 1
        REVERSAL: enter opposite, set anchor = price, new cycle
      Else:
        Go to WATCHING (reversal skipped, SR too low)

  - Elif adverse >= CurrentStepDist AND at cap:
      CAP-WALK: anchor = price (just move anchor, no trade)
      CycleCapWalks++

  - Elif adverse >= CurrentAddDist AND NOT at cap:
      ADD: enter proposed_qty contracts
      anchor = price
      Update AvgEntryPrice
      PositionQty += proposed_qty

SESSION FLATTEN:
  - At session_end_tod (16:00) OR if positioned at 16:00:
      FLATTEN ALL, full state reset, go to IDLE
  - At 18:00: go to PRE_RTH for next session
```

### Key Differences from V1_OG

| Aspect | V1_OG | V1.4 |
|--------|-------|------|
| StepDist | Fixed input | Adaptive: P90 from Study 1, read at cycle entry |
| AddDist | = StepDist | Adaptive: P75 from Study 1, read at cycle entry |
| SeedDist | = StepDist | Fixed 15 pts (decoupled) |
| Cap behavior | Not implemented | Cap-walk: anchor moves, position stays |
| SR filter | None | Rolling 50-bar avg >= 48 on seed AND reversal |
| Session start | 09:30 | 10:00 (configurable input) |
| ML levels | 1-2-4-8 (geometric) | ML=1: all 1s. ML=2: 1-2-1-2 |
| Watch price | First tick after 18:00 | First tick at 09:30 (rth_open mode) |
| Cap action | N/A | Walk anchor at StepDist (NOT AddDist) |

### Order Execution Notes

- Use `sc.BuyEntry()` / `sc.SellEntry()` with market orders (same as V1_OG)
- `sc.AllowMultipleEntriesInSameDirection = 1` for adds
- After `FlattenAndCancelAllOrders()`, wait for confirmation before entering reversal
- Use `sc.GetTradePosition()` to verify fills before state transitions

### CSV Logging

Expand V1_OG log format:
```
DateTime,Symbol,Event,Side,Price,AvgEntry,PosQty,AddQty,Level,PnlTicks,
StepDist,AddDist,SeedDist,MaxLevels,PosCap,RollingSR,CycleCapWalks
```

Events: SEED, ADD, REVERSAL, REVERSAL_ENTRY, REVERSAL_SR_SKIP, CAP_WALK, FLATTEN, SESSION_FLATTEN

---

## Build & Test Plan

### Phase A: Studies (no trading)

1. **ZigZagRegime study** — build, attach to chart alongside built-in zigzag, verify P75/P90 subgraph values match Python rolling percentile computation on the same date range. Use CSV export to compare.

2. **SpeedReadFilter study** — build, attach alongside SpeedRead study, verify rolling average matches Python computation.

### Phase B: Autotrader (paper trading)

3. **ATEAM_ROTATION_V1_4** — build with all three studies on chart. Run on historical P1 data in Sierra Chart replay mode. Compare trade log CSV against Python simulator output for cycle-by-cycle match.

4. **Validation criteria:**
   - Cycle count within ±2% of Python (small diffs from bar boundary timing)
   - Net PnL within ±5% (execution timing, bar vs tick granularity)
   - Session win rate within ±3%
   - All seeds, reversals, adds, cap-walks appear in correct sequence

### Phase C: Live (sim account)

5. Deploy on NQ sim account, monitor for 5 trading days.
6. Compare daily PnL against Python expectations.
7. Verify SR filter activates/deactivates as expected.

---

## Critical Implementation Notes

1. **Two rolling computations are INDEPENDENT.** Study 1 (ZigZagRegime: 200 swings of zigzag distances) and Study 2 (SpeedReadFilter: 50 bars of SR composite) use different data sources, different window types, different update frequencies. Do NOT conflate them.

2. **Adaptive values are READ AT CYCLE ENTRY only.** Once a cycle starts, CurrentStepDist and CurrentAddDist are fixed for that cycle. The autotrader does NOT re-read during a positioned state.

3. **Cap-walk uses StepDist, not AddDist.** When at position cap: anchor walks at StepDist intervals. Adds fire at AddDist when below cap. These are different triggers.

4. **Watch price = first tick at 09:30, but no seeds until 10:00.** The watch price is set at RTH open (09:30) but the PRE_RTH→WATCHING transition doesn't happen until seed_start_tod (10:00). This means the watch price accumulates 30 minutes of movement before seeds can fire.

5. **Session flatten = full state reset.** At 16:00: flatten position, clear all persistent state (anchor, direction, level, qty, cap-walks), go to IDLE. Same behavior at session_window_end if configured.

6. **SR filter on reversals is the key driver.** The autotrader MUST check RollingSR before entering the opposite direction on a reversal. If RollingSR < threshold, flatten to WATCHING without entering opposite. This single check accounts for +10% NPF improvement.

---

## Post-P2 Queue: Simulator Enhancements (After P2 Validation)

These are tested AFTER P2 one-shot validation on the base config WITHOUT them. They require both Python simulator changes and C++ autotrader inputs.

### 1. max_adverse_sigma parameter

Flatten cycle if adverse excursion from entry > N × rolling zigzag std (from Study 1).
Simulation continues after stop: new watch price at flatten price, new seed when distance met.

- **Python:** Add `max_adverse_sigma` parameter to `simulate_daily_flatten()`. On each positioned tick, check `adverse_excursion > N * rotation_std`. If triggered: flatten, go to WATCHING, set watch_price = price.
- **C++:** Add input `[12] MaxAdverseSigma (float, default=0 = disabled)`. Read Study 1 Std subgraph. Check per-tick while positioned.
- **Sweep:** N = 1.5, 2.0, 2.5, 3.0 via autoresearch on full P1.
- **Key:** The stop reads rolling zigzag std, NOT the cycle's own std. Same Study 1 data source as StepDist/AddDist but different output (std vs percentile).

### 2. max_cap_walks parameter

Flatten cycle if cap-walk count within the current cycle exceeds N. Same continuation logic as above.

- **Python:** Add `max_cap_walks` parameter to `simulate_daily_flatten()`. After each CAP_WALK event, check `cycle_cap_walks > N`. If triggered: flatten, go to WATCHING.
- **C++:** Add input `[13] MaxCapWalks (int, default=0 = disabled)`. Increment `CycleCapWalks` persistent counter on each cap-walk. Check against limit.
- **Sweep:** N = 1, 2, 3, 4 via autoresearch on full P1.
- **Key:** Counter resets per cycle (on SEED, REVERSAL, or FLATTEN). Not per session.
