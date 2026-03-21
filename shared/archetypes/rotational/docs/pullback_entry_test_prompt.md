# Pullback Entry Test: Fractal-Aligned Entry on Frozen Anchor

## OBJECTIVE

Add a CONFIRMING state to the frozen-anchor simulator that waits for a child-scale pullback before entering. Test whether this pullback entry captures the 80% fractal completion edge that the immediate entry misses. Compare directly against the existing frozen-anchor immediate-entry results.

⚠️ **This modifies the frozen-anchor simulator, not V1.1. The frozen anchor, symmetric failure exit, and all logging infrastructure remain unchanged. The only change is WHEN the entry occurs — after a confirmed pullback instead of immediately on direction detection.**

---

## WHY THIS CHANGE

The frozen-anchor sweep showed success rates that exactly match the random-walk first-passage formula:

| RT | Strategy SR | Random Walk Prediction | Delta |
|----|------------|----------------------|-------|
| 1.0 | 49.4% | 50.0% | -0.6pp |
| 0.8 | 55.6% | 55.6% | 0.0pp |
| 0.7 | 59.2% | 58.8% | +0.4pp |
| 0.6 | 62.0% | 62.5% | -0.5pp |
| 0.5 | 66.8% | 66.7% | +0.1pp |

The strategy extracts ZERO directional edge from the entry point. It's a pure random walk from the moment of entry.

The fractal data says 80% completion after a pullback. But 80% is a CONDITIONAL probability — given that a move has pulled back and is resuming. The current entry happens BEFORE the pullback, at an unconditional point where the market is a coin flip.

📌 **The fractal edge lives in the pullback, not in the direction detection. This test enters WHERE the fractal data says the edge is: after the first child-scale retracement confirms the parent move is real.**

---

## STATE MACHINE MODIFICATION

### Current Flow (Immediate Entry)
```
WATCHING → price moves ≥ SD from WatchPrice → ENTER → POSITIONED
```

### New Flow (Pullback Entry)
```
WATCHING → price moves ≥ SD from WatchPrice → CONFIRMING (no position)
CONFIRMING → track HWM → price pulls back ≥ AddDist from HWM → ENTER → POSITIONED
```

### CONFIRMING State Details

On entering CONFIRMING:
- Direction = direction of the move (LONG if price went up SD from watch)
- HWM = current price (the price that triggered direction detection)
- ConfirmAnchor = WatchPrice (kept for reference, not used for trading)
- **No position is opened. No cost incurred.**

On each bar in CONFIRMING:
1. Update HWM if price extends further in the direction of the move
2. Check if price has pulled back ≥ AddDist from HWM (against the detected direction)
3. If pullback detected → ENTER:
   - Enter 1 contract in the detected direction at current price
   - AnchorPrice = current price (this is the FROZEN anchor for the cycle)
   - Transition to POSITIONED (same state machine as before)

⚠️ **The anchor is set at the pullback entry price, NOT at the original direction detection price. This is critical — the fractal edge is measured from the pullback point, and the success/failure boundaries must be relative to where the actual entry occurs.**

📌 **HWM only moves in the favorable direction. If direction is LONG, HWM = max(HWM, current_high). If price pulls back then resumes without reaching AddDist, HWM continues tracking. The pullback threshold is always measured from the highest point reached.**

### CONFIRMING State Exits (Besides Pullback Entry)

**Session end while CONFIRMING:** Log as a "missed entry" — direction was detected but pullback never occurred before 16:15. No position, no PnL, no cost. Record in a separate log.

**Direction invalidation:** If price moves ≥ StepDist AGAINST the detected direction from HWM (erasing the original move entirely), the direction signal is dead. Options:

⚠️ **For this test, use the simplest approach: if price drops back to WatchPrice level while in CONFIRMING, cancel the direction signal and return to WATCHING. This prevents entering a pullback on a move that has fully reversed. The invalidation threshold = price returns to within AddDist of WatchPrice in the wrong direction.**

### POSITIONED State

Identical to existing frozen anchor:
- Priority 1: SUCCESS at +RT×SD from AnchorPrice (the pullback entry price)
- Priority 2: FAILURE at -SD from AnchorPrice
- Priority 3: ADD at successive multiples of AddDist from AnchorPrice

📌 **Everything downstream of entry is UNCHANGED. The only difference is WHERE and WHEN the entry occurs. All exit logic, add logic, cost model, and logging work exactly as before.**

### POST-EXIT RE-ENTRY (3 Options — All Tested)

After a SUCCESS or FAILURE exit during the session, the strategy must decide how to re-enter. This test runs all three options to separate the entry effect from the re-entry effect:

