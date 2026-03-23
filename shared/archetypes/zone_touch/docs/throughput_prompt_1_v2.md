Throughput optimization analysis — Part 1 of 2.

The core tradeoff: longer holds capture more per trade but block 
more signals. Shorter holds capture less per trade but allow 
more trades. Which produces higher TOTAL PROFIT?

⚠️ PRIMARY DATA: P1 trades, blocked signals, and bar data.
P2 is used for CROSS-VALIDATION ONLY — noted at each section.

⚠️ DATA FILES: Before starting, generate P1 answer keys for 
BOTH exit frameworks by running the replication harness on P1 
data with the v3.0 scoring config (A-Cal threshold 16.66, 
CT 5t limit, no-overlap).

Zone-relative run:
- p1_twoleg_answer_key_zr.csv (P1 traded signals)
- p1_skipped_signals_zr.csv (P1 blocked signals)

Fixed-exit run (same signals, different exit math):
- p1_twoleg_answer_key_fixed.csv (CT 40/80/190, WT 60/80/240)
- p1_skipped_signals_fixed.csv

If these already exist, verify row counts. The qualifying 
SIGNAL list is identical (same scoring threshold), but the 
traded and blocked lists WILL DIFFER between ZR and fixed — 
different hold times produce different blocking windows, so 
a signal blocked under ZR (prior trade held 120 bars) may 
execute under fixed (prior trade held 40 bars). Each framework 
must be simulated from scratch with full sequential no-overlap 
logic. Do NOT simply recalculate PnL on the ZR trade list 
with fixed exit math — that misses the additional trades 
that faster fixed exits unlock. For P2 cross-validation, use the existing 
p2_twoleg_answer_key_zr.csv (69 trades) and 
p2_skipped_signals_zr.csv (63 blocked), plus generate 
p2_twoleg_answer_key_fixed.csv if it doesn't exist.

⚠️ P1 has a different zone width distribution from P2 (42.6% 
under 100t vs P2's 11.9%). Narrow zones resolve faster and 
produce smaller absolute moves. This is the honest development 
set — if throughput improvements work here, they generalize.

⚠️ TWO EXIT FRAMEWORKS UNDER TEST: This analysis compares 
throughput for both the current zone-relative exits AND the 
prior fixed exits. Both use identical scoring, entry, and 
no-overlap rules — only the target/stop math differs.

ZONE-RELATIVE (current):
- T1 = 0.5× zone_width (67%), T2 = 1.0× zone_width (33%)
- Stop = max(1.5× zone_width, 120t), TC = 160 bars

FIXED (prior):
- CT: T1 = 40t (67%), T2 = 80t (33%), Stop = 190t, TC = 160
- WT: T1 = 60t (67%), T2 = 80t (33%), Stop = 240t, TC = 160

Fixed exits resolve faster on wide zones (T2=80t vs T2=300t 
on a 300t zone) but capture less per trade. The throughput 
analysis determines which framework produces higher TOTAL 
profit after accounting for freed signals on both sides.

⚠️ SIMULATION RULE — "FREED SIGNALS": Throughout this prompt, 
when a trade is shortened or exited early, some previously-
blocked signals become eligible. These MUST be simulated 
SEQUENTIALLY with the same no-overlap rule: freed signal A 
trades, and while A is in position it may block freed signal B. 
Do NOT count freed signals independently — that inflates the 
benefit. Simulate the full sequential cascade for every freed 
signal estimate in every section.

⚠️ KILL-SWITCH WITHIN CASCADE: The 3-consecutive-loss halt 
applies INSIDE the freed signal simulation. If a freed signal 
loses and that is the 3rd consecutive loss (counting original 
trades + freed trades in chronological order), the session 
halts — all remaining freed signals for that day are dead. 
Without this, freed signal PnL is inflated for configs that 
produce more losses.

================================================================
SECTION 1: SIGNAL ARRIVAL PATTERNS (run first)
================================================================

⚠️ This section runs first because signal density determines 
whether faster exits can actually generate more trades. If 
signals are sparse, faster exits just create idle time.

A) Signal arrival rate on P1:
- Mean bars between qualifying signals (score >= 16.66)
- Median bars between signals
- P10 and P90 of inter-signal gap

| Hour (ET) | Qualifying signals | Trades (current) | Blocked |
|-----------|-------------------|------------------|---------|
| 06-08 | ? | ? | ? |
| 08-10 | ? | ? | ? |
| 10-12 | ? | ? | ? |
| 12-14 | ? | ? | ? |
| 14-16 | ? | ? | ? |
| 16-18 | ? | ? | ? |

