from fastapi import APIRouter, BackgroundTasks, status
from sqlalchemy import select

from app.api.deps import DB, Bus, VehicleDep, get_or_404
from app.events import Event
from app.models import MaintenanceCategory, MaintenanceRecord
from app.schemas import MaintenanceCreate, MaintenanceRead, MaintenanceUpdate
from app.services.odometer import record_odometer

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
    record = MaintenanceRecord(vehicle_id=vehicle.id, **body.model_dump())
    db.add(record)
    record_odometer(db, vehicle, body.odometer_km, body.performed_on)
    db.commit()
    bus.publish(
        background,
        Event("maintenance_added", vehicle.id, {"record_id": record.id, "category": record.category, "title": record.title, "cost": record.cost}),
    )
    return record


@router.get("/{record_id}", response_model=MaintenanceRead)
def get_maintenance(vehicle: VehicleDep, record_id: int, db: DB):
    return get_or_404(db, MaintenanceRecord, record_id, vehicle.id)


@router.patch("/{record_id}", response_model=MaintenanceRead)
def update_maintenance(vehicle: VehicleDep, record_id: int, body: MaintenanceUpdate, db: DB):
    record = get_or_404(db, MaintenanceRecord, record_id, vehicle.id)
    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(record, key, value)
    db.commit()
    return record


@router.delete("/{record_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_maintenance(vehicle: VehicleDep, record_id: int, db: DB):
    db.delete(get_or_404(db, MaintenanceRecord, record_id, vehicle.id))
    db.commit()
