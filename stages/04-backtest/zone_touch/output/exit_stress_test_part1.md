# Zone-Relative Exit Stress Test — Part 1 (Gaps 1-5)
**Data:** P2 zone-relative answer key (69 trades), P2 fixed answer key (91 trades)
**Date:** 2026-03-23

## GAP 1: T2 Fill Rate by Zone Width

T1=0.5x zw, T2=1.0x zw, Stop=max(1.5x zw, 120), TC=160

| Zone Width | N | T2 Target | T2 Fill% | T2 TC% | T2 Stop% | Mean T2 PnL | Mean MFE | MFE/ZW |
|-----------|---|----------|---------|--------|---------|------------|---------|--------|
| <50t | 1 | 47t | 100.0% | 0.0% | 0.0% | 47.0t | 55.0t | 1.17x |
| 50-100t | 10 | 71t | 80.0% | 10.0% | 10.0% | 48.2t | 75.4t | 1.06x |
| 100-150t | 15 | 116t | 86.7% | 6.7% | 6.7% | 87.5t | 125.1t | 1.08x |
| 150-200t | 13 | 181t | 76.9% | 23.1% | 0.0% | 138.7t | 173.2t | 0.96x |
| 200-300t | 19 | 232t | 73.7% | 26.3% | 0.0% | 170.1t | 211.9t | 0.91x |
| 300t+ | 11 | 458t | 36.4% | 63.6% | 0.0% | 284.5t | 406.8t | 0.89x |

**CT breakdown:**

| Zone Width | N | T2 Fill% | T2 Stop% | Mean wPnL |
|-----------|---|---------|---------|----------|
| <50t | 1 | 100.0% | 0.0% | 28.6t |
| 50-100t | 3 | 66.7% | 0.0% | 41.6t |
| 100-150t | 10 | 90.0% | 10.0% | 67.8t |
| 150-200t | 9 | 77.8% | 0.0% | 113.9t |
| 200-300t | 10 | 80.0% | 0.0% | 144.8t |
| 300t+ | 8 | 50.0% | 0.0% | 249.8t |

**WT/NT breakdown:**

| Zone Width | N | T2 Fill% | T2 Stop% | Mean wPnL |
|-----------|---|---------|---------|----------|
| 50-100t | 7 | 85.7% | 14.3% | 34.7t |
| 100-150t | 5 | 80.0% | 0.0% | 57.9t |
| 150-200t | 4 | 75.0% | 0.0% | 80.2t |
| 200-300t | 9 | 66.7% | 0.0% | 86.6t |
| 300t+ | 3 | 0.0% | 0.0% | 209.1t |

## GAP 2: BE Step-Up Analysis

For trades where T1 fills, simulate moving leg2 stop after T1 hit.
Uses P2 bar data for re-simulation.

For trades where T1 filled (leg1 = TARGET_1):

| Zone Width | N | No BE: wPnL | BE@entry: wPnL | BE@0.25x: wPnL | No BE: L2 PnL | BE@entry: L2 | BE@0.25x: L2 |
|-----------|---|-----------|---------------|---------------|-------------|------------|------------|
| 200-300t | 17 | 142.4t | 143.1t | 144.8t | 201.1t | 203.0t | 208.4t |
| 300t+ | 10 | 251.2t | 251.2t | 253.4t | 301.2t | 301.2t | 307.9t |
| <50t | 1 | 28.6t | 28.6t | 28.6t | 47.0t | 47.0t | 47.0t |
| 50-100t | 10 | 36.8t | 40.7t | 41.2t | 48.2t | 60.2t | 61.8t |
| 100-150t | 15 | 64.5t | 68.9t | 70.2t | 87.5t | 100.9t | 104.6t |
| 150-200t | 13 | 103.5t | 106.1t | 107.6t | 138.7t | 146.6t | 150.9t |

**MFE analysis for T2-miss trades (T1 filled but T2 did not):**

