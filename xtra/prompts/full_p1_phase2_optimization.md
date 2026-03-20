# Full-P1 Investigation Phase 2 — Optimization & Config Freeze

> **⚠️ CRITICAL — READ BEFORE AND AFTER IMPLEMENTATION**
> 1. **This is Phase 2 of 2.** It uses the cycle dataset and verdicts from Phase 1. Do NOT recompute features or baselines.
> 2. **Full P1 (Sep 21 – Dec 14) for all optimization.** Settings must survive both P1a and P1b regimes.
> 3. **RTH only (09:30-16:00 ET), daily flatten at 16:00 ET.**
> 4. **cost_ticks = 1.**
> 5. **P2 is NOT touched.** The frozen config from this prompt will go to P2a validation in a separate prompt.
> 6. **Adapt based on Phase 1 verdicts.** If SpeedRead was killed for RTH, skip SpeedRead steps. If sigma-band was killed, use fixed SeedDist. Read Phase 1 outputs before starting.

---

## Phase 1 Inputs Required

Before starting, confirm these Phase 1 outputs exist:

- [ ] `full_p1_rth_baseline.json` — unfiltered baseline metrics
- [ ] `speedread_rth_analysis.json` — SpeedRead verdict + threshold (or "killed")
- [ ] `sigma_band_analysis.json` — sigma-band verdict (or "killed")
- [ ] `full_p1_rth_cycles_with_features.parquet` — complete cycle dataset with all 14 features
- [ ] Phase 1 feature ranking table — which features showed signal, which were redundant with SpeedRead

**Read and state the two key verdicts before proceeding:**
1. SpeedRead RTH: helps (with threshold X) or killed?
2. Sigma-band: predicts cycle quality or killed?

---

## Step 1: Seed Distance Optimization

> **⚠️ ADAPT BASED ON SIGMA-BAND VERDICT:**
> - **If sigma-band HELPS:** Test sigma-calibrated seed. Sweep N from 0.5σ to 2.0σ in 0.25 increments. SeedDist = rolling rotation_mean + N × rolling rotation_std (where rotation_mean/std come from zigzag market rotations on 250-tick bars, rolling 200-swing window, NOT strategy cycle distances). Also test fixed SeedDist 15, 20, 25, 30 as comparison.
> - **If sigma-band KILLED:** Test fixed SeedDist only: 15, 20, 25, 30, 35.

### 1A: Seed Distance Sweep

> **⚠️ IMPORTANT: Sigma-band configs change the seed distance dynamically per cycle. The Phase 1 cycle dataset was run with fixed SeedDist=25 and CANNOT be reused for sigma-band testing. You MUST re-run the simulation for each sigma-band config. Fixed SeedDist configs also need fresh simulation runs since the seed distance affects which cycles occur and when. Use `run_seed_investigation.py` for all simulations.**

> **⚠️ DATA FILTERING: The 250-tick CSV extends beyond P1 into P2 territory. All zigzag data and bar data MUST be filtered to P1 dates (Sep 21 – Dec 14, 2025) before computing rolling statistics. This applies to sigma-band rolling windows, adaptive stop rolling windows, and any feature that reads zigzag columns.**

For each candidate, run on full P1 with:
- Daily flatten 16:00 ET, watch price at 09:30 ET
- StepDist=25, cap=2, ML=1, walking anchor
- SpeedRead filter from Phase 1 verdict (if applicable), OR no filter (if SpeedRead killed)
- cost_ticks=1

Report per seed config:

| Seed Config | Cycles | Net PF | Net PnL | Daily Mean | Daily StdDev | Session Win% | Seed Accuracy |
|-------------|--------|--------|---------|------------|-------------|-------------|--------------|
| Fixed SD=15 | ? | ? | ? | ? | ? | ? | ? |
| Fixed SD=20 | ? | ? | ? | ? | ? | ? | ? |
| Fixed SD=25 | ? | ? | ? | ? | ? | ? | ? |
| Fixed SD=30 | ? | ? | ? | ? | ? | ? | ? |
| 0.5σ | ? | ? | ? | ? | ? | ? | ? |
| 0.75σ | ? | ? | ? | ? | ? | ? | ? |
| 1.0σ | ? | ? | ? | ? | ? | ? | ? |
| ... | | | | | | | |

