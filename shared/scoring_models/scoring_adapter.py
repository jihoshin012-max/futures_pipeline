# archetype: shared
"""All adapters expose: score(touch_df) -> pd.Series[float]

Protocol and stub classes for scoring model adapters.
Concrete implementations are written in Phase 4.
"""

from typing import Protocol
import pandas as pd


class ScoringAdapter(Protocol):
    """Scoring adapter protocol. All adapters must implement score()."""

    def score(self, touch_df: pd.DataFrame) -> "pd.Series[float]":
        """Score each row in touch_df. Returns float series aligned to touch_df index."""
        ...


class BinnedScoringAdapter:
    """Loads a JSON scoring model matching _template.json schema and scores via bin lookup."""

    def __init__(self, model_path: str) -> None:
        self.model_path = model_path

    def score(self, touch_df: pd.DataFrame) -> "pd.Series[float]":
        raise NotImplementedError("Implement in Phase 4")


class SklearnScoringAdapter:
    """Wraps a scikit-learn model with the ScoringAdapter interface."""

    def __init__(self, model_path: str) -> None:
        self.model_path = model_path

    def score(self, touch_df: pd.DataFrame) -> "pd.Series[float]":
        raise NotImplementedError("Implement in Phase 4")


class ONNXScoringAdapter:
    """Wraps an ONNX runtime model with the ScoringAdapter interface."""

    def __init__(self, model_path: str) -> None:
        self.model_path = model_path

    def score(self, touch_df: pd.DataFrame) -> "pd.Series[float]":
        raise NotImplementedError("Implement in Phase 4")


def load_scoring_adapter(model_path: str, adapter_type: str) -> ScoringAdapter:
    """Factory function. Returns the appropriate ScoringAdapter for adapter_type.

    Args:
        model_path: Path to the serialized model file.
        adapter_type: One of 'binned', 'sklearn', 'onnx'.

    Returns:
        ScoringAdapter instance.
    """
    raise NotImplementedError("Implement in Phase 4")
