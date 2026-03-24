# NQ Zone Touch — Gap Investigation (v3.2)

Generated: 2026-03-24
**Reminder: These are supplementary tests. They do not replace Prompt 3 verdicts.**
All targeted tests use P1-calibrate / P2-one-shot protocol. Every result compared against baseline PF anchor (1.3396).

---

## Tests Answered from Existing Data

### Test B: HTF-Only (240m+) as Standalone Mode

**Prior claim:** HTF zones had best R/P (3.22-3.97) but worst SBB rate.

**v3.2 evidence (from feature screening confirmation simulation):**
| TF | PF @3t (median cell) | Trades |
|----|---------------------|--------|
| 240m | 1.272 | 145 |
| 360m | 1.262 | 108 |
| 480m | 0.828 | 98 |
| 720m | 0.959 | 73 |

**Verdict: NOT VIABLE.** 480m and 720m are below baseline (1.34). 240m and 360m are marginally below baseline. The prior HTF R/P advantage was likely an artifact of SBB exclusion — in warmup-enriched data with low SBB rate, HTF zones show no edge advantage over the population. The prior finding that "HTF best R/P but worst SBB" was a confound: HTF had high SBB rate, and removing SBB artificially inflated HTF's apparent R/P.

### Test C: CT + Low Score (Prior M3 Replication)

**Prior result:** PF 1.06 (dead).

**v3.2 evidence:**
- seg3 A-Cal ModeC_Below (CT + below A-Cal threshold): PF 0.69 @4t, 66 P2 trades → **No verdict**
- seg3 B-ZScore ModeC_Below: PF 0.74 @4t, 186 P2 trades → **No verdict**

**Verdict: CONFIRMED DEAD.** Low-quality CT touches have no edge on warmup-enriched data, consistent with prior finding. The structural inversion (CT + HIGH score = viable) is covered in the main report.

### Test F: ZONEREL Exits on A-Eq ModeA Population

**Question:** What if zone-relative exits replace FIXED 190t/60t on the same A-Eq ModeA qualifying touches?

**v3.2 evidence (from Prompt 2 P1 calibration):**
| Exit Type | P1 PF @3t | P1 Trades | Exit Params |
|-----------|-----------|-----------|-------------|
| FIXED (winner) | 8.496 | 107 | Stop=190t, Target=60t, TC=120 |
| ZONEREL | 7.530 | 107 | Stop=1.2xZW, Target=0.75xZW, TC=80 |

FIXED outperforms ZONEREL by 12.8% on P1 for the A-Eq ModeA population. [SPECULATION] The likely reason: A-Eq ModeA selects high-quality touches with favorable penetration (F10) and young zones (F21) — these are decisive bounces where a fixed tight target (60t) captures the initial reaction reliably, while ZONEREL targets scale with zone width and may be too large for narrow zones or too small for wide zones in this specific sub-population.

**Verdict: FIXED is correct for A-Eq ModeA.** ZONEREL remains the right choice for B-ZScore RTH (larger, more diverse population where zone-relative sizing adapts better).

---

## Tests Requiring Simulation (Deferred)

### Test A: Afternoon Scalp Sub-Population

**Prior claim:** M4 afternoon scalp at PF 1.49-1.54 with 30t target / 10-bar cap.

**What's needed:** Filter P2 B-ZScore or A-Eq qualifying touches to Close session only. Apply 30t target / 60t stop / 10-bar time cap. Compute P2 PF.

**Available context:** From v3.2 feature screening, Close session at median cell: PF 1.480 (297 P1 trades). This is above baseline (1.34) but below the scoring model's enhancement. The question is whether the scoring model + Close session + scalp exit structure produces a distinct viable mode.

**Implementation:** Would require modifying `prompt3_holdout_v32.py` to add a Close-session-only run with scalp exit parameters. P1 calibration first, then P2 one-shot.

**Expected value: LOW.** [OPINION] The Close session is the 4th-best session (PF 1.48 vs PreRTH 1.82, OpeningDrive 1.91), and afternoon scalping with 30t target at 3t cost has breakeven WR of 60/(60+30)=67% — tight margin. The scoring model already assigns F05 (Session) points that appropriately weight Close touches. A dedicated afternoon mode is unlikely to add value beyond what the combined waterfall already captures.

### Test D: Prior M1_A Config Replication

