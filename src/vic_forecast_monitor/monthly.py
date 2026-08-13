from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

import pandas as pd

from .aemo import build_panel, download, monthly_urls, parse_dispatch_monthly, parse_p5min_monthly


def run(month: date, root: Path) -> pd.DataFrame:
    stamp = f"{month.year}{month.month:02d}"
    p5_url, dispatch_url = monthly_urls(month)
    p5_path = root / "data" / "raw" / "p5min" / f"PUBLIC_ARCHIVE_P5MIN_REGIONSOLUTION_{stamp}.zip"
    dispatch_path = root / "data" / "raw" / "dispatch" / f"PUBLIC_ARCHIVE_DISPATCHPRICE_{stamp}.zip"
    download(p5_url, p5_path)
    download(dispatch_url, dispatch_path)
    panel = build_panel(parse_p5min_monthly(p5_path), parse_dispatch_monthly(dispatch_path))
    destination = root / "data" / "processed" / "monthly"
    destination.mkdir(parents=True, exist_ok=True)
    panel.to_parquet(destination / f"forecast_actual_panel_{stamp}.parquet", index=False)
    return panel


def build_year(year: int, root: Path) -> tuple[pd.DataFrame, dict[str, object]]:
    monthly_frames: list[pd.DataFrame] = []
    audits: list[dict[str, object]] = []
    for month_number in range(1, 13):
        month = date(year, month_number, 1)
        stamp = f"{year}{month_number:02d}"
        output = root / "data" / "processed" / "monthly" / f"forecast_actual_panel_{stamp}.parquet"
        panel = pd.read_parquet(output) if output.exists() else run(month, root)
        audit = audit_month(panel, stamp)
        if not audit["passed"]:
            raise ValueError(f"Integrity audit failed for {stamp}: {audit}")
        monthly_frames.append(panel)
        audits.append(audit)
        print(f"{stamp}: {audit['target_intervals']:,} intervals, {audit['forecast_vintages']:,} vintages")

    combined = pd.concat(monthly_frames, ignore_index=True).sort_values(["target_time", "issue_time"])
    duplicate_rows = int(combined.duplicated(["issue_time", "target_time", "region"]).sum())
    if duplicate_rows:
        combined = combined.drop_duplicates(["issue_time", "target_time", "region"], keep="last")
    combined = combined.reset_index(drop=True)
    audit = {
        "year": year,
        "passed": all(item["passed"] for item in audits),
        "months": audits,
        "forecast_vintages": int(len(combined)),
        "target_intervals": int(combined["target_time"].nunique()),
        "start": combined["target_time"].min().isoformat(),
        "end": combined["target_time"].max().isoformat(),
        "duplicate_rows_removed_at_year_boundary": duplicate_rows,
        "lookahead_violations": int((combined["issue_time"] > combined["target_time"]).sum()),
        "missing_actual_prices": int(combined["actual_price"].isna().sum()),
    }
    destination = root / "data" / "processed"
    combined.to_parquet(destination / f"forecast_actual_panel_{year}.parquet", index=False)
    metadata = root / "data" / "metadata"
    metadata.mkdir(parents=True, exist_ok=True)
    (metadata / f"audit_{year}.json").write_text(json.dumps(audit, indent=2) + "\n", encoding="utf-8")
    return combined, audit


def audit_month(panel: pd.DataFrame, stamp: str) -> dict[str, object]:
    target_counts = panel.groupby("target_time").size()
    issue_after_target = int((panel["issue_time"] > panel["target_time"]).sum())
    duplicate_vintages = int(panel.duplicated(["issue_time", "target_time", "region"]).sum())
    missing_actuals = int(panel["actual_price"].isna().sum())
    invalid_horizons = int((~panel["horizon_minutes"].between(0, 60)).sum())
    unique_targets = panel[["target_time", "actual_price"]].drop_duplicates("target_time")
    gaps = unique_targets["target_time"].sort_values().diff().dropna()
    non_five_minute_gaps = int((gaps != pd.Timedelta("5min")).sum())
    passed = not any((issue_after_target, duplicate_vintages, missing_actuals, invalid_horizons))
    return {
        "month": stamp,
        "passed": passed,
        "forecast_vintages": int(len(panel)),
        "target_intervals": int(target_counts.size),
        "start": panel["target_time"].min().isoformat(),
        "end": panel["target_time"].max().isoformat(),
        "median_vintages_per_target": float(target_counts.median()),
        "min_vintages_per_target": int(target_counts.min()),
        "max_vintages_per_target": int(target_counts.max()),
        "lookahead_violations": issue_after_target,
        "duplicate_vintages": duplicate_vintages,
        "missing_actual_prices": missing_actuals,
        "invalid_horizons": invalid_horizons,
        "non_five_minute_gaps": non_five_minute_gaps,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--month", help="Month in YYYY-MM format")
    parser.add_argument("--year", type=int, help="Build and audit a full calendar year")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    if args.year:
        panel, audit = build_year(args.year, args.root)
        print(json.dumps(audit, indent=2))
    else:
        if not args.month:
            parser.error("provide either --month YYYY-MM or --year YYYY")
        month = date.fromisoformat(f"{args.month}-01")
        panel = run(month, args.root)
        print(f"{args.month}: {len(panel):,} vintages, {panel.target_time.nunique():,} intervals")


if __name__ == "__main__":
    main()
