# P2a Replication Validation: Frozen-Anchor SD40/RT0.8

## OBJECTIVE

Run the frozen-anchor strategy with frozen P1 parameters on P2a holdout data. This is the replication gate — the strategy must demonstrate the same structural signature on unseen data. No parameter changes, no re-optimization. One shot.

⚠️ **FROZEN PARAMETERS. Do not modify anything based on P2a results. The strategy runs exactly as calibrated on P1. If it fails, it fails. Do not "fix" it by adjusting parameters — that contaminates the holdout.**

---

## THE STRATEGY (Frozen from P1)

```python
FrozenAnchorConfig(
    config_id="P2A_VALIDATION",
    step_dist=40.0,
    add_dist=16.0,     # Unused (MaxAdds=0) but required > 0
    max_adds=0,
    reversal_target=0.8,
    cost_ticks=2.0,
    entry_mode="immediate",  # Standard seed, no pullback
)
```

**State machine:**
- WATCHING: WatchPrice = first bar of session. Direction when price moves ≥ 40pts from WatchPrice.
- POSITIONED: Anchor = entry price (frozen). Success at +32pts. Failure at -40pts.
- Exit: flatten + enter 1 opposite. New anchor = exit price.
- Session reset at 16:15. Flatten any position.
- 1 contract, no adds, always in market after first seed.

📌 **This is identical to FA_SD40_MA0_RT80 from the P1 sweep. Same simulator, same config, different data. The only change is the date range.**

---

## DATA

**P2a period:** Dec 15, 2025 – ~Jan 28, 2026 (midpoint split of Dec 15 – Mar 13)

⚠️ **Determine the exact midpoint by counting RTH trading days in the Dec 15 – Mar 13 range, then split at the halfway point. Report the actual P2a end date and P2b start date. Both should have approximately equal RTH days.**

- Source: `C:\Projects\pipeline\stages\01-data\data\bar_data\tick\`
- 1-tick bars, RTH only (09:30–16:15 ET)
- Pre-compute context tags via `context_tagger.py` (same as P1 sweep)

Report after loading: total rows, date range confirmed, number of RTH trading days. Compare to P1 (25.4M bars, 60 RTH days).

---

## ALSO RUN (For Comparison Only)

Run two additional configs alongside the primary validation. These do NOT affect the pass/fail verdict — they provide context:

```python
# Best add config from P1 — does the add edge replicate?
FrozenAnchorConfig(
    config_id="P2A_R03_MA2",
    step_dist=40.0,
    add_dist=12.0,
    max_adds=2,
    reversal_target=0.8,
    cost_ticks=2.0,
    entry_mode="immediate",
)
```

⚠️ **The R03_MA2 config is informational only. It showed +16,998 adj net on P1 (vs +12,420 for MA0) but with higher drawdown. If the primary MA0 config passes but R03_MA2 fails, adds are not robust. If both pass, adds may be explored further on P2b.**

```python
# Random walk baseline — confirms the market structure is the same
FrozenAnchorConfig(
    config_id="P2A_RANDOM_WALK_CHECK",
    step_dist=40.0,
    add_dist=16.0,
    max_adds=0,
    reversal_target=1.0,   # Symmetric exits — should be ~50% SR
    cost_ticks=0.0,         # Zero cost to isolate structural SR
)
```

📌 **The random walk check is the most important baseline. If RT=1.0 shows ~50% SR on P2a (same as P1's 49.4%), the market structure is consistent. If it shows 45% or 55%, the market's behavior shifted and all P1 findings may not generalize.**

---

## PASS/FAIL CRITERIA

⚠️ **Read ALL criteria before running. The verdict is determined by these rules, not by "does it look good."**

### Primary Criteria (ALL must pass)

1. **Success rate above random walk:** SR must exceed the random walk prediction (55.6% for RT=0.8) by at least 1pp. P1 showed 58.8% (+3.2pp). P2a doesn't need to match exactly, but it must be above random walk. **If Delta is between +1pp and +2.5pp, mark as NARROW PASS and note in the report — the edge is present but weaker than P1.**

2. **Adjusted net PnL positive:** net_pnl + incomplete_unrealized_pnl > 0. The strategy must make money after costs and session-end losses.

3. **Random walk baseline validates:** The RT=1.0/cost=0 check must show SR within ±3pp of 50%. If the market structure has shifted (e.g., 45% or 56% at symmetric exits), the P1 calibration assumptions don't hold.

### Structural Signature (Diagnostic — Not Pass/Fail)

Report these for comparison to P1 but they don't determine the verdict:

| Metric | P1 Value | P2a Value | Concern Threshold |
|--------|----------|-----------|-------------------|
| Success rate | 58.8% | ? | < 55.6% (below random walk) |
| First-cycle SR | 66.1% | ? | < 58% (edge disappeared) |
| Later-cycle SR | 58.6% | ? | < 53% (below random walk) |
| Failure cascade rate | 42.8% | ? | > 55% (regime shift) |
| Avg progress HWM (failures) | 30.8% | ? | > 50% (failures getting closer to target = different character) |
| Incomplete PnL per day | -7 ticks | ? | < -100 (session-end exposure growing) |
| NPF | 1.08 | ? | < 1.0 (losing money) |

📌 **The structural signature tells us WHETHER the strategy works for the same reasons on P2a as P1. If SR is 59% but first-cycle SR dropped to 52% and later-cycle SR rose to 60%, the edge source shifted — passing on different mechanics than what we validated.**

---

## PER-CYCLE LOGGING

Same columns as the frozen-anchor sweep:

**Standard:** config_id, cycle_id, start_time, end_time, duration_bars, duration_minutes, side, add_count, exit_position, pnl_ticks_gross, pnl_ticks_net, MFE, MAE

**Exit classification:** exit_type (SUCCESS/FAILURE/SESSION_END)

**Diagnostics:** progress_hwm, cycle_day_seq, cycle_start_hour, prev_cycle_exit_type, cycle_waste_pct

**Regime context:** atr_20bar, atr_percentile, swing_median_20, swing_p90_20, directional_persistence, bar_range_median_20

⚠️ **All logging columns must match P1 exactly. The comparison requires identical schemas.**

**Incomplete cycles:** Same format as P1 sweep — `{config_id}_incomplete.csv` with unrealized PnL.

---

## OUTPUT

Save to: `C:\Projects\pipeline\stages\05-assessment\rotational\p2a_validation\`

📌 **This goes in the assessment directory (stage 05), not the backtest directory (stage 04). P2a is validation, not development.**

```
p2a_validation/
├── config_summary.csv          # 3 rows (primary + 2 comparison)
├── cycle_logs/                 # 3 cycle CSVs + 3 incomplete CSVs
├── p2a_validation_report.md    # Verdict + structural comparison
└── p2a_metadata.json           # Date range, bar count, trading days
```

### p2a_validation_report.md Structure

```markdown
# P2a Validation Report

