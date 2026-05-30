import re
from datetime import datetime, timezone
from typing import Dict, List, Optional, Set, Tuple

import requests
from flask import Blueprint, abort, jsonify, request

from civiclookup.config import get_config
from civiclookup.data.loaders import (
    DATA_DIR,
    load_financial_disclosures,
    load_federal_officials,
    load_state_officials,
    load_zip_districts,
)
from civiclookup.services.disclosure_service import (
    disclosure_source_status,
    get_financial_disclosures_for_official,
)
from civiclookup.utils.normalization import (
    format_district_label,
    normalize_district,
    normalize_state_legislative_district,
    slugify_division_key,
    strip_state_legislative_label,
)

api_bp = Blueprint("api", __name__)
config = get_config()

COUNTRY_OCD_ID = "ocd-division/country:us"
SUPPORTED_NATIVE_INCLUDES = {"financial_disclosures", "social", "offices", "sources"}

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


def jurisdiction_ocd_id(state_abbr: str) -> str:
    if state_abbr == "DC":
        return f"{COUNTRY_OCD_ID}/district:dc"
    if state_abbr in TERRITORY_ABBRS:
        return f"{COUNTRY_OCD_ID}/territory:{state_abbr.lower()}"
    return f"{COUNTRY_OCD_ID}/state:{state_abbr.lower()}"


def district_ocd_id(district: dict) -> str:
    state_abbr = district["state"]
    district_number = district["district_number"]
    if state_abbr == "DC" or district_number == 0:
        return jurisdiction_ocd_id(state_abbr)
    return f"{jurisdiction_ocd_id(state_abbr)}/cd:{district_number}"


def district_aliases(district: dict) -> List[str]:
    state_abbr = district["state"]
    district_number = district["district_number"]
    if state_abbr == "DC" or district_number != 0:
        return []
    return [f"{jurisdiction_ocd_id(state_abbr)}/cd:1"]


def state_legislative_ocd_id(
    state_abbr: str,
    chamber: str,
    code: Optional[str],
    district_key: str,
) -> str:
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


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def source_metadata(include_geocoder: bool = False) -> List[dict]:
    federal_data = load_federal_officials()
    state_data = load_state_officials()
    zip_data = load_zip_districts()
    disclosure_data = load_financial_disclosures()
    sources = [
        {
            "name": "unitedstates/congress-legislators",
            "type": "federal_officials",
            "url": federal_data.get("sources", {}).get("legislators"),
            "generatedAt": federal_data.get("generated_at"),
        },
        {
            "name": "OpenStates people",
            "type": "state_officials",
            "url": state_data.get("sources", {}).get("openstates_people"),
            "generatedAt": state_data.get("generated_at"),
        },
        {
            "name": "OpenSourceActivismTech/us-zipcodes-congress",
            "type": "zip_districts",
            "url": zip_data.get("sources", {}).get("zip_districts"),
            "generatedAt": zip_data.get("generated_at"),
        },
    ]
    if disclosure_data.get("generated_at"):
        sources.append(
            {
                "name": "Kadoa Congress Trading Monitor",
                "type": "financial_disclosures",
                "url": disclosure_data.get("sources", {}).get("kadoa_trades"),
                "generatedAt": disclosure_data.get("generated_at"),
                "upstreamGeneratedAt": disclosure_data.get("upstream_generated_at"),
            }
        )
    if include_geocoder:
        sources.append(
            {
                "name": "US Census Geocoder",
                "type": "address_geocoder",
                "url": config.GEOCODER_URL,
                "generatedAt": None,
            }
        )
    return sources


def lookup_districts(zip_code: str) -> List[dict]:
    return get_districts_by_zip().get(zip_code, [])


def build_lookup_result(
    districts: Optional[List[dict]] = None,
    state_upper_district: Optional[dict] = None,
    state_lower_district: Optional[dict] = None,
    matched_address: Optional[str] = None,
    coordinates: Optional[dict] = None,
    states: Optional[List[str]] = None,
) -> dict:
    return {
        "districts": districts or [],
        "state_upper_district": state_upper_district,
        "state_lower_district": state_lower_district,
        "matched_address": matched_address,
        "coordinates": coordinates,
        "states": states or [],
    }


