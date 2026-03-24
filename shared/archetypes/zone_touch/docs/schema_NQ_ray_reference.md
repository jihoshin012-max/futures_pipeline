# Schema: NQ_ray_reference_P*.csv

Source: RayValidator.cpp (ACSIL study on 250-vol chart)
Pipeline location: `stages/01-data/data/touches/NQ_ray_reference_{P1,P2}.csv`
Columns: 10
One row per base-chart bar per HTF chart slot where V4 reports a non-zero ray price.

## Purpose

Ground truth for validating ZTE's ray accumulator. RayValidator reads V4 SG 12/13
directly from each TF chart and writes every non-zero ray price it sees. ZTE's
accumulated rays are compared against this reference to verify completeness.

## Column Definitions

| # | Column | Type | Example | Description |
|---|--------|------|---------|-------------|
| 1 | BaseBarIndex | int | 92 | Bar index on the 250-vol base chart |
| 2 | DateTime | datetime | 2025-12-19 09:30:28 | Timestamp of the base chart bar |
| 3 | ChartSlot | int | 0 | ZTE chart slot index (0-8) |
| 4 | SourceLabel | string | 15m | Timeframe label for this chart slot |
| 5 | ChartNumber | int | 3 | SC chart number of the HTF chart |
| 6 | HtfBarIndex | int | 552 | Bar index on the HTF chart (V4's bar) |
| 7 | DemandRayPrice | float | 0.00 | V4 SG 12 value — broken demand zone ray price (0 = none) |
| 8 | SupplyRayPrice | float | 25707.50 | V4 SG 13 value — broken supply zone ray price (0 = none) |
| 9 | DemandBrokenCount | int | 0 | V4 SG 6 value — demand break count on this bar |
| 10 | SupplyBrokenCount | int | 1 | V4 SG 7 value — supply break count on this bar |

## Validation Usage

```python
# Extract unique (price, side) pairs from reference
ref_rays = set()
for _, r in ray_ref.iterrows():
    if r['DemandRayPrice'] > 0:
        ref_rays.add((r['DemandRayPrice'], 'DEMAND'))
    if r['SupplyRayPrice'] > 0:
        ref_rays.add((r['SupplyRayPrice'], 'SUPPLY'))

# Compare against ZTE ray_context
zte_rays = set((r['RayPrice'], r['RaySide']) for _, r in ray_ctx.iterrows())
missing = ref_rays - zte_rays
match_rate = (len(ref_rays) - len(missing)) / len(ref_rays)
```

## Notes

- RayValidator uses the same chart slot configuration (Input[]) as ZTE — both read from the same 9 TF charts
- Rows are only written when at least one of DemandRayPrice or SupplyRayPrice is non-zero
- BrokenCount columns are informational (how many zones broke on that HTF bar), not used in validation
- Ray prices follow V4's convention: demand ray = TopPrice of broken demand zone, supply ray = BottomPrice of broken supply zone
- RayValidator is a validation-only tool — it does not participate in the live study chain
