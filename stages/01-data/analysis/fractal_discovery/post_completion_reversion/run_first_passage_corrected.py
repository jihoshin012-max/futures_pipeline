#!/usr/bin/env python3
"""Corrected first-passage from ACTUAL ENTRY POINT after parent completion.

The strategy can't enter at the completion extreme — it enters AFTER the
child-threshold reversal confirms the completion. Entry point is:
  LONG parent completion: completion_price - child_thresh (16pt)
  SHORT parent completion: completion_price + child_thresh (16pt)

From this entry, measure first-passage to:
  Targets (further reversion): -4, -8, -12, -16, -20 pts
  Stops (recovery toward completion extreme): +8, +16, +24, +32 pts
"""
import numpy as np
import numba as nb
import pandas as pd
from pathlib import Path
import sys
import time

_FRACTAL_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_FRACTAL_DIR))
from fractal_01_prepare import zigzag, compute_trading_dates, assign_session_ids

DATA_DIR = Path(r"C:\Projects\pipeline\stages\01-data\data\bar_data\tick")
P1_PATH = DATA_DIR / "NQ_BarData_1tick_rot_P1.csv"
OUT_DIR = Path(__file__).resolve().parent

RTH_START = 9 * 3600 + 30 * 60
RTH_END = 16 * 3600 + 15 * 60

PARENT_THRESH = 40
CHILD_THRESH = 16
REVERSION_TARGETS = [4, 8, 12, 16, 20]
STOP_LEVELS = [8, 16, 24, 32]


def load_p1_rth():
    print(f"Loading P1 1-tick data...")
    df = pd.read_csv(P1_PATH, usecols=[0, 1, 5], skipinitialspace=True,
                     header=0, low_memory=False)
    df.columns = ['date', 'time', 'price']
    t = df['time'].str.strip()
    parts = t.str.split(':', n=2, expand=True)
    time_secs = (parts[0].astype(np.int32) * 3600 +
                 parts[1].astype(np.int32) * 60 +
                 parts[2].astype(np.float64)).values.astype(np.float32)
    d = df['date'].str.strip()
    dparts = d.str.split('-', n=2, expand=True)
    cal_dates = (dparts[0].astype(np.int32) * 10000 +
                 dparts[1].astype(np.int32) * 100 +
                 dparts[2].astype(np.int32)).values.astype(np.int32)
    prices = df['price'].values.astype(np.float64)
    mask = (time_secs >= RTH_START) & (time_secs < RTH_END)
    prices = prices[mask].copy()
    time_secs = time_secs[mask].copy()
    cal_dates = cal_dates[mask].copy()
    print(f"  RTH rows: {len(prices):,}")
    return prices, time_secs, cal_dates


@nb.njit(cache=True)
def find_completions_with_raw_idx(c_prices, c_dirs, c_sids, c_idx, parent_thresh):
    """Walk child swings, find completions. Return raw bar index and att at
    each completion point (the child swing where fav >= parent_thresh)."""
    n = len(c_prices)
    mx = n // 2 + 1
    o_raw_idx = np.empty(mx, dtype=np.int64)
    o_att     = np.empty(mx, dtype=np.int8)
    cnt = 0

    i = 0
    while i < n - 1:
        cs = c_sids[i]
        anch_p = c_prices[i]
        i += 1
        if c_sids[i] != cs:
            continue
        disp = c_prices[i] - anch_p
        if disp == 0.0:
            continue
        att = np.int8(1) if disp > 0 else np.int8(-1)

        if abs(disp) >= parent_thresh:
            o_raw_idx[cnt] = c_idx[i]
            o_att[cnt] = att
            cnt += 1
            continue

        while True:
            i += 1
            if i >= n or c_sids[i] != cs:
                break
            fav = (c_prices[i] - anch_p) * att
            if fav >= parent_thresh:
                o_raw_idx[cnt] = c_idx[i]
                o_att[cnt] = att
                cnt += 1
                break
            elif fav <= -parent_thresh:
                break

    return o_raw_idx[:cnt], o_att[:cnt]


