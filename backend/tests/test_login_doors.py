"""
The two sign-in doors: Bank staff (/staff/login, portal "internal") and reporting institutions (/login, portal "external").
See app/core/portal.py.
"""
import pytest

from app.core.portal import EXTERNAL, INTERNAL, portal_of, wrong_portal_message
from app.models.models import AuditLog, RoleEnum, User
from tests.conftest import DEFAULT_PASSWORD, make_user


def _door(client, username, portal, password=DEFAULT_PASSWORD):
    body = {"username": username, "password": password}
    if portal is not None:
        body["portal"] = portal
    return client.post("/api/auth/login", json=body)


@pytest.fixture()
def people(db_session):
    make_user(db_session, role=RoleEnum.INSTITUTION_USER, username="inst1")
    make_user(db_session, role=RoleEnum.BOT_USER, username="bot1")
    make_user(db_session, role=RoleEnum.SYSTEM_ADMIN, username="admin1")


def test_every_role_belongs_to_exactly_one_door():
    assert portal_of(RoleEnum.BOT_USER) == INTERNAL
    assert portal_of(RoleEnum.SYSTEM_ADMIN) == INTERNAL
    assert portal_of(RoleEnum.INSTITUTION_USER) == EXTERNAL
    assert {portal_of(r) for r in RoleEnum} == {INTERNAL, EXTERNAL}


@pytest.mark.parametrize("username,portal", [("inst1", "external"), ("bot1", "internal"), ("admin1", "internal")])
def test_a_person_signs_in_at_their_own_door(client, people, username, portal):
    res = _door(client, username, portal)
    assert res.status_code == 200
    assert res.json()["access_token"]


@pytest.mark.parametrize("username,portal,where", [
    ("inst1", "internal", "/login"),
    ("bot1", "external", "/staff/login"),
    ("admin1", "external", "/staff/login"),
])
def test_a_person_at_the_other_door_is_turned_away_and_told_where_to_go(client, people, username, portal, where):
    res = _door(client, username, portal)
    assert res.status_code == 403
    assert where in res.json()["detail"]
    assert "access_token" not in res.json()


def test_a_caller_that_names_no_door_is_not_restricted(client, people):
    for name in ("inst1", "bot1", "admin1"):
        assert _door(client, name, None).status_code == 200


def test_an_unknown_door_is_refused_as_malformed(client, people):
    assert _door(client, "bot1", "back-office").status_code == 422


def test_the_wrong_door_reveals_nothing_without_the_right_password(client, people):
    wrong_door_wrong_password = _door(client, "bot1", "external", password="Not-The-Password-1!")
    unknown_user = _door(client, "nobody", "external", password="Not-The-Password-1!")
    assert wrong_door_wrong_password.status_code == unknown_user.status_code == 401
    assert wrong_door_wrong_password.json() == unknown_user.json()


def test_the_wrong_door_is_audited_and_is_not_a_failed_password(client, db_session, people):
    for _ in range(15):                                                  # far more than the lock-out allows
        assert _door(client, "inst1", "internal").status_code == 403
    user = db_session.query(User).filter(User.username == "inst1").one()
    assert (user.failed_login_attempts or 0) == 0 and user.locked_until is None
    assert _door(client, "inst1", "external").status_code == 200         # still free to sign in at their own door
    logged = db_session.query(AuditLog).filter(AuditLog.action == "LOGIN_WRONG_PORTAL", AuditLog.user_id == user.id).count()
    assert logged == 15


def test_the_message_names_the_right_door_for_each_kind_of_person():
    assert "/staff/login" in wrong_portal_message(RoleEnum.BOT_USER)
    assert "/staff/login" in wrong_portal_message(RoleEnum.SYSTEM_ADMIN)
    assert "/login" in wrong_portal_message(RoleEnum.INSTITUTION_USER)


def test_the_second_step_follows_the_right_door_only(client, db_session, monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "MFA_REQUIRED", True)
    make_user(db_session, role=RoleEnum.BOT_USER, username="bot2")
    assert _door(client, "bot2", "external").status_code == 403           # no step token is handed out at the wrong door
    ok = _door(client, "bot2", "internal")
    assert ok.status_code == 200 and ok.json()["mfa_setup_required"] is True and ok.json()["access_token"] is None
