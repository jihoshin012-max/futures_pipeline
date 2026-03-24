# archetype: shared
"""Parameterized data loading for touch and bar data.

No hardcoded paths — all paths come from function arguments.
The engine resolves paths from config JSON; this module is a pure loader.

Exports: load_bars, load_touches, load_data, load_zte_raw,
         load_ray_context, load_ray_reference, parse_instruments_md
"""

import re
import pandas as pd


def load_bars(path: str) -> pd.DataFrame:
    """Load bar data from a volume-bar CSV file.

    The file header uses spaces after commas, so column names are stripped.
    A combined datetime column is parsed from the Date and Time columns.
    The result is sorted by datetime ascending (determinism requirement).

    Args:
        path: Absolute or relative path to the bar data .txt/.csv file.

    Returns:
        DataFrame with stripped column names, parsed 'datetime' column,
        sorted ascending by datetime.
    """
    df = pd.read_csv(path)
    # Strip whitespace from column names (header has "Date, Time, Open, ..." format)
    df.columns = [c.strip() for c in df.columns]

    # Strip whitespace from string value columns (Date and Time may have leading space)
    for col in ("Date", "Time"):
        if col in df.columns:
            df[col] = df[col].astype(str).str.strip()

    # Parse datetime from Date + Time columns using format="mixed" for flexibility
    datetime_str = df["Date"] + " " + df["Time"]
    df["datetime"] = pd.to_datetime(datetime_str, format="mixed")

    # Sort ascending for determinism
    df = df.sort_values("datetime").reset_index(drop=True)

    return df


def load_touches(path: str) -> pd.DataFrame:
    """Load zone touch data from a ZRA_Hist CSV file.

    Args:
        path: Absolute or relative path to the touch CSV file.

    Returns:
        DataFrame with 32 columns and DateTime parsed as datetime64.
    """
    df = pd.read_csv(path)

    # Parse DateTime column using format="mixed" for flexibility
    df["DateTime"] = pd.to_datetime(df["DateTime"], format="mixed")

    return df


def load_data(touches_csv: str, bars_path: str) -> tuple:
    """Convenience wrapper that loads both touches and bars.

    Args:
        touches_csv: Path to the touch data CSV file.
        bars_path: Path to the bar data file.

    Returns:
        Tuple of (touches_df, bars_df).
    """
    return load_touches(touches_csv), load_bars(bars_path)


def load_zte_raw(path: str) -> pd.DataFrame:
    """Load ZTE unified zone touch data (52-column format).

    Args:
        path: Path to NQ_ZTE_raw_*.csv file.

    Returns:
        DataFrame with 52 columns and DateTime parsed as datetime64.
    """
    df = pd.read_csv(path)
    df.columns = [c.strip() for c in df.columns]
    for col in df.select_dtypes(include="object").columns:
        df[col] = df[col].str.strip()
    df["DateTime"] = pd.to_datetime(df["DateTime"], format="mixed")
    return df


def load_ray_context(path: str) -> pd.DataFrame:
    """Load ray context long-format CSV (7 columns).

    Args:
        path: Path to NQ_ray_context_*.csv file.

    Returns:
        DataFrame with 7 columns (TouchID, RayPrice, RaySide, etc.).
    """
    df = pd.read_csv(path)
    df.columns = [c.strip() for c in df.columns]
    for col in df.select_dtypes(include="object").columns:
        df[col] = df[col].str.strip()
    return df


def load_ray_reference(path: str) -> pd.DataFrame:
    """Load ray reference ground truth CSV (10 columns).

    Args:
        path: Path to NQ_ray_reference_*.csv file.

    Returns:
        DataFrame with 10 columns and DateTime parsed as datetime64.
    """
    df = pd.read_csv(path)
    df.columns = [c.strip() for c in df.columns]
    for col in df.select_dtypes(include="object").columns:
        df[col] = df[col].str.strip()
    df["DateTime"] = pd.to_datetime(df["DateTime"], format="mixed")
    return df


def parse_instruments_md(instrument: str, config_path: str = "_config/instruments.md") -> dict:
    """Parse instrument constants from the instruments.md registry.

    Reads tick_size, tick_value, and cost_ticks for the given instrument symbol.
    Never hardcode these values — always read from the registry per pipeline rule 5.

    Args:
        instrument: Instrument symbol (e.g. "NQ", "ES", "GC").
        config_path: Path to _config/instruments.md.

    Returns:
        Dict with keys: tick_size (float), tick_value (float), cost_ticks (int).

    Raises:
        ValueError: If the instrument symbol is not found in the registry.
    """
    with open(config_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Find the section for this instrument (e.g. "### NQ")
    # Stop at any heading (##, ###, etc.) or end of file
    section_pattern = rf"### {re.escape(instrument)}\n(.*?)(?=\n##|\Z)"
    match = re.search(section_pattern, content, re.DOTALL)
    if not match:
        raise ValueError(
            f"Instrument '{instrument}' not found in {config_path}. "
            f"Check the registry for valid symbols."
        )

    section = match.group(1)

    # Parse tick_size: "- Tick size: 0.25 points"
    tick_size_match = re.search(r"Tick size:\s*([\d.]+)\s*points", section)
    if not tick_size_match:
        raise ValueError(f"Could not parse tick_size for '{instrument}' in {config_path}")
    tick_size = float(tick_size_match.group(1))

    # Parse tick_value: "- Tick value: $5.00"
    tick_value_match = re.search(r"Tick value:\s*\$([\d.]+)", section)
    if not tick_value_match:
        raise ValueError(f"Could not parse tick_value for '{instrument}' in {config_path}")
    tick_value = float(tick_value_match.group(1))

    # Parse cost_ticks: "- Cost model (round trip): 3 ticks = $15.00" or "1 tick = ..."
    cost_ticks_match = re.search(r"Cost model \(round trip\):\s*(\d+)\s*ticks?", section)
    if not cost_ticks_match:
        raise ValueError(f"Could not parse cost_ticks for '{instrument}' in {config_path}")
    cost_ticks = int(cost_ticks_match.group(1))

    return {
        "tick_size": tick_size,
        "tick_value": tick_value,
        "cost_ticks": cost_ticks,
    }
