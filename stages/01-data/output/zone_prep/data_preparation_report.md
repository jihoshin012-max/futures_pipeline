# Zone Touch Data Preparation Report
Generated: 2026-03-20T13:46:17.999615

## Step 1: File Inventory

| File | Rows | Date Range |
|------|------|------------|
| ZRA_P1 | 4,964 | 2025-09-16 02:26:01 — 2025-12-14 23:51:01 |
| ZB4_P1 | 4,964 | 2025-09-16 02:26:00 — 2025-12-14 23:51:00 |
| Bar_P1 | 138,704 | 2025-09-21 18:00:00 — 2025-12-14 23:58:18.949000 |

| File | Rows | Date Range |
|------|------|------------|
| ZRA_P2 | 4,660 | 2025-12-15 00:06:39 — 2026-03-02 23:58:38 |
| ZB4_P2 | 4,653 | 2025-12-15 07:08:00 — 2026-03-02 23:58:00 |
| Bar_P2 | 131,709 | 2025-12-15 00:06:39.018001 — 2026-03-13 16:59:48.056000 |

## Step 2: VP_RAY Filtering

- P1: 0 VP_RAY touches removed
  Remaining types: {'SUPPLY_EDGE', 'DEMAND_EDGE'} (4,964 rows)
  Trimmed 263 ZRA rows outside P1 bounds (2025-09-21 — 2025-12-14), 4,701 remain
- P2: 0 VP_RAY touches removed
  Remaining types: {'SUPPLY_EDGE', 'DEMAND_EDGE'} (4,660 rows)

## Step 3: ZB4 Trimming

- P1: ZB4 trimmed from 4,964 to 4,701 rows (ZRA range: 2025-09-21 18:00:00 — 2025-12-14 23:51:01)
- P2: ZB4 trimmed from 4,653 to 4,653 rows (ZRA range: 2025-12-15 00:06:39 — 2026-03-02 23:58:38)

## Step 4: Merge Results

  WARNING: 5 ZRA rows share a key with another row (0.1%)
### P1
- Matched: 4,701 / 4,701 (100.0%)
- Unmatched: 0

  WARNING: 5 ZRA rows share a key with another row (0.1%)
### P2
- Matched: 4,653 / 4,660 (99.8%)
- Unmatched: 7
- Unmatched touches:
  - 2025-12-15 00:06:39 | 25513.75 | DEMAND_EDGE | 60m
  - 2025-12-15 00:21:36 | 25529.5 | SUPPLY_EDGE | 15m
  - 2025-12-15 03:02:09 | 25513.5 | SUPPLY_EDGE | 60m
  - 2025-12-15 03:11:32 | 25492.75 | DEMAND_EDGE | 90m
  - 2025-12-15 03:16:17 | 25503.25 | SUPPLY_EDGE | 15m
  - 2025-12-15 03:34:02 | 25529.5 | SUPPLY_EDGE | 15m
  - 2025-12-15 04:21:40 | 25576.25 | SUPPLY_EDGE | 15m

✓ Confirmed: only CascadeState and TFConfluence pulled from ZB4 (no scoring columns)

## Step 5: Derived Columns

- P1: ZoneWidthTicks computed, SBB_Label assigned (1626 SBB touches retained)
- P2: ZoneWidthTicks computed, SBB_Label assigned (1398 SBB touches retained)
✓ Confirmed: SBB touches labeled but NOT removed — all remain in dataset

## Step 6: Bar Data Join

- P1: 4,701/4,701 matched (100.0%), max gap: 40575.5s
  ⚠️ 1024 touches with gap > 60s
- P2: 4,659/4,660 matched (100.0%), max gap: 1081.5s
  ⚠️ 960 touches with gap > 60s

## Step 7: Period Split

### P1 split at 2025-11-05
- P1a: 2,334 touches (2025-09-21 — 2025-11-04)
- P1b: 2,367 touches (2025-11-05 — 2025-12-14)

