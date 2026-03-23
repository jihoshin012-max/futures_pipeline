# NQ Zone Touch — Autotrader Build Spec: Part C (Paper Trading Protocol)

> **Version:** 3.0
> **Date:** 2026-03-23
> **Scope:** Paper trading rules, success criteria, weekly review, queued post-trading work
> **Prerequisite:** Part A v3.0 build complete. Part B v3.0 replication gate PASSED.
> **Period:** P3: Mar–Jun 2026 (3 months minimum, 60+ RTH trading days)
> **Change from v2.0:** Zone-relative exits, CT 5t limit entry, updated kill-switch thresholds, zone width monitoring added.

---

## Paper Trading Objectives

1. Validate the strategy on unseen live data (P3 — data the pipeline never touched)
2. Validate zone-relative exits in real-time (zone widths will vary vs P1/P2 distribution)
3. Validate CT 5t limit fill rate and fill timing in live conditions
4. Measure execution reality: slippage, latency, signal-to-trade conversion
5. Collect ETH vs RTH data to resolve the session filter question
6. Build confidence in the autotrader's mechanical operation before risking capital

⚠️ Paper trading is NOT optimization. No parameters change during P3. The autotrader runs P1-frozen scoring with zone-relative exit multipliers (0.5x, 1.0x, 1.5x, 120t floor). If performance degrades, you gather data to understand why — you don't adjust.

---

## Expected Trade Volume

| Mode | Trades/RTH day | Trades in 60 days | Basis |
|------|---------------|-------------------|-------|
| CT mode (5t limit fills) | ~0.35 | ~21 | P2: ~177 fills / ~150 days × ~95% fill rate |
| CT LIMIT_EXPIRED | ~0.02 | ~1 | P2: ~10 unfilled / ~150 days |
| WT/NT mode | ~0.3 | ~18 | P2: ~125 trades / ~150 days, minus LIMIT_PENDING blocks |
| Combined | ~0.65 | ~39 | Most days: 0-1 trades. Some days: 2-3. |

⚠️ 39 trades in 3 months is a small sample. Statistical significance requires patience. Don't overreact to a bad week.

