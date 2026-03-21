#!/usr/bin/env python3
"""First-passage from completion point: does reversion target hit before stop?

For each parent-scale completion at 40pt, walk RAW 1-tick bars from the
completion point and measure first-passage to reversion target vs continuation stop.

Targets (reversion, against parent dir): -8, -12, -16, -20, -24
Stops (continuation, same as parent dir): +20, +30, +40, +50
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
REVERSION_TARGETS = [8, 12, 16, 20, 24]
STOP_LEVELS = [20, 30, 40, 50]


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
def find_completions_with_raw_idx(
    c_prices, c_dirs, c_sids, c_idx, parent_thresh
):
    """Walk child swings, find completions, return the raw bar index and
    direction (att) at each completion point."""
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
def first_passage_from_completions(
    raw_prices, raw_sids, comp_raw_idx, comp_att,
    rev_target, stop_level,
):
    """For each completion, walk raw bars and check first passage.

    rev_target: positive number, reversion distance (against parent dir)
    stop_level: positive number, continuation distance (same as parent dir)

    Returns per-completion:
      outcome: 1=reversion hit first, 2=stop hit first, 0=session end
      bars_to_outcome: bars from completion to outcome
    """
    n_comp = len(comp_raw_idx)
    n_raw = len(raw_prices)
    o_outcome = np.empty(n_comp, dtype=np.int8)
    o_bars    = np.empty(n_comp, dtype=np.int64)

    for k in range(n_comp):
        start = comp_raw_idx[k]
        att = comp_att[k]
        comp_price = raw_prices[start]
        sid = raw_sids[start]

        outcome = np.int8(0)
        bars = np.int64(0)

        for j in range(start + 1, n_raw):
            if raw_sids[j] != sid:
                break
            bars += 1
            move = (raw_prices[j] - comp_price) * att
            # move > 0 = continuation (same as parent); move < 0 = reversion
            if -move >= rev_target:  # reversion hit
                outcome = np.int8(1)
                break
            if move >= stop_level:   # stop hit
                outcome = np.int8(2)
                break

        o_outcome[k] = outcome
        o_bars[k] = bars

    return o_outcome, o_bars


def main():
    t0 = time.time()
    print("=" * 60)
    print("FIRST-PASSAGE FROM COMPLETION POINT")
    print(f"Parent={PARENT_THRESH}pt, Child={CHILD_THRESH}pt")
    print("=" * 60)

    prices, time_secs, cal_dates = load_p1_rth()
    trading_dates = compute_trading_dates(cal_dates, time_secs)
    sids = assign_session_ids(trading_dates)

    # Get child swings
    sw_idx, sw_price, sw_dir, sw_sid = zigzag(prices, sids, float(CHILD_THRESH))
    print(f"  {len(sw_price):,} child swings")

    # Find completions with raw bar index
    comp_idx, comp_att = find_completions_with_raw_idx(
        sw_price.astype(np.float64), sw_dir, sw_sid, sw_idx, float(PARENT_THRESH)
    )
    print(f"  {len(comp_idx):,} completions found")

    # Run first-passage for all target/stop combinations
    rows = []
    print(f"\n{'Rev Target':>12s} {'Stop':>6s} {'Rev Wins':>10s} {'Stop Wins':>10s} {'Sess End':>10s} {'Win Rate':>9s} {'Med Bars':>9s}")
    print("-" * 75)

    for rev in REVERSION_TARGETS:
        for stop in STOP_LEVELS:
            outcome, bars = first_passage_from_completions(
                prices, sids, comp_idx, comp_att,
                float(rev), float(stop),
            )
            n = len(outcome)
            rev_wins = int((outcome == 1).sum())
            stop_wins = int((outcome == 2).sum())
            sess_end = int((outcome == 0).sum())
            win_rate = rev_wins / n if n > 0 else 0

            # Median bars for rev wins
            med_bars = int(np.median(bars[outcome == 1])) if rev_wins > 0 else 0

            rows.append({
                "reversion_target": rev,
                "stop_level": stop,
                "completions": n,
                "rev_wins": rev_wins,
                "stop_wins": stop_wins,
                "session_end": sess_end,
                "rev_win_rate": round(win_rate * 100, 2),
                "stop_rate": round(stop_wins / n * 100, 2) if n > 0 else 0,
                "sess_end_rate": round(sess_end / n * 100, 2) if n > 0 else 0,
                "median_bars_to_rev": med_bars,
            })

            print(f"{rev:>10d}pt {stop:>5d}pt {rev_wins:>8d} ({win_rate*100:5.1f}%) "
                  f"{stop_wins:>5d} ({stop_wins/n*100:5.1f}%) "
                  f"{sess_end:>5d} ({sess_end/n*100:5.1f}%) "
                  f"{win_rate*100:>7.1f}% {med_bars:>7d}")

    df = pd.DataFrame(rows)
    df.to_csv(OUT_DIR / "first_passage_40pt.csv", index=False)
    print(f"\n  first_passage_40pt.csv saved ({len(df)} rows)")

    # Pretty summary table
    lines = [
        "# First-Passage from Completion Point",
        f"**Parent:** {PARENT_THRESH}pt, **Child:** {CHILD_THRESH}pt",
        f"**Completions:** {len(comp_idx):,}",
        "",
        "## Win Rate Grid (% reversion target hit before stop)",
        "",
        "| Rev Target |" + "".join(f" Stop={s}pt |" for s in STOP_LEVELS),
        "|------------|" + "".join("----------|" for _ in STOP_LEVELS),
    ]
    for rev in REVERSION_TARGETS:
        cells = []
        for stop in STOP_LEVELS:
            r = next(x for x in rows if x["reversion_target"] == rev and x["stop_level"] == stop)
            cells.append(f" **{r['rev_win_rate']:.1f}%** ")
        lines.append(f"| {rev}pt |" + "|".join(cells) + "|")

    lines.extend([
        "",
        "## Session-End Rate Grid (% neither target hit before session end)",
        "",
        "| Rev Target |" + "".join(f" Stop={s}pt |" for s in STOP_LEVELS),
        "|------------|" + "".join("----------|" for _ in STOP_LEVELS),
    ])
    for rev in REVERSION_TARGETS:
        cells = []
        for stop in STOP_LEVELS:
            r = next(x for x in rows if x["reversion_target"] == rev and x["stop_level"] == stop)
            cells.append(f" {r['sess_end_rate']:.1f}% ")
        lines.append(f"| {rev}pt |" + "|".join(cells) + "|")

    lines.extend([
        "",
        "## Median Bars to Reversion Target (for wins only)",
        "",
        "| Rev Target |" + "".join(f" Stop={s}pt |" for s in STOP_LEVELS),
        "|------------|" + "".join("----------|" for _ in STOP_LEVELS),
    ])
    for rev in REVERSION_TARGETS:
        cells = []
        for stop in STOP_LEVELS:
            r = next(x for x in rows if x["reversion_target"] == rev and x["stop_level"] == stop)
            cells.append(f" {r['median_bars_to_rev']:,} ")
        lines.append(f"| {rev}pt |" + "|".join(cells) + "|")

    (OUT_DIR / "first_passage_summary.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"  first_passage_summary.md saved")
    print(f"\n  Total time: {time.time()-t0:.1f}s")


if __name__ == "__main__":
    main()