**Option A — Full Re-Watch:** Return to WATCHING. Require a full StepDist directional move from the exit price, THEN a pullback of AddDist from the new HWM, THEN enter. Strategy goes completely flat between cycles. Fewest trades per day. Tests: does the full re-confirmation process improve quality enough to justify missing many cycles?

**Option B — Confirm Only:** Enter CONFIRMING with direction = opposite of exited cycle, HWM = exit price. Skip directional detection (the exit already signals reversal). Wait for price to first extend ≥ AddDist in the new direction (updating HWM), THEN pull back ≥ AddDist from the new HWM, THEN enter. Strategy goes flat briefly. Tests: does just the pullback confirmation (without full directional re-detection) capture the edge?

⚠️ **Option B requires a minimum extension of AddDist before pullback detection activates. Without this, after a SUCCESS exit at the high/low of the move, the pullback detector fires immediately on any adverse bounce — entering at a terrible price with no directional confirmation. The extension requirement ensures the new direction is real before looking for a pullback.**

**Option C — Pullback Seed Only:** Pullback entry for the FIRST trade of the day only. After SUCCESS/FAILURE exits, immediate re-seed opposite (same as frozen-anchor baseline). Tests: is the edge purely in the seed quality, or does post-exit behavior matter?

⚠️ **All 3 options use pullback entry for the initial start-of-day seed. They differ ONLY in post-exit behavior. If Option C shows the same SR improvement as A/B, the edge is in the seed and we don't need to change mid-session behavior. If only A/B show improvement, the re-confirmation between cycles matters.**