B) Cluster detection: how many times do 2+ qualifying signals 
fire within 20 bars of each other?

| Cluster size | Occurrences | Signals in clusters | % of all signals |
|-------------|-------------|--------------------|-----------------| 
| 2 signals within 20 bars | ? | ? | ? |
| 3+ signals within 20 bars | ? | ? | ? |

⚠️ Clusters are where blocking costs the most. If signals are 
evenly spaced (median gap > 80 bars), faster exits yield few 
extra trades. If 40%+ arrive in clusters, fast exit during 
cluster windows could dramatically increase trade count.

C) Are blocked signals concentrated in specific hours? If 
blocking happens mostly 08-10 (morning cluster), a faster 
exit rule during that window specifically could help.

D) Blocking by zone type:

| Block type | Count | Mean score | Mean hyp PnL |
|-----------|-------|-----------|-------------|
| Same zone as current trade | ? | ? | ? |
| Different zone, same TF | ? | ? | ? |
| Different zone, different TF | ? | ? | ? |

⚠️ Same-zone blocks are unavoidable — you can't double-enter 
the same zone. Only different-zone blocks are addressable 
throughput opportunity. Report the ADDRESSABLE fraction.

**P2 cross-validation:** Run the same arrival pattern table 
and cluster detection on P2. Note if signal density differs.

📌 REMINDER: P1 is primary. P2 is cross-validation only. All 
parameter decisions are made on P1 results.

================================================================
SECTION 2: TIME-TO-PROFIT CURVES
================================================================

For each P1 traded signal, compute favorable excursion at 
every bar from entry:

MFE at bar 5, 10, 15, 20, 30, 40, 50, 75, 100, 120, 160

Report by zone width bin:

| Zone width | MFE@10 | MFE@20 | MFE@30 | MFE@50 | MFE@100 | Final MFE |
|-----------|--------|--------|--------|--------|---------|-----------|
| 50-100t | ? | ? | ? | ? | ? | ? |
| 100-150t | ? | ? | ? | ? | ? | ? |
| 150-200t | ? | ? | ? | ? | ? | ? |
| 200-300t | ? | ? | ? | ? | ? | ? |
| 300t+ | ? | ? | ? | ? | ? | ? |

Also: MFE as FRACTION of zone width at each bar:

| Zone width | MFE/ZW @10 | MFE/ZW @20 | MFE/ZW @30 | MFE/ZW @50 |
|-----------|-----------|-----------|-----------|-----------|
| 50-100t | ? | ? | ? | ? |
| 100-150t | ? | ? | ? | ? |
| 150-200t | ? | ? | ? | ? |
| 200-300t | ? | ? | ? | ? |
| 300t+ | ? | ? | ? | ? |

⚠️ Flag any bin with fewer than 8 trades as LOW SAMPLE.

**P2 cross-validation:**

| Period | Bar where MFE/ZW reaches 80% | Consistent? |
|--------|------------------------------|-------------|
| P1 | ? | baseline |
| P2 | ? | ? |

Key question: at what bar count does MFE/ZW plateau? If 80% of 
the zone-relative move is captured by bar 30, holding to bar 79 
average captures only 20% more but costs 49 bars of capacity.

⚠️ CT and WT are structurally different (CT r=-0.218, WT 
r=-0.562). Also report MFE/ZW @10, @20, @30, @50 split by 
CT vs WT (collapsed across zone width bins). If CT resolves 
in 15 bars and WT takes 60, mode-specific exit timing may 
matter more than zone width.

================================================================
SECTION 3: EARLY EXIT SIMULATIONS
================================================================

⚠️ CRITICAL: Use SEQUENTIAL freed signal simulation (see top-
of-prompt rule). Do NOT count freed signals independently.

Simulate exiting ALL positions at fixed bar counts (regardless 
of target/stop). Exit at market at bar N from entry:

⚠️ NOTE: This forces ALL trades to hold for exactly N bars — 
even trades that would naturally hit T1 at bar 5 are held to 
bar N. This overstates blocking for fast-resolving trades. 
Use this table to understand the throughput CURVE, not as a 
deployable config. Sections 4-6 test realistic exit mechanisms.

