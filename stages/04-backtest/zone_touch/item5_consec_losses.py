# archetype: zone_touch
"""ITEM 5: Consecutive Loss Sequences for seg3_A-Cal/ModeB (winner).

Reads p2_trade_details.csv. Outputs consecutive_loss_analysis.md.
"""

import numpy as np
import pandas as pd
from datetime import datetime
from pathlib import Path

OUT = Path(r"c:\Projects\pipeline\stages\04-backtest\zone_touch\output")
df = pd.read_csv(OUT / "p2_trade_details.csv")
w = df[df["seg_model_group"] == "seg3_ModeB"].sort_values("datetime").reset_index(drop=True)

w["dt"] = pd.to_datetime(w["datetime"])
w["date"] = w["dt"].dt.date
w["is_loss"] = w["pnl_ticks"] <= 0

print(f"Winner trades: {len(w)}, Losses: {w['is_loss'].sum()}")

# ── Streak helpers ───────────────────────────────────────────────────

def get_max_streak(loss_series):
    mx, cur = 0, 0
    for v in loss_series:
        if v:
            cur += 1
            mx = max(mx, cur)
        else:
            cur = 0
    return mx


def get_streak_ranges(df_sub):
    """Return list of (start_iloc, length) for loss streaks."""
    out = []
    start = None
    length = 0
    for i in range(len(df_sub)):
        if df_sub.iloc[i]["is_loss"]:
            if start is None:
                start = i
            length += 1
        else:
            if length > 0:
                out.append((start, length))
            start = None
            length = 0
    if length > 0:
        out.append((start, length))
    return out


# ── 1-3: Max consecutive losses ─────────────────────────────────────

streaks_all = get_streak_ranges(w)
max_all = max((s[1] for s in streaks_all), default=0)

w_a = w[w["period"] == "P2a"].reset_index(drop=True)
w_b = w[w["period"] == "P2b"].reset_index(drop=True)
w_a["is_loss"] = w_a["pnl_ticks"] <= 0
w_b["is_loss"] = w_b["pnl_ticks"] <= 0
max_a = get_max_streak(w_a["is_loss"])
max_b = get_max_streak(w_b["is_loss"])

print(f"Max consec losses — combined: {max_all}, P2a: {max_a}, P2b: {max_b}")

# ── 4: Same day / same TF for consecutive losses ────────────────────

for start, length in streaks_all:
    if length >= 2:
        st = w.iloc[start:start + length]
        same_day = len(set(st["date"])) == 1
        tfs = st["F01_Timeframe"].unique()
        same_tf = len(tfs) == 1
        d0 = st.iloc[0]["datetime"][:10]
        print(f"  Streak {length} @ {d0}: same_day={same_day}, "
              f"same_tf={same_tf} ({' / '.join(tfs)})")

# ── 5: Worst streak PnL ─────────────────────────────────────────────

worst_pnl = 0.0
for start, length in streaks_all:
    sp = w.iloc[start:start + length]["pnl_ticks"].sum()
    if sp < worst_pnl:
        worst_pnl = sp
print(f"Worst streak PnL: {worst_pnl:.1f} ticks")

# ── 6: Longest drawdown duration ────────────────────────────────────

cum_pnl = w["pnl_ticks"].cumsum().values
peak = np.maximum.accumulate(cum_pnl)
dd = peak - cum_pnl

# Track drawdown in bars and calendar days
longest_dd_bars = 0
longest_dd_days = 0
max_dd_depth = dd.max()

cur_dd_bars = 0
cur_dd_start_dt = None

for i in range(len(w)):
    if dd[i] > 0:
        cur_dd_bars += int(w.iloc[i]["bars_held"])
        if cur_dd_start_dt is None:
            # find last peak before this
            for j in range(i, -1, -1):
                if dd[j] == 0:
                    cur_dd_start_dt = w.iloc[j]["dt"]
                    break
            if cur_dd_start_dt is None:
                cur_dd_start_dt = w.iloc[0]["dt"]
        cal_days = (w.iloc[i]["dt"] - cur_dd_start_dt).days
        if cur_dd_bars > longest_dd_bars:
            longest_dd_bars = cur_dd_bars
        if cal_days > longest_dd_days:
            longest_dd_days = cal_days
    else:
        cur_dd_bars = 0
        cur_dd_start_dt = None

print(f"Longest DD: {longest_dd_bars} bars, ~{longest_dd_days} cal days, "
      f"depth={max_dd_depth:.1f}t")

# ── 7: Streak detail table ──────────────────────────────────────────

