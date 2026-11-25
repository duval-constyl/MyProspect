from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Repository root .env (absent inside the Docker image, where Compose injects variables).
ROOT_ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT_ENV_FILE, extra="ignore")

    database_url: str
    home_lat: float
    home_long: float
    pagespeed_api_key: str | None = None
    # France Travail « Offres d'emploi v2 » application (optional, V2 Task 4).
    francetravail_client_id: str | None = None
    francetravail_client_secret: str | None = None

    @field_validator(
        "pagespeed_api_key", "francetravail_client_id", "francetravail_client_secret", mode="before"
    )
    @classmethod
    def _blank_key_is_none(cls, value: str | None) -> str | None:
        return value or None


@lru_cache
def get_settings() -> Settings:
    return Settings()
