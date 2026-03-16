# TDS Calibration Report — Phase 03.1

## Overview

Hypothesis-driven TDS calibration with 3 targeted experiments (~99 total runs).
**Objective:** Identify which TDS detectors and thresholds provide survival benefit
(reduced worst-case drawdown) without excessive PnL degradation.

| Experiment | Description | Runs |
|-----------|-------------|------|
| 1 | Isolated detector test (4 detectors x 3 profiles x 3 bar types) | 36 |
| 2 | Drawdown budget sweep (6 thresholds x 3 profiles x 3 bar types) | 54 |
| 3 | Combined winner config (per combination) | 9 |
| **Total** | | **99** |

**Selection criteria:** Maximize `worst_dd_reduction + max_level_pct_reduction`.
**PnL guard:** Configs that degrade PnL by >20% vs baseline are excluded.
**Over-trigger flag:** Configs with >5% of cycles as TDS flattens are flagged.

---

## Experiment 1: Isolated Detector Analysis

Each detector was enabled individually with all others disabled at extreme thresholds.

**Notes:**
- Detector 1 (retracement): data-driven, no threshold. Only L1 can fire (step widen).
- Detector 2 (velocity): L1 fire when add velocity < 60s threshold.
- Detector 3 (consecutive_adds): L1 fire after 3 consecutive adds in same direction.
- Detector 4 (drawdown_budget): fires L3 directly (force flatten), never L1.

### bar_data_10sec_rot

| Profile | Detector | L1 Triggers | L3 Triggers | DD Reduction | PnL Impact | PnL Guard | Over-Trigger |
|---------|----------|------------|------------|-------------|------------|-----------|--------------|
| MAX_PROFIT | consecutive_adds | 64,203 | 0 | +0 | +95 | PASS | no |
| MAX_PROFIT | drawdown_budget | 0 | 2,264 | +13875 | -25170 | FAIL | YES |
| MAX_PROFIT | retracement | 49,057 | 0 | +0 | +0 | PASS | no |
| MAX_PROFIT | velocity | 49,739 | 0 | +575 | +259 | PASS | no |
| MOST_CONSISTENT | consecutive_adds | 64,203 | 0 | +0 | +95 | PASS | no |
| MOST_CONSISTENT | drawdown_budget | 0 | 2,264 | +13875 | -25170 | FAIL | YES |
| MOST_CONSISTENT | retracement | 49,057 | 0 | +0 | +0 | PASS | no |
| MOST_CONSISTENT | velocity | 49,739 | 0 | +575 | +259 | PASS | no |
| SAFEST | consecutive_adds | 67,472 | 0 | +0 | +0 | PASS | no |
| SAFEST | drawdown_budget | 0 | 2,265 | +4746 | -14530 | FAIL | YES |
| SAFEST | retracement | 56,365 | 0 | +0 | +0 | PASS | no |
| SAFEST | velocity | 56,365 | 0 | +0 | +0 | PASS | no |

### bar_data_250tick_rot

| Profile | Detector | L1 Triggers | L3 Triggers | DD Reduction | PnL Impact | PnL Guard | Over-Trigger |
|---------|----------|------------|------------|-------------|------------|-----------|--------------|
| MAX_PROFIT | consecutive_adds | 58,977 | 0 | +0 | -512 | PASS | no |
| MAX_PROFIT | drawdown_budget | 0 | 3,394 | +5181 | -25619 | FAIL | YES |
| MAX_PROFIT | retracement | 39,469 | 0 | +0 | +0 | PASS | no |
| MAX_PROFIT | velocity | 39,469 | 0 | +0 | +0 | PASS | no |
| MOST_CONSISTENT | consecutive_adds | 57,477 | 0 | +0 | +78 | PASS | no |
| MOST_CONSISTENT | drawdown_budget | 0 | 3,394 | +9499 | -28653 | FAIL | YES |
| MOST_CONSISTENT | retracement | 37,643 | 0 | +0 | +0 | PASS | no |
| MOST_CONSISTENT | velocity | 40,801 | 0 | -870 | -4231 | FAIL | no |
| SAFEST | consecutive_adds | 59,442 | 0 | -135 | -572 | FAIL | no |
| SAFEST | drawdown_budget | 0 | 3,394 | +4551 | -20509 | FAIL | YES |
| SAFEST | retracement | 38,587 | 0 | +0 | +0 | PASS | no |
| SAFEST | velocity | 38,587 | 0 | +0 | +0 | PASS | no |

