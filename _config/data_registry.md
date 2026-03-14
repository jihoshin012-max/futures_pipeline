# Data Registry
last_reviewed: 2026-03-13
## THE RULE
No stage hardcodes file paths. All paths come from data_manifest.json (Stage 01 output),
which is generated from this registry.

## Registered Sources

| source_id    | type       | description                              | periods | file_pattern                    | required_by                    |
|--------------|------------|------------------------------------------|---------|---------------------------------|--------------------------------|
| bar_data     | price      | 1-min OHLCV bar data (tick bars)         | P1, P2  | NQ_BarData_*.txt                | 02-features, 04-backtest       |
| zone_csv_v2  | touches    | ZRA zone touch events (V4/ZRA, 32 cols)  | P1, P2  | ZRA_Hist_*.csv                  | 03-hypothesis, 04-backtest     |

Note: Add one row per data source your archetype requires. source_id must be unique and
match the schema file name in 01-data/references/{source_id}_schema.md.

## Data Type Taxonomy
| type        | description                            |
|-------------|----------------------------------------|
| touches     | Per-touch or per-signal event data     |
| price       | OHLCV bar data                         |
| label       | Derived classification labels          |
| orderflow   | Intrabar volume/delta data             |
| fundamental | Macro/economic data                    |
| alt         | Anything else                          |

## To Add a New Source
1. Drop files into 01-data/data/<source_id>/
2. Add row to this table
3. Re-run Stage 01 validation (regenerates data_manifest.json automatically)
4. Human checkpoint: review validation report
