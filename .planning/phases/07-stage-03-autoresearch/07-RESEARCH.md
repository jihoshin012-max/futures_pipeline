# Phase 7: Stage 03 Autoresearch - Research

**Researched:** 2026-03-14
**Domain:** Hypothesis generation keep/revert loop — P1a/P1b replication enforcement, Bonferroni budget control, Stage 05 feedback wiring
**Confidence:** HIGH

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| AUTO-09 | hypothesis_generator.py written (Rule 4 P1a/P1b replication, Bonferroni gates) | Stage 02 driver is the structural template; P1a/P1b split dates known; replication_gate value is `flag_and_review` in period_config.md; Bonferroni thresholds in statistical_gates.md |
| AUTO-10 | Stage 03 driver.py written (hypothesis keep/revert, replication enforcement, 200 budget) | Stage 04 driver.py and Stage 02 driver.py are direct templates; budget=200 from statistical_gates.md; keep rule is PF improves by > 0.1 per CONTEXT.md |
| AUTO-11 | Stage 03 program.md written (<=30 lines) | Stage 04 program.md and Stage 02 program.md are direct templates; METRIC=pf, KEEP RULE=0.1, BUDGET=200 |
| AUTO-12 | Stage 03 overnight test (12 experiments, replication_pass column, Rule 4 enforced) | backtest_engine.py accepts touches_csv/bar_data — can be run against P1a and P1b data slices; TSV must gain replication_pass column; P1b fail path must revert and mark failed |
| AUTO-13 | Feedback loop wired (Stage 05 feedback_to_hypothesis.md -> Stage 03 prior_results.md) | Stage 05 assess.py exists but does not yet produce feedback_to_hypothesis.md; Stage 03 CONTEXT.md specifies prior_results.md; wiring requires a script that copies/symlinks after Stage 05 run |
</phase_requirements>

---

## Summary

Phase 7 implements the Stage 03 hypothesis autoresearch loop. The core components are: (1) a `hypothesis_generator.py` that runs the backtest engine against full P1 AND then separately against P1a and P1b to enforce Rule 4 internal replication; (2) a `driver.py` that owns the keep/revert loop, 200-experiment budget enforcement, Bonferroni p-value gating, and `replication_pass` column logging; (3) a `program.md` machine-readable steering file; (4) a 12-experiment overnight smoke test verifying the full loop; and (5) feedback wiring that copies `feedback_to_hypothesis.md` from Stage 05 output to Stage 03's `references/prior_results.md` automatically after any Stage 05 run.

The architecture is a direct extension of the Stage 04 driver pattern with one critical addition: after a hypothesis passes the PF keep rule on full P1, the driver must run the backtest engine a second time against P1b data only. If P1b PF falls below an acceptable threshold (or the replication_gate is `hard_block` and P1b fails), the hypothesis is reverted regardless of P1 PF. The `replication_pass` column in results.tsv captures the boolean result of this second check per experiment.

The what-to-vary step differs from Stage 04: in Stage 03, the agent (Claude) edits `hypothesis_config.json` (one file per the CONTEXT.md contract), while the `hypothesis_generator.py` acts as the fixed harness. The driver does NOT propose parameter changes; it runs the harness, reads the result, and applies the keep/revert + replication logic.

**Primary recommendation:** Build the Stage 03 driver as a close adaptation of Stage 04 driver.py. Add the P1b replication check as a post-keep step. The `hypothesis_generator.py` is essentially a thin wrapper that accepts `hypothesis_config.json` and calls `backtest_engine.py` twice — once for full P1, once with the `touches_csv` and `bar_data` fields swapped to P1a-filtered data.

---

## Standard Stack

### Core (all already installed and verified)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| subprocess | stdlib | Run backtest_engine.py as subprocess for P1, P1a, P1b runs | Identical pattern to Stage 04 driver; engine is a fixed harness |
| json | stdlib | Read hypothesis_config.json, result.json; write updated configs | Same pattern throughout all prior drivers |
| shutil | stdlib | Copy hypothesis_config.json to/from current_best/ on keep/revert | Identical to Stage 04 exit_params.json copy pattern |
| hashlib.sha1 | stdlib | Generate run_id from archetype+timestamp+experiment_n | Identical to Stage 04 _generate_run_id() |
| pandas | project standard | Date-filter touches CSV for P1a/P1b data split | Already installed; used in all data loading |
| shared.data_loader | project | load_touches() for P1a/P1b date filtering | Already established; no sys.path mutation needed |
| pathlib.Path | stdlib | All file path construction | Project-wide convention |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| importlib | stdlib | Load hypothesis_generator.py as module for testability | Optional — generator can also be a subprocess target |
| argparse | stdlib | CLI entry point for driver.py and hypothesis_generator.py | Same pattern as all prior drivers |

