import numpy as np
import pandas as pd


def detect_demand_anomalies(
    data: pd.DataFrame,
    window: int = 7,
    threshold: float = 2.0,
) -> pd.DataFrame:
    """Detects statistical anomalies and pandemic/outbreak demand surges in medical consumption."""
    df = data.copy()

    if "daily_demand" in df.columns and "units_consumed" not in df.columns:
        df["units_consumed"] = df["daily_demand"]

    if "units_consumed" not in df.columns:
        raise ValueError("Data must contain 'units_consumed' or 'daily_demand'.")

    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").reset_index(drop=True)

    rolling_mean = (
        df["units_consumed"]
        .rolling(window=window, min_periods=3)
        .mean()
    )

    rolling_std = (
        df["units_consumed"]
        .rolling(window=window, min_periods=3)
        .std()
    )

    # Prevent division by zero
    rolling_std = rolling_std.replace(0, np.nan).fillna(1.0)
    rolling_mean = rolling_mean.bfill().ffill()

    df["rolling_mean"] = rolling_mean
    df["rolling_std"] = rolling_std
    df["z_score"] = ((df["units_consumed"] - rolling_mean) / rolling_std).fillna(0.0).round(2)

    # Anomaly flag (two-tailed or positive surge)
    df["anomaly"] = df["z_score"].abs() >= threshold

    # Outbreak / Surge detection: sustained positive spike (Z-score > 2.0 or consumption > 1.5x 14-day baseline)
    baseline_14 = df["units_consumed"].rolling(window=14, min_periods=3).mean().bfill()
    df["surge_ratio"] = (df["units_consumed"] / baseline_14.replace(0, 1.0)).round(2)
    df["outbreak_signal"] = (df["z_score"] >= threshold) & (df["surge_ratio"] >= 1.35)

    return df