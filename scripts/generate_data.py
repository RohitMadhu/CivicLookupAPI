import csv
import io
import json
import os
import re
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path

import requests
import yaml

LEGISLATORS_URL = "https://unitedstates.github.io/congress-legislators/legislators-current.json"
SOCIAL_MEDIA_URL = "https://unitedstates.github.io/congress-legislators/legislators-social-media.json"
ZIP_DISTRICTS_URL = (
    "https://raw.githubusercontent.com/OpenSourceActivismTech/us-zipcodes-congress/master/zccd.csv"
)
OPENSTATES_PEOPLE_REPO = "https://github.com/openstates/people"
KADOA_BASE_URL = "https://congress.kadoa.com/data"
KADOA_TRADES_URL = f"{KADOA_BASE_URL}/trades.json"
KADOA_FILERS_URL = f"{KADOA_BASE_URL}/filers.json"
KADOA_STATS_URL = f"{KADOA_BASE_URL}/stats.json"
REQUEST_TIMEOUT_SECONDS = 60

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

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
DEFAULT_OPENSTATES_PEOPLE_DIR = Path(os.environ.get("OPENSTATES_PEOPLE_DIR", "/tmp/openstates-people"))

LEGISLATIVE_ROLE_TYPES = {"upper", "lower", "legislature"}
STATEWIDE_EXECUTIVE_ROLE_TYPES = {
    "governor",
    "lt_governor",
    "secretary of state",
    "chief election officer",
}
STATEWIDE_EXECUTIVE_ROLE_ORDER = {
    "governor": 0,
    "lt_governor": 1,
    "secretary of state": 2,
    "chief election officer": 3,
}
OFFICE_CLASSIFICATION_ORDER = {
    "capitol": 0,
    "district": 1,
    "office": 2,
}
DISTRICT_PREFIX_PATTERNS = (
    re.compile(r"^state senate district\s+", re.IGNORECASE),
    re.compile(r"^state house district\s+", re.IGNORECASE),
    re.compile(r"^state legislative district\s+", re.IGNORECASE),
)
DISTRICT_SUFFIX_PATTERNS = (
    re.compile(r"\s+state house district$", re.IGNORECASE),
    re.compile(r"\s+senatorial district$", re.IGNORECASE),
    re.compile(r"\s+district$", re.IGNORECASE),
)


def fetch_json(url):
    response = requests.get(url, timeout=REQUEST_TIMEOUT_SECONDS)
    response.raise_for_status()
    return response.json()


def fetch_text(url):
    response = requests.get(url, timeout=REQUEST_TIMEOUT_SECONDS)
    response.raise_for_status()
    return response.text


def build_full_name(name_dict):
    official_full = name_dict.get("official_full")
    if official_full:
        return official_full
    return " ".join(
        part
        for part in [name_dict.get("first"), name_dict.get("middle"), name_dict.get("last")]
        if part
    ).strip()


def normalize_district(value):
    try:
        district_number = int(value)
        return 0 if district_number == 98 else district_number
    except (TypeError, ValueError):
        return None


def format_district_label(state_abbr, district_number):
    state_name = STATE_NAMES.get(state_abbr, state_abbr)
    if district_number == 0:
        return f"{state_name} At Large"
    return f"{state_name} District {district_number}"


def normalize_state_legislative_district(value):
    if not value:
        return ""

    normalized = " ".join(str(value).strip().split())
    for pattern in DISTRICT_PREFIX_PATTERNS:
        normalized = pattern.sub("", normalized)
    for pattern in DISTRICT_SUFFIX_PATTERNS:
        normalized = pattern.sub("", normalized)
    return normalized.strip().lower()


def parse_iso_date(value):
    if not value:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            return None
    return None


def is_current_role(role, today):
    start_date = parse_iso_date(role.get("start_date"))
    end_date = parse_iso_date(role.get("end_date"))
    if start_date and start_date > today:
        return False
    if end_date and end_date < today:
        return False
    return True


def choose_primary_office(offices):
    if not offices:
        return {}
    return min(
        offices,
        key=lambda office: (
            OFFICE_CLASSIFICATION_ORDER.get(office.get("classification"), 99),
            office.get("address") or "",
        ),
    )


def choose_primary_url(links):
    if not links:
        return None
    for link in links:
        if not link.get("note"):
            return link.get("url")
    return links[0].get("url")


