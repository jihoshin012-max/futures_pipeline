# Phase 6: Stage 02 Autoresearch - Research

**Researched:** 2026-03-14
**Domain:** Feature engineering keep/revert loop — MWU spread, entry-time enforcement, budget control
**Confidence:** HIGH

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Entry-time enforcement:**
- Runtime bar-index guard: feature_evaluator.py truncates bar_df at the touch row's entry bar index before passing to feature_engine.py
- Features only see bars up to and including entry bar close — structural, not convention
- Truncation applied per touch row (every P1 touch, no sampling)
- On violation (NaN/error from truncated data): keep is blocked, results.tsv logs kept=false with reason='entry_time_violation'
- No static AST scan — runtime guard is sufficient and non-brittle

**MWU spread computation:**
- Metric: best-bin vs worst-bin mean trade PnL in ticks
- Binning: terciles (3 bins) — low/mid/high
- Bin edges computed on P1a feature values, applied to P1b touches
- MWU test compares P1a best-bin PnL distribution vs P1b best-bin PnL distribution
- Keep threshold (from feature_rules.md): spread > 0.15 AND MWU p < 0.10
- Outcome variable: trade PnL in ticks (same as backtest engine output)

**Driver keep/revert flow:**
- Agent (Claude) writes/edits feature_engine.py per program.md direction — Karpathy pattern: agent proposes, harness judges
- Driver does NOT propose features itself — it runs the harness, evaluates keep/revert, logs results
- current_best/ directory holds the last kept feature_engine.py copy (same pattern as Stage 04)
- On keep: copy feature_engine.py to current_best/. On revert: restore from current_best/
- Baseline controlled by program.md and current_best/ contents — not hardcoded in driver
- For zone_touch: human seeds current_best/ with zone_width feature before first run
- For new archetypes with no prior features: current_best/ starts empty, compute_features() returns empty dict
- Budget: 300 experiments, enforced from statistical_gates.md — driver refuses experiment 301

**Feature accumulation:**
- Stacking model: each experiment adds or modifies one feature in a growing feature_engine.py
- Spread and MWU p measured on the new/modified feature only — not the combined set
- compute_features(bar_df, touch_row) returns dict keyed by feature name: {'zone_width': 3.5, 'vol_ratio': 1.2, ...}
- Driver tells evaluator which key is new (from program.md or diff against current_best/)
- Prior kept features remain untouched in feature_engine.py across experiments
- results.tsv logs per-feature metrics (one row per experiment, feature_name column)

**Archetype-agnostic design:**
- evaluate_features.py dispatcher remains archetype-agnostic — loads evaluator via importlib with --archetype flag (already implemented in Phase 5)
- feature_evaluator.py's evaluate() interface documented as: returns dict with at minimum {spread, mwu_p} — harness does not care how spread is computed internally
- Same Phase 6 infrastructure (driver, dispatcher, keep/revert loop) runs against any archetype's feature_evaluator.py without modification
- No zone_touch-specific logic in driver or dispatcher

**Human freeze workflow:**
- After reviewing results.tsv and feature_catalog.md, human runs a freeze script
- Freeze reads current_best/feature_engine.py, extracts feature names + bin edges, writes frozen_features.json to stages/02-features/output/
- Human copies frozen_features.json to stages/03-hypothesis/references/ (per Stage 02 CONTEXT.md)
- Not automated — human approval gate required

### Claude's Discretion
- results.tsv column layout and exact format
- program.md template content and steering instructions
- Error handling and anomaly detection patterns (following Phase 5 conventions)
- Freeze script implementation details
- feature_engine.py template structure

