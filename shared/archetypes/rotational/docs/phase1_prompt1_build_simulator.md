# Phase 1, Prompt 1: Build Multi-Approach Rotation Simulator

## OBJECTIVE

Extend the Phase 0 calibrated Python simulator to support four approach variants (A-D) via a unified configuration object. Add per-cycle regime context tagging and shadow metrics. The deliverable is a tested simulator module that accepts any config and produces an enriched cycle log.

⚠️ **Start from the Phase 0 calibrated simulator. Do NOT rewrite from scratch. The calibration guarantee depends on the existing code being preserved. Extend, don't replace.**

---

## PREREQUISITE

Phase 0 must have PASSED. The calibrated simulator should be at:
`C:\Projects\pipeline\stages\01-data\analysis\calibration_v1_1\`

Confirm the simulator file exists and note its filename before proceeding.

---

## DELIVERABLES

1. `rotation_simulator.py` — unified simulator module supporting Approaches A-D
2. `config_schema.py` — configuration dataclass/dict definition
3. `context_tagger.py` — regime context computation (ATR, swing stats, directional persistence)
4. Verification output confirming Phase 0 calibration still passes after refactoring

**Save to:** `C:\Projects\pipeline\stages\04-backtest\rotational\`

📌 **Reminder: This prompt builds the SIMULATOR, not the sweep. The simulator must support all 4 approaches via the config object below. Prompt 2 (separate) will generate the 182 configs and run the sweep. This prompt's success gate is the Phase 0 re-verification at the end.**

---

## CONFIGURATION SCHEMA

Every sweep config is defined by a single object:

```python
@dataclass
class RotationConfig:
    config_id: str              # Unique identifier (e.g., "B_SD25_AD10_MA2")
    approach: str               # "A", "B", "C", "D"
    step_dist: float            # Reversal distance (points)
    add_dist: float = 0.0       # Against-trigger distance (Approach B only)
    confirm_dist: float = 0.0   # Favorable-trigger distance (C, D only)
    max_adds: int = 0           # 0 for Approach A
    add_size: int = 1           # Contracts per add (D can be >1, others always 1)
    ml: int = 1                 # Fixed: flat adds
    iq: int = 1                 # Fixed: initial quantity
    cost_ticks: float = 2.0     # Per-side cost in ticks (sensitivity at 3.0 in Prompt 3)
```

⚠️ **Validation rules on config creation:**
- Approach A: max_adds MUST be 0, add_dist and confirm_dist MUST be 0
- Approach B: add_dist MUST be > 0, confirm_dist MUST be 0
- Approach C: confirm_dist MUST be > 0, add_dist MUST be 0, add_size MUST be 1
- Approach D: confirm_dist MUST be > 0, add_dist MUST be 0, add_size MUST be ≥ 1
- All: step_dist > 0, ml = 1, iq = 1

Raise an error if any config violates these rules. Do not silently ignore.

---

## STATE MACHINE MODIFICATIONS BY APPROACH

The Phase 0 simulator implements V1.1: SEED → ADD (against) → REVERSAL. Each approach modifies this differently.

### Base Logic (Shared by All)

**SEED:** Identical to V1.1. Two-phase directional seed. Watch price → wait for StepDist move → seed in that direction. AnchorPrice = price, Level = 0.

**REVERSAL:** Price moves ≥ StepDist IN FAVOR from AnchorPrice → flatten all, enter 1 opposite. AnchorPrice = price, Level = 0.

📌 **SEED and REVERSAL are the same across all approaches. Only the ADD/against behavior differs. When implementing, keep SEED and REVERSAL as shared code and branch only on the add logic.**

### Approach A: Pure Rotation

- When price moves ≥ StepDist AGAINST from anchor: **fire a REVERSAL** (not an add)
- Flatten all, enter 1 opposite direction, AnchorPrice = price
- This means both in-favor AND against moves of ≥ StepDist trigger reversals
- Position is always exactly 1 contract
- No add logic runs. MaxAdds = 0.

### Approach B: Traditional Martingale

- When price moves ≥ **AddDist** AGAINST from anchor: fire an ADD
- AddDist may differ from StepDist (this is the decoupled innovation)
- Add 1 contract (ML=1, always size 1) in same direction
- AnchorPrice = price on every add (anchor walks — standard V1.1)
- Level increments and resets per V1.1 ML logic
- If add_count >= max_adds: suppress further adds, hold position until reversal

⚠️ **When max_adds is reached: do NOT fire an add. Do NOT fire a reversal. Just hold. The strategy waits for price to move StepDist IN FAVOR from the current anchor to reverse. This is the "frozen position" state. The against-trigger is simply ignored.**

### Approach C: Anti-Martingale

- Adds fire at **successive multiples** of ConfirmDist IN FAVOR from anchor: first add at 1×ConfirmDist, second at 2×ConfirmDist, etc.
- Add 1 contract in same direction (adding into a winner)
- **AnchorPrice does NOT reset on this add** — anchor stays at original seed/reversal entry
- Reversal still triggers at StepDist in favor from ORIGINAL anchor
- When price moves against: no add, just hold (same as B when max_adds exhausted)
- If add_count >= max_adds: suppress further adds

⚠️ **CRITICAL anchor rule for Approach C: the favorable add does NOT move the anchor. If you reset anchor on the favorable add, the reversal distance becomes StepDist from the ADD point (farther from original entry), which breaks the strategy's intended behavior. Only REVERSAL and SEED reset anchor.**

⚠️ **Multiple add spacing: with MaxAdds=2 and ConfirmDist=0.5×StepDist, the first add fires when price is 0.5×SD in favor, the second when price is 1.0×SD in favor (which is right at the reversal point — effectively no second add). With ConfirmDist=0.4×SD, first at 0.4×SD, second at 0.8×SD. Track `next_add_threshold = anchor + (add_count + 1) × ConfirmDist × direction`. Same logic applies to Approach D.**

⚠️ **PRIORITY RULE: If both an add threshold AND the reversal threshold are met on the same bar, the REVERSAL fires and the add is skipped. Reversal ALWAYS takes priority. This applies to ALL approaches — but it only matters in practice for C/D where adds and reversals are on the same side (in-favor).**

### Approach D: Scaled Entry

- Identical to Approach C mechanically — including successive-multiple add spacing
- The only difference: add_size can be > 1 (conviction sizing)
- When price moves ≥ N×ConfirmDist in favor (Nth add): add **add_size** contracts (not just 1)
- Same anchor rule as C: no reset on favorable add

📌 **Approaches C and D share the same code path. The only branch is `add_qty = 1` (C) vs `add_qty = config.add_size` (D). Implement as one path with a size parameter.**

---

## PER-CYCLE CONTEXT TAGGING

For every completed cycle, compute and log these additional columns. These describe what the MARKET was doing at cycle start — they are NOT strategy parameters.

⚠️ **Context tagging requires pre-computed rolling indicators on the bar data. Compute these ONCE before the sweep runs, not inside each config's simulation loop. Store as additional columns on the bar DataFrame.**

### Pre-Compute on Bar Data (Before Any Simulation)

```python
# ATR (20-bar)
bars['atr_20'] = compute_atr(bars, period=20)

