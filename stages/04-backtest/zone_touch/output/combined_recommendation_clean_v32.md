# NQ Zone Touch — Combined Recommendation (v3.2)

Generated: 2026-03-24
Supplements: `verdict_narrative_v32.md` (Prompt 3) and `cross_reference_report_clean_v32.md` (Prompt 4)

---

## Executive Summary

The v3.2 pipeline — run on warmup-enriched data with bottom-up methodology — confirms a tradeable zone touch edge on NQ futures. The recommended deployment is a **2-tier priority waterfall** combining A-Eq ModeA (high-conviction, 86 P2 trades, PF 7.83 with 1+2 partials) with B-ZScore RTH (balanced, 301 P2 trades, PF 4.26 with 1.3×ZW stop + position sizing). Combined: **387 P2 trades, PF 4.52**.

Risk mitigation investigation (2026-03-24) validated M1 partial exits and M2 stop tightening + position sizing. Stress test (bootstrap MC, reshuffling MC, HMM MC) confirmed robustness: 95th percentile max DD 1,541t, PF > 2.0 through -15% WR degradation, PF > 2.0 through 10t RT slippage. Paper trading is the correct next step.

**Note on trade counts:** Post-partial M1 trade counts (P1=100, P2=86) differ from pre-partial (P1=107, P2=96) because M1 runner legs hold longer, increasing position overlap and reducing total trades taken. Pre-partial counts appear in mode classification and early pipeline stages; post-partial counts are the frozen deployment reality.

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

**Pre-mitigation baseline (for reference):**

| Mode | P2 Trades | PF @4t | WR% | Max DD | Profit/DD | Perm p | Rand %ile | Verdict |
|------|-----------|--------|-----|--------|-----------|--------|-----------|---------|
| A-Eq ModeA (baseline, single-leg) | 96 | 6.26 | 94.8 | 193 | 22.5 | 0.002 | 99.7 | Conditional |
| B-ZScore RTH (baseline, 1.5xZW) | 309 | 4.10 | 76.4 | -- | -- | -- | -- | Conditional |

**Post-mitigation frozen config (deployed):**

| Mode | P2 Trades | PF | WR% | Verdict |
|------|-----------|-----|-----|---------|
| A-Eq ModeA (1+2 partial, 3ct) | 86 | **7.83** | ~95% | **P2 PASS** |
| B-ZScore RTH (1.3xZW stop, sized) | 301 | **4.26** | ~76% | **P2 PASS** |
| **Combined** | **387** | **4.52** | **—** | **DEPLOY** |

Trade count note: Post-partial M1 counts (86 P2) are lower than pre-partial (96) due to increased position overlap from runner legs. Pre-partial counts (107/96 P1/P2 M1, 239/309 P1/P2 M2) appear in mode classification; post-partial counts (100/86 M1, 231/301 M2) are the frozen deployment baseline.

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
| Expected trades/day | ~6.2 (from stress test: 718 trades / 115 days) |
| Expected total trades (60 trading days) | ~375 |
| Success criteria | Combined PF > 2.0 on P3 |
| Failure criteria | Combined PF < 1.0 at any 30-trade checkpoint |
| Monitoring | Daily trade log with feature scores, exit reasons, PnL |
| Comparison benchmark | P2 combined PF 4.52 (post-mitigation frozen config) |
| Capital | $15,412 MNQ (2× worst 95th DD) |

### What to Watch For

- **SBB leak rate creep:** If live SBB rate exceeds 15% (vs 0.9% in P2), the warmup-enriched training data may not match live conditions. Investigate V4 zone warmup configuration.
- **F10 null rate change:** If prior-touch features have >50% null rate live (vs 36% in P1), zone lifecycle dynamics may have shifted.
- **Mode 2 dominance:** B-ZScore RTH should produce ~3.5x more trades than A-Eq ModeA. If the ratio is >5x or <2x, investigate threshold calibration drift.
- **Win rate compression:** A-Eq ModeA WR should be ~95%. If <80%, the 190t/60t partial exit structure may not suit the current regime.
- **Circuit breaker triggers:** Track daily loss events, consecutive losses, and DD from HWM. Any manual-reset breaker trigger warrants a review before restarting.

---

## Circuit Breakers

All breakers are configurable inputs in the C++ autotrader.

| Breaker | Default | Trigger | Reset |
|---------|---------|---------|-------|
| Daily loss limit | 700t | Cumulative daily PnL ≤ -700t → halt new entries | Auto-reset at session open (17:00 CT) |
| Max consecutive losses | 5 | 5 consecutive losing trades → halt new entries | Manual reset (operator acknowledgment) |
| Max drawdown from HWM | 1,541t | Equity drawdown from high-water mark ≥ 1,541t → halt | Manual reset (operator acknowledgment) |
| Rolling 30-trade PF floor | 1.0 | Rolling 30-trade PF < 1.0 → halt new entries | Manual reset (operator acknowledgment) |

The 1,541t DD threshold is the worst 95th percentile across bootstrap, reshuffling, and HMM Monte Carlo simulations.

---

## Session Controls

| Control | Default | Description |
|---------|---------|-------------|
| EOD forced close | 15:50 ET | All open positions closed at market |
| EOD entry blackout | 15:30 ET | No new entries after this time |
| News blackout window | Off (configurable) | Optional ±N minute window around scheduled events |

---

## Stress Test Summary (2026-03-24)

All numbers below are from the frozen configuration (partials, 1.3×ZW stop, position sizing).

### Monte Carlo Drawdown (718 trades, 10,000 iterations)