### Deferred Ideas (OUT OF SCOPE)
- Rotational strategy archetype support — future archetype registration, not Phase 6 work (infrastructure is archetype-agnostic by design)
- Combined feature set evaluation (multi-feature composite signal) — could be a Phase 6 extension or separate phase
- Automated freeze after budget exhaustion — intentionally deferred; human gate preferred
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| AUTO-06 | Stage 02 driver.py written (feature keep/revert, entry-time enforcement, 300 budget) | Stage 04 driver.py is the direct template; entry-time truncation pattern verified with real data; budget enforcement pattern is identical to Stage 04 |
| AUTO-07 | Stage 02 program.md written (<=30 lines) | Stage 04 program.md is the direct template; METRIC/KEEP RULE/BUDGET fields are machine-readable; Stage 02 substitutes spread for pf |
| AUTO-08 | Stage 02 overnight test (20 experiments, feature spread values, entry-time block verified) | P1a has 2882 rows, P1b has 3267 rows — sufficient for MWU; zone_width baseline feature confirmed; canary test pattern verified with real data (IndexError on truncated bar_df) |
</phase_requirements>

---

## Summary

Phase 6 implements the Stage 02 feature autoresearch loop. The architecture is a direct adaptation of the Stage 04 driver pattern: instead of proposing exit parameter perturbations, the driver invokes a fixed harness (evaluate_features.py + feature_evaluator.py) that measures each feature's predictive spread via MWU on P1a vs P1b splits.

The three delivery items are: (1) Stage 02 driver.py — a keep/revert loop that enforces 300-experiment budget and drives the feature_engine.py keep/revert state via current_best/; (2) Stage 02 program.md — machine-readable steering instructions for the Claude agent; and (3) a 20-experiment overnight test verifying spread values populate correctly and the entry-time canary correctly blocks lookahead features.

The entry-time enforcement is purely structural: feature_evaluator.py truncates bar_df to bar_df.iloc[:touch_row['BarIndex']] before calling feature_engine.compute_features(). Any feature that attempts to read a bar at or after the entry index receives an IndexError (verified empirically), which is caught and logged as an entry_time_violation. This is reliable without AST scanning and cannot be bypassed by a well-behaved feature_engine.py.

**Primary recommendation:** Adapt Stage 04 driver.py directly. The loop structure, run_id generation, audit logging, git commit pattern, and TSV append logic are identical — only the "run experiment" step changes from spawning backtest_engine.py to spawning evaluate_features.py.

---

## Standard Stack

### Core (all already installed and verified in the project)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| scipy.stats.mannwhitneyu | scipy 1.17.0 | MWU test — p-value for best-bin PnL comparison | Verified installed; `alternative='two-sided'` is the default and correct choice here |
| numpy.percentile | numpy 2.3.5 | Tercile edge computation on P1a feature values | Required for `np.percentile(series, [33.33, 66.67])` bin edges |
| pandas | (project standard) | Touch/bar data loading, split by date, bin assignment with `pd.cut` | All data loading via shared.data_loader already uses pandas |
| shared.data_loader.load_touches | — | Load P1 touch CSV — already used in Phase 5 feature_evaluator.py placeholder | No new code needed |
| shared.data_loader.load_bars | — | Load bar data for entry-time truncation | Same loader used by backtest engine |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| importlib.util.spec_from_file_location | stdlib | Load feature_engine.py at runtime without sys.path mutation | In feature_evaluator.py — same pattern as evaluate_features.py dispatcher |
| shutil.copy2 | stdlib | Copy feature_engine.py to/from current_best/ | Same pattern as Stage 04 exit_params.json copy |
| hashlib.sha1 | stdlib | Generate run_id from archetype+timestamp+experiment_n | Identical to Stage 04 _generate_run_id() |

### Installation

No new dependencies. All required libraries are already installed in the project environment (scipy 1.17.0, numpy 2.3.5 confirmed).

---

## Architecture Patterns

### Recommended Project Structure

