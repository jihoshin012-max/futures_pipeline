Ray baseline analysis — observational study.

PURPOSE: Understand broken zone ray behavior before screening 
features or building trading logic. This is the equivalent of 
Prompt 0 for zone touches — measure the phenomenon, establish 
base rates, identify which ray attributes matter. No trading, 
no scoring, no parameter fitting.

⚠️ DATA: Use ALL available data (P1 + P2 combined). This is 
observational — no parameters are fit, no thresholds are set. 
Combining periods maximizes statistical power for base rate 
estimation. The P1/P2 split only matters when feature screening 
begins (future Prompt 1a equivalent).

Combine:
- NQ_ZTE_raw_P1.csv + NQ_ZTE_raw_P2.csv (325 + 3,537 = ~3,862 touches)
- NQ_ray_context_P1.csv + NQ_ray_context_P2.csv (~31K + 1.3M = ~1.33M ray-touch pairs)
- NQ_ray_reference_P1.csv + NQ_ray_reference_P2.csv (33 + 365 = ~398 ray creation events)
- P1 + P2 bar data (for price-ray interaction analysis)

⚠️ This is OBSERVATIONAL — no parameters are fit, no thresholds 
are set. Measure and report. The data decides what matters.

================================================================
SECTION 1: RAY POPULATION
================================================================

⚠️ Before analyzing interactions, understand the ray landscape.
How many rays exist, how do they distribute, and how fast do 
they accumulate?

A) Ray creation rate:
| Metric | Value |
|--------|-------|
| Total ray creation events | ? |
| Mean rays created per day | ? |
| Median rays created per day | ? |
| Days with zero ray creation | ? |

B) Ray creation by TF:
| TF | Count | % of total | Mean per day |
|----|-------|-----------|-------------|
| 15m | ? | ? | ? |
| 30m | ? | ? | ? |
| 60m | ? | ? | ? |
| 90m | ? | ? | ? |
| 120m | ? | ? | ? |
| 240m+ | ? | ? | ? |

⚠️ If LTF rays (15m, 30m) dominate the count, they may 
create noise. But don't filter yet — measure first, filter 
after seeing interaction data.

C) Active ray count over time. At each bar across the full 
P1+P2 period, how many rays are currently active (accumulated, 
not purged)?

| Metric | Value |
|--------|-------|
| Mean active rays per bar | ? |
| Median active rays per bar | ? |
| Max active rays per bar | ? |
| Active rays at end of period | ? |

Plot or describe: does the active count grow linearly, or 
does it plateau (old rays absorbed by price action)?

D) Active rays by TF at end of period:
| TF | Active count | % of total active |
|----|-------------|------------------|
| 15m | ? | ? |
| 30m | ? | ? |
| 60m | ? | ? |
| 90m | ? | ? |
| 120m | ? | ? |
| 240m+ | ? | ? |

📌 REMINDER: Observational only. No filtering, no scoring.

================================================================
SECTION 2: PRICE-RAY INTERACTIONS (all bars, not just touches)
================================================================

⚠️ This section uses bar data + ray_reference to analyze what 
happens when price reaches ANY ray, regardless of whether a 
zone touch is occurring. This establishes base rates.

⚠️ INTERACTION DEFINITION: Rays are a single price point with 
zero width — unlike zones which have a top/bottom range. The 
"interaction zone" around a ray must be defined by proximity 
threshold. The right threshold may differ depending on context 
(a ray near a zone edge has natural backing; an isolated ray 
in open space doesn't). Test multiple thresholds and let the 
data show which produces the cleanest bounce/break separation.

Reconstruct the ray timeline: using ray_reference.csv (creation 
events) and bar data, identify every bar where price comes 
within N ticks of any active ray.

⚠️ INTERACTION DEDUP RULE: An interaction is a DISCRETE EVENT, 
not a per-bar count. An interaction STARTS when price first 
enters the proximity zone (within N ticks of the ray) and ENDS 
when it resolves — bounce, break, or false break per the 
close-based definitions from 2B. If price stays within the 
proximity zone for 50 bars, that is ONE interaction with a 
dwell time of 50 bars (measured in 2J). A new interaction 
begins only after price has LEFT the proximity zone and 
RETURNED.

--- STEP 1: Define what an interaction IS (2A) ---
--- STEP 2: Define how to classify outcomes (2B) ---
--- STEP 3: Re-verify threshold with close-based definitions ---
--- STEP 4: Apply those definitions to measure everything else ---

A) Proximity threshold calibration — PRELIMINARY. Run the 
interaction detection at multiple thresholds. For initial 
calibration, use a simple wick-based bounce/break definition 
(reverses 20t+ = bounce, crosses 20t+ = break). The close 
analysis in 2B will refine these categories, and 2A will be 
re-verified afterward.

