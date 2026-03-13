# Phase 1: Scaffold - Research

**Researched:** 2026-03-13
**Domain:** Static file scaffold — directory structure, config documents, stage contracts, shared resources, data migration, audit infrastructure
**Confidence:** HIGH

---

## Summary

Phase 1 is a documentation and file-creation phase — no pipeline Python code is required (the spec states this explicitly). The deliverable is a complete static layer: every `_config/` file, every stage `CONTEXT.md`, every `shared/` resource, and all data migrated to canonical locations. Any downstream phase (2 through 7) reads these files; if a file is missing, wrong, or inconsistently authored, it creates a silent misalignment that compounds across phases.

The primary risk in this phase is not technical complexity — it is authoring precision. Every file has an exact required format, specific line-count limits, and mandatory front-matter. The lost-in-middle conventions (operative instruction in first 5 lines, CLAUDE.md ≤60 lines, CONTEXT.md ≤80 lines, program.md ≤30 lines) are enforced by spec, not tooling. Violating them degrades agent performance in later phases without any immediate error signal.

The PREREQ work (repo fetches and data migration) must be verified before writing any CONTEXT.md files, because the ICM repo conventions (PREREQ-01) may require adjustments to the CONTEXT.md format that would require rework if ignored.

**Primary recommendation:** Work through the spec's Pass 1 task list in order (1-01 through 1-27), treating each task's "DONE CHECK" as a mandatory gate before the next task starts. Do not batch file creation — the cross-references between files (e.g., source_id in data_registry.md must match schema file names in 01-data/references/) require sequential verification.

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| PREREQ-01 | RinDig ICM repo fetched and reviewed; convention conflicts resolved | Spec explicitly requires this before writing any CONTEXT.md. ICM repo URL: https://github.com/RinDig/Interpreted-Context-Methdology |
| PREREQ-02 | karpathy/autoresearch repo fetched and reviewed; program.md format, train.py keep/revert logic understood | Confirmed real repo. URL: https://github.com/karpathy/autoresearch. Review program.md and keep/revert logic specifically. |
| PREREQ-03 | NQ bar data files migrated to 01-data/data/bar_data/ for P1 and P2 | Data already exists; task is migration to canonical path. Pattern: {SYMBOL}_BarData_*.txt |
| PREREQ-04 | Touch/signal data migrated to 01-data/data/touches/ for P1 and P2 | Data already exists; task is migration to canonical path |
| SCAF-01 | Root folder structure created (stages 01-07, _config, shared, dashboard, archive, audit) | Full mkdir tree specified in spec Task 1-01 |
| SCAF-02 | CLAUDE.md written (≤60 lines, 5 rules in first 20, hard prohibitions) | Full content provided in spec Task 1-02 |
| SCAF-03 | Root CONTEXT.md routing file (active stage, stage status table, human checkpoints) | Full content provided in spec Task 1-03 |
| SCAF-04 | _config/instruments.md (NQ registered with all fields, template for new instruments) | Full content provided in spec Task 1-04. NQ, ES, GC all shown. |
| SCAF-05 | _config/data_registry.md (all sources registered, type taxonomy, add-source workflow) | Schema and full content provided in spec Task 1-05 |
| SCAF-06 | _config/period_config.md (P1 IS + P2 OOS boundaries, P1a/P1b split, rolling-forward rules) | Full content in spec Task 1-06. P1: 2025-09-16 to 2025-12-14; P2: 2025-12-15 to 2026-03-02; P1a: to 2025-10-31; P1b: 2025-11-01 onward |
| SCAF-07 | _config/pipeline_rules.md (all 5 rules including Rule 4 + Rule 5, grandfathering note) | Full content in spec Task 1-07 |
| SCAF-08 | _config/statistical_gates.md (verdict thresholds, iteration budgets, Bonferroni gates, drawdown gate) | Full content in spec Task 1-08. Budgets: Stage 02=300, Stage 03=200, Stage 04=500 |
| SCAF-09 | _config/regime_definitions.md (3 dimensions, Stage 05 usage rules) | Full content in spec Task 1-09 |
| SCAF-10 | _config/context_review_protocol.md (file length limits, front-loading rule, staleness flag) | Full content in spec Task 1-10 |
| SCAF-11 | shared/feature_definitions.md (entry-time rule, template, empty registered features) | Full content in spec Task 1-11. Starts empty for new strategy from scratch. |
| SCAF-12 | 02-features/references/feature_rules.md (5 rules, ≤30 lines) | Full content in spec Task 1-11b |
| SCAF-13 | 02-features/references/feature_catalog.md (active/dropped/dead-end tables) | Full content in spec Task 1-11c. Starts empty for new strategy. |
| SCAF-14 | shared/scoring_models/ directory + _template.json + scoring_adapter.py (3 adapter stubs) | Full schema and code in spec Task 1-12. Three adapters: BinnedScoringAdapter, SklearnScoringAdapter, ONNXScoringAdapter |
| SCAF-15 | Stage 01 CONTEXT.md + reference schema files + data_manifest.json schema spec | Tasks 1-14, 1-14b, 1-14c in spec. Schema files: one per source_id. data_manifest.json schema fully specified. |
| SCAF-16 | Stage 02 CONTEXT.md | Task 1-15 in spec. Full content provided. |
| SCAF-17 | Stage 03 CONTEXT.md | Task 1-16 in spec. Full content provided. |
| SCAF-18 | Stage 04 CONTEXT.md + shared/archetypes/{archetype}/exit_templates.md | Tasks 1-17 and 1-17b in spec. Full content provided. |
| SCAF-19 | Stage 05 CONTEXT.md + verdict_criteria.md + statistical_tests.md | Tasks 1-18 and 1-18b in spec. Full content provided. |
| SCAF-20 | Stage 06 CONTEXT.md + context_package_spec.md + assemble_context.sh | Tasks 1-19 and 1-19b in spec. Full assemble_context.sh bash script provided. |
| SCAF-21 | Stage 07 CONTEXT.md + triggers/review_triggers.md | Tasks 1-20 and 1-20b in spec. Full content provided. |
| SCAF-22 | dashboard/results_master.tsv (header row, 24 columns) | Task 1-21 in spec. Exact header row specified. |
| SCAF-23 | dashboard/index.html stub | Task 1-22 in spec. Exact HTML stub provided. |
| SCAF-24 | audit/audit_log.md stub (append-only header + first manual entry) | Task 1-25 in spec. Template provided. |
| SCAF-25 | audit/audit_entry.sh (promote, deploy, note, fill commands) | Task 1-26 in spec. Full bash script provided in architecture doc lines 1215-1295. |
| SCAF-26 | 03-hypothesis/references/strategy_archetypes.md (template + simulator interface contract) | Task 1-27 in spec. Template and interface contract fully specified. |
</phase_requirements>

