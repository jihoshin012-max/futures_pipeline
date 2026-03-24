# Zone Touch Data Preparation Report
Generated: 2026-03-24T01:37:37.851550

## Step 1: File Inventory

**Mode: ZTE (consolidated)** — reading per-period NQ_ZTE_raw_*.csv from pipeline data folder

| File | Rows | Date Range |
|------|------|------------|
| ZTE_P1 | 3,278 | 2025-09-21 20:46:28 — 2025-12-14 23:51:01 |
| Bar_P1 | 138,704 | 2025-09-21 18:00:00 — 2025-12-14 23:58:18.949000 |

| File | Rows | Date Range |
|------|------|------------|
| ZTE_P2 | 3,537 | 2025-12-15 00:06:39 — 2026-03-02 23:58:38 |
| Bar_P2 | 131,709 | 2025-12-15 00:06:39.018001 — 2026-03-13 16:59:48.056000 |

## Step 2: VP_RAY Filtering

- P1: 0 VP_RAY touches removed
  Remaining types: {'SUPPLY_EDGE', 'DEMAND_EDGE'} (3,278 rows)
- P2: 0 VP_RAY touches removed
  Remaining types: {'SUPPLY_EDGE', 'DEMAND_EDGE'} (3,537 rows)

## Step 3: ZB4 Trimming

- SKIPPED (ZTE mode — CascadeState and TFConfluence already in unified CSV)

## Step 4: Merge Results

### P1
- ZTE mode: 3,278 rows — CascadeState and TFConfluence from unified CSV (no ZB4 merge)

### P2
- ZTE mode: 3,537 rows — CascadeState and TFConfluence from unified CSV (no ZB4 merge)

✓ Confirmed: only CascadeState and TFConfluence present (no scoring columns)

## Step 5: Derived Columns

- P1: ZoneWidthTicks from ZTE (not recomputed)
- P1: SBB_Label assigned (240 SBB touches retained)
- P2: ZoneWidthTicks from ZTE (not recomputed)
- P2: SBB_Label assigned (304 SBB touches retained)
✓ Confirmed: SBB touches labeled but NOT removed — all remain in dataset

## Step 6: Bar Data Join

- P1: 3,278/3,278 matched (100.0%), max gap: 40575.5s
  ⚠️ 792 touches with gap > 60s
- P2: 3,536/3,537 matched (100.0%), max gap: 1081.5s
  ⚠️ 779 touches with gap > 60s

## Step 7: Period Split

### P1 split at 2025-11-06
- P1a: 1,606 touches (2025-09-21 — 2025-11-05)
- P1b: 1,672 touches (2025-11-06 — 2025-12-14)

### P2 split at 2026-01-27
- P2a: 1,767 touches (2025-12-15 — 2026-01-26)
- P2b: 1,770 touches (2026-01-27 — 2026-03-02)

✓ Confirmed: split dates determined from data (median DateTime), not hardcoded

## Step 8: Verification Checks

### P1a (1,606 rows)
- [PASS] No nulls in key columns
- [PASS] Valid TouchType
- [PASS] Valid SourceLabel
- [PASS] Valid CascadeState
- [PASS] Non-negative outcomes
- [PASS] Zone ordering (Top > Bot)
- [PASS] Date range within bounds
- [PASS] Minimum 500 touches

### P1b (1,672 rows)
- [PASS] No nulls in key columns
- [PASS] Valid TouchType
- [PASS] Valid SourceLabel
- [PASS] Valid CascadeState
- [PASS] Non-negative outcomes
- [PASS] Zone ordering (Top > Bot)
- [PASS] Date range within bounds
- [PASS] Minimum 500 touches

### P2a (1,767 rows)
- [PASS] No nulls in key columns
- [PASS] Valid TouchType
- [PASS] Valid SourceLabel
- [PASS] Valid CascadeState
- [PASS] Non-negative outcomes
- [PASS] Zone ordering (Top > Bot)
- [PASS] Date range within bounds
- [PASS] Minimum 500 touches

### P2b (1,770 rows)
- [PASS] No nulls in key columns
- [PASS] Valid TouchType
- [PASS] Valid SourceLabel
- [PASS] Valid CascadeState
- [PASS] Non-negative outcomes
- [PASS] Zone ordering (Top > Bot)
- [PASS] Date range within bounds
- [PASS] Minimum 500 touches

✓ Confirmed: UNKNOWN CascadeState counts: {'P1a': np.int64(0), 'P1b': np.int64(0), 'P2a': np.int64(0), 'P2b': np.int64(0)}

✓ All verification checks passed

## Step 9: Output Files

- Saved: NQ_merged_P1a.csv (1,606 rows)
- Saved: NQ_merged_P1b.csv (1,672 rows)
- Saved: NQ_merged_P2a.csv (1,767 rows)
- Saved: NQ_merged_P2b.csv (1,770 rows)
- Copied: NQ_bardata_P1.csv (138,704 rows)
- Copied: NQ_bardata_P2.csv (131,709 rows)
- Saved: period_config.json

## Distributions by Sub-Period

### P1a (1,606 touches)

**TouchType:**
  - DEMAND_EDGE: 810 (50.4%)
  - SUPPLY_EDGE: 796 (49.6%)