| Threshold | Total interactions | Bounce % | Break % | Bounce/Break ratio |
|-----------|-------------------|---------|--------|-------------------|
| 5t | ? | ? | ? | ? |
| 10t | ? | ? | ? | ? |
| 20t | ? | ? | ? | ? |
| 30t | ? | ? | ? | ? |
| 40t | ? | ? | ? | ? |

⚠️ At small thresholds (5t), you see fewer interactions but 
they're more "real." At large thresholds (40t), you see more 
but include noise (price near the ray but not reacting to it). 
Pick the threshold with the highest bounce/break ratio — that's 
where the ray's influence is clearest. Use that threshold for 
the rest of Section 2.

B) CLOSE ANALYSIS — defines the interaction outcome categories 
used by ALL subsequent analysis (2C through 2J, Section 3, 
Section 4, etc.).

⚠️ Wick-based definitions (price reverses/crosses by Nt) are 
preliminary. A bar can wick 30t through a ray and close back 
on the original side — that's a rejection, not a break. The 
close position is the market's verdict.

Three close methods to compare — speed vs signal quality:

Method 1: Single 250-vol bar close
- At each interaction, record: bar close vs ray price
- Classify: close on original side (REJECTION) vs close past 
  ray (ACCEPTANCE)

Method 2: Consecutive 250-vol bar closes
- After price touches ray, count consecutive 250-vol bars 
  closing on the same side
- Test N = 2, 3, 4, 5 consecutive closes as confirmation

Method 3: 15m bar close (via TF chart slot)
- At each interaction, find the corresponding 15m bar
- Record: 15m bar close vs ray price
- ⚠️ 15m is the maximum acceptable delay. Do NOT test 
  higher TF closes (30m, 60m) — too slow for execution.

Compare all methods against ground truth:

⚠️ GROUND TRUTH DEFINITION: To evaluate which close method 
is best, we need a method-neutral outcome measure. Use the 
250-vol bar OHLC (the base chart) for ground truth — this 
avoids biasing toward any close method being tested.

Define "actual bounce" as: over the next 200 250-vol bars, 
price (measured by bar closes) spends 80%+ of bars on the 
original side of the ray. Define "actual break" as: over the 
next 200 250-vol bars, price (measured by bar closes) moves 
30t+ past the ray on the new side AND spends 60%+ of bars on 
the new side. Events that fit neither category = "ambiguous" 
— report count but exclude from accuracy scoring.

These outcome windows are for evaluation only — not trading 
rules. The 200-bar / 30t / 80% / 60% values are observational 
cutpoints.

"Correctly ID'd" = the close method's classification matches 
the ground truth outcome. "False signal" = close method says 
bounce but ground truth says break, or vice versa.

| Close method | Bounce correctly ID'd | Break correctly ID'd | False signals | n |
|-------------|---------------------|---------------------|--------------|---|
| Wick only (no close check) | ? | ? | ? | ? |
| Single 250-vol close | ? | ? | ? | ? |
| 2 consecutive 250-vol closes | ? | ? | ? | ? |
| 3 consecutive 250-vol closes | ? | ? | ? | ? |
| 4 consecutive 250-vol closes | ? | ? | ? | ? |
| 5 consecutive 250-vol closes | ? | ? | ? | ? |
| 15m bar close | ? | ? | ? | ? |

