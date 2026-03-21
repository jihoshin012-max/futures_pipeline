# Post-Pullback Displacement + Completion Analysis
**Data:** P1 RTH 1-tick, child threshold = 10 pts
**Parent thresholds:** [25, 35, 40]

## Query 1: Post-Pullback Favorable Displacement

From the pullback resumption point, how far does price typically travel favorably?

| Parent | Samples | Median | P25 | P75 | P90 | Completion% |
|--------|---------|--------|-----|-----|-----|-------------|
| 25 | 3,577 | 27.2 | 18.5 | 37.2 | 47.0 | 63.5% |
| 35 | 2,230 | 34.2 | 21.8 | 45.8 | 57.5 | 61.9% |
| 40 | 1,771 | 38.2 | 23.5 | 50.2 | 62.0 | 61.0% |

### Displacement thresholds (% of pullbacks reaching each level)

| Parent | >=10pts | >=15pts | >=20pts | >=25pts | >=30pts | >=40pts |
|--------|---------|---------|---------|---------|---------|---------|
| 25 | 100.0% | 84.3% | 71.1% | 57.6% | 42.6% | 19.8% |
| 35 | 100.0% | 88.5% | 78.9% | 69.5% | 59.0% | 36.5% |
| 40 | 100.0% | 89.8% | 80.9% | 72.3% | 63.8% | 46.2% |

## Query 2: Completion Rate by Pullback Depth

Does shallow pullback → higher completion rate?

### Parent = 25 pts

| Depth Bucket | Samples | Completion% | Median Post-PB Fav |
|-------------|---------|-------------|-------------------|
| Shallow (<=25%) | 0 | 0.0% | 0.0 pts |
| Moderate (25-50%) | 95 | 94.7% | 19.2 pts |
| Deep (50-75%) | 551 | 85.8% | 23.0 pts |
| Very deep (75-100%) | 1,927 | 67.2% | 29.0 pts |

### Parent = 35 pts

| Depth Bucket | Samples | Completion% | Median Post-PB Fav |
|-------------|---------|-------------|-------------------|
| Shallow (<=25%) | 0 | 0.0% | 0.0 pts |
| Moderate (25-50%) | 174 | 89.7% | 23.9 pts |
| Deep (50-75%) | 403 | 80.4% | 31.5 pts |
| Very deep (75-100%) | 1,072 | 61.7% | 37.5 pts |

### Parent = 40 pts

| Depth Bucket | Samples | Completion% | Median Post-PB Fav |
|-------------|---------|-------------|-------------------|
| Shallow (<=25%) | 0 | 0.0% | 0.0 pts |
| Moderate (25-50%) | 173 | 87.3% | 28.5 pts |
| Deep (50-75%) | 304 | 72.4% | 35.0 pts |
| Very deep (75-100%) | 817 | 61.6% | 42.2 pts |

## Strategy Implications

Key questions answered:

1. **Is the success target reachable from the pullback point?**
   Compare P75 post-pullback displacement against RT×SD:
   - SD=25, RT=0.8: target = 20 pts from entry
   - SD=35, RT=1.0: target = 35 pts from entry
   - SD=40, RT=0.8: target = 32 pts from entry

2. **Do shallow pullbacks complete more reliably?**
   If shallow >> deep completion rate, pullback_depth_pct is a viable filter.

3. **What is the structural completion rate after a pullback?**
   If completion rate ≈ random walk prediction, pullback entry adds no edge.
   Random walk: SD/(RT×SD + SD) = 1/(RT+1).
   - RT=0.8: RW = 55.6%
   - RT=1.0: RW = 50.0%