**SourceLabel (TF):**
  - 120m: 131 (8.2%)
  - 15m: 488 (30.4%)
  - 240m: 72 (4.5%)
  - 30m: 376 (23.4%)
  - 360m: 69 (4.3%)
  - 480m: 46 (2.9%)
  - 60m: 235 (14.6%)
  - 720m: 38 (2.4%)
  - 90m: 151 (9.4%)
**CascadeState:**
  - PRIOR_BROKE: 1261 (78.5%)
  - PRIOR_HELD: 255 (15.9%)
  - NO_PRIOR: 90 (5.6%)
**SBB Rate by TF:**
  - 120m: 5.3%
  - 15m: 10.5%
  - 240m: 5.6%
  - 30m: 6.1%
  - 360m: 7.2%
  - 480m: 10.9%
  - 60m: 8.1%
  - 720m: 0.0%
  - 90m: 5.3%
**ZoneWidthTicks:** min=9, max=1142, mean=225.1, median=139
**TouchSequence:**
  - 1: 622 (38.7%)
  - 2: 306 (19.1%)
  - 3: 189 (11.8%)
  - 4: 131 (8.2%)
  - 5+: 358 (22.3%)
**HasVPRay rate:** 0.0%

### P1b (1,672 touches)

**TouchType:**
  - DEMAND_EDGE: 916 (54.8%)
  - SUPPLY_EDGE: 756 (45.2%)
**SourceLabel (TF):**
  - 120m: 167 (10.0%)
  - 15m: 484 (28.9%)
  - 240m: 109 (6.5%)
  - 30m: 350 (20.9%)
  - 360m: 81 (4.8%)
  - 480m: 79 (4.7%)
  - 60m: 171 (10.2%)
  - 720m: 51 (3.1%)
  - 90m: 180 (10.8%)
**CascadeState:**
  - PRIOR_BROKE: 1311 (78.4%)
  - PRIOR_HELD: 285 (17.0%)
  - NO_PRIOR: 76 (4.5%)
**SBB Rate by TF:**
  - 120m: 5.4%
  - 15m: 9.1%
  - 240m: 4.6%
  - 30m: 9.4%
  - 360m: 1.2%
  - 480m: 0.0%
  - 60m: 4.1%
  - 720m: 0.0%
  - 90m: 10.6%
**ZoneWidthTicks:** min=17, max=1605, mean=342.8, median=260
**TouchSequence:**
  - 1: 542 (32.4%)
  - 2: 294 (17.6%)
  - 3: 198 (11.8%)
  - 4: 131 (7.8%)
  - 5+: 507 (30.3%)
**HasVPRay rate:** 0.0%

### P2a (1,767 touches)

**TouchType:**
  - SUPPLY_EDGE: 912 (51.6%)
  - DEMAND_EDGE: 855 (48.4%)
**SourceLabel (TF):**
  - 120m: 151 (8.5%)
  - 15m: 443 (25.1%)
  - 240m: 110 (6.2%)
  - 30m: 348 (19.7%)
  - 360m: 109 (6.2%)
  - 480m: 143 (8.1%)
  - 60m: 186 (10.5%)
  - 720m: 107 (6.1%)
  - 90m: 170 (9.6%)
**CascadeState:**
  - PRIOR_BROKE: 1277 (72.3%)
  - PRIOR_HELD: 411 (23.3%)
  - NO_PRIOR: 79 (4.5%)
**SBB Rate by TF:**
  - 120m: 11.3%
  - 15m: 8.1%
  - 240m: 10.0%
  - 30m: 4.6%
  - 360m: 4.6%
  - 480m: 22.4%
  - 60m: 10.8%
  - 720m: 8.4%
  - 90m: 7.1%
**ZoneWidthTicks:** min=6, max=1350, mean=332.6, median=211
**TouchSequence:**
  - 1: 525 (29.7%)
  - 2: 277 (15.7%)
  - 3: 169 (9.6%)
  - 4: 115 (6.5%)
  - 5+: 681 (38.5%)
**HasVPRay rate:** 3.7%

### P2b (1,770 touches)

**TouchType:**
  - DEMAND_EDGE: 1038 (58.6%)
  - SUPPLY_EDGE: 732 (41.4%)
**SourceLabel (TF):**
  - 120m: 144 (8.1%)
  - 15m: 540 (30.5%)
  - 240m: 98 (5.5%)
  - 30m: 298 (16.8%)
  - 360m: 77 (4.4%)
  - 480m: 78 (4.4%)
  - 60m: 295 (16.7%)
  - 720m: 60 (3.4%)
  - 90m: 180 (10.2%)
**CascadeState:**
  - PRIOR_BROKE: 1349 (76.2%)
  - PRIOR_HELD: 350 (19.8%)
  - NO_PRIOR: 71 (4.0%)
**SBB Rate by TF:**
  - 120m: 9.0%
  - 15m: 9.3%
  - 240m: 11.2%
  - 30m: 6.0%
  - 360m: 15.6%
  - 480m: 5.1%
  - 60m: 5.4%
  - 720m: 5.0%
  - 90m: 10.6%
**ZoneWidthTicks:** min=19, max=1461, mean=370.1, median=310
**TouchSequence:**
  - 1: 540 (30.5%)
  - 2: 300 (16.9%)
  - 3: 219 (12.4%)
  - 4: 152 (8.6%)
  - 5+: 559 (31.6%)
**HasVPRay rate:** 2.4%
