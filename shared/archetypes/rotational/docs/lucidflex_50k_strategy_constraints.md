# LucidFlex 50K — Strategy Constraint Analysis

**Created:** 2026-03-25
**References:**
- [martingale_rotation_math.md](martingale_rotation_math.md) — strategy formulas
- [lucidflex_50k_rules.md](lucidflex_50k_rules.md) — prop firm rules
- Study: `ATEAM_ROTATION_V3_V2803.cpp`

**Purpose:** Maps the martingale rotation formulas onto the LucidFlex 50K prop firm constraints. Identifies which prop firm rule binds at each phase and how position sizing (minis vs micros) affects the viable operating envelope.

---

## Binding Constraints by Phase

At each phase, one constraint dominates. The others are slack.

| Phase | Binding Constraint | Secondary Constraint |
|-------|-------------------|---------------------|
| Eval | $2,000 MLL (EOD) | 50% consistency rule |
| Funded ($0–$999) | Scaling: 2 minis / 20 micros | $2,000 MLL trailing (not yet locked) |
| Funded ($1,000–$1,999) | Scaling: 3 minis / 30 micros | $2,000 MLL trailing |
| Funded ($2,000+) | $2,000 MLL (locked at $50,100) | Scaling no longer constrains (4 minis = eval cap) |
| LucidLive | Day-1 capital ($2,400) | Escrow release gates |

---

## Minis vs Micros: Position Sizing Choice

The scaling plan specifies limits in **minis OR micros** (1 mini = 10 micros). The choice of base unit fundamentally changes the martingale's operating characteristics.

### NQ Contract Values

| Contract | $/point | $/tick |
|----------|---------|--------|
| Mini (NQ) | $20 | $5.00 |
| Micro (MNQ) | $2 | $0.50 |

### Minis at Each Scaling Tier

With `InitialQty = 1 mini`, the doubling sequence is 1 → 2 → 4 → 8.

| Tier | Max Size | Max Depth ($k^*$) | Risk/Reward | Breakeven $W$ | Profit/Cycle | MaxDD/Cycle |
|------|----------|-------------------|-------------|---------------|-------------|-------------|
| $0–$999 | 2 minis | 1 add | 1:1 | 50% | $d \times \$20$ | $d \times \$20$ |
| $1k–$2k | 3 minis | 1 + partial | irregular | irregular | $d \times \$20$ | irregular |
| $2,000+ | 4 minis | 2 adds | 3:1 | 75% | $d \times \$20$ | $3d \times \$20$ |

With $d = 2.0$ pts:
- Profit/cycle: $2.0 \times \$20 = \$40$
- MaxDD at tier 1 (depth 1): $2.0 \times \$20 = \$40$
- MaxDD at tier 3 (depth 2): $6.0 \times \$20 = \$120$

**Cycles to reach $1,000 (unlock tier 2):** $1,000 / \$40 = 25$ completed cycles

### Micros at Each Scaling Tier

With `InitialQty = 1 micro`, the doubling sequence is 1 → 2 → 4 → 8 → 16.

| Tier | Max Size | Max Depth ($k^*$) | Risk/Reward | Breakeven $W$ | Profit/Cycle | MaxDD/Cycle |
|------|----------|-------------------|-------------|---------------|-------------|-------------|
| $0–$999 | 20 micros | 4 adds | 15:1 | 93.75% | $d \times \$2$ | $15d \times \$2$ |
| $1k–$2k | 30 micros | 4 adds | 15:1 | 93.75% | $d \times \$2$ | $15d \times \$2$ |
| $2,000+ | 40 micros | 5 adds | 31:1 | 96.88% | $d \times \$2$ | $31d \times \$2$ |

With $d = 2.0$ pts:
- Profit/cycle: $2.0 \times \$2 = \$4$
- MaxDD at depth 4: $30.0 \times \$2 = \$60$

**Cycles to reach $1,000 (unlock tier 2):** $1,000 / \$4 = 250$ completed cycles

### Scaled Micros: The Middle Ground

Using a larger micro base size recovers meaningful per-cycle profit while staying within scaling limits.

**`InitialQty = 5 micros` at $0–$999 tier (20 micro cap):**

