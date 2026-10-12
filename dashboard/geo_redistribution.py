"""Read-only geo-redistribution analysis for the synthetic dashboard dataset."""

from math import floor, radians, sin, cos, asin, sqrt
from pathlib import Path
from typing import Optional

import pandas as pd


REPO_ROOT = Path(__file__).resolve().parent.parent
AVERAGE_SPEED_KMPH = 35.0
DEFAULT_SAFETY_DAYS = 3.0
DEFAULT_COVERAGE_DAYS = 7.0
MAX_COVERAGE_DAYS = 14.0
NEAR_EXPIRY_DAYS = 30


def _find_column(frame: pd.DataFrame, candidates: tuple[str, ...]) -> Optional[str]:
    columns = {str(column).strip().lower(): column for column in frame.columns}
    return next((columns[name] for name in candidates if name in columns), None)


def _number_column(frame: pd.DataFrame, column: Optional[str]) -> pd.Series:
    if column is None:
        return pd.Series(0.0, index=frame.index)
    return pd.to_numeric(frame[column], errors="coerce").fillna(0).clip(lower=0)


def prepare_geo_snapshot(
    supply: pd.DataFrame,
    locations: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, Optional[str]]:
    """Aggregate latest hospital/medicine values and join demo locations separately."""
    hospital_col = _find_column(supply, ("hospital_id", "hospital"))
    medicine_name_col = _find_column(
        supply, ("medicine_name", "medicine", "item_name"))
    stock_col = _find_column(
        supply, ("current_stock", "stock", "quantity", "available_quantity"))
    if hospital_col is None or medicine_name_col is None or stock_col is None:
        return pd.DataFrame(), locations.copy(), None

    data = supply.copy()
    data["hospital_id"] = data[hospital_col].astype("string").str.strip()
    data["medicine_name"] = data[medicine_name_col].astype(
        "string").str.strip()
    medicine_id_col = _find_column(data, ("medicine_id", "item_id"))
    data["medicine_id"] = (
        data[medicine_id_col].astype("string").str.strip()
        if medicine_id_col is not None
        else data["medicine_name"]
    )

    date_col = _find_column(data, ("date", "snapshot_date", "recorded_at"))
    snapshot_date = None
    if date_col is not None:
        data[date_col] = pd.to_datetime(data[date_col], errors="coerce")
        if data[date_col].notna().any():
            latest_date = data[date_col].max()
            data = data[data[date_col].eq(latest_date)].copy()
            snapshot_date = latest_date.date().isoformat()

    data["current_stock"] = _number_column(data, stock_col)
    demand_col = _find_column(
        data, ("daily_demand", "predicted_daily_demand", "demand"))
    data["daily_demand"] = _number_column(data, demand_col)
    emergency_col = _find_column(
        data, ("emergency_demand", "emergency_cases", "emergency"))
    data["emergency_demand"] = _number_column(data, emergency_col)
    patient_col = _find_column(data, ("patient_load", "patient_count"))
    data["patient_load"] = _number_column(data, patient_col)
    outbreak_col = _find_column(data, ("outbreak_signal", "outbreak"))
    data["outbreak_signal"] = _number_column(data, outbreak_col)
    lead_col = _find_column(
        data, ("supplier_lead_time_days", "lead_time_days", "lead_days"))
    data["supplier_lead_time_days"] = _number_column(data, lead_col)

    expiry_col = _find_column(data, ("expiry_date", "expiry"))
    if expiry_col is None:
        data["expiry_date"] = pd.NaT
    else:
        data["expiry_date"] = pd.to_datetime(data[expiry_col], errors="coerce")

    # Stock is additive across duplicate batch-like rows; repeated demand signals are averaged.
    grouped = data.groupby(
        ["hospital_id", "medicine_id", "medicine_name"], dropna=True, as_index=False
    ).agg(
        current_stock=("current_stock", "sum"),
        daily_demand=("daily_demand", "mean"),
        emergency_demand=("emergency_demand", "max"),
        patient_load=("patient_load", "max"),
        outbreak_signal=("outbreak_signal", "max"),
        supplier_lead_time_days=("supplier_lead_time_days", "max"),
    )

    if expiry_col is not None:
        expiring = data.loc[data["current_stock"].gt(
            0) & data["expiry_date"].notna()]
        expiry_by_item = expiring.groupby(
            ["hospital_id", "medicine_id", "medicine_name"], as_index=False
        )["expiry_date"].min()
        grouped = grouped.merge(
            expiry_by_item,
            on=["hospital_id", "medicine_id", "medicine_name"],
            how="left",
        )
    else:
        grouped["expiry_date"] = pd.NaT
    grouped.attrs["snapshot_date"] = snapshot_date

    location_data = locations.copy()
    location_hospital_col = _find_column(
        location_data, ("hospital_id", "hospital"))
    if location_hospital_col is None:
        return grouped, pd.DataFrame(), snapshot_date
    location_data["hospital_id"] = location_data[location_hospital_col].astype(
        "string").str.strip()
    name_col = _find_column(location_data, ("hospital_name", "name"))
    city_col = _find_column(location_data, ("city", "place", "location"))
    lat_col = _find_column(location_data, ("latitude", "lat"))
    lon_col = _find_column(location_data, ("longitude", "lon", "lng"))
    location_data["hospital_name"] = location_data[name_col].astype(
        "string") if name_col else location_data["hospital_id"]
    location_data["city"] = location_data[city_col].astype(
        "string") if city_col else pd.NA
    location_data["hospital_name"] = location_data["hospital_name"].fillna(
        location_data["hospital_id"]
    )
    location_data["hospital_name"] = location_data["hospital_name"].where(
        location_data["hospital_name"].ne(""), location_data["hospital_id"]
    )
    location_data["city"] = location_data["city"].fillna("Place unavailable")
    location_data["city"] = location_data["city"].where(
        location_data["city"].ne(""), "Place unavailable"
    )
    location_data["latitude"] = pd.to_numeric(
        location_data[lat_col], errors="coerce") if lat_col else float("nan")
    location_data["longitude"] = pd.to_numeric(
        location_data[lon_col], errors="coerce") if lon_col else float("nan")
    valid_coordinates = (
        location_data["latitude"].between(-90, 90)
        & location_data["longitude"].between(-180, 180)
    )
    location_data.loc[~valid_coordinates, [
        "latitude", "longitude"]] = float("nan")
    location_data = location_data.dropna(subset=["hospital_id"])
    location_data = location_data.drop_duplicates("hospital_id", keep="first")
    location_data = location_data[[
        "hospital_id", "hospital_name", "city", "latitude", "longitude"]]
    return grouped, location_data, snapshot_date


