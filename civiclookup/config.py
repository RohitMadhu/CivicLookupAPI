from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
GEOCODER_URL = "https://geocoding.geo.census.gov/geocoder/geographies"
REQUEST_TIMEOUT = 30