⚠️ Trade volume may differ from P2 because P1 had a very different zone width distribution (42.6% under 100t vs P2's 11.9%). P3's distribution is unknown — monitor weekly.

---

## Variants to Track

Both use identical scoring, features, zone-relative exits, and CT 5t limit. The only difference is whether ETH signals are executed or just logged.

| Variant | What it does | Purpose |
|---------|-------------|---------|
| **A (full)** | Takes all trades — RTH + ETH | Baseline. What the backtest produced. |
| **B (RTH only)** | Takes RTH trades only, logs ETH as skipped (reason=ETH_FILTER) | Tests whether removing ETH improves PF |

⚠️ Variant B doesn't require separate autotrader code. Just add a `variant_b_action` column to signal_log.csv: TRADE for RTH signals, SKIP_ETH for ETH signals. Then filter trade_log.csv by session=RTH for Variant B metrics.

---

## Success Criteria (after 3 months)

### Minimum for live deployment:

| Metric | Minimum | Stretch Goal | P2 ZR Reference | P1 ZR Reference |
|--------|---------|-------------|-----------------|-----------------|
| Combined PF @3t | > 2.0 | > 5.0 | 33.35 | 7.25 |
| Win rate | > 75% | > 85% | 94.2% | 83.6% |
| Max consecutive losses | ≤ 5 | ≤ 3 | TBD from answer key | TBD |
| Max DD (single trade) | < zone-relative max | — | 154t | TBD |
| CT limit fill rate | > 85% | > 95% | ~95% | ~95% |
| Mean slippage | < 3t | < 1t | N/A (sim assumed 0) | N/A |
| Mean latency | < 5 seconds | < 1 second | N/A | N/A |

⚠️ Zone-relative PF references are much higher than fixed-exit references. P3 will be lower than P2 (different zone width distribution, unseen market conditions). PF dropping from 28 to 5 is expected. PF dropping below 2.0 means the edge or the zone-relative framework didn't generalize.

⚠️ Max DD per trade now depends on zone width. A 300t zone has a 450t stop (1.5x). A 50t zone has a 120t stop (floor). Track max DD per trade alongside zone_width to understand if wide-zone trades carry disproportionate risk.

### Kill criteria (stop paper trading early):

| Condition | Action |
|-----------|--------|
| PF < 1.0 after 20+ trades | Pause and investigate. Compare zone width distribution vs P1/P2. |
| 5+ consecutive losses | Kill-switch already halts. Review before resuming next week. |
| Max DD > 1200t (weekly limit) | Halt paper trading. Full review before any continuation. |
| CT limit fill rate < 70% | Limit entry may not work in live conditions. Investigate fill mechanics. |
| Mean slippage > 5t consistently | Execution issue — fix before continuing. |
| Zone width distribution dramatically different from P1/P2 | Flag for investigation — zone-relative exits calibrated on P1/P2 widths. |

---

## Weekly Review (every Friday)

⚠️ Generate `weekly_summary.md` from trade_log.csv and signal_log.csv. This is the primary monitoring tool.

### Weekly Summary Contents:

**Performance:**
- Trades this week / cumulative
- PF @3t (week / cumulative)
- Win rate (week / cumulative)
- Net PnL ticks (week / cumulative)
- Max DD this week (single trade, with zone_width noted)

**Zone-Relative Monitoring (NEW in v3.0):**
- Zone width distribution this week vs P1/P2 reference
- Mean zone_width_ticks of traded zones (P2 reference: ~170t)
- Trades in narrow zones (< 100t) this week / cumulative — these are the weakest bin
- Trades in wide zones (200t+) this week / cumulative — these produce highest EV
- Stop floor activations (zone < 80t, stop = 120t instead of 1.5x)
- Mean T1 ticks / T2 ticks / stop ticks this week (should scale with zone width)

⚠️ If narrow zone trades (< 100t) consistently produce PF < 1.5, flag for investigation. This bin was weakest on both P1 (PF 2.77 with floor) and P2 (PF 4.77).

**CT Limit Entry Monitoring (NEW in v3.0):**
- CT signals placed / filled / expired this week
- Fill rate (should be ~95%)
- Mean bars to fill (P2 reference: ~7 bars at 5t depth)
- Price improvement fills (filled better than limit price)
- LIMIT_PENDING blocks (WT signals skipped during CT limit window)

⚠️ If CT fill rate drops below 85% for 2+ consecutive weeks, the 5t limit may not work in live conditions (wider spreads, different microstructure). Flag for investigation.

**Execution:**
- Mean slippage (ticks) — for WT market entries
- CT limit slippage (should be 0 or negative = price improvement)
- Max slippage
- Mean latency (ms)
- Any fills > 2 bars after signal (flag as LATE_ENTRY)

**Signal Quality:**
- Total signals fired / trades taken / skip rate
- Skip reasons breakdown (IN_POSITION, CROSS_MODE_OVERLAP, LIMIT_PENDING, LIMIT_EXPIRED, TF_FILTER, SEQ_FILTER, BELOW_THRESHOLD)
- Mean score of traded signals vs skipped signals
- Any SBB touches above threshold (should be 0)

⚠️ Reminder: compare every weekly result against P2 reference values. Flag deviations > 1 standard deviation from P2 metrics.

**ETH vs RTH:**
- Variant A PF (week / cumulative)
- Variant B (RTH-only) PF (week / cumulative)
- ETH trades this week: count, wins, losses
- Running ETH stop rate vs RTH stop rate

**Mode breakdown:**
- CT trades / PF / WR / mean zone_width
- WT/NT trades / PF / WR / mean zone_width
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
- Signals skipped due to LIMIT_PENDING
- Trades where zone_width < 50t (extremely narrow — monitor outcomes)
- Trades where stop > 400t (extremely wide zone — monitor risk)

---

## Post-Paper-Trading Analysis (after 3 months)

⚠️ All decisions below are made AFTER collecting 3 months of P3 data. No parameter changes during paper trading.

### ETH Decision

| P3 ETH Result | Action |
|---------------|--------|
| ETH PF < 1.0 AND ETH has ≥ 50% of losses | **Filter ETH.** Deploy Variant B (RTH only). One-line change. |
| ETH PF 1.0-1.5 | **Monitor.** Continue tracking in live with small position. |
| ETH PF > 1.5 | **Keep ETH.** P2's weakness may have been sample-specific. |

### Zone Width Distribution Assessment

| P3 Result | Action |
|-----------|--------|
| Distribution similar to P2 (< 15% under 100t) | Framework validated as-is. |
| Distribution similar to P1 (> 40% under 100t) | Stop floor is critical. Consider raising floor to 150t. |
| Distribution dramatically different from both | Zone-relative multipliers may need recalibration on P3 data. |

### CT Limit Fill Assessment

⚠️ Reminder: all assessments below use P3 data collected over the full 3 months. No changes during paper trading.

| P3 Result | Action |
|-----------|--------|
| Fill rate > 90% | 5t limit validated for live deployment. |
| Fill rate 80-90% | Consider reducing to 3t depth (higher fill, slightly less filtering). |
| Fill rate < 80% | Revert to market entry for CT. The microstructure doesn't support limit fills. |

### Narrow Zone Assessment

| P3 Result | Action |
|-----------|--------|
| < 100t zone PF > 1.5 | Keep narrow zones in population. |
| < 100t zone PF 1.0-1.5 | Consider minimum zone width filter (e.g., ZW ≥ 75t). |
| < 100t zone PF < 1.0 | Exclude narrow zones. Minimum zone width filter required. |

⚠️ All decisions use P3 data — no recalibration during paper trading. These analyses happen AFTER the 3-month period ends.

### Exit Profile Comparison

| Metric | P1 ZR | P2 ZR | P3 |
|--------|-------|-------|----|
| WR | 83.6% | 94.2% | ? |
| PF | 7.25 | 33.35 | ? |
| Stop rate | ? | ? | ? |
| Time cap rate | ? | ? | ? |
| CT fill rate | ~95% | ~95% | ? |
| Mean zone_width | ? | ~170t | ? |
| Narrow zone % | 42.6% | 11.9% | ? |

---

## Queued Post-Paper-Trading Work

⚠️ None of these run during paper trading. They queue for after P3 results are analyzed.

### Autoresearch (11 items):
1. Bin granularity (tercile vs quintile)
2. Interaction terms (F10×F04, etc.)
3. Feature transforms (log/sqrt on F21)
4. Categorical remapping (non-tercile TF scoring)
5. Volatility-adjusted exits (ATR multiples — may complement zone-relative)
6. Screening rejects as filters (F22 Break Rate gate)
7. Conditional SBB scoring
8. Entry variations (volume confirmation, retest patterns — 5t limit already implemented)
9. SpeedRead as feature (speed regime distinct from ATR)
10. ETH filter (resolved by P3 data — see ETH Decision above)
11. VP Ray V4 fix (persist ImbalancePrice in ZoneData — collect during paper trading, screen after)

### Exit investigation follow-ups (from v3.0 findings):
- MFE-floor exit rule for WT drifters (if MFE < 20t by bar 20, exit)
- Penetration speed-based exit (100t in 10 bars catches 41% of blowout losers)
- Narrow zone stop floor optimization (120t vs 150t)
- Zone-relative trail after T1 (0.15x zw no cap showed marginal improvement)

### Zone break strategy:
- See ZONE_BREAK_STRATEGY_SEEDS.md for collected findings
- Inverted feature polarity from bounce pipeline
- SBB touches (1,411) + bounce near-miss touches as break population
- Key insights: blowout vs drifter failure modes, opposite edge cross signal, WT structural weakness
- Same Prompt 0-4 pipeline structure
- Queue after bounce autotrader is live-deployed

### Shared config refactor:
- zone_shared_config.h — extract duplicated constants from V4/ZRA/ZB4/autotrader
- Do AFTER paper trading, BEFORE autoresearch
- Recompile + replication gate required after refactor

### Live deployment (if P3 passes):
- Start with 1 contract (single-leg T1 only — conservative)
- After 2 weeks stable: scale to 3 contracts (2-leg)
- After 1 month stable: evaluate full position sizing
- Staged scale-up, not all-at-once
- Zone-relative stops mean wider max loss per trade — size accordingly

---

## Preparation Checklist (before P3 starts)

✅ **Complete before enabling paper trading:**
- [ ] Part A v3.0 build complete (zone-relative exits, CT 5t limit, stop floor)
- [ ] Part B v3.0 replication gate PASSED against `p2_twoleg_answer_key_zr.csv`
- [ ] Enable Trading Logic = Yes, Send Live Orders = No
- [ ] SpeedRead V2 Roll50 export added to Sierra Chart bar data (or flagged TODO)
- [ ] Macro calendar pre-populated for Mar–Jun 2026 (FOMC, CPI, NFP, PPI, retail sales, GDP, unemployment)
- [ ] Weekly summary template created (includes zone-relative and CT limit sections)
- [ ] trade_log.csv writing correctly (verified: zone_width_ticks, stop_ticks, t1_ticks, t2_ticks, entry_type columns)
- [ ] signal_log.csv writing correctly (verified: LIMIT_EXPIRED, LIMIT_PENDING skip reasons)
- [ ] All additional logs configured (microstructure, speedread, zone stability)
- [ ] Kill-switch thresholds set (3 consecutive, -600t daily, -1200t weekly)
- [ ] Variant B tracking configured (ETH signals logged as SKIP_ETH)
- [ ] Friday review calendar reminder set
- [ ] ZONE_BREAK_STRATEGY_SEEDS.md saved in pipeline docs/
