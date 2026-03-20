# archetype: rotational
"""RTH Zigzag Swing Distribution — Intraday Time Blocks.

Analyses P1-only NQ 250T data, assigns each swing to the block where its
starting reversal occurred, and produces:
  - rth_swings_by_block.csv          (swing-level dataset)
  - rth_swing_block_summary.json     (summary table)
  - nq_250t_swing_histogram_*.png    (per-block + overlay histograms)
"""

import datetime as dt
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

_REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_REPO))
from shared.data_loader import load_bars

OUT_DIR = Path(__file__).parent

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
P1_END = pd.Timestamp("2025-12-14 23:59:59")
P1A_END = pd.Timestamp("2025-11-02 23:59:59")  # P1a: Sep 21 – Nov 2
# P1b: Nov 3 – Dec 14

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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def assign_block(t: dt.time) -> str:
    """Return block name for a time-of-day, or '' if outside RTH blocks."""
    for name, start, end in BLOCKS:
        if start <= t < end:
            return name
    return ""


def _color_gradient(n_bins):
    colors = []
    for i in range(n_bins):
        frac = i / max(n_bins - 1, 1)
        if frac < 0.25:
            colors.append("#4caf50")
        elif frac < 0.45:
            colors.append("#7cb342")
        elif frac < 0.60:
            colors.append("#9e9d24")
        elif frac < 0.75:
            colors.append("#b08040")
        elif frac < 0.88:
            colors.append("#d08060")
        else:
            colors.append("#e07050")
    return colors


def plot_block_histogram(swing_sizes, title, subtitle, out_path):
    """Single histogram in the established dark-theme style."""
    total = len(swing_sizes)
    if total == 0:
        print(f"  Skipped {out_path.name} — no swings")
        return
    median_pts = np.median(swing_sizes)
    mean_pts = np.mean(swing_sizes)
    p90_pts = np.percentile(swing_sizes, 90)

    max_bin = 40
    bin_edges = np.arange(0, max_bin + 1, 1)
    clipped = np.clip(swing_sizes, 0, max_bin - 0.01)
    counts, _ = np.histogram(clipped, bins=bin_edges)
    overflow = (swing_sizes >= max_bin).sum()
    counts = np.append(counts, overflow)
    n_bins = len(counts)
    hist_colors = _color_gradient(n_bins)

    fig, ax = plt.subplots(figsize=(18, 7))
    fig.patch.set_facecolor("#1a1a2e")
    ax.set_facecolor("#1a1a2e")
    ax.tick_params(colors="white", labelsize=8)
    ax.xaxis.label.set_color("white")
    ax.yaxis.label.set_color("white")
    ax.title.set_color("white")
    for spine in ax.spines.values():
        spine.set_color("#444")

    x_pos = np.arange(n_bins)
    bar_objs = ax.bar(x_pos, counts, color=hist_colors, width=0.85, edgecolor="none")

    for bar, cnt in zip(bar_objs, counts):
        if cnt > 0:
            pct = cnt / total * 100
            fs = 7 if cnt >= 500 else 6 if cnt >= 50 else 5.5
            label = f"{cnt:,}\n({pct:.1f}%)"
            ax.text(bar.get_x() + bar.get_width() / 2,
                    bar.get_height() + max(counts) * 0.008,
                    label, ha="center", va="bottom", color="white", fontsize=fs)

    bin_labels = [f"{int(bin_edges[i])}-{int(bin_edges[i+1])}"
                  for i in range(len(bin_edges) - 1)]
    bin_labels.append(f"{max_bin}+")
    ax.set_xticks(x_pos)
    ax.set_xticklabels(bin_labels, rotation=45, ha="right", fontsize=7)
    ax.set_xlabel("Swing Size (points)", fontsize=12)
    ax.set_ylabel("Count", fontsize=12)
    ax.set_title(title, fontsize=15, fontweight="bold", color="white")

    ax.text(0.5, -0.14, subtitle,
            transform=ax.transAxes, ha="center", color="#aaa", fontsize=10)
    ax.set_ylim(0, max(counts) * 1.15)

    fig.savefig(out_path, dpi=150, bbox_inches="tight", facecolor=fig.get_facecolor())
    print(f"  Saved: {out_path.name}")
    plt.close()


