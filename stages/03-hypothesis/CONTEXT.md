---
last_reviewed: 2026-03-13
reviewed_by: Ji
---
# Stage 03: Hypothesis Generation
## YOUR TASK: Edit hypothesis_config.json only. Metric: P1 PF at 3t cost.
## CONSTRAINT: Do not touch hypothesis_generator.py (fixed harness).

| | |
|---|---|
| **You edit** | autoresearch/hypothesis_config.json (one file only) |
| **Fixed harness** | autoresearch/hypothesis_generator.py (calls backtest + assess internally) |
| **Metric** | P1 PF at 3t minimum cost, minimum 30 trades |
| **Keep rule** | PF improves by > 0.1 → keep; else revert |
| **Outputs** | results.tsv, output/promoted_hypotheses/ (human-approved only) |
| **Reads** | references/frozen_features.json (from Stage 02), references/prior_results.md (from Stage 05) |

## INTERNAL REPLICATION RULE (Rule 4 — local repeat)
A hypothesis can only advance to P2 after passing both P1a and P1b independently.
The generator enforces this. Do not manually advance a hypothesis that failed P1b.

## ITERATION BUDGET
Max 200 experiments per archetype per IS period.

## PROGRAM
Read autoresearch/program.md before each experiment. It steers your direction.
Read references/prior_results.md to avoid repeating failures.
