# Phase 4: Backtest Engine - Research

**Researched:** 2026-03-14
**Domain:** Python backtest engine — deterministic CLI harness, dynamic dispatch, holdout guard, config schema
**Confidence:** HIGH (all findings derived from project spec files, existing source code, and architecture documents already committed to repo)

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| ENGINE-01 | Q1-Q6 answers documented in backtest_engine_qa.md | All six answers already documented in Functional Spec Part 0 Task P0-4 — transcription task only |
| ENGINE-02 | data_loader.py patched (5 hardcoded paths parameterized, existing callers updated) | data_loader.py does NOT exist yet in the repo; must be written fresh from simulator library knowledge in architecture doc |
| ENGINE-03 | backtest_engine.py written (~175-225 lines, dynamic dispatch, holdout guard, per-mode breakdown) | Full call sequence, config schema, and output schema specified in arch doc section "backtest_engine.py Build Spec" |
| ENGINE-04 | config_schema.json written (all fields, trail step validation rules enforced at load) | Complete JSON structure documented in arch doc and functional spec Task 2-04 |
| ENGINE-05 | config_schema.md written (every field documented, FIXED vs CANDIDATE) | Full field table with valid ranges documented in functional spec Task 2-04/2-05 |
| ENGINE-06 | Determinism verified (identical config → identical output, diffed) | Requires no random state; pure function simulators + pandas sort → deterministic by construction |
| ENGINE-07 | Manual end-to-end pass (01 → 04 → 05, verdict_report.md well-formed, net-of-cost Sharpe < 80% gross Sharpe) | Stage 05 CONTEXT.md specifies exact output format and Sharpe formula |
| ENGINE-08 | shared/archetypes/{archetype}/simulation_rules.md written from actual source | Simulator interface contract known; transcription from existing simulator modules (m1_simulator.py, single_simulator.py) |
| ENGINE-09 | Scoring adapter interface validated at engine load time (instantiate + call score() on empty df), not at first experiment | scoring_adapter.py stubs raise NotImplementedError — validation must instantiate + call to surface this immediately |
</phase_requirements>

---

## Summary

Phase 4 builds the single most critical fixed component in the entire pipeline: `backtest_engine.py`. This file is written once and never modified again — it is the Karpathy `prepare.py` analog. The engine wraps existing simulator library functions (which already exist as pure Python functions from prior strategy work) behind a CLI that accepts `--config config.json --output result.json`, enforces the holdout guard structurally at import time, and produces deterministic byte-identical output for any given config.

The full specification for every deliverable in this phase has already been captured in `Futures_Pipeline_Functional_Spec.md` (Part 2) and `Futures_Pipeline_Architecture_ICM.md` (backtest_engine.py Build Spec section). No architectural decisions remain open. The work is implementation of a known spec. Research found that `data_loader.py` and the simulator files do not yet exist on disk (the architecture doc describes their intended interface from prior strategy work), so ENGINE-02 and ENGINE-03 require fresh implementations rather than patching existing files.

**Primary recommendation:** Write backtest_engine.py strictly to the call sequence in the arch doc. Use `importlib.import_module()` for dynamic dispatch. Validate the scoring adapter by instantiating and calling `score()` with an empty DataFrame immediately after import — before any experiment runs.

---

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| pandas | (project pinned) | Touch and bar data loading, DataFrame operations | Already used in hmm_regime_fitter.py — project standard |
| numpy | (project pinned) | Array operations for metrics | Already used in hmm_regime_fitter.py |
| scipy.stats | (project pinned) | Mann-Whitney U test for Stage 05 | Statistical testing requirement from statistical_tests.md |
| json | stdlib | Config load, result write | No external dep needed |
| argparse | stdlib | CLI `--config` / `--output` flags | No external dep needed |
| importlib | stdlib | Dynamic dispatch of simulator modules | `importlib.import_module(config.archetype.simulator_module)` |
| pathlib | stdlib | Path handling | Already used in hmm_regime_fitter.py — project standard |
| dataclasses | stdlib | SimResult, config dataclasses | Already used in strategy_archetypes.md interface contract |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| pytest | (project pinned) | Unit + integration tests | ENGINE-06 determinism verification, ENGINE-09 adapter validation |
| hmmlearn | 0.3.3 pinned | HMM regime labels (read-only in this phase) | Already fitted in Phase 2 — engine reads regime_labels.csv, does not refit |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| importlib.import_module | direct imports | Dynamic dispatch is required — config drives which simulator loads; hardcoding imports violates Option B extensibility contract |
| stdlib json | pydantic for config validation | pydantic adds a dependency; trail step validation rules are simple enough for manual checks in a validate_config() function |