def load_geo_snapshot(
    supply_path: Optional[Path] = None,
    locations_path: Optional[Path] = None,
) -> tuple[pd.DataFrame, pd.DataFrame, Optional[str]]:
    """Load the supplied synthetic CSVs without modifying the source dataset."""
    supply_file = supply_path or REPO_ROOT / \
        "data" / "medical_supply_20_medicines.csv"
    locations_file = locations_path or REPO_ROOT / "hospital_locations.csv"
    if not supply_file.exists() or not locations_file.exists():
        return pd.DataFrame(), pd.DataFrame(), None
    try:
        supply = pd.read_csv(supply_file)
        locations = pd.read_csv(locations_file)
    except (OSError, UnicodeDecodeError, pd.errors.ParserError):
        return pd.DataFrame(), pd.DataFrame(), None
    return prepare_geo_snapshot(supply, locations)


def haversine_km(lat_a: float, lon_a: float, lat_b: float, lon_b: float) -> float:
    """Return the great-circle distance between two coordinates in kilometres."""
    lat_a_rad, lat_b_rad = radians(lat_a), radians(lat_b)
    delta_lat = lat_b_rad - lat_a_rad
    delta_lon = radians(lon_b - lon_a)
    haversine = sin(delta_lat / 2) ** 2 + cos(lat_a_rad) * \
        cos(lat_b_rad) * sin(delta_lon / 2) ** 2
    return 6371.0 * 2 * asin(sqrt(min(1.0, haversine)))


def hospital_stock_status(stock: float, demand: float) -> str:
    if stock <= 0 or (demand > 0 and stock / demand <= DEFAULT_SAFETY_DAYS):
        return "Critical shortage"
    if demand > 0 and stock / demand < DEFAULT_COVERAGE_DAYS:
        return "Low stock"
    return "Sufficient / excess"


