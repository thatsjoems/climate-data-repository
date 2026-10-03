"""
Tests that the CHECK constraints declared in models.py actually reject bad
data - not just that they're syntactically declared.

This complements, but does not replace, scripts/verify_db_constraints.py:
that script checks whether the REAL deployed PostgreSQL database has these
constraints (the thing that was silently missing until caught via `\\d
climate_records` on a live database - see the ninth review in
ICN_REQUIREMENTS_TRACEABILITY_MATRIX.md). This file checks the constraint
CONDITIONS themselves are logically correct, using the test suite's
existing isolated SQLite database (created fresh via Base.metadata.create_all,
which is not the code path that missed them on a real deployment).
Both are needed: this test passing has never been enough on its own to
prove the real database is protected.
"""
import pytest
from sqlalchemy.exc import IntegrityError

from app.models.models import ClimateRecord, Submission
from tests.conftest import make_institution, make_user


def test_negative_rainfall_is_rejected(db_session):
    rec = ClimateRecord(region="Dodoma", year=2026, rainfall_mm=-5.0, quality_flag="UNVALIDATED")
    db_session.add(rec)
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_valid_rainfall_is_accepted(db_session):
    rec = ClimateRecord(region="Dodoma", year=2026, rainfall_mm=120.5, quality_flag="UNVALIDATED")
    db_session.add(rec)
    db_session.commit()  # must not raise
    assert rec.id is not None


def test_out_of_range_latitude_is_rejected(db_session):
    rec = ClimateRecord(region="Dodoma", year=2026, latitude=200.0, quality_flag="UNVALIDATED")
    db_session.add(rec)
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_invalid_quality_flag_is_rejected(db_session):
    rec = ClimateRecord(region="Dodoma", year=2026, quality_flag="NOT_A_REAL_FLAG")
    db_session.add(rec)
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_temperature_min_greater_than_max_is_rejected(db_session):
    rec = ClimateRecord(
        region="Dodoma", year=2026, quality_flag="UNVALIDATED",
        temperature_min_c=30.0, temperature_max_c=20.0,  # min > max: physically impossible
    )
    db_session.add(rec)
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_malformed_reporting_period_is_rejected(db_session):
    # This exact constraint had an off-by-one bug that rejected every
    # value, including valid ones - see the eighth review's fix. This
    # test guards the fixed version: "2026-Q3" (7 chars, valid quarter)
    # must be ACCEPTED, and a malformed one must still be REJECTED.
    inst = make_institution(db_session)
    user = make_user(db_session, institution=inst)
    good = Submission(
        institution_id=inst.id, submitted_by_user_id=user.id,
        reporting_period="2026-Q3", file_name="f.xlsx", file_path="/tmp/f.xlsx",
    )
    db_session.add(good)
    db_session.commit()  # must not raise - this is exactly the case the old bug broke

    bad = Submission(
        institution_id=inst.id, submitted_by_user_id=user.id,
        reporting_period="2026-Q5", file_name="f2.xlsx", file_path="/tmp/f2.xlsx",
    )
    db_session.add(bad)
    with pytest.raises(IntegrityError):
        db_session.commit()
