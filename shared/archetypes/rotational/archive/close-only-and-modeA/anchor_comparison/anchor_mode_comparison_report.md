# Anchor Mode Comparison Report

**Configs tested:** MAX_PROFIT profile winning configs on P1a
**Modes:** A (frozen), B (walking), C (frozen_stop @ [-40, -60, -80])
**Total runs:** 15

## 250vol (SD=7.0, ML=1, MTP=2)

| Mode | Threshold | Cycle PF | N Cycles | Win Rate | Total PnL | Worst DD | Avg Cycle Dur | MTP DD Exits |
|------|-----------|----------|----------|----------|-----------|----------|---------------|-------------|
| frozen | — | 2.2037 | 624 | 0.9583 | 10537 | 8569 | 0 | 0 |
| walking | — | 0.7410 | 7542 | 0.7304 | -66506 | 4033 | 10 | 0 |
| frozen_stop | -40 | 0.6970 | 12239 | 0.5860 | -108308 | 1425 | 6 | 5066 |
| frozen_stop | -60 | 0.7057 | 11029 | 0.6580 | -104732 | 2867 | 7 | 3704 |
| frozen_stop | -80 | 0.7224 | 10274 | 0.7002 | -95726 | 2867 | 7 | 2959 |

## 250tick (SD=4.5, ML=1, MTP=1)

| Mode | Threshold | Cycle PF | N Cycles | Win Rate | Total PnL | Worst DD | Avg Cycle Dur | MTP DD Exits |
|------|-----------|----------|----------|----------|-----------|----------|---------------|-------------|
| frozen | — | 1.8413 | 360 | 0.9972 | 4489 | 5336 | 0 | 0 |
| walking | — | 0.7099 | 11858 | 0.5720 | -66939 | 2108 | 6 | 0 |
| frozen_stop | -40 | 0.7342 | 13514 | 0.6270 | -77964 | 1674 | 5 | 5040 |
| frozen_stop | -60 | 0.7430 | 10368 | 0.6946 | -63861 | 1674 | 7 | 3165 |
| frozen_stop | -80 | 0.7719 | 8325 | 0.7446 | -47799 | 1663 | 8 | 2125 |

## 10sec (SD=10.0, ML=1, MTP=4)

| Mode | Threshold | Cycle PF | N Cycles | Win Rate | Total PnL | Worst DD | Avg Cycle Dur | MTP DD Exits |
|------|-----------|----------|----------|----------|-----------|----------|---------------|-------------|
| frozen | — | 1.7218 | 368 | 0.9212 | 11363 | 13981 | 0 | 0 |
| walking | — | 0.8580 | 2907 | 0.8438 | -20818 | 2618 | 25 | 0 |
| frozen_stop | -40 | 0.7375 | 5288 | 0.5004 | -46294 | 1342 | 14 | 2642 |
| frozen_stop | -60 | 0.7880 | 4667 | 0.6111 | -38037 | 1342 | 16 | 1815 |
| frozen_stop | -80 | 0.8325 | 4319 | 0.6666 | -28998 | 2488 | 17 | 1430 |

## Winner Selection

Criteria: highest cycle_pf with lowest worst_cycle_dd (risk-adjusted).
Composite score = cycle_pf / (worst_cycle_dd / 1000) — higher is better.

| Bar Type | Best Mode | Threshold | Composite | Cycle PF | Worst DD | PnL |
|----------|-----------|-----------|-----------|----------|----------|-----|
| 250vol | frozen_stop | -40 | 0.4891 | 0.6970 | 1425 | -108308 |
| 250tick | frozen_stop | -80 | 0.4642 | 0.7719 | 1663 | -47799 |
| 10sec | frozen_stop | -60 | 0.5872 | 0.7880 | 1342 | -38037 |

## Recommendation

**Dominant winner: `frozen_stop`** (wins 3/3 bar types)

- 250vol: `frozen_stop` @ -40 ticks
- 250tick: `frozen_stop` @ -80 ticks
- 10sec: `frozen_stop` @ -60 ticks