import math
from typing import Optional


def calculate_stockout_days(
    current_stock: int,
    forecast: list[float],
) -> Optional[int]:
    """Calculates the exact number of days until inventory hits zero based on forecasted demand."""
    if current_stock < 0:
        raise ValueError("Current stock cannot be negative.")

    if current_stock == 0:
        return 0

    cumulative_demand = 0.0

    for day, predicted_demand in enumerate(forecast, start=1):
        if predicted_demand < 0:
            raise ValueError("Predicted demand cannot be negative.")

        cumulative_demand += predicted_demand

        if cumulative_demand >= current_stock:
            return day

    return None


def calculate_shortage_risk(
    stockout_days: Optional[int],
    lead_time_days: int,
) -> str:
    """Classifies shortage risk level based on stockout velocity vs supplier replenishment lead time."""
    if lead_time_days < 0:
        raise ValueError("Lead time cannot be negative.")

    if stockout_days is None:
        return "LOW"

    if stockout_days == 0:
        return "CRITICAL"

    if stockout_days <= lead_time_days:
        return "HIGH"

    if stockout_days <= lead_time_days + 3:
        return "MEDIUM"

    return "LOW"


def calculate_safety_stock(
    forecast: list[float],
    lead_time_days: int,
    service_level_z: float = 1.65,  # ~95% service level
) -> int:
    """Computes dynamic safety buffer to mitigate demand volatility during replenishment lead times."""
    if not forecast or lead_time_days <= 0:
        return 0

    std_dev = float(math.sqrt(sum((x - (sum(forecast) / len(forecast))) ** 2 for x in forecast) / max(1, len(forecast) - 1)))
    safety_stock = service_level_z * std_dev * math.sqrt(lead_time_days)
    return int(math.ceil(safety_stock))


def calculate_suggested_reorder(
    current_stock: int,
    forecast: list[float],
    lead_time_days: int,
    target_coverage_days: int = 14,
) -> tuple[int, str]:
    """Calculates suggested order quantity and order urgency."""
    avg_daily = sum(forecast) / max(1, len(forecast))
    safety_stock = calculate_safety_stock(forecast, lead_time_days)
    target_stock = int(math.ceil(avg_daily * (lead_time_days + target_coverage_days) + safety_stock))

    shortfall = max(0, target_stock - current_stock)

    stockout = calculate_stockout_days(current_stock, forecast)
    risk = calculate_shortage_risk(stockout, lead_time_days)

    if risk == "CRITICAL" or (stockout is not None and stockout <= 1):
        urgency = "EMERGENCY_EXPEDITE"
    elif risk == "HIGH":
        urgency = "URGENT"
    elif risk == "MEDIUM":
        urgency = "ROUTINE_HIGH"
    else:
        urgency = "ROUTINE"

    return shortfall, urgency