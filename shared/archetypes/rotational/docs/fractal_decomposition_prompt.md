# NQ Fractal Structure Discovery — 1T Data Analysis

## OBJECTIVE

Analyze the fractal/hierarchical nesting structure of NQ price swings using 1-tick bar data. We want to understand how larger swings decompose into smaller child swings, and whether this decomposition is self-similar across scales. This is a **discovery/research task** — produce data, charts, and summary statistics. Do not build a trading strategy.

## DATA

- **Location:** `C:\Projects\pipeline\stages\01-data\data\bar_data\tick\`
- **Format:** CSV, 1-tick bars
- **Instrument:** NQ (Nasdaq 100 E-mini futures)
- **Expected columns:** DateTime, Open, High, Low, Close, Volume (and possibly others). Inspect the file header first and confirm column names before proceeding.
- **Date range:** ~6 months (approx Sept 2025 – Mar 2026)

⚠️ **DATA SIZE WARNING: 6 months of 1-tick NQ data may be tens of millions of rows. Use chunked reading (pandas `chunksize` or similar), efficient dtypes (float32 where possible), and avoid loading the full dataset into memory more than once. Consider processing session splits sequentially rather than holding all three in memory.**

⚠️ **First step: inspect the CSV header and first 10 rows, and count total rows (`wc -l` or equivalent). Confirm column names, date format, and data size before writing any analysis code. If multiple files exist, list them and confirm which to use.**

---

## ANALYSIS — FOUR PARTS

### PART 1: Multi-Threshold Swing Distributions

Run a zig-zag swing detection on the 1T Close price series at **each** of these reversal thresholds: **3, 5, 7, 10, 15, 25, 50 points**.

For each threshold, a "swing" is defined as: price moves at least [threshold] points from the last confirmed swing point in the opposite direction. When that happens, the prior extreme becomes a confirmed swing point. This is standard zig-zag logic.

⚠️ **Use Close prices only (on 1T bars, OHLC are effectively identical — Close is fine). The zig-zag reversal threshold is in NQ points (not ticks). 1 NQ point = 4 ticks = 0.25 pts per tick. Dollar values are irrelevant for this analysis.**

**Output for each threshold:**
- Histogram of swing sizes (in points), binned by 1-point increments
- Count of swings, mean, median, P75, P90, standard deviation
- Skewness of the distribution

**Then compare across thresholds:**
- Table showing [threshold, count, mean, median, P90, skewness] for all 7 thresholds
- Plot all 7 distributions overlaid (normalized to percentages so they're comparable despite different counts)
- **Key question:** Does the *shape* of the distribution remain similar across scales? Compare median/P90 ratio and skewness across thresholds. If these ratios are stable, that's evidence of self-similarity.

📌 **Reminder: thresholds are 3, 5, 7, 10, 15, 25, 50 points. Use Close prices. 1 point = 4 ticks.**

---

### PART 2: Hierarchical Decomposition (Parent-Child Nesting)

This is the core analysis. For each adjacent pair of thresholds, treat the larger as "parent" and the smaller as "child":
- Parent 50 → Child 25
- Parent 25 → Child 15
- Parent 25 → Child 10
- Parent 15 → Child 7
- Parent 10 → Child 5
- Parent 7 → Child 3

**For each parent-child pair:**

1. Run zig-zag at the **child** threshold only on the price series. This gives you a sequence of child swings.
2. Also run zig-zag at the **parent** threshold to get parent swings — but these are used ONLY for the waste% and child-count-per-parent metrics (items a-c below), NOT for the completion rate.

**Metrics from parent overlay (items a-c):**

For each completed parent swing (from parent zig-zag), find all child swings nested inside it:

   - **Child count per parent:** How many child swings occur inside each parent swing? Report mean, median, min, max, distribution.
   - **Directional vs retracement children:** Of the child swings inside a parent, how many move in the parent's direction ("with") vs against ("retracement")? Report the ratio.
   - **Retracement waste:** Sum the absolute point movement of all child swings inside a parent. Compare to the parent's net movement. The difference is "wasted" movement on retracements. Express as a percentage: `waste% = (gross_child_movement - parent_net_movement) / gross_child_movement × 100`

⚠️ **IMPORTANT: The above metrics only look at completed parent swings (survivorship). The completion rate below is the critical metric and uses a DIFFERENT method.**

**Completion rate (item d) — DIFFERENT METHOD, DO NOT USE PARENT ZIG-ZAG:**

This measures the probability that a parent-scale move completes given N child retracements. It must capture both successful AND failed parent moves. Method:

   - Walk through the child zig-zag sequence chronologically.
   - At each child swing endpoint, track **cumulative net displacement** from a "start anchor."
   - The start anchor initializes at the first child swing point and resets every time a parent-scale move completes or fails (see below).
   - A child swing that moves AGAINST the current net direction counts as a "retracement."
   - **Success:** cumulative displacement from anchor reaches ±parent_threshold → parent-scale move completed. Record the number of child retracements that occurred. Reset anchor.
   - **Failure:** cumulative displacement reverses — it was positive but reaches -parent_threshold (or vice versa) → parent-scale move failed in the original direction. Record retracement count and mark as failure. Reset anchor.
   - Report: for each retracement count (0, 1, 2, 3, 4, 5+), how many parent-scale moves succeeded vs failed? This gives the **true completion rate** conditioned on retracement count.
   - **Session-end handling:** If a parent-scale move is still in progress when a session ends (RTH close at 16:15, ETH close at 09:30, or daily close for Combined), discard it. Do NOT carry state across session boundaries. This applies to items (d) and (e).

⚠️ **CRITICAL: This completion rate is the most important output of the entire analysis. It directly determines the structural breakpoint where adding to a position transitions from "exploiting a child retracement within an intact parent move" to "the parent move has failed." Do not skip this. Do not substitute the parent zig-zag overlay method — that only sees successes.**

**Half-block completion analysis (item e):**

Using the same child-walk method above, measure the **conditional completion probability at each progress level:**
   - For ALL parent-scale move attempts (both eventual successes and failures), track the maximum favorable displacement reached before the move either completed or failed.
   - For each 10% bucket of parent progress (10%, 20%, 30%... 90%): of all moves whose displacement reached at least that level, what fraction eventually completed the full parent threshold? Example: of all moves that reached at least 50% of the 25pt threshold (12.5 pts), what % went on to complete the full 25 pts vs reversed and hit -25?
   - Report this as a curve: X-axis = % of parent threshold reached, Y-axis = probability of eventual completion given that progress level was reached.
   - This curve identifies the "safe zone" — the progress level beyond which completion becomes highly probable — and the half-block sweet spot where taking profit balances capture rate against hold risk.

**Output:**
- Table: [parent_threshold, child_threshold, avg_children_per_parent, avg_with_children, avg_retrace_children, waste%, completion_after_0_retrace, completion_after_1, completion_after_2, completion_after_3, completion_after_4, completion_after_5plus]
- For the 25→10 pair specifically (matches our trade data), produce a detailed histogram of "child retracements per parent-scale move" with completion rate overlaid — include BOTH successes and failures.
- Half-block completion curve for the 25→10 pair: X = % of parent threshold reached, Y = probability of eventual completion.

📌 **Mid-document reminder: You are measuring how larger swings decompose into smaller ones. "Retracement" = a child swing that moves against the parent direction. "Completion" = cumulative displacement from anchor reaches the parent threshold. The completion rate method walks through child swings sequentially and tracks BOTH successes and failures — it does NOT use the parent zig-zag (which only sees successes).**

---

### PART 3: Power Law Tail Analysis

For each of the 7 threshold levels from Part 1:
- Take the swing size distribution
- Plot log(swing_size) vs log(frequency) for the right tail (swings > median)
- Fit a linear regression to the log-log plot
- Report the slope (power law exponent) and R² for each threshold

**If the exponents are similar across thresholds, the market has scale-free fractal structure.** If they diverge, different scales have different tail behavior.

---

### PART 4: Time-of-Day Structure Analysis (RTH Only)

This measures whether the fractal decomposition behavior is stable throughout the trading day or concentrated in specific windows. **RTH only (09:30–16:15 ET).**

**Parent-child pairs for this analysis:**
- Parent 15 → Child 7
- Parent 25 → Child 10
- Parent 50 → Child 25

**Time blocks:** Divide RTH into 30-minute blocks: 09:30, 10:00, 10:30, 11:00, 11:30, 12:00, 12:30, 13:00, 13:30, 14:00, 14:30, 15:00, 15:30 (last block runs 15:30–16:15).

**Method:** Use the **same child-walk method from Part 2 item (d)** — cumulative displacement from anchor, tracking both successes and failures. The only addition is tagging each parent-scale move attempt with a time block.

⚠️ **BLOCK ASSIGNMENT RULE: Assign each parent-scale move to the 30-minute block containing the ANCHOR timestamp (the point where the move attempt begins). A move that starts at 10:25 and resolves at 10:45 is assigned to the 10:00–10:30 block. The start is the decision point — that's when a trader would enter. Do NOT assign to the resolution block or double-count across blocks.**

⚠️ **Moves that are still in progress when RTH ends (16:15) should be discarded — they are incomplete and would bias the results.**

**Metrics per block, per parent scale:**
- **Sample count** — the gatekeeper. If a block has fewer than 30 parent-scale move attempts across the full 6 months, flag it as `INSUFFICIENT_SAMPLE` and do not report other metrics for that cell.
- **Completion rate at 0 retracements** — what % of moves that experience no child retracement complete successfully?
- **Completion rate at 1 retracement** — what % complete after exactly one child retracement?
- **Waste%** — for each **successful** parent-scale completion (from the child-walk), sum the absolute point movement of all child swings that occurred during that attempt, then apply: `waste% = (gross_child_movement - parent_threshold) / gross_child_movement × 100`. Exclude failed moves. Report the median waste% per block.
- **Median child swing size (points)** — are rotations tighter or wider in this window?

**Aggregation to test for noise:**
After computing all metrics at 30-minute granularity, also aggregate to **60-minute blocks** (09:30, 10:30, 11:30, 12:30, 13:30, 14:30, 15:30) and report the same metrics. If variation visible at 30-min resolution disappears at 60-min, the 30-min signal was noise. If it persists, it's structural. Report both resolutions.

📌 **Reminder: Use the child-walk method from Part 2(d) — NOT the parent zig-zag overlay. Assign moves to block by anchor timestamp. Minimum 30 samples per cell to report.**

**Output:**
- `part4_timeofday_30min.csv` — full metrics table: rows = 30-min blocks, columns = [block_start, parent_threshold, sample_count, completion_0_retrace, completion_1_retrace, waste_pct, median_child_swing]
- `part4_timeofday_60min.csv` — same table aggregated to 60-min blocks
- `part4_heatmap.png` — heatmap visualization: X-axis = time blocks (30-min), Y-axis = parent scale (15/25/50), color = completion rate at 1 retracement. Overlay sample count as text in each cell. Produce a second heatmap with waste% as the color.

---

## SESSION SPLITS

Run Parts 1-3 separately for (Part 4 is RTH-only by design and does not need session splits):
- **RTH only:** 09:30–16:15 ET
- **ETH only:** 18:00–09:30 ET
- **Combined (all hours)**

⚠️ **SESSION BOUNDARY HANDLING: For RTH-only and ETH-only analyses, RESET the zig-zag state at the start of each session. Do NOT carry zig-zag state across overnight gaps or session transitions. An overnight gap of 50 points is NOT a 50-point swing — it's a new starting condition. For Combined analysis, reset at the start of each trading day (18:00 ET Sunday–Friday). This means each session/day starts fresh with no prior swing context.**

⚠️ **This means each analysis produces THREE sets of results. Do RTH first as the primary output, then ETH, then combined. If time/compute is tight, RTH is the priority.**

---

## OUTPUT FORMAT

Save all results to: `C:\Projects\pipeline\stages\01-data\analysis\fractal_discovery\`

Create the directory if it doesn't exist. Save:
1. `fractal_summary.md` — narrative summary of all findings with key tables inline
2. `part1_distributions.png` — overlaid normalized distributions (all 7 thresholds)
3. `part2_decomposition_table.csv` — full decomposition metrics for all parent-child pairs
4. `part2_completion_rates.png` — completion rate vs retracement count (25→10 pair, includes successes AND failures)
5. `part2_halfblock_curve.png` — half-block completion probability curve (25→10 pair)
6. `part3_powerlaw.png` — log-log plots with fitted lines
7. `part4_timeofday_30min.csv` — time-of-day metrics at 30-min resolution
8. `part4_timeofday_60min.csv` — time-of-day metrics at 60-min resolution
9. `part4_heatmap.png` — completion rate and waste% heatmaps (time blocks × parent scale)
10. All raw data as CSVs for further analysis

---

## SELF-CHECK BEFORE FINISHING

- [ ] Part 1: All 7 thresholds computed? Overlay plot generated? Shape comparison table present?
- [ ] Part 2 (a-c): All 6 parent-child pairs analyzed for child count, directionality, and waste%?
- [ ] Part 2 (d): Completion rate computed using the child-walk method (NOT parent zig-zag overlay)? Captures both successes AND failures?
- [ ] Part 2 (d): 25→10 detailed histogram with completion rate overlaid, showing both outcomes?
- [ ] Part 2 (e): Half-block completion curve generated for 25→10?
- [ ] Part 3: Power law exponents reported for all 7 thresholds?
- [ ] Part 4: All three parent scales (15/25/50) computed at both 30-min and 60-min resolution?
- [ ] Part 4: Heatmaps generated? Sample counts visible in cells? Cells with <30 samples flagged?
- [ ] Part 4: Block assignment uses anchor timestamp (move start), NOT resolution timestamp?
- [ ] Parts 1-3: All three session splits (RTH/ETH/Combined) completed, or RTH at minimum?
- [ ] All files saved to `fractal_discovery\` directory?
- [ ] No trading strategy built — this is pure discovery/research output only
