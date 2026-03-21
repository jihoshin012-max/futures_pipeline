# Frozen-Anchor Strategy: Simulator Modification

## OBJECTIVE

Modify the existing rotation simulator to implement frozen-anchor mechanics with symmetric failure exits. This is the smallest structural change that aligns the strategy with the fractal research findings. The deliverable is a tested simulator that accepts the new config schema and produces enriched cycle logs with failure-type classification and progress tracking.

⚠️ **This modifies the existing simulator at `C:\Projects\pipeline\stages\04-backtest\rotational\`. Do NOT rebuild from scratch. The context tagger, cycle logger infrastructure, and cost model are reusable. The changes are: (1) freeze anchor on adverse adds, (2) add failure exit, (3) add ReversalTarget parameter, (4) add new logging columns.**

---

## WHY THIS CHANGE

The Phase 1 sweep revealed that V1.1's walking anchor breaks structural alignment with the fractal data:

- The fractal data measures completion relative to a fixed swing start point
- V1.1 moves the anchor on every adverse add, losing track of the swing origin
- Result: positions get stuck on trending days with no structural exit mechanism
- Nov 20 example: 2-contract position 1,118 pts underwater, -8,942 ticks lost

Freezing the anchor restores the mapping:
- Progress = (price - anchor) / StepDist → maps to half-block curve
- Add count = child retracement count → maps to completion degradation curve
- Failure at -StepDist from anchor → structural parent failure
- Success at +ReversalTarget from anchor → parent move captured

📌 **This is a strategy logic change, not a parameter tuning exercise. The anchor behavior is the foundation — everything else flows from it.**

---

## CONFIGURATION SCHEMA

Replace the existing RotationConfig with:

```python
@dataclass
class FrozenAnchorConfig:
    config_id: str              # Unique identifier (e.g., "FA_SD25_AD10_MA2_RT80")
    step_dist: float            # Parent scale — defines success and failure boundaries
    add_dist: float             # Child scale — distance for adverse adds (points)
    max_adds: int               # Max adverse adds (0 = pure rotation)
    reversal_target: float      # Profit exit as fraction of step_dist (0.5-1.0)
    cost_ticks: float = 2.0     # Per-side cost in ticks
    iq: int = 1                 # Initial quantity (always 1)
    add_size: int = 1           # Contracts per add (always 1 for this sweep)
