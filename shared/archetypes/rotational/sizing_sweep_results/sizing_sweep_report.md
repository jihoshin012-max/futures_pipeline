# Sizing Sweep Report — Rotational Archetype (P1a)

**Generated from:** `sizing_sweep_P1a.tsv`
**Period:** P1a (in-sample calibration data)

---

## 1. Summary

| Metric | Value |
|--------|-------|
| Raw parameter combos | 420 (14 StepDist x 5 MaxLevels x 6 MTP) |
| After deduplication | 322 unique combos per bar type |
| Dedup savings | 98 combos eliminated (23%) |
| Total simulation runs | 966 (322 x 3 bar types) |
| Configs with PF >= 1.0 | 188 (19.5%) |
| Configs with PF < 1.0 | 778 (80.5%) |

### Best Config per Bar Type (by Cycle PF)

| Bar Type | StepDist | MaxLevels | MTP | Cycle PF | Total PnL (ticks) |
|----------|----------|-----------|-----|----------|-------------------|
| 250vol | 7.0 | 1 | 2 | 2.2037 | 10537 |
| 250tick | 4.5 | 1 | 1 | 1.8413 | 4489 |
| 10sec | 10.0 | 1 | 4 | 1.7218 | 11363 |

---

## 2. Profile Selections — Top 3 Candidates per Bar Type

### 2.1 Profile: MAX_PROFIT

*Highest cycle PF regardless of risk*

**250vol:**

| Rank | StepDist | MaxLevels | MTP | cycle_pf | total_pnl_ticks | worst_cycle_dd | calmar_ratio | PF<1? |
|---|---|---|---|---|---|---|---|---|
| 1 | 7.0 | 1 | 2 | 2.2037 | 10537 | 8569.0000 | 1.2297 | no |
| 2 | 7.0 | 2 | 2 | 2.2037 | 10537 | 8569.0000 | 1.2297 | no |
| 3 | 10.0 | 1 | 1 | 1.7522 | 3716.0000 | 4940.0000 | 0.7522 | no |

**250tick:**

| Rank | StepDist | MaxLevels | MTP | cycle_pf | total_pnl_ticks | worst_cycle_dd | calmar_ratio | PF<1? |
|---|---|---|---|---|---|---|---|---|
| 1 | 4.5 | 1 | 1 | 1.8413 | 4489.0000 | 5336.0000 | 0.8413 | no |
| 2 | 4.0 | 1 | 1 | 1.8376 | 4411.0000 | 5266.0000 | 0.8376 | no |
| 3 | 4.5 | 1 | 2 | 1.7928 | 8265.0000 | 9644.0000 | 0.8570 | no |

**10sec:**

| Rank | StepDist | MaxLevels | MTP | cycle_pf | total_pnl_ticks | worst_cycle_dd | calmar_ratio | PF<1? |
|---|---|---|---|---|---|---|---|---|
| 1 | 10.0 | 1 | 4 | 1.7218 | 11363 | 13981 | 0.8127 | no |
| 2 | 10.0 | 2 | 4 | 1.7218 | 11363 | 13981 | 0.8127 | no |
| 3 | 10.0 | 3 | 4 | 1.7218 | 11363 | 13981 | 0.8127 | no |

### 2.2 Profile: SAFEST

*Best survival metrics — minimise worst-case single-cycle loss*

**250vol:**

| Rank | StepDist | MaxLevels | MTP | worst_cycle_dd | max_level_exposure_pct | tail_ratio | cycle_pf | PF<1? |
|---|---|---|---|---|---|---|---|---|
| 1 | 1.0 | 4 | 16 | 753.0000 | 0.0000 | 0.5738 | 1.0209 | no |
| 2 | 1.0 | 5 | 16 | 753.0000 | 0.0000 | 0.5738 | 1.0209 | no |
| 3 | 1.0 | 2 | 16 | 753.0000 | 6.4700 | 0.5738 | 1.0209 | no |

**250tick:**

| Rank | StepDist | MaxLevels | MTP | worst_cycle_dd | max_level_exposure_pct | tail_ratio | cycle_pf | PF<1? |
|---|---|---|---|---|---|---|---|---|
| 1 | 5.0 | 1 | 1 | 4656.0000 | 0.0000 | 0.0057 | 1.2154 | no |
| 2 | 5.5 | 1 | 1 | 4740.0000 | 0.0000 | 0.0061 | 1.4867 | no |
| 3 | 8.0 | 1 | 1 | 4812.0000 | 0.0000 | 0.0084 | 1.2891 | no |

**10sec:**

| Rank | StepDist | MaxLevels | MTP | worst_cycle_dd | max_level_exposure_pct | tail_ratio | cycle_pf | PF<1? |
|---|---|---|---|---|---|---|---|---|
| 1 | 10.0 | 1 | 1 | 5455.0000 | 0.0000 | 0.0111 | 1.1021 | no |
| 2 | 8.0 | 1 | 1 | 5481.0000 | 0.0000 | 0.0115 | 0.9057 | YES |
| 3 | 4.5 | 1 | 1 | 5481.0000 | 0.0000 | 0.0060 | 0.9049 | YES |