### bar_data_250vol_rot

| Profile | Detector | L1 Triggers | L3 Triggers | DD Reduction | PnL Impact | PnL Guard | Over-Trigger |
|---------|----------|------------|------------|-------------|------------|-----------|--------------|
| MAX_PROFIT | consecutive_adds | 60,585 | 0 | +0 | -289 | PASS | no |
| MAX_PROFIT | drawdown_budget | 0 | 3,697 | +8426 | -32708 | FAIL | YES |
| MAX_PROFIT | retracement | 38,880 | 0 | +0 | +0 | PASS | no |
| MAX_PROFIT | velocity | 41,675 | 0 | -1130 | -7171 | FAIL | no |
| MOST_CONSISTENT | consecutive_adds | 60,585 | 0 | +0 | -289 | PASS | no |
| MOST_CONSISTENT | drawdown_budget | 0 | 3,697 | +8426 | -32708 | FAIL | YES |
| MOST_CONSISTENT | retracement | 38,880 | 0 | +0 | +0 | PASS | no |
| MOST_CONSISTENT | velocity | 41,675 | 0 | -1130 | -7171 | FAIL | no |
| SAFEST | consecutive_adds | 49,692 | 0 | +0 | +12358 | PASS | no |
| SAFEST | drawdown_budget | 0 | 3,696 | -531 | -25654 | FAIL | YES |
| SAFEST | retracement | 23,486 | 0 | +0 | +0 | PASS | no |
| SAFEST | velocity | 36,931 | 0 | -78003 | -77377 | FAIL | no |

### Experiment 1 Key Findings

**Per combination, best L1 detector (PnL guard passing):**

- **MAX_PROFIT/bar_data_10sec_rot**: `velocity` (dd_reduction=+575, pnl_impact=+259)
- **MOST_CONSISTENT/bar_data_10sec_rot**: `velocity` (dd_reduction=+575, pnl_impact=+259)
- **SAFEST/bar_data_10sec_rot**: `retracement` (dd_reduction=+0, pnl_impact=+0)
- **MAX_PROFIT/bar_data_250tick_rot**: `retracement` (dd_reduction=+0, pnl_impact=+0)
- **MOST_CONSISTENT/bar_data_250tick_rot**: `retracement` (dd_reduction=+0, pnl_impact=+0)
- **SAFEST/bar_data_250tick_rot**: `retracement` (dd_reduction=+0, pnl_impact=+0)
- **MAX_PROFIT/bar_data_250vol_rot**: `retracement` (dd_reduction=+0, pnl_impact=+0)
- **MOST_CONSISTENT/bar_data_250vol_rot**: `retracement` (dd_reduction=+0, pnl_impact=+0)
- **SAFEST/bar_data_250vol_rot**: `retracement` (dd_reduction=+0, pnl_impact=+0)

---

## Experiment 2: Drawdown Budget Sweep

Only Detector 4 (drawdown_budget) active. Swept thresholds: 30, 40, 50, 60, 80, 100 ticks.
Expected: tighter threshold → more L3 triggers → more PnL degradation → more DD reduction.

### bar_data_10sec_rot

| Profile | Threshold | L3 Triggers | DD Reduction | PnL Impact | PnL Guard | Over-Trigger |
|---------|-----------|------------|-------------|------------|-----------|--------------|
| MAX_PROFIT | 30 | 2,265 | +13895 | -24668 | FAIL | YES |
| MAX_PROFIT | 40 | 2,264 | +13775 | -23862 | FAIL | YES |
| MAX_PROFIT | 50 | 2,264 | +13875 | -25170 | FAIL | YES |
| MAX_PROFIT | 60 | 2,261 | +13777 | -25386 | FAIL | YES |
| MAX_PROFIT | 80 | 2,260 | +12771 | -26190 | FAIL | YES |
| MAX_PROFIT | 100 | 2,260 | +13489 | -23591 | FAIL | YES |
| MOST_CONSISTENT | 30 | 2,265 | +13895 | -24668 | FAIL | YES |
| MOST_CONSISTENT | 40 | 2,264 | +13775 | -23862 | FAIL | YES |
| MOST_CONSISTENT | 50 | 2,264 | +13875 | -25170 | FAIL | YES |
| MOST_CONSISTENT | 60 | 2,261 | +13777 | -25386 | FAIL | YES |
| MOST_CONSISTENT | 80 | 2,260 | +12771 | -26190 | FAIL | YES |
| MOST_CONSISTENT | 100 | 2,260 | +13489 | -23591 | FAIL | YES |
| SAFEST | 30 | 2,265 | +4746 | -14530 | FAIL | YES |
| SAFEST | 40 | 2,265 | +4746 | -14530 | FAIL | YES |
| SAFEST | 50 | 2,265 | +4746 | -14530 | FAIL | YES |
| SAFEST | 60 | 2,264 | +5118 | -14415 | FAIL | YES |
| SAFEST | 80 | 2,263 | +4742 | -15140 | FAIL | YES |
| SAFEST | 100 | 2,261 | +5349 | -12792 | FAIL | YES |

