import json
from functools import lru_cache
from civiclookup.config import DATA_DIR

@lru_cache(maxsize=1)
def load_federal_officials() -> dict:
    with (DATA_DIR / "federal_officials.json").open() as f:
        return json.load(f)

@lru_cache(maxsize=1)
def load_zip_districts() -> dict:
    with (DATA_DIR / "zip_districts.json").open() as f:
        return json.load(f)

@lru_cache(maxsize=1)
def load_state_officials() -> dict:
    with (DATA_DIR / "state_officials.json").open() as f:
        return json.load(f)