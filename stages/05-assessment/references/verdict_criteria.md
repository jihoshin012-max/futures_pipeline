# Verdict Criteria
last_reviewed: 2026-03-13
# Stage 05 reads this to determine Yes / Conditional / No.
# Source of truth: _config/statistical_gates.md. This file is a local copy for agent access.

## Verdict logic (all gates must pass for the verdict to hold)
YES: PF >= 2.5 AND trades >= 50 AND MWU p < 0.05 AND perm p < 0.05 AND pctile >= 99 AND dd_multiple < 3
CONDITIONAL: PF >= 1.5 AND trades >= 30 AND MWU p < 0.10 AND perm p < 0.10 AND pctile >= 95 AND dd_multiple < 5
NO: anything below Conditional thresholds, OR n_prior_tests > 200, OR replication_pass == false

## Drawdown gate
dd_multiple = max_drawdown_ticks / avg_winner_ticks
Compute from trade_log.csv at assessment time. Do not use absolute tick values.

## Multiple testing adjustment
Read n_prior_tests from results_master.tsv for this archetype.
Apply Bonferroni-adjusted MWU threshold from _config/statistical_gates.md.

| n_prior_tests | MWU p threshold |
|---------------|-----------------|
| <= 10 | < 0.05 (standard) |
| 11 - 50 | < 0.02 (tightened) |
| 51 - 200 | < 0.01 (strict) |
| > 200 | Do not advance — budget exhausted |

## [archetype: rotational] — Cycle-Level Verdicts

All metrics computed on CYCLES (not trades). See _config/statistical_gates.md for full thresholds.

PASS: Cycle PF >= 1.5 AND cycles >= 30 AND all survival gates AND all robustness gates AND P1b PF >= 1.3
CONDITIONAL: Cycle PF >= 1.2 AND (survival or robustness gate failure, or cycles 15-29)
WEAK_REPLICATION: All gates pass except P1b cycle PF (1.0-1.29)
FAIL: Cycle PF < 1.2 OR worst-cycle DD exceeds limit OR asymmetry > 10:1

Robustness gates (martingale-specific): slippage sensitivity, breakeven removal, asymmetry ratio, cost drag.
Extended metrics in col 25 (JSON) — parsed by assess.py for rotational verdict logic.