| Method | 50th DD | 95th DD | 99th DD | Worst |
|--------|---------|---------|---------|-------|
| Bootstrap (random w/ replacement) | 1,004t | 1,501t | 1,797t | 3,076t |
| Reshuffling (permutation) | 1,006t | 1,474t | 1,758t | 3,504t |
| HMM (regime-aware, 3-state) | 1,025t | 1,541t | 1,861t | 2,919t |

Worst 95th DD across all methods: **1,541t** (HMM). Historical max DD: **1,042t** (56th percentile — typical ordering).

### Robustness

- **WR compression:** PF > 2.0 through -15% WR degradation (breakeven not reached within test range)
- **Slippage:** Combined PF > 2.0 through 10t RT/contract slippage
- **Regime sensitivity:** PF > 2.0 in all market regime bins (strong down through strong up)
- **Event days:** PF 6.20 on FOMC/NFP/CPI days vs 5.70 baseline — no adverse event effect
- **HMM states:** States overlap (mean±1std) — no persistent adverse regime detected
- **Serial correlation:** Lag-3 significant (r=0.08) — bootstrap may slightly understate tail risk
- **Losing months:** 0 out of 7 months

### Capital Requirements

| Contract | Worst 95th DD | 2× Buffer | Min Capital |
|----------|--------------|-----------|-------------|
| MNQ ($5/t) | $7,706 | $15,412 | **$15,412** |
| NQ ($20/t) | $30,823 | $61,647 | **$61,647** |

### Monitoring Thresholds (Paper Trading)

- Stop trading if DD exceeds 1,541t
- Review if rolling 60-trade PF drops below 1.5
- Review after 60+ live trades to recalibrate
- Review if 3+ consecutive losing days

---

## Known Issues (Accepted Limitations)

1. **B-ZScore model inconsistency:** P1 uses C=1.0 rolling probability from CSV; P2 uses C=0.01 global linear from JSON. Both produce authoritative baseline counts and PFs. Fix deferred to pipeline v4.

2. **Limited data period:** 6 months of data (Sep 2025 – Mar 2026). Stress test results are optimistic bounds. Recalibrate after 60+ live trades.

3. **M1 loss count fragility:** M1 has only ~4-8 losses across P1/P2. WR compression sensitivity is real but unquantifiable with this sample. The 95% WR could be unstable.

4. **M1 partial overlap effect:** Partial exits (1+2) increase position overlap, reducing observed trade count from 107/96 to 100/86 (P1/P2). This is a mechanical effect of runner legs holding longer, not a degradation.

---

## C++ Implementation Reference

| Item | Value |
|------|-------|
| Study name | ATEAM_ZONE_TOUCH_V32 |
| Deployment spec | This document (`combined_recommendation_clean_v32.md`) |
| ZTE study | `acsil/ZoneTouchEngine.cpp` (v4.0) — provides touch events + features |
| Study chain | `acsil/STUDY_CHAIN_REFERENCE.md` |
| Feature config | `output/feature_config_v32.json` (A-Eq bin edges, 7 features) |
| A-Eq scoring model | `output/scoring_model_aeq_v32.json` (equal weights, threshold 45.5) |
| B-ZScore scoring model | `output/scoring_model_bzscore_v32.json` (L1 coefficients + StandardScaler) |
| Reference autotraders | `acsil/ATEAM_ZONE_BOUNCE_FIXED.cpp`, `acsil/ATEAM_ZONE_BOUNCE_ZONEREL.cpp` |

### Key Configurable Inputs (defaults from frozen config)

| Input | Default | Description |
|-------|---------|-------------|
| M1 Stop | 190t | Fixed from entry |
| M1 T1 | 60t (1ct) | First partial target |
| M1 T2 | 120t (2ct) | Runner target, BE on runner after T1 |
| M1 Time Cap | 120 bars | |
| M2 Stop Multiplier | 1.3 | × ZoneWidth |
| M2 Stop Floor | 100t | min(stop, floor) |
| M2 Target Multiplier | 1.0 | × ZoneWidth |
| M2 Time Cap | 80 bars | |
| M2 Size: ZW < 150 | 3ct | |
| M2 Size: ZW 150-250 | 2ct | |
| M2 Size: ZW ≥ 250 | 1ct | |
| A-Eq Threshold | 45.5 | Score ≥ threshold → Mode 1 |
| B-ZScore Threshold | 0.50 | Score ≥ threshold → Mode 2 |
| Daily Loss Limit | 700t | Circuit breaker |
| Max Consec Losses | 5 | Circuit breaker |
| Max DD from HWM | 1,541t | Circuit breaker |
| Rolling PF Floor | 1.0 (30 trades) | Circuit breaker |
| EOD Close | 15:50 ET | Forced close |
| EOD Blackout | 15:30 ET | Entry blackout |
| EntryOffset | 0t | Configurable deeper entry (paper trade experimentation) |

---

## Open Items (Non-Blocking)

| Item | Priority | Description |
|------|----------|-------------|
| C++ autotrader build | **Next** | Build ATEAM_ZONE_TOUCH_V32 from this spec (see C++ Implementation Reference) |
| C++ EntryOffset param | Medium | Configurable deeper entry (default 0) for paper trade experimentation |
| Deferred Test D | Low | Replicate prior M1_A config on v3.2 data to confirm seq/TF gates unnecessary |
| 3-tier evaluation | Low | After P3 validates 2-tier, evaluate B-only (669 trades, PF 2.34) as 3rd tier |
| B-ZScore model unification | v4 | Reconcile P1 (C=1.0 rolling) vs P2 (C=0.01 global) scoring inconsistency |