```
stages/02-features/autoresearch/
├── driver.py               # NEW: Stage 02 keep/revert loop (Phase 6)
├── program.md              # NEW: Agent steering instructions (Phase 6)
├── evaluate_features.py    # EXISTS: fixed dispatcher (Phase 5, do not modify)
├── feature_evaluation.json # EXISTS: output of dispatcher
├── results.tsv             # NEW: created by driver on first run
└── current_best/
    └── feature_engine.py   # NEW: seeded by human with zone_width before run

shared/archetypes/zone_touch/
├── feature_evaluator.py    # EXISTS placeholder: Phase 6 adds MWU spread logic
├── feature_engine.py       # NEW: agent edits this (Phase 6)
└── ...

stages/02-features/output/
└── frozen_features.json    # Phase 6+: written by freeze script after human approval
```

### Pattern 1: Entry-Time Truncation Guard

**What:** feature_evaluator.py loads the full bar_df once, then slices it per touch row before calling feature_engine.compute_features(). The feature only sees bars up to and including the entry bar's close.

**When to use:** On every P1 touch row — no sampling, no exceptions.

**Example:**
```python
# In feature_evaluator.py — verified with real data (BarIndex 1321 => bars.iloc[:1321])
bar_df_full = load_bars(str(_BARS_PATH))  # load once, outside the loop

for _, touch_row in touch_df.iterrows():
    bar_index = int(touch_row['BarIndex'])
    bar_df_truncated = bar_df_full.iloc[:bar_index]  # entry bar is iloc[bar_index-1]
    try:
        features = feature_engine.compute_features(bar_df_truncated, touch_row)
        # ... bin and compute spread
    except (IndexError, KeyError, ValueError) as e:
        # Entry-time violation: feature tried to access bar after truncation boundary
        violation_detected = True
        violation_reason = str(e)
```

**Why IndexError is the right signal:** With `bar_df.iloc[:N]`, any access to `iloc[N]` or beyond raises IndexError. A feature reading the bar after entry (lookahead) will fail exactly this way. Verified empirically: `bars.iloc[:5].iloc[5]` raises `IndexError: single positional indexer is out-of-bounds`.

### Pattern 2: MWU Spread Computation (P1a calibrate, P1b validate)

**What:** Compute tercile bin edges on P1a feature values, apply edges to P1b, run MWU on the best-bin PnL distributions across the two periods.

**When to use:** For each new/modified feature after the entry-time guard passes.

**Example:**
```python
# Source: scipy 1.17.0 docs + numpy 2.3.5 percentile API
import numpy as np
from scipy.stats import mannwhitneyu

# Step 1: compute tercile edges on P1a
edges = np.percentile(p1a_feature_values, [33.33, 66.67])

# Step 2: bin P1a and P1b using P1a edges (out-of-sample bin assignment)
import pandas as pd
def assign_bins(series, edges):
    return pd.cut(series, bins=[-np.inf, edges[0], edges[1], np.inf],
                  labels=['low', 'mid', 'high'])

p1a['bin'] = assign_bins(p1a[feature_name], edges)
p1b['bin'] = assign_bins(p1b[feature_name], edges)

# Step 3: extract best-bin PnL distributions
# Note: 'best' bin direction depends on feature; assume high = best (verify per feature)
p1a_best_pnl = p1a[p1a['bin'] == 'high']['pnl_ticks']
p1b_best_pnl = p1b[p1b['bin'] == 'high']['pnl_ticks']

# Step 4: spread = mean(best-bin P1a) - mean(worst-bin P1a)
p1a_worst_pnl = p1a[p1a['bin'] == 'low']['pnl_ticks']
spread = float(p1a_best_pnl.mean() - p1a_worst_pnl.mean())

# Step 5: MWU test P1a best-bin vs P1b best-bin
if len(p1a_best_pnl) > 0 and len(p1b_best_pnl) > 0:
    _, mwu_p = mannwhitneyu(p1a_best_pnl, p1b_best_pnl, alternative='two-sided')
else:
    mwu_p = 1.0  # Degenerate: insufficient data, treat as fail
```