**Installation:** All required libraries are already present (pandas, numpy, scipy, pytest used in prior phases).

---

## Architecture Patterns

### Recommended Project Structure
```
stages/04-backtest/
├── autoresearch/
│   ├── backtest_engine.py      # ENGINE-03: fixed engine, never modified
│   └── current_best/           # autoresearch keeps best exit_params.json here
├── references/
│   ├── backtest_engine_qa.md   # ENGINE-01: Q1-Q6 answers
│   ├── config_schema.json      # ENGINE-04: reference config with all fields
│   └── config_schema.md        # ENGINE-05: field documentation table
└── output/
    └── trade_log.csv           # written by engine on each run

shared/archetypes/zone_touch/
├── exit_templates.md           # already exists from Phase 1
├── simulation_rules.md         # ENGINE-08: transcribed from simulator source
├── {archetype}_simulator.py    # pure function: run(bar_df, touch_row, config, bar_offset) -> SimResult
└── feature_engine.py           # feature computation (used in Phase 5+)

shared/scoring_models/
├── scoring_adapter.py          # already exists; BinnedScoringAdapter.score() needs implementation
├── _template.json              # already exists
└── {archetype}_v1.json         # scoring model weights (frozen from P1 calibration)
```

### Pattern 1: Internal Call Sequence (backtest_engine.py)
**What:** Fixed, sequential pipeline from config load to result write
**When to use:** Every run — this is the only run path
```python
# Source: Futures_Pipeline_Architecture_ICM.md "backtest_engine.py Build Spec"
def main(config_path: str, output_path: str) -> None:
    config = load_and_validate_config(config_path)    # validate trail steps here
    check_holdout_flag(config)                         # abort if P2 paths + flag exists
    touches, bars = load_data(config.touches_csv, config.bar_data)
    adapter = load_scoring_adapter(
        config.scoring_model_path,
        config.archetype.scoring_adapter)
    validate_adapter(adapter)                          # ENGINE-09: instantiate + call score()
    touches["score"] = adapter.score(touches)
    route_waterfall(touches, config.routing)
    simulator = load_simulator(config.archetype.simulator_module)
    results = []
    for _, touch in touches[touches["mode"].isin(config.active_modes)].iterrows():
        results.append(simulator.run(bars, touch, config, bar_offset))
    write_result(output_path, compute_metrics(results, config.active_modes))
```

### Pattern 2: Dynamic Dispatch (simulator loading)
**What:** Load simulator by module name from config — engine never hardcodes archetype logic
**When to use:** Every engine run; all archetype-specific logic stays in the archetype module
```python
# Source: Futures_Pipeline_Architecture_ICM.md "Simulator Interface Contract"
import importlib

def load_simulator(module_name: str):
    """Load simulator module by name. Aborts with clear error if module not found."""
    try:
        mod = importlib.import_module(module_name)
    except ModuleNotFoundError:
        raise SystemExit(
            f"ERROR: Simulator module '{module_name}' not found. "
            f"Check config.archetype.simulator_module and PYTHONPATH."
        )
    if not hasattr(mod, "run"):
        raise SystemExit(
            f"ERROR: Module '{module_name}' has no run() function. "
            f"Simulator must expose: run(bar_df, touch_row, config, bar_offset) -> SimResult"
        )
    return mod
```