```

⚠️ **Validation rules:**
- step_dist > 0
- add_dist > 0 (even when max_adds=0 — it's used for the would_flatten_reseed shadow metric)
- max_adds >= 0
- reversal_target > 0 and reversal_target <= 1.0
- add_size = 1 (fixed for this sweep — scaled entry is a separate investigation)

---

## STATE MACHINE

### States

WATCHING → POSITIONED → (back to POSITIONED on add or exit-with-re-entry)

**WATCHING** is only for the start-of-day seed. During the day, SUCCESS and FAILURE exits go directly to a new POSITIONED state (immediate re-entry in opposite direction). The strategy never returns to WATCHING mid-session.

### WATCHING (Directional Seed)

Identical to V1.1. Two-phase:
1. Record WatchPrice = first bar's price at session start
2. Wait for price to move ≥ StepDist from WatchPrice
3. SEED: enter 1 contract in the direction of the move

On seed:
- AnchorPrice = current price (this is the FIXED reference for the entire cycle)
- Direction = direction of the move
- AddCount = 0
- CyclePnL = 0
- CycleCosts = cost_ticks × 1 (seed cost)

📌 **AnchorPrice is set ONCE at seed and does NOT change until the cycle ends. This is the core change from V1.1. Every trigger distance is measured from this fixed point.**

### POSITIONED (Main Loop)

On every bar, check three conditions in this priority order:

⚠️ **Priority order matters. Check all three, fire the FIRST one that's true. Do NOT check lower-priority conditions if a higher one fires.**

**Priority 1 — SUCCESS EXIT:**
Price has moved ≥ reversal_target × step_dist IN FAVOR from AnchorPrice.

→ Flatten all contracts. Enter 1 contract in OPPOSITE direction (re-seed immediately).
→ Log completed cycle as `exit_type = SUCCESS`
→ New AnchorPrice = current price (new cycle starts)
→ AddCount = 0

**Priority 2 — FAILURE EXIT:**
Price has moved ≥ step_dist AGAINST from AnchorPrice.

→ Flatten all contracts. Enter 1 contract in OPPOSITE direction (re-seed immediately).
→ Log completed cycle as `exit_type = FAILURE`
→ New AnchorPrice = current price (new cycle starts)
→ AddCount = 0

**Priority 3 — ADD:**
Price has moved ≥ (AddCount + 1) × add_dist AGAINST from AnchorPrice, AND AddCount < max_adds.

→ Add 1 contract in same direction
→ AddCount += 1
→ CycleCosts += cost_ticks × 1
→ AnchorPrice does NOT change

📌 **Adds fire at successive multiples of AddDist from the FROZEN anchor: first add at 1×AddDist against, second at 2×AddDist, third at 3×AddDist. The anchor never moves. This means each add enters at a progressively better average price relative to the anchor.**

⚠️ **DEAD CONFIG CONSTRAINT: Any add threshold at or beyond -StepDist from anchor is dead — failure exit fires first (Priority 2 > Priority 3). This prunes the grid:**
- **Ratio 0.4** (AD = 0.4×SD): adds at -0.4, -0.8, -1.2×SD. Add3 beyond failure. **MaxAdds 0,1,2 valid.**
- **Ratio 0.5** (AD = 0.5×SD): adds at -0.5, -1.0×SD. Add2 = failure point. **MaxAdds 0,1 valid.**
- **Ratio 1.0** (AD = SD): add1 = failure point. **MaxAdds 0 only.**
- **MaxAdds=0 is identical regardless of AddDist ratio** (no adds fire). Deduplicate in sweep.
The sweep prompt (Prompt 2) will handle the exact config grid with these constraints.

⚠️ **When MaxAdds=0: no add logic runs. Only success and failure exits. This is "pure rotation with symmetric exits" — equivalent to old Approach A but with the failure exit replacing the stuck-position problem. Every StepDist move in either direction triggers a reversal.**

### EXIT MECHANICS

Both SUCCESS and FAILURE exits work the same way mechanically:
1. Flatten entire position (all contracts)
2. Immediately enter 1 contract in the opposite direction
3. New AnchorPrice = current price
4. New cycle begins

The difference is only in classification and PnL:
- SUCCESS: position was profitable (or at least exited at target)
- FAILURE: position was losing (parent move failed)

⚠️ **The immediate re-seed after exit means the strategy is always in the market during RTH (except during the initial seed at session start). There is no flat period between cycles. This is the same as V1.1.**

### SESSION HANDLING

- RTH only: 09:30–16:15 ET
- State reset at start of each session: WatchPrice = 0, no position
- At 16:15: if a cycle is in progress, log it as `exit_type = SESSION_END` in the incomplete cycle file
- First cycle of each day requires a fresh directional seed

📌 **Session reset means: flatten any position, record incomplete cycle, start next day with WATCHING state. No overnight carry.**

---

## PER-CYCLE LOGGING

### Standard Metrics (same as V1.1 sweep)
- config_id, cycle_id, start_time, end_time
- duration_bars, duration_minutes
- side (LONG/SHORT), add_count, exit_position
- pnl_ticks_gross, pnl_ticks_net
- max_favorable_excursion (MFE), max_adverse_excursion (MAE)

### Regime Context (same as V1.1 sweep — pre-computed on bar data)
- atr_20bar, atr_percentile
- swing_median_20, swing_p90_20
- directional_persistence
- bar_range_median_20

### New Columns (Required)

**exit_type:** `SUCCESS` | `FAILURE` | `SESSION_END`
- SUCCESS = price reached +reversal_target × step_dist from anchor
- FAILURE = price reached -step_dist from anchor
- SESSION_END = cycle still open at 16:15 (logged in incomplete file only)

⚠️ **Every completed cycle must have exit_type = SUCCESS or FAILURE. If a cycle ends without either, something is wrong — there is no "hold forever" state in the frozen-anchor strategy.**

**progress_hwm:** Maximum favorable progress as percentage of step_dist during the cycle. Computed as: max((price - anchor) × direction) / step_dist × 100 across all bars in the cycle. A cycle that reached 85% of target before failing back tells a different story than one that never got past 20%.

📌 **progress_hwm maps directly to the half-block curve. If cycles with progress_hwm > 70% have a 90%+ success rate, that confirms the fractal prediction under live strategy conditions. If not, the half-block relationship doesn't hold under strategy execution.**

**time_between_adds:** For cycles with 2+ adds, record the bar count between add 1 and add 2 (and add 2 to add 3 if applicable). Format: comma-separated string (e.g., "342,187"). For 0 or 1 add cycles, set to empty string. Rapid consecutive adds suggest trending; spaced adds suggest rotational pullbacks.

**cycle_day_seq:** Sequence number of this cycle within the current trading day (1, 2, 3, ...). First cycle = 1 (the seed cycle). This lets us compare first-cycle-of-day performance vs subsequent cycles. If cycle_day_seq=1 systematically underperforms, the seed mechanism is fighting the fractal rhythm.

**cycle_start_hour:** Integer hour of cycle start (9, 10, 11, ..., 15). Fractal Fact 5 says time-of-day shouldn't matter — this verifies that under strategy execution. If late-day cycles (14-15) show elevated failure rates, that's a wind-down signal.

**progress_at_adds:** For cycles with adds, record the signed displacement from anchor as percentage of StepDist at the moment each add fired. Negative = adverse (price moved against the position). Format: comma-separated (e.g., "-40,-80" meaning the first add fired when price was 40% of StepDist against anchor, second at 80% against). For 0-add cycles, set to empty string. Since adds only fire on adverse moves, values will always be negative. This shows how deep into the fractal failure zone each add enters.

⚠️ **The new diagnostic columns (exit_type through cycle_waste_pct) each map to a specific fractal finding. They do not influence strategy execution. But they determine whether the frozen-anchor approach is structurally sound or whether we need to pivot again.**

**prev_cycle_exit_type:** How did the PREVIOUS cycle end? Values: `SUCCESS`, `FAILURE`, `SESSION_START` (first cycle of day). This reveals whether failure exits lead to recoveries (failure → success = trend reversal detected correctly) or cascading losses (failure → failure → failure = regime where strategy can't find direction).

**cycle_waste_pct:** Total absolute bar-to-bar price movement during the cycle divided by the net displacement (abs of entry-to-exit distance). Values above 2.0 mean more than half the movement was retracement noise. Fractal Fact 4 predicts 40-52% waste (ratio ~1.7-2.1). If strategy cycles show waste ratios of 4.0+, cycles are spending excessive time in chop.

### Shadow Metrics
- would_flatten_reseed: boolean — did MAE ever exceed 3 × add_dist? (Shadow metric for potential tighter failure exit)
- half_block_profit: PnL snapshot at first bar where price reaches 0.5 × step_dist in favor from anchor. NULL if never reached.

---

## INCOMPLETE CYCLE LOGGING

Same as V1.1 sweep. For each session-end cycle, write to `{config_id}_incomplete.csv`:

- config_id, cycle_id, start_time, end_time, side, position_size
- add_count, avg_entry, last_price, unrealized_pnl_ticks
- exit_type = SESSION_END
- progress_hwm (how far the cycle got before session end)
- cycle_day_seq

Add to config_summary.csv: `incomplete_cycles` (count) and `incomplete_unrealized_pnl` (sum).

Also add to config_summary.csv:
- `success_count`: cycles with exit_type=SUCCESS
- `failure_count`: cycles with exit_type=FAILURE
- `success_rate`: success_count / cycle_count
- `failure_after_failure`: count of cycles where prev_cycle_exit_type=FAILURE AND this cycle also exit_type=FAILURE (cascading failures)

⚠️ **success_rate is NOT the same as win_rate. win_rate is based on PnL sign (a SUCCESS exit with ReversalTarget=0.5 after 2 adds might still be net negative after costs). success_rate is based on exit_type — did the parent move complete or fail structurally.**

---

## COST MODEL

Same as V1.1 sweep:
- SEED: cost_ticks × 1
- ADD: cost_ticks × 1
- SUCCESS EXIT: cost_ticks × (exit_contracts + 1). Flatten + re-seed.
- FAILURE EXIT: cost_ticks × (exit_contracts + 1). Flatten + re-seed.

⚠️ **Both exits pay the same cost — flatten the full position plus enter 1 in the opposite direction. A failure with 3 contracts costs: 3 × cost_ticks (flatten) + 1 × cost_ticks (re-seed) = 4 × cost_ticks.**

---

## ASYMMETRIC PNL STRUCTURE

This is the key structural advantage of frozen anchor with adverse adds. Document this in the verification report.

With SD=40, AddDist=16, MaxAdds=2:
- Entry at anchor. Add1 at anchor-16. Add2 at anchor-32.
- Average entry = anchor - 16

**On SUCCESS (reversal_target=1.0):**
- Exit at anchor + 40
- Contract 1 (entered at anchor): +40pts = +160 ticks
- Contract 2 (entered at anchor-16): +56pts = +224 ticks
- Contract 3 (entered at anchor-32): +72pts = +288 ticks
- Total: +672 ticks gross

**On FAILURE:**
- Exit at anchor - 40
- Contract 1: -40pts = -160 ticks
- Contract 2: -24pts = -96 ticks
- Contract 3: -8pts = -32 ticks
- Total: -288 ticks gross

**Win/loss ratio: 672/288 = 2.33.** Even at 50% win rate, expected value is positive. At the fractal-predicted 64% completion for 2 retracements (which maps to 2 adds), EV = 0.64 × 672 - 0.36 × 288 = +326 ticks per fully-loaded cycle. Note: not all cycles will reach 2 adds — many succeed with 0 or 1 adds, which have even higher completion rates.

📌 **This asymmetry is WHY the frozen anchor works. Adds at progressively better prices make wins larger than losses by construction. The walking anchor in V1.1 destroyed this by resetting the reference point on each add.**

---

## VERIFICATION

### Unit Tests

Write tests for:

1. **Frozen anchor:** After adverse add, verify AnchorPrice unchanged. After success exit, verify AnchorPrice updates to new entry.

2. **Failure exit fires:** Price moves -StepDist from anchor → flatten + re-seed opposite. Verify exit_type=FAILURE.

3. **Success exit fires:** Price moves +ReversalTarget×StepDist from anchor → flatten + re-seed opposite. Verify exit_type=SUCCESS.

4. **Priority order:** Price crosses both add threshold AND failure threshold on same bar → FAILURE fires (priority 2 beats priority 3).

5. **Successive add spacing:** With SD=40, AD=10, MaxAdds=3 (ratio 0.25), adds fire at -10, -20, -30 from frozen anchor. Not at -10 from last add. Failure at -40.

6. **MaxAdds=0:** No adds fire. Success at +RT×SD, failure at -SD. Position always 1.

⚠️ **Test the asymmetric PnL structure explicitly: with SD=40, AD=16, MA=2, RT=1.0, create a SUCCESS scenario and a FAILURE scenario. Verify gross PnL matches the calculations above (672 ticks success, -288 ticks failure).**

7. **ReversalTarget < 1.0:** With RT=0.7 and SD=40, success fires at +28 from anchor (not +40). Verify.

8. **progress_hwm:** Create a cycle where price reaches 80% of target then fails. Verify progress_hwm = 80.

9. **cycle_day_seq:** Run 2 days. Verify first cycle each day has seq=1, subsequent cycles increment.

### Re-Verification Against V1.1

Run with settings that replicate V1.1 behavior:
```python
FrozenAnchorConfig(
    config_id="V11_CHECK",
    step_dist=25.0,
    add_dist=25.0,    # Same as StepDist (V1.1 behavior)
    max_adds=0,        # No adds — simplest case
    reversal_target=1.0  # Full StepDist exit
)
```

⚠️ **This will NOT match V1.1 exactly because V1.1 has no failure exit. But with MaxAdds=0 and AddDist=StepDist, the failure exit fires at exactly the same point V1.1's against-trigger would have fired an add. The cycle count should be similar to A_SD25 from the V1.1 sweep (4,856 cycles) but the PnL will differ because failure exits create bounded losses instead of stuck positions.**

Compare: cycle count should be in the same ballpark. If dramatically different, investigate.

### Fractal Completion Rate Validation

After the unit tests pass, run two configs to validate the fractal completion curve:

```python
# Check 1: Ratio 0.4 — validates 0, 1, 2 add points
FrozenAnchorConfig(
    config_id="FRACTAL_CHECK_R04",
    step_dist=25.0,
    add_dist=10.0,     # Ratio 0.4 — adds at -10, -20. Failure at -25.
    max_adds=2,         # Max possible at this ratio (add3 at -30 > failure at -25)
    reversal_target=1.0,
    cost_ticks=0.0
)