**Key decision from CONTEXT.md:** The outcome variable is **trade PnL in ticks** — not Reaction from the touch CSV. The Reaction column is a bar-count lookahead measure. PnL in ticks must come from the backtest engine's per-touch simulation, OR from a simplified proxy (see pitfalls below).

### Pattern 3: Driver Loop (Stage 04 Adaptation)

**What:** Stage 02 driver.py runs the same loop as Stage 04 but calls evaluate_features.py instead of backtest_engine.py, and copies feature_engine.py to/from current_best/ instead of exit_params.json.

**Key structural difference from Stage 04:**
- The "proposal step" is absent — driver does NOT write feature_engine.py; the human agent (Claude) does
- Driver instead: (1) checks if feature_engine.py has changed since last iteration, (2) runs harness, (3) reads result, (4) keep/revert

**TSV columns for Stage 02 (adapting Stage 04 24-column layout):**
The Stage 04 TSV header is already defined and used in results_master.tsv. Stage 02 driver should write to its own results.tsv using the same header for compatibility. Relevant populated columns: run_id, stage='02-features', timestamp, archetype, feature_name (in the 'features' column), spread (in mwu_p column or dedicated), mwu_p, n_prior_tests, verdict, notes.

### Pattern 4: feature_engine.py Interface Contract

**What:** compute_features(bar_df, touch_row) -> dict[str, float]

**Constraints:**
- Returns a dict keyed by feature name, values are floats
- Must only use data from bar_df (truncated) and scalar values from touch_row
- Must not raise exceptions on valid truncated data
- zone_width can be computed purely from touch_row['ZoneTop'] and touch_row['ZoneBot'] — no bar data needed

**Example template:**
```python
# archetype: zone_touch
"""Feature engine for zone_touch archetype.
Edit this file during Stage 02 autoresearch.
compute_features() must be entry-time safe: only use bar_df rows and touch_row scalars.
"""

def compute_features(bar_df, touch_row) -> dict:
    """Compute all registered features for a single touch.

    Args:
        bar_df: DataFrame of bars truncated at entry bar index (iloc[:BarIndex])
        touch_row: Series with touch data columns (ZoneTop, ZoneBot, ZoneAgeBars, etc.)

    Returns:
        dict mapping feature_name -> float value
    """
    features = {}
    # zone_width: computable from touch_row only (entry-time safe, no bar_df needed)
    zone_width_ticks = (touch_row['ZoneTop'] - touch_row['ZoneBot']) / 0.25
    features['zone_width'] = float(zone_width_ticks)
    return features
```

### Anti-Patterns to Avoid

- **Using Reaction/Penetration/RxnBar_*/PenBar_* as features:** These are post-entry measurements from the touch CSV. They look like columns but are lookahead. The entry-time guard won't catch them because they come from touch_row, not bar_df. The driver/evaluator must explicitly exclude these columns from feature computation or document them as off-limits.
- **Using pd.cut with duplicate edges:** If a feature has very low variance, tercile edges may be identical, causing pd.cut to fail. Must handle degenerate case (all touches in same bin → spread=0.0, skip MWU).
- **Assuming 'high' bin is always 'best':** For some features (e.g., zone_age where older = worse), 'low' may be the best bin. The CONTEXT.md says "best-bin vs worst-bin" — evaluator must determine which end is predictively better, not always 'high'.
- **Forgetting to load bar data for bar-based features:** feature_evaluator.py currently only loads touch data. Bar-based features (vol_ratio, ATR, etc.) require loading bar_data too — must add load_bars() call when first bar-dependent feature is added.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Non-parametric distribution test | Custom rank-sum logic | `scipy.stats.mannwhitneyu` | Handles ties, correct p-value, one call |
| Percentile-based binning | Manual sort + index math | `numpy.percentile` + `pandas.pd.cut` | Handles edge cases, NaN-safe with `nan_policy` |
| Module loading from path | sys.path mutation | `importlib.util.spec_from_file_location` | Already established in evaluate_features.py; no path contamination |
| Run ID generation | UUID or sequential int | `hashlib.sha1(archetype+timestamp+n)[:7]` | Already established in Stage 04 driver |
| Freeze script parsing | Regex on feature_engine.py | Import feature_engine via importlib, call compute_features on dummy data to get keys | Structural: feature names come from the dict keys returned by compute_features |

