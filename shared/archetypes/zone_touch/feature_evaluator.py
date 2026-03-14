# archetype: zone_touch
"""Zone touch feature evaluator — standard interface contract.

Phase 5 placeholder: loads P1 touch data and returns empty features list.
Phase 6 adds real MWU spread computation via feature_engine.py.

Interface:
    evaluate() -> dict
        Returns: {"features": [{"name": str, "spread": float, "mwu_p": float, "kept": bool}],
                  "n_touches": int}

This function is stateless — no module-level state, no caching.
Each call loads fresh data from disk.

Exports: evaluate
"""

import sys
from pathlib import Path

# Resolve repo root from this file's location:
# shared/archetypes/zone_touch/feature_evaluator.py
# parents[0] = zone_touch/, parents[1] = archetypes/, parents[2] = shared/, parents[3] = repo root
_REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_REPO_ROOT))

from shared.data_loader import load_touches  # noqa: E402

# P1 touch data path — resolved from repo root per pipeline convention
_P1_TOUCHES_PATH = _REPO_ROOT / "stages/01-data/data/touches/ZRA_Hist_P1.csv"


def evaluate() -> dict:
    """Evaluate features for zone_touch archetype on P1 data.

    Phase 5 placeholder — loads P1 touch data and returns empty features list.
    Phase 6 adds real MWU spread computation when feature_engine.py is registered.

    Returns:
        dict with keys:
            "features": list of feature result dicts, each with keys:
                        "name" (str), "spread" (float), "mwu_p" (float), "kept" (bool)
            "n_touches": int — number of P1 touch rows loaded
    """
    # Load P1 touch data — stateless, no caching
    touch_df = load_touches(str(_P1_TOUCHES_PATH))
    n_touches = len(touch_df)

    # Phase 5: no features registered yet (feature_engine.py is Phase 6 work)
    # Return empty features list satisfying the interface contract
    return {
        "features": [],
        "n_touches": n_touches,
    }
