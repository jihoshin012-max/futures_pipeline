# archetype: rotational
"""Feature engine for rotational archetype.

Edit this file during Stage 02 autoresearch.
compute_features() takes bar_df only — no touch_row, since rotational is a bar-only archetype.
Features must be entry-time safe: only use bar_df rows up to the current bar index.

Exports: compute_features
"""

import sys
from pathlib import Path

# Resolve repo root: shared/archetypes/rotational/ -> repo root (parents[3])
_REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_REPO_ROOT))

from shared.data_loader import parse_instruments_md  # noqa: E402

# Cache instrument constants at module level (loaded once per import)
# parse_instruments_md resolves relative to cwd; use absolute path
_INSTRUMENTS_MD_PATH = _REPO_ROOT / "_config/instruments.md"
_NQ_CONSTANTS = parse_instruments_md("NQ", str(_INSTRUMENTS_MD_PATH))
_TICK_SIZE = _NQ_CONSTANTS["tick_size"]


def compute_features(bar_df) -> dict:
    """Compute features for rotational archetype. Edit during Stage 02 autoresearch.

    Args:
        bar_df: DataFrame of bars up to and including the current entry bar.
                Must only access rows available at entry time (no lookahead).

    Returns:
        dict mapping feature_name -> float value
        e.g. {'channel_width': 12.0}
    """
    features = {}

    # TODO: implement features during Stage 02 autoresearch

    return features
