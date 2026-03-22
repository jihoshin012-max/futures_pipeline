# NQ Zone Touch — Autotrader Build Spec: Part B (Replication Gate)

> **Version:** 2.0
> **Date:** 2026-03-22
> **Scope:** Mandatory verification that C++ autotrader reproduces Python pipeline results
> **Prerequisite:** Part A build complete. P2 data files available. `p2_trade_details.csv` as answer key.
> **C++ source:** `C:\Projects\sierrachart\ATEAM_ZONE_BOUNCE_V1.cpp`
> **MANDATORY:** Do not begin paper trading until this gate passes.

---

## Purpose

The Python pipeline produced specific results on P2 holdout data: 58 CT trades at PF 5.10, 91 All-mode trades at PF 3.07. The C++ autotrader must reproduce these results. Any discrepancy means the implementation has a bug.

⚠️ The answer key is `p2_trade_details.csv` — 312 trades with every feature value, score, MFE/MAE, exit type, and PnL. Every C++ output is compared against this file.

---

## Data for Replication

**Use P2 data, not P1.** Reasons:
1. `p2_trade_details.csv` has complete per-trade answer key (features, bins, scores, exits, PnL)
2. P2 contains all edge cases (4 stops, 3 time caps, ETH + RTH, all cascade states)
3. P2 is the holdout result we're claiming works — reproducing it proves the implementation is correct

**Files needed:**
| File | Purpose |
|------|---------|
| `NQ_bardata_P2.csv` | P2 bar data for replay |
| `NQ_merged_P2a.csv` + `NQ_merged_P2b.csv` | P2 zone touches |
| `p2_trade_details.csv` | Answer key (312 trades) |
| `scoring_model_acal.json` | P1-frozen scoring model |
| `feature_config.json` | P1-frozen bin edges, TrendSlope cutoffs |

⚠️ All scoring uses P1-frozen parameters applied to P2 data. This is identical to what Prompt 3 did.

---

## Phase 1: Signal Replication (score matching)

**Purpose:** Verify the C++ scoring logic matches Python on individual touches.

### Sample Selection

Select 20 touches from P2, stratified to cover ALL logical branches:

⚠️ Choose touches from TWO sources:
- **Traded touches (above threshold):** `p2_trade_details.csv` — 312 trades with all feature values
- **Rejected touches (below threshold):** `NQ_merged_P2a.csv` and `NQ_merged_P2b.csv` — the raw P2 zone touches. Score these using the Python scoring logic (same as Prompt 3) to find touches below threshold. Alternatively, if a full P2 scored touches file exists (all touches scored, not just traded), use that.

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
| CT label (demand + supply) | 2 | Non-direction-aware trend logic (slope ≤ P33 → CT for both demand and supply) |

Some touches will satisfy multiple categories. Total = 20 unique touches.

⚠️ **GSD task:** Before running the replication gate, identify the specific 20 touches by row index from `p2_trade_details.csv` and the P2 scored touches file. Print their Python-computed values. These become the expected values.

### Verification Table (per sample touch)

Run the C++ autotrader's scoring logic on each of the 20 touches. Compare:

⚠️ **Answer key source:** `p2_trade_details.csv` has raw feature values (F10_PriorPenetration, F04_CascadeState, F01_Timeframe, F21_ZoneAge) and total acal_score, but does NOT have per-feature bin assignments or points. GSD must compute expected bins and points from: raw value + bin edges in `feature_config.json` + weights in `scoring_model_acal.json`. Verify the computed total matches the acal_score in the CSV.

| Field | Expected Value (source) | C++ Value | Match? |
|-------|------------------------|-----------|--------|
| F10 raw value | p2_trade_details.csv: F10_PriorPenetration | from C++ | ✓/✗ |
| F10 bin assignment | Compute: raw value vs bin edges in feature_config.json | from C++ | ✓/✗ |
| F10 points | Compute: bin → weight from scoring_model_acal.json | from C++ | ✓/✗ |
| F04 raw value | p2_trade_details.csv: F04_CascadeState | from C++ | ✓/✗ |
| F04 bin assignment | Compute from raw value | from C++ | ✓/✗ |
| F04 points | Compute from bin | from C++ | ✓/✗ |
| F01 raw value | p2_trade_details.csv: F01_Timeframe | from C++ | ✓/✗ |
| F01 bin assignment | Compute from raw value | from C++ | ✓/✗ |
| F01 points | Compute from bin | from C++ | ✓/✗ |
| F21 raw value | p2_trade_details.csv: F21_ZoneAge | from C++ | ✓/✗ |
| F21 bin assignment | Compute from raw value | from C++ | ✓/✗ |
| F21 points | Compute from bin | from C++ | ✓/✗ |
| A-Cal total score | p2_trade_details.csv: acal_score (cross-check: sum of computed points) | from C++ | ✓/✗ |
| Pass/fail threshold | acal_score vs 16.66 | from C++ | ✓/✗ |
| TrendSlope value | p2_trade_details.csv: trend_slope | from C++ | ✓/✗ |
| Trend label (CT/WT/NT) | p2_trade_details.csv: trend_label | from C++ | ✓/✗ |

