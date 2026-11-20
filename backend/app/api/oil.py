from fastapi import APIRouter, BackgroundTasks, status
from sqlalchemy import select

from app.api.deps import DB, Bus, VehicleDep, get_or_404
from app.models import OilRecord
from app.schemas import OilRecordCreate, OilRecordRead
from app.services import records

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
    return records.add_oil(db, bus, background, vehicle, body)


@router.delete("/{record_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_oil(vehicle: VehicleDep, record_id: int, db: DB):
    records.delete(db, get_or_404(db, OilRecord, record_id, vehicle.id))
