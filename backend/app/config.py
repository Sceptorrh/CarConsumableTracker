from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings, read from environment variables prefixed with CCT_."""

    model_config = SettingsConfigDict(env_prefix="CCT_", env_file=".env", extra="ignore")

    database_url: str = "sqlite:///./data/cct.db"

    # When set, every /api request must send "Authorization: Bearer <token>".
    api_token: str | None = None

    currency: str = "EUR"

    # Tread depth thresholds in mm. Below "warning" -> warning, below "critical" -> critical.
    tread_warning_mm: float = 3.0
    tread_warning_winter_mm: float = 4.0
    tread_critical_mm: float = 1.6

    # Maintenance items due within this window are reported as "due_soon".
    maintenance_due_soon_days: int = 30
    maintenance_due_soon_km: int = 1000

    # Outbound events: Home Assistant webhook URL, e.g.
    # http://homeassistant.local:8123/api/webhook/car_consumable_tracker
    ha_webhook_url: str | None = None
    webhook_timeout_s: float = 5.0


@lru_cache
def get_settings() -> Settings:
    return Settings()
