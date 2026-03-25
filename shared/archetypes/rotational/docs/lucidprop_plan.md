# Rotation Strategy — Parameter Sweep & PropScore Plan

**Created:** 2026-03-25
**Goal:** Generate empirical $E[R]$ and $\sigma$ per configuration, compute PropScore and $P_{\text{pass}}$ under LucidFlex 50K constraints, identify top parameter sets for funded trading.

**References:**
- [martingale_rotation_math.md](martingale_rotation_math.md) — strategy formulas
- [lucidflex_50k_rules.md](lucidflex_50k_rules.md) — prop firm rules
- [lucidflex_50k_strategy_constraints.md](lucidflex_50k_strategy_constraints.md) — constraints, probability framework, open questions
- Study: `ATEAM_ROTATION_V3_V2803.cpp`
- Test mode pattern: `ATEAM_ZONE_TOUCH_V32.cpp`

---

## Sweep Parameters

### Swept

| Parameter | Values | Count |
|-----------|--------|-------|
| StepDist (pts) | 10, 15, 20, 25, 30, 50 | 6 |
| HardStop (ticks) | 20, 30, 40, 60, 80, 120 | 6 |
| MaxFades | 0 (unlimited), 3, 5 | 3 |

**Total configurations: 108**

### Fixed

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| InitialQty | 1 mini | Commission-viable at funded tier 1 |
| MaxContractSize | 2 | Funded tier 1 scaling cap |
| MaxLevels | 1 | Depth 1 (1 add max at 2-contract cap) |
| Commission | $4.00/RT mini, $0.50/RT micro | Working estimates |
| Session | RTH only (9:30–15:50 ET) | Flatten by 15:50 to ensure flat before EOD snapshot |
| Data | P1 only (Sept 21 – Dec 17, 2025) | P2 is holdout — never used for calibration/sweep |
| Instrument | NQ, 1-tick bars | |
| Speed Filter | Off | Baseline sweep without filter; can layer on later |

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
| $P_{\text{pass}}$ (funded) | Same with $D=2000, T=1000$ (first scaling tier) |
| PropScore | $E[R]/\sigma \cdot \sqrt{D/T}$ |
| Fractional Kelly $r^*$ | $\alpha \cdot D \cdot E[R] / \sigma^2$, $\alpha = 0.2$ |

---

## Execution Plan

### Phase 1: C++ Test Mode

- [x] **1.1** Read Zone Touch V32 test mode implementation to understand the CSV output pattern
- [x] **1.2** Add test mode + RTH gate to LP C++ study (LP-1.1)
  - Input 12: RTH Only toggle — restricts live trading to 9:30-15:49:50 ET, forced flatten at EOD
  - Input 14: CSV Test Mode toggle + Input 15: Test Path
  - Loads up to 500K bars from calibration CSV, runs batch simulation bar-by-bar
  - Outputs ATEAM_LP_TEST_cycles.csv (cycle-level with watch phase, P&L, depth, MFE/MAE)
  - Outputs ATEAM_LP_TEST_events.csv (every event: SEED, ADD, REVERSAL, HARD_STOP, EOD_FLATTEN)
  - RTH session boundary detection + reset at session open
  - Simulates position/avg entry internally (no SC order system in test mode)
  - Follows V32 pattern: allocate memory, batch process, write CSVs, free memory, return
- [x] **1.3** Run LP test mode on calibration slice — 49 cycles, all event types confirmed

### Phase 2: Python Simulator

- [x] **2.1** Review existing `rotational_simulator.py` — too many differences to retrofit, built new standalone
- [x] **2.2** Built `lp_simulator.py` — clean replication of C++ test mode logic
  - Pullback-based seed, martingale add with doubling, anchor reset on add
  - Reversal (flatten + flip), hard stop, max direction fades
  - RTH session gate (9:30–15:49:50 ET, forced flatten, session reset)
  - Cycle-level + event-level CSV output matching C++ format