## Verdict: PASS / FAIL

## Primary Criteria
1. SR above random walk: [PASS/FAIL] — SR=?%, RW=55.6%, Delta=?pp
2. Adjusted net positive: [PASS/FAIL] — Adj net=? ticks
3. Random walk baseline: [PASS/FAIL] — RT=1.0 SR=?% (expect ~50%)

## Structural Signature Comparison
[table comparing P1 vs P2a on all diagnostic metrics]

⚠️ If first-cycle SR dropped but overall SR held, note that the edge source may have shifted.

## Equity Curve
[cumulative PnL over P2a cycles — is it steadily positive or front/back loaded?]

## Regime Comparison
[ATR and persistence distributions on P2a vs P1 — was the market similar?]
```

📌 **The equity curve is important. A strategy that makes +10K ticks but had -8K at the midpoint and recovered in the last week is less trustworthy than one that accumulated steadily. Report the max drawdown timing — did it occur early, mid, or late in P2a?**

---

## AFTER THE VERDICT

**If PASS:** Proceed to P2b with the same frozen config. P2b is the final validation — same process, same criteria, no changes.

**If FAIL:** Do NOT re-optimize. Record the failure in the audit log with the specific metrics that failed. The strategy architecture has been fully explored — the P1 edge did not replicate. Options at that point:
- Review the structural factor findings for new hypotheses
- Revisit the volume profile analysis
- Accept that the edge is too thin and regime-dependent to trade

⚠️ **There is no "conditional pass" or "close enough." The criteria are binary. Pass or fail.**

---

## SELF-CHECK BEFORE FINISHING

- [ ] P2a date range confirmed: Dec 15, 2025 – midpoint (~Jan 28, 2026)
- [ ] Midpoint computed by counting RTH days, not calendar days
- [ ] P2b dates reserved: midpoint – Mar 13, 2026 (NOT loaded, NOT examined)
- [ ] 1-tick data loaded, RTH only
- [ ] Context tags pre-computed
- [ ] 3 configs run: primary (MA0/RT80), comparison (R03_MA2/RT80), baseline (RT100/cost0)
- [ ] All logging columns match P1 schema exactly
- [ ] Incomplete cycles logged
- [ ] Pass/fail criteria applied: SR > RW + 1pp, adj net > 0, RW baseline ~50%
- [ ] Structural signature comparison table produced
- [ ] Equity curve reported with max drawdown timing
- [ ] Regime comparison (ATR, persistence distributions) reported
- [ ] Verdict clearly stated: PASS or FAIL
- [ ] All files saved to `stages/05-assessment/rotational/p2a_validation/`
