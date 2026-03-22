# VP Ray Investigation — Findings & Resolution

Date: 2026-03-22
Status: CLOSED for current pipeline. V4 fix queued.

## Summary

VP Ray features (F19, F20) were screened on garbage data in v3.1
and correctly excluded from scoring. Investigation revealed a V4
architecture issue that cannot be resolved for historical data.

## Root Cause Chain

1. V4 computes VP imbalance from VolumeAtPriceForBars at zone
   birth bars (2 bars per zone)
2. SC purges per-bar VAP data after some retention period
3. On chart recalc (required for historical export), VAP is gone
4. V4 checks prof.Valid — if false, skips subgraph 14 write
5. Subgraph 14 retains stale values from last valid computation
6. Stale values: NQ ~22,000 when actual price was ~24,800-25,500
7. ZRA/ZBV4 read subgraph 14 and propagate stale values

## Fixes Applied

- MaxVPProfiles: 50 → 0 (=500, all zones get profiles)
- ZBV4 proximity filter: rejects VP > 3x zone width from edge
- ZRA proximity filter: same fix (ZRA is pipeline CSV source)
- All compiled and active in C:\Projects\sierrachart\

## Results After Fix

| Period | HasVPRay=1 (v3.1 stale) | HasVPRay=1 (fixed) |
|--------|------------------------|--------------------|
| P1 | 4,701/4,701 (100% stale) | 0/4,701 (0%) |
| P2 | ~4,552/4,660 (97.7% stale) | 108/4,660 (2.3%) |

P1: zero legitimate VP data — VAP completely purged
P2: 108 legitimate — some recent bars had VAP

## Cannot Fix Retroactively

VAP data for P1 bars (Sep-Dec 2025) is permanently gone. No code
change recovers it. VP features cannot be screened on P1.

## V4 Fix Required (Autoresearch Item #11)

Persist ImbalancePrice in ZoneData:
1. Add float ImbalancePrice to ZoneData struct
2. First VP compute (VAP available): store in ZoneData
3. Subsequent recalc (VAP gone): use stored value for subgraph
4. Clear on zone slot recycle
5. Only works going forward — collect during paper trading

## Three VP Features to Investigate (Post-Fix)

1. F20 Distance at seq=1: ray distance from zone edge. All TFs.
2. F19 Consumption at seq=2+: ray consumed = zone weaker. All TFs.
3. Consumed Ray as S/R: consumed ray price becomes support/
   resistance level. Time since consumption matters.

## Files Changed

| File | Change | Status |
|------|--------|--------|
| ZoneBounceSignalsV4_aligned.cpp | Proximity filter | Active |
| ZoneReactionAnalyzer.cpp | Proximity filter | Active |
| ZoneBounceSignalsV4_aligned_v31.cpp | Pre-fix backup | Archived |
| ZoneReactionAnalyzer_v31.cpp | Pre-fix backup | Archived |
| V4 MaxVPProfiles setting | 50 → 0 | Active |
| SupplyDemandZonesV4.cpp | NOT modified | Pending item #11 |

## Impact

- v3.1 pipeline: UNAFFECTED (VP not in scoring model)
- Autotrader: UNAFFECTED (VP not in A-Cal features)
- Paper trading: proximity filters active, any available VP
  data will be clean. V4 persistence fix enables collection.
