# archetype: rotational
"""Tests for HYPOTHESIS_REGISTRY and helper functions in hypothesis_configs.py.

Covers:
    - HYPOTHESIS_REGISTRY has exactly 41 entries
    - Dimension counts: A=5, B=1, C=16, D=10, E=2, F=7
    - Required fields on each entry
    - H37 has exclude_10sec=True
    - H19 has requires_reference=True
    - H23 is in dimension D (NOT C)
    - get_screening_experiments() returns 122 entries
    - H19 experiments marked requires_reference=True
    - build_experiment_config produces valid config with correct overrides
"""

from __future__ import annotations

import copy
import sys
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from hypothesis_configs import (  # noqa: E402
    HYPOTHESIS_REGISTRY,
    get_hypothesis,
    get_hypotheses_by_dimension,
    build_experiment_config,
    get_screening_experiments,
)


# ---------------------------------------------------------------------------
# Registry size and structure
# ---------------------------------------------------------------------------

def test_registry_has_41_entries():
    assert len(HYPOTHESIS_REGISTRY) == 41, (
        f"Expected 41 entries, got {len(HYPOTHESIS_REGISTRY)}. "
        f"Keys: {sorted(HYPOTHESIS_REGISTRY.keys())}"
    )


def test_dimension_counts():
    """A=5, B=1, C=16, D=10, E=2, F=7 per spec Section 3."""
    counts = {}
    for entry in HYPOTHESIS_REGISTRY.values():
        dim = entry["dimension"]
        counts[dim] = counts.get(dim, 0) + 1
    assert counts.get("A", 0) == 5, f"Dimension A expected 5, got {counts.get('A', 0)}"
    assert counts.get("B", 0) == 1, f"Dimension B expected 1, got {counts.get('B', 0)}"
    assert counts.get("C", 0) == 16, f"Dimension C expected 16, got {counts.get('C', 0)}"
    assert counts.get("D", 0) == 10, f"Dimension D expected 10, got {counts.get('D', 0)}"
    assert counts.get("E", 0) == 2, f"Dimension E expected 2, got {counts.get('E', 0)}"
    assert counts.get("F", 0) == 7, f"Dimension F expected 7, got {counts.get('F', 0)}"


def test_required_fields_on_each_entry():
    required = {"id", "name", "dimension", "config_patch", "param_grid",
                "default_params", "exclude_10sec", "requires_reference",
                "requires_dynamic_features", "computed_features", "description"}
    for h_id, entry in HYPOTHESIS_REGISTRY.items():
        missing = required - set(entry.keys())
        assert not missing, f"{h_id} missing fields: {missing}"


def test_h37_has_exclude_10sec_true():
    h37 = HYPOTHESIS_REGISTRY.get("H37")
    assert h37 is not None, "H37 not found in registry"
    assert h37["exclude_10sec"] is True, f"H37 exclude_10sec should be True, got {h37['exclude_10sec']}"


def test_h19_has_requires_reference_true():
    h19 = HYPOTHESIS_REGISTRY.get("H19")
    assert h19 is not None, "H19 not found in registry"
    assert h19["requires_reference"] is True, f"H19 requires_reference should be True"


def test_h23_is_dimension_d_not_c():
    """H23 is Conditional adds — Dimension D per spec Section 3.4."""
    h23 = HYPOTHESIS_REGISTRY.get("H23")
    assert h23 is not None, "H23 not found in registry"
    assert h23["dimension"] == "D", (
        f"H23 must be in Dimension D (Structural Modifications), got '{h23['dimension']}'. "
        "H23 is 'Conditional adds' per spec Section 3.4, not a filter."
    )


def test_dimension_a_hypotheses_have_trigger_mechanism_in_config_patch():
    """H1, H3, H8, H9, H10 should set trigger_mechanism in config_patch."""
    for h_id in ("H1", "H3", "H8", "H9", "H10"):
        entry = HYPOTHESIS_REGISTRY.get(h_id)
        assert entry is not None, f"{h_id} not in registry"
        config_patch = entry["config_patch"]
        has_trigger = any(
            k == "hypothesis.trigger_mechanism" or k.startswith("hypothesis.trigger")
            for k in config_patch.keys()
        )
        assert has_trigger, f"{h_id} config_patch missing trigger_mechanism: {config_patch}"


