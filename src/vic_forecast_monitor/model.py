from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.metrics import mean_absolute_error, root_mean_squared_error

from .analysis import select_vintage

FEATURES = [
    "forecast_price",
    "forecast_demand",
    "forecast_solar_uigf_mw",
    "forecast_wind_uigf_mw",
    "forecast_net_interchange_mw",
    "forecast_revision_mwh",
    "known_price_35m_ago",
    "known_price_60m_ago",
    "hour_sin",
    "hour_cos",
    "weekday_sin",
    "weekday_cos",
]


def feature_frame(panel: pd.DataFrame, lead_minutes: float = 30) -> pd.DataFrame:
    selected = select_vintage(panel, lead_minutes)
    earliest = panel.sort_values("horizon_minutes", ascending=False).drop_duplicates(["target_time", "region"])
    first_forecast = earliest.set_index("target_time")["forecast_price"]
    actual = selected.drop_duplicates("target_time").set_index("target_time")["actual_price"]
    selected["forecast_revision_mwh"] = selected["forecast_price"] - selected["target_time"].map(first_forecast)
    selected["known_price_35m_ago"] = (selected["target_time"] - pd.Timedelta("35min")).map(actual)
    selected["known_price_60m_ago"] = (selected["target_time"] - pd.Timedelta("60min")).map(actual)
    hour = selected["target_time"].dt.hour + selected["target_time"].dt.minute / 60
    weekday = selected["target_time"].dt.dayofweek
    selected["hour_sin"] = np.sin(2 * np.pi * hour / 24)
    selected["hour_cos"] = np.cos(2 * np.pi * hour / 24)
    selected["weekday_sin"] = np.sin(2 * np.pi * weekday / 7)
    selected["weekday_cos"] = np.cos(2 * np.pi * weekday / 7)
    return selected.dropna(subset=FEATURES).reset_index(drop=True)


def train_and_evaluate(panel: pd.DataFrame, cutoff: str = "2025-10-01") -> tuple[pd.DataFrame, dict[str, object]]:
    frame = feature_frame(panel)
    cutoff_time = pd.Timestamp(cutoff)
    train = frame.loc[frame["target_time"] < cutoff_time].copy()
    test = frame.loc[frame["target_time"] >= cutoff_time].copy()
    model = HistGradientBoostingRegressor(
        loss="absolute_error",
        learning_rate=0.06,
        max_iter=250,
        max_leaf_nodes=24,
        min_samples_leaf=60,
        l2_regularization=2.0,
        random_state=42,
    )
    model.fit(train[FEATURES], train["actual_price"])
    test["model_fair_value"] = model.predict(test[FEATURES])
    test["model_edge"] = test["model_fair_value"] - test["forecast_price"]
    test["signal"] = np.select(
        [test["model_edge"] >= 25, test["model_edge"] <= -25],
        ["MODEL HIGHER", "MODEL LOWER"],
        default="NEUTRAL",
    )
    actual = test["actual_price"]
    aemo_mae = mean_absolute_error(actual, test["forecast_price"])
    model_mae = mean_absolute_error(actual, test["model_fair_value"])
    summary = {
        "model": "Histogram gradient boosting with absolute-error loss",
        "signal_definition": "Model fair value minus AEMO P5MIN forecast at approximately 30 minutes",
        "signal_threshold_mwh": 25,
        "training_start": train["target_time"].min().isoformat(),
        "training_end": train["target_time"].max().isoformat(),
        "test_start": test["target_time"].min().isoformat(),
        "test_end": test["target_time"].max().isoformat(),
        "training_intervals": int(len(train)),
        "test_intervals": int(len(test)),
        "aemo_mae": float(aemo_mae),
        "model_mae": float(model_mae),
        "mae_improvement_percent": float((aemo_mae - model_mae) / aemo_mae * 100),
        "aemo_rmse": float(root_mean_squared_error(actual, test["forecast_price"])),
        "model_rmse": float(root_mean_squared_error(actual, test["model_fair_value"])),
        "model_bias": float((test["model_fair_value"] - actual).mean()),
        "aemo_bias": float((test["forecast_price"] - actual).mean()),
        "signals": {key: int(value) for key, value in test["signal"].value_counts().items()},
        "warning": "A forecast-disagreement research signal, not an executable market price or backtested trading P&L.",
    }
    return test, summary


def export_model(test: pd.DataFrame, summary: dict[str, object], root: Path) -> None:
    destination = root / "output" / "dashboard_data"
    destination.mkdir(parents=True, exist_ok=True)
    (destination / "model_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    display = test.nlargest(100, "model_edge", keep="all").head(50)
    low = test.nsmallest(50, "model_edge")
    display = pd.concat([display, low]).sort_values("target_time")
    columns = ["target_time", "issue_time", "forecast_price", "model_fair_value", "actual_price", "model_edge", "signal"]
    for column in ("target_time", "issue_time"):
        display[column] = display[column].map(pd.Timestamp.isoformat)
    (destination / "model_signals.json").write_text(json.dumps(display[columns].to_dict(orient="records"), indent=2) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--panel", type=Path, required=True)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    test, summary = train_and_evaluate(pd.read_parquet(args.panel))
    export_model(test, summary, args.root)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
