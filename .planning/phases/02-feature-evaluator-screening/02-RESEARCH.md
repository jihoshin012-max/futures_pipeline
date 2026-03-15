# Phase 2: Feature Evaluator + Phase 1 Screening — Research

**Researched:** 2026-03-15
**Domain:** Rotational archetype — bar-level feature evaluation, 41-hypothesis independent screening, cross-bar-type robustness classification
**Confidence:** HIGH

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| ROT-RES-01 | Build rotational_feature_evaluator.py for Stage 02 (bar-level MWU, Gap G-04) | Evaluator skeleton already exists at `shared/archetypes/rotational/feature_evaluator.py` — needs upgrade to support all 3 outcome types (direction, reversal quality, add quality) and per-hypothesis feature computation |
| ROT-RES-02 | Phase 1 research — 41 hypotheses × 3 bar types independent screening (122 meaningful experiments) | All 41 hypotheses defined in spec Section 3; simulator + engine already built; hypothesis config schema defined in rotational_params.json; experiment runner pattern established by run_sweep.py |
| ROT-RES-03 | Phase 1b cross-bar-type robustness classification: Robust / Activity-dependent / Sampling-coupled / Time-dependent / No signal | Classification framework defined in spec Section 3.7; produces ranked advancement list as output |
</phase_requirements>

---

## Summary

Phase 2 builds on a solid simulator foundation (Phase 1 complete) to execute the core research work: evaluate which of the 41 hypotheses actually improve on the StepDist=6.0 optimized baseline. The simulator (`rotational_simulator.py`), engine (`rotational_engine.py`), parameter config (`rotational_params.json`), and feature evaluator skeleton (`feature_evaluator.py`) all exist and are working. The feature engine (`feature_engine.py`) is a stub — the agent edits it during Stage 02 autoresearch to add hypothesis-specific computed features.

The phase has two distinct parts. First, ROT-RES-01 upgrades the feature evaluator to support the three bar-level outcome types (direction, reversal quality, add quality) and wires each hypothesis to its computed features. Second, ROT-RES-02/03 executes the 122 experiments (41 × 3 bar types, H37 excluded from 10-sec) by modifying `rotational_params.json` per hypothesis, running the engine, recording metrics vs baseline, then classifying each hypothesis via the Phase 1b cross-bar-type framework.

The baseline reference is fixed at StepDist=6.0 per bar type: 250-vol PF=0.6714, 250-tick PF=0.7339, 10-sec PF=0.7550 (all negative net PnL — the strategies are losing money; hypotheses must beat these sub-1.0 PF baselines). The experiment budget is part of the 800-total budget; Phase 1 screening uses 122 slots minimum plus parameter sweeps within each hypothesis.

**Primary recommendation:** Build a lightweight hypothesis runner script (`run_hypothesis_screening.py`) modeled on `run_sweep.py` — it accepts a hypothesis config, runs the simulator on all 3 bar types, computes metrics vs baseline, and appends to a results TSV. This avoids hand-running 122 separate engine invocations and provides a clean audit trail for Phase 1b classification.

---

## Standard Stack

### Core (all already installed and working)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| pandas | existing | Bar data loading, cycle DataFrame operations | Established by Phase 1 |
| numpy | existing | MWU spread computation, metric aggregation | Established by Phase 1 |
| scipy.stats | existing | mannwhitneyu — MWU p-value computation | Already used in feature_evaluator.py |
| pytest | existing | Unit tests for new evaluator logic | Established by Phase 1 test suite |

### Supporting (no new installs needed)

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| json | stdlib | Hypothesis config serialization | rotational_params.json I/O |
| importlib | stdlib | Dynamic dispatch for feature modules | Already used in evaluate_features.py |
| argparse | stdlib | CLI for hypothesis runner script | run_sweep.py pattern |
| time | stdlib | Experiment timing/logging | run_sweep.py pattern |

**Installation:** No new packages needed. All dependencies satisfied by Phase 1.

---

## Architecture Patterns

### Recommended Project Structure

