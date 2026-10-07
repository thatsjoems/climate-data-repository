"""
Behind the production proxy the rate limit must see the REAL caller, not the proxy.

Before this was fixed every connection came from the proxy's address, so all users shared one sign-in allowance (10 a minute):
one person trying passwords could stop everybody else signing in. These tests switch the limiter ON (the rest of the suite
keeps it off) and connect as the proxy.
"""
import pytest
from fastapi.testclient import TestClient

from app.core import client_ip as client_ip_module
from app.core.client_ip import parse_networks
from app.core.database import get_db
from app.core.rate_limit import limiter
from app.main import app


def _reset():
    reset = getattr(limiter, "reset", None)
    if reset:
        reset()
    else:
        limiter._storage.reset()


@pytest.fixture
def behind_a_proxy(db_session, monkeypatch):
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    monkeypatch.setattr(client_ip_module, "_configured", lambda: parse_networks("10.0.0.0/8"))
    limiter.enabled = True
    _reset()
    try:
        with TestClient(app, client=("10.0.0.5", 50000)) as proxy:      # every request arrives from the proxy's address
            yield proxy
    finally:
        limiter.enabled = False
        _reset()
        app.dependency_overrides.clear()


def _attempt(proxy, forwarded):
    return proxy.post("/api/auth/login", json={"username": "nobody", "password": "x"}, headers={"X-Forwarded-For": forwarded})


def test_each_real_caller_has_their_own_sign_in_allowance(behind_a_proxy):
    codes = [_attempt(behind_a_proxy, "198.51.100.1").status_code for _ in range(11)]
    assert codes[:10] == [401] * 10 and codes[10] == 429          # the 11th attempt of one caller in a minute is stopped
    assert _attempt(behind_a_proxy, "198.51.100.2").status_code == 401   # a different caller is not affected


def test_a_caller_cannot_get_a_fresh_allowance_by_inventing_addresses(behind_a_proxy):
    # the proxy appends the real address on the right; whatever the caller wrote on the left is never used
    for n in range(10):
        assert _attempt(behind_a_proxy, f"9.9.9.{n}, 198.51.100.7").status_code == 401
    assert _attempt(behind_a_proxy, "8.8.8.8, 198.51.100.7").status_code == 429


def test_without_a_trusted_proxy_the_header_is_not_believed(db_session, monkeypatch):
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    monkeypatch.setattr(client_ip_module, "_configured", lambda: ())
    limiter.enabled = True
    _reset()
    try:
        with TestClient(app, client=("10.0.0.5", 50000)) as direct:
            codes = [_attempt(direct, f"7.7.7.{n}").status_code for n in range(11)]
        assert codes[:10] == [401] * 10 and codes[10] == 429       # varying the header changes nothing: one connection, one allowance
    finally:
        limiter.enabled = False
        _reset()
        app.dependency_overrides.clear()
