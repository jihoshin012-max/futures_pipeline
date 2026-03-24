Ray feature screening — Prompt 1a equivalent.

PURPOSE: Test which ray attributes improve the zone touch 
scoring model when added as features. The baseline and 
follow-up identified 11 surviving attributes. This prompt 
screens each one against the existing 4-feature A-Cal model 
(F10, F04, F01, F21) to determine which add predictive value.

⚠️ THIS IS FEATURE SCREENING — parameters are being fit. 
Use P1 for calibration. P2 for validation ONLY. Do NOT look 
at P2 results until all P1 screening is complete.

DATA:
- P1: NQ_ZTE_raw_P1.csv (325 touches), NQ_ray_context_P1.csv, 
  NQ_ray_reference_P1.csv, P1 bar data
- P2 (validation only): same files with _P2 suffix
- Existing A-Cal model: 4 features (F10, F04, F01, F21), 
  threshold 16.66, PF 11.96 on P1 (77-trade replication 
  population)

⚠️ RAY TF FILTER: Use 60m+ rays ONLY throughout this prompt. 
Discard all 15m and 30m rays. The baseline proved TF has no 
effect on individual ray behavior (2.5pp), but LTF rays 
triple the density and mask real effects. Filter in Python — 
ZTE's accumulator still captures all rays for data completeness. 
This filter applies to ALL sections.

⚠️ Ray lifecycle attributes (bounce streak, flip count, 
dwell time, S/R decay) are NOT currently in ray_context.csv. 
They must be COMPUTED from ray_reference + bar data before 
screening can begin. Section 0 handles this prerequisite.

================================================================
SECTION 0: DATA PREREQUISITE — COMPUTE RAY LIFECYCLE
================================================================

⚠️ Before any screening, build the ray lifecycle features 
from raw data. For each ray in ray_reference.csv, reconstruct 
its full interaction history using P1 bar data and the 
baseline definitions:

Definitions (from ray_baseline_analysis.md):
- Proximity threshold: 40t
- Close method: 15m bar close
- Bounce: 15m bar close on original side of ray
- Break: 15m bar close past ray, sustained
- False break: 15m bar close past ray, reverses within 1-2 bars
- Flip: a confirmed break (not a false break)

For each ray at each zone touch time, compute:

| Feature | Definition | Type |
|---------|-----------|------|
| ray_bounce_streak | Consecutive bounces in current polarity at touch time | int (0, 1, 2, 3+) |
| ray_flip_count | Total polarity flips in ray's lifetime at touch time | int |
| ray_dwell_bars | If price is currently near this ray at touch time, how many bars has it been dwelling? | int |
| ray_decay_magnitude | Mean bounce magnitude of last 3 interactions vs first 3 (ratio) | float |
| ray_approach_velocity | Price movement rate over prior 5 bars toward the ray | float (ticks/bar) |
| ray_session | RTH or ETH at touch time | categorical |
| ray_close_type | Last interaction outcome: strong_rejection, weak_rejection, acceptance, confirmed_acceptance, failed_acceptance | categorical |
| ray_dist_ticks | Distance from ray to touch zone edge | float |
| ray_tf | Source timeframe of the ray | categorical |
| ray_between_entry_t1 | Is this ray between entry and T1? | boolean |
| ray_cross_tf_count | Number of other TFs with rays within 20t of this ray | int |

⚠️ These features are computed PER RAY. At each zone touch, 
there may be multiple nearby rays. Aggregate to one value per 
touch using TWO aggregation rules depending on purpose:

BACKING RAY (for entry scoring — features A-G, J, K): 
Use the nearest HTF (60m+) ray by distance that is AT or 
BEHIND the entry (inside zone or on the same side as the 
stop). If no qualifying ray within 30t, use NULL/missing.

OBSTACLE RAY (for trade management — features H, I): 
Use the nearest HTF (60m+) ray AHEAD of entry (between 
entry price and T1/T2). If no qualifying ray ahead, use 
NULL/missing.

Report both aggregations. A touch may have a backing ray 
AND an obstacle ray — these are different rays serving 
different purposes.

