# archetype: rotational
"""Hypothesis configuration registry for the rotational archetype.

Defines all 41 hypotheses from spec Sections 3.1-3.6 with their config patches,
parameter grids, and metadata. Provides helper functions for experiment generation.

Dimension breakdown per spec (verified):
    A = 5  (Trigger mechanisms: H1, H3, H8, H9, H10)
    B = 1  (Symmetry modifier: H2)
    C = 16 (Conditional filters: H4, H5, H6, H7, H11, H12, H16, H17, H33, H34, H35, H36, H37, H39, H40, H41)
    D = 10 (Structural modifications: H13, H14, H15, H20, H21, H22, H23, H24, H25, H26)
    E = 2  (Cross-data & directional: H18, H19)
    F = 7  (Dynamics: H27, H28, H29, H30, H31, H32, H38)
    Total = 41

NOTE: H23 is Dimension D ("Conditional adds" per spec Section 3.4), NOT Dimension C.

Exports:
    HYPOTHESIS_REGISTRY: dict mapping str -> hypothesis definition dict
    get_hypothesis(h_id) -> dict
    get_hypotheses_by_dimension(dim) -> list[dict]
    build_experiment_config(base_config, hypothesis, params) -> dict
    get_screening_experiments() -> list[dict]
"""

from __future__ import annotations

import copy

# ---------------------------------------------------------------------------
# Bar sources (3 primary bar types)
# ---------------------------------------------------------------------------

_ALL_SOURCES = [
    "bar_data_250vol_rot",
    "bar_data_250tick_rot",
    "bar_data_10sec_rot",
]

# ---------------------------------------------------------------------------
# HYPOTHESIS_REGISTRY
# ---------------------------------------------------------------------------

HYPOTHESIS_REGISTRY: dict[str, dict] = {}

# === DIMENSION A — Trigger Mechanisms (5 hypotheses) ===
# H1, H3, H8, H9, H10 replace the fixed-point StepDist trigger.

HYPOTHESIS_REGISTRY["H1"] = {
    "id": "H1",
    "name": "ATR-scaled step",
    "dimension": "A",
    "description": "StepDist = multiplier × ATR (col 35). Dynamic trigger that scales with market volatility.",
    "config_patch": {
        "hypothesis.trigger_mechanism": "atr_scaled",
    },
    "param_grid": [
        {"hypothesis.trigger_params.multiplier": m}
        for m in [0.2, 0.3, 0.4, 0.5, 0.75, 1.0]
    ],
    "default_params": {"hypothesis.trigger_params.multiplier": 0.5},
    "computed_features": ["atr_scaled_step"],
    "exclude_10sec": False,
    "requires_reference": False,
    "requires_dynamic_features": False,
}

HYPOTHESIS_REGISTRY["H3"] = {
    "id": "H3",
    "name": "SD band triggers",
    "dimension": "A",
    "description": (
        "Reverse when price crosses SD band boundary. Variants: "
        "H3a=StdDev_1 (1.5×,500-bar,tactical), H3b=StdDev_2 (4.0×,500-bar,extreme), "
        "H3c=composite (StdDev_1 with StdDev_3 confirmation), "
        "H3d=StdDev_1 reversals + StdDev_2 add-refusal boundary."
    ),
    "config_patch": {
        "hypothesis.trigger_mechanism": "sd_band",
    },
    "param_grid": [
        {"hypothesis.trigger_params.band_type": "stddev1"},
        {"hypothesis.trigger_params.band_type": "stddev2"},
        {"hypothesis.trigger_params.band_type": "composite"},
        {"hypothesis.trigger_params.band_type": "stddev1_refuse_adds_at_stddev2"},
    ],
    "default_params": {"hypothesis.trigger_params.band_type": "stddev1"},
    "computed_features": [],
    "exclude_10sec": False,
    "requires_reference": False,
    "requires_dynamic_features": False,
}

HYPOTHESIS_REGISTRY["H8"] = {
    "id": "H8",
    "name": "SD-scaled step from anchor",
    "dimension": "A",
    "description": "StepDist = multiplier × rolling_SD(Close, lookback). Dynamic step that adapts to recent price dispersion.",
    "config_patch": {
        "hypothesis.trigger_mechanism": "sd_scaled",
    },
    "param_grid": [
        {"hypothesis.trigger_params.multiplier": m, "hypothesis.trigger_params.lookback": lb}
        for m in [0.3, 0.5, 0.75, 1.0, 1.5]
        for lb in [20, 50, 100, 200]
    ],
    "default_params": {
        "hypothesis.trigger_params.multiplier": 0.75,
        "hypothesis.trigger_params.lookback": 50,
    },
    "computed_features": ["rolling_sd", "sd_scaled_step"],
    "exclude_10sec": False,
    "requires_reference": False,
    "requires_dynamic_features": False,
}

