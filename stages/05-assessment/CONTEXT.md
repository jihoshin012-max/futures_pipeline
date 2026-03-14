---
last_reviewed: 2026-03-13
reviewed_by: Ji
---
# Stage 05: Statistical Assessment
## YOUR TASK: Compute metrics and render verdict. Deterministic — no exploration.
## CONSTRAINT: You do not modify backtest outputs. You read them and compute.

| | |
|---|---|
| **Inputs** | 04-backtest/output/trade_log.csv, data_manifest.json |
| **Process** | Compute PF, MWU, permutation test, percentile rank; apply adjusted p-value gate |
| **Outputs** | verdict_report.md, verdict_report.json, statistical_summary.md, feedback_to_hypothesis.md |
| **Human checkpoint** | None — deterministic. Human reads verdict_report.md and decides whether to promote. |

## MULTIPLE TESTING (Gap A — local repeat)
Read n_prior_tests from results_master.tsv for this archetype.
Apply adjusted p-value gate from _config/statistical_gates.md (not the baseline).
If n_prior_tests > 200: verdict is automatically NO regardless of p-value.

## statistical_summary.md OUTPUT SPEC
Compute and report all of these. Verdict gates apply to the top block only.
Sharpe is a REPORTING METRIC — informational, not a verdict gate.

### Verdict metrics (gates apply)
- profit_factor, n_trades, win_rate
- mwu_p, permutation_p, percentile_rank
- max_drawdown_ticks, avg_winner_ticks, drawdown_multiple (DD / avg winner)

### Reporting metrics (logged, not gated)
- sharpe_ratio: (mean_trade_pnl / std_trade_pnl) * sqrt(n_trades)
  Note: trade-level Sharpe — no annualization, no capital assumption
- avg_loser_ticks, avg_winner_ticks, win_loss_ratio
- longest_losing_streak, longest_flat_bars
- regime_breakdown: PF per regime bucket (if n_trades >= 20 per bucket)

### Sharpe implementation note
Use trade-level Sharpe only. Do NOT annualize. Do NOT assume account size.
Formula: mean(trade_pnl_ticks) / std(trade_pnl_ticks) * sqrt(n_trades)
This is comparable across strategies on the same instrument without capital assumptions.
Flag as unreliable if n_trades < 30.
