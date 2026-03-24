"""Unit tests for shared/data_loader.py

Tests load actual P1 data files to verify correct column handling,
datetime parsing, and sorting behavior.
"""

import os
import pytest
import pandas as pd

# Path to this file's directory, then navigate to repo root
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

BAR_FILE = os.path.join(REPO_ROOT, "stages/01-data/data/bar_data/volume/NQ_BarData_250vol_P1.txt")
TOUCH_FILE = os.path.join(REPO_ROOT, "stages/01-data/data/touches/NQ_ZTE_raw_P1.csv")
RAY_CTX_FILE = os.path.join(REPO_ROOT, "stages/01-data/data/touches/NQ_ray_context_P1.csv")
RAY_REF_FILE = os.path.join(REPO_ROOT, "stages/01-data/data/touches/NQ_ray_reference_P1.csv")
INSTRUMENTS_MD = os.path.join(REPO_ROOT, "_config/instruments.md")

from shared.data_loader import (load_bars, load_touches, load_data,
                                 load_zte_raw, load_ray_context, load_ray_reference,
                                 parse_instruments_md)


def test_load_bars_columns():
    """Bar file has space-after-comma headers — must strip to get clean column names."""
    df = load_bars(BAR_FILE)
    expected = ["Date", "Time", "Open", "High", "Low", "Last", "Volume", "NumberOfTrades", "BidVolume", "AskVolume"]
    assert list(df.columns[:10]) == expected, f"Got columns: {list(df.columns)}"


def test_load_bars_datetime_parsed():
    """Bars must have a parsed datetime column for sorting."""
    df = load_bars(BAR_FILE)
    assert "datetime" in df.columns, "Expected 'datetime' column from Date+Time parse"
    assert pd.api.types.is_datetime64_any_dtype(df["datetime"]), "datetime column must be datetime64 dtype"


def test_load_bars_sorted():
    """Bars must be sorted by datetime ascending (Pitfall 5: determinism requirement)."""
    df = load_bars(BAR_FILE)
    assert "datetime" in df.columns
    datetimes = df["datetime"].reset_index(drop=True)
    assert datetimes.is_monotonic_increasing, "Bar DataFrame must be sorted by datetime ascending"


def test_load_bars_nonempty():
    """Sanity: actual P1 file has data."""
    df = load_bars(BAR_FILE)
    assert len(df) > 0, "Expected rows in bar file"


def test_load_touches_columns():
    """ZTE_raw has 52 columns (unified ZRA+ZB4+ray).
    Key columns from ZRA (measurement), ZB4 (scoring), and ray (new) must all be present."""
    df = load_touches(TOUCH_FILE)
    assert len(df.columns) == 52, f"Expected 52 columns, got {len(df.columns)}: {list(df.columns)}"
    # ZRA measurement columns
    assert "DateTime" in df.columns
    assert "TouchType" in df.columns
    assert "Reaction" in df.columns
    # ZB4 scoring columns
    assert "ModeAssignment" in df.columns
    assert "QualityScore" in df.columns
    assert "CascadeState" in df.columns
    # Ray columns
    assert "DemandRayPrice" in df.columns
    assert "SupplyRayPrice" in df.columns


def test_load_touches_datetime_parsed():
    """DateTime column must be parsed as datetime64."""
    df = load_touches(TOUCH_FILE)
    assert "DateTime" in df.columns, "Expected 'DateTime' column"
    assert pd.api.types.is_datetime64_any_dtype(df["DateTime"]), "DateTime must be datetime64 dtype"


def test_load_touches_nonempty():
    """Sanity: actual P1 touch file has data."""
    df = load_touches(TOUCH_FILE)
    assert len(df) > 0, "Expected rows in touch file"


def test_load_data_returns_tuple():
    """load_data convenience wrapper returns (touches_df, bars_df) tuple."""
    touches, bars = load_data(TOUCH_FILE, BAR_FILE)
    assert isinstance(touches, pd.DataFrame), "First element must be touches DataFrame"
    assert isinstance(bars, pd.DataFrame), "Second element must be bars DataFrame"
    assert len(touches.columns) == 52
    assert "datetime" in bars.columns


# === ZTE-specific loader tests ===

@pytest.mark.skipif(not os.path.exists(TOUCH_FILE), reason="NQ_ZTE_raw_P1.csv not yet imported")
def test_load_zte_raw_columns():
    """ZTE raw CSV has 52 columns with all required fields."""
    df = load_zte_raw(TOUCH_FILE)
    assert len(df.columns) == 52, f"Expected 52 columns, got {len(df.columns)}"
    for col in ["DateTime", "TouchType", "Reaction", "ModeAssignment",
                "QualityScore", "CascadeState", "DemandRayPrice", "SupplyRayPrice"]:
        assert col in df.columns, f"Missing column: {col}"
    assert pd.api.types.is_datetime64_any_dtype(df["DateTime"])


@pytest.mark.skipif(not os.path.exists(RAY_CTX_FILE), reason="NQ_ray_context_P1.csv not yet imported")
def test_load_ray_context_columns():
    """Ray context CSV has 7 columns."""
    df = load_ray_context(RAY_CTX_FILE)
    assert len(df.columns) == 7, f"Expected 7 columns, got {len(df.columns)}"
    for col in ["TouchID", "RayPrice", "RaySide", "RayDirection",
                "RayDistTicks", "RayTF", "RayAgeBars"]:
        assert col in df.columns, f"Missing column: {col}"
    assert (df["RayAgeBars"] >= 0).all(), "RayAgeBars must be non-negative"


@pytest.mark.skipif(not os.path.exists(RAY_REF_FILE), reason="NQ_ray_reference_P1.csv not yet imported")
def test_load_ray_reference_columns():
    """Ray reference CSV has 10 columns."""
    df = load_ray_reference(RAY_REF_FILE)
    assert len(df.columns) == 10, f"Expected 10 columns, got {len(df.columns)}"
    for col in ["BaseBarIndex", "DateTime", "ChartSlot", "SourceLabel",
                "DemandRayPrice", "SupplyRayPrice"]:
        assert col in df.columns, f"Missing column: {col}"
    assert pd.api.types.is_datetime64_any_dtype(df["DateTime"])


def test_parse_instruments_nq():
    """Parse NQ from instruments.md — cost_ticks=3, tick_size=0.25, tick_value=5.0."""
    result = parse_instruments_md("NQ", config_path=INSTRUMENTS_MD)
    assert result["cost_ticks"] == 3, f"Expected cost_ticks=3, got {result['cost_ticks']}"
    assert result["tick_size"] == 0.25, f"Expected tick_size=0.25, got {result['tick_size']}"
    assert result["tick_value"] == 5.0, f"Expected tick_value=5.0, got {result['tick_value']}"


def test_parse_instruments_es():
    """Parse ES from instruments.md — cost_ticks=1."""
    result = parse_instruments_md("ES", config_path=INSTRUMENTS_MD)
    assert result["cost_ticks"] == 1


def test_parse_instruments_unknown():
    """Unknown instrument must raise ValueError with clear message."""
    with pytest.raises(ValueError, match="UNKNOWN"):
        parse_instruments_md("UNKNOWN", config_path=INSTRUMENTS_MD)