**Key insight:** The MWU test has edge cases (all-equal distributions, n=0, single-element bins) that are handled correctly by scipy. Custom implementations will miss these. Always guard for empty bins before calling mannwhitneyu.

---

## Common Pitfalls

### Pitfall 1: Outcome Variable Confusion — Reaction vs PnL

**What goes wrong:** CONTEXT.md specifies "trade PnL in ticks" as the outcome variable, but the touch CSV contains a `Reaction` column (bars of positive reaction). Using Reaction as the outcome proxy would be a different metric than the backtest engine's pnl_ticks.

**Why it matters:** The MWU spread computed from Reaction vs pnl_ticks will differ. The keep threshold (spread > 0.15) was calibrated against pnl_ticks context.

**How to handle:** The evaluator must either (a) run the backtest engine per-touch to get true pnl_ticks, or (b) use a simplified PnL proxy. Given the overnight loop runs 20+ experiments each touching thousands of P1 rows, per-touch engine calls would be prohibitively slow. Research the existing touch data for a usable PnL proxy — the `Reaction` column is in "ticks of price movement" not trade PnL, but may serve as a directional proxy if normalized. **This is the most critical open question for planning.**

**Warning signs:** spread values that are implausibly large (thousands of ticks) suggest Reaction is being used raw instead of normalized trade PnL.

### Pitfall 2: Degenerate Bins from Low-Variance Features

**What goes wrong:** `np.percentile(series, [33.33, 66.67])` returns identical values when the feature has <3 unique values. `pd.cut` with non-unique edges raises ValueError.

**How to avoid:**
```python
edges = np.percentile(values, [33.33, 66.67])
if edges[0] == edges[1]:
    return {"spread": 0.0, "mwu_p": 1.0, "kept": False, "reason": "degenerate_bins"}
```

**Warning signs:** ValueError from pd.cut during first run.

### Pitfall 3: Budget Count Off-By-One

**What goes wrong:** Stage 04 established: n_prior_tests is counted BEFORE appending the new row. Budget=300 means experiment 300 runs (seeded row counts as 1, so 299 new experiments maximum if seeded). Driver must check `if n_prior_tests >= budget: stop` before running.

**How to avoid:** Copy Stage 04's `_count_tsv_rows()` + pre-check pattern verbatim. Do not count rows after appending.

### Pitfall 4: feature_engine.py Not Yet Present

**What goes wrong:** On first run, if no feature_engine.py exists in current_best/ or shared/archetypes/zone_touch/, the driver loop will error when trying to diff or load it.

**How to avoid:** Driver must check for feature_engine.py existence before running harness. If absent (and current_best/ also empty), treat as zero-feature baseline, return spread=0.0. The human seeds current_best/feature_engine.py with zone_width before the first real run.

### Pitfall 5: Entry-Time Violation from touch_row Columns, Not bar_df

**What goes wrong:** The truncation guard only protects bar_df access. A feature that reads `touch_row['Reaction']` or `touch_row['RxnBar_30']` uses lookahead data from the touch CSV — this is NOT caught by the bar_df truncation.

**How to avoid:** feature_evaluator.py must pass only the entry-time-safe columns of touch_row to compute_features. Explicitly filter out post-entry columns before passing: Reaction, Penetration, ReactionPeakBar, ZoneBroken, BreakBarIndex, BarsObserved, RxnBar_*, PenBar_*. This is a structural safeguard, not documentation.

### Pitfall 6: feature_evaluator.py is "Never Touch" but Needs Significant Changes

