# Frozen-Anchor Sweep: Generate Configs and Run

## OBJECTIVE

Run ~210 frozen-anchor configs on P1 1-tick data. The primary question: does ReversalTarget < 1.0 push the success rate above 50% enough to create positive EV, and do adds amplify that through payoff asymmetry? Produce per-config summaries with all diagnostic columns for analysis.

---

## KEY FINDINGS FROM VERIFICATION (Context for This Sweep)

⚠️ **Read these before running. They explain what the sweep is testing and why.**

1. **Success rate at RT=1.0 is 49.4%.** Symmetric exits (±StepDist from anchor) produce a coin flip. The fractal data predicted ~80% completion, but the strategy enters AFTER a seed move — it needs a second StepDist move in the same direction.

2. **Add count ≠ retracement count.** Survivorship bias: non-max-add cycles that fail graduate to higher add counts before the failure exit fires. The 1-add bucket is 100% success by construction. This means adds affect PAYOFF MAGNITUDE, not success probability.

3. **Adds don't change the success/failure split.** All three verification configs produced identical 2,401/2,455 splits. The exit triggers are anchor-relative, so adds don't affect when exits fire.

4. **ReversalTarget is the main lever.** At RT=0.6, success fires at +0.6×SD from anchor while failure fires at -1.0×SD. Success is closer → should fire more often. The half-block curve predicts ~80% completion at 60% progress. This is the key test.

📌 **The sweep answers: what RT value creates the optimal balance between higher success rate (from closer target) and lower per-success payoff (from taking less of the move)?**

---

## PREREQUISITES

⚠️ **Verify all before proceeding.**

1. Frozen-anchor simulator exists and passed verification (25/25 tests + V11_CHECK)
2. P1 1-tick data: 25,457,094 RTH bars, 60 trading days, Sept 22 – Dec 12, 2025
3. Context tagger ready (same as V1.1 sweep)

---

## DATA PREPARATION

Same as V1.1 sweep:
- Load P1 1-tick bars, RTH only (09:30–16:15 ET)
- Pre-compute context tags via `context_tagger.py` (ATR, swing stats, persistence)
- Context computed ONCE, shared across all configs

⚠️ **Use the same bar DataFrame from the V1.1 sweep if still in memory. Do NOT reload and recompute if avoidable — saves 10+ minutes.**

---

## CONFIG GRID

### Parameters

| Parameter | Values | Count |
|-----------|--------|-------|
| StepDist | 15, 20, 25, 30, 35, 40, 50 | 7 |
| ReversalTarget | 0.5, 0.6, 0.7, 0.8, 1.0 | 5 |
| AddDist/MaxAdds | see below | 6 groups |

### Add Configurations (with dead-config pruning)

| Group | Ratio | AddDist | MaxAdds | Contracts at Max | Notes |
|-------|-------|---------|---------|-----------------|-------|
| MA0 | n/a | n/a | 0 | 1 | Pure rotation baseline. Deduplicated — one per SD×RT. |
| R04_MA1 | 0.4 | 0.4×SD | 1 | 2 | One add at -40% of SD |
| R04_MA2 | 0.4 | 0.4×SD | 2 | 3 | Two adds at -40%, -80% of SD |
| R05_MA1 | 0.5 | 0.5×SD | 1 | 2 | One add at -50% of SD |
| R03_MA2 | 0.3 | 0.3×SD | 2 | 3 | Two adds at -30%, -60% of SD |
| R03_MA3 | 0.3 | 0.3×SD | 3 | 4 | Three adds at -30%, -60%, -90% of SD |

📌 **Why ratio 0.3:** allows MaxAdds=3 (adds at -0.3, -0.6, -0.9×SD, failure at -1.0). More adds = more payoff asymmetry (4 contracts on success vs bounded loss). Tests whether tighter child scale improves EV through larger win/loss ratio.

⚠️ **Dead configs already pruned from this grid:**
- Ratio 1.0 with any adds (add1 = failure point)
- Ratio 0.5 with MaxAdds≥2 (add2 at -1.0×SD = failure point)
- Ratio 0.4 with MaxAdds≥3 (add3 at -1.2×SD > failure)
- Ratio 0.3 with MaxAdds≥4 (add4 at -1.2×SD > failure)

### Config Generation

⚠️ **Generate all 210 configs in a single script. 6 add groups × 7 StepDists × 5 ReversalTargets. The code below is split into two blocks for readability but should be ONE nested loop.**

```python
configs = []
COST_TICKS = 2.0

for sd in [15, 20, 25, 30, 35, 40, 50]:
    for rt in [0.5, 0.6, 0.7, 0.8, 1.0]:

        # Group MA0: pure rotation (no adds)
        configs.append(FrozenAnchorConfig(
            config_id=f"FA_SD{sd}_MA0_RT{int(rt*100)}",
            step_dist=sd,
            add_dist=sd * 0.4,  # Unused but required > 0
            max_adds=0,
            reversal_target=rt,
            cost_ticks=COST_TICKS
        ))
```

