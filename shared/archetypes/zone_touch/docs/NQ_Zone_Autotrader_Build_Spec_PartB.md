# NQ Zone Touch — Autotrader Build Spec: Part B (Replication Gate)

> **Version:** 3.0
> **Date:** 2026-03-23
> **Scope:** Mandatory verification that C++ autotrader reproduces Python pipeline results with zone-relative exits
> **Prerequisite:** Part A v3.0 build complete. P2 data files available. `p2_twoleg_answer_key_zr.csv` as answer key.
> **C++ source:** `C:\Projects\sierrachart\ATEAM_ZONE_BOUNCE_V1.cpp`
> **MANDATORY:** Do not begin paper trading until this gate passes.
> **Change from v2.0:** Answer key uses zone-relative exits (0.5x/1.0x/1.5x zone width), CT 5t limit entry, 120t stop floor. Phase 2 adds zone-width verification columns and limit order samples.

---

## Purpose

The Python replication harness produced zone-relative results on P2 holdout data. The C++ autotrader must reproduce these results. Any discrepancy means the implementation has a bug.

⚠️ The answer key is `p2_twoleg_answer_key_zr.csv` — zone-relative 2-leg exits with CT 5t limit entry. Every C++ output is compared against this file. The old fixed-exit answer key is preserved as `p2_twoleg_answer_key_fixed.csv` for reference only.

⚠️ Skipped signals are verified against `p2_skipped_signals_zr.csv` — includes LIMIT_EXPIRED and LIMIT_PENDING skip reasons.

---

## Data for Replication

**Use P2 data, not P1.** Reasons:
1. `p2_twoleg_answer_key_zr.csv` has complete per-trade answer key with zone-relative exits
2. P2 contains edge cases across zone widths, CT limit fills, and all exit types
3. P2 is the holdout result — reproducing it proves the implementation is correct

**Files needed:**
| File | Purpose |
|------|---------|
| `NQ_bardata_P2.csv` | P2 bar data for replay |
| `NQ_merged_P2a.csv` + `NQ_merged_P2b.csv` | P2 zone touches |
| `p2_twoleg_answer_key_zr.csv` | Answer key (zone-relative 2-leg exits) |
| `p2_skipped_signals_zr.csv` | Skipped signal answer key (includes LIMIT_EXPIRED, LIMIT_PENDING) |
| `scoring_model_acal.json` | P1-frozen scoring model |
| `feature_config.json` | P1-frozen bin edges, TrendSlope cutoffs |

⚠️ All scoring uses P1-frozen parameters. Exit multipliers (0.5x, 1.0x, 1.5x, 120t floor) are hardcoded in `zone_bounce_config.h`.

---

## Phase 1: Signal Replication (score matching)

**Purpose:** Verify the C++ scoring logic matches Python on individual touches. Scoring is unchanged from v2.0 — this phase validates features, bins, and threshold logic.

### Sample Selection

Select 20 touches from P2, stratified to cover ALL logical branches:

⚠️ Choose touches from TWO sources:
- **Traded touches (above threshold):** `p2_twoleg_answer_key_zr.csv` — trades with all feature values
- **Rejected touches (below threshold):** `NQ_merged_P2a.csv` and `NQ_merged_P2b.csv` — raw P2 zone touches. Score using Python scoring logic to find below-threshold touches.

The specific touches must cover:

| Category | Count | What it tests |
|----------|-------|--------------|
| High score margin (> 3 pts above threshold) | 3 | Normal scoring path |
| Near-threshold (margin 0-1 pts) | 3 | Bin edge boundary handling |
| Below threshold (rejects) | 3 | Rejection path works correctly |
| SBB touches | 2 | SBB_label detection |
| Seq = 1 (F10 is null) | 2 | Null handling for prior penetration |
| Each CascadeState (NO_PRIOR, PRIOR_HELD, PRIOR_BROKE) | 1 each | F04 categorical encoding |
| Each TF (15m, 30m, 60m, 90m, 120m) | 1 each | F01 encoding across timeframes |
| CT label (demand + supply) | 2 | Non-direction-aware trend logic |

