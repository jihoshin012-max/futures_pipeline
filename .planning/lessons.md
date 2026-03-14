# Lessons & Build Constraints

Cross-session learnings and forward constraints. Review at session start and before major refactors.

---

## Phase 7 — hypothesis_generator.py Build Constraints

Recorded: 2026-03-14 (during Phase 01.2 execution)
Source: period_config.md replication gate redesign

### CONSTRAINT 1 — P1a/P1b boundaries from data_manifest.json
hypothesis_generator.py must read P1a/P1b start/end dates from data_manifest.json.
Stage 01 computes and writes these from p1_split_rule in period_config.md.
Do not hardcode dates in Python.

### CONSTRAINT 2 — Gate behaviour must be runtime-configurable
Read replication_gate from data_manifest.json. Apply:
- replication_pass true → proceed
- replication_pass false + hard_block → verdict: NO
- replication_pass false + flag_and_review → verdict: WEAK_REPLICATION, log flag, do not auto-block, surface for human review
- n_trades_p1b < 15 → replication_pass: inconclusive, always flag_and_review regardless of gate setting

### CONSTRAINT 3 — Result JSON must include replication_gate field
So results_master.tsv and dashboard can show which gate was active when each verdict was produced.

### Done check (at Phase 7 build time)
- [ ] Set replication_gate: hard_block, force P1b fail → verdict: NO
- [ ] Set replication_gate: flag_and_review, same failure → verdict: WEAK_REPLICATION not NO
- [ ] Set n_trades_p1b < 15 → replication_pass: inconclusive regardless of gate setting
- [ ] Result JSON contains replication_gate field
