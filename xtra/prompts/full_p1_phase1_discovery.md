# Full-P1 Investigation Phase 1 — Discovery & Feature Analysis

> **⚠️ CRITICAL — READ BEFORE AND AFTER IMPLEMENTATION**
> 1. **This uses FULL P1 (Sep 21 – Dec 14, 2025) for all discovery work.** Not P1a only. The regime change at Nov 2 is intentionally included — settings must survive both regimes.
> 2. **P2 data is reserved for validation only.** P2 will be split into P2a (replication gate) and P2b (final holdout). Do NOT touch P2 in this prompt.
> 3. **Daily flatten at 16:00 ET, RTH-only (09:30-16:00).** This reflects the user's actual trading style. All baselines and features are computed in this context.
> 4. **cost_ticks = 1** for all net PF calculations.
> 5. **This is Phase 1 of 2.** This prompt discovers features and builds the cycle-level dataset. Phase 2 optimizes parameters using this dataset.
> 6. **SpeedRead composite series already exists for all hours.** It does NOT need recomputing. Step 2 FILTERS the existing series to RTH hours (09:30-16:00) for distribution analysis and quintile diagnostics.

---

## Background: Why We're Restarting on Full P1

Prior investigations optimized on P1a only (Sep 21 – Nov 2). Results:
- SpeedRead ≥ 48 reverse filter: **passed P1b** (continuous, NPF=1.117)
- SeedDist=15 + Variant D + daily flatten: **failed P1b** (NPF=0.973, gross PF collapsed)

The P1a/P1b regime difference killed seed optimizations. Full-P1 discovery forces settings to survive both regimes. P2a/P2b replaces P1b as the holdout.

### P2 Holdout Structure (For Future Validation — NOT Used in This Prompt)
P2 tick data covers a separate date range after P1. It will be split:
- **P2a:** Replication gate. Frozen config from Phase 2, one-shot. Catches P1 overfitting.
- **P2b:** Final holdout. Only configs that pass P2a reach here. Untouched until the very end.
- **P2 date range and split boundary:** TBD — determine from actual P2 data file dates before P2a validation prompt is written.

> **⚠️ SETTLED ITEMS BELOW WERE PROVEN ON STRUCTURAL/UNIVERSAL GROUNDS. Do not re-test them. They carry forward unchanged into the new full-P1 analysis.**

### What's Settled (Do NOT Retest)
- StepDist = 25 (rotation step)
- ML = 1 (no geometric martingale)
- Position cap = 2 (FRC)
- Walking anchor on cap hit
- Tick data is ground truth
- Fast markets help rotation (confirmed on both P1a and P1b independently)
- Watch price at 09:30 ET (user constraint — RTH-only trading is a lifestyle choice, not an optimization target)
- SR-block watch price behavior: watch price STAYS FIXED during SpeedRead blocks (Variants F and G tested and both degraded performance — the "stale" watch price is actually accumulated directional signal)
- HMM regime detection: discussed and deferred. Image analysis showed GMMHMM barely improves over basic Gaussian HMM. The marginal gain from sophisticated regime models doesn't justify the complexity over SpeedRead. If SpeedRead is killed for RTH in Step 2, revisit HMM as a separate investigation — do NOT explore it in this prompt.

### What's Being Re-Evaluated on Full P1
- SpeedRead: does it help during RTH? What threshold?
- Seed distance: fixed vs sigma-calibrated
- New features: distance from VWAP, retracement, zigzag structure
- Risk mitigation: adaptive stops, max daily loss

> **⚠️ REMINDER: Full P1 = Sep 21 – Dec 14. RTH only = 09:30-16:00. Daily flatten = 16:00 ET. cost_ticks=1. No P2. This is discovery — no parameter optimization. Phase 2 optimizes.**

---

## Data

- **1-tick data:** `bar_data_1tick_rot` covering full P1 (Sep 21 – Dec 14)
- **250-tick bars:** `NQ_BarData_250tick_rot_P1.csv` (127,567 bars)
  - Close = `Last` column (col 6). Volume = `Volume` column (col 7). Headers have leading spaces — strip whitespace.
  - **Zigzag columns available:** `Zig Zag` (col 14), `Reversal Price` (col 16), `Zig Zag Line Length` (col 17), `Zig Zag Num Bars` (col 18). These are needed for features #4-8.