# ATR percentile (rank vs trailing 500 bars)
bars['atr_pct'] = bars['atr_20'].rolling(500).apply(
    lambda x: percentileofscore(x[:-1], x.iloc[-1])  # exclude current
)

# Bar range
bars['bar_range'] = bars['High'] - bars['Low']
bars['bar_range_median_20'] = bars['bar_range'].rolling(20).median()
```

### Pre-Compute Zig-Zag Context (Before Any Simulation)

Run a 5pt reversal threshold zig-zag on the bar Close prices. For each bar, store:
- `swing_median_20`: median of last 20 completed swing sizes at that point
- `swing_p90_20`: P90 of last 20 completed swing sizes

Run a 10pt reversal threshold zig-zag on the bar Close prices. For each bar, store:
- `directional_persistence`: count of consecutive swings in the same direction immediately preceding this bar. Count resets when swing direction flips.

⚠️ **These zig-zag computations use FIXED thresholds (5pt and 10pt). They do NOT vary with StepDist. They describe the market state, not the strategy. Use the same numba-accelerated zig-zag from the fractal analysis scripts.**

📌 **Reminder: pre-compute ALL context columns on the bar DataFrame before running any simulation. The simulation loop then just looks up `bars.iloc[start_bar_index]` for each cycle's context — zero additional computation per config.**

### Per-Cycle Log Columns

When a cycle completes (reversal fires), log one row with:

**Standard metrics:**
- config_id, approach, step_dist, add_dist/confirm_dist
- cycle_id, start_time, end_time, duration_bars, duration_minutes
- side (LONG/SHORT), add_count, exit_position
- pnl_ticks_gross, pnl_ticks_net (after cost_ticks applied)
- max_favorable_excursion (MFE): max points in favor during cycle
- max_adverse_excursion (MAE): max points against during cycle

**Regime context (looked up from pre-computed bar data at cycle start bar):**
- atr_20bar, atr_percentile
- swing_median_20, swing_p90_20
- directional_persistence
- bar_range_median_20

**Shadow metrics:**
- would_flatten_reseed: boolean — for Approach B only: did MAE ever exceed 3 × add_dist during this cycle? For Approaches A/C/D: always set to FALSE (these approaches have add_dist=0; do NOT evaluate the condition, just hardcode FALSE).
- half_block_profit: at the first bar where price reaches ≥ 0.5 × StepDist in favor from the **original cycle entry price** (the SEED or REVERSAL_ENTRY price, NOT the walked anchor after adds), snapshot the running PnL (gross) for the current position at that bar's price, then subtract all costs incurred up to that point. If price never reaches 0.5 × StepDist in favor from original entry during the cycle, set to NULL. **For Approach B: this requires tracking the original entry price separately from AnchorPrice, since anchor walks on adds.**

---

## COST MODEL

Apply to every trade action:
- SEED: cost_ticks × contracts
- ADD: cost_ticks × add_qty
- REVERSAL: cost_ticks × (exit_contracts + entry_contracts). The flatten is one side, the re-entry is another — each charged cost_ticks per contract.

⚠️ **cost_ticks is per-side, per-contract. A reversal from 3 long to 1 short = flatten 3 (cost: 3 × cost_ticks) + enter 1 (cost: 1 × cost_ticks) = total 4 × cost_ticks. There is NO 2× multiplier — the two sides are already captured by summing exit + entry contracts. Track cumulative cost per cycle and subtract from gross PnL for net.**

---

## SESSION HANDLING

- RTH only: 09:30–16:15 ET
- Reset simulator state at start of each RTH session (no carry-over from previous day)
- Discard any cycle in progress at 16:15 (incomplete cycle — do not count in results)

📌 **Session reset means: AnchorPrice = 0, WatchPrice = 0, Direction = 0, Level = 0, position = 0. Every day starts fresh with a new directional seed. This is consistent with the fractal analysis session boundary handling.**

---

## VERIFICATION GATE

After refactoring, re-run the simulator with Phase 0 calibration settings **on the same March 20, 2026 RTH bar data used in Phase 0** (NOT on P1 data):

```python
calibration_config = RotationConfig(
    config_id="CALIBRATION",
    approach="B",  # V1.1 is martingale with AddDist = StepDist
    step_dist=25.0,
    add_dist=25.0,
    max_adds=99,   # Effectively unlimited (V1.1 has no cap)
    cost_ticks=0.0  # Phase 0 compared gross
)
# Data: same bar file and time window from Phase 0 (2026-03-20 08:29–16:03)
```

⚠️ **The Phase 0 log used MCS=3 with ML=1. With ML=1, MCS is never hit (add size is always 1). So max_adds=99 (unlimited) with add_size=1 replicates V1.1 behavior. Verify this produces the same 55 complete cycles, same distribution 26/17/6/4/1/1, and PnL within 2% of +2,870.3 ticks on the same RTH day (2026-03-20).**

If verification fails: the refactoring broke something. Diff against the Phase 0 simulator and fix before proceeding.

---

## OUTPUT

Save all files to: `C:\Projects\pipeline\stages\04-backtest\rotational\`

```
rotational/
├── rotation_simulator.py    # Main simulator — accepts RotationConfig, returns cycle log
├── config_schema.py         # RotationConfig dataclass + validation
├── context_tagger.py        # Pre-compute regime context on bar data
├── cycle_logger.py          # Cycle log schema + CSV/DataFrame output
├── verification_report.md   # Phase 0 re-verification results
└── tests/
    └── test_approaches.py   # Unit tests for each approach's add logic
