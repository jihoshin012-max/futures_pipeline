# archetype: rotational
# Simulation Rules — rotational archetype
last_reviewed: 2026-03-14

## Status: Stub

This is a bar-only archetype. No external touch events (zone_csv_v2 or similar) are required.
Signal logic lives entirely in archetype code, operating on bar data.

## Bar-Only Architecture

Unlike zone_touch, the rotational archetype does not rely on a pre-computed touch/signal file.
Entry signals are generated programmatically from bar features during Stage 03 hypothesis
development. This means:
- No BarIndex-to-touch-row pairing step
- No entry_time_violation safety net (bar_df truncation must be enforced explicitly in feature engine)
- The feature engine receives bar_df only (no touch_row parameter)

## Entry/Exit Mechanics

TBD — will be defined during Stage 03 hypothesis development.

Placeholder constraints:
- Entry: long or short signal from bar-based indicator logic (specific signal TBD)
- Exit: target/stop/time-cap pattern (parameters TBD)
- Direction: momentum-following (likely long-biased or dual-direction, TBD)

## SimResult Contract

Not yet defined. Will be specified when the simulator module is created in Stage 03.

Reference contract from zone_touch (for pattern):
```python
from dataclasses import dataclass

@dataclass
class SimResult:
    pnl_ticks: float
    win: bool
    exit_reason: str
    bars_held: int
```

## Cost Model

Cost applied per trade as per _config/instruments.md cost_ticks.
Individual trade pnl_ticks in SimResult is RAW (no cost deduction).
Cost applied during metrics aggregation — never hardcode cost_ticks.
