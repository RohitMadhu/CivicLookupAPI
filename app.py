import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import requests
from flask import Flask, jsonify, request

app = Flask(__name__)

GEOCODER_GEOGRAPHIES_URL = "https://geocoding.geo.census.gov/geocoder/geographies"
REQUEST_TIMEOUT_SECONDS = 30
DATA_DIR = Path(__file__).resolve().parent / "data"
FEDERAL_OFFICIALS_PATH = DATA_DIR / "federal_officials.json"
ZIP_DISTRICTS_PATH = DATA_DIR / "zip_districts.json"
STATE_OFFICIALS_PATH = DATA_DIR / "state_officials.json"
COUNTRY_OCD_ID = "ocd-division/country:us"

STATE_NAMES = {
    "AL": "Alabama",
    "AK": "Alaska",
    "AZ": "Arizona",
    "AR": "Arkansas",
    "CA": "California",
    "CO": "Colorado",
    "CT": "Connecticut",
    "DE": "Delaware",
    "FL": "Florida",
    "GA": "Georgia",
    "HI": "Hawaii",
    "ID": "Idaho",
    "IL": "Illinois",
    "IN": "Indiana",
    "IA": "Iowa",
    "KS": "Kansas",
    "KY": "Kentucky",
    "LA": "Louisiana",
    "ME": "Maine",
    "MD": "Maryland",
    "MA": "Massachusetts",
    "MI": "Michigan",
    "MN": "Minnesota",
    "MS": "Mississippi",
    "MO": "Missouri",
    "MT": "Montana",
    "NE": "Nebraska",
    "NV": "Nevada",
    "NH": "New Hampshire",
    "NJ": "New Jersey",
    "NM": "New Mexico",
    "NY": "New York",
    "NC": "North Carolina",
    "ND": "North Dakota",
    "OH": "Ohio",
    "OK": "Oklahoma",
    "OR": "Oregon",
    "PA": "Pennsylvania",
    "RI": "Rhode Island",
    "SC": "South Carolina",
    "SD": "South Dakota",
    "TN": "Tennessee",
    "TX": "Texas",
    "UT": "Utah",
    "VT": "Vermont",
    "VA": "Virginia",
    "WA": "Washington",
    "WV": "West Virginia",
    "WI": "Wisconsin",
    "WY": "Wyoming",
    "DC": "District of Columbia",
    "PR": "Puerto Rico",
    "AS": "American Samoa",
    "GU": "Guam",
    "MP": "Northern Mariana Islands",
    "VI": "U.S. Virgin Islands",
}

STATE_FIPS_TO_ABBR = {
    "01": "AL",
    "02": "AK",
    "04": "AZ",
    "05": "AR",
    "06": "CA",
    "08": "CO",
    "09": "CT",
    "10": "DE",
    "11": "DC",
    "12": "FL",
    "13": "GA",
    "15": "HI",
    "16": "ID",
    "17": "IL",
    "18": "IN",
    "19": "IA",
    "20": "KS",
    "21": "KY",
    "22": "LA",
    "23": "ME",
    "24": "MD",
    "25": "MA",
    "26": "MI",
    "27": "MN",
    "28": "MS",
    "29": "MO",
    "30": "MT",
    "31": "NE",
    "32": "NV",
    "33": "NH",
    "34": "NJ",
    "35": "NM",
    "36": "NY",
    "37": "NC",
    "38": "ND",
    "39": "OH",
    "40": "OK",
    "41": "OR",
    "42": "PA",
    "44": "RI",
    "45": "SC",
    "46": "SD",
    "47": "TN",
    "48": "TX",
    "49": "UT",
    "50": "VT",
    "51": "VA",
    "53": "WA",
    "54": "WV",
    "55": "WI",
    "56": "WY",
    "60": "AS",
    "66": "GU",
    "69": "MP",
    "72": "PR",
    "78": "VI",
}