| Exit bar | Trades | Mean PnL | Total PnL | WR | Freed signals (seq sim) |
|----------|--------|---------|-----------|-----|------------------------|
| 10 bars | ? | ? | ? | ? | ? |
| 15 bars | ? | ? | ? | ? | ? |
| 20 bars | ? | ? | ? | ? | ? |
| 30 bars | ? | ? | ? | ? | ? |
| 50 bars | ? | ? | ? | ? | ? |
| 75 bars | ? | ? | ? | ? | ? |
| Current (ZR exits) | ? | ? | ? | ? | 0 |
| Fixed exits (CT 40/80/190, WT 60/80/240) | ? | ? | ? | ? | ? |

⚠️ "Freed signals" = simulate the cascade: shorten trade → 
check if any blocked signal now fits → if yes, simulate that 
trade (same bar limit) → check if IT blocks the next signal → 
continue until no more signals fit.

Then the COMBINED result:

| Exit bar | Original trades PnL | Unblocked trades PnL | TOTAL PnL | vs current | Kill-switch triggers |
|----------|--------------------|--------------------|-----------|------------|---------------------|
| 10 bars | ? | ? | ? | ? | ? |
| 15 bars | ? | ? | ? | ? | ? |
| 20 bars | ? | ? | ? | ? | ? |
| 30 bars | ? | ? | ? | ? | ? |
| 50 bars | ? | ? | ? | ? | ? |
| Current (ZR) | ? | 0 | ? | baseline | ? |
| Fixed exits + freed | ? | ? | ? | ? | ? |

⚠️ FIXED EXIT BASELINE: Use the pre-zone-relative config:
CT: T1=40t(67%), T2=80t(33%), Stop=190t, TC=160
WT: T1=60t(67%), T2=80t(33%), Stop=240t, TC=160
Same scoring, same entry, same no-overlap rule. Only the 
target/stop math differs. Run the full sequential freed signal 
simulation — fixed exits resolve faster on wide zones, so they 
may free more signals. This is the honest throughput comparison.

⚠️ Kill-switch = 3 consecutive losses. Early exits may turn 
marginal winners into losers, triggering the kill-switch more 
often. A config that looks better in raw Total PnL could look 
worse after accounting for kill-switch halts. Count how many 
times the 3-consecutive-loss trigger fires per config.

⚠️ The unblocked trades must also use zone-relative entry 
(CT 5t limit, WT market) and the same scoring filters.

**P2 cross-validation:** Run the best P1 exit bar (highest 
TOTAL PnL from combined table) on P2 data.

| Period | Best exit bar | Total PnL | vs current | Consistent? |
|--------|-------------|-----------|------------|-------------|
| P1 | ? | ? | baseline | — |
| P2 | same bar | ? | ? | ? |

📌 REMINDER: Sequential freed signal simulation. P1 primary. 
Kill-switch triggers counted for all configs.

================================================================
SECTION 4: SINGLE-LEG T1 THROUGHPUT
================================================================

What if we used T1 only (0.5x zone width, single leg, 100% 
of position)? T1 fills faster than T2, freeing capacity sooner.

A) Single-leg baseline on P1:
| Strategy | Trades | Mean hold | Mean PnL | Total PnL | Blocked | KS triggers |
|----------|--------|----------|---------|-----------|---------|-------------|
| 2-leg ZR (current) | ? | ? | ? | ? | ? | ? |
| 2-leg Fixed (CT 40/80, WT 60/80) | ? | ? | ? | ? | ? | ? |
| ZR single-leg T1 only | ? | ? | ? | ? | ? | ? |
| ZR single-leg T1 + unblocked (seq sim) | ? | ? | ? | ? | — | ? |
| Fixed single-leg T1 (CT 40t, WT 60t) | ? | ? | ? | ? | ? | ? |
| Fixed single-leg T1 + unblocked (seq sim) | ? | ? | ? | ? | — | ? |

⚠️ Fixed single-leg T1 uses CT=40t, WT=60t (same as fixed 
exit leg 1). Compare to ZR single-leg T1 = 0.5x zone width. 
On narrow zones (ZW < 100t) these are similar. On wide zones 
(ZW 300t) fixed T1=40t is much faster than ZR T1=150t.

B) T2 runner marginal value. For trades where T1 fills:
- How many bars after T1 fill does T2 resolve?
- What is T2's marginal PnL (T2 leg PnL alone)?
- How many signals were blocked AFTER T1 filled (during 
  the T2 hold period only)?
- What is the hypothetical value of those blocked signals 
  (sequentially simulated)?

Run for BOTH exit frameworks:

ZR exits (T2 = 1.0x zone width):
| Metric | All | ZW < 150t | 150-250t | 250t+ |
|--------|-----|----------|----------|-------|
| Trades where T1 filled | ? | ? | ? | ? |
| Mean bars T1 fill → T2 exit | ? | ? | ? | ? |
| Mean T2 marginal PnL | ? | ? | ? | ? |
| Signals blocked after T1 (seq sim) | ? | ? | ? | ? |
| Blocked signal value (seq sim) | ? | ? | ? | ? |

Fixed exits (T2 = 80t for both modes):
| Metric | All | ZW < 150t | 150-250t | 250t+ |
|--------|-----|----------|----------|-------|
| Trades where T1 filled | ? | ? | ? | ? |
| Mean bars T1 fill → T2 exit | ? | ? | ? | ? |
| Mean T2 marginal PnL | ? | ? | ? | ? |
| Signals blocked after T1 (seq sim) | ? | ? | ? | ? |
| Blocked signal value (seq sim) | ? | ? | ? | ? |

⚠️ KEY COMPARISON: On wide zones (250t+), fixed T2=80t should 
resolve much faster than ZR T2=250t+. If the freed signals 
from faster fixed T2 resolution exceed the PnL difference 
between T2=80t and T2=1.0x zw, fixed exits win on throughput 
for wide zones even though they capture less per trade.

⚠️ If blocked signal value > T2 marginal PnL for a zone width 
bin, the T2 runner is a bad throughput trade for that bin. This 
could mean: use single-leg T1 for narrow zones, keep 2-leg for 
wide zones (hybrid exit by zone width).

**P2 cross-validation:**

| Period | Config | 2-leg Total PnL | T1 + freed Total PnL | Winner |
|--------|--------|----------------|----------------------|--------|
| P1 | ZR | ? | ? | ? |
| P1 | Fixed | ? | ? | ? |
| P2 | ZR | ? | ? | ? |
| P2 | Fixed | ? | ? | ? |

================================================================
SECTION 5: SPEED-AT-ENTRY AS PREDICTOR
================================================================

A) Do fast-MFE trades correlate with observable features?

| Feature | Fast MFE (T1 in <15 bars) | Slow MFE (T1 in >30 bars) |
|---------|--------------------------|--------------------------|
| Mean zone width | ? | ? |
| Mean score margin | ? | ? |
| % CT | ? | ? |
| % RTH | ? | ? |
| Mean penetration speed | ? | ? |

B) Zone-width-controlled speed check. WITHIN the 150-250t bin 
only (controls for zone width), do the same features predict 
speed? If not, the "speed signal" from part A is just zone 
width in disguise.

⚠️ If zone width is the dominant predictor and nothing else 
adds information after controlling for it, skip adaptive logic 
and use zone-width-based exit selection instead.

| Feature (150-250t only) | Fast T1 (<15 bars) | Slow T1 (>30 bars) |
|------------------------|-------------------|-------------------|
| Mean score margin | ? | ? |
| % CT | ? | ? |
| % RTH | ? | ? |
| Mean penetration speed | ? | ? |

C) Adaptive time cap by predicted speed (EXPLORATORY):
- Fast bounce predicted → TC=50, single-leg T1 only
- Slow bounce predicted → TC=160, 2-leg T1+T2

⚠️ This is exploratory — we're looking for whether speed is 
predictable at entry BEYOND zone width, not committing to 
adaptive logic. If only zone width predicts speed, the simpler 
approach is zone-width-based exit (Section 4B already covers).

**P2 cross-validation:** Run the same feature tables on P2. 
Note if the fast/slow split is consistent across periods.

📌 REMINDER: P1 is primary. Kill-switch column in all summary 
tables. Sequential simulation for freed signals everywhere.

================================================================
SECTION 6: STOP TIGHTENING FOR THROUGHPUT
================================================================

Zone-relative stop = max(1.5x zw, 120). For wide zones this is 
300-450t. A stopped trade at -450t takes a long time to resolve 
AND blocks signals AND produces the worst outcome.

A) Full-position stop tightening:

| Stop | Trades stopped | Bars saved | Freed signals (seq sim) | Net PnL (incl freed) | KS triggers |
|------|---------------|-----------|------------------------|---------------------|-------------|
| max(1.5x, 120) ZR current | ? | 0 | 0 | ? | ? |
| max(1.0x, 100) | ? | ? | ? | ? | ? |
| max(0.75x, 80) | ? | ? | ? | ? | ? |
| Fixed 120t for all | ? | ? | ? | ? | ? |
| Fixed 80t for all | ? | ? | ? | ? | ? |
| Fixed exits (CT 190t, WT 240t) | ? | ref | ref | ? | ? |

