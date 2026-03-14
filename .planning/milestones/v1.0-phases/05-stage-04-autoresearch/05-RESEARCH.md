# Phase 5: Stage 04 Autoresearch - Research

**Researched:** 2026-03-14
**Domain:** Python autoresearch driver loop, keep/revert experiment harness, TSV logging, evaluate_features dispatcher
**Confidence:** HIGH — all findings verified directly from project source files, functional spec, and existing tested code

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| AUTO-01 | Stage 04 driver.py (keep/revert loop, budget enforcement, EXPERIMENT_ANOMALY handling) | Full spec in Functional_Spec.md lines 1998–2075; exact pseudocode provided |
| AUTO-02 | Stage 04 program.md (≤30 lines, machine-readable METRIC/KEEP RULE/BUDGET) | Exact template in Functional_Spec.md lines 2034–2052 |
| AUTO-03 | Stage 04 overnight test (50 experiments, results.tsv populated, keep/revert verified) | Test protocol in Functional_Spec.md line 2071–2075; seeding step required first |
| AUTO-04 | evaluate_features.py dispatcher (~30 lines, loads archetype evaluator) | Spec lines 2079–2122; pure dispatcher pattern documented |
| AUTO-05 | shared/archetypes/zone_touch/feature_evaluator.py (standard interface) | Interface contract lines 2102–2106; responsibilities lines 2095–2101 |
</phase_requirements>

---

## Summary

Phase 5 wires the autoresearch loop for Stage 04: the overnight parameter optimizer that runs the fixed `backtest_engine.py` harness repeatedly, keeps or reverts `exit_params.json`, and logs every experiment to `results.tsv`. This phase also builds the Stage 02 feature evaluation infrastructure (AUTO-04, AUTO-05), which the functional spec requires to be built before the Stage 02 driver — but only after Stage 04's overnight test passes.

The pattern is a direct implementation of the karpathy/autoresearch protocol reviewed in PREREQ-02. The mapping is: `train.py` → `backtest_engine.py` (fixed, NEVER MODIFY), `program.md` → human steering file, results.tsv → persistent experiment log. The keep/revert loop is pure Python subprocess + file management — no exotic dependencies.

All key interfaces are already locked and tested: the engine CLI signature, result.json schema, config JSON format, and trail step validation rules are all verified from Phase 4. Phase 5 wraps them in an unattended loop.

**Primary recommendation:** Build driver.py first around the exact pseudocode from the functional spec, seed results.tsv with the reference config as the baseline before the first overnight run, then run 50 experiments to validate loop health before scaling to 500.

---

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| subprocess | stdlib | Run backtest_engine.py as a child process | Engine is a separate script; subprocess.run with capture_output is the correct invocation pattern |
| json | stdlib | Read result.json, write exit_params.json | All engine I/O is JSON |
| csv / tsv | stdlib (open + write) | Append rows to results.tsv | Tab-delimited; no external library needed |
| pathlib.Path | stdlib | Path manipulation for current_best/ | Already used throughout project |
| importlib | stdlib | evaluate_features.py loads archetype evaluator dynamically | Matches engine's load_simulator pattern |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| sys, os | stdlib | sys.path manipulation in evaluate_features.py | Archetype directory must be added to path for evaluator import |
| datetime | stdlib | Timestamps for EXPERIMENT_ANOMALY log entries | ISO format timestamps in audit entries |
| copy / shutil | stdlib | Copy exit_params.json to/from current_best/ | Backup/restore on keep/revert |

No external package dependencies needed for Phase 5.

---

## Architecture Patterns

### File Locations
```
stages/04-backtest/autoresearch/
  driver.py                    # NEW — AUTO-01: keep/revert loop
  program.md                   # NEW — AUTO-02: human steering, machine-readable fields
  current_best/
    exit_params.json           # NEW — seeded from config_schema.json baseline
  results.tsv                  # NEW — one row per experiment
  backtest_engine.py           # FIXED — NEVER MODIFY

stages/02-features/autoresearch/
  evaluate_features.py         # NEW — AUTO-04: pure dispatcher (~30 lines)

shared/archetypes/zone_touch/
  feature_evaluator.py         # NEW — AUTO-05: archetype-specific harness
  zone_touch_simulator.py      # EXISTS — no changes
  simulation_rules.md          # EXISTS — no changes
  exit_templates.md            # EXISTS — no changes
```

### Pattern 1: Keep/Revert Loop (Stage 04 driver.py)

