from fastapi import APIRouter, BackgroundTasks, status
from sqlalchemy import select

from app.api.deps import DB, Bus, VehicleDep, get_or_404
from app.models import TreadMeasurement, TyreSet
from app.schemas import (
    MountRequest,
    TreadMeasurementCreate,
    TreadMeasurementRead,
    TyreSetCreate,
    TyreSetRead,
    TyreSetUpdate,
)
from app.services import records

router = APIRouter(prefix="/vehicles/{vehicle_id}/tyre-sets", tags=["tyres"])


@router.get("", response_model=list[TyreSetRead])
def list_tyre_sets(vehicle: VehicleDep, db: DB, include_retired: bool = False):
    q = select(TyreSet).where(TyreSet.vehicle_id == vehicle.id).order_by(TyreSet.id)
    if not include_retired:
        q = q.where(TyreSet.retired.is_(False))
    return db.scalars(q).all()


@router.post("", response_model=TyreSetRead, status_code=status.HTTP_201_CREATED)
def create_tyre_set(vehicle: VehicleDep, body: TyreSetCreate, db: DB):
    return records.create_tyre_set(db, vehicle, body)


@router.get("/{tyre_set_id}", response_model=TyreSetRead)
def get_tyre_set(vehicle: VehicleDep, tyre_set_id: int, db: DB):
    return get_or_404(db, TyreSet, tyre_set_id, vehicle.id)


@router.patch("/{tyre_set_id}", response_model=TyreSetRead)
def update_tyre_set(vehicle: VehicleDep, tyre_set_id: int, body: TyreSetUpdate, db: DB):
    return records.apply_update(db, get_or_404(db, TyreSet, tyre_set_id, vehicle.id), body)


@router.delete("/{tyre_set_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_tyre_set(vehicle: VehicleDep, tyre_set_id: int, db: DB):
    records.delete(db, get_or_404(db, TyreSet, tyre_set_id, vehicle.id))


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
    return records.mount_tyre_set(db, bus, background, vehicle, tyre_set, body)


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
    return records.add_tread_measurements(db, bus, background, vehicle, tyre_set, body)
