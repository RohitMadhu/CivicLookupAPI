from civiclookup.api import routes


class MockResponse:
    def __init__(self, payload):
        self.payload = payload

    def json(self):
        return self.payload

    def raise_for_status(self):
        return None


def test_zip_rep_lookup_returns_google_shape(client):
    response = client.get("/api/rep/60601")

    assert response.status_code == 200
    payload = response.get_json()

    assert payload["kind"] == "civicinfo#representativeInfoResponse"
    assert payload["normalizedInput"] == {"line1": "", "city": "", "state": "IL", "zip": "60601"}
    assert "districts" not in payload
    assert "count" not in payload
    assert "offices" in payload
    assert "officials" in payload
    assert "ocd-division/country:us" in payload["divisions"]
    assert any(office["name"] == "United States Senate" for office in payload["offices"])
    assert any(office["name"] == "United States House of Representatives" for office in payload["offices"])


def test_include_offices_false_omits_offices_and_officials(client):
    response = client.get("/api/rep/60601?includeOffices=false")

    assert response.status_code == 200
    payload = response.get_json()

    assert payload["kind"] == "civicinfo#representativeInfoResponse"
    assert "offices" not in payload
    assert "officials" not in payload
    assert "ocd-division/country:us/state:il" in payload["divisions"]


def test_rep_address_requires_street_or_address(client):
    response = client.get("/api/rep/address")

    assert response.status_code == 400
    assert "Provide either address=<full address>" in response.get_json()["error"]


def test_rep_address_lookup_builds_state_legislative_offices(client, monkeypatch):
    payload = {
        "result": {
            "addressMatches": [
                {
                    "matchedAddress": "1100 MASSACHUSETTS ST, LAWRENCE, KS, 66044",
                    "coordinates": {"x": -95.2353, "y": 38.9717},
                    "geographies": {
                        "Congressional Districts": [
                            {"STATE": "20", "CD118": "2", "BASENAME": "2"}
                        ],
                        "State Legislative Districts - Upper": [
                            {
                                "STATE": "20",
                                "SLDU": "002",
                                "NAME": "State Senate District 2",
                                "BASENAME": "2",
                            }
                        ],
                        "State Legislative Districts - Lower": [
                            {
                                "STATE": "20",
                                "SLDL": "046",
                                "NAME": "State House District 46",
                                "BASENAME": "46",
                            }
                        ],
                    },
                }
            ]
        }
    }

    def fake_get(url, params=None, timeout=None):
        assert url.endswith("/address")
        assert params["street"] == "1100 Massachusetts St"
        assert params["city"] == "Lawrence"
        assert params["state"] == "KS"
        return MockResponse(payload)

    monkeypatch.setattr("civiclookup.api.routes.requests.get", fake_get)

    response = client.get(
        "/api/rep/address?street=1100%20Massachusetts%20St&city=Lawrence&state=KS"
    )

    assert response.status_code == 200
    body = response.get_json()

    assert body["normalizedInput"]["zip"] == "66044"
    assert "message" not in body
    office_names = [office["name"] for office in body["offices"]]
    assert "Kansas State Senate" in office_names
    assert "Kansas State House" in office_names
    assert "ocd-division/country:us/state:ks/sldu:002" in body["divisions"]
    assert "ocd-division/country:us/state:ks/sldl:046" in body["divisions"]


def test_address_districts_returns_divisions_payload(client, monkeypatch):
    payload = {
        "result": {
            "addressMatches": [
                {
                    "matchedAddress": "1100 MASSACHUSETTS ST, LAWRENCE, KS, 66044",
                    "coordinates": {"x": -95.2353, "y": 38.9717},
                    "geographies": {
                        "Congressional Districts": [
                            {"STATE": "20", "CD118": "2", "BASENAME": "2"}
                        ]
                    },
                }
            ]
        }
    }

    monkeypatch.setattr(
        "civiclookup.api.routes.requests.get",
        lambda *args, **kwargs: MockResponse(payload),
    )

    response = client.get(
        "/api/address/districts?street=1100%20Massachusetts%20St&city=Lawrence&state=KS"
    )

    assert response.status_code == 200
    body = response.get_json()

    assert body["kind"] == "civicinfo#divisionsByAddressResponse"
    assert "message" not in body
    assert "ocd-division/country:us/state:ks/cd:2" in body["divisions"]


def test_v1_zip_lookup_returns_nested_native_shape(client):
    response = client.get("/v1/lookup/zip/22030")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["input"]["normalized"]["zip"] == "22030"
    assert payload["jurisdictions"]
    assert payload["offices"]
    assert "officials" in payload["offices"][0]
    assert "sources" in payload["metadata"]
    assert "ZIP-only lookup may be ambiguous" in " ".join(payload["metadata"]["warnings"])


def test_v1_zip_lookup_no_match_returns_warning(client):
    response = client.get("/v1/lookup/zip/00000")

    assert response.status_code == 404
    payload = response.get_json()
    assert payload["offices"] == []
    assert "No matching districts" in " ".join(payload["metadata"]["warnings"])


def test_v1_address_lookup_accepts_one_line_address(client, monkeypatch):
    lookup_result = routes.build_lookup_result(
        districts=[{"state": "VA", "district_number": 11, "district": "Virginia District 11"}],
        matched_address="123 MAIN ST, FAIRFAX, VA, 22030",
    )
    monkeypatch.setattr("civiclookup.api.routes.lookup_address_districts", lambda **kwargs: lookup_result)

    response = client.get("/v1/lookup/address?address=123%20Main%20St,%20Fairfax,%20VA")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["input"]["raw"] == "123 Main St, Fairfax, VA"
    assert payload["input"]["normalized"]["city"] == "FAIRFAX"
    assert payload["metadata"]["confidence"] == "exact_address_match"
    assert payload["offices"]


def test_v1_address_lookup_no_match_returns_warning(client, monkeypatch):
    monkeypatch.setattr(
        "civiclookup.api.routes.lookup_address_districts",
        lambda **kwargs: routes.build_lookup_result(),
    )

    response = client.get("/v1/lookup/address?street=123%20Main%20St&zip=00000")

    assert response.status_code == 404
    warnings = " ".join(response.get_json()["metadata"]["warnings"])
    assert "No matching districts" in warnings
    assert "US Census Geocoder returned no address match" in warnings


def test_v1_division_and_official_routes(client):
    division_id = "ocd-division/country:us/state:va/cd:11"

    division = client.get(f"/v1/divisions/{division_id}")
    officials = client.get(f"/v1/divisions/{division_id}/officials")

    assert division.status_code == 200
    assert division.get_json()["division"]["id"] == division_id
    assert officials.status_code == 200
    assert officials.get_json()["officials"]


def test_v1_official_route_uses_stable_id(client):
    lookup = client.get("/v1/lookup/zip/22030").get_json()
    official_id = lookup["offices"][0]["officials"][0]["id"]

    response = client.get(f"/v1/officials/{official_id}")

    assert response.status_code == 200
    assert response.get_json()["official"]["id"] == official_id


def test_v1_sources_status_returns_bundled_data_status(client):
    response = client.get("/v1/sources/status")

    assert response.status_code == 200
    payload = response.get_json()
    assert "generatedAt" in payload
    assert len(payload["sources"]) >= 3
    assert all(file_info["available"] for file_info in payload["files"])
