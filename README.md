# Car Consumable Tracker

Self-hosted tracker for the consumables of your cars: **tyres** (summer/winter/all-season sets,
tread depth per wheel), **engine oil** top-ups, **maintenance** and their **costs** – with a
mobile-friendly web UI and a REST API designed to integrate with **Home Assistant**.

The app records facts; Home Assistant decides what is "due" or "too low".

- [docs/PLAN.md](docs/PLAN.md) – MVP scope, architecture and roadmap
- [docs/DEPLOY-UNRAID.md](docs/DEPLOY-UNRAID.md) – install on unRAID with automatic updates

## Run with Docker

[`docker-compose.yml`](docker-compose.yml) runs the published image plus a scoped auto-updater.
Copy [`.env.example`](.env.example) to `.env`, fill it in, then:

```bash
docker compose up -d
# Web UI: http://localhost:8000   API docs: http://localhost:8000/docs
```

Build the image yourself: `docker build -t cct backend`.

## Run locally

```bash
cd backend
python -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
alembic upgrade head
CCT_DATABASE_URL=sqlite:///./data/cct.db uvicorn app.main:app --reload
pytest
```

CI ([.github/workflows/ci.yml](.github/workflows/ci.yml)) runs the tests on every push and
publishes `ghcr.io/sceptorrh/carconsumabletracker:latest` from `main` (and `X.Y.Z` from `vX.Y.Z` tags).

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
* Set `CCT_HA_WEBHOOK_URL` to receive events such as `tread_measured` and `oil_added` in HA.
* Set `CCT_API_TOKEN` and send `Authorization: Bearer <token>` from HA.

## Project layout

```
backend/
  app/
    api/          REST routers (vehicles, tyres, oil, maintenance, status)
    web/          web UI: routes, Jinja templates, CSS
    services/     domain logic shared by API and UI (records, status/costs, odometer)
    models.py     SQLAlchemy models      schemas.py  API schemas
    events.py     event bus + publishers (log, HA webhook; MQTT later)
    config.py     settings from CCT_* env vars
  alembic/        database migrations
  tests/
deploy/unraid/    unRAID Docker template (alternative to compose)
homeassistant/    example HA configuration
docs/             plan, unRAID deployment guide
docker-compose.yml production stack (app + scoped Watchtower)
```
