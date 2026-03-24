# Ray Incremental Elbow Test — Analysis A (v3.2)

Generated: 2026-03-24 15:43

```
======================================================================
RAY INCREMENTAL ELBOW TEST — ANALYSIS A (v3.2)
======================================================================
  Date: 2026-03-24 15:42
  Frozen model: ['F10', 'F01', 'F05', 'F09', 'F21', 'F13', 'F04']
  Ray filters: 60m+ only, 40t proximity, BACKING only

  P1 touches loaded: 3278
  P1 bars: 138704
  P1 raw touches (excl VP_RAY): 3278
  HTF ray-touch pairs: 213898
  Ray reference events: 1716
  250vol bars: 138704
  Building 15m bars from 10-sec data...
  15m bars: 5470

  Extracting HTF rays...
  Detecting interactions...
  73638 valid interactions from 750 HTF rays
  Building lifecycle lookup...
  Computing ray features per touch (BACKING + OBSTACLE)...

--- Joining ray features to precomputed P1 features ---
  Backing ray coverage: 2033/3278 (62.0%)

--- Ray Feature Coverage Report ---
  Feature                          Non-NULL   Coverage
  ----------------------------------------------------
  backing_bounce_streak                2033      62.0%
  backing_flip_count                   2033      62.0%
  backing_dwell_bars                   2033      62.0%
  backing_decay_mag                    1389      42.4%
  backing_approach_vel                 2023      61.7%
  backing_dist_ticks                   2201      67.1%
  backing_cross_tf                     2201      67.1%
  backing_session                      2023      61.7%
  backing_close_type                   2033      62.0%

  Saved: ray_elbow_candidates_v32.csv (3278 rows)

======================================================================
PRECOMPUTE SIMULATION DATA
======================================================================
  Sim precomputed for 3278 touches
  Mean PnL @3t: 16.24 ticks

======================================================================
REPRODUCE 7-FEATURE BASELINE
======================================================================
  0-feature baseline: PF@3t=1.3045, trades=1433
  7-feature model: PF@3t=5.3671, trades=102, thr=50.0
  Reference (from incremental build): PF@3t=5.3671, trades=102, thr=50.0
  ✓ PF matches within tolerance (delta=0.0000)

======================================================================
STEP 2: SOLO SCREENING OF RAY CANDIDATES
======================================================================

  R1: Backing Bounce Streak (backing_bounce_streak)
    Valid values: 2033/3278 (62.0%)
    Bins (edges=0.00/2.00):
        Low: R/P@60=1.172, pts=0, n=915
        Mid: R/P@60=1.421, pts=10, n=515
       High: R/P@60=1.211, pts=5, n=603
         NA: R/P@60=1.287, pts=5, n=1245
    R/P spread: 0.249 → MODERATE
    Correlations with existing features:
      F10: r=-0.048
      F21: r=-0.034
      F13: r=+0.003
      F09: r=-0.001

  R2: Backing Flip Count (backing_flip_count)
    Valid values: 2033/3278 (62.0%)
    Bins (edges=2.00/29.00):
        Low: R/P@60=1.109, pts=0, n=687
        Mid: R/P@60=1.465, pts=10, n=681
       High: R/P@60=1.189, pts=5, n=665
         NA: R/P@60=1.287, pts=5, n=1245
    R/P spread: 0.356 → MODERATE
    Correlations with existing features:
      F10: r=+0.230
      F09: r=-0.075
      F21: r=+0.024
      F13: r=+0.011

  R3: Backing Ray Distance (backing_dist_ticks)
    Valid values: 2201/3278 (67.1%)
    Bins (edges=2.00/7.00):
        Low: R/P@60=1.175, pts=0, n=840
        Mid: R/P@60=1.322, pts=5, n=629
       High: R/P@60=1.216, pts=5, n=732
         NA: R/P@60=1.329, pts=10, n=1077
    R/P spread: 0.154 → WEAK
    Correlations with existing features:
      F21: r=-0.136
      F10: r=+0.068
      F09: r=-0.046
      F13: r=-0.015

  R4: Backing Ray Decay (backing_decay_mag)
    Valid values: 1389/3278 (42.4%)
    Bins (edges=1.16/2.24):
        Low: R/P@60=1.207, pts=0, n=464
        Mid: R/P@60=1.396, pts=10, n=462
       High: R/P@60=1.311, pts=5, n=463
         NA: R/P@60=1.227, pts=5, n=1889
    R/P spread: 0.189 → WEAK
    Correlations with existing features:
      F21: r=+0.257
      F10: r=-0.108
      F09: r=+0.051
      F13: r=-0.001

  R5: Backing Ray Age (backing_dwell_bars)
    Valid values: 2033/3278 (62.0%)
    Bins (edges=0.00/0.00):
        Low: R/P@60=1.236, pts=0, n=2009
       High: R/P@60=3.088, pts=10, n=24
         NA: R/P@60=1.287, pts=5, n=1245
    R/P spread: 1.852 → STRONG
    Correlations with existing features:
      F21: r=+0.053
      F10: r=-0.023
      F13: r=+0.012
      F09: r=-0.004

  R6: Backing Cross-TF (backing_cross_tf)
    Valid values: 2201/3278 (67.1%)
    Bins (edges=1.00/2.00):
        Low: R/P@60=1.235, pts=5, n=1139
        Mid: R/P@60=1.328, pts=5, n=493
       High: R/P@60=1.131, pts=0, n=569
         NA: R/P@60=1.329, pts=10, n=1077
    R/P spread: 0.198 → WEAK
    Correlations with existing features:
      F09: r=-0.047
      F21: r=-0.035
      F10: r=+0.017
      F13: r=-0.008

  R7: Backing Approach Vel (backing_approach_vel)
    Valid values: 2023/3278 (61.7%)
    Bins (edges=4.20/9.00):
        Low: R/P@60=1.255, pts=5, n=694
        Mid: R/P@60=1.251, pts=5, n=669
       High: R/P@60=1.134, pts=0, n=660
         NA: R/P@60=1.350, pts=10, n=1255
    R/P spread: 0.216 → MODERATE
    Correlations with existing features:
      F09: r=+0.088
      F10: r=+0.027
      F21: r=+0.024
      F13: r=-0.022

--- Solo Screening Summary ---
   Key Name                             Spread        Class  Valid_N          Max|r| with
  --------------------------------------------------------------------------------------
    R1 Backing Bounce Streak             0.249     MODERATE     2033            F10(0.05)
    R2 Backing Flip Count                0.356     MODERATE     2033            F10(0.23)
    R3 Backing Ray Distance              0.154         WEAK     2201            F21(0.14)
    R4 Backing Ray Decay                 0.189         WEAK     1389            F21(0.26)
    R5 Backing Ray Age                   1.852       STRONG     2033            F21(0.05)
    R6 Backing Cross-TF                  0.198         WEAK     2201            F09(0.05)
    R7 Backing Approach Vel              0.216     MODERATE     2023            F09(0.09)

======================================================================
STEP 3: INCREMENTAL BUILD EXTENSION (position #8+)
======================================================================
  Baseline: 7-feature model PF@3t=5.3671, trades=102, thr=50.0
  Eligible candidates (STRONG/MODERATE): 4

   Pos   Cand Name                              PF@3t  Trades       dPF    Thr Status
  ------------------------------------------------------------------------------------------
     8     R5 Backing Ray Age                  5.1652     154   -0.2019   50.0 REDUNDANT
     8     R2 Backing Flip Count               4.7723     111   -0.5947   55.0 REDUNDANT
     8     R1 Backing Bounce Streak            3.5555     234   -1.8116   50.0 REDUNDANT
     8     R7 Backing Approach Vel             5.1804      56   -0.1867   60.0 REDUNDANT

  No ray candidate showed positive dPF at position #8.

======================================================================
VERDICT
======================================================================

  VERDICT: REDUNDANT
  All ray features showed negative dPF when added to the 7-feature model.
  The existing features (especially F10 Prior Penetration, F21 Zone Age)
  already capture the information that ray attributes provide.

  The 7-feature scoring model STAYS FROZEN at v3.2.
  Ray value is redirected to Analysis B (Surfaces 2-3: trade management).

  Elapsed: 74.6s
```

