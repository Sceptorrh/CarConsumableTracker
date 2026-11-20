"""Derived, automation-friendly status for a vehicle (tyres, oil, maintenance, costs).

The app reports facts only; scheduling decisions such as "maintenance due" are left to
Home Assistant, which can compare ``next_due_on`` / ``next_due_km`` with today / the odometer."""

from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.models import (
    MaintenanceCategory,
    MaintenanceRecord,
    OilRecord,
    TreadMeasurement,
    TyreSet,
    TyreType,
    Vehicle,
    WheelPosition,
)
from app.schemas import CostSummary, MaintenanceLatest, OilStatus, TyreStatus, VehicleStatus

ROAD_POSITIONS = {
    WheelPosition.front_left,
    WheelPosition.front_right,
    WheelPosition.rear_left,
    WheelPosition.rear_right,
}


def tread_state(min_depth: float | None, tyre_type: TyreType, settings: Settings) -> str:
    if min_depth is None:
        return "unknown"
    if min_depth < settings.tread_critical_mm:
        return "critical"
    warning = (
        settings.tread_warning_winter_mm
        if tyre_type in (TyreType.winter, TyreType.all_season)
        else settings.tread_warning_mm
    )
    return "warning" if min_depth < warning else "ok"


def latest_depths(db: Session, tyre_set: TyreSet) -> tuple[dict[WheelPosition, float], date | None]:
    """Most recent depth per wheel position for a tyre set."""
    rows = db.scalars(
        select(TreadMeasurement)
        .where(TreadMeasurement.tyre_set_id == tyre_set.id)
        .order_by(TreadMeasurement.measured_on.desc(), TreadMeasurement.id.desc())
    ).all()
    depths: dict[WheelPosition, float] = {}
    last: date | None = None
    for m in rows:
        last = last or m.measured_on
        depths.setdefault(m.position, m.depth_mm)
    return depths, last


def tyre_status(db: Session, tyre_set: TyreSet, settings: Settings) -> TyreStatus:
    depths, last = latest_depths(db, tyre_set)
    road = [d for p, d in depths.items() if p in ROAD_POSITIONS]
    min_depth = min(road) if road else None
    return TyreStatus(
        tyre_set_id=tyre_set.id,
        name=tyre_set.name,
        tyre_type=tyre_set.tyre_type,
        last_measured_on=last,
        depths_mm=depths,
        min_depth_mm=min_depth,
        state=tread_state(min_depth, tyre_set.tyre_type, settings),
    )


def oil_status(db: Session, vehicle: Vehicle) -> OilStatus:
    last_change = db.scalars(
        select(MaintenanceRecord)
        .where(
            MaintenanceRecord.vehicle_id == vehicle.id,
            MaintenanceRecord.category == MaintenanceCategory.oil_change,
        )
        .order_by(MaintenanceRecord.performed_on.desc(), MaintenanceRecord.id.desc())
        .limit(1)
    ).first()

    q = select(OilRecord).where(OilRecord.vehicle_id == vehicle.id)
    if last_change:
        q = q.where(OilRecord.added_on >= last_change.performed_on)
    top_ups = db.scalars(q.order_by(OilRecord.added_on.desc())).all()
    added = round(sum(r.amount_l for r in top_ups), 2)

    km_since = None
    consumption = None
    if last_change and last_change.odometer_km is not None and vehicle.odometer_km is not None:
        km_since = vehicle.odometer_km - last_change.odometer_km
        if km_since > 0:
            consumption = round(added / km_since * 1000, 3)

    return OilStatus(
        last_change_on=last_change.performed_on if last_change else None,
        last_change_km=last_change.odometer_km if last_change else None,
        added_since_change_l=added,
        last_top_up_on=top_ups[0].added_on if top_ups else None,
        km_since_change=km_since,
        consumption_l_per_1000km=consumption,
    )


def latest_maintenance(db: Session, vehicle: Vehicle) -> dict[MaintenanceCategory, MaintenanceLatest]:
    """Latest record per category, so consumers can see when something was last done."""
    records = db.scalars(
        select(MaintenanceRecord)
        .where(MaintenanceRecord.vehicle_id == vehicle.id)
        .order_by(MaintenanceRecord.performed_on.desc(), MaintenanceRecord.id.desc())
    ).all()
    result: dict[MaintenanceCategory, MaintenanceLatest] = {}
    for r in records:
        result.setdefault(
            r.category,
            MaintenanceLatest(
                record_id=r.id,
                title=r.title,
                performed_on=r.performed_on,
                odometer_km=r.odometer_km,
                next_due_on=r.next_due_on,
                next_due_km=r.next_due_km,
            ),
        )
    return result


def cost_summary(db: Session, vehicle: Vehicle, settings: Settings, today: date) -> CostSummary:
    by_category: dict[str, Decimal] = {}
    this_year = Decimal("0")

    def add(category: str, amount: Decimal | None, on: date | None) -> None:
        nonlocal this_year
        if amount is None:
            return
        by_category[category] = by_category.get(category, Decimal("0")) + amount
        if on is not None and on.year == today.year:
            this_year += amount

    for m in db.scalars(select(MaintenanceRecord).where(MaintenanceRecord.vehicle_id == vehicle.id)):
        add(m.category.value, m.cost, m.performed_on)
    for o in db.scalars(select(OilRecord).where(OilRecord.vehicle_id == vehicle.id)):
        add("oil_top_up", o.cost, o.added_on)
    for t in db.scalars(select(TyreSet).where(TyreSet.vehicle_id == vehicle.id)):
        add("tyres", t.purchase_cost, t.purchased_on)

    return CostSummary(
        currency=settings.currency,
        total=sum(by_category.values(), Decimal("0")),
        this_year=this_year,
        by_category=by_category,
    )


def vehicle_status(
    db: Session, vehicle: Vehicle, settings: Settings, today: date | None = None
) -> VehicleStatus:
    today = today or date.today()
    mounted = db.scalars(
        select(TyreSet).where(TyreSet.vehicle_id == vehicle.id, TyreSet.is_mounted.is_(True))
    ).first()
    tyres = tyre_status(db, mounted, settings) if mounted else None

    alerts: list[str] = []
    if tyres and tyres.state in ("warning", "critical"):
        alerts.append(f"tread_{tyres.state}")

    return VehicleStatus(
        vehicle_id=vehicle.id,
        name=vehicle.name,
        license_plate=vehicle.license_plate,
        odometer_km=vehicle.odometer_km,
        tyres=tyres,
        oil=oil_status(db, vehicle),
        maintenance=latest_maintenance(db, vehicle),
        costs=cost_summary(db, vehicle, settings, today),
        alerts=alerts,
    )