### Pattern 3: Holdout Guard (import-time abort)
**What:** Engine aborts if holdout_locked_P2.flag exists and any config path references P2 data
**When to use:** First thing in main() — before any data loads
```python
# Source: Functional Spec Task 2-03, Q5 answer
HOLDOUT_FLAG = Path("stages/04-backtest/p2_holdout/holdout_locked_P2.flag")

def check_holdout_flag(config) -> None:
    """Abort if P2 paths present and holdout flag exists. Cannot be bypassed by config."""
    if not HOLDOUT_FLAG.exists():
        return
    p2_paths = [config.touches_csv, config.bar_data]
    for p in p2_paths:
        if "p2" in p.lower() or "P2" in p:
            raise SystemExit(
                f"HOLDOUT GUARD: holdout_locked_P2.flag is set. "
                f"Engine aborted — P2 path detected in config: {p}\n"
                f"P2 runs exactly once with frozen params after human approval."
            )
```

### Pattern 4: Trail Step Validation (config load time)
**What:** Validate trail_steps on config load — abort with clear error before any simulation
**When to use:** Inside load_and_validate_config()
```python
# Source: Functional Spec Task 2-04/2-05 trail step validation rules
def validate_trail_steps(steps: list[dict]) -> None:
    """Rules from config_schema.md — enforced at load, not mid-simulation."""
    if not (1 <= len(steps) <= 6):
        raise SystemExit(f"trail_steps: must have 1-6 steps, got {len(steps)}")
    triggers = [s["trigger_ticks"] for s in steps]
    new_stops = [s["new_stop_ticks"] for s in steps]
    if triggers != sorted(set(triggers)):
        raise SystemExit("trail_steps: trigger_ticks must be strictly monotonically increasing")
    for i, s in enumerate(steps):
        if s["new_stop_ticks"] >= s["trigger_ticks"]:
            raise SystemExit(f"trail_steps[{i}]: new_stop_ticks must be < trigger_ticks")
    if new_stops != sorted(new_stops):
        raise SystemExit("trail_steps: new_stop_ticks must be monotonically non-decreasing")
    if new_stops[0] < 0:
        raise SystemExit("trail_steps[0]: new_stop_ticks must be >= 0")
```

### Pattern 5: Adapter Validation (ENGINE-09)
**What:** Instantiate adapter and call score() with empty DataFrame immediately after load
**When to use:** After adapter is loaded, before any experiment data passes through it
```python
# Source: ENGINE-09 requirement + scoring_adapter.py interface contract
def validate_adapter(adapter) -> None:
    """Instantiate check — surfaces NotImplementedError stubs before first experiment."""
    import pandas as pd
    try:
        adapter.score(pd.DataFrame())
    except NotImplementedError as e:
        adapter_type = type(adapter).__name__
        raise SystemExit(
            f"ERROR: Scoring adapter '{adapter_type}' is an unimplemented stub. "
            f"Implement score() in shared/scoring_models/scoring_adapter.py before running engine."
        ) from e
```

### Pattern 6: Output Schema (result.json)
**What:** Top-level metrics + per-mode breakdown — per Q6 answer
```python
# Source: Futures_Pipeline_Architecture_ICM.md Output JSON schema
result = {
    "pf": float,
    "n_trades": int,
    "win_rate": float,
    "total_pnl_ticks": float,
    "max_drawdown_ticks": float,
    "per_mode": {
        "{mode_name}": {"pf": float, "n_trades": int, "win_rate": float}
        # Keys are from config.active_modes — not hardcoded in engine
    }
}
```

### Anti-Patterns to Avoid
- **Hardcoding simulator imports:** `from zone_touch_simulator import run` — violates Option B dynamic dispatch; adding a new archetype would require engine edits
- **Hardcoding instrument constants:** Never embed `cost_ticks=3` in engine or config — must be read from `_config/instruments.md` at runtime; source: CLAUDE.md Rule 5
- **Absorbing NotImplementedError silently:** If adapter.score() raises NotImplementedError at run time rather than load time, the error surfaces after the engine has wasted setup time and produces confusing output
- **Recomputing bin_edges in engine:** Engine must never touch `bin_edges` or `weights` in scoring model JSON — BinnedScoringAdapter owns that logic; engine calls `adapter.score()` only
- **be_trigger_ticks as a separate field:** Per Q3 answer and exit_templates.md — BE is `trail_steps[0]` with `new_stop_ticks=0`; no separate field
- **data_loader period awareness:** Engine takes explicit path strings; never reads data_manifest.json or resolves period labels — the driver loop sets the paths

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Statistical significance | Manual permutation code | scipy.stats.mannwhitneyu | Edge cases in ties, continuity corrections — scipy handles these correctly |
| Module loading | `exec()` or custom import machinery | `importlib.import_module()` | stdlib; handles PYTHONPATH, module caching, errors correctly |
| Config validation | Schema library | Simple validate_config() function | Trail step rules are specific enough that a ~20-line validator beats adding jsonschema dependency |
| Path resolution | os.path string concatenation | pathlib.Path | Already established pattern in hmm_regime_fitter.py |