> **⚠️ CRITICAL: The 250-tick CSV file extends BEYOND P1 (through ~March 2026, into P2 territory). You MUST filter all bar data and zigzag data to P1 dates only (Sep 21 – Dec 14, 2025) before computing any features or rolling statistics. Failure to filter leaks P2 data into the discovery phase.**

  - **Zigzag distribution sanity check:** On the full dataset, median swing size ≈ 11.8 pts, P90 ≈ 24.2 pts, ~158K total swings. After filtering to P1 only, verify similar order of magnitude. If your zigzag extraction produces median < 5 or > 30, something is wrong with the column parsing.
  - **VWAP is NOT a column in this file.** Developing session VWAP must be computed from price and volume data: `VWAP = cumulative(price × volume) / cumulative(volume)` resetting at each session open.
- **SpeedRead composite:** `speedread_250tick.parquet` (existing, covers all hours — filter to RTH for Step 2)
- **Use `run_seed_investigation.py`** simulation function (has daily flatten, RTH support)

---

## Step 1: Full-P1 RTH Baseline (No Filters)

> **⚠️ REMINDER: This baseline has NO SpeedRead filter. It establishes the unfiltered floor for RTH-only daily-flatten trading on full P1. All subsequent improvements are measured against this.**

**Config:**
- V1.1, StepDist=25, cap=2, ML=1, walking anchor
- SeedDist=25 (same as StepDist — not decoupled yet)
- Daily flatten at 16:00 ET
- Watch price at first tick at/after 09:30 ET
- **NO SpeedRead filter**
- cost_ticks=1

**Report:**
- Total cycles, gross PF, net PF @1t, net PnL
- Number of sessions, mean cycles per session
- Daily mean PnL, daily std dev, session win %
- Seed accuracy
- Per-session PnL distribution: P10, P25, median, P75, P90
- Worst 5 sessions, best 5 sessions

**Save as:** `full_p1_rth_baseline.json`

> **⚠️ NOTE: This exact config (SeedDist=25, watch at 09:30, daily flatten, no SpeedRead, full P1) has never been run before — there is no known value to sanity-check against. As a partial check, also run on the P1a portion only (Sep 21 – Nov 2) and confirm it's directionally consistent with the prior P1a daily-flatten baseline (NPF≈1.243, which used watch at 18:00 and had SpeedRead≥48). Expect different numbers but similar order of magnitude.**

---

## Step 2: SpeedRead RTH Recalibration

> **⚠️ THIS IS NOT "shift threshold 48 to RTH." It's a complete re-evaluation from first principles. SpeedRead might not help during RTH at all. The quintile diagnostic determines this.**

### 2A: RTH SpeedRead Distribution

Compute SpeedRead composite distribution for RTH bars only (09:30-16:00 ET) across full P1:
- Mean, median, P10, P25, P75, P90
- Compare with all-hours distribution (already known: centered ~50)
- How much of RTH time is below 48? If < 10%, the old threshold barely filters during RTH.

### 2B: Quintile Diagnostic on RTH Cycles

Using the unfiltered cycle data from Step 1:
1. Tag each cycle with SpeedRead composite at entry
2. Split into 5 quintiles (Q1=slowest RTH, Q5=fastest RTH)
3. Report per quintile: cycles, gross PF, net PF @1t, mean gross PnL

**The table:**

| Quintile | SR Range | Cycles | Gross PF | Net PF @1t |
|----------|---------|--------|----------|-----------|
| Q1 (slow RTH) | ? | ? | ? | ? |
| Q2 | ? | ? | ? | ? |
| Q3 | ? | ? | ? | ? |
| Q4 | ? | ? | ? | ? |
| Q5 (fast RTH) | ? | ? | ? | ? |

> **⚠️ KILL CONDITION: If gross PF is flat across all 5 quintiles (Q5-Q1 spread < 0.15), SpeedRead does NOT help during RTH. Skip threshold optimization. Mark SpeedRead as dead for RTH trading. Proceed to Step 3 without a SpeedRead filter.**

### 2C: Threshold Optimization (If Quintile Diagnostic Shows Signal)

