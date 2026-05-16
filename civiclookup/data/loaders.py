import json
from functools import lru_cache
from pathlib import Path

# Use the root /data folder (simpler and more reliable for Vercel)
DATA_DIR = Path(__file__).parent.parent.parent / "data"

@lru_cache(maxsize=1)
def load_federal_officials() -> dict:
    with (DATA_DIR / "federal_officials.json").open(encoding="utf-8") as f:
        return json.load(f)

@lru_cache(maxsize=1)
def load_zip_districts() -> dict:
    with (DATA_DIR / "zip_districts.json").open(encoding="utf-8") as f:
        return json.load(f)

@lru_cache(maxsize=1)
def load_state_officials() -> dict:
    with (DATA_DIR / "state_officials.json").open(encoding="utf-8") as f:
        return json.load(f)