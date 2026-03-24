Ray baseline follow-up — HTF filter, freshness, and regime checks.

PURPOSE: The baseline analysis (ray_baseline_analysis.md) 
identified 6 STRONG and 4 MODERATE ray attributes, but several 
findings are confounded or undertested. This follow-up resolves 
the open questions before feature screening begins.

⚠️ Use the same combined P1+P2 data as the baseline. Same 
data files:
- NQ_ZTE_raw_P1.csv + NQ_ZTE_raw_P2.csv (~3,862 touches)
- NQ_ray_context_P1.csv + NQ_ray_context_P2.csv (~1.33M pairs)
- NQ_ray_reference_P1.csv + NQ_ray_reference_P2.csv (~398 events)
- P1 + P2 bar data

⚠️ Use the same definitions from the baseline: 40t proximity 
threshold, 15m bar close, close-based bounce/break. Exception: 
Check 8 explicitly tests a tighter threshold.

================================================================
CHECK 1: RAY DENSITY WITH HTF FILTER
================================================================

⚠️ The baseline's ray density problem: 19.7 rays within 30t 
at every touch made it impossible to isolate individual ray 
effects. Filter to 60m+ rays ONLY (60m, 90m, 120m, 240m+). 
Discard all 15m and 30m rays.

| Metric | All rays (baseline) | 60m+ only |
|--------|-------------------|-----------|
| Active rays at end of period | 313 | ? |
| Mean rays per touch (within 30t) | 19.7 | ? |
| Touches with 0 nearby rays | 12 (0.3%) | ? |
| Touches with 0 nearby 60m+ rays | — | ? |

⚠️ KEY QUESTION: Does filtering to 60m+ create a meaningful 
"no nearby ray" group? If touches with 0 HTF rays nearby 
rises from 0.3% to 10%+, we can properly test ray-present 
vs ray-absent. If it stays under 5%, the density problem 
persists even at HTF.

Report the distribution:
| HTF rays within 30t | Touches | % |
|--------------------|---------|---|
| 0 | ? | ? |
| 1-2 | ? | ? |
| 3-5 | ? | ? |
| 6+ | ? | ? |

⚠️ DECISION GATE: If the 0 HTF ray group is under 5% of 
touches, the density problem persists even at HTF. In that 
case, SKIP binary presence/absence comparisons in Checks 2, 
3, and 9. Instead use CONTINUOUS features for those checks:
- Nearest HTF ray distance (ticks) instead of "ray present 
  vs absent"
- Nearest HTF ray bounce streak instead of "ray vs no ray"
Report this substitution if triggered.

Additionally, if mean HTF rays within 30t is still above 5 
after filtering, apply a PER-TF selection: for each touch, 
from each TF (60m, 90m, 120m, 240m+), select the nearest 
ray by distance AND the newest ray by age (may be the same 
ray). Only consider rays in/near the zone (within zone width 
+ 30t buffer from zone edges). This gives at most 8 rays per 
touch (2 per TF × 4 TFs) — a manageable set focused on the 
rays most likely to interact with the trade.

Then measure cross-TF confluence: when rays from 2+ different 
TFs are within 20t of each other near the zone, that's multi-
TF convergence at a single price level.

| Cross-TF confluence at zone | Touches | R/P | n |
|----------------------------|---------|-----|----|
| 0 TFs with ray near zone | ? | ? | ? |
| 1 TF with ray near zone | ? | ? | ? |
| 2 TFs converging within 20t | ? | ? | ? |
| 3+ TFs converging within 20t | ? | ? | ? |

⚠️ If R/P increases with the number of converging TFs, 
multi-TF ray confluence near a zone is a strong feature — 
stronger than any single-TF ray attribute.

Report the per-TF density alongside the uncapped for 
comparison.

================================================================
CHECK 2: FRESH RAY + FRESH ZONE COMBINATION
================================================================

⚠️ The baseline couldn't test freshness properly (n=26 for 
fresh rays). This check tests the INTERACTION between ray 
freshness and zone freshness — a structural reset where 
both levels are newly formed.

Define (using 60m+ rays only):
- Fresh ray: ray age < 100 bars at touch time
- Fresh zone: ZoneAgeBars < 100 at touch time
- Stale ray: ray age > 500 bars
- Stale zone: ZoneAgeBars > 500

⚠️ The 100-bar and 500-bar cutpoints are observational. If 
sample sizes are too small in any cell, widen the fresh 
window to 200 bars and report the adjusted cutpoint.

