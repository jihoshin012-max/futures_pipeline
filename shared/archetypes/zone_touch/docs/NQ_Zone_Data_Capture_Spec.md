# NQ Zone Touch — Data Capture Specification

> **Version:** 1.0
> **Date:** 2026-03-22
> **Scope:** Data points to capture during autotrader build and paper trading (P3: Mar–Jun 2026)
> **Purpose:** Future reference, diagnostics, autoresearch inputs, and strategy refinement

---

## Two Categories

1. **Pre-deployment (capture from existing pipeline data NOW)** — items 1-5
2. **Paper trading (capture from day one of P3)** — items 6-12

---

## Pre-Deployment: Extract from Pipeline Data

These use existing P2 simulation output and P1 scored touches. Run once, save permanently.

⚠️ No new simulations needed. Extract from existing files.

---

### Item 1: Per-Trade Feature Values (P2)

**Source:** P2 simulation output + feature computation from Prompt 3

For every P2 trade taken (across all 4 "Yes" groups), save:

| Column | Description |
|--------|------------|
| trade_id | Unique identifier |
| seg_model_group | e.g., seg3_ACal_ModeB |
| period | P2a or P2b |
| datetime | Touch bar datetime |
| direction | DEMAND / SUPPLY |
| F10_PriorPenetration | Raw value |
| F04_CascadeState | PRIOR_HELD / NO_PRIOR / PRIOR_BROKE |
| F01_Timeframe | SourceLabel + TFWeightScore |
| F21_ZoneAge | Raw value (bars since zone birth) |
| acal_score | A-Cal composite score |
| acal_threshold | Frozen threshold |
| score_margin | score - threshold (how far above/below) |
| trend_label | WT / CT / NT |
| SBB_label | NORMAL / SBB |
| entry_price | Actual entry (next bar open) |
| exit_price | Where trade closed |
| exit_type | TARGET / STOP / BE / TRAIL / TIMECAP |
| pnl_ticks | Net PnL in ticks (after 3t cost) |
| bars_held | Number of bars from entry to exit |
| mfe_ticks | Max favorable excursion |
| mae_ticks | Max adverse excursion |

**Save as:** `p2_trade_details.csv`

⚠️ MFE and MAE are critical — they show how close winning trades came to stopping out and how far losing trades moved favorably before reversing. This feeds step-up optimization directly.

---

### Item 2: Losing Trade Profiles (P2)

**Source:** Filter `p2_trade_details.csv` for exit_type = STOP or TIMECAP

For the ~7 losing/time-cap trades on the winner (seg3 ModeB), report:

| Field | Value |
|-------|-------|
| datetime | When |
| direction | Long or short |
| F10 value | Was prior penetration unusually high for a "passing" touch? |
| F04 value | Which cascade state? |
| F01 TF | Which timeframe? |
| F21 age | Young or old? |
| zone_width | Narrow or wide? |
| SBB_label | Did any SBB touches leak through? |
| session | Morning / afternoon / overnight? |
| mfe_ticks | How far did it move favorably before failing? |
| mae_ticks | How deep did the adverse excursion go? |
| bars_held | Fast stop-out or slow bleed? |
| score_margin | Barely above threshold or well above? |

**Purpose:** Qualitative pattern recognition. 7 trades isn't enough for statistics, but if all 4 stops happened on afternoon 30m demand zones with zone age > 500 bars, that's a pattern worth investigating.

**Save as:** Section in `p2_trade_diagnostics.md`

---

### Item 3: Near-Miss Touches (P1 + P2)

**Source:** `p1_scored_touches_acal.csv` and P2 scored touches

For touches scoring within 2 points below A-Cal threshold:

| Metric | Value |
|--------|-------|
| Count (P1) | How many near-misses on P1? |
| Count (P2) | How many on P2? |
| Mean R/P @60 of near-misses | Are they close to threshold-quality or clearly worse? |
| PF @3t if threshold were lowered by 1 point | Simulated — does PF drop sharply or gradually? |
| PF @3t if threshold were lowered by 2 points | Same |

⚠️ This measures **threshold sensitivity**:
- **Cliff:** PF drops from 5.0 to 1.2 at threshold-1 → threshold is well-placed, model correctly separates
- **Slope:** PF drops from 5.0 to 4.0 to 3.2 → threshold could be loosened for more trades with modest PF cost

**Save as:** `threshold_sensitivity.md`

---

### Item 4: Time-of-Day Distribution

**Source:** `p2_trade_details.csv`

For the winner (seg3 ModeB, 58 P2 trades):

| Hour Block | Trades | Wins | Losses | PF @3t |
|-----------|--------|------|--------|--------|
| 8:30-10:00 | ? | ? | ? | ? |
| 10:00-12:00 | ? | ? | ? | ? |
| 12:00-14:00 | ? | ? | ? | ? |
| 14:00-16:00 | ? | ? | ? | ? |
| 16:00-17:00 | ? | ? | ? | ? |
| Overnight | ? | ? | ? | ? |

