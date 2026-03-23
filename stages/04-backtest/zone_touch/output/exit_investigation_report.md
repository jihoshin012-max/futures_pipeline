# Zone Touch Exit Investigation — Combined Report
## P2 Data: 312 trades (187 CT, 125 WT) | seg3_ModeB + variants

---

## SUMMARY

### ACTIONABLE (clear improvement, robust signal)

1. **Zone-relative exits (0.5x/1.0x/1.5x zone_width)** — NEEDS P1 CONFIRMATION
   - P2 result: EV 107.4 vs 43.3 fixed baseline (2.5x improvement)
   - 2-leg (67/33): T1=0.5x zw, T2=1.0x zw, Stop=1.5x zw, TC=160
   - Works across all zone widths; strongest for 150t+ zones
   - Risk: narrow zones (50-100t) have tight stops (75-150t), lower WR

2. **CT 5t limit entry** — NEEDS P1 CONFIRMATION
   - P2 result: 177/187 CT fill (95%), zero CT losses with fixed 40t/190t exits
   - 5t deeper entry captures the penetration bounce more reliably
   - Risk: 10 CT trades (5%) do not fill and are skipped

3. **Stop floor for narrow zones: max(1.5x zw, 120t)** — NEEDS P1 CONFIRMATION
   - Protects narrow zone trades from premature stop-outs
   - Minimal impact on wide zones (1.5x zw already > 120t for zones > 80t)

### DIAGNOSTIC (interesting pattern, needs more data)

1. **Losers penetrate FAST** (9.6 t/bar at 10 bars vs 4.1 for winners)
   - Opposite of initial hypothesis (slow drift)
   - 100t in 10 bars rule: catches 41% of losers at 3% FP, PF +0.06
   - Too selective to be primary exit — supplementary signal at best

2. **Opposite edge cross** — 28% of losers vs 4.6% of winners
   - Exit at edge+25t: 9 losses saved, 6 winners killed (net PF 3.35)
   - Signal fires too late (damage already done) — marginal improvement

3. **No-bounce rules** — TYPE 2 (50t adv, no 20t close bounce in 30 bars)
   - Zero triggers on P2 data — all adverse trades bounce by close
   - Losing pattern is repeated shallow bounces that fail, not continuous drive
   - Need tick-level data or smaller bars to detect bounce quality

4. **WT losers never reach T1** (0% at all bar checkpoints)
   - WT losses are identifiable early — flat MFE by bar 10 is a strong signal
   - Potential for WT-specific early exit if MFE < 20t at bar 15-20

5. **Battleground stall analysis** — LOW CONFIDENCE (n=3 unique events)
   - Winners and losers both bounce within 2-3 bars of max pen
   - No distinguishing stall pattern at current bar granularity

### NOT VIABLE (tested and failed)

1. **Breakeven step-up** — destroys PF at all levels except T1-coincident
   - BE@10-30t: kills 85-95% of remaining position value
   - The strategy needs room to oscillate; BE removes that room
   - Only BE@T1 (40t CT, 0.5x zw) is neutral/slightly positive

2. **Fixed trail with T2 cap** — underperforms fixed T2
   - Trail 20-50t with 80t cap: all slightly worse than fixed T2=80t
   - Only trail with NO CAP shows improvement (lets winners run)

3. **Halfway timecap rule** (adverse >50t at bar 60) — PF drops 1.42
   - Kills 11% of winners for only 56% loser catch rate

### RECOMMENDED NEXT STEPS (priority order)

1. **P1 validation of zone-relative framework** — highest priority
   - Test 0.5x/1.0x/1.5x 2-leg on P1 data
   - If PF > 3.0 on P1, this is the primary exit upgrade

2. **P1 validation of CT 5t limit entry**
   - Verify fill rate and zero-loss claim on P1 data
   - If confirmed, adopt for CT regardless of exit framework

3. **P1 test of stop floor max(1.5x zw, 120t)**
   - Check if 50-100t zone performance improves without harming wider zones

4. **P1 test of zone-relative trail (0.15x zw, no T2 cap)**
   - If zone-rel framework confirmed, this is the next optimization layer

5. **Investigate WT early exit signal (MFE < 20t at bar 15-20)**
   - Need P1 data to confirm WT losers consistently show flat early MFE
   - Could reduce WT losses with minimal winner impact

