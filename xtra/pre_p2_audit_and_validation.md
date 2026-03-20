# Pre-P2 Audit & P2a Validation

> **⚠️ CRITICAL — TWO TASKS IN THIS PROMPT**
> 1. **Task 1: Audit** — verify all Phase 1+2 artifacts, config consistency, P2 contamination ledger
> 2. **Task 2: P2a Validation** — one-shot frozen config on P2a data. Do NOT run until audit passes.
> 3. **P2b is UNTOUCHED.** Only P2a is used here. P2b is the final holdout.
> 4. **cost_ticks = 1** for all calculations.

---

## Task 1: Pre-P2 Audit

### 1A: Verify All Phase 1 Artifacts

| Artifact | Expected | Status |
|----------|----------|--------|
| `phase1_base_config.json` | Base config before SR layer | ? |
| `full_p1_base_cycles.parquet` | Cycle data with all fields (3,424+ cycles) | ? |
| `step1b_zigzag_sensitivity.json` | ZZ sensitivity: PASS, 5.25 pt validated | ? |
| `step2_sweep_results.json` | 39 configs (30 fixed + 9 adaptive) | ? |
| `step5_summary.json` | Phase 1 freeze summary | ? |

### 1B: Verify All Phase 2 Artifacts

| Artifact | Expected | Status |
|----------|----------|--------|
| `phase2_final_config.json` | Frozen V1.4 config | ? |
| `phase2_step5_summary.md` | Decision log with layered improvement table | ? |
| `phase2_step6_cpp_plan.md` | C++ three-study architecture | ? |
| SR sweep results (JSON) | Both-SR threshold sweep, hysteresis results | ? |
| Feature discovery results (JSON) | 17 features, quintile diagnostics | ? |
| Risk mitigation results (JSON) | 4A/4B/4C results + post-P2 queue items | ? |

> **⚠️ If ANY artifact is missing, recreate it before proceeding. The audit trail must be complete.**

### 1C: Frozen Config Consistency Check

Read `phase2_final_config.json` and verify every parameter matches across all saved artifacts:

| Parameter | Expected Value | Source |
|-----------|---------------|--------|
| StepDist | Rolling zigzag P90 (200-swing window) | Phase 1 Step 2 |
| AddDist | Rolling zigzag P75 (200-swing window) | Phase 1 Step 2 |
| SeedDist | 15 pts fixed | Phase 1 Step 3 |
| Session start | 10:00 ET | Phase 2 P0-2 |
| Session end / flatten | 16:00 ET | Settled |
| ML | 1 | Phase 1 Step 2b (reopened, confirmed) |
| Position cap | 2 | Phase 1 Step 2b (reopened, confirmed) |
| Anchor mode | Walking (cap-walk uses StepDist) | Settled |
| Watch price | First tick at/after 10:00 ET | Updated from 09:30 |
| SR block behavior | Watch price stays fixed | Settled (F/G killed) |
| SpeedRead filter | Roll50 SR ≥ 48 (both seed + reversal) | Phase 2 Step 2 |
| SpeedRead normalization | Median (200-bar trailing window) | SpeedRead V2 |
| Zigzag settings | 5.25 pt reversal, calc mode 3, no bar filter | Settled (sensitivity passed) |
| Zigzag rolling window | 200 swings, computed from ALL RTH bars | Phase 1 B4 |
| Daily flatten | 16:00 ET | Settled |
| cost_ticks | 1 | Settled |

Cross-check: does ANY saved artifact contradict any value in this table? If yes, flag it.

> **⚠️ NOTE: TWO separate rolling computations exist in this config:**
> 1. **ZigZagRegime:** 200-swing rolling window of zigzag leg distances → P90 (StepDist) and P75 (AddDist)
> 2. **SpeedRead filter:** 50-bar rolling average of SpeedRead composite → threshold ≥ 48
> These are different studies, different windows, different data. Do NOT conflate them.

### 1D: P2 Contamination Ledger

