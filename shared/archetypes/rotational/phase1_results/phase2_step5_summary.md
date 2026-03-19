# Phase 2 Final Config — V1.4 Summary

## Layered Improvement Table

| Layer | Config | Net PF | Net PnL | Cycles | Improvement |
|-------|--------|--------|---------|--------|-------------|
| 0 | Phase 1 base (10:00, no SR, no filters) | 1.0680 | +12,235 | 2,803 | — |
| 1 | + SpeedRead (Roll50 >= 48, seed+rev) | 1.1997 | +20,919 | 1,847 | +12.3% NPF, +71% PnL |
| — | Feature filters | — | — | — | Not adopted (overfitting risk) |
| — | Risk mitigation (4A/4C) | — | — | — | Deferred to Phase 2.5 (needs sim changes) |

## Frozen V1.4 Config

- **Type:** Adaptive (rolling zigzag percentile)
- **StepDist:** P90 of rolling 200-swing zigzag (floor 10)
- **AddDist:** P75 of rolling 200-swing zigzag (floor 10)
- **SeedDist:** 15 pts fixed (decoupled)
- **ML:** 1 (all adds = 1 contract)
- **Position Cap:** 2 (cap-walk at StepDist)
- **Session:** 10:00-16:00 ET
- **Watch Mode:** rth_open (first tick at 09:30, but no seeds until 10:00)
- **SpeedRead:** Rolling 50-tick avg >= 48 (seed AND reversal)
- **Cap Action:** walk (anchor walks at cap)
- **Cost:** 1 tick per side

## Key Decisions

1. **10:00 start** (skip Open block): Open has NPF=0.83, 29.6% cap-walk rate. Removing it improved PnL by +50%.
2. **Rev SR filter is primary driver:** Seed-only SR adds <1% NPF. Both seed+rev at SR>=48 adds +10%.
3. **Rolling 50-tick SR avg** beats point-in-time by +2.1% NPF (smooths out spiky readings).
4. **No feature filters adopted:** 16/17 features pass 3% threshold but with non-monotonic quintile patterns and only 59 sessions. Overfitting risk too high.
5. **Risk mitigation deferred:** Cap-walk limit (max CW=3) and adaptive stop (2.5σ) show strong potential but need simulator-level implementation.

## Phase 2.5 Queue (Simulator Enhancements)

1. Max cap-walks per cycle = 3 (flatten if exceeded)
2. Adaptive cycle stop = 2.5 * rolling zigzag std
3. Clock-time rolling zigzag window (last 60 min vs 200-swing count)

## Files

- `phase2_final_config.json` — Complete frozen config
- `full_p1_base_cycles_10am.parquet` — Cycle dataset (2,814 raw, 2,803 filtered)
- `phase2_step1_sr_results.json` — SR threshold sweep
- `phase2_step2_hysteresis_results.json` — Rolling SR analysis
- `phase2_feature_discovery.json` — 17-feature quintile analysis
- `phase2_step4_risk_results.json` — Risk mitigation (4A/4B/4C)
