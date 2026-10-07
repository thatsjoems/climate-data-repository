"""
Keys that SEND climate data (TMA and PMO).

What these tests pin down: a sending key can do exactly one thing (send a file) and nothing else, a reading key cannot
send, the data goes through the very same checks as a manual upload and is stored as UNVALIDATED, the label of its source
follows from the key and cannot be chosen by the sender (and a person cannot type it either), re-sending a file is safe,
every delivery is audited and the analysts are told, and the database refuses a malformed key or batch.
"""
from datetime import datetime

import pytest
from sqlalchemy.exc import IntegrityError

from app.models.models import ApiClient, AuditLog, ClimateIngestionBatch, ClimateRecord, Notification, RoleEnum, User
from tests.conftest import auth_header, login, make_user
from tests.test_climate_ingestion import _csv_bytes
from tests.test_integration_access import _row

GOOD = ["Dodoma,Chamwino,2026,7,45.2,28.5,Drought,MEDIUM,REC-1", "Mwanza,,2026,7,120.0,25.1,Flood,HIGH,REC-2"]


def _make_key(client, token, scope, name=None):
    res = client.post("/api/integration-clients", json={"name": name or f"{scope} feed", "scope": scope}, headers=auth_header(token))
    assert res.status_code == 201, res.text
    return res.json()


def _send(client, key, rows=GOOD, filename="tma.csv", **form):
    return client.post(
        "/api/integration/climate-data", data=form,
        files={"file": (filename, _csv_bytes(rows), "text/csv")}, headers={"X-API-Key": key},
    )


@pytest.fixture
def bot_token(client, db_session):
    make_user(db_session, role=RoleEnum.BOT_USER, username="bot_feed")
    return login(client, "bot_feed").json()["access_token"]


@pytest.fixture
def tma(client, bot_token):
    return _make_key(client, bot_token, "INGEST_TMA")


@pytest.fixture
def reader(client, bot_token):
    return _make_key(client, bot_token, "READ", name="QGIS reader")


# ------------------------------------------------------------------ creating a sending key
@pytest.mark.parametrize("scope", ["INGEST_TMA", "INGEST_PMO"])
def test_a_bot_analyst_creates_a_sending_key_that_says_what_it_may_do(client, bot_token, scope):
    made = _make_key(client, bot_token, scope)
    assert made["scope"] == scope
    who = client.get("/api/integration/whoami", headers={"X-API-Key": made["api_key"]}).json()
    assert who["scope"] == scope and "only send climate data" in who["access"]


def test_an_unknown_scope_is_refused(client, bot_token):
    res = client.post("/api/integration-clients", json={"name": "x", "scope": "WRITE_EVERYTHING"}, headers=auth_header(bot_token))
    assert res.status_code == 422


def test_the_list_shows_what_each_key_may_do(client, bot_token, tma, reader):
    listing = client.get("/api/integration-clients", headers=auth_header(bot_token)).json()
    assert {item["scope"] for item in listing} == {"INGEST_TMA", "READ"}


# ------------------------------------------------------------------ what a delivery does
@pytest.mark.parametrize("scope, label", [("INGEST_TMA", "API_KEY_TMA"), ("INGEST_PMO", "API_KEY_PMO")])
def test_a_delivery_is_stored_unvalidated_under_a_label_the_sender_cannot_choose(client, db_session, bot_token, scope, label):
    made = _make_key(client, bot_token, scope)
    res = _send(client, made["api_key"], source="MANUAL_OTHER_FILE", dataset_name="Daily rainfall")   # a claimed source is ignored
    assert res.status_code == 201
    body = res.json()
    assert body["source"] == label and body["records_accepted"] == 2 and body["uploaded_by_api_client_id"] == made["id"]
    rows = db_session.query(ClimateRecord).all()
    assert len(rows) == 2 and {r.quality_flag for r in rows} == {"UNVALIDATED"} and {r.source for r in rows} == {label}
    batch = db_session.query(ClimateIngestionBatch).one()
    assert batch.uploaded_by_user_id is None and batch.uploaded_by_api_client_id == made["id"] and batch.dataset_name == "Daily rainfall"