---

## Standard Stack

### Core
| Component | Version | Purpose | Why Standard |
|-----------|---------|---------|--------------|
| Bash scripts | System bash | autocommit.sh, assemble_context.sh, audit_entry.sh, git hooks | No Python dependency for infrastructure; runs on any system |
| Markdown | - | All _config/, CONTEXT.md, reference docs | Plain text; readable by agents and humans; ICM convention |
| JSON | - | _template.json, data_manifest.json schema, scoring model template | Machine-readable config; consumed by Python scripts in later phases |
| TSV | - | results_master.tsv, future results.tsv files | Tab-delimited; loadable as pandas DataFrame; no CSV quoting issues |
| Python 3 (stubs only) | 3.x | scoring_adapter.py (Protocol + class stubs) | Phase 1 creates stubs only; implementation in Phase 4 |

### Supporting
| Component | Version | Purpose | When to Use |
|-----------|---------|---------|-------------|
| git | System | Repo initialization, hooks setup | SCAF-01 creates repo; hooks are Pass 1.5 (Phase 3) but directory structure created in Phase 1 |
| HTML | - | dashboard/index.html stub | Stub only in Phase 1; full implementation deferred to Milestone 2 |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Markdown config files | YAML/TOML | Markdown is ICM convention and human-agent readable; YAML/TOML need parsers |
| TSV for results | CSV | TSV avoids quoting issues with free-text fields like regime_breakdown (pipe-delimited within a cell) |
| Bash scripts | Python scripts | Bash for infrastructure scripts (no pip install required); Python for pipeline logic in later phases |

