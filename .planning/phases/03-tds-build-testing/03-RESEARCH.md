# Phase 3: TDS Build + Testing - Research

**Researched:** 2026-03-16
**Domain:** Trend Defense System — Python implementation of a 5-detector, 3-level escalation subsystem integrated into the rotational simulator's state machine
**Confidence:** HIGH (based on spec Section 4 which is fully defined, plus thorough review of the existing codebase)

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| ROT-RES-04 | Build trend_defense.py with 5 detectors (retracement quality, velocity monitor, consecutive add counter, drawdown budget, trend precursor composite) and 3-level escalation (Level 1 early warning, Level 2 active threat, Level 3 emergency), including hypothesis feed-ins from H33, H36, H38, H39, H40. Test each TDS level independently against baseline on all 3 bar types. Measure on survival metrics: worst-cycle DD, max-level exposure %, tail ratio, drawdown budget hit count. TDS velocity thresholds and cooldown periods must be bar-type-specific (10-sec has ~5x more bars per unit time). | Spec Section 4 provides complete detector spec, escalation logic, parameters, and metrics. Existing `RotationalSimulator` has `trend_defense_level_max` field in cycle records and `forced_flat` state hooks ready for TDS integration. `feature_engine.py` already computes H33, H35, H38, H40 features. H36 and H39 require simulator state (dynamic features) — their NaN placeholders are already registered in `_DYNAMIC_FEATURE_COLUMNS`. |
</phase_requirements>

---

## Summary

Phase 3 builds `trend_defense.py` — a standalone module that implements the Trend Defense System (TDS) described in spec Section 4. TDS is the dedicated response to the strategy's primary failure mode: straight-line moves that fire all martingale levels with no retracement opportunity. The module plugs into the existing `RotationalSimulator` via well-defined integration points that already exist in the code.

The codebase entering Phase 3 is in excellent shape. `rotational_simulator.py` already has `trend_defense_level_max=0` in cycle records (placeholder awaiting TDS), the simulation loop has a logical seam where TDS evaluation runs before state machine transitions, and `feature_engine.py` has vectorized implementations of H33 (price speed), H35 (imbalance trend), H38 (regime transition speed), and H40 (band-relative speed). The two state-dependent features (H36 adverse move speed, H39 cycle adverse velocity ratio) are declared as dynamic features requiring simulator state — they must be computed inside the simulator loop, not in the static vectorized stage.

The critical Phase 3 design challenge is the bar-type cadence asymmetry: 10-sec bars arrive at ~6/minute (fixed cadence, RTH session only), while 250-vol and 250-tick bars arrive irregularly, averaging ~50-80 bars per 10 minutes during active periods. A velocity threshold of "Level 0 to Level 3 in fewer than 5 bars" means something completely different across bar types. All TDS timing-dependent parameters (velocity circuit breaker, consecutive add counter, cooldown bars) must either be bar-type-specific or expressed in elapsed seconds rather than bar counts.

**Primary recommendation:** Build `trend_defense.py` as a stateful class (`TrendDefenseSystem`) that is instantiated per simulation run and receives `bar_duration_sec` as a computed input alongside bar data. Express all timing thresholds in seconds, not bars, then convert to bar counts using the series' median bar duration at initialization. This makes parameters interpretable across bar types while keeping the simulator loop clean.

---

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Python | 3.14 (repo standard) | Implementation language | Already in use throughout codebase |
| pandas | repo standard | DataFrame operations, cycle data | All existing code uses pandas |
| numpy | repo standard | Numerical computation | Already used in feature_engine.py |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| dataclasses | stdlib | TDS state container | Already used for SimulationResult in rotational_simulator.py |
| pytest | 9.0.2 (confirmed in .pytest_cache) | Unit tests | Already the test framework for all rotational tests |

### No New Dependencies
TDS is pure Python/numpy/pandas. No new packages are needed. The existing test infrastructure handles all coverage needs.

**Installation:**
No new packages — all dependencies already present in the repo environment.

---

## Architecture Patterns

### Recommended Module Structure
```
shared/archetypes/rotational/
├── trend_defense.py          # New: TDS module (Phase 3 deliverable)
├── test_trend_defense.py     # New: TDS unit tests
├── rotational_simulator.py   # Modify: integrate TDS class
├── feature_engine.py         # Modify: add H36/H39 dynamic feature wiring
└── tds_results/              # New: TDS testing output directory
    ├── tds_test_P1a.tsv      # Results: each TDS config vs baseline
    └── tds_test_report.md    # Summary: effectiveness per level per bar type
```

