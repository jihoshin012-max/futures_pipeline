# Throughput Optimization Analysis — Part 2 of 2

Generated: 2026-03-23 13:25
P1 baseline: 120 trades, 8802.7t total PnL
P2 baseline: 69 trades, 7563.9t total PnL

======================================================================
## SECTION 8: WINNER VS LOSER RESOLUTION SPEED
======================================================================

| Metric | Winners | Losers |
|--------|---------|--------|
| Count | 106 | 14 |
| Mean bars held | 61.8 | 102.3 |
| Median bars held | 44 | 149 |
| Mean bars to T1 (winners) | 26.1 | -- |
| Mean bars to stop (losers) | -- | 18.2 |
| Signals blocked per trade | 0.34 | 0.86 |
| Blocking cost (blocked x 73.4t EV) | 2640.8 | 880.3 |

### Per-Loser Detail (all P1 ZR losers)

| # | bars_held | PnL | zone_width | mode | exit_type | signals_blocked |
|---|----------|-----|-----------|------|-----------|----------------|
| 1 | 116 | -18.0 | 94 | WT | TARGET_1 | 0 |
| 2 | 160 | -3.9 | 81 | WT | TARGET_1 | 0 |
| 3 | 13 | -156.0 | 102 | WT | STOP | 0 |
| 4 | 88 | -42.7 | 245 | WT | TARGET_1 | 0 |
| 5 | 46 | -31.2 | 173 | WT | TARGET_1 | 0 |
| 6 | 149 | -20.9 | 112 | WT | TARGET_1 | 1 |
| 7 | 6 | -149.0 | 97 | WT | STOP | 0 |
| 8 | 11 | -151.0 | 99 | WT | STOP | 0 |
| 9 | 160 | -42.0 | 232 | WT | TIMECAP | 3 |
| 10 | 160 | -14.0 | 232 | WT | TIMECAP | 4 |
| 11 | 43 | -123.0 | 76 | WT | STOP | 1 |
| 12 | 160 | -102.0 | 138 | CT | TIMECAP | 1 |
| 13 | 160 | -3.0 | 431 | WT | TIMECAP | 1 |
| 14 | 160 | -40.0 | 330 | WT | TIMECAP | 1 |

### Adverse Excursion Exit Rules

| Rule | Losers caught (AE exit) | Winners killed | Freed (seq sim) | Net PnL | KS triggers |
|------|------------------------|---------------|----------------|---------|-------------|
| No rule (current) | 0 | 0 | 0 | 8802.7 | 0 |
| AE > 0.75x zw + bar > 20 | 18 | 1 | 10 | 7484.9 | 0 |
| AE > 1.0x zw + bar > 15 | 8 | 0 | 3 | 8139.9 | 0 |
| AE > 0.5x zw + bar > 30 | 17 | 5 | 10 | 7413.2 | 1 |

======================================================================
## SECTION 9: SIGNAL CLUSTERING AND THROUGHPUT WINDOWS
======================================================================

### A) Next Signal Gap Analysis

| Next signal gap | Count | Mean bars_held | Mean signals blocked |
|----------------|-------|---------------|---------------------|
| < 15 bars | 3 | 67.3 | 1.33 |
| 15-30 bars | 13 | 86.9 | 1.23 |
| 30-60 bars | 13 | 88.2 | 1.08 |
| > 60 bars | 90 | 60.2 | 0.16 |
| No next signal | 1 | -- | -- |

### B) Cluster Windows (3+ signals within 30 bars)

Cluster windows found: 3
- Window 1: 3 signals in 22 bars, 1 traded, 2 blocked
- Window 2: 3 signals in 0 bars, 3 traded, 0 blocked
- Window 3: 3 signals in 0 bars, 0 traded, 3 blocked

> Cluster windows are rare on P1 (sparse signals). Exit tightening during clusters
> would affect very few trades. This is OBSERVATIONAL — no mechanism implemented.

======================================================================
## SECTION 10: DYNAMIC T2 EXIT ON NEW SIGNAL
======================================================================

| Metric | Current | Dynamic T2 exit |
|--------|---------|----------------|
| Total trades | 120 | 122 |
| T2 early closes triggered | -- | 7 |
| Mean T2 PnL on early close | -- | 42.3 |
| Mean T2 PnL if held (given up) | -- | 139.0 |
| New signal trades taken | -- | 3 |
| New signal CT limit EXPIRED | -- | 0 |
| Net cost of expired CT limits | -- | 0.0t |
| New signal WR | -- | 100.0% |
| New signal total PnL | -- | 284.4 |
| NET total PnL | 8802.7 | 8834.4 |
| Kill-switch triggers | 0 | 0 |

| T2 status at close | Count | Mean T2 early PnL | Mean new signal PnL |
|-------------------|-------|-------------------|---------------------|
| T2 was profitable | 5 | 61.2 | 94.8 |
| T2 was at loss | 2 | -5.0 | 0.0 |

### P2 Cross-Validation

