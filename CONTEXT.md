---
last_reviewed: 2026-03-13
reviewed_by: Ji
---
# CONTEXT.md — Pipeline Router

## CURRENT ACTIVE STAGE
→ Stage 01: Data Foundation (Pass 1 scaffold — no autoresearch yet)

## TO START WORK
1. Read CLAUDE.md (global rules)
2. Read stages/{active_stage}/CONTEXT.md (your task)
3. Read stages/{active_stage}/autoresearch/program.md (if autoresearch stage)

## STAGE STATUS
| Stage | Status | Notes |
|-------|--------|-------|
| 01-data | Active | Scaffold complete; awaiting data validation |
| 02-features | Not started | Pending Pass 2 |
| 03-hypothesis | Not started | Pending Pass 3 |
| 04-backtest | Not started | Pending Pass 2 |
| 05-assessment | Not started | |
| 06-deployment | Not started | |
| 07-live | Active — monitor only | Paper trades accumulating |

## HUMAN CHECKPOINTS (never skip)
- Before P2 run: confirm holdout_locked_P2.flag does NOT exist
- Before hypothesis promotion: review results.tsv top 3–5 manually
- Before deployment: compile, verify on replay, confirm params match frozen_params.json
