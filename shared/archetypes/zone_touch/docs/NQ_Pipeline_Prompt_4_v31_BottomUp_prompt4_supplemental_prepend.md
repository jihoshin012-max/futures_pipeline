================================================================
PROMPT 4 SUPPLEMENTAL — v3.2 RESULTS-SPECIFIC CORRECTIONS
================================================================

Execute Prompt 4 (Cross-Reference & Gap Investigation) on 
the v3.2 pipeline results. The corrections below override 
the base prompt where they conflict.

================================================================
A. V3.2 PIPELINE CONTEXT
================================================================

⚠️ The v3.2 pipeline differs significantly from v3.1. Key 
context for all comparisons:

- P1: 3,278 touches (was ~325 in old cold-start, 4,701 in 
  v3.1 prompt text). Warmup-enriched chart with 90+ days 
  pre-P1 history.
- P2: 3,537 touches across P2a (1,767) + P2b (1,770)
- 7 winning features: F10, F01, F05, F09, F21, F13, F04
  (was 4 features in v3.1: F10, F04, F01, F21)
- F04 dropped from STRONG to MODERATE but still entered 
  elbow via incremental PF contribution
- 3 new features in elbow: F05 (Session), F09 (ZW/ATR), 
  F13 (Touch Bar Close Pos)
- B-ZScore was degenerate (rolling z-score destroyed signal), 
  fixed with global StandardScaler + L1 regularization
- VP Ray features dead (HasVPRay=0 for all warmup-enriched 
  touches). F03, F19, F20 permanently dropped.

================================================================
B. UPDATED VERDICT CONTEXT
================================================================

⚠️ Prompt 3 v3.2 results:
- 0 Yes, 24 Conditional, 4 Conditional (combined only)
- Winner: A-Eq Seg1 ModeA (PF 6.26 @4t, 96 trades, 94.8% WR)
- Multi-mode combo VALIDATED:
  A-Eq ModeA + B-ZScore Seg2 RTH = DEPLOY COMBO
  (423 trades, PF 4.43 @4t, Profit/DD 47.6)

All references to "15 runs" → use 14 (13 standard + B-only).
All references to "4,701 touches" → use 3,278.
All references to "verdict_narrative.md" → use 
verdict_narrative_v32.md (8-section version including 
multi-mode assessment).

================================================================
C. PRIOR REFERENCE COMPARISON UPDATES
================================================================

⚠️ Step 14b references "prior M1_A achieved PF 4.67 on 66 
trades." The v3.1 recalibration produced different results 
on the corrected population. Use the v3.2 winner (A-Eq 
Seg1 ModeA, PF 6.26 @4t, 96 trades) as the primary 
comparison, with the prior M1_A as secondary context.

⚠️ Step 15a mode comparison table: the prior M1-M5 modes 
may not have direct equivalents in v3.2. The multi-mode 
deployment structure is different:
- A-Eq ModeA ≈ prior M1 (high-conviction zone bounce)
- B-ZScore Seg2 RTH = NEW (no prior equivalent — volume 
  mode with continuous scoring)
- B-Only tier = NEW (lower-conviction residual)

⚠️ Step 15b feature comparison: update prior weights. The 
old top-down had cascade as #1 (weight 20). In v3.2 
bottom-up, F10 (Prior Penetration) is #1 (weight 10.0), 
F04 (Cascade) is #7 (weight 1.93). This is the biggest 
structural insight: cascade was overweighted in the prior 
analysis. F10 is the true dominant feature.

================================================================
D. SPECIFIC INVESTIGATION POINTS — UPDATED
================================================================

⚠️ Replace the investigation points in Step 16b with:

1. A-CAL vs A-EQ: A-Eq won on P2 (PF 6.26 vs A-Cal 1.62). 
   Both use the same 7 features with different weighting. 
   Why does equal-weight outscore calibrated-weight on P2? 
   Investigate whether A-Cal's proportional weights overfit 
   to P1's feature distribution while A-Eq's equal weights 
   generalize better.

2. WIN RATE JUMP: v3.2 winner has 94.8% WR vs prior 60.6%. 
   This is entirely due to exit structure — 190t stop / 60t 
   target gives high WR by design (wide stop, tight target). 
   Confirm by computing WR at the prior exit structure 
   (3-leg partial) on the v3.2 qualifying touches.

3. B-ZSCORE RECOVERY: The B-ZScore model required a 
   different normalization approach (global StandardScaler 
   + L1 vs rolling z-score). Investigate: does the corrected 
   B-ZScore select a fundamentally different population 
   than A-Eq, or is it selecting the same quality touches 
   through a different lens? Report feature importance from 
   the L1 coefficients.

