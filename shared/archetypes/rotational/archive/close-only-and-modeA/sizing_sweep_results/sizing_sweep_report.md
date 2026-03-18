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
| Configs with PF >= 1.0 | 610 (63.1%) |
| Configs with PF < 1.0 | 356 (36.9%) |

### Best Config per Bar Type (by Cycle PF)

| Bar Type | StepDist | MaxLevels | MTP | Cycle PF | Total PnL (ticks) |
|----------|----------|-----------|-----|----------|-------------------|
| 250vol | 5.0 | 1 | 4 | 8.0641 | 135518 |
| 250tick | 5.5 | 1 | 4 | 10.4816 | 173646 |
| 10sec | 5.0 | 1 | 4 | 6.8348 | 80194 |

---

## 2. Profile Selections — Top 3 Candidates per Bar Type

### 2.1 Profile: MAX_PROFIT

*Highest cycle PF regardless of risk*

**250vol:**

| Rank | StepDist | MaxLevels | MTP | cycle_pf | total_pnl_ticks | worst_cycle_dd | calmar_ratio | PF<1? |
|---|---|---|---|---|---|---|---|---|
| 1 | 5.0 | 1 | 4 | 8.0641 | 135518 | 16256 | 8.3365 | no |
| 2 | 5.0 | 2 | 4 | 8.0641 | 135518 | 16256 | 8.3365 | no |
| 3 | 5.0 | 3 | 4 | 8.0641 | 135518 | 16256 | 8.3365 | no |

**250tick:**

| Rank | StepDist | MaxLevels | MTP | cycle_pf | total_pnl_ticks | worst_cycle_dd | calmar_ratio | PF<1? |
|---|---|---|---|---|---|---|---|---|
| 1 | 5.5 | 1 | 4 | 10.4816 | 173646 | 16758 | 10.3620 | no |
| 2 | 5.5 | 2 | 4 | 10.4816 | 173646 | 16758 | 10.3620 | no |
| 3 | 5.5 | 3 | 4 | 10.4816 | 173646 | 16758 | 10.3620 | no |

**10sec:**

| Rank | StepDist | MaxLevels | MTP | cycle_pf | total_pnl_ticks | worst_cycle_dd | calmar_ratio | PF<1? |
|---|---|---|---|---|---|---|---|---|
| 1 | 5.0 | 1 | 4 | 6.8348 | 80194 | 11708 | 6.8495 | no |
| 2 | 5.0 | 2 | 4 | 6.8348 | 80194 | 11708 | 6.8495 | no |
| 3 | 5.0 | 3 | 4 | 6.8348 | 80194 | 11708 | 6.8495 | no |

### 2.2 Profile: SAFEST

*Best survival metrics — minimise worst-case single-cycle loss*

**250vol:**

| Rank | StepDist | MaxLevels | MTP | worst_cycle_dd | max_level_exposure_pct | tail_ratio | cycle_pf | PF<1? |
|---|---|---|---|---|---|---|---|---|
| 1 | 10.0 | 1 | 1 | 4909.0000 | 0.0000 | 0.0069 | 2.2648 | no |
| 2 | 8.0 | 1 | 1 | 4917.0000 | 0.0000 | 0.0053 | 2.8290 | no |
| 3 | 7.0 | 1 | 1 | 4921.0000 | 0.0000 | 0.0045 | 3.0534 | no |

**250tick:**

| Rank | StepDist | MaxLevels | MTP | worst_cycle_dd | max_level_exposure_pct | tail_ratio | cycle_pf | PF<1? |
|---|---|---|---|---|---|---|---|---|
| 1 | 10.0 | 1 | 1 | 4903.0000 | 0.0000 | 0.0069 | 2.6282 | no |
| 2 | 8.0 | 1 | 1 | 4911.0000 | 0.0000 | 0.0053 | 2.6524 | no |
| 3 | 7.0 | 1 | 1 | 4915.0000 | 0.0000 | 0.0045 | 2.8334 | no |

**10sec:**

| Rank | StepDist | MaxLevels | MTP | worst_cycle_dd | max_level_exposure_pct | tail_ratio | cycle_pf | PF<1? |
|---|---|---|---|---|---|---|---|---|
| 1 | 10.0 | 1 | 1 | 4672.0000 | 0.0000 | 0.0073 | 3.1657 | no |
| 2 | 8.0 | 1 | 1 | 4680.0000 | 0.0000 | 0.0056 | 3.1944 | no |
| 3 | 7.0 | 1 | 1 | 4684.0000 | 0.0000 | 0.0047 | 2.9919 | no |

### 2.3 Profile: MOST_CONSISTENT

*Best risk-adjusted returns — maximise calmar and consistency*

**250vol:**

