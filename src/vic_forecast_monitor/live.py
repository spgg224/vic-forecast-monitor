from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import re
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin

import joblib
import numpy as np
import pandas as pd
import requests

from .aemo import _flat_table_rows, _optional_float, _parse_dispatch_rows, TIME_FORMAT
from .model import FEATURES

P5_INDEX = "https://www.nemweb.com.au/Reports/Current/P5_Reports/"
DISPATCH_INDEX = "https://www.nemweb.com.au/Reports/Current/DispatchIS_Reports/"


def current_urls(index_url: str, pattern: str, limit: int = 96) -> list[str]:
    response = requests.get(index_url, timeout=30)
    response.raise_for_status()
    links = re.findall(r'href=["\']([^"\']+\.zip)["\']', response.text, flags=re.I)
    matching = sorted({urljoin(index_url, link) for link in links if pattern in link.upper()})
    return matching[-limit:]


def cache_files(urls: list[str], directory: Path) -> list[Path]:
    directory.mkdir(parents=True, exist_ok=True)
    def fetch(url: str) -> Path | None:
        path = directory / url.rsplit("/", 1)[-1]
        if not path.exists():
            response = requests.get(url, timeout=60, headers={"User-Agent": "vic-forecast-monitor/1.0"})
            if not response.ok:
                return None  # Current indexes can retain a link briefly after its file rolls off.
            path.write_bytes(response.content)
        return path

    with ThreadPoolExecutor(max_workers=6) as pool:
        return [path for path in pool.map(fetch, urls) if path is not None]


def parse_current_p5(archives: list[Path], region: str = "VIC1") -> pd.DataFrame:
    records: list[dict[str, object]] = []
    for archive in archives:
        for source, row in _flat_table_rows(archive, "P5MIN", "REGIONSOLUTION"):
            if row.get("REGIONID") != region or row.get("INTERVENTION") != "0":
                continue
            issue = pd.to_datetime(row["LASTCHANGED"], format=TIME_FORMAT)
            target = pd.to_datetime(row["INTERVAL_DATETIME"], format=TIME_FORMAT)
            records.append({
                "issue_time": issue,
                "target_time": target,
                "region": region,
                "horizon_minutes": (target - issue).total_seconds() / 60,
                "forecast_price": float(row["RRP"]),
                "forecast_demand": float(row["TOTALDEMAND"]),
                "forecast_solar_uigf_mw": _optional_float(row.get("SS_SOLAR_UIGF")),
                "forecast_wind_uigf_mw": _optional_float(row.get("SS_WIND_UIGF")),
                "forecast_net_interchange_mw": _optional_float(row.get("NETINTERCHANGE")),
                "source_file": source,
            })
    return pd.DataFrame(records).drop_duplicates(["issue_time", "target_time", "region"], keep="last")


def parse_current_dispatch(archives: list[Path], region: str = "VIC1") -> pd.DataFrame:
    frames = [_parse_dispatch_rows(_flat_table_rows(path, "DISPATCH", "PRICE"), region) for path in archives]
    return pd.concat(frames, ignore_index=True).drop_duplicates(["target_time", "region"], keep="last")


def live_feature_frame(p5: pd.DataFrame, actuals: pd.DataFrame, lead: float = 30) -> pd.DataFrame:
    candidates = p5.loc[p5["horizon_minutes"] > 0].copy()
    candidates["lead_distance"] = (candidates["horizon_minutes"] - lead).abs()
    selected = candidates.sort_values(["target_time", "lead_distance"]).drop_duplicates("target_time").copy()
    earliest = candidates.sort_values("horizon_minutes", ascending=False).drop_duplicates("target_time")
    selected["forecast_revision_mwh"] = selected["forecast_price"] - selected["target_time"].map(earliest.set_index("target_time")["forecast_price"])
    actual_map = actuals.set_index("target_time")["actual_price"]
    selected["known_price_35m_ago"] = (selected["target_time"] - pd.Timedelta(minutes=35)).map(actual_map)
    selected["known_price_60m_ago"] = (selected["target_time"] - pd.Timedelta(minutes=60)).map(actual_map)
    hour = selected["target_time"].dt.hour + selected["target_time"].dt.minute / 60
    weekday = selected["target_time"].dt.dayofweek
    selected["hour_sin"] = np.sin(2 * np.pi * hour / 24)
    selected["hour_cos"] = np.cos(2 * np.pi * hour / 24)
    selected["weekday_sin"] = np.sin(2 * np.pi * weekday / 7)
    selected["weekday_cos"] = np.cos(2 * np.pi * weekday / 7)
    selected["actual_price"] = selected["target_time"].map(actual_map)
    return selected.dropna(subset=FEATURES).sort_values("target_time")


def build_live(root: Path, limit: int = 96) -> dict[str, object]:
    cache = root / "data" / "live"
    p5 = parse_current_p5(cache_files(current_urls(P5_INDEX, "PUBLIC_P5MIN_", limit), cache / "p5"))
    dispatch = parse_current_dispatch(cache_files(current_urls(DISPATCH_INDEX, "PUBLIC_DISPATCHIS_", limit), cache / "dispatch"))
    frame = live_feature_frame(p5, dispatch)
    model = joblib.load(root / "model" / "forecast_model.joblib")
    frame["model_fair_value"] = model.predict(frame[FEATURES])
    frame["model_edge"] = frame["model_fair_value"] - frame["forecast_price"]
    frame["signal"] = np.select([frame["model_edge"] >= 25, frame["model_edge"] <= -25], ["MODEL HIGHER", "MODEL LOWER"], default="NEUTRAL")
    columns = ["target_time", "issue_time", "forecast_price", "model_fair_value", "actual_price", "model_edge", "signal"]
    rows = frame.tail(72)[columns].copy()
    for column in ("target_time", "issue_time"):
        rows[column] = rows[column].map(pd.Timestamp.isoformat)
    records = [
        {key: (None if pd.isna(value) else value) for key, value in record.items()}
        for record in rows.to_dict(orient="records")
    ]
    payload = {
        "generated_at": datetime.now().astimezone().isoformat(),
        "source": "AEMO NEMWeb Current P5MIN and DispatchIS reports",
        "refresh_note": "Rolling feed; actual price is blank until dispatch has occurred.",
        "rows": records,
    }
    destination = root / "dashboard" / "public" / "data" / "live.json"
    destination.write_text(json.dumps(payload, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--limit", type=int, default=96)
    args = parser.parse_args()
    payload = build_live(args.root, args.limit)
    print(f"Exported {len(payload['rows'])} rolling observations at {payload['generated_at']}")


if __name__ == "__main__":
    main()
