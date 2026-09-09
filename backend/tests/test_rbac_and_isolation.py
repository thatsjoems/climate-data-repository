"""
RBAC and tenant-isolation tests.

MOST IMPORTANT ACCEPTANCE CRITERION covered here: Institution A must never be
able to see Institution B's data through any endpoint, and a client-supplied
institution_id must never override server-side authorization.
"""
from app.models.models import RoleEnum, Submission, SubmissionRecord, SubmissionStatus
from tests.conftest import make_institution, make_user, login, auth_header


def test_institution_user_cannot_create_institution(client, db_session):
    inst = make_institution(db_session)
    make_user(db_session, role=RoleEnum.INSTITUTION_USER, institution=inst, username="bank_a_user")
    token = login(client, "bank_a_user").json()["access_token"]

    res = client.post(
        "/api/institutions",
        json={"code": "NEW-1", "name": "New Bank", "type": "BANK"},
        headers=auth_header(token),
    )
    assert res.status_code == 403


def test_institution_user_cannot_create_user(client, db_session):
    inst = make_institution(db_session)
    make_user(db_session, role=RoleEnum.INSTITUTION_USER, institution=inst, username="bank_a_user")
    token = login(client, "bank_a_user").json()["access_token"]

    res = client.post(
        "/api/users",
        json={
            "full_name": "New Person", "username": "newperson", "email": "n@example.com",
            "password": "Passw0rd!23", "role": "INSTITUTION_USER",
        },
        headers=auth_header(token),
    )
    assert res.status_code == 403


def test_bot_user_cannot_view_password_reset_requests(client, db_session):
    """Only SYSTEM_ADMIN handles account/administration matters - BOT_USER is a data reviewer, not IT/security."""
    make_user(db_session, role=RoleEnum.BOT_USER, username="analyst1")
    token = login(client, "analyst1").json()["access_token"]

    res = client.get("/api/password-reset-requests", headers=auth_header(token))
    assert res.status_code == 403


def _seed_submission_for(db_session, institution, region="Dodoma", district="Chamwino District", amount=1_000_000.0):
    submitter = make_user(db_session, role=RoleEnum.INSTITUTION_USER, institution=institution,
                           username=f"submitter_{institution.code}")
    submission = Submission(
        institution_id=institution.id,
        submitted_by_user_id=submitter.id,
        file_name="test.xlsx",
        file_path="uploads/test.xlsx",
        reporting_period="2026-Q1",
        status=SubmissionStatus.VALID,
        total_records=1, valid_records=1, invalid_records=0,
    )
    db_session.add(submission)
    db_session.flush()
    db_session.add(SubmissionRecord(
        submission_id=submission.id, row_number=2, loan_id=f"LN-{institution.code}",
        borrower_name="Borrower", loan_amount_tzs=amount, collateral_value_tzs=amount,
        region=region, district=district, is_valid=True,
    ))
    db_session.commit()
    return submission


def test_institution_user_cannot_see_other_institutions_submissions(client, db_session):
    inst_a = make_institution(db_session, code="BANK-A", name="Bank A")
    inst_b = make_institution(db_session, code="BANK-B", name="Bank B")
    _seed_submission_for(db_session, inst_a)
    _seed_submission_for(db_session, inst_b)

    viewer = make_user(db_session, role=RoleEnum.INSTITUTION_USER, institution=inst_a, username="viewer_a")
    token = login(client, "viewer_a").json()["access_token"]

    res = client.get("/api/submissions", headers=auth_header(token))
    assert res.status_code == 200
    institution_ids_seen = {s["institution_id"] for s in res.json()}
    assert institution_ids_seen == {inst_a.id}


def test_institution_user_cannot_fetch_another_institutions_submission_by_id(client, db_session):
    inst_a = make_institution(db_session, code="BANK-A", name="Bank A")
    inst_b = make_institution(db_session, code="BANK-B", name="Bank B")
    submission_b = _seed_submission_for(db_session, inst_b)

    make_user(db_session, role=RoleEnum.INSTITUTION_USER, institution=inst_a, username="viewer_a")
    token = login(client, "viewer_a").json()["access_token"]

    res = client.get(f"/api/submissions/{submission_b.id}", headers=auth_header(token))
    assert res.status_code == 403


def test_institution_user_kpi_summary_scoped_to_own_institution_only(client, db_session):
    """
    The core acceptance criterion: an INSTITUTION_USER's KPI totals must reflect
    ONLY their own institution's exposure, never the sector-wide aggregate.
    """
    inst_a = make_institution(db_session, code="BANK-A", name="Bank A")
    inst_b = make_institution(db_session, code="BANK-B", name="Bank B")
    _seed_submission_for(db_session, inst_a, amount=1_000_000.0)
    _seed_submission_for(db_session, inst_b, amount=9_000_000.0)

    make_user(db_session, role=RoleEnum.INSTITUTION_USER, institution=inst_a, username="viewer_a")
    token = login(client, "viewer_a").json()["access_token"]

    res = client.get("/api/analytics/kpi-summary", headers=auth_header(token))
    assert res.status_code == 200
    body = res.json()
    assert body["total_loan_exposure_tzs"] == 1_000_000.0  # Bank A's own exposure only
    assert body["total_submissions"] == 1                  # not the sector-wide count of 2


