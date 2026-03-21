# Phase 0 Re-Verification Report
**Date:** 2026-03-20
**Simulator:** `rotation_simulator.py` (multi-approach, Approach B mode)
**Data:** `NQ_calibration_V1_1_20260320_calibration.csv` (413,170 ticks, 08:27:46-16:04:00)

## Calibration Config

```python
RotationConfig(
    config_id="CALIBRATION",
    approach="B",
    step_dist=25.0,
    add_dist=25.0,      # AddDist = StepDist (V1.1 behavior)
    max_adds=99,         # Effectively unlimited
    cost_ticks=0.0,      # Gross comparison
)
# Additional: strict_trigger=True, initial_watch_price=24469.75
```

## Results

| Metric | C++ Ground Truth | Phase 0 Python | New Simulator | Match |
|--------|-----------------|----------------|---------------|-------|
| Complete cycles | 55 | 55 | **55** | YES |
| Winners | 43 | 43 | **43** | YES |
| Losers | 12 | 12 | **12** | YES |
| Per-unit PnL (ticks) | 2,870.3 | 2,943.8 | **2,943.8** | EXACT vs P0 |
| Delta vs C++ | — | 2.56% | **2.56%** | YES |

## Cycle Distribution (by add count)

| Adds | C++ | Phase 0 Python | New Simulator | Match P0 |
|------|-----|----------------|---------------|----------|
| 0 | 26 | 27 | **27** | YES |
| 1 | 17 | 13 | **13** | YES |
| 2 | 6 | 8 | **8** | YES |
| 3 | 4 | 5 | **5** | YES |
| 4 | 1 | 2 | **2** | YES |
| 6 | 1 | 0 | **0** | YES |

## Verdict: **PASS**

The new multi-approach simulator reproduces Phase 0 Python results exactly:
- Identical cycle count (55)
- Identical win/loss split (43/12)
- Identical per-unit PnL sum (2,943.8 ticks — 0.00% delta)
- Identical cycle distribution (27/13/8/5/2)

The 2.56% delta vs C++ ground truth is inherited from Phase 0's tick-batching
offset (documented in the original calibration report). This is a data-level
artifact, not a simulator logic difference.

## Notes

- **Trigger mode:** Phase 0 calibration uses strict `>` (not `>=`) for
  positioned-state triggers to model SC's tick-batching behavior. The sweep
  will use `>=` (default) as it processes all ticks directly.
- **Per-unit vs qty-weighted PnL:** Phase 0 reports per-unit PnL
  (`(exit - avg_entry) / tick_size`, no qty multiplier). The new simulator
  tracks both: `pnl_ticks_gross` (qty-weighted) and `pnl_ticks_per_unit`.
- **RTH filtering:** Disabled for calibration (entire window = one session).
  Enabled for production sweep (RTH 09:30-16:15, state reset per session).

## Unit Tests

28/28 tests pass covering all 4 approaches:
- Config validation (10 tests)
- Approach A: pure rotation (3 tests)
- Approach B: traditional martingale (4 tests)
- Approach C: anti-martingale (5 tests)
- Approach D: scaled entry (2 tests)
- Cost model (2 tests)
- Shadow metrics (2 tests)

---

# Frozen-Anchor Simulator Verification Report
**Date:** 2026-03-21
**Simulator:** `rotation_simulator.py :: run_frozen_anchor_simulation()`
**Config:** `FrozenAnchorConfig` (new dataclass in `config_schema.py`)

## What Changed from V1.1

| Aspect | V1.1 (Approach B) | Frozen Anchor |
|--------|-------------------|---------------|
| Anchor on adverse add | Walks to add price | **Frozen at seed/re-seed** |
| Failure exit | None (position stuck) | **At -StepDist from anchor** |
| Success exit | At +StepDist from walking anchor | **At +RT×StepDist from frozen anchor** |
| Add direction | Against (B), In-favor (C/D) | **Against only** |
| Add spacing | From walking anchor (B) | **Successive multiples from frozen anchor** |
| Exit classification | None | **SUCCESS / FAILURE / SESSION_END** |

