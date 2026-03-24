# Ray Analysis A — Incremental Elbow Test

**Purpose:** Determine whether any ray-derived feature adds independent predictive 
power to the existing 7-feature zone touch scoring model. This resolves whether the 
scoring model needs to unfreeze (Surface 1 integration path).

**Branch:** `feature/ray-integration` (off `v3.2-baseline` tag)
**Pipeline version:** 3.2 (warmup-enriched data, bottom-up methodology)
**Date:** 2026-03-24

**Prior ray work (reference — DO NOT re-run, results are valid):**
- `ray_baseline_analysis.md` — observational study (752K interactions, 40t threshold, 
  15m bar close, bounce streak 30.5pp, flip count 12.9pp, dwell decay confirmed)
- `ray_htf_followup.md` — HTF filter validated (60m+ only), freshness overturned 
  (explained by streak), regime stability confirmed P1↔P2
- `ray_feature_screening.md` — ran on OLD 4-feature A-Cal model / 325 P1 touches. 
  Results are STALE. The ray lifecycle computation logic and BACKING/OBSTACLE ray 
  aggregation framework in the script (`ray_feature_screening.py`) are REUSABLE.
- `ray_feature_screening_prompt.md` Section 0 — defines ray lifecycle feature 
  computation from raw data. USE THIS METHODOLOGY for computing ray features.

---

## Context

The v3.2 zone touch model uses 7 features selected via incremental forward build 
on P1 (3,278 touches). The features, in elbow entry order:

| # | Feature | A-Cal Weight | Screening Class |
|---|---------|-------------|-----------------|
| 1 | F10 Prior Penetration | 10.0 | STRONG |
| 2 | F01 Timeframe | 4.91 | STRONG |
| 3 | F05 Session | 4.54 | STRONG |
| 4 | F09 ZW/ATR Ratio | 2.98 | STRONG |
| 5 | F21 Zone Age | 2.95 | STRONG |
| 6 | F13 Close Position | 2.82 | MODERATE |
| 7 | F04 Cascade State | 1.93 | MODERATE |

Three STRONG features (F02 Zone Width, F12 Touch Bar Duration, F08 Prior Rxn Speed) 
did NOT enter the elbow because they showed negative dPF when added — redundant with 
features already included.

⚠️ KEY QUESTION: Do ray features follow the same pattern (strong solo, redundant in 
combination)? Or do they capture genuinely independent information the 7 features miss?

Ray baseline findings (752K interactions, 1,701 rays, stable P1↔P2):
- Bounce streak: 30.5pp spread (STRONGEST signal)
- Flip count: 12.9pp spread
- Session: 14.1pp (ETH rays > RTH rays)
- Dwell time: real-time decay (68.6%→56.0% over 20 bars)
- Freshness: OVERTURNED (explained by streak)
- 60m+ rays only (LTF permanently dropped)
- 40t proximity threshold confirmed

---

⚠️ REMEMBER: The 7-feature model is the baseline. Ray features are tested as 
ADDITIONS at position #8+. Existing features are NOT re-optimized.

## File Locations

```
TOUCH DATA (P1):
  c:\Projects\pipeline\stages\01-data\data\touches\NQ_ZTE_raw_P1.csv

RAY DATA (P1):
  c:\Projects\pipeline\stages\01-data\data\touches\NQ_ray_context_P1.csv
  c:\Projects\pipeline\stages\01-data\data\touches\NQ_ray_reference_P1.csv

SCORED TOUCHES (P1, for qualifying population reference):
  c:\Projects\pipeline\shared\archetypes\zone_touch\output\p1_scored_touches_aeq_v32.csv
  c:\Projects\pipeline\shared\archetypes\zone_touch\output\p1_scored_touches_bzscore_v32.csv

EXISTING MODEL:
  c:\Projects\pipeline\shared\archetypes\zone_touch\output\feature_config_v32.json
  c:\Projects\pipeline\shared\archetypes\zone_touch\output\scoring_model_aeq_v32.json
  c:\Projects\pipeline\shared\archetypes\zone_touch\output\scoring_model_bzscore_v32.json

EXISTING PIPELINE SCRIPTS:
  c:\Projects\pipeline\shared\archetypes\zone_touch\feature_engine.py
  c:\Projects\pipeline\shared\archetypes\zone_touch\zone_touch_simulator.py
  c:\Projects\pipeline\shared\archetypes\zone_touch\feature_evaluator.py
  c:\Projects\pipeline\shared\archetypes\zone_touch\model_building_v32.py
  c:\Projects\pipeline\shared\archetypes\zone_touch\ray_feature_screening.py

⚠️ INSPECT these existing scripts BEFORE writing new code. The incremental build 
methodology and simulation parameters must match exactly.

P2 VALIDATION DATA:
  c:\Projects\pipeline\stages\01-data\data\touches\NQ_ZTE_raw_P2.csv
  c:\Projects\pipeline\stages\01-data\data\touches\NQ_ray_context_P2.csv
  c:\Projects\pipeline\stages\01-data\data\touches\NQ_ray_reference_P2.csv
  c:\Projects\pipeline\shared\archetypes\zone_touch\output\p1_scored_touches_aeq_v32.csv
```

