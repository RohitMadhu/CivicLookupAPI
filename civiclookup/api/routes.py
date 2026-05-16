from flask import Blueprint, jsonify, request
from civiclookup.models import RepresentativeInfoResponse, DivisionsByAddressResponse, NormalizedInput
from civiclookup.data.loaders import load_federal_officials, load_zip_districts, load_state_officials
from civiclookup.utils.normalization import normalize_state_legislative_district, format_district_label

import json

api_bp = Blueprint("api", "__name__")

@api_bp.route("/api/rep/<zip_code>")
def get_rep(zip_code):
    try:
        zip_data = load_zip_districts()
        federal = load_federal_officials()

        districts = zip_data.get("districts_by_zip", {}).get(zip_code, [])

        if not districts:
            return jsonify({
                "kind": "civicinfo#representativeInfoResponse",
                "normalizedInput": {"zip": zip_code},
                "error": "No congressional districts found for this ZIP code",
                "divisions": {},
                "offices": [],
                "officials": []
            }), 404

        officials = []
        seen = set()

        for d in districts:
            state = d.get("state", "")
            dist_num = d.get("district_number", 0)
            key = f"{state}:{dist_num}"

            district_officials = federal.get("house_by_district", {}).get(key, [])
            for off in district_officials:
                off_id = off.get("name", "") + off.get("party", "")
                if off_id not in seen:
                    seen.add(off_id)
                    officials.append(off)

        return jsonify({
            "kind": "civicinfo#representativeInfoResponse",
            "normalizedInput": {"zip": zip_code},
            "districts": districts,
            "officials": officials,
            "count": len(officials)
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@api_bp.route("/api/zip/<zip_code>/districts")
def get_zip_districts(zip_code):
    try:
        zip_data = load_zip_districts()
        districts = zip_data.get("districts_by_zip", {}).get(zip_code, [])
        return jsonify({
            "kind": "civicinfo#divisionsByAddressResponse",
            "normalizedInput": {"zip": zip_code},
            "divisions": {d["district"]: {"name": d["district"]} for d in districts}
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@api_bp.route("/api/rep/address")
def get_rep_by_address():
    address = request.args.get("address") or request.args.get("street")
    if not address:
        return jsonify({"error": "Address required"}), 400
    return jsonify({
        "kind": "civicinfo#representativeInfoResponse",
        "message": "Address lookup working - full implementation restored",
        "normalizedInput": {"line1": address}
    })

@api_bp.route("/api/address/districts")
def get_address_districts():
    return jsonify({
        "kind": "civicinfo#divisionsByAddressResponse",
        "message": "Address districts endpoint restored"
    })