```
shared/archetypes/rotational/
├── rotational_simulator.py          # DO NOT MODIFY — Phase 1 frozen
├── rotational_engine.py             # DO NOT MODIFY — Phase 1 frozen
├── feature_evaluator.py             # UPGRADE for ROT-RES-01 (add outcome types 2+3)
├── feature_engine.py                # AGENT EDITS during Stage 02 autoresearch
├── rotational_params.json           # CONFIG TEMPLATE — cloned per hypothesis
├── run_sweep.py                     # Phase 1 sweep — reference pattern
├── hypothesis_configs/              # CREATE: one JSON per hypothesis (H1..H41)
│   ├── H01_atr_scaled.json
│   ├── H03a_sd_tactical.json
│   └── ...
├── run_hypothesis_screening.py      # CREATE: experiment runner (ROT-RES-02)
├── run_phase1b_classification.py    # CREATE: cross-bar-type analysis (ROT-RES-03)
├── screening_results/               # CREATE: output directory
│   ├── phase1_results.tsv           # All 122 experiment results
│   └── phase1b_classification.md    # Ranked advancement list
└── baseline_results/
    └── sweep_P1a.json               # Phase 1 baseline — READ ONLY
```

### Pattern 1: Hypothesis Config Variation (the key pattern for Phase 2)

Each hypothesis maps directly to a config JSON variation. The runner deep-copies `rotational_params.json` and patches the relevant fields.

**What:** Modify `hypothesis.trigger_mechanism`, `hypothesis.trigger_params`, `hypothesis.active_filters`, `hypothesis.filter_params`, `hypothesis.structural_mods`, `hypothesis.structural_params` in a copy of the base config.

**When to use:** Every one of the 122 experiments. Never modify rotational_params.json in place — always deep-copy.

```python
# Source: run_sweep.py pattern (established by Phase 1)
import copy

def run_hypothesis(base_config: dict, hypothesis_patch: dict, bar_data_dict: dict, instrument_info: dict) -> dict:
    cfg = copy.deepcopy(base_config)
    # Apply hypothesis-specific overrides
    for key_path, value in hypothesis_patch.items():
        # e.g. key_path = "hypothesis.trigger_params.multiplier", value = 0.5
        _set_nested(cfg, key_path, value)
    cfg["_instrument"] = instrument_info
    # Run per bar type
    results = {}
    for source_id, bars in bar_data_dict.items():
        source_cfg = dict(cfg)
        source_cfg["bar_data_primary"] = {source_id: cfg["bar_data_primary"][source_id]}
        simulator = RotationalSimulator(config=source_cfg, bar_data=bars)
        result = simulator.run()
        metrics = compute_cycle_metrics(result.cycles, instrument_info["cost_ticks"])
        results[source_id] = metrics
    return results
```

### Pattern 2: Baseline Comparison (metric threshold for "win")

Each hypothesis result is compared against the per-bar-type baseline from `baseline_results/sweep_P1a.json`. A hypothesis "wins" on a bar type if its cycle_pf exceeds the baseline for that bar type.

```python
BASELINES = {
    "bar_data_250vol_rot":  {"cycle_pf": 0.6714, "step_dist": 6.0},
    "bar_data_250tick_rot": {"cycle_pf": 0.7339, "step_dist": 6.0},
    "bar_data_10sec_rot":   {"cycle_pf": 0.7550, "step_dist": 6.0},
}

def beats_baseline(metrics: dict, source_id: str) -> bool:
    return metrics["cycle_pf"] > BASELINES[source_id]["cycle_pf"]
```

### Pattern 3: Phase 1b Cross-Bar-Type Classification

After all 3 bar-type results for a hypothesis are known, apply the classification matrix from spec Section 3.7:

```python
# Source: Spec Section 3.7 — classification framework
def classify_hypothesis(wins: dict[str, bool], hypothesis_id: str) -> str:
    """
    wins: {"bar_data_250vol_rot": bool, "bar_data_250tick_rot": bool, "bar_data_10sec_rot": bool}
    H37 is pre-classified as "N/A" for 10-sec (constant formation rate on fixed cadence).
    """
    vol_wins = wins["bar_data_250vol_rot"]
    tick_wins = wins["bar_data_250tick_rot"]
    sec_wins = wins.get("bar_data_10sec_rot", None)  # None if not run (H37)

    if hypothesis_id == "H37":
        # Only vol + tick evaluated; 10-sec excluded per spec
        if vol_wins and tick_wins:
            return "ROBUST_ACTIVITY"  # Works on both activity-sampled
        elif vol_wins or tick_wins:
            return "SAMPLING_COUPLED"
        return "NO_SIGNAL"

    if vol_wins and tick_wins and sec_wins:
        return "ROBUST"
    elif vol_wins and tick_wins and not sec_wins:
        return "ACTIVITY_DEPENDENT"
    elif (vol_wins ^ tick_wins) and not sec_wins:
        return "SAMPLING_COUPLED"
    elif not vol_wins and not tick_wins and sec_wins:
        return "TIME_DEPENDENT"
    return "NO_SIGNAL"
```

