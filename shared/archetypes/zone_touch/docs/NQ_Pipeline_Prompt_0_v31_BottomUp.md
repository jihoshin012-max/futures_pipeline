# NQ Zone Touch — Clean Data Pipeline: Prompt 0 (Baseline Establishment)

> **Version:** 3.1
> **Date:** 2026-03-20
> **Scope:** Load all data, establish raw edge baseline across all periods, 9 structural splits, verdict
> **Prerequisite:** Data prep skill outputs (merged CSVs, bar data, period config)
> **Next:** Review baseline results. Proceed to Prompt 1a (Feature Screening) if there's signal to work with.

---

## Three Rules (non-negotiable — apply to ALL prompts)

1. **P1 only for calibration.** Every weight, bin edge, parameter, threshold from P1 data only (P1a + P1b combined). P2a, P2b are not used for calibration. **Exception:** This prompt (Prompt 0) uses ALL periods because no parameters are fit — it measures a population statistic.
2. **No iteration on holdout data.** P2a/P2b are tested exactly once (Prompt 3). No adjustments after seeing results.
3. **All features computable at trade entry time.** No post-touch data for the current touch. Entry is on the NEXT BAR OPEN after the touch bar closes.

⚠️ Reminder: Rules 1–3 apply to every step.

---

## Instrument Constants

- **Instrument:** NQ (Nasdaq 100 E-mini futures)
- **Tick size:** 0.25 points
- **Tick value:** $5.00 per tick per contract
- **Cost model:** 3 ticks ($15.00) per round-turn per contract
- **Bar type:** 250-volume bars
- **Trading hours:** Futures session; primary activity 8:30–17:00 ET

---

## Inputs from Data Prep

| File | Purpose |
|------|---------|
| `NQ_merged_P1a.csv` | P1a sub-period touches |
| `NQ_merged_P1b.csv` | P1b sub-period touches |
| `NQ_merged_P2a.csv` | P2a touches |
| `NQ_merged_P2b.csv` | P2b touches |
| `NQ_bardata_P1.csv` | Rotational bar data for P1 — simulation |
| `NQ_bardata_P2.csv` | Rotational bar data for P2 — simulation |
| `period_config.json` | Date boundaries and touch counts |
| `data_preparation_report.md` | Verification results |

⚠️ **This prompt uses ALL periods for baseline.** No parameters are fit. This is a population statistic.

---

## Simulation Specifications (used throughout this prompt and the entire pipeline)

**Bar-by-bar simulation** using rotational bar data as the price series:
- `NQ_bardata_P1.csv` for P1a/P1b touches
- `NQ_bardata_P2.csv` for P2a/P2b touches

**Entry:** Next bar open after touch bar closes. Entry price = Open of the bar following the touch bar (identified by RotBarIndex + 1).

**Intra-bar conflict:** If both stop and target could fill on the same bar, assume stop fills first (worst case).

**Cost model:** Report PF at 2t, 3t, 4t. Primary metric = PF at 3t.

**Direction:** DEMAND_EDGE → long. SUPPLY_EDGE → short.

**No overlapping trades:** If in position, skip new signals until flat.

**Time cap:** Flatten at time cap bar count. Also flatten at 16:55 ET.

⚠️ These simulation specs are fixed for the entire pipeline. Do not change them.

---

## Step 1: Load & Verify

1. Load ALL merged CSVs: `NQ_merged_P1a.csv`, `NQ_merged_P1b.csv`, `NQ_merged_P2a.csv`, `NQ_merged_P2b.csv`
2. Load both bar data files: `NQ_bardata_P1.csv`, `NQ_bardata_P2.csv`
3. Load `period_config.json` — print all period date boundaries and touch counts
4. Verify RotBarIndex maps correctly for each period (spot-check 5 touches per period)
5. Print per period: row count, touch type distribution, TF distribution, CascadeState distribution, SBB rate
6. Print total: combined touch count across all 4 periods

⚠️ Checkpoint: all 4 period files loaded. This prompt uses ALL of them for baseline.

---

## Step 2: Raw Edge Baseline (no features, no filtering — ALL periods)

**Purpose:** Determine whether zone touches have an inherent edge BEFORE any feature selection. This is the null hypothesis — a population statistic, not a calibration. No parameters are fit, so using all data does not compromise the holdout.

**Population:** ALL edge touches across ALL 4 periods (P1a + P1b + P2a + P2b). No filtering by score, seq, TF, width, or any feature. Every DEMAND_EDGE and SUPPLY_EDGE touch gets traded.