HYPOTHESIS_REGISTRY["H9"] = {
    "id": "H9",
    "name": "VWAP SD bands",
    "dimension": "A",
    "description": "Reverse when price crosses VWAP ± K×SD. VWAP computed from price/volume/timestamps.",
    "config_patch": {
        "hypothesis.trigger_mechanism": "vwap_sd",
    },
    "param_grid": [
        {"hypothesis.trigger_params.k": k, "hypothesis.trigger_params.vwap_reset": reset}
        for k in [1.0, 1.5, 2.0, 2.5]
        for reset in ["session", "rolling"]
    ],
    "default_params": {
        "hypothesis.trigger_params.k": 2.0,
        "hypothesis.trigger_params.vwap_reset": "session",
    },
    "computed_features": ["vwap", "vwap_sd_upper", "vwap_sd_lower"],
    "exclude_10sec": False,
    "requires_reference": False,
    "requires_dynamic_features": False,
}

HYPOTHESIS_REGISTRY["H10"] = {
    "id": "H10",
    "name": "Price z-score threshold",
    "dimension": "A",
    "description": "Reverse when abs((Price - rolling_mean) / rolling_SD) > threshold. No anchor concept.",
    "config_patch": {
        "hypothesis.trigger_mechanism": "zscore",
    },
    "param_grid": [
        {"hypothesis.trigger_params.threshold": t, "hypothesis.trigger_params.lookback": lb}
        for t in [1.5, 2.0, 2.5, 3.0]
        for lb in [50, 100, 200]
    ],
    "default_params": {
        "hypothesis.trigger_params.threshold": 2.0,
        "hypothesis.trigger_params.lookback": 100,
    },
    "computed_features": ["price_zscore", "rolling_mean", "rolling_sd"],
    "exclude_10sec": False,
    "requires_reference": False,
    "requires_dynamic_features": False,
}

# === DIMENSION B — Symmetry Modifier (1 hypothesis) ===

HYPOTHESIS_REGISTRY["H2"] = {
    "id": "H2",
    "name": "Asymmetric reversal vs add thresholds",
    "dimension": "B",
    "description": "Separate multiplier for reversal trigger and add trigger. e.g., reverse at 1.0×ATR but add at 0.5×ATR.",
    "config_patch": {
        "hypothesis.symmetry": "asymmetric",
    },
    "param_grid": [
        {"hypothesis.symmetry_params.rev_add_ratio": r}
        for r in [0.5, 0.75, 1.0, 1.5, 2.0]
    ],
    "default_params": {"hypothesis.symmetry_params.rev_add_ratio": 1.5},
    "computed_features": [],
    "exclude_10sec": False,
    "requires_reference": False,
    "requires_dynamic_features": False,
}

# === DIMENSION C — Conditional Filters (16 hypotheses) ===
# H4, H5, H6, H7, H11, H12, H16, H17, H33, H34, H35, H36, H37, H39, H40, H41

HYPOTHESIS_REGISTRY["H4"] = {
    "id": "H4",
    "name": "ZZ swing confirmation",
    "dimension": "C",
    "description": "Require ZZ reversal signal within N bars of step trigger (cols 14-18).",
    "config_patch": {
        "hypothesis.active_filters": ["H4"],
    },
    "param_grid": [
        {"hypothesis.filter_params.H4.lookback_bars": n}
        for n in [3, 5, 10, 20]
    ],
    "default_params": {"hypothesis.filter_params.H4.lookback_bars": 5},
    "computed_features": [],
    "exclude_10sec": False,
    "requires_reference": False,
    "requires_dynamic_features": False,
}

HYPOTHESIS_REGISTRY["H5"] = {
    "id": "H5",
    "name": "Regime-conditional parameters",
    "dimension": "C",
    "description": "Step multiplier varies by HMM regime state (refit on rotational data).",
    "config_patch": {
        "hypothesis.active_filters": ["H5"],
    },
    "param_grid": [],
    "default_params": {},
    "computed_features": ["regime_state"],
    "exclude_10sec": False,
    "requires_reference": False,
    "requires_dynamic_features": False,
}

