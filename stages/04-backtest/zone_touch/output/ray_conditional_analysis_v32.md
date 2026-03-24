# Ray Conditional Analysis on Qualifying Trades — Analysis B (v3.2)

Generated: 2026-03-24 16:18

```
======================================================================
RAY CONDITIONAL ANALYSIS — ANALYSIS B (v3.2)
======================================================================
  Date: 2026-03-24 16:16
  Frozen model: ['F10', 'F01', 'F05', 'F09', 'F21', 'F13', 'F04']
  Analysis A verdict: REDUNDANT (model stays frozen)
  Ray filters: 60m+ only, backing=40t, obstacle=100t

======================================================================
STEP 0: LOAD DATA
======================================================================
  Total P1 touches: 3278
  Ray elbow candidates: 3278 rows
  P1 bars: 138704

======================================================================
STEP 1a: IDENTIFY QUALIFYING TRADES
======================================================================
  Mode 1 (A-Eq >= 45.49999999999999): 127 qualifying touches
  Mode 2 (B-ZScore RTH, excl M1): 325 qualifying touches
  Combined: 452

======================================================================
STEP 1b: JOIN RAY CONTEXT
======================================================================
  M1 backing ray coverage: 69/127 (54.3%)
  M2 backing ray coverage: 201/325 (61.8%)

  Computing OBSTACLE ray features...
  M1 obstacle ray coverage: 89/127 (70.1%)
  M2 obstacle ray coverage: 263/325 (80.9%)
  M1 mean ray density (50t): 5.6
  M2 mean ray density (50t): 6.0

======================================================================
STEP 1c: SIMULATE TRADE OUTCOMES (P1)
======================================================================
  Mode 1 P1 trades: 107
    PF@4t=8.30, WR=96.3%
  Mode 2 P1 trades: 239
    PF@4t=4.53, WR=74.5%

======================================================================
STEP 1d: BACKING STREAK PARADOX DIAGNOSTIC
======================================================================
  Testing whether high backing streak = worse outcomes for qualifying trades
  (Analysis A found dPF = -1.8116 for R1 backing bounce streak)


  --- Mode 1 (A-Eq ModeA) (107 trades) ---
  Streak                   N     WR%    PF@4t   Mean PnL
  -------------------------------------------------------
  0 (just flipped)        26   96.2%     7.22      +46.4
  1-2                     10  100.0%      inf      +56.0
  3-5                     10   90.0%     2.60      +31.0
  6+                      11   90.9%     2.89      +33.3
  No backing ray          50   98.0%    24.28      +52.6
  Paradox: CONFIRMED (high streak PF < 70% of low streak PF)

  --- Mode 2 (B-ZScore RTH) (239 trades) ---
  Streak                   N     WR%    PF@4t   Mean PnL
  -------------------------------------------------------
  0 (just flipped)        56   78.6%     5.03      +84.6
  1-2                     39   74.4%     5.21     +145.7
  3-5                     20   70.0%     3.32      +61.6
  6+                      23   73.9%    10.04     +134.4
  No backing ray         101   73.3%     3.43      +59.4
  Paradox: NOT CONFIRMED (high streak outperforms)

  OVERALL PARADOX STATUS: MODE_DEPENDENT
  -> Paradox confirmed for one mode, not the other
  -> Apply backing streak signals only where relationship holds

  Saved: c:\Projects\pipeline\shared\archetypes\zone_touch\output\qualifying_trades_ray_context_v32.csv (346 trades)

======================================================================
STEP 2: SURFACE 2 — SKIP GATE ANALYSIS
======================================================================
  Focus: Mode 2 (239 trades)
  Mode 1 has 107 trades — too few losers for segment analysis
  Paradox status: MODE_DEPENDENT

  --- Mode 2 Segment Analysis ---
  Baseline: N=239, PF@4t=4.53, WR=74.5%

  Segment                                 N     WR%    PF@4t   vs Pop
  --------------------------------------------------------------------
  Strong obstacle (<=40t)               149   71.8%     3.81    -0.73
  Mid obstacle (40-80t)                  34   82.4%    10.62    +6.08
  Far obstacle (80-100t)                 10   90.0%    13.54    +9.00
  No obstacle ray                        46   73.9%     4.09    -0.44
  Strong backing (streak>=5)             28   67.9%     8.31    +3.77
  Moderate backing (streak 1-4)          54   75.9%     4.81    +0.27
  Weak backing (streak=0)                56   78.6%     5.03    +0.50
  No backing ray                        101   73.3%     3.43    -1.11
  Dense rays (>=5 within 50t)           116   72.4%     3.83    -0.70
  Sparse rays (<3 within 50t)            89   76.4%     5.86    +1.33
  Congested (streak>=3 + dense)          33   69.7%     4.04    -0.50

  No viable skip gate candidates found (no segment with PF < 50% baseline AND N >= 15)

  --- Mode 1 (reference only) Segment Analysis ---
  Baseline: N=107, PF@4t=8.30, WR=96.3%

  Segment                                 N     WR%    PF@4t   vs Pop
  --------------------------------------------------------------------
  Has obstacle (any)                     76   96.1%     7.02    -1.28
  No obstacle                            31   96.8%    14.87    +6.57
  Strong backing (streak>=5)             11   90.9%     2.89    -5.41
  Weak/No backing                        76   97.4%    13.50    +5.20

======================================================================
STEP 3: SURFACE 3 — ADAPTIVE EXIT ANALYSIS
======================================================================

--- 3a: Winner MFE vs Obstacle Ray (Mode 2) ---
  Mode 2 winners: 178, losers: 61
  Obstacle Context              N    Med MFE    Med PnL   Efficiency
  -------------------------------------------------------------------
  Obstacle <=30t               94      163.5      132.5       92.6%
  Obstacle 30-60t              34      112.0      101.5       91.9%
  Obstacle 60-100t             16      162.5      138.5       95.7%
  No obstacle                  34      148.0      123.0       88.2%

--- 3b: Loser Analysis vs Backing Ray (Mode 2, 61 losers) ---
  Backing Context               N    Med MAE    Med PnL   Pct of Losers
  ----------------------------------------------------------------------
  Streak 0                     12      155.5      -77.0           19.7%
  Streak 1-2                   10      169.5     -127.0           16.4%
  Streak 3-5                    6      183.5      -68.5            9.8%
  Streak 6+                     6       95.0      -32.0            9.8%
  No backing                   27      129.0      -70.0           44.3%

--- 3c/3d: Adaptive Exit Rule Testing (Mode 2) ---
  Baseline Mode 2: 239 trades, PF@4t=4.53

  Rule                                   PF@4t  Trades     WR%      dPF
  ----------------------------------------------------------------------
  Baseline (ZONEREL)                      4.53     239   74.5%      ---
  Obstacle ceiling                        5.17     283   93.6%    +0.63
  No-obstacle extension (+20%)            4.51     238   73.5%    -0.03
  Dense ray caution (TC 60%)              3.91     248   72.2%    -0.62

  Rules with positive dPF: 1
    Obstacle ceiling: dPF=+0.63

======================================================================
STEP 4: P2 VALIDATION
======================================================================
  Loading P2 data for validation...
  P2 bars: 131709
  P2 touches (after RotBarIndex filter): 3536
  P2 Mode 1 qualifying: 108
  P2 Mode 2 qualifying: 493
  Computing P2 ray features...
  P2 Mode 1 trades: 96
  P2 Mode 2 trades: 309
    M1 PF@4t: 6.26
    M2 PF@4t: 4.10
  P2 combined: 405 trades, PF@4t=4.30

  --- P2 Adaptive Exit Validation ---
  Rule                                 P1 PF@4t  P2 PF@4t  P2 Trades    Verdict
  ------------------------------------------------------------------------------
  Obstacle ceiling                         5.17      3.14        396 FAIL (overfit)

======================================================================
VERDICT
======================================================================

  VERDICT: ADAPTIVE EXIT CANDIDATE identified

  Paradox status: MODE_DEPENDENT
  Model: FROZEN at v3.2 (7 features)
  Elapsed: 135.3s
```

