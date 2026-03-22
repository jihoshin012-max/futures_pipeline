# Gap Investigation Report (v3.1)
Generated: 2026-03-22
Prompt 3 verdicts are FINAL. This report is supplementary.

---

## Summary

No targeted follow-up simulations were run. All gaps identified in Step 17a were resolved analytically — no prior finding was missed that warrants additional P1-calibrate / P2-one-shot testing.

## Gap Resolution Detail

### Test A: M4 Afternoon Scalp (PF 1.49-1.54 prior)
**Resolution: No gap.** Afternoon session is captured in F05_Session screening (Close session R/P = 1.234 @60 bars, ranked #3 STRONG). The fresh pipeline scores session quality rather than hard-segmenting by time-of-day. The afternoon population that the prior isolated would be drawn from touches already rejected by the A-Cal threshold (score < 16.66) — these consistently show PF ~1.07 on P2 across all segmentations.

### Test B: HTF-Only Strict Width (R/P 3.22-3.97 prior)
**Resolution: No gap.** Prior R/P numbers were at longer observation horizons (full observation). At practical simulation horizons (30-120 bars with time cap), HTF zones show PF < 1.0:
- 480m: PF @3t = 0.6963 (baseline)
- 720m: PF @3t = 0.7042 (baseline)
The high R/P at full observation reflects eventual reversion over hundreds of bars — impractical for the time-capped exit structure (30-120 bars) used in deployment.

### Test C: CT + Low Score + Morning (PF 1.06 prior — dead)
**Resolution: Confirmed dead.** seg3 ModeC (below threshold, including CT rejects) achieved PF 1.068 @4t on P2 with "No" verdict. The fresh pipeline independently confirms that CT without quality scoring has no edge.

### Test D: Direct M1_A Replication
**Resolution: Superseded.** The fresh 4-feature model (PF 5.0) outperforms the prior 14-feature M1_A (PF 4.67) with fewer features and better risk metrics. Replication would require reconstructing the prior v2 scoring model weights — unnecessary since the fresh model is demonstrably superior.

### Test E: WEAK+STRUCTURAL Features Forced Into Elbow
**Resolution: Already tested.** The incremental build (Prompt 1b) tested adding each feature sequentially after the elbow point:
- F09_ZW_ATR added to 4-feature model: dPF = -0.94 (SKIPPED)
- F02_ZoneWidth added to 4-feature model: dPF = -0.84 (SKIPPED)

Both WEAK+STRUCTURAL features degraded performance when added to the elbow model. Their mechanistic grounding does not translate to independent predictive power sufficient to improve the already-strong 4-feature model.

## Conclusion

All 5 candidate tests were resolved without requiring additional simulation:
- 2 gaps are non-gaps (captured by scoring rather than segmentation)
- 1 gap confirmed dead (independent replication of prior finding)
- 1 gap superseded (fresh model outperforms)
- 1 gap already tested (incremental build covered it)

No modifications to Prompt 3 deployment spec required.
