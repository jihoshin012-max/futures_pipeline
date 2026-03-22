# NQ Zone Touch — Clean Data Pipeline: Prompt 1a (Feature Screening)

> **Version:** 3.1
> **Date:** 2026-03-20
> **Scope:** Feature computation (P1 only), single-feature R/P screening, mechanism validation
> **Prerequisite:** Prompt 0 outputs (`baseline_report_clean.md` + `zone_lifecycle.csv`) + data prep files
> **Next:** Review screening results. Proceed to Prompt 1b (Model Building) unless zero STRONG + zero SBB-MASKED features AND baseline PF < 1.0.

---

## Three Rules (non-negotiable — apply to ALL prompts)

1. **P1 only for calibration.** Every weight, bin edge, parameter, threshold from P1 data only (P1a + P1b combined). P2a, P2b are not used.
2. **No iteration on holdout data.** P2a/P2b are tested exactly once (Prompt 3). No adjustments after seeing results.
3. **All features computable at trade entry time.** No post-touch data for the current touch. Entry is on the NEXT BAR OPEN after the touch bar closes.

⚠️ Reminder: Rules 1–3 apply to every step. P2 data was used in Prompt 0 (baseline) only. From this prompt onward, P1 only.

---

## Inputs

### From Prompt 0:

| File | Purpose |
|------|---------|
| `baseline_report_clean.md` | Baseline PF anchor (MEDIAN cell @3t with 95% CI), population R/P at 4 horizons, all structural splits. The reference for everything in this prompt. |
| `zone_lifecycle.csv` | Zone birth/death table built from ALL periods. Used by expansion features 21–25 to determine zone age, active zone set, break events at each touch time. Do NOT rebuild — load directly. |

### From Data Prep:

| File | Purpose |
|------|---------|
| `NQ_merged_P1a.csv` | P1a touches — concatenated with P1b for calibration |
| `NQ_merged_P1b.csv` | P1b touches — concatenated with P1a for calibration |
| `NQ_bardata_P1.csv` | Rotational bar data for P1 — feature computation |
| `period_config.json` | Date boundaries and touch counts |

⚠️ **Concatenate P1a + P1b** into one P1 dataset at load time. **Filter out touches with RotBarIndex < 0** (invalid bar mapping — same filter applied in Prompt 0). All work in this prompt uses the filtered P1 set.

⚠️ Read `baseline_report_clean.md` first. Extract and print:
- Baseline PF anchor (median cell PF @3t with CI)
- **Median cell exit parameters: stop, target, time_cap** (needed for confirmation simulation in Step 4.6)
- Population R/P @60bars
- SBB split (NORMAL vs SBB PF)
- Baseline verdict (LOW/MODERATE/HIGH)

Every result below is compared against these.

---

## Step 3: Feature Computation (P1 only)

Compute all 24 features (19 core + 5 expansion) for every P1 touch.

⚠️ Reminder: we are on P1 only (P1a + P1b concatenated, 4,701 touches). Baseline PF anchor = [X] from Prompt 0.

#### Features 1–14 (from merged CSV + rotational bar data)

**Feature 1: Timeframe** — SourceLabel as a CATEGORICAL feature. Use natural categories: 15m, 30m, 60m, 90m, 120m, 240m, 360m, 480m, 720m. Do NOT impose ordinal weights — Prompt 0 showed 30m outperforms 720m, which contradicts the prior assumption that higher TF = better. Let R/P screening determine which TF groups separate.

**Feature 2: Zone Width** — ZoneWidthTicks column (pre-computed)

**Feature 3: DROPPED** — VP Ray Binary (HasVPRay = 1 for 100% — zero variance)

**Feature 4: Cascade State** — CascadeState column: PRIOR_HELD / NO_PRIOR / PRIOR_BROKE / UNKNOWN. Treat UNKNOWN as NO_PRIOR.

**Feature 5: Session** — 4 classes from DateTime: PreRTH (<9:30 ET), OpeningDrive (9:30–11:00), Midday (11:00–14:00), Close (14:00–17:00). Touches outside 6:00–17:00 classified as Overnight (5th class if present).

