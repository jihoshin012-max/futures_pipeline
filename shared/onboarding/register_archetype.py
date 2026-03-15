#!/usr/bin/env python3
"""
shared/onboarding/register_archetype.py
Register a new strategy archetype in the pipeline.

Writes to:
  _config/period_config.md         — adds per-archetype period rows
  strategy_archetypes.md           — adds archetype entry with Periods field
  shared/archetypes/{name}/        — creates 4 required stub files
  shared/scoring_models/{name}_v1.json — creates scoring model stub

Does NOT commit — autocommit.sh and pre-commit hooks handle that.
Does NOT touch CONTEXT.md files — update those per context_review_protocol.md.
Run register_source.py separately for each new data source first.

Usage (from repo root):
  python shared/onboarding/register_archetype.py \\
    --name rotational \\
    --instrument NQ \\
    --p1-start 2025-09-21 --p1-end 2025-12-14 \\
    --p2-start 2025-12-15 --p2-end 2026-03-13 \\
    --data-sources "bar_data_250vol_rot, bar_data_250tick_rot" \\
    --adapter new \\
    --opt-surface "allocation_weights, rebalance_threshold, lookback_bars"
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
    p = argparse.ArgumentParser(description="Register a new strategy archetype")
    p.add_argument("--name", required=True, help="Archetype name, e.g. rotational")
    p.add_argument("--instrument", required=True, help="e.g. NQ, ES, GC")
    p.add_argument("--p1-start", required=True, help="P1 IS start date YYYY-MM-DD")
    p.add_argument("--p1-end",   required=True, help="P1 IS end date YYYY-MM-DD")
    p.add_argument("--p2-start", required=True, help="P2 OOS start date YYYY-MM-DD")
    p.add_argument("--p2-end",   required=True, help="P2 OOS end date YYYY-MM-DD")
    p.add_argument("--data-sources", required=True,
                   help="Comma-separated source_ids (must already be in data_registry.md)")
    p.add_argument("--adapter", default="BinnedScoringAdapter",
                   help="BinnedScoringAdapter | SklearnScoringAdapter | ONNXScoringAdapter | new")
    p.add_argument("--opt-surface",
                   default="stop_ticks, targets, trail_steps, time_cap_bars, score_threshold",
                   help="Comma-separated optimizable params")
    p.add_argument("--simulator", default="new",
                   help="m1_simulator | single_simulator | new")
    args = p.parse_args()

    root = repo_root()
    today = date.today().isoformat()
    name = args.name

    print(f"\nRegistering archetype: {name}")
    print(f"{'─' * 50}")

    # ── 1. period_config.md — add archetype rows ───────────────────────────
    period_cfg = root / "_config" / "period_config.md"
    content = period_cfg.read_text()

    if f"| P1        | {name}" in content:
        print(f"  ⚠  Period rows for '{name}' already exist in period_config.md — skipping.")
    else:
        new_rows = (
            f"| P1        | {name:<11} | IS   | {args.p1_start} | {args.p1_end} "
            f"| Calibration — used freely     |\n"
            f"| P2        | {name:<11} | OOS  | {args.p2_start} | {args.p2_end} "
            f"| Holdout — one-shot only       |"
        )
        insert_before = "\n## Rules (do not change)"
        if insert_before in content:
            content = content.replace(insert_before, f"\n{new_rows}{insert_before}")
            period_cfg.write_text(content)
            print(f"  ✓  Period rows added to _config/period_config.md")
            print(f"     P1: {args.p1_start} → {args.p1_end} (IS)")
            print(f"     P2: {args.p2_start} → {args.p2_end} (OOS)")
            print(f"     Note: pre-commit hook will auto-log PERIOD_CONFIG_CHANGED audit entry")
        else:
            print(f"  ⚠  Could not find insertion point in period_config.md — add manually.")

    # ── 2. Verify data sources registered ─────────────────────────────────
    registry = root / "_config" / "data_registry.md"
    reg_content = registry.read_text()
    sources = [s.strip() for s in args.data_sources.split(",")]
    missing = [s for s in sources if s and s not in reg_content]
    if missing:
        print(f"\n  ⚠  These source_ids are NOT in data_registry.md:")
        for s in missing:
            print(f"     - {s}")
        print(f"     Run register_source.py for each before proceeding.")
        print(f"     Stage 01 validation will fail without registered sources.")
    else:
        print(f"  ✓  All required data sources registered in data_registry.md")

    # ── 3. strategy_archetypes.md ──────────────────────────────────────────
    archetypes_path = (root / "stages" / "03-hypothesis" /
                       "references" / "strategy_archetypes.md")
    arch_content = archetypes_path.read_text()

    if f"## {name}" in arch_content:
        print(f"  ⚠  Archetype '{name}' already in strategy_archetypes.md — skipping.")
    else:
        sim_module = (f"shared/archetypes/{name}/{name}_simulator.py"
                      if args.simulator == "new"
                      else f"shared/archetypes/zone_touch/{args.simulator}.py")
        entry = textwrap.dedent(f"""
            ## {name}
            - Description: [FILL IN — what does this strategy do?]
            - Instrument: {args.instrument}
            - Periods: P1, P2
            - Required data: {args.data_sources}
            - Simulator module: `{sim_module}`
            - Scoring model: `shared/scoring_models/{name}_v1.json`
            - Scoring adapter: {args.adapter}
            - feature_evaluator: `shared/archetypes/{name}/feature_evaluator.py`
            - feature_engine: `shared/archetypes/{name}/feature_engine.py`
            - Optimization surface: {args.opt_surface}
            - Structural reference: `stages/06-deployment/references/{name}_reference.cpp`
            - Current status: hypothesis stage
            - Date registered: {today}
        """)
        with open(archetypes_path, "a") as f:
            f.write(entry)
        print(f"  ✓  Entry added to strategy_archetypes.md")
        print(f"     ⚠  Fill in the Description field before Stage 03 runs")

    # ── 4. shared/archetypes/{name}/ skeleton ─────────────────────────────
    arch_dir = root / "shared" / "archetypes" / name
    arch_dir.mkdir(parents=True, exist_ok=True)

    files_created = []

    # feature_engine.py
    fe = arch_dir / "feature_engine.py"
    if not fe.exists():
        fe.write_text(textwrap.dedent(f"""\
            # archetype: {name}
            # feature_engine.py — {name}
            # Stage 02 autoresearch agent edits this file only. One feature per experiment.
            # Entry-time computability is a HARD RULE — no look-ahead allowed.
            # Register each approved feature in shared/feature_definitions.md after Stage 02 approves it.
            # last_reviewed: {today}
            import pandas as pd


            def compute_features(bar_df: pd.DataFrame, touch_row: dict) -> dict:
                \"\"\"
                Compute features for a single signal at entry time.
                bar_df is truncated to entry bar — future bars are not visible.
                Returns: dict of {{feature_name: float_value}}
                \"\"\"
                features = {{}}
                # Stage 02 autoresearch will propose features here.
                # Do not add features manually — let Stage 02 discover them.
                return features
        """))
        files_created.append("feature_engine.py")

    # feature_evaluator.py
    feval = arch_dir / "feature_evaluator.py"
    if not feval.exists():
        feval.write_text(textwrap.dedent(f"""\
            # archetype: {name}
            # feature_evaluator.py — {name}
            # Fixed harness — Stage 02 autoresearch NEVER edits this file.
            # Loads data from data_manifest.json, calls feature_engine.py,
            # computes best-bin vs worst-bin predictive spread per feature.
            # Standard interface: evaluate_features.py dispatcher calls evaluate().
            # last_reviewed: {today}
            import json
            from pathlib import Path
            import pandas as pd


            def evaluate() -> dict:
                \"\"\"
                Standard interface — called by evaluate_features.py dispatcher.
                Returns: {{
                    "features": [{{"name": str, "spread": float, "mwu_p": float, "kept": bool}}],
                    "n_touches": int
                }}
                \"\"\"
                manifest_path = Path("stages/01-data/output/data_manifest.json")
                if not manifest_path.exists():
                    raise FileNotFoundError(
                        "data_manifest.json not found. Run Stage 01 validation first."
                    )
                with open(manifest_path) as f:
                    manifest = json.load(f)

                # Load P1a data for this archetype from manifest
                # archetype_periods = manifest["archetypes"]["{name}"]["periods"]
                # p1a = archetype_periods["P1"]["p1a_start"], archetype_periods["P1"]["p1a_end"]
                # Load required sources:
                # {args.data_sources}

                raise NotImplementedError(
                    "Implement evaluate() for {name}. "
                    "Load sources from manifest, call compute_features(), "
                    "compute tercile spread and MWU p-value."
                )
        """))
        files_created.append("feature_evaluator.py")

    # simulation_rules.md
    sim_rules = arch_dir / "simulation_rules.md"
    if not sim_rules.exists():
        sim_rules.write_text(textwrap.dedent(f"""\
            # Simulation rules — {name}
            last_reviewed: {today}
            # HUMAN ACTION REQUIRED: Transcribe from actual simulator source.
            # Do not invent rules — read the source code and document what it does.
            # Stage 04 agent reads this to understand engine mechanics.

            ## Entry mechanics
            Signal source: [describe what triggers a signal row]
            Entry timing: [bar offset — which bar index is entry bar]
            Direction: [long / short / both]

            ## Cost model
            cost_ticks: [value from _config/instruments.md — Rule 5]
            Instrument: {args.instrument}

            ## Exit mechanics
            Stop: [stop_ticks — how placed]
            Targets: [leg structure or single target]
            BE trigger: [trail_steps[0] if applicable]
            Time cap: [time_cap_bars — exits on bar N if no other exit]

            ## What the engine does NOT enforce
            - Scoring threshold gate: enforced by backtest_engine.py
            - Feature entry-time rule: enforced by feature_rules.md
            - Iteration budget: enforced by driver loop

            ## Notes
            [Any special mechanics — gap handling, session filters, etc.]
        """))
        files_created.append("simulation_rules.md")

    # exit_templates.md
    exit_tpl = arch_dir / "exit_templates.md"
    if not exit_tpl.exists():
        exit_tpl.write_text(textwrap.dedent(f"""\
            # Exit templates — {name}
            last_reviewed: {today}
            # Stage 04 agent reads this before proposing exit param changes.
            # Templates are illustrative starting points — agent explores within
            # the constraints defined in simulation_rules.md.

            ## Template A — conservative
            [fill in conservative param values]

            ## Template B — aggressive
            [fill in aggressive param values]

            ## Template C — balanced (seed for Stage 04 autoresearch)
            [fill in balanced starting params — this is the autoresearch seed]

            ## Constraints (from simulation_rules.md)
            - [list hard constraints the agent must not violate]
        """))
        files_created.append("exit_templates.md")

    if files_created:
        print(f"  ✓  shared/archetypes/{name}/ created with: {', '.join(files_created)}")
    else:
        print(f"  ⚠  shared/archetypes/{name}/ already exists — skeleton skipped")

    # ── 5. Scoring model stub ──────────────────────────────────────────────
    models_dir = root / "shared" / "scoring_models"
    model_path = models_dir / f"{name}_v1.json"
    if not model_path.exists():
        model_path.write_text(textwrap.dedent(f"""\
            {{
              "_note": "Populate after P1 calibration — do not fill in manually",
              "_created": "{today}",
              "archetype": "{name}",
              "version": "v1",
              "bin_edges": {{}},
              "weights": {{}}
            }}
        """))
        print(f"  ✓  Scoring model stub: shared/scoring_models/{name}_v1.json")

    # ── 6. scaffold_adapter if new adapter ────────────────────────────────
    registered_adapters = ["BinnedScoringAdapter", "SklearnScoringAdapter", "ONNXScoringAdapter"]
    if args.adapter not in registered_adapters:
        scaffold = root / "shared" / "scoring_models" / "scaffold_adapter.py"
        if scaffold.exists():
            import subprocess
            subprocess.run([sys.executable, str(scaffold)], cwd=root)
            print(f"  ✓  scaffold_adapter.py run — adapter stub generated")
        else:
            print(f"  ⚠  New adapter requested but scaffold_adapter.py not found.")
            print(f"     Run it manually: python shared/scoring_models/scaffold_adapter.py")

    # ── Summary ────────────────────────────────────────────────────────────
    print(f"\n{'─' * 50}")
    print(f"  Done. Next steps:")
    print(f"")
    print(f"  1. Fill in Description in strategy_archetypes.md for '{name}'")
    print(f"")
    print(f"  2. Complete simulation_rules.md from actual simulator source:")
    print(f"     shared/archetypes/{name}/simulation_rules.md")
    print(f"")
    print(f"  3. If new data sources were listed above as missing,")
    print(f"     run register_source.py for each, then drop data files,")
    print(f"     then run Stage 01 validation.")
    print(f"")
    print(f"  4. Run Stage 01 validation once data is in place:")
    print(f"     python stages/01-data/validate.py")
    print(f"")
    print(f"  5. Update CONTEXT.md files per _config/context_review_protocol.md")
    print(f"     (NOT done by this script — agent-facing files need human review)")
    print(f"")
    print(f"  6. Complete new archetype intake checklist (functional spec)")
    print(f"     before Stage 03 autoresearch can run for this archetype.")
    print(f"")
    print(f"  autocommit.sh will commit these changes automatically.")
    print(f"  pre-commit hook will log PERIOD_CONFIG_CHANGED audit entry.")


if __name__ == "__main__":
    main()
