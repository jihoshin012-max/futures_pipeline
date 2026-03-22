# NQ Zone Touch — Expanded Exit Sweep Specification

> **Version:** 1.0
> **Date:** 2026-03-22
> **Scope:** Phased exit parameter sweep — staggered exits, graduated stop step-up, trail with distance
> **Prerequisite:** Prompt 2 outputs (frozen scoring models, segmentation params) + backtest engine with `exit_type` tracking
> **When to run:** Before next pipeline iteration. Results feed into updated Prompt 2 exit grid.

---

## Purpose

The current exit grid (Prompt 2 v3.1) tested 5 stops × 7 targets × 4 BE triggers × 4 trail triggers × 4 time caps = 2,240 single-leg combos. The optimizer selected Stop=190t, Target=60-80t, no BE, no trail, TimeCap=120.

This expanded sweep tests four additional dimensions the original grid couldn't explore:
1. **Staggered exits** — multi-leg partial profit-taking (1/3 at T1, 1/3 at T2, 1/3 at T3)
2. **Graduated stop step-up** — move stop to specific levels at MFE thresholds (not just break-even)
3. **Trail with configurable distance** — trail at a fixed distance behind price after MFE trigger
4. **Re-entry after step-up exit** — if price returns to zone after a profitable step-up exit, re-enter

⚠️ **Overfitting control:** The sweep is phased. Each phase runs ≤ 3,100 combos. Only the top 3 winners from each phase advance to the next. This prevents testing 450K+ combos on ~40 trades.

---

## Three Rules (non-negotiable)

1. **P1 only.** All sweep results use P1 simulation data. P2 is not touched.
2. **Same simulation specs.** Entry = next bar open after touch bar. Intra-bar conflict = stop fills first. Cost = 3t.
3. **Phase discipline.** Each phase completes fully before the next begins. No cherry-picking mid-phase.

⚠️ These rules apply to every phase. P2 data is NOT loaded.

---

## Instrument Constants

- **Tick size:** 0.25 points
- **Tick value:** $5.00 per tick per contract
- **Cost model:** 3 ticks ($15.00) per round-turn per contract
- **Bar type:** 250-volume bars

---

## Populations to Sweep

Run all 4 phases on both groups that will be paper traded:

| Group | Scoring | Seg | Filter | P1 Trades | Current Best |
|-------|---------|-----|--------|-----------|-------------|
| **CT mode** | A-Cal ModeB | seg3 | Counter-trend + high score + TF ≤ 120m | ~40 | Stop=190t, Target=80t, TC=120 |
| **All mode** | A-Cal ModeA | seg1 | High score + TF ≤ 120m + seq ≤ 5 | ~134 | Stop=190t, Target=60t, TC=120 |

⚠️ Both groups use the same frozen A-Cal scoring model and feature set (F10, F04, F01, F21). Only exit parameters change.

---

## Phase 1: Core Exit Shape (~3,100 combos)

**Purpose:** Find the best combination of legs, targets, stop, and time cap. No step-up or trail — those are Phase 2-3.

⚠️ Reminder: P1 only. Current best PF for CT mode = 30.58 (P1), for All mode = 9.39 (P1).

⚠️ **Minimum trade gate:** Only report/rank combos with ≥ 20 total trades. For multi-leg, count the number of trade entries (not per-leg fills). CT mode (~40 trades) will disqualify some combos with aggressive filters — this is expected and correct. A PF on 12 trades is noise.

### Single-leg (100 combos)

| Parameter | Values |
|-----------|--------|
| Target | 40t, 60t, 80t, 120t |
| Stop | 90t, 120t, 160t, 190t, 240t |
| Time cap | 30, 50, 80, 120, 160 bars |

### Two-leg (600 combos)

| Parameter | Values |
|-----------|--------|
| T1 | 40t, 60t, 80t, 120t |
| T2 | 80t, 120t, 160t |
| Stop | 90t, 120t, 160t, 190t, 240t |
| Time cap | 30, 50, 80, 120, 160 bars |
| Size split | 50/50, 67/33 |

⚠️ Constraint: T2 > T1 always. Skip invalid combos (e.g., T1=120, T2=80).

### Three-leg (2,400 combos)

| Parameter | Values |
|-----------|--------|
| T1 | 40t, 60t, 80t, 120t |
| T2 | 80t, 120t, 160t |
| T3 | 160t, 200t, 240t, 300t |
| Stop | 90t, 120t, 160t, 190t, 240t |
| Time cap | 30, 50, 80, 120, 160 bars |
| Size split | 33/33/33, 50/25/25 |