**Feature 6: Approach Velocity** — ApproachVelocity column

**Feature 7: Approach Deceleration** — mean(H-L for bars -3 to -1) / mean(H-L for bars -10 to -8) relative to touch bar

**Feature 8: Prior Touch Reaction Speed** — RxnBar_30 from prior touch (seq-1) on same zone. Null for seq=1 → neutral.

**Feature 9: Zone Width / ATR Ratio** — zone width in points / ATR at RotBarIndex

**Feature 10: Prior Touch Penetration** — Penetration from prior touch (seq-1) on same zone. Null for seq=1 → neutral.

⚠️ Reminder: all features from the touch bar or earlier. Nothing from the bar after the touch. P1 only.

**Feature 11: Touch Bar Delta Divergence** — (AskVol - BidVol) on touch bar. Negate for supply.

**Feature 12: Touch Bar Duration** — timestamp gap between touch bar and prior bar (seconds)

**Feature 13: Touch Bar Close Position** — Demand: (Last-Low)/(High-Low). Supply: (High-Last)/(High-Low).

**Feature 14: Average Order Size** — Volume / NumTrades on touch bar

#### Features 15–20 (from rotational zigzag/regime/VP Ray data)

**Feature 15: ZZ Swing Regime** — Median of 20 most recent non-zero ZZ Line Length values. Count completed swings backward, not bars.

**Feature 16: ZZ Oscillator at Touch** — Raw ZZ Oscillator value at RotBarIndex

**Feature 17: ATR Regime** — Rolling percentile rank of current ATR vs trailing 500 bars

**Feature 18: Channel Confluence** — Count of 6 channel boundaries within N ticks of zone edge. Calibrate N on P1 (test 20, 50, 100 ticks).

⚠️ Reminder: P1 only. Baseline PF anchor = [X] from Prompt 0. All feature computation uses P1-frozen parameters.

**Feature 19: VP Ray Consumption** — Derived from touch history: for seq ≥ 2, check if any prior touch on same zone penetrated to VPRayPrice. If yes → VP_RAY_CONSUMED, else → VP_RAY_INTACT. Seq 1 always INTACT. Demand: touch low ≤ VPRayPrice (touch low = TouchPrice - Penetration × 0.25). Supply: touch high ≥ VPRayPrice (touch high = TouchPrice + Penetration × 0.25).

**Feature 20: Distance to Consumed VP Ray** — For VP_RAY_CONSUMED touches: abs(TouchPrice - VPRayPrice) / 0.25 (ticks). Null for INTACT and seq=1 → neutral.

#### Expansion Features 21–25 (derived from zone interaction data)

⚠️ **EXPANSION FEATURES:** Computed and screened alongside the core 19. Clearly labeled so that if the core 19 produce a strong model, these can be noted as "screened but not needed" without requiring C++ implementation. If any classify as STRONG, they join the incremental build in Prompt 1b. Features 21–25 all use `zone_lifecycle.csv` from Prompt 0 (birth/death/active zone set). Do NOT rebuild the lifecycle — load it directly.

**Feature 21: Zone Age** — Number of bars between zone birth and the current touch. Use `birth_datetime` from `zone_lifecycle.csv` for this ZoneID, convert to bar count via RotBarIndex difference vs the touch bar. Older zones have survived longer without breaking.

**Feature 22: Recent Break Rate** — Number of zone death events (from `zone_lifecycle.csv`, any TF, any direction) in the trailing 500 bars before this touch, divided by total active zones in that window. High break rate = trending/momentum market. Low break rate = range-bound.

**Feature 23: Cross-TF Confluence** — Count of active zones from OTHER timeframes within 200 ticks of this zone's edge, same direction. A 30m demand zone with a 120m demand zone 50 ticks below has cross-TF confluence. Computed from ZonePrice values in the active zone set at touch time.

⚠️ Reminder: P1 only. All expansion features computable at entry time. Baseline anchor = [X] from Prompt 0.

