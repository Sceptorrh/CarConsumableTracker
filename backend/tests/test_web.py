"""Smoke tests for the server-rendered UI: every page renders and every form works."""

import re


def _post(client, url, data):
    return client.post(url, data=data, follow_redirects=False)


def _create_vehicle(client, **extra):
    r = _post(client, "/vehicles/new", {"name": "Golf", "license_plate": "AB-123-C", "odometer_km": "50000", **extra})
    assert r.status_code == 303
    return r.headers["location"]  # /vehicles/{id}


def test_dashboard_empty_and_static(client):
    r = client.get("/")
    assert r.status_code == 200 and "No vehicles yet" in r.text
    assert client.get("/static/style.css").status_code == 200


def test_vehicle_form_validation(client):
    r = _post(client, "/vehicles/new", {"name": "", "year": "1700"})
    assert r.status_code == 422
    assert 'class="error"' in r.text


def test_full_flow(client, published):
    base = _create_vehicle(client, fuel_type="petrol", oil_spec="5W-30")
    assert "Golf" in client.get("/").text
    page = client.get(base)
    assert page.status_code == 200 and "50 000 km" in page.text

    # odometer
    assert _post(client, f"{base}/odometer", {"odometer_km": "51000"}).status_code == 303

    # tyres: add set, measure, mount
    assert _post(client, f"{base}/tyres/new", {"name": "Winter", "tyre_type": "winter", "is_mounted": "on", "purchase_cost": "500"}).status_code == 303
    assert _post(client, f"{base}/tyres/new", {"name": "Summer", "tyre_type": "summer"}).status_code == 303
    tyres = client.get(f"{base}/tyres").text
    winter_id, summer_id = re.findall(r"/tyres/(\d+)/edit", tyres)[:2]
    r = _post(client, f"{base}/tyres/{winter_id}/measure", {
        "measured_on": "2026-11-01", "odometer_km": "51500",
        "depth_front_left": "6.5", "depth_front_right": "6.4", "depth_rear_left": "", "depth_rear_right": "7",
    })
    assert r.status_code == 303
    assert "6.5" in client.get(f"{base}/tyres").text
    assert _post(client, f"{base}/tyres/{winter_id}/measure", {"depth_front_left": ""}).status_code == 422
    assert _post(client, f"{base}/tyres/{summer_id}/mount", {"odometer_km": "52000"}).status_code == 303
    assert "52 000 km" in client.get(base).text

    # oil
    assert _post(client, f"{base}/oil", {"added_on": "2026-11-02", "amount_l": "0.5", "cost": "12.50"}).status_code == 303
    oil_page = client.get(f"{base}/oil").text
    assert "5W-30" in oil_page  # defaulted from vehicle
    assert _post(client, f"{base}/oil", {"added_on": "2026-11-02", "amount_l": "-1"}).status_code == 422

    # maintenance: add, edit, delete
    r = _post(client, f"{base}/maintenance/new", {
        "category": "service", "title": "Yearly service", "performed_on": "2026-10-01",
        "cost": "289.00", "next_due_km": "65000",
    })
    assert r.status_code == 303
    m_page = client.get(f"{base}/maintenance").text
    rid = re.search(r"/maintenance/(\d+)/edit", m_page).group(1)
    assert client.get(f"{base}/maintenance/{rid}/edit").status_code == 200
    r = _post(client, f"{base}/maintenance/{rid}/edit", {
        "category": "service", "title": "Big service", "performed_on": "2026-10-01", "cost": "300",
    })
    assert r.status_code == 303
    assert "Big service" in client.get(f"{base}/maintenance?category=service").text
    assert "Big service" in client.get(base).text  # latest maintenance table

    types = [e.type for e in published.events]
    for t in ("vehicle_created", "odometer_updated", "tread_measured", "tyres_mounted", "oil_added", "maintenance_added"):
        assert t in types, t

    assert _post(client, f"{base}/maintenance/{rid}/delete", {}).status_code == 303
    assert "Big service" not in client.get(f"{base}/maintenance").text


def test_edit_vehicle_archive_and_unarchive(client):
    base = _create_vehicle(client)
    assert client.get(f"{base}/edit").status_code == 200
    _post(client, f"{base}/edit", {"name": "Golf", "archived": "on"})
    assert "Archived vehicles (1)" in client.get("/").text
    _post(client, f"{base}/edit", {"name": "Golf"})  # unchecked box -> unarchive
    assert "Archived vehicles" not in client.get("/").text


def test_delete_measurement_and_vehicle(client):
    base = _create_vehicle(client)
    _post(client, f"{base}/tyres/new", {"name": "S", "tyre_type": "summer"})
    tid = re.search(r"/tyres/(\d+)/edit", client.get(f"{base}/tyres").text).group(1)
    _post(client, f"{base}/tyres/{tid}/measure", {"measured_on": "2026-01-01", "depth_front_left": "4.2"})
    page = client.get(f"{base}/tyres").text
    ids = re.findall(r'name="ids" value="(\d+)"', page)
    assert ids
    _post(client, f"{base}/tyres/{tid}/measurements/delete", {"ids": ids})
    assert 'name="ids"' not in client.get(f"{base}/tyres").text

    assert _post(client, f"{base}/delete", {}).status_code == 303
    assert client.get(base).status_code == 404


def test_ui_not_blocked_by_api_token(client, settings):
    settings.api_token = "secret"
    assert client.get("/").status_code == 200
