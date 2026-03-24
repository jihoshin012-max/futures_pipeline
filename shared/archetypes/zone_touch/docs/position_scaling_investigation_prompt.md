Position Scaling & Deeper Entry Investigation — Queued

PURPOSE: Investigate two related concepts for improving 
trade geometry on qualifying zone touches:

1. POSITION SCALING: Enter multiple contracts at 
   progressively deeper levels within the zone, improving 
   average entry price.

2. DEEPER INITIAL ENTRY: Shift the primary entry from the 
   zone edge to a data-driven depth inside the zone, 
   reducing stop distance and improving risk:reward.

⚠️ Run AFTER Prompt 3 validates the base strategy. These 
are modifications to the validated model, not replacements. 
Use P1 for calibration, P2 for validation. Same holdout 
discipline as the main pipeline.

⚠️ Run this investigation SEPARATELY for each validated 
mode. The optimal entry depth and add structure may differ:

- A-Eq Seg1 ModeA (FIXED exits: Stop=190t, Target=60t): 
  Deeper entry doesn't change the fixed stop, but improves 
  target fill rate. Adds amplify exposure on a mode with 
  96% WR — the 4% losers get 3× more expensive.

- B-ZScore Seg2 RTH (ZONEREL exits: Stop=max(1.5×ZW,120t), 
  Target=1.0×ZW): Deeper entry DIRECTLY reduces stop 
  distance because the stop is anchored to zone structure, 
  not measured from entry. R:R improves on both sides.

- B-ZScore Seg4 LowATR (ZONEREL, Target=0.5×ZW): Same 
  ZONEREL stop benefit. Low ATR = smaller swings = higher 
  probability of reaching deeper entry levels. Fill rate 
  penalty may be smallest for this mode.

Report all tables below PER MODE. Do not aggregate across 
modes — they have different exit structures and the 
tradeoffs differ.

================================================================
PART 1: POSITION SCALING (ADD-INS)
================================================================

⚠️ The current model enters 1 contract at the zone edge. 
This investigation tests entering up to 3 contracts at 
progressively deeper levels within the zone.

A) PRICE DEPTH ANALYSIS — how deep does price go?

For all qualifying touches on P1, measure how far price 
penetrates into the zone before reversing:

| Max penetration depth | Touches | % | Cumulative % |
|----------------------|---------|---|-------------|
| 0-25% of zone width | ? | ? | ? |
| 25-50% of zone width | ? | ? | ? |
| 50-75% of zone width | ? | ? | ? |
| 75-100% of zone width | ? | ? | ? |
| > 100% (beyond opposite edge) | ? | ? | ? |

⚠️ This tells you how often each add level would fire. If 
80% of touches bounce within 25% of the edge, adds at 50% 
depth rarely execute.

B) ADD LEVEL TESTING

Test these add structures against the single-contract 
baseline. All use the same exit parameters from the 
validated model (stop, target, timecap from frozen config).

⚠️ CRITICAL: For ZONEREL modes, the stop LEVEL is anchored 
to zone structure (zone edge + 1.5×ZW on adverse side) and 
does NOT move with entry. Deeper entry reduces the DISTANCE 
from entry to the fixed stop level. For FIXED modes (A-Eq), 
the stop level DOES move with entry (190t from wherever you 
enter). Stop and target PnL are always calculated from the 
actual entry price of each contract.

Structure 1 — Zone-relative adds:
| Contract | Entry level | Condition |
|----------|------------|-----------|
| 1 | Zone edge (current) | Always |
| 2 | 50% of zone width deeper | Price reaches midpoint |
| 3 | 100% of zone width deeper | Price reaches opposite edge |

Structure 2 — Fixed-distance adds:
| Contract | Entry level | Condition |
|----------|------------|-----------|
| 1 | Zone edge (current) | Always |
| 2 | 50t deeper | Price reaches edge + 50t |
| 3 | 100t deeper | Price reaches edge + 100t |

Structure 3 — Aggressive scaling (2× on add):
| Contract | Entry level | Size | Condition |
|----------|------------|------|-----------|
| 1 | Zone edge | 1 lot | Always |
| 2 | 50% zone width deeper | 2 lots | Price reaches midpoint |

⚠️ For each structure, report:

