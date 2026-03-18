# Lessons & Build Constraints

Cross-session learnings and forward constraints. Review at session start and before major refactors.

---

## Phase 7 — hypothesis_generator.py Build Constraints

Recorded: 2026-03-14 (during Phase 01.2 execution)
Source: period_config.md replication gate redesign

### CONSTRAINT 1 — P1a/P1b boundaries from data_manifest.json
hypothesis_generator.py must read P1a/P1b start/end dates from data_manifest.json.
Stage 01 computes and writes these from p1_split_rule in period_config.md.
Do not hardcode dates in Python.

### CONSTRAINT 2 — Gate behaviour must be runtime-configurable
Read replication_gate from data_manifest.json. Apply:
- replication_pass true → proceed
- replication_pass false + hard_block → verdict: NO
- replication_pass false + flag_and_review → verdict: WEAK_REPLICATION, log flag, do not auto-block, surface for human review
- n_trades_p1b < 15 → replication_pass: inconclusive, always flag_and_review regardless of gate setting

### CONSTRAINT 3 — Result JSON must include replication_gate field
So results_master.tsv and dashboard can show which gate was active when each verdict was produced.

### Done check (at Phase 7 build time)
- [ ] Set replication_gate: hard_block, force P1b fail → verdict: NO
- [ ] Set replication_gate: flag_and_review, same failure → verdict: WEAK_REPLICATION not NO
- [ ] Set n_trades_p1b < 15 → replication_pass: inconclusive regardless of gate setting
- [ ] Result JSON contains replication_gate field

---

## Simulator Fidelity Lessons

Recorded: 2026-03-17 (during Phase 4 pre-execution)

### LESSON 1 — Close-only simulation is invalid for rotational strategy
The Python simulator originally processed one price per bar (close). 42% of 250vol P1a
bars have H-L range >= StepDist (7.0 pts). Close-only misses all intra-bar rotations,
producing MTP=0 PF=0.58 when live C++ showed PF~1.7. The threshold-crossing OHLC fix
resolved this — but it still executes at exact trigger prices (no slippage).

### LESSON 2 — OHLC threshold-crossing over-estimates profitability
Even with threshold-crossing logic (exact trigger levels checked against High/Low),
the simulator executes at perfect trigger prices. Real execution has gap slippage —
price gaps past the trigger, and you fill at the worse price. OHLC showed PF=4.06 for
SD=5.0/MTP=1; tick data showed PF=0.65 for the same config. The entire OHLC-based
sweep was over-optimistic by 4-6x on PF.

### LESSON 3 — Tick-level simulation is ground truth
Validated Python tick simulator against C++ at regular replay speed: 24 cycles matched
exactly (0% delta on cycle count, 0.3% on PF). Accelerated replay skips ticks —
all accelerated C++ logs are invalid and must be discarded.

### LESSON 4 — Accelerated replay is unreliable
Sierra Chart accelerated replay skips ticks during fast-forward. The C++ first ADD
fired at 25651.50 (accelerated) vs 25649.00 (regular speed / Python). This 2.50-point
difference cascades through the entire trade sequence. Never use accelerated replay
for calibration.

### LESSON 5 — Mode B walking anchor: validated on OHLC, but irrelevant on tick data
Walking anchor eliminated stuck cycles on OHLC simulation (0 stuck vs 26 for frozen,
6.3x more total PnL). But on tick data, the strategy's gross edge (~20%) cannot overcome
3-tick-per-action NQ costs regardless of anchor mode. The anchor mode question was
superseded by the cost viability question.

### LESSON 6 — Rotation edge exists but is thin
V1.1 (unlimited adds) shows consistent gross PF of 1.10-1.25 across all StepDist values
(5-25 pts) on tick data. The edge is real but ~20% gross — it cannot support 3-tick
($15/RT) costs at most configs. Only at SD=25+ with minimal position growth does the
per-cycle margin (100 ticks gross) exceed per-cycle cost (6-12 ticks).

### LESSON 7 — Asymmetric triggers unlock viability
Splitting StepDist into separate reversal distance (15 pts) and add distance (40 pts)
captures frequent rotations while keeping position growth rare. This is the only
tick-viable config found: PF=1.04 @3t cost, PF=1.10 @2t cost, 2,107 cycles.

### LESSON 8 — Time-of-day filter is free alpha
Excluding hours 1, 19, 20 (low-liquidity ETH) improved PF for all configs at 96-99%
cycle retention. Hour 16 (market close) is universally toxic for MAX_PROFIT configs.
No implementation cost — just don't trade during those hours.

### LESSON 9 — Filters that reduce cycle count hurt thin-edge strategies
SpeedRead, ATR-adaptive, and re-entry delay all reduced cycle count without improving
per-cycle economics. For a strategy with PF=1.04, any filter that skips trades
destroys the small positive expectation through lost volume. Only filters that improve
per-cycle PF without reducing count (like time-of-day exclusion) are viable.

### LESSON 10 — Cost model matters more than strategy parameters
At 3-tick cost ($15/RT), only 2 configs out of ~100 tested are profitable on tick data.
At 2-tick cost ($10/RT), ~5 configs become viable. At 1-tick cost ($5/RT), many more.
The difference between a viable and unviable strategy is $5-10 per round turn, not
the trigger mechanism or position management.

### LESSON 11 — V2_js calibrated (MTP + walking anchor path validated)
Python V2_js path (MTP=3, walking anchor) validated against C++ regular-speed replay:
47 vs 49 cycles (+4.3%), Gross PF 0.68 vs 0.67 (-2.0%). All within 5% tolerance.
Both V1.1 and V2_js simulator paths are now calibrated for tick data.

### LESSON 12 — Fixed distances don't generalize across volatility regimes
Rev=15/Add=40 was optimized on P1a (ATR=7.46). On P1b (ATR=9.49, +27%), gross PF
dropped from 1.25 to 1.06 — breakeven at best. The 15-point reversal distance is 2.0x
ATR in P1a but only 1.6x ATR in P1b. ATR-normalized distances (R=2.0x, A=4.0x) solve
this by maintaining constant ATR ratios across regimes.

### LESSON 13 — ATR-normalized asymmetric is the strongest tick-viable config
R=2.0x A=4.0x produces PF=1.22 at 1-tick cost (+16,171 ticks) — better than any fixed-
distance config. Avg reversal=14.7 pts, avg add=29.1 pts in P1a. The 1:2 ratio (reversal
half of add distance) captures frequent rotations while keeping adds rare.

### LESSON 14 — V2 MTP=2 walking beats MTP=1 at SD=25 on total PnL
MTP=2 walking: +9,749 ticks, PF=1.10 at 1t. MTP=1: +5,933, PF=1.09. The extra add
level generates more cycles without excessive cost because SD=25 keeps position growth
rare. But 662 "stuck" events (pos=2 for 500+ ticks) are a concern for live trading.

### LESSON 15 — User's actual cost is 1 tick ($5/RT)
Cost model confirmed: $4-5 commission + exchange per round turn = ~1 tick at $5/tick.
Slippage is already captured in tick-level execution prices. cost_ticks=1 is the
correct setting for live P&L estimation.