def lookup_states_for_districts(districts: List[dict]) -> List[str]:
    return sorted({district["state"] for district in districts})


def lookup_states_for_result(lookup_result: dict) -> List[str]:
    states = set(lookup_result.get("states", []))
    states.update(lookup_states_for_districts(lookup_result.get("districts", [])))
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
        or lookup_result.get("states")
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
        match = re.match(
            r"^(?P<city>.+?)\s+(?P<state>[A-Z]{2})\s+(?P<zip>\d{5}(?:-\d{4})?)$",
            remainder,
        )
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
        or "|".join(
            str(official.get(field) or "")
            for field in ("state", "name", "district", "role_type", "chamber")
        )
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

    normalized_input = {
        "line1": street or address or "",
        "city": city or "",
        "state": state or "",
        "zip": zip_code or "",
    }
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


def add_google_officials(
    official_records: List[dict],
    officials: List[dict],
    official_indices: Dict[str, int],
) -> List[int]:
    indices = []
    for official in official_records:
        official_key = official_registry_key(official)
        if official_key not in official_indices:
            official_indices[official_key] = len(officials)
            officials.append(build_google_official(official))
        indices.append(official_indices[official_key])
    return indices


def lookup_state_legislators_for_district(
    district_info: Optional[dict],
    preferred_chambers: Tuple[str, ...],
) -> Tuple[List[dict], Optional[str]]:
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


def collect_office_records(lookup_result: dict) -> List[dict]:
    offices = []
    states = lookup_states_for_result(lookup_result)

    for state_abbr in states:
        state_senators = get_senators_by_state().get(state_abbr, [])
        if state_senators:
            offices.append(
                {
                    "name": "United States Senate",
                    "divisionId": jurisdiction_ocd_id(state_abbr),
                    "levels": ["country"],
                    "roles": ["legislatorUpperBody"],
                    "officials": state_senators,
                }
            )

    for district in lookup_result.get("districts", []):
        district_key = f"{district['state']}:{district['district_number']}"
        district_reps = get_reps_by_district().get(district_key, [])
        if district_reps:
            offices.append(
                {
                    "name": "United States House of Representatives",
                    "divisionId": district_ocd_id(district),
                    "levels": ["country"],
                    "roles": ["legislatorLowerBody"],
                    "officials": district_reps,
                }
            )

    for state_abbr in states:
        executive_officials = get_statewide_executives_by_state().get(state_abbr, [])
        grouped_by_role: Dict[str, List[dict]] = {}
        for executive in executive_officials:
            grouped_by_role.setdefault(executive["role_type"], []).append(executive)

        for role_type, metadata in sorted(
            STATEWIDE_EXECUTIVE_METADATA.items(),
            key=lambda item: item[1]["order"],
        ):
            role_officials = grouped_by_role.get(role_type, [])
            if not role_officials:
                continue
            offices.append(
                {
                    "name": statewide_executive_office_name(state_abbr, role_type),
                    "divisionId": jurisdiction_ocd_id(state_abbr),
                    "levels": ["administrativeArea1"],
                    "roles": metadata["roles"],
                    "officials": role_officials,
                }
            )

    state_upper_district = lookup_result.get("state_upper_district")
    upper_officials, upper_chamber = lookup_state_legislators_for_district(
        state_upper_district,
        ("upper", "legislature"),
    )
    if state_upper_district and upper_officials:
        offices.append(
            {
                "name": state_legislative_office_name(
                    state_upper_district["state"],
                    upper_chamber or "upper",
                ),
                "divisionId": state_upper_district["division_id"],
                "levels": ["administrativeArea1"],
                "roles": ["legislatorUpperBody"],
                "officials": upper_officials,
            }
        )

    state_lower_district = lookup_result.get("state_lower_district")
    lower_officials, lower_chamber = lookup_state_legislators_for_district(
        state_lower_district,
        ("lower", "legislature"),
    )
    if state_lower_district and lower_officials:
        offices.append(
            {
                "name": state_legislative_office_name(
                    state_lower_district["state"],
                    lower_chamber or "lower",
                ),
                "divisionId": state_lower_district["division_id"],
                "levels": ["administrativeArea1"],
                "roles": ["legislatorLowerBody"],
                "officials": lower_officials,
            }
        )

    return offices


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
    for office_record in collect_office_records(lookup_result):
        official_indices_for_office = add_google_officials(
            office_record["officials"],
            officials,
            official_indices,
        )
        office_index = len(offices)
        offices.append(
            {
                "name": office_record["name"],
                "divisionId": office_record["divisionId"],
                "levels": office_record["levels"],
                "roles": office_record.get("roles", []),
                "officialIndices": official_indices_for_office,
            }
        )
        add_office_index(divisions, office_record["divisionId"], office_index)

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


