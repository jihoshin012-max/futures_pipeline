# LucidFlex 50K — Prop Firm Rules Reference

**Account:** LucidFlex 50K Flex Eval
**Created:** 2026-03-25
**Source:** Lucid Trading official help center articles + site screenshots (March 2026)

---

## Account Parameters

| Parameter | Value |
|-----------|-------|
| Starting Balance | $50,000 |
| Max Loss Limit (MLL) | $2,000 |
| Daily Loss Limit (DLL) | **None** (eval and funded) |
| Drawdown Type | End-of-Day (EOD) trailing |
| Max Position Size (eval) | 4 minis / 40 micros |
| Max Position Size (funded) | 2–4 minis (scaling plan) |

---

## Stage 1: Evaluation

### Pass Criteria

| Rule | Value |
|------|-------|
| Profit Target | $3,000 |
| Minimum Trading Days | 2 |
| Time Limit | None (as long as account stays above MLL) |
| Consistency Rule | 50% (with ~4% cushion) |
| Max Position | 4 minis / 40 micros |
| DLL | None |

### Consistency Rule (Eval Only)

**Formula:** `Largest Single Day Profit / Account Profit = Consistency %`

Must be ≤ 50% to upgrade to funded. A built-in cushion allows slightly exceeding 50%:

| Account | Profit Target | Hard 50% | Cushion Limit |
|---------|--------------|----------|---------------|
| $50K | $3,000 | $1,500 | $1,560 |

The cushion is percentage-based, not a fixed dollar amount — it varies with actual daily profit.

**Mathematical implication:** With profit target $T = $3,000$ and effective cap $c \approx 0.52$:
- Max single-day profit ≈ $1,560
- Minimum days to pass = 2
- If best day = $1,560, remaining days must sum to ≥ $1,440

### Drawdown Mechanics (Eval)

- **EOD only** — calculated at end of each trading session, not intraday
- **Trailing** — MLL rises with highest EOD closing balance
- Intraday drawdowns do not trigger violations if recovered by session close
- If EOD balance reaches MLL → account breached

---

## Stage 2: Funded Account

### Rules Changes from Eval

| Rule | Eval | Funded |
|------|------|--------|
| Consistency Rule | 50% | **None** |
| Max Position | 4 minis (fixed) | 2–4 minis (scaling) |
| Daily Loss Limit | None | None |
| Drawdown | EOD trailing | EOD trailing (same) |

### Scaling Plan (Funded Only)

No scaling in evaluation. Funded position size scales with simulated profit, updated at **end of each session** (not real-time intraday).

| Simulated Profit | Max Position |
|------------------|-------------|
| $0 – $999 | 2 minis / 20 micros |
| $1,000 – $1,999 | 3 minis / 30 micros |
| $2,000+ | 4 minis / 40 micros |

- Scales **downward** if profit drops below a tier threshold
- One accidental oversize = no penalty; repeated intentional circumvention = account review
- Scaling has no effect on payout eligibility or amounts

### Drawdown Lock Mechanics

| Parameter | 50K Value |
|-----------|-----------|
| MLL Amount | $2,000 |
| Initial Trail Balance | $52,100 |
| Locked MLL Balance | $50,100 |

**How it works:**
1. MLL starts at $48,000 ($50,000 − $2,000)
2. End of each session: if closing balance sets new high water mark, MLL trails up: `MLL = HWM − $2,000`
3. Once EOD close ≥ $52,100 (Initial Trail Balance): **MLL locks permanently**
4. On first payout request: MLL adjusts to Locked MLL Balance ($50,100) and never moves again

**From Lucid:** *"Once the account exceeds the trail, the MLL locks at the initial balance plus $100."*

**Example:**

| Day | EOD Close | HWM | MLL | Status |
|-----|-----------|-----|-----|--------|
| 1 | $50,400 | $50,400 | $48,400 | Trailing |
| 2 | $51,250 | $51,250 | $49,250 | Trailing |
| 3 | $50,800 | $51,250 | $49,250 | No change (not new HWM) |
| 4 | $52,200 | $52,200 | **$50,100** | **LOCKED** (≥ $52,100) |
| 5+ | Any | — | $50,100 | Permanent |

### Payout Rules (Funded)

| Rule | Value |
|------|-------|
| Profit Split | 90% trader / 10% firm |
| Min Profitable Days per Cycle | 5 days at ≥ $150 each |
| Min Net Profit per Cycle | > $0 |
| Min Payout Request | $500 |
| Max Payout | 50% of profit, up to $2,000 |
| Payout Frequency | Anytime after meeting criteria |
| Total Payouts to Live | **5** |

**From Lucid:** *"Traders may take up to [5] payouts from each LucidFlex account after which they will be moved live."*

**From Lucid:** *"Unlike our other prop firm funded accounts, the maximums here do not scale up with more payouts."* — all 5 payouts use the same $2,000 cap.

**From Lucid:** *"There is no buffer balance that must be maintained in LucidFlex funded accounts."*

