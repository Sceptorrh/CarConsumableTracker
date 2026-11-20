from datetime import date

from sqlalchemy.orm import Session

from app.models import OdometerReading, OdometerSource, Vehicle


def record_odometer(
    db: Session,
    vehicle: Vehicle,
    odometer_km: int | None,
    recorded_on: date | None = None,
    source: OdometerSource = OdometerSource.record,
) -> OdometerReading | None:
    """Store a reading and move the vehicle's odometer forward (never backwards).

    Call this from anything that carries an odometer value, so the vehicle's current
    mileage stays up to date without the user having to enter it twice.
    """
    if odometer_km is None:
        return None
    reading = OdometerReading(
        vehicle_id=vehicle.id,
        odometer_km=odometer_km,
        recorded_on=recorded_on or date.today(),
        source=source,
    )
    db.add(reading)
    if vehicle.odometer_km is None or odometer_km > vehicle.odometer_km:
        vehicle.odometer_km = odometer_km
    return reading
