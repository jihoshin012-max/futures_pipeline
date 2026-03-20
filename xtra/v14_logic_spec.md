# ATEAM Rotation V1.4 — Definitive Logic Specification

> **This document is the single source of truth for the validated rotation config.**
> It defines every decision point, state transition, and branch in pseudocode.
> The C++ implementation MUST replicate this logic exactly.
> Any ambiguity should be resolved by referring to the Python simulator (`run_seed_investigation.py`).

**Version:** V1.4 (Adaptive P90/P75 + AddDist decoupled + 10:00 start + Roll50 SR + max_cap_walks stop)
**Status:** Validated on P1 (NPF=1.172 w/ stops), P2b (NPF=1.230 w/ stops). P2a failed (regime dip).
**V1.3 is OBSOLETE. Do NOT reference it.**

---

## 1. Architecture Overview

V1.4 requires THREE C++ studies on the same chart:

| Study | Purpose | New? |
|-------|---------|------|
| **ZigZagRegime** | 200-swing rolling buffer → P90 (StepDist), P75 (AddDist), std subgraphs | NEW — must build |
| **SpeedRead V2** | Market speed composite | EXISTS — minor modification needed (Roll50 subgraph) |
| **ATEAM_ROTATION_V14** | Autotrader — reads from both studies above | REWRITE of V1.2 |

The autotrader reads adaptive StepDist/AddDist from ZigZagRegime and Roll50 SR from SpeedRead V2 via `GetStudyArrayUsingID`. It does NOT compute rolling percentiles or rolling SR internally.

> **⚠️ KEY DIFFERENCE FROM V1.2/V1.3: StepDist and AddDist are no longer fixed input values. They are READ from the ZigZagRegime study at each cycle entry. SeedDist (15 pts) remains fixed.**

---

## 2. Study 1: ZigZagRegime (NEW)

### Purpose
Maintains a rolling window of the last 200 completed zigzag swing distances from Sierra Chart's built-in Zig Zag study. Outputs rolling percentiles and std as subgraphs for the autotrader to read.

### Inputs

| Input | Name | Default | Notes |
|-------|------|---------|-------|
| Input[0] | Zigzag Study ID | 0 | ID of Sierra Chart's Zig Zag study on same chart |
| Input[1] | Rolling Window | 200 | Number of completed swings to track |
| Input[2] | Enable | Yes | |

### Subgraphs (Output)

| Subgraph | Name | Description |
|----------|------|-------------|
| SG[0] | ZZ_P90 | Rolling P90 of abs(swing distances) — used as StepDist |
| SG[1] | ZZ_P75 | Rolling P75 — used as AddDist |
| SG[2] | ZZ_P50 | Rolling median — regime health monitor |
| SG[3] | ZZ_Std | Rolling std — used by adaptive stop (future) |
| SG[4] | ZZ_P85 | Rolling P85 — calibration health monitor |

### Data Source

Read from Sierra Chart's Zig Zag study using `GetStudyArrayUsingID`:
- **Zig Zag Line Length** column — this has SIGNED values (positive=up leg, negative=down leg)
- Use `abs()` on every value before inserting into the rolling buffer

> **⚠️ CRITICAL: The zigzag values are SIGNED. Failing to abs() them will produce a buffer with half the values negative, making percentile computations meaningless.**

### Logic