**Installation:** No new dependencies required. This phase uses only: bash, git, a text editor, and Python stdlib (for the stubs skeleton in scoring_adapter.py).

---

## Architecture Patterns

### Recommended Project Structure
```
futures-pipeline/               # git root
├── CLAUDE.md                   # Agent identity and 5 pipeline rules
├── CONTEXT.md                  # Active stage router
├── _config/                    # Immutable settings — configure once
│   ├── instruments.md
│   ├── data_registry.md
│   ├── period_config.md
│   ├── pipeline_rules.md
│   ├── statistical_gates.md
│   ├── regime_definitions.md
│   └── context_review_protocol.md
├── shared/                     # Cross-stage resources
│   ├── feature_definitions.md
│   ├── archetypes/
│   │   └── {archetype}/        # One folder per strategy archetype
│   │       ├── feature_engine.py       (stub — populated in Phase 6)
│   │       ├── feature_evaluator.py    (stub — populated in Phase 6)
│   │       ├── simulation_rules.md     (stub — populated in Phase 4)
│   │       └── exit_templates.md       (SCAF-18 — populated in Phase 1)
│   └── scoring_models/
│       ├── _template.json
│       └── scoring_adapter.py  (3 stubs: Binned, Sklearn, ONNX)
├── stages/
│   ├── 01-data/{references,data/{touches,bar_data,labels},output}
│   ├── 02-features/{references,autoresearch/current_best,output}
│   ├── 03-hypothesis/{references,autoresearch/current_best,output/promoted_hypotheses}
│   ├── 04-backtest/{references,autoresearch/current_best,output,p2_holdout}
│   ├── 05-assessment/{references,output}
│   ├── 06-deployment/{references,output}
│   └── 07-live/{data,output,triggers}
├── dashboard/
│   ├── results_master.tsv      (24-column header only)
│   └── index.html              (stub)
├── audit/
│   ├── audit_log.md            (append-only)
│   └── audit_entry.sh
└── archive/
```

### Pattern 1: ICM Lost-in-Middle Authoring
**What:** Every file an agent reads at runtime has its operative instruction in the first 5 lines. Hard limits: CLAUDE.md ≤60 lines, CONTEXT.md ≤80 lines, program.md ≤30 lines.
**When to use:** Every single agent-readable file created in this phase.
**Example structure:**
```markdown
---
last_reviewed: 2026-03-13
reviewed_by: Ji
---
# Stage 04: Backtest Simulation
## YOUR TASK: Edit exit params JSON only. Metric: P1 PF at 3t, min 30 trades.
## CONSTRAINT: Do NOT edit backtest_engine.py. It is a fixed engine.
[rest of content — must stay ≤80 lines total]
```

### Pattern 2: Single Source of Truth Per Domain
**What:** Each type of configuration lives in exactly one canonical file. No stage hardcodes what belongs to a config file.
**When to use:** Any time a value appears in two places — it belongs in one and should be referenced from the other.

| Domain | Single Source | Who Reads It |
|--------|--------------|--------------|
| IS/OOS boundaries | `_config/period_config.md` | Stage 01 reads it, writes to data_manifest.json; all other stages read data_manifest.json |
| Instrument constants | `_config/instruments.md` | All pipeline scripts (Rule 5) |
| Statistical thresholds | `_config/statistical_gates.md` | Stage 05; also local-copied to verdict_criteria.md for agent access |
| Data source registry | `_config/data_registry.md` | Stage 01 uses it to populate data_manifest.json |
| Archetype registration | `strategy_archetypes.md` | Stage 03 agent, backtest engine (for simulator dispatch) |

### Pattern 3: Source ID Cross-Reference Integrity
**What:** The `source_id` string ties together four artifacts: registry entry in data_registry.md, data files in 01-data/data/{source_id}/, schema file at 01-data/references/{source_id}_schema.md, and data_manifest.json entries. The string must be identical in all four places.
**When to use:** When registering any data source during SCAF-05 / SCAF-15.

