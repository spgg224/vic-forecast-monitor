from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

HORIZON_EDGES = [0, 10, 20, 30, 40, 50, 61]
HORIZON_LABELS = ["0-10", "10-20", "20-30", "30-40", "40-50", "50-60"]


def add_analysis_fields(panel: pd.DataFrame) -> pd.DataFrame:
    frame = panel.copy()
    frame["absolute_error"] = frame["forecast_error"].abs()
    frame["squared_error"] = frame["forecast_error"] ** 2
    frame["horizon_bucket"] = pd.cut(
        frame["horizon_minutes"], HORIZON_EDGES, labels=HORIZON_LABELS, right=False
    )
    frame["target_hour"] = frame["target_time"].dt.hour
    return frame


def metric_row(frame: pd.DataFrame) -> dict[str, float | int]:
    error = frame["forecast_error"]
    absolute = error.abs()
    return {
        "observations": int(len(frame)),
        "mae": float(absolute.mean()),
        "rmse": float(np.sqrt(np.mean(error**2))),
        "median_absolute_error": float(absolute.median()),
        "bias": float(error.mean()),
        "p90_absolute_error": float(absolute.quantile(0.90)),
        "p95_absolute_error": float(absolute.quantile(0.95)),
    }


def scorecard(panel: pd.DataFrame) -> dict[str, object]:
    frame = add_analysis_fields(panel)
    by_horizon = []
    for bucket, group in frame.groupby("horizon_bucket", observed=True):
        by_horizon.append({"horizon_minutes": str(bucket), **metric_row(group)})
    return {
        "coverage": {
            "start": frame["target_time"].min().isoformat(),
            "end": frame["target_time"].max().isoformat(),
            "forecast_vintages": int(len(frame)),
            "target_intervals": int(frame["target_time"].nunique()),
        },
        "overall": metric_row(frame),
        "by_horizon": by_horizon,
    }


def error_heatmap(panel: pd.DataFrame) -> pd.DataFrame:
    frame = add_analysis_fields(panel)
    return (
        frame.groupby(["horizon_bucket", "target_hour"], observed=True)["absolute_error"]
        .mean()
        .unstack("target_hour")
        .reindex(HORIZON_LABELS)
    )


def select_vintage(panel: pd.DataFrame, lead_minutes: float = 30) -> pd.DataFrame:
    """Choose one forecast per target, nearest to a declared lead time."""
    frame = panel.copy()
    frame["lead_distance"] = (frame["horizon_minutes"] - lead_minutes).abs()
    return (
        frame.sort_values(["target_time", "lead_distance", "issue_time"])
        .drop_duplicates(["target_time", "region"], keep="first")
        .drop(columns="lead_distance")
        .reset_index(drop=True)
    )


def largest_misses(panel: pd.DataFrame, lead_minutes: float = 30, count: int = 20) -> list[dict[str, object]]:
    frame = select_vintage(panel, lead_minutes)
    frame["absolute_error"] = frame["forecast_error"].abs()
    columns = [
        "issue_time",
        "target_time",
        "horizon_minutes",
        "forecast_price",
        "actual_price",
        "forecast_error",
        "absolute_error",
        "source_file",
        "source_file_actual",
    ]
    selected = frame.nlargest(count, "absolute_error")[columns].copy()
    for column in ("issue_time", "target_time"):
        selected[column] = selected[column].map(pd.Timestamp.isoformat)
    return selected.to_dict(orient="records")


def export_analysis(panel: pd.DataFrame, root: Path) -> None:
    output = root / "output"
    dashboard = output / "dashboard_data"
    figures = output / "figures"
    dashboard.mkdir(parents=True, exist_ok=True)
    figures.mkdir(parents=True, exist_ok=True)

    scores = scorecard(panel)
    (dashboard / "scorecard.json").write_text(json.dumps(scores, indent=2) + "\n", encoding="utf-8")
    misses = {"lead_minutes": 30, "events": largest_misses(panel)}
    (dashboard / "events.json").write_text(json.dumps(misses, indent=2) + "\n", encoding="utf-8")

    heatmap = error_heatmap(panel)
    heatmap.reset_index().to_json(dashboard / "error_heatmap.json", orient="records", indent=2)
    _plot_horizon(scores, figures / "mae_by_horizon.png")
    _plot_heatmap(heatmap, figures / "error_heatmap.png")


def _plot_horizon(scores: dict[str, object], destination: Path) -> None:
    rows = scores["by_horizon"]
    labels = [row["horizon_minutes"] for row in rows]
    values = [row["mae"] for row in rows]
    fig, ax = plt.subplots(figsize=(8.5, 4.8))
    ax.bar(labels, values, color="#277da1")
    ax.set(title="VIC1 P5MIN price error increases with forecast horizon", xlabel="Forecast horizon (minutes)", ylabel="Mean absolute error ($/MWh)")
    ax.grid(axis="y", alpha=0.2)
    ax.set_axisbelow(True)
    fig.tight_layout()
    fig.savefig(destination, dpi=180)
    plt.close(fig)


def _plot_heatmap(heatmap: pd.DataFrame, destination: Path) -> None:
    fig, ax = plt.subplots(figsize=(11, 4.8))
    image = ax.imshow(heatmap.to_numpy(dtype=float), aspect="auto", cmap="YlOrRd")
    ax.set(title="Mean absolute price error by target hour and forecast horizon", xlabel="Target hour (NEM time)", ylabel="Forecast horizon (minutes)")
    ax.set_xticks(range(24), range(24))
    ax.set_yticks(range(len(heatmap.index)), heatmap.index)
    fig.colorbar(image, ax=ax, label="MAE ($/MWh)")
    fig.tight_layout()
    fig.savefig(destination, dpi=180)
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    panel = pd.read_parquet(args.root / "data" / "processed" / "forecast_actual_panel.parquet")
    export_analysis(panel, args.root)
    scores = scorecard(panel)
    print(json.dumps(scores, indent=2))


if __name__ == "__main__":
    main()

