# Stress Test, Monte Carlo & Kelly Sizing — v3.2 Zone Touch Strategy

**Purpose:** Stress test the frozen v3.2 configuration to determine position sizing, 
capital requirements, and deployment viability. This produces the final risk 
parameters before C++ implementation and paper trading.

**Branch:** `main`
**Pipeline version:** 3.2 (model and execution parameters frozen)
**Date:** 2026-03-24

⚠️ EVERYTHING IS FROZEN. This analysis does not change the model, trade selection, 
entry, exit, or position sizing rules. It tests the frozen configuration under 
adverse conditions to determine whether the strategy is deployable and at what 
capital level.

---

## Frozen Configuration

**Mode 1 (A-Eq ModeA):**
| Parameter | Value |
|-----------|-------|
| Entry | Bar Open after touch (zone edge) |
| Stop | 190t fixed from entry |
| Target | 1+2 partial: 1ct@60t + 2ct@120t, BE on runner after T1 |
| Time cap | 120 bars |
| Contracts | 3 |
| P1 trades / PF@3t | 107 / 8.50 |
| P2 trades / PF@4t | 96 / 6.26 (8.25 with partials) |
| WR (P2) | 94.8% |

**Mode 2 (B-ZScore RTH):**
| Parameter | Value |
|-----------|-------|
| Entry | Bar Open after touch (zone edge) |
| Stop | max(1.3×ZW, 100t) from entry |
| Target | 1.0×ZW |
| Time cap | 80 bars |
| Contracts | 3ct if ZW<150, 2ct if 150-250, 1ct if 250+ |
| P1 trades / PF@3t | 239 / 4.61 |
| P2 trades / PF@4t | 309 / 4.10 |
| WR (P1) | 74.5% |

📌 REMINDER: M1 uses 1+2 partial exits. M2 uses 1.3×ZW floor 100t stop (not 1.5×ZW) 
and position sizing by zone width. These are the FROZEN risk mitigation parameters.

**Combined Combo 1:**
| Metric | P1 | P2 |
|--------|----|----|
| Trades | 346 | 405 |
| PF | ~5.5 @3t | 4.30 @4t |

⚠️ The P2 PF of 4.30 is the pre-partial baseline. The post-partial combined P2 
will be computed in Step 1. Use the post-partial number as the true baseline 
throughout this analysis.

---

## File Locations

```
TRADE OUTCOMES:
  c:\Projects\pipeline\shared\archetypes\zone_touch\output\qualifying_trades_outcomes_v32.csv

SIMULATION SCRIPTS:
  c:\Projects\pipeline\shared\archetypes\zone_touch\zone_touch_simulator.py
  c:\Projects\pipeline\shared\archetypes\zone_touch\risk_mitigation_v32.py

DEPLOYMENT SPEC:
  c:\Projects\pipeline\shared\archetypes\zone_touch\output\combined_recommendation_clean_v32.md
```

⚠️ B-ZScore scoring inconsistency (documented in risk mitigation): P1 uses 
Score_BZScore from CSV (C=1.0 probability). P2 uses JSON score_bzscore() 
(C=0.01 raw linear). Both threshold 0.50. If rebuilding populations from scratch, 
use the same approach as the risk mitigation investigation. If reusing the 
existing qualifying_trades_outcomes_v32.csv, verify counts match (M1: 107/96, 
M2: 239/309).

---

## Step 1: Build the True Baseline Trade Sequence

⚠️ MANDATORY FIRST STEP. Generate the complete per-trade outcome series for 
the frozen configuration on BOTH P1 and P2.

### 1a: Simulate the frozen configuration

Run the position-overlap-aware simulator with the frozen exit parameters 
(M1 partials, M2 1.3×ZW stop, M2 position sizing) on P1 and P2. The output 
is a time-ordered sequence of trades with:

| Column | Description |
|--------|------------|
| trade_id | Unique identifier |
| mode | 1 or 2 |
| datetime | Entry datetime |
| contracts | Position size (from sizing rules) |
| pnl_per_contract | Per-contract P&L in ticks |
| pnl_total | Total P&L (contracts × per-contract) |
| zone_width | Zone width in ticks |
| exit_type | TARGET_T1, TARGET_T2, BE_RUNNER, STOP, TIMECAP |
| bars_held | Duration |
| win | Boolean |

📌 REMINDER: M1 uses 1+2 partial exits. Each M1 trade produces a multi-leg 
outcome. Report the COMBINED per-trade PnL (sum across legs). The exit_type 
should reflect the final leg's exit (the runner determines overall outcome type).

### 1b: Verify baseline metrics

| Metric | P1 Expected | P1 Actual | P2 Expected | P2 Actual |
|--------|------------|-----------|-------------|-----------|
| M1 trades | ~107 | ? | ~96 | ? |
| M2 trades | ~239 | ? | ~309 | ? |
| M1 PF (with partials) | ~9.52 | ? | ~8.25 | ? |
| M2 PF | ~4.61 | ? | ~4.10 | ? |
| Combined PF | ? | ? | ? | ? |

⚠️ If combined post-partial P2 PF differs significantly from expectations, 
investigate before proceeding.

### 1c: Basic trade statistics

Report for the COMBINED P1+P2 population (all trades in time order):

| Metric | Value |
|--------|-------|
| Total trades | ? |
| Trading days covered | ? |
| Mean trades per day | ? |
| Median trades per day | ? |
| Max trades in one day | ? |
| Days with zero trades | ? |
| Mean PnL per trade (ticks, all contracts) | ? |
| Median PnL per trade | ? |
| Std dev PnL per trade | ? |
| Skewness | ? |
| Max single-trade win (ticks) | ? |
| Max single-trade loss (ticks) | ? |
| Win rate | ? |

⚠️ Use P1+P2 combined for the stress test — this gives the largest sample. The 
Monte Carlo bootstrap will resample from this population.

---

## Step 2: Historical Drawdown Analysis

### 2a: Equity curve and drawdown series

Compute the cumulative PnL (in ticks, accounting for contract sizing) in trade 
order. Report:

| Metric | P1 | P2 | P1+P2 |
|--------|----|----|-------|
| Total profit (ticks) | ? | ? | ? |
| Max drawdown (ticks) | ? | ? | ? |
| Profit / Max DD | ? | ? | ? |
| Max consecutive losses | ? | ? | ? |
| Max consecutive wins | ? | ? | ? |
| Longest drawdown (trades) | ? | ? | ? |
| Longest drawdown (days) | ? | ? | ? |

⚠️ Drawdown is measured in TICKS (all contracts combined), not dollars. The 
dollar conversion depends on contract size ($5/tick for NQ micro, $20/tick for 
NQ E-mini). Report in ticks; we'll convert later.

### 2b: Drawdown recovery analysis

For each drawdown that exceeded 500t:

| DD # | Peak Equity | Trough | DD Size | Recovery Trades | Recovery Days |
|------|------------|--------|---------|-----------------|---------------|
| 1 | ? | ? | ? | ? | ? |
| 2 | ? | ? | ? | ? | ? |
| ... | | | | | |

📌 REMINDER: A 500t drawdown at 1 MNQ contract = $2,500. At 3 contracts = $7,500. 
The capital requirement must accommodate the max drawdown with margin buffer.

---

## Step 3: Monte Carlo Simulation

⚠️ This is the core stress test. Bootstrap resample the trade outcomes to 
generate thousands of possible equity paths.

### 3a: Setup

- **Population:** All P1+P2 trades (the combined sequence from Step 1)
- **Method:** Bootstrap with replacement — randomly sample N trades from the 
  population (where N = population size) to create one synthetic equity path