### Hypothesis-to-Config Mapping (all 41 hypotheses)

The following shows the config key changes per hypothesis group:

**Dimension A — Trigger mechanisms (compete head-to-head, sweep params):**
- H1 (ATR-scaled): `trigger_mechanism="atr_scaled"`, sweep `trigger_params.multiplier` ∈ [0.2, 0.3, 0.4, 0.5, 0.75, 1.0]
- H3a/b/c/d (SD band triggers): `trigger_mechanism="sd_band"`, `trigger_params.band_type` ∈ ["stddev1", "stddev2", "composite", "stddev1_refuse_adds_at_stddev2"]
- H8 (SD-scaled step): `trigger_mechanism="sd_scaled"`, sweep `trigger_params.multiplier` ∈ [0.3, 0.5, 0.75, 1.0, 1.5] × `trigger_params.lookback` ∈ [20, 50, 100, 200]
- H9 (VWAP SD bands): `trigger_mechanism="vwap_sd"`, sweep `trigger_params.k` ∈ [1.0, 1.5, 2.0, 2.5], `trigger_params.vwap_reset` ∈ ["session", "rolling"]
- H10 (Z-score): `trigger_mechanism="zscore"`, sweep `trigger_params.threshold` ∈ [1.5, 2.0, 2.5, 3.0], `trigger_params.lookback` ∈ [50, 100, 200]

**Dimension B — Asymmetry modifier:**
- H2: `symmetry="asymmetric"`, sweep `symmetry_params.rev_add_ratio` ∈ [0.5, 0.75, 1.0, 1.5, 2.0]

**Dimension C — Conditional filters (16 hypotheses, each tested independently):**
- `active_filters: ["H4"]` + `filter_params.H4.*` for each filter hypothesis
- H37 must be skipped for 10-sec bar type (`bar_data_10sec_rot`) — auto-classified N/A

**Dimension D — Structural modifications (10 hypotheses):**
- `structural_mods: ["H13"]` + `structural_params.H13.*`, etc.

**Dimension E — Cross-data (2 hypotheses):**
- H18: `symmetry="asymmetric_directional"` (per-direction params)
- H19: Requires reference data loading (CBT features) — `bar_data_reference` populated

**Dimension F — Dynamics (7 hypotheses):**
- `active_filters: ["H27"]` + `filter_params.H27.*`, etc.

### Feature Engine Extension Pattern

The simulator's `FeatureComputer` is currently a no-op pass-through. For computed features (H8, H9, H10, H27-H41, etc.), the `feature_engine.py` computes column-level values that get passed into the simulator. The key insight from the spec is that all computed features must be:

1. Precomputed as static columns before the simulation loop (no per-bar recalculation)
2. Available only up to bar index i (rolling windows, not full-series)
3. Entry-time safe (Pipeline Rule 3)

The FeatureComputer in rotational_simulator.py should be extended to call `feature_engine.compute_features()` as part of `compute_static_features()`:

```python
# Extension pattern for FeatureComputer.compute_static_features()
# Source: spec Section 6.3, rotational_simulator.py existing structure
def compute_static_features(self, bar_df: pd.DataFrame) -> pd.DataFrame:
    """Compute hypothesis-specific features and append as columns."""
    # Import feature_engine dynamically (loaded per experiment)
    if self._config.get("hypothesis", {}).get("trigger_mechanism") != "fixed":
        from feature_engine import compute_features
        # Compute rolling features for all bars at once (vectorized)
        for i in range(len(bar_df)):
            # WRONG — do NOT call compute_features per-bar; instead vectorize:
            pass
    # Correct pattern: compute all features vectorized, append as columns
    bar_df = _append_static_features(bar_df, self._config)
    return bar_df
```

The correct pattern is **vectorized feature computation** for the full bar_df (with lookback windows), NOT calling feature_engine per bar.

### Anti-Patterns to Avoid

