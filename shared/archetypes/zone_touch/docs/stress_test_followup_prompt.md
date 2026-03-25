# Stress Test Follow-Up — Advanced MC, Regime, Concentration & Correlation Analysis

**Purpose:** Comprehensive follow-up to `stress_test_v32.md` covering: (1) two 
additional MC techniques (reshuffling, HMM) to address serial correlation, 
(2) market regime sensitivity, (3) liquidity/news event risk, (4) concentration 
risk, and (5) M1/M2 loss correlation. All findings feed into an updated 
capital and deployment recommendation.

**Branch:** `main`
**Pipeline version:** 3.2 (frozen)
**Date:** 2026-03-24
**Prerequisite:** `stress_test_v32.py` and `stress_test_trades_v32.csv` (718 
trades with per-trade PnL from the frozen configuration)

⚠️ EVERYTHING IS FROZEN. No model or parameter changes. This is additional 
risk analysis on the same trade population.

---

## Input Data

Use the 718-trade sequence from `stress_test_trades_v32.csv` (P1+P2 combined, 
time-ordered). Each trade has: mode, datetime, contracts, pnl_total, exit_type, 
zone_width, win.

Key baseline numbers from the bootstrap analysis:
| Metric | Value |
|--------|-------|
| Historical max DD | 1,129t |
| Bootstrap 95th DD | 1,501t |
| Bootstrap 99th DD | 1,797t |
| Bootstrap worst | 3,076t |
| Lag-3 autocorrelation | 0.082 (significant) |
| Total profit | 114,071t |

📌 REMINDER: The bootstrap found lag-3 autocorrelation (marginally significant). 
The HMM in Part 2 directly addresses whether this autocorrelation reflects 
persistent regime clustering that the bootstrap understates.

---

## Part 1: Reshuffling (Permutation) Monte Carlo

### 1a: Method

Randomly shuffle the 718 trades into a new order (without replacement — every 
trade appears exactly once). Compute the equity curve and max drawdown for each 
shuffled sequence.

- **Iterations:** 10,000 shuffled paths
- **Trade count:** Exactly 718 per path (same trades, different order)
- **Preserve:** Each trade's pnl_total unchanged — only the sequence changes

⚠️ KEY DIFFERENCE FROM BOOTSTRAP: Bootstrap samples with replacement (some 
trades appear multiple times, others not at all). Reshuffling uses every trade 
exactly once. The total profit is IDENTICAL across all reshuffled paths — only 
the max drawdown and equity path shape change.

This answers: **was the historical sequence lucky?** If the historical DD 
(1,129t) is at the 20th percentile of reshuffled DDs, the actual trade 
ordering was favorable — losses happened to occur when the account was already 
profitable. If it's at the 80th percentile, the actual ordering was unlucky.

### 1b: Results

**Reshuffled drawdown distribution:**

| Percentile | Max DD (ticks) | vs Bootstrap |
|-----------|---------------|-------------|
| 50th | ? | 1,004t (bootstrap) |
| 75th | ? | 1,171t |
| 90th | ? | 1,362t |
| 95th | ? | 1,501t |
| 99th | ? | 1,797t |
| Worst | ? | 3,076t |

📌 REMINDER: Total profit is constant across all reshuffled paths (114,071t). 
Only the drawdown profile varies. If reshuffled 95th DD is materially different 
from bootstrap 95th DD (1,501t), report the difference and explain why.

**Historical sequence position:**

| Metric | Value |
|--------|-------|
| Historical max DD | 1,129t |
| Percentile in reshuffled distribution | ? |
| Interpretation | Lucky / Average / Unlucky |

⚠️ If historical DD is below the 30th percentile of reshuffled DDs, the 
actual sequence was favorable. The capital recommendation should use the 
reshuffled 95th percentile instead of the bootstrap 95th.

### 1c: Longest drawdown duration

The bootstrap doesn't capture duration risk (it resamples without time 
structure). Reshuffling preserves trade count but randomizes order.

| Percentile | Longest DD (trades) | Longest DD (est. days) |
|-----------|--------------------|-----------------------|
| 50th | ? | ? |
| 75th | ? | ? |
| 90th | ? | ? |
| 95th | ? | ? |

⚠️ If 95th percentile longest DD exceeds 30 trades (~5 days at 6.24 trades/day), 
this is important for psychology — you need to be prepared for a week-long 
drawdown even if the dollar amount is manageable.

---

## Part 2: HMM (Hidden Markov Model) Monte Carlo

### 2a: Fit the HMM

Fit a Gaussian HMM with 2-3 hidden states to the trade PnL sequence. Use the 
`hmmlearn` library (GaussianHMM).