HYPOTHESIS_REGISTRY["H6"] = {
    "id": "H6",
    "name": "Bid/Ask volume imbalance",
    "dimension": "C",
    "description": "Skew reversal/add behavior based on directional volume (static snapshot per bar, cols 12-13).",
    "config_patch": {
        "hypothesis.active_filters": ["H6"],
    },
    "param_grid": [
        {"hypothesis.filter_params.H6.imbalance_threshold": t}
        for t in [0.2, 0.3, 0.4, 0.5]
    ],
    "default_params": {"hypothesis.filter_params.H6.imbalance_threshold": 0.3},
    "computed_features": ["bid_ask_imbalance"],
    "exclude_10sec": False,
    "requires_reference": False,
    "requires_dynamic_features": False,
}

HYPOTHESIS_REGISTRY["H7"] = {
    "id": "H7",
    "name": "ZZ Oscillator gating",
    "dimension": "C",
    "description": "Gate adds at extreme oscillator values; suppress at moderate (col 21).",
    "config_patch": {
        "hypothesis.active_filters": ["H7"],
    },
    "param_grid": [
        {"hypothesis.filter_params.H7.extreme_threshold": t}
        for t in [0.7, 0.8, 0.9]
    ],
    "default_params": {"hypothesis.filter_params.H7.extreme_threshold": 0.8},
    "computed_features": [],
    "exclude_10sec": False,
    "requires_reference": False,
    "requires_dynamic_features": False,
}

HYPOTHESIS_REGISTRY["H11"] = {
    "id": "H11",
    "name": "Time-of-day conditioning",
    "dimension": "C",
    "description": "Session segment (pre-market/open/midday/close/overnight) modifies parameters (cols 1-2).",
    "config_patch": {
        "hypothesis.active_filters": ["H11"],
    },
    "param_grid": [],
    "default_params": {},
    "computed_features": ["session_segment"],
    "exclude_10sec": False,
    "requires_reference": False,
    "requires_dynamic_features": False,
}

HYPOTHESIS_REGISTRY["H12"] = {
    "id": "H12",
    "name": "Day-of-week conditioning",
    "dimension": "C",
    "description": "Day-specific parameter adjustment (col 1).",
    "config_patch": {
        "hypothesis.active_filters": ["H12"],
    },
    "param_grid": [],
    "default_params": {},
    "computed_features": ["day_of_week"],
    "exclude_10sec": False,
    "requires_reference": False,
    "requires_dynamic_features": False,
}

HYPOTHESIS_REGISTRY["H16"] = {
    "id": "H16",
    "name": "Bar formation quality filter",
    "dimension": "C",
    "description": "Suppress actions on bars with extreme # of Trades or formation speed (col 8, timestamps).",
    "config_patch": {
        "hypothesis.active_filters": ["H16"],
    },
    "param_grid": [
        {"hypothesis.filter_params.H16.max_trades_zscore": z}
        for z in [2.0, 2.5, 3.0]
    ],
    "default_params": {"hypothesis.filter_params.H16.max_trades_zscore": 2.5},
    "computed_features": ["trades_zscore", "bar_duration_sec"],
    "exclude_10sec": False,
    "requires_reference": False,
    "requires_dynamic_features": False,
}

HYPOTHESIS_REGISTRY["H17"] = {
    "id": "H17",
    "name": "Cycle performance feedback",
    "dimension": "C",
    "description": "Adjust behavior based on last N cycle outcomes (win/loss, duration). Requires simulator internal state.",
    "config_patch": {
        "hypothesis.active_filters": ["H17"],
    },
    "param_grid": [
        {"hypothesis.filter_params.H17.lookback_cycles": n}
        for n in [3, 5, 10]
    ],
    "default_params": {"hypothesis.filter_params.H17.lookback_cycles": 5},
    "computed_features": ["cycle_feedback_state"],
    "exclude_10sec": False,
    "requires_reference": False,
    "requires_dynamic_features": True,
}

HYPOTHESIS_REGISTRY["H33"] = {
    "id": "H33",
    "name": "PriceSpeed filter",
    "dimension": "C",
    "description": "Suppress reversals/adds when price velocity (points/second, Close delta / timestamp delta) exceeds threshold.",
    "config_patch": {
        "hypothesis.active_filters": ["H33"],
    },
    "param_grid": [
        {"hypothesis.filter_params.H33.speed_threshold": t}
        for t in [0.5, 1.0, 2.0, 3.0]
    ],
    "default_params": {"hypothesis.filter_params.H33.speed_threshold": 1.0},
    "computed_features": ["price_speed", "bar_duration_sec"],
    "exclude_10sec": False,
    "requires_reference": False,
    "requires_dynamic_features": False,
}