```
// Internal state: circular buffer of 200 swing distances
double swingBuffer[200]
int    bufferCount = 0      // how many swings stored (0 to 200)
int    bufferHead  = 0      // next write position
double lastZZLength = 0.0   // previous bar's ZZ Line Length (for change detection)

function OnBar(currentBarIndex):
    // Read zigzag line length from the referenced study
    zzLength = GetStudyArrayUsingID(ZigzagStudyID, ZZ_LINE_LENGTH_SUBGRAPH)[currentBarIndex]
    
    // Detect new completed swing: zzLength changes from previous bar
    if zzLength != lastZZLength AND zzLength != 0 AND lastZZLength != 0:
        swingDist = abs(zzLength)
        
        // Insert into circular buffer
        // ⚠️ CRITICAL: swingDist must be abs(zzLength) — zigzag values are SIGNED
        swingBuffer[bufferHead] = swingDist
        bufferHead = (bufferHead + 1) % 200
        if bufferCount < 200:
            bufferCount += 1
    
    lastZZLength = zzLength
    
    // Compute percentiles if buffer has enough data
    if bufferCount >= 20:  // minimum warm-up
        sorted = sort(swingBuffer[0..bufferCount-1])
        SG[0][currentBarIndex] = percentile(sorted, 90)  // P90
        SG[1][currentBarIndex] = percentile(sorted, 75)  // P75
        SG[2][currentBarIndex] = percentile(sorted, 50)  // P50
        SG[3][currentBarIndex] = std(swingBuffer[0..bufferCount-1])
        SG[4][currentBarIndex] = percentile(sorted, 85)  // P85
    else:
        // Warm-up period — output 0 (autotrader should not trade)
        SG[0..4][currentBarIndex] = 0.0
```

> **⚠️ EDGE CASES:**
> - **Full recalculation:** Buffer rebuilds from scratch by processing all historical bars.
> - **Session boundaries:** The zigzag study runs continuously (ETH + RTH). The rolling buffer captures ALL swings regardless of session. The autotrader decides when to READ the values (only during 10:00-16:00).
> - **Warm-up:** First ~200 swings produce expanding-window percentiles. P90 stabilizes after ~100 swings. During warm-up (bufferCount < 20), output 0.0 — autotrader treats 0.0 as "not ready, don't trade."
> - **First swing missed:** `lastZZLength` starts at 0.0, so the first zigzag value change (0→nonzero) is skipped by the `lastZZLength != 0` guard. This loses one swing out of thousands — negligible for a 200-swing buffer.

### Percentile Computation

For an array of N sorted values, percentile P:
```
index = (P / 100.0) * (N - 1)
lower = floor(index)
frac  = index - lower
result = sorted[lower] + frac * (sorted[lower+1] - sorted[lower])
```
This matches NumPy's default linear interpolation.

---

> **📌 REMINDER: Two rolling computations exist in V1.4:**
> 1. **ZigZagRegime:** 200-swing buffer → P90, P75, std (this section)
> 2. **SpeedRead Roll50:** 50-bar rolling average of SR composite (next section)
> Different studies, different windows, different data. Do NOT conflate.

---

## 3. Study 2: SpeedRead V2 (MODIFICATION)

### What Exists
SpeedRead V2 already computes the composite speed indicator. Subgraph[0] is the smoothed composite (default 3-bar SMA). Arrays[0] stores the raw (pre-smoothing) composite.

### What's Needed
The validated config uses **Roll50** — a 50-bar simple moving average of the raw composite. The autotrader compares Roll50 against threshold 48.

**Two options for implementation:**

**Option A (preferred): Add a Roll50 subgraph to SpeedRead V2**
- New Subgraph[5]: Roll50 — 50-bar SMA of Arrays[0] (raw composite)
- New Input: Roll50 Period (default 50)
- Autotrader reads SG[5] via GetStudyArrayUsingID

**Option B: Autotrader computes Roll50 internally**
- Autotrader reads SpeedRead V2 Arrays[0] (raw composite) for the last 50 bars
- Computes its own SMA
- More complex autotrader, but SpeedRead V2 stays unmodified

> **⚠️ Whichever option is chosen, the Roll50 value must match the Python pipeline's `rolling(50).mean()` on the raw composite. Verify with the SpeedRead verification data from Phase 2 (max delta was 0.000000 on P1 cross-check).**

---

## 4. Study 3: ATEAM_ROTATION_V14 (Autotrader)

### Inputs