**What:** Each iteration: read program.md, check budget, propose params, run engine, evaluate metric, keep or revert, log TSV row.

**When to use:** Every Stage 04 autoresearch experiment

**Example (from Functional_Spec.md lines 1981–1991 and 2003–2031):**
```python
# Source: Futures_Pipeline_Functional_Spec.md lines 2003–2031
metric_field, improvement_threshold, budget_limit = read_loop_config(program_md)
while experiment_count < MAX_EXPERIMENTS:
    n_prior_tests = count_prior_tests(results_tsv, archetype)
    if n_prior_tests >= budget_limit:
        log("Budget exhausted. Stopping.")
        break
    params = propose_next_params(results_tsv, current_best, program_md)
    write_params(exit_params_json, params)
    result = subprocess.run(
        ["python", engine_path, "--config", exit_params_json, "--output", result_json],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        log_experiment_anomaly(result.stderr)
        revert_to_prior_best()
        continue
    metric_value = read_metric(result_json, metric_field)
    n_trades = read_n_trades(result_json)
    verdict = "kept" if (metric_value > current_best_metric + improvement_threshold
                         and n_trades >= MIN_TRADES) else "reverted"
    if verdict == "kept":
        current_best_metric = metric_value
        save_current_best(params)  # copy exit_params.json → current_best/exit_params.json
    else:
        revert_to_prior_best()     # restore current_best/exit_params.json → exit_params.json
    append_tsv(results_tsv, params, metric_value, n_trades, n_prior_tests, verdict)
    experiment_count += 1
```

### Pattern 2: program.md Machine-Readable Fields

**What:** driver.py parses three specific lines from program.md at the start of each experiment. These are the only machine-readable fields — everything else is human-readable direction.

**Exact template (from Functional_Spec.md lines 2034–2052):**
```markdown
# Stage 04 Parameter Optimization
EDIT: exit_params.json only. DO NOT touch backtest_engine.py.
METRIC: pf
KEEP RULE: 0.05
BUDGET: 500

## Current search direction
[Human writes here each evening]

## Prior best
[Driver updates from results.tsv automatically]
```

**Parsing rules:**
- `METRIC:` — field name to extract from result.json (e.g. `pf`)
- `KEEP RULE:` — improvement threshold as float (e.g. `0.05`)
- `BUDGET:` — integer experiment limit; driver stops when `n_prior_tests >= BUDGET`

### Pattern 3: evaluate_features.py Dispatcher (AUTO-04)

**What:** Pure dispatcher — reads archetype from program.md, loads evaluator via importlib, calls evaluate(), writes feature_evaluation.json. No data loading, no metric logic.

**Example (from Functional_Spec.md lines 2084–2089):**
```python
# Source: Futures_Pipeline_Functional_Spec.md lines 2084–2089
# evaluate_features.py — fixed dispatcher (~30 lines)
archetype = read_archetype_from_program_md()
evaluator = load_module(f"shared/archetypes/{archetype}/feature_evaluator.py")
result = evaluator.evaluate()   # standard interface
write_evaluation_json(result)
```

### Pattern 4: feature_evaluator.py Standard Interface (AUTO-05)

**What:** Archetype-specific evaluation harness. Loads P1 data, computes predictive spread per feature, returns structured dict.

**Interface contract (from Functional_Spec.md lines 2102–2106):**
```python
# Source: Futures_Pipeline_Functional_Spec.md lines 2102–2106
def evaluate() -> dict:
    # Returns: {"features": [{name, spread, mwu_p, kept}], "n_touches": int}
    ...
```

**Output JSON written by dispatcher (feature_evaluation.json):**
```json
{
  "timestamp": "...",
  "features_evaluated": [
    {"name": "feature_1", "spread": 0.34, "p_value": 0.02, "bins": 3, "result": "kept"},
    {"name": "feature_2", "spread": 0.08, "p_value": 0.41, "result": "reverted"}
  ]
}
```

### Pattern 5: EXPERIMENT_ANOMALY Audit Entry

**What:** Driver writes directly to audit/audit_log.md when engine returns non-zero exit code. Does NOT abort the loop.

**Exact template (from Functional_Spec.md lines 1691–1703):**
```markdown
## {timestamp} | EXPERIMENT_ANOMALY
- stage: 04-backtest
- run_id: {git short hash}
- detected_by: {exit_code / stale_results_tsv / empty_output}
- error_output: {last 20 lines of stderr}
- investigation: # TODO: fill in
- resolution: # TODO: fill in
- resolution_commit: # TODO: fill in
- generated_by: autoresearch driver
```
After writing: `git add audit/audit_log.md` (do not commit — autocommit.sh picks it up).