⚠️ INSTALL: `pip install hmmlearn --break-system-packages`

**Test 2 and 3 states. Pick the model with the better BIC/AIC:**

| States | Log-likelihood | AIC | BIC | Selected? |
|--------|---------------|-----|-----|-----------|
| 2 | ? | ? | ? | ? |
| 3 | ? | ? | ? | ? |

### 2b: Characterize the regimes

For each hidden state, report:

| State | Mean PnL | Std PnL | WR | % of Trades | Interpretation |
|-------|---------|--------|----|----|-------------|
| 0 | ? | ? | ? | ? | ? (e.g., "strong edge") |
| 1 | ? | ? | ? | ? | ? (e.g., "choppy/weak") |
| 2 (if 3-state) | ? | ? | ? | ? | ? (e.g., "adverse regime") |

**Transition matrix:**

| From \ To | State 0 | State 1 | State 2 |
|-----------|---------|---------|---------|
| State 0 | ? | ? | ? |
| State 1 | ? | ? | ? |
| State 2 | ? | ? | ? |

⚠️ KEY QUESTION: Is there a persistent adverse state? If the transition matrix 
shows high self-transition probability for a losing state (e.g., State 1 stays 
in State 1 with >70% probability), losses will cluster. The bootstrap cannot 
capture this — an HMM simulation can.

📌 REMINDER: With only 718 trades and 2-3 states, the HMM fit may be noisy. 
If the states are not clearly separated (overlapping mean±std), the HMM adds 
no value over the bootstrap. Report whether the states are meaningfully distinct.

### 2c: Regime-aware simulation

Using the fitted HMM, generate synthetic trade sequences:

1. Start in a random state (weighted by stationary distribution)
2. At each step: transition to next state per transition matrix, then sample 
   PnL from that state's Gaussian distribution
3. Generate 10,000 paths of 718 trades each

⚠️ This differs from the bootstrap in a crucial way: losses cluster in adverse 
regimes because the HMM preserves state persistence. A run of bad trades in 
State 1 stays in State 1 (high self-transition), producing realistic drawdown 
clustering.

### 2d: HMM Monte Carlo results

**HMM drawdown distribution:**

| Percentile | HMM DD (ticks) | Bootstrap DD | Reshuffled DD | Difference |
|-----------|---------------|-------------|--------------|-----------|
| 50th | ? | 1,004t | ? | ? |
| 75th | ? | 1,171t | ? | ? |
| 90th | ? | 1,362t | ? | ? |
| 95th | ? | 1,501t | ? | ? |
| 99th | ? | 1,797t | ? | ? |
| Worst | ? | 3,076t | ? | ? |

⚠️ If HMM 95th DD is materially higher than bootstrap 95th DD (1,501t), 
the serial correlation matters and the capital requirement should be increased. 
"Materially higher" = >20% (>1,800t).

**HMM ruin probability:**

| DD Threshold | HMM % | Bootstrap % | Difference |
|-------------|-------|------------|-----------|
| 1,000t | ? | 51.3% | ? |
| 2,000t | ? | 0.4% | ? |
| 3,000t | ? | 0.0% | ? |
| 5,000t | ? | 0.0% | ? |

📌 REMINDER: If HMM shows 2,000t ruin at >2% (vs bootstrap 0.4%), the 
capital recommendation needs to increase from $15K to accommodate the 
regime-clustered tail risk.

---

## Part 3: Synthesis — Updated Capital Recommendation

### 3a: Compare all three methods

| Method | 95th DD | 99th DD | Key Assumption |
|--------|---------|---------|---------------|
| Bootstrap | 1,501t | 1,797t | Trades independent |
| Reshuffled | ? | ? | Same trades, random order |
| HMM | ? | ? | Regime-clustered losses |

⚠️ USE THE WORST (highest) 95th percentile DD across all three methods for 
the final capital recommendation.

### 3b: Updated capital requirements

| Contract | Worst 95th DD | 2× Buffer | Updated Min Capital |
|----------|-------------|-----------|-------------------|
| MNQ ($5/t) | ? | ? | ? |
| NQ ($20/t) | ? | ? | ? |

Previous recommendation: $15,011 MNQ / $60,044 NQ (from bootstrap only).
Updated recommendation: ? (incorporating reshuffling and HMM tail risk).

### 3c: Final deployment notes

Incorporate ALL findings from Parts 1-7 into a unified assessment:

**From MC methods (Parts 1-2):**
- Was the historical sequence lucky, average, or unlucky? (from reshuffling)
- Are there persistent adverse regimes? (from HMM)
- Does the capital recommendation change? By how much?

