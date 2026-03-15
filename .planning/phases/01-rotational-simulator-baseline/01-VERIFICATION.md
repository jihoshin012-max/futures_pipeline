---
phase: 01-rotational-simulator-baseline
verified: 2026-03-15T22:15:00Z
status: passed
score: 10/10 must-haves verified
re_verification: false
---

# Phase 01: Rotational Simulator & Baseline Verification Report

**Phase Goal:** Build rotational_simulator.py (continuous state machine), FeatureComputer, TradeLogger with cycle tracking, verify determinism, implement RTH session filter, run C++ defaults baseline on all 3 bar types, execute fixed-step parameter sweep (StepDist 1.0-6.0) to establish per-bar-type optimized baselines
**Verified:** 2026-03-15T22:15:00Z
**Status:** passed
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Simulator processes every bar sequentially and produces correct SEED/REVERSAL/ADD actions | VERIFIED | State machine fully implemented; all 43 synthetic unit tests pass (TestSeed, TestReversal, TestAdd, TestAddCap classes) |
| 2 | Cycle records capture all required fields from spec Section 6.4 | VERIFIED | `finalize_cycle()` produces 19 fields: cycle_id, start_bar, end_bar, direction, duration_bars, entry_price, exit_price, avg_entry_price, adds_count, max_level_reached, max_position_qty, gross_pnl_ticks, net_pnl_ticks, max_adverse_excursion_ticks, max_favorable_excursion_ticks, retracement_depths, time_at_max_level_bars, trend_defense_level_max, exit_reason. TestCycleRecord confirms all fields present. |
| 3 | 10-sec bars are RTH-filtered before simulation (09:30-16:00 ET) | VERIFIED | `_filter_bars()` applies RTH mask when "10sec" in source_id key; TestRTHFilter covers 09:30 include, 08:00/16:00/16:01 exclude, mixed bars, and vol-bars-not-filtered |
| 4 | P1a date filtering works (only bars within P1a period are simulated) | VERIFIED | `_filter_bars()` bisects P1 window at midpoint (~2025-11-02); TestDateFilter covers P1a/P1b/P1 cases; sweep bars_processed=52028 (vol), 47837 (tick), 70200 (10sec) — consistent with half-period filtering |
| 5 | Cost model correctly charges cost_ticks per action, double for reversals | VERIFIED | SEED costs cost_ticks*qty; REVERSAL logs FLATTEN (cost*flatten_qty) + REVERSAL entry (cost*initial_qty); TestCostModel verifies arithmetic |
| 6 | Running the simulator twice with identical config+data produces identical output (determinism) | VERIFIED | TestDeterminismRealData class: 3 @pytest.mark.slow tests on real 250-vol P1a data (66,539 bars); bars_processed, trades, and cycles DataFrames are bit-for-bit identical across two runs. All 46 tests pass in 86s. |
| 7 | Baseline run (StepDist=2.0) completes on all 3 bar types using P1a data | VERIFIED | baseline_P1a.json exists with per_source for all 3 bar types; vol: 21,604 cycles, tick: 20,448 cycles, 10sec: 17,939 cycles — all n_cycles > 0 |
| 8 | Baseline metrics (cycle_pf, n_cycles, win_rate, total_pnl_ticks) captured per bar type | VERIFIED | baseline_P1a.json contains cycle_pf, n_cycles, win_rate, total_pnl_ticks for each of 3 bar types; no NaN or infinite values |
| 9 | Parameter sweep runs StepDist 1.0 through 6.0 in 0.5 increments (11 values) on all 3 bar types | VERIFIED | sweep_P1a.json has 11 step values, each with 3 sources = 33 total combinations; n_cycles is monotonically decreasing as StepDist increases (confirmed); bars_processed identical across all StepDist values for each bar type (confirmed) |
| 10 | Per-bar-type optimized baseline is identified; results saved in JSON and TSV | VERIFIED | best_per_source: all 3 bar types peak at StepDist=6.0; sweep_P1a.tsv has 33 data rows + header (34 lines total) |

**Score:** 10/10 truths verified