### Pattern 6: results.tsv Row Schema

The 24-column TSV matches `dashboard/results_master.tsv` header. For Stage 04 driver rows, the key populated columns are:

| Column | Source | Notes |
|--------|--------|-------|
| run_id | `git rev-parse --short HEAD` after each experiment | 7-char hash |
| stage | `"04-backtest"` | literal |
| timestamp | datetime.now() ISO | |
| archetype | from config | `"zone_touch"` |
| pf_p1 | result.json `pf` | |
| trades_p1 | result.json `n_trades` | |
| n_prior_tests | count of rows in results.tsv before appending | driver counts, not hooks |
| verdict | `"kept"` / `"reverted"` / `"seeded"` | |
| api_cost_usd | blank | no LLM call in Stage 04 engine runs |

**CRITICAL:** `run_id` must be written by calling `git rev-parse --short HEAD` immediately after each experiment completes, before autocommit fires (30s window).

### Anti-Patterns to Avoid

- **Modifying backtest_engine.py:** NEVER. Hard prohibition in CLAUDE.md. Driver only modifies exit_params.json.
- **Aborting on single anomaly:** Engine returning non-zero exit code should log EXPERIMENT_ANOMALY and continue — not stop the overnight run.
- **Hardcoding budget:** Budget must come from `BUDGET:` line in program.md, not from a constant in driver.py. This makes it adjustable without code changes.
- **n_prior_tests from program.md:** Count rows in results.tsv every iteration — never cache or persist this count elsewhere. The spec is explicit (statistical_gates.md line 40: "Driver counts rows in results.tsv").
- **Forgetting seeding:** The driver searches from a baseline. Running with no results.tsv seeded means the first experiment has no `current_best` to compare against.
- **Path resolution:** Engine path must be absolute or resolved relative to repo root. The engine uses `parents[3]` to find repo root; driver must ensure consistent working directory or use absolute paths.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| File backup/restore | Custom snapshot system | shutil.copy2 to current_best/ | Simple, atomic, already the documented pattern |
| Budget enforcement | DB or external state | Count TSV rows per iteration | Spec is explicit; TSV is ground truth |
| Config mutation | Template engine | Read JSON, modify dict, write JSON | Config is a simple dict; keep it simple |
| Audit log write | Log framework | Direct file open/append | audit_log.md is markdown; no library needed |
| Archetype module load | Plugin system | importlib.import_module | Matches existing engine load_simulator pattern |

---

## Common Pitfalls

### Pitfall 1: run_id Race with autocommit.sh
**What goes wrong:** autocommit.sh fires every 30 seconds. If driver writes results.tsv row before calling `git rev-parse --short HEAD`, the commit that fires may be the NEXT one, giving the wrong run_id.
**Why it happens:** autocommit is polling, not synchronous with driver.
**How to avoid:** Call `git rev-parse --short HEAD` immediately after writing result.json and before appending the TSV row. The 30-second window is narrow but sufficient if done in order.
**Warning signs:** run_id values in results.tsv that don't match any experiment-related commit.

### Pitfall 2: Budget Read Once vs Per Iteration
**What goes wrong:** Driver reads program.md once at startup; human updates BUDGET in program.md mid-run; budget change has no effect.
**How to avoid:** The spec says "read program.md at the start of each experiment" (Functional_Spec.md line 1962). Re-parse program.md every iteration.
**Warning signs:** Budget changes don't take effect until driver restart.

### Pitfall 3: current_best/ Directory Empty on First Run
**What goes wrong:** `revert_to_prior_best()` tries to copy from current_best/exit_params.json, which doesn't exist yet if seeding step was skipped.
**How to avoid:** Seeding step is mandatory. Before first run, copy config_schema.json (or a hand-tuned starting config) to current_best/exit_params.json and add one row to results.tsv with `verdict: seeded`.
**Warning signs:** FileNotFoundError on first revert.

### Pitfall 4: n_prior_tests Off-By-One
**What goes wrong:** Driver counts rows in results.tsv AFTER appending the new row, causing the Bonferroni gate to apply one test too early.
**How to avoid:** Count rows BEFORE the experiment, write `n_prior_tests` to TSV based on that pre-experiment count. This matches "n_prior_tests = rows at start of this experiment."
**Warning signs:** Stage 05 reports n_prior_tests that is 1 higher than expected.