---

## Step 0: Data Inspection (MANDATORY FIRST STEP)

Before writing ANY code, inspect the data files and report their schemas.

```python
import pandas as pd

# 1. Touch data
zte = pd.read_csv(r'c:\Projects\pipeline\stages\01-data\data\touches\NQ_ZTE_raw_P1.csv')
print("ZTE P1 columns:", list(zte.columns))
print("ZTE P1 shape:", zte.shape)
print(zte.head(3))

# 2. Ray context
ray_ctx = pd.read_csv(r'c:\Projects\pipeline\stages\01-data\data\touches\NQ_ray_context_P1.csv')
print("\nRay context P1 columns:", list(ray_ctx.columns))
print("Ray context P1 shape:", ray_ctx.shape)
print(ray_ctx.head(3))

# 3. Ray reference — ⚠️ Check join key between ray data and touch data
ray_ref = pd.read_csv(r'c:\Projects\pipeline\stages\01-data\data\touches\NQ_ray_reference_P1.csv')
print("\nRay reference P1 columns:", list(ray_ref.columns))
print("Ray reference P1 shape:", ray_ref.shape)
print(ray_ref.head(3))

# 4. Feature config
import json

# ⚠️ The feature_config defines the frozen 7-feature elbow. Ray candidates extend FROM this.
with open(r'c:\Projects\pipeline\shared\archetypes\zone_touch\output\feature_config_v32.json') as f:
    fc = json.load(f)
print("\nFeature config keys:", list(fc.keys())[:10])

# 5. Existing screening script (check how ray features were defined)
with open(r'c:\Projects\pipeline\shared\archetypes\zone_touch\ray_feature_screening.py') as f:
    content = f.read()
print("\nray_feature_screening.py first 100 lines:")
print('\n'.join(content.split('\n')[:100]))
```

⚠️ STOP after this step. Report the schemas before proceeding. The join logic 
in Step 1 depends on knowing the exact column names and key relationships between 
these files.

**If running as a single session:** Print the schema output above, review it 
yourself, and only proceed to Step 1 once you have confirmed the join keys 
exist and the data shapes match expectations (P1 ~3,278 touches, ray_context 
has many-to-one relationship with touches, ray_reference has ray creation events). 
If schemas don't match expectations, STOP and report the discrepancy.

**If running as a multi-turn session:** Post the output and wait for confirmation.

---

## Step 1: Build Ray Feature Candidates

After data inspection, join ray context to touch data. The join key is likely a 
timestamp + bar index or a touch ID linking to ray proximity at touch time.

⚠️ CRITICAL: Use 60m+ rays ONLY. Filter out 15m and 30m ray timeframes before 
any feature computation. The LTF ray drop is a frozen decision from ray baseline.

⚠️ CRITICAL: 40t proximity threshold. Only rays within 40 ticks of the touch 
zone edge are "relevant" ray context.

⚠️ REUSE METHODOLOGY: The existing `ray_feature_screening.py` and 
`ray_feature_screening_prompt.md` Section 0 define how to compute ray lifecycle 
features from raw data (bounce streak, flip count, dwell bars, decay magnitude, 
approach velocity, close type, etc.). Inspect `ray_feature_screening.py` and 
REUSE its ray lifecycle computation. Do NOT rewrite from scratch.

The existing framework defines two aggregation modes per touch:
- **BACKING RAY**: Nearest 60m+ ray AT or BEHIND entry (stop side). For entry 
  scoring — does the backing S/R structure predict touch quality?
