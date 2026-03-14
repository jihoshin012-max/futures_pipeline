# Zone CSV v2 Schema
last_reviewed: 2026-03-13
# Required columns for ZRA zone touch event files. Validation fails if any column is missing.
# Source ID: zone_csv_v2 — must match data_registry.md entry.
# File pattern: ZRA_Hist_*.csv (32 columns total, V4/ZRA format)

| Column | Type | Description |
|--------|------|-------------|
| datetime | str | Touch event datetime YYYY-MM-DD HH:MM:SS |
| Reaction | float | Price reaction magnitude in ticks |
| Penetration | float | Zone penetration depth in ticks |
| RxnBar_Open | float | Bar open at reaction bar |
| RxnBar_High | float | Bar high at reaction bar |
| RxnBar_Low | float | Bar low at reaction bar |
| RxnBar_Close | float | Bar close at reaction bar |
| RxnBar_Volume | int | Bar volume at reaction bar |

## Notes
- Full ZRA_Hist CSV format has 32 columns; additional columns beyond the required set are permitted
- Columns above are the minimum required for Stage 02 feature engineering
- If a required column is missing, Stage 01 validation fails with schema_error in validation_report.md
- Spot-check 10 rows against source files to verify column alignment after any data migration
- Source files use file pattern ZRA_Hist_*.csv per _config/data_registry.md
