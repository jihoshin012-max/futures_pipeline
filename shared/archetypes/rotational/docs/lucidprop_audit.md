# LucidProp — Audit Trail

**Started:** 2026-03-25

---

## Session 1 — 2026-03-25

### Research & Fact Gathering

- [x] Reviewed V2803 C++ study — full code read of martingale rotation logic
- [x] Derived closed-form martingale formulas directly from code mechanics
  - Profit per cycle: $q_0 \cdot d$ (constant regardless of depth)
  - Max drawdown at depth k: $q_0 \cdot d \cdot (2^k - 1)$
  - Risk/reward: $(2^k - 1) : 1$
  - Breakeven win rate: $1 - 2^{-k}$
  - Average entry price: $P_0 - d(k - 1 + 2^{-k})$
  - Hard stop loss, depth-reachability, adjusted breakeven with stop
  - Fade limit chained loss cap
- [x] Saved → `martingale_rotation_math.md`

### Fractal Data Review

- [x] Read all three fractal docs (hypothesis v3, decomposition prompt, monitor skill prompt)
- [x] Identified connections: Fact 2 completion rates map to martingale breakeven, 1:1 ratio problem, half-block curve
- [x] Decision: keep fractal data as separate Layer 2 — not baked into strategy math or constraints
  - Strategy math = Layer 1 (what the machine does)
  - Fractal observations = Layer 2 (what the market does)
  - Prop firm rules = Layer 3 (external constraints)

### LucidFlex 50K Rules

- [x] Web search + fetch from third-party guides (initial pass)
- [x] User provided official Lucid help center text + screenshots — corrected multiple third-party errors:
  - Payouts to Live: 5 (not 6)
  - Payout cap: flat $2,000 all payouts (not escalating)
  - Consistency cushion: ~4% ($1,560 on $3,000 target)
- [x] Added trading rules: microscalping (>50% profits from ≤5s holds), HFT prohibition, martingale "strongly discouraged" but not banned, scaling/DCA allowed, genuine scalping allowed
- [x] Added LucidLive transition: move-to-live cap ($8,000), Day-1 deposit ($2,400), escrow ($5,600), escrow release ($5K per $10K earned), 60-day minimum
- [x] Added account limits: 10 eval, 5 funded, 5 live, 10 total eval+funded
- [x] Saved → `lucidflex_50k_rules.md`

### Strategy Constraints (Bridge Doc)

- [x] Mapped martingale formulas onto LucidFlex constraints
- [x] Identified binding constraint per phase (eval, funded tiers, live)
- [x] Minis vs micros analysis — full comparison table at each scaling tier
- [x] Commission analysis ($4.00/mini RT, $0.50/micro RT):
  - Configs B, C (deep micros) are negative EV after commissions
  - Config D (5 micros, depth 2) is breakeven
  - Config A (1 mini, depth 1) retains 60% of gross → $24 net/cycle
  - Micro depth advantage largely eliminated by commission drag
- [x] Added Monte Carlo / probability framework ($P_{\text{pass}}$, PropScore, Kelly)
  - Identified gaps: bimodal returns, trailing drawdown, serial correlation
- [x] Added open questions: EOD flatten, commission drag, payout timing, sim-to-live gap, hard stop optimization, data requirements
- [x] Saved → `lucidflex_50k_strategy_constraints.md`

### Sweep Planning

- [x] Defined sweep grid: 5 StepDist × 6 HardStop × 3 MaxFades = 90 configs
- [x] Fixed params: 1 mini, MaxContractSize=2, MaxLevels=1, RTH only, P1 data, NQ 1-tick
- [x] Defined outputs per config: cycle count, win rate, E[R], σ, PropScore, P_pass, Kelly
- [x] 6-phase execution plan with decision points
- [x] Saved → `lucidprop_plan.md`

### Phase 1.1: Zone Touch Test Mode Review

- [x] Read V32 test mode implementation (inputs, batch processing, CSV output pattern)
- [x] Documented pattern: runs once on last bar, loads bar data from CSV, walks bar-by-bar, writes trades/skipped/decisions CSVs
- [x] Defined V2803 test mode output fields:
  - Cycle-level: id, timestamps, direction, prices, exit_type, depth, position, P&L, bars_held, MFE, MAE
  - Watch-phase: start time, reference price, running high/low, duration in bars
- [x] Updated plan step 1.1 as complete

### Phase 1.2: C++ Test Mode + RTH Gate (LP-1.1)

- [x] Created `ATEAM_ROTATION_V3_LP.cpp` as fork of V2803
- [x] Added RTH gate (Input 12) — live trading restricted to 9:30:00–15:49:50 ET
  - Forced flatten at 15:49:50 with EOD_FLATTEN event
  - Session open reset via RTHFlatSent persistent flag (int 8)
  - No entries outside RTH window when enabled
- [x] Added CSV test mode (Input 14/15) — batch simulation
  - Loads up to 500K bars from calibration CSV (small subset, not full 32M)
  - Parses Date/Time columns, filters RTH only, detects session boundaries
  - Full rotation state machine: watch → seed → add/reversal/hard_stop → EOD flatten
  - Simulates position and avg entry internally (no SC order system)
  - Tracks MFE/MAE per cycle using bar High/Low
  - Outputs: ATEAM_LP_TEST_cycles.csv (20 columns) + ATEAM_LP_TEST_events.csv (10 columns)
  - Summary logged to SC message log (cycle count, W/L, net P&L)
- [x] Data check: P1 1-tick data is 31.9M rows — confirmed too large for C++ memory allocation
  - Decision: extract small calibration slice (1 RTH session) for C++ test mode
  - Full 32M-row sweep runs in Python (Phase 3)
