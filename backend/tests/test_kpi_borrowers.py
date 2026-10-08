"""
The summary figures count each borrower ONCE however many loans, institutions and files they appear in, and add up the loans and collateral of the
current approved submissions only. The way the figures are computed was changed (one pass for the totals and a DISTINCT list for the borrowers instead of
count(distinct ...): found by a load test, docs/LOAD_TESTING.md), so the meaning is pinned down here with a case that has every awkward part:
one borrower with several loans, one borrower shared by two institutions, and a submission that is not approved and must not count.
"""
from app.models.models import RoleEnum
from tests.conftest import auth_header, login, make_user
from tests.test_upload_and_workflow import VALID_ROW, _setup_institution_user, _upload

LOAN, COLLATERAL = VALID_ROW["loan_amount_tzs"], VALID_ROW["collateral_value_tzs"]


def _file(pairs):
    return [dict(VALID_ROW, customer_id=customer, loan_id=loan) for customer, loan in pairs]


def _approved_upload(client, db_session, username, code, pairs, reviewer_token):
    _setup_institution_user(db_session, username=username, institution_code=code)
    token = login(client, username).json()["access_token"]
    submission = _upload(client, token, _file(pairs)).json()
    assert submission["status"] == "VALID"
    assert client.post(f"/api/submissions/{submission['id']}/review", json={"decision": "APPROVE"}, headers=auth_header(reviewer_token)).status_code == 200
    return token


def _kpi(client, token):
    return client.get("/api/analytics/kpi-summary", headers=auth_header(token)).json()


def test_borrowers_are_counted_once_across_loans_and_institutions(client, db_session):
    make_user(db_session, role=RoleEnum.BOT_USER, username="kpi_reviewer")
    reviewer = login(client, "kpi_reviewer").json()["access_token"]
    a = _approved_upload(client, db_session, "kpi_a", "KPI-A", [("C1", "L1"), ("C1", "L2"), ("C2", "L3")], reviewer)    # C1 has two loans
    b = _approved_upload(client, db_session, "kpi_b", "KPI-B", [("C2", "L1"), ("C3", "L2")], reviewer)                  # C2 is also a customer of the first bank

    sector = _kpi(client, reviewer)
    assert sector["total_borrowers"] == 3                                    # C1, C2, C3: C2 once although two banks lend to them
    assert sector["total_loan_exposure_tzs"] == 5 * LOAN and sector["total_collateral_value_tzs"] == 5 * COLLATERAL
    assert _kpi(client, a)["total_borrowers"] == 2 and _kpi(client, a)["total_loan_exposure_tzs"] == 3 * LOAN
    assert _kpi(client, b)["total_borrowers"] == 2 and _kpi(client, b)["total_loan_exposure_tzs"] == 2 * LOAN


def test_a_submission_that_is_not_approved_adds_nothing(client, db_session):
    make_user(db_session, role=RoleEnum.BOT_USER, username="kpi_reviewer2")
    reviewer = login(client, "kpi_reviewer2").json()["access_token"]
    _approved_upload(client, db_session, "kpi_c", "KPI-C", [("C1", "L1")], reviewer)
    _setup_institution_user(db_session, username="kpi_d", institution_code="KPI-D")
    pending = login(client, "kpi_d").json()["access_token"]
    assert _upload(client, pending, _file([("C9", "L1"), ("C8", "L2")])).json()["status"] == "VALID"      # uploaded, not approved
    sector = _kpi(client, reviewer)
    assert sector["total_borrowers"] == 1 and sector["total_loan_exposure_tzs"] == LOAN


def test_no_approved_data_gives_zeros_not_errors(client, db_session):
    make_user(db_session, role=RoleEnum.BOT_USER, username="kpi_reviewer3")
    reviewer = login(client, "kpi_reviewer3").json()["access_token"]
    kpi = _kpi(client, reviewer)
    assert kpi["total_borrowers"] == 0 and kpi["total_loan_exposure_tzs"] == 0 and kpi["total_collateral_value_tzs"] == 0
