import pytest
from app import (
    normalize_district,
    format_district_label,
    normalize_state_legislative_district,
    strip_state_legislative_label,
    jurisdiction_ocd_id,
    district_ocd_id,
    slugify_division_key,
)


class TestNormalizeDistrict:
    def test_normal_cases(self):
        assert normalize_district(5) == 5
        assert normalize_district("12") == 12
        assert normalize_district(98) == 0  # Special at-large case

    def test_invalid(self):
        assert normalize_district(None) is None
        assert normalize_district("abc") is None
        assert normalize_district("") is None


class TestFormatDistrictLabel:
    def test_regular_district(self):
        assert format_district_label("CA", 12) == "California District 12"

    def test_at_large(self):
        assert format_district_label("WY", 0) == "Wyoming At Large"

    def test_unknown_state(self):
        assert format_district_label("XX", 5) == "XX District 5"


class TestStateLegislativeNormalization:
    def test_prefix_removal(self):
        assert normalize_state_legislative_district("State Senate District 5") == "5"
        assert normalize_state_legislative_district("State House District 42") == "42"

    def test_suffix_removal(self):
        assert normalize_state_legislative_district("State Senate District 3") == "3"
        assert normalize_state_legislative_district("State House District 7") == "7"

    def test_empty(self):
        assert normalize_state_legislative_district(None) == ""
        assert normalize_state_legislative_district("") == ""


class TestOCDIDs:
    def test_jurisdiction(self):
        assert jurisdiction_ocd_id("CA") == "ocd-division/country:us/state:ca"
        assert jurisdiction_ocd_id("DC") == "ocd-division/country:us/district:dc"

    def test_district_ocd(self):
        district = {"state": "CA", "district_number": 12}
        assert district_ocd_id(district) == "ocd-division/country:us/state:ca/cd:12"


class TestSlugify:
    def test_basic(self):
        assert slugify_division_key("State Senate District 5") == "state_senate_district_5"
        assert slugify_division_key("  Weird   Name! ") == "weird_name"
