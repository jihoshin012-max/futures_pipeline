# Prompt 1b — Incremental Build Report (v3.1)
Generated: 2026-03-21T23:41:27.843273
P1 only: 4701 touches. P2 NOT USED.
Baseline PF anchor: 0.8984

## Build Order & Results

| Step | Feature | Class | PF @3t | Trades | dPF prev | dPF base | Status |
|------|---------|-------|--------|--------|----------|----------|--------|
| 0 | Baseline | — | 0.9458 | 987 | — | — | — |
| 1 | F10_PriorPenetration | STRONG | 1.1812 | 403 | +0.2354 | +0.2354 | ACCEPTED |
| 2 | F04_CascadeState | STRONG | 1.3998 | 193 | +0.2186 | +0.4540 | ACCEPTED |
| 3 | F05_Session | STRONG | 1.3206 | 225 | -0.0792 | +0.3748 | SKIPPED |
| 4 | F01_Timeframe | STRONG | 1.4538 | 71 | +0.0541 | +0.5080 | ACCEPTED |
| 5 | F21_ZoneAge | SBB-MASKED | 2.6939 | 103 | +1.2401 | +1.7481 | ACCEPTED |
| 6 | F09_ZW_ATR | SBB-MASKED | 1.7509 | 365 | -0.9430 | +0.8051 | SKIPPED |
| 7 | F02_ZoneWidth | SBB-MASKED | 1.8509 | 197 | -0.8431 | +0.9051 | SKIPPED |
| 8 | F12_BarDuration | MODERATE | 1.8686 | 195 | -0.8254 | +0.9228 | SKIPPED |
| 9 | F24_NearestZoneDist | MODERATE | 1.8640 | 158 | -0.8300 | +0.9181 | SKIPPED |
| 10 | F20_VPDistance | MODERATE | 2.2395 | 114 | -0.4544 | +1.2937 | SKIPPED |
| 11 | F13_ClosePosition | MODERATE | 2.3682 | 177 | -0.3258 | +1.4224 | SKIPPED |
| 12 | F16_ZZOscillator | MODERATE | 1.6684 | 212 | -1.0255 | +0.7226 | SKIPPED |
| 13 | F25_BreakHistory | MODERATE | 1.8724 | 181 | -0.8215 | +0.9266 | SKIPPED |
| 14 | F11_DeltaDivergence | MODERATE | 2.1528 | 170 | -0.5411 | +1.2070 | SKIPPED |
| 15 | F23_CrossTFConfluence | MODERATE | 1.5242 | 204 | -1.1697 | +0.5784 | SKIPPED |
| 16 | F17_ATRRegime | MODERATE | 1.5306 | 271 | -1.1633 | +0.5848 | SKIPPED |
| 17 | F19_VPConsumption | MODERATE | 1.5730 | 308 | -1.1210 | +0.6272 | SKIPPED |
| 18 | F08_PriorRxnSpeed | MODERATE | 2.3553 | 150 | -0.3386 | +1.4095 | SKIPPED |
| 19 | F06_ApproachVelocity | WEAK | 1.8635 | 186 | -0.8304 | +0.9177 | SKIPPED |
| 20 | F22_RecentBreakRate | WEAK | 1.5832 | 212 | -1.1108 | +0.6373 | SKIPPED |
| 21 | F15_ZZSwingRegime | WEAK | 1.4524 | 189 | -1.2415 | +0.5066 | SKIPPED |
| 22 | F14_AvgOrderSize | WEAK | 1.4571 | 199 | -1.2368 | +0.5113 | SKIPPED |
| 23 | F07_Deceleration | WEAK | 1.6048 | 195 | -1.0892 | +0.6590 | SKIPPED |

## Elbow Point: 4 features
Features: ['F10_PriorPenetration', 'F04_CascadeState', 'F01_Timeframe', 'F21_ZoneAge']
PF @3t: 2.6939
Mechanism classes: ['STRUCTURAL', 'STRUCTURAL', 'STRUCTURAL', 'STRUCTURAL']

## Winning Feature Set: elbow
Features (4): ['F10_PriorPenetration', 'F04_CascadeState', 'F01_Timeframe', 'F21_ZoneAge']
Reason: Full model PF (2.6939) ≈ Elbow PF (2.6939), within 10% — elbow preferred

## Scoring Models (all P1-calibrated)
- A-Cal: PF=2.0759, threshold=16.66
- A-Eq: PF=2.6939, threshold=26.0
- B-ZScore: PF=1.4963, threshold=0.750

## Trend Context
TrendSlope P33=-0.3076, P67=0.3403
Distribution: WT=26.2%, CT=39.8%, NT=34.1%