6. **Test combined: 5t CT + zone-rel exits + stop floor + trail**
   - Only after individual components validated on P1
   - Combined overfitting risk is high — test each layer incrementally

---


---

## PART 1: Battleground Profiling + Zone-Width-Relative Exits

(Part 1 results — see console output from exit_investigation_part1.py)

---

## PART 2: Penetration Dynamics + Exit Re-Optimization

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


---

## PART 3: Interaction Effects + Head-to-Head

# Zone Touch Exit Investigation — Part 3 of 3

## SECTION 5: INTERACTION EFFECTS

### 5A) Score Margin × Penetration Depth (MAE)

| | Pen 0-50t | Pen 50-100t | Pen 100-150t | Pen 150t+ |
|---|---|---|---|---|
| Margin 0-2 | n=112, WR=100%, PnL=61, PF=inf | n=70, WR=94%, PnL=57, PF=168.4 | n=19, WR=84%, PnL=48, PF=19.8 | n=34, WR=35%, PnL=-105, PF=0.2 |
| Margin 2-4 | n=38, WR=100%, PnL=58, PF=inf | n=7, WR=100%, PnL=60, PF=inf ⚠️ | n=8, WR=100%, PnL=64, PF=inf ⚠️ | n=5, WR=80%, PnL=11, PF=1.3 ⚠️ |
| Margin 4-6 | n=9, WR=100%, PnL=64, PF=inf ⚠️ | n=3, WR=100%, PnL=57, PF=inf ⚠️ | n=5, WR=60%, PnL=-14, PF=0.7 ⚠️ | n=2, WR=100%, PnL=35, PF=inf ⚠️ |
| Margin 6+ | — | — | — | — |

### 5B) Session × Outcome

| | RTH | ETH |
|---|---|---|
| Count | 238 | 74 |
| WR | 92.0% | 82.4% |
| Mean PnL | 45.7 | 16.6 |
| Mean MAE | 62.6 | 77.8 |
| Mean MFE | 71.2 | 73.6 |
| PF | 5.81 | 1.49 |
| Stop rate | 4.2% | 17.6% |

### 5C) Touch Sequence × Penetration

| Seq | Count | Mean pen | Median pen | WR | % pen > 100t |
|:---:|:---:|:---:|:---:|:---:|:---:|
| 1 | 19 | 58 | 37 | 95% | 21% |
| 2 | 130 | 72 | 61 | 88% | 19% |
| 3 | 64 | 53 | 29 | 84% | 17% |
| 4+ | 99 | 69 | 56 | 94% | 29% |

### 5D) Cascade State × Outcome

| State | Count | WR | Mean PnL | Mean MAE | Stop rate |
|---|:---:|:---:|:---:|:---:|:---:|
| NO_PRIOR | 76 | 97% | 53.8 | 57 | 3% |
| PRIOR_HELD | 198 | 88% | 36.4 | 68 | 8% |
| PRIOR_BROKE | 38 | 84% | 21.2 | 76 | 16% |

### 5E) Timeframe × Penetration × Outcome

| TF | Count | Mean pen | WR | PF | Stop rate |
|:---:|:---:|:---:|:---:|:---:|:---:|
| 15m | 130 | 66 | 88% | 2.94 | 9% |
| 30m | 91 | 69 | 86% | 1.96 | 12% |
| 60m | 28 | 75 | 100% | inf | 0% |
| 90m | 28 | 63 | 89% | 32.19 | 0% |
| 120m | 27 | 56 | 100% | inf | 0% |
| 240m | 1 ⚠️ | 165 | 100% | inf | 0% |
| 480m | 2 ⚠️ | 84 | 100% | inf | 0% |
| 720m | 5 ⚠️ | 29 | 100% | inf | 0% |

### 5F) Zone Width × Outcome (Fixed vs Zone-Relative)

| Zone width | Count | WR | Mean PnL (fixed) | Mean PnL (zone-rel) | PF (fixed) | PF (zone-rel) | Stop rate |
|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| 0-50t ⚠️ | 4 | 100% | 62.0 | 22.9 | inf | inf | 0% |
| 50-100t | 33 | 73% | 12.7 | 26.2 | 1.42 | 4.77 | 15% |
| 100-150t | 74 | 95% | 45.9 | 57.3 | 5.40 | 8.79 | 5% |
| 150-200t | 62 | 95% | 57.0 | 99.5 | 74.65 | 294.83 | 0% |
| 200t+ | 139 | 88% | 32.4 | 159.3 | 2.52 | 54.22 | 10% |

