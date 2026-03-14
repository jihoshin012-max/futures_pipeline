---
last_reviewed: 2026-03-13
reviewed_by: Ji
---
# Stage 01: Data Foundation
## YOUR TASK: Validate and register data. Do not modify any _config/ files.

| | |
|---|---|
| **Inputs** | Raw source files (archetype touch data, bar data) in 01-data/data/ |
| **Process** | Validate schemas, check date coverage, discover bar offsets, register periods |
| **Outputs** | data_manifest.json, validation_report.md |
| **Human checkpoint** | Review validation_report.md before any downstream stage runs |

## CONSTRAINT
You do not run backtests. You do not touch _config/. Your only outputs are data_manifest.json
and validation_report.md.

## VALIDATION CHECKLIST
- [ ] Schema check: required columns present in all CSVs
- [ ] Date coverage: P1 and P2 fully covered, no gaps
- [ ] Row counts: logged in data_manifest.json
- [ ] Bar offset: verified and documented
- [ ] Label columns: spot-check 10 rows against source files (if archetype uses derived labels)
- [ ] regime_labels.csv: exists, covers both P1 and P2 date ranges, not all-one-state
- [ ] data_manifest.json: all registered periods present, all sources PASS, bar_offset verified

## NEW DATA TYPES
When a new archetype requires data not in data_registry.md:
1. Add schema doc to 01-data/references/{format}_schema.md
2. Add validation block to Stage 01 validation script for that schema
3. Add row to data_registry.md
4. Re-run Stage 01 — new source must pass before archetype intake proceeds
Stage 01 validation is NOT automatic for new formats — human writes the schema and validation block.
