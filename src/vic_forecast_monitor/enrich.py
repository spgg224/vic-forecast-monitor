from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

import pandas as pd

from .aemo import download, monthly_regionsum_url, parse_p5min_conditions_monthly, parse_regionsum_monthly


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


def enrich_conditions(year: int, root: Path) -> tuple[pd.DataFrame, dict[str, object]]:
    condition_frames: list[pd.DataFrame] = []
    for month_number in range(1, 13):
        stamp = f"{year}{month_number:02d}"
        archive = root / "data" / "raw" / "p5min" / f"PUBLIC_ARCHIVE_P5MIN_REGIONSOLUTION_{stamp}.zip"
        condition_frames.append(parse_p5min_conditions_monthly(archive))
        print(f"{stamp}: renewable and net-interchange forecasts parsed")
    conditions = pd.concat(condition_frames, ignore_index=True)
    conditions = conditions.drop_duplicates(["issue_time", "target_time", "region"], keep="last")
    base_path = root / "data" / "processed" / f"forecast_actual_panel_{year}_enriched.parquet"
    panel = pd.read_parquet(base_path)
    merged = panel.merge(
        conditions,
        on=["issue_time", "run_time", "target_time", "region"],
        how="left",
        validate="one_to_one",
    )
    merged["solar_gap_mw"] = merged["forecast_solar_uigf_mw"] - merged["actual_solar_cleared_mw"]
    merged["wind_gap_mw"] = merged["forecast_wind_uigf_mw"] - merged["actual_wind_cleared_mw"]
    merged["net_interchange_error_mw"] = merged["forecast_net_interchange_mw"] - merged["actual_net_interchange_mw"]
    audit = {
        "year": year,
        "forecast_vintages": int(len(merged)),
        "missing_forecast_solar": int(merged["forecast_solar_uigf_mw"].isna().sum()),
        "missing_forecast_wind": int(merged["forecast_wind_uigf_mw"].isna().sum()),
        "missing_forecast_net_interchange": int(merged["forecast_net_interchange_mw"].isna().sum()),
    }
    if any(audit[key] for key in audit if key.startswith("missing_")):
        raise ValueError(f"Condition enrichment audit failed: {audit}")
    destination = root / "data" / "processed" / f"forecast_actual_panel_{year}_conditions.parquet"
    merged.to_parquet(destination, index=False)
    (root / "data" / "metadata" / f"conditions_audit_{year}.json").write_text(json.dumps(audit, indent=2) + "\n", encoding="utf-8")
    return merged, audit


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--conditions", action="store_true", help="Add renewable and net-interchange forecast conditions")
    args = parser.parse_args()
    _, audit = enrich_conditions(args.year, args.root) if args.conditions else enrich_year(args.year, args.root)
    print(json.dumps(audit, indent=2))


if __name__ == "__main__":
    main()
