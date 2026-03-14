# Stage 04 Parameter Optimization
EDIT: exit_params.json only. DO NOT touch backtest_engine.py.
METRIC: pf
KEEP RULE: 0.05
BUDGET: 500

## Current search direction
Random perturbation around current best. Phase 5 validation mode.

## Prior best
[Driver updates from results.tsv automatically]

## Data notes
- Rows 1-51 in results.tsv use git HEAD hash as run_id (pre-fix, non-unique)
- Rows 52+ use sha1(archetype+timestamp+n)[:7] — unique per experiment
- hypothesis_name populated from promoted_hypothesis.json (archetype fallback if file absent)
- Kept experiment rows include git:{hash} in notes column for commit traceability