⚠️ Constraint: T3 > T2 > T1 always. Skip invalid combos.

⚠️ **Three-leg fill rate on small populations:** On CT mode (~40 trades), T3 at 200-300t may fill on fewer than 5 trades. If T3 fill rate < 15%, the three-leg PF is dominated by T1/T2 — it's effectively a two-leg config with dead weight. Report T3 fill rate for all three-leg winners. If T3 fills < 15%, flag and prefer the equivalent two-leg config.

### Phase 1 reporting

For each population (CT mode and All mode), report:

| Rank | Legs | Targets | Split | Stop | TimeCap | PF @3t | Trades | Profit/DD | Target% | Stop% | TCap% |
|------|------|---------|-------|------|---------|--------|--------|-----------|---------|-------|-------|
| 1 | ? | ? | ? | ? | ? | ? | ? | ? | ? | ? | ? |
| 2 | ? | ? | ? | ? | ? | ? | ? | ? | ? | ? | ? |
| 3 | ? | ? | ? | ? | ? | ? | ? | ? | ? | ? | ? |

⚠️ Include exit_type breakdown for every top-3 winner. Compare against current best.

Print: "Phase 1 winners — CT mode: [config]. All mode: [config]. Advancing top 3 per population to Phase 2."

### Phase 1 per-leg stop behavior (multi-leg winners only)

If any top-3 winner is multi-leg, also test these 3 stop behaviors on that winner:
- **Shared stop:** All legs exit at same stop level (default)
- **Move after T1:** After T1 fills, remaining legs' stop moves to entry (0t)
- **Move after T2:** After T2 fills, remaining leg's stop moves to T1

This adds ≤ 9 combos (3 behaviors × up to 3 multi-leg winners). Report whether per-leg stop improves PF.

---

## Phase 2: Graduated Stop Step-Up (~800 combos)

**Purpose:** Test moving the stop to specific levels as price moves favorably. Run on the top 3 Phase 1 winners per population only.

⚠️ Reminder: P1 only. Phase 1 results are locked — do not re-run Phase 1.

⚠️ **Impact gate for small populations:** Step-ups only affect trades that (a) reach the MFE trigger AND (b) subsequently retrace to the step-up level. On CT mode (~40 trades, ~1 stop exit on P1), step-ups will change the outcome of 1-3 trades — too few to measure a real improvement.

**How to count trades affected:** Simulate the Phase 1 winner (no step-up) and the Phase 2 candidate (with step-up) on the same population. Compare trade-by-trade: a trade is "affected" if its exit_type OR PnL changed between the two configs. Report the count.

For populations where Phase 2 changes < 3 trade outcomes, report the result but flag as **"LOW IMPACT — fewer than 3 trades affected, result is noise on this sample."** Do NOT advance a LOW IMPACT winner over the Phase 1 winner.

For each of the top 3 Phase 1 winners (per population):

### Step-up Level 1

| Parameter | Values |
|-----------|--------|
| Trigger (MFE) | 20t, 30t, 40t, 60t |
| Destination | -20t, -10t, 0t (BE), +10t, +20t, +30t |

= 24 combos per winner

### Step-up Level 1 + Level 2

| Parameter | Values |
|-----------|--------|
| L1 Trigger | 20t, 30t, 40t, 60t |
| L1 Destination | -10t, 0t, +10t, +20t |
| L2 Trigger | 60t, 80t, 100t, 120t |
| L2 Destination | +10t, +20t, +30t, +40t, +60t |

⚠️ Constraint: L2 Trigger > L1 Trigger always. L2 Destination > L1 Destination always. Skip invalid combos.

≈ 240 combos per winner (after constraints)

### Phase 2 reporting

For each population, report:

| Rank | Base (from P1) | L1 Trigger | L1 Dest | L2 Trigger | L2 Dest | PF @3t | Trades | Profit/DD | vs Phase 1 Best |
|------|---------------|------------|---------|------------|---------|--------|--------|-----------|-----------------|
| 1 | ? | ? | ? | ? | ? | ? | ? | ? | +? |
| 2 | ? | ? | ? | ? | ? | ? | ? | ? | +? |
| 3 | ? | ? | ? | ? | ? | ? | ? | ? | +? |