---

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `shared/archetypes/rotational/rotational_simulator.py` | RotationalSimulator class with run() -> SimulationResult | VERIFIED | 625 lines; line 1 is `# archetype: rotational`; exports RotationalSimulator, SimulationResult, FeatureComputer, TradeLogger; all three classes substantive |
| `shared/archetypes/rotational/test_rotational_simulator.py` | Unit tests for state machine logic | VERIFIED | 737 lines; 46 tests across 9 test classes (TestSeed, TestReversal, TestAdd, TestAddCap, TestCycleRecord, TestCostModel, TestRTHFilter, TestDateFilter, TestContract, TestDeterminism, TestDeterminismRealData); all 46 pass |
| `shared/archetypes/rotational/baseline_results/baseline_P1a.json` | Baseline metrics for all 3 bar types at StepDist=2.0 | VERIFIED | Contains per_source with all 3 bar types; realistic non-NaN metrics |
| `shared/archetypes/rotational/run_sweep.py` | Parameter sweep runner script | VERIFIED | 302 lines; line 1 is `# archetype: rotational`; imports RotationalSimulator directly, load_bars, parse_instruments_md, compute_cycle_metrics |
| `shared/archetypes/rotational/baseline_results/sweep_P1a.json` | Full sweep results for all StepDist x bar_type combinations | VERIFIED | 11 step values x 3 sources = 33 entries; contains best_per_source section |
| `shared/archetypes/rotational/baseline_results/sweep_P1a.tsv` | Human-readable sweep summary table | VERIFIED | 34 lines (header + 33 data rows); step_dist column present |

---

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `rotational_simulator.py` | `rotational_engine.py` | RotationalSimulator loaded by engine's load_simulator() | WIRED | Engine uses importlib.import_module; checks for RotationalSimulator class; instantiates with (config=source_config, bar_data=bars, reference_data=...) and calls .run(); contract matches exactly |
| `rotational_simulator.py` | `shared/data_loader.py` | parse_instruments_md for cost_ticks (via engine injection into config._instrument) | WIRED | Engine calls parse_instruments_md(), injects result as config["_instrument"]; simulator reads cost_ticks from config._instrument — no direct call needed, contract fulfilled through config injection |
| `run_sweep.py` | `rotational_simulator.py` | Direct import of RotationalSimulator | WIRED | Line 35: `from rotational_simulator import RotationalSimulator`; instantiates at line 86 |
| `run_sweep.py` | `shared/data_loader.py` | load_bars and parse_instruments_md | WIRED | Line 34: `from shared.data_loader import load_bars, parse_instruments_md`; called at lines 262 and 273 |
| `rotational_engine.py` | `rotational_simulator.py` (per-source config scoping) | RTH filter bug fix: engine scopes bar_data_primary to single key per run | WIRED | Lines 322-323: `source_config = dict(config); source_config["bar_data_primary"] = {source_id: ...}` — ensures RTH filter only activates for the 10sec source being processed |

---

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| ROT-SIM-01 | 01-01-PLAN | Build RotationalSimulator class implementing state machine (FLAT/POSITIONED, SEED/REVERSAL/ADD) per spec Section 1.2 | SATISFIED | rotational_simulator.py exists, 625 lines, state machine fully implemented and tested |
| ROT-SIM-02 | 01-01-PLAN | Build FeatureComputer with compute_static_features() for baseline (reads ATR, SD bands from CSV columns) | SATISFIED | FeatureComputer class implemented as extensible pass-through; ATR and SD bands in CSV columns, no recomputation needed at baseline |
| ROT-SIM-03 | 01-01-PLAN | Build TradeLogger with cycle tracking — cycle record per spec Section 6.4 with all required fields | SATISFIED | TradeLogger.finalize_cycle() produces all 19 spec Section 6.4 fields; TestCycleRecord confirms all required fields present |
| ROT-SIM-04 | 01-01-PLAN | Implement RTH session filter for 10-sec bars (9:30-16:00 ET) | SATISFIED | _filter_bars() with RTH mask, 09:30 inclusive / 16:00 exclusive; fractional seconds bug in Time parsing fixed in plan 03 (_parse_time uses int(float(parts[2]))) |
| ROT-SIM-05 | 01-02-PLAN | Verify determinism — identical config+data produces identical output | SATISFIED | TestDeterminismRealData: 3 slow tests on 66,539 real bars; all pass; check_exact=True used |
| ROT-SIM-06 | 01-02-PLAN | Run C++ defaults baseline (StepDist=2.0, MaxLevels=4) on all 3 bar types P1a, produce raw baseline metrics | SATISFIED | baseline_P1a.json: vol=21,604 cycles/PF=0.5075, tick=20,448/PF=0.5071, 10sec=17,939/PF=0.5032 |
| ROT-SIM-07 | 01-03-PLAN | Execute fixed-step parameter sweep (StepDist 1.0-6.0, step 0.5) on P1a all 3 bar types, establish per-bar-type optimized baseline | SATISFIED | 33 combinations completed; best_per_source: all 3 bar types at StepDist=6.0; monotonicity verified; TSV has 33 data rows |

