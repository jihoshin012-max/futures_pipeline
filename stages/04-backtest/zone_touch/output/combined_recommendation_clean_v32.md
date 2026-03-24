# NQ Zone Touch — Combined Recommendation (v3.2)

Generated: 2026-03-24
Supplements: `verdict_narrative_v32.md` (Prompt 3) and `cross_reference_report_clean_v32.md` (Prompt 4)

---

## Executive Summary

The v3.2 pipeline — run on warmup-enriched data with bottom-up methodology — confirms a tradeable zone touch edge on NQ futures. The recommended deployment is a **2-tier priority waterfall** combining A-Eq ModeA (high-conviction, 96 P2 trades, PF 6.26 @4t baseline, 8.25 @4t with partials) with B-ZScore RTH (balanced, 309 P2 trades in non-overlapping waterfall, PF 4.18 @4t with tightened stop). Combined: 405 trades, PF 4.30 @4t.

Risk mitigation investigation (2026-03-24) validated M1 partial exits and M2 stop tightening + position sizing. No group earned a full "Yes" verdict (24 Conditional, 0 Yes). Paper trading is the correct next step.

---

## What Changed from Prior Analysis

| Dimension | Prior (v2/v3.1) | v3.2 Bottom-Up | Implication |
|-----------|-----------------|----------------|-------------|
| Dominant feature | F04 Cascade (#1, weight 20) | F10 Prior Penetration (#1, weight 10.0) | Cascade was overweighted in top-down calibration |
| Feature count | 14 | 7 (elbow) | Simpler model, lower overfit risk |
| VP Ray features | F03 weight 10 (#3) | Dead (HasVPRay=0) | VP Ray was a data pipeline artifact |
| Baseline PF | 0.90 (cold-start) | 1.34 (warmup-enriched) | Inherent edge is real, confirmed |
| SBB rate | ~34% | 7.3% | Warmup eliminates most spurious zones |
| Winner PF @4t | 4.67 (66 trades) | 6.26 (96 trades) | Stronger edge on cleaner data |
| Scoring approach | A-Cal (proportional weights) | A-Eq (equal weights) | Equal weights generalize better with low SBB |
| CT mode | Dead (M3 PF 1.06) | Viable at high score (PF 2.74) | Structural inversion: CT works with quality |
| Multi-mode | Not validated | Validated (PF 4.43, 423 trades) | B-ZScore complements A-Eq |
| New feature | — | F21 Zone Age (STRONG, STRUCTURAL) | Young zones bounce better |

---

## Deployment Configuration (Frozen, updated 2026-03-24 with risk mitigation)

### Priority Waterfall

```
ON EACH ZONE TOUCH EVENT:
  1. Compute 7 features: F10, F01, F05, F09, F21, F13, F04
  2. Compute A-Eq score (equal-weight, 0-70 scale)
  3. IF A-Eq score >= 45.5:
       → MODE 1: FIXED exit with partial targets
         Contracts = 3
         Entry = market (next bar open), EntryOffset = 0 (configurable)
         Stop = 190 ticks from entry
         T1 = 60 ticks (1 contract)     ← exits first
         T2 = 120 ticks (2 contracts)   ← runner, stop moves to entry after T1
         Time cap = 120 bars
         Alternative config: 1+1+1 (1ct@60t, 1ct@120t, 1ct@180t, BE after T1)
  4. ELSE:
       Compute B-ZScore (global StandardScaler)
       IF B-ZScore >= 0.50
          AND session = RTH
          AND seq <= 2
          AND TF <= 120m:
            → MODE 2: ZONEREL exit with position sizing
              Contracts = 3 if ZW < 150t, 2 if ZW 150-250t, 1 if ZW >= 250t
              Entry = market (next bar open), EntryOffset = 0 (configurable)
              Stop = max(1.3 × ZoneWidth, 100) ticks from entry
              Target = 1.0 × ZoneWidth ticks from entry
              Time cap = 80 bars
              No BE, no trail, no partials
  5. ELSE: SKIP (no trade)
```

### Risk Mitigation Modifications (validated 2026-03-24)

Changes from the pre-mitigation baseline, all P2-validated:

| Change | Mode | P1 Effect | P2 PF@4t | P2 Degrad | Source |
|--------|------|-----------|---------|-----------|--------|
| Partial exits (1+2) | M1 | PF 8.50 → 9.52 | 8.25 | -31.7% (improved) | B5 |
| Partial exits (1+1+1) | M1 | PF 8.50 → 9.00 | 8.31 | -32.6% (improved) | B5 |
| Stop 1.3xZW floor 100 | M2 | PF 4.61 → 4.67 | 4.18 | -2.0% (improved) | B2 |
| Position sizing by ZW | M2 | -- | -- | -- | C |

Rejected modifications (with evidence):
- Zone-fixed stop/target: PF jump was single-trade artifact (1 of 4 losers flipped)
- Deeper entries: fill rate too low (68% at 10t), selection bias in missed trades
- BE stops: P2 PF drops >50% on both modes
- M2 target reduction: 1.0xZW already optimal at every level tested
- M1 stop reduction: PF drops at every stop level
- M2 partials: degrade PF (4.61 to 4.27-4.54)
- TC tightening: degrades PF on both modes

See `shared/archetypes/zone_touch/output/risk_mitigation_investigation_v32.md`.

### Feature Bin Definitions (from P1, frozen)

| Feature | Type | Bins | Points (A-Eq: all 10/5/0) |
|---------|------|------|--------------------------|
| F10 (Prior Penetration) | Continuous | Low ≤155, Mid 155-473, High >473, NA | 10/5/0/5 |
| F01 (Timeframe) | Categorical | 90m=10, 120m/60m/30m/15m/240m/360m/720m=5, 480m=0 | Per-bin |
| F05 (Session) | Categorical | PreRTH=10, OD/Midday/Close=5, Overnight=0 | Per-bin |
| F09 (ZW/ATR Ratio) | Continuous | Low ≤3.71, Mid 3.71-9.42, High >9.42 | 10/5/0 |
| F21 (Zone Age) | Continuous | Low ≤110.2, Mid 110.2-1136.3, High >1136.3 | 10/5/0 |
| F13 (Close Position) | Continuous | Low ≤0.032, Mid 0.032-0.240, High >0.240 | 10/5/0 |
| F04 (Cascade State) | Categorical | NO_PRIOR=10, PRIOR_HELD=5, PRIOR_BROKE=0 | Per-bin |

A-Eq max score: 70. Threshold: 45.5 (65%).

### B-ZScore Parameters (frozen)

- Features: same 7 as A-Eq
- Normalization: global StandardScaler (mean/std frozen from P1)
- L1 regularization (coefficients frozen from P1)
- Window: 100 touches
- Threshold: 0.50
- Filters: RTH only, seq ≤ 2, TF ≤ 120m

---

## Validation Summary

### P2 One-Shot Results (frozen parameters, no recalibration)

| Mode | P2 Trades | PF @4t | WR% | Max DD | Profit/DD | Perm p | Rand %ile | Verdict |
|------|-----------|--------|-----|--------|-----------|--------|-----------|---------|
| A-Eq ModeA (baseline) | 96 | 6.26 | 94.8 | 193 | 22.5 | 0.002 | 99.7 | Conditional |
| A-Eq ModeA (1+2 partial) | 92 | **8.25** | 95.7 | -- | -- | -- | -- | **P2 PASS** |
| B-ZScore RTH (baseline)* | 309 | 4.10 | 76.4 | -- | -- | -- | -- | Conditional |
| B-ZScore RTH (1.3xZW stop) | 309 | **4.18** | 76.4 | -- | -- | -- | -- | **P2 PASS** |
| **Combined** | **423** | **4.43** | **—** | **647** | **47.6** | **—** | **—** | **DEPLOY COMBO** |

### P2a / P2b Consistency

| Mode | P2a PF @3t | P2b PF @3t | Direction |
|------|-----------|-----------|-----------|
| A-Eq ModeA | 4.80 | 11.52 | Improving |
| B-ZScore RTH | 3.39 | 5.20 | Improving |

Both modes show stable-to-improving PF from P2a to P2b. No evidence of edge decay within the holdout window.

### Overfit Risk Assessment

| Metric | Value | Interpretation |
|--------|-------|----------------|
| Winner PF / Baseline PF | 6.26 / 1.34 = 4.67x | Moderate overfit risk |
| STRUCTURAL feature weight | 85% of model | High mechanistic confidence |
| Feature count | 7 (elbow) | Low model complexity |
| SBB leak rate | 0.9% (A-Eq ModeA) | Negligible |
| P2a and P2b both profitable | Yes | Not a single-half fluke |
| Independent validation (B-ZScore) | PF 4.25 on 327 trades | Confirms edge via different method |

---

## Key Structural Insights from Cross-Reference

1. **F10 (Prior Penetration) is the true #1 feature** — not cascade (F04). Independent R/P spread: F10=1.371, F04=0.265. The prior top-down analysis overweighted cascade due to simultaneous calibration effects.

2. **VP Ray features are permanently dead** on warmup-enriched charts. HasVPRay=0 for all 3,278 P1 touches. The autotrader does not need VP Ray integration.

3. **Counter-trend works only with high zone quality.** CT + high A-Eq score: PF 2.74 (viable). CT + low score: PF 0.69 (dead). No trend filter is needed in the deployed model — the score threshold handles quality selection, making trend direction approximately neutral.

4. **F21 (Zone Age) is a new structural finding.** Young zones bounce better. This feature was not available in the prior analysis and entered the elbow as #5 (weight 2.95).

5. **Equal weighting generalizes better than calibrated weighting** when SBB contamination is low (7.3%). A-Eq's requirement for broad feature strength across all 7 dimensions produces a more robust quality filter than A-Cal's F10-dominant weighting.

---

## Study File Architecture

```
Sierra Chart Studies (live deployment):
  V4               — Zone detection (unchanged)
  ZoneTouchEngine   — Touch detection + feature export (replaces ZRA + ZB4)
  Autotrader        — Priority waterfall scoring + trade execution (new)

Autotrader routing:
  1. ZTE fires touch event with 7 features
  2. Autotrader computes A-Eq score
  3. If >= 45.5 → Mode 1 entry (FIXED exits)
  4. Else compute B-ZScore
  5. If >= 0.50 AND RTH AND seq<=2 AND TF<=120m → Mode 2 entry (ZONEREL exits)
  6. Else → no trade
```

This is a **single autotrader** with a priority waterfall, not two separate autotraders.

---

## Paper Trading Plan (P3)

| Parameter | Value |
|-----------|-------|
| Period | P3: Mar-Jun 2026 (M contract) |
| Expected trades/day | ~5.4 (A-Eq ~1.2 + B-ZScore RTH ~4.2, from P1 rates) |
| Expected total trades (60 trading days) | ~320 |
| Success criteria | Combined PF > 2.0 @4t on P3 |
| Failure criteria | Combined PF < 1.0 @4t at any 30-trade checkpoint |
| Monitoring | Daily trade log with feature scores, exit reasons, PnL |
| Comparison benchmark | P2 combined PF 4.43 @4t |

### What to Watch For

- **SBB leak rate creep:** If live SBB rate exceeds 15% (vs 0.9% in P2), the warmup-enriched training data may not match live conditions. Investigate V4 zone warmup configuration.
- **F10 null rate change:** If prior-touch features have >50% null rate live (vs 36% in P1), zone lifecycle dynamics may have shifted.
- **Mode 2 dominance:** B-ZScore RTH should produce ~3.5x more trades than A-Eq ModeA. If the ratio is >5x or <2x, investigate threshold calibration drift.
- **Win rate compression:** A-Eq ModeA WR should be 85-95%. If <80%, the 190t/60t exit structure may not suit the current regime.

---

## Open Items (Non-Blocking)

| Item | Priority | Description |
|------|----------|-------------|
| C++ multileg implementation | High | Implement M1 1+2 partial exits in autotrader (stop-to-BE after T1) |
| C++ M2 stop formula | High | Change M2 stop from max(1.5xZW,120) to max(1.3xZW,100) |
| C++ position sizing | High | Add ZW-conditional contract sizing for M2 |
| C++ EntryOffset param | Medium | Configurable deeper entry (default 0) for paper trade experimentation |
| Zone-fixed stop/target | Low | Future investigation — changes baseline, needs own P1/P2 cycle |
| Deferred Test D | Low | Replicate prior M1_A config on v3.2 data to confirm seq/TF gates unnecessary |
| 3-tier evaluation | Low | After P3 validates 2-tier, evaluate B-only (669 trades, PF 2.34) as 3rd tier |
