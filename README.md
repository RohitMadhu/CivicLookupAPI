# CivicLookupAPI

CivicLookupAPI is a Flask API for looking up U.S. federal and state officials by ZIP code or street address. It has two API modes:

- Google Civic-compatible mode under `/api`, which preserves the familiar `normalizedInput`, `divisions`, `offices`, `officials`, `officeIndices`, and `officialIndices` response model.
- Native v1 mode under `/v1`, which returns nested, source-transparent JSON that is easier for app developers to consume and can optionally include congressional financial disclosure and trading data.

## Data Sources

- Bundled local JSON at runtime:
  - `data/federal_officials.json`
  - `data/zip_districts.json`
  - `data/state_officials.json`
  - `data/financial_disclosures.json`
- Generated from:
  - `https://unitedstates.github.io/congress-legislators/legislators-current.json`
  - `https://unitedstates.github.io/congress-legislators/legislators-social-media.json`
  - [`zccd.csv`](https://github.com/OpenSourceActivismTech/us-zipcodes-congress)
  - [Open States people](https://github.com/openstates/people)
  - [Kadoa Congress Trading Monitor](https://github.com/kadoa-org/congress-trading-monitor), which publishes static JSON from House Clerk, Senate eFD, and OGE STOCK Act disclosures
- Address disambiguation uses the [U.S. Census Geocoder](https://geocoding.geo.census.gov/geo/geographies/address)

## Installation

1. Install dependencies:
```bash
python3 -m pip install -r requirements.txt
```

2. Clone the Open States people repo once, or point `OPENSTATES_PEOPLE_DIR` at an existing checkout:
```bash
git clone --depth 1 https://github.com/openstates/people.git /tmp/openstates-people
```

3. Refresh bundled data when needed:
```bash
python3 scripts/generate_data.py
```

To refresh only the financial disclosure/trading cache:

```bash
python3 scripts/fetch_kadoa_data.py
```

To use a different checkout path:

```bash
OPENSTATES_PEOPLE_DIR=/path/to/openstates-people python3 scripts/generate_data.py
```

4. Run the API:
```bash
python3 app.py
```

## Google-Compatible API

The `/api` routes are a compatibility layer. They intentionally keep Google Civic-style response shapes and index references.

- `GET /api/rep/<zip_code>` or `GET /api/<zip_code>`
Returns a Google-style `representativeInfoResponse` with `normalizedInput`, `divisions`, `offices`, and `officials`. ZIP-only responses include U.S. House, U.S. Senate, and statewide executives for the matched state or states.

- `GET /api/rep/<zip_code>?includeOffices=false` or `GET /api/<zip_code>?includeOffices=false`
Returns only `normalizedInput` and `divisions`, similar to Google's `includeOffices=false`.

- `GET /api/rep/<zip_code>?street=<street>&city=<city>&state=<state>` or `GET /api/<zip_code>?street=<street>&city=<city>&state=<state>`
Uses the street address to resolve ambiguous ZIPs and adds state legislative offices when the Census Geocoder returns state senate and state house districts.

- `GET /api/rep/address?street=<street>&city=<city>&state=<state>`
Address-first representative lookup with the same response shape.

- `GET /api/rep/address?address=<full address>`
One-line address lookup.

- `GET /api/zip/<zip_code>/districts`
Returns a Google-style `divisionsByAddressResponse` for ZIP-based congressional district matching.

- `GET /api/address/districts?street=<street>&city=<city>&state=<state>`
Returns a Google-style `divisionsByAddressResponse` for an address, including state legislative divisions when available.

## Native v1 API

The `/v1` routes return nested JSON with stable IDs, source metadata, warnings, and direct office-to-official relationships.

- `GET /v1/lookup/address?address=<full address>`
One-line address lookup. Uses the U.S. Census Geocoder for exact congressional and state legislative district matching.

- `GET /v1/lookup/address?street=<street>&city=<city>&state=<state>`
Structured address lookup.

- `GET /v1/lookup/address?street=<street>&zip=<zip>`
Structured address lookup using ZIP instead of city and state.

- `GET /v1/lookup/zip/<zip_code>`
ZIP-derived lookup. This is fully local and includes warnings because ZIP-only district matching can be ambiguous.

- `GET /v1/divisions/<division_id>`
Returns a division, related offices, and source metadata. Division IDs are OCD IDs such as `ocd-division/country:us/state:va/cd:11`.

- `GET /v1/divisions/<division_id>/officials`
Returns officials associated with a division.

- `GET /v1/officials/<official_id>`
Returns one official by stable ID. Federal officials prefer `bioguide:<id>`, state officials prefer `openstates:<id>`, and records without source IDs fall back to deterministic `slug:<value>` IDs.

- `GET /v1/sources/status`
Returns bundled data file status, generated timestamps, and source provenance.

- `GET /health`
Basic service health check.

- `GET /metrics`
Basic Prometheus-style metrics endpoint.

## Response Differences

- Google-compatible `/api` responses match the old Civic API pattern: offices reference officials by `officialIndices`, and divisions reference offices by `officeIndices`.
- Native `/v1` lookup responses nest officials directly inside offices, so app developers do not have to join arrays by index.
- Native `/v1` responses include `metadata.sources`, `metadata.generatedAt`, `metadata.warnings`, and `metadata.confidence`.
- ZIP-only native lookups include warnings when a ZIP maps to multiple congressional districts or when address lookup would be more precise.
- Address native lookups include a warning when the Census Geocoder returns no match.

## Optional Includes

Native v1 supports an `include` query parameter for future enrichment:

- `include=financial_disclosures` adds Kadoa Congress Trading Monitor matches when an official can be linked to a filer. Each match includes filer metadata, aggregate trade counts, estimated volume, late filing counts, and recent trade rows with source filing URLs.
- `include=social`, `include=offices`, and `include=sources` are reserved as stable extension points. Current native lookup responses already include offices, social handles, and source metadata by default.
- Multiple includes can be comma-separated, for example `include=financial_disclosures,sources`.

Financial disclosure matching is deterministic and local. Federal officials are matched to Kadoa filers by normalized name plus state/chamber, with House matches also using district when available. Records that do not match return `financialDisclosures.status = "no_match"` instead of failing the lookup.

## Examples

Examples below are shortened to the key fields.

`GET /v1/lookup/zip/66952`

```json
{
  "input": {
    "normalized": {
      "city": "",
      "line1": "",
      "state": "KS",
      "zip": "66952"
    },
    "raw": "66952"
  },
  "jurisdictions": [
    {
      "confidence": "approximate",
      "id": "ocd-division/country:us",
      "level": "country",
      "name": "United States",
      "type": "country"
    },
    {
      "confidence": "approximate",
      "id": "ocd-division/country:us/state:ks",
      "level": "administrativeArea1",
      "name": "Kansas",
      "type": "state"
    },
    {
      "confidence": "approximate",
      "id": "ocd-division/country:us/state:ks/cd:1",
      "level": "country",
      "name": "Kansas District 1",
      "type": "congressional_district"
    }
  ],
  "metadata": {
    "confidence": "zip_approximate",
    "generatedAt": "2026-05-30T13:36:43.463776+00:00",
    "sources": [
      {
        "generatedAt": "2026-03-31T01:09:17.999462+00:00",
        "name": "unitedstates/congress-legislators",
        "type": "federal_officials",
        "url": "https://unitedstates.github.io/congress-legislators/legislators-current.json"
      },
      {
        "generatedAt": "2026-03-31T01:09:52.132546+00:00",
        "name": "OpenStates people",
        "type": "state_officials",
        "url": "https://github.com/openstates/people"
      },
      {
        "generatedAt": "2026-03-31T01:09:18.307489+00:00",
        "name": "OpenSourceActivismTech/us-zipcodes-congress",
        "type": "zip_districts",
        "url": "https://raw.githubusercontent.com/OpenSourceActivismTech/us-zipcodes-congress/master/zccd.csv"
      }
    ],
    "warnings": [
      "ZIP-only lookup may be ambiguous; use an address lookup for exact district matching."
    ]
  },
  "offices": [
    {
      "divisionId": "ocd-division/country:us/state:ks",
      "id": "us-senate-ks",
      "level": "country",
      "name": "United States Senate",
      "officials": [
        {
          "chamber": "senate",
          "district": null,
          "emails": [],
          "id": "bioguide:M000934",
          "name": "Jerry Moran",
          "party": "Republican",
          "phones": [
            "202-224-6521"
          ],
          "photoUrl": null,
          "social": {
            "facebook": "jerrymoran",
            "instagram": "senjerrymoran",
            "instagram_id": 298271065,
            "twitter": "JerryMoran",
            "twitter_id": "18632666",
            "youtube": "senatorjerrymoran",
            "youtube_id": "UC1oRxeUPam6-53wPBZ3N02A"
          },
          "state": "KS",
          "urls": [
            "https://www.moran.senate.gov"
          ]
        },
        {
          "chamber": "senate",
          "district": null,
          "emails": [],
          "id": "bioguide:M001198",
          "name": "Roger Marshall",
          "party": "Republican",
          "phones": [
            "202-224-4774"
          ],
          "photoUrl": null,
          "social": {
            "facebook": "RogerMarshallMD",
            "instagram": "senrogermarshall",
            "twitter": "SenatorMarshall",
            "twitter_id": "1336344005588738052",
            "youtube": "UCR3nOFMqBB-kRpKFwgapMaQ"
          },
          "state": "KS",
          "urls": [
            "https://www.marshall.senate.gov"
          ]
        }
      ],
      "role": "legislatorUpperBody"
    },
    {
      "divisionId": "ocd-division/country:us/state:ks/cd:1",
      "id": "us-house-ks-1",
      "level": "country",
      "name": "United States House of Representatives",
      "officials": [
        {
          "chamber": "house",
          "district": "Kansas District 1",
          "emails": [],
          "id": "bioguide:M000871",
          "name": "Tracey Mann",
          "party": "Republican",
          "phones": [
            "202-225-2715"
          ],
          "photoUrl": null,
          "social": {
            "facebook": "Congressman-Tracey-Mann-105522931489227",
            "instagram": "reptraceymann",
            "twitter": "RepMann",
            "twitter_id": "1345825008887721986"
          },
          "state": "KS",
          "urls": [
            "https://mann.house.gov"
          ]
        }
      ],
      "role": "legislatorLowerBody"
    },
    {
      "divisionId": "ocd-division/country:us/state:ks",
      "id": "ks-governor",
      "level": "administrativeArea1",
      "name": "Kansas Governor",
      "officials": [
        {
          "chamber": "governor",
          "district": null,
          "emails": [],
          "id": "openstates:ocd-person/2654d836-700f-464d-a0dd-81cb0bd77b9e",
          "name": "Laura Kelly",
          "party": "Democratic",
          "phones": [
            "785-368-8500"
          ],
          "photoUrl": "https://governor.kansas.gov/wp-content/uploads/2019/01/Kansas-Governor.jpg",
          "social": {
            "twitter": "GovLauraKelly"
          },
          "state": "KS",
          "urls": [
            "https://governor.kansas.gov/"
          ]
        }
      ],
      "role": "headOfGovernment"
    },
    {
      "divisionId": "ocd-division/country:us/state:ks",
      "id": "ks-secretary-of-state",
      "level": "administrativeArea1",
      "name": "Kansas Secretary of State",
      "officials": [
        {
          "chamber": "secretary of state",
          "district": null,
          "emails": [
            "sos@sos.ks.gov"
          ],
          "id": "openstates:ocd-person/5ef16835-fd08-407d-abaf-0407a665ada1",
          "name": "Scott Schwab",
          "party": "Republican",
          "phones": [
            "785-296-4564"
          ],
          "photoUrl": "https://sos.ks.gov/images/about-the-office/ss-headshot.jpg",
          "social": {
            "twitter": "KansasSOS"
          },
          "state": "KS",
          "urls": [
            "https://sos.ks.gov"
          ]
        }
      ],
      "role": "governmentOfficer"
    }
  ]
}
```

`GET /api/rep/address?street=1100%20Massachusetts%20St&city=Lawrence&state=KS`

```json
{
  "kind": "civicinfo#representativeInfoResponse",
  "normalizedInput": {
    "line1": "1100 MASSACHUSETTS ST",
    "city": "LAWRENCE",
    "state": "KS",
    "zip": "66044"
  },
  "divisions": {
    "ocd-division/country:us": {
      "name": "United States"
    },
    "ocd-division/country:us/state:ks": {
      "name": "Kansas",
      "officeIndices": [0, 2, 3]
    },
    "ocd-division/country:us/state:ks/cd:1": {
      "name": "Kansas District 1",
      "officeIndices": [1]
    },
    "ocd-division/country:us/state:ks/sldu:002": {
      "name": "Kansas State Senate District 2",
      "officeIndices": [4]
    },
    "ocd-division/country:us/state:ks/sldl:046": {
      "name": "Kansas State House District 46",
      "officeIndices": [5]
    }
  },
  "offices": [
    {
      "name": "United States Senate",
      "divisionId": "ocd-division/country:us/state:ks",
      "levels": ["country"],
      "roles": ["legislatorUpperBody"]
    },
    {
      "name": "United States House of Representatives",
      "divisionId": "ocd-division/country:us/state:ks/cd:1",
      "levels": ["country"],
      "roles": ["legislatorLowerBody"]
    },
    {
      "name": "Kansas Governor",
      "divisionId": "ocd-division/country:us/state:ks",
      "levels": ["administrativeArea1"],
      "roles": ["headOfGovernment"]
    },
    {
      "name": "Kansas Secretary of State",
      "divisionId": "ocd-division/country:us/state:ks",
      "levels": ["administrativeArea1"],
      "roles": ["governmentOfficer"]
    },
    {
      "name": "Kansas State Senate",
      "divisionId": "ocd-division/country:us/state:ks/sldu:002",
      "levels": ["administrativeArea1"],
      "roles": ["legislatorUpperBody"]
    },
    {
      "name": "Kansas State House",
      "divisionId": "ocd-division/country:us/state:ks/sldl:046",
      "levels": ["administrativeArea1"],
      "roles": ["legislatorLowerBody"]
    }
  ],
  "officials": [
    { "name": "Jerry Moran" },
    { "name": "Roger Marshall" },
    { "name": "Tracey Mann" },
    { "name": "Laura Kelly" },
    { "name": "Scott Schwab" },
    { "name": "Marci Francisco" },
    { "name": "Brooklynne Mosley" }
  ]
}
```

`GET /api/address/districts?street=1100%20Massachusetts%20St&city=Lawrence&state=KS`

```json
{
  "kind": "civicinfo#divisionsByAddressResponse",
  "normalizedInput": {
    "line1": "1100 MASSACHUSETTS ST",
    "city": "LAWRENCE",
    "state": "KS",
    "zip": "66044"
  },
  "divisions": {
    "ocd-division/country:us": {
      "name": "United States"
    },
    "ocd-division/country:us/state:ks": {
      "name": "Kansas"
    },
    "ocd-division/country:us/state:ks/cd:1": {
      "name": "Kansas District 1"
    },
    "ocd-division/country:us/state:ks/sldu:002": {
      "name": "Kansas State Senate District 2"
    },
    "ocd-division/country:us/state:ks/sldl:046": {
      "name": "Kansas State House District 46"
    }
  }
}
```

## Notes

- ZIP-only lookups are fully local and do not fetch GitHub at request time.
- Address lookups still call the Census Geocoder so ambiguous ZIPs can resolve to the correct congressional and state legislative districts.
- State legislative offices require an address lookup because a 5-digit ZIP is not precise enough to map reliably to state senate and state house districts.
- Statewide executives are included when Open States has current records for that jurisdiction. The bundled data currently covers governor, lieutenant governor, secretary of state, and chief election officer roles when available.
- `includeOffices=false` is supported on representative endpoints.
- ZIP-to-district lookups are approximate because 5-digit ZIPs and Census ZCTAs are not a perfect 1:1 match.
