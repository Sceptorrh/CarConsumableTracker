from fastapi import APIRouter, BackgroundTasks, status
from sqlalchemy import select

from app.api.deps import DB, Bus, VehicleDep, get_or_404
from app.models import MaintenanceCategory, MaintenanceRecord
from app.schemas import MaintenanceCreate, MaintenanceRead, MaintenanceUpdate
from app.services import records

router = APIRouter(prefix="/vehicles/{vehicle_id}/maintenance", tags=["maintenance"])


@router.get("", response_model=list[MaintenanceRead])
def list_maintenance(vehicle: VehicleDep, db: DB, category: MaintenanceCategory | None = None):
    q = select(MaintenanceRecord).where(MaintenanceRecord.vehicle_id == vehicle.id)
    if category:
        q = q.where(MaintenanceRecord.category == category)
    return db.scalars(q.order_by(MaintenanceRecord.performed_on.desc(), MaintenanceRecord.id.desc())).all()


@router.post("", response_model=MaintenanceRead, status_code=status.HTTP_201_CREATED)
def add_maintenance(
    vehicle: VehicleDep, body: MaintenanceCreate, db: DB, bus: Bus, background: BackgroundTasks
):
    return records.add_maintenance(db, bus, background, vehicle, body)


@router.get("/{record_id}", response_model=MaintenanceRead)
def get_maintenance(vehicle: VehicleDep, record_id: int, db: DB):
    return get_or_404(db, MaintenanceRecord, record_id, vehicle.id)


@router.patch("/{record_id}", response_model=MaintenanceRead)
def update_maintenance(vehicle: VehicleDep, record_id: int, body: MaintenanceUpdate, db: DB):
    return records.apply_update(db, get_or_404(db, MaintenanceRecord, record_id, vehicle.id), body)


@router.delete("/{record_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_maintenance(vehicle: VehicleDep, record_id: int, db: DB):
    records.delete(db, get_or_404(db, MaintenanceRecord, record_id, vehicle.id))