### P2 split at 2026-01-27
- P2a: 2,304 touches (2025-12-15 — 2026-01-26)
- P2b: 2,356 touches (2026-01-27 — 2026-03-02)

✓ Confirmed: split dates determined from data (median DateTime), not hardcoded

## Step 8: Verification Checks

### P1a (2,334 rows)
- [PASS] No nulls in key columns
- [PASS] Valid TouchType
- [PASS] Valid SourceLabel
- [PASS] Valid CascadeState
- [PASS] Non-negative outcomes
- [PASS] Zone ordering (Top > Bot)
- [PASS] Date range within bounds
- [PASS] Minimum 500 touches

### P1b (2,367 rows)
- [PASS] No nulls in key columns
- [PASS] Valid TouchType
- [PASS] Valid SourceLabel
- [PASS] Valid CascadeState
- [PASS] Non-negative outcomes
- [PASS] Zone ordering (Top > Bot)
- [PASS] Date range within bounds
- [PASS] Minimum 500 touches

### P2a (2,304 rows)
- [PASS] No nulls in key columns
- [PASS] Valid TouchType
- [PASS] Valid SourceLabel
- [PASS] Valid CascadeState
- [PASS] Non-negative outcomes
- [PASS] Zone ordering (Top > Bot)
- [PASS] Date range within bounds
- [PASS] Minimum 500 touches

### P2b (2,356 rows)
- [PASS] No nulls in key columns
- [PASS] Valid TouchType
- [PASS] Valid SourceLabel
- [PASS] Valid CascadeState
- [PASS] Non-negative outcomes
- [PASS] Zone ordering (Top > Bot)
- [PASS] Date range within bounds
- [PASS] Minimum 500 touches

✓ Confirmed: UNKNOWN CascadeState counts: {'P1a': np.int64(0), 'P1b': np.int64(0), 'P2a': np.int64(7), 'P2b': np.int64(0)}

✓ All verification checks passed

## Step 9: Output Files

- Saved: NQ_merged_P1a.csv (2,334 rows)
- Saved: NQ_merged_P1b.csv (2,367 rows)
- Saved: NQ_merged_P2a.csv (2,304 rows)
- Saved: NQ_merged_P2b.csv (2,356 rows)
- Copied: NQ_bardata_P1.csv (138,704 rows)
- Copied: NQ_bardata_P2.csv (131,709 rows)
- Saved: period_config.json

## Distributions by Sub-Period

### P1a (2,334 touches)

**TouchType:**
  - DEMAND_EDGE: 1227 (52.6%)
  - SUPPLY_EDGE: 1107 (47.4%)
**SourceLabel (TF):**
  - 120m: 209 (9.0%)
  - 15m: 667 (28.6%)
  - 240m: 120 (5.1%)
  - 30m: 500 (21.4%)
  - 360m: 109 (4.7%)
  - 480m: 75 (3.2%)
  - 60m: 349 (15.0%)
  - 720m: 69 (3.0%)
  - 90m: 236 (10.1%)
**CascadeState:**
  - PRIOR_BROKE: 2010 (86.1%)
  - PRIOR_HELD: 238 (10.2%)
  - NO_PRIOR: 86 (3.7%)
**SBB Rate by TF:**
  - 120m: 45.5%
  - 15m: 35.5%
  - 240m: 43.3%
  - 30m: 28.0%
  - 360m: 41.3%
  - 480m: 50.7%
  - 60m: 37.5%
  - 720m: 44.9%
  - 90m: 41.1%
**ZoneWidthTicks:** min=9, max=1142, mean=200.6, median=127
**TouchSequence:**
  - 1: 868 (37.2%)
  - 2: 441 (18.9%)
  - 3: 300 (12.9%)
  - 4: 212 (9.1%)
  - 5+: 513 (22.0%)
**HasVPRay rate:** 100.0%

### P1b (2,367 touches)

**TouchType:**
  - DEMAND_EDGE: 1310 (55.3%)
  - SUPPLY_EDGE: 1057 (44.7%)
