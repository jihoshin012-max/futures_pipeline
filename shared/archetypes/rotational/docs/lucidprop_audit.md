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
| `lp_sweep.py` | v2 baseline sweep (144 configs, derived HS) | Active | No — updated for each sweep iteration |
| `lp_analysis.py` | Post-processing: 30-min blocks + regime classification | Active | No |
| **Documentation (docs/)** | | | |
| `rotational_findings.md` | Evolving findings report — updated as analysis progresses | Active | No |
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

### Phase 3: Parameter Sweep

**Sweep v1 (completed, archived):**
- [x] 108 configs: SD [10,15,20,25,30,50] × HS [20,30,40,60,80,120] × MF [0,3,5]
- [x] Fixed: MCS=2, ML=1 (funded tier 1 constraints)
- [x] Commission: $4.00/RT (later corrected to $3.50)
- [x] Results saved: `sweep_results_v1_SD10-50_HS20-120_MF0-5_commission400.csv`
- [x] Key findings:
  - MaxFades has no effect — dropped from future sweeps
  - Most configs tested pure rotation (HS < SD_ticks), not martingale
  - SD=25 HS=120 was top PropScore but only allowed 1 add with 20 ticks of room
  - HS range too tight to test actual martingale behavior at larger SD values

**Design iteration (discussion-driven):**
- [x] Identified that HS is derived from SD and depth, not an independent variable
- [x] HS minimum for adds: depth 1 needs HS ≥ SD_ticks, depth 2 needs HS ≥ 1.5×SD_ticks, etc.
- [x] MLL caps max loss: position × HS × $5/tick ≤ $2,000 for viable configs
- [x] Decision: drop eval/funded constraints from sweep, run full unconstrained grid, tag viability after
- [x] Decision: start from eval (4 minis) not funded tier 1 (2 minis) — must pass eval first
- [x] Decision: regime classification by cycle outcome at each SD scale (depth + exit_type)
- [x] Decision: save all cycle-level data for 30-min block and regime post-processing
- [x] Commission corrected to $3.50/RT mini, $1.00/RT micro

**Sweep v2 (baseline, running):**
- [x] 144 configs: 6 SD × 4 depths (MCS=1,2,4,8) × 6 HS per depth
- [x] HS derived from depth minimums with multipliers [1.0, 1.25, 1.5, 2.0, 2.5, 3.0]
- [x] Depth 0: 36 configs (pure rotation, all eval-viable)
- [x] Depth 1: 36 configs (25 eval-viable, 11 informational)
- [x] Depth 2: 36 configs (4 eval-viable, 32 informational)
- [x] Depth 3: 36 configs (0 eval-viable, all informational)
- [x] Commission: $3.50/RT
- [x] Outputs: sweep_results.csv + sweep_all_cycles.csv (full cycle data)
- [ ] Results pending — sweep running (~51 min estimated)

---

## Decisions Log (continued)

| Date | Decision | Rationale |
|------|----------|-----------|
| 2026-03-25 | Drop MaxFades from sweep | v1 showed no effect across all configs |
| 2026-03-25 | HS is derived from SD × depth, not independent | HS below depth minimum means adds can't fire — testing those is testing pure rotation, not martingale |
| 2026-03-25 | Full unconstrained sweep, tag viability post-hoc | Allows isolating results for any stage (eval/funded/live) without re-running |
| 2026-03-25 | Start from eval constraints, not funded tier 1 | Must pass eval first; if it fails at 4 minis it fails at 2 |
| 2026-03-25 | Regime = cycle outcome at that SD scale | Rotational vs trending is scale-dependent; reversal=rotation, stop=trend at that grid |
| 2026-03-25 | Save all cycle data for post-processing | Enables 30-min block analysis, regime splits without re-running sims |
| 2026-03-25 | Commission: $3.50/RT mini, $1.00/RT micro | Corrected from initial $4.00/$0.50 estimates |

---

## Next Up

**After sweep v2 completes:**
1. Review results — which SD × depth combinations have positive E[R]
2. Build 30-min block analysis on saved cycle data
3. Regime analysis: rotation vs trend breakdown by cycle outcome
4. Identify top configs for targeted follow-up sweeps

---

## Future Exploration

### Rotation Scale Detection Study (Filter Study)

**Goal:** Identify the current dominant rotation scale in real-time to inform StepDist selection or enable/disable trading based on whether the market matches the strategy's grid.

**Approach options:**

1. **Rolling zigzag swing size** — run zigzag at a small threshold (e.g., 3 pts) over a lookback window (30–60 min). Median completed swing size = current rotation scale. Maps directly to which SD is appropriate. Can also detect scale trend (expanding/contracting swings → possible transition to trend).

2. **Rolling range vs displacement** — over a lookback window, compare total range (high - low) to net displacement (|close - open|). High range + low displacement = rotational. The ratio is a "rotation quality" score, and the absolute range indicates the scale.

3. **Multi-scale fractal decomposition** — run zigzag simultaneously at multiple thresholds (e.g., 5, 10, 15, 25, 50 pts). Report which scale has the most active completions. Connects directly to the fractal Layer 2 analysis (Fact 1 self-similarity, Fact 3 parent/child ratio).

**Implementation:** Separate SC study (like SpeedRead) that the rotation strategy reads via inter-study reference. Outputs rotation scale, quality score, and scale trend as subgraph values.

**Dependencies:** None on the current sweep — this is an independent research track. The sweep results (specifically the regime analysis showing which SD performs best in which conditions) would inform the thresholds for this study.
