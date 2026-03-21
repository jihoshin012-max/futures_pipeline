# archetype: rotational
"""Cycle logger — enriched cycle log schema for the multi-approach rotation simulator.

Each completed cycle produces one row with standard metrics, regime context
(looked up from pre-computed bar data), and shadow metrics.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pandas as pd


# Column schema for the V1.1 cycle log DataFrame
CYCLE_COLUMNS = [
    # Config identification
    "config_id", "approach", "step_dist", "add_dist", "confirm_dist",
    # Cycle identification
    "cycle_id", "start_time", "end_time", "duration_bars", "duration_minutes",
    "start_bar_idx", "end_bar_idx",
    # Position
    "side", "add_count", "exit_position",
    # PnL
    "pnl_ticks_gross", "pnl_ticks_net",
    # Excursion
    "mfe_points", "mae_points",
    # Regime context (from pre-computed bar data at cycle start)
    "atr_20bar", "atr_percentile",
    "swing_median_20", "swing_p90_20",
    "directional_persistence",
    "bar_range_median_20",
    # Shadow metrics
    "would_flatten_reseed", "half_block_profit",
]

# Column schema for the frozen-anchor cycle log DataFrame
FA_CYCLE_COLUMNS = [
    # Config identification
    "config_id", "step_dist", "add_dist", "max_adds", "reversal_target",
    # Cycle identification
    "cycle_id", "start_time", "end_time", "duration_bars", "duration_minutes",
    "start_bar_idx", "end_bar_idx",
    # Position
    "side", "add_count", "exit_position",
    # PnL
    "pnl_ticks_gross", "pnl_ticks_net",
    # Excursion
    "mfe_points", "mae_points",
    # Regime context (from pre-computed bar data at cycle start)
    "atr_20bar", "atr_percentile",
    "swing_median_20", "swing_p90_20",
    "directional_persistence",
    "bar_range_median_20",
    # New frozen-anchor columns
    "exit_type",               # SUCCESS | FAILURE | SESSION_END
    "progress_hwm",            # Max favorable progress as % of step_dist
    "time_between_adds",       # Comma-separated bar counts between adds
    "cycle_day_seq",           # 1-based sequence within trading day
    "cycle_start_hour",        # Integer hour (9-15)
    "progress_at_adds",        # Comma-separated % of StepDist at each add
    "prev_cycle_exit_type",    # SUCCESS | FAILURE | SESSION_START
    "cycle_waste_pct",         # total abs movement / net displacement
    # Pullback entry columns (populated when entry_mode="pullback")
    "entry_type",              # IMMEDIATE | PULLBACK
    "direction_detect_time",   # Timestamp when direction first detected
    "confirming_duration_bars",  # Bars from detection to pullback entry
    "hwm_at_entry",            # Extension from WatchPrice to HWM (points)
    "pullback_depth_pct",      # Pullback from HWM as % of extension
    "runaway_flag",            # True if hwm_at_entry > 2 × StepDist
    "remaining_to_parent_target",  # Distance from entry to parent target (NULL for post-exit)
    # Shadow metrics
    "would_flatten_reseed", "half_block_profit",
]

# Column schema for missed entries (pullback entry mode)
FA_MISSED_COLUMNS = [
    "config_id", "date", "direction_detect_time", "direction",
    "hwm_reached", "exit_reason", "hypothetical_immediate_pnl",
]


@dataclass
class CycleRecord:
    """One completed cycle's full record."""

    # Config
    config_id: str = ""
    approach: str = ""
    step_dist: float = 0.0
    add_dist: float = 0.0
    confirm_dist: float = 0.0

    # Cycle
    cycle_id: int = 0
    start_time: object = None
    end_time: object = None
    duration_bars: int = 0
    duration_minutes: float = 0.0
    start_bar_idx: int = 0
    end_bar_idx: int = 0

    # Position
    side: str = ""          # "LONG" or "SHORT"
    add_count: int = 0
    exit_position: int = 0  # total contracts at exit

    # PnL
    pnl_ticks_gross: float = 0.0       # qty-weighted: (exit-avg)/tick * total_qty
    pnl_ticks_net: float = 0.0         # gross minus costs
    pnl_ticks_per_unit: float = 0.0    # per-unit: (exit-avg)/tick (no qty multiplier)

    # Excursion (in points, not ticks)
    mfe_points: float = 0.0
    mae_points: float = 0.0

    # Regime context
    atr_20bar: float = np.nan
    atr_percentile: float = np.nan
    swing_median_20: float = np.nan
    swing_p90_20: float = np.nan
    directional_persistence: int = 0
    bar_range_median_20: float = np.nan

    # Shadow metrics
    would_flatten_reseed: bool = False
    half_block_profit: Optional[float] = None

    def to_dict(self) -> dict:
        return {
            "config_id": self.config_id,
            "approach": self.approach,
            "step_dist": self.step_dist,
            "add_dist": self.add_dist,
            "confirm_dist": self.confirm_dist,
            "cycle_id": self.cycle_id,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "duration_bars": self.duration_bars,
            "duration_minutes": self.duration_minutes,
            "start_bar_idx": self.start_bar_idx,
            "end_bar_idx": self.end_bar_idx,
            "side": self.side,
            "add_count": self.add_count,
            "exit_position": self.exit_position,
            "pnl_ticks_gross": self.pnl_ticks_gross,
            "pnl_ticks_net": self.pnl_ticks_net,
            "pnl_ticks_per_unit": self.pnl_ticks_per_unit,
            "mfe_points": self.mfe_points,
            "mae_points": self.mae_points,
            "atr_20bar": self.atr_20bar,
            "atr_percentile": self.atr_percentile,
            "swing_median_20": self.swing_median_20,
            "swing_p90_20": self.swing_p90_20,
            "directional_persistence": self.directional_persistence,
            "bar_range_median_20": self.bar_range_median_20,
            "would_flatten_reseed": self.would_flatten_reseed,
            "half_block_profit": self.half_block_profit,
        }