**From structural risk analysis (Parts 4-7):**
- Are there market regimes where PF drops below 2.0? If so, recommend 
  monitoring thresholds (e.g., pause/reduce size when 20-day return exceeds ±5%)
- Do news events degrade performance? If so, recommend blackout windows
- Does same-zone clustering produce correlated losses? If so, recommend zone 
  cooldown rules
- Do M1 and M2 losses correlate by day? If the worst single-day loss exceeds 
  the MC 95th DD, the capital recommendation must increase further

⚠️ The final capital recommendation should reflect the WORST finding across 
ALL seven parts, not just the MC comparison. A regime where PF drops to 1.5 or 
a correlated worst-day loss of 2,000t matters more than the MC 95th percentile.

---

## Part 4: Market Regime Correlation

⚠️ The strategy trades zone bounces. In strong trends, zones break more often 
than bounce. This test measures whether the edge degrades in specific market 
conditions.

### 4a: Compute market context for each trade

For each of the 718 trades, compute at the time of entry:

| Column | Definition |
|--------|-----------|
| nq_20d_return | NQ 20-day trailing return (% change) |
| nq_5d_return | NQ 5-day trailing return |
| nq_20d_atr | 20-day ATR (absolute volatility) |
| vix_proxy | If VIX data available; otherwise use NQ realized vol as proxy |

⚠️ If VIX data is not in the pipeline, use the 20-day ATR as a volatility 
proxy. The question is whether high-volatility or strong-trend environments 
degrade PF.

### 4b: Performance by market regime

Bin trades into regimes and report PF per bin:

**By trend strength (20-day return):**

| 20d Return Bin | Trades | PF | WR% | Interpretation |
|---------------|--------|----|----|----------------|
| < -5% (strong down) | ? | ? | ? | Bear trend |
| -5% to -1% (mild down) | ? | ? | ? | Mild bearish |
| -1% to +1% (range) | ? | ? | ? | Rangebound |
| +1% to +5% (mild up) | ? | ? | ? | Mild bullish |
| > +5% (strong up) | ? | ? | ? | Bull trend |

**By volatility (20-day ATR):**

| ATR Bin | Trades | PF | WR% | Interpretation |
|---------|--------|----|----|----------------|
| Bottom quartile (low vol) | ? | ? | ? | Quiet market |
| 2nd quartile | ? | ? | ? | Normal |
| 3rd quartile | ? | ? | ? | Elevated vol |
| Top quartile (high vol) | ? | ? | ? | High vol |

⚠️ KEY QUESTION: Does PF drop below 2.0 in any regime? If strong trends crush 
PF (zones break instead of bounce), the monitoring threshold should include a 
trend filter: reduce size or pause when 20-day return exceeds ±5%.

📌 REMINDER: With 718 trades split into 5 bins, each bin has ~140 trades. 
That's enough for directional signal but not precise PF estimates. Look for 
large differences (PF 2.0 in one bin vs 6.0 in another), not small ones.

---

## Part 5: Liquidity / News Event Risk

⚠️ FOMC announcements, NFP releases, CPI prints, and other major economic 
events cause spread widening and slippage spikes. Trades near these events may 
have worse fills than the backtested bar Open suggests.

### 5a: Economic calendar overlay

Identify major economic events during the P1+P2 data period:

| Event Type | Dates in Data | Typical Time |
|-----------|--------------|-------------|
| FOMC decisions | ? | 14:00 ET |
| NFP releases | ? | 08:30 ET |
| CPI releases | ? | 08:30 ET |
| GDP releases | ? | 08:30 ET |

⚠️ If the economic calendar is not available in the pipeline data, use a 
hardcoded list of known dates for Sep 2025 - Mar 2026. Alternatively, flag 
trades that occur within 30 minutes of 08:30 ET or 14:00 ET as "news-adjacent."

### 5b: Performance near events

| Condition | Trades | PF | WR% |
|-----------|--------|----|----|
| All trades (baseline) | 718 | ? | 81.5% |
| Within 30 min of 08:30 or 14:00 | ? | ? | ? |
| NOT within 30 min of events | ? | ? | ? |
| FOMC day trades | ? | ? | ? |
| Non-FOMC day trades | ? | ? | ? |

⚠️ If event-adjacent trades have meaningfully worse PF, consider adding a 
news blackout window to the C++ autotrader (configurable: skip signals within 
N minutes of scheduled releases).

---

## Part 6: Concentration Risk

⚠️ With 6.24 trades/day and one position at a time, multiple trades can fire 
on the same zone within the same day. If that zone's level is mispriced (e.g., 
a structural break), you take repeated losses at the same price level.

### 6a: Same-zone clustering