| Metric | Single contract | Structure 1 | Structure 2 | Structure 3 |
|--------|----------------|-------------|-------------|-------------|
| Trades where add 2 fires | — | ? | ? | ? |
| Trades where add 3 fires | — | ? | ? | — |
| Average entry improvement (ticks) | — | ? | ? | ? |
| Win rate | ? | ? | ? | ? |
| PF @3t | ? | ? | ? | ? |
| Mean winning trade PnL | ? | ? | ? | ? |
| Mean losing trade PnL | ? | ? | ? | ? |
| Max drawdown (ticks) | ? | ? | ? | ? |
| Max drawdown (dollars, all contracts) | ? | ? | ? | ? |

⚠️ KEY QUESTION: Does the improved average entry on 
winners outweigh the tripled exposure on losers? Report 
the NET impact — total PnL of the add structure vs total 
PnL of single contract across ALL trades.

C) LOSS AMPLIFICATION ANALYSIS

For the trades that hit the stop (losers), compare:

| Metric | Single contract | With adds |
|--------|----------------|-----------|
| Mean loss per losing trade (ticks) | ? | ? |
| Mean loss per losing trade (dollars) | ? | ? |
| Max single-trade loss (dollars) | ? | ? |
| % of losers where add 2 fired before stop | ? | ? |
| % of losers where add 3 fired before stop | ? | ? |

⚠️ If adds fire on most losers (price pushes deep into 
zone before failing), the add structure amplifies losses 
more than it improves winners. Report the ratio:
(mean winner improvement) / (mean loser amplification)

📌 REMINDER: Adds that only fire on losers are the worst 
outcome — you're scaling into losing trades. Adds that 
fire on winners AND losers proportionally improve average 
entry on both.

D) BOUNCE CONFIRMATION GATE (optional refinement)

Instead of adding blindly at depth levels, wait for a 
bounce confirmation before adding:

| Add rule | Description |
|----------|-------------|
| Blind add | Enter at depth level immediately |
| Bounce confirm | Price reaches depth level, then closes 
  back above 25% of the penetration = add fires |

Compare blind vs bounce-confirmed adds:

| Metric | Blind add | Bounce confirm add |
|--------|----------|-------------------|
| Add 2 fill rate | ? | ? |
| Add 2 win rate | ? | ? |
| Combined PF | ? | ? |

⚠️ Bounce confirmation reduces add frequency but may 
improve add quality. The ray analysis found price stalls 
at structural levels — a bounce off a ray or zone midpoint 
before adding is a stronger signal than adding at a fixed 
depth.

================================================================
PART 2: DEEPER INITIAL ENTRY
================================================================

⚠️ The current model enters at the zone edge. But 
price may frequently penetrate some depth before bouncing. 
If the data shows price typically penetrates 30t into a 
200t zone before reversing, entering at edge+30t instead 
of the edge gives a 30t better entry on average — at the 
cost of missing trades that bounce immediately at the edge.

⚠️ STOP REDUCTION: For ZONEREL modes, deeper entry is a 
direct stop reduction mechanism. The stop is anchored to 
zone structure (1.5×ZW from the EDGE, not from entry). 
Entering deeper means the stop distance from your entry 
is shorter:

| Zone width | Current stop (from edge) | Entry at 20% depth | Stop from entry |
|-----------|------------------------|--------------------|-----------------| 
| 200t | 300t | 40t inside | 260t |
| 300t | 450t | 60t inside | 390t |
| 100t | 150t | 20t inside | 130t |

For FIXED exit modes (A-Eq), the stop stays the same 
distance from entry. The benefit is on the target side — 
price needs less favorable movement to reach the target.

Report the EFFECTIVE STOP DISTANCE from entry for each 
depth level and each mode.

A) OPTIMAL ENTRY DEPTH

Using the depth analysis from Part 1A, find the depth that 
maximizes risk-adjusted return:

For each candidate entry depth (as % of zone width):

| Entry depth | Fill rate | Mean entry improvement | WR | PF @3t | Trades | PF × Trades |
|------------|-----------|----------------------|-----|--------|--------|-------------|
| 0% (edge, current) | 100% | 0t | ? | ? | ? | ? |
| 10% | ? | ? | ? | ? | ? | ? |
| 20% | ? | ? | ? | ? | ? | ? |
| 30% | ? | ? | ? | ? | ? | ? |
| 40% | ? | ? | ? | ? | ? | ? |
| 50% (midpoint) | ? | ? | ? | ? | ? | ? |