**SourceLabel (TF):**
  - 120m: 252 (10.6%)
  - 15m: 673 (28.4%)
  - 240m: 139 (5.9%)
  - 30m: 472 (19.9%)
  - 360m: 113 (4.8%)
  - 480m: 111 (4.7%)
  - 60m: 257 (10.9%)
  - 720m: 95 (4.0%)
  - 90m: 255 (10.8%)
**CascadeState:**
  - PRIOR_BROKE: 1985 (83.9%)
  - PRIOR_HELD: 300 (12.7%)
  - NO_PRIOR: 82 (3.5%)
**SBB Rate by TF:**
  - 120m: 33.3%
  - 15m: 30.5%
  - 240m: 25.2%
  - 30m: 32.0%
  - 360m: 29.2%
  - 480m: 25.2%
  - 60m: 36.2%
  - 720m: 46.3%
  - 90m: 34.1%
**ZoneWidthTicks:** min=11, max=1605, mean=306.4, median=224
**TouchSequence:**
  - 1: 771 (32.6%)
  - 2: 426 (18.0%)
  - 3: 295 (12.5%)
  - 4: 212 (9.0%)
  - 5+: 663 (28.0%)
**HasVPRay rate:** 100.0%

### P2a (2,304 touches)

**TouchType:**
  - DEMAND_EDGE: 1153 (50.0%)
  - SUPPLY_EDGE: 1151 (50.0%)
**SourceLabel (TF):**
  - 120m: 205 (8.9%)
  - 15m: 583 (25.3%)
  - 240m: 157 (6.8%)
  - 30m: 421 (18.3%)
  - 360m: 142 (6.2%)
  - 480m: 176 (7.6%)
  - 60m: 264 (11.5%)
  - 720m: 135 (5.9%)
  - 90m: 221 (9.6%)
**CascadeState:**
  - PRIOR_BROKE: 1807 (78.4%)
  - PRIOR_HELD: 411 (17.8%)
  - NO_PRIOR: 79 (3.4%)
  - UNKNOWN: 7 (0.3%)
**SBB Rate by TF:**
  - 120m: 33.2%
  - 15m: 29.2%
  - 240m: 36.9%
  - 30m: 20.7%
  - 360m: 26.8%
  - 480m: 36.9%
  - 60m: 37.1%
  - 720m: 27.4%
  - 90m: 28.5%
**ZoneWidthTicks:** min=6, max=1350, mean=283.0, median=180
**TouchSequence:**
  - 1: 740 (32.1%)
  - 2: 391 (17.0%)
  - 3: 242 (10.5%)
  - 4: 168 (7.3%)
  - 5+: 763 (33.1%)
**HasVPRay rate:** 100.0%

### P2b (2,356 touches)

**TouchType:**
  - DEMAND_EDGE: 1293 (54.9%)
  - SUPPLY_EDGE: 1063 (45.1%)
**SourceLabel (TF):**
  - 120m: 209 (8.9%)
  - 15m: 681 (28.9%)
  - 240m: 155 (6.6%)
  - 30m: 394 (16.7%)
  - 360m: 101 (4.3%)
  - 480m: 121 (5.1%)
  - 60m: 377 (16.0%)
  - 720m: 89 (3.8%)
  - 90m: 229 (9.7%)
**CascadeState:**
  - PRIOR_BROKE: 1935 (82.1%)
  - PRIOR_HELD: 350 (14.9%)
  - NO_PRIOR: 71 (3.0%)
**SBB Rate by TF:**
  - 120m: 37.3%
  - 15m: 26.4%
  - 240m: 43.9%
  - 30m: 27.2%
  - 360m: 35.6%
  - 480m: 38.8%
  - 60m: 26.0%
  - 720m: 36.0%
  - 90m: 29.7%
**ZoneWidthTicks:** min=10, max=1461, mean=343.9, median=280
**TouchSequence:**
  - 1: 718 (30.5%)
  - 2: 407 (17.3%)
  - 3: 281 (11.9%)
  - 4: 208 (8.8%)
  - 5+: 742 (31.5%)
**HasVPRay rate:** 100.0%
