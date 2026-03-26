# Rotation Strategy — Parameter Sweep & PropScore Plan

**Created:** 2026-03-25
**Updated:** 2026-03-25
**Goal:** Generate empirical $E[R]$ and $\sigma$ per configuration, compute PropScore and $P_{\text{pass}}$, identify top parameter sets. Prop firm constraints applied as post-hoc filters on unconstrained results.

**References:**
- [martingale_rotation_math.md](martingale_rotation_math.md) — strategy formulas
- [lucidflex_50k_rules.md](lucidflex_50k_rules.md) — prop firm rules
- [lucidflex_50k_strategy_constraints.md](lucidflex_50k_strategy_constraints.md) — constraints, probability framework
- [rotational_findings.md](rotational_findings.md) — evolving findings report
- Study: `ATEAM_ROTATION_V3_V2803.cpp` (original), `ATEAM_ROTATION_V3_LP.cpp` (LP fork)

---

## Sweep v2 Parameters (Baseline — Completed)

### Grid Design

HardStop is derived from StepDist and depth — not an independent variable. For each SD × depth, HS tested at multiples of the minimum threshold for that depth to fire.

| Parameter | Values |
|-----------|--------|
| StepDist (pts) | 10, 15, 20, 25, 30, 50 |
| Depth 0 (MCS=1) | HS at 0.25×, 0.5×, 0.75×, 1.0×, 1.5×, 2.0× of SD_ticks |
| Depth 1 (MCS=2) | HS at 1.0×, 1.25×, 1.5×, 2.0×, 2.5×, 3.0× of HS_min |
| Depth 2 (MCS=4) | HS at 1.0×, 1.25×, 1.5×, 2.0×, 2.5×, 3.0× of HS_min |
| Depth 3 (MCS=8) | HS at 1.0×, 1.25×, 1.5×, 2.0×, 2.5×, 3.0× of HS_min |

**Total: 144 configurations (36 per depth level)**

### Fixed

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| InitialQty | 1 mini | Base unit |
| MaxFades | 0 (unlimited) | v1 sweep confirmed no effect |
| Commission | $3.50/RT mini | Confirmed by user |
| Session | RTH only (9:30–15:50 ET) | Flatten at 15:49:50 |
| Data | P1 only (Sept 21 – Dec 17, 2025) | P2 is holdout |
| Instrument | NQ, 1-tick bars | |
| Speed Filter | Off | Baseline; can layer later |

### Best Config Identified

**SD=25, HS=125, MCS=2 (depth 1)**

| Setting | Value |
|---------|-------|
| Step Dist | 25 pts |
| Initial Qty | 1 |
| Max Martingale Levels | 1 |
| Max Contract Size | 2 |
| Hard Stop | 125 ticks |
| Max Direction Fades | 0 |
| RTH Only | Yes (LP study only) |

---

## Outputs Per Configuration

| Metric | Description |
|--------|-------------|
| Cycle count | Total completed + stopped + EOD-flattened cycles |
| Win rate | Completed cycles / total cycles |
| $E[R]$ | Mean cycle P&L (net of commission) |
| $\sigma$ | Std dev of cycle P&L |
| Max consecutive losses | Longest losing streak observed |
| $P_{\text{pass}}$ (eval) | Gambler's Ruin formula with $D=2000, T=3000$ |
| $P_{\text{pass}}$ (funded) | Same with $D=2000, T=1000$ |
| PropScore | $E[R]/\sigma \cdot \sqrt{D/T}$ |
| Fractional Kelly $r^*$ | $\alpha \cdot D \cdot E[R] / \sigma^2$, $\alpha = 0.2$ |
| Depth distribution | Count of cycles at each depth (d0, d1, d2, d3) |
| Exit type distribution | Count by REVERSAL, HARD_STOP, EOD_FLATTEN |
| Viability tags | eval_viable, funded_t1_viable, funded_t3_viable |

---

## Execution Plan

### Phase 1: C++ Test Mode — COMPLETE

- [x] **1.1** Read Zone Touch V32 test mode implementation
- [x] **1.2** Add test mode + RTH gate to LP C++ study (LP-1.1)
- [x] **1.3** Run LP test mode on calibration slice — 49 cycles, all event types confirmed

### Phase 2: Python Simulator — COMPLETE

- [x] **2.1** Review existing `rotational_simulator.py` — built new standalone instead
- [x] **2.2** Built `lp_simulator.py` — clean replication of C++ test mode logic
- [x] **2.3** Ran Python simulator on same calibration data
- [x] **2.4** Calibration gate: **PASS — 100% match** (49 cycles, zero diff all 20 columns)

### Phase 3: Parameter Sweep — COMPLETE

- [x] **3.1** Sweep v1: 108 configs (SD × HS × MaxFades), MCS=2 fixed, $4.00 commission
  - Archived as `sweep_results_v1_SD10-50_HS20-120_MF0-5_commission400.csv`
  - Key learning: MaxFades has no effect; HS range too tight for martingale at larger SD
- [x] **3.2** Sweep v2: 144 configs (SD × depth × derived HS), $3.50 commission
  - Full unconstrained sweep — viability tagged post-hoc
  - Saved: `sweep_results.csv` (summary) + `sweep_all_cycles.csv` (885K cycles)
  - 58 minutes runtime on 31.9M bars

### Phase 4: Analysis & Ranking — COMPLETE