streak_rows = []
for start, length in streaks_all:
    if length < 2:
        continue
    st = w.iloc[start:start + length]
    total_pnl = st["pnl_ticks"].sum()
    date_strs = [d.strftime("%m/%d %H:%M") for d in st["dt"]]
    same_day = len(set(st["date"])) == 1
    tfs = st["F01_Timeframe"].unique()
    same_tf = len(tfs) == 1

    # Recovery: bars from end of streak to equity recovery
    end_iloc = start + length
    pre_equity = cum_pnl[start - 1] if start > 0 else 0.0
    rec_bars = 0
    recovered = False
    for j in range(end_iloc, len(w)):
        rec_bars += int(w.iloc[j]["bars_held"])
        if cum_pnl[j] >= pre_equity:
            recovered = True
            break

    if recovered:
        rec_str = str(rec_bars)
    elif end_iloc < len(w):
        rec_str = f"{rec_bars}+ (open)"
    else:
        rec_str = "N/A (end of sample)"

    streak_rows.append({
        "length": length,
        "dates": " -> ".join(date_strs),
        "total_pnl": total_pnl,
        "same_day": "Yes" if same_day else "No",
        "same_tf": f"Yes ({tfs[0]})" if same_tf else f"No ({' / '.join(tfs)})",
        "recovery": rec_str,
    })

# ── W/L sequence ────────────────────────────────────────────────────

seq = "".join("W" if p > 0 else ("L" if p < 0 else "B") for p in w["pnl_ticks"])
print(f"\nW/L sequence: {seq}")
print(f"  {len(w)} trades: {seq.count('W')}W {seq.count('L')}L {seq.count('B')}B")

# ── Write markdown ──────────────────────────────────────────────────

L = []
L.append("# ITEM 5: Consecutive Loss Sequences — seg3_A-Cal/ModeB (Winner)")
L.append(f"Generated: {datetime.now().isoformat()}")
L.append(f"Total trades: {len(w)}, Losses: {w['is_loss'].sum()}")
L.append("")
L.append("## Summary")
L.append("")
L.append("| Metric | Value |")
L.append("|--------|-------|")
L.append(f"| Max consecutive losses (P2 combined) | {max_all} |")
L.append(f"| Max consecutive losses (P2a) | {max_a} |")
L.append(f"| Max consecutive losses (P2b) | {max_b} |")
L.append(f"| Worst streak PnL | {worst_pnl:.1f} ticks |")
L.append(f"| Longest DD duration (bars) | {longest_dd_bars} |")
L.append(f"| Longest DD duration (cal days) | ~{longest_dd_days} |")
L.append(f"| Max DD depth | {max_dd_depth:.1f} ticks |")
L.append("")

L.append("## W/L Sequence (chronological)")
L.append(f"`{seq}`")
L.append(f"({len(w)} trades: {seq.count('W')}W, {seq.count('L')}L, {seq.count('B')}B)")
L.append("")

if streak_rows:
    L.append("## Loss Streaks (2+ consecutive)")
    L.append("")
    L.append("| Streak | Trades | Dates | Total PnL | Same Day? | Same TF? | Recovery (bars) |")
    L.append("|--------|--------|-------|-----------|-----------|----------|-----------------|")
    for i, sr in enumerate(streak_rows, 1):
        L.append(f"| {i} | {sr['length']} | {sr['dates']} | "
                 f"{sr['total_pnl']:.1f} | {sr['same_day']} | {sr['same_tf']} | "
                 f"{sr['recovery']} |")
    L.append("")
else:
    L.append("## Loss Streaks")
    L.append("No loss streaks of 2+ consecutive trades.")
    L.append("")

L.append("## Kill-Switch Implications")
L.append("")
L.append(f"- Max observed consecutive losses: **{max_all}**")
if max_all <= 2:
    L.append("- [SUGGESTION] Kill-switch at 3 consecutive losses would never have "
             "triggered on P2.")
    L.append("- [SUGGESTION] Kill-switch at 4 consecutive losses provides "
             "1-trade buffer beyond observed worst case.")
else:
    L.append(f"- [SUGGESTION] Kill-switch at {max_all + 2} consecutive losses "
             "provides 2-trade buffer beyond observed worst case.")

worst_usd = abs(worst_pnl) * 5.0  # NQ: $5 per tick
L.append(f"- Worst single-streak damage: {worst_pnl:.1f}t = "
         f"${worst_usd:,.0f} per contract")
L.append(f"- [SUGGESTION] Position sizing should tolerate "
         f"{abs(worst_pnl):.0f}t drawdown without exceeding risk limits.")
L.append(f"- Max DD depth across all trades: {max_dd_depth:.1f}t = "
         f"${max_dd_depth * 5:,.0f} per contract")

md_path = OUT / "consecutive_loss_analysis.md"
with open(md_path, "w", encoding="utf-8") as f:
    f.write("\n".join(L))
print(f"\nSaved to {md_path.name}")