@nb.njit(cache=True)
def find_actual_entry_idx(
    raw_prices, raw_sids,
    comp_raw_idx, comp_att,
    child_thresh,
):
    """For each completion, walk forward in raw bars to find the first tick
    where price has reversed child_thresh from the completion extreme.

    The completion point is a child swing extreme. The zig-zag confirms it
    when price reverses child_thresh from that extreme. The FIRST raw bar
    where this reversal is reached is the actual entry point.

    Returns:
      entry_idx: raw bar index of actual entry
      entry_price: price at entry
      valid: True if entry found before session end
    """
    n_comp = len(comp_raw_idx)
    n_raw = len(raw_prices)
    o_entry_idx   = np.empty(n_comp, dtype=np.int64)
    o_entry_price = np.empty(n_comp, dtype=np.float64)
    o_valid       = np.empty(n_comp, dtype=nb.boolean)

    for k in range(n_comp):
        start = comp_raw_idx[k]
        att = comp_att[k]
        comp_price = raw_prices[start]
        sid = raw_sids[start]

        # Track extreme from completion point (price may extend further
        # before the reversal is confirmed)
        extreme = comp_price
        found = False

        for j in range(start + 1, n_raw):
            if raw_sids[j] != sid:
                break
            p = raw_prices[j]

            # Update extreme in parent direction
            if att == 1 and p > extreme:
                extreme = p
            elif att == -1 and p < extreme:
                extreme = p

            # Check reversal from extreme
            rev = (extreme - p) * att  # positive = reversal from extreme
            if rev >= child_thresh:
                o_entry_idx[k] = j
                o_entry_price[k] = p
                o_valid[k] = True
                found = True
                break

        if not found:
            o_entry_idx[k] = -1
            o_entry_price[k] = 0.0
            o_valid[k] = False

    return o_entry_idx, o_entry_price, o_valid


@nb.njit(cache=True)
def first_passage_from_entry(
    raw_prices, raw_sids,
    entry_idx, entry_price, entry_att, valid,
    rev_target, stop_level,
):
    """From each actual entry point, measure first-passage.

    The flipped strategy enters AGAINST the parent direction:
      - "reversion target" = price moves FURTHER against parent dir from entry
      - "stop" = price moves back TOWARD the completion extreme (same as parent dir)

    For a LONG parent completion, the flipped entry is SHORT:
      target hit: entry_price - price >= rev_target  (price drops further)
      stop hit:   price - entry_price >= stop_level  (price recovers up)

    Returns per-entry:
      outcome: 1=target hit, 2=stop hit, 0=session end
      bars: bars from entry to outcome
    """
    n = len(entry_idx)
    o_outcome = np.empty(n, dtype=np.int8)
    o_bars    = np.empty(n, dtype=np.int64)
    n_raw = len(raw_prices)

    for k in range(n):
        if not valid[k]:
            o_outcome[k] = -1
            o_bars[k] = 0
            continue

        start = entry_idx[k]
        ep = entry_price[k]
        att = entry_att[k]  # original parent direction
        sid = raw_sids[start]

        # Flipped strategy is AGAINST parent: favorable = against att
        outcome = np.int8(0)
        bars = np.int64(0)

        for j in range(start + 1, n_raw):
            if raw_sids[j] != sid:
                break
            bars += 1
            p = raw_prices[j]

            # Move from entry, measured in parent direction
            move_parent_dir = (p - ep) * att
            # move_parent_dir > 0 = toward completion extreme (bad for flipped = stop)
            # move_parent_dir < 0 = further reversion (good for flipped = target)

            if -move_parent_dir >= rev_target:
                outcome = np.int8(1)  # target hit
                break
            if move_parent_dir >= stop_level:
                outcome = np.int8(2)  # stop hit
                break

        o_outcome[k] = outcome
        o_bars[k] = bars

    return o_outcome, o_bars