If signal exists, sweep thresholds. Test BOTH directions:
- **Reverse filter (remove slow):** composite < T → skip. Sweep T from P20 to P50 of **cycle-entry composite values** (filtering out the slowest 20-50% of cycles).
- **Forward filter (remove fast):** composite > T → skip. Sweep T from P50 to P80 of cycle-entry composite values (filtering out the fastest 20-50%).

Don't assume the relationship is the same as all-hours. RTH might show a different pattern.

Report: threshold | retained cycles | retention % | gross PF | net PF @1t

Identify the approximate best threshold and direction. **This is a diagnostic — Phase 2 will refine the exact threshold combined with hysteresis.** Do NOT test hysteresis here — that's a Phase 2 optimization refinement (Step 4). Phase 1 identifies the threshold range and filter direction; Phase 2 refines the delivery mechanism.

**Save as:** `speedread_rth_analysis.json` (distribution, quintiles, threshold sweep)

---

> **📌 MID-DOCUMENT CONTEXT REMINDER:**
> - Full P1 (Sep 21 – Dec 14), RTH only (09:30-16:00), daily flatten at 16:00
> - Step 1 = unfiltered baseline (no SpeedRead)
> - Step 2 = SpeedRead RTH recalibration from first principles
> - Step 3 = new features (distance, retracement, zigzag, sigma-band feasibility)
> - Step 4 = summary and dataset output
> - cost_ticks = 1. Do NOT touch P2.

---

## Step 3: Feature Discovery

Using the unfiltered cycle dataset from Step 1, compute candidate features at each cycle entry and evaluate predictive power.

> **⚠️ EVERY feature must be computable at entry time from completed bars only. Max 3 parameters per feature. Each feature needs a one-sentence causal hypothesis.**

### 3A: Compute Features

For each completed cycle in the Step 1 dataset, compute at entry time:

**Distance features (from RF/XGBoost importance analysis):**
1. **distance_vwap:** Distance from developing session VWAP at entry (points). Mechanism: extended price = likely mean reversion = good rotation.
2. **distance_vwap_atr:** distance_vwap normalized by current ATR. Regime-invariant version. Mechanism: same as above but adapts to volatility.
3. **distance_session_mid:** Distance from (session_high + session_low) / 2 at entry. Mechanism: price near center of range = balanced, near extremes = extended.

**Retracement/structure features:**
4. **retracement_pct:** % of most recent zigzag swing retraced at entry. Mechanism: 50% retracement entry more favorable than 10% (deeper into the range).
5. **zigzag_num_bars:** Number of bars in the most recent completed zigzag swing. Mechanism: short swings = rapid oscillation = good for rotation.
6. **zigzag_reversal_distance:** Distance from last confirmed zigzag reversal price at entry. Mechanism: similar to distance features but anchored to market structure.

**Sigma-band features (from rotation distance analysis):**
7. **rotation_mean:** Rolling mean of the last 200 completed zigzag rotation distances on the 250-tick chart. A zigzag rotation distance = absolute price distance from one zigzag reversal point to the next (i.e., the length of one zigzag leg in points, using `Zig Zag Line Length` column or computed as `abs(current_reversal_price - prior_reversal_price)`). This measures MARKET rotation behavior, NOT strategy cycle distances. Window of 200 swings ≈ 1 hour of RTH data (market produces ~200 zigzag swings per RTH hour on 250-tick bars). Mechanism: characterizes current rotation regime independent of strategy settings.
8. **rotation_std:** Rolling std dev of the last 200 completed zigzag rotation distances. Mechanism: wide std = volatile rotations, narrow std = predictable rotations.
9. **entry_sigma_level:** (price distance from watch price at entry) expressed as number of standard deviations from rotation_mean. Mechanism: entries at higher sigma levels = more directional conviction = better cycle quality. This is the core concept from the sigma-band analysis. **NOTE: This feature is only meaningful for SEED entries (which have a watch price). For reversal entries, log as NaN — the reversal always fires at StepDist from anchor, which is fixed at 25. Evaluate this feature on seed cycles only.**

> **⚠️ REMINDER: rotation_mean and rotation_std require 200 completed zigzag swings for stable estimates. On 250-tick bars, this is roughly 1 hour of RTH. Use expanding window until 200 swings available, then rolling 200. Flag warm-up cycles in the dataset. Phase 2 may test alternative window sizes (100, 200, 500) but 200 is the default for discovery.**