- **Iterations:** 10,000 paths
- **Trade count per path:** Same as actual trade count (use the P1+P2 total)
- **Preserve:** Per-trade PnL including contract sizing. Do NOT resample 
  contracts separately — the pnl_total already reflects position sizing.

⚠️ IMPORTANT: This bootstrap assumes trades are independent. If there's serial 
correlation (winning streaks, losing clusters), the bootstrap understates tail 
risk. Check for serial correlation in Step 3b before interpreting results.

### 3b: Serial correlation check

Compute the autocorrelation of the trade PnL series at lags 1-5:

| Lag | Autocorrelation | Significant? (|r| > 2/sqrt(N)) |
|-----|----------------|-------------------------------|
| 1 | ? | ? |
| 2 | ? | ? |
| 3 | ? | ? |
| 4 | ? | ? |
| 5 | ? | ? |

If any lag shows significant autocorrelation, note it. This means the bootstrap 
understates clustering risk and the drawdown percentiles should be viewed 
conservatively.

📌 REMINDER: The frozen configuration uses one-position-at-a-time with overlap 
skipping. Trades are NOT mechanically independent (a long-held trade prevents 
subsequent signals). However, conditional on being TAKEN, the trade outcomes 
may still be approximately independent.

### 3c: Monte Carlo results

From the 10,000 paths, report:

**Drawdown distribution:**

| Percentile | Max Drawdown (ticks) |
|-----------|---------------------|
| 50th (median) | ? |
| 75th | ? |
| 90th | ? |
| 95th | ? |
| 99th | ? |
| Worst case (max) | ? |

⚠️ The 95th percentile max drawdown is the PRIMARY risk metric. Capital 
allocation should accommodate this with margin buffer.

**Profit distribution:**

| Percentile | Total Profit (ticks) |
|-----------|---------------------|
| 5th (worst) | ? |
| 25th | ? |
| 50th (median) | ? |
| 75th | ? |
| 95th (best) | ? |

**Win rate distribution:**

| Percentile | Win Rate |
|-----------|---------|
| 5th | ? |
| 25th | ? |
| 50th | ? |
| 75th | ? |
| 95th | ? |

### 3d: Ruin probability

From the 10,000 paths, what percentage hit a drawdown exceeding:

| DD Threshold | % of Paths | Interpretation |
|-------------|-----------|----------------|
| 1,000t | ? | Moderate stress |
| 2,000t | ? | Severe stress |
| 3,000t | ? | Near-ruin for small accounts |
| 5,000t | ? | Catastrophic |

⚠️ "Ruin" depends on account size and contract type. For 1 MNQ ($5/tick), 
3,000t = $15,000 drawdown. For 1 NQ ($20/tick), 3,000t = $60,000. These 
thresholds will be mapped to dollar amounts in Step 5.

---

## Step 4: WR Compression Stress Test

⚠️ The backtested WR may not persist in live trading. Slippage, data differences, 
and regime changes can compress WR. This test measures sensitivity.

### 4a: WR degradation scenarios

Artificially degrade the win rate by randomly converting N% of winners to 
losers (assign them -1× mean loss PnL). Run each scenario 1,000 times and 
report the median PF and 95th percentile max DD:

| WR Reduction | Effective WR (M1/M2) | Median PF | 95th DD |
|-------------|---------------------|-----------|---------|
| 0% (baseline) | 94.8% / 74.5% | ? | ? |
| -2% | 92.8% / 72.5% | ? | ? |
| -5% | 89.8% / 69.5% | ? | ? |
| -8% | 86.8% / 66.5% | ? | ? |
| -10% | 84.8% / 64.5% | ? | ? |
| -15% | 79.8% / 59.5% | ? | ? |

⚠️ KEY QUESTION: At what WR reduction does PF drop below 2.0? Below 1.5? 
Below 1.0 (breakeven)? This is the strategy's margin of safety.