B) T2-leg-only stop tightening (AFTER T1 fills). This is a 
distinct mechanism: once T1 fills (67% banked), tighten the 
stop on the remaining 33% runner to free capacity faster 
while preserving the T1 profit.

| T2 stop (after T1 fills) | T2 trades stopped | Bars saved | Freed signals (seq sim) | Net PnL | KS triggers |
|-------------------------|------------------|-----------|------------------------|---------|-------------|
| Original stop (current) | ? | 0 | 0 | ? | ? |
| max(1.0x, 100) | ? | ? | ? | ? | ? |
| Entry (breakeven T2) | ? | ? | ? | ? | ? |
| T1 price (lock profit) | ? | ? | ? | ? | ? |

📌 REMINDER: Both exit frameworks (ZR and fixed) are being 
compared throughout. Sequential freed signal simulation with 
kill-switch inside the cascade. P1 primary.

C) FULL-POSITION BE STEP-UP UNDER ZONE-RELATIVE. Prior exit 
investigation rejected BE under fixed exits — 94% reached 
target and losers failed early (MFE < 40t). But under ZR, 
wide zones have T1=150t+ and trades spend more time in 
favorable territory before resolving. The "losers fail early" 
pattern may not hold for wide zones under ZR.

⚠️ Use Section 2 MFE curves to inform interpretation. If wide-
zone trades show a "moves 80-120t favorable then reverses" 
population, that's the BE opportunity. If losers still fail 
early (MFE < 0.25x zw before reversing), BE is confirmed 
unnecessary under ZR as well.

Test: after MFE reaches trigger level, move stop to entry 
(breakeven). This applies to the FULL position (both legs), 
not just T2.

| BE trigger | Trades where BE fires | Stopped at BE (0 PnL) | Hit T1/T2 target | Net PnL change | Bars saved vs stop | Freed signals (seq sim) | KS triggers |
|-----------|----------------------|----------------------|------------------|----------------|-------------------|------------------------|-------------|
| No BE (current) | — | — | — | — | 0 | 0 | ? |
| MFE > 0.25x zw | ? | ? | ? | ? | ? | ? | ? |
| MFE > 0.33x zw | ? | ? | ? | ? | ? | ? | ? |
| MFE > 0.5x zw (= T1 level) | ? | ? | ? | ? | ? | ? | ? |

⚠️ "Bars saved vs stop" = for trades that hit BE instead of 
the original stop, how many fewer bars were they in position? 
This is the throughput benefit of BE — faster resolution on 
trades that would otherwise hold to stop.

Split by zone width bin:

| BE trigger = 0.25x zw | ZW < 150t | 150-250t | 250t+ |
|-----------------------|----------|----------|-------|
| Trades where BE fires | ? | ? | ? |
| Stopped at BE | ? | ? | ? |
| Net PnL change vs no-BE | ? | ? | ? |
| Freed signals (seq sim) | ? | ? | ? |

⚠️ KEY QUESTION: Does BE help specifically on wide zones 
(250t+) where it was untested under fixed exits? If BE 
improves wide zones but hurts narrow zones, it becomes a 
zone-width-conditional rule (another hybrid candidate for 
Prompt 2 Section 11).

D) RISK PROFILE BY STOP LEVEL. Beyond throughput, tighter stops 
reduce tail risk. The daily kill-switch is -600t and weekly is 
-1200t. A single 450t stop (1.5x on a 300t zone) consumes 75% 
of the daily budget.

| Stop config | Max single trade loss | Worst-case 2-trade daily loss | % daily budget (-600t) | Max drawdown | P95 adverse excursion |
|------------|----------------------|------------------------------|----------------------|-------------|---------------------|
| max(1.5x, 120) ZR current | ? | ? | ? | ? | ? |
| max(1.0x, 100) | ? | ? | ? | ? | ? |
| max(0.75x, 80) | ? | ? | ? | ? | ? |
| Fixed 120t for all | ? | ? | ? | ? | ? |
| Fixed exits (CT 190t, WT 240t) | ? | ? | ? | ? | ? |

⚠️ Rows 1-4 use ZR targets (T1=0.5x, T2=1.0x) with varied 
stops. Row 5 is the complete fixed-exit package (different 
targets AND stops). This is intentional — row 5 answers "what 
is the risk profile of the prior config as a whole?"