TERRITORY_ABBRS = {"AS", "GU", "MP", "PR", "VI"}
STATEWIDE_EXECUTIVE_METADATA = {
    "governor": {"label": "Governor", "roles": ["headOfGovernment"], "order": 0},
    "lt_governor": {"label": "Lieutenant Governor", "roles": ["deputyHeadOfGovernment"], "order": 1},
    "secretary of state": {"label": "Secretary of State", "roles": ["governmentOfficer"], "order": 2},
    "chief election officer": {"label": "Chief Election Officer", "roles": ["governmentOfficer"], "order": 3},
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


def jurisdiction_ocd_id(state_abbr: str) -> str:
    if state_abbr == "DC":
        return f"{COUNTRY_OCD_ID}/district:dc"
    if state_abbr in TERRITORY_ABBRS:
        return f"{COUNTRY_OCD_ID}/territory:{state_abbr.lower()}"
    return f"{COUNTRY_OCD_ID}/state:{state_abbr.lower()}"


def district_ocd_id(district: dict) -> str:
    state_abbr = district["state"]
    district_number = district["district_number"]
    if state_abbr == "DC":
        return jurisdiction_ocd_id(state_abbr)
    if district_number == 0:
        return jurisdiction_ocd_id(state_abbr)
    return f"{jurisdiction_ocd_id(state_abbr)}/cd:{district_number}"


def district_aliases(district: dict) -> List[str]:
    state_abbr = district["state"]
    district_number = district["district_number"]
    if state_abbr == "DC":
        return []
    if district_number == 0:
        return [f"{jurisdiction_ocd_id(state_abbr)}/cd:1"]
    return []


def state_legislative_ocd_id(state_abbr: str, chamber: str, code: Optional[str], district_key: str) -> str:
    segment = "sldu" if chamber == "upper" else "sldl"
    identifier = (code or slugify_division_key(district_key)).lower()
    return f"{jurisdiction_ocd_id(state_abbr)}/{segment}:{identifier}"


def state_legislative_division_name(state_abbr: str, chamber: str, district_name: str) -> str:
    state_name = STATE_NAMES.get(state_abbr, state_abbr)
    if state_abbr == "DC":
        return f"{state_name} Council {district_name}"
    if chamber == "upper":
        return f"{state_name} State Senate District {district_name}"
    if chamber == "lower":
        return f"{state_name} State House District {district_name}"
    return f"{state_name} State Legislature District {district_name}"


def state_legislative_office_name(state_abbr: str, chamber: str) -> str:
    state_name = STATE_NAMES.get(state_abbr, state_abbr)
    if state_abbr == "DC":
        return "Council of the District of Columbia"
    if chamber == "upper":
        return f"{state_name} State Senate"
    if chamber == "lower":
        return f"{state_name} State House"
    return f"{state_name} State Legislature"


def statewide_executive_office_name(state_abbr: str, role_type: str) -> str:
    state_name = STATE_NAMES.get(state_abbr, state_abbr)
    label = STATEWIDE_EXECUTIVE_METADATA.get(role_type, {}).get("label", role_type.title())
    return f"{state_name} {label}"


@lru_cache(maxsize=1)
def load_federal_officials() -> dict:
    with FEDERAL_OFFICIALS_PATH.open() as federal_officials_file:
        return json.load(federal_officials_file)


@lru_cache(maxsize=1)
def load_zip_districts() -> dict:
    with ZIP_DISTRICTS_PATH.open() as zip_districts_file:
        return json.load(zip_districts_file)


@lru_cache(maxsize=1)
def load_state_officials() -> dict:
    with STATE_OFFICIALS_PATH.open() as state_officials_file:
        return json.load(state_officials_file)


def get_reps_by_district() -> Dict[str, List[dict]]:
    return load_federal_officials()["house_by_district"]


def get_senators_by_state() -> Dict[str, List[dict]]:
    return load_federal_officials()["senate_by_state"]


def get_districts_by_zip() -> Dict[str, List[dict]]:
    return load_zip_districts()["districts_by_zip"]


def get_state_upper_by_district() -> Dict[str, List[dict]]:
    return load_state_officials()["state_upper_by_district"]


def get_state_lower_by_district() -> Dict[str, List[dict]]:
    return load_state_officials()["state_lower_by_district"]


def get_state_legislature_by_district() -> Dict[str, List[dict]]:
    return load_state_officials()["state_legislature_by_district"]


def get_statewide_executives_by_state() -> Dict[str, List[dict]]:
    return load_state_officials()["statewide_executives_by_state"]


def lookup_districts(zip_code: str) -> List[dict]:
    return get_districts_by_zip().get(zip_code, [])


def build_lookup_result(
    districts: Optional[List[dict]] = None,
    state_upper_district: Optional[dict] = None,
    state_lower_district: Optional[dict] = None,
    matched_address: Optional[str] = None,
    coordinates: Optional[dict] = None,
) -> dict:
    return {
        "districts": districts or [],
        "state_upper_district": state_upper_district,
        "state_lower_district": state_lower_district,
        "matched_address": matched_address,
        "coordinates": coordinates,
    }


def lookup_states_for_districts(districts: List[dict]) -> List[str]:
    return sorted({district["state"] for district in districts})


def lookup_states_for_result(lookup_result: dict) -> List[str]:
    states = set(lookup_states_for_districts(lookup_result.get("districts", [])))
    for district_key in ("state_upper_district", "state_lower_district"):
        district = lookup_result.get(district_key)
        if district:
            states.add(district["state"])
    return sorted(states)


def has_lookup_matches(lookup_result: dict) -> bool:
    return bool(
        lookup_result.get("districts")
        or lookup_result.get("state_upper_district")
        or lookup_result.get("state_lower_district")
    )


def get_include_offices() -> bool:
    include_offices = request.args.get("includeOffices")
    if include_offices is None:
        return True
    return include_offices.strip().lower() not in {"0", "false", "no"}


def build_channels(social: dict) -> List[dict]:
    channel_order = [
        ("facebook", "Facebook"),
        ("instagram", "Instagram"),
        ("twitter", "Twitter"),
        ("youtube", "YouTube"),
    ]
    channels = []
    for social_key, channel_type in channel_order:
        channel_id = social.get(social_key) or social.get(f"{social_key}_id")
        if channel_id:
            channels.append({"type": channel_type, "id": str(channel_id)})
    return channels


def build_contact_address(official: dict) -> List[dict]:
    office = official.get("office")
    full_address = official.get("address")
    if not full_address:
        return []

    if office and full_address.lower().startswith(office.lower()):
        remainder = full_address[len(office) :].strip()
        match = re.match(r"^(?P<city>.+?)\s+(?P<state>[A-Z]{2})\s+(?P<zip>\d{5}(?:-\d{4})?)$", remainder)
        if match:
            return [
                {
                    "line1": office,
                    "city": match.group("city"),
                    "state": match.group("state"),
                    "zip": match.group("zip"),
                }
            ]

    return [{"line1": full_address}]


def build_google_official(official: dict) -> dict:
    google_official = {"name": official["name"]}

    if official.get("party"):
        google_official["party"] = official["party"]
    if official.get("email"):
        google_official["emails"] = [official["email"]]
    if official.get("phone"):
        google_official["phones"] = [official["phone"]]
    if official.get("url"):
        google_official["urls"] = [official["url"]]
    if official.get("image"):
        google_official["photoUrl"] = official["image"]

    channels = build_channels(official.get("social", {}))
    if channels:
        google_official["channels"] = channels

    address = build_contact_address(official)
    if address:
        google_official["address"] = address

    return google_official


def official_registry_key(official: dict) -> str:
    return (
        official.get("bioguide_id")
        or official.get("openstates_id")
        or "|".join(str(official.get(field) or "") for field in ("state", "name", "district", "role_type", "chamber"))
    )


def build_normalized_input_from_matched_address(matched_address: Optional[str]) -> dict:
    normalized_input = {"line1": "", "city": "", "state": "", "zip": ""}
    if not matched_address:
        return normalized_input

    parts = [part.strip() for part in matched_address.split(",")]
    if len(parts) >= 4:
        normalized_input["line1"] = parts[0]
        normalized_input["city"] = parts[-3]
        normalized_input["state"] = parts[-2]
        normalized_input["zip"] = parts[-1]
        return normalized_input

    normalized_input["line1"] = matched_address
    return normalized_input


def build_normalized_input_from_request(
    zip_code: Optional[str] = None,
    street: Optional[str] = None,
    city: Optional[str] = None,
    state: Optional[str] = None,
    address: Optional[str] = None,
    matched_address: Optional[str] = None,
    districts: Optional[List[dict]] = None,
    states: Optional[List[str]] = None,
) -> dict:
    if matched_address:
        return build_normalized_input_from_matched_address(matched_address)

    normalized_input = {"line1": street or address or "", "city": city or "", "state": state or "", "zip": zip_code or ""}
    candidate_states = states or []
    if not candidate_states and districts:
        candidate_states = lookup_states_for_districts(districts)
    if not normalized_input["state"] and len(candidate_states) == 1:
        normalized_input["state"] = candidate_states[0]
    return normalized_input


def build_google_divisions(lookup_result: dict, include_offices: bool) -> dict:
    divisions = {COUNTRY_OCD_ID: {"name": "United States"}}
    division_order: List[str] = [COUNTRY_OCD_ID]

    for state_abbr in lookup_states_for_result(lookup_result):
        division_id = jurisdiction_ocd_id(state_abbr)
        if division_id not in divisions:
            divisions[division_id] = {"name": STATE_NAMES.get(state_abbr, state_abbr)}
            division_order.append(division_id)

    for district in lookup_result.get("districts", []):
        current_division_id = district_ocd_id(district)
        if current_division_id not in divisions:
            divisions[current_division_id] = {"name": district["district"]}
            division_order.append(current_division_id)

        aliases = district_aliases(district)
        if aliases:
            division_aliases = divisions[current_division_id].setdefault("alsoKnownAs", [])
            for alias in aliases:
                if alias not in division_aliases:
                    division_aliases.append(alias)

    for district_key in ("state_upper_district", "state_lower_district"):
        district = lookup_result.get(district_key)
        if not district:
            continue

        division_id = district["division_id"]
        if division_id not in divisions:
            divisions[division_id] = {"name": district["division_name"]}
            division_order.append(division_id)

    ordered_divisions = {division_id: divisions[division_id] for division_id in division_order}
    if not include_offices:
        return ordered_divisions
    return ordered_divisions


def add_office_index(division_map: dict, division_id: str, office_index: int):
    division = division_map.setdefault(division_id, {"name": division_id})
    office_indices = division.setdefault("officeIndices", [])
    office_indices.append(office_index)


def add_google_officials(official_records: List[dict], officials: List[dict], official_indices: Dict[str, int]) -> List[int]:
    indices = []
    for official in official_records:
        official_key = official_registry_key(official)
        if official_key not in official_indices:
            official_indices[official_key] = len(officials)
            officials.append(build_google_official(official))
        indices.append(official_indices[official_key])
    return indices


def lookup_state_legislators_for_district(district_info: Optional[dict], preferred_chambers: Tuple[str, ...]) -> Tuple[List[dict], Optional[str]]:
    if not district_info:
        return [], None

    chamber_maps = {
        "upper": get_state_upper_by_district(),
        "lower": get_state_lower_by_district(),
        "legislature": get_state_legislature_by_district(),
    }

    for district_key in district_info.get("district_key_candidates", []):
        map_key = f"{district_info['state']}:{district_key}"
        for chamber in preferred_chambers:
            officials = chamber_maps[chamber].get(map_key, [])
            if officials:
                return officials, chamber
    return [], None


def build_google_response(normalized_input: dict, lookup_result: dict) -> dict:
    include_offices = get_include_offices()
    divisions = build_google_divisions(lookup_result, include_offices)
    response = {
        "kind": "civicinfo#representativeInfoResponse",
        "normalizedInput": normalized_input,
        "divisions": divisions,
    }

    if not include_offices:
        return response

    offices = []
    officials = []
    official_indices: Dict[str, int] = {}
    states = lookup_states_for_result(lookup_result)

    for state_abbr in states:
        state_senators = get_senators_by_state().get(state_abbr, [])
        if not state_senators:
            continue

        senator_indices = add_google_officials(state_senators, officials, official_indices)
        office_index = len(offices)
        senate_division_id = jurisdiction_ocd_id(state_abbr)
        offices.append(
            {
                "name": "United States Senate",
                "divisionId": senate_division_id,
                "levels": ["country"],
                "roles": ["legislatorUpperBody"],
                "officialIndices": senator_indices,
            }
        )
        add_office_index(divisions, senate_division_id, office_index)

    for district in lookup_result.get("districts", []):
        district_key = f"{district['state']}:{district['district_number']}"
        district_reps = get_reps_by_district().get(district_key, [])
        if not district_reps:
            continue

        rep_indices = add_google_officials(district_reps, officials, official_indices)
        office_index = len(offices)
        office_division_id = district_ocd_id(district)
        offices.append(
            {
                "name": "United States House of Representatives",
                "divisionId": office_division_id,
                "levels": ["country"],
                "roles": ["legislatorLowerBody"],
                "officialIndices": rep_indices,
            }
        )
        add_office_index(divisions, office_division_id, office_index)

    for state_abbr in states:
        executive_officials = get_statewide_executives_by_state().get(state_abbr, [])
        if not executive_officials:
            continue

        grouped_by_role: Dict[str, List[dict]] = {}
        for executive in executive_officials:
            grouped_by_role.setdefault(executive["role_type"], []).append(executive)

        state_division_id = jurisdiction_ocd_id(state_abbr)
        for role_type, metadata in sorted(
            STATEWIDE_EXECUTIVE_METADATA.items(),
            key=lambda item: item[1]["order"],
        ):
            role_officials = grouped_by_role.get(role_type, [])
            if not role_officials:
                continue

            role_indices = add_google_officials(role_officials, officials, official_indices)
            office_index = len(offices)
            office = {
                "name": statewide_executive_office_name(state_abbr, role_type),
                "divisionId": state_division_id,
                "levels": ["administrativeArea1"],
                "officialIndices": role_indices,
            }
            if metadata["roles"]:
                office["roles"] = metadata["roles"]
            offices.append(office)
            add_office_index(divisions, state_division_id, office_index)

    state_upper_district = lookup_result.get("state_upper_district")
    upper_officials, upper_chamber = lookup_state_legislators_for_district(
        state_upper_district,
        ("upper", "legislature"),
    )
    if state_upper_district and upper_officials:
        upper_indices = add_google_officials(upper_officials, officials, official_indices)
        office_index = len(offices)
        offices.append(
            {
                "name": state_legislative_office_name(state_upper_district["state"], upper_chamber or "upper"),
                "divisionId": state_upper_district["division_id"],
                "levels": ["administrativeArea1"],
                "roles": ["legislatorUpperBody"],
                "officialIndices": upper_indices,
            }
        )
        add_office_index(divisions, state_upper_district["division_id"], office_index)

    state_lower_district = lookup_result.get("state_lower_district")
    lower_officials, lower_chamber = lookup_state_legislators_for_district(
        state_lower_district,
        ("lower", "legislature"),
    )
    if state_lower_district and lower_officials:
        lower_indices = add_google_officials(lower_officials, officials, official_indices)
        office_index = len(offices)
        offices.append(
            {
                "name": state_legislative_office_name(state_lower_district["state"], lower_chamber or "lower"),
                "divisionId": state_lower_district["division_id"],
                "levels": ["administrativeArea1"],
                "roles": ["legislatorLowerBody"],
                "officialIndices": lower_indices,
            }
        )
        add_office_index(divisions, state_lower_district["division_id"], office_index)

    response["offices"] = offices
    response["officials"] = officials
    return response


def extract_district_number(match: dict) -> Optional[int]:
    district_keys = sorted(
        [key for key in match.keys() if key.startswith("CD") and key[2:].isdigit()],
        reverse=True,
    )
    for district_key in district_keys:
        district_number = normalize_district(match.get(district_key))
        if district_number is not None:
            return district_number
    return normalize_district(match.get("BASENAME"))


def extract_congressional_districts(geographies: dict) -> List[dict]):
    districts = []
    seen = set()

    for geography_name, matches in geographies.items():
        if "Congressional District" not in geography_name:
            continue

        for match in matches:
            state_abbr = STATE_FIPS_TO_ABBR.get((match.get("STATE") or "").zfill(2))
            district_number = extract_district_number(match)
            if not state_abbr or district_number is None:
                continue

            district_key = (state_abbr, district_number)
            if district_key in seen:
                continue

            seen.add(district_key)
            districts.append(
                {
                    "state": state_abbr,
                    "district_number": district_number,
                    "district": format_district_label(state_abbr, district_number),
                }
            )

    districts.sort(key=lambda district: (district["state"], district["district_number"]))
    return districts


