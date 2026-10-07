"""
An API key can be limited to the addresses it may be used from.

A key that leaks is far less useful if it works only from the workstation or server it was issued for. The list is optional
(no list = any address, as before), it is checked after the key itself has been proved, a refusal looks like every other refusal
to the caller while the audit log records the real reason and the address, and a list that cannot be read refuses everyone.
"""
from datetime import datetime

import pytest
from sqlalchemy.exc import IntegrityError

from app.models.models import ApiClient, AuditLog, RoleEnum
from tests.conftest import auth_header, login, make_user
from tests.test_integration_access import REFUSAL, _by_key, _row


@pytest.fixture
def bot_token(client, db_session):
    make_user(db_session, role=RoleEnum.BOT_USER, username="bot_allow")
    return login(client, "bot_allow").json()["access_token"]


def _create(client, token, allowed, name="Restricted"):
    return client.post("/api/integration-clients", json={"name": name, "allowed_networks": allowed}, headers=auth_header(token))


def _from(monkeypatch, address):
    monkeypatch.setattr("app.core.integration_auth.client_ip", lambda request: address)


def test_the_list_is_normalised_stored_and_shown(client, db_session, bot_token):
    body = _create(client, bot_token, " 203.0.113.0/24 ,10.1.2.3/32, ").json()
    assert body["allowed_networks"] == "203.0.113.0/24, 10.1.2.3"
    assert db_session.query(ApiClient).one().allowed_networks == "203.0.113.0/24, 10.1.2.3"
    assert client.get("/api/integration-clients", headers=auth_header(bot_token)).json()[0]["allowed_networks"] == "203.0.113.0/24, 10.1.2.3"


@pytest.mark.parametrize("blank", [None, "", "   "])
def test_no_list_means_any_address(client, bot_token, blank):
    assert _create(client, bot_token, blank).json()["allowed_networks"] is None


@pytest.mark.parametrize("bad", ["not-an-address", "300.1.1.1", "10.0.0.0/33", "10.0.0.1; 10.0.0.2"])
def test_a_list_with_a_bad_entry_is_refused_and_no_key_is_made(client, db_session, bot_token, bad):
    assert _create(client, bot_token, bad).status_code == 422
    assert db_session.query(ApiClient).count() == 0


def test_more_than_twenty_entries_are_refused(client, bot_token):
    assert _create(client, bot_token, ", ".join(f"10.0.0.{i}" for i in range(21))).status_code == 422


@pytest.mark.parametrize("address", ["203.0.113.7", "10.1.2.3"])
def test_a_key_works_from_an_allowed_address(client, bot_token, monkeypatch, address):
    key = _create(client, bot_token, "203.0.113.0/24, 10.1.2.3").json()["api_key"]
    _from(monkeypatch, address)
    assert client.get("/api/integration/whoami", headers=_by_key(key)).status_code == 200


@pytest.mark.parametrize("address", ["198.51.100.9", "10.1.2.4", "2001:db8::1", "unknown"])
def test_a_key_is_refused_from_any_other_address_like_every_other_refusal_and_audited(client, db_session, bot_token, monkeypatch, address):
    key = _create(client, bot_token, "203.0.113.0/24, 10.1.2.3").json()["api_key"]
    _from(monkeypatch, address)
    res = client.get("/api/integration/whoami", headers=_by_key(key))
    assert res.status_code == 401 and res.json()["detail"] == REFUSAL
    row = db_session.query(AuditLog).filter_by(action="INTEGRATION_AUTH_FAILED").one()
    assert row.details_json["reason"] == "address not allowed" and row.details_json["client_address"] == address
    assert key.split("_", 2)[2] not in str(row.details_json) + (row.details or "")


def test_the_address_is_checked_only_after_the_key_is_proved(client, db_session, bot_token, monkeypatch):
    key = _create(client, bot_token, "203.0.113.0/24").json()["api_key"]
    _from(monkeypatch, "198.51.100.9")
    client.get("/api/integration/whoami", headers=_by_key(key[:-1] + ("A" if key[-1] != "A" else "B")))
    assert db_session.query(AuditLog).filter_by(action="INTEGRATION_AUTH_FAILED").one().details_json["reason"] == "wrong secret"


def test_a_key_without_a_list_works_from_anywhere(client, bot_token, monkeypatch):
    key = _create(client, bot_token, None).json()["api_key"]
    _from(monkeypatch, "198.51.100.9")
    assert client.get("/api/integration/whoami", headers=_by_key(key)).status_code == 200


def test_a_list_that_cannot_be_read_refuses_everyone(client, db_session, bot_token, monkeypatch):
    key = _create(client, bot_token, "203.0.113.0/24").json()["api_key"]
    db_session.query(ApiClient).one().allowed_networks = "corrupt;;value"
    db_session.commit()
    _from(monkeypatch, "203.0.113.7")
    assert client.get("/api/integration/whoami", headers=_by_key(key)).status_code == 401


def test_the_database_refuses_a_blank_list(db_session):
    with pytest.raises(IntegrityError):
        _row(db_session, allowed_networks="   ")
    db_session.rollback()
    _row(db_session, allowed_networks=None)
