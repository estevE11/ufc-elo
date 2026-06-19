#!/usr/bin/env python3
"""Generate an MP4 bar-chart-race animation of Elo evolution from 2020 onward."""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib.animation as animation
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.animation import FFMpegWriter

DEFAULT_OUTPUT = Path("output/elo_evolution_2020.mp4")
TOP_N = 10
FRAMES_PER_MONTH = 8
FPS = 24
START_DATE = "2020-01-01"


def load_p4p_series(snapshots_path: Path, start_date: str) -> pd.DataFrame:
    snapshots = pd.read_csv(snapshots_path, parse_dates=["date"])
    snapshots["elo_score"] = pd.to_numeric(snapshots["elo_score"], errors="coerce")
    snapshots = snapshots.dropna(subset=["elo_score", "fighter_name"])

    p4p = snapshots[
        (snapshots["weight_class"] == "p4p") & (snapshots["date"] >= start_date)
    ].copy()
    if p4p.empty:
        raise ValueError(f"No P4P snapshots found from {start_date}.")

    return (
        p4p.sort_values("date")
        .groupby(["date", "fighter_name"], as_index=False)["elo_score"]
        .last()
    )


def build_interpolated_frames(
    monthly: pd.DataFrame,
    top_n: int,
    frames_per_month: int,
) -> list[dict]:
    """Interpolate between months for smooth bar movement."""
    dates = sorted(monthly["date"].unique())
    candidate_names: set[str] = set()

    monthly_lookup: dict[pd.Timestamp, dict[str, float]] = {}
    for date in dates:
        month_slice = monthly[monthly["date"] == date]
        monthly_lookup[date] = dict(zip(month_slice["fighter_name"], month_slice["elo_score"]))
        candidate_names.update(monthly_lookup[date].keys())

    frames: list[dict] = []

    def frame_from_lookup(current_date: pd.Timestamp, lookup: dict[str, float]) -> dict:
        ranked = sorted(lookup.items(), key=lambda item: item[1], reverse=True)[:top_n]
        names = [name for name, _ in ranked]
        elos = [score for _, score in ranked]
        return {"date": current_date, "names": names, "elos": elos}

    for index, date in enumerate(dates):
        current_lookup = {name: monthly_lookup[date].get(name, np.nan) for name in candidate_names}
        for name, score in monthly_lookup[date].items():
            current_lookup[name] = score
        current_lookup = {k: v for k, v in current_lookup.items() if not np.isnan(v)}

        if index == 0:
            for step in range(frames_per_month):
                frames.append(frame_from_lookup(date, current_lookup))
            continue

        previous_date = dates[index - 1]
        previous_lookup = {
            name: monthly_lookup[previous_date].get(name, current_lookup.get(name, np.nan))
            for name in candidate_names
        }
        previous_lookup = {k: v for k, v in previous_lookup.items() if not np.isnan(v)}

        all_names = set(previous_lookup) | set(current_lookup)
        for step in range(frames_per_month):
            alpha = step / frames_per_month
            blended = {}
            for name in all_names:
                prev = previous_lookup.get(name)
                curr = current_lookup.get(name)
                if prev is not None and curr is not None:
                    blended[name] = prev + (curr - prev) * alpha
                elif curr is not None:
                    blended[name] = curr
                elif prev is not None:
                    blended[name] = prev
            frames.append(frame_from_lookup(date, blended))

    return frames


def create_animation(
    frames: list[dict],
    output_path: Path,
    fps: int,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)

    all_elos = [elo for frame in frames for elo in frame["elos"]]
    x_min = max(900, min(all_elos) - 40)
    x_max = max(all_elos) + 30

    plt.style.use("dark_background")
    fig, ax = plt.subplots(figsize=(12, 7))
    fig.patch.set_facecolor("#0d0d0d")
    ax.set_facecolor("#111111")

    cmap = plt.colormaps["turbo"]
    bar_container: dict[str, object] = {"bars": None, "texts": []}

    def draw_frame(frame_index: int) -> list:
        frame = frames[frame_index]
        names = frame["names"]
        elos = frame["elos"]
        colors = [cmap(0.15 + 0.75 * (i / max(len(names) - 1, 1))) for i in range(len(names))]

        ax.clear()
        ax.set_facecolor("#111111")
        y_pos = np.arange(len(names))

        bars = ax.barh(y_pos, elos, color=colors, height=0.72, edgecolor="#222222")
        ax.set_yticks(y_pos)
        ax.set_yticklabels(names, fontsize=11)
        ax.invert_yaxis()
        ax.set_xlim(x_min, x_max)
        ax.set_xlabel("P4P Elo Rating", fontsize=12)
        ax.grid(axis="x", color="#333333", linestyle="--", alpha=0.6)
        ax.set_title(
            f"UFC Pound-for-Pound Elo — {frame['date'].strftime('%B %Y')}",
            fontsize=16,
            fontweight="bold",
            pad=16,
        )

        for bar, elo in zip(bars, elos):
            ax.text(
                bar.get_width() + 2,
                bar.get_y() + bar.get_height() / 2,
                f"{elo:.0f}",
                va="center",
                ha="left",
                fontsize=10,
                color="#f0f0f0",
            )

        year = frame["date"].year
        ax.text(
            0.99,
            0.02,
            str(year),
            transform=ax.transAxes,
            ha="right",
            va="bottom",
            fontsize=42,
            fontweight="bold",
            color="#ffffff",
            alpha=0.12,
        )
        return list(bars)

    anim = animation.FuncAnimation(
        fig,
        draw_frame,
        frames=len(frames),
        interval=1000 / fps,
        blit=False,
    )

    writer = FFMpegWriter(fps=fps, metadata={"artist": "ufc-elo"}, bitrate=4000)
    anim.save(output_path, writer=writer, dpi=150)
    plt.close(fig)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Animate P4P Elo evolution as MP4.")
    parser.add_argument(
        "--snapshots",
        type=Path,
        default=Path("data/historical_elo_snapshots.csv"),
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--start-date", default=START_DATE)
    parser.add_argument("--top-n", type=int, default=TOP_N)
    parser.add_argument("--fps", type=int, default=FPS)
    parser.add_argument("--frames-per-month", type=int, default=FRAMES_PER_MONTH)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    monthly = load_p4p_series(args.snapshots, args.start_date)
    frames = build_interpolated_frames(monthly, top_n=args.top_n, frames_per_month=args.frames_per_month)
    create_animation(frames, args.output, fps=args.fps)
    print(f"Saved animation to {args.output} ({len(frames)} frames @ {args.fps} fps).")


if __name__ == "__main__":
    main()
