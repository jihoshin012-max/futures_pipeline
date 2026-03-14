---
last_reviewed: 2026-03-13
reviewed_by: Ji
---
# Stage 04: Backtest Simulation
## YOUR TASK: Edit exit params JSON only. Metric: P1 PF at 3t, min 30 trades.
## CONSTRAINT: Do NOT edit backtest_engine.py. It is a fixed engine.

| | |
|---|---|
| **You edit** | autoresearch/current_best/exit_params.json (one file only) |
| **Fixed engine** | autoresearch/backtest_engine.py — NEVER MODIFY |
| **Call signature** | python backtest_engine.py --config params.json --output result.json |
| **Metric** | PF at 3t on P1, minimum 30 trades |
| **Keep rule** | PF improves by > 0.05 → keep; else revert |

## ARCHETYPE REFERENCES
Read program.md to identify the active archetype.
All archetype-specific rules are in: shared/archetypes/{archetype_name}/
For {archetype}: shared/archetypes/{archetype}/simulation_rules.md
For {archetype}: shared/archetypes/{archetype}/exit_templates.md
Read these files before proposing any param changes.
Do not apply rules from a different archetype's folder.

## P2 HOLDOUT RULE (Rule 2 — local repeat)
If p2_holdout/holdout_locked_P2.flag exists: STOP. Do not run any backtest against P2.
P2 runs exactly once, with frozen params, after human approval.

## ITERATION BUDGET
Max 500 experiments per archetype per IS period.
