# Ray Context CSV Schema
last_reviewed: 2026-03-23
# ZoneTouchEngine v4.0 ray-touch pairs in long format.
# Source ID: ray_context — must match data_registry.md entry.
# File pattern: NQ_ray_context_*.csv (7 columns)

| # | Column | Type | Description |
|---|--------|------|-------------|
| 0 | TouchID | str | Unique touch identifier: BarIndex_TouchType_SourceLabel |
| 1 | RayPrice | float | Broken zone edge price |
| 2 | RaySide | str | DEMAND or SUPPLY (which type of broken zone) |
| 3 | RayDirection | str | ABOVE or BELOW (relative to touch zone edge) |
| 4 | RayDistTicks | float | Distance from touch zone edge to ray in ticks (0.0 valid) |
| 5 | RayTF | str | Source timeframe of broken zone (15m, 30m, ..., 720m) |
| 6 | RayAgeBars | int | Bars since zone broke (touch bar - break bar) |

## Notes
- One row per (touch, nearby ray) pair; a touch with 6 nearby rays produces 6 rows
- Proximity filter: only rays within 2x max zone width of the touch price
- RayDistTicks=0.0 is valid (ray price equals touch price exactly)
- RayAgeBars < 0 should never occur (would indicate a future ray)
- TouchID can be joined to zte_raw via BarIndex (first component of TouchID)
- Import from SC via: make import-zte