def build_state_person(person, state_abbr):
    primary_office = choose_primary_office(person.get("offices", []))
    party_entries = person.get("party") or []
    party_name = None
    if party_entries:
        party_name = party_entries[0].get("name")

    return {
        "name": person.get("name"),
        "party": party_name,
        "email": person.get("email"),
        "image": person.get("image"),
        "url": choose_primary_url(person.get("links", [])),
        "phone": primary_office.get("voice"),
        "address": primary_office.get("address"),
        "social": person.get("ids", {}),
        "state": state_abbr,
        "state_name": STATE_NAMES.get(state_abbr, state_abbr),
        "openstates_id": person.get("id"),
    }


def build_federal_officials():
    legislators = fetch_json(LEGISLATORS_URL)
    social_media = fetch_json(SOCIAL_MEDIA_URL)
    social_by_bioguide = {}
    for social_entry in social_media:
        bioguide_id = social_entry.get("id", {}).get("bioguide")
        if bioguide_id:
            social_by_bioguide[bioguide_id] = social_entry.get("social", {})

    house_by_district = defaultdict(list)
    senate_by_state = defaultdict(list)

    for legislator in legislators:
        terms = legislator.get("terms", [])
        if not terms:
            continue

        current_term = max(terms, key=lambda term: term.get("start", ""))
        chamber = current_term.get("type")
        if chamber not in {"rep", "sen"}:
            continue

        state_abbr = current_term.get("state")
        if not state_abbr:
            continue

        bioguide_id = legislator.get("id", {}).get("bioguide")
        official = {
            "name": build_full_name(legislator.get("name", {})),
            "party": current_term.get("party"),
            "url": current_term.get("url"),
            "phone": current_term.get("phone"),
            "address": current_term.get("address"),
            "office": current_term.get("office"),
            "social": social_by_bioguide.get(bioguide_id, {}),
            "state": state_abbr,
            "state_name": STATE_NAMES.get(state_abbr, state_abbr),
            "bioguide_id": bioguide_id,
        }

        if chamber == "rep":
            official["chamber"] = "house"
            district_number = normalize_district(current_term.get("district", 0))
            if district_number is None:
                continue
            official["district_number"] = district_number
            official["district"] = format_district_label(state_abbr, district_number)
            house_by_district[f"{state_abbr}:{district_number}"].append(official)
        else:
            official["chamber"] = "senate"
            official["class"] = current_term.get("class")
            senate_by_state[state_abbr].append(official)

    for officials in house_by_district.values():
        officials.sort(key=lambda official: official["name"])

    for officials in senate_by_state.values():
        officials.sort(key=lambda official: official["name"])

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "sources": {
            "legislators": LEGISLATORS_URL,
            "social_media": SOCIAL_MEDIA_URL,
        },
        "house_by_district": dict(sorted(house_by_district.items())),
        "senate_by_state": dict(sorted(senate_by_state.items())),
    }


def build_zip_districts():
    reader = csv.DictReader(io.StringIO(fetch_text(ZIP_DISTRICTS_URL)))
    districts_by_zip = defaultdict(list)
    seen = defaultdict(set)

    for row in reader:
        zip_code = (row.get("zcta") or "").strip()
        state_abbr = (row.get("state_abbr") or "").strip()
        district_number = normalize_district(row.get("cd"))
        if not zip_code or not state_abbr or district_number is None:
            continue

        district_key = (state_abbr, district_number)
        if district_key in seen[zip_code]:
            continue

        seen[zip_code].add(district_key)
        districts_by_zip[zip_code].append(
            {
                "state": state_abbr,
                "district_number": district_number,
                "district": format_district_label(state_abbr, district_number),
            }
        )

    for districts in districts_by_zip.values():
        districts.sort(key=lambda district: (district["state"], district["district_number"]))

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "sources": {
            "zip_districts": ZIP_DISTRICTS_URL,
        },
        "districts_by_zip": dict(sorted(districts_by_zip.items())),
    }


