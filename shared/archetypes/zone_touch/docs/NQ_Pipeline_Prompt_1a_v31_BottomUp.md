# NQ Zone Touch — Clean Data Pipeline: Prompt 1a (Feature Screening)

> **Version:** 3.1
> **Date:** 2026-03-20
> **Scope:** Feature computation (P1 only), single-feature R/P screening, mechanism validation
> **Prerequisite:** Prompt 0 outputs (baseline_report_clean.md) + data prep files
> **Next:** Review screening results. Proceed to Prompt 1b (Model Building) unless zero STRONG features AND baseline PF < 1.0.

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

### From Data Prep:

| File | Purpose |
|------|---------|
| `NQ_merged_P1a.csv` | P1a touches — concatenated with P1b for calibration |
| `NQ_merged_P1b.csv` | P1b touches — concatenated with P1a for calibration |
| `NQ_bardata_P1.csv` | Rotational bar data for P1 — feature computation |
| `period_config.json` | Date boundaries and touch counts |

⚠️ **Concatenate P1a + P1b** into one P1 dataset at load time. All work in this prompt uses the full P1 set (4,701 touches).

⚠️ Read `baseline_report_clean.md` first. Print: baseline PF anchor (median cell), population R/P @60bars, SBB split, baseline verdict. Every result below is compared against these.

---

## Step 3: Feature Computation (P1 only)

Compute all 19 active features for every P1 touch.

⚠️ Reminder: we are on P1 only (P1a + P1b concatenated, 4,701 touches). Baseline PF anchor = [X] from Prompt 0.

#### Features 1–14 (from merged CSV + rotational bar data)

**Feature 1: Timeframe** — SourceLabel mapped to TFWeightScore: 15m=5, 30m=8, 60m=12, 90m=15, 120m=18, 240m+=25

**Feature 2: Zone Width** — ZoneWidthTicks column (pre-computed)

**Feature 3: DROPPED** — VP Ray Binary (HasVPRay = 1 for 100% — zero variance)

**Feature 4: Cascade State** — CascadeState column: PRIOR_HELD / NO_PRIOR / PRIOR_BROKE / UNKNOWN. Treat UNKNOWN as NO_PRIOR.

**Feature 5: Session** — 5 classes from DateTime: PreMarket (<8:30), Morning (8:30–12:00), Afternoon (12:00–15:00), LateAfternoon (15:00–17:00), Evening (>17:00)

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

Print: feature distributions, correlation matrix (flag |r| > 0.7), 5 sample rows, VP Ray Consumption distribution + mean Reaction per category, Feature 20 distribution for consumed touches, null rates for features 8/10/19/20.

⚠️ Checkpoint: confirm all 19 features computable at entry time. State explicitly.

---

## Step 4: Single-Feature Screening (P1 only)

**Purpose:** Test each feature INDEPENDENTLY — no other features involved. A feature that separates good from bad touches on its own is likely structural. A feature that only helps in combination is likely curve fitting.

**Why R/P ratio instead of simulated PF:** Screening asks a touch-level question: "does this feature identify touches where price reacts favorably?" Using PF under a specific exit biases toward features that work with that exit structure. R/P ratio measures touch quality directly, with no exit dependency. Multi-horizon R/P adds time-awareness: a feature that separates at 30, 60, AND 120 bars is robust; one that only separates at 360 bars is a slow signal most exits can't capture.

⚠️ Reminder: P1 data only. No simulation needed for primary screening — R/P uses columns already in the merged CSV. Baseline median R/P = [X] from Prompt 0.

For each of the 19 active features:

**1. Bin P1 touches** by this feature only:
   - Continuous features: tercile split (P33/P67 from P1)
   - Categorical features (Cascade, Session, VP Ray Consumption): use natural categories

**2. Compute R/P ratio per bin at multiple horizons:**

For each bin, compute:
- R/P at 30 bars: mean(RxnBar_30) / mean(PenBar_30)
- R/P at 60 bars: mean(RxnBar_60) / mean(PenBar_60)
- R/P at 120 bars: mean(RxnBar_120) / mean(PenBar_120)
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

**6. Confirmation simulation (STRONG features only):**

For features classified as STRONG, run a single confirmation simulation using the **median cell exit from Prompt 0** to verify the R/P separation translates to PF separation under realistic trading conditions. Report PF @3t per bin.

If a STRONG feature shows clear R/P separation but weak PF separation under simulation: the feature identifies good touches but the no-overlap filter or time cap prevents capturing the edge. Note this — it may work with different exits in Prompt 2.

⚠️ Reminder: P1 only. Baseline anchor = [X]. This confirmation simulation uses P1 bar data only.

Print single-feature screening table:

| Rank | Feature | Best Bin R/P @60 | Worst Bin R/P @60 | R/P Spread @60 | Horizons Consistent | MWU p @60 | Cohen's d | Classification | N (best/worst) |
|------|---------|-----------------|------------------|----------------|--------------------|-----------| ----------|---------------|-----------------|
| 1 | ? | ? | ? | ? | ?/4 | ? | ? | ? | ? |
| 2 | ? | ? | ? | ? | ?/4 | ? | ? | ? | ? |
| ... | | | | | | | | | |
| 19 | ? | ? | ? | ? | ?/4 | ? | ? | ? | ? |

(Show 60-bar horizon as primary column. Full multi-horizon table in `feature_screening_clean.md`.)