**Key insight:** The simulator functions (m1_simulator, single_simulator) are documented in the architecture doc as already-clean pure functions. The only work is the CLI wrapper and dynamic dispatch plumbing — not reimplementing simulation logic.

---

## Common Pitfalls

### Pitfall 1: data_loader.py Does Not Exist on Disk
**What goes wrong:** ENGINE-02 says "patch data_loader.py (5 hardcoded paths parameterized)" — but the file is not present in the repo. The architecture doc describes its interface from prior work, but it was not migrated.
**Why it happens:** The pipeline was scaffolded fresh; existing strategy code exists outside this repo.
**How to avoid:** ENGINE-02 must be written as a new file conforming to the interface described in the architecture doc. Function signatures: `load_source_data(touches_csv: str, bars_path: str) -> tuple[pd.DataFrame, pd.DataFrame]`. Read column headers from existing data files before writing.
**Warning signs:** FileNotFoundError when searching for data_loader.py — confirmed absent in repo scan.

### Pitfall 2: Simulator Modules Also Do Not Exist on Disk
**What goes wrong:** backtest_engine.py calls `importlib.import_module(config.archetype.simulator_module)` but no simulator .py files exist in shared/archetypes/zone_touch/ yet.
**Why it happens:** Same as Pitfall 1 — prior code is not in this repo.
**How to avoid:** The zone_touch simulator must be written in this phase (ENGINE-08 covers simulation_rules.md; the actual simulator .py is a prerequisite for ENGINE-07 end-to-end pass). Write the simulator as a pure function module conforming to the SimResult interface in strategy_archetypes.md.
**Warning signs:** The current_best/ directory in stage 04 autoresearch is empty — no prior calibration results to diff against.

### Pitfall 3: Cost Ticks Hardcoding Temptation
**What goes wrong:** Config JSON or engine code embeds `cost_ticks: 3` directly instead of reading from `_config/instruments.md`.
**Why it happens:** Cost ticks are needed during simulation for PF calculation; they feel like "config".
**How to avoid:** The engine must read cost_ticks from instruments.md at startup and pass them through config or as a resolved parameter. Source: CLAUDE.md Rule 5, instruments.md "THE RULE". The architecture doc confirms cost_ticks was hardcoded in m1_calibration.py as a known bug to fix.
**Warning signs:** Any literal `3` adjacent to "cost" in engine code.

### Pitfall 4: Scoring Adapter Score() Returns Wrong Type
**What goes wrong:** BinnedScoringAdapter.score() must return `pd.Series[float]` aligned to touch_df index. If it returns a list or numpy array, downstream touch["score"] = adapter.score(touches) will fail index alignment.
**Why it happens:** Protocol only specifies the return type hint — not enforced at runtime.
**How to avoid:** In BinnedScoringAdapter implementation, explicitly construct `pd.Series(scores, index=touch_df.index)` before returning.
**Warning signs:** DataFrame merge errors or shifted score values after scoring step.

### Pitfall 5: Determinism Broken by Floating-Point Accumulation Order
**What goes wrong:** Two runs produce slightly different PF values (e.g., 2.341657 vs 2.341658) due to floating-point sum order varying between runs.
**Why it happens:** Python's sum() over floats can vary if dict/DataFrame iteration order varies.
**How to avoid:** Use `sorted()` before any summation loop; ensure touch DataFrame is sorted by DateTime before processing. Confirmed: pandas DataFrames are deterministic when sort_values() is called explicitly.
**Warning signs:** diff run1.json run2.json shows differences only in trailing decimal digits.