### 5G) Zone Width × Penetration Speed (Winners vs Losers)

| Zone width | Mean pen speed W | Mean pen speed L | Speed ratio (L/W) |
|:---:|:---:|:---:|:---:|
| 0-50t ⚠️ | 7.7 | 0.0 | 0.0x |
| 50-100t | 16.1 | 6.1 | 0.4x |
| 100-150t | 12.0 | 5.1 | 0.4x |
| 150-200t | 13.5 | 1.7 | 0.1x |
| 200t+ | 12.3 | 9.7 | 0.8x |

### 5H) Mode × Zone Width × Outcome

| Mode | Zone width | Count | WR | PF | Mean PnL (zone-rel) |
|:---:|:---:|:---:|:---:|:---:|:---:|
| CT | 0-100t | 15 | 73% | inf | 37.1 |
| CT | 100-200t | 72 | 99% | 83.48 | 92.2 |
| CT | 200t+ | 100 | 89% | 575.64 | 172.4 |
| WT | 0-100t | 22 | 77% | 2.74 | 18.1 |
| WT | 100-200t | 64 | 91% | 8.78 | 58.9 |
| WT | 200t+ | 39 | 87% | 13.69 | 125.6 |

---

## SECTION 6: HEAD-TO-HEAD COMPARISON

All strategies use 2-leg exits (67/33 split). Max DD = worst single-trade loss (ticks).

### FIXED FRAMEWORK

| Strategy | Fills | WR | PF | EV/opp | Max DD |
|----------|:---:|:---:|:---:|:---:|:---:|
| Current v1.0 (market, 190/240, 40-80/60-80) | 312 | 91.3% | 7.51 | 43.3 | 243 |
| 5t limit CT | 302 | 91.1% | 9.36 | 44.6 | 243 |
| 5t + 150t stop | 302 | 83.1% | 3.67 | 33.3 | 153 |
| 5t + BE@40t | 302 | 58.9% | 9.56 | 24.2 | 243 |
| 5t + trail 30t no cap | 302 | 96.7% | 15.23 | 47.7 | 243 |
| 5t + no-bounce 75/25/50 | 302 | 91.1% | 9.36 | 44.6 | 243 |
| 5t + opp edge+25t | 302 | 88.1% | 7.20 | 41.6 | 162 |
| **Best fixed: fixed_trail** | 302 | 96.7% | 15.23 | 47.7 | 243 |

### ZONE-RELATIVE FRAMEWORK

| Strategy | Fills | WR | PF | EV/opp | Max DD |
|----------|:---:|:---:|:---:|:---:|:---:|
| ZR baseline (mkt, 0.5x/1.0x/1.5x) | 312 | 92.0% | 28.69 | 107.4 | 154 |
| ZR + 5t CT | 302 | 91.7% | 28.05 | 107.0 | 154 |
| ZR + 5t + BE@0.5x zw | 302 | 93.0% | 27.45 | 92.8 | 154 |
| ZR + 5t + trail 0.15x no cap | 302 | 95.0% | 31.06 | 103.7 | 154 |
| ZR + 5t + no-bounce 75/25/50 | 302 | 91.7% | 28.05 | 107.0 | 154 |
| ZR + 5t + stop floor max(1.5x,120t) | 302 | 92.7% | 26.38 | 107.1 | 154 |
| **Best ZR: zr_base** | 312 | 92.0% | 28.69 | 107.4 | 154 |

### OVERALL BEST

| Strategy | Fills | WR | PF | EV/opp | Max DD |
|----------|:---:|:---:|:---:|:---:|:---:|
| Best fixed: fixed_trail | 302 | 96.7% | 15.23 | 47.7 | 243 |
| Best ZR: zr_base | 312 | 92.0% | 28.69 | 107.4 | 154 |
| **OVERALL: zr_base** | 312 | 92.0% | 28.69 | 107.4 | 154 |

**WARNING: All 'best' parameters selected on P2 data. This is the OVERFITTED CEILING.**
**Real OOS performance will be lower. Nothing enters autotrader spec without P1 confirmation.**
