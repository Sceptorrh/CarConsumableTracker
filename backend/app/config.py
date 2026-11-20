from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings, read from environment variables prefixed with CCT_."""

    model_config = SettingsConfigDict(env_prefix="CCT_", env_file=".env", extra="ignore")

    # Set at image build time (git tag or commit); shown in the UI footer.
    version: str = "dev"

    database_url: str = "sqlite:///./data/cct.db"

    # When set, every /api request must send "Authorization: Bearer <token>".
    api_token: str | None = None

    currency: str = "EUR"

    # Outbound events: Home Assistant webhook URL, e.g.
    # http://homeassistant.local:8123/api/webhook/car_consumable_tracker
    ha_webhook_url: str | None = None
    webhook_timeout_s: float = 5.0


@lru_cache
def get_settings() -> Settings:
    return Settings()
