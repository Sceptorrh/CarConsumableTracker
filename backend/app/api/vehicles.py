from fastapi import APIRouter, BackgroundTasks, status
from sqlalchemy import select

from app.api.deps import DB, Bus, SettingsDep, VehicleDep
from app.models import OdometerReading, Vehicle
from app.schemas import (
    OdometerCreate,
    OdometerRead,
    VehicleCreate,
    VehicleRead,
    VehicleStatus,
    VehicleUpdate,
)
from app.services import records
from app.services.status import vehicle_status

router = APIRouter(prefix="/vehicles", tags=["vehicles"])


@router.get("", response_model=list[VehicleRead])
def list_vehicles(db: DB, include_archived: bool = False):
    q = select(Vehicle).order_by(Vehicle.name)
    if not include_archived:
        q = q.where(Vehicle.archived.is_(False))
    return db.scalars(q).all()


@router.post("", response_model=VehicleRead, status_code=status.HTTP_201_CREATED)
def create_vehicle(body: VehicleCreate, db: DB, bus: Bus, background: BackgroundTasks):
    return records.create_vehicle(db, bus, background, body)


@router.get("/{vehicle_id}", response_model=VehicleRead)
def get_vehicle(vehicle: VehicleDep):
    return vehicle


@router.patch("/{vehicle_id}", response_model=VehicleRead)
def update_vehicle(vehicle: VehicleDep, body: VehicleUpdate, db: DB):
    return records.apply_update(db, vehicle, body)


@router.delete("/{vehicle_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_vehicle(vehicle: VehicleDep, db: DB):
    records.delete(db, vehicle)


@router.get("/{vehicle_id}/odometer", response_model=list[OdometerRead])
def list_odometer(vehicle: VehicleDep, db: DB):
    return db.scalars(
        select(OdometerReading)
        .where(OdometerReading.vehicle_id == vehicle.id)
        .order_by(OdometerReading.recorded_on.desc(), OdometerReading.id.desc())
    ).all()


@router.post("/{vehicle_id}/odometer", response_model=OdometerRead, status_code=201)
def add_odometer(
    vehicle: VehicleDep, body: OdometerCreate, db: DB, bus: Bus, background: BackgroundTasks
):
    """Add a mileage reading. Home Assistant can push this from a car integration."""
    return records.add_odometer(db, bus, background, vehicle, body)


@router.get("/{vehicle_id}/status", response_model=VehicleStatus)
def get_status(vehicle: VehicleDep, db: DB, settings: SettingsDep):
    """Flat summary designed for dashboards and Home Assistant REST sensors."""
    return vehicle_status(db, vehicle, settings)
