# archetype: zone_touch
"""
Throughput re-examination on correct 77-trade population.

Checks whether throughput analysis conclusions hold when using
replication harness answer keys (77 ZR, 85 FIXED) instead of
throughput pre-scored keys (120 ZR, 130 FIXED).
"""
import csv, math, sys
from collections import Counter, defaultdict

BASE = 'C:/Projects/pipeline/stages'

# =========================================================================
#  Load data
# =========================================================================

def load_answer_key(path):
    with open(path) as f:
        return list(csv.DictReader(f))

def load_skipped(path):
    with open(path) as f:
        return list(csv.DictReader(f))

zr_trades = load_answer_key(f'{BASE}/04-backtest/zone_touch/output/p1_replication_answer_key_zr.csv')
zr_skipped = load_skipped(f'{BASE}/04-backtest/zone_touch/output/p1_replication_skipped_zr.csv')
fixed_trades = load_answer_key(f'{BASE}/04-backtest/zone_touch/output/p1_replication_answer_key_fixed.csv')

print(f"Loaded: {len(zr_trades)} ZR trades, {len(zr_skipped)} ZR skipped, {len(fixed_trades)} FIXED trades")

# =========================================================================
#  CHECK 1: Signal Density
# =========================================================================

print("\n" + "="*60)
print("  CHECK 1: SIGNAL DENSITY")
print("="*60)

# Qualifying signals = traded + blocked (IN_POSITION, LIMIT_PENDING, LIMIT_EXPIRED, KILL_SWITCH)
# Exclude BELOW_THRESHOLD, TF_FILTER, SEQ_FILTER — those never qualified
QUALIFIED_SKIP_REASONS = {'IN_POSITION', 'LIMIT_PENDING', 'LIMIT_EXPIRED', 'KILL_SWITCH'}

qualified_skips = [s for s in zr_skipped if s['skip_reason'] in QUALIFIED_SKIP_REASONS]
total_qualifying = len(zr_trades) + len(qualified_skips)

print(f"\nTotal qualifying signals: {total_qualifying}")
print(f"  Traded: {len(zr_trades)}")
print(f"  Blocked: {len(qualified_skips)}")
for reason, count in Counter(s['skip_reason'] for s in qualified_skips).most_common():
    print(f"    {reason}: {count}")

# Build qualifying signal RBIs (traded rbis + blocked rbis)
# For traded signals, rbi is in the CSV. For skipped, we need to estimate.
# Skipped signals don't have rbi directly — they have datetime.
# Use traded signals' rbi for gap analysis.
traded_rbis = sorted(int(t['rbi']) for t in zr_trades)

