# Zone Touch Exit Investigation — Part 2 of 3

## SECTION 3: PENETRATION DYNAMICS

### 3A) Penetration Speed Profile

| Metric | Winners (n=280) | Losers (n=32) | All (n=312) |
|--------|---------|--------|-----|
| Mean bars to reach 25t adverse | 16.3 | 4.8 | 15.0 |
| Mean bars to reach 50t adverse | 32.3 | 8.0 | 29.2 |
| Mean bars to reach 100t adverse | 58.7 | 22.0 | 52.2 |
| Mean bars to reach max adverse | 57.1 | 58.4 | 57.2 |
| Pen speed at 10 bars (t/bar) | 4.1 | 9.6 | 4.7 |
| Pen speed at 25 bars (t/bar) | 2.3 | 5.8 | 2.7 |

% of trades reaching adverse threshold:

| Threshold | Winners | Losers | All |
|-----------|---------|--------|-----|
| 25t | 259/280 (92%) | 32/32 (100%) | 291/312 (93%) |
| 50t | 219/280 (78%) | 32/32 (100%) | 251/312 (80%) |
| 100t | 130/280 (46%) | 28/32 (88%) | 158/312 (51%) |

### 3B) Speed-Based and No-Bounce Exit Rules

**TYPE 1 — Fast penetration (catches deep blowouts):**

| Speed threshold | Trades exited | Would have lost | Would have won | Losers caught % | Winners killed % | Net PF | PF Δ |
|----------------|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| 50t in 5 bars | 66 | 19 | 47 | 59% | 17% | 3.06 | -0.48 |
| 50t in 10 bars | 110 | 24 | 86 | 75% | 31% | 1.77 | -1.77 |
| 75t in 5 bars | 35 | 16 | 19 | 50% | 7% | 3.56 | +0.02 |
| 75t in 10 bars | 52 | 18 | 34 | 56% | 12% | 2.71 | -0.83 |
| 100t in 10 bars | 22 | 13 | 9 | 41% | 3% | 3.60 | +0.06 |
| 100t in 20 bars | 51 | 19 | 32 | 59% | 11% | 2.35 | -1.19 |

**TYPE 2 — Slow no-bounce (catches battleground drifters):**

| Rule | Trades exited | Would have lost | Would have won | Losers caught % | Winners killed % | Net PF | PF Δ |
|------|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| 50t adv, no 20t bounce in 30 bars | 0 | 0 | 0 | 0% | 0% | 3.54 | +0.00 |
| 50t adv, no 20t bounce in 50 bars | 0 | 0 | 0 | 0% | 0% | 3.54 | +0.00 |
| 75t adv, no 25t bounce in 30 bars | 0 | 0 | 0 | 0% | 0% | 3.54 | +0.00 |
| 75t adv, no 25t bounce in 50 bars | 0 | 0 | 0 | 0% | 0% | 3.54 | +0.00 |
| 100t adv, no 30t bounce in 40 bars | 0 | 0 | 0 | 0% | 0% | 3.54 | +0.00 |
| Adverse > 50t at bar 60 (PnL<0) | 48 | 18 | 30 | 56% | 11% | 2.11 | -1.42 |

Baseline PF = 3.54

### 3C) Opposite Edge Cross as Live Exit Signal

Winners that crossed opposite edge: 13/280 (4.6%)
Losers that crossed opposite edge: 9/32 (28.1%)

| Strategy | Trades affected | Losses saved | Wins killed | Mean PnL early exits | Net PF |
|----------|:---:|:---:|:---:|:---:|:---:|
| Exit at opposite edge | 22 | 9 | 13 | -113.3 | 2.91 |
| Exit at opp edge + 10t | 22 | 9 | 13 | -123.3 | 2.80 |
| Exit at opp edge + 25t | 15 | 9 | 6 | -126.7 | 3.35 |

### 3D) Penetration Stall Detection (Battleground, MAE 50-150t)

