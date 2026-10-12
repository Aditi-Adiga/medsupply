from app.utils.calculations import (
    calculate_safety_stock,
    calculate_shortage_risk,
    calculate_stockout_days,
    calculate_suggested_reorder,
)


def analyze_shortage_risk(
    current_stock: int,
    lead_time_days: int,
    forecast: list[float],
) -> dict:
    """Evaluates comprehensive inventory risk, replenishment urgency, and clinical stockout projections."""
    stockout_days = calculate_stockout_days(
        current_stock=current_stock,
        forecast=forecast,
    )

    risk = calculate_shortage_risk(
        stockout_days=stockout_days,
        lead_time_days=lead_time_days,
    )
    forecast_limited = len(forecast) < lead_time_days + 3
    if forecast_limited and risk == "LOW":
        risk = "MEDIUM"

    safety_stock = calculate_safety_stock(
        forecast=forecast,
        lead_time_days=lead_time_days,
    )

    reorder_qty, urgency = calculate_suggested_reorder(
        current_stock=current_stock,
        forecast=forecast,
        lead_time_days=lead_time_days,
    )

    # Build actionable clinical decision recommendation
    if risk == "CRITICAL" or stockout_days == 0:
        recommendation = (
            f"CRITICAL ALERT: Stock is exhausted. Trigger emergency mutual-aid transfer "
            f"or overnight expedite order of {reorder_qty} units immediately."
        )
    elif risk == "HIGH":
        recommendation = (
            f"HIGH RISK: Stockout expected in {stockout_days} days, before supplier lead time ({lead_time_days} days). "
            f"Dispatch priority purchase order of {reorder_qty} units immediately to prevent supply interruption."
        )
    elif risk == "MEDIUM" and stockout_days is None:
        recommendation = "Supply risk is uncertain. Extend the forecast before deciding that stock is safe."
    elif risk == "MEDIUM":
        recommendation = (
            f"MEDIUM CAUTION: Stockout in {stockout_days} days. Place standard restocking order of {reorder_qty} units "
            f"within 48 hours to maintain adequate buffer."
        )
    else:
        recommendation = (
            f"STABLE: Current stock buffer is sufficient. Routine reorder window active; recommended buffer is {safety_stock} units."
        )

    if forecast_limited:
        recommendation += " Forecast is too short to cover supplier lead time and the safety period. Later risk is unknown."

    return {
        "forecast_limited": forecast_limited,
        "stockout_in_days": stockout_days,
        "shortage_risk": risk,
        "safety_stock_recommended": safety_stock,
        "suggested_reorder_qty": reorder_qty,
        "reorder_urgency": urgency,
        "action_recommendation": recommendation,
    }