### Pitfall 5: propose_next_params Infinite Loop
**What goes wrong:** param proposal generates the same config every time; every experiment is reverted; overnight run makes no progress.
**How to avoid:** Proposal logic must sample or mutate from current_best, not regenerate the same config. Read results.tsv to avoid re-testing known-bad configurations.
**Warning signs:** All 50 overnight experiments return identical metric values and all revert.

### Pitfall 6: evaluate_features.py Importing Archetype State
**What goes wrong:** evaluate_features.py imports something from the archetype module at module level, not inside evaluate(). If the archetype changes, the dispatcher retains stale state.
**How to avoid:** dispatcher must load the evaluator module fresh via importlib each run, or at minimum call evaluator.evaluate() as a stateless function.

### Pitfall 7: Trail Step Validation on Proposed Params
**What goes wrong:** Driver proposes a config that violates trail step rules; engine returns non-zero exit code; every experiment is an EXPERIMENT_ANOMALY; overnight run logs 50 anomalies and never keeps.
**How to avoid:** driver's propose_next_params must enforce the 5 trail step validation rules before writing params (or catch the anomaly and retry with valid params). The rules are documented in config_schema.md and enforced in backtest_engine.py's validate_trail_steps().
**Warning signs:** EXPERIMENT_ANOMALY log shows "trail_steps" in error output.

---

## Code Examples

Verified patterns from existing project source:

### Engine CLI Invocation (from backtest_engine.py line 420–427)
```python
# Source: stages/04-backtest/autoresearch/backtest_engine.py lines 420-427
# python backtest_engine.py --config params.json --output result.json
result = subprocess.run(
    ["python", str(engine_path), "--config", str(config_path), "--output", str(result_path)],
    capture_output=True,
    text=True,
    cwd=str(repo_root),  # engine uses parents[3] for repo root, so cwd must be repo root
)
```

### Result JSON Schema (from backtest_engine_qa.md Q6)
```json
{
  "pf": 0.0,
  "n_trades": 0,
  "win_rate": 0.0,
  "total_pnl_ticks": 0.0,
  "max_drawdown_ticks": 0.0,
  "per_mode": {
    "M1": {"pf": 0.0, "n_trades": 0, "win_rate": 0.0}
  }
}
```
Keep decision: `result["pf"] > current_best_pf + 0.05 AND result["n_trades"] >= 30`

### Config JSON Structure (from stages/04-backtest/references/config_schema.json)
```json
{
  "version": "v1",
  "instrument": "NQ",
  "touches_csv": "stages/01-data/data/touches/ZRA_Hist_P1.csv",
  "bar_data": "stages/01-data/data/bar_data/volume/NQ_BarData_250vol_P1.txt",
  "scoring_model_path": "shared/scoring_models/zone_touch_v1.json",
  "archetype": {"name": "zone_touch", "simulator_module": "zone_touch_simulator", "scoring_adapter": "BinnedScoringAdapter"},
  "active_modes": ["M1"],
  "routing": {"score_threshold": 48, "seq_limit": 3},
  "M1": {
    "stop_ticks": 135,
    "leg_targets": [50, 120, 240],
    "trail_steps": [
      {"trigger_ticks": 30, "new_stop_ticks": 0},
      {"trigger_ticks": 60, "new_stop_ticks": 20},
      {"trigger_ticks": 120, "new_stop_ticks": 50},
      {"trigger_ticks": 200, "new_stop_ticks": 100}
    ],
    "time_cap_bars": 80
  }
}
```
CANDIDATE fields (what driver varies): `stop_ticks`, `leg_targets`, `trail_steps`, `time_cap_bars`
FIXED fields (driver never changes): `version`, `instrument`, `touches_csv`, `bar_data`, `scoring_model_path`, `archetype`, `active_modes`, `routing`

### Trail Step Validation Rules (from config_schema.md)
Driver must enforce these before writing params to avoid EXPERIMENT_ANOMALY on every run:
1. 0–6 steps allowed
2. trigger_ticks strictly monotonically increasing
3. new_stop_ticks < trigger_ticks for each step
4. new_stop_ticks non-decreasing across steps
5. new_stop_ticks[0] >= 0