# Inter-signal gaps (between consecutive traded signals)
gaps = [traded_rbis[i+1] - traded_rbis[i] for i in range(len(traded_rbis)-1)]
if gaps:
    gaps_sorted = sorted(gaps)
    median_gap = gaps_sorted[len(gaps_sorted)//2]
    p10_idx = max(0, int(len(gaps_sorted) * 0.10))
    p90_idx = min(len(gaps_sorted)-1, int(len(gaps_sorted) * 0.90))
    p10_gap = gaps_sorted[p10_idx]
    p90_gap = gaps_sorted[p90_idx]
    mean_gap = sum(gaps) / len(gaps)

    # Clustering: signals within 20 bars of each other
    cluster_count = sum(1 for g in gaps if g <= 20)
    # A signal is "in a cluster" if gap before OR after is <= 20
    in_cluster = set()
    for i, g in enumerate(gaps):
        if g <= 20:
            in_cluster.add(i)
            in_cluster.add(i+1)
    cluster_pct = 100.0 * len(in_cluster) / len(traded_rbis) if traded_rbis else 0

    print(f"\nInter-signal gaps (traded signals only, {len(gaps)} gaps):")
    print(f"  Median gap: {median_gap} bars")
    print(f"  Mean gap: {mean_gap:.1f} bars")
    print(f"  P10: {p10_gap} bars")
    print(f"  P90: {p90_gap} bars")
    print(f"  Signals in clusters (<=20 bars): {len(in_cluster)}/{len(traded_rbis)} ({cluster_pct:.1f}%)")

# Same-zone blocking analysis
# Check if blocked IN_POSITION signals share zone with the blocking trade
ip_skips = [s for s in qualified_skips if s['skip_reason'] == 'IN_POSITION']
# We can't do precise same-zone matching without rbi in skipped file,
# but we can count the total
print(f"\n  Blocked IN_POSITION: {len(ip_skips)}")
print(f"  Blocked LIMIT_PENDING: {sum(1 for s in qualified_skips if s['skip_reason'] == 'LIMIT_PENDING')}")
print(f"  Blocked LIMIT_EXPIRED: {sum(1 for s in qualified_skips if s['skip_reason'] == 'LIMIT_EXPIRED')}")
print(f"  Blocked KILL_SWITCH: {sum(1 for s in qualified_skips if s['skip_reason'] == 'KILL_SWITCH')}")

# Decision gate
GATE_MEDIAN = 100
GATE_CLUSTER = 25.0
density_gate_pass = median_gap >= GATE_MEDIAN and cluster_pct <= GATE_CLUSTER
print(f"\n  DECISION GATE: median_gap={median_gap} (threshold={GATE_MEDIAN}), "
      f"cluster_pct={cluster_pct:.1f}% (threshold={GATE_CLUSTER}%)")
if density_gate_pass:
    print("  GATE: PASS — signals remain sparse. Proceeding to Check 2.")
else:
    print("  GATE: FAIL — signal density changed materially!")
    print("  STOP: Full throughput re-run likely needed.")

# =========================================================================
#  CHECK 2: T2 Runner Marginal Value
# =========================================================================

print("\n" + "="*60)
print("  CHECK 2: T2 RUNNER MARGINAL VALUE")
print("="*60)

# For trades where T1 filled, compute T2 marginal PnL
# T1 filled = leg1_exit == 'TARGET_1'
t1_filled = [t for t in zr_trades if t['leg1_exit'] == 'TARGET_1']
print(f"\nTrades where T1 filled: {len(t1_filled)}/{len(zr_trades)}")

# Zone width buckets
def zw_bucket(zw):
    if zw < 150: return '<150t'
    if zw < 250: return '150-250t'
    return '250t+'

buckets = defaultdict(list)
for t in t1_filled:
    zw = float(t['zone_width'])
    l2_pnl = float(t['leg2_pnl'])
    bars = int(t['bars_held'])
    entry_bar = int(t['entry_bar'])
    # T1 exit bar not directly available, approximate from leg1 timing
    # T2 marginal = leg2 PnL (since leg1 already captured T1)
    bucket = zw_bucket(zw)
    buckets[bucket].append(dict(zw=zw, l2_pnl=l2_pnl, bars=bars))

print(f"\n{'Bucket':<12} {'Count':>6} {'Mean L2 PnL':>12} {'Mean bars':>10}")
print("-" * 42)
for bucket in ['<150t', '150-250t', '250t+']:
    items = buckets[bucket]
    if items:
        mean_pnl = sum(d['l2_pnl'] for d in items) / len(items)
        mean_bars = sum(d['bars'] for d in items) / len(items)
        print(f"{bucket:<12} {len(items):>6} {mean_pnl:>12.1f} {mean_bars:>10.1f}")
    else:
        print(f"{bucket:<12} {'0':>6} {'n/a':>12} {'n/a':>10}")

# Overall T2 marginal
if t1_filled:
    all_l2 = [float(t['leg2_pnl']) for t in t1_filled]
    print(f"\nOverall T2 marginal (when T1 fills): mean={sum(all_l2)/len(all_l2):.1f}t")

# =========================================================================
#  CHECK 3: Baseline Performance
# =========================================================================

print("\n" + "="*60)
print("  CHECK 3: BASELINE PERFORMANCE (ZR)")
print("="*60)

def compute_stats(trades, label):
    pnls = [float(t['weighted_pnl']) for t in trades]
    wins = sum(1 for p in pnls if p > 0)
    gw = sum(p for p in pnls if p > 0)
    gl = sum(abs(p) for p in pnls if p < 0)
    pf = gw / gl if gl > 0 else float('inf')
    bars = [int(t['bars_held']) for t in trades]

    # Max drawdown (cumulative)
    cum = 0
    peak = 0
    max_dd = 0
    for p in pnls:
        cum += p
        if cum > peak:
            peak = cum
        dd = peak - cum
        if dd > max_dd:
            max_dd = dd

    max_loss = min(pnls) if pnls else 0

    print(f"\n  [{label}] {len(trades)} trades")
    print(f"  Total PnL: {sum(pnls):.1f}t")
    print(f"  WR: {100*wins/len(trades):.1f}%")
    print(f"  PF: {pf:.2f}")
    print(f"  Mean bars held: {sum(bars)/len(bars):.0f}")
    print(f"  Max DD: {max_dd:.1f}t")
    print(f"  Max single loss: {max_loss:.1f}t")
    return dict(total_pnl=sum(pnls), wr=100*wins/len(trades), pf=pf,
                mean_bars=sum(bars)/len(bars), max_dd=max_dd, max_loss=max_loss,
                mean_pnl=sum(pnls)/len(trades))

zr_stats = compute_stats(zr_trades, "ZR")
fixed_stats = compute_stats(fixed_trades, "FIXED")

# =========================================================================
#  CHECK 4: Fixed Exit Comparison
# =========================================================================

print("\n" + "="*60)
print("  CHECK 4: FIXED EXIT COMPARISON")
print("="*60)

print(f"\n  {'Metric':<20} {'ZR (77)':>12} {'Fixed (85)':>12}")
print("  " + "-"*46)
print(f"  {'Total PnL':<20} {zr_stats['total_pnl']:>12.1f} {fixed_stats['total_pnl']:>12.1f}")
print(f"  {'Mean PnL/trade':<20} {zr_stats['mean_pnl']:>12.1f} {fixed_stats['mean_pnl']:>12.1f}")
print(f"  {'WR':<20} {zr_stats['wr']:>11.1f}% {fixed_stats['wr']:>11.1f}%")
print(f"  {'PF':<20} {zr_stats['pf']:>12.2f} {fixed_stats['pf']:>12.2f}")
print(f"  {'Max DD':<20} {zr_stats['max_dd']:>12.1f} {fixed_stats['max_dd']:>12.1f}")

pnl_diff_pct = 100 * (fixed_stats['total_pnl'] - zr_stats['total_pnl']) / abs(zr_stats['total_pnl'])
print(f"\n  Fixed vs ZR total PnL difference: {pnl_diff_pct:+.1f}%")
if abs(pnl_diff_pct) <= 15:
    print("  NOTE: Within 15% — throughput advantage (8 extra trades) partially compensates.")

# =========================================================================
#  CHECK 5: Dynamic T2 Exit
# =========================================================================

print("\n" + "="*60)
print("  CHECK 5: DYNAMIC T2 EXIT")
print("="*60)

# Dynamic T2: when T1 fills and a NEW qualifying signal arrives on a DIFFERENT
# zone before T2 exits, close T2 runner and enter the new signal.
# Sequential simulation with no-overlap and kill-switch.

# Load bar data for exit simulation
print("\nLoading P1 bar data for dynamic T2 simulation...")
bar_data = []
with open(f'{BASE}/01-data/output/zone_prep/NQ_bardata_P1.csv') as f:
    for row in csv.DictReader(f):
        r = {k.strip(): v.strip() for k, v in row.items()}
        bar_data.append((float(r['Open']), float(r['High']), float(r['Low']), float(r['Last'])))
n_bars = len(bar_data)

# Rebuild the full signal list: traded + IN_POSITION blocked
# We need rbi for all qualifying signals. Traded have rbi.
# IN_POSITION skips don't have rbi — we need to reconstruct.
# For dynamic T2, we just check if a NEW qualifying signal arrives
# during an active T2 runner from the TRADED list.

# Approach: iterate through trades. When T1 fills and T2 is still running,
# check if the NEXT traded signal's rbi falls before the T2 exit bar.
# If so, close T2 at the new signal's entry bar and "free" a new trade.

TICK_SIZE = 0.25
COST_TICKS = 3.0
LEG1_W, LEG2_W = 0.67, 0.33

ZR_T1_MULT = 0.5
ZR_T2_MULT = 1.0
ZR_STOP_MULT = 1.5
ZR_STOP_FLOOR = 120

dynamic_t2_closes = 0
dynamic_new_trades = 0
dynamic_extra_pnl = 0.0
ks_consec = 0
ks_daily_pnl = 0.0
ks_halted = False
last_day = ''

# Build trade list with computed T1 fill bars
trade_details = []
for t in zr_trades:
    rbi = int(t['rbi'])
    entry_bar = int(t['entry_bar'])
    exit_bar = int(t['exit_bar'])
    direction = 1 if t['direction'] == '1' else -1
    zw = float(t['zone_width'])
    ep = float(t['entry_price'])
    l1_exit = t['leg1_exit']
    l2_exit = t['leg2_exit']
    l2_pnl = float(t['leg2_pnl'])
    t2_ticks = int(t['t2_ticks'])
    stop_ticks = int(t['stop_ticks'])

    # Find T1 fill bar (scan for TARGET_1 hit)
    t1_fill_bar = None
    if l1_exit == 'TARGET_1':
        t1_ticks = int(t['t1_ticks'])
        t1_px = ep + t1_ticks * TICK_SIZE if direction == 1 else ep - t1_ticks * TICK_SIZE
        for bi in range(entry_bar, min(exit_bar + 1, n_bars)):
            o, h, l, c = bar_data[bi]
            hit = (h >= t1_px) if direction == 1 else (l <= t1_px)
            if hit:
                t1_fill_bar = bi
                break

    trade_details.append(dict(
        rbi=rbi, entry_bar=entry_bar, exit_bar=exit_bar,
        direction=direction, zw=zw, ep=ep,
        l1_exit=l1_exit, l2_exit=l2_exit, l2_pnl=l2_pnl,
        t1_fill_bar=t1_fill_bar, t2_ticks=t2_ticks, stop_ticks=stop_ticks
    ))

# Simulate dynamic T2
baseline_pnl = sum(float(t['weighted_pnl']) for t in zr_trades)
dynamic_pnl = baseline_pnl
ks_triggers = 0

for i, td in enumerate(trade_details):
    if td['l1_exit'] != 'TARGET_1' or td['t1_fill_bar'] is None:
        continue
    if td['l2_exit'] in ('TARGET_2', 'STOP'):
        continue  # T2 already resolved before any new signal could matter

    # T2 is still running after T1 fill. Check if next trade's entry
    # is before this trade's exit.
    if i + 1 >= len(trade_details):
        continue

    next_td = trade_details[i + 1]
    next_entry = next_td['entry_bar']

    # Is the next signal on a DIFFERENT zone?
    same_zone = (abs(td['ep'] - next_td['ep']) < 1.0 and td['direction'] == next_td['direction'])
    if same_zone:
        continue

    # Does the next signal arrive while T2 runner is active?
    if next_entry > td['t1_fill_bar'] and next_entry < td['exit_bar']:
        # Close T2 runner at the bar when next signal arrives
        close_bar = next_entry
        o, h, l, c = bar_data[close_bar]
        close_pnl = (c - td['ep']) / TICK_SIZE if td['direction'] == 1 else (td['ep'] - c) / TICK_SIZE

        # Original L2 PnL vs early close PnL
        delta = close_pnl - td['l2_pnl']
        # Weighted delta (L2 is 33% weight)
        weighted_delta = LEG2_W * delta

        dynamic_t2_closes += 1
        dynamic_pnl += weighted_delta

        # The next trade is already counted in the baseline (it was traded).
        # In dynamic mode, it would also be traded (same signal).
        # But the timing might free signals that were IN_POSITION blocked.
        # For this simplified check, we just count the T2 early close impact.

print(f"\n  Dynamic T2 early closes: {dynamic_t2_closes}")
print(f"  Baseline PnL: {baseline_pnl:.1f}t")
print(f"  Dynamic T2 PnL: {dynamic_pnl:.1f}t")
print(f"  Delta: {dynamic_pnl - baseline_pnl:+.1f}t ({100*(dynamic_pnl-baseline_pnl)/baseline_pnl:+.1f}%)")

# =========================================================================
#  VERDICT
# =========================================================================

print("\n" + "="*60)
print("  VERDICT")
print("="*60)

print(f"""
| Original conclusion                              | Status |
|--------------------------------------------------|--------|""")

# 1. Signal density
if density_gate_pass:
    density_status = "CONFIRMED" if median_gap >= 150 else "WEAKENED"
else:
    density_status = "OVERTURNED"
print(f"| Signal density too sparse for throughput gains    | {density_status:>6} |")

# 2. ZR optimal
zr_optimal = "CONFIRMED" if zr_stats['pf'] > 3.0 and zr_stats['wr'] > 75 else "WEAKENED"
print(f"| Current ZR 2-leg is optimal                      | {zr_optimal:>6} |")

# 3. Fixed loses
fixed_loses = "CONFIRMED" if fixed_stats['total_pnl'] < zr_stats['total_pnl'] else "OVERTURNED"
if abs(pnl_diff_pct) <= 15 and fixed_stats['total_pnl'] < zr_stats['total_pnl']:
    fixed_loses = "WEAKENED"
print(f"| Fixed exits lose throughput comparison            | {fixed_loses:>6} |")

# 4. T2 runner
print(f"| T2 runner adds value on wide, marginal on narrow | {'TBD':>6} |")

# 5. Dynamic T2
dyn_delta = dynamic_pnl - baseline_pnl
dyn_status = "CONFIRMED" if abs(dyn_delta) < 100 else "WEAKENED"
print(f"| Dynamic T2 exit is only ACTIONABLE mechanism     | {dyn_status:>6} |")

# 6. No safe improvement
print(f"| No safe throughput improvement exists             | {density_status:>6} |")

print()
if density_status != "OVERTURNED" and zr_optimal != "OVERTURNED" and fixed_loses != "OVERTURNED":
    print("Throughput conclusions hold on correct population. No re-run needed.")
    print("Proceed to visual spot-check.")
else:
    print("WARNING: One or more conclusions OVERTURNED. Full re-run may be needed.")
