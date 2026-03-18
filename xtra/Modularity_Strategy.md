# Modularity Strategy — Scaling Without Unnecessary Abstraction
> **Created:** 2026-03-15
> **Purpose:** Concrete rules for keeping the pipeline codebase modular as archetypes, instruments, and experiment volume grow — without over-engineering. Companion to `Futures_Pipeline_Scaling_Considerations.md` (which covers *what* scales) — this covers *how* the code stays clean.
> **Principle:** Extract when duplication causes bugs, not when it offends aesthetics. Every layer of indirection makes experiment debugging harder.

---

## 1. The Three Growth Axes

The pipeline scales along exactly three dimensions. Modularity decisions should serve these — nothing else.

| Axis | Current | Growth pattern | Where friction compounds |
|------|---------|----------------|--------------------------|
| Archetypes | 2 (zone_touch, rotational) | New strategy type = new folder + simulator + evaluator + config schema | Onboarding cost per archetype |
| Instruments | 1 (NQ) | Same strategy, different market constants | Already solved — instruments.md registry |
| Experiments per stage | 200-500 budget | Budget grows as confidence builds | Driver consistency across stages |

---

## 2. Current Modularity Strengths (Don't Touch)

These patterns are working. Resist the urge to "improve" them.

| Pattern | Why it works | Temptation to resist |
|---------|-------------|---------------------|
| Archetype plugin folders (`shared/archetypes/{name}/`) | New archetype = new folder, `importlib` dispatch in backtest_engine, zero engine changes | Don't build a formal plugin registry until 5+ archetypes |
| `importlib.import_module(f"shared.archetypes.{name}.{name}_simulator")` | Convention-based discovery, no registration step | Don't replace with a plugin framework — naming convention IS the registry |
| Instrument constants from `_config/instruments.md` + `parse_instruments_md()` | Adding NQ/CL/ES is a one-line registry edit | Don't build an instrument class hierarchy |
| Separate simulators per archetype | zone_touch and rotational have fundamentally different state machines | Don't force into a shared base class — leaky abstraction guaranteed |
| `backtest_engine.py` as frozen core | Reproducibility anchor, dynamic dispatch is the only extension point | NEVER modify — this is a feature, not tech debt |
| Config-driven dispatch via JSON | Archetype name in config routes everything | Don't replace with code-level routing |

---

## 3. Three Surgical Extractions (Do These)

### 3a. Shared autoresearch utilities (not a base class)

**Problem:** Drivers in Stages 02, 03, 04 (~400-600 LOC each) duplicate keep/revert logic, budget enforcement, and results.tsv writing. The risk isn't wasted lines — it's silent drift where one driver gets a bugfix and another doesn't, leading to inconsistent experiment behavior.

**Solution:** Extract exactly three utility functions into `shared/autoresearch_utils.py`:

```
write_result_row(results_path, row_dict)    # Consistent TSV schema + atomic write
keep_or_revert(file_path, backup_path)      # File swap with audit logging
check_budget(results_path, max_iters)       # Budget enforcement + warning at 90%
```

Each driver imports and calls these. Orchestration flow stays inline in each driver — the flows *are* different and will diverge further as archetypes add stage-specific behavior. Utility functions > inheritance hierarchy.

**When:** Before rotational archetype enters Stage 02 autoresearch.

### 3b. Archetype scaffold script (not a framework)

**Problem:** Adding rotational required: new simulator, new feature evaluator, new config schemas, new assessment logic, touching multiple drivers. Archetype #3 will repeat this. `shared/onboarding/` has this intent but isn't end-to-end.

**Solution:** Make `python -m shared.onboarding.new_archetype <name>` actually work:

- Generates `shared/archetypes/{name}/` with: `{name}_simulator.py` (stub implementing run()), `feature_engine.py` (stub with archetype header), `feature_evaluator.py` (stub with compute_outcome + evaluate), `simulation_rules.md` (template), config JSON templates
- All stubs pass lint and import cleanly
- Prints checklist of remaining manual steps (register in data_registry if new data source, add to instruments.md if new instrument)

**Goal:** Archetype #3 onboarding takes hours, not days. A working scaffold is worth more than any base class.

**When:** Before archetype #3 is started.

### 3c. One validation function at the one seam that varies

**Problem:** Data flows between stages via convention (frozen_features.json, trade_log.csv, cycle_log.csv). The zone_touch flow is stable. The rotational flow introduces cycles vs trades, different columns, different config shapes. Schema drift at this seam causes silent downstream failures.

