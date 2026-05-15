import json
from pathlib import Path
from functools import lru_cache

from civiclookup.config import DATA_DIR

@lru_cache(maxsize=1)
def load_federal_officials() -> dict:
    path = DATA_DIR / "federal_officials.json"
    with path.open() as f:
        return json.load(f)

@lru_cache(maxsize=1)
def load_zip_districts() -> dict:
    path = DATA_DIR / "zip_districts.json"
    with path.open() as f:
        return json.load(f)

@lru_cache(maxsize=1)
def load_state_officials() -> dict:
    path = DATA_DIR / "state_officials.json"
    with path.open() as f:
        return json.load(f)