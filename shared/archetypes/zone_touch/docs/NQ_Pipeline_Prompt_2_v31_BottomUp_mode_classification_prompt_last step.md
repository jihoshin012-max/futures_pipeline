Mode Deployment Classification — Post-Prompt 2 Analysis

PURPOSE: Classify every mode from Prompt 2's segmentation 
results across 8 deployment dimensions. This is a presentation 
layer over the calibration results — no recalculation, no 
parameter changes. The output is a scorecard that shows which 
modes excel at what, enabling informed multi-mode deployment 
decisions.

⚠️ Run this AFTER Prompt 2 completes. Load the following:
- segmentation_params_clean.json (all frozen parameter sets)
- frozen_parameters_manifest_clean.json (P1 PF, Profit/DD)
- p1_calibration_summary_clean.md (per-group results)
- feature_analysis_clean.md (ablation, B-only verdict)

================================================================
DIMENSION DEFINITIONS
================================================================

Rate every mode HIGH / MEDIUM / LOW on each dimension using 
the criteria below. Thresholds are relative to the full set 
of modes — HIGH = top third, MEDIUM = middle third, LOW = 
bottom third within this analysis.

⚠️ These are relative ratings, not absolute. A mode rated 
LOW on AGGRESSIVE is not bad — it means other modes in the 
set are more aggressive.

1. AGGRESSIVE — maximizes return per trade.
   Metrics: PF, mean PnL per trade, mean winning trade size.
   HIGH: highest PF, largest per-trade PnL, widest targets.
   LOW: smallest per-trade PnL, tightest targets.

2. BALANCED — best risk-adjusted return.
   Metrics: Profit/DD ratio (primary), PF > 2.0, trade 
   count > 50.
   HIGH: best Profit/DD with adequate trade count.
   LOW: poor Profit/DD or too few trades to be reliable.

3. CONSERVATIVE — minimizes drawdown.
   Metrics: max DD (ticks), max consecutive losses, stop 
   distance, win rate.
   HIGH: smallest max DD, tightest stops, highest win rate.
   LOW: largest max DD, widest stops, lowest win rate.

4. VOLUME — maximizes opportunity count.
   Metrics: total trades, trades per day, total cumulative 
   PnL.
   HIGH: most trades per day, highest total PnL.
   LOW: fewest trades, lowest total PnL regardless of 
   per-trade edge.

⚠️ Dimensions 1-4 are performance-based. Dimensions 5-8 
below are stability and deployment-based. A complete mode 
evaluation requires BOTH sets.

5. CONSISTENT — most stable across regimes and periods.
   Metrics: PF variance across P1a vs P1b, DD variance 
   across sub-periods, RTH vs ETH PF spread, trending vs 
   ranging PF spread.
   HIGH: smallest variance across all splits. Performance 
   looks the same regardless of market conditions.
   LOW: large variance — performs well in one regime but 
   poorly in another.

⚠️ To compute CONSISTENT, split each mode's trades by:
   a) P1a vs P1b (temporal stability)
   b) RTH vs ETH (session stability)
   c) WT vs CT vs NT trend labels (regime stability)
   Report PF for each split. Variance across splits = 
   the consistency metric.

6. ROBUST — survives cost and slippage degradation.
   Metrics: PF at 2t, 3t, 4t cost; PF drop from 3t to 4t; 
   win rate margin above breakeven.
   HIGH: PF at 4t is still strong (< 15% drop from 3t). 
   The mode works even with pessimistic execution.
   LOW: PF at 4t drops > 30% from 3t, or approaches 1.0. 
   The mode's edge is fragile to execution quality.

⚠️ ROBUST and SCALABLE are the two dimensions most likely 
to invalidate a mode that looks good on paper. A HIGH-
AGGRESSIVE mode with LOW-ROBUST is dangerous to deploy.