| Rank | StepDist | MaxLevels | MTP | calmar_ratio | winning_session_pct | max_dd_duration_bars | cycle_pf | PF<1? |
|---|---|---|---|---|---|---|---|---|
| 1 | 5.0 | 1 | 4 | 8.3365 | 94.1200 | 14409 | 8.0641 | no |
| 2 | 5.0 | 2 | 4 | 8.3365 | 94.1200 | 14409 | 8.0641 | no |
| 3 | 5.0 | 3 | 4 | 8.3365 | 94.1200 | 14409 | 8.0641 | no |

**250tick:**

| Rank | StepDist | MaxLevels | MTP | calmar_ratio | winning_session_pct | max_dd_duration_bars | cycle_pf | PF<1? |
|---|---|---|---|---|---|---|---|---|
| 1 | 5.0 | 1 | 8 | 11.5973 | 95.2400 | 15732 | 8.3524 | no |
| 2 | 5.0 | 2 | 8 | 11.5973 | 95.2400 | 15732 | 8.3524 | no |
| 3 | 5.0 | 3 | 8 | 11.5973 | 95.2400 | 15732 | 8.3524 | no |

**10sec:**

| Rank | StepDist | MaxLevels | MTP | calmar_ratio | winning_session_pct | max_dd_duration_bars | cycle_pf | PF<1? |
|---|---|---|---|---|---|---|---|---|
| 1 | 5.0 | 1 | 4 | 6.8495 | 93.3300 | 16305 | 6.8348 | no |
| 2 | 5.0 | 2 | 4 | 6.8495 | 93.3300 | 16305 | 6.8348 | no |
| 3 | 5.0 | 3 | 4 | 6.8495 | 93.3300 | 16305 | 6.8348 | no |

---

## 3. Pure Reversal (MTP=1) vs Best Martingale

Pure reversal means MaxTotalPosition=1: the position never adds, so martingale levels are irrelevant. These rows have `max_level_exposure_pct=0` (confirmed).

| Bar Type | Best MTP=1 PF | Best MTP=1 SD | Best Martingale PF | Martingale SD/ML/MTP | Martingale Wins? |
|----------|--------------|--------------|-------------------|---------------------|-----------------|
| 250vol | 3.0534 | SD=7.0 | 8.0641 | SD=5.0 ML=1 MTP=4 | YES |
| 250tick | 2.8334 | SD=7.0 | 10.4816 | SD=5.5 ML=1 MTP=4 | YES |
| 10sec | 3.1944 | SD=8.0 | 6.8348 | SD=5.0 ML=1 MTP=4 | YES |

---

## 4. Notable Findings

### PF >= 1.0 Configs by Bar Type

| Bar Type | Total Configs | PF >= 1.0 | PF < 1.0 | Best PF |
|----------|--------------|-----------|----------|---------|
| 250vol | 322 | 223 | 99 | 8.0641 |
| 250tick | 322 | 222 | 100 | 10.4816 |
| 10sec | 322 | 165 | 157 | 6.8348 |

### Cross-Bar-Type Profile Disagreement Analysis

Do the three bar types select different StepDist optima for the same profile?

| Profile | 250vol SD | 250tick SD | 10sec SD | All Agree? |
|---------|-----------|------------|----------|-----------|
| MAX_PROFIT | 5.0 | 5.5 | 5.0 | no |
| SAFEST | 10.0 | 10.0 | 10.0 | YES |
| MOST_CONSISTENT | 5.0 | 5.0 | 5.0 | YES |

---

## 5. Pure Reversal (MTP=1) Full Results

All 42 MTP=1 rows (14 StepDist values x 3 bar types). `max_level_exposure_pct=0` for all rows — confirmed no adds fired.

### 250vol

| StepDist | ML | MTP | Cycle PF | n_cycles | Total PnL (t) | calmar | worst_dd | win_sess% |
|----------|----|-----|----------|----------|--------------|--------|----------|-----------|
| 1.0 | 1 | 1 | 0.0000 * | 1350 | -7643 | -1.0003 | 4945 | 0.0 |
| 1.5 | 1 | 1 | 0.0000 * | 1352 | -4943 | -1.0000 | 4943 | 0.0 |
| 2.0 | 1 | 1 | 0.5452 * | 1348 | -2247 | -0.4548 | 4941 | 93.3 |
| 2.5 | 1 | 1 | 1.1152 | 1378 | 569 | 0.1152 | 4939 | 93.3 |
| 3.0 | 1 | 1 | 1.6152 | 1330 | 3037 | 0.6152 | 4937 | 93.3 |
| 3.5 | 1 | 1 | 1.9988 | 1234 | 4929 | 0.9988 | 4935 | 93.3 |
| 4.0 | 1 | 1 | 2.4062 | 1188 | 6937 | 1.4062 | 4933 | 93.3 |
| 4.5 | 1 | 1 | 2.7037 | 1112 | 8401 | 1.7037 | 4931 | 93.3 |
| 5.0 | 1 | 1 | 2.9454 | 1038 | 9589 | 1.9454 | 4929 | 93.3 |
| 5.5 | 1 | 1 | 2.8934 | 892 | 9329 | 1.8934 | 4927 | 93.3 |
| 6.0 | 1 | 1 | 2.8910 | 792 | 9313 | 1.8910 | 4925 | 92.9 |
| 7.0 | 1 | 1 | 3.0534 | 684 | 10105 | 2.0534 | 4921 | 92.9 |
| 8.0 | 1 | 1 | 2.8290 | 536 | 8993 | 1.8290 | 4917 | 92.9 |
| 10.0 | 1 | 1 | 2.2648 | 328 | 6209 | 1.2648 | 4909 | 92.9 |

