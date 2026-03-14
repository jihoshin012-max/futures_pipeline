# archetype: zone_touch
"""Stage 02 autoresearch driver — feature keep/revert loop with budget enforcement.

Usage:
    python driver.py [--archetype zone_touch] [--autoresearch-dir DIR] [--repo-root DIR]
                     [--n-experiments N]

The driver reads program.md every iteration (budget/metric/new_feature are re-read
each loop), runs evaluate_features.py as a subprocess, evaluates the keep/revert
decision based on spread and MWU p-value, logs results.tsv, and handles anomalies.

Key differences from Stage 04 driver:
- No propose_next_params (agent edits feature_engine.py, not driver)
- No trail step validation (Stage 04-specific)
- Runs evaluate_features.py subprocess instead of backtest_engine.py
- Copies feature_engine.py to/from current_best/ instead of exit_params.json
- Reads feature_evaluation.json (features_evaluated list) for results
- Stage column = '02-features' not '04-backtest'
- program.md adds NEW_FEATURE field
- Keep decision: spread > keep_rule AND mwu_p < 0.10 (threshold-based, not improvement-based)
- entry_time_violation checked per-feature (inside feature dict, NOT top-level)
"""

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

# ---------------------------------------------------------------------------
# results.tsv helpers (identical to Stage 04)
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
# Unique run_id generation (identical to Stage 04)
# ---------------------------------------------------------------------------

def _generate_run_id(archetype: str, timestamp: str, experiment_n: int) -> str:
    """Generate unique run_id per experiment using hash of archetype+timestamp+n."""
    raw = f"{archetype}:{timestamp}:{experiment_n}"
    return hashlib.sha1(raw.encode()).hexdigest()[:7]


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
# program.md parsing (adapted from Stage 04 — adds NEW_FEATURE field)
# ---------------------------------------------------------------------------