### Pitfall 6: ENGINE-09 Test with Empty DataFrame Hits Column KeyError Before NotImplementedError
**What goes wrong:** validate_adapter() calls `adapter.score(pd.DataFrame())` — an empty DataFrame with no columns. The adapter tries to access touch_df["some_column"] before reaching the NotImplementedError, producing a KeyError instead.
**Why it happens:** Stubs that access columns before raising NotImplementedError.
**How to avoid:** The validate_adapter() function should catch both NotImplementedError and any other exception, and re-raise as a clear SystemExit identifying the adapter. Alternatively, pass a DataFrame with the expected columns but zero rows.
**Warning signs:** KeyError in validate_adapter() instead of clean "adapter is stub" error message.

### Pitfall 7: Holdout Guard Path Check Too Narrow
**What goes wrong:** Holdout guard checks for literal string "p2_holdout" in config paths but misses paths like `P2.csv` or `ZRA_Hist_P2.csv`.
**Why it happens:** Simple substring matching on directory name misses other P2 path conventions.
**How to avoid:** Check for case-insensitive "p2" in the filename portion AND verify the path convention matches what Stage 01 actually writes (ZRA_Hist_P2.csv, NQ_BarData_250vol_P2.txt). Use Path(p).name.lower() for comparison.
**Warning signs:** Guard passes when it should block; P2 data gets evaluated.

### Pitfall 8: quantstats pandas 2.x Compatibility (from STATE.md)
**What goes wrong:** If Stage 05 assessment uses quantstats for tearsheet generation, it may fail with pandas 2.x.
**Why it happens:** Noted as unverified concern in STATE.md blockers section.
**How to avoid:** Stage 05 Sharpe formula is explicitly defined as `mean(trade_pnl_ticks) / std(trade_pnl_ticks) * sqrt(n_trades)` — do NOT use quantstats for Stage 05 output. Implement the formula directly. This sidesteps the compatibility issue entirely.
**Warning signs:** ImportError or AttributeError when running Stage 05 assessment script.

---

## Code Examples

Verified patterns from spec documents:

### SimResult Dataclass (strategy_archetypes.md)
```python
# Source: stages/03-hypothesis/references/strategy_archetypes.md
from dataclasses import dataclass

@dataclass
class SimResult:
    pnl_ticks: float
    win: bool
    exit_reason: str
    bars_held: int
```

### Config JSON Schema (complete structure)
```json
// Source: Futures_Pipeline_Architecture_ICM.md + Functional Spec Task 2-04
{
  "version": "v1",
  "instrument": "NQ",
  "touches_csv": "stages/01-data/data/touches/ZRA_Hist_P1.csv",
  "bar_data":    "stages/01-data/data/bar_data/volume/NQ_BarData_250vol_P1.txt",
  "scoring_model_path": "shared/scoring_models/zone_touch_v1.json",
  "archetype": {
    "name": "zone_touch",
    "simulator_module": "zone_touch_simulator",
    "scoring_adapter": "BinnedScoringAdapter"
  },
  "active_modes": ["M1", "M3", "M4", "M5"],
  "routing": { "score_threshold": 48, "seq_limit": 3 },
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
  },
  "M3": {
    "stop_ticks": 80,
    "leg_targets": [160],
    "trail_steps": [],
    "time_cap_bars": 80
  }
}
```

### Known Frozen Params (from architecture doc)
```
# Source: Futures_Pipeline_Architecture_ICM.md "Current Frozen Values"
M1-A: stop=135, targets=[50,120,240], BE_trigger=30, time_cap=80, trail=4-step
M1-B: stop=90,  targets=[50,120,240], BE_trigger=40, time_cap=120, trail=1-step
M3-A: stop=80,  targets=[160],        time_cap=80,   no trail
M4-A: stop=80,  targets=[30],         BE_trigger=30, time_cap=10
M5-A: stop=120, targets=[80],         BE_trigger=20, time_cap=30
```

### Sharpe Calculation (Stage 05 reporting metric)
```python
# Source: stages/05-assessment/CONTEXT.md "Sharpe implementation note"
# Trade-level only. No annualization. No capital assumption.
import numpy as np

def compute_sharpe(trade_pnl_ticks: list[float]) -> float:
    arr = np.array(trade_pnl_ticks)
    if arr.std() == 0 or len(arr) < 30:
        return float('nan')  # flag as unreliable if n_trades < 30
    return arr.mean() / arr.std() * np.sqrt(len(arr))
```

