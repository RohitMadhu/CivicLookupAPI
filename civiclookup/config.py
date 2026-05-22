import os
from pathlib import Path

try:
    from pydantic_settings import BaseSettings
except ModuleNotFoundError:
    BaseSettings = None


DEFAULT_DATA_DIR = Path(__file__).resolve().parent / "data"
DEFAULT_GEOCODER_URL = "https://geocoding.geo.census.gov/geocoder/geographies"
DEFAULT_REQUEST_TIMEOUT = 30
DEFAULT_GUNICORN_WORKERS = 2
DEFAULT_RATE_LIMIT = "100 per minute"


def _env_bool(name: str, default: bool) -> bool:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    return raw_value.strip().lower() in {"1", "true", "yes", "on"}


if BaseSettings is not None:
    class Settings(BaseSettings):
        DATA_DIR: Path = DEFAULT_DATA_DIR
        GEOCODER_URL: str = DEFAULT_GEOCODER_URL
        REQUEST_TIMEOUT: int = DEFAULT_REQUEST_TIMEOUT
        DEBUG: bool = False
        GUNICORN_WORKERS: int = DEFAULT_GUNICORN_WORKERS
        RATE_LIMIT: str = DEFAULT_RATE_LIMIT

        class Config:
            env_file = ".env"
            env_file_encoding = "utf-8"
else:
    class Settings:
        def __init__(self):
            self.DATA_DIR = Path(os.getenv("DATA_DIR", str(DEFAULT_DATA_DIR)))
            self.GEOCODER_URL = os.getenv("GEOCODER_URL", DEFAULT_GEOCODER_URL)
            self.REQUEST_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", str(DEFAULT_REQUEST_TIMEOUT)))
            self.DEBUG = _env_bool("DEBUG", False)
            self.GUNICORN_WORKERS = int(
                os.getenv("GUNICORN_WORKERS", str(DEFAULT_GUNICORN_WORKERS))
            )
            self.RATE_LIMIT = os.getenv("RATE_LIMIT", DEFAULT_RATE_LIMIT)


def get_config() -> Settings:
    return Settings()
