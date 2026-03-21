# Volume Profile Analysis: Spatial Structure at Fractal Inflection Points

## OBJECTIVE

Investigate whether volume-at-price structure explains WHY some fractal pullbacks are shallow and others deep, and whether volume profile imbalances predict pullback completion. This extends the fractal knowledge base with a spatial dimension — not just what happens at fractal events, but where those events sit in the volume landscape.

This is market-structure research. Results are recorded in the fractal knowledge base, not applied to the current strategy iteration.

⚠️ **This is fractal research, not strategy optimization. Results go to `fractal_discovery/volume_profile/`, not to the strategy directory. Run this ONLY if the structural factor analysis (Queries 1-7) shows that pullback depth or multi-scale alignment produces a STRONG gradient. If those queries show no gradient, volume profile is unlikely to add useful information.**

---

## PREREQUISITE

Structural factor analysis (7 queries) must be complete. This analysis is warranted if:
- Query 1 (volume) shows STRONG or MODERATE gradient, OR
- Query 4 (bar range) shows STRONG or MODERATE gradient, OR
- Query 5 (multi-scale alignment) shows STRONG gradient

📌 **If none of those conditions are met, shelve this analysis. Volume profile is a potential MECHANISM explaining why those factors work. If the factors themselves don't work, the mechanism is irrelevant.**

---

## DATA

- P1 1-tick bars, RTH only, Sept 22 – Dec 12, 2025
- Same bar data used for all prior fractal analyses
- Parent thresholds: 25pt and 40pt
- Child thresholds: 10pt and 16pt (ratio 0.4)

---

## STEP 1: Build Rolling Volume Profile

For each bar in the dataset, compute a volume-at-price distribution over a trailing lookback window:

**Lookback:** 1 RTH session (previous full day). This captures the most recent "value area" without overfitting to stale structure.

⚠️ **Use the PREVIOUS session's data, not the current session. The profile must be fully known before the current session's price action begins — no lookahead bias.**

**Construction:**
1. Divide the previous session's price range into bins of 1 point (4 ticks for NQ)
2. Sum volume traded in each bin
3. Identify:
   - **POC (Point of Control):** price bin with highest volume
   - **Value Area High/Low:** price range containing 70% of total volume (centered on POC)
   - **Low Volume Nodes (LVN):** bins with volume < 20% of POC volume
   - **High Volume Nodes (HVN):** bins with volume > 80% of POC volume

📌 **The volume profile is computed ONCE per session from the prior day's data. Every bar within the current session references the same profile. This is a static spatial map, not a rolling indicator.**

---

## STEP 2: Classify Fractal Events by Volume Profile Location

For each child pullback in the child-walk decomposition, determine:

**pullback_reversal_location:** Where did the pullback reverse (resume the parent direction)?
- **AT_HVN:** within 2 points of a high volume node
- **AT_LVN:** within 2 points of a low volume node
- **AT_VAH/VAL:** within 2 points of value area boundary
- **IN_VALUE:** inside the value area but not near a node
- **OUTSIDE_VALUE:** outside the value area

**parent_target_location:** Where is the parent completion target relative to the profile?
- Same categories as above