### bar_data_250tick_rot

| Profile | Threshold | L3 Triggers | DD Reduction | PnL Impact | PnL Guard | Over-Trigger |
|---------|-----------|------------|-------------|------------|-----------|--------------|
| MAX_PROFIT | 30 | 3,394 | +5181 | -25619 | FAIL | YES |
| MAX_PROFIT | 40 | 3,394 | +5181 | -25619 | FAIL | YES |
| MAX_PROFIT | 50 | 3,394 | +5181 | -25619 | FAIL | YES |
| MAX_PROFIT | 60 | 3,394 | +5209 | -24817 | FAIL | YES |
| MAX_PROFIT | 80 | 3,394 | +5217 | -23396 | FAIL | YES |
| MAX_PROFIT | 100 | 3,388 | +5181 | -25424 | FAIL | YES |
| MOST_CONSISTENT | 30 | 3,394 | +9489 | -29405 | FAIL | YES |
| MOST_CONSISTENT | 40 | 3,394 | +9489 | -29405 | FAIL | YES |
| MOST_CONSISTENT | 50 | 3,394 | +9499 | -28653 | FAIL | YES |
| MOST_CONSISTENT | 60 | 3,394 | +9475 | -28675 | FAIL | YES |
| MOST_CONSISTENT | 80 | 3,388 | +9470 | -26847 | FAIL | YES |
| MOST_CONSISTENT | 100 | 3,388 | +9440 | -29193 | FAIL | YES |
| SAFEST | 30 | 3,394 | +4551 | -20509 | FAIL | YES |
| SAFEST | 40 | 3,394 | +4551 | -20509 | FAIL | YES |
| SAFEST | 50 | 3,394 | +4551 | -20509 | FAIL | YES |
| SAFEST | 60 | 3,394 | +4501 | -22215 | FAIL | YES |
| SAFEST | 80 | 3,394 | +4501 | -22215 | FAIL | YES |
| SAFEST | 100 | 3,394 | +4530 | -21423 | FAIL | YES |

### bar_data_250vol_rot

| Profile | Threshold | L3 Triggers | DD Reduction | PnL Impact | PnL Guard | Over-Trigger |
|---------|-----------|------------|-------------|------------|-----------|--------------|
| MAX_PROFIT | 30 | 3,697 | +8368 | -33346 | FAIL | YES |
| MAX_PROFIT | 40 | 3,697 | +8368 | -33346 | FAIL | YES |
| MAX_PROFIT | 50 | 3,697 | +8426 | -32708 | FAIL | YES |
| MAX_PROFIT | 60 | 3,697 | +8426 | -32708 | FAIL | YES |
| MAX_PROFIT | 80 | 3,697 | +8420 | -32346 | FAIL | YES |
| MAX_PROFIT | 100 | 3,691 | +8368 | -33190 | FAIL | YES |
| MOST_CONSISTENT | 30 | 3,697 | +8368 | -33346 | FAIL | YES |
| MOST_CONSISTENT | 40 | 3,697 | +8368 | -33346 | FAIL | YES |
| MOST_CONSISTENT | 50 | 3,697 | +8426 | -32708 | FAIL | YES |
| MOST_CONSISTENT | 60 | 3,697 | +8426 | -32708 | FAIL | YES |
| MOST_CONSISTENT | 80 | 3,697 | +8420 | -32346 | FAIL | YES |
| MOST_CONSISTENT | 100 | 3,691 | +8368 | -33190 | FAIL | YES |
| SAFEST | 30 | 3,696 | -131 | -28391 | FAIL | YES |
| SAFEST | 40 | 3,696 | +77 | -25274 | FAIL | YES |
| SAFEST | 50 | 3,696 | -531 | -25654 | FAIL | YES |
| SAFEST | 60 | 3,696 | +45 | -25806 | FAIL | YES |
| SAFEST | 80 | 3,695 | -899 | -26020 | FAIL | YES |
| SAFEST | 100 | 3,695 | -1411 | -26803 | FAIL | YES |