📌 REMINDER: Use P1 data only for building lifecycle features. 
P2 features are computed identically but NOT examined until 
Section 4 (validation).

Save the enriched touch dataset with ray features to:
p1_touches_with_ray_features.csv

Verify:
- Row count matches NQ_ZTE_raw_P1.csv (325 touches)
- All ray feature columns populated (report % NULL for each)
- Spot check 5 touches: does bounce streak match manual count?

================================================================
SECTION 1: INDIVIDUAL FEATURE SCREENING
================================================================

⚠️ Test each ray attribute INDIVIDUALLY against the existing 
4-feature baseline. The question is: does adding this one 
feature to the existing model improve R/P separation?

Methodology for each candidate feature:
1. Split P1 touches into bins by the feature value
2. For each bin, compute R/P ratio
3. Measure the SPREAD between best and worst bins
4. Compare monotonicity (does R/P improve consistently 
   across bins, or is it noisy?)
5. Report sample size per bin — flag any bin with n < 15

⚠️ For continuous features, use quartile bins (Q1-Q4). For 
categorical features, use natural categories. For boolean 
features, use present/absent.

A) ray_bounce_streak (STRONG — 30.7pp in baseline):
| Bounce streak | Touches | Mean Rxn | Mean Pen | R/P | n |
|--------------|---------|---------|---------|-----|---|
| 0 (just flipped) | ? | ? | ? | ? | ? |
| 1 | ? | ? | ? | ? | ? |
| 2 | ? | ? | ? | ? | ? |
| 3+ | ? | ? | ? | ? | ? |

📌 REMINDER: P1 only. This is the strongest baseline signal 
(30.7pp). If R/P separation is weak on P1 zone touches 
specifically, it means the ray signal doesn't transfer to 
zone touch quality — bounce streak predicts ray interactions 
but not trade outcomes.

B) ray_dwell_bars (STRONG — 21.9pp in baseline):
| Dwell time bin | Touches | R/P | n |
|---------------|---------|-----|----|
| 1-2 bars (decisive) | ? | ? | ? |
| 3-5 bars | ? | ? | ? |
| 6-10 bars | ? | ? | ? |
| 10+ bars | ? | ? | ? |
| Not currently dwelling | ? | ? | ? |

⚠️ "Not currently dwelling" = price is not within 40t of 
any ray at touch time. This may be the majority of touches.

C) ray_session (STRONG — 13.6pp in baseline):
| Session | Touches | R/P | n |
|---------|---------|-----|----|
| RTH | ? | ? | ? |
| ETH | ? | ? | ? |

⚠️ SessionClass is already in the zone touch model. Session 
at touch time is the same regardless of whether measured from 
the zone or ray perspective. This feature will likely correlate 
~1.0 with existing SessionClass and add no independent signal. 
Report the correlation. If correlation > 0.9, DROP immediately 
without further testing — it's redundant, not a new feature.

D) ray_flip_count (STRONG — 14.4pp in baseline):
| Flip count | Touches | R/P | n |
|-----------|---------|-----|----|
| 0 (never flipped) | ? | ? | ? |
| 1 | ? | ? | ? |
| 2-3 | ? | ? | ? |
| 4+ | ? | ? | ? |

E) ray_close_type (STRONG — structurally distinct):
| Last interaction close type | Touches | R/P | n |
|----------------------------|---------|-----|----|
| Strong rejection | ? | ? | ? |
| Weak rejection | ? | ? | ? |
| Failed acceptance | ? | ? | ? |
| Confirmed acceptance | ? | ? | ? |
| No prior interaction | ? | ? | ? |

F) ray_decay_magnitude (MODERATE — 7.3% decline):
| Decay ratio (recent/early bounce magnitude) | Touches | R/P | n |
|--------------------------------------------|---------|-----|----|
| > 1.0 (strengthening) | ? | ? | ? |
| 0.8-1.0 (stable) | ? | ? | ? |
| < 0.8 (decaying) | ? | ? | ? |

⚠️ Requires 3+ interactions to compute. Touches near rays 
with < 3 interactions will have NULL for this feature.