| Input | Name | Default | Notes |
|-------|------|---------|-------|
| Input[0] | SeedDist | 15.0 | Fixed. Seed detection distance (points). |
| Input[1] | InitialQty | 1 | Every entry and add is 1 contract |
| Input[2] | ML | 1 | Max martingale level. ML=1 → addQty always = InitialQty |
| Input[3] | PositionCap | 2 | Max absolute position size |
| Input[4] | MaxCapWalks | 2 | Max cap-walks per cycle before forced flatten. 0=unlimited. |
| Input[5] | Enable | Yes | Master on/off |
| Input[6] | CSV Log | Yes | |
| Input[7] | ZigZagRegime Study ID | 0 | Must point to ZigZagRegime study on same chart |
| Input[8] | SpeedRead Study ID | 0 | Must point to SpeedRead V2 study on same chart |
| Input[9] | SR Threshold | 48.0 | Roll50 SR composite must be ≥ this for seed + reversal |
| Input[10] | Flatten Time (HHMM) | 1600 | 24hr format, ET |
| Input[11] | Resume Time (HHMM) | 1000 | **10:00 ET, NOT 09:30** |

> **⚠️ KEY DIFFERENCES FROM V1.2/V1.3:**
> - **No StepDist input** — read dynamically from ZigZagRegime SG[0] (P90)
> - **No AddDist input** — read dynamically from ZigZagRegime SG[1] (P75)
> - **AddDist ≠ StepDist** — they are separate values for separate triggers
> - **Resume Time = 10:00** (was 09:30)
> - **MaxCapWalks** is NEW (Input[4])
> - **SR threshold** applies to Roll50 of composite (not point-in-time)

### State Variables

```
double AnchorPrice     = 0.0    // Price reference for StepDist/AddDist calculations
double WatchPrice      = 0.0    // Price reference for SeedDist detection
int    Direction       = 0      // 1=long, -1=short, 0=no direction
int    Level           = 0      // Current add level (0=initial entry only, 1=one add, etc.)
int    CapWalkCount    = 0      // Cap-walks in current cycle (resets on new cycle)
int    OrderPending    = 0      // 1=waiting for fill confirmation
int    FlattenPending  = 0      // 1=waiting for flatten to complete
int    SessionActive   = 0      // 1=past ResumeTime, accepting trades
int    DailyFlattened  = 0      // 1=already flattened today
double CycleStepDist   = 0.0    // StepDist locked at cycle entry (from ZigZagRegime P90)
double CycleAddDist    = 0.0    // AddDist locked at cycle entry (from ZigZagRegime P75)
```

> **⚠️ NEW STATE VARS vs V1.2:**
> - `CapWalkCount` — tracks cap-walks per cycle for the 4C stop
> - `CycleStepDist` / `CycleAddDist` — locked at cycle entry from the adaptive study. They do NOT change mid-cycle. This prevents the distance thresholds from shifting while a cycle is in progress.

---

### Reading Adaptive Parameters

```
function ReadAdaptiveParams():
    // Read from ZigZagRegime study
    readIndex = currentBarIndex - 1  // completed bar, not forming
    
    stepDist = GetStudyArrayUsingID(ZigZagRegimeStudyID, SG0_P90)[readIndex]
    addDist  = GetStudyArrayUsingID(ZigZagRegimeStudyID, SG1_P75)[readIndex]
    
    // ⚠️ Warm-up check FIRST — before floor. ZigZagRegime outputs 0.0 when not ready.
    if stepDist <= 0.0 OR addDist <= 0.0:
        return (0.0, 0.0)  // signals "don't trade"
    
    // Floor: minimum 10 pts for both
    if stepDist < 10.0: stepDist = 10.0
    if addDist  < 10.0: addDist  = 10.0
    
    // Constraint: AddDist <= StepDist
    if addDist > stepDist: addDist = stepDist
    
    return (stepDist, addDist)
```

> **⚠️ Read from `currentBarIndex - 1` (completed bar). The forming bar's values are not final.**

---

### Reading Roll50 SpeedRead