7. SCALABLE — works with multiple contracts and in liquid 
   conditions.
   Metrics: target distance (wider = more room for size), 
   session (RTH = more liquid), trade duration (longer = 
   easier order management), stop distance (wider = less 
   sensitive to fill price).
   HIGH: RTH trades, targets > 100t, stops > 100t, 
   duration > 20 bars.
   LOW: ETH/overnight trades, targets < 60t, stops < 60t, 
   duration < 10 bars.

8. IMPLEMENTABLE — operational simplicity.
   Metrics: number of exit parameters, exit structure type, 
   number of conditional filters.
   HIGH: single-leg exit (1 stop, 1 target, 1 timecap), 
   score threshold + seq gate only, no trailing/BE.
   Assign points: single-leg = 0, 3-leg partial = +2, 
   BE trigger = +1, trail trigger = +1, session-conditional 
   exits = +1, width-conditional exits = +1, TF filter = +1.
   Total complexity score: 0-1 = HIGH, 2-3 = MEDIUM, 4+ = LOW.

================================================================
OUTPUT FORMAT
================================================================

⚠️ Rate every mode on ALL 8 dimensions. Do not skip 
dimensions for modes with low trade counts — rate them 
LOW with a note, don't omit them.

A) Full scorecard — one row per mode, one column per dimension:

| Mode | Model | Seg | PF | Trades | AGG | BAL | CON | VOL | CONS | ROB | SCAL | IMPL |
|------|-------|-----|-----|--------|-----|-----|-----|-----|------|-----|------|------|
| ? | ? | ? | ? | ? | ? | ? | ? | ? | ? | ? | ? | ? |

B) Per-dimension leader — which mode rates highest on each:

| Dimension | Best mode | Rating | Key metric |
|-----------|-----------|--------|-----------|
| AGGRESSIVE | ? | HIGH | PF=? |
| BALANCED | ? | HIGH | Profit/DD=? |
| CONSERVATIVE | ? | HIGH | MaxDD=? |
| VOLUME | ? | HIGH | Trades/day=? |
| CONSISTENT | ? | HIGH | PF variance=? |
| ROBUST | ? | HIGH | PF 3t→4t drop=? |
| SCALABLE | ? | HIGH | Mean target=? |
| IMPLEMENTABLE | ? | HIGH | Complexity=? |

C) Multi-mode deployment recommendation:

⚠️ The scorecard (A) and leaders (B) are informational. 
This section (C) is the actionable output — which modes 
to actually deploy together.

⚠️ Select 2-3 modes that COMPLEMENT each other. Ideal 
combinations cover different dimensions:
- One HIGH-AGGRESSIVE + one HIGH-VOLUME
- One HIGH-CONSERVATIVE + one HIGH-BALANCED
- Avoid pairing two modes that are HIGH on the same 
  dimensions — they're redundant, not complementary

For each recommended combination:

| Metric | Mode A alone | Mode B alone | Combined |
|--------|-------------|-------------|----------|
| Total trades | ? | ? | ? |
| Trade overlap % | — | — | ? |
| Combined PF | — | — | ? |
| Combined max DD | — | — | ? |
| Combined Profit/DD | — | — | ? |

⚠️ Trade overlap: count touches taken by BOTH modes. If 
overlap > 30%, the modes are redundant. Report overlap % 
for every recommended pair.

D) Per-mode deployment card (for each recommended mode):

| Field | Value |
|-------|-------|
| Mode name | ? |
| Scoring model | A-Cal / A-Eq / B-ZScore |
| Threshold | ? |
| Segmentation | ? |
| Group | ? |
| Exit structure | single-leg / 3-leg |
| Stop | ? (fixed or zone-relative) |
| Target | ? (fixed or zone-relative) |
| Time cap | ? bars |
| BE trigger | ? or none |
| Trail trigger | ? or none |
| Seq gate | ≤ ? |
| TF filter | ? or none |
| Width filter | ? or none |
| P1 PF @3t | ? |
| P1 trades | ? |
| P1 max DD | ? |
| P1 Profit/DD | ? |
| Estimated trades/day | ? |
| Profile | AGG/BAL/CON/VOL (primary dimension) |

Save results to mode_classification.md