### Anti-Patterns to Avoid
- **Hardcoded file paths:** Any script that contains a literal path like `"../data/NQ_BarData_P1.txt"` violates Rule 5 / data registry discipline. All paths come from data_manifest.json.
- **Hardcoded instrument constants:** tick_size, cost_ticks, session times embedded in any file other than instruments.md violate Rule 5.
- **Operative instruction not in first 5 lines:** The most critical constraint for each file should be line 1-5 after front matter, not buried mid-document.
- **CONTEXT.md exceeding 80 lines:** Silent failure — agent reading a long file loses the critical constraints to context dilution.
- **Creating strategy_archetypes.md without a registered simulator:** The spec requires a simulator module path to be registered at archetype intake. A stub entry without a module reference creates a broken reference that will fail in Phase 4.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Scoring adapter interface | Custom per-archetype loader | `scoring_adapter.py` Protocol + factory pattern | Already fully specified in spec; three adapters cover all current and planned model formats |
| Data path resolution | Paths embedded in scripts | `data_manifest.json` produced by Stage 01 | Path abstraction is the mechanism that makes period rollover require zero code changes |
| Period boundary logic | Date-range checks in scripts | `period_config.md` → `data_manifest.json` chain | Single-file period update propagates automatically |
| Audit entry formatting | Ad-hoc log appends | `audit_entry.sh` with templated commands | Ensures append-only discipline; prevents accidental overwrites |
| Feature registration | Inline comments | `shared/feature_definitions.md` formal entry | Enables entry-time enforcement; provides catalog for Stage 02 agent |

**Key insight:** Phase 1 is entirely about creating the infrastructure that prevents hand-rolling in later phases. Every config file written now is a safeguard against a later agent making an incorrect assumption.

---

## Common Pitfalls

### Pitfall 1: P1a/P1b Split Boundary Not Committed First
**What goes wrong:** Any evaluation file (results.tsv rows, verdict outputs) committed before `period_config.md` contains the P1a/P1b boundary creates ambiguity about whether the split was locked before results were generated.
**Why it happens:** It is tempting to proceed with other scaffold tasks before finalizing dates.
**How to avoid:** Write and commit `_config/period_config.md` (SCAF-06) as one of the first tasks. STATE.md explicitly flags this: "P1a/P1b split boundary must be committed to period_config before ANY Stage 04 evaluation file exists."
**Warning signs:** git log shows an evaluation file committed before or at the same timestamp as period_config.md.

### Pitfall 2: ICM Repo Not Reviewed Before Writing CONTEXT.md Files
**What goes wrong:** The CONTEXT.md format, stage contract structure, and front-matter conventions may have specific requirements from the RinDig ICM repo that differ from the spec's inferred conventions. If CONTEXT.md files are written before PREREQ-01 is complete, they may need rework.
**Why it happens:** PREREQ-01/PREREQ-02 feel like optional background reading rather than hard gates.
**How to avoid:** Complete PREREQ-01 and PREREQ-02 before writing any CONTEXT.md or program.md files. The spec states: "Fetch and review before writing CONTEXT.md files."
**Warning signs:** CONTEXT.md files written before `git log` shows a commit acknowledging ICM repo review.

### Pitfall 3: Source ID Mismatch Between Registry and Schema Files
**What goes wrong:** data_registry.md lists `source_id: zone_csv_v2` but the schema file is named `01-data/references/zone_touch_schema.md`. Stage 01 validation cannot match them.
**Why it happens:** Schema file is named by data type rather than source_id.
**How to avoid:** The schema file name must exactly match the source_id string from data_registry.md. Example: source_id `zone_csv_v2` → schema file `01-data/references/zone_csv_v2_schema.md`.
**Warning signs:** Stage 01 validation fails to find schema for a registered source.

### Pitfall 4: scoring_adapter.py Written as Full Implementation Instead of Stubs
**What goes wrong:** BinnedScoringAdapter is fully implemented in Phase 1 but without the actual scoring model JSON to test against, the implementation may be incorrect in ways that only surface in Phase 4.
**Why it happens:** The spec provides the full class structure, tempting complete implementation.
**How to avoid:** Write the Protocol and class signatures as specified (these are required by SCAF-14), but mark method bodies as `raise NotImplementedError("Implement in Phase 4")` stubs. The done-check in the spec says "BinnedScoringAdapter fully implemented and tested against at least one known scoring model JSON" — this requires actual data. If scoring model JSON is available during Phase 1, full implementation is correct; if not, stub it.
**Warning signs:** scoring_adapter.py has `pass` bodies that silently return None instead of raising errors.