| Combination | Touches | R/P | WR | n |
|------------|---------|-----|----|----|
| Fresh zone + fresh HTF ray | ? | ? | ? | ? |
| Fresh zone + stale HTF ray | ? | ? | ? | ? |
| Fresh zone + no HTF ray nearby | ? | ? | ? | ? |
| Stale zone + fresh HTF ray | ? | ? | ? | ? |
| Stale zone + stale HTF ray | ? | ? | ? | ? |
| Stale zone + no HTF ray nearby | ? | ? | ? | ? |

⚠️ If fresh zone + fresh HTF ray shows significantly higher 
R/P than other combinations, the INTERACTION between freshness 
of both levels is the signal — not either one alone.

Also report bounce streak of the fresh vs stale rays to 
control for the confound from the baseline (fresh rays have 
zero bounces by definition):

| Ray freshness | Mean bounce streak | Bounce % | n |
|--------------|-------------------|---------|---|
| Fresh HTF ray (< 100 bars) | ? | ? | ? |
| Stale HTF ray (> 500 bars) | ? | ? | ? |

📌 REMINDER: 60m+ rays only for all of Check 2. This is 
the HTF-filtered analysis.

================================================================
CHECK 3: HTF RAY EFFECT ON ZONE TOUCH R/P (CLEANED)
================================================================

Repeat Section 4C from the baseline but with 60m+ rays only:

| Ray context (60m+ only) | Touches | R/P | n |
|------------------------|---------|-----|----|
| No HTF ray within 30t | ? | ? | ? |
| HTF ray inside zone | ? | ? | ? |
| Fresh HTF ray inside zone | ? | ? | ? |
| HTF ray between entry and T1 | ? | ? | ? |

⚠️ Compare the "No HTF ray" R/P here to the baseline's 
no-ray R/P (5.09, n=79). Three possible outcomes:

1. No-HTF-ray R/P is still high with larger n → the 
   congestion effect is real (rays = negative for touches)
2. No-HTF-ray R/P normalizes to ~1.5-1.7 → the baseline's 
   5.09 was a confound (breakout regime, not ray absence)
3. Fresh HTF ray inside zone shows HIGHER R/P than stale → 
   freshness matters and the blanket "rays are negative" 
   conclusion was wrong

⚠️ Also split by zone width to control for composition:
| Zone width | No HTF ray R/P | With HTF ray R/P | n (no) | n (with) |
|-----------|---------------|-----------------|--------|----------|
| < 150t (narrow) | ? | ? | ? | ? |
| 150-250t | ? | ? | ? | ? |
| 250t+ (wide) | ? | ? | ? | ? |

📌 REMINDER: Use ZONEREL targets for entry/T1/T2/stop 
calculations (T1=0.5xZW, T2=1.0xZW, Stop=max(1.5xZW, 120t)).

================================================================
CHECK 4: BOUNCE STREAK DECONFOUNDED FROM AGE
================================================================

⚠️ The baseline showed fresh rays bounce at 34.6% and stale 
at 78.3% — but fresh rays have zero confirmed bounces (they 
just formed). Is "freshness" a real attribute or just another 
way of saying "no bounce streak yet"?

2×2 table controlling for bounce streak (60m+ rays only):

| Age | Bounce streak | Bounce % | n |
|-----|--------------|---------|---|
| Fresh (< 100 bars) | 0 bounces | ? | ? |
| Fresh (< 100 bars) | 1+ bounces | ? | ? |
| Stale (> 500 bars) | 0 bounces | ? | ? |
| Stale (> 500 bars) | 1+ bounces | ? | ? |

⚠️ INTERPRETATION:
- If fresh + 1 bounce ≈ stale + 1 bounce → age is fully 
  explained by streak. Drop age, keep streak only.
- If fresh + 1 bounce > stale + 1 bounce → freshness adds 
  signal beyond streak. Both are features.
- If fresh + 0 bounce > stale + 0 bounce → fresh rays hold 
  better even without confirmation. Freshness is independent.

================================================================
CHECK 5: LIFECYCLE AT HTF ONLY
================================================================

Re-run Section 3A (flip frequency) and 3C (bounce streak) 
on 60m+ rays only:

⚠️ The baseline showed flat TF effect (2.5pp) but that was 
measured in a dense multi-TF ray environment. At HTF-only, 
the bounce streak signal might be stronger or weaker.

| Bounce streak (60m+ only) | Next bounce % | n |
|--------------------------|--------------|---|
| 0 (just flipped) | ? | ? |
| 1 confirmed | ? | ? |
| 2 confirmed | ? | ? |
| 3+ confirmed | ? | ? |

