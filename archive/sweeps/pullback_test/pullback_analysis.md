# Pullback Entry Analysis
**Date:** 2026-03-21 10:22:19

## Pullback Depth Distribution

- Count: 10285
- Mean: 42.1%
- Median: 35.4%
- P25: 28.7%
- P75: 48.3%
- Min: 9.6%, Max: 143.1%

## Success Rate by Pullback Depth Quartile

| Quartile | Count | SR | Avg Depth |
|----------|-------|-----|-----------|
| Q1 (shallow) | 2574 | 56.1% | 23.4% |
| Q2 | 2580 | 53.1% | 32.3% |
| Q3 | 2563 | 56.3% | 39.2% |
| Q4 (deep) | 2568 | 55.5% | 73.7% |

## Confirming Duration Distribution

- Count: 10285
- Median: 1233 bars
- Mean: 2294 bars
- P25: 539, P75: 2759

## Success Rate by Confirming Duration

- Quick pullback (<= 1233 bars): SR = 54.0% (5143 cycles)
- Slow pullback (> 1233 bars): SR = 56.5% (5142 cycles)

## Runaway Entries (HWM > 2×StepDist)

- Runaway entries: 542 (5.3%)
- Runaway SR: 57.0% vs Normal SR: 55.1%

## Failure Cascade Rate by Option

| Config | Option | Cycles | Failure-after-Failure | Cascade Rate |
|--------|--------|--------|----------------------|--------------|
| PB_SD40_RT80_OPTA | A | 957 | 174 | 18.2% |
| PB_SD40_RT80_OPTB | B | 1148 | 229 | 19.9% |
| PB_SD40_RT80_OPTC | C | 2295 | 406 | 17.7% |
| PB_SD35_RT100_OPTA | A | 1159 | 281 | 24.2% |
| PB_SD35_RT100_OPTB | B | 1311 | 316 | 24.1% |
| PB_SD35_RT100_OPTC | C | 2413 | 582 | 24.1% |
| PB_SD25_RT80_OPTA | A | 2515 | 481 | 19.1% |
| PB_SD25_RT80_OPTB | B | 3018 | 558 | 18.5% |
| PB_SD25_RT80_OPTC | C | 6106 | 1223 | 20.0% |

## Fractal-Aligned Completion Rate (First Cycles Only)

For first-cycle-of-day pullback entries where `remaining_to_parent_target` is defined:
how often does price reach the parent target level (WatchPrice + StepDist) at any
point during the cycle — regardless of strategy exit outcome?

**531 first cycles across all 9 configs.**

### How far is the entry from the parent target?

- Median remaining: **3.5 pts**
- Mean remaining: **0.2 pts**
- P25: -6.5 pts (entry is PAST the parent target)
- P75: 8.25 pts

The pullback entry occurs very close to — or beyond — the parent completion level.
In 25% of cases the entry is already past the parent target (negative remaining).

### Overall fractal-aligned completion rate: **92.1%** (489/531)

| Config | Completion Rate | Cycles | Median Remaining |
|--------|----------------|--------|-----------------|
| SD25 (all options) | **100.0%** | 59 each | 4.5 pts |
| SD35 (all options) | **86.4%** | 59 each | 1.8 pts |
| SD40 (all options) | **89.8%** | 59 each | 2.8 pts |

### Completion by pullback depth quartile — depth gradient reappears

| Quartile | Count | Parent CR | Avg Depth | Med Remaining | Strategy SR |
|----------|-------|-----------|-----------|---------------|-------------|
| Q1 (shallow) | 135 | **100.0%** | 21.5% | -13.0 pts | 68.9% |
| Q2 | 132 | **100.0%** | 28.5% | 0.0 pts | 65.9% |
| Q3 | 135 | **91.1%** | 33.8% | 6.2 pts | 66.7% |
| Q4 (deep) | 129 | **76.7%** | 38.1% | 12.2 pts | 58.1% |

The depth gradient is strong when measuring against the PARENT target (100% → 77%)
but nearly flat when measuring against the STRATEGY target (69% → 58%). The fractal
edge exists but the strategy's success target (RT×SD from entry) overshoots it.

### Gap: strategy target vs remaining parent distance

| Config | Strategy Target | Median Remaining | Ratio |
|--------|----------------|-----------------|-------|
| SD25, RT=0.8 | 20 pts | 4.5 pts | **4.4×** |
| SD35, RT=1.0 | 35 pts | 1.8 pts | **20.0×** |
| SD40, RT=0.8 | 32 pts | 2.8 pts | **11.6×** |

The strategy asks for 4-20× more displacement than what remains of the parent move
from the pullback entry point. The fractal predicts ~90% completion of the parent
move — but the parent move is nearly complete by the time the pullback entry fires.
The strategy's success target extends far beyond the fractal's coverage into
uncorrelated territory.

## First Cycle vs Later Cycle Success Rate

| Config | Option | First Cycle SR | Later Cycle SR |
|--------|--------|---------------|----------------|
| PB_SD40_RT80_OPTA | A | 66.1% | 55.9% |
| PB_SD40_RT80_OPTB | B | 66.1% | 54.9% |
| PB_SD40_RT80_OPTC | C | 66.1% | 57.8% |
| PB_SD35_RT100_OPTA | A | 61.0% | 49.8% |
| PB_SD35_RT100_OPTB | B | 61.0% | 49.3% |
| PB_SD35_RT100_OPTC | C | 61.0% | 50.7% |
| PB_SD25_RT80_OPTA | A | 67.8% | 56.2% |
| PB_SD25_RT80_OPTB | B | 67.8% | 57.1% |
| PB_SD25_RT80_OPTC | C | 67.8% | 55.5% |