### Pattern 1: TrendDefenseSystem as Stateful Class

**What:** A class instantiated once per simulation run that maintains detector state across bars and produces a `ThreatLevel` (0-3). The simulator calls `evaluate()` once per bar before state machine transitions, then calls `apply_response()` to modify available actions.

**When to use:** The TDS must track state across bars (retracement history, consecutive add count, running cycle drawdown). A stateful class is the only clean way to do this without polluting the RotationalSimulator's own state dict.

**Interface contract:**
```python
# Source: spec Section 4 + pattern from existing simulator design (Section 6.1)

@dataclass
class TDSState:
    current_level: int = 0          # 0=inactive, 1=early warning, 2=active threat, 3=emergency
    forced_flat: bool = False
    cooldown_remaining: int = 0
    consecutive_adds: int = 0
    last_retracement_depths: list = field(default_factory=list)
    cycle_unrealized_pnl_ticks: float = 0.0
    l1_triggers: int = 0
    l2_triggers: int = 0
    l3_triggers: int = 0


class TrendDefenseSystem:
    def __init__(self, config: dict, bar_duration_stats: dict) -> None:
        """
        config: trend_defense sub-dict from hypothesis config
        bar_duration_stats: {'median_sec': float, 'p10_sec': float}
          computed from bar_df before simulation starts
        """

    def evaluate(self, bar: pd.Series, features: dict, sim_state: dict) -> int:
        """
        Run all 5 detectors. Return ThreatLevel 0-3.
        sim_state: {'direction', 'level', 'anchor', 'position_qty',
                    'cycle_start_bar', 'bar_idx', 'avg_entry_price'}
        """

    def apply_response(self, sim_state: dict, threat: int) -> dict:
        """
        Return dict of action modifiers:
          {'step_widen_factor': float, 'max_levels_reduction': int,
           'refuse_adds': bool, 'force_flatten': bool,
           'reduced_reversal_threshold': float | None}
        """

    def update_cycle_metrics(self, bar: pd.Series, sim_state: dict) -> None:
        """Update running cycle PnL and retracement tracking after each bar."""

    def on_reversal(self) -> None:
        """Reset per-cycle detector state when a reversal occurs."""

    def on_add(self) -> None:
        """Increment consecutive add counter."""

    def can_reengage(self, features: dict) -> bool:
        """Level 3 re-engagement check: cooldown expired AND threat < Level 1."""

    def get_summary(self) -> dict:
        """Return TDS trigger counts and recovery stats for extended_metrics."""
```

### Pattern 2: Bar-Type-Aware Parameter Initialization

**What:** TDS timing parameters are stored in seconds at configuration time, then converted to bar counts at initialization using median bar duration of the actual data.

**Why:** "Velocity circuit breaker: Level 0 → Level N in fewer than K bars" has a 5x different meaning between 10-sec bars and vol/tick bars. Expressing thresholds in seconds makes configs interpretable and cross-bar-type-comparable.

**Example:**
```python
# In TrendDefenseSystem.__init__:
median_bar_sec = bar_duration_stats['median_sec']  # e.g., 10.0 for 10sec, ~7.5 for vol/tick

# Convert second-based thresholds to bar counts
self._velocity_bars = max(1, round(
    config['level_2']['velocity_threshold_sec'] / median_bar_sec
))
self._cooldown_bars = max(1, round(
    config['level_3']['cooldown_sec'] / median_bar_sec
))

# Typical conversions:
# velocity_threshold_sec=30  -> 3 bars on 10sec, ~4 bars on vol/tick
# cooldown_sec=300           -> 30 bars on 10sec, ~40 bars on vol/tick
```

### Pattern 3: Simulator Integration Seam

**What:** The existing RotationalSimulator simulation loop has an explicit structural seam where TDS evaluation should run — before state machine transitions, after feature computation. The pseudocode in spec Section 6.2 already shows this structure.

**Current simulator loop structure (from rotational_simulator.py line 618-638):**
```python
for bar_idx, row in bars.iterrows():
    close = float(row["Last"])
    dt = row["datetime"]

    if self._state == "FLAT":
        self._seed(...)
    elif self._state == "POSITIONED":
        distance = close - self._anchor
        # ... check in_favor / against
        if in_favor:
            self._reversal(...)
        elif against:
            self._add(...)
```