⚠️ Also report the "ambiguous" count for each method — 
interactions where the ground truth is neither clear bounce 
nor clear break. A method that classifies ambiguous events 
confidently is overreaching.

Select the best-performing close method. This becomes the 
GOVERNING DEFINITION for the rest of the analysis:

- BOUNCE = interaction where the best close method shows 
  rejection (price stays on original side)
- BREAK = interaction where the best close method shows 
  confirmed acceptance (sustained close past ray)
- FALSE BREAK = acceptance followed by reversal back to 
  original side within 1-2 bars
- POLARITY FLIP (Section 3) = a BREAK, not a false break

📌 REMINDER: These definitions govern ALL subsequent analysis. 
Every table from 2C onward, and all of Sections 3-7, use 
these close-based categories — not the wick-based definitions.

After selecting the best close method, RE-RUN the proximity 
threshold table from 2A using the close-based definitions 
instead of wick-based:

| Threshold | Interactions | Bounce % (close) | Break % (close) | Ratio |
|-----------|-------------|-----------------|----------------|-------|
| 5t | ? | ? | ? | ? |
| 10t | ? | ? | ? | ? |
| 20t | ? | ? | ? | ? |
| 30t | ? | ? | ? | ? |
| 40t | ? | ? | ? | ? |

⚠️ If the optimal threshold shifts under close-based 
definitions (e.g., 10t was best wick-based but 20t is best 
close-based), use the close-based optimal for all subsequent 
analysis. Report both results.

📌 REMINDER: All tables in 2C through 2J and in Sections 3-7 
use the CLOSE-BASED definitions from this step, NOT the 
preliminary wick-based definitions from 2A.

For the best-performing close method, report the interaction 
type distribution:

| Interaction type | Count | % | Next 20-bar MFE |
|-----------------|-------|---|----------------|
| Strong rejection (wick past ray, close far on original side) | ? | ? | ? |
| Weak rejection (wick past ray, close barely on original side) | ? | ? | ? |
| Acceptance (close past ray) | ? | ? | ? |
| Confirmed acceptance (2+ closes past ray) | ? | ? | ? |
| Failed acceptance (close past, next bar closes back) | ? | ? | ? |

⚠️ "Strong rejection" = bar wick crosses ray but close is 
in the top/bottom 25% of bar range on the original side. 
"Weak rejection" = close is within 25% of the ray price. 
These 25% bins are observational — the data may show a 
different natural breakpoint between strong and weak.

--- From here, ALL bounce/break classifications use the ---
--- close-based definitions from 2B.                    ---

C) Zone-backed vs isolated ray interactions. For each 
interaction (at the selected threshold), classify:

| Context | Interactions | Bounce % | Break % | n |
|---------|-------------|---------|--------|---|
| Ray within 30t of an active zone edge (zone-backed) | ? | ? | ? | ? |
| Ray NOT near any active zone (isolated) | ? | ? | ? | ? |

⚠️ The 30t zone-backing distance is an observational cutpoint, 
not a calibrated threshold. If results are interesting, also 
test 15t and 50t to see if the effect is robust to the choice.

⚠️ If zone-backed rays bounce more than isolated rays, the 
ray's effective "width" is amplified by nearby zone structure. 
A ray at 25,050 with a zone edge at 25,045 acts as a wider 
S/R band than a ray at 25,300 in open space.

D) Interaction frequency (at selected threshold):
| Metric | Value |
|--------|-------|
| Total price-ray interactions | ? |
| Mean interactions per day | ? |
| % of all bars with a ray interaction | ? |
| Mean interactions per ray (across its lifetime) | ? |

E) First interaction outcome. For each ray, what happens the 
FIRST time price reaches it after creation? Use close-based 
definitions from 2B.

| Outcome | Count | % |
|---------|-------|---|
| Bounce (close-based rejection) | ? | ? |
| Break (close-based confirmed acceptance) | ? | ? |
| False break (acceptance → reversal) | ? | ? |