Some touches will satisfy multiple categories. Total = 20 unique touches.

⚠️ **GSD task:** Identify the specific 20 touches by row index. Print their Python-computed values. These become the expected values.

### Verification Table (per sample touch)

⚠️ **Answer key source:** The answer key has raw feature values and total acal_score, but does NOT have per-feature bin assignments or points. Compute expected bins and points from: raw value + bin edges in `feature_config.json` + weights in `scoring_model_acal.json`. Verify the computed total matches the acal_score.

| Field | Expected Value (source) | C++ Value | Match? |
|-------|------------------------|-----------|--------|
| F10 raw value | from answer key | from C++ | ✓/✗ |
| F10 bin assignment | Compute: raw vs bin edges | from C++ | ✓/✗ |
| F10 points | Compute: bin → weight | from C++ | ✓/✗ |
| F04 raw value | from answer key | from C++ | ✓/✗ |
| F04 bin assignment | Compute from raw | from C++ | ✓/✗ |
| F04 points | Compute from bin | from C++ | ✓/✗ |
| F01 raw value | from answer key | from C++ | ✓/✗ |
| F01 bin assignment | Compute from raw | from C++ | ✓/✗ |
| F01 points | Compute from bin | from C++ | ✓/✗ |
| F21 raw value | from answer key | from C++ | ✓/✗ |
| F21 bin assignment | Compute from raw | from C++ | ✓/✗ |
| F21 points | Compute from bin | from C++ | ✓/✗ |
| A-Cal total score | from answer key (cross-check: sum of points) | from C++ | ✓/✗ |
| Pass/fail threshold | acal_score vs 16.66 | from C++ | ✓/✗ |
| TrendSlope value | from answer key | from C++ | ✓/✗ |
| Trend label (CT/WT/NT) | from answer key | from C++ | ✓/✗ |

**Pass criteria:** All 20 samples match on total score (within ±0.01 float tolerance) AND pass/fail decision AND trend label.

⚠️ **Common mismatch causes:**
- Bin edge boundary: Python uses `<` vs C++ uses `<=` (or vice versa) at bin boundaries
- TrendSlope source: must read from SignalRecord (ZBV4 pre-computed), NOT compute from bar data. Different scale.
- Trend classification: non-direction-aware (slope ≤ P33 → CT regardless of touch type). NOT direction-aware.
- F10 null: seq=1 touches have no prior penetration — value = 0, assign to lowest bin
- F04 categorical: string matching is case-sensitive

---

## Phase 2: Trade Replication (entry + exit matching)

**Purpose:** Verify C++ produces the same trades with zone-relative entries and exits as Python.

⚠️ Reminder: replication must PASS before paper trading. Do not skip.

⚠️ The answer key `p2_twoleg_answer_key_zr.csv` contains zone-relative exits for ALL trades. No prerequisite generation needed — the replication prompt already produced it.

### Sample Selection

Select 12 specific trades from `p2_twoleg_answer_key_zr.csv`, covering all entry types, exit types, and zone width ranges:

| Category | Count | What it tests |
|----------|-------|--------------|
| CT LIMIT_5T + TARGET (both legs) | 2 | CT limit fill + zone-relative target hit (1 narrow zone, 1 wide zone) |
| CT LIMIT_5T + STOP | 1 | CT limit fill + zone-relative stop hit |
| CT LIMIT_5T + TIMECAP | 1 | CT limit fill + time cap expiry |
| WT MARKET + TARGET (both legs) | 2 | WT market entry + zone-relative target (1 narrow, 1 wide) |
| WT MARKET + STOP | 1 | WT market entry + zone-relative stop |
| TARGET T1 + TIMECAP T2 (partial fill) | 1 | T1 hits but T2 doesn't reach 1.0x zone width |
| Narrow zone (< 100t) where stop floor applies | 1 | max(1.5x zw, 120t) = 120t |
| Wide zone (200t+) | 1 | Large zone-relative targets/stops |
| LIMIT_EXPIRED from skipped signals | 1 | CT limit unfilled after 20 bars |

⚠️ Include at least one trade with price improvement (limit fill better than limit price).

