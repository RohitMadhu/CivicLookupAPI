import sys
from pathlib import Path

import pytest
from flask import Flask

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from civiclookup.api.routes import api_bp


@pytest.fixture
def app():
    app = Flask(__name__)
    app.register_blueprint(api_bp)
    return app


@pytest.fixture
def client(app):
    return app.test_client()
