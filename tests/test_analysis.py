import pandas as pd

from vic_forecast_monitor.analysis import largest_misses, metric_row, select_vintage


def test_metrics_have_known_values() -> None:
    frame = pd.DataFrame({"forecast_error": [-2.0, 2.0]})
    result = metric_row(frame)
    assert result["mae"] == 2.0
    assert result["rmse"] == 2.0
    assert result["bias"] == 0.0


def test_vintage_selection_uses_declared_lead() -> None:
    target = pd.Timestamp("2026-01-01 18:00")
    frame = pd.DataFrame(
        {
            "target_time": [target, target],
            "issue_time": [target - pd.Timedelta(minutes=10), target - pd.Timedelta(minutes=31)],
            "horizon_minutes": [10.0, 31.0],
            "region": ["VIC1", "VIC1"],
            "forecast_error": [100.0, 5.0],
        }
    )
    selected = select_vintage(frame, lead_minutes=30)
    assert selected.iloc[0]["horizon_minutes"] == 31.0


def test_largest_miss_does_not_duplicate_target_intervals() -> None:
    target = pd.to_datetime(["2026-01-01 18:00", "2026-01-01 18:00", "2026-01-01 18:05"])
    frame = pd.DataFrame(
        {
            "target_time": target,
            "issue_time": target - pd.to_timedelta([30, 10, 30], unit="m"),
            "horizon_minutes": [30.0, 10.0, 30.0],
            "region": ["VIC1"] * 3,
            "forecast_price": [10.0, 200.0, 20.0],
            "actual_price": [100.0, 100.0, 25.0],
            "forecast_error": [-90.0, 100.0, -5.0],
            "source_file": ["forecast"] * 3,
            "source_file_actual": ["actual"] * 3,
        }
    )
    events = largest_misses(frame, count=20)
    assert len(events) == 2