### Installation

No new dependencies. All required libraries already installed in the project environment.

---

## Architecture Patterns

### Recommended Project Structure

```
stages/03-hypothesis/autoresearch/
├── driver.py                    # NEW: keep/revert loop, replication enforcement, 200 budget
├── hypothesis_generator.py      # NEW: fixed harness — runs engine on P1, P1a, P1b
├── hypothesis_config.json       # NEW: agent edits this per program.md direction
├── result.json                  # GENERATED: full P1 result from hypothesis_generator.py
├── result_p1b.json              # GENERATED: P1b result for replication check
├── program.md                   # NEW: machine-readable agent steering
├── results.tsv                  # NEW: created by driver on first run
└── current_best/
    └── hypothesis_config.json   # NEW: seeded by human with baseline config before run

stages/03-hypothesis/references/
├── frozen_features.json         # EXISTS: from Stage 02 (already present: zone_width)
├── strategy_archetypes.md       # EXISTS: archetype registry
└── prior_results.md             # TARGET of feedback wiring (AUTO-13)

stages/03-hypothesis/output/
└── promoted_hypotheses/         # EXISTS: human-approved only
```

### Pattern 1: hypothesis_generator.py — Thin Harness Over backtest_engine.py

**What:** hypothesis_generator.py accepts hypothesis_config.json and runs backtest_engine.py twice — once for full P1 (to compute the keep metric) and once for P1b only (to check Rule 4 replication). It writes two result files: result.json (full P1) and result_p1b.json.

**Key design decision:** The generator does NOT modify hypothesis_config.json. It reads the config, generates P1b-filtered touch/bar data paths (or writes a temporary P1b-filtered touches CSV), and runs the engine. The driver orchestrates keep/revert.

**P1b data approach — two options:**

Option A (recommended): Write a temporary P1b-filtered touches CSV before each engine call. `pd.read_csv → filter by DateTime >= P1b_start → write to tmp path → pass tmp path to engine`.

Option B: Pass date range flags to engine (not supported — engine has no date filter flag; cannot modify engine).

Use Option A. The engine only requires that `touches_csv` point to a valid CSV file — it does not care whether it is the full P1 or a P1b slice.

**Example:**
```python
# Source: period_config.md P1b = 2025-11-01 to 2025-12-14
# hypothesis_generator.py

import json
import subprocess
import sys
import tempfile
from pathlib import Path
import pandas as pd

_REPO_ROOT = Path(__file__).resolve().parents[3]

P1B_START = pd.Timestamp("2025-11-01")
P1B_END   = pd.Timestamp("2025-12-14 23:59:59")

def run(config_path: str, result_path: str, result_p1b_path: str,
        engine_path: str, repo_root: str) -> None:
    config = json.loads(Path(config_path).read_text())

    # Full P1 run
    subprocess.run(
        [sys.executable, engine_path, "--config", config_path, "--output", result_path],
        cwd=repo_root, check=True
    )

    # P1b-filtered run — write temp CSV
    touches_csv = str(_REPO_ROOT / config["touches_csv"])
    touch_df = pd.read_csv(touches_csv)
    touch_df["DateTime"] = pd.to_datetime(touch_df["DateTime"], format="mixed")
    p1b_df = touch_df[
        (touch_df["DateTime"] >= P1B_START) & (touch_df["DateTime"] <= P1B_END)
    ]
    with tempfile.NamedTemporaryFile(
        suffix="_p1b.csv", delete=False, mode="w", encoding="utf-8"
    ) as f:
        p1b_df.to_csv(f, index=False)
        tmp_p1b_path = f.name

    p1b_config = dict(config)
    p1b_config["touches_csv"] = tmp_p1b_path

    with tempfile.NamedTemporaryFile(
        suffix="_p1b_config.json", delete=False, mode="w", encoding="utf-8"
    ) as f:
        json.dump(p1b_config, f)
        tmp_config_path = f.name

    subprocess.run(
        [sys.executable, engine_path, "--config", tmp_config_path,
         "--output", result_p1b_path],
        cwd=repo_root, check=True
    )
```

**Why two separate engine runs (not one):** The engine does not accept date range arguments. Filtering before passing is the only approach that does not modify the engine (HARD PROHIBITION).