def extract_congressional_districts(geographies: dict) -> List[dict]:
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


def legislative_district_key_candidates(match: dict) -> List[str]:
    candidates = []
    for value in (match.get("NAME"), match.get("BASENAME")):
        district_key = normalize_state_legislative_district(value)
        if district_key and district_key not in candidates:
            candidates.append(district_key)
    return candidates


def extract_state_legislative_district(geographies: dict, chamber: str) -> Optional[dict]:
    geography_label = (
        "State Legislative Districts - Upper"
        if chamber == "upper"
        else "State Legislative Districts - Lower"
    )
    code_key = "SLDU" if chamber == "upper" else "SLDL"

    for geography_name, matches in geographies.items():
        if geography_label not in geography_name:
            continue

        for match in matches:
            state_abbr = STATE_FIPS_TO_ABBR.get((match.get("STATE") or "").zfill(2))
            district_key_candidates = legislative_district_key_candidates(match)
            district_name = strip_state_legislative_label(
                match.get("NAME")
            ) or strip_state_legislative_label(match.get("BASENAME"))
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
) -> dict:
    params = {
        "benchmark": "Public_AR_Current",
        "vintage": "Current_Current",
        "format": "json",
    }

    if address:
        url = f"{config.GEOCODER_URL}/onelineaddress"
        params["address"] = address
    else:
        url = f"{config.GEOCODER_URL}/address"
        params["street"] = street
        if city:
            params["city"] = city
        if state:
            params["state"] = state
        if zip_code:
            params["zip"] = zip_code

    response = requests.get(url, params=params, timeout=config.REQUEST_TIMEOUT)
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


def parse_address_lookup_args(
    default_zip: Optional[str] = None,
) -> Tuple[Optional[dict], Optional[Tuple[dict, int]]]:
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


def build_divisions_response(normalized_input: dict, lookup_result: dict) -> dict:
    return {
        "kind": "civicinfo#divisionsByAddressResponse",
        "normalizedInput": normalized_input,
        "divisions": build_google_divisions(lookup_result, include_offices=False),
    }


def parse_native_includes() -> Tuple[Set[str], List[str]]:
    raw_include = request.args.get("include", "")
    includes = {item.strip() for item in raw_include.split(",") if item.strip()}
    unknown = sorted(includes - SUPPORTED_NATIVE_INCLUDES)
    return includes & SUPPORTED_NATIVE_INCLUDES, [
        f"Unsupported include ignored: {include}" for include in unknown
    ]


