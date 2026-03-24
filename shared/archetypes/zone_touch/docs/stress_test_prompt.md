Stress Test & Position Sizing — Post-Validation Analysis

PURPOSE: Establish statistical confidence, worst-case risk 
profiles, and position sizing for the validated deployment 
modes. Three Monte Carlo methods provide layered confidence. 
Kelly criterion analysis provides sizing framework.

⚠️ Run AFTER Prompt 4 completes and the final mode set is 
confirmed. Use the frozen parameters from Prompt 3 / 
deployment_spec_clean_v32.json. Do NOT recalibrate anything.

⚠️ Run SEPARATELY for each deployed mode:
- A-Eq Seg1 ModeA (FIXED 190t/60t, 96 P2 trades)
- B-ZScore Seg2 RTH (ZONEREL exits, 327 P2 trades)
- Any additional modes confirmed by Prompt 4

Use COMBINED P1+P2 trade populations for maximum sample 
size. The model is frozen — combining periods for stress 
testing does not violate holdout discipline because no 
parameters are being fit.

================================================================
SECTION 1: BOOTSTRAP RESAMPLING (RESHUFFLING)
================================================================

⚠️ Resample the actual trade outcomes with replacement. 
This preserves the exact distribution of wins/losses but 
randomizes their order. Answers: "given these exact trades, 
how much could the equity curve vary from sequencing luck?"

For each mode, using all available trades (P1+P2 combined):

A) Run 10,000 bootstrap resamples. Each resample = same 
number of trades drawn with replacement. For each resample, 
compute the full equity curve and record:

| Metric | Mean | Median | 5th %ile | 95th %ile | Worst |
|--------|------|--------|----------|-----------|-------|
| PF @3t | ? | ? | ? | ? | ? |
| PF @4t | ? | ? | ? | ? | ? |
| Max drawdown (ticks) | ? | ? | ? | ? | ? |
| Max consecutive losses | ? | ? | ? | ? | ? |
| Max consecutive wins | ? | ? | ? | ? | ? |
| Total PnL (ticks) | ? | ? | ? | ? | ? |
| Sharpe ratio | ? | ? | ? | ? | ? |
| Win rate | ? | ? | ? | ? | ? |

⚠️ The 5th percentile is the "bad luck" scenario — what 
performance looks like in the worst 5% of trade orderings. 
This is the conservative planning number.

B) Drawdown duration analysis. For each resample, record 
the longest drawdown duration (number of trades from equity 
peak to recovery). Report:

| Metric | Mean | 5th %ile | 95th %ile | Worst |
|--------|------|----------|-----------|-------|
| Longest DD duration (trades) | ? | ? | ? | ? |
| Longest DD duration (est. days) | ? | ? | ? | ? |

⚠️ Use the mode's trades/day estimate to convert trade 
count to calendar days. A 20-trade drawdown at 1 trade/day 
= 20 trading days ≈ 4 weeks.

C) Probability of ruin. For each resample, check whether 
the equity curve ever drops below -X ticks from the starting 
point (test X = 500, 1000, 1500, 2000 ticks):

| Ruin threshold | % of resamples hitting ruin | Mean trades to ruin |
|---------------|---------------------------|-------------------|
| -500t | ? | ? |
| -1000t | ? | ? |
| -1500t | ? | ? |
| -2000t | ? | ? |

📌 REMINDER: Bootstrap preserves win/loss distribution but 
destroys sequential dependencies. The ACTUAL worst case may 
be worse if losses cluster (addressed in Section 3).

================================================================
SECTION 2: STANDARD MONTE CARLO (FORWARD PROJECTION)
================================================================

⚠️ Generate synthetic trades from estimated parameters. 
This projects forward assuming the edge is real and stable. 
Answers: "if I trade this for 6 months, what's the range 
of outcomes?"

A) Parameter estimation. From the combined P1+P2 trades:

| Parameter | A-Eq ModeA | B-ZScore RTH |
|-----------|-----------|-------------|
| Win rate | ? | ? |
| Mean win (ticks) | ? | ? |
| Std dev win (ticks) | ? | ? |
| Mean loss (ticks) | ? | ? |
| Std dev loss (ticks) | ? | ? |
| Win distribution shape | Normal / Lognormal / Empirical | ? |
| Loss distribution shape | Normal / Lognormal / Empirical | ? |

⚠️ Fit both Normal and Lognormal to win/loss distributions. 
Use the better fit (KS test). If neither fits well, use 
the empirical distribution directly.

B) Forward simulation. Generate 10,000 synthetic equity 
curves of N trades each. Test N = 100, 250, 500, 1000 
(representing ~1 month, ~3 months, ~6 months, ~1 year at 
estimated trade frequency).

For each N, report:

| N trades | Median PnL | 5th %ile PnL | 95th %ile PnL | P(loss) | Median DD | 95th %ile DD |
|----------|-----------|-------------|-------------|---------|----------|-------------|
| 100 | ? | ? | ? | ? | ? | ? |
| 250 | ? | ? | ? | ? | ? | ? |
| 500 | ? | ? | ? | ? | ? | ? |
| 1000 | ? | ? | ? | ? | ? | ? |

⚠️ P(loss) = probability of net negative PnL after N 
trades. If P(loss) at 250 trades is 2%, you have 98% 
confidence of being profitable after ~3 months.

C) Time to equity targets. For a starting capital of 
$25,000 per contract:

| Target | Median trades to reach | 5th %ile | P(never) |
|--------|----------------------|----------|----------|
| +$5,000 | ? | ? | ? |
| +$10,000 | ? | ? | ? |
| +$25,000 (double) | ? | ? | ? |

📌 REMINDER: Standard MC assumes IID trades — each trade 
is independent with the same parameters. This OVERSTATES 
confidence if the edge degrades over time or if losses 
cluster. Section 3 addresses this.

================================================================
SECTION 3: REGIME-SWITCHING MONTE CARLO (MARKOV CHAINS)
================================================================

⚠️ The most realistic simulation. Models the strategy as 
switching between observable states with different 
performance characteristics. Answers: "what happens when 
the strategy enters a bad regime?"

A) State definition. Use ATR regime (already computed) as 
the observable state:

| State | Definition | From baseline |
|-------|-----------|--------------|
| LOW_VOL | ATR < P33 (from P1) | Lower edge, tighter moves |
| MID_VOL | ATR P33-P67 | Baseline conditions |
| HIGH_VOL | ATR > P67 | Wider moves, higher DD |

For each mode, compute performance per state on P1+P2:

| State | Trades | WR | Mean win | Mean loss | PF | Max DD |
|-------|--------|-----|---------|----------|-----|--------|
| LOW_VOL | ? | ? | ? | ? | ? | ? |
| MID_VOL | ? | ? | ? | ? | ? | ? |
| HIGH_VOL | ? | ? | ? | ? | ? | ? |

⚠️ If any state has < 20 trades, merge with the adjacent 
state and use a 2-state model instead of 3-state.

B) Transition matrix estimation. From the ATR time series 
(not trade series — use bar data), estimate the probability 
of transitioning between states:

| From \ To | LOW_VOL | MID_VOL | HIGH_VOL |
|-----------|---------|---------|----------|
| LOW_VOL | ? | ? | ? |
| MID_VOL | ? | ? | ? |
| HIGH_VOL | ? | ? | ? |

Also estimate mean state duration (bars and days):

| State | Mean duration (bars) | Mean duration (days) |
|-------|---------------------|---------------------|
| LOW_VOL | ? | ? |
| MID_VOL | ? | ? |
| HIGH_VOL | ? | ? |

C) Regime-switching simulation. Run 10,000 synthetic paths:

📌 REMINDER: This is the most realistic simulation — it 
models the strategy switching between volatility regimes 
with estimated transition probabilities. The 5th percentile 
from this method is the PLANNING NUMBER for live deployment.

1. Start in a random state (weighted by empirical frequency)
2. Generate trade outcome from that state's distribution
3. After each trade, check for state transition using the 
   Markov transition matrix
4. Continue for N trades

For N = 250 (≈3 months):

| Metric | Mean | 5th %ile | 95th %ile | Worst |
|--------|------|----------|-----------|-------|
| PF @3t | ? | ? | ? | ? |
| Max drawdown (ticks) | ? | ? | ? | ? |
| Max consecutive losses | ? | ? | ? | ? |
| Total PnL (ticks) | ? | ? | ? | ? |
| Time spent in worst state (%) | ? | ? | ? | ? |

D) Worst-regime stress test. Force the simulation to START 
in the worst-performing state and stay there for 50 trades 
before allowing transitions:

| Metric | Worst-state-locked | Normal Markov |
|--------|-------------------|--------------|
| PF after 50 trades | ? | ? |
| Max DD in first 50 | ? | ? |
| Recovery trades after exiting worst state | ? | ? |

⚠️ This simulates "what if I start trading during the 
worst possible market regime and it persists?" If the 
strategy survives 50 trades locked in the bad state, it's 
robust enough for live deployment.

📌 REMINDER: Compare all three methods' 5th percentile DD 
estimates. The Markov MC should produce WIDER confidence 
intervals than bootstrap or standard MC because it accounts 
for regime clustering. If it doesn't, the regime effect is 
small and the simpler methods are adequate.

================================================================
SECTION 4: CROSS-METHOD COMPARISON
================================================================

⚠️ The three methods should AGREE on the general picture 
but DISAGREE on tail risk. Compare:

| Metric | Bootstrap | Standard MC | Markov MC |
|--------|-----------|-------------|-----------|
| Median PF | ? | ? | ? |
| 5th %ile PF | ? | ? | ? |
| Median max DD | ? | ? | ? |
| 95th %ile max DD | ? | ? | ? |
| P(ruin at -1000t) | ? | ? | ? |
| Max consecutive losses (95th) | ? | ? | ? |

⚠️ If Markov MC shows significantly worse tail risk than 
the other two methods, regime effects matter and the 
conservative sizing should use Markov estimates, not 
bootstrap. If all three agree, use the simpler bootstrap 
estimates.

================================================================
SECTION 5: KELLY CRITERION & POSITION SIZING
================================================================

⚠️ Kelly gives the theoretical optimal fraction of capital 
to risk per trade. In practice, nobody uses full Kelly — 
estimation error makes it dangerous.

A) Kelly computation per mode.

For modes with FIXED exits (A-Eq ModeA):
- b = target / stop = 60 / 190 = 0.316
- p = observed WR (use combined P1+P2)
- q = 1 - p
- Full Kelly f* = (b × p - q) / b
- Report f* and the implied position size

For modes with ZONEREL exits (B-ZScore RTH):
- b varies per trade (zone-width dependent)
- Compute Kelly for each zone-width quartile:

| Zone width quartile | Mean b (target/stop) | WR | Kelly f* |
|--------------------|---------------------|-----|---------|
| Q1 (narrowest) | ? | ? | ? |
| Q2 | ? | ? | ? |
| Q3 | ? | ? | ? |
| Q4 (widest) | ? | ? | ? |

⚠️ If Kelly f* varies significantly across zone widths, 
position size should be zone-width-conditional.

B) Fractional Kelly analysis.

| Fraction | f* × κ | Capital risked per trade | Expected geometric growth rate | P(ruin at -20% of capital) |
|----------|--------|------------------------|------------------------------|---------------------------|
| Full Kelly (κ=1.0) | ? | ? | ? | ? |
| 3/4 Kelly (κ=0.75) | ? | ? | ? | ? |
| Half Kelly (κ=0.5) | ? | ? | ? | ? |
| Quarter Kelly (κ=0.25) | ? | ? | ? | ? |
| Tenth Kelly (κ=0.1) | ? | ? | ? | ? |