⚠️ PF × Trades captures the tradeoff: deeper entry = 
higher PF but fewer trades. The optimal depth maximizes 
the product.

⚠️ Also test FIXED depth offsets (not zone-relative):

| Entry depth | Fill rate | WR | PF @3t | Trades |
|------------|-----------|-----|--------|--------|
| Edge (current) | 100% | ? | ? | ? |
| Edge + 15t | ? | ? | ? | ? |
| Edge + 30t | ? | ? | ? | ? |
| Edge + 50t | ? | ? | ? | ? |

📌 REMINDER: A deeper entry means the stop distance from 
entry is SHORTER (same stop level, better entry price). 
This naturally improves risk:reward. But missed trades 
(price bounces at edge without reaching the deeper entry) 
reduce opportunity.

B) ZONE-WIDTH CONDITIONAL DEPTH

Deeper entry may work better on wide zones (more room) 
than narrow zones (already tight):

| Zone width | Best entry depth | Fill rate | PF | Trades |
|-----------|-----------------|-----------|-----|--------|
| < 100t (narrow) | ? | ? | ? | ? |
| 100-200t (medium) | ? | ? | ? | ? |
| 200-300t (wide) | ? | ? | ? | ? |
| 300t+ (very wide) | ? | ? | ? | ? |

⚠️ On narrow zones (80t), entering 20% deeper = 16t. 
That might miss most trades. On wide zones (300t), 
entering 20% deeper = 60t — significant improvement with 
potentially acceptable miss rate.

C) LIMIT ORDER ENTRY VS MARKET ORDER

⚠️ The current model uses market entry (next bar open 
after touch). A deeper entry implies a LIMIT ORDER placed 
inside the zone, which may or may not fill.

Report for the optimal depth:
| Metric | Value |
|--------|-------|
| Limit order fill rate | ? |
| Mean time to fill (bars) | ? |
| Max time to fill (bars) | ? |
| Partial fills (price touches limit but reverses) | ? |

⚠️ If mean time to fill is > 5 bars, the entry delay 
may consume the edge. Compare PF with time-to-fill delay 
vs PF assuming immediate fill.

================================================================
PART 3: COMBINED — DEEPER ENTRY + ADDS
================================================================

If both Part 1 and Part 2 show improvements, test the 
combination:

| Structure | Entry 1 | Entry 2 | Entry 3 | PF | Trades |
|-----------|---------|---------|---------|-----|--------|
| Current | Edge, 1 lot | — | — | ? | ? |
| Deeper only | Edge+Xt, 1 lot | — | — | ? | ? |
| Adds only | Edge, 1 lot | Midpoint, 1 lot | Opp edge, 1 lot | ? | ? |
| Deeper + adds | Edge+Xt, 1 lot | Midpoint, 1 lot | Opp edge, 1 lot | ? | ? |

⚠️ Report total capital at risk for each structure. 
1 contract at edge = known risk. 3 contracts with the 
deepest at the opposite edge = 3× capital at risk. The 
PF improvement must justify the capital increase.

For structures with multiple contracts, also test SCALED 
EXITS — take 1 contract off at T1, 1 at T2, hold 1 for 
T3. Compare full-exit-at-one-level vs scaled exits:

| Exit style | PF | Max DD | Profit/DD |
|-----------|-----|--------|-----------|
| All contracts at single target | ? | ? | ? |
| Scaled: 1 at 0.5×ZW, 1 at 1.0×ZW, 1 runner | ? | ? | ? |

================================================================
PART 4: STANDALONE STOP REDUCTION (NO ENTRY CHANGE)
================================================================

⚠️ These approaches reduce the stop WITHOUT changing entry 
depth or adding contracts. They modify the stop rule itself. 
Test each independently on the current edge-entry, single-
contract baseline.

A) REDUCED STOP MULTIPLIER

⚠️ Prompt 2 stop investigation found opposite zone edge 
(1.0×ZW) only cost 5 extra stop-outs vs 1.5×ZW. Retest 
on each validated mode's qualifying trades:

| Stop rule | PF @3t | Trades | Stops | WR | Max DD | Trades lost vs current |
|----------|--------|--------|-------|-----|--------|-----------------------|
| 1.5×ZW, floor 120t (current) | ? | ? | ? | ? | ? | — |
| 1.2×ZW, floor 120t | ? | ? | ? | ? | ? | ? |
| 1.0×ZW (opposite edge) | ? | ? | ? | ? | ? | ? |
| 1.0×ZW + 20t buffer | ? | ? | ? | ? | ? | ? |
| 0.8×ZW, floor 100t | ? | ? | ? | ? | ? | ? |