- **OBSTACLE RAY**: Nearest 60m+ ray AHEAD of entry (profit side). For trade 
  management — does what's ahead predict trade outcome?

For the INCREMENTAL ELBOW test, use BACKING RAY aggregation. The question is 
whether the backing ray context adds independent scoring power beyond F10-F04. 
Obstacle ray features are deferred to Analysis B (trade management).

Define these candidate ray features for each P1 touch (BACKING RAY):

| Candidate | Definition | Expected Source |
|-----------|-----------|-----------------|
| R1: Backing Bounce Streak | Bounce streak of nearest 60m+ backing ray | ray lifecycle computation |
| R2: Backing Flip Count | Flip count of nearest 60m+ backing ray | ray lifecycle computation |
| R3: Backing Ray Distance | Distance (ticks) from entry to backing ray | ray_context or computed |
| R4: Backing Ray Decay | Decay magnitude (recent/early bounce ratio) of backing ray | ray lifecycle computation |
| R5: Backing Ray Age | Age in bars of backing ray at touch time | ray_reference + bar data |
| R6: Ray Density (backing side) | Count of 60m+ rays within 50t behind entry | ray_context |
| R7: Cross-TF Confluence | Number of TFs with rays within 20t of backing ray | ray lifecycle computation |

⚠️ NOTE ON R5: Ray freshness was OVERTURNED in the HTF followup — fresh rays 
performed worse, fully explained by bounce streak (fresh rays have zero confirmed 
bounces by definition). R5 is included for completeness but EXPECTED to be redundant 
with R1 (Backing Bounce Streak). If R5 shows STRONG solo, verify it's not just 
an inverse proxy for streak before advancing to Step 3.

⚠️ IMPORTANT: Adapt these definitions to match the actual column names and 
computation methods found in `ray_feature_screening.py` and Step 0 inspection. 
If the existing script already computes some of these, reuse directly. If the 
ray data doesn't support a candidate, note it and skip that candidate. Do NOT 
fabricate columns.

For touches with NO 60m+ backing ray within proximity, assign NaN (not zero). 
The model handles NaN via the "NA" bin pattern used for F10.

⚠️ COVERAGE GATE: After computing ray features, report the coverage rate — what 
% of P1 touches have at least one 60m+ backing ray within 40t? If coverage is 
below 30% (fewer than ~980 touches with ray data), the screening has insufficient 
power. In that case, widen the proximity threshold to 60t and re-report. If still 
below 30%, verdict is INSUFFICIENT DATA — do not proceed to Steps 2-4.

📌 REMINDER: This analysis tests BACKING RAY features only (entry scoring, 
Surface 1). OBSTACLE RAY features (trade management, Surfaces 2-3) are tested 
in Analysis B. The incremental elbow test answers: does the S/R structure 
behind the entry add information the 7 features miss?

**Save the enriched touch dataset immediately after computation:**
Save to `c:\Projects\pipeline\shared\archetypes\zone_touch\output\ray_elbow_candidates_v32.csv`
This file is needed by Analysis B regardless of this analysis's verdict (ELBOW ENTRY, 
REDUNDANT, or INSUFFICIENT DATA). Do NOT defer this save to Step 5.

---

## Step 2: Solo Screening of Ray Candidates

⚠️ REMINDER: All ray features use 60m+ rays only with 40t proximity threshold. 
These filters were applied in Step 1. Verify they are still in effect.

For each ray candidate (R1-R7), compute the independent R/P spread using the same 
methodology as the original feature screening:

1. Bin each ray feature into 3 bins (Low/Mid/High) using P1 terciles
2. For each bin, compute median R/P ratio at a reference exit (use the same 
   baseline exit as original screening — check `feature_evaluator.py` or 
   `feature_screening_v32.py` for the exact parameters)
3. Compute R/P spread = max(bin R/P) - min(bin R/P)

⚠️ CHECK: The original screening used a specific simulation approach (likely 
zone_touch_simulator.py with baseline exit params). Use the SAME approach. Do NOT 
invent a new simulation method. Inspect the existing scripts to match methodology.

Classify each ray candidate using the same thresholds as `feature_screening_v32.py`. 
If the script uses different cutpoints than below, use the script's values:
- R/P spread ≥ 0.40: STRONG
- R/P spread 0.20-0.39: MODERATE  
- R/P spread < 0.20: WEAK