### 2.3 Profile: MOST_CONSISTENT

*Best risk-adjusted returns — maximise calmar and consistency*

**250vol:**

| Rank | StepDist | MaxLevels | MTP | calmar_ratio | winning_session_pct | max_dd_duration_bars | cycle_pf | PF<1? |
|---|---|---|---|---|---|---|---|---|
| 1 | 7.0 | 1 | 2 | 1.2297 | 94.4400 | 14206 | 2.2037 | no |
| 2 | 7.0 | 2 | 2 | 1.2297 | 94.4400 | 14206 | 2.2037 | no |
| 3 | 10.0 | 1 | 1 | 0.7522 | 93.3300 | 15185 | 1.7522 | no |

**250tick:**

| Rank | StepDist | MaxLevels | MTP | calmar_ratio | winning_session_pct | max_dd_duration_bars | cycle_pf | PF<1? |
|---|---|---|---|---|---|---|---|---|
| 1 | 4.5 | 1 | 2 | 0.8570 | 93.3300 | 13791 | 1.7928 | no |
| 2 | 4.5 | 2 | 2 | 0.8570 | 93.3300 | 13791 | 1.7928 | no |
| 3 | 4.5 | 1 | 1 | 0.8413 | 92.8600 | 19998 | 1.8413 | no |

**10sec:**

| Rank | StepDist | MaxLevels | MTP | calmar_ratio | winning_session_pct | max_dd_duration_bars | cycle_pf | PF<1? |
|---|---|---|---|---|---|---|---|---|
| 1 | 10.0 | 1 | 4 | 0.8127 | 86.6700 | 21735 | 1.7218 | no |
| 2 | 10.0 | 2 | 4 | 0.8127 | 86.6700 | 21735 | 1.7218 | no |
| 3 | 10.0 | 3 | 4 | 0.8127 | 86.6700 | 21735 | 1.7218 | no |

---

## 3. Pure Reversal (MTP=1) vs Best Martingale

Pure reversal means MaxTotalPosition=1: the position never adds, so martingale levels are irrelevant. These rows have `max_level_exposure_pct=0` (confirmed).

| Bar Type | Best MTP=1 PF | Best MTP=1 SD | Best Martingale PF | Martingale SD/ML/MTP | Martingale Wins? |
|----------|--------------|--------------|-------------------|---------------------|-----------------|
| 250vol | 1.7522 | SD=10.0 | 2.2037 | SD=7.0 ML=1 MTP=2 | YES |
| 250tick | 1.8413 | SD=4.5 | 1.7928 | SD=4.5 ML=1 MTP=2 | no |
| 10sec | 1.1172 | SD=7.0 | 1.7218 | SD=10.0 ML=1 MTP=4 | YES |

---

## 4. Notable Findings

### PF >= 1.0 Configs by Bar Type

| Bar Type | Total Configs | PF >= 1.0 | PF < 1.0 | Best PF |
|----------|--------------|-----------|----------|---------|
| 250vol | 322 | 69 | 253 | 2.2037 |
| 250tick | 322 | 56 | 266 | 1.8413 |
| 10sec | 322 | 63 | 259 | 1.7218 |

### Cross-Bar-Type Profile Disagreement Analysis

Do the three bar types select different StepDist optima for the same profile?

| Profile | 250vol SD | 250tick SD | 10sec SD | All Agree? |
|---------|-----------|------------|----------|-----------|
| MAX_PROFIT | 7.0 | 4.5 | 10.0 | no |
| SAFEST | 1.0 | 5.0 | 10.0 | no |
| MOST_CONSISTENT | 7.0 | 4.5 | 10.0 | no |

---

## 5. Pure Reversal (MTP=1) Full Results

All 42 MTP=1 rows (14 StepDist values x 3 bar types). `max_level_exposure_pct=0` for all rows — confirmed no adds fired.

### 250vol

| StepDist | ML | MTP | Cycle PF | n_cycles | Total PnL (t) | calmar | worst_dd | win_sess% |
|----------|----|-----|----------|----------|--------------|--------|----------|-----------|
| 1.0 | 1 | 1 | 1.4822 | 592 | 2690 | 0.4905 | 5484 | 92.9 |
| 1.5 | 1 | 1 | 1.0087 | 404 | 44 | 0.0087 | 5077 | 93.3 |
| 2.0 | 1 | 1 | 1.4321 | 424 | 2312 | 0.4321 | 5350 | 92.9 |
| 2.5 | 1 | 1 | 1.6213 | 444 | 3324 | 0.6213 | 5350 | 92.9 |
| 3.0 | 1 | 1 | 0.9752 * | 276 | -124 | -0.0248 | 4990 | 93.3 |
| 3.5 | 1 | 1 | 1.0429 | 264 | 214 | 0.0429 | 4990 | 93.3 |
| 4.0 | 1 | 1 | 1.3317 | 278 | 1528 | 0.3317 | 4607 | 93.3 |
| 4.5 | 1 | 1 | 1.3419 | 266 | 1706 | 0.3419 | 4990 | 93.3 |
| 5.0 | 1 | 1 | 1.1287 | 208 | 642 | 0.1287 | 4990 | 92.9 |
| 5.5 | 1 | 1 | 1.6565 | 276 | 3446 | 0.6565 | 5249 | 92.9 |
| 6.0 | 1 | 1 | 1.2008 | 196 | 1010 | 0.2008 | 5030 | 92.9 |
| 7.0 | 1 | 1 | 1.1925 | 176 | 940 | 0.1925 | 4883 | 92.9 |
| 8.0 | 1 | 1 | 1.4219 | 178 | 1978 | 0.4219 | 4688 | 92.9 |
| 10.0 | 1 | 1 | 1.7522 | 190 | 3716 | 0.7522 | 4940 | 93.3 |