### Bar Data and Touch Data Format (verified from actual files)
```
# Bar data: stages/01-data/data/bar_data/volume/NQ_BarData_250vol_P1.txt
# Header: Date, Time, Open, High, Low, Last, Volume, NumberOfTrades, BidVolume, AskVolume
# Note: space after comma in header — use df.columns = [c.strip() for c in df.columns]
# Date format: 2025/9/16, Time format: 00:08:35.782 (mixed format — use pd.to_datetime(..., format="mixed"))

# Touch data: stages/01-data/data/touches/ZRA_Hist_P1.csv
# Header: DateTime,BarIndex,TouchType,ApproachDir,TouchPrice,ZoneTop,ZoneBot,...,RxnBar_*,PenBar_*
# 32 columns total. DateTime format: 9/16/2025 2:26
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Hardcoded paths in data_loader.py (m1_calibration.py had `cost_ticks=3` embedded) | Parameterized function args + instruments.md for constants | Phase 4 (this phase) | Engine can switch periods by changing config paths; cost changes propagate from one registry file |
| Separate be_trigger_ticks field in config | trail_steps[0] with new_stop_ticks=0 IS the BE trigger | Phase 1 Q3 answer | No redundant field; one source of truth for breakeven behavior |
| Multiple entry points (run_m1_calibration.py, run_p2_holdout.py) | Single engine with --config flag | Phase 4 | Autoresearch driver calls one fixed command: `python backtest_engine.py --config params.json --output result.json` |

**Deprecated/outdated:**
- `be_trigger_ticks` as a standalone config field: Removed per Q3 answer — do not add it back
- `data_loader.py` module-level path constants: The pattern to replace — all paths come from config JSON

---

## Open Questions

1. **Simulator module location and import path**
   - What we know: strategy_archetypes.md shows `simulator_module: shared/archetypes/{name}/{name}_simulator.py` as the template
   - What's unclear: Whether `importlib.import_module("zone_touch_simulator")` requires the module to be on PYTHONPATH or whether the engine must manipulate sys.path
   - Recommendation: Set PYTHONPATH to include `shared/archetypes/zone_touch/` before calling engine, or use `sys.path.insert(0, "shared/archetypes/zone_touch/")` at engine startup based on config.archetype.name

2. **BinnedScoringAdapter: which features does it score and what scoring model JSON exists**
   - What we know: _template.json schema exists; weights and bin_edges are the structure; 14 features split 7 static / 7 percentile-binned per Q2 answer
   - What's unclear: No zone_touch_v1.json scoring model file exists in shared/scoring_models/ yet — it requires a calibration run or manual creation from prior work
   - Recommendation: Create a placeholder scoring model JSON with all weights=0 for the end-to-end pass (ENGINE-07), document this as "uncalibrated baseline". Scoring model calibration is Phase 5/6 work.

3. **bar_offset computation in simulator**
   - What we know: Simulator interface is `run(bar_df, touch_row, config, bar_offset)` where bar_offset locates the entry bar
   - What's unclear: The exact logic for converting touch DateTime to a bar_offset index in bar_df — depends on how bar_df is indexed
   - Recommendation: Index bar_df by a parsed datetime column; bar_offset = bar_df.index.searchsorted(touch_datetime) and pass that integer index to simulator.

---

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest (already in use — tests/test_scaffold_adapter.py, test_hmm_regime_fitter.py) |
| Config file | none (no pytest.ini or conftest.py yet; tests run from repo root) |
| Quick run command | `python -m pytest tests/test_backtest_engine.py -x -v` |
| Full suite command | `python -m pytest tests/ -v` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| ENGINE-01 | backtest_engine_qa.md contains all 6 Q rows with non-empty answers | smoke | `python -m pytest tests/test_backtest_engine.py::test_qa_doc_complete -x` | No — Wave 0 |
| ENGINE-02 | load_data(touches_csv, bars_path) returns two DataFrames with expected columns | unit | `python -m pytest tests/test_data_loader.py -x` | No — Wave 0 |
| ENGINE-03 | Engine produces result.json with pf, n_trades, per_mode keys when given valid config | integration | `python -m pytest tests/test_backtest_engine.py::test_engine_produces_output -x` | No — Wave 0 |
| ENGINE-04 | config_schema.json parses cleanly; trail step validation raises on invalid step | unit | `python -m pytest tests/test_backtest_engine.py::test_config_validation -x` | No — Wave 0 |
| ENGINE-05 | config_schema.md has a row for every key in config_schema.json | smoke | `python -m pytest tests/test_backtest_engine.py::test_schema_doc_coverage -x` | No — Wave 0 |
| ENGINE-06 | Two runs with same config produce byte-identical result.json | integration | `python -m pytest tests/test_backtest_engine.py::test_determinism -x` | No — Wave 0 |
| ENGINE-07 | verdict_report.md exists, is well-formed, net-of-cost Sharpe < 80% gross Sharpe | manual | Manual review after end-to-end pass | N/A |
| ENGINE-08 | simulation_rules.md exists with all required sections | smoke | `python -m pytest tests/test_backtest_engine.py::test_simulation_rules_doc -x` | No — Wave 0 |
| ENGINE-09 | Engine aborts with clear error naming adapter when score() is a stub | unit | `python -m pytest tests/test_backtest_engine.py::test_adapter_validation_aborts -x` | No — Wave 0 |

### Sampling Rate
- **Per task commit:** `python -m pytest tests/test_backtest_engine.py -x`
- **Per wave merge:** `python -m pytest tests/ -v`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_backtest_engine.py` — ENGINE-01, ENGINE-03, ENGINE-04, ENGINE-05, ENGINE-06, ENGINE-08, ENGINE-09
- [ ] `tests/test_data_loader.py` — ENGINE-02
- [ ] No framework install needed (pytest already present from prior phases)

