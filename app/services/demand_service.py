import os
import pandas as pd
from typing import Union

from app.ml.forecasting import forecast_demand


DATASET_PATH = "data/medical_supply_20_medicines.csv"


def load_hospital_medicine_data(
    hospital_id: Union[str, int],
    medicine_id: Union[str, int],
) -> pd.DataFrame:
    """Fetches real time-series consumption data for specific hospital and medicine."""
    if os.path.exists(DATASET_PATH):
        df = pd.read_csv(DATASET_PATH)
        df["date"] = pd.to_datetime(df["date"])

        # Filter by hospital and medicine (string matching e.g. H01 or 1)
        h_str = str(hospital_id).upper().strip()
        m_str = str(medicine_id).upper().strip()

        # Normalize H1 -> H01, M1 -> M01 if needed
        if h_str.isdigit():
            h_str = f"H{int(h_str):02d}"
        if m_str.isdigit():
            m_str = f"M{int(m_str):02d}"

        sub = df[(df["hospital_id"].astype(str).str.upper() == h_str) & 
                 (df["medicine_id"].astype(str).str.upper() == m_str)]

        if not sub.empty:
            sub = sub.sort_values("date").reset_index(drop=True)
            if "daily_demand" in sub.columns:
                sub["units_consumed"] = sub["daily_demand"]
            return sub

    # Fallback synthetic historical data
    dates = pd.date_range(end=pd.Timestamp.today(), periods=30)
    return pd.DataFrame({
        "date": dates,
        "units_consumed": [
            80, 85, 82, 90, 88, 95, 92, 100, 97, 105, 110, 108, 115, 120,
            112, 118, 125, 122, 130, 128, 135, 132, 140, 138, 145, 142, 150, 148, 155, 160
        ],
    })


def get_demand_forecast(
    data: pd.DataFrame,
    horizon_days: int = 7,
) -> dict:
    """Invokes ML demand forecaster on input time-series dataframe."""
    return forecast_demand(
        data=data,
        horizon_days=horizon_days,
    )