- [x] **2.3** Ran Python simulator on same calibration data (NQ_calibration_1day.csv, Sept 22)
- [x] **2.4** Calibration gate: **PASS — 100% match**
  - 49 cycles in both C++ and Python
  - Zero diff across all 20 columns (cycle_id, direction, prices, P&L, depth, MFE/MAE, bars_held)
  - 39 W / 10 L, net PnL = 321.0 ticks — identical in both
- [ ] **2.5** Fix discrepancies if any, re-run until calibration passes

### Phase 3: Parameter Sweep

- [ ] **3.1** Build sweep harness in Python
  - Iterates over 90 configurations
  - For each config: runs simulator on full P1 1-tick data (RTH only)
  - Collects cycle-level P&L series per config
  - Applies commission ($4.00/RT per mini per cycle, accounting for depth)
- [ ] **3.2** Run sweep on P1 data
- [ ] **3.3** Compute per-config metrics:
  - Cycle count, win rate, $E[R]$, $\sigma$
  - Max consecutive losses
  - $P_{\text{pass}}$ (eval and funded)
  - PropScore
  - Fractional Kelly $r^*$
- [ ] **3.4** Output results to `sweep_results.csv` and summary table

### Phase 4: Analysis & Ranking

- [ ] **4.1** Rank configurations by PropScore
- [ ] **4.2** Filter: exclude configs with fewer than 100 cycles (insufficient sample)
- [ ] **4.3** Filter: exclude configs with negative $E[R]$ net of commission
- [ ] **4.4** Identify top 3–5 configurations
- [ ] **4.5** For top configs, compute confidence intervals on $E[R]$ and $\sigma$ (bootstrap or analytical)

### Phase 5: Monte Carlo Validation

- [ ] **5.1** Build Monte Carlo simulator with explicit LucidFlex rules:
  - Trailing EOD drawdown (MLL trails HWM − $2,000, locks at $52,100)
  - Scaling tier transitions (2 → 3 → 4 minis as profit grows)
  - Consistency rule (eval: 50% max single-day profit)
  - Payout logic (5 profitable days at $150+, $2,000 cap)
  - Commission on every cycle
- [ ] **5.2** Run 10,000 Monte Carlo paths per top config
- [ ] **5.3** Measure per config:
  - Eval pass rate
  - Median days to pass eval
  - Funded survival rate (probability of reaching first payout)
  - Funded survival to 5 payouts
  - Distribution of total extracted value (payouts + move-to-live)
- [ ] **5.4** Document results

### Phase 6: Documentation

- [ ] **6.1** Save sweep results and Monte Carlo outputs to `docs/` or `results/`
- [ ] **6.2** Update constraint doc with empirical findings
- [ ] **6.3** Identify next steps (P2 holdout run with frozen params, or parameter refinement)

---

## Decision Points

| After Phase | Decision |
|-------------|----------|
| Phase 2 (calibration) | If calibration fails: debug simulator before proceeding |
| Phase 4 (ranking) | If no config has positive $E[R]$ net of commission: reassess StepDist range or position sizing |
| Phase 4 (ranking) | If PropScore is very low across all configs: the strategy may not be viable for this prop firm structure |
| Phase 5 (Monte Carlo) | If pass rates are low even for top configs: consider whether funded tier 1 constraint is the bottleneck and whether starting with eval-only (4 minis) changes the picture |
| Phase 6 | If results are promising: proceed to P2 holdout with frozen top config |

---

## Data Requirements

| Item | Location | Status |
|------|----------|--------|
| NQ 1-tick P1 data | `stages/01-data/data/bar_data/tick/` | Verify file exists for P1 date range |
| V2803 C++ source | `shared/archetypes/rotational/acsil/ATEAM_ROTATION_V3_V2803.cpp` | Exists |
| Zone Touch V32 test mode reference | `shared/archetypes/zone_touch/acsil/ATEAM_ZONE_TOUCH_V32.cpp` | Exists |
| Python simulator | `shared/archetypes/rotational/rotational_simulator.py` | Exists — needs review |
| instruments.md (tick size, costs) | `_config/instruments.md` | Verify NQ entry |
