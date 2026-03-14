"""Stage 05 assessment script — ENGINE-07 end-to-end verification.

Reads result.json from backtest engine, computes gross/net Sharpe and cost impact,
and writes verdict_report.md. Optionally writes feedback_to_hypothesis.md and copies
it to Stage 03 references/prior_results.md when --feedback-output is provided.

CLI: python assess.py --input result.json --output stages/05-assessment/output/verdict_report.md
     [--feedback-output stages/05-assessment/output/feedback_to_hypothesis.md]
"""

import argparse
import json
import math
import shutil
import sys
from datetime import datetime, timezone
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


def _build_feedback_content(
    result: dict,
    n_trades: int,
    win_rate: float,
    max_dd: float,
    net_pf: float,
    per_mode: dict,
    verdict: str,
) -> str:
    """Generate feedback_to_hypothesis.md content from assessment data."""
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # What Worked: modes with PF > 1.5
    worked_lines = []
    avoid_lines = []
    for mode, stats in per_mode.items():
        pf = stats.get("pf", 0.0)
        n = stats.get("n_trades", 0)
        if pf > 1.5:
            worked_lines.append(f"- {mode}: PF={pf:.3f}, n_trades={n}")
        elif pf < 1.0:
            avoid_lines.append(
                f"- {mode}: PF={pf:.3f} — underperforming, consider parameter changes"
            )

    worked_section = (
        "\n".join(worked_lines)
        if worked_lines
        else "- No modes showed strong performance"
    )
    avoid_section = (
        "\n".join(avoid_lines)
        if avoid_lines
        else "- No critical underperformance detected"
    )

    # Regime Breakdown
    if per_mode:
        regime_lines = []
        for mode, stats in per_mode.items():
            pf = stats.get("pf", 0.0)
            n = stats.get("n_trades", 0)
            wr = stats.get("win_rate", 0.0)
            regime_lines.append(
                f"- {mode}: PF={pf:.3f}, n_trades={n}, win_rate={wr:.1%}"
            )
        regime_section = "\n".join(regime_lines)
    else:
        regime_section = "Not available for this assessment"

    lines = [
        "# Feedback to Hypothesis Generator",
        f"**Generated:** {timestamp}",
        "**Source:** Stage 05 assessment",
        f"**Verdict:** {verdict}",
        "",
        "## Key Metrics",
        f"- Profit Factor (net): {net_pf:.3f}",
        f"- n_trades: {n_trades}",
        f"- Win Rate: {win_rate:.1%}",
        f"- Max Drawdown (ticks): {max_dd:.1f}",
        "",
        "## Verdict:",
        verdict,
        "",
        "## What Worked",
        worked_section,
        "",
        "## What to Avoid",
        avoid_section,
        "",
        "## Regime Breakdown",
        regime_section,
        "",
    ]
    return "\n".join(lines)


def main(
    input_path: str,
    output_path: str,
    feedback_output_path: str = None,
    stage03_ref_path: str = None,
) -> None:
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
    net_pnl_per_trade = total_pnl / n_trades if n_trades > 0 else 0.0

    # Read cost_ticks from instruments.md using same regex as data_loader.parse_instruments_md
    _repo_root = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(_repo_root))
    cost_ticks = 0.0
    try:
        from shared.data_loader import parse_instruments_md
        instrument_info = parse_instruments_md(
            "NQ", config_path=str(_repo_root / "_config/instruments.md")
        )
        cost_ticks = float(instrument_info["cost_ticks"])
    except Exception:
        pass  # cost_ticks stays 0.0 if lookup fails

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

    # --- Feedback output (optional) ---
    if feedback_output_path is not None:
        feedback_content = _build_feedback_content(
            result=result,
            n_trades=n_trades,
            win_rate=win_rate,
            max_dd=max_dd,
            net_pf=net_pf,
            per_mode=per_mode,
            verdict=verdict,
        )
        Path(feedback_output_path).parent.mkdir(parents=True, exist_ok=True)
        Path(feedback_output_path).write_text(feedback_content, encoding="utf-8")
        print(f"Feedback written to {feedback_output_path}")

        # Copy to Stage 03 references/prior_results.md
        if stage03_ref_path is None:
            stage03_ref_path = str(
                _repo_root / "stages/03-hypothesis/references/prior_results.md"
            )
        Path(stage03_ref_path).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(feedback_output_path, stage03_ref_path)
        print(f"Feedback copied to {stage03_ref_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Stage 05 assessment — ENGINE-07")
    parser.add_argument("--input", required=True, help="Path to result.json from engine")
    parser.add_argument("--output", required=True, help="Path to write verdict_report.md")
    parser.add_argument(
        "--feedback-output",
        default=None,
        help="Optional path to write feedback_to_hypothesis.md",
    )
    args = parser.parse_args()
    main(
        input_path=args.input,
        output_path=args.output,
        feedback_output_path=args.feedback_output,
    )