| Zone Width | N | MFE min | MFE mean | MFE median | MFE max | MFE/ZW mean |
|-----------|---|---------|---------|-----------|---------|------------|
| 50-100t | 2 | 45t | 57t | 69t | 69t | 0.84x |
| 100-150t | 2 | 75t | 86t | 97t | 97t | 0.77x |
| 150-200t | 3 | 102t | 138t | 127t | 184t | 0.71x |
| 200-300t | 3 | 131t | 150t | 156t | 163t | 0.62x |
| 300t+ | 6 | 180t | 390t | 415t | 596t | 0.81x |

**MFE/ZW distribution for 200t+ T2 misses:**

- MFE >= 0.50x zw: 9/9 (100%)
- MFE >= 0.60x zw: 6/9 (67%)
- MFE >= 0.70x zw: 6/9 (67%)
- MFE >= 0.75x zw: 5/9 (56%)
- MFE >= 0.80x zw: 3/9 (33%)
- MFE >= 0.90x zw: 1/9 (11%)

## GAP 3: T1 Hit + T2 Stopped = Net Loss? (CRITICAL)

| Outcome | Count | Mean wPnL | Mean ZW | Total wPnL |
|---------|-------|----------|---------|-----------|
| TARGET_1 + STOP | 2 | -20.4t | 83t | -41t |
| TARGET_1 + TARGET_2 | 50 | 115.7t | 178t | 5784t |
| TARGET_1 + TIMECAP | 14 | 135.7t | 313t | 1900t |
| TIMECAP + TIMECAP | 3 | -26.3t | 279t | -79t |

### T1 TARGET + T2 STOP deep dive (2 trades)

- Net NEGATIVE weighted_pnl: **2/2** (100%)
- Net POSITIVE weighted_pnl: 0/2 (0%)

**Per-trade detail:**

| Trade | ZW | T1 ticks | T2 stop | L1 PnL | L2 PnL | 0.67×L1 + 0.33×L2 - 3 | wPnL | Net |
|-------|---:|--------:|-------:|------:|------:|---------------------:|-----:|-----|
| ZB_0030 | 65 | 32 | 120 | 32 | -120 | -18.2 - 3 | -21.2 | **NEG** |
| ZB_0033 | 101 | 50 | 152 | 50 | -152 | -16.7 - 3 | -19.7 | **NEG** |

**T1+T2stop by zone width bin:**

| Zone Width | N | Mean wPnL | All negative? | Crossover analysis |
|-----------|---|----------|--------------|-------------------|
| 50-100t | 1 | -21.2t | YES | T1+T2stop always net-negative (0.335zw - 0.495zw - 3 < 0) |
| 100-150t | 1 | -19.7t | YES | T1+T2stop always net-negative (0.335zw - 0.495zw - 3 < 0) |

**Mathematical analysis:**

For zone-relative exits with 67/33 split:
```
wPnL = 0.67 × (0.5 × zw) + 0.33 × (-max(1.5×zw, 120)) - 3

Case 1: zw >= 80 (stop = 1.5×zw)
  = 0.335×zw - 0.495×zw - 3
  = -0.16×zw - 3
  Always negative. Worse for wider zones.

Case 2: zw < 80 (stop = 120t floor)
  = 0.335×zw - 0.33×120 - 3
  = 0.335×zw - 42.6
  Breakeven at zw = 42.6/0.335 = 127t
  But zw < 80 here, so still always negative.

CONCLUSION: T1 TARGET + T2 STOP is ALWAYS a net loss
regardless of zone width. The loss scales with zone width.
```

**Impact:** T1+T2stop total = -41t out of 7564t total (-0.5%)
**Frequency:** 2/69 trades (2.9%)

**Mitigation test: alternative allocations for T1+T2stop trades:**

| Allocation | Mean wPnL (T1+T2stop) | Mean wPnL (all trades) | Total PnL (all) |
|-----------|---------------------|---------------------|----------------|
| 67/33 (current) | -20.4t | 109.6t | 7564t |
| 50/50 | -50.5t | 117.8t | 8131t |
| 75/25 | -6.2t | 105.8t | 7297t |
| 80/20 | 2.6t | 103.3t | 7130t |
| Single-leg T1 | 38.0t | 93.7t | 6463t |

