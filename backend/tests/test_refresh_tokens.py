"""
Refresh token tests - Module: session security (short-lived access tokens + revocable, rotated refresh tokens).

Since observation O2 the refresh token is carried by an HttpOnly cookie that the page's scripts cannot read (app/core/session_cookie.py); the
access token is the only token in an answer. The test client keeps cookies between calls like a browser does.
"""
from app.core.config import settings
from app.models.models import RoleEnum, RefreshToken
from tests.conftest import WEB, make_user, login, auth_header

COOKIE = "cdr_refresh"


def _plant(client, value: str) -> None:
    """Puts exactly this value in the browser's cookie (a copy that was stolen or kept), replacing whatever is there."""
    client.cookies.delete(COOKIE)
    client.cookies.set(COOKIE, value)


def _set_cookie_header(res) -> str:
    return next(v for k, v in res.headers.multi_items() if k.lower() == "set-cookie" and v.startswith(COOKIE + "="))


def test_login_returns_the_access_token_and_sets_the_refresh_token_as_an_http_only_cookie(client, db_session):
    make_user(db_session, username="alice")
    res = login(client, "alice")
    assert res.status_code == 200
    body = res.json()
    assert body["access_token"]
    assert body["refresh_token"] is None                # a script reading the answer never sees the refresh token
    header = _set_cookie_header(res).lower()
    assert "httponly" in header and "samesite=strict" in header and "path=/api/auth" in header
    assert f"max-age={settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400}" in header
    assert client.cookies.get(COOKIE)


def test_the_cookie_is_secure_when_the_site_runs_over_https(client, db_session, monkeypatch):
    make_user(db_session, username="alice")
    assert "secure" not in _set_cookie_header(login(client, "alice")).lower().replace("samesite", "")      # plain http in the test suite
    monkeypatch.setattr(settings, "REFRESH_COOKIE_SECURE", True)
    assert "; secure" in _set_cookie_header(login(client, "alice")).lower()


def test_refresh_token_is_stored_hashed_not_raw(client, db_session):
    """The raw refresh token must never be recoverable from the database."""
    make_user(db_session, username="alice")
    login(client, "alice")
    raw_refresh = client.cookies.get(COOKIE)

    stored = db_session.query(RefreshToken).first()
    assert stored is not None
    assert stored.token_hash != raw_refresh
    assert len(stored.token_hash) == 64  # SHA-256 hex digest


def test_refresh_endpoint_issues_a_new_access_token_and_a_new_cookie(client, db_session):
    make_user(db_session, username="alice")
    login(client, "alice")
    old_cookie = client.cookies.get(COOKIE)

    res = client.post("/api/auth/refresh", headers=WEB)
    assert res.status_code == 200
    body = res.json()
    assert body["access_token"] and "refresh_token" not in body
    assert body["user"]["username"] == "alice"           # a reloaded page learns who is signed in from this answer
    assert client.cookies.get(COOKIE) and client.cookies.get(COOKIE) != old_cookie
    me = client.get("/api/auth/me", headers=auth_header(body["access_token"]))
    assert me.status_code == 200 and me.json()["username"] == "alice"


def test_refresh_token_is_rotated_old_one_cannot_be_reused(client, db_session):
    """Once a refresh token has been used it is dead: a stolen copy replayed after the legitimate browser rotated it is rejected."""
    make_user(db_session, username="alice")
    login(client, "alice")
    original = client.cookies.get(COOKIE)

    assert client.post("/api/auth/refresh", headers=WEB).status_code == 200

    _plant(client, original)                                                          # the thief's copy
    assert client.post("/api/auth/refresh", headers=WEB).status_code == 401


def test_a_missing_or_invalid_cookie_is_rejected(client, db_session):
    assert client.post("/api/auth/refresh", headers=WEB).status_code == 401              # no cookie
    _plant(client, "this-is-not-a-real-token")
    assert client.post("/api/auth/refresh", headers=WEB).status_code == 401


def test_a_refresh_token_sent_in_the_body_is_not_accepted(client, db_session):
    """Only the cookie counts, so nothing a script could hold or send can renew a session."""
    make_user(db_session, username="alice")
    login(client, "alice")
    raw = client.cookies.get(COOKIE)
    client.cookies.clear()
    assert client.post("/api/auth/refresh", json={"refresh_token": raw}, headers=WEB).status_code == 401


def test_the_cookie_endpoints_refuse_a_request_that_does_not_come_from_the_application(client, db_session):
    make_user(db_session, username="alice")
    login(client, "alice")
    assert client.post("/api/auth/refresh").status_code == 403          # no X-CDR-Client header: what a form on another site would send
    assert client.post("/api/auth/logout").status_code == 403
    assert client.post("/api/auth/refresh", headers={"X-CDR-Client": "other"}).status_code == 403
    assert client.post("/api/auth/refresh", headers=WEB).status_code == 200      # the refused calls did not use the token up


def test_logout_revokes_the_refresh_token_and_clears_the_cookie(client, db_session):
    """After logout the refresh token must no longer be usable to get a new access token, even if a copy was kept."""
    make_user(db_session, username="alice")
    login(client, "alice")
    kept_copy = client.cookies.get(COOKIE)

    logout_res = client.post("/api/auth/logout", headers=WEB)
    assert logout_res.status_code == 200
    assert 'max-age=0' in _set_cookie_header(logout_res).lower()          # the browser is told to delete it
    assert not client.cookies.get(COOKIE)

    _plant(client, kept_copy)
    assert client.post("/api/auth/refresh", headers=WEB).status_code == 401


def test_logout_without_a_session_is_harmless(client, db_session):
    assert client.post("/api/auth/logout", headers=WEB).status_code == 200


def test_refresh_fails_for_deactivated_user(client, db_session):
    """A refresh token must stop working immediately if the account is deactivated in between."""
    user = make_user(db_session, username="alice")
    login(client, "alice")

    user.is_active = False
    db_session.commit()

    assert client.post("/api/auth/refresh", headers=WEB).status_code == 401


def test_access_token_alone_still_works_for_normal_requests(client, db_session):
    """Sanity check: the refresh mechanism doesn't break ordinary authenticated requests."""
    make_user(db_session, role=RoleEnum.BOT_USER, username="analyst1")
    token = login(client, "analyst1").json()["access_token"]
    res = client.get("/api/climate-data/quality-summary", headers=auth_header(token))
    assert res.status_code == 200
