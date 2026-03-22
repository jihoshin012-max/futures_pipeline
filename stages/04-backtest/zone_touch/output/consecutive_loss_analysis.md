# ITEM 5: Consecutive Loss Sequences — seg3_A-Cal/ModeB (Winner)
Generated: 2026-03-22T02:47:20.647973
Total trades: 58, Losses: 5

## Summary

| Metric | Value |
|--------|-------|
| Max consecutive losses (P2 combined) | 1 |
| Max consecutive losses (P2a) | 1 |
| Max consecutive losses (P2b) | 1 |
| Worst streak PnL | -193.0 ticks |
| Longest DD duration (bars) | 222 |
| Longest DD duration (cal days) | ~5 |
| Max DD depth | 193.0 ticks |

## W/L Sequence (chronological)
`LWWWLWWWWWWWWWWWWWWWWWWWWLWWWWWWWWWWLWWWWWWWLWWWWWWWWWWWWW`
(58 trades: 53W, 5L, 0B)

## Loss Streaks
No loss streaks of 2+ consecutive trades.

## Kill-Switch Implications

- Max observed consecutive losses: **1**
- [SUGGESTION] Kill-switch at 3 consecutive losses would never have triggered on P2.
- [SUGGESTION] Kill-switch at 4 consecutive losses provides 1-trade buffer beyond observed worst case.
- Worst single-streak damage: -193.0t = $965 per contract
- [SUGGESTION] Position sizing should tolerate 193t drawdown without exceeding risk limits.
- Max DD depth across all trades: 193.0t = $965 per contract