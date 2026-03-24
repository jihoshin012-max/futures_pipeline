================================================================
DATA CORRECTION — APPLY TO ALL PIPELINE PROMPTS (0, 1a, 1b, 2, 3, 4)
================================================================

The zone touch pipeline is being re-run on warmup-enriched data. 
The charts now load 90+ days of history before each period starts, 
which gives V4 adequate zone warmup. This changes the touch 
population significantly.

⚠️ READ THIS FIRST before executing any pipeline prompt. These 
corrections override stale references in the prompt text.

================================================================
1. DATA FILE SUBSTITUTIONS
================================================================

All prompts reference old data files. Use the new files:

| Old reference | New file | Notes |
|--------------|----------|-------|
| NQ_merged_P1a.csv | NQ_ZTE_raw_P1.csv | Single P1 file, no P1a/P1b split |
| NQ_merged_P1b.csv | (removed) | Merged into NQ_ZTE_raw_P1.csv |
| NQ_merged_P2a.csv | NQ_ZTE_raw_P2.csv | Single P2 file |
| NQ_merged_P2b.csv | (removed) | Merged into NQ_ZTE_raw_P2.csv |
| NQ_ZRA_Hist_*.csv | (removed) | Replaced by ZTE |
| NQ_ZB4_signals_*.csv | (removed) | Replaced by ZTE |

Additional data files now available (for ray features if needed):
- NQ_ray_context_P1.csv / P2.csv
- NQ_ray_reference_P1.csv / P2.csv

⚠️ Wherever prompts say "concatenate P1a + P1b," simply load 
NQ_ZTE_raw_P1.csv directly. There is no split.

================================================================
2. TOUCH COUNT CORRECTIONS
================================================================

| Reference in prompts | Corrected value |
|---------------------|----------------|
| "4,701 touches" (P1) | ~3,278 touches |
| "P1a + P1b combined" | Single P1 (~3,278) |
| P2 touch count | ~3,537 (confirm after load) |

⚠️ The old P1 had 325 touches (cold-start, no zone warmup) 
which was later referenced as 4,701 in the v3.1 prompts. The 
new warmup-enriched P1 has ~3,278 touches. This is the correct 
population — it matches P2's density (~40-46 touches/day) and 
reflects what the live paper trading chart will look like.

================================================================
3. PERIOD STRUCTURE
================================================================

The prompts reference P1a/P1b/P2a/P2b (4-period split). 
For this re-run, use a 2-period structure:

| Period | Date range | Use |
|--------|-----------|-----|
| P1 | Sept 23 - Dec 14, 2024 (Z contract) | Calibration |
| P2 | Dec 15 - Mar 2, 2025 (H contract) | Validation |

⚠️ The P1a/P1b split within P1 was used for rule-based 
screening stability checks. With 3,278 P1 touches (adequate 
sample), this split is optional. If any prompt references 
P1a/P1b specific steps, run them on the full P1 instead.

⚠️ The P2a/P2b split for validation (Prompt 3) should be 
maintained — validating on two independent holdout halves 
is stronger than validating on one combined P2. Split P2 
at its date midpoint.

================================================================
4. COLUMN NAME MAPPING
================================================================

ZTE_raw uses different column names than the old merged files. 
Key mappings:

| Old column | ZTE_raw column | Notes |
|-----------|---------------|-------|
| SourceLabel | SourceLabel | Same |
| ZoneWidthTicks | ZoneWidthTicks | Same |
| CascadeState | CascadeState | Same |
| TouchPrice | TouchPrice | Same |
| Reaction | Reaction | Same |
| Penetration | Penetration | Same |
| DateTime | DateTime | Same |
| RotBarIndex | BarIndex | Name change |

⚠️ Verify column names on first load. If any feature 
computation fails due to column name mismatch, check the 
ZTE_raw schema (documented in the data registry).

================================================================
5. ZONE LIFECYCLE
================================================================

Prompts reference zone_lifecycle.csv built from V4_history. 
With ZTE consolidation, zone birth/death data is available 
in NQ_ZTE_raw_P1/P2.csv directly:

- Zone birth: first appearance of a ZoneID in the data
- Zone death: ZoneStatus = BROKEN (or absence from later bars)
- Active zone set: all zones with ZoneStatus = ACTIVE at 
  each bar

⚠️ If Prompt 0 or 1a requires zone_lifecycle.csv, rebuild 
it from ZTE_raw rather than loading the old file. The old 
file was built from V4_history which produces different zone 
detection than live V4 on the warmup-enriched chart.

================================================================
6. WHAT STAYS THE SAME
================================================================

- Methodology: baseline → screening → model building → 
  validation. Unchanged.
- Simulation specs: 250-vol bars, next-bar-open entry, 
  stop-first intra-bar, 3t cost model. Unchanged.
- Feature definitions (1-25): all computable from ZTE_raw 
  + bar data. Unchanged.
- Three scoring approaches (A-Cal, A-Eq, B-ZScore). Unchanged.
- Holdout discipline: P1 calibration, P2 validation, no 
  iteration after seeing P2. Unchanged.

================================================================
7. EXECUTION ORDER
================================================================

Run prompts in order: 0 → 1a → 1b → 2 → 3 → 4

After each prompt completes, review results before proceeding 
to the next. The review gates in each prompt still apply.

⚠️ The goal is to recalibrate the A-Cal model on the correct 
warmup-enriched population. The same 4 features (F10, F04, 
F01, F21) may or may not survive screening on the new data. 
Let the data decide — do not force the prior feature set.

Save results with suffix _v32 to distinguish from v31 outputs.
