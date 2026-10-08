"""
Rate limits per signed-in person (app/core/rate_limit.py, observation O6 of docs/PENTEST_CHECKLIST.md).

Every route already had a general limit, but it was counted by ADDRESS only: everybody in an office behind one address shared one allowance of 200 requests a minute,
and a busy minute of analysts opening dashboards (about ten requests a page) could stop all of them. Now a request is counted against the signed-in person (a valid
access token), and against the real caller's address only when there is none. Two routes without a limit of their own got one: a password-reset request and the token
refresh. These tests switch the limiter ON for their duration (the suite runs with it off).
"""
import pytest
from fastapi.testclient import TestClient
from jose import jwt
from starlette.requests import Request

from app.core import client_ip as client_ip_module
from app.core.client_ip import parse_networks
from app.core.config import settings
from app.core.database import get_db
from app.core.rate_limit import GENERAL_LIMIT, caller_key, limiter
from app.core.security import create_access_token
from app.main import app
from app.models.models import RoleEnum
from tests.conftest import auth_header, login, make_user


class _ConnectsFrom:
    """Wraps the application so every request appears to come from this address, as in an office behind one address."""

    def __init__(self, application, host):
        self.application, self.host = application, host

    async def __call__(self, scope, receive, send):
        if scope["type"] in ("http", "websocket"):
            scope = {**scope, "client": (self.host, 50000)}
        await self.application(scope, receive, send)


def _reset():
    reset = getattr(limiter, "reset", None)
    if reset:
        reset()
    else:
        limiter._storage.reset()


@pytest.fixture
def office(db_session, monkeypatch):
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    monkeypatch.setattr(client_ip_module, "_configured", lambda: parse_networks(""))      # no trusted proxy: the connection address is the caller
    limiter.enabled = True
    _reset()
    try:
        with TestClient(_ConnectsFrom(app, "198.51.100.20")) as client:                  # everybody arrives from the same address
            yield client
    finally:
        limiter.enabled = False
        _reset()
        app.dependency_overrides.clear()


def test_the_general_limit_is_the_one_documented():
    assert GENERAL_LIMIT == "300/minute"


def test_people_in_one_office_have_an_allowance_each(office, db_session):
    make_user(db_session, role=RoleEnum.BOT_USER, username="office_a")
    make_user(db_session, role=RoleEnum.BOT_USER, username="office_b")
    token_a = login(office, "office_a").json()["access_token"]
    token_b = login(office, "office_b").json()["access_token"]
    codes = [office.get("/api/auth/me", headers=auth_header(token_a)).status_code for _ in range(301)]
    assert codes[:300] == [200] * 300 and codes[300] == 429             # the 301st request of ONE person in a minute is stopped
    assert office.get("/api/auth/me", headers=auth_header(token_b)).status_code == 200      # the colleague at the same address is not affected


def test_password_reset_requests_are_limited_per_address(office):
    codes = [office.post("/api/password-reset-requests", json={"username_or_email": "nobody"}).status_code for _ in range(11)]
    assert codes[:10] == [202] * 10 and codes[10] == 429


def test_token_refresh_is_limited_per_address(office):
    codes = [office.post("/api/auth/refresh", json={"refresh_token": "not-a-real-token"}).status_code for _ in range(31)]
    assert codes[:30] == [401] * 30 and codes[30] == 429


# ------------------------------------------------------------------ which bucket a request goes into
def _request(authorization=None, peer="198.51.100.4"):
    headers = [(b"authorization", authorization.encode())] if authorization else []
    return Request({"type": "http", "method": "GET", "path": "/", "headers": headers, "client": (peer, 50000), "query_string": b""})


@pytest.fixture(autouse=True)
def _no_trusted_proxy(monkeypatch):
    monkeypatch.setattr(client_ip_module, "_configured", lambda: parse_networks(""))


def test_a_valid_token_puts_the_request_in_that_persons_bucket():
    token = create_access_token({"sub": "person-1"})
    assert caller_key(_request(f"Bearer {token}")) == "user:person-1"


def test_a_token_signed_with_another_key_cannot_spend_somebody_elses_allowance():
    forged = jwt.encode({"sub": "person-1"}, "not-the-real-key", algorithm=settings.ALGORITHM)
    assert caller_key(_request(f"Bearer {forged}")) == "198.51.100.4"      # counted against the sender's own address instead


def test_an_expired_token_falls_back_to_the_address():
    expired = jwt.encode({"sub": "person-1", "exp": 1}, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    assert caller_key(_request(f"Bearer {expired}")) == "198.51.100.4"


@pytest.mark.parametrize("header", [None, "", "Bearer ", "Bearer garbage", "Basic abc", "Token xyz"])
def test_no_usable_token_means_the_address(header):
    assert caller_key(_request(header)) == "198.51.100.4"