HYPOTHESIS_REGISTRY["H34"] = {
    "id": "H34",
    "name": "Absorption rate proxy",
    "dimension": "C",
    "description": "AskVol/bar_duration and BidVol/bar_duration as absorption rate approximations (cols 12-13, timestamps).",
    "config_patch": {
        "hypothesis.active_filters": ["H34"],
    },
    "param_grid": [
        {"hypothesis.filter_params.H34.absorption_threshold": t}
        for t in [5.0, 10.0, 20.0]
    ],
    "default_params": {"hypothesis.filter_params.H34.absorption_threshold": 10.0},
    "computed_features": ["ask_absorption_rate", "bid_absorption_rate", "bar_duration_sec"],
    "exclude_10sec": False,
    "requires_reference": False,
    "requires_dynamic_features": False,
}

HYPOTHESIS_REGISTRY["H35"] = {
    "id": "H35",
    "name": "Imbalance trend",
    "dimension": "C",
    "description": "Rolling slope of (AskVol-BidVol)/(AskVol+BidVol) over N bars. Extends H6 from static to directional (cols 12-13).",
    "config_patch": {
        "hypothesis.active_filters": ["H35"],
    },
    "param_grid": [
        {"hypothesis.filter_params.H35.lookback": n}
        for n in [10, 20, 40]
    ],
    "default_params": {"hypothesis.filter_params.H35.lookback": 20},
    "computed_features": ["imbalance_ratio", "imbalance_slope"],
    "exclude_10sec": False,
    "requires_reference": False,
    "requires_dynamic_features": False,
}

HYPOTHESIS_REGISTRY["H36"] = {
    "id": "H36",
    "name": "Adverse move speed",
    "dimension": "C",
    "description": "Speed of price movement specifically against current position direction. Fast adverse = trending against, suppress adds.",
    "config_patch": {
        "hypothesis.active_filters": ["H36"],
    },
    "param_grid": [
        {"hypothesis.filter_params.H36.adverse_speed_threshold": t}
        for t in [0.5, 1.0, 2.0]
    ],
    "default_params": {"hypothesis.filter_params.H36.adverse_speed_threshold": 1.0},
    "computed_features": ["adverse_speed"],
    "exclude_10sec": False,
    "requires_reference": False,
    "requires_dynamic_features": True,
}

HYPOTHESIS_REGISTRY["H37"] = {
    "id": "H37",
    "name": "Bar formation rate",
    "dimension": "C",
    "description": "Rolling bars-per-minute on vol/tick series. High rate = active/hot, potentially trending. Constant on 10-sec — excluded.",
    "config_patch": {
        "hypothesis.active_filters": ["H37"],
    },
    "param_grid": [
        {"hypothesis.filter_params.H37.lookback_minutes": m}
        for m in [1, 5, 15]
    ],
    "default_params": {"hypothesis.filter_params.H37.lookback_minutes": 5},
    "computed_features": ["bar_formation_rate"],
    "exclude_10sec": True,
    "requires_reference": False,
    "requires_dynamic_features": False,
}

HYPOTHESIS_REGISTRY["H39"] = {
    "id": "H39",
    "name": "Cycle adverse velocity ratio",
    "dimension": "C",
    "description": "Adverse leg speed / prior favorable leg speed within cycle. Ratio > 1 = market character changed mid-cycle.",
    "config_patch": {
        "hypothesis.active_filters": ["H39"],
    },
    "param_grid": [
        {"hypothesis.filter_params.H39.ratio_threshold": t}
        for t in [1.0, 1.5, 2.0]
    ],
    "default_params": {"hypothesis.filter_params.H39.ratio_threshold": 1.5},
    "computed_features": ["adverse_velocity_ratio"],
    "exclude_10sec": False,
    "requires_reference": False,
    "requires_dynamic_features": True,
}

HYPOTHESIS_REGISTRY["H40"] = {
    "id": "H40",
    "name": "Band-relative speed regime",
    "dimension": "C",
    "description": "Classify bars into speed × band-position states. Inside StdDev_1+slow=rotation-friendly. Outside StdDev_2+fast=danger.",
    "config_patch": {
        "hypothesis.active_filters": ["H40"],
    },
    "param_grid": [],
    "default_params": {},
    "computed_features": ["band_speed_state", "price_speed"],
    "exclude_10sec": False,
    "requires_reference": False,
    "requires_dynamic_features": False,
}