**From Lucid:** *"If you take a trade before your payout is processed that drops your balance below the required amount, your request may be denied."*

**Profitable day requirement resets:** *"The minimum profit on trading days reset and must be earned again after every approved payout."*

### LucidLive Transition (After 5 Payouts)

Automatically moved to LucidLive after 5 funded payouts. Details from third-party sources (verify with Lucid):

| Parameter | Value |
|-----------|-------|
| Starting Balance | $0 |
| One-time Bonus | $2,000 (reported) |
| Profit Split | 80/20 (reported) |
| Daily Payout | Available (reported) |

---

## Stage 3: LucidLive (After 5 Funded Payouts)

**Note:** This section documents the structure for accounts purchased/reset after 2/27/26. A legacy structure exists for earlier accounts (see Lucid help center).

Traders transition to live when:
- They complete their 5th (final) LucidFlex payout, **or**
- At the discretion of the Lucid risk team (before 5th payout)

### Move-to-Live Capital

Simulated profits from the funded account determine live starting capital, subject to a cap:

| Account Size | Max Moved Live (per account) |
|-------------|------------------------------|
| $25,000 | $4,000 |
| $50,000 | **$8,000** |
| $100,000 | $12,000 |
| $150,000 | $16,000 |

**Any simulated profits above the cap are forfeited on transition.**

### Day-One Capital vs Escrow

Only a portion is deposited on Day 1. The rest is held in escrow:

| Account Size | Day-1 Deposit (per account) | Escrow (remainder) |
|-------------|----------------------------|-------------------|
| $25,000 | $1,200 | up to $2,800 |
| $50,000 | **$2,400** | **up to $5,600** |
| $100,000 | $3,600 | up to $8,400 |
| $150,000 | $4,800 | up to $11,200 |

**50K example:** If you move live with $10,000 simulated profit → capped to $8,000 ($2,000 forfeited). Day 1 = $2,400. Escrow = $5,600.

### Escrow Release

Escrow is released based on live trading performance:

**Prerequisites (must meet both):**
1. Complete 10 profitable trading days in live account
2. Earn $10,000 in live trading profits

**Release rate:** For every $10,000 in additional live profits, $5,000 in escrow is released.

**Rules:**
- Reviewed weekly (not daily)
- Minimum 60 days from account opening before any escrow withdrawal
- Only released escrow amounts may be withdrawn
- Released funds may be used for margin
- Significant drawdowns after release may trigger risk review
- "Yolo" / reckless trading disqualifies escrow release

### Multiple Accounts at Live

Up to **5 LucidLive accounts** per household.

**50K multi-account example (5 accounts):**
- Max moved live: $8,000 × 5 = $40,000
- Day-1 capital: $2,400 × 5 = $12,000
- Escrow: up to $28,000
- Each account tracked independently for escrow release

---

## Account Limits

| Account Type | Max Active |
|-------------|-----------|
| Evaluation accounts | 10 |
| Funded accounts | 5 |
| Live accounts | 5 |
| **Total eval + funded combined** | **10** |

- 5 eval accounts may be held in reserve while holding 5 funded accounts
- Reserve eval accounts may still be traded
- Different funded account types (LucidFlex, LucidDirect, LucidPro) share the 5-account funded cap

---

## Trading Rules & Permissions

### Allowed

| Activity | Status | Notes |
|----------|--------|-------|
| News Trading | **Allowed** | No restrictions. Slippage/velocity logic risk on trader. |
| Genuine Scalping | **Allowed** | Short-term trades reflecting realistic execution. Must stay within microscalping policy. |
| Scaling / DCA | **Allowed** | No limits on entry methods. |
| Automated Strategies | **Allowed** | Trade copiers permitted. Trader responsible for software errors. |
| Flipping | **Allowed** | Quick in-and-out to meet minimum trading day requirements. Not restricted. |
| DLL | **None** | No daily loss limit (eval or funded). |

### Prohibited

**Microscalping:**
- Defined as capturing very small price moves with large size in extremely short timeframes (seconds), exploiting simulated fill behavior
- **Detection trigger:** >50% of profits from trades held ≤5 seconds
- **Enforcement:** Flag → manual review → written warning → profit forfeiture → permanent ban
- Genuine scalping (short-term trades in good faith) is NOT microscalping

**High Frequency Trading (HFT):**
- Automated strategies submitting high volume of trades in seconds/milliseconds
- **Enforcement:** Written warning → profit removal → account closure → permanent ban

### Cautioned (Not Prohibited)

**Martingaling:**
- From Lucid: *"While scaling is permitted, martingaling, continuously adding to losing positions in hopes of recovery, is strongly discouraged. Martingaling can quickly escalate risk and is not considered a sustainable long-term strategy."*
- **Status:** Not prohibited, but explicitly flagged as discouraged
- **Implication for strategy modeling:** The rotation study IS a martingale. Lucid does not ban it, but the language signals risk-team scrutiny is possible. The strategy's EOD recovery behavior (intraday drawdowns that resolve by close) and the rotation mechanic (not purely "adding to losers" — it flips direction) may differentiate it from what Lucid considers problematic martingaling. This is an interpretation, not a guarantee.

