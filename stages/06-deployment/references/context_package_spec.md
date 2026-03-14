# ACSIL Generation Context Package Spec
last_reviewed: 2026-03-13
# This is the information contract between the pipeline and Claude Code.
# assemble_context.sh reads this spec and builds the prompt from it.

## Required sections (in order)

### 1. Strategy identity
- hypothesis_id (from audit_log.md HYPOTHESIS_PROMOTED entry)
- archetype (from strategy_archetypes.md)
- verdict + period (from 05-assessment/output/verdict_report.json)

### 2. Frozen Parameters (copy verbatim)
- 04-backtest/output/frozen_params.json — all exit params, exactly as optimized
- shared/scoring_models/{model_id}.json — scoring weights and thresholds

### 3. Features used
- Relevant entries from shared/feature_definitions.md
- Only features active in this strategy — not the full list

### 4. Structural reference
- Point Claude Code at archetype structural reference file (from strategy_archetypes.md)
- Read structural_reference path from strategy_archetypes.md for the active archetype
- Instruction: preserve entry logic; replace exit params with frozen_params.json values only
- Example: stages/06-deployment/references/{strategy_id}_reference.cpp

### 5. Output instructions
- Output folder: stages/06-deployment/output/{strategy_id}/
- Determine number of .cpp files needed (1 study or multiple coordinated studies)
- No magic numbers — every param value traces to frozen_params.json
- Each file must be compile-ready: no placeholders, no TODOs

## What NOT to include
- Experiment history or rejected hypotheses
- P1/P2 trade logs
- IS/OOS period config (not relevant to code structure)