def test_bot_user_sees_sector_wide_kpi_totals(client, db_session):
    """BOT_USER (Analyst) retains full supervisory visibility across all institutions."""
    inst_a = make_institution(db_session, code="BANK-A", name="Bank A")
    inst_b = make_institution(db_session, code="BANK-B", name="Bank B")
    _seed_submission_for(db_session, inst_a, amount=1_000_000.0)
    _seed_submission_for(db_session, inst_b, amount=9_000_000.0)

    make_user(db_session, role=RoleEnum.BOT_USER, username="analyst1")
    token = login(client, "analyst1").json()["access_token"]

    res = client.get("/api/analytics/kpi-summary", headers=auth_header(token))
    assert res.status_code == 200
    assert res.json()["total_loan_exposure_tzs"] == 10_000_000.0
    assert res.json()["total_submissions"] == 2


def test_system_admin_cannot_access_climate_or_submission_data(client, db_session):
    """
    Acceptance criterion for this project's RBAC design: SYSTEM_ADMIN's dashboard
    is strictly administration-only. Climate/financial data and submissions are
    exclusively the Analyst's (BOT_USER) and reporting institutions' domain.
    """
    make_user(db_session, role=RoleEnum.SYSTEM_ADMIN, username="admin1")
    token = login(client, "admin1").json()["access_token"]

    assert client.get("/api/analytics/kpi-summary", headers=auth_header(token)).status_code == 403
    assert client.get("/api/analytics/hazard-exposure", headers=auth_header(token)).status_code == 403
    assert client.get("/api/analytics/combined-climate-financial-exposure", headers=auth_header(token)).status_code == 403
    assert client.get("/api/submissions", headers=auth_header(token)).status_code == 403
    assert client.get("/api/risk-advisories", headers=auth_header(token)).status_code == 403


def test_bot_user_cannot_access_administration_endpoints(client, db_session):
    """The reverse: BOT_USER (Analyst) has no visibility into administration matters."""
    make_user(db_session, role=RoleEnum.BOT_USER, username="analyst1")
    token = login(client, "analyst1").json()["access_token"]

    assert client.get("/api/audit-logs", headers=auth_header(token)).status_code == 403
    assert client.get("/api/users", headers=auth_header(token)).status_code == 403
    assert client.get("/api/password-reset-requests", headers=auth_header(token)).status_code == 403


def test_institution_id_in_request_body_is_ignored_for_uploads(client, db_session):
    """
    A malicious/confused client attaching an institution_id to the multipart form
    must have zero effect - the server always derives it from the authenticated
    user's own record, never from client-supplied data.
    """
    inst_a = make_institution(db_session, code="BANK-A", name="Bank A")
    inst_b = make_institution(db_session, code="BANK-B", name="Bank B")
    make_user(db_session, role=RoleEnum.INSTITUTION_USER, institution=inst_a, username="viewer_a")
    token = login(client, "viewer_a").json()["access_token"]

    # There is no institution_id form field accepted by the endpoint at all -
    # confirm the resulting submission is still correctly attributed to inst_a.
    from tests.test_upload_and_workflow import build_test_excel  # local import to avoid cycle at collection time
    file_bytes = build_test_excel([{
        "loan_id": "LN-1", "borrower_name": "B", "loan_amount_tzs": 100, "collateral_type": "Land",
        "collateral_value_tzs": 100, "region": "Dodoma", "district": "Chamwino District",
        "reporting_period": "2026-Q1", "climate_hazard_exposure": "None",
    }], reporting_period="2026-Q1")

    res = client.post(
        "/api/submissions/upload",
        data={"reporting_period": "2026-Q1", "institution_id": inst_b.id},  # attempted override - must be ignored
        files={"file": ("test.xlsx", file_bytes, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        headers=auth_header(token),
    )
    assert res.status_code == 201
    assert res.json()["institution_id"] == inst_a.id


def test_access_request_feature_no_longer_exists(client, db_session):
    """Request Access was removed entirely per updated onboarding process - no route should exist."""
    make_user(db_session, role=RoleEnum.SYSTEM_ADMIN, username="admin1")
    token = login(client, "admin1").json()["access_token"]
    res = client.get("/api/access-requests", headers=auth_header(token))
    assert res.status_code == 404


def test_bot_user_can_generate_summary_report(client, db_session):
    make_user(db_session, role=RoleEnum.BOT_USER, username="analyst1")
    token = login(client, "analyst1").json()["access_token"]
    res = client.get("/api/reports/summary.pdf", headers=auth_header(token))
    assert res.status_code == 200
    assert res.headers["content-type"] == "application/pdf"


def test_institution_user_cannot_generate_summary_report(client, db_session):
    inst = make_institution(db_session)
    make_user(db_session, role=RoleEnum.INSTITUTION_USER, institution=inst, username="inst_user")
    token = login(client, "inst_user").json()["access_token"]
    res = client.get("/api/reports/summary.pdf", headers=auth_header(token))
    assert res.status_code == 403


def test_system_admin_cannot_generate_summary_report(client, db_session):
    make_user(db_session, role=RoleEnum.SYSTEM_ADMIN, username="admin1")
    token = login(client, "admin1").json()["access_token"]
    res = client.get("/api/reports/summary.pdf", headers=auth_header(token))
    assert res.status_code == 403
