from datetime import date, timedelta


def url(vehicle, path=""):
    return f"/api/v1/vehicles/{vehicle['id']}{path}"


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_vehicle_crud(client, vehicle):
    assert vehicle["odometer_km"] == 50000
    assert [v["name"] for v in client.get("/api/v1/vehicles").json()] == ["Golf"]

    r = client.patch(url(vehicle), json={"archived": True})
    assert r.json()["archived"] is True
    assert client.get("/api/v1/vehicles").json() == []
    assert len(client.get("/api/v1/vehicles?include_archived=true").json()) == 1

    assert client.delete(url(vehicle)).status_code == 204
    assert client.get(url(vehicle)).status_code == 404


def test_odometer_never_goes_backwards(client, vehicle):
    client.post(url(vehicle, "/odometer"), json={"odometer_km": 51000, "source": "integration"})
    client.post(url(vehicle, "/odometer"), json={"odometer_km": 40000})
    assert client.get(url(vehicle)).json()["odometer_km"] == 51000
    assert len(client.get(url(vehicle, "/odometer")).json()) == 3  # incl. initial reading


def test_tyre_sets_mounting_and_tread(client, vehicle, published):
    summer = client.post(url(vehicle, "/tyre-sets"), json={"name": "Summer", "tyre_type": "summer", "is_mounted": True}).json()
    winter = client.post(url(vehicle, "/tyre-sets"), json={"name": "Winter", "tyre_type": "winter"}).json()
    assert summer["is_mounted"] and not winter["is_mounted"]

    r = client.post(url(vehicle, f"/tyre-sets/{winter['id']}/mount"), json={"odometer_km": 52000})
    assert r.json()["is_mounted"] is True
    sets = {s["name"]: s for s in client.get(url(vehicle, "/tyre-sets")).json()}
    assert sets["Summer"]["is_mounted"] is False

    r = client.post(
        url(vehicle, f"/tyre-sets/{winter['id']}/measurements"),
        json={"odometer_km": 52500, "depths_mm": {"front_left": 5.0, "front_right": 3.8, "rear_left": 6.0, "rear_right": 6.1}},
    )
    assert r.status_code == 201 and len(r.json()) == 4

    status = client.get(url(vehicle, "/status")).json()
    assert status["odometer_km"] == 52500
    assert status["tyres"]["name"] == "Winter"
    assert status["tyres"]["min_depth_mm"] == 3.8
    assert status["tyres"]["state"] == "warning"  # winter threshold is 4.0 mm
    assert "tread_warning" in status["alerts"]
    assert {"tyres_mounted", "tread_measured", "tread_low"} <= {e.type for e in published.events}


def test_latest_measurement_wins(client, vehicle):
    ts = client.post(url(vehicle, "/tyre-sets"), json={"name": "S", "tyre_type": "summer", "is_mounted": True}).json()
    m = url(vehicle, f"/tyre-sets/{ts['id']}/measurements")
    client.post(m, json={"measured_on": "2026-01-01", "depths_mm": {"front_left": 1.0}})
    client.post(m, json={"measured_on": "2026-06-01", "depths_mm": {"front_left": 7.0}})
    tyres = client.get(url(vehicle, "/status")).json()["tyres"]
    assert tyres["depths_mm"]["front_left"] == 7.0
    assert tyres["state"] == "ok"


def test_oil_since_last_change(client, vehicle):
    client.post(url(vehicle, "/oil"), json={"added_on": "2026-01-10", "amount_l": 1.0})
    client.post(url(vehicle, "/maintenance"), json={"performed_on": "2026-02-01", "odometer_km": 50000, "category": "oil_change", "title": "Oil change", "cost": "120.00"})
    client.post(url(vehicle, "/oil"), json={"added_on": "2026-03-01", "amount_l": 0.5, "cost": "15.50", "odometer_km": 52000})

    oil = client.get(url(vehicle, "/status")).json()["oil"]
    assert oil["added_since_change_l"] == 0.5
    assert oil["km_since_change"] == 2000
    assert oil["consumption_l_per_1000km"] == 0.25


def test_maintenance_latest_and_costs(client, vehicle):
    """The app reports raw next-due values; it never decides due/overdue itself."""
    today = date.today()
    past = (today - timedelta(days=1)).isoformat()
    client.post(url(vehicle, "/maintenance"), json={
        "performed_on": (today - timedelta(days=730)).isoformat(), "category": "inspection",
        "title": "APK 2024", "cost": "50.00",
    })
    client.post(url(vehicle, "/maintenance"), json={
        "performed_on": (today - timedelta(days=365)).isoformat(), "category": "inspection",
        "title": "APK 2025", "cost": "50.00", "next_due_on": past,
    })
    client.post(url(vehicle, "/maintenance"), json={
        "performed_on": today.isoformat(), "odometer_km": 50000, "category": "service",
        "title": "Service", "cost": "300.00", "next_due_km": 50500,
    })
    client.post(url(vehicle, "/tyre-sets"), json={"name": "S", "tyre_type": "summer", "purchase_cost": "400", "purchased_on": today.isoformat()})

    status = client.get(url(vehicle, "/status")).json()
    maint = status["maintenance"]
    assert maint["inspection"]["title"] == "APK 2025"
    assert maint["inspection"]["next_due_on"] == past
    assert maint["service"]["next_due_km"] == 50500
    assert "state" not in maint["inspection"]
    assert status["alerts"] == []  # overdue date does not produce an alert

    costs = status["costs"]
    assert float(costs["total"]) == 800.0
    assert float(costs["by_category"]["tyres"]) == 400.0
    assert len(client.get("/api/v1/status").json()) == 1


def test_records_scoped_to_vehicle(client, vehicle):
    other = client.post("/api/v1/vehicles", json={"name": "Other"}).json()
    rec = client.post(url(vehicle, "/maintenance"), json={"performed_on": "2026-01-01", "category": "other", "title": "x"}).json()
    assert client.get(f"/api/v1/vehicles/{other['id']}/maintenance/{rec['id']}").status_code == 404


def test_validation(client, vehicle):
    ts = client.post(url(vehicle, "/tyre-sets"), json={"name": "S", "tyre_type": "summer"}).json()
    r = client.post(url(vehicle, f"/tyre-sets/{ts['id']}/measurements"), json={"depths_mm": {"front_middle": 5}})
    assert r.status_code == 422
    assert client.post(url(vehicle, "/oil"), json={"added_on": "2026-01-01", "amount_l": -1}).status_code == 422


def test_api_token(client, settings):
    settings.api_token = "secret"
    assert client.get("/api/v1/vehicles").status_code == 401
    assert client.get("/api/v1/vehicles", headers={"Authorization": "Bearer secret"}).status_code == 200
    assert client.get("/health").status_code == 200