| Adds (k) | Add Qty | Total Position | MaxDD ($) |
|-----------|---------|----------------|-----------|
| 0 (seed) | 5 | 5 micros | — |
| 1 | 5 | 10 micros | $20 |
| 2 | 10 | 20 micros | $60 |

- Effective depth: $k^* = 2$ (20 micros = tier cap)
- Profit/cycle: $5 \times 2.0 \times \$2 = \$20$
- MaxDD at depth 2: $\$60$
- Risk/reward: **3:1**
- Breakeven: **75%**
- Cycles to $1,000: **50**

**`InitialQty = 2 micros` at $0–$999 tier (20 micro cap):**

| Adds (k) | Add Qty | Total Position | MaxDD ($) |
|-----------|---------|----------------|-----------|
| 0 (seed) | 2 | 2 micros | — |
| 1 | 2 | 4 micros | $8 |
| 2 | 4 | 8 micros | $24 |
| 3 | 8 | 16 micros | $56 |

- Effective depth: $k^* = 3$ (next add = 16 more, total 32 > 20 cap)
- Profit/cycle: $2 \times 2.0 \times \$2 = \$8$
- MaxDD at depth 3: $\$56$
- Risk/reward: **7:1**
- Breakeven: **87.5%**
- Cycles to $1,000: **125**

### Comparison Table (All Configurations at $0–$999 Tier)

| Config | Base Unit | InitialQty | Max Depth | Profit/Cycle | MaxDD/Cycle | Risk/Reward | Breakeven | Cycles to $1K | MaxDD as % of MLL |
|--------|-----------|-----------|-----------|-------------|-------------|-------------|-----------|--------------|-------------------|
| A | Mini | 1 | 1 | $40 | $40 | 1:1 | 50% | 25 | 2.0% |
| B | Micro | 1 | 4 | $4 | $60 | 15:1 | 93.75% | 250 | 3.0% |
| C | Micro | 2 | 3 | $8 | $56 | 7:1 | 87.5% | 125 | 2.8% |
| D | Micro | 5 | 2 | $20 | $60 | 3:1 | 75% | 50 | 3.0% |
| E | Micro | 10 | 1 | $40 | $40 | 1:1 | 50% | 25 | 2.0% |

Config E (10 micros = 1 mini) produces identical results to Config A — confirming micros vs minis is purely a granularity choice.

---

## MLL Budget Analysis

The $2,000 MLL limits how many cycles can fail consecutively before account breach.

**Max consecutive failures before breach** (starting from $50,000, no prior profits):

$$N_{\text{fail}} = \left\lfloor \frac{\$2,000}{\text{MaxDD per cycle}} \right\rfloor$$

| Config | MaxDD/Cycle | Max Consecutive Failures |
|--------|-------------|------------------------|
| A (1 mini) | $40 | 50 |
| B (1 micro) | $60 | 33 |
| C (2 micros) | $56 | 35 |
| D (5 micros) | $60 | 33 |
| E (10 micros) | $40 | 50 |

All configurations can absorb 33+ consecutive max-depth failures before breaching MLL. Per-cycle risk is small relative to the $2,000 budget.

**However:** this assumes every failure hits max depth. With a hard stop set tighter than max depth, the loss per failure is smaller and the failure count tolerance increases.

---

## Trailing Drawdown Interaction

Before the MLL locks at $52,100, the trailing drawdown creates a dynamic constraint. The effective buffer is always $2,000 below the highest EOD close, not $2,000 below starting balance.

**Scenario: early funded with Config D (5 micros), profitable start:**

| Day | EOD Close | HWM | MLL | Effective Buffer |
|-----|-----------|-----|-----|-----------------|
| 1 | $50,100 | $50,100 | $48,100 | $2,000 |
| 5 | $50,500 | $50,500 | $48,500 | $2,000 |
| 10 | $50,300 | $50,500 | $48,500 | $1,800 |

On Day 10: balance dropped but MLL didn't — effective buffer shrank to $1,800. This is the trailing drawdown squeeze. The buffer is always $2,000 if you're at your HWM, but any pullback from HWM reduces it.

**Key property:** The trailing drawdown doesn't change per-cycle risk (MaxDD/cycle stays the same). It changes **how many losing cycles the account can absorb** during a drawdown from HWM. The MLL only moves up, never down — so [OPINION] a profit run followed by a losing streak is more dangerous than steady performance, because the floor has risen while the balance drops.