| Period | Current Total PnL | Dynamic T2 Total PnL | Delta | KS triggers |
|--------|-------------------|---------------------|-------|-------------|
| P1 | 8802.7 | 8834.4 | +31.7 | 0 |
| P2 | 7563.9 | 7666.7 | +102.8 | 0 |

======================================================================
## SECTION 11: HYBRID EXIT STRATEGY
======================================================================

> **Hybrid D skipped**: Part 1 Section 6C found BE NOT VIABLE across all zone width bins
> (0.25x: -4010t, 0.33x: -2617t, 0.5x: -823t). No zone-width-conditional BE improvement exists.

| Config | Trades | Total PnL | Mean hold | Freed | Max DD | Max loss | KS |
|--------|--------|-----------|----------|-------|--------|---------|-----|
| Current uniform ZR 2-leg | 120 | 8802.7 | 66.5 | 0 | 179.0 | 156.0 | 0 |
| Hybrid A: narrow=T1, wide=2leg | 124 | 8457.2 | 53.1 | 4 | 179.0 | 156.0 | 0 |
| Hybrid B: narrow=T1, wide=dynamic T2 | 125 | 8484.0 | 53.3 | 5 | 179.0 | 156.0 | 0 |
| Hybrid C: narrow=BE T2, wide=current | 123 | 8570.4 | 57.8 | 3 | 179.0 | 156.0 | 0 |

Best P1 hybrid: **Hybrid C: narrow=BE T2, wide=current** (8570.4t)

| Period | Hybrid | Total PnL | vs current | Consistent? |
|--------|--------|-----------|------------|-------------|
| P1 | Hybrid C: narrow=BE T2, wide=current | 8570.4 | -232.3 | baseline |
| P2 | same | 7421.3 | -142.6 | NO |

======================================================================
## SECTION 12: COMBINED THROUGHPUT SUMMARY
======================================================================

### All P1 Results

| Strategy | Mechanism | Trades | Total PnL | vs Current | Max DD | Max loss | KS | Complexity |
|----------|-----------|--------|-----------|------------|--------|---------|-----|------------|
| Current ZR 2-leg | baseline | 120 | 8802.7 | -- | 179.0 | 156.0 | 0 | current |
| Fixed exits (Part 1 S3) | fixed T/S | 130 | 6735.5 | -2067.2 | 243.0 | 243.0 | 0 | low |
| ZR single-leg T1 (Part 1 S4) | drop T2 | 127 | 8119.0 | -683.7 | 179.0 | 156.0 | 0 | low |
| Fixed single-leg T1 (Part 1 S4) | drop fixed T2 | 138 | 6455.0 | -2347.7 | 243.0 | 243.0 | 0 | low |
| Full tighter stop (Part 1 S6A) | faster loss | 121 | 8527.8 | -274.9 | 222.1 | 141.0 | 0 | low |
| T2-only tighter stop (Part 1 S6B) | faster T2 | 120 | 8680.0 | -122.8 | 179.0 | 156.0 | 0 | low |
| BE step-up 0.5x (Part 1 S6C) | BE exit | 124 | 7980.1 | -822.6 | 185.0 | 156.0 | 0 | low |
| Adverse excursion (AE > 1.0x zw + bar > 15) | cond. early exit | 122 | 8139.9 | -662.8 | 271.1 | 156.0 | 0 | medium |
| Dynamic T2 exit (S10) | signal-triggered T2 | 122 | 8834.4 | +31.7 | 179.0 | 156.0 | 0 | medium |
| Best hybrid (S11): Hybrid C: narrow=BE T2, wide=current | zone-width-based | 123 | 8570.4 | -232.3 | 179.0 | 156.0 | 0 | medium |

### P2 Cross-Validation Summary

| Config | P1 Total PnL | P2 Total PnL | P1 KS | P2 KS | Classification |
|--------|-------------|-------------|-------|-------|---------------|
| Current ZR 2-leg | 8802.7 | 7563.9 | 0 | 0 | baseline |
| Fixed exits | 6735.5 | 4215.9 | 0 | 0 | NOT VIABLE |
| ZR single-leg T1 | 8119.0 | 7654.0 | 0 | 0 | PROMISING |
| T2-only tighter stop | 8680.0 | 7468.9 | 0 | 0 | NOT VIABLE |
| BE step-up 0.5x | 7980.1 | 7374.5 | 0 | 0 | NOT VIABLE |
| Dynamic T2 exit | 8834.4 | 7666.7 | 0 | 0 | ACTIONABLE |
| Best hybrid (Hybrid C: narrow=BE T2, wide=current) | 8802.7 | 7421.3 | 0 | 0 | NOT VIABLE |

## FINAL RECOMMENDATION

**Recommended config: Dynamic T2 exit**

- P1 Total PnL: 8834.4 (+31.7 vs current)
- P2 Total PnL: 7666.7 (+102.8 vs current)
- Max single loss: 156.0t (within 300t budget)
- KS triggers: P1=0, P2=0

---
*Sequential freed signal simulation used throughout. P1 primary, P2 cross-validation.
Kill-switch triggers counted for all configs.*