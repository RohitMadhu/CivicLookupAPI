import json
from functools import lru_cache
from importlib.resources import files

DATA_PACKAGE = "civiclookup.data"

@lru_cache(maxsize=1)
def load_federal_officials() -> dict:
    return json.loads((files(DATA_PACKAGE) / "federal_officials.json").read_text(encoding="utf-8"))

@lru_cache(maxsize=1)
def load_zip_districts() -> dict:
    return json.loads((files(DATA_PACKAGE) / "zip_districts.json").read_text(encoding="utf-8"))

@lru_cache(maxsize=1)
def load_state_officials() -> dict:
    return json.loads((files(DATA_PACKAGE) / "state_officials.json").read_text(encoding="utf-8"))