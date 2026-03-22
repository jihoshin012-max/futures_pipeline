# Pipeline Audit Report

**Date:** 2026-03-22
**Scope:** Full structural audit of `C:\Projects\pipeline\`

---

## 1. Directory Tree (3 levels, with sizes)

```
pipeline/                          (32+ GB total, ~1500 files)
├── _config/                       (40K, 8 files)
│   ├── context_review_protocol.md
│   ├── data_registry.md
│   ├── instruments.md
│   ├── period_config.md
│   ├── pipeline_rules.md
│   ├── regime_definitions.md
│   └── statistical_gates.md
├── archive/                       (0K, 1 file — .gitkeep only)
├── audit/                         (40K, 3 files)
│   ├── audit_entry.sh
│   └── audit_log.md
├── dashboard/                     (6K, 3 files)
│   ├── index.html
│   └── results_master.tsv
├── shared/                        (20M, 299 files)
│   ├── archetypes/
│   │   ├── rotational/            (19M, 240 files)
│   │   └── zone_touch/            (752K, 40 files)
│   ├── onboarding/                (140K, 6 files)
│   ├── scoring_models/            (50K, 8 files)
│   ├── data_loader.py
│   └── feature_definitions.md
├── stages/                        (32G, 1147 files)
│   ├── 01-data/                   (32G, 143 files)
│   │   ├── analysis/              (78M, 92 files)
│   │   ├── data/                  (31G, 28 files)
│   │   ├── output/                (59M, 12 files)
│   │   └── references/            (32K, 6 files)
│   ├── 02-features/               (90K, 18 files)
│   │   ├── autoresearch/          (61K, 10 files)
│   │   ├── output/                (1K, 2 files)
│   │   └── references/            (12K, 3 files)
│   ├── 03-hypothesis/             (128K, 20 files)
│   │   ├── autoresearch/          (110K, 12 files)
│   │   ├── output/                (0K, 2 files)
│   │   └── references/            (10K, 4 files)
│   ├── 04-backtest/               (433M, 934 files)
│   │   ├── autoresearch/          (113K, 11 files)
│   │   ├── output/                (1K, 2 files)
│   │   ├── p2_holdout/            (0K, 1 file)
│   │   ├── references/            (20K, 4 files)
│   │   ├── rotational/            (422M, 864 files)
│   │   └── zone_touch/            (11M, 50 files)
│   ├── 05-assessment/             (701K, 19 files)
│   │   ├── output/                (4K, 2 files)
│   │   ├── references/            (12K, 3 files)
│   │   └── rotational/            (653K, 10 files)
│   ├── 06-deployment/             (16K, 6 files)
│   │   ├── output/                (0K, 1 file)
│   │   └── references/            (4K, 2 files)
│   └── 07-live/                   (12K, 6 files)
│       ├── data/                  (0K, 1 file)
│       ├── output/                (0K, 1 file)
│       └── triggers/              (4K, 2 files)
├── tests/                         (772K, 30 files)
├── xtra/                          (592K, 17 files)
│   ├── prompts/                   (2 files)
│   └── (15 misc docs + data files)
├── .benchmarks/
├── .claude/
├── .planning/
├── CLAUDE.md
├── CONTEXT.md
├── autocommit.sh
└── requirements.txt
```

---

## 2. Structural Issues

### A) MISPLACED FILES

| File/Pattern | Location | Issue | Recommendation |
|---|---|---|---|
| `NQ_ZB4_signals_P1_v31.csv`, `NQ_ZB4_signals_P2_v31.csv`, `NQ_ZRA_Hist_P1_v31.csv`, `NQ_ZRA_Hist_P2_v31.csv` | `stages/01-data/data/touches/` | Superseded v31 backup files sitting alongside active files | Move to `archive/data_snapshots/v31/` or delete if git-tracked |
| `NQ_calibration_V1_1_20260320_calibration.csv` (130M) | `stages/01-data/data/bar_data/tick/` | One-off calibration export mixed with production bar data | Move to `stages/01-data/analysis/calibration_v1_1/` |
| `NQ_BarData_250vol_P1.txt`, `NQ_BarData_250vol_P2.txt` | `stages/01-data/data/bar_data/volume/` | Legacy `.txt` format alongside newer `.csv` format of same data | Archive or delete if `.csv` versions are canonical |
| `ZoneBounceSignalsV4_aligned_v31.cpp`, `ZoneReactionAnalyzer_v31.cpp` | `shared/archetypes/zone_touch/acsil/` | Superseded v31 backup copies alongside active versions | Move to `archive/acsil_snapshots/v31/` or delete |
| `zone_bounce_config.h` | `shared/archetypes/zone_touch/acsil/` | Header file violates SC remote build constraint (no custom .h files, single .cpp only per feedback_acsil_build memory) | Should be inlined or documented as local-build-only |
| `run_zone_prep.py` | `stages/01-data/output/zone_prep/` | Script mixed with its own output directory | **MOVED** to `stages/01-data/scripts/` (Phase 3) |
| `hmm_regime_fitter.py` | `stages/01-data/` (root) | Loose script at stage root, not in analysis/ or scripts/ | **MOVED** to `stages/01-data/scripts/` (Phase 3) |
| `zigzag_results.pkl` (74M) | `stages/01-data/analysis/fractal_discovery/` | Large binary intermediate file in analysis folder | Should be gitignored (already covered by `*.pkl` in .gitignore) |
| `.pytest_cache/` directories | `stages/04-backtest/rotational/`, `shared/archetypes/rotational/` | Test cache artifacts committed/present | Should be in .gitignore |
| `ATEAM_ROTATION_V1_OG_V2803.cpp`, `ATEAM_ROTATION_V1_OG_analysis.md` | `xtra/` | Original rotation code mixed with design docs, prompts, and specs | Separate: code to archive, specs stay |
| `ATEAM_ROTATION_V1_1_log_live.csv` | `xtra/` | Live log data in a docs/reference folder | Move to `stages/07-live/data/` or `archive/` |
| `ATEAM_ROTATION_V1_1_log_live.csv` (duplicate) | `shared/archetypes/rotational/references/` | Same file appears in both xtra/ and shared/ | Keep one canonical copy |
| Sweep cycle_logs (422M total) | `stages/04-backtest/rotational/frozen_anchor_sweep/`, `sweep_results/` | Massive CSV outputs from completed sweeps, 800+ files | Archive completed sweeps; only keep summary CSVs active |

### B) NAMING INCONSISTENCIES

| Pattern | Examples | Issue |
|---|---|---|
| Mixed case in filenames | `ATEAM_ZONE_BOUNCE_V1.cpp` vs `zone_bounce_config.h` vs `SupplyDemandZonesV4.cpp` | ACSIL files use PascalCase (SC convention); config uses snake_case; autotrader uses SCREAMING_SNAKE. Three conventions in one dir |
| `NQ_BarData_*` vs `NQ_ZB4_signals_*` vs `NQ_ZRA_Hist_*` | Data files in `stages/01-data/data/` | No consistent naming scheme for data exports. Mix of CamelCase and abbreviations |
| `run_*.py` proliferation | 30+ files like `run_phase1_sweep.py`, `run_p2a_validation.py`, `run_fa_sweep.py` | No way to tell which are current vs historical sweeps. No date/version prefix |
| Prompt files naming | `prompt0_baseline.py`, `prompt1a_screening.py` (zone_touch) vs `run_phase1_base.py`, `run_phase2_features.py` (rotational) | Two different naming conventions for equivalent pipeline steps across archetypes |
| `autoresearch/` vs archetype-specific dirs | `stages/04-backtest/autoresearch/` AND `stages/04-backtest/zone_touch/` AND `stages/04-backtest/rotational/` | Generic autoresearch dir coexists with archetype-specific dirs. Unclear which is canonical |
| `output/` ambiguity | Every stage has `output/`, plus archetypes have their own outputs inline | No clear ownership — `stages/04-backtest/output/result.json` vs `stages/04-backtest/zone_touch/output/` |
| Phase naming (`p1a`, `p1b`, `P1`, `P1a`) | Throughout | Inconsistent capitalization of period identifiers |

### C) MISSING STRUCTURE

| Gap | Impact |
|---|---|
| No `scripts/` directory in any stage | Scripts are scattered at stage root, in `output/`, or in `autoresearch/`. No clear separation of code vs data vs config |
| No top-level `Makefile` or `justfile` | Every step is manual or ad-hoc script invocation. No reproducible pipeline runner |
| `archive/` is empty | 4 _v31 backup files, sweep results, and historical experiments have no archive destination |
| No `stages/01-data/data/README.md` | 31GB of data files with no manifest or provenance doc inside the data directory itself |
| `dashboard/results_master.tsv` empty/minimal | Dashboard exists but is disconnected from actual experiment results |
| `stages/07-live/` is skeletal | Only .gitkeeps and a triggers readme. No scripts, no data flow defined |
| No separation of `rotational` vs `zone_touch` at pipeline level | Both archetypes are jammed into the same stage directories. Each stage must handle both, but there's no routing or namespacing at the top level |
| Missing `.gitignore` entries | `.pytest_cache/` directories not ignored. Some large CSVs in backtest/ may not be caught |
| `CONTEXT.md` stage status table is stale | Shows stages 02-04 as "Not started" but all three have significant content |

---

## 3. Size Hotspots

| Path | Size | Note |
|---|---|---|
| `stages/01-data/data/bar_data/tick/` | ~31G | 1-tick CSVs (ES 16G, NQ 8.3G + 6.9G). Gitignored correctly |
| `stages/04-backtest/rotational/frozen_anchor_sweep/` | 379M | 423 files — completed sweep, archivable |
| `stages/04-backtest/rotational/sweep_results/` | 30M | 367 files — completed sweep, archivable |
| `stages/01-data/analysis/fractal_discovery/` | ~78M | Includes 74M zigzag_results.pkl |
| `stages/01-data/output/zone_prep/` | ~59M | Two 29M bardata CSVs (gitignored) |
| `shared/archetypes/rotational/` | 19M | Parquet files, PNG charts, speedread results |

---

## 4. Automation Hooks

| Manual Step | Current Process | Automation Opportunity | Type |
|---|---|---|---|
| Data export from SC | Manual SC chart export | SC study `WriteBarDataToFile()` on recalc auto-export | Must stay manual (SC GUI) |
| Zone prep | Run `run_zone_prep.py` manually | `make zone-prep` target with input validation + period_config.json | Makefile target |
| Period splitting | Hardcoded in zone_prep | Read from `_config/period_config.md` or `period_config.json` | Already partially done |
| Feature evaluation | `python evaluate_features.py --archetype zone_touch` | `make features ARCH=zone_touch` | Makefile target |
| Feature freeze | `python freeze_features.py` | `make freeze-features` (validates features exist first) | Makefile target |
| Hypothesis screening | Run driver.py in 03-hypothesis | `make hypothesis ARCH=zone_touch` | Makefile target |
| Backtest sweep | Run `run_sweep.py` or `prompt*.py` manually | `make backtest ARCH=zone_touch PHASE=p1a` | Makefile target |
| Replication gate | Manual comparison (79/79 matched check) | `make replication-gate ARCH=zone_touch` — automated test suite | Makefile + pytest |
| P2 holdout check | Manually check `holdout_locked_P2.flag` | Pre-backtest hook checks flag + warns | Makefile guard |
| Data manifest update | Manual JSON editing | `make manifest` — regenerate from data/ scan | Makefile target |
| Validation | `python validate.py` | `make validate` | Makefile target |
| Version tracking | Manual CHANGELOG.md | `git log --oneline` formatted into CHANGELOG on release | Git hook or Makefile |
| CONTEXT.md stage status | Manual editing | Script scans `stages/*/output/` for artifacts, updates table | Utility script |
| Sweep archive | Never done (422M sitting in backtest) | `make archive-sweep NAME=frozen_anchor_sweep` — moves to `archive/` with summary | Makefile target |
| Dashboard update | Manual | `make dashboard` — aggregate results.tsv files into master | Makefile target |
| Lint / pre-commit | None | Pre-commit hook: check no P2 data access if flag exists, validate JSON schemas | Git pre-commit |
| ACSIL build | Manual copy to SC Data folder, remote build | `make build-acsil STUDY=ZoneBounceSignalsV4` — copies + triggers | Makefile + SC path |

### Priority Automation

1. **Makefile (HIGH):** Core pipeline targets — `validate`, `zone-prep`, `features`, `backtest`, `replication-gate`
2. **Git pre-commit (HIGH):** P2 holdout guard, instrument constant hardcode check
3. **Utility scripts (MEDIUM):** `archive_sweep.py`, `update_dashboard.py`, `update_context_status.py`
4. **Must stay manual:** SC GUI data export, SC chart configuration, parameter review checkpoints

---

## 5. Cross-Reference Dependency Map

### Critical paths referenced by scripts (DO NOT BREAK)

```
stages/01-data/data/bar_data/tick/NQ_BarData_250tick_rot_P1.csv   — 15+ scripts
stages/01-data/data/bar_data/tick/NQ_BarData_250tick_rot_P2.csv   — 5+ scripts
stages/01-data/data/bar_data/tick/NQ_BarData_1tick_rot_P1.csv     — 8+ scripts
stages/01-data/data/bar_data/tick/NQ_BarData_1tick_rot_P2.csv     — 5+ scripts
stages/01-data/data/bar_data/volume/NQ_BarData_250vol_rot_P1.csv  — 4+ scripts
stages/01-data/data/bar_data/volume/NQ_BarData_250vol_rot_P2.csv  — 2+ scripts
stages/01-data/data/bar_data/time/NQ_BarData_10sec_rot_P1.csv     — 2+ scripts
stages/01-data/data/bar_data/time/NQ_BarData_10sec_rot_P2.csv     — 2+ scripts
stages/01-data/data/touches/NQ_ZRA_Hist_P1.csv                    — 2+ scripts
stages/01-data/data/bar_data/volume/NQ_BarData_250vol_P1.txt      — 1 script (zone_touch feature_evaluator)
stages/01-data/output/data_manifest.json                           — 2+ scripts
stages/04-backtest/p2_holdout/holdout_locked_P2.flag               — rotational_engine.py
shared/archetypes/zone_touch/feature_engine.py                     — stage 02 driver
shared/archetypes/zone_touch/simulation_rules.md                   — test_backtest_engine
shared/scoring_models/zone_touch_v1.json                           — 4+ test files
shared/scoring_models/hmm_regime_v1.pkl                            — hmm_regime_fitter.py
shared/feature_definitions.md                                      — assemble_context.sh
shared/data_loader.py                                              — many scripts via import
stages/03-hypothesis/references/strategy_archetypes.md             — scaffold_adapter.py
shared/archetypes/rotational/rotational_params.json                — central path registry
```
