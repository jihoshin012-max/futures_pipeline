# archetype: zone_touch
"""Zone touch feature evaluator — MWU spread computation.

Computes predictive spread for each feature via Mann-Whitney U test on P1a/P1b splits.

Outcome variable: precomputed PnL column ('pnl_ticks') if present in touch data.
Fallback: Reaction column (directional proxy for trade outcome).
# TODO: Replace Reaction fallback with true precomputed PnL once reference backtest is run
#       and pnl_ticks column is stored alongside touch CSV (Option C from Task 0 decision).

Interface:
    evaluate() -> dict
        Returns: {"features": [{"name": str, "spread": float, "mwu_p": float,
                                "kept": bool, "entry_time_violation": bool}],
                  "n_touches": int}

Entry-time enforcement:
    bar_df is truncated to iloc[:BarIndex] before passing to compute_features().
    Any feature reading beyond the truncation boundary raises IndexError, caught per-feature.
    Post-entry touch_row columns are stripped before passing to compute_features().

IMPORTANT — dispatcher contract:
    evaluate_features.py only forwards result["features"] to feature_evaluation.json.
    Top-level keys like "violation_count" are DROPPED. Therefore, entry_time_violation
    is embedded INSIDE each feature dict (not as a top-level key).

Exports: evaluate
"""

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import mannwhitneyu

# Resolve repo root from this file's location:
# shared/archetypes/zone_touch/feature_evaluator.py
# parents[0] = zone_touch/, parents[1] = archetypes/, parents[2] = shared/, parents[3] = repo root
_REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_REPO_ROOT))

from shared.data_loader import load_bars, load_touches  # noqa: E402

# Data paths
_P1_TOUCHES_PATH = _REPO_ROOT / "stages/01-data/data/touches/ZRA_Hist_P1.csv"
_P1_BARS_PATH = _REPO_ROOT / "stages/01-data/data/bar_data/volume/NQ_BarData_250vol_P1.txt"

# P1a/P1b split boundaries (from _config/period_config.md)
_P1A_END = pd.Timestamp('2025-10-31 23:59:59')
_P1B_START = pd.Timestamp('2025-11-01')
_P1B_END = pd.Timestamp('2025-12-14 23:59:59')

# Keep thresholds (from stages/02-features/references/feature_rules.md)
_SPREAD_THRESHOLD = 0.15
_MWU_P_THRESHOLD = 0.10

# Entry-time safe columns only — post-entry columns are stripped before compute_features()
# These are the columns available AT entry time (zone formation + approach metadata)
SAFE_TOUCH_COLUMNS = [
    'DateTime', 'BarIndex', 'TouchType', 'ApproachDir', 'TouchPrice',
    'ZoneTop', 'ZoneBot', 'HasVPRay', 'VPRayPrice', 'TouchSequence',
    'ZoneAgeBars', 'ApproachVelocity', 'TrendSlope', 'SourceChart',
    'SourceStudyID', 'SourceLabel',
]

# Post-entry columns to strip (lookahead — must not reach compute_features)
_POST_ENTRY_COLUMNS = {
    'Reaction', 'Penetration', 'ReactionPeakBar', 'ZoneBroken',
    'BreakBarIndex', 'BarsObserved',
    'RxnBar_30', 'RxnBar_50', 'RxnBar_80', 'RxnBar_120', 'RxnBar_160',
    'RxnBar_240', 'RxnBar_360',
    'PenBar_30', 'PenBar_50', 'PenBar_80', 'PenBar_120',
}


