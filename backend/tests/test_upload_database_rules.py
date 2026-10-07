"""
Upload rules that mirror database constraints.

The database rejects a negative amount, an interest rate outside 0-100, an impossible
coordinate, and (since migration f4a9c2d71b05) an outstanding principal above the loan
amount. A constraint failure rejects the WHOLE INSERT, so before these rules existed in the
validator an upload carrying such a value did not produce a visible row error for the
reviewer - it failed with an unexplained HTTP 409 (or, for outstanding > loan on a real
database that lacked the constraint, was accepted as VALID).

These tests pin the intended behaviour: the upload is stored (201), the offending row is
INVALID, and the value the database would have rejected is reported but not stored.
"""
import pytest

from app.models.models import SubmissionRecord
from tests.conftest import login
from tests.test_upload_and_workflow import VALID_ROW, _setup_institution_user, _upload


def _upload_as_institution_user(client, db_session, rows):
    _setup_institution_user(db_session)
    token = login(client, "inst_user").json()["access_token"]
    return _upload(client, token, rows)


FLAGGED_CASES = [
    pytest.param(dict(outstanding_principal_tzs=9_000_000), id="outstanding-above-loan"),
    pytest.param(dict(loan_amount_tzs=-5), id="negative-loan-amount"),
    pytest.param(dict(insurance_value_protected_tzs=-1), id="negative-optional-amount"),
    pytest.param(dict(annual_turnover_tzs=-100), id="negative-turnover"),
    pytest.param(dict(annual_interest_rate=150), id="interest-rate-above-100"),
    pytest.param(dict(annual_interest_rate=-2), id="interest-rate-negative"),
    pytest.param(dict(loan_latitude=200, loan_longitude=35.7), id="latitude-out-of-range"),
    pytest.param(dict(loan_latitude=-6.2, loan_longitude=500), id="longitude-out-of-range"),
    pytest.param(dict(loan_amount_tzs=1e30), id="amount-too-large-for-the-column"),
]


@pytest.mark.parametrize("override", FLAGGED_CASES)
def test_a_value_the_database_would_reject_is_flagged_not_a_409(client, db_session, override):
    res = _upload_as_institution_user(client, db_session, [dict(VALID_ROW, **override)])
    assert res.status_code == 201, res.text
    assert res.json()["status"] == "INVALID"
    assert res.json()["invalid_records"] == 1


def test_outstanding_principal_equal_to_the_loan_amount_is_accepted(client, db_session):
    res = _upload_as_institution_user(client, db_session, [dict(VALID_ROW, outstanding_principal_tzs=5_000_000)])
    assert res.status_code == 201, res.text
    assert res.json()["status"] == "VALID"


def test_a_large_but_representable_amount_is_accepted(client, db_session):
    res = _upload_as_institution_user(
        client, db_session, [dict(VALID_ROW, loan_amount_tzs=5e17, collateral_value_tzs=8e17)]
    )
    assert res.status_code == 201, res.text
    assert res.json()["status"] == "VALID"


def test_flagged_values_are_not_stored_but_the_rest_of_the_row_is(client, db_session):
    _upload_as_institution_user(
        client, db_session,
        [dict(VALID_ROW, outstanding_principal_tzs=9_000_000, annual_interest_rate=150)],
    )
    record = db_session.query(SubmissionRecord).filter(SubmissionRecord.loan_id == "LN-1").one()
    assert record.is_valid is False
    assert record.outstanding_principal_tzs is None
    assert record.annual_interest_rate is None
    assert record.loan_amount_tzs is not None  # the rest of the row is kept for the reviewer (FR-SUB-07)
