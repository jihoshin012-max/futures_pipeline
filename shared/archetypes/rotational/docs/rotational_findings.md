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

## Phase 5 Results: Refinement (2026-03-25)

### Finding 7: Time Gate Significantly Improves Performance

Tested on best config (SD=25, HS=125, MCS=2). Results from P1 cycle data:

| Scenario | Cycles | E[R] | Sigma | PropScore | P_pass Eval |
|----------|--------|------|-------|-----------|-------------|
| Full RTH (9:30-15:50) | 3,165 | $33.19 | $768.64 | 0.035 | 46.8% |
| Excl 09:30-10:00 | 2,600 | $44.56 | $761.27 | 0.048 | 49.4% |
| Excl 12:30-13:00 | 2,966 | $39.35 | $764.76 | 0.042 | 48.2% |
| Excl both | 2,401 | $53.11 | $755.67 | 0.057 | 51.3% |
| Excl 09:30 + 13:30-14:00 | 2,444 | $55.90 | $754.39 | 0.061 | 51.9% |
| **Excl all 3 bad blocks** | **2,245** | **$66.06** | **$747.57** | **0.072** | **54.3%** |

**Observation:** Excluding the three worst blocks (09:30-10:00, 12:30-13:00, 13:30-14:00) doubles E[R] from $33 to $66 and PropScore from 0.035 to 0.072. Sigma actually decreases (fewer large losses), so the improvement is real, not just from dropping cycles. P_pass eval goes from 46.8% to 54.3%.

**The three bad blocks contribute 920 cycles (29% of total) but produce net losses.** Removing them improves every metric simultaneously — more E[R], less sigma, higher PropScore, higher P_pass.

[SUGGESTION] A time gate excluding these three blocks is the highest-impact single change available. Needs P2 validation to confirm the pattern isn't P1-specific.

### Finding 8: Optimal Hard Stop is 125-130 Ticks for SD=25

Fine-grained HS sweep (100-160 ticks, 5-tick increments) for SD=25 MCS=2:

| HS | Cycles | Win Rate | E[R] | Sigma | PropScore |
|----|--------|----------|------|-------|-----------|
| 100 | 3,727 | 50.5% | $0.63 | $499 | 0.001 |
| 105 | 3,263 | 68.0% | $3.58 | $719 | 0.004 |
| 110 | 3,226 | 69.0% | $1.94 | $737 | 0.002 |
| 115 | 3,175 | 70.3% | $9.19 | $750 | 0.010 |
| 120 | 3,156 | 71.9% | $22.73 | $759 | 0.025 |
| **125** | **3,165** | **73.4%** | **$33.19** | **$769** | **0.035** |
| **130** | **3,131** | **74.1%** | **$34.14** | **$783** | **0.036** |
| 135 | 3,068 | 74.0% | $20.32 | $804 | 0.021 |
| 140 | 3,018 | 74.5% | $17.95 | $820 | 0.018 |
| 150 | 2,940 | 75.1% | $7.95 | $853 | 0.008 |
| 155 | 2,867 | 75.2% | -$2.00 | $873 | -0.002 |

**Observation:** Sharp peak at HS=125-130. Below 120, PropScore drops steeply (the add has too little room to recover). Above 135, sigma grows faster than E[R] (wider stop = bigger losses on failures). HS=100 (the theoretical minimum for the add to fire) produces near-zero E[R] — the add fires but has essentially no recovery room.

HS=125 and HS=130 are within noise of each other. [OPINION] Either is a valid choice. HS=125 is slightly more conservative (lower max loss: $1,250 vs $1,300).

### Finding 9: Dominant StepDist Shifts by Time Block

Tested all 6 SD values (best HS per SD, depth 1) across 30-min blocks. SD=25 is not the best in every block — it wins overall by being consistently decent, not dominant anywhere.

**Winning SD per block (P1 data):**

| Time Block | Best SD | E[R] | 2nd SD | E[R] |
|-----------|---------|------|--------|------|
| 09:30-10:00 | SD=10 | -$7.54 | SD=25 | -$19.13 |
| 10:00-10:30 | SD=50 | $110.91 | SD=30 | $88.75 |
| 10:30-11:00 | SD=30 | $146.93 | SD=50 | $135.60 |
| 11:00-11:30 | SD=25 | $30.45 | SD=10 | $4.68 |
| 11:30-12:00 | SD=50 | $338.66 | SD=30 | $75.49 |
| 12:00-12:30 | SD=25 | $73.08 | SD=30 | $68.69 |
| 12:30-13:00 | SD=50 | $31.56 | SD=10 | -$5.71 |
| 13:00-13:30 | SD=30 | $330.18 | SD=25 | $227.15 |
| 13:30-14:00 | SD=10 | $0.68 | SD=20 | -$0.86 |
| 14:00-14:30 | SD=50 | $286.59 | SD=30 | $156.42 |
| 14:30-15:00 | SD=30 | $343.62 | SD=25 | $155.24 |
| 15:00-15:30 | SD=20 | $122.67 | SD=15 | $72.80 |
| 15:30-15:50 | SD=50 | $324.74 | SD=30 | $20.73 |

**Observations:**
- SD=30 and SD=50 dominate the highest-E[R] blocks (10:30, 11:30, 13:00, 14:00, 14:30)
- SD=25 dominates the moderate blocks (11:00, 12:00)
- SD=10 and SD=20 dominate the quietest blocks (13:30, 15:00)
- 09:30-10:00 is negative for ALL SD values — universally bad regardless of grid scale
- [OPINION] The rotation scale shifts throughout the day. SD=25 works as a one-size-fits-all because it avoids the worst mismatches, but a dynamic SD selection could capture significantly more edge.

**Data saved:** `analysis_sd_by_timeblock.csv` — full metrics per SD × time block for P2 comparison.

---

## Open Questions for Next Analysis

1. **Monte Carlo under LucidFlex rules:** Run the probability framework on SD=25 HS=125 with time gate, using explicit trailing drawdown, scaling tiers, and consistency rules. The P_pass formula gives ~54% with time gate — Monte Carlo may differ due to trailing MLL.

2. **Rotation scale detection:** Can we identify in real-time whether the current market is rotating at the SD=25 scale? (See Future Exploration section in audit trail — three approach options + MA-based trend filter documented.)

3. **P2 holdout validation:** Run on P2 data (frozen params, one shot) per pipeline rules. Check whether time block pattern, regime distribution, and SD-by-block dominance hold.

4. **Time gate + HS combination:** The time gate and HS analyses were done independently. The optimal HS might shift when the bad blocks are excluded (fewer trend cycles in the data → different HS balance point).

5. **Dynamic SD selection:** Finding 9 shows different SDs dominate different blocks. [SPECULATION] A two-SD approach (e.g., SD=25 for midday, SD=30-50 for morning/afternoon) could capture more edge if the pattern holds in P2.