def _load_feature_engine():
    """Load feature_engine.py from the same directory via importlib.

    Returns:
        The feature_engine module, or None if not found.
    """
    engine_path = Path(__file__).parent / 'feature_engine.py'
    if not engine_path.exists():
        return None
    spec = importlib.util.spec_from_file_location("feature_engine", str(engine_path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _compute_mwu_spread(p1a_values, p1a_outcome, p1b_values, p1b_outcome, feature_name):
    """Compute tercile-based MWU spread for a single feature.

    Bin edges computed on P1a feature values, applied out-of-sample to P1b.
    'Best' bin is determined dynamically as the bin with highest mean outcome.

    Args:
        p1a_values: Series of feature values for P1a touches.
        p1a_outcome: Series of outcome values for P1a touches.
        p1b_values: Series of feature values for P1b touches.
        p1b_outcome: Series of outcome values for P1b touches.
        feature_name: str feature key.

    Returns:
        dict with name, spread, mwu_p, kept, entry_time_violation (always False here).
    """
    # Compute tercile edges on P1a feature values
    clean_p1a = p1a_values.dropna()
    if len(clean_p1a) < 3:
        return {
            "name": feature_name, "spread": 0.0, "mwu_p": 1.0,
            "kept": False, "entry_time_violation": False,
            "reason": "insufficient_data",
        }

    edges = np.percentile(clean_p1a, [33.33, 66.67])
    if edges[0] >= edges[1]:
        # Degenerate: constant or near-constant feature — no discriminative power
        return {
            "name": feature_name, "spread": 0.0, "mwu_p": 1.0,
            "kept": False, "entry_time_violation": False,
            "reason": "degenerate_bins",
        }

    def assign_bins(vals):
        return pd.cut(
            vals,
            bins=[-np.inf, edges[0], edges[1], np.inf],
            labels=['low', 'mid', 'high'],
        )

    p1a_bins = assign_bins(p1a_values)
    p1b_bins = assign_bins(p1b_values)

    # Compute mean outcome per bin on P1a to find best/worst dynamically
    bin_means = {}
    for bin_label in ['low', 'mid', 'high']:
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

    p1a_best_outcome = p1a_outcome[p1a_bins == best_bin]
    p1a_worst_outcome = p1a_outcome[p1a_bins == worst_bin]
    p1b_best_outcome = p1b_outcome[p1b_bins == best_bin]

    # Spread: best-bin mean outcome minus worst-bin mean outcome (on P1a)
    if len(p1a_best_outcome) > 0 and len(p1a_worst_outcome) > 0:
        spread = float(p1a_best_outcome.mean() - p1a_worst_outcome.mean())
    else:
        spread = 0.0

    # MWU: P1a best-bin vs P1b best-bin (cross-period consistency check)
    if len(p1a_best_outcome) < 2 or len(p1b_best_outcome) < 2:
        mwu_p = 1.0
    else:
        _, mwu_p = mannwhitneyu(p1a_best_outcome, p1b_best_outcome, alternative='two-sided')
        mwu_p = float(mwu_p)

    kept = (spread > _SPREAD_THRESHOLD) and (mwu_p < _MWU_P_THRESHOLD)
    return {
        "name": feature_name,
        "spread": spread,
        "mwu_p": mwu_p,
        "kept": kept,
        "entry_time_violation": False,
        "reason": "ok" if kept else "threshold_not_met",
    }


def evaluate() -> dict:
    """Evaluate features for zone_touch archetype on P1 data.

    Loads P1 touch and bar data, splits into P1a/P1b, runs each touch through
    compute_features() with entry-time truncation guard, then computes MWU spread.

    Outcome variable: pnl_ticks column if present (precomputed PnL from reference backtest).
    Fallback: Reaction column (directional proxy — see module docstring for TODO).

    Returns:
        dict with keys:
            "features": list of feature result dicts, each containing:
                        "name" (str), "spread" (float), "mwu_p" (float),
                        "kept" (bool), "entry_time_violation" (bool)
            "n_touches": int — number of P1 touch rows loaded
    """
    # Load data once
    touch_df = load_touches(str(_P1_TOUCHES_PATH))
    bar_df_full = load_bars(str(_P1_BARS_PATH))
    n_touches = len(touch_df)

    # Load feature engine — return empty list if not yet present
    feature_engine = _load_feature_engine()
    if feature_engine is None:
        return {"features": [], "n_touches": n_touches}

    # Determine outcome column: prefer precomputed pnl_ticks, fall back to Reaction
    # TODO: Replace with precomputed pnl_ticks column once reference backtest is run
    if 'pnl_ticks' in touch_df.columns:
        outcome_col = 'pnl_ticks'
    else:
        outcome_col = 'Reaction'  # Directional proxy — see module docstring

    # P1a/P1b split
    p1a_mask = touch_df['DateTime'] <= _P1A_END
    p1b_mask = (touch_df['DateTime'] >= _P1B_START) & (touch_df['DateTime'] <= _P1B_END)

    # Determine which safe columns are actually present in touch_df
    safe_cols_present = [c for c in SAFE_TOUCH_COLUMNS if c in touch_df.columns]

    # Collect feature values per feature name across P1a and P1b
    # Structure: {feature_name: {'p1a': [], 'p1b': [], 'p1a_outcome': [], 'p1b_outcome': [],
    #                             'violation': False}}
    feature_data = {}

    # Process P1a touches
    for _, touch_row in touch_df[p1a_mask].iterrows():
        bar_index = int(touch_row['BarIndex'])
        bar_df_truncated = bar_df_full.iloc[:bar_index]
        # Strip post-entry columns from touch_row
        safe_touch_row = touch_row[safe_cols_present]
        try:
            computed = feature_engine.compute_features(bar_df_truncated, safe_touch_row)
            for feat_name, feat_val in computed.items():
                if feat_name not in feature_data:
                    feature_data[feat_name] = {
                        'p1a': [], 'p1b': [],
                        'p1a_outcome': [], 'p1b_outcome': [],
                        'violation': False,
                    }
                feature_data[feat_name]['p1a'].append(float(feat_val))
                feature_data[feat_name]['p1a_outcome'].append(float(touch_row[outcome_col]))
        except (IndexError, KeyError, ValueError):
            # Entry-time violation: feature tried to access beyond truncation boundary
            # Mark violation for any feature that would have been computed in this row
            # We can't know which features would have been returned, so mark a sentinel
            if '__violation__' not in feature_data:
                feature_data['__violation__'] = {'count': 0}
            feature_data['__violation__']['count'] = feature_data.get(
                '__violation__', {'count': 0}
            ).get('count', 0) + 1
            # Mark all already-registered features as violated
            for feat_name in list(feature_data.keys()):
                if feat_name != '__violation__':
                    feature_data[feat_name]['violation'] = True

    # Process P1b touches
    for _, touch_row in touch_df[p1b_mask].iterrows():
        bar_index = int(touch_row['BarIndex'])
        bar_df_truncated = bar_df_full.iloc[:bar_index]
        safe_touch_row = touch_row[safe_cols_present]
        try:
            computed = feature_engine.compute_features(bar_df_truncated, safe_touch_row)
            for feat_name, feat_val in computed.items():
                if feat_name not in feature_data:
                    feature_data[feat_name] = {
                        'p1a': [], 'p1b': [],
                        'p1a_outcome': [], 'p1b_outcome': [],
                        'violation': False,
                    }
                feature_data[feat_name]['p1b'].append(float(feat_val))
                feature_data[feat_name]['p1b_outcome'].append(float(touch_row[outcome_col]))
        except (IndexError, KeyError, ValueError):
            for feat_name in list(feature_data.keys()):
                if feat_name != '__violation__':
                    feature_data[feat_name]['violation'] = True

    # Compute MWU spread for each feature
    features_out = []
    for feat_name, data in feature_data.items():
        if feat_name == '__violation__':
            continue

        if data['violation']:
            # Entry-time violation detected: block keep, report per-feature
            features_out.append({
                "name": feat_name,
                "spread": 0.0,
                "mwu_p": 1.0,
                "kept": False,
                "entry_time_violation": True,
                "reason": "entry_time_violation",
            })
            continue

        p1a_values = pd.Series(data['p1a'])
        p1a_outcome = pd.Series(data['p1a_outcome'])
        p1b_values = pd.Series(data['p1b'])
        p1b_outcome = pd.Series(data['p1b_outcome'])

        result = _compute_mwu_spread(p1a_values, p1a_outcome, p1b_values, p1b_outcome, feat_name)
        features_out.append(result)

    return {
        "features": features_out,
        "n_touches": n_touches,
    }
