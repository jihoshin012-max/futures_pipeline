#!/usr/bin/env python
"""evaluate_features.py — Pure dispatcher for archetype feature evaluation.

Usage:
    python evaluate_features.py --archetype zone_touch [--output path/to/output.json]

Loads the archetype-specific feature_evaluator.py via importlib, calls evaluate(),
and writes feature_evaluation.json to the output path.

Never modify this file during autoresearch — it is the fixed harness.
"""

import argparse
import importlib
import importlib.util
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

# Resolve repo root: stages/02-features/autoresearch/ -> repo root (parents[3])
_REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_REPO_ROOT))

# Default paths
_DEFAULT_OUTPUT = _REPO_ROOT / "stages/02-features/autoresearch/feature_evaluation.json"
_DEFAULT_ARCHETYPE_BASE = _REPO_ROOT / "shared/archetypes"


def load_evaluator(archetype: str, archetype_base_dir: Path):
    """Load the feature_evaluator module for the given archetype via importlib.

    Args:
        archetype: Archetype name (e.g. "zone_touch").
        archetype_base_dir: Path to the archetypes root directory.

    Returns:
        The imported feature_evaluator module.

    Raises:
        SystemExit: If feature_evaluator.py is not found for the archetype.
    """
    evaluator_path = archetype_base_dir / archetype / "feature_evaluator.py"

    if not evaluator_path.exists():
        print(
            f"ERROR: feature_evaluator.py not found for archetype '{archetype}' at {evaluator_path}",
            file=sys.stderr,
        )
        sys.exit(1)

    spec = importlib.util.spec_from_file_location("feature_evaluator", str(evaluator_path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # Load fresh each time (no caching)
    return module


def main():
    parser = argparse.ArgumentParser(
        description="Dispatch to archetype feature evaluator and write feature_evaluation.json."
    )
    parser.add_argument(
        "--archetype",
        required=True,
        help="Archetype name (e.g. zone_touch). Must match a subdirectory under shared/archetypes/.",
    )
    parser.add_argument(
        "--output",
        default=str(_DEFAULT_OUTPUT),
        help="Output path for feature_evaluation.json.",
    )
    parser.add_argument(
        "--archetype-base-dir",
        default=str(_DEFAULT_ARCHETYPE_BASE),
        help="Override archetypes base directory (used in tests).",
    )
    args = parser.parse_args()

    archetype = args.archetype
    output_path = Path(args.output)
    archetype_base_dir = Path(args.archetype_base_dir)

    # Load the archetype's feature_evaluator module
    evaluator = load_evaluator(archetype, archetype_base_dir)

    # Call evaluate() — returns {"features": [...], "n_touches": int}
    result = evaluator.evaluate()

    # Wrap in standard output schema
    output = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "features_evaluated": result["features"],
    }

    # Write output JSON
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(output, f, indent=2)

    # Print summary
    n_features = len(result["features"])
    n_kept = sum(1 for f in result["features"] if f.get("kept", False))
    print(f"Features evaluated: {n_features}, kept: {n_kept}")
    print(f"Output written to: {output_path}")


if __name__ == "__main__":
    main()
