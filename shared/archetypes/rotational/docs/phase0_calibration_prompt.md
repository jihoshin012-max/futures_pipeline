# Phase 0: Python Simulator Calibration Against C++ V1.1

## OBJECTIVE

Verify that the Python rotation simulator produces identical results to the C++ ATEAM_ROTATION_V1_1 Sierra Chart study. This is a **fidelity gate** — if the simulator disagrees with live C++ execution, all downstream sweep results are untrustworthy.

⚠️ **NO SWEEP RUNS UNTIL THIS GATE PASSES.**

---

## GROUND TRUTH

The calibration reference is the attached file `ATEAM_ROTATION_V1_1_log_live.csv` — a C++ execution log from a single trading session.

**Settings used:**
- StepDist = 25 points
- InitialQty = 1
- MaxLevels = 1 (flat adds: every add is size 1, level resets to 0 after each add)
- MaxContractSize = 3 (resets add size to InitialQty when hit — does NOT cap total position)
- Seed = Directional (wait for price to move StepDist from watch price, then seed in that direction)
- Always-in-market after seed

**Time window:** 2026-03-20 08:29 through 2026-03-20 16:03 (RTH session)

⚠️ **CRITICAL: MaxContractSize (MCS) is NOT MaxTotalPosition (MTP). MCS=3 means: when add size would exceed 3, reset to InitialQty (1). It does NOT prevent position from growing beyond 3. Position reached 7 contracts in this log. The Python simulator MUST replicate this behavior. If you implement MCS as a position cap, the results will be wrong.**

⚠️ **The log ends with an INCOMPLETE cycle — 5 events (1 REVERSAL_ENTRY + 4 ADDs) with no closing REVERSAL. The last complete cycle ends before this. The Python simulator should be compared against the 55 COMPLETE cycles only. Ignore the trailing incomplete cycle in the comparison.**

⚠️ **Date format in this log is M/D/YYYY H:MM (e.g., "3/20/2026 8:29"), NOT the ISO format from previous logs. Parse accordingly.**

**Expected results from the C++ log (complete cycles only):**
- 55 complete rotation cycles (+ 1 incomplete at end, excluded)
- 55 add events
- 43 winning cycles (total: +3,409.5 ticks)
- 12 losing cycles (total: -539.2 ticks)
- Net PnL: +2,870.3 ticks
- Max position: 7 contracts
- Cycle distribution by add count: 26×(0 adds), 17×(1 add), 6×(2 adds), 4×(3 adds), 1×(4 adds), 1×(6 adds)

📌 **These numbers are the pass/fail criteria. Memorize them. Every comparison you make references back to these exact figures.**

---

## DATA NEEDED