def main():
    t0 = time.time()
    print("=" * 60)
    print("CORRECTED FIRST-PASSAGE FROM ACTUAL ENTRY POINT")
    print(f"Parent={PARENT_THRESH}pt, Child={CHILD_THRESH}pt")
    print(f"Entry = completion extreme - {CHILD_THRESH}pt reversal")
    print("=" * 60)

    prices, time_secs, cal_dates = load_p1_rth()
    trading_dates = compute_trading_dates(cal_dates, time_secs)
    sids = assign_session_ids(trading_dates)

    sw_idx, sw_price, sw_dir, sw_sid = zigzag(prices, sids, float(CHILD_THRESH))
    print(f"  {len(sw_price):,} child swings")

    comp_idx, comp_att = find_completions_with_raw_idx(
        sw_price.astype(np.float64), sw_dir, sw_sid, sw_idx, float(PARENT_THRESH)
    )
    print(f"  {len(comp_idx):,} completions")

    # Find actual entry points
    entry_idx, entry_price, valid = find_actual_entry_idx(
        prices, sids, comp_idx, comp_att, float(CHILD_THRESH)
    )
    n_valid = int(valid.sum())
    n_invalid = int((~valid).sum())
    print(f"  {n_valid:,} valid entries, {n_invalid} missed (session end before reversal)")

    # Report entry offset from completion
    comp_prices = prices[comp_idx]
    offsets = np.abs(entry_price[valid] - comp_prices[valid])
    print(f"  Entry offset from completion extreme:")
    print(f"    Median: {np.median(offsets):.2f} pts")
    print(f"    Mean:   {np.mean(offsets):.2f} pts")
    print(f"    Min:    {np.min(offsets):.2f}, Max: {np.max(offsets):.2f}")

    # Run grid
    rows = []
    print(f"\n{'Target':>8s} {'Stop':>6s} {'Wins':>12s} {'Stops':>12s} {'SessEnd':>12s} {'WinRate':>8s} {'MedBars':>8s}")
    print("-" * 70)

    for rev in REVERSION_TARGETS:
        for stop in STOP_LEVELS:
            outcome, bars = first_passage_from_entry(
                prices, sids,
                entry_idx, entry_price, comp_att, valid,
                float(rev), float(stop),
            )
            # Filter to valid entries only
            mask = valid
            o = outcome[mask]
            b = bars[mask]
            n = len(o)
            wins = int((o == 1).sum())
            stops = int((o == 2).sum())
            sess = int((o == 0).sum())
            wr = wins / n if n > 0 else 0
            med_b = int(np.median(b[o == 1])) if wins > 0 else 0

            rows.append({
                "reversion_target": rev,
                "stop_level": stop,
                "entries": n,
                "target_wins": wins,
                "stop_losses": stops,
                "session_end": sess,
                "win_rate": round(wr * 100, 2),
                "stop_rate": round(stops / n * 100, 2) if n > 0 else 0,
                "sess_end_rate": round(sess / n * 100, 2) if n > 0 else 0,
                "median_bars_to_target": med_b,
                "ev_per_trade": round(wr * rev - (1 - wr - sess / n) * stop, 2) if n > 0 else 0,
            })

            print(f"{rev:>6d}pt {stop:>5d}pt {wins:>6d} ({wr*100:5.1f}%) "
                  f"{stops:>6d} ({stops/n*100:5.1f}%) "
                  f"{sess:>6d} ({sess/n*100:5.1f}%) "
                  f"{wr*100:>6.1f}% {med_b:>7,}")

    df = pd.DataFrame(rows)
    df.to_csv(OUT_DIR / "first_passage_corrected_40pt.csv", index=False)
    print(f"\n  first_passage_corrected_40pt.csv saved")

    # Summary markdown
    lines = [
        "# Corrected First-Passage from Actual Entry Point",
        f"**Parent:** {PARENT_THRESH}pt, **Child:** {CHILD_THRESH}pt",
        f"**Entry:** Completion extreme minus {CHILD_THRESH}pt zig-zag reversal",
        f"**Valid entries:** {n_valid:,} (of {len(comp_idx):,} completions)",
        f"**Median entry offset from extreme:** {np.median(offsets):.1f} pts",
        "",
        "Targets = further reversion beyond entry (flipped strategy profit).",
        "Stops = recovery back toward completion extreme (flipped strategy loss).",
        "",
        "## Win Rate Grid",
        "",
        "| Target |" + "".join(f" Stop={s}pt |" for s in STOP_LEVELS),
        "|--------|" + "".join("---------|" for _ in STOP_LEVELS),
    ]
    for rev in REVERSION_TARGETS:
        cells = []
        for stop in STOP_LEVELS:
            r = next(x for x in rows if x["reversion_target"] == rev and x["stop_level"] == stop)
            cells.append(f" **{r['win_rate']:.1f}%** ")
        lines.append(f"| {rev}pt |" + "|".join(cells) + "|")

    lines.extend([
        "",
        "## EV per Trade (target_pts x win_rate - stop_pts x stop_rate)",
        "",
        "| Target |" + "".join(f" Stop={s}pt |" for s in STOP_LEVELS),
        "|--------|" + "".join("---------|" for _ in STOP_LEVELS),
    ])
    for rev in REVERSION_TARGETS:
        cells = []
        for stop in STOP_LEVELS:
            r = next(x for x in rows if x["reversion_target"] == rev and x["stop_level"] == stop)
            cells.append(f" {r['ev_per_trade']:+.1f} ")
        lines.append(f"| {rev}pt |" + "|".join(cells) + "|")

    lines.extend([
        "",
        "## Median Bars to Target (1-tick bars, wins only)",
        "",
        "| Target |" + "".join(f" Stop={s}pt |" for s in STOP_LEVELS),
        "|--------|" + "".join("---------|" for _ in STOP_LEVELS),
    ])
    for rev in REVERSION_TARGETS:
        cells = []
        for stop in STOP_LEVELS:
            r = next(x for x in rows if x["reversion_target"] == rev and x["stop_level"] == stop)
            cells.append(f" {r['median_bars_to_target']:,} ")
        lines.append(f"| {rev}pt |" + "|".join(cells) + "|")

    (OUT_DIR / "first_passage_corrected_summary.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"  first_passage_corrected_summary.md saved")
    print(f"\n  Total time: {time.time()-t0:.1f}s")


if __name__ == "__main__":
    main()
