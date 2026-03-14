# Period Configuration
last_reviewed: 2026-03-13
# NEVER edit this file mid-run. Only update between complete pipeline runs.
# After editing: re-run Stage 01 validation. data_manifest.json is regenerated automatically.

## Active Periods

| period_id | archetype  | role | start_date | end_date   | notes                     |
|-----------|------------|------|------------|------------|---------------------------|
| P1        | zone_touch | IS   | 2025-09-16 | 2025-12-14 | Calibration — used freely |
| P2        | zone_touch | OOS  | 2025-12-15 | 2026-03-02 | Holdout — one-shot only   |
| P1        | rotational | IS   | 2025-09-21 | 2025-12-14 | Calibration — used freely |
| P2        | rotational | OOS  | 2025-12-15 | 2026-03-13 | Holdout — one-shot only   |

## Rules (do not change)
- IS periods: used for feature calibration, hypothesis search, parameter optimization
- OOS periods: used for final one-shot validation only — never re-run after first use
- A period cannot be both IS and OOS in the same run
- OOS periods become IS when a new OOS period is designated (see Rolling Forward below)

## Rolling Forward (when P3 arrives ~Jun 2026)
1. Add P3 rows (one per archetype, or use archetype='*' wildcard if boundary is shared)
2. Change P2 rows to role IS (after their one-shot OOS test is complete)
3. Re-run Stage 01 validation
4. No code changes needed

## Example — end of Q2 2026 (P3 arrives)

Before:
| P1 | zone_touch | IS  | 2025-09-16 | 2025-12-14 |
| P2 | zone_touch | OOS | 2025-12-15 | 2026-03-02 |
| P1 | rotational | IS  | 2025-09-21 | 2025-12-14 |
| P2 | rotational | OOS | 2025-12-15 | 2026-03-13 |

After (P2 tested, P3 arrives):
| P1 | zone_touch | IS  | 2025-09-16 | 2025-12-14 |
| P2 | zone_touch | IS  | 2025-12-15 | 2026-03-02 | promoted after one-shot OOS test |
| P3 | *          | OOS | 2026-03-03 | 2026-06-30 | new holdout (all archetypes)      |
| P1 | rotational | IS  | 2025-09-21 | 2025-12-14 |
| P2 | rotational | IS  | 2025-12-15 | 2026-03-13 | promoted after one-shot OOS test |

No code changes. Stage 01 re-reads this file and updates data_manifest.json automatically.

## Internal Replication Sub-periods (Rule 4)
p1_split_rule: midpoint
# Stage 01 computes P1a/P1b dynamically from P1 start/end using this rule.
# Options: midpoint | 60_40 | fixed_days:<N>
#   midpoint       — P1a = first half of P1, P1b = second half (default)
#   60_40          — P1a = first 60% of P1, P1b = last 40%
#   fixed_days:<N> — P1a = first N days, P1b = remainder
# When P1 rolls forward the split auto-updates — no manual date editing.
# Current computed split per archetype (informational — Stage 01 writes resolved dates
# into data_manifest.json):
#   zone_touch: P1a = 2025-09-16 to 2025-10-31 | P1b = 2025-11-01 to 2025-12-14
#   rotational: P1a = 2025-09-21 to 2025-11-02 | P1b = 2025-11-03 to 2025-12-14
replication_gate: flag_and_review
# Options: hard_block | flag_and_review
#   hard_block      — P1b fail = NO verdict, do not advance to P2
#   flag_and_review — P1b fail = WEAK_REPLICATION flag, human decides
# flag_and_review is recommended when n_trades_p1b < 50.
# hypothesis_generator.py reads this value at runtime.
Any strategy calibrated on full P1 before Rule 4 was introduced is
grandfathered — its existing P2 result stands. Rule 4 applies to all
new hypotheses.
