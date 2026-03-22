# NQ Zone Touch — Autotrader Build Spec: Part C (Paper Trading Protocol)

> **Version:** 2.0
> **Date:** 2026-03-22
> **Scope:** Paper trading rules, success criteria, weekly review, queued post-trading work
> **Prerequisite:** Part A build complete. Part B replication gate PASSED.
> **Period:** P3: Mar–Jun 2026 (3 months minimum, 60+ RTH trading days)

---

## Paper Trading Objectives

1. Validate the strategy on unseen live data (P3 — data the pipeline never touched)
2. Measure execution reality: slippage, latency, signal-to-trade conversion
3. Collect ETH vs RTH data to resolve the session filter question
4. Build confidence in the autotrader's mechanical operation before risking capital

⚠️ Paper trading is NOT optimization. No parameters change during P3. The autotrader runs P1-frozen config. If performance degrades, you gather data to understand why — you don't adjust.

---

## Expected Trade Volume

| Mode | Trades/RTH day | Trades in 60 days | Basis |
|------|---------------|-------------------|-------|
| CT mode | ~0.4 | ~24 | P2: 58 trades / ~150 days |
| WT/NT mode | ~0.35 | ~21 | P2: ~33 additional trades / ~150 days |
| Combined | ~0.75 | ~45 | Most days: 0-1 trades. Some days: 2-3. |

⚠️ 45 trades in 3 months is a small sample. Statistical significance requires patience. Don't overreact to a bad week.

---

## Variants to Track

Both use identical scoring, features, and exit logic. The only difference is whether ETH signals are executed or just logged.

| Variant | What it does | Purpose |
|---------|-------------|---------|
| **A (full)** | Takes all trades — RTH + ETH | Baseline. What the backtest produced. |
| **B (RTH only)** | Takes RTH trades only, logs ETH as skipped (reason=ETH_FILTER) | Tests whether removing ETH improves PF |

⚠️ Variant B doesn't require separate autotrader code. Just add a `variant_b_action` column to signal_log.csv: TRADE for RTH signals, SKIP_ETH for ETH signals. Then filter trade_log.csv by session=RTH for Variant B metrics.

---

## Success Criteria (after 3 months)

### Minimum for live deployment:

| Metric | Minimum | Stretch Goal | P2 Reference |
|--------|---------|-------------|-------------|
| Combined PF @3t | > 1.5 | > 2.5 | 5.10 (CT), 3.07 (All) |
| Win rate | > 70% | > 85% | 91.4% |
| Max consecutive losses | ≤ 5 | ≤ 3 | 1 |
| Max DD | < 600t ($3,000) | < 300t ($1,500) | 193t ($965) |
| Mean slippage | < 3t | < 1t | N/A (sim assumed 0) |
| Mean latency | < 5 seconds | < 1 second | N/A |

⚠️ Reminder: P2 results reflect in-sample exit optimization on P1 data. P3 performance WILL be lower than P2. PF dropping from 5.10 to 2.5 is healthy. PF dropping to 0.9 means the edge didn't generalize.

### Kill criteria (stop paper trading early):

| Condition | Action |
|-----------|--------|
| PF < 1.0 after 30+ trades | Pause and investigate. The strategy may not work on live data. |
| 5+ consecutive losses | Kill-switch already halts. Review before resuming next week. |
| Max DD > 800t | Halt paper trading. Full review before any continuation. |
| Mean slippage > 5t consistently | Execution issue — fix before continuing. The edge may not survive real spreads. |

---

## Weekly Review (every Friday)

⚠️ Generate `weekly_summary.md` from trade_log.csv and signal_log.csv. This is the primary monitoring tool.

### Weekly Summary Contents:

**Performance:**
- Trades this week / cumulative
- PF @3t (week / cumulative)
- Win rate (week / cumulative)
- Net PnL ticks (week / cumulative)
- Max DD this week

**Execution:**
- Mean slippage (ticks)
- Max slippage
- Mean latency (ms)
- Any fills > 2 bars after signal (flag as LATE_ENTRY)

**Signal Quality:**
- Total signals fired / trades taken / skip rate
- Skip reasons breakdown (IN_POSITION, CROSS_MODE, TF_FILTER, SEQ_FILTER, BELOW_THRESHOLD)
- Mean score of traded signals vs skipped signals
- Any SBB touches above threshold (should be 0)

⚠️ Reminder: compare every weekly result against P2 reference values. Flag deviations > 1 standard deviation from P2 metrics.

