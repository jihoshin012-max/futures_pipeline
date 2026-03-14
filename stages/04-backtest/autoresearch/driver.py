# archetype: zone_touch
"""Stage 04 autoresearch driver — keep/revert loop with budget enforcement.

Usage:
    python driver.py [--autoresearch-dir DIR] [--repo-root DIR]

The driver reads program.md every iteration (budget/metric are re-read each loop),
proposes a random perturbation of CANDIDATE fields, runs backtest_engine.py,
evaluates the keep/revert decision, logs results.tsv, and handles anomalies.
"""

import argparse
import copy
import json
import random
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MIN_TRADES = 30  # Minimum trades required to accept a "kept" result

# CANDIDATE fields that driver varies; all others are FIXED
_CANDIDATE_MODES = ["M1"]  # Only M1 mode params are varied

# ---------------------------------------------------------------------------
# Subprocess helper (isolated for patching in tests)
# ---------------------------------------------------------------------------

# Tests patch 'driver.subprocess' — expose it at module level
# (nothing extra needed; subprocess is already imported)


def _get_run_id() -> str:
    """Get short git hash of HEAD. Returns 'unknown' if git fails."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return "unknown"


# ---------------------------------------------------------------------------
# program.md parsing
# ---------------------------------------------------------------------------

def parse_program_md(path) -> dict:
    """Parse machine-readable fields from program.md.

    Returns dict with keys: metric (str), keep_rule (float), budget (int).
    Raises ValueError if any required field is missing or malformed.
    """
    path = Path(path)
    content = path.read_text(encoding="utf-8")

    result = {}
    for line in content.splitlines():
        line = line.strip()
        if line.startswith("METRIC:"):
            result["metric"] = line.split(":", 1)[1].strip()
        elif line.startswith("KEEP RULE:"):
            result["keep_rule"] = float(line.split(":", 1)[1].strip())
        elif line.startswith("BUDGET:"):
            result["budget"] = int(line.split(":", 1)[1].strip())

    missing = [k for k in ("metric", "keep_rule", "budget") if k not in result]
    if missing:
        raise ValueError(f"program.md missing required fields: {missing}")

    return result


# ---------------------------------------------------------------------------
# Trail step validation
# ---------------------------------------------------------------------------

def validate_trail_steps(steps: list) -> bool:
    """Validate trail steps against 5 rules from config_schema.md.

    Rules:
    1. 0-6 steps allowed
    2. trigger_ticks strictly monotonically increasing
    3. new_stop_ticks < trigger_ticks for each step
    4. new_stop_ticks non-decreasing across steps
    5. new_stop_ticks[0] >= 0

    Returns True if valid, False otherwise (does not raise).
    """
    if len(steps) > 6:
        return False
    if len(steps) == 0:
        return True

    triggers = [s["trigger_ticks"] for s in steps]
    new_stops = [s["new_stop_ticks"] for s in steps]

    # Rule 2: strictly monotonically increasing triggers
    for i in range(1, len(triggers)):
        if triggers[i] <= triggers[i - 1]:
            return False

    # Rule 3: new_stop_ticks < trigger_ticks
    for s in steps:
        if s["new_stop_ticks"] >= s["trigger_ticks"]:
            return False

    # Rule 4: new_stop_ticks non-decreasing
    for i in range(1, len(new_stops)):
        if new_stops[i] < new_stops[i - 1]:
            return False

    # Rule 5: new_stop_ticks[0] >= 0
    if new_stops[0] < 0:
        return False

    return True


# ---------------------------------------------------------------------------
# Parameter proposal
# ---------------------------------------------------------------------------

def propose_next_params(current_best_config: dict, results_tsv_path) -> dict:
    """Propose next params by random perturbation of CANDIDATE fields.

    FIXED fields (version, instrument, touches_csv, bar_data, scoring_model_path,
    archetype, active_modes, routing) are never changed.

    CANDIDATE fields varied:
    - stop_ticks: +/- 30, min 10
    - leg_targets: each +/- 20, min 10, sorted ascending
    - trail_steps: mutate trigger_ticks and new_stop_ticks with validation retry
    - time_cap_bars: +/- 20, min 10

    Returns a new config dict (deep copy, FIXED fields preserved).
    """
    proposed = copy.deepcopy(current_best_config)

    for mode in proposed.get("active_modes", []):
        if mode not in proposed:
            continue
        mode_cfg = proposed[mode]

        # stop_ticks
        delta = random.randint(-30, 30)
        mode_cfg["stop_ticks"] = max(10, mode_cfg["stop_ticks"] + delta)

        # leg_targets: each target perturbed, then sorted ascending
        new_targets = []
        for t in mode_cfg.get("leg_targets", []):
            delta = random.randint(-20, 20)
            new_targets.append(max(10, t + delta))
        # Sort and deduplicate (ensure strictly ascending for valid leg order)
        new_targets = sorted(set(new_targets))
        if not new_targets:
            new_targets = [50, 120, 240]
        mode_cfg["leg_targets"] = new_targets

        # time_cap_bars
        delta = random.randint(-20, 20)
        mode_cfg["time_cap_bars"] = max(10, mode_cfg["time_cap_bars"] + delta)

        # trail_steps: attempt mutation up to 10 times
        base_steps = mode_cfg.get("trail_steps", [])
        for _attempt in range(10):
            if not base_steps:
                new_steps = []
                break
            new_steps = []
            for step in base_steps:
                t_delta = random.randint(-15, 15)
                s_delta = random.randint(-10, 10)
                new_steps.append({
                    "trigger_ticks": max(1, step["trigger_ticks"] + t_delta),
                    "new_stop_ticks": max(0, step["new_stop_ticks"] + s_delta),
                })
            # Sort by trigger_ticks, deduplicate triggers
            new_steps.sort(key=lambda s: s["trigger_ticks"])
            # Make triggers strictly increasing
            for i in range(1, len(new_steps)):
                if new_steps[i]["trigger_ticks"] <= new_steps[i - 1]["trigger_ticks"]:
                    new_steps[i]["trigger_ticks"] = new_steps[i - 1]["trigger_ticks"] + 1
            # Ensure new_stop_ticks < trigger_ticks for each step
            for step in new_steps:
                if step["new_stop_ticks"] >= step["trigger_ticks"]:
                    step["new_stop_ticks"] = step["trigger_ticks"] - 1
            # Ensure new_stop_ticks non-decreasing
            for i in range(1, len(new_steps)):
                if new_steps[i]["new_stop_ticks"] < new_steps[i - 1]["new_stop_ticks"]:
                    new_steps[i]["new_stop_ticks"] = new_steps[i - 1]["new_stop_ticks"]
            # Re-check new_stop_ticks < trigger_ticks after above adjustments
            valid = True
            for step in new_steps:
                if step["new_stop_ticks"] >= step["trigger_ticks"]:
                    valid = False
                    break
            if valid and validate_trail_steps(new_steps):
                break
        else:
            # Fallback: keep original steps if all attempts failed
            new_steps = base_steps

        mode_cfg["trail_steps"] = new_steps

    return proposed


# ---------------------------------------------------------------------------
# results.tsv helpers
# ---------------------------------------------------------------------------

TSV_HEADER = (
    "run_id\tstage\ttimestamp\thypothesis_name\tarchetype\tversion\tfeatures"
    "\tpf_p1\tpf_p2\ttrades_p1\ttrades_p2\tmwu_p\tperm_p\tpctile\tn_prior_tests"
    "\tverdict\tsharpe_p1\tmax_dd_ticks\tavg_winner_ticks\tdd_multiple\twin_rate"
    "\tregime_breakdown\tapi_cost_usd\tnotes"
)


def _count_tsv_rows(tsv_path: Path) -> int:
    """Count data rows (excluding header) in results.tsv."""
    if not tsv_path.exists():
        return 0
    lines = tsv_path.read_text(encoding="utf-8").splitlines()
    # Skip header and blank lines
    return sum(1 for line in lines[1:] if line.strip())


def _append_tsv_row(tsv_path: Path, row_values: list) -> None:
    """Append one row to results.tsv as tab-delimited. Creates file with header if missing."""
    if not tsv_path.exists():
        tsv_path.write_text(TSV_HEADER + "\n", encoding="utf-8")
    with tsv_path.open("a", encoding="utf-8", newline="") as f:
        f.write("\t".join(str(v) for v in row_values) + "\n")


# ---------------------------------------------------------------------------
# Audit log helper
# ---------------------------------------------------------------------------

def _log_experiment_anomaly(
    audit_log_path: Path, run_id: str, stderr: str
) -> None:
    """Append EXPERIMENT_ANOMALY entry to audit_log.md. Does NOT git commit."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    # Limit stderr to last 20 lines
    stderr_lines = stderr.strip().splitlines()
    stderr_tail = "\n".join(stderr_lines[-20:]) if stderr_lines else "(none)"
    entry = (
        f"\n## {timestamp} | EXPERIMENT_ANOMALY\n"
        f"- stage: 04-backtest\n"
        f"- run_id: {run_id}\n"
        f"- detected_by: exit_code\n"
        f"- error_output: {stderr_tail}\n"
        f"- investigation: # TODO: fill in\n"
        f"- resolution: # TODO: fill in\n"
        f"- resolution_commit: # TODO: fill in\n"
        f"- generated_by: autoresearch driver\n"
    )
    with audit_log_path.open("a", encoding="utf-8") as f:
        f.write(entry)
    # git add (do not commit — autocommit.sh handles it)
    try:
        subprocess.run(
            ["git", "add", str(audit_log_path)],
            capture_output=True,
            text=True,
        )
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

