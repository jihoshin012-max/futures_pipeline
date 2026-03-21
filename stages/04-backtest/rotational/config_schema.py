# archetype: rotational
"""RotationConfig — unified configuration for multi-approach rotation simulator.

Supports Approaches A (pure rotation), B (traditional martingale),
C (anti-martingale), D (scaled entry) via a single dataclass with
validation rules enforced on construction.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RotationConfig:
    """Single sweep configuration for the rotation simulator.

    Validation rules (enforced by __post_init__):
        - Approach A: max_adds == 0, add_dist == 0, confirm_dist == 0
        - Approach B: add_dist > 0, confirm_dist == 0
        - Approach C: confirm_dist > 0, add_dist == 0, add_size == 1
        - Approach D: confirm_dist > 0, add_dist == 0, add_size >= 1
        - All: step_dist > 0, ml == 1, iq == 1
    """

    config_id: str
    approach: str           # "A", "B", "C", "D"
    step_dist: float        # Reversal distance (points)
    add_dist: float = 0.0   # Against-trigger distance (Approach B only)
    confirm_dist: float = 0.0  # Favorable-trigger distance (C, D only)
    max_adds: int = 0       # 0 for Approach A
    add_size: int = 1       # Contracts per add (D can be >1, others always 1)
    ml: int = 1             # Fixed: flat adds
    iq: int = 1             # Fixed: initial quantity
    cost_ticks: float = 2.0 # Per-side cost in ticks

    def __post_init__(self) -> None:
        approach = self.approach.upper()
        # Use object.__setattr__ because frozen=True
        object.__setattr__(self, "approach", approach)

        if self.step_dist <= 0:
            raise ValueError(f"step_dist must be > 0, got {self.step_dist}")
        if self.ml != 1:
            raise ValueError(f"ml must be 1, got {self.ml}")
        if self.iq != 1:
            raise ValueError(f"iq must be 1, got {self.iq}")

        if approach == "A":
            if self.max_adds != 0:
                raise ValueError(f"Approach A: max_adds must be 0, got {self.max_adds}")
            if self.add_dist != 0.0:
                raise ValueError(f"Approach A: add_dist must be 0, got {self.add_dist}")
            if self.confirm_dist != 0.0:
                raise ValueError(f"Approach A: confirm_dist must be 0, got {self.confirm_dist}")

        elif approach == "B":
            if self.add_dist <= 0:
                raise ValueError(f"Approach B: add_dist must be > 0, got {self.add_dist}")
            if self.confirm_dist != 0.0:
                raise ValueError(f"Approach B: confirm_dist must be 0, got {self.confirm_dist}")

        elif approach == "C":
            if self.confirm_dist <= 0:
                raise ValueError(f"Approach C: confirm_dist must be > 0, got {self.confirm_dist}")
            if self.add_dist != 0.0:
                raise ValueError(f"Approach C: add_dist must be 0, got {self.add_dist}")
            if self.add_size != 1:
                raise ValueError(f"Approach C: add_size must be 1, got {self.add_size}")

        elif approach == "D":
            if self.confirm_dist <= 0:
                raise ValueError(f"Approach D: confirm_dist must be > 0, got {self.confirm_dist}")
            if self.add_dist != 0.0:
                raise ValueError(f"Approach D: add_dist must be 0, got {self.add_dist}")
            if self.add_size < 1:
                raise ValueError(f"Approach D: add_size must be >= 1, got {self.add_size}")

        else:
            raise ValueError(f"Unknown approach '{approach}', expected A/B/C/D")


@dataclass(frozen=True)
class FrozenAnchorConfig:
    """Configuration for the frozen-anchor rotation simulator.

    The frozen anchor fixes the reference price at seed/re-seed and never
    moves it on adverse adds.  Success and failure exits are symmetric
    reversals measured from that fixed anchor.

    Validation rules (enforced by __post_init__):
        - step_dist > 0
        - add_dist > 0 (used for would_flatten_reseed shadow even when max_adds=0)
        - max_adds >= 0
        - 0 < reversal_target <= 1.0
        - add_size == 1 (fixed for this sweep)
    """

    config_id: str
    step_dist: float            # Parent scale — defines success and failure boundaries
    add_dist: float             # Child scale — distance for adverse adds (points)
    max_adds: int               # Max adverse adds (0 = pure rotation)
    reversal_target: float      # Profit exit as fraction of step_dist (0.5-1.0)
    cost_ticks: float = 2.0     # Per-side cost in ticks
    iq: int = 1                 # Initial quantity (always 1)
    add_size: int = 1           # Contracts per add (always 1 for this sweep)
    entry_mode: str = "immediate"  # "immediate" or "pullback"
    reentry_mode: str = "C"        # "A"=full rewatch, "B"=confirm only, "C"=pullback seed only
    seed_dist: float = 0.0         # Detection threshold (0 = use step_dist)

    def __post_init__(self) -> None:
        if self.step_dist <= 0:
            raise ValueError(f"step_dist must be > 0, got {self.step_dist}")
        if self.add_dist <= 0:
            raise ValueError(f"add_dist must be > 0, got {self.add_dist}")
        if self.max_adds < 0:
            raise ValueError(f"max_adds must be >= 0, got {self.max_adds}")
        if self.reversal_target <= 0 or self.reversal_target > 1.0:
            raise ValueError(
                f"reversal_target must be in (0, 1.0], got {self.reversal_target}"
            )
        if self.add_size != 1:
            raise ValueError(f"add_size must be 1 for this sweep, got {self.add_size}")
        if self.iq != 1:
            raise ValueError(f"iq must be 1, got {self.iq}")
        if self.entry_mode not in ("immediate", "pullback"):
            raise ValueError(
                f"entry_mode must be 'immediate' or 'pullback', got {self.entry_mode}"
            )
        if self.reentry_mode not in ("A", "B", "C"):
            raise ValueError(
                f"reentry_mode must be 'A', 'B', or 'C', got {self.reentry_mode}"
            )
        if self.seed_dist < 0:
            raise ValueError(f"seed_dist must be >= 0, got {self.seed_dist}")
        # Resolve seed_dist=0 → use step_dist
        if self.seed_dist == 0.0:
            object.__setattr__(self, "seed_dist", self.step_dist)
        if self.seed_dist > self.step_dist:
            raise ValueError(
                f"seed_dist ({self.seed_dist}) must be <= step_dist ({self.step_dist})"
            )
