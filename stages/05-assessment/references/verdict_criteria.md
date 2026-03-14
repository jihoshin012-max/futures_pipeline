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