⚠️ **Key question:** Does step-up improve Profit/DD even if PF is similar? Converting a -190t stop loss into a -10t or +10t exit on 1-2 trades could meaningfully reduce max drawdown without changing PF much.

Print: "Phase 2 winners — CT mode: [config]. All mode: [config]. Step-up impact: [improved/no change/degraded]. Advancing top 3 to Phase 3."

---

## Phase 3: Trail with Distance (~48 combos)

**Purpose:** Test trailing stop activation after MFE threshold. Run on top 3 Phase 2 winners per population only.

⚠️ Reminder: P1 only. Phase 1 and Phase 2 results are locked.

⚠️ **Same impact gate as Phase 2:** Trail only affects trades that reach MFE trigger and then retrace far enough to hit the trailing stop instead of the target. On high-target-rate populations (87-94% target exits), trail changes very few outcomes. Flag as LOW IMPACT if < 3 trades affected.

For each of the top 3 Phase 2 winners (per population):

| Parameter | Values |
|-----------|--------|
| Trail trigger (MFE) | 80t, 100t, 120t, 160t |
| Trail distance | 30t, 40t, 60t, 80t |

= 16 combos per winner

⚠️ **Interaction with step-up:** Trail activates AFTER step-ups. If step-up moved stop to +20t and trail triggers at MFE 100t with distance 40t, the trailing stop starts at 100t - 40t = +60t (replacing the +20t step-up level). Trail only moves the stop forward, never backward.

### Phase 3 reporting

For each population, report:

| Rank | Base (from P2) | Trail Trigger | Trail Dist | PF @3t | Trades | Profit/DD | vs Phase 2 Best | vs Current Deployed |
|------|---------------|---------------|------------|--------|--------|-----------|-----------------|---------------------|
| 1 | ? | ? | ? | ? | ? | ? | +? | +? |

⚠️ Include the full exit configuration chain: targets/legs/split + stop + step-ups + trail + time cap.

Print: "Phase 3 final — CT mode: [full config]. All mode: [full config]."

---

## Phase 3b: Re-Entry After Step-Up Exit (~36 combos)

**Purpose:** If Phase 2 found beneficial step-ups, some trades will exit at the step-up level when price retraces. Those trades had correct direction (price bounced past the MFE trigger) but price came back. Re-entry asks: should you re-enter when price returns to the zone?

⚠️ **Skip this phase entirely if Phase 2 found step-ups don't help** (i.e., Phase 2 best = Phase 1 best for both populations). No step-up exits means no re-entry candidates.

⚠️ Reminder: P1 only. Phases 1-3 results are locked.

For each of the top 3 Phase 3 winners per population (only those with active step-ups):

| Parameter | Values |
|-----------|--------|
| Re-entry window | 10, 20, 30 bars after step-up exit |
| Re-entry condition | Price returns within 10t of original entry price |
| Re-entry exit | Same target/stop as original (full reset), OR reduced target only (remaining distance to original target) |

= 6 combos per winner (3 windows × 2 exit modes)

⚠️ **No re-entry on stop exits or time cap exits.** Only on step-up exits where the trade was profitable at exit. The thesis is: the zone held (proved by MFE reaching step-up trigger), price temporarily retraced, the zone may hold again.

### Phase 3b reporting

| Rank | Base (from P3) | Window | Exit Mode | Re-entries | Re-entry WR | Re-entry PF | Combined PF @3t | vs Phase 3 Best |
|------|---------------|--------|-----------|------------|-------------|-------------|-----------------|-----------------|
| 1 | ? | ? | ? | ? | ? | ? | ? | +? |

⚠️ **Report re-entry trades both separately and combined.** Re-entry PF = PF of re-entry trades only. Combined PF = original + re-entry trades together. If re-entry PF < 1.0, the re-entries are dilutive even if combined PF is still positive — flag this.

Print: "Phase 3b — Re-entry impact: [improved/no change/skipped]. CT mode: [config]. All mode: [config]."

---

## Phase 4: Final Comparison

⚠️ Reminder: P1 only. All phases complete. Compare the best from each phase against the current deployed configuration.

