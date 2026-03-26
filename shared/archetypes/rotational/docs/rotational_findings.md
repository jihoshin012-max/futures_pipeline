# Rotational Strategy — Findings Report

**Started:** 2026-03-25
**Status:** Active — updated as analysis progresses

---

## Sweep v2 Baseline Results (2026-03-25)

**Data:** NQ 1-tick P1 (Sept 21 – Dec 17, 2025), RTH only (9:30–15:50 ET)
**Grid:** 144 configs — 6 SD × 4 depths × 6 HS per depth
**Commission:** $3.50/RT mini
**Total cycles analyzed:** 885,250

### Finding 1: Martingale Adds Improve Performance

Pure rotation (depth 0) vs martingale (depth 1+):

| Depth | Configs with positive E[R] | Best PropScore | Best E[R] |
|-------|---------------------------|---------------|-----------|
| 0 (pure rotation) | 11 / 36 (31%) | 0.013 | $5.52 |
| 1 (1 add, MCS=2) | 24 / 36 (67%) | 0.035 | $49.63 |
| 2 (2 adds, MCS=4) | 21 / 36 (58%) | 0.020 | $37.67 |
| 3 (3 adds, MCS=8) | 15 / 36 (42%) | 0.014 | $75.68 |

**Observation:** In this P1 dataset, depth 1 produced the highest PropScore. Adding the first martingale contract increased the percentage of profitable configs from 31% to 67% and the best PropScore from 0.013 to 0.035. Deeper martingale (depth 2-3) showed higher raw E[R] but sigma grew proportionally faster, resulting in lower PropScore.

### Finding 2: Best Overall Config

**SD=25, HS=125, MCS=2 (depth 1)** — PropScore 0.035

| Metric | Value |
|--------|-------|
| Cycles | 3,165 |
| Win rate | 73.4% |
| Net E[R] | $33.19 / cycle |
| Sigma | $768.64 |
| PropScore | 0.0353 |
| P_pass eval | 46.8% |
| Max loss per cycle | $1,250 |
| MLL viable (eval) | Yes ($1,250 < $2,000) |

### Finding 3: Regime Classification — Where Profit and Loss Come From

For the best config (SD=25, HS=125, depth 1):

| Regime | % of Cycles | Avg Net PnL | Total Net PnL | What it means |
|--------|------------|-------------|---------------|---------------|
| Clean rotation | 50.1% | +$498 | +$789,554 | Reversal at depth 0 — no add needed |
| Martingale save | 22.4% | +$496 | +$351,965 | Reversal at depth 1 — add rescued the cycle |
| Trend overcame | 25.8% | -$1,259 | -$1,030,191 | Hard stop after add — trend beat the martingale |
| EOD incomplete | 1.6% | -$123 | -$6,294 | Forced flatten at session close |

**Observation:** In this dataset, ~72% of cycles were profitable (clean rotation + martingale save). The ~26% trend-overcame cycles accounted for -$1,030,191 in losses vs +$1,141,519 in gains from the profitable cycles. [SUGGESTION] Reducing trend exposure appears to be the highest-leverage improvement path based on this data.

### Finding 4: 30-Minute Block Analysis — Time Matters

Consistent patterns across all configs:

| Time Block | Pattern | Observation |
|-----------|---------|-------------|
| **09:30-10:00** | **Worst block** | Negative E[R] in every config tested. [OPINION] Opening drive appears too directional for rotation. |
| 10:00-10:30 | Mixed | Transition period. Some configs positive, some negative. |
| 10:30-11:00 | Mixed | Similar to 10:00-10:30. |
| **11:00-11:30** | Positive | Rotation starts to establish. |
| **11:30-12:00** | Positive | Good rotation window. |
| 12:00-12:30 | Mixed | Can go either way. |
| **12:30-13:00** | **Often negative** | [SPECULATION] Possibly pre-lunch positioning creating directional moves. |
| **13:00-13:30** | **Best block** | Highest E[R] and win rate across all configs tested. [OPINION] Midday lower volume may favor rotation. |
| 13:30-14:00 | Mixed to negative | Afternoon positioning begins. |
| **14:00-14:30** | Positive | Often strong. |
| **14:30-15:00** | Positive | Good rotation window. |
| 15:00-15:30 | Positive | Still decent but fewer cycles. |
| 15:30-15:50 | Degraded | EOD flattens cut cycles short, lower win rate. |

**For the best config (SD=25, HS=125):**

| Block | Cycles | Win Rate | Net E[R] | Total PnL |
|-------|--------|----------|----------|-----------|
| 09:30-10:00 | 565 | 70.6% | -$19.13 | -$10,810 |
| 13:00-13:30 | 189 | 84.7% | +$227.15 | +$42,931 |
| 14:30-15:00 | 190 | 80.0% | +$155.24 | +$29,495 |

**Observation:** In this dataset, excluding 09:30-10:00 would have eliminated $10,810 in losses for the best config. [SUGGESTION] A time gate starting at 10:00 may be the simplest risk mitigation — needs validation on out-of-sample data before committing.

### Finding 5: Hard Stop Must Accommodate Martingale Depth

From the v1 sweep and v2 redesign, we learned:

- HS < SD_ticks → no adds fire, pure rotation regardless of MCS setting
- HS at 1.0× SD_ticks (the minimum for adds) → add fires but almost no room for recovery
- HS at 1.25× SD_ticks → the sweet spot for depth 1 (SD=25 HS=125 = 1.25×)
- HS at 1.5×+ → progressively more room but larger losses when stops fire

The HS is not an independent parameter — it's a function of SD and the intended depth. Setting it below the depth minimum turns off the martingale entirely.

### Finding 6: Depth 3 (MCS=8) is Informational Only

No depth 3 config is eval-viable (max loss always exceeds $2,000 MLL). The data shows:

- Very high win rates (90-97%) — the martingale almost always recovers
- But when it doesn't, losses are catastrophic ($28K-$42K per failure)
- The 2-3% failure rate at these loss sizes means a single bad cycle wipes weeks of gains

The observed win rates (90-97%) are near the mathematical breakeven threshold (87-94%), leaving thin margin. [OPINION] This does not appear to provide a reliable edge at depth 3 given the catastrophic tail risk.

---

## Open Questions for Next Analysis

1. **Time gate impact:** Quantify the improvement from excluding 09:30-10:00 (and possibly 12:30-13:00) on the top configs. Simple re-filter on saved cycle data.

2. **Targeted HS sweep around SD=25:** The best config is HS=125. Test HS=110, 115, 120, 125, 130, 135, 140 in 5-tick increments to find the precise optimum.

3. **Rotation scale detection:** Can we identify in real-time whether the current market is rotating at the SD=25 scale? (See Future Exploration section in audit trail — three approach options documented.)

4. **Monte Carlo under LucidFlex rules:** Run the probability framework on the top configs with explicit trailing drawdown, scaling tiers, and consistency rules. The P_pass formula gives ~47% for the best config — Monte Carlo may differ due to trailing MLL.

5. **P2 holdout validation:** Once a final config is selected, run on P2 data (frozen params, one shot) per pipeline rules.