⚠️ P(ruin) is computed from the Markov MC Section 3 — 
apply each fractional Kelly sizing to the regime-switching 
simulation and report how often the equity drops 20% from 
peak.

C) Estimation error sensitivity. Kelly is only as good as 
the WR and payoff estimates. Test sensitivity:

| WR perturbation | Full Kelly f* | Half Kelly f* | Implied size change |
|----------------|--------------|--------------|-------------------|
| Observed WR | ? | ? | baseline |
| WR - 5pp | ? | ? | ? |
| WR - 10pp | ? | ? | ? |
| WR - 15pp | ? | ? | ? |
| Breakeven WR | ? | ? | 0 (no position) |

⚠️ For A-Eq ModeA: if WR drops from 94.8% to 84.8% 
(-10pp), does half-Kelly still produce positive expected 
growth? If not, the sizing is fragile to edge degradation.

📌 REMINDER: Kelly assumes IID bets. Your trades are NOT 
IID (regime effects from Section 3). Use the Markov MC 
P(ruin) estimates, not the Kelly formula's theoretical 
P(ruin), for actual risk management.

D) Practical sizing recommendation.

Given:
- Account size: $25,000 per contract (NQ margin + buffer)
- Max acceptable DD: user-defined (report for 10%, 15%, 20%)
- Worst-case DD from Markov MC 95th percentile

| Max DD tolerance | Contracts per $25K | Implied Kelly fraction | Expected monthly PnL |
|-----------------|-------------------|----------------------|---------------------|
| 10% ($2,500) | ? | ? | ? |
| 15% ($3,750) | ? | ? | ? |
| 20% ($5,000) | ? | ? | ? |

⚠️ The practical size is: floor(max DD tolerance / 
Markov 95th percentile DD in dollars). This anchors to 
the REALISTIC worst case, not the theoretical Kelly 
optimum.

For multi-mode deployment (A-Eq + B-ZScore RTH running 
simultaneously):

| Metric | A-Eq alone | B-ZScore RTH alone | Combined |
|--------|-----------|-------------------|----------|
| Markov 95th DD (ticks) | ? | ? | ? |
| Markov 95th DD (dollars, 1 contract each) | ? | ? | ? |
| Contracts at 15% DD tolerance | ? | ? | ? |
| Expected monthly PnL at that size | ? | ? | ? |

⚠️ Combined DD is NOT the sum of individual DDs — the 
modes have low overlap and may drawdown at different times. 
Simulate the combined equity curve (union of both modes' 
trades in chronological order) through the Markov MC to 
get the true combined DD distribution.

================================================================
SECTION 6: PARAMETER SENSITIVITY
================================================================

⚠️ How fragile is the strategy to small parameter changes? 
Nudge each frozen parameter ±10% and ±20%:

A) For A-Eq ModeA:

| Parameter | -20% | -10% | Current | +10% | +20% |
|-----------|------|------|---------|------|------|
| Score threshold (45.5) | PF=? | PF=? | PF=? | PF=? | PF=? |
| Stop (190t) | PF=? | PF=? | PF=? | PF=? | PF=? |
| Target (60t) | PF=? | PF=? | PF=? | PF=? | PF=? |
| Time cap (120 bars) | PF=? | PF=? | PF=? | PF=? | PF=? |

B) For B-ZScore Seg2 RTH (report mean across zone widths):

| Parameter | -20% | -10% | Current | +10% | +20% |
|-----------|------|------|---------|------|------|
| B-ZScore threshold (0.50) | PF=? | PF=? | PF=? | PF=? | PF=? |
| Stop multiplier (1.5×ZW) | PF=? | PF=? | PF=? | PF=? | PF=? |
| Target multiplier (1.0×ZW) | PF=? | PF=? | PF=? | PF=? | PF=? |
| Time cap (80 bars) | PF=? | PF=? | PF=? | PF=? | PF=? |
| Seq gate (≤2) | — | — | PF=? | ≤3=? | ≤5=? |

