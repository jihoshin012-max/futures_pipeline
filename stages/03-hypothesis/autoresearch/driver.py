# archetype: zone_touch
"""Stage 03 autoresearch driver — hypothesis keep/revert loop with P1b replication enforcement.

Usage:
    python driver.py [--autoresearch-dir DIR] [--repo-root DIR] [--n-experiments N]

The driver reads program.md every iteration, proposes a random perturbation of CANDIDATE
fields, runs hypothesis_generator.py (which runs backtest_engine.py twice for P1 and P1b),
evaluates the keep/revert decision with P1b replication gating, logs results.tsv, and
handles anomalies.

Key differences from Stage 04 driver:
- Calls hypothesis_generator.py subprocess (not backtest_engine.py directly)
- hypothesis_generator.py returns both result.json (P1) and result_p1b.json (P1b)
- Replication gating: hard_block reverts; flag_and_review keeps with flag
- TSV has 25 columns (adds replication_pass as column 25)
- current_best file: hypothesis_config.json (not exit_params.json)
- stage column: '03-hypothesis' (not '04-backtest')
- program.md: 3 fields only (metric, keep_rule, budget) — no NEW_FEATURE field
"""

import argparse
import copy
import hashlib
import json
import random
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MIN_TRADES = 30  # Minimum P1 trades required to accept a "kept" result
REPLICATION_PF_THRESHOLD = 1.0   # P1b PF must be >= this to pass replication
REPLICATION_MIN_TRADES = 10       # P1b n_trades minimum to count as valid replication

# CANDIDATE fields that driver varies; all others are FIXED
_CANDIDATE_MODES = ["M1"]  # Only M1 mode params are varied

# ---------------------------------------------------------------------------
# TSV header (25 columns — Stage 03 adds replication_pass after notes)
# ---------------------------------------------------------------------------

TSV_HEADER = (
    "run_id\tstage\ttimestamp\thypothesis_name\tarchetype\tversion\tfeatures"
    "\tpf_p1\tpf_p2\ttrades_p1\ttrades_p2\tmwu_p\tperm_p\tpctile\tn_prior_tests"
    "\tverdict\tsharpe_p1\tmax_dd_ticks\tavg_winner_ticks\tdd_multiple\twin_rate"
    "\tregime_breakdown\tapi_cost_usd\tnotes\treplication_pass"
)


# ---------------------------------------------------------------------------
# Unique run_id generation (identical to Stage 04)
# ---------------------------------------------------------------------------

def _generate_run_id(archetype: str, timestamp: str, experiment_n: int) -> str:
    """Generate unique run_id per experiment using hash of archetype+timestamp+n."""
    raw = f"{archetype}:{timestamp}:{experiment_n}"
    return hashlib.sha1(raw.encode()).hexdigest()[:7]


# ---------------------------------------------------------------------------
# Hypothesis name helper
# ---------------------------------------------------------------------------

def _read_hypothesis_name(autoresearch_dir: Path) -> str:
    """Read hypothesis name from promoted_hypothesis.json, fallback to empty string."""
    hyp_path = autoresearch_dir / "promoted_hypothesis.json"
    if hyp_path.exists():
        data = json.loads(hyp_path.read_text(encoding="utf-8"))
        return data.get("name", "")
    return ""


# ---------------------------------------------------------------------------
# Non-fatal git commit (identical to Stage 04)
# ---------------------------------------------------------------------------

def _git_commit(repo_root: Path, files: list, message: str) -> str:
    """Stage files and commit with message. Returns short hash or empty string. Non-fatal."""
    try:
        subprocess.run(["git", "add"] + files, cwd=str(repo_root), capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", message], cwd=str(repo_root), capture_output=True
        )
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=str(repo_root), capture_output=True, text=True,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass  # Git failures must not abort the experiment loop
    return ""


# ---------------------------------------------------------------------------
# program.md parsing (3 fields: metric, keep_rule, budget — no NEW_FEATURE)
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
# Replication gate reader
# ---------------------------------------------------------------------------

def read_replication_gate(repo_root: Path) -> str:
    """Read replication_gate from _config/period_config.md.

    Returns 'hard_block' or 'flag_and_review'. Default: 'flag_and_review'.
    """
    config_path = repo_root / "_config" / "period_config.md"
    try:
        content = config_path.read_text(encoding="utf-8")
        match = re.search(r"^replication_gate:\s*(\S+)", content, re.MULTILINE)
        if match:
            return match.group(1).strip()
    except Exception:
        pass
    return "flag_and_review"


# ---------------------------------------------------------------------------
# Trail step validation (identical to Stage 04)
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
# Parameter proposal (identical to Stage 04)
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

def _count_tsv_rows(tsv_path: Path) -> int:
    """Count data rows (excluding header) in results.tsv."""
    if not tsv_path.exists():
        return 0
    lines = tsv_path.read_text(encoding="utf-8").splitlines()
    return sum(1 for line in lines[1:] if line.strip())