Verify that P2 data has NEVER been used in any Phase 1 or Phase 2 computation:

| Investigation | Touched P2? | Evidence |
|--------------|-------------|---------|
| Phase 1 Step 1 (simulator) | NO | `load_data('full_p1')` filters to P1 dates |
| Phase 1 Step 1b (zigzag) | NO | 250-tick CSV filtered to P1 dates |
| Phase 1 Step 2 (SD×AD sweep) | NO | Full P1 only |
| Phase 1 Step 2b (ML/cap) | NO | Full P1 only |
| Phase 1 Step 3 (SeedDist) | NO | Full P1 only |
| Phase 1 Step 4 (session window) | NO | Full P1 only |
| Phase 2 P0 (window/start/SR) | NO | Full P1 only |
| Phase 2 Steps 1-4 (SR/features/risk) | NO | Full P1 only |
| 250-tick CSV zigzag columns | VERIFY | CSV extends to March 2026 — confirm rolling percentiles used P1-filtered data only |
| SpeedRead composite | VERIFY | Composite covers all hours/dates — confirm simulation only read P1 portion |

> **⚠️ The 250-tick CSV extends into P2. Confirm the zigzag rolling percentile lookup was filtered to P1 dates. If any P2 zigzag data leaked into the rolling window computation, the adaptive StepDist/AddDist values are contaminated.**

### 1E: Code Artifacts

| File | Purpose | Status |
|------|---------|--------|
| `run_seed_investigation.py` | Core simulator (AddDist decoupled, session window, ML/cap) | ? |
| `run_phase1_base.py` | Phase 1 sweep harness | ? |
| Phase 2 scripts | SR sweep, feature discovery, risk mitigation | ? |
| `SpeedRead_V2.cpp` | C++ SpeedRead study (on Sierra Chart machine) | NOT in repo |
| `ATEAM_ROTATION_V12SR.cpp` | Current autotrader (OBSOLETE — V1.4 needed) | NOT in repo |

### 1F: Confirm P2 Data Availability

Before P2a can run:
1. What is the P2 1-tick data filepath? Look for a file matching the pattern `NQ_BarData_1tick_rot_P2*.csv` in the same directory as the P1 data.
2. What is the date range (first row to last row)?
3. Total row count?
4. Print first 3 and last 3 rows (date, time, price).
5. **Determine P2a/P2b split:** Split P2 into two roughly equal halves by date. P2a = first half (replication gate). P2b = second half (final holdout). State the split date.
6. **Minimum session count:** P2a must contain at least 20 trading sessions. If fewer, expand P2a at the expense of P2b (P2b minimum = 10 sessions). If total P2 has fewer than 30 sessions, flag this as insufficient data for a reliable two-part holdout.
7. **Confirm 250-tick CSV and SpeedRead parquet cover the full P2a date range.** If they end before P2a ends, the simulation will lack zigzag percentile and SR data.
8. **Identify the simulator script** that has ALL V1.4 features: adaptive SD/AD from rolling zigzag, Roll50 SR filter, 10:00 session start, AddDist decoupling, session window flatten. State the exact filename.

---

> **📌 MID-DOCUMENT REMINDER:**
> - Task 1 = audit. Task 2 = P2a validation (only after audit passes).
> - Frozen config: Adaptive P90/P75, SeedDist=15, 10:00-16:00, Roll50 SR≥48, ML=1, cap=2
> - Two rolling computations: zigzag 200-swing window ≠ SpeedRead 50-bar rolling average
> - P2b untouched. cost_ticks=1.

---

## Task 2: P2a Validation (ONE-SHOT)

> **⚠️ DO NOT RUN UNTIL TASK 1 AUDIT PASSES WITH ZERO ISSUES.**

### 2A: Pre-Run Sanity Check

Run the frozen config on full P1. Confirm it matches known values:
- NPF ≈ 1.200
- Net PnL ≈ +20,919 ticks (Roll50 SR≥48 config)
- If deviation > 5%, STOP and debug.

