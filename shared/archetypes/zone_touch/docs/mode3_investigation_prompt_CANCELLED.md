# Mode 3 Investigation — LowATR Residual Addition to Combo 1

**Purpose:** Determine whether adding a third tier (B-ZScore LowATR trades NOT 
already in Combo 1) improves the combined deployment configuration. If the 
residual LowATR population has decent standalone PF, it adds throughput without 
diluting existing Modes 1+2.

**Branch:** `main`
**Pipeline version:** 3.2 (model frozen)
**Date:** 2026-03-24

**Context:** Combo 1 uses a 2-tier waterfall: Mode 1 (A-Eq ModeA) → Mode 2 
(B-ZScore RTH). Combo 2 uses Mode 1 → B-ZScore LowATR. These overlap but are 
NOT subsets of each other — some LowATR trades are ETH (not in RTH filter), and 
some RTH trades are high-ATR (not in LowATR filter). The non-overlapping LowATR 
residual is a potentially complementary population.

⚠️ THE SCORING MODEL IS FROZEN. Trade selection thresholds do not change 
(A-Eq ≥ 45.5, B-ZScore ≥ 0.50). This investigation only determines whether the 
LowATR residual population merits its own tier in the waterfall.

---

## Frozen Combo 1 Configuration (from risk mitigation)

| Metric | Mode 1 (A-Eq ModeA) | Mode 2 (B-ZScore RTH) |
|--------|---------------------|----------------------|
| P1 trades | 107 | 239 |
| P2 trades | 96 | 309 |
| Stop | 190t fixed | 1.3×ZW floor 100t |
| Target | 60t (partial: 1+2 or 1+1+1) | 1.0×ZW |
| TC | 120 bars | 80 bars |
| Position sizing | 3ct | 3ct ZW<150 / 2ct 150-250 / 1ct 250+ |

⚠️ Mode 1 is identical across all combos. This investigation only concerns the 
Mode 2/3 tier.

---

## File Locations

```
SCORED TOUCHES:
  c:\Projects\pipeline\shared\archetypes\zone_touch\output\p1_scored_touches_aeq_v32.csv
  c:\Projects\pipeline\shared\archetypes\zone_touch\output\p1_scored_touches_bzscore_v32.csv

RAW DATA:
  c:\Projects\pipeline\stages\01-data\data\touches\NQ_ZTE_raw_P1.csv
  c:\Projects\pipeline\stages\01-data\data\touches\NQ_ZTE_raw_P2.csv

SIMULATION:
  c:\Projects\pipeline\shared\archetypes\zone_touch\zone_touch_simulator.py
  c:\Projects\pipeline\shared\archetypes\zone_touch\risk_mitigation_v32.py

SCORING:
  c:\Projects\pipeline\shared\archetypes\zone_touch\output\scoring_model_bzscore_v32.json

MODE CLASSIFICATION:
  c:\Projects\pipeline\shared\archetypes\zone_touch\output\mode_classification_v32.md
```

⚠️ B-ZScore scoring inconsistency: P1 uses Score_BZScore from CSV (C=1.0 
probability). P2 uses JSON score_bzscore() (C=0.01 raw linear). Both threshold 
0.50. Use the same approach as the risk mitigation investigation.

---

## Step 1: Build the Three Populations

### 1a: Define Mode 2 (RTH) and LowATR populations

**Mode 2 (RTH) — same as Combo 1:**
- B-ZScore ≥ 0.50 AND RTH AND seq ≤ 2 AND TF ≤ 120m
- Exclude Mode 1 overlap (A-Eq has priority)

**LowATR — same as Combo 2:**
- B-ZScore ≥ 0.50 AND LowATR segment
- Exclude Mode 1 overlap

⚠️ CHECK: What is the LowATR definition? Find it in the mode classification output 
or the Combo 2 spec. It should be a segment from the B-ZScore segmentation — 
likely Seg4 LowATR. Confirm the exact filter definition before proceeding.

