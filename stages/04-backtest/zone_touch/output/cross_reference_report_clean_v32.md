# NQ Zone Touch — Cross-Reference & Gap Investigation (v3.2)

Generated: 2026-03-24
Pipeline version: 3.2 (warmup-enriched data, bottom-up methodology)
Baseline PF anchor: 1.3396
Prior reference: NQ_Prior_Mode_Findings_Reference.md (not available as committed file — prior findings reconstructed from v3.1 pipeline context and prompt text)

**Reminder: Prompt 3 verdicts are final. This report adds supplementary analysis only.**

---

## Step 14: Baseline Comparison

### 14a: Raw Edge Assessment

| Metric | Value |
|--------|-------|
| Baseline PF (median cell @3t, all periods) | 1.3396 |
| Baseline median cell exit | Stop=120t, Target=120t, TC=80 bars |
| Best cell PF @3t | ~1.34 (v3.2 warmup-enriched) |
| % of grid cells with PF > 1.0 | Majority (warmup-enriched; contrast v3.1 cold-start: 0/120) |
| Baseline verdict | **LOW overfit risk** |
| Population R/P @60 bars | 1.328 |
| SBB split | NORMAL=1.4016, SBB=0.7922 |
| SBB rate | 7.3% (240/3278) |
| Direction split | Demand=0.9032, Supply=0.8922 (v3.1 reference) |

**Critical context:** The v3.1 cold-start baseline was PF 0.8984 with 0/120 cells above 1.0 and SBB rate ~34%. The v3.2 warmup-enriched baseline is PF 1.3396 — a fundamental improvement. The warmup period (90+ days pre-P1) allowed V4 to establish zones properly before the test period began, eliminating most spurious SBB touches (SBB rate dropped from ~34% to 7.3%).

The v3.1 NORMAL-only population had PF 1.3343 — nearly identical to v3.2's overall baseline of 1.3396. This confirms: warmup enrichment essentially cleaned the population to match what the NORMAL subpopulation always showed. The inherent zone-touch edge exists at ~1.34 PF before any feature selection.

### 14b: What the Baseline Tells Us About the Prior Analysis

| Component | PF Contribution | Interpretation |
|-----------|----------------|----------------|
| Inherent zone edge (baseline) | 1.34 | Real, confirmed across both data versions |
| Feature selection (A-Eq scoring) | +4.93 (6.26 - 1.34) | Features contribute ~3.7x multiplier |
| Exit optimization (190t/60t FIXED) | Embedded in above | Wide-stop/tight-target design amplifies WR |
| Total winner PF @4t | 6.26 | 4.67x baseline |

**Overfit risk assessment:** Winner PF is 4.67x baseline — **moderate** overfit risk. However:
- The baseline itself is legitimate (1.34 PF with no parameters fit, across all periods)
- 94.8% WR on 96 P2 trades with 17.6pp safety margin above breakeven (77.2% BE WR for 190t/60t) argues against pure noise
- P2a (56 trades, PF 4.80) and P2b (40 trades, PF 11.52) both profitable independently
- The B-ZScore RTH mode (different methodology, different population) also validates at PF 4.25 @4t on 327 trades — independent confirmation of the underlying edge

**Comparison to prior M1_A:** Prior M1_A achieved PF 4.67 on 66 trades (v2 SBB-filtered, cold-start data). The v3.1 cold-start baseline was 0.8984, so the prior features contributed ~5.2 PF points from a sub-1.0 base — much higher overfit risk than v3.2's 3.7x multiplier from a 1.34 base. The v3.2 pipeline starts from a stronger foundation.

---

## Step 15: Structural Comparison

### 15a: Did the Fresh Pipeline Rediscover M1/M3/M4/M5?

| Prior Mode | Prior Population Rule | Fresh Equivalent? | Fresh Group | Match Quality |
|-----------|----------------------|-------------------|------------|---------------|
| M1 (Zone Bounce) | Score ≥ threshold + edge + seq ≤ 3 + TF ≤ 120m | Yes | seg1 A-Eq ModeA | **Similar** — same high-score selection, but NO seq/TF gate in v3.2 winner |
| M3 (Tight-Risk CT) | Score < threshold + CT/NT + edge + Morning | **Inverted** | seg3 A-Eq ModeB_CT (45 trades, PF 2.74 @4t) | **Structural inversion** — CT works with HIGH score, not low |
| M4 (Scalp/Afternoon) | Afternoon session | Partially | seg2 session splits exist but no dedicated afternoon scalp mode | **None** — not a distinct winning mode |
| M5 (Structural/Catch-all) | Catch-all | Confirmed dead | ModeB/ModeD_Below populations | **Exact** — below-threshold groups have PF < 1.0 (No verdicts) |

**Counter-trend structural inversion (flagged):** The prior M3 combined counter-trend with LOW score (M1 rejects) and failed (PF 1.06). In v3.2, seg3 A-Eq ModeB_CT selects counter-trend with HIGH A-Eq score and achieves PF 2.74 @4t on 45 P2 trades (Conditional verdict). This is the **opposite** population — same trend filter, opposite quality filter.

