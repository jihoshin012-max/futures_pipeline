# archetype: rotational
"""NQ 250T Zig Zag Swing Histogram — 1-point bins, RTH / ETH / Total views."""

import datetime as dt
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

_REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_REPO))
from shared.data_loader import load_bars

# NQ session boundaries (ET) — from _config/instruments.md
RTH_START = dt.time(9, 30)
RTH_END = dt.time(16, 15)


def _color_gradient(n_bins):
    """Green -> olive -> brownish/red gradient."""
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


def _plot_histogram(swing_sizes, title, subtitle_extra, out_path):
    """Render and save a single swing-size histogram."""
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

    ax.text(0.5, -0.14,
            f"Swings: {total:,}  |  Mean: {mean_pts:.1f} pts  |  Median: {median_pts:.1f} pts"
            f"  |  P90: {p90_pts:.1f} pts  |  {subtitle_extra}",
            transform=ax.transAxes, ha="center", color="#aaa", fontsize=10)

    ax.set_ylim(0, max(counts) * 1.15)

    fig.savefig(out_path, dpi=150, bbox_inches="tight", facecolor=fig.get_facecolor())
    print(f"Saved: {out_path}")
    plt.close()


def main():
    print("Loading NQ 250-tick bar data...")
    p1 = load_bars(str(_REPO / "stages/01-data/data/bar_data/tick/NQ_BarData_250tick_rot_P1.csv"))
    p2 = load_bars(str(_REPO / "stages/01-data/data/bar_data/tick/NQ_BarData_250tick_rot_P2.csv"))
    bars = pd.concat([p1, p2], ignore_index=True).sort_values("datetime").reset_index(drop=True)

    date_range = (bars["datetime"].iloc[0].strftime("%Y-%m-%d")
                  + " to " + bars["datetime"].iloc[-1].strftime("%Y-%m-%d"))

    # Classify session
    time_of_day = bars["datetime"].dt.time
    bars["session"] = "ETH"
    bars.loc[(time_of_day >= RTH_START) & (time_of_day < RTH_END), "session"] = "RTH"

    # Extract swings with session tag
    swing_mask = bars["Zig Zag Line Length"] != 0
    swings = bars.loc[swing_mask].copy()
    swings["swing_size"] = np.abs(swings["Zig Zag Line Length"])

    out_dir = Path(__file__).parent

    configs = [
        ("Total", swings["swing_size"].values,
         "NQ 250T Swing Size Histogram (Total)",
         out_dir / "nq_250t_swing_histogram.png"),
        ("RTH", swings.loc[swings["session"] == "RTH", "swing_size"].values,
         "NQ 250T Swing Size Histogram (RTH 09:30-16:15 ET)",
         out_dir / "nq_250t_swing_histogram_rth.png"),
        ("ETH", swings.loc[swings["session"] == "ETH", "swing_size"].values,
         "NQ 250T Swing Size Histogram (ETH 18:00-09:30 ET)",
         out_dir / "nq_250t_swing_histogram_eth.png"),
    ]

    for label, sizes, title, path in configs:
        print(f"\n--- {label} ({len(sizes):,} swings) ---")
        _plot_histogram(sizes, title, date_range, path)


if __name__ == "__main__":
    main()