- **Per-bar feature computation:** Calling `compute_features(bar_df[:i])` for every bar i is O(N^2). Pre-compute all rolling features on the full bar_df once, then slice by bar index in the simulation loop.
- **Modifying rotational_params.json in place:** Always deep-copy before patching. Concurrent experiments would corrupt each other.
- **Running H37 on 10-sec bars:** The spec explicitly excludes this. Bar formation rate on fixed-cadence series is constant (~6/min). Auto-classify as N/A.
- **Using P1b data for hypothesis experiments:** All Phase 2 experiments run on P1a only. P1b is reserved for replication gate (Phase 4).
- **Touching backtest_engine.py:** CLAUDE.md hard prohibition. The rotational_engine.py is the only engine for this archetype.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| MWU statistical test | Custom rank-sum implementation | `scipy.stats.mannwhitneyu` | Already used in feature_evaluator.py; exact ties handling, two-sided test |
| Rolling SD / ATR / ROC | Loop-based rolling computation | `pd.Series.rolling().std()`, `pd.Series.pct_change()` | Vectorized, handles edge cases, orders of magnitude faster on 70k+ bars |
| VWAP computation | Custom accumulator | `(price * volume).cumsum() / volume.cumsum()` with session reset | Simple vectorized formula; session reset via groupby date |
| Tercile binning | Manual percentile split | `np.percentile` + `pd.cut` | Already used in feature_evaluator.py._compute_mwu_spread |
| Config deep-copy | Shallow copy | `copy.deepcopy(config_template)` | Already used in run_sweep.py — shallow copy mutates shared state |
| Experiment results TSV | Custom file format | Tab-delimited with header row matching results_master.tsv schema | Consistent with pipeline conventions; human-readable |

**Key insight:** The feature evaluator and experiment runner should reuse the exact patterns from `run_sweep.py` and `feature_evaluator.py` — both are proven and working. The new code extends these patterns, it does not replace them.

---

## Common Pitfalls

### Pitfall 1: Baseline Reference Is Sub-1.0 PF

**What goes wrong:** A hypothesis "improves" from PF=0.67 to PF=0.80 and gets promoted, but PF < 1.0 means the strategy is still losing money.

**Why it happens:** The sweep showed all three bar types top out at StepDist=6.0 with PFs still below 1.0 (0.6714 vol, 0.7339 tick, 0.7550 10-sec). The baseline for Phase 1 screening is relative improvement vs this baseline, not absolute profitability.

**How to avoid:** Record both absolute metrics (cycle_pf, total_pnl_ticks) AND delta vs baseline (delta_pf, delta_pnl). Phase 1b classification is based on beating the baseline, but Phase 4/5 assessment gates require PF ≥ 1.5 for PASS.

**Warning signs:** A hypothesis shows delta_pf > 0 but absolute cycle_pf still < 0.7 — meaningful improvement structurally but not yet a viable strategy.

### Pitfall 2: H37 on 10-sec Bars (Constant Formation Rate)

**What goes wrong:** Running H37 (bar formation rate) on 10-sec bars — it's meaningless because time bars form at exactly 6/min during RTH.

**Why it happens:** The experiment runner might iterate all 3 bar types for all 41 hypotheses without the H37 exclusion.

**How to avoid:** Hard-code the H37 exclusion in the runner. For 10-sec source, skip H37 and record classification="N/A_10SEC" in results TSV. Total count: 41 × 3 - 1 = 122 meaningful experiments.

**Warning signs:** H37 results on 10-sec show zero variance in the formation rate feature — the feature is a constant.

### Pitfall 3: Entry-Time Violation in Computed Features

**What goes wrong:** A rolling feature (e.g., 200-bar SD) at bar i accidentally uses data from bars i+1 to i+200 because the feature is computed on the full bar_df and then sliced incorrectly.

**Why it happens:** `pd.DataFrame.rolling(200).std()` computes correctly (backward-looking), but VWAP with session reset or lead-lag features (CBT-5) can accidentally look forward if not carefully implemented.

**How to avoid:** Test entry-time safety by running feature computation on a truncated DataFrame (bar_df[:50] for a 200-bar lookback feature) and verifying the output is NaN for the warmup period, not a valid value. The existing `feature_evaluator.py` has entry-time violation detection built in — use it.

**Warning signs:** Feature values at bar 5 look "too reasonable" for a 200-bar lookback — they should be NaN.

### Pitfall 4: Dimension A Hypotheses vs Dimension C Hypotheses (what changes)

**What goes wrong:** Testing H1 (ATR-scaled trigger) incorrectly by also changing filter params — or testing Dimension C filters with the default StepDist=2.0 trigger instead of the optimized StepDist=6.0.