HYPOTHESIS_REGISTRY["H41"] = {
    "id": "H41",
    "name": "Band-relative ATR behavior",
    "dimension": "C",
    "description": "ATR expanding outside bands = trend strengthening. ATR contracting outside bands = exhaustion. Location-aware volatility.",
    "config_patch": {
        "hypothesis.active_filters": ["H41"],
    },
    "param_grid": [],
    "default_params": {},
    "computed_features": ["band_atr_state"],
    "exclude_10sec": False,
    "requires_reference": False,
    "requires_dynamic_features": False,
}

# === DIMENSION D — Structural Modifications (10 hypotheses) ===
# H13, H14, H15, H20, H21, H22, H23, H24, H25, H26

HYPOTHESIS_REGISTRY["H13"] = {
    "id": "H13",
    "name": "Selective flat periods",
    "dimension": "D",
    "description": "Define conditions where strategy flattens and pauses instead of always rotating. Breaks always-in-market assumption.",
    "config_patch": {
        "hypothesis.structural_mods": ["H13"],
    },
    "param_grid": [],
    "default_params": {},
    "computed_features": [],
    "exclude_10sec": False,
    "requires_reference": False,
    "requires_dynamic_features": False,
}

HYPOTHESIS_REGISTRY["H14"] = {
    "id": "H14",
    "name": "Adaptive martingale progression",
    "dimension": "D",
    "description": "Add multiplier or max levels adjusts based on market state. Changes the fixed 1→2→4→8 sizing.",
    "config_patch": {
        "hypothesis.structural_mods": ["H14"],
    },
    "param_grid": [],
    "default_params": {},
    "computed_features": [],
    "exclude_10sec": False,
    "requires_reference": False,
    "requires_dynamic_features": False,
}

HYPOTHESIS_REGISTRY["H15"] = {
    "id": "H15",
    "name": "Alternative anchor strategies",
    "dimension": "D",
    "description": "Anchor = original cycle entry, or average entry, or reset on reversal only (not on adds). Changes how distance is measured.",
    "config_patch": {
        "hypothesis.structural_mods": ["H15"],
    },
    "param_grid": [
        {"hypothesis.structural_params.H15.anchor_type": t}
        for t in ["original_entry", "avg_entry", "reversal_only"]
    ],
    "default_params": {"hypothesis.structural_params.H15.anchor_type": "original_entry"},
    "computed_features": [],
    "exclude_10sec": False,
    "requires_reference": False,
    "requires_dynamic_features": False,
}

HYPOTHESIS_REGISTRY["H20"] = {
    "id": "H20",
    "name": "Partial rotation",
    "dimension": "D",
    "description": "Scale out instead of full flatten; or reverse with size proportional to cycle profit. Breaks total-flatten-and-reverse pattern.",
    "config_patch": {
        "hypothesis.structural_mods": ["H20"],
    },
    "param_grid": [
        {"hypothesis.structural_params.H20.scale_out_pct": p}
        for p in [0.25, 0.5, 0.75]
    ],
    "default_params": {"hypothesis.structural_params.H20.scale_out_pct": 0.5},
    "computed_features": [],
    "exclude_10sec": False,
    "requires_reference": False,
    "requires_dynamic_features": False,
}

HYPOTHESIS_REGISTRY["H21"] = {
    "id": "H21",
    "name": "Cycle profit target",
    "dimension": "D",
    "description": "Exit on PnL threshold (ticks, ATR multiples, or function of max adverse excursion). Adds exit mechanism not in baseline.",
    "config_patch": {
        "hypothesis.structural_mods": ["H21"],
    },
    "param_grid": [
        {"hypothesis.structural_params.H21.profit_target_ticks": t}
        for t in [8, 12, 16, 24]
    ],
    "default_params": {"hypothesis.structural_params.H21.profit_target_ticks": 12},
    "computed_features": [],
    "exclude_10sec": False,
    "requires_reference": False,
    "requires_dynamic_features": True,
}