Split by ray TF:
| TF | Bounce % | Break % | False break % | n |
|----|---------|--------|--------------|---|
| 15m | ? | ? | ? | ? |
| 30m | ? | ? | ? | ? |
| 60m | ? | ? | ? | ? |
| 90m | ? | ? | ? | ? |
| 120m | ? | ? | ? | ? |
| 240m+ | ? | ? | ? | ? |

⚠️ Flag any TF with fewer than 20 first interactions as 
LOW SAMPLE.

F) First interaction by ray age:
| Ray age at first interaction | Bounce % | Break % | n |
|-----------------------------|---------|--------|---|
| < 50 bars (fresh) | ? | ? | ? |
| 50-200 bars | ? | ? | ? |
| 200-500 bars | ? | ? | ? |
| 500+ bars (stale) | ? | ? | ? |

⚠️ If fresh rays bounce more than stale rays, age is a 
predictive feature. If no difference, age doesn't matter.

G) Interaction side (polarity). When price approaches the ray:
| Approach | Bounce % | Break % | n |
|----------|---------|--------|---|
| From above (ray = support) | ? | ? | ? |
| From below (ray = resistance) | ? | ? | ? |

Does broken demand ray (TopPrice) behave differently from 
broken supply ray (BottomPrice)?

| Ray type | As support (bounce %) | As resistance (bounce %) |
|----------|---------------------|------------------------|
| Demand ray | ? | ? |
| Supply ray | ? | ? |

📌 REMINDER: Using combined P1+P2 data and close-based 
definitions from 2B. These are base rates — the raw 
probability of bounce vs break at ray levels. No zone 
context yet.

H) Approach velocity. How fast price reaches the ray:

| Approach speed | Bounce % | Break % | n |
|---------------|---------|--------|---|
| Fast (> 5 ticks/bar over prior 5 bars) | ? | ? | ? |
| Medium (2-5 ticks/bar) | ? | ? | ? |
| Slow (< 2 ticks/bar) | ? | ? | ? |

⚠️ The 2t/5t velocity bins are observational cutpoints. If 
the effect is strong, also report the distribution (quartiles 
of approach velocity) to see if the relationship is linear or 
has a step change.

⚠️ If fast approach + rejection = stronger S/R signal than 
slow approach + rejection, approach velocity is a feature 
(parallels the zone touch ApproachVelocity finding).

I) Session context:
| Session | Interactions | Bounce % | Break % | n |
|---------|-------------|---------|--------|---|
| RTH (09:30-16:15 ET) | ? | ? | ? | ? |
| ETH (outside RTH) | ? | ? | ? | ? |

⚠️ The zone touch strategy found ETH was structurally weaker. 
If ray bounces during ETH are less reliable, session is a 
filter for ray-based signals.

J) Dwell time before resolution. How many bars does price 
spend near the ray before the close-based outcome resolves?

| Dwell time (bars within threshold of ray) | Bounce % | Break % | n |
|------------------------------------------|---------|--------|---|
| 1-2 bars (decisive) | ? | ? | ? |
| 3-5 bars (contested) | ? | ? | ? |
| 6-10 bars (consolidation) | ? | ? | ? |
| 10+ bars (range-bound at ray) | ? | ? | ? |

⚠️ If decisive (1-2 bar) resolutions have higher bounce % 
than prolonged consolidations, speed of resolution is a 
quality signal.

================================================================
SECTION 3: POLARITY FLIPS
================================================================

⚠️ Rays don't die when broken — they flip polarity. A supply 
ray broken upward becomes support. Track the lifecycle.

⚠️ FLIP DEFINITION: Section 2B established the governing 
close-based definitions. A FLIP = a BREAK (confirmed 
acceptance from 2B). A FALSE BREAK = failed acceptance 
from 2B — this is NOT a flip.

For comparison, also report wick-based flips (price crosses 
ray by 20t+). If close-based produces fewer flips but cleaner 
lifecycle patterns, the close-based definition is correct — 
wick-only flips were counting false breakouts as polarity 
changes.