⚠️ "Worst-case 2-trade daily loss" = two consecutive stopped 
trades in one day. This is the scenario that blows through the 
-600t daily kill-switch. If a stop config keeps this under 600t, 
the kill-switch always fires before the 2nd stop completes.

⚠️ A stop config with lower total PnL but dramatically lower 
max drawdown and daily budget exposure may be preferable for 
live deployment. Flag any config where max single loss exceeds 
50% of the -600t daily kill-switch as HIGH EXPOSURE.

⚠️ T2-only tightening never kills T1 winners — T1 is already 
banked. It only risks cutting the runner short. This should be 
a pure throughput improvement with minimal PnL cost. If the 
freed signals compensate for lost T2 upside, this is ACTIONABLE.

**P2 cross-validation:** Run the best P1 tighter stop config 
on P2.

| Period | Current stop PnL | Tighter stop + freed PnL | Winner |
|--------|-----------------|-------------------------|--------|
| P1 | ? | ? | ? |
| P2 | ? | ? | ? |

================================================================
SECTION 7: OPTIMAL THROUGHPUT CONFIGURATION
================================================================

From Sections 1-6, identify the configuration that maximizes 
TOTAL P1 PROFIT:

| Config | Trades | Mean PnL | Total PnL | Mean hold | Max DD | Max single loss | KS triggers |
|--------|--------|---------|-----------|----------|--------|----------------|-------------|
| Current ZR 2-leg | ? | ? | ? | ? | ? | ? | ? |
| Fixed exits (CT 40/80/190, WT 60/80/240) | ? | ? | ? | ? | ? | ? | ? |
| Fixed exits + freed | ? | ? | ? | ? | ? | ? | ? |
| Best fixed bar exit | ? | ? | ? | ? | ? | ? | ? |
| ZR single-leg T1 + freed | ? | ? | ? | ? | ? | ? | ? |
| Fixed single-leg T1 + freed | ? | ? | ? | ? | ? | ? | ? |
| Best tighter stop (full) | ? | ? | ? | ? | ? | ? | ? |
| Best T2-only stop tighten | ? | ? | ? | ? | ? | ? | ? |
| Best BE step-up (full position) | ? | ? | ? | ? | ? | ? | ? |
| Best combined | ? | ? | ? | ? | ? | ? | ? |

⚠️ Fixed exits are the throughput benchmark — they resolve 
faster on wide zones. If ZR still wins after accounting for 
throughput on both sides, zone-relative is confirmed superior.

⚠️ "Best combined" = cherry-picked from each section on P1. 
Flag as OVERFITTED CEILING — this is the upper bound, not 
a deployable config.

📌 FINAL REMINDER: Sequential freed signal simulation was used 
throughout. P1 was the primary data set. All configs include 
kill-switch trigger counts.

**P2 cross-validation summary:**

| Config | P1 Total PnL | P2 Total PnL | P1 KS | P2 KS | Consistent? |
|--------|-------------|-------------|-------|-------|-------------|
| Current ZR 2-leg | ? | ? | ? | ? | baseline |
| Fixed exits + freed | ? | ? | ? | ? | ? |
| Best P1 fixed bar exit | ? | ? | ? | ? | ? |
| ZR single-leg T1 + freed | ? | ? | ? | ? | ? |
| Fixed single-leg T1 + freed | ? | ? | ? | ? | ? |
| Best P1 tighter stop | ? | ? | ? | ? | ? |
| Best P1 T2-only tighten | ? | ? | ? | ? | ? |
| Best P1 BE step-up | ? | ? | ? | ? | ? |

⚠️ Any config that beats current on P1 but NOT on P2 is 
likely overfitted to P1's narrow-zone-heavy distribution. 
Only configs that beat current on BOTH periods are ACTIONABLE.

⚠️ Any config that increases kill-switch triggers by >50% 
vs current, even if Total PnL is higher, should be flagged 
as HIGH VARIANCE — the PnL improvement may not survive 
real-time sequencing.

Classify each finding:
- ACTIONABLE: beats current on both P1 and P2, KS triggers stable
- PROMISING: beats on P1, needs P2 confirmation (mixed)
- MONITOR: marginal improvement, track during paper trading
- NOT VIABLE: tested, doesn't help on either period

⚠️ Do NOT freeze any new exit config from this prompt. 
Throughput Part 2 (dynamic T2 exit) may alter the optimal 
config. Section 7 identifies candidates only — the final 
decision comes after Part 2.

Save results to throughput_analysis_part1.md.