def slugify_identifier(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "unknown"


def native_official_id(official: dict) -> str:
    if official.get("bioguide_id"):
        return f"bioguide:{official['bioguide_id']}"
    if official.get("openstates_id"):
        return f"openstates:{official['openstates_id']}"
    fallback = "|".join(
        str(official.get(field) or "")
        for field in ("state", "name", "district", "role_type", "chamber")
    )
    return f"slug:{slugify_identifier(fallback)}"


def parse_state_from_division_id(division_id: str) -> Optional[str]:
    match = re.search(r"/(?:state|territory):([a-z]{2})", division_id)
    if match:
        return match.group(1).upper()
    if "/district:dc" in division_id:
        return "DC"
    return None


def parse_cd_from_division_id(division_id: str) -> Optional[int]:
    match = re.search(r"/cd:(\d+)$", division_id)
    if match:
        return int(match.group(1))
    return None


def parse_state_legislative_from_division_id(
    division_id: str,
) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    match = re.search(r"/(sldu|sldl):([^/]+)$", division_id)
    if not match:
        return None, None, None
    chamber = "upper" if match.group(1) == "sldu" else "lower"
    return parse_state_from_division_id(division_id), chamber, match.group(2)


def native_division_type(division_id: str) -> str:
    if division_id == COUNTRY_OCD_ID:
        return "country"
    if "/cd:" in division_id:
        return "congressional_district"
    if "/sldu:" in division_id:
        return "state_senate_district"
    if "/sldl:" in division_id:
        return "state_house_district"
    if "/state:" in division_id or "/territory:" in division_id or "/district:" in division_id:
        return "state"
    return "division"


def native_division_level(division_id: str) -> str:
    if division_id == COUNTRY_OCD_ID or "/cd:" in division_id:
        return "country"
    return "administrativeArea1"


def native_office_id(office: dict) -> str:
    state_abbr = parse_state_from_division_id(office["divisionId"]) or "us"
    state_slug = state_abbr.lower()
    name = office["name"]
    role = (office.get("roles") or ["office"])[0]

    if name == "United States Senate":
        return f"us-senate-{state_slug}"
    if name == "United States House of Representatives":
        district_number = parse_cd_from_division_id(office["divisionId"])
        district_slug = str(district_number) if district_number is not None else "at-large"
        return f"us-house-{state_slug}-{district_slug}"
    if role == "legislatorUpperBody":
        identifier = office["divisionId"].rsplit(":", 1)[-1]
        return f"{state_slug}-state-senate-{slugify_identifier(identifier)}"
    if role == "legislatorLowerBody":
        identifier = office["divisionId"].rsplit(":", 1)[-1]
        return f"{state_slug}-state-house-{slugify_identifier(identifier)}"

    for role_type, metadata in STATEWIDE_EXECUTIVE_METADATA.items():
        if name == statewide_executive_office_name(state_abbr, role_type):
            return f"{state_slug}-{slugify_identifier(metadata['label'])}"
    return f"{state_slug}-{slugify_identifier(name)}"


def disclosure_stub_for_official(official: dict, includes: Set[str]) -> Optional[dict]:
    if "financial_disclosures" not in includes:
        return None
    return get_financial_disclosures_for_official(official)


def build_native_official(official: dict, includes: Set[str]) -> dict:
    native_official = {
        "id": native_official_id(official),
        "name": official.get("name"),
        "party": official.get("party"),
        "state": official.get("state"),
        "chamber": official.get("chamber") or official.get("role_type"),
        "district": official.get("district"),
        "phones": [official["phone"]] if official.get("phone") else [],
        "emails": [official["email"]] if official.get("email") else [],
        "urls": [official["url"]] if official.get("url") else [],
        "photoUrl": official.get("image"),
        "social": official.get("social") or {},
    }
    disclosure = disclosure_stub_for_official(official, includes)
    if disclosure:
        native_official["financialDisclosures"] = disclosure
    return native_official


def build_native_jurisdictions(lookup_result: dict, confidence: str) -> List[dict]:
    divisions = build_google_divisions(lookup_result, include_offices=False)
    return [
        {
            "id": division_id,
            "name": division.get("name", division_id),
            "type": native_division_type(division_id),
            "level": native_division_level(division_id),
            "confidence": confidence,
        }
        for division_id, division in divisions.items()
    ]


def build_native_offices(lookup_result: dict, includes: Set[str]) -> List[dict]:
    native_offices = []
    for office in collect_office_records(lookup_result):
        roles = office.get("roles") or []
        native_offices.append(
            {
                "id": native_office_id(office),
                "name": office["name"],
                "divisionId": office["divisionId"],
                "level": office["levels"][0] if office.get("levels") else None,
                "role": roles[0] if roles else None,
                "officials": [
                    build_native_official(official, includes)
                    for official in office["officials"]
                ],
            }
        )
    return native_offices


def native_lookup_warnings(
    lookup_result: dict,
    lookup_mode: str,
    include_warnings: Optional[List[str]] = None,
) -> List[str]:
    warnings = list(include_warnings or [])
    if lookup_mode == "zip":
        warnings.append(
            "ZIP-only lookup may be ambiguous; use an address lookup for exact district matching."
        )
    if not has_lookup_matches(lookup_result):
        warnings.append("No matching districts or officials were found for the provided input.")
        if lookup_mode == "address" and not lookup_result.get("matched_address"):
            warnings.append("US Census Geocoder returned no address match.")
    if len(lookup_result.get("districts", [])) > 1:
        warnings.append("ZIP maps to multiple congressional districts; address lookup is recommended.")
    return warnings


def build_native_metadata(
    lookup_result: dict,
    lookup_mode: str,
    includes: Set[str],
    warnings: List[str],
) -> dict:
    if lookup_mode == "division":
        confidence = "source_record"
    elif lookup_mode == "address" and lookup_result.get("matched_address"):
        confidence = "exact_address_match"
    else:
        confidence = "zip_approximate"
    if not has_lookup_matches(lookup_result):
        confidence = "no_match"

    metadata = {
        "generatedAt": utc_now_iso(),
        "sources": source_metadata(include_geocoder=lookup_mode == "address"),
        "warnings": warnings,
        "confidence": confidence,
    }
    if "financial_disclosures" in includes:
        disclosure_status = disclosure_source_status()
        metadata["enrichments"] = {
            "financial_disclosures": {
                "status": "available" if disclosure_status["generatedAt"] else "not_loaded",
                "source": disclosure_status,
            }
        }
    return metadata


def build_native_lookup_response(
    lookup_args: dict,
    normalized_input: dict,
    lookup_result: dict,
    lookup_mode: str,
    includes: Set[str],
    include_warnings: Optional[List[str]] = None,
) -> dict:
    warnings = native_lookup_warnings(lookup_result, lookup_mode, include_warnings)
    jurisdiction_confidence = (
        "exact" if lookup_mode == "address" and lookup_result.get("matched_address") else "approximate"
    )
    if not has_lookup_matches(lookup_result):
        jurisdiction_confidence = "none"
    raw_input = lookup_args.get("address") or ", ".join(
        value
        for value in [
            lookup_args.get("street"),
            lookup_args.get("city"),
            lookup_args.get("state"),
            lookup_args.get("zip_code"),
        ]
        if value
    )
    return {
        "input": {"raw": raw_input, "normalized": normalized_input},
        "jurisdictions": build_native_jurisdictions(lookup_result, jurisdiction_confidence),
        "offices": build_native_offices(lookup_result, includes),
        "metadata": build_native_metadata(lookup_result, lookup_mode, includes, warnings),
    }


def lookup_result_for_division(division_id: str) -> Optional[dict]:
    if division_id == COUNTRY_OCD_ID:
        return build_lookup_result()

    state_abbr = parse_state_from_division_id(division_id)
    if not state_abbr:
        return None

    congressional_district = parse_cd_from_division_id(division_id)
    if congressional_district is not None:
        return build_lookup_result(
            districts=[
                {
                    "state": state_abbr,
                    "district_number": congressional_district,
                    "district": format_district_label(state_abbr, congressional_district),
                }
            ]
        )

    legislative_state, chamber, identifier = parse_state_legislative_from_division_id(division_id)
    if legislative_state and chamber and identifier:
        district_info = {
            "state": legislative_state,
            "district_name": identifier,
            "district_key_candidates": [identifier, identifier.lstrip("0") or identifier],
            "division_id": division_id,
            "division_name": state_legislative_division_name(
                legislative_state,
                chamber,
                identifier,
            ),
        }
        if chamber == "upper":
            return build_lookup_result(state_upper_district=district_info)
        return build_lookup_result(state_lower_district=district_info)

    return build_lookup_result(states=[state_abbr])


def find_native_official(official_id: str, includes: Set[str]) -> Optional[dict]:
    seen = set()
    collections = [
        *get_senators_by_state().values(),
        *get_reps_by_district().values(),
        *get_statewide_executives_by_state().values(),
        *get_state_upper_by_district().values(),
        *get_state_lower_by_district().values(),
        *get_state_legislature_by_district().values(),
    ]
    for officials in collections:
        for official in officials:
            registry_key = official_registry_key(official)
            if registry_key in seen:
                continue
            seen.add(registry_key)
            native_official = build_native_official(official, includes)
            if native_official["id"] == official_id:
                return native_official
    return None


@api_bp.route("/v1/lookup/address")
def v1_lookup_address():
    includes, include_warnings = parse_native_includes()
    lookup_args, error = parse_address_lookup_args()
    if error:
        payload, status_code = error
        return jsonify(payload), status_code

    try:
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
        response_payload = build_native_lookup_response(
            lookup_args,
            normalized_input,
            lookup_result,
            "address",
            includes,
            include_warnings,
        )
        if not has_lookup_matches(lookup_result):
            return jsonify(response_payload), 404
        return jsonify(response_payload)
    except requests.RequestException as exc:
        return jsonify({"error": "Unable to geocode address", "details": str(exc)}), 502
    except (OSError, ValueError) as exc:
        return jsonify({"error": "Unable to load bundled legislator data", "details": str(exc)}), 500


@api_bp.route("/v1/lookup/zip/<zip_code>")
def v1_lookup_zip(zip_code):
    if not re.fullmatch(r"\d{5}", zip_code):
        abort(404)

    includes, include_warnings = parse_native_includes()
    try:
        lookup_result = build_lookup_result(districts=lookup_districts(zip_code))
        normalized_input = build_normalized_input_from_request(
            zip_code=zip_code,
            districts=lookup_result["districts"],
            states=lookup_states_for_result(lookup_result),
        )
        response_payload = build_native_lookup_response(
            {"zip_code": zip_code},
            normalized_input,
            lookup_result,
            "zip",
            includes,
            include_warnings,
        )
        if not has_lookup_matches(lookup_result):
            return jsonify(response_payload), 404
        return jsonify(response_payload)
    except (OSError, ValueError) as exc:
        return jsonify({"error": "Unable to load bundled legislator data", "details": str(exc)}), 500


def build_native_division_payload(
    division_id: str,
    lookup_result: dict,
    includes: Set[str],
) -> Optional[dict]:
    jurisdictions = build_native_jurisdictions(lookup_result, "exact")
    division = next(
        (jurisdiction for jurisdiction in jurisdictions if jurisdiction["id"] == division_id),
        None,
    )
    if not division:
        return None
    return {
        "division": division,
        "offices": build_native_offices(lookup_result, includes),
        "metadata": build_native_metadata(lookup_result, "division", includes, []),
    }


@api_bp.route("/v1/divisions/<path:division_id>/officials")
def v1_division_officials(division_id):
    includes, include_warnings = parse_native_includes()
    lookup_result = lookup_result_for_division(division_id)
    if lookup_result is None:
        abort(404)

    payload = build_native_division_payload(division_id, lookup_result, includes)
    if payload is None:
        abort(404)

    officials = []
    seen = set()
    for office in payload["offices"]:
        if office["divisionId"] != division_id:
            continue
        for official in office["officials"]:
            if official["id"] not in seen:
                officials.append(official)
                seen.add(official["id"])

    warnings = include_warnings
    if not officials:
        warnings.append("No officials were found for this division.")
    return jsonify(
        {
            "division": payload["division"],
            "officials": officials,
            "metadata": build_native_metadata(lookup_result, "division", includes, warnings),
        }
    )


@api_bp.route("/v1/divisions/<path:division_id>")
def v1_division(division_id):
    includes, include_warnings = parse_native_includes()
    lookup_result = lookup_result_for_division(division_id)
    if lookup_result is None:
        abort(404)

    payload = build_native_division_payload(division_id, lookup_result, includes)
    if payload is None:
        abort(404)
    payload["metadata"]["warnings"].extend(include_warnings)
    return jsonify(payload)


@api_bp.route("/v1/officials/<path:official_id>")
def v1_official(official_id):
    includes, include_warnings = parse_native_includes()
    official = find_native_official(official_id, includes)
    if not official:
        abort(404)
    return jsonify(
        {
            "official": official,
            "metadata": {
                "generatedAt": utc_now_iso(),
                "sources": source_metadata(include_geocoder=False),
                "warnings": include_warnings,
                "confidence": "source_record",
            },
        }
    )


@api_bp.route("/v1/sources/status")
def v1_sources_status():
    files = [
        ("federal_officials", DATA_DIR / "federal_officials.json", load_federal_officials()),
        ("state_officials", DATA_DIR / "state_officials.json", load_state_officials()),
        ("zip_districts", DATA_DIR / "zip_districts.json", load_zip_districts()),
        ("financial_disclosures", DATA_DIR / "financial_disclosures.json", load_financial_disclosures()),
    ]
    return jsonify(
        {
            "generatedAt": utc_now_iso(),
            "sources": source_metadata(include_geocoder=True),
            "financialDisclosures": disclosure_source_status(),
            "files": [
                {
                    "type": source_type,
                    "path": str(path.relative_to(DATA_DIR.parent)),
                    "generatedAt": data.get("generated_at"),
                    "available": path.exists(),
                    "sizeBytes": path.stat().st_size if path.exists() else None,
                }
                for source_type, path, data in files
            ],
        }
    )


@api_bp.route("/api/zip/<zip_code>/districts")
def get_zip_districts(zip_code):
    try:
        lookup_result = build_lookup_result(districts=lookup_districts(zip_code))
        normalized_input = build_normalized_input_from_request(
            zip_code=zip_code,
            districts=lookup_result["districts"],
            states=lookup_states_for_result(lookup_result),
        )
        response_payload = build_divisions_response(normalized_input, lookup_result)
        if not lookup_result["districts"]:
            return jsonify(response_payload), 404
        return jsonify(response_payload)
    except (OSError, ValueError) as exc:
        return jsonify(
            {"error": "Unable to load ZIP-to-district data", "details": str(exc)}
        ), 500


@api_bp.route("/api/address/districts")
def get_address_districts():
    lookup_args, error = parse_address_lookup_args()
    if error:
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
    except requests.RequestException as exc:
        return jsonify({"error": "Unable to geocode address", "details": str(exc)}), 502


@api_bp.route("/api/rep/address")
def get_rep_by_address():
    lookup_args, error = parse_address_lookup_args()
    if error:
        payload, status_code = error
        return jsonify(payload), status_code

    try:
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
    except requests.RequestException as exc:
        return jsonify({"error": "Unable to geocode address", "details": str(exc)}), 502
    except (OSError, ValueError) as exc:
        return jsonify(
            {"error": "Unable to load bundled legislator data", "details": str(exc)}
        ), 500


@api_bp.route("/api/rep/<zip_code>")
@api_bp.route("/api/<zip_code>")
def get_rep(zip_code):
    if request.args.get("address") or request.args.get("street"):
        lookup_args, error = parse_address_lookup_args(default_zip=zip_code)
        if error:
            payload, status_code = error
            return jsonify(payload), status_code

        try:
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
        except requests.RequestException as exc:
            return jsonify({"error": "Unable to geocode address", "details": str(exc)}), 502
        except (OSError, ValueError) as exc:
            return jsonify(
                {"error": "Unable to load bundled legislator data", "details": str(exc)}
            ), 500

    try:
        lookup_result = build_lookup_result(districts=lookup_districts(zip_code))
        normalized_input = build_normalized_input_from_request(
            zip_code=zip_code,
            districts=lookup_result["districts"],
            states=lookup_states_for_result(lookup_result),
        )
        response_payload = build_google_response(normalized_input, lookup_result)
        if not lookup_result["districts"]:
            return jsonify(response_payload), 404
        return jsonify(response_payload)
    except (OSError, ValueError) as exc:
        return jsonify(
            {"error": "Unable to load bundled legislator data", "details": str(exc)}
        ), 500