def legislative_district_key_candidates(match: dict) -> List[str]):
    candidates = []
    for value in (match.get("NAME"), match.get("BASENAME")):
        district_key = normalize_state_legislative_district(value)
        if district_key and district_key not in candidates:
            candidates.append(district_key)
    return candidates


def extract_state_legislative_district(geographies: dict, chamber: str) -> Optional[dict]):
    geography_label = "State Legislative Districts - Upper" if chamber == "upper" else "State Legislative Districts - Lower"
    code_key = "SLDU" if chamber == "upper" else "SLDL"

    for geography_name, matches in geographies.items():
        if geography_label not in geography_name:
            continue

        for match in matches:
            state_abbr = STATE_FIPS_TO_ABBR.get((match.get("STATE") or "").zfill(2))
            district_key_candidates = legislative_district_key_candidates(match)
            district_name = strip_state_legislative_label(match.get("NAME")) or strip_state_legislative_label(
                match.get("BASENAME")
            )
            if not state_abbr or not district_key_candidates:
                continue

            primary_key = district_key_candidates[0]
            return {
                "state": state_abbr,
                "district_name": district_name or primary_key.title(),
                "district_key_candidates": district_key_candidates,
                "division_id": state_legislative_ocd_id(
                    state_abbr,
                    chamber,
                    match.get(code_key),
                    primary_key,
                ),
                "division_name": state_legislative_division_name(
                    state_abbr,
                    chamber,
                district_name or primary_key.title(),
            ),
            }

    return None


