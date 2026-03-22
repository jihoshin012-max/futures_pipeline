# Combined Recommendation — NQ Zone Touch (v3.1)
Generated: 2026-03-22
Supplements: `verdict_narrative.md` (Prompt 3)

---

## 1. Verdict

The NQ zone touch strategy **passed** holdout testing with a bottom-up methodology. The winning configuration achieves PF 5.0 @4t on 58 P2 trades with 91.4% win rate, 193-tick max drawdown, and 100th percentile random ranking. All 4 scoring features are STRUCTURAL mechanism class. Deploy as single-mode CT-only.

## 2. Winning Configuration (Frozen)

| Parameter | Value |
|-----------|-------|
| Run | seg3_A-Cal / ModeB |
| Scoring model | A-Cal (calibrated weights) |
| Features | F10_PriorPenetration (wt=10.0), F04_CascadeState (wt=5.94), F21_ZoneAge (wt=4.42), F01_Timeframe (wt=3.44) |
| Max score | 23.8 |
| Threshold | ≥ 16.66 |
| Trend filter | Counter-trend only (CT) |
| Edge filter | DEMAND_EDGE or SUPPLY_EDGE required |
| TF filter | Active (all TFs eligible, scored by F01) |
| Seq gate | None |
| Width gate | None |
| Stop | 190 ticks |
| Target | 80 ticks |
| BE trigger | None |
| Trail trigger | None |
| Time cap | 120 bars |
| SBB leak rate | 0.0% |

Machine-readable spec: `deployment_spec_clean.json`
Scoring weights: `scoring_model_acal.json`

## 3. P2 Holdout Performance

| Metric | P2a | P2b | Combined |
|--------|-----|-----|----------|
| Trades | 28 | 30 | 58 |
| PF @3t | 4.722 | 5.477 | 5.096 |
| PF @4t | 4.623 | 5.376 | 4.996 |
| Win rate | 89.3% | 93.3% | 91.4% |
| Max DD | 193t | 193t | 193t |
| Profit/DD | 7.560 | 8.953 | 16.513 |
| Sharpe | 0.722 | 0.840 | 0.787 |
| SBB % | 0.0% | 0.0% | 0.0% |
| MWU p | 0.002 | 0.014 | 0.001 |
| Perm p | 0.007 | 0.002 | 0.000 |
| Rand %ile | 99.1 | 100.0 | 100.0 |

## 4. Baseline & Overfit Context

| Reference | PF @3t |
|-----------|--------|
| Unfiltered baseline (all periods, no features) | 0.898 |
| NORMAL-only baseline | 1.334 |
| Winner on P2 | 5.096 |
| Winner / unfiltered | 5.7× |
| Winner / NORMAL | 3.8× |

The scoring model adds ~3.8× value above the NORMAL baseline. All value comes from 4 STRUCTURAL features — no STATISTICAL_ONLY features in the model. The 0% SBB leak rate means the model perfectly filters the destructive population. [OPINION] Overfit risk is moderate — the high multiplier warrants monitoring during paper trading, but mechanistic grounding and holdout stability provide confidence.

## 5. What the Bottom-Up Approach Revealed

### 5a. Counter-Trend Structural Inversion
The prior analysis found CT + low score = dead (PF 1.06). The fresh pipeline found CT + high score = best mode (PF 5.0). Same trend filter, opposite quality filter, opposite result. [SPECULATION] Counter-trend touches at high-quality zones represent stronger structural levels — the zone held despite trend pressure, implying greater significance.

### 5b. Feature Reduction (14 → 4)
The prior top-down calibration used 14 features simultaneously. The bottom-up screening revealed only 4 have independent predictive power (STRONG or SBB-MASKED + enters elbow). Notably:
- Zone width (F02): prior weight = 13 (2nd highest). Fresh: **WEAK** (#15). No independent signal — was benefiting entirely from combination effects in the prior calibration.
- Prior penetration (F10): prior weight = 7 (5th). Fresh: **#1 strongest feature** with R/P spread = 0.977 @60 bars (nearly 2× any other feature). The prior top-down underweighted it.

### 5c. Zone Age (F21) — New Feature
The expansion feature F21_ZoneAge (from `zone_lifecycle.csv`) contributed the largest single dPF increment (+1.24) in the incremental build. Younger zones bounce more reliably. This feature was not available in the prior analysis.

### 5d. SBB-MASKED Classification
Three features (F21, F09, F02) were classified SBB-MASKED — their signal is hidden by SBB contamination in the full population but visible on the NORMAL subset. F21 entered the elbow; the other two did not. The SBB-MASKED classification is a methodological contribution of the bottom-up approach: it identifies features whose apparent weakness comes from population contamination rather than lack of signal.

## 6. Rejected Alternatives

| Alternative | Result | Why Rejected |
|------------|--------|-------------|
| A-Eq scoring | PF 1.644 on P2 (Conditional) | Equal weights dilute F10's dominant signal |
| B-ZScore scoring | PF 1.266 on P2 (No) | 17.5% SBB leak, insufficient separation |
| seg1 ModeA (all trends, high score) | PF 2.996 (Yes) | 2.3× worse than CT-only; includes WT/NT subset (PF 1.6) |
| seg4 ModeA (low ATR + high score) | PF 3.640 (Yes) | Overlaps winner population; different lens on same edge |
| B-only secondary tier | PF 1.071 (No) | Economically insufficient at 4t cost |
| Multi-mode portfolio (CT + WT/NT) | PF ~3.0 (est.) | -40% PF, +100% max DD for +40% frequency — not worth it |

## 7. Open Items for Deployment

| Item | Priority | Action |
|------|----------|--------|
| Exit type breakdown | Medium | Run `exit_type_breakdown.py` to compare P1 vs P2 exit profiles |
| Paper trading (P3) | **High** | Mar–Jun 2026: collect live signals with frozen parameters |
| C++ autotrader | High | Implement scoring model + routing logic from `deployment_spec_clean.json` |
| Study files | Medium | V4 v1 (unmodified) + ZB4 aligned + new autotrader — compile and test |
| P3 comparison metric | Medium | Compare P3 live PF against P2 PF (5.0 @4t). Threshold for concern: PF < 2.0 over 30+ trades |
| Win rate monitoring | Medium | P3 target: win rate > 80%. If drops below 70%, investigate whether CT structural edge is degrading |
| Max DD monitoring | Low | P3 threshold: if max DD exceeds 400t (2× P2), pause and investigate |

## 8. Signal Flow (Production)

```
Touch event → Compute 4 features (F10, F04, F01, F21)
           → Score = Σ(weight × bin_score)
           → IF score ≥ 16.66 AND edge present AND TrendLabel == CT:
               → ENTER (long if DEMAND_EDGE, short if SUPPLY_EDGE)
               → Stop = entry ± 190t
               → Target = entry ∓ 80t
               → Time cap = 120 bars
           → ELSE: SKIP
```

## 9. Cross-Reference Summary

- No gaps found vs prior analysis (all 11 prior lessons captured or refined)
- No targeted follow-up tests needed
- Single-mode deployment confirmed (no multi-mode portfolio)
- B-only tier rejected (PF degraded from P1 1.43 to P2 1.07)
- All prior findings compatible with fresh results when correctly interpreted through bottom-up lens

---

*This document supplements `verdict_narrative.md` (Prompt 3). Full analysis in `cross_reference_report_clean.md` (this prompt).*