### Pattern 2: Replication Check in driver.py

**What:** After a hypothesis passes the PF keep rule on full P1, the driver reads result_p1b.json and applies the replication gate from period_config.md.

**When to use:** Only for hypotheses that pass the primary keep rule (PF improvement > 0.1, n_trades >= 30). Failed P1 hypotheses are reverted immediately without P1b check.

**Example:**
```python
# In driver.py run_loop(), after computing improved = True:

result_p1b = json.loads(result_p1b_path.read_text())
pf_p1b = float(result_p1b.get("pf", 0.0))
n_trades_p1b = int(result_p1b.get("n_trades", 0))

# Read replication_gate from period_config.md (or config constant)
# Current value: flag_and_review (from period_config.md line 49)
replication_gate = "flag_and_review"  # read dynamically or hard-read from config

REPLICATION_PF_THRESHOLD = 1.0  # P1b PF must be > 1.0 to be considered replicated
replication_pass = (pf_p1b > REPLICATION_PF_THRESHOLD) and (n_trades_p1b >= 10)

if not replication_pass:
    if replication_gate == "hard_block":
        # Revert despite P1 pass — Rule 4 enforced structurally
        verdict = "p1b_replication_fail"
        shutil.copy2(str(current_best_path), str(config_path))
        improved = False
    else:  # flag_and_review
        # Keep but flag for human review
        verdict = "kept_weak_replication"
        # Still copy to current_best (human decides at assessment time)
        shutil.copy2(str(config_path), str(current_best_path))
else:
    verdict = "kept"
    shutil.copy2(str(config_path), str(current_best_path))
```

**Critical:** The `replication_pass` boolean (True/False) MUST be written to results.tsv as a dedicated column. The TSV header requires extension beyond the standard 24 columns, OR the `notes` column carries it. See Column Layout section.

### Pattern 3: Bonferroni Gate Enforcement

**What:** The driver reads n_prior_tests from results.tsv before each experiment and applies the tightened MWU p-value threshold from statistical_gates.md. For Stage 03, the primary verdict metric is PF (not MWU p), but the Bonferroni gate still applies to any statistical tests run during assessment.

**For Stage 03 specifically:** The keep rule in CONTEXT.md is purely PF-based ("PF improves by > 0.1"). The Bonferroni gate is documented in statistical_gates.md as applying to Stage 05's MWU p-value when reading from results_master.tsv. The driver enforces:
1. Budget gate: n_prior_tests >= 200 → stop
2. Budget gate at experiment 201: reject launch

The p-value Bonferroni thresholds are enforced by Stage 05, not by the Stage 03 driver itself. The driver's job is budget enforcement and replication enforcement.

**Example:**
```python
# Budget enforcement — identical to Stage 04/02 pattern
n_prior_tests = _count_tsv_rows(results_tsv_path)
if n_prior_tests >= budget:  # budget=200 from program.md
    print(f"Budget exhausted ({n_prior_tests} >= {budget}). Stopping.")
    break
```

### Pattern 4: TSV Column Layout — Extended for Replication

The standard 24-column TSV header is used across all stages. For Stage 03, the `replication_pass` information must be captured. Two options:

Option A (recommended): Use the `notes` column to carry `replication_pass:True/False|pf_p1b:X.XXX`.
Option B: Add a 25th column `replication_pass` — breaks compatibility with existing header.

Use Option A (notes column) to preserve header compatibility. The planner should confirm this decision.

**TSV row format for Stage 03:**
```
run_id | stage='03-hypothesis' | timestamp | hypothesis_name | archetype | version |
features=<frozen_features> | pf_p1=<full_P1_PF> | pf_p2='' |
trades_p1=<n_trades_P1> | trades_p2='' | mwu_p='' | perm_p='' | pctile='' |
n_prior_tests=<count_before> | verdict=<kept|reverted|p1b_replication_fail|kept_weak_replication> |
sharpe_p1='' | max_dd_ticks=<max_dd> | avg_winner_ticks='' | dd_multiple='' |
win_rate=<win_rate> | regime_breakdown='' | api_cost_usd='' |
notes=<replication_pass:True|pf_p1b:X.XXX|git:hash>
```

However, the SUCCESS CRITERIA (AUTO-12) explicitly requires a `replication_pass` column in results.tsv. This implies Option B (explicit column) is the intended design. The planner must decide — both options are documented here. If Option B is used, the TSV header becomes 25 columns and the existing `_append_tsv_row` pattern is adapted.

### Pattern 5: Stage 05 Feedback Wiring (AUTO-13)