- [x] NQ bar data format confirmed: Date, Time, Open, High, Low, Last, Volume, ... ATR (38 columns)
- [x] Updated plan step 1.2 as complete

---

## Decisions Log

| Date | Decision | Rationale |
|------|----------|-----------|
| 2026-03-25 | Keep fractal data separate (Layer 2) | Strategy math should stand alone; fractal is empirical and regime-dependent |
| 2026-03-25 | Use P1 data only for sweep | P2 is holdout per pipeline rules — never used for calibration |
| 2026-03-25 | RTH only, flatten by ~3:50 PM | Operational rule — ensures flat before Lucid EOD snapshot |
| 2026-03-25 | Commission rates: $4.00/mini, $0.50/micro | Working estimates from user; update if Lucid schedule differs |
| 2026-03-25 | StepDist ≥ 10 pts | Smaller values risk microscalping flag (>50% profits from ≤5s holds) |
| 2026-03-25 | Start sweep at funded tier 1 (2 minis, depth 1) | Most vulnerable phase — if strategy doesn't work here, other tiers are moot |
| 2026-03-25 | Overnight gap not a risk | User confirms trading always closes before EOD RTH |
| 2026-03-25 | Multi-account correlation not a concern for now | User deferred this consideration |
| 2026-03-25 | Include watch-phase data in test mode CSV | Needed for cycle frequency, daily P&L distribution, consistency rule modeling |
| 2026-03-25 | C++ test mode uses small calibration slice, not full 32M rows | SC AllocateMemory can't handle 32M bars; calibration only needs 1 RTH session (~50-100K rows) |
| 2026-03-25 | RTH gate: 9:30:00 open, 15:49:50 forced flatten | 10 seconds before 15:50 to ensure flat before Lucid EOD snapshot |

---

## Documents Created

| File | Purpose | Status | Locked? |
|------|---------|--------|---------|
| **Documentation (docs/)** | | | |
| `martingale_rotation_math.md` | Layer 1: strategy mechanics & formulas | Complete | Yes |
| `lucidflex_50k_rules.md` | Layer 3: prop firm rules (official sources) | Complete | Yes |
| `lucidflex_50k_strategy_constraints.md` | Bridge: constraints, probability framework, open questions | Complete | Yes |
| `lucidprop_plan.md` | Execution plan with checkboxes | Active | No — updated as steps complete |
| `lucidprop_audit.md` | This file — audit trail | Active | No — updated as work progresses |
| **C++ (acsil/)** | | | |
| `ATEAM_ROTATION_V3_V2803.cpp` | Original study — DO NOT MODIFY | Frozen | **Yes — original, never touch** |
| `ATEAM_ROTATION_V3_LP.cpp` | LP fork with test mode + RTH gate (LP-1.1) | Calibrated | **Yes — calibration-locked. Changes require re-calibration.** |
| **Python (rotational/)** | | | |
| `lp_simulator.py` | Python replication of C++ test mode — 100% match verified | Calibrated | **Yes — calibration-locked. Changes require re-calibration vs C++.** |
| `lp_sweep.py` | 108-config parameter sweep harness | Active | No — may need updates for time-block analysis |
| `rotational_simulator.py` | Original pipeline simulator — not used by LP project | Unchanged | N/A |
| **Data (stages/01-data/data/bar_data/tick/)** | | | |
| `NQ_BarData_1tick_rot_P1.csv` | Full P1 1-tick data (32M rows) — sweep input | Source | **Yes — source data, never modify** |
| `NQ_calibration_1day.csv` | Sept 22 RTH slice (334K rows) — calibration input | Calibration | **Yes — calibration reference** |
| `ATEAM_LP_TEST_cycles.csv` | C++ test mode output — calibration reference | Calibration | **Yes — reference for Python match** |
| `ATEAM_LP_TEST_events.csv` | C++ test mode events — calibration reference | Calibration | **Yes — reference for Python match** |
| `ATEAM_LP_PY_cycles.csv` | Python output — verified 100% match to C++ | Calibration | **Yes — proof of calibration** |
| `ATEAM_LP_PY_events.csv` | Python output — events | Calibration | **Yes — proof of calibration** |

**Lock policy:** Files marked "Yes" must not be modified without explicit instruction. Any change to `lp_simulator.py` or `ATEAM_ROTATION_V3_LP.cpp` requires re-running the calibration gate and re-verifying the 100% match.

---

### Phase 1.3: C++ Test Mode Run

- [x] Extracted calibration slice: NQ_calibration_1day.csv (Sept 22, 2025 RTH, 334K rows)
- [x] Ran C++ test mode in SC — 49 cycles produced
- [x] Confirmed all event types present: REVERSAL, HARD_STOP, EOD_FLATTEN
- [x] Bugs found and fixed (LP-1.1 bugfix): avg_entry, pnl_dollars, cycle_id
- [x] Recompiled and verified fixes

### Phase 2: Python Simulator + Calibration

- [x] Reviewed existing rotational_simulator.py — too many differences (no hard stop, no fades, no RTH gate, different add logic)
- [x] Built standalone `lp_simulator.py` — clean replication of C++ test mode
- [x] Ran on same calibration data with same params (SD=10, HS=60, ML=2, MCS=4, MF=3)
- [x] **Calibration gate: PASS — 100% match**
  - 49 cycles, zero diff across all 20 columns
  - 39 W / 10 L, net PnL = 321.0 ticks
  - C++ output: ATEAM_LP_TEST_cycles.csv
  - Python output: ATEAM_LP_PY_cycles.csv
  - Compared with `diff` — identical

---

## Next Up

**Phase 3:** Build sweep harness, run 90-config sweep on full P1 data, compute E[R], σ, PropScore per config.
