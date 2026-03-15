# Phase 1: Rotational Simulator & Baseline - Context

**Gathered:** 2026-03-15
**Status:** Ready for planning
**Source:** PRD Express Path (xtra/Rotational_Archetype_Spec.md — Sections 1, 6, Phase B)

<domain>
## Phase Boundary

Build the core rotational simulator as a continuous state machine, feature computation layer, cycle-level trade logging, RTH session filter, and baseline establishment via C++ defaults + fixed-step parameter sweep. This phase produces the working simulator and per-bar-type optimized baselines that all Phase C hypotheses must beat.

**What this phase delivers:**
1. `rotational_simulator.py` — baseline-only state machine (no hypotheses, no trend defense)
2. `FeatureComputer` — static features needed for baseline (ATR, SD bands are in data; no computed features needed yet)
3. `TradeLogger` with cycle tracking (cycle record per spec Section 6.4)
4. RTH session filter for 10-sec bars (9:30-16:00 ET)
5. Determinism verification (identical run -> empty diff)
6. Raw baseline metrics (StepDist=2.0 on all 3 bar types, P1a)
7. Fixed-step parameter sweep (StepDist 1.0-6.0, step 0.5, all 3 bar types)
8. Per-bar-type optimized baseline established

**What this phase does NOT deliver:**
- No hypothesis implementation (Phase C)
- No Trend Defense System (Phase C)
- No assessment/verdict logic (Phase D)
- No computed features beyond what's in the CSV columns (those come in Phase C)

</domain>

<decisions>
## Implementation Decisions

### State Machine (from spec Section 1.2 — locked)
- States: FLAT -> POSITIONED (Long/Short, Level 0..N)
- Actions: SEED, REVERSAL, ADD
- SEED: Position flat, no anchor -> Buy InitialQty, Direction=Long, Anchor=Price, Level=0
- REVERSAL: Price >= StepDist IN FAVOR from Anchor -> Flatten all, Enter opposite, Direction flips, Anchor=Price, Level=0
- ADD: Price >= StepDist AGAINST from Anchor -> Add (InitialQty * 2^Level), Anchor=Price, Level++
- Cap: If add qty > MaxContractSize -> reset to InitialQty, Level=0
- Always seeds Long (matching C++ behavior — RQ-06 resolved)

### Baseline Parameters (locked)
- StepDist: 2.0 pts
- InitialQty: 1
- MaxLevels: 4 (sizes: 1, 2, 4, 8)
- MaxContractSize: 8

### Cycle Definition (from spec Section 6.4 — locked)
- A cycle = seed/reversal through all adds to the next reversal
- Cycle record fields: cycle_id, start_bar, end_bar, direction, duration_bars, entry_price, exit_price, avg_entry_price, adds_count, max_level_reached, max_position_qty, gross_pnl_ticks, net_pnl_ticks, max_adverse_excursion_ticks, max_favorable_excursion_ticks, retracement_depths[], time_at_max_level_bars, trend_defense_level_max, exit_reason

### Cost Model (locked)
- Each action (seed, reversal entry, add) incurs cost_ticks from instruments.md (3 ticks for NQ)
- Reversal incurs cost twice (flatten + re-enter)
- Cycle net PnL = gross PnL - (number_of_actions * cost_ticks * position_size_at_action)

### Data Sources (locked)
- 3 primary bar types run independently: 250-vol, 250-tick, 10-sec
- 10-sec bars RTH-filtered before simulation (9:30-16:00 ET)
- Data loaded via data_manifest.json paths
- Bar schema: 35 columns per bar_data_rot_schema.md

### Determinism (locked)
- Same config + same data -> identical results
- No randomness
- Strictly sequential bar processing
- No lookahead (entry-time only rule)

### Parameter Sweep (locked)
- StepDist in [1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0, 5.5, 6.0]
- Run on P1a only, all 3 bar types
- Best fixed step per bar type = that bar type's optimized baseline

### Claude's Discretion
- Internal class structure of RotationalSimulator (method decomposition)
- How to structure the parameter sweep runner (script vs function)
- Test strategy (unit tests for state machine logic)
- How to report baseline metrics (stdout, JSON, TSV)
- Whether to use dataclass or dict for state tracking

</decisions>

<specifics>
## Specific Ideas

- Simulator architecture per spec Section 6.1: RotationalSimulator with DataLoader, FeatureComputer, StateMachine, TradeLogger
- Simulation loop per spec Section 6.2: iterate all bars, check seed/reversal/add on each
- Price comparison uses bar Close price for distance calculations (matching C++ behavior)
- The existing rotational_engine.py handles data loading, config validation, holdout guard — simulator just needs to implement the run() method
- Instrument constants (tick_size=0.25, cost_ticks=3) from _config/instruments.md via shared/data_loader.py parse_instruments_md()
- RTH filter: keep bars where Time is between 09:30:00 and 16:00:00 ET (exclusive of 16:00:00, or per session definition in instruments.md which says RTH 09:30-16:15 ET)

</specifics>

<deferred>
## Deferred Ideas

- FeatureComputer.compute_dynamic_features() — only needed when hypotheses are active (Phase C)
- TrendDefenseSystem — separate subsystem built in Phase C
- Hypothesis-to-code mapping (H1-H41) — Phase C
- Structural mods (H13, H21, H22, H24) — Phase C
- Extended metrics col 25 JSON blob — will write to results but full schema populated in Phase C
- Cross-bar-type analysis (Phase 1b robustness classification) — Phase C

</deferred>

---

*Phase: 01-rotational-simulator-baseline*
*Context gathered: 2026-03-15 via PRD Express Path*
