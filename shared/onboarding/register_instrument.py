#!/usr/bin/env python3
"""
shared/onboarding/register_instrument.py
Register a new instrument in the pipeline.

Writes to: _config/instruments.md
Creates:   stages/01-data/data/bar_data/{volume,time,tick}/.gitkeep (for new instrument)

Run register_source.py separately for bar data source_ids after this.

Usage (from repo root):
  python shared/onboarding/register_instrument.py \\
    --symbol MNQ \\
    --exchange CME \\
    --full-name "Micro E-mini Nasdaq-100 Futures" \\
    --tick-size 0.25 \\
    --tick-value 0.50 \\
    --cost-ticks 2 \\
    --session-rth "09:30-16:15 ET" \\
    --session-eth "18:00-09:30 ET"
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


def main():
    p = argparse.ArgumentParser(description="Register a new instrument")
    p.add_argument("--symbol", required=True, help="e.g. MNQ, CL, MES")
    p.add_argument("--exchange", required=True, help="e.g. CME, CBOT")
    p.add_argument("--full-name", required=True, help="Full instrument name")
    p.add_argument("--tick-size", required=True, type=float)
    p.add_argument("--tick-value", required=True, type=float, help="Dollar value per tick")
    p.add_argument("--cost-ticks", required=True, type=int,
                   help="Round-trip transaction cost in ticks")
    p.add_argument("--session-rth", required=True, help="RTH session e.g. '09:30-16:15 ET'")
    p.add_argument("--session-eth", default="18:00-09:30 ET")
    args = p.parse_args()

    root = repo_root()
    today = date.today().isoformat()
    sym = args.symbol.upper()

    print(f"\nRegistering instrument: {sym}")
    print(f"{'─' * 50}")

    instruments_md = root / "_config" / "instruments.md"
    content = instruments_md.read_text()

    if f"### {sym}" in content or f"## {sym}" in content:
        print(f"  ⚠  Instrument '{sym}' already in instruments.md — skipping.")
    else:
        block = textwrap.dedent(f"""
            ### {sym}
            - Symbol: {sym} ({args.exchange} {args.full_name})
            - Tick size: {args.tick_size} points
            - Tick value: ${args.tick_value}
            - Session: RTH {args.session_rth} | ETH {args.session_eth}
            - Cost model (round trip): {args.cost_ticks} tick{'s' if args.cost_ticks != 1 else ''} = ${args.cost_ticks * args.tick_value:.2f}
            - Bar data prefix: {sym}_BarData
            - Margin: check current at {args.exchange} (varies)
            - Date registered: {today}
            - ⚠  Cost model requires human approval before any backtest uses this instrument.
        """)

        # Append before ## Template for new instrument
        insert_before = "\n## Template for new instrument"
        if insert_before in content:
            content = content.replace(insert_before, f"{block}{insert_before}")
        else:
            content += block
        instruments_md.write_text(content)
        print(f"  ✓  {sym} added to _config/instruments.md")
        print(f"     ⚠  Cost model requires human approval before any backtest uses this instrument")

    print(f"\n{'─' * 50}")
    print(f"  Done. Next steps:")
    print(f"")
    print(f"  1. Verify cost_ticks value in instruments.md — changing it affects all")
    print(f"     historical PF calculations for this instrument (Rule 5).")
    print(f"")
    print(f"  2. Register bar data source_ids for {sym}:")
    print(f"     python shared/onboarding/register_source.py \\")
    print(f"       --source-id {sym.lower()}_bar_data_volume \\")
    print(f"       --type price --bar-type volume \\")
    print(f"       --file-pattern '{sym}_BarData_250vol_*.txt' \\")
    print(f"       --periods 'P1, P2' --required-by '02-features, 04-backtest'")
    print(f"")
    print(f"  autocommit.sh will commit instruments.md automatically.")


if __name__ == "__main__":
    main()