A) Flip frequency (report for BOTH definitions — close-based 
is the primary, wick-based is the comparison):
| Metric | Value |
|--------|-------|
| Rays with 0 flips (never broken through) | ? |
| Rays with 1 flip | ? |
| Rays with 2 flips | ? |
| Rays with 3+ flips | ? |
| Max flips observed on a single ray | ? |

B) Does flip history predict future behavior?
| Flip count so far | Next interaction bounce % | n |
|------------------|-------------------------|---|
| 0 (never flipped) | ? | ? |
| 1 (flipped once) | ? | ? |
| 2+ (multi-flip) | ? | ? |

⚠️ If multi-flip rays hold better than never-flipped rays, 
"battle-tested" levels are stronger — that's a feature.

C) Bounce streak:
| Consecutive bounces in current polarity | Next bounce % | n |
|----------------------------------------|--------------|---|
| 0 (just flipped or new) | ? | ? |
| 1 confirmed bounce | ? | ? |
| 2 confirmed bounces | ? | ? |
| 3+ confirmed bounces | ? | ? |

⚠️ If bounce % increases with consecutive confirmations, 
S/R strength builds with interaction history — the lifecycle 
model is valid.

D) Retest after flip. When a ray flips polarity (break from 
2B definitions), does price come back to test it from the 
new side? This is the highest-conviction moment in the 
lifecycle — a ray that held as strong support, then broke, 
should act as strong resistance on the retest.

| Metric | Value |
|--------|-------|
| Flips where price retests from new side | ? (%) |
| Mean bars until retest | ? |
| Median bars until retest | ? |
| Retests that never happen (price keeps going) | ? (%) |

Does pre-flip strength predict retest outcome?

| Pre-flip bounces | Retest bounce % (new polarity) | n |
|-----------------|-------------------------------|---|
| 0 (broke on first interaction) | ? | ? |
| 1 bounce before break | ? | ? |
| 2 bounces before break | ? | ? |
| 3+ bounces before break | ? | ? |

⚠️ If rays with more pre-flip bounces produce higher retest 
bounce rates, then pre-flip S/R strength CARRIES OVER to the 
new polarity. This is a tradeable signal — a strong support 
that breaks becomes strong resistance on the retest.

Split retest outcome by ray TF:
| Ray TF | Retests | Retest bounce % | n |
|--------|---------|----------------|---|
| 15m | ? | ? | ? |
| 30m | ? | ? | ? |
| 60m | ? | ? | ? |
| 90m | ? | ? | ? |
| 120m | ? | ? | ? |
| 240m+ | ? | ? | ? |

📌 REMINDER: This is observational — measuring whether the 
retest pattern exists and whether pre-flip history predicts 
it. Not proposing a trading rule.

E) S/R decay within a polarity phase. After a flip, does 
each subsequent bounce from the ray get weaker until the 
ray breaks again?

For rays with 2+ interactions in the same polarity phase 
(between flips), measure whether bounce magnitude decays:

⚠️ BOUNCE MAGNITUDE DEFINITION: The maximum distance (in 
ticks) price travels away from the ray on the original side 
before the interaction ends (price returns to the proximity 
zone or the next interaction begins). This is the MFE from 
the ray price in the bounce direction.

| Interaction # in current polarity | Mean bounce magnitude (ticks) | n |
|----------------------------------|------------------------------|---|
| 1st interaction after flip | ? | ? |
| 2nd interaction | ? | ? |
| 3rd interaction | ? | ? |
| 4th+ interaction | ? | ? |

⚠️ If bounce magnitude decreases with each successive 
interaction, the ray is "wearing out" in its current 
polarity — each test absorbs S/R strength until it fails. 
This would mean the number of interactions in the current 
polarity is a DECAY signal: more touches = weaker ray = 
higher probability of the next flip.

Also measure: does dwell time (from 2J) increase as the 
ray weakens? If early interactions resolve in 1-2 bars 
but later ones take 5-10 bars, increasing dwell time is 
an early warning of the next flip.

================================================================
SECTION 4: RAYS AND ZONE TOUCHES
================================================================

