# archetype: rotational
"""RTH Swing Blocks — Clock-Time Validation.

Validates whether the amplitude uniformity across RTH blocks is real or a
tick-bar artifact by computing clock-time metrics: swing duration, swings/hour,
price travel/minute, and points available per hour.

Reads the same P1-only NQ 250T data and reuses block/swing definitions from
analyze_rth_swing_blocks.py.

Outputs:
  - Updates rth_swings_by_block.csv with swing_duration_sec column
  - rth_swing_block_clocktime.json
"""

import datetime as dt
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

_REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_REPO))
from shared.data_loader import load_bars

OUT_DIR = Path(__file__).parent

P1_END = pd.Timestamp("2025-12-14 23:59:59")
P1A_END = pd.Timestamp("2025-11-02 23:59:59")

BLOCKS = [
    ("Open",      dt.time(9, 30),  dt.time(10, 0)),
    ("Morning",   dt.time(10, 0),  dt.time(11, 30)),
    ("Midday",    dt.time(11, 30), dt.time(13, 30)),
    ("Afternoon", dt.time(13, 30), dt.time(15, 0)),
    ("Close",     dt.time(15, 0),  dt.time(16, 0)),
]

BLOCK_LABELS = {
    "Open":      "09:30-10:00",
    "Morning":   "10:00-11:30",
    "Midday":    "11:30-13:30",
    "Afternoon": "13:30-15:00",
    "Close":     "15:00-16:00",
}

# Block durations in hours (for swings/hour calculation)
BLOCK_HOURS = {
    "Open":      0.5,
    "Morning":   1.5,
    "Midday":    2.0,
    "Afternoon": 1.5,
    "Close":     1.0,
}


def assign_block(t: dt.time) -> str:
    for name, start, end in BLOCKS:
        if start <= t < end:
            return name
    return ""


