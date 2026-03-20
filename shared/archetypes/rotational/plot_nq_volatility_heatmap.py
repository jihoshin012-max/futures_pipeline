# archetype: rotational
"""NQ 250T Volatility Heatmap — Avg Hourly Range by Hour x Day of Week."""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors

_REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_REPO))
from shared.data_loader import load_bars


def main():
    print("Loading NQ 250-tick bar data (P1 + P2)...")
    p1 = load_bars(str(_REPO / "stages/01-data/data/bar_data/tick/NQ_BarData_250tick_rot_P1.csv"))
    p2 = load_bars(str(_REPO / "stages/01-data/data/bar_data/tick/NQ_BarData_250tick_rot_P2.csv"))
    bars = pd.concat([p1, p2], ignore_index=True).sort_values("datetime").reset_index(drop=True)

    date_start = bars["datetime"].iloc[0].strftime("%Y-%m-%d")
    date_end = bars["datetime"].iloc[-1].strftime("%Y-%m-%d")

    bars["hour"] = bars["datetime"].dt.hour
    bars["date"] = bars["datetime"].dt.date
    bars["dow"] = bars["datetime"].dt.day_name()

    # Per-bar range, then average by hour × day-of-week
    bars["bar_range"] = bars["High"] - bars["Low"]

    # Average bar range by day-of-week × hour
    pivot = bars.groupby(["dow", "hour"])["bar_range"].mean().reset_index()
    pivot.rename(columns={"bar_range": "range"}, inplace=True)
    pivot["range"] = pivot["range"].round(1)

    dow_order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Sunday"]
    all_hours = list(range(24))

    matrix = pd.pivot_table(pivot, values="range", index="hour", columns="dow")
    matrix = matrix.reindex(index=all_hours, columns=dow_order)

    # Count occurrences for annotation (skip cells with <2 samples)
    counts = bars.groupby(["dow", "hour"])["bar_range"].count().reset_index()
    counts.rename(columns={"bar_range": "range"}, inplace=True)
    count_pivot = pd.pivot_table(counts, values="range", index="hour", columns="dow")
    count_pivot = count_pivot.reindex(index=all_hours, columns=dow_order)

    # Mask cells with insufficient data
    mask = count_pivot.fillna(0) < 2

    # --- Plot ---
    fig, ax = plt.subplots(figsize=(14, 16))
    fig.patch.set_facecolor("#1a1a2e")
    ax.set_facecolor("#1a1a2e")

    # Colormap: yellow → orange → red → dark red (matching reference)
    colors_list = ["#fffde7", "#fff9c4", "#fff176", "#ffee58",
                   "#ffca28", "#ffa726", "#ff8f00", "#f57c00",
                   "#e65100", "#d84315", "#bf360c", "#8b0000"]
    cmap = mcolors.LinearSegmentedColormap.from_list("vol_heat", colors_list, N=256)

    data = matrix.values.copy()
    vmin = np.nanmin(data[~np.isnan(data)]) if not np.all(np.isnan(data)) else 5
    vmax = np.nanmax(data[~np.isnan(data)]) if not np.all(np.isnan(data)) else 30

    im = ax.imshow(data, cmap=cmap, aspect="auto", vmin=vmin, vmax=vmax)

    # Annotate cells
    for i in range(data.shape[0]):
        for j in range(data.shape[1]):
            if mask.iloc[i, j] or np.isnan(data[i, j]):
                continue
            val = data[i, j]
            # Dark text on light cells, white on dark
            brightness = (val - vmin) / (vmax - vmin) if vmax > vmin else 0.5
            color = "black" if brightness < 0.6 else "white"
            ax.text(j, i, f"{val:.1f}", ha="center", va="center",
                    fontsize=9, fontweight="bold", color=color)

    ax.set_xticks(range(len(dow_order)))
    ax.set_xticklabels(dow_order, fontsize=12, color="white")
    ax.set_yticks(range(24))
    ax.set_yticklabels([str(h) for h in all_hours], fontsize=10, color="white")
    ax.set_ylabel("Hour (ET)", fontsize=13, color="white")
    ax.set_xlabel("Day of Week", fontsize=13, color="white")
    ax.set_title("NQ 250T Volatility Heatmap: Avg Bar Range by Hour x Day",
                 fontsize=16, fontweight="bold", color="white", pad=15)

    # Subtitle
    ax.text(0.5, -0.05,
            f"Avg per-bar range (High - Low) of 250-tick bars  |  {date_start} to {date_end}",
            transform=ax.transAxes, ha="center", color="#aaa", fontsize=10)

    ax.tick_params(colors="white")
    for spine in ax.spines.values():
        spine.set_color("#444")

    # Colorbar
    cbar = fig.colorbar(im, ax=ax, shrink=0.6, pad=0.02)
    cbar.set_label("Avg Range (pts)", color="white", fontsize=11)
    cbar.ax.tick_params(colors="white")

    # Grid lines
    ax.set_xticks([x - 0.5 for x in range(1, len(dow_order))], minor=True)
    ax.set_yticks([y - 0.5 for y in range(1, 24)], minor=True)
    ax.grid(which="minor", color="#333", linewidth=0.5)
    ax.tick_params(which="minor", length=0)

    out_path = Path(__file__).parent / "nq_250t_volatility_heatmap.png"
    fig.savefig(out_path, dpi=150, bbox_inches="tight", facecolor=fig.get_facecolor())
    print(f"Saved: {out_path}")
    plt.close()


if __name__ == "__main__":
    main()