```

### Unit Tests (test_approaches.py)

Write at least one test per approach using synthetic price data:

1. **Approach A:** Price moves +StepDist → reversal. Price moves -StepDist → reversal (not add). Verify position never exceeds 1.
2. **Approach B:** Price moves -AddDist → add fires. Verify add_count increments. Verify add suppressed when max_adds reached. Verify anchor resets on add.
3. **Approach C:** Price moves +ConfirmDist → first add fires. Price continues to +2×ConfirmDist → second add fires (if MaxAdds=2). Verify anchor does NOT reset after either add. Verify reversal fires at StepDist from ORIGINAL anchor. Price moves against → no add. Verify add does NOT fire immediately after first add (successive-multiple spacing enforced). **Priority test:** with ConfirmDist=0.5×StepDist and MaxAdds=2, verify second add does NOT fire — reversal fires instead at StepDist.
4. **Approach D:** Same as C but verify add_qty = add_size (>1).

⚠️ **These tests use synthetic price sequences (e.g., [100, 125, 150, 125, 100, 75]), NOT real bar data. They test state machine logic in isolation. Real data validation is the Phase 0 re-verification above.**

---

## SELF-CHECK BEFORE FINISHING

- [ ] Phase 0 simulator identified and used as starting point (NOT rewritten)
- [ ] RotationConfig dataclass created with validation rules
- [ ] Approach A: against-trigger fires reversal, not add. Position always 1.
- [ ] Approach B: decoupled AddDist. Anchor resets on add. Adds suppressed at max_adds.
- [ ] Approach C: ConfirmDist in-favor add. Anchor does NOT reset on add. Reversal from original anchor. Successive adds at N×ConfirmDist (not all at 1×). Reversal takes priority over add when both thresholds met.
- [ ] Approach D: same as C with add_size > 1 support. Same successive-multiple spacing.
- [ ] Context tagger: ATR, swing stats, directional persistence pre-computed on bar data
- [ ] Context uses FIXED thresholds (5pt, 10pt) — does NOT vary with StepDist
- [ ] Shadow metrics: would_flatten_reseed and half_block_profit logged per cycle
- [ ] Cost model: per-side, per-contract, applied to every trade action
- [ ] Session handling: RTH only, state reset daily, incomplete cycles discarded
- [ ] Phase 0 re-verification: same 55 cycles, same distribution, PnL within 2% (on March 20 data, NOT P1)
- [ ] Unit tests pass for all 4 approaches on synthetic data
- [ ] All files saved to `stages/04-backtest/rotational/`
