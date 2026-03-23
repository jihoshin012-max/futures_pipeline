Throughput optimization analysis — Part 2 of 2.

PREREQUISITE: Part 1 complete (throughput_analysis_part1.md).
Use the same data files as Part 1.

⚠️ PRIMARY DATA: P1 (~121 trades + blocked signals + bar data).
P2 is used for CROSS-VALIDATION ONLY.

⚠️ SIMULATION RULE — "FREED SIGNALS": Same rule as Part 1. 
When a trade is shortened or exited early, freed signals MUST 
be simulated SEQUENTIALLY with the no-overlap rule. Do NOT 
count freed signals independently. The 3-consecutive-loss 
kill-switch applies INSIDE the cascade — if a freed signal 
is the 3rd consecutive loss, the session halts and remaining 
freed signals for that day are dead.

⚠️ Load throughput_analysis_part1.md BEFORE STARTING. Sections 
8, 9, and 11 reference specific Part 1 findings (S6B, S1, S4B, 
S6C). Section 12 compiles both parts into a single summary.

⚠️ P1 COMPOSITION BIAS — READ BEFORE INTERPRETING: Part 1 
found "current ZR 2-leg is near-optimal" but this conclusion 
is shaped by P1's zone width distribution (42.6% narrow zones 
under 100t). Key implications:

1. P1 signal density was SPARSE (194-bar median gap). Only 10 
   extra trades were unlocked by faster fixed exits (130 vs 120). 
   But P2 had 69 trades in a shorter window — higher density. 
   Signal sparsity may be P1-specific.

2. On P1, narrow zones dilute the throughput signal because ZR 
   and fixed exits perform similarly on them. The throughput 
   cost concentrates on WIDE zones — and P1 has fewer of them.

3. The forced 75-bar exit beat current by +38% on P2 (10,441 
   vs 7,564) but only +8% on P1. P2 is 88% over 100t. This 
   suggests throughput improvements matter MORE when the zone 
   width distribution is wider.

4. Paper trading (P3, Mar-Jun 2026) zone width distribution is 
   unknown. If it resembles P2, throughput matters. If it 
   resembles P1, current config is fine.

CONSEQUENCE FOR PART 2: For findings that are zone-width-
dependent (Sections 10, 11 especially), weigh P2 cross-
validation results MORE HEAVILY than normal. A mechanism that 
shows marginal improvement on P1 but strong improvement on P2 
for wide zones should be classified PROMISING, not NOT VIABLE. 
The conservative P1 result may be understating the opportunity.

================================================================
SECTION 8: WINNER VS LOSER RESOLUTION SPEED
================================================================

⚠️ Losers that take long to resolve are the worst throughput 
outcome: lose money AND block signals.

Using P1 data:

| Metric | Winners | Losers |
|--------|---------|--------|
| Mean bars held | ? | ? |
| Median bars held | ? | ? |
| Mean bars to T1 (winners) | ? | — |
| Mean bars to stop (losers) | — | ? |
| Mean bars to timecap (if TC exit) | — | ? |
| Signals blocked per trade | ? | ? |
| Blocking cost (blocked × mean signal EV) | ? | ? |

Per-loser detail (list all P1 losers):
| trade_id | bars_held | PnL | zone_width | signals_blocked | blocked_value |

Are losers disproportionately expensive in throughput terms?

⚠️ Compare to Part 1 Section 6B (T2-only stop tightening). 
Would tighter stops SPECIFICALLY on trades that are losing 
(real-time adverse excursion rule) improve total PnL more 
than blanket tighter stops on all trades?

Test: at EACH BAR progressively, check if running adverse 
excursion exceeds threshold AND bar count exceeds minimum. 
Exit at market the FIRST bar both conditions are true 
simultaneously. This is a real-time rule — do NOT compute 
final MAE retroactively.