⚠️ CRITICAL: Does the LowATR filter also include seq ≤ 2 AND TF ≤ 120m gates? 
Mode 2 (RTH) requires these. If LowATR does NOT, then Mode 3 residual could 
include seq>2 or TF>120m trades that were excluded from Mode 2 for QUALITY 
reasons, not session reasons. Check the Combo 2 spec for the exact filter chain. 
If LowATR has no seq/TF gates, apply them anyway for Mode 3 — otherwise you are 
adding trades that failed Mode 2's quality filter through a back door.

### 1b: Compute the residual (Mode 3)

Mode 3 = LowATR trades that are NOT in Mode 2 (RTH).

```
mode_3 = lowATR_qualifying - mode_1_trades - mode_2_trades
```

A trade is in Mode 3 if:
- B-ZScore ≥ 0.50
- Passes LowATR segment filter
- Does NOT pass RTH filter (otherwise it's already in Mode 2)
- Not a Mode 1 trade

📌 REMINDER: A trade can be in both RTH and LowATR if it's a low-volatility RTH 
session trade. Those trades are ALREADY in Mode 2. Mode 3 captures only the 
LowATR trades that RTH missed — typically ETH/overnight low-volatility trades.

### 1c: Count verification

Report for BOTH P1 and P2:

| Population | P1 Count | P2 Count |
|-----------|----------|----------|
| Mode 1 (A-Eq) qualifying | ? | ? |
| Mode 2 (RTH) qualifying, excl M1 | ? | ? |
| LowATR qualifying, excl M1 | ? | ? |
| **Overlap (in both M2 and LowATR)** | ? | ? |
| **Mode 3 residual (LowATR NOT in M2)** | ? | ? |

⚠️ If Mode 3 residual is < 20 trades on P1, the population is too small for 
reliable analysis. Report the finding and stop — Mode 3 is not viable.

---

## Step 2: Characterize Mode 3 Residual

For the Mode 3 residual population on P1:

| Attribute | Mode 2 (RTH) | Mode 3 (LowATR residual) | Different? |
|-----------|-------------|--------------------------|-----------|
| Mean B-ZScore | ? | ? | ? |
| Mean zone width | ? | ? | ? |
| Session distribution | RTH by definition | ? (expect ETH/overnight) | ? |
| Timeframe distribution | ? | ? | ? |
| Mean score (A-Eq if available) | ? | ? | ? |

⚠️ KEY QUESTION: What sessions are Mode 3 trades from? If they're predominantly 
overnight/ETH, they operate in different liquidity conditions than Mode 2 RTH. 
This doesn't disqualify them, but the exit parameters may need different 
calibration (tighter stops, smaller targets due to lower volatility).

📌 REMINDER: The scoring model is FROZEN. We are characterizing an existing 
population, not creating new features or thresholds.

---

## Step 3: Simulate Mode 3 with Candidate Exit Parameters

⚠️ Mode 3 may need different exits than Mode 2. The Combo 2 spec used 0.5×ZW 
target (not 1.0×ZW). Test both:

⚠️ STANDALONE LIMITATION: These tests simulate Mode 3 in isolation (no position 
overlap from M1/M2). In the combined waterfall, many Mode 3 qualifying trades are 
blocked by active M1/M2 positions. The exit parameters optimized here may not be 
perfectly optimal on the smaller traded subset. This is acceptable for parameter 
selection -- the combined simulation in Step 4 will show the actual deployed PF.

### 3a: Mode 3 with Mode 2 exits (1.3×ZW floor 100 stop, 1.0×ZW target, TC 80)

| Metric | P1 Value |
|--------|---------|
| Trades | ? |
| PF @3t | ? |
| WR% | ? |
| Mean Win | ? |
| Mean Loss | ? |
| L:W | ? |
| TC exits | ? (% of trades) |

### 3b: Mode 3 with LowATR exits (1.3×ZW floor 100 stop, 0.5×ZW target, TC 80)

| Metric | P1 Value |
|--------|---------|
| Trades | ? |
| PF @3t | ? |
| WR% | ? |
| Mean Win | ? |
| Mean Loss | ? |
| L:W | ? |
| TC exits | ? (% of trades) |

⚠️ If TC exits dominate with 1.0×ZW target (>60%), the 0.5×ZW target is likely 
better for this population. If TC exits are moderate (<40%) with 1.0×ZW, the 
wider target captures more per trade.

### 3c: Mode 3 target sweep (if neither 3a nor 3b is clearly best)

| Target | PF @3t | WR% | TC Exits % |
|--------|--------|-----|-----------|
| 0.5×ZW | ? | ? | ? |
| 0.6×ZW | ? | ? | ? |
| 0.7×ZW | ? | ? | ? |
| 0.8×ZW | ? | ? | ? |
| 1.0×ZW | ? | ? | ? |

Pick the PF-maximizing target.

📌 REMINDER: Stop is 1.3×ZW floor 100t for all tests (transferred from M2 risk 
mitigation). Only the target varies.

---

## Step 4: Combined Performance (Modes 1+2+3)

### 4a: Simulate the 3-tier waterfall on P1

Run the position-overlap-aware simulator with priority: Mode 1 > Mode 2 > Mode 3.
A trade goes to the highest tier it qualifies for. Only one position at a time.

WARNING: Use the FROZEN risk mitigation config for M1 and M2:
- M1: 1+2 partial exits (1ct@60t + 2ct@120t, BE on runner after T1), stop 190t, TC 120
- M2: stop 1.3xZW floor 100t, target 1.0xZW, TC 80
- M3: best exit params from Step 3
M1 partials increase hold time (runner leg stays open after T1). This reduces 
availability for M2/M3 signals. The combined sim MUST use partials to get 
realistic overlap behavior.

WARNING - PREEMPTION RULE: Higher-priority signals preempt lower-priority positions.
- Mode 1 signal while in Mode 3 position: CLOSE Mode 3 at market, ENTER Mode 1
- Mode 1 signal while in Mode 2 position: CLOSE Mode 2 at market, ENTER Mode 1
- Mode 2 signal while in Mode 3 position: CLOSE Mode 3 at market, ENTER Mode 2
- Mode 3 signal while in Mode 1 or 2 position: SKIP (no preemption upward)

Preempted trades close at the bar Open of the preempting signal's bar. Their PnL 
is whatever the position had at that moment -- could be positive, negative, or 
scratch. Report the number of preempted trades and their mean PnL separately.

WARNING: WITHOUT PREEMPTION, adding Mode 3 can HURT performance by blocking 
higher-quality signals. If Mode 3 preemption cost (forced early exits on trades 
that get preempted) exceeds Mode 3 profit contribution, the tier destroys value.

WARNING: ALSO RUN WITHOUT PREEMPTION (simple skip) for comparison. If preemption 
adds complexity but doesn't materially change combined PF, the simpler skip logic 
is preferable for C++ implementation.

Report ALL FOUR scenarios to isolate preemption vs Mode 3 effects:

| Metric | C1 skip (baseline) | C1 preempt | C1+M3 skip | C1+M3 preempt |
|--------|-------------------|-----------|-----------|---------------|
| P1 Trades | 346 | ? | ? | ? |
| P1 PF @3t | ? | ? | ? | ? |
| P1 WR% | ? | ? | ? | ? |
| P1 Profit/DD | ? | ? | ? | ? |
| M3 trades taken | 0 | 0 | ? | ? |
| M3 incremental PF | -- | -- | ? | ? |
| Preempted M2 by M1 | 0 | ? | 0 | ? |
| Preempted M3 by M1/M2 | 0 | 0 | 0 | ? |
| Mean preempted PnL | -- | ? | -- | ? |

"C1 preempt" = Combo 1 only (no Mode 3) but with Mode 1 preempting Mode 2. 
This isolates the preemption benefit on the existing 2-tier waterfall. If C1 
preempt >> C1 skip, preemption is valuable INDEPENDENT of Mode 3.

### 4b: Position sizing for Mode 3

Based on Mode 3's zone width distribution and PF, propose sizing:

| Condition | Contracts | Rationale |
|-----------|-----------|-----------|
| Mode 3, ZW < 150t | ? | ? |
| Mode 3, ZW 150-250t | ? | ? |
| Mode 3, ZW 250+ | ? | ? |

---

## Step 5: P2 Validation

⚠️ ONE-SHOT HOLDOUT. Run after P1 analysis is complete and Mode 3 configuration 
is frozen. Use whichever overlap mode (skip or preempt) performed best on P1.

⚠️ If preemption won on P1, the P2 Combo 1 baseline must ALSO use preemption 
(Mode 1 preempting Mode 2) for a fair comparison. Do not compare preempted 
3-tier P2 against skip-mode Combo 1 P2.

### 5a: P2 3-tier waterfall

WARNING: The 4.30 combined P2 PF is the PRE-risk-mitigation baseline (flat M1 
exits, 1.5xZW M2 stop). Compute the POST-risk-mitigation Combo 1 P2 PF first 
(M1 with 1+2 partials + M2 with 1.3xZW stop). This is the correct comparison 
baseline. It should be HIGHER than 4.30.

| Metric | P2 Combo 1 (post-RM) | P2 Combo 1+3 | Change |
|--------|---------------------|-------------|--------|
| Trades | ? | ? | ? |
| PF @4t | ? (compute fresh) | ? | ? |
| WR% | ? | ? | ? |
| Profit/DD | ? | ? | ? |

⚠️ PASS CRITERIA:
- Combined P2 PF must not degrade by more than 15% vs post-RM Combo 1 P2 PF
- Mode 3 standalone P2 PF must be > 1.5 (otherwise not worth adding)
- If combined PF degrades but total profit increases meaningfully, report as 
  TRADEOFF — stress test will determine if the throughput gain justifies the 
  PF dilution

📌 REMINDER: P2 is one-shot. No recalibration after seeing P2 results.

---

## Step 6: Verdict and Recommendation

Three possible outcomes:

**A. Mode 3 passes P2 and improves combined profile:**
→ Adopt 3-tier waterfall. Update deployment spec. Stress test runs on 3-tier.

**B. Mode 3 passes P2 but dilutes PF without enough throughput gain:**
→ Keep 2-tier (Combo 1). Mode 3 is a paper trading experiment — configurable in 
C++ autotrader as an optional tier.

**C. Mode 3 has too few trades or fails P2:**
→ Discard. 2-tier Combo 1 is the final configuration.

⚠️ If verdict is A or B, the C++ autotrader should support configurable tier 
enable/disable so Mode 3 can be toggled during paper trading.

---

## Output Files

Save to: `c:\Projects\pipeline\shared\archetypes\zone_touch\output\`
- `mode3_investigation_v32.md` — this report
- Update `combined_recommendation_clean_v32.md` if Mode 3 is adopted

Commit to `main` with message:
"Investigate Mode 3 (LowATR residual) for 3-tier waterfall"

---

## Self-Check Before Submitting

- [ ] LowATR segment definition confirmed from mode classification
- [ ] LowATR seq/TF gates confirmed (applied if Combo 2 spec had them)
- [ ] Combo 1 preempt tested as separate scenario (isolates preemption from Mode 3)
- [ ] Mode 3 residual correctly excludes Mode 1 AND Mode 2 trades
- [ ] Overlap between RTH and LowATR quantified
- [ ] B-ZScore scoring matches risk mitigation approach (P1 CSV, P2 JSON)
- [ ] Mode 3 tested with both 1.0×ZW and 0.5×ZW targets
- [ ] Combined simulation tested WITH and WITHOUT preemption
- [ ] Preempted trade count and mean PnL reported
- [ ] Combined simulation is position-overlap-aware (priority waterfall)
- [ ] Mode 3 throughput reported (qualifying vs actually traded after overlap)
- [ ] P2 Combo 1 baseline computed with post-risk-mitigation config (not stale 4.30)
- [ ] Combined simulation uses M1 partials (1+2) — not flat exits
- [ ] P2 validation is one-shot
- [ ] Incremental PF of Mode 3 trades reported separately from combined PF
- [ ] Scoring model confirmed FROZEN throughout