**What goes wrong:** The Phase 5 feature_evaluator.py is a placeholder returning []. Phase 6 adds MWU spread logic, bar loading, P1a/P1b splitting — this is the PRIMARY work of Phase 6. The file must be substantially rewritten.

**How to avoid:** Treat Phase 5 feature_evaluator.py as a starting template, not a constraint. The "never touch evaluate_features.py" rule applies to the dispatcher (evaluate_features.py in autoresearch/), NOT to feature_evaluator.py in shared/archetypes/zone_touch/. These are different files.

---

## Code Examples

### Loading P1 Data and Splitting P1a/P1b

```python
# Source: period_config.md — P1a = 2025-09-16 to 2025-10-31, P1b = 2025-11-01 to 2025-12-14
# These dates are the current computed split (informational — read from data_manifest.json at runtime)
from shared.data_loader import load_touches, load_bars

touch_df = load_touches(str(_P1_TOUCHES_PATH))
bar_df = load_bars(str(_BARS_PATH))

p1a_mask = touch_df['DateTime'] <= pd.Timestamp('2025-10-31 23:59:59')
p1b_mask = (touch_df['DateTime'] >= pd.Timestamp('2025-11-01')) & \
            (touch_df['DateTime'] <= pd.Timestamp('2025-12-14 23:59:59'))

p1a = touch_df[p1a_mask].copy()
p1b = touch_df[p1b_mask].copy()
# P1a: 2882 rows (verified), P1b: 3267 rows (verified)
```

### Bar Truncation Per Touch Row

```python
# BarIndex in touch CSV is 1-indexed absolute bar number in the bar file
# bar_df.iloc[:bar_index] gives all bars up to AND including the entry bar
bar_index = int(touch_row['BarIndex'])
bar_df_truncated = bar_df_full.iloc[:bar_index]
# bar_df_truncated.iloc[-1] is the entry bar (valid entry-time data)
# bar_df_truncated.iloc[bar_index] would raise IndexError (post-entry)
```

### MWU Spread with Degenerate Guard

```python
from scipy.stats import mannwhitneyu
import numpy as np
import pandas as pd

def compute_mwu_spread(p1a_values, p1a_pnl, p1b_values, p1b_pnl, feature_name):
    """Returns dict with spread, mwu_p, kept, reason."""
    edges = np.percentile(p1a_values.dropna(), [33.33, 66.67])
    if edges[0] >= edges[1]:
        return {"name": feature_name, "spread": 0.0, "mwu_p": 1.0,
                "kept": False, "reason": "degenerate_bins"}

    def bin_series(vals):
        return pd.cut(vals, bins=[-np.inf, edges[0], edges[1], np.inf],
                      labels=['low', 'mid', 'high'])

    p1a_bins = bin_series(p1a_values)
    p1b_bins = bin_series(p1b_values)

    p1a_best = p1a_pnl[p1a_bins == 'high']
    p1a_worst = p1a_pnl[p1a_bins == 'low']
    p1b_best = p1b_pnl[p1b_bins == 'high']

    spread = float(p1a_best.mean() - p1a_worst.mean()) if len(p1a_best) > 0 and len(p1a_worst) > 0 else 0.0

    if len(p1a_best) < 2 or len(p1b_best) < 2:
        mwu_p = 1.0
    else:
        _, mwu_p = mannwhitneyu(p1a_best, p1b_best, alternative='two-sided')

    kept = (spread > 0.15) and (mwu_p < 0.10)
    return {"name": feature_name, "spread": spread, "mwu_p": float(mwu_p),
            "kept": kept, "reason": "ok" if kept else "threshold_not_met"}
```

### results.tsv TSV Row for Stage 02

The Stage 04 24-column TSV header is reused for Stage 02. Key populated columns:

