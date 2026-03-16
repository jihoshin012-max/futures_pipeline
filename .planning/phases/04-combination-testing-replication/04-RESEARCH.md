# Phase 4: Combination Testing + Replication — Research

**Researched:** 2026-03-16
**Domain:** Hypothesis combination sweep, parameter tuning, TDS integration, P1b replication gate
**Confidence:** HIGH (all source code verified in-repo; upstream inputs fully inspected)

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| ROT-RES-05 | Phase 2 research — combine winners across dimensions (Dim A winner x H2 on/off x Dim C winners x Dim D winners x H18/H19). Run on all 3 bar types. Cross-bar-type consistency required. | Phase 1b classification JSON is the input; run_hypothesis_screening.py and hypothesis_configs.py provide all config-building infrastructure; sweep harness pattern established in run_sizing_sweep.py and run_tds_calibration.py |
| ROT-RES-06 | Phase 3 research — best combination from ROT-RES-05 + best TDS configuration from Phase 03.1 calibration | best_tds_configs.json contains per-profile per-bar-type TDS configs ready for injection; profile configs in profiles/*.json are the martingale params |
| ROT-RES-07 | P1b replication gate on final candidates — soft gate (flag_and_review), WEAK_REPLICATION surfaces for human review, not a hard block | P1b data split is mid-point ~2025-11-02; rotational_engine.py already handles date filtering via period="P1b"; run_phase1b_classification.py shows P1a/P1b date boundaries work |
</phase_requirements>

---

## Summary

Phase 4 is the combination testing and replication gate phase for the rotational archetype. It has three logical sub-phases: (1) sweep hypothesis parameter spaces across dimensional combinations on P1a to find configs that beat the tuned baselines from Phase 02.1, (2) integrate the winning combination with the calibrated TDS config from Phase 03.1, and (3) run a P1b replication check on final candidates as a soft gate.

**Critical context from upstream phases:** Phase 1b classified ALL 40 hypotheses as NO_SIGNAL — but this is entirely expected and does not mean the hypotheses are useless. The Phase 1 screening ran every hypothesis at default params with the fixed trigger mechanism, which by design cannot respond to computed features. The fixed trigger fires on price distance alone and ignores all feature values entirely. The signal discovery happens when hypotheses are swept over their actual parameter grids: ATR-scaled step for H1, different band types for H3, actual filter thresholds for Dimension C/D/F filters. Phase 4 is where the real parameter search begins.

**Phase 4's relationship to prior phases:** Phase 4 consumes three outputs: (a) phase1b_classification.json — the structural baseline and H19 deferral decision, (b) profiles/*.json — the sizing configurations (step_dist, max_levels, max_total_position) that define which martingale params to combine with, and (c) best_tds_configs.json — TDS disabled for vol/tick, velocity-only L1 for 10sec MAX_PROFIT/MOST_CONSISTENT.

**The combinatorial explosion problem:** Phase 2 combinations multiply significantly. The spec says "Dimension A winner x H2 on/off x Dimension C winners x Dimension D winners x H18/H19." But since Phase 1 used default params and all showed NO_SIGNAL, Phase 4 must first re-run parameter sweeps per hypothesis in isolation before knowing which ones beat the profile baselines. This means Phase 4 has two stages: (A) individual re-sweeps with parameter grids, identify winners per dimension, then (B) combine winners. Without this approach, Phase 4 would be combining hypotheses that have never been validated at any parameter value.

**Primary recommendation:** Structure Phase 4 as three plans: Plan 01 — per-hypothesis parameter sweep to identify dimensional winners on P1a (the real Phase 1 with tuned params); Plan 02 — combine dimensional winners and integrate with TDS (ROT-RES-05 + ROT-RES-06); Plan 03 — P1b replication gate on final candidates (ROT-RES-07).

---

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Python | 3.x (repo standard) | All implementation | All rotational code is Python |
| pandas | repo standard | DataFrame sweep output, TSV I/O | All existing harnesses use pandas |
| numpy | repo standard | Numerical operations | Used throughout codebase |
| pytest | repo standard | TDD for new harnesses | All 60+ existing tests use pytest |

### No New Dependencies
All infrastructure exists. run_hypothesis_screening.py sweeps hypotheses. run_sizing_sweep.py and run_tds_calibration.py provide the sweep loop and metrics patterns. hypothesis_configs.py has all 41 hypotheses defined. No new packages needed.

**Installation:** None — all dependencies already present.

---

## Architecture Patterns

### Recommended Output Structure
```
shared/archetypes/rotational/
├── run_combination_sweep.py      # New: Phase 4 combination harness
├── run_p1b_replication.py        # New: P1b replication gate runner
├── test_combination_sweep.py     # New: TDD tests for harness
├── test_p1b_replication.py       # New: TDD tests for replication
└── combination_results/          # New: output directory
    ├── phase4_param_sweep.tsv    # Plan 01: per-hypothesis param sweep results
    ├── phase4_param_sweep.json   # Plan 01: JSON version
    ├── dimensional_winners.json  # Plan 01: best config per hypothesis per bar_type
    ├── phase4_combinations.tsv   # Plan 02: combination sweep results
    ├── phase4_combinations.json  # Plan 02: JSON version
    ├── phase4_tds_combined.tsv   # Plan 02: best combo + TDS results
    ├── final_candidates.json     # Plan 02: configs advancing to P1b
    ├── p1b_replication.tsv       # Plan 03: P1b replication check results
    ├── p1b_replication.json      # Plan 03: JSON version
    └── phase4_report.md          # Plan 03: human-readable summary
```

### Pattern 1: Per-Hypothesis Parameter Sweep (Plan 01)

**What:** For each hypothesis, iterate over its param_grid from hypothesis_configs.py, run on all 3 bar types against the profile baselines from profiles/*.json, measure improvement over the profile's no-TDS baseline.

**When to use:** Before combination testing — you cannot combine hypotheses unless you know which parameter values make them work.

**Key insight:** hypothesis_configs.py already has param_grid defined for all 41 hypotheses. The Plan 01 harness can iterate: for each hypothesis h, for each param in h["param_grid"], for each bar_type, build experiment config, run RotationalSimulator, measure cycle_pf delta vs profile baseline.

**Pattern:**
```python
# Source: run_hypothesis_screening.py + hypothesis_configs.py (verified in codebase)
for h_id, h_def in HYPOTHESIS_REGISTRY.items():
    for params in h_def["param_grid"]:
        for source_id in _ALL_SOURCES:
            config = build_experiment_config(base_profile_config, h_def, params)
            # Override martingale from profile (not rotational_params.json defaults)
            config = inject_profile_martingale(config, profile_data[source_id])
            sim = RotationalSimulator(config, bars[source_id])
            result = sim.run()
            metrics = compute_extended_metrics(result.cycles, cost_ticks, bars[source_id], max_levels)
            delta_pf = metrics["cycle_pf"] - baseline_pf[source_id]
            # Write row: hypothesis_id, params, source_id, all metrics, delta_pf
```

**Critical difference from Phase 1 screening:** Phase 1 used fixed trigger mechanism and default params (so delta_pf was always 0). Phase 4 Plan 01 must use the actual trigger mechanism and sweep each hypothesis's real parameter grid.

### Pattern 2: Combination Config Builder

**What:** Takes a Dimension A winner config, optional H2 symmetry mod, a list of Dimension C/D/F filter winners, and H18/H19, merges them into a single experiment config.

**When to use:** Plan 02 combination sweep.

**Pattern:**
```python
# Source: build_experiment_config() from hypothesis_configs.py (verified)
def build_combination_config(
    dim_a_config: dict,    # from Plan 01 dimensional_winners.json
    h2_enabled: bool,
    h2_params: dict,
    filter_winners: list[dict],  # Dim C/D/F winners to stack
    h18_enabled: bool,
    h19_enabled: bool,
    profile_data: dict,    # from profiles/*.json
    source_id: str,
) -> dict:
    config = copy.deepcopy(dim_a_config)
    # Inject profile martingale (step_dist, max_levels, max_total_position)
    config = inject_profile_martingale(config, profile_data[source_id])
    if h2_enabled:
        config["hypothesis"]["symmetry"] = "asymmetric"
        config["hypothesis"]["symmetry_params"] = h2_params
    for f in filter_winners:
        # Stack active_filters (Dim C), structural_mods (Dim D)
        # Per hypothesis_configs.py convention
        if f["dimension"] in ("C", "F"):
            config["hypothesis"]["active_filters"].append(f["id"])
            config["hypothesis"]["filter_params"].update(f["best_params"])
        elif f["dimension"] == "D":
            config["hypothesis"]["structural_mods"].append(f["id"])
            config["hypothesis"]["structural_params"].update(f["best_params"])
    return config
```

### Pattern 3: Profile Martingale Injection

**What:** All Phase 4 experiments should use the profile martingale configurations (step_dist, max_levels, max_total_position) from profiles/*.json, NOT the defaults from rotational_params.json. The profile configs represent the best sizing from Phase 02.1.

**Critical:** The profile is selected per bar_type. Each of the 3 bar types has different optimal step_dist/max_levels. Do not apply one bar_type's profile to another.

```python
# Source: profiles/max_profit.json structure (verified — each bar_type has own params)
def inject_profile_martingale(config: dict, bar_type_profile: dict) -> dict:
    """Replace martingale params with the profile's bar-type-specific values."""
    config["hypothesis"]["trigger_params"]["step_dist"] = bar_type_profile["step_dist"]
    config["martingale"]["max_levels"] = bar_type_profile["max_levels"]
    config["martingale"]["max_total_position"] = bar_type_profile["max_total_position"]
    config["martingale"]["max_contract_size"] = 16  # fixed per Phase 02.1
    return config
```

**Profile baseline values to beat (from best_tds_configs.json no_tds_baselines):**

| Profile | bar_type | step_dist | max_levels | max_total_position | cycle_pf |
|---------|----------|-----------|------------|-------------------|---------|
| MAX_PROFIT | 250vol | 7.0 | 1 | 2 | 2.2037 |
| MAX_PROFIT | 250tick | 4.5 | 1 | 1 | 1.8413 |
| MAX_PROFIT | 10sec | 10.0 | 1 | 4 | 1.7218 |
| MOST_CONSISTENT | 250vol | 7.0 | 1 | 2 | 2.2037 |
| MOST_CONSISTENT | 250tick | 4.5 | 1 | 2 | 1.7928 |
| MOST_CONSISTENT | 10sec | 10.0 | 1 | 4 | 1.7218 |
| SAFEST | 250vol | 1.0 | 4 | 16 | 1.0209 |
| SAFEST | 250tick | 5.0 | 1 | 1 | 1.2154 |
| SAFEST | 10sec | 10.0 | 1 | 1 | 1.1021 |

### Pattern 4: TDS Integration Config (Plan 02)

**What:** After best combination identified, inject TDS config from best_tds_configs.json into the combination config.

**Per human-approved Phase 03.1 disposition (CRITICAL):**
- vol/tick bar types: TDS disabled (`"trend_defense": {"enabled": false}`)
- 10sec bar type, MAX_PROFIT / MOST_CONSISTENT profiles: velocity-only L1 (60sec threshold)
- 10sec bar type, SAFEST profile: TDS disabled (no multi-level exposure to defend)

```python
# Source: best_tds_configs.json (verified — human-approved 2026-03-16)
def inject_tds_config(config: dict, best_tds_configs: dict, profile_name: str, source_id: str) -> dict:
    tds_entry = best_tds_configs[profile_name][source_id]
    config["trend_defense"] = tds_entry["trend_defense"]
    return config
```

### Pattern 5: P1b Replication Runner (Plan 03)

**What:** Run the final candidate config on P1b data (frozen, no parameter changes). Compare cycle_pf on P1b vs P1a. The replication gate is a soft gate — WEAK_REPLICATION is flagged for human review, not auto-blocked.

**Gate thresholds (from spec Section 7.3):**
- PASS: P1b cycle_pf >= 1.3 AND P1a cycle_pf >= 1.5
- CONDITIONAL: P1b cycle_pf >= 1.1 (degraded but viable)
- WEAK_REPLICATION: P1b cycle_pf < 1.1 — flag for human review, do NOT block P2

```python
# Source: rotational_engine.py period parameter (verified — filters by P1b date range)
def run_p1b_replication(candidate_config: dict, bars: dict) -> dict:
    """Run candidate on P1b data only. P1b = ~2025-11-02 to 2025-12-14."""
    config = copy.deepcopy(candidate_config)
    config["period"] = "P1b"  # rotational_engine handles date filtering
    for source_id in _ALL_SOURCES:
        sim = RotationalSimulator(config, bars[source_id])
        result = sim.run()
        # Classify: PASS / CONDITIONAL / WEAK_REPLICATION based on P1b cycle_pf
```

**CRITICAL: P1b data is still IS data (not holdout).** The P2 holdout flag check applies only to the P2 data split. P1b is safe to run multiple times — it is the second half of the P1 in-sample window. Only P2 runs are irreversible.

### Anti-Patterns to Avoid

- **Combining hypotheses without individual param sweeps first:** If you skip Plan 01 and go straight to combinations at default params, every hypothesis will still show delta_pf=0 (same as Phase 1). The point of Phase 4 is parameter-tuned combinations.
- **Selecting a single profile for combination testing:** Run all 3 profiles (MAX_PROFIT, SAFEST, MOST_CONSISTENT) per bar_type. A combination that only improves one profile may not generalize.
- **Cross-bar-type consistency not required for advancement:** The spec is explicit: "combinations must show consistent improvement across bar types to advance." A combination that wins on 250vol but fails on 250tick and 10sec is flagged, not promoted.
- **Running against baseline StepDist=6.0 instead of profile configs:** The correct baseline for Phase 4 is the sized-profile configs from Phase 02.1, not the raw Phase 01 sweep optimum.
- **Treating H19 as fully implemented:** H19 (bar-type divergence signal) was deferred in Phase 1b with disposition SKIPPED_REFERENCE_REQUIRED. Phase 4 can now implement H19 since all 3 bar types are loaded simultaneously in the combination runner — but this is a NEW feature implementation, not a re-run of Phase 1.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Hypothesis config generation | Custom dict construction | `build_experiment_config()` from `hypothesis_configs.py` | Already handles all 41 hypotheses, config patching, param grid iteration |
| Bar loading | Custom CSV reader | `load_bars()` from `shared/data_loader.py` | Handles all 3 bar type formats, datetime parsing, RTH filter logic |
| Simulator execution | Direct bar loop | `RotationalSimulator(config, bars).run()` | All TDS integration, RTH filter, date filter, feature dispatch already wired |
| Extended metrics | Custom aggregation | `compute_extended_metrics()` from `rotational_engine.py` | Already computes worst_cycle_dd, tail_ratio, max_level_exposure_pct, calmar_ratio etc. |
| Cycle-level metrics | Custom calculation | `compute_cycle_metrics()` from `rotational_engine.py` | All cycle PF, win_rate, Sharpe etc. |
| Profile loading | Hardcoded params | Read from `profiles/*.json` | Permanent pipeline infrastructure — profile values were human-selected |
| TDS config | Manual construction | Read from `tds_profiles/best_tds_configs.json` | Human-approved calibration, permanent baseline for Phase 04 |
| P1b date filtering | Manual date slicing | Pass `period="P1b"` to config; RotationalSimulator applies filter | Date boundaries in period_config.md, already tested |

---

## Common Pitfalls

### Pitfall 1: Phase 1 NO_SIGNAL Does Not Mean "Don't Test"
**What goes wrong:** Treating the Phase 1b classification of DO_NOT_ADVANCE as meaning "these hypotheses are useless, skip them in Phase 4."
**Why it happens:** Misreading the Phase 1b output. All 40 hypotheses ran at DEFAULT params with a fixed trigger that ignores features. Of course they showed delta_pf=0.
**How to avoid:** Phase 4 Plan 01 re-sweeps every hypothesis over its actual param_grid. The winners that advance to combinations are found NOW, not in Phase 1.
**Warning signs:** If Plan 01 also shows delta_pf=0 for all hypotheses at all param values, THEN something is genuinely broken (feature dispatch not working, hypotheses not wired to simulator).

### Pitfall 2: Wrong Baseline for Comparison
**What goes wrong:** Comparing Phase 4 results against the Phase 01 sweep optimum (StepDist=6.0, best cycle_pf ~sub-1.0 baselines) instead of the Phase 02.1 profile configs.
**Why it happens:** Phase 01 final output was the StepDist sweep. Phase 02.1 then identified sized profiles that are the correct baseline.
**How to avoid:** Load baseline values from `best_tds_configs.json["no_tds_baselines"]` which has exact profile metrics (e.g., MAX_PROFIT 250vol: cycle_pf=2.2037). A "winning" combination in Phase 4 must beat THESE numbers.
**Warning signs:** Delta_pf improvement looks suspiciously easy — you may be comparing against a sub-baseline.

### Pitfall 3: Combination Explosion Without Budget Control
**What goes wrong:** Naively constructing "all Dim A x H2 x all Dim C x all Dim D x H18/H19" produces thousands of runs without a plan for which to prioritize.
**Why it happens:** The spec says "Dim A winner x H2 on/off x Dim C winners x Dim D winners x H18/H19." The word "winners" is key — only hypotheses that beat the baseline in Plan 01 are combined. If Plan 01 produces N_A Dim A winners, N_C Dim C winners, N_D Dim D winners, the combination count is: N_A x 2 (H2) x 2^N_C x 2^N_D x 3 (H18/H19 on/off/both). This can still be large.
**How to avoid:** Set an explicit budget. If N_C + N_D winners > 6 total, use a greedy approach: stack winners one at a time, keep if improvement maintained. Budget: ~500 combination experiments across all bar types is feasible.
**Warning signs:** Combination count > 1000 before considering 3 bar types means Plan 02 will run for hours.

### Pitfall 4: Cross-Bar-Type Consistency Not Verified
**What goes wrong:** Promoting a combination that wins on 250vol but fails on 250tick/10sec.
**Why it happens:** Checking results one bar_type at a time without a cross-bar-type agreement check.
**How to avoid:** For every candidate combination, check whether it beats the respective profile baseline on ALL 3 bar types. Use the same robustness classification framework from Phase 1b (spec Section 3.7). A combination that is "Activity-dependent" (wins on vol+tick but not 10sec) may still advance with a flag.
**Warning signs:** Best combination results only show one source_id in the output.

### Pitfall 5: H19 Requires Simultaneous Multi-Source Load
**What goes wrong:** Trying to implement H19 the same way as other filters — it cannot be computed from a single bar series alone.
**Why it happens:** H19 (bar-type divergence signal) was deferred specifically because Phase 1/2 runs loaded one bar type at a time. Phase 4's combination runner may load all 3 simultaneously.
**How to avoid:** If implementing H19, the runner must load all 3 bar series into the same FeatureComputer call, using as-of timestamp alignment (spec Section 2.4). This is new infrastructure — plan time for it. Do not assume it's a simple filter add.
**Warning signs:** H19 feature value is always 0 or always NaN.

### Pitfall 6: P1b is Not the Holdout
**What goes wrong:** Treating P1b replication the same as P2 holdout — either refusing to run it multiple times (too conservative) or checking holdout_locked_P2.flag before running P1b (wrong check).
**Why it happens:** Conflating the two safeguards.
**How to avoid:** P1b = second half of P1 in-sample window (~2025-11-02 to 2025-12-14). It is safe to run multiple candidate configs against P1b. The P2 holdout flag check in CLAUDE.md applies only to P2 data. P1b runs are just time-series validation within the IS window.
**Warning signs:** Paralysis about running P1b, or running it against the holdout flag.

### Pitfall 7: Profile Mismatch — Bar_Type Profiles Are Different
**What goes wrong:** Using MAX_PROFIT 250vol step_dist=7.0 when running experiments on 250tick bars.
**Why it happens:** Loading the profile and applying it globally instead of per-bar_type.
**How to avoid:** Every experiment config must inject the profile's bar_type-specific params. The profile JSON structure is `profile["bar_types"][source_id]` — always index by source_id before extracting step_dist, max_levels, max_total_position.
**Warning signs:** 250tick experiments produce cycle counts very different from baseline (suggesting wrong step_dist).

### Pitfall 8: TDS Disabled for Vol/Tick — Don't Override
**What goes wrong:** Attempting to apply the 10sec velocity-only TDS config to vol/tick bar types in Plan 02.
**Why it happens:** Forgetting the human-approved Phase 03.1 disposition.
**How to avoid:** Read disposition from best_tds_configs.json before injecting. For vol/tick, `tds_disposition == "disabled"` — inject `{"enabled": false}`. Only 10sec MAX_PROFIT/MOST_CONSISTENT gets `velocity_only_l1`.
**Warning signs:** Vol/tick results differ from baseline unexpectedly after TDS injection.

---

## Code Examples

### Plan 01: Per-Hypothesis Parameter Sweep Loop
```python
# Source: hypothesis_configs.py HYPOTHESIS_REGISTRY (verified) +
#         run_hypothesis_screening.py pattern (verified) +
#         best_tds_configs.json no_tds_baselines (verified)

# Load baselines from Phase 02.1 profiles (no-TDS)
baselines = load_json("tds_profiles/best_tds_configs.json")["no_tds_baselines"]

results = []
for h_id, h_def in HYPOTHESIS_REGISTRY.items():
    if h_def.get("advancement_decision") == "NOT_TESTED" and h_id != "H19":
        continue  # Skip non-H19 NOT_TESTED (none exist)
    for params in h_def["param_grid"]:
        for profile_name, profile_data in profiles.items():
            for source_id in _ALL_SOURCES:
                if h_def.get("exclude_10sec") and source_id == "bar_data_10sec_rot":
                    continue
                # Build config from hypothesis + inject profile martingale
                config = build_experiment_config(base_config, h_def, params)
                config = inject_profile_martingale(config, profile_data["bar_types"][source_id])
                # Run simulation
                sim = RotationalSimulator(config, bars[source_id])
                result = sim.run()
                metrics = compute_extended_metrics(result.cycles, cost_ticks, bars[source_id], max_levels)
                baseline = baselines[profile_name][source_id]
                row = {
                    "hypothesis_id": h_id,
                    "profile": profile_name,
                    "source_id": source_id,
                    **params,
                    "cycle_pf": metrics["cycle_pf"],
                    "delta_pf": metrics["cycle_pf"] - baseline["cycle_pf"],
                    "beats_baseline": metrics["cycle_pf"] > baseline["cycle_pf"],
                    # ... other extended metrics
                }
                results.append(row)
```

### Plan 01: Dimensional Winner Selection
```python
# For each (hypothesis_id, source_id, profile_name): find best params by cycle_pf delta
# Winner requires beats_baseline=True on >= 2 of 3 bar types (robust signal criterion)
def select_dimensional_winners(df: pd.DataFrame, min_bar_types: int = 2) -> dict:
    """
    Returns: {hypothesis_id: {profile_name: {source_id: best_params}}}
    Only includes hypotheses where beats_baseline=True on >= min_bar_types bar types.
    """
    winners = {}
    for h_id in df["hypothesis_id"].unique():
        h_df = df[df["hypothesis_id"] == h_id]
        # Find best params per (profile, source_id)
        best_per_source = h_df[h_df["beats_baseline"]].groupby(
            ["profile", "source_id"]
        ).apply(lambda g: g.loc[g["delta_pf"].idxmax()])
        # Check cross-bar-type wins per profile
        for profile_name in ["MAX_PROFIT", "SAFEST", "MOST_CONSISTENT"]:
            p_df = best_per_source[best_per_source.index.get_level_values("profile") == profile_name]
            if len(p_df) >= min_bar_types:
                if h_id not in winners:
                    winners[h_id] = {}
                winners[h_id][profile_name] = p_df.to_dict("index")
    return winners
```

### Plan 02: TDS Injection for Combination
```python
# Source: best_tds_configs.json schema (verified — human-approved 2026-03-16)
def inject_tds_from_calibration(
    config: dict,
    best_tds_configs: dict,
    profile_name: str,
    source_id: str,
) -> dict:
    """Inject per-profile per-bar-type TDS config from Phase 03.1 calibration."""
    tds_entry = best_tds_configs[profile_name][source_id]
    config = copy.deepcopy(config)
    config["trend_defense"] = copy.deepcopy(tds_entry["trend_defense"])
    return config
```

### Plan 03: P1b Replication Verdict
```python
# Source: spec Section 7.3 replication gate logic (verified in ROADMAP.md)
def classify_replication(p1a_pf: float, p1b_pf: float) -> str:
    """Classify P1b replication result per spec Section 7.3."""
    if p1b_pf >= 1.3 and p1a_pf >= 1.5:
        return "PASS"
    elif p1b_pf >= 1.1:
        return "CONDITIONAL"
    else:
        return "WEAK_REPLICATION"  # Soft gate: flag_and_review, NOT hard block

# Output row: candidate_id, profile, source_id, p1a_cycle_pf, p1b_cycle_pf,
#             replication_verdict, advance_to_p2 (True unless all 3 bar types WEAK_REPLICATION)
```

---

## Key Inputs and Outputs

### Inputs (all exist, paths verified)

| Input | Path | Used By | Verified |
|-------|------|---------|---------|
| Phase 1b classification | `screening_results/phase1b_classification.json` | Plan 01 — confirms H19 deferral | Yes — 41 hypotheses, all NO_SIGNAL at default params |
| Profile configs | `profiles/max_profit.json`, `safest.json`, `most_consistent.json` | All plans — martingale params per bar_type | Yes |
| Profile definitions | `profiles/profile_definitions.json` | Selection criteria reference | Yes |
| Calibrated TDS configs | `tds_profiles/best_tds_configs.json` | Plan 02 — TDS injection | Yes — human-approved 2026-03-16 |
| Hypothesis registry | `hypothesis_configs.py` HYPOTHESIS_REGISTRY | Plan 01 — all param grids | Yes — 41 hypotheses with param_grid |
| Base engine config | `rotational_params.json` | Config skeleton for experiments | Yes |
| Bar data files | `stages/01-data/data/bar_data/...` (from rotational_params.json) | All plans | Yes |
| Instrument constants | `_config/instruments.md` | tick_size, cost_ticks | Yes — never hardcode |

### Outputs (to create)

| Output | Path | Plan | Consumed By |
|--------|------|------|------------|
| Per-hypothesis param sweep TSV | `combination_results/phase4_param_sweep.tsv` | 01 | Plan 02 |
| Dimensional winners JSON | `combination_results/dimensional_winners.json` | 01 | Plan 02 |
| Combination sweep TSV | `combination_results/phase4_combinations.tsv` | 02 | Plan 03 |
| TDS-combined results TSV | `combination_results/phase4_tds_combined.tsv` | 02 | Plan 03 |
| Final candidates JSON | `combination_results/final_candidates.json` | 02 | Plan 03 |
| P1b replication TSV | `combination_results/p1b_replication.tsv` | 03 | Phase 5 |
| Phase 4 report | `combination_results/phase4_report.md` | 03 | Human review |

---

## Phase 4 Execution Strategy (Recommended Plan Count)

### Plan 01: Per-Hypothesis Parameter Sweep
**Goal:** Run each of the 41 hypotheses over their full param_grid against the 3 profile baselines, all 3 bar types, on P1a. Identify which hypotheses beat the baseline at any parameter value. Produce dimensional_winners.json as input to Plan 02.

**Experiment count estimate:**
- Average param_grid size: ~5 values per hypothesis (verified from hypothesis_configs.py)
- 41 hypotheses x 5 params x 3 profiles x 3 bar types = ~1,845 runs
- With H37 exclusion from 10sec: slightly under 1,800 runs
- At ~0.1-0.5 sec per run: 3-15 minutes wall clock

**Key constraint:** H19 requires multi-source data loading. If implementing H19 in Plan 01, this is new infrastructure and should be flagged as a sub-task. Default: defer H19 to Plan 02 as specified in the Phase 1b disposition.

### Plan 02: Combination Sweep + TDS Integration
**Goal:** Combine dimensional winners from Plan 01. Run cross-bar-type analysis on combinations. Inject calibrated TDS configs per profile per bar_type. Identify final candidates.

**Experiment count estimate (depends on Plan 01 results):**
- If 5-10 dimensional winners found: ~200-800 combination runs (manageable)
- If > 15 winners: use greedy stacking to bound to ~500 runs
- TDS injection adds 3 bar_types x 3 profiles x N candidates = small additional runs

**Human checkpoint:** Plan 02 should include a human-verify task reviewing combination results before proceeding to P1b replication.

### Plan 03: P1b Replication Gate
**Goal:** Run final candidates against P1b data. Classify PASS/CONDITIONAL/WEAK_REPLICATION. Soft gate — WEAK_REPLICATION triggers human review, not hard block. Write phase4_report.md. Human approves advancement to Phase 5.

**Experiment count:** Low — only the top final candidates (3-9 configs), 3 bar types each = 9-27 P1b runs.

---

## Special Cases

### H19 in Phase 4
H19 (bar-type divergence signal) was deferred because Phase 1 ran bar types independently. In Phase 4, the combination runner loads all 3 bar types simultaneously to measure cross-bar-type consistency. H19 can now be tested.

**What H19 needs:** The FeatureComputer must load all 3 bar series and compute CBT-5 lead-lag detection across them. This requires the as-of timestamp alignment described in spec Section 2.4 — a FeatureComputer.compute_cross_bar_type() call that wasn't needed for single-bar-type runs.

**Decision for planner:** H19 implementation adds real engineering work (CBT feature engineering layer). Recommend: treat H19 as an optional bonus in Plan 02. If time/budget permits after core combination testing is complete, implement H19. Do not let H19 gate the rest of Phase 4.

### SAFEST Profile in Combination Testing
The SAFEST profile (250vol: step_dist=1.0, max_levels=4) has very different characteristics — 8,532 cycles at PF=1.0209 vs MAX_PROFIT's 624 cycles at PF=2.2037. Hypotheses that work on SAFEST may be completely different from those that work on MAX_PROFIT. The plan should note this and not assume the same combination works across all 3 profiles.

### 10sec vs Vol/Tick Combination Asymmetry
TDS only provides value for 10sec MAX_PROFIT/MOST_CONSISTENT. When building the final combined config for Plan 02:
- 250vol + 250tick: winning hypothesis combination only (no TDS benefit)
- 10sec MAX_PROFIT/MOST_CONSISTENT: winning hypothesis combination + velocity L1 TDS
- 10sec SAFEST: winning hypothesis combination only (TDS disabled for single-level structure)

This means there are effectively 2 "final candidate" flavors per profile: with and without TDS. The combination runner should emit both for Plan 03 replication.

---

## State of the Art (Within This Project)

| Old State | Current State | When Changed | Impact on Phase 4 |
|-----------|---------------|--------------|-------------------|
| All hypotheses NO_SIGNAL at default params | Expected — fixed trigger ignores features; real signal discovery is in Phase 4 | Phase 1b (2026-03-15) | Phase 4 must run param sweeps, not just re-run Phase 1 |
| TDS at spec defaults (untested) | TDS calibrated: disabled for vol/tick; velocity-only L1 for 10sec MAX_PROFIT/MOST_CONSISTENT | Phase 03.1 (2026-03-16) | Phase 4 injects calibrated configs, not spec defaults |
| H19 deferred (no multi-source runner) | Still deferred but Phase 4 has multi-source context | Phase 1b (2026-03-15) | H19 can be implemented if budget permits |
| Sizing at C++ defaults (ML=4, MTP=unlimited) | Sized profiles with MaxTotalPosition guard | Phase 02.1 (2026-03-16) | Phase 4 baselines use profile configs, not C++ defaults |

---

## Open Questions

1. **How many dimensional winners will Plan 01 find?**
   - What we know: Phase 1 at default params found 0 winners. Plan 01 sweeps actual param grids.
   - What's unclear: The actual hit rate. If only 2-3 hypotheses beat the baseline at any param value, combinations are trivial. If 15+ win, the combination space is large.
   - Recommendation: Plan 02 should be written to handle both cases. Include a greedy-stack fallback if combination count exceeds 500.

2. **Should the combination sweep use the BEST profile or all 3 profiles?**
   - What we know: The spec says "run on all 3 bar types — combinations must show consistent improvement." It does not explicitly say test all 3 profiles.
   - Recommendation: Test against all 3 profiles (MAX_PROFIT, SAFEST, MOST_CONSISTENT) but select the primary candidate from MAX_PROFIT (highest PF, most stringent). Cross-check that it does not catastrophically harm SAFEST.

3. **Is there a single "best combination" or one per bar_type?**
   - What we know: The spec says combinations "must show consistent improvement across bar types." This implies a single combination that works on all 3. But profiles differ per bar_type.
   - Recommendation: One combination config (active_filters, structural_mods, trigger_mechanism, trigger_params), but with per-bar-type profile martingale params injected. The hypothesis combination layer is separate from the sizing layer.

4. **H19 implementation scope**
   - What we know: H19 needs CBT feature engineering layer (spec Section 2.5 CBT-5 lead-lag detection).
   - What's unclear: Whether FeatureComputer.compute_cross_bar_type() exists yet in feature_engine.py. Inspection shows `compute_cross_bar_type_features()` is referenced in the spec simulator pseudocode but may not be implemented.
   - Recommendation: Check feature_engine.py and rotational_simulator.py for CBT feature support before committing to H19 in Plan 01. Treat as conditional.

---

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest (verified — all 60+ existing tests use pytest) |
| Config file | none required — run from archetype directory |
| Quick run command | `pytest shared/archetypes/rotational/test_combination_sweep.py -x -q` |
| Full suite command | `pytest shared/archetypes/rotational/ -x -q` |

### Phase Requirements to Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| ROT-RES-05 | Per-hypothesis param sweep produces TSV with delta_pf populated | smoke | `python run_combination_sweep.py --plan 1 --dry-run --limit 5` | Wave 0 |
| ROT-RES-05 | Profile martingale injection uses bar-type-specific params | unit | `pytest test_combination_sweep.py::test_inject_profile_martingale -x` | Wave 0 |
| ROT-RES-05 | Cross-bar-type winner selection requires >= 2 bar types | unit | `pytest test_combination_sweep.py::test_select_dimensional_winners -x` | Wave 0 |
| ROT-RES-05 | H37 excluded from 10sec in sweep | unit | `pytest test_combination_sweep.py::test_h37_exclusion -x` | Wave 0 |
| ROT-RES-06 | TDS injection uses calibrated configs (disabled for vol/tick) | unit | `pytest test_combination_sweep.py::test_inject_tds_disabled_for_vol_tick -x` | Wave 0 |
| ROT-RES-06 | TDS injection uses velocity-only L1 for 10sec MAX_PROFIT | unit | `pytest test_combination_sweep.py::test_inject_tds_velocity_l1_10sec -x` | Wave 0 |
| ROT-RES-07 | P1b replication uses P1b period (not P1a) | unit | `pytest test_p1b_replication.py::test_p1b_period_used -x` | Wave 0 |
| ROT-RES-07 | WEAK_REPLICATION verdict does not hard-block | unit | `pytest test_p1b_replication.py::test_weak_replication_is_soft_gate -x` | Wave 0 |
| ROT-RES-07 | Replication verdict classification correct | unit | `pytest test_p1b_replication.py::test_classify_replication -x` | Wave 0 |

### Sampling Rate
- **Per task commit:** `pytest shared/archetypes/rotational/test_combination_sweep.py -x -q`
- **Per wave merge:** `pytest shared/archetypes/rotational/ -x -q`
- **Phase gate:** Full suite green + human approval of Phase 4 report before Phase 5

### Wave 0 Gaps
- [ ] `shared/archetypes/rotational/test_combination_sweep.py` — unit + smoke tests for Plan 01/02 harness
- [ ] `shared/archetypes/rotational/test_p1b_replication.py` — unit tests for Plan 03 replication runner
- [ ] `shared/archetypes/rotational/combination_results/` — output directory (create at harness init)
- [ ] Verify `feature_engine.py` CBT support before H19 implementation

*(All existing tests in test_hypothesis_configs.py, test_hypothesis_screening.py, test_tds_calibration.py, test_trend_defense.py, test_rotational_simulator.py remain as regression coverage.)*

---

## Sources

### Primary (HIGH confidence)
- `shared/archetypes/rotational/hypothesis_configs.py` — HYPOTHESIS_REGISTRY, param_grid for all 41 hypotheses, build_experiment_config() API
- `shared/archetypes/rotational/screening_results/phase1b_classification.json` — Phase 1b results, H19 deferral, all NO_SIGNAL at default params confirmed
- `shared/archetypes/rotational/tds_profiles/best_tds_configs.json` — Human-approved TDS calibration, no_tds_baselines (exact profile metrics), disposition per bar_type
- `shared/archetypes/rotational/profiles/max_profit.json`, `safest.json`, `most_consistent.json` — Per-bar-type martingale configs
- `shared/archetypes/rotational/run_hypothesis_screening.py` — Sweep loop pattern, RTH filtering, TSV output
- `shared/archetypes/rotational/run_sizing_sweep.py` — Harness pattern, compute_extended_metrics call, column schema
- `shared/archetypes/rotational/run_tds_calibration.py` — Multi-experiment harness, selection logic pattern
- `xtra/Rotational_Archetype_Spec.md` Section 3.7 — Phase 2 combination spec, cross-bar-type classification
- `.planning/STATE.md` decisions list — all prior phase decisions (especially Phase 03.1 TDS disposition)
- `.planning/ROADMAP.md` Phase 4 description — confirmed scope

### Secondary (MEDIUM confidence)
- `.planning/phases/02-feature-evaluator-screening/02-03-SUMMARY.md` — H19 deferral decision, NO_SIGNAL confirmation
- `.planning/phases/03.1-tds-profile-calibration/03.1-RESEARCH.md` — TDS calibration patterns, pitfalls

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all code verified in-repo, all harness patterns established, no new dependencies
- Architecture (Plan 01 sweep): HIGH — direct pattern from run_hypothesis_screening.py, param_grid already in hypothesis_configs.py
- Architecture (Plan 02 combinations): HIGH — build_experiment_config + inject_profile_martingale + inject_tds patterns fully specified from verified sources
- Architecture (Plan 03 P1b gate): HIGH — period filtering tested, verdict thresholds from spec
- Experiment count estimates: MEDIUM — depends on Plan 01 winner count, which is unknown
- H19 implementation feasibility: LOW — CBT feature layer existence in feature_engine.py not verified; treat as conditional

**Research date:** 2026-03-16
**Valid until:** Stable — all code is in-repo. Re-research needed only if: (a) profiles are regenerated, (b) best_tds_configs.json is revised, or (c) new hypotheses are added. None expected.
