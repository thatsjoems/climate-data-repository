"""
Authentication tests - Module A / Solution 2 (secure user authentication).
"""
from app.models.models import RoleEnum
from tests.conftest import make_institution, make_user, login, DEFAULT_PASSWORD


def test_valid_login_returns_token(client, db_session):
    make_user(db_session, username="alice")
    res = login(client, "alice")
    assert res.status_code == 200
    assert "access_token" in res.json()
    assert res.json()["user"]["username"] == "alice"


def test_invalid_password_rejected(client, db_session):
    make_user(db_session, username="alice")
    res = login(client, "alice", password="wrong-password")
    assert res.status_code == 401


def test_nonexistent_username_gives_generic_error(client, db_session):
    """Same error/shape as a wrong password - prevents username enumeration."""
    res_missing = client.post("/api/auth/login", json={"username": "ghost", "password": "whatever123!"})
    make_user(db_session, username="alice")
    res_wrong_pw = login(client, "alice", password="whatever123!")
    assert res_missing.status_code == res_wrong_pw.status_code == 401
    assert res_missing.json()["detail"] == res_wrong_pw.json()["detail"]


def test_account_locks_after_max_failed_attempts(client, db_session):
    make_user(db_session, username="alice")
    for _ in range(5):
        res = login(client, "alice", password="wrong-password")
        assert res.status_code == 401

    # 6th attempt (even with the CORRECT password) must now be blocked by the lockout
    res = login(client, "alice", password=DEFAULT_PASSWORD)
    assert res.status_code == 403
    assert "locked" in res.json()["detail"].lower()


def test_deactivated_account_cannot_login(client, db_session):
    user = make_user(db_session, username="alice")
    user.is_active = False
    db_session.commit()
    res = login(client, "alice")
    assert res.status_code == 403


def test_unauthenticated_request_rejected(client):
    res = client.get("/api/submissions")
    assert res.status_code == 401
