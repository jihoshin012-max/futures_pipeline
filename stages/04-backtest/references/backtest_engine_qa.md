---
last_reviewed: 2026-03-14
---
# Backtest Engine Q&A

Design decisions for `backtest_engine.py`. Answers are frozen — do not revise without a matching plan update.

## Q1

**Does backtest_engine.py read data_manifest.json?**

NO. The engine takes explicit path strings from the config JSON (`touches_csv`, `bar_data`). It never reads `data_manifest.json` or resolves period labels. The driver loop (autoresearch harness) is responsible for setting the correct paths in the config before each run. This keeps the engine stateless and period-agnostic.

## Q2

**How does BinnedScoringAdapter work?**

`BinnedScoringAdapter` uses 14 features: 7 static (raw values from touch row) and 7 percentile-binned (mapped via `bin_edges` arrays). Weights and `bin_edges` are loaded from a JSON model file at the path specified in `config.scoring_model_path`. The adapter computes a weighted score per touch row and returns a `pd.Series[float]` aligned to the input DataFrame's index. The engine calls `adapter.score(touches)` — it never touches `bin_edges` or `weights` directly.

## Q3

**Is be_trigger_ticks a separate config field?**

NO. `trail_steps[0]` with `new_stop_ticks=0` IS the breakeven trigger. When MFE reaches `trail_steps[0].trigger_ticks`, the stop moves to entry (zero risk). There is no separate `be_trigger_ticks` field. This is the single source of truth for BE behavior — confirmed in `exit_templates.md` and enforced by the trail step validation rules in `config_schema.md`.

## Q4

**How does the engine resolve cost_ticks?**

The engine reads `cost_ticks` from `_config/instruments.md` at startup using `config.instrument` to locate the correct instrument section. It is NEVER hardcoded in the engine, config JSON, or simulator. Per CLAUDE.md Rule 5: instrument constants (tick size, cost_ticks, session times) come only from the registry. The resolved value is passed through to metrics aggregation — individual trade `pnl_ticks` is raw; cost is applied when computing PF.

## Q5

**How does the holdout guard work?**

The guard checks two conditions: (1) `stages/04-backtest/p2_holdout/holdout_locked_P2.flag` exists on disk, AND (2) any config path (`touches_csv`, `bar_data`) contains case-insensitive "p2" in the filename. If both conditions are true, the engine raises `SystemExit` before any data loads. The check cannot be bypassed by config — it runs as the first operation in `main()` and does not depend on any config flag or environment variable.

## Q6

**What is the output schema?**

The engine writes `result.json` with the following schema:

```json
{
  "pf": float,
  "n_trades": int,
  "win_rate": float,
  "total_pnl_ticks": float,
  "max_drawdown_ticks": float,
  "per_mode": {
    "{mode_name}": {"pf": float, "n_trades": int, "win_rate": float}
  }
}
```

`per_mode` keys are driven by `config.active_modes` — not hardcoded. All metrics are net of cost (cost_ticks applied from instruments.md). `pf` is profit factor: sum(winning pnl) / abs(sum(losing pnl)).