**What:** After a Stage 05 assessment run, `feedback_to_hypothesis.md` must appear in Stage 03's `references/prior_results.md` location automatically (no human intervention).

**Current state of Stage 05:** `assess.py` exists but does NOT produce `feedback_to_hypothesis.md`. The Stage 05 CONTEXT.md lists it as an output but the current assess.py implementation only writes `verdict_report.md`.

**Wiring options:**

Option A (recommended): Extend `assess.py` to produce `feedback_to_hypothesis.md` as a second output, and then have `assess.py` copy/symlink it to `stages/03-hypothesis/references/prior_results.md`.

Option B: A separate `wire_feedback.sh` or `wire_feedback.py` script that is called after `assess.py`. The driver or a post-run hook triggers it.

Option C: Symbolic link at `stages/03-hypothesis/references/prior_results.md` pointing to `stages/05-assessment/output/feedback_to_hypothesis.md` — no copy needed, link is static.

**Recommended approach — Option A + Option C hybrid:** `assess.py` writes `stages/05-assessment/output/feedback_to_hypothesis.md`, and Stage 03's `prior_results.md` is a symlink (or the driver reads the Stage 05 output path directly). On Windows, symlinks require elevated permissions; use a Python copy script instead.

**feedback_to_hypothesis.md content spec** (from Stage 05 CONTEXT.md): The file must summarize assessment findings in a format that helps hypothesis generation avoid repeated failures. Minimum content:
- Verdict: YES/CONDITIONAL/NO
- Metrics that gated or nearly gated the result
- Regime breakdown if available
- What parameter ranges appeared in the best runs

### Anti-Patterns to Avoid

- **Modifying backtest_engine.py to add P1b support:** HARD PROHIBITION. All data filtering must happen in hypothesis_generator.py before invoking the engine.
- **Running P1b against P2 data:** hypothesis_generator.py must filter by P1b dates (2025-11-01 to 2025-12-14), not by any P2 date range. The holdout guard in the engine will not block this because P1b paths still reference P1 CSV files — the date filtering happens at the Python level.
- **Skipping replication check on all experiments:** The replication check is only needed when P1 passes. Applying it unconditionally wastes an engine call for experiments that will revert anyway.
- **Hardcoding P1a/P1b dates:** Read from period_config.md or data_manifest.json at runtime. If not yet generating data_manifest.json in Stage 03, hardcode as constants with a comment pointing to period_config.md as the source of truth — but document that these need updating when P1 rolls forward.
- **Using `check=True` in subprocess for all engine calls:** Engine failures (non-zero exit) should be caught and logged as EXPERIMENT_ANOMALY (same as Stage 04 pattern), not raised as exceptions that abort the loop.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| P1b date filtering | Custom date parsing logic | `pd.read_csv` + `pd.to_datetime` + boolean mask | Already established in feature_evaluator.py; handles format="mixed" |
| Run ID generation | UUID or sequential int | `hashlib.sha1(archetype+timestamp+n)[:7]` | Already established in Stage 04 driver; identical here |
| TSV append | Custom file writer | `_append_tsv_row()` from Stage 04 pattern | Handles missing-header creation, encoding, newline |
| Temporary file creation | Manual path construction | `tempfile.NamedTemporaryFile(delete=False)` | Safe cross-platform temp file with known suffix |
| Budget enforcement | Custom row counter | `_count_tsv_rows()` from Stage 04 pattern | Already established; pre-count before append |
| Replication gate config | Hardcoded string | Read `replication_gate` from period_config.md at startup | Allows future switching between hard_block / flag_and_review without code change |

**Key insight:** The Stage 03 driver is substantially a copy of Stage 04 driver.py with three additions: (1) the `hypothesis_generator.py` subprocess call instead of backtest_engine.py directly, (2) the P1b replication check step, and (3) the `replication_pass` value in the TSV row. Resist the temptation to redesign the loop structure.

---

## Common Pitfalls

### Pitfall 1: hypothesis_config.json vs exit_params.json — Different Schema

**What goes wrong:** Stage 04 uses `exit_params.json` as the agent-editable config. Stage 03 uses `hypothesis_config.json`. These must have different schemas because Stage 03 is controlling what to test (which hypothesis), not what exit parameters to use.

**Why it matters:** hypothesis_config.json is passed to hypothesis_generator.py (the fixed harness), not directly to backtest_engine.py. The generator maps hypothesis_config fields to the backtest_engine.py config format.

