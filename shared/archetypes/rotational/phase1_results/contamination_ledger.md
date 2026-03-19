# Contamination Ledger — Rotational Strategy V1.4

## Dataset Status

| Dataset | Date Range | Status | Details |
|---------|-----------|--------|---------|
| **P1 (Full)** | Sep 21 – Dec 14, 2025 | **CONTAMINATED** | Used for all Phase 1 calibration (SD/AD sweep, SeedDist, session window, ML/cap), Phase 2 optimization (SpeedRead threshold, feature discovery, risk mitigation), and stop parameter sweep. 59 RTH sessions. |
| **P2a** | Dec 18, 2025 – Jan 30, 2026 | **CONTAMINATED** | One-shot V1.4 validation (FAIL: NPF=0.958). Four-prong diagnostic performed (SR on/off, tail concentration, rolling variance, reversal chain). 28 sessions, 667 cycles. |
| **P2b** | Feb 2 – Mar 13, 2026 | **CONTAMINATED** | One-shot V1.4 + 4C validation (PASS: NPF=1.230). Final holdout consumed. 29 sessions, 995 cycles. |

## No Clean Holdout Remaining

All available out-of-sample data has been consumed. The next clean validation requires new data (P3).

## Chronological Use Log

| Step | Data Used | What Was Done |
|------|-----------|---------------|
| Phase 1 Step 1 | P1 | Simulator baseline with daily flatten |
| Phase 1 Step 1b | P1 250-tick | Zigzag sensitivity (5.25 pt validated) |
| Phase 1 Step 2 | P1 | SD×AD sweep: 30 fixed + 9 adaptive configs |
| Phase 1 Step 2b | P1 | ML/cap sweep: ML=1, cap=2 selected |
| Phase 1 Step 3 | P1 | SeedDist sweep: 15 pts fixed selected |
| Phase 1 Step 4 | P1 | Session window: 09:30-16:00 full RTH |
| Phase 1 Step 5 | P1 | Freeze: adaptive P90/P75, Sd=15, ML=1, cap=2 |
| Phase 2 P0-1 | P1 | Clock-time vs count window comparison |
| Phase 2 P0-2 | P1 | Session start 10:00 vs 09:30 → 10:00 selected |
| Phase 2 P0-3 | P1 | SpeedRead quintile by block diagnostic |
| Phase 2 Step 1 | P1 | SR threshold sweep (seed + reversal) |
| Phase 2 Step 2 | P1 | Rolling SR hysteresis → Roll50 Both>=48 selected |
| Phase 2 Step 3 | P1 | Feature discovery (17 features, none adopted) |
| Phase 2 Step 4 | P1 | Risk mitigation (4A/4B/4C evaluated, deferred) |
| Phase 2 Step 5 | P1 | V1.4 freeze: NPF=1.200, +20,919 ticks |
| P2a Validation | P2a | One-shot V1.4 → FAIL (NPF=0.958) |
| P2a Diagnostic | P2a + P1 | Four-prong failure analysis |
| Stop Sweep | P1 | 4A killed (60% recovery), 4C maxcw=2 selected |
| P2b Validation | P2b | One-shot V1.4 + 4C → PASS (NPF=1.230) |

## 250-Tick and SpeedRead Data

| Source File | Coverage | Used For |
|-------------|----------|----------|
| NQ_BarData_250tick_rot_P1.csv | Sep 21 – Dec 14, 2025 | Zigzag P90/P75 calibration, SpeedRead computation |
| NQ_BarData_250tick_rot_P2.csv | Dec 15, 2025 – Mar 13, 2026 | P2a/P2b zigzag + SpeedRead (P1 tail warm-up) |
| NQ_BarData_1tick_rot_P1.csv | Sep 21 – Dec 14, 2025 | Tick-level simulation (P1) |
| NQ_BarData_1tick_rot_P2.csv | Dec 17, 2025 – Mar 13, 2026 | Tick-level simulation (P2a + P2b) |
| speedread_250tick.parquet | Sep 21 – Dec 14, 2025 | P1 SpeedRead composite (verified match with Python) |