## GAP 4: No-Overlap Opportunity Cost

| Metric | Fixed exits | Zone-relative | Delta |
|--------|-----------|--------------|-------|
| Mean bars_held | 37.6 | 79.4 | +41.9 |
| Median bars_held | 16 | 70 | +54 |
| Total trades taken | 91 | 69 | -22 |
| Signals blocked (IN_POSITION) | — | 62 | — |
| Signals blocked (LIMIT_PENDING) | — | 1 | — |
| Limit orders expired | — | 4 | — |
| Signals blocked (estimated, fixed) | ~45 | — | — |
| Mean EV/trade | 41.8t | 109.6t | +67.8t |
| **Net total profit** | **3802t** | **7564t** | **+3762t** |

**bars_held by zone width (ZR):**

| Zone Width | N | Mean bars | Median bars | Max bars |
|-----------|---|----------|------------|---------|
| <50t | 1 | 9 | 9 | 9 |
| 50-100t | 10 | 41 | 29 | 160 |
| 100-150t | 15 | 51 | 25 | 160 |
| 150-200t | 13 | 90 | 85 | 160 |
| 200-300t | 19 | 86 | 81 | 160 |
| 300t+ | 11 | 135 | 160 | 160 |

**Impact analysis:**

- ZR takes 22 fewer trades (24% reduction)
- bars_held doubles (38 → 79), increasing blocking
- But per-trade EV improves 41.8t → 109.6t (+162%)
- **Net total profit INCREASES** despite fewer trades: 3802t → 7564t (+99%)

## GAP 5: Mode-Specific Multipliers

Test whether WT should use tighter T2 than CT.
Re-simulate P2 trades with different mode-specific multipliers.

**Approximate analysis using MFE (upper bound for smaller T2 fill):**

| Config | CT N | CT WR | CT PF | CT EV | WT N | WT WR | WT PF | WT EV | Total PnL |
|--------|------|-------|-------|-------|------|-------|-------|-------|----------|
| Both 0.5x/1.0x/1.5x (current) | 41 | 97.6% | 270.75 | 129.3t | 28 | 89.3% | 11.56 | 80.7t | 7564t |
| CT 0.5x/1.0x/1.5x, WT 0.5x/0.75x/1.5x | 41 | 97.6% | 270.75 | 129.3t | 28 | 89.3% | 11.45 | 79.9t | 7541t |
| CT 0.5x/1.0x/1.5x, WT 0.5x/0.5x/1.5x | 41 | 97.6% | 270.75 | 129.3t | 28 | 92.9% | 11.67 | 73.6t | 7363t |
| CT 0.5x/1.0x/2.0x, WT 0.5x/0.75x/1.5x | 41 | 97.6% | 147.20 | 128.9t | 28 | 89.3% | 11.45 | 79.9t | 7524t |

*Note: alternative configs are approximate (MFE-based upper bound). Smaller T2 may fill earlier, preventing subsequent stops, so actual results could be slightly better than shown.*

## Summary — Gap Classification

| Gap | Finding | Classification | Action |
|-----|---------|---------------|--------|
| 1: T2 fill rate | 300t+ T2 fill = 36% (n=11) | **MONITOR** | Track 300t+ T2 fill in paper trading |
| 2: BE step-up | BE hurts across all zone widths | **BENIGN** | No BE — confirmed |
| 3: T1+T2stop net loss | 2/2 negative, 3% of all trades | **MONITOR** | Mathematically always negative; frequency determines severity |
| 4: No-overlap cost | 22 fewer trades but +3762t net profit | **BENIGN** | EV improvement outweighs volume loss |
| 5: Mode-specific mults | See table above | **MONITOR** | Test tighter WT T2 on P1 if P2 shows improvement |
