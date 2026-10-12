from app.utils.calculations import (
    calculate_safety_stock,
    calculate_shortage_risk,
    calculate_stockout_days,
    calculate_suggested_reorder,
)
from app.services.shortage_service import analyze_shortage_risk


def test_stockout_calculation():
    forecast = [100, 100, 100, 100, 100]
    result = calculate_stockout_days(
        current_stock=350,
        forecast=forecast,
    )
    assert result == 4


def test_stockout_immediate_zero():
    forecast = [50, 50, 50]
    result = calculate_stockout_days(
        current_stock=0,
        forecast=forecast,
    )
    assert result == 0


def test_shortage_risk_levels():
    assert calculate_shortage_risk(stockout_days=0, lead_time_days=7) == "CRITICAL"
    assert calculate_shortage_risk(stockout_days=5, lead_time_days=7) == "HIGH"
    assert calculate_shortage_risk(stockout_days=9, lead_time_days=7) == "MEDIUM"
    assert calculate_shortage_risk(stockout_days=20, lead_time_days=7) == "LOW"
    assert calculate_shortage_risk(stockout_days=None, lead_time_days=7) == "LOW"


def test_safety_stock_and_reorder():
    forecast = [40.0, 45.0, 50.0, 55.0, 60.0]
    safety_stock = calculate_safety_stock(forecast, lead_time_days=7)
    assert safety_stock > 0

    reorder_qty, urgency = calculate_suggested_reorder(
        current_stock=50,
        forecast=forecast,
        lead_time_days=7,
    )
    assert reorder_qty > 0
    assert urgency in ["EMERGENCY_EXPEDITE", "URGENT", "ROUTINE_HIGH", "ROUTINE"]


def test_analyze_shortage_risk_service():
    res = analyze_shortage_risk(
        current_stock=150,
        lead_time_days=5,
        forecast=[50.0, 50.0, 50.0, 50.0, 50.0],
    )
    assert res["stockout_in_days"] == 3
    assert res["shortage_risk"] == "HIGH"
    assert res["reorder_urgency"] == "URGENT"
    assert "HIGH RISK" in res["action_recommendation"]