### Verification Table (per sample trade)

| Field | Python (from answer key) | C++ Output | Match? |
|-------|-------------------------|------------|--------|
| Touch bar index | ? | ? | ✓/✗ |
| Entry type (LIMIT_5T / MARKET) | ? | ? | ✓/✗ |
| Entry bar | ? | ? | ✓/✗ |
| Entry price | ? | ? | ✓/✗ |
| Direction (LONG/SHORT) | ? | ? | ✓/✗ |
| Mode (CT/WTNT) | ? | ? | ✓/✗ |
| zone_width_ticks | ? | ? | ✓/✗ |
| t1_ticks (0.5 × zw) | ? | ? | ✓/✗ |
| t2_ticks (1.0 × zw) | ? | ? | ✓/✗ |
| stop_ticks (max(1.5 × zw, 120)) | ? | ? | ✓/✗ |
| T1 target price | ? | ? | ✓/✗ |
| T2 target price | ? | ? | ✓/✗ |
| Stop price | ? | ? | ✓/✗ |
| Leg 1 exit type | ? | ? | ✓/✗ |
| Leg 1 exit bar | ? | ? | ✓/✗ |
| Leg 1 PnL | ? | ? | ✓/✗ |
| Leg 2 exit type | ? | ? | ✓/✗ |
| Leg 2 exit bar | ? | ? | ✓/✗ |
| Leg 2 PnL | ? | ? | ✓/✗ |
| Bars held | ? | ? | ✓/✗ |
| MFE | ? | ? | ✓/✗ |
| MAE | ? | ? | ✓/✗ |

⚠️ **Zone-relative verification:** For every sample trade, verify the chain:
zone_width_ticks → t1_ticks (= 0.5 × zw) → t2_ticks (= 1.0 × zw) → stop_ticks (= max(1.5 × zw, 120)) → absolute price levels from entry. If zone_width matches but target prices don't, the multiplier or direction arithmetic is wrong.

**Pass criteria:** All 12 trades match on entry type, entry price, zone_width_ticks, exit type per leg, and PnL (within ±1 tick). The LIMIT_EXPIRED signal must show in signal_log with correct skip_reason.

⚠️ **Common mismatch causes (v3.0 additions):**
- Zone width computation: (ZoneTop - ZoneBot) / tick_size — verify tick_size = 0.25
- Stop floor: max(1.5 × zw, 120) — for zones < 80t, the floor should activate
- CT limit fill: checking Low ≤ limit_price (LONG) or High ≥ limit_price (SHORT) within 20 bars
- Price improvement: fill at min(Open, limit_price) for LONG, max(Open, limit_price) for SHORT
- Limit expiry: exactly 20 bars, not 19 or 21
- LIMIT_PENDING: WT signal during CT limit window should be skipped
- Intra-bar conflict: stop-first rule with zone-relative stop levels
- Time cap count: from entry bar (fill bar for CT limit, next bar for WT market)

⚠️ The zone-relative exit multipliers are the critical new verification. Every sample trade must have its zone width → tick conversion → price level chain verified column by column.

---

## Phase 3: Full Period Replay (aggregate matching)

**Purpose:** Run C++ autotrader on full P2 data. Compare aggregate stats against the answer key.

⚠️ Reminder: this is the final replication check. Phases 1-2 tested individual signals and trades. Phase 3 tests the full system including no-overlap gating, CT limit pending blocking, and signal ordering.

### Run the C++ autotrader on P2

⚠️ **Replay method:** Use the standalone CSV replay harness (proven in prior replication). SC chart replay has known phantom signal issues with V4. Flag which method was used in `replication_gate_results.md`.

The autotrader should produce `trade_log.csv` and `signal_log.csv` as specified in Part A v3.0.

### Compare aggregate stats

