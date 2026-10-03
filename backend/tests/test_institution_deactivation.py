"""
Institution deactivation is enforced (KG-02).

Before this fix, deactivating an institution set a flag that nothing read: its users
could still sign in, refresh tokens and upload. These tests pin the enforcement at
every entry point - login, token refresh, per-request authentication and password
recovery - and the supported way to reverse it.
"""
from types import SimpleNamespace

from app.core.account_status import (
    ACCOUNT_DEACTIVATED,
    INSTITUTION_DEACTIVATED,
    authentication_block_reason,
)
from app.models.models import AuditLog, PasswordResetRequest, RoleEnum
from tests.conftest import auth_header, login, make_institution, make_user


def _admin_token(client, db_session):
    make_user(db_session, role=RoleEnum.SYSTEM_ADMIN, username="admin1")
    return login(client, "admin1").json()["access_token"]


# ---- the decision itself ---------------------------------------------------

def test_block_reason_covers_every_combination():
    active, inactive, legacy_null = (SimpleNamespace(is_active=v) for v in (True, False, None))
    cases = [
        (SimpleNamespace(is_active=True, institution=active), None),
        (SimpleNamespace(is_active=True, institution=inactive), INSTITUTION_DEACTIVATED),
        (SimpleNamespace(is_active=False, institution=active), ACCOUNT_DEACTIVATED),
        (SimpleNamespace(is_active=False, institution=inactive), ACCOUNT_DEACTIVATED),
        (SimpleNamespace(is_active=True, institution=None), None),          # BOT Analyst / Administrator
        (SimpleNamespace(is_active=True, institution=legacy_null), None),   # legacy NULL is not a lock-out
    ]
    for user, expected in cases:
        assert authentication_block_reason(user) == expected


# ---- every entry point -----------------------------------------------------

def test_user_of_a_deactivated_institution_cannot_log_in(client, db_session):
    inst = make_institution(db_session)
    make_user(db_session, institution=inst, username="teller")
    inst.is_active = False
    db_session.commit()

    res = login(client, "teller")
    assert res.status_code == 403
    assert "institution" in res.json()["detail"].lower()


def test_a_wrong_password_still_gets_the_generic_message(client, db_session):
    """The institution status is only revealed after the password is verified (no username enumeration)."""
    inst = make_institution(db_session)
    make_user(db_session, institution=inst, username="teller")
    inst.is_active = False
    db_session.commit()

    res = login(client, "teller", password="not-the-password")
    assert res.status_code == 401
    assert res.json()["detail"] == "Incorrect username or password"


def test_an_already_issued_access_token_stops_working(client, db_session):
    inst = make_institution(db_session)
    make_user(db_session, institution=inst, username="teller")
    token = login(client, "teller").json()["access_token"]
    assert client.get("/api/auth/me", headers=auth_header(token)).status_code == 200

    inst.is_active = False
    db_session.commit()
    assert client.get("/api/auth/me", headers=auth_header(token)).status_code == 401


def test_a_refresh_token_is_refused(client, db_session):
    inst = make_institution(db_session)
    make_user(db_session, institution=inst, username="teller")
    refresh = login(client, "teller").json()["refresh_token"]

    inst.is_active = False
    db_session.commit()
    res = client.post("/api/auth/refresh", json={"refresh_token": refresh})
    assert res.status_code == 401


def test_password_recovery_creates_no_request_for_such_a_user(client, db_session):
    inst = make_institution(db_session)
    make_user(db_session, institution=inst, username="teller")
    inst.is_active = False
    db_session.commit()

    res = client.post("/api/password-reset-requests", json={"username_or_email": "teller"})
    assert res.status_code == 202          # same generic answer as for any other identifier
    assert db_session.query(PasswordResetRequest).count() == 0


# ---- the administrator's endpoints -----------------------------------------

def test_deactivating_through_the_api_blocks_users_and_activating_restores_them(client, db_session):
    inst = make_institution(db_session)
    make_user(db_session, institution=inst, username="teller")
    admin = _admin_token(client, db_session)

    res = client.patch(f"/api/institutions/{inst.id}/deactivate", headers=auth_header(admin))
    assert res.status_code == 200 and res.json()["is_active"] is False
    assert login(client, "teller").status_code == 403

    res = client.patch(f"/api/institutions/{inst.id}/activate", headers=auth_header(admin))
    assert res.status_code == 200 and res.json()["is_active"] is True
    assert login(client, "teller").status_code == 200

    actions = [row.action for row in db_session.query(AuditLog).all()]
    assert "INSTITUTION_DEACTIVATED" in actions and "INSTITUTION_ACTIVATED" in actions


def test_activating_an_unknown_institution_is_a_404(client, db_session):
    admin = _admin_token(client, db_session)
    res = client.patch("/api/institutions/does-not-exist/activate", headers=auth_header(admin))
    assert res.status_code == 404


def test_only_a_system_administrator_may_activate_or_deactivate(client, db_session):
    inst = make_institution(db_session)
    make_user(db_session, institution=inst, username="teller")
    make_user(db_session, role=RoleEnum.BOT_USER, username="analyst")
    for username in ("teller", "analyst"):
        token = login(client, username).json()["access_token"]
        for action in ("activate", "deactivate"):
            res = client.patch(f"/api/institutions/{inst.id}/{action}", headers=auth_header(token))
            assert res.status_code == 403, (username, action)


# ---- who is NOT affected ---------------------------------------------------

def test_other_institutions_and_bot_users_are_unaffected(client, db_session):
    bank_a = make_institution(db_session, code="BANK-A", name="Bank A Ltd")
    bank_b = make_institution(db_session, code="BANK-B", name="Bank B Ltd")
    make_user(db_session, institution=bank_a, username="a_user")
    make_user(db_session, institution=bank_b, username="b_user")
    make_user(db_session, role=RoleEnum.BOT_USER, username="analyst")

    bank_a.is_active = False
    db_session.commit()

    assert login(client, "a_user").status_code == 403
    assert login(client, "b_user").status_code == 200
    assert login(client, "analyst").status_code == 200
