import re
from typing import List, Optional

from civiclookup.data.loaders import load_financial_disclosures


def normalize_match_text(value: Optional[str]) -> str:
    if not value:
        return ""
    value = re.sub(r"[^a-z0-9]+", " ", str(value).lower())
    suffixes = {"jr", "sr", "ii", "iii", "iv", "honorable"}
    return " ".join(part for part in value.split() if part not in suffixes)


def official_district_number(official: dict) -> Optional[int]:
    if official.get("district_number") is not None:
        return official["district_number"]
    district = official.get("district")
    if not district:
        return None
    match = re.search(r"\b(?:district|cd)\s+(\d{1,2})\b", str(district), re.IGNORECASE)
    if match:
        return int(match.group(1))
    return None


def candidate_index_keys(official: dict) -> List[str]:
    state = official.get("state")
    chamber = official.get("chamber")
    name = normalize_match_text(official.get("name"))
    keys = []
    if not state or not chamber or not name:
        return keys

    if chamber == "house":
        district_number = official_district_number(official)
        if district_number is not None:
            keys.append(f"seat:{state}:house:{district_number}:{name}")
    if chamber in {"house", "senate"}:
        keys.append(f"name:{state}:{chamber}:{name}")
    return keys


def find_filer_ids_for_official(official: dict) -> List[str]:
    disclosures = load_financial_disclosures()
    indexes = disclosures.get("indexes", {})
    filer_ids = []
    for key in candidate_index_keys(official):
        for filer_id in indexes.get(key, []):
            if filer_id not in filer_ids:
                filer_ids.append(filer_id)
    return filer_ids


def get_financial_disclosures_for_official(official: dict) -> dict:
    disclosures = load_financial_disclosures()
    filer_ids = find_filer_ids_for_official(official)
    matched_filers = [
        disclosures.get("filers", {}).get(filer_id)
        for filer_id in filer_ids
        if disclosures.get("filers", {}).get(filer_id)
    ]

    if not matched_filers:
        return {
            "status": "no_match",
            "source": "kadoa_congress_trading_monitor",
            "generatedAt": disclosures.get("generated_at"),
            "message": "No matching Kadoa disclosure filer was found for this official.",
            "matches": [],
        }

    return {
        "status": "matched",
        "source": "kadoa_congress_trading_monitor",
        "generatedAt": disclosures.get("generated_at"),
        "upstreamGeneratedAt": disclosures.get("upstream_generated_at"),
        "matches": [
            {
                "filer": match.get("filer", {}),
                "summary": match.get("summary", {}),
                "recentTrades": match.get("recent_trades", []),
            }
            for match in matched_filers
        ],
    }


def disclosure_source_status() -> dict:
    disclosures = load_financial_disclosures()
    return {
        "name": "Kadoa Congress Trading Monitor",
        "type": "financial_disclosures",
        "generatedAt": disclosures.get("generated_at"),
        "upstreamGeneratedAt": disclosures.get("upstream_generated_at"),
        "sources": disclosures.get("sources", {}),
        "stats": disclosures.get("stats", {}),
        "filerCount": len(disclosures.get("filers", {})),
    }