Print: "STRONG SIGNAL features: [list] — consistent across [N] horizons."
Print: "WEAK SIGNAL features: [list]."

⚠️ Reminder: P1 only. No other period data used. Baseline median R/P = [X] from Prompt 0.

---

## Step 5: Feature Mechanism Validation (P1 only — STRONG and MODERATE features only)

Run mechanism validation tests ONLY on features classified as STRONG or MODERATE in Step 4. WEAK features are tested but results are informational.

**Test 1: Temporal Stability** — Split P1 in half by date. Compute R/P spread (at 60-bar horizon) per feature on each half independently. Stable = same sign and within 2× magnitude.

**Test 2: Regime Independence** — Split P1 by ATR regime (Feature 17 median). Compute R/P spread (at 60-bar horizon) within each regime. Independent = same sign in both.

⚠️ Reminder: the halves and regime splits are within P1, not across periods. P1 only. Baseline anchor = [X].

**Test 3: Monotonicity** — For 3-bin features, check consistent ordering of Reaction across bins. Binary features exempt.

⚠️ Zone width drift warning: Compare Feature 2 (Zone Width) and Feature 9 (ZW/ATR) bin edges. Report whether the ratio absorbs the width drift observed in the data prep report (P1 median ~170t vs P2b median=280t — zone widths increase over time).

**Mechanism Classification:**

| Feature | Step 4 Class | Temporal | Regime | Monotonic | Final Classification |
|---------|-------------|----------|--------|-----------|---------------------|
| ? | STRONG | ? | ? | ? | STRUCTURAL / LIKELY / STATISTICAL |
| ... | | | | | |

Rules:
- **STRUCTURAL:** STRONG signal + passes 2/3 mechanism tests (or 3/3)
- **LIKELY STRUCTURAL:** MODERATE signal + passes 2/3, OR STRONG + passes 1/3
- **STATISTICAL ONLY:** Fails signal screening OR passes ≤ 1/3 mechanism tests
- **DROPPED:** Feature 3 (constant)

⚠️ **This step does NOT remove features from the model.** It classifies them for deployment confidence. All 19 active features proceed to Prompt 1b.

---

## Required Outputs (saved for Prompt 1b)

| Output File | Contents |
|-------------|----------|
| `feature_screening_clean.md` | Single-feature screening table, classifications (STRONG/MODERATE/WEAK), ranked by R/P spread at 60-bar horizon. Full multi-horizon detail included. |
| `feature_mechanism_validation.md` | Temporal stability, regime independence, monotonicity + STRUCTURAL/LIKELY/STATISTICAL per feature |
| `p1_features_computed.csv` | P1 touches (P1a + P1b, 4,701 rows) with all 19 features computed (for Prompt 1b incremental build) |
| `feature_config_partial.json` | P33/P67 bin edges for all features, Feature 18 proximity threshold, P1 feature mean/std |

⚠️ **Handoff contract to Prompt 1b:** These files plus `baseline_report_clean.md` from Prompt 0. Prompt 1b builds scoring models from these. If no features are classified STRONG, discuss with user before proceeding.

---

## Review Gate

**Before proceeding to Prompt 1b, the user reviews:**

1. **Feature screening** — how many STRONG features? Which ones?
2. **Multi-horizon consistency** — do the STRONG features separate at 3+ horizons?
3. **Mechanism validation** — how many STRUCTURAL? Do they align with trading intuition?
4. **Cross-reference with baseline** — do the STRONG features align with the population splits from Prompt 0? (e.g., if TF split showed HTF outperforms, did Feature 1 classify STRONG?)
5. **Confirmation simulation** — did STRONG features also show PF separation, or only R/P?

⚠️ **If zero features classified STRONG AND baseline PF < 1.0 (from Prompt 0):** This is the strongest stop signal. No unfiltered edge AND no individual feature can separate. User decides whether to proceed.

⚠️ **If zero features classified STRONG BUT baseline PF > 1.0:** The edge exists but features don't improve it. Consider trading the unfiltered population.

⚠️ **If STRONG features exist regardless of baseline PF:** Proceed to Prompt 1b. The features may create an edge even from a weak baseline.

---

## Context Reminders

⚠️ **Every 25–35 lines of code, reinforce:**
- P1 only (4,701 touches). P2 NOT used.
- Is this feature computable at entry time?
- Compare against baseline R/P from Prompt 0.

⚠️ **After Step 3 (feature computation):** Print null rates and confirm entry-time computability.

⚠️ **After Step 4 (screening):** Print STRONG/MODERATE/WEAK classification. This is the key deliverable of Prompt 1a.

✅ **Prompt 1a self-check (run before saving outputs):**
- [ ] P1 only (P1a + P1b concatenated, 4,701 touches) — P2 NOT used
- [ ] Single-feature screening used exit-independent R/P ratios at 4 horizons
- [ ] Floor rule applied (denominator ≥ 1.0 tick)
- [ ] Multi-horizon consistency checked for all features
- [ ] Confirmation simulation used median cell exit from Prompt 0 (STRONG features only)
- [ ] Feature 3 (VP Ray binary) NOT included (constant at 100%)
- [ ] Feature 19 (VP Ray Consumption) derived from touch history — NOT from HasVPRay
- [ ] Feature 20 (Distance to Consumed VP Ray) null for INTACT and seq=1
- [ ] Mechanism validation did NOT remove features — classification only
- [ ] Baseline anchor (from Prompt 0) referenced throughout
- [ ] All output files saved
