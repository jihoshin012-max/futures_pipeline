# Segmentation Comparison (v3.2)
Generated: 2026-03-24T14:11:44.216179
Combined P2 results. Baseline PF anchor: 1.3396

## Within-Segmentation (best group PF @3t)

| Seg | A-Cal | A-Eq | B-ZScore | Best |
|-----|-------|------|----------|------|
| seg1 | 1.6509 | 6.4170 | 2.4941 | A-Eq |
| seg2 | 1.9767 | 3.5465 | 4.3164 | B-ZScore |
| seg3 | 1.6640 | 4.4664 | 2.4629 | A-Eq |
| seg4 | 1.7778 | 4.3441 | 2.6196 | A-Eq |
| seg5 | 0.0000 | 0.0000 | 3.2591 | B-ZScore |

## Across-Segmentation

| Metric | Seg1 | Seg2 | Seg3 | Seg4 | Seg5 |
|--------|------|------|------|------|------|
| total_trades | 3109 | 2583 | 3313 | 3290 | 1066 |
| combined_pf | 1.8689 | 1.9002 | 1.7667 | 1.8022 | 2.5032 |
| best_group_pf | 6.4170 | 4.3164 | 4.4664 | 4.3441 | 3.2591 |
| best_group_pdd | 22.4819 | 43.8939 | 12.9919 | 16.0407 | 2.2591 |
| sharpe | 0.2356 | 0.2846 | 0.2557 | 0.2633 | 0.3552 |
| max_dd | 2831 | 2831 | 3102 | 2831 | 953 |
| n_pass | 4 | 8 | 7 | 7 | 3 |
| vs_base | 0.5293 | 0.5606 | 0.4271 | 0.4626 | 1.1636 |