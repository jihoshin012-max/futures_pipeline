# Martingale Rotation — Mathematical Reference

**Study:** `ATEAM_ROTATION_V3_V2803.cpp`
**Created:** 2026-03-25
**Source:** Formulas derived directly from the study's code mechanics (doubling sequence, anchor-reset, reversal-flip). Results are consistent with classical martingale probability theory.

---

## Notation

| Symbol | Meaning | Default |
|--------|---------|---------|
| $q_0$  | Initial quantity (`InitialQty`) | 1 |
| $d$    | Step distance in points (`StepDist`) | 2.0 |
| $M$    | Max martingale levels (`MaxLevels`) | 4 |
| $C$    | Max contract size cap (`MaxContractSize`) | 8 |
| $H$    | Hard stop in ticks (`HardStop`, 0 = off) | 0 |
| $k$    | Number of adds completed (seed = 0 adds) | — |
| $P_0$  | Seed entry price | — |

---

## Core Cycle (Pure Martingale, No Circuit Breakers)

These formulas assume:
- No hard stop fires
- No fade limit blocks entry
- No speed filter flattens mid-cycle
- Price eventually moves $d$ in favor to trigger reversal

### 1. Position Size After *k* Adds

$$Q(k) = q_0 \cdot 2^k$$

The doubling sequence from the code: seed = $q_0$, add quantities are $q_0 \cdot 2^0, q_0 \cdot 2^1, \ldots, q_0 \cdot 2^{k-1}$.

Total: $q_0(1 + 1 + 2 + 4 + \ldots + 2^{k-1}) = q_0 \cdot 2^k$.

| Adds (k) | Add Qty | Total Position |
|-----------|---------|----------------|
| 0 (seed)  | $q_0$   | $q_0$          |
| 1         | $q_0$   | $2q_0$         |
| 2         | $2q_0$  | $4q_0$         |
| 3         | $4q_0$  | $8q_0$         |
| 4         | $8q_0$  | $16q_0$        |

### 2. Entry Prices (Long Direction)

Each add fires when price moves $d$ against from the last anchor. The anchor resets on every add (code line 556).

| Event | Price | Quantity |
|-------|-------|----------|
| Seed  | $P_0$ | $q_0$ |
| Add 1 | $P_0 - d$ | $q_0$ |
| Add 2 | $P_0 - 2d$ | $2q_0$ |
| Add 3 | $P_0 - 3d$ | $4q_0$ |
| Add k | $P_0 - kd$ | $q_0 \cdot 2^{k-1}$ |

### 3. Average Entry Price After *k* Adds

$$\bar{P}(k) = P_0 - d\left(k - 1 + 2^{-k}\right)$$

**Derivation:** Weighted average of entry prices by quantity, using the identity $\sum_{i=1}^{k} i \cdot 2^{i-1} = (k-1) \cdot 2^k + 1$.

**Worked example** ($q_0=1, d=2, P_0=100, k=4$):

$$\bar{P} = 100 - 2(4 - 1 + 2^{-4}) = 100 - 2(3.0625) = 93.875$$

Verification: $(1 \times 100 + 1 \times 98 + 2 \times 96 + 4 \times 94 + 8 \times 92) / 16 = 1502 / 16 = 93.875$ ✓

### 4. Profit Per Completed Cycle

The reversal triggers when price moves $d$ in favor from the last anchor ($P_0 - kd$), reaching $P_0 - (k-1)d$.

$$\text{PnL} = \left(P_0 - (k-1)d - \bar{P}(k)\right) \times Q(k) = \frac{d}{2^k} \times q_0 \cdot 2^k = q_0 \cdot d$$

**The profit per completed cycle is always $q_0 \times d$, regardless of depth.**

This is the fundamental invariant of the strategy. With defaults: $1 \times 2.0 = 2.0$ points per cycle.

### 5. Max Drawdown at Depth *k*

Unrealized loss right after the $k$-th add (price at $P_0 - kd$, position is $Q(k)$):

$$\text{MaxDD}(k) = q_0 \cdot d \cdot (2^k - 1)$$

| Adds (k) | Position | Max Drawdown (points) | Max Drawdown ($d$ multiples) |
|-----------|----------|-----------------------|------------------------------|
| 0 (seed)  | $q_0$    | 0                     | 0                            |
| 1         | $2q_0$   | $q_0 d$              | 1                            |
| 2         | $4q_0$   | $3 q_0 d$            | 3                            |
| 3         | $8q_0$   | $7 q_0 d$            | 7                            |
| 4         | $16q_0$  | $15 q_0 d$           | 15                           |

### 6. Risk/Reward Ratio at Depth *k*

$$\frac{\text{MaxDD}(k)}{\text{Profit}} = 2^k - 1$$

At max depth $M$: risk/reward = $(2^M - 1) : 1$.

With `MaxLevels=4` uncapped: **15:1**.

### 7. Breakeven Win Rate

