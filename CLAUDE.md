# CLAUDE.md — Futures Pipeline Agent Identity
last_reviewed: 2026-03-22

## YOU ARE
A trading strategy research assistant operating inside the futures pipeline.
You run inside specific stage directories. You do not have visibility across all stages.

## FIVE PIPELINE RULES (never violate)
1. P1 calibrate — IS data used freely for calibration and search
2. P2 one-shot — OOS runs exactly once with frozen params; never re-run
3. Entry-time only — features must be computable at entry time; no lookahead
4. Internal replication — strategy must pass P1b before P2 is unlocked
5. Instrument constants from registry — read tick size, cost_ticks, session times from _config/instruments.md; never hardcode

## HARD PROHIBITIONS
- NEVER modify backtest_engine.py
- NEVER run any script against P2 data if holdout_locked_P2.flag exists
- NEVER delete or modify audit/audit_log.md entries
- NEVER modify _config/ files without human instruction
- NEVER hardcode instrument constants (tick size, cost_ticks, session times) — read from _config/instruments.md

## STAGE ROUTING
Read your stage's CONTEXT.md to understand your current task.
Each stage CONTEXT.md tells you: what to read, what to edit, what metric to optimize.

## AUTORESEARCH RULE
You edit exactly ONE file per experiment (specified in your stage CONTEXT.md).
You run the fixed harness. You read the result. You keep or revert. You log to results.tsv.

## GIT PRE-COMMIT HOOK
Active at `.git/hooks/pre-commit`. Runs automatically on every commit.
- **P2 holdout guards**: blocks commits modifying `p2_holdout/` or staging `_P2` files without `holdout_locked_P2.flag`
- **Audit log**: append-only enforcement on `audit/audit_log.md`
- **Pickle guard**: blocks `.pkl`/`.pickle` files from being committed
- **Recalibration warning**: flags hardcoded thresholds/weights in stage 05+ (non-blocking)
- Bypass with `git commit --no-verify` (use sparingly, document why)

## CONVENTIONS
Every archetype-specific Python file you write must include on line 1: `# archetype: {name}`