**Target structure with TDS integrated:**
```python
for bar_idx, row in bars.iterrows():
    close = float(row["Last"])
    dt = row["datetime"]

    # Compute dynamic features (H36 adverse speed, H39 velocity ratio)
    dyn_features = self._compute_dynamic_features(bar_idx, row)
    features = {**static_features_row, **dyn_features}

    # TDS evaluation (if enabled)
    action_modifiers = {'step_widen_factor': 1.0, 'max_levels_reduction': 0,
                        'refuse_adds': False, 'force_flatten': False,
                        'reduced_reversal_threshold': None}
    if self._tds is not None:
        threat = self._tds.evaluate(row, features, self._get_sim_state(bar_idx))
        action_modifiers = self._tds.apply_response(self._get_sim_state(bar_idx), threat)
        if action_modifiers['force_flatten']:
            if self._tds.state.cooldown_remaining > 0:
                self._tds.state.cooldown_remaining -= 1
                self._tds.update_cycle_metrics(row, self._get_sim_state(bar_idx))
                continue
            elif not self._tds.can_reengage(features):
                continue

    if self._state == "FLAT":
        self._seed(...)
    elif self._state == "POSITIONED":
        effective_step = self._step_dist * action_modifiers['step_widen_factor']
        effective_max_levels = self._max_levels - action_modifiers['max_levels_reduction']
        # ... check in_favor / against using effective_step
        if in_favor:
            self._reversal(...)
            if self._tds: self._tds.on_reversal()
        elif against and not action_modifiers['refuse_adds']:
            if self._level < effective_max_levels:
                self._add(...)
                if self._tds: self._tds.on_add()

    if self._tds:
        self._tds.update_cycle_metrics(row, self._get_sim_state(bar_idx))
```

### Pattern 4: The 5 Detectors

**What each detector computes** (from spec Section 4.2):

```python
# Detector 1: Retracement Quality
# Tracks pullback depths within current cycle.
# Trigger: declining retracement depths over consecutive swings.
# State: list of last N retracement depth ratios (from TradeLogger.finalize_cycle
# pattern, but tracked live within the cycle)
retracement_declining = (
    len(self.state.last_retracement_depths) >= 3
    and all(
        self.state.last_retracement_depths[i] < self.state.last_retracement_depths[i-1]
        for i in range(1, len(self.state.last_retracement_depths[-3:]))
    )
)

# Detector 2: Velocity Monitor
# Trigger: Level 0 -> Level N in fewer than K bars (converted from seconds).
# Tracks: bar_idx when level 0 was entered, current level.
level_escalation_too_fast = (
    self.state.current_level > 0
    and (bar_idx - self._level_zero_bar_idx) < self._velocity_bars
)

# Detector 3: Consecutive Add Counter
# Trigger: N adds without any retracement reaching X% of step distance.
too_many_consecutive_adds = (
    self.state.consecutive_adds >= self._max_consecutive_adds
)

# Detector 4: Drawdown Budget
# Trigger: Cycle unrealized PnL exceeds max allowed cycle drawdown.
drawdown_budget_hit = (
    self.state.cycle_unrealized_pnl_ticks < -self._drawdown_budget_ticks
)

# Detector 5: Trend Precursor Composite
# Trigger: Multiple precursors align simultaneously.
# Consumes: features from H33 (price_speed), H38 (regime_transition_speed),
#           H40 (band_speed_state), H36 (adverse_speed — dynamic),
#           H39 (adverse_velocity_ratio — dynamic)
precursor_signals = 0
if features.get('price_speed', 0) > self._speed_threshold:
    precursor_signals += 1
if features.get('regime_transition_speed', 0) > self._regime_accel_threshold:
    precursor_signals += 1
if features.get('band_speed_state', 0) >= 3:  # outside_sd2 + fast
    precursor_signals += 1
if features.get('adverse_speed', 0) > self._adverse_speed_threshold:
    precursor_signals += 1
trend_precursor_composite_fires = precursor_signals >= self._precursor_min_signals
```

### Anti-Patterns to Avoid

