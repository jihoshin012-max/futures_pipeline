# archetype: hmm_regime_fitter
"""
hmm_regime_fitter.py — Fit three independent GaussianHMM models on P1 bar data
and produce regime_labels.csv and hmm_regime_v1.pkl.

Pipeline rules enforced:
- P2 rows NEVER passed to fit() (P1_END boundary strictly inclusive)
- Standardization uses P1 mean/std only (applied to P2 rows using same stats)
- predict_proba() (filtered posteriors) used, NOT predict() (Viterbi)
- random_state=42 for reproducibility
- Convergence asserted after each fit
- Not-all-one-state asserted after each predict
"""

import logging
import pickle
from pathlib import Path

import numpy as np
import pandas as pd
from hmmlearn.hmm import GaussianHMM

# Import smoke test — verifies NumPy ABI compatibility (Pitfall 4)
assert GaussianHMM is not None, "hmmlearn import failed — check NumPy ABI compatibility"

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants (from _config/period_config.md — never hardcoded instrument values)
# ---------------------------------------------------------------------------
P1_END_STR = "2025-12-14"
P1_END = pd.Timestamp(P1_END_STR).date()
P1_DAYS_EXPECTED = 77
TOTAL_DAYS_EXPECTED = 144

# FOMC, CPI, NFP dates for P1+P2 range (2025-09-16 to 2026-03-02)
# Hard-coded per plan — only ~12 events in scope; reference file would be over-engineering.
MACRO_EVENT_DATES = {
    # FOMC meetings (rate decisions)
    "2025-09-18",  # FOMC rate decision
    "2025-11-07",  # FOMC rate decision
    "2025-12-18",  # FOMC rate decision
    "2026-01-29",  # FOMC rate decision
    # CPI releases (Consumer Price Index)
    "2025-09-11",  # CPI (pre-range, included for completeness)
    "2025-10-14",  # CPI
    "2025-11-13",  # CPI
    "2025-12-11",  # CPI
    "2026-01-15",  # CPI
    "2026-02-12",  # CPI
    # NFP releases (Non-Farm Payroll — always first Friday of month)
    "2025-10-03",  # NFP
    "2025-11-07",  # NFP (same day as FOMC this month)
    "2025-12-05",  # NFP
    "2026-01-09",  # NFP
    "2026-02-07",  # NFP
}
_MACRO_DATE_SET = {pd.Timestamp(d).date() for d in MACRO_EVENT_DATES}


# ---------------------------------------------------------------------------
# 1. load_all_bars
# ---------------------------------------------------------------------------

def load_all_bars(repo_root: Path) -> pd.DataFrame:
    """Concatenate P1 and P2 bar data files from stages/01-data/data/bar_data/.

    Columns: Date, Time, Open, High, Low, Last, Volume, NumberOfTrades, BidVolume, AskVolume
    datetime parsed with format='mixed' per verified bar data format.
    """
    bar_data_dir = repo_root / "stages" / "01-data" / "data" / "bar_data"
    bar_files = sorted(bar_data_dir.glob("NQ_BarData_*.txt"))
    if not bar_files:
        raise FileNotFoundError(f"No bar data files found in {bar_data_dir}")

    dfs = []
    for path in bar_files:
        df = pd.read_csv(path)
        df.columns = [c.strip() for c in df.columns]
        df["dt"] = pd.to_datetime(
            df["Date"].str.strip() + " " + df["Time"].str.strip(), format="mixed"
        )
        df["date"] = df["dt"].dt.date
        dfs.append(df)
        log.info("Loaded %d rows from %s", len(df), path.name)

    combined = pd.concat(dfs, ignore_index=True)
    combined.sort_values("dt", inplace=True)
    combined.reset_index(drop=True, inplace=True)
    log.info("Total bar rows loaded: %d", len(combined))
    return combined


# ---------------------------------------------------------------------------
# 2. aggregate_to_daily
# ---------------------------------------------------------------------------

