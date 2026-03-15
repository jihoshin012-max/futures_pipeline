# Stage 01 Validation Report
Generated: 2026-03-15 03:38:04

## Status: PASS

## Per-Archetype Period Boundaries

### zone_touch
- P1 (IS): 2025-09-16 to 2025-12-14
- P1a: 2025-09-16 to 2025-10-31
- P1b: 2025-11-01 to 2025-12-14
- P2 (OOS): 2025-12-15 to 2026-03-02
  Sources:
  - zone_touch_v2 (touches): MISSING (0 rows, ? to ?)
  - volume_bar (bar data): MISSING (0 rows, ? to ?)

### rotational
- P1 (IS): 2025-09-21 to 2025-12-14
- P1a: 2025-09-21 to 2025-11-02
- P1b: 2025-11-03 to 2025-12-14
- P2 (OOS): 2025-12-15 to 2026-03-13
  Sources:
  - bar_data_250vol_rot: FOUND (270413 rows, 2025-09-21 to 2026-03-13)
  - bar_data_250tick_rot: FOUND (249162 rows, 2025-09-21 to 2026-03-13)
  - bar_data_10sec_rot: FOUND (976982 rows, 2025-09-21 to 2026-03-13)

## Backwards-Compatible Flat Periods
(zone_touch dates — for downstream consumers not yet updated)

- P1: 2025-09-16 to 2025-12-14
- P2: 2025-12-15 to 2026-03-02

## Data Sources Found

- stages/01-data/data/labels/regime_labels.csv (144 rows)
- stages/01-data/data/touches/ZRA_Hist_P1.csv (6232 rows)
- stages/01-data/data/touches/ZRA_Hist_P2.csv (5891 rows)
- stages/01-data/data/bar_data/tick/NQ_BarData_250tick_rot_P1.csv (127567 rows)
- stages/01-data/data/bar_data/tick/NQ_BarData_250tick_rot_P2.csv (121595 rows)
- stages/01-data/data/bar_data/time/NQ_BarData_10sec_rot_P1.csv (477810 rows)
- stages/01-data/data/bar_data/time/NQ_BarData_10sec_rot_P2.csv (499172 rows)
- stages/01-data/data/bar_data/volume/NQ_BarData_250vol_rot_P1.csv (138704 rows)
- stages/01-data/data/bar_data/volume/NQ_BarData_250vol_rot_P2.csv (131709 rows)
- stages/01-data/data/bar_data/volume/NQ_BarData_250vol_P1.txt (146166 rows)
- stages/01-data/data/bar_data/volume/NQ_BarData_250vol_P2.txt (110156 rows)