def parse_program_md(path) -> dict:
    """Parse machine-readable fields from program.md.

    Returns dict with keys: metric (str), keep_rule (float), budget (int),
    new_feature (str).
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
        elif line.startswith("NEW_FEATURE:"):
            result["new_feature"] = line.split(":", 1)[1].strip()

    missing = [k for k in ("metric", "keep_rule", "budget", "new_feature") if k not in result]
    if missing:
        raise ValueError(f"program.md missing required fields: {missing}")

    return result


# ---------------------------------------------------------------------------
# Audit log helper (adapted from Stage 04 — stage name changed)
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
        f"- stage: 02-features\n"
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
    archetype: str = "zone_touch",
    max_iterations: int = None,
) -> None:
    """Run the Stage 02 feature keep/revert autoresearch loop.

    Args:
        autoresearch_dir: Path to stages/02-features/autoresearch/
        repo_root: Path to repository root (for subprocess cwd and audit_log.md)
        archetype: Archetype name (default: zone_touch)
        max_iterations: Hard cap on iterations (for smoke testing). None = no cap.
    """
    autoresearch_dir = Path(autoresearch_dir)
    repo_root = Path(repo_root)

    # Resolve paths
    evaluate_features_path = autoresearch_dir / "evaluate_features.py"
    result_json_path = autoresearch_dir / "feature_evaluation.json"
    results_tsv_path = autoresearch_dir / "results.tsv"
    program_md_path = autoresearch_dir / "program.md"
    audit_log_path = repo_root / "audit" / "audit_log.md"
    current_best_path = autoresearch_dir / "current_best" / "feature_engine.py"

    # feature_engine.py lives in shared/archetypes/{archetype}/
    # repo_root resolution: try script-relative first, fall back to provided repo_root
    feature_engine_path = repo_root / "shared" / "archetypes" / archetype / "feature_engine.py"

    # Validate current_best/feature_engine.py exists (human must seed before first run)
    if not current_best_path.exists():
        print(
            f"ERROR: current_best/feature_engine.py not found at {current_best_path}.\n"
            f"Human must seed current_best/ with a baseline feature_engine.py before running."
        )
        return

    iteration = 0

    # Lockfile: coordinate with autocommit.sh to suppress polling during autoresearch
    lockfile = repo_root / ".autoresearch_running"
    lockfile.touch()
    try:
        while True:
            if max_iterations is not None and iteration >= max_iterations:
                break

            # Re-read program.md every iteration (budget/metric/new_feature may change)
            program = parse_program_md(program_md_path)
            keep_rule = program["keep_rule"]
            budget = program["budget"]
            new_feature = program["new_feature"]

            # Count prior tests BEFORE this experiment (count before, not after)
            n_prior_tests = _count_tsv_rows(results_tsv_path)

            if n_prior_tests >= budget:
                print(f"Budget exhausted ({n_prior_tests} >= {budget}). Stopping.")
                _git_commit(
                    repo_root,
                    [str(results_tsv_path.relative_to(repo_root))],
                    f"auto: stage-02 budget exhausted | {n_prior_tests} experiments"
                    f" | {archetype}",
                )
                break

            # Generate unique run_id per experiment
            timestamp = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
            run_id = _generate_run_id(archetype, timestamp, n_prior_tests)

            # Run evaluate_features.py as subprocess
            proc = subprocess.run(
                [
                    sys.executable,
                    str(evaluate_features_path),
                    "--archetype", archetype,
                    "--output", str(result_json_path),
                ],
                capture_output=True,
                text=True,
                cwd=str(repo_root),
            )

            if proc.returncode != 0:
                # Log anomaly and commit (do NOT abort loop)
                _log_experiment_anomaly(audit_log_path, run_id, proc.stderr)
                _git_commit(
                    repo_root,
                    [
                        str(audit_log_path.relative_to(repo_root)),
                        str(results_tsv_path.relative_to(repo_root)),
                    ],
                    f"auto: ANOMALY stage-02 experiment {n_prior_tests + 1}"
                    f" | {archetype} | see audit_log.md",
                )
                # Revert to prior best
                shutil.copy2(str(current_best_path), str(feature_engine_path))
                iteration += 1
                continue

            # Read feature_evaluation.json
            result_data = json.loads(result_json_path.read_text(encoding="utf-8"))
            features_evaluated = result_data.get("features_evaluated", [])

            # Find the feature matching new_feature from program.md
            feature_dict = None
            for fd in features_evaluated:
                if fd.get("name") == new_feature:
                    feature_dict = fd
                    break

            if feature_dict is None:
                # Feature not found in results — treat as anomaly (no keep)
                notes = f"feature_not_found:{new_feature}"
                verdict = "reverted"
                spread = 0.0
                mwu_p = 1.0
                n_p1a = 0
                n_p1b = 0
                shutil.copy2(str(current_best_path), str(feature_engine_path))
            else:
                spread = float(feature_dict.get("spread", 0.0))
                mwu_p = float(feature_dict.get("mwu_p", 1.0))
                n_p1a = int(feature_dict.get("n_p1a", 0))
                n_p1b = int(feature_dict.get("n_p1b", 0))

                # Check entry_time_violation PER-FEATURE (inside feature dict)
                # Do NOT look for top-level 'violation_count' — dispatcher drops top-level keys
                entry_time_violation = bool(feature_dict.get("entry_time_violation", False))

                if entry_time_violation:
                    verdict = "entry_time_violation"
                    notes = "entry_time_violation:blocked"
                    # Revert: restore feature_engine.py from current_best/
                    shutil.copy2(str(current_best_path), str(feature_engine_path))
                elif spread > keep_rule and mwu_p < 0.10:
                    verdict = "kept"
                    notes = ""
                    # Keep: copy feature_engine.py to current_best/
                    shutil.copy2(str(feature_engine_path), str(current_best_path))
                else:
                    verdict = "reverted"
                    notes = ""
                    # Revert: restore feature_engine.py from current_best/
                    shutil.copy2(str(current_best_path), str(feature_engine_path))

            # Event-driven git commit on kept experiments — capture hash for notes
            if verdict == "kept":
                git_hash = _git_commit(
                    repo_root,
                    [
                        str(current_best_path.relative_to(repo_root)),
                        str(results_tsv_path.relative_to(repo_root)),
                    ],
                    f"auto: kept experiment {n_prior_tests + 1} | spread={spread:.3f}"
                    f" | {archetype} | stage=02",
                )
                if git_hash:
                    notes = f"git:{git_hash}"

            # Append TSV row (all 24 columns)
            # pf_p1 carries spread value (reusing dashboard column for Stage 02 metric)
            # mwu_p column carries MWU p-value
            row = [
                run_id,          # run_id
                "02-features",   # stage
                timestamp,       # timestamp
                "",              # hypothesis_name
                archetype,       # archetype
                "",              # version
                new_feature,     # features (feature name being evaluated)
                spread,          # pf_p1 (carries spread for Stage 02)
                "",              # pf_p2
                n_p1a,           # trades_p1 (n_p1a touches)
                n_p1b,           # trades_p2 (n_p1b touches)
                mwu_p,           # mwu_p
                "",              # perm_p
                "",              # pctile
                n_prior_tests,   # n_prior_tests
                verdict,         # verdict
                "",              # sharpe_p1
                "",              # max_dd_ticks
                "",              # avg_winner_ticks
                "",              # dd_multiple
                "",              # win_rate
                "",              # regime_breakdown
                "",              # api_cost_usd
                notes,           # notes
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
        description="Stage 02 autoresearch driver — feature keep/revert loop."
    )
    parser.add_argument(
        "--archetype",
        default="zone_touch",
        help="Archetype name (default: zone_touch)",
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
    run_loop(
        args.autoresearch_dir,
        args.repo_root,
        archetype=args.archetype,
        max_iterations=args.n_experiments,
    )
