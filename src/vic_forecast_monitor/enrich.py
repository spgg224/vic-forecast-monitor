from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

import pandas as pd

from .aemo import download, monthly_regionsum_url, parse_regionsum_monthly


def enrich_year(year: int, root: Path) -> tuple[pd.DataFrame, dict[str, object]]:
    actual_frames: list[pd.DataFrame] = []
    for month_number in range(1, 13):
        month = date(year, month_number, 1)
        stamp = f"{year}{month_number:02d}"
        archive = root / "data" / "raw" / "dispatch" / f"PUBLIC_ARCHIVE_DISPATCHREGIONSUM_{stamp}.zip"
        download(monthly_regionsum_url(month), archive)
        actual_frames.append(parse_regionsum_monthly(archive))
        print(f"{stamp}: regional dispatch summary parsed")

    actuals = (
        pd.concat(actual_frames, ignore_index=True)
        .sort_values("target_time")
        .drop_duplicates(["target_time", "region"], keep="last")
    )
    panel_path = root / "data" / "processed" / f"forecast_actual_panel_{year}.parquet"
    panel = pd.read_parquet(panel_path)
    enriched = panel.merge(actuals, on=["target_time", "region"], how="left", validate="many_to_one")
    enriched["demand_error_mw"] = enriched["forecast_demand"] - enriched["actual_demand"]
    audit = {
        "year": year,
        "forecast_vintages": int(len(enriched)),
        "missing_actual_demand": int(enriched["actual_demand"].isna().sum()),
        "demand_mae_mw": float(enriched["demand_error_mw"].abs().mean()),
        "demand_bias_mw": float(enriched["demand_error_mw"].mean()),
        "correlation_absolute_demand_and_price_error": float(
            enriched["demand_error_mw"].abs().corr(enriched["forecast_error"].abs())
        ),
    }
    if audit["missing_actual_demand"]:
        raise ValueError(f"Missing actual demand after join: {audit}")
    enriched.to_parquet(root / "data" / "processed" / f"forecast_actual_panel_{year}_enriched.parquet", index=False)
    (root / "data" / "metadata" / f"demand_audit_{year}.json").write_text(json.dumps(audit, indent=2) + "\n", encoding="utf-8")
    return enriched, audit


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    _, audit = enrich_year(args.year, args.root)
    print(json.dumps(audit, indent=2))


if __name__ == "__main__":
    main()
