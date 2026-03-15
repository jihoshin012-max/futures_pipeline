#!/usr/bin/env python3
"""
shared/onboarding/register_source.py
Register a new data source in the pipeline.

Writes to: _config/data_registry.md
Creates:   stages/01-data/references/{source_id}_schema.md
Creates:   stages/01-data/data/{subfolder}/ with .gitkeep

Does NOT commit — autocommit.sh and pre-commit hooks handle that.
Does NOT run Stage 01 — run manually after dropping data files in place.

Usage (from repo root):
  python shared/onboarding/register_source.py \\
    --source-id bar_data_250vol_rot \\
    --type price \\
    --description "250-vol OHLCV bars for rotational archetype" \\
    --bar-type volume \\
    --file-pattern "NQ_BarData_250vol_rot_*.csv" \\
    --periods "P1, P2" \\
    --required-by "02-features, 04-backtest"
"""

import argparse
import sys
import textwrap
from datetime import date
from pathlib import Path


def repo_root() -> Path:
    import subprocess
    try:
        r = subprocess.run(["git", "rev-parse", "--show-toplevel"],
                           capture_output=True, text=True, check=True)
        return Path(r.stdout.strip())
    except subprocess.CalledProcessError:
        print("ERROR: Run from inside the futures-pipeline repo.")
        sys.exit(1)


def data_subfolder(source_id: str, bar_type: str | None, source_type: str) -> Path:
    root = repo_root()
    base = root / "stages" / "01-data" / "data"
    if source_type == "price" and bar_type:
        return base / "bar_data" / bar_type
    elif source_type in ("touches",) or any(k in source_id for k in ("zra", "csv", "touch")):
        return base / "touches"
    elif source_type == "label" or any(k in source_id for k in ("label", "sbb", "regime")):
        return base / "labels"
    else:
        return base / source_id


def main():
    p = argparse.ArgumentParser(description="Register a new data source")
    p.add_argument("--source-id", required=True)
    p.add_argument("--type", required=True,
                   choices=["touches", "price", "label", "orderflow", "fundamental", "alt"])
    p.add_argument("--description", required=True)
    p.add_argument("--file-pattern", required=True)
    p.add_argument("--periods", required=True)
    p.add_argument("--required-by", required=True)
    p.add_argument("--bar-type", choices=["volume", "time", "tick"],
                   help="Required for price type")
    args = p.parse_args()

    if args.type == "price" and not args.bar_type:
        p.error("--bar-type required for price type")

    root = repo_root()
    today = date.today().isoformat()

    print(f"\nRegistering source: {args.source_id}")
    print(f"{'─' * 50}")

    # ── 1. data_registry.md ────────────────────────────────────────────────
    registry = root / "_config" / "data_registry.md"
    content = registry.read_text()

    if args.source_id in content:
        print(f"  ⚠  source_id '{args.source_id}' already in data_registry.md — skipping.")
    else:
        new_row = (
            f"| {args.source_id:<20} | {args.type:<10} | {args.description:<36} "
            f"| {args.periods:<8} | {args.file_pattern:<35} | {args.required_by:<24} |"
        )
        insert_before = "\n## Data Type Taxonomy"
        if insert_before in content:
            content = content.replace(insert_before, f"\n{new_row}{insert_before}")
        else:
            content += f"\n{new_row}\n"
        # Update last_reviewed
        content = content.replace(
            content.split("last_reviewed:")[1].split("\n")[0],
            f" {today}"
        ) if "last_reviewed:" in content else content
        registry.write_text(content)
        print(f"  ✓  Row added to _config/data_registry.md")

    # ── 2. Schema file ─────────────────────────────────────────────────────
    schema_dir = root / "stages" / "01-data" / "references"
    schema_path = schema_dir / f"{args.source_id}_schema.md"

    if schema_path.exists():
        print(f"  ⚠  Schema file already exists — skipping: {schema_path.name}")
    else:
        schema_content = textwrap.dedent(f"""\
            # {args.description} Schema
            last_reviewed: {today}
            # source_id: {args.source_id}
            # Required columns for {args.source_id} data files.
            # Validation fails if any required column is missing.
            #
            # HUMAN ACTION REQUIRED:
            # Verify and complete the column list below against the
            # actual Sierra Chart export format before running Stage 01.

            | Column               | Type     | Description                                |
            |----------------------|----------|--------------------------------------------|
            | datetime             | str      | Bar datetime YYYY-MM-DD HH:MM:SS           |
            | open                 | float    | Bar open price                             |
            | high                 | float    | Bar high price                             |
            | low                  | float    | Bar low price                              |
            | close                | float    | Bar close price (or Last)                  |
            | volume               | int      | Bar volume                                 |

            # Add additional columns present in the actual data file above.
            # Remove any columns not present in the actual data file.
        """)
        schema_path.write_text(schema_content)
        print(f"  ✓  Schema stub created: stages/01-data/references/{schema_path.name}")

    # ── 3. Data subfolder ──────────────────────────────────────────────────
    folder = data_subfolder(args.source_id, args.bar_type, args.type)
    folder.mkdir(parents=True, exist_ok=True)
    gitkeep = folder / ".gitkeep"
    if not gitkeep.exists():
        gitkeep.touch()
    print(f"  ✓  Data folder ready: {folder.relative_to(root)}")

    # ── Summary ────────────────────────────────────────────────────────────
    print(f"\n{'─' * 50}")
    print(f"  Done. Next steps:")
    print(f"")
    print(f"  1. Open and complete the schema file:")
    print(f"     stages/01-data/references/{schema_path.name}")
    print(f"     Verify column names match actual Sierra Chart export format.")
    print(f"")
    print(f"  2. Drop data files into:")
    print(f"     {folder.relative_to(root)}/")
    print(f"     File names must match: {args.file_pattern}")
    print(f"")
    print(f"  3. Run Stage 01 validation:")
    print(f"     python stages/01-data/validate.py")
    print(f"")
    print(f"  4. Review stages/01-data/output/validation_report.md")
    print(f"")
    print(f"  autocommit.sh will commit file changes automatically.")
    print(f"  pre-commit hook will log PERIOD_CONFIG_CHANGED if applicable.")
    print(f"")
    print(f"  ⚠  Bar-type pairing rule: if this is a touches source,")
    print(f"     ensure it is paired with the correct bar_data_* source_id.")
    print(f"     Touches are coupled to whichever bar type ZRA was configured on.")


if __name__ == "__main__":
    main()