- [x] **4.1** Ranked by PropScore — SD=25 HS=125 MCS=2 is best (PropScore 0.035)
- [x] **4.2** 30-minute block analysis on top configs
  - 09:30-10:00 worst block (negative E[R] everywhere)
  - 13:00-13:30 best block (highest E[R] and win rate)
- [x] **4.3** Regime classification by cycle outcome
  - 72% profitable (clean rotation + martingale save)
  - 26% trend losses dominate total cost
- [x] **4.4** Results documented in `rotational_findings.md`
- [x] **4.5** Output: `analysis_time_blocks.csv`, `analysis_regime.csv`

### Phase 5: Follow-up Sweeps & Refinement — COMPLETE

- [x] **5.1** Time gate impact: excluding 3 bad blocks doubles E[R] ($33→$66) and PropScore (0.035→0.072)
  - 09:30-10:00, 12:30-13:00, 13:30-14:00 are all net negative
  - P_pass eval: 46.8% → 54.3%
- [x] **5.2** Targeted HS sweep: SD=25, HS=100-160 in 5-tick steps
  - Sharp peak at HS=125-130 (PropScore 0.035-0.036)
  - Below 120 drops steeply, above 135 degrades
- [x] **5.3** Evaluated 12:30-13:00 and 13:30-14:00 exclusions — both help
- [x] **5.4** Documented in `rotational_findings.md` (Findings 7-8)

### Phase 6: Monte Carlo Validation

- [ ] **6.1** Build Monte Carlo simulator with explicit LucidFlex rules:
  - Trailing EOD drawdown (MLL trails HWM − $2,000, locks at $52,100)
  - Scaling tier transitions (2 → 3 → 4 minis as profit grows)
  - Consistency rule (eval: 50% max single-day profit)
  - Payout logic (5 profitable days at $150+, $2,000 cap)
  - Commission on every cycle
- [ ] **6.2** Run 10,000 Monte Carlo paths per top config
- [ ] **6.3** Measure: eval pass rate, median days to pass, funded survival, total extracted value
- [ ] **6.4** Document results

### Phase 7: P2 Holdout Validation

- [ ] **7.1** P2 holdout run with frozen top config (one shot, per pipeline rules)
- [ ] **7.2** Compare P2 vs P1 — check if these hold or shift:
  - [ ] Overall E[R], sigma, PropScore, win rate
  - [ ] 30-minute block pattern (09:30 worst, 13:00 best — same in P2?)
  - [ ] Regime distribution (% clean rotation / martingale save / trend overcame)
  - [ ] Depth distribution (same d0/d1 split?)
  - [ ] Max consecutive losses (similar or worse?)
  - [ ] Cycle frequency per session (similar number of cycles per day?)
  - [ ] SD dominance by time block (same SDs win same blocks? — compare vs `analysis_sd_by_timeblock.csv`)
- [ ] **7.3** Pass/Fail criteria:
  - **PASS:** E[R] positive, PropScore within 50% of P1, regime distribution similar
  - **WEAK:** E[R] positive but PropScore degraded >50%, or time block pattern shifts significantly
  - **FAIL:** E[R] negative, or regime distribution fundamentally different (e.g., trend overcame jumps from 26% to 50%+)
- [ ] **7.4** If PASS: proceed to paper trade on LP study with identified settings
- [ ] **7.5** If WEAK: document what shifted, assess if it's a regime change or noise
- [ ] **7.6** If FAIL: investigate root cause, do NOT re-optimize on P2 data

---

## Decision Points

| After Phase | Decision |
|-------------|----------|
| Phase 4 (done) | Depth 1 is PropScore sweet spot; SD=25 HS=125 is best config |
| Phase 5 | Does time gating materially improve PropScore/P_pass? |
| Phase 5 | Does finer HS tuning around 125 ticks change the picture? |
| Phase 6 | Is P_pass under full LucidFlex rules viable (>60%)? |
| Phase 7 | Does P2 holdout confirm P1 results? |

---

## Data & File Inventory

| Item | Location | Status |
|------|----------|--------|
| NQ 1-tick P1 data | `stages/01-data/data/bar_data/tick/NQ_BarData_1tick_rot_P1.csv` | 31.9M rows |
| Calibration slice | `stages/01-data/data/bar_data/tick/NQ_calibration_1day.csv` | 334K rows (Sept 22) |
| C++ LP study | `shared/archetypes/rotational/acsil/ATEAM_ROTATION_V3_LP.cpp` | Calibration-locked |
| Python simulator | `shared/archetypes/rotational/lp_simulator.py` | Calibration-locked |
| Sweep harness | `shared/archetypes/rotational/lp_sweep.py` | v2, active |
| Analysis script | `shared/archetypes/rotational/lp_analysis.py` | Active |
| Sweep results | `shared/archetypes/rotational/docs/sweep_results.csv` | v2 baseline, 144 configs |
| Cycle data | `shared/archetypes/rotational/docs/sweep_all_cycles.csv` | 885K cycles, gitignored |
| v1 archive | `shared/archetypes/rotational/docs/sweep_results_v1_*.csv` | Archived |
| Time block analysis | `shared/archetypes/rotational/docs/analysis_time_blocks.csv` | Complete |
| Regime analysis | `shared/archetypes/rotational/docs/analysis_regime.csv` | Complete |
| Findings report | `shared/archetypes/rotational/docs/rotational_findings.md` | Evolving |
| Audit trail | `shared/archetypes/rotational/docs/lucidprop_audit.md` | Active |