> **⚠️ FOR SIGMA-BAND CONFIGS: Report the effective SeedDist range (min/max/mean of the rolling threshold across P1). If it varies from 8 to 40 points, that's good — it's adapting. If it stays at 22-28, it's barely different from fixed SD=25. Also enforce a minimum floor of 10 points — if the sigma formula produces SeedDist < 10, clamp to 10 to avoid triggering on noise.**

### 1B: Sensitivity Check

For the top 2 candidates (by net PF):
- Plot net PF vs seed parameter. Must be smooth, not spiky.
- For sigma-band: does performance degrade gracefully if N is ±0.25 from optimal?
- For fixed: does performance degrade gracefully if SD is ±5 from optimal?

**Kill condition for sigma-band:** If the best sigma-band config doesn't beat the best fixed SeedDist by > 3% NPF, the added complexity isn't justified. Use fixed.

---

## Step 2: Adaptive Stop & Risk Mitigation

> **⚠️ REMINDER: These are evaluated by worst-day improvement vs mean PnL cost, NOT by net PF alone. A stop that reduces net PF by 2% but cuts worst-day loss by 40% is valuable.**

Using the best seed config from Step 1, test risk mitigation overlays:

### 2A: Adaptive Cycle Stop

Flatten a cycle if its adverse excursion exceeds N × rolling std dev of recent zigzag rotation distances (200-swing rolling window, same as sigma-band features — market behavior, not strategy cycle history).

Sweep N: 1.5, 2.0, 2.5, 3.0 (and "no stop" baseline)

For each, report:
- Net PF @1t
- Net PnL
- Number of cycles stopped
- % of stopped cycles that would have recovered **(to compute this: for each stopped cycle, continue the simulation from the stop point without the stop to see if price eventually reversed StepDist in favor from the last anchor. This is a counterfactual — compare actual stopped PnL vs what the cycle would have produced if left alone.)**
- Mean PnL of stopped cycles
- **Worst session PnL** (the key metric — does the stop protect tail risk?)
- **Max single-cycle loss** (with and without stop)

### 2B: Max Daily Loss Stop

Flatten and stop trading for the day if session PnL drops below -X ticks.

Sweep X: -100, -150, -200, -250 (and "no stop" baseline)

For each, report:
- Net PF @1t
- Net PnL
- Sessions stopped early
- Mean PnL on stopped days (how bad were they going to get?)
- **Worst session PnL** (capped by the stop vs uncapped)
- Cycles forfeited (cycles that would have occurred after the stop)

> **📌 MID-DOCUMENT CONTEXT REMINDER:**
> - Full P1, RTH only, daily flatten. cost_ticks=1.
> - Step 1 = seed optimization (sigma-band or fixed, based on Phase 1 verdict)
> - Step 2 = risk mitigation (adaptive cycle stop + max daily loss)
> - Step 3 = feature filters (surviving features from Phase 1)
> - Step 4 = hysteresis for SpeedRead (if applicable)
> - Step 5 = final config assembly and freeze
> - Do NOT touch P2.

### 2C: Max Cap-Walks Per Cycle

If a cycle accumulates more than N cap-walks, flatten and re-enter watching mode.

Sweep N: 2, 3, 4, 5 (and "no limit" baseline)

For each, report same metrics as 2A.

> **⚠️ EVALUATE 2A, 2B, 2C INDEPENDENTLY FIRST, then test the best of each combined. A combined config (e.g., adaptive 2σ stop + max daily loss -150) might behave differently than either alone.**

---

## Step 3: Feature Filters (Top Survivors from Phase 1)

> **⚠️ ONLY test features that passed Phase 1's quintile diagnostic with spread > 0.15, monotonic gradient, AND |r| < 0.7 with SpeedRead.**

> **⚠️ Use the cycle data from Phase 2 Step 1's best seed config simulation, NOT the Phase 1 cycle dataset. The seed distance may have changed, which changes which cycles occur and when. Feature values must be recomputed on the new simulation output.**