⚠️ Now connect rays to zone touch events. Use ray_context.csv 
which has ray data specifically at touch time.

⚠️ METRIC DISTINCTION: Section 2 measured ray interaction 
outcomes (bounce/break — close-based from 2B). Section 4 
measures zone touch quality (R/P = Reaction / Penetration — 
how far price bounces vs how far it penetrates after touching 
a zone). These are DIFFERENT metrics applied to overlapping 
events. A zone touch can have a high R/P (strong bounce from 
zone) while a nearby ray gets broken through. Both are 
measured — they answer different questions.

A) Ray density at zone touches:
| Metric | Value |
|--------|-------|
| Mean rays per touch (within proximity filter) | ? |
| Median rays per touch | ? |
| Touches with 0 nearby rays | ? (%) |
| Touches with 5+ nearby rays | ? (%) |

B) Ray position relative to zone:
| Position | Count | % | Mean distance (ticks) |
|----------|-------|---|----------------------|
| Ray INSIDE active zone | ? | ? | ? |
| Ray ABOVE zone (for demand touch) | ? | ? | ? |
| Ray BELOW zone (for supply touch) | ? | ? | ? |
| Ray between entry and T1 target | ? | ? | ? |
| Ray between T1 and T2 target | ? | ? | ? |
| Ray on adverse side (beyond stop) | ? | ? | ? |

⚠️ Use ZONEREL targets for the entry/T1/T2/stop calculations 
(T1=0.5xZW, T2=1.0xZW, Stop=max(1.5xZW, 120t)).

C) Do rays predict zone touch outcome?

Split zone touches by ray context and compare R/P ratios:

| Ray context | Touches | WR | Mean Rxn | Mean Pen | R/P |
|------------|---------|----|---------|---------|----|
| No rays nearby | ? | ? | ? | ? | ? |
| Ray inside zone (confirmation) | ? | ? | ? | ? | ? |
| Fresh HTF ray inside zone | ? | ? | ? | ? | ? |
| Ray between entry and T1 (obstacle) | ? | ? | ? | ? | ? |
| Multiple rays clustered near zone | ? | ? | ? | ? | ? |

⚠️ Define "fresh" = ray age < 200 bars. "HTF" = 60m+. These 
are observational cutpoints, not thresholds to calibrate.

📌 REMINDER: Observational — measure R/P at these splits, do 
not fit thresholds. The data shows whether ray context 
predicts touch quality.

D) Ray TF vs zone TF interaction:
| Ray TF | Zone TF | Touches | R/P | Signal? |
|--------|---------|---------|-----|---------|
| Same TF | — | ? | ? | ? |
| Higher TF ray, lower TF zone | — | ? | ? | ? |
| Lower TF ray, higher TF zone | — | ? | ? | ? |

⚠️ If HTF rays near LTF zones improve R/P, that's cross-TF 
confluence from the ray side — complementary to the existing 
TF confluence feature.

E) Nested zone context. At any touch, multiple TF zones may 
overlap at the same price. A ray inside a nested zone structure 
means something different than a ray in open space.

For each zone touch, count how many OTHER TF zones overlap 
at the touch price (zone top/bot from ZTE_raw for all TFs):

| Nesting depth | Touches | % | Mean rays nearby |
|--------------|---------|---|-----------------|
| 1 (touched zone only) | ? | ? | ? |
| 2 (one parent zone) | ? | ? | ? |
| 3+ (deep nesting) | ? | ? | ? |

For rays at nested touches, classify where the ray sits:
| Ray position | Count | R/P |
|-------------|-------|-----|
| Ray inside touched zone only | ? | ? |
| Ray inside parent zone (but outside touched zone) | ? | ? |
| Ray at parent zone edge | ? | ? |
| Ray between nested zones | ? | ? |
| Ray outside all zones | ? | ? |

⚠️ Triple confluence (active zone edge + nested parent zone + 
ray) may be the strongest signal. Measure R/P for touches 
where all three align vs touches with zone only.

================================================================
SECTION 5: RAY CLUSTERING
================================================================