HYPOTHESIS_REGISTRY["H22"] = {
    "id": "H22",
    "name": "Cycle time decay",
    "dimension": "D",
    "description": "Force action if cycle exceeds N bars/minutes without resolving. Adds time-based exit not in baseline.",
    "config_patch": {
        "hypothesis.structural_mods": ["H22"],
    },
    "param_grid": [
        {"hypothesis.structural_params.H22.max_cycle_bars": n}
        for n in [50, 100, 200, 500]
    ],
    "default_params": {"hypothesis.structural_params.H22.max_cycle_bars": 100},
    "computed_features": [],
    "exclude_10sec": False,
    "requires_reference": False,
    "requires_dynamic_features": False,
}

HYPOTHESIS_REGISTRY["H23"] = {
    "id": "H23",
    "name": "Conditional adds",
    "dimension": "D",
    "description": (
        "Adds require secondary confirmation (volume, ZZ, momentum) beyond just price distance. "
        "Introduces 'refused adds' — the strategy can decline to escalate. "
        "Per spec Section 3.4 (Structural Modifications, Dimension D). NOT in Dimension C."
    ),
    "config_patch": {
        "hypothesis.structural_mods": ["H23"],
    },
    "param_grid": [
        {"hypothesis.structural_params.H23.confirmation_type": t}
        for t in ["volume_confirm", "zz_confirm", "momentum_confirm"]
    ],
    "default_params": {"hypothesis.structural_params.H23.confirmation_type": "volume_confirm"},
    "computed_features": [],
    "exclude_10sec": False,
    "requires_reference": False,
    "requires_dynamic_features": False,
}

HYPOTHESIS_REGISTRY["H24"] = {
    "id": "H24",
    "name": "Intra-cycle de-escalation",
    "dimension": "D",
    "description": "Trim position back toward base size on adverse conditions while at Level 2+. Reduces exposure without full reversal.",
    "config_patch": {
        "hypothesis.structural_mods": ["H24"],
    },
    "param_grid": [],
    "default_params": {},
    "computed_features": [],
    "exclude_10sec": False,
    "requires_reference": False,
    "requires_dynamic_features": False,
}

HYPOTHESIS_REGISTRY["H25"] = {
    "id": "H25",
    "name": "Higher-timeframe context",
    "dimension": "D",
    "description": "Derive HTF trend/structure signal; bias reversal direction toward HTF trend. Breaks single-timeframe assumption.",
    "config_patch": {
        "hypothesis.structural_mods": ["H25"],
    },
    "param_grid": [
        {"hypothesis.structural_params.H25.htf_multiplier": m}
        for m in [5, 10, 20]
    ],
    "default_params": {"hypothesis.structural_params.H25.htf_multiplier": 10},
    "computed_features": ["htf_trend"],
    "exclude_10sec": False,
    "requires_reference": False,
    "requires_dynamic_features": False,
}

HYPOTHESIS_REGISTRY["H26"] = {
    "id": "H26",
    "name": "Session range position",
    "dimension": "D",
    "description": "Condition behavior on where price sits within developing session range. Adds location awareness.",
    "config_patch": {
        "hypothesis.structural_mods": ["H26"],
    },
    "param_grid": [
        {"hypothesis.structural_params.H26.range_pct_threshold": t}
        for t in [0.2, 0.3, 0.4]
    ],
    "default_params": {"hypothesis.structural_params.H26.range_pct_threshold": 0.3},
    "computed_features": ["session_range_position"],
    "exclude_10sec": False,
    "requires_reference": False,
    "requires_dynamic_features": False,
}

# === DIMENSION E — Cross-Data & Directional (2 hypotheses) ===

HYPOTHESIS_REGISTRY["H18"] = {
    "id": "H18",
    "name": "Directional asymmetry",
    "dimension": "E",
    "description": "Structurally different parameters for long vs short exposure. Breaks the symmetric assumption.",
    "config_patch": {
        "hypothesis.symmetry": "asymmetric_directional",
    },
    "param_grid": [],
    "default_params": {},
    "computed_features": [],
    "exclude_10sec": False,
    "requires_reference": False,
    "requires_dynamic_features": False,
}

HYPOTHESIS_REGISTRY["H19"] = {
    "id": "H19",
    "name": "Bar-type divergence signal",
    "dimension": "E",
    "description": (
        "Use agreement/disagreement between vol, tick, and time series as confidence signal. "
        "Requires multi-source data loading (Gap G-01). "
        "Single-source runner returns SKIPPED_REFERENCE_REQUIRED."
    ),
    "config_patch": {},
    "param_grid": [],
    "default_params": {},
    "computed_features": ["bar_type_divergence"],
    "exclude_10sec": False,
    "requires_reference": True,
    "requires_dynamic_features": False,
}

