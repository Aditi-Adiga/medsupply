from fastapi import APIRouter, HTTPException, Depends
from app.api.routes.operations import current_user
from app.services.auth import allowed

from app.schemas.demand import (
    AnomalyDetectionRequest,
    AnomalyDetectionResponse,
    DemandForecastRequest,
    DemandForecastResponse,
)
from app.services.demand_service import (
    get_demand_forecast,
    load_hospital_medicine_data,
)
from app.services.anomaly_service import get_anomaly_summary


router = APIRouter()


@router.post(
    "/demand/forecast",
    response_model=DemandForecastResponse,
    summary="Predict future medical demand",
    description="Forecasts multi-day future consumption using machine learning with confidence bounds.",
)
def forecast_demand_endpoint(
    request: DemandForecastRequest,
    user=Depends(current_user),
):
    allowed(user, request.hospital_id)
    try:
        # Load historical consumption series for the specified hospital & medicine
        history_df = load_hospital_medicine_data(
            hospital_id=request.hospital_id,
            medicine_id=request.medicine_id,
        )

        result = get_demand_forecast(
            data=history_df,
            horizon_days=request.horizon_days,
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        )

    return DemandForecastResponse(
        hospital_id=request.hospital_id,
        medicine_id=request.medicine_id,
        horizon_days=request.horizon_days,
        forecast=result["forecast"],
        daily_average=result.get("daily_average"),
        confidence_interval_lower=result.get("lower_bound"),
        confidence_interval_upper=result.get("upper_bound"),
        model_used=result.get("model_name", "ML Regressor Ensemble"),
    )


@router.post(
    "/demand/anomalies",
    response_model=AnomalyDetectionResponse,
    summary="Detect demand spikes and outbreak signals",
    description="Performs statistical anomaly and surge analysis on consumption history.",
)
def detect_anomalies_endpoint(
    request: AnomalyDetectionRequest,
    user=Depends(current_user),
):
    allowed(user, request.hospital_id)
    try:
        summary = get_anomaly_summary(
            hospital_id=request.hospital_id,
            medicine_id=request.medicine_id,
            threshold=request.threshold,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        )

    return AnomalyDetectionResponse(**summary)
