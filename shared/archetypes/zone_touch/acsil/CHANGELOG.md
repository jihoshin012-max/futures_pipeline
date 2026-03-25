# ACSIL Study Chain — Change Log

Every modification to any study in this directory gets an entry.
Newest first. Update this file with EVERY commit that touches
a .cpp, .h, or SC setting.

## 2026-03-24 — ATEAM_ZONE_TOUCH_V32 autotrader built

| File | Change |
|------|--------|
| Added: ATEAM_ZONE_TOUCH_V32.cpp | v3.2 unified autotrader — dual-model (A-Eq M1 + B-ZScore M2) waterfall, 47 inputs, partial exits with BE, circuit breakers, CSV logging, visual display |
| Added: zone_touch_v32_inputs.txt | Default input values + feature-to-ZTE mapping reference |
| Updated: STUDY_CHAIN_REFERENCE.md | Section 4c updated from "TO BE BUILT" to implemented. Added to Active Studies table. |

Impact: New study added. No existing studies modified. Pending replication gate
(P1 comparison) before paper trading. Reads ZTE SignalStorage unchanged (magic
0x5A425634). Scoring models inlined from feature_config_v32.json,
scoring_model_aeq_v32.json, scoring_model_bzscore_v32.json.

## 2026-03-23 — Throughput re-examination CONFIRMED

- All 6 throughput conclusions hold on correct 77-trade population
- Signal density sparser (median gap 756 vs 194 bars, 0% clustering)
- Baseline quality higher (WR 92.2%, PF 11.96)
- ZR beats fixed by 40.8% total PnL; dynamic T2 has 0 triggers
- Added: throughput_reexamination.py, throughput_reexamination.md

## 2026-03-23 — C++ replication gate PASSED

- **ZONEREL:** 77/77 match on P1 (C++ vs Python replication harness)
- **FIXED:** 85/85 match on P1
- 7 bugs fixed: P2/P1 path mismatch, column mapping, TIMECAP
  off-by-one, rounding method, CT entry mechanism, inline
  constants, answer key source (pre-scored → replication harness)
- Answer keys regenerated from replication harness (authoritative)
- Old throughput answer keys (.bak) removed
- Tags updated: v1.0-pre-merge, v3.0-pre-merge
- Added: generate_p1_answer_keys.py
- Added: p1_replication_answer_key_fixed.csv, p1_replication_answer_key_zr.csv
- Added: p1_replication_skipped_fixed.csv, p1_replication_skipped_zr.csv

## 2026-03-23 — Throughput analysis complete

- Tested 20+ exit configurations across 12 analysis sections
- Compared zone-relative vs fixed exits with full sequential
  freed signal simulation (including kill-switch in cascade)
- Current ZR 2-leg confirmed optimal on both P1 and P2
- Dynamic T2 exit (only ACTIONABLE finding) deferred to v3.1
- No parameter changes — exit config frozen for C++ test mode
- Added: throughput_analysis_part1.md, throughput_analysis_part2.md
- Added: p1_twoleg_answer_key_zr.csv, p1_twoleg_answer_key_fixed.csv
- Added: p1_twoleg_skipped_signals_zr.csv, p1_twoleg_skipped_signals_fixed.csv
- Added: throughput_prompt_1_v2.md, throughput_prompt_2_v2.md

## 2026-03-22 — V4 MaxVPProfiles default (Commit 5)

| File | Change |
|------|--------|
| SupplyDemandZonesV4.cpp | MaxVPProfiles default 50 → 0, MaxRays default 50 → 0 |

Impact: New V4 instances default to unlimited VP profiles and rays.
No logic change — only default values.

## 2026-03-22 — sc.GraphName + Version Headers (Commit 4)

| File | Change |
|------|--------|
| All 5 .cpp files | Added sc.GraphName with [version] tag |
| All 6 .cpp/.h files | Added STUDY VERSION LOG header block |

Impact: Display names on SC chart now show version. No logic changes.

## 2026-03-22 — VP Ray Investigation (Commit 3)

| File | Change |
|------|--------|
| ZoneReactionAnalyzer.cpp | v3.1 -> v3.2: VP proximity filter |
| ZoneBounceSignalsV4_aligned.cpp | v3.1 -> v3.2: VP proximity filter |
| V4 MaxVPProfiles setting | 50 -> 0 (=500) |
| Added: VP_RAY_INVESTIGATION.md | Root cause + fix documentation |
| Added: ZoneReactionAnalyzer_v31.cpp | Backup |
| Added: ZoneBounceSignalsV4_aligned_v31.cpp | Backup |

Impact: VP fields only. Scoring model, zones, touches unaffected.

## 2026-03-22 — Replication Gate (Commit 2)

| File | Change |
|------|--------|
| Added: replication_harness.py | P2 trade verification |
| Added: p2_twoleg_answer_key.csv | 91 trades, 2-leg exits |
| Added: replication_gate_results.md | 79/79 PASS |

Impact: Verification only. No study code changed.

## 2026-03-22 — Autotrader Build (Commit 1)

| File | Change |
|------|--------|
| Added: ATEAM_ZONE_BOUNCE_V1.cpp | New autotrader study |
| Added: zone_bounce_config.h | P1-frozen config |
| Added: STUDY_CHAIN_REFERENCE.md | Study chain documentation |
| Snapshot: SupplyDemandZonesV4.cpp | v3.1 |
| Snapshot: SupplyDemandZonesV4_history.cpp | v3.1 |
| Snapshot: ZoneReactionAnalyzer.cpp | v3.1 |
| Snapshot: ZoneBounceSignalsV4_aligned.cpp | v3.1 |
| Added: scoring_model_acal.json | P1-frozen weights |
| Added: feature_config.json | P1-frozen bin edges |

Impact: New study added. No existing studies modified.

## Template for future entries

## YYYY-MM-DD — [Description]

| File | Change |
|------|--------|
| filename.cpp | what changed |

Impact: [what's affected, what's not]