def build_state_officials(openstates_people_dir):
    people_data_dir = openstates_people_dir / "data"
    if not people_data_dir.exists():
        raise FileNotFoundError(
            "Open States people repo not found at "
            f"{openstates_people_dir}. Clone {OPENSTATES_PEOPLE_REPO} there, "
            "or set OPENSTATES_PEOPLE_DIR to an existing checkout before running this script."
        )

    today = date.today()
    state_upper_by_district = defaultdict(list)
    state_lower_by_district = defaultdict(list)
    state_legislature_by_district = defaultdict(list)
    statewide_executives_by_state = defaultdict(list)
    seen_legislators = {
        "upper": defaultdict(set),
        "lower": defaultdict(set),
        "legislature": defaultdict(set),
    }
    seen_executives = defaultdict(set)

    for path in sorted(people_data_dir.glob("*/*/*.yml")):
        collection_name = path.parts[-2]
        if collection_name not in {"legislature", "executive"}:
            continue

        person = yaml.safe_load(path.read_text())
        if not person:
            continue

        state_abbr = path.parts[-3].upper()
        person_id = person.get("id") or person.get("name")

        if collection_name == "legislature":
            for role in person.get("roles", []):
                role_type = role.get("type")
                if role_type not in LEGISLATIVE_ROLE_TYPES or not is_current_role(role, today):
                    continue

                district_name = (role.get("district") or "").strip()
                district_key = normalize_state_legislative_district(district_name)
                if not district_key:
                    continue

                if person_id in seen_legislators[role_type][f"{state_abbr}:{district_key}"]:
                    continue
                seen_legislators[role_type][f"{state_abbr}:{district_key}"].add(person_id)

                official = build_state_person(person, state_abbr)
                official["chamber"] = role_type
                official["district"] = district_name
                official["district_key"] = district_key

                district_id = f"{state_abbr}:{district_key}"
                if role_type == "upper":
                    state_upper_by_district[district_id].append(official)
                elif role_type == "lower":
                    state_lower_by_district[district_id].append(official)
                else:
                    state_legislature_by_district[district_id].append(official)

        if collection_name == "executive":
            for role in person.get("roles", []):
                role_type = role.get("type")
                if role_type not in STATEWIDE_EXECUTIVE_ROLE_TYPES or not is_current_role(role, today):
                    continue

                executive_key = (role_type, person_id)
                if executive_key in seen_executives[state_abbr]:
                    continue
                seen_executives[state_abbr].add(executive_key)

                official = build_state_person(person, state_abbr)
                official["role_type"] = role_type
                statewide_executives_by_state[state_abbr].append(official)

    for officials in state_upper_by_district.values():
        officials.sort(key=lambda official: official["name"])
    for officials in state_lower_by_district.values():
        officials.sort(key=lambda official: official["name"])
    for officials in state_legislature_by_district.values():
        officials.sort(key=lambda official: official["name"])
    for officials in statewide_executives_by_state.values():
        officials.sort(
            key=lambda official: (
                STATEWIDE_EXECUTIVE_ROLE_ORDER.get(official.get("role_type"), 99),
                official["name"],
            )
        )

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "sources": {
            "openstates_people": OPENSTATES_PEOPLE_REPO,
        },
        "state_upper_by_district": dict(sorted(state_upper_by_district.items())),
        "state_lower_by_district": dict(sorted(state_lower_by_district.items())),
        "state_legislature_by_district": dict(sorted(state_legislature_by_district.items())),
        "statewide_executives_by_state": dict(sorted(statewide_executives_by_state.items())),
    }


def normalize_match_text(value):
    if not value:
        return ""
    value = re.sub(r"[^a-z0-9]+", " ", str(value).lower())
    suffixes = {"jr", "sr", "ii", "iii", "iv", "honorable"}
    return " ".join(part for part in value.split() if part not in suffixes)


def parse_kadoa_district(office):
    if not office:
        return None
    match = re.search(r"·\s*[A-Z]{2}-(\d{1,2})", office)
    if not match:
        return None
    return int(match.group(1))


def index_kadoa_keys(record):
    keys = set()
    filer_id = record.get("id") or record.get("filer_id")
    if filer_id:
        keys.add(f"id:{filer_id}")

    normalized_name = normalize_match_text(record.get("full_name") or record.get("filer_name"))
    state = record.get("state")
    chamber = record.get("chamber")
    if normalized_name and state and chamber:
        keys.add(f"name:{state}:{chamber}:{normalized_name}")
        district_number = parse_kadoa_district(record.get("office"))
        if chamber == "house" and district_number is not None:
            keys.add(f"seat:{state}:house:{district_number}:{normalized_name}")
    return sorted(keys)