| Metric | Baseline (all TFs) | 60m+ only |
|--------|-------------------|-----------|
| 0→1 jump magnitude | 29.0pp | ? |
| 3+ bounce rate | 79.2% | ? |
| 0 bounce rate | 48.5% | ? |

⚠️ If the 0→1 jump is LARGER for 60m+ rays, bounce streak 
is a stronger signal at HTF — your experience that HTF rays 
matter more is confirmed through the lifecycle lens even 
though the aggregate TF comparison was flat.

Also report flip frequency at HTF only:
| Metric (60m+ rays) | Value |
|--------------------|-------|
| Rays with 0 flips | ? |
| Rays with 1 flip | ? |
| Rays with 2 flips | ? |
| Rays with 3+ flips | ? |
| Max flips | ? |

📌 REMINDER: Use the same 40t threshold and close-based 
definitions from the baseline for Checks 1-5. Check 8 
tests a different threshold.

================================================================
CHECK 6: REGIME STABILITY (P1 vs P2 INDEPENDENT)
================================================================

⚠️ CRITICAL CHECK. The active ray count jumps from 19 (P1) 
to 313 (P2). The baseline combined them, but key findings 
might only hold in one regime.

Split every key finding by period independently:

| Finding | P1 value | P1 n | P2 value | P2 n | Stable? |
|---------|---------|------|---------|------|---------|
| Bounce streak 0→1 jump (pp) | ? | ? | ? | ? | ? |
| Bounce streak 3+ bounce % | ? | ? | ? | ? | ? |
| Dwell time 1-2 bar bounce % | ? | ? | ? | ? | ? |
| Dwell time 10+ bar bounce % | ? | ? | ? | ? | ? |
| ETH vs RTH spread (pp) | ? | ? | ? | ? | ? |
| Flip count 0-flip bounce % | ? | ? | ? | ? | ? |
| Overall bounce % at 40t | ? | ? | ? | ? | ? |

⚠️ P1 has much smaller sample sizes (325 touches, 33 ray 
events, ~19 active rays). Flag any metric with n < 50 as 
LOW CONFIDENCE.

Classification:
- STABLE: both periods show same direction and >50% of the 
  combined magnitude
- UNSTABLE: one period shows effect, other doesn't
- REVERSED: periods show opposite directions
- LOW CONFIDENCE: P1 n < 50, cannot assess

⚠️ If any STRONG finding from the baseline is UNSTABLE or 
REVERSED, it should NOT advance to feature screening without 
further investigation. Flag it.

================================================================
CHECK 7: DWELL TIME SURVIVAL CURVE
================================================================

⚠️ Dwell time was the second-strongest signal (21.9pp) but 
it's measured RETROSPECTIVELY — you know the total dwell 
only after the interaction resolves. At trade entry time, you 
don't know if the interaction will last 2 bars or 20.

For dwell time to be a REAL-TIME signal, we need a survival 
curve: at each bar N of dwell, what's the probability of 
eventually bouncing given price is STILL within the proximity 
zone?

| Bars dwelling so far | Still unresolved | Eventually bounce % | n |
|---------------------|-----------------|--------------------|----|
| 1 | ? | ? | ? |
| 2 | ? | ? | ? |
| 3 | ? | ? | ? |
| 5 | ? | ? | ? |
| 8 | ? | ? | ? |
| 10 | ? | ? | ? |
| 15 | ? | ? | ? |
| 20 | ? | ? | ? |

⚠️ INTERPRETATION:
- If "eventually bounce %" drops steadily with each bar → 
  dwell time is a real-time decay signal. After N bars near 
  the ray without resolution, the bounce probability has 
  already degraded. Usable as a live exit trigger.
- If it stays flat then drops suddenly at bar N → there's a 
  critical threshold. Before bar N, the interaction is still 
  viable. After bar N, abandon hope. The threshold is the 
  tradeable insight.
- If it stays flat throughout → dwell time is an outcome 
  characteristic, not a real-time signal. Still useful for 
  post-hoc analysis but not for live trade management.

📌 REMINDER: This is about real-time usability of dwell 
time — can we use partial dwell during a trade, or only 
after the fact?

================================================================
CHECK 8: FLIP COUNT AT TIGHTER THRESHOLD
================================================================

⚠️ The baseline at 40t showed 302/313 rays with 3+ flips 
(max = 313 flips on a single ray). At 40t, price oscillates 
through the proximity zone so frequently that every ray 
appears to be constantly flipping. This may be inflating the 
bounce streak signal — a "just flipped" ray at 40t might 
just mean price barely crossed 40t to the other side, not 
a real polarity change.

Re-run Section 3A (flip frequency), 3C (bounce streak), 
and 3D (retest) at 20t threshold:

