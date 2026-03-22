# Segmentation Comparison (v3.1)
Generated: 2026-03-22T01:15:49.959559
Combined P2 results. Baseline PF anchor: 0.8984

## Within-Segmentation (best group PF @3t)

| Seg | A-Cal | A-Eq | B-ZScore | Best |
|-----|-------|------|----------|------|
| seg1 | 3.0698 | 1.5936 | 1.1021 | A-Cal |
| seg2 | 3.0698 | 1.5936 | 1.1021 | A-Cal |
| seg3 | 5.0964 | 1.6766 | 1.2861 | A-Cal |
| seg4 | 3.7315 | 1.6996 | 1.4010 | A-Cal |
| seg5 | 1.1914 | 1.1914 | 1.1914 | A-Cal |

## Across-Segmentation

| Metric | Seg1 | Seg2 | Seg3 | Seg4 | Seg5 |
|--------|------|------|------|------|------|
| total_trades | 3574 | 3392 | 3731 | 3812 | 3666 |
| combined_pf | 1.0592 | 1.0957 | 1.0815 | 1.1221 | 1.1066 |
| best_group_pf | 3.0698 | 3.0698 | 5.0964 | 3.7315 | 1.1914 |
| best_group_pdd | 6.6946 | 6.6946 | 16.5130 | 6.9845 | 4.9875 |
| sharpe | 0.0243 | 0.0396 | 0.0335 | 0.0497 | 0.0433 |
| max_dd | 9301 | 7943 | 9012 | 8701 | 3902 |
| n_pass | 2 | 2 | 3 | 4 | 0 |
| vs_base | 0.1608 | 0.1973 | 0.1831 | 0.2237 | 0.2082 |