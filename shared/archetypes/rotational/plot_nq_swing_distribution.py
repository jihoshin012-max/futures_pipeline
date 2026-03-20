# archetype: rotational
"""NQ 250T Zig Zag Swing Distribution — matching ES chart style.

Produces two charts:
  1. Percentile bar chart: swing sizes at 100%, 90%, 80%, ... 10%
  2. Histogram: swing count by 5-point buckets

Uses Zig Zag Line Length from NQ 250-tick bar data (P1 + P2, ~6 months).
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker

_REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_REPO))
from shared.data_loader import load_bars

TICK_SIZE = 0.25  # NQ tick size in points


def main():
    # Load data
    print("Loading NQ 250-tick bar data...")
    p1 = load_bars(str(_REPO / "stages/01-data/data/bar_data/tick/NQ_BarData_250tick_rot_P1.csv"))
    p2 = load_bars(str(_REPO / "stages/01-data/data/bar_data/tick/NQ_BarData_250tick_rot_P2.csv"))
    bars = pd.concat([p1, p2], ignore_index=True).sort_values("datetime").reset_index(drop=True)

    date_start = bars["datetime"].iloc[0].strftime("%Y-%m-%d")
    date_end = bars["datetime"].iloc[-1].strftime("%Y-%m-%d")

    # Extract completed swings (non-zero Zig Zag Line Length)
    swings = bars[bars["Zig Zag Line Length"] != 0]["Zig Zag Line Length"].values
    swing_sizes = np.abs(swings)

    total = len(swing_sizes)
    median_pts = np.median(swing_sizes)
    p90_pts = np.percentile(swing_sizes, 90)

    print(f"Total swings: {total:,}")
    print(f"Median: {median_pts:.1f} pts | P90: {p90_pts:.1f} pts")
    print(f"Date range: {date_start} to {date_end}")

    # ===================================================================
    # Figure setup: dark theme
    # ===================================================================
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 10),
                                    gridspec_kw={"hspace": 0.35})
    fig.patch.set_facecolor("#1a1a2e")

    for ax in (ax1, ax2):
        ax.set_facecolor("#1a1a2e")
        ax.tick_params(colors="white", labelsize=9)
        ax.xaxis.label.set_color("white")
        ax.yaxis.label.set_color("white")
        ax.title.set_color("white")
        for spine in ax.spines.values():
            spine.set_color("#444")

    # ===================================================================
    # Chart 1: Percentile bars
    # ===================================================================
    percentiles = [100, 90, 80, 70, 60, 50, 40, 30, 20, 10]
    pct_values = [np.percentile(swing_sizes, p) for p in percentiles]
    pct_ticks = [v / TICK_SIZE for v in pct_values]

    # Color gradient: red (100%) -> olive -> green (10%)
    colors_pct = [
        "#e63946",  # 100% - red
        "#e07050",  # 90%
        "#d08060",  # 80%
        "#b08040",  # 70%
        "#a09040",  # 60%
        "#80a040",  # 50%
        "#60a040",  # 40%
        "#50a050",  # 30%
        "#40b060",  # 20%
        "#30c070",  # 10%
    ]

    x_pos = np.arange(len(percentiles))
    bars_pct = ax1.bar(x_pos, pct_values, color=colors_pct, width=0.7, edgecolor="none")

    # Labels on bars
    for i, (bar, val, ticks) in enumerate(zip(bars_pct, pct_values, pct_ticks)):
        ax1.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.5,
                 f"{val:.1f} pts\n({ticks:.0f} ticks)",
                 ha="center", va="bottom", color="white", fontsize=8, fontweight="bold")

    ax1.set_xticks(x_pos)
    ax1.set_xticklabels([f"{p}%" for p in percentiles])
    ax1.set_ylabel("Swing Size (points)", fontsize=11)
    ax1.set_title(f"NQ 250T Zig Zag Swing Distribution", fontsize=14, fontweight="bold")

    # Subtitle line
    ax1.text(0.5, -0.12,
             f"Total swings: {total:,}  |  Median: {median_pts:.1f} pts  |  P90: {p90_pts:.1f} pts"
             f"  |  {date_start} to {date_end}",
             transform=ax1.transAxes, ha="center", color="#aaa", fontsize=9)

    ax1.set_ylim(0, max(pct_values) * 1.15)

    # ===================================================================
    # Chart 2: Histogram by 5-point buckets
    # ===================================================================
    bin_width = 5
    max_bin = 65  # last bin captures 60+
    bin_edges = np.arange(0, max_bin + bin_width, bin_width)
    # Clip values above max_bin into last bin
    clipped = np.clip(swing_sizes, 0, max_bin - 0.01)
    counts, _ = np.histogram(clipped, bins=bin_edges)

    # Colors: green gradient for small swings, transitioning to olive/red for large
    n_bins = len(counts)
    hist_colors = []
    for i in range(n_bins):
        frac = i / max(n_bins - 1, 1)
        if frac < 0.3:
            hist_colors.append("#4caf50")  # green
        elif frac < 0.5:
            hist_colors.append("#8bc34a")  # light green
        elif frac < 0.7:
            hist_colors.append("#9e9d24")  # olive
        elif frac < 0.85:
            hist_colors.append("#d08060")  # brownish
        else:
            hist_colors.append("#e07050")  # reddish

    x_hist = np.arange(n_bins)
    bars_hist = ax2.bar(x_hist, counts, color=hist_colors, width=0.8, edgecolor="none")

    # Labels on bars
    for i, (bar, cnt) in enumerate(zip(bars_hist, counts)):
        if cnt > 0:
            pct = cnt / total * 100
            label = f"{cnt:,}\n({pct:.1f}%)" if cnt >= 100 else f"{cnt}\n({pct:.1f}%)"
            ax2.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 20,
                     label, ha="center", va="bottom", color="white",
                     fontsize=7 if cnt >= 100 else 6)

    # X-axis labels
    bin_labels = []
    for i in range(n_bins):
        lo = int(bin_edges[i])
        hi = int(bin_edges[i + 1])
        if i == n_bins - 1:
            bin_labels.append(f"{lo}+")
        else:
            bin_labels.append(f"{lo}-{hi}")
    ax2.set_xticks(x_hist)
    ax2.set_xticklabels(bin_labels, rotation=45, ha="right", fontsize=8)
    ax2.set_xlabel("Swing Size (points)", fontsize=11)
    ax2.set_ylabel("Count", fontsize=11)
    ax2.set_title("NQ 250T Swing Size Histogram", fontsize=14, fontweight="bold")
    ax2.set_ylim(0, max(counts) * 1.2)

    # Save
    out_path = Path(__file__).parent / "nq_250t_swing_distribution.png"
    fig.savefig(out_path, dpi=150, bbox_inches="tight", facecolor=fig.get_facecolor())
    print(f"\nSaved: {out_path}")
    plt.close()


if __name__ == "__main__":
    main()
