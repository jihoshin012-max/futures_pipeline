# Zone Break Strategy — Discovery Seeds

Collected from zone bounce exit investigation (P2, 312 trades).
These findings describe how zones FAIL — the inverse of the bounce
strategy. Each seed is a potential entry signal or filter for the
break strategy.

Status: COLLECTION PHASE. Do not build until bounce autotrader
is paper trading.

last_reviewed: 2026-03-23

---

## Failure Mode 1: Fast Blowouts (150t+ MAE)
- Price drives through zone at 9.6+ t/bar (pen_speed_10bar)
- 100% hit stop
- 88% reach 100t adverse (vs 46% of winners)
- Losers reach 25t adverse in 4.8 bars (vs 16.3 for winners)
- Concentrated in WT mode
- Source: Part 2 Section 3A

## Failure Mode 2: Slow Drifters (50-150t MAE)
- Price penetrates at 1.7 t/bar (battleground only)
- Shallow bounces that fail to hold — all trades bounce by close,
  but the bounces don't persist (repeated bounce-fail pattern)
- All exit via timecap (120 bars, never hit stop or target)
- MFE never reaches T1 for WT losers (0% at all bar checkpoints)
- 100% are PRIOR_HELD cascade state
- 100% are RTH session
- Only 3 unique touch events replicated across modes (low confidence)
- Source: Part 1 Section 1B, Part 2 Section 3D

## Failure Signal: Opposite Edge Cross
- 28.1% of losers cross opposite zone edge vs 4.6% of winners
- 6x stronger predictor of failure than success
- By the time cross happens, 113-127t adverse already
- Exiting at edge+25t: catches 9 losses, kills 6 winners (PF 3.35)
- Source: Part 2 Section 3C

## Failure Signal: MFE Trajectory
- Losers show flat MFE growth (31.4t at bar 10 vs 69.4t for winners)
- WT losers NEVER reach T1 at 60t (0% at bars 10, 20, 30, 50, 100)
- Winners at 61% T1 by bar 10, 80% by bar 20
- If MFE < 20t by bar 20, likely a loser
- CT losers eventually reach T1 (56% by bar 10) but via mean reversion,
  not directional conviction — MFE flat at 182t by bar 50, same as winners
- Source: Part 2 Section 3E

## Failure Signal: Penetration Speed
- Blowout losers: 9.6 t/bar at bar 10 (2.3x winner rate of 4.1 t/bar)
- Drifter losers: 1.7 t/bar (battleground subset only)
- Best speed rule: 100t in 10 bars catches 41% of losers at 3% false positive
- Speed alone doesn't cleanly separate (overlapping distributions)
- Source: Part 2 Section 3A-B

## Structural Weakness: ETH Session
- ETH: PF 1.49, stop rate 17.6%, mean MAE 77.8t
- RTH: PF 5.81, stop rate 4.2%, mean MAE 62.6t
- ETH is where the strategy is weakest — zone breaks may be
  more tradeable in ETH than bounces
- Source: Part 3 Section 5B

## Structural Weakness: Cascade State
- NO_PRIOR: 97% WR, 3% stop rate (zones are fresh)
- PRIOR_HELD: 88% WR, 8% stop rate (zones holding but weakening)
- PRIOR_BROKE: 84% WR, 16% stop rate (zones already cracked)
- PRIOR_BROKE zones fail 5x more than NO_PRIOR — the prior break
  weakened the zone structurally
- Source: Part 3 Section 5D

## Structural Weakness: Low Timeframe
- 15m/30m zones carry ALL the losses (stop rate 9-12%)
- 60m+ zones: 0% stop rate, 100% WR (n=91)
- LTF zones are weaker — LTF break signals may have higher conviction
- Source: Part 3 Section 5E

## WT Structural Weakness
- WT losers never reach T1 (0% at all bar checkpoints)
- WT has 16% stop rate in PRIOR_BROKE state
- When WT fails, it fails fast — good break signal candidate
- Source: Multiple sections

## Narrow Zone Weakness
- 50-100t zones: 72.7% WR (worst bin)
- Zone-relative stops help (PF 1.42 fixed vs 4.77 zone-relative)
  but still the weakest population
- Too narrow for the bounce to develop fully
- Narrow zone break could be more tradeable than narrow bounce
- Source: Part 1 Section 2, Part 3 Section 5F

## Score Margin Interaction
- Margin 0-2 with 150t+ MAE: 35% WR, PF 0.2 (n=34) — this is the
  primary loss population (low-confidence zone, deep penetration)
- Margin 2+ with any MAE: near-100% WR across all depths
- Low margin is the enabling condition; depth is the outcome
- Source: Part 3 Section 5A

## Threshold Cliff — Model Fragility
- Lowering A-Cal threshold by 1pt (16.66 → 15.66): PF drops 46%
  (5.10 → 2.76), 77 trades instead of 58
- Lowering by 2pt (→ 14.66): PF drops 62% (→ 1.92), 121 trades
- The threshold is load-bearing — below-threshold touches are
  structurally different, not just slightly weaker
- Near-miss inventory: 266 P1 + 269 P2 touches in [T-2, T] range
- Break implication: near-miss touches (scored just below threshold)
  are a large population of "almost bounce-worthy" zones — their
  breaks may have different character than garbage-zone breaks
- Source: near_miss_analysis.md

## 15m Timeframe Overweight in Losers
- 57% of losing trades (4/7 in seg3 winner) were 15m zones
  vs 41% of winner trades
- 15m zones are noisier — more false touches, less structural
- 15m + 30m carry ALL stop losses (9-12% stop rate)
- 60m+ zones: zero stops across 91 trades
- Break implication: 15m zone breaks may be just noise, not
  signal. HTF zone breaks (60m+) that overcome a strong zone
  are higher conviction.