📌 REMINDER: M1 has only 4 losers in 107 P1 trades. Converting even 2 winners 
to losers changes the ratio dramatically. The WR compression test reveals how 
fragile the M1 edge is.

### 4b: Slippage sensitivity

Add N ticks of total round-trip slippage PER CONTRACT to every trade (this 
accounts for adverse fills on both entry and exit). For M1 with 3 contracts, 
N ticks slippage = 3N ticks total position impact. Reduce each trade's 
pnl_total by (contracts × N):

| Slippage (per ct RT) | Combined PF | M1 PF | M2 PF | 95th DD |
|---------------------|------------|-------|-------|---------|
| 0t (baseline) | ? | ? | ? | ? |
| 2t | ? | ? | ? | ? |
| 3t | ? | ? | ? | ? |
| 4t | ? | ? | ? | ? |
| 6t | ? | ? | ? | ? |
| 10t | ? | ? | ? | ? |

⚠️ NQ typically has 1-2t of slippage per side (entry and exit), so 2-4t 
round-trip per contract is realistic. 4t round-trip is conservative. If PF 
drops below 2.0 at 4t RT slippage, the strategy is fragile.

---

## Step 5: Kelly Criterion & Capital Sizing

### 5a: Kelly fraction

Compute the Kelly fraction for each mode independently:

```
Kelly% = WR - (1 - WR) / (AvgWin / AvgLoss)
```

| Metric | Mode 1 | Mode 2 |
|--------|--------|--------|
| WR | ? | ? |
| Avg Win (ticks, per contract) | ? | ? |
| Avg Loss (ticks, per contract) | ? | ? |
| Win/Loss ratio | ? | ? |
| Full Kelly % | ? | ? |
| Half Kelly % | ? | ? |
| Quarter Kelly % | ? | ? |

⚠️ Full Kelly is theoretically optimal but assumes perfect parameter knowledge. 
In practice, half or quarter Kelly is standard for trading strategies with 
parameter uncertainty. The WR compression test in Step 4 shows how uncertain 
the parameters are.

### 5b: Capital requirements

The 95th percentile max drawdown from the Monte Carlo (Step 3c) is the combined 
DD across ALL trades (M1 and M2 mixed). Use THIS number for capital sizing — 
not per-tier DDs computed separately.

For each contract type, compute the capital needed:

| Contract Type | 95th DD (ticks, from 3c) | 95th DD ($) | 2x Buffer ($) | Min Capital |
|--------------|------------------------|-------------|---------------|-------------|
| MNQ ($5/tick) | ? | ? | ? | ? |
| NQ ($20/tick) | ? | ? | ? | ? |

⚠️ "2× Buffer" = 2× the 95th percentile DD. This is the minimum capital to 
deploy the strategy with reasonable confidence of surviving the worst expected 
drawdown without ruin.

📌 REMINDER: NQ intraday margin is typically $1,000-2,000 per MNQ contract. 
The capital requirement should be WELL above margin — the margin is the exchange 
minimum, not a sufficient trading stake.

### 5c: Expected annual metrics

Extrapolate from the P1+P2 trade rate and per-trade statistics:

| Metric | MNQ (3ct max) | NQ (3ct max) |
|--------|-------------|-------------|
| Est. trades per year | ? | ? |
| Est. annual profit (ticks) | ? | ? |
| Est. annual profit ($) | ? | ? |
| Est. max annual DD ($) | ? | ? |
| Annual profit / Max DD | ? | ? |
| Est. annual return on capital | ? | ? |

⚠️ These are ESTIMATES based on backtested performance. Live trading will 
differ due to slippage, missed fills, and regime changes. Use the slippage-
adjusted PF (4t RT slippage from Step 4b) for conservative estimates.

---

## Step 6: Regime Sensitivity

### 6a: Rolling performance

Compute rolling 60-trade PF and WR across the P1+P2 sequence:

