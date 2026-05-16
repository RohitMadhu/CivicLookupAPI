import os
from pathlib import Path

from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    DATA_DIR: str = str(Path(__file__).resolve().parent.parent / "data")
    GEOCODER_URL: str = "https://geocoding.geo.census.gov/geocoder/geographies"
    REQUEST_TIMEOUT: int = 30
    DEBUG: bool = False
    GUNICORN_WORKERS: int = 2
    RATE_LIMIT: str = "100 per minute"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

def get_config() -> Settings:
    return Settings()