# Dashboard Module

This module houses the interactive **Medical Supply Intelligence Dashboard** (e.g., Streamlit application) designed for hospital supply chain managers and network coordinators.

## Planned Views & Features

1. **Executive Overview**:
   - Total network inventory, active critical alerts, near-term shortage count, and wastage risk summary.
2. **Inventory & Demand Forecasts**:
   - Interactive charts of historical vs. predicted demand across hospitals and item categories.
   - Days-of-supply remaining per item.
3. **Shortage & Expiry Risk Tracker**:
   - Ranked list of high-risk items and facilities with real-time risk indicators and countdowns to stockout/expiry.
4. **Redistribution Action Center**:
   - Interactive recommendation cards displaying suggested hospital-to-hospital transfers with accept/reject or export options.
   - Network transfer map / distance matrix visualization.

## Running the Dashboard

Once the application code is added, run:
```bash
python -m streamlit run dashboard/dashboard_app.py
```
*(or the designated dashboard entry point)*

## Objective 3: Smart Geo-Redistribution

The authenticated dashboard includes a read-only map and transfer recommendations based on the latest dated rows in `data/medical_supply_20_medicines.csv`, joined separately to `hospital_locations.csv` by `hospital_id`. The files contain synthetic demo data and locations; this view is not live stock, does not create requests, and does not change inventory. It reports straight-line Haversine distance and estimated travel time at the selected average speed, not a road route or traffic prediction. Install `requirements.txt` to enable the Folium map.
