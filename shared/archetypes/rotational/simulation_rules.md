# archetype: rotational
# Simulation Rules — rotational archetype
last_reviewed: 2026-03-17

## Engine

`rotational_engine.py` — separate from `backtest_engine.py` (zone_touch).
Continuous state machine harness: loads bars, dispatches to RotationalSimulator, collects cycle-level results.

## State Machine

```
States:  WATCHING → POSITIONED (Long/Short, Level 0..N)
Actions: SEED, REVERSAL, ADD, FLATTEN

SEED:     First StepDist move detected → enter in direction of move (directional seed)
REVERSAL: Price ≥ StepDist IN FAVOR from Anchor → Flatten all, enter opposite at InitialQty, Level=0
ADD:      Price ≥ StepDist AGAINST from Anchor → Add (InitialQty × 2^Level), Level++
          Cap: add qty > MaxContractSize or Level >= MaxLevels → reset to InitialQty, Level=0
FLATTEN:  Exit all contracts (part of REVERSAL or standalone via flatten-reseed/hard-stop)
```

## Ground Truth: Tick-Level Simulation

**Decision (2026-03-17):** Tick-level simulation (`_run_tick_fast`) is the only
trustworthy source for absolute PF and parameter selection.

- **Close-only** (original): invalid — missed 42% of intra-bar rotations
- **OHLC threshold-crossing** (intermediate): over-estimates PF by 4-6x — executes at
  exact trigger prices with no slippage
- **Tick-level** (current): validated against C++ regular-speed replay within 5%

The tick-mode fast path processes one price per row, fires at most one action per tick,
and executes at the actual tick price (gap slippage is captured naturally).

Calibration logs: `calibration/cpp_replay_*_regspeed.csv` (V1.1 and V2_js validated).
Accelerated replay logs are invalid (tick skipping confirmed) — archived.

## Directional Seed

The simulator uses directional seeding (matching C++ V2_js behavior):
- When FLAT/WATCHING, records a watch_price at current tick
- Waits for price to move StepDist from watch_price
- If price moves UP by StepDist → seeds Long
- If price moves DOWN by StepDist → seeds Short

This replaces the original always-Long seed behavior.

## ATR-Normalized Asymmetric Distances

**Decision (2026-03-17):** The top P1b candidate uses ATR-normalized distances with
separate reversal and add multiples:

```
reversal_distance = atr_rev_mult × current_ATR
add_distance = atr_add_mult × current_ATR
```

ATR computed from 250tick bar data (20-bar period). Each tick inherits the last
completed 250tick bar's ATR via timestamp lookup.

**Winner: R=2.0x, A=4.0x** (reversal at 2× ATR, add at 4× ATR).
In P1a: avg reversal = 14.7 pts, avg add = 29.1 pts.

Fixed distances (e.g., Rev=15/Add=40) were shown to fail on P1b due to ATR regime
shift (+27%). ATR-normalization is designed to maintain constant ratios across regimes.

**Fragility note:** ATR(20) is a sharp optimum. ATR(14) and ATR(30) both degrade
significantly. R=2.0x/A=4.0x is also a sharp peak — nearest neighbors are clearly
inferior. This is a P1b risk factor.

## Flatten-Reseed Cap

Config: `martingale.flatten_reseed_cap`. When position reaches the cap and another add
would trigger, flattens all contracts and re-enters WATCHING state (directional seed).
Different from MTP refusal: no anchor walk, no position hold — full exit and restart.

## Unit of Analysis: CYCLE

A **cycle** = seed/reversal through all adds to the next reversal (or flatten-reseed/end-of-data).
Trades within a cycle are NOT independent. All metrics computed on cycles.

## Cost Model

Each trade action (seed, reversal entry, add, flatten) incurs `cost_ticks × qty`.
- Reversal = FLATTEN (cost × pos_qty) + REVERSAL_ENTRY (cost × 1) = variable cost
- MTP=1 pure reversal: 2 ticks per cycle (flatten 1 + enter 1) at cost_ticks=1
- **User actual cost: 1 tick ($5/RT).** instruments.md shows 3 ticks ($15/RT) as
  conservative default. Slippage is already captured in tick-level execution prices.

## Determinism

- Identical config + identical data → identical results
- No randomness in simulation loop
- Bar/tick processing strictly sequential (no lookahead)
- Features at bar i use only data from bars 0..i (Pipeline Rule 3: Entry-Time Only)

## Data Sources

- **Ground truth:** 1-tick data (`bar_data_1tick_rot`), 31.9M rows P1a
- **ATR source:** 250-tick bars (`bar_data_250tick_rot`), mapped to ticks
- **OHLC bar types** (250-vol, 250-tick, 10-sec): available for OHLC threshold-crossing
  mode but NOT used for parameter selection
- 10-sec bars filtered to RTH session only (09:30-16:00 ET)

## Time-of-Day Filter

**Decision (2026-03-17):** Exclude hours 1, 19, 20 (ET) from all tick-data runs.
These low-liquidity ETH hours consistently drag PF below baseline across all configs
at 96-99% cycle retention. Implemented as post-hoc filter on cycle entry hour.

## Anchor Behavior on MTP Refusal

**Decision: walking anchor (Mode B)** — production default. When MaxTotalPosition
refuses an ADD, anchor updates to the current price. Keeps reversal trigger reachable.

**Frozen anchor (Mode A) rejected for live trading:** Shows inflated PF from
survivorship bias. High PF comes from extreme selectivity (holding dead positions),
with catastrophic tail risk on the rare losing cycle (-9,814 to -10,484 ticks).
Capital idle most of the time.

## Trend Defense System (TDS) — Disabled for Tick-Data Candidates

**Decision (2026-03-17):** TDS is disabled for all tick-data V1.1 candidates:

- **L1 (velocity step-widening):** Redundant — ATR-normalization already adapts
  distances to volatility. When ATR rises, reversal and add distances widen
  automatically.

- **L2 (refuse adds):** Irrelevant at MTP=0 — no adds are ever refused because
  there is no position cap to trigger refusal.

- **L3 (force flatten / drawdown budget):** Harmful — Test D (2026-03-17) proved
  all ATR-normalized hard stop thresholds (2.0x, 3.0x, 4.0x, 5.0x ATR) hurt PF
  on tick data. The strategy recovers from drawdowns better than any stop predicts.

TDS remains in the codebase for potential V2 MTP>1 deployment. If V2 MTP=2 walking
is ever deployed, TDS must be re-calibrated on tick data (not OHLC). Previous TDS
calibration (OHLC era, MAX_PROFIT SD=6.0/ML=1/MTP=8) is archived.

## Scoring

No scoring adapter. Decision logic lives inside the simulator.
`config.archetype.scoring_adapter = null` — engine skips scoring entirely.
