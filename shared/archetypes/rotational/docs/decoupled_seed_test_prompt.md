# Decoupled Seed Test: Small Detection, Large Target

## OBJECTIVE

Test whether separating the detection scale (SeedDist) from the trading scale (StepDist) preserves enough parent displacement at entry for the fractal edge to translate into strategy performance. The pullback test showed that with SeedDist=StepDist=40, only 3.5pts of parent move remains at entry — the detection consumes the move. A smaller SeedDist should preserve 20-30pts of remaining displacement, placing the strategy target within the fractal structure's coverage.

⚠️ **This modifies the frozen-anchor simulator to accept a new `seed_dist` parameter. Only the WATCHING state detection threshold changes. Everything else — CONFIRMING, POSITIONED, exits, adds, costs, logging — remains identical to the pullback test.**

---

## THE CORE INSIGHT

The fractal data shows 80-90% completion of parent moves after a child pullback. The pullback test confirmed this: 92.1% of first cycles reached the parent target. But the parent target was only 3.5pts away because the detection move consumed the parent move.

| Detection Scale | Entry Point | Remaining to Parent | Strategy Needs (RT=0.8) | Covered? |
|----------------|-------------|--------------------|-----------------------|----------|
| SeedDist=40 | Late in move | ~3.5 pts | 32 pts | No — 11.6× gap |
| SeedDist=15 | Mid-move | ~21 pts | 32 pts | Partially — 1.5× gap |
| SeedDist=10 | Early in move | ~26 pts | 32 pts | Mostly — 1.2× gap |

📌 **The fractal edge is real and confirmed. The strategy just enters too late to capture it. Smaller SeedDist = earlier entry = more of the fractal-predicted move available to trade.**

---

## STATE MACHINE MODIFICATION

### WATCHING State (Only Change)

Current: direction confirmed when price moves ≥ **step_dist** from WatchPrice.
New: direction confirmed when price moves ≥ **seed_dist** from WatchPrice.

```
WATCHING → price moves ≥ seed_dist from WatchPrice → CONFIRMING
CONFIRMING → HWM tracking → pullback ≥ add_dist from HWM → ENTER → POSITIONED
```

⚠️ **Only the detection threshold changes. The CONFIRMING pullback logic, POSITIONED exit/add logic, and all boundaries (success at +RT×step_dist, failure at -step_dist from anchor) use step_dist, NOT seed_dist. SeedDist is consumed during detection and never used again.**

### CONFIRMING State (Unchanged)

Same as pullback test:
- HWM tracks in favorable direction only
- Pullback entry at AddDist from HWM
- Anchor set at pullback entry price

📌 **CONFIRMING invalidation rules unchanged from pullback test: return to WATCHING if price returns to within AddDist of WatchPrice in the wrong direction. With SeedDist=10, WatchPrice is only 10pts from detection — invalidation is tighter, which is correct (a 10pt move that fully reverses was noise, not signal).**

### POSITIONED State (Unchanged)

Same priorities:
- Priority 1: SUCCESS at +RT×step_dist from anchor
- Priority 2: FAILURE at -step_dist from anchor
- Priority 3: ADD at multiples of add_dist from anchor (MaxAdds=0 for this test)

### Post-Exit Re-Entry

⚠️ **Option C only (pullback seed for first trade, immediate re-seed after exits). The pullback test showed Options A/B destroy value.**

After exits mid-session, the immediate re-seed enters 1 contract opposite at the exit price. The new anchor = exit price. The new cycle's success/failure boundaries use step_dist from that anchor. SeedDist is ONLY used for the start-of-day WATCHING → CONFIRMING transition.

📌 **SeedDist applies to the first trade of the day ONLY. All subsequent re-seeds after exits use the standard frozen-anchor immediate re-entry (enter opposite at exit price, anchor = exit price). This is identical to Option C from the pullback test.**

---

## ADDDIST SCALING

AddDist is set to 40% of SeedDist (not StepDist) for the pullback confirmation:

| SeedDist | AddDist | Ratio |
|----------|---------|-------|
| 10 | 4.0 | 0.4 |
| 15 | 6.0 | 0.4 |
| 20 | 8.0 | 0.4 |
| 40 (baseline) | 16.0 | 0.4 |

⚠️ **A 4pt pullback on a 10pt seed is proportionally identical to a 16pt pullback on a 40pt seed — same 40% parent/child ratio. The fractal self-similarity means the same ratio applies at smaller scales. A 4pt NQ pullback is not noise — the fractal analysis confirmed structural self-similarity down to the 3pt threshold. Do NOT increase AddDist because it "seems small."**

---

## LOGGING

All existing columns from the pullback test carry forward. One additional column:

**remaining_to_parent_target:** Same definition as pullback test, but now the values should be MUCH larger. With SeedDist=10, entry occurs ~14pts into a 40pt parent move, leaving ~26pts. With SeedDist=40, entry occurs ~36.5pts in, leaving ~3.5pts. This column directly measures whether the decoupled seed preserves the parent displacement.

📌 **For first cycles (cycle_day_seq=1), remaining_to_parent_target = (WatchPrice + step_dist) - entry_price for LONG. For later cycles (immediate re-seed), set to NULL as before.**

All other columns unchanged: exit_type, progress_hwm, confirming_duration_bars, hwm_at_entry, pullback_depth_pct, runaway_flag, cycle_day_seq, cycle_start_hour, prev_cycle_exit_type, cycle_waste_pct, time_between_adds, progress_at_adds.

---

## TEST CONFIGS

9 configs: 3 SeedDist values × 2 RT values, plus 2 baselines and 1 scale-transfer test.

