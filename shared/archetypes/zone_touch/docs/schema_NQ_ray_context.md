# Schema: NQ_ray_context_P*.csv

Source: ZoneTouchEngine v4.0 (ACSIL study on 250-vol chart)
Pipeline location: `stages/01-data/data/touches/NQ_ray_context_{P1,P2}.csv`
Columns: 7
Long format: one row per (touch, nearby broken zone ray) pair.

A touch with 6 nearby rays produces 6 rows. The pipeline groups by TouchID
and aggregates into features.

## Column Definitions

| # | Column | Type | Example | Description |
|---|--------|------|---------|-------------|
| 1 | TouchID | string | 3_DEMAND_EDGE_360m | Composite key: BarIndex_TouchType_SourceLabel. Joins to ZTE_raw on BarIndex + TouchType + SourceLabel |
| 2 | RayPrice | float | 25084.25 | Price level of the broken zone ray |
| 3 | RaySide | string | SUPPLY | DEMAND or SUPPLY — which side the broken zone was |
| 4 | RayDirection | string | ABOVE | ABOVE or BELOW — ray position relative to the touch zone edge |
| 5 | RayDistTicks | float | 137.0 | Distance from touch zone edge to ray price (always positive, in ticks) |
| 6 | RayTF | string | 240m | Timeframe of the V4 instance that produced the broken zone ray |
| 7 | RayAgeBars | int | 2 | Bars since the ray was first accumulated (ray age at touch time) |

## Proximity Filter

Only rays within 2x the widest zone width of the touch price are included.
This bounds row count without losing analytically relevant rays.

## Join Key

TouchID is a composite string: `{BarIndex}_{TouchType}_{SourceLabel}`

To join with ZTE_raw:
```python
zte['TouchID'] = zte['BarIndex'].astype(str) + '_' + zte['TouchType'] + '_' + zte['SourceLabel']
merged = ray_ctx.merge(zte, on='TouchID', how='left')
```

## Notes

- RayDistTicks is always > 0 (distance, not signed offset)
- RayAgeBars should always be >= 0
- RayDirection indicates resistance (ABOVE) vs support (BELOW) context relative to the touch
- Entry-relative ray features (RaysBetweenEntryTarget, NearestRayDir) are computed in Python, not in this file
- Ray prices come from V4 SG 12 (DemandRayPrice) and SG 13 (SupplyRayPrice), accumulated across all HTF bars
