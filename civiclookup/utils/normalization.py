import re
from typing import Optional

STATE_NAMES = {
    "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas",
    "CA": "California", "CO": "Colorado", "CT": "Connecticut", "DE": "Delaware",
    "FL": "Florida", "GA": "Georgia", "HI": "Hawaii", "ID": "Idaho",
    "IL": "Illinois", "IN": "Indiana", "IA": "Iowa", "KS": "Kansas",
    "KY": "Kentucky", "LA": "Louisiana", "ME": "Maine", "MD": "Maryland",
    "MA": "Massachusetts", "MI": "Michigan", "MN": "Minnesota", "MS": "Mississippi",
    "MO": "Missouri", "MT": "Montana", "NE": "Nebraska", "NV": "Nevada",
    "NH": "New Hampshire", "NJ": "New Jersey", "NM": "New Mexico", "NY": "New York",
    "NC": "North Carolina", "ND": "North Dakota", "OH": "Ohio", "OK": "Oklahoma",
    "OR": "Oregon", "PA": "Pennsylvania", "RI": "Rhode Island", "SC": "South Carolina",
    "SD": "South Dakota", "TN": "Tennessee", "TX": "Texas", "UT": "Utah",
    "VT": "Vermont", "VA": "Virginia", "WA": "Washington", "WV": "West Virginia",
    "WI": "Wisconsin", "WY": "Wyoming", "DC": "District of Columbia",
}

DISTRICT_PREFIX_PATTERNS = (
    re.compile(r"^state senate district\s+", re.IGNORECASE),
    re.compile(r"^state house district\s+", re.IGNORECASE),
    re.compile(r"^state legislative district\s+", re.IGNORECASE),
)

DISTRICT_SUFFIX_PATTERNS = (
    re.compile(r"\s*state house district(?:\s+\d+)?$", re.IGNORECASE),
    re.compile(r"\s*senatorial district(?:\s+\d+)?$", re.IGNORECASE),
    re.compile(r"\s*district(?:\s+\d+)?$", re.IGNORECASE),
)

def normalize_district(value) -> Optional[int]:
    try:
        district_number = int(value)
        return 0 if district_number == 98 else district_number
    except (TypeError, ValueError):
        return None


def format_district_label(state_abbr: str, district_number: int) -> str:
    state_name = STATE_NAMES.get(state_abbr, state_abbr)
    if district_number == 0:
        return f"{state_name} At Large"
    return f"{state_name} District {district_number}"


def normalize_state_legislative_district(value: Optional[str]) -> str:
    if not value:
        return ""
    normalized = " ".join(str(value).strip().split())
    for pattern in DISTRICT_PREFIX_PATTERNS:
        normalized = pattern.sub("", normalized)
    for pattern in DISTRICT_SUFFIX_PATTERNS:
        normalized = pattern.sub("", normalized)
    return normalized.strip().lower()


def strip_state_legislative_label(value: Optional[str]) -> str:
    if not value:
        return ""
    cleaned = " ".join(str(value).strip().split())
    for pattern in DISTRICT_PREFIX_PATTERNS:
        cleaned = pattern.sub("", cleaned)
    for pattern in DISTRICT_SUFFIX_PATTERNS:
        cleaned = pattern.sub("", cleaned)
    return cleaned.strip()


def slugify_division_key(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
    return slug or "unknown"