```
function GetRoll50SR(studyID):
    if studyID <= 0:
        return 100.0  // Disabled — fail-open
    
    readIndex = currentBarIndex - 1
    
    // Option A: read from SpeedRead V2 SG[5] (Roll50 subgraph)
    roll50 = GetStudyArrayUsingID(studyID, SG5_ROLL50)[readIndex]
    
    // Option B: compute from raw composite
    // rawArray = GetStudyArrayUsingID(studyID, ARRAYS0_RAW)
    // sum = 0; for i in range(50): sum += rawArray[readIndex - i]
    // roll50 = sum / 50
    
    if roll50 <= 0:
        return 100.0  // Fail-open if data not available
    
    return roll50
```

---

> **📌 MID-DOCUMENT REMINDER:**
> - StepDist = ZigZagRegime P90 (read at cycle entry, locked for cycle duration)
> - AddDist = ZigZagRegime P75 (same — locked at entry)
> - SeedDist = 15 pts FIXED (Input[0])
> - Roll50 SR ≥ 48 gates BOTH seed and reversal entries
> - MaxCapWalks = 2 — flatten if exceeded
> - Cap-walk uses CycleStepDist, NOT CycleAddDist
> - Resume Time = 10:00 ET

---

### Session Time Logic

```
function CheckSessionTime(currentTime):
    
    // CHECK 1: Daily flatten
    if currentTime >= FlattenTime AND DailyFlattened == 0:
        if position != 0:
            FlattenAndCancelAllOrders()
            log("DAILY_FLATTEN")
        
        // Full state reset
        // ⚠️ Reset ALL state including CapWalkCount and CycleStepDist/CycleAddDist
        AnchorPrice    = 0.0
        WatchPrice     = 0.0
        Direction      = 0
        Level          = 0
        CapWalkCount   = 0
        CycleStepDist  = 0.0
        CycleAddDist   = 0.0
        OrderPending   = 0
        FlattenPending = 0
        SessionActive  = 0
        DailyFlattened = 1
        return STOP
    
    // CHECK 2: Session resume (10:00 ET)
    if currentTime >= ResumeTime AND currentTime < FlattenTime:
        if SessionActive == 0:
            SessionActive = 1
            DailyFlattened = 0
        return CONTINUE
    
    // CHECK 3: Outside trading window
    return STOP
```

---

### Main Logic (Per-Tick Processing)

> **⚠️ BRANCH ORDER IS STRICT: A → B → C → D → E → F → G. Each branch returns after processing — no fallthrough. The three distance triggers are:**
> - **CycleAddDist** — ADD trigger (price moves AddDist AGAINST)
> - **CycleStepDist** — REVERSAL trigger (price moves StepDist IN FAVOR)
> - **CycleStepDist** — CAP-WALK trigger (price moves StepDist AGAINST when at cap)

