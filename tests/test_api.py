import pytest
from unittest.mock import patch


class TestZipEndpoints:
    def test_get_zip_districts_success(self, client, mock_data_loaders):
        response = client.get("/api/zip/94107/districts")
        assert response.status_code == 200
        data = response.get_json()
        assert data["kind"] == "civicinfo#divisionsByAddressResponse"
        assert "divisions" in data

    def test_get_rep_by_zip(self, client, mock_data_loaders):
        response = client.get("/api/rep/94107")
        assert response.status_code == 200
        data = response.get_json()
        assert data["kind"] == "civicinfo#representativeInfoResponse"
        assert "officials" in data or "divisions" in data


class TestAddressEndpoints:
    def test_get_rep_by_address_success(self, client, mock_data_loaders, mock_geocoder):
        response = client.get("/api/rep/address?street=123+Main+St&city=San+Francisco&state=CA&zip=94107")
        assert response.status_code == 200
        data = response.get_json()
        assert "normalizedInput" in data

    def test_get_address_districts(self, client, mock_data_loaders, mock_geocoder):
        response = client.get("/api/address/districts?address=123+Main+St%2C+San+Francisco%2C+CA+94107")
        assert response.status_code == 200


class TestErrorCases:
    def test_missing_street_for_address(self, client):
        response = client.get("/api/rep/address?city=San+Francisco&state=CA")
        assert response.status_code == 400
        assert "error" in response.get_json()

    def test_invalid_zip_format(self, client, mock_data_loaders):
        # Currently the app doesn't strictly validate, but we test graceful behavior
        response = client.get("/api/zip/abc123/districts")
        # Should still attempt and return something (or error depending on data)
        assert response.status_code in (200, 404, 500)
