# Rotational Archetype — Specification & Research Plan

**Archetype:** `rotational`
**Instrument:** NQ futures (extensible)
**Source study:** `ATEAM_ROTATION_V1_OG_V2803.cpp` → C++ V2: `ATEAM_ROTATION_V2_V2882_wmaxcap.cpp`
**Status:** Phase 04 (hypothesis screening) ready to start. Phases A, B, 02.1, 03, 03.1 complete. Simulator, profiles, TDS, and anchor mode validated.
**Date:** 2026-03-16 (last updated)

---

## EXECUTIVE SUMMARY

**Read this section first. It contains everything needed to orient on the full document.**

### What This Strategy Is

A single-instrument, always-in-market, direction-rotation state machine with martingale position averaging on NQ futures. The strategy is always positioned long or short. When price moves a threshold distance in favor, the strategy flattens and reverses. When price moves against, the strategy adds contracts at geometrically increasing size (1→2→4→8). The kill zone is straight-line moves without pullback — the martingale fires through all levels with no reversal opportunity.

### What This Document Covers

- **Section 1:** Baseline strategy (C++ replication target)
- **Section 2:** Data requirements (three bar types: 250-vol, 250-tick, 10-sec) + cross-bar-type feature engineering layer (6 derived signals from inter-series relationships)
- **Section 3:** 41 research hypotheses organized into 6 dimensions
- **Section 4:** Trend Defense System — three-level escalation to survive straight-line moves
- **Section 5:** 10 pipeline architecture gaps identified with proposed resolutions
- **Section 6:** Simulator design (continuous state machine, not event-driven)
- **Section 7:** Assessment metrics — 11 metric categories with expanded verdict logic (cycle-level, not trade-level; includes capital exposure, cost drag, profit concentration, heat, action efficiency, equity curve quality, session-level distribution, dollar-weighted metrics, directional split, trend defense)
- **Sections 8-10:** Files, implementation sequence, open questions

### Critical Architectural Decisions (reference throughout)

1. **The unit of analysis is the CYCLE, not the trade.** A cycle = seed/reversal through all adds to the next reversal. Trades within a cycle are not independent. All metrics (PF, Sharpe, win rate) are computed on cycles.

2. **No scoring adapter.** Unlike zone_touch, there are no discrete signal events to score. The decision logic lives inside the simulator. `config.archetype.scoring_adapter = null`.

3. **Three bar types as primary execution series.** 250-vol, 250-tick, and 10-sec (RTH session-filtered) all run the strategy independently. 10-sec also serves as reference layer for VWAP, time-based conditions, and cross-series divergence. Cross-bar-type analysis (Phase 1b) classifies hypothesis robustness by how consistently results hold across sampling methods.

4. **Assessment goes far beyond PF and Sharpe.** Martingale strategies produce misleading standard metrics (high win rate, inflated PF). Verdict logic includes robustness gates: slippage sensitivity (PF must survive +0.5 tick slippage), profit concentration (breakeven removal count ≥ 10% of cycles), and asymmetry ratio (average loser < 5× average winner). These gates catch martingale illusions that standard metrics miss.

5. **41 hypotheses tested independently first, then cross-analyzed, then combined.** Phase 1 = independent screening on all 3 bar types × 3 profiles (~366 meaningful experiments per profile cycle). Phase 1b = cross-bar-type analysis per profile (classify robustness). Phase 2 = winner combinations. Phase 3 = integrate Trend Defense System. **Priority ranking updated based on Empirical Findings — see below.**

6. **Trend Defense is a separate subsystem, not a hypothesis.** It's a coordinated multi-level response to straight-line moves. Tested and measured separately on survival metrics, then combined with the best alpha configuration.

7. **3 parallel risk profiles, not a single baseline.** Joint parameter sweep (StepDist × MaxLevels × MaxTotalPosition) produces 3 distinct baseline profiles per bar type: MAX_PROFIT (highest cycle PF), SAFEST (best survival metrics), MOST_CONSISTENT (best risk-adjusted returns). All downstream research runs per-profile — hypothesis screening, TDS calibration, combination testing, and assessment each produce 3 results. Final pipeline output offers 3 deployable configurations; the user chooses the profile matching their risk appetite.

8. **MaxTotalPosition is a pipeline addition not in the C++ source.** The C++ has no total position cap — position grows without limit. MaxTotalPosition caps total exposure: `current_position + proposed_addQty > MTP` → refuse add. This is the primary risk control lever and the key differentiator between profiles.

9. **No PF gating until Phase 5 verdict.** Hypothesis filters (time-of-day, PriceSpeed, selective flat periods, etc.) will reshape which cycles occur and may transform a raw PF 0.7 into a filtered PF 2.0. Gating on PF during profile selection or hypothesis screening would create false negatives. PF < 1.0 is flagged but not excluded until the final verdict after all filters, TDS, and combinations are applied.

### Empirical Findings (from completed phases — reference throughout)

**FINDING 1 — MARTINGALE IS NET NEGATIVE (Phase 02.1 sizing sweep, 966 P1a runs):**
Geometric martingale (ML=4, 1→2→4→8) is 24-32% worse than ML=1 (flat adds) on activity-sampled bars. Cost drag from geometric sizing creates 3×-11× cost multiplier per cycle. The strategy's edge is pure rotation, not position averaging. Winning configs use ML=1 with MTP=1 or MTP=2. Martingale-management hypotheses (H14, H23, H24, H39) deprioritized. Dimension A triggers, H11 (time-of-day), H13 (selective flat), H33 (PriceSpeed) elevated.

**FINDING 2 — FROZEN ANCHOR IS THE CORRECT DESIGN (anchor mode comparison, 15 P1a runs):**
When MTP refuses an add, anchor stays at the last successful trade. Walking the anchor (Mode B) or adding a hard stop (Mode C) both destroy the strategy — PF drops from 1.7-2.2 to 0.7-0.9, with cycle count exploding 12× and transaction costs overwhelming returns. The patience of holding through adverse moves IS the edge. Documented in `simulation_rules.md`.

**FINDING 3 — TDS L3 (FORCE-FLATTEN) IS INCOMPATIBLE WITH ROTATIONAL EDGE (Phase 03.1, 99 P1a runs):**
Every form of forced exit destroys the strategy. L3 drawdown budget fires on virtually every cycle because normal rotation at SD=7.0 MTP=2 routinely produces 50-100+ tick unrealized drawdowns. TDS disposition: disabled for vol/tick bars, velocity-only L1 for 10sec bars. L2 is dead code at MTP≤2. MTP IS the risk management — position size cap, not exit rules.

**FINDING 4 — MAX_PROFIT AND MOST_CONSISTENT CONVERGE (Phase 02.1):**
On 250vol and 10sec, the most profitable config is also the most risk-adjusted. SD=7.0 ML=1 MTP=2 wins both profiles on 250vol (PF=2.20, Calmar=1.23, 94.4% winning sessions). This convergence suggests a structural edge, not fragile optimization.

**WINNING CONFIGURATIONS (from validated sweep, Mode A frozen anchor):**

| Bar Type | StepDist | ML | MTP | Cycle PF | Total PnL | Calmar | Win% | Profile |
|----------|----------|----|-----|----------|-----------|--------|------|---------|
| 250vol | 7.0 | 1 | 2 | 2.20 | +10,537t | 1.23 | 94.4% | MAX_PROFIT & MOST_CONSISTENT |
| 250tick | 4.5 | 1 | 1 | 1.84 | +4,489t | 0.84 | 92.9% | MAX_PROFIT (pure reversal) |
| 10sec | 10.0 | 1 | 4 | 1.72 | +11,363t | 0.81 | 86.7% | MAX_PROFIT & MOST_CONSISTENT |

All PF numbers are NET of costs (cost_ticks=3 per NQ round trip from instruments.md).

### Pipeline Gaps — Implementation Status

| Gap | Severity | One-line summary | Status |
|-----|----------|-----------------|--------|
| G-01 | **HIGH** | `data_manifest.json` multi-source support | ✅ Complete (Phase A) |
| G-02 | **HIGH** | Separate `rotational_engine.py` | ✅ Complete (Phase A) |
| G-03 | Resolved | Scoring adapter N/A | ✅ Resolved by G-02 |
| G-04 | **HIGH** | Stage 02 feature evaluator bar-level outcomes | ✅ Complete (Phase A) |
| G-05 | Medium | `results_master.tsv` col 25 `extended_metrics` | ✅ Complete (Phase A) |
| G-06 | Medium | Rotational-specific verdict thresholds | ✅ Complete (Phase A) |
| G-07 | Low | HMM regime model refit on rotational data | ⏳ Open — needed before H5 testing |
| G-08 | Medium | Autoresearch mapping for rotational | ✅ Complete (files built) |
| G-09 | Medium | Feature evaluator dynamic dispatch | ✅ Complete (already existed) |
| G-10 | Medium | Bonferroni / multiple testing correction | ⏳ Pending — deferred to Phase 05 |

**Full details for each gap are in Section 5.**

### Five Pipeline Rules (absolute — never violate)

These rules govern the entire pipeline and apply to all archetypes including rotational:

1. **P1 Calibrate** — IS data (P1) used freely for calibration and search
2. **P2 One-Shot** — OOS (P2) runs exactly once with frozen params; never re-run
3. **Entry-Time Only** — features must be computable at entry time; no lookahead. For rotational: all feature values at bar index i use only data from bars 0..i
4. **Internal Replication** — strategy must pass P1b before P2 is unlocked (gate: `flag_and_review` — P1b fail → `WEAK_REPLICATION` verdict for human review)
5. **Instrument Constants from Registry** — tick size, cost_ticks, session times from `_config/instruments.md` only

---

## 1. Baseline Strategy Definition

### 1.1 What This Strategy Is

A single-instrument, always-in-market, direction-rotation state machine with martingale position averaging. The strategy is always positioned long or short. When price moves a threshold distance in the position's favor, the strategy flattens and reverses to the opposite direction. When price moves against, the strategy adds to the position at geometrically increasing size.

This is fundamentally different from zone_touch. Zone_touch is event-driven (discrete touch signals → score → enter → exit). Rotational is continuous (every bar is a potential state transition). This distinction drives most of the architectural gaps identified in Section 5.

### 1.2 State Machine

```
States:  FLAT → POSITIONED (Long/Short, Level 0..N)
Actions: SEED, REVERSAL, ADD

SEED:
  Trigger:  Position is flat, no anchor set
  Action:   Buy InitialQty
  Result:   Direction=Long, Anchor=Price, Level=0

REVERSAL:
  Trigger:  Price moves ≥ StepDist IN FAVOR from Anchor
  Action:   Flatten all → Enter opposite direction at InitialQty
  Result:   Direction flips, Anchor=Price, Level=0

ADD:
  Trigger:  Price moves ≥ StepDist AGAINST from Anchor
  Action:   Add (InitialQty × 2^Level) contracts in same direction
  Result:   Anchor=Price, Level++
  Cap:      If add qty > MaxContractSize → reset to InitialQty, Level=0
```

### 1.3 Baseline Parameters