## Section 1: Data Join Summary

- Join key: `BarIndex_TouchType_SourceLabel`
- P1 touches: 3278
- HTF rays extracted: 750
- Valid interactions: 73638
- Backing ray coverage: 2033/3278 (62.0%)
- Filters: 60m+ rays only, 40t proximity

## Section 2: Solo Screening Results

| Candidate | R/P Spread | Class | Max |r| with Existing 7 |
|-----------|-----------|-------|---------------------|
| R1: Backing Bounce Streak | 0.249 | MODERATE | F10(0.05) |
| R2: Backing Flip Count | 0.356 | MODERATE | F10(0.23) |
| R3: Backing Ray Distance | 0.154 | WEAK | F21(0.14) |
| R4: Backing Ray Decay | 0.189 | WEAK | F21(0.26) |
| R5: Backing Ray Age | 1.852 | STRONG | F21(0.05) |
| R6: Backing Cross-TF | 0.198 | WEAK | F09(0.05) |
| R7: Backing Approach Vel | 0.216 | MODERATE | F09(0.09) |

## Section 3: Incremental Build Results

| Candidate | PF@3t (8-feat) | dPF vs 7-feat | Status |
|-----------|---------------|--------------|--------|
| R5: Backing Ray Age | 5.1652 | -0.2019 | REDUNDANT |
| R2: Backing Flip Count | 4.7723 | -0.5947 | REDUNDANT |
| R1: Backing Bounce Streak | 3.5555 | -1.8116 | REDUNDANT |
| R7: Backing Approach Vel | 5.1804 | -0.1867 | REDUNDANT |