For trades stopped out by tighter stop but NOT by current:

| Tighter stop | Extra stops | Eventually win % | Mean PnL if held |
|-------------|-------------|-----------------|-----------------|
| 1.2×ZW | ? | ? | ? |
| 1.0×ZW | ? | ? | ? |
| 0.8×ZW | ? | ? | ? |

⚠️ If "eventually win %" is below 30%, those trades were 
going to lose anyway — the tighter stop just lost less. If 
above 60%, the tighter stop is cutting real winners.

📌 REMINDER: For A-Eq ModeA (FIXED Stop=190t), test fixed 
stop reductions instead: 160t, 140t, 120t, 100t.

B) SCORE-CONDITIONAL STOPS

⚠️ Higher scores = higher conviction. High-conviction 
touches may tolerate tighter stops (if the thesis is right, 
it should work quickly).

Split qualifying trades by score percentile and test:

| Score percentile | Current stop PF | Tighter stop PF | Stop used | n |
|-----------------|----------------|-----------------|-----------|---|
| Top 25% of qualifying | ? | ? | 1.0×ZW | ? |
| Middle 50% | ? | ? | 1.2×ZW | ? |
| Bottom 25% of qualifying | ? | ? | 1.5×ZW (current) | ? |

⚠️ If top-scoring touches perform equally with tighter 
stops, the stop can be score-conditional: best setups get 
tight stops, borderline setups keep wide stops.

C) ATR-CONDITIONAL STOPS

⚠️ Low ATR = smaller expected price excursion. The same 
zone width represents a LARGER move relative to current 
volatility.

| ATR regime | Current stop PF | Tighter stop PF | Stop used | n |
|-----------|----------------|-----------------|-----------|---|
| Low ATR (< P33) | ? | ? | 1.0×ZW | ? |
| Mid ATR (P33-P67) | ? | ? | 1.2×ZW | ? |
| High ATR (> P67) | ? | ? | 1.5×ZW | ? |

⚠️ B-ZScore Seg4 already segments by ATR. This tests 
whether the stop should ALSO adapt, not just the trade 
selection.

D) ZONE-WIDTH-CONDITIONAL MULTIPLIER

⚠️ The 1.5× multiplier treats all zones equally but the 
structural meaning differs by width:

- Narrow zone (80t): 1.5× = 120t stop. Price crosses 
  the zone and goes 40t beyond. Could be noise.
- Wide zone (300t): 1.5× = 450t stop. Price crosses 
  the zone and goes 150t beyond. That's a real failure.

Test whether narrow and wide zones need different multipliers:

| Zone width | Best multiplier | PF at best | PF at 1.5× | n |
|-----------|----------------|-----------|-----------|---|
| < 100t | ? | ? | ? | ? |
| 100-200t | ? | ? | ? | ? |
| 200-300t | ? | ? | ? | ? |
| 300t+ | ? | ? | ? | ? |

⚠️ Test multipliers: 0.8×, 1.0×, 1.2×, 1.5× for each bin.

E) PARENT ZONE BACKSTOP

⚠️ 95.6% of touches have 3+ zone nesting depth. The 
touched zone has parent zones from higher TFs overlapping. 
If the parent zone's opposite edge is closer than the 
current stop, it's a stronger structural anchor.

| Metric | Value |
|--------|-------|
| Qualifying touches with parent zone | ? (%) |
| Mean parent opp edge distance (ticks) | ? |
| Mean current stop distance (ticks) | ? |
| Cases where parent edge is CLOSER | ? (%) |

For cases where parent edge is closer:

| Stop reference | PF | Trades | Stops | Max DD |
|---------------|-----|--------|-------|--------|
| Current stop | ? | ? | ? | ? |
| Parent opp edge | ? | ? | ? | ? |
| Parent opp edge + 20t buffer | ? | ? | ? | ? |

F) TIME-BASED TIGHTENING (conditional on dwell)

⚠️ The ray analysis confirmed dwell time is a real-time 
decay signal (68.6% → 56.0% over 20 bars). If the trade 
isn't working after N bars, the bounce probability has 
already degraded.

