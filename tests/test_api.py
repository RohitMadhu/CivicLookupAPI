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
