"""
Climate Data - Hazard Summary (Concept Note, Figure 3): GET /analytics/hazard-summary.

It describes where ONE hazard was recorded and how severe, from climate readings only. Nothing is estimated: a district
with no reading of the hazard is absent, and readings recorded for a region only are counted but cannot be placed in a
district. It never looks at loans, so it works with no institution data at all.
"""
import itertools

import pytest

from app.models.models import ClimateRecord, RoleEnum
from tests.conftest import auth_header, login, make_user

_ids = itertools.count(1)


def _reading(db, region, district, hazard="Drought", severity="HIGH", flag="VALIDATED", period="2026-Q2", **extra):
    fields = dict(
        region=region, district=district, year=2026, month=5, rainfall_mm=20.0, avg_temperature_c=28.0,
        hazard_type=hazard, hazard_severity=severity, reporting_period=period, quality_flag=flag,
        source_record_id=f"R-{next(_ids)}",
    )
    fields.update(extra)
    db.add(ClimateRecord(**fields))
    db.commit()


def _bot(db):
    make_user(db, role=RoleEnum.BOT_USER, username="bot1")


def _get(client, username, query):
    token = login(client, username).json()["access_token"]
    return client.get("/api/analytics/hazard-summary" + query, headers=auth_header(token))


def test_districts_are_listed_worst_first_with_their_counts(client, db_session):
    _bot(db_session)
    _reading(db_session, "Dodoma", "Bahi", severity="MEDIUM")
    _reading(db_session, "Dodoma", "Bahi", severity="HIGH")          # the worst reading of the district counts
    _reading(db_session, "Dodoma", "Chamwino", severity="LOW")
    _reading(db_session, "Singida", "Manyoni", severity="HIGH")
    _reading(db_session, "Singida", "Ikungi", severity=None)         # recorded, but not graded
    body = _get(client, "bot1", "?filter_hazard_type=Drought").json()
    assert body["districts_affected"] == 4
    assert body["regions_affected"] == 2
    assert body["readings"] == 5
    assert body["highest_severity"] == "HIGH"
    assert body["districts_by_severity"] == {"HIGH": 2, "MEDIUM": 0, "LOW": 1, "NOT_GRADED": 1}
    # Worst first; equal severity: more readings first, then alphabetical.
    assert [(d["district"], d["highest_severity"], d["readings"]) for d in body["districts"]] == [
        ("Bahi", "HIGH", 2), ("Manyoni", "HIGH", 1), ("Chamwino", "LOW", 1), ("Ikungi", None, 1),
    ]


def test_only_the_chosen_hazard_counts(client, db_session):
    _bot(db_session)
    _reading(db_session, "Dodoma", "Bahi", hazard="Drought")
    _reading(db_session, "Mwanza", "Ilemela", hazard="Flood")
    drought = _get(client, "bot1", "?filter_hazard_type=Drought").json()
    flood = _get(client, "bot1", "?filter_hazard_type=Flood").json()
    assert [d["district"] for d in drought["districts"]] == ["Bahi"]
    assert [d["district"] for d in flood["districts"]] == ["Ilemela"]
    assert _get(client, "bot1", "?filter_hazard_type=Cyclone").json()["districts"] == []


def test_period_and_region_narrow_the_summary(client, db_session):
    _bot(db_session)
    _reading(db_session, "Dodoma", "Bahi", period="2026-Q2")
    _reading(db_session, "Dodoma", "Chamwino", period="2026-Q1", month=2)
    _reading(db_session, "Mwanza", "Ilemela", period="2026-Q2")
    q2 = _get(client, "bot1", "?filter_hazard_type=Drought&filter_reporting_period=2026-Q2").json()
    assert {d["district"] for d in q2["districts"]} == {"Bahi", "Ilemela"}
    one = _get(client, "bot1", "?filter_hazard_type=Drought&filter_reporting_period=2026-Q2&filter_region=Dodoma").json()
    assert [d["district"] for d in one["districts"]] == ["Bahi"]
    assert one["reporting_period"] == "2026-Q2" and one["region"] == "Dodoma"


