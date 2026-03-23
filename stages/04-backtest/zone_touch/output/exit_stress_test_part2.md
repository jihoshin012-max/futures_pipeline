# Zone-Relative Exit Stress Test -- Part 2 (Gaps 6-10)
**Data:** P2 zone-relative answer key (69 trades), P2 fixed answer key (91 trades), P2 bar data (131709 bars)
**Date:** 2026-03-23

## GAP 6: T1 Fill Timing by Zone Width

| Zone Width | N (T1 filled) | Mean bars to T1 | Median | P25 | P75 | % by bar 80 | % by bar 160 |
|-----------|--------------|----------------|--------|-----|-----|-----------|-------------|
| <50t | 1 | 3 | 3 | 3 | 3 | 100% | 100% |
| 50-100t | 9 | 14 | 8 | 2 | 25 | 100% | 100% |
| 100-150t | 15 | 17 | 10 | 1 | 15 | 93% | 100% |
| 150-200t | 12 | 41 | 41 | 16 | 74 | 92% | 100% |
| 200-300t | 16 | 20 | 19 | 13 | 30 | 100% | 100% |
| 300t+ | 9 | 67 | 55 | 53 | 90 | 67% | 100% |

**Slow T1 fills (>80 bars) vs fast (<= 80 bars):**

| Speed | N | Mean wPnL | T2 fill% | Mean bars to T1 |
|-------|---|----------|---------|----------------|
| Fast (<=80) | 57 | 109.3t | 77% | 22 |
| Slow (>80) | 5 | 158.5t | 40% | 106 |

## GAP 7: 16:55 Flatten / Timecap Impact

Trades with at least one leg at timecap (160 bars): 17/69

| Zone Width | TC trades | Mean wPnL at TC | % wPnL > 0 | Mean leg2 PnL | Mean MFE |
|-----------|----------|----------------|-----------|-------------|---------|
| < 150t | 2 | 25.0t | 100% | -12.5t | 83.0t |
| 150-250t | 7 | 25.6t | 71% | -8.3t | 116.6t |
| 250t+ | 8 | 199.0t | 100% | 179.6t | 335.4t |

**Timecap trade detail:**

| Trade | ZW | Mode | Leg1 | Leg2 | wPnL | MFE | Bars |
|-------|---:|------|------|------|-----:|----:|-----:|
| ZB_0009 | 70 | CT | TARGET_1(35) | TIMECAP(24) | 28 | 69 | 160 |
| ZB_0011 | 122 | WTNT | TARGET_1(61) | TIMECAP(-49) | 22 | 97 | 160 |
| ZB_0018 | 192 | CT | TARGET_1(96) | TIMECAP(88) | 90 | 184 | 160 |
| ZB_0034 | 194 | WTNT | TARGET_1(97) | TIMECAP(-103) | 28 | 127 | 160 |
| ZB_0035 | 194 | CT | TARGET_1(97) | TIMECAP(40) | 75 | 102 | 160 |
| ZB_0064 | 201 | WTNT | TIMECAP(-53) | TIMECAP(-53) | -56 | 45 | 160 |
| ZB_0027 | 210 | WTNT | TIMECAP(-134) | TIMECAP(-134) | -137 | 71 | 160 |
| ZB_0021 | 211 | CT | TARGET_1(106) | TIMECAP(136) | 113 | 156 | 160 |
| ZB_0003 | 236 | WTNT | TARGET_1(118) | TIMECAP(-32) | 66 | 131 | 160 |
| ZB_0043 | 282 | CT | TARGET_1(141) | TIMECAP(38) | 104 | 163 | 160 |
| ZB_0025 | 307 | CT | TARGET_1(154) | TIMECAP(65) | 122 | 180 | 160 |
| ZB_0004 | 356 | WTNT | TARGET_1(178) | TIMECAP(286) | 211 | 315 | 160 |
| ZB_0059 | 425 | CT | TIMECAP(117) | TIMECAP(117) | 114 | 177 | 160 |
| ZB_0012 | 443 | CT | TARGET_1(222) | TIMECAP(339) | 258 | 415 | 160 |
| ZB_0053 | 499 | WTNT | TARGET_1(250) | TIMECAP(196) | 229 | 390 | 160 |
| ZB_0054 | 499 | WTNT | TARGET_1(250) | TIMECAP(70) | 188 | 447 | 160 |
| ZB_0056 | 783 | CT | TARGET_1(392) | TIMECAP(326) | 367 | 596 | 160 |

**Unrealized potential at timecap (leg2 exits at TC):**

| Trade | ZW | T2 target | MFE | MFE/T2 | Leg2 PnL at TC | Left on table |
|-------|---:|--------:|----:|-------:|-------------:|-------------:|
| ZB_0009 | 70 | 70 | 69 | 0.99x | 24 | 45t |
| ZB_0011 | 122 | 122 | 97 | 0.80x | -49 | 97t |
| ZB_0018 | 192 | 192 | 184 | 0.96x | 88 | 96t |
| ZB_0034 | 194 | 194 | 127 | 0.65x | -103 | 127t |
| ZB_0035 | 194 | 194 | 102 | 0.53x | 40 | 62t |
| ZB_0064 | 201 | 201 | 45 | 0.22x | -53 | 45t |
| ZB_0027 | 210 | 210 | 71 | 0.34x | -134 | 71t |
| ZB_0021 | 211 | 211 | 156 | 0.74x | 136 | 20t |
| ZB_0003 | 236 | 236 | 131 | 0.56x | -32 | 131t |
| ZB_0043 | 282 | 282 | 163 | 0.58x | 38 | 125t |
| ZB_0025 | 307 | 307 | 180 | 0.59x | 65 | 115t |
| ZB_0004 | 356 | 356 | 315 | 0.88x | 286 | 29t |
| ZB_0059 | 425 | 425 | 177 | 0.42x | 117 | 60t |
| ZB_0012 | 443 | 443 | 415 | 0.94x | 339 | 76t |
| ZB_0053 | 499 | 499 | 390 | 0.78x | 196 | 194t |
| ZB_0054 | 499 | 499 | 447 | 0.90x | 70 | 377t |
| ZB_0056 | 783 | 783 | 596 | 0.76x | 326 | 270t |

