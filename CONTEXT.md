---
last_reviewed: 2026-03-22
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
| 01-data | Complete | Data validated; zone_prep outputs ready; HMM regime labels generated |
| 02-features | Complete (zone_touch) | Feature engine + evaluator built; features frozen |
| 03-hypothesis | Complete (zone_touch) | Hypothesis configs generated; P1b replication passed |
| 04-backtest | Complete (zone_touch), Active (rotational) | Zone touch: P2 holdout run, exit sweeps done. Rotational: phase1-2 sweeps done, P2a validated |
| 05-assessment | Active (rotational) | P2a validation run with cycle logs; zone touch verdict produced |
| 06-deployment | Scaffolded | assemble_context.sh ready; awaiting promoted strategy |
| 07-live | Active — monitor only | Paper trades accumulating |

## HUMAN CHECKPOINTS (never skip)
- Before P2 run: confirm holdout_locked_P2.flag does NOT exist
- Before hypothesis promotion: review results.tsv top 3–5 manually
- Before deployment: compile, verify on replay, confirm params match frozen_params.json
