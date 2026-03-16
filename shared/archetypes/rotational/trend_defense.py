# archetype: rotational
"""TrendDefenseSystem -- 5-detector, 3-level escalation module for rotational simulator.

This module is standalone and does NOT modify simulator state directly. It returns
action_modifiers dicts that the simulator applies. All timing thresholds are stored
in seconds and converted to bar counts at initialization using median_bar_sec.

Usage::

    bar_duration_stats = {"median_sec": 10.0, "p10_sec": 5.0}
    tds = TrendDefenseSystem(config["trend_defense"], bar_duration_stats)

    # In the simulation loop (per bar):
    threat = tds.evaluate(bar, features, sim_state)
    action_modifiers = tds.apply_response(sim_state, threat)
    tds.update_cycle_metrics(bar, sim_state)

    # On reversal:
    tds.on_reversal()

    # On add:
    tds.on_add(price=current_price)

Spec: Rotational_Archetype_Spec.md Section 4
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class TDSState:
    """Mutable per-simulation state for TrendDefenseSystem."""

    current_level: int = 0
    """0=inactive, 1=early warning, 2=active threat, 3=emergency."""

    forced_flat: bool = False
    """True when Level 3 has been triggered and cooldown is active."""

    cooldown_remaining: int = 0
    """Bars remaining in Level 3 cooldown."""

    consecutive_adds: int = 0
    """Adds since last reversal or qualifying retracement."""

    last_retracement_depths: list = field(default_factory=list)
    """Running list of retracement depth ratios within the current cycle."""

    cycle_unrealized_pnl_ticks: float = 0.0
    """Running unrealized PnL in ticks for the current cycle."""

    l1_triggers: int = 0
    l2_triggers: int = 0
    l3_triggers: int = 0

    _last_add_price: float | None = None
    """Price at the most recent add (used for qualifying-retracement reset)."""

    _level_zero_bar_idx: int = 0
    """Bar index when position was at level 0 (used by velocity monitor)."""


class TrendDefenseSystem:
    """Stateful defense system against straight-line adverse moves.

    Instantiate once per simulation run. Receives ``bar_duration_stats``
    computed from the actual bar DataFrame before the simulation starts so that
    second-based thresholds are correctly scaled per bar type.

    Args:
        config: The ``trend_defense`` sub-dict from the hypothesis config.
        bar_duration_stats: Dict with at least ``{'median_sec': float}``.
    """

    def __init__(self, config: dict, bar_duration_stats: dict) -> None:
        median_bar_sec: float = bar_duration_stats["median_sec"]

        # Level 1 parameters
        l1 = config.get("level_1", {})
        self._step_widen_factor: float = float(l1.get("step_widen_factor", 1.5))
        self._max_levels_reduction: int = int(l1.get("max_levels_reduction", 1))

        # Level 2 parameters
        l2 = config.get("level_2", {})
        velocity_threshold_sec: float = float(l2.get("velocity_threshold_sec", 60.0))
        self._velocity_bars: int = max(1, round(velocity_threshold_sec / median_bar_sec))
        self._max_consecutive_adds: int = int(l2.get("consecutive_adds_threshold", 3))
        self._retracement_reset_pct: float = float(l2.get("retracement_reset_pct", 0.3))

        # Level 3 parameters
        l3 = config.get("level_3", {})
        self._drawdown_budget_ticks: float = float(l3.get("drawdown_budget_ticks", 50.0))
        cooldown_sec: float = float(l3.get("cooldown_sec", 300.0))
        self._cooldown_bars: int = max(1, round(cooldown_sec / median_bar_sec))

        # Precursor composite parameters
        prec = config.get("precursor", {})
        self._precursor_min_signals: int = int(prec.get("precursor_min_signals", 2))
        self._speed_threshold: float = float(prec.get("speed_threshold", 1.0))
        self._regime_accel_threshold: float = float(prec.get("regime_accel_threshold", 1.0))
        self._adverse_speed_threshold: float = float(prec.get("adverse_speed_threshold", 1.0))

        self.state = TDSState()

    # ------------------------------------------------------------------
    # Core evaluation
    # ------------------------------------------------------------------

    def evaluate(self, bar, features: dict, sim_state: dict) -> int:
        """Run all 5 detectors and return threat level 0-3.

        Args:
            bar: pd.Series with at least ``{'Last': float}``.
            features: Dict of computed hypothesis features (static + dynamic).
            sim_state: Dict with keys ``direction``, ``level``, ``anchor``,
                ``position_qty``, ``cycle_start_bar``, ``bar_idx``,
                ``avg_entry_price``, ``step_dist_ticks``.

        Returns:
            Threat level 0 (inactive) through 3 (emergency).
        """
        bar_idx: int = int(sim_state.get("bar_idx", 0))
        sim_level: int = int(sim_state.get("level", 0))

        # Track the bar index when sim was at level 0 (seed point)
        if sim_level == 0:
            self.state._level_zero_bar_idx = bar_idx

        # --- Detector 1: Retracement Quality ---
        depths = self.state.last_retracement_depths
        retracement_declining = (
            len(depths) >= 3
            and all(
                depths[i] < depths[i - 1]
                for i in range(1, len(depths[-3:]))
            )
        )

        # --- Detector 2: Velocity Monitor ---
        level_escalation_too_fast = (
            sim_level > 0
            and (bar_idx - self.state._level_zero_bar_idx) < self._velocity_bars
        )

        # --- Detector 3: Consecutive Add Counter ---
        too_many_consecutive_adds = self.state.consecutive_adds >= self._max_consecutive_adds

        # --- Detector 4: Drawdown Budget ---
        drawdown_budget_hit = (
            self.state.cycle_unrealized_pnl_ticks < -self._drawdown_budget_ticks
        )

        # --- Detector 5: Trend Precursor Composite ---
        precursor_signals = 0
        if features.get("price_speed", 0) > self._speed_threshold:
            precursor_signals += 1
        if features.get("regime_transition_speed", 0) > self._regime_accel_threshold:
            precursor_signals += 1
        if features.get("band_speed_state", 0) >= 3:
            precursor_signals += 1
        if features.get("adverse_speed", 0) > self._adverse_speed_threshold:
            precursor_signals += 1
        trend_precursor_fires = precursor_signals >= self._precursor_min_signals

        # --- Count firing detectors ---
        firing = [
            retracement_declining,
            level_escalation_too_fast,
            too_many_consecutive_adds,
            drawdown_budget_hit,
            trend_precursor_fires,
        ]
        firing_count = sum(firing)

        # --- Level assignment ---
        if drawdown_budget_hit or firing_count >= 3:
            threat = 3
        elif firing_count >= 2:
            threat = 2
        elif firing_count == 1:
            threat = 1
        else:
            threat = 0

        # --- Update state ---
        self.state.current_level = threat
        if threat == 1:
            self.state.l1_triggers += 1
        elif threat == 2:
            self.state.l2_triggers += 1
        elif threat == 3:
            self.state.l3_triggers += 1

        return threat

    # ------------------------------------------------------------------
    # Response generation
    # ------------------------------------------------------------------

    def apply_response(self, sim_state: dict, threat: int) -> dict:
        """Return action modifier dict for the simulator to apply.

        Returns:
            Dict with keys:
            - ``step_widen_factor`` (float): multiply step_dist by this
            - ``max_levels_reduction`` (int): reduce max_levels by this
            - ``refuse_adds`` (bool): if True, block new adds
            - ``force_flatten`` (bool): if True, exit position immediately
            - ``reduced_reversal_threshold`` (float | None): optional tighter reversal
        """
        response: dict = {
            "step_widen_factor": 1.0,
            "max_levels_reduction": 0,
            "refuse_adds": False,
            "force_flatten": False,
            "reduced_reversal_threshold": None,
        }

        if threat == 0:
            return response

        if threat >= 1:
            response["step_widen_factor"] = self._step_widen_factor
            response["max_levels_reduction"] = self._max_levels_reduction

        if threat >= 2:
            response["refuse_adds"] = True

        if threat >= 3:
            response["force_flatten"] = True
            self.state.cooldown_remaining = self._cooldown_bars
            self.state.forced_flat = True

        return response

    # ------------------------------------------------------------------
    # Cycle metric updates
    # ------------------------------------------------------------------

    def update_cycle_metrics(self, bar, sim_state: dict) -> None:
        """Update running cycle PnL and check for qualifying retracement.

        Uses the MAE pattern from rotational_simulator.py lines 254-258.
        Also resets consecutive_adds when a qualifying retracement occurs.
        """
        direction: str = sim_state.get("direction", "Long")
        avg_entry: float = float(sim_state.get("avg_entry_price", 0.0))
        position_qty: int = int(sim_state.get("position_qty", 0))
        step_dist_ticks: float = float(sim_state.get("step_dist_ticks", 8.0))

        try:
            close = float(bar["Last"])
        except (KeyError, TypeError):
            return

        if position_qty == 0:
            return

        # Compute unrealized PnL in ticks (tick_size=1.0 for tick-normalized calc)
        # The simulator normalizes by tick_size at finalization; here we track raw ticks.
        tick_size = float(sim_state.get("tick_size", 1.0))
        if direction == "Long":
            unrealized = (close - avg_entry) / tick_size
        else:
            unrealized = (avg_entry - close) / tick_size

        self.state.cycle_unrealized_pnl_ticks = min(
            self.state.cycle_unrealized_pnl_ticks, unrealized
        )

        # Qualifying retracement check (Pitfall 5): if price moved in-favor from
        # _last_add_price by >= retracement_reset_pct * step_dist_ticks, reset counter.
        if self.state._last_add_price is not None and step_dist_ticks > 0:
            if direction == "Long":
                move_in_favor = close - self.state._last_add_price
            else:
                move_in_favor = self.state._last_add_price - close

            qualifying_threshold = self._retracement_reset_pct * step_dist_ticks
            if move_in_favor >= qualifying_threshold:
                self.state.consecutive_adds = 0
                self.state._last_add_price = None

    # ------------------------------------------------------------------
    # Event callbacks
    # ------------------------------------------------------------------

    def on_reversal(self) -> None:
        """Reset all per-cycle detector state on a reversal."""
        self.state.consecutive_adds = 0
        self.state.last_retracement_depths = []
        self.state._last_add_price = None
        self.state.cycle_unrealized_pnl_ticks = 0.0

    def on_add(self, price: float | None = None) -> None:
        """Increment consecutive add counter and track add price."""
        self.state.consecutive_adds += 1
        if price is not None:
            self.state._last_add_price = price

    # ------------------------------------------------------------------
    # Re-engagement and summary
    # ------------------------------------------------------------------

    def can_reengage(self, features: dict) -> bool:
        """Return True when cooldown expired (primary gate).

        Per research recommendation: cooldown check is pure bar-count-based.
        Optional feature-based secondary check can be added later.
        """
        return self.state.cooldown_remaining <= 0

    def get_summary(self) -> dict:
        """Return TDS trigger count summary for extended metrics."""
        return {
            "l1_triggers": self.state.l1_triggers,
            "l2_triggers": self.state.l2_triggers,
            "l3_triggers": self.state.l3_triggers,
        }
