# NQ Zone Touch — Holdout Verdict Narrative (v3.2)
Generated: 2026-03-24T14:11:44.217415

## 1. Executive Summary

The zone touch strategy achieved **conditional** results. No group earned a full 'Yes' verdict, but 24 group(s) passed partial criteria. The best conditional result (seg1_A-Eq/ModeA) had PF @4t = 6.264. Paper trading recommended before deployment.

## 2. Baseline Context

- Raw baseline PF @3t: 1.3396 (warmup-enriched v3.2 data)
- Median cell: Stop=120t, Target=120t, TimeCap=80 bars
- P1 touches: 3278
- P2 touches: 3536 (P2a=1766, P2b=1770)

## 3. What Features Mattered

- Winning features (elbow=7): ['F10', 'F01', 'F05', 'F09', 'F21', 'F13', 'F04']
- Feature classifications: F10=STRONG, F01=STRONG, F05=STRONG, F09=STRONG, F21=STRONG, F13=MODERATE, F04=MODERATE
- A-Cal weights: F10=10.0, F01=4.91, F05=4.54, F09=2.98, F21=2.95, F13=2.82, F04=1.93

## 4. Scoring and Segmentation

- Best segmentation: seg1 (best group PF = 6.4170)
- Winning run: seg1_A-Eq/ModeA (A-Eq)
- Tradeable groups: 0 Yes + 24 Conditional

## 5. Holdout Results

**Winner: seg1_A-Eq/ModeA**

| Period | Trades | PF @3t | PF @4t |
|--------|--------|--------|--------|
| P2a | 56 | 4.7977 | — |
| P2b | 40 | 11.5181 | — |
| Combined | 96 | 6.4170 | 6.2643 |

## 6. Risk Profile

- Max drawdown: 193 ticks
- Profit/DD: 22.482
- Sharpe: 0.888
- SBB leak: 0.9%
- Win rate: 94.8%
- Trades/day: 1.23

## 7. Recommendation

**PAPER TRADE** — No group achieved full 'Yes' verdict. 24 conditional group(s) warrant live paper trading.

## 8. Multi-Mode Deployment Assessment

Prompt 2 recommended deploying multiple complementary modes simultaneously. Two combos were validated on P2:

**Primary Combo: A-Eq Seg1 ModeA + B-ZScore Seg2 ModeA_RTH**
- P1 overlap: 13.1%
- A-Eq Seg1 ModeA: high conviction, Conditional verdict, PF @4t = 6.264
- B-ZScore Seg2 RTH: balanced, Conditional verdict, PF @4t = 4.245
- Combo verdict: **DEPLOY COMBO**
- Combined PF @3t: 4.5080, @4t: 4.4290
- Combined trades: 423, Max DD: 647, Profit/DD: 47.615

**Secondary Combo: A-Eq Seg1 ModeA + B-ZScore Seg4 ModeA_LowATR**
- P1 overlap: 16.8%
- Combo verdict: **DEPLOY COMBO**
- Combined PF @3t: 2.9103, @4t: 2.8533

Mode characteristics (from mode_classification_v32.md):
- A-Eq Seg1 ModeA: AGGRESSIVE, HIGH-CONVICTION, wide stop / tight target
- B-ZScore Seg2 RTH: BALANCED, RTH-only, zone-relative exits
- B-ZScore Seg4 LowATR: CONSERVATIVE, low-volatility specialist