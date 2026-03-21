# Phase 1, Prompt 2: Generate Configs and Run the Sweep

## OBJECTIVE

Generate all ~182 configuration objects for Approaches A-D, pre-compute regime context on P1 bar data, run every config through the simulator from Prompt 1, and produce per-config summary tables. The deliverable is a complete set of cycle logs and summary metrics ready for cross-approach analysis in Prompt 3.

---

## PREREQUISITES

⚠️ **All of these must be true before proceeding. Verify each one.**

1. Prompt 1 deliverables exist at `C:\Projects\pipeline\stages\04-backtest\rotational\`:
   - `rotation_simulator.py`
   - `config_schema.py` (RotationConfig dataclass)
   - `context_tagger.py`
   - `cycle_logger.py`
2. Prompt 1 Phase 0 re-verification PASSED (check `verification_report.md`)
3. P1 bar data is available for Sept 21, 2025 – Dec 17, 2025

Confirm all three before writing any code.

---

## DATA PREPARATION

### Step 1: Load P1 Bar Data

Load bar data covering **P1 only: Sept 21, 2025 through Dec 17, 2025.**

⚠️ **Do NOT load data after Dec 17, 2025. P2a and P2b are holdout periods. Loading them here contaminates validation.**

- Source: `C:\Projects\pipeline\stages\01-data\data\bar_data\tick\`
- Use the same bar type that Phase 0 calibration ran on
- Filter to RTH only (09:30–16:15 ET)
- Load only the columns needed: DateTime, Open, High, Low, Close/Last, Volume

Report after loading: total rows, date range confirmed, number of RTH trading days.

### Step 2: Pre-Compute Context Tags

Run `context_tagger.py` from Prompt 1 on the loaded P1 bar data. This adds the following columns to the bar DataFrame:

- `atr_20`, `atr_pct` (ATR and percentile)
- `bar_range`, `bar_range_median_20`
- `swing_median_20`, `swing_p90_20` (from 5pt zig-zag)
- `directional_persistence` (from 10pt zig-zag)

📌 **This runs ONCE, before any simulation. The enriched DataFrame is then passed to every config's simulation run. Do not re-compute context inside the simulation loop.**

Verify after tagging: spot-check 5 random bars and confirm context columns have reasonable values (ATR > 0, swing stats > 0, persistence ≥ 0). Report any NaN rows at the start of the data (expected: first ~500 bars will have NaN for atr_pct due to the rolling window).

---

## CONFIG GENERATION

### Approach A: Pure Rotation (7 configs)

```python
for sd in [15, 20, 25, 30, 35, 40, 50]:
    RotationConfig(
        config_id=f"A_SD{sd}",
        approach="A",
        step_dist=sd,
        max_adds=0,
        cost_ticks=COST_TICKS  # from instruments.md or default 2.0
    )
```

### Approach B: Traditional Martingale (84 configs)

⚠️ **All configs below import RotationConfig from config_schema.py (Prompt 1 deliverable). COST_TICKS should be read from `_config/instruments.md` if available, otherwise default to 2.0 ticks per side (covers ~$4-5 commission + ~$2-5 slippage for 1-lot NQ market orders). Use the SAME cost_ticks value for every config. Prompt 3 will re-score winners at 3.0 ticks as a sensitivity check.**

```python
for sd in [15, 20, 25, 30, 35, 40, 50]:
    for ad_ratio in [1.0, 0.5, 0.4]:  # AddDist = sd * ratio
        ad = round(sd * ad_ratio, 2)
        for ma in [1, 2, 3, 4]:
            RotationConfig(
                config_id=f"B_SD{sd}_AD{ad}_MA{ma}",
                approach="B",
                step_dist=sd,
                add_dist=ad,
                max_adds=ma,
                cost_ticks=COST_TICKS
            )
