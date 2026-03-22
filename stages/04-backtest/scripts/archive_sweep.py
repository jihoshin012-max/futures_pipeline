# STATUS: ACTIVE
# PURPOSE: Archive completed sweep directories with summary preservation
# LAST RUN: 2026-03-22
"""
Archive a completed sweep directory from stages/04-backtest/rotational/
to archive/sweeps/, preserving summary files in the active tree.

Usage:
    python stages/04-backtest/scripts/archive_sweep.py <sweep_dir_name>

Example:
    python stages/04-backtest/scripts/archive_sweep.py frozen_anchor_sweep
"""

import os
import shutil
import sys
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
ROTATIONAL_DIR = REPO_ROOT / "stages" / "04-backtest" / "rotational"
ARCHIVE_DIR = REPO_ROOT / "archive" / "sweeps"
SUMMARIES_DIR = REPO_ROOT / "stages" / "04-backtest" / "references" / "sweep_summaries"
RESTRUCTURE_LOG = REPO_ROOT / "docs" / "RESTRUCTURE_LOG.md"

SUMMARY_PATTERNS = ["config_summary.csv", "*_analysis.md", "*_report.md", "sweep_metadata.json"]


def count_files_and_size(directory: Path) -> tuple[int, int]:
    """Return (file_count, total_bytes) for all files under directory."""
    count = 0
    total = 0
    for f in directory.rglob("*"):
        if f.is_file():
            count += 1
            total += f.stat().st_size
    return count, total


def format_size(size_bytes: int) -> str:
    """Format bytes as human-readable string."""
    if size_bytes >= 1_073_741_824:
        return f"{size_bytes / 1_073_741_824:.1f}G"
    if size_bytes >= 1_048_576:
        return f"{size_bytes / 1_048_576:.1f}M"
    if size_bytes >= 1024:
        return f"{size_bytes / 1024:.1f}K"
    return f"{size_bytes}B"


def find_summary_files(directory: Path) -> list[Path]:
    """Find summary files in the top level of a sweep directory."""
    found = []
    for pattern in SUMMARY_PATTERNS:
        found.extend(directory.glob(pattern))
    return sorted(set(found))


def append_to_log(sweep_name: str, file_count: int, size_str: str, summaries_copied: list[str]) -> None:
    """Append an archive entry to RESTRUCTURE_LOG.md."""
    today = date.today().isoformat()
    summary_note = ", ".join(summaries_copied) if summaries_copied else "none"

    entry = (
        f"\n**Sweep archived via archive_sweep.py** — {today}\n\n"
        f"| Action | Source | Destination | Details |\n"
        f"|--------|--------|-------------|--------|\n"
        f"| MOVE | `stages/04-backtest/rotational/{sweep_name}/` | `archive/sweeps/{sweep_name}/` "
        f"| {file_count} files, {size_str} |\n"
        f"| COPY | summaries | `stages/04-backtest/references/sweep_summaries/` "
        f"| {summary_note} |\n"
    )

    with open(RESTRUCTURE_LOG, "a", encoding="utf-8") as f:
        f.write(entry)


def main() -> None:
    if len(sys.argv) != 2:
        print("Usage: python archive_sweep.py <sweep_dir_name>")
        sys.exit(1)

    sweep_name = sys.argv[1]
    sweep_dir = ROTATIONAL_DIR / sweep_name

    # 1. Verify directory exists
    if not sweep_dir.is_dir():
        print(f"ERROR: {sweep_dir.relative_to(REPO_ROOT)} does not exist.")
        sys.exit(1)

    dest_dir = ARCHIVE_DIR / sweep_name
    if dest_dir.exists():
        print(f"ERROR: {dest_dir.relative_to(REPO_ROOT)} already exists in archive.")
        sys.exit(1)

    # 2. Count files and size
    file_count, total_bytes = count_files_and_size(sweep_dir)
    size_str = format_size(total_bytes)
    print(f"Sweep: {sweep_name}")
    print(f"  Files: {file_count}")
    print(f"  Size:  {size_str}")

    # 3. Find summary files
    summaries = find_summary_files(sweep_dir)
    if summaries:
        print(f"  Summaries found: {', '.join(f.name for f in summaries)}")
    else:
        print("  Summaries found: none")

    # 4. Copy summaries to references
    SUMMARIES_DIR.mkdir(parents=True, exist_ok=True)
    copied_names = []
    for src in summaries:
        dest_name = f"{sweep_name}_{src.name}" if src.name == "config_summary.csv" else src.name
        # Avoid overwriting if name collides with another sweep's file
        if src.name != "config_summary.csv":
            dest_name = f"{sweep_name}_{src.name}"
        dest = SUMMARIES_DIR / dest_name
        shutil.copy2(src, dest)
        copied_names.append(dest_name)
        print(f"  Copied: {src.name} -> sweep_summaries/{dest_name}")

    # 5. Move sweep directory to archive
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    shutil.move(str(sweep_dir), str(dest_dir))
    print(f"\nArchived to: archive/sweeps/{sweep_name}/")

    # 6. Append to restructure log
    if RESTRUCTURE_LOG.exists():
        append_to_log(sweep_name, file_count, size_str, copied_names)
        print(f"Logged to: docs/RESTRUCTURE_LOG.md")

    print("Done.")


if __name__ == "__main__":
    main()