def main():
    # ------------------------------------------------------------------
    # Load data
    # ------------------------------------------------------------------
    print("Loading NQ 250-tick P1 data...")
    bars = load_bars(str(_REPO / "stages/01-data/data/bar_data/tick/NQ_BarData_250tick_rot_P1.csv"))
    bars = bars[bars["datetime"] <= P1_END].copy()
    print(f"  Bars: {len(bars):,}  ({bars['datetime'].iloc[0]} to {bars['datetime'].iloc[-1]})")

    # Assign block to every bar
    bar_time = bars["datetime"].dt.time
    bars["block"] = [assign_block(t) for t in bar_time]
    bars["period"] = np.where(bars["datetime"] <= P1A_END, "P1a", "P1b")

    # Count trading sessions (unique dates with RTH bars)
    rth_bars = bars[bars["block"] != ""]
    trading_dates = rth_bars["datetime"].dt.date.unique()
    n_sessions = len(trading_dates)
    print(f"  RTH trading sessions: {n_sessions}")

    # ------------------------------------------------------------------
    # 1. Swing duration — rebuild swing table with durations
    # ------------------------------------------------------------------
    rev_mask = bars["Zig Zag Line Length"] != 0
    reversals = bars[rev_mask][["datetime", "Zig Zag Line Length"]].copy()
    reversals = reversals.reset_index(drop=True)

    swing_start_time = reversals["datetime"].iloc[:-1].values
    swing_end_time = reversals["datetime"].iloc[1:].values
    swing_sizes = np.abs(reversals["Zig Zag Line Length"].iloc[1:].values)

    swings = pd.DataFrame({
        "swing_start_time": swing_start_time,
        "swing_end_time":   swing_end_time,
        "swing_size_pts":   swing_sizes,
    })

    # Duration in seconds
    swings["swing_duration_sec"] = (
        (pd.to_datetime(swings["swing_end_time"]) -
         pd.to_datetime(swings["swing_start_time"]))
        .dt.total_seconds()
    )

    # Assign block and period from start time
    start_times = pd.to_datetime(swings["swing_start_time"])
    swings["block"] = [assign_block(t) for t in start_times.dt.time]
    swings["period"] = np.where(start_times <= P1A_END, "P1a", "P1b")

    # Keep only RTH swings
    swings = swings[swings["block"] != ""].copy()
    print(f"  RTH swings: {len(swings):,}")

    # Save updated CSV
    csv_path = OUT_DIR / "rth_swings_by_block.csv"
    swings.to_csv(csv_path, index=False)
    print(f"  Saved: {csv_path.name}")

    # ------------------------------------------------------------------
    # 2. Metric 1: Swing Duration per block
    # ------------------------------------------------------------------
    print("\n" + "=" * 100)
    print("METRIC 1: SWING DURATION (seconds)")
    print("-" * 100)
    print(f"{'Block':<12} {'Time':<14} {'Swings':>7} {'Mean':>8} {'Median':>8} "
          f"{'P10':>8} {'P90':>8}")
    print("-" * 100)

    duration_stats = {}
    for bname, _, _ in BLOCKS:
        s = swings.loc[swings["block"] == bname, "swing_duration_sec"]
        stats = {
            "swings": int(len(s)),
            "mean_sec":   round(float(s.mean()), 1),
            "median_sec": round(float(s.median()), 1),
            "p10_sec":    round(float(np.percentile(s, 10)), 1),
            "p90_sec":    round(float(np.percentile(s, 90)), 1),
        }
        duration_stats[bname] = stats
        print(f"{bname:<12} {BLOCK_LABELS[bname]:<14} {stats['swings']:>7,} "
              f"{stats['mean_sec']:>8.1f} {stats['median_sec']:>8.1f} "
              f"{stats['p10_sec']:>8.1f} {stats['p90_sec']:>8.1f}")

    # ------------------------------------------------------------------
    # 3. Metric 2: Swings per clock-hour
    # ------------------------------------------------------------------
    print("\n" + "=" * 100)
    print("METRIC 2: SWINGS PER CLOCK-HOUR")
    print("-" * 100)
    print(f"{'Block':<12} {'Hrs/Sess':>9} {'Sessions':>9} {'Total Hrs':>10} "
          f"{'Swings':>7} {'Swings/Hr':>10}")
    print("-" * 100)

    swings_per_hour = {}
    for bname, _, _ in BLOCKS:
        total_hours = BLOCK_HOURS[bname] * n_sessions
        n_swings = duration_stats[bname]["swings"]
        sph = n_swings / total_hours
        swings_per_hour[bname] = {
            "hrs_per_session": BLOCK_HOURS[bname],
            "total_hours": round(total_hours, 1),
            "swings": n_swings,
            "swings_per_hour": round(sph, 1),
        }
        print(f"{bname:<12} {BLOCK_HOURS[bname]:>9.1f} {n_sessions:>9} "
              f"{total_hours:>10.1f} {n_swings:>7,} {sph:>10.1f}")

    # ------------------------------------------------------------------
    # 4. Metric 3: Price travel per minute (bar-to-bar close changes)
    # ------------------------------------------------------------------
    print("\n" + "=" * 100)
    print("METRIC 3: PRICE TRAVEL PER MINUTE")
    print("-" * 100)
    print(f"{'Block':<12} {'Total Travel':>14} {'Total Min':>10} {'Pts/Min':>10}")
    print("-" * 100)

    # Compute bar-to-bar |close[i] - close[i-1]| within each block
    # Use 'Last' column as close
    bars_sorted = bars.sort_values("datetime").copy()
    bars_sorted["close_change"] = bars_sorted["Last"].diff().abs()
    # Zero out changes at session boundaries (first bar of each date-block combo)
    bars_sorted["date"] = bars_sorted["datetime"].dt.date
    bars_sorted.loc[
        bars_sorted.groupby(["date", "block"]).cumcount() == 0,
        "close_change"
    ] = 0.0

    travel_stats = {}
    for bname, _, _ in BLOCKS:
        block_bars = bars_sorted[bars_sorted["block"] == bname]
        total_travel = block_bars["close_change"].sum()
        total_minutes = BLOCK_HOURS[bname] * 60 * n_sessions
        pts_per_min = total_travel / total_minutes if total_minutes > 0 else 0
        travel_stats[bname] = {
            "total_travel_pts": round(float(total_travel), 1),
            "total_minutes": round(total_minutes, 1),
            "pts_per_minute": round(float(pts_per_min), 2),
        }
        print(f"{bname:<12} {total_travel:>14,.1f} {total_minutes:>10.0f} "
              f"{pts_per_min:>10.2f}")

    # ------------------------------------------------------------------
    # 5. Metric 4: Points available per hour
    # ------------------------------------------------------------------
    print("\n" + "=" * 100)
    print("METRIC 4: POINTS AVAILABLE PER HOUR  (mean_swing × swings/hr)")
    print("-" * 100)

    # Also compute from prior analysis mean swing sizes
    block_mean_swing = {}
    for bname, _, _ in BLOCKS:
        s = swings.loc[swings["block"] == bname, "swing_size_pts"]
        block_mean_swing[bname] = float(s.mean())

    print(f"{'Block':<12} {'Mean Swing':>11} {'Swings/Hr':>10} {'Pts/Hr':>9} {'Rank':>5}")
    print("-" * 100)

    pts_per_hour = {}
    for bname, _, _ in BLOCKS:
        ms = block_mean_swing[bname]
        sph = swings_per_hour[bname]["swings_per_hour"]
        pph = ms * sph
        pts_per_hour[bname] = round(pph, 1)

    # Rank
    ranked = sorted(pts_per_hour.items(), key=lambda x: x[1], reverse=True)
    rank_map = {name: i + 1 for i, (name, _) in enumerate(ranked)}

    points_hour_stats = {}
    for bname, _, _ in BLOCKS:
        ms = block_mean_swing[bname]
        sph = swings_per_hour[bname]["swings_per_hour"]
        pph = pts_per_hour[bname]
        rank = rank_map[bname]
        points_hour_stats[bname] = {
            "mean_swing_pts": round(ms, 2),
            "swings_per_hour": sph,
            "points_per_hour": pph,
            "rank": rank,
        }
        print(f"{bname:<12} {ms:>11.2f} {sph:>10.1f} {pph:>9.1f} {rank:>5}")

    # ------------------------------------------------------------------
    # 6. Regime comparison (P1a vs P1b) for metrics 1-3
    # ------------------------------------------------------------------
    print("\n" + "=" * 100)
    print("REGIME COMPARISON (P1a: Sep 21 – Nov 2  |  P1b: Nov 3 – Dec 14)")
    print("-" * 100)

    # Count sessions per period
    p1a_dates = rth_bars[rth_bars["period"] == "P1a"]["datetime"].dt.date.unique()
    p1b_dates = rth_bars[rth_bars["period"] == "P1b"]["datetime"].dt.date.unique()
    n_p1a = len(p1a_dates)
    n_p1b = len(p1b_dates)
    print(f"  P1a sessions: {n_p1a}  |  P1b sessions: {n_p1b}")

    print(f"\n{'Block':<12} | {'--- P1a ---':^38} | {'--- P1b ---':^38} | {'Delta':^12}")
    print(f"{'':12} | {'Med Dur':>8} {'Sw/Hr':>8} {'Pt/Min':>8} {'Pt/Hr':>9} "
          f"| {'Med Dur':>8} {'Sw/Hr':>8} {'Pt/Min':>8} {'Pt/Hr':>9} "
          f"| {'Pt/Hr':>10}")
    print("-" * 115)

    regime_stats = {}
    for bname, _, _ in BLOCKS:
        regime_stats[bname] = {}
        for period, n_sess in [("P1a", n_p1a), ("P1b", n_p1b)]:
            sw = swings[(swings["block"] == bname) & (swings["period"] == period)]
            blk_bars = bars_sorted[(bars_sorted["block"] == bname) &
                                   (bars_sorted["period"] == period)]

            n_sw = len(sw)
            total_hours = BLOCK_HOURS[bname] * n_sess
            sph = n_sw / total_hours if total_hours > 0 else 0
            med_dur = float(sw["swing_duration_sec"].median()) if n_sw > 0 else 0
            mean_swing = float(sw["swing_size_pts"].mean()) if n_sw > 0 else 0

            total_travel = blk_bars["close_change"].sum()
            total_minutes = BLOCK_HOURS[bname] * 60 * n_sess
            ptm = float(total_travel / total_minutes) if total_minutes > 0 else 0

            pph = mean_swing * sph

            regime_stats[bname][period] = {
                "swings": int(n_sw),
                "sessions": int(n_sess),
                "median_duration_sec": round(med_dur, 1),
                "swings_per_hour": round(sph, 1),
                "pts_per_minute": round(ptm, 2),
                "mean_swing_pts": round(mean_swing, 2),
                "points_per_hour": round(pph, 1),
            }

        p1a_s = regime_stats[bname].get("P1a", {})
        p1b_s = regime_stats[bname].get("P1b", {})
        delta_pph = p1b_s.get("points_per_hour", 0) - p1a_s.get("points_per_hour", 0)

        print(f"{bname:<12} | {p1a_s.get('median_duration_sec',0):>8.1f} "
              f"{p1a_s.get('swings_per_hour',0):>8.1f} "
              f"{p1a_s.get('pts_per_minute',0):>8.2f} "
              f"{p1a_s.get('points_per_hour',0):>9.1f} "
              f"| {p1b_s.get('median_duration_sec',0):>8.1f} "
              f"{p1b_s.get('swings_per_hour',0):>8.1f} "
              f"{p1b_s.get('pts_per_minute',0):>8.2f} "
              f"{p1b_s.get('points_per_hour',0):>9.1f} "
              f"| {delta_pph:>+10.1f}")

    # ------------------------------------------------------------------
    # Save JSON
    # ------------------------------------------------------------------
    output = {
        "sessions": {
            "total": n_sessions,
            "P1a": n_p1a,
            "P1b": n_p1b,
        },
        "swing_duration": duration_stats,
        "swings_per_hour": swings_per_hour,
        "price_travel": travel_stats,
        "points_per_hour": points_hour_stats,
        "regime_comparison": regime_stats,
    }

    json_path = OUT_DIR / "rth_swing_block_clocktime.json"
    with open(json_path, "w") as f:
        json.dump(output, f, indent=2)
    print(f"\n  Saved: {json_path.name}")
    print("Done.")


if __name__ == "__main__":
    main()
