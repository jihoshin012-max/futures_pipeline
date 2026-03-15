# archetype: rotational
"""Rotational feature evaluator — bar-level MWU spread computation.

Evaluates features for predictive power on bar-level outcomes (no touch events).
Uses the same tercile-based MWU spread test as zone_touch, but the unit of
analysis is the bar rather than the touch.

Outcome variables (from spec G-04):
    1. Direction: Did the next N bars move up or down from this bar's close? (Binary)
    2. Reversal quality: On bars where a reversal occurred, was it profitable within M bars?
    3. Add quality: On bars where an add occurred, did the position recover within M bars?

For Phase 1 (independent hypothesis screening), Outcome 1 (direction) is the
primary evaluator. Outcomes 2 and 3 require a running simulator and will be
added when the simulator is built (Phase B).

Interface:
    evaluate() -> dict
        Returns: {"features": [{"name": str, "spread": float, "mwu_p": float,
                                "kept": bool, "entry_time_violation": bool}],
                  "n_bars": int}

Entry-time enforcement:
    bar_df is truncated to iloc[:i] before passing to compute_features().
    Any feature reading beyond the truncation boundary raises IndexError.

Exports: evaluate
"""

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import mannwhitneyu

_REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_REPO_ROOT))

from shared.data_loader import load_bars  # noqa: E402

# Data manifest for path resolution
_MANIFEST_PATH = _REPO_ROOT / "stages/01-data/output/data_manifest.json"

# Direction outcome lookforward (bars)
_DIRECTION_LOOKFORWARD = 50

# Keep thresholds (same as zone_touch — from feature_rules.md)
_SPREAD_THRESHOLD = 0.15
_MWU_P_THRESHOLD = 0.10

# Sample stride — evaluating every bar on 138k+ bars is expensive;
# stride controls how many bars to skip between samples.
# Set to 1 for full evaluation, higher for faster screening.
_SAMPLE_STRIDE = 10