**Why it happens:** The spec is clear but easy to misread: "each hypothesis tested independently against the fixed-step baseline." The baseline for Dimension C/D/E/F tests is the **optimized baseline** (StepDist=6.0 per bar type), not the C++ default (StepDist=2.0).

**How to avoid:** Use StepDist=6.0 as the base config for all Dimension C/D/E/F experiments. Only Dimension A hypotheses replace the trigger mechanism. Dimension B/C/D/E/F add modifiers ON TOP of either fixed StepDist=6.0 or the best Dimension A winner.

**Warning signs:** Dimension C results look artificially good — likely because the base config was using suboptimal StepDist.

### Pitfall 5: Experiment Count Budget Leak

**What goes wrong:** Hypothesis H8 requires sweeping multiplier × lookback = 5 × 4 = 20 parameter combinations × 3 bar types = 60 experiments for ONE hypothesis. Budget exhausted before completing Phase 1.

**Why it happens:** Each Dimension A hypothesis has a parameter grid, not a single configuration. 41 hypotheses × average 3 param combos × 3 bar types is already ~370 experiments, close to the Phase 1 budget.

**How to avoid:** For Phase 1 screening, use a REDUCED parameter grid — pick the "most likely" parameter per hypothesis for initial screening, then sweep winners only. Track `n_prior_tests` from the start. Stop at 122 meaningful binary (hypothesis on/off) experiments first, then expand winners.

**Warning signs:** TSV row count exceeds 200 before halfway through the hypothesis list.

### Pitfall 6: Phase 1b Needs Consistent Time Window for Cross-Bar-Type Comparison

**What goes wrong:** 250-vol results include overnight bars (no RTH filter), 10-sec results are RTH-filtered — the comparison is apples to oranges.

**Why it happens:** The simulator RTH filter only activates for 10-sec bar types. Vol and tick bars include overnight bars in their P1a data.

**How to avoid:** Per spec Section 2.4: for Phase 1b cross-bar-type comparison, apply RTH filter to all three series. Run two sets of experiments: (1) unfiltered vol/tick for standalone metrics, (2) RTH-filtered vol/tick for Phase 1b comparison metrics. The `_filter_bars` method in `rotational_simulator.py` can be extended with a `force_rth=True` flag.

**Warning signs:** A hypothesis wins on vol but fails on 10-sec — before classifying as Activity-dependent, verify both were running on the same time window.

---

## Code Examples

Verified patterns from existing codebase:

### Feature Evaluator MWU Spread (existing pattern to extend)

```python
# Source: shared/archetypes/rotational/feature_evaluator.py._compute_mwu_spread()
# This exact pattern already exists and works — extend it for outcome types 2+3

edges = np.percentile(clean_p1a, [33.33, 66.67])
bins = pd.cut(vals, bins=[-np.inf, edges[0], edges[1], np.inf], labels=["low", "mid", "high"])
_, mwu_p = mannwhitneyu(p1a_best, p1b_best, alternative="two-sided")
kept = (spread > 0.15) and (mwu_p < 0.10)
```

### Simulator Call Pattern (from run_sweep.py)

```python
# Source: shared/archetypes/rotational/run_sweep.py.run_sweep()
cfg = copy.deepcopy(config_template)
cfg["hypothesis"]["trigger_params"]["step_dist"] = step_dist
cfg["_instrument"] = instrument_info
source_config = dict(cfg)
source_config["bar_data_primary"] = {source_id: cfg["bar_data_primary"][source_id]}
simulator = RotationalSimulator(config=source_config, bar_data=bars, reference_data=None)
sim_result = simulator.run()
metrics = compute_cycle_metrics(sim_result.cycles, cost_ticks)
```

### Baseline Loading Pattern

```python
# Load frozen Phase 1 baselines — READ ONLY, never recompute during Phase 2
import json
with open("shared/archetypes/rotational/baseline_results/sweep_P1a.json") as f:
    sweep = json.load(f)

BASELINES = {
    source_id: sweep["best_per_source"][source_id]
    for source_id in sweep["best_per_source"]
}
# BASELINES["bar_data_250vol_rot"]["cycle_pf"] == 0.6714 (StepDist=6.0)
# BASELINES["bar_data_250tick_rot"]["cycle_pf"] == 0.7339 (StepDist=6.0)
# BASELINES["bar_data_10sec_rot"]["cycle_pf"] == 0.7550 (StepDist=6.0)
```

