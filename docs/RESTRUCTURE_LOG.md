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

**Phase 2: Archive completed sweeps** — 2026-03-22

| # | Action | Source | Destination | Reason |
|---|--------|--------|-------------|--------|
| 2.1 | MOVE | `stages/04-backtest/rotational/frozen_anchor_sweep/` (379M, 423 files) | `archive/sweeps/frozen_anchor_sweep/` | Completed sweep — all results final |
| 2.2 | MOVE | `stages/04-backtest/rotational/sweep_results/` (30M, 367 files) | `archive/sweeps/sweep_results/` | Completed sweep — all results final |
| 2.3 | MOVE | `stages/04-backtest/rotational/decoupled_seed_test/` (6.4M, 22 files) | `archive/sweeps/decoupled_seed_test/` | Completed sweep — all results final |
| 2.4 | MOVE | `stages/04-backtest/rotational/pullback_test/` (6.1M, 28 files) | `archive/sweeps/pullback_test/` | Completed sweep — all results final |
| 2.5a | COPY | `archive/sweeps/frozen_anchor_sweep/config_summary.csv` | `stages/04-backtest/references/sweep_summaries/` | Preserve summary in active tree |
| 2.5b | COPY | `archive/sweeps/frozen_anchor_sweep/smoke_test_report.md` | `stages/04-backtest/references/sweep_summaries/` | Preserve summary in active tree |
| 2.5c | COPY | `archive/sweeps/sweep_results/config_summary.csv` | `stages/04-backtest/references/sweep_summaries/` | Preserve summary in active tree |
| 2.5d | COPY | `archive/sweeps/sweep_results/smoke_test_report.md` | `stages/04-backtest/references/sweep_summaries/` | Preserve summary in active tree |
| 2.5e | COPY | `archive/sweeps/decoupled_seed_test/{config_summary.csv,decoupled_seed_analysis.md}` | `stages/04-backtest/references/sweep_summaries/` | Preserve summary in active tree |
| 2.5f | COPY | `archive/sweeps/pullback_test/{config_summary.csv,pullback_analysis.md}` | `stages/04-backtest/references/sweep_summaries/` | Preserve summary in active tree |
| 2.7 | EDIT | `docs/PIPELINE_RESTRUCTURE_PLAN.md` | — | Mark Phase 2 as executed |

**Space freed:** 421M moved from `stages/04-backtest/rotational/` (was 422M, now 548K). 840 files archived.

**Script reference check:** 4 runner scripts in `stages/04-backtest/rotational/` reference these dirs as OUTPUT_DIR. Re-running those scripts recreates fresh output dirs. No read-only consumers outside the runners.