def lookup_address_districts(
    street: Optional[str] = None,
    city: Optional[str] = None,
    state: Optional[str] = None,
    zip_code: Optional[str] = None,
    address: Optional[str] = None,
) -> dict):
    params = {
        "benchmark": "Public_AR_Current",
        "vintage": "Current_Current",
        "format": "json",
    }

    if address:
        url = f"{GEOCODER_GEOGRAPHIES_URL}/onelineaddress"
        params["address"] = address
    else:
        url = f"{GEOCODER_GEOGRAPHIES_URL}/address"
        params["street"] = street
        if city:
            params["city"] = city
        if state:
            params["state"] = state
        if zip_code:
            params["zip"] = zip_code

    response = requests.get(url, params=params, timeout=REQUEST_TIMEOUT_SECONDS)
    response.raise_for_status()
    result = response.json().get("result", {})
    matches = result.get("addressMatches", [])
    if not matches:
        return build_lookup_result()

    best_match = matches[0]
    geographies = best_match.get("geographies", {})
    return build_lookup_result(
        districts=extract_congressional_districts(geographies),
        state_upper_district=extract_state_legislative_district(geographies, "upper"),
        state_lower_district=extract_state_legislative_district(geographies, "lower"),
        matched_address=best_match.get("matchedAddress"),
        coordinates=best_match.get("coordinates"),
    )