def test_an_older_reading_without_a_period_is_found_by_its_year_and_month(client, db_session):
    _bot(db_session)
    _reading(db_session, "Dodoma", "Bahi", period=None, month=5)      # April-June 2026 = 2026-Q2
    _reading(db_session, "Dodoma", "Chamwino", period=None, month=8)  # July-September
    body = _get(client, "bot1", "?filter_hazard_type=Drought&filter_reporting_period=2026-Q2").json()
    assert [d["district"] for d in body["districts"]] == ["Bahi"]


def test_by_default_only_validated_readings_count_and_flagged_ones_never(client, db_session):
    _bot(db_session)
    _reading(db_session, "Dodoma", "Bahi", flag="VALIDATED")
    _reading(db_session, "Dodoma", "Chamwino", flag="UNVALIDATED")
    _reading(db_session, "Dodoma", "Kondoa", flag="FLAGGED")
    default = _get(client, "bot1", "?filter_hazard_type=Drought").json()
    assert [d["district"] for d in default["districts"]] == ["Bahi"]
    assert default["validated_only"] is True
    wider = _get(client, "bot1", "?filter_hazard_type=Drought&validated_only=false").json()
    assert {d["district"] for d in wider["districts"]} == {"Bahi", "Chamwino"}      # never the flagged one
    assert wider["validated_only"] is False


def test_a_reading_for_a_region_only_is_counted_but_not_placed_in_a_district(client, db_session):
    _bot(db_session)
    _reading(db_session, "Dodoma", None)
    _reading(db_session, "Dodoma", "  ")
    _reading(db_session, "Dodoma", "Bahi")
    body = _get(client, "bot1", "?filter_hazard_type=Drought").json()
    assert body["readings"] == 3
    assert body["readings_without_district"] == 2
    assert body["districts_affected"] == 1
    assert body["regions_affected"] == 1


def test_no_readings_gives_zeros_and_empty_lists_not_an_error(client, db_session):
    _bot(db_session)
    body = _get(client, "bot1", "?filter_hazard_type=Drought").json()
    assert body["districts_affected"] == 0 and body["regions_affected"] == 0 and body["readings"] == 0
    assert body["highest_severity"] is None
    assert body["districts"] == [] and body["available_periods"] == [] and body["available_regions"] == []
    assert body["districts_by_severity"] == {"HIGH": 0, "MEDIUM": 0, "LOW": 0, "NOT_GRADED": 0}


def test_the_pickers_offer_the_periods_and_regions_that_have_readings(client, db_session):
    _bot(db_session)
    _reading(db_session, "Dodoma", "Bahi", period="2026-Q1", month=2)
    _reading(db_session, "Mwanza", "Ilemela", hazard="Flood", period="2026-Q2")
    _reading(db_session, "Arusha", "Meru", period="2026-Q3", month=8, flag="FLAGGED")   # flagged: never offered
    body = _get(client, "bot1", "?filter_hazard_type=Drought&filter_region=Dodoma").json()
    # Whatever is chosen, the pickers still list everything that has readings of that quality.
    assert body["available_periods"] == ["2026-Q2", "2026-Q1"]
    assert body["available_regions"] == ["Dodoma", "Mwanza"]


@pytest.mark.parametrize("query", [
    "",                                                  # the hazard is required
    "?filter_hazard_type=None",                          # a hazard that was not recorded has no summary
    "?filter_hazard_type=Earthquake",
    "?filter_hazard_type=Drought&filter_reporting_period=2026",
    "?filter_hazard_type=Drought&filter_reporting_period=2026-Q5",
])
def test_unknown_or_missing_parameters_are_refused(client, db_session, query):
    _bot(db_session)
    assert _get(client, "bot1", query).status_code == 422


def test_only_a_bot_analyst_may_read_it(client, db_session):
    _bot(db_session)
    make_user(db_session, role=RoleEnum.SYSTEM_ADMIN, username="admin1")
    make_user(db_session, role=RoleEnum.INSTITUTION_USER, username="inst1")
    assert _get(client, "bot1", "?filter_hazard_type=Drought").status_code == 200
    assert _get(client, "admin1", "?filter_hazard_type=Drought").status_code == 403
    assert _get(client, "inst1", "?filter_hazard_type=Drought").status_code == 403
    assert client.get("/api/analytics/hazard-summary?filter_hazard_type=Drought").status_code in (401, 403)
