from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

from .aemo import build_panel, days, download_period, parse_dispatch, parse_p5min, write_manifest


def run(start: date, end: date, root: Path) -> pd.DataFrame:
    raw = root / "data" / "raw"
    manifest = download_period(start, end, raw)
    write_manifest(manifest, root / "data" / "metadata" / "manifest.json")

    forecasts = pd.concat(
        [parse_p5min(raw / "p5min" / f"PUBLIC_P5MIN_{day:%Y%m%d}.zip") for day in days(start, end)],
        ignore_index=True,
    )
    actuals = pd.concat(
        [parse_dispatch(raw / "dispatch" / f"PUBLIC_DISPATCHIS_{day:%Y%m%d}.zip") for day in days(start, end)],
        ignore_index=True,
    ).drop_duplicates(["target_time", "region"], keep="last")
    panel = build_panel(forecasts, actuals)

    processed = root / "data" / "processed"
    processed.mkdir(parents=True, exist_ok=True)
    forecasts.to_parquet(processed / "p5min_vintages.parquet", index=False)
    actuals.to_parquet(processed / "dispatch_actuals.parquet", index=False)
    panel.to_parquet(processed / "forecast_actual_panel.parquet", index=False)

    _plot_replay(panel, root / "output" / "figures" / "forecast_vintage_replay.png")
    return panel


def _plot_replay(panel: pd.DataFrame, destination: Path) -> None:
    vintage_counts = panel.groupby("target_time").size()
    eligible = vintage_counts[vintage_counts >= 6].index
    target = panel.loc[panel["target_time"].isin(eligible)].groupby("target_time")["actual_price"].max().idxmax()
    event = panel.loc[panel["target_time"] == target].sort_values("issue_time")

    destination.parent.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(10, 5.5))
    ax.plot(event["issue_time"], event["forecast_price"], marker="o", color="#277da1", label="P5MIN forecast")
    ax.axhline(event["actual_price"].iloc[0], color="#c44536", linestyle="--", label="Actual VIC1 RRP")
    ax.set(title=f"Forecast vintages for {target:%Y-%m-%d %H:%M} NEM time", xlabel="Forecast run time", ylabel="Price ($/MWh)")
    ax.grid(axis="y", alpha=0.2)
    ax.legend(frameon=False)
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(destination, dpi=180)
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", type=date.fromisoformat, default=date(2026, 7, 1))
    parser.add_argument("--end", type=date.fromisoformat, default=date(2026, 7, 7))
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    panel = run(args.start, args.end, args.root)
    print(f"Panel rows: {len(panel):,}")
    print(f"Target intervals: {panel['target_time'].nunique():,}")
    print(f"Forecast vintages per target: {panel.groupby('target_time').size().median():.0f} median")


if __name__ == "__main__":
    main()

