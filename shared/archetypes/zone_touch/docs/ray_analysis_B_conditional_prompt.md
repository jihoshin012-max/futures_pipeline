# Ray Analysis B — Conditional Ray Analysis (Qualifying Trades)

**Purpose:** Determine whether ray context at time of entry can improve trade outcomes 
for the v3.2 qualifying population — either by filtering out predictable losers 
(Surface 2: skip gate) or by adapting exits based on ray environment (Surface 3: 
adaptive exits). The scoring model is treated as FROZEN throughout this analysis.

**Branch:** `feature/ray-integration` (off `v3.2-baseline` tag)
**Pipeline version:** 3.2 (model frozen, exits under investigation)
**Date:** 2026-03-24
**Dependency:** Analysis A is COMPLETE. Verdict: REDUNDANT. All ray candidates 
showed negative dPF. The 7-feature scoring model is FROZEN at v3.2. Use v3.2 
qualifying population as-is. Key finding: R1 (Backing Bounce Streak) showed 
dPF = -1.8116 (actively harmful, not merely redundant) — see paradox diagnostic 
in Step 1d.

**Prior ray work (reference — results are valid):**
- `ray_baseline_analysis.md` — observational base rates
- `ray_htf_followup.md` — Check 9 already investigated rays as stop/target/entry 
  refinement on observational level. Analysis B builds on those findings with 
  formal P1-calibrate / P2-validate protocol on the qualifying population.
- `ray_feature_screening.py` — contains BACKING RAY vs OBSTACLE RAY aggregation 
  framework. REUSE this logic:
  - **BACKING RAY**: Nearest 60m+ ray AT or BEHIND entry (inside zone or on stop 
    side). Describes the S/R structure supporting the trade. Used for Surface 2 
    (skip gate — is the backing structure weak?).
  - **OBSTACLE RAY**: Nearest 60m+ ray AHEAD of entry (between entry and target). 
    Describes what blocks the profit path. Used for Surface 3 (adaptive exits — 
    should we tighten target?).
- `ray_feature_screening_prompt.md` Section 0 — defines ray lifecycle feature 
  computation (bounce streak, flip count, dwell bars, etc.). USE THIS METHODOLOGY.

---

## Context

The v3.2 deployment is a 2-tier priority waterfall:
- **Mode 1 (A-Eq ModeA):** Score ≥ 45.5 → FIXED exit (190t stop / 60t target / 
  120-bar TC). ~127 P1 trades, 96 P2 trades, PF 6.26 @4t.
- **Mode 2 (B-ZScore RTH):** B-ZScore ≥ 0.50 AND RTH AND seq ≤ 2 AND TF ≤ 120m → 
  ZONEREL exit (max(1.5×ZW, 120) stop / 1.0×ZW target / 80-bar TC). ~245 P1, 
  327 P2 trades, PF 4.25 @4t.
- **Combined:** ~330-350 P1, 423 P2, PF 4.43 @4t, Profit/DD 47.6.

⚠️ THE MODEL IS FROZEN. This analysis does NOT modify feature weights, bin 
boundaries, thresholds, or the waterfall routing logic. It adds an OVERLAY — 
either a pre-entry skip gate or post-entry exit modification.

Ray baseline findings relevant to this analysis:
- Bounce streak: 30.5pp spread. High-streak rays repel price.
- Dwell time: real-time decay over 20 bars. Price lingers = weakening bounce.
- Stale+stale R/P 1.85 > fresh+fresh 1.14 (streak explains this).
- Adverse ray as stop: dead at 25t.
- 60m+ rays only, 40t proximity threshold.

⚠️ CRITICAL FINDING FROM ANALYSIS A: Backing bounce streak (R1) showed dPF = 
-1.8116 when added to the 7-feature model — actively HARMFUL, not merely redundant. 
The other ray candidates were near zero (dPF -0.19 to -0.59). This suggests a 
Simpson's paradox: high backing streak = good across ALL touches (baseline 30.5pp), 
but among qualifying trades, high backing streak may correlate with WORSE outcomes. 
Possible mechanism: high-streak backing rays indicate congested, heavily structured 
areas where the model's quality filter has already selected the best trades, and 
adding streak over-selects for congestion.

⚠️ NOTE: Analysis A's GSD used threshold 50.0 (102 P1 trades). The deployment 
threshold is 45.5 (127 P1 trades). The paradox was observed at 50.0. Step 1d 
tests it at the DEPLOYMENT threshold (45.5) — the correct population. The paradox 
may or may not persist with the 25 additional trades. Either result is informative.

