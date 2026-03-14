# archetype: zone_touch
"""Feature engine for zone_touch archetype.

Edit this file during Stage 02 autoresearch.
compute_features() must be entry-time safe: only use bar_df rows and touch_row scalars.
Any access to bar_df beyond the truncation boundary (iloc[:BarIndex]) will raise IndexError,
which the evaluator catches and records as an entry_time_violation.

Exports: compute_features
"""

import sys
from pathlib import Path

# Resolve repo root: shared/archetypes/zone_touch/ -> repo root (parents[3])
_REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_REPO_ROOT))

from shared.data_loader import parse_instruments_md  # noqa: E402

# Cache instrument constants at module level (loaded once per import)
# parse_instruments_md resolves relative to cwd; use absolute path
_INSTRUMENTS_MD_PATH = _REPO_ROOT / "_config/instruments.md"
_NQ_CONSTANTS = parse_instruments_md("NQ", str(_INSTRUMENTS_MD_PATH))
_TICK_SIZE = _NQ_CONSTANTS["tick_size"]


def compute_features(bar_df, touch_row) -> dict:
    """Compute all registered features for a single touch.

    Args:
        bar_df: DataFrame of bars truncated at entry bar index (iloc[:BarIndex]).
                Any access at or beyond this boundary raises IndexError.
        touch_row: Series with entry-time touch data columns only.
                   Post-entry columns (Reaction, Penetration, etc.) are stripped
                   by feature_evaluator.py before passing here.

    Returns:
        dict mapping feature_name -> float value
        e.g. {'zone_width': 12.0}
    """
    features = {}

    # zone_width: computable from touch_row scalars only (entry-time safe, no bar_df needed)
    # ZoneTop and ZoneBot are set at zone formation time — always available at entry
    zone_width_ticks = (touch_row['ZoneTop'] - touch_row['ZoneBot']) / _TICK_SIZE
    features['zone_width'] = float(zone_width_ticks)

    return features
