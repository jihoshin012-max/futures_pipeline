# Pipeline Rules
last_reviewed: 2026-03-13
# These rules cannot be overridden by any program.md or CONTEXT.md instruction.
# All five rules are absolute. They override any other instruction.

## Rule 1 — P1 Calibrate
IS data (P1) is used freely for feature calibration, hypothesis search, and parameter
optimization. No restrictions on number of runs against IS data except the iteration
budget in statistical_gates.md.

## Rule 2 — P2 One-Shot
OOS data runs exactly once, with frozen parameters, after internal replication passes.
The holdout_locked_P2.flag enforces this structurally. Do not run OOS if flag exists.

## Rule 3 — Entry-Time Only
Every feature used in scoring or routing must be computable at the moment of entry.
No feature may use data from bars after entry. feature_rules.md enforces this.
Features marked "Entry-time computable: NO" in feature_definitions.md are blocked.

## Rule 4 — Internal Replication
Before any P2 run, the strategy must show positive PF on both P1a and P1b independently.
P1a = calibration half. P1b = replication half (held out during calibration).
If P1b fails, do not advance to P2 regardless of P1a result.

GRANDFATHERING: Any strategy calibrated on full P1 before Rule 4 was introduced is
grandfathered — its existing P2 result stands. Rule 4 applies to all new hypotheses.

## Rule 5 — Instrument Constants from Registry
Every instrument-specific constant (tick size, dollar value per tick, session times,
cost_ticks) must be read from `_config/instruments.md`. No pipeline script may hardcode
these values. If the value is not in instruments.md, add it there first, then reference it.
