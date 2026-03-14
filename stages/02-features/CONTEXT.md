---
last_reviewed: 2026-03-13
reviewed_by: Ji
---
# Stage 02: Feature Engineering
## YOUR TASK: Edit feature_engine.py only. Metric: predictive spread on P1.
## CONSTRAINT: Do not touch evaluate_features.py (fixed harness).

| | |
|---|---|
| **You edit** | shared/archetypes/{archetype}/feature_engine.py (one file only) |
| **Dispatcher** | autoresearch/evaluate_features.py — loads archetype evaluator, never touch |
| **Evaluator** | shared/archetypes/{archetype}/feature_evaluator.py — archetype-specific harness, never touch |
| **Metric** | Best-bin vs worst-bin predictive spread on P1 (archetype-specific — see feature_evaluator.py) |
| **Keep rule** | spread > threshold in program.md → keep; else revert |
| **Outputs** | results.tsv (every experiment), output/frozen_features.json (human-approved) |

## ARCHETYPE REFERENCES
Read program.md to identify the active archetype.
You edit: shared/archetypes/{archetype}/feature_engine.py
Do not edit feature_engine.py files belonging to other archetypes.
Read shared/archetypes/{archetype}/feature_evaluator.py to understand what data is available.

## ENTRY-TIME RULE (Rule 3 — local repeat)
Every feature you add must be computable at the moment of entry.
No feature may use data from bars after entry. Check feature_rules.md before adding.

## ITERATION BUDGET (from statistical_gates.md)
Max 300 experiments per IS period. Driver logs n_prior_tests on each row.
Stop and report to human when budget is reached.

## PROGRAM
Read autoresearch/program.md before each experiment. It steers your direction.

## AFTER HUMAN PROMOTION
When human approves features and creates output/frozen_features.json:
  cp stages/02-features/output/frozen_features.json \
     stages/03-hypothesis/references/frozen_features.json
This makes the approved feature set available to Stage 03 hypothesis agent.