```
run_id | stage='02-features' | timestamp | hypothesis_name | archetype | version='' |
features=<feature_name> | pf_p1=<spread> | pf_p2='' | trades_p1=<n_p1a_touches> |
trades_p2=<n_p1b_touches> | mwu_p=<mwu_p_value> | perm_p='' | pctile='' |
n_prior_tests=<count_before> | verdict=<kept|reverted|entry_time_violation> |
sharpe_p1='' | max_dd_ticks='' | avg_winner_ticks='' | dd_multiple='' |
win_rate='' | regime_breakdown='' | api_cost_usd='' | notes=<git:hash|reason>
```

Note: pf_p1 column carries the spread value (reusing dashboard column for Stage 02 metric).

---

## Open Questions

1. **Outcome variable: what is "trade PnL in ticks" for feature evaluation?**
   - What we know: CONTEXT.md says "Outcome variable: trade PnL in ticks (same as backtest engine output)"
   - What's unclear: Computing true per-touch PnL ticks requires running the backtest simulator for each touch row — expensive for 6000 P1 rows * 300 experiments = 1.8M simulator calls. This was not an issue in Stage 04 (one run = full backtest). Stage 02 needs a per-touch PnL estimate.
   - Options: (a) Run simulator per touch in evaluate() — possible but slow; (b) Use a pre-computed PnL column from a prior backtest run stored as a reference; (c) Use Reaction ticks as a directional proxy after normalization
   - Recommendation: **Plan should clarify this upfront.** The most practical approach is to run the zone_touch simulator in evaluate() for the seeded feature set across all P1 touches once per evaluator call (not per experiment). The simulator already has a pure-function interface: `run(bar_df, touch_row, config, bar_offset) -> SimResult`. The evaluator would need a reference config (from current_best/exit_params.json or a fixed reference config).

2. **Which bin direction is "best" for zone_width and future features?**
   - What we know: zone_width high bin has higher mean Reaction (494 vs 487 ticks). But is wider zone better or worse for trade PnL?
   - What's unclear: With actual PnL ticks, the direction may differ from Reaction.
   - Recommendation: compute spread as abs(best - worst) or let the evaluator test both directions and take the better spread. OR: define "best" as the bin with highest mean PnL, discovered at runtime.

3. **How does the driver know which feature key is "new" in feature_engine.py?**
   - What we know: CONTEXT.md says "Driver tells evaluator which key is new (from program.md or diff against current_best/)"
   - What's unclear: program.md format needs a NEW_FEATURE field, or the driver diffs current_best/feature_engine.py against stages/02-features/autoresearch/ to find the new key
   - Recommendation: Add `NEW_FEATURE: <feature_name>` field to program.md (machine-readable, same pattern as METRIC/KEEP RULE/BUDGET). Simpler than runtime diffing.

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest (existing, tests/ at repo root) |
| Config file | none — run from repo root |
| Quick run command | `pytest tests/test_feature_evaluator.py tests/test_stage02_driver.py -x -q` |
| Full suite command | `pytest tests/ -x -q` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| AUTO-06 | driver.py enforces 300-experiment budget — stops at 300, refuses experiment 301 | unit | `pytest tests/test_stage02_driver.py::TestBudgetEnforcement -x` | Wave 0 |
| AUTO-06 | driver.py keep/revert: copies feature_engine.py to current_best/ on keep, restores on revert | unit | `pytest tests/test_stage02_driver.py::TestKeepRevert -x` | Wave 0 |
| AUTO-06 | entry-time violation: driver logs kept=false, reason='entry_time_violation' in TSV | unit | `pytest tests/test_stage02_driver.py::TestEntryTimeViolation -x` | Wave 0 |
| AUTO-07 | program.md parses correctly (METRIC, KEEP RULE, BUDGET, NEW_FEATURE fields) | unit | `pytest tests/test_stage02_driver.py::test_parse_program_md -x` | Wave 0 |
| AUTO-08 | feature_evaluator.evaluate() returns spread and mwu_p for zone_width on real P1 data | integration | `pytest tests/test_feature_evaluator.py::TestMWUSpread -x` | Wave 0 (extends existing) |
| AUTO-08 | entry-time canary: feature reading post-entry bar is detected and blocked | integration | `pytest tests/test_feature_evaluator.py::TestEntryTimeCanary -x` | Wave 0 |
| AUTO-08 | 20-experiment overnight smoke test runs without error, TSV has 20+ rows with spread column populated | integration | `pytest tests/test_stage02_driver.py::TestOvernightSmoke -x` | Wave 0 |