⚠️ **This is the ONLY prompt that uses P2 data for analysis.** It's justified because no parameters are being fit — you're measuring a population property (do zone touches have an edge?), not calibrating a model. From Prompt 1a onward, only P1 is used.

**Exit grid:** Test every combination of:

| Parameter | Values |
|-----------|--------|
| Stop | 60t, 90t, 120t, 160t, 200t |
| Target | 60t, 90t, 120t, 160t, 200t, 240t |
| Time cap | 30, 50, 80, 120 bars |

No BE trigger, no trail — pure stop/target/time cap. This isolates the zone touch edge from exit engineering.

⚠️ Reminder: bar-by-bar simulation. Entry = next bar open after touch bar. Intra-bar conflict = stop fills first. Use `NQ_bardata_P1.csv` for P1a/P1b touches and `NQ_bardata_P2.csv` for P2a/P2b touches.

---

#### 2a: Full Population Baseline

**Report:**

| Metric | Value |
|--------|-------|
| Total edge touches (all periods) | ? |
| P1a / P1b / P2a / P2b | ? / ? / ? / ? |
| Total simulated trades (after no-overlap filter) | ? |
| Trades skipped due to overlap | ? |

**Seq distribution of trades taken** (after no-overlap filter):

| Seq | Trades Taken | % of Total | Trades Skipped | Notes |
|-----|-------------|-----------|---------------|-------|
| 1 | ? | ? | ? | First touches — no prior history |
| 2 | ? | ? | ? | |
| 3 | ? | ? | ? | |
| 4+ | ? | ? | ? | |

This shows whether the no-overlap filter biases toward first touches (seq 1) or whether mature touches get traded proportionally.

⚠️ Reminder: everything in Step 2 uses ALL periods (9,361 touches). No parameters are fit. These are population statistics.

**Population R/P ratios (all touches, no filtering, no simulation):**

| Horizon | Mean Reaction | Mean Penetration | R/P Ratio |
|---------|--------------|-----------------|-----------|
| 30 bars | ? | ? | ? |
| 60 bars | ? | ? | ? |
| 120 bars | ? | ? | ? |
| Full observation | ? | ? | ? |

This is the population-level R/P at each horizon. Prompt 1a screening uses these as the reference — features must show R/P separation relative to these population values.

⚠️ Reminder: this baseline uses ALL 9,361 touches. No feature filtering. This is the population-level edge measurement.