**Pass criteria:** All 20 samples match on total score (within ±0.01 float tolerance) AND pass/fail decision AND trend label.

⚠️ **Common mismatch causes:**
- Bin edge boundary: Python uses `<` vs C++ uses `<=` (or vice versa) at bin boundaries
- TrendSlope source: must read from SignalRecord (ZBV4 pre-computed), NOT compute from bar data. Different scale.
- Trend classification: non-direction-aware (slope ≤ P33 → CT regardless of touch type). NOT direction-aware.
- F10 null: seq=1 touches have no prior penetration — value = 0, assign to lowest bin
- F04 categorical: string matching is case-sensitive

---

## Phase 2: Trade Replication (entry + exit matching)

**Purpose:** Verify C++ produces the same trades with the same entries and exits as Python.

⚠️ Reminder: replication must PASS before paper trading. Do not skip.

⚠️ **Answer key gap:** `p2_trade_details.csv` was generated with single-leg exits (from the pipeline). The autotrader uses 2-leg exits (from the exit sweep). Per-leg exit data for P2 does NOT exist yet. Before running Phase 2:

**GSD prerequisite task:** Run the Python 2-leg simulator (`exit_sweep_phase1.py` logic) on P2 data for the 10 sample trades below. Generate per-trade expected values: entry_price, leg1_exit_type, leg1_pnl, leg2_exit_type, leg2_pnl, bars_held, mfe, mae. Save as `p2_twoleg_answer_key.csv`. This becomes the Phase 2 answer key.

Use the same 2-leg exit params as the C++ autotrader:
- CT: T1=40t(67%), T2=80t(33%), Stop=190t, TC=160
- WT/NT: T1=60t(67%), T2=80t(33%), Stop=240t, TC=160

The single-leg `p2_trade_details.csv` can still verify: trade selection (same touches traded), entry prices (same), direction (same), scoring (same). Only the exit fields come from the new 2-leg answer key.

### Sample Selection

Select 10 specific trades from `p2_trade_details.csv`, covering all exit types:

| Category | Count | Trade IDs (from p2_trade_details.csv) |
|----------|-------|--------------------------------------|
| TARGET exit (both legs hit) | 3 | Pick 1 CT demand, 1 CT supply, 1 WT/NT |
| TARGET T1 + TIMECAP T2 (partial fill) | 2 | T1 fills but T2 doesn't reach target |
| STOP exit (both legs stopped) | 2 | Include 1 ETH stop (trade 1 or 45 from loser profile) |
| TIMECAP exit | 1 | Price didn't hit target or stop |
| Low margin trade (margin < 1) | 1 | Tests threshold boundary |
| High margin trade (margin > 4) | 1 | Tests clean signal path |

⚠️ **GSD task:** Select the specific 10 trades by trade_id from `p2_trade_details.csv`. The CSV already has entry_price, exit_type, pnl_ticks, bars_held, mfe_ticks, mae_ticks — these are the expected values.

### Verification Table (per sample trade)

Replay each trade on P2 bar data using the C++ autotrader. Compare:

| Field | Python (from CSV) | C++ Output | Match? |
|-------|-------------------|------------|--------|
| Touch bar index | ? | ? | ✓/✗ |
| Entry bar (touch + 1) | ? | ? | ✓/✗ |
| Entry price (bar open) | ? | ? | ✓/✗ |
| Direction (LONG/SHORT) | ? | ? | ✓/✗ |
| Mode (CT/WTNT) | ? | ? | ✓/✗ |
| Stop price | ? | ? | ✓/✗ |
| T1 target price | ? | ? | ✓/✗ |
| T2 target price | ? | ? | ✓/✗ |
| Leg 1 exit type | ? | ? | ✓/✗ |
| Leg 1 exit bar | ? | ? | ✓/✗ |
| Leg 1 PnL | ? | ? | ✓/✗ |
| Leg 2 exit type | ? | ? | ✓/✗ |
| Leg 2 exit bar | ? | ? | ✓/✗ |
| Leg 2 PnL | ? | ? | ✓/✗ |
| Bars held | ? | ? | ✓/✗ |
| MFE | ? | ? | ✓/✗ |
| MAE | ? | ? | ✓/✗ |

**Pass criteria:** All 10 trades match on entry price, exit type per leg, and PnL (within ±1 tick for float rounding). No trade taken by Python but missed by C++, or vice versa.

⚠️ **Common mismatch causes:**
- Intra-bar conflict: C++ checking target before stop (should be stop-first)
- Time cap count: off-by-one (bar count starts at entry bar or bar after entry)
- No-overlap gate: different `in_trade_until` logic (does it include the exit bar or not?)
- 16:55 flatten: C++ has real timestamps, Python may not have flattened these trades
- 2-leg exit: when T1 fills on bar N, does T2's time cap start counting from entry or from T1 fill? (Answer: from entry — shared time cap for all legs)

