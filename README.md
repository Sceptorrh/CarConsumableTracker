# Car Consumable Tracker

Self-hosted tracker for the consumables of your cars: **tyres** (summer/winter/all-season sets,
tread depth per wheel), **engine oil** top-ups, **maintenance** and their **costs** – with a
REST API designed to integrate with **Home Assistant**.

See [docs/PLAN.md](docs/PLAN.md) for MVP scope, architecture and roadmap.

## Run with Docker

```bash
docker compose up -d --build
# API docs: http://localhost:8000/docs
```

Data is stored in `./data/cct.db`. Configuration is via `CCT_*` environment variables
(see [.env.example](.env.example)).

## Run locally

```bash
cd backend
python -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
alembic upgrade head
uvicorn app.main:app --reload
pytest
```

## Quick tour of the API

```bash
API=http://localhost:8000/api/v1
curl -X POST $API/vehicles -H 'Content-Type: application/json' \
  -d '{"name":"Golf","make":"VW","license_plate":"AB-123-C","odometer_km":84500}'

curl -X POST $API/vehicles/1/tyre-sets -H 'Content-Type: application/json' \
  -d '{"name":"Winter 2025","tyre_type":"winter","size":"205/55 R16","is_mounted":true}'

curl -X POST $API/vehicles/1/tyre-sets/1/measurements -H 'Content-Type: application/json' \
  -d '{"odometer_km":85000,"depths_mm":{"front_left":6.1,"front_right":6.0,"rear_left":6.8,"rear_right":6.9}}'

curl -X POST $API/vehicles/1/oil -H 'Content-Type: application/json' \
  -d '{"added_on":"2026-11-20","amount_l":0.5,"cost":"12.50"}'

curl -X POST $API/vehicles/1/maintenance -H 'Content-Type: application/json' \
  -d '{"performed_on":"2026-11-01","odometer_km":84000,"category":"oil_change","title":"Yearly service","cost":"289.00","next_due_on":"2027-11-01","next_due_km":99000}'

curl $API/vehicles/1/status
```

## Home Assistant

* Example package with REST sensors, an odometer `rest_command` and a webhook automation:
  [homeassistant/packages/car_consumable_tracker.yaml](homeassistant/packages/car_consumable_tracker.yaml)
* Set `CCT_HA_WEBHOOK_URL` to receive events such as `tread_low` and `oil_added` in HA.
* Set `CCT_API_TOKEN` and send `Authorization: Bearer <token>` from HA.

## Project layout

```
backend/
  app/
    api/          REST routers (vehicles, tyres, oil, maintenance, status)
    services/     domain logic (status/alerts/costs, odometer)
    models.py     SQLAlchemy models      schemas.py  API schemas
    events.py     event bus + publishers (log, HA webhook; MQTT later)
    config.py     settings from CCT_* env vars
  alembic/        database migrations
  tests/
homeassistant/    example HA configuration
docs/PLAN.md      MVP plan & roadmap
```