- **Encoding TDS thresholds as bar counts in the config JSON**: Configs become uninterpretable across bar types. Always store thresholds in seconds or ticks, convert at initialization.
- **Computing H36 (adverse_speed) and H39 (adverse_velocity_ratio) in the vectorized feature_engine pass**: These require `self._direction` and cycle tracking state that only exist inside the live simulation loop. They must be computed as dynamic features per bar, not as static vectorized columns.
- **Having TrendDefenseSystem directly mutate RotationalSimulator state**: TDS should return action modifiers and the simulator applies them. This keeps TDS testable in isolation with a mock sim_state dict.
- **Resetting consecutive_adds on reversal only**: Must also reset when a qualifying retracement occurs mid-cycle (price retracing >= X% of step_dist from the add anchor). Otherwise the counter can accumulate across a profitable recovery.
- **Single global TDS parameter set**: Spec Section 4.5 provides parameters per level (not per bar type). The bar-type adaptation is in the seconds-to-bars conversion at init time, not in separate configs per bar type.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Bar duration computation | Custom timestamp parser | `_compute_bar_duration_sec()` already in feature_engine.py | Already handles 10-sec fractional seconds format, zero-duration guard, fallback to median |
| Cycle unrealized PnL | Custom accounting loop | Reuse the MAE pattern from `TradeLogger.finalize_cycle` | The bar-by-bar unrealized PnL logic (lines 228-274 of rotational_simulator.py) is already correct and handles Long/Short asymmetry |
| Feature computation for H33/H38/H40 | TDS-internal feature compute | Use features dict already computed by `FeatureComputer.compute_static_features()` | These features are already vectorized in feature_engine.py and available in the features dict at each bar |
| Test harness for TDS | Custom run loop | Copy pattern from test_rotational_simulator.py | `_make_config()` helper and synthetic DataFrame construction already established |
| Timing threshold conversion | ad hoc `if bar_type == '10sec': threshold = 30 else: threshold = 6` | Compute median bar duration from actual data at init time | Robust to future bar types, handles irregular vol/tick cadence correctly |

**Key insight:** TDS is mostly a matter of wiring existing pieces together. The feature computation is done, the simulator loop structure is defined in the spec, the cycle record already has `trend_defense_level_max` as a placeholder, and the parameter structure (`trend_defense.level_1/2/3` sub-dicts) is already in `rotational_hypothesis_config.json`. The implementation task is building the TDS class and integrating the wiring — not designing from scratch.

---

## Common Pitfalls

### Pitfall 1: Bar-Type Cadence Asymmetry in TDS Timing Parameters
**What goes wrong:** TDS Level 2 "velocity circuit breaker" triggers after K bars of rapid escalation. On 10-sec bars (250k bars, ~6/min), K=5 means 50 seconds. On 250-vol bars (~138k bars, ~50/min active), K=5 means 6 seconds. The same config fires 8x more aggressively on vol bars. This produces TDS that is radically different in behavior across bar types, making cross-bar-type comparison meaningless.
**Why it happens:** Bar count thresholds feel natural when looking at one bar type but are not portable.
**How to avoid:** Express ALL timing thresholds in seconds. Convert to bar counts at `TrendDefenseSystem.__init__` using `median_bar_sec` computed from the actual bar_df before simulation. Document this conversion in TDS config comments.
**Warning signs:** TDS Level 2/3 triggers far more often on one bar type than others at the same parameter settings.

### Pitfall 2: H36 (Adverse Move Speed) Computed in Static Feature Pass
**What goes wrong:** H36 is listed in `_DYNAMIC_FEATURE_COLUMNS` in feature_engine.py because it requires `self._direction` from the live simulator state. Attempting to compute it in `compute_hypothesis_features()` returns a NaN column (the placeholder behavior is already implemented). If TDS tries to read `adverse_speed` from the pre-computed features dict and gets NaN, the Trend Precursor detector silently misses its most critical signal.
**Why it happens:** H36 looks like a simple feature (price delta / time) until you realize "adverse" is direction-relative.
**How to avoid:** Compute `adverse_speed` inside `_compute_dynamic_features()` in the simulator loop, where `self._direction` is available. Pass it in the features dict to `tds.evaluate()` as a dynamically-computed value, not a static column.
**Warning signs:** TDS trend precursor composite never fires even during rapid adverse moves.

### Pitfall 3: TDS Level 3 Cooldown Does Not Reset Martingale State
**What goes wrong:** Level 3 forces flatten and enters a cooldown. When cooldown expires and `can_reengage()` returns True, the simulator seeds again (starting a new cycle). But if `_level` and `_position_qty` are not explicitly reset during the forced flatten, the next SEED enters with stale level/qty values.
**Why it happens:** The `_reversal()` method resets level/qty as part of the normal reversal flow. A TDS-forced flatten bypasses `_reversal()` and must do the reset explicitly.
**How to avoid:** The `apply_response()` return dict should include `'force_flatten': True` and the simulator must call `_finalize_current_cycle_as_tds_exit()` before entering cooldown, which logs the cycle with `exit_reason='td_flatten'` and resets all state.
**Warning signs:** Cycles after Level 3 recovery show wrong entry prices, wrong levels, or wrong position quantities.

