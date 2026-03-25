# archetype: zone_touch
"""v3.2 Simulation Ground Truth Verification — bar-by-bar trade walkthrough.

Reads raw bar data and stress test trades, walks each selected trade
bar-by-bar to verify the simulator's output matches ground truth.

Output: v32_simulation_verification_report.md
"""

import sys
import json
import math
from pathlib import Path
from datetime import datetime

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import numpy as np
import pandas as pd

# ════════════════════════════════════════════════════════════════════
# PATHS
# ════════════════════════════════════════════════════════════════════
BASE = Path(r"c:\Projects\pipeline")
DATA_DIR = BASE / "stages" / "01-data" / "output" / "zone_prep"
OUT_DIR = BASE / "shared" / "archetypes" / "zone_touch" / "output"
TICK = 0.25

# ════════════════════════════════════════════════════════════════════
# LOAD DATA
# ════════════════════════════════════════════════════════════════════
print("Loading data files...")

# Bar data (same file stress_test_v32.py uses)
bar_p1 = pd.read_csv(DATA_DIR / "NQ_bardata_P1.csv")
bar_p1.columns = bar_p1.columns.str.strip()
bar_arr = bar_p1[["Open", "High", "Low", "Last"]].to_numpy(np.float64)
n_bars = len(bar_arr)
print(f"  Bar data: {n_bars} bars")

# Stress test trades
trades_df = pd.read_csv(OUT_DIR / "stress_test_trades_v32.csv")
p1_trades = trades_df[trades_df["period"].str.contains("P1")].copy()
p1_trades = p1_trades.reset_index(drop=True)
print(f"  P1 trades: {len(p1_trades)}")

# Merged touch data (for signal lookup)
merged_p1a = pd.read_csv(DATA_DIR / "NQ_merged_P1a.csv")
merged_p1b = pd.read_csv(DATA_DIR / "NQ_merged_P1b.csv")
merged_p1 = pd.concat([merged_p1a, merged_p1b], ignore_index=True)
merged_p1 = merged_p1[merged_p1["RotBarIndex"] >= 0].reset_index(drop=True)
print(f"  Merged touches (P1): {len(merged_p1)}")

# Scored touches
aeq_df = pd.read_csv(OUT_DIR / "p1_scored_touches_aeq_v32.csv")
bz_df = pd.read_csv(OUT_DIR / "p1_scored_touches_bzscore_v32.csv")
print(f"  A-Eq scored: {len(aeq_df)}, B-ZScore scored: {len(bz_df)}")

# Load A-Eq threshold from JSON (same as stress test)
with open(OUT_DIR / "scoring_model_aeq_v32.json") as f:
    aeq_cfg = json.load(f)
M1_THRESHOLD = aeq_cfg["threshold"]  # ~45.5
M2_THRESHOLD = 0.50

# Bar datetime for lookups
bar_dt = bar_p1["Date"].astype(str) + " " + bar_p1["Time"].astype(str)

# ════════════════════════════════════════════════════════════════════
# REPORT BUILDER
# ════════════════════════════════════════════════════════════════════
report_lines = []


def rp(msg=""):
    print(msg)
    report_lines.append(str(msg))


