# Throughput Optimization Analysis — Part 1 of 2

Generated: 2026-03-23 13:05
P1 bars: 138,704 | P1 qualifying signals: 178
P2 bars: 131,709 | P2 qualifying signals: 147

======================================================================
## SECTION 1: SIGNAL ARRIVAL PATTERNS
======================================================================

### A) Signal Arrival Rate (P1)

- Mean bars between signals: **773.6**
- Median bars between signals: **194**
- P10: **22** bars | P90: **2721** bars

| Hour (ET) | Qualifying signals | Trades (ZR) | Blocked (IN_POSITION) |
|-----------|-------------------|-------------|----------------------|
| 06-08 | 4 | 3 | 0 |
| 08-10 | 13 | 11 | 1 |
| 10-12 | 24 | 17 | 7 |
| 12-14 | 28 | 20 | 7 |
| 14-16 | 68 | 39 | 25 |
| 16-18 | 21 | 14 | 4 |

### B) Cluster Detection (P1)

| Cluster size | Occurrences | Signals in clusters | % of all signals |
|-------------|-------------|--------------------|-----------------| 
| 2 signals within 20 bars | 8 | 16 | 9.0% |
| 3+ signals within 20 bars | 2 | 6 | 3.4% |

### C) Blocked Signal Hour Concentration

| Hour (ET) | Blocked (IN_POSITION) | % of all blocked |
|-----------|----------------------|-----------------|
| 06-08 | 0 | 0.0% |
| 08-10 | 2 | 4.4% |
| 10-12 | 9 | 20.0% |
| 12-14 | 7 | 15.6% |
| 14-16 | 25 | 55.6% |
| 16-18 | 4 | 8.9% |

### D) Blocking by Zone Type

| Block type | Count | Mean score | Addressable? |
|-----------|-------|-----------|-------------|
| Same zone as current trade | 34 | 17.57 | NO |
| Different zone, same TF | 8 | 17.28 | YES |
| Different zone, different TF | 6 | 17.63 | YES |

**Addressable fraction: 14/48 = 29.2%**

### P2 Cross-Validation: Signal Arrival

- P2 mean gap: 734.7 bars | P2 median gap: 61
- P1 mean gap: 773.6 bars | P1 median gap: 194
- Density similar: YES

P2 clusters: 2-signal=18 (24.5%), 3+=4 (8.8%)

======================================================================
## SECTION 2: TIME-TO-PROFIT CURVES (MFE)
======================================================================

### MFE by Zone Width (absolute ticks)

| Zone width | N | MFE@10 | MFE@20 | MFE@30 | MFE@50 | MFE@100 | Final MFE |
|---|---|---|---|---|---|---|---|
| 50-100t | 34 | 62.1 | 85.4 | 96.4 | 111.3 | 163.5 | 70.4 |
| 100-150t | 20 | 59.0 | 93.5 | 101.0 | 164.4 | 222.5 | 111.8 |
| 150-200t | 14 | 75.6 | 90.3 | 103.4 | 153.9 | 268.6 | 160.9 |
| 200-300t | 20 | 73.9 | 113.2 | 154.3 | 192.1 | 298.3 | 245.8 |
| 300t+ | 15 | 56.7 | 74.8 | 100.0 | 165.9 | 264.9 | 342.7 |

### MFE as Fraction of Zone Width

| Zone width | N | MFE/ZW @10 | MFE/ZW @20 | MFE/ZW @30 | MFE/ZW @50 |
|---|---|---|---|---|---|
| 50-100t | 34 | 0.997 | 1.320 | 1.482 | 1.703 |
| 100-150t | 20 | 0.491 | 0.766 | 0.830 | 1.341 |
| 150-200t | 14 | 0.443 | 0.526 | 0.601 | 0.899 |
| 200-300t | 20 | 0.299 | 0.464 | 0.639 | 0.806 |
| 300t+ | 15 | 0.136 | 0.174 | 0.232 | 0.344 |

### MFE/ZW Plateau Analysis

- P1: MFE/ZW reaches 80% at bar **10**
- P2: MFE/ZW reaches 80% at bar **29**

### MFE/ZW by Mode (CT vs WT)