## Core Invariant: Anchor Never Moves on Adds

Verified by `test_anchor_unchanged_after_add`:
- Seed Long at 125 → anchor = 125
- Adverse add at 115 → anchor still 125 (trade log confirms `anchor=125.0`)
- Success exit at 150 → new anchor = 150 (trade log confirms `anchor=150.0`)

## State Machine Priority Order

Verified by `test_failure_beats_add_on_same_bar`:
- SD=40, AD=10, MA=3. Price jumps from -9 to -42 from anchor in one bar
- Both add threshold (-10) and failure threshold (-40) qualify
- **FAILURE fires, add_count stays 0** — priority 2 beats priority 3

## Add Spacing from Frozen Anchor

Verified by `test_adds_at_multiples_from_frozen_anchor`:
- SD=40, AD=10, MA=3. Seed Long at 140.
- Add 1 fires at 130.0 (-10 from anchor 140) — anchor stays 140
- Add 2 fires at 120.0 (-20 from anchor 140) — anchor stays 140
- Add 3 fires at 110.0 (-30 from anchor 140) — anchor stays 140
- Failure at 100.0 (-40 from anchor 140)

All three adds confirmed `anchor=140.0` in trade log.

## Asymmetric PnL Structure

Verified by `test_success_pnl_with_adds` and `test_failure_pnl_with_adds`:

With SD=40, AD=16, MA=2, RT=1.0:

| Scenario | Contract 1 (at anchor) | Contract 2 (at -16) | Contract 3 (at -32) | Total |
|----------|----------------------|---------------------|---------------------|-------|
| **SUCCESS** (exit at anchor+40) | +160 ticks | +224 ticks | +288 ticks | **+672 ticks** |
| **FAILURE** (exit at anchor-40) | -160 ticks | -96 ticks | -32 ticks | **-288 ticks** |

**Win/loss ratio: 672 / 288 = 2.33x**

Test results:
- SUCCESS gross PnL: **672.0 ticks** (matches calculation)
- FAILURE gross PnL: **-288.0 ticks** (matches calculation)
- `test_asymmetry_success_greater_than_failure`: **PASS** — win > abs(loss)

At fractal-predicted 64% completion for 2 retracements:
EV = 0.64 × 672 - 0.36 × 288 = **+326 ticks** per fully-loaded cycle (before costs).

## Cost Model

Verified by `test_failure_exit_cost` and `test_success_exit_cost_no_adds`:

| Scenario | Seed | Adds | Flatten | Re-seed | Total (at 2t/side) |
|----------|------|------|---------|---------|-------------------|
| SUCCESS, 0 adds (1 contract) | 2 | 0 | 2 | 2 | **6 ticks** |
| FAILURE, 2 adds (3 contracts) | 2 | 4 | 6 | 2 | **14 ticks** |

Both tests confirm `gross - net` matches expected cost exactly.

Re-seed cost is charged to the **closing** cycle, not the new one. New cycle starts with `cumulative_cost = 0`.

## ReversalTarget < 1.0

Verified by `test_success_at_rt_times_sd`:
- RT=0.7, SD=40 → success fires at +28 from anchor (not +40)
- Gross PnL ≈ 112 ticks (28pts / 0.25 tick_size × 1 contract)
- **PASS**: PnL within 4 ticks of expected 112.0

## Diagnostic Columns

### exit_type
- `test_failure_exit_at_minus_step_dist`: FAILURE confirmed
- `test_success_exit_at_plus_rt_sd`: SUCCESS confirmed
- `test_session_end_incomplete`: SESSION_END in incomplete cycles confirmed

### progress_hwm
- `test_progress_hwm_on_failure`: Price reached 80% of target (20/25 pts), then failed
- Recorded `progress_hwm ≈ 80.0` — **PASS**