⚠️ Multiple rays near the same price level create confluence 
zones. Are these stronger than isolated rays?

A) Identify ray clusters: groups of 2+ rays within 30 ticks 
of each other. (30t is an observational cutpoint — if results 
are interesting, also test 20t and 50t to check sensitivity.)

⚠️ Evaluate cluster membership at the TIME of each interaction, 
not at a fixed snapshot. A ray that was isolated when created 
may be in a cluster by the time price reaches it (if new zones 
broke nearby). Use the set of active rays at the interaction 
bar to determine cluster membership.

| Metric | Value |
|--------|-------|
| Total clusters found | ? |
| Mean rays per cluster | ? |
| Mean cluster width (ticks) | ? |
| % of all rays that are in a cluster | ? |

B) Cluster vs isolated ray interaction outcome:
| Type | First bounce % | First break % | n |
|------|---------------|--------------|---|
| Isolated ray (no other ray within 30t) | ? | ? | ? |
| Cluster (2+ rays within 30t) | ? | ? | ? |
| Dense cluster (3+ rays within 30t) | ? | ? | ? |

⚠️ If clusters bounce more than isolated rays, ray density 
near a price level is a feature.

C) Cluster TF composition:
| Cluster type | Bounce % | n |
|-------------|---------|---|
| All same TF | ? | ? |
| Mixed TF (e.g., 30m + 60m) | ? | ? |
| HTF-anchored (at least one 60m+) | ? | ? |

================================================================
SECTION 6: RAY AS TARGET / STOP REFERENCE
================================================================

⚠️ Can rays serve as natural exit levels? This section uses 
qualifying zone touches (scored above A-Cal threshold under 
ZONEREL config) and simulates where exits would occur. These 
are NOT executed trades — this is observational analysis of 
where rays sit relative to simulated trade geometry.

A) For all qualifying zone touches (scored above threshold 
under ZONEREL config), how often does a ray sit between entry 
and T1?

⚠️ STALL DEFINITION: Price "stalls at a ray" when it reaches 
within the proximity threshold (from 2A) of the ray AND 
spends 3+ bars within that threshold before resolving. 
Resolution = either continues past the ray toward T1 or 
reverses back toward entry. Use the close-based definitions 
from 2B to determine direction of resolution.

| Metric | Value |
|--------|-------|
| Qualifying touches with ray between entry and T1 | ? (%) |
| Mean ray distance from entry (as % of T1 distance) | ? |
| Touches where price stalls at the ray before reaching T1 | ? (%) |

B) For qualifying touches where price stalls at a ray before T1:
| Outcome | Count | % |
|---------|-------|---|
| Eventually reaches T1 after stalling | ? | ? |
| Reverses from ray, never reaches T1 | ? | ? |
| Reverses from ray, price reaches stop level | ? | ? |

⚠️ If a significant % of touches stall at rays and then 
reverse, the ray is a natural earlier exit — capturing 
profit before the reversal.

C) For stop placement: how often does a ray sit on the 
adverse side within the simulated stop distance?

| Metric | Value |
|--------|-------|
| Qualifying touches with adverse-side ray within stop | ? (%) |
| Mean ray distance from entry on adverse side | ? |
| When price breaks through adverse ray, does it reach stop level? | ? (%) |

📌 REMINDER: These are observational measurements. Do not 
propose exit rule changes. The data informs whether rays 
have value as exit references.

D) Ray-to-ray movement. When price breaks through one ray, 
does it tend to reach the next ray? This determines whether 
rays form a natural target ladder.

For each ray break-through, find the next ray in the 
direction of the break:

| Metric | Value |
|--------|-------|
| Break-throughs with another ray ahead | ? (%) |
| Mean distance to next ray (ticks) | ? |
| % that reach the next ray | ? |
| Mean bars to reach next ray | ? |

Split by whether the broken ray was isolated vs in a cluster:
| Context | Reaches next ray % | n |
|---------|-------------------|---|
| Broke isolated ray → next ray | ? | ? |
| Broke through cluster → next ray | ? | ? |

