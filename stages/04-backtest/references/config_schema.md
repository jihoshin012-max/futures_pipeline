---
last_reviewed: 2026-03-14
---
# Config Schema Documentation

Field-by-field reference for the backtest engine config JSON.
FIXED fields: set once, not varied during autoresearch.
CANDIDATE fields: varied per experiment in Stage 04 autoresearch.

## Top-Level Fields

| Field | Type | FIXED/CANDIDATE | Valid Range | Description |
|-------|------|-----------------|-------------|-------------|
| version | string | FIXED | "v1" | Schema version. Must be "v1". Engine rejects other values. |
| instrument | string | FIXED | "NQ", "ES", "CL" | Instrument name. Used to look up cost_ticks, tick size from _config/instruments.md. |
| touches_csv | string | FIXED | valid file path | Path to touch data CSV (ZRA_Hist format, 32 columns). P1 or P2 path set by driver. |
| bar_data | string | FIXED | valid file path | Path to bar data file (volume bar format, 10 columns). P1 or P2 path set by driver. |
| scoring_model_path | string | FIXED | valid file path | Path to JSON scoring model (weights, bin_edges). BinnedScoringAdapter reads this. |

## Archetype Block

| Field | Type | FIXED/CANDIDATE | Valid Range | Description |
|-------|------|-----------------|-------------|-------------|
| archetype.name | string | FIXED | "zone_touch" | Archetype identifier. Used to resolve archetype reference files. |
| archetype.simulator_module | string | FIXED | valid Python module name | Module loaded via importlib.import_module(). Must expose run() function. |
| archetype.scoring_adapter | string | FIXED | "BinnedScoringAdapter" | Adapter class name loaded from scoring_adapter.py. |

## Routing Block

| Field | Type | FIXED/CANDIDATE | Valid Range | Description |
|-------|------|-----------------|-------------|-------------|
| active_modes | list[string] | FIXED | subset of ["M1","M3","M4","M5"] | Modes to simulate. Touches not matching an active mode are skipped. |
| routing.score_threshold | int | FIXED | 0–100 | Minimum score for a touch to enter any mode. Touches below threshold are filtered out. |
| routing.seq_limit | int | FIXED | 1–10 | Maximum consecutive touches routed to the same mode. Prevents sequential clustering bias. |

## Per-Mode Fields (applies to M1, M3, M4, M5 blocks)

| Field | Type | FIXED/CANDIDATE | Valid Range | Description |
|-------|------|-----------------|-------------|-------------|
| stop_ticks | int | CANDIDATE | 20–300 | Initial stop distance in ticks from entry price. Fixed for life of trade unless trailed past it. |
| leg_targets | list[int] | CANDIDATE | each 10–500, 1–3 elements | Tick targets for partial exits. M1 supports 1–3 legs. M3/M4/M5 use single-leg (1 element). |
| trail_steps | list[object] | CANDIDATE | 0–6 elements (see validation rules) | Trail step array. Empty list means no trailing stop. Each step: {trigger_ticks, new_stop_ticks}. |
| time_cap_bars | int | CANDIDATE | 5–200 | Maximum bars held before forced market exit. Prevents open-ended holding. |

### trail_steps object fields

| Field | Type | Valid Range | Description |
|-------|------|-------------|-------------|
| trigger_ticks | int | 1–500 | MFE level (ticks) at which stop ratchets to new_stop_ticks. |
| new_stop_ticks | int | 0–499 | New stop distance from entry after trigger fires. 0 = breakeven (stop at entry). |

## Trail Step Validation Rules

The engine enforces these rules in `validate_config()` at load time. Any violation raises `SystemExit` before simulation begins.

1. **Step count:** 0 to 6 steps allowed (empty list = no trail).
2. **Monotonic triggers:** `trigger_ticks` must be strictly monotonically increasing across steps.
3. **Stop below trigger:** For each step, `new_stop_ticks` must be strictly less than `trigger_ticks`.
4. **Non-decreasing stops:** `new_stop_ticks` must be monotonically non-decreasing across steps (stop can only ratchet forward).
5. **Non-negative first stop:** `new_stop_ticks[0]` must be >= 0 (BE is 0; negative values not allowed).

## Notes

- Additional modes (M3, M4, M5) follow the same per-mode schema as M1.
- Config paths use forward slashes and are relative to the repo root.
- `cost_ticks` is NOT in this config — read from `_config/instruments.md` at runtime.
- `be_trigger_ticks` is NOT a field — `trail_steps[0]` with `new_stop_ticks=0` is the BE trigger.
- The engine never modifies config values — all values are treated as read-only after load.