def build_redistribution_recommendations(
    snapshot: pd.DataFrame,
    locations: pd.DataFrame,
    average_speed_kmph: float = AVERAGE_SPEED_KMPH,
) -> pd.DataFrame:
    """Rank feasible transfers and allocate without reusing donor surplus or recipient need."""
    columns = [
        "source_hospital_id", "source_hospital_name", "source_city", "destination_hospital_id",
        "destination_hospital_name", "destination_city", "medicine_id", "medicine_name",
        "quantity", "source_excess", "destination_shortage", "distance_km", "eta_minutes",
        "score", "reason", "snapshot_date",
    ]
    if snapshot.empty or locations.empty or average_speed_kmph <= 0:
        return pd.DataFrame(columns=columns)

    valid_locations = locations.dropna(subset=["latitude", "longitude"]).copy()
    if valid_locations.empty:
        return pd.DataFrame(columns=columns)
    located = snapshot.merge(valid_locations, on="hospital_id", how="inner")
    if located.empty:
        return pd.DataFrame(columns=columns)
    snapshot_date = snapshot.attrs.get("snapshot_date")

    transfers = []
    keys = ["medicine_id", "medicine_name"]
    for (medicine_id, medicine_name), medicine_rows in located.groupby(keys, dropna=True):
        item = medicine_rows.copy()
        item["target_days"] = (
            item["supplier_lead_time_days"].clip(
                lower=DEFAULT_COVERAGE_DAYS, upper=MAX_COVERAGE_DAYS)
            + 3.0
        ).clip(upper=MAX_COVERAGE_DAYS)
        item["target_stock"] = item["daily_demand"] * item["target_days"]
        item["surplus"] = (item["current_stock"] - item["daily_demand"]
                           * DEFAULT_SAFETY_DAYS).clip(lower=0)
        item["shortage"] = (item["target_stock"] -
                            item["current_stock"]).clip(lower=0)
        item["demand_percentile"] = (
            0.70 * item["daily_demand"].rank(pct=True)
            + 0.30 * item["patient_load"].rank(pct=True)
        )
        sources = item[item["surplus"] >= 1].copy()
        destinations = item[item["shortage"] >= 1].copy()
        if sources.empty or destinations.empty:
            continue

        for destination in destinations.to_dict("records"):
            for source in sources.to_dict("records"):
                if source["hospital_id"] == destination["hospital_id"]:
                    continue
                distance = haversine_km(
                    float(source["latitude"]), float(source["longitude"]),
                    float(destination["latitude"]), float(
                        destination["longitude"]),
                )
                source_expiry = source.get("expiry_date")
                expiry_days = None
                if snapshot_date and pd.notna(source_expiry):
                    expiry_days = (pd.Timestamp(source_expiry).date(
                    ) - pd.Timestamp(snapshot_date).date()).days
                near_expiry = expiry_days is not None and 0 <= expiry_days <= NEAR_EXPIRY_DAYS
                emergency = float(destination.get("emergency_demand", 0)) > 0
                outbreak = float(destination.get("outbreak_signal", 0)) > 0
                target = max(float(destination["target_stock"]), 1.0)
                shortage_priority = min(
                    float(destination["shortage"]) / target, 1.0)
                demand_priority = float(destination["demand_percentile"])
                emergency_priority = min(
                    float(destination.get("emergency_demand", 0))
                    / max(float(destination["daily_demand"]), 1.0),
                    1.0,
                )
                outbreak_priority = 1.0 if outbreak else 0.0
                pressure_priority = max(emergency_priority, outbreak_priority)
                expiry_priority = 1.0 if near_expiry else 0.0
                proximity_priority = max(0.0, 1.0 - distance / 250.0)
                score = (
                    0.30 * shortage_priority
                    + 0.20 * demand_priority
                    + 0.20 * pressure_priority
                    + 0.10 * expiry_priority
                    + 0.20 * proximity_priority
                )
                transfers.append({
                    "source_hospital_id": source["hospital_id"],
                    "source_hospital_name": source["hospital_name"],
                    "source_city": source["city"],
                    "destination_hospital_id": destination["hospital_id"],
                    "destination_hospital_name": destination["hospital_name"],
                    "destination_city": destination["city"],
                    "medicine_id": medicine_id,
                    "medicine_name": medicine_name,
                    "source_excess": float(source["surplus"]),
                    "destination_shortage": float(destination["shortage"]),
                    "source_stock": float(source["current_stock"]),
                    "destination_stock": float(destination["current_stock"]),
                    "destination_demand": float(destination["daily_demand"]),
                    "destination_patient_load": float(destination.get("patient_load", 0)),
                    "emergency_demand": float(destination.get("emergency_demand", 0)),
                    "outbreak_signal": float(destination.get("outbreak_signal", 0)),
                    "emergency": emergency,
                    "outbreak": outbreak,
                    "expiry_days": expiry_days,
                    "near_expiry": near_expiry,
                    "distance_km": distance,
                    "eta_minutes": distance / average_speed_kmph * 60.0,
                    "score": score,
                    "snapshot_date": snapshot_date,
                })

    if not transfers:
        return pd.DataFrame(columns=columns)

    # A single ranked pass prevents separate routes from spending the same surplus or need twice.
    transfers.sort(key=lambda row: (-row["score"], row["distance_km"],
                   row["source_hospital_id"], row["destination_hospital_id"]))
    source_left = {}
    destination_left = {}
    allocations = []
    seen = set()
    for candidate in transfers:
        item_key = (candidate["medicine_id"], candidate["medicine_name"])
        source_key = (*item_key, candidate["source_hospital_id"])
        destination_key = (*item_key, candidate["destination_hospital_id"])
        pair_key = (
            *item_key, candidate["source_hospital_id"], candidate["destination_hospital_id"])
        if pair_key in seen:
            continue
        seen.add(pair_key)
        source_left.setdefault(source_key, candidate["source_excess"])
        destination_left.setdefault(
            destination_key, candidate["destination_shortage"])
        quantity = min(floor(source_left[source_key]), floor(
            destination_left[destination_key]))
        if quantity <= 0:
            continue
        source_left[source_key] -= quantity
        destination_left[destination_key] -= quantity

        reasons = [
            f"{candidate['destination_hospital_id']} is {hospital_stock_status(candidate['destination_stock'], candidate['destination_demand']).lower()} with {candidate['destination_stock']:g} units for {candidate['destination_demand']:g} units of daily demand.",
            f"{candidate['source_hospital_id']} has {candidate['source_excess']:g} units above its {DEFAULT_SAFETY_DAYS:g}-day reserve.",
        ]
        if candidate["destination_patient_load"] > 0:
            reasons.append(
                f"Destination patient load is {candidate['destination_patient_load']:g}.")
        if candidate["emergency"]:
            reasons.append(
                f"Emergency demand is {candidate['emergency_demand']:g} units at the destination.")
        if candidate["outbreak"]:
            reasons.append(
                f"The destination outbreak signal is {candidate['outbreak_signal']:g}.")
        if candidate["near_expiry"]:
            reasons.append(
                f"The source has stock with an expiry date {candidate['expiry_days']} days after the snapshot.")
        reasons.append(
            f"The demo coordinates place the hospitals {candidate['distance_km']:.1f} km apart, "
            f"about {candidate['eta_minutes']:.0f} minutes at {average_speed_kmph:g} km/h."
        )
        allocations.append({
            **candidate,
            "quantity": quantity,
            "reason": " ".join(reasons),
        })

    if not allocations:
        return pd.DataFrame(columns=columns)
    result = pd.DataFrame(allocations)
    return result[columns].drop_duplicates(
        ["source_hospital_id", "destination_hospital_id",
            "medicine_id", "medicine_name"]
    ).reset_index(drop=True)