### 250tick

| StepDist | ML | MTP | Cycle PF | n_cycles | Total PnL (t) | calmar | worst_dd | win_sess% |
|----------|----|-----|----------|----------|--------------|--------|----------|-----------|
| 1.0 | 1 | 1 | 1.4861 | 580 | 2605 | 0.4937 | 5277 | 92.9 |
| 1.5 | 1 | 1 | 1.7368 | 588 | 4037 | 0.7368 | 5479 | 92.9 |
| 2.0 | 1 | 1 | 1.6145 | 500 | 3367 | 0.6145 | 5479 | 92.9 |
| 2.5 | 1 | 1 | 1.3148 | 388 | 1691 | 0.3148 | 5371 | 92.3 |
| 3.0 | 1 | 1 | 1.2297 | 330 | 1273 | 0.2297 | 5541 | 92.9 |
| 3.5 | 1 | 1 | 1.7204 | 418 | 3869 | 0.7204 | 5371 | 92.9 |
| 4.0 | 1 | 1 | 1.8376 | 384 | 4411 | 0.8376 | 5266 | 92.9 |
| 4.5 | 1 | 1 | 1.8413 | 360 | 4489 | 0.8413 | 5336 | 92.9 |
| 5.0 | 1 | 1 | 1.2154 | 214 | 1003 | 0.2154 | 4656 | 92.9 |
| 5.5 | 1 | 1 | 1.4867 | 244 | 2307 | 0.4867 | 4740 | 92.9 |
| 6.0 | 1 | 1 | 1.2537 | 202 | 1235 | 0.2537 | 4868 | 92.9 |
| 7.0 | 1 | 1 | 1.1935 | 172 | 931 | 0.1935 | 4812 | 92.9 |
| 8.0 | 1 | 1 | 1.2891 | 154 | 1391 | 0.2891 | 4812 | 92.9 |
| 10.0 | 1 | 1 | 1.3840 | 150 | 1939 | 0.3840 | 5050 | 92.9 |

### 10sec

| StepDist | ML | MTP | Cycle PF | n_cycles | Total PnL (t) | calmar | worst_dd | win_sess% |
|----------|----|-----|----------|----------|--------------|--------|----------|-----------|
| 1.0 | 1 | 1 | 0.8866 * | 200 | -627 | -0.1140 | 5502 | 88.9 |
| 1.5 | 1 | 1 | 0.8904 * | 268 | -603 | -0.1096 | 5502 | 88.9 |
| 2.0 | 1 | 1 | 0.8562 * | 162 | -791 | -0.1438 | 5502 | 88.9 |
| 2.5 | 1 | 1 | 0.9686 * | 200 | -175 | -0.0314 | 5576 | 88.9 |
| 3.0 | 1 | 1 | 0.9388 * | 176 | -341 | -0.0612 | 5576 | 88.9 |
| 3.5 | 1 | 1 | 0.9605 * | 198 | -219 | -0.0395 | 5540 | 88.9 |
| 4.0 | 1 | 1 | 0.9875 * | 192 | -69 | -0.0125 | 5540 | 88.9 |
| 4.5 | 1 | 1 | 0.9049 * | 152 | -521 | -0.0951 | 5481 | 88.9 |
| 5.0 | 1 | 1 | 0.8842 * | 138 | -637 | -0.1158 | 5502 | 88.9 |
| 5.5 | 1 | 1 | 1.1121 | 158 | 617 | 0.1121 | 5502 | 88.9 |
| 6.0 | 1 | 1 | 1.0314 | 142 | 173 | 0.0314 | 5502 | 88.9 |
| 7.0 | 1 | 1 | 1.1172 | 140 | 645 | 0.1172 | 5502 | 88.9 |
| 8.0 | 1 | 1 | 0.9057 * | 80 | -517 | -0.0943 | 5481 | 88.9 |
| 10.0 | 1 | 1 | 1.1021 | 100 | 557 | 0.1021 | 5455 | 88.9 |

*\* PF < 1.0*

---

*Report generated programmatically from sizing_sweep_P1a.tsv*