| Rule | Losers caught | Winners killed | Freed signals (seq sim) | Net PnL (incl freed) | Bars freed | KS triggers |
|------|--------------|---------------|------------------------|---------------------|-----------|-------------|
| No rule (current) | — | — | 0 | — | — | ? |
| Running AE > 0.75x zw + bar > 20 | ? | ? | ? | ? | ? | ? |
| Running AE > 1.0x zw + bar > 15 | ? | ? | ? | ? | ? | ? |
| Running AE > 0.5x zw + bar > 30 | ? | ? | ? | ? | ? | ? |

📌 REMINDER: P1 primary. Sequential freed signal simulation. 
Kill-switch triggers counted.

================================================================
SECTION 9: SIGNAL CLUSTERING AND THROUGHPUT WINDOWS
================================================================

⚠️ This section builds on Part 1 Section 1 (signal arrival 
patterns). Use the cluster data from Part 1 to test whether 
exit behavior should adapt to signal density.

A) For each P1 trade, compute: "next qualifying signal arrives 
in N bars." Split into:

| Next signal gap | Count | Mean bars_held (current) | Mean signals blocked |
|----------------|-------|------------------------|---------------------|
| < 15 bars | ? | ? | ? |
| 15-30 bars | ? | ? | ? |
| 30-60 bars | ? | ? | ? |
| > 60 bars | ? | ? | ? |

⚠️ If the "< 15 bars" group blocks the most signals AND those 
blocked signals are high quality, that's the strongest case 
for dynamic exits during cluster windows.

B) Could we identify cluster windows in real-time? A cluster 
window = 3+ qualifying signals within 30 bars. During a 
cluster window, should exits be tightened?

This is OBSERVATIONAL — report the data, don't implement yet.

================================================================
SECTION 10: DYNAMIC T2 EXIT ON NEW SIGNAL
================================================================

⚠️ This is the most promising throughput mechanism — it only 
sacrifices the runner (33%) and only when a new opportunity 
appears.

Test on P1 data: when a qualifying signal fires while in 
position AND T1 has already filled (only runner remains) AND 
the signal is from a DIFFERENT zone, close T2 runner at market 
and enter the new signal per normal rules.

Rules:
- T1 must have already filled (only 33% runner remains)
- New signal must be a DIFFERENT zone (same-zone retouches 
  remain blocked regardless)
- Close T2 at current market price (take whatever PnL exists)
- New CT signal: place 5t limit (may take bars to fill)
- New WT signal: market at next bar open
- If T1 has NOT filled yet, keep current blocking rule

⚠️ UNFILLED CT LIMIT HANDLING: If the new signal is CT and the 
5t limit EXPIRES (does not fill within 20-bar fill window), 
you've given up the T2 runner for nothing. Track these cases:

| Metric | Current | Dynamic T2 exit |
|--------|---------|----------------|
| Total trades | ? | ? |
| T2 early closes triggered | — | ? |
| Mean T2 PnL on early close | — | ? |
| Mean T2 PnL if held (what we gave up) | — | ? |
| New signal trades taken | — | ? |
| New signal CT limit EXPIRED (no fill) | — | ? |
| Net cost of expired CT limits | — | ? |
| New signal WR | — | ? |
| New signal total PnL | — | ? |
| NET total PnL | ? | ? |
| Kill-switch triggers | ? | ? |

⚠️ "Net cost of expired CT limits" = sum of (T2 PnL given up) 
for cases where the CT replacement did not fill. This is the 
pure downside of the mechanism. If this exceeds 5% of total 
PnL, the mechanism needs a CT-specific gate (only flatten T2 
for WT replacements, or only flatten if CT is already within 
5t of the zone edge at signal time).

Break down by whether the early-closed T2 was profitable or not:

| T2 status at close | Count | Mean T2 early PnL | New signal PnL |
|-------------------|-------|-------------------|----------------|
| T2 was profitable | ? | ? | ? |
| T2 was at loss | ? | ? | ? |

📌 REMINDER: Sequential simulation. The new trade from dynamic 
T2 exit may itself block further signals — simulate the full 
cascade.

**P2 cross-validation:**