For each trade, identify the zone it trades. If the trade data includes a 
zone_id or zone_index from the ZTE, use that directly. If not, define "same 
zone" as: same TF AND zone edge price within 10 ticks AND same zone type 
(demand/supply). Count how many times the SAME zone is traded within a rolling 
24-hour window.

| Trades on Same Zone (24h) | Occurrences | % of Days | Mean PnL per Cluster |
|--------------------------|-------------|-----------|---------------------|
| 1 (unique zone) | ? | ? | ? |
| 2 (same zone hit twice) | ? | ? | ? |
| 3+ (same zone 3+ times) | ? | ? | ? |

### 6b: Consecutive same-zone losses

Find instances where the SAME zone produced 2+ consecutive losses:

| Count | Mean Loss per Event | Worst Event |
|-------|--------------------|-----------| 
| ? | ? | ? |

⚠️ If same-zone consecutive losses occur, this motivates a "zone cooldown" 
rule: after a loss on zone X, skip the next touch on zone X within N bars. 
This is a C++ implementation consideration, not a model change.

📌 REMINDER: The seq ≤ 2 gate on Mode 2 already limits sequential touches on 
the same zone. But seq counts across the full history — a zone can have seq=1 
on two separate days and both pass the filter. Intraday clustering is different 
from the seq gate.

---

## Part 7: M1/M2 Loss Correlation

⚠️ The Monte Carlo bootstrap treats M1 and M2 trades independently. If both 
modes lose on the same days, the combined DD is worse than independent DDs 
suggest.

### 7a: Daily PnL correlation

Compute daily PnL for M1-only and M2-only trades. Report the correlation:

| Metric | Value |
|--------|-------|
| Daily M1 PnL / M2 PnL correlation | ? |
| Days where BOTH M1 and M2 had negative PnL | ? |
| Days where M1 was negative | ? |
| Days where M2 was negative | ? |

⚠️ If the correlation is > 0.3, losses cluster by day. The bootstrap 
understates combined DD because it scrambles the day-level correlation.

### 7b: Worst-day analysis

| Rank | Date | M1 PnL | M2 PnL | Combined | Trades |
|------|------|--------|--------|----------|--------|
| 1 (worst) | ? | ? | ? | ? | ? |
| 2 | ? | ? | ? | ? | ? |
| 3 | ? | ? | ? | ? | ? |
| 4 | ? | ? | ? | ? | ? |
| 5 | ? | ? | ? | ? | ? |

### 7c: Conditional drawdown

What is the max DD if we restrict to days where both M1 and M2 lost?

| Metric | Independent (baseline) | Correlated Days Only |
|--------|----------------------|---------------------|
| Max combined daily loss | ? | ? |
| Frequency (days) | ? | ? |

⚠️ If the worst combined daily loss exceeds the 95th MC DD (1,501t), the 
capital recommendation needs to increase. This would mean a single bad day 
can exceed what the MC says is a rare multi-trade drawdown.

📌 REMINDER: M1 has only ~4 losses in the entire dataset. The correlation 
analysis has very few data points on the M1 loss side. Report the sample 
size limitation — if M1 has 0 losses on M2 loss days, the correlation is 
undefined, not zero.

---

## Output Files

Save to: `c:\Projects\pipeline\shared\archetypes\zone_touch\output\`
- `stress_test_followup_v32.md` — this report
- Update `stress_test_v32.md` Section 7 if capital recommendation changes

Commit to `main` with message:
"Add reshuffling, HMM, regime, liquidity, concentration, and correlation stress tests"

---

## Self-Check Before Submitting

- [ ] Reshuffling uses exactly 718 trades per path (no replacement)
- [ ] Total profit is constant across all reshuffled paths (verified)
- [ ] Historical DD percentile in reshuffled distribution reported
- [ ] Longest DD duration distribution reported
- [ ] HMM fitted with both 2 and 3 states, best selected by AIC/BIC
- [ ] HMM states are meaningfully distinct (non-overlapping distributions)
- [ ] HMM simulation preserves transition matrix (not just sampling from states)
- [ ] All three DD distributions compared side by side
- [ ] Capital recommendation uses WORST 95th DD across all methods
- [ ] Final deployment notes incorporate findings from ALL 7 parts (not just MC)
- [ ] If HMM adds no value (states not distinct), reported as such
- [ ] Market regime PF reported by trend strength AND volatility bins
- [ ] News-adjacent trades identified and PF compared to non-event trades
- [ ] Same-zone clustering quantified with consecutive loss count
- [ ] Same-zone identification uses zone_id or 10t tolerance (not exact edge price)
- [ ] M1/M2 daily PnL correlation computed
- [ ] Worst-day analysis shows top 5 combined loss days
- [ ] Sample size limitations noted (especially M1 loss count)