### 250tick

| StepDist | ML | MTP | Cycle PF | n_cycles | Total PnL (t) | calmar | worst_dd | win_sess% |
|----------|----|-----|----------|----------|--------------|--------|----------|-----------|
| 1.0 | 1 | 1 | 0.0000 * | 1066 | -7069 | -1.0003 | 4939 | 0.0 |
| 1.5 | 1 | 1 | 0.0000 * | 1198 | -4937 | -1.0000 | 4937 | 0.0 |
| 2.0 | 1 | 1 | 0.4932 * | 1218 | -2501 | -0.5068 | 4935 | 93.3 |
| 2.5 | 1 | 1 | 0.9511 * | 1174 | -241 | -0.0489 | 4933 | 93.3 |
| 3.0 | 1 | 1 | 1.4395 | 1184 | 2167 | 0.4395 | 4931 | 93.3 |
| 3.5 | 1 | 1 | 1.8811 | 1160 | 4343 | 0.8811 | 4929 | 93.3 |
| 4.0 | 1 | 1 | 2.2630 | 1116 | 6223 | 1.2630 | 4927 | 93.3 |
| 4.5 | 1 | 1 | 2.5218 | 1036 | 7495 | 1.5218 | 4925 | 93.3 |
| 5.0 | 1 | 1 | 2.7158 | 956 | 8447 | 1.7158 | 4923 | 93.3 |
| 5.5 | 1 | 1 | 2.7214 | 838 | 8471 | 1.7214 | 4921 | 93.3 |
| 6.0 | 1 | 1 | 2.7847 | 762 | 8779 | 1.7847 | 4919 | 92.9 |
| 7.0 | 1 | 1 | 2.8334 | 634 | 9011 | 1.8334 | 4915 | 92.9 |
| 8.0 | 1 | 1 | 2.6524 | 502 | 8115 | 1.6524 | 4911 | 92.9 |
| 10.0 | 1 | 1 | 2.6282 | 380 | 7983 | 1.6282 | 4903 | 92.9 |

### 10sec

| StepDist | ML | MTP | Cycle PF | n_cycles | Total PnL (t) | calmar | worst_dd | win_sess% |
|----------|----|-----|----------|----------|--------------|--------|----------|-----------|
| 1.0 | 1 | 1 | 0.0000 * | 964 | -6634 | -1.0003 | 4708 | 0.0 |
| 1.5 | 1 | 1 | 0.0000 * | 1082 | -4706 | -1.0000 | 4706 | 0.0 |
| 2.0 | 1 | 1 | 0.4613 * | 1086 | -2534 | -0.5387 | 4704 | 92.3 |
| 2.5 | 1 | 1 | 0.8175 * | 962 | -858 | -0.1825 | 4702 | 92.3 |
| 3.0 | 1 | 1 | 1.2319 | 966 | 1090 | 0.2319 | 4700 | 92.3 |
| 3.5 | 1 | 1 | 1.5206 | 894 | 2446 | 0.5206 | 4698 | 92.3 |
| 4.0 | 1 | 1 | 1.8548 | 872 | 4014 | 0.8548 | 4696 | 92.3 |
| 4.5 | 1 | 1 | 2.1602 | 846 | 5446 | 1.1602 | 4694 | 92.3 |
| 5.0 | 1 | 1 | 2.3900 | 802 | 6522 | 1.3900 | 4692 | 92.3 |
| 5.5 | 1 | 1 | 2.7190 | 798 | 8062 | 1.7190 | 4690 | 92.3 |
| 6.0 | 1 | 1 | 2.7069 | 706 | 8002 | 1.7069 | 4688 | 92.3 |
| 7.0 | 1 | 1 | 2.9919 | 638 | 9330 | 1.9919 | 4684 | 92.3 |
| 8.0 | 1 | 1 | 3.1944 | 576 | 10270 | 2.1944 | 4680 | 92.3 |
| 10.0 | 1 | 1 | 3.1657 | 436 | 10118 | 2.1657 | 4672 | 92.3 |

*\* PF < 1.0*

---

*Report generated programmatically from sizing_sweep_P1a.tsv*