### cycle_day_seq
- `test_day_seq_resets_each_day`: Multi-day run, seq=1 appears at least once per day
- Seq increments within day — **PASS**

### cycle_start_hour
- `test_start_hour_captured`: Cycle starting at 09:30:50 records `cycle_start_hour = 9`
- **PASS**

### prev_cycle_exit_type
- `test_first_cycle_is_session_start`: First cycle records `SESSION_START` — **PASS**
- `test_second_cycle_inherits_prev`: Second cycle's `prev_cycle_exit_type` matches first cycle's `exit_type` — **PASS**

### MaxAdds=0 (Pure Rotation)
- `test_no_adds_only_exits`: Position always 1, add_count always 0, no ADD trades
- First cycle SUCCESS, second FAILURE — **PASS**

## V1.1 Regression Check

Original V1.1 test suite (`test_approaches.py`): **28/28 PASS**

The original `run_simulation()` function was not modified. The frozen-anchor logic is a new function `run_frozen_anchor_simulation()` added below it. No V1.1 behavior was altered.

## Frozen-Anchor Unit Tests: 25/25 PASS

| Category | Tests | Status |
|----------|-------|--------|
| FrozenAnchorConfig validation | 7 | PASS |
| Frozen anchor invariant | 1 | PASS |
| Failure exit | 1 | PASS |
| Success exit | 1 | PASS |
| Priority order (failure > add) | 1 | PASS |
| Add spacing from frozen anchor | 1 | PASS |
| MaxAdds=0 pure rotation | 1 | PASS |
| ReversalTarget < 1.0 | 1 | PASS |
| progress_hwm | 1 | PASS |
| cycle_day_seq | 1 | PASS |
| Asymmetric PnL (3 scenarios) | 3 | PASS |
| Cost model (2 scenarios) | 2 | PASS |
| prev_cycle_exit_type | 2 | PASS |
| cycle_start_hour | 1 | PASS |
| Incomplete cycles / SESSION_END | 1 | PASS |
| **Total** | **25** | **ALL PASS** |

## Self-Check

- [x] AnchorPrice set once at seed/re-seed, NEVER changes on adds
- [x] Failure exit at -StepDist from frozen anchor → flatten + re-seed opposite
- [x] Success exit at +ReversalTarget×StepDist from anchor → flatten + re-seed opposite
- [x] Priority: success > failure > add (checked on every bar)
- [x] Adds at successive multiples from frozen anchor: -1×AD, -2×AD, -3×AD
- [x] MaxAdds=0: no adds, just success/failure exits. Position always 1.
- [x] exit_type logged for every cycle: SUCCESS, FAILURE, or SESSION_END
- [x] progress_hwm computed and logged
- [x] time_between_adds logged for multi-add cycles
- [x] cycle_day_seq logged (1-based per day)
- [x] cycle_start_hour logged (integer 9-15)
- [x] progress_at_adds logged (% of StepDist at each add, comma-separated)
- [x] prev_cycle_exit_type logged (SUCCESS/FAILURE/SESSION_START)
- [x] cycle_waste_pct logged (total absolute movement / net displacement)
- [x] Incomplete cycles logged with exit_type=SESSION_END + progress_hwm
- [x] Cost model: flatten + reseed charged to closing cycle
- [x] Asymmetric PnL verified: +672 ticks success vs -288 ticks failure (2.33x ratio)
- [x] Unit tests pass for all 25 test cases
- [x] V1.1 regression: 28/28 original tests still pass

## Pending (Requires P1 Data Run)

- [ ] V1.1 comparison: cycle count vs A_SD25 (4,856) — needs full P1 sweep
- [ ] Fractal completion validation: success rate by add count vs 79.7%/64.1%/56.0% — needs full P1 sweep
- [ ] Comparison table: fractal-predicted vs observed completion rates — needs full P1 sweep
