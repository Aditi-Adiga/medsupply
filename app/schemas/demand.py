from datetime import date
from typing import Union
from pydantic import BaseModel, Field


class DemandRecord(BaseModel):
    hospital_id: Union[str, int]
    medicine_id: Union[str, int]
    date: date
    units_consumed: int = Field(ge=0)


class DemandForecastRequest(BaseModel):
    hospital_id: Union[str, int] = Field(default="H01", description="Hospital identifier (e.g., 'H01' or 1)")
    medicine_id: Union[str, int] = Field(default="M01", description="Medicine identifier (e.g., 'M01' or 1)")
    horizon_days: int = Field(
        default=7,
        ge=1,
        le=30,
        description="Forecast horizon in days (1 to 30)",
    )


class DemandForecastResponse(BaseModel):
    hospital_id: Union[str, int]
    medicine_id: Union[str, int]
    horizon_days: int
    forecast: list[float]
    daily_average: float | None = None
    confidence_interval_lower: list[float] | None = None
    confidence_interval_upper: list[float] | None = None
    model_used: str = "XGBoost + Rolling Horizon Ensemble"


class AnomalyDetectionRequest(BaseModel):
    hospital_id: Union[str, int] = Field(default="H01")
    medicine_id: Union[str, int] = Field(default="M01")
    threshold: float = Field(default=2.0, ge=1.0, le=5.0)


class AnomalyPoint(BaseModel):
    date: str
    units_consumed: float
    z_score: float
    is_anomaly: bool
    is_outbreak_spike: bool


class AnomalyDetectionResponse(BaseModel):
    hospital_id: Union[str, int]
    medicine_id: Union[str, int]
    total_records: int
    anomalies_detected: int
    outbreak_signals: int
    details: list[AnomalyPoint]