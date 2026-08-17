from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor
import json
from datetime import date, timedelta
from pathlib import Path

import joblib
import pandas as pd

from .aemo import (
    DISPATCH_URL,
    P5MIN_URL,
    build_panel,
    download,
    monthly_urls,
    parse_dispatch,
    parse_dispatch_monthly,
    parse_p5min,
    parse_p5min_conditions,
    parse_p5min_conditions_monthly,
    parse_p5min_monthly,
)
from .model import FEATURES, feature_frame


def monthly_panel(month: date, root: Path) -> pd.DataFrame:
    stamp = f"{month.year}{month.month:02d}"
    cached = root / "data" / "processed" / "history" / f"model_panel_{stamp}.parquet"
    if cached.exists():
        return pd.read_parquet(cached)
    p5_url, dispatch_url = monthly_urls(month)
    p5_path = root / "data" / "raw" / "p5min" / f"PUBLIC_ARCHIVE_P5MIN_REGIONSOLUTION_{stamp}.zip"
    dispatch_path = root / "data" / "raw" / "dispatch" / f"PUBLIC_ARCHIVE_DISPATCHPRICE_{stamp}.zip"
    download(p5_url, p5_path)
    download(dispatch_url, dispatch_path)
    base = build_panel(parse_p5min_monthly(p5_path), parse_dispatch_monthly(dispatch_path))
    conditions = parse_p5min_conditions_monthly(p5_path)
    panel = base.merge(conditions, on=["issue_time", "run_time", "target_time", "region"], how="left", validate="one_to_one")
    cached.parent.mkdir(parents=True, exist_ok=True)
    panel.to_parquet(cached, index=False)
    return panel


def daily_panel(day: date, root: Path) -> pd.DataFrame:
    stamp = day.strftime("%Y%m%d")
    p5_path = root / "data" / "raw" / "p5min_daily" / f"PUBLIC_P5MIN_{stamp}.zip"
    dispatch_path = root / "data" / "raw" / "dispatch_daily" / f"PUBLIC_DISPATCHIS_{stamp}.zip"
    download(P5MIN_URL.format(day=stamp), p5_path)
    download(DISPATCH_URL.format(day=stamp), dispatch_path)
    base = build_panel(parse_p5min(p5_path), parse_dispatch(dispatch_path))
    conditions = parse_p5min_conditions(p5_path)
    return base.merge(conditions, on=["issue_time", "run_time", "target_time", "region"], how="left", validate="one_to_one")


def build_history(year: int, through: date, root: Path) -> dict[str, object]:
    frames: list[pd.DataFrame] = []
    month = date(year, 1, 1)
    current_month = date(through.year, through.month, 1)
    months: list[date] = []
    while month < current_month:
        months.append(month)
        month = date(month.year + (month.month == 12), month.month % 12 + 1, 1)
    if through.day == (date(through.year + (through.month == 12), through.month % 12 + 1, 1) - timedelta(days=1)).day:
        months.append(current_month)
        day = through + timedelta(days=1)
    else:
        day = current_month
    with ProcessPoolExecutor(max_workers=3) as pool:
        frames.extend(pool.map(monthly_panel, months, [root] * len(months)))
    while day <= through:
        print(f"Loading {day:%Y-%m-%d}", flush=True)
        frames.append(daily_panel(day, root))
        day += timedelta(days=1)
    panel = pd.concat(frames, ignore_index=True).drop_duplicates(["issue_time", "target_time", "region"], keep="last")
    frame = feature_frame(panel)
    model = joblib.load(root / "model" / "forecast_model.joblib")
    frame["model_fair_value"] = model.predict(frame[FEATURES])
    rows = frame[["target_time", "forecast_price", "model_fair_value", "actual_price"]].copy()
    rows = rows.loc[rows["target_time"].dt.minute.mod(15).eq(0)]
    rows["target_time"] = rows["target_time"].map(pd.Timestamp.isoformat)
    payload = {
        "start": rows["target_time"].iloc[0],
        "end": rows["target_time"].iloc[-1],
        "resolution_minutes": 15,
        "note": "Fifteen-minute display sample from the underlying five-minute series.",
        "rows": rows.to_dict(orient="records"),
    }
    destination = root / "dashboard" / "public" / "data" / f"history_{year}.json"
    destination.write_text(json.dumps(payload, separators=(",", ":"), allow_nan=False) + "\n", encoding="utf-8")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--year", type=int, default=2026)
    parser.add_argument("--through", type=date.fromisoformat, default=date.today() - timedelta(days=1))
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    payload = build_history(args.year, args.through, args.root)
    print(f"Exported {len(payload['rows']):,} observations from {payload['start']} to {payload['end']}")


if __name__ == "__main__":
    main()