```

⚠️ **AddDist ratios are 1.0, 0.5, and 0.4 (corresponding to parent/child ratios of 1.0, 2.0, and 2.5). The hypothesis doc says "StepDist, StepDist/2, StepDist/2.5" — the 0.4 ratio gives StepDist/2.5. Example: SD=25 → AddDist = 25, 12.5, 10.**

### Approach C: Anti-Martingale (35 configs after pruning)

```python
for sd in [15, 20, 25, 30, 35, 40, 50]:
    for cd_frac in [0.4, 0.5, 0.6, 0.7]:
        cd = round(sd * cd_frac, 2)
        for ma in [1, 2]:
            # PRUNE: MaxAdds=2 with ConfirmDist >= 0.5*SD is dead.
            # Second add at 2*ConfirmDist >= 1.0*SD, but reversal fires
            # at 1.0*SD first (priority rule). Only cd_frac=0.4 with
            # MaxAdds=2 produces a meaningful second add (at 0.8*SD).
            if ma == 2 and cd_frac >= 0.5:
                continue
            RotationConfig(
                config_id=f"C_SD{sd}_CD{cd}_MA{ma}",
                approach="C",
                step_dist=sd,
                confirm_dist=cd,
                max_adds=ma,
                cost_ticks=COST_TICKS
            )
# Result: 7 StepDists × 4 ConfirmDists × MA1 = 28
#        + 7 StepDists × 1 ConfirmDist(0.4) × MA2 = 7
#        Total: 35 configs
```

### Approach D: Scaled Entry (56 unique configs after dedup)

📌 **Reminder: Approach D is mechanically identical to C (same anchor rule, same successive-multiple spacing). The only difference is add_size > 1. Deduplication below removes all D configs where add_size=1 since those are already covered by C.**

```python
generated_d = []
for sd in [15, 20, 25, 30, 35, 40, 50]:
    for cd_frac in [0.4, 0.5, 0.6, 0.7]:
        cd = round(sd * cd_frac, 2)
        for add_sz in [1, 2, 3]:
            config_id = f"D_SD{sd}_CD{cd}_AS{add_sz}"
            # Dedup: D with add_size=1 is identical to C with max_adds=1
            if add_sz == 1:
                # Skip — already covered by C_SD{sd}_CD{cd}_MA1
                continue
            generated_d.append(RotationConfig(
                config_id=config_id,
                approach="D",
                step_dist=sd,
                confirm_dist=cd,
                max_adds=1,  # D always does 1 add (the conviction add)
                add_size=add_sz,
                cost_ticks=COST_TICKS
            ))
```

📌 **Deduplication rule: Approach D with add_size=1 produces identical simulation results to Approach C with max_adds=1. Skip all D configs where add_size=1. This removes 28 duplicates (7 StepDists × 4 ConfirmDists). Net D configs: 7 × 4 × 2 remaining add_sizes = 56. Note: D does NOT need the same pruning as C because D always has max_adds=1 — there is no "dead second add" issue.**

⚠️ **Approach D max_adds is always 1. The "scaled entry" concept is: 1 probe entry + 1 conviction add at ConfirmDist. The conviction add size varies (2 or 3 contracts). If you set max_adds > 1 for D, you get multiple conviction adds which is not the intended mechanic. Keep max_adds=1 for all D configs.**

### Total Config Count

```python
total_a = 7
total_b = 84
total_c = 35   # after pruning dead MaxAdds=2 configs
total_d = 56   # after dedup with C
total = total_a + total_b + total_c + total_d  # = 182
```

Report the exact count after generation. It should be 182.

---

## SWEEP EXECUTION

### Run All Configs

```python
all_cycle_logs = []
config_summaries = []

for config in all_configs:
    cycle_log = run_simulation(bars_with_context, config)
    all_cycle_logs.append(cycle_log)
    summary = compute_config_summary(cycle_log, config)
    config_summaries.append(summary)
    
    # Progress reporting
    print(f"[{idx}/{total}] {config.config_id}: "
          f"{summary['cycle_count']} cycles, NPF={summary['npf_net']:.3f}")