### EXPERIMENT_ANOMALY Write Pattern
```python
# Source: Futures_Pipeline_Functional_Spec.md lines 1691-1703
timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
entry = f"""
## {timestamp} | EXPERIMENT_ANOMALY
- stage: 04-backtest
- run_id: {run_id}
- detected_by: exit_code
- error_output: {stderr[-20_lines]}
- investigation: # TODO: fill in
- resolution: # TODO: fill in
- resolution_commit: # TODO: fill in
- generated_by: autoresearch driver
"""
with open(audit_log_path, "a", encoding="utf-8") as f:
    f.write(entry)
# Then: subprocess.run(["git", "add", audit_log_path])
# Do NOT call git commit here — autocommit.sh handles it
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Manual param tuning | Automated keep/revert loop (karpathy pattern) | PREREQ-02 review | Overnight runs possible; human reviews results in morning |
| Results in memory | results.tsv as persistent ground truth | Architecture decision | Driver restarts safely; n_prior_tests always accurate |
| Budget in code | BUDGET in program.md | Architecture decision | Budget adjustable without code changes |

---

## Key Constraints and Relationships

### What Already Exists (Phase 4 built and locked)
- `stages/04-backtest/autoresearch/backtest_engine.py` — NEVER MODIFY
- `stages/04-backtest/references/config_schema.json` — reference config for seeding
- `stages/04-backtest/autoresearch/current_best/` — directory exists (empty, .gitkeep)
- `shared/archetypes/zone_touch/zone_touch_simulator.py` — simulator in place
- `shared/scoring_models/scoring_adapter.py` — BinnedScoringAdapter implemented (returns zeros for uncalibrated model)
- `shared/data_loader.py` — load_data(), parse_instruments_md() in place
- `tests/test_backtest_engine.py` — existing test suite

### What Does NOT Exist Yet (Phase 5 must create)
- `stages/04-backtest/autoresearch/driver.py`
- `stages/04-backtest/autoresearch/program.md`
- `stages/04-backtest/autoresearch/current_best/exit_params.json` (seeded baseline)
- `stages/04-backtest/autoresearch/results.tsv` (with header + seeded rows)
- `stages/02-features/autoresearch/evaluate_features.py`
- `shared/archetypes/zone_touch/feature_evaluator.py`

### Budget Interaction with statistical_gates.md
- `statistical_gates.md` sets Stage 04 budget at **500 experiments** per archetype per IS period
- The BUDGET line in program.md is the active limit — driver enforces it from program.md, not from statistical_gates.md directly
- For the first overnight test, functional spec says set MAX_EXPERIMENTS=50 (not 500) to verify loop health
- `n_prior_tests` is counted from results.tsv for the active archetype — seeded rows count toward the budget

### Scoring Model Status
- `BinnedScoringAdapter` currently returns zeros for all touches (placeholder model — no calibration yet)
- This means `score_threshold: 48` in config will block ALL touches from entering simulation (score=0 < 48)
- Result: `n_trades=0`, `pf=0.0` for every experiment with the reference config as-is
- **Driver must use `score_threshold: 0` in the working config** to get non-zero trades during Phase 5
- Alternatively, plan can adjust score_threshold as a CANDIDATE parameter OR seed with threshold=0

---

## Open Questions

1. **propose_next_params implementation depth**
   - What we know: Spec provides the loop structure but not the mutation strategy
   - What's unclear: Does Phase 5 need a full intelligent param proposer, or is random perturbation around current_best sufficient for the 50-experiment overnight test?
   - Recommendation: Implement random perturbation within valid ranges for Phase 5 (simpler, sufficient to verify loop health). A smarter proposer is Pass 4+ work. Document this as a deliberate simplification.

2. **Score threshold interaction with zero-weight model**
   - What we know: BinnedScoringAdapter returns 0.0 for all touches; reference config has score_threshold=48; this produces n_trades=0
   - What's unclear: Should driver.py hardcode score_threshold=0 in the working config, or is this a CANDIDATE field the driver can vary?
   - Recommendation: Config schema marks routing.score_threshold as FIXED, not CANDIDATE. Driver should use threshold=0 in the seeded baseline config to produce trades. Document this in program.md comments.

3. **feature_evaluator.py scope for Phase 5**
   - What we know: AUTO-05 requires the standard interface with evaluate() -> dict
   - What's unclear: Does the evaluator need real predictive spread computation (requiring feature_engine.py) or can it be a stub that returns an empty feature list?
   - Recommendation: Implement evaluate_features.py dispatcher (AUTO-04) and feature_evaluator.py (AUTO-05) with the standard interface and real data loading but without feature_engine.py (that's Phase 6 work). The evaluator should load P1 data and return empty features_evaluated list. This satisfies the interface contract and the "build before Stage 02 driver" requirement.

---

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest (existing, verified working in Phase 4) |
| Config file | none — pytest auto-discovers tests/ directory |
| Quick run command | `python -m pytest tests/test_backtest_engine.py -x -v` |
| Full suite command | `python -m pytest tests/ -v` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| AUTO-01 | driver.py keep/revert loop runs 50 experiments without human intervention | integration | `python -m pytest tests/test_driver.py -x -v` | ❌ Wave 0 |
| AUTO-01 | driver.py stops when n_prior_tests reaches budget (budget=3 → stops at 3) | unit | `python -m pytest tests/test_driver.py::test_budget_enforcement -x -v` | ❌ Wave 0 |
| AUTO-01 | EXPERIMENT_ANOMALY logged to audit_log.md on engine non-zero exit | unit | `python -m pytest tests/test_driver.py::test_experiment_anomaly -x -v` | ❌ Wave 0 |
| AUTO-01 | reverted experiment's config is identical to prior kept state | unit | `python -m pytest tests/test_driver.py::test_revert_restores_prior -x -v` | ❌ Wave 0 |
| AUTO-02 | program.md exists, ≤30 lines, contains METRIC/KEEP RULE/BUDGET | doc | `python -m pytest tests/test_driver.py::test_program_md_format -x -v` | ❌ Wave 0 |
| AUTO-03 | 50-experiment overnight test completes, results.tsv has 50 rows with monotonic IDs | integration (manual) | manual overnight run + row count check | ❌ manual |
| AUTO-04 | evaluate_features.py dispatches to archetype evaluator, writes feature_evaluation.json | unit | `python -m pytest tests/test_evaluate_features.py -x -v` | ❌ Wave 0 |
| AUTO-05 | feature_evaluator.py evaluate() returns dict matching interface contract | unit | `python -m pytest tests/test_feature_evaluator.py -x -v` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `python -m pytest tests/test_driver.py -x -v`
- **Per wave merge:** `python -m pytest tests/ -v`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_driver.py` — covers AUTO-01, AUTO-02 (budget enforcement, keep/revert, anomaly handling)
- [ ] `tests/test_evaluate_features.py` — covers AUTO-04
- [ ] `tests/test_feature_evaluator.py` — covers AUTO-05

