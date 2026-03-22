# Pipeline Restructure Plan

**Date:** 2026-03-22
**Status:** Phases 1-2 EXECUTED 2026-03-22 — Phase 3+ pending

---

## 1. Proposed Clean Structure

The key insight: the current structure is not bad — `stages/01-07` with `shared/archetypes/` is sound. The issues are:
- No `scripts/` separation within stages
- No archetype namespacing at the data level
- Backup/historical files mixed with active
- No Makefile or automation layer
- 422M+ of archivable sweep results

### Target Structure (changes only — existing good structure preserved)

```
pipeline/
├── _config/                       ← KEEP AS-IS (protected, never auto-modify)
├── archive/                       ← ACTIVATE (currently empty)
│   ├── data_snapshots/
│   │   └── v31/                   ← v31 touch/signal backups
│   ├── sweeps/
│   │   ├── frozen_anchor_sweep/   ← 379M from 04-backtest/rotational/
│   │   ├── sweep_results/         ← 30M from 04-backtest/rotational/
│   │   ├── decoupled_seed_test/   ← 6.4M from 04-backtest/rotational/
│   │   └── pullback_test/         ← 6.1M from 04-backtest/rotational/
│   └── xtra/                      ← historical docs/code from xtra/
├── audit/                         ← KEEP AS-IS
├── dashboard/                     ← KEEP AS-IS (enhance later)
├── docs/                          ← NEW (this file lives here)
├── shared/                        ← KEEP STRUCTURE
│   ├── archetypes/
│   │   ├── rotational/            ← KEEP (but archive completed sweep outputs)
│   │   └── zone_touch/
│   │       └── acsil/             ← KEEP v31 backups co-located for easy rollback
│   ├── onboarding/                ← KEEP AS-IS
│   ├── scoring_models/            ← KEEP AS-IS
│   ├── data_loader.py             ← KEEP
│   └── feature_definitions.md     ← KEEP
├── stages/
│   ├── 01-data/
│   │   ├── analysis/              ← KEEP AS-IS
│   │   ├── data/                  ← KEEP (add README.md)
│   │   ├── output/                ← KEEP
│   │   ├── references/            ← KEEP
│   │   ├── scripts/               ← NEW: move hmm_regime_fitter.py, run_zone_prep.py here
│   │   ├── CONTEXT.md             ← KEEP
│   │   └── validate.py            ← KEEP (or move to scripts/)
│   ├── 02-features/               ← KEEP AS-IS (structure is clean)
│   ├── 03-hypothesis/             ← KEEP AS-IS
│   ├── 04-backtest/
│   │   ├── autoresearch/          ← KEEP (generic backtest engine)
│   │   ├── output/                ← KEEP
│   │   ├── p2_holdout/            ← KEEP
│   │   ├── references/            ← KEEP
│   │   ├── rotational/            ← KEEP (but archive sweep dirs)
│   │   └── zone_touch/            ← KEEP AS-IS
│   ├── 05-assessment/             ← KEEP AS-IS
│   ├── 06-deployment/             ← KEEP AS-IS
│   └── 07-live/                   ← KEEP (needs buildout later)
├── tests/                         ← KEEP AS-IS
├── Makefile                       ← NEW
├── CLAUDE.md                      ← KEEP
├── CONTEXT.md                     ← UPDATE (stage status is stale)
├── autocommit.sh                  ← KEEP
└── requirements.txt               ← KEEP
```

---

## 2. Migration Steps (Ordered)

### Phase 1: Safe cleanup — EXECUTED 2026-03-22

| # | Action | Status | Notes |
|---|---|---|---|
| 1.1 | Create `archive/` subdirectories | DONE | `data_snapshots/v31`, `sweeps`, `xtra` |
| 1.2 | Move v31 touch data backups to archive | DONE | 4 files, 3.2M total |
| 1.3 | ~~Move v31 ACSIL backups~~ | SKIPPED | Decision: keep v31 .cpp co-located in acsil/ for easy rollback |
| 1.4 | Move calibration CSV to analysis dir | DONE | 130M file, gitignore updated |
| 1.5 | Add `.pytest_cache/` to .gitignore | DONE | Also added gitignore for calibration CSV at new location |
| 1.6 | Update CONTEXT.md stage status table | DONE | Stages 01-05 updated to reflect actual content |
| 1.7 | Create `stages/01-data/data/README.md` | DONE | Data provenance and inventory |