| Period | Current Total PnL | Dynamic T2 Total PnL | Winner | KS triggers |
|--------|-------------------|---------------------|--------|-------------|
| P1 | ? | ? | ? | ? |
| P2 | ? | ? | ? | ? |

================================================================
SECTION 11: HYBRID EXIT STRATEGY
================================================================

⚠️ This section tests whether different zone width bins should 
use different exit strategies — combining the best findings 
from all prior sections.

Based on Part 1 Section 4B (T2 marginal value by zone width), 
test a hybrid:

Candidate hybrid rules (test each):

HYBRID A: Zone-width-based exit selection
- ZW < 150t → single-leg T1 only (0.5x zw target)
- ZW 150-250t → 2-leg current (0.5x/1.0x)
- ZW 250t+ → 2-leg current (0.5x/1.0x)

HYBRID B: Zone-width + dynamic T2
- ZW < 150t → single-leg T1 only
- ZW 150t+ → 2-leg with dynamic T2 exit (Section 10 rules)
- ⚠️ If Section 10 was classified NOT VIABLE, skip Hybrid B 
  and note "not testable — depends on Section 10"

HYBRID C: T2-tightened for narrow + current for wide
- ZW < 150t → 2-leg but T2 stop at entry (breakeven runner)
- ZW 150t+ → 2-leg current