## Section 1: Qualifying Population

- Mode 1 (A-Eq ModeA): 127 touches, 107 trades
- Mode 2 (B-ZScore RTH): 325 touches, 239 trades
- Backing ray coverage: M1=69/127, M2=201/325
- Obstacle ray coverage: M1=89/127, M2=263/325
- **Paradox diagnostic: MODE_DEPENDENT**

## Section 2: Surface 2 (Skip Gate)

No viable skip gate found. No segment showed PF < 50% of baseline with N >= 15.


## Section 3: Surface 3 (Adaptive Exits)

**Rules that improved P1 PF:**

- Obstacle ceiling: PF@4t=5.17 (dPF=+0.63) on P1

**P2 validation: FAILED.** Obstacle ceiling degraded P2 PF from 4.10 to 3.14 (overfit).
No other rule improved P1. All adaptive exit candidates are rejected.

### Winner MFE Analysis (Mode 2)

Close obstacles (<=30t) did NOT cap MFE as hypothesized. Median MFE was 163.5t
for winners with close obstacles vs 148.0t for those without. The obstacle ceiling
rule's P1 improvement was an artifact of the re-simulation mechanics (tighter targets
increased trade count from 239 to 283 by shortening hold times), not genuine
obstacle-based signal.

### Loser Analysis (Mode 2)

44.3% of Mode 2 losers had no backing ray. Losers with high backing streak (6+)
had lower median MAE (95.0t) and milder losses (-32.0t) than losers with no backing
(129.0t MAE, -70.0t PnL). This is consistent with the Mode 2 paradox NOT CONFIRMED
result: strong backing IS protective for Mode 2 losers but the effect is too small
and the population too sparse to build a reliable skip gate.

## Section 4: Verdict

**NO VIABLE OVERLAY**

Ray context does not meaningfully improve qualifying trade outcomes on P2 validation:

- **Surface 2 (Skip Gate):** No segment showed PF < 50% of baseline with N >= 15.
  The strongest segment effect was "No backing ray" (PF 3.43 vs 4.53 baseline, 24%
  reduction) — insufficient for a reliable skip gate.
- **Surface 3 (Adaptive Exits):** The only P1-improving rule (obstacle ceiling,
  dPF=+0.63) FAILED P2 validation (PF 4.10 -> 3.14). Overfit to P1 patterns.

The 7-feature scoring model captures sufficient information. Ray value is redirected
to **Surface 4** (ray-only archetype, separate pipeline — queued post-paper-trading).

### Backing Streak Paradox

- Mode 1: **CONFIRMED** — high backing streak = worse outcomes (PF drops from 7.22
  at streak=0 to 2.89 at streak=6+). Mechanism: congested, heavily structured areas
  where the A-Eq filter has already selected the best trades.
- Mode 2: **NOT CONFIRMED** — high backing streak = better outcomes (PF=10.04 at
  streak=6+ vs 5.03 at streak=0). Strong backing IS protective for Mode 2 trades.
- Overall: **MODE_DEPENDENT**. Not actionable as a universal overlay.

- Model: **FROZEN** at v3.2
- Paradox: **MODE_DEPENDENT**
