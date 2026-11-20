from fastapi import APIRouter, BackgroundTasks, status
from sqlalchemy import select

from app.api.deps import DB, Bus, VehicleDep, get_or_404
from app.events import Event
from app.models import OilRecord
from app.schemas import OilRecordCreate, OilRecordRead
from app.services.odometer import record_odometer

router = APIRouter(prefix="/vehicles/{vehicle_id}/oil", tags=["oil"])


@router.get("", response_model=list[OilRecordRead])
def list_oil(vehicle: VehicleDep, db: DB):
    return db.scalars(
        select(OilRecord)
        .where(OilRecord.vehicle_id == vehicle.id)
        .order_by(OilRecord.added_on.desc(), OilRecord.id.desc())
    ).all()


@router.post("", response_model=OilRecordRead, status_code=status.HTTP_201_CREATED)
def add_oil(vehicle: VehicleDep, body: OilRecordCreate, db: DB, bus: Bus, background: BackgroundTasks):
    record = OilRecord(vehicle_id=vehicle.id, **body.model_dump())
    if record.oil_spec is None:
        record.oil_spec = vehicle.oil_spec
    db.add(record)
    record_odometer(db, vehicle, body.odometer_km, body.added_on)
    db.commit()
    bus.publish(background, Event("oil_added", vehicle.id, {"amount_l": record.amount_l, "odometer_km": record.odometer_km}))
    return record


@router.delete("/{record_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_oil(vehicle: VehicleDep, record_id: int, db: DB):
    db.delete(get_or_404(db, OilRecord, record_id, vehicle.id))
    db.commit()