A) Flip frequency at 20t:
| Metric (20t) | Value |
|-------------|-------|
| Rays with 0 flips | ? |
| Rays with 1 flip | ? |
| Rays with 2 flips | ? |
| Rays with 3+ flips | ? |
| Max flips | ? |

B) Bounce streak at 20t:

📌 REMINDER: This check uses 20t threshold — all other checks 
use 40t. Comparing the two thresholds tells us if lifecycle 
tracking needs a different threshold than interaction detection.

| Bounce streak (20t) | Next bounce % | n |
|--------------------|--------------|---|
| 0 (just flipped) | ? | ? |
| 1 confirmed | ? | ? |
| 2 confirmed | ? | ? |
| 3+ confirmed | ? | ? |

C) Compare to baseline:
| Metric | 40t baseline | 20t follow-up |
|--------|-------------|--------------|
| Bounce streak 0→1 jump | 29.0pp | ? |
| 3+ bounce rate | 79.2% | ? |
| Max flips per ray | 313 | ? |
| Rays with 3+ flips | 302 | ? |

⚠️ INTERPRETATION:
- If bounce streak spread is WIDER at 20t → the tighter 
  threshold produces cleaner lifecycle signal. Use 20t for 
  lifecycle/flip tracking even though 40t is used for 
  initial interaction detection.
- If spread NARROWS or disappears → 40t is correct despite 
  high flip counts. The oscillation is how rays actually 
  behave.
- If max flips drops dramatically (313 → e.g. 15) → 40t was 
  counting noise as flips. 20t is the correct lifecycle 
  threshold.

⚠️ It is valid for the INTERACTION threshold (40t) and the 
FLIP threshold (20t) to be different. The interaction 
threshold defines "price is near the ray." The flip threshold 
defines "price has genuinely crossed to the other side." 
These are different questions.

D) Retest at 20t (if flip counts are reasonable):
| Pre-flip bounces (20t) | Retest bounce % | n |
|-----------------------|----------------|---|
| 0 (broke on first) | ? | ? |
| 1 bounce before break | ? | ? |
| 2 bounces before break | ? | ? |
| 3+ bounces before break | ? | ? |

⚠️ The baseline showed NO retest carryover at 40t (~48% 
regardless of pre-flip bounces). If 20t produces a different 
result — particularly if pre-flip strength DOES carry over 
at a tighter threshold — then the 40t flips were too noisy 
to detect the carryover effect.

📌 REMINDER: Check 8 uses 20t threshold. All other checks 
use 40t. These can be DIFFERENT thresholds for different 
purposes (interaction detection vs lifecycle tracking).

================================================================
CHECK 9: HTF RAYS AS STOP / TARGET / ENTRY REFINEMENT
================================================================

⚠️ The baseline showed rays exist near most trades (83% have 
a ray between entry and T1) but didn't test whether HTF rays 
specifically could tighten stops, provide earlier targets, or 
improve entry precision. This check uses 60m+ rays only.

A) TIGHTER STOPS VIA ADVERSE-SIDE HTF RAY.

For qualifying zone touches (ZONEREL config), identify cases 
where a 60m+ ray sits on the ADVERSE side between entry and 
the current stop level (Stop = max(1.5×ZW, 120t)):

| Metric | Value |
|--------|-------|
| Qualifying touches with adverse HTF ray within stop | ? (%) |
| Mean adverse HTF ray distance from entry (ticks) | ? |
| Mean current stop distance (ticks) | ? |
| Potential stop reduction (current stop - ray distance) | ? |

When price breaks through the adverse HTF ray, what happens?

⚠️ ADVERSE RAY BREAK DEFINITION: For stop analysis, "break" 
means price crosses the ray_price itself in the adverse 
direction — NOT the 40t proximity zone. The question is 
whether the ray price is a hard level: once crossed, does 
price continue to the full stop? The 40t close-based 
definition from Section 2B is too loose for this purpose.

| After adverse HTF ray break | Count | % |
|----------------------------|-------|---|
| Price continues to full stop level | ? | ? |
| Price reverses before reaching stop | ? | ? |

⚠️ If 80%+ of adverse ray breaks lead to the full stop, then 
the ray break IS the stop signal — you can tighten the stop 
to just past the ray (ray_price + buffer) and lose almost 
nothing. Report the buffer needed (distance from ray break 
to eventual stop hit).

Split by ray bounce streak (does a high-streak adverse ray 
provide a better stop signal?):

| Adverse ray bounce streak | Break → full stop % | n |
|--------------------------|--------------------|----|
| 0-1 bounces | ? | ? |
| 2+ bounces | ? | ? |
| 3+ bounces | ? | ? |