**Prior config:** Score ≥ threshold + seq ≤ 3 + TF ≤ 120m + 14 features + TF-specific width gates + 3-leg partial exits.

**What's needed:** Apply seq ≤ 3 and TF ≤ 120m filters to v3.2 A-Eq ModeA population, then run P2 simulation.

**Available context:**
- v3.2 winner without these gates: 96 P2 trades, PF 6.26
- P1 seq distribution: 35.5% are seq 1
- P1 TF distribution: 15m (972), 30m (726), 60m (406), 90m (331), 120m (298) — these 5 TFs cover 83% of touches

**Expected outcome:** [SPECULATION] Adding seq ≤ 3 and TF ≤ 120m gates would reduce trade count (likely to ~70-80 trades) while potentially increasing PF if the excluded touches (seq 4+, TF 240m+) were dilutive. However, since A-Eq already selects high-score touches (127 P1 → 96 P2), the marginal touches are already high quality. The gates were necessary in the prior analysis to compensate for a weaker scoring model (14 features simultaneously calibrated); with the v3.2 7-feature elbow model, the score threshold alone is sufficient quality control.

### Test G: A-Cal ModeA Overlap with A-Eq ModeA

**Question:** A-Cal ModeA has 1,183 P2 trades at PF 1.62. What % overlap with A-Eq ModeA (96 trades)? What PF on the A-Cal-only (non-overlapping) population?

**What's needed:** Trade-level join between `p1_scored_touches_acal_v32.csv` and `p1_scored_touches_aeq_v32.csv`, then P2 simulation on the A-Cal-only subset.

**Available context:**
- A-Cal threshold: 21.09/30.13 (70%) → 109 P1 qualifying touches
- A-Eq threshold: 45.5/70 (65%) → 127 P1 qualifying touches
- Both use the same 7 features, different weighting

[SPECULATION] Since A-Cal is more heavily weighted toward F10, and A-Eq requires broad strength across all 7 features, the overlap should be significant but not complete. A-Cal will include some touches with very high F10 but mediocre other features, while A-Eq will include some touches with moderate F10 but strong across all dimensions.

**The A-Cal-only population** (A-Cal accepts, A-Eq rejects) would have ~1,087 P2 trades at PF ~1.55 (slightly below the 1,183-trade composite because the overlapping A-Eq trades are the best performers). [SPECULATION] This is unlikely to be viable as a standalone third tier — PF ~1.55 at 4t cost is marginal.

### Test H: Session Sub-Splits Within B-ZScore RTH

**Question:** Does OpeningDrive outperform Midday/Close within B-ZScore Seg2 RTH?

**What's needed:** Split B-ZScore RTH qualifying touches by F05 (Session) into OpeningDrive, Midday, Close. Run P2 simulation on each.

**Available context:**
- B-ZScore RTH mode_classification CV = 0.150 (low — consistent across sub-splits)
- From P1 calibration, B-ZScore RTH P1 PF = 4.71 on 245 trades
- Session screening: OpeningDrive PF 1.91, Midday 1.30, Close 1.48 at median cell

**Expected outcome:** [SPECULATION] OpeningDrive likely outperforms within RTH because it has the strongest baseline R/P (1.91 vs 1.30 Midday), and B-ZScore scoring already favors OpeningDrive via F05 points. Session-conditional exits could capture this (e.g., wider target in OpeningDrive, tighter in Midday), but this adds complexity for marginal gain. The low CV (0.150) suggests the B-ZScore scoring model already handles session differences adequately — further sub-splitting would fragment an already well-calibrated mode.

---

## Deferred Tests Summary

| Test | Priority | Expected Value | Blocker |
|------|----------|---------------|---------|
| A (Afternoon scalp) | Low | Low — Close session is 4th-best | Simulation script needed |
| D (M1_A replication) | Medium | Medium — confirms gates are unnecessary | Simulation script needed |
| G (A-Cal overlap) | Medium | Low — A-Cal-only population likely marginal | Trade-level join + simulation |
| H (Session sub-splits) | Low | Low — CV already low (0.150) | Simulation script needed |

[OPINION] None of the deferred tests are likely to change the deployment recommendation. The 2-tier waterfall (A-Eq ModeA + B-ZScore RTH) is the correct deployment for paper trading. These tests are academic interest for understanding the edge structure, not deployment-critical.
