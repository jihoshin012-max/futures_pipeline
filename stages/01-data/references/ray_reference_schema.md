# Ray Reference CSV Schema
last_reviewed: 2026-03-23
# RayValidator v1.1 ground truth for V4 SG 12/13 ray prices.
# Source ID: ray_reference — must match data_registry.md entry.
# File pattern: NQ_ray_reference_*.csv (10 columns)

| # | Column | Type | Description |
|---|--------|------|-------------|
| 0 | BaseBarIndex | int | 250-vol base chart bar index |
| 1 | DateTime | str | Datetime YYYY-MM-DD HH:MM:SS |
| 2 | ChartSlot | int | TF chart slot index (0-8) |
| 3 | SourceLabel | str | Source timeframe (15m, 30m, ..., 720m) |
| 4 | ChartNumber | int | SC chart number |
| 5 | HtfBarIndex | int | Bar index on the HTF chart |
| 6 | DemandRayPrice | float | V4 SG 12 value (0.0 if no demand break) |
| 7 | SupplyRayPrice | float | V4 SG 13 value (0.0 if no supply break) |
| 8 | DemandBrokenCount | float | V4 SG 6 cumulative demand break count |
| 9 | SupplyBrokenCount | float | V4 SG 7 cumulative supply break count |

## Notes
- Validation-only data source — used to verify ZTE's ray accumulator, not consumed by pipeline stages
- Each row represents a non-zero ray event on a specific TF chart at a specific base bar
- Deduped: only emitted on the first base bar mapping to each new HTF bar
- Import from SC via: make import-zte
