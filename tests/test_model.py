import pandas as pd


def test_lagged_price_is_known_before_forecast_issue_time():
    target_time = pd.Timestamp("2025-10-01 12:00:00")
    issue_time = pd.Timestamp("2025-10-01 11:31:30")
    known_price_time = target_time - pd.Timedelta(minutes=35)
    assert known_price_time < issue_time


def test_chronological_holdout_does_not_overlap_training():
    cutoff = pd.Timestamp("2025-10-01 00:00:00")
    target_times = pd.Series(pd.to_datetime([
        "2025-09-30 23:55:00",
        "2025-10-01 00:00:00",
    ]))
    train = target_times[target_times < cutoff]
    test = target_times[target_times >= cutoff]
    assert train.max() < test.min()