| Metric | Python Answer Key | C++ Output | Tolerance |
|--------|------------------|------------|-----------|
| CT trades (filled) | from answer key | ? | Exact |
| CT LIMIT_EXPIRED | from answer key | ? | Exact |
| WT/NT trades | from answer key | ? | Exact |
| LIMIT_PENDING skips | from skipped signals file | ? | Exact |
| Total trades | from answer key | ? | Exact |
| WR | from answer key | ? | Within ±2% |
| PF @3t | from answer key | ? | Within ±5% |
| CT target rate (T1) | from answer key | ? | Within ±3% |
| CT stop rate | from answer key | ? | Within ±3% |
| CT time cap rate | from answer key | ? | Within ±3% |
| Total signals fired (above threshold) | from skipped signals file | ? | Exact |
| Total signals skipped (all reasons) | from skipped signals file | ? | Exact |

⚠️ **Trade count must be EXACT.** The zone-relative exits don't change which trades are taken — they change the exit levels. Trade count differences indicate a scoring, filtering, or overlap logic bug, not an exit issue.

⚠️ **PF tolerance is ±5%** because both C++ and Python use the same zone-relative exit logic. Larger deviations indicate a simulation logic bug. Common causes: zone width rounding, stop floor activation threshold, limit fill price computation.

### Cross-check with trade_log.csv

After Phase 3 replay, verify the C++ `trade_log.csv`:
- Every row has zone_width_ticks, stop_ticks, t1_ticks, t2_ticks populated
- t1_ticks = 0.5 × zone_width_ticks for every row
- t2_ticks = 1.0 × zone_width_ticks for every row
- stop_ticks = max(1.5 × zone_width_ticks, 120) for every row
- entry_type = LIMIT_5T for all CT, MARKET for all WT/NT
- All feature columns populated (no nulls except F10 on seq=1)
- score_margin = acal_score - 16.66
- session = RTH or ETH correctly classified
- MFE and MAE are positive values

### Cross-check with signal_log.csv

- LIMIT_EXPIRED entries present with correct count
- LIMIT_PENDING entries present (WT signals blocked by active CT limit)
- IN_POSITION and CROSS_MODE_OVERLAP entries present
- BELOW_THRESHOLD, TF_FILTER, SEQ_FILTER entries present
- zone_width_ticks populated on every signal row

---

## Replication Gate Verdict

| Result | Criteria | Action |
|--------|----------|--------|
| **PASS** | All 3 phases pass | Proceed to paper trading (Part C) |
| **PARTIAL PASS** | Phase 1+2 pass, Phase 3 has minor PF deviation (within ±10%) but trade count matches | Investigate. Likely float rounding or bar-boundary timing. |
| **FAIL** | Any phase fails on score matching, trade matching, or trade count | Fix before paper trading. Do not proceed. |

⚠️ Save all replication results to `replication_gate_results_zr.md`. Include the 20 score samples, 12 trade samples, and aggregate comparison table. This is the permanent record that the C++ implementation was verified against the zone-relative answer key.

---

## Part B Self-Check

✅ **Replication gate complete when:**
- [ ] `p2_twoleg_answer_key_zr.csv` exists as the zone-relative answer key
- [ ] `p2_skipped_signals_zr.csv` exists with all skip reasons
- [ ] 20 sample touches selected (stratified across all branches — including 3 below-threshold)
- [ ] Replay method documented (standalone CSV replay recommended)
- [ ] Phase 1: all 20 scores match within ±0.01, all pass/fail match, all trend labels match
- [ ] Phase 2: all 12 trades match on entry type, entry price, zone_width_ticks, exit type per leg, PnL within ±1 tick
- [ ] Phase 2: zone-relative chain verified (zw → t1_ticks → t2_ticks → stop_ticks → prices)
- [ ] Phase 2: LIMIT_EXPIRED signal verified in signal_log
- [ ] Phase 2: at least one stop floor trade verified (zone < 80t, stop = 120t)
- [ ] Phase 3: trade counts match exactly (CT filled, CT expired, WT, LIMIT_PENDING)
- [ ] Phase 3: PF within ±5% of answer key
- [ ] trade_log.csv has ALL Part A v3.0 columns populated
- [ ] signal_log.csv has ALL signals including LIMIT_EXPIRED and LIMIT_PENDING
- [ ] `replication_gate_results_zr.md` saved with all comparison tables
- [ ] Verdict: PASS / PARTIAL PASS / FAIL recorded
