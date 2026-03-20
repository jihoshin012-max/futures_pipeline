# Rotational Archetype — Context

## Current Status: Phase 0 (Calibration Gate)

### What's Done
- Fractal structure discovery complete (Sept 2025 – Mar 2026, 60.9M 1-tick bars)
- Six structural facts established and documented
- Strategy hypothesis v3 finalized: 5 approaches, ~221 sweep configs
- V1.1 C++ reference and live trade log archived

### What's Next
- **Phase 0:** Calibrate Python simulator against C++ V1.1 live log (see phase0_calibration_prompt.md)
- **Phase 1:** Primary sweep (~221 configs on P1 data) — BLOCKED on Phase 0 pass
- **Phase 2:** Secondary sweep (FlattenReseed + ReversalTarget) — BLOCKED on Phase 1
- **Phase 3:** P2a replication — BLOCKED on Phase 2
- **Phase 4:** P2b validation — BLOCKED on Phase 3

### Key Documents
- `docs/fractal_strategy_hypothesis_v3.md` — source of truth for sweep design
- `docs/phase0_calibration_prompt.md` — calibration gate specification
- `docs/fractal_decomposition_prompt.md` — original analysis prompt
- `docs/fractal_monitor_skill_prompt.md` — quarterly monitoring skill spec
- `references/ATEAM_ROTATION_V1_1.cpp` — V1.1 state machine reference
- `references/ATEAM_ROTATION_V1_1_log_live.csv` — calibration ground truth

### Key Findings (Fractal Analysis)
- Self-similarity confirmed: mean/threshold ≈ 2.0x, skewness ≈ 1.9 across all scales
- Completion at 1 retracement: ~75-80% (structural backing for first add)
- Optimal parent/child ratio: 2.5 (25→10 pair highest completion)
- Half-block curve: 70% at entry → 86% at 70% progress → 95% at 90%
- Time-of-day: structure stable (7-12pp variation), not time-dependent

### Period Boundaries
- P1: Sept 21, 2025 – Dec 17, 2025 (sweep calibration)
- P2a: Dec 17, 2025 – ~Jan/Feb 2026 (replication)
- P2b: ~Jan/Feb 2026 – Mar 13, 2026 (validation)
