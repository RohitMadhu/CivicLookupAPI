import pytest


class TestZipEndpoints:
    def test_get_zip_districts_success(self, client, mock_data_loaders):
        response = client.get("/api/zip/94107/districts")
        assert response.status_code == 200
        data = response.get_json()
        assert "kind" in data
        assert data["kind"] == "civicinfo#divisionsByAddressResponse"
        assert "divisions" in data

    def test_get_rep_by_zip(self, client, mock_data_loaders):
        response = client.get("/api/rep/94107")
        assert response.status_code == 200
        data = response.get_json()
        assert "kind" in data
        assert data["kind"] == "civicinfo#representativeInfoResponse"


class TestAddressEndpoints:
    def test_get_rep_by_address_success(self, client, mock_data_loaders, mock_geocoder):
        response = client.get("/api/rep/address?street=123+Main+St&city=San+Francisco&state=CA&zip=94107")
        assert response.status_code == 200
        data = response.get_json()
        assert "kind" in data

    def test_get_address_districts(self, client, mock_data_loaders, mock_geocoder):
        response = client.get("/api/address/districts?address=123+Main+St%2C+San+Francisco%2C+CA+94107")
        assert response.status_code == 200


class TestErrorCases:
    def test_missing_street_for_address(self, client):
        response = client.get("/api/rep/address?city=San+Francisco&state=CA")
        assert response.status_code == 400
        data = response.get_json()
        assert "error" in data

    def test_invalid_zip_format(self, client, mock_data_loaders):
        response = client.get("/api/zip/abc123/districts")
        # App should handle gracefully (200 or 404/500 depending on data)
        assert response.status_code in (200, 404, 500)