4. MULTI-MODE OVERLAP: The P1 overlap between A-Eq ModeA 
   and B-ZScore Seg2 RTH was 13.1%. Report the P2 overlap. 
   If P2 overlap is significantly different (>25%), the 
   modes' complementarity may not generalize.

================================================================
E. GAP INVESTIGATION — ADDITIONS
================================================================

⚠️ Add these targeted tests to Step 17b:

| # | Test | Rationale |
|---|------|-----------|
| F | ZONEREL exits on A-Eq ModeA population | A-Eq uses FIXED 190t/60t. What if zone-relative exits are applied to the same qualifying touches? |
| G | A-Cal ModeA as middle tier | 1,183 trades at PF 1.62. Decompose: what % overlap with A-Eq ModeA? What PF on the non-overlapping A-Cal-only population? Is this a viable 3rd mode? |
| H | Session sub-splits of B-ZScore RTH | B-ZScore Seg2 RTH = all RTH sessions combined. Does OpeningDrive outperform Midday/Close within this population? Could you run RTH with session-conditional exits? |

================================================================
F. STUDY FILE REFERENCE UPDATE
================================================================

⚠️ Step 18c references "V4 v1 (unmodified) + ZB4 aligned + 
new autotrader." After ZTE consolidation:

Use: V4 (unchanged) + ZoneTouchEngine (replaces ZRA+ZB4) + 
new autotrader(s).

For multi-mode deployment, the autotrader routing is:
1. ZTE detects touch and exports scoring features
2. Check A-Eq score ≥ 45.5 → Mode 1 (FIXED 190t/60t)
3. Else check B-ZScore score ≥ 0.50 AND RTH AND seq ≤2 
   AND TF ≤120m → Mode 2 (ZONEREL exits)
4. Else skip

This is a priority waterfall, not two separate autotraders.

================================================================
G. SYNTHESIS QUESTION UPDATES
================================================================

⚠️ Step 18a question updates:

Question 9 (overfit risk): Baseline PF = 1.34. A-Eq winner 
PF = 6.26. That's 4.7× baseline — moderate overfit risk. 
But 94.8% WR on 96 P2 trades with 17.6pp safety margin 
above breakeven argues against pure overfitting. Discuss 
both perspectives.

Question 11 (B-only tier): B-only now VALIDATED (PF 2.34 
@4t, 669 trades, Conditional verdict). This IS a viable 
third tier. Discuss whether 3-tier deployment (A-Eq ModeA 
+ B-ZScore RTH + B-Only) adds value over 2-tier.

Add Question 12: MULTI-MODE DEPLOYMENT ASSESSMENT. The 
primary combo (A-Eq + B-ZScore RTH) validates at PF 4.43 
on 423 trades. But 24 modes received "Conditional" verdicts. 
Evaluate ALL viable modes for deployment potential:

Tier 1 candidates (PF > 4.0 @4t):
- A-Eq Seg1 ModeA (96 trades, PF 6.26)
- B-ZScore Seg2 RTH (327 trades, PF 4.25)

Tier 2 candidates (PF 2.0-4.0 @4t):
- B-ZScore Seg1 ModeA (713 trades, PF 2.45)
- seg5 Cluster0 (796 trades, PF 2.66)
- B-ZScore Seg4 LowATR (378 trades, PF 2.57)
- B-ZScore Seg4 HighATR (490 trades, PF 2.55)
- B-ZScore Seg3 WTNT (401 trades, PF 2.42)
- B-ZScore Seg3 CT (413 trades, PF 2.42)
- B-Only (669 trades, PF 2.34)
- A-Eq ModeB (868 trades, PF 2.13)

Tier 3 candidates (PF 1.5-2.0 @4t):
- B-ZScore Seg2 Overnight (328 trades, PF 1.87)
- A-Cal Seg2 PreRTH (140 trades, PF 1.94)
- A-Cal Seg2 RTH (548 trades, PF 1.88)
- A-Cal Seg4 LowATR (448 trades, PF 1.75)
- A-Cal Seg1 ModeA (1183 trades, PF 1.62)

For each tier, compute overlap matrix (% of trades shared 
between every pair). Identify the MINIMUM SET of modes that 
covers the maximum non-overlapping trade population while 
maintaining combined PF > 2.0 @4t.

What is the diminishing returns point — when does adding 
modes dilute combined PF without adequate trade count 
benefit? Plot: number of modes vs combined PF vs total 
trades.
