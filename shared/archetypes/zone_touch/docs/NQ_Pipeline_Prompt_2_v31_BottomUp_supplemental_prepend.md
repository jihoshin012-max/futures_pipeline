================================================================
PROMPT 2 SUPPLEMENTAL — v3.2 RESULTS-SPECIFIC CORRECTIONS
================================================================

Execute Prompt 2 (Segmentation & Exit Calibration) on the 
v3.2 warmup-enriched data. Run all calibration runs, report 
results. The corrections below override the base prompt 
where they conflict.

================================================================
A. TRADE COUNT REALITY — CRITICAL
================================================================

⚠️ The v3.2 scoring models produce these P1 trade counts:
- A-Cal: 84 trades (threshold 21.09 / max 30.13 = 70%)
- A-Eq: 102 trades (threshold 45.5 / max 70 = 65%)
- B-ZScore: 877 trades (threshold 0.50)

Segmentations with 3-4 groups will shred A-Cal/A-Eq into 
groups of 20-30 trades each. This is too thin for meaningful 
exit grid calibration.

RULE: For A-Cal and A-Eq, ONLY run Segmentation 1 (Score 
Only) with full exit grid calibration. For Segmentations 
2-5, report group sizes but use median cell exits for all 
A-Cal/A-Eq groups — do NOT run exit grids on groups with 
< 50 trades.

B-ZScore (877 trades) has adequate headroom for all 5 
segmentations with full exit calibration.

This means: 2 full calibration runs (Seg 1 × A-Cal, A-Eq) 
+ 5 full calibration runs (Seg 1-5 × B-ZScore) + 6 
report-only runs (Seg 2-4 × A-Cal, A-Eq with median exits).
Seg 5 (K-means) skipped for A-Cal/A-Eq (see Section G).
Total: 13 runs, 7 with calibrated exits, 6 report-only.

================================================================
B. SESSION SEGMENTATION FIX
================================================================

⚠️ Segmentation 2 in the prompt uses Morning/Afternoon. 
The v3.2 screening found 5 session classes with different 
performance profiles:

- PreRTH: best session (PF far above baseline)
- OpeningDrive: strong
- Midday: moderate
- Close: moderate  
- Overnight: weakest (PF below baseline)

Replace Segmentation 2 group definitions with:

- **Mode A:** Score ≥ threshold AND RTH session 
  (OpeningDrive + Midday + Close)
- **Mode B:** Score ≥ threshold AND PreRTH
- **Mode C:** Score ≥ threshold AND Overnight
- **Mode D:** Below threshold (all sessions)

This aligns with the actual session classes from Prompt 1a 
and the baseline finding (RTH PF=1.50 vs Overnight PF=1.13).

================================================================
C. ZONE-RELATIVE EXITS — ADD TO EXIT GRID
================================================================

⚠️ The exit grid only tests FIXED stop/target levels. The 
prior v3.1 model found zone-relative exits (ZONEREL) 
outperformed fixed exits. Add zone-relative options:

Single-leg zone-relative grid (run alongside the fixed grid):

| Parameter | Values |
|-----------|--------|
| Stop | 1.0×ZW, 1.2×ZW, 1.5×ZW, max(1.5×ZW, 120t) |
| Target | 0.3×ZW, 0.5×ZW, 0.75×ZW, 1.0×ZW |
| Time cap | 30, 50, 80 bars |

Compare the best zone-relative cell against the best fixed 
cell for each group. Report both. If zone-relative wins, 
it advances to Prompt 3. If fixed wins, fixed advances.

⚠️ Zone-relative exits require ZoneWidthTicks from ZTE_raw 
for each touch. This column exists in the data.

================================================================
D. MULTI-MODE DEPLOYMENT FRAMING
================================================================

⚠️ The goal is NOT to pick a single winner. Multiple modes 
can coexist if they serve different purposes:

- High-conviction mode: few trades, high PF, tight filter
- Broader mode: more trades, moderate PF, wider filter
- Regime-conditional mode: different exits per regime

For EVERY group in EVERY segmentation, report these metrics 
explicitly in a deployment comparison table:

| Seg | Model | Group | P1 PF | Trades | Trades/Day | 
  Max DD | Profit/DD | Exit Type | Regime |

After all 13 runs, produce a MULTI-MODE RECOMMENDATION:
- Which 2-3 configurations could be deployed simultaneously?
- Do they overlap (same trades scored differently) or are 
  they complementary (different trade populations)?
- What is the COMBINED P1 PF if all recommended modes run 
  together (union of their trade populations)?

⚠️ Modes that trade the same touches with different exits 
are NOT complementary — they're redundant. Complementary 
modes have < 30% trade overlap.

================================================================
E. STOP INVESTIGATION ADDITION
================================================================

⚠️ The current stop investigation is limited to the exit 
grid sweep. Add a targeted stop analysis for the best 
group in Segmentation 1 (highest PF):

For all qualifying trades in that group:

1. OPPOSITE ZONE EDGE: What PF if stop = 1.0×ZW (opposite 
   zone edge) instead of the grid winner? Report trades 
   stopped out by tighter stop that would have won under 
   wider stop.

2. PARENT ZONE BACKSTOP: For touches with a parent zone 
   (higher TF zone overlapping), what PF if stop = 
   min(current stop, parent zone opposite edge + 20t)?

3. TIME-BASED TIGHTENING: After 30 bars without price 
   reaching 0.25×target, tighten stop to 0.8× original. 
   Report additional stop-outs and net PF impact.

These are observational — report results but do NOT change 
the frozen exit parameters. The stop investigation informs 
a future dedicated stop prompt.

================================================================
F. SBB-MASKED REFERENCES
================================================================

⚠️ The v3.2 screening found 0 SBB-MASKED features. All 
references to "SBB-MASKED features," "NORMAL-only R/P 
spread," and the SBB-MASKED feature check in Step 6 can 
be simplified. Still report SBB vs NORMAL PF per group 
(the SBB split is structural), but skip the SBB-MASKED 
specific checks.

================================================================
G. SEGMENTATION 5 (K-MEANS) SCOPE
================================================================

⚠️ K-means on 84 A-Cal trades or 102 A-Eq trades is 
meaningless — k=4 gives ~20 per cluster. Run Segmentation 
5 on B-ZScore ONLY (877 trades). Skip it entirely for 
A-Cal and A-Eq. This reduces total runs from 15 to 13.

================================================================
H. CORRECTED MEDIAN CELL FALLBACK
================================================================

⚠️ The prompt references "Stop=90t, Target=120t, TimeCap=80" 
as the median cell fallback. The v3.2 baseline found:

Median cell: Stop=120t, Target=120t, TimeCap=80 bars

Use these corrected values for all small-group fallbacks.