**Feature 24: Nearest Same-Direction Zone Distance** — Distance (in ticks) to the nearest active same-direction zone. For demand: nearest demand zone below. For supply: nearest supply zone above. Small distance = dense cluster / layered support. Large distance = isolated zone. Null if no other same-direction zone is active → set to max observed value on P1.

**Feature 25: Price-Level Break History** — Fraction of all zones in `zone_lifecycle.csv` created within ±500 ticks of this zone's price that have died (death_cause != ALIVE), across all TFs, considering only zones born before this touch time. High fraction = this price level is a transit zone. Low fraction = price level has strong historical support/resistance.

Print: feature distributions, correlation matrix (flag |r| > 0.7), 5 sample rows, VP Ray Consumption distribution + mean Reaction per category, Feature 20 distribution for consumed touches, null rates for features 8/10/19/20/21/24.

⚠️ Checkpoint: confirm all 24 features (19 core + 5 expansion) computable at entry time. State explicitly.

---

## Step 4: Single-Feature Screening (P1 only)

**Purpose:** Test each feature INDEPENDENTLY — no other features involved. A feature that separates good from bad touches on its own is likely structural. A feature that only helps in combination is likely curve fitting.

**Why R/P ratio instead of simulated PF:** Screening asks a touch-level question: "does this feature identify touches where price reacts favorably?" Using PF under a specific exit biases toward features that work with that exit structure. R/P ratio measures touch quality directly, with no exit dependency. Multi-horizon R/P adds time-awareness: a feature that separates at 30, 60, AND 120 bars is robust; one that only separates at 360 bars is a slow signal most exits can't capture.

⚠️ Reminder: P1 data only. No simulation needed for primary screening — R/P uses columns already in the merged CSV. Baseline median R/P = [X] from Prompt 0.

For each of the 24 features (19 core + 5 expansion):

**1. Bin P1 touches** by this feature only:
   - Continuous features: tercile split (P33/P67 from P1)
   - Categorical features (Timeframe, Cascade, Session, VP Ray Consumption): use natural categories

**2. Compute R/P ratio per bin at multiple horizons:**

⚠️ **Do NOT use `RxnBar_30`, `PenBar_30`, etc. — these are bar indices, not tick values.** Use the horizon R/P computation method defined in Prompt 0:
- For each touch: entry bar = RotBarIndex + 1, entry price = Open of entry bar
- Reaction at N bars: max favorable excursion in next N bars (ticks). Demand: (max High - entry) / 0.25. Supply: (entry - min Low) / 0.25.
- Penetration at N bars: max adverse excursion in next N bars (ticks). Demand: (entry - min Low) / 0.25. Supply: (max High - entry) / 0.25.
- Full observation: use `Reaction` and `Penetration` columns from merged CSV (correct).

For each bin, compute:
- R/P at 30 bars: mean(Reaction@30) / mean(Penetration@30)
- R/P at 60 bars: mean(Reaction@60) / mean(Penetration@60)
- R/P at 120 bars: mean(Reaction@120) / mean(Penetration@120)
- R/P full observation: mean(Reaction) / mean(Penetration)

⚠️ **Floor rule:** If mean penetration for a bin at any horizon is < 1.0 tick, set denominator to 1.0 to avoid inflated R/P from near-zero penetration. Report floored bins as such.

Also report per bin: touch count, mean Reaction, mean Penetration.

**3. Compute separation metrics per horizon:**

For each horizon:
- **R/P Spread:** best-bin R/P minus worst-bin R/P
- **Reaction Spread:** best-bin mean Reaction minus worst-bin mean Reaction
- **Statistical significance:** Mann-Whitney U test comparing Reaction distributions between best and worst bins (p-value)
- **Effect size:** Cohen's d between best and worst bins

⚠️ Reminder: each feature tested INDEPENDENTLY. P1 only. Compare separation against baseline R/P from Prompt 0.

**4. Multi-horizon consistency check:**

