#!/bin/bash
# Watches futures-pipeline/ for changes and auto-commits with timestamp + changed files
# Run once in background: bash autocommit.sh &
# Source: Futures_Pipeline_Architecture_ICM.md lines 546-563

WATCH_DIR="$(git rev-parse --show-toplevel)"
POLL_INTERVAL=30  # seconds

while true; do
    sleep $POLL_INTERVAL
    cd "$WATCH_DIR"
    if ! git diff --quiet || ! git diff --cached --quiet || [ -n "$(git ls-files --others --exclude-standard)" ]; then
        CHANGED=$(git diff --name-only; git ls-files --others --exclude-standard)
        TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')
        git add -A
        git commit -m "auto: $TIMESTAMP | $(echo $CHANGED | tr '\n' ' ' | cut -c1-80)"
    fi
done
