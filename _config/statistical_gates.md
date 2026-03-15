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

---

## [archetype: rotational] — Cycle-Level Verdict Thresholds

Martingale strategies inflate PF and win rate by construction (averaging converts losers to
small winners while hiding tail risk). All metrics below are computed on CYCLES, not trades.
A cycle = reversal-to-reversal including all adds. Extended metrics are in col 25 (JSON).

### Primary Gates
| Metric | PASS | CONDITIONAL | FAIL |
|--------|------|-------------|------|
| Cycle PF (P1a) | >= 1.5 | 1.2 – 1.49 | < 1.2 |
| Cycles per period | >= 30 | 15 – 29 | < 15 |

### Survival Gates
| Metric | PASS | FAIL |
|--------|------|------|
| Worst-cycle DD | < 2× avg ATR × max position size | exceeds limit |
| Max-level exposure % | < 15% of total bars | >= 15% |
| Max consecutive losing cycles | <= 5 | > 5 |

### Robustness Gates (martingale-specific — catch illusions standard metrics miss)
| Metric | PASS | FAIL | Why |
|--------|------|------|-----|
| Slippage sensitivity | PF at +0.50 tick >= 1.2 | PF collapses below 1.2 | Fragile edge that vanishes under realistic execution |
| Breakeven removal count | >= 10% of total cycles | < 10% | Profit concentrated in too few outlier cycles |
| Asymmetry ratio | < 5:1 (avg loser / avg winner) | >= 5:1 | High win rate masking outsized losing cycles |
| Cost as % of gross profit | < 35% | >= 35% | Trading too frequently for the edge captured |

### Replication Gate (Pipeline Rule 4)
| Metric | PASS | WEAK_REPLICATION | FAIL |
|--------|------|------------------|------|
| Cycle PF (P1b) | >= 1.3 | 1.0 – 1.29 | < 1.0 |

### Verdict Categories
- **PASS:** All four tiers satisfied
- **CONDITIONAL:** Primary gates pass but one or more survival/robustness gates fail, or cycles < 30
- **WEAK_REPLICATION:** Primary + survival + robustness pass but P1b cycle PF < 1.3
- **FAIL:** Primary gates not met OR worst-cycle DD exceeds hard limit OR asymmetry ratio > 10:1

*Thresholds are initial estimates. Calibrate after baseline runs in Phase B.*

### Extended Metrics Schema (col 25 JSON)
See xtra/Rotational_Archetype_Spec.md Section 7.2 for full schema.
8 metric categories: cycle_core, capital_exposure, cost_analysis, profit_concentration,
heat, action_efficiency, equity_curve, session_level. Plus: dollar_weighted,
directional_split, trend_defense, bar_type.