⚠️ If >60% of trades cluster in one block, the strategy has a session dependency the scoring model doesn't capture. Worth investigating as a future filter (autoresearch or next pipeline iteration).

Also report: day-of-week distribution (Mon-Fri). Any day with 0 trades across 6 months of P2 is notable.

**Save as:** Section in `p2_trade_diagnostics.md`

---

### Item 5: Consecutive Loss Sequences

**Source:** `p2_trade_details.csv`, sorted by datetime

| Metric | Value |
|--------|-------|
| Max consecutive losses (P2 combined) | ? |
| Max consecutive losses (P2a) | ? |
| Max consecutive losses (P2b) | ? |
| Longest drawdown duration (bars between equity high and recovery) | ? |
| Were consecutive losses on the same day? | Yes / No |
| Were consecutive losses in the same TF? | Which TF? |
| Max losing streak PnL (ticks) | How much damage before recovery? |

⚠️ This directly informs position sizing and the autotrader's kill-switch logic. If the max losing streak is 3 trades totaling -400t, a kill-switch at 5 consecutive losses or -600t gives reasonable headroom.

**Save as:** Section in `p2_trade_diagnostics.md`

---

## Paper Trading: Capture from Day One

These require the autotrader to log additional data in real-time during P3 (Mar–Jun 2026).

⚠️ Build these into the C++ autotrader from the start. Retrofitting logging after paper trading begins means lost data.

---

### Item 6: Execution Slippage

**Log per trade:**

| Field | Description |
|-------|------------|
| signal_bar_close_price | Last price of the touch bar |
| simulated_entry_price | Open of next bar (what backtest assumes) |
| actual_fill_price | Where the order actually filled |
| slippage_ticks | actual_fill - simulated_entry (signed: positive = worse fill) |

**Aggregate weekly:**
- Mean slippage (ticks)
- Max slippage
- % of trades with slippage > 2t

⚠️ The simulation assumes zero slippage. If mean slippage is 2-3 ticks, the effective cost model is 5-6t not 3t. This directly impacts whether the strategy remains profitable at the PF @4t threshold.

---

### Item 7: Signal-to-Trade Latency

**Log per signal:**

| Field | Description |
|-------|------------|
| zone_touch_detected_time | Timestamp when study detects the touch |
| touch_bar_close_time | When the touch bar actually closes |
| scoring_complete_time | When all 4 features are computed and score is calculated |
| order_submitted_time | When the order is sent to the exchange |
| order_filled_time | When the fill is confirmed |
| total_latency_ms | order_filled - touch_bar_close (milliseconds) |
| bars_delayed | How many bars elapsed between touch bar close and actual entry |

⚠️ If bars_delayed > 0 for more than 10% of signals, the "next bar open" assumption is violated. The entry is 2+ bars late, which changes the effective entry price and potentially the trade outcome.

---

### Item 8: Skipped Signals (No-Overlap)

**Log per skipped signal:**

| Field | Description |
|-------|------------|
| datetime | When the signal fired |
| reason | IN_POSITION / OTHER |
| current_position_entry | When was the existing trade entered? |
| current_position_pnl | What was the unrealized PnL at skip time? |
| skipped_signal_score | A-Cal score of the skipped touch |
| skipped_signal_trend | WT / CT / NT |

**Aggregate weekly:**
- Total signals fired vs trades taken
- Skip rate (%)
- Mean score of skipped signals vs taken signals

⚠️ If high-scoring signals are regularly skipped because of an existing lower-quality trade, a priority queue (exit current if new signal scores higher) or second-contract system could capture additional edge.

---

### Item 9: Zone Study Version Stability

**Log daily:**

| Field | Description |
|-------|------------|
| date | Trading date |
| v4_study_version | Compile timestamp or hash of the ACSIL study |
| zones_created_today | How many new zones appeared |
| zones_died_today | How many zones broke |
| total_active_zones | End-of-day count |
| any_recompilation | Yes / No — did the study recompile during the session? |
| data_feed_gaps | Any gaps in the tick feed (count + duration) |

⚠️ Zone placement depends on the study running continuously. A study recompile, data feed gap, or Sierra Chart restart can cause zone recalculation — zones may appear or disappear differently than in backtest. Log any anomaly.

---

### Item 10: Market Microstructure at Touch

**Log per zone touch (all touches, not just trades taken):**

