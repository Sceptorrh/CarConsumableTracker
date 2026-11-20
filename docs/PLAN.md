# Car Consumable Tracker – MVP plan

## Goal
Keep track of the "consumables" of my cars – tyres, engine oil, maintenance – and what they
cost, in a self-hosted app that Home Assistant (HA) can read from and react to.

## MVP scope

| # | Feature | Status |
|---|---------|--------|
| 1 | Vehicles: add / edit / archive / delete (name, make, model, year, plate, VIN, fuel type, oil spec) | ✅ API |
| 2 | Odometer history; mileage from any record moves the vehicle odometer forward (never back) | ✅ API |
| 3 | Tyre sets per vehicle, type **summer / winter / all-season**, brand, size, DOT, purchase cost | ✅ API |
| 4 | Mount a tyre set (seasonal swap); other sets of that car are unmounted automatically | ✅ API |
| 5 | Tread depth per wheel (FL / FR / RL / RR / spare), history per set | ✅ API |
| 6 | Oil top-ups: litres added, date, odometer, spec, cost | ✅ API |
| 7 | Maintenance records: category, title, cost, garage, optional *next due date / km* (stored only) | ✅ API |
| 8 | Status per vehicle: tread state, oil added since last change + L/1000 km, latest maintenance per category (incl. next-due values), costs (total, this year, per category), alerts | ✅ API |
| 9 | Home Assistant: REST sensors on `/status`, push odometer in, webhook events out | ✅ API + example package |
| 10 | Web UI (mobile-friendly) to enter records in the garage / at the pump | ⏳ next |
| 11 | CSV export of all records | ⏳ next |

Out of MVP: multiple users, photos/receipts, fuel/charging log, reports & charts.

## Architecture

```
            ┌────────────── Car Consumable Tracker (Docker) ──────────────┐
 Web UI ──► │ FastAPI REST /api/v1  ──► services (status, odometer)       │
 HA rest ─► │        │                        │                           │
            │        ▼                        ▼                           │
            │   SQLAlchemy ── SQLite (/data)  EventBus ──► LogPublisher   │
            │   Alembic migrations                    └──► WebhookPublisher ──► HA webhook automation
            └─────────────────────────────────────────────────────────────┘
```

* **Backend:** Python 3.12, FastAPI, SQLAlchemy 2, Alembic, Pydantic v2. Python matches HA,
  so a future HA custom integration can reuse the same models/know-how.
* **Storage:** SQLite in a Docker volume (one file, easy backups). `CCT_DATABASE_URL` can point
  to PostgreSQL later without code changes.
* **API first:** everything (UI, HA, scripts) uses the same REST API; OpenAPI docs at `/docs`.
* **Units:** km, litres, mm; money as decimal in one configured currency.

### Data model

```
Vehicle 1─* OdometerReading
Vehicle 1─* TyreSet 1─* TreadMeasurement (position, depth_mm, date, odometer)
Vehicle 1─* OilRecord        (top-ups between changes)
Vehicle 1─* MaintenanceRecord (category, cost, next_due_on / next_due_km)
```

Design choices:
* **Tyre *sets*** rather than single tyres: matches how people swap summer/winter, and keeps
  measurement entry simple (one form, four numbers). A single tyre replacement can be
  noted on the set; per-tyre tracking (rotation, DOT per tyre) is a later extension.
* **Oil change = maintenance record** (`category=oil_change`), oil *top-ups* are `OilRecord`s.
  This gives "litres added since last change" and oil consumption per 1000 km.
* **The app stays dumb about scheduling.** A maintenance record may carry `next_due_on` /
  `next_due_km`, and the status endpoint exposes the latest record per category with those
  values as-is. Deciding whether something is due or overdue, and when to remind, is done in
  Home Assistant (template sensors / automations), not in CCT.
* **Costs** come from maintenance, oil top-ups and tyre purchases – no separate cost table.

### Automation / Home Assistant

1. **Pull (HA → CCT):** `GET /api/v1/vehicles/{id}/status` (or `/api/v1/status` for all) is a flat
   JSON shaped for HA `rest` sensors. See `homeassistant/packages/car_consumable_tracker.yaml`.
2. **Push in (HA → CCT):** `POST /api/v1/vehicles/{id}/odometer` with `source=integration`,
   e.g. nightly from a car's manufacturer integration.
3. **Push out (CCT → HA):** domain events (`vehicle_created`, `odometer_updated`, `tyres_mounted`,
   `tread_measured`, `tread_low`, `oil_added`, `maintenance_added`) are POSTed to
   `CCT_HA_WEBHOOK_URL` after each change. Publishers are pluggable (`app/events.py`).
4. **Auth:** optional bearer token (`CCT_API_TOKEN`).

## Roadmap after the MVP

1. **Web UI** – server-rendered (Jinja + htmx) or a small SPA; mobile-first entry forms.
2. **MQTT publisher with HA MQTT discovery** – devices/entities appear in HA automatically,
   no YAML. Fits in as another `Publisher`.
3. **HA custom integration (HACS)** – config flow, a device per vehicle, and HA services like
   `cct.add_oil` / `cct.add_tread_measurement` so records can be added from HA dashboards/NFC tags.
4. Tread wear prediction (mm per 1000 km → expected replacement date/km).
5. Per-tyre tracking & rotations, tyre age warnings from DOT code.
6. Attachments (invoices/photos), CSV import/export, fuel/charging log, multi-user.