⚠️ The 2-leg exits are NEW from the exit sweep. Python's `exit_sweep_phase1.py` is the authoritative reference for 2-leg simulation logic, not the original single-leg `zone_touch_simulator.py`.

---

## Phase 3: Full Period Replay (aggregate matching)

**Purpose:** Run C++ autotrader on full P2 bar data. Compare aggregate stats against known results.

⚠️ Reminder: this is the final replication check. Phases 1-2 tested individual signals and trades. Phase 3 tests the full system including no-overlap gating and signal ordering.

### Run the C++ autotrader on P2

### Run the C++ autotrader on P2

⚠️ **Replay method:** Use Sierra Chart's Chart Replay feature to replay the P2 date range bar-by-bar. The autotrader runs on chart in its normal mode — it doesn't know it's replay vs live. This tests the full real-time code path including V4 zone detection, touch events, scoring, and order management.

Alternative: If Sierra Chart replay is impractical (e.g., V4 zones don't reconstruct identically on replay), build a standalone replay mode in the C++ study that reads `NQ_bardata_P2.csv` and `NQ_merged_P2a/P2b.csv` directly, bypassing V4. This tests scoring + exit logic but NOT the V4 data interface. Flag which method was used in `replication_gate_results.md`.

The autotrader should produce `trade_log.csv` and `signal_log.csv` as specified in Part A.

### Compare aggregate stats

| Metric | Python Answer Key | C++ Output | Tolerance |
|--------|------------------|------------|-----------|
| CT mode total trades | 58 | ? | Exact (trade selection unchanged by exit type) |
| WT/NT-only trades | ~33 (91 All-mode minus 58 CT) | ? | Exact |
| CT mode PF @3t (2-leg) | From `p2_twoleg_answer_key.csv` (generated in Phase 2 prereq) | ? | Within ±5% |
| CT target rate (T1) | From 2-leg answer key | ? | Within ±3% |
| CT stop rate | From 2-leg answer key | ? | Within ±3% |
| CT time cap rate | From 2-leg answer key | ? | Within ±3% |
| Total signals fired (above threshold) | From signal_log comparison | ? | Exact |
| Total signals skipped (in-position) | From signal_log comparison | ? | Exact |

⚠️ **Important note on trade counts:** The Python pipeline tested seg3 ModeB (CT only = 58) and seg1 ModeA (all high-score = 91) as SEPARATE populations. The C++ autotrader routes CT and WT/NT as exclusive modes (a touch is either CT or WT/NT, never both). So the C++ total should be: CT trades + WT/NT-only trades = approximately 58 + 33 = ~91 total. Not 58 + 91 = 149.

⚠️ **PF tolerance is ±5% for Phase 3** because both C++ and the Python 2-leg answer key use the same exit parameters. If Phase 2 prereq task ran correctly, both should agree closely. Larger deviations indicate a simulation logic bug, not an expected difference.

### Cross-check with trade_log.csv

After Phase 3 replay, the C++ `trade_log.csv` should exist with all columns from Part A spec. Verify:
- Every row has all feature columns populated (no nulls except F10 on seq=1)
- Every row has per-leg exit types
- score_margin = acal_score - 16.66 (computed correctly)
- session = RTH or ETH (correctly classified)
- MFE and MAE are positive values

---

## Replication Gate Verdict

| Result | Criteria | Action |
|--------|----------|--------|
| **PASS** | All 3 phases pass | Proceed to paper trading (Part C) |
| **PARTIAL PASS** | Phase 1+2 pass, Phase 3 has minor PF deviation (within ±10%) but trade count matches | Investigate. Likely float rounding or bar-boundary timing. |
| **FAIL** | Any phase fails on score matching, trade matching, or trade count | Fix before paper trading. Do not proceed. |

⚠️ Save all replication results to `replication_gate_results.md`. Include the 20 score samples, 10 trade samples, and aggregate comparison table. This is the permanent record that the C++ implementation was verified.

---

## Part B Self-Check

✅ **Replication gate complete when:**
- [ ] Python 2-leg answer key generated (`p2_twoleg_answer_key.csv`) — prerequisite for Phases 2-3
- [ ] 20 sample touches selected (stratified across all branches — including 3 below-threshold from raw P2 merged CSVs)
- [ ] Replay method documented (Sierra Chart replay or standalone CSV replay — flag which)
- [ ] Phase 1: all 20 scores match within ±0.01, all pass/fail decisions match, all trend labels match
- [ ] Phase 2: all 10 trades match on entry price, exit type per leg, PnL within ±1 tick
- [ ] Phase 3: CT trade count = 58 (exact). Signal count matches. Exit rates within ±3%.
- [ ] trade_log.csv produced with all Part A columns populated
- [ ] signal_log.csv produced with all skipped signals and reasons
- [ ] Any mismatches investigated and resolved (root cause documented)
- [ ] `replication_gate_results.md` saved with all comparison tables
- [ ] Verdict: PASS / PARTIAL PASS / FAIL recorded