## GAP 8: Session x Zone Width

**Zone-relative exits by session:**

| Session | N | Mean ZW | WR | PF | EV | Stop rate | Total PnL |
|---------|---|--------|----|----|----|---------:|----------|
| RTH | 50 | 213t | 96.0% | 30.18 | 112.6t | 0% | 5632t |
| ETH | 19 | 192t | 89.5% | 48.34 | 101.7t | 0% | 1932t |

**Fixed exits by session (for comparison):**

| Session | N | WR | PF | EV | Total PnL |
|---------|---|----|----|----|---------:|
| RTH | 69 | 92.8% | 11.84 | 47.4t | 3274t |
| ETH | 22 | 81.8% | 2.17 | 24.0t | 528t |

**Session x zone width (ZR):**

| Session + Width | N | WR | PF | EV | Total |
|----------------|---|----|----|----|---------:|
| RTH + narrow (<100t) | 5 | 100.0% | inf | 37.7t | 188t |
| RTH + medium (100-200t) | 21 | 100.0% | inf | 89.5t | 1880t |
| RTH + wide (200t+) | 24 | 91.7% | 19.46 | 148.5t | 3563t |
| ETH + narrow (<100t) | 6 | 83.3% | 10.83 | 34.6t | 208t |
| ETH + medium (100-200t) | 7 | 85.7% | 23.07 | 62.0t | 434t |
| ETH + wide (200t+) | 6 | 100.0% | inf | 215.1t | 1291t |

## GAP 9: Limit Depth vs Zone Width (CT Only)

Overall CT fill rate: 41/45 (91.1%)
CT limit expired: 4

**CT limit fill analysis by zone width:**

| Zone Width | CT trades | Mean bars held | Mean MFE | 5t as % of ZW |
|-----------|----------|---------------|---------|--------------|
| <50t | 1 | 9 | 55t | 10.6% |
| 50-100t | 3 | 57 | 87t | 6.7% |
| 100-150t | 10 | 45 | 132t | 4.2% |
| 150-200t | 9 | 82 | 183t | 2.6% |
| 200-300t | 10 | 86 | 231t | 2.1% |
| 300t+ | 8 | 125 | 415t | 1.1% |

*Note: 5t as % of ZW shows how deep the limit goes relative to zone width. For narrow zones (50t), 5t = 10% of zone. For wide zones (300t), 5t = 1.7%.*

## GAP 10: Cost Asymmetry

PF with 3t cost vs 0t cost by zone width:

| Zone Width | N | PF @3t | PF @0t | PF delta | Cost as % of EV |
|-----------|---|--------|--------|---------|----------------|
| <50t | 1 | inf | inf | +0.00 | 10.5% |
| 50-100t | 10 | 18.37 | 22.89 | +4.52 | 8.2% |
| 100-150t | 15 | 50.23 | 61.79 | +11.57 | 4.6% |
| 150-200t | 13 | inf | inf | +0.00 | 2.9% |
| 200-300t | 19 | 12.55 | 13.22 | +0.68 | 2.6% |
| 300t+ | 11 | inf | inf | +0.00 | 1.3% |

**ALL: PF @3t = 33.35, PF @0t = 36.03, cost = 2.7% of EV**

## Summary -- Combined Gap Classification (Parts 1 + 2)

| Gap | Priority | Classification | Key Finding | Action |
|-----|----------|---------------|-------------|--------|
| 1. T2 fill rate | HIGH | **MONITOR** | 300t+ T2 fill = 36% (n=11), but 0% stop rate | Track 300t+ T2 fill in paper trading |
| 2. BE step-up | HIGH | **BENIGN** | BE hurts all width bins | No BE -- confirmed |
| 3. T1+T2stop loss | HIGH | **MONITOR** | 2/69 trades (2.9%), -41t total | Mathematically always negative; low frequency |
| 4. Overlap cost | HIGH | **BENIGN** | -22 trades but +3,762t net profit | EV improvement outweighs volume loss |
| 5. Mode-specific mults | HIGH | **MONITOR** | WT T2 alternatives no improvement | No mode-specific exits needed |
| 6. T1 fill timing | MEDIUM | **MONITOR** | 300t+ mean 67 bars vs 50-100t mean 14 bars | Track slow T1 fills in paper trading |
| 7. TC/flatten impact | MEDIUM | **MONITOR** | 17 TC trades (25%), 88% profitable | Monitor flatten timing in paper trading |
| 8. Session x width | MEDIUM | **MONITOR** | RTH PF=30.18 vs ETH PF=48.34 | Monitor ETH performance in paper trading |
| 9. Limit depth | LOW | **BENIGN** | CT fill rate 91%, 5t depth scales well | No change needed |
| 10. Cost asymmetry | LOW | **BENIGN** | 3t cost = 2.7% of EV, minimal impact on PF | No change needed |

**Overall verdict: ZERO BLOCKERS across all 10 gaps. Spec proceeds to paper trading as-is.**