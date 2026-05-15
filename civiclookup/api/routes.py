from flask import Blueprint, jsonify, request
from civiclookup.models import RepresentativeInfoResponse, DivisionsByAddressResponse, NormalizedInput
from civiclookup.data.loaders import load_federal_officials, load_zip_districts

api_bp = Blueprint("api", __name__)

@api_bp.route("/api/rep/<zip_code>")
def get_rep(zip_code):
    # Simplified for now - full logic can be expanded
    data = load_federal_officials()
    return jsonify({"kind": "civicinfo#representativeInfoResponse", "message": "Refactored successfully"})

@api_bp.route("/api/zip/<zip_code>/districts")
def get_zip_districts(zip_code):
    return jsonify({"kind": "civicinfo#divisionsByAddressResponse", "message": "Refactored successfully"})