def run_loop(
    autoresearch_dir,
    repo_root,
    max_iterations: int = None,
) -> None:
    """Run the keep/revert autoresearch loop.

    Args:
        autoresearch_dir: Path to stages/04-backtest/autoresearch/
        repo_root: Path to repository root (for engine cwd and audit_log.md)
        max_iterations: Hard cap on iterations (for testing). None = no cap.
    """
    autoresearch_dir = Path(autoresearch_dir)
    repo_root = Path(repo_root)

    engine_path = autoresearch_dir / "backtest_engine.py"
    exit_params_path = autoresearch_dir / "exit_params.json"
    current_best_path = autoresearch_dir / "current_best" / "exit_params.json"
    result_json_path = autoresearch_dir / "result.json"
    results_tsv_path = autoresearch_dir / "results.tsv"
    program_md_path = autoresearch_dir / "program.md"
    audit_log_path = repo_root / "audit" / "audit_log.md"

    # Load current best config and establish baseline metric
    current_best_config = json.loads(current_best_path.read_text(encoding="utf-8"))

    # Determine baseline metric from last "seeded" or "kept" row in results.tsv
    current_best_metric = _read_baseline_metric(results_tsv_path)

    iteration = 0

    while True:
        if max_iterations is not None and iteration >= max_iterations:
            break

        # Re-read program.md every iteration (Pitfall 2: budget/metric may change)
        program = parse_program_md(program_md_path)
        metric_field = program["metric"]
        keep_rule = program["keep_rule"]
        budget = program["budget"]

        # Count prior tests BEFORE this experiment (Pitfall 4: count before, not after)
        n_prior_tests = _count_tsv_rows(results_tsv_path)

        if n_prior_tests >= budget:
            print(f"Budget exhausted ({n_prior_tests} >= {budget}). Stopping.")
            break

        # Propose next params
        proposed_config = propose_next_params(current_best_config, results_tsv_path)

        # Write exit_params.json
        exit_params_path.write_text(
            json.dumps(proposed_config, indent=2), encoding="utf-8"
        )

        # Run backtest engine
        proc = subprocess.run(
            [
                sys.executable,
                str(engine_path),
                "--config",
                str(exit_params_path),
                "--output",
                str(result_json_path),
            ],
            capture_output=True,
            text=True,
            cwd=str(repo_root),
        )

        # Get run_id immediately after engine completes (Pitfall 1)
        run_id = _get_run_id()

        timestamp = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")

        if proc.returncode != 0:
            # Log anomaly and continue (do NOT abort)
            _log_experiment_anomaly(audit_log_path, run_id, proc.stderr)
            # Revert to prior best
            shutil.copy2(current_best_path, exit_params_path)
            iteration += 1
            continue

        # Read result
        result_data = json.loads(result_json_path.read_text(encoding="utf-8"))
        metric_value = float(result_data.get(metric_field, 0.0))
        n_trades = int(result_data.get("n_trades", 0))
        win_rate = float(result_data.get("win_rate", 0.0))
        max_dd = float(result_data.get("max_drawdown_ticks", 0.0))

        # Keep/revert decision
        improved = (metric_value > current_best_metric + keep_rule) and (n_trades >= MIN_TRADES)
        verdict = "kept" if improved else "reverted"

        if improved:
            shutil.copy2(exit_params_path, current_best_path)
            current_best_metric = metric_value
            current_best_config = proposed_config
        else:
            shutil.copy2(current_best_path, exit_params_path)

        # Append TSV row (all 24 columns)
        archetype = current_best_config.get("archetype", {}).get("name", "")
        version = current_best_config.get("version", "")
        row = [
            run_id,          # run_id
            "04-backtest",   # stage
            timestamp,       # timestamp
            "",              # hypothesis_name
            archetype,       # archetype
            version,         # version
            "",              # features
            metric_value,    # pf_p1
            "",              # pf_p2
            n_trades,        # trades_p1
            "",              # trades_p2
            "",              # mwu_p
            "",              # perm_p
            "",              # pctile
            n_prior_tests,   # n_prior_tests
            verdict,         # verdict
            "",              # sharpe_p1
            max_dd,          # max_dd_ticks
            "",              # avg_winner_ticks
            "",              # dd_multiple
            win_rate,        # win_rate
            "",              # regime_breakdown
            "",              # api_cost_usd
            "",              # notes
        ]
        _append_tsv_row(results_tsv_path, row)

        iteration += 1