⚠️ Prompt 2 found time-based tightening HURT A-Eq ModeA 
(-2.90 PF impact). Only test on ZONEREL modes where the 
wider stop has more room to tighten.

| Bars without 0.25×target progress | Tighten to | PF | Extra stops | Trades that would have won |
|-----------------------------------|-----------|-----|------------|--------------------------|
| 20 bars | 1.2×ZW | ? | ? | ? |
| 30 bars | 1.0×ZW | ? | ? | ? |
| 40 bars | 0.8×ZW | ? | ? | ? |
| 20 bars | Move to breakeven | ? | ? | ? |

G) DEEPER ENTRY × REDUCED MULTIPLIER (interaction test)

⚠️ The most powerful stop reduction combines Parts 2 and 
4A. Deeper entry moves entry inside the zone. Reduced 
multiplier brings the stop level closer. Both reduce 
stop distance from entry simultaneously.

For the best deeper entry depth from Part 2:

| Configuration | Entry | Stop rule | Effective stop from entry | PF | Trades |
|-------------|-------|----------|--------------------------|-----|--------|
| Current | Edge | 1.5×ZW | ? | ? | ? |
| Deeper only | Edge+Xt | 1.5×ZW | ? | ? | ? |
| Reduced mult only | Edge | 1.0×ZW | ? | ? | ? |
| Both | Edge+Xt | 1.0×ZW | ? | ? | ? |

⚠️ "Both" is the maximum stop reduction available from 
zone structure. If this combination passes P2 validation, 
it represents the tightest structurally-anchored stop.

================================================================
VALIDATION
================================================================

⚠️ Calibrate all parameters (entry depth, add levels, 
confirmation rules, stop multipliers, conditional rules) 
on P1. Validate on P2. Same holdout discipline as the 
main pipeline. If any modification improves P1 but degrades 
P2, it's overfit. Drop it.

================================================================
PART 5: STATISTICAL CONFIDENCE & MISSING STOP APPROACHES
================================================================

⚠️ Every stop modification in Parts 1-4 reports a single 
PF number. With 84-283 trades per mode, small changes could 
be noise. This part adds statistical rigor and tests 
remaining stop approaches.

A) MONTE CARLO CONFIDENCE INTERVALS

For EACH stop modification that shows PF improvement on P1, 
run 10,000 bootstrap resamples:

1. Resample the qualifying trades (with replacement)
2. Compute PF under both current stop and modified stop
3. Report the DIFFERENCE in PF (modified - current)

| Stop modification | Mean PF diff | 95% CI of diff | % of resamples where modified > current |
|------------------|-------------|---------------|---------------------------------------|
| Reduced mult 1.0×ZW | ? | ? | ? |
| Score-conditional | ? | ? | ? |
| ATR-conditional | ? | ? | ? |
| Deeper entry | ? | ? | ? |
| Deeper + reduced combo | ? | ? | ? |

⚠️ If the 95% CI of the PF difference includes zero, the 
modification is NOT statistically significant — it could 
be noise. Only modifications where >95% of resamples show 
improvement should advance to P2 validation.

Also compute Monte Carlo on the CURRENT strategy (no 
modifications) to establish baseline variability:

| Metric | Mean | 95% CI | 5th percentile |
|--------|------|--------|---------------|
| PF @3t | ? | ? | ? |
| Max drawdown (ticks) | ? | ? | ? |
| Max consecutive losses | ? | ? | ? |
| Calmar ratio (annualized) | ? | ? | ? |
| Sharpe ratio | ? | ? | ? |

⚠️ The 5th percentile is the "bad luck" scenario — what 
performance looks like in the worst 5% of outcomes. Use 
this for position sizing and risk management.

B) PARAMETER SENSITIVITY ANALYSIS

For the best stop modification from Part 4, nudge the 
parameter ±10% and ±20%:

| Parameter value | PF @3t | Trades | Max DD |
|----------------|--------|--------|--------|
| Optimal - 20% | ? | ? | ? |
| Optimal - 10% | ? | ? | ? |
| Optimal (best) | ? | ? | ? |
| Optimal + 10% | ? | ? | ? |
| Optimal + 20% | ? | ? | ? |

⚠️ If PF swings wildly with small parameter changes, the 
modification is fragile and likely overfit. If PF is stable 
across ±20%, the modification is robust.

C) SESSION-CONDITIONAL STOPS

⚠️ Baseline: RTH PF=1.50 vs Overnight PF=1.13. ETH has 
lower volatility but also lower edge. Different stop 
rules may be appropriate.

