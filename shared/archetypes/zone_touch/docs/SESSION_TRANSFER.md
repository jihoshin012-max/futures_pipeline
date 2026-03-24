# NQ Zone Touch — Session Transfer

> **Last updated:** 2026-03-24
> **Current state:** Risk mitigation investigation COMPLETE. Exit structure and
> position sizing frozen. Ready for C++ implementation update.

---

## IMMEDIATE NEXT STEPS

### ~~1. Throughput Re-examination~~ — DONE

All 6 conclusions CONFIRMED on 77-trade population. Signal density sparser
(median gap 756 bars, 0% clustering). Baseline quality higher (WR 92%, PF 12.0).
See `output/throughput_reexamination.md`.

### ~~2. Risk Mitigation Investigation~~ — DONE (2026-03-24)

Entry/exit/sizing investigation complete. See `output/risk_mitigation_investigation_v32.md`.

**Frozen modifications (all P2-validated):**
- M1: Partial exits — 1+2 (1ct@60t + 2ct@120t, BE on runner). P2 PF 8.25 (up from 6.26).
  Alternative: 1+1+1 (1ct@60t + 1ct@120t + 1ct@180t, BE). P2 PF 8.31.
- M2: Stop tightened to max(1.3xZW, 100t). P2 PF 4.18 (up from 4.10).
- M2: Position sizing by zone width — 3ct ZW<150t, 2ct 150-250t, 1ct 250t+.

**Rejected (with data):**
- Zone-fixed stop/target levels (PF jump was single-trade artifact)
- Deeper entries (fill rate too low, selection bias in missed trades)
- BE stops (destroy WR, fail P2)
- M2 target reduction (1.0xZW confirmed optimal)
- M1 stop reduction (PF drops at every level)

### 3. Visual Spot-Check (REQUIRED before paper trading)

Pick 10 trades from the 77 ZONEREL replication answer key. Verify on Sierra Chart:
- Zone exists at the expected price level
- Touch bar matches the merged CSV datetime
- Entry price correct (CT: limit fill, WT: next bar open)
- Score plausible (check features against merged CSV row)
- Exit at correct bar/price (stop, target, or time cap)

### 4. C++ Autotrader Update

Update ATEAM_ZONE_BOUNCE autotrader to implement:
- M1 multileg exits (1+2 or 1+1+1 config, with stop-to-BE after T1)
- M2 stop formula change (1.3xZW floor 100, was 1.5xZW floor 120)
- M2 contract sizing by ZoneWidthTicks input
- EntryOffset parameter (default 0, configurable for future experimentation)

### 5. Paper Trading

After steps 3-4 complete: paper trade P3 (Mar-Jun 2026).
Both FIXED and ZONEREL variants with mitigated exits.
Weekly review cadence (Friday summaries).

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
