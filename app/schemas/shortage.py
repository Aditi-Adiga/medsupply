from typing import Union, Optional
from pydantic import BaseModel, Field


class ShortageRiskRequest(BaseModel):
    hospital_id: Union[str, int] = Field(default="H01")
    medicine_id: Union[str, int] = Field(default="M01")
    current_stock: int = Field(default=250, ge=0, description="Current units on hand")
    lead_time_days: int = Field(default=7, ge=0, description="Supplier lead time in days")
    forecast: list[float] = Field(
        default=[40.0, 45.0, 50.0, 55.0, 60.0, 65.0, 70.0],
        description="Forecasted daily demand sequence",
    )


class ShortageRiskResponse(BaseModel):
    hospital_id: Union[str, int]
    medicine_id: Union[str, int]
    current_stock: int
    lead_time_days: int
    stockout_in_days: Optional[int]
    shortage_risk: str  # "CRITICAL", "HIGH", "MEDIUM", "LOW"
    safety_stock_recommended: int = 0
    suggested_reorder_qty: int = 0
    reorder_urgency: str = "NORMAL"
    action_recommendation: str = ""


class BulkShortageAssessmentRequest(BaseModel):
    hospital_id: Optional[Union[str, int]] = None
    risk_filter: Optional[str] = None  # All, HIGH, CRITICAL, etc.


class MedicineShortageSummary(BaseModel):
    hospital_id: str
    medicine_id: str
    medicine_name: str
    current_stock: int
    daily_consumption_avg: float
    stockout_in_days: Optional[int]
    shortage_risk: str
    recommended_order: int