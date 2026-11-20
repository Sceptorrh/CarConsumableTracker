"""Write operations shared by the REST API and the web UI.

Each function changes the database, commits, and publishes the matching domain event, so
both front doors behave identically (same odometer updates, same Home Assistant events).
"""

from datetime import date

from fastapi import BackgroundTasks
from pydantic import BaseModel
from sqlalchemy import update
from sqlalchemy.orm import Session

from app.events import Event, EventBus
from app.models import (
    MaintenanceRecord,
    OdometerReading,
    OdometerSource,
    OilRecord,
    TreadMeasurement,
    TyreSet,
    Vehicle,
)
from app.schemas import (
    MaintenanceCreate,
    MountRequest,
    OdometerCreate,
    OilRecordCreate,
    TreadMeasurementCreate,
    TyreSetCreate,
    VehicleCreate,
)
from app.services.odometer import record_odometer
from app.services.status import tyre_status


def apply_update[T](db: Session, obj: T, body: BaseModel) -> T:
    """PATCH semantics: only fields that were sent are changed."""
    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(obj, key, value)
    if isinstance(obj, TyreSet) and obj.retired:
        obj.is_mounted = False
    db.commit()
    return obj


def delete(db: Session, obj) -> None:
    db.delete(obj)
    db.commit()


def create_vehicle(db: Session, bus: EventBus, bg: BackgroundTasks, body: VehicleCreate) -> Vehicle:
    vehicle = Vehicle(**body.model_dump(exclude={"odometer_km"}))
    db.add(vehicle)
    db.flush()
    record_odometer(db, vehicle, body.odometer_km, source=OdometerSource.manual)
    db.commit()
    bus.publish(bg, Event("vehicle_created", vehicle.id, {"name": vehicle.name}))
    return vehicle


def add_odometer(
    db: Session, bus: EventBus, bg: BackgroundTasks, vehicle: Vehicle, body: OdometerCreate
) -> OdometerReading:
    reading = record_odometer(db, vehicle, body.odometer_km, body.recorded_on, body.source)
    db.commit()
    bus.publish(bg, Event("odometer_updated", vehicle.id, {"odometer_km": vehicle.odometer_km}))
    return reading


def _unmount_all(db: Session, vehicle_id: int) -> None:
    db.execute(update(TyreSet).where(TyreSet.vehicle_id == vehicle_id).values(is_mounted=False))


def create_tyre_set(db: Session, vehicle: Vehicle, body: TyreSetCreate) -> TyreSet:
    if body.is_mounted:
        _unmount_all(db, vehicle.id)
    tyre_set = TyreSet(vehicle_id=vehicle.id, **body.model_dump())
    db.add(tyre_set)
    db.commit()
    return tyre_set


def mount_tyre_set(
    db: Session,
    bus: EventBus,
    bg: BackgroundTasks,
    vehicle: Vehicle,
    tyre_set: TyreSet,
    body: MountRequest,
) -> TyreSet:
    _unmount_all(db, vehicle.id)
    tyre_set.is_mounted = True
    tyre_set.retired = False
    record_odometer(db, vehicle, body.odometer_km, body.mounted_on)
    db.commit()
    db.refresh(tyre_set)
    bus.publish(
        bg,
        Event(
            "tyres_mounted",
            vehicle.id,
            {"tyre_set_id": tyre_set.id, "name": tyre_set.name, "tyre_type": tyre_set.tyre_type},
        ),
    )
    return tyre_set


def add_tread_measurements(
    db: Session,
    bus: EventBus,
    bg: BackgroundTasks,
    vehicle: Vehicle,
    tyre_set: TyreSet,
    body: TreadMeasurementCreate,
) -> list[TreadMeasurement]:
    measured_on = body.measured_on or date.today()
    rows = [
        TreadMeasurement(
            tyre_set_id=tyre_set.id,
            measured_on=measured_on,
            odometer_km=body.odometer_km,
            position=position,
            depth_mm=depth,
        )
        for position, depth in body.depths_mm.items()
    ]
    db.add_all(rows)
    record_odometer(db, vehicle, body.odometer_km, measured_on)
    db.commit()

    st = tyre_status(db, tyre_set)
    payload = {
        "tyre_set_id": tyre_set.id,
        "tyre_type": tyre_set.tyre_type,
        "depths_mm": st.depths_mm,
        "min_depth_mm": st.min_depth_mm,
    }
    bus.publish(bg, Event("tread_measured", vehicle.id, payload))
    return rows


def add_oil(
    db: Session, bus: EventBus, bg: BackgroundTasks, vehicle: Vehicle, body: OilRecordCreate
) -> OilRecord:
    record = OilRecord(vehicle_id=vehicle.id, **body.model_dump())
    if record.oil_spec is None:
        record.oil_spec = vehicle.oil_spec
    db.add(record)
    record_odometer(db, vehicle, body.odometer_km, body.added_on)
    db.commit()
    bus.publish(
        bg,
        Event("oil_added", vehicle.id, {"amount_l": record.amount_l, "odometer_km": record.odometer_km}),
    )
    return record


def add_maintenance(
    db: Session, bus: EventBus, bg: BackgroundTasks, vehicle: Vehicle, body: MaintenanceCreate
) -> MaintenanceRecord:
    record = MaintenanceRecord(vehicle_id=vehicle.id, **body.model_dump())
    db.add(record)
    record_odometer(db, vehicle, body.odometer_km, body.performed_on)
    db.commit()
    bus.publish(
        bg,
        Event(
            "maintenance_added",
            vehicle.id,
            {"record_id": record.id, "category": record.category, "title": record.title, "cost": record.cost},
        ),
    )
    return record