# Check 2: Ratio 0.25 — validates 0, 1, 2, 3 add points
FrozenAnchorConfig(
    config_id="FRACTAL_CHECK_R025",
    step_dist=25.0,
    add_dist=6.25,     # Ratio 0.25 — adds at -6.25, -12.5, -18.75. Failure at -25.
    max_adds=3,
    reversal_target=1.0,
    cost_ticks=0.0
)
```

⚠️ **The dead config constraint limits observable add counts. At ratio 0.4, max useful adds = 2 (add3 at -1.2×SD exceeds failure at -1.0×SD). To validate the 3-retracement point (56%), we need ratio 0.25 where add3 at -0.75×SD is still inside the failure boundary. If the 3-add completion rate at ratio 0.25 matches 56%, the fractal mapping holds even with a tighter child scale.**

From the cycle log, compute **success rate by add count**:
- Cycles with 0 adds: what % ended in SUCCESS vs FAILURE?
- Cycles with 1 add: what %?
- Cycles with 2 adds: what %?
- Cycles with 3 adds: what %?

⚠️ **Compare these to the fractal completion degradation curve: 0 ret = ~100%, 1 ret = 79.7%, 2 ret = 64.1%, 3 ret = 56.0%. These are the most important numbers in the entire verification. If 1-add cycles succeed at ~80%, the frozen anchor is faithfully capturing fractal structure. If they succeed at 60%, the distance-threshold proxy is losing something vs actual retracement counting. Report the comparison table in verification_report.md.**

📌 **This is not a pass/fail gate — the strategy might work even if the rates don't match exactly. But the comparison tells us HOW MUCH structural fidelity we have. A large gap (>10pp at 1 add) means the distinction between "distance threshold crossed" and "actual retracement occurred" matters in practice, and Option 2 (real-time zig-zag) might be needed after all.**

---

## OUTPUT

Save all files to: `C:\Projects\pipeline\stages\04-backtest\rotational\`

Overwrite or update existing files as needed — the V1.1 versions are committed in git.

```
rotational/
├── rotation_simulator.py    # Updated — frozen anchor + failure exit
├── config_schema.py         # Updated — FrozenAnchorConfig
├── context_tagger.py        # Unchanged — reuse from V1.1
├── cycle_logger.py          # Updated — new columns
├── verification_report.md   # New — frozen anchor tests + V1.1 comparison
└── tests/
    └── test_frozen_anchor.py  # New test suite
