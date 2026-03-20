# Build Skill: NQ Fractal Structure Monitor

## OBJECTIVE

Create a reusable skill in the pipeline that runs the NQ fractal structure analysis on demand — quarterly, or whenever new data is available. The skill should:

1. Accept a date range and data path as inputs
2. Run the full four-part fractal analysis (distributions, decomposition, power law, time-of-day)
3. Compare results against a stored baseline (the current Sept 2025 – Mar 2026 findings)
4. Flag any structural drift that could invalidate strategy parameters
5. Produce a standardized report with drift verdicts

This is the monitoring layer that ensures the six structural facts underpinning the rotation strategy remain valid over time.

## LOCATION

Create the skill at: `C:\Projects\pipeline\stages\01-data\skills\fractal_monitor\`

Structure:
```
fractal_monitor/
├── SKILL.md                     # Skill definition and usage guide
├── scripts/
│   ├── run_fractal_analysis.py  # Main entry point — runs all 4 parts
│   ├── zigzag.py                # Reusable zig-zag implementation (numba-accelerated)
│   ├── part1_distributions.py   # Multi-threshold swing distributions
│   ├── part2_decomposition.py   # Hierarchical decomposition + completion rates + half-block
│   ├── part3_powerlaw.py        # Power law tail analysis
│   ├── part4_timeofday.py       # Time-of-day structure (RTH only)
│   ├── compare_baseline.py      # Drift detection against stored baseline
│   └── generate_report.py       # Standardized markdown + charts output
├── baseline/
│   ├── baseline_2025Q4_2026Q1.json  # Current findings as structured data (see below)
│   └── README.md                     # Documents what each baseline field means
└── output/                      # Generated reports go here (gitignored)
```

## BASELINE DATA TO STORE

⚠️ **The baseline JSON must capture all six structural facts in machine-readable form. This is the reference point for all drift detection.**

Extract the following from the current fractal_summary.md and analysis CSVs:

```json
{
  "metadata": {
    "date_range": "2025-09-21 to 2026-03-13",
    "data_source": "NQ_BarData_1tick_rot",
    "total_rows": 60900000,
    "created": "2026-03-20"
  },
  "fact1_self_similarity": {
    "thresholds": [3, 5, 7, 10, 15, 25, 50],
    "rth": {
      "mean_over_threshold": [2.10, 2.06, 2.03, 2.01, 1.99, 1.98, 1.94],
      "median_over_threshold": [1.73, 1.76, 1.71, 1.70, 1.70, 1.68, 1.67],
      "p90_over_threshold": [3.60, 3.44, 3.36, 3.30, 3.30, 3.23, 3.13],
      "skewness": [1.93, 1.89, 1.92, 1.89, 1.97, 1.90, 1.89],
      "median_p90_ratio": [0.488, 0.507, 0.511, 0.515, 0.515, 0.520, 0.533]
    }
  },
  "fact2_completion_degradation": {
    "rth": {
      "25_10": {
        "retracement_0": 100.0,
        "retracement_1": 79.7,
        "retracement_2": 64.1,
        "retracement_3": 56.0,
        "retracement_4": 50.7,
        "retracement_5plus": 45.2,
        "sample_counts": [2346, 2170, 1686, 1192, 872, 2004]
      },
      "50_25": {
        "retracement_0": 100.0,
        "retracement_1": 76.5,
        "retracement_2": 55.9,
        "retracement_3": 48.3,
        "retracement_4": 50.3,
        "retracement_5plus": 51.7,
        "sample_counts": [950, 629, 370, 230, 143, 211]
      },
      "15_7": {
        "retracement_0": 100.0,
        "retracement_1": 76.8,
        "retracement_2": 58.1,
        "retracement_3": 49.6,
        "retracement_4": 47.8,
        "retracement_5plus": 43.6,
        "sample_counts": [9651, 6625, 4578, 2951, 1803, 2904]
      }
    }
  },
```

📌 **Mid-block reminder: The JSON above and below is ONE object — shown in two blocks for readability. Combine them into a single baseline JSON file. Every field must be populated from the original fractal_summary.md and analysis CSVs. Include ALL 6 parent-child pairs for fact2, and ALL 3 sessions (RTH/ETH/Combined). The abbreviated example above shows only 3 pairs and only RTH for space — the real baseline must have all 6 pairs × 3 sessions.**

```json
  "fact3_parent_child_ratio": {
    "rth": {
      "pairs": ["50_25", "25_15", "25_10", "15_7", "10_5", "7_3"],
      "ratios": [2.0, 1.67, 2.5, 2.14, 2.0, 2.33],
      "completion_at_1_retrace": [76.5, 68.4, 79.7, 76.8, 73.5, 75.8]
    }
  },
  "fact4_waste": {
    "rth": {
      "pairs": ["50_25", "25_10", "15_7", "10_5", "7_3"],
      "waste_pct": [42.0, 51.7, 44.1, 38.9, 43.8]
    }
  },
  "fact5_time_stability": {
    "rth_completion_1retrace_spread_pp": {
      "parent_15": 7.4,
      "parent_25": 11.9,
      "parent_50": 20.3
    }
  },
  "fact6_halfblock_curve": {
    "rth_25_10": {
      "progress_pct": [10, 20, 30, 40, 50, 60, 70, 80, 90, 100],
      "completion_pct": [69.8, 69.8, 69.8, 69.8, 74.7, 79.9, 85.6, 90.2, 95.1, 100.0]
    }
  }
}
```

⚠️ **Include all parent-child pairs in fact2, not just the three shown above. I abbreviated for space. The full baseline must have all 6 pairs (50→25, 25→15, 25→10, 15→7, 10→5, 7→3) for RTH, ETH, and Combined.**

## DRIFT DETECTION LOGIC

The `compare_baseline.py` script compares new quarterly results against the stored baseline. For each structural fact, define thresholds:

**Fact 1 (Self-Similarity):**
- STABLE: median/threshold ratio within ±0.10 of baseline at each scale
- DRIFT: ratio shifts by 0.10-0.20 at 3+ thresholds
- BREAK: ratio shifts by >0.20 at any threshold, OR skewness changes by >0.5

**Fact 2 (Completion Degradation):**
- STABLE: completion rate at 1 retracement within ±5pp of baseline for all pairs
- DRIFT: 5-10pp shift for any pair
- BREAK: >10pp shift for any pair, OR the 50% crossover point moves by ≥2 retracement levels

⚠️ **Fact 2 is the most important drift indicator. A 10pp drop in completion at 1 retracement directly erodes the martingale's structural backing. Flag this prominently.**

**Fact 3 (Parent/Child Ratio):**
- STABLE: best-performing ratio stays within same pair (currently 25→10)
- DRIFT: a different pair takes the lead by >3pp
- BREAK: no pair shows completion >70% at 1 retracement

**Fact 4 (Waste):**
- STABLE: waste% within ±5pp of baseline
- DRIFT: 5-10pp shift
- BREAK: >10pp shift (market becoming significantly more or less "noisy")

**Fact 5 (Time Stability):**
- STABLE: spread remains within 5pp of baseline
- DRIFT: spread increases by 5-15pp (time-of-day matters more now)
- BREAK: spread >30pp (the fractal structure is now time-dependent)

**Fact 6 (Half-Block Curve):**
- STABLE: completion at 60% progress within ±5pp of baseline (currently 79.9%)
- DRIFT: 5-10pp shift
- BREAK: >10pp shift, OR the curve shape changes (e.g., no longer accelerates past 50%)

⚠️ **Reminder: All six drift thresholds above must be implemented in `compare_baseline.py`. Each fact gets a STABLE/DRIFT/BREAK verdict. The overall report verdict is: ALL_STABLE (all 6 stable), DRIFT_DETECTED (any drift, no breaks), or STRUCTURE_BREAK (any break). Fact 2 is the highest-priority check.**

## REPORT OUTPUT

`generate_report.py` produces:

1. **`fractal_quarterly_YYYY_QN.md`** — Markdown report with:
   - Date range and data summary
   - Six-fact comparison table: baseline vs current, with STABLE/DRIFT/BREAK verdict per fact
   - Detailed tables for any DRIFT or BREAK findings
   - Charts overlaying current vs baseline distributions (Part 1) and completion curves (Part 2)
   - Overall verdict: ALL_STABLE / DRIFT_DETECTED / STRUCTURE_BREAK
   - If DRIFT or BREAK: specific recommendations (e.g., "re-run strategy sweep with updated parameters")

2. **`fractal_quarterly_YYYY_QN.json`** — Machine-readable results in same schema as baseline. This becomes the new baseline if the user approves.

**Baseline versioning:** Keep ALL historical baselines in the `baseline/` directory. Name them `baseline_YYYYQN_YYYYQN.json` by the date range they cover. The `compare_baseline.py` script should compare against TWO references:
   - **Original baseline** (`baseline_2025Q4_2026Q1.json`) — always compare against the founding analysis. This detects long-term structural drift.
   - **Previous quarter** (most recent baseline file) — detects short-term changes.
   
   The report should show both comparisons. A fact can be STABLE vs previous quarter but DRIFT vs original — that means gradual shift over multiple quarters.

3. **Charts as PNG files** (same as original analysis)

📌 **Reminder: The skill's core purpose is comparing NEW quarterly data against the STORED baseline to detect structural drift. The drift thresholds above (STABLE/DRIFT/BREAK) determine whether strategy parameters remain valid. Fact 2 (completion degradation) is the highest-priority indicator — a >10pp drop at 1 retracement is a BREAK that should trigger strategy re-evaluation.**

## ENTRY POINT USAGE

```bash
# Run quarterly analysis on new data
python run_fractal_analysis.py \
  --data-path "C:\Projects\pipeline\stages\01-data\data\bar_data\tick\" \
  --date-range "2026-03-14 to 2026-06-13" \
  --session RTH \
  --baseline baseline/baseline_2025Q4_2026Q1.json \
  --output output/fractal_quarterly_2026_Q2/