> **⚠️ This verification ensures the simulation code hasn't been modified since Phase 2 completed. If it doesn't match, something changed.**

### 2B: Run P2a (ONE-SHOT)

> **⚠️ ONE RUN. Frozen parameters. No adjustments after seeing results. No re-runs.**

Run the frozen config on P2a data (first half of P2, date range from Task 1F).

**IMPLEMENTATION CONSISTENCY:** Use the EXACT SAME simulator code and zigzag percentile lookup functions that produced the P1 NPF=1.200 result. Do NOT rewrite or refactor for P2a. Only change the date range and data source. The zigzag `Zig Zag Line Length` column has SIGNED values (positive=up, negative=down) — use `abs()` as established in Phase 1.

**The simulator needs:**
- P2a 1-tick data (filtered to P2a date range)
- 250-tick bars covering P2a for zigzag rolling percentile computation. **NOTE: The 250-tick CSV extends to ~March 2026 and DOES include P2a dates. For P2a simulation, read P2a-dated rows from this CSV — this is NOT a P2 contamination issue because you're running ON P2a data, not training on it. The P1 date filter applied during Phase 1/2 discovery was to prevent P2 leakage into optimization. Here you're validating on P2a intentionally.**
- SpeedRead composite covering P2a. **Same logic — the `speedread_250tick.parquet` covers all dates. Read P2a-dated rows for the simulation.**
- **IMPORTANT:** The zigzag rolling window needs warm-up data from the tail of P1 to compute P90/P75 at the start of P2a. Load the last ~200 zigzag swings from P1's ALL RTH bars (09:30-16:00), NOT just 10:00-16:00 trading window swings. The rolling window always computes from all RTH zigzag activity regardless of the trading session start time. Do NOT start with an empty buffer.
- **Same for SpeedRead:** Roll50 needs 50 bars of warm-up from P1's tail. Load bars from ALL hours (SpeedRead is not RTH-restricted).
- **Confirm the 250-tick CSV covers the full P2a date range.** If it ends before P2a ends, flag this — the simulation would lose zigzag percentile data partway through.

Report ALL of the following:

**Primary metrics:**

> **⚠️ Report ALL of these, not just NPF. Session win% and clean cycle% are critical for assessing whether the strategy is structurally sound OOS, not just aggregate profitable.**

- Total completed cycles
- Gross PF
- Net PF @1t
- Net PnL in ticks
- Sessions
- Daily mean PnL
- Daily std dev
- Session win %
- Seed accuracy
- Clean cycle %
- Mean MAE

**P1 vs P2a comparison:**

| Metric | P1 | P2a | Delta |
|--------|-----|-----|-------|
| Net PF @1t | 1.200 | ? | ? |
| Net PnL | +20,919 | ? | ? |
| Cycles | ~1,847 | ? | ? |
| Daily mean | ? | ? | ? |
| Session win % | ? | ? | ? |
| Clean % | ? | ? | ? |
| Mean MAE | ? | ? | ? |

> **⚠️ REMINDER: This is a ONE-SHOT P2a run. Frozen config: Adaptive P90/P75, SeedDist=15, 10:00-16:00, Roll50 SR≥48, ML=1, cap=2. cost_ticks=1. Do NOT adjust parameters after seeing results.**

**Adaptive range on P2a:**
Report effective StepDist range (min/max/mean) and AddDist range on P2a. If they're wildly different from P1 (e.g., P1 mean SD=22, P2a mean SD=35), the regime has shifted and the strategy is adapting — that's expected behavior, not a bug.

**Distribution analysis:**
- Per-session PnL: P10, P25, median, P75, P90
- Worst 5 sessions (date + PnL)
- Best 5 sessions (date + PnL)
- EV components: P_clean, P_1add, P_capwalk, P_deep + mean PnL per category

**SpeedRead filter activity:**
- SR-block episodes during session
- % of session time blocked
- Cycles skipped by SR filter

### 2C: Pass/Fail Criteria

