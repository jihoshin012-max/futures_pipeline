---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: milestone
status: planning
stopped_at: Completed 07-stage-03-autoresearch plan 03 (assess.py feedback loop wiring)
last_updated: "2026-03-14T21:22:58.221Z"
last_activity: 2026-03-13 — Roadmap created; all 7 phases derived from requirements and build order constraints
progress:
  total_phases: 9
  completed_phases: 8
  total_plans: 26
  completed_plans: 25
  percent: 17
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-03-13)

**Core value:** Every deployed strategy traces back to a statistically validated, internally replicated hypothesis with frozen parameters — no unaudited shortcuts from idea to live trading.
**Current focus:** Phase 1 — Scaffold

## Current Position

Phase: 1 of 7 (Scaffold)
Plan: 0 of TBD in current phase
Status: Ready to plan
Last activity: 2026-03-13 — Roadmap created; all 7 phases derived from requirements and build order constraints

Progress: [██░░░░░░░░] 17%

## Performance Metrics

**Velocity:**
- Total plans completed: 0
- Average duration: -
- Total execution time: 0 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| - | - | - | - |

**Recent Trend:**
- Last 5 plans: none yet
- Trend: -

*Updated after each plan completion*
| Phase 01-scaffold P01 | 15 | 1 tasks | 43 files |
| Phase 01-scaffold P01 | 30 | 2 tasks | 47 files |
| Phase 01-scaffold P02 | 3 | 2 tasks | 9 files |
| Phase 01-scaffold P03 | 8 | 2 tasks | 5 files |
| Phase 01-scaffold P05 | 2 | 2 tasks | 8 files |
| Phase 01-scaffold P04 | 10 | 2 tasks | 8 files |
| Phase 01-scaffold P06 | 1 | 2 tasks | 5 files |
| Phase 01.1-scoring-adapter-scaffold-generator P01 | 1 | 2 tasks | 2 files |
| Phase 02-hmm-regime-fitter P01 | 4 | 2 tasks | 4 files |
| Phase 02-hmm-regime-fitter P02 | 5 | 2 tasks | 3 files |
| Phase 01.2-bar-type-registry-and-subfolder-structure P01 | 2 | 2 tasks | 7 files |
| Phase 03-git-infrastructure P01 | 13 | 2 tasks | 4 files |
| Phase 03-git-infrastructure P02 | 5 | 2 tasks | 0 files |
| Phase 04-backtest-engine P01 | 8 | 2 tasks | 4 files |
| Phase 04-backtest-engine P02 | 3 | 2 tasks | 5 files |
| Phase 04-backtest-engine P03 | 16 | 2 tasks | 4 files |
| Phase 04-backtest-engine P04 | 30 | 2 tasks | 4 files |
| Phase 05-stage-04-autoresearch P01 | 10 | 2 tasks | 5 files |
| Phase 05-stage-04-autoresearch P02 | 8 | 2 tasks | 4 files |
| Phase 05-stage-04-autoresearch P03 | 45 | 2 tasks | 2 files |
| Phase 05-stage-04-autoresearch P04 | 25 | 2 tasks | 3 files |
| Phase 06-stage-02-autoresearch P02 | 10 | 1 tasks | 2 files |
| Phase 06-stage-02-autoresearch P01 | 9 | 2 tasks | 4 files |
| Phase 06-stage-02-autoresearch P03 | 45 | 2 tasks | 4 files |
| Phase 07-stage-03-autoresearch P01 | 10 | 2 tasks | 7 files |
| Phase 07-stage-03-autoresearch P03 | 11 | 1 tasks | 2 files |

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.
Recent decisions affecting current work:

- [Roadmap]: Phase 2 (HMM) and Phase 3 (Git) both depend only on Phase 1 — they can be planned in parallel but Phase 4 (Engine) requires Phase 3 complete first
- [Roadmap]: Phase 1 includes PREREQ (repo fetches + data migration) as precondition — do not begin SCAF work until PREREQ-01 through PREREQ-04 are verified
- [Phase 01-scaffold]: ICM CONTEXT.md files stay under 80 lines, routing-only; matches functional spec intent for stage contracts
- [Phase 01-scaffold]: autoresearch keep/revert uses git reset for discards; phases 2-4 driver scripts must mirror this pattern
- [Phase 01-scaffold]: zone_touch used as archetype folder name per architecture doc convention
- [Phase 01-scaffold]: Bar data format confirmed: Date/Time/OHLCV/Trades/BidVol/AskVol tick bars; Touch data: ZRA_Hist CSV with 32 cols including Reaction, Penetration, RxnBar_* — both sets validated for P1 and P2
- [Phase 01-scaffold]: zone_csv_v2 used as source_id for ZRA touch data; matches architecture doc; files use ZRA_Hist_*.csv pattern on disk
- [Phase 01-scaffold]: period_config.md committed before any evaluation file — STATE.md P1a/P1b blocker cleared
- [Phase 01-scaffold]: data_registry.md zone_csv_v2 source_id must match zone_csv_v2_schema.md in Plan 04 Stage 01 references
- [Phase 01-scaffold]: Scoring adapter stubs raise NotImplementedError instead of pass/None — prevents silent failure in Phase 4
- [Phase 01-scaffold]: feature_rules.md held to 15 lines — operative rules in first 5 lines per lost-in-middle constraint
- [Phase 01-scaffold]: verdict_criteria.md is a local copy for agent access; source of truth remains _config/statistical_gates.md
- [Phase 01-scaffold]: assemble_context.sh reads archetype from frozen_params.json at runtime — never hardcoded (Pitfall 6 prevention)
- [Phase 01-scaffold]: Stage 07 review triggers kept in separate file to allow threshold expansion without exceeding CONTEXT.md 80-line limit
- [Phase 01-scaffold]: zone_csv_v2_schema.md filename matches zone_csv_v2 source_id in data_registry.md — schema-to-source_id naming convention established
- [Phase 01-scaffold]: trail_steps[0] where new_stop_ticks=0 IS the BE trigger — no separate be_trigger_ticks field per Q3 answer
- [Phase 01-scaffold]: results_master.tsv created programmatically using printf \t to guarantee tab delimiters -- not hand-authored
- [Phase 01-scaffold]: strategy_archetypes.md has no active archetype entry -- intake checklist required before first autoresearch run (anti-pattern: entry without registered simulator)
- [Phase 01-scaffold]: Simulator interface: def run(bar_df, touch_row, config, bar_offset) -> SimResult -- pure function, no I/O, returns pnl_ticks/win/exit_reason/bars_held
- [Phase 01.1-scoring-adapter-scaffold-generator]: Tests monkeypatch all 4 module-level Path constants for test isolation without touching live audit_log.md and scoring_adapter.py
- [Phase 01.1-scoring-adapter-scaffold-generator]: tests/ directory created at repo root as first integration test location for pipeline
- [Phase 02-hmm-regime-fitter]: Three independent GaussianHMMs (trend 2-state, vol 3-state) plus calendar macro — not joint HMM — for independent per-dimension label columns in regime_labels.csv
- [Phase 02-hmm-regime-fitter]: predict_proba().argmax() (filtered posteriors) for regime labels, not predict() (Viterbi) — per pipeline requirements
- [Phase 02-hmm-regime-fitter]: P1 standardization stats stored as _p1_mean/_p1_std on fitted model; P1 mask uses <= P1_END (inclusive); P1 row count asserted == 77 before fit()
- [Phase 02-hmm-regime-fitter]: Artifacts (regime_labels.csv, hmm_regime_v1.pkl) committed in Plan 02 after validation — separates fitter code delivery from validated artifact delivery
- [Phase 02-hmm-regime-fitter]: Shared Scoring Models section in strategy_archetypes.md placed above archetype placeholder — shared resources registration pattern established for pkl model artifacts
- [Phase 01.2-bar-type-registry-and-subfolder-structure]: bar_data_volume source_id used (not bar_data) — encodes bar type, matches schema filename convention, aligns with architecture doc
- [Phase 01.2-bar-type-registry-and-subfolder-structure]: bar_data_time and bar_data_tick registered as placeholder rows with periods=none — documents intent without claiming coverage
- [Phase 01.2-bar-type-registry-and-subfolder-structure]: bar_data subfolder convention: bar_data/<bar_type>/ differs from other sources <source_id>/ — documented in data_registry.md To Add a New Source workflow
- [Phase 03-git-infrastructure]: Path-prefix holdout guard (grep -q stages/04-backtest/p2_holdout/) replaces three-file list — covers all files under directory, strictly safer
- [Phase 03-git-infrastructure]: Audit append-only grep pattern: use grep ^- | grep -v ^--- instead of ^-[^-] — original pattern fails on markdown list items in diffs
- [Phase 03-git-infrastructure]: Recursion guard added to post-commit: git commit --amend DOES re-fire post-commit on Windows/MSYS2 git 2.53; lock file .git/post-commit-amend.lock prevents infinite loop
- [Phase 03-git-infrastructure]: No code changes required in Plan 02 — Plan 01 delivered correct implementations; manual verification confirmed all three tests pass
- [Phase 04-backtest-engine]: cost_ticks not in config JSON — engine reads from _config/instruments.md at startup via config.instrument lookup
- [Phase 04-backtest-engine]: trail_steps[0] with new_stop_ticks=0 IS the BE trigger — no separate be_trigger_ticks field; empty trail_steps[] valid for no-trail modes
- [Phase 04-backtest-engine]: Individual trade pnl_ticks in SimResult is raw; cost_ticks applied only during metrics aggregation for PF calculation
- [Phase 04-backtest-engine]: Touch file ZRA_Hist_P1.csv has 33 columns not 32 — test corrected to file ground truth
- [Phase 04-backtest-engine]: parse_instruments_md regex uses ticks? to handle both singular and plural tick count format in instruments.md
- [Phase 04-backtest-engine]: BinnedScoringAdapter.score() returns pd.Series(0.0, index=touch_df.index) for placeholder model with empty weights
- [Phase 04-backtest-engine]: Stop price tracked as absolute price not ticks — required for trail ratchet above entry (BE trigger and profitable stop exits)
- [Phase 04-backtest-engine]: Engine _REPO_ROOT uses parents[3]: file is 3 levels deep under repo root (stages/04-backtest/autoresearch/)
- [Phase 04-backtest-engine]: test_determinism added as standalone function (not class method) so pytest::test_determinism address works per plan verify step
- [Phase 04-backtest-engine]: assess.py uses parse_instruments_md() from shared.data_loader for cost_ticks — consistent with engine, no regex duplication
- [Phase 04-backtest-engine]: INSUFFICIENT_DATA verdict in verdict_report.md is correct for uncalibrated model — plan explicitly anticipated this outcome
- [Phase 05-stage-04-autoresearch]: validate_trail_steps() returns bool not raises — driver retries proposal with valid steps rather than propagating exceptions
- [Phase 05-stage-04-autoresearch]: score_threshold=0 in seeded baseline — BinnedScoringAdapter returns zeros; threshold=48 produces n_trades=0 for every experiment
- [Phase 05-stage-04-autoresearch]: Budget counts seeded row — n_prior_tests=1 at start of first experiment; budget=3 means 2 new experiments run
- [Phase 05-stage-04-autoresearch]: importlib.util.spec_from_file_location used for path-based evaluator loading — no sys.path mutation, loads fresh module each call
- [Phase 05-stage-04-autoresearch]: --archetype-base-dir CLI flag on dispatcher enables test isolation without touching real evaluators
- [Phase 05-stage-04-autoresearch]: feature_evaluator.py Phase 5 placeholder returns empty features list; Phase 6 adds MWU spread via feature_engine.py
- [Phase 05-stage-04-autoresearch]: Budget counts seeded row — budget=3 means 2 new experiments run; smoke-test before overnight run prevents wasted compute
- [Phase 05-stage-04-autoresearch]: _generate_run_id uses SHA-256 hash of archetype:timestamp:experiment_n truncated to 8 hex chars — unique per experiment, no git subprocess
- [Phase 05-stage-04-autoresearch]: hypothesis_name falls back to archetype name (not empty string) — always non-empty in TSV; promoted_hypothesis.json overrides when present
- [Phase 05-stage-04-autoresearch]: _git_commit failures are non-fatal (try/except pass) — git errors must not abort the experiment loop
- [Phase 06-stage-02-autoresearch]: entry_time_violation read per-feature from features_evaluated list (not top-level key) — dispatcher drops top-level keys from evaluate() return value
- [Phase 06-stage-02-autoresearch]: parse_program_md requires 4 fields (metric, keep_rule, budget, new_feature) — Stage 04 only required 3; NEW_FEATURE enables driver to look up matching feature in features_evaluated
- [Phase 06-stage-02-autoresearch]: Stage 02 keep rule is threshold-based (spread > keep_rule AND mwu_p < 0.10), not improvement-based like Stage 04 — no baseline metric tracking needed
- [Phase 06-stage-02-autoresearch]: precomputed-pnl selected as outcome variable; Reaction used as fallback proxy until pnl_ticks column available in touch CSV
- [Phase 06-stage-02-autoresearch]: entry_time_violation per-feature not top-level — dispatcher only forwards result['features'], top-level keys dropped
- [Phase 06-stage-02-autoresearch]: P1a/P1b empirical counts are 2952/3280 (not 2882/3267 per research docs) — tests corrected to data ground truth
- [Phase 06-stage-02-autoresearch]: freeze_features.py uses importlib introspection on current_best/feature_engine.py — no sys.path mutation, path resolution from stages/02-features/ (parents[1])
- [Phase 06-stage-02-autoresearch]: frozen_features.json written to stages/02-features/output/ with features list, frozen_date, source path — Stage 03 must copy to stages/03-hypothesis/references/
- [Phase 06-stage-02-autoresearch]: Budget smoke test (budget=3, n-experiments=5) run before overnight — driver stopped at 3 as expected; 20-experiment smoke test all verdict=kept, spread=44.09, mwu_p=1.48e-07
- [Phase 07-stage-03-autoresearch]: hypothesis_generator.py uses subprocess check=True for engine calls — driver handles CalledProcessError as EXPERIMENT_ANOMALY
- [Phase 07-stage-03-autoresearch]: replication_gate read at loop start from _config/period_config.md — stable per-session, hard_block reverts, flag_and_review flags as kept_weak_replication
- [Phase 07-stage-03-autoresearch]: Stage 03 TSV uses 25 columns (replication_pass added after notes) — does not affect Stage 02 or 04 TSV headers
- [Phase 07-stage-03-autoresearch]: stage03_ref_path defaults to repo-root-relative path internally — not a CLI flag, keeping interface minimal
- [Phase 07-stage-03-autoresearch]: What Worked threshold PF>1.5, What to Avoid threshold PF<1.0 — matches verdict_label() thresholds in assess.py

### Pending Todos

None yet.

### Roadmap Evolution

- Phase 01.1 inserted after Phase 1: Scoring Adapter Scaffold Generator (URGENT) — adds scaffold_adapter.py to auto-generate adapter stubs when new archetypes are registered
- Phase 01.2 inserted after Phase 1: Bar type registry and subfolder structure (URGENT) — splits flat bar_data/ into typed subfolders (volume/time/tick), registers each as separate source_id in data_registry.md

### Blockers/Concerns

- [Pre-start]: hmmlearn 0.3.3 is in limited-maintenance mode — pin full dependency tree in Phase 2 and add import smoke test to verify NumPy ABI compatibility
- [Pre-start]: P1a/P1b split boundary must be committed to period_config before ANY Stage 04 evaluation file exists; verify git log timestamp ordering when closing Phase 1
- [Pre-start]: quantstats pandas 2.x compatibility unverified — add tearsheet smoke test to Phase 4 acceptance criteria

## Session Continuity

Last session: 2026-03-14T21:22:58.217Z
Stopped at: Completed 07-stage-03-autoresearch plan 03 (assess.py feedback loop wiring)
Resume file: None