```python
configs = []

# SeedDist sweep at SD=40
for seed_dist in [10, 15, 20]:
    for rt in [0.8, 1.0]:
        ad = round(seed_dist * 0.4, 1)
        configs.append(FrozenAnchorConfig(
            config_id=f"DS_SD40_SEED{seed_dist}_AD{int(ad)}_RT{int(rt*100)}",
            step_dist=40.0,
            seed_dist=seed_dist,
            add_dist=ad,
            max_adds=0,
            reversal_target=rt,
            cost_ticks=2.0,
            entry_mode="pullback",
            reentry_mode="C",
        ))
```

📌 **Baseline configs below use SeedDist=40 (same as pullback test Option C) for direct comparison.**

```python
# Baselines: SeedDist = StepDist (current behavior)
for rt in [0.8, 1.0]:
    configs.append(FrozenAnchorConfig(
        config_id=f"DS_SD40_SEED40_AD16_RT{int(rt*100)}",
        step_dist=40.0,
        seed_dist=40.0,
        add_dist=16.0,
        max_adds=0,
        reversal_target=rt,
        cost_ticks=2.0,
        entry_mode="pullback",
        reentry_mode="C",
    ))

# Scale transfer: does it work at SD=25?
configs.append(FrozenAnchorConfig(
    config_id="DS_SD25_SEED10_AD4_RT80",
    step_dist=25.0,
    seed_dist=10.0,
    add_dist=4.0,
    max_adds=0,
    reversal_target=0.8,
    cost_ticks=2.0,
    entry_mode="pullback",
    reentry_mode="C",
))

print(f"Total: {len(configs)}")  # Should be 9
```

⚠️ **MaxAdds=0 for all configs. Isolating the SeedDist effect. Adds tested separately if this shows an edge.**

---

## COMPARISON TABLE (Primary Output)

| SeedDist | SD | RT | First-Cycle SR | RW Pred | Delta | Med Remaining | Cycles | Adj Net |
|----------|-----|-----|---------------|---------|-------|--------------|--------|---------|
| 40 (base) | 40 | 0.8 | ? | 55.6% | ? | ? pts | ? | ? |
| 20 | 40 | 0.8 | ? | 55.6% | ? | ? pts | ? | ? |
| 15 | 40 | 0.8 | ? | 55.6% | ? | ? pts | ? | ? |
| 10 | 40 | 0.8 | ? | 55.6% | ? | ? pts | ? | ? |
| 40 (base) | 40 | 1.0 | ? | 50.0% | ? | ? pts | ? | ? |
| 20 | 40 | 1.0 | ? | 50.0% | ? | ? pts | ? | ? |
| 15 | 40 | 1.0 | ? | 50.0% | ? | ? pts | ? | ? |
| 10 | 40 | 1.0 | ? | 50.0% | ? | ? pts | ? | ? |
| 10 | 25 | 0.8 | ? | 55.6% | ? | ? pts | ? | ? |

⚠️ **The prediction: as SeedDist decreases, Med Remaining increases and Delta (SR above random walk) should increase proportionally. If Delta stays flat regardless of remaining displacement, the fractal edge doesn't translate to strategy SR even with proper alignment.**

📌 **Also report later-cycle SR. Later cycles use immediate re-seed (SeedDist irrelevant). If later-cycle SR is ~55.6% across all configs, that confirms the SeedDist effect is specific to the first cycle — the informational content is in the detection move, not in any downstream mechanic.**

---

## ALSO REPORT

1. **Remaining displacement correlation:** Scatter or table of remaining_to_parent_target vs success rate for first cycles across all SeedDist values. Does more remaining displacement = higher SR?

2. **Fractal-aligned completion rate by SeedDist:** For first cycles, what % reached the parent target (WatchPrice + StepDist)? Should increase as SeedDist decreases (more room to reach target).

3. **Pullback depth distribution by SeedDist:** Does the depth distribution shift with smaller seeds? Smaller AddDist may produce shallower pullbacks.

4. **Cycle count comparison:** Smaller SeedDist fires more frequently (10pt moves happen more often than 40pt moves). Does more frequent detection = more total cycles? Or does the pullback filter keep counts similar?

---

## OUTPUT

Save to: `C:\Projects\pipeline\stages\04-backtest\rotational\decoupled_seed_test\`

```
decoupled_seed_test/
├── config_summary.csv          # 9 rows
├── cycle_logs/                 # 9 cycle CSVs + 9 incomplete CSVs
├── missed_entries/             # 9 missed entry CSVs
├── comparison_table.md         # SeedDist comparison
└── decoupled_seed_analysis.md  # Correlation, completion, depth analysis
```

---

## SELF-CHECK BEFORE FINISHING

- [ ] seed_dist parameter added to config and WATCHING state
- [ ] WATCHING detects direction at seed_dist (not step_dist)
- [ ] CONFIRMING, POSITIONED, exits all use step_dist (not seed_dist)
- [ ] seed_dist used ONLY for first-trade-of-day detection
- [ ] Post-exit re-entry: immediate re-seed (Option C), no seed_dist involvement
- [ ] CONFIRMING invalidation: return to WATCHING if price returns to within AddDist of WatchPrice
- [ ] AddDist = 40% of seed_dist (not step_dist) for pullback confirmation
- [ ] remaining_to_parent_target logged for first cycles
- [ ] All other logging columns carried forward from pullback test
- [ ] 9 configs: 3 SeedDist × 2 RT + 2 baselines + 1 scale transfer
- [ ] MaxAdds=0 for all configs
- [ ] Comparison table with Delta vs random walk for each config
- [ ] Fractal-aligned completion rate reported by SeedDist
- [ ] Later-cycle SR reported separately from first-cycle SR
- [ ] All files saved to `decoupled_seed_test/`