```

---

## SELF-CHECK BEFORE FINISHING

- [ ] AnchorPrice set once at seed/re-seed, NEVER changes on adds
- [ ] Failure exit at -StepDist from frozen anchor → flatten + re-seed opposite
- [ ] Success exit at +ReversalTarget×StepDist from anchor → flatten + re-seed opposite
- [ ] Priority: success > failure > add (checked on every bar)
- [ ] Adds at successive multiples from frozen anchor: -1×AD, -2×AD, -3×AD
- [ ] MaxAdds=0: no adds, just success/failure exits. Position always 1.
- [ ] exit_type logged for every cycle: SUCCESS, FAILURE, or SESSION_END
- [ ] progress_hwm computed and logged (max favorable progress as % of StepDist)
- [ ] time_between_adds logged for multi-add cycles
- [ ] cycle_day_seq logged (1-based per day)
- [ ] cycle_start_hour logged (integer 9-15)
- [ ] progress_at_adds logged (% of StepDist at each add, comma-separated)
- [ ] prev_cycle_exit_type logged (SUCCESS/FAILURE/SESSION_START)
- [ ] cycle_waste_pct logged (total absolute movement / net displacement)
- [ ] Incomplete cycles logged with exit_type=SESSION_END + progress_hwm
- [ ] Cost model: same per-side per-contract as V1.1 sweep
- [ ] Asymmetric PnL verified: success PnL > abs(failure PnL) when adds present
- [ ] Unit tests pass for all 9 test cases
- [ ] V1.1 comparison: cycle count in same ballpark as A_SD25 (4,856)
- [ ] Fractal completion validation: success rate by add count computed and compared to 79.7%/64.1%/56.0%
- [ ] Comparison table included in verification_report.md
- [ ] All files saved to `stages/04-backtest/rotational/`