> **⚠️ The config has multiple optimized parameters (StepDist percentile, AddDist percentile, SeedDist, session start, SR threshold). Expect 20-40% edge degradation OOS.**

**Pass (ALL must be met):**
- Net PF @1t > 1.0
- Gross PF > 1.05
- Session win % > 50%
- Net PnL > 0

**Conditional pass (flag for review):**
- NPF between 1.0 and 1.05 — edge exists but very thin, may not survive live trading costs
- Session win % between 45% and 50% — high daily variance
- Clean cycle % drops below 40% — strategy struggling to complete cycles
- P2a NPF degrades more than 30% from P1 (P2a NPF < 0.84) — strategy works but heavy overfitting to P1

**Fail (ANY triggers fail):**
- NPF < 1.0
- Net PnL < 0
- Session win % < 45%

### 2D: Save Results

Regardless of pass or fail:

1. `p2a_validation_cycles.parquet` — all cycle data with features
2. `p2a_validation_sessions.json` — per-session summary
3. `p2a_validation_result.json` — all metrics, pass/fail, comparison table, frozen config

4. **Update contamination ledger:**
   - "P2a validation: Frozen V1.4 config | [result] | Contaminated"

> **⚠️ P2b REMAINS UNTOUCHED. If P2a passes, P2b is the final holdout — run only when ready to commit to live trading.**

---

## Pipeline Rules (Absolute)

> **⚠️ REMINDER: Frozen config = Adaptive P90/P75, SeedDist=15, 10:00-16:00, Roll50 SR≥48, ML=1, cap=2. cost_ticks=1. One-shot P2a. No re-runs.**

1. **Audit passes before P2a runs.** Zero issues.
2. **P1 sanity check before P2a.** Must match known NPF≈1.200.
3. **ONE-SHOT P2a.** No parameter changes, no re-runs.
4. **Warm-up data from P1 tail.** Rolling windows need seed data.
5. **P2b UNTOUCHED.**
6. **cost_ticks = 1.**
7. **Save everything regardless of outcome.**
8. **Report honestly.** If it fails, document the failure.

---

## ⚠️ Common Mistakes — Self-Check

**Task 1 (Audit):**
- [ ] All Phase 1 + Phase 2 artifacts exist and contain expected data
- [ ] Frozen config consistent across ALL saved files
- [ ] Two rolling computations distinguished (zigzag 200-swing ≠ SpeedRead Roll50)
- [ ] P2 contamination ledger verified — no P2 data in any P1/P2 computation
- [ ] 250-tick CSV zigzag columns confirmed P1-filtered in rolling percentile computation
- [ ] P2 data file found, date range confirmed, P2a/P2b split determined
- [ ] P2a has ≥ 20 sessions (statistical minimum)
- [ ] 250-tick CSV and SpeedRead parquet cover full P2a date range
- [ ] Simulator script identified with ALL V1.4 features

**Task 2 (P2a):**
- [ ] P1 sanity check passes (NPF≈1.200, ±5%)
- [ ] P2a date range correct (first half of P2 only)
- [ ] Warm-up: last 200 RTH zigzag swings (09:30-16:00, not just 10:00-16:00) from P1
- [ ] Warm-up: last 50 SpeedRead bars from P1 (all hours, not RTH-restricted)
- [ ] Session start = 10:00 ET (NOT 09:30)
- [ ] SeedDist = 15 (NOT StepDist)
- [ ] SR filter: Roll50 ≥ 48 on BOTH seed and reversal
- [ ] Same simulator code as Phase 1/2 — no refactoring, just different date range
- [ ] Zigzag Line Length column uses abs() (signed values: positive=up, negative=down)
- [ ] Adaptive StepDist/AddDist ranges reported for P2a
- [ ] All metrics reported (not just NPF)
- [ ] Pass/fail determined against ALL criteria
- [ ] All cycle and session data saved
- [ ] Contamination ledger updated
- [ ] P2b NOT touched
- [ ] Did NOT re-run or adjust after seeing results