def _read_baseline_metric(results_tsv_path: Path) -> float:
    """Read the pf_p1 from the most recent 'kept' or 'seeded' row in results.tsv.

    Returns 0.0 if no such row found (safe default — any positive result will be kept).
    """
    if not results_tsv_path.exists():
        return 0.0
    lines = results_tsv_path.read_text(encoding="utf-8").splitlines()
    if len(lines) < 2:
        return 0.0
    # Header is line 0; iterate data rows in reverse order
    header = lines[0].split("\t")
    try:
        pf_idx = header.index("pf_p1")
        verdict_idx = header.index("verdict")
    except ValueError:
        return 0.0

    for line in reversed(lines[1:]):
        if not line.strip():
            continue
        cols = line.split("\t")
        if len(cols) <= max(pf_idx, verdict_idx):
            continue
        verdict = cols[verdict_idx]
        if verdict in ("kept", "seeded"):
            try:
                return float(cols[pf_idx])
            except (ValueError, IndexError):
                return 0.0
    return 0.0


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Stage 04 autoresearch driver — keep/revert loop."
    )
    parser.add_argument(
        "--autoresearch-dir",
        default=str(Path(__file__).resolve().parent),
        help="Path to autoresearch/ directory (default: script's parent dir)",
    )
    parser.add_argument(
        "--repo-root",
        default=str(Path(__file__).resolve().parents[3]),
        help="Path to repository root (default: 3 parents up from script)",
    )
    args = parser.parse_args()
    run_loop(args.autoresearch_dir, args.repo_root)