### Pitfall 5: dashboard/results_master.tsv Column Count Error
**What goes wrong:** Header row has wrong number of columns (not exactly 24) or uses inconsistent delimiter (spaces instead of tabs).
**Why it happens:** TSV is hand-authored; tab characters are invisible in editors.
**How to avoid:** Create the file programmatically or verify with `awk -F'\t' '{print NF}' results_master.tsv` after creation. The spec provides the exact 24-column header.
**Warning signs:** Column count command returns anything other than 24.

### Pitfall 6: assemble_context.sh Written With Hardcoded Archetype Names
**What goes wrong:** Script uses a hardcoded archetype name instead of reading it from frozen_params.json, breaking the extensibility contract.
**Why it happens:** It is tempting to simplify the script for the current archetype.
**How to avoid:** The script must read archetype from `frozen_params.json` at runtime, as shown in the spec. This is the same single-source-of-truth principle applied to shell scripts.

---

## Code Examples

Verified patterns directly from spec/architecture docs:

### CLAUDE.md First 20 Lines Pattern (SCAF-02)
```markdown
# CLAUDE.md — Futures Pipeline Agent Identity
last_reviewed: 2026-03-13

## YOU ARE
A trading strategy research assistant operating inside the futures pipeline.
You run inside specific stage directories. You do not have visibility across all stages.

## FIVE PIPELINE RULES (never violate)
1. P1 calibrate — IS data used freely for calibration and search
2. P2 one-shot — OOS runs exactly once with frozen params; never re-run
3. Entry-time only — features must be computable at entry time; no lookahead
4. Internal replication — strategy must pass P1b before P2 is unlocked
5. Instrument constants from registry — read tick size, cost_ticks, session times from _config/instruments.md; never hardcode

## HARD PROHIBITIONS
- NEVER modify backtest_engine.py
- NEVER run any script against P2 data if holdout_locked_P2.flag exists
- NEVER delete or modify audit/audit_log.md entries
- NEVER modify _config/ files without human instruction
- NEVER hardcode instrument constants (tick size, cost_ticks, session times) — read from _config/instruments.md
```

### Root Folder Structure Creation (SCAF-01)
```bash
# From spec Task 1-01 — run from desired parent directory
mkdir -p futures-pipeline/{_config,shared/{scoring_models,archetypes/{archetype}},dashboard,archive}
mkdir -p futures-pipeline/stages/{01-data/{references,data/{touches,bar_data,labels},output},02-features/{references,autoresearch/current_best,output},03-hypothesis/{references,autoresearch/current_best,output/promoted_hypotheses},04-backtest/{references,autoresearch/current_best,output,p2_holdout},05-assessment/{references,output},06-deployment/{references,output},07-live/{data,output,triggers}}
mkdir -p futures-pipeline/audit
git init futures-pipeline && cd futures-pipeline
```

### scoring_adapter.py Stub Pattern (SCAF-14)
```python
# shared/scoring_models/scoring_adapter.py
# All adapters expose: score(touch_df) -> pd.Series[float]
# Engine calls adapter.score() — never touches model internals directly.

from typing import Protocol
import pandas as pd

class ScoringAdapter(Protocol):
    def score(self, touch_df: pd.DataFrame) -> pd.Series: ...

class BinnedScoringAdapter:
    """Wraps the existing JSON scoring model (bin_edges + weights). Current default."""
    def __init__(self, model_path: str): ...
    def score(self, touch_df: pd.DataFrame) -> pd.Series: ...

class SklearnScoringAdapter:
    """Wraps a scikit-learn model (RF, XGBoost). Future path for Stage 02 ML scoring."""
    def __init__(self, model_path: str): ...
    def score(self, touch_df: pd.DataFrame) -> pd.Series: ...

class ONNXScoringAdapter:
    """Wraps an ONNX model. Future path for neural net scoring."""
    def __init__(self, model_path: str): ...
    def score(self, touch_df: pd.DataFrame) -> pd.Series: ...

def load_scoring_adapter(model_path: str, adapter_type: str) -> ScoringAdapter:
    """Factory — reads adapter_type from archetype config. Returns the right adapter."""
    ...
```