Count how many horizons (30, 60, 120, full) show the same best bin with R/P spread > 0.2:
- **4/4 horizons consistent:** Feature separates at all timescales. Very strong structural signal.
- **3/4 horizons consistent:** Feature separates at most timescales. Strong.
- **2/4 horizons consistent:** Feature is timescale-dependent. Moderate — note which horizons work.
- **1/4 or 0/4:** Feature separation is fragile or nonexistent.

**5. Classify each feature:**

- **STRONG SIGNAL:** R/P spread > 0.3 at ≥ 3 horizons AND MWU p < 0.05 at ≥ 2 horizons. High confidence it's structural.
- **MODERATE SIGNAL:** R/P spread > 0.2 at ≥ 2 horizons OR MWU p < 0.10 at ≥ 2 horizons. Moderate confidence.
- **WEAK SIGNAL:** R/P spread < 0.2 at most horizons AND p > 0.10. No independent separation. Higher overfit risk.
- **INVERTED:** worst bin outperforms best bin at ≥ 3 horizons. Feature works opposite to expectations — investigate.

⚠️ **No exit structure is chosen for screening.** The R/P metric is exit-independent. This ensures feature rankings aren't biased by the exit choice. Exit optimization happens later in Prompt 1b (incremental build) and Prompt 2 (segmentation).

**5b. SBB-masked secondary screening (WEAK and MODERATE features only):**

⚠️ **Why this matters:** SBB touches are 34% of the population at PF 0.37. Any feature correlated with SBB probability will show large R/P spreads on the full population — it's partly measuring SBB separation, not touch quality. But a feature that separates good from bad touches WITHIN the NORMAL population may show small R/P spreads on the full population because SBB noise dilutes the signal. That feature gets classified WEAK and enters the incremental build last, even though it could be the most useful feature once SBB is already filtered.

For each feature classified WEAK or MODERATE in the primary classification above (Step 4, sub-step 5):
1. Filter to NORMAL-only touches (SBB_Label = NORMAL) on P1
2. Recompute R/P spread at **all 4 horizons** (30, 60, 120, full) on this NORMAL-only population
3. Recompute MWU p-values at all 4 horizons on NORMAL-only
4. If the feature would reclassify as STRONG under the same thresholds (R/P spread > 0.3 at ≥ 3 horizons AND MWU p < 0.05 at ≥ 2): flag it as **SBB-MASKED**

SBB-MASKED features enter the incremental build in Prompt 1b AFTER all STRONG features but BEFORE other MODERATE/WEAK features. They represent real within-population separation that was hidden by the SBB noise floor.

Print: "SBB-MASKED features (WEAK/MODERATE on full pop, STRONG on NORMAL-only): [list or NONE]."

**6. Confirmation simulation (STRONG and SBB-MASKED features only):**

For features classified as STRONG or SBB-MASKED, run a single confirmation simulation using the **median cell exit from Prompt 0** to verify the R/P separation translates to PF separation under realistic trading conditions. For STRONG features: simulate on full P1 population. For SBB-MASKED features: simulate on NORMAL-only P1 population (consistent with how they were screened). Report PF @3t per bin.

If a STRONG feature shows clear R/P separation but weak PF separation under simulation: the feature identifies good touches but the no-overlap filter or time cap prevents capturing the edge. Note this — it may work with different exits in Prompt 2.

⚠️ Reminder: P1 only. Baseline anchor = [X]. This confirmation simulation uses P1 bar data only.

Print single-feature screening table:

| Rank | Feature | Best Bin R/P @60 | Worst Bin R/P @60 | R/P Spread @60 | Horizons Consistent | MWU p @60 | Cohen's d | Classification | N (best/worst) |
|------|---------|-----------------|------------------|----------------|--------------------|-----------| ----------|---------------|-----------------|
| 1 | ? | ? | ? | ? | ?/4 | ? | ? | ? | ? |
| 2 | ? | ? | ? | ? | ?/4 | ? | ? | ? | ? |
| ... | | | | | | | | | |
| 19 | ? | ? | ? | ? | ?/4 | ? | ? | ? | ? |
| 21 (EXP) | ? | ? | ? | ? | ?/4 | ? | ? | ? | ? |
| 22 (EXP) | ? | ? | ? | ? | ?/4 | ? | ? | ? | ? |
| 23 (EXP) | ? | ? | ? | ? | ?/4 | ? | ? | ? | ? |
| 24 (EXP) | ? | ? | ? | ? | ?/4 | ? | ? | ? | ? |
| 25 (EXP) | ? | ? | ? | ? | ?/4 | ? | ? | ? | ? |

