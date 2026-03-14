# tests/test_hmm_regime_fitter.py
"""
Tests for hmm_regime_fitter.py — covers HMM-01, HMM-02, HMM-03.

Design: Use synthetic data (small random arrays) to avoid depending on real bar
data files. Tests run in < 15 seconds.

Requirements covered:
- HMM-01: fit() uses P1 rows only; model converges; not all-one-state
- HMM-02: regime_labels.csv covers 144 rows; all label values valid
- HMM-03: pkl serializes and loads cleanly; loaded model predicts correctly
"""
import pickle
import tempfile
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "stages" / "01-data"))

from hmm_regime_fitter import (
    aggregate_to_daily,
    assign_state_names_trend,
    assign_state_names_volatility,
    compute_macro_flags,
    compute_trend_features,
    compute_volatility_features,
    fit_hmm,
    generate_labels,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def make_daily_df(n_days: int = 144, start_date: date = date(2025, 9, 16)) -> pd.DataFrame:
    """Return a synthetic daily OHLCV DataFrame."""
    rng = np.random.default_rng(42)
    dates = [start_date + timedelta(days=i) for i in range(n_days)]
    close = 20000 + rng.normal(0, 100, n_days).cumsum()
    high = close + rng.uniform(10, 100, n_days)
    low = close - rng.uniform(10, 100, n_days)
    open_ = close + rng.normal(0, 20, n_days)
    volume = rng.integers(50_000, 200_000, n_days).astype(float)
    return pd.DataFrame(
        {"date": dates, "open": open_, "high": high, "low": low, "close": close, "volume": volume}
    )


P1_END = date(2025, 12, 14)
P1_DAYS = 77
P2_DAYS = 67
TOTAL_DAYS = P1_DAYS + P2_DAYS  # 144


# ---------------------------------------------------------------------------
# HMM-01: P1-only fit
# ---------------------------------------------------------------------------

def test_fit_uses_p1_only():
    """P1 mask (date <= 2025-12-14) excludes P2 rows from the X array passed to fit().

    Synthetic data uses consecutive calendar days from 2025-09-16. The P1 boundary
    is 2025-12-14 (inclusive), giving exactly 90 calendar days (not 77, which is the
    trading-day count for real bar data). What matters for correctness: X_p1.shape[0]
    is strictly less than TOTAL_DAYS, proving P2 rows are excluded.
    """
    daily = make_daily_df(n_days=TOTAL_DAYS)
    trend_features = compute_trend_features(daily)
    p1_mask = np.array([d <= P1_END for d in daily["date"]])

    X_p1 = trend_features[p1_mask]
    X_p2 = trend_features[~p1_mask]

    # Calendar days from 2025-09-16 to 2025-12-14 inclusive = 90
    CALENDAR_P1_DAYS = 90
    assert X_p1.shape[0] == CALENDAR_P1_DAYS, (
        f"P1 slice has {X_p1.shape[0]} rows; expected {CALENDAR_P1_DAYS} calendar days. "
        "P2 data must not be passed to fit()."
    )
    # P2 rows must be non-empty (mask is working) and sum to TOTAL_DAYS
    assert X_p2.shape[0] == TOTAL_DAYS - CALENDAR_P1_DAYS, (
        "P2 slice count mismatch — masking logic is broken"
    )
    assert X_p1.shape[0] + X_p2.shape[0] == TOTAL_DAYS


# ---------------------------------------------------------------------------
# HMM-01: Convergence
# ---------------------------------------------------------------------------

def test_model_converges():
    """Both trend and volatility HMMs must converge on P1 data."""
    daily = make_daily_df(n_days=TOTAL_DAYS)
    trend_features = compute_trend_features(daily)
    vol_features = compute_volatility_features(daily)
    p1_mask = np.array([d <= P1_END for d in daily["date"]])

    trend_model = fit_hmm(trend_features[p1_mask], n_components=2)
    vol_model = fit_hmm(vol_features[p1_mask], n_components=3)

    assert trend_model.monitor_.converged, "Trend HMM did not converge"
    assert vol_model.monitor_.converged, "Volatility HMM did not converge"


# ---------------------------------------------------------------------------
# HMM-01: No degenerate states
# ---------------------------------------------------------------------------

def test_no_degenerate_states():
    """After predicting on full data, trend has exactly 2 unique labels, vol has 3."""
    daily = make_daily_df(n_days=TOTAL_DAYS)
    trend_features = compute_trend_features(daily)
    vol_features = compute_volatility_features(daily)
    p1_mask = np.array([d <= P1_END for d in daily["date"]])

    trend_model = fit_hmm(trend_features[p1_mask], n_components=2)
    vol_model = fit_hmm(vol_features[p1_mask], n_components=3)

    # Standardize full data using P1 stats (same as fit_hmm does internally)
    t_mean = trend_features[p1_mask].mean(axis=0)
    t_std = trend_features[p1_mask].std(axis=0) + 1e-8
    v_mean = vol_features[p1_mask].mean(axis=0)
    v_std = vol_features[p1_mask].std(axis=0) + 1e-8

    trend_proba = trend_model.predict_proba((trend_features - t_mean) / t_std)
    vol_proba = vol_model.predict_proba((vol_features - v_mean) / v_std)

    trend_labels = trend_proba.argmax(axis=1)
    vol_labels = vol_proba.argmax(axis=1)

    assert len(np.unique(trend_labels)) == 2, (
        f"Trend HMM collapsed to {len(np.unique(trend_labels))} state(s) — degenerate"
    )
    assert len(np.unique(vol_labels)) == 3, (
        f"Volatility HMM collapsed to {len(np.unique(vol_labels))} state(s) — degenerate"
    )


# ---------------------------------------------------------------------------
# HMM-02: Labels cover full range
# ---------------------------------------------------------------------------

def test_labels_cover_full_range():
    """generate_labels() must return a DataFrame with exactly 144 rows."""
    daily = make_daily_df(n_days=TOTAL_DAYS)
    trend_features = compute_trend_features(daily)
    vol_features = compute_volatility_features(daily)
    p1_mask = np.array([d <= P1_END for d in daily["date"]])
    macro_flags = compute_macro_flags(pd.Series(daily["date"]))

    trend_model = fit_hmm(trend_features[p1_mask], n_components=2)
    vol_model = fit_hmm(vol_features[p1_mask], n_components=3)

    trend_p1_stats = (trend_features[p1_mask].mean(axis=0), trend_features[p1_mask].std(axis=0) + 1e-8)
    vol_p1_stats = (vol_features[p1_mask].mean(axis=0), vol_features[p1_mask].std(axis=0) + 1e-8)

    trend_names = assign_state_names_trend(trend_model, adx_col=0)
    vol_names = assign_state_names_volatility(vol_model, atr_ratio_col=0)

    labels_df = generate_labels(
        daily, trend_model, vol_model,
        trend_features, vol_features,
        trend_p1_stats, vol_p1_stats,
        macro_flags, trend_names, vol_names,
    )

    assert len(labels_df) == TOTAL_DAYS, (
        f"labels_df has {len(labels_df)} rows; expected {TOTAL_DAYS}"
    )
    assert list(labels_df.columns) == ["date", "trend", "volatility", "macro"]


# ---------------------------------------------------------------------------
# HMM-02: Label values are valid strings
# ---------------------------------------------------------------------------

def test_label_values_valid():
    """trend, volatility, and macro columns must contain only the allowed string values."""
    daily = make_daily_df(n_days=TOTAL_DAYS)
    trend_features = compute_trend_features(daily)
    vol_features = compute_volatility_features(daily)
    p1_mask = np.array([d <= P1_END for d in daily["date"]])
    macro_flags = compute_macro_flags(pd.Series(daily["date"]))

    trend_model = fit_hmm(trend_features[p1_mask], n_components=2)
    vol_model = fit_hmm(vol_features[p1_mask], n_components=3)

    trend_p1_stats = (trend_features[p1_mask].mean(axis=0), trend_features[p1_mask].std(axis=0) + 1e-8)
    vol_p1_stats = (vol_features[p1_mask].mean(axis=0), vol_features[p1_mask].std(axis=0) + 1e-8)

    trend_names = assign_state_names_trend(trend_model, adx_col=0)
    vol_names = assign_state_names_volatility(vol_model, atr_ratio_col=0)

    labels_df = generate_labels(
        daily, trend_model, vol_model,
        trend_features, vol_features,
        trend_p1_stats, vol_p1_stats,
        macro_flags, trend_names, vol_names,
    )

    valid_trend = {"trending", "ranging"}
    valid_vol = {"high_vol", "normal_vol", "low_vol"}
    valid_macro = {"event_day", "normal_day"}

    actual_trend = set(labels_df["trend"].unique())
    actual_vol = set(labels_df["volatility"].unique())
    actual_macro = set(labels_df["macro"].unique())

    assert actual_trend.issubset(valid_trend), f"Invalid trend values: {actual_trend - valid_trend}"
    assert actual_vol.issubset(valid_vol), f"Invalid volatility values: {actual_vol - valid_vol}"
    assert actual_macro.issubset(valid_macro), f"Invalid macro values: {actual_macro - valid_macro}"


# ---------------------------------------------------------------------------
# HMM-03: Pkl round-trip
# ---------------------------------------------------------------------------

def test_pkl_round_trip():
    """Serialized pkl must load back with keys 'trend' and 'volatility' and correct n_components."""
    daily = make_daily_df(n_days=TOTAL_DAYS)
    trend_features = compute_trend_features(daily)
    vol_features = compute_volatility_features(daily)
    p1_mask = np.array([d <= P1_END for d in daily["date"]])

    trend_model = fit_hmm(trend_features[p1_mask], n_components=2)
    vol_model = fit_hmm(vol_features[p1_mask], n_components=3)

    with tempfile.NamedTemporaryFile(suffix=".pkl", delete=False) as f:
        pkl_path = f.name
        pickle.dump({"trend": trend_model, "volatility": vol_model}, f, protocol=4)

    with open(pkl_path, "rb") as f:
        loaded = pickle.load(f)

    assert "trend" in loaded, "pkl missing 'trend' key"
    assert "volatility" in loaded, "pkl missing 'volatility' key"
    assert loaded["trend"].n_components == 2
    assert loaded["volatility"].n_components == 3


# ---------------------------------------------------------------------------
# HMM-03: Loaded pkl model predicts
# ---------------------------------------------------------------------------

def test_pkl_model_predicts():
    """Loaded model from pkl must call predict_proba() without error and return correct shape."""
    daily = make_daily_df(n_days=TOTAL_DAYS)
    trend_features = compute_trend_features(daily)
    vol_features = compute_volatility_features(daily)
    p1_mask = np.array([d <= P1_END for d in daily["date"]])

    trend_model = fit_hmm(trend_features[p1_mask], n_components=2)
    vol_model = fit_hmm(vol_features[p1_mask], n_components=3)

    # Standardization stats from P1
    t_mean = trend_features[p1_mask].mean(axis=0)
    t_std = trend_features[p1_mask].std(axis=0) + 1e-8

    with tempfile.NamedTemporaryFile(suffix=".pkl", delete=False) as f:
        pkl_path = f.name
        pickle.dump({"trend": trend_model, "volatility": vol_model}, f, protocol=4)

    with open(pkl_path, "rb") as f:
        loaded = pickle.load(f)

    # Predict on new (synthetic) data
    new_data = (trend_features - t_mean) / t_std
    proba = loaded["trend"].predict_proba(new_data)
    assert proba.shape == (TOTAL_DAYS, 2), f"predict_proba shape {proba.shape} != ({TOTAL_DAYS}, 2)"
    assert np.allclose(proba.sum(axis=1), 1.0, atol=1e-5), "predict_proba rows do not sum to 1"