### audit_entry.sh (SCAF-25)
Full implementation is in `Futures_Pipeline_Architecture_ICM.md` lines 1215-1295. The four commands are: `promote`, `deploy`, `note`, `fill`. All write to `$(git rev-parse --show-toplevel)/audit/audit_log.md`.

### data_manifest.json Schema (SCAF-15)
```json
{
  "generated": "YYYY-MM-DD HH:MM:SS",
  "periods": {
    "P1": {
      "start": "YYYY-MM-DD",
      "end": "YYYY-MM-DD",
      "sources": {
        "{source_id}": {
          "path": "stages/01-data/data/{source_folder}/{filename}",
          "row_count": 0,
          "schema_version": "{schema_doc_filename}",
          "validation_status": "PASS"
        }
      }
    }
  },
  "bar_offset": {
    "verified": true,
    "offset_bars": 0,
    "verified_date": "YYYY-MM-DD",
    "method": "[how offset was determined]"
  },
  "validation_summary": {
    "status": "PASS",
    "warnings": [],
    "errors": []
  }
}
```

### results_master.tsv Header (SCAF-22)
```
run_id	stage	timestamp	hypothesis_name	archetype	version	features	pf_p1	pf_p2	trades_p1	trades_p2	mwu_p	perm_p	pctile	n_prior_tests	verdict	sharpe_p1	max_dd_ticks	avg_winner_ticks	dd_multiple	win_rate	regime_breakdown	api_cost_usd	notes
```
(24 columns, tab-delimited, single header row)

---

## State of the Art

| Old Approach | Current Approach | Notes |
|--------------|------------------|-------|
| Hardcoded paths in calibration scripts | data_manifest.json + data_registry.md | Enables period rollover with zero code changes |
| Per-run verdict reports only | results_master.tsv across all stages | Single aggregated ledger enables trend analysis and budget enforcement |
| be_trigger_ticks as separate config field | trail_steps[0] with new_stop_ticks=0 is the BE trigger | Q3 answer — redundant field removed |
| Separate calibration scripts per mode | Single backtest_engine.py with dynamic dispatch | Option B; new archetype = new module, no engine changes |

**Deprecated/outdated:**
- `be_trigger_ticks` field: removed per Q3 answer; BE is trail_steps[0] with new_stop_ticks=0
- `acsil_templates/` directory: replaced by `assemble_context.sh` + Claude Code generation approach

---

## Open Questions

1. **ICM Repo Conventions (PREREQ-01)**
   - What we know: CONTEXT.md front-matter format and stage contract tables are inferred from spec
   - What's unclear: Whether RinDig ICM has specific file naming, front-matter, or section ordering requirements that differ from the spec's examples
   - Recommendation: Fetch repo as first action in Phase 1; compare CONTEXT.md examples with spec Task 1-14 through 1-20 examples; update any that differ before writing final versions

2. **Archetype Name for v1**
   - What we know: Architecture doc shows `zone_touch` as the archetype name throughout (e.g., `shared/archetypes/zone_touch/`)
   - What's unclear: Whether `{archetype}` placeholder in spec Task 1-01 mkdir command should be `zone_touch` or a different identifier
   - Recommendation: Use `zone_touch` as the archetype directory name, consistent with architecture doc examples

3. **Data File Format for Migration (PREREQ-03, PREREQ-04)**
   - What we know: NQ bar data uses pattern `{SYMBOL}_BarData_*.txt`; touch data source_id is inferred as `zone_csv_v2` from architecture doc
   - What's unclear: Exact filenames of the actual data files to migrate; whether P1 and P2 are in separate files or need to be split
   - Recommendation: User to confirm data file locations and naming during PREREQ-03/04 execution