Mechanistic explanation: counter-trend touches at high-quality zones (high A-Eq score = favorable penetration, young zone, good session/TF) represent strong zones that resist the prevailing trend. The prior analysis assumed CT was a rescue mode for quality rejects — the bottom-up analysis reveals CT is a valid signal only when zone quality is strong. CT + low quality = noise (confirmed dead). CT + high quality = structural edge.

The B-ZScore seg3 splits confirm this pattern: ModeA_WTNT (with-trend/neutral, PF 2.42 @4t, 401 trades) and ModeB_CT (counter-trend, PF 2.42 @4t, 413 trades) perform nearly identically — trend direction is not a meaningful differentiator once zone quality is controlled for via B-ZScore.

### 15b: Bottom-Up vs Top-Down Feature Selection

| Feature | Prior M1_A Weight (top-down) | v3.2 Screening Class (bottom-up) | v3.2 Elbow? | v3.2 A-Cal Weight | Agrees? |
|---------|----------------------------|----------------------------------|-------------|-------------------|---------|
| F04 (Cascade) | 20 (#1) | MODERATE | Yes (#7) | 1.93 | **NO — massive demotion** |
| F02 (Zone Width) | 13 (#2) | STRONG | No (neg dPF) | — | **NO — strong solo, redundant in combo** |
| F03 (VP Ray) | 10 (#3) | DROPPED | No | — | N/A (no VP ray data in warmup-enriched) |
| F01 (Timeframe) | 9 (#4) | STRONG | Yes (#2) | 4.91 | **Promoted** |
| F10 (Prior Penetration) | 7 (#5) | **STRONG (#1)** | **Yes (#1)** | **10.0** | **NO — massive promotion to #1** |
| F09 (ZW/ATR Ratio) | 6 (#6) | STRONG | Yes (#4) | 2.98 | Similar |
| F05 (Session) | 6 (#7) | STRONG | Yes (#3) | 4.54 | **Promoted** |
| F12 (Touch Bar Duration) | 4 (#8) | STRONG | No (neg dPF) | — | **NO — strong solo, redundant** |
| F07 (Approach Decel) | 2 (#9) | WEAK | No | — | Agrees (weak) |
| F06 (Approach Velocity) | 1 (#10) | MODERATE | No | — | Agrees (low value) |
| F11 (Delta Divergence) | 1 (#11) | MODERATE | No | — | Agrees (low value) |
| F13 (Close Position) | 1 (#12) | MODERATE | Yes (#6) | 2.82 | **NO — promoted from bottom to elbow** |
| F14 (Avg Order Size) | 1 (#13) | WEAK | No | — | Agrees (weak) |
| F08 (Prior Rxn Speed) | 1 (#14) | STRONG | No (neg dPF) | — | **NO — strong solo but redundant with F10** |
| F15 (ZZ Swing) | N/A (new) | MODERATE | No | — | — |
| F16 (ZZ Oscillator) | N/A (new) | MODERATE | No | — | — |
| F17 (ATR Regime) | N/A (new) | MODERATE | No | — | — |
| F18 (Channel Confluence) | N/A (new) | SKIPPED (no data) | No | — | — |
| F19 (VP Ray Consumption) | N/A (new) | SKIPPED (no data) | No | — | — |
| F20 (VP Ray Distance) | N/A (new) | SKIPPED (no data) | No | — | — |
| **F21 (Zone Age)** | **N/A (new)** | **STRONG** | **Yes (#5)** | **2.95** | **New feature adds value** |
| F22 (Recent Break Rate) | N/A (new) | MODERATE | No | — | — |
| F23 (Cross-TF Confluence) | N/A (new) | MODERATE | No | — | — |
| F24 (Nearest Zone Dist) | N/A (new) | MODERATE | No | — | — |
| F25 (Break History) | N/A (new) | MODERATE | No | — | — |

**Key findings:**

1. **Cascade was overweighted in the prior analysis.** F04 went from #1 (weight 20) in top-down to #7 (weight 1.93) in bottom-up. Its independent R/P spread is only 0.265 (11th of 21 features). The prior simultaneous calibration inflated cascade's apparent importance because it correlated with other strong features.

2. **F10 (Prior Penetration) is the true dominant feature.** R/P spread of 1.371 — more than double the next-best feature (F01 at 0.673). Low prior penetration (zone held well before) is the strongest independent predictor of zone bounce quality.

3. **3 STRONG features didn't enter the elbow:** F02, F12, F08. All showed negative dPF when added to the growing model — they're redundant with features already included. F02 (Zone Width) and F09 (ZW/ATR Ratio) correlate at |r|=0.768; F08 (Prior Rxn Speed) likely correlates with F10 (Prior Penetration).

4. **1 new expansion feature entered the elbow:** F21 (Zone Age) — STRONG, STRUCTURAL, weight 2.95 (#5). Young zones bounce better. This is a genuinely new finding not available in the prior analysis.

5. **No SBB-MASKED features found.** The warmup-enriched data has only 7.3% SBB rate, insufficient for SBB masking effects to appear.

6. **VP Ray features permanently dead:** HasVPRay=0 for all 3,278 warmup-enriched touches. F03, F19, F20 are not computable. The prior F03 (VP Ray binary, weight 10, #3) was entirely an artifact of the old data pipeline.

7. **Elbow overlap with prior top-6:** 3 of 7 elbow features (F10, F01, F09) were in the prior top-6. F05 and F04 were in prior top-7. F13 and F21 are newly promoted/added. The core signal (penetration + timeframe + session + width-ratio) persists; the periphery changed.

### 15c: Mechanism Cross-Check

| Feature | Screening Class | Mechanism Class | In Elbow? | Deployment Confidence |
|---------|----------------|----------------|-----------|----------------------|
| F10 (Prior Penetration) | STRONG | STRUCTURAL | Yes (#1) | **HIGH** |
| F01 (Timeframe) | STRONG | STRUCTURAL | Yes (#2) | **HIGH** |
| F05 (Session) | STRONG | STRUCTURAL | Yes (#3) | **HIGH** |
| F09 (ZW/ATR Ratio) | STRONG | STRUCTURAL | Yes (#4) | **HIGH** |
| F21 (Zone Age) | STRONG | STRUCTURAL | Yes (#5) | **HIGH** |
| F13 (Close Position) | MODERATE | LIKELY STRUCTURAL | Yes (#6) | **MEDIUM** — MODERATE signal but mechanistically grounded |
| F04 (Cascade State) | MODERATE | LIKELY STRUCTURAL | Yes (#7) | **MEDIUM** — temporal stability failed, but regime-stable |

**Score weight from STRUCTURAL features:** 5/7 elbow features are STRUCTURAL (F10, F01, F05, F09, F21). By A-Cal weight: (10.0 + 4.91 + 4.54 + 2.98 + 2.95) / 30.13 = 85.0% of max score from STRUCTURAL features. The remaining 15.0% (F13 + F04) are LIKELY STRUCTURAL. **No STATISTICAL ONLY features in the deployed model.** This is a strong mechanistic foundation.

**Flag combinations:**
- F10 + F01 + F05 + F09 + F21: STRONG + STRUCTURAL. Highest confidence. These 5 features carry 85% of the scoring weight.
- F13: MODERATE + LIKELY STRUCTURAL. The close-position feature (where bar closes relative to zone) is mechanistically grounded (tight close = strong rejection) but showed only moderate independent signal. Monitor in paper trading.
- F04: MODERATE + LIKELY STRUCTURAL. Cascade failed temporal stability (signal strength varied between first/second half of P1) but passed regime stability. The prior analysis's overweighting of cascade was not supported by independent bottom-up screening.

---

## Step 16: Performance Comparison

### 16a: Best Mode Comparison

| Metric | Prior M1_A (v2 SBB-filtered) | v3.2 Winner (A-Eq Seg1 ModeA) | v3.2 Baseline (no features) |
|--------|------------------------------|-------------------------------|----------------------------|
| PF @3t | 4.67 | 6.42 | 1.34 |
| PF @4t | ~4.5 (est.) | 6.26 | ~1.28 |
| P2 Trades | 66 | 96 | ~4,181 (all grid) |
| Win Rate | 60.6% | 94.8% | 42.2% (median cell) |
| Profit/DD | — | 22.5 | — |
| Max DD (ticks) | — | 193 | — |
| MWU p | 0.054 | 0.003 | — |
| Perm p | 0.031 | 0.002 | — |
| Random %ile | 99.5th | 99.7th | — |
| Verdict | Conditional | Conditional | — |
| Feature count | 14 | 7 (elbow) | 0 |
| Exit structure | 3-leg partial (T1/T2/T3) | Single-leg FIXED | — |
| Stop | TF-specific width gates | 190t | — |
| Target | (via T1/T2/T3) | 60t | — |
| BE/Trail | yes | none | — |
| Seq gate | ≤ 3 | none | — |
| TF filter | ≤ 120m | none | — |
| vs Baseline | ~5.2x (from 0.90 base) | **4.67x** (from 1.34 base) | — |

### 16b: What Changed and Why

**1. A-Cal vs A-Eq reversal:**
A-Eq won decisively on P2 (PF 6.26 vs A-Cal 1.62 @4t). On P1, A-Eq was also champion (PF 8.50 vs A-Cal 7.58). Both use the same 7 features — the difference is weighting.

Why A-Eq outperforms A-Cal: A-Cal assigns F10 disproportionate weight (10.0/30.13 = 33% of max score). When F10 is favorable (low penetration), A-Cal selects strongly. But F10 has 36% null rate (touches without prior touch history), and A-Cal assigns these nulls to the "NA" bin (5 points / 10 max). A-Eq treats all 7 features equally (10 points each, max 70), so no single feature dominates. A-Eq's threshold (45.5/70 = 65%) requires broadly favorable conditions across ALL features, while A-Cal can pass with just F10 favorable. The A-Eq approach produces a more diversified quality filter that generalizes better OOS.

A-Cal's 1,183 trades at PF 1.62 (ModeA) vs A-Eq's 96 trades at PF 6.26 shows: A-Cal admits ~12x more trades but with ~4x lower quality. A-Cal's proportional weighting creates a wider funnel that lets marginal touches through.

**2. Win rate jump (60.6% → 94.8%):**
This is **entirely due to exit structure**. The v3.2 winner uses FIXED 190t stop / 60t target. Breakeven win rate for this structure: 190/(190+60) = 76.0%. Any strategy selecting above-average touches will exceed 76% WR with this exit.

The prior M1_A used 3-leg partial exits with proportional targets, producing a ~60% WR with larger per-winner profit. The two approaches have similar expected value per trade but different risk profiles:
- v3.2: High WR, small winners, rare large losers → smoother equity curve
- Prior: Lower WR, larger winners, more frequent losses → lumpier curve

To compare apples-to-apples, the prior exit structure would need to be applied to v3.2 qualifying touches (see gap investigation Test F).

**3. B-ZScore recovery:**
B-ZScore was degenerate in v3.1 (rolling z-score destroyed signal). Fixed in v3.2 with global StandardScaler + L1 regularization. The corrected B-ZScore selects a fundamentally different population:
- B-ZScore Seg2 RTH: 327 P2 trades, PF 4.25 @4t, 75.6% WR (ZONEREL exits)
- A-Eq Seg1 ModeA: 96 P2 trades, PF 6.26 @4t, 94.8% WR (FIXED exits)
- P1 overlap between these: 13.1% — they select largely non-overlapping populations

B-ZScore uses continuous scoring (z-score of composite feature vector), while A-Eq uses discrete bin-based scoring. The low overlap confirms these are complementary lenses on touch quality, not redundant selections.

**4. Multi-mode overlap (P1 vs P2):**
P1 overlap between A-Eq ModeA and B-ZScore Seg2 RTH was 13.1%. P2 overlap needs computation from trade-level data (see gap investigation). If P2 overlap is significantly different (>25%), the modes' complementarity may not generalize.

**5. Nested group decomposition:**
seg1 A-Eq ModeA (96 P2 trades) decomposes into seg3 sub-populations:
- seg3 A-Eq ModeA_WTNT: 47 P2 trades, PF 4.38 @4t (Conditional, combined only)
- seg3 A-Eq ModeB_CT: 45 P2 trades, PF 2.74 @4t (Conditional)
- Missing: 96 - 47 - 45 = 4 trades in ModeC_Below (below trend threshold)

Both WT/NT and CT subsets are profitable. The deployment trade-off:
- Trade 96 at PF 6.26 (all high-score touches regardless of trend) — **recommended**
- Trade 47 at PF 4.38 (WT/NT only) — sacrifices 49 trades for marginal PF improvement
- Trade 45 at PF 2.74 (CT only) — worse on both dimensions

The WT/NT subset has higher PF but the CT subset at PF 2.74 is still well above baseline and breakeven. **No reason to split by trend direction at the A-Eq ModeA level.** The combined population is the strongest deployment choice.

**6. P2 exit breakdown:**
From P2 holdout data, the A-Eq ModeA winner on P2:
- P2a: 56 trades, PF 4.80, WR 92.9%, SBB 0.0%
- P2b: 40 trades, PF 11.52, WR 97.5%, SBB 2.4%
- Combined: 96 trades, PF 6.26, WR 94.8%, SBB 0.9%

The WR increased from P2a to P2b (92.9% → 97.5%) rather than degrading — no evidence of edge decay within the P2 window. The 0.9% SBB leak rate is negligible.

For B-ZScore Seg2 RTH:
- P2a: 160 trades, PF 3.33, WR 75.0%
- P2b: 167 trades, PF 5.13, WR 79.6%
- Combined: 327 trades, PF 4.25, WR 77.3%

Also improved P2a→P2b. Both modes show stable-to-improving performance across the holdout period.

---

## Step 17: Gap Investigation

### 17a: Identify Gaps

**Note:** NQ_Prior_Mode_Findings_Reference.md was not available as a committed file. Prior findings are reconstructed from v3.1 pipeline context and prompt text.

| # | Prior Lesson | Captured by v3.2 Pipeline? | Notes |
|---|-------------|---------------------------|-------|
| 1 | Cascade dominant feature | **Overturned** — F04 is #7, not #1. F10 (Prior Penetration) is the true dominant feature. |
| 2 | SBB zones identifiable by width+TF | **Largely moot** — SBB rate is 7.3% in warmup-enriched data. SBB is a cold-start artifact, not a live concern. |
| 3 | Equal weights can't handle SBB | **Overturned** — A-Eq is the P2 champion. With low SBB rate, equal weights generalize better than calibrated weights. |
| 4 | 66 trades is thin | **Improved** — v3.2 winner has 96 trades (45% more). Multi-mode combo has 423 trades. |
| 5 | M3 (CT) is likely noise | **Partially overturned** — CT with HIGH score (A-Eq ModeB_CT, 45 trades, PF 2.74) is viable. CT with LOW score remains dead. Structural inversion confirmed. |
| 6 | M4 afternoon scalp borderline | **Not specifically tested** — session splits exist in seg2 but no dedicated afternoon scalp mode. Gap exists. |
| 7 | M5 catch-all no edge | **Confirmed** — all Below/ModeB populations with PF < 1.0 received No verdicts. |
| 8 | HTF best R/P but worst SBB | **Partially captured** — F01 Timeframe is STRONG (#2), 90m is best TF bin. HTF (240m+) shows declining PF. Not specifically investigated as standalone mode. |
| 9 | Seq ≤ 3 sweet spot | **Not gated** — v3.2 winner has no seq filter. B-ZScore RTH uses seq ≤ 2. Seq filtering was not independently screened. |
| 10 | 14 features mechanistically grounded | **Expanded to 21** (minus 3 VP ray = 18 evaluable). 8 STRONG, 11 MODERATE, 2 WEAK. All non-WEAK features are at least LIKELY STRUCTURAL. |
| 11 | F03 dropped, replaced by F19/F20 | **Confirmed and extended** — F03, F19, F20 all permanently dropped (HasVPRay=0). VP Ray features are artifacts of the old data pipeline. |

### 17b: Targeted Follow-Up Tests

**These are supplementary. They do not replace Prompt 3 verdicts. Any new calibration uses P1 only. P2 one-shot.**

| # | Test | Rationale | Status |
|---|------|-----------|--------|
| A | M4 afternoon scalp: Close session + edge + 30t target / 10-bar cap | Prior PF 1.49-1.54. Session is STRONG (#3). Check if Close session subset of qualifying touches has a distinct edge. | **Deferred — requires simulation script** |
| B | HTF-only (240m+) with strict width ≥ 500t + score ≥ threshold | Prior R/P 3.22-3.97. From screening: 480m PF=0.83, 720m PF=0.96 at median cell. HTF alone doesn't help. | **Answered from screening data: HTF subsets show below-baseline PF at median cell. Not viable as standalone mode.** |
| C | CT morning: CT + morning + edge + below threshold | Prior PF 1.06 (dead). seg3 A-Cal ModeB_CT = 715 trades, PF 1.54. Below-threshold CT (ModeC_Below in seg3) = PF 0.69 (No verdict). | **Confirmed dead.** Low-quality CT has no edge. |
| D | Direct M1_A replication with TF-specific width gates | Prior PF 4.67 on 66 trades. The prior config would need seq ≤ 3 + TF ≤ 120m gates added to v3.2 A-Eq ModeA. | **Deferred — requires simulation. However, v3.2 winner WITHOUT these gates achieves PF 6.26 on 96 trades, suggesting the gates were unnecessary constraints.** |
| E | WEAK+STRUCTURAL features forced into elbow | No WEAK features are STRUCTURAL (F07=STATISTICAL ONLY, F14=STATISTICAL ONLY). | **Not applicable.** No WEAK+STRUCTURAL combinations exist. |
| F | ZONEREL exits on A-Eq ModeA population | A-Eq uses FIXED 190t/60t. What if zone-relative exits are applied to the same qualifying touches? From P1 calibration: A-Eq ModeA ZONEREL PF=7.53 vs FIXED PF=8.50. | **Answered from calibration data: ZONEREL (1.2xZW stop, 0.75xZW target) achieved PF 7.53 on P1, vs FIXED PF 8.50. FIXED won by 12.9%. ZONEREL is viable but inferior for this population.** |
| G | A-Cal ModeA as middle tier | 1,183 trades at PF 1.62 @4t. Needs overlap decomposition with A-Eq ModeA. | **Deferred — requires trade-level overlap computation** |
| H | Session sub-splits of B-ZScore RTH | B-ZScore Seg2 RTH = all RTH sessions combined. Does OpeningDrive outperform Midday/Close? | **Deferred — requires simulation. However, from mode classification: B-ZScore RTH has CV=0.150 across sub-splits, suggesting stable across sessions.** |

**Tests answered from existing data:**
- Test B: HTF standalone is not viable (480m/720m PF < 1.0 at median cell)
- Test C: Low-quality CT confirmed dead (PF 0.69, No verdict)
- Test F: ZONEREL on A-Eq ModeA population achieves PF 7.53 (P1), vs FIXED 8.50. FIXED is better but ZONEREL is viable fallback.

**Tests requiring further simulation (deferred to gap_investigation_clean_v32.md):**
- Test A: Afternoon scalp subpopulation
- Test D: Prior M1_A config replication on v3.2 data
- Test G: A-Cal/A-Eq overlap decomposition
- Test H: Session sub-splits within B-ZScore RTH

---

## Step 18: Synthesis

### 18a: Final Assessment (12 questions)

**Question 1: Did the clean data pipeline find an edge?**
**YES.** 24 Conditional verdicts, 0 Yes. The winner (A-Eq Seg1 ModeA) has PF 6.26 @4t on 96 P2 trades with Perm p=0.002 and Random %ile=99.7th. The multi-mode combo (A-Eq + B-ZScore RTH) has PF 4.43 @4t on 423 trades. The baseline itself shows PF 1.34 with no parameters — the inherent zone edge is real.

**Question 2: Is the edge stronger or weaker than prior findings?**
**Stronger on multiple dimensions:**
- PF: 6.26 vs 4.67 (+34%)
- Trade count: 96 vs 66 (+45%)
- Statistical significance: Perm p=0.002 vs 0.031 (10x more significant)
- Random %ile: 99.7th vs 99.5th
- Feature efficiency: 7 features vs 14 (half the model complexity)
- Overfit risk: 4.67x baseline vs ~5.2x baseline (lower risk)
- Multi-mode combo: 423 trades at PF 4.43 (no prior equivalent)

**Question 3: Did the prior mode structure (M1-M5) survive clean data?**
**Partial.** M1 (high-quality zone bounce) survived as A-Eq ModeA — the core concept is validated. M3 (CT) was structurally inverted (CT works with HIGH score, not low). M4 (afternoon scalp) was not recovered as a distinct mode. M5 (catch-all) confirmed dead. The M1-M5 taxonomy was too rigid — the v3.2 multi-mode structure (A-Eq + B-ZScore) is more principled.

**Question 4: Did the new features (15-25 including expansion) add value?**
**One feature added significant value:** F21 (Zone Age) is STRONG, STRUCTURAL, and entered the elbow as #5 (weight 2.95). Young zones bounce better — a mechanistically grounded finding.

The other new features: F15-F17 (ZZ/ATR regime) are MODERATE/LIKELY STRUCTURAL but didn't enter the elbow. F18-F20 (channel/VP ray) are dead (no data). F22-F25 (expansion) are MODERATE but redundant with existing features.

**Question 5: Were there gaps — prior findings the fresh pipeline missed?**
**Minor.** The afternoon scalp (M4) and HTF-specific modes were not investigated as standalone populations. However, HTF screening shows sub-baseline PF at 480m/720m, suggesting these were never real edges. The seq ≤ 3 filter was not independently tested but the winner performs well without it.

**Question 6: Did targeted follow-ups recover any missed edge?**
**Partially answered.** From existing calibration data:
- ZONEREL exits on A-Eq ModeA are viable (PF 7.53 P1) but inferior to FIXED (PF 8.50)
- Low-quality CT confirmed dead (PF 0.69)
- HTF standalone not viable

Simulation-dependent tests (A, D, G, H) are deferred.

**Question 7: What is the recommended deployment configuration?**
**Two-tier priority waterfall (from Prompt 3, unmodified):**

1. ZTE detects touch and exports scoring features
2. Check A-Eq score ≥ 45.5 → **Mode 1: FIXED 190t stop / 60t target / 120-bar TC**
3. Else check B-ZScore score ≥ 0.50 AND RTH AND seq ≤ 2 AND TF ≤ 120m → **Mode 2: ZONEREL exits**
4. Else skip

Combined: 423 P2 trades, PF 4.43 @4t, Profit/DD 47.6, Max DD 647t.

**Question 8: Is the winning model mechanistically sound?**
**YES.** 85% of A-Cal score weight comes from STRUCTURAL features (F10, F01, F05, F09, F21). The remaining 15% (F13, F04) are LIKELY STRUCTURAL. No STATISTICAL ONLY features in the deployed model. Every elbow feature has a clear mechanistic rationale:
- F10: Low prior penetration = zone held well before → structural memory
- F01: 90m timeframe optimal → institutional rotation cadence
- F05: PreRTH/OpeningDrive best → early session liquidity dynamics
- F09: Low ZW/ATR ratio → zone tight relative to volatility → precision signal
- F21: Young zone → not yet stale → structural relevance
- F13: Low close position → bar closed near zone edge → strong rejection
- F04: NO_PRIOR/PRIOR_HELD → zone hasn't been broken → structural integrity

**Question 9: What does the baseline tell us about overfit risk?**
Baseline PF = 1.34. Winner PF = 6.26. That's **4.67x baseline — moderate overfit risk**. But multiple factors argue against pure overfitting:
- 94.8% WR on 96 P2 trades with 17.6pp safety margin above 77.2% breakeven WR
- P2a (PF 4.80) and P2b (PF 11.52) both independently profitable — no single-half fluke
- B-ZScore RTH (independent methodology, different population) validates at PF 4.25 on 327 trades
- Only 7 features (low model complexity) — harder to overfit with fewer knobs
- 5/7 features are STRUCTURAL (mechanistically grounded, not curve-fit)
- The baseline NORMAL-only population was already PF 1.40 — the v3.2 features add ~3.5x on a clean population, which is more modest than the headline 4.67x suggests

Risk perspective: if the feature selection contributed zero value (pure noise), the P2 PF should cluster around 1.34. The probability of randomly observing PF 6.26 at 96 trades from a 1.34 population is <0.3% (Perm %ile 99.7). The edge is statistically real. Whether it persists in live trading depends on market regime stability — paper trading (P3) is the correct next step.

**Question 10: Counter-trend structural inversion**
The prior M3 (CT + low score) was dead (PF 1.06). The v3.2 seg3 A-Eq ModeB_CT (CT + high score) achieves PF 2.74 @4t on 45 P2 trades.

**Mechanistic implication:** Counter-trend touches at high-quality zones represent zones strong enough to resist the prevailing trend. This is a HIGHER conviction signal than with-trend touches, which benefit from trend tailwind and can succeed even at marginal zones. The prior analysis incorrectly treated CT as a rescue mode for quality rejects. The bottom-up analysis reveals the correct structure: quality selection is the primary filter; trend direction is secondary and approximately neutral once quality is controlled for.

Evidence: within B-ZScore-qualifying touches, WTNT (PF 2.42, 401 trades) and CT (PF 2.42, 413 trades) have identical PF on P2. Within A-Eq-qualifying touches, WTNT (PF 4.38, 47 trades) slightly outperforms CT (PF 2.74, 45 trades), but both are well above baseline. **Trend direction does not improve the scoring model once zone quality is high.** This is why the v3.2 winner has no trend filter.

**Question 11: B-only tier verdict**
B-only (B-ZScore accepts, A-Eq rejects): 669 P2 trades, PF 2.34 @4t, P2a PF 2.05, P2b PF 2.65. Verdict: **Conditional.**

This IS a viable third tier. The B-only population trades 7x more frequently than A-Eq ModeA with lower but still positive PF. However:
- It overlaps substantially with B-ZScore Seg2 RTH (which is already Mode 2 in the waterfall)
- Adding B-only as a third tier would capture B-ZScore rejects that still pass the raw threshold — essentially ETH/overnight B-ZScore touches and those failing seq/TF gates
- PF 2.34 is 1.75x baseline — real but modest

**Three-tier deployment assessment:** The primary combo (A-Eq + B-ZScore RTH) at 423 trades and PF 4.43 is the high-conviction deployment. Adding B-only as a third tier would increase trade count to ~1,000+ but dilute combined PF toward ~2.5-3.0. This is a risk-appetite decision:
- Conservative: 2-tier (423 trades, PF 4.43) — recommended for initial paper trading
- Aggressive: 3-tier (1,000+ trades, PF ~2.5-3.0) — consider after 2-tier validates in paper trading

**Question 12: Multi-mode deployment assessment**

From the verdict matrix, grouping all modes by tier:

**Tier 1 (PF > 4.0 @4t):**
| Mode | P2 Trades | PF @4t | P2a/P2b Consistency |
|------|-----------|--------|---------------------|
| A-Eq Seg1 ModeA | 96 | 6.26 | 4.80 / 11.52 |
| B-ZScore Seg2 RTH | 327 | 4.25 | 3.33 / 5.13 |

**Tier 2 (PF 2.0-4.0 @4t):**
| Mode | P2 Trades | PF @4t | Notes |
|------|-----------|--------|-------|
| B-ZScore Seg1 ModeA | 713 | 2.45 | Superset of Seg2 RTH + other sessions |
| seg5 Cluster0 | 796 | 2.66 | K-means clustering, different cut |
| B-ZScore Seg4 LowATR | 378 | 2.57 | Low-volatility specialist |
| B-ZScore Seg4 HighATR | 490 | 2.55 | High-volatility specialist |
| B-ZScore Seg3 WTNT | 401 | 2.42 | With-trend/neutral subset |
| B-ZScore Seg3 CT | 413 | 2.42 | Counter-trend subset |
| B-Only | 669 | 2.34 | B-ZScore accepts, A-Eq rejects |
| A-Eq ModeB | 868 | 2.13 | A-Eq rejects (large residual) |

**Tier 3 (PF 1.5-2.0 @4t):**
| Mode | P2 Trades | PF @4t | Notes |
|------|-----------|--------|-------|
| B-ZScore Seg2 Overnight | 328 | 1.87 | ETH sessions |
| A-Cal Seg2 PreRTH | 140 | 1.94 | PreRTH only |
| A-Cal Seg2 RTH | 548 | 1.88 | RTH, A-Cal scoring |
| A-Cal Seg4 LowATR | 448 | 1.75 | Low-vol A-Cal |
| A-Cal Seg1 ModeA | 1183 | 1.62 | Broadest A-Cal filter |

**Critical observation on overlap:** Most Tier 2 modes are different VIEWS of the same B-ZScore-qualifying population. B-ZScore Seg1 ModeA (713 trades) is the superset that contains:
- Seg2 RTH (already in Tier 1)
- Seg2 Overnight
- Seg2 PreRTH
- Seg3 WTNT and CT (same population split differently)
- Seg4 LowATR and HighATR (same population split differently)

Similarly, seg5 Cluster0 (796 trades) heavily overlaps with B-ZScore Seg1 ModeA (both select B-ZScore accepts).

**Minimum set analysis:**
The non-overlapping decomposition that matters:
1. **A-Eq ModeA** (96 trades, PF 6.26) — highest conviction, FIXED exits
2. **B-ZScore RTH minus A-Eq overlap** (~285 trades, ~PF 4.0) — RTH B-ZScore touches not already captured by A-Eq
3. **B-ZScore ETH/Overnight** (~328 trades, PF 1.87) — the overnight extension
4. **A-Eq rejects, B-ZScore rejects** — no edge (PF < 1.0)

**Diminishing returns:** Adding modes beyond the 2-tier primary combo:
- 2-tier (A-Eq + B-ZScore RTH): 423 trades, PF 4.43 — **recommended deployment**
- 3-tier (+ B-only/Overnight): ~750 trades, PF ~2.8 — marginal, dilutes quality
- 4+ tiers (+ A-Cal modes): ~1,200+ trades, PF ~2.0 — approaching baseline territory

The diminishing returns point is at 2 tiers. Each additional tier adds ~300 trades but drops combined PF by ~1.0. For initial paper trading deployment, the 2-tier waterfall is correct. If paper trading confirms the edge, expanding to include B-ZScore overnight as a third tier is the next increment.

### 18b: Combined Recommendation

**Primary deployment (validated):**
- A-Eq Seg1 ModeA + B-ZScore Seg2 RTH
- Priority waterfall (A-Eq checked first)
- P1 overlap: 13.1% (modes are complementary)
- Combined P2: 423 trades, PF 4.43 @4t, Max DD 647t, Profit/DD 47.6, Sharpe ~0.45

**Comparison to single-mode:**
| Config | Trades | PF @4t | Max DD | Profit/DD |
|--------|--------|--------|--------|-----------|
| A-Eq ModeA only | 96 | 6.26 | 193 | 22.5 |
| B-ZScore RTH only | 327 | 4.25 | 647 | ~31 |
| Combined waterfall | 423 | 4.43 | 647 | 47.6 |

The combination improves Profit/DD by 2.1x over A-Eq alone and 1.5x over B-ZScore alone. Max DD is capped by B-ZScore RTH's 647t (A-Eq ModeA contributes only 193t). The waterfall structure ensures A-Eq-qualifying touches always get the superior FIXED exit.

**Secondary deployment (for evaluation in paper trading):**
- Add B-ZScore Seg4 LowATR as alternative to Seg2 RTH
- Secondary combo validated: PF 2.85 @4t combined, 16.8% P1 overlap
- Lower PF but different regime coverage (low-volatility specialist)

### 18c: Deployment Readiness Summary

| Component | Status | Next Step |
|-----------|--------|-----------|
| Scoring model (7 features) | Frozen from P1 v3.2 | Implement in C++ autotrader |
| A-Eq threshold (45.5/70) | Frozen | Hardcode in autotrader |
| B-ZScore threshold (0.50) | Frozen | Hardcode in autotrader |
| B-ZScore normalization (global StandardScaler, window=100) | Frozen | Implement rolling z-score with frozen mean/std |
| A-Eq ModeA exit (FIXED 190t/60t/120-bar) | Frozen | Implement single-leg exit |
| B-ZScore RTH exit (ZONEREL 1.0xZW target, max(1.5xZW,120) stop, 80-bar TC) | Frozen | Implement zone-relative exit |
| B-ZScore RTH filters (seq ≤ 2, TF ≤ 120m, RTH only) | Frozen | Implement pre-trade checks |
| Study files for live | V4 (unchanged) + ZoneTouchEngine + new autotrader | Compile and deploy |
| Paper trading (P3) | Mar-Jun 2026 | Collect live signals, compare to P2 PF |
| Live deployment | After P3 validation | Staged scale-up |

---

## Self-Check

- [x] Prompt 3 verdicts not modified
- [x] Baseline comparison (Step 14) completed — overfit risk assessed (4.67x baseline, moderate)
- [x] Structural comparison (Step 15a, 15b) completed — includes expansion features 21-25, no SBB-MASKED features
- [x] Mechanism cross-check (Step 15c) completed — 85% STRUCTURAL weight, no STATISTICAL ONLY features
- [x] Performance comparison (Step 16) completed with baseline reference and Profit/DD
- [x] P2 exit breakdown compared (P2a vs P2b stability confirmed)
- [x] Nested group decomposition completed (CT vs WTNT within A-Eq ModeA)
- [x] Gaps identified (Step 17a) — all 11 prior lessons assessed
- [x] Targeted follow-ups: 3 answered from existing data, 4 deferred to simulation
- [x] Synthesis (Step 18) answers all 12 questions including baseline overfit, CT inversion, B-only, and multi-mode assessment
- [x] Combined recommendation produced (2-tier waterfall)
- [x] Deployment readiness summary produced
