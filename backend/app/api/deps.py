import secrets
from typing import Annotated

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db import get_db
from app.events import EventBus, get_bus
from app.models import Vehicle

DB = Annotated[Session, Depends(get_db)]
SettingsDep = Annotated[Settings, Depends(get_settings)]
Bus = Annotated[EventBus, Depends(get_bus)]


def require_token(
    settings: SettingsDep, authorization: Annotated[str | None, Header()] = None
) -> None:
    """Bearer-token auth, enabled only when CCT_API_TOKEN is set."""
    if not settings.api_token:
        return
    expected = f"Bearer {settings.api_token}"
    if not authorization or not secrets.compare_digest(authorization, expected):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or missing API token")


def get_vehicle(vehicle_id: int, db: DB) -> Vehicle:
    vehicle = db.get(Vehicle, vehicle_id)
    if vehicle is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Vehicle not found")
    return vehicle


VehicleDep = Annotated[Vehicle, Depends(get_vehicle)]


def get_or_404(db: Session, model: type, obj_id: int, vehicle_id: int | None = None):
    obj = db.get(model, obj_id)
    if obj is None or (vehicle_id is not None and getattr(obj, "vehicle_id", None) != vehicle_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"{model.__name__} not found")
    return obj
