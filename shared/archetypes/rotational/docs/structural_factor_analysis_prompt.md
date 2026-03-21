# Structural Factor Analysis: Extending the Fractal Knowledge Base

## OBJECTIVE

Extend the fractal discovery with additional dimensions of market behavior at fractal inflection points. The original six facts describe the GEOMETRY of price movement — distance, count, ratios, waste. These queries add INTENSITY (volume), SPEED, TIME, VOLATILITY, and MULTI-SCALE CONTEXT measurements at the same structural events (pullbacks, completions, failures).

These are market-structure findings, not strategy filters. Results are recorded as candidate Facts in the fractal knowledge base. They are NOT incorporated into the current strategy iteration. They inform future research after P2a validation of the current design.

⚠️ **This is fractal research, not strategy optimization. Results go to `fractal_discovery/structural_factors/`, not to the strategy directory. Do NOT reference any strategy parameter (StepDist, RT, AddDist) in the analysis. Measure the market, not the strategy.**

---

## DATA

- P1 1-tick bars, RTH only, Sept 22 – Dec 12, 2025
- Parent threshold: 25pt and 40pt (the two scales with the most practical relevance)
- Child threshold: 10pt (for 25pt parent) and 16pt (for 40pt parent) — ratio 0.4
- Grandparent threshold: 2.5× parent (62.5pt for 25pt parent, 100pt for 40pt parent)

📌 **Each query produces completion rates CONDITIONED on a structural factor. The baseline is the unconditional completion rate from the original fractal analysis: ~80% at 1 retracement. A factor that splits this into 90% vs 65% is useful. A factor that shows 80% vs 79% is not.**

---

## QUERY 1: Volume at Pullback

**Question:** Do pullbacks on low volume complete at higher rates than pullbacks on high volume?

For each child pullback within a parent move:
1. Compute the average volume per bar during the pullback (from child HWM to child reversal point)
2. Compute the average volume per bar during the preceding directional leg (from last child reversal to child HWM)
3. Compute the volume ratio: pullback_volume / directional_leg_volume

Bucket the volume ratio into quartiles and report completion rate for each:

| Volume Ratio Quartile | Sample Count | Completion Rate | Median Ratio |
|-----------------------|-------------|----------------|--------------|
| Q1 (low vol pullback) | ? | ? | ? |
| Q2 | ? | ? | ? |
| Q3 | ? | ? | ? |
| Q4 (high vol pullback) | ? | ? | ? |

⚠️ **Volume ratio is more informative than absolute volume. A pullback with 500 contracts/bar during a session averaging 200 is high conviction. The same 500 during a session averaging 1000 is quiet. The ratio normalizes for time-of-day and session-level volume differences.**

Also report: does volume ratio predict completion INDEPENDENTLY of pullback depth? Cross-tabulate:
- Shallow + low volume vs shallow + high volume
- Deep + low volume vs deep + high volume

📌 **If volume adds information beyond depth, it's a genuinely new structural dimension. If it's just a proxy for depth (deep pullbacks happen to have high volume), it's redundant.**

---

## QUERY 2: Speed of Initial Move

**Question:** Does the speed of the initial directional leg predict first-pullback completion?

For each parent move, compute the speed of the first child-scale leg (from parent start to first child HWM):
1. Distance in points (always ≥ child threshold by definition)
2. Duration in bars
3. Speed = distance / duration (points per bar)

Bucket speed into quartiles and report completion rate after the first pullback:

| Speed Quartile | Sample Count | Completion Rate | Median Speed |
|---------------|-------------|----------------|--------------|
| Q1 (slow) | ? | ? | ? |
| Q2 | ? | ? | ? |
| Q3 | ? | ? | ? |
| Q4 (fast) | ? | ? | ? |

⚠️ **Speed captures "conviction" of the initial move. A fast 10pt move (2-3 bars) suggests strong directional pressure. A slow 10pt move (200+ bars) suggests drift. If fast initial legs show 90% completion after pullback and slow ones show 70%, speed is a significant structural dimension of fractal quality.**

---

## QUERY 3: Time-of-Day for First Pullback

**Question:** Does the time when the first pullback completes affect completion rate?

For each parent move where at least one child pullback occurs, record the time of day when the first pullback completes (child reversal point after the first retracement).

Bucket into 30-minute windows and report:

| Time Window | Sample Count | Completion Rate |
|------------|-------------|----------------|
| 09:30-10:00 | ? | ? |
| 10:00-10:30 | ? | ? |
| ... | ... | ... |
| 15:30-16:00 | ? | ? |

📌 **The original fractal analysis showed time-of-day was stable for UNCONDITIONAL completion across all retracements. This query asks about FIRST PULLBACK completion specifically — a subset that may behave differently. The open (09:30-10:30) has gap resolution and overnight order flow that could create structurally distinct conditions.**

Also report: does time to first pullback (duration from parent start to first child pullback) vary by time of day?

---

## QUERY 4: Bar Range Profile

**Question:** Does the bar range during the pullback predict completion?

For each child pullback:
1. Compute median bar range (High - Low) during the pullback
2. Compute median bar range during the preceding directional leg
3. Compute the range ratio: pullback_bar_range / directional_leg_bar_range

Bucket into quartiles and report:

| Range Ratio Quartile | Sample Count | Completion Rate | Median Ratio |
|---------------------|-------------|----------------|--------------|
| Q1 (narrow pullback bars) | ? | ? | ? |
| Q2 | ? | ? | ? |
| Q3 | ? | ? | ? |
| Q4 (wide pullback bars) | ? | ? | ? |

⚠️ **Bar range measures something different from speed. Speed = distance/time. Bar range = volatility within each bar. A slow move with wide bars is choppy and indecisive. A slow move with narrow bars is calm drift. Same speed, different structural character. Report the correlation between range ratio and speed — if r > 0.7, they're measuring the same thing.**

---

## QUERY 5: Multi-Scale Alignment (Grandparent Context)

**Question:** Does the parent move's alignment with the grandparent-scale trend affect pullback completion?

⚠️ **This is the most important new query. The fractal structure is hierarchical. A parent move that's WITH the grandparent trend should complete at a higher rate than one fighting it. This is the multi-scale insight the original analysis didn't measure.**

For each parent move that experiences a child pullback:
1. Determine the grandparent-scale direction at the time the parent move starts. Use the grandparent zig-zag (62.5pt for 25pt parent, 100pt for 40pt parent). Is price in the favorable half of the current grandparent swing (WITH trend) or the unfavorable half (AGAINST trend)?
2. Classify as:
   - **WITH**: parent move direction matches grandparent swing direction AND price is in the first 50% of the grandparent swing (progressing toward grandparent target)
   - **AGAINST**: parent move opposes grandparent swing direction
   - **EXTENDED**: parent move matches grandparent direction but grandparent swing has already exceeded its typical range (parent P90)

Report completion rate for each:

| Alignment | Sample Count | Completion Rate |
|-----------|-------------|----------------|
| WITH grandparent | ? | ? |
| AGAINST grandparent | ? | ? |
| EXTENDED | ? | ? |

📌 **If WITH-trend pullbacks complete at 90% and AGAINST-trend at 65%, multi-scale alignment is the strongest structural predictor we've found. This would mean the fractal hierarchy carries directional information — not just geometric self-similarity, but hierarchical momentum.**

Also report: what fraction of parent moves are WITH vs AGAINST vs EXTENDED? If 80% are WITH, the classification is unbalanced and the AGAINST sample may be too small.

---

## QUERY 6: Prior Swing Completion History

**Question:** Does the recent success/failure rate of parent-scale swings predict the next pullback's completion?

For each parent move that experiences a child pullback:
1. Count how many of the previous 5 parent-scale swings completed (reached their threshold)
2. Bucket into: 0-1 completed (recent failures), 2-3 completed (mixed), 4-5 completed (recent completions)

Report completion rate:

| Prior Completions (last 5) | Sample Count | Completion Rate |
|---------------------------|-------------|----------------|
| 0-1 (recent failures) | ? | ? |
| 2-3 (mixed) | ? | ? |
| 4-5 (recent completions) | ? | ? |

📌 **This measures "structural health" at the parent scale. If the last 5 swings all completed, the market is rotating cleanly at this scale. If only 1 of 5 completed, the structure at this scale is breaking down — possibly because the market has shifted to a different dominant scale. This is a fractal regime indicator, distinct from ATR or persistence.**

⚠️ **Also report: is prior completion history correlated with directional persistence from the context tagger? If so, they measure the same underlying regime. If not, they capture different dimensions of market state.**

---

## QUERY 7: Swing Sequence Within Day

**Question:** Does the ordinal position of the parent swing within the trading day affect completion?