See `docs/RESTRUCTURE_LOG.md` for full action log.

### Phase 2: Archive completed sweeps — EXECUTED 2026-03-22

421M moved, 840 files archived. Summary files preserved in `stages/04-backtest/references/sweep_summaries/`.

| # | Action | Status | Notes |
|---|---|---|---|
| 2.1 | Archive frozen_anchor_sweep | DONE | 379M, 423 files |
| 2.2 | Archive sweep_results | DONE | 30M, 367 files |
| 2.3 | Archive decoupled_seed_test | DONE | 6.4M, 22 files |
| 2.4 | Archive pullback_test | DONE | 6.1M, 28 files |
| 2.5 | Preserve summaries in active tree | DONE | 8 files → `stages/04-backtest/references/sweep_summaries/` |

See `docs/RESTRUCTURE_LOG.md` for full action log.

### Phase 3: Script organization

| # | Action | Risk | Notes |
|---|---|---|---|
| 3.1 | Create `stages/01-data/scripts/` | None | |
| 3.2 | Move `hmm_regime_fitter.py` to `scripts/` | **MEDIUM** — imported by tests | Update import path in `tests/test_hmm_regime_fitter.py` |
| 3.3 | Move `run_zone_prep.py` from `output/zone_prep/` to `scripts/` | **MEDIUM** — may be referenced in docs | Update any doc references |
| 3.4 | Create `Makefile` with initial targets | None | New file, additive only |

### Phase 4: Naming normalization (LOWEST PRIORITY — high effort, moderate risk)

| Issue | Recommendation | Risk |
|---|---|---|
| ACSIL file naming (PascalCase) | KEEP AS-IS — matches Sierra Chart convention | N/A |
| Data file naming (mixed) | KEEP AS-IS — files are SC exports, renaming breaks `.gitignore` patterns | N/A |
| `run_*.py` proliferation | Add header comments with status (ACTIVE / HISTORICAL / ONE-TIME) | Low |
| Period identifier casing (P1a vs p1a) | Standardize to lowercase in new code only | Low |

---

## 3. "Do Not Break" List

These paths are hardcoded in scripts and tests. Any rename requires updating all references.

### Tier 1: Data paths (referenced by 5+ scripts)

```
stages/01-data/data/bar_data/tick/NQ_BarData_250tick_rot_P1.csv
stages/01-data/data/bar_data/tick/NQ_BarData_250tick_rot_P2.csv
stages/01-data/data/bar_data/tick/NQ_BarData_1tick_rot_P1.csv
stages/01-data/data/bar_data/tick/NQ_BarData_1tick_rot_P2.csv
stages/01-data/data/bar_data/tick/ES_BarData_1tick_rot_P1.csv
stages/01-data/data/bar_data/volume/NQ_BarData_250vol_rot_P1.csv
stages/01-data/data/bar_data/volume/NQ_BarData_250vol_rot_P2.csv
stages/01-data/data/bar_data/time/NQ_BarData_10sec_rot_P1.csv
stages/01-data/data/bar_data/time/NQ_BarData_10sec_rot_P2.csv
```

### Tier 2: Shared code paths (referenced by 2+ files)

```
shared/data_loader.py
shared/archetypes/zone_touch/feature_engine.py
shared/archetypes/zone_touch/simulation_rules.md
shared/archetypes/zone_touch/zone_touch_simulator.py
shared/archetypes/rotational/rotational_simulator.py
shared/archetypes/rotational/rotational_engine.py
shared/archetypes/rotational/feature_engine.py
shared/archetypes/rotational/feature_evaluator.py
shared/archetypes/rotational/rotational_params.json
shared/scoring_models/zone_touch_v1.json
shared/scoring_models/hmm_regime_v1.pkl
shared/scoring_models/scoring_adapter.py
shared/scoring_models/scaffold_adapter.py
shared/feature_definitions.md
```

