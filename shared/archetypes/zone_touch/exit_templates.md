# Exit Templates
last_reviewed: 2026-03-13
# Reference patterns for exit structure. Agent reads before proposing param changes.
# Do not modify these templates — they describe what the simulator supports.

## Multi-leg partial exit (if archetype supports multiple targets)
- Leg 1: smallest target — earliest exit, highest probability
- Leg 2: mid target — core of the trade
- Leg 3: largest target — runner leg (add/remove legs per archetype design)
- All legs share same stop. BE trigger activates after first leg fills.
- Trail applies after BE trigger: trigger price → new stop level.
- Time cap: if no fill by time_cap_bars, exit at market.

## Single-leg exit (if archetype supports single-target mode)
- One target, one stop.
- BE trigger: trail_steps[0] with new_stop_ticks=0 moves stop to entry (zero risk).
- Time cap: same pattern as multi-leg.

## Trail mechanics + BE (unified)
- trail_steps is a list of {trigger_ticks, new_stop_ticks} pairs
- Once MFE hits trigger_ticks, stop ratchets to new_stop_ticks above entry — never moves back
- BE is trail_steps[0] where new_stop_ticks=0 (stop moves to entry = zero risk)
- There is no separate be_trigger_ticks field — trail_steps[0] IS the BE trigger
- Agent may vary step count (1–6) and trigger/new_stop values within validation rules

## Optimization surface (what agent varies in Stage 04)
- stop_ticks, targets, trail_steps (full array), time_cap_bars
- FIXED: cost_ticks, score thresholds, any archetype-specific filter configs, simulator_module
