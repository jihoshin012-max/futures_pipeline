# Statistical Gates
last_reviewed: 2026-03-13
# These gates are enforced by Stage 05. Do not bypass.
# Mandatory reading before any autoresearch run — multiple testing controls apply.

## Baseline Verdict Thresholds
| Metric          | Yes       | Conditional   | No       |
|-----------------|-----------|---------------|----------|
| Profit Factor   | >= 2.5    | 1.5 – 2.49    | < 1.5    |
| Min trades      | >= 50     | 30 – 49       | < 30     |
| MWU p-value     | < 0.05    | < 0.10        | >= 0.10  |
| Permutation p   | < 0.05    | < 0.10        | >= 0.10  |
| Percentile rank | >= 99th   | 95th – 98th   | < 95th   |
| Max drawdown    | < 3x avg winner | 3x – 5x avg winner | > 5x avg winner |

## Drawdown Gate Notes
- Expressed as a multiple of average winning trade (ticks) — no capital assumption needed
- avg_winner computed from trade_log.csv at assessment time
- Rationale: a strategy with PF 3.0 but DD 20x average winner is unliveable regardless of PF
- Do not use absolute tick values — these would need updating as strategy params change

## Multiple Testing Controls (mandatory before autoresearch)

### Iteration Budgets (per archetype per IS period)
| Stage          | Max P1 iterations | Action at limit                          |
|----------------|-------------------|------------------------------------------|
| 02-features    | 300               | Freeze feature set or retire candidates  |
| 03-hypothesis  | 200               | Advance best to P2 or retire archetype   |
| 04-backtest    | 500               | Freeze best params or retire             |

### Bonferroni-Adjusted P-value Gates (Stage 05 reads n_prior_tests from results_master.tsv)
| n_prior_tests for archetype | MWU p threshold         |
|-----------------------------|-------------------------|
| <= 10                       | < 0.05 (standard)       |
| 11 – 50                     | < 0.02 (tightened)      |
| 51 – 200                    | < 0.01 (strict)         |
| > 200                       | Do not advance — budget exhausted |

## n_prior_tests Implementation
Written by the autoresearch driver loop — NOT by a git hook.
Driver counts rows in results.tsv for the current archetype before appending each new row.
Stage 05 reads n_prior_tests from results_master.tsv when computing verdict.
