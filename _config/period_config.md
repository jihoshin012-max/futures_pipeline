# Period Configuration
last_reviewed: 2026-03-13
# NEVER edit this file mid-run. Only update between complete pipeline runs.
# After editing: re-run Stage 01 validation. data_manifest.json is regenerated automatically.

## Active Periods

| period_id | role | start_date | end_date   | notes                        |
|-----------|------|------------|------------|------------------------------|
| P1        | IS   | 2025-09-16 | 2025-12-14 | Calibration — used freely    |
| P2        | OOS  | 2025-12-15 | 2026-03-02 | Holdout — one-shot only      |

## Rules (do not change)
- IS periods: used for feature calibration, hypothesis search, parameter optimization
- OOS periods: used for final one-shot validation only — never re-run after first use
- A period cannot be both IS and OOS in the same run
- OOS periods become IS when a new OOS period is designated (see Rolling Forward below)

## Rolling Forward (when P3 arrives ~Jun 2026)
1. Add P3 row (role: OOS)
2. Change P2 role to IS (after its one-shot OOS test is complete)
3. Re-run Stage 01 validation
4. No code changes needed

## Example — end of Q2 2026 (P3 arrives)

Before:
| P1 | IS  | 2025-09-16 | 2025-12-14 |
| P2 | OOS | 2025-12-15 | 2026-03-02 |

After (P2 tested, P3 arrives):
| P1 | IS  | 2025-09-16 | 2025-12-14 |
| P2 | IS  | 2025-12-15 | 2026-03-02 | promoted after one-shot OOS test |
| P3 | OOS | 2026-03-03 | 2026-06-30 | new holdout                      |

No code changes. Stage 01 re-reads this file and updates data_manifest.json automatically.

## Internal Replication Sub-periods (Rule 4)
For new hypotheses: P1a = 2025-09-16 to 2025-10-31 (calibrate)
                   P1b = 2025-11-01 to 2025-12-14 (replicate)
Any strategy calibrated on full P1 before Rule 4 was introduced is grandfathered — its
existing P2 result stands. Rule 4 applies to all new hypotheses.