def parse_address_lookup_args(default_zip: Optional[str] = None) -> Tuple[Optional[dict], Optional[Tuple[dict, int]]]:
    address = request.args.get("address")
    street = request.args.get("street")
    city = request.args.get("city")
    state = request.args.get("state")
    zip_code = request.args.get("zip", default_zip)

    if address:
        return (
            {
                "address": address,
                "street": None,
                "city": None,
                "state": None,
                "zip_code": zip_code,
            },
            None,
        )

    if not street:
        return (
            None,
            (
                {
                    "error": (
                        "Provide either address=<full address> or street=<street address> plus zip=<zip> "
                        "or city=<city>&state=<state>."
                    )
                },
                400,
            ),
        )

    if not (zip_code or (city and state)):
        return (
            None,
            (
                {
                    "error": "Address lookups require street plus zip, or street plus city and state."
                },
                400,
            ),
        )

    return (
        {
            "address": None,
            "street": street,
            "city": city,
            "state": state,
            "zip_code": zip_code,
        },
        None,
    )


def build_divisions_response(normalized_input: dict, lookup_result: dict) -> dict):
    return {
        "kind": "civicinfo#divisionsByAddressResponse",
        "normalizedInput": normalized_input,
        "divisions": build_google_divisions(lookup_result, include_offices=False),
    }


