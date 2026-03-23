#!/usr/bin/env python3
"""
Pipeline reconciliation — pre-cleanup verification tool.

Scans the working tree for untracked/modified files, validates paths
against pipeline conventions, detects stale uncommitted work, and
reports a summary with actionable groupings.

Usage:
    python scripts/reconcile.py              # summary
    python scripts/reconcile.py --detail     # per-file listing
    python scripts/reconcile.py --json       # machine-readable output

Ignore patterns: .reconcile_ignore (gitignore format, repo root).
"""
import subprocess, sys, os, json, fnmatch
from datetime import datetime, timedelta
from pathlib import Path

ROOT = subprocess.check_output(
    ['git', 'rev-parse', '--show-toplevel'], text=True).strip()
os.chdir(ROOT)

DETAIL = '--detail' in sys.argv or '-d' in sys.argv
JSON_OUT = '--json' in sys.argv

# =========================================================================
#  Load .reconcile_ignore
# =========================================================================

def load_ignore_patterns():
    """Load ignore patterns from .reconcile_ignore (gitignore format)."""
    patterns = []
    ignore_path = os.path.join(ROOT, '.reconcile_ignore')
    if not os.path.exists(ignore_path):
        return patterns
    with open(ignore_path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            patterns.append(line)
    return patterns

def is_ignored(filepath, patterns):
    """Check if filepath matches any ignore pattern."""
    for pat in patterns:
        if fnmatch.fnmatch(filepath, pat):
            return True
        if fnmatch.fnmatch(os.path.basename(filepath), pat):
            return True
        # Support directory patterns like stages/04-backtest/p2_holdout/
        if pat.endswith('/') and filepath.startswith(pat[:-1]):
            return True
    return False

IGNORE_PATS = load_ignore_patterns()

# =========================================================================
#  Git queries
# =========================================================================

def git_lines(cmd):
    """Run git command, return non-empty output lines."""
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=ROOT)
    return [l for l in result.stdout.strip().split('\n') if l]

def get_untracked():
    return git_lines(['git', 'ls-files', '--others', '--exclude-standard'])

def get_modified():
    return git_lines(['git', 'diff', '--name-only'])

def get_staged():
    return git_lines(['git', 'diff', '--cached', '--name-only'])

def get_last_commit_date(filepath):
    """Get the date of the last commit touching this file's directory."""
    dirpath = os.path.dirname(filepath) or '.'
    lines = git_lines(['git', 'log', '-1', '--format=%aI', '--', dirpath])
    if lines:
        try:
            return datetime.fromisoformat(lines[0].replace('Z', '+00:00'))
        except (ValueError, IndexError):
            pass
    return None

# =========================================================================
#  Path convention rules
# =========================================================================

# Known archetype directories
ARCHETYPE_DIRS = {
    'zone_touch': 'shared/archetypes/zone_touch',
    'rotational': 'shared/archetypes/rotational',
}

# Expected file locations by extension/type within zone_touch backtest
ZT_BACKTEST = 'stages/04-backtest/zone_touch'
ZT_OUTPUT = f'{ZT_BACKTEST}/output'
ZT_DOCS = 'shared/archetypes/zone_touch/docs'
ZT_ACSIL = 'shared/archetypes/zone_touch/acsil'

def classify_file(filepath):
    """Classify a file by its pipeline role. Returns (role, expected_dir, issue)."""
    name = os.path.basename(filepath)
    ext = os.path.splitext(name)[1].lower()
    dirpath = os.path.dirname(filepath)

    # Zone touch backtest scripts
    if filepath.startswith(ZT_BACKTEST) and ext == '.py':
        if dirpath == ZT_OUTPUT:
            # Scripts in output/ — should be in root
            return ('script', ZT_BACKTEST, 'MISPLACED: script in output/, expected in stage root')
        return ('script', ZT_BACKTEST, None)

    # Zone touch output files
    if filepath.startswith(ZT_OUTPUT):
        if ext == '.csv':
            return ('data', ZT_OUTPUT, None)
        if ext == '.md':
            return ('report', ZT_OUTPUT, None)
        if ext in ('.py', '.png', '.json'):
            return ('artifact', ZT_OUTPUT, None)
        return ('artifact', ZT_OUTPUT, None)

    # Zone touch docs/prompts
    if filepath.startswith(ZT_DOCS):
        return ('doc', ZT_DOCS, None)

    # ACSIL files
    if filepath.startswith(ZT_ACSIL):
        return ('acsil', ZT_ACSIL, None)

    # Top-level docs/
    if filepath.startswith('docs/'):
        return ('doc', 'docs', None)

    # Config
    if filepath.startswith('_config/'):
        return ('config', '_config', None)

    return ('other', dirpath, None)

