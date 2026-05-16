import json
from functools import lru_cache
from civiclookup.config import get_config

config = get_config()

@lru_cache(maxsize=1)
def load_federal_officials() -> dict:
    with (config.DATA_DIR / "federal_officials.json").open() as f:
        return json.load(f)

@lru_cache(maxsize=1)
def load_zip_districts() -> dict:
    with (config.DATA_DIR / "zip_districts.json").open() as f:
        return json.load(f)

@lru_cache(maxsize=1)
def load_state_officials() -> dict:
    with (config.DATA_DIR / "state_officials.json").open() as f:
        return json.load(f)