📌 **Groups with adds below. Ratio 0.4 gets MA=1 and MA=2. All configs share the same SD×RT outer loop.**

```python
        # (continuing inside the same sd/rt loop)

        # Group R04_MA1
        ad = round(sd * 0.4, 2)
        configs.append(FrozenAnchorConfig(
            config_id=f"FA_SD{sd}_R04_MA1_RT{int(rt*100)}",
            step_dist=sd,
            add_dist=ad,
            max_adds=1,
            reversal_target=rt,
            cost_ticks=COST_TICKS
        ))

        # Group R04_MA2
        configs.append(FrozenAnchorConfig(
            config_id=f"FA_SD{sd}_R04_MA2_RT{int(rt*100)}",
            step_dist=sd,
            add_dist=ad,
            max_adds=2,
            reversal_target=rt,
            cost_ticks=COST_TICKS
        ))
```

📌 **Continuing config generation. Groups above: MA0 (no adds), R04_MA1, R04_MA2. Groups below: R05_MA1, R03_MA2, R03_MA3. All 6 groups use the same SD and RT loops.**

```python
        # (continuing inside the same sd/rt loop)

        # Group R05_MA1 — ratio 0.5 only supports MA=1
        ad5 = round(sd * 0.5, 2)
        configs.append(FrozenAnchorConfig(
            config_id=f"FA_SD{sd}_R05_MA1_RT{int(rt*100)}",
            step_dist=sd,
            add_dist=ad5,
            max_adds=1,
            reversal_target=rt,
            cost_ticks=COST_TICKS
        ))

        # Group R03_MA2
        ad3 = round(sd * 0.3, 2)
        configs.append(FrozenAnchorConfig(
            config_id=f"FA_SD{sd}_R03_MA2_RT{int(rt*100)}",
            step_dist=sd,
            add_dist=ad3,
            max_adds=2,
            reversal_target=rt,
            cost_ticks=COST_TICKS
        ))

        # Group R03_MA3 — tightest ratio, most adds (4 contracts max)
        # ⚠️ This is the maximum asymmetry config: 4 contracts on success vs bounded loss
        configs.append(FrozenAnchorConfig(
            config_id=f"FA_SD{sd}_R03_MA3_RT{int(rt*100)}",
            step_dist=sd,
            add_dist=ad3,
            max_adds=3,
            reversal_target=rt,
            cost_ticks=COST_TICKS
        ))

print(f"Total configs: {len(configs)}")  # Should be 210
```

⚠️ **Verify count = 210 (7 StepDists × 5 RTs × 6 add groups). If not 210, debug before running.**

---

## SMOKE TEST

Before the full sweep, run 5 configs — one per RT value at SD=25, R04_MA2:

```python
smoke_configs = [
    FrozenAnchorConfig("SMOKE_RT50", 25.0, 10.0, 2, 0.5, 2.0),
    FrozenAnchorConfig("SMOKE_RT60", 25.0, 10.0, 2, 0.6, 2.0),
    FrozenAnchorConfig("SMOKE_RT70", 25.0, 10.0, 2, 0.7, 2.0),
    FrozenAnchorConfig("SMOKE_RT80", 25.0, 10.0, 2, 0.8, 2.0),
    FrozenAnchorConfig("SMOKE_RT100", 25.0, 10.0, 2, 1.0, 2.0),
]
```

📌 **The smoke test answers the most important question immediately: does success rate increase as RT decreases? If SMOKE_RT50 shows ~75%+ success rate and SMOKE_RT100 shows ~50%, the RT lever is working. Report success rate, failure rate, cycle count, and adjusted net PnL for each.**

Verify:
- All produce > 0 cycles
- All have exit_type = SUCCESS or FAILURE (no undefined)
- Success rate increases as RT decreases
- Net PnL < gross PnL (costs applied)
- Cycle logs have all diagnostic columns
- Incomplete cycles logged separately

⚠️ **If success rate does NOT increase as RT decreases, STOP. The core thesis is broken.**

---

## SWEEP EXECUTION

Run all 210 configs with multiprocessing (4 workers).

```python
from multiprocessing import Pool

def run_config(args):
    bars_path, config = args
    bars = load_bars(bars_path)  # Or shared memory approach
    cycle_log, incomplete_log = run_frozen_anchor_simulation(bars, config)
    summary = compute_config_summary(cycle_log, incomplete_log, config)
    save_cycle_log(cycle_log, config.config_id)
    save_incomplete_log(incomplete_log, config.config_id)
    return summary

with Pool(4) as pool:
    summaries = pool.map(run_config, [(bars_path, c) for c in configs])
```

