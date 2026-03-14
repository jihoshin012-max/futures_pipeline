# archetype: zone_touch
# Simulation Rules — zone_touch archetype
last_reviewed: 2026-03-14
# Read before modifying exit params. Describes what the simulator supports — do not modify.

## Entry Mechanics
- Entry price comes from `touch_row.TouchPrice`.
- Direction comes from `touch_row.ApproachDir` (Long / Short).
- Mode (M1, M3, M4, M5) is assigned by the routing waterfall before simulation begins.
- `bar_offset` is the integer index into `bar_df` that corresponds to the touch entry bar.

## Exit Mechanics
- **Multi-leg mode (M1):** `leg_targets` is a list of tick targets. Each leg exits a proportional fraction of the position when MFE reaches that target. All legs share the same stop.
- **Single-leg mode (M3, M4, M5):** `leg_targets` has one entry. Full position exits at that target.
- `stop_ticks`: initial stop distance from entry, fixed at trade open.
- Stop loss triggers if price moves `stop_ticks` against entry before any target fills.

## Trail Mechanics
- `trail_steps` is a list of `{trigger_ticks, new_stop_ticks}` pairs, ordered by ascending `trigger_ticks`.
- When MFE (max favorable excursion in ticks) reaches `trigger_ticks`, the stop ratchets to `entry ± new_stop_ticks`.
- Stop never moves against the trade — it only ratchets in the favorable direction.
- **Breakeven (BE):** `trail_steps[0]` with `new_stop_ticks=0` moves the stop to entry. There is no separate `be_trigger_ticks` field.
- If `trail_steps` is empty, stop remains fixed at `stop_ticks` for the life of the trade.

## Time Cap
- If neither target nor stop is reached within `time_cap_bars` bars after entry, the trade exits at market.
- `exit_reason` is set to `"time_cap"` for these exits.
- `pnl_ticks` is calculated as the bar's close price relative to entry at the time cap bar.

## Cost Model
- `cost_ticks` is read from `_config/instruments.md` at engine startup — never hardcoded.
- Individual trade `pnl_ticks` in `SimResult` is RAW (no cost deduction).
- Cost is applied during metrics aggregation in the engine: `net_pnl = pnl_ticks - cost_ticks` per trade.
- PF is computed on net P&L values.

## SimResult Contract
- Simulator is a pure function — no I/O, no global state, no random calls.
- Interface: `def run(bar_df, touch_row, config, bar_offset) -> SimResult`
- Returns: `SimResult(pnl_ticks: float, win: bool, exit_reason: str, bars_held: int)`
- `exit_reason` values: `"target_1"`, `"target_2"`, `"target_3"`, `"stop"`, `"time_cap"`
- `win` is `True` if `pnl_ticks > 0` after any partial fills; `False` otherwise.