def summarize_hospitals(snapshot: pd.DataFrame, locations: pd.DataFrame, medicine_name: Optional[str] = None) -> pd.DataFrame:
    """Build per-hospital map totals, including location-only hospitals with unknown stock."""
    if locations.empty:
        return pd.DataFrame()
    rows = snapshot
    if medicine_name and medicine_name != "All Medicines":
        rows = rows[rows["medicine_name"].eq(medicine_name)]
    totals = rows.groupby("hospital_id", as_index=False).agg(
        current_stock=("current_stock", "sum"), daily_demand=("daily_demand", "sum")
    )
    hospitals = locations.merge(totals, on="hospital_id", how="left")
    hospitals["has_supply_data"] = hospitals["current_stock"].notna()
    hospitals[["current_stock", "daily_demand"]] = hospitals[[
        "current_stock", "daily_demand"]].fillna(0)
    if medicine_name is None or medicine_name == "All Medicines":
        severity = {"Sufficient / excess": 0,
                    "Low stock": 1, "Critical shortage": 2}
        item_status = rows.copy()
        item_status["status"] = item_status.apply(
            lambda row: hospital_stock_status(
                row["current_stock"], row["daily_demand"]),
            axis=1,
        )
        worst_status = item_status.groupby("hospital_id")["status"].agg(
            lambda statuses: max(statuses, key=lambda status: severity[status])
        )
        hospitals = hospitals.merge(
            worst_status.rename("status"), on="hospital_id", how="left"
        )
        hospitals["status"] = hospitals["status"].fillna("No supply data")
    else:
        hospitals["status"] = hospitals.apply(
            lambda row: hospital_stock_status(
                row["current_stock"], row["daily_demand"])
            if row["has_supply_data"] else "No supply data",
            axis=1,
        )
    return hospitals
