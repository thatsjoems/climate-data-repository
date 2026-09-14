"""
Tests for app.services.geo_lookup - the Region/District/Ward/Village
reference data (2022 Census village list + Zanzibar Frame).
"""
from app.services import geo_lookup as geo


def test_all_names_are_whitespace_normalized():
    """
    Regression test: the source files contain a small number of names with
    stray leading/trailing whitespace (e.g. a ward literally stored as
    "Kwa Mchina " in the Zanzibar Frame). Since uploaded Excel values are
    stripped during validation, the reference data must be stripped
    identically at load time - otherwise a technically-correct name fails
    validation purely because of invisible whitespace. Found via a 15,000-row
    generated test file that produced exactly this false-positive warning.
    """
    data = geo._load()
    for region, districts in data.items():
        assert region == region.strip(), f"Region {region!r} has stray whitespace"
        for district, wards in districts.items():
            assert district == district.strip(), f"District {district!r} has stray whitespace"
            for ward, villages in wards.items():
                assert ward == ward.strip(), f"Ward {ward!r} has stray whitespace"
                for v in villages:
                    assert v == v.strip(), f"Village {v!r} has stray whitespace"


def test_kwa_mchina_ward_matches_after_normalization():
    """The specific case that surfaced this bug: a ward stored with a trailing space."""
    wards = geo.wards_for_district("Mjini Magharibi", "Magharibi B")
    assert "Kwa Mchina" in wards
    assert geo.is_valid_ward("Mjini Magharibi", "Magharibi B", "Kwa Mchina")


def test_region_district_ward_village_counts_are_stable():
    """Sanity check on the overall dataset shape, so a future data-file swap is caught if it changes drastically."""
    regions = geo.all_regions()
    assert len(regions) == 31
    total_districts = sum(len(geo.districts_for_region(r)) for r in regions)
    assert total_districts == 151