For each surviving feature from Phase 1:
1. Using the cycle dataset, sweep filter thresholds (keeping the feature's top 60-80% of cycles)
2. Report net PF at 60%, 70%, 80% retention
3. Test combined with SpeedRead filter (if SpeedRead survived Phase 1)
4. Test combined with the best seed config from Step 1

**Kill condition per feature:** If adding the feature doesn't improve net PF by > 3% over the base config (seed + SpeedRead if applicable), it's not worth the added complexity.

Present surviving features with:
- Threshold value
- Filter direction
- Net PF improvement
- Retention
- Correlation with SpeedRead (redundancy check)

---

## Step 4: SpeedRead Hysteresis (If SpeedRead Survived Phase 1)

> **⚠️ Skip this step entirely if Phase 1 killed SpeedRead for RTH.**

Using the best SpeedRead threshold from Phase 1 (call it T):

Test hysteresis bands:
- Entry requires SR ≥ T+2, stay active until SR < T-3
- Entry requires SR ≥ T+3, stay active until SR < T-3
- Entry requires SR ≥ T+5, stay active until SR < T-5
- Hard cutoff at T (baseline)

Report: net PF, number of filter state changes per session (fewer = more stable), net PnL.

**The value here is stability, not PF improvement.** Hysteresis that matches hard-cutoff PF but has 50% fewer state changes is better for live trading.

---

## Step 5: Final Config Assembly & Freeze

### 5A: Build the Best Config

Layer components in order, showing incremental improvement:

| Layer | Config | Net PF | Net PnL | Worst Day | Improvement |
|-------|--------|--------|---------|-----------|-------------|
| 0 | Unfiltered baseline (Step 1 of Phase 1) | ? | ? | ? | — |
| 1 | + SpeedRead filter (if survived) | ? | ? | ? | +?% |
| 2 | + Best seed config | ? | ? | ? | +?% |
| 3 | + Best feature filter (if any survived) | ? | ? | ? | +?% |
| 4 | + Best risk mitigation | ? | ? | ? | PF: ?%, worst day: ?% |
| 5 | + Hysteresis (if applicable) | ? | ? | ? | stability |

> **⚠️ EACH LAYER MUST IMPROVE THE CONFIG OR BE DROPPED. No layer is included "because we tested it." If a layer doesn't help, remove it and proceed with the simpler config. Simpler configs generalize better.**

### 5B: Freeze Complete Parameter Table

> **⚠️ EVERY parameter must be specified. No TBD values. No "see Phase 1." This table is the single source of truth for P2a validation and C++ implementation.**

| Parameter | Value | Source |
|-----------|-------|--------|
| StepDist | 25 | Settled |
| SeedDist | ? (fixed value) OR sigma formula | Step 1 |
| SeedDist sigma formula (if applicable) | rotation_mean + N × rotation_std, N=?, window=200 swings, source=zigzag legs on 250-tick, floor=10 | Step 1 |
| Watch price | 09:30 ET first tick | Settled |
| Position cap | 2 | Settled |
| ML | 1 | Settled |
| Anchor mode | Walking | Settled |
| SpeedRead filter | ? (threshold/hysteresis/killed) | Phase 1 + Step 4 |
| Feature filter(s) | ? (or none) | Step 3 |
| Adaptive cycle stop | ? (Nσ or none) | Step 2A |
| Max daily loss | ? (ticks or none) | Step 2B |
| Max cap-walks | ? (or unlimited) | Step 2C |
| Daily flatten | 16:00 ET | Settled |
| Session resume | 09:30 ET | Settled |
| cost_ticks | 1 | Settled |

### 5C: C++ Replication Planning

> **⚠️ This section ensures everything the Python computes can be replicated in Sierra Chart C++. Flag any feature or computation that CANNOT be done in Sierra Chart.**

For each component in the frozen config, document:

1. **Can it be computed in real-time C++?** (Yes/No)
2. **What data does it need?** (price, volume, completed bars, cycle history, etc.)
3. **Does it require state that persists across bars?** (rolling windows, cycle counters, etc.)
4. **How many persistent variables?** (Sierra Chart has limited persistent storage slots)
5. **Warm-up requirements?** (how many bars/cycles before the computation is valid?)

**Specific concerns:**
- **Sigma-band seed:** requires rolling mean/std of last 200 zigzag rotation distances. The autotrader must either: (a) track zigzag completions by reading the zigzag study and maintaining a 200-element circular buffer of leg distances, or (b) compute from the zigzag study's historical subgraph data. Option (b) is simpler if the zigzag study stores leg lengths in a subgraph array.
- **Adaptive stop (rolling σ):** same 200-swing buffer as sigma-band. Shares the computation.
- **Distance from VWAP:** Sierra Chart can compute developing VWAP. Need to confirm the study can read it or compute it internally.
- **Retracement %:** requires zigzag study data. Can read via GetStudyArrayUsingID (same pattern as SpeedRead).
- **Session volume ratio:** needs historical average volume by time-of-day. Requires a lookup table or rolling computation.

For any component that CAN'T be done in C++, flag it and recommend an alternative that can.

### 5D: Save All Artifacts

> **⚠️ REMINDER: Save EVERYTHING. The frozen config table is the single source of truth for P2a validation AND C++ implementation. Every parameter specified, no TBD. C++ feasibility confirmed for every component. Simpler config wins ties.**

- `phase2_seed_sweep.json` — all seed configs and results
- `phase2_risk_mitigation.json` — all stop/limit results
- `phase2_feature_filters.json` — surviving feature filter results
- `phase2_hysteresis.json` — hysteresis comparison (if applicable)
- `phase2_frozen_config.json` — complete frozen parameter table
- `phase2_cpp_replication_plan.json` — C++ feasibility assessment per component
- `phase2_incremental_layers.json` — the layered improvement table

**Update contamination ledger:**
- "Full P1 Phase 1+2: Discovery and optimization on Sep 21 – Dec 14 | All components | Optimized (NOT validated)"

---

## Pipeline Rules (Absolute)

1. **Full P1 for all optimization.** Both regimes must be survived.
2. **RTH only.** 09:30-16:00 ET. Daily flatten at 16:00.
3. **P2 is UNTOUCHED.** Will be split P2a (replication gate) / P2b (final holdout) in a separate validation prompt. Date ranges TBD from actual P2 data.
4. **cost_ticks = 1.**
5. **Simpler configs preferred.** Every added layer must justify its complexity with measurable improvement.
6. **Risk mitigation evaluated by tail risk reduction, not just PF.**
7. **C++ feasibility is a hard constraint.** If it can't be implemented in Sierra Chart, it can't be used.
8. **Adapt to Phase 1 verdicts.** Don't test dead features or killed components.
9. **Use `run_seed_investigation.py`** for all simulations. Same tool as Phase 1.
10. **Watch price at 09:30 ET is SETTLED** (user constraint — RTH-only trading). Do not re-sweep watch price variants.
10. **SR-block watch price stays FIXED during blocks.** Variants F and G were tested and degraded performance. The "stale" watch price is accumulated directional signal. Do NOT implement resets.
11. **HMM regime detection is DEFERRED.** Do not explore HMM in this prompt. If SpeedRead is killed for RTH, HMM becomes a separate future investigation.

---

> **📌 FINAL CONTEXT REMINDER:**
> - Phase 1 provides: unfiltered baseline, SpeedRead RTH verdict, sigma-band verdict, feature rankings, complete cycle dataset
> - This prompt optimizes: seed distance, risk mitigation, feature filters, hysteresis
> - Output: frozen config table, C++ replication plan, layered improvement evidence
> - Next: P2a validation (separate prompt) with the frozen config
> - EVERY component must be C++ implementable

---

## ⚠️ Common Mistakes — Self-Check

**Step 1:**
- [ ] Read Phase 1 sigma-band verdict before choosing fixed vs sigma sweep
- [ ] Read Phase 1 SpeedRead verdict before applying filter
- [ ] Full P1 (NOT P1a only)
- [ ] All bar data and zigzag data filtered to P1 dates (Sep 21 – Dec 14) — CSV extends beyond P1
- [ ] Sigma-band effective range reported (min/max/mean SeedDist)
- [ ] Sigma-band floor of 10 points enforced
- [ ] Sensitivity check performed — smooth curve, not spike
- [ ] cost_ticks = 1

**Step 2:**
- [ ] Risk mitigation evaluated by worst-day improvement, not just NPF
- [ ] Each stop type tested independently FIRST, then combined
- [ ] "Would have recovered" analysis included for adaptive stop
- [ ] Max daily loss measured in ticks (not dollars)
- [ ] cost_ticks = 1

**Step 3:**
- [ ] Only features from Phase 1 with spread > 0.15, monotonic, |r| < 0.7 with SR
- [ ] Features recomputed on Step 1's best seed config simulation, NOT Phase 1 cycle dataset
- [ ] Kill condition: > 3% NPF improvement required to keep
- [ ] Combined with SpeedRead and seed config, not standalone

**Step 4:**
- [ ] Skipped if SpeedRead killed in Phase 1
- [ ] Hysteresis evaluated by stability (fewer state changes) not just PF

**Step 5:**
- [ ] Every parameter has a specific value — no TBD
- [ ] If sigma-band won: formula specifies N value, window size (200 swings), data source (zigzag legs), and floor (10 points)
- [ ] Each layer demonstrably improves or is dropped
- [ ] C++ feasibility confirmed for every component
- [ ] All artifacts saved
- [ ] P2 NOT touched
