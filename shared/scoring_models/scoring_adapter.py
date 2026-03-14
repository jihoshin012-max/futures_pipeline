# archetype: shared
"""All adapters expose: score(touch_df) -> pd.Series[float]

Protocol and stub classes for scoring model adapters.
BinnedScoringAdapter is implemented as a placeholder (all-zero weights) — real calibration is Phase 5+ work.
SklearnScoringAdapter and ONNXScoringAdapter remain stubs (NotImplementedError) until Phase 5+.
"""

import json
import sys
from typing import Protocol
import pandas as pd


class ScoringAdapter(Protocol):
    """Scoring adapter protocol. All adapters must implement score()."""

    def score(self, touch_df: pd.DataFrame) -> "pd.Series[float]":
        """Score each row in touch_df. Returns float series aligned to touch_df index."""
        ...


class BinnedScoringAdapter:
    """Loads a JSON scoring model matching _template.json schema and scores via bin lookup.

    For the placeholder model (all weights={}), score() returns pd.Series of zeros
    aligned to touch_df.index. This is correct behavior — zero weights produce zero scores.
    Real bin lookup logic is implemented when calibration data exists (Phase 5+ work).
    """

    def __init__(self, model_path: str) -> None:
        self.model_path = model_path
        with open(model_path, "r", encoding="utf-8") as f:
            model = json.load(f)
        self.weights: dict = model.get("weights", {})
        self.bin_edges: dict = model.get("bin_edges", {})
        self.model_id: str = model.get("model_id", "")
        self.frozen_date: str = model.get("frozen_date", "uncalibrated")

    def score(self, touch_df: pd.DataFrame) -> "pd.Series[float]":
        """Score each row in touch_df.

        For the placeholder model (all weights={}), returns zeros aligned to touch_df.index.
        Per Pitfall 4: always returns pd.Series(scores, index=touch_df.index), never a plain list.

        Args:
            touch_df: DataFrame of zone touch rows to score.

        Returns:
            pd.Series of float scores aligned to touch_df.index.
        """
        # Placeholder: all weights are zero — return zeros aligned to index
        # Real binning logic: look up each feature's bin, multiply by weight, sum
        return pd.Series(0.0, index=touch_df.index, dtype=float)


class SklearnScoringAdapter:
    """Wraps a scikit-learn model with the ScoringAdapter interface."""

    def __init__(self, model_path: str) -> None:
        self.model_path = model_path

    def score(self, touch_df: pd.DataFrame) -> "pd.Series[float]":
        raise NotImplementedError("Implement in Phase 5+")


class ONNXScoringAdapter:
    """Wraps an ONNX runtime model with the ScoringAdapter interface."""

    def __init__(self, model_path: str) -> None:
        self.model_path = model_path

    def score(self, touch_df: pd.DataFrame) -> "pd.Series[float]":
        raise NotImplementedError("Implement in Phase 5+")


# Registry of valid adapter types
_ADAPTER_REGISTRY: dict = {
    "BinnedScoringAdapter": BinnedScoringAdapter,
    "SklearnScoringAdapter": SklearnScoringAdapter,
    "ONNXScoringAdapter": ONNXScoringAdapter,
}


def load_scoring_adapter(model_path: str, adapter_type: str) -> ScoringAdapter:
    """Factory function. Returns the appropriate ScoringAdapter for adapter_type.

    Args:
        model_path: Path to the serialized model file.
        adapter_type: One of 'BinnedScoringAdapter', 'SklearnScoringAdapter', 'ONNXScoringAdapter'.

    Returns:
        ScoringAdapter instance.

    Raises:
        SystemExit: If adapter_type is not recognized (names the unknown adapter and lists valid types).
    """
    if adapter_type not in _ADAPTER_REGISTRY:
        valid = ", ".join(sorted(_ADAPTER_REGISTRY.keys()))
        print(
            f"[scoring_adapter] ERROR: Unknown adapter_type '{adapter_type}'. "
            f"Valid types: {valid}",
            file=sys.stderr,
        )
        raise SystemExit(
            f"Unknown adapter_type '{adapter_type}'. Valid types: {valid}"
        )

    adapter_class = _ADAPTER_REGISTRY[adapter_type]
    return adapter_class(model_path)
