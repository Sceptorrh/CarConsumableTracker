"""Database models.

Conventions:
- distances in kilometres (``*_km``), volumes in litres (``*_l``), tread in millimetres
- money stored as Numeric(10, 2) in the configured currency
- every record that happens "on the car" carries a date and an optional odometer reading
"""

import enum
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

Money = Numeric(10, 2)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class FuelType(str, enum.Enum):
    petrol = "petrol"
    diesel = "diesel"
    hybrid = "hybrid"
    plugin_hybrid = "plugin_hybrid"
    electric = "electric"
    lpg = "lpg"
    other = "other"


class TyreType(str, enum.Enum):
    summer = "summer"
    winter = "winter"
    all_season = "all_season"


class WheelPosition(str, enum.Enum):
    front_left = "front_left"
    front_right = "front_right"
    rear_left = "rear_left"
    rear_right = "rear_right"
    spare = "spare"


class MaintenanceCategory(str, enum.Enum):
    service = "service"
    oil_change = "oil_change"
    tyre_change = "tyre_change"
    brakes = "brakes"
    inspection = "inspection"  # e.g. APK / MOT / TÜV
    battery = "battery"
    filters = "filters"
    fluids = "fluids"
    repair = "repair"
    other = "other"


class OdometerSource(str, enum.Enum):
    manual = "manual"
    record = "record"  # derived from a tyre/oil/maintenance record
    integration = "integration"  # pushed by e.g. Home Assistant


def _enum(cls: type[enum.Enum]) -> Enum:
    # Store enum *values* as plain strings; no native DB enum to keep migrations simple.
    return Enum(cls, native_enum=False, length=32, values_callable=lambda e: [m.value for m in e])


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )


class Vehicle(TimestampMixin, Base):
    __tablename__ = "vehicles"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    make: Mapped[str | None] = mapped_column(String(100))
    model: Mapped[str | None] = mapped_column(String(100))
    year: Mapped[int | None] = mapped_column(Integer)
    license_plate: Mapped[str | None] = mapped_column(String(20))
    vin: Mapped[str | None] = mapped_column(String(32))
    fuel_type: Mapped[FuelType | None] = mapped_column(_enum(FuelType))
    odometer_km: Mapped[int | None] = mapped_column(Integer)
    # Recommended engine oil, e.g. "5W-30 VW 504.00"
    oil_spec: Mapped[str | None] = mapped_column(String(100))
    notes: Mapped[str | None] = mapped_column(Text)
    archived: Mapped[bool] = mapped_column(Boolean, default=False)

    tyre_sets: Mapped[list["TyreSet"]] = relationship(
        back_populates="vehicle", cascade="all, delete-orphan"
    )
    oil_records: Mapped[list["OilRecord"]] = relationship(
        back_populates="vehicle", cascade="all, delete-orphan"
    )
    maintenance_records: Mapped[list["MaintenanceRecord"]] = relationship(
        back_populates="vehicle", cascade="all, delete-orphan"
    )
    odometer_readings: Mapped[list["OdometerReading"]] = relationship(
        back_populates="vehicle", cascade="all, delete-orphan"
    )


class OdometerReading(Base):
    __tablename__ = "odometer_readings"

    id: Mapped[int] = mapped_column(primary_key=True)
    vehicle_id: Mapped[int] = mapped_column(ForeignKey("vehicles.id", ondelete="CASCADE"), index=True)
    recorded_on: Mapped[date] = mapped_column(Date)
    odometer_km: Mapped[int] = mapped_column(Integer)
    source: Mapped[OdometerSource] = mapped_column(_enum(OdometerSource), default=OdometerSource.manual)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    vehicle: Mapped[Vehicle] = relationship(back_populates="odometer_readings")


class TyreSet(TimestampMixin, Base):
    """A set of (usually four) tyres. Cars often have a summer and a winter set that get swapped."""

    __tablename__ = "tyre_sets"

    id: Mapped[int] = mapped_column(primary_key=True)
    vehicle_id: Mapped[int] = mapped_column(ForeignKey("vehicles.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(100))
    tyre_type: Mapped[TyreType] = mapped_column(_enum(TyreType))
    brand: Mapped[str | None] = mapped_column(String(100))
    model: Mapped[str | None] = mapped_column(String(100))
    size: Mapped[str | None] = mapped_column(String(50))  # e.g. "205/55 R16 91V"
    dot_code: Mapped[str | None] = mapped_column(String(20))  # production week/year, e.g. "2324"
    purchased_on: Mapped[date | None] = mapped_column(Date)
    purchase_cost: Mapped[Decimal | None] = mapped_column(Money)
    is_mounted: Mapped[bool] = mapped_column(Boolean, default=False)
    retired: Mapped[bool] = mapped_column(Boolean, default=False)
    notes: Mapped[str | None] = mapped_column(Text)

    vehicle: Mapped[Vehicle] = relationship(back_populates="tyre_sets")
    measurements: Mapped[list["TreadMeasurement"]] = relationship(
        back_populates="tyre_set", cascade="all, delete-orphan"
    )


class TreadMeasurement(Base):
    """Tread depth of one wheel position at one moment."""

    __tablename__ = "tread_measurements"

    id: Mapped[int] = mapped_column(primary_key=True)
    tyre_set_id: Mapped[int] = mapped_column(ForeignKey("tyre_sets.id", ondelete="CASCADE"), index=True)
    measured_on: Mapped[date] = mapped_column(Date)
    odometer_km: Mapped[int | None] = mapped_column(Integer)
    position: Mapped[WheelPosition] = mapped_column(_enum(WheelPosition))
    depth_mm: Mapped[float] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    tyre_set: Mapped[TyreSet] = relationship(back_populates="measurements")


class OilRecord(TimestampMixin, Base):
    """Engine oil added between oil changes (top-ups). Full oil changes are maintenance records."""

    __tablename__ = "oil_records"

    id: Mapped[int] = mapped_column(primary_key=True)
    vehicle_id: Mapped[int] = mapped_column(ForeignKey("vehicles.id", ondelete="CASCADE"), index=True)
    added_on: Mapped[date] = mapped_column(Date)
    odometer_km: Mapped[int | None] = mapped_column(Integer)
    amount_l: Mapped[float] = mapped_column(Float)
    oil_spec: Mapped[str | None] = mapped_column(String(100))
    cost: Mapped[Decimal | None] = mapped_column(Money)
    notes: Mapped[str | None] = mapped_column(Text)

    vehicle: Mapped[Vehicle] = relationship(back_populates="oil_records")


class MaintenanceRecord(TimestampMixin, Base):
    __tablename__ = "maintenance_records"

    id: Mapped[int] = mapped_column(primary_key=True)
    vehicle_id: Mapped[int] = mapped_column(ForeignKey("vehicles.id", ondelete="CASCADE"), index=True)
    performed_on: Mapped[date] = mapped_column(Date)
    odometer_km: Mapped[int | None] = mapped_column(Integer)
    category: Mapped[MaintenanceCategory] = mapped_column(_enum(MaintenanceCategory))
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    cost: Mapped[Decimal | None] = mapped_column(Money)
    provider: Mapped[str | None] = mapped_column(String(200))  # garage / "DIY"
    # Optional next occurrence. Stored and exposed as-is; deciding "due"/"overdue" is up to
    # the consumer (e.g. Home Assistant automations).
    next_due_on: Mapped[date | None] = mapped_column(Date)
    next_due_km: Mapped[int | None] = mapped_column(Integer)
    notes: Mapped[str | None] = mapped_column(Text)

    vehicle: Mapped[Vehicle] = relationship(back_populates="maintenance_records")
