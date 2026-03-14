"""Tests for the evaluate_features.py dispatcher.

Tests use tmp_path to create mock program.md and archetype directories with
stub feature_evaluator.py modules. These tests do NOT import the real
zone_touch evaluator — they test the dispatcher in isolation.
"""

import importlib
import json
import sys
import textwrap
from pathlib import Path

import pytest

# Add repo root so dispatcher imports resolve from any working directory
_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT))


def _create_mock_archetype(tmp_path: Path, archetype: str, evaluate_result: dict) -> Path:
    """Create a mock archetype directory with a stub feature_evaluator.py."""
    arch_dir = tmp_path / "shared" / "archetypes" / archetype
    arch_dir.mkdir(parents=True)
    evaluator_code = textwrap.dedent(f"""\
        # archetype: {archetype}
        def evaluate():
            return {repr(evaluate_result)}
    """)
    (arch_dir / "feature_evaluator.py").write_text(evaluator_code)
    return arch_dir


def _run_dispatcher(tmp_path: Path, archetype: str, output_path: Path) -> dict:
    """Import and call the dispatcher main logic directly via subprocess-style invocation."""
    import subprocess
    dispatcher = _REPO_ROOT / "stages" / "02-features" / "autoresearch" / "evaluate_features.py"
    result = subprocess.run(
        [
            sys.executable,
            str(dispatcher),
            "--archetype", archetype,
            "--archetype-base-dir", str(tmp_path / "shared" / "archetypes"),
            "--output", str(output_path),
        ],
        capture_output=True,
        text=True,
    )
    return result


class TestDispatcherLoadsEvaluator:
    """Test that dispatcher calls evaluate() and writes feature_evaluation.json."""

    def test_dispatcher_loads_evaluator(self, tmp_path):
        """Dispatcher calls evaluate() on mock evaluator, writes feature_evaluation.json."""
        evaluate_result = {
            "features": [
                {"name": "f1", "spread": 0.35, "mwu_p": 0.01, "kept": True},
            ],
            "n_touches": 50,
        }
        _create_mock_archetype(tmp_path, "mock_arch", evaluate_result)

        output_path = tmp_path / "feature_evaluation.json"
        result = _run_dispatcher(tmp_path, "mock_arch", output_path)

        assert result.returncode == 0, f"Dispatcher failed: {result.stderr}"
        assert output_path.exists(), "feature_evaluation.json was not created"

        with open(output_path) as f:
            data = json.load(f)

        assert "timestamp" in data
        assert "features_evaluated" in data
        assert len(data["features_evaluated"]) == 1
        assert data["features_evaluated"][0]["name"] == "f1"

    def test_dispatcher_reads_archetype(self, tmp_path):
        """Dispatcher correctly dispatches to the named archetype evaluator."""
        evaluate_result = {
            "features": [
                {"name": "arch_specific_feature", "spread": 0.42, "mwu_p": 0.03, "kept": True},
            ],
            "n_touches": 100,
        }
        _create_mock_archetype(tmp_path, "zone_mock", evaluate_result)

        output_path = tmp_path / "feature_evaluation.json"
        result = _run_dispatcher(tmp_path, "zone_mock", output_path)

        assert result.returncode == 0, f"Dispatcher failed: {result.stderr}"

        with open(output_path) as f:
            data = json.load(f)

        # Verify data came from the correct evaluator
        assert data["features_evaluated"][0]["name"] == "arch_specific_feature"

    def test_dispatcher_output_schema(self, tmp_path):
        """feature_evaluation.json has 'timestamp' and 'features_evaluated' keys."""
        evaluate_result = {"features": [], "n_touches": 42}
        _create_mock_archetype(tmp_path, "schema_arch", evaluate_result)

        output_path = tmp_path / "feature_evaluation.json"
        result = _run_dispatcher(tmp_path, "schema_arch", output_path)

        assert result.returncode == 0, f"Dispatcher failed: {result.stderr}"

        with open(output_path) as f:
            data = json.load(f)

        assert "timestamp" in data, "Missing 'timestamp' key"
        assert "features_evaluated" in data, "Missing 'features_evaluated' key"
        assert isinstance(data["features_evaluated"], list), "'features_evaluated' must be a list"
        # Timestamp should be a non-empty string (ISO format)
        assert isinstance(data["timestamp"], str) and len(data["timestamp"]) > 0

    def test_dispatcher_missing_evaluator(self, tmp_path):
        """Dispatcher exits with error when archetype evaluator does not exist."""
        # Do NOT create the archetype directory — it should be missing
        output_path = tmp_path / "feature_evaluation.json"
        result = _run_dispatcher(tmp_path, "nonexistent_arch", output_path)

        assert result.returncode != 0, "Expected non-zero exit code for missing evaluator"
        # Should print a clear error message naming the missing evaluator
        combined = result.stdout + result.stderr
        assert "nonexistent_arch" in combined, (
            f"Error message should name the missing archetype. Got: {combined}"
        )
        assert "feature_evaluator" in combined.lower() or "evaluator" in combined.lower(), (
            f"Error message should mention the evaluator file. Got: {combined}"
        )
        # Output file should NOT be created on failure
        assert not output_path.exists(), "Output should not be written on failure"
