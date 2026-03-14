# Review Triggers
last_reviewed: 2026-03-13
# Conditions that force a pipeline review. Check after every trade log update.
# Do not change thresholds without a MANUAL_NOTE audit entry explaining the reason.

## Active Triggers

| Trigger | Threshold | Action |
|---------|-----------|--------|
| Live PF vs backtest PF | Diverges > 40% after 50+ trades | Review hypothesis; consider retiring |
| Consecutive stop-outs | 8 or more | Pause trading; review signal filter and entry conditions |
| Max drawdown exceeded | > 2x backtest DD | Pause trading immediately |
| Trade count below expected | < 5 signals/month | Check signal detection alignment and live system config |

## Escalation
If any trigger fires: create MANUAL_NOTE in audit/audit_log.md before doing anything else.
This creates a timestamped record before any investigation changes the system state.

## Promotion Trigger (not a problem — a milestone)
After 200+ live trades: flag for IS promotion evaluation via PERIOD_CONFIG_CHANGED audit entry.
Human decides whether to promote. Stage 07 flags it; pipeline does not act automatically.