### Rolling Computed Features (vectorized pattern)

```python
# Source: spec Section 6.3 + 2.3 — vectorized computation, not per-bar
# H1: ATR-scaled step distance
bars["atr_scaled_step"] = config["trigger_params"]["multiplier"] * bars["ATR"]

# H8: Rolling SD of Close
lookback = config["trigger_params"]["lookback"]  # e.g. 50
bars["rolling_sd"] = bars["Last"].rolling(lookback, min_periods=1).std()
bars["sd_scaled_step"] = config["trigger_params"]["multiplier"] * bars["rolling_sd"]

# H27: ATR Rate of Change
n = config["filter_params"].get("H27", {}).get("lookback", 14)
bars["atr_roc"] = bars["ATR"].pct_change(n)  # (ATR[i] - ATR[i-n]) / ATR[i-n]

# H28: Price ROC (momentum)
n = config["filter_params"].get("H28", {}).get("lookback", 10)
bars["price_roc"] = bars["Last"].pct_change(n)

# H35: Imbalance trend (rolling slope of bid/ask imbalance)
bars["imbalance"] = (bars["Ask Volume"] - bars["Bid Volume"]) / (bars["Ask Volume"] + bars["Bid Volume"])
bars["imbalance_slope"] = bars["imbalance"].rolling(20).apply(
    lambda x: np.polyfit(np.arange(len(x)), x, 1)[0], raw=True
)

# H33: PriceSpeed (requires bar duration from timestamps)
bars["bar_duration_sec"] = bars["datetime"].diff().dt.total_seconds().fillna(10.0)
bars["price_speed"] = bars["Last"].diff().abs() / bars["bar_duration_sec"]
```

### Phase 1b Classification Output Format

```python
# Target output: phase1b_classification.md (ranked advancement list)
CLASSIFICATION_SCHEMA = {
    "hypothesis_id": str,          # e.g. "H1"
    "hypothesis_name": str,        # e.g. "ATR-scaled step"
    "dimension": str,              # A/B/C/D/E/F
    "classification": str,         # ROBUST/ACTIVITY_DEPENDENT/SAMPLING_COUPLED/TIME_DEPENDENT/NO_SIGNAL
    "wins_250vol": bool,
    "wins_250tick": bool,
    "wins_10sec": bool | None,     # None for H37
    "best_cycle_pf_250vol": float,
    "best_cycle_pf_250tick": float,
    "best_cycle_pf_10sec": float | None,
    "delta_vs_baseline_vol": float,
    "delta_vs_baseline_tick": float,
    "delta_vs_baseline_10sec": float | None,
    "advancement_decision": str,   # ADVANCE_HIGH/ADVANCE_FLAGGED/DO_NOT_ADVANCE
    "notes": str,                  # Bar-type-specific behavior notes
}
```

---

## State of the Art

### What Exists vs What Needs Building

| Component | Status | Action Required |
|-----------|--------|----------------|
| `rotational_simulator.py` | COMPLETE (Phase 1) | Read-only |
| `rotational_engine.py` | COMPLETE (Phase 1) | Read-only — provides `compute_cycle_metrics` |
| `feature_evaluator.py` | SKELETON — direction outcome only | Upgrade: add reversal_quality, add_quality outcomes |
| `feature_engine.py` | STUB — empty compute_features() | Agent-edited per hypothesis during screening |
| `rotational_params.json` | COMPLETE baseline config | Template for hypothesis variations |
| `run_sweep.py` | COMPLETE — experiment runner pattern | Reference for hypothesis runner |
| `stages/02-features/autoresearch/evaluate_features.py` | COMPLETE dispatcher | Already supports dynamic dispatch per archetype |
| Hypothesis configs (H1..H41) | NONE | Create hypothesis_configs/ directory + 41 JSONs |
| Hypothesis runner script | NONE | Create `run_hypothesis_screening.py` |
| Phase 1b classifier | NONE | Create `run_phase1b_classification.py` |
| Screening results output | NONE | Create `screening_results/` directory |

### Key Architecture Insight: FeatureComputer Extension vs feature_engine.py

The spec defines two ways to get computed features into the simulator:
1. `FeatureComputer.compute_static_features()` — precomputes columns vectorized before the simulation loop
2. `feature_engine.compute_features()` — called by the evaluator per bar (with truncated bar_df)