### Pitfall 4: Survival Metrics Comparison Requires Matched WITH/WITHOUT-TDS Runs
**What goes wrong:** Comparing TDS-enabled results against the prior sizing sweep baselines produces misleading comparisons because the baseline configs differ (different StepDist, MaxLevels, MTP) from the TDS test configs.
**Why it happens:** The sizing sweep identified different optimal configs per bar type. TDS must be tested against the same base config it augments.
**How to avoid:** For each TDS level test, run a matched pair: identical config with `trend_defense.enabled=false` (no TDS) vs `trend_defense.enabled=true` (TDS active). The improvement metrics (worst-cycle DD reduction, max-level exposure % reduction) are computed as the delta between these matched pairs, not against the sizing sweep baselines.
**Warning signs:** TDS appears to "improve" results mainly by choosing a different base config that happened to be better, not by the TDS mechanism itself.

### Pitfall 5: Consecutive Add Counter Resets Only on Reversal
**What goes wrong:** If `consecutive_adds` only resets on reversal, a cycle with: ADD → large favorable move → ADD → large favorable move → ADD will count 3 consecutive adds even though price was healthy after each add. The counter should also reset when a qualifying retracement occurs (price moves in favor by >= retracement_pct × step_dist after an add).
**Why it happens:** The spec says "N adds without any retracement" — this requires tracking whether a qualifying retracement has occurred since the last add, not just counting adds since the last reversal.
**How to avoid:** Track `_last_add_price` in TDS state. On each bar, if `price_in_favor_from_last_add >= retracement_pct * step_dist`, reset `consecutive_adds = 0`.
**Warning signs:** TDS Level 2 triggers prematurely on cycles that had healthy retracements between adds.

---

## Code Examples

Verified patterns from the existing codebase:

### Cycle Record Has TDS Field Already
```python
# Source: rotational_simulator.py line 297
self._cycles.append({
    ...
    "trend_defense_level_max": 0,  # no TDS in baseline — placeholder for Phase 3
    "exit_reason": exit_reason,    # "reversal" | "end_of_data" | "td_flatten" needed
})
```

### TDS Config Already in rotational_hypothesis_config.json
```json
{
  "trend_defense": {
    "enabled": false,
    "level_1": {},
    "level_2": {},
    "level_3": {}
  }
}
```

### Dynamic Feature Registration Pattern (feature_engine.py)
```python
# Source: feature_engine.py lines 61-66
_DYNAMIC_FEATURE_COLUMNS = {
    "H17": "cycle_feedback_state",
    "H36": "adverse_speed",           # <- TDS primary feed-in
    "H39": "adverse_velocity_ratio",  # <- TDS primary feed-in
    "H21": "cycle_pnl",
}
```

### H33 Price Speed Already Vectorized (for static feed-in)
```python
# Source: feature_engine.py lines 203-207
elif filter_id == "H33":
    bar_dur = _compute_bar_duration_sec(df)
    df["bar_duration_sec"] = bar_dur
    df["price_speed"] = df["Last"].diff().abs() / bar_dur
```

### H38 Regime Transition Speed Already Vectorized
```python
# Source: feature_engine.py lines 247-263
elif filter_id == "H38":
    n = int(fp.get("transition_lookback", 10))
    # ... composite of ATR ROC + imbalance slope + price acceleration
    df["regime_transition_speed"] = (
        atr_roc.fillna(0) + imbalance_slope.fillna(0) + price_accel.fillna(0)
    )
```

### H40 Band-Speed State Already Vectorized
```python
# Source: feature_engine.py lines 265-286
elif filter_id == "H40":
    # State 0=inside_sd1+slow, 1=inside_sd1+fast, 2=outside_sd2+slow, 3=outside_sd2+fast
    # State 3 (outside_sd2 + fast) is a direct Level 1 TDS trigger per spec Section 4.2
    df["band_speed_state"] = (
        inside_sd1 * 0 + (1 - inside_sd1) * outside_sd2 * (2 + fast)
    )
```

### MAE Pattern for Cycle Unrealized PnL (DrawdownBudget detector input)
```python
# Source: rotational_simulator.py lines 254-258
close = row["Last"]
if direction == "Long":
    unrealized = (close - avg_entry) / tick_size * running_qty_for_excursion
else:
    unrealized = (avg_entry - close) / tick_size * running_qty_for_excursion
mae_ticks = min(mae_ticks, unrealized)
```