(Show 60-bar horizon as primary column. Full multi-horizon table in `feature_screening_clean.md`.)

**If any SBB-MASKED features exist, print a separate NORMAL-only table:**

| Rank | Feature | Full-Pop Class | NORMAL-only R/P Spread @60 | NORMAL-only Horizons | NORMAL-only MWU p @60 | N (NORMAL best/worst) |
|------|---------|---------------|---------------------------|---------------------|----------------------|----------------------|
| ? | ? | WEAK/MODERATE | ? | ?/4 | ? | ? |

This shows WHY the feature was upgraded — the full-pop table alone would make the classification look unjustified.

Print: "STRONG SIGNAL features: [list] — consistent across [N] horizons."
Print: "SBB-MASKED features: [list or NONE]."
Print: "WEAK SIGNAL features: [list]."

⚠️ Reminder: P1 only. No other period data used. Baseline median R/P = [X] from Prompt 0.

---

## Step 5: Feature Mechanism Validation (P1 only — STRONG, SBB-MASKED, and MODERATE features only)

Run mechanism validation tests on features classified as STRONG, SBB-MASKED, or MODERATE in Step 4. WEAK features are tested but results are informational.

⚠️ **For SBB-MASKED features:** Run all three mechanism tests on NORMAL-only P1 touches (consistent with how they were screened). Their signal was demonstrated on the NORMAL population, so stability and regime independence must be verified on the same population.

**Test 1: Temporal Stability** — Split P1 in half by date. Compute R/P spread (at 60-bar horizon) per feature on each half independently. Stable = same sign and within 2× magnitude.

**Test 2: Regime Independence** — Split P1 by ATR regime (Feature 17 median). Compute R/P spread (at 60-bar horizon) within each regime. Independent = same sign in both.

⚠️ Reminder: the halves and regime splits are within P1, not across periods. P1 only. For SBB-MASKED features, filter to NORMAL-only before splitting. Baseline anchor = [X].

**Test 3: Monotonicity** — For 3-bin features, check consistent ordering of Reaction across bins. Binary features exempt.

⚠️ Zone width drift warning: Compare Feature 2 (Zone Width) and Feature 9 (ZW/ATR) bin edges. Report whether the ratio absorbs the width drift observed in the data prep report (P1 median ~170t vs P2b median=280t — zone widths increase over time).

**Mechanism Classification:**

| Feature | Step 4 Class | Temporal | Regime | Monotonic | Final Classification |
|---------|-------------|----------|--------|-----------|---------------------|
| ? | STRONG | ? | ? | ? | STRUCTURAL / LIKELY / STATISTICAL |
| ? | SBB-MASKED | ? | ? | ? | STRUCTURAL / LIKELY / STATISTICAL |
| ... | | | | | |

Rules:
- **STRUCTURAL:** STRONG or SBB-MASKED signal + passes 2/3 mechanism tests (or 3/3)
- **LIKELY STRUCTURAL:** MODERATE signal + passes 2/3, OR STRONG/SBB-MASKED + passes 1/3
- **STATISTICAL ONLY:** Fails signal screening OR passes ≤ 1/3 mechanism tests
- **DROPPED:** Feature 3 (constant)

⚠️ **This step does NOT remove features from the model.** It classifies them for deployment confidence. All 24 features proceed to Prompt 1b.

---

## Required Outputs (saved for Prompt 1b)