# Run without baseline comparison (first-time or standalone)
python run_fractal_analysis.py \
  --data-path "..." \
  --date-range "..." \
  --session RTH \
  --output output/

# Run specific parts only
python run_fractal_analysis.py \
  --data-path "..." \
  --parts 1,2 \
  --output output/
```

## IMPLEMENTATION NOTES

⚠️ **The zig-zag implementation must match the one used in the original analysis EXACTLY. Port the numba-accelerated zig-zag from the fractal_01_prepare.py and fractal_02_analyze.py scripts that were just built. Do NOT rewrite from scratch — copy and refactor into zigzag.py.**

📌 **The Part 2 completion rate MUST use the child-walk method (tracking cumulative displacement, capturing both successes AND failures). Do NOT use the parent zig-zag overlay method. This was the critical methodological distinction in the original analysis. See fractal_strategy_hypothesis_v3.md, Phase 0 section, for the exact method description.**

📌 **Session boundary handling: RESET zig-zag state at session boundaries. An overnight gap is NOT a swing. See the original fractal_decomposition_prompt.md SESSION SPLITS section for the exact rules.**

**Data handling:**
- 1-tick data may be tens of millions of rows. Use chunked reading, efficient dtypes (float32), process sessions sequentially.
- Load only Date, Time, and Last (Close) columns. Ignore all indicator columns.

**Dependency on existing scripts:**
- The fractal_01_prepare.py and fractal_02_analyze.py scripts from the fractal_discovery directory contain working, tested implementations of all four parts. The skill should refactor these into modular, reusable components — not rewrite the logic.

## SELF-CHECK BEFORE FINISHING

- [ ] SKILL.md written with proper frontmatter (name, description)
- [ ] All 4 parts implemented as separate modules
- [ ] Zig-zag implementation ported from existing scripts (not rewritten)
- [ ] Child-walk method used for completion rates (NOT parent zig-zag overlay)
- [ ] Session boundary reset implemented
- [ ] Baseline JSON created with ALL 6 pairs, ALL 3 sessions, ALL 6 facts
- [ ] Drift detection thresholds implemented for all 6 facts
- [ ] Report generation produces both .md and .json
- [ ] Entry point CLI works with --data-path, --date-range, --session, --baseline, --output, --parts
- [ ] Script runs successfully on the existing 1-tick data as a validation test
- [ ] Output matches the original fractal_summary.md results (this IS the calibration gate for the skill)