G) ray_approach_velocity (MODERATE — 4.5pp):
| Approach velocity | Touches | R/P | n |
|------------------|---------|-----|----|
| Fast (> 5 ticks/bar) | ? | ? | ? |
| Medium (2-5) | ? | ? | ? |
| Slow (< 2) | ? | ? | ? |

H) ray_between_entry_t1 (MODERATE — stall finding):
| Ray between entry and T1? | Touches | R/P | n |
|--------------------------|---------|-----|----|
| Yes, HTF ray in path | ? | ? | ? |
| No HTF ray in path | ? | ? | ? |

⚠️ Use ZONEREL targets (T1=0.5×ZW). "In path" = HTF ray 
between entry price and T1 price with 3+ bounce streak 
(strong obstacle).

I) ray_cross_tf_count (NEW FINDING — limited discriminatory):
| TFs converging within 20t | Touches | R/P | n |
|--------------------------|---------|-----|----|
| 0-1 TFs | ? | ? | ? |
| 2 TFs | ? | ? | ? |
| 3+ TFs | ? | ? | ? |

⚠️ Baseline showed 93% of touches have 3+ TFs converging. 
This may only work as a negative filter (flag 0-1 TFs as 
weaker), not a positive signal.

J) 15m_bar_close (STRONG — 74.2% accuracy):

⚠️ This is the close method, not a feature per se. It 
governs how bounce/break is classified. The question for 
screening is: does the 15m bar close at the NEAREST ray 
at touch time predict zone touch R/P?

| 15m close at nearest ray | Touches | R/P | n |
|-------------------------|---------|-----|----|
| Close on bounce side (rejection) | ? | ? | ? |
| Close on break side (acceptance) | ? | ? | ? |
| No ray interaction at touch time | ? | ? | ? |

K) ray_dist_ticks (proximity to nearest HTF ray):
| Distance to nearest HTF ray | Touches | R/P | n |
|----------------------------|---------|-----|----|
| < 10t (very close) | ? | ? | ? |
| 10-20t | ? | ? | ? |
| 20-30t | ? | ? | ? |
| 30t+ or no ray | ? | ? | ? |

📌 REMINDER: All screening on P1 only. 325 touches is a 
small population — some bins may be sparse. Flag any bin 
with n < 15 as LOW CONFIDENCE. Do not drop the feature 
solely due to small bins — flag and continue.

================================================================
SECTION 2: RANKING AND SELECTION
================================================================

⚠️ After Section 1, rank all 11 features by their R/P 
separation spread on P1:

| Rank | Feature | Best bin R/P | Worst bin R/P | Spread | Monotonic? | Min bin n |
|------|---------|-------------|-------------|--------|-----------|----------|
| 1 | ? | ? | ? | ? | ? | ? |
| 2 | ? | ? | ? | ? | ? | ? |
| ... | ? | ? | ? | ? | ? | ? |

Selection criteria:
- ADVANCE: Spread > 0.5 R/P AND monotonic AND min bin n ≥ 15
- MARGINAL: Spread > 0.3 but non-monotonic or min bin n < 15
- DROP: Spread < 0.3 or no consistent pattern

⚠️ Also check for REDUNDANCY. If two features are highly 
correlated (e.g., bounce streak and flip count both measure 
lifecycle state), only the stronger one advances. Report 
correlation between all ADVANCE features:

| Feature A | Feature B | Correlation | Keep? |
|-----------|-----------|-------------|-------|
| ? | ? | ? | ? |

📌 REMINDER: All on P1. Do NOT look at P2 yet.

================================================================
SECTION 3: COMBINATION TESTING
================================================================

⚠️ Test the top features in combination with the existing 
4-feature model. The question is: does adding ray features 
improve the model's ability to separate good touches from 
bad ones?

Take the ADVANCE features from Section 2. For each:

A) Add the ray feature to the existing A-Cal model as a 
5th feature. Compute the combined score. Split P1 touches 
by combined score quintiles:

| Score quintile | Touches | R/P | WR | n |
|---------------|---------|-----|----|---|
| Q1 (lowest) | ? | ? | ? | ? |
| Q2 | ? | ? | ? | ? |
| Q3 | ? | ? | ? | ? |
| Q4 | ? | ? | ? | ? |
| Q5 (highest) | ? | ? | ? | ? |

