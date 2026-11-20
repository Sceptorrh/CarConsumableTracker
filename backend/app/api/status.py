from fastapi import APIRouter
from sqlalchemy import select

from app.api.deps import DB, SettingsDep
from app.models import Vehicle
from app.schemas import VehicleStatus
from app.services.status import vehicle_status

router = APIRouter(tags=["status"])


@router.get("/status", response_model=list[VehicleStatus])
def all_status(db: DB, settings: SettingsDep):
    """Status of every active vehicle in one call (one HA REST request for all sensors)."""
    vehicles = db.scalars(select(Vehicle).where(Vehicle.archived.is_(False)).order_by(Vehicle.id)).all()
    return [vehicle_status(db, v, settings) for v in vehicles]