- Source: losing_trade_profiles.md, Part 3 Section 5E

## SBB Population — Ready-Made Break Candidates
- 1,411 SBB touches in P1 baseline (34% of all touches)
- SBB baseline PF: 0.37 — zones broke on the same bar they were
  touched, before any bounce could develop
- The bounce winner perfectly filters these out (0% SBB leak)
- These are NOT low-quality zones — they are zones that faced
  momentum they couldn't hold. The momentum IS the signal.
- Break implication: SBB touches are the purest break population.
  Entry after SBB confirmation (price continues past zone) could
  capture the momentum that defeated the zone.
- Source: feature_analysis_clean.md

## ETH Hour-Level Weakness
- Hour 07:00: 50% WR (1 loss in 2 trades)
- Hour 14:00: 85% WR, mean PnL only 49.8t vs 77t baseline
  (2 losses, highest loss count of any hour)
- Hour 18:00: 50% WR (1 loss in 2 trades)
- All 3 fast STOP losses in P2 occurred in ETH
- Break implication: ETH zone failures cluster around session
  transitions (18:00 globex open, 07:00 pre-RTH). These are
  periods of structural regime change — zones from prior session
  may not hold in new session context.
- Source: time_of_day_distribution.md

## High Prior Penetration Correlates with Loss
- Losing trades had mean F10_PriorPenetration of 189t vs
  ~100-150t range for winners
- 6/7 losers (86%) were PRIOR_HELD cascade state
- A zone that previously experienced deep penetration (but held)
  is weaker on retest — the prior penetration damaged it
- Break implication: zones with high prior penetration that are
  re-tested may be more likely to break on the next touch.
  F10 > 220t (top bin boundary) could be a break filter.
- Source: losing_trade_profiles.md

## Consecutive Loss Ceiling — Risk Management Baseline
- Max consecutive losses in P2: 1 (never reached 2+)
- Longest drawdown duration: 222 bars (~5 calendar days)
- Max single-trade DD: 193 ticks per contract
- Kill-switch recommendation: 3 consecutive losses (1-trade
  buffer beyond observed worst case)
- Break implication: if break strategy is deployed alongside
  bounce, combined consecutive loss tracking is needed. A
  bounce loss followed by a break loss on the same zone is
  a correlated event.
- Source: consecutive_loss_analysis.md

## VP Ray Feature — Permanently Lost for Historical Analysis
- Sierra Chart purges per-bar VAP data after retention period
- 100% of P1 VP data is stale; 97.7% of P2 VP data is stale
- VP features (F19, F20) correctly excluded from winner model
- Cannot fix retroactively — only forward-looking VP data valid
- Break implication: VP ray proximity (volume node at zone edge)
  could be a break confirmation signal, but can only be tested
  on live/paper data, not historical backtest.
- Source: VP_RAY_INVESTIGATION.md

## Candidate Break Entry Populations
- SBB touches (1,411 in P1) — zone broke on same bar it was
  touched. These never had a chance to bounce. Largest and
  purest break population.
- Bounce near-miss touches (266 P1, 269 P2 within 2pts below
  threshold) — scored too low for bounce but zone was engaged.
  These are "almost good enough" zones that failed.
- High-penetration bounce losers — entered as bounce, failed.
  Break entry would be the reversal of the bounce position.
- Touches on PRIOR_BROKE zones at LTF (15m/30m) in ETH —
  highest failure rate combination in the bounce data.
- NORMAL-filtered but below-threshold touches — zones that
  pass SBB filter but fail scoring. PF 1.33 in this population
  means some do bounce, but the edge is thin.

## Inverted Features (from bounce findings)
- Bounce: high score = good. Break: low score margin = zone weak?
  (Confirmed: margin 0-2 with 150t+ MAE = 35% WR, PF 0.2)
- Bounce: PRIOR_HELD = good. Break: PRIOR_BROKE = cascade exhaustion
  (16% stop rate vs 3% for NO_PRIOR — confirmed)
- Bounce: low F10 penetration = good. Break: high F10 (>220t) =
  zone already damaged by prior deep penetration?
- Bounce: CT mode stronger. Break: WT mode fails faster =
  better break signal? (WT losers never reach T1)
- Bounce: 60m+ TF perfect. Break: 15m/30m TF = zone too weak
  to hold? (All stops in 15m/30m)
- Bounce: high F21_ZoneAge = bad. Break: old zones (>831 bars)
  may have decayed — zone age as break predictor?

## Open Questions
1. What distinguishes the breaks that DON'T reverse?
   (Need to study SBB population directly, not just bounce losers)
2. Does the break direction (up through supply vs down through
   demand) matter?
3. Is there a time-of-day pattern for zone failures beyond
   the RTH/ETH split? (Hour 14:00 and session transitions
   are initial signals — need larger sample)
4. Do HTF zone breaks produce bigger follow-through than LTF?
   (60m+ zones never fail as bounces — when they DO break,
   is it more significant?)
5. Can MFE trajectory in first 10 bars predict break vs bounce
   in real-time? (WT: 0% T1 reach is strong, CT: less clear)
6. What is the fill rate and slippage profile for break entries
   vs bounce entries? Breaks may move fast, making limit fills
   harder.
7. Does the zone-width-relative framework apply to breaks?
   (Break targets could scale with zone width)
8. Is the SBB population (PF 0.37 for bounce) above 1.0 PF
   when traded as breaks? This is the first thing to test.
9. Does combining SBB + PRIOR_BROKE + 15m TF identify a
   high-conviction break subset?
10. What is the mean follow-through (in ticks) after a zone
    breaks? Is it proportional to zone width?
