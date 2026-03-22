# NQ Zone Touch — Holdout Verdict Narrative (v3.1)
Generated: 2026-03-22T01:15:49.960747

## 1. Executive Summary

The NQ zone touch strategy **passed** holdout testing. 4 group(s) achieved 'Yes' verdict on independent P2 data with frozen P1 parameters. The winning configuration (seg3_A-Cal/ModeB) achieved PF @4t = 4.996 with 58 combined P2 trades, Profit/DD = 16.51, vs baseline PF of 0.8984.

## 2. Baseline Context

- Raw baseline PF @3t: 0.8984 (95% CI: 0.8455–0.9568)
- Median cell: Stop=90t, Target=120t, TimeCap=80 bars
- Population R/P @60 bars: 1.007
- SBB split: NORMAL PF=1.3343, SBB PF=0.3684
- Per-period: P1a=0.9033, P1b=0.8219, P2a=1.0236 (baseline), P2b=0.8864 (baseline)

## 3. What Features Mattered

- Winning features (elbow=4): ['F10_PriorPenetration', 'F04_CascadeState', 'F01_Timeframe', 'F21_ZoneAge']
- All STRUCTURAL class
- F10_PriorPenetration: strongest single feature (+0.2354 dPF)
- F04_CascadeState: NO_PRIOR zones dominate high-conviction group
- F21_ZoneAge (SBB-masked): large dPF but partly from SBB filtering

## 4. Scoring and Segmentation

- Best segmentation: seg3 (best group PF = 5.0964)
- Winning run: seg3_A-Cal/ModeB (A-Cal)
- Scoring approach: A-Cal
- Tradeable groups: 4 Yes + 3 Conditional

## 5. Holdout Results

**Winner: seg3_A-Cal/ModeB**

| Period | Trades | PF @3t | PF @4t |
|--------|--------|--------|--------|
| P2a | ? | 4.7219 | — |
| P2b | ? | 5.4767 | — |
| Combined | 58 | 5.0964 | 4.9962 |

## 6. Risk Profile

- Max drawdown: 193 ticks
- Profit/DD: 16.513
- Sharpe: 0.787
- SBB leak: 0.0%
- Win rate: 91.4%

## 7. Recommendation

**DEPLOY** — 4 group(s) passed all holdout criteria. The winning configuration is ready for C++ autotrader implementation with the frozen parameters above.