import json
import math
import os
import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

from app.ml.preprocessing import prepare_demand_data

MODEL_DIR = "app/ml/models"
PERSISTED_MODEL_PATH = os.path.join(MODEL_DIR, "demand_forecaster.joblib")
_CACHED_GLOBAL_MODEL = None
_CACHED_FEATURE_COLS = None


def get_or_load_pretrained_model():
    """Loads the pre-trained production model from disk if available for fast inference."""
    global _CACHED_GLOBAL_MODEL, _CACHED_FEATURE_COLS
    if _CACHED_GLOBAL_MODEL is not None:
        return _CACHED_GLOBAL_MODEL, _CACHED_FEATURE_COLS

    if os.path.exists(PERSISTED_MODEL_PATH):
        try:
            artifact = joblib.load(PERSISTED_MODEL_PATH)
            _CACHED_GLOBAL_MODEL = artifact["model"]
            _CACHED_FEATURE_COLS = artifact["feature_cols"]
            return _CACHED_GLOBAL_MODEL, _CACHED_FEATURE_COLS
        except Exception:
            pass
    return None, None


def train_demand_forecaster(
    data: pd.DataFrame,
) -> tuple[object, list[str]]:
    """Trains a machine learning regressor on engineered demand features."""
    df_feat = prepare_demand_data(data)

    feature_cols = [
        "day_of_week",
        "is_weekend",
        "day_of_month",
        "month",
        "quarter",
        "lag_1",
        "lag_2",
        "lag_3",
        "lag_7",
        "lag_14",
        "rolling_mean_3",
        "rolling_mean_7",
        "rolling_mean_14",
        "rolling_std_7",
        "ema_7",
        "ema_14",
    ]

    if "patient_load" in df_feat.columns:
        feature_cols.append("patient_load")
    if "emergency_demand" in df_feat.columns:
        feature_cols.append("emergency_demand")

    feature_cols = [c for c in feature_cols if c in df_feat.columns]

    X = df_feat[feature_cols].fillna(0.0).infer_objects(copy=False)
    y = df_feat["units_consumed"].fillna(0.0)

    if len(df_feat) >= 30:
        model = GradientBoostingRegressor(
            n_estimators=100,
            learning_rate=0.08,
            max_depth=4,
            random_state=42,
        )
    else:
        model = Ridge(alpha=1.0)

    model.fit(X, y)
    return model, feature_cols


