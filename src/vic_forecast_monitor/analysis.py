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


def enrich_events(panel: pd.DataFrame, events: list[dict[str, object]]) -> list[dict[str, object]]:
    enriched: list[dict[str, object]] = []
    for event in events:
        target = pd.Timestamp(event["target_time"])
        vintages = panel.loc[panel["target_time"] == target].sort_values("issue_time")
        item = dict(event)
        item["vintages"] = [
            {
                "issue_time": row.issue_time.isoformat(),
                "horizon_minutes": float(row.horizon_minutes),
                "forecast_price": float(row.forecast_price),
            }
            for row in vintages.itertuples()
        ]
        enriched.append(item)
    return enriched


def findings(panel: pd.DataFrame) -> dict[str, object]:
    frame = add_analysis_fields(panel)
    selected = select_vintage(panel, 30)
    selected["absolute_error"] = selected["forecast_error"].abs()
    actuals = selected.drop_duplicates("target_time")
    near = frame.loc[frame["horizon_bucket"] == "0-10", "absolute_error"].mean()
    far = frame.loc[frame["horizon_bucket"] == "50-60", "absolute_error"].mean()
    top_one_percent = selected.nlargest(max(1, len(selected) // 100), "absolute_error")["absolute_error"].sum()
    result = {
        "lead_minutes": 30,
        "near_horizon_mae": float(near),
        "far_horizon_mae": float(far),
        "far_to_near_error_ratio": float(far / near),
        "thirty_minute_mae": float(selected["absolute_error"].mean()),
        "thirty_minute_bias": float(selected["forecast_error"].mean()),
        "top_one_percent_error_share": float(top_one_percent / selected["absolute_error"].sum()),
        "actual_intervals_above_300": int((actuals["actual_price"] > 300).sum()),
        "actual_intervals_above_1000": int((actuals["actual_price"] > 1000).sum()),
        "max_actual_price": float(actuals["actual_price"].max()),
        "largest_underforecast": float(selected["forecast_error"].min()),
        "largest_overforecast": float(selected["forecast_error"].max()),
    }
    if "actual_demand" in selected:
        demand_error = selected["forecast_demand"] - selected["actual_demand"]
        result.update(
            {
                "thirty_minute_demand_mae_mw": float(demand_error.abs().mean()),
                "thirty_minute_demand_bias_mw": float(demand_error.mean()),
                "absolute_demand_price_error_correlation": float(
                    demand_error.abs().corr(selected["forecast_error"].abs())
                ),
                "demand_mae_when_price_above_1000_mw": float(
                    demand_error.loc[selected["actual_price"] > 1000].abs().mean()
                ),
            }
        )
    return result


def export_analysis(panel: pd.DataFrame, root: Path) -> None:
    output = root / "output"
    dashboard = output / "dashboard_data"
    figures = output / "figures"
    dashboard.mkdir(parents=True, exist_ok=True)
    figures.mkdir(parents=True, exist_ok=True)

    scores = scorecard(panel)
    (dashboard / "scorecard.json").write_text(json.dumps(scores, indent=2) + "\n", encoding="utf-8")
    misses = {"lead_minutes": 30, "events": enrich_events(panel, largest_misses(panel))}
    (dashboard / "events.json").write_text(json.dumps(misses, indent=2) + "\n", encoding="utf-8")

    heatmap = error_heatmap(panel)
    heatmap.reset_index().to_json(dashboard / "error_heatmap.json", orient="records", indent=2)
    (dashboard / "findings.json").write_text(json.dumps(findings(panel), indent=2) + "\n", encoding="utf-8")
    selected = select_vintage(panel, 30)
    # NEM interval timestamps label the interval end; midnight belongs to the prior market day.
    selected["month"] = (selected["target_time"] - pd.Timedelta("5min")).dt.strftime("%Y-%m")
    monthly = selected.groupby("month").apply(metric_row, include_groups=False).to_dict()
    (dashboard / "monthly.json").write_text(json.dumps(monthly, indent=2) + "\n", encoding="utf-8")
    case = misses["events"][0]
    case["selection_rule"] = "Largest absolute price miss using the forecast nearest to a 30-minute lead."
    (dashboard / "case_study.json").write_text(json.dumps(case, indent=2) + "\n", encoding="utf-8")
    _plot_horizon(scores, figures / "mae_by_horizon.png")
    _plot_heatmap(heatmap, figures / "error_heatmap.png")
    if "actual_demand" in panel:
        demand = add_analysis_fields(panel)
        demand["absolute_demand_error"] = (demand["forecast_demand"] - demand["actual_demand"]).abs()
        demand_rows = [
            {
                "horizon_minutes": str(bucket),
                "mae_mw": float(group["absolute_demand_error"].mean()),
                "bias_mw": float((group["forecast_demand"] - group["actual_demand"]).mean()),
            }
            for bucket, group in demand.groupby("horizon_bucket", observed=True)
        ]
        (dashboard / "demand.json").write_text(json.dumps(demand_rows, indent=2) + "\n", encoding="utf-8")
        _plot_demand(demand_rows, figures / "demand_mae_by_horizon.png")


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


def _plot_demand(rows: list[dict[str, object]], destination: Path) -> None:
    fig, ax = plt.subplots(figsize=(8.5, 4.8))
    ax.bar([str(row["horizon_minutes"]) for row in rows], [float(row["mae_mw"]) for row in rows], color="#688b72")
    ax.set(title="VIC demand forecast error by horizon", xlabel="Forecast horizon (minutes)", ylabel="Mean absolute error (MW)")
    ax.grid(axis="y", alpha=0.2)
    ax.set_axisbelow(True)
    fig.tight_layout()
    fig.savefig(destination, dpi=180)
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--panel", type=Path, help="Panel parquet; defaults to the prototype panel")
    args = parser.parse_args()
    panel_path = args.panel or args.root / "data" / "processed" / "forecast_actual_panel.parquet"
    panel = pd.read_parquet(panel_path)
    export_analysis(panel, args.root)
    scores = scorecard(panel)
    print(json.dumps(scores, indent=2))


if __name__ == "__main__":
    main()