```
function OnTick():

    // ========================================
    // GATE 1: Study enabled?
    // ========================================
    if not Enabled:
        return
    
    if currentBarIndex != lastBarIndex:
        return

    // ========================================
    // GATE 2: Session time check
    // ========================================
    if CheckSessionTime(currentTime) == STOP:
        return
    
    // ========================================
    // READ CURRENT STATE
    // ⚠️ Roll50 SR read from completed bar (index-1), same as ZigZagRegime reads
    // ========================================
    position = GetTradePosition()
    price = Close[currentBarIndex]
    roll50SR = GetRoll50SR(SpeedReadStudyID)
    
    // ========================================
    // GATE 3: Full recalculation reset
    // ========================================
    if IsFullRecalculation AND currentBarIndex == lastBarIndex:
        ResetAllState()
        return
    
    // ========================================
    // BRANCH A: Order pending — waiting for fill
    // ⚠️ BRANCH ORDER: A→B→C→D→E→F→G. Each returns. No fallthrough.
    // ========================================
    if OrderPending == 1:
        // Check if fill happened by comparing position to expected
        // If filled, set OrderPending = 0
        // If not filled, return and wait
        return

    // ========================================
    // BRANCH B: Flatten pending — waiting for broker to confirm flat
    // ========================================
    if FlattenPending == 1:
        if position != 0:
            return  // Still waiting
        
        // Flatten complete. Check SR before reversing.
        // ⚠️ SR gates the REVERSAL ENTRY, not the flatten. Flatten always executes.
        if roll50SR < SRThreshold:
            // SR too low — enter watching mode
            FlattenPending = 0
            AnchorPrice    = 0.0
            WatchPrice     = price    // NEW watch price at current price
            Direction      = 0
            Level          = 0
            CapWalkCount   = 0
            CycleStepDist  = 0.0
            CycleAddDist   = 0.0
            log("SR_BLOCK_REVERSAL", roll50SR)
            return
        
        // SR OK — read adaptive params and enter opposite direction
        (sd, ad) = ReadAdaptiveParams()
        if sd == 0.0:
            // ZigZagRegime not ready — enter watching mode
            FlattenPending = 0
            WatchPrice = price
            Direction  = 0
            Level      = 0
            CapWalkCount = 0
            return
        
        newDir = -Direction
        if SendMarketOrder(newDir, InitialQty):
            AnchorPrice   = price
            WatchPrice    = 0.0
            Direction     = newDir
            Level         = 0
            CapWalkCount  = 0
            CycleStepDist = sd     // ⚠️ Lock adaptive params — do NOT update mid-cycle
            CycleAddDist  = ad     // AddDist (P75) < StepDist (P90) always
            OrderPending  = 1
            FlattenPending = 0
            log("REVERSAL_ENTRY", newDir, price, sd, ad, roll50SR)
        return

    // ========================================
    // BRANCH C: No position, no direction — SEED detection
    // Uses SeedDist (fixed 15 pts), NOT StepDist
    // ⚠️ SeedDist=15 is from Input[0]. CycleStepDist/CycleAddDist are set AFTER seed fires.
    // ========================================
    if position == 0 AND Direction == 0:
        
        // Set watch price on first tick of session
        if WatchPrice == 0.0:
            WatchPrice = price
            log("WATCH_SET", price)
            return
        
        dist = price - WatchPrice  // signed distance
        
        if abs(dist) >= SeedDist:
            // Check SR before seeding
            // ⚠️ SR blocks seed but WatchPrice stays FIXED (does not update)
            if roll50SR < SRThreshold:
                // SR too low — keep watching, DO NOT update WatchPrice
                log("SR_BLOCK_SEED", roll50SR)
                return
            
            // Read adaptive params
            (sd, ad) = ReadAdaptiveParams()
            if sd == 0.0:
                return  // Not ready
            
            seedDir = 1 if dist > 0 else -1
            if SendMarketOrder(seedDir, InitialQty):
                AnchorPrice   = price
                WatchPrice    = 0.0
                Direction     = seedDir
                Level         = 0
                CapWalkCount  = 0
                CycleStepDist = sd
                CycleAddDist  = ad
                OrderPending  = 1
                log("SEED_ENTRY", seedDir, price, sd, ad, roll50SR)
        return

    // ========================================
    // From here: position is open. Check distance triggers.
    // ⚠️ REMINDER: CycleAddDist (P75) for ADD. CycleStepDist (P90) for REVERSAL and CAP-WALK.
    // These were locked at cycle entry. They do NOT change mid-cycle.
    // ========================================
    if position == 0:
        return  // Safety: no position but has direction — shouldn't happen

    absPos = abs(position)
    signedDist = (price - AnchorPrice) * Direction
    // signedDist > 0 means price moved IN FAVOR
    // signedDist < 0 means price moved AGAINST

    // ========================================
    // BRANCH D: Cap-walk stop check (4C)
    // ⚠️ Check BEFORE reversal/add to prevent processing a stopped cycle
    // ========================================
    if MaxCapWalks > 0 AND CapWalkCount >= MaxCapWalks:
        // Already exceeded max cap-walks — should have been stopped
        // This is a safety catch, not normal flow
        FlattenAndCancelAllOrders()
        log("CAPWALK_STOP_SAFETY", CapWalkCount)
        // Full reset to watching mode
        AnchorPrice   = 0.0
        WatchPrice    = price
        Direction     = 0
        Level         = 0
        CapWalkCount  = 0
        CycleStepDist = 0.0
        CycleAddDist  = 0.0
        return

    // ========================================
    // BRANCH E: Price moved IN FAVOR by CycleStepDist → REVERSAL
    // ========================================
    if signedDist >= CycleStepDist:
        FlattenAndCancelAllOrders()
        FlattenPending = 1
        log("REVERSAL_TRIGGER", price, signedDist, CycleStepDist)
        return

    // ========================================
    // BRANCH F: Price moved AGAINST — ADD or CAP-WALK
    // ⚠️ AddDist for adds, StepDist for cap-walks
    // ========================================
    if signedDist <= -CycleAddDist AND absPos < PositionCap:
        // Below cap — ADD
        addQty = InitialQty  // ML=1 always
        if SendMarketOrder(Direction, addQty):
            AnchorPrice = price    // Anchor resets to add price
            Level += 1
            OrderPending = 1
            log("ADD", Direction, addQty, Level, price, CycleAddDist)
        return
    
    if signedDist <= -CycleStepDist AND absPos >= PositionCap:
        // At cap — CAP-WALK (anchor walks, no position change)
        // ⚠️ Cap-walk uses CycleStepDist (P90), NOT CycleAddDist (P75)
        AnchorPrice = price
        CapWalkCount += 1
        log("CAP_WALK", CapWalkCount, price, CycleStepDist)
        
        // Check 4C stop AFTER incrementing
        if MaxCapWalks > 0 AND CapWalkCount >= MaxCapWalks:
            FlattenAndCancelAllOrders()
            log("CAPWALK_STOP", CapWalkCount, price)
            // Full reset to watching mode
            AnchorPrice   = 0.0
            WatchPrice    = price
            Direction     = 0
            Level         = 0
            CapWalkCount  = 0
            CycleStepDist = 0.0
            CycleAddDist  = 0.0
        return

    // ========================================
    // BRANCH G: No trigger hit — do nothing
    // ========================================
    return
```