**Volume features:**
10. **session_volume_ratio:** Cumulative session volume at entry vs average cumulative volume at same time-of-day. Mechanism: high-activity session = more two-way flow = better rotation.
11. **volume_rate:** SpeedRead's volume component at entry (already computed). Included for completeness.

**Session context features (path-dependent — evaluate separately):**
12. **session_pnl:** Cumulative session PnL before this cycle. Risk management, not cycle quality.
13. **session_cycle_count:** Number of cycles completed this session. Later cycles may be lower quality as the session matures.
14. **prior_cycle_pnl:** PnL of the immediately preceding cycle. Streak detection.

### 3B: Quintile Diagnostic for Each Feature

For each feature, on the full P1 unfiltered cycle dataset:
1. Split cycles into 5 quintiles by feature value
2. Report per quintile: cycles, gross PF, net PF @1t
3. Flag whether gradient is monotonic
4. Compute Spearman rank correlation with cycle gross PnL

**Present as ranked table:**

| Rank | Feature | Params | Correlation | Q1 Gross PF | Q5 Gross PF | Spread | Monotonic? | Causal Hypothesis |
|------|---------|--------|------------|------------|------------|--------|-----------|-------------------|
| 1 | ? | ? | ? | ? | ? | ? | ? | ? |

> **⚠️ REDUNDANCY CHECK: For each feature, also report correlation with SpeedRead composite. Features with |r| > 0.7 against SpeedRead are likely measuring the same thing and won't add value as a combined filter.**

> **⚠️ PATH-DEPENDENT FEATURES (12-14): Rank these separately. They function as session-level risk management, NOT per-cycle quality predictors. Do not conflate with features 1-11.**

### 3C: Sigma-Band Feasibility Assessment

This is the key new concept. Using feature #9 (entry_sigma_level):

1. Split cycles into bins by entry_sigma_level: <0.5σ, 0.5-1.0σ, 1.0-1.5σ, 1.5-2.0σ, >2.0σ
2. Report per bin: cycle count, gross PF, net PF @1t, win rate
3. **Key question:** Does cycle quality improve monotonically with sigma level? If yes, sigma-calibrated seed distance (replacing fixed SeedDist) has a strong foundation.

**Also compute:** rolling rotation_mean and rotation_std across full P1. Plot them over time. Do they shift between regimes (P1a period vs P1b period)? If yes, sigma-band naturally adapts and this explains why fixed SeedDist failed across regimes.

**Kill condition:** If entry_sigma_level shows no monotonic relationship with cycle quality, sigma-band seed is dead. Fixed SeedDist is the simpler and correct approach.

**Save as:** `sigma_band_analysis.json`

---

## Step 4: Summary and Dataset Output

> **⚠️ REMINDER: This step saves the COMPLETE cycle dataset that Phase 2 will use. Every feature must be populated. Missing values flagged. SpeedRead and sigma-band verdicts must be stated clearly so Phase 2 knows which paths to take.**

### 4A: Feature Rankings

