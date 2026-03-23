# NQ Zone Touch — Session Transfer

> **Last updated:** 2026-03-23
> **Current state:** C++ replication PASSED. Throughput CONFIRMED. Visual spot-check next.

---

## IMMEDIATE NEXT STEPS

### ~~1. Throughput Re-examination~~ — DONE

All 6 conclusions CONFIRMED on 77-trade population. Signal density sparser
(median gap 756 bars, 0% clustering). Baseline quality higher (WR 92%, PF 12.0).
See `output/throughput_reexamination.md`.

### 2. Visual Spot-Check (REQUIRED before paper trading)

Pick 10 trades from the 77 ZONEREL replication answer key. Verify on Sierra Chart:
- Zone exists at the expected price level
- Touch bar matches the merged CSV datetime
- Entry price correct (CT: limit fill, WT: next bar open)
- Score plausible (check features against merged CSV row)
- Exit at correct bar/price (stop, target, or time cap)

### 3. ZRA+ZB4 Consolidation

Tags `v1.0-pre-merge` and `v3.0-pre-merge` are set. Both C++ tests pass.
Ready to merge ZRA+ZB4 into a single study chain, then re-test both versions
to confirm no regression.

### 4. Paper Trading

After steps 1-3 complete: paper trade P3 (Mar-Jun 2026).
Both FIXED and ZONEREL variants. Weekly review cadence (Friday summaries).

---

## Key Artifacts

| File | Purpose |
|------|---------|
| `acsil/ATEAM_ZONE_BOUNCE_FIXED.cpp` | FIXED autotrader (v1.0), tagged v1.0-pre-merge |
| `acsil/ATEAM_ZONE_BOUNCE_ZONEREL.cpp` | ZONEREL autotrader (v3.0), tagged v3.0-pre-merge |
| `stages/.../generate_p1_answer_keys.py` | Generates P1 answer keys for both variants |
| `stages/.../output/p1_twoleg_answer_key_*.csv` | C++ test baselines (authoritative) |
| `stages/.../output/p1_replication_answer_key_*.csv` | Replication harness output (reference) |
| `docs/NQ_Zone_Audit_Trail.md` | Full pipeline audit trail |
| `acsil/CHANGELOG.md` | ACSIL study change log |

## C++ Test Mode Quick Reference

1. SC Input[14] = Yes (CSV Test Mode), Input[15] = `C:\Projects\pipeline\stages\01-data\output\zone_prep\`
2. Recalc study on any NQ chart
3. Check SC Message Log for "Complete"
4. Report at `E:\SierraChart\SierraChartInstance_4\Data\ATEAM_CSV_TEST_[FIXED|ZONEREL]_report.txt`