def test_dimension_c_filter_hypotheses_have_active_filters_in_config_patch():
    """Dimension C filter hypotheses (H4, H5, H6, ...) set active_filters."""
    # These are Dimension C non-simulator-internal hypotheses
    filter_hypotheses = {
        "H4", "H5", "H6", "H7", "H11", "H12", "H16",
        "H33", "H34", "H35", "H37", "H40", "H41"
    }
    for h_id in filter_hypotheses:
        entry = HYPOTHESIS_REGISTRY.get(h_id)
        assert entry is not None, f"{h_id} not in registry"
        config_patch = entry["config_patch"]
        has_filter = any(k.startswith("hypothesis.active_filters") for k in config_patch.keys())
        assert has_filter, f"{h_id} config_patch should set active_filters, got: {config_patch}"


# ---------------------------------------------------------------------------
# Screening experiments
# ---------------------------------------------------------------------------

def test_screening_experiments_returns_122():
    """41 × 3 bar types - 1 (H37 excluded from 10sec) = 122."""
    experiments = get_screening_experiments()
    assert len(experiments) == 122, (
        f"Expected 122 screening experiments, got {len(experiments)}"
    )


def test_h37_excluded_from_10sec():
    experiments = get_screening_experiments()
    h37_10sec = [
        e for e in experiments
        if e["hypothesis_id"] == "H37" and e["source_id"] == "bar_data_10sec_rot"
    ]
    assert len(h37_10sec) == 0, "H37 should not appear for bar_data_10sec_rot"


def test_h19_experiments_have_requires_reference():
    experiments = get_screening_experiments()
    h19_experiments = [e for e in experiments if e["hypothesis_id"] == "H19"]
    assert len(h19_experiments) == 3, f"H19 should have 3 experiments (one per bar type), got {len(h19_experiments)}"
    for exp in h19_experiments:
        assert exp.get("requires_reference") is True, (
            f"H19 experiment for {exp['source_id']} missing requires_reference=True"
        )


def test_screening_experiment_required_fields():
    """Each experiment must have hypothesis_id, source_id, params, requires_reference."""
    experiments = get_screening_experiments()
    for exp in experiments:
        for field in ("hypothesis_id", "source_id", "params", "requires_reference"):
            assert field in exp, f"Experiment missing field '{field}': {exp}"


def test_all_hypotheses_have_vol_and_tick_experiments():
    """Every hypothesis must have at least vol and tick experiments."""
    experiments = get_screening_experiments()
    by_hyp: dict[str, set] = {}
    for exp in experiments:
        h_id = exp["hypothesis_id"]
        src = exp["source_id"]
        by_hyp.setdefault(h_id, set()).add(src)

    for h_id, srcs in by_hyp.items():
        assert "bar_data_250vol_rot" in srcs, f"{h_id} missing vol experiment"
        assert "bar_data_250tick_rot" in srcs, f"{h_id} missing tick experiment"


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def test_get_hypothesis_returns_correct_entry():
    h1 = get_hypothesis("H1")
    assert h1["id"] == "H1"
    assert h1["dimension"] == "A"


def test_get_hypothesis_raises_on_unknown():
    with pytest.raises((KeyError, ValueError)):
        get_hypothesis("H99")


def test_get_hypotheses_by_dimension():
    dim_a = get_hypotheses_by_dimension("A")
    assert len(dim_a) == 5
    for entry in dim_a:
        assert entry["dimension"] == "A"


def test_build_experiment_config_applies_patch():
    """build_experiment_config should deep-copy base and apply config_patch."""
    base_config = {
        "hypothesis": {
            "trigger_mechanism": "fixed",
            "trigger_params": {"step_dist": 6.0},
            "active_filters": [],
            "filter_params": {},
        }
    }
    h1 = get_hypothesis("H1")
    params = {"hypothesis.trigger_params.multiplier": 0.5}
    result = build_experiment_config(base_config, h1, params)

    # Verify deep copy (original unchanged)
    assert base_config["hypothesis"]["trigger_mechanism"] == "fixed"

    # Verify patch applied
    assert result["hypothesis"]["trigger_mechanism"] != "fixed", (
        "H1 should change trigger_mechanism from 'fixed'"
    )
    # Verify param override applied
    assert result["hypothesis"]["trigger_params"].get("multiplier") == 0.5


def test_build_experiment_config_does_not_mutate_base():
    """Mutating result should not affect base_config."""
    base_config = {
        "hypothesis": {
            "trigger_mechanism": "fixed",
            "trigger_params": {"step_dist": 6.0},
            "active_filters": [],
            "filter_params": {},
        }
    }
    original_base = copy.deepcopy(base_config)
    h2 = get_hypothesis("H2")
    build_experiment_config(base_config, h2, {})
    assert base_config == original_base, "build_experiment_config must not mutate base_config"
