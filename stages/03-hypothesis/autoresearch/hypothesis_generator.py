# archetype: zone_touch
"""Stage 03 hypothesis generator — wraps backtest_engine.py for P1 and P1b runs.

Usage:
    python hypothesis_generator.py --config hypothesis_config.json
                                   --output result.json
                                   --output-p1b result_p1b.json

This module runs backtest_engine.py twice:
1. Full P1 run using the original config.
2. P1b-filtered run using a temp config pointing to a filtered touches CSV.

Rule 4 enforcement: hypothesis_generator.py is the fixed harness that implements
internal replication (P1b sub-period test). The driver calls this via subprocess
and reads both result.json and result_p1b.json to apply the replication gate.
"""

import argparse
import csv
import json
import re
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

# ---------------------------------------------------------------------------
# P1b date constants
# Source of truth: _config/period_config.md
# Fallback constants used if file cannot be parsed.
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parents[3]

P1B_START = "2025-11-01"  # fallback — period_config.md is authoritative
P1B_END = "2025-12-14"    # fallback — period_config.md is authoritative


def _read_p1b_dates_from_config() -> tuple:
    """Read P1b start/end from _config/period_config.md.

    Returns (p1b_start, p1b_end) as 'YYYY-MM-DD' strings.
    Falls back to module-level constants if parsing fails.
    """
    config_path = _REPO_ROOT / "_config" / "period_config.md"
    try:
        content = config_path.read_text(encoding="utf-8")
        # Matches comment line: # P1a = 2025-09-16 to 2025-10-31 | P1b = 2025-11-01 to 2025-12-14
        match = re.search(
            r"P1b\s*=\s*(\d{4}-\d{2}-\d{2})\s+to\s+(\d{4}-\d{2}-\d{2})", content
        )
        if match:
            return match.group(1), match.group(2)
    except Exception:
        pass
    return P1B_START, P1B_END


# Read P1b dates at module load
_P1B_START, _P1B_END = _read_p1b_dates_from_config()


def write_p1b_filtered_csv(touches_csv_path: str) -> str:
    """Filter a touches CSV to P1b date range and write to a temp file.

    Args:
        touches_csv_path: Path to the full P1 touches CSV.

    Returns:
        Path to the temp filtered CSV file (caller must clean up).

    Raises:
        ValueError: If no rows fall within the P1b date range.
    """
    touches_csv_path = Path(touches_csv_path)

    p1b_start = datetime.strptime(_P1B_START, "%Y-%m-%d")
    p1b_end = datetime.strptime(_P1B_END, "%Y-%m-%d")

    kept_rows = []
    header = None

    with touches_csv_path.open(encoding="utf-8", newline="") as f:
        reader = csv.reader(f)
        for i, row in enumerate(reader):
            if i == 0:
                header = row
                continue
            if not row:
                continue
            # DateTime column is first column
            date_str = row[0].strip()
            if not date_str:
                continue
            try:
                # Handle formats like "11/15/2025 10:00" or "2025-11-15 10:00"
                for fmt in ("%m/%d/%Y %H:%M", "%Y-%m-%d %H:%M", "%m/%d/%Y", "%Y-%m-%d"):
                    try:
                        dt = datetime.strptime(date_str, fmt)
                        break
                    except ValueError:
                        continue
                else:
                    continue  # Could not parse date — skip row
                if p1b_start <= dt <= p1b_end:
                    kept_rows.append(row)
            except Exception:
                continue

    if not kept_rows:
        raise ValueError(
            f"No P1b rows found in {touches_csv_path} for range "
            f"{_P1B_START} to {_P1B_END}. Check period_config.md and touches CSV dates."
        )

    # Write to a temp file
    tmp_file = tempfile.NamedTemporaryFile(
        mode="w", suffix="_p1b_touches.csv", delete=False, encoding="utf-8", newline=""
    )
    writer = csv.writer(tmp_file)
    if header is not None:
        writer.writerow(header)
    writer.writerows(kept_rows)
    tmp_file.close()

    return tmp_file.name