⚠️ LOW CONFIDENCE: 9 losers = 3 unique touch events × modes

| Metric | Winners (n=103) | Losers (n=9) |
|--------|---------|--------|
| Mean bars at max pen before 25t reversal | 2.8 | 3.0 |
| Median bars | 2.0 | 2.0 |
| % stalled > 5 bars before reversing | 11% | 0% |
| % drove through without 25t bounce | 0% | 0% |

### 3E) MFE Timing Profile

**All trades:**

| Bars after entry | Mean MFE (winners) | Mean MFE (losers) | % reached T1 (winners) | % reached T1 (losers) |
|:---:|:---:|:---:|:---:|:---:|
| 10 bars | 69.4t | 31.4t | 61% | 28% |
| 20 bars | 106.9t | 54.9t | 80% | 28% |
| 30 bars | 130.6t | 74.1t | 86% | 28% |
| 50 bars | 178.2t | 105.2t | 94% | 28% |
| 100 bars | 264.6t | 187.5t | 99% | 50% |

**CT trades (T1=40t):**

| Bars | Mean MFE (W) | Mean MFE (L) | % W reached T1 | % L reached T1 |
|:---:|:---:|:---:|:---:|:---:|
| 10 | 70.2t | 35.5t | 70% | 56% |
| 20 | 116.0t | 82.2t | 86% | 56% |
| 30 | 141.0t | 120.8t | 89% | 56% |
| 50 | 181.9t | 182.2t | 92% | 56% |
| 100 | 278.7t | 343.9t | 98% | 100% |

**WT trades (T1=60t):**

| Bars | Mean MFE (W) | Mean MFE (L) | % W reached T1 | % L reached T1 |
|:---:|:---:|:---:|:---:|:---:|
| 10 | 68.2t | 27.3t | 48% | 0% |
| 20 | 92.5t | 27.5t | 71% | 0% |
| 30 | 114.4t | 27.5t | 82% | 0% |
| 50 | 172.4t | 28.1t | 95% | 0% |
| 100 | 242.6t | 31.1t | 100% | 0% |

---

## SECTION 4: EXIT RE-OPTIMIZATION WITH 5t ENTRY

CT trades: 187 total, 177 fill 5t (95%), 10 skipped
WT trades: 125 (all at market entry)

### 4A) Single-Leg Sweep — FIXED Framework (5t CT entry)

| Target | Stop | TC | CT WR | CT PF | CT n | WT WR | WT PF | WT n |
|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| 40t | 100t | 160 | 90.4% | 3.38 | 177 | 84.0% | 1.89 | 125 |
| 40t | 120t | 160 | 94.4% | 5.02 | 177 | 88.8% | 2.39 | 125 |
| 40t | 150t | 160 | 96.0% | 5.87 | 177 | 93.6% | 3.54 | 125 |
| 40t | 190t | 160 | 100.0% | inf | 177 | 93.6% | 2.80 | 125 |
| 60t | 100t | 160 | 84.2% | 2.94 | 177 | 76.0% | 1.75 | 125 |
| 60t | 120t | 160 | 88.7% | 3.64 | 177 | 80.8% | 1.95 | 125 |
| 60t | 150t | 160 | 90.4% | 3.51 | 177 | 87.2% | 3.09 | 125 |
| 80t | 100t | 160 | 75.1% | 2.22 | 177 | 73.6% | 1.96 | 125 |
| 80t | 150t | 160 | 81.4% | 2.16 | 177 | 85.6% | 3.38 | 125 |

### 4A2) Single-Leg Sweep — ZONE-RELATIVE Framework (5t CT entry)