def _append_tsv_row(tsv_path: Path, row_values: list) -> None:
    """Append one row to results.tsv as tab-delimited. Creates file with header if missing."""
    if not tsv_path.exists():
        tsv_path.write_text(TSV_HEADER + "\n", encoding="utf-8")
    with tsv_path.open("a", encoding="utf-8", newline="") as f:
        f.write("\t".join(str(v) for v in row_values) + "\n")


# ---------------------------------------------------------------------------
# Baseline metric reader
# ---------------------------------------------------------------------------

def _read_baseline_metric(results_tsv_path: Path) -> float:
    """Read the pf_p1 from the most recent 'kept' or 'seeded' row in results.tsv.

    Returns 0.0 if no such row found (safe default — any positive result will be kept).
    """
    if not results_tsv_path.exists():
        return 0.0
    lines = results_tsv_path.read_text(encoding="utf-8").splitlines()
    if len(lines) < 2:
        return 0.0
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
        if verdict in ("kept", "seeded", "kept_weak_replication"):
            try:
                return float(cols[pf_idx])
            except (ValueError, IndexError):
                return 0.0
    return 0.0


# ---------------------------------------------------------------------------
# Audit log helper
# ---------------------------------------------------------------------------

def _log_experiment_anomaly(
    audit_log_path: Path, run_id: str, stderr: str
) -> None:
    """Append EXPERIMENT_ANOMALY entry to audit_log.md. Does NOT git commit."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    stderr_lines = stderr.strip().splitlines()
    stderr_tail = "\n".join(stderr_lines[-20:]) if stderr_lines else "(none)"
    entry = (
        f"\n## {timestamp} | EXPERIMENT_ANOMALY\n"
        f"- stage: 03-hypothesis\n"
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


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

def run_loop(
    autoresearch_dir,
    repo_root,
    max_iterations: int = None,
) -> None:
    """Run the Stage 03 hypothesis keep/revert autoresearch loop.

    Args:
        autoresearch_dir: Path to stages/03-hypothesis/autoresearch/
        repo_root: Path to repository root (for generator cwd and audit_log.md)
        max_iterations: Hard cap on iterations (for testing). None = no cap.
    """
    autoresearch_dir = Path(autoresearch_dir).resolve()
    repo_root = Path(repo_root).resolve()

    generator_path = autoresearch_dir / "hypothesis_generator.py"
    hypothesis_config_path = autoresearch_dir / "hypothesis_config.json"
    current_best_path = autoresearch_dir / "current_best" / "hypothesis_config.json"
    result_json_path = autoresearch_dir / "result.json"
    result_p1b_json_path = autoresearch_dir / "result_p1b.json"
    results_tsv_path = autoresearch_dir / "results.tsv"
    program_md_path = autoresearch_dir / "program.md"
    audit_log_path = repo_root / "audit" / "audit_log.md"

    # Load current best config and establish baseline metric
    current_best_config = json.loads(current_best_path.read_text(encoding="utf-8"))
    current_best_metric = _read_baseline_metric(results_tsv_path)

    # Read hypothesis name once at loop start
    hypothesis_name_base = _read_hypothesis_name(autoresearch_dir)

    # Read replication gate from period_config.md
    replication_gate = read_replication_gate(repo_root)

    iteration = 0

    # Lockfile: coordinate with autocommit.sh to suppress polling during autoresearch
    lockfile = repo_root / ".autoresearch_running"
    lockfile.touch()
    try:
        while True:
            if max_iterations is not None and iteration >= max_iterations:
                break

            # Re-read program.md every iteration
            program = parse_program_md(program_md_path)
            metric_field = program["metric"]
            keep_rule = program["keep_rule"]
            budget = program["budget"]

            # Count prior tests BEFORE this experiment
            n_prior_tests = _count_tsv_rows(results_tsv_path)

            if n_prior_tests >= budget:
                print(f"Budget exhausted ({n_prior_tests} >= {budget}). Stopping.")
                archetype_name = current_best_config.get("archetype", {}).get("name", "")
                _git_commit(
                    repo_root,
                    [str(results_tsv_path.relative_to(repo_root))],
                    f"auto: stage-03 budget exhausted | {n_prior_tests} experiments"
                    f" | best pf={current_best_metric:.3f} | {archetype_name}",
                )
                break

            # Propose next params
            proposed_config = propose_next_params(current_best_config, results_tsv_path)

            # Write hypothesis_config.json (agent-editable file)
            hypothesis_config_path.write_text(
                json.dumps(proposed_config, indent=2), encoding="utf-8"
            )

            # Generate unique run_id
            timestamp = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
            archetype = current_best_config.get("archetype", {}).get("name", "")
            run_id = _generate_run_id(archetype, timestamp, n_prior_tests)

            # Run hypothesis_generator.py via subprocess
            # hypothesis_generator.py calls backtest_engine.py twice (P1 + P1b)
            proc = subprocess.run(
                [
                    sys.executable,
                    str(generator_path),
                    "--config", str(hypothesis_config_path),
                    "--output", str(result_json_path),
                    "--output-p1b", str(result_p1b_json_path),
                ],
                capture_output=True,
                text=True,
                cwd=str(repo_root),
            )

            if proc.returncode != 0:
                # Log anomaly and continue loop (do NOT abort)
                _log_experiment_anomaly(audit_log_path, run_id, proc.stderr)
                _git_commit(
                    repo_root,
                    [
                        str(audit_log_path.relative_to(repo_root)),
                        str(results_tsv_path.relative_to(repo_root)),
                    ],
                    f"auto: ANOMALY stage-03 experiment {n_prior_tests + 1}"
                    f" | {archetype} | see audit_log.md",
                )
                # Revert to prior best
                shutil.copy2(current_best_path, hypothesis_config_path)
                iteration += 1
                continue

            # Read P1 result
            result_data = json.loads(result_json_path.read_text(encoding="utf-8"))
            metric_value = float(result_data.get(metric_field, 0.0))
            n_trades = int(result_data.get("n_trades", 0))
            win_rate = float(result_data.get("win_rate", 0.0))
            max_dd = float(result_data.get("max_drawdown_ticks", 0.0))

            # Keep/revert decision — Step 1: P1 check
            p1_passes = (metric_value > current_best_metric + keep_rule) and (n_trades >= MIN_TRADES)

            if not p1_passes:
                # P1 failed — revert immediately, skip P1b check
                verdict = "reverted"
                replication_pass = ""
                notes = ""
                shutil.copy2(current_best_path, hypothesis_config_path)
            else:
                # P1 passed — read P1b result and apply replication gate
                result_p1b_data = json.loads(result_p1b_json_path.read_text(encoding="utf-8"))
                pf_p1b = float(result_p1b_data.get("pf", 0.0))
                n_trades_p1b = int(result_p1b_data.get("n_trades", 0))

                replication_pass_bool = (
                    pf_p1b >= REPLICATION_PF_THRESHOLD
                    and n_trades_p1b >= REPLICATION_MIN_TRADES
                )
                replication_pass = str(replication_pass_bool)

                if replication_pass_bool:
                    # P1b passed — keep
                    verdict = "kept"
                    shutil.copy2(hypothesis_config_path, current_best_path)
                    current_best_metric = metric_value
                    current_best_config = proposed_config
                elif replication_gate == "hard_block":
                    # P1b failed, hard_block — revert
                    verdict = "p1b_replication_fail"
                    shutil.copy2(current_best_path, hypothesis_config_path)
                else:
                    # P1b failed, flag_and_review — keep but flag
                    verdict = "kept_weak_replication"
                    shutil.copy2(hypothesis_config_path, current_best_path)
                    current_best_metric = metric_value
                    current_best_config = proposed_config

                notes = f"replication_pass:{replication_pass_bool}|pf_p1b:{pf_p1b:.3f}"

            # Populate hypothesis_name
            hypothesis_name = hypothesis_name_base if hypothesis_name_base else archetype

            # Event-driven git commit on kept experiments
            if verdict in ("kept", "kept_weak_replication"):
                git_hash = _git_commit(
                    repo_root,
                    [
                        str(current_best_path.relative_to(repo_root)),
                        str(results_tsv_path.relative_to(repo_root)),
                    ],
                    f"auto: {verdict} experiment {n_prior_tests + 1} | pf={metric_value:.3f}"
                    f" | {archetype} | stage=03",
                )
                if git_hash:
                    if notes:
                        notes = f"{notes}|git:{git_hash}"
                    else:
                        notes = f"git:{git_hash}"

            # Append TSV row (25 columns)
            version = current_best_config.get("version", "")
            row = [
                run_id,            # run_id
                "03-hypothesis",   # stage
                timestamp,         # timestamp
                hypothesis_name,   # hypothesis_name
                archetype,         # archetype
                version,           # version
                "",                # features
                metric_value,      # pf_p1
                "",                # pf_p2
                n_trades,          # trades_p1
                "",                # trades_p2
                "",                # mwu_p
                "",                # perm_p
                "",                # pctile
                n_prior_tests,     # n_prior_tests
                verdict,           # verdict
                "",                # sharpe_p1
                max_dd,            # max_dd_ticks
                "",                # avg_winner_ticks
                "",                # dd_multiple
                win_rate,          # win_rate
                "",                # regime_breakdown
                "",                # api_cost_usd
                notes,             # notes
                replication_pass,  # replication_pass (column 25)
            ]
            _append_tsv_row(results_tsv_path, row)

            iteration += 1
    finally:
        lockfile.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Stage 03 autoresearch driver — hypothesis keep/revert loop."
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
    parser.add_argument(
        "--n-experiments",
        type=int,
        default=None,
        help="Hard cap on experiments for smoke testing (default: no cap)",
    )
    args = parser.parse_args()
    run_loop(args.autoresearch_dir, args.repo_root, max_iterations=args.n_experiments)