**Implication for this analysis:** Do NOT assume "strong backing ray = protective" 
for qualifying trades. The relationship may be inverted in this population. 
Step 1d (below) explicitly tests this before Surfaces 2 and 3 rely on backing 
streak as a signal.

---

## File Locations

```
QUALIFYING TRADE DATA:
  c:\Projects\pipeline\shared\archetypes\zone_touch\output\p1_scored_touches_aeq_v32.csv
  c:\Projects\pipeline\shared\archetypes\zone_touch\output\p1_scored_touches_bzscore_v32.csv

RAW TOUCH + OUTCOME DATA:
  c:\Projects\pipeline\stages\01-data\data\touches\NQ_ZTE_raw_P1.csv
  c:\Projects\pipeline\stages\01-data\data\touches\NQ_ZTE_raw_P2.csv

RAY DATA:
  c:\Projects\pipeline\stages\01-data\data\touches\NQ_ray_context_P1.csv
  c:\Projects\pipeline\stages\01-data\data\touches\NQ_ray_context_P2.csv
  c:\Projects\pipeline\stages\01-data\data\touches\NQ_ray_reference_P1.csv
  c:\Projects\pipeline\stages\01-data\data\touches\NQ_ray_reference_P2.csv

SIMULATION SCRIPTS:
  c:\Projects\pipeline\shared\archetypes\zone_touch\zone_touch_simulator.py
  c:\Projects\pipeline\stages\04-backtest\zone_touch\prompt3_holdout_v32.py

# ⚠️ 60m+ rays ONLY, 40t backing proximity, 100t obstacle search range.
RAY ELBOW TEST OUTPUT (from Analysis A):
  c:\Projects\pipeline\shared\archetypes\zone_touch\output\ray_elbow_candidates_v32.csv
```

⚠️ CRITICAL: `ray_elbow_candidates_v32.csv` contains BACKING ray features per 
touch from Analysis A. Load this first. You still need to compute OBSTACLE ray 
features (ahead of entry) — they were not part of Analysis A.

📌 REMINDER: Analysis B treats the scoring model as FROZEN. We are testing overlays 
(skip gates and adaptive exits), not modifying the 7-feature model or thresholds.

---

## Step 0: Data Inspection (MANDATORY FIRST STEP)

```python
import pandas as pd

# 1. Scored touches — identify qualifying trades
aeq = pd.read_csv(r'c:\Projects\pipeline\shared\archetypes\zone_touch\output\p1_scored_touches_aeq_v32.csv')
print("A-Eq scored columns:", list(aeq.columns))
print("A-Eq shape:", aeq.shape)

bz = pd.read_csv(r'c:\Projects\pipeline\shared\archetypes\zone_touch\output\p1_scored_touches_bzscore_v32.csv')
print("\nB-ZScore scored columns:", list(bz.columns))
print("B-ZScore shape:", bz.shape)

# 2. Identify qualifying population
# A-Eq ModeA: score >= 45.5
# B-ZScore RTH: bzscore >= 0.50 AND RTH AND seq <= 2 AND TF <= 120m
# Check what column names are used for score, session, seq, TF
print("\nA-Eq score column stats:")
# (adapt column name after inspection)

# 3. Raw touch data — what outcome columns exist?
zte = pd.read_csv(r'c:\Projects\pipeline\stages\01-data\data\touches\NQ_ZTE_raw_P1.csv')
print("\nZTE columns:", list(zte.columns))

# 4. Ray data
# ⚠️ 60m+ rays ONLY. Filter LTF before any analysis.
ray_ctx = pd.read_csv(r'c:\Projects\pipeline\stages\01-data\data\touches\NQ_ray_context_P1.csv')
print("\nRay context columns:", list(ray_ctx.columns))
print("Ray context shape:", ray_ctx.shape)

ray_ref = pd.read_csv(r'c:\Projects\pipeline\stages\01-data\data\touches\NQ_ray_reference_P1.csv')
print("\nRay reference columns:", list(ray_ref.columns))
print("Ray reference shape:", ray_ref.shape)

# 5. If Analysis A output exists, load it
try:
    ray_feat = pd.read_csv(r'c:\Projects\pipeline\shared\archetypes\zone_touch\output\ray_elbow_candidates_v32.csv')
    print("\nRay elbow candidates columns:", list(ray_feat.columns))
    print("Shape:", ray_feat.shape)
except FileNotFoundError:
    print("\nray_elbow_candidates_v32.csv not found — will compute ray features from raw data")
```