| Mode | N | MFE/ZW @10 | MFE/ZW @20 | MFE/ZW @30 | MFE/ZW @50 |
|------|---|-----------|-----------|-----------|-----------|
| CT | 33 | 0.528 | 0.823 | 0.974 | 1.355 |
| WT | 87 | 0.951 | 1.322 | 1.551 | 1.985 |

======================================================================
## SECTION 3: EARLY EXIT SIMULATIONS
======================================================================

### Early Exit — Original Trades

| Exit config | Trades | Mean PnL | Total PnL | WR | Freed signals | KS triggers |
|------------|--------|---------|-----------|-----|--------------|-------------|
| 10 bars | 161 | 32.1 | 5168.0 | 66.5% | 41 | 0 |
| 15 bars | 156 | 37.0 | 5770.0 | 64.1% | 37 | 2 |
| 20 bars | 155 | 44.3 | 6864.0 | 68.4% | 36 | 2 |
| 30 bars | 140 | 54.9 | 7681.0 | 72.1% | 23 | 1 |
| 50 bars | 132 | 69.9 | 9224.0 | 71.2% | 19 | 1 |
| 75 bars | 118 | 80.4 | 9492.0 | 71.2% | 9 | 1 |
| Current ZR | 120 | 73.4 | 8802.7 | 88.3% | 0 | 0 |
| Fixed exits | 130 | 51.8 | 6735.5 | 96.2% | 15 | 0 |

### Combined Result (Original + Freed PnL)

| Exit config | Original PnL | Freed PnL | TOTAL PnL | vs current | KS triggers |
|------------|-------------|-----------|-----------|------------|-------------|
| 10 bars | 3251.0 | 1917.0 | 5168.0 | -3634.7 | 0 |
| 15 bars | 3483.0 | 2287.0 | 5770.0 | -3032.7 | 2 |
| 20 bars | 4079.0 | 2785.0 | 6864.0 | -1938.7 | 2 |
| 30 bars | 5282.0 | 2399.0 | 7681.0 | -1121.7 | 1 |
| 50 bars | 7446.0 | 1778.0 | 9224.0 | +421.3 | 1 |
| 75 bars | 9120.0 | 372.0 | 9492.0 | +689.3 | 1 |
| Current ZR | 8802.7 | 0 | 8802.7 | baseline | 0 |
| Fixed exits + freed | 5867.7 | 867.8 | 6735.5 | -2067.2 | 0 |

### P2 Cross-Validation (Best P1 Forced Exit)

| Period | Best exit bar | Total PnL | vs current | Consistent? |
|--------|-------------|-----------|------------|-------------|
| P1 | 75 | 9492.0 | baseline | — |
| P2 | 75 | 10441.0 | +2877.1 | YES |

======================================================================
## SECTION 4: SINGLE-LEG T1 THROUGHPUT
======================================================================

### A) Single-Leg Baseline

| Strategy | Trades | Mean hold | Mean PnL | Total PnL | Blocked | KS triggers |
|----------|--------|----------|---------|-----------|---------|-------------|
| 2-leg ZR (current) | 120 | 66.5 | 73.4 | 8802.7 | 48 | 0 |
| 2-leg Fixed | 130 | 39.6 | 51.8 | 6735.5 | 38 | 0 |
| ZR single-leg T1 | 127 | 36.0 | 63.9 | 8119.0 | 41 | 0 |
| Fixed single-leg T1 | 138 | 26.9 | 46.8 | 6455.0 | 30 | 0 |

### B) T2 Runner Marginal Value (ZR exits)

**ZR exits (T2 = 1.0x zone_width):**

| Metric | All | ZW < 150t | 150-250t | 250t+ |
|---|---|---|---|---|
| Trades where T1 filled | 107 | 66 | 24 | 17 |
| Mean bars T1->T2 exit | 34.8 | 23.8 | 47.0 | 60.0 |
| Mean T2 marginal PnL | 37.5 | 20.1 | 36.6 | 106.1 |
| Signals blocked after T1 | 8 | 5 | 2 | 1 |
| Blocked signal hyp value | 603.2 | 155.4 | 224.1 | 223.8 |

**Fixed exits (T2 = 80t):**

| Metric | All | ZW < 150t | 150-250t | 250t+ |
|---|---|---|---|---|
| Trades where T1 filled | 126 | 72 | 27 | 27 |
| Mean bars T1->T2 exit | 14.1 | 18.2 | 11.6 | 5.7 |
| Mean T2 marginal PnL | 23.2 | 20.7 | 26.4 | 26.4 |
| Signals blocked after T1 | 11 | 5 | 5 | 1 |
| Blocked signal hyp value | 441.9 | 60.3 | 318.0 | 63.6 |