@app.route("/api/zip/<zip_code>/districts")
def get_zip_districts(zip_code):
    try:
        lookup_result = build_lookup_result(districts=lookup_districts(zip_code))
        normalized_input = build_normalized_input_from_request(
            zip_code=zip_code,
            districts=lookup_result["districts"],
            states=lookup_states_for_result(lookup_result),
        )
        return jsonify(build_divisions_response(normalized_input, lookup_result))
    except (OSError, ValueError) as exc):
        return jsonify({"error": "Unable to load ZIP-to-district data", "details": str(exc))), 500


@app.route("/api/address/districts")
def get_address_districts():
    lookup_args, error = parse_address_lookup_args()
    if error):
        payload, status_code = error
        return jsonify(payload), status_code

    try:
        result = lookup_address_districts(**lookup_args)
        normalized_input = build_normalized_input_from_request(
            street=lookup_args.get("street"),
            city=lookup_args.get("city"),
            state=lookup_args.get("state"),
            zip_code=lookup_args.get("zip_code"),
            address=lookup_args.get("address"),
            matched_address=result["matched_address"],
            districts=result["districts"],
            states=lookup_states_for_result(result),
        )
        response_payload = build_divisions_response(normalized_input, result)
        if not has_lookup_matches(result):
            return jsonify(response_payload), 404
        return jsonify(response_payload)
    except requests.RequestException as exc):
        return jsonify({"error": "Unable to geocode address", "details": str(exc))), 502


