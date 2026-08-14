from pathlib import Path

import pandas as pd

from vic_forecast_monitor.aemo import build_panel, parse_dispatch, parse_p5min, parse_regionsum_monthly
from vic_forecast_monitor.monthly import audit_month


def test_sample_archives_parse() -> None:
    root = Path(__file__).parents[1]
    p5 = root / "data/raw/p5min/PUBLIC_P5MIN_20260701.zip"
    dispatch = root / "data/raw/dispatch/PUBLIC_DISPATCHIS_20260701.zip"
    if not p5.exists() or not dispatch.exists():
        return
    forecasts = parse_p5min(p5)
    actuals = parse_dispatch(dispatch)
    assert not forecasts.empty
    assert not actuals.empty
    assert forecasts["horizon_minutes"].between(0, 60).all()
    assert (forecasts["issue_time"] < forecasts["run_time"]).all()
    assert forecasts.groupby("target_time").size().max() >= 6


def test_panel_rejects_lookahead() -> None:
    forecasts = pd.DataFrame(
        {
            "issue_time": pd.to_datetime(["2026-01-01 00:10"]),
            "target_time": pd.to_datetime(["2026-01-01 00:05"]),
            "region": ["VIC1"],
            "forecast_price": [100.0],
        }
    )
    actuals = pd.DataFrame(
        {"target_time": pd.to_datetime(["2026-01-01 00:05"]), "region": ["VIC1"], "actual_price": [90.0]}
    )
    try:
        build_panel(forecasts, actuals)
    except ValueError as error:
        assert "Lookahead" in str(error)
    else:
        raise AssertionError("Lookahead row was accepted")


def test_month_audit_rejects_duplicate_vintage() -> None:
    panel = pd.DataFrame(
        {
            "issue_time": pd.to_datetime(["2026-01-01 00:00"] * 2),
            "target_time": pd.to_datetime(["2026-01-01 00:05"] * 2),
            "region": ["VIC1"] * 2,
            "horizon_minutes": [5.0] * 2,
            "actual_price": [10.0] * 2,
        }
    )
    audit = audit_month(panel, "202601")
    assert not audit["passed"]
    assert audit["duplicate_vintages"] == 1


def test_monthly_regionsum_parses_actual_demand() -> None:
    archive = Path(__file__).parents[1] / "data/raw/dispatch/PUBLIC_ARCHIVE_DISPATCHREGIONSUM_202501.zip"
    if not archive.exists():
        return
    actuals = parse_regionsum_monthly(archive)
    assert len(actuals) == 8_928
    assert actuals["actual_demand"].notna().all()
