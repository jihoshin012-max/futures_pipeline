# P2a Validation Report
**Date:** 2026-03-21 13:27:38
**Period:** P2a (Dec 18, 2025 - Jan 30, 2026), 30 RTH trading days
**Bars:** 10,475,281 (RTH, 1-tick)

## Verdict: **FAIL**

## Primary Criteria

- 1. SR above RW: NARROW PASS -- SR=56.9%, RW=55.6%, Delta=+1.3% (edge present but weaker than P1)
- 2. Adj net positive: FAIL -- -507 ticks
- 3. RW baseline valid: FAIL -- RT=1.0 SR=53.2% (outside +/-3pp of 50%, market structure shifted)

## Structural Signature Comparison

| Metric | P1 Value | P2a Value | Concern Threshold |
|--------|----------|-----------|-------------------|
| Success rate | 58.8% | 56.9% | < 55.6% (below RW) |
| First-cycle SR | 66.1% | 46.7% | < 58% |
| Later-cycle SR | 58.6% | 57.3% | < 53% |
| Failure cascade rate | 42.8% | 44.5% | > 55% |
| Avg progress HWM (fail) | 30.8% | 32.0% | > 50% |
| Inc PnL / day | -7 ticks | -11.4 ticks | < -100 |
| NPF (net) | 1.08 | 1.00 | < 1.0 |
| Adj net PnL | 12,420 | -507 | < 0 |
| Cycle count | 2,389 | 777 | (30 days vs 60) |
| RW check (RT=1.0) | 49.4% | 53.2% | outside 47-53% |

## Comparison Configs (Informational Only)

| Config | SR | Cycles | Adj Net | Notes |
|--------|----|--------|---------|-------|
| MA0 RT=0.8 (primary) | 56.9% | 777 | -507 | Validation target |
| R03_MA2 RT=0.8 | 56.9% | 777 | -1186 | Add config |
| RT=1.0 cost=0 | 53.2% | 637 | 6503 | RW baseline |

## Equity Curve

- Max drawdown: -2850 ticks at cycle #155
- Total cycles: 777
- Final equity: -166 ticks (net), -507 ticks (adjusted)
- Max drawdown occurred: early (first third) (cycle 155/777, 20%)