def _load_manifest() -> dict:
    """Load data_manifest.json."""
    import json
    with open(_MANIFEST_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _resolve_p1_bar_path(manifest: dict, source_id: str) -> str:
    """Resolve the P1 bar data path for a given rotational source."""
    sources = manifest.get("archetypes", {}).get("rotational", {}).get("sources", {})
    src_info = sources.get(source_id, {})
    path = src_info.get("path")
    if isinstance(path, list):
        # Find P1 file
        for p in path:
            if "P1" in p and "P2" not in p:
                return str(_REPO_ROOT / p)
        return str(_REPO_ROOT / path[0])
    elif path:
        return str(_REPO_ROOT / path)
    raise SystemExit(f"Cannot resolve P1 bar path for source '{source_id}' in manifest.")


def _get_period_boundaries(manifest: dict) -> tuple[str, str, str, str]:
    """Get P1a/P1b boundaries from manifest."""
    periods = manifest.get("archetypes", {}).get("rotational", {}).get("periods", {})
    p1a = periods.get("P1a", {})
    p1b = periods.get("P1b", {})
    return (
        p1a.get("start", "2025-09-21"),
        p1a.get("end", "2025-11-02"),
        p1b.get("start", "2025-11-03"),
        p1b.get("end", "2025-12-14"),
    )


def _load_feature_engine():
    """Load rotational feature_engine.py from same directory."""
    engine_path = Path(__file__).parent / "feature_engine.py"
    if not engine_path.exists():
        return None
    spec = importlib.util.spec_from_file_location("feature_engine", str(engine_path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _compute_direction_outcome(bar_df: pd.DataFrame, bar_idx: int, lookforward: int) -> float:
    """Compute direction outcome: +1 if price moved up over next N bars, -1 if down, 0 if flat.

    Uses close-to-close difference. Entry-time safe: only uses bars after bar_idx
    for outcome (these are future bars used as labels, not features).
    """
    if bar_idx + lookforward >= len(bar_df):
        return np.nan  # Not enough future bars
    current_close = bar_df.iloc[bar_idx]["Last"]
    future_close = bar_df.iloc[bar_idx + lookforward]["Last"]
    diff = future_close - current_close
    if diff > 0:
        return 1.0
    elif diff < 0:
        return -1.0
    return 0.0


def _compute_mwu_spread(
    p1a_values: pd.Series,
    p1a_outcome: pd.Series,
    p1b_values: pd.Series,
    p1b_outcome: pd.Series,
    feature_name: str,
) -> dict:
    """Compute tercile-based MWU spread for a single feature.

    Same logic as zone_touch evaluator: bin edges from P1a, applied OOS to P1b.
    """
    clean_p1a = p1a_values.dropna()
    if len(clean_p1a) < 3:
        return {
            "name": feature_name, "spread": 0.0, "mwu_p": 1.0,
            "kept": False, "entry_time_violation": False,
            "reason": "insufficient_data",
        }

    edges = np.percentile(clean_p1a, [33.33, 66.67])
    if edges[0] >= edges[1]:
        return {
            "name": feature_name, "spread": 0.0, "mwu_p": 1.0,
            "kept": False, "entry_time_violation": False,
            "reason": "degenerate_bins",
        }

    def assign_bins(vals):
        return pd.cut(
            vals,
            bins=[-np.inf, edges[0], edges[1], np.inf],
            labels=["low", "mid", "high"],
        )

    p1a_bins = assign_bins(p1a_values)
    p1b_bins = assign_bins(p1b_values)

    bin_means = {}
    for bin_label in ["low", "mid", "high"]:
        mask = p1a_bins == bin_label
        if mask.sum() > 0:
            bin_means[bin_label] = float(p1a_outcome[mask].mean())

    if len(bin_means) < 2:
        return {
            "name": feature_name, "spread": 0.0, "mwu_p": 1.0,
            "kept": False, "entry_time_violation": False,
            "reason": "too_few_populated_bins",
        }

    best_bin = max(bin_means, key=bin_means.get)
    worst_bin = min(bin_means, key=bin_means.get)

    p1a_best = p1a_outcome[p1a_bins == best_bin]
    p1a_worst = p1a_outcome[p1a_bins == worst_bin]
    p1b_best = p1b_outcome[p1b_bins == best_bin]

    spread = float(p1a_best.mean() - p1a_worst.mean()) if len(p1a_best) > 0 and len(p1a_worst) > 0 else 0.0

    if len(p1a_best) < 2 or len(p1b_best) < 2:
        mwu_p = 1.0
    else:
        _, mwu_p = mannwhitneyu(p1a_best, p1b_best, alternative="two-sided")
        mwu_p = float(mwu_p)

    kept = (spread > _SPREAD_THRESHOLD) and (mwu_p < _MWU_P_THRESHOLD)
    return {
        "name": feature_name,
        "spread": round(spread, 4),
        "mwu_p": round(mwu_p, 6),
        "kept": kept,
        "entry_time_violation": False,
        "reason": "ok" if kept else "threshold_not_met",
    }


def evaluate(source_id: str = "bar_data_250vol_rot") -> dict:
    """Evaluate features for rotational archetype on P1 bar data.

    Args:
        source_id: Which primary bar source to evaluate on. Defaults to 250-vol.

    Returns:
        dict with "features" list and "n_bars" count.
    """
    manifest = _load_manifest()
    bar_path = _resolve_p1_bar_path(manifest, source_id)
    p1a_start, p1a_end, p1b_start, p1b_end = _get_period_boundaries(manifest)

    bar_df = load_bars(bar_path)
    n_bars = len(bar_df)

    feature_engine = _load_feature_engine()
    if feature_engine is None:
        return {"features": [], "n_bars": n_bars}

    # P1a/P1b split by datetime
    p1a_end_ts = pd.Timestamp(p1a_end + " 23:59:59")
    p1b_start_ts = pd.Timestamp(p1b_start)
    p1b_end_ts = pd.Timestamp(p1b_end + " 23:59:59")

    p1a_mask = bar_df["datetime"] <= p1a_end_ts
    p1b_mask = (bar_df["datetime"] >= p1b_start_ts) & (bar_df["datetime"] <= p1b_end_ts)

    p1a_indices = bar_df.index[p1a_mask].tolist()
    p1b_indices = bar_df.index[p1b_mask].tolist()

    # Sample bars at stride intervals (full eval on 138k bars is expensive)
    p1a_sample = p1a_indices[::_SAMPLE_STRIDE]
    p1b_sample = p1b_indices[::_SAMPLE_STRIDE]

    # Collect feature values + outcomes
    feature_data: dict[str, dict] = {}

    def _process_bars(indices, period_label):
        for bar_idx in indices:
            # Direction outcome (future bars — used as label, not feature)
            outcome = _compute_direction_outcome(bar_df, bar_idx, _DIRECTION_LOOKFORWARD)
            if np.isnan(outcome):
                continue

            # Entry-time truncation: features only see bars 0..bar_idx
            bar_df_truncated = bar_df.iloc[: bar_idx + 1]
            try:
                computed = feature_engine.compute_features(bar_df_truncated)
                for feat_name, feat_val in computed.items():
                    if feat_name not in feature_data:
                        feature_data[feat_name] = {
                            "p1a": [], "p1b": [],
                            "p1a_outcome": [], "p1b_outcome": [],
                            "violation": False,
                        }
                    feature_data[feat_name][period_label].append(float(feat_val))
                    feature_data[feat_name][f"{period_label}_outcome"].append(outcome)
            except (IndexError, KeyError, ValueError):
                for feat_name in list(feature_data.keys()):
                    feature_data[feat_name]["violation"] = True

    _process_bars(p1a_sample, "p1a")
    _process_bars(p1b_sample, "p1b")

    # Compute MWU spread per feature
    features_out = []
    for feat_name, data in feature_data.items():
        if data["violation"]:
            features_out.append({
                "name": feat_name, "spread": 0.0, "mwu_p": 1.0,
                "kept": False, "entry_time_violation": True,
                "reason": "entry_time_violation",
            })
            continue

        result = _compute_mwu_spread(
            pd.Series(data["p1a"]),
            pd.Series(data["p1a_outcome"]),
            pd.Series(data["p1b"]),
            pd.Series(data["p1b_outcome"]),
            feat_name,
        )
        features_out.append(result)

    return {
        "features": features_out,
        "n_bars": n_bars,
    }
