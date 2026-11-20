"""Server-rendered web UI (Jinja templates, plain HTML forms, no JS build step).

The UI calls the same service functions as the REST API, so records added here update the
odometer and send the same Home Assistant events.
"""

from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from itertools import groupby
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, BackgroundTasks, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, ValidationError
from sqlalchemy import select

from app.api.deps import DB, Bus, SettingsDep, VehicleDep, get_or_404
from app.models import (
    FuelType,
    MaintenanceCategory,
    MaintenanceRecord,
    OdometerReading,
    OilRecord,
    TreadMeasurement,
    TyreSet,
    TyreType,
    Vehicle,
    WheelPosition,
)
from app.schemas import (
    MaintenanceCreate,
    MountRequest,
    OdometerCreate,
    OilRecordCreate,
    TreadMeasurementCreate,
    TyreSetBase,
    TyreSetCreate,
    VehicleBase,
    VehicleCreate,
)
from app.services import records
from app.services.status import tyre_status, vehicle_status

TEMPLATES = Jinja2Templates(directory=Path(__file__).parent / "templates")
router = APIRouter(include_in_schema=False)

LABELS: dict[type[Enum], dict[str, str]] = {
    TyreType: {"summer": "Summer", "winter": "Winter", "all_season": "All-season"},
    WheelPosition: {
        "front_left": "Front left",
        "front_right": "Front right",
        "rear_left": "Rear left",
        "rear_right": "Rear right",
        "spare": "Spare",
    },
    MaintenanceCategory: {
        "service": "Service",
        "oil_change": "Oil change",
        "tyre_change": "Tyre change",
        "brakes": "Brakes",
        "inspection": "Inspection (APK/MOT)",
        "battery": "Battery",
        "filters": "Filters",
        "fluids": "Fluids",
        "repair": "Repair",
        "other": "Other",
    },
    FuelType: {
        "petrol": "Petrol",
        "diesel": "Diesel",
        "hybrid": "Hybrid",
        "plugin_hybrid": "Plug-in hybrid",
        "electric": "Electric",
        "lpg": "LPG",
        "other": "Other",
    },
}
CURRENCY_SYMBOLS = {"EUR": "€", "USD": "$", "GBP": "£", "CHF": "CHF", "SEK": "kr", "NOK": "kr", "DKK": "kr"}


# ---------- template helpers ----------


def label(value: Enum | str | None) -> str:
    if value is None:
        return ""
    if isinstance(value, Enum):
        return LABELS.get(type(value), {}).get(value.value, value.value)
    for mapping in LABELS.values():
        if value in mapping:
            return mapping[value]
    return str(value)


def fmt_km(value: int | None) -> str:
    return "–" if value is None else f"{value:,}".replace(",", " ") + " km"


def fmt_date(value: date | datetime | None) -> str:
    return "–" if value is None else value.strftime("%d %b %Y")


def fmt_num(value: float | None, digits: int = 1) -> str:
    return "–" if value is None else f"{value:.{digits}f}"


TEMPLATES.env.filters.update(label=label, km=fmt_km, date=fmt_date, num=fmt_num)
TEMPLATES.env.globals.update(
    TyreType=TyreType,
    WheelPosition=WheelPosition,
    MaintenanceCategory=MaintenanceCategory,
    FuelType=FuelType,
    ROAD_WHEELS=[WheelPosition.front_left, WheelPosition.front_right, WheelPosition.rear_left, WheelPosition.rear_right],
)


def render(request: Request, name: str, settings, status_code: int = 200, **ctx: Any) -> HTMLResponse:
    def money(value: Decimal | float | None) -> str:
        if value is None:
            return "–"
        symbol = CURRENCY_SYMBOLS.get(settings.currency, settings.currency)
        return f"{symbol} {Decimal(value):,.2f}"

    ctx.update(
        settings=settings,
        money=money,
        today=date.today().isoformat(),
    )
    return TEMPLATES.TemplateResponse(request, name, ctx, status_code=status_code)


def redirect(url: str) -> RedirectResponse:
    return RedirectResponse(url, status_code=303)  # POST -> redirect -> GET


