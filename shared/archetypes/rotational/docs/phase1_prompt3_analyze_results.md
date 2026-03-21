# Phase 1, Prompt 3: Analyze Sweep Results and Pick Winners

## OBJECTIVE

Analyze the 182-config sweep results from Prompt 2. Rank configs across approaches on risk-adjusted metrics. Identify the top 3-5 configs per approach. Run cost sensitivity at 3.0 ticks. Preview regime segmentation using context tags. Determine which configs advance to Phase 2 (secondary sweep).

---

## PREREQUISITES

⚠️ **All of these must exist before proceeding. Verify each one.**

1. `config_summary.csv` at `C:\Projects\pipeline\stages\04-backtest\rotational\sweep_results\` — exactly 182 rows
2. `cycle_logs/` directory with one CSV per config — 182 files
3. `sweep_metadata.json` — confirms P1 date range, cost_ticks=2.0, 182 configs

Load `config_summary.csv` and confirm row count = 182 before any analysis.

---

## ANALYSIS — FIVE PARTS

### Part 1: Cross-Approach Overview

**Goal:** See the big picture before drilling into details.

For each approach (A, B, C, D), report:
- Number of configs
- NPF net: min, median, max
- Net PnL: min, median, max
- Profit per drawdown: min, median, max
- Cycle count: min, median, max
- How many configs have NPF net > 1.0? > 1.5? > 2.0?

📌 **This overview answers the first-order question: which APPROACH tends to perform best? If Approach A's median NPF is 1.8 and Approach B's median is 1.3, that's a structural finding — pure rotation beats martingale on the median config, regardless of parameter tuning.**

Produce a summary table:

| Approach | Configs | Median NPF | Median Net PnL | Median Profit/DD | NPF>1.5 Count | Best Config NPF |
|----------|---------|-----------|----------------|------------------|---------------|----------------|

---

### Part 2: Top Config Selection

**Goal:** Identify the top 3-5 configs per approach.

⚠️ **Ranking metric: profit_per_dd (net_pnl / max_drawdown_ticks).** This is the primary selection criterion — it rewards configs that make money efficiently relative to their risk. NPF alone favors low-frequency configs with few but large wins. Total PnL alone favors high-risk configs. Profit/DD balances both.

**Secondary filters (must pass ALL to qualify):**
- cycle_count ≥ 50 (statistical minimum — fewer than 50 cycles is not enough data)
- npf_net > 1.0 (must be net profitable after costs)
- max_drawdown_ticks < 2 × net_pnl (drawdown less than 2× total profit — avoids fragile configs)

📌 **Apply filters first, THEN rank by profit_per_dd within each approach. If an approach has fewer than 3 qualifying configs, report all that qualify and note the shortfall.**

For each top config, report the full summary row from config_summary.csv plus:
- Cycle-type breakdown: what % of PnL comes from 0-add, 1-add, and multi-add cycles?
- flatten_reseed_would_fire count (B only): how many cycles would have been cut short?

**Output:** `top_configs.csv` — one row per top config (expect 12-20 rows total across 4 approaches)

---

### Part 3: Cost Sensitivity at 3.0 Ticks

**Goal:** Confirm top configs survive pessimistic cost assumptions.

⚠️ **Do NOT re-run the simulator.** The cycle logs already contain gross PnL and trade counts. Recompute net PnL by applying cost_ticks=3.0 to the existing cycle-level trade data.

For each top config from Part 2:
- Recalculate total costs at 3.0 ticks/side
- Recalculate net_pnl, npf_net, profit_per_dd
- Flag any config where NPF drops below 1.0 at 3.0 ticks — these are cost-sensitive

📌 **This is a spreadsheet exercise on existing data, not a simulation re-run. Each cycle log has trade counts (seed + adds + reversal). Multiply trade count × new cost_ticks to get new total cost. Subtract from gross PnL.**

**Output:** `cost_sensitivity.csv` — columns: config_id, npf_at_2.0, npf_at_3.0, pnl_at_2.0, pnl_at_3.0, profit_dd_at_2.0, profit_dd_at_3.0, survives_3.0 (boolean)

---

### Part 4: Regime Segmentation Preview

**Goal:** Use the context tags to preview whether performance varies by market regime. This is the foundation for the trending-market conversation.

⚠️ **Run this on the top 5 overall configs (across all approaches), not all 182. This is a preview, not a full analysis.**

For each top config, split its cycle log into regime buckets using the context columns:

**ATR regime (3 buckets):**
- Low: atr_percentile ≤ 33
- Medium: 33 < atr_percentile ≤ 67
- High: atr_percentile > 67

**Directional persistence (3 buckets):**
- Rotational: directional_persistence ≤ 1
- Transitional: 2 ≤ directional_persistence ≤ 3
- Trending: directional_persistence ≥ 4

For each bucket, report: cycle count, win rate, npf_net, avg pnl_net per cycle.

📌 **The key question: does performance degrade in high-ATR or high-persistence (trending) regimes? If the top rotation configs show NPF > 1.5 in rotational regime but NPF < 1.0 in trending regime, that's the empirical case for building a regime filter or a separate trending-market mode.**

**Output:** `regime_preview.csv` — columns: config_id, regime_type (atr/persistence), bucket (low/med/high or rotational/transitional/trending), cycle_count, win_rate, npf_net, avg_pnl_net

Also produce a visual: 2×5 grid of small bar charts (2 regime types × 5 configs), each showing NPF by bucket. Save as `regime_preview.png`.

---

### Part 5: Approach Comparison and Advancement Decision

**Goal:** Synthesize Parts 1-4 into a clear recommendation of which configs advance to Phase 2.

⚠️ **This is the decision section. Be explicit about what the data says and what it doesn't.**

Answer these questions in a narrative summary:

1. **Which approach wins?** Compare the best config from each approach on profit_per_dd, NPF, and drawdown. Is one approach clearly dominant, or are multiple competitive?

2. **Does the decoupled AddDist help?** Within Approach B, compare AddDist=StepDist (ratio 1.0) vs AddDist=StepDist/2.5 (ratio 0.4) at the same StepDist levels. If decoupling doesn't improve results, it's unnecessary complexity.

3. **Do adds help at all?** Compare the best Approach A config (no adds) against the best B/C/D configs. If A wins on risk-adjusted terms, adds are structural cost for no benefit.

4. **Does conviction sizing help?** Within Approach D, compare add_size=2 vs add_size=3 at the same StepDist/ConfirmDist. Bigger conviction = more profit on winners but more loss on failures.

📌 **Reminder: the goal is not to find one winner. It's to identify the 10-15 configs that advance to Phase 2 (secondary sweep with FlattenReseed + ReversalTarget). The secondary sweep will further refine. Be generous with advancement — a config that's top-5 in one approach but not overall should still advance.**

5. **What does regime segmentation suggest?** If performance is regime-dependent, note which regimes are favorable and which are hostile. This informs whether Phase 2 should include a regime gate or whether the trending-market defense is a priority.

**Advancement criteria:**
- Top 3-5 per approach that pass the Part 2 filters
- Any config from any approach that has profit_per_dd in the top 15 overall
- Any config that shows particularly strong regime resilience (NPF > 1.3 in ALL regime buckets)

**Output:** `advancement_list.csv` — config_ids that advance to Phase 2, with the reason for each (top_in_approach / top_overall / regime_resilient)

---

## FINAL OUTPUT

Save all results to: `C:\Projects\pipeline\stages\04-backtest\rotational\sweep_results\analysis\`

```
analysis/
├── cross_approach_overview.csv    # Part 1 summary table
├── top_configs.csv                # Part 2 top 3-5 per approach
├── cost_sensitivity.csv           # Part 3 re-scoring at 3.0 ticks
├── regime_preview.csv             # Part 4 regime buckets
├── regime_preview.png             # Part 4 visual
├── advancement_list.csv           # Part 5 configs advancing to Phase 2
└── sweep_analysis_report.md       # Narrative report covering all 5 parts
```

📌 **The sweep_analysis_report.md is the primary deliverable. It should be readable as a standalone document — someone who hasn't seen the raw data should understand which approaches work, which don't, and why. Include the key tables inline. The CSVs are supporting data for reproducibility.**

---

## SELF-CHECK BEFORE FINISHING

- [ ] config_summary.csv loaded: 182 rows confirmed
- [ ] Part 1: cross-approach overview table produced for all 4 approaches
- [ ] Part 2: top 3-5 per approach selected by profit_per_dd after filtering
- [ ] Part 2: filters applied — cycle_count ≥ 50, npf_net > 1.0, max_dd < 2× net_pnl
- [ ] Part 3: cost sensitivity computed at 3.0 ticks WITHOUT re-running simulator
- [ ] Part 3: configs that fail at 3.0 ticks flagged
- [ ] Part 4: regime segmentation on top 5 overall configs (not all 182)
- [ ] Part 4: ATR and directional persistence buckets both computed
- [ ] Part 4: regime_preview.png visual generated
- [ ] Part 5: explicit answers to all 5 comparison questions
- [ ] Part 5: advancement_list.csv produced with reasons
- [ ] sweep_analysis_report.md is standalone readable
- [ ] All files saved to `sweep_results/analysis/`