def plot_overlay(swings_df, out_path):
    """Percentage-normalized overlay of all 5 blocks on one chart."""
    max_bin = 40
    bin_edges = np.arange(0, max_bin + 1, 1)
    n_bins = len(bin_edges)  # 41 edges -> 40 bins + 1 overflow = 41 bars

    block_colors = {
        "Open":      "#ff6b6b",
        "Morning":   "#ffd93d",
        "Midday":    "#6bcb77",
        "Afternoon": "#4d96ff",
        "Close":     "#c084fc",
    }

    fig, ax = plt.subplots(figsize=(20, 8))
    fig.patch.set_facecolor("#1a1a2e")
    ax.set_facecolor("#1a1a2e")
    ax.tick_params(colors="white", labelsize=8)
    ax.xaxis.label.set_color("white")
    ax.yaxis.label.set_color("white")
    ax.title.set_color("white")
    for spine in ax.spines.values():
        spine.set_color("#444")

    bar_width = 0.16
    x_pos = np.arange(len(bin_edges))  # 0..40 (40 bins + overflow)

    for idx, (block_name, _, _) in enumerate(BLOCKS):
        sizes = swings_df.loc[swings_df["block"] == block_name, "swing_size_pts"].values
        if len(sizes) == 0:
            continue
        clipped = np.clip(sizes, 0, max_bin - 0.01)
        counts, _ = np.histogram(clipped, bins=bin_edges)
        overflow = (sizes >= max_bin).sum()
        counts = np.append(counts, overflow)
        pcts = counts / len(sizes) * 100

        offset = (idx - 2) * bar_width
        ax.bar(x_pos + offset, pcts, width=bar_width,
               color=block_colors[block_name], alpha=0.85,
               label=f"{block_name} ({BLOCK_LABELS[block_name]}, n={len(sizes):,})",
               edgecolor="none")

    bin_labels = [f"{int(bin_edges[i])}-{int(bin_edges[i+1])}"
                  for i in range(len(bin_edges) - 1)]
    bin_labels.append(f"{max_bin}+")
    ax.set_xticks(x_pos)
    ax.set_xticklabels(bin_labels, rotation=45, ha="right", fontsize=7)
    ax.set_xlabel("Swing Size (points)", fontsize=12)
    ax.set_ylabel("% of Block's Swings", fontsize=12)
    ax.set_title("NQ 250T Swing Distribution by RTH Block (P1, % Normalized)",
                 fontsize=15, fontweight="bold", color="white")
    ax.legend(loc="upper right", fontsize=10, facecolor="#2a2a4e",
              edgecolor="#444", labelcolor="white")

    fig.savefig(out_path, dpi=150, bbox_inches="tight", facecolor=fig.get_facecolor())
    print(f"  Saved: {out_path.name}")
    plt.close()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    print("Loading NQ 250-tick P1 data...")
    bars = load_bars(str(_REPO / "stages/01-data/data/bar_data/tick/NQ_BarData_250tick_rot_P1.csv"))

    # Filter to P1 date range
    bars = bars[bars["datetime"] <= P1_END].copy()
    print(f"  Bars: {len(bars):,}  ({bars['datetime'].iloc[0]} to {bars['datetime'].iloc[-1]})")

    # -----------------------------------------------------------------------
    # Build swing table: each swing goes from reversal[i-1] to reversal[i]
    # Assign to the block where the START reversal (i-1) occurred
    # -----------------------------------------------------------------------
    rev_mask = bars["Zig Zag Line Length"] != 0
    reversals = bars[rev_mask][["datetime", "Reversal Price", "Zig Zag Line Length"]].copy()
    reversals = reversals.reset_index(drop=True)

    swings = pd.DataFrame({
        "swing_start_time": reversals["datetime"].iloc[:-1].values,
        "swing_end_time":   reversals["datetime"].iloc[1:].values,
        "swing_size_pts":   np.abs(reversals["Zig Zag Line Length"].iloc[1:].values),
    })

    # Assign block based on start time
    start_times = pd.to_datetime(swings["swing_start_time"]).dt.time
    swings["block"] = [assign_block(t) for t in start_times]

    # Keep only RTH-block swings
    swings = swings[swings["block"] != ""].copy()

    # Assign period
    swings["period"] = np.where(
        pd.to_datetime(swings["swing_start_time"]) <= P1A_END, "P1a", "P1b"
    )

    print(f"  RTH swings (block-assigned): {len(swings):,}")

    # -----------------------------------------------------------------------
    # Save swing-level CSV
    # -----------------------------------------------------------------------
    csv_path = OUT_DIR / "rth_swings_by_block.csv"
    swings.to_csv(csv_path, index=False)
    print(f"  Saved: {csv_path.name}")

    # -----------------------------------------------------------------------
    # Summary table
    # -----------------------------------------------------------------------
    def block_stats(s):
        if len(s) == 0:
            return {}
        return {
            "swings": int(len(s)),
            "mean":   round(float(np.mean(s)), 2),
            "median": round(float(np.median(s)), 2),
            "p75":    round(float(np.percentile(s, 75)), 2),
            "p80":    round(float(np.percentile(s, 80)), 2),
            "p85":    round(float(np.percentile(s, 85)), 2),
            "p90":    round(float(np.percentile(s, 90)), 2),
            "p95":    round(float(np.percentile(s, 95)), 2),
            "max":    round(float(np.max(s)), 2),
            "pct_ge_15": round(float((s >= 15).mean() * 100), 1),
            "pct_ge_20": round(float((s >= 20).mean() * 100), 1),
            "pct_ge_25": round(float((s >= 25).mean() * 100), 1),
            "p85_value": round(float(np.percentile(s, 85)), 2),
        }

    summary = {}
    block_order = [b[0] for b in BLOCKS] + ["RTH Total"]

    for bname in [b[0] for b in BLOCKS]:
        s = swings.loc[swings["block"] == bname, "swing_size_pts"].values
        summary[bname] = {
            "time": BLOCK_LABELS[bname],
            **block_stats(s),
        }

    # RTH Total
    all_rth = swings["swing_size_pts"].values
    summary["RTH Total"] = {
        "time": "09:30-16:00",
        **block_stats(all_rth),
    }

    # Regime comparison
    regime = {}
    for bname in [b[0] for b in BLOCKS]:
        regime[bname] = {}
        for period in ["P1a", "P1b"]:
            s = swings.loc[(swings["block"] == bname) & (swings["period"] == period),
                           "swing_size_pts"].values
            if len(s) > 0:
                regime[bname][period] = {
                    "swings": int(len(s)),
                    "median": round(float(np.median(s)), 2),
                    "p90":    round(float(np.percentile(s, 90)), 2),
                    "mean":   round(float(np.mean(s)), 2),
                }

    output = {"blocks": summary, "regime_comparison": regime}
    json_path = OUT_DIR / "rth_swing_block_summary.json"
    with open(json_path, "w") as f:
        json.dump(output, f, indent=2)
    print(f"  Saved: {json_path.name}")

    # -----------------------------------------------------------------------
    # Print summary table
    # -----------------------------------------------------------------------
    print("\n" + "=" * 120)
    print(f"{'Block':<12} {'Time':<14} {'Swings':>7} {'Mean':>7} {'Median':>7} "
          f"{'P75':>7} {'P80':>7} {'P85':>7} {'P90':>7} {'P95':>7} {'Max':>7} "
          f"{'>=15':>6} {'>=20':>6} {'>=25':>6}")
    print("-" * 120)
    for bname in block_order:
        s = summary[bname]
        print(f"{bname:<12} {s['time']:<14} {s['swings']:>7,} {s['mean']:>7.1f} {s['median']:>7.1f} "
              f"{s['p75']:>7.1f} {s['p80']:>7.1f} {s['p85']:>7.1f} {s['p90']:>7.1f} {s['p95']:>7.1f} {s['max']:>7.1f} "
              f"{s['pct_ge_15']:>5.1f}% {s['pct_ge_20']:>5.1f}% {s['pct_ge_25']:>5.1f}%")

    # Regime comparison table
    print("\n" + "=" * 90)
    print("REGIME COMPARISON (P1a: Sep 21 – Nov 2  |  P1b: Nov 3 – Dec 14)")
    print("-" * 90)
    print(f"{'Block':<12} {'P1a Swings':>10} {'P1a Med':>8} {'P1a P90':>8}  |  "
          f"{'P1b Swings':>10} {'P1b Med':>8} {'P1b P90':>8}  {'Delta Med':>10} {'Delta P90':>10}")
    print("-" * 90)
    for bname in [b[0] for b in BLOCKS]:
        r = regime[bname]
        p1a = r.get("P1a", {})
        p1b = r.get("P1b", {})
        d_med = p1b.get("median", 0) - p1a.get("median", 0) if p1a and p1b else float("nan")
        d_p90 = p1b.get("p90", 0) - p1a.get("p90", 0) if p1a and p1b else float("nan")
        print(f"{bname:<12} "
              f"{p1a.get('swings', 0):>10,} {p1a.get('median', 0):>8.1f} {p1a.get('p90', 0):>8.1f}  |  "
              f"{p1b.get('swings', 0):>10,} {p1b.get('median', 0):>8.1f} {p1b.get('p90', 0):>8.1f}  "
              f"{d_med:>+10.1f} {d_p90:>+10.1f}")

    # -----------------------------------------------------------------------
    # Histograms — one per block
    # -----------------------------------------------------------------------
    print("\nGenerating per-block histograms...")
    date_range = f"P1: {bars['datetime'].iloc[0].strftime('%Y-%m-%d')} to {bars['datetime'].iloc[-1].strftime('%Y-%m-%d')}"

    for bname in [b[0] for b in BLOCKS]:
        sizes = swings.loc[swings["block"] == bname, "swing_size_pts"].values
        s = summary[bname]
        subtitle = (f"Swings: {s['swings']:,}  |  Mean: {s['mean']:.1f} pts  |  "
                    f"Median: {s['median']:.1f} pts  |  P90: {s['p90']:.1f} pts  |  {date_range}")
        fname = f"nq_250t_swing_histogram_rth_{bname.lower()}.png"
        plot_block_histogram(
            sizes,
            f"NQ 250T Swing Size — {bname} ({BLOCK_LABELS[bname]} ET)",
            subtitle,
            OUT_DIR / fname,
        )

    # RTH total (update existing)
    subtitle = (f"Swings: {summary['RTH Total']['swings']:,}  |  "
                f"Mean: {summary['RTH Total']['mean']:.1f} pts  |  "
                f"Median: {summary['RTH Total']['median']:.1f} pts  |  "
                f"P90: {summary['RTH Total']['p90']:.1f} pts  |  {date_range}")
    plot_block_histogram(
        all_rth,
        "NQ 250T Swing Size Histogram (RTH Total, P1)",
        subtitle,
        OUT_DIR / "nq_250t_swing_histogram_rth_total.png",
    )

    # Overlay
    print("\nGenerating overlay chart...")
    plot_overlay(swings, OUT_DIR / "nq_250t_swing_histogram_rth_overlay.png")

    print("\nDone.")


if __name__ == "__main__":
    main()