| Metric | Min | Max | Mean | Std |
|--------|-----|-----|------|-----|
| Rolling 60-trade PF | ? | ? | ? | ? |
| Rolling 60-trade WR | ? | ? | ? | ? |

⚠️ If rolling PF drops below 1.0 for any window, report the dates and 
characterize the regime (high vol? trend? range?).

### 6b: Monthly performance

Report PnL by calendar month across P1+P2:

| Month | Trades | PF | WR | PnL (ticks) |
|-------|--------|----|----|-------------|
| ? | ? | ? | ? | ? |
| ... | | | | |

⚠️ Are there months with negative PnL? If so, how many and how severe? This 
sets expectations for live trading — even a profitable strategy has losing 
months.

---

## Step 7: Output Report

Produce `stress_test_v32.md` with:

### Section 1: Baseline Trade Statistics
- Post-partial combined P1/P2 metrics
- Trade frequency, PnL distribution, skewness

### Section 2: Historical Drawdown
- Equity curve description
- Drawdown recovery analysis
- Max consecutive losses

### Section 3: Monte Carlo Results
- Serial correlation check
- DD distribution (50th through 99th)
- Profit distribution
- Ruin probability table

### Section 4: Stress Tests
- WR compression results with breakeven point
- Slippage sensitivity with breakeven point

📌 REMINDER: Report the WR level where PF drops below 2.0, 1.5, and 1.0. 
Report the slippage level (round-trip per contract) where PF drops below 2.0. 
These are the strategy's margins of safety.

### Section 5: Kelly & Capital Sizing
- Kelly fractions per mode
- Capital requirements per contract type
- Expected annual metrics (conservative, using 4t RT slippage)

### Section 6: Regime Analysis
- Rolling performance stability
- Monthly breakdown
- Any losing periods identified

### Section 7: Deployment Recommendation
- Recommended contract type (MNQ vs NQ)
- Recommended starting capital
- Expected first-year performance range (5th to 95th percentile)
- Key risk factors and monitoring thresholds

⚠️ The deployment recommendation should be CONSERVATIVE. Use half-Kelly, 
4t RT slippage, and 95th percentile DD for all sizing recommendations.

📌 FINAL REMINDER: The model and execution parameters are FROZEN. This analysis 
does not change anything — it tells us whether the frozen configuration is 
deployable, at what capital level, and what the realistic risk profile looks like.

---

## Output Files

Save to: `c:\Projects\pipeline\shared\archetypes\zone_touch\output\`
- `stress_test_v32.md` — full report
- `stress_test_v32.py` — reproducible analysis script
- `monte_carlo_results_v32.csv` — raw MC output (10K paths summary)

Commit to `main` with message:
"Add stress test / Monte Carlo / Kelly analysis"

---

## Self-Check Before Submitting

- [ ] Post-partial combined P2 PF computed (not stale 4.30)
- [ ] M1 simulation uses 1+2 partial exits (not flat)
- [ ] M2 simulation uses 1.3×ZW floor 100t stop (not 1.5×ZW)
- [ ] M2 simulation uses position sizing (3/2/1 by ZW)
- [ ] Trade sequence is time-ordered (for serial correlation and rolling analysis)
- [ ] Monte Carlo uses P1+P2 combined population
- [ ] Serial correlation checked before interpreting MC results
- [ ] WR compression tested on M1 and M2 independently
- [ ] Slippage tested as round-trip per contract (2-10t range), scaled by contracts
- [ ] Capital requirements use COMBINED MC 95th DD (not per-tier)
- [ ] B-ZScore scoring approach matches risk mitigation (P1 CSV, P2 JSON) if rebuilt
- [ ] Kelly computed per mode (not combined)
- [ ] Capital requirements computed for both MNQ and NQ
- [ ] Annual estimates use 4t RT slippage (conservative)
- [ ] Rolling PF checked for sub-1.0 windows
- [ ] Losing months identified and characterized
- [ ] Deployment recommendation uses half-Kelly and 95th percentile DD
