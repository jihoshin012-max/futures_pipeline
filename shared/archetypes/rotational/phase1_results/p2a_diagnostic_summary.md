# P2a Diagnostic Summary — V1.4 Adaptive Config

## Prong 1: Base Config (SR OFF) on P2a
- SR OFF: NPF=0.9541, GPF=1.0022, net=-3,055 ticks, 1017 cycles
- SR ON:  NPF=0.9577, GPF=1.0058, net=-1,797 ticks, 667 cycles
- P1 ref: NPF=1.200, GPF=1.260, 1,847 cycles
- SR-skipped cycles (would fail SR<48): n=452, mean net=-5.4

## Prong 2: Tail Concentration
| Worst Removed | NPF | Net Ticks | Cycles | Sessions Left |
|---------------|-----|-----------|--------|---------------|
| 0 | 0.9577 | -1,797 | 667 | 28 |
| 1 | 1.0345 | +1,258 | 613 | 27 |
| 2 | 1.0856 | +2,910 | 598 | 26 |
| 3 | 1.1392 | +4,280 | 564 | 25 |
| 4 | 1.1964 | +5,495 | 535 | 24 |
| 5 | 1.2514 | +6,479 | 511 | 23 |

| Best Removed | NPF | Net Ticks | Cycles |
|--------------|-----|-----------|--------|
| 0 | 0.9577 | -1,797 | 667 |
| 1 | 0.9104 | -3,754 | 633 |
| 2 | 0.8616 | -5,366 | 572 |
| 3 | 0.8199 | -6,883 | 538 |

## Prong 3: Rolling 28-Session Variance
- P1 rolling NPF: mean=1.2471, min=1.1281, max=1.3435, std=0.0586
- P2a NPF (0.9577) at P0 of P1 distribution
- P1 windows with NPF < 1.0: 0
- P1 rolling Gross PF: mean=1.3094, min=1.1817
- P1 rolling cap-walk rate: mean=25.8%, min=24.6%, max=27.7%

## Prong 4: Reversal Chain Economics
| Metric | P1 Rev | P2a Rev |
|--------|--------|---------|
| Cycles | 1565 | 543 |
| Gross PF | 1.3482 | 1.1000 |
| Net PF | 1.2841 | 1.0479 |
| Mean net/cycle | +15.4 | +2.9 |
| Cap-walk rate | 26.1% | 26.2% |
| CW mean loss | -207.3 | -227.7 |
| CW mean MAE | 63.9 | 64.1 |

## Decision
**Diagnosis:** Regime shift + tail concentration.

**Next step:** Strategy may need regime detection. Park and wait for P3.
