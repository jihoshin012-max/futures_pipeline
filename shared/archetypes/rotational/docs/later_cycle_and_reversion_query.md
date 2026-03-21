# Two Quick Queries: Later-Cycle PnL + Post-Completion Reversion

## QUERY 1: Later-Cycle-Only PnL (Existing Data)

From the existing frozen-anchor cycle logs, filter and compute later-cycle-only performance.

⚠️ **No new simulation. Use the existing cycle logs and incomplete logs from the P1 frozen-anchor sweep and P2a validation.**

### Steps

1. Load cycle logs for FA_SD40_MA0_RT80 from P1 sweep (`frozen_anchor_sweep/cycle_logs/`)
2. Load cycle log for P2A_VALIDATION from P2a validation (`p2a_validation/cycle_logs/`)
3. Filter both to `cycle_day_seq > 1` (exclude first cycle of each day)
4. Include ALL incomplete cycles — the incomplete cycle is always the last cycle of the day, which is always a later cycle. No proportional splitting needed.

### Report

| Metric | P1 (later only) | P2a (later only) |
|--------|-----------------|------------------|
| Cycle count | ? | ? |
| Success rate | ? | ? |
| Gross PnL | ? | ? |
| Net PnL (after costs) | ? | ? |
| Incomplete PnL | ? | ? |
| Adjusted net (net + incomplete) | ? | ? |
| Edge per cycle (net / count) | ? | ? |
| Max drawdown | ? | ? |

📌 **This answers: if the strategy skipped the first cycle entirely and only traded from the second cycle onward, would P2a have been positive? If later-cycle adjusted net is still negative on P2a, the 57.3% SR doesn't survive costs at SD=40/RT=0.8 and Option A is dead.**

---

## QUERY 2: Post-Completion Reversion Depth (Fractal Data)

Using the existing child-walk decomposition on P1 1-tick RTH data, measure what happens AFTER a parent-scale move completes its threshold.

⚠️ **This runs on the fractal zig-zag data, not the strategy simulator. Use the same child-walk method from the fractal analysis scripts.**

### Definition

A parent-scale completion occurs when the cumulative child-scale displacement from the parent start reaches the parent threshold (e.g., +40pts for a long parent move).

From the COMPLETION POINT (the exact price where the parent threshold was reached), measure:

1. The maximum reversion — how far price moves AGAINST the original parent direction before EITHER:
   - Price returns to the completion point level (reversion fully retraced — the original direction resumed), OR
   - Session ends

📌 **This is the pullback the flipped strategy would try to capture. The completion point is where the strategy would detect "a 40pt move just happened" and enter opposite. The max reversion is how much pullback was available from that entry.**

### Report for Parent=40pt, Child=16pt

| Metric | Value |
|--------|-------|
| Sample count (completions) | ? |
| Median reversion depth (pts) | ? |
| P25 reversion | ? |
| P75 reversion | ? |
| P90 reversion | ? |
| % completions with ≥8pt reversion | ? |
| % with ≥12pt reversion | ? |
| % with ≥16pt reversion | ? |
| % with ≥20pt reversion | ? |
| % with ≥24pt reversion | ? |
| Median time to max reversion (bars) | ? |
| Median time to completion point return (bars) | ? |

⚠️ **Also report: what percentage of completions see price return to the completion point level (full reversion recovery) vs price continuing in the reversion direction past -40pts (new parent move in opposite direction)? This distinguishes "pullback within continuation" from "genuine reversal."**

### Also Run for Parent=25pt, Child=10pt

Same table. This tests whether the reversion pattern is scale-consistent (fractal self-similarity predicts it should be).

### Interpretation Guide

For the flipped strategy to work at Parent=40pt:
- Median reversion needs to be ≥12pts to cover costs (4 ticks entry + 4 ticks exit = 8 ticks = 2pts, plus minimum profit)
- The % with ≥12pt reversion needs to be >65% to overcome the unfavorable risk/reward
- If median reversion is <8pts, the pullback is too shallow to trade profitably

📌 **If the data shows median reversion of 20+ pts with 80%+ of completions seeing ≥12pt reversions, the flipped framing has strong structural backing. If median reversion is 6-8pts, the pullback is real but too small to trade after costs. Either result is valuable — it determines whether to build the flipped simulator or move on.**

---

## OUTPUT

Query 1: Print results inline. No file needed — this is a quick filter of existing data.

Query 2: Save to `C:\Projects\pipeline\stages\01-data\analysis\fractal_discovery\post_completion_reversion\`

```
post_completion_reversion/
├── reversion_40pt.csv
├── reversion_25pt.csv
└── post_completion_summary.md
```

---

## SELF-CHECK

- [ ] Query 1: filtered to cycle_day_seq > 1 (later cycles only)
- [ ] Query 1: included all incomplete cycle PnL (all incompletes are later cycles)
- [ ] Query 1: computed for both P1 and P2a
- [ ] Query 2: measured reversion from completion point (not from parent start)
- [ ] Query 2: stopping condition is return to completion point OR session end
- [ ] Query 2: reported % of completions that fully recover vs continue reversing
- [ ] Query 2: ran at both 40pt and 25pt parent thresholds
- [ ] Query 2: saved to fractal_discovery (not strategy directory)
