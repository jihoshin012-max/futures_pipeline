# Schema: NQ_ZTE_raw_P*.csv

Source: ZoneTouchEngine v4.0 (ACSIL study on 250-vol chart)
Pipeline location: `stages/01-data/data/touches/NQ_ZTE_raw_{P1,P2}.csv`
Columns: 52
One row per zone touch event (demand edge, supply edge, or VP ray).

## Column Definitions

| # | Column | Type | Example | Description |
|---|--------|------|---------|-------------|
| 1 | DateTime | datetime | 2025-09-23 09:34:53 | Touch timestamp (SC bar close time) |
| 2 | BarIndex | int | 3 | Base chart (250-vol) bar index |
| 3 | TouchType | string | DEMAND_EDGE | DEMAND_EDGE, SUPPLY_EDGE, or VP_RAY |
| 4 | ApproachDir | int | -1 | -1 = from above (demand), +1 = from below (supply) |
| 5 | TouchPrice | float | 25050.00 | Price at zone edge where touch detected |
| 6 | ZoneTop | float | 25050.00 | Upper boundary of touched zone |
| 7 | ZoneBot | float | 25009.25 | Lower boundary of touched zone |
| 8 | HasVPRay | int | 1 | 1 = VP imbalance ray present near zone (3x width filter) |
| 9 | VPRayPrice | float | 25016.75 | VP imbalance ray price (0 if HasVPRay=0) |
| 10 | Reaction | float | 426.0 | Max favorable excursion in ticks over observation window |
| 11 | Penetration | float | 688.0 | Max adverse excursion in ticks over observation window |
| 12 | ReactionPeakBar | int | 4 | Bar index where max reaction was reached |
| 13 | ZoneBroken | int | 1 | 1 = zone was broken during observation window |
| 14 | BreakBarIndex | int | 5 | Bar index where zone broke (-1 if not broken) |
| 15 | BarsObserved | int | 2 | Bars between touch and resolution (-1 if unresolved) |
| 16 | TouchSequence | int | 1 | Nth touch of this zone (1 = first touch) |
| 17 | ZoneAgeBars | int | 1 | Bars since zone first appeared |
| 18 | ApproachVelocity | float | 0.0 | Price change over 10-bar lookback (ticks) |
| 19 | TrendSlope | float | 0.0 | Price change over 50-bar lookback (ticks) |
| 20 | SourceLabel | string | 360m | Timeframe label of the V4 instance that produced the zone |
| 21 | SourceChart | int | 8 | SC chart number of the source TF chart |
| 22 | SourceStudyID | int | 3 | V4 study ID on the source TF chart |
| 23 | RxnBar_30 | int | 4 | First bar where reaction >= 30 ticks (-1 = never) |
| 24 | RxnBar_50 | int | 4 | First bar where reaction >= 50 ticks (-1 = never) |
| 25 | RxnBar_80 | int | 4 | First bar where reaction >= 80 ticks (-1 = never) |
| 26 | RxnBar_120 | int | 4 | First bar where reaction >= 120 ticks (-1 = never) |
| 27 | RxnBar_160 | int | 4 | First bar where reaction >= 160 ticks (-1 = never) |
| 28 | RxnBar_240 | int | 4 | First bar where reaction >= 240 ticks (-1 = never) |
| 29 | RxnBar_360 | int | 4 | First bar where reaction >= 360 ticks (-1 = never) |
| 30 | PenBar_30 | int | 5 | First bar where penetration >= 30 ticks (-1 = never) |
| 31 | PenBar_50 | int | 5 | First bar where penetration >= 50 ticks (-1 = never) |
| 32 | PenBar_80 | int | 5 | First bar where penetration >= 80 ticks (-1 = never) |
| 33 | PenBar_120 | int | 5 | First bar where penetration >= 120 ticks (-1 = never) |
| 34 | ZoneWidthTicks | int | 163 | (ZoneTop - ZoneBot) / tick_size |
| 35 | CascadeState | string | PRIOR_BROKE | PRIOR_HELD, PRIOR_BROKE, NO_PRIOR, UNKNOWN |
| 36 | CascadeActive | int | 1 | 1 = cascade event within lookback window |
| 37 | TFWeightScore | int | 25 | Timeframe weight component of quality score |
| 38 | TFConfluence | int | 2 | Number of higher TFs with aligned zones |
| 39 | SessionClass | int | 0 | 0=Open, 1=MidDay, 2=Afternoon, 3=OffHours |
| 40 | DayOfWeek | int | 2 | 0=Sun, 1=Mon, ..., 6=Sat |
| 41 | ModeAssignment | string | M3 | M1F, M1H, M3, M4, M5, SKIP |
| 42 | QualityScore | int | 60 | A-Cal quality score (TF weight + zone width + VP ray) |
| 43 | ContextScore | int | 28 | A-Cal context score (cascade + session + velocity + pen) |
| 44 | TotalScore | int | 88 | QualityScore + ContextScore |
| 45 | SourceSlot | int | 6 | Chart slot index (0-8) in ZTE's input configuration |
| 46 | ConfirmedBar | int | 3 | Bar index where signal was confirmed |
| 47 | HtfConfirmed | int | 1 | 1 = HTF confirmation present |
| 48 | Active | int | 1 | 1 = touch still active (unresolved) at export time |
| 49 | DemandRayPrice | float | 25050.00 | Nearest broken demand zone ray price (0 = none) |
| 50 | SupplyRayPrice | float | 25051.75 | Nearest broken supply zone ray price (0 = none) |
| 51 | DemandRayDistTicks | float | 0.0 | Distance from zone edge to nearest demand ray (ticks) |
| 52 | SupplyRayDistTicks | float | 7.0 | Distance from zone edge to nearest supply ray (ticks) |

## Notes

- VP_RAY touches are filtered out by `run_zone_prep.py` before entering the merged CSV
- SourceChart and SourceStudyID are dropped during prep (not in merged output)
- Columns 49-52 (ray summary) are quick-reference only; full ray data is in `NQ_ray_context_*.csv`
- Observation window is configurable in ZTE (default 720 minutes)
- Threshold bar columns (23-33) record the first bar crossing each tick threshold; -1 = threshold never reached