# ---------- form helpers ----------


async def _form(request: Request) -> dict[str, Any]:
    """Form fields as a dict; empty strings become None so optional fields validate."""
    form = await request.form()
    data: dict[str, Any] = {}
    for key in form.keys():
        values = [v.strip() if isinstance(v, str) else v for v in form.getlist(key)]
        values = [v for v in values if v not in ("", None)]
        data[key] = (values if len(values) > 1 else values[0]) if values else None
    return data


Form = Annotated[dict[str, Any], Depends(_form)]


def _validate[M: BaseModel](schema: type[M], data: dict[str, Any]) -> tuple[M | None, dict[str, str]]:
    try:
        return schema.model_validate(data), {}
    except ValidationError as exc:
        errors: dict[str, str] = {}
        for err in exc.errors():
            field = ".".join(str(p) for p in err["loc"]) or "__all__"
            errors.setdefault(field, err["msg"].removeprefix("Value error, "))
        return None, errors


def _form_values(obj: Any, fields: list[str]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for f in fields:
        v = getattr(obj, f, None)
        out[f] = v.value if isinstance(v, Enum) else v.isoformat() if isinstance(v, date) else v
    return out


class VehicleForm(VehicleBase):
    archived: bool = False


class TyreSetEditForm(TyreSetBase):
    retired: bool = False


# ---------- dashboard ----------


@router.get("/")
def dashboard(request: Request, db: DB, settings: SettingsDep, archived: bool = False):
    q = select(Vehicle).where(Vehicle.archived.is_(archived)).order_by(Vehicle.name)
    vehicles = db.scalars(q).all()
    archived_count = len(db.scalars(select(Vehicle.id).where(Vehicle.archived.is_(True))).all())
    cards = [(v, vehicle_status(db, v, settings)) for v in vehicles]
    return render(request, "dashboard.html", settings, cards=cards, archived=archived, archived_count=archived_count)


# ---------- vehicles ----------

VEHICLE_FIELDS = ["name", "make", "model", "year", "license_plate", "vin", "fuel_type", "oil_spec", "notes"]


@router.get("/vehicles/new")
def vehicle_new(request: Request, settings: SettingsDep):
    return render(request, "vehicle_form.html", settings, vehicle=None, values={}, errors={})


@router.post("/vehicles/new")
def vehicle_create(request: Request, form: Form, db: DB, bus: Bus, settings: SettingsDep, background: BackgroundTasks):
    body, errors = _validate(VehicleCreate, form)
    if errors:
        return render(request, "vehicle_form.html", settings, 422, vehicle=None, values=form, errors=errors)
    vehicle = records.create_vehicle(db, bus, background, body)
    return redirect(f"/vehicles/{vehicle.id}")


@router.get("/vehicles/{vehicle_id}")
def vehicle_overview(request: Request, vehicle: VehicleDep, db: DB, settings: SettingsDep):
    status = vehicle_status(db, vehicle, settings)
    readings = db.scalars(
        select(OdometerReading)
        .where(OdometerReading.vehicle_id == vehicle.id)
        .order_by(OdometerReading.recorded_on.desc(), OdometerReading.id.desc())
        .limit(5)
    ).all()
    return render(request, "vehicle_overview.html", settings, vehicle=vehicle, status=status, readings=readings, tab="overview")


@router.post("/vehicles/{vehicle_id}/odometer")
def vehicle_odometer(vehicle: VehicleDep, form: Form, db: DB, bus: Bus, background: BackgroundTasks):
    body, errors = _validate(OdometerCreate, form)
    if body:
        records.add_odometer(db, bus, background, vehicle, body)
    return redirect(f"/vehicles/{vehicle.id}")


@router.get("/vehicles/{vehicle_id}/edit")
def vehicle_edit(request: Request, vehicle: VehicleDep, settings: SettingsDep):
    values = _form_values(vehicle, VEHICLE_FIELDS + ["archived"])
    return render(request, "vehicle_form.html", settings, vehicle=vehicle, values=values, errors={})


@router.post("/vehicles/{vehicle_id}/edit")
def vehicle_update(request: Request, vehicle: VehicleDep, form: Form, db: DB, settings: SettingsDep):
    form.setdefault("archived", False)  # unchecked checkboxes are not sent
    body, errors = _validate(VehicleForm, form)
    if errors:
        return render(request, "vehicle_form.html", settings, 422, vehicle=vehicle, values=form, errors=errors)
    records.apply_update(db, vehicle, body)
    return redirect(f"/vehicles/{vehicle.id}")


@router.post("/vehicles/{vehicle_id}/delete")
def vehicle_delete(vehicle: VehicleDep, db: DB):
    records.delete(db, vehicle)
    return redirect("/")


# ---------- tyres ----------

TYRE_FIELDS = ["name", "tyre_type", "brand", "model", "size", "dot_code", "purchased_on", "purchase_cost", "notes"]


def _measurement_history(db, tyre_set: TyreSet) -> list[dict[str, Any]]:
    """Measurements grouped per session (date + odometer), newest first."""
    rows = db.scalars(
        select(TreadMeasurement)
        .where(TreadMeasurement.tyre_set_id == tyre_set.id)
        .order_by(TreadMeasurement.measured_on.desc(), TreadMeasurement.id.desc())
    ).all()
    history = []
    for (measured_on, odometer), group in groupby(rows, key=lambda m: (m.measured_on, m.odometer_km)):
        group = list(group)
        history.append(
            {
                "measured_on": measured_on,
                "odometer_km": odometer,
                "depths": {m.position: m.depth_mm for m in reversed(group)},
                "ids": [m.id for m in group],
            }
        )
    return history


@router.get("/vehicles/{vehicle_id}/tyres")
def tyres(request: Request, vehicle: VehicleDep, db: DB, settings: SettingsDep, retired: bool = False):
    q = select(TyreSet).where(TyreSet.vehicle_id == vehicle.id)
    if not retired:
        q = q.where(TyreSet.retired.is_(False))
    sets = db.scalars(q.order_by(TyreSet.is_mounted.desc(), TyreSet.id)).all()
    items = [(s, tyre_status(db, s), _measurement_history(db, s)) for s in sets]
    return render(request, "tyres.html", settings, vehicle=vehicle, items=items, show_retired=retired, tab="tyres")


@router.get("/vehicles/{vehicle_id}/tyres/new")
def tyre_new(request: Request, vehicle: VehicleDep, settings: SettingsDep):
    return render(request, "tyre_form.html", settings, vehicle=vehicle, tyre_set=None, values={}, errors={}, tab="tyres")


@router.post("/vehicles/{vehicle_id}/tyres/new")
def tyre_create(request: Request, vehicle: VehicleDep, form: Form, db: DB, settings: SettingsDep):
    body, errors = _validate(TyreSetCreate, form)
    if errors:
        return render(request, "tyre_form.html", settings, 422, vehicle=vehicle, tyre_set=None, values=form, errors=errors, tab="tyres")
    records.create_tyre_set(db, vehicle, body)
    return redirect(f"/vehicles/{vehicle.id}/tyres")


@router.get("/vehicles/{vehicle_id}/tyres/{tyre_set_id}/edit")
def tyre_edit(request: Request, vehicle: VehicleDep, tyre_set_id: int, db: DB, settings: SettingsDep):
    tyre_set = get_or_404(db, TyreSet, tyre_set_id, vehicle.id)
    values = _form_values(tyre_set, TYRE_FIELDS + ["retired"])
    return render(request, "tyre_form.html", settings, vehicle=vehicle, tyre_set=tyre_set, values=values, errors={}, tab="tyres")


@router.post("/vehicles/{vehicle_id}/tyres/{tyre_set_id}/edit")
def tyre_update(request: Request, vehicle: VehicleDep, tyre_set_id: int, form: Form, db: DB, settings: SettingsDep):
    tyre_set = get_or_404(db, TyreSet, tyre_set_id, vehicle.id)
    form.setdefault("retired", False)  # unchecked checkboxes are not sent
    body, errors = _validate(TyreSetEditForm, form)
    if errors:
        return render(request, "tyre_form.html", settings, 422, vehicle=vehicle, tyre_set=tyre_set, values=form, errors=errors, tab="tyres")
    records.apply_update(db, tyre_set, body)
    return redirect(f"/vehicles/{vehicle.id}/tyres")


@router.post("/vehicles/{vehicle_id}/tyres/{tyre_set_id}/mount")
def tyre_mount(vehicle: VehicleDep, tyre_set_id: int, form: Form, db: DB, bus: Bus, background: BackgroundTasks):
    tyre_set = get_or_404(db, TyreSet, tyre_set_id, vehicle.id)
    body, _ = _validate(MountRequest, form)
    records.mount_tyre_set(db, bus, background, vehicle, tyre_set, body or MountRequest())
    return redirect(f"/vehicles/{vehicle.id}/tyres")


@router.post("/vehicles/{vehicle_id}/tyres/{tyre_set_id}/delete")
def tyre_delete(vehicle: VehicleDep, tyre_set_id: int, db: DB):
    records.delete(db, get_or_404(db, TyreSet, tyre_set_id, vehicle.id))
    return redirect(f"/vehicles/{vehicle.id}/tyres")


@router.get("/vehicles/{vehicle_id}/tyres/{tyre_set_id}/measure")
def tread_new(request: Request, vehicle: VehicleDep, tyre_set_id: int, db: DB, settings: SettingsDep):
    tyre_set = get_or_404(db, TyreSet, tyre_set_id, vehicle.id)
    return render(request, "tread_form.html", settings, vehicle=vehicle, tyre_set=tyre_set, values={}, errors={}, tab="tyres")


@router.post("/vehicles/{vehicle_id}/tyres/{tyre_set_id}/measure")
def tread_create(
    request: Request, vehicle: VehicleDep, tyre_set_id: int, form: Form, db: DB, bus: Bus,
    settings: SettingsDep, background: BackgroundTasks,
):
    tyre_set = get_or_404(db, TyreSet, tyre_set_id, vehicle.id)
    data = {
        "measured_on": form.get("measured_on"),
        "odometer_km": form.get("odometer_km"),
        "depths_mm": {p.value: form[f"depth_{p.value}"] for p in WheelPosition if form.get(f"depth_{p.value}") is not None},
    }
    body, errors = _validate(TreadMeasurementCreate, data)
    if errors:
        errors = {("depths_mm" if k.startswith("depths_mm") else k): v for k, v in errors.items()}
        if "depths_mm" in errors and not data["depths_mm"]:
            errors["depths_mm"] = "Enter at least one tread depth."
        return render(request, "tread_form.html", settings, 422, vehicle=vehicle, tyre_set=tyre_set, values=form, errors=errors, tab="tyres")
    records.add_tread_measurements(db, bus, background, vehicle, tyre_set, body)
    return redirect(f"/vehicles/{vehicle.id}/tyres")


@router.post("/vehicles/{vehicle_id}/tyres/{tyre_set_id}/measurements/delete")
def tread_delete(vehicle: VehicleDep, tyre_set_id: int, form: Form, db: DB):
    get_or_404(db, TyreSet, tyre_set_id, vehicle.id)
    ids = form.get("ids") or []
    for raw in ids if isinstance(ids, list) else [ids]:
        m = db.get(TreadMeasurement, int(raw))
        if m is not None and m.tyre_set_id == tyre_set_id:
            db.delete(m)
    db.commit()
    return redirect(f"/vehicles/{vehicle.id}/tyres")


# ---------- oil ----------


@router.get("/vehicles/{vehicle_id}/oil")
def oil(request: Request, vehicle: VehicleDep, db: DB, settings: SettingsDep):
    return _oil_page(request, vehicle, db, settings, {}, {})


def _oil_page(request, vehicle, db, settings, values, errors, status_code=200):
    entries = db.scalars(
        select(OilRecord).where(OilRecord.vehicle_id == vehicle.id).order_by(OilRecord.added_on.desc(), OilRecord.id.desc())
    ).all()
    status = vehicle_status(db, vehicle, settings)
    return render(request, "oil.html", settings, status_code, vehicle=vehicle, entries=entries, oil=status.oil, values=values, errors=errors, tab="oil")


@router.post("/vehicles/{vehicle_id}/oil")
def oil_create(request: Request, vehicle: VehicleDep, form: Form, db: DB, bus: Bus, settings: SettingsDep, background: BackgroundTasks):
    body, errors = _validate(OilRecordCreate, form)
    if errors:
        return _oil_page(request, vehicle, db, settings, form, errors, 422)
    records.add_oil(db, bus, background, vehicle, body)
    return redirect(f"/vehicles/{vehicle.id}/oil")


@router.post("/vehicles/{vehicle_id}/oil/{record_id}/delete")
def oil_delete(vehicle: VehicleDep, record_id: int, db: DB):
    records.delete(db, get_or_404(db, OilRecord, record_id, vehicle.id))
    return redirect(f"/vehicles/{vehicle.id}/oil")


# ---------- maintenance ----------

MAINT_FIELDS = [
    "performed_on", "odometer_km", "category", "title", "description", "cost",
    "provider", "next_due_on", "next_due_km", "notes",
]


@router.get("/vehicles/{vehicle_id}/maintenance")
def maintenance(request: Request, vehicle: VehicleDep, db: DB, settings: SettingsDep, category: str | None = None):
    q = select(MaintenanceRecord).where(MaintenanceRecord.vehicle_id == vehicle.id)
    if category in MaintenanceCategory._value2member_map_:
        q = q.where(MaintenanceRecord.category == MaintenanceCategory(category))
    entries = db.scalars(q.order_by(MaintenanceRecord.performed_on.desc(), MaintenanceRecord.id.desc())).all()
    status = vehicle_status(db, vehicle, settings)
    return render(request, "maintenance.html", settings, vehicle=vehicle, entries=entries, costs=status.costs, category=category, tab="maintenance")


@router.get("/vehicles/{vehicle_id}/maintenance/new")
def maintenance_new(request: Request, vehicle: VehicleDep, settings: SettingsDep, category: str | None = None):
    values = {"category": category} if category else {}
    return render(request, "maintenance_form.html", settings, vehicle=vehicle, record=None, values=values, errors={}, tab="maintenance")


@router.post("/vehicles/{vehicle_id}/maintenance/new")
def maintenance_create(request: Request, vehicle: VehicleDep, form: Form, db: DB, bus: Bus, settings: SettingsDep, background: BackgroundTasks):
    body, errors = _validate(MaintenanceCreate, form)
    if errors:
        return render(request, "maintenance_form.html", settings, 422, vehicle=vehicle, record=None, values=form, errors=errors, tab="maintenance")
    records.add_maintenance(db, bus, background, vehicle, body)
    return redirect(f"/vehicles/{vehicle.id}/maintenance")


@router.get("/vehicles/{vehicle_id}/maintenance/{record_id}/edit")
def maintenance_edit(request: Request, vehicle: VehicleDep, record_id: int, db: DB, settings: SettingsDep):
    record = get_or_404(db, MaintenanceRecord, record_id, vehicle.id)
    values = _form_values(record, MAINT_FIELDS)
    return render(request, "maintenance_form.html", settings, vehicle=vehicle, record=record, values=values, errors={}, tab="maintenance")


@router.post("/vehicles/{vehicle_id}/maintenance/{record_id}/edit")
def maintenance_update(request: Request, vehicle: VehicleDep, record_id: int, form: Form, db: DB, settings: SettingsDep):
    record = get_or_404(db, MaintenanceRecord, record_id, vehicle.id)
    body, errors = _validate(MaintenanceCreate, form)
    if errors:
        return render(request, "maintenance_form.html", settings, 422, vehicle=vehicle, record=record, values=form, errors=errors, tab="maintenance")
    records.apply_update(db, record, body)
    return redirect(f"/vehicles/{vehicle.id}/maintenance")


@router.post("/vehicles/{vehicle_id}/maintenance/{record_id}/delete")
def maintenance_delete(vehicle: VehicleDep, record_id: int, db: DB):
    records.delete(db, get_or_404(db, MaintenanceRecord, record_id, vehicle.id))
    return redirect(f"/vehicles/{vehicle.id}/maintenance")
