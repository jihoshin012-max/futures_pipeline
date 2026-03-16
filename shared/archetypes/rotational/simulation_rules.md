# archetype: rotational
# Simulation Rules — rotational archetype
last_reviewed: 2026-03-14

## Engine

`rotational_engine.py` — separate from `backtest_engine.py` (zone_touch).
Continuous state machine harness: loads bars, dispatches to RotationalSimulator, collects cycle-level results.

## State Machine

```
States:  FLAT → POSITIONED (Long/Short, Level 0..N)
Actions: SEED, REVERSAL, ADD

SEED:     Position flat, no anchor → Buy InitialQty, Direction=Long, Level=0
REVERSAL: Price ≥ StepDist IN FAVOR from Anchor → Flatten all, enter opposite at InitialQty, Level=0
ADD:      Price ≥ StepDist AGAINST from Anchor → Add (InitialQty × 2^Level), Level++
          Cap: add qty > MaxContractSize → reset to InitialQty, Level=0
```

## Unit of Analysis: CYCLE

A **cycle** = seed/reversal through all adds to the next reversal.
Trades within a cycle are NOT independent. All metrics computed on cycles.

Cycle record: cycle_id, start_bar, end_bar, direction, duration_bars,
entry_price, exit_price, avg_entry_price, adds_count, max_level_reached,
max_position_qty, gross_pnl_ticks, net_pnl_ticks, max_adverse_excursion_ticks,
max_favorable_excursion_ticks, retracement_depths[], time_at_max_level_bars,
trend_defense_level_max, exit_reason

## SimulationResult Contract

```python
@dataclass
class SimulationResult:
    trades: pd.DataFrame    # Individual actions (seed, reversal, add)
    cycles: pd.DataFrame    # Reversal-to-reversal summaries — PRIMARY assessment unit
    bars_processed: int
```

## Cost Model

Each trade action (seed, reversal entry, add) incurs cost_ticks from instruments.md.
Reversal incurs cost twice (flatten + re-enter).
Cycle net_pnl = gross_pnl - (number_of_actions × cost_ticks × position_size_at_action).

## Determinism

- Identical config + identical data → identical results (diff empty)
- No randomness in simulation loop
- Bar processing strictly sequential (no lookahead)
- Features at bar i use only data from bars 0..i (Pipeline Rule 3: Entry-Time Only)

## Data Sources

- **Primary** (250-vol, 250-tick, 10-sec): strategy runs independently on all three
- No reference sources — all three bar types are independent execution series
- 10-sec bars filtered to RTH session only (09:30-16:00 ET) before simulation
- Engine runs simulation per primary source, results compared in Phase 1b cross-bar-type analysis

## Scoring

No scoring adapter. Decision logic lives inside the simulator.
`config.archetype.scoring_adapter = null` — engine skips scoring entirely.

## Anchor Behavior on MTP Refusal

**Decision: frozen anchor (Mode A)** — when MaxTotalPosition refuses an ADD, anchor
stays at the last successful trade price. No state mutation occurs.

**Tested 2026-03-16** via `run_anchor_mode_comparison.py` against MAX_PROFIT winning
configs (250vol SD=7.0/MTP=2, 250tick SD=4.5/MTP=1, 10sec SD=10.0/MTP=4) on P1a:

| Mode | Behavior | Result |
|------|----------|--------|
| A (frozen) | Anchor stays at last trade price | **PF 1.72–2.20, positive PnL** |
| B (walking) | Anchor updates to current price | PF 0.71–0.86, massive negative PnL |
| C (frozen_stop) | Frozen anchor + hard stop exit | PF 0.70–0.83, massive negative PnL |

**Why frozen wins:** The rotational strategy profits from patience — holding through
adverse excursions until reversal. Walking the anchor (B) shortens effective cycle
distance, exploding cycle count (360 → 11,858 for 250tick) and creating rapid-cycling
that cannot overcome transaction costs. Hard stops (C) force-exit mid-drawdown then
re-SEED, doubling cost burden on every exit.

**Implication for TDS:** L3 drawdown-budget force-flatten suffers the same failure mode
as Mode C — it is fundamentally incompatible with the rotational strategy's edge at
current MTP levels. TDS L1/L2 (step widening, add refusal) remain viable because they
slow position growth without forcing exits.

**Any future MTP-related changes must respect this decision.** The `anchor_mode` config
parameter exists in `rotational_simulator.py` for testing purposes but the production
default is `"frozen"` and must not be changed without re-running this comparison.