---

## Consistency Rule Interaction (Eval Only)

The 50% consistency rule constrains how the eval can be passed. With Config A ($40/cycle profit):

- Profit target: $3,000
- Max single-day profit: ~$1,560 (with cushion)
- Max cycles per day at $40 each: $1,560 / $40 = 39 cycles before hitting consistency cap
- Minimum days: 2 (need at least $1,440 on other days)

With Config D ($20/cycle):
- Max cycles per day: $1,560 / $20 = 78 cycles
- The consistency rule is less likely to bind at smaller per-cycle profit

**Note:** During eval, scaling doesn't apply — full 4 minis / 40 micros available. The constraint analysis above (2-mini / 20-micro starting cap) applies only to funded phase.

---

## Microscalping Rule Interaction

Lucid flags accounts where >50% of profits come from trades held ≤5 seconds. The rotation strategy's hold time depends on:

- `StepDist` — larger step = longer time for price to move $d$ points
- Market volatility — fast markets complete cycles faster
- Martingale depth — deeper cycles take longer (multiple adds before reversal)

With $d = 2.0$ pts on NQ, [SPECULATION] a cycle could complete very quickly during volatile periods. The speed filter (if active) may partially address this by disabling trading during fast tape — which is also when sub-5-second cycles would be most likely.

---

## Summary: Viable Operating Envelopes

### Eval Phase (4 minis / 40 micros available)

Full position sizing available. MLL ($2,000) and consistency (50%) are the binding constraints. No scaling limitation.

### Early Funded ($0–$999, 2 minis / 20 micros)

| Approach | Tradeoff |
|----------|----------|
| 1 mini, depth 1 | Fastest to $1,000 (25 cycles), but 1:1 risk/reward — needs >50% win rate |
| 5 micros, depth 2 | Moderate pace (50 cycles), 3:1 risk/reward — needs >75% win rate |
| 2 micros, depth 3 | Slower (125 cycles), 7:1 risk/reward — needs >87.5% win rate |
| 1 micro, depth 4 | Slowest (250 cycles), 15:1 risk/reward — needs >93.75% win rate |

### Mid Funded ($1,000–$1,999, 3 minis / 30 micros)

Transitional tier. Geometric doubling doesn't fit cleanly into 3 minis. Micros provide clean depth options.

### Full Funded ($2,000+, 4 minis / 40 micros)

Same as eval position limits. MLL (now locked at $50,100) is the only binding constraint.

---

## Monte Carlo / Probability Framework

Reference: Gambler's Ruin with drift, applied to prop firm evaluation. Framework validated by ORB strategy practitioners using years of trade data and Monte Carlo simulation.

### Core Formulas

**Probability of passing (hitting profit target before MLL breach):**

$$P_{\text{pass}} \approx \frac{1 - e^{-2E[R] D_R / \sigma^2}}{1 - e^{-2E[R](D_R + T_R)/\sigma^2}}$$

Where:
- $E[R]$ = expected return per cycle (the edge/drift)
- $\sigma$ = standard deviation of returns per cycle
- $D_R$ = drawdown limit ($2,000 for LucidFlex 50K)
- $T_R$ = profit target ($3,000 for eval)

**Parameterized by risk fraction $r$:**

$$P_{\text{pass}}(r) = \frac{1 - e^{-2E[R] D / (r\sigma^2)}}{1 - e^{-2E[R](D+T)/(r\sigma^2)}}$$

Where $D = D_R/r$ and $T = T_R/r$.

**Optimal Kelly fraction:**

$$f^* = \frac{E[R]}{\sigma^2}$$

**Practical risk sizing (fractional Kelly):**

$$r^* \approx \alpha \cdot \frac{D \cdot E[R]}{\sigma^2} \quad \text{where } \alpha \in [0.1, 0.3]$$

**PropScore (composite pass-probability metric):**

$$\text{PropScore} = \frac{E[R]}{\sigma} \cdot \sqrt{\frac{D}{T}}$$

### Applying to Rotation Strategy

The rotation strategy produces discrete cycles with known payoff structure. Each cycle is one observation for the probability framework.

**Inputs needed from rotation data:**