B) HTF RAY AS EARLIER TARGET.

⚠️ The all-ray ladder was too dense (28.3t spacing). With 
60m+ filter, is the spacing usable?

| Metric (60m+ rays only) | Value |
|------------------------|-------|
| Mean distance between adjacent HTF rays | ? |
| Median distance between adjacent HTF rays | ? |
| % of qualifying touches with HTF ray between entry and T1 | ? |
| Mean HTF ray distance from entry (as % of T1) | ? |

For touches where a HTF ray sits between entry and T1:

| Outcome at the HTF ray | Count | % |
|-----------------------|-------|---|
| Price passes through ray, reaches T1 | ? | ? |
| Price stalls at ray, eventually reaches T1 | ? | ? |
| Price stalls at ray, reverses (never T1) | ? | ? |
| Price stalls at ray, reverses to stop | ? | ? |

⚠️ If a significant % of stalls at HTF rays reverse to stop, 
taking profit at the ray instead of waiting for T1 would have 
captured the profit and avoided the loss. Calculate:
- PnL taking profit at HTF ray for stall-reversal trades
- PnL under current T1 for the same trades
- Net improvement from ray-based early exit

Split by ray bounce streak:
| Ray bounce streak | Stall → reverse % | n |
|------------------|-------------------|----|
| 0-1 bounces | ? | ? |
| 2+ bounces | ? | ? |
| 3+ bounces | ? | ? |

⚠️ High bounce streak rays between entry and T1 are the 
strongest obstacles — price is likely to stall there. Low 
streak rays are weaker obstacles.

C) PRECISION ENTRY VIA HTF RAY INSIDE ZONE.

⚠️ On wide zones (200t+), the current entry is at the zone 
edge. If a fresh 60m+ ray sits inside the zone, entering at 
the ray instead of the edge gives a deeper entry with a 
tighter effective stop.

For qualifying touches on wide zones (ZoneWidth > 200t) with 
a 60m+ ray inside the zone:

| Metric | Value |
|--------|-------|
| Wide zone touches with HTF ray inside zone | ? (%) |
| Mean ray depth inside zone (ticks from edge) | ? |
| Mean ray depth (as % of zone width) | ? |

If entry shifted from zone edge to the HTF ray inside:
| Metric | Edge entry (current) | Ray entry (shifted) |
|--------|---------------------|-------------------|
| Mean entry to T1 distance | ? | ? |
| Mean entry to stop distance | ? | ? |
| Risk:reward ratio | ? | ? |

⚠️ This is observational — measuring whether the geometry 
improves. The execution challenge (price may not reach the 
ray inside the zone, missing the trade entirely) must also 
be measured:

| Metric | Value |
|--------|-------|
| Wide zone touches where price reaches HTF ray inside | ? (%) |
| Trades missed by waiting for ray entry | ? (%) |

📌 REMINDER: Check 9 uses 60m+ rays only. ZONEREL exit 
config (T1=0.5×ZW, T2=1.0×ZW, Stop=max(1.5×ZW, 120t)). 
These are observational measurements — do not propose rule 
changes.

================================================================
SUMMARY
================================================================

⚠️ For each check, report:
- CONFIRMED: baseline finding holds after deconfounding
- REFINED: finding holds but with important nuance
- OVERTURNED: finding does not hold after proper testing
- NEW FINDING: something not in the baseline emerges
- INSUFFICIENT DATA: sample size too small to conclude

| Check | Finding | Status |
|-------|---------|--------|
| 1. HTF density | Does 60m+ filter create testable groups? | ? |
| 2. Fresh + fresh | Interaction between ray and zone freshness | ? |
| 3. HTF R/P | Rays as congestion vs confluence (cleaned) | ? |
| 4. Age vs streak | Is freshness independent of bounce streak? | ? |
| 5. HTF lifecycle | Bounce streak stronger at 60m+? | ? |
| 6. Regime stability | Do key findings hold in P1 AND P2? | ? |
| 7. Dwell survival | Is dwell time usable in real-time? | ? |
| 8. Tighter flips | Does 20t produce cleaner lifecycle? | ? |
| 9a. HTF stop tightening | Can adverse HTF ray reduce stop size? | ? |
| 9b. HTF ray as target | Do HTF rays between entry and T1 cause stalls? | ? |
| 9c. Precision entry | Does entering at HTF ray inside zone improve R:R? | ? |

⚠️ DECISION GATE: If Check 6 shows any STRONG baseline 
finding is UNSTABLE across regimes, do NOT advance it to 
feature screening. Flag for further investigation.

Save results to ray_htf_followup.md