| Parameter | C++ Default | Pipeline Addition | Description |
|-----------|-------------|-------------------|-------------|
| `StepDist` | 2.0 pts | Sweep-optimized | Distance threshold for reversal and add |
| `InitialQty` | 1 | Fixed at 1 | Base position size (linear scaling factor — doesn't affect ratio metrics) |
| `MaxLevels` | 4 | Sweep-optimized | Controls add pattern: ML=1→flat adds (1,1,1,...), ML=2→(1,2,1,2,...), ML=3→(1,2,4,...), ML=4→(1,2,4,8,...), ML=5→(1,2,4,8,16,...) |
| `MaxContractSize` | 8 | Fixed at 16 | Caps **individual add size** only (`addQty > MCS` → reset to InitialQty). Set to 16 in all runs to let MaxLevels be the sole pattern control. |
| `MaxTotalPosition` | N/A (no cap in C++) | Sweep-optimized | **Pipeline addition.** Caps **total position exposure**. Check: `current_position + proposed_addQty > MTP` → refuse add entirely. MTP=0 means unlimited (C++ behavior). MTP=1 means pure reversal (no adds). |

**Critical distinction:** MaxContractSize caps the size of a single add. MaxTotalPosition caps total accumulated exposure. The C++ has no total position cap — position grows without limit until a reversal flattens everything. MaxTotalPosition is the pipeline's primary risk control lever.

### 1.4 Critical Behavioral Properties

- **Always in market** — no flat state during normal operation (only at seed and during flatten→reverse transition)
- **Symmetric** — same StepDist for reversal and add, same parameters for long and short
- **Anchor resets on every action** — reversal and add both move anchor to current price
- **Anchor FREEZES on MTP refusal** — when MaxTotalPosition refuses an add, anchor stays at last successful trade. This is a validated design decision (see Empirical Finding 2). The patience of holding through adverse moves is the strategy's edge. Walking the anchor or adding hard stops destroys profitability.
- **Trades are not independent** — a martingale add is causally linked to prior entries; the unit of analysis is the full rotation cycle (seed/reversal → all adds → next reversal)
- **Single timeframe** — operates on one bar series with no higher-timeframe awareness
- **No exit except reversal** — no profit target, no stop loss, no time-based exit. MTP caps position size but does not force exits. TDS L3 (force-flatten) was empirically shown to destroy the edge.
- **No memory** — ignores its own recent performance
- **No total position cap (C++ default)** — position accumulates without limit until reversal. MaxTotalPosition (pipeline addition) addresses this.

### 1.5 Known Vulnerability

Straight-line moves without pullback. The strategy's profitability depends on price rotating — retracing enough to trigger reversals at favorable levels. A sustained directional move puts the strategy on the wrong side and the frozen anchor means it must wait for a full recovery (price returning to anchor + StepDist) to reverse.

**Mitigations validated by data:**
- **MaxTotalPosition (primary):** Caps total exposure at 1-4 contracts. The strategy holds through adverse moves but position size is controlled. Worst-cycle DD at MTP=2 is 8,569 ticks — significant but recoverable within the P1a sample.
- **TDS L1 velocity step-widening (10sec only):** Widens steps during fast moves, reducing activity during adverse conditions without forcing exits. +575 worst-DD reduction on 10sec bars.

**Mitigations shown to be harmful:**
- ~~TDS L3 force-flatten~~ — fires on virtually every cycle, destroying profitability. Incompatible with rotational edge.
- ~~Hard stops of any kind~~ — Mode C comparison showed all hard-stop variants produce massive losses. The strategy's patience IS the edge.
- ~~Walking anchor on MTP refusal~~ — creates cycle count explosion (12×) and cost drag that overwhelms returns.

---

## 2. Data Requirements

### 2.1 Bar Data Sources

| source_id | Bar type | File pattern | Status |
|-----------|----------|--------------|--------|
| `bar_data_250vol_rot` | 250-volume | `NQ_BarData_250vol_rot_{period}.csv` | P1 uploaded, P2 available |
| `bar_data_250tick_rot` | 250-tick | `NQ_BarData_250tick_rot_{period}.csv` | P1 uploaded, P2 available |
| `bar_data_10sec_rot` | 10-second | `NQ_BarData_10sec_rot_{period}.csv` | P1 and P2 available in pipeline |

**IS/OOS periods (from `period_config.md`):**

| period_id | archetype | role | start_date | end_date |
|-----------|-----------|------|------------|----------|
| P1 | rotational | IS | 2025-09-21 | 2025-12-14 |
| P2 | rotational | OOS | 2025-12-15 | 2026-03-13 |

P1a/P1b split computed by Stage 01 via `p1_split_rule: midpoint`. Approximate midpoint: ~2025-11-02. P1a = 2025-09-21 to ~2025-11-02. P1b = ~2025-11-02 to 2025-12-14.

### 2.2 Column Schema (35-column, shared across all three bar types)

| Col | Name | Use |
|-----|------|-----|
| 1-2 | Date, Time | Timestamp, session logic, H11, H12, H22 |
| 3-6 | Open, High, Low, Last | Price action, simulator core |
| 7 | Volume | H32, VWAP computation (H9) |
| 8 | # of Trades | H16 (bar quality) |
| 9-11 | OHLC Avg, HLC Avg, HL Avg | Derived averages |
| 12-13 | Bid Volume, Ask Volume | H6 (imbalance) |
| 14 | Zig Zag | ZZ value |
| 15 | Text Labels | Sparse (values: 10, 12) |
| 16 | Reversal Price | ZZ reversal level, H4 |
| 17 | Zig Zag Line Length | ZZ swing size, H4 |
| 18 | Zig Zag Num Bars | ZZ swing duration, H4 |
| 19 | Zig Zag Mid-Point | ZZ midpoint |
| 20 | Extension Lines | ZZ extensions |
| 21 | Zig Zag Oscillator | H7 |
| 22 | Sum | Summation of Study Subgraph — input for all three SD band sets |
| 23-26 | Top, Bottom, Top MovAvg, Bottom MovAvg | **StdDev_1**: 1.5× SD, 500-bar, Weighted MA — tactical/mean-reversion band (narrow). Values are deviations from center, not absolute prices. H3 |
| 27-30 | Top, Bottom, Top MovAvg, Bottom MovAvg | **StdDev_2**: 4.0× SD, 500-bar, Weighted MA — extreme extension band (wide). Same lookback as StdDev_1, wider multiplier. H3, H23, TDS |
| 31-34 | Top, Bottom, Top MovAvg, Bottom MovAvg | **StdDev_3**: 4.0× SD, 5000-bar, Exponential MA — structural/regime band (macro). 10× longer lookback, defines macro envelope. H3, H5 |
| 35 | ATR | H1, H27, H30 |

**SD Band interpretation for H3 and Trend Defense:**
- StdDev_1 crossing → short-term overextension, primary reversal trigger candidate
- StdDev_2 crossing → extreme move, unlikely to sustain; candidate for add refusal (H23) or TDS Level 1 trigger
- StdDev_3 position → structural context; price near StdDev_3 boundary = macro-extended regime, price near center = compressed
- All values are deviations from center — already normalized, directly comparable across price levels
- Full schema documented in `stages/01-data/references/bar_data_rot_schema.md`

### 2.3 Computed Features (derived in pipeline, no export needed)

| Feature | Source | Hypotheses |
|---------|--------|------------|
| Rolling SD of Close | Close prices | H8, H10, H30 |
| Price Z-score | Close, rolling mean, rolling SD | H10 |
| VWAP + SD bands | Price, Volume, Timestamps | H9 |
| Price ROC | Close prices | H28, H31 |
| Price acceleration | Close prices (2nd derivative) | H29 |
| ATR ROC | ATR column | H27 |
| Volume ROC | Volume column | H32 |
| Session range position | High, Low, Timestamps | H26 |
| Bar duration | Timestamps | H16, H33, H34 |
| HTF synthetic bars | Aggregated from primary bars | H25 |
| Retracement depth | High, Low within cycle | Trend Defense |
| Cycle PnL | Simulator internal | H21, Trend Defense |
| PriceSpeed | Close delta / timestamp delta (points per second) | H33, H40, Trend Defense |
| Absorption rate proxy | AskVol / bar_duration, BidVol / bar_duration | H34 |
| Imbalance trend | Rolling slope of (AskVol - BidVol) / (AskVol + BidVol) | H35, H38 |
| Adverse move speed | PriceSpeed filtered to only adverse-direction bars relative to position | H36, H39, Trend Defense |
| Bar formation rate | Rolling bars-per-minute (vol/tick series only) | H37 |
| Regime transition speed | Combined derivative of ATR ROC + imbalance slope + momentum acceleration | H38 |
| Cycle adverse velocity ratio | Adverse leg speed / prior favorable leg speed within cycle | H39, Trend Defense |
| Band-relative speed state | Speed × StdDev band position classification matrix | H40 |
| Band-relative ATR state | ATR direction × StdDev band position classification | H41 |

**Cross-bar-type derived features (require reference data from other series):**

| Feature | Source | Consumers |
|---------|--------|-----------|
| Trade size regime | Vol bar rate / tick bar rate over aligned time window | All filters, TDS |
| Activity concentration | Vol bars + tick bars completing per 10-sec window | H13, H37, TDS |
| Price path efficiency | Time-series path / vol-series path over aligned window | All Dim A triggers, TDS |
| Feature agreement score | Cross-series correlation of ATR, imbalance, momentum | All filters (confidence weighting) |
| Lead-lag signal | Temporal cross-correlation of features across series | H19, all Dim F dynamics |
| Cycle quality agreement | Cross-series cycle PnL agreement for completed cycles | H17 (cycle feedback) |

These features are only computable when reference data from other bar types is available. They are produced by the cross-bar-type feature engineering layer (Section 2.5) and made available to any hypothesis or TDS detector via the FeatureComputer.

### 2.4 Multi-Bar-Type Operation

**This is Pipeline Gap G-01 (HIGH severity). See Section 5 for full resolution.**

The rotational archetype operates on **all three bar types as primary execution series**:
- **250-vol** — activity-sampled, clusters during active periods, ~138k bars P1
- **250-tick** — event-sampled, more uniform than vol, ~128k bars P1
- **10-sec RTH-filtered** — time-sampled, fixed cadence, ~250k bars P1 after RTH filter (9:30–16:00 ET). **Session-filtered to remove overnight/pre-market bars** where near-zero activity produces noise reversals not present in the activity-sampled series.

The strategy runs independently on each bar type. Results are systematically compared in Phase 1b (cross-bar-type analysis, Section 3.7) to classify hypothesis robustness.

**RTH filter consistency for cross-bar-type comparison:** The 10-sec series is RTH session-filtered (9:30–16:00 ET) to remove overnight noise. For Phase 1b cross-bar-type analysis to be valid, the vol and tick series should also be RTH-filtered when computing comparison metrics. Otherwise a hypothesis might appear to fail on 10-sec not because of the sampling method but because overnight bars were excluded. **Implementation: apply RTH filter to all three series for Phase 1b comparison runs. The unfiltered vol/tick runs (including overnight) are also valuable — they show full-session performance — but cross-bar-type comparisons must use consistent time windows.**

**10-sec bars also serve as the reference layer** for VWAP computation (H9), time-based conditioning (H11, H22), HTF aggregation (H25), and bar-type divergence (H19) when running on vol/tick primary series.

**H19 specifically** requires cross-referencing between series at runtime — at any given bar on Series A, the simulator must look up the most recent state of Series B and C via as-of timestamp alignment.

### 2.5 Cross-Bar-Type Feature Engineering Layer

**The three bar types sample the same market with different clocks. When those clocks disagree, the disagreement itself is a signal about market microstructure that's invisible to any individual series.** This section defines a systematic feature engineering layer that extracts derived signals from the relationships between the three series. These are not hypotheses — they are inputs available to any hypothesis or TDS detector.

**Implementation:** The FeatureComputer precomputes these features using reference data (the other two series loaded via as-of timestamp index). When running on 250-vol as primary, the 250-tick and 10-sec series are available as reference. Cross-bar-type features are computed once as static features, then available at each bar index i using only data from bars 0..i (**Entry-Time Only rule applies**).

**CBT-1: Trade Size Regime**

Vol bars complete after 250 contracts. Tick bars complete after 250 trades. If vol bars are completing much faster than tick bars in the same wall-clock window, average trade size is large — fewer trades moving more volume means institutional/block activity. If tick bars are faster, trade size is small — retail-dominated flow.

```
trade_size_regime = vol_bars_per_minute / tick_bars_per_minute
```

- Ratio > 1.5 → large institutional trades (sustained directional risk, adds dangerous)
- Ratio ≈ 1.0 → normal trade size mix
- Ratio < 0.7 → small retail trades (choppier flow, rotation-friendly)

**CBT-2: Activity Concentration**

Count how many vol bars and tick bars complete within each 10-sec window. High count = bursty activity. Low/zero count = quiet. This gives a granular activity heat map that no single series reveals.

```
activity_burst = vol_bars_in_10sec_window + tick_bars_in_10sec_window
```

- High burst count → market is active, potentially trending, TDS should be alert
- Low burst count → quiet, rotation likely safe
- Sustained high burst → regime may be shifting (ties to H38 regime transition speed)

**CBT-3: Price Path Efficiency**

Compare total price path traveled across bar types over the same wall-clock period. Sum of absolute bar ranges on the vol series vs the time series over an aligned N-second window.

```
path_efficiency = time_series_path / vol_series_path
```

- Ratio near 1.0 → price moving cleanly in one direction (trending), rotation dangerous
- Ratio near 0.3-0.5 → price churning back and forth (mean-reverting), rotation works
- This is a fundamentally different measure from ATR or momentum — it captures the fractal structure of the price path

**CBT-4: Feature Agreement Score**

For any feature computed on all three series (ATR, imbalance, momentum, z-score), compute the cross-series agreement:

```
agreement = 1 - normalized_std_across_series(feature_value)
```

- High agreement (near 1.0) → stable regime, signals are trustworthy, weight them normally
- Low agreement (near 0.0) → regime is ambiguous, signals should be weighted down or strategy should go conservative
- Can be computed per-feature or as a composite across all features

**CBT-5: Lead-Lag Detection**

One bar type may consistently signal state changes before the others. Compute rolling cross-correlation between feature values on series A vs series B at various time offsets.

```
lead_lag = argmax(cross_correlation(feature_A, feature_B, offsets))
```

- Tick leading vol on momentum → tick bars are first to register direction change
- Vol leading tick on volatility → volume surges before trade count catches up
- These relationships shift through the day and by regime — the current lead-lag state itself is a feature

**CBT-6: Cycle Quality Agreement**

After each completed cycle, compare the cycle's PnL across all three series (same wall-clock window, different bar sampling). Cycles where all three agree (all profitable or all losing) are structurally cleaner than cycles with mixed results.

```
cycle_agreement = sign(pnl_vol) == sign(pnl_tick) == sign(pnl_10sec)
```

- All agree profitable → high-quality cycle, current conditions favor rotation
- All agree losing → conditions are hostile across all sampling methods
- Mixed → ambiguous, next cycle is less predictable
- Feeds into H17 (cycle performance feedback) as a cross-series quality signal

**Availability:** All six CBT features are available to every hypothesis and TDS detector. They are not toggled on/off like individual hypotheses — they are always computed when reference data is present. Individual hypotheses and TDS detectors choose whether to consume them.

---

## 3. Research Plan — 41 Hypotheses

**Reminder: The unit of analysis is the CYCLE (reversal-to-reversal, including all adds). All Phase 1 metrics are cycle-level.**

### 3.1 Dimension A — Trigger Mechanism (5 hypotheses)

These compete head-to-head as replacements for the fixed-point StepDist. Each is tested independently against baseline. Only one Dimension A hypothesis is active in any given experiment.

| ID | Name | Description | Data source |
|----|------|-------------|-------------|
| H1 | ATR-scaled step | `StepDist = multiplier × ATR` | Col 35 |
| H3 | SD band triggers | Reverse when price crosses SD band boundary. Three band sets with distinct characters: StdDev_1 (1.5×, 500-bar, tactical), StdDev_2 (4.0×, 500-bar, extreme), StdDev_3 (4.0×, 5000-bar, structural). Values are deviations from center, already normalized. | Cols 23-34 |
| H8 | SD-scaled step from anchor | `StepDist = multiplier × rolling_SD(Close, N)` | Computed |
| H9 | VWAP SD bands | Reverse when price crosses VWAP ± K×SD | Computed from Price/Vol/Time (10-sec series preferred) |
| H10 | Price z-score threshold | Reverse when `abs((Price - rolling_mean) / rolling_SD) > threshold` — no anchor concept | Computed |

**Parameters to sweep (Phase 1):**
- H1: multiplier ∈ [0.2, 0.3, 0.4, 0.5, 0.75, 1.0], ATR lookback = column 35 native
- H3 variants (test each independently):
  - H3a: Reverse at StdDev_1 boundary (tactical mean-reversion trigger)
  - H3b: Reverse at StdDev_2 boundary (extreme extension trigger)
  - H3c: Reverse at StdDev_1 but only when StdDev_3 confirms structural extension (composite)
  - H3d: Use StdDev_1 for reversals, StdDev_2 as add-refusal boundary (ties to H23/TDS)
  - For each: test Top/Bottom vs MovAvg variants
- H8: multiplier ∈ [0.3, 0.5, 0.75, 1.0, 1.5], lookback ∈ [20, 50, 100, 200]
- H9: K ∈ [1.0, 1.5, 2.0, 2.5], VWAP reset = session vs rolling
- H10: threshold ∈ [1.5, 2.0, 2.5, 3.0], lookback ∈ [50, 100, 200]

### 3.2 Dimension B — Symmetry Modifier (1 hypothesis)

Orthogonal to Dimension A. Applies as a modifier to any trigger mechanism.

| ID | Name | Description |
|----|------|-------------|
| H2 | Asymmetric reversal vs add thresholds | Separate multiplier for reversal trigger and add trigger. e.g., reverse at 1.0×ATR but add at 0.5×ATR |

**Parameters to sweep:** reversal_multiplier / add_multiplier ratio ∈ [0.5, 0.75, 1.0, 1.5, 2.0]

### 3.3 Dimension C — Conditional Filters (16 hypotheses)

Each independently toggleable. Multiple can be active simultaneously. Each tested first in isolation against baseline.

| ID | Name | Description | Data source |
|----|------|-------------|-------------|
| H4 | ZZ swing confirmation | Require ZZ reversal signal within N bars of step trigger | Cols 14-18 |
| H5 | Regime-conditional parameters | Step multiplier varies by HMM regime state | Regime model (refit on rotational data — see Gap G-07) |
| H6 | Bid/Ask volume imbalance | Skew reversal/add behavior based on directional volume (static snapshot per bar) | Cols 12-13 |
| H7 | ZZ Oscillator gating | Gate adds at extreme oscillator values; suppress at moderate | Col 21 |
| H11 | Time-of-day conditioning | Session segment (pre-market/open/midday/close/overnight) modifies parameters | Cols 1-2 |
| H12 | Day-of-week conditioning | Day-specific parameter adjustment | Col 1 |
| H16 | Bar formation quality filter | Suppress actions on bars with extreme # of Trades or formation speed | Col 8, timestamps |
| H17 | Cycle performance feedback | Adjust behavior based on last N cycle outcomes (win/loss, duration) | Simulator internal |
| H33 | PriceSpeed filter | Suppress reversals/adds when price velocity (points per second, Close delta / timestamp delta) exceeds threshold. Fast price = trending, rotation dangerous. Slow price = choppy, rotation works. **Distinct from H28 (ROC per bar) because this is per clock time — captures urgency.** Also feeds into TDS as a detector. | Close, timestamps |
| H34 | Absorption rate proxy | `AskVol / bar_duration` and `BidVol / bar_duration` as absorption rate approximations. Low absorption both sides = quiet market, rotation-friendly. High asymmetric absorption = directional pressure, adds dangerous. **Proxy for order book persistence — true persistence requires L2 data we don't have.** | Cols 12-13, timestamps |
| H35 | Imbalance trend | Rolling slope of `(AskVol - BidVol) / (AskVol + BidVol)` over N bars. Flat/oscillating = balanced flow, rotation works. Sustained directional slope = one side dominating, rotation at risk. **Extends H6 from static snapshot to directional signal.** | Cols 12-13 |
| H36 | Adverse move speed | Speed of price movement specifically against current position direction (points per second, adverse only). Fast adverse = trending against you, suppress adds. **Distinct from H33 which is direction-agnostic.** Fast move in your favor is fine; fast move against you is what kills the strategy. Feeds directly into TDS threat escalation. | Close, timestamps, simulator state (direction) |
| H37 | Bar formation rate | Rolling bars-per-minute on vol/tick series. High rate = active/hot market, potentially trending. Low rate = quiet, rotation-friendly. **On 10-sec series this is constant by definition — only meaningful on activity-sampled bars.** Direct market pace signal connecting to the finding that rotation works when price moves slowly. | Timestamps |
| H39 | Cycle adverse velocity ratio | Within current cycle: speed of adverse leg / speed of prior favorable leg. Ratio > 1 = adverse move is faster than what generated the entry, market character has changed mid-cycle. **Feeds directly into TDS threat escalation and H23 (conditional adds).** | Simulator internal (cycle tracking) |
| H40 | Band-relative speed regime | Classify each bar into speed × band-position states. Inside StdDev_1 + slow = rotation-friendly. Outside StdDev_2 + fast = danger zone (breakout/trend). Outside StdDev_2 + slow = exhaustion/recovery opportunity (adds safer). **Composite of location and speed — same speed has completely different implications based on where price is relative to bands.** | Cols 23-30 (StdDev_1/2), H33 (PriceSpeed) |
| H41 | Band-relative ATR behavior | ATR expanding while price outside bands = trend strengthening, suppress all adds. ATR contracting while outside bands = move losing steam, adds safer. ATR expanding inside bands = volatility regime shift incoming (ties to H30 squeeze breakout). **Location-aware volatility assessment.** | Col 35 (ATR), Cols 23-30 |

### 3.4 Dimension D — Structural Modifications (10 hypotheses)

Each changes the fundamental cycle mechanics. Tested independently against baseline. **These are the most architecturally significant hypotheses** because they alter the state machine itself, not just its parameters.

| ID | Name | Description |
|----|------|-------------|
| H13 | Selective flat periods | Define conditions where strategy flattens and pauses instead of always rotating. **Breaks the always-in-market assumption.** |
| H14 | Adaptive martingale progression | Add multiplier or max levels adjusts based on market state. **Changes the fixed 1→2→4→8 sizing.** |
| H15 | Alternative anchor strategies | Anchor = original cycle entry, or average entry, or reset on reversal only (not on adds). **Changes how distance is measured.** |
| H20 | Partial rotation | Scale out instead of full flatten; or reverse with size proportional to cycle profit. **Breaks the total-flatten-and-reverse pattern.** |
| H21 | Cycle profit target | Exit on PnL threshold (ticks, ATR multiples, or function of max adverse excursion). **Adds an exit mechanism that doesn't exist in baseline.** |
| H22 | Cycle time decay | Force action if cycle exceeds N bars/minutes without resolving. **Adds a time-based exit that doesn't exist in baseline.** |
| H23 | Conditional adds | Adds require secondary confirmation (volume, ZZ, momentum) beyond just price distance. **Introduces the concept of "refused adds" — the strategy can decline to escalate.** |
| H24 | Intra-cycle de-escalation | Trim position back toward base size on adverse conditions while at Level 2+. **Allows the strategy to reduce exposure without full reversal.** |
| H25 | Higher-timeframe context | Derive HTF trend/structure signal; bias reversal direction toward HTF trend. **Breaks the single-timeframe assumption.** |
| H26 | Session range position | Condition behavior on where price sits within developing session range. **Adds location awareness.** |

### 3.5 Dimension E — Cross-Data & Directional (2 hypotheses)

| ID | Name | Description |
|----|------|-------------|
| H18 | Directional asymmetry | Structurally different parameters for long vs short exposure. **Breaks the symmetric assumption.** |
| H19 | Bar-type divergence signal | Use agreement/disagreement between vol, tick, and time series as confidence signal. **Requires multi-source data loading (Gap G-01).** |

### 3.6 Dimension F — Dynamics (7 hypotheses)

These capture how volatility, momentum, and volume are **changing**, not their static levels.

| ID | Name | Description | Data source |
|----|------|-------------|-------------|
| H27 | Volatility rate of change | ATR expanding/contracting — derivative of volatility | Col 35 |
| H28 | Price momentum / ROC | Rate of change of Close as directional filter | Computed |
| H29 | Acceleration / deceleration | Second derivative of price — momentum exhaustion detection | Computed |
| H30 | Volatility compression breakout | Squeeze detection — shift posture pre/post compression | Col 35 or computed SD |
| H31 | Momentum divergence from price | Price extends but momentum weakens — classic divergence | Computed |
| H32 | Volume rate of change | Rising/declining volume confirms or denies move quality | Col 7 |
| H38 | Regime transition speed | Rate of change of regime indicators (ATR derivative + imbalance trend slope + momentum acceleration combined). Detects how fast the market is shifting from rotation-friendly to trending. **Faster transition = earlier TDS engagement needed.** Composite derivative — measures acceleration of the regime shift itself, not just the individual components. | Computed (combines H27, H29, H35 derivatives) |

### 3.7 Research Execution

**Phase 1 — Independent screening:**
- 41 hypotheses × 3 primary bar types (250-vol, 250-tick, 10-sec RTH-filtered) = 122 meaningful experiments (H37 excluded from 10-sec — bar formation rate is constant on fixed-cadence series; auto-classified as N/A in Phase 1b)
- Each tested in isolation against the fixed-step baseline on each bar type
- **10-sec bars are RTH session-filtered** (9:30–16:00 ET / 8:30–15:00 CT) before simulation to remove overnight/pre-market bars where near-zero activity produces noise reversals not present in the activity-sampled series. This makes results comparable across all three bar types.
- Metric: cycle-level PF, cycle Sharpe, max DD, worst-cycle PnL (defined in Section 7)
- **Reminder: Entry-Time Only rule applies — all features at bar i use only data from bars 0..i**

**Phase 1b — Cross-bar-type analysis:**

Before advancing to combination testing, systematically compare Phase 1 results across the three bar types. This is an analytical step, not an experiment — it produces a classification for each hypothesis that determines how it advances.

**Classification framework:**

| Pattern | Interpretation | Advancement decision |
|---------|---------------|---------------------|
| Wins on all 3 bar types | **Robust signal** — captures real market structure independent of sampling method. Strongest evidence. | Advance to Phase 2 with high confidence |
| Wins on 250-vol and 250-tick, fails on 10-sec | **Activity-dependent signal** — works when there's market activity but not on fixed-cadence bars. May indicate the signal depends on volume/activity clustering. | Advance to Phase 2 but flag as requiring session-filtered deployment. Investigate whether the failure is concentrated in early/late RTH where activity patterns differ. |
| Wins on one activity-sampled type only (vol or tick, not both) | **Sampling-coupled signal** — likely an artifact of how that specific bar type samples price action, not a real market feature. | Do not advance. Investigate why it diverges — the divergence itself is informative. |
| Wins on 10-sec only, fails on vol and tick | **Time-dependent signal** — works on fixed cadence but not activity-sampled bars. Likely capturing time-based patterns (session structure, clock-driven events) rather than price/volume dynamics. | Advance cautiously — may have value as a time-based filter (H11/H12) but not as a core trigger. |
| Fails on all 3 bar types | **No signal** — hypothesis does not improve on the optimized baseline regardless of sampling. | Drop from further testing. |

**Specific cross-bar-type questions to answer:**

1. **Does the optimized fixed-step baseline differ across bar types?** If the best StepDist is 2.5 on vol, 3.0 on tick, and 1.5 on 10-sec, that tells you the optimal step is sampling-dependent — which means adaptive scaling (H1, H8) is likely to outperform any fixed value.

2. **Do Dimension A winners agree?** If ATR-scaling (H1) wins on vol but SD-scaling (H8) wins on tick, the trigger mechanism is not universal — the choice should be conditioned on bar type, or a composite trigger that works across all three should be prioritized.

3. **Do cycle characteristics differ?** Average cycle duration, adds per cycle, and max-level exposure may differ systematically across bar types. Shorter cycles on vol (fewer bars per cycle due to activity clustering) vs longer cycles on 10-sec (more bars per cycle at fixed cadence) — this affects Trend Defense parameter tuning.

4. **Where do time-based filters (H11, H12) add the most value?** H11/H12 may show strong results on 10-sec (natural time alignment) but weaker results on vol/tick (where bar timestamps are irregular). If so, the time filter should be applied via the 10-sec reference layer even when running on vol/tick primary series.

5. **What does H19 (bar-type divergence) show when all three are primary?** With three series running independently, you can now measure whether divergence between series predicts the next N bars on any given series. This is the richest form of cross-bar-type signal.

**Phase 1b output:** A ranked list of hypotheses classified by robustness pattern, with advancement decisions and notes on bar-type-specific behavior. This feeds directly into Phase 2 combination selection.

**Phase 2 — Combination testing:**
- Dimension A winner (from Phase 1b, robust signals prioritized) × H2 on/off × each Dimension C winner × each Dimension D winner × H18/H19
- Exact count depends on Phase 1/1b results
- **Run on all 3 bar types** — combinations must show consistent improvement across bar types to advance
- Cross-bar-type analysis repeated: combinations that only work on one bar type are flagged

**Phase 3 — Trend Defense integration (Section 4):**
- Best combination from Phase 2 + Trend Defense System levels
- Measured on both alpha metrics AND survival metrics (Section 7)
- **TDS parameters may need bar-type-specific tuning** — velocity thresholds and cooldown periods depend on bar cadence (130k vs 250k bars, different bar durations)
- Run on all 3 bar types

**Budget:** ~2,400 experiments total across all phases (252 sweep + 366 Phase 1 screening per profile × 3 profiles + Phase 1b analysis + TDS per profile + Phase 2 combinations per profile + Phase 3 integration per profile). Exact count depends on Phase 1b advancement rates per profile.

---

## ── MID-DOCUMENT ANCHOR ──

**Where we are:** Phases A, B, and initial calibration are complete. The simulator, profiles, TDS, and anchor mode have been validated through ~1,250 P1a experiment runs. Phase 04 (hypothesis screening) is next.

**Key findings to carry forward:**
- **Martingale is net negative** — winning configs use ML=1 with MTP=1 or MTP=2. No geometric escalation.
- **Frozen anchor on MTP refusal is correct** — patience through adverse moves IS the edge.
- **TDS L3 (forced exits) destroys the strategy** — TDS disabled for vol/tick, velocity-only L1 for 10sec.
- **MTP IS the risk management** — position size cap, not exit rules.
- **Sections below retain original design documentation** but Sections 4 (TDS) and 5 (gaps) are now implemented with empirical results recorded in Executive Summary.

**Key context to carry forward:**
- The unit of analysis is the **CYCLE** (reversal-to-reversal including all adds), not individual trades
- **No scoring adapter** — decision logic lives inside the simulator, not a separate scoring layer
- **Three primary bar types** — 250-vol, 250-tick, 10-sec (RTH-filtered). Strategy runs independently on each. Cross-bar-type analysis (Phase 1b) classifies robustness before combination testing.
- **Entry-Time Only** rule applies to all feature computation

---

## 4. Trend Defense System

**⚠️ CALIBRATION RESULT (Phase 03.1): TDS is largely incompatible with the rotational edge at winning profile settings (MTP=1-2). L3 force-flatten fires on virtually every cycle and destroys profitability. L2 refuse_adds is dead code at MTP≤2. Only L1 velocity step-widening shows benefit, and only on 10sec bars. TDS disposition: disabled for vol/tick, velocity-only L1 for 10sec. The design below is retained as documentation of the full system, which may become relevant if future profiles use higher MTP values.**

### 4.1 Purpose

Dedicated subsystem to detect and respond to straight-line moves — the strategy's primary failure mode (see Section 1.5). This is NOT a hypothesis — it's a coordinated multi-level response system. Evaluated separately from the 41 alpha hypotheses on survival metrics, then integrated with the best alpha configuration.

### 4.2 Detection Layer

All detectors run continuously during simulation. Each produces a threat score.

| Detector | What it measures | Trigger condition |
|----------|-----------------|-------------------|
| Retracement quality | Depth of pullbacks within current cycle | Pullback depth declining over consecutive swings |
| Velocity monitor | Speed of martingale level escalation | Level 0 → Level N in fewer than K bars |
| Consecutive add counter | Adds without qualifying retracement | N adds without any retracement reaching X% of step distance |
| Drawdown budget | Cycle unrealized PnL | Exceeds max allowed cycle drawdown (ticks or ATR-scaled) |
| Trend precursor composite | Volatility expansion + momentum + volume confirmation | Multiple precursors align simultaneously |

**Hypothesis feed-ins to TDS detectors:** Several Dimension C filters directly enhance TDS when active:
- **H33 (PriceSpeed)** and **H36 (Adverse move speed)** feed into the Velocity monitor and Trend precursor composite — fast adverse price movement is the most direct signal that a straight-line move is in progress
- **H39 (Cycle adverse velocity ratio)** feeds into the Retracement quality and Velocity monitors — adverse leg faster than favorable leg means market character has shifted
- **H40 (Band-relative speed regime)** feeds into the Trend precursor composite — the "outside StdDev_2 + fast speed" state is a direct Level 1 trigger candidate
- **H38 (Regime transition speed)** feeds into all detectors as an early-warning amplifier — fast regime transitions should lower thresholds for all detectors

When these hypotheses are active, their computed values are available to the TDS detectors as additional input signals. When inactive, TDS operates on its five core detectors only.

### 4.3 Response Escalation

Responses are tiered. Higher levels override lower levels. Each level is independently testable.

**Level 1 — Early Warning:**
- Trigger: Retracement quality declining OR trend precursors aligning
- Response: Widen step distance by factor (e.g., 1.5×), suppress next add level (reduce MaxLevels by 1)
- Effect: Strategy becomes more conservative but stays in market

**Level 2 — Active Threat:**
- Trigger: Velocity circuit breaker OR consecutive adds without retracement
- Response: Refuse all further adds, begin de-escalation (trim position toward InitialQty)
- Effect: Strategy caps its risk exposure, starts reducing

**Level 3 — Emergency:**
- Trigger: Cycle drawdown budget hit OR max-level position with continued adverse momentum
- Response: Force flatten, enter cooldown period (FLAT state for N bars or until conditions normalize)
- Re-engagement: Qualifying retracement occurs, or cooldown period expires and threat detectors are below Level 1

### 4.4 Max-Level Position Special Handling

When at max martingale level and offside, switch exit logic:
- Standard reversal threshold → reduced threshold (e.g., breakeven on average entry, or 50% of normal StepDist)
- Purpose: escape max-exposure positions faster, accept reduced profit

### 4.5 Parameters (per level)

| Parameter | Level 1 | Level 2 | Level 3 |
|-----------|---------|---------|---------|
| Step widen factor | 1.25–2.0 | N/A (adds refused) | N/A (flat) |
| MaxLevels reduction | -1 | all adds refused | N/A |
| De-escalation rate | None | trim 1 level per N bars | immediate flatten |
| Cooldown bars | None | None | 50–500 |
| Re-engagement condition | Auto (threat subsides) | Qualifying retracement | Cooldown + threat < L1 |

### 4.6 Assessment Metrics (survival-specific)

These metrics are computed when Trend Defense is active and stored in `extended_metrics.trend_defense`. They complement the broader assessment metrics in Section 7.2.

| Metric | Description | Cross-ref |
|--------|-------------|-----------|
| Worst-cycle drawdown (ticks) | Maximum unrealized loss in any single cycle | Also in `cycle_core.worst_cycle_dd_ticks` |
| Worst-cycle drawdown (ATR-normalized) | Same, normalized by ambient ATR | Also in `cycle_core.worst_cycle_dd_atr` |
| Max-level exposure bars | Number of bars spent at MaxLevels across all cycles | Also in `cycle_core.max_level_exposure_bars` |
| Max-level exposure % | Proportion of total bars at MaxLevels | Also in `cycle_core.max_level_exposure_pct` |
| Consecutive-add-without-retracement max | Longest streak of adds without qualifying pullback | TDS-specific |
| Drawdown budget hit count | How many times Level 3 was triggered | `trend_defense.l3_triggers` |
| Recovery time after Level 3 | Bars from flatten to re-engagement | `trend_defense.l3_recovery_bars_avg` |
| Tail ratio | P95 cycle PnL / P5 cycle PnL | Also in `cycle_core.tail_ratio_p95_p5` |
| PnL saved estimate | Estimated ticks saved by TDS intervention vs no-TDS baseline | `trend_defense.pnl_saved_estimate_ticks` |

**TDS effectiveness is measured by comparing WITH-TDS and WITHOUT-TDS runs on the same data.** Key comparisons: worst-cycle DD reduction, max-level exposure % reduction, tail ratio improvement, and total PnL impact (TDS may reduce tail risk but also reduce gross profit by exiting early).

---

## 5. Pipeline Architecture — Gap Analysis

**10 gaps identified. 3 were HIGH severity. All proposed resolutions have been implemented (except G-07 HMM refit and G-10 Bonferroni, both deferred). The descriptions below serve as design documentation for the implemented solutions. See the gap status table in the Executive Summary for current status.**

### G-01: Multi-Source Data Loading [HIGH]

**Current state:** `data_manifest.json` resolves one `bar_data` source per archetype. `backtest_engine.py` loads a single bar series via `simulator_module`.

**Rotational need:** Three bar types loaded and timestamp-aligned for a single simulation run (250-vol, 250-tick, 10-sec).

**Proposed resolution:**
- Extend `data_manifest.json["archetypes"]["rotational"]` schema:
```json
{
  "data_sources": {
    "primary": ["bar_data_250vol_rot", "bar_data_250tick_rot", "bar_data_10sec_rot"],
    "reference": ["bar_data_10sec_rot"]
  },
  "periods": { ... }
}
```
- `primary` = series the strategy runs on independently (separate simulation per primary source). 10-sec is RTH session-filtered before simulation.
- `reference` = series loaded as supplementary data within each simulation (available via lookup, not iterated). 10-sec appears in both lists: it runs as its own primary AND serves as reference for vol/tick runs.
- Simulator's data loader builds an as-of timestamp index for reference series
- `rotational_engine.py` passes both primary bars and reference bars to the simulator

**Impact on existing pipeline:** Additive. Zone_touch continues using the single-source pattern (its `data_sources.primary` list has one entry, no `reference`). No breaking changes.

### G-02: Simulator Interface — Continuous State Machine [HIGH]

**Current state:** Zone_touch simulator processes discrete touch events. The `backtest_engine.py` is tightly coupled to the touch-based flow: config validation requires `touches_csv` and `bar_data`, `load_data()` expects one touch file + one bar file, scoring always loads an adapter, and `run_simulations()` iterates over touch rows calling `simulator.run(bar_df, touch_row, config, bar_offset)`. The existing engine has a CLAUDE.md hard prohibition on modification.

**Rotational need:** Simulator iterates over every bar in the primary series, maintaining internal state (direction, anchor, level, position qty, cycle tracker), and makes state transition decisions on each bar. There are no pre-scored "events" — every bar is a potential action bar. The touch-based interface does not fit.

**Proposed resolution — separate `rotational_engine.py`:**
- Create `rotational_engine.py` in `shared/archetypes/rotational/`
- Purpose-built for continuous simulation: loads multiple bar sources, skips scoring, iterates all bars
- `backtest_engine.py` stays frozen — zone_touch engine untouched, CLAUDE.md prohibition honored
- Archetype config or runner script selects which engine to invoke based on archetype
- Interface contract: engine receives archetype config → loads data → invokes simulator → writes results

```python
class RotationalEngine:
    def __init__(self, config, profile="max_profit"):
        """
        config: archetype config with data_sources, hypothesis params, TDS config
        profile: one of "max_profit", "safest", "most_consistent"
                 Loads baseline params (StepDist, MaxLevels, MaxTotalPosition)
                 from shared/archetypes/rotational/profiles/{profile}.json
        """

    def run(self, period="P1a") -> SimulationResult:
        """
        1. Load profile baseline from profiles/{profile}.json
        2. Load primary bar data + reference data from data_manifest
        3. Apply RTH filter if 10-sec series
        4. Instantiate RotationalSimulator with config + profile params + data
        5. Call simulator.run()
        6. Compute extended_metrics from SimulationResult
        7. Generate run_id: sha1(archetype + profile + timestamp + n)[:7]
        8. Write complete row to dashboard/results_master.tsv:
           - Cols 1-24: run_id, stage, timestamp, hypothesis_name, archetype,
             version, features, pf_p1, pf_p2, trades_p1, trades_p2, mwu_p,
             perm_p, pctile, n_prior_tests, verdict, sharpe_p1, max_dd_ticks,
             avg_winner_ticks, dd_multiple, win_rate, regime_breakdown,
             api_cost_usd, notes
           - Col 25: extended_metrics (JSON blob, Section 7.2)
                     includes "profile" field tagging which profile was used
           NOTE: pf/trades/sharpe/win_rate computed on CYCLES, not trades
        9. Append event to audit/audit_log.md
        """
```

**Results output contract:** `rotational_engine.py` writes to `dashboard/results_master.tsv` in the same 25-column format as the zone_touch engine. All universal columns (1-24) use cycle-level values. The `archetype` column (col 5) = "rotational". The `n_prior_tests` column (col 15) is incremented per experiment for Bonferroni correction (G-10). The `extended_metrics` JSON (col 25) includes a `"profile"` field so results are always tagged to their profile.

**Impact on existing pipeline:** None. Zone_touch engine completely untouched. New engine is additive.

### G-03: Scoring Adapter Concept Does Not Apply [Resolved by G-02]

**Current state:** All three scoring adapters (`BinnedScoringAdapter`, `SklearnScoringAdapter`, `ONNXScoringAdapter`) implement `score(touch_df) → pd.Series`. The backtest engine scores touches, then passes scored touches to the simulator.

**Rotational need:** There are no touches to score. The "signal" is the state machine's internal logic — distance from anchor, ATR level, SD band position, etc. All decision logic lives inside the simulator.

**Resolution:** Resolved by G-02 (separate `rotational_engine.py`). The rotational engine has no scoring step — it loads bar data and passes it directly to the simulator. No modification to `backtest_engine.py` needed. The original spec proposed a null check in `backtest_engine.py`, but with a separate engine this is unnecessary.

**Note:** The original handoff doc mentioned a `RankingAdapter` for rotational. That was based on an incorrect assumption that rotational meant multi-instrument comparative ranking. With the actual C++ logic understood, no RankingAdapter is needed. If a future multi-instrument rotation archetype is added, `RankingAdapter` can be revisited then.

### G-04: Feature Evaluation Harness (Stage 02) [HIGH]

**Current state:** `feature_evaluator.py` evaluates features via MWU test on signal rows (touch events with outcomes). Metric: predictive spread > 0.15, MWU p < 0.10.

**Rotational need:** No signal rows exist. Features need to be evaluated for predictive power on bar-level outcomes.

**Proposed resolution:**
- Define bar-level outcomes for feature evaluation:
  - **Outcome 1 (direction):** Did the next N bars move up or down from this bar's close? (Binary)
  - **Outcome 2 (reversal quality):** On bars where a reversal occurred, was the reversal profitable within M bars? (Binary)
  - **Outcome 3 (add quality):** On bars where an add occurred, did the position recover within M bars? (Binary)
- Evaluator logic: compute feature value on each bar → split into terciles → measure outcome distribution per tercile → MWU between extreme terciles
- Same statistical test, different unit of analysis
- Implement as `rotational_feature_evaluator.py` loaded via dynamic dispatch

**Requires Gap G-09** (Stage 02 evaluator dynamic dispatch) to be resolved first.

**Impact on existing pipeline:** New evaluator module. Zone_touch evaluator unchanged.

### G-05: Results Schema — Cycle-Level Metrics [Medium]

**Current state:** 24-col `results_master.tsv` with trade-level aggregate metrics.

**Rotational need:** Cycle-level metrics plus archetype-specific extended metrics (worst-cycle DD, max-level exposure, trend defense triggers, etc.).

**Proposed resolution:**
- Add col 25: `extended_metrics` — JSON blob containing archetype-specific metrics organized into 11 categories: cycle_core, capital_exposure, cost_analysis, profit_concentration, heat, action_efficiency, equity_curve, session_level, dollar_weighted, directional_split, trend_defense (see Section 7.2 for full schema)
- Universal columns (1-24) remain unchanged but are computed on **cycles** for rotational (PF = cycle PF, trades = cycle count, etc.)
- `extended_metrics` schema defined per archetype in `strategy_archetypes.md`
- Stage 05 reads `extended_metrics` for archetype-specific verdict logic — robustness gates (slippage sensitivity, breakeven removal count, asymmetry ratio) consume these metrics directly

**Impact on existing pipeline:** One new column appended. Existing tooling continues working. Dashboard spec updated to parse extended_metrics for rotational rows.

### G-06: Assessment Thresholds (Stage 05) [Medium]

**Current state:** `statistical_gates.md` defines verdict thresholds: PF@3t, Sharpe, MWU p, etc.

**Rotational need:** Martingale strategies inflate PF and win rate by construction (averaging converts losers to small winners while hiding tail risk). Assessment must focus on survival metrics.

**Proposed resolution:**
- Add `[archetype: rotational]` section to `statistical_gates.md` with 4-tier verdict:
  - **Primary gate:** Cycle-level PF ≥ 1.5, cycles ≥ 30
  - **Survival gate:** Worst-cycle DD < limit, max_level_exposure_pct < 15%, max consecutive losing cycles ≤ 5
  - **Robustness gate:** Slippage sensitivity (PF at +0.50 tick ≥ 1.2), breakeven removal count ≥ 10% of cycles, asymmetry ratio < 5:1, cost drag < 35% of gross profit
  - **Replication gate:** Cycle PF on P1b ≥ 1.3
- Verdict categories (PASS, CONDITIONAL, WEAK_REPLICATION, FAIL) remain the same; criteria differ per archetype
- Robustness gates are the key addition vs zone_touch — they catch martingale-specific illusions (concentrated profits, slippage fragility, asymmetric losses hidden by high win rate)
- See Section 7.3 for full verdict logic

**Impact on existing pipeline:** Additive section. Zone_touch thresholds unchanged.

### G-07: HMM Regime Model Refit [Low]

**Current state:** `hmm_regime_v1.pkl` fitted on zone_touch 250-vol bar data.

**Rotational need:** H5 (regime-conditional parameters) requires a regime model fitted on rotational bar data.

**Proposed resolution:**
- Fit separate model: `hmm_regime_rot_v1.pkl`
- Same methodology (3-state HMM, P1-only fit)
- Store in `shared/scoring_models/`
- Regime labels generated for all three bar types via timestamp mapping

**Impact on existing pipeline:** New model file. Existing model untouched.

### G-08: Autoresearch Mapping for Rotational [Medium]

**Current state:** Autoresearch mapping defined for zone_touch only.

**Rotational autoresearch mapping:**
| Stage | Agent edits | Fixed harness | Metric | Budget |
|-------|-------------|---------------|--------|--------|
| 02 | `rotational_feature_engine.py` | `rotational_feature_evaluator.py` | predictive spread > 0.15, MWU p < 0.10 | 300 |
| 03 | `rotational_hypothesis_config.json` | `rotational_hypothesis_generator.py` | P1a cycle PF, replication_pass on P1b | 200 |
| 04 | `rotational_params.json` | `rotational_engine.py` (separate engine, not backtest_engine.py) | P1a cycle PF, survival gates, improve > 0.05 | 500 |

**Config schema for `rotational_hypothesis_config.json`:**
```json
{
  "archetype": "rotational",
  "profile": "max_profit | safest | most_consistent",
  "trigger_mechanism": "atr_scaled | sd_band | sd_scaled | vwap_sd | zscore | fixed",
  "trigger_params": { },
  "symmetry": "symmetric | asymmetric",
  "symmetry_params": { },
  "active_filters": ["H4", "H5", ...],
  "filter_params": { },
  "structural_mods": ["H13", "H15", ...],
  "structural_params": { },
  "trend_defense": { "enabled": false, "level_1": {}, "level_2": {}, "level_3": {} },
  "martingale": {
    "initial_qty": 1,
    "max_levels": 4,
    "max_contract_size": 16,
    "max_total_position": 0,
    "progression": "geometric"
  }
}
```

**Impact on existing pipeline:** New files in `shared/archetypes/rotational/`. Zone_touch autoresearch unchanged.

**Pipeline integration requirements (must match existing conventions):**
- **Feedback loop:** Stage 05 verdict → `prior_results.md` → Stage 03. `rotational_hypothesis_generator.py` reads `prior_results.md` to avoid repeating failed configurations and to build on successful ones. Same pattern as zone_touch.
- **Frozen features:** When Stage 02 feature selection is finalized, create `rotational_frozen_features.json` via human freeze command (same pattern as zone_touch `frozen_features.json`). Once frozen, Stage 02 autoresearch for this archetype stops.
- **Feature registration:** Stage 02 autoresearch registers discovered features in `shared/feature_definitions.md`. Same registry as zone_touch — features are archetype-tagged.
- **run_id generation:** `sha1(archetype + profile + timestamp + n)[:7]` — includes profile name to distinguish experiments across profiles. Generated by `rotational_engine.py`.
- **Profile selection:** `rotational_engine.py` accepts a `--profile` flag (`max_profit`, `safest`, or `most_consistent`) that loads baseline params from `shared/archetypes/rotational/profiles/{profile}.json`. All results tagged with profile name in `extended_metrics`.
- **Event-driven git commits:** `rotational_engine.py` triggers a git commit per kept experiment (improvement over prior best), not on a timer. Same pattern as zone_touch autoresearch (auto-01b/01c). The existing `autocommit.sh` and holdout guard pre-commit hook work at repo level and should function for rotational without modification — holdout guard reads `period_config.md` for P2 boundaries per archetype.
- **Audit log:** `rotational_engine.py` writes key events to `audit/audit_log.md` — baseline established, hypothesis promoted, TDS configuration locked, P1b replication results, P2 promotion decisions. Same append-only format as zone_touch.
- **Verdict report:** Stage 05 writes `verdict_report.md` and `verdict_report.json` to `stages/05-assessment/output/` for rotational, same location as zone_touch but with archetype-tagged filenames or a subdirectory.
- **data_manifest.json:** Read-only for `rotational_engine.py` — only Stage 01 writes it. Never hand-edit.
- **CONTEXT.md:** Each stage's CONTEXT.md updated when rotational work modifies that stage's logic or outputs.

### G-09: Stage 02 Feature Evaluator Dynamic Dispatch [Medium]

**Current state:** Stage 02 has a single feature evaluator implementation. No dynamic dispatch — evaluator is zone_touch-specific.

**Rotational need:** Different evaluation paradigm (bar-level outcomes instead of touch-event outcomes). See G-04.

**Proposed resolution:**
- Add `config.archetype.feature_evaluator_module` to archetype config
- `evaluate_features.py` loads the evaluator module at runtime (same pattern as Stage 04's `simulator_module` dispatch)
- Zone_touch: `feature_evaluator_module: "zone_touch_feature_evaluator"`
- Rotational: `feature_evaluator_module: "rotational_feature_evaluator"`

**Impact on existing pipeline:** Refactor of `evaluate_features.py` to add dispatch. Zone_touch evaluator extracted into own module (currently inline). Functionally identical for zone_touch after refactor.

### G-10: Multiple Testing Correction [Medium]

**Current state:** `statistical_gates.md` includes Bonferroni gates and `results_master.tsv` tracks `n_prior_tests` and `pctile` per row. Zone_touch autoresearch uses these for multiple testing correction.

**Rotational need:** With ~122 Phase 1 experiments per profile (×3 profiles = ~366 total) across 3 bar types, the probability of a false positive at nominal α=0.05 is extremely high. Multiple testing correction is essential. Bonferroni applied per-profile since each profile is an independent research track.

**Proposed resolution:**
- `rotational_engine.py` tracks and increments `n_prior_tests` for each experiment, writes to `results_master.tsv` col 15
- Stage 05 applies Bonferroni-adjusted thresholds: effective α = nominal α / n_prior_tests
- `pctile` (col 14) = rank of this result within all prior rotational results
- Phase 1b cross-bar-type analysis provides structural protection beyond statistical correction — a hypothesis must show consistent improvement across 3 bar types, not just pass on one by chance
- Permutation test on cycle PF vs baseline: shuffle cycle labels, recompute PF, establish null distribution. Bonferroni-adjust the permutation p-value.

**Impact on existing pipeline:** Same mechanism as zone_touch. `rotational_engine.py` writes the same columns. No changes to existing Bonferroni infrastructure.

---

## ── MID-DOCUMENT ANCHOR (Section 6-10) ──

**Where we are:** Sections 1-5 defined the strategy, data, 41 hypotheses, TDS (now calibrated), and 10 pipeline gaps (8 implemented, 2 deferred). The remaining sections are implementation-focused:

- **Section 6:** Simulator design — the continuous state machine, now built and validated (57 tests passing)
- **Section 7:** Assessment metrics — what we measure and how verdicts work (cycle-level, not trade-level)
- **Sections 8-10:** Files created/modified, implementation sequence (Phases A-B complete, C in progress), open questions (8/10 resolved)

**Critical context for Phase 04:**
- **All gaps resolved** except G-07 (HMM refit, deferred) and G-10 (Bonferroni, Phase 05)
- **Anchor freezes on MTP refusal** — validated design decision, do NOT modify
- **TDS disposition**: disabled for vol/tick, velocity-only L1 for 10sec
- **Hypothesis priority**: H11, H13, H33, Dimension A triggers elevated. H14, H23, H24, H39 deprioritized.
- **3 profiles run in parallel** — hypothesis results, combinations, and verdicts are per-profile

---

## 6. Simulator Design

### 6.1 Architecture

```
RotationalSimulator
├── DataLoader
│   ├── load_primary(source_id) → DataFrame
│   └── load_reference(source_id) → DataFrame (as-of timestamp indexed)
├── FeatureComputer
│   ├── compute_static_features(bars) → DataFrame
│   │   (ATR, SD, VWAP, ROC, z-score, SD bands — all precomputed once)
│   ├── compute_cross_bar_type_features(bars, reference_data) → DataFrame
│   │   (CBT-1 through CBT-6: trade size regime, activity concentration,
│   │    path efficiency, feature agreement, lead-lag, cycle agreement
│   │    — precomputed once from primary + reference series alignment)
│   └── compute_dynamic_features(bar_index, state) → dict
│       (cycle PnL, retracement depth, cycle duration — depend on live state)
├── StateMachine
│   ├── state: {direction, anchor, level, position_qty, cycle_id, cycle_start_bar}
│   ├── evaluate_reversal(bar, features, config) → bool
│   ├── evaluate_add(bar, features, config) → bool
│   └── evaluate_trend_defense(bar, features, state) → ThreatLevel
├── TrendDefenseSystem
│   ├── detectors: [RetraceQuality, Velocity, ConsecutiveAdd, DrawdownBudget, TrendPrecursor]
│   ├── current_level: 0 | 1 | 2 | 3
│   └── apply_response(state, level) → modified state/action
├── TradeLogger
│   ├── log_trade(action, bar, state, pnl_info)
│   └── log_cycle(cycle_summary)
└── run() → SimulationResult
       ├── trades: DataFrame (individual actions)
       └── cycles: DataFrame (reversal-to-reversal summaries — PRIMARY assessment unit)
```

### 6.2 Simulation Loop (pseudocode)

**Reminder: Entry-Time Only rule — features at bar i use only data from bars 0..i. No lookahead.**

```python
def run(self):
    static_features = self.feature_computer.compute_static(self.bars)
    # static_features are pre-rolled — value at index i uses only bars 0..i

    cbt_features = self.feature_computer.compute_cross_bar_type(
        self.bars, self.reference_data
    ) if self.reference_data else None
    # CBT features (Section 2.5): trade size regime, activity concentration,
    # path efficiency, feature agreement, lead-lag — precomputed from
    # primary + reference series alignment. None when no reference data.

    for i, bar in enumerate(self.bars):
        features = {
            **static_features.iloc[i],
            **(cbt_features.iloc[i] if cbt_features is not None else {}),
            **self.feature_computer.compute_dynamic(i, self.state)
        }

        # Trend Defense check (if enabled)
        if self.config.trend_defense.enabled:
            threat = self.trend_defense.evaluate(bar, features, self.state)
            self.trend_defense.apply_response(self.state, threat)
            if self.state.forced_flat:
                if self.state.cooldown_remaining > 0:
                    self.state.cooldown_remaining -= 1
                    continue
                elif self.trend_defense.can_reengage(features):
                    self.state.forced_flat = False
                else:
                    continue

        # State machine transitions
        if self.state.position_qty == 0 and self.state.anchor is None:
            self._seed(bar, features)
        elif self._check_reversal(bar, features):
            self._execute_reversal(bar, features)
        elif self._check_add(bar, features):
            self._execute_add(bar, features)

        # Structural mod checks (H21 profit target, H22 time decay, H24 de-escalation)
        self._check_structural_mods(bar, features)

        # Update cycle tracking
        self._update_cycle_metrics(bar)

    return SimulationResult(
        trades=self.trade_logger.trades,
        cycles=self.trade_logger.cycles,  # PRIMARY assessment unit
        bars_processed=len(self.bars)
    )
```

### 6.3 Hypothesis-to-Code Mapping

This table shows exactly where each hypothesis is implemented in the simulator. Grouped by method for clarity.

**Trigger/decision methods (`_check_reversal`, `_check_add`):**

| Hypothesis | What changes |
|------------|-------------|
| H1 (ATR-scaled) | Distance computation: `threshold = multiplier × ATR` instead of fixed points |
| H3 (SD band triggers) | Replace distance check with: `price > StdDev_X_Top` (reversal from long) or `price < StdDev_X_Bottom`. Variants: StdDev_1 (tactical), StdDev_2 (extreme), composite (StdDev_1 + StdDev_3 confirmation) |
| H8 (SD-scaled) | Distance computation: `threshold = multiplier × rolling_SD` |
| H9 (VWAP SD bands) | Replace distance check with: `price crosses VWAP ± K×SD` |
| H10 (Z-score threshold) | Replace distance-from-anchor with: `abs(z_score) > threshold` (no anchor) |
| H2 (Asymmetric) | `_check_reversal` and `_check_add` use different threshold multipliers |
| H4 (ZZ confirmation) | Additional gate: `and zz_reversal_within_N_bars` |
| H6 (Volume imbalance) | Additional gate: `and volume_imbalance_confirms_direction` |
| H7 (ZZ Oscillator) | Additional gate on adds: `and zz_oscillator_at_extreme` |
| H16 (Bar quality) | Additional gate: `and bar_quality_acceptable` |
| H23 (Conditional adds) | Secondary confirmation required before `_check_add` returns True |
| H33 (PriceSpeed) | Additional gate: `and price_speed < threshold` — suppress actions during fast moves |
| H34 (Absorption proxy) | Additional gate: `and absorption_rate_balanced` — suppress adds when asymmetric absorption detected |
| H35 (Imbalance trend) | Additional gate: `and imbalance_slope_flat` — suppress adds when sustained directional imbalance trend |
| H36 (Adverse speed) | Additional gate on adds: `and adverse_move_speed < threshold` — suppress adds when price moving fast against position. Does NOT gate reversals (fast favorable move → reverse is fine). |
| H37 (Bar formation rate) | Additional gate: `and bars_per_minute < threshold` — suppress actions when market pace is hot (vol/tick only) |
| H39 (Cycle velocity ratio) | Additional gate on adds: `and cycle_adverse_velocity_ratio < threshold` — suppress adds when adverse leg is faster than favorable leg |
| H40 (Band-relative speed) | Composite gate: action depends on speed × band-position state matrix. Inside+slow = permit. Outside+fast = suppress adds. Outside+slow = permit adds (exhaustion). |
| H41 (Band-relative ATR) | Composite gate: ATR expanding + outside bands = suppress all adds. ATR contracting + outside bands = permit adds. ATR expanding + inside bands = widen steps (squeeze breakout). |

**Feature computation (`compute_static_features`, `compute_dynamic_features`, `compute_cross_bar_type_features`):**

| Hypothesis | What changes |
|------------|-------------|
| H5 (Regime) | Regime label lookup → parameter override dict |
| H11 (Time-of-day) | Session segment extraction → parameter override dict |
| H12 (Day-of-week) | Day bucket → parameter override dict |
| H17 (Cycle feedback) | Recent cycle outcome tracking → parameter adjustment |
| H19 (Bar divergence) | Cross-series state lookup via reference data as-of index |
| H25 (HTF context) | Aggregate N bars into synthetic HTF bar → trend/structure signal |
| H26 (Session range) | Track developing session high/low → position within range |
| H27 (Vol ROC) | `ATR_ROC = ATR[i] / ATR[i-N] - 1` |
| H28 (Momentum) | `ROC = (Close[i] - Close[i-N]) / Close[i-N]` |
| H29 (Acceleration) | `acceleration = ROC[i] - ROC[i-N]` (2nd derivative) |
| H30 (Vol compression) | `squeeze = rolling_SD < threshold × rolling_SD_long` |
| H31 (Momentum divergence) | Compare price swing direction with ROC swing direction |
| H32 (Volume ROC) | `vol_ROC = Volume[i] / Volume[i-N] - 1` |
| H33 (PriceSpeed) | `price_speed = abs(Close[i] - Close[i-1]) / bar_duration_seconds[i]` (points per second) |
| H34 (Absorption proxy) | `ask_absorb = AskVol[i] / bar_duration[i]`, `bid_absorb = BidVol[i] / bar_duration[i]`, `absorb_asymmetry = ask_absorb / (ask_absorb + bid_absorb)` |
| H35 (Imbalance trend) | `imbalance = (AskVol - BidVol) / (AskVol + BidVol)`, then `imbalance_slope = linear_regression_slope(imbalance, N)` |
| H36 (Adverse speed) | `adverse_speed = price_speed if move_is_against_position else 0` — requires simulator state (direction). Computed in `compute_dynamic_features`. |
| H37 (Bar formation rate) | `bars_per_minute = count(bars in trailing 60 seconds)` — only meaningful on vol/tick series. On 10-sec series this is constant (6/min) and should be disabled. |
| H38 (Regime transition speed) | `regime_accel = normalize(ATR_ROC_derivative) + normalize(imbalance_slope_derivative) + normalize(momentum_acceleration_derivative)` — composite second derivative of regime indicators |
| H39 (Cycle velocity ratio) | `adverse_leg_speed / favorable_leg_speed` — computed in `compute_dynamic_features`, requires cycle tracking state (favorable and adverse leg timestamps + distances) |
| H40 (Band-relative speed) | `band_state = classify(price vs StdDev_1/2 bands)`, `speed_state = classify(price_speed vs threshold)`, `combined_state = (band_state, speed_state)` → lookup action from state matrix |
| H41 (Band-relative ATR) | `atr_direction = sign(ATR[i] - ATR[i-N])`, `band_state = classify(price vs StdDev_1/2 bands)`, `combined_state = (atr_direction, band_state)` → lookup action from state matrix |

**Cross-bar-type feature computation (`compute_cross_bar_type_features` — Section 2.5):**

| CBT Feature | Computation |
|-------------|-------------|
| CBT-1 (Trade size regime) | `vol_bars_per_minute / tick_bars_per_minute` over trailing aligned window. Requires vol and tick reference data. |
| CBT-2 (Activity concentration) | `count(vol_bars) + count(tick_bars)` completing within each 10-sec reference window. Requires 10-sec as reference. |
| CBT-3 (Path efficiency) | `sum(abs(bar_range))` on time-series / same on vol-series over aligned N-second window. Requires both reference series. |
| CBT-4 (Feature agreement) | `1 - normalized_std(feature_value_across_3_series)` for each feature (ATR, imbalance, momentum). Requires both reference series. |
| CBT-5 (Lead-lag) | `argmax(cross_correlation(feature_primary, feature_reference, offsets))` — rolling cross-correlation at multiple time offsets. |
| CBT-6 (Cycle quality agreement) | `sign(pnl_primary) == sign(pnl_reference)` for completed cycles over aligned wall-clock window. Computed in `compute_dynamic_features`. |

These features are always computed when reference data is present. They are available to any hypothesis or TDS detector — not toggled individually. When reference data is absent (e.g., running 10-sec as primary with no other series loaded), CBT features return NaN and are ignored.

**Execution methods (`_execute_reversal`, `_execute_add`, `_seed`):**

| Hypothesis | What changes |
|------------|-------------|
| H14 (Adaptive martingale) | Add size and max levels modified by market state before execution |
| H15 (Alt anchors) | Anchor update logic branch: cycle_entry / avg_entry / reversal_only |
| H18 (Directional asymmetry) | All parameters looked up by `self.state.direction` |
| H20 (Partial rotation) | `_execute_reversal` scales out instead of full flatten |

**Structural mod checks (`_check_structural_mods`):**

| Hypothesis | What changes |
|------------|-------------|
| H13 (Selective flat) | Flat condition evaluation → force flatten + pause |
| H21 (Profit target) | `if cycle_pnl >= target: flatten or reverse` |
| H22 (Time decay) | `if cycle_duration >= limit: flatten or widen` |
| H24 (De-escalation) | `if at_level_2_plus and conditions_adverse: trim position` |

**Trend Defense System (separate from hypothesis logic):**

| Component | Implementation |
|-----------|---------------|
| TDS detectors | Run in `evaluate_trend_defense()` before state machine transitions |
| TDS responses | Applied in `apply_response()` — modifies state and gates available actions |
| TDS Level 3 cooldown | Managed in main loop — skips state machine when `forced_flat` |

### 6.4 Cycle Definition

**This is the fundamental unit of analysis. All assessment metrics (Section 7) are computed on cycles.**

A **cycle** is the complete sequence from one reversal (or seed) to the next reversal (or flatten). Within a cycle there may be zero or more adds.

**Cycle record fields:**
```
cycle_id | start_bar | end_bar | direction | duration_bars |
entry_price | exit_price | avg_entry_price |
adds_count | max_level_reached | max_position_qty |
gross_pnl_ticks | net_pnl_ticks (after costs) |
max_adverse_excursion_ticks | max_favorable_excursion_ticks |
retracement_depths[] | time_at_max_level_bars |
trend_defense_level_max | exit_reason (reversal | profit_target | time_decay | td_flatten)
```

**Cost model:** Each trade action (seed, reversal entry, add) incurs `cost_ticks` from `instruments.md` (Pipeline Rule 5). Reversal incurs cost twice (flatten + re-enter). Cycle net PnL = gross PnL - (number_of_actions × cost_ticks × position_size_at_action).

### 6.5 Determinism

Same requirements as all pipeline simulators:
- Identical config + identical data → identical results (diff empty)
- No randomness in the simulation loop
- Bar processing is strictly sequential (no lookahead)
- Feature computations use only data available at bar index i (**Pipeline Rule 3: Entry-Time Only**)

---

## 7. Assessment Metrics

**Reminder: All metrics below are computed on CYCLES (Section 6.4), not individual trades. This is because trades within a martingale cycle are not independent — PF and win rate computed on individual trades are misleading for this strategy type (see Gap G-06).**

### 7.1 Universal Metrics (results_master.tsv cols 1-24)

These use the same column definitions as the existing pipeline but are computed on CYCLES:

| Column | Rotational interpretation |
|--------|--------------------------|
| `pf_p1` / `pf_p2` | Cycle-level profit factor |
| `trades_p1` / `trades_p2` | Number of complete cycles |
| `sharpe_p1` | Sharpe ratio of cycle PnL series |
| `max_dd_ticks` | Max peak-to-trough drawdown across equity curve |
| `win_rate` | % of cycles with positive net PnL |
| `avg_winner_ticks` | Average winning cycle PnL |
| `dd_multiple` | Max DD / avg winner |

### 7.2 Extended Metrics (results_master.tsv col 25 — JSON, per Gap G-05)

**11 metric categories. All values below are illustrative examples, not targets.**

```json
{
  "cycle_core": {
    "cycles_total": 142,
    "adds_total": 387,
    "avg_adds_per_cycle": 2.73,
    "max_level_reached": 4,
    "max_level_exposure_pct": 0.08,
    "max_level_exposure_bars": 1247,
    "worst_cycle_dd_ticks": -89.5,
    "worst_cycle_dd_atr": -6.2,
    "avg_cycle_duration_bars": 312,
    "median_cycle_duration_bars": 198,
    "tail_ratio_p95_p5": 3.4,
    "cycle_pf_p1a": 2.1,
    "cycle_pf_p1b": 1.8,
    "refused_adds": 12,
    "retracement_health_avg": 0.62
  },

  "capital_exposure": {
    "peak_margin_contracts": 15,
    "avg_position_weighted_contracts": 3.2,
    "time_at_level": { "0": 0.41, "1": 0.28, "2": 0.18, "3": 0.08, "4": 0.05 },
    "exposure_adjusted_sharpe": 0.85
  },

  "cost_analysis": {
    "total_round_trips": 529,
    "total_cost_ticks": 1058.0,
    "cost_pct_of_gross_profit": 0.23,
    "avg_cost_per_cycle": 7.45,
    "slippage_sensitivity": {
      "base_pf": 2.1,
      "pf_at_plus_0.25_tick": 1.95,
      "pf_at_plus_0.50_tick": 1.78,
      "pf_at_plus_1.00_tick": 1.44
    }
  },

  "profit_concentration": {
    "top_5pct_profit_share": 0.38,
    "top_10pct_profit_share": 0.55,
    "top_20pct_profit_share": 0.72,
    "gini_coefficient": 0.61,
    "breakeven_removal_count": 7
  },

  "heat": {
    "median_intra_cycle_dd_ticks": -18.5,
    "p90_intra_cycle_dd_ticks": -52.0,
    "avg_heat_ratio": 3.8,
    "pct_bars_underwater": 0.62
  },

  "action_efficiency": {
    "reversal_efficiency_pct": 0.68,
    "add_recovery_rate_pct": 0.74,
    "avg_bars_to_recovery_after_add": 87
  },

  "equity_curve": {
    "calmar_ratio": 1.4,
    "sortino_ratio": 1.8,
    "max_dd_duration_bars": 4200,
    "max_consecutive_losing_cycles": 3
  },

  "session_level": {
    "total_sessions": 62,
    "winning_sessions_pct": 0.71,
    "worst_session_pnl_ticks": -67.0,
    "avg_session_pnl_ticks": 12.3
  },

  "dollar_weighted": {
    "dollar_weighted_win_rate": 0.52,
    "asymmetry_ratio": 4.2
  },

  "directional_split": {
    "long_cycles": 71,
    "short_cycles": 71,
    "long_cycle_pf": 2.3,
    "short_cycle_pf": 1.9
  },

  "trend_defense": {
    "l1_triggers": 8,
    "l2_triggers": 3,
    "l3_triggers": 1,
    "l3_recovery_bars_avg": 245,
    "pnl_saved_estimate_ticks": 156.0
  },

  "bar_type": "250vol"
}
```

**Metric category descriptions:**

| Category | What it captures | Why it matters for martingale |
|----------|-----------------|-------------------------------|
| `cycle_core` | Cycle-level PF, duration, level exposure, tail ratio | Primary assessment unit; replaces misleading trade-level metrics |
| `capital_exposure` | Peak/avg contracts, time-at-level, exposure-adjusted returns | Martingale swings from 1 to 15 contracts — raw returns without exposure context are meaningless |
| `cost_analysis` | Round trips, cost drag, slippage sensitivity curve | Martingale trades heavily; if cost drag exceeds 30% of gross profit or PF collapses with +0.5 tick slippage, strategy is fragile |
| `profit_concentration` | Top-N cycle dependency, Gini coefficient, breakeven removal count | If 3 out of 142 cycles account for 60% of profit, one missed cycle destroys the edge |
| `heat` | Unrealized DD distribution, heat ratio, time underwater | A cycle that dips -50 ticks before closing +5 is a "winner" with terrible risk characteristics |
| `action_efficiency` | Reversal efficiency, add recovery rate, recovery time | Directly measures whether the martingale mechanism is working — are adds actually recovering? |
| `equity_curve` | Calmar, Sortino, max DD duration, losing streaks | Asymmetric return distributions (inherent to martingale) make Sharpe insufficient; Sortino and Calmar are more appropriate |
| `session_level` | Daily P/L distribution, worst session, win/loss session ratio | The real-world trading experience — what you see at the end of each day |
| `dollar_weighted` | Dollar-weighted win rate, asymmetry ratio | A 75% count-weighted win rate with a 30% dollar-weighted win rate means average losers dwarf average winners — the high win rate is a martingale illusion |

### 7.3 Verdict Logic (rotational-specific, per Gap G-06)

Verdict gates are organized into primary, survival, robustness, multiple testing, and replication tiers. **All tiers must pass for a PASS verdict.**

**Primary gates:**
- Cycle PF (P1a) ≥ 1.5
- Cycles ≥ 30 per period

**Survival gates:**
- Worst-cycle DD < 2× average ATR × max position size
- Max-level exposure % < 15%
- Max consecutive losing cycles ≤ 5

**Robustness gates:**
- Slippage sensitivity: PF at +0.50 tick slippage ≥ 1.2 (strategy survives realistic execution costs)
- Breakeven removal count ≥ 10% of total cycles (profit not concentrated in a few outliers)
- Asymmetry ratio < 5:1 (average losing cycle < 5× average winning cycle)
- Cost as % of gross profit < 35%

**Multiple testing gate (G-10):**
- `n_prior_tests` tracked per hypothesis — total experiments run before this one
- `pctile` = rank of this result within all prior results for the same archetype
- Bonferroni-adjusted significance: with 122 Phase 1 experiments, a nominally significant result must clear a higher bar. Apply Bonferroni correction to MWU p-values from feature evaluation and permutation tests from cycle PF comparison vs baseline.
- Phase 1b cross-bar-type analysis provides additional protection — a hypothesis must show consistent improvement across bar types, not just pass on one series by chance.
- **Implementation:** `rotational_engine.py` increments `n_prior_tests` for each experiment and writes it to results_master.tsv col 15. Stage 05 uses this for Bonferroni-adjusted thresholds.

**Replication gate (Pipeline Rule 4):**
- Cycle PF (P1b) ≥ 1.3

**PASS:** All four tiers satisfied.

**CONDITIONAL:** Primary gates pass but one or more survival or robustness gates fail, OR cycles < 30 (insufficient sample).

**WEAK_REPLICATION:** Primary + survival + robustness pass but P1b cycle PF < 1.3.

**FAIL:** Primary gates not met OR worst-cycle DD exceeds hard limit OR asymmetry ratio > 10:1.

*Thresholds are initial estimates. Calibrate after baseline runs.*

---

## 8. Files to Create

### 8.1 New Files (rotational archetype)

| File | Location | Purpose |
|------|----------|---------|
| `simulation_rules.md` | `shared/archetypes/rotational/` | State machine definition, cycle semantics |
| `rotational_engine.py` | `shared/archetypes/rotational/` | Separate engine for continuous simulation flow (Gap G-02) |
| `rotational_simulator.py` | `shared/archetypes/rotational/` | Continuous state machine simulator |
| `rotational_feature_engine.py` | `shared/archetypes/rotational/` | Feature computation (agent-editable in Stage 02) |
| `rotational_feature_evaluator.py` | `shared/archetypes/rotational/` | Bar-level feature evaluation harness (Gap G-04) |
| `rotational_hypothesis_config.json` | `shared/archetypes/rotational/` | Default config (agent-editable in Stage 03) |
| `rotational_hypothesis_generator.py` | `shared/archetypes/rotational/` | Hypothesis harness for Stage 03 |
| `rotational_params.json` | `shared/archetypes/rotational/` | Parameter config (agent-editable in Stage 04) |
| `trend_defense.py` | `shared/archetypes/rotational/` | Trend Defense System module |
| `profiles/max_profit.json` | `shared/archetypes/rotational/profiles/` | MAX_PROFIT profile: optimized params + baseline metrics |
| `profiles/safest.json` | `shared/archetypes/rotational/profiles/` | SAFEST profile: optimized params + baseline metrics |
| `profiles/most_consistent.json` | `shared/archetypes/rotational/profiles/` | MOST_CONSISTENT profile: optimized params + baseline metrics |
| `profiles/profile_definitions.json` | `shared/archetypes/rotational/profiles/` | Profile selection criteria config (new profiles addable without code changes) |
| `run_sizing_sweep.py` | `shared/archetypes/rotational/` | 966-run joint parameter sweep harness |
| `run_tds_calibration.py` | `shared/archetypes/rotational/` | 99-run TDS calibration harness (permanent pipeline step) |
| `run_anchor_mode_comparison.py` | `shared/archetypes/rotational/` | 3-mode anchor comparison harness |
| `test_rotational_simulator.py` | `shared/archetypes/rotational/` | 57 simulator tests incl 7 anchor mode tests |
| `test_trend_defense.py` | `shared/archetypes/rotational/` | 22 TDS unit tests + 8 integration tests |
| `test_tds_calibration.py` | `shared/archetypes/rotational/` | 58 calibration harness tests |
| `tds_profiles/best_tds_configs.json` | `shared/archetypes/rotational/` | Calibrated TDS configs per profile (velocity L1 for 10sec, disabled for vol/tick) |
| `hmm_regime_rot_v1.pkl` | `shared/scoring_models/` | Regime model fitted on rotational data (Gap G-07 — not yet built) |
| `bar_data_rot_schema.md` | `_config/` | 35-col schema (already created per handoff) |
| `ATEAM_ROTATION_V2_V2882_wmaxcap.cpp` | Sierra Chart study | C++ V2 with MaxTotalPosition input. Only functional change from V1. |

### 8.2 Results & Output Files (generated by completed phases)

| File | Location | Contents |
|------|----------|----------|
| `sizing_sweep_P1a.tsv` | `shared/archetypes/rotational/sizing_sweep_results/` | 966 rows, all sweep configs |
| `sizing_sweep_report.md` | `shared/archetypes/rotational/sizing_sweep_results/` | Full analysis + FORMAL FINDING |
| `phase1_results.tsv` | `shared/archetypes/rotational/screening_results/` | 123 rows, default-params screening |
| `phase1b_classification.json` | `shared/archetypes/rotational/screening_results/` | Cross-bar-type classification |
| `tds_calibration_report.md` | `shared/archetypes/rotational/tds_profiles/` | 99-run TDS analysis |
| `exp[1-3]_*.tsv` | `shared/archetypes/rotational/tds_profiles/` | Per-experiment TDS results |
| `anchor_mode_comparison_P1a.tsv` | `shared/archetypes/rotational/anchor_comparison/` | 15-run mode comparison |
| `anchor_mode_comparison_report.md` | `shared/archetypes/rotational/anchor_comparison/` | Mode A wins analysis |

### 8.3 Modified Files (pipeline infrastructure)

| File | Change | Gap |
|------|--------|-----|
| `data_manifest.json` | Add `data_sources` structure for rotational | G-01 ✅ |
| `evaluate_features.py` | Add dynamic dispatch for feature evaluator module | G-09 ✅ |
| `results_master.tsv` | Add col 25: `extended_metrics` (JSON) | G-05 ✅ |
| `statistical_gates.md` | Add `[archetype: rotational]` section | G-06 ✅ |
| `strategy_archetypes.md` | Update rotational entry with full config | G-08 ✅ |
| `data_registry.md` | Add `bar_data_10sec_rot` source | ✅ |
| `period_config.md` | Verify rotational rows present | ✅ |

### 8.4 Existing Files Confirmed Unchanged

- `backtest_engine.py` — rotational uses separate `rotational_engine.py` (G-02). CLAUDE.md prohibition honored.
- `scoring_adapter.py` — rotational doesn't use it (G-03)
- Zone_touch simulator, feature engine, evaluator — all untouched
- `pipeline_rules.md` — five rules apply as-is to rotational
- `regime_definitions.md` — same dimensions, different model fit

---

## 9. Implementation Sequence

### Phase A — Infrastructure ✅ COMPLETE

All 10 gaps resolved (8 complete, G-07 deferred to before H5, G-10 deferred to Phase 05). 6 commits. Spec corrections logged: G-02 became separate engine, G-03 absorbed into G-02, G-09 already existed.

1. **G-01 (HIGH — multi-source data):** G-01 schema work was completed by GSD with `primary: [250vol, 250tick], reference: [10sec]`. **Update needed:** add `bar_data_10sec_rot` to the primary list (promoted to third primary after GSD's initial build). Update `strategy_archetypes.md` and regenerate `data_manifest.json`.
2. **G-02 (HIGH — continuous simulator):** Build `rotational_engine.py` — separate engine for continuous simulation flow. `backtest_engine.py` stays frozen.
3. **G-03 (Resolved by G-02):** No action needed — rotational engine has no scoring step. `backtest_engine.py` untouched.
4. **G-04 (HIGH — feature evaluation) + G-09 (Medium — dispatch):** Add dynamic dispatch to `evaluate_features.py`; extract zone_touch evaluator into own module
5. **G-05 (Medium — extended metrics):** Add `extended_metrics` col 25 to `results_master.tsv`
6. **G-06 (Medium — assessment thresholds):** Add rotational 4-tier verdict thresholds to `statistical_gates.md`
7. **Data registration (use onboarding tools in `shared/onboarding/`):**
   - Run `register_source.py` to register `bar_data_10sec_rot` in `data_registry.md` (data available in pipeline)
   - Run `register_archetype.py` to update rotational entry in `strategy_archetypes.md` and `period_config.md` with full config from Section 5, G-08
8. **Verify PM-01 complete**, then run Stage 01 to populate `data_manifest.json` for rotational with per-archetype period boundaries. **Human checkpoint:** review `stages/01-data/output/validation_report.md` before proceeding to Phase B. Confirm all three bar types resolve correctly, period boundaries match `period_config.md`, and `data_manifest.json` was not hand-edited.

### Phase B — Simulator Build & Baseline Establishment ✅ COMPLETE

Simulator built (57 tests passing), determinism verified, RTH filter implemented. Joint parameter sweep: 966 P1a runs (322 unique combos × 3 bar types after deduplication). 3 profiles identified and stored in `shared/archetypes/rotational/profiles/`. Key findings: martingale is net negative (see Empirical Findings above), MAX_PROFIT and MOST_CONSISTENT converge on 250vol and 10sec.

**Anchor mode comparison (15 runs):** Frozen anchor (Mode A) wins decisively — PF 1.7-2.2 vs sub-0.9 for walking anchor and hard stop modes. Documented in `simulation_rules.md`.

**TDS calibration (99 runs):** L3 drawdown budget incompatible with rotational edge — fires on normal cycles. TDS disabled for vol/tick, velocity-only L1 for 10sec. Calibrated configs stored in `tds_profiles/best_tds_configs.json`.

### Phase C — Research Execution ← CURRENT PHASE (Phase 04 in GSD)

**DATA DISCIPLINE: All research in Phase C runs exclusively on P1a data. P1b data is never touched during calibration and search — it is reserved for the replication check at Step 9. Running combinations on full P1 instead of P1a-only would contaminate the replication holdout.**

**REPLICATION GATE: The P1b result at Step 9 is a soft gate (`flag_and_review`), not a hard block. P1b failure → `WEAK_REPLICATION` verdict surfaces for human review. The human decides whether to promote to P2.**

**3-PROFILE PARALLEL TRACKS: All steps below run independently for each of the 3 profiles (MAX_PROFIT, SAFEST, MOST_CONSISTENT) from Phase B. Each profile has its own optimized baseline parameters (StepDist, MaxLevels, MaxTotalPosition). Hypothesis results, TDS calibration, and combinations are profile-specific — what works for MAX_PROFIT may not work for SAFEST.**

**HYPOTHESIS PRIORITY (based on Empirical Findings):**
- **TOP PRIORITY:** H11 (time-of-day), H13 (selective flat), H33 (PriceSpeed), Dimension A triggers (H1, H3, H8, H9, H10), H2 (asymmetric thresholds)
- **DEPRIORITIZED** (test for completeness, not expected to help): H14 (adaptive martingale), H23 (conditional adds), H24 (de-escalation), H39 (cycle adverse velocity ratio) — these manage a mechanism the data shows is harmful
- **DEFERRED:** H19 (bar-type divergence) — requires multi-source reference, deferred to combination testing

1. ~~Build `rotational_feature_evaluator.py` for Stage 02~~ ✅ Complete (Phase 02)
2. **Phase 1 research:** 41 hypotheses × 3 bar types × 3 profiles = ~366 meaningful experiments (H37 excluded from 10-sec), independent screening against each profile's optimized baseline. **Initial screening at default params (123 runs) complete — 0/119 beat baseline as expected. Parameter-tuned screening is the real test.**
3. **Phase 1b analysis:** Cross-bar-type robustness classification (Section 3.7) — run per profile. Classify each hypothesis per profile. A hypothesis may be Robust for MAX_PROFIT but No Signal for SAFEST.
4. ~~Build `trend_defense.py`~~ ✅ Complete (Phase 03) — 5 detectors, 3-level escalation, 22 unit tests
5. ~~Test TDS levels 1, 2, 3 independently against each profile's baseline~~ ✅ Complete (Phase 03.1) — **TDS disposition: disabled for vol/tick, velocity-only L1 for 10sec. L3 incompatible with rotational edge.**
6. **Phase 2 research:** Combine winners (from Phase 1b, per profile) across dimensions. Run on all 3 bar types per profile. Repeat cross-bar-type analysis.
7. **Phase 3 research:** Best combination + best TDS configuration per profile, all 3 bar types
8. **Profile convergence analysis:** Compare the 3 profiles' hypothesis winners. If profiles converge on the same winners, that's strong evidence. If they diverge, the divergence reveals what each hypothesis actually does (alpha vs risk management vs consistency).
9. P1b replication gate on final candidates per profile (**Pipeline Rule 4: Internal Replication**)
10. Human review → promote to P2

### Phase D — Assessment & Deployment

1. **P2 one-shot run** with frozen parameters per profile, all 3 bar types (**Pipeline Rule 2: P2 One-Shot — NEVER re-run**). 3 profiles × 3 bar types = 9 verdict runs.
2. Stage 05 verdict using rotational 5-tier logic per profile (Gap G-06). **PF > 1.0 hard gate enforced here** — after all hypotheses, TDS, and filters have been applied. Cross-bar-type consistency is a factor in verdict confidence.
3. **Final output:** Up to 3 deployable configurations (one per profile that passes verdict). User chooses the profile matching their risk appetite.
4. If PASS/CONDITIONAL → Stage 06 deployment preparation

---

## 10. Open Questions

| ID | Question | Context | Status |
|----|----------|---------|--------|
| RQ-01 | ~~What are the three channel sets in the export (cols 23-34)?~~ | **RESOLVED.** StdDev_1 (1.5×, 500-bar, WMA — tactical), StdDev_2 (4.0×, 500-bar, WMA — extreme), StdDev_3 (4.0×, 5000-bar, EMA — structural). All computed on col 22 (Sum). Values are deviations from center. Full schema in `stages/01-data/references/bar_data_rot_schema.md`. | ✅ Resolved |
| RQ-02 | VWAP on 250-vol bars: equal-volume bars flatten VWAP. 10-sec time bars solve this, but confirm we compute VWAP in Python (preferred) vs exporting from Sierra Chart. | Impacts H9 (VWAP SD bands, Dimension A) — Python computation keeps pipeline self-contained | Before H9 testing in Phase 04 |
| RQ-03 | Regime model: refit HMM on rotational bar data, or use zone_touch regime labels mapped by timestamp? Former is cleaner. | Impacts H5 (regime-conditional, Dimension C) — see Gap G-07 (still open) | Before H5 testing in Phase 04 |
| RQ-04 | ~~What is the computational budget for a single simulation run?~~ | **RESOLVED.** Actual runtimes: sizing sweep ~1.9s/run, TDS calibration ~12s/run, anchor comparison ~10s/run. Total ~1,250 P1a runs completed. | ✅ Resolved |
| RQ-05 | ~~Baseline C++ StepDist=2.0 — is this the value you've been running live?~~ | **RESOLVED.** Nothing has been run. Joint parameter sweep (StepDist × ML × MTP) replaced single-parameter sweep. Best fixed configs found per profile per bar type. | ✅ Resolved |
| RQ-06 | ~~The C++ always seeds long. For Python simulator, seed long as well?~~ | **RESOLVED.** Always seed Long. `rotational_simulator.py` line 476: `self._direction = "Long"`. Matches C++ behavior. Fixed design choice, not parameterized. | ✅ Resolved |
| RQ-07 | ~~MaxContractSize=8 — hard cap or parameter?~~ | **RESOLVED.** MCS raised to 16 (irrelevant at ML=1). MaxTotalPosition is the real position control — new pipeline addition not in C++. ML=1 wins for MAX_PROFIT, MCS rarely reached. C++ V2 study created with MTP input. | ✅ Resolved |
| RQ-08 | ~~Extended metrics — JSON blob in col 25 vs separate file?~~ | **RESOLVED.** Separate JSON files per profile in `shared/archetypes/rotational/profiles/`. Not JSON blobs in TSV — full standalone files. `max_profit.json`, `safest.json`, `most_consistent.json` + `profile_definitions.json`. | ✅ Resolved |
| RQ-09 | ~~PM-01 (per-archetype period boundaries) — confirm complete.~~ | **RESOLVED.** PM-01 is complete. | ✅ Resolved |
| RQ-10 | Dashboard spec needs update for rotational-specific views. | Impacts Milestone 2 dashboard. Not blocking. | After Phase 04 |

---

## Appendix A — Hypothesis Quick Reference

**41 hypotheses across 6 dimensions. Each tested independently in Phase 1 (~366 experiments: 41 × 3 bar types × 3 profiles, minus H37 on 10-sec), cross-analyzed in Phase 1b for robustness per profile, then combined in Phase 2.**

**Priority ranking (based on Empirical Findings):**
- **TOP:** H1, H2, H3, H8, H9, H10 (Dim A triggers), H11 (time-of-day), H13 (selective flat), H33 (PriceSpeed)
- **DEPRIORITIZED:** H14, H23, H24, H39 (martingale management — mechanism is net negative)
- **DEFERRED:** H19 (requires multi-source reference)

| ID | Dim | Name | Type | Key data |
|----|-----|------|------|----------|
| H1 | A | ATR-scaled step | Trigger | Col 35 (ATR) |
| H2 | B | Asymmetric thresholds | Modifier | Parameter split |
| H3 | A | SD band triggers | Trigger | Cols 23-34 (3 SD band sets) |
| H4 | C | ZZ swing confirmation | Filter | Cols 14-18 |
| H5 | C | Regime-conditional params | Filter | HMM model (refit, G-07) |
| H6 | C | Bid/Ask volume imbalance | Filter | Cols 12-13 |
| H7 | C | ZZ Oscillator gating | Filter | Col 21 |
| H8 | A | SD-scaled step | Trigger | Computed |
| H9 | A | VWAP SD bands | Trigger | Computed (10-sec preferred) |
| H10 | A | Price z-score threshold | Trigger | Computed |
| H11 | C | Time-of-day conditioning | Filter | Cols 1-2 |
| H12 | C | Day-of-week conditioning | Filter | Col 1 |
| H13 | D | Selective flat periods | Structural | Breaks always-in |
| H14 | D | Adaptive martingale | Structural | Changes sizing |
| H15 | D | Alternative anchors | Structural | Changes distance measurement |
| H16 | C | Bar formation quality | Filter | Col 8, timestamps |
| H17 | C | Cycle performance feedback | Filter | Simulator internal |
| H18 | E | Directional asymmetry | Cross/Dir | Breaks symmetric |
| H19 | E | Bar-type divergence | Cross/Dir | Multi-source (G-01) |
| H20 | D | Partial rotation | Structural | Breaks total flatten |
| H21 | D | Cycle profit target | Structural | Adds new exit |
| H22 | D | Cycle time decay | Structural | Adds time exit |
| H23 | D | Conditional adds | Structural | Refused adds concept |
| H24 | D | Intra-cycle de-escalation | Structural | Position trimming |
| H25 | D | Higher-timeframe context | Structural | Breaks single-TF |
| H26 | D | Session range position | Structural | Location awareness |
| H27 | F | Volatility ROC | Dynamics | Col 35 derivative |
| H28 | F | Price momentum / ROC | Dynamics | Computed |
| H29 | F | Acceleration / deceleration | Dynamics | 2nd derivative |
| H30 | F | Vol compression breakout | Dynamics | Squeeze detection |
| H31 | F | Momentum divergence | Dynamics | Price vs ROC divergence |
| H32 | F | Volume ROC | Dynamics | Col 7 derivative |
| H33 | C | PriceSpeed filter | Filter | Close, timestamps (pts/sec) |
| H34 | C | Absorption rate proxy | Filter | Cols 12-13, timestamps |
| H35 | C | Imbalance trend | Filter | Cols 12-13 (rolling slope) |
| H36 | C | Adverse move speed | Filter | Close, timestamps, simulator state |
| H37 | C | Bar formation rate | Filter | Timestamps (vol/tick only) |
| H38 | F | Regime transition speed | Dynamics | Composite derivative (H27+H29+H35) |
| H39 | C | Cycle adverse velocity ratio | Filter | Simulator internal (cycle tracking) |
| H40 | C | Band-relative speed regime | Filter | Cols 23-30, H33 (composite) |
| H41 | C | Band-relative ATR behavior | Filter | Col 35, Cols 23-30 (composite) |

## Appendix B — Pipeline Gap Summary

**10 gaps. 8 implemented, 2 deferred (G-07 HMM refit, G-10 Bonferroni). All resolutions were additive — no breaking changes to existing pipeline.**

| Gap | Severity | Component | Summary | Status |
|-----|----------|-----------|---------|--------|
| G-01 | **HIGH** | data_manifest / Stage 01 | Multi-source data loading | ✅ |
| G-02 | **HIGH** | Stage 04 / engine | Separate engine for continuous simulation | ✅ |
| G-03 | Resolved | Stage 04 / scoring | Scoring adapter not applicable | ✅ |
| G-04 | **HIGH** | Stage 02 / evaluation | Feature eval needs bar-level outcomes | ✅ |
| G-05 | Medium | results_master.tsv | Cycle-level extended metrics | ✅ |
| G-06 | Medium | Stage 05 / assessment | Rotational-specific verdict thresholds | ✅ |
| G-07 | Low | Stage 01 / regime | HMM refit on rotational data | ⏳ Before H5 |
| G-08 | Medium | Autoresearch config | Rotational autoresearch mapping | ✅ |
| G-09 | Medium | Stage 02 / dispatch | Feature evaluator dynamic dispatch | ✅ |
| G-10 | Medium | Stage 05 / assessment | Bonferroni (~366 experiments, per-profile) | ⏳ Phase 05 |

## Appendix C — Trend Defense Quick Reference

**Three-level escalation system for surviving straight-line moves. ⚠️ CALIBRATION RESULT: TDS disabled for vol/tick bars, velocity-only L1 for 10sec bars. L2 and L3 are incompatible with rotational edge at MTP≤2. See Empirical Finding 3.**

| Level | Trigger | Response | Strategy state |
|-------|---------|----------|---------------|
| 1 (Early Warning) | Retracement quality declining, trend precursors | Widen steps, suppress next add level | In market, conservative |
| 2 (Active Threat) | Rapid level escalation, consecutive adds without retracement | Refuse all adds, begin de-escalation | In market, reducing |
| 3 (Emergency) | Drawdown budget hit, max-level + adverse momentum | Force flatten, cooldown period | Flat, waiting |

**Max-level special handling:** When at max martingale level and offside, switch to reduced exit threshold (breakeven on avg entry or 50% of normal StepDist) to escape faster.

**Survival metrics:** Worst-cycle DD, max-level exposure %, consecutive adds without retracement, drawdown budget hit count, tail ratio (P95/P5).

**Full assessment (Section 7) also includes:** Slippage sensitivity curve, breakeven removal count, asymmetry ratio, heat ratio, add recovery rate, Calmar/Sortino ratios, max DD duration, worst session PnL, dollar-weighted win rate. Verdict logic uses robustness gates on slippage sensitivity (PF must survive +0.5 tick), profit concentration (breakeven removal ≥ 10% of cycles), and asymmetry ratio (< 5:1).

## Appendix D — Five Pipeline Rules (repeated for end-of-document reference)

**These are absolute and apply to all work on the rotational archetype:**

1. **P1 Calibrate** — IS data (P1) used freely for calibration and search
2. **P2 One-Shot** — OOS (P2) runs exactly once with frozen params; NEVER re-run
3. **Entry-Time Only** — all features at bar index i use only data from bars 0..i; no lookahead
4. **Internal Replication** — must pass P1b before P2 unlocked; `flag_and_review` gate
5. **Instrument Constants from Registry** — tick size, cost_ticks, session times from `_config/instruments.md` only