def aggregate_to_daily(bar_df: pd.DataFrame) -> pd.DataFrame:
    """Group tick bars by date. Return columns: date, open, high, low, close, volume.

    Uses named aggregation syntax (pandas 3.0 compatible).
    """
    daily = (
        bar_df.groupby("date")
        .agg(
            open=("Open", "first"),
            high=("High", "max"),
            low=("Low", "min"),
            close=("Last", "last"),
            volume=("Volume", "sum"),
        )
        .reset_index()
    )
    daily = daily.sort_values("date").reset_index(drop=True)
    log.info("Aggregated to %d daily bars", len(daily))
    return daily


# ---------------------------------------------------------------------------
# 3. compute_trend_features
# ---------------------------------------------------------------------------

def compute_trend_features(daily: pd.DataFrame) -> np.ndarray:
    """Compute ADX (14-period) and 5-day return direction.

    Pure pandas/numpy — no TA library. ADX formula from RESEARCH.md Pattern 4.

    Returns array of shape (n_days, 2):
      col 0: ADX (14-period)
      col 1: 5-day return direction (sign of 5-day log return)
    """
    high = daily["high"]
    low = daily["low"]
    close = daily["close"]
    period = 14

    # True Range
    prev_close = close.shift(1)
    tr = pd.concat(
        [high - low, (high - prev_close).abs(), (low - prev_close).abs()], axis=1
    ).max(axis=1)

    # +DM and -DM
    up_move = high - high.shift(1)
    down_move = low.shift(1) - low
    plus_dm = up_move.where((up_move > down_move) & (up_move > 0), 0.0)
    minus_dm = down_move.where((down_move > up_move) & (down_move > 0), 0.0)

    # Smoothed with EMA
    atr = tr.ewm(span=period, adjust=False).mean()
    plus_di = 100.0 * plus_dm.ewm(span=period, adjust=False).mean() / atr
    minus_di = 100.0 * minus_dm.ewm(span=period, adjust=False).mean() / atr

    denom = (plus_di + minus_di).replace(0, np.nan)
    dx = 100.0 * (plus_di - minus_di).abs() / denom
    adx = dx.ewm(span=period, adjust=False).mean().fillna(0.0)

    # 5-day return direction
    log_ret_5 = np.log(close / close.shift(5)).fillna(0.0)
    ret_dir = np.sign(log_ret_5)

    return np.column_stack([adx.values, ret_dir.values])


# ---------------------------------------------------------------------------
# 4. compute_volatility_features
# ---------------------------------------------------------------------------

def compute_volatility_features(daily: pd.DataFrame) -> np.ndarray:
    """Compute ATR ratio and log volatility change.

    Returns array of shape (n_days, 2):
      col 0: ATR ratio = daily ATR / 20-day rolling mean ATR
      col 1: log vol change = log(day range / prev day range)
    """
    high = daily["high"]
    low = daily["low"]
    close = daily["close"]

    # Daily range as ATR proxy (simpler than full TR for volatility feature)
    daily_range = high - low

    # ATR ratio: daily range / 20-day rolling mean range
    rolling_mean = daily_range.rolling(window=20, min_periods=1).mean()
    atr_ratio = (daily_range / rolling_mean.replace(0, np.nan)).fillna(1.0)

    # Log vol change: log(today range / yesterday range)
    prev_range = daily_range.shift(1).replace(0, np.nan)
    log_vol_change = np.log(daily_range / prev_range).fillna(0.0)

    return np.column_stack([atr_ratio.values, log_vol_change.values])


# ---------------------------------------------------------------------------
# 5. compute_macro_flags
# ---------------------------------------------------------------------------

def compute_macro_flags(dates: pd.Series) -> np.ndarray:
    """Return 0/1 array where 1 = macro event day (FOMC, CPI, NFP).

    Event dates are hard-coded for the P1+P2 range (2025-09-16 to 2026-03-02).
    See MACRO_EVENT_DATES constant for documented list.
    """
    return np.array([1 if d in _MACRO_DATE_SET else 0 for d in dates], dtype=np.int8)


# ---------------------------------------------------------------------------
# 6. fit_hmm
# ---------------------------------------------------------------------------

