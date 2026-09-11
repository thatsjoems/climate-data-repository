"""
Regression tests for Combined Climate-Financial Exposure data-quality honesty.

Found via external review: the original implementation queried ClimateRecord
by region + reconstructed year/months only, with no quality_flag filter at
all - meaning FLAGGED (explicitly rejected) readings, SYNTHETIC demo data,
and VALIDATED real readings could all be silently averaged together into one
number with no indication of what went into it. These tests lock in the fix:
FLAGGED is excluded outright, reporting_period is matched directly when
present, and the composition of what WAS used is always visible.
"""
from datetime import date
from app.models.models import RoleEnum, ClimateRecord
from app.services.analytics_service import get_combined_climate_financial_exposure
from tests.conftest import make_institution, make_user, login, auth_header
from tests.test_rbac_and_isolation import _seed_submission_for


def _add_climate_record(db, region="Dodoma", year=2026, month=2, reporting_period="2026-Q1",
                         quality_flag="VALIDATED", rainfall=50.0):
    rec = ClimateRecord(
        region=region, year=year, month=month, rainfall_mm=rainfall,
        avg_temperature_c=25.0, reporting_period=reporting_period, quality_flag=quality_flag,
    )
    db.add(rec)
    db.commit()
    return rec


def test_flagged_climate_records_are_excluded_from_combined_exposure(client, db_session):
    inst = make_institution(db_session)
    _seed_submission_for(db_session, inst)  # region=Dodoma, reporting_period=2026-Q1

    # A FLAGGED (explicitly rejected) reading with an extreme, obviously-bad
    # value - if it leaked into the average, it would be easy to spot.
    _add_climate_record(db_session, quality_flag="FLAGGED", rainfall=9999.0)
    _add_climate_record(db_session, quality_flag="VALIDATED", rainfall=50.0)

    results = get_combined_climate_financial_exposure(db_session)
    row = next(r for r in results if r["region"] == "Dodoma")
    assert row["avg_rainfall_mm"] == 50.0  # the FLAGGED 9999.0 must not affect this
    assert row["climate_data_quality"] == "VALIDATED"


def test_quality_composition_is_reported_when_mixed(client, db_session):
    inst = make_institution(db_session)
    _seed_submission_for(db_session, inst)

    _add_climate_record(db_session, quality_flag="SYNTHETIC", rainfall=40.0)
    _add_climate_record(db_session, quality_flag="UNVALIDATED", rainfall=60.0)

    results = get_combined_climate_financial_exposure(db_session)
    row = next(r for r in results if r["region"] == "Dodoma")
    assert row["climate_data_quality"] is not None
    assert row["climate_data_quality"] != "VALIDATED"
    assert "SYNTHETIC" in row["climate_data_quality"]
    assert "UNVALIDATED" in row["climate_data_quality"]


def test_reporting_period_is_matched_directly_when_present(client, db_session):
    """
    A record tagged with the WRONG reporting_period but matching year/month
    must NOT be picked up once a direct reporting_period match is possible -
    the direct tag is authoritative.
    """
    inst = make_institution(db_session)
    _seed_submission_for(db_session, inst)  # reporting_period=2026-Q1 (Jan-Mar)

    # Same region/year/month as Q1, but explicitly tagged as a DIFFERENT
    # quarter (e.g. a late-arriving correction relabelled by TMA).
    _add_climate_record(db_session, month=2, reporting_period="2026-Q2", quality_flag="VALIDATED", rainfall=999.0)
    # The one that actually IS Q1.
    _add_climate_record(db_session, month=2, reporting_period="2026-Q1", quality_flag="VALIDATED", rainfall=30.0)

    results = get_combined_climate_financial_exposure(db_session)
    row = next(r for r in results if r["region"] == "Dodoma")
    assert row["avg_rainfall_mm"] == 30.0


def test_legacy_records_without_reporting_period_still_match_via_year_month(client, db_session):
    """Backward compatibility: older/ingested rows with no reporting_period set must still be found."""
    inst = make_institution(db_session)
    _seed_submission_for(db_session, inst)  # 2026-Q1 = Jan/Feb/Mar

    rec = ClimateRecord(region="Dodoma", year=2026, month=2, rainfall_mm=77.0,
                         avg_temperature_c=24.0, reporting_period=None, quality_flag="VALIDATED")
    db_session.add(rec)
    db_session.commit()

    results = get_combined_climate_financial_exposure(db_session)
    row = next(r for r in results if r["region"] == "Dodoma")
    assert row["avg_rainfall_mm"] == 77.0


def test_no_climate_data_reports_null_quality_not_a_fabricated_default(client, db_session):
    inst = make_institution(db_session)
    _seed_submission_for(db_session, inst, region="Mbeya")  # no climate records seeded for Mbeya

    results = get_combined_climate_financial_exposure(db_session)
    row = next(r for r in results if r["region"] == "Mbeya")
    assert row["avg_rainfall_mm"] is None
    assert row["climate_data_quality"] is None