For each parent move, record which parent-scale swing of the day it is (1st, 2nd, 3rd, etc. counted from session open).

Report completion rate by sequence:

| Day Swing # | Sample Count | Completion Rate |
|------------|-------------|----------------|
| 1st | ? | ? |
| 2nd | ? | ? |
| 3rd | ? | ? |
| 4th | ? | ? |
| 5th+ | ? | ? |

📌 **The fractal waste data tells us roughly how many child moves fit within a parent. There may be a natural "swing budget" per session — early swings complete at higher rates because there's more session time for the structure to play out. Later swings get truncated by approaching session end. If the 1st swing completes at 90% and the 5th+ at 60%, session position is a structural timing dimension.**

---

## COMBINED FACTOR ANALYSIS

After running all 7 queries individually, test the top 2-3 factors together:

⚠️ **Only run combinations for factors with >10pp spread between best and worst bucket. If fewer than 2 qualify, skip this section.**

Cross-tabulate the two strongest factors into a 2×2 grid (above/below median). Report completion rate in each cell:

| | Factor B: Favorable | Factor B: Unfavorable |
|---|---|---|
| **Factor A: Favorable** | ?% (best) | ?% |
| **Factor A: Unfavorable** | ?% | ?% (worst) |

📌 **If the combined spread is wider than either factor alone, the factors compound — both describe independent dimensions of fractal quality. If the combined spread equals the stronger factor alone, one is redundant. Record the finding either way — application decisions happen after P2a, not here.**

If 3 factors qualify, also run the 2×2 for each pair.

---

## OUTPUT

Save to: `C:\Projects\pipeline\stages\01-data\analysis\fractal_discovery\structural_factors\`

⚠️ **This lives in fractal_discovery, not in the strategy backtest directory. These are market properties, not strategy parameters. The boundary is clear: if a factor shows a STRONG gradient, it becomes a candidate hypothesis for a FUTURE strategy iteration — tested on P2a alongside the existing six facts. It does NOT get added to the current strategy before P2a validation.**

```
structural_factors/
├── volume_analysis.csv           # Query 1
├── speed_analysis.csv            # Query 2
├── timeofday_analysis.csv        # Query 3
├── barrange_analysis.csv         # Query 4
├── multiscale_alignment.csv      # Query 5
├── prior_completion.csv          # Query 6
├── swing_sequence.csv            # Query 7
├── combined_factors.csv          # Combined (if applicable)
└── structural_factors_summary.md # Verdicts per factor
```

### Summary Format

For each factor, report a verdict:

- **STRONG** (>15pp spread): significant structural property. Record as candidate Fact. Verify persistence on P2a data in the quarterly fractal monitor.
- **MODERATE** (10-15pp spread): measurable but marginal. Record for reference. May compound with other factors.
- **WEAK** (<10pp spread): the fractal structure does not express through this dimension. Not useful.
- **REDUNDANT**: correlated with another factor, no independent information.

📌 **Even STRONG findings are recorded, not acted on. The current strategy goes to P2a without incorporating these factors. If a factor is STRONG AND persists on P2a data, it becomes a candidate for the next iteration after P2b validation.**

---

## SELF-CHECK BEFORE FINISHING

- [ ] Used existing child-walk decomposition (same method as fractal analysis)
- [ ] RTH only, P1 data only
- [ ] Ran at parent thresholds 25pt and 40pt
- [ ] Grandparent zig-zag computed at 62.5pt and 100pt
- [ ] Query 1: volume ratio computed and quartiled, cross-tabulated with depth
- [ ] Query 2: speed computed (points/bar for initial leg), quartiled
- [ ] Query 3: time-of-day bucketed in 30-min windows for first pullback
- [ ] Query 4: bar range ratio computed and quartiled, correlation with speed reported
- [ ] Query 5: multi-scale alignment (WITH/AGAINST/EXTENDED) computed and reported
- [ ] Query 5: sample balance across alignment categories reported
- [ ] Query 6: prior 5-swing completion history computed, correlation with persistence checked
- [ ] Query 7: swing sequence within day computed
- [ ] Combined analysis run if 2+ factors show >10pp gradient
- [ ] All results saved to `fractal_discovery/structural_factors/` (NOT strategy directory)
- [ ] Summary with verdicts per factor produced
- [ ] No strategy parameters referenced in the analysis
- [ ] Results framed as structural findings, not strategy filter recommendations
