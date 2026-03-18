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

## Bar Resolution: Threshold-Crossing OHLC

**Decision: threshold-crossing logic (2026-03-16)** — the simulator uses exact trigger
levels (anchor +/- step_dist) checked against each bar's High and Low to detect intra-bar
threshold crossings. Multiple actions can fire within a single bar.

The close-only approach (evaluating only bar Close) was found to be fundamentally
incompatible with the rotational strategy at higher MTP values. 42% of 250-vol P1a bars
have H-L range >= 7.0 points. Close-only missed all intra-bar rotations, producing
MTP=0 PF=0.58 when live C++ showed profitable trading (PF~1.7). The threshold-crossing
fix resolved this: MTP=0 PF=1.74, position self-limits through intra-bar reversals.

When both add and reversal triggers are crossed within the same bar, Open proximity
determines which fires first. This is the only approximation — all other trigger
detections are exact.

## Anchor Behavior on MTP Refusal

**Decision: walking anchor (Mode B)** — when MaxTotalPosition refuses an ADD, anchor
updates to the current trigger price. This keeps the reversal trigger reachable, preventing
the "stuck" problem where frozen anchor leaves positions trapped indefinitely.

**Tested 2026-03-16** via anchor mode comparison on 250tick SD=5.5/ML=1/MTP=4 P1a
using threshold-crossing simulator:

| Mode | PF | Net PnL | Cycles | WorstDD | Stuck |
|------|----|---------|--------|---------|-------|
| A (frozen) | 10.48 | 173,646 | 13,408 | -16,758 | 26 |
| **B (walking)** | **5.75** | **1,096,775** | **92,984** | **-8,274** | **0** |
| C-20pt (frozen+stop) | 3.38 | 852,369 | 84,674 | -6,558 | 1 |
| C-30pt (frozen+stop) | 3.67 | 806,453 | 77,603 | -6,558 | 11 |
| C-40pt (frozen+stop) | 3.67 | 745,729 | 71,701 | -6,558 | 20 |

**Why walking wins:** Mode A's high PF (10.48) is misleading — it achieves selectivity by
leaving capital stuck at MTP cap (26 stuck cycles, position frozen for 100+ bars). Mode B
eliminates stuck cycles entirely (0) and generates 6.3x more total PnL. With threshold-
crossing capturing intra-bar reversals, the cycle explosion from walking anchor no longer
destroys profitability — each additional cycle carries positive expectation.

**Historical note:** The previous comparison (close-only simulator) showed frozen anchor
winning because walking anchor caused 12x cycle explosion with rapid cycling that could
not overcome transaction costs. The threshold-crossing fix resolved this by allowing
intra-bar reversals, making walking anchor viable.

**The `anchor_mode` config parameter exists in `rotational_simulator.py` for testing
purposes but the production default is `"walking"`.** Any changes require re-running
this comparison with the threshold-crossing simulator.

## Trend Defense System (TDS) Applicability

**Decision (2026-03-17):** TDS applicability depends on MTP. Walking anchor + threshold-
crossing fundamentally changed position dynamics:

| Profile | MTP | TDS Status | Rationale |
|---------|-----|------------|-----------|
| MOST_CONSISTENT | 1 | **Disabled** | No adds fire. Position always 1 contract. Walking anchor keeps reversal reachable. Nothing to defend. |
| SAFEST | 1 | **Disabled** | Same as above — pure reversal, no position growth. |
| MAX_PROFIT | 8 | **Re-calibrate** | Position can grow to 8 contracts. TDS L1/L2 (step widening, add refusal) may still reduce drawdown during sustained adverse moves. |

TDS was originally designed for Mode A (frozen anchor) where positions got trapped at
MTP cap indefinitely. Mode B eliminates stuck cycles, but MAX_PROFIT (MTP=8) still
accumulates position during multi-step adverse moves. TDS L1/L2 may help there.

**TDS L3 (force flatten) remains incompatible** with the rotational strategy regardless
of anchor mode — it forces exits mid-drawdown then re-SEEDs, doubling cost burden.
