# ZIP Code Federal and State Officials Lookup API

Flask API for looking up U.S. federal officials by ZIP code and federal plus state officials by street address, with responses shaped like Google Civic Information API's old representatives model.

## Data Sources

- Bundled local JSON at runtime:
  - `data/federal_officials.json`
  - `data/zip_districts.json`
  - `data/state_officials.json`
- Generated from:
  - `https://unitedstates.github.io/congress-legislators/legislators-current.json`
  - `https://unitedstates.github.io/congress-legislators/legislators-social-media.json`
  - [`zccd.csv`](https://github.com/OpenSourceActivismTech/us-zipcodes-congress)
  - [Open States people](https://github.com/openstates/people)
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

To use a different checkout path:

```bash
OPENSTATES_PEOPLE_DIR=/path/to/openstates-people python3 scripts/generate_data.py
```

4. Run the API:
```bash
python3 app.py
```

## Endpoints

- `GET /api/rep/<zip_code>`
Returns a Google-style `representativeInfoResponse` with `normalizedInput`, `divisions`, `offices`, and `officials`. ZIP-only responses include U.S. House, U.S. Senate, and statewide executives for the matched state or states.

- `GET /api/rep/<zip_code>?includeOffices=false`
Returns only `normalizedInput` and `divisions`, similar to Google's `includeOffices=false`.

- `GET /api/rep/<zip_code>?street=<street>&city=<city>&state=<state>`
Uses the street address to resolve ambiguous ZIPs and adds state legislative offices when the Census Geocoder returns state senate and state house districts.

- `GET /api/rep/address?street=<street>&city=<city>&state=<state>`
Address-first representative lookup with the same response shape.

- `GET /api/rep/address?address=<full address>`
One-line address lookup.

- `GET /api/zip/<zip_code>/districts`
Returns a Google-style `divisionsByAddressResponse` for ZIP-based congressional district matching.

- `GET /api/address/districts?street=<street>&city=<city>&state=<state>`
Returns a Google-style `divisionsByAddressResponse` for an address, including state legislative divisions when available.

## Example Responses

Examples below are shortened to the key fields.

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
