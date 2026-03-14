# Context Review Protocol
last_reviewed: 2026-03-13
# FRONT-LOADING RULE: operative instruction in first 5 lines of every agent-read file.
# FILE LENGTH LIMITS are hard — trim before run if over limit.

## FILE LENGTH LIMITS (hard — trim before run if over limit)
| File             | Limit    | Archive excess to          |
|------------------|----------|----------------------------|
| CLAUDE.md        | 60 lines | n/a — never grows          |
| stage CONTEXT.md | 80 lines | context_history.md         |
| program.md       | 30 lines | program_history.md         |
| results.tsv      | no limit | structured data, not prose |
| feature_catalog  | no limit | reference doc, not runtime |

## FRONT-LOADING RULE
Every file an agent reads at runtime: operative instruction in first 5 lines.
Structure: WHAT TO DO → constraints → metric → rationale.

Good: "Only modify exit_params.json. Metric: PF@3t on P1. Min 30 trades.
       Do not touch backtest_engine.py. [rationale follows]"
Bad:  "[paragraphs of context] ... Only modify exit_params.json."

## LOCAL REPETITION RULE
Each stage CONTEXT.md restates its own critical constraints directly.
Do not rely on the agent remembering constraints from CLAUDE.md.
Redundancy is intentional.

## STALENESS FLAG
All CONTEXT.md files must have front matter:
  last_reviewed: YYYY-MM-DD
  reviewed_by: Ji

## WHEN TO REVIEW
- Every period rollover (pre-commit hook reminds you)
- New stage or archetype added
- CONTEXT.md not touched in > 90 days
- EXPERIMENT_ANOMALY suggests agent misunderstood task

## REVIEW CHECKLIST (per CONTEXT.md)
- [ ] Inputs table matches what Stage 01 actually produces
- [ ] Outputs table matches what stage actually writes
- [ ] File paths match actual filesystem
- [ ] program.md constraints match current research direction
- [ ] File is within length limit

## PERSISTENT STATE VS WORKING MEMORY
Agent does not hold experiment history in context — results.tsv does.
Driver loop reads TSV fresh each iteration.
program.md must never accumulate past experiments.