def fit_hmm(X_p1: np.ndarray, n_components: int) -> GaussianHMM:
    """Standardize using P1 mean/std, fit GaussianHMM, assert convergence.

    X_p1 must contain ONLY P1 rows — P2 rows must never be passed here.

    Returns fitted GaussianHMM with the scaler stats stored for later application.
    """
    mean = X_p1.mean(axis=0)
    std = X_p1.std(axis=0) + 1e-8  # avoid division by zero

    X_scaled = (X_p1 - mean) / std

    model = GaussianHMM(
        n_components=n_components,
        covariance_type="diag",
        n_iter=100,
        random_state=42,
    )
    model.fit(X_scaled)

    assert model.monitor_.converged, (
        f"GaussianHMM(n_components={n_components}) did not converge — "
        "increase n_iter or check feature scaling"
    )

    # Store P1 standardization stats on model for downstream use
    model._p1_mean = mean
    model._p1_std = std

    log.info(
        "Fitted GaussianHMM(n_components=%d): converged=%s, means=%s",
        n_components, model.monitor_.converged, model.means_.round(2),
    )
    return model


# ---------------------------------------------------------------------------
# 7. assign_state_names_trend
# ---------------------------------------------------------------------------

def assign_state_names_trend(model: GaussianHMM, adx_col: int = 0) -> dict:
    """Map integer HMM states to 'trending'/'ranging'.

    Higher mean ADX = 'trending'; lower = 'ranging'.
    Returns dict: {state_int: label_str}
    """
    adx_means = model.means_[:, adx_col]
    sorted_states = np.argsort(adx_means)  # ascending: lowest ADX first

    names = {}
    names[int(sorted_states[0])] = "ranging"
    names[int(sorted_states[1])] = "trending"

    for state, name in names.items():
        log.info("Trend state %d -> '%s' (mean ADX col = %.3f)", state, name, adx_means[state])

    return names


# ---------------------------------------------------------------------------
# 8. assign_state_names_volatility
# ---------------------------------------------------------------------------

def assign_state_names_volatility(model: GaussianHMM, atr_ratio_col: int = 0) -> dict:
    """Map integer HMM states to 'high_vol'/'normal_vol'/'low_vol'.

    Ordered by mean ATR ratio ascending: lowest = low_vol, middle = normal_vol, highest = high_vol.
    Returns dict: {state_int: label_str}
    """
    atr_means = model.means_[:, atr_ratio_col]
    sorted_states = np.argsort(atr_means)  # ascending

    labels = ["low_vol", "normal_vol", "high_vol"]
    names = {}
    for rank, state in enumerate(sorted_states):
        names[int(state)] = labels[rank]
        log.info(
            "Vol state %d -> '%s' (mean ATR ratio col = %.3f)",
            int(state), labels[rank], atr_means[state],
        )

    return names


# ---------------------------------------------------------------------------
# 9. generate_labels
# ---------------------------------------------------------------------------

def generate_labels(
    daily: pd.DataFrame,
    trend_model: GaussianHMM,
    vol_model: GaussianHMM,
    trend_features_all: np.ndarray,
    vol_features_all: np.ndarray,
    trend_p1_stats: tuple,
    vol_p1_stats: tuple,
    macro_flags: np.ndarray,
    trend_names: dict,
    vol_names: dict,
) -> pd.DataFrame:
    """Apply predict_proba() on standardized full-range features.

    Standardization uses P1 stats only (no P2 leakage).
    Argmax of posterior = hard label per day.
    Maps integer states to string names.

    Returns DataFrame with columns: date, trend, volatility, macro.
    """
    t_mean, t_std = trend_p1_stats
    v_mean, v_std = vol_p1_stats

    trend_scaled = (trend_features_all - t_mean) / t_std
    vol_scaled = (vol_features_all - v_mean) / v_std

    # predict_proba() = filtered posteriors (NOT Viterbi predict())
    trend_proba = trend_model.predict_proba(trend_scaled)
    vol_proba = vol_model.predict_proba(vol_scaled)

    trend_int = trend_proba.argmax(axis=1)
    vol_int = vol_proba.argmax(axis=1)

    assert len(np.unique(trend_int)) == trend_model.n_components, (
        "Trend HMM produced degenerate (all-one-state) output"
    )
    assert len(np.unique(vol_int)) == vol_model.n_components, (
        "Volatility HMM produced degenerate (all-one-state) output"
    )

    trend_labels = [trend_names[i] for i in trend_int]
    vol_labels = [vol_names[i] for i in vol_int]
    macro_labels = ["event_day" if f == 1 else "normal_day" for f in macro_flags]

    labels_df = pd.DataFrame(
        {
            "date": daily["date"].values,
            "trend": trend_labels,
            "volatility": vol_labels,
            "macro": macro_labels,
        }
    )
    return labels_df