⚠️ If price consistently runs from ray to ray after breaking, 
the ray ladder is a valid target framework. If movement is 
random after a break, rays only have value as S/R, not as 
targets.

================================================================
SECTION 7: LTF VS HTF RAYS
================================================================

⚠️ The hypothesis is that HTF rays (60m+) matter more. 
Let the data confirm or reject.

A) Consolidate all interaction data by TF:
| TF | Total interactions | Bounce % | Break % | Mean persistence (bars) | Flip rate |
|----|--------------------|---------|--------|----------------------|-----------|
| 15m | ? | ? | ? | ? | ? |
| 30m | ? | ? | ? | ? | ? |
| 60m | ? | ? | ? | ? | ? |
| 90m | ? | ? | ? | ? | ? |
| 120m | ? | ? | ? | ? | ? |
| 240m+ | ? | ? | ? | ? | ? |

B) At zone touches specifically:
| TF | Touches with ray present | R/P with ray | R/P without ray | Delta |
|----|-------------------------|-------------|----------------|-------|
| 15m ray | ? | ? | ? | ? |
| 30m ray | ? | ? | ? | ? |
| 60m ray | ? | ? | ? | ? |
| 90m ray | ? | ? | ? | ? |
| 120m ray | ? | ? | ? | ? |
| 240m+ ray | ? | ? | ? | ? |

⚠️ If LTF rays show no R/P difference (delta ≈ 0), they are 
noise and can be filtered in future analysis. If HTF rays 
show strong positive delta, they are candidate features.

================================================================
SECTION 8: SUMMARY AND DISCOVERY MAP
================================================================

⚠️ Synthesize all findings into a discovery map for future 
feature screening.

A) For each ray attribute, classify signal strength:

| Attribute | Signal? | Evidence | Section |
|-----------|---------|----------|---------|
| Ray TF | ? | ? | 2E, 7 |
| Ray age / freshness | ? | ? | 2F |
| Ray polarity (support vs resistance) | ? | ? | 2G |
| Close type (rejection/acceptance/confirmed/failed) | ? | ? | 2B |
| Best close method (250-vol / N-consecutive / 15m) | ? | ? | 2B |
| Approach velocity | ? | ? | 2H |
| Session context (RTH vs ETH) | ? | ? | 2I |
| Dwell time before resolution | ? | ? | 2J |
| Flip count | ? | ? | 3B |
| Flip definition (wick-based vs close-based) | ? | ? | 3A |
| Bounce streak (S/R strength) | ? | ? | 3C |
| Retest after flip (pre-flip strength carryover) | ? | ? | 3D |
| S/R decay (bounce magnitude decreasing per touch) | ? | ? | 3E |
| Ray inside vs outside zone | ? | ? | 4B |
| Ray between entry and target | ? | ? | 6A |
| Ray-to-ray movement (target ladder) | ? | ? | 6D |
| Ray clustering | ? | ? | 5B |
| Cluster TF composition | ? | ? | 5C |
| Cross-TF confluence (ray TF vs zone TF) | ? | ? | 4D |
| Optimal proximity threshold | ? | ? | 2A |
| Zone-backed vs isolated ray | ? | ? | 2C |
| Nested zone context (nesting depth) | ? | ? | 4E |
| Triple confluence (zone + parent + ray) | ? | ? | 4E |

Classify each:
- STRONG: clear separation in interaction outcome or R/P
- MODERATE: some separation but small sample or inconsistent
- WEAK: no meaningful separation
- INSUFFICIENT DATA: too few observations to assess

B) Based on the discovery map, which attributes should 
advance to feature screening (Prompt 1a equivalent)?

List in priority order. Only STRONG and MODERATE advance.

C) Are there any findings that suggest rays should be 
filtered before feature screening? (e.g., "drop all 15m 
rays" or "only consider rays < 500 bars old")

D) Does the polarity flip lifecycle model hold? Is S/R 
strength (bounce streak) a real phenomenon or noise?

Save results to ray_baseline_analysis.md