Compare to the existing 4-feature model's quintile separation:

| Metric | 4-feature baseline | 5-feature (+ ray) | Delta |
|--------|-------------------|-------------------|-------|
| Q5/Q1 R/P ratio | ? | ? | ? |
| Q5 R/P | ? | ? | ? |
| Q1 R/P | ? | ? | ? |

B) If multiple ray features ADVANCE, test the best 2-feature 
ray combination added to the 4-feature model (6 features total):

| Metric | 4-feature | +best ray | +2 best rays | 
|--------|----------|-----------|-------------|
| Q5/Q1 R/P ratio | ? | ? | ? |
| Q5 R/P | ? | ? | ? |

⚠️ Adding features to a 325-touch P1 dataset risks overfitting. 
Do NOT add more than 2 ray features. The model has 4 features 
already — going to 6 or 7 on 325 touches is too many parameters 
for the sample size.

⚠️ WEIGHT CALIBRATION: When adding a ray feature, test 
multiple weight ratios against the existing 4-feature score. 
The ray feature may need a different weight scale:

| Ray feature weight (as % of total score) | Q5/Q1 ratio |
|----------------------------------------|------------|
| 5% | ? |
| 10% | ? |
| 15% | ? |
| 20% | ? |
| 25% | ? |

📌 REMINDER: All calibration on P1. The weight that produces 
the best Q5/Q1 separation on P1 goes to P2 validation. ONE 
weight, chosen before looking at P2.

================================================================
SECTION 4: P2 VALIDATION
================================================================

⚠️ HOLDOUT GATE. Run this section ONLY after Sections 1-3 
are fully complete and the model specification is frozen. 
Do NOT iterate after seeing P2 results.

Take the final model from Section 3 (existing 4 features + 
best ray feature(s) at calibrated weight) and run on P2:

A) Compute ray lifecycle features for P2 touches using the 
same pipeline from Section 0 (P2 bar data, P2 ray_reference, 
P2 ray_context). Save to p2_touches_with_ray_features.csv.

B) Apply the P1-calibrated model to P2:

| Metric | P1 (calibration) | P2 (validation) |
|--------|-----------------|----------------|
| Total touches | 325 | 3,537 |
| Q5/Q1 R/P ratio | ? | ? |
| Q5 R/P | ? | ? |
| Q1 R/P | ? | ? |
| Touches above threshold | ? | ? |
| PF above threshold | ? | ? |
| WR above threshold | ? | ? |

⚠️ PASS CRITERIA:
- Q5/Q1 ratio on P2 must be > 50% of P1's Q5/Q1 ratio
- PF above threshold on P2 must be > 3.0
- The ray feature must IMPROVE the P2 metric vs the existing 
  4-feature model (not just match it)

If the ray feature improves P1 but NOT P2, it's overfit. Drop 
it. The existing 4-feature model stands.

C) Compare to existing model on P2:

| Metric | 4-feature model (P2) | With ray feature(s) (P2) | Delta |
|--------|---------------------|------------------------|-------|
| PF | ? | ? | ? |
| WR | ? | ? | ? |
| Total PnL | ? | ? | ? |
| Mean PnL per trade | ? | ? | ? |

📌 REMINDER: This is the FINAL gate. If ray features don't 
improve P2 performance, they do not enter the model. The 
4-feature A-Cal model continues unchanged to paper trading.

================================================================
SECTION 5: IMPLEMENTATION SPECIFICATION
================================================================

⚠️ Only complete this section if Section 4 passes.

⚠️ Ray features may serve TWO distinct purposes. The screening 
results determine which path (or both) each feature takes:

PATH 1 — ENTRY SCORING: Ray attributes that predict zone 
touch QUALITY (R/P) get added to the A-Cal scoring model. 
These are rays AT or BEHIND the entry — they describe the 
S/R structure backing the trade. Example: a zone touch 
backed by a high-bounce-streak ray is a higher-quality setup.

PATH 2 — TRADE MANAGEMENT: Ray attributes that predict what 
happens AHEAD of the entry inform adaptive exit logic. These 
are rays between entry and T1/T2. Example: a strong resistance 
ray ahead means take full profit early; a weak ray ahead means 
let the runner go.

