"""Pydantic schemas for the REST API (request + response bodies)."""

from datetime import date, datetime
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from app.models import FuelType, MaintenanceCategory, OdometerSource, TyreType, WheelPosition

Km = Annotated[int, Field(ge=0)]
Cost = Annotated[Decimal, Field(ge=0, max_digits=10, decimal_places=2)]


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---------- Vehicles ----------


class VehicleBase(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    make: str | None = None
    model: str | None = None
    year: int | None = Field(default=None, ge=1886, le=2100)
    license_plate: str | None = None
    vin: str | None = None
    fuel_type: FuelType | None = None
    oil_spec: str | None = None
    notes: str | None = None


class VehicleCreate(VehicleBase):
    odometer_km: Km | None = None


class VehicleUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    make: str | None = None
    model: str | None = None
    year: int | None = Field(default=None, ge=1886, le=2100)
    license_plate: str | None = None
    vin: str | None = None
    fuel_type: FuelType | None = None
    oil_spec: str | None = None
    notes: str | None = None
    archived: bool | None = None


class VehicleRead(VehicleBase, ORM):
    id: int
    odometer_km: int | None
    archived: bool
    created_at: datetime
    updated_at: datetime


# ---------- Odometer ----------


class OdometerCreate(BaseModel):
    odometer_km: Km
    recorded_on: date | None = None  # defaults to today
    source: OdometerSource = OdometerSource.manual


class OdometerRead(ORM):
    id: int
    vehicle_id: int
    recorded_on: date
    odometer_km: int
    source: OdometerSource


# ---------- Tyres ----------


class TyreSetBase(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    tyre_type: TyreType
    brand: str | None = None
    model: str | None = None
    size: str | None = None
    dot_code: str | None = None
    purchased_on: date | None = None
    purchase_cost: Cost | None = None
    notes: str | None = None


class TyreSetCreate(TyreSetBase):
    is_mounted: bool = False


class TyreSetUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    tyre_type: TyreType | None = None
    brand: str | None = None
    model: str | None = None
    size: str | None = None
    dot_code: str | None = None
    purchased_on: date | None = None
    purchase_cost: Cost | None = None
    retired: bool | None = None
    notes: str | None = None


class TyreSetRead(TyreSetBase, ORM):
    id: int
    vehicle_id: int
    is_mounted: bool
    retired: bool


class TreadMeasurementCreate(BaseModel):
    """Record tread depth for one or more wheel positions in one go."""

    measured_on: date | None = None  # defaults to today
    odometer_km: Km | None = None
    depths_mm: dict[WheelPosition, Annotated[float, Field(ge=0, le=30)]] = Field(min_length=1)


class TreadMeasurementRead(ORM):
    id: int
    tyre_set_id: int
    measured_on: date
    odometer_km: int | None
    position: WheelPosition
    depth_mm: float


class MountRequest(BaseModel):
    """Mount a tyre set. Other sets on the same vehicle are unmounted automatically."""

    mounted_on: date | None = None
    odometer_km: Km | None = None


# ---------- Oil ----------


class OilRecordBase(BaseModel):
    added_on: date
    odometer_km: Km | None = None
    amount_l: float = Field(gt=0, le=20)
    oil_spec: str | None = None
    cost: Cost | None = None
    notes: str | None = None


class OilRecordCreate(OilRecordBase):
    pass


class OilRecordRead(OilRecordBase, ORM):
    id: int
    vehicle_id: int


# ---------- Maintenance ----------


class MaintenanceBase(BaseModel):
    performed_on: date
    odometer_km: Km | None = None
    category: MaintenanceCategory
    title: str = Field(min_length=1, max_length=200)
    description: str | None = None
    cost: Cost | None = None
    provider: str | None = None
    next_due_on: date | None = None
    next_due_km: Km | None = None
    notes: str | None = None


class MaintenanceCreate(MaintenanceBase):
    pass


class MaintenanceUpdate(BaseModel):
    performed_on: date | None = None
    odometer_km: Km | None = None
    category: MaintenanceCategory | None = None
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    cost: Cost | None = None
    provider: str | None = None
    next_due_on: date | None = None
    next_due_km: Km | None = None
    notes: str | None = None


class MaintenanceRead(MaintenanceBase, ORM):
    id: int
    vehicle_id: int


# ---------- Status (flat, automation-friendly) ----------


class TyreStatus(BaseModel):
    tyre_set_id: int
    name: str
    tyre_type: TyreType
    last_measured_on: date | None
    depths_mm: dict[WheelPosition, float]
    min_depth_mm: float | None


class OilStatus(BaseModel):
    last_change_on: date | None
    last_change_km: int | None
    added_since_change_l: float
    last_top_up_on: date | None
    km_since_change: int | None
    consumption_l_per_1000km: float | None


class MaintenanceLatest(BaseModel):
    """Most recent maintenance record of one category, with its (raw) next-due values."""

    record_id: int
    title: str
    performed_on: date
    odometer_km: int | None
    next_due_on: date | None
    next_due_km: int | None


class CostSummary(BaseModel):
    currency: str
    total: Decimal
    this_year: Decimal
    by_category: dict[str, Decimal]


class VehicleStatus(BaseModel):
    vehicle_id: int
    name: str
    license_plate: str | None
    odometer_km: int | None
    tyres: TyreStatus | None
    oil: OilStatus
    maintenance: dict[MaintenanceCategory, MaintenanceLatest]
    costs: CostSummary