class CycleLog:
    """Accumulate cycle records and produce a DataFrame."""

    def __init__(self) -> None:
        self._records: list[dict] = []

    def append(self, record: CycleRecord) -> None:
        self._records.append(record.to_dict())

    def to_dataframe(self) -> pd.DataFrame:
        if not self._records:
            return pd.DataFrame(columns=CYCLE_COLUMNS)
        return pd.DataFrame(self._records)

    def __len__(self) -> int:
        return len(self._records)


# =========================================================================
# Frozen-anchor cycle record
# =========================================================================

@dataclass
class FACycleRecord:
    """One completed cycle from the frozen-anchor simulator."""

    # Config
    config_id: str = ""
    step_dist: float = 0.0
    add_dist: float = 0.0
    max_adds: int = 0
    reversal_target: float = 1.0

    # Cycle
    cycle_id: int = 0
    start_time: object = None
    end_time: object = None
    duration_bars: int = 0
    duration_minutes: float = 0.0
    start_bar_idx: int = 0
    end_bar_idx: int = 0

    # Position
    side: str = ""          # "LONG" or "SHORT"
    add_count: int = 0
    exit_position: int = 0  # total contracts at exit

    # PnL
    pnl_ticks_gross: float = 0.0
    pnl_ticks_net: float = 0.0

    # Excursion (in points, not ticks)
    mfe_points: float = 0.0
    mae_points: float = 0.0

    # Regime context
    atr_20bar: float = np.nan
    atr_percentile: float = np.nan
    swing_median_20: float = np.nan
    swing_p90_20: float = np.nan
    directional_persistence: int = 0
    bar_range_median_20: float = np.nan

    # New frozen-anchor columns
    exit_type: str = ""                         # SUCCESS | FAILURE
    progress_hwm: float = 0.0                   # Max favorable progress as % of step_dist
    time_between_adds: str = ""                  # Comma-separated bar counts
    cycle_day_seq: int = 0                       # 1-based per day
    cycle_start_hour: int = 0                    # Integer hour (9-15)
    progress_at_adds: str = ""                   # Comma-separated % of StepDist
    prev_cycle_exit_type: str = "SESSION_START"  # SUCCESS | FAILURE | SESSION_START
    cycle_waste_pct: float = 0.0                 # total abs movement / net displacement

    # Pullback entry columns
    entry_type: str = "IMMEDIATE"                   # IMMEDIATE | PULLBACK
    direction_detect_time: object = None             # When direction first detected
    confirming_duration_bars: int = 0                # Bars from detection to entry
    hwm_at_entry: float = 0.0                        # Extension points from WatchPrice
    pullback_depth_pct: float = 0.0                  # Pullback / extension × 100
    runaway_flag: bool = False                       # hwm_at_entry > 2 × StepDist
    remaining_to_parent_target: Optional[float] = None  # Distance to parent target

    # Shadow metrics
    would_flatten_reseed: bool = False
    half_block_profit: Optional[float] = None

    def to_dict(self) -> dict:
        return {
            "config_id": self.config_id,
            "step_dist": self.step_dist,
            "add_dist": self.add_dist,
            "max_adds": self.max_adds,
            "reversal_target": self.reversal_target,
            "cycle_id": self.cycle_id,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "duration_bars": self.duration_bars,
            "duration_minutes": self.duration_minutes,
            "start_bar_idx": self.start_bar_idx,
            "end_bar_idx": self.end_bar_idx,
            "side": self.side,
            "add_count": self.add_count,
            "exit_position": self.exit_position,
            "pnl_ticks_gross": self.pnl_ticks_gross,
            "pnl_ticks_net": self.pnl_ticks_net,
            "mfe_points": self.mfe_points,
            "mae_points": self.mae_points,
            "atr_20bar": self.atr_20bar,
            "atr_percentile": self.atr_percentile,
            "swing_median_20": self.swing_median_20,
            "swing_p90_20": self.swing_p90_20,
            "directional_persistence": self.directional_persistence,
            "bar_range_median_20": self.bar_range_median_20,
            "exit_type": self.exit_type,
            "progress_hwm": self.progress_hwm,
            "time_between_adds": self.time_between_adds,
            "cycle_day_seq": self.cycle_day_seq,
            "cycle_start_hour": self.cycle_start_hour,
            "progress_at_adds": self.progress_at_adds,
            "prev_cycle_exit_type": self.prev_cycle_exit_type,
            "cycle_waste_pct": self.cycle_waste_pct,
            "entry_type": self.entry_type,
            "direction_detect_time": self.direction_detect_time,
            "confirming_duration_bars": self.confirming_duration_bars,
            "hwm_at_entry": self.hwm_at_entry,
            "pullback_depth_pct": self.pullback_depth_pct,
            "runaway_flag": self.runaway_flag,
            "remaining_to_parent_target": self.remaining_to_parent_target,
            "would_flatten_reseed": self.would_flatten_reseed,
            "half_block_profit": self.half_block_profit,
        }


