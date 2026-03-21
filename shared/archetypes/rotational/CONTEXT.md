# Rotational Archetype — Context

## Current Status: Research Arc Closed — Random Walk Finding

### Summary
Systematic investigation of fractal-informed rotational strategies concluded
that NQ at the 15-50pt intraday scale behaves as a random walk from every
accessible entry point. The fractal structure is real (geometric self-similarity,
completion rates, waste ratios) but describes the SHAPE of price movement,
not a tradeable directional edge.

### What Was Done
- Fractal discovery: 6 structural facts established (Sept 2025 - Mar 2026 data)
- V1.1 sweep: 182 configs, 4 approaches. Walking anchor causes stuck positions.
- Frozen-anchor pivot: symmetric failure exit. 210 configs swept.
- Pullback entry: 3 re-entry options. First-cycle +10pp, but total PnL worse.
- Decoupled seed: smaller detection = lower SR (inverted prediction).
- Structural factors: 7 queries. Multi-scale alignment WEAK. Speed WEAK.
- Post-completion reversion: 100% at 16pt is definitional. From entry: random walk.
- P2a validation: FAIL. First-cycle edge collapsed. Later-cycle: +$37/day.

### Key Finding: Random Walk at All Entry Points
SR matches first-passage formula b/(a+b) within 1-3pp across:
- 5 RT values (0.5-1.0)
- 7 StepDist values (15-50)
- 6 add configurations
- 4 entry methods (immediate, pullback, decoupled seed, reversion)
- 2 time periods (P1 and P2a)

### Preserved Assets
- Fractal knowledge base: `stages/01-data/analysis/fractal_discovery/`
- Frozen-anchor simulator: `stages/04-backtest/rotational/`
- Structural factors: `stages/01-data/analysis/fractal_discovery/structural_factors/`
- P2a results: `stages/05-assessment/rotational/p2a_validation/`
- P2b holdout: NOT consumed (reserved for future use)

### What Would Need to Change for Future Work
The random walk finding applies to PRICE-DISTANCE strategies at intraday scales.
It does NOT rule out:
- Order flow / volume-driven strategies (different information source)
- Cross-scale strategies using structural factors (time-of-day, volume ratio)
- Non-directional strategies (market-making, volatility capture)
- Longer timeframe strategies where fractal properties may carry directional info

### Period Boundaries
- P1: Sept 22 - Dec 12, 2025 (60 RTH days, fully consumed)
- P2a: Dec 18 - Jan 30, 2026 (30 RTH days, consumed — FAIL)
- P2b: Feb 2 - Mar 13, 2026 (30 RTH days, NOT consumed)