⚠️ STOP after this step. Report schemas and qualifying population counts. Confirm 
A-Eq ModeA P1 count ≈ 127 and B-ZScore RTH P1 count ≈ 245 before proceeding.

**If running as a single session:** Print the schema output above, review it 
yourself, and only proceed to Step 1 once you have confirmed the qualifying 
population counts match expectations and the outcome columns exist (PnL, MFE, MAE 
or equivalent). If schemas don't match expectations, STOP and report the discrepancy.

**If running as a multi-turn session:** Post the output and wait for confirmation.

---

## Step 1: Build Qualifying Trade Dataset with Ray Context

### 1a: Identify qualifying trades

Apply the frozen waterfall to P1 data:
1. Compute A-Eq score for all P1 touches
2. Flag Mode 1 trades: A-Eq score ≥ 45.5
3. Compute B-ZScore for ALL P1 touches (using frozen mean/std from 
   `scoring_model_bzscore_v32.json` — do NOT refit the StandardScaler on a subset)
4. Flag Mode 2 trades: B-ZScore ≥ 0.50 AND RTH AND seq ≤ 2 AND TF ≤ 120m
5. EXCLUDE Mode 1 trades from Mode 2 set (A-Eq has priority in the waterfall)
6. Combined qualifying set = Mode 1 + Mode 2 (non-overlapping by construction)

⚠️ VERIFY: Mode 1 P1 count should be ~127. Mode 2 P1 count (after excluding Mode 1 
overlap) should be ~215-230. Combined = Mode 1 + Mode 2 = ~330-350. If counts are 
significantly different, STOP and investigate. Note: ~13% of B-ZScore qualifiers 
also qualify for A-Eq — they are assigned to Mode 1 (priority) and excluded from 
Mode 2 count.

### 1b: Join ray context to qualifying trades

For EACH qualifying trade, characterize the ray environment at time of entry 
using the BACKING RAY / OBSTACLE RAY framework from `ray_feature_screening.py`:

**BACKING RAY** (nearest 60m+ ray at/behind entry — stop side):
| Field | Definition |
|-------|-----------|
| backing_ray_dist | Distance (ticks) from entry to backing ray |
| backing_ray_streak | Bounce streak of backing ray at touch time |
| backing_ray_flips | Flip count of backing ray |
| backing_ray_dwell | Bars price has dwelt near backing ray |
| has_backing_ray | Binary: is there a 60m+ backing ray within 40t? |

⚠️ BACKING RAY SEARCH RANGE = 40t (matching Analysis A and ray_elbow_candidates_v32.csv). 
If the CSV from Analysis A is loaded, these values are already computed at 40t. 
Do NOT change to 100t — the paradox diagnostic in Step 1d depends on consistency 
with Analysis A's data.

**OBSTACLE RAY** (nearest 60m+ ray ahead of entry — profit side):
| Field | Definition |
|-------|-----------|
| obstacle_ray_dist | Distance (ticks) from entry to obstacle ray |
| obstacle_ray_streak | Bounce streak of obstacle ray at touch time |
| obstacle_ray_flips | Flip count of obstacle ray |
| obstacle_ray_dwell | Bars price has dwelt near obstacle ray |
| has_obstacle_ray | Binary: is there a 60m+ obstacle ray within 100t? |

⚠️ NOTE ON SEARCH RANGE: Obstacle ray search uses 100t (not 40t) because we are 
looking for rays that could interfere with the trade's PROFIT TARGET, which is 
60t (Mode 1) to ~1.0×ZW (Mode 2, typically 100-300t). A ray 80t ahead is irrelevant 
for interaction detection (40t threshold) but critically relevant for trade management. 
The 100t range covers the Mode 1 target zone. For Mode 2 with wider targets, also 
check for obstacle rays up to the ZONEREL target distance for each trade.

**ENVIRONMENT** (aggregate):
| Field | Definition |
|-------|-----------|
| ray_count_100t | Total 60m+ rays within 100t of entry |
| ray_count_50t | Total 60m+ rays within 50t of entry |

📌 REMINDER: "Backing" = stop direction (for demand zone touch, backing = below entry; 
for supply zone, backing = above entry). "Obstacle" = profit direction. The zone type 
(demand/supply) determines which direction is which. The existing 
`ray_feature_screening.py` already implements this mapping — reuse its logic.