| Config | Legs | Targets | Stop | Step-up | Trail | Re-entry | TC | PF @3t | Trades | Profit/DD | Max DD | Target% | Stop% | TCap% |
|--------|------|---------|------|---------|-------|----------|-----|--------|--------|-----------|--------|---------|-------|-------|
| Current (CT) | 1 | 80t | 190t | none | none | no | 120 | ? | ? | ? | ? | ? | ? | ? |
| Phase 1 best | ? | ? | ? | none | none | no | ? | ? | ? | ? | ? | ? | ? | ? |
| Phase 2 best | ? | ? | ? | ? | none | no | ? | ? | ? | ? | ? | ? | ? | ? |
| Phase 3 best | ? | ? | ? | ? | ? | no | ? | ? | ? | ? | ? | ? | ? | ? |
| Phase 3b best | ? | ? | ? | ? | ? | ? | ? | ? | ? | ? | ? | ? | ? | ? |

Same table for All mode.

**Decision framework:**
- If Phase 3/3b best PF ≈ current PF (within 10%) but Profit/DD is significantly better: **adopt** — same edge, better risk profile
- If Phase 3/3b best PF > current PF by >10%: **adopt with caution** — the improvement may be P1-specific. Note the added complexity.
- If Phase 3/3b best PF < current PF: **keep current** — simpler is better when performance is equal or worse
- If staggered exits won Phase 1 but step-up/trail/re-entry didn't help in Phase 2-3b: **adopt staggered only** — the core shape matters, management doesn't
- If Phases 2-3b flagged LOW IMPACT for a population: **Phase 1 winner is the final answer for that population** — step-up/trail/re-entry are untestable at this sample size. Paper trading will collect more data to revisit later.

⚠️ **Overfit warning:** The current config (Stop=190, Target=80, no BE/trail, TC=120) was selected from 2,240 combos and survived P2 holdout at PF 5.10. Any new config from this sweep has NOT been holdout-tested. Treat it as a paper trading candidate, not a deployment override. The paper trading period (P3: Mar–Jun 2026) validates both the current config AND any sweep improvement simultaneously.

---

## Required Outputs

| Output File | Contents |
|-------------|----------|
| `exit_sweep_phase1_results.md` | Top 10 per population with full exit profiles |
| `exit_sweep_phase2_results.md` | Step-up impact analysis, top 3 per population |
| `exit_sweep_phase3_results.md` | Trail impact analysis, final best per population |
| `exit_sweep_phase3b_results.md` | Re-entry analysis (if step-ups active), or "SKIPPED — no step-ups" |
| `exit_sweep_final_comparison.md` | Phase 4 table, decision, recommended paper trading configs |
| `exit_sweep_configs.json` | Machine-readable configs for top 3 overall winners per population |

---

## Context Reminders

⚠️ **Every 25–35 lines of code, reinforce:**
- P1 only — no P2 data loaded
- Phase discipline — complete current phase before starting next
- Compare against current deployed config at every phase
- Include exit_type breakdown (target/stop/step-up/trail/time cap %) for every winner

⚠️ **After Phase 1:** Lock Phase 1 results. Only top 3 advance.
⚠️ **After Phase 2:** Lock Phase 2 results. Only top 3 advance.
⚠️ **After Phase 3:** Print full config chain for final winners.

✅ **Sweep self-check:**
- [ ] P1 only — P2 not loaded
- [ ] Phase 1 tested single-leg, 2-leg, and 3-leg with size splits
- [ ] Phase 1 constraints enforced (T3 > T2 > T1)
- [ ] Minimum trade gate (≥ 20) applied to all phases — combos below gate not ranked
- [ ] Three-leg T3 fill rate reported — configs with T3 fill < 15% flagged as effectively two-leg
- [ ] Per-leg stop tested for multi-leg Phase 1 winners
- [ ] Phase 2 constraints enforced (L2 trigger > L1 trigger, L2 dest > L1 dest)
- [ ] Phase 3 trail interacts correctly with step-ups (never moves stop backward)
- [ ] Phases 2-3b: LOW IMPACT flag applied when < 3 trades affected — Phase 1 winner preserved for that population
- [ ] Phase 3b re-entry only runs if Phase 2 found beneficial step-ups — skipped otherwise
- [ ] Phase 3b re-entry only on step-up exits (not stop/time cap exits)
- [ ] Phase 3b re-entry PF reported separately AND combined (flag if re-entry PF < 1.0)
- [ ] Phase 4 comparison includes exit_type breakdown
- [ ] Every phase compared against current deployed config
- [ ] Overfit warning: new configs are paper trading candidates, not deployment overrides
- [ ] All output files saved
