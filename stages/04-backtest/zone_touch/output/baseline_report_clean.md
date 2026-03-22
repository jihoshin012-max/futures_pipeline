# Prompt 0 — Raw Edge Baseline Report (v3.1)
Generated: 2026-03-21T21:41:42.616274

## Baseline Anchor
- **Median cell PF @3t:** 0.8984 (95% CI: 0.8455–0.9568)
- **Median cell exit:** Stop=90t, Target=120t, TimeCap=80 bars
- **Best cell PF @3t:** 0.9847 at Stop=200t, Target=240t, TimeCap=120 bars
- **Best cell PF 95% CI:** 0.8998–1.0793
- **Cells > 1.0:** 0/120 (0%)
- **Cells > 1.3:** 0/120
- **Cells > 1.5:** 0/120
- **Median cell CI excludes 1.0:** NO

## Median Cell Risk Profile
- Win rate: 42.2%
- Avg trade PnL @3t: -5.35 ticks
- Avg winning trade: 112.06 ticks
- Avg losing trade: -91.21 ticks
- Max consecutive losses: 20
- Total trades: 4181
- Trades skipped (overlap): 5179

## Population R/P Ratios (v3.1: computed from bar data)
- 30 bars: 0.960
- 60 bars: 1.007
- 120 bars: 1.038
- Full observation: 1.155

## SBB Split
- NORMAL PF @3t: 1.3343 (2770 trades)
- SBB PF @3t: 0.3684 (1411 trades)

## Per-Period Stability
- P1a: PF @3t = 0.9033 (919 trades)
- P1b: PF @3t = 0.8219 (1176 trades)
- P2a: PF @3t = 1.0236 (894 trades)
- P2b: PF @3t = 0.8864 (1192 trades)

## Direction Split
- Demand (long): PF @3t = 0.9032 (2337 trades)
- Supply (short): PF @3t = 0.8922 (1844 trades)

## Session Split
- RTH (8:30-17:00 ET): PF @3t = 0.9318 (2764 trades)
- Overnight: PF @3t = 0.8383 (1417 trades)

## CascadeState Split
- PRIOR_HELD: PF @3t = 1.2551 (469 trades)
- PRIOR_BROKE: PF @3t = 0.8295 (3419 trades)
- NO_PRIOR: PF @3t = 1.3804 (290 trades)

## Timeframe Split
- 15m: PF @3t = 0.8849 (1352 trades, SBB rate=30.4%)
- 30m: PF @3t = 1.0654 (809 trades, SBB rate=27.1%)
- 60m: PF @3t = 0.8419 (587 trades, SBB rate=33.7%)
- 90m: PF @3t = 0.9517 (419 trades, SBB rate=33.5%)
- 120m: PF @3t = 0.8033 (359 trades, SBB rate=37.1%)
- 240m: PF @3t = 0.8984 (209 trades, SBB rate=37.3%)
- 360m: PF @3t = 0.8931 (181 trades, SBB rate=32.7%)
- 480m: PF @3t = 0.6963 (148 trades, SBB rate=36.9%)
- 720m: PF @3t = 0.7042 (117 trades, SBB rate=37.1%)

## Sequence Split
- Seq 1: PF @3t = 1.1264
- Seq 2: PF @3t = 0.8299
- Seq 3: PF @3t = 0.9128
- Seq 4: PF @3t = 0.6971
- Seq 5+: PF @3t = 0.7350

## Zone Density Split
- Isolated (0 nearby): PF @3t = 0.8137
- Sparse (1 nearby): PF @3t = 0.8611
- Clustered (2+ nearby): PF @3t = 0.9074

## Break Contagion
- Conditional break rate: 0.0546
- Base rate: 0.0347
- Contagion ratio: 1.5718

## Time Cap Sensitivity
- TimeCap=30: PF @3t = 0.8800 (4678 trades)
- TimeCap=50: PF @3t = 0.8901 (4354 trades)
- TimeCap=80: PF @3t = 0.8984 (4181 trades)
- TimeCap=120: PF @3t = 0.9019 (4121 trades)

## Cost Robustness
- Median cell PF @2t: 0.9165
- Median cell PF @3t: 0.8984
- Median cell PF @4t: 0.8807
- Robust at 4t cost: NO

## 16:55 ET Flatten Rule
- **Status: DEFERRED.** Bar data contains Date/Time columns but implementing per-bar datetime checks in the inner simulation loop would significantly increase runtime (~120 cells × 9000+ touches). Time cap serves as a proxy. Document this deferral for audit.

## RotBarIndex Filter (v3.1)
- Touches with RotBarIndex < 0 removed: 1

## Verdict: HIGH OVERFIT RISK
No robust unfiltered edge. PF > 1.0 in 0/120 cells (0%). Median CI [0.8455–0.9568] includes 1.0. Features must create the entire edge. HIGH overfit risk — but viable if Prompt 1a screening identifies strong features.

## Full Summary
RAW BASELINE: Median PF @3t = 0.8984 (95% CI: 0.8455–0.9568) across 120 grid cells. Best cell PF = 0.9847. 0% of cells > 1.0. Population R/P @60bars = 1.007. SBB split: NORMAL=1.3343, SBB=0.3684. Per-period: P1a=0.9033, P1b=0.8219, P2a=1.0236, P2b=0.8864. Direction: Demand=0.9032, Supply=0.8922. Session: RTH=0.9318, Overnight=0.8383. Cascade: HELD=1.2551, BROKE=0.8295, NO_PRIOR=1.3804. TF: 15m=0.8849, 30m=1.0654, 60m=0.8419, 90m=0.9517, 120m=0.8033, 240m=0.8984, 360m=0.8931, 480m=0.6963, 720m=0.7042. Seq: 1=1.1264, 2=0.8299, 3=0.9128, 4=0.6971, 5+=0.7350. Density: Isolated=0.8137, Sparse=0.8611, Clustered=0.9074. Break contagion ratio=1.5718.