### Tier 3: Stage infrastructure paths

```
stages/01-data/output/data_manifest.json
stages/01-data/data/touches/NQ_ZRA_Hist_P1.csv
stages/01-data/data/touches/NQ_ZB4_signals_P1.csv
stages/01-data/data/touches/NQ_ZB4_signals_P2.csv
stages/01-data/data/bar_data/volume/NQ_BarData_250vol_P1.txt
stages/02-features/references/feature_rules.md
stages/03-hypothesis/references/strategy_archetypes.md
stages/04-backtest/p2_holdout/holdout_locked_P2.flag
stages/04-backtest/autoresearch/backtest_engine.py
```

### Tier 4: Config and pipeline infra

```
_config/instruments.md
_config/period_config.md
_config/pipeline_rules.md
_config/regime_definitions.md
_config/statistical_gates.md
CLAUDE.md
CONTEXT.md
audit/audit_log.md
```

---

## 4. Proposed Makefile (Initial)

```makefile
# pipeline/Makefile — Pipeline automation targets
SHELL := /bin/bash
PYTHON := python

.PHONY: validate zone-prep features freeze-features backtest replication-gate dashboard help

help:
	@echo "Pipeline targets:"
	@echo "  validate          — Run data validation (stage 01)"
	@echo "  zone-prep         — Run zone data preparation"
	@echo "  features          — Evaluate features for ARCH"
	@echo "  freeze-features   — Freeze features for ARCH"
	@echo "  backtest          — Run backtest for ARCH/PHASE"
	@echo "  replication-gate  — Run replication gate for ARCH"
	@echo "  dashboard         — Update results dashboard"
	@echo "  archive-sweep     — Archive a completed sweep"
	@echo "  check-p2          — Verify P2 holdout is locked"

validate:
	$(PYTHON) stages/01-data/validate.py

check-p2:
	@test -f stages/04-backtest/p2_holdout/holdout_locked_P2.flag && \
		echo "P2 LOCKED — holdout flag present" || \
		echo "WARNING: P2 NOT LOCKED — holdout flag missing"

archive-sweep:
	@test -n "$(NAME)" || (echo "Usage: make archive-sweep NAME=<sweep_dir>"; exit 1)
	mkdir -p archive/sweeps/$(NAME)
	mv stages/04-backtest/rotational/$(NAME) archive/sweeps/$(NAME)
	@echo "Archived $(NAME) to archive/sweeps/"
```

---

## 5. Summary of Recommendations

### ~~Do Now (zero risk)~~ DONE — Phase 1 executed 2026-03-22
1. ~~Create `archive/` subdirs and move v31 backups~~ DONE
2. ~~Add `.pytest_cache/` to .gitignore~~ DONE
3. ~~Update stale `CONTEXT.md` stage status~~ DONE
4. ~~Move calibration CSV out of production data dir~~ DONE
5. ~~Add `stages/01-data/data/README.md` with data provenance~~ DONE

### ~~Do Soon (low risk, high value)~~ Phase 2 DONE — 2026-03-22
6. ~~Archive completed rotational sweeps (~420M)~~ DONE

### Do Next
7. Create initial `Makefile` with `validate`, `check-p2`, `archive-sweep`

### Do Later (requires path updates)
8. Organize scripts into `scripts/` subdirs per stage
9. Add status headers to `run_*.py` files (ACTIVE vs HISTORICAL)
10. Standardize period identifier casing in new code

### Do Not Do
- Rename data files (31G of data, massive .gitignore impact, 40+ script references)
- Rename ACSIL files (SC convention requires specific names)
- Restructure `shared/archetypes/` (well-organized, heavily cross-referenced)
- Split stages by archetype at top level (current shared infra works)
