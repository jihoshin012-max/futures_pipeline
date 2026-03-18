# Sizing Sweep Report — Tick-Data Era
generated: 2026-03-17
data: P1a 1-tick (15.3M rows, ground truth)
simulator: tick-mode fast path (directional seed, one action per tick)
cost_model: Reports at 1-tick ($5/RT, user actual), 2-tick ($10/RT), and 3-tick ($15/RT)
time_filter: Exclude hours 1, 19, 20 (low-liquidity ETH)

## Ground Truth

OHLC-based results (250tick, 10sec, 250vol) are superseded. Tick-level simulation is
the only trustworthy source for absolute PF. See .planning/lessons.md for the full
history of close-only -> threshold-crossing OHLC -> tick-level progression.

## P1b Candidates (ranked by Net PF @1t)

| Rank | Config | Cyc | GrPF | NP@1t | NP@2t | NP@3t | Net@1t | WR | MP | P1b |
|:----:|--------|----:|-----:|------:|------:|------:|-------:|----:|---:|:---:|
| 1 | **ATR R=2.0x A=4.0x** | 2,263 | 1.31 | **1.21** | 1.12 | 1.03 | +15,798 | 79.2% | 6 | clean |
| 2 | **FRC SD=25 cap=2** | 1,551 | 1.19 | **1.14** | 1.10 | 1.05 | +15,015 | 77.5% | 2 | clean |
| 3 | ATR R=2.5x A=4.0x | 1,663 | 1.22 | 1.14 | 1.07 | 1.00 | +10,827 | 85.8% | 8 | clean |
| 4 | ATR R=2.0x/A=4.0x MTP=2 walk | 2,263 | 1.22 | 1.14 | 1.07 | 0.99 | +11,303 | 79.2% | 2 | clean |
| 5 | FRC SD=25 cap=3 | 1,438 | 1.17 | 1.12 | 1.06 | 1.02 | +11,492 | 78.1% | 3 | clean |
| 6 | V2 SD=25 MTP=2 walking | 1,355 | 1.14 | 1.10 | 1.06 | 1.02 | +9,750 | 77.1% | 2 | clean |
| 7 | V2 SD=20 MTP=1 walking | 2,141 | 1.15 | 1.09 | 1.04 | 0.99 | +7,641 | 56.7% | 1 | clean |
| 8 | V2 SD=25 MTP=1 walking | 1,355 | 1.14 | 1.09 | 1.05 | 1.01 | +5,934 | 55.2% | 1 | clean |
| 9 | V2 SD=20 MTP=3 walking | 2,141 | 1.15 | 1.09 | 1.03 | 0.97 | +10,547 | 78.6% | 3 | clean |
| 10 | ATR R=1.5x A=6.0x | 2,471 | 1.16 | 1.08 | 1.00 | 0.93 | +6,312 | 80.9% | 6 | clean |

*Fixed R=15/A=40 (NP@1t=1.18) excluded — P1b-contaminated.*

## Rejected Approaches

- **Frozen anchor (Mode A):** High PF from survivorship bias, catastrophic tail risk (-9,814 ticks), capital idle most of the time. Rejected.
- **Hard stops (ATR-normalized):** All thresholds hurt PF. 2x-5x ATR stops all produce worse results than uncapped baseline. Rejected.
- **Re-entry delay:** All delays hurt. Strategy has no predictive signal for consecutive losses. Rejected.
- **Direction fade:** Zero effect. Consecutive same-direction losses structurally rare in rotational state machine.
- **SpeedRead filter:** Too compressed on 250tick bars. Deferred to post-P1b.
- **ATR-adaptive single scaling factor:** No improvement over fixed distances. Legitimate.
- **Position cap on ATR-normalized:** All cap values (2,3,4) hurt PF. Forces exits at losses the strategy recovers from. Rejected.
- **SD=50:** Gross PF < 1.0 at all position sizes. Rotation signal doesn't exist at this step distance.

## Fragility Notes

- ATR(20) is a sharp optimum: ATR(14) and ATR(30) both significantly degrade performance.
- R=2.0x/A=4.0x is a sharp optimum: nearest neighbors (R=1.75/A=3.5, R=2.25/A=4.5) are clearly inferior.
- Fixed Rev=15/Add=40 fails on P1b (ATR +27% from P1a). ATR-normalization is intended to solve this but the sharp ATR(20) peak is a concern.

## Full Sweep Results

See: screening_results/tick_sweep_results.tsv (41 configs)

*Previous OHLC-era results archived to archive/ohlc-era-mode-b-sweep/*