def summarize_kadoa_trades(trades):
    purchases = 0
    sales = 0
    late_filings = 0
    estimated_volume = 0
    tickers = set()
    latest_transaction_date = None
    latest_filing_date = None

    for trade in trades:
        transaction_type = (trade.get("transaction_type") or "").lower()
        if "purchase" in transaction_type:
            purchases += 1
        if "sale" in transaction_type:
            sales += 1
        if trade.get("is_late"):
            late_filings += 1
        low = trade.get("amount_range_low") or 0
        high = trade.get("amount_range_high") or low
        estimated_volume += (low + high) / 2
        if trade.get("ticker"):
            tickers.add(trade["ticker"])
        transaction_date = trade.get("transaction_date")
        filing_date = trade.get("filing_date")
        if transaction_date and (latest_transaction_date is None or transaction_date > latest_transaction_date):
            latest_transaction_date = transaction_date
        if filing_date and (latest_filing_date is None or filing_date > latest_filing_date):
            latest_filing_date = filing_date

    return {
        "trade_count": len(trades),
        "purchases": purchases,
        "sales": sales,
        "late_filings": late_filings,
        "estimated_volume": estimated_volume,
        "tickers": sorted(tickers),
        "latest_transaction_date": latest_transaction_date,
        "latest_filing_date": latest_filing_date,
    }


def build_kadoa_disclosures():
    trades = fetch_json(KADOA_TRADES_URL)
    filers = fetch_json(KADOA_FILERS_URL)
    stats = fetch_json(KADOA_STATS_URL)

    trades_by_filer = defaultdict(list)
    for trade in trades:
        filer_id = trade.get("filer_id")
        if filer_id:
            trades_by_filer[filer_id].append(trade)

    filers_by_id = {}
    indexes = defaultdict(list)
    for filer in filers:
        filer_id = filer.get("id")
        if not filer_id:
            continue
        filers_by_id[filer_id] = filer
        for key in index_kadoa_keys(filer):
            indexes[key].append(filer_id)

    summaries_by_filer = {}
    all_filer_ids = sorted(set(filers_by_id) | set(trades_by_filer))
    for filer_id in all_filer_ids:
        filer = filers_by_id.get(filer_id, {})
        recent_trades = sorted(
            trades_by_filer.get(filer_id, []),
            key=lambda trade: (
                trade.get("transaction_date") or "",
                trade.get("filing_date") or "",
                trade.get("id") or "",
            ),
            reverse=True,
        )
        recent_summary = summarize_kadoa_trades(recent_trades)
        summaries_by_filer[filer_id] = {
            "filer": filer,
            "summary": {
                "trade_count": filer.get("trade_count", recent_summary["trade_count"]),
                "purchases": filer.get("purchases", recent_summary["purchases"]),
                "sales": filer.get("sales", recent_summary["sales"]),
                "late_filings": filer.get("late_filings", recent_summary["late_filings"]),
                "estimated_volume": filer.get("est_volume", recent_summary["estimated_volume"]),
                "recent_trade_count": recent_summary["trade_count"],
                "recent_tickers": recent_summary["tickers"],
                "latest_transaction_date": recent_summary["latest_transaction_date"],
                "latest_filing_date": recent_summary["latest_filing_date"],
            },
            "recent_trades": recent_trades[:50],
        }

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "sources": {
            "kadoa_trades": KADOA_TRADES_URL,
            "kadoa_filers": KADOA_FILERS_URL,
            "kadoa_stats": KADOA_STATS_URL,
            "license": "https://github.com/kadoa-org/congress-trading-monitor/blob/main/LICENSE",
        },
        "upstream_generated_at": stats.get("generatedAt"),
        "stats": stats,
        "indexes": dict(sorted((key, sorted(set(value))) for key, value in indexes.items())),
        "filers": summaries_by_filer,
    }


def write_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def main():
    write_json(DATA_DIR / "federal_officials.json", build_federal_officials())
    write_json(DATA_DIR / "zip_districts.json", build_zip_districts())
    write_json(DATA_DIR / "state_officials.json", build_state_officials(DEFAULT_OPENSTATES_PEOPLE_DIR))
    write_json(DATA_DIR / "financial_disclosures.json", build_kadoa_disclosures())
    print("Generated data files in", DATA_DIR)


if __name__ == "__main__":
    main()