# === DIMENSION F — Dynamics (7 hypotheses) ===
# H27, H28, H29, H30, H31, H32, H38

HYPOTHESIS_REGISTRY["H27"] = {
    "id": "H27",
    "name": "Volatility rate of change",
    "dimension": "F",
    "description": "ATR expanding/contracting — derivative of volatility (col 35).",
    "config_patch": {
        "hypothesis.active_filters": ["H27"],
    },
    "param_grid": [
        {"hypothesis.filter_params.H27.lookback": n}
        for n in [5, 10, 14, 20]
    ],
    "default_params": {"hypothesis.filter_params.H27.lookback": 14},
    "computed_features": ["atr_roc"],
    "exclude_10sec": False,
    "requires_reference": False,
    "requires_dynamic_features": False,
}

HYPOTHESIS_REGISTRY["H28"] = {
    "id": "H28",
    "name": "Price momentum / ROC",
    "dimension": "F",
    "description": "Rate of change of Close as directional filter (computed from price).",
    "config_patch": {
        "hypothesis.active_filters": ["H28"],
    },
    "param_grid": [
        {"hypothesis.filter_params.H28.lookback": n}
        for n in [5, 10, 20, 40]
    ],
    "default_params": {"hypothesis.filter_params.H28.lookback": 10},
    "computed_features": ["price_roc"],
    "exclude_10sec": False,
    "requires_reference": False,
    "requires_dynamic_features": False,
}

HYPOTHESIS_REGISTRY["H29"] = {
    "id": "H29",
    "name": "Acceleration / deceleration",
    "dimension": "F",
    "description": "Second derivative of price — momentum exhaustion detection (computed from price).",
    "config_patch": {
        "hypothesis.active_filters": ["H29"],
    },
    "param_grid": [
        {"hypothesis.filter_params.H29.lookback": n}
        for n in [5, 10, 20]
    ],
    "default_params": {"hypothesis.filter_params.H29.lookback": 10},
    "computed_features": ["price_acceleration"],
    "exclude_10sec": False,
    "requires_reference": False,
    "requires_dynamic_features": False,
}

HYPOTHESIS_REGISTRY["H30"] = {
    "id": "H30",
    "name": "Volatility compression breakout",
    "dimension": "F",
    "description": "Squeeze detection — shift posture pre/post compression (col 35 or computed SD).",
    "config_patch": {
        "hypothesis.active_filters": ["H30"],
    },
    "param_grid": [
        {"hypothesis.filter_params.H30.squeeze_lookback": n}
        for n in [10, 20, 50]
    ],
    "default_params": {"hypothesis.filter_params.H30.squeeze_lookback": 20},
    "computed_features": ["volatility_squeeze_state"],
    "exclude_10sec": False,
    "requires_reference": False,
    "requires_dynamic_features": False,
}

HYPOTHESIS_REGISTRY["H31"] = {
    "id": "H31",
    "name": "Momentum divergence from price",
    "dimension": "F",
    "description": "Price extends but momentum weakens — classic divergence (computed from price).",
    "config_patch": {
        "hypothesis.active_filters": ["H31"],
    },
    "param_grid": [
        {"hypothesis.filter_params.H31.divergence_lookback": n}
        for n in [10, 20, 40]
    ],
    "default_params": {"hypothesis.filter_params.H31.divergence_lookback": 20},
    "computed_features": ["momentum_divergence"],
    "exclude_10sec": False,
    "requires_reference": False,
    "requires_dynamic_features": False,
}

HYPOTHESIS_REGISTRY["H32"] = {
    "id": "H32",
    "name": "Volume rate of change",
    "dimension": "F",
    "description": "Rising/declining volume confirms or denies move quality (col 7).",
    "config_patch": {
        "hypothesis.active_filters": ["H32"],
    },
    "param_grid": [
        {"hypothesis.filter_params.H32.lookback": n}
        for n in [5, 10, 20]
    ],
    "default_params": {"hypothesis.filter_params.H32.lookback": 10},
    "computed_features": ["volume_roc"],
    "exclude_10sec": False,
    "requires_reference": False,
    "requires_dynamic_features": False,
}

