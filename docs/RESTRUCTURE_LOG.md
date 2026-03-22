# Restructure Log

**Phase 1: Safe cleanup** — 2026-03-22

| # | Action | Source | Destination | Reason |
|---|--------|--------|-------------|--------|
| 1.1a | CREATE | — | `archive/data_snapshots/v31/` | Archive directory for superseded data backups |
| 1.1b | CREATE | — | `archive/sweeps/` | Archive directory for completed sweep results (Phase 2) |
| 1.1c | CREATE | — | `archive/xtra/` | Archive directory for historical docs/code (future) |
| 1.2a | MOVE | `stages/01-data/data/touches/NQ_ZB4_signals_P1_v31.csv` | `archive/data_snapshots/v31/` | Superseded v31 backup; not referenced by any script |
| 1.2b | MOVE | `stages/01-data/data/touches/NQ_ZB4_signals_P2_v31.csv` | `archive/data_snapshots/v31/` | Superseded v31 backup; not referenced by any script |
| 1.2c | MOVE | `stages/01-data/data/touches/NQ_ZRA_Hist_P1_v31.csv` | `archive/data_snapshots/v31/` | Superseded v31 backup; not referenced by any script |
| 1.2d | MOVE | `stages/01-data/data/touches/NQ_ZRA_Hist_P2_v31.csv` | `archive/data_snapshots/v31/` | Superseded v31 backup; not referenced by any script |
| 1.3 | SKIP | `stages/01-data/data/touches/test_vp/` | — | Directory does not exist; no action needed |
| 1.4 | MOVE | `stages/01-data/data/bar_data/tick/NQ_calibration_V1_1_20260320_calibration.csv` | `stages/01-data/analysis/calibration_v1_1/` | One-off calibration export; does not belong with production bar data |
| 1.5a | EDIT | `.gitignore` | — | Added `.pytest_cache/` (deduplicated existing `__pycache__/` entry) |
| 1.5b | EDIT | `.gitignore` | — | Added gitignore for 130M calibration CSV at new analysis location |
| 1.5c | EDIT | `.gitignore` | — | Added gitignore for archived data snapshots |
| 1.6 | EDIT | `CONTEXT.md` | — | Updated stage status table to reflect actual state (02-05 have content) |
| 1.7 | CREATE | — | `stages/01-data/data/README.md` | Data directory provenance and inventory |
| 1.8 | EDIT | `docs/PIPELINE_RESTRUCTURE_PLAN.md` | — | Removed acsil_snapshots from plan; v31 .cpp kept co-located per user decision |