| Field | Description |
|-------|------------|
| datetime | Touch time |
| bid_ask_spread | Spread at touch bar close (ticks) |
| touch_bar_volume | Total volume on the touch bar |
| touch_bar_num_trades | Number of trades on the bar |
| touch_bar_delta | AskVol - BidVol (signed) |
| book_depth_bid | If available: resting bid size within 10 ticks of zone |
| book_depth_ask | If available: resting ask size within 10 ticks of zone |
| score | A-Cal score (even if below threshold) |
| trade_taken | Yes / No |

⚠️ Not for the current model — for future entry optimization (autoresearch item #8: entry variations). Capturing this from day one means you can screen it retroactively. Book depth may not be available in Sierra Chart's data feed — log what's accessible, skip what isn't.

---

### Item 11: Macro Event Correlation

**Log per trade:**

| Field | Description |
|-------|------------|
| is_news_day | Binary: FOMC, CPI, NFP, PPI, retail sales, GDP, unemployment (known schedule) |
| news_event | Which event, if any |
| minutes_to_event | How many minutes before/after the event was the trade entered? |
| event_day_pnl | PnL of this trade |

**Also maintain a simple calendar file:**

| Date | Event | Time |
|------|-------|------|
| 2026-03-26 | FOMC Minutes | 14:00 ET |
| ... | ... | ... |

⚠️ Pre-populate the known economic calendar for Mar–Jun 2026 at the start of paper trading. Flag any trade within 30 minutes of a major release.

**Purpose:** If losing trades cluster around news events, a simple "don't trade within N minutes of scheduled news" filter could eliminate the worst losses cheaply.

---

### Item 12: SpeedRead at Each Touch

**Log per zone touch (all touches, not just trades taken):**

| Field | Description |
|-------|------------|
| datetime | Touch time |
| speedread_roll50 | SpeedRead V2 Roll50 composite value at the touch bar |
| speedread_median_norm | Median-normalized component |
| trade_taken | Yes / No |
| pnl_ticks | If traded, net PnL (null if not traded) |

⚠️ **Requires Sierra Chart export fix:** Add SpeedRead V2 Roll50 subgraph as an exported column in the bar data. This was identified as a gap — the C++ study exists but its output isn't in the CSV export. Fix the export when building the autotrader chartbook.

**Purpose:** Retroactive screening of SpeedRead as a zone feature (autoresearch item #10) without re-running paper trading.

---

## Output Files

### Pre-deployment (extract now):

| File | Contents |
|------|----------|
| `p2_trade_details.csv` | All P2 trades with full feature values, MFE/MAE, exit details |
| `p2_trade_diagnostics.md` | Losing trade profiles, time-of-day distribution, consecutive loss analysis |
| `threshold_sensitivity.md` | Near-miss analysis, PF at threshold-1 and threshold-2 |

### Paper trading (autotrader logs):

| File | Frequency | Contents |
|------|-----------|----------|
| `trade_log.csv` | Per trade | All Item 6-8 fields + standard trade data |
| `signal_log.csv` | Per signal (including skipped) | Score, trend, skip reason |
| `microstructure_log.csv` | Per zone touch | Item 10 fields |
| `speedread_log.csv` | Per zone touch | Item 12 fields |
| `zone_stability_log.csv` | Daily | Item 9 fields |
| `macro_calendar.csv` | Static + per trade | Item 11 fields |
| `weekly_summary.md` | Weekly | Aggregated slippage, latency, skip rate, trade count |

---

## Implementation Notes

⚠️ **Build logging into the autotrader from the start.** The cost of adding a few log statements at build time is trivial. The cost of realizing 2 months into paper trading that you needed slippage data but didn't capture it is a wasted paper trading period.

⚠️ **Log everything, analyze later.** Storage is cheap. Err on the side of capturing too much. The microstructure and SpeedRead logs capture all touches (not just trades) — this is intentional. Non-traded touches are the control group for future feature screening.

⚠️ **Weekly review cadence:** During paper trading, review `weekly_summary.md` every Friday. Look for:
- Mean slippage trending up (liquidity issue)
- Skip rate trending up (frequency issue — signals clustering)
- Zone count diverging from historical (study stability issue)
- Losing trades clustering on news days or specific sessions

---

## Self-Check

✅ **Before starting paper trading, confirm:**
- [ ] p2_trade_details.csv extracted with all columns including MFE/MAE
- [ ] p2_trade_diagnostics.md completed (losing profiles, time-of-day, consecutive losses)
- [ ] threshold_sensitivity.md completed (near-miss analysis)
- [ ] Autotrader logs trade_log.csv with slippage and latency fields
- [ ] Autotrader logs signal_log.csv including skipped signals
- [ ] Autotrader logs microstructure_log.csv for all zone touches
- [ ] SpeedRead export added to Sierra Chart bar data (or flagged as TODO)
- [ ] Macro calendar pre-populated for Mar–Jun 2026
- [ ] Zone stability logging active from day one
- [ ] Weekly summary template created