Present two ranked lists:
1. **Per-cycle quality features** (#1-11): ranked by quintile spread × monotonicity
2. **Session risk management features** (#12-14): ranked separately

For each surviving feature (spread > 0.15, monotonic, |r| < 0.7 with SpeedRead):
- Is it computable in real-time C++? Note any that require data not available in Sierra Chart.
- Does it require a rolling window of completed cycles (like sigma-band)? If so, note warm-up requirements.

### 4B: Save Complete Cycle Dataset

Save the full P1 RTH cycle dataset with ALL computed features as:
`full_p1_rth_cycles_with_features.parquet`

Fields: entry_time, exit_time, direction, seed_or_reversal, gross_pnl, net_pnl, adds, cap_walks, max_adverse_excursion, cycle_duration, speedread_composite, distance_vwap, distance_vwap_atr, distance_session_mid, retracement_pct, zigzag_num_bars, zigzag_reversal_distance, rotation_mean, rotation_std, entry_sigma_level, session_volume_ratio, volume_rate, session_pnl, session_cycle_count, prior_cycle_pnl

> **⚠️ This dataset is the input for Phase 2. Every field must be populated and verified. Missing values should be flagged (warm-up periods, first cycle of session, etc.).**

### 4C: SpeedRead Verdict

State clearly:
- Does SpeedRead help during RTH? (Yes with threshold X / No)
- If yes: hard cutoff or hysteresis? What parameters?
- If no: SpeedRead is dropped from the config for RTH trading

### 4D: Sigma-Band Verdict

State clearly:
- Does entry_sigma_level predict cycle quality? (Yes / No)
- If yes: what sigma range shows the best cycles? This informs Phase 2's seed sweep.
- If no: Phase 2 uses fixed SeedDist sweep instead

---

> **📌 LATE-DOCUMENT CONTEXT REMINDER:**
> - Full P1, RTH only, daily flatten. cost_ticks=1.
> - Step 1 = unfiltered baseline
> - Step 2 = SpeedRead RTH recalibration (might be killed)
> - Step 3 = 14 features + sigma-band feasibility
> - Step 4 = save everything, clear verdicts on SpeedRead and sigma-band
> - Output dataset feeds Phase 2. Do NOT optimize parameters in this prompt.
> - Do NOT touch P2.

---

## Pipeline Rules (Absolute)

1. **Full P1 for all discovery.** Sep 21 – Dec 14, 2025.
2. **RTH only.** 09:30-16:00 ET. Daily flatten at 16:00.
3. **P2 is UNTOUCHED.** Will be split P2a/P2b in Phase 2.
4. **cost_ticks = 1.**
5. **No final parameter selection in this prompt.** Discover features, measure signal, identify approximate threshold ranges, save dataset. Phase 2 makes final parameter selections and tests refinements (hysteresis, combinations).
6. **SpeedRead might be killed for RTH.** Let the data decide.
7. **Sigma-band might be killed.** Let the data decide.
8. **All features must be entry-time computable from completed bars.**
9. **Max 3 parameters per feature.**

---

## ⚠️ Common Mistakes — Self-Check

**Step 1:**
- [ ] Running on FULL P1 (Sep 21 – Dec 14), NOT P1a only
- [ ] RTH only (09:30-16:00), daily flatten at 16:00
- [ ] NO SpeedRead filter — this is the unfiltered baseline
- [ ] SeedDist = 25 (NOT 15 — that failed P1b)
- [ ] Watch price at 09:30 ET first tick
- [ ] cost_ticks = 1

**Step 2:**
- [ ] RTH-only SpeedRead distribution computed separately from all-hours
- [ ] Quintile diagnostic on RTH cycles only
- [ ] Kill condition checked: is Q1-Q5 spread > 0.15?
- [ ] Both filter directions tested (remove slow AND remove fast)
- [ ] Hysteresis tested if threshold found
- [ ] cost_ticks = 1

**Step 3:**
- [ ] All 14 features computed at entry time from completed bars only
- [ ] Zigzag features (#4-8) use zigzag columns from 250-tick CSV (cols 14, 16, 17, 18)
- [ ] VWAP (#1-2) computed as cumulative(price×volume)/cumulative(volume) from bar data, NOT read from a column
- [ ] rotation_mean/rotation_std (#7-8) use zigzag leg distances (abs distance between consecutive reversal prices), NOT strategy cycle distances
- [ ] Zigzag data filtered to P1 dates only (Sep 21 – Dec 14) — CSV extends beyond P1
- [ ] rotation_mean/rotation_std use rolling 200-swing window (expanding during warm-up), NOT 20
- [ ] Zigzag distribution sanity check: median swing ≈ 11.8 pts on P1 data
- [ ] entry_sigma_level (#9) only evaluated on SEED entries, NaN for reversals
- [ ] Sigma-band features use rolling 20-cycle window (expanding during warm-up)
- [ ] SpeedRead redundancy check: correlation between each feature and SR composite
- [ ] Path-dependent features (12-14) ranked separately
- [ ] Sigma-band feasibility assessed with bin analysis
- [ ] cost_ticks = 1

**Step 4:**
- [ ] Complete cycle dataset saved as parquet with ALL features
- [ ] SpeedRead verdict clearly stated (helps RTH / doesn't help)
- [ ] Sigma-band verdict clearly stated (predicts quality / doesn't)
- [ ] No parameters optimized — discovery only
- [ ] P2 not touched
