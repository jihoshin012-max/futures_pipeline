# Stage 03 Hypothesis Generation — Program
# Max 30 lines. Machine-readable fields must stay at top.

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