**ETH vs RTH:**
- Variant A PF (week / cumulative)
- Variant B (RTH-only) PF (week / cumulative)
- ETH trades this week: count, wins, losses
- Running ETH stop rate vs RTH stop rate

**Mode breakdown:**
- CT trades / PF / WR
- WT/NT trades / PF / WR
- Any mode producing PF < 1.0?

⚠️ Reminder: P3 is observation only. If a mode shows PF < 1.0 for 2+ consecutive weeks, flag it but do NOT disable. Collect the full 3 months. The sample is too small for weekly conclusions.

**Zone stability:**
- Zones created / died this week
- Any study recompilation?
- Any data feed gaps?
- Total active zones (trending up/down/stable?)

**Anomalies:**
- Kill-switch activations
- Trades with slippage > 3t
- Trades with latency > 5 seconds
- Signals skipped due to cross-mode overlap

---

## Post-Paper-Trading Analysis (after 3 months)

### ETH Decision

| P3 ETH Result | Action |
|---------------|--------|
| ETH PF < 1.0 AND ETH has ≥ 50% of losses | **Filter ETH.** Deploy Variant B (RTH only). One-line change. |
| ETH PF 1.0-1.5 | **Monitor.** Continue tracking in live with small position. |
| ETH PF > 1.5 | **Keep ETH.** P2's weakness was noise on 17 trades. |

⚠️ Reminder: all decisions below use P3 data — no recalibration during paper trading. These analyses happen AFTER the 3-month period ends.

### Score Margin Investigation

From P3 trade_log.csv:
- Do margin < 1 trades continue to account for most stops? (P2: 3/4 stops at margin < 1)
- If yes: raising threshold by 1 point eliminates those trades. Evaluate PF trade-off.

### Exit Profile Comparison

| Metric | P1 | P2 | P3 |
|--------|----|----|-----|
| Target rate | 94% | 87.9% | ? |
| Stop rate | 2% | 6.9% | ? |
| Time cap rate | 4% | 5.2% | ? |
| Time cap avg PnL | -22t | +10.7t | ? |

If target rate continues declining (94→88→?), the 2-leg structure's T1 floor becomes more valuable. If stop rate increases, ETH filter or margin filter becomes urgent.

---

## Queued Post-Paper-Trading Work

⚠️ None of these run during paper trading. They queue for after P3 results are analyzed.

### Autoresearch (10 items):
1. Bin granularity (tercile vs quintile)
2. Interaction terms (F10×F04, etc.)
3. Feature transforms (log/sqrt on F21)
4. Categorical remapping (non-tercile TF scoring)
5. Volatility-adjusted exits (ATR multiples)
6. Screening rejects as filters (F22 Break Rate gate)
7. Conditional SBB scoring
8. Entry variations (limit inside zone, volume confirmation, retest)
9. SpeedRead as feature (speed regime distinct from ATR)
10. ETH filter (resolved by P3 data — see ETH Decision above)

### Zone break strategy:
- Inverted feature polarity from bounce pipeline
- SBB touches (1,411) + bounce near-miss touches (269 P2, within 2pts below threshold)
- Key insights from bounce diagnostics: PRIOR_HELD losers, low score margin cluster, ETH weakness all point to break candidates
- Same Prompt 0-4 pipeline structure
- Queue after bounce autotrader is live-deployed

### Live deployment (if P3 passes):
- Start with 1 contract (single-leg T1 only — conservative)
- After 2 weeks stable: scale to 3 contracts (2-leg)
- After 1 month stable: evaluate full position sizing
- Staged scale-up, not all-at-once

---

## Preparation Checklist (before P3 starts)

✅ **Complete before enabling paper trading:**
- [ ] Part A build complete
- [ ] Part B replication gate PASSED
- [ ] SpeedRead V2 Roll50 export added to Sierra Chart bar data (or flagged TODO)
- [ ] Macro calendar pre-populated for Mar–Jun 2026 (FOMC, CPI, NFP, PPI, retail sales, GDP, unemployment)
- [ ] Weekly summary template created
- [ ] trade_log.csv writing correctly (verified during replication gate)
- [ ] signal_log.csv writing correctly (verified during replication gate)
- [ ] All additional logs configured (microstructure, speedread, zone stability)
- [ ] Kill-switch thresholds set (3 consecutive, -400t daily, -800t weekly)
- [ ] Variant B tracking configured (ETH signals logged as SKIP_ETH)
- [ ] Friday review calendar reminder set
