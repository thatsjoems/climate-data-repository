"""RTIS/BSIS/QGIS/ArcGIS connection status (sidebar of the BOT dashboard)."""
import itertools
from datetime import timedelta

import httpx
import pytest

from app.core.config import settings
from app.core.timeutil import utcnow
from app.models.models import ApiClient, RoleEnum
from app.services import external_systems
from tests.conftest import auth_header, login, make_user


def _bot(db):
    return make_user(db, role=RoleEnum.BOT_USER, username="bot1")


_prefix_counter = itertools.count(1)


def _key(db, user, name, last_used=None, scope="READ", revoked=False, days=30):
    # key_prefix is unique in the database, so every key needs its own.
    k = ApiClient(name=name, key_prefix=f"{next(_prefix_counter):010x}", key_hash="x" * 64, created_by_user_id=user.id,
                  expires_at=utcnow() + timedelta(days=days), last_used_at=last_used, scope=scope,
                  revoked_at=utcnow() if revoked else None)
    db.add(k)
    db.commit()
    return k


def _status(client, username="bot1"):
    token = login(client, username).json()["access_token"]
    res = client.get("/api/integration-clients/platform-status", headers=auth_header(token))
    return res


def test_nothing_is_connected_by_default(client, db_session):
    _bot(db_session)
    res = _status(client)
    assert res.status_code == 200
    by_name = {r["name"]: r for r in res.json()}
    assert set(by_name) == {"ArcGIS", "QGIS", "BSIS", "RTIS"}
    assert not any(r["connected"] for r in by_name.values())
    assert by_name["RTIS"]["configured"] is False


def test_gis_tool_is_connected_only_by_a_recently_used_read_key(client, db_session):
    bot = _bot(db_session)
    _key(db_session, bot, "QGIS - FSD GIS desk", last_used=utcnow() - timedelta(days=2))
    _key(db_session, bot, "ArcGIS old", last_used=utcnow() - timedelta(days=90))
    _key(db_session, bot, "QGIS ingest", scope="INGEST_TMA", last_used=utcnow())
    by_name = {r["name"]: r for r in _status(client).json()}
    assert by_name["QGIS"]["connected"] is True
    assert by_name["ArcGIS"]["connected"] is False and by_name["ArcGIS"]["configured"] is True


def test_revoked_key_does_not_count(client, db_session):
    bot = _bot(db_session)
    _key(db_session, bot, "QGIS", last_used=utcnow(), revoked=True)
    assert {r["name"]: r for r in _status(client).json()}["QGIS"]["configured"] is False


def test_only_bot_users_may_ask(client, db_session):
    make_user(db_session, role=RoleEnum.SYSTEM_ADMIN, username="adm1")
    assert _status(client, "adm1").status_code == 403


@pytest.fixture()
def fake_http(monkeypatch):
    calls = []

    def install(result):
        def fake_get(url, headers=None, timeout=None, follow_redirects=None):
            calls.append((url, headers, follow_redirects))
            if isinstance(result, Exception):
                raise result
            return httpx.Response(result, request=httpx.Request("GET", url))
        monkeypatch.setattr(external_systems.httpx, "get", fake_get)
        return calls
    return install


def test_http_system_connected_on_2xx_and_never_follows_redirects(fake_http):
    calls = fake_http(200)
    st = external_systems.check_http_system("RTIS", "https://rtis.bot.local/", "secret", "health", production=True)
    assert st.connected and st.configured
    url, headers, follow = calls[0]
    assert url == "https://rtis.bot.local/health"
    assert headers["X-API-Key"] == "secret" and follow is False


@pytest.mark.parametrize("outcome,expected", [
    (503, "HTTP 503"), (httpx.ConnectError("boom"), "could not be reached"), (httpx.ReadTimeout("slow"), "time limit"),
])
def test_http_system_failures_are_reported_not_raised(fake_http, outcome, expected):
    fake_http(outcome)
    st = external_systems.check_http_system("BSIS", "https://bsis.bot.local", "k", "/health", production=True)
    assert not st.connected and st.configured and expected in st.detail


def test_production_refuses_plain_http(fake_http):
    calls = fake_http(200)
    st = external_systems.check_http_system("RTIS", "http://rtis.bot.local", "k", "/health", production=True)
    assert not st.connected and "https" in st.detail and calls == []


def test_error_detail_never_contains_the_credential(fake_http):
    fake_http(httpx.ConnectError("could not connect with key super-secret"))
    st = external_systems.check_http_system("RTIS", "https://x.local", "super-secret", "/health", production=True)
    assert "super-secret" not in st.detail