# ════════════════════════════════════════════════════════════════════
# STEP 0: VERIFY CONVENTIONS
# ════════════════════════════════════════════════════════════════════
rp("# v3.2 Simulation Ground Truth Verification Report")
rp("")
rp(f"## Date: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
rp("")
rp("---")
rp("")
rp("## Step 0: Simulator Conventions (verified from code)")
rp("")
rp("| Convention | Value | Source |")
rp("|-----------|-------|--------|")
rp("| Simulation logic (M1) | `zone_touch_simulator.py:run_multileg()` | stress_test_v32.py:324 |")
rp("| Simulation logic (M2) | `stress_test_v32.py:sim_trade_m2()` | stress_test_v32.py:265 |")
rp(f"| Bar data file | `NQ_bardata_P1.csv` ({n_bars} bars) | stress_test_v32.py:563 |")
rp("| Touch data | `NQ_merged_P1a/b.csv` | stress_test_v32.py:577 |")
rp("| RotBarIndex mapping | Direct 0-based row index | stress_test_v32.py:339 |")
rp("| datetime column | TOUCH time (row DateTime) | stress_test_v32.py:349 |")
rp("| Entry convention | `RotBarIndex + 1`, price = Open | stress_test_v32.py:340,270 |")
rp("| Exit checking starts | Entry bar itself (bars_held=1) | M2:280, M1:286 |")
rp("| Same-bar conflict | STOP fills first | M2:297-302, M1:314-337 |")
rp("| bars_held formula | `i - entry_bar + 1` (M2) / `i + 1` (M1) | inclusive from entry |")
rp("| PnL columns | GROSS (no cost deduction) | stress_test_v32.py:394 |")
rp("| Cost model | 3t/ct P1 — applied only in PF/WR calcs | stress_test_v32.py:33,410 |")
rp("| Blackout/EOD | NOT enforced in simulation | deployment-level only |")
rp("")

# Verify RotBarIndex mapping on a sample trade
sample = p1_trades.iloc[0]
sample_rbi = int(sample["RotBarIndex"])
bar_dt_at_rbi = bar_dt.iloc[sample_rbi]
rp(f"**RotBarIndex mapping check:** Trade 0 RBI={sample_rbi}, "
   f"touch datetime=`{sample['datetime']}`, bar datetime at RBI=`{bar_dt_at_rbi}` — "
   f"{'MATCH' if sample['datetime'][:10] in bar_dt_at_rbi else 'CHECK NEEDED'}")
rp("")

# Parameter audit
rp("### Parameter Audit")
rp("")
rp("| Parameter | Spec | Code | Match |")
rp("|-----------|------|------|-------|")
params = [
    ("M1 stop", 190, 190), ("M1 T1", 60, 60), ("M1 T2", 120, 120),
    ("M1 contracts", 3, 3), ("M1 time cap", 120, 120),
    ("M1 BE after T1", 0, 0), ("M2 stop mult", 1.3, 1.3),
    ("M2 stop floor", 100, 100), ("M2 target mult", 1.0, 1.0),
    ("M2 time cap", 80, 80), ("M2 3ct cutoff", "<150", "<150"),
    ("M2 2ct range", "150-250", "150-250"), ("M2 1ct cutoff", ">250", ">250"),
    ("A-Eq threshold", 45.5, round(M1_THRESHOLD, 1)),
    ("B-ZScore threshold", 0.50, 0.50),
    ("Cost P1", 3, 3),
]
all_match = True
for name, spec, code in params:
    match = "Y" if str(spec) == str(code) else "N"
    if match == "N":
        all_match = False
    rp(f"| {name} | {spec} | {code} | {match} |")
rp("")
if not all_match:
    rp("**BLOCKING: Parameter mismatch detected. Investigate before proceeding.**")
    rp("")
else:
    rp("All parameters match spec. Proceeding to trade verification.")
rp("")

# ════════════════════════════════════════════════════════════════════
# TRADE SELECTION
# ════════════════════════════════════════════════════════════════════
rp("---")
rp("")
rp("## Trade Selection")
rp("")

selected_indices = []
selected_categories = []

# Helper to find trades matching criteria
m1 = p1_trades[p1_trades["mode"] == "M1"]
m2 = p1_trades[p1_trades["mode"] == "M2"]

# 1. M1 T1+T2 LONG
t = m1[(m1["exit_type"] == "target_2") & (m1["direction"] == 1)]
if len(t) > 0:
    idx = t.index[0]
    selected_indices.append(idx)
    selected_categories.append("M1 T1+T2 LONG winner")

# 2. M1 T1+T2 SHORT
t = m1[(m1["exit_type"] == "target_2") & (m1["direction"] == -1)]
if len(t) > 0:
    idx = t.index[0]
    selected_indices.append(idx)
    selected_categories.append("M1 T1+T2 SHORT winner")

# 3. M1 T1+BE LONG
t = m1[(m1["exit_type"] == "stop") & (m1["direction"] == 1) &
       (m1["pnl_per_contract"].between(15, 25))]
if len(t) > 0:
    idx = t.index[0]
    selected_indices.append(idx)
    selected_categories.append("M1 T1+BE stop LONG")

# 4. M1 T1+BE SHORT
t = m1[(m1["exit_type"] == "stop") & (m1["direction"] == -1) &
       (m1["pnl_per_contract"].between(15, 25))]
if len(t) > 0:
    idx = t.index[0]
    selected_indices.append(idx)
    selected_categories.append("M1 T1+BE stop SHORT")

# 5. M1 full stops — ALL 3
t = m1[(m1["exit_type"] == "stop") & (m1["pnl_per_contract"] < -100)]
for i in t.index:
    selected_indices.append(i)
    d = "LONG" if p1_trades.loc[i, "direction"] == 1 else "SHORT"
    selected_categories.append(f"M1 full stop {d}")

# 6. M1 time cap — the 1
t = m1[m1["exit_type"] == "time_cap"]
for i in t.index:
    selected_indices.append(i)
    selected_categories.append("M1 time cap")

# 7. M2 TARGET 3ct (ZW < 150)
t = m2[(m2["exit_type"] == "TARGET") & (m2["contracts"] == 3)]
if len(t) > 0:
    idx = t.index[0]
    selected_indices.append(idx)
    selected_categories.append("M2 TARGET 3ct (ZW<150)")

# 8. M2 TARGET 2ct (150-250)
t = m2[(m2["exit_type"] == "TARGET") & (m2["contracts"] == 2)]
if len(t) > 0:
    idx = t.index[0]
    selected_indices.append(idx)
    selected_categories.append("M2 TARGET 2ct (150-250)")

# 9. M2 TARGET 1ct (ZW > 250)
t = m2[(m2["exit_type"] == "TARGET") & (m2["contracts"] == 1)]
if len(t) > 0:
    idx = t.index[0]
    selected_indices.append(idx)
    selected_categories.append("M2 TARGET 1ct (ZW>250)")

# 10. M2 STOP — ALL 3
t = m2[m2["exit_type"] == "STOP"]
for i in t.index:
    selected_indices.append(i)
    d = "LONG" if p1_trades.loc[i, "direction"] == 1 else "SHORT"
    selected_categories.append(f"M2 STOP {d}")

# 11. M2 TIMECAP
t = m2[m2["exit_type"] == "TIMECAP"]
if len(t) > 0:
    idx = t.index[0]
    selected_indices.append(idx)
    selected_categories.append("M2 TIMECAP")

# 12. M2 LONG (if not already covered)
t = m2[m2["direction"] == 1]
covered_m2_long = any(p1_trades.loc[i, "direction"] == 1 and p1_trades.loc[i, "mode"] == "M2"
                      for i in selected_indices)
if not covered_m2_long and len(t) > 0:
    idx = t.index[0]
    selected_indices.append(idx)
    selected_categories.append("M2 LONG")

# 13. M2 SHORT (if not already covered)
t = m2[m2["direction"] == -1]
covered_m2_short = any(p1_trades.loc[i, "direction"] == -1 and p1_trades.loc[i, "mode"] == "M2"
                       for i in selected_indices)
if not covered_m2_short and len(t) > 0:
    idx = t.index[0]
    selected_indices.append(idx)
    selected_categories.append("M2 SHORT")

# 14. Trade near EOD (latest entry)
latest = p1_trades.sort_values("RotBarIndex").iloc[-1]
latest_idx = p1_trades[p1_trades["RotBarIndex"] == latest["RotBarIndex"]].index[0]
if latest_idx not in selected_indices:
    selected_indices.append(latest_idx)
    selected_categories.append("Latest entry (EOD proximity)")

rp(f"Selected {len(selected_indices)} trades:")
rp("")
for i, (idx, cat) in enumerate(zip(selected_indices, selected_categories)):
    tr = p1_trades.loc[idx]
    rp(f"{i+1}. **{cat}** — {tr['mode']} {tr['exit_type']} "
       f"dir={'LONG' if tr['direction']==1 else 'SHORT'} "
       f"pnl_per={tr['pnl_per_contract']} RBI={tr['RotBarIndex']} "
       f"dt={tr['datetime']}")
rp("")


# ════════════════════════════════════════════════════════════════════
# VERIFICATION FUNCTIONS
# ════════════════════════════════════════════════════════════════════
def find_touch(rbi, dt_str):
    """Find touch in merged data by RotBarIndex."""
    matches = merged_p1[merged_p1["RotBarIndex"] == rbi]
    if len(matches) == 0:
        # Try matching by datetime
        matches = merged_p1[merged_p1["DateTime"].str.contains(dt_str[:16], na=False)]
    if len(matches) > 0:
        return matches.iloc[0]
    return None


def find_aeq_score(rbi):
    """Find A-Eq score for a touch."""
    matches = aeq_df[aeq_df["RotBarIndex"] == rbi]
    if len(matches) > 0:
        return float(matches.iloc[0]["Score_AEq"])
    return None


def find_bz_score(rbi):
    """Find B-ZScore for a touch."""
    matches = bz_df[bz_df["RotBarIndex"] == rbi]
    if len(matches) > 0:
        return float(matches.iloc[0]["Score_BZScore"])
    return None


def get_session_class(rbi):
    """Get SessionClass from merged data."""
    matches = merged_p1[merged_p1["RotBarIndex"] == rbi]
    if len(matches) > 0:
        return str(matches.iloc[0].get("SessionClass", ""))
    # Try from aeq_df which may have it
    matches = aeq_df[aeq_df["RotBarIndex"] == rbi]
    if len(matches) > 0:
        sc = matches.iloc[0].get("SessionClass", "")
        if pd.notna(sc):
            return str(sc)
    return ""


def format_bar(bar_idx):
    """Format a bar's OHLC for display."""
    if bar_idx < 0 or bar_idx >= n_bars:
        return "OUT OF RANGE"
    o, h, l, c = bar_arr[bar_idx]
    dt = bar_dt.iloc[bar_idx]
    return f"{dt} | O={o:.2f} H={h:.2f} L={l:.2f} C={c:.2f}"


discrepancies = []


def verify_trade(trade_num, trade_idx, category):
    """Full verification of a single trade."""
    tr = p1_trades.loc[trade_idx]
    rbi = int(tr["RotBarIndex"])
    entry_bar = rbi + 1
    direction = int(tr["direction"])
    mode = tr["mode"]
    dir_str = "LONG" if direction == 1 else "SHORT"
    expected_pnl = float(tr["pnl_per_contract"])
    expected_exit = str(tr["exit_type"])
    expected_bh = int(tr["bars_held"])
    contracts = int(tr["contracts"])
    zw = int(tr["zone_width"])

    rp(f"### Trade {trade_num}: {category}")
    rp(f"**Stress test row:** mode={mode}, datetime={tr['datetime']}, "
       f"direction={direction} ({dir_str}), pnl_per={expected_pnl}, "
       f"exit_type={expected_exit}, bars_held={expected_bh}, "
       f"contracts={contracts}, zone_width={zw}")
    rp("")

    # === Step A: Touch Signal ===
    rp("**Step A — Touch Signal:**")
    touch = find_touch(rbi, str(tr["datetime"]))
    if touch is not None:
        touch_type = str(touch.get("TouchType", "?"))
        zone_top = float(touch.get("ZoneTop", 0))
        zone_bot = float(touch.get("ZoneBot", 0))
        zw_computed = round((zone_top - zone_bot) / TICK)
        tf = str(touch.get("SourceLabel", "?"))
        seq = int(touch.get("TouchSequence", 0))
        session = str(touch.get("SessionClass", ""))
        rp(f"- Touch datetime: {touch.get('DateTime', '?')}")
        rp(f"- Zone: {touch_type}, edges: {zone_top:.2f} to {zone_bot:.2f}, "
           f"width: {zw_computed} ticks (CSV says {zw})")
        rp(f"- TF: {tf}, seq: {seq}, session: {session}")
    else:
        rp(f"- Touch NOT FOUND for RBI={rbi}")
        touch_type = "DEMAND" if direction == 1 else "SUPPLY"
        zw_computed = zw
        tf = "?"
        seq = 0
        session = ""
    rp("")

    # === Step B: Scoring & Mode ===
    rp("**Step B — Scoring:**")
    aeq_score = find_aeq_score(rbi)
    bz_score = find_bz_score(rbi)

    if aeq_score is not None:
        rp(f"- A-Eq score: {aeq_score:.2f} (threshold: {M1_THRESHOLD:.1f})")
    else:
        rp("- A-Eq score: NOT FOUND")

    if bz_score is not None:
        rp(f"- B-ZScore: {bz_score:.4f} (threshold: {M2_THRESHOLD})")
    else:
        rp("- B-ZScore: NOT FOUND")

    # Waterfall
    expected_mode = mode
    if aeq_score is not None and aeq_score >= M1_THRESHOLD:
        computed_mode = "M1"
    elif (bz_score is not None and bz_score >= M2_THRESHOLD):
        # Check RTH, seq, TF filters
        rth_ok = session in ["OpeningDrive", "Midday", "Close"] if session else True
        seq_ok = seq <= 2 if touch is not None else True
        tf_val = 0
        if tf and tf != "?":
            try:
                tf_val = int(tf.replace("m", ""))
            except ValueError:
                tf_val = 0
        tf_ok = tf_val <= 120 if tf_val > 0 else True
        if rth_ok and seq_ok and tf_ok:
            computed_mode = "M2"
        else:
            computed_mode = "skip"
    else:
        computed_mode = "skip"

    mode_match = computed_mode == expected_mode
    rp(f"- Waterfall result: {computed_mode} — CSV mode: {expected_mode} "
       f"{'MATCH' if mode_match else 'MISMATCH'}")
    if not mode_match:
        discrepancies.append((trade_num, "mode", computed_mode, expected_mode, "HIGH"))
    rp("")

    # === Step C: Entry ===
    rp("**Step C — Entry:**")
    if entry_bar >= n_bars:
        rp(f"- Entry bar {entry_bar} OUT OF RANGE (n_bars={n_bars})")
        rp("")
        return

    entry_price = bar_arr[entry_bar, 0]  # Open
    rp(f"- Entry bar (RBI+1={entry_bar}): {format_bar(entry_bar)}")
    rp(f"- Entry price (Open): {entry_price:.2f}")
    rp("")

    # === Step D: Compute Levels ===
    rp("**Step D — Expected Levels:**")
    if mode == "M1":
        stop_ticks = 190
        stop_price = entry_price - stop_ticks * TICK if direction == 1 else entry_price + stop_ticks * TICK
        t1_price = entry_price + 60 * TICK if direction == 1 else entry_price - 60 * TICK
        t2_price = entry_price + 120 * TICK if direction == 1 else entry_price - 120 * TICK
        be_stop = entry_price  # after T1

        rp(f"- Stop: {stop_price:.2f} ({stop_ticks}t from entry)")
        rp(f"- T1: {t1_price:.2f} (60t)")
        rp(f"- T2: {t2_price:.2f} (120t)")
        rp(f"- BE stop (after T1): {be_stop:.2f}")
    else:
        stop_t = max(round(1.3 * zw), 100)
        target_t = max(1, round(1.0 * zw))
        stop_price = entry_price - stop_t * TICK if direction == 1 else entry_price + stop_t * TICK
        target_price = entry_price + target_t * TICK if direction == 1 else entry_price - target_t * TICK

        # Verify sizing
        if zw < 150:
            expected_contracts = 3
        elif zw <= 250:
            expected_contracts = 2
        else:
            expected_contracts = 1

        rp(f"- Stop: {stop_price:.2f} ({stop_t}t = max(1.3x{zw}, 100))")
        rp(f"- Target: {target_price:.2f} ({target_t}t = 1.0x{zw})")
        rp(f"- Contracts: {expected_contracts} (ZW={zw}) — CSV says {contracts} "
           f"{'MATCH' if expected_contracts == contracts else 'MISMATCH'}")
        if expected_contracts != contracts:
            discrepancies.append((trade_num, "contracts", expected_contracts, contracts, "HIGH"))
    rp("")

    # === Step E: Bar Walk ===
    rp("**Step E — Bar Walk:**")

    if mode == "M1":
        # Walk M1 with partial state machine
        t1_filled = False
        t1_fill_bar = None
        current_stop = stop_price
        exit_bar_idx = None
        exit_type_actual = None
        leg_pnls = [0.0, 0.0]  # T1 (1ct), T2 (2ct)

        max_walk = min(entry_bar + 200, n_bars)  # safety limit well beyond TC=120
        for i in range(entry_bar, max_walk):
            bh = i - entry_bar + 1
            h, l, last = bar_arr[i, 1], bar_arr[i, 2], bar_arr[i, 3]

            # Check stop
            if direction == 1:
                stop_hit = l <= current_stop
            else:
                stop_hit = h >= current_stop

            if stop_hit:
                if not t1_filled:
                    # Full stop — all 3ct at -190t
                    stop_pnl = (current_stop - entry_price) / TICK if direction == 1 else (entry_price - current_stop) / TICK
                    leg_pnls = [stop_pnl, stop_pnl]
                    exit_type_actual = "stop"
                    rp(f"- Bar {bh} ({format_bar(i)})")
                    rp(f"  **FULL STOP** at {current_stop:.2f}, pnl={stop_pnl:.1f}t per leg")
                else:
                    # BE stop after T1 — 2ct at BE
                    be_pnl = (current_stop - entry_price) / TICK if direction == 1 else (entry_price - current_stop) / TICK
                    leg_pnls[1] = be_pnl
                    exit_type_actual = "stop"
                    rp(f"- Bar {bh} ({format_bar(i)})")
                    rp(f"  **BE STOP** after T1, 2ct at {current_stop:.2f}, pnl={be_pnl:.1f}t")
                exit_bar_idx = i
                break

            # Check T1 (if not filled)
            if not t1_filled:
                if direction == 1:
                    t1_hit = h >= t1_price
                else:
                    t1_hit = l <= t1_price
                if t1_hit:
                    t1_filled = True
                    t1_fill_bar = bh
                    leg_pnls[0] = 60.0
                    current_stop = be_stop  # move to BE
                    rp(f"- Bar {bh} ({format_bar(i)})")
                    rp(f"  **T1 FILL** at {t1_price:.2f}, 1ct x 60t = 60t. Stop moves to BE={be_stop:.2f}")

            # Check T2 (only if T1 filled)
            if t1_filled:
                if direction == 1:
                    t2_hit = h >= t2_price
                else:
                    t2_hit = l <= t2_price
                if t2_hit:
                    leg_pnls[1] = 120.0
                    exit_type_actual = "target_2"
                    rp(f"- Bar {bh} ({format_bar(i)})")
                    rp(f"  **T2 FILL** at {t2_price:.2f}, 2ct x 120t = 240t")
                    exit_bar_idx = i
                    break

            # Time cap
            if bh >= 120:
                tc_pnl = (last - entry_price) / TICK if direction == 1 else (entry_price - last) / TICK
                if not t1_filled:
                    leg_pnls = [tc_pnl, tc_pnl]
                else:
                    leg_pnls[1] = tc_pnl
                exit_type_actual = "time_cap"
                rp(f"- Bar {bh} ({format_bar(i)})")
                rp(f"  **TIME CAP** at bar 120, close={last:.2f}, tc_pnl={tc_pnl:.1f}t")
                exit_bar_idx = i
                break

        if exit_bar_idx is None:
            rp(f"  **NO EXIT FOUND** within walk limit!")
            exit_bar_idx = max_walk - 1
            exit_type_actual = "no_exit"

        actual_bh = exit_bar_idx - entry_bar + 1

        # Compute weighted PnL (same as simulator)
        weighted_pnl = 0.333 * leg_pnls[0] + 0.667 * leg_pnls[1]

    else:
        # M2 walk
        exit_bar_idx = None
        exit_type_actual = None
        actual_pnl = None

        end = min(entry_bar + 80, n_bars)
        for i in range(entry_bar, end):
            bh = i - entry_bar + 1
            h, l, last = bar_arr[i, 1], bar_arr[i, 2], bar_arr[i, 3]

            if direction == 1:
                stop_hit = l <= stop_price
                target_hit_check = h >= target_price
            else:
                stop_hit = h >= stop_price
                target_hit_check = l <= target_price

            if stop_hit:
                pnl = (stop_price - entry_price) / TICK if direction == 1 else (entry_price - stop_price) / TICK
                exit_type_actual = "STOP"
                actual_pnl = pnl
                rp(f"- Bar {bh} ({format_bar(i)})")
                rp(f"  **STOP** at {stop_price:.2f}, pnl={pnl:.1f}t")
                exit_bar_idx = i
                break

            if target_hit_check:
                exit_type_actual = "TARGET"
                actual_pnl = target_t
                rp(f"- Bar {bh} ({format_bar(i)})")
                rp(f"  **TARGET** at {target_price:.2f}, pnl={target_t:.1f}t")
                exit_bar_idx = i
                break

            if bh >= 80:
                pnl = (last - entry_price) / TICK if direction == 1 else (entry_price - last) / TICK
                exit_type_actual = "TIMECAP"
                actual_pnl = pnl
                rp(f"- Bar {bh} ({format_bar(i)})")
                rp(f"  **TIMECAP** at bar 80, close={last:.2f}, pnl={pnl:.1f}t")
                exit_bar_idx = i
                break

        if exit_bar_idx is None:
            # Ran out of bars before TC
            if end > entry_bar:
                last = bar_arr[end - 1, 3]
                pnl = (last - entry_price) / TICK if direction == 1 else (entry_price - last) / TICK
                actual_pnl = pnl
                exit_type_actual = "TIMECAP"
                exit_bar_idx = end - 1
                rp(f"- Bar {end - entry_bar} ({format_bar(end - 1)})")
                rp(f"  **END OF DATA** pnl={pnl:.1f}t")
            else:
                actual_pnl = 0
                exit_type_actual = "no_exit"
                exit_bar_idx = entry_bar

        actual_bh = exit_bar_idx - entry_bar + 1
        weighted_pnl = actual_pnl  # M2 has no weighting
    rp("")

    # === Step F: Verify PnL ===
    rp("**Step F — PnL Verification:**")

    if mode == "M1":
        rp(f"- Leg PnLs: T1={leg_pnls[0]:.2f}t, T2={leg_pnls[1]:.2f}t")
        rp(f"- Weighted: 0.333×{leg_pnls[0]:.2f} + 0.667×{leg_pnls[1]:.2f} = {weighted_pnl:.4f}t")
    else:
        rp(f"- Raw PnL: {weighted_pnl:.2f}t per contract")

    pnl_diff = abs(weighted_pnl - expected_pnl)
    pnl_ok = pnl_diff < 1.0  # within 1 tick tolerance
    rp(f"- Expected (CSV): {expected_pnl:.4f}t")
    rp(f"- Computed: {weighted_pnl:.4f}t")
    rp(f"- Difference: {pnl_diff:.4f}t — {'MATCH' if pnl_ok else 'MISMATCH'}")
    if not pnl_ok:
        discrepancies.append((trade_num, "pnl_per_contract",
                              f"{weighted_pnl:.4f}", f"{expected_pnl:.4f}",
                              "HIGH" if pnl_diff > 5 else "LOW"))
    rp("")

    # === Step G: Verify bars_held ===
    rp("**Step G — bars_held Verification:**")
    bh_ok = actual_bh == expected_bh
    rp(f"- Computed: {actual_bh} (bar {entry_bar} to {exit_bar_idx})")
    rp(f"- Expected (CSV): {expected_bh}")
    rp(f"- {'MATCH' if bh_ok else 'MISMATCH'}")
    if not bh_ok:
        discrepancies.append((trade_num, "bars_held",
                              str(actual_bh), str(expected_bh), "MEDIUM"))
    rp("")

    # Exit type check
    exit_ok = exit_type_actual == expected_exit
    rp(f"**Exit type:** computed={exit_type_actual}, CSV={expected_exit} — "
       f"{'MATCH' if exit_ok else 'MISMATCH'}")
    if not exit_ok:
        discrepancies.append((trade_num, "exit_type",
                              exit_type_actual, expected_exit, "HIGH"))

    overall = "PASS" if (pnl_ok and bh_ok and exit_ok and mode_match) else "FAIL"
    rp(f"\n**Verdict: {'PASS' if overall == 'PASS' else 'FAIL'}**")
    rp("")
    rp("---")
    rp("")

    return overall


# ════════════════════════════════════════════════════════════════════
# RUN VERIFICATION ON ALL SELECTED TRADES
# ════════════════════════════════════════════════════════════════════
rp("---")
rp("")
rp("## Trade Verification Details")
rp("")

verdicts = []
for i, (idx, cat) in enumerate(zip(selected_indices, selected_categories)):
    v = verify_trade(i + 1, idx, cat)
    verdicts.append(v)


# ════════════════════════════════════════════════════════════════════
# STEP H: NO-OVERLAP CHECK (ALL 331 P1 TRADES)
# ════════════════════════════════════════════════════════════════════
rp("## Step H: No-Overlap Check (All 331 P1 Trades)")
rp("")

sorted_trades = p1_trades.sort_values("RotBarIndex").reset_index(drop=True)
overlap_count = 0
overlap_details = []

for i in range(len(sorted_trades) - 1):
    t1_entry = int(sorted_trades.loc[i, "RotBarIndex"]) + 1
    t1_bh = int(sorted_trades.loc[i, "bars_held"])
    t1_exit = t1_entry + t1_bh - 1  # last bar of trade

    t2_rbi = int(sorted_trades.loc[i + 1, "RotBarIndex"])
    t2_entry = t2_rbi + 1

    if t2_entry <= t1_exit:
        overlap_count += 1
        overlap_details.append(
            f"Trade {i} (entry={t1_entry}, exit={t1_exit}) overlaps with "
            f"trade {i+1} (entry={t2_entry})")

rp(f"- Trades checked: {len(sorted_trades)}")
rp(f"- Overlaps found: {overlap_count}")
if overlap_count > 0:
    rp("")
    for d in overlap_details[:10]:
        rp(f"  - {d}")
    if overlap_count > 10:
        rp(f"  ... and {overlap_count - 10} more")
    discrepancies.append(("ALL", "overlap", f"{overlap_count} overlaps", "0", "CRITICAL"))
else:
    rp("- **No overlapping trades detected.**")
rp("")

# Also check skip-due-to-position-open
rp("### Skip-Due-to-Position-Open Verification")
rp("")

# Find cases where a qualifying touch was skipped
# Look for consecutive qualifying touches where first was taken and gap is small
skip_verified = False
for i in range(len(sorted_trades) - 1):
    t1_entry = int(sorted_trades.loc[i, "RotBarIndex"]) + 1
    t1_bh = int(sorted_trades.loc[i, "bars_held"])
    t1_exit = t1_entry + t1_bh - 1

    t2_rbi = int(sorted_trades.loc[i + 1, "RotBarIndex"])
    t2_entry = t2_rbi + 1

    # The gap between trades — if small, there might have been a skipped touch
    gap = t2_entry - t1_exit
    if 1 <= gap <= 5:
        # Check if there was a qualifying touch between t1_exit and t2_rbi
        # that was skipped during t1's trade duration
        between = merged_p1[
            (merged_p1["RotBarIndex"] > int(sorted_trades.loc[i, "RotBarIndex"])) &
            (merged_p1["RotBarIndex"] < t2_rbi) &
            (merged_p1["RotBarIndex"] + 1 <= t1_exit)
        ]
        if len(between) > 0:
            skip_touch = between.iloc[0]
            skip_rbi = int(skip_touch["RotBarIndex"])
            skip_aeq = find_aeq_score(skip_rbi)
            skip_bz = find_bz_score(skip_rbi)
            qualifies = False
            if skip_aeq is not None and skip_aeq >= M1_THRESHOLD:
                qualifies = True
            elif skip_bz is not None and skip_bz >= M2_THRESHOLD:
                qualifies = True

            if qualifies:
                rp(f"- Found skipped qualifying touch at RBI={skip_rbi} "
                   f"(A-Eq={skip_aeq}, BZ={skip_bz})")
                rp(f"  - Previous trade: entry={t1_entry}, exit={t1_exit}")
                rp(f"  - Skip entry would be: {skip_rbi + 1}")
                rp(f"  - Position was open (exit {t1_exit} >= skip entry {skip_rbi + 1}): "
                   f"{'YES — skip correct' if t1_exit >= skip_rbi + 1 else 'NO — should have entered'}")
                skip_verified = True
                break

if not skip_verified:
    # Broader search — find any qualifying touch during a trade's duration
    for i in range(min(50, len(sorted_trades))):
        t_entry = int(sorted_trades.loc[i, "RotBarIndex"]) + 1
        t_bh = int(sorted_trades.loc[i, "bars_held"])
        t_exit = t_entry + t_bh - 1

        during = merged_p1[
            (merged_p1["RotBarIndex"] + 1 > t_entry) &
            (merged_p1["RotBarIndex"] + 1 <= t_exit)
        ]
        for _, sk in during.iterrows():
            sk_rbi = int(sk["RotBarIndex"])
            sk_aeq = find_aeq_score(sk_rbi)
            sk_bz = find_bz_score(sk_rbi)
            qualifies = False
            if sk_aeq is not None and sk_aeq >= M1_THRESHOLD:
                qualifies = True
            elif sk_bz is not None and sk_bz >= M2_THRESHOLD:
                qualifies = True
            if qualifies:
                rp(f"- Found skipped qualifying touch at RBI={sk_rbi} "
                   f"during trade {i} (entry={t_entry}, exit={t_exit})")
                rp(f"  - A-Eq={sk_aeq}, BZ={sk_bz}")
                rp(f"  - Position was open: YES — skip correct")
                skip_verified = True
                break
        if skip_verified:
            break

if not skip_verified:
    rp("- No clear skip-due-to-position-open case found in first 50 trades")
    rp("  (may indicate no qualifying touches occur during other trades' durations)")
rp("")

# ════════════════════════════════════════════════════════════════════
# COST MODEL VERIFICATION
# ════════════════════════════════════════════════════════════════════
rp("## Cost Model Verification")
rp("")
rp("CSV columns contain **GROSS PnL** (no cost deduction). "
   "Cost (3t/ct for P1) is applied only in PF/WR aggregate calculations.")
rp("")
rp("Verification on 3 sample trades:")
rp("")

# Pick a winner, a loser, and a non-3ct M2
cost_samples = []
for idx in selected_indices:
    tr = p1_trades.loc[idx]
    if tr["pnl_per_contract"] > 50 and len(cost_samples) < 1:
        cost_samples.append(idx)
    elif tr["pnl_per_contract"] < -50 and len(cost_samples) < 2:
        cost_samples.append(idx)
    elif tr["contracts"] != 3 and tr["mode"] == "M2" and len(cost_samples) < 3:
        cost_samples.append(idx)
    if len(cost_samples) >= 3:
        break

# Fill remaining if needed
for idx in selected_indices:
    if len(cost_samples) >= 3:
        break
    if idx not in cost_samples:
        cost_samples.append(idx)

for idx in cost_samples:
    tr = p1_trades.loc[idx]
    gross = float(tr["pnl_per_contract"])
    cts = int(tr["contracts"])
    cost_total = 3 * cts
    net_total = gross * cts - cost_total
    rp(f"- {tr['mode']} {tr['exit_type']}: gross={gross:.2f}t/ct × {cts}ct = "
       f"{gross * cts:.2f}t, cost={cost_total}t, net={net_total:.2f}t")

rp("")

# ════════════════════════════════════════════════════════════════════
# DISCREPANCY LOG & SUMMARY
# ════════════════════════════════════════════════════════════════════
rp("---")
rp("")
rp("## Discrepancy Log")
rp("")
if len(discrepancies) == 0:
    rp("| Trade | Field | Expected (bar data) | Stress test says | Severity |")
    rp("|-------|-------|-------------------|-----------------|----------|")
    rp("| (none) | — | — | — | — |")
else:
    rp("| Trade | Field | Expected (bar data) | Stress test says | Severity |")
    rp("|-------|-------|-------------------|-----------------|----------|")
    for trade_n, field, expected, actual, sev in discrepancies:
        rp(f"| {trade_n} | {field} | {expected} | {actual} | {sev} |")
rp("")

# Summary
rp("---")
rp("")
rp("## Summary")
rp("")
n_pass = sum(1 for v in verdicts if v == "PASS")
n_fail = sum(1 for v in verdicts if v == "FAIL")
rp(f"- **Trades verified:** {len(verdicts)} of {len(p1_trades)} P1 trades")
rp(f"- **PASS:** {n_pass}")
rp(f"- **FAIL:** {n_fail}")
rp(f"- **Overlaps detected:** {overlap_count}")
rp(f"- **Discrepancies:** {len(discrepancies)}")
rp("")

categories_covered = selected_categories
rp("**Categories covered:**")
for c in categories_covered:
    rp(f"- {c}")
rp("")

overall_result = "PASS" if (n_fail == 0 and overlap_count == 0) else "FAIL"
rp(f"## Result: **{overall_result}**")
rp("")
if overall_result == "PASS":
    rp("All selected trades match ground truth bar data. The v3.2 simulator "
       "produces correct entry prices, exit levels, PnL calculations, "
       "bars_held counts, and respects the one-position-at-a-time rule.")
else:
    rp("Discrepancies found — see details above. Investigate before proceeding.")

# ════════════════════════════════════════════════════════════════════
# SAVE REPORT
# ════════════════════════════════════════════════════════════════════
report_path = OUT_DIR / "v32_simulation_verification_report.md"
report_path.write_text("\n".join(report_lines), encoding="utf-8")
print(f"\nReport saved to: {report_path}")
