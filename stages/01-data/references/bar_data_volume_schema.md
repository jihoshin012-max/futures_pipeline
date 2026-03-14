# Bar Data Volume Schema
last_reviewed: 2026-03-13
# Required columns for {SYMBOL}_BarData_250vol_* files.
# Source ID: bar_data_volume — must match data_registry.md entry.
# Bar type: Volume bars — each bar closes after exactly N contracts traded.
# Bar size (N=250 for NQ zone_touch): encoded in filename, not in this schema.

| Column | Type | Description |
|--------|------|-------------|
| datetime | str | Bar datetime YYYY-MM-DD HH:MM:SS |
| open | float | Bar open price |
| high | float | Bar high price |
| low | float | Bar low price |
| close | float | Bar close price |
| volume | int | Bar volume (constant = bar size for volume bars) |

## Notes
- NQ 250-vol bars: file pattern NQ_BarData_250vol_*.txt per _config/data_registry.md
- Additional columns (NumberOfTrades, BidVolume, AskVolume) may be present — not required
- Files live in stages/01-data/data/bar_data/volume/
- Datetime parsed from separate Date + Time columns in raw files; combined on load
