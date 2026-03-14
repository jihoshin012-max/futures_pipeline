#!/bin/bash
# Usage: bash audit_entry.sh <event_type>
# event_type: promote | deploy | note | fill <line_number>
# Appends a templated entry to audit/audit_log.md or fills a TODO placeholder

AUDIT_LOG="$(git rev-parse --show-toplevel)/audit/audit_log.md"
TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')

case "$1" in
  promote)
    echo "hypothesis_id:"
    read HYP_ID
    echo "pf_p1 (from results.tsv):"
    read PF
    echo "n_trades_p1:"
    read N
    echo "reason (1-2 sentences):"
    read REASON
    echo "alternatives_considered:"
    read ALT
    cat >> "$AUDIT_LOG" << EOF

## $TIMESTAMP | HYPOTHESIS_PROMOTED
- hypothesis_id: $HYP_ID
- pf_p1: $PF
- n_trades_p1: $N
- reason: $REASON
- alternatives_considered: $ALT
- human: $(git config user.name)
EOF
    echo "Entry appended to audit_log.md"
    ;;

  deploy)
    echo "hypothesis_id:"
    read HYP_ID
    echo "note (alignment checks, replay verification):"
    read NOTE
    cat >> "$AUDIT_LOG" << EOF

## $TIMESTAMP | DEPLOYMENT_APPROVED
- hypothesis_id: $HYP_ID
- output_commit: $(git rev-parse --short HEAD)
- checklist_completed: YES
- note: $NOTE
- human: $(git config user.name)
EOF
    echo "Entry appended to audit_log.md"
    ;;

  note)
    echo "subject:"
    read SUBJECT
    echo "detail:"
    read DETAIL
    cat >> "$AUDIT_LOG" << EOF

## $TIMESTAMP | MANUAL_NOTE
- subject: $SUBJECT
- detail: $DETAIL
- human: $(git config user.name)
EOF
    echo "Entry appended to audit_log.md"
    ;;

  fill)
    # Open audit_log.md at first TODO line in editor
    TODO_LINE=$(grep -n "# TODO" "$AUDIT_LOG" | head -1 | cut -d: -f1)
    if [ -z "$TODO_LINE" ]; then
      echo "No TODO placeholders found in audit_log.md"
    else
      ${EDITOR:-nano} +"$TODO_LINE" "$AUDIT_LOG"
    fi
    ;;

  *)
    echo "Usage: bash audit_entry.sh <promote|deploy|note|fill>"
    ;;
esac
