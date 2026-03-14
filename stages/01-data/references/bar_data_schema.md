# Bar Data Schema
last_reviewed: 2026-03-13
# Required columns for {SYMBOL}_BarData files. Validation fails if any column is missing.
# Source ID: bar_data — must match data_registry.md entry.
# Bar data prefix is registered per instrument in _config/instruments.md.

| Column | Type | Description |
|--------|------|-------------|
| datetime | str | Bar datetime YYYY-MM-DD HH:MM:SS |
| open | float | Bar open price |
| high | float | Bar high price |
| low | float | Bar low price |
| close | float | Bar close price |
| volume | int | Bar volume |

Resolution: 1-minute bars required. Gaps > 5 bars flagged in validation_report.md.
Bar offset: validated in Stage 01 — signal bar index must align to correct bar.

## Notes
- NQ tick bars: file pattern NQ_BarData_*.txt per _config/data_registry.md
- Additional columns (Trades, BidVol, AskVol) may be present — they are not required but are not errors
- Datetime format must parse without ambiguity; UTC or local-consistent timestamps required