A feature can serve BOTH paths (e.g., bounce streak of the 
backing ray → entry scoring, bounce streak of the obstacle 
ray → exit management). The same attribute, applied to 
different ray populations relative to the trade.

⚠️ Classify each surviving feature into Path 1, Path 2, or 
both before writing the implementation spec.

For each ray feature that passes validation, classify:

| Feature | Path 1 (entry scoring) | Path 2 (exit management) |
|---------|----------------------|------------------------|
| ? | YES/NO | YES/NO |

A) Feature definition:
| Field | Value |
|-------|-------|
| Feature name | ? |
| Data source | ray_context.csv / computed from bar data |
| Computation | exact formula/algorithm |
| Value range | min-max |
| Bin edges | for A-Cal scoring |
| Weight in combined score | % of total |

B) Pipeline integration:
- Where does this feature get computed? (Python pipeline / 
  C++ ZTE / both?)
- What new data does ZTE need to export?
- Does ray_context.csv need new columns?

📌 REMINDER: Path 1 features modify the scoring model. 
Path 2 features modify exit logic. Both may require ZTE 
to track ray lifecycle in real-time (bounce streak, flip 
count per ray in the accumulator).

C) C++ autotrader impact:
- Does the autotrader need to read ray lifecycle data?
- If so, through persistent storage or CSV?
- Estimated code changes (lines, files)

⚠️ If the ray feature requires ZTE to compute and export 
bounce streak per ray (real-time lifecycle tracking), that's 
a significant C++ change. Document the scope.

D) Replication gate:
- After implementation, re-run C++ test mode
- New answer keys required (ray features change scoring)
- Expected trade count change vs current 77 ZONEREL / 85 FIXED

E) Real-time close method for trade management (Path 2 only):

⚠️ 15m bar close is the best classification method but takes 
up to 15 minutes — too slow for real-time exit decisions 
during a trade. Compare 15m vs consecutive 250-vol closes 
specifically on the Path 2 use case (stall detection at ray 
between entry and T1).

For trades where price reaches an HTF ray between entry and 
T1, classify the ray interaction using both methods and 
compare outcomes:

| Close method | Stalls correctly ID'd | False stall signals | n |
|-------------|---------------------|--------------------|----|
| 15m bar close | ? | ? | ? |
| 2 consecutive 250-vol closes | ? | ? | ? |
| 3 consecutive 250-vol closes | ? | ? | ? |
| 4 consecutive 250-vol closes | ? | ? | ? |

⚠️ "Correctly ID'd" = method classified interaction as 
rejection/stall AND price actually reversed (never reached 
T1). "False stall" = method said stall but price continued 
to T1.

| Metric | 15m close | Best N-consecutive 250-vol |
|--------|----------|--------------------------|
| Accuracy | ? | ? |
| Mean detection delay (bars) | ? | ? |
| PnL on stall-exit trades | ? | ? |

⚠️ If accuracy gap between 15m and best consecutive 250-vol 
is < 5pp, use the 250-vol method for trade management — it's 
available in real-time without needing 5m data infrastructure. 
If gap is > 10pp, 5m bar data may be needed. Report the gap 
and recommend.

F) Trade management specification (Path 2 features only):

If any feature advances on Path 2 (exit management), specify 
the adaptive exit logic:

| Scenario | Ray condition ahead | Exit action |
|----------|-------------------|-------------|
| Strong obstacle | Bounce streak 3+, low flip count | ? (e.g., take 100% at ray, skip T1) |
| Weak obstacle | Bounce streak 0-1, high flip count | ? (e.g., hold runner, keep T2) |
| No ray ahead | No HTF ray between entry and T1 | ? (e.g., current static exits) |
| Decaying obstacle | High streak but decay ratio < 0.8 | ? (e.g., hold but tighten stop) |

⚠️ Do NOT calibrate exit rules here. Document the LOGIC 
for a separate exit management prompt. The screening proves 
whether ray strength ahead predicts trade outcomes — the 
exit rules require their own calibration on P1 and validation 
on P2.

Save results to ray_feature_screening.md
