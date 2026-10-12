import numpy as np
import pandas as pd


def prepare_demand_data(
    data: pd.DataFrame,
) -> pd.DataFrame:
    """Preprocess time-series medical consumption data, engineering lag, rolling, and temporal features."""
    df = data.copy()

    # Support either 'units_consumed' or 'daily_demand'
    if "daily_demand" in df.columns and "units_consumed" not in df.columns:
        df["units_consumed"] = df["daily_demand"]

    required_columns = ["date", "units_consumed"]
    missing = [col for col in required_columns if col not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns: {missing}")

    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").reset_index(drop=True)

    # Temporal Calendar Features
    df["day_of_week"] = df["date"].dt.dayofweek
    df["is_weekend"] = df["day_of_week"].isin([5, 6]).astype(int)
    df["day_of_month"] = df["date"].dt.day
    df["month"] = df["date"].dt.month
    df["quarter"] = df["date"].dt.quarter

    # Lag features
    for lag in [1, 2, 3, 7, 14]:
        df[f"lag_{lag}"] = df["units_consumed"].shift(lag)

    # Rolling window aggregations
    for window in [3, 7, 14, 28]:
        df[f"rolling_mean_{window}"] = (
            df["units_consumed"].shift(1).rolling(window=window, min_periods=1).mean()
        )
        df[f"rolling_std_{window}"] = (
            df["units_consumed"].shift(1).rolling(window=window, min_periods=1).std().fillna(0)
        )
        df[f"rolling_max_{window}"] = (
            df["units_consumed"].shift(1).rolling(window=window, min_periods=1).max()
        )

    # Exponential Moving Averages
    df["ema_7"] = df["units_consumed"].shift(1).ewm(span=7, adjust=False).mean()
    df["ema_14"] = df["units_consumed"].shift(1).ewm(span=14, adjust=False).mean()

    # Fill NaN for initial lag rows with backward/forward fill and zero fallback
    df = df.bfill().ffill().fillna(0.0)

    return df


def load_dataset(csv_path: str = "data/medical_supply_20_medicines.csv") -> pd.DataFrame:
    """Helper to load and validate the medical supply dataset."""
    df = pd.read_csv(csv_path)
    df["date"] = pd.to_datetime(df["date"])
    if "daily_demand" in df.columns and "units_consumed" not in df.columns:
        df["units_consumed"] = df["daily_demand"]
    return df