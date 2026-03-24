================================================================
PROMPT 3 SUPPLEMENTAL — v3.2 RESULTS-SPECIFIC CORRECTIONS
================================================================

Execute Prompt 3 (P2 Holdout & Verdicts) on the v3.2 
warmup-enriched data. Apply all frozen parameters from 
Prompts 1b and 2 to P2. Report results. The corrections 
below override the base prompt where they conflict.

================================================================
A. RUN COUNT CORRECTION
================================================================

⚠️ Prompt 2 produced 13 runs (not 15). The breakdown:
- 2 full calibration: Seg1 × A-Cal, Seg1 × A-Eq
- 5 full calibration: Seg1-5 × B-ZScore
- 6 report-only: Seg2-4 × A-Cal, Seg2-4 × A-Eq 
  (median cell exits, not grid-calibrated)
- Seg5 skipped for A-Cal/A-Eq (insufficient trades)

Plus B-only 14th run (verdict = VIABLE, PF 1.53, 852 trades).

Total: 14 runs to validate on P2 (13 standard + B-only).

⚠️ Wherever the prompt says "15 runs" or "16th run," use 
13 standard + B-only 14th run instead.

================================================================
B. MULTI-MODE VALIDATION
================================================================

⚠️ Prompt 2 recommended deploying MULTIPLE complementary 
modes simultaneously (not picking a single winner). The 
recommended combo is:

- A-Eq Seg1 ModeA (high conviction, 107 trades, PF 8.50)
- B-ZScore Seg2 RTH (balanced, 245 trades, PF 4.71)

With 13.1% trade overlap on P1.

In addition to per-run verdicts, validate the COMBINATION:

1. On P2, compute the trade overlap between A-Eq Seg1 
   ModeA and B-ZScore Seg2 RTH. Report overlap %.

2. For the union of both modes' trades on P2, compute:
   - Combined PF @3t and @4t
   - Combined max DD
   - Combined Profit/DD
   - Combined trades and trades/day

3. Apply verdict criteria to the combination:
   Does the COMBINED portfolio pass PF > 1.5 @4t?

4. Also validate the secondary combo:
   A-Eq Seg1 ModeA + B-ZScore Seg4 LowATR (16.8% overlap)

⚠️ A mode that passes individually but degrades the combo 
should be flagged. A mode that fails individually but 
improves the combo should also be flagged.
⚠️ COMBO VERDICT LOGIC:
- Both modes pass individually → DEPLOY COMBO
- Mode A passes, Mode B fails → DEPLOY Mode A only
- Mode A fails, Mode B passes → DEPLOY Mode B only  
- Both fail individually but combo passes → CONDITIONAL 
  (paper trade the combo, not the individual modes)

================================================================
C. FEATURE SET UPDATE
================================================================

⚠️ The prompt references the v3.1 winning features 
(F10, F04, F01, F21). The v3.2 winning set is 7 features:

F10 (Prior Touch Penetration), F01 (Timeframe), 
F05 (Session), F09 (ZW/ATR Ratio), F21 (Zone Age), 
F13 (Touch Bar Close Pos), F04 (Cascade State)

Update all feature drift checks (Step 9a) to cover ALL 7 
winning features, not just the old 4.

================================================================
D. ZONE-RELATIVE EXIT HANDLING
================================================================

⚠️ B-ZScore modes use ZONEREL exits (zone-width-relative 
stops and targets). A-Eq Seg1 ModeA uses FIXED exits 
(Stop=190t, Target=60t, TC=120).

When simulating on P2, ensure ZONEREL exits use each P2 
touch's ZoneWidthTicks from NQ_ZTE_raw_P2.csv to compute 
the actual stop/target distances. Do NOT use P1 zone width 
averages.

================================================================
E. DATA FILE CORRECTIONS
================================================================

⚠️ Apply the same data file substitutions from the general 
data correction prepend:

| Old reference | New file |
|--------------|----------|
| NQ_merged_P2a.csv | NQ_ZTE_raw_P2.csv (split at date midpoint for P2a/P2b) |
| NQ_merged_P2b.csv | (same file, second half by date) |

P2a/P2b split: use the date midpoint of P2 (Dec 15 - Mar 2). 
P2a ≈ Dec 15 - Jan 22, P2b ≈ Jan 23 - Mar 2. Confirm exact 
split and report touch counts for each half.

================================================================
F. A-EQ MODE A — EXTRA SCRUTINY
================================================================

⚠️ A-Eq Seg1 ModeA has PF 8.50 with 96.3% WR on P1. This 
is the highest PF in the pipeline. It uses a wide stop 
(190t) with a tight target (60t) — a high-WR structure 
that is SENSITIVE to win rate degradation.

For A-Eq ModeA specifically on P2, report:
1. Win rate on P2a and P2b separately
2. If WR drops below 90%, compute the PF at that WR
3. Size of losing trades on P2 vs P1 (are P2 losses larger?)
4. Max consecutive losses on P2 (P1 had max 1)

A WR drop from 96% to 88% with 190t stop and 60t target 
gives PF ≈ 2.3. A drop to 80% gives PF ≈ 1.3. Report the 
breakeven WR for this exit structure.

================================================================
G. DEPLOYMENT SPEC UPDATE
================================================================

⚠️ Section 13d references "unmodified V4 + ZB4 aligned + 
new autotrader." After ZTE consolidation:

Use: V4 (unchanged) + ZoneTouchEngine (replaces ZRA+ZB4) + 
new autotrader.

The deployment spec should reference the v3.2 scoring model 
files (_v32 suffix) and the ZTE-based data pipeline.

================================================================
H. NARRATIVE REPORT ADDITION
================================================================

⚠️ Add an 8th section to the verdict_narrative.md:

8. **Multi-mode deployment assessment:** If multiple modes 
   pass validation, describe the complementary deployment 
   — which modes run simultaneously, their overlap, combined 
   risk profile, and which market conditions each mode 
   specializes in. Reference the mode classification 
   dimensions (AGGRESSIVE, BALANCED, CONSERVATIVE, VOLUME, 
   CONSISTENT, ROBUST, SCALABLE, IMPLEMENTABLE) from the 
   mode_classification_v32.md analysis.