class FACycleLog:
    """Accumulate frozen-anchor cycle records and produce a DataFrame."""

    def __init__(self) -> None:
        self._records: list[dict] = []

    def append(self, record: FACycleRecord) -> None:
        self._records.append(record.to_dict())

    def to_dataframe(self) -> pd.DataFrame:
        if not self._records:
            return pd.DataFrame(columns=FA_CYCLE_COLUMNS)
        return pd.DataFrame(self._records)

    def __len__(self) -> int:
        return len(self._records)


# =========================================================================
# Missed entry record (pullback entry mode)
# =========================================================================

@dataclass
class FAMissedRecord:
    """A direction detection that did not result in an entry."""

    config_id: str = ""
    date: str = ""                      # Trading date
    direction_detect_time: object = None
    direction: str = ""                 # "LONG" or "SHORT"
    hwm_reached: float = 0.0           # Max favorable extension (points)
    exit_reason: str = ""              # SESSION_END or INVALIDATED
    hypothetical_immediate_pnl: float = 0.0  # Mark-to-market PnL of immediate entry

    def to_dict(self) -> dict:
        return {
            "config_id": self.config_id,
            "date": self.date,
            "direction_detect_time": self.direction_detect_time,
            "direction": self.direction,
            "hwm_reached": self.hwm_reached,
            "exit_reason": self.exit_reason,
            "hypothetical_immediate_pnl": self.hypothetical_immediate_pnl,
        }


class FAMissedLog:
    """Accumulate missed entry records and produce a DataFrame."""

    def __init__(self) -> None:
        self._records: list[dict] = []

    def append(self, record: FAMissedRecord) -> None:
        self._records.append(record.to_dict())

    def to_dataframe(self) -> pd.DataFrame:
        if not self._records:
            return pd.DataFrame(columns=FA_MISSED_COLUMNS)
        return pd.DataFrame(self._records)

    def __len__(self) -> int:
        return len(self._records)