Report the results table:

| Candidate | R/P Spread | Class | Mechanism | Max |r| with Existing 7 |
|-----------|-----------|-------|-----------|---------------------|

⚠️ CRITICAL: For each STRONG or MODERATE ray candidate, compute Pearson/Spearman 
correlation with ALL 7 existing features (F10, F01, F05, F09, F21, F13, F04). 
F10 (Prior Penetration, R/P spread 1.371) is the most likely redundancy source, 
but backing ray attributes could also correlate with F21 (Zone Age — young zones 
may have fewer established rays) or F04 (Cascade — zones with prior breaks may 
have broken rays nearby). If a ray feature correlates >0.5 with ANY existing 
feature, it's likely redundant — flag but still test in Step 3.

📌 REMINDER: We expect ray features may be STRONG solo but redundant in combination, 
following the pattern of F02, F08, F12. The correlation check is the early warning.

---

## Step 3: Incremental Build Extension

This is the critical test. Take the existing 7-feature model as frozen baseline 
and attempt to extend the incremental build.

**Methodology** (must match `model_building_v32.py` exactly):

1. Load the existing incremental build state after feature #7 (F04). 
   If `model_building_v32.py` does not serialize intermediate states, reconstruct 
   the 7-feature baseline by running the incremental build with the frozen 7 features 
   (using the bin boundaries and weights from `feature_config_v32.json` and 
   `scoring_model_aeq_v32.json`). The resulting PF must match the value reported in 
   `incremental_build_clean_v32.md` — if it doesn't, STOP and investigate.
2. Compute the baseline dPF at position #7 (this should match the original 
   incremental build report — cross-check against `incremental_build_clean_v32.md`)
3. For each ray candidate that passed solo screening (STRONG or MODERATE):
   a. Add it as candidate #8 to the existing 7-feature model
   b. Re-run the simulation/evaluation with 8 features
   c. Compute dPF = PF(8 features) - PF(7 features)
   d. If dPF > 0, the candidate ENTERS the elbow
   e. If dPF ≤ 0, the candidate is REDUNDANT

⚠️ CRITICAL: Use the SAME evaluation methodology as the original incremental build. 
This means the same simulation parameters, the same P1 population (all 3,278 touches), 
the same PF computation method, and the same cost basis (check model_building_v32.py — 
likely @3t for P1 calibration). Inspect `model_building_v32.py` to replicate exactly.

⚠️ CRITICAL: Do NOT re-optimize the existing 7 features. They are FROZEN. Only the 
ray candidate's bins/weights are calibrated on P1. The existing bin boundaries and 
weights for F10/F01/F05/F09/F21/F13/F04 do not change.

If multiple ray candidates show positive dPF at position #8, test them in order of 
dPF magnitude (largest first), then test whether a second ray candidate adds value 
at position #9.

📌 REMINDER: The incremental build has diminishing returns. By position #7, the 
marginal dPF is already small (F04 weight is only 1.93). A ray feature needs to 
beat that bar to justify model expansion.

---

## Step 4: P2 Validation (only if a ray feature enters the elbow)

⚠️ ONLY execute this step if Step 3 found a ray candidate with positive dPF.

If no candidate entered the elbow → SKIP to Step 5 (Redundancy Report).

If a ray candidate entered:
1. Apply the same ray feature computation to P2 data (NQ_ZTE_raw_P2.csv + 
   NQ_ray_context_P2.csv + NQ_ray_reference_P2.csv)
2. Using the P1-frozen bin boundaries and weights (including the new ray feature), 
   score all P2 touches
3. Re-run the waterfall simulation on P2:
   - A-Eq with 8 features: max score changes from 70 (7×10) to 80 (8×10). 
     Recalibrate threshold on P1 using the same optimization method as the 
     original Prompt 2 segmentation (inspect `prompt2_segmentation_v32.py`). 
     Starting point: ~65% of 80 = 52.0. The optimal threshold may differ — 
     use whatever P1 optimization produces. Freeze the result for P2.
   - B-ZScore with 8 features: refit StandardScaler on P1 with 8 features, 
     freeze mean/std, apply to P2. Threshold stays 0.50.
4. Compare P2 results to v3.2 baseline:

| Metric | v3.2 (7 features) | v3.3 candidate (8 features) | Delta |
|--------|-------------------|----------------------------|-------|
| A-Eq ModeA P2 PF @4t | 6.26 | ? | ? |
| A-Eq ModeA P2 trades | 96 | ? | ? |
| B-ZScore RTH P2 PF @4t | 4.25 | ? | ? |
| B-ZScore RTH P2 trades | 327 | ? | ? |
| Combined PF @4t | 4.43 | ? | ? |
| Combined trades | 423 | ? | ? |

**Pass criteria:** The 8-feature model must IMPROVE combined PF @4t on P2 without 
reducing trade count by >20%. If PF improves but trades drop significantly, the ray 
feature is acting as a filter (→ redirect to Analysis B, Surface 2) not a scoring 
enhancement.

⚠️ REMINDER: P2 is one-shot holdout. No recalibration on P2 data. All thresholds 
and bin boundaries frozen from P1.

---

## Step 5: Output Report

Produce `ray_elbow_test_v32.md` with:

### Section 1: Data Join Summary
- How ray data was joined to touch data
- Ray coverage rate (% of P1 touches with at least one 60m+ ray within proximity)
- Any data quality issues

### Section 2: Solo Screening Results
- Table of all ray candidates with R/P spread, class, and max |r| with existing 7 features
- Note which candidates were STRONG/MODERATE solo

### Section 3: Incremental Build Results
- Table showing dPF for each candidate at position #8
- Clear statement: did any ray feature ENTER the elbow? YES/NO

### Section 4: Verdict

⚠️ The verdict determines the pipeline's next step. State it unambiguously.

One of three outcomes:
- **ELBOW ENTRY**: Ray feature [X] entered the elbow with dPF = [Y]. Model 
  unfreezes → proceed to P2 validation, then mode classification on modified model.
- **REDUNDANT**: All ray features showed negative dPF. The 7-feature model already 
  captures the signal. Model stays frozen. → Redirect ray value to Analysis B 
  (Surfaces 2 and 3).
- **INSUFFICIENT DATA**: Ray coverage too sparse for reliable testing. → Note 
  minimum coverage needed and defer.

### Section 5 (if applicable): P2 Validation Results
- Only if a ray feature entered the elbow
- Comparison table vs v3.2 baseline
- Pass/fail against criteria

📌 FINAL REMINDER: This analysis determines whether the v3.2 scoring model changes. 
If the verdict is REDUNDANT (expected), the model stays frozen and ray value is 
pursued through trade filters and adaptive exits (Analysis B). If the verdict is 
ELBOW ENTRY, the model unfreezes and mode classification must wait for the new 
model to stabilize. Either outcome is informative — there is no failure case.

---

## Output Files

Save to: `c:\Projects\pipeline\shared\archetypes\zone_touch\output\`
- `ray_elbow_test_v32.md` — full report
- `ray_elbow_candidates_v32.csv` — BACKING ray feature values per P1 touch (reusable 
  by Analysis B for cross-reference; Analysis B computes OBSTACLE features separately)

⚠️ Save script as: `c:\Projects\pipeline\shared\archetypes\zone_touch\ray_elbow_test_v32.py`
Commit to `feature/ray-integration` branch with message: 
"Add ray incremental elbow test (Analysis A)"

---

## Self-Check Before Submitting

- [ ] Step 0 data inspection completed and schemas reported
- [ ] Existing ray_feature_screening.py inspected and lifecycle computation reused
- [ ] BACKING RAY aggregation used (not obstacle ray — that's Analysis B)
- [ ] 60m+ ray filter applied (no 15m/30m rays)
- [ ] 40t proximity threshold used
- [ ] NaN assigned for touches with no qualifying ray (not zero)
- [ ] Coverage gate checked (≥30% of P1 touches have backing ray data)
- [ ] ray_elbow_candidates_v32.csv saved after Step 1 (regardless of verdict)
- [ ] Solo screening uses same methodology as original feature_screening_v32.py
- [ ] Incremental build uses same methodology as model_building_v32.py
- [ ] Existing 7 feature bins/weights NOT modified
- [ ] Correlation with ALL 7 existing features computed for STRONG/MODERATE candidates
- [ ] P2 validation is one-shot (no P2 recalibration)
- [ ] All files saved to correct directories
- [ ] Script committed to feature/ray-integration branch