> **⚠️ BRANCH F CRITICAL DETAIL: The ADD trigger uses `CycleAddDist` but the CAP-WALK trigger uses `CycleStepDist`. They are DIFFERENT values. AddDist (P75) is smaller than StepDist (P90). This means:**
> - **Adds fire earlier** (at P75 distance against) — entering at better prices
> - **Cap-walks fire later** (at P90 distance against) — giving more recovery room once at cap

---

## 5. State Reset Behavior

Three reset triggers, all use the same full reset:

| Trigger | When | Position | Next State |
|---------|------|----------|------------|
| Daily flatten | 16:00 ET | Flatten if open | Idle until 10:00 next day |
| 4C stop (max cap-walks) | CapWalkCount ≥ MaxCapWalks | Flatten | Watching mode (new watch price at current) |
| SR block after reversal | Roll50 < 48 post-flatten | Already flat | Watching mode (new watch price at current) |

> **⚠️ After 4C stop and SR block: WatchPrice is set to CURRENT price (where the flatten/block happened). The strategy then waits for a fresh SeedDist=15 move from that point. Watch price does NOT revert to the session open price.**

---

## 6. CSV Logging

Log every event with timestamp, event type, and all relevant state:

```
DateTime, Event, Side, Price, AnchorPrice, WatchPrice, Position, Level,
CapWalkCount, CycleStepDist, CycleAddDist, Roll50SR, PnlTicks
```

Events: WATCH_SET, SEED_ENTRY, REVERSAL_TRIGGER, REVERSAL_ENTRY, ADD, CAP_WALK, CAPWALK_STOP, SR_BLOCK_SEED, SR_BLOCK_REVERSAL, DAILY_FLATTEN

> **⚠️ The CSV log is the PRIMARY replication verification tool. Run C++ on P1 in replay mode, export the CSV, and compare entry-by-entry against the Python simulator output. Every cycle entry time, direction, StepDist/AddDist used, and PnL must match.**

---

