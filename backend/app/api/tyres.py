from datetime import date

from fastapi import APIRouter, BackgroundTasks, status
from sqlalchemy import select, update

from app.api.deps import DB, Bus, VehicleDep, get_or_404
from app.events import Event
from app.models import TreadMeasurement, TyreSet
from app.schemas import (
    MountRequest,
    TreadMeasurementCreate,
    TreadMeasurementRead,
    TyreSetCreate,
    TyreSetRead,
    TyreSetUpdate,
)
from app.services.odometer import record_odometer
from app.services.status import tyre_status

router = APIRouter(prefix="/vehicles/{vehicle_id}/tyre-sets", tags=["tyres"])


def _unmount_all(db, vehicle_id: int) -> None:
    db.execute(update(TyreSet).where(TyreSet.vehicle_id == vehicle_id).values(is_mounted=False))


@router.get("", response_model=list[TyreSetRead])
def list_tyre_sets(vehicle: VehicleDep, db: DB, include_retired: bool = False):
    q = select(TyreSet).where(TyreSet.vehicle_id == vehicle.id).order_by(TyreSet.id)
    if not include_retired:
        q = q.where(TyreSet.retired.is_(False))
    return db.scalars(q).all()


@router.post("", response_model=TyreSetRead, status_code=status.HTTP_201_CREATED)
def create_tyre_set(vehicle: VehicleDep, body: TyreSetCreate, db: DB):
    if body.is_mounted:
        _unmount_all(db, vehicle.id)
    tyre_set = TyreSet(vehicle_id=vehicle.id, **body.model_dump())
    db.add(tyre_set)
    db.commit()
    return tyre_set


@router.get("/{tyre_set_id}", response_model=TyreSetRead)
def get_tyre_set(vehicle: VehicleDep, tyre_set_id: int, db: DB):
    return get_or_404(db, TyreSet, tyre_set_id, vehicle.id)


@router.patch("/{tyre_set_id}", response_model=TyreSetRead)
def update_tyre_set(vehicle: VehicleDep, tyre_set_id: int, body: TyreSetUpdate, db: DB):
    tyre_set = get_or_404(db, TyreSet, tyre_set_id, vehicle.id)
    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(tyre_set, key, value)
    if tyre_set.retired:
        tyre_set.is_mounted = False
    db.commit()
    return tyre_set


@router.delete("/{tyre_set_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_tyre_set(vehicle: VehicleDep, tyre_set_id: int, db: DB):
    db.delete(get_or_404(db, TyreSet, tyre_set_id, vehicle.id))
    db.commit()


@router.post("/{tyre_set_id}/mount", response_model=TyreSetRead)
def mount_tyre_set(
    vehicle: VehicleDep,
    tyre_set_id: int,
    body: MountRequest,
    db: DB,
    bus: Bus,
    background: BackgroundTasks,
):
    """Mark this set as the one on the car (e.g. seasonal summer/winter swap)."""
    tyre_set = get_or_404(db, TyreSet, tyre_set_id, vehicle.id)
    _unmount_all(db, vehicle.id)
    tyre_set.is_mounted = True
    tyre_set.retired = False
    record_odometer(db, vehicle, body.odometer_km, body.mounted_on)
    db.commit()
    db.refresh(tyre_set)
    bus.publish(
        background,
        Event(
            "tyres_mounted",
            vehicle.id,
            {"tyre_set_id": tyre_set.id, "name": tyre_set.name, "tyre_type": tyre_set.tyre_type},
        ),
    )
    return tyre_set


@router.get("/{tyre_set_id}/measurements", response_model=list[TreadMeasurementRead])
def list_measurements(vehicle: VehicleDep, tyre_set_id: int, db: DB):
    get_or_404(db, TyreSet, tyre_set_id, vehicle.id)
    return db.scalars(
        select(TreadMeasurement)
        .where(TreadMeasurement.tyre_set_id == tyre_set_id)
        .order_by(TreadMeasurement.measured_on.desc(), TreadMeasurement.position)
    ).all()


@router.post(
    "/{tyre_set_id}/measurements",
    response_model=list[TreadMeasurementRead],
    status_code=status.HTTP_201_CREATED,
)
def add_measurements(
    vehicle: VehicleDep,
    tyre_set_id: int,
    body: TreadMeasurementCreate,
    db: DB,
    bus: Bus,
    background: BackgroundTasks,
):
    """Record tread depth per wheel, e.g. {"depths_mm": {"front_left": 6.1, "front_right": 6.0}}."""
    tyre_set = get_or_404(db, TyreSet, tyre_set_id, vehicle.id)
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
    bus.publish(background, Event("tread_measured", vehicle.id, payload))
    return rows
