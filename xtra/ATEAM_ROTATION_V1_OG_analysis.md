# ATEAM_ROTATION_V1_OG_V2803 — Study Analysis
generated: 2026-03-14
source: ATEAM_ROTATION_V1_OG_V2803.cpp

## What It Is

A **martingale grid/rotation trading system** for Sierra Chart. It continuously holds a position, reversing direction when price moves in its favor and doubling down (martingale) when price moves against it.

## Core Logic Flow

### 1. Seed Entry
- When flat with no anchor, enters **long** with `InitialQty` (default: 1 contract)
- Sets the entry price as the **anchor price**

### 2. Price Moves In Favor (≥ StepDist)
- **Flattens the entire position** (takes profit)
- Then **reverses** into the opposite direction with `InitialQty`
- Resets martingale level to 0
- Example: Long from 20000, StepDist=2.0pts → price hits 20002 → flatten, go short 1 contract

### 3. Price Moves Against (≥ StepDist — Martingale)
- **Doubles down** in the same direction using power-of-2 sizing:
  - Level 0: 1 contract, Level 1: 2, Level 2: 4, Level 3: 8
- Resets anchor to current price (so the next step measures from here)
- If `addQty > MaxContractSize` (default 8), resets back to `InitialQty`
- Level wraps back to 0 after reaching `MaxLevels` (default 4)

## Inputs

| # | Name | Default | Purpose |
|---|------|---------|---------|
| 0 | Step Dist (pts) | 2.0 | Distance in points that triggers reversal or add |
| 1 | Initial Qty | 1 | Base position size |
| 2 | Max Martingale Levels | 4 | Levels before reset (1,2,4,8 pattern) |
| 3 | Max Contract Size | 8 | Cap — resets to InitialQty if exceeded |
| 4 | Enable | Yes | On/off switch |
| 5 | CSV Log | Yes | Trade logging to CSV file |

## Persistent State

Uses `sc.GetPersistentDouble/Int` to survive recalculations:
- **AnchorPrice** — last entry/add price (measures step distance from here)
- **Direction** — 1=long, -1=short
- **Level** — current martingale level (0 to MaxLevels-1)
- **OrderPending/FlattenPending** — state machine flags for async order fills

## Key Characteristics

- **Always in the market** — only flat momentarily during reversals
- **Mean-reversion assumption** — profits when price oscillates within the step grid; bleeds when price trends strongly
- **Exponential risk** — martingale sizing (1→2→4→8) means max exposure is 15x InitialQty before reset
- **Runs on last bar only** (`sc.Index != sc.ArraySize - 1`) with `UpdateAlways=1` — real-time execution, not historical backfillable
- **CSV logging** — writes every event (SEED, ADD, REVERSAL, REVERSAL_ENTRY) to `ATEAM_ROTATION_V1_OG_log.csv` in SC's data folder

## Risk Profile

This is a **high-risk** strategy. The martingale doubling means a sustained directional move of 4 steps (8 points at default settings) builds a position of 1+2+4+8 = 15 contracts all underwater. The MaxContractSize cap provides a safety valve but doesn't prevent the drawdown — it just resets sizing.