def run(
    config_path: str,
    result_path: str,
    result_p1b_path: str,
    engine_path: str,
    repo_root: str,
) -> None:
    """Run backtest_engine.py for P1 and P1b sub-period.

    Steps:
    1. Run engine with original config -> result_path (full P1 result).
    2. Filter touches CSV to P1b date range -> temp file.
    3. Write temp config JSON pointing to P1b touches.
    4. Run engine with temp config -> result_p1b_path (P1b result).
    5. Clean up both temp files in finally block.

    Args:
        config_path: Path to hypothesis_config.json (agent-editable).
        result_path: Output path for full P1 result.json.
        result_p1b_path: Output path for P1b result_p1b.json.
        engine_path: Path to backtest_engine.py.
        repo_root: Repository root (used as cwd for engine calls).

    Raises:
        subprocess.CalledProcessError: If engine exits with non-zero code.
    """
    config_path = Path(config_path)
    result_path = Path(result_path)
    result_p1b_path = Path(result_p1b_path)
    engine_path = Path(engine_path)
    repo_root = Path(repo_root)

    config_data = json.loads(config_path.read_text(encoding="utf-8"))
    original_touches_csv = config_data.get("touches_csv", "")

    temp_csv_path = None
    temp_config_path = None

    try:
        # Step 1: Run full P1 engine
        subprocess.run(
            [
                sys.executable,
                str(engine_path),
                "--config", str(config_path),
                "--output", str(result_path),
            ],
            capture_output=True,
            text=True,
            cwd=str(repo_root),
            check=True,
        )

        # Step 2: Filter touches CSV to P1b range
        # Resolve the touches CSV path relative to repo_root if not absolute
        touches_path = Path(original_touches_csv)
        if not touches_path.is_absolute():
            touches_path = repo_root / touches_path

        temp_csv_path = write_p1b_filtered_csv(str(touches_path))

        # Step 3: Write temp config pointing to P1b-filtered touches
        p1b_config = dict(config_data)
        # Use relative path (relative to repo_root) for temp CSV, or absolute
        p1b_config["touches_csv"] = temp_csv_path

        tmp_config_file = tempfile.NamedTemporaryFile(
            mode="w", suffix="_p1b_config.json", delete=False, encoding="utf-8"
        )
        json.dump(p1b_config, tmp_config_file, indent=2)
        tmp_config_file.close()
        temp_config_path = tmp_config_file.name

        # Step 4: Run P1b engine
        subprocess.run(
            [
                sys.executable,
                str(engine_path),
                "--config", str(temp_config_path),
                "--output", str(result_p1b_path),
                "--output-p1b", str(result_p1b_path),
            ],
            capture_output=True,
            text=True,
            cwd=str(repo_root),
            check=True,
        )

    finally:
        # Step 5: Clean up temp files
        if temp_csv_path is not None:
            Path(temp_csv_path).unlink(missing_ok=True)
        if temp_config_path is not None:
            Path(temp_config_path).unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Stage 03 hypothesis generator — P1 + P1b dual engine runs."
    )
    parser.add_argument(
        "--config",
        required=True,
        help="Path to hypothesis_config.json",
    )
    parser.add_argument(
        "--output",
        required=True,
        help="Output path for full P1 result.json",
    )
    parser.add_argument(
        "--output-p1b",
        required=True,
        dest="output_p1b",
        help="Output path for P1b result_p1b.json",
    )
    parser.add_argument(
        "--engine",
        default=str(
            Path(__file__).resolve().parents[2] / "04-backtest" / "autoresearch" / "backtest_engine.py"
        ),
        help="Path to backtest_engine.py",
    )
    parser.add_argument(
        "--repo-root",
        default=str(_REPO_ROOT),
        help="Path to repository root",
    )
    args = parser.parse_args()
    run(
        config_path=args.config,
        result_path=args.output,
        result_p1b_path=args.output_p1b,
        engine_path=args.engine,
        repo_root=args.repo_root,
    )
