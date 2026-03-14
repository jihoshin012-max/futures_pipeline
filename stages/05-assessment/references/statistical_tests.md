# Statistical Tests
last_reviewed: 2026-03-13
# Specifications for tests Stage 05 must run. All three required for every verdict.

## Mann-Whitney U test
- Null hypothesis: live PnL distribution is not different from zero-mean
- Input: trade_pnl_ticks column from trade_log.csv
- Two-tailed. Report p-value to 4 decimal places.
- Flag as unreliable if n_trades < 20.

## Permutation test
- Method: shuffle trade outcomes 10,000 times, recompute PF each time
- Report: percentile rank of actual PF vs permuted distribution
- p-value: fraction of permuted PFs >= actual PF
- Budget: 10,000 permutations minimum

## Random percentile rank
- Compare strategy PF to 10,000 random strategies on same data
- Random strategy: random entry/exit on same bars, same trade count
- Report: percentile rank of actual PF (99th = top 1% of random)
