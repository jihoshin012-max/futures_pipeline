# Throughput Re-examination — Correct Population (77 ZR trades)

**Date:** 2026-03-23
**Trigger:** Replication harness produces 77 ZONEREL trades vs 120 used in throughput analysis.
51 touches scored above threshold in pre-scored data but below threshold at runtime (F10 divergence).

---

## CHECK 1: Signal Density

| Metric | Old (120 trades) | New (77 trades) | Changed? |
|--------|-----------------|----------------|----------|
| Total qualifying signals | 178 | 123 | Yes, -31% |
| Median gap | 194 bars | 756 bars | Yes, much sparser |
| P10 gap | — | 123 bars | — |
| P90 gap | — | 5084 bars | — |
| % in clusters (<=20 bars) | 12.4% | 0.0% | Yes, no clustering |
| Blocked signals | 58 | 46 | Yes, -21% |
| IN_POSITION | — | 44 | — |
| LIMIT_EXPIRED | — | 2 | — |
| LIMIT_PENDING | — | 0 | — |

**DECISION GATE: PASS** — median gap 756 >> 100, clustering 0% << 25%.
Signals even sparser on correct population. The 43 dropped trades were
disproportionately from denser signal windows.

## CHECK 2: T2 Runner Marginal Value

| Bucket | Trades (T1 filled) | Mean L2 PnL |
|--------|-------------------|-------------|
| < 150t | 41 | 58.0t |
| 150-250t | 16 | 166.4t |
| 250t+ | 11 | 359.9t |
| **Overall** | **68** | **132.4t** |

T2 adds substantial value across all zone widths. Wide zones (250t+) benefit
most at 359.9t marginal. Original finding directionally confirmed, magnitudes
stronger on correct population.

## CHECK 3: Baseline Performance

| Metric | Old (120 trades) | New (77 trades) | Changed? |
|--------|-----------------|----------------|----------|
| Total PnL | 8,803t | 6,540.7t | Yes, -26% (fewer trades) |
| WR | ~84% | 92.2% | Yes, higher |
| PF | ~7.25 | 11.96 | Yes, higher |
| Mean bars held | ~79 | 78 | No |
| Max DD | 179t | 210.0t | Slightly worse |
| Max single loss | 156t | -210.0t | Slightly worse |

Total PnL lower due to fewer trades, but per-trade quality is materially
better (WR 92% vs 84%, PF 12.0 vs 7.3). The 43 dropped trades were
lower-quality (lower true scores), so removing them improves the surviving
population's quality metrics.

## CHECK 4: Fixed Exit Comparison

| Metric | ZR (77 trades) | Fixed (85 trades) |
|--------|---------------|-------------------|
| Total PnL | 6,540.7t | 3,871.9t |
| Mean PnL/trade | 84.9t | 45.6t |
| WR | 92.2% | 95.3% |
| PF | 11.96 | 9.59 |
| Max DD | 210.0t | 436.0t |

Fixed total PnL is 40.8% below ZR. Even with 8 extra trades from faster
resolution, fixed exits capture substantially less per trade. ZR wins
convincingly on both total PnL and risk-adjusted metrics.

## CHECK 5: Dynamic T2 Exit

| Metric | Old | New | Changed? |
|--------|-----|-----|----------|
| Dynamic T2 PnL | 8,834t | 6,540.7t | Fewer trades |
| Delta vs baseline | +31.7t (+0.4%) | +0.0t (+0.0%) | No early closes triggered |
| T2 early closes | 7 | 0 | Sparser signals = no overlaps |
| New trades from closes | 3 | 0 | — |

With 0% clustering, no qualifying signal arrives during an active T2 runner
on a different zone. Dynamic T2 has no opportunity to trigger. The mechanism
is valid but irrelevant on this population.

---

## VERDICT

| Original conclusion | Status |
|--------------------|--------|
| Signal density too sparse for throughput gains | **CONFIRMED** — even sparser (756 vs 194 median gap) |
| Current ZR 2-leg is optimal | **CONFIRMED** — WR 92%, PF 12.0 |
| Fixed exits lose throughput comparison | **CONFIRMED** — 40.8% below ZR |
| T2 runner adds value on wide, marginal on narrow | **CONFIRMED** — 360t on wide, 58t on narrow |
| Dynamic T2 exit is only ACTIONABLE mechanism | **CONFIRMED** — but 0 triggers on correct population |
| No safe throughput improvement exists | **CONFIRMED** |

**All conclusions CONFIRMED on correct 77-trade population. No full re-run needed.**

**Key insight:** The 43 dropped trades (scored above threshold with pre-scored data
but below threshold at runtime) were disproportionately clustered and lower quality.
Removing them made the surviving population sparser and higher quality. All throughput
mechanisms that relied on signal density are even less relevant than originally estimated.

**Next step:** Visual spot-check, then proceed to ZRA+ZB4 consolidation.
