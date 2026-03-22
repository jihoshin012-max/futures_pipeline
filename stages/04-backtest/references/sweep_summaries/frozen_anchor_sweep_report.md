# Frozen-Anchor Smoke Test Report
**Date:** 2026-03-21 03:27:10
**Bars:** 25,457,094 (RTH, P1, 1-tick)
**Config:** SD=25, AD=10 (R04), MA=2, cost=2.0t/side

## RT Comparison (Key Question: Does success rate increase as RT decreases?)

| RT | Cycles | Success% | Failure% | Win% | Net PnL | Adj Net | Avg HWM(S) | Avg HWM(F) | Time |
|----|--------|----------|----------|------|---------|---------|------------|------------|------|
| 0.5 | 9815 | 66.8% | 33.2% | 66.8% | -70001 | -70611 | 50.4 | 20.9 | 198.4s |
| 0.6 | 8081 | 62.0% | 38.0% | 62.0% | -77521 | -77830 | 60.4 | 25.2 | 198.9s |
| 0.7 | 6968 | 59.2% | 40.8% | 59.2% | -53895 | -53197 | 70.3 | 28.5 | 198.7s |
| 0.8 | 6019 | 55.6% | 44.4% | 55.6% | -53369 | -52115 | 80.2 | 32.6 | 198.3s |
| 1.0 | 4856 | 49.4% | 50.6% | 49.4% | -54336 | -52268 | 100.2 | 37.8 | 195.7s |

## Monotonicity Check
**PASS**: Success rate monotonically decreases as RT increases.
- RT=0.5: success_rate=0.6683
- RT=0.6: success_rate=0.6198
- RT=0.7: success_rate=0.5917
- RT=0.8: success_rate=0.5559
- RT=1.0: success_rate=0.4944

**RT=0.5 success rate: 66.8%** vs **RT=1.0: 49.4%**
Core thesis SUPPORTED: lower RT produces higher success rate.

## First Cycle vs Later Cycle Success Rate
| RT | First Cycle SR | Later Cycle SR |
|----|---------------|----------------|
| 0.5 | 74.6% | 66.8% |
| 0.6 | 71.2% | 61.9% |
| 0.7 | 67.8% | 59.1% |
| 0.8 | 62.7% | 55.5% |
| 1.0 | 61.0% | 49.3% |