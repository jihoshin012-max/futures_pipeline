# shared/onboarding/

Pipeline onboarding scripts. Each script does one job and writes only
to its designated extension point. Run from the repo root.

## Scripts

### register_source.py
Register a new data source.
- Writes: `_config/data_registry.md` (new row)
- Creates: `stages/01-data/references/{source_id}_schema.md` (stub)
- Creates: `stages/01-data/data/{subfolder}/` (with .gitkeep)

```bash
python shared/onboarding/register_source.py \
  --source-id bar_data_250vol_rot \
  --type price \
  --description "250-vol OHLCV bars for rotational archetype" \
  --bar-type volume \
  --file-pattern "NQ_BarData_250vol_rot_*.csv" \
  --periods "P1, P2" \
  --required-by "02-features, 04-backtest"
```

### register_archetype.py
Register a new strategy archetype.
- Writes: `_config/period_config.md` (per-archetype period rows)
- Writes: `stages/03-hypothesis/references/strategy_archetypes.md` (entry)
- Creates: `shared/archetypes/{name}/` (4 required stub files)
- Creates: `shared/scoring_models/{name}_v1.json` (stub)
- Calls: `scaffold_adapter.py` if adapter is new

```bash
python shared/onboarding/register_archetype.py \
  --name rotational \
  --instrument NQ \
  --p1-start 2025-09-21 --p1-end 2025-12-14 \
  --p2-start 2025-12-15 --p2-end 2026-03-13 \
  --data-sources "bar_data_250vol_rot, bar_data_250tick_rot" \
  --adapter new \
  --opt-surface "allocation_weights, rebalance_threshold, lookback_bars"
```

### register_instrument.py
Register a new instrument symbol.
- Writes: `_config/instruments.md` (new instrument block)

```bash
python shared/onboarding/register_instrument.py \
  --symbol MNQ \
  --exchange CME \
  --full-name "Micro E-mini Nasdaq-100 Futures" \
  --tick-size 0.25 \
  --tick-value 0.50 \
  --cost-ticks 2 \
  --session-rth "09:30-16:15 ET"
```

## What these scripts do NOT do

- Commit — autocommit.sh handles that
- Touch CONTEXT.md files — update per _config/context_review_protocol.md
- Run Stage 01 — run manually after dropping data files in place
- Write audit entries — pre-commit hook handles PERIOD_CONFIG_CHANGED automatically

## Correct sequence for a new strategy

1. `register_instrument.py` (if new symbol)
2. `register_source.py` (once per new data source)
3. Drop data files into the correct subfolder
4. `register_archetype.py`
5. Complete simulation_rules.md and Description field manually
6. `python stages/01-data/validate.py`
7. Review validation_report.md
8. Complete new archetype intake checklist (functional spec)