**How to handle:** Define what hypothesis_config.json contains. Minimum fields needed:
- `archetype` block (same as exit_params.json)
- `touches_csv` and `bar_data` paths pointing to P1 data
- `scoring_model_path`
- All engine-required fields from exit_params.json (version, instrument, active_modes, routing, M1 block)

**Simplest approach:** hypothesis_config.json IS a valid backtest_engine.py config JSON (identical schema to exit_params.json). The agent changes hypothesis-level parameters (stop_ticks, targets, trail_steps) within it — same fields as Stage 04. The generator wraps it to produce the P1b run. This avoids a translation layer.

**Recommendation:** Make hypothesis_config.json schema-identical to exit_params.json. This reuses the existing config validation in backtest_engine.py and eliminates a new schema definition.

### Pitfall 2: P1b Trade Count Too Low for Reliable Replication Gate

**What goes wrong:** P1b has ~3280 touches total. With score_threshold=0, the engine processes all of them. But with the current BinnedScoringAdapter returning zeros, ALL touches go through (threshold=0 with score=0). n_trades_p1b may be very small or zero with tight routing parameters, making the P1b gate unreliable.

**Why it matters:** period_config.md already acknowledges this with `replication_gate: flag_and_review`. The driver should use a very low minimum trades threshold for P1b (e.g., n_trades_p1b >= 10) to avoid false rejections.

**Warning signs:** All experiments show `replication_pass: False` due to n_trades_p1b = 0 (too-restrictive routing on a small data subset).

### Pitfall 3: Temp File Cleanup on Windows

**What goes wrong:** `tempfile.NamedTemporaryFile(delete=False)` leaves temp files in %TEMP% on Windows. An overnight loop running 12+ experiments creates 24+ temp files (2 per experiment: P1b CSV and P1b config JSON).

**How to avoid:** Clean up temp files explicitly after each experiment:
```python
import os
try:
    # use temp files
finally:
    os.unlink(tmp_p1b_path)
    os.unlink(tmp_config_path)
```

### Pitfall 4: P1b Filter Produces Empty DataFrame

**What goes wrong:** If the `touches_csv` path in hypothesis_config.json points to a file with all dates in P1a (e.g., a test fixture), the P1b filter returns an empty DataFrame. The engine receives an empty CSV and may produce n_trades=0 or error.

**How to avoid:** Check len(p1b_df) > 0 before writing the temp P1b CSV. If empty, skip the P1b run and log replication_pass=False with reason='insufficient_p1b_data'.

### Pitfall 5: replication_gate Value Not Read at Runtime

**What goes wrong:** period_config.md line 49 says `replication_gate: flag_and_review`. If the driver hardcodes this value, future changes to period_config.md (switching to `hard_block` after n_trades_p1b becomes reliable) won't take effect.

**How to avoid:** Read replication_gate from period_config.md at driver startup using a simple regex (same pattern as parse_instruments_md). This is a one-time read, not per-experiment.

### Pitfall 6: Stage 05 assess.py Writes to Wrong Output Path

**What goes wrong:** When wiring feedback (AUTO-13), the script must write to `stages/05-assessment/output/feedback_to_hypothesis.md`, then copy to `stages/03-hypothesis/references/prior_results.md`. If assess.py already exists and is extended, the existing `--output` flag path should not be changed (backward compatibility).

**How to avoid:** Add a `--feedback-output` flag to assess.py for the feedback file path. Do not change the existing `--output` flag for verdict_report.md.

### Pitfall 7: current_best/ Directory Not Seeded Before First Run

**What goes wrong:** Stage 03's current_best/ exists but contains only `.gitkeep`. The driver will fail on startup trying to read `current_best/hypothesis_config.json`.