---

## Experiment 3: Combined Config Validation

Per combination, the best L1 detector from Exp 1 + best L3 threshold from Exp 2 combined.

| Profile | Source | Combined Config | DD Reduction | PnL Impact | PnL Guard | Over-Trigger | vs Best Solo |
|---------|--------|----------------|-------------|------------|-----------|--------------|--------------|
| MAX_PROFIT | bar_data_10sec_rot | combined_velocity_dd100.0 | +13489 | -23591 | FAIL | YES | +12914 |
| MAX_PROFIT | bar_data_250tick_rot | combined_retracement_dd80.0 | +5217 | -23396 | FAIL | YES | +5217 |
| MAX_PROFIT | bar_data_250vol_rot | combined_retracement_dd80.0 | +8420 | -32346 | FAIL | YES | +8420 |
| MOST_CONSISTENT | bar_data_10sec_rot | combined_velocity_dd100.0 | +13489 | -23591 | FAIL | YES | +12914 |
| MOST_CONSISTENT | bar_data_250tick_rot | combined_retracement_dd80.0 | +9470 | -26847 | FAIL | YES | +9470 |
| MOST_CONSISTENT | bar_data_250vol_rot | combined_retracement_dd80.0 | +8420 | -32346 | FAIL | YES | +8420 |
| SAFEST | bar_data_10sec_rot | combined_retracement_dd100.0 | +5349 | -12792 | FAIL | YES | +5349 |
| SAFEST | bar_data_250tick_rot | combined_retracement_dd30.0 | +4551 | -20509 | FAIL | YES | +4551 |
| SAFEST | bar_data_250vol_rot | combined_retracement_dd40.0 | +77 | -25274 | FAIL | YES | +77 |

---

## Final Selection: Best TDS Config Per Combination

| Profile | Source | Selected From | DD Reduction | PnL Impact | PnL Guard | Over-Trigger |
|---------|--------|--------------|-------------|------------|-----------|--------------|
| MAX_PROFIT | bar_data_10sec_rot | exp1_velocity | +575 | +259 | PASS | no |
| MAX_PROFIT | bar_data_250tick_rot | exp1_retracement | +0 | +0 | PASS | no |
| MAX_PROFIT | bar_data_250vol_rot | exp1_retracement | +0 | +0 | PASS | no |
| MOST_CONSISTENT | bar_data_10sec_rot | exp1_velocity | +575 | +259 | PASS | no |
| MOST_CONSISTENT | bar_data_250tick_rot | exp1_retracement | +0 | +0 | PASS | no |
| MOST_CONSISTENT | bar_data_250vol_rot | exp1_retracement | +0 | +0 | PASS | no |
| SAFEST | bar_data_10sec_rot | exp1_retracement | +0 | +0 | PASS | no |
| SAFEST | bar_data_250tick_rot | exp1_retracement | +0 | +0 | PASS | no |
| SAFEST | bar_data_250vol_rot | exp1_retracement | +0 | +0 | PASS | no |

---

## Key Observations

1. **Drawdown budget (L3) over-triggers in all configurations**: The L3 force-flatten mechanism
   converts the majority of the dataset into TDS-controlled cycles, catastrophically destroying PnL.
   This means the tested thresholds [30-100 ticks] are all too aggressive for the P1a data patterns.

2. **L1 detectors (velocity, consecutive_adds) show limited effect**: Most L1 triggers fire
   but do not materially reduce worst_cycle_dd. Only velocity shows any meaningful benefit
   in 10sec bar type where add velocity is more variable.

3. **Retracement detector is effectively a no-op**: L1 triggers fire but produce zero
   worst_dd_reduction, meaning the step-widening response does not prevent cycles from
   reaching the same worst-case loss level.

4. **Phase 04 recommendation**: Use `velocity` detector for 10sec bar types where it shows
   positive benefit. For vol/tick bar types, consider TDS disabled or at very high drawdown
   thresholds (>200 ticks) that don't over-trigger. The current calibrated configs will be
   provided per combination, but Phase 04 combination testing should validate these findings.
