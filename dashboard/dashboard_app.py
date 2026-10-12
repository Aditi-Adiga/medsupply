import pandas as pd
import qrcode
import requests
import json
import io
from dashboard.geo_redistribution import (
    AVERAGE_SPEED_KMPH,
    build_redistribution_recommendations,
    load_geo_snapshot,
    summarize_hospitals,
)
import streamlit as st
import os
import sys
import html

# Ensure repository root is in sys.path
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)


try:
    import folium
    from folium.plugins import PolyLineTextPath
    from streamlit_folium import st_folium
except ImportError:
    folium = None
    PolyLineTextPath = None
    st_folium = None

# ---------------------------------------------------------
# Page Configuration & Global Theme
# ---------------------------------------------------------
st.set_page_config(
    page_title="Medical Supply Intelligence • Control Tower",
    page_icon="🏥",
    layout="wide",
    initial_sidebar_state="expanded",
)

# High-Contrast Pure White Theme CSS Overrides
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap');
    
    /* Force Global Pure White Canvas & High-Contrast Typography */
    html, body, [class*="css"], .stApp, [data-testid="stAppViewContainer"], .main, [data-testid="stHeader"] {
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif !important;
        background-color: #FFFFFF !important;
        color: #0F172A !important;
    }
    
    .main .block-container {
        padding-top: 1.5rem !important;
        padding-bottom: 3rem !important;
        max-width: 96% !important;
        background-color: #FFFFFF !important;
    }
    
    /* Left Sidebar Styling */
    [data-testid="stSidebar"], [data-testid="stSidebar"] > div:first-child {
        background-color: #F8FAFC !important;
        border-right: 1.5px solid #E2E8F0 !important;
        color: #0F172A !important;
    }
    
    [data-testid="stSidebar"] * {
        color: #0F172A !important;
    }
    
    /* Top Header */
    .dashboard-title {
        font-size: 2.25rem;
        font-weight: 900;
        color: #0F172A !important;
        letter-spacing: -0.03em;
        margin-bottom: 0.15rem;
    }
    .dashboard-subtitle {
        font-size: 1.02rem;
        color: #475569 !important;
        font-weight: 500;
        margin-bottom: 1.3rem;
    }
    
    /* Section Headings */
    h1, h2, h3, h4, h5, h6 {
        color: #0F172A !important;
        font-weight: 800 !important;
    }
    
    /* Form Labels */
    label, [data-testid="stWidgetLabel"] p, [data-testid="stWidgetLabel"] span {
        color: #0F172A !important;
        font-weight: 700 !important;
        font-size: 0.88rem !important;
    }
    
    /* Input Boxes & Select Boxes High Contrast */
    div[data-baseweb="select"] > div,
    input, textarea, [data-testid="stTextInput"] input {
        background-color: #FFFFFF !important;
        color: #0F172A !important;
        border: 1.5px solid #CBD5E1 !important;
        border-radius: 8px !important;
        font-weight: 600 !important;
    }
    
    /* KPI Card Component */
    .kpi-card {
        background: #FFFFFF !important;
        border: 1.5px solid #E2E8F0 !important;
        border-radius: 12px;
        padding: 16px 20px;
        box-shadow: 0 2px 4px rgba(0, 0, 0, 0.04);
        margin-bottom: 12px;
        transition: transform 0.15s ease, box-shadow 0.15s ease;
    }
    .kpi-card:hover {
        transform: translateY(-2px);
        box-shadow: 0 6px 12px -2px rgba(0, 0, 0, 0.08);
    }
    .kpi-title {
        font-size: 0.74rem;
        font-weight: 800;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        color: #475569 !important;
        margin-bottom: 6px;
    }
    .kpi-value {
        font-size: 2.1rem;
        font-weight: 900;
        color: #0F172A !important;
        line-height: 1.1;
        margin-bottom: 4px;
    }
    .kpi-subtext {
        font-size: 0.8rem;
        color: #64748B !important;
        font-weight: 500;
    }
    
    /* Card Left Border Accents */
    .kpi-blue { border-left: 6px solid #2563EB !important; }
    .kpi-red { border-left: 6px solid #EF4444 !important; }
    .kpi-red .kpi-value { color: #DC2626 !important; }
    .kpi-orange { border-left: 6px solid #F59E0B !important; }
    .kpi-orange .kpi-value { color: #D97706 !important; }
    .kpi-cyan { border-left: 6px solid #0EA5E9 !important; }
    .kpi-cyan .kpi-value { color: #0284C7 !important; }
    .kpi-green { border-left: 6px solid #10B981 !important; }
    
    /* Sidebar Status Badges */
    .status-badge {
        display: inline-flex;
        align-items: center;
        gap: 6px;
        font-size: 0.82rem;
        font-weight: 600;
        padding: 7px 10px;
        border-radius: 6px;
        background: #FFFFFF !important;
        border: 1.5px solid #E2E8F0 !important;
        color: #1E293B !important;
        margin-bottom: 6px;
        width: 100%;
        justify-content: space-between;
    }
    .status-badge-ok {
        color: #16A34A !important;
        font-weight: 800;
    }
    
    /* Navigation Tabs */
    .stTabs [data-baseweb="tab-list"] {
        gap: 10px;
        border-bottom: 2px solid #E2E8F0 !important;
        margin-bottom: 1.5rem;
        background-color: transparent !important;
    }
    .stTabs [data-baseweb="tab"] {
        font-size: 0.84rem !important;
        font-weight: 800 !important;
        text-transform: uppercase;
        letter-spacing: 0.04em;
        padding: 10px 18px !important;
        color: #475569 !important;
        background-color: transparent !important;
        border: none !important;
    }
    .stTabs [aria-selected="true"] {
        color: #DC2626 !important;
        border-bottom: 3px solid #DC2626 !important;
    }
    
    /* Custom High-Contrast HTML Data Tables */
    .custom-table-container {
        width: 100%;
        overflow-x: auto;
        border: 1.5px solid #E2E8F0;
        border-radius: 10px;
        box-shadow: 0 1px 3px rgba(0,0,0,0.03);
        margin-top: 10px;
        margin-bottom: 20px;
        background: #FFFFFF;
    }
    .custom-table {
        width: 100%;
        border-collapse: collapse;
        text-align: left;
        font-size: 0.86rem;
        color: #0F172A;
    }
    .custom-table th {
        background-color: #F8FAFC;
        color: #334155;
        font-weight: 800;
        text-transform: uppercase;
        font-size: 0.75rem;
        letter-spacing: 0.05em;
        padding: 12px 14px;
        border-bottom: 2px solid #E2E8F0;
    }
    .custom-table td {
        padding: 11px 14px;
        border-bottom: 1px solid #F1F5F9;
        font-weight: 500;
        color: #0F172A;
    }
    .custom-table tr:hover {
        background-color: #F8FAFC;
    }
    
    /* High-Contrast Badges */
    .tag-critical {
        background-color: #FEE2E2;
        color: #991B1B;
        font-weight: 800;
        padding: 4px 8px;
        border-radius: 6px;
        border: 1px solid #FCA5A5;
        display: inline-block;
    }
    .tag-high {
        background-color: #FFEDD5;
        color: #9A3412;
        font-weight: 800;
        padding: 4px 8px;
        border-radius: 6px;
        border: 1px solid #FDBA74;
        display: inline-block;
    }
    .tag-medium {
        background-color: #FEF3C7;
        color: #92400E;
        font-weight: 700;
        padding: 4px 8px;
        border-radius: 6px;
        border: 1px solid #FCD34D;
        display: inline-block;
    }
    .tag-low {
        background-color: #DCFCE7;
        color: #166534;
        font-weight: 700;
        padding: 4px 8px;
        border-radius: 6px;
        border: 1px solid #86EFAC;
        display: inline-block;
    }
    
    /* Suggestion Chips in AI Assistant */
    .chip-button {
        display: inline-block;
        background: #F1F5F9;
        border: 1.5px solid #CBD5E1;
        border-radius: 20px;
        padding: 6px 14px;
        margin: 4px 6px 4px 0;
        font-size: 0.83rem;
        font-weight: 600;
        color: #1E293B;
        text-decoration: none;
        cursor: pointer;
    }
    .chip-button:hover {
        background: #E2E8F0;
        border-color: #94A3B8;
        color: #0F172A;
    }
</style>
""", unsafe_allow_html=True)


# All private data comes from the authenticated API.
API_URL = os.environ.get(
    "MSI_API_URL", "http://127.0.0.1:8000").rstrip("/") + "/api/v1"


@st.cache_data(show_spinner=False)
def cached_geo_snapshot():
    return load_geo_snapshot()


def render_geo_map(hospitals, recommendations):
    if folium is None or PolyLineTextPath is None or st_folium is None:
        st.warning(
            "Map packages are unavailable. Install the requirements listed for Objective 3 to enable the interactive map.")
        return

    mapped = hospitals.dropna(subset=["latitude", "longitude"])
    if mapped.empty:
        st.info("No hospitals have usable latitude and longitude values.")
        return

    center = [float(mapped["latitude"].mean()),
              float(mapped["longitude"].mean())]
    geo_map = folium.Map(location=center, zoom_start=7,
                         control_scale=True, tiles="CartoDB positron")
    status_colors = {
        "Sufficient / excess": "green",
        "Low stock": "orange",
        "Critical shortage": "red",
        "No supply data": "gray",
    }
    for row in mapped.to_dict("records"):
        hospital_id = html.escape(str(row["hospital_id"]))
        hospital_name = html.escape(str(row["hospital_name"]))
        city = html.escape(str(row["city"])) if pd.notna(
            row["city"]) else "Place unavailable"
        status = str(row["status"])
        popup = (
            f"<strong>{hospital_id} · {hospital_name}</strong><br>"
            f"{city}<br>Status: {html.escape(status)}<br>"
            f"Current stock: {row['current_stock']:,.0f} units<br>"
            f"Daily demand: {row['daily_demand']:,.1f} units"
        )
        folium.Marker(
            location=[float(row["latitude"]), float(row["longitude"])],
            tooltip=f"{hospital_id} · {hospital_name} · {city}",
            popup=folium.Popup(popup, max_width=300),
            icon=folium.Icon(color=status_colors.get(
                status, "gray"), icon="plus", prefix="fa"),
        ).add_to(geo_map)

    lookup = hospitals.set_index("hospital_id")
    for recommendation in recommendations.head(10).to_dict("records"):
        source = lookup.loc[recommendation["source_hospital_id"]]
        destination = lookup.loc[recommendation["destination_hospital_id"]]
        points = [
            [float(source["latitude"]), float(source["longitude"])],
            [float(destination["latitude"]), float(destination["longitude"])],
        ]
        color = "#c2410c" if recommendation["score"] < 0.6 else "#b91c1c"
        route = folium.PolyLine(
            points,
            color=color,
            weight=4,
            opacity=0.8,
            tooltip=(
                f"{recommendation['source_hospital_id']} → "
                f"{recommendation['destination_hospital_id']}: "
                f"{recommendation['quantity']} units · "
                f"{recommendation['distance_km']:.1f} km · "
                f"{recommendation['eta_minutes']:.0f} min"
            ),
        ).add_to(geo_map)
        PolyLineTextPath(
            route,
            "  ▶  ",
            repeat=False,
            offset=8,
            attributes={"fill": color,
                        "font-weight": "bold", "font-size": "16"},
        ).add_to(geo_map)

    geo_map.fit_bounds(mapped[["latitude", "longitude"]
                              ].astype(float).values.tolist())
    st_folium(geo_map, height=560, use_container_width=True,
              returned_objects=[], key="objective3_geo_map")


def api(method, path, body=None, challenge=False):
    value = st.session_state.get("challenge" if challenge else "token", "")
    try:
        response = requests.request(method, API_URL + path, json=body,
                                    headers={"Authorization": f"Bearer {value}"} if value else {}, timeout=20)
    except requests.RequestException:
        st.error("Cannot connect to the API. Start the backend first.")
        st.stop()
    if response.status_code >= 400:
        detail = response.json().get("detail", "The request failed.")
        if response.status_code == 401 and not challenge and "token" in st.session_state:
            st.session_state.pop("token", None)
            st.warning("Your session ended. Sign in again.")
        else:
            st.error(detail if isinstance(detail, str)
                     else "Check the form values.")
        st.stop()
    return response.json()


st.markdown('<div class="dashboard-title">Medical Supply Intelligence Dashboard</div>',
            unsafe_allow_html=True)
st.caption("Synthetic data. Travel times and forecasts are estimates.")
auth_panel = st.empty()
if "token" not in st.session_state:
    with auth_panel.container():
        st.subheader("Administrator sign-in")
        if "challenge" not in st.session_state:
            with st.form("login"):
                username = st.text_input("Username")
                password = st.text_input("Password", type="password")
                submit = st.form_submit_button("Continue")
            if submit:
                result = api("POST", "/auth/login",
                             {"username": username, "password": password})
                st.session_state.challenge = result["challenge"]
                st.session_state.setup_required = result["setup_required"]
                st.rerun()
        else:
            st.info(
                "Use your authenticator code. This is a time-based one-time password (TOTP).")
            if st.session_state.setup_required:
                st.caption("Account settings: set up two-factor access.")
                uri = api("POST", "/auth/setup", challenge=True)["uri"]
                buffer = io.BytesIO()
                qrcode.make(uri).save(buffer, format="PNG")
                st.image(buffer.getvalue(), width=230)
                st.caption(
                    "Scan this QR code in an authenticator app. Then enter its code.")
            with st.form("second_factor"):
                code = st.text_input(
                    "Authenticator code or recovery code", type="password")
                recovery = st.checkbox(
                    "Use a recovery code", disabled=st.session_state.setup_required)
                submit = st.form_submit_button("Verify and sign in")
            if submit:
                result = api("POST", "/auth/verify",
                             {"code": code, "recovery": recovery}, challenge=True)
                st.session_state.token = result["token"]
                st.session_state.pop("challenge", None)
                if result["recovery_codes"]:
                    st.session_state.recovery_once = result["recovery_codes"]
                st.rerun()
            if st.button("Start sign-in again"):
                st.session_state.pop("challenge", None)
                st.rerun()
        st.stop()
else:
    auth_panel.empty()

user = api("GET", "/auth/me")
hospital = user["hospital_id"]
with st.sidebar:
    st.subheader(hospital)
    st.write(user["username"])
    st.caption("Your account is assigned to this hospital.")
    if st.button("Logout"):
        api("POST", "/auth/logout")
        st.session_state.clear()
        st.rerun()

if "recovery_once" in st.session_state:
    st.warning(
        "Save these recovery codes now. They are shown once. Each code works once.")
    st.code("\n".join(st.session_state.pop("recovery_once")))
    st.caption("Keep the codes in a safe place. Do not share them.")

medicines = api("GET", "/medicines")
labels = {m["id"]: m["name"] for m in medicines}
inventory = api("GET", f"/hospitals/{hospital}/inventory")
alert_rows = api("GET", "/alerts")
request_rows = api("GET", "/requests")
risk_rows = api("GET", "/risk")
col1, col2, col3 = st.columns(3)
col1.metric("Assigned hospital", hospital)
col2.metric("Stock units", sum(b["quantity"] for b in inventory))
col3.metric("Active alerts", sum(a["state"] == "Active" for a in alert_rows))
tabs = st.tabs(["Inventory", "Risk and alerts", "Supply search",
               "Requests", "Account settings", "Objective 3 · Geo-Redistribution"])
with tabs[0]:
    st.subheader("Hospital inventory")
    st.dataframe(inventory, use_container_width=True)
    st.download_button("Export hospital inventory", json.dumps(api("GET", "/inventory/export"), indent=2),
                       file_name=f"{hospital}-inventory.json", mime="application/json")
with tabs[1]:
    st.subheader("Forecast and supply risk")
    st.caption(
        "Demo forecast: recent average daily demand. Check covers supplier lead time and safety stock.")
    st.dataframe([r for r in risk_rows if "medicine_id" in r],
                 use_container_width=True)
    st.subheader("Hospital alerts")
    st.caption(
        "Acknowledged means seen. It does not mean the stock problem is fixed.")
    for alert in alert_rows:
        if alert["state"] != "Resolved":
            st.write(
                f"{alert['severity']} ? {alert['kind']} ? {alert['state']}")
            st.caption(alert["message"])
            if alert["state"] == "Active" and st.button("Acknowledge", key=alert["id"]):
                api("POST", f"/alerts/{alert['id']}/acknowledge")
                st.rerun()
    if not alert_rows:
        st.info("No active alerts.")
with tabs[2]:
    st.subheader("Find a safe supply source")
    st.session_state.setdefault("search_quantity", 500)
    with st.form("search"):
        medicine = st.selectbox("Medicine", list(
            labels), format_func=lambda mid: labels[mid])
        quantity = st.number_input(
            "Quantity in units", min_value=1, max_value=1000000, key="search_quantity")
        submitted = st.form_submit_button("Search")
    if submitted:
        result = api("POST", "/supply/search",
                     {"medicine_id": medicine, "quantity": quantity})
        st.session_state.search_results = result["recommendations"]
    with st.expander("Supply assistant"):
        with st.form("assistant"):
            question = st.text_input(
                "Question", placeholder="We need 500 units of Paracetamol. Which hospital can supply them?")
            ask = st.form_submit_button("Ask")
        if ask:
            result = api("POST", "/assistant", {"question": question})
            st.info(result["message"])
            st.session_state.search_results = result.get("recommendations", [])
    recommendations = st.session_state.get("search_results")
    if recommendations is not None:
        if not recommendations:
            st.info("No safe transfer is available.")
        else:
            st.dataframe(recommendations, use_container_width=True)
            st.caption(
                "Arrival times are simulated. Search does not create or approve a request.")
            with st.form("new_request"):
                choice = st.selectbox("Source", range(len(recommendations)),
                                      format_func=lambda i: recommendations[i]["donor_hospital"] + " ? " + labels.get(recommendations[i]["medicine"], recommendations[i]["medicine"]))
                selected = recommendations[choice]
                amount = st.number_input("Requested quantity", min_value=1,
                                         max_value=selected["available_quantity"], value=selected["available_quantity"])
                urgency = st.selectbox("Urgency", ["Routine", "Urgent"])
                reason = st.text_input("Reason", value="Hospital supply need")
                send = st.form_submit_button("Submit request")
            if send:
                api("POST", "/requests", {"donor": selected["donor_hospital"], "medicine_id": selected["medicine"],
                    "quantity": amount, "urgency": urgency, "reason": reason})
                st.session_state.pop("search_results", None)
                st.rerun()
with tabs[3]:
    st.caption("Allocation priority uses the urgency entered by the requester. It needs donor review. Notification severity does not allocate stock.")
    for title, incoming in [("Incoming requests for your stock", True), ("Outgoing supply requests", False)]:
        st.subheader(title)
        rows = [r for r in request_rows if (
            r["donor"] == hospital) == incoming]
        if not rows:
            st.caption("No requests.")
        for r in rows:
            with st.expander(f"{r['medicine_id']} ? {r['requested']} units ? {r['status']} ? {r['id'][:8]}"):
                st.json(r)
                controls = []
                if incoming and r["status"] == "Requested":
                    controls = ["Approved", "Rejected"]
                elif incoming and r["status"] == "Approved":
                    controls = ["Dispatched"]
                elif not incoming and r["status"] == "Dispatched":
                    controls = ["Received"]
                if r["status"] in ("Requested", "Approved"):
                    controls.append("Cancelled")
                amount = None
                if "Approved" in controls:
                    amount = st.number_input(
                        "Approved units", min_value=1, max_value=r["requested"], value=r["requested"], key="qty" + r["id"])
                for control in controls:
                    if st.button(control, key=r["id"] + control):
                        api("POST", f"/requests/{r['id']}/action", {
                            "status": control, "quantity": amount if control == "Approved" else None})
                        st.rerun()
with tabs[4]:
    st.subheader("Two-factor access")
    st.write("Authenticator setup is complete. Recovery codes work once.")
    st.caption("To replace your authenticator, enter your password and a new authenticator code or unused recovery code. All sessions will end.")
    with st.form("reset"):
        password = st.text_input("Current password", type="password")
        code = st.text_input(
            "New authenticator code or recovery code", type="password")
        recovery = st.checkbox("Use recovery code")
        submit = st.form_submit_button("Reset two-factor access")
    if submit:
        api("POST", "/auth/reset",
            {"password": password, "code": code, "recovery": recovery})
        st.session_state.clear()
        st.rerun()

with tabs[5]:
    st.subheader("🎯 Objective 3 — Smart Geo-Redistribution")
    st.warning(
        "Read-only synthetic demo analysis. Recommendations use the latest dated CSV snapshot, "
        "not live stock_batches; locations are synthetic and are not real hospital locations. "
        "Nothing here reserves stock or submits a transfer request."
    )
    geo_snapshot, geo_locations, geo_snapshot_date = cached_geo_snapshot()
    if geo_snapshot.empty or geo_locations.empty:
        st.info("The supply snapshot or hospital_locations.csv is missing or does not contain the required columns.")
    else:
        if geo_snapshot_date:
            st.caption(f"Supply snapshot date: {geo_snapshot_date}")
        st.caption(
            "Ranking weights: 30% shortage, 20% relative demand (70% daily demand, 30% patient load), "
            "20% emergency/outbreak, "
            "10% near-expiry signal (within 30 days), and 20% proximity (decreases to zero at 250 km). "
            "Donors retain a 3-day demand reserve; recipient targets use max(7 days, supplier lead time) + 3 days, capped at 14 days. "
            "Expiry prioritizes a source but cannot quantity-limit a batch because the CSV has no batch-level expiry quantities."
        )
        medicine_options = ["All Medicines"] + sorted(
            geo_snapshot["medicine_name"].dropna().astype(
                str).unique().tolist()
        )
        filter_col, speed_col = st.columns([3, 2])
        with filter_col:
            selected_geo_medicine = st.selectbox(
                "Filter recommendations and map stock by medicine",
                medicine_options,
                key="objective3_medicine_filter",
            )
        with speed_col:
            average_speed = st.slider(
                "Estimated average speed (km/h)",
                min_value=15,
                max_value=80,
                value=int(AVERAGE_SPEED_KMPH),
                key="objective3_average_speed",
            )

        recommendations = build_redistribution_recommendations(
            geo_snapshot, geo_locations, average_speed_kmph=float(
                average_speed)
        )
        if selected_geo_medicine != "All Medicines":
            recommendations = recommendations[
                recommendations["medicine_name"].eq(selected_geo_medicine)
            ].reset_index(drop=True)
        map_hospitals = summarize_hospitals(
            geo_snapshot, geo_locations, selected_geo_medicine
        )
        missing_locations = set(
            geo_snapshot["hospital_id"]) - set(geo_locations["hospital_id"])
        if missing_locations:
            st.caption(
                f"{len(missing_locations)} hospital ID(s) have supply rows but no matching location and cannot be routed.")

        if recommendations.empty:
            st.info(
                "No feasible source-to-destination transfers were found for this snapshot and filter.")
        else:
            st.markdown("#### Recommended transfers")
            for recommendation in recommendations.head(6).to_dict("records"):
                st.markdown(
                    f"##### {recommendation['source_hospital_id']} → {recommendation['destination_hospital_id']} · "
                    f"{recommendation['medicine_name']}"
                )
                source_col, transfer_col, destination_col = st.columns([
                                                                       2, 1, 2])
                source_col.metric(
                    f"Source · {recommendation['source_city']}",
                    recommendation["source_hospital_name"],
                )
                transfer_col.metric(
                    "Transfer", f"{recommendation['quantity']:,} units")
                destination_col.metric(
                    f"Destination · {recommendation['destination_city']}",
                    recommendation["destination_hospital_name"],
                )
                distance_col, eta_col, score_col = st.columns(3)
                distance_col.metric("Straight-line distance",
                                    f"{recommendation['distance_km']:.1f} km")
                eta_col.metric("Estimated transport time",
                               f"{recommendation['eta_minutes']:.0f} min")
                score_col.metric("Priority score",
                                 f"{recommendation['score']:.2f} / 1.00")
                with st.expander("Why this recommendation?"):
                    st.write(recommendation["reason"])
                st.divider()
            if len(recommendations) > 6:
                st.caption(
                    f"Showing 6 of {len(recommendations)} ranked recommendations above; all are in the table below.")

        st.markdown("#### Hospital network map")
        st.caption(
            "Green: sufficient/excess · Orange: low · Red: critical · Gray: no snapshot data. "
            "With All Medicines selected, marker color reflects the worst medicine-level status; popup quantities are combined totals. "
            "Arrows show the top 10 scored routes. Distances are straight-line Haversine estimates; "
            "ETA uses the configurable speed above, not road routing or traffic."
        )
        render_geo_map(map_hospitals, recommendations)

        st.markdown("#### Redistribution table")
        if recommendations.empty:
            st.info("No recommendation rows to display.")
        else:
            table = recommendations.rename(columns={
                "source_hospital_id": "Source",
                "source_city": "Source Place",
                "destination_hospital_id": "Destination",
                "destination_city": "Destination Place",
                "medicine_name": "Medicine",
                "quantity": "Quantity",
                "distance_km": "Distance (km)",
                "eta_minutes": "ETA (min)",
                "score": "Priority score",
                "reason": "Reason",
            })
            st.dataframe(
                table[[
                    "Source", "Source Place", "Destination", "Destination Place",
                    "Medicine", "Quantity", "Distance (km)", "ETA (min)",
                    "Priority score", "Reason",
                ]],
                use_container_width=True,
                hide_index=True,
            )
