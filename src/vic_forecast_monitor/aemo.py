from __future__ import annotations

import csv
import hashlib
import io
import json
import zipfile
from datetime import date, timedelta
from pathlib import Path
from typing import Iterator

import pandas as pd
import requests

P5MIN_URL = "https://www.nemweb.com.au/Reports/ARCHIVE/P5_Reports/PUBLIC_P5MIN_{day}.zip"
DISPATCH_URL = "https://www.nemweb.com.au/Reports/ARCHIVE/DispatchIS_Reports/PUBLIC_DISPATCHIS_{day}.zip"
MMS_BASE = "https://www.nemweb.com.au/Data_Archive/Wholesale_Electricity/MMSDM/{year}/MMSDM_{year}_{month}/MMSDM_Historical_Data_SQLLoader/DATA"
TIME_FORMAT = "%Y/%m/%d %H:%M:%S"


def days(start: date, end: date) -> Iterator[date]:
    """Yield calendar days in the inclusive range."""
    current = start
    while current <= end:
        yield current
        current += timedelta(days=1)


def download(url: str, destination: Path) -> dict[str, object]:
    """Download once and return source metadata suitable for a manifest."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    if not destination.exists():
        with requests.get(url, stream=True, timeout=120) as response:
            response.raise_for_status()
            with destination.open("wb") as handle:
                for chunk in response.iter_content(1024 * 1024):
                    handle.write(chunk)
    digest = hashlib.sha256(destination.read_bytes()).hexdigest()
    return {"url": url, "path": destination.as_posix(), "bytes": destination.stat().st_size, "sha256": digest}


def download_period(start: date, end: date, root: Path) -> list[dict[str, object]]:
    manifest: list[dict[str, object]] = []
    for day in days(start, end):
        stamp = day.strftime("%Y%m%d")
        for product, template in (("p5min", P5MIN_URL), ("dispatch", DISPATCH_URL)):
            path = root / product / f"PUBLIC_{'P5MIN' if product == 'p5min' else 'DISPATCHIS'}_{stamp}.zip"
            record = download(template.format(day=stamp), path)
            record.update({"product": product, "market_day": day.isoformat()})
            manifest.append(record)
    return manifest


def write_manifest(records: list[dict[str, object]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(records, indent=2) + "\n", encoding="utf-8")


def _table_rows(archive: Path, package: str, table: str) -> Iterator[tuple[str, dict[str, str]]]:
    """Stream only one MMS table from nested daily report archives."""
    info_prefix = f"I,{package},{table},".encode()
    data_prefix = f"D,{package},{table},".encode()
    with zipfile.ZipFile(archive) as outer:
        for inner_name in sorted(name for name in outer.namelist() if name.lower().endswith(".zip")):
            with outer.open(inner_name) as inner_handle:
                with zipfile.ZipFile(io.BytesIO(inner_handle.read())) as inner:
                    csv_name = next(name for name in inner.namelist() if name.lower().endswith(".csv"))
                    with inner.open(csv_name) as raw:
                        header: list[str] | None = None
                        for line in raw:
                            if line.startswith(info_prefix):
                                header = next(csv.reader([line.decode("utf-8-sig")]))[4:]
                            elif header is not None and line.startswith(data_prefix):
                                values = next(csv.reader([line.decode("utf-8-sig")]))[4:]
                                yield inner_name, dict(zip(header, values, strict=False))


def _flat_table_rows(
    archive: Path, package: str, table: str, data_contains: bytes | None = None
) -> Iterator[tuple[str, dict[str, str]]]:
    """Stream a table from an MMSDM monthly archive containing one CSV."""
    info_prefix = f"I,{package},{table},".encode()
    data_prefix = f"D,{package},{table},".encode()
    with zipfile.ZipFile(archive) as bundle:
        csv_name = next(name for name in bundle.namelist() if name.lower().endswith(".csv"))
        with bundle.open(csv_name) as raw:
            header: list[str] | None = None
            for line in raw:
                if line.startswith(info_prefix):
                    header = next(csv.reader([line.decode("utf-8-sig")]))[4:]
                elif header is not None and line.startswith(data_prefix) and (
                    data_contains is None or data_contains in line
                ):
                    values = next(csv.reader([line.decode("utf-8-sig")]))[4:]
                    yield csv_name, dict(zip(header, values, strict=False))


def monthly_urls(month: date) -> tuple[str, str]:
    base = MMS_BASE.format(year=month.year, month=f"{month.month:02d}")
    stamp = f"{month.year}{month.month:02d}010000"
    return (
        f"{base}/PUBLIC_ARCHIVE%23P5MIN_REGIONSOLUTION%23FILE01%23{stamp}.zip",
        f"{base}/PUBLIC_ARCHIVE%23DISPATCHPRICE%23FILE01%23{stamp}.zip",
    )


def monthly_regionsum_url(month: date) -> str:
    base = MMS_BASE.format(year=month.year, month=f"{month.month:02d}")
    stamp = f"{month.year}{month.month:02d}010000"
    return f"{base}/PUBLIC_ARCHIVE%23DISPATCHREGIONSUM%23FILE01%23{stamp}.zip"


def parse_p5min_monthly(archive: Path, region: str = "VIC1") -> pd.DataFrame:
    return _parse_p5min_rows(_flat_table_rows(archive, "P5MIN", "REGIONSOLUTION"), region)


def parse_p5min_conditions_monthly(archive: Path, region: str = "VIC1") -> pd.DataFrame:
    records: list[dict[str, object]] = []
    prefix = b"I,P5MIN,REGIONSOLUTION,"
    data_prefix = b"D,P5MIN,REGIONSOLUTION,"
    wanted = ["RUN_DATETIME", "LASTCHANGED", "INTERVAL_DATETIME", "REGIONID", "INTERVENTION", "SS_SOLAR_UIGF", "SS_WIND_UIGF", "NETINTERCHANGE"]
    with zipfile.ZipFile(archive) as bundle:
        source_file = next(name for name in bundle.namelist() if name.lower().endswith(".csv"))
        with bundle.open(source_file) as raw:
            indices: dict[str, int] | None = None
            for line in raw:
                if line.startswith(prefix):
                    header = line.decode("utf-8-sig").rstrip().split(",")[4:]
                    indices = {name: header.index(name) + 4 for name in wanted}
                elif indices is not None and line.startswith(data_prefix) and f",{region},".encode() in line:
                    values = line.decode("utf-8-sig").rstrip().split(",")
                    get = lambda name: values[indices[name]].strip('"')
                    if get("REGIONID") != region or get("INTERVENTION") != "0":
                        continue
                    records.append(
                        {
                            "run_time": get("RUN_DATETIME"),
                            "issue_time": get("LASTCHANGED"),
                            "target_time": get("INTERVAL_DATETIME"),
                            "region": region,
                            "forecast_solar_uigf_mw": _optional_float(get("SS_SOLAR_UIGF")),
                            "forecast_wind_uigf_mw": _optional_float(get("SS_WIND_UIGF")),
                            "forecast_net_interchange_mw": _optional_float(get("NETINTERCHANGE")),
                            "source_file_conditions": source_file,
                        }
                    )
    frame = pd.DataFrame.from_records(records)
    for column in ("run_time", "issue_time", "target_time"):
        frame[column] = pd.to_datetime(frame[column], format=TIME_FORMAT)
    return (
        frame.sort_values(["target_time", "issue_time"])
        .drop_duplicates(["issue_time", "target_time", "region"], keep="last")
        .reset_index(drop=True)
    )


def parse_dispatch_monthly(archive: Path, region: str = "VIC1") -> pd.DataFrame:
    return _parse_dispatch_rows(_flat_table_rows(archive, "DISPATCH", "PRICE", f",{region},".encode()), region)


def parse_regionsum_monthly(archive: Path, region: str = "VIC1") -> pd.DataFrame:
    records: list[dict[str, object]] = []
    for source_file, row in _flat_table_rows(archive, "DISPATCH", "REGIONSUM", f",{region},".encode()):
        if row.get("REGIONID") != region or row.get("INTERVENTION") != "0":
            continue
        records.append(
            {
                "target_time": pd.to_datetime(row["SETTLEMENTDATE"], format=TIME_FORMAT),
                "region": region,
                "actual_demand": float(row["TOTALDEMAND"]),
                "actual_solar_cleared_mw": _optional_float(row.get("SS_SOLAR_CLEAREDMW")),
                "actual_wind_cleared_mw": _optional_float(row.get("SS_WIND_CLEAREDMW")),
                "actual_net_interchange_mw": _optional_float(row.get("NETINTERCHANGE")),
                "source_file_regionsum": source_file,
            }
        )
    frame = pd.DataFrame.from_records(records)
    return frame.sort_values("target_time").drop_duplicates(["target_time", "region"], keep="last").reset_index(drop=True)


def _optional_float(value: str | None) -> float:
    return float(value) if value not in (None, "") else float("nan")


def parse_p5min(archive: Path, region: str = "VIC1") -> pd.DataFrame:
    return _parse_p5min_rows(_table_rows(archive, "P5MIN", "REGIONSOLUTION"), region)


def parse_p5min_conditions(archive: Path, region: str = "VIC1") -> pd.DataFrame:
    """Parse model condition fields from a nested daily P5MIN archive."""
    return _parse_p5min_condition_rows(_table_rows(archive, "P5MIN", "REGIONSOLUTION"), region)


def _parse_p5min_condition_rows(rows: Iterator[tuple[str, dict[str, str]]], region: str) -> pd.DataFrame:
    records: list[dict[str, object]] = []
    for source_file, row in rows:
        if row.get("REGIONID") != region or row.get("INTERVENTION") != "0":
            continue
        records.append({
            "run_time": pd.to_datetime(row["RUN_DATETIME"], format=TIME_FORMAT),
            "issue_time": pd.to_datetime(row["LASTCHANGED"], format=TIME_FORMAT),
            "target_time": pd.to_datetime(row["INTERVAL_DATETIME"], format=TIME_FORMAT),
            "region": region,
            "forecast_solar_uigf_mw": _optional_float(row.get("SS_SOLAR_UIGF")),
            "forecast_wind_uigf_mw": _optional_float(row.get("SS_WIND_UIGF")),
            "forecast_net_interchange_mw": _optional_float(row.get("NETINTERCHANGE")),
            "source_file_conditions": source_file,
        })
    return pd.DataFrame(records).drop_duplicates(["issue_time", "target_time", "region"], keep="last")


def _parse_p5min_rows(rows: Iterator[tuple[str, dict[str, str]]], region: str) -> pd.DataFrame:
    records: list[dict[str, object]] = []
    for source_file, row in rows:
        if row.get("REGIONID") != region or row.get("INTERVENTION") != "0":
            continue
        run_time = pd.to_datetime(row["RUN_DATETIME"], format=TIME_FORMAT)
        issue_time = pd.to_datetime(row["LASTCHANGED"], format=TIME_FORMAT)
        target_time = pd.to_datetime(row["INTERVAL_DATETIME"], format=TIME_FORMAT)
        records.append(
            {
                "issue_time": issue_time,
                "run_time": run_time,
                "target_time": target_time,
                "horizon_minutes": (target_time - issue_time).total_seconds() / 60,
                "region": region,
                "forecast_price": float(row["RRP"]),
                "forecast_demand": float(row["TOTALDEMAND"]),
                "source_file": source_file,
            }
        )
    return pd.DataFrame.from_records(records).sort_values(["target_time", "issue_time"]).reset_index(drop=True)


def parse_dispatch(archive: Path, region: str = "VIC1") -> pd.DataFrame:
    return _parse_dispatch_rows(_table_rows(archive, "DISPATCH", "PRICE"), region)


def _parse_dispatch_rows(rows: Iterator[tuple[str, dict[str, str]]], region: str) -> pd.DataFrame:
    records: list[dict[str, object]] = []
    for source_file, row in rows:
        if row.get("REGIONID") != region or row.get("INTERVENTION") != "0":
            continue
        records.append(
            {
                "target_time": pd.to_datetime(row["SETTLEMENTDATE"], format=TIME_FORMAT),
                "region": region,
                "actual_price": float(row["RRP"]),
                "source_file_actual": source_file,
            }
        )
    frame = pd.DataFrame.from_records(records)
    return frame.sort_values("target_time").drop_duplicates(["target_time", "region"], keep="last").reset_index(drop=True)


def build_panel(p5min: pd.DataFrame, actuals: pd.DataFrame) -> pd.DataFrame:
    panel = p5min.merge(actuals, on=["target_time", "region"], how="inner", validate="many_to_one")
    if (panel["issue_time"] > panel["target_time"]).any():
        raise ValueError("Lookahead detected: issue_time occurs after target_time")
    panel["forecast_error"] = panel["forecast_price"] - panel["actual_price"]
    return panel.sort_values(["target_time", "issue_time"]).reset_index(drop=True)
