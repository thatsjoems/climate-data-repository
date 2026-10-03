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


# ---- Username enumeration via lockout status (item 8 of the September 2026 external review) ----

def test_a_wrong_password_on_a_locked_account_gives_the_generic_message_not_a_lock_notice(client, db_session):
    """
    Before this fix, ANY password against a locked account revealed the lock
    (403) - so an attacker could learn a username was valid, and currently
    locked, without ever supplying its correct password. A wrong password
    must always look identical whether the account is locked or not.
    """
    make_user(db_session, username="bob")
    for _ in range(5):
        assert login(client, "bob", password="wrong-password").status_code == 401
    # Account is now locked. A further WRONG password must still be the generic 401 - not 403.
    res = login(client, "bob", password="still-wrong")
    assert res.status_code == 401
    assert res.json()["detail"] == "Incorrect username or password"


def test_the_correct_password_is_required_before_lock_status_is_revealed(client, db_session):
    """The 403 lock notice is reachable only with the account's own correct password."""
    make_user(db_session, username="carol")
    for _ in range(5):
        login(client, "carol", password="wrong-password")
    res = login(client, "carol", password=DEFAULT_PASSWORD)
    assert res.status_code == 403
    assert "locked" in res.json()["detail"].lower()


def test_locked_and_unknown_usernames_are_indistinguishable_under_a_wrong_password(client, db_session):
    """The 401 body for a wrong password must be identical whether the username exists and is locked, or does not exist at all."""
    make_user(db_session, username="dora")
    for _ in range(5):
        login(client, "dora", password="wrong-password")
    locked_user_response = login(client, "dora", password="another-wrong-one")
    unknown_user_response = login(client, "no-such-user-at-all", password="anything")
    assert locked_user_response.status_code == unknown_user_response.status_code == 401
    assert locked_user_response.json()["detail"] == unknown_user_response.json()["detail"]


def test_deactivated_account_cannot_login(client, db_session):
    user = make_user(db_session, username="alice")
    user.is_active = False
    db_session.commit()
    res = login(client, "alice")
    assert res.status_code == 403


def test_unauthenticated_request_rejected(client):
    res = client.get("/api/submissions")
    assert res.status_code == 401
