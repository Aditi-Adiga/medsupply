import pandas as pd

from app.ml.forecasting import forecast_demand, evaluate_forecast_metrics
from app.ml.preprocessing import prepare_demand_data
from app.ml.anomaly_detection import detect_demand_anomalies


def test_prepare_demand_data():
    data = pd.DataFrame({
        "date": pd.date_range(start="2026-01-01", periods=15),
        "units_consumed": [10, 12, 11, 13, 14, 12, 15, 16, 14, 17, 18, 16, 19, 20, 22],
    })
    df_prepared = prepare_demand_data(data)
    assert "day_of_week" in df_prepared.columns
    assert "rolling_mean_7" in df_prepared.columns
    assert "lag_1" in df_prepared.columns
    assert len(df_prepared) == 15


def test_forecast_demand():
    data = pd.DataFrame({
        "date": pd.date_range(start="2026-01-01", periods=14),
        "units_consumed": [10, 12, 11, 13, 14, 12, 15, 16, 14, 17, 18, 16, 19, 20],
    })

    result = forecast_demand(
        data=data,
        horizon_days=7,
    )

    assert "forecast" in result
    assert len(result["forecast"]) == 7
    assert all(value >= 0 for value in result["forecast"])
    assert result["daily_average"] > 0
    assert len(result["lower_bound"]) == 7
    assert len(result["upper_bound"]) == 7


def test_detect_demand_anomalies():
    # Normal data with one extreme surge spike at the end
    units = [50] * 10 + [250]
    data = pd.DataFrame({
        "date": pd.date_range(start="2026-01-01", periods=11),
        "units_consumed": units,
    })

    anomaly_df = detect_demand_anomalies(data, threshold=2.0)
    assert "anomaly" in anomaly_df.columns
    assert "z_score" in anomaly_df.columns
    assert anomaly_df["anomaly"].iloc[-1] == True


def test_evaluate_forecast_metrics():
    y_true = [100.0, 110.0, 105.0, 120.0]
    y_pred = [102.0, 108.0, 107.0, 118.0]
    metrics = evaluate_forecast_metrics(y_true, y_pred)
    assert "MAE" in metrics
    assert "RMSE" in metrics
    assert "MAPE_percent" in metrics
    assert "R2_Score" in metrics
    assert metrics["MAE"] >= 0