| Target | Stop | TC | CT WR | CT PF | CT n | WT WR | WT PF | WT n |
|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| 0.5x zw | 1.0x zw | 160 | 94.4% | 20.16 | 177 | 85.6% | 5.91 | 125 |
| 0.5x zw | 1.5x zw | 160 | 98.3% | 1275.53 | 177 | 90.4% | 8.84 | 125 |
| 0.5x zw | 2.0x zw | 160 | 98.3% | 1275.53 | 177 | 90.4% | 7.39 | 125 |
| 0.75x zw | 1.5x zw | 160 | 96.0% | 38.59 | 177 | 79.2% | 6.18 | 125 |
| 0.75x zw | 2.0x zw | 160 | 98.3% | 1731.55 | 177 | 79.2% | 5.20 | 125 |
| 1.0x zw | 1.5x zw | 160 | 96.0% | 48.33 | 177 | 76.8% | 6.23 | 125 |
| 1.0x zw | 2.0x zw | 160 | 98.3% | 2166.00 | 177 | 76.8% | 5.30 | 125 |
| 1.0x zw | 2.5x zw | 160 | 98.3% | 2166.00 | 177 | 81.6% | 7.80 | 125 |

### 4B) Breakeven Step-Up

#### FIXED Framework

**ALL (CT: 40/80/190, WT: 60/80/240)** (baseline PF = 5.86):

| BE trigger | BE fires | Stopped at BE | Hit target | Net PF | PF Δ |
|:---:|:---:|:---:|:---:|:---:|:---:|
| 10t | 297 | 294 | 3 | 0.13 | -5.73 |
| 20t | 297 | 279 | 18 | 0.75 | -5.11 |
| 30t | 294 | 232 | 62 | 2.34 | -3.52 |
| 40t | 294 | 184 | 110 | 4.20 | -1.66 |

CT only:

**CT (40/80/190)** (baseline PF = 13.84):

| BE trigger | BE fires | Stopped at BE | Hit target | Net PF | PF Δ |
|:---:|:---:|:---:|:---:|:---:|:---:|
| 10t | 177 | 177 | 0 | 0.18 | -13.66 |
| 20t | 177 | 172 | 5 | 1.06 | -12.78 |
| 30t | 177 | 150 | 27 | 7.13 | -6.72 |
| 40t | 177 | 124 | 53 | 17.35 | +3.50 |

WT only:

**WT (60/80/240)** (baseline PF = 6.82):

| BE trigger | BE fires | Stopped at BE | Hit target | Net PF | PF Δ |
|:---:|:---:|:---:|:---:|:---:|:---:|
| 10t | 123 | 120 | 3 | 0.23 | -6.59 |
| 20t | 123 | 110 | 13 | 1.32 | -5.50 |
| 30t | 123 | 88 | 35 | 3.54 | -3.28 |
| 40t | 123 | 66 | 57 | 6.82 | -0.00 |

#### ZONE-RELATIVE Framework

**ALL (0.5x/1.0x/1.5x)** (baseline PF = 28.05):

| BE trigger | BE fires | Stopped at BE | Hit target | Net PF | PF Δ |
|:---:|:---:|:---:|:---:|:---:|:---:|
| 0.1x zw | 299 | 280 | 13 | 2.47 | -25.58 |
| 0.2x zw | 297 | 239 | 45 | 10.36 | -17.69 |
| 0.25x zw | 291 | 216 | 60 | 12.18 | -15.87 |
| 0.5x zw | 274 | 115 | 139 | 27.45 | -0.60 |

CT only:

**CT (0.5x/1.0x/1.5x)** (baseline PF = 244.60):

| BE trigger | BE fires | Stopped at BE | Hit target | Net PF | PF Δ |
|:---:|:---:|:---:|:---:|:---:|:---:|
| 0.1x zw | 177 | 167 | 4 | 3.83 | -240.76 |
| 0.2x zw | 177 | 142 | 25 | 21.36 | -223.23 |
| 0.25x zw | 176 | 130 | 37 | 30.72 | -213.87 |
| 0.5x zw | 165 | 58 | 93 | 1352.97 | +1108.38 |

WT only:

**WT (0.5x/1.0x/1.5x)** (baseline PF = 9.25):