**Did any ray feature enter the elbow? NO**

## Section 3a: Notes on R5 (Backing Ray Age)

R5 classified STRONG (spread 1.852) but this is a **binning artifact**. The `backing_dwell_bars`
field has degenerate tercile edges (0.00/0.00) because 99% of values are 0 (touch occurs
outside an active dwell episode). The "High" bin contains only **24 touches** — far too few
for a reliable R/P estimate. The 3.088 R/P@60 from n=24 is noise. The incremental build
correctly rejected R5 (dPF = -0.20), confirming the STRONG solo classification is spurious.

## Section 3b: Why Redundant Despite Low Correlation?

All ray candidates have max |r| < 0.26 with existing features — meaning ray attributes are
NOT linearly correlated with F10/F01/F05/F09/F21/F13/F04. Yet they still show negative dPF.

This follows the same pattern as F02 (Zone Width, r=? with F09 ZW/ATR) and F12 (Touch Bar
Duration). The redundancy is **nonlinear**: the scoring threshold already selects a subset
where ray context is homogeneous. When the 7-feature model scores a touch highly (score ≥ 50),
it has already selected for young zones (F21), held-or-no-prior cascades (F04), and low
prior penetration (F10) — conditions that implicitly select for favorable backing ray context.
Adding an explicit ray feature cannot split the already-filtered population further.

## Section 4: Verdict

**REDUNDANT**: All ray features showed negative dPF when added to the
7-feature model. The existing features already capture the information
that ray attributes provide.

- Model stays **FROZEN** at v3.2 (7 features)
- Ray value redirected to **Analysis B** (Surfaces 2-3: trade management)
  - OBSTACLE ray features for trade filtering
  - Backing ray attributes for adaptive exit calibration