# ---------------------------------------------------------------------------
# 10. main
# ---------------------------------------------------------------------------

def main(repo_root: Path) -> None:
    """Orchestrator: load bars, aggregate, compute features, fit HMMs, generate labels.

    Outputs:
    - stages/01-data/data/labels/regime_labels.csv (144 rows)
    - shared/scoring_models/hmm_regime_v1.pkl ({'trend': model, 'volatility': model})
    """
    log.info("=== HMM Regime Fitter — start ===")
    log.info("repo_root: %s", repo_root.resolve())

    # Load and aggregate
    bar_df = load_all_bars(repo_root)
    daily = aggregate_to_daily(bar_df)

    log.info("Daily bars: %d days (expected %d)", len(daily), TOTAL_DAYS_EXPECTED)

    # Compute features (full range — P1 + P2)
    trend_features = compute_trend_features(daily)   # shape (n_days, 2)
    vol_features = compute_volatility_features(daily)  # shape (n_days, 2)
    macro_flags = compute_macro_flags(pd.Series(daily["date"]))

    # CRITICAL: P1 mask — inclusive of P1 end date, P2 rows NEVER reach fit()
    p1_mask = np.array([d <= P1_END for d in daily["date"]])
    p1_count = p1_mask.sum()
    log.info("P1 rows: %d (expected %d)", p1_count, P1_DAYS_EXPECTED)
    assert p1_count == P1_DAYS_EXPECTED, (
        f"P1 row count {p1_count} != expected {P1_DAYS_EXPECTED}. "
        "Check bar data files and P1_END boundary."
    )

    X_trend_p1 = trend_features[p1_mask]   # (77, 2) — P2 never touches fit()
    X_vol_p1 = vol_features[p1_mask]       # (77, 2) — P2 never touches fit()

    # Fit HMMs on P1 only
    log.info("Fitting trend HMM (2 states) on P1...")
    trend_model = fit_hmm(X_trend_p1, n_components=2)

    log.info("Fitting volatility HMM (3 states) on P1...")
    vol_model = fit_hmm(X_vol_p1, n_components=3)

    # Assign human-readable names to integer states
    trend_names = assign_state_names_trend(trend_model, adx_col=0)
    vol_names = assign_state_names_volatility(vol_model, atr_ratio_col=0)

    # P1 standardization stats (stored on model by fit_hmm, but also passed explicitly)
    trend_p1_stats = (trend_model._p1_mean, trend_model._p1_std)
    vol_p1_stats = (vol_model._p1_mean, vol_model._p1_std)

    # Generate labels — applies frozen models to P1+P2 using P1 standardization
    labels_df = generate_labels(
        daily, trend_model, vol_model,
        trend_features, vol_features,
        trend_p1_stats, vol_p1_stats,
        macro_flags, trend_names, vol_names,
    )
    log.info("Labels generated: %d rows", len(labels_df))

    # Save CSV
    labels_dir = repo_root / "stages" / "01-data" / "data" / "labels"
    labels_dir.mkdir(parents=True, exist_ok=True)
    labels_path = labels_dir / "regime_labels.csv"
    labels_df.to_csv(labels_path, index=False)
    log.info("Saved: %s", labels_path)

    # Serialize pkl — macro is calendar-based (not HMM), not stored in pkl
    pkl_dir = repo_root / "shared" / "scoring_models"
    pkl_dir.mkdir(parents=True, exist_ok=True)
    pkl_path = pkl_dir / "hmm_regime_v1.pkl"
    with open(pkl_path, "wb") as f:
        pickle.dump({"trend": trend_model, "volatility": vol_model}, f, protocol=4)
    log.info("Saved: %s", pkl_path)

    # Verify round-trip
    with open(pkl_path, "rb") as f:
        loaded = pickle.load(f)
    assert loaded["trend"].n_components == 2
    assert loaded["volatility"].n_components == 3
    log.info("Pkl round-trip verified.")

    log.info("=== HMM Regime Fitter — done ===")


if __name__ == "__main__":
    main(Path("."))
