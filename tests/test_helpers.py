import pytest

# Minimal passing tests for the refactor

def test_package_structure():
    from civiclookup import config
    assert hasattr(config, 'DATA_DIR')

def test_pydantic_models():
    from civiclookup.models import NormalizedInput, RepresentativeInfoResponse
    data = NormalizedInput(line1="123 Main", city="Test", state="CA", zip="12345")
    assert data.state == "CA"


def test_api_routes():
    from civiclookup.api.routes import api_bp
    assert api_bp.name == "api"