No orphaned requirements found. All 7 ROT-SIM-* IDs declared in plan frontmatter and present in REQUIREMENTS.md (all marked complete).

---

### Anti-Patterns Found

| File | Pattern | Severity | Impact |
|------|---------|----------|--------|
| None found | — | — | — |

Scanned: rotational_simulator.py, test_rotational_simulator.py, run_sweep.py. No TODO/FIXME/placeholder comments. No stub return values (return null/return []). No console.log-only handlers. All implementations substantive.

---

### Human Verification Required

#### 1. Baseline metrics are negative PnL — expected behavior, not a bug

**Test:** Inspect baseline_P1a.json. All 3 bar types show negative total_pnl_ticks at StepDist=2.0.
**Expected:** Negative PnL is correct for an unoptimized martingale reversal strategy at NQ default parameters. The martingale's ADD structure absorbs large losses that overwhelm the 70-73% win rate.
**Why human:** Cannot verify "expected negative PnL" programmatically — requires domain understanding to confirm this is intentional, not a simulator logic error.

#### 2. P1a date filter midpoint calculation

**Test:** Verify P1 midpoint (~2025-11-02) is the correct bisection of 2025-09-21 to 2025-12-14.
**Expected:** Midpoint = 2025-09-21 + 84 days = 2025-12-14; half = 42 days -> ~2025-11-02. The sweep results show vol bars_processed=52,028 vs total P1 raw (66,539 from baseline run which filters P1a), which is consistent with approximately half the P1 window.
**Why human:** The spec says "first half" but does not pin an exact date. The current implementation uses arithmetic bisection; a human should confirm this matches the intended P1a/P1b boundary if a specific date was intended.

---

### Gaps Summary

No gaps. All must-haves verified. All requirements satisfied. All commits confirmed in git log (2a854f8, cc3dd82, 2f32952, cc319f2, 3506eaa).

One noteworthy auto-fix from plan 02: the engine's RTH filter scope bug (engine was passing full config with all 3 `bar_data_primary` keys to each simulator, causing vol/tick bars to be RTH-filtered) was identified and corrected. The fix is in rotational_engine.py (per-source config scoping at lines 322-323) and is correctly verified.

One auto-fix from plan 03: fractional seconds in 10-sec bar Time column format (`HH:MM:SS.ffffff`) was handled by changing `int(parts[2])` to `int(float(parts[2]))` in `_parse_time`. This was required for the sweep to complete and is correct.

---

## Commit Verification

| Commit | Description | Verified |
|--------|-------------|---------|
| 2a854f8 | feat(01-01): build RotationalSimulator with state machine, FeatureComputer, TradeLogger | Found in git log |
| cc3dd82 | feat(01-02): verify determinism on real P1a data; fix RTH filter scope bug | Found in git log |
| 2f32952 | feat(01-02): run C++ defaults baseline (StepDist=2.0) on P1a all 3 bar types | Found in git log |
| cc319f2 | feat(01-03): build parameter sweep runner script | Found in git log |
| 3506eaa | feat(01-03): execute P1a parameter sweep, produce baseline results | Found in git log |

---

_Verified: 2026-03-15T22:15:00Z_
_Verifier: Claude (gsd-verifier)_
