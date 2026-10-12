import pandas as pd

from dashboard.geo_redistribution import (
    build_redistribution_recommendations,
    haversine_km,
    prepare_geo_snapshot,
    summarize_hospitals,
)


def sample_frames():
    supply = pd.DataFrame([
        {"date": "2026-01-01", "hospital_id": "H01", "medicine_id": "M01", "medicine_name": "Demo medicine", "current_stock": 600, "daily_demand": 10,
            "expiry_date": "2026-01-15", "patient_load": 100, "emergency_demand": 0, "outbreak_signal": 0, "supplier_lead_time_days": 7},
        {"date": "2026-01-01", "hospital_id": "H01", "medicine_id": "M01", "medicine_name": "Demo medicine", "current_stock": 400, "daily_demand": 10,
            "expiry_date": "2026-02-01", "patient_load": 100, "emergency_demand": 0, "outbreak_signal": 0, "supplier_lead_time_days": 7},
        {"date": "2026-01-01", "hospital_id": "H02", "medicine_id": "M01", "medicine_name": "Demo medicine", "current_stock": 0, "daily_demand": 20,
            "expiry_date": "2026-04-01", "patient_load": 250, "emergency_demand": 2, "outbreak_signal": 1, "supplier_lead_time_days": 7},
        {"date": "2026-01-01", "hospital_id": "H03", "medicine_id": "M01", "medicine_name": "Demo medicine", "current_stock": 0, "daily_demand": 5,
            "expiry_date": "2026-04-01", "patient_load": 100, "emergency_demand": 0, "outbreak_signal": 0, "supplier_lead_time_days": 7},
        {"date": "2026-01-01", "hospital_id": "H04", "medicine_id": "M01", "medicine_name": "Demo medicine", "current_stock": 800, "daily_demand": 10,
            "expiry_date": "2026-04-01", "patient_load": 100, "emergency_demand": 0, "outbreak_signal": 0, "supplier_lead_time_days": 7},
    ])
    locations = pd.DataFrame([
        {"hospital_id": "H01", "hospital_name": "Hospital 01",
            "city": "Mangaluru", "latitude": 12.9141, "longitude": 74.8560},
        {"hospital_id": "H02", "hospital_name": "Hospital 02",
            "city": "Udupi", "latitude": 13.3409, "longitude": 74.7421},
        {"hospital_id": "H03", "hospital_name": "Hospital 03",
            "city": "Manipal", "latitude": 13.3528, "longitude": 74.7921},
        {"hospital_id": "H04", "hospital_name": "Hospital 04",
            "city": "Kundapura", "latitude": 13.6291, "longitude": 74.6902},
        {"hospital_id": "H05", "hospital_name": "Hospital 05",
            "city": "No snapshot", "latitude": None, "longitude": None},
    ])
    return supply, locations


def test_recommendations_respect_surplus_shortage_and_unique_pairs():
    supply, locations = sample_frames()
    snapshot, cleaned_locations, snapshot_date = prepare_geo_snapshot(
        supply, locations)
    snapshot.attrs["snapshot_date"] = snapshot_date

    source = snapshot.loc[snapshot["hospital_id"].eq("H01")].iloc[0]
    assert source["current_stock"] == 1000
    assert source["daily_demand"] == 10

    recommendations = build_redistribution_recommendations(
        snapshot, cleaned_locations)
    assert not recommendations.empty
    assert not recommendations.duplicated(
        ["source_hospital_id", "destination_hospital_id", "medicine_id"]
    ).any()
    assert recommendations["quantity"].gt(0).all()
    assert recommendations.groupby("source_hospital_id")[
        "quantity"].sum()["H01"] <= 970

    for destination, routes in recommendations.groupby("destination_hospital_id"):
        row = snapshot.loc[snapshot["hospital_id"].eq(destination)].iloc[0]
        target_stock = row["daily_demand"] * 10
        shortage = max(0, target_stock - row["current_stock"])
        assert routes["quantity"].sum() <= shortage


def test_recommendations_use_geo_and_actual_explanation_values():
    supply, locations = sample_frames()
    snapshot, cleaned_locations, snapshot_date = prepare_geo_snapshot(
        supply, locations)
    snapshot.attrs["snapshot_date"] = snapshot_date
    recommendations = build_redistribution_recommendations(
        snapshot, cleaned_locations)

    urgent = recommendations.loc[recommendations["destination_hospital_id"].eq(
        "H02")].iloc[0]
    expected_distance = haversine_km(12.9141, 74.8560, 13.3409, 74.7421)
    assert abs(urgent["distance_km"] - expected_distance) < 0.01
    assert abs(urgent["eta_minutes"] - expected_distance / 35 * 60) < 0.01
    assert "Emergency demand" in urgent["reason"]
    assert "outbreak signal" in urgent["reason"]
    assert "14 days" in urgent["reason"]


def test_missing_coordinates_are_skipped_and_location_only_hospital_is_not_critical():
    supply, locations = sample_frames()
    snapshot, cleaned_locations, _ = prepare_geo_snapshot(supply, locations)
    recommendations = build_redistribution_recommendations(
        snapshot, cleaned_locations)
    hospitals = summarize_hospitals(snapshot, cleaned_locations)

    assert "H05" not in set(recommendations["source_hospital_id"])
    assert "H05" not in set(recommendations["destination_hospital_id"])
    assert hospitals.loc[hospitals["hospital_id"].eq(
        "H05"), "status"].item() == "No supply data"


def test_all_medicines_map_status_uses_worst_medicine_at_each_hospital():
    supply, locations = sample_frames()
    supply.loc[len(supply)] = {
        "date": "2026-01-01",
        "hospital_id": "H01",
        "medicine_id": "M02",
        "medicine_name": "Second medicine",
        "current_stock": 0,
        "daily_demand": 20,
        "expiry_date": "2026-04-01",
        "patient_load": 100,
        "emergency_demand": 0,
        "outbreak_signal": 0,
        "supplier_lead_time_days": 7,
    }
    snapshot, cleaned_locations, _ = prepare_geo_snapshot(supply, locations)

    all_medicines = summarize_hospitals(
        snapshot, cleaned_locations, "All Medicines")
    one_medicine = summarize_hospitals(
        snapshot, cleaned_locations, "Demo medicine")
    assert all_medicines.loc[all_medicines["hospital_id"].eq(
        "H01"), "status"].item() == "Critical shortage"
    assert one_medicine.loc[one_medicine["hospital_id"].eq(
        "H01"), "status"].item() == "Sufficient / excess"


def test_empty_inventory_produces_no_recommendations():
    _, locations = sample_frames()
    recommendations = build_redistribution_recommendations(
        pd.DataFrame(), locations)
    assert recommendations.empty
