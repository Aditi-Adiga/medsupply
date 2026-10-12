import pandas as pd
from typing import Union

from app.ml.anomaly_detection import detect_demand_anomalies
from app.services.demand_service import load_hospital_medicine_data


def analyze_demand_anomalies(
    data: pd.DataFrame,
    threshold: float = 2.0,
) -> pd.DataFrame:
    """Runs statistical anomaly and outbreak surge detection on input consumption data."""
    return detect_demand_anomalies(data=data, threshold=threshold)


def get_anomaly_summary(
    hospital_id: Union[str, int],
    medicine_id: Union[str, int],
    threshold: float = 2.0,
) -> dict:
    """Fetches real history for hospital/medicine and computes detailed anomaly diagnostics."""
    df = load_hospital_medicine_data(hospital_id=hospital_id, medicine_id=medicine_id)
    anomaly_df = detect_demand_anomalies(df, threshold=threshold)

    total_records = len(anomaly_df)
    anomalies_detected = int(anomaly_df["anomaly"].sum())
    outbreak_signals = int(anomaly_df["outbreak_signal"].sum()) if "outbreak_signal" in anomaly_df.columns else 0

    points = []
    # Return last 30 days of data points
    for _, row in anomaly_df.tail(30).iterrows():
        points.append({
            "date": str(row["date"])[:10],
            "units_consumed": float(row["units_consumed"]),
            "z_score": float(row.get("z_score", 0.0)),
            "is_anomaly": bool(row.get("anomaly", False)),
            "is_outbreak_spike": bool(row.get("outbreak_signal", False)),
        })

    return {
        "hospital_id": hospital_id,
        "medicine_id": medicine_id,
        "total_records": total_records,
        "anomalies_detected": anomalies_detected,
        "outbreak_signals": outbreak_signals,
        "details": points,
    }