**How to avoid:** Driver must check existence and print a clear error message (same pattern as Stage 02 driver's check for current_best/feature_engine.py). Human must seed `current_best/hypothesis_config.json` with the Stage 04 current best (`stages/04-backtest/autoresearch/current_best/exit_params.json`) before first run.

---

## Code Examples

### Reading replication_gate from period_config.md

```python
# Source: period_config.md line 49: replication_gate: flag_and_review
import re
from pathlib import Path

def read_replication_gate(repo_root: Path) -> str:
    """Read replication_gate from _config/period_config.md."""
    config_path = repo_root / "_config" / "period_config.md"
    content = config_path.read_text(encoding="utf-8")
    match = re.search(r"^replication_gate:\s*(\S+)", content, re.MULTILINE)
    if match:
        return match.group(1)
    return "flag_and_review"  # safe default per pipeline_rules.md
```

### P1b Date Filter for Touches CSV

```python
# Source: period_config.md — P1b = 2025-11-01 to 2025-12-14
import pandas as pd
import tempfile
import os

P1B_START = pd.Timestamp("2025-11-01")
P1B_END   = pd.Timestamp("2025-12-14 23:59:59")

def write_p1b_filtered_csv(touches_csv_path: str) -> str:
    """Filter touches CSV to P1b date range and write to temp file.

    Returns path to temp CSV file. Caller must delete after use.
    """
    df = pd.read_csv(touches_csv_path)
    df["DateTime"] = pd.to_datetime(df["DateTime"], format="mixed")
    p1b = df[(df["DateTime"] >= P1B_START) & (df["DateTime"] <= P1B_END)]
    if len(p1b) == 0:
        raise ValueError("P1b filter produced empty DataFrame — check touches_csv path and dates")
    with tempfile.NamedTemporaryFile(
        suffix="_p1b_touches.csv", delete=False, mode="w", encoding="utf-8"
    ) as f:
        p1b.to_csv(f, index=False)
        return f.name
```

### Driver Loop — Replication Check After Keep

```python
# In run_loop(), after primary keep/revert decision:

if improved:
    # Run P1b replication check
    result_p1b = json.loads(result_p1b_path.read_text(encoding="utf-8"))
    pf_p1b = float(result_p1b.get("pf", 0.0))
    n_trades_p1b = int(result_p1b.get("n_trades", 0))
    replication_pass = (pf_p1b > 1.0) and (n_trades_p1b >= 10)

    if not replication_pass and replication_gate == "hard_block":
        verdict = "p1b_replication_fail"
        shutil.copy2(str(current_best_path), str(config_path))
        improved = False  # Don't update current_best
    elif not replication_pass:
        verdict = "kept_weak_replication"
        shutil.copy2(str(config_path), str(current_best_path))
    else:
        verdict = "kept"
        shutil.copy2(str(config_path), str(current_best_path))
        current_best_metric = metric_value
        current_best_config = proposed_config
else:
    replication_pass = None  # Not checked for reverted experiments
    pf_p1b = None
    shutil.copy2(str(current_best_path), str(config_path))
```

### program.md Template for Stage 03

```markdown
# Stage 03 Hypothesis Generation — Program
# Max 30 lines (machine-readable fields must stay at top)

## Direction
Edit hypothesis_config.json to propose a new hypothesis variant.
Each experiment: change ONE structural parameter (stop_ticks, leg_targets, trail_steps, or routing).
Read references/frozen_features.json before each experiment — features are locked from Stage 02.
Read references/prior_results.md to avoid repeating failed hypothesis structures.

## Machine-Readable Fields
METRIC: pf
KEEP RULE: 0.1
BUDGET: 200

## Constraints
- Only edit hypothesis_config.json (do not touch hypothesis_generator.py)
- Do not modify features — frozen_features.json is locked from Stage 02
- A hypothesis advancing to P2 must have passed P1b replication (Rule 4)
- Budget: 200 experiments maximum (statistical_gates.md)
```

### feedback_to_hypothesis.md Skeleton (Stage 05 Output)

```markdown
# Feedback to Hypothesis Generator
**Generated:** {timestamp}
**Source:** Stage 05 assessment of {hypothesis_name}
**Verdict:** {verdict}

## Key Metrics
- Profit Factor (full P1): {pf}
- P1b PF (replication): {pf_p1b}
- n_trades: {n_trades}
- Drawdown multiple: {dd_multiple}

## What Worked
{notes on parameter ranges that scored well}

## What to Avoid
{notes on parameter ranges that failed or showed high drawdown}

## Regime Breakdown
{per-regime PF if available}
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Stage 03 is empty (only CONTEXT.md + references) | Phase 7: full autoresearch loop with P1a/P1b replication | Phase 7 (now) | Rule 4 enforcement becomes structural, not convention |
| assess.py only writes verdict_report.md | Phase 7: assess.py extended to write feedback_to_hypothesis.md | Phase 7 (now) | Stage 03 can condition hypothesis generation on prior assessment outcomes |
| P1b replication is documented as a rule | Phase 7: P1b replication enforced by driver code — reverts failing hypotheses | Phase 7 (now) | Rule 4 cannot be bypassed by skipping Stage 05 |
| hypothesis_generator.py does not exist | Phase 7: fixed harness wraps engine for P1 + P1b runs | Phase 7 (now) | Agent edits one file (hypothesis_config.json), harness handles dual-run |

**Deprecated/outdated:**
- Stage 03 references/strategy_archetypes.md currently has no active archetype entry. Before the first overnight run, human must complete the NEW ARCHETYPE INTAKE checklist and add zone_touch as an active archetype. This is a prerequisite, not a Phase 7 deliverable.

---

## Open Questions

1. **replication_pass column: 24 columns or 25?**
   - What we know: AUTO-12 requires "results.tsv contains a replication_pass column". This implies a dedicated column, not embedding in notes.
   - What's unclear: Adding column 25 breaks header compatibility with Stage 02 and Stage 04 TSV files that share the same header definition. The dashboard index.html stub may depend on column count.
   - Recommendation: Add `replication_pass` as column 25 in Stage 03 results.tsv only. Stage 03 driver uses its own TSV header constant (not shared). The planner should confirm this is acceptable given the existing architecture.

2. **What is the baseline hypothesis_config.json?**
   - What we know: Stage 04 has a `current_best/exit_params.json` with optimized parameters (stop_ticks=174, leg_targets=[60,81,249], trail_steps=[...], time_cap_bars=85). Stage 03 should start from this as the seeded baseline.
   - What's unclear: Should Stage 03 start fresh (re-explore from scratch) or continue from Stage 04's current best? The pipeline flow is Stage 04 feeds Stage 03 in the circular research loop.
   - Recommendation: Seed Stage 03's current_best/hypothesis_config.json with a copy of Stage 04's current_best/exit_params.json. The agent can then propose variations around the Stage 04 best as a starting point.

3. **What PF threshold constitutes P1b "pass"?**
   - What we know: statistical_gates.md defines PF >= 1.5 as CONDITIONAL YES. replication_gate is `flag_and_review`.
   - What's unclear: The exact numeric threshold for P1b replication pass is not specified in any config file. A hypothesis that barely passes P1 (PF=1.5) might have P1b PF = 1.1 — is that a pass?
   - Recommendation: Use PF_P1B >= 1.0 as the replication pass threshold (better than break-even) with n_trades_p1b >= 10. This is conservative enough to catch genuine failures without being so strict it rejects everything on a smaller data set. The planner should codify this as a named constant.

4. **Where do P1a dates come from?**
   - What we know: period_config.md says P1a = 2025-09-16 to 2025-10-31, P1b = 2025-11-01 to 2025-12-14 (current computed split, written to data_manifest.json by Stage 01).
   - What's unclear: data_manifest.json does not exist in the repo (Stage 01 was designed to generate it but no data_manifest.json was found). The dates in period_config.md are the source of truth.
   - Recommendation: Read P1b dates directly from period_config.md using regex at driver startup (same approach as read_replication_gate above). Do not depend on data_manifest.json until it exists.

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest (existing, tests/ at repo root) |
| Config file | none — run from repo root |
| Quick run command | `pytest tests/test_stage03_driver.py tests/test_hypothesis_generator.py -x -q` |
| Full suite command | `pytest tests/ -x -q` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| AUTO-09 | hypothesis_generator.py runs engine on full P1 and P1b — returns result.json + result_p1b.json | unit | `pytest tests/test_hypothesis_generator.py::TestRunnerOutputs -x` | Wave 0 |
| AUTO-09 | P1b filter produces correct date range subset of touches | unit | `pytest tests/test_hypothesis_generator.py::TestP1bFilter -x` | Wave 0 |
| AUTO-10 | driver.py enforces 200-experiment budget — stops at 200, refuses experiment 201 | unit | `pytest tests/test_stage03_driver.py::TestBudgetEnforcement -x` | Wave 0 |
| AUTO-10 | driver.py replication fail: hypothesis passing P1 but failing P1b replication → reverted, verdict='p1b_replication_fail' | unit | `pytest tests/test_stage03_driver.py::TestReplicationEnforcement::test_p1b_fail_reverts` | Wave 0 |
| AUTO-10 | driver.py replication pass: hypothesis passing P1 and P1b → kept, replication_pass=True in TSV | unit | `pytest tests/test_stage03_driver.py::TestReplicationEnforcement::test_p1b_pass_keeps` | Wave 0 |
| AUTO-11 | program.md parses correctly (METRIC, KEEP RULE, BUDGET fields) | unit | `pytest tests/test_stage03_driver.py::test_parse_program_md -x` | Wave 0 |
| AUTO-12 | 12-experiment overnight smoke test: results.tsv populated, replication_pass column present, at least one experiment has replication_pass value set | integration | `pytest tests/test_stage03_driver.py::TestOvernightSmoke -x` | Wave 0 |
| AUTO-13 | After assess.py run: feedback_to_hypothesis.md written to stages/05-assessment/output/ | unit | `pytest tests/test_assess_feedback.py::TestFeedbackOutput -x` | Wave 0 |
| AUTO-13 | Feedback file copied to stages/03-hypothesis/references/prior_results.md | unit | `pytest tests/test_assess_feedback.py::TestFeedbackWiring -x` | Wave 0 |

### Sampling Rate

- **Per task commit:** `pytest tests/test_stage03_driver.py tests/test_hypothesis_generator.py -x -q`
- **Per wave merge:** `pytest tests/ -x -q`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps

- [ ] `tests/test_stage03_driver.py` — new file; covers AUTO-10, AUTO-11, AUTO-12 driver tests
- [ ] `tests/test_hypothesis_generator.py` — new file; covers AUTO-09 generator tests
- [ ] `tests/test_assess_feedback.py` — new file; covers AUTO-13 feedback wiring tests
- [ ] `stages/03-hypothesis/autoresearch/current_best/hypothesis_config.json` — must be seeded (copy of Stage 04 current_best/exit_params.json) before driver can run
- [ ] `stages/03-hypothesis/references/frozen_features.json` — ALREADY EXISTS as output of Phase 6 freeze script; must be copied here before first run if not already present

*(Existing `tests/test_driver.py` and `tests/test_stage02_driver.py` require no changes — they test Stage 04 and Stage 02 respectively.)*

---

## Sources

### Primary (HIGH confidence)

- `stages/04-backtest/autoresearch/driver.py` — direct template for Stage 03 driver; verified read; keep/revert loop, budget enforcement, git commit, anomaly handling all reuse verbatim
- `stages/02-features/autoresearch/driver.py` — second template demonstrating Stage 02 adaptations; verified read
- `stages/03-hypothesis/CONTEXT.md` — authoritative spec for Stage 03 agent contract (edit hypothesis_config.json, not generator)
- `_config/statistical_gates.md` — budget=200 for Stage 03; Bonferroni thresholds; iteration budget table
- `_config/period_config.md` — P1b = 2025-11-01 to 2025-12-14; replication_gate=flag_and_review; p1_split_rule=midpoint
- `_config/pipeline_rules.md` — Rule 4 internal replication requirement; Rule 5 instrument constants
- `stages/05-assessment/CONTEXT.md` — lists feedback_to_hypothesis.md as a Stage 05 output; verified; assess.py does not yet produce it
- `stages/05-assessment/assess.py` — current assess.py; verified it does not produce feedback_to_hypothesis.md; needs extension
- `stages/04-backtest/autoresearch/current_best/exit_params.json` — Stage 04 current best (PF-optimized params); seed for Stage 03 current_best/hypothesis_config.json
- `stages/02-features/output/frozen_features.json` — confirmed present with zone_width; Stage 03 reads this from references/

### Secondary (MEDIUM confidence)

- `tests/test_stage02_driver.py` and `tests/test_driver.py` — test patterns to follow for Stage 03 tests; verified structure
- `stages/02-features/freeze_features.py` — importlib pattern for loading Python modules from non-standard paths; will NOT be needed in Stage 03 (no py-file keep/revert)
- `_config/period_config.md` P1b computed dates (informational): P1a = 2025-09-16 to 2025-10-31, P1b = 2025-11-01 to 2025-12-14 — verified these match the empirical touch CSV date ranges from Phase 6 research (P1a: 2952 touches, P1b: 3280 touches after Phase 6 correction)

### Tertiary (LOW confidence — needs validation during planning)

- P1b replication pass threshold (PF > 1.0, n_trades >= 10) — not specified in any config file; recommended value based on statistical_gates.md CONDITIONAL range (PF >= 1.5) and thin P1b data consideration
- replication_pass as column 25 vs notes column — architectural decision not resolved in existing docs; must be confirmed during planning

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all libraries verified installed; no new dependencies
- Driver architecture: HIGH — direct adaptation of Stage 04 with verified templates
- P1b replication mechanism: HIGH — mechanism is clear (filter CSV, run engine); threshold is LOW confidence
- Stage 05 feedback wiring: MEDIUM — mechanism is clear but assess.py extension not yet designed
- TSV column layout (replication_pass placement): LOW — architectural decision pending

**Research date:** 2026-03-14
**Valid until:** 2026-04-14 (stable internal project, no external dependencies changing)