### P2 Cross-Validation (Single-Leg T1)

| Period | Config | 2-leg Total PnL | T1-only Total PnL | Winner |
|--------|--------|----------------|-------------------|--------|
| P1 | ZR | 8802.7 | 8119.0 | 2-leg |
| P1 | Fixed | 6735.5 | 6455.0 | 2-leg |
| P2 | ZR | 7563.9 | 7654.0 | T1-only |
| P2 | Fixed | 4215.9 | 4252.0 | T1-only |

======================================================================
## SECTION 5: SPEED-AT-ENTRY AS PREDICTOR
======================================================================

### A) Features Correlated with Speed

| Feature | Fast MFE (T1 in <15 bars) | Slow MFE (T1 in >30 bars) |
|---------|--------------------------|--------------------------|
| Mean zone width | 104.1 | 243.1 |
| Mean score margin | 1.21 | 1.53 |
| % CT | 30.9% | 31.4% |
| % RTH | 60.0% | 82.9% |

### B) Zone-Width-Controlled Speed Check (150-250t only)

Fast trades (150-250t): 8 | Slow trades (150-250t): 9

| Feature (150-250t only) | Fast T1 (<15 bars) | Slow T1 (>30 bars) |
|------------------------|-------------------|-------------------|
| Mean score margin | 1.55 | 1.06 |
| % CT | 25.0% | 55.6% |
| % RTH | 25.0% | 88.9% |


======================================================================
## SECTION 6: STOP TIGHTENING FOR THROUGHPUT
======================================================================

### A) Full-Position Stop Tightening

| Stop | Trades stopped | Trades | Freed (seq sim) | Net PnL | KS triggers |
|------|---------------|--------|----------------|---------|-------------|
| max(1.5x, 120) ZR current | 4 | 120 | 0 | 8802.7 | 0 |
| max(1.0x, 100) | 7 | 121 | 2 | 8527.8 | 0 |
| max(0.75x, 80) | 15 | 126 | 8 | 7876.1 | 0 |
| Fixed 120t for all | 21 | 130 | 12 | 6452.4 | 1 |
| Fixed 80t for all | 32 | 129 | 11 | 4135.1 | 1 |
| Fixed exits (CT 190t, WT 240t) | 2 | 130 | 15 | 6735.5 | 0 |

### B) T2-Leg Stop Tightening (after T1 fills)

| T2 stop (after T1 fills) | Trades | Freed (seq sim) | Net PnL | KS triggers |
|-------------------------|--------|----------------|---------|-------------|
| Original stop (current) | 120 | 0 | 8802.7 | 0 |
| max(1.0x, 100) after T1 | 120 | 0 | 8680.0 | 0 |
| Entry (breakeven T2) | 124 | 4 | 8407.4 | 0 |
| T1 price (lock profit) | 127 | 7 | 8463.2 | 0 |

Context: 107 of 120 ZR trades had T1 fill.
- Mean bars T1->T2 exit: 34.8
- Total T2 marginal PnL: 4010.2t
- T2 stopped after T1: 4 (loss: -309.2t)

### C) Full-Position BE Step-Up (Zone-Relative)

| BE trigger | Trades | Stopped at BE | Net PnL | Freed signals | KS triggers |
|-----------|--------|--------------|---------|--------------|-------------|
| No BE (current) | 120 | 0 | 8802.7 | 0 | 0 |
| MFE > 0.25x zw | 130 | 82 | 4792.3 | 21 | 9 |
| MFE > 0.33x zw | 128 | 57 | 6185.3 | 17 | 6 |
| MFE > 0.5x zw (=T1) | 124 | 15 | 7980.1 | 4 | 0 |

### BE Split by Zone Width (trigger = 0.25x zw)

| Zone width | Trades | BE stops | Net PnL change vs no-BE | Freed |
|-----------|--------|---------|------------------------|-------|
| ZW < 150t | 78 | 59 | -1890.8 | 13 |
| 150-250t | 28 | 15 | -1189.3 | 3 |
| 250t+ | 24 | 8 | -930.3 | 5 |