**Solution:** One function, one file:

```python
# shared/stage_contracts.py
COMMON_COLS = {"timestamp", "instrument", "direction", "entry_price", "exit_price", "pnl_ticks"}
ARCHETYPE_COLS = {
    "zone_touch": {"zone_width", "score", "touch_id"},
    "rotational": {"cycle_id", "n_adds", "seed_bar", "peak_adverse"},
}

def validate_backtest_output(df, archetype: str) -> list[str]:
    """Returns list of errors. Empty = valid."""
    required = COMMON_COLS | ARCHETYPE_COLS.get(archetype, set())
    return [c for c in required if c not in df.columns]
```

No JSON schema library. No validation framework. A function that returns a list of missing columns. Called at one point: Stage 04 output before it flows to Stage 05.

**When:** When rotational backtest output first flows to assessment.

---

## 4. The Feature Evaluator Question (Wait for Signal)

`zone_touch/feature_evaluator.py` and `rotational/feature_evaluator.py` use different outcome variables (touch reaction vs bar-level PnL). A protocol interface could standardize this:

```python
class FeatureEvaluator(Protocol):
    def compute_outcome(self, df: pd.DataFrame) -> pd.Series: ...
    def evaluate(self, feature_col: str, outcome_col: str) -> dict: ...
```

Each archetype implements `compute_outcome()` (its unit of analysis). The `evaluate()` method (spread calc, MWU test, binning) stays shared.

**Decision: Wait.** Two instances isn't enough signal to know what's actually shared vs accidentally similar. Build this when archetype #3 arrives and reveals the real pattern. Premature extraction here risks encoding zone_touch assumptions into the shared interface.

---

## 5. Anti-Patterns to Avoid

| Temptation | Why it's wrong here | Do this instead |
|-----------|---------------------|-----------------|
| Base class for autoresearch drivers | Flows are actually different and diverging; inheritance locks in shared assumptions | Shared utility functions (3a) |
| Abstract simulator interface | zone_touch (event-driven signal scoring) and rotational (continuous state machine) have nothing in common beyond "they produce trades" | Let them diverge — plugin folders are the right seam |
| Plugin discovery/registration system | `importlib` + naming convention is already discovery; formal registry adds indirection for zero benefit at 2-5 archetypes | Convention IS the registry |
| Comprehensive inter-stage schema validation | Most seams are stable; validating everything adds maintenance without catching real bugs | Validate only the seam that varies (3c) |
| Config class hierarchy | JSON configs are flat, readable, and diff-friendly; Python classes add a layer between the human and the values | Keep configs as JSON with light runtime validation |
| Shared assessment logic across archetypes | Cycles and trades have fundamentally different statistical properties; shared code would be full of `if archetype == ...` branches | Per-archetype assessment modules, shared statistical primitives (MWU, permutation) as utility functions |

---

## 6. Decision Framework for Future Extractions

Before extracting shared code, ask these three questions in order:

1. **Has the duplication caused a bug or inconsistency?** If no, leave it. Three similar lines > premature abstraction.
2. **Will the shared code be stable, or will archetypes need to diverge?** If divergence is likely, utility functions beat inheritance. If stable, a shared module is fine.
3. **Does the abstraction make debugging harder?** Every layer of indirection between "experiment config" and "experiment result" is a layer that slows root-cause analysis when results don't reproduce. The pipeline optimizes for reproducibility — abstractions must not compromise that.

If all three answers favor extraction, extract. Otherwise, tolerate the duplication.

---

## 7. Priority Sequence

| # | Action | Trigger | Effort |
|---|--------|---------|--------|
| 1 | `shared/autoresearch_utils.py` — 3 utility functions | Before rotational enters autoresearch | Small (1 session) |
| 2 | `shared/stage_contracts.py` — 1 validation function | When rotational output flows to Stage 05 | Tiny |
| 3 | Scaffold script end-to-end | Before archetype #3 starts | Medium (1-2 sessions) |
| 4 | Feature evaluator protocol | When archetype #3 reveals what's shared | Small |
| 5 | Per-archetype assessment modules + shared stat primitives | When rotational assessment diverges from zone_touch | Medium |

---

*This document is expected to be revisited after each new archetype is onboarded. Update Section 4 when archetype #3 arrives.*