Minimum fraction of cycles that must complete (reversal fires) vs. fail (hard stop or forced flatten at max drawdown):

$$W_{\min} = \frac{2^k - 1}{2^k} = 1 - 2^{-k}$$

| Depth (k) | Required Win Rate |
|-----------|-------------------|
| 1         | 50.0%             |
| 2         | 75.0%             |
| 3         | 87.5%             |
| 4         | 93.75%            |

---

## Effect of MaxContractSize Cap

`MaxContractSize` ($C$) is the binding constraint in practice. The effective max depth $k^*$ is:

$$k^* = \lfloor \log_2(C / q_0) \rfloor$$

With defaults ($C=8, q_0=1$): $k^* = 3$ (positions: 1 → 2 → 4 → 8, then blocked).

**Effective risk profile with cap:**
- Max drawdown: $q_0 \cdot d \cdot (C - 1) = 1 \times 2 \times 7 = 14$ points
- Profit per cycle: $q_0 \cdot d = 2$ points
- Risk/reward: $C - 1 = 7:1$
- Breakeven win rate: $(C - 1)/C = 87.5\%$

---

## Hard Stop — Risk Truncation

The hard stop fires when unrealized ticks from `AvgEntry` exceeds $H$. This fundamentally reshapes the risk profile by replacing the open-ended martingale tail with a bounded loss.

### Loss at Hard Stop

When the stop fires at depth $k$:

$$\text{Loss}_{\text{stop}}(k) = q_0 \cdot 2^k \cdot H \cdot t$$

where $t$ = `TickSize` (points per tick). The loss scales with position size — deeper stops are more expensive.

| Depth (k) | Position | Stop Loss (× $H \cdot t$) |
|-----------|----------|---------------------------|
| 0 (seed)  | $q_0$    | $q_0$                     |
| 1         | $2q_0$   | $2q_0$                    |
| 2         | $4q_0$   | $4q_0$                    |
| 3         | $8q_0$   | $8q_0$                    |

### Unrealized at Each Depth (Determines When Stop Can Fire)

The hard stop is measured from average entry, while adds trigger from the last anchor. These are different reference points, which creates a critical interaction.

Right after add $k$, the unrealized against (in ticks) from avg entry is:

$$U_{\text{at\_add}}(k) = \frac{d \cdot (1 - 2^{-k})}{t}$$

Just before add $k{+}1$ would trigger, the unrealized has grown to:

$$U_{\text{before\_next}}(k) = \frac{d \cdot (2 - 2^{-k})}{t}$$

The stop fires between add $k$ and add $k{+}1$ when:

$$U_{\text{at\_add}}(k) < H < U_{\text{before\_next}}(k)$$

### Maximum Reachable Depth Given Hard Stop

Add $k{+}1$ is reachable only if the stop does not fire first:

$$H \geq \frac{d \cdot (2 - 2^{-k})}{t}$$

**Example** ($d=2.0$, $t=0.25$ for NQ, so $d/t = 8$ ticks per step):

| To reach... | Requires $H \geq$ |
|-------------|-------------------|
| Add 1       | 8 ticks           |
| Add 2       | 12 ticks          |
| Add 3       | 14 ticks          |
| Add 4       | 15 ticks          |

This table reveals the design tension: a tight stop (e.g., $H=10$) allows only 1 add before the stop fires, effectively converting the strategy into a 2-contract fixed-size system. A loose stop (e.g., $H=60$) lets the full martingale run — but the loss when it does fire is catastrophic.

### Hard-Stop-Adjusted Breakeven

With a hard stop, the loss on a failed cycle is no longer the theoretical max drawdown — it's capped at $\text{Loss}_{\text{stop}}$. But the loss depends on *which depth* the stop fires at. For the worst case (stop fires at max reachable depth $k$):

$$E[\text{cycle}] = W \cdot q_0 d - (1 - W) \cdot q_0 \cdot 2^k \cdot H \cdot t$$

Setting $E = 0$ and solving for the breakeven win rate:

$$W_{\min} = \frac{2^k \cdot H \cdot t}{q_0 \cdot d + 2^k \cdot H \cdot t}$$

**Example** ($q_0=1, d=2, t=0.25, H=10$, max depth $k=1$):
- Profit per win: $1 \times 2 = 2.0$ pts
- Loss per stop: $2 \times 10 \times 0.25 = 5.0$ pts
- $W_{\min} = 5.0 / (2.0 + 5.0) = 71.4\%$

Compare to the uncapped $k=3$ breakeven of 87.5% — the hard stop reduces the required win rate by truncating the tail, but introduces a fixed loss that occurs more frequently.

### Stop Placement Decision Framework

The hard stop $H$ controls a three-way tradeoff:

| $H$ too tight | $H$ balanced | $H$ too loose |
|---------------|-------------|---------------|
| Stops fire frequently | Allows some depth | Full martingale runs |
| Low loss per stop | Moderate loss per stop | Catastrophic loss when it fires |
| Low win rate needed | Moderate win rate needed | High win rate needed |
| Strategy degenerates to fixed-size | Martingale with bounded tail | Pure martingale risk |