| Output File | Contents |
|-------------|----------|
| `feature_screening_clean.md` | Single-feature screening table, classifications (STRONG/SBB-MASKED/MODERATE/WEAK), ranked by R/P spread at 60-bar horizon. SBB-MASKED features include NORMAL-only R/P detail. Full multi-horizon detail included. |
| `feature_mechanism_validation.md` | Temporal stability, regime independence, monotonicity + STRUCTURAL/LIKELY/STATISTICAL per feature |
| `p1_features_computed.csv` | P1 touches (P1a + P1b, 4,701 rows) with all 24 features computed (for Prompt 1b incremental build) |
| `feature_config_partial.json` | P33/P67 bin edges for all features, Feature 18 proximity threshold, P1 feature mean/std |

⚠️ **Handoff contract to Prompt 1b:** These files plus `baseline_report_clean.md` from Prompt 0. Prompt 1b builds scoring models from these. If no features are classified STRONG or SBB-MASKED, discuss with user before proceeding.

---

## Review Gate

**Before proceeding to Prompt 1b, the user reviews:**

1. **Feature screening** — how many STRONG features? Which ones? Any SBB-MASKED features?
2. **Multi-horizon consistency** — do the STRONG features separate at 3+ horizons?
3. **Mechanism validation** — how many STRUCTURAL? Do they align with trading intuition?
4. **Cross-reference with baseline** — do the STRONG features align with the population splits from Prompt 0? (e.g., if CascadeState split showed PRIOR_BROKE is a loser, did Feature 4 classify STRONG?)
5. **SBB-masked check** — did any features upgrade from WEAK to STRONG on NORMAL-only? These capture within-population signal hidden by SBB noise.
6. **Confirmation simulation** — did STRONG features also show PF separation, or only R/P?

⚠️ **If zero features classified STRONG, zero SBB-MASKED, AND baseline PF < 1.0 (from Prompt 0):** This is the strongest stop signal. No unfiltered edge AND no individual feature can separate on either the full or NORMAL-only population. User decides whether to proceed.

⚠️ **If zero STRONG but SBB-MASKED features exist:** The features work on the NORMAL population. Proceed to Prompt 1b — the scoring model will naturally filter SBB touches, and SBB-MASKED features take over from there.

⚠️ **If zero STRONG, zero SBB-MASKED, BUT baseline PF > 1.0:** The edge exists but features don't improve it. Consider trading the unfiltered population.

⚠️ **If STRONG features exist regardless of baseline PF:** Proceed to Prompt 1b. The features may create an edge even from a weak baseline.

---

## Context Reminders

⚠️ **Every 25–35 lines of code, reinforce:**
- P1 only (4,701 touches). P2 NOT used.
- Is this feature computable at entry time?
- Compare against baseline R/P from Prompt 0.

⚠️ **After Step 3 (feature computation):** Print null rates and confirm entry-time computability.

⚠️ **After Step 4 (screening):** Print STRONG/SBB-MASKED/MODERATE/WEAK classification. This is the key deliverable of Prompt 1a.

✅ **Prompt 1a self-check (run before saving outputs):**
- [ ] P1 only (P1a + P1b concatenated, 4,701 touches) — P2 NOT used
- [ ] Median cell exit parameters (stop/target/time_cap) extracted from baseline report
- [ ] Single-feature screening used exit-independent R/P ratios at 4 horizons
- [ ] Floor rule applied (denominator ≥ 1.0 tick)
- [ ] Multi-horizon consistency checked for all features
- [ ] SBB-masked secondary screening run on WEAK/MODERATE features using NORMAL-only touches
- [ ] Confirmation simulation used median cell exit from Prompt 0 (STRONG + SBB-MASKED features)
- [ ] Feature 3 (VP Ray binary) NOT included (constant at 100%)
- [ ] Feature 19 (VP Ray Consumption) derived from touch history — NOT from HasVPRay
- [ ] Feature 20 (Distance to Consumed VP Ray) null for INTACT and seq=1
- [ ] Mechanism validation did NOT remove features — classification only
- [ ] Expansion features 21–25 computed using zone_lifecycle.csv (not rebuilt)
- [ ] Expansion features labeled as (EXP) in screening table
- [ ] Baseline anchor (from Prompt 0) referenced throughout
- [ ] All output files saved
