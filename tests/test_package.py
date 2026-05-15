import pytest
from civiclookup.models import NormalizedInput, RepresentativeInfoResponse

def test_pydantic_models():
    data = NormalizedInput(line1="123 Main St", city="Anytown", state="CA", zip="12345")
    assert data.state == "CA"
    assert data.zip == "12345"

def test_response_model():
    resp = RepresentativeInfoResponse(
        normalizedInput=NormalizedInput(),
        divisions={"ocd-division/country:us": {"name": "United States"}}
    )
    assert resp.kind == "civicinfo#representativeInfoResponse"