def group_by_origin(files):
    """Group files by their likely origin (which analysis phase produced them)."""
    groups = {}
    for f in files:
        # Infer origin from directory + naming
        if 'throughput' in f.lower() or 'twoleg' in f.lower():
            origin = 'throughput_analysis'
        elif 'exit_investigation' in f.lower() or 'exit_stress' in f.lower():
            origin = 'exit_investigation'
        elif 'exit_sweep' in f.lower():
            origin = 'exit_sweep'
        elif 'equity_curve' in f.lower():
            origin = 'equity_comparison'
        elif 'zr_' in f.lower() or 'zone_relative' in f.lower():
            origin = 'zr_validation'
        elif f.startswith('stages/04-backtest/p2_holdout/'):
            origin = 'holdout_guard'
        elif f.startswith(ZT_ACSIL):
            origin = 'acsil_build'
        elif f.startswith(ZT_DOCS):
            origin = 'build_spec'
        elif f.startswith('docs/'):
            origin = 'pipeline_docs'
        else:
            origin = os.path.dirname(f) or 'root'
        groups.setdefault(origin, []).append(f)
    return groups

# =========================================================================
#  Staleness detection
# =========================================================================

def check_staleness(modified_files):
    """Flag modified files where the containing directory hasn't been
    committed to in over 24 hours (suggests forgotten work)."""
    stale = []
    now = datetime.now().astimezone()
    for f in modified_files:
        last = get_last_commit_date(f)
        if last and (now - last) > timedelta(hours=24):
            age_days = (now - last).days
            stale.append((f, age_days))
    return stale

# =========================================================================
#  Main
# =========================================================================

def main():
    untracked_raw = get_untracked()
    modified_raw = get_modified()
    staged_raw = get_staged()

    # Filter ignored files
    untracked = [f for f in untracked_raw if not is_ignored(f, IGNORE_PATS)]
    ignored = [f for f in untracked_raw if is_ignored(f, IGNORE_PATS)]
    modified = modified_raw
    staged = staged_raw

    # Classify and check paths
    misplaced = []
    for f in untracked + modified:
        role, expected, issue = classify_file(f)
        if issue:
            misplaced.append((f, issue))

    # Group untracked by origin
    ut_groups = group_by_origin(untracked) if untracked else {}

    # Staleness check
    stale = check_staleness(modified) if modified else []

    # ---- Output ----

    if JSON_OUT:
        result = {
            'untracked': untracked,
            'ignored': ignored,
            'modified': modified,
            'staged': staged,
            'misplaced': misplaced,
            'stale': [(f, d) for f, d in stale],
            'groups': ut_groups,
            'status': 'CLEAN' if not untracked and not modified and not staged else 'NEEDS_CLEANUP',
        }
        print(json.dumps(result, indent=2))
        return 0 if result['status'] == 'CLEAN' else 1

    # Human-readable output
    print("=" * 60)
    print("  Pipeline Reconciliation")
    print("=" * 60)
    print()

    # Untracked
    print(f"Untracked files: {len(untracked)}", end='')
    if ignored:
        print(f"  ({len(ignored)} ignored via .reconcile_ignore)", end='')
    print()

    if untracked:
        for origin, files in sorted(ut_groups.items()):
            print(f"  [{origin}] {len(files)} file(s)")
            if DETAIL:
                for f in sorted(files):
                    print(f"    {f}")
        print()

    # Modified
    print(f"Modified files: {len(modified)}")
    if modified and DETAIL:
        for f in sorted(modified):
            print(f"    {f}")
    if stale:
        for f, age in stale:
            print(f"  [STALE {age}d] {f}")
    if modified:
        print()

    # Staged
    if staged:
        print(f"Staged (not yet committed): {len(staged)}")
        if DETAIL:
            for f in sorted(staged):
                print(f"    {f}")
        print()

    # Misplaced
    if misplaced:
        print(f"Path issues: {len(misplaced)}")
        for f, issue in misplaced:
            print(f"  {issue}")
            print(f"    {f}")
        print()

    # Ignored detail
    if ignored and DETAIL:
        print(f"Ignored files ({len(ignored)}):")
        for f in sorted(ignored):
            print(f"    {f}")
        print()

    # Status
    clean = not untracked and not modified and not staged
    status = "CLEAN" if clean else "NEEDS CLEANUP"
    print(f"Status: {status}")

    if not clean and not DETAIL:
        print("  Run with --detail for per-file listing")

    return 0 if clean else 1


if __name__ == '__main__':
    sys.exit(main())