**Baseline PF heatmap (combined — all periods):** The full exit grid is 5 stops × 6 targets × 4 time caps = **120 combinations**. Compute PF @3t for all 120. Report:
- How many of the 120 cells show PF > 1.0?
- How many show PF > 1.3?
- How many show PF > 1.5?
- **Median PF across all 120 cells** (the honest central tendency — what you'd get with a randomly chosen reasonable exit)
- Best PF and its stop/target/time_cap combination (optimistic bound)
- Worst PF and its stop/target/time_cap combination

**Print a 5×6 stop × target visual heatmap** at time_cap=80 (the middle value) for readability. This is a visual summary — the statistics above use all 120 cells.

**Bootstrap confidence interval:** For the median cell and the best cell, compute 95% CI via 10,000 bootstrap resamples. **Resample the trade-level PnL outcomes** from the existing simulation (do NOT re-run the simulation — resample the vector of per-trade net PnL values, recompute PF each time). Report:
- Median cell PF @3t: [point estimate] (95% CI: [lower] – [upper])
- Best cell PF @3t: [point estimate] (95% CI: [lower] – [upper])
- Does the median cell's 95% CI exclude 1.0? (If yes, edge is statistically confirmed at population level)

⚠️ **The baseline PF ANCHOR is the MEDIAN cell PF, not the best cell.** The median represents what you'd get with any reasonable exit structure. The best cell is the optimistic bound. Both are reported but the median is the honest reference throughout the pipeline.

**Median cell risk profile:** For the median cell exit, also report:
- Win rate (% of trades hitting target before stop or time cap)
- Average trade PnL @3t (ticks)
- Average winning trade (ticks) and average losing trade (ticks)
- Max consecutive losses

This characterizes the baseline edge: a 55% win rate with +4t avg PnL is a very different strategy than a 35% win rate with +12t avg PnL.

---

#### 2b: SBB Split Baseline

Run the **median cell** exit on three populations:

| Population | PF @3t | PF @4t | Trades | % of Total |
|-----------|--------|--------|--------|-----------|
| All touches | ? | ? | ? | 100% |
| NORMAL only (SBB_Label = NORMAL) | ? | ? | ? | ? |
| SBB only (SBB_Label = SBB) | ? | ? | ? | ? |

⚠️ Reminder: no parameters fit. This split uses the SBB_Label from data prep (informational). It answers: "Is the zone touch edge destroyed by SBB touches, or does it exist despite them?"

**SBB baseline interpretation:**
- NORMAL PF >> SBB PF → SBB dilutes a real edge. Features that filter SBB are structural (they remove known losers), not curve fitting.
- NORMAL PF ≈ SBB PF → SBB is not the problem. The edge (or lack of it) applies equally to both populations.
- NORMAL PF < 1.0 AND SBB PF < 1.0 → No edge in either population. The strategy has fundamental issues.

---

#### 2c: Per-Period Stability

At the **median** grid cell, report PF on each period independently:

| Period | PF @3t | PF @4t | Trades | Notes |
|--------|--------|--------|--------|-------|
| P1a | ? | ? | ? | Calibration sub-period |
| P1b | ? | ? | ? | Calibration sub-period |
| P2a | ? | ? | ? | Holdout 1 |
| P2b | ? | ? | ? | Holdout 2 |
| Combined | ? | ? | ? | Full sample |

This shows whether the edge is stable across time or concentrated in one period. If PF degrades monotonically from P1a → P2b, the market may be evolving away from zone-based behavior.

⚠️ Reminder: this baseline uses ALL periods because no parameters are fit. From Prompt 1a onward, only P1 is used.

---

#### 2d: Direction Split

At the median grid cell:

| Direction | PF @3t | PF @4t | Trades |
|-----------|--------|--------|--------|
| Demand (long) | ? | ? | ? |
| Supply (short) | ? | ? | ? |
| Combined | ? | ? | ? |

If one direction is profitable and the other isn't, that's structural — no feature will fix the losing direction. The pipeline should note this and the user should consider whether to trade both directions or only the profitable one.

---

#### 2e: Session Split

At the median grid cell:

| Session | PF @3t | PF @4t | Trades |
|---------|--------|--------|--------|
| RTH (8:30–17:00 ET) | ? | ? | ? |
| Overnight (17:00–8:30 ET) | ? | ? | ? |
| Combined | ? | ? | ? |

If RTH shows an edge but overnight doesn't (or vice versa), that's a population-level structural property — not a feature finding.

⚠️ Reminder: all splits in Step 2 use ALL periods with no parameters fit. These are population properties — not features. The baseline anchor is the MEDIAN cell PF.

---

#### 2f: CascadeState Split

At the median grid cell:

| CascadeState | PF @3t | PF @4t | Trades | % of Total | R/P @60 |
|-------------|--------|--------|--------|-----------|---------|
| PRIOR_HELD | ? | ? | ? | ? | ? |
| PRIOR_BROKE | ? | ? | ? | ? | ? |
| NO_PRIOR | ? | ? | ? | ? | ? |
| Combined | ? | ? | ? | ? | ? |

CascadeState was the dominant feature in the prior analysis (20/82 weight points, largest ablation impact). It's a categorical property of the zone itself — observable before entry, no binning needed.

⚠️ Reminder: CascadeState describes what happened at the PRIOR zone level, not the current touch. PRIOR_HELD = a prior zone at this level held. PRIOR_BROKE = a prior zone at this level was broken. NO_PRIOR = no prior zone history at this level.

Key questions:
- If PRIOR_HELD PF >> PRIOR_BROKE PF: cascade state is a structural edge driver — zones that previously held are more reliable. Feature 4 (Cascade State) in Prompt 1a is capturing a real population property.
- If PRIOR_BROKE PF < 1.0: broken zones are structural losers. Filtering them is removing known bad trades, not curve fitting.
- If all three are similar: cascade state doesn't drive the edge at the population level. Its prior importance may have been an artifact of incomplete data.

---

#### 2g: Timeframe Split

At the median grid cell:

| Timeframe | PF @3t | PF @4t | Trades | SBB Rate | R/P @60 |
|-----------|--------|--------|--------|----------|---------|
| 15m | ? | ? | ? | ? | ? |
| 30m | ? | ? | ? | ? | ? |
| 60m | ? | ? | ? | ? | ? |
| 90m | ? | ? | ? | ? | ? |
| 120m | ? | ? | ? | ? | ? |
| 240m | ? | ? | ? | ? | ? |
| 360m | ? | ? | ? | ? | ? |
| 480m | ? | ? | ? | ? | ? |
| 720m | ? | ? | ? | ? | ? |
| Combined | ? | ? | ? | ? | ? |

⚠️ Reminder: TF determines zone formation bar length and strongly correlates with SBB rate (15m ~30% vs 720m ~46% in the data). If HTF zones show higher PF but also higher SBB rates, that's a structural tension the scoring model must resolve.

Key questions:
- Do HTF zones (90m+) outperform LTF zones (15m/30m)? If yes, Feature 1 (Timeframe) is capturing a real population property.
- Does the TF edge persist after removing SBB touches? (Cross-reference with 2b SBB split — run TF × SBB if any TF shows PF > 1.5)
- Is there a TF below which zones have no edge? If 15m PF < 1.0 even for NORMAL touches, those zones may not be worth trading regardless of features.

⚠️ Reminder: all splits in Step 2 (direction, session, SBB, per-period, CascadeState, TF, seq) use ALL periods with no parameters fit. These are population properties. The baseline anchor is the MEDIAN cell PF.

---

#### 2h: Touch Sequence Split

At the median grid cell:

| Seq | PF @3t | PF @4t | Trades | R/P @60 |
|-----|--------|--------|--------|---------|
| 1 | ? | ? | ? | ? |
| 2 | ? | ? | ? | ? |
| 3 | ? | ? | ? | ? |
| 4 | ? | ? | ? | ? |
| 5+ | ? | ? | ? | ? |
| Combined | ? | ? | ? | ? |

The prior analysis found seq ≤ 3 was the sweet spot. If seq 1-3 show PF > 1.0 but seq 5+ shows PF < 1.0, that's a population property — the seq gate in Prompt 2 is structural, not curve fitting.

⚠️ Reminder: seq also drives null rates for Features 8, 10, 19, 20. Seq 1 touches lack prior-touch history. If seq 1 has a different PF profile than seq 2-3, that's informative — the prior-touch features can only help for seq ≥ 2.

---

#### 2i: Time Cap Sensitivity

For the median stop/target, report PF at all 4 time caps:

| Time Cap | PF @3t | Trades |
|----------|--------|--------|
| 30 bars | ? | ? |
| 50 bars | ? | ? |
| 80 bars | ? | ? |
| 120 bars | ? | ? |

This reveals the edge's time structure: does the edge appear immediately (low time cap best) or develop slowly (high time cap best)?

---

#### 2j: Baseline Verdict

Combine all findings. The baseline determines the **overfit risk level** — not whether the strategy works. Features may create an edge even if the unfiltered population is unprofitable.

- **PF > 1.0 across >70% of the 120 exit grid cells AND median CI excludes 1.0:** Zone touches have a statistically confirmed inherent edge. Features refine it. LOW overfit risk — even a weak scoring model should be profitable.
- **PF > 1.0 across 30–70% of the 120 cells OR median CI includes 1.0:** Moderate/uncertain edge. Features needed to select the profitable subset. MODERATE overfit risk — features must do meaningful work, but the raw material has promise.
- **PF > 1.0 across <30% of the 120 cells AND median CI includes 1.0:** No robust unfiltered edge. Features must create the entire edge by separating winners from losers. HIGH overfit risk — but viable if Prompt 1a screening identifies STRONG features with large R/P spreads. Proceed to screening before judging.

⚠️ **A baseline PF < 1.0 does NOT mean stop.** It means the average zone touch isn't profitable — but a profitable subset may exist. The critical question shifts to Prompt 1a: can individual features reliably separate that subset? If yes, the strategy works despite a weak baseline.

**Cost robustness:** Also check: does the median cell PF stay > 1.0 at 4t cost? If the edge disappears at pessimistic cost assumptions, it's fragile even for the unfiltered population.

⚠️ **The baseline anchor = MEDIAN cell PF @3t with 95% CI.** This is the honest reference for the entire pipeline. Every feature, filter, and scoring model must justify how much it improves over this anchor.

Print: "RAW BASELINE: Median PF @3t = [X] (95% CI: [lower]–[upper]) across 120 grid cells. Best cell PF = [Y]. [Z]% of cells > 1.0. Population R/P @60bars = [R]. SBB split: NORMAL=[A], SBB=[B]. Per-period: P1a=[X], P1b=[X], P2a=[X], P2b=[X]. Direction: Demand=[X], Supply=[X]. Session: RTH=[X], Overnight=[X]. Cascade: HELD=[X], BROKE=[X], NO_PRIOR=[X]. TF: 15m=[X], 30m=[X], 60m=[X], 90m=[X], 120m=[X], 240m=[X], 360m=[X], 480m=[X], 720m=[X]. Seq: 1=[X], 2=[X], 3=[X], 4=[X], 5+=[X]."

---

## Required Outputs (saved for Prompt 1a)

| Output File | Contents |
|-------------|----------|
| `baseline_report_clean.md` | Raw edge baseline: MEDIAN cell PF @3t with bootstrap 95% CI (the anchor) across 120 grid cells, best cell PF, % of grid > 1.0, population R/P ratios at 4 horizons (reference for feature screening), SBB split (NORMAL vs SBB), per-period stability (P1a/P1b/P2a/P2b), direction split (demand vs supply), session split (RTH vs overnight), CascadeState split (PRIOR_HELD vs PRIOR_BROKE vs NO_PRIOR), TF split (per timeframe PF + SBB rate), seq split (per-seq PF), seq distribution of trades taken, time cap sensitivity, baseline verdict. Uses ALL periods — no parameters fit. |

⚠️ **Handoff contract to Prompt 1a:** This file is the single output. Prompt 1a also loads the merged CSVs and bar data directly from data prep — but only P1 (P1a + P1b) for calibration. The baseline report is the anchor everything downstream references.

---

## Review Gate

**Before proceeding to Prompt 1a, the user reviews:**

1. **Baseline verdict** — is there an inherent edge? (LOW/MODERATE/HIGH overfit risk)
2. **Bootstrap CI** — does the median cell's 95% CI exclude 1.0?
3. **SBB split** — is the edge in NORMAL touches, SBB touches, or both? If NORMAL PF >> SBB PF, SBB filtering is a structural mechanism.
4. **Per-period stability** — is the edge consistent or concentrated?
5. **Direction split** — do both demand and supply contribute?
6. **Session split** — do both RTH and overnight contribute?
7. **CascadeState split** — is the edge in PRIOR_HELD zones? Are PRIOR_BROKE zones structural losers?
8. **TF split** — which timeframes have an edge? Does any TF lack an edge entirely?
9. **Seq split** — does performance degrade at higher seq? Is seq ≤ 3 a structural filter?

⚠️ **If baseline median PF < 1.0:** This does NOT mean stop. It means the unfiltered population isn't profitable — features must create the edge. Proceed to Prompt 1a to see if features can separate.

⚠️ **If NORMAL PF > 1.0 but SBB PF << 1.0:** The edge exists but is masked by SBB contamination. Strong signal to proceed.

---

## Context Reminders

⚠️ **Every 25–35 lines of code, reinforce:**
- ALL periods used in this prompt — no parameters fit
- Baseline anchor is MEDIAN cell PF (not best cell)
- Every split (2a–2j) is a population property

⚠️ **After Step 2j (verdict):** Print the full baseline summary. This is the single most important output of the entire pipeline — everything else is measured against it.

✅ **Prompt 0 self-check (run before saving outputs):**
- [ ] ALL periods loaded and used (9,361 touches)
- [ ] No parameters fit anywhere in this prompt
- [ ] Baseline anchor is MEDIAN cell PF across 120 grid cells (not best cell)
- [ ] Bootstrap 95% CI computed on median and best cell PF
- [ ] Median cell risk profile reported (win rate, avg trade PnL, max consecutive losses)
- [ ] SBB split reported (NORMAL vs SBB baselines separately)
- [ ] Per-period stability reported (P1a/P1b/P2a/P2b separately)
- [ ] Direction split reported (demand vs supply separately)
- [ ] Session split reported (RTH vs overnight separately)
- [ ] CascadeState split reported (PRIOR_HELD vs PRIOR_BROKE vs NO_PRIOR)
- [ ] TF split reported (per-timeframe PF + SBB rate)
- [ ] Seq split reported (per-seq PF)
- [ ] Seq distribution of trades taken reported (after no-overlap filter)
- [ ] Population R/P ratios at 4 horizons reported
- [ ] Cost robustness checked (@4t in addition to @3t)
- [ ] Time cap sensitivity reported
- [ ] Baseline verdict printed (LOW/MODERATE/HIGH)
- [ ] Full baseline summary string printed
- [ ] `baseline_report_clean.md` saved
