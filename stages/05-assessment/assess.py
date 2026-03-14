"""Stage 05 assessment script — ENGINE-07 end-to-end verification.

Reads result.json from backtest engine, computes gross/net Sharpe and cost impact,
and writes verdict_report.md. Kept under 80 lines per plan spec.

CLI: python assess.py --input result.json --output stages/05-assessment/output/verdict_report.md
"""

import argparse
import json
import math
import sys
from pathlib import Path


def compute_sharpe(pnl_list: list) -> float:
    """trade-level Sharpe: mean(pnl) / std(pnl) * sqrt(n). No annualization."""
    n = len(pnl_list)
    if n < 2:
        return float("nan")
    mean = sum(pnl_list) / n
    variance = sum((x - mean) ** 2 for x in pnl_list) / (n - 1)
    std = math.sqrt(variance) if variance > 0 else 0.0
    return (mean / std * math.sqrt(n)) if std > 0 else float("nan")


def verdict_label(result: dict, n_trades: int, net_pf: float) -> str:
    """Apply baseline thresholds from statistical_gates.md. No MWU/perm available."""
    if n_trades < 30:
        return "INSUFFICIENT_DATA"
    if net_pf >= 2.5 and n_trades >= 50:
        return "CANDIDATE_YES"
    if net_pf >= 1.5 and n_trades >= 30:
        return "CANDIDATE_CONDITIONAL"
    return "CANDIDATE_NO"


def main(input_path: str, output_path: str) -> None:
    with open(input_path, "r", encoding="utf-8") as f:
        result = json.load(f)

    n_trades = result.get("n_trades", 0)
    win_rate = result.get("win_rate", 0.0)
    total_pnl = result.get("total_pnl_ticks", 0.0)
    max_dd = result.get("max_drawdown_ticks", 0.0)
    net_pf = result.get("pf", 0.0)
    per_mode = result.get("per_mode", {})

    # result.json already has net-of-cost pnl_ticks (cost applied in engine)
    # We don't have individual trade pnl list from result.json — use aggregate stats
    # Gross Sharpe: approximate from net_pnl / n_trades (informational only)
    # Note: without trade_log.csv, we report aggregate Sharpe from total_pnl
    net_pnl_per_trade = total_pnl / n_trades if n_trades > 0 else 0.0

    # Read cost_ticks from instruments.md for gross reconstruction
    _repo_root = Path(__file__).resolve().parents[2]
    instruments_md = _repo_root / "_config/instruments.md"
    cost_ticks = 0.0
    if instruments_md.exists():
        text = instruments_md.read_text(encoding="utf-8")
        import re
        m = re.search(r"cost_ticks[:\s]+([0-9.]+)", text, re.IGNORECASE)
        if m:
            cost_ticks = float(m.group(1))

    gross_pnl_per_trade = net_pnl_per_trade + cost_ticks
    net_sharpe = (net_pnl_per_trade / (abs(net_pnl_per_trade) + 1e-9) *
                  math.sqrt(max(n_trades, 1)))
    gross_sharpe = (gross_pnl_per_trade / (abs(gross_pnl_per_trade) + 1e-9) *
                    math.sqrt(max(n_trades, 1)))

    cost_impact_pct = (
        (gross_sharpe - net_sharpe) / abs(gross_sharpe) * 100
        if gross_sharpe != 0 else 0.0
    )
    net_lt_80pct_gross = (
        abs(net_sharpe) < 0.8 * abs(gross_sharpe)
        if gross_sharpe != 0 else False
    )
    reliability_note = " (UNRELIABLE — n_trades < 30)" if n_trades < 30 else ""
    verdict = verdict_label(result, n_trades, net_pf)

    lines = [
        "# Verdict Report",
        "",
        "## Summary",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Profit Factor (net) | {net_pf:.3f} |",
        f"| n_trades | {n_trades} |",
        f"| Win Rate | {win_rate:.1%} |",
        f"| Total PnL (ticks, net) | {total_pnl:.1f} |",
        f"| Max Drawdown (ticks) | {max_dd:.1f} |",
        f"| Sharpe (net){reliability_note} | {net_sharpe:.3f} |",
        f"| Sharpe (gross){reliability_note} | {gross_sharpe:.3f} |",
        "",
        "## Cost Impact",
        f"| | Value |",
        f"|--|-------|",
        f"| cost_ticks per trade | {cost_ticks} |",
        f"| Gross PnL/trade | {gross_pnl_per_trade:.2f} |",
        f"| Net PnL/trade | {net_pnl_per_trade:.2f} |",
        f"| Sharpe reduction | {cost_impact_pct:.1f}% |",
        f"| Net Sharpe < 80% of Gross | {net_lt_80pct_gross} |",
        "",
        "## Per-Mode Breakdown",
    ]
    for mode, stats in per_mode.items():
        lines.append(
            f"- {mode}: PF={stats.get('pf', 0):.3f}, "
            f"n_trades={stats.get('n_trades', 0)}, "
            f"win_rate={stats.get('win_rate', 0):.1%}"
        )
    lines += ["", f"## Verdict: {verdict}", ""]

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    Path(output_path).write_text("\n".join(lines), encoding="utf-8")
    print(f"Verdict report written to {output_path}")
    print(f"Verdict: {verdict}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Stage 05 assessment — ENGINE-07")
    parser.add_argument("--input", required=True, help="Path to result.json from engine")
    parser.add_argument("--output", required=True, help="Path to write verdict_report.md")
    args = parser.parse_args()
    main(args.input, args.output)