*(No new framework install needed — pytest already in use)*

---

## Sources

### Primary (HIGH confidence)
- `C:/Projects/pipeline/Futures_Pipeline_Functional_Spec.md` — lines 1981–2075 (driver loop, program.md template, seeding protocol, done checks), lines 2079–2122 (evaluate_features.py, feature_evaluator.py interface)
- `C:/Projects/pipeline/stages/04-backtest/autoresearch/backtest_engine.py` — CLI interface, result.json schema, engine invocation pattern
- `C:/Projects/pipeline/stages/04-backtest/references/config_schema.json` — exact config structure for seeding
- `C:/Projects/pipeline/stages/04-backtest/references/config_schema.md` — FIXED vs CANDIDATE field documentation
- `C:/Projects/pipeline/_config/statistical_gates.md` — budget limits (500 for Stage 04), n_prior_tests implementation note
- `C:/Projects/pipeline/Futures_Pipeline_Functional_Spec.md` — lines 1691–1703 (EXPERIMENT_ANOMALY template), lines 1646 (run_id contract)

### Secondary (MEDIUM confidence)
- `C:/Projects/pipeline/shared/scoring_models/scoring_adapter.py` — BinnedScoringAdapter returns zero scores (confirmed: all experiments will have n_trades=0 with score_threshold>0)
- `C:/Projects/pipeline/stages/04-backtest/output/result.json` — confirmed result schema from Phase 4 end-to-end pass

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — stdlib only, verified against functional spec pseudocode
- Architecture: HIGH — exact file locations and patterns from functional spec and existing codebase
- Pitfalls: HIGH — trail step rules from config_schema.md, run_id contract from autocommit.sh, seeding from spec
- Open questions: MEDIUM — resolved by recommendation, not yet tested

**Research date:** 2026-03-14
**Valid until:** 2026-06-14 (stable — functional spec is frozen, engine is locked NEVER MODIFY)
