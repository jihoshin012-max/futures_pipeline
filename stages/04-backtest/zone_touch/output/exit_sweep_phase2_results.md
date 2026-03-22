# Exit Sweep -- Phase 2 Results: Graduated Stop Step-Up

P1 ONLY. P2 NOT LOADED. Phase 1 locked.

Date: 2026-03-22 03:18

## CT mode (seg3 A-Cal ModeB)

| Rank | Base (from P1) | L1 Trigger | L1 Dest | L2 Trigger | L2 Dest | PF@3t | Trades | P/DD | MaxDD | Affected | NetProfit |
|------|---------------|------------|---------|------------|---------|-------|--------|------|-------|----------|-----------|
| 1 | #1 T=40/80 S=190 | 40 | +10 | - | - | inf | 40 | inf | 0 | 20 | 1358.2 |
| 2 | #1 T=40/80 S=190 | 40 | +20 | - | - | inf | 40 | inf | 0 | 29 | 1172.3 |
| 3 | #1 T=40/80 S=190 | 40 | +30 | - | - | inf | 40 | inf | 0 | 37 | 1156.1 |

**Step-up impact (CT mode): improved**

## All mode (seg1 A-Cal ModeA)

| Rank | Base (from P1) | L1 Trigger | L1 Dest | L2 Trigger | L2 Dest | PF@3t | Trades | P/DD | MaxDD | Affected | NetProfit |
|------|---------------|------------|---------|------------|---------|-------|--------|------|-------|----------|-----------|
| 1 | #1 T=60/80 S=240 | 60 | 0 | 80 | +60 | 10.78 | 133 | 25.89 | 243 | 80 | 6290.6 |
| 2 | #1 T=60/80 S=240 | 60 | 0 | 100 | +60 | 10.73 | 133 | 25.78 | 246 | 45 | 6341.6 |
| 3 | #1 T=60/80 S=240 | 60 | -10 | 80 | +60 | 10.70 | 133 | 26.35 | 243 | 77 | 6403.2 |

**Step-up impact (All mode): degraded**

## Self-Check
- [x] P1 only -- P2 not loaded
- [x] Phase 1 results locked
- [x] L2 Trigger > L1 Trigger constraint enforced
- [x] L2 Destination > L1 Destination constraint enforced
- [x] Trade-by-trade affected count reported
- [x] LOW IMPACT flag applied where <3 trades affected
- [x] Compared against Phase 1 best
- [x] Key question addressed: Profit/DD and MaxDD impact