# ACSIL Study Chain — Change Log

Every modification to any study in this directory gets an entry.
Newest first. Update this file with EVERY commit that touches
a .cpp, .h, or SC setting.

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
