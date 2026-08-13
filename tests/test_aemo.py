from pathlib import Path

import pandas as pd

from vic_forecast_monitor.aemo import build_panel, parse_dispatch, parse_p5min


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