```

⚠️ **Performance note: 182 configs on ~3 months of 1-tick data (~32M rows). If each config takes 30-90 seconds with numba, total runtime is 1.5-4.5 hours. Consider parallelization (multiprocessing) if available. The bar data with context tags can be shared read-only across processes. If parallelizing, do NOT share mutable state — each process gets its own simulator instance.**

📌 **Progress reporting is mandatory. Print config_id, cycle count, and net NPF after each config completes. If a config produces 0 cycles, flag it as a warning — it likely means StepDist is too large for the data window.**

### Per-Config Summary Metrics

For each config, compute from its cycle log:

| Metric | Description |
|--------|-------------|
| config_id | Unique identifier |
| approach | A/B/C/D |
| step_dist | Reversal distance |
| add_dist / confirm_dist | Trigger distance (whichever applies) |
| max_adds / add_size | Config parameters |
| cycle_count | Total completed cycles |
| win_count | Cycles with pnl_ticks_net > 0 |
| loss_count | Cycles with pnl_ticks_net ≤ 0 |
| win_rate | win_count / cycle_count |
| gross_pnl | Sum of pnl_ticks_gross (qty-weighted, not per-unit) |
| net_pnl | Sum of pnl_ticks_net (qty-weighted, not per-unit) |
| total_costs | Sum of all costs (gross_pnl - net_pnl) |
| npf_gross | gross_wins / abs(gross_losses). Set to 999.0 if no losses. |
| npf_net | net_wins / abs(net_losses). Set to 999.0 if no losses. |
| avg_win_net | Mean net PnL of winning cycles |
| avg_loss_net | Mean net PnL of losing cycles |
| max_drawdown_ticks | Maximum peak-to-trough drawdown in cumulative net PnL |
| profit_per_dd | net_pnl / max_drawdown_ticks (risk-adjusted return) |
| max_position | Maximum contracts held across all cycles |
| avg_cycle_duration_bars | Mean duration in bars |

⚠️ **The following cycle-type columns break down performance by add count. These are essential — they show whether the approach's edge comes from clean rotations, 1-add cycles, or multi-add cycles.**

| Metric | Description |
|--------|-------------|
| cycles_0_adds | Count of clean rotations (0 adds) |
| cycles_1_add | Count of 1-add cycles |
| cycles_multi_add | Count of 2+ add cycles |
| pnl_0_adds | Net PnL from clean rotations only |
| pnl_1_add | Net PnL from 1-add cycles only |
| pnl_multi_add | Net PnL from 2+ add cycles |
| flatten_reseed_would_fire | Count of cycles where would_flatten_reseed = TRUE (B only) |

⚠️ **NPF calculation: separate wins and losses by net PnL sign. NPF = sum(positive net PnLs) / abs(sum(negative net PnLs)). If there are zero losing cycles, set NPF to 999.0 (not infinity). If there are zero winning cycles, set NPF to 0.0.**

📌 **The cycle-type breakdown (0 adds / 1 add / multi-add) with per-type PnL is critical for understanding WHERE each approach makes and loses money. Do not skip these columns.**

### Drawdown Calculation

```python
cumulative = cycle_log['pnl_ticks_net'].cumsum()
rolling_max = cumulative.cummax()
drawdown = cumulative - rolling_max
max_drawdown_ticks = abs(drawdown.min())
```

⚠️ **Drawdown is computed on the cycle-level cumulative PnL curve (one point per completed cycle), not on bar-by-bar equity. This is intentional — it measures strategy-level drawdown, not intra-cycle noise.**

---

## SMOKE TEST

Before running all 182 configs, run a smoke test on 4 configs — one from each approach:

```python
smoke_configs = [
    RotationConfig("SMOKE_A", "A", step_dist=25.0, cost_ticks=2.0),
    RotationConfig("SMOKE_B", "B", step_dist=25.0, add_dist=10.0, max_adds=2, cost_ticks=2.0),
    RotationConfig("SMOKE_C", "C", step_dist=25.0, confirm_dist=10.0, max_adds=1, cost_ticks=2.0),
    RotationConfig("SMOKE_D", "D", step_dist=25.0, confirm_dist=10.0, max_adds=1, add_size=2, cost_ticks=2.0),
]
```

Verify for each smoke config:
- Produces > 0 cycles
- Cycle log has all expected columns (standard + context + shadow)
- Net PnL < gross PnL (costs are being applied)
- Approach A: max position = 1 for every cycle
- Approach B: some cycles have adds, position > 1
- Approach C: adds only appear when price moved in favor
- Approach D: same as C but exit_position = 3 on cycles with an add (1 probe + 2 conviction)

⚠️ **If any smoke test fails, debug before running the full sweep. A bug caught on 4 configs saves hours vs catching it after 182.**

---

## OUTPUT

Save all results to: `C:\Projects\pipeline\stages\04-backtest\rotational\sweep_results\`

```
sweep_results/
├── config_summary.csv          # One row per config, all summary metrics
├── cycle_logs/                 # One CSV per config
│   ├── A_SD15.csv
│   ├── A_SD20.csv
│   ├── ...
│   ├── B_SD25_AD10_MA2.csv
│   ├── ...
│   ├── C_SD25_CD12.5_MA1.csv
│   ├── ...
│   └── D_SD25_CD12.5_AS2.csv
├── sweep_metadata.json         # Run timestamp, data range, bar count, config count
└── smoke_test_report.md        # Smoke test results
```

📌 **The config_summary.csv is the primary input for Prompt 3 (analysis). The cycle_logs/ directory contains the raw data for deep dives. Both must be complete and consistent — every row in config_summary.csv must have a corresponding cycle log file.**

### sweep_metadata.json

```json
{
    "run_timestamp": "2026-XX-XXTXX:XX:XX",
    "p1_date_range": "2025-09-21 to 2025-12-17",
    "bar_type": "1tick or 250tick",
    "total_bars": 99999,
    "rth_trading_days": 99,
    "total_configs": 182,
    "configs_by_approach": {"A": 7, "B": 84, "C": 35, "D": 56},
    "cost_ticks": 2.0,
    "context_thresholds": {"swing_zigzag": 5, "persistence_zigzag": 10},
    "total_runtime_seconds": 99999
}
```

---

## SELF-CHECK BEFORE FINISHING

- [ ] P1 data loaded: Sept 21 – Dec 17, 2025 only. No data after Dec 17.
- [ ] RTH filter applied: 09:30–16:15 ET only
- [ ] Context tags pre-computed once on bar DataFrame (not per-config)
- [ ] Context columns spot-checked: reasonable values, NaNs only at start
- [ ] Config count: exactly 182 (7 + 84 + 35 + 56 after pruning and dedup)
- [ ] Deduplication: no D configs with add_size=1 (already covered by C)
- [ ] Pruning: no C configs with MaxAdds=2 and ConfirmDist ≥ 0.5×StepDist (reversal fires first)
- [ ] D configs: max_adds=1 for all (single conviction add)
- [ ] B configs: AddDist ratios are 1.0, 0.5, 0.4 (not 1/2, 1/2.5 — those are the same as 0.5, 0.4)
- [ ] cost_ticks = 2.0 for all configs (sensitivity at 3.0 deferred to Prompt 3)
- [ ] Smoke test: 4 configs passed (one per approach A-D) before full sweep
- [ ] All 182 configs ran to completion
- [ ] Any 0-cycle configs flagged and documented
- [ ] config_summary.csv has exactly 182 rows
- [ ] Every config_summary row has a matching cycle log CSV
- [ ] NPF computed correctly: wins/abs(losses), 999.0 if no losses, 0.0 if no wins
- [ ] PnL is qty-weighted (not per-unit) in all summary metrics and cycle logs
- [ ] Drawdown computed on cycle-level cumulative PnL, not bar-level
- [ ] sweep_metadata.json populated with actual values
- [ ] All files saved to `stages/04-backtest/rotational/sweep_results/`