### Sampling Rate

- **Per task commit:** `pytest tests/test_stage02_driver.py tests/test_feature_evaluator.py -x -q`
- **Per wave merge:** `pytest tests/ -x -q`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps

- [ ] `tests/test_stage02_driver.py` — new file; covers AUTO-06, AUTO-07, AUTO-08 driver tests
- [ ] `tests/test_feature_evaluator.py` — extends existing Phase 5 file; add MWU spread and canary tests for Phase 6
- [ ] `shared/archetypes/zone_touch/feature_engine.py` — does not exist yet; must be created as seeded baseline before tests can run

*(Existing `tests/test_evaluate_features.py` and `tests/test_feature_evaluator.py` from Phase 5 require no changes to pass — they test the Phase 5 placeholder interface which remains valid.)*

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| feature_evaluator.py returns [] (Phase 5 placeholder) | Phase 6: evaluator runs MWU spread computation per feature | Phase 6 (now) | Dispatcher output becomes meaningful — spread/mwu_p populated |
| No feature_engine.py exists | Phase 6: seeded with zone_width baseline, agent accumulates features | Phase 6 (now) | Stage 02 autoresearch loop becomes runnable |
| No Stage 02 driver.py | Phase 6: keep/revert loop with 300-experiment budget | Phase 6 (now) | Overnight feature search becomes automated |

**Deprecated/outdated:**
- Phase 5 feature_evaluator.py comment "Phase 5 placeholder": replace with real implementation in Phase 6; the comment guidance to add MWU in Phase 6 is now the implementation target.

---

## Sources

### Primary (HIGH confidence)

- `stages/04-backtest/autoresearch/driver.py` — direct template for Stage 02 driver; verified read
- `stages/02-features/autoresearch/evaluate_features.py` — fixed dispatcher; verified read
- `shared/archetypes/zone_touch/feature_evaluator.py` — Phase 5 placeholder; verified read
- `_config/statistical_gates.md` — budget=300 for Stage 02; keep threshold anchor; verified read
- `_config/period_config.md` — P1a = 2025-09-16 to 2025-10-31, P1b = 2025-11-01 to 2025-12-14; verified read
- `stages/02-features/references/feature_rules.md` — spread > 0.15 AND MWU p < 0.10; verified read
- `tests/test_driver.py`, `tests/test_feature_evaluator.py` — test patterns to follow; verified read
- scipy.stats.mannwhitneyu API — verified with `help(mannwhitneyu)` in project environment (scipy 1.17.0)
- numpy.percentile API — verified in project environment (numpy 2.3.5)

### Secondary (MEDIUM confidence)

- Empirical verification: P1a=2882 touches, P1b=3267 touches — sufficient for MWU test
- Empirical verification: BarIndex truncation pattern (iloc[:N] raises IndexError on post-entry access)
- Empirical verification: zone_width P1a tercile edges [82, 184] ticks, spread≈6.9 ticks using Reaction proxy

### Tertiary (LOW confidence — open question)

- "trade PnL in ticks" as outcome variable: the exact computation method (simulator per touch vs proxy) is not specified in existing code and needs resolution in planning

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all libraries verified installed; APIs verified
- Architecture: HIGH — direct adaptation of Stage 04 pattern, all integration points confirmed
- Entry-time enforcement: HIGH — empirically verified with real data
- MWU computation: HIGH — scipy API confirmed, edge cases documented
- Outcome variable (PnL ticks): LOW — open question on computation method

**Research date:** 2026-03-14
**Valid until:** 2026-04-14 (stable internal project, no external dependencies changing)