4. **Archetype Source ID Registration (SCAF-05)**
   - What we know: Architecture doc references `zone_csv_v2`, `bar_data`, `sbb_labels` as source IDs
   - What's unclear: Which source IDs apply to the current strategy from scratch (no prior strategy to migrate)
   - Recommendation: Register `bar_data` (required for all archetypes) and the touch/signal data source once PREREQ-04 confirms what data exists

---

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | Shell verification (bash done-checks) — no automated test framework required for Phase 1 |
| Config file | None — Phase 1 is static file creation |
| Quick run command | `find . -type f \| wc -l` (count files), manual spot-checks |
| Full suite command | Per-task DONE CHECKs from functional spec |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Verification Command | Notes |
|--------|----------|-----------|---------------------|-------|
| PREREQ-01 | ICM repo fetched and reviewed | Manual | `ls ../Interpreted-Context-Methdology/` | Human confirms conventions reviewed |
| PREREQ-02 | karpathy/autoresearch reviewed | Manual | `ls ../autoresearch/program.md` | Human confirms keep/revert logic read |
| PREREQ-03 | Bar data present in canonical location | Shell | `ls stages/01-data/data/bar_data/` shows P1 and P2 files | |
| PREREQ-04 | Touch data present in canonical location | Shell | `ls stages/01-data/data/touches/` shows P1 and P2 files | |
| SCAF-01 | Root folder structure | Shell | `find . -type d \| head -40` shows full tree | Spec DONE CHECK |
| SCAF-02 | CLAUDE.md ≤60 lines, 5 rules in first 20 | Shell | `wc -l CLAUDE.md` returns ≤60; `head -20 CLAUDE.md \| grep -c "Rule"` returns 5 | |
| SCAF-03 | Root CONTEXT.md ≤80 lines with required sections | Shell | `wc -l CONTEXT.md` returns ≤80 | |
| SCAF-04 | instruments.md has NQ with all required fields | Manual | `grep -c "Tick size\|Tick value\|Session\|Cost model" _config/instruments.md` returns ≥4 | |
| SCAF-05 | data_registry.md has all archetype sources registered | Manual | Review registry; confirm each source_id has matching schema file in 01-data/references/ | |
| SCAF-06 | period_config.md committed before evaluation files | Git | `git log --oneline -- _config/period_config.md` shows commit before any results.tsv commit | CRITICAL — STATE.md blocker |
| SCAF-07 | pipeline_rules.md has all 5 rules + grandfathering | Manual | `grep -c "^## Rule" _config/pipeline_rules.md` returns 5 | |
| SCAF-08 | statistical_gates.md has thresholds + budgets + Bonferroni | Manual | Confirm 3 iteration budget rows and 4 Bonferroni rows present | |
| SCAF-09 | regime_definitions.md has 3 dimensions + Stage 05 usage rule | Manual | Confirm Trend, Volatility, Macro sections present | |
| SCAF-10 | context_review_protocol.md has limits + front-loading + staleness | Manual | Confirm 4-row length limits table and FRONT-LOADING RULE section present | |
| SCAF-11 | feature_definitions.md starts with entry-time rule and empty registered features | Manual | File exists; "Registered Features" section shows "(empty)" | |
| SCAF-12 | feature_rules.md ≤30 lines, 5 rules | Shell | `wc -l 02-features/references/feature_rules.md` returns ≤30 | |
| SCAF-13 | feature_catalog.md has 3-table structure | Manual | Active/Dropped/Dead ends sections present | |
| SCAF-14 | scoring_models/ has _template.json and scoring_adapter.py with 3 stubs | Shell | `ls shared/scoring_models/` shows both files; `grep -c "class.*Adapter" scoring_adapter.py` returns ≥3 | |
| SCAF-15 | Stage 01 CONTEXT.md + schema files + data_manifest schema | Manual | CONTEXT.md ≤80 lines; schema files present matching data_registry source IDs; data_manifest.json schema documented | |
| SCAF-16 | Stage 02 CONTEXT.md | Shell | `wc -l stages/02-features/CONTEXT.md` returns ≤80 | |
| SCAF-17 | Stage 03 CONTEXT.md | Shell | `wc -l stages/03-hypothesis/CONTEXT.md` returns ≤80 | |
| SCAF-18 | Stage 04 CONTEXT.md + exit_templates.md | Shell | Both files exist; CONTEXT.md ≤80 lines | |
| SCAF-19 | Stage 05 CONTEXT.md + verdict_criteria.md + statistical_tests.md | Manual | All 3 files exist; verdict thresholds in criteria match statistical_gates.md | |
| SCAF-20 | Stage 06 CONTEXT.md + context_package_spec.md + assemble_context.sh | Shell | `bash stages/06-deployment/assemble_context.sh` produces output without "file not found" errors (requires later phases' output files to exist) | Script correctness only verifiable fully in Phase 4+ |
| SCAF-21 | Stage 07 CONTEXT.md + review_triggers.md | Manual | Both files exist; trigger thresholds present | |
| SCAF-22 | results_master.tsv has exactly 24-column header | Shell | `awk -F'\t' '{print NF}' dashboard/results_master.tsv` returns 24 | |
| SCAF-23 | dashboard/index.html renders in browser | Manual | Open in browser; placeholder text visible | |
| SCAF-24 | audit_log.md has header + first entry | Manual | File exists; APPEND-ONLY header present; first MANUAL_NOTE present | |
| SCAF-25 | audit_entry.sh runs for all 4 commands | Manual | `bash audit/audit_entry.sh note` prompts and appends entry | Full round-trip test |
| SCAF-26 | strategy_archetypes.md has template + simulator interface contract | Manual | Template block and `def run(bar_df, touch_row, config, bar_offset) -> SimResult` interface present | |

### Sampling Rate
- **Per task completion:** Run the DONE CHECK from the functional spec task
- **Per wave merge:** Full file-existence check: `find . -name "*.md" -o -name "*.json" -o -name "*.tsv" -o -name "*.sh" -o -name "*.html" -o -name "*.py" | sort`
- **Phase gate:** All 26 SCAF + 4 PREREQ done-checks must pass before Phase 1 is complete

### Wave 0 Gaps
None — Phase 1 creates all files from scratch. No pre-existing test infrastructure applies. All verification is via shell done-checks and manual inspection as specified in the functional spec.

---

## Sources

### Primary (HIGH confidence)
- `Futures_Pipeline_Functional_Spec.md` (v1.0, 2026-03-11) — authoritative build spec; all task content, done-checks, file schemas sourced from here. Every SCAF requirement has a corresponding task (1-01 through 1-27) with exact content.
- `Futures_Pipeline_Architecture_ICM.md` (2026-03-13) — full directory tree, all audit event templates, audit_entry.sh implementation, assemble_context.sh implementation, backtest engine spec for context.
- `.planning/REQUIREMENTS.md` — requirement IDs and descriptions
- `.planning/PROJECT.md` — constraints, key decisions, IS/OOS period values
- `.planning/STATE.md` — known blockers (P1a/P1b ordering, hmmlearn pin, quantstats compatibility)
- `.planning/ROADMAP.md` — phase dependencies and success criteria

### Secondary (MEDIUM confidence)
- ICM repo reference (https://github.com/RinDig/Interpreted-Context-Methdology) — architecture doc references it as the methodology source; not directly fetched this session (PREREQ-01 is pending)
- karpathy/autoresearch (https://github.com/karpathy/autoresearch) — architecture doc confirms it is real and reviewed; not fetched this session (PREREQ-02 is pending)

### Tertiary (LOW confidence)
- None — all findings are sourced from the project's own authoritative spec documents

---

## Metadata

**Confidence breakdown:**
- Requirement mapping: HIGH — every SCAF/PREREQ requirement maps directly to a numbered task in the functional spec with exact content
- File content / schemas: HIGH — spec provides verbatim content for every file, not just descriptions
- Architecture patterns: HIGH — architecture doc provides the full directory tree and cross-reference rules
- PREREQ verification: MEDIUM — the PREREQ tasks (ICM repo review, karpathy review) require external repo fetches that are pending; the expected content is well-specified but actual convention differences unknown until reviewed
- Data file specifics: MEDIUM — exact filenames of source data to migrate are not in the spec; require confirmation from user

**Research date:** 2026-03-13
**Valid until:** 2026-06-13 (stable spec; only changes if spec is revised)