📌 **The hypothesis: pullbacks that reverse at HVNs (structural support/resistance from prior day's trading) should complete at higher rates because those levels represent accepted value where institutional order flow concentrates. Pullbacks that reverse at LVNs are in "thin air" — less structural support for the reversal.**

---

## STEP 3: Completion Rate by Volume Profile Location

Report completion rate of parent move after the first child pullback, bucketed by where the pullback reversed:

| Pullback Reversal Location | Sample Count | Completion Rate |
|---------------------------|-------------|----------------|
| AT_HVN | ? | ? |
| AT_VAH/VAL | ? | ? |
| IN_VALUE | ? | ? |
| AT_LVN | ? | ? |
| OUTSIDE_VALUE | ? | ? |

⚠️ **Sample sizes may be uneven. If any bucket has fewer than 50 observations, flag it as low-confidence. The LVN and OUTSIDE_VALUE buckets may be small since most trading occurs within the value area.**

---

## STEP 4: Volume Profile and Pullback Depth Interaction

Cross-tabulate pullback location with pullback depth:

| | Shallow Pullback (≤50%) | Deep Pullback (>50%) |
|---|---|---|
| **Pullback at HVN** | ?% (n=?) | ?% (n=?) |
| **Pullback at LVN** | ?% (n=?) | ?% (n=?) |
| **Other** | ?% (n=?) | ?% (n=?) |

📌 **This answers the causal question: are shallow pullbacks shallow BECAUSE they hit a high-volume node? If shallow+HVN shows 95% completion and shallow+LVN shows 75%, the volume node is the mechanism behind the depth gradient. If both show ~85%, depth works independently of volume location and volume profile adds no new information.**

---

## STEP 5: Path Through Volume Profile

**Question:** Do parent moves that travel through low-volume zones complete at higher rates than those that must traverse high-volume zones?

For each parent move:
1. Map the path from current price to parent target
2. Compute the volume density along this path: sum of profile volume in all bins between current price and target
3. Normalize by path distance (volume per point of travel)

Bucket into quartiles:

| Path Volume Density | Sample Count | Completion Rate |
|--------------------|-------------|----------------|
| Q1 (low density = clear path) | ? | ? |
| Q2 | ? | ? |
| Q3 | ? | ? |
| Q4 (high density = congested path) | ? | ? |

⚠️ **The intuition: price moves faster through low-volume zones (no orders to absorb) and slower through high-volume zones (institutional positions create resistance). A parent move with a "clear path" through LVN territory should complete more readily than one that must push through the prior day's POC.**

---

## STEP 6: Session Open Relative to Prior Profile

**Question:** Does the relationship between the session open and the prior day's value area predict the character of the day's fractal structure?

For each trading day, classify the open:
- **INSIDE:** open price is within prior day's value area
- **ABOVE:** open price is above value area high
- **BELOW:** open price is below value area low

Report for each:

| Open Location | Days | Avg Parent Swings/Day | Avg Completion Rate | Avg First-Pullback Completion |
|--------------|------|----------------------|--------------------|-----------------------------|
| INSIDE | ? | ? | ? | ? |
| ABOVE | ? | ? | ? | ? |
| BELOW | ? | ? | ? | ? |

📌 **Open-inside-value days often mean-revert (rotational). Open-outside-value days often trend (directional). If this distinction shows a 15pp+ completion difference, it's a structural regime signal grounded in volume profile — different from ATR or persistence because it's based on where price IS relative to accepted value, not how fast it's moving.**

---

## OUTPUT

Save to: `C:\Projects\pipeline\stages\01-data\analysis\fractal_discovery\volume_profile\`

⚠️ **Same boundary as the structural factor analysis: these are market properties, not strategy parameters. Record findings, verify on P2a before any application.**

```
volume_profile/
├── volume_profile_builder.py     # Script to compute rolling profiles
├── pullback_at_profile.csv       # Step 3: completion by reversal location
├── depth_profile_interaction.csv # Step 4: depth × location cross-tab
├── path_density.csv              # Step 5: completion by path volume
├── open_vs_profile.csv           # Step 6: session open classification
└── volume_profile_summary.md     # Summary with verdicts
```

### Summary Format

Same as structural factor analysis:
- **STRONG** (>15pp spread): significant spatial property of fractal structure
- **MODERATE** (10-15pp spread): measurable, record for reference
- **WEAK** (<10pp spread): volume profile doesn't explain fractal behavior at this level
- **REDUNDANT**: correlated with depth or another factor already identified

📌 **Record all findings regardless of strength. If Step 4 shows volume profile explains the depth gradient causally, note that even if the standalone gradient is moderate — it provides mechanism, not just correlation.**

---

## SELF-CHECK BEFORE FINISHING

- [ ] Prerequisite confirmed: structural factor analysis shows relevant gradient
- [ ] Volume profile built from PREVIOUS session data only (no lookahead)
- [ ] Profile bins at 1pt resolution (4 ticks)
- [ ] POC, value area (70%), HVN (>80% of POC), LVN (<20% of POC) identified
- [ ] Pullback reversal locations classified against prior-day profile
- [ ] Completion rates reported by reversal location
- [ ] Depth × location cross-tabulation computed
- [ ] Path volume density computed for parent moves
- [ ] Session open vs value area classification computed
- [ ] All results saved to `fractal_discovery/volume_profile/` (NOT strategy directory)
- [ ] Summary with verdicts produced
- [ ] Results framed as structural findings, not strategy recommendations
