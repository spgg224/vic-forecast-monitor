from __future__ import annotations

import argparse
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


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--month", required=True, help="Month in YYYY-MM format")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    month = date.fromisoformat(f"{args.month}-01")
    panel = run(month, args.root)
    print(f"{args.month}: {len(panel):,} vintages, {panel.target_time.nunique():,} intervals")


if __name__ == "__main__":
    main()