---

## Sources

### Primary (HIGH confidence)
- `Futures_Pipeline_Functional_Spec.md` Part 2 (Tasks 2-01 through 2-08) — complete deliverable spec for all ENGINE-* requirements
- `Futures_Pipeline_Architecture_ICM.md` "backtest_engine.py Build Spec" and "Clarifying Questions" sections — internal call sequence, config schema, output schema, Q1-Q6 answers
- `stages/04-backtest/CONTEXT.md` — stage-level constraints and call signature
- `stages/03-hypothesis/references/strategy_archetypes.md` — SimResult interface contract
- `shared/scoring_models/scoring_adapter.py` — adapter stubs and ScoringAdapter protocol
- `shared/archetypes/zone_touch/exit_templates.md` — trail step semantics and BE definition
- `_config/instruments.md` — NQ instrument constants (tick size, cost model)
- `_config/statistical_gates.md` — verdict thresholds and Bonferroni gates
- `stages/05-assessment/CONTEXT.md` — Sharpe formula and reporting metric definitions
- `stages/05-assessment/references/statistical_tests.md` — MWU, permutation test, random percentile rank specs
- `stages/01-data/data/touches/ZRA_Hist_P1.csv` — verified touch data column format (first 2 rows)
- `stages/01-data/data/bar_data/volume/NQ_BarData_250vol_P1.txt` — verified bar data column format (first 2 rows)
- `.planning/STATE.md` accumulated decisions — quantstats compatibility concern, scoring adapter NotImplementedError pattern

### Secondary (MEDIUM confidence)
- `Futures_Pipeline_Architecture_ICM.md` "File Inventory" — simulator file descriptions (m1_simulator.py, single_simulator.py, data_loader.py) describe prior-work code not yet in repo; interface contracts are spec, not verified source

### Tertiary (LOW confidence)
- None — all findings backed by committed project files

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all libraries already in use or stdlib
- Architecture: HIGH — call sequence, config schema, output schema all explicitly specified in committed architecture doc
- Pitfalls: HIGH for Pitfalls 1-4 (confirmed from file system scans and committed source); MEDIUM for Pitfalls 5-8 (inferred from spec + pattern)
- ENGINE-02/ENGINE-03 implementation: MEDIUM — interfaces specified but no prior source code present on disk to diff against

**Research date:** 2026-03-14
**Valid until:** 2026-06-14 (stable domain — architecture is frozen by design; only risk is new archetype additions)
