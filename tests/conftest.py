import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path
import json

# Import the Flask app
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from app import app as flask_app, load_federal_officials, load_zip_districts, load_state_officials


@pytest.fixture
def client():
    """Flask test client fixture."""
    flask_app.config['TESTING'] = True
    with flask_app.test_client() as client:
        yield client


@pytest.fixture
def mock_data_loaders():
    """Mock the data loading functions so tests don't depend on real JSON files."""
    with patch('app.load_federal_officials') as mock_fed, \
         patch('app.load_zip_districts') as mock_zip, \
         patch('app.load_state_officials') as mock_state:
        
        # Minimal realistic mock data
        mock_fed.return_value = {
            "house_by_district": {
                "CA:12": [{"name": "Test Rep", "party": "Democrat", "bioguide_id": "T000001"}]
            },
            "senate_by_state": {
                "CA": [
                    {"name": "Sen. Feinstein", "party": "Democrat", "bioguide_id": "F000062"},
                    {"name": "Sen. Padilla", "party": "Democrat", "bioguide_id": "P000145"}
                ]
            }
        }
        
        mock_zip.return_value = {
            "districts_by_zip": {
                "94107": [{"state": "CA", "district_number": 12, "district": "California District 12"}]
            }
        }
        
        mock_state.return_value = {
            "state_upper_by_district": {},
            "state_lower_by_district": {},
            "state_legislature_by_district": {},
            "statewide_executives_by_state": {}
        }
        
        yield


@pytest.fixture
def mock_geocoder():
    """Mock the Census Geocoder HTTP call."""
    with patch('app.requests.get') as mock_get:
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "result": {
                "addressMatches": [{
                    "matchedAddress": "123 Main St, San Francisco, CA 94107",
                    "geographies": {
                        "Congressional Districts": [{
                            "STATE": "06",
                            "CD118": "12",
                            "BASENAME": "12"
                        }]
                    },
                    "coordinates": {"x": -122.4, "y": 37.77}
                }]
            }
        }
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response
        yield mock_get