### Test Pattern (from test_rotational_simulator.py)
```python
# Source: test_rotational_simulator.py
def _make_config(step_dist=2.0, initial_qty=1, max_levels=4,
                 max_contract_size=8, max_total_position=0, period="P1"):
    return {
        "version": "v1",
        "hypothesis": {"trigger_mechanism": "fixed",
                       "trigger_params": {"step_dist": step_dist},
                       "active_filters": [], "structural_mods": []},
        "martingale": {"initial_qty": initial_qty, "max_levels": max_levels,
                       "max_contract_size": max_contract_size,
                       "max_total_position": max_total_position,
                       "progression": "geometric"},
        "_instrument": {"tick_size": 0.25, "cost_ticks": 3},
        "period": period,
        "bar_data_primary": {"bar_data_10sec_rot": "dummy.csv"},
    }
```

---

## TDS Parameter Starting Points

The spec provides ranges (Section 4.5). These are recommended starting values for the sweep:

| Parameter | Level | Spec Range | Recommended Starting Values |
|-----------|-------|------------|------------------------------|
| `step_widen_factor` | 1 | 1.25–2.0 | [1.25, 1.5, 2.0] |
| `max_levels_reduction` | 1 | -1 | 1 (fixed) |
| `cooldown_sec` | 3 | 50–500 bars → | 300 sec (30 bars @ 10sec, ~40 bars @ vol/tick) |
| `velocity_threshold_sec` | 2 | "fewer than K bars" | 60 sec (6 bars @ 10sec, ~8 bars @ vol/tick) |
| `consecutive_adds_threshold` | 2 | N adds | 3 (sweep: [2, 3, 4]) |
| `drawdown_budget_ticks` | 3 | ATR-scaled | 50 ticks (sweep: [30, 50, 100]) |
| `precursor_min_signals` | precursor | composite | 2 of 4 signals |
| `retracement_reset_pct` | consec-add | qualifying retrace | 0.3 (30% of step_dist) |

**Note from sizing sweep findings:** The "martingale is net negative" finding (Section 6 of sizing_sweep_report.md) means TDS is tested primarily in the context of ML=1 configs (the winning configs). TDS Level 2 ("refuse all further adds") and Level 3 ("force flatten") are the most relevant levels for ML=1 since there are no escalating adds to prevent. Level 1 (widen step, reduce MaxLevels) becomes the primary protective mechanism.

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Martingale as primary feature | Martingale is net-negative; pure rotation is the edge | Phase 02.1 sizing sweep (2026-03-16) | TDS focus shifts from "preventing bad adds" to "protecting rotation entries and preventing prolonged max-exposure" |
| All 41 hypotheses equally weighted for Phase 3 | Only H33, H36, H38, H39, H40 feed into TDS; others deferred to Phase 4 | Spec Section 4.2 (by design) | TDS is simpler to build and test — 5 core detectors, 5 hypothesis feed-ins |
| Phase 1 baseline from fixed step sweep | Baseline is now from sizing sweep: 250vol SD=7.0 ML=1 MTP=2 PF=2.20, 250tick SD=4.5 ML=1 MTP=1 PF=1.84, 10sec SD=10.0 ML=1 MTP=4 PF=1.72 | Phase 02.1 (2026-03-16) | TDS testing must use THESE as baselines, not the original Phase 1 sweep results |

**Deprecated/outdated:**
- H39 (cycle adverse velocity ratio), H23 (conditional adds), H24 (intra-cycle de-escalation) elevated to high priority for Phase 4 TDS testing: per sizing sweep finding, these hypotheses manage a mechanism (martingale escalation) shown to be harmful. They still feed into TDS as signals but are deprioritized for standalone testing.

---

## Architecture Patterns for Testing

### TDS Test Harness Design

TDS must be tested in two modes:

**Mode 1: Unit tests (isolated TDS class)**
- Synthetic bars designed to trigger specific detectors
- Verify each detector fires at correct threshold
- Verify correct action modifiers returned per level
- Verify level transitions: 0→1, 1→2, 2→3, and recovery paths

**Mode 2: Integration tests (TDS inside simulator)**
- Run `RotationalSimulator` with `trend_defense.enabled=true` on real P1a data
- Compare WITH-TDS vs WITHOUT-TDS matched pairs
- Verify survival metrics improve: worst_cycle_dd down, max_level_exposure_pct down
- Verify alpha not destroyed: PF within acceptable range of baseline
- Run all 3 bar types