HYBRID D: BE step-up for wide + current for narrow
- ZW < 150t → 2-leg current (no BE — prior analysis showed 
  narrow zone losers fail early, BE doesn't help)
- ZW 150t+ → 2-leg with BE at best trigger from Part 1 S6C
- ⚠️ If Part 1 S6C found BE NOT VIABLE across all zone width 
  bins, skip Hybrid D and note "not testable — BE rejected"

| Config | Trades | Total PnL | Mean hold | Freed trades | Max DD | Max single loss | KS triggers |
|--------|--------|-----------|----------|-------------|--------|----------------|-------------|
| Current uniform ZR 2-leg | ? | ? | ? | 0 | ? | ? | ? |
| Hybrid A | ? | ? | ? | ? | ? | ? | ? |
| Hybrid B | ? | ? | ? | ? | ? | ? | ? |
| Hybrid C | ? | ? | ? | ? | ? | ? | ? |
| Hybrid D | ? | ? | ? | ? | ? | ? | ? |

⚠️ The zone width cutoff (150t) is a starting point. If the 
data suggests a different cutoff, report it. But do NOT sweep 
multiple cutoffs — that's overfitting on P1.

**P2 cross-validation:** Run the best P1 hybrid on P2.

| Period | Hybrid | Total PnL | vs current | Consistent? |
|--------|--------|-----------|------------|-------------|
| P1 | best | ? | ? | baseline |
| P2 | same | ? | ? | ? |

================================================================
SECTION 12: COMBINED THROUGHPUT SUMMARY
================================================================

⚠️ Confirm throughput_analysis_part1.md is loaded (per preamble 
instruction). Combine Parts 1 and 2 findings into a single 
comparison.

All results on P1 (primary):

| Strategy | Mechanism | Trades | Total PnL | vs Current | Max DD | Max single loss | KS triggers | Complexity |
|----------|-----------|--------|-----------|------------|--------|----------------|-------------|------------|
| Current ZR 2-leg | baseline | ? | ? | — | ? | ? | ? | current |
| Fixed exits + freed (Part 1 S3) | fixed T/S, throughput | ? | ? | ? | ? | ? | ? | low |
| Best fixed bar exit (Part 1 S3) | early exit all | ? | ? | ? | ? | ? | ? | low |
| ZR single-leg T1 + freed (Part 1 S4) | drop ZR T2 | ? | ? | ? | ? | ? | ? | low |
| Fixed single-leg T1 + freed (Part 1 S4) | drop fixed T2 | ? | ? | ? | ? | ? | ? | low |
| Full tighter stops + freed (Part 1 S6A) | faster loss resolution | ? | ? | ? | ? | ? | ? | low |
| T2-only tighter stops (Part 1 S6B) | faster T2 resolution | ? | ? | ? | ? | ? | ? | low |
| BE step-up full position (Part 1 S6C) | move stop to entry | ? | ? | ? | ? | ? | ? | low |
| Adverse excursion exit (S8) | conditional early exit | ? | ? | ? | ? | ? | ? | medium |
| Dynamic T2 exit (S10) | signal-triggered T2 close | ? | ? | ? | ? | ? | ? | medium |
| Best hybrid (S11) | zone-width-based | ? | ? | ? | ? | ? | ? | medium |
| Best combined from all | cherry-picked | ? | ? | ? | ? | ? | ? | varies |

⚠️ "Best combined" is the OVERFITTED CEILING — cherry-picked 
on P1. Not deployable without P2 confirmation.

⚠️ Max single loss matters for deployment. A config with 5% 
less total PnL but 50% lower max single loss may be preferable. 
Flag any config where max single loss > 300t (-600t daily 
budget / 2 trades) as HIGH EXPOSURE.

📌 FINAL CHECK: Sequential freed signal simulation was used 
throughout. P1 was the primary data set. All configs include 
kill-switch trigger counts.

**P2 cross-validation summary:**

| Config | P1 Total PnL | P2 Total PnL | P1 KS | P2 KS | Consistent? |
|--------|-------------|-------------|-------|-------|-------------|
| Current ZR 2-leg | ? | ? | ? | ? | baseline |
| Fixed exits + freed | ? | ? | ? | ? | ? |
| Best fixed bar exit | ? | ? | ? | ? | ? |
| ZR single-leg T1 + freed | ? | ? | ? | ? | ? |
| Fixed single-leg T1 + freed | ? | ? | ? | ? | ? |
| T2-only tighter stops | ? | ? | ? | ? | ? |
| BE step-up | ? | ? | ? | ? | ? |
| Dynamic T2 exit | ? | ? | ? | ? | ? |
| Best hybrid | ? | ? | ? | ? | ? |

⚠️ Any config that beats current on P1 but NOT on P2 is 
likely overfitted to P1's narrow-zone-heavy distribution.

⚠️ ASYMMETRIC BIAS (see preamble): A config that is MARGINAL 
on P1 but STRONG on P2 may be undervalued by P1's narrow-zone 
composition. For zone-width-dependent mechanisms (dynamic T2, 
hybrids), if P2 shows >15% improvement over baseline while P1 
shows <5%, classify as PROMISING not NOT VIABLE. P1's sparse 
signals and narrow-zone dominance suppress the throughput 
benefit that wider-distribution data reveals.

⚠️ Any config that increases KS triggers by >50% vs current, 
even if Total PnL is higher, flag as HIGH VARIANCE.

Classify each finding:
- ACTIONABLE: beats current on both P1 and P2, KS stable
- PROMISING: beats on P1, P2 mixed — OR marginal on P1 but 
  strong on P2 for zone-width-dependent mechanisms (see bias note)
- MONITOR: marginal improvement, track during paper trading
- NOT VIABLE: tested, doesn't help on either period

FINAL RECOMMENDATION: State the single recommended exit config 
for the C++ standalone test mode build. If "current ZR 2-leg" 
wins, state that explicitly — the throughput analysis confirmed 
the existing config is optimal and no changes are needed.

If a new config wins, specify the EXACT parameters:
- T1 multiplier, T2 multiplier (if applicable), stop multiplier
- Any zone-width-based routing rules
- Dynamic T2 exit rules (if applicable)
- Time cap
- Stop level and whether it's zone-relative or fixed

⚠️ If the top Total PnL config has HIGH EXPOSURE on max single 
loss, also state the best RISK-ADJUSTED config (highest Total 
PnL among configs where max single loss ≤ 300t). The final 
decision between max PnL and risk-adjusted is the trader's 
call, but present both options with the tradeoff quantified.

Save results to throughput_analysis_part2.md.