⚠️ **Estimated runtime: ~210 configs × 3 min / 4 workers = ~2.6 hours. Progress reporting: print config_id, cycle_count, success_rate, adjusted_net after each config completes.**

---

## PER-CONFIG SUMMARY METRICS

For each config, compute from its cycle log:

**Core metrics:**
- config_id, step_dist, add_dist, max_adds, reversal_target
- cycle_count, success_count, failure_count
- success_rate (success_count / cycle_count)
- win_count (pnl_ticks_net > 0), loss_count, win_rate
- gross_pnl, net_pnl (qty-weighted)
- total_costs
- max_drawdown_ticks (cycle-level cumulative)
- profit_per_dd
- max_position, avg_cycle_duration_bars

📌 **success_rate and win_rate are DIFFERENT metrics. success_rate = structural exits (did the parent move complete?). win_rate = PnL sign (did the cycle make money after costs?). A SUCCESS exit with RT=0.5 after 2 adds might still be net negative after costs.**

**Cycle-type breakdown:**
- cycles_0_adds, cycles_1_add, cycles_multi_add
- pnl_0_adds, pnl_1_add, pnl_multi_add

⚠️ **The add-count PnL breakdown is important for understanding whether adds help or hurt. With the survivorship bias finding, non-max-add buckets will be almost all successes. The max-add bucket concentrates all failures. This is expected — report it but don't misinterpret it.**

**Failure dynamics:**
- failure_after_failure (count of cascading failures)
- incomplete_cycles, incomplete_unrealized_pnl
- adjusted_net_pnl = net_pnl + incomplete_unrealized_pnl

**Diagnostic aggregates:**
- avg_progress_hwm_success (mean progress_hwm for SUCCESS cycles)
- avg_progress_hwm_failure (mean progress_hwm for FAILURE cycles)
- avg_cycle_waste_pct
- first_cycle_success_rate (success rate where cycle_day_seq=1)
- later_cycle_success_rate (success rate where cycle_day_seq > 1)

📌 **first_cycle_success_rate vs later_cycle_success_rate answers the seed quality question. If first cycles win at 40% but later cycles win at 55%, the seed is a drag on performance.**

---

## OUTPUT

Save to: `C:\Projects\pipeline\stages\04-backtest\rotational\frozen_anchor_sweep\`

```
frozen_anchor_sweep/
├── config_summary.csv          # 210 rows, all metrics
├── cycle_logs/                 # 210 cycle CSVs + 210 incomplete CSVs
├── sweep_metadata.json         # Run metadata
└── smoke_test_report.md        # Smoke test results with RT comparison
```

### sweep_metadata.json

```json
{
    "run_timestamp": "2026-XX-XX",
    "strategy": "frozen_anchor",
    "p1_date_range": "2025-09-22 to 2025-12-12",
    "bar_type": "1tick",
    "total_bars": 25457094,
    "rth_trading_days": 60,
    "total_configs": 210,
    "config_groups": {
        "MA0": 35,
        "R04_MA1": 35,
        "R04_MA2": 35,
        "R05_MA1": 35,
        "R03_MA2": 35,
        "R03_MA3": 35
    },
    "cost_ticks": 2.0,
    "context_thresholds": {"swing_zigzag": 5, "persistence_zigzag": 10},
    "total_runtime_seconds": 0,
    "verification": {
        "v11_check_cycles": 4856,
        "success_rate_at_rt100": 0.494,
        "fractal_check": "add_count != retracement_count (survivorship bias)"
    }
}
```

---

## SELF-CHECK BEFORE FINISHING

- [ ] P1 1-tick data loaded: 25,457,094 bars, 60 RTH days
- [ ] Context tags pre-computed once (reused from V1.1 sweep if available)
- [ ] Config count: exactly 210 (7 SD × 5 RT × 6 add groups)
- [ ] No dead configs: ratio 0.3 max MA=3, ratio 0.4 max MA=2, ratio 0.5 max MA=1
- [ ] MaxAdds=0 deduplicated: one per SD×RT (AddDist irrelevant)
- [ ] cost_ticks = 2.0 for all configs
- [ ] Smoke test: 5 configs passed, success rate increases as RT decreases
- [ ] All 210 configs ran to completion
- [ ] config_summary.csv has exactly 210 rows
- [ ] Every config has matching cycle log + incomplete log
- [ ] success_rate and win_rate both computed (they are different metrics)
- [ ] adjusted_net_pnl computed: net_pnl + incomplete_unrealized_pnl
- [ ] failure_after_failure computed
- [ ] first_cycle vs later_cycle success rates computed
- [ ] avg_progress_hwm for success and failure cycles computed
- [ ] All diagnostic columns present in cycle logs
- [ ] sweep_metadata.json populated with actual values
- [ ] All files saved to `frozen_anchor_sweep/`