**Mode 3: Sweep tests (parameter sensitivity)**
- For each TDS level independently: sweep key parameters, record survival metrics
- Level 1 sweep: `step_widen_factor` in [1.25, 1.5, 2.0]
- Level 2 sweep: `velocity_threshold_sec` in [30, 60, 120], `consecutive_adds` in [2, 3, 4]
- Level 3 sweep: `drawdown_budget_ticks` in [30, 50, 100], `cooldown_sec` in [120, 300, 600]

### Survival Metrics to Capture Per TDS Run

From spec Section 4.6 (stored in `extended_metrics.trend_defense`):

| Metric | Column in output TSV | Formula |
|--------|---------------------|---------|
| `worst_cycle_dd_ticks` | `worst_cycle_dd_tds` | `min(cycle.max_adverse_excursion_ticks)` across all cycles |
| `max_level_exposure_pct` | `max_level_exposure_pct_tds` | Already computed in sizing sweep — same formula |
| `tail_ratio` | `tail_ratio_tds` | `p95(cycle.net_pnl_ticks) / abs(p5(cycle.net_pnl_ticks))` |
| `l3_trigger_count` | `l3_triggers` | Count of Level 3 forced flattens |
| `pnl_saved_estimate` | `pnl_saved_ticks` | `worst_cycle_dd_no_tds - worst_cycle_dd_tds` (matched pair delta) |

---

## Open Questions

1. **Which base config to use for TDS testing?**
   - What we know: Sizing sweep identified 3 profiles per bar type (MAX_PROFIT, SAFEST, MOST_CONSISTENT). TDS should be tested on configs that actually have martingale exposure — SAFEST has `max_level_exposure_pct=0` which means TDS Level 2/3 (add-related) never fires.
   - What's unclear: Should TDS be tested on MAX_PROFIT config (highest PF, some add exposure) or a purpose-built config with known add exposure?
   - Recommendation: Test on MAX_PROFIT configs plus one "stress test" config (ML=4, MTP=unlimited) that deliberately has add exposure so detectors can fire. This ensures the test validates detector logic, not just an absence of adds.

2. **How should Level 3 re-engagement interact with the forced_flat cooldown when TDS is disabled mid-run?**
   - What we know: Cooldown period is tracked in bars. If `can_reengage()` checks feature thresholds, there's a chicken-and-egg problem: features are computed at each bar but the loop skips bars during cooldown.
   - Recommendation: Cooldown check should be pure bar-count-based (not feature-dependent) with an optional feature check as a secondary gate. Primary: `cooldown_remaining <= 0`. Secondary: `threat_level < 1` (computed from features on the re-engagement bar).

3. **Should TDS `pnl_saved_estimate` go into the cycle record or only in aggregate summary?**
   - What we know: Per-cycle TDS intervention can be tracked but requires a shadow simulation (what would have happened without TDS intervention in that cycle).
   - Recommendation: Keep `pnl_saved_estimate` as aggregate only (sum of worst-case losses avoided). Per-cycle shadow simulation adds significant complexity and is not required by the spec.

