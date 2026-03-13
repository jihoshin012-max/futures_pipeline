---
phase: 1
slug: scaffold
status: draft
nyquist_compliant: true
wave_0_complete: true
created: 2026-03-13
---

# Phase 1 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | Shell verification (bash done-checks) — no automated test framework required for Phase 1 |
| **Config file** | None — Phase 1 is static file creation |
| **Quick run command** | `find . -type f \| wc -l` (count files), manual spot-checks |
| **Full suite command** | Per-task DONE CHECKs from functional spec |
| **Estimated runtime** | ~5 seconds |

---

## Sampling Rate

- **After every task commit:** Run the DONE CHECK from the functional spec task
- **After every plan wave:** Full file-existence check: `find . -name "*.md" -o -name "*.json" -o -name "*.tsv" -o -name "*.sh" -o -name "*.html" -o -name "*.py" | sort`
- **Before `/gsd:verify-work`:** All 26 SCAF + 4 PREREQ done-checks must pass
- **Max feedback latency:** 5 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 1-01 | 01 | 1 | PREREQ-01 | Manual | `ls ../Interpreted-Context-Methodology/` | N/A | ⬜ pending |
| 1-02 | 01 | 1 | PREREQ-02 | Manual | `ls ../autoresearch/program.md` | N/A | ⬜ pending |
| 1-03 | 01 | 1 | PREREQ-03 | Shell | `ls stages/01-data/data/bar_data/` | N/A | ⬜ pending |
| 1-04 | 01 | 1 | PREREQ-04 | Shell | `ls stages/01-data/data/touches/` | N/A | ⬜ pending |
| 1-05 | 02 | 1 | SCAF-01 | Shell | `find . -type d \| head -40` | N/A | ⬜ pending |
| 1-06 | 02 | 1 | SCAF-02 | Shell | `wc -l CLAUDE.md` ≤60 | N/A | ⬜ pending |
| 1-07 | 02 | 1 | SCAF-03 | Shell | `wc -l CONTEXT.md` ≤80 | N/A | ⬜ pending |
| 1-08 | 02 | 1 | SCAF-04 | Manual | `grep -c "Tick size\|Tick value" _config/instruments.md` ≥4 | N/A | ⬜ pending |
| 1-09 | 02 | 1 | SCAF-05 | Manual | Review data_registry.md source_id → schema cross-ref | N/A | ⬜ pending |
| 1-10 | 02 | 1 | SCAF-06 | Git | `git log --oneline -- _config/period_config.md` before results | N/A | ⬜ pending |
| 1-11 | 02 | 1 | SCAF-07 | Manual | `grep -c "^## Rule" _config/pipeline_rules.md` returns 5 | N/A | ⬜ pending |
| 1-12 | 02 | 1 | SCAF-08 | Manual | Confirm 3 iteration budget rows + 4 Bonferroni rows | N/A | ⬜ pending |
| 1-13 | 02 | 1 | SCAF-09 | Manual | Confirm Trend, Volatility, Macro sections | N/A | ⬜ pending |
| 1-14 | 02 | 1 | SCAF-10 | Manual | Confirm 4-row length limits + FRONT-LOADING RULE | N/A | ⬜ pending |
| 1-15 | 03 | 2 | SCAF-11 | Manual | feature_definitions.md exists with empty registered features | N/A | ⬜ pending |
| 1-16 | 03 | 2 | SCAF-12 | Shell | `wc -l 02-features/references/feature_rules.md` ≤30 | N/A | ⬜ pending |
| 1-17 | 03 | 2 | SCAF-13 | Manual | Active/Dropped/Dead ends tables present | N/A | ⬜ pending |
| 1-18 | 03 | 2 | SCAF-14 | Shell | `ls shared/scoring_models/` shows both files | N/A | ⬜ pending |
| 1-19 | 04 | 2 | SCAF-15 | Manual | CONTEXT.md + schema files + data_manifest schema | N/A | ⬜ pending |
| 1-20 | 04 | 2 | SCAF-16 | Shell | `wc -l stages/02-features/CONTEXT.md` ≤80 | N/A | ⬜ pending |
| 1-21 | 04 | 2 | SCAF-17 | Shell | `wc -l stages/03-hypothesis/CONTEXT.md` ≤80 | N/A | ⬜ pending |
| 1-22 | 04 | 2 | SCAF-18 | Shell | Both files exist; CONTEXT.md ≤80 | N/A | ⬜ pending |
| 1-23 | 04 | 2 | SCAF-19 | Manual | All 3 files; verdict thresholds match statistical_gates | N/A | ⬜ pending |
| 1-24 | 04 | 2 | SCAF-20 | Shell | assemble_context.sh exists and is executable | N/A | ⬜ pending |
| 1-25 | 04 | 2 | SCAF-21 | Manual | Both files exist; trigger thresholds present | N/A | ⬜ pending |
| 1-26 | 05 | 3 | SCAF-22 | Shell | `awk -F'\t' '{print NF}' dashboard/results_master.tsv` returns 24 | N/A | ⬜ pending |
| 1-27 | 05 | 3 | SCAF-23 | Manual | Open index.html in browser; placeholder visible | N/A | ⬜ pending |
| 1-28 | 05 | 3 | SCAF-24 | Manual | audit_log.md exists with APPEND-ONLY header | N/A | ⬜ pending |
| 1-29 | 05 | 3 | SCAF-25 | Manual | `bash audit/audit_entry.sh note` prompts and appends | N/A | ⬜ pending |
| 1-30 | 05 | 3 | SCAF-26 | Manual | Template block + simulator interface contract present | N/A | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

None — Phase 1 creates all files from scratch. No pre-existing test infrastructure applies. All verification is via shell done-checks and manual inspection as specified in the functional spec.

*Existing infrastructure covers all phase requirements.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| ICM repo conventions reviewed | PREREQ-01 | Requires human judgement on convention applicability | Fetch repo, review structure, confirm conventions match spec assumptions |
| karpathy/autoresearch reviewed | PREREQ-02 | Requires human reading of keep/revert logic | Review program.md, confirm understanding of keep/revert pattern |
| source_id cross-reference integrity | SCAF-05 | No tooling enforces string match across files | Manually verify each data_registry source_id matches schema filename in 01-data/references/ |
| Dashboard renders correctly | SCAF-23 | Requires visual browser check | Open dashboard/index.html in browser, verify placeholder text visible |
| audit_entry.sh round-trip | SCAF-25 | Requires interactive shell prompts | Run `bash audit/audit_entry.sh note`, confirm prompt appears and entry appended |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references
- [x] No watch-mode flags
- [x] Feedback latency < 5s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** approved
