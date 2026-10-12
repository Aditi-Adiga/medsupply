from app.services import routes, supply
from tests.test_operations import system, block_external_notifications, headers


def test_saved_directed_routes_and_delivery():
    saved = routes.load_routes()
    assert len(saved) == 380
    assert routes.route_for('H05', 'H01')['donor_city'] == 'Mysuru'
    assert routes.route_for('H05', 'H01')['recipient_city'] == 'Mangaluru'
    assert routes.route_for('H05', 'H01')['road_distance_km'] == 254.6
    assert routes.route_for('H05', 'H01')['estimated_delivery_minutes'] == 252
    assert routes.route_for('H06', 'H01')['estimated_delivery_minutes'] == 331
    assert routes.route_for('unknown', 'H01') is None


def test_api_route_fields_and_sort(system):
    response = system.client.post('/api/v1/supply/search', headers=headers(system), json={'medicine_id':'M01','quantity':100})
    assert response.status_code == 200, response.text
    rows = response.json()['recommendations']
    assert rows
    assert all(r['recipient_city'] == 'Mangaluru' and r['road_distance_km'] > 0 for r in rows)
    assert all(not r['travel_time_simulated'] for r in rows)
    times = [r['estimated_delivery_minutes'] for r in rows]
    assert times == sorted(times)


def test_missing_route_excludes_allocation(system, monkeypatch):
    monkeypatch.setattr(supply, 'route_for', lambda donor, recipient: None)
    with system.sessions() as db:
        assert supply.safe_allocation(db, 'H02', 'H01', 'M01', 100) == []


def test_expiry_horizon_rounds_delivery_up(monkeypatch):
    monkeypatch.setattr(supply, 'route_for', lambda donor, recipient: {'estimated_delivery_minutes':1441})
    assert supply.travel_days(None, 'H02', 'H01') == 2