---

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.0.2 |
| Config file | none (no pytest.ini — tests run from working directory) |
| Quick run command | `cd shared/archetypes/rotational && python -m pytest test_trend_defense.py -q` |
| Full suite command | `cd shared/archetypes/rotational && python -m pytest -q` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| ROT-RES-04 | TrendDefenseSystem class instantiates with config and bar stats | unit | `pytest test_trend_defense.py::test_tds_init -x` | Wave 0 |
| ROT-RES-04 | Detector 1: Retracement quality fires when depths declining | unit | `pytest test_trend_defense.py::test_detector_retracement_quality -x` | Wave 0 |
| ROT-RES-04 | Detector 2: Velocity monitor fires on rapid level escalation | unit | `pytest test_trend_defense.py::test_detector_velocity_monitor -x` | Wave 0 |
| ROT-RES-04 | Detector 3: Consecutive add counter fires on N adds without retrace | unit | `pytest test_trend_defense.py::test_detector_consecutive_adds -x` | Wave 0 |
| ROT-RES-04 | Detector 4: Drawdown budget fires when cycle unrealized exceeds limit | unit | `pytest test_trend_defense.py::test_detector_drawdown_budget -x` | Wave 0 |
| ROT-RES-04 | Detector 5: Trend precursor composite fires on 2+ aligned signals | unit | `pytest test_trend_defense.py::test_detector_trend_precursor -x` | Wave 0 |
| ROT-RES-04 | Level 1 response: step widens, MaxLevels reduces by 1 | unit | `pytest test_trend_defense.py::test_level1_response -x` | Wave 0 |
| ROT-RES-04 | Level 2 response: adds refused, de-escalation begins | unit | `pytest test_trend_defense.py::test_level2_response -x` | Wave 0 |
| ROT-RES-04 | Level 3 response: forced flatten, cooldown period entered | unit | `pytest test_trend_defense.py::test_level3_response -x` | Wave 0 |
| ROT-RES-04 | Level 3 re-engagement: cooldown + threat < L1 required | unit | `pytest test_trend_defense.py::test_level3_reengage -x` | Wave 0 |
| ROT-RES-04 | TDS integrated into RotationalSimulator: cycle records have trend_defense_level_max | integration | `pytest test_trend_defense.py::test_simulator_integration -x` | Wave 0 |
| ROT-RES-04 | TDS WITH vs WITHOUT: worst_cycle_dd improves on synthetic straight-line data | integration | `pytest test_trend_defense.py::test_survival_metrics_improvement -x` | Wave 0 |
| ROT-RES-04 | Bar-type parameter conversion: 10sec config produces 5x more bars per cooldown than vol/tick | unit | `pytest test_trend_defense.py::test_bar_type_param_conversion -x` | Wave 0 |
| ROT-RES-04 | TDS summary metrics match expected l1/l2/l3 trigger counts | unit | `pytest test_trend_defense.py::test_summary_metrics -x` | Wave 0 |
| ROT-RES-04 | H33/H38/H40 features consumed by TDS when active_filters includes them | integration | `pytest test_trend_defense.py::test_hypothesis_feedins -x` | Wave 0 |
| ROT-RES-04 | H36/H39 dynamic features computed inside loop and available to TDS | integration | `pytest test_trend_defense.py::test_dynamic_feature_wiring -x` | Wave 0 |
| ROT-RES-04 | Determinism: identical config + data → identical results with TDS enabled | unit | `pytest test_trend_defense.py::test_determinism_tds -x` | Wave 0 |
| ROT-RES-04 | TDS disabled (enabled=false) produces identical results to no-TDS baseline | unit | `pytest test_trend_defense.py::test_tds_disabled_passthrough -x` | Wave 0 |

### Sampling Rate
- **Per task commit:** `cd shared/archetypes/rotational && python -m pytest test_trend_defense.py -q`
- **Per wave merge:** `cd shared/archetypes/rotational && python -m pytest -q`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `shared/archetypes/rotational/test_trend_defense.py` — all 18 test cases above
- [ ] `shared/archetypes/rotational/trend_defense.py` — TDS implementation (the deliverable itself)
- [ ] `shared/archetypes/rotational/tds_results/` — output directory (create empty with .gitkeep)

*(Existing test files `test_rotational_simulator.py`, `test_hypothesis_screening.py`, etc. continue to pass — no regressions expected since TDS is an additive feature behind `enabled=false` default.)*

---

## Sources

### Primary (HIGH confidence)
- `xtra/Rotational_Archetype_Spec.md` — Section 4 (TDS complete design), Section 6.2 (simulation loop pseudocode), Section 7.2 (extended metrics), Section 8.1 (file list)
- `shared/archetypes/rotational/rotational_simulator.py` — existing simulator state machine, cycle record schema, integration seam
- `shared/archetypes/rotational/feature_engine.py` — existing H33/H35/H38/H40 implementations, `_DYNAMIC_FEATURE_COLUMNS` registry

### Secondary (MEDIUM confidence)
- `shared/archetypes/rotational/sizing_sweep_results/sizing_sweep_report.md` — baseline configs and the "martingale is net negative" finding that affects TDS priority
- `shared/archetypes/rotational/screening_results/phase1b_classification.md` — Phase 1b results context
- `shared/archetypes/rotational/rotational_hypothesis_config.json` — existing TDS config schema

### Tertiary (LOW confidence)
- None — all findings verified against primary sources in the repository.

---

## Metadata

**Confidence breakdown:**
- TDS design (5 detectors + 3 levels): HIGH — spec Section 4 is fully specified
- Integration points: HIGH — simulator code read directly, seams identified by line number
- Parameter starting values: MEDIUM — spec gives ranges; exact sweep bounds are estimates
- Bar-type cadence ratios (5x factor): MEDIUM — derived from bar counts in sizing sweep (322 combos x 3 bar types) but exact median bar durations not computed directly from data files
- Test coverage: HIGH — all behaviors specified, test names match spec requirements

**Research date:** 2026-03-16
**Valid until:** 2026-04-16 (spec unlikely to change; simulator code is the constraint)
