"""The analyst's Submission Monitoring list must say which institution sent each file."""
from app.models.models import RoleEnum, SubmissionStatus
from tests.conftest import make_institution, make_user, login, auth_header
from tests.test_rbac_and_isolation import _seed_submission_for


def test_analyst_list_shows_institution_name_for_pending_and_final(client, db_session):
    a = make_institution(db_session, code="BANK-A", name="Bank A")
    b = make_institution(db_session, code="BANK-B", name="Bank B")
    _seed_submission_for(db_session, a, status=SubmissionStatus.PENDING)
    _seed_submission_for(db_session, b, status=SubmissionStatus.APPROVED)
    make_user(db_session, role=RoleEnum.BOT_USER, username="analyst_x")
    token = login(client, "analyst_x").json()["access_token"]

    res = client.get("/api/submissions", headers=auth_header(token))
    assert res.status_code == 200
    names = {s["institution_name"] for s in res.json()}
    assert names == {"Bank A", "Bank B"}


def test_submission_detail_carries_institution_name(client, db_session):
    a = make_institution(db_session, code="BANK-A", name="Bank A")
    sub = _seed_submission_for(db_session, a)
    make_user(db_session, role=RoleEnum.BOT_USER, username="analyst_y")
    token = login(client, "analyst_y").json()["access_token"]

    res = client.get(f"/api/submissions/{sub.id}", headers=auth_header(token))
    assert res.status_code == 200
    assert res.json()["institution_name"] == "Bank A"
