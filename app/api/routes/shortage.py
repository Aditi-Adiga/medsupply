from fastapi import APIRouter, HTTPException, Query, Depends
from app.api.routes.operations import current_user, DB
from app.services.auth import allowed
from app.services.alerts import assess

from app.schemas.shortage import (
    MedicineShortageSummary,
    ShortageRiskRequest,
    ShortageRiskResponse,
)
from app.services.shortage_service import (
    analyze_shortage_risk,
)


router = APIRouter()


@router.post(
    "/shortage-risk",
    response_model=ShortageRiskResponse,
    summary="Calculate shortage risk and stockout days",
    description="Analyzes inventory levels vs lead time and forecasted demand to project exact stockout day and risk grade.",
)
def shortage_risk_endpoint(
    request: ShortageRiskRequest,
    user=Depends(current_user),
):
    allowed(user, request.hospital_id)
    try:
        result = analyze_shortage_risk(
            current_stock=request.current_stock,
            lead_time_days=request.lead_time_days,
            forecast=request.forecast,
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        )

    return ShortageRiskResponse(
        hospital_id=request.hospital_id,
        medicine_id=request.medicine_id,
        current_stock=request.current_stock,
        lead_time_days=request.lead_time_days,
        stockout_in_days=result["stockout_in_days"],
        shortage_risk=result["shortage_risk"],
        safety_stock_recommended=result.get("safety_stock_recommended", 0),
        suggested_reorder_qty=result.get("suggested_reorder_qty", 0),
        reorder_urgency=result.get("reorder_urgency", "NORMAL"),
        action_recommendation=result.get("action_recommendation", ""),
    )


@router.get(
    "/shortage-risk/overview",
    response_model=list[MedicineShortageSummary],
    summary="Hospital-wide shortage risk overview",
    description="Scans inventory and lead times across all medicines to flag critical stockouts.",
)
def get_hospital_inventory_overview(
    db: DB,
    hospital_id: str = Query(default="H01", description="Hospital ID (e.g. H01)"),
    user=Depends(current_user),
):
    allowed(user, hospital_id)
    values = assess(db, user.hospital_id)
    return [MedicineShortageSummary(hospital_id=user.hospital_id, medicine_id=v["medicine_id"],
        medicine_name=v["medicine_id"], current_stock=v["usable_quantity"], daily_consumption_avg=0,
        stockout_in_days=v["stockout_in_days"], shortage_risk=v["severity"], recommended_order=0)
        for v in values if "stockout_in_days" in v]