⚠️ ADAPT these field definitions to the actual ray data structure found in Step 0. 
If directional ray info isn't available, compute it from ray price vs entry price 
vs zone type.

### 1c: Join trade outcomes

For each qualifying trade, attach the actual trade outcome using MODE-SPECIFIC 
exit parameters:
- PnL (ticks)
- Win/loss
- Exit type (target hit, stop hit, time cap)
- Max favorable excursion (MFE) in ticks
- Max adverse excursion (MAE) in ticks
- Bars held

⚠️ CHECK: Inspect `prompt3_holdout_v32.py` for how per-trade outcomes are computed.
If the holdout script already saves per-trade results to a CSV with these columns, 
load that CSV. If it only saves aggregate statistics (PF, WR, trade count), you 
will need to run the simulation to get per-trade outcomes — this is NOT recalibration, 
it is replicating the existing P1 simulation to extract per-trade detail. Use the 
SAME exit parameters (Mode 1: FIXED 190t/60t/TC120, Mode 2: ZONEREL) and the 
SAME scoring thresholds. The aggregate PF must match the known v3.2 values.

⚠️ IMPORTANT DISTINCTION for later steps: Step 3d ("Re-simulate with MODIFIED 
exits") is a DIFFERENT operation — that tests alternative exit rules on the same 
trades. The simulation here in Step 1c uses the BASELINE v3.2 exit parameters. 
Both are valid simulations; they serve different purposes.

### 1d: Backing Streak Paradox Diagnostic (MANDATORY BEFORE Step 2)

⚠️ Analysis A found backing bounce streak (R1) was actively HARMFUL when added 
to the scoring model (dPF = -1.8116). Before designing skip gates or adaptive 
exits that rely on backing streak, test whether the paradox exists in this 
qualifying population.

For P1 qualifying trades (Mode 1 and Mode 2 separately):

| backing_ray_streak | N | WR% | PF @4t | Mean PnL | vs Mode Population |
|-------------------|---|-----|--------|----------|--------------------|
| 0 (just flipped) | ? | ? | ? | ? | ? |
| 1-2 | ? | ? | ? | ? | ? |
| 3-5 | ? | ? | ? | ? | ? |
| 6+ | ? | ? | ? | ? | ? |
| No backing ray | ? | ? | ? | ? | ? |

**Three possible outcomes:**

1. **Paradox CONFIRMED**: Higher backing streak → worse PF among qualifying trades. 
   → "Strong backing" is NOT protective in this population. Reverse the Surface 2 
   hypothesis: "strong backing" becomes a potential SKIP signal (congestion), not 
   a safety signal. Surface 3 should not use backing streak for stop tightening.

2. **Paradox NOT CONFIRMED**: Higher backing streak → better or neutral PF among 
   qualifying trades. → The dPF=-1.8 from Analysis A was a binning/threshold 
   interaction artifact, not a population-level inversion. Proceed with original 
   Surface 2/3 hypotheses (strong backing = protective).

3. **MODE-DEPENDENT**: Paradox holds for Mode 1 but not Mode 2 (or vice versa). 
   → Apply backing streak signals only to the mode where the relationship holds.

📌 THIS DIAGNOSTIC GATES THE INTERPRETATION OF ALL SUBSEQUENT BACKING RAY RESULTS. 
Report the outcome clearly and reference it when interpreting Surface 2 and Surface 3 
findings. If the paradox is confirmed, the "Weak backing" and "Strong backing" 
segments in Step 2a must be RELABELED and their hypotheses REVERSED.

### 1e: Coverage gates and data save

⚠️ COVERAGE GATES — report both before proceeding:
- **Backing ray coverage**: What % of qualifying trades have a 60m+ backing ray? 
  (Should be ~62% based on Analysis A's full-population rate, but may differ for 
  the qualifying subset.)
- **Obstacle ray coverage**: What % of qualifying trades have a 60m+ obstacle ray 
  within 100t ahead of entry? If below 30%, Surface 3 winner analysis lacks power. 
  In that case, widen the obstacle search range to max(100t, ZONEREL target distance) 
  and re-report. If still below 30%, note that Surface 3 results are low-confidence.

**Save the enriched qualifying trade dataset immediately:**
Save to `c:\Projects\pipeline\shared\archetypes\zone_touch\output\qualifying_trades_ray_context_v32.csv`
This file is the reusable dataset regardless of the analysis verdict. Do NOT defer 
this save to Step 5.

---

## Step 2: Surface 2 — Skip Gate Analysis

**Question:** Are there specific ray configurations among qualifying trades that 
reliably predict LOSERS?

⚠️ SCOPE: Skip gates are primarily a MODE 2 investigation. Mode 1 has 94.8% WR 
(~5 P2 losers out of 96 trades) — no segment will have enough losers for 
statistical reliability. Compute Mode 1 segments for completeness but do NOT 
propose Mode 1 skip gates unless a segment has N ≥ 15 losers on P1. Mode 2 has 
22.7% loss rate (~74 P2 losers) — sufficient for segment analysis.

### 2a: Segment qualifying trades by ray context

Split qualifying trades into groups:

| Segment | Definition | Hypothesis |
|---------|-----------|------------|
| Strong obstacle, close | obstacle_ray_dist ≤ 40t AND obstacle_ray_streak ≥ 5 | Price hits wall before target → higher loss rate |
| Strong obstacle, mid | obstacle_ray_dist 40-80t AND obstacle_ray_streak ≥ 5 | Partial obstruction |
| No obstacle ray | has_obstacle_ray = False | Unobstructed profit path |
| Strong backing | backing_ray_streak ≥ 5 AND has_backing_ray = True | ⚠️ CONDITIONAL on Step 1d: if paradox confirmed, this is a SKIP candidate (congestion), not protective |
| Weak backing | backing_ray_streak ≤ 1 OR has_backing_ray = False | ⚠️ CONDITIONAL on Step 1d: if paradox confirmed, this may be NEUTRAL or positive, not vulnerable |
| Dense ray zone | ray_count_50t ≥ 3 | Congested area, choppy price action |

⚠️ Adapt segment definitions based on the actual data distributions found. Use 
P1 terciles/quartiles if the above thresholds don't produce balanced groups.

📌 REMINDER: We are looking for LOSERS, not winners. The model already selects 
high-quality touches (94.8% WR for Mode 1, 77.3% for Mode 2). A useful skip gate 
must identify a subset with significantly WORSE outcomes. The bar is high — you 
need a subset where WR drops below breakeven (77.2% for Mode 1, ~65% for Mode 2).

### 2b: Compute segment-level performance

For each segment, on P1 qualifying trades:

| Segment | N | WR% | PF @4t | Mean PnL | vs Population |
|---------|---|-----|--------|----------|---------------|

### 2c: Identify skip candidates

A segment qualifies as a skip gate candidate if:
1. PF @4t is significantly below the mode's overall PF (>50% reduction)
2. The segment contains enough trades for statistical reliability (N ≥ 15 on P1)
3. The performance degradation has a mechanistic explanation (ray ahead blocks 
   profit target, etc.)

⚠️ CRITICAL: Apply skip gate candidates to Mode 1 and Mode 2 SEPARATELY. A ray 
configuration that hurts Mode 2 (ZONEREL exits) may not hurt Mode 1 (FIXED exits) 
because the exit structures interact differently with ray obstacles.

### 2d: P2 validation of skip gate candidates

⚠️ P2 VALIDATION REQUIRES REPLICATING THE FULL STEP 1 PIPELINE ON P2 DATA:
1. Score all P2 touches using frozen A-Eq and B-ZScore models (same thresholds)
2. Apply the waterfall: Mode 1 (A-Eq ≥ 45.5) first, Mode 2 (B-ZScore ≥ 0.50, 
   RTH, seq ≤ 2, TF ≤ 120m, excluding Mode 1) second
3. Compute BACKING and OBSTACLE ray features for P2 qualifying trades using 
   P2 ray data files (same methodology as Step 1b)
4. Join P2 trade outcomes using P2 simulation (same exit parameters as Step 1c)
5. Verify: P2 Mode 1 count ≈ 96, P2 Mode 2 count ≈ 280-330

Then for each skip gate candidate from 2c:
1. Apply the same segment definition to P2 qualifying trades
2. Compute the same segment performance metrics
3. Does the performance degradation persist on P2?

| Skip Gate Candidate | P1 PF @4t | P2 PF @4t | P1 N | P2 N | Verdict |
|--------------------|-----------|-----------| -----|------|---------|

**Pass criteria:** The skip gate segment must show PF degradation on BOTH P1 and 
P2. If it degrades on P1 but not P2, it's noise.

📌 MID-DOCUMENT REMINDER: The model is FROZEN. Skip gates are pre-entry filters 
applied AFTER the waterfall selects a trade but BEFORE entry. They reduce trade 
count. A useful skip gate removes bad trades without removing good ones — the 
combined PF should INCREASE even though trade count drops.

---

## Step 3: Surface 3 — Adaptive Exit Analysis

⚠️ REMINDER: Surface 3 modifies EXITS, not entry selection. The qualifying trade 
population is identical to v3.2 baseline (minus any skip gate removals from Step 2).

**Question:** Does ray context at time of entry predict how much profit a winning 
trade captures? Can exits be adapted based on ray environment?

### 3a: Winner-only analysis (OBSTACLE RAY focus)

⚠️ The HTF followup (Check 9b) already found observationally that HTF rays 
between entry and T1 cause stalls. This step formalizes the finding on the 
qualifying trade population with P1/P2 protocol.

Filter to WINNING qualifying trades only (separate for Mode 1 and Mode 2).

For each winner, compare:
- Actual profit captured (PnL in ticks)
- Max favorable excursion (MFE)
- Efficiency: PnL / MFE (how much of the available move was captured)
- Obstacle ray distance and streak at entry

Plot (or tabulate) the relationship:
- X: obstacle_ray_dist (binned: ≤30t, 30-60t, 60-100t, >100t, no obstacle)
- Y: median MFE, median PnL, median efficiency

**Hypothesis:** Winners with a strong obstacle ray close ahead have LOWER MFE 
(the ray caps the move). Winners with no obstacle ray have HIGHER MFE. If 
confirmed, adaptive targets can capture this:
- Strong obstacle close ahead → tighten target to obstacle_ray_dist - buffer
- No obstacle ahead → widen target or add trail

### 3b: Loser analysis (BACKING RAY focus, Mode 2)

⚠️ The HTF followup (Check 9a) found that adverse-side HTF ray breaks mostly 
lead to full stop-outs. This step tests whether weak/absent backing rays predict 
Mode 2 losers specifically.

⚠️ CRITICAL: Interpret backing ray results through the Step 1d paradox diagnostic. 
If the paradox was CONFIRMED (high backing streak = worse outcomes for qualifying 
trades), then the hypothesis REVERSES: losers may have HIGHER backing streak (they 
were in congested areas), not lower. Design your analysis to detect the relationship 
in EITHER direction — do not assume the direction before seeing the data.

For Mode 2 losers (ZONEREL exits), check:
- Compare backing_ray_streak distribution: Mode 2 winners vs Mode 2 losers
- Is the relationship monotonic or non-linear?
- Does MAE cluster at backing ray distances? (stop-outs happen when backing fails)
- If paradox confirmed: does high backing streak + dense ray environment predict 
  losers? (congestion → choppy action → stop hit)

⚠️ Mode 1 has 94.8% WR — only ~5 losers on P2. Not enough for loser analysis. 
Focus Mode 2 loser analysis on the ~74 P2 losers (327 trades × 22.7% loss rate).

### 3c: Candidate adaptive exit rules

📌 MODE EXIT PARAMETERS (for reference — these are the BASELINE values being modified):
- Mode 1: FIXED — Stop 190t, Target 60t, Time Cap 120 bars
- Mode 2: ZONEREL — Stop max(1.5×ZW, 120t), Target 1.0×ZW, Time Cap 80 bars

Based on 3a and 3b findings, propose candidate rules. Examples (adapt based on data):

| Rule | Trigger | Modification | Applies To |
|------|---------|-------------|------------|
| Obstacle ceiling | Strong obstacle ray within MODE target distance | Tighten target to min(original_target, obstacle_ray_dist - 5t) | Mode 2 |
| No-obstacle extension A | No 60m+ obstacle ray within 100t | Widen target by 20% | Mode 2 |
| No-obstacle extension B | No 60m+ obstacle ray within 100t | Add trail at 30t (move stop to entry+30t once MFE exceeds 30t) | Mode 2 |
| Backing support stop | Strong backing ray within 40t of entry | ⚠️ CONDITIONAL on Step 1d: if paradox NOT confirmed, tighten stop. If paradox confirmed, this rule is INVALID — do not use. | Mode 2 |
| Dwell bail | Price dwells within 5t of obstacle ray for >10 bars | Close at market | Mode 2 first; test Mode 1 only if Mode 2 result is strong |

⚠️ NOTE: If Step 1d CONFIRMS the paradox (high backing streak = worse outcomes), 
a "congestion skip" rule (high backing streak + dense ray environment → skip trade) 
belongs in Step 2 (skip gate), NOT here in Step 3 (adaptive exits). Go back and 
add it to the Step 2a segment table and test it through the Step 2b-2d pipeline.

⚠️ These are EXAMPLES. Design rules based on what the data actually shows. Do NOT 
force-fit rules that the data doesn't support.

⚠️ CRITICAL: Do NOT apply adaptive exit rules to Mode 1 unless the data strongly 
supports it. Mode 1's FIXED 190t/60t structure won the calibration decisively 
(PF 8.50 vs ZONEREL 7.53 on P1). Modifying Mode 1 exits requires very strong 
evidence.

📌 REMINDER: Any adaptive exit rule must be tested with P1-calibrate / P2-one-shot 
protocol. The rule parameters (distance thresholds, buffer sizes) are calibrated on 
P1, then applied without modification to P2.

### 3d: P1 calibration of adaptive exit rules

⚠️ REMINDER: All adaptive exit rule parameters are calibrated on P1 qualifying 
trades only. P2 is strictly one-shot validation. No P2 peeking.

For each candidate rule:
1. Apply to P1 qualifying trades (Mode 1 or Mode 2 as specified)
2. Re-simulate with modified exits
3. Compare to baseline:

| Rule | Baseline PF @4t | Modified PF @4t | Baseline Trades | Modified Trades | Delta |
|------|----------------|-----------------|-----------------|-----------------|-------|

### 3e: P2 validation of adaptive exit rules

⚠️ Use the same P2 qualifying population and ray context built in Step 2d. 
Do NOT rebuild from scratch — the P2 pipeline was already run for skip gate 
validation. If Step 2d was skipped (no skip gate candidates), run the P2 
pipeline now following the same 5-step process described in Step 2d.

For each rule that improved P1 PF:
1. Apply to P2 qualifying trades with FROZEN rule parameters from P1
2. Compare to P2 baseline:

| Rule | P2 Baseline PF @4t | P2 Modified PF @4t | P2 Trades | Verdict |
|------|-------------------|--------------------|-----------|---------|

**Pass criteria:** P2 PF must improve or hold flat. P2 PF degradation = rule is 
overfit to P1 patterns → reject.

---

## Step 4: Combined Impact Assessment

📌 REMINDER: Compare all results back to the v3.2 baseline (423 P2 trades, PF 4.43 
@4t, Profit/DD 47.6). Any overlay must IMPROVE these numbers on P2 to be viable.

### 4a: Stack validated overlays

If both a skip gate AND an adaptive exit rule pass P2 validation, apply them 
together:

1. Apply skip gate first (removes trades)
2. Apply adaptive exits to remaining trades
3. Compute combined P2 performance:

| Config | P2 Trades | PF @4t | WR% | Profit/DD |
|--------|-----------|--------|-----|-----------|
| v3.2 baseline (no ray overlay) | 423 | 4.43 | — | 47.6 |
| + skip gate only | ? | ? | ? | ? |
| + adaptive exits only | ? | ? | ? | ? |
| + both (stacked) | ? | ? | ? | ? |

### 4b: Implementation complexity check

For each validated overlay, assess C++ implementation complexity:

| Overlay | Data Needed at Runtime | Computation | Complexity |
|---------|----------------------|-------------|------------|
| Skip gate | Ray context at entry time | Lookup nearest ray, check streak/distance | Medium — ZTE already exports ray data |
| Adaptive exits | Same + ongoing ray monitoring | Modify exit targets based on ray context | High — requires real-time ray tracking |

⚠️ An overlay that validates on paper but requires fundamental autotrader 
architecture changes may not be worth implementing for V1. Flag high-complexity 
overlays as "defer to V2."

📌 FINAL SECTION REMINDER: The scoring model is FROZEN. Nothing in this analysis 
changes the 7-feature model, the thresholds, or the waterfall routing. All 
validated overlays are ADDITIONS to the existing deployment spec.

---

## Step 5: Output Report

Produce `ray_conditional_analysis_v32.md` with:

### Section 1: Qualifying Population Summary
- Mode 1 and Mode 2 trade counts (P1 and P2)
- Ray coverage rate (% of qualifying trades with ray context available)
- Distribution of ray features across qualifying trades
- **Step 1d paradox result**: CONFIRMED / NOT CONFIRMED / MODE-DEPENDENT
  - Backing streak vs PF table for each mode
  - How this result affected Surface 2/3 hypothesis interpretation

### Section 2: Surface 2 Results (Skip Gate)
- Segment performance table
- Skip gate candidates with P1 and P2 validation
- Recommended skip gate(s) or "no viable skip gate found"

### Section 3: Surface 3 Results (Adaptive Exits)
- Winner MFE analysis by ray context
- Loser analysis (Mode 2)
- Candidate rules with P1 calibration and P2 validation
- Recommended adaptive exit rule(s) or "no viable adaptive exit found"

⚠️ REMINDER: All adaptive exit rules must pass P1-calibrate / P2-one-shot. 
Rules that improve P1 but degrade P2 are overfit — reject them.

### Section 4: Combined Impact
- Stacked overlay performance on P2
- Implementation complexity assessment
- Net impact on deployment spec

### Section 5: Verdict
One of four outcomes:

⚠️ REMINDER: The model is FROZEN regardless of verdict. These outcomes determine 
what OVERLAY (if any) is added to the v3.2 deployment spec.
- **SKIP GATE VALIDATED**: Specific ray configuration(s) predict losers. Add 
  pre-entry filter to waterfall. Expected trade reduction: X%, expected PF 
  improvement: Y%.
- **ADAPTIVE EXITS VALIDATED**: Ray context improves exit timing. Modify Mode 2 
  (and/or Mode 1) exit rules. Expected PF improvement: Y%.
- **BOTH VALIDATED**: Skip gate + adaptive exits both improve P2 performance. 
  Stack them. Combined impact: X% fewer trades, Y% PF improvement.
- **NO VIABLE OVERLAY**: Ray context does not meaningfully improve qualifying 
  trade outcomes. The v3.2 model captures sufficient information through the 
  7-feature scoring. Ray value is redirected to Surface 4 (ray-only archetype, 
  separate pipeline).

📌 FINAL REMINDER: An outcome of "no viable overlay" is NOT a failure. It means 
the 7-feature model is sufficient and the ray data's primary value lies in the 
standalone ray-only archetype (Surface 4, queued for post-paper-trading). Every 
outcome advances the pipeline.

---

## Output Files

Save to: `c:\Projects\pipeline\shared\archetypes\zone_touch\output\`
- `ray_conditional_analysis_v32.md` — full report
- `qualifying_trades_ray_context_v32.csv` — qualifying trades with ray features 
  and outcomes (reusable dataset)

⚠️ Save script as: 
`c:\Projects\pipeline\shared\archetypes\zone_touch\ray_conditional_analysis_v32.py`
Commit to `feature/ray-integration` branch with message: 
"Add ray conditional analysis on qualifying trades (Analysis B)"

---

## Self-Check Before Submitting

- [ ] Step 0 data inspection completed and qualifying population counts verified
- [ ] Step 1d backing streak paradox diagnostic completed and result stated
- [ ] Surface 2/3 backing ray hypotheses adjusted based on Step 1d outcome
- [ ] Mode 1 and Mode 2 populations match v3.2 expected counts (±5%)
- [ ] 60m+ ray filter applied (no 15m/30m rays)
- [ ] 40t proximity threshold used for ray relevance
- [ ] Obstacle ray 100t search range used (wider than 40t — see note in Step 1b)
- [ ] Coverage gates reported for both backing and obstacle rays
- [ ] qualifying_trades_ray_context_v32.csv saved after Step 1 (regardless of verdict)
- [ ] Ray direction (backing/obstacle) correctly mapped to zone type (demand/supply)
- [ ] Backing/obstacle aggregation matches ray_feature_screening.py methodology
- [ ] Surface 2 segments have mechanistic rationale, not just data mining
- [ ] Surface 2 skip gate tested separately on Mode 1 and Mode 2
- [ ] P2 validation used full pipeline replication (scoring → waterfall → ray context → outcomes)
- [ ] Surface 3 analysis separates winners and losers
- [ ] Surface 3 adaptive exit rules calibrated on P1, validated on P2 (one-shot)
- [ ] Mode 1 exit modifications only proposed with very strong evidence
- [ ] Combined impact computed with stacked overlays
- [ ] Implementation complexity assessed
- [ ] All files saved to correct directories
- [ ] Script committed to feature/ray-integration branch
