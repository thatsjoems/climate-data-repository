"""
Refresh token tests - Module: session security (short-lived access tokens +
revocable, rotated refresh tokens).
"""
from app.models.models import RoleEnum, RefreshToken
from tests.conftest import make_user, login, auth_header


def test_login_returns_both_access_and_refresh_token(client, db_session):
    make_user(db_session, username="alice")
    res = login(client, "alice")
    assert res.status_code == 200
    body = res.json()
    assert "access_token" in body
    assert "refresh_token" in body
    assert body["access_token"] != body["refresh_token"]


def test_refresh_token_is_stored_hashed_not_raw(client, db_session):
    """The raw refresh token must never be recoverable from the database."""
    make_user(db_session, username="alice")
    res = login(client, "alice")
    raw_refresh = res.json()["refresh_token"]

    stored = db_session.query(RefreshToken).first()
    assert stored is not None
    assert stored.token_hash != raw_refresh
    assert len(stored.token_hash) == 64  # SHA-256 hex digest


def test_refresh_endpoint_issues_new_access_token(client, db_session):
    make_user(db_session, username="alice")
    login_res = login(client, "alice")
    refresh_token = login_res.json()["refresh_token"]
    old_access_token = login_res.json()["access_token"]

    res = client.post("/api/auth/refresh", json={"refresh_token": refresh_token})
    assert res.status_code == 200
    body = res.json()
    assert "access_token" in body
    assert "refresh_token" in body
    # New access token actually works for an authenticated request
    me = client.get("/api/auth/me", headers=auth_header(body["access_token"]))
    assert me.status_code == 200
    assert me.json()["username"] == "alice"


def test_refresh_token_is_rotated_old_one_cannot_be_reused(client, db_session):
    """
    Acceptance criterion for rotation: once a refresh token has been used,
    it is dead - reusing it (e.g. a stolen copy replayed after the
    legitimate client already rotated) must be rejected.
    """
    make_user(db_session, username="alice")
    login_res = login(client, "alice")
    original_refresh = login_res.json()["refresh_token"]

    first_use = client.post("/api/auth/refresh", json={"refresh_token": original_refresh})
    assert first_use.status_code == 200

    second_use = client.post("/api/auth/refresh", json={"refresh_token": original_refresh})
    assert second_use.status_code == 401


def test_invalid_refresh_token_is_rejected(client, db_session):
    res = client.post("/api/auth/refresh", json={"refresh_token": "this-is-not-a-real-token"})
    assert res.status_code == 401


def test_logout_revokes_refresh_token(client, db_session):
    """After logout, the refresh token must no longer be usable to get a new access token."""
    make_user(db_session, username="alice")
    login_res = login(client, "alice")
    refresh_token = login_res.json()["refresh_token"]

    logout_res = client.post("/api/auth/logout", json={"refresh_token": refresh_token})
    assert logout_res.status_code == 200

    reuse_attempt = client.post("/api/auth/refresh", json={"refresh_token": refresh_token})
    assert reuse_attempt.status_code == 401


def test_refresh_fails_for_deactivated_user(client, db_session):
    """A refresh token must stop working immediately if the account is deactivated in between."""
    user = make_user(db_session, username="alice")
    login_res = login(client, "alice")
    refresh_token = login_res.json()["refresh_token"]

    user.is_active = False
    db_session.commit()

    res = client.post("/api/auth/refresh", json={"refresh_token": refresh_token})
    assert res.status_code == 401


def test_access_token_alone_still_works_for_normal_requests(client, db_session):
    """Sanity check: the refresh mechanism doesn't break ordinary authenticated requests."""
    make_user(db_session, role=RoleEnum.BOT_USER, username="analyst1")
    token = login(client, "analyst1").json()["access_token"]
    res = client.get("/api/climate-data/quality-summary", headers=auth_header(token))
    assert res.status_code == 200
