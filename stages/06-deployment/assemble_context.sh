#!/bin/bash
# Usage: bash assemble_context.sh <strategy_id>
# Prints assembled context package to stdout.
# Example: bash assemble_context.sh {strategy_id} | tee context_package.md

STRATEGY_ID=${1:?Usage: assemble_context.sh <strategy_id>}
ROOT="$(git rev-parse --show-toplevel)"

echo "# ACSIL Generation Context Package"
echo "# Strategy: $STRATEGY_ID | $(date)"
echo ""
echo "## Verdict"
cat "$ROOT/stages/05-assessment/output/verdict_report.json"
echo ""
echo "## Frozen Parameters"
cat "$ROOT/stages/04-backtest/output/frozen_params.json"
echo ""
echo "## Scoring Model"
# Scoring model path is in frozen_params.json under scoring_model_path
SCORING_MODEL=$(python3 -c "import json; print(json.load(open('$ROOT/stages/04-backtest/output/frozen_params.json'))['scoring_model_path'])")
cat "$ROOT/$SCORING_MODEL"
echo ""
echo "## Features Used"
cat "$ROOT/shared/feature_definitions.md"
echo ""
echo "## Generation Instructions"
cat "$ROOT/stages/06-deployment/references/context_package_spec.md"
echo ""
echo "## Structural Reference"
echo "# Read this file for ACSIL API patterns, entry logic, and data-feed conventions."
echo "# Preserve entry logic. Replace exit params with frozen_params.json values only."
# Archetype read at runtime from frozen_params.json — NOT hardcoded (Pitfall 6)
ARCHETYPE=$(python3 -c "import json; print(json.load(open('$ROOT/stages/04-backtest/output/frozen_params.json'))['archetype']['name'])")
STRUCT_REF=$(grep -A 20 "^## $ARCHETYPE" "$ROOT/stages/03-hypothesis/references/strategy_archetypes.md" | grep "^- Structural reference:" | head -1 | sed 's/.*: //')
cat "$ROOT/$STRUCT_REF"