> **📌 LATE-DOCUMENT REMINDER:**
> - Three studies: ZigZagRegime (NEW), SpeedRead V2 (modified), ATEAM_ROTATION_V14 (rewrite)
> - StepDist/AddDist read from ZigZagRegime at cycle entry, LOCKED for cycle duration
> - AddDist (P75) for adds, StepDist (P90) for reversals and cap-walks
> - SeedDist = 15 fixed, Resume = 10:00, Roll50 SR ≥ 48
> - MaxCapWalks = 2 → flatten + watching mode + fresh seed
> - Replication gate: C++ CSV must match Python output cycle-by-cycle on P1

---

## 7. Replication Gate

Before paper trading, run C++ autotrader on P1 data in Sierra Chart replay mode:

1. Enable CSV logging on both C++ and Python simulator
2. Run both on identical P1 date range
3. Compare cycle-by-cycle:
   - Entry time (within 1 bar tolerance)
   - Entry direction
   - CycleStepDist and CycleAddDist values used
   - Exit time and type (reversal, flatten, stop)
   - Gross PnL per cycle
4. Aggregate comparison: total cycles, NPF, net PnL must match within 1%

**Pass criteria:** >98% of cycles match on direction, entry time (±1 bar), and PnL (±2 ticks).
**Fail:** Debug until pass. The most common C++ bugs from V1.2 experience:
- Reading forming bar instead of completed bar for SR/ZigZag
- Off-by-one in percentile computation
- Signed zigzag values not abs()'d in ZigZagRegime
- AddDist used for cap-walk instead of StepDist
- WatchPrice not resetting after 4C stop
- Warm-up check after floor clamp (trades with StepDist=10 during ZigZagRegime warm-up)

---

## 8. Implementation Priority

| Priority | Component | Effort | Dependency |
|----------|-----------|--------|------------|
| 1 | ZigZagRegime study | Medium | Sierra Chart Zig Zag study must be on chart |
| 2 | SpeedRead V2 Roll50 subgraph | Small | Existing study, add one SMA subgraph |
| 3 | ATEAM_ROTATION_V14 autotrader | Large | Needs both studies above |
| 4 | Replication gate on P1 | Medium | Needs Python CSV export for comparison |
| 5 | Paper trading | — | Replication gate must pass |

---

## Self-Check for C++ Implementation

- [ ] ZigZagRegime uses abs() on zigzag line lengths (signed values)
- [ ] ZigZagRegime circular buffer is 200 swings, not 200 bars
- [ ] ZigZagRegime percentile computation matches NumPy linear interpolation
- [ ] ZigZagRegime outputs 0.0 during warm-up (bufferCount < 20)
- [ ] SpeedRead Roll50 is 50-bar SMA of RAW composite (Arrays[0]), not smoothed (SG[0])
- [ ] Autotrader reads completed bar (index-1) for both ZigZagRegime and SpeedRead
- [ ] CycleStepDist/CycleAddDist locked at cycle entry, NOT updated mid-cycle
- [ ] AddDist used for ADD trigger, StepDist used for REVERSAL and CAP-WALK
- [ ] ReadAdaptiveParams: warm-up check (≤ 0.0) runs BEFORE floor clamp (prevents trading with StepDist=10 during warm-up)
- [ ] Floor: StepDist ≥ 10, AddDist ≥ 10, AddDist ≤ StepDist
- [ ] MaxCapWalks checked AFTER incrementing CapWalkCount
- [ ] 4C stop: flatten → full reset → WatchPrice = current price → watching mode
- [ ] SR block after reversal: WatchPrice = current price (not session open)
- [ ] Resume Time = 10:00 ET (not 09:30)
- [ ] SeedDist = 15 fixed from Input[0] (not from ZigZagRegime)
- [ ] SR threshold applied to Roll50 (not point-in-time composite)
- [ ] SR gates BOTH seed and reversal entries
- [ ] Daily flatten resets ALL state including CapWalkCount and CycleStepDist/CycleAddDist
- [ ] CSV log includes CycleStepDist and CycleAddDist for replication verification