def forecast_demand(
    data: pd.DataFrame,
    horizon_days: int = 7,
    confidence_level: float = 0.90,
) -> dict:
    """Generates multi-step ahead demand forecasts with confidence intervals using ML & time-series dynamics."""
    if data.empty:
        raise ValueError("Demand data cannot be empty.")

    if "daily_demand" in data.columns and "units_consumed" not in data.columns:
        data = data.copy()
        data["units_consumed"] = data["daily_demand"]

    if "units_consumed" not in data.columns:
        raise ValueError("Data must contain 'units_consumed' or 'daily_demand'.")

    df = data.copy()
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").reset_index(drop=True)

    if len(df) < 5:
        avg = float(df["units_consumed"].mean())
        forecast_list = [round(avg, 2) for _ in range(horizon_days)]
        return {
            "forecast": forecast_list,
            "daily_average": round(avg, 2),
            "lower_bound": [round(max(0, avg * 0.8), 2) for _ in range(horizon_days)],
            "upper_bound": [round(avg * 1.2, 2) for _ in range(horizon_days)],
            "model_name": "Moving Average Fallback",
        }

    # Prepare feature set
    df_prepared = prepare_demand_data(df)

    # Use pre-trained production model if available, otherwise train dynamic forecaster
    model, feature_cols = get_or_load_pretrained_model()
    if model is None:
        model, feature_cols = train_demand_forecaster(df)

    # Ensure all required feature columns exist in simulated_df
    simulated_df = df_prepared.copy()
    for col in feature_cols:
        if col not in simulated_df.columns:
            simulated_df[col] = 0.0

    last_date = simulated_df["date"].max()
    forecast_values = []
    lower_bounds = []
    upper_bounds = []

    # Calculate historical residual standard deviation for confidence intervals
    historical_preds = model.predict(simulated_df[feature_cols].fillna(0.0))
    residuals = simulated_df["units_consumed"] - historical_preds
    sigma = float(np.std(residuals)) if len(residuals) > 1 else 5.0
    z_multiplier = 1.645 if confidence_level >= 0.90 else 1.96

    for step in range(1, horizon_days + 1):
        next_date = last_date + pd.Timedelta(days=step)
        
        day_of_week = next_date.dayofweek
        is_weekend = 1 if day_of_week in [5, 6] else 0
        day_of_month = next_date.day
        month = next_date.month
        quarter = (month - 1) // 3 + 1

        history_vals = simulated_df["units_consumed"].values
        lag_1 = history_vals[-1]
        lag_2 = history_vals[-2] if len(history_vals) >= 2 else lag_1
        lag_3 = history_vals[-3] if len(history_vals) >= 3 else lag_2
        lag_7 = history_vals[-7] if len(history_vals) >= 7 else lag_1
        lag_14 = history_vals[-14] if len(history_vals) >= 14 else lag_7

        roll_3 = float(np.mean(history_vals[-3:]))
        roll_7 = float(np.mean(history_vals[-7:]))
        roll_14 = float(np.mean(history_vals[-14:]))
        roll_std_7 = float(np.std(history_vals[-7:])) if len(history_vals) >= 7 else 0.0
        ema_7 = float(pd.Series(history_vals).ewm(span=7).mean().iloc[-1])
        ema_14 = float(pd.Series(history_vals).ewm(span=14).mean().iloc[-1])

        feat_dict = {
            "day_of_week": day_of_week,
            "is_weekend": is_weekend,
            "day_of_month": day_of_month,
            "month": month,
            "quarter": quarter,
            "lag_1": lag_1,
            "lag_2": lag_2,
            "lag_3": lag_3,
            "lag_7": lag_7,
            "lag_14": lag_14,
            "rolling_mean_3": roll_3,
            "rolling_mean_7": roll_7,
            "rolling_mean_14": roll_14,
            "rolling_std_7": roll_std_7,
            "ema_7": ema_7,
            "ema_14": ema_14,
        }

        if "patient_load" in feature_cols:
            feat_dict["patient_load"] = float(simulated_df["patient_load"].iloc[-7:].mean()) if "patient_load" in simulated_df.columns else 200.0
        if "emergency_demand" in feature_cols:
            feat_dict["emergency_demand"] = float(simulated_df["emergency_demand"].iloc[-7:].mean()) if "emergency_demand" in simulated_df.columns else 0.0

        # Fill any other missing features
        for fc in feature_cols:
            if fc not in feat_dict:
                feat_dict[fc] = 0.0

        row_df = pd.DataFrame([feat_dict])[feature_cols].fillna(0.0)
        predicted_demand = float(model.predict(row_df)[0])
        predicted_demand = max(0.0, predicted_demand)

        uncertainty = z_multiplier * sigma * math.sqrt(1 + (step * 0.1))
        lower_b = max(0.0, predicted_demand - uncertainty)
        upper_b = predicted_demand + uncertainty

        forecast_values.append(round(predicted_demand, 2))
        lower_bounds.append(round(lower_b, 2))
        upper_bounds.append(round(upper_b, 2))

        new_row = {
            "date": next_date,
            "units_consumed": predicted_demand,
        }
        for k, v in feat_dict.items():
            new_row[k] = v
        simulated_df = pd.concat([simulated_df, pd.DataFrame([new_row])], ignore_index=True)

    daily_avg = round(float(np.mean(forecast_values)), 2)

    return {
        "forecast": forecast_values,
        "daily_average": daily_avg,
        "lower_bound": lower_bounds,
        "upper_bound": upper_bounds,
        "model_name": type(model).__name__,
    }


def evaluate_forecast_metrics(y_true: list[float], y_pred: list[float]) -> dict:
    """Calculates comprehensive performance metrics for demand forecasting evaluation."""
    yt = np.array(y_true)
    yp = np.array(y_pred)

    mae = float(mean_absolute_error(yt, yp))
    rmse = float(np.sqrt(mean_squared_error(yt, yp)))
    r2 = float(r2_score(yt, yp)) if len(yt) > 1 else 1.0

    total_actual = float(np.sum(yt))
    wape = float(np.sum(np.abs(yt - yp)) / total_actual * 100) if total_actual > 0 else 0.0

    non_zero = yt > 0
    mape = float(np.mean(np.abs((yt[non_zero] - yp[non_zero]) / yt[non_zero])) * 100) if np.any(non_zero) else 0.0

    return {
        "MAE": round(mae, 2),
        "RMSE": round(rmse, 2),
        "MAPE_percent": round(mape, 2),
        "WAPE_percent": round(wape, 2),
        "R2_Score": round(r2, 4),
    }