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

- **Primary** (250-vol, 250-tick): strategy runs independently on each
- **Reference** (10-sec): loaded as supplementary lookup via as-of timestamp index
- Engine runs simulation per primary source, results compared

## Scoring

No scoring adapter. Decision logic lives inside the simulator.
`config.archetype.scoring_adapter = null` — engine skips scoring entirely.