**Invalidation rules:**
- Option A: if price moves ≥ StepDist in the wrong direction from WATCHING anchor, stay in WATCHING (standard seed invalidation)
- Option B: if price moves ≥ StepDist in the SAME direction as the exited cycle from exit point (reversal didn't materialize), cancel and return to WATCHING for full re-detection
- Option C: no invalidation needed (immediate re-seed, same as current)

📌 **The post-exit CONFIRMING state (Option B) skips directional detection — the exit already signals reversal. It ONLY waits for the pullback confirmation. This is faster than Option A but still requires the fractal entry signal before committing capital.**

---

## PER-ENTRY LOGGING (New Columns)

In addition to all existing cycle columns, add:

**entry_type:** `IMMEDIATE` or `PULLBACK` — which entry method produced this cycle. For this test, all will be PULLBACK. The column exists for future comparison runs.

**direction_detect_time:** Timestamp when direction was first detected (CONFIRMING state entered). Combined with start_time (when entry occurred), the gap shows how long the strategy waited for the pullback.

**confirming_duration_bars:** Bar count from direction detection to pullback entry. Short = quick pullback (healthy rotation). Long = extended wait (price ran far before pulling back).

**hwm_at_entry:** The highest favorable price reached before the pullback. Measured as points above the WatchPrice for LONG, below for SHORT. Shows how far the move extended before retracing.

**pullback_depth_pct:** The pullback from HWM as percentage of the extension from WatchPrice. Formula: AddDist / (HWM - WatchPrice) × 100 for LONG. Values near 100% mean the pullback nearly erased the move. Values near 20-30% mean a shallow, healthy retracement.

⚠️ **pullback_depth_pct is the closest proxy for fractal retracement quality. The fractal data measures child retracements as a fraction of parent progress. Shallow pullbacks (20-40%) should have higher completion rates than deep ones (70-90%). If this is confirmed, pullback_depth_pct becomes a potential entry filter.**

**runaway_flag:** Boolean. If direction was detected but the entry occurs with HWM far beyond AddDist (price ran very far before pulling back), the entry is on a deep retracement of an extended move — structurally different from a shallow pullback. Flag cycles where hwm_at_entry > 2 × StepDist (the move doubled before pulling back).

**remaining_to_parent_target:** Distance in points from the pullback entry price to the original parent threshold (WatchPrice + StepDist for LONG, WatchPrice - StepDist for SHORT). This measures how much of the parent move is "left" from where the entry actually occurs. The fractal data predicts ~80% completion of the parent move after a pullback — but completion is measured to the parent threshold, not to the strategy's success target (which is RT×SD from entry). If remaining_to_parent_target is typically 5-10 points but the strategy targets 32 points (RT=0.8×SD=40), we're asking for 3-6× more than the fractal completion guarantees.

⚠️ **For post-exit re-entries (Options A and B), the "parent target" is less clearly defined since there's no WatchPrice. For these cycles, set remaining_to_parent_target = NULL. The column is most meaningful for the first cycle of the day (cycle_day_seq=1) where WatchPrice is well-defined.**

---

## MISSED ENTRY LOGGING

⚠️ **This is as important as the cycle logs. Missed entries are the COST of waiting for the pullback.**

Create a separate log: `{config_id}_missed.csv`

For each direction detection that does NOT result in an entry — both start-of-day seeds and post-exit CONFIRMING periods that end without entering:

- config_id, date, direction_detect_time, direction
- hwm_reached (how far price extended before session end / invalidation)
- exit_reason: `SESSION_END` or `INVALIDATED`
- hypothetical_immediate_pnl: what would the PnL have been with immediate entry at direction detection price, exiting at session end? (Mark to market at 16:15 or invalidation point)

📌 **If the strategy misses 30% of trading days because the pullback never comes, and those missed days would have been profitable with immediate entry, then the pullback entry is filtering OUT the best trades. The hypothetical_immediate_pnl tells us exactly what we're giving up by waiting.**

Add to config_summary.csv:
- `missed_entries`: count of direction detections that didn't result in entries
- `missed_pct`: missed_entries / (cycle_count + missed_entries) — what fraction of opportunities are skipped
- `missed_hypothetical_pnl`: sum of hypothetical_immediate_pnl from missed entries

---

## COST MODEL

Same as frozen anchor:
- ENTRY: cost_ticks × 1 (no cost during CONFIRMING — only on actual entry)
- ADD: cost_ticks × 1
- SUCCESS EXIT: cost_ticks × (exit_contracts + 1)
- FAILURE EXIT: cost_ticks × (exit_contracts + 1)

📌 **Waiting in CONFIRMING costs nothing in transaction fees. The only cost is opportunity — captured by the missed entry log.**

---

## TEST CONFIGS

Run 9 configs — 3 parameter sets × 3 re-entry options:

**Option A (Full Re-Watch):** After exit, return to WATCHING. Require full StepDist directional move + pullback before re-entering. Strategy goes flat between cycles. Fewest trades.

**Option B (Confirm Only):** After exit, enter CONFIRMING with direction = opposite, HWM = exit price. Skip directional detection, just wait for pullback. Strategy goes flat briefly.

**Option C (Pullback Seed Only):** Pullback entry for the FIRST trade of the day only. After exits, immediate re-seed opposite (same as current frozen anchor). Tests seed quality in isolation.

⚠️ **All 3 options use pullback entry for the initial seed. They differ ONLY in what happens after a SUCCESS or FAILURE exit mid-session.**

### Config Grid

```python
configs = []

for sd, ad, rt, label in [
    (40.0, 16.0, 0.8, "SD40_RT80"),    # Best frozen-anchor config
    (35.0, 14.0, 1.0, "SD35_RT100"),    # Marginal positive config
    (25.0, 10.0, 0.8, "SD25_RT80"),     # Negative config — can pullback rescue it?
]:
    for option in ["A", "B", "C"]:
        configs.append(FrozenAnchorConfig(
            config_id=f"PB_{label}_OPT{option}",
            step_dist=sd,
            add_dist=ad,
            max_adds=0,
            reversal_target=rt,
            cost_ticks=2.0,
            entry_mode="pullback",
            reentry_mode=option,  # "A" = full rewatch, "B" = confirm only, "C" = immediate reseed
        ))
```

📌 **MaxAdds=0 for all 9 configs. Isolate the entry effect first. If pullback entry shows an edge, adds can be tested in a follow-up.**

⚠️ **If the config schema doesn't support `reentry_mode` as a field, implement it as a parameter to `run_frozen_anchor_simulation()` instead. The key is that all 3 options run through the same simulator with the same exit logic — only the post-exit transition differs.**

---

## COMPARISON TABLE (Primary Output)

Produce this table comparing all 3 options against immediate entry (from frozen-anchor sweep):

| Config | Option | SR | RW Pred | Delta | Cycles | Gross PnL | Adj Net | Missed | Missed% |
|--------|--------|-----|---------|-------|--------|----------|---------|--------|---------|
| SD40_RT80 | Immediate | 58.8% | 55.6% | +3.2pp | 2,389 | +22,529 | +12,420 | n/a | n/a |
| SD40_RT80 | A (rewatch) | ?% | 55.6% | ? | ? | ? | ? | ? | ?% |
| SD40_RT80 | B (confirm) | ?% | 55.6% | ? | ? | ? | ? | ? | ?% |
| SD40_RT80 | C (seed only) | ?% | 55.6% | ? | ? | ? | ? | ? | ?% |
| SD35_RT100 | Immediate | 51.6% | 50.0% | +1.6pp | 2,397 | +10,520 | +1,496 | n/a | n/a |
| SD35_RT100 | A | ?% | 50.0% | ? | ? | ? | ? | ? | ?% |
| SD35_RT100 | B | ?% | 50.0% | ? | ? | ? | ? | ? | ?% |
| SD35_RT100 | C | ?% | 50.0% | ? | ? | ? | ? | ? | ?% |
| SD25_RT80 | Immediate | 55.6% | 55.6% | +0.0pp | 6,019 | +587 | -23,738 | n/a | n/a |
| SD25_RT80 | A | ?% | 55.6% | ? | ? | ? | ? | ? | ?% |
| SD25_RT80 | B | ?% | 55.6% | ? | ? | ? | ? | ? | ?% |
| SD25_RT80 | C | ?% | 55.6% | ? | ? | ? | ? | ? | ?% |

📌 **Expect significantly fewer cycles than immediate entry for Options A and B. Option A (full rewatch) will have the fewest cycles — potentially 1-3 per day. Option B (confirm only) will have more. Option C (pullback seed only) should have similar cycle counts to immediate entry since only the first trade changes.**

⚠️ **The "Delta" column (SR minus random-walk prediction) is the fractal edge measurement. If Options A/B show Delta > +10pp consistently, the pullback entry is capturing structural edge. If Delta ≈ 0 for all options, the market is random from the pullback point too.**

### Random Walk Predictions for Reference

With pullback entry, the boundaries are: Success = +RT×SD from entry. Failure = -SD from entry. Random walk prediction = SD / (RT×SD + SD).

- RT=0.8: 1/1.8 = 55.6%
- RT=1.0: 1/2.0 = 50.0%

---

## ALSO REPORT

For all 9 configs:

1. **Fractal-aligned completion rate:** For cycles where remaining_to_parent_target is not NULL (first cycles of day), what percentage reached the parent target level (WatchPrice + StepDist)? This is directly comparable to the 80% fractal prediction and doesn't depend on the strategy's RT setting. Compute from cycle logs: did price ever reach anchor + remaining_to_parent_target during the cycle? Report per option.

2. **Pullback depth distribution:** Histogram of pullback_depth_pct across all entries. Are entries mostly shallow (30-40%) or deep (70-80%)?

3. **Success rate by pullback depth:** Bucket pullback_depth_pct into quartiles. Does shallow pullback → higher SR?

4. **Confirming duration distribution:** How long does the strategy wait? Median bars in CONFIRMING. Distribution of waits.

5. **Success rate by confirming duration:** Do quick pullbacks (< median bars) succeed more than slow ones?

6. **Failure cascade comparison:** Is failure_after_failure rate lower with pullback entry vs immediate? Compare across all 3 options.

7. **Option comparison summary:** For each SD/RT pair, which option (A/B/C) has the best adjusted net PnL? Which has the highest SR? Which has the fewest cascading failures? Is one option consistently better or does it vary by scale?

---

## OUTPUT

Save to: `C:\Projects\pipeline\stages\04-backtest\rotational\pullback_test\`

```
pullback_test/
├── config_summary.csv          # 9 rows + all metrics + missed entry stats
├── cycle_logs/                 # 9 cycle CSVs + 9 incomplete CSVs
├── missed_entries/             # 9 missed entry CSVs
├── comparison_table.md         # Side-by-side vs immediate entry
└── pullback_analysis.md        # Depth distribution, duration, SR by depth
```

---

## SELF-CHECK BEFORE FINISHING

- [ ] CONFIRMING state added: no position opened until pullback occurs
- [ ] Anchor set at pullback entry price, NOT at direction detection price
- [ ] HWM tracks in favorable direction only
- [ ] Invalidation: return to WATCHING if direction signal invalidated
- [ ] Session end in CONFIRMING: logged as missed entry, not incomplete cycle
- [ ] All existing exit/add/cost logic unchanged (operates on POSITIONED state)
- [ ] Option A implemented: post-exit → WATCHING → full seed + pullback
- [ ] Option B implemented: post-exit → CONFIRMING with dir=opposite, HWM=exit price, requires AddDist extension before pullback detection activates
- [ ] Option C implemented: post-exit → immediate re-seed (pullback for first seed only)
- [ ] entry_type, direction_detect_time, confirming_duration_bars logged
- [ ] hwm_at_entry, pullback_depth_pct, runaway_flag logged
- [ ] remaining_to_parent_target logged (NULL for post-exit re-entries)
- [ ] Missed entries logged separately with hypothetical immediate PnL
- [ ] config_summary has missed_entries, missed_pct, missed_hypothetical_pnl
- [ ] 9 configs run: 3 SD/RT pairs × 3 options (A/B/C)
- [ ] Option A: post-exit returns to WATCHING (full re-watch)
- [ ] Option B: post-exit enters CONFIRMING with direction=opposite (confirm only)
- [ ] Option C: post-exit does immediate re-seed, pullback entry for first seed only
- [ ] Comparison table produced with random-walk predictions and Delta column
- [ ] Fractal-aligned completion rate computed (cycles reaching parent target)
- [ ] SR by pullback depth analysis produced
- [ ] Option comparison summary produced
- [ ] All files saved to `pullback_test/`
