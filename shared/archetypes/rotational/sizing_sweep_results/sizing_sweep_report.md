# Sizing Sweep Report — Mode B (Walking Anchor), Threshold-Crossing Simulator
generated: 2026-03-17
bar_type: 250tick (bar_data_250tick_rot)
period: P1a
anchor_mode: walking (Mode B)
simulator: threshold-crossing OHLC (exact trigger levels against High/Low)

## Summary

322 unique parameter combinations swept on 250tick P1a data using the threshold-crossing
simulator with Mode B (walking anchor). Cost model: 3 ticks ($15) per action round-turn.

**Key finding:** Walking anchor transforms the landscape. Mode A's high-PF/low-PnL
selectivity is replaced by Mode B's moderate-PF/high-PnL active trading. MTP=1 (pure
reversal) is now competitive with martingale configs because walking anchor eliminates
the "stuck at MTP cap" problem entirely.

## Profile Winners

### MAX_PROFIT — SD=6.0, ML=1, MTP=8
- PF: 6.60 | Net PnL: +1,074,653 ticks | Cycles: 78,487
- WR: 93.9% | MaxDD: 16,866 | Calmar: 63.72 | WinSess: 97.3%

### SAFEST — SD=10.0, ML=1, MTP=1
- PF: 3.39 | Net PnL: +391,659 ticks | Cycles: 21,394
- WR: 76.3% | MaxDD: 2,132 | Calmar: 183.71 | WinSess: 94.6%

### MOST_CONSISTENT — SD=5.0, ML=1, MTP=1
- PF: 4.06 | Net PnL: +959,317 ticks | Cycles: 111,171
- WR: 81.8% | MaxDD: 2,158 | Calmar: 444.54 | WinSess: 100.0%

## MTP=1 (Pure Reversal) — Strong with Walking Anchor

| StepDist | PF | Net PnL | Cycles | MaxDD |
|----------|---:|--------:|-------:|------:|
| 5.0 | 4.06 | +959,317 | 111,171 | 2,158 |
| 5.5 | 4.29 | +928,759 | 92,984 | 2,102 |
| 6.0 | 6.36 | +1,067,405 | 78,487 | 33,090 |
| 7.0 | 4.33 | +745,691 | 55,038 | 1,562 |
| 8.0 | 4.13 | +620,827 | 44,153 | 1,718 |

MTP=1 eliminates position growth risk entirely. With walking anchor, it generates
comparable PnL to MTP=4/8 configs with dramatically lower drawdowns.

## MTP=0 (Unlimited / V1 Equivalent)

Best: SD=7.0, PF=1.78, PnL=+481,873, MaxDD=378,876.

MTP=0 is profitable but the unlimited position growth creates massive drawdowns.
Walking anchor helps (vs close-only PF=0.58) but position still grows unconstrained
during sustained adverse moves.

## Mode A vs Mode B Comparison

| Config | Mode A PF | Mode B PF | Mode A PnL | Mode B PnL |
|--------|----------:|----------:|-----------:|-----------:|
| SD=5.0/ML=1/MTP=4 | 6.60 | 5.36 | 116,924 | **1,123,345** |
| SD=5.5/ML=1/MTP=4 | 10.48 | 5.75 | 173,646 | **1,096,775** |
| SD=6.0/ML=1/MTP=8 | 2.15 | 6.60 | 65,186 | **1,074,653** |
| SD=7.0/ML=1/MTP=1 | 2.83 | 4.33 | 9,011 | **745,691** |
| SD=7.0/ML=1/MTP=2 | 7.04 | 4.23 | 59,208 | **829,033** |

Mode B generates 6-80x more net PnL than Mode A across all configs tested. Mode A's
higher PF at some configs comes from extreme selectivity (holding dead positions).

## Observations

1. **ML=1 dominates everywhere** — higher max_levels never wins any profile
2. **MTP=1 is now the MOST_CONSISTENT winner** — walking anchor makes pure reversal viable
3. **SD=5.0-6.0 is the sweet spot** — consistent across MAX_PROFIT and MOST_CONSISTENT
4. **SAFEST prefers SD=10.0/MTP=1** — wide steps, pure reversal, minimal exposure
5. **All profiles are profitable** — 216 of 322 configs have PF >= 1.0 (67%)

## Parameters

- StepDist: [1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0, 5.5, 6.0, 7.0, 8.0, 10.0]
- MaxLevels: [1, 2, 3, 4, 5]
- MaxTotalPosition: [1, 2, 4, 8, 16, 0]
- MaxContractSize: 16 (fixed)
- InitialQty: 1 (fixed)
- AnchorMode: walking (fixed)
- CostTicks: 3 (NQ, from instruments.md)

*Report generated from sizing_sweep_P1a.tsv*