def test_a_person_cannot_type_the_key_labels_in_a_manual_upload(client, bot_token):
    res = client.post(
        "/api/climate-data/ingest", data={"source": "API_KEY_TMA"},
        files={"file": ("a.csv", _csv_bytes(GOOD), "text/csv")}, headers=auth_header(bot_token),
    )
    assert res.status_code == 400


def test_sending_the_same_file_again_is_safe_and_overwrites_nothing(client, db_session, tma):
    assert _send(client, tma["api_key"]).json()["records_accepted"] == 2
    again = _send(client, tma["api_key"]).json()
    assert again["records_accepted"] == 0 and again["records_duplicate"] == 2
    assert db_session.query(ClimateRecord).count() == 2


def test_rejected_rows_are_counted_and_not_stored(client, db_session, tma):
    body = _send(client, tma["api_key"], rows=["Narnia,,2026,7,45.2,28.5,,,REC-9", GOOD[0]]).json()
    assert body["records_accepted"] == 1 and body["records_rejected"] == 1
    assert [r.region for r in db_session.query(ClimateRecord).all()] == ["Dodoma"]


def test_a_file_of_the_wrong_type_is_refused(client, db_session, tma):
    assert _send(client, tma["api_key"], filename="notes.txt").status_code == 400
    assert db_session.query(ClimateIngestionBatch).count() == 0


# ------------------------------------------------------------------ a key does one thing
def test_a_sending_key_cannot_read_and_a_reading_key_cannot_send(client, db_session, tma, reader):
    assert client.get("/api/integration/kpi-summary", headers={"X-API-Key": tma["api_key"]}).status_code == 403
    assert _send(client, reader["api_key"]).status_code == 403
    assert db_session.query(ClimateRecord).count() == 0
    reasons = [a.details_json["reason"] for a in db_session.query(AuditLog).filter_by(action="INTEGRATION_AUTH_FAILED").all()]
    assert reasons == ["scope", "scope"]


def test_a_sending_key_works_nowhere_else(client, tma):
    key = {"X-API-Key": tma["api_key"]}
    assert client.get("/api/climate-data/ingestions", headers=key).status_code == 401
    res = client.post("/api/climate-data/ingest", data={"source": "MANUAL_TMA_FILE"}, files={"file": ("a.csv", _csv_bytes(GOOD), "text/csv")}, headers=key)
    assert res.status_code == 401


def test_a_revoked_sending_key_is_refused_at_once(client, db_session, bot_token, tma):
    client.post(f"/api/integration-clients/{tma['id']}/revoke", headers=auth_header(bot_token))
    assert _send(client, tma["api_key"]).status_code == 401
    assert db_session.query(ClimateRecord).count() == 0


# ------------------------------------------------------------------ accountability
def test_a_delivery_is_audited_without_the_key_and_the_analysts_are_told(client, db_session, tma):
    batch_id = _send(client, tma["api_key"]).json()["id"]
    entry = db_session.query(AuditLog).filter_by(action="INTEGRATION_INGEST").one()
    assert entry.user_id is None and entry.entity_id == batch_id
    assert "INGEST_TMA feed" in entry.details and "2 accepted" in entry.details
    assert entry.details_json["api_client_id"] == tma["id"] and entry.details_json["source"] == "API_KEY_TMA"
    secret = tma["api_key"].split("_", 2)[2]
    assert secret not in (entry.details or "") and secret not in str(entry.details_json)
    bot = db_session.query(User).filter_by(username="bot_feed").one()
    note = db_session.query(Notification).filter_by(user_id=bot.id).one()
    assert "INGEST_TMA feed" in note.message and "2 climate record" in note.message and note.related_entity_id == batch_id


# ------------------------------------------------------------------ the database
def test_the_database_refuses_an_unknown_scope(db_session):
    with pytest.raises(IntegrityError):
        _row(db_session, scope="WRITE_EVERYTHING")
    db_session.rollback()


def test_the_database_refuses_a_batch_with_both_a_person_and_a_key_as_uploader(db_session):
    _row(db_session)
    key, person = db_session.query(ApiClient).one(), db_session.query(User).one()
    db_session.add(ClimateIngestionBatch(source="API_KEY_TMA", uploaded_by_user_id=person.id, uploaded_by_api_client_id=key.id,
                                         records_received=0, records_accepted=0, records_rejected=0, records_duplicate=0, status="COMPLETED"))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()
