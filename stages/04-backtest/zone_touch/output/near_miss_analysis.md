# Near-Miss Touches — A-Cal Threshold Sensitivity
Generated: 2026-03-22T02:38:34.059082
A-Cal threshold: 16.66

## Counts
| Period | Near-Miss (T-2 to T) | Above Threshold |
|--------|---------------------|-----------------|
| P1 (edges) | 266 | 200 |
| P2 (edges) | 269 | 187 |

## Threshold Sensitivity Simulation (winner's frozen exits: seg3_ModeB)
Using seg3_A-Cal/ModeB exit params (stop=190, target=80, time_cap=120)

| Threshold (baseline) (>=16.66) | 58 trades | PF@3t=5.096 | WR=91.4% |
| Threshold - 1pt (>=15.66) | 77 trades | PF@3t=2.759 | WR=85.7% |
| Threshold - 2pt (>=14.66) | 121 trades | PF@3t=1.924 | WR=79.3% |

## Cliff vs Slope Assessment
If PF degrades sharply with -1pt: CLIFF (threshold is load-bearing).
If PF degrades gradually: SLOPE (threshold has margin).