⚠️ If PF changes > 30% with a 10% parameter nudge, that 
parameter is fragile. Flag it. If PF is stable across ±20% 
on all parameters, the model is robust.

📌 REMINDER: This is sensitivity analysis on FROZEN 
parameters. Do NOT optimize — just report how PF changes. 
If a nudge IMPROVES PF, note it but do NOT adopt it. That's 
parameter snooping on validation data.

================================================================
SECTION 7: CONCENTRATION & CALENDAR RISK
================================================================

A) Trade clustering. Are trades evenly distributed or 
concentrated in specific periods?

| Period | Trades | PnL | % of total PnL |
|--------|--------|-----|----------------|
| Week 1-4 | ? | ? | ? |
| Week 5-8 | ? | ? | ? |
| Week 9-12 | ? | ? | ? |
| Week 13+ | ? | ? | ? |

⚠️ If >50% of PnL comes from 2-3 weeks, the equity curve 
is driven by a few hot streaks. The Monte Carlo CIs may 
be optimistic because the underlying process isn't 
stationary.

B) Day-of-week analysis:

| Day | Trades | WR | PF | Avg PnL |
|-----|--------|-----|-----|---------|
| Mon | ? | ? | ? | ? |
| Tue | ? | ? | ? | ? |
| Wed | ? | ? | ? | ? |
| Thu | ? | ? | ? | ? |
| Fri | ? | ? | ? | ? |

C) Gap risk. For all trades, check whether any position 
was open at session close (16:55 ET flatten should prevent 
this, but verify):

| Metric | Value |
|--------|-------|
| Trades open at session boundary | ? |
| Overnight gap exposure instances | ? |
| Max potential gap loss (if position held) | ? |

================================================================
SUMMARY
================================================================

⚠️ Produce a single-page risk summary per mode:

| Metric | A-Eq ModeA | B-ZScore RTH | Combined |
|--------|-----------|-------------|----------|
| Observed PF @4t | ? | ? | ? |
| Bootstrap 5th %ile PF | ? | ? | ? |
| Standard MC 5th %ile PF (250 trades) | ? | ? | ? |
| Markov MC 5th %ile PF (250 trades) | ? | ? | ? |
| Bootstrap 95th %ile max DD (ticks) | ? | ? | ? |
| Markov 95th %ile max DD (ticks) | ? | ? | ? |
| P(ruin at -1000t) — Markov | ? | ? | ? |
| Max consecutive losses (95th %ile) | ? | ? | ? |
| Full Kelly f* | ? | ? | — |
| Half Kelly f* | ? | ? | — |
| Practical contracts at 15% DD tolerance | ? | ? | ? |
| Expected monthly PnL at practical size | ? | ? | ? |
| Breakeven WR | ? | ? | ? |
| WR safety margin (observed - breakeven) | ? | ? | ? |
| Parameter sensitivity (max PF change at ±10%) | ? | ? | ? |
| Calmar ratio (annualized return / max DD) | ? | ? | ? |
| Sortino ratio | ? | ? | ? |

⚠️ The MARKOV estimates are the planning numbers for live 
deployment. Bootstrap and standard MC are optimistic 
comparisons. If all three agree, high confidence. If 
Markov is significantly worse, use Markov for sizing.

RISK VERDICT per mode:
- GREEN: Markov 5th %ile PF > 1.5, P(ruin) < 5%, 
  parameter sensitivity < 20%, WR margin > 10pp
- YELLOW: Markov 5th %ile PF > 1.0, P(ruin) < 15%, 
  some parameter sensitivity
- RED: Markov 5th %ile PF < 1.0, P(ruin) > 15%, or 
  fragile parameters

Save results to stress_test_results.md