**1-tick bar data covering the same time window.** This should be available at:
`C:\Projects\pipeline\stages\01-data\data\bar_data\tick\`

⚠️ **First step: inspect the data files and extract ONLY the rows covering 2026-03-20 08:29 through 2026-03-20 16:04. Confirm the price column name (expected: Last or Close) and timestamp format before writing any simulator code.**

Do NOT load the full 6-month dataset. Extract the one-day window and work with that.

---

## CALIBRATION PROCEDURE

### Step 1: Parse the C++ Log

Read `ATEAM_ROTATION_V1_1_log_live.csv` and extract:
- Every event row with: DateTime, Event type (SEED/ADD/REVERSAL/REVERSAL_ENTRY), Side, Price, AvgEntryPrice, PosQty, AddQty, Level, PnlTicks
- Build a cycle-by-cycle summary: cycle number, start event, end event (REVERSAL), number of adds, exit position size, PnL ticks, side

This parsed log is the ground truth for comparison.

### Step 2: Build or Adapt the Python Simulator

The simulator must implement the V1.1 state machine exactly:

**State variables:**
- AnchorPrice (resets on every action: seed, add, reversal entry)
- WatchPrice (used only during directional seed phase)
- Direction (1=long, -1=short, 0=flat)
- Level (0..MaxLevels-1, resets to 0 after each add since ML=1)
- Position quantity (tracks total contracts held)

**SEED logic:**
1. When flat and no anchor: set WatchPrice = current price
2. Wait for price to move ≥ StepDist from WatchPrice
3. If price ≥ WatchPrice + StepDist → seed LONG
4. If price ≤ WatchPrice - StepDist → seed SHORT
5. On seed: Direction = seed direction, AnchorPrice = current price, Level = 0, WatchPrice = 0

⚠️ **The directional seed is a TWO-PHASE process. Phase A records the watch price. Phase B waits for the StepDist move. Many simulators skip Phase A and seed immediately — this is WRONG for V1.1.**

**REVERSAL logic:**
- Price moves ≥ StepDist IN FAVOR from AnchorPrice
- "In favor" = price went UP if long, DOWN if short
- Action: flatten all contracts, then enter 1 contract in OPPOSITE direction
- Reset: Direction flips, AnchorPrice = current price, Level = 0

**ADD (martingale) logic:**
- Price moves ≥ StepDist AGAINST from AnchorPrice
- "Against" = price went DOWN if long, UP if short
- Compute add size: `addQty = InitialQty × 2^Level` (with ML=1, Level is always 0 after reset, so addQty is always 1)
- If addQty > MaxContractSize → reset addQty to InitialQty, Level = 0
- Add addQty contracts in same direction
- Update: AnchorPrice = current price, Level++ (then if Level >= MaxLevels, Level = 0)

⚠️ **With ML=1: Level starts at 0, addQty = 1×2^0 = 1, Level increments to 1, then resets to 0 (because 1 >= MaxLevels=1). Every add is size 1. Level is always 0 at the start of each add computation. This means MCS=3 is never reached with ML=1 (max add size is always 1). MCS only matters with ML>1. Verify this in your implementation. Position reached 7 contracts in the live log despite MCS=3 — confirming MCS does not cap position.**

📌 **Anchor resets on EVERY action — seed, add, AND reversal entry. This is the core V1.1 behavior. The anchor walks with price on every trade.**

**Flat detection:**
- If position is unexpectedly 0 (not during a reversal flatten), reset all state to initial

**Price comparison:**
- Use the Close/Last price of each bar for all comparisons
- The C++ study runs on `UpdateAlways` with `AllowOnlyOneTradePerBar = 0`, meaning multiple events can fire on the same bar. The Python simulator iterating through bars may need to check BOTH the reversal and add conditions on each bar and handle the case where price moves more than StepDist in a single bar.

### Step 3: Run the Simulator

Run the Python simulator on the extracted 1-tick data with SD=25, ML=1, MCS=3, IQ=1, directional seed.

Produce an event log in the same format as the C++ log: DateTime, Event, Side, Price, PosQty, AddQty, Level, PnlTicks.

### Step 4: Compare Event-by-Event

⚠️ **This is the most important step. Do not skip or abbreviate it.**

For each event in the C++ log, find the corresponding event in the Python log. Compare:

1. **Event type match:** SEED↔SEED, ADD↔ADD, REVERSAL↔REVERSAL, REVERSAL_ENTRY↔REVERSAL_ENTRY
2. **Timestamp:** Within 1 bar tolerance (on 1-tick data this should be exact or ±1 tick)
3. **Price:** Within 0.25 pts (1 tick) tolerance
4. **Side:** Exact match (LONG/SHORT)
5. **Position quantity:** Exact match
6. **Add quantity:** Exact match
7. **PnL (reversals only):** Within 2 ticks tolerance

Report:
- Total events in C++ log vs Python log
- Number of exact matches
- Number of matches within tolerance
- Number of mismatches (with details: which event, what differed, by how much)
- Cycle-level comparison: for each of the 55 complete cycles, does add count and PnL match?

⚠️ **Reminder: The C++ ground truth is 55 complete cycles, net +2,870.3 ticks, cycle distribution 26/17/6/4/1/1. These are the exact numbers the Python output must match.**

### Step 5: Verdict

**PASS (≥95% event match + PnL within 2%):**
- Total PnL: Python net must be within ±57 ticks of 2,870.3 (2% tolerance)
- Cycle count: must be exactly 55 (excluding incomplete trailing cycle)
- Cycle distribution: must match 26/17/6/4/1/1
- ≥95% of individual events match within tolerance

**CONDITIONAL PASS (90-95% match):**
- Document every discrepancy with root cause
- Common acceptable causes: bar-boundary timing (C++ fires mid-bar, Python fires at bar close), rounding differences in AvgEntryPrice
- Unacceptable causes: wrong number of cycles, wrong cycle types, systematic PnL divergence

**FAIL (<90% match or structural disagreement):**
- Do NOT proceed to any sweep
- Debug the simulator: identify the first point of divergence, trace the state machine logic, fix, and re-run

📌 **Final reminder: The goal is structural fidelity — does the Python simulator make the same trading decisions as the C++ study? Timing differences of ±1 tick are expected. Price differences of ±0.25 are expected. Different cycle counts or different cycle types are NOT acceptable.**

---

## OUTPUT

Save all results to: `C:\Projects\pipeline\stages\01-data\analysis\calibration_v1_1\`

1. `calibration_report.md` — Full comparison report with verdict
2. `python_event_log.csv` — Python simulator's event log (same format as C++ log)
3. `comparison_detail.csv` — Event-by-event comparison: C++ event, Python event, match/mismatch, delta
4. `cycle_comparison.csv` — Cycle-by-cycle: cycle number, C++ adds/PnL, Python adds/PnL, match

---

## SELF-CHECK BEFORE FINISHING

- [ ] C++ log parsed: 55 complete cycles, 55 adds, 166 event rows confirmed (+ 1 incomplete trailing cycle excluded)
- [ ] 1-tick data extracted for correct time window (2026-03-20 08:29 – 2026-03-20 16:04)
- [ ] Price column identified and used (Last or Close)
- [ ] Simulator implements directional seed (two-phase: watch → move → seed)
- [ ] Simulator implements MCS correctly (resets add SIZE, does NOT cap position)
- [ ] Anchor resets on every action (seed, add, reversal entry)
- [ ] ML=1 behavior verified: every add is size 1, level always resets
- [ ] Event-by-event comparison completed (not just aggregate PnL)
- [ ] Cycle count: exactly 55 in Python output (excluding incomplete trailing cycle)
- [ ] Cycle distribution matches: 26/17/6/4/1/1
- [ ] Total PnL within 2% of 2,870.3 ticks
- [ ] Verdict issued: PASS / CONDITIONAL PASS / FAIL
- [ ] All discrepancies documented with root cause
- [ ] If FAIL: first point of divergence identified for debugging
