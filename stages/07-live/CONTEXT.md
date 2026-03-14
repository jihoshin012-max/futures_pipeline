---
last_reviewed: 2026-03-13
reviewed_by: Ji
---
# Stage 07: Live Performance Monitor
## YOUR TASK: Compare live trades to backtest expectations. Monitor only.
## CONSTRAINT: No autoresearch. No code generation. No backtest runs.

| | |
|---|---|
| **Inputs** | data/paper_trades.csv (manual export from live trading system) |
| **Baseline** | 05-assessment/output/verdict_report.json (backtest expectations) |
| **Outputs** | output/live_assessment.md (periodic), output/drift_report.md (rolling) |
| **Human checkpoint** | Monthly review of live_assessment.md; immediate if any trigger fires |

## REVIEW TRIGGERS
See `triggers/review_triggers.md` for full thresholds and escalation rules.
Check after every trade log update. If any trigger fires, create MANUAL_NOTE in audit_log.md first.

## LIVE DATA PROMOTION
After 200+ trades: evaluate for IS promotion via PERIOD_CONFIG_CHANGED audit entry.
This is a human decision. You flag it; human decides.