HYPOTHESIS_REGISTRY["H38"] = {
    "id": "H38",
    "name": "Regime transition speed",
    "dimension": "F",
    "description": (
        "Rate of change of regime indicators (ATR derivative + imbalance trend slope + momentum acceleration). "
        "Detects how fast the market is shifting from rotation-friendly to trending."
    ),
    "config_patch": {
        "hypothesis.active_filters": ["H38"],
    },
    "param_grid": [
        {"hypothesis.filter_params.H38.transition_lookback": n}
        for n in [5, 10, 20]
    ],
    "default_params": {"hypothesis.filter_params.H38.transition_lookback": 10},
    "computed_features": ["regime_transition_speed"],
    "exclude_10sec": False,
    "requires_reference": False,
    "requires_dynamic_features": False,
}


# ---------------------------------------------------------------------------
# Sanity check at import time (fast)
# ---------------------------------------------------------------------------

def _validate_registry() -> None:
    """Raise AssertionError if registry is misconfigured."""
    required = {"id", "name", "dimension", "config_patch", "param_grid",
                "default_params", "exclude_10sec", "requires_reference",
                "requires_dynamic_features", "computed_features", "description"}
    for h_id, entry in HYPOTHESIS_REGISTRY.items():
        missing = required - set(entry.keys())
        if missing:
            raise AssertionError(f"Hypothesis {h_id} missing fields: {missing}")
    assert len(HYPOTHESIS_REGISTRY) == 41, (
        f"Registry has {len(HYPOTHESIS_REGISTRY)} entries, expected 41"
    )


_validate_registry()


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def get_hypothesis(h_id: str) -> dict:
    """Return hypothesis definition by ID. Raises KeyError if not found."""
    if h_id not in HYPOTHESIS_REGISTRY:
        raise KeyError(f"Hypothesis '{h_id}' not found in HYPOTHESIS_REGISTRY. "
                       f"Available: {sorted(HYPOTHESIS_REGISTRY.keys())}")
    return HYPOTHESIS_REGISTRY[h_id]


def get_hypotheses_by_dimension(dim: str) -> list[dict]:
    """Return all hypothesis definitions for a given dimension (A/B/C/D/E/F)."""
    return [entry for entry in HYPOTHESIS_REGISTRY.values() if entry["dimension"] == dim]


def _set_nested(config: dict, dotted_key: str, value: object) -> None:
    """Set a nested dict value using a dotted key path.

    Example: _set_nested(cfg, "hypothesis.trigger_params.multiplier", 0.5)
    Sets cfg["hypothesis"]["trigger_params"]["multiplier"] = 0.5, creating
    intermediate dicts as needed.
    """
    parts = dotted_key.split(".")
    node = config
    for part in parts[:-1]:
        if part not in node or not isinstance(node[part], dict):
            node[part] = {}
        node = node[part]
    node[parts[-1]] = value


def build_experiment_config(
    base_config: dict,
    hypothesis: dict,
    params: dict | None = None,
) -> dict:
    """Build a ready-to-use experiment config by applying hypothesis patch + optional params.

    Args:
        base_config: The base config dict (deep-copied, not mutated).
        hypothesis: Hypothesis definition dict (from HYPOTHESIS_REGISTRY).
        params: Optional dict of dotted-path overrides (e.g., param_grid entry).

    Returns:
        Deep copy of base_config with hypothesis config_patch and params applied.
    """
    cfg = copy.deepcopy(base_config)

    # Apply hypothesis config_patch
    for dotted_key, value in hypothesis.get("config_patch", {}).items():
        _set_nested(cfg, dotted_key, value)

    # Apply param overrides (e.g., from param_grid entry or default_params)
    if params:
        for dotted_key, value in params.items():
            _set_nested(cfg, dotted_key, value)

    return cfg


def get_screening_experiments() -> list[dict]:
    """Return list of all 122 meaningful Phase 1 screening experiments.

    41 hypotheses × 3 bar types - 1 (H37 excluded from 10sec) = 122.

    Each entry:
        hypothesis_id: str
        source_id: str
        params: dict (default_params for the hypothesis)
        requires_reference: bool
    """
    experiments = []

    for h_id, hypothesis in HYPOTHESIS_REGISTRY.items():
        for source_id in _ALL_SOURCES:
            # H37 is excluded from 10-sec bars (constant formation rate on fixed-cadence series)
            if h_id == "H37" and source_id == "bar_data_10sec_rot":
                continue

            experiments.append({
                "hypothesis_id": h_id,
                "source_id": source_id,
                "params": copy.deepcopy(hypothesis.get("default_params", {})),
                "requires_reference": hypothesis.get("requires_reference", False),
            })

    return experiments