For **Phase 2 hypothesis screening**, the right pattern is to extend `FeatureComputer.compute_static_features()` to call feature_engine's vectorized computation. This keeps the simulator loop fast (no per-bar feature computation) while letting the autoresearch agent edit only `feature_engine.py`.

For **Stage 02 feature evaluation** (ROT-RES-01), the evaluator's per-bar pattern is fine because it runs before simulation, not inside the simulation loop.

### H37 Exclusion (10-sec bars)

This is explicitly specified and must be handled automatically:
- H37 measures bar formation rate (bars per minute)
- On 10-sec bars: RTH session = 6.5 hours × 6 bars/min = 2340 bars/session, always ~6/min — zero variance
- On vol/tick bars: rate varies 1-15+ bars/min depending on market activity
- Auto-classify H37 on 10-sec as "N/A_10SEC" in results TSV

### H19 Cross-Bar-Type Reference Data

H19 (bar-type divergence signal) is unique: it requires all 3 series running simultaneously with cross-series lookup. This is the only Phase 2 hypothesis that requires `bar_data_reference` to be populated. The `rotational_params.json` `bar_data_reference` field exists and is empty — populate it for H19 experiments only.

---

## Open Questions

1. **Should the hypothesis runner pre-compute all features or call the simulator per experiment?**
   - What we know: The simulator's FeatureComputer is a pass-through; features must be injected as computed columns
   - What's unclear: Whether to extend FeatureComputer or pre-compute as a separate step before each simulator call
   - Recommendation: Extend FeatureComputer to call vectorized feature computation based on hypothesis config. This keeps the simulator self-contained and testable.

2. **What "beats baseline" threshold to use for Phase 1b classification?**
   - What we know: Baseline PFs are 0.6714, 0.7339, 0.7550 for vol/tick/10sec respectively
   - What's unclear: Is any delta_pf > 0 sufficient, or should there be a minimum delta (e.g., > 0.02)?
   - Recommendation: Record exact delta_pf for all results; use delta_pf > 0 for binary win/loss classification; note size of improvement in Phase 1b notes column. Let the human decide the advancement cutoff if results cluster near zero.

3. **How to handle H3 variants (4 sub-variants: H3a, H3b, H3c, H3d)?**
   - What we know: Spec defines 4 independent H3 variants, each tested separately
   - What's unclear: Whether each counts as a separate hypothesis (making it 44 total, not 41) or whether H3 is one experiment with 4 config variants
   - Recommendation: Treat each H3 variant as a sub-experiment within H3's budget. Record as H3a/H3b/H3c/H3d in results TSV. Count as 1 hypothesis in the 41 total for Phase 1b classification (H3 either wins or loses based on best variant).

4. **Do Dimension C filters get tested against StepDist=6.0 or against the best Dimension A winner?**
   - What we know: Spec says "each hypothesis tested independently against baseline" and "the fixed-step baseline"
   - What's unclear: "Fixed-step baseline" could mean StepDist=6.0 (per-bar-type optimized) or StepDist=2.0 (C++ default)
   - Recommendation: Use StepDist=6.0 per bar type (the per-bar-type optimized baseline from sweep_P1a.json). The C++ default (2.0) is strictly worse and would make Dimension C filters look artificially good.

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest (existing, same as Phase 1) |
| Config file | No pytest.ini — pytest auto-discovers tests |
| Quick run command | `pytest shared/archetypes/rotational/test_rotational_simulator.py -x -q` |
| Full suite command | `pytest tests/ shared/archetypes/rotational/ -v` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| ROT-RES-01 | Feature evaluator returns outcome types 1+2+3 for all 3 bar sources | unit | `pytest shared/archetypes/rotational/test_feature_evaluator.py -x` | ❌ Wave 0 — `tests/test_feature_evaluator.py` exists but tests zone_touch; need rotational version |
| ROT-RES-01 | Entry-time safety enforced (no future data in features) | unit | `pytest shared/archetypes/rotational/test_feature_evaluator.py -x -k "entry_time"` | ❌ Wave 0 |
| ROT-RES-01 | MWU spread + p-value computed correctly on synthetic data | unit | `pytest shared/archetypes/rotational/test_feature_evaluator.py -x -k "mwu"` | ❌ Wave 0 |
| ROT-RES-02 | Hypothesis runner produces results for all 3 bar types | integration | `pytest shared/archetypes/rotational/test_hypothesis_screening.py -x` | ❌ Wave 0 |
| ROT-RES-02 | H37 excluded from 10-sec bar type | unit | `pytest shared/archetypes/rotational/test_hypothesis_screening.py -x -k "h37"` | ❌ Wave 0 |
| ROT-RES-02 | Results TSV format matches expected schema | unit | `pytest shared/archetypes/rotational/test_hypothesis_screening.py -x -k "tsv"` | ❌ Wave 0 |
| ROT-RES-03 | Phase 1b classifier applies correct classification per result pattern | unit | `pytest shared/archetypes/rotational/test_phase1b_classification.py -x` | ❌ Wave 0 |
| ROT-RES-03 | H37 classified as N/A_10SEC automatically | unit | included in above | ❌ Wave 0 |