| Input | Source | Notes |
|-------|--------|-------|
| $E[R]$ | Mean cycle P&L | Must be per CYCLE, not per order or per day |
| $\sigma$ | Std dev of cycle P&L | Same — per cycle |
| Cycle count | Total completed + stopped cycles | Sample size for confidence intervals |
| Win rate | Completed cycles / total cycles | Cross-check against breakeven $W_{\min}$ |

**LucidFlex parameters for the formulas:**

| Parameter | Eval | Funded |
|-----------|------|--------|
| $D$ (drawdown limit) | $2,000 | $2,000 (trailing, then locked) |
| $T$ (profit target) | $3,000 | Payout threshold (varies) |

### Applicability and Gaps

The $P_{\text{pass}}$ formula assumes:
1. Returns are approximately normally distributed
2. The drawdown barrier is static (fixed $D$)
3. Trades are independent

How these hold for the rotation strategy:

| Assumption | Fit | Impact |
|------------|-----|--------|
| Normal returns | Poor — returns are bimodal (+$q_0 d$ or −stop loss) | Monte Carlo more reliable than closed-form |
| Static barrier | Poor during early funded (trailing MLL) / Good after lock | Must model trailing MLL explicitly in simulation |
| Independence | [SPECULATION] Uncertain — cycles are serially linked (reversal exit = next seed) | Autocorrelation may be weak enough to ignore; measure from data |

**Recommendation:** Use $P_{\text{pass}}$ and PropScore as quick screening metrics. Use Monte Carlo with explicit LucidFlex rules (trailing EOD drawdown, scaling tiers, consistency rule) as the authoritative answer.

---

## Open Questions for Further Exploration

### 1. EOD Flatten Rule

Trading stops before EOD RTH (~3:50 PM) to ensure positions are flat before Lucid's EOD balance snapshot. This is an operational rule — the V2803 study does not currently implement a time gate.

**Question:** Should the study include an automatic session-close flatten? If a cycle is mid-martingale at ~3:50 PM, a forced exit at whatever depth and P&L breaks the clean cycle math. The forced-exit P&L would need to be included in $E[R]$ and $\sigma$ measurements — it's a third outcome type alongside "completed cycle" and "hard stop."

### 2. Commission Drag on Micro Configurations

Each martingale add generates per-contract commission. At micro scale with small per-cycle profit, commissions can consume a significant portion of gross profit.

**Commission rates (working estimates):**
- Micro (MNQ): $0.50 per round-turn contract
- Mini (NQ): $4.00 per round-turn contract

A full cycle at depth $k$ involves: 1 seed order + $k$ add orders + 1 flatten order = $k + 2$ order events. Total contracts traded (round-trip) across all events:

$$\text{Contracts}_{\text{RT}} = 2 \times q_0 \times 2^k$$

(Each contract is entered once and exited once.)

**Commission per cycle by configuration** (all configs from the comparison table, $d = 2.0$ pts):

| Config | Base | InitialQty | Max Depth | Contracts RT | Commission | Gross Profit | **Net Profit** | Net as % of Gross |
|--------|------|-----------|-----------|-------------|------------|-------------|---------------|-------------------|
| A | Mini | 1 | 1 | 4 | $16.00 | $40.00 | **$24.00** | 60% |
| B | Micro | 1 | 4 | 32 | $16.00 | $4.00 | **-$12.00** | — |
| C | Micro | 2 | 3 | 32 | $16.00 | $8.00 | **-$8.00** | — |
| D | Micro | 5 | 2 | 40 | $20.00 | $20.00 | **$0.00** | 0% |
| E | Micro | 10 | 1 | 40 | $20.00 | $40.00 | **$20.00** | 50% |

**Key findings:**
- Configs B and C are **negative EV after commissions** — the commission exceeds gross profit per cycle
- Config D is **breakeven** after commissions — no net profit per completed cycle
- Config A (1 mini) retains 60% of gross profit
- Config E (10 micros = 1 mini equivalent) retains 50% — worse than Config A because 10 micros generates more round-trip contracts than 1 mini for the same notional size

**Why micros cost more per equivalent size:** A 1-mini market order is 1 contract at $4.00 RT. A 10-micro market order is 10 contracts at $0.50 each = $5.00 RT. The per-contract micro rate is lower, but the total commission is higher at equivalent notional.