@app.route("/api/rep/address")
def get_rep_by_address():
    lookup_args, error = parse_address_lookup_args()
    if error):
        payload, status_code = error
        return jsonify(payload), status_code

    try):
        lookup_result = lookup_address_districts(**lookup_args)
        normalized_input = build_normalized_input_from_request(
            street=lookup_args.get("street"),
            city=lookup_args.get("city"),
            state=lookup_args.get("state"),
            zip_code=lookup_args.get("zip_code"),
            address=lookup_args.get("address"),
            matched_address=lookup_result["matched_address"],
            districts=lookup_result["districts"],
            states=lookup_states_for_result(lookup_result),
        )
        response_payload = build_google_response(normalized_input, lookup_result)
        if not has_lookup_matches(lookup_result):
            return jsonify(response_payload), 404
        return jsonify(response_payload)
    except requests.RequestException as exc):
        return jsonify({"error": "Unable to geocode address", "details": str(exc))), 502
    except (OSError, ValueError) as exc):
        return jsonify({"error": "Unable to load bundled legislator data", "details": str(exc))), 500


@app.route("/api/rep/<zip_code>")
def get_rep(zip_code):
    if request.args.get("address") or request.args.get("street"):
        lookup_args, error = parse_address_lookup_args(default_zip=zip_code)
        if error):
            payload, status_code = error
            return jsonify(payload), status_code

        try):
            lookup_result = lookup_address_districts(**lookup_args)
            normalized_input = build_normalized_input_from_request(
                street=lookup_args.get("street"),
                city=lookup_args.get("city"),
                state=lookup_args.get("state"),
                zip_code=zip_code,
                address=lookup_args.get("address"),
                matched_address=lookup_result["matched_address"],
                districts=lookup_result["districts"],
                states=lookup_states_for_result(lookup_result),
            )
            response_payload = build_google_response(normalized_input, lookup_result)
            if not has_lookup_matches(lookup_result):
                return jsonify(response_payload), 404
            return jsonify(response_payload)
        except requests.RequestException as exc):
            return jsonify({"error": "Unable to geocode address", "details": str(exc))), 502
        except (OSError, ValueError) as exc):
            return jsonify({"error": "Unable to load bundled legislator data", "details": str(exc))), 500

    try):
        lookup_result = build_lookup_result(districts=lookup_districts(zip_code))
        normalized_input = build_normalized_input_from_request(
            zip_code=zip_code,
            districts=lookup_result["districts"],
            states=lookup_states_for_result(lookup_result),
        )
        return jsonify(build_google_response(normalized_input, lookup_result))
    except (OSError, ValueError) as exc):
        return jsonify({"error": "Unable to load bundled legislator data", "details": str(exc))), 500


if __name__ == "__main__":
    app.run(debug=True)