---

## Key Constraints for Strategy Modeling

These are the hard constraints the mathematical model must respect:

### Eval Phase Constraints

1. **$2,000 MLL (EOD trailing)** — EOD balance must never reach MLL; starting floor = $48,000
2. **Consistency ≤ 50%** — largest single-day profit ≤ ~52% of cumulative profit (with cushion)
3. **Max 4 minis** — hard position cap during eval
4. **$3,000 profit target** — must be reached to pass

### Funded Phase Constraints

1. **$2,000 MLL (EOD trailing → locked)** — same drawdown, but trails up then locks at $50,100
2. **Scaling: starts at 2 minis** — half of eval cap; must earn $2,000 simulated profit to unlock full 4 minis
3. **5 profitable days (≥$150 each) per payout cycle** — resets after every payout
4. **$2,000 max payout** — flat cap on all 5 payouts, 50% of profit
5. **$500 min payout** — need meaningful accumulated profit
6. **5 payouts to LucidLive** — then transition to live account structure

### LucidLive Phase Constraints

1. **Day-1 capital = $2,400** (per 50K account) — trading starts with limited capital
2. **Escrow unlock requires $10,000 live profit + 10 profitable days** — high bar before accessing remaining capital
3. **Escrow release rate: $5,000 per $10,000 profit** — 50% earn-back ratio
4. **60-day minimum** before any escrow withdrawal
5. **Risk review on drawdowns** — reckless trading disqualifies escrow release
6. **Multi-account scaling** — up to 5 live accounts, each tracked independently

### Critical Interactions with Martingale Strategy

- **Position cap at funded start (2 minis)** constrains `MaxContractSize` — martingale depth limited to $\lfloor \log_2(2) \rfloor = 1$ add initially
- **$2,000 MLL is the total risk budget** — martingale $\text{MaxDD}(k) = q_0 \cdot d \cdot (2^k - 1)$ must stay under this on an EOD basis
- **EOD-only measurement is favorable** — intraday martingale drawdowns are tolerated if the cycle completes or recovers by session close
- **No DLL** — a single bad session doesn't independently kill the account (only cumulative EOD balance matters)
- **Trailing drawdown before lock** — early funded trading is the most dangerous period; each new HWM raises the floor, shrinking effective buffer until lock at $52,100
- **Scaling creates a ramp** — strategy parameters may need to be staged: conservative at 2 minis, normal at 4 minis
- **Forfeiture cap at live transition** — simulated profit above $8,000 is lost; no incentive to over-accumulate in funded phase beyond what's needed to maximize payouts + move-to-live cap
- **Escrow structure rewards consistency** — the live phase explicitly penalizes aggressive/reckless trading; martingale risk parameters at live must be conservative enough to pass risk review
- **Martingale is cautioned, not banned** — Lucid explicitly discourages martingaling but does not prohibit it. The rotation mechanic (flatten + reverse, not just pile into losers) may distinguish this strategy from what Lucid considers problematic. However, risk-team scrutiny is possible, especially if drawdown patterns look like classic martingale blow-ups
- **Microscalping rule (≤5 second trades)** — with small StepDist values, fast rotation cycles could produce very short hold times. If >50% of profits come from trades held ≤5 seconds, the account gets flagged. StepDist must be large enough that cycle durations consistently exceed this threshold
- **HFT prohibition** — automated execution is allowed, but very high order volume in short timeframes is not. The rotation strategy's order frequency must stay well below what Lucid's systems consider HFT

### Full Pipeline (50K Single Account)

| Phase | Capital at Risk | Position Cap | Key Gate |
|-------|----------------|-------------|----------|
| Eval | $2,000 MLL | 4 minis | $3,000 profit target + 50% consistency |
| Funded (early) | $2,000 MLL trailing | 2 minis | Scaling + 5 profitable days per payout |
| Funded (locked) | $2,000 MLL locked at $50,100 | 2–4 minis | 5 payouts, $2,000 cap each |
| Live (Day 1) | $2,400 deposited | TBD | 10 profitable days + $10,000 profit |
| Live (escrow) | $2,400 + released escrow | TBD | $5,000 released per $10,000 earned |

**Maximum extractable value (single 50K account):**
- Funded payouts: 5 × $2,000 = $10,000 (90% split → $9,000 net to trader)
- Move-to-live cap: $8,000 (Day-1: $2,400 + Escrow: $5,600)
- Total recoverable: up to $17,000 before live trading profits

---

## Source

All rules in this document sourced from Lucid Trading official help center articles (written by AJ), accessed March 2026:
- LucidFlex Evaluation Account
- LucidFlex Funded Account
- LucidFlex Payouts
- LucidFlex Consistency Percentage
- LucidFlex Scaling Plan
- LucidFlex Drawdown
- LucidFlex Live (Legacy) — for post-2/27/26 structure
- Simulated Account Fees
- Payout Methods
- Maximum Number of Accounts