**Commission-adjusted comparison table (updated from Minis vs Micros section):**

| Config | Gross Profit/Cycle | Commission | Net Profit/Cycle | Net MaxDD/Cycle | Net Risk/Reward | Cycles to $1K (net) |
|--------|-------------------|------------|-----------------|-----------------|----------------|-------------------|
| A (1 mini, depth 1) | $40 | $16 | $24 | $56 | 2.3:1 | 42 |
| D (5 micros, depth 2) | $20 | $20 | $0 | $80 | — | ∞ |
| E (10 micros, depth 1) | $40 | $20 | $20 | $60 | 3.0:1 | 50 |

Note: MaxDD includes commission on losing cycles (stop loss + commission on all orders in that cycle).

[OPINION] After commissions, the micro advantage for achieving deeper martingale depth largely disappears at these rate levels. The configurations that use micros for depth (B, C, D) lose their economic viability. Micros remain useful only for granularity at sizes below 1 mini (e.g., Config E gives equivalent exposure to Config A but with slightly worse commission economics).

### 3. Payout Timing Optimization

Strategic question: when to request payouts during funded phase to maximize total extracted value.

**Known constraints:**
- 5 payouts max, each capped at $2,000 (50% of profit)
- Each payout resets the 5-profitable-days requirement
- Move-to-live cap: $8,000 simulated profit
- Profits above $8,000 at transition are forfeited

**Maximum theoretical extraction (single 50K account):**
- 5 payouts × $2,000 = $10,000 gross ($9,000 net at 90% split)
- Move-to-live: $8,000 (Day-1: $2,400, Escrow: $5,600)
- To take 5 × $2,000 payouts AND have $8,000 remaining at transition, total profit earned must be ≥ $18,000

**Question:** What is the optimal balance threshold at which to request each payout? Too early = risk of MLL breach during the 5-day reset period. Too late = excess capital sitting in the account earning nothing above the payout cap.

### 4. Simulation-to-Live Execution Gap

The funded phase uses simulated fills. Live phase uses real market execution. Differences that could affect $E[R]$ and $\sigma$:

- **Slippage on market orders:** The study uses `SCT_ORDERTYPE_MARKET`. In simulation, fills are at the current price. In live, slippage shifts the effective anchor price, distorting the grid geometry.
- **Fill latency:** A few ticks of delay on adds changes the actual entry price relative to the theoretical grid.
- **Partial fills:** At larger sizes (especially during scaling), market orders may fill across multiple price levels.

These effects are small per-cycle but compound over hundreds of cycles. [SUGGESTION] When computing $E[R]$ for the Monte Carlo, include a slippage adjustment (e.g., 1 tick per order) as a conservative estimate.

### 5. Hard Stop Placement Optimization

The hard stop $H$ creates a tradeoff that directly affects PropScore:

- Tighter $H$ → smaller loss per failure → lower $\sigma$ → better $E[R]/\sigma$ ratio
- Tighter $H$ → more cycles fail (stop fires before reversal) → lower $E[R]$

The optimal $H$ maximizes $E[R]/\sigma$ (the PropScore numerator), not $E[R]$ or $1/\sigma$ independently.

**Question:** Can the optimal $H$ be derived analytically from the martingale math + fractal completion rates, or does it require empirical sweep? The fractal data (Layer 2) provides completion probabilities at each retracement count, which could inform where the stop should sit relative to the grid — but this connects Layer 1 and Layer 2, which are currently kept separate by design.

### 6. Measuring $E[R]$ and $\sigma$ from Rotation Data

To run the probability framework, cycle-level P&L data is needed. Sources:

- **V2803 CSV log:** The study's `WriteCSV` function logs every event. A complete cycle can be reconstructed from SEED → ADD(s) → REVERSAL events.
- **Python simulator:** The rotational_simulator.py can generate cycle-level P&L over the P1 data period.
- **Sample size:** With $d = 2.0$ pts on NQ, [SPECULATION] cycles likely complete frequently enough to produce hundreds or thousands of observations over 6 months of data — sufficient for reliable $E[R]$ and $\sigma$ estimates. Exact count depends on StepDist and market conditions.

**Minimum viable dataset:** $E[R]$, $\sigma$, and cycle count. With those three numbers, every formula in this section can be computed.