---

## Max Direction Fades — Serial Loss Control

The fade limit $N$ (`MaxFades`) caps consecutive entries in the same direction. This does not change individual cycle math but controls **loss chaining** — the scenario where the strategy repeatedly re-seeds the same losing direction.

### Chained Loss Without Fade Limit

Without the fade limit, after a stop-out the strategy can immediately re-seed the same direction (if the pullback signal qualifies). In a sustained trend:

$$\text{Max chained loss (unlimited)} = \text{unbounded}$$

Each failed cycle at depth $k$ costs $q_0 \cdot 2^k \cdot H \cdot t$, and there is no limit on repetition.

### Chained Loss With Fade Limit $N$

With the fade limit, max consecutive same-direction entries = $N$. The worst-case chained loss in one direction:

$$\text{Max chained loss} = N \times \text{Loss}_{\text{stop}}(k)$$

where $k$ is the depth at which the stop fires.

**Example** ($N=3, k=1, H=10, t=0.25$):
Max chained loss = $3 \times 5.0 = 15.0$ pts before the direction is blocked.

### Fade Limit and Cycle Frequency

The fade limit reduces expected cycles per session by blocking entries. If we model direction outcomes as independent (simplification), the expected number of blocked entries per $N$ attempts in a trending regime approaches:

- **Mean-reverting regime**: fade rarely binds (alternating directions)
- **Trending regime**: fade binds after $N$ entries, forcing a pause until direction changes

The fade limit is most valuable precisely when the strategy is most vulnerable — sustained one-directional moves that would chain martingale losses.

### Combined Risk Budget: Hard Stop + Fade Limit

The maximum capital at risk in a single directional run:

$$R_{\max} = N \times q_0 \cdot 2^{k^*} \cdot H \cdot t$$

where $k^*$ is the max reachable depth (constrained by both $C$ and $H$).

**Example** (full defaults + $H=10, N=3, k^*=1$):

$$R_{\max} = 3 \times 1 \times 2 \times 10 \times 0.25 = 15.0 \text{ pts}$$

This is the **worst-case loss before the strategy is forced to stop fading one direction** — the true risk envelope of the system.

---

## Speed Filter (Hysteresis)

Two thresholds with hysteresis:
- **Fast threshold** (e.g., 70): speed above this → flatten and stop trading
- **Slow threshold** (e.g., 30): speed below this → resume trading

If the filter fires mid-cycle, the exit price is wherever the market is at that moment — P&L is path-dependent and cannot be expressed in closed form. The speed filter is a regime gate, not a risk parameter: it decides *whether* the strategy trades, not *how* it trades. Its mathematical contribution is to the probability that a cycle completes vs. is interrupted by an external exit.

---

## Strategy-Specific Design Choices

These distinguish this study from a generic martingale:

1. **Anchor-reset on every add** — each step is measured relative to the last add price, not the original seed. This is what makes the entry prices evenly spaced at $P_0, P_0{-}d, P_0{-}2d, \ldots$

2. **Reversal-flip** — profit is harvested by flattening and entering the opposite direction, not by hitting a fixed take-profit. The exit of one cycle is the seed of the next.

3. **Pullback-based seeding** — initial entry requires a $d$-point pullback from a tracked extreme (running high/low), not an arbitrary entry. This imposes a directional filter on the first trade.

4. **Level wrap-around** — when `Level >= MaxLevels`, it resets to 0 and restarts the doubling sequence. Combined with `MaxContractSize`, the cap typically binds before wrap-around matters.

---

## Quick Reference

### Pure Cycle (no circuit breakers)

| Metric | Formula | Default Value |
|--------|---------|---------------|
| Profit per cycle | $q_0 \times d$ | 2.0 pts |
| Max position (capped) | $C$ | 8 contracts |
| Effective depth | $\lfloor \log_2(C/q_0) \rfloor$ | 3 adds |
| Max drawdown (capped) | $q_0 \times d \times (C - 1)$ | 14 pts |
| Risk/reward (capped) | $(C - 1) : 1$ | 7:1 |
| Breakeven win rate (capped) | $(C - 1) / C$ | 87.5% |

### With Hard Stop + Fade Limit

| Metric | Formula | Example ($H{=}10, N{=}3, k{=}1$) |
|--------|---------|-----------------------------------|
| Stop loss at depth $k$ | $q_0 \cdot 2^k \cdot H \cdot t$ | 5.0 pts |
| Breakeven win rate (stop) | $\frac{2^k H t}{q_0 d + 2^k H t}$ | 71.4% |
| Max chained directional loss | $N \times q_0 \cdot 2^k \cdot H \cdot t$ | 15.0 pts |
| Max reachable depth given $H$ | Largest $k$ where $H \geq d(2{-}2^{-k})/t$ | 1 add |
