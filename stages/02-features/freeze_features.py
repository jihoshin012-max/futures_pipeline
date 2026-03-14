"""freeze_features.py — Human-triggered freeze script for Stage 02 feature approval.

After reviewing results.tsv, run this script to freeze approved features into
frozen_features.json. The JSON is then copied to stages/03-hypothesis/references/
for Stage 03 consumption.

Usage:
    python stages/02-features/freeze_features.py [--current-best-dir DIR]

Output:
    stages/02-features/output/frozen_features.json
"""

import argparse
import importlib.util
import json
import sys
from datetime import date
from pathlib import Path

# Resolve repo root: stages/02-features/ -> repo root (parents[2])
_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT))

_DEFAULT_CURRENT_BEST_DIR = (
    _REPO_ROOT / "stages" / "02-features" / "autoresearch" / "current_best"
)
_DEFAULT_OUTPUT_DIR = _REPO_ROOT / "stages" / "02-features" / "output"


def _load_feature_engine(current_best_dir: Path):
    """Load current_best/feature_engine.py via importlib.

    Returns the loaded module.
    Raises FileNotFoundError if feature_engine.py is not found.
    """
    feature_engine_path = current_best_dir / "feature_engine.py"
    if not feature_engine_path.exists():
        raise FileNotFoundError(
            f"current_best/feature_engine.py not found at {feature_engine_path}.\n"
            f"Ensure the autoresearch loop has run and produced a current_best/ directory."
        )

    spec = importlib.util.spec_from_file_location("feature_engine", str(feature_engine_path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _make_dummy_inputs():
    """Create dummy bar_df and touch_row to probe compute_features() for feature name keys.

    Returns a (bar_df, touch_row) tuple with minimal valid structure.
    """
    import pandas as pd

    # 5-bar OHLCV DataFrame — enough for any simple feature
    bar_df = pd.DataFrame({
        "Date": ["2025-10-01"] * 5,
        "Time": ["09:30:00", "09:31:00", "09:32:00", "09:33:00", "09:34:00"],
        "Open":  [19000.0, 19001.0, 19002.0, 19003.0, 19004.0],
        "High":  [19005.0, 19006.0, 19007.0, 19008.0, 19009.0],
        "Low":   [18995.0, 18996.0, 18997.0, 18998.0, 18999.0],
        "Close": [19002.0, 19003.0, 19004.0, 19005.0, 19006.0],
        "Volume": [100, 110, 120, 130, 140],
    })

    # Minimal touch_row Series with ZoneTop, ZoneBot, BarIndex
    touch_row = pd.Series({
        "ZoneTop": 19010.0,
        "ZoneBot": 18990.0,
        "BarIndex": 4,
    })

    return bar_df, touch_row


def freeze_features(current_best_dir: Path, output_dir: Path) -> Path:
    """Extract feature names from current_best/feature_engine.py and write frozen_features.json.

    Args:
        current_best_dir: Path to autoresearch/current_best/ directory.
        output_dir: Path to write frozen_features.json.

    Returns:
        Path to the written frozen_features.json file.
    """
    # Load the feature engine module
    module = _load_feature_engine(current_best_dir)
    if not hasattr(module, "compute_features"):
        raise AttributeError(
            f"feature_engine.py at {current_best_dir} does not export compute_features()."
        )

    # Probe compute_features() with dummy inputs to discover feature names
    bar_df, touch_row = _make_dummy_inputs()
    try:
        features_dict = module.compute_features(bar_df, touch_row)
    except Exception as e:
        raise RuntimeError(
            f"compute_features() raised an exception with dummy inputs: {e}\n"
            f"Verify feature_engine.py is valid before freezing."
        ) from e

    feature_names = list(features_dict.keys())
    if not feature_names:
        raise ValueError(
            "compute_features() returned an empty dict — nothing to freeze.\n"
            "Verify current_best/feature_engine.py has at least one feature."
        )

    # Build frozen_features.json
    frozen = {
        "features": feature_names,
        "frozen_date": date.today().isoformat(),
        "source": "current_best/feature_engine.py",
    }

    # Write to output/
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "frozen_features.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(frozen, f, indent=2)
        f.write("\n")

    return output_path


def main():
    parser = argparse.ArgumentParser(
        description="Freeze approved Stage 02 features into frozen_features.json."
    )
    parser.add_argument(
        "--current-best-dir",
        default=str(_DEFAULT_CURRENT_BEST_DIR),
        help=(
            "Path to current_best/ directory containing feature_engine.py "
            f"(default: {_DEFAULT_CURRENT_BEST_DIR})"
        ),
    )
    parser.add_argument(
        "--output-dir",
        default=str(_DEFAULT_OUTPUT_DIR),
        help=(
            f"Output directory for frozen_features.json (default: {_DEFAULT_OUTPUT_DIR})"
        ),
    )
    args = parser.parse_args()

    current_best_dir = Path(args.current_best_dir)
    output_dir = Path(args.output_dir)

    print(f"Loading current_best from: {current_best_dir}")
    output_path = freeze_features(current_best_dir, output_dir)

    with open(output_path, encoding="utf-8") as f:
        data = json.load(f)

    print(f"Frozen features: {data['features']}")
    print(f"Frozen date: {data['frozen_date']}")
    print(f"Source: {data['source']}")
    print(f"Output: {output_path}")
    print()
    print("Next step: Copy frozen_features.json to stages/03-hypothesis/references/")
    print("           for Stage 03 consumption.")


if __name__ == "__main__":
    main()
