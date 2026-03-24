# Verdict Report (v3.2)
Generated: 2026-03-24T14:11:44.216578
Baseline PF anchor: 1.3396
All parameters frozen from P1. P2 tested one-shot.

## Verdict Matrix

| Seg | Model | Group | P2 Trades | PF@4t | MWU p | Perm p | Rand %ile | P2a PF | P2b PF | Verdict |
|-----|-------|-------|-----------|-------|-------|--------|-----------|--------|--------|---------|
| B-only | B-ZScore | BOnly | 669 | 2.343 | 0.000 | 0.011 | 99.3 | 2.0536 | 2.6548 | Conditional |
| seg1 | A-Cal | ModeA | 1183 | 1.619 | 0.000 | 0.031 | 97.3 | 1.6654 | 1.6574 | Conditional |
| seg1 | A-Cal | ModeB | 63 | 0.657 | 0.793 | 0.935 | 6.0 | 0.8039 | 0.5876 | No |
| seg1 | A-Eq | ModeA | 96 | 6.264 | 0.003 | 0.002 | 99.7 | 4.7977 | 11.5181 | Conditional |
| seg1 | A-Eq | ModeB | 868 | 2.133 | 0.013 | 0.056 | 95.2 | 1.9791 | 2.3182 | Conditional |
| seg1 | B-ZScore | ModeA | 713 | 2.453 | 0.000 | 0.004 | 99.4 | 2.1819 | 2.7567 | Conditional |
| seg1 | B-ZScore | ModeB | 186 | 0.737 | 1.000 | 0.995 | 0.4 | 0.5254 | 0.9022 | No |
| seg2 | A-Cal | ModeA_RTH | 548 | 1.883 | 0.040 | 0.002 | 99.7 | 2.1617 | 1.7798 | Conditional |
| seg2 | A-Cal | ModeB_PreRTH | 140 | 1.944 | 0.000 | 0.018 | 98.6 | 2.6026 | 1.5967 | Conditional |
| seg2 | A-Cal | ModeD_Below | 66 | 0.690 | 0.793 | 0.960 | 3.0 | 0.7052 | 0.7004 | No |
| seg2 | A-Eq | ModeA_RTH | 39 | 3.177 | 0.810 | 0.010 | 98.6 | 2.4157 | 5.5081 | Conditional (combined only) |
| seg2 | A-Eq | ModeB_PreRTH | 44 | 3.487 | 0.002 | 0.002 | 99.9 | 2.7832 | 5.0732 | Conditional (combined only) |
| seg2 | A-Eq | ModeD_Below | 814 | 1.703 | 0.013 | 0.000 | 100.0 | 1.7927 | 1.6937 | Conditional |
| seg2 | B-ZScore | ModeA_RTH | 327 | 4.245 | 0.000 | 0.000 | 100.0 | 3.3922 | 5.2044 | Conditional |
| seg2 | B-ZScore | ModeB_PreRTH | 91 | 1.652 | 0.000 | 0.056 | 93.9 | 3.1141 | 1.0597 | Conditional |
| seg2 | B-ZScore | ModeC_Overnight | 328 | 1.868 | 0.055 | 0.016 | 98.5 | 1.3970 | 2.3833 | Conditional |
| seg2 | B-ZScore | ModeD_Below | 186 | 0.737 | 1.000 | 0.995 | 0.4 | 0.5254 | 0.9022 | No |
| seg3 | A-Cal | ModeA_WTNT | 626 | 1.635 | 0.000 | 0.020 | 97.2 | 1.8515 | 1.5370 | Conditional |
| seg3 | A-Cal | ModeB_CT | 715 | 1.537 | 0.007 | 0.006 | 99.4 | 1.4732 | 1.6355 | Conditional |
| seg3 | A-Cal | ModeC_Below | 66 | 0.690 | 0.793 | 0.960 | 3.0 | 0.7052 | 0.7004 | No |
| seg3 | A-Eq | ModeA_WTNT | 47 | 4.382 | 0.067 | 0.001 | 100.0 | 2.5795 | 16.7236 | Conditional (combined only) |
| seg3 | A-Eq | ModeB_CT | 45 | 2.740 | 0.086 | 0.047 | 95.8 | 2.5745 | 3.0439 | Conditional |
| seg3 | A-Eq | ModeC_Below | 814 | 1.703 | 0.013 | 0.000 | 100.0 | 1.7927 | 1.6937 | Conditional |
| seg3 | B-ZScore | ModeA_WTNT | 401 | 2.423 | 0.000 | 0.055 | 93.8 | 2.3140 | 2.5971 | Conditional |
| seg3 | B-ZScore | ModeB_CT | 413 | 2.423 | 0.000 | 0.018 | 98.1 | 2.0098 | 2.8121 | Conditional |
| seg3 | B-ZScore | ModeC_Below | 186 | 0.737 | 1.000 | 0.995 | 0.4 | 0.5254 | 0.9022 | No |
| seg4 | A-Cal | ModeA_LowATR | 448 | 1.746 | 0.001 | 0.008 | 99.3 | 2.1254 | 1.5894 | Conditional |
| seg4 | A-Cal | ModeB_HighATR | 816 | 1.572 | 0.003 | 0.001 | 99.8 | 1.4697 | 1.7151 | Conditional |
| seg4 | A-Cal | ModeC_Below | 66 | 0.690 | 0.793 | 0.960 | 3.0 | 0.7052 | 0.7004 | No |
| seg4 | A-Eq | ModeA_LowATR | 29 | 4.262 | 0.195 | 0.005 | 100.0 | 2.4913 | 6.9350 | Conditional (combined only) |
| seg4 | A-Eq | ModeB_HighATR | 63 | 2.787 | 0.033 | 0.006 | 99.5 | 2.1955 | 4.5183 | Conditional |
| seg4 | A-Eq | ModeC_Below | 814 | 1.703 | 0.013 | 0.000 | 100.0 | 1.7927 | 1.6937 | Conditional |
| seg4 | B-ZScore | ModeA_LowATR | 378 | 2.571 | 0.000 | 0.042 | 96.6 | 2.4631 | 2.7318 | Conditional |
| seg4 | B-ZScore | ModeB_HighATR | 490 | 2.554 | 0.000 | 0.007 | 99.4 | 2.2480 | 2.8944 | Conditional |
| seg4 | B-ZScore | ModeC_Below | 186 | 0.737 | 1.000 | 0.995 | 0.4 | 0.5254 | 0.9022 | No |
| seg5 | B-ZScore | Cluster0 | 796 | 2.659 | 0.000 | 0.001 | 99.9 | 2.5586 | 2.8208 | Conditional |
| seg5 | B-ZScore | Cluster2 | 252 | 1.829 | 0.151 | 0.100 | 90.4 | 1.2170 | 2.6582 | No |
| seg5 | B-ZScore | Cluster3 | 18 | 3.155 | 1.000 | 1.000 | 0.0 | inf | 2.4922 | Insufficient Sample |

## Summary: Yes=0, Conditional=24, Conditional(combined)=4

## Multi-Mode Combos
- Primary (A-Eq Seg1 ModeA + B-ZScore Seg2 RTH): DEPLOY COMBO
- Secondary (A-Eq Seg1 ModeA + B-ZScore Seg4 LowATR): DEPLOY COMBO

## Winner: seg1_A-Eq/ModeA
- Verdict: Conditional
- PF @4t: 6.2643