### D) Risk Profile by Stop Level

| Stop config | Max single loss | Worst 2-trade daily | % daily budget (-600t) | Max DD | P95 MAE | HIGH EXPOSURE? |
|------------|----------------|--------------------|-----------------------|--------|---------|---------------|
| max(1.5x, 120) ZR current | 156.0t | 137.0t | 26.0% | 179.0t | 263.0t | NO |
| max(1.0x, 100) | 141.0t | 119.1t | 23.5% | 222.1t | 210.0t | NO |
| max(0.75x, 80) | 251.0t | 215.0t | 41.8% | 286.3t | 189.0t | NO |
| Fixed 120t for all | 123.0t | 246.0t | 20.5% | 526.7t | 144.0t | NO |
| Fixed 80t for all | 83.0t | 166.0t | 13.8% | 283.4t | 101.0t | NO |
| Fixed exits (CT 190t, WT 240t) | 243.0t | 0.0t | 40.5% | 243.0t | 171.0t | NO |

### P2 Cross-Validation (Tighter Stop)

| Period | Current stop PnL | Tighter stop (max(1.0x, 100)) PnL | Winner |
|--------|-----------------|--------------------------------------|--------|
| P1 | 8802.7 | 8527.8 | current |
| P2 | 7563.9 | 7064.7 | current |

======================================================================
## SECTION 7: OPTIMAL THROUGHPUT CONFIGURATION
======================================================================

| Config | Trades | Mean PnL | Total PnL | Mean hold | Max DD | Max loss | KS |
|--------|--------|---------|-----------|----------|--------|---------|-----|
| Current ZR 2-leg | 120 | 73.4 | 8802.7 | 66.5 | 179.0 | 156.0 | 0 |
| Fixed exits (CT 40/80/190, WT 60/80/240) | 130 | 51.8 | 6735.5 | 39.6 | 243.0 | 243.0 | 0 |
| Best fixed bar exit (75b) | 118 | 80.4 | 9492.0 | 75.0 | 860.0 | 860.0 | 1 |
| ZR single-leg T1 | 127 | 63.9 | 8119.0 | 36.0 | 179.0 | 156.0 | 0 |
| Fixed single-leg T1 | 138 | 46.8 | 6455.0 | 26.9 | 243.0 | 243.0 | 0 |
| Best tighter stop (max(1.0x, 100)) | 121 | 70.5 | 8527.8 | 62.9 | 222.1 | 141.0 | 0 |
| Best BE (MFE > 0.5x zw (=T1)) | 124 | 64.4 | 7980.1 | 50.2 | 185.0 | 156.0 | 0 |
| Best T2-only tighten (max(1.0x, 100) after T1) | 120 | 72.3 | 8680.0 | 64.5 | 179.0 | 156.0 | 0 |

### P2 Cross-Validation Summary

| Config | P1 Total PnL | P2 Total PnL | P1 KS | P2 KS | Classification |
|--------|-------------|-------------|-------|-------|---------------|
| Current ZR 2-leg | 8802.7 | 7563.9 | 0 | 0 | baseline |
| Fixed exits (CT 40/80/190, WT 60/80/240) | 6735.5 | 4215.9 | 0 | 0 | NOT VIABLE |
| Best fixed bar exit (75b) | 9492.0 | 10441.0 | 1 | 0 | HIGH EXPOSURE (beats both) |
| ZR single-leg T1 | 8119.0 | 7654.0 | 0 | 0 | NOT VIABLE |
| Fixed single-leg T1 | 6455.0 | 4252.0 | 0 | 0 | NOT VIABLE |
| Best tighter stop (max(1.0x, 100)) | 8527.8 | 7064.7 | 0 | 0 | NOT VIABLE |
| Best BE (MFE > 0.5x zw (=T1)) | 7980.1 | 7374.5 | 0 | 0 | NOT VIABLE |
| Best T2-only tighten (max(1.0x, 100) after T1) | 8680.0 | 7468.9 | 0 | 0 | NOT VIABLE |

> **OVERFITTED CEILING**: The best combined config cherry-picks from each section on P1.
> This is the upper bound, not a deployable config.

> **REMINDER**: Do NOT freeze any new exit config from this prompt.
> Throughput Part 2 (dynamic T2 exit) may alter the optimal config.
> Section 7 identifies candidates only.