| BE trigger | BE fires | Stopped at BE | Hit target | Net PF | PF Δ |
|:---:|:---:|:---:|:---:|:---:|:---:|
| 0.1x zw | 122 | 113 | 9 | 1.62 | -7.63 |
| 0.2x zw | 120 | 97 | 20 | 5.38 | -3.87 |
| 0.25x zw | 115 | 86 | 23 | 5.64 | -3.61 |
| 0.5x zw | 109 | 57 | 46 | 8.41 | -0.84 |

### 4C) Trail After T1

#### FIXED Framework

**CT (T1=40t, Stop=190t)** (baseline PF=13.84):

| Trail type | T2/Trail fills | Mean PnL | Net PF | vs baseline |
|:---:|:---:|:---:|:---:|:---:|
| Fixed T2=80t (baseline) | 89% | 42.3 | 13.84 | — |
| Trail 20t from HW, cap 80t | 100% | 42.1 | inf | +inf |
| Trail 30t from HW, cap 80t | 100% | 41.3 | inf | +inf |
| Trail 40t from HW, cap 80t | 100% | 40.7 | inf | +inf |
| Trail 50t from HW, cap 80t | 100% | 40.0 | inf | +inf |
| Trail 30t, no cap | 100% | 45.7 | inf | +inf |

**WT (T1=60t, Stop=240t)** (baseline PF=6.82):

| Trail type | T2/Trail fills | Mean PnL | Net PF | vs baseline |
|:---:|:---:|:---:|:---:|:---:|
| Fixed T2=80t (baseline) | 90% | 47.7 | 6.82 | — |
| Trail 20t from HW, cap 80t | 100% | 46.9 | 6.80 | -0.02 |
| Trail 30t from HW, cap 80t | 100% | 46.3 | 6.72 | -0.10 |
| Trail 40t from HW, cap 80t | 100% | 45.6 | 6.64 | -0.18 |
| Trail 50t from HW, cap 80t | 100% | 44.7 | 6.52 | -0.29 |
| Trail 30t, no cap | 97% | 50.5 | 7.24 | +0.43 |

#### ZONE-RELATIVE Framework

**CT (T1=0.5x, Stop=1.5x)** (baseline PF=244.60):

| Trail type | T2/Trail fills | Mean PnL | Net PF | vs baseline |
|:---:|:---:|:---:|:---:|:---:|
| Fixed T2=1.0x zw (baseline) | 82% | 131.4 | 244.60 | — |
| Trail 0.10x zw, cap 1.0x | 100% | 118.2 | 1395.38 | +1150.78 |
| Trail 0.15x zw, cap 1.0x | 99% | 119.8 | 1414.67 | +1170.07 |
| Trail 0.20x zw, cap 1.0x | 99% | 118.6 | 1400.56 | +1155.96 |
| Trail 0.25x zw, cap 1.0x | 99% | 116.9 | 1380.10 | +1135.50 |
| Trail 0.15x zw, no cap | 99% | 125.4 | 1481.09 | +1236.50 |

**WT (T1=0.5x, Stop=1.5x)** (baseline PF=9.25):

| Trail type | T2/Trail fills | Mean PnL | Net PF | vs baseline |
|:---:|:---:|:---:|:---:|:---:|
| Fixed T2=1.0x zw (baseline) | 73% | 72.6 | 9.25 | — |
| Trail 0.10x zw, cap 1.0x | 100% | 69.5 | 9.47 | +0.22 |
| Trail 0.15x zw, cap 1.0x | 100% | 69.7 | 9.49 | +0.24 |
| Trail 0.20x zw, cap 1.0x | 100% | 68.2 | 9.31 | +0.06 |
| Trail 0.25x zw, cap 1.0x | 97% | 68.6 | 9.35 | +0.10 |
| Trail 0.15x zw, no cap | 100% | 72.9 | 9.87 | +0.62 |