| Session | Current stop PF | Tighter stop PF | Stop used | n |
|---------|----------------|-----------------|-----------|---|
| RTH | ? | ? | 1.2×ZW | ? |
| ETH | ? | ? | 1.0×ZW | ? |
| PreRTH | ? | ? | 1.0×ZW | ? |

⚠️ If ETH tolerates tighter stops without WR degradation, 
session-conditional stops save risk during the lower-edge 
period.

D) SEQ-CONDITIONAL STOPS

⚠️ Baseline: seq 1 PF=1.97, seq 2=1.31, seq 3=1.48, 
seq 5+=0.97. First touches are structurally stronger. 
They may tolerate tighter stops.

| Seq | Current stop PF | Tighter stop PF | Stop used | n |
|-----|----------------|-----------------|-----------|---|
| 1 | ? | ? | 1.0×ZW | ? |
| 2 | ? | ? | 1.2×ZW | ? |
| 3 | ? | ? | 1.5×ZW (current) | ? |

E) TRAILING STOP AS STOP REDUCTION

⚠️ A trailing stop doesn't reduce the initial stop but 
reduces the REALIZED stop once the trade moves favorably. 
After price moves X ticks in your favor, the stop moves 
to limit maximum giveback.

| Trail structure | PF | Avg realized stop (ticks) | Max DD | n |
|----------------|-----|--------------------------|--------|---|
| No trail (current) | ? | ? | ? | ? |
| Trail after 40t MFE, 50% giveback | ? | ? | ? | ? |
| Trail after 60t MFE, 50% giveback | ? | ? | ? | ? |
| Trail after 40t MFE, trail to breakeven | ? | ? | ? | ? |
| Breakeven at 30t MFE (no trail, just BE) | ? | ? | ? | ? |

⚠️ "Avg realized stop" = the actual stop distance at the 
time of exit (whether stop hit or target hit). Trailing 
reduces this on winning trades. Compare to the current 
average.

📌 REMINDER: Trailing stops were in the Prompt 2 exit 
grid but may not have been selected as optimal. This tests 
them specifically as stop reduction mechanisms, not exit 
optimizations.

F) POSITION SIZING IMPLICATION

⚠️ Tighter stops enable larger position sizes for the 
same dollar risk. Quantify this for the best stop 
reduction approach:

| Metric | Current stop | Reduced stop |
|--------|-------------|-------------|
| Mean stop distance (ticks) | ? | ? |
| Dollar risk at 1 contract ($5/tick × stop) | ? | ? |
| Contracts for same dollar risk | ? | ? |
| PnL at scaled position (PF × contracts) | ? | ? |
| Max DD at scaled position (dollars) | ? | ? |

⚠️ If stop reduction from 300t to 150t allows 2 contracts 
for the same risk, and PF holds, total PnL doubles. But 
max DD in TICKS also doubles (2 contracts × drawdown). 
Report DOLLAR risk, not tick risk, for the scaled position.

================================================================
FINAL STOP REDUCTION SUMMARY
================================================================

⚠️ Report across ALL approaches (Parts 1-5):

| Approach | Current stop (mean ticks) | New stop (mean ticks) | Reduction | PF impact | Monte Carlo significant? | P2 verdict |
|----------|-------------------------|---------------------|-----------|-----------|------------------------|-----------|
| Deeper entry | ? | ? | ? | ? | ? | ? |
| Reduced multiplier | ? | ? | ? | ? | ? | ? |
| Score-conditional | ? | ? | ? | ? | ? | ? |
| ATR-conditional | ? | ? | ? | ? | ? | ? |
| Width-conditional | ? | ? | ? | ? | ? | ? |
| Parent backstop | ? | ? | ? | ? | ? | ? |
| Time-based tighten | ? | ? | ? | ? | ? | ? |
| Session-conditional | ? | ? | ? | ? | ? | ? |
| Seq-conditional | ? | ? | ? | ? | ? | ? |
| Trailing stop | ? | ? | ? | ? | ? | ? |
| Deeper + reduced (combo) | ? | ? | ? | ? | ? | ? |

⚠️ Only approaches that are BOTH Monte Carlo significant 
on P1 AND pass P2 validation advance to implementation. 
This is a double gate — statistical confidence AND 
out-of-sample confirmation.

Save results to position_scaling_investigation.md