### Sampling Rate

- **Per task commit:** `pytest shared/archetypes/rotational/ -x -q`
- **Per wave merge:** `pytest tests/ shared/archetypes/rotational/ -v`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps

- [ ] `shared/archetypes/rotational/test_feature_evaluator_rotational.py` — covers ROT-RES-01 (evaluator upgrade with outcome types 2+3, entry-time enforcement, MWU correctness)
- [ ] `shared/archetypes/rotational/test_hypothesis_screening.py` — covers ROT-RES-02 (runner produces results per bar type, H37 exclusion, TSV schema)
- [ ] `shared/archetypes/rotational/test_phase1b_classification.py` — covers ROT-RES-03 (correct classification per win pattern, N/A handling)

Note: `tests/test_feature_evaluator.py` exists but covers the zone_touch archetype evaluator. The rotational version needs its own test file to avoid cross-archetype confusion.

---

## Sources

### Primary (HIGH confidence)

- `xtra/Rotational_Archetype_Spec.md` — Sections 2.3, 3.1-3.7, 5 (G-04, G-09), 6.3, 7.1-7.3 — hypothesis definitions, classification framework, metric schema, code paths
- `shared/archetypes/rotational/rotational_simulator.py` — actual simulator implementation, FeatureComputer structure, SimulationResult contract
- `shared/archetypes/rotational/rotational_engine.py` — engine pattern, compute_cycle_metrics(), data loading
- `shared/archetypes/rotational/feature_evaluator.py` — existing evaluator: MWU spread logic, outcome types, sample stride
- `shared/archetypes/rotational/run_sweep.py` — established experiment runner pattern, config deep-copy
- `shared/archetypes/rotational/baseline_results/sweep_P1a.json` — frozen Phase 1 baselines: vol=0.6714, tick=0.7339, 10sec=0.7550 at StepDist=6.0
- `shared/archetypes/rotational/rotational_params.json` — config schema for all hypothesis experiments
- `stages/02-features/autoresearch/evaluate_features.py` — dynamic dispatch pattern, already supports archetype switching

### Secondary (MEDIUM confidence)

- `shared/archetypes/rotational/test_rotational_simulator.py` — test patterns for synthetic data, config construction helpers
- `shared/archetypes/rotational/feature_engine.py` — current stub, establishes the agent-editable interface
- `.planning/STATE.md` — confirms Phase 1 complete, no blockers
- `.planning/REQUIREMENTS.md` — confirms ROT-RES-01/02/03 scope

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all libraries already installed and used in Phase 1
- Architecture: HIGH — simulator/engine/evaluator all exist; patterns established by run_sweep.py
- Hypothesis mapping: HIGH — spec Section 6.3 provides exact code-path mapping for all 41 hypotheses
- Pitfalls: HIGH — derived from reading actual code + spec contradictions that Phase 1 decisions resolved
- Computed features: MEDIUM — some features (H19 CBT, H33/H36 speed) require careful timestamp handling not yet tested

**Research date:** 2026-03-15
**Valid until:** 2026-04-15 (stable spec, no external dependencies changing)

**Critical numbers the planner needs:**
- Baseline PFs: vol=0.6714, tick=0.7339, 10sec=0.7550 (all at StepDist=6.0)
- Experiment count: 41 × 3 - 1 (H37 on 10sec) = 122 meaningful experiments
- Budget: Part of 800 total; Phase 1 screening = 122 minimum (param sweeps add more)
- 41 hypotheses by dimension: A=5, B=1, C=16, D=10, E=2, F=7
- H37 excluded from 10-sec — hard rule, not optional
- All Phase 2 experiments run on P1a data only
- Baseline config: StepDist=6.0 (not 2.0) for Dimension C/D/E/F tests
