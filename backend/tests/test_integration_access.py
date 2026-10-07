"""
Read-only API keys for external systems (QGIS, ArcGIS, TMA, PMO, BSIS, RTIS).

What these tests pin down: only a BOT analyst can create a key (the System Administrator may not read supervisory
data, so a key would be a way round that rule), the key is shown once and never stored, a key reads exactly what the
analyst's dashboard shows and nothing else, it can never write or reach any other endpoint, every refusal looks the
same from outside while the audit log records the real reason, and the database itself protects the table.
"""
from datetime import datetime, timedelta

import pytest
from sqlalchemy.exc import IntegrityError

from app.core.integration_auth import KEY_PATTERN
from app.core.security import hash_refresh_token
from app.models.models import ApiClient, AuditLog, RoleEnum, SubmissionRecord
from tests.conftest import auth_header, login, make_institution, make_user
from tests.test_rbac_and_isolation import _seed_submission_for

REFUSAL = "Invalid, expired or revoked API key"


def _token(client, username):
    return login(client, username).json()["access_token"]


def _create(client, token, name="QGIS workstation", **extra):
    return client.post("/api/integration-clients", json={"name": name, **extra}, headers=auth_header(token))


def _by_key(key):
    return {"Authorization": f"Bearer {key}"}


@pytest.fixture
def bot_token(client, db_session):
    make_user(db_session, role=RoleEnum.BOT_USER, username="bot_keys")
    return _token(client, "bot_keys")


@pytest.fixture
def api_key(client, bot_token):
    res = _create(client, bot_token)
    assert res.status_code == 201
    return res.json()["api_key"]


# ------------------------------------------------------------------ who may create, list and revoke
def test_a_bot_analyst_creates_a_key_and_sees_it_once(client, db_session, bot_token):
    res = _create(client, bot_token, description="FSD GIS desk")
    assert res.status_code == 201
    body = res.json()
    assert KEY_PATTERN.match(body["api_key"]) and body["status"] == "ACTIVE" and body["key_prefix"] in body["api_key"]
    row = db_session.query(ApiClient).one()
    assert row.key_hash == hash_refresh_token(body["api_key"])      # only the hash is stored
    assert body["api_key"] not in repr(row.__dict__)


@pytest.mark.parametrize("who", ["admin_keys", "inst_keys"])
def test_only_a_bot_analyst_may_create_a_key(client, db_session, who):
    make_user(db_session, role=RoleEnum.SYSTEM_ADMIN, username="admin_keys")
    make_user(db_session, role=RoleEnum.INSTITUTION_USER, username="inst_keys")
    assert _create(client, _token(client, who)).status_code == 403
    assert db_session.query(ApiClient).count() == 0


def test_the_administrator_can_list_and_revoke_but_the_list_never_shows_a_key(client, db_session, bot_token, api_key):
    make_user(db_session, role=RoleEnum.SYSTEM_ADMIN, username="admin_keys")
    admin = _token(client, "admin_keys")
    listing = client.get("/api/integration-clients", headers=auth_header(admin))
    assert listing.status_code == 200 and len(listing.json()) == 1
    secret = api_key.split("_", 2)[2]
    assert "api_key" not in listing.text and "key_hash" not in listing.text and secret not in listing.text
    row_id = listing.json()[0]["id"]
    assert client.post(f"/api/integration-clients/{row_id}/revoke", headers=auth_header(admin)).json()["status"] == "REVOKED"
    assert client.get("/api/integration/whoami", headers=_by_key(api_key)).status_code == 401   # cut at once


def test_an_institution_user_cannot_list_or_revoke(client, db_session, bot_token, api_key):
    make_user(db_session, role=RoleEnum.INSTITUTION_USER, username="inst_keys")
    token = _token(client, "inst_keys")
    row_id = db_session.query(ApiClient).one().id
    assert client.get("/api/integration-clients", headers=auth_header(token)).status_code == 403
    assert client.post(f"/api/integration-clients/{row_id}/revoke", headers=auth_header(token)).status_code == 403


def test_a_key_lives_one_to_365_days_and_180_by_default(client, bot_token):
    assert _create(client, bot_token, name="a", valid_days=0).status_code == 422
    assert _create(client, bot_token, name="b", valid_days=366).status_code == 422
    body = _create(client, bot_token, name="c").json()
    lifetime = datetime.fromisoformat(body["expires_at"]) - datetime.fromisoformat(body["created_at"])
    assert 179 <= lifetime.days <= 180


def test_two_live_keys_cannot_share_a_name_but_a_revoked_name_can_be_reused(client, bot_token):
    first = _create(client, bot_token).json()
    assert _create(client, bot_token, name="qgis WORKSTATION").status_code == 409     # case-insensitive
    client.post(f"/api/integration-clients/{first['id']}/revoke", headers=auth_header(bot_token))
    assert _create(client, bot_token).status_code == 201


def test_revoking_twice_or_an_unknown_key_is_refused(client, bot_token):
    first = _create(client, bot_token).json()
    assert client.post(f"/api/integration-clients/{first['id']}/revoke", headers=auth_header(bot_token)).status_code == 200
    assert client.post(f"/api/integration-clients/{first['id']}/revoke", headers=auth_header(bot_token)).status_code == 409
    assert client.post("/api/integration-clients/nope/revoke", headers=auth_header(bot_token)).status_code == 404


# ------------------------------------------------------------------ what a key can and cannot do
@pytest.mark.parametrize("headers_for", [lambda k: _by_key(k), lambda k: {"X-API-Key": k}])
def test_a_key_works_in_either_header(client, api_key, headers_for):
    res = client.get("/api/integration/whoami", headers=headers_for(api_key))
    assert res.status_code == 200 and res.json()["name"] == "QGIS workstation" and "read-only" in res.json()["access"]


def test_a_key_is_read_only_and_works_nowhere_else(client, api_key):
    assert client.post("/api/integration/kpi-summary", headers=_by_key(api_key)).status_code == 405
    assert client.delete("/api/integration/kpi-summary", headers=_by_key(api_key)).status_code == 405
    for path in ("/api/analytics/kpi-summary", "/api/submissions", "/api/integration-clients", "/api/audit-logs"):
        assert client.get(path, headers=_by_key(api_key)).status_code == 401, path


def test_a_normal_sign_in_token_is_not_accepted_on_the_integration_endpoints(client, bot_token):
    assert client.get("/api/integration/whoami", headers=auth_header(bot_token)).status_code == 401


@pytest.mark.parametrize("path", [
    "kpi-summary", "hazard-exposure", "combined-climate-financial-exposure", "map-points", "exposure-points",
])
def test_a_key_sees_exactly_what_a_bot_analyst_sees(client, db_session, bot_token, api_key, path):
    _seed_submission_for(db_session, make_institution(db_session))
    via_key = client.get(f"/api/integration/{path}", headers=_by_key(api_key))
    via_user = client.get(f"/api/analytics/{path}", headers=auth_header(bot_token))
    assert via_key.status_code == 200 and via_user.status_code == 200
    assert via_key.json() == via_user.json()


def test_an_unknown_hazard_filter_is_refused_for_a_key_too(client, api_key):
    assert client.get("/api/integration/hazard-exposure?filter_hazard_type=Earthquake", headers=_by_key(api_key)).status_code == 422


def test_the_geojson_has_one_feature_per_point_with_longitude_first(client, db_session, api_key):
    sub = _seed_submission_for(db_session, make_institution(db_session))
    rec = db_session.query(SubmissionRecord).filter_by(submission_id=sub.id).first()
    rec.is_valid = True
    rec.loan_amount_tzs, rec.collateral_value_tzs = 1000.0, 500.0
    rec.loan_latitude, rec.loan_longitude = -6.8, 39.2
    rec.collateral_latitude, rec.collateral_longitude = -3.4, 37.3
    db_session.commit()
    res = client.get("/api/integration/exposure-points.geojson", headers=_by_key(api_key))
    assert res.status_code == 200 and res.headers["content-type"].startswith("application/geo+json")
    features = res.json()["features"]
    assert res.json()["type"] == "FeatureCollection" and sorted(f["properties"]["kind"] for f in features) == ["collateral", "loan"]
    loan = next(f for f in features if f["properties"]["kind"] == "loan")
    assert loan["geometry"] == {"type": "Point", "coordinates": [39.2, -6.8]} and loan["properties"]["amount_tzs"] == 1000.0


def test_the_geojson_is_empty_not_an_error_when_there_are_no_points(client, api_key):
    res = client.get("/api/integration/exposure-points.geojson", headers=_by_key(api_key))
    assert res.status_code == 200 and res.json() == {"type": "FeatureCollection", "features": []}


# ------------------------------------------------------------------ refusals look the same; the audit log knows why
@pytest.mark.parametrize("reason", ["wrong secret", "unknown key", "malformed", "missing"])
def test_every_kind_of_refusal_gives_the_same_answer_and_is_audited_with_its_real_reason(client, db_session, api_key, reason):
    good_prefix = api_key.split("_")[1]
    headers = {
        "wrong secret": _by_key(api_key[:-1] + ("A" if api_key[-1] != "A" else "B")),
        "unknown key": _by_key("cdrk_" + "a" * 10 + "_" + "b" * 43),
        "malformed": _by_key("not-a-key"),
        "missing": {},
    }[reason]
    res = client.get("/api/integration/whoami", headers=headers)
    assert res.status_code == 401 and res.json()["detail"] == REFUSAL
    row = db_session.query(AuditLog).filter_by(action="INTEGRATION_AUTH_FAILED").one()
    assert row.details_json["reason"] in (reason, "missing or malformed")
    if reason == "wrong secret":
        assert row.details_json["key_prefix"] == good_prefix
    secret = api_key.split("_", 2)[2]
    assert secret not in (row.details or "") and secret not in str(row.details_json)


def test_an_expired_key_is_refused_and_a_revoked_one_too(client, db_session, bot_token, api_key):
    row = db_session.query(ApiClient).one()
    row.created_at, row.expires_at = datetime.utcnow() - timedelta(days=2), datetime.utcnow() - timedelta(days=1)
    db_session.commit()
    res = client.get("/api/integration/whoami", headers=_by_key(api_key))
    assert res.status_code == 401 and res.json()["detail"] == REFUSAL
    assert db_session.query(AuditLog).filter_by(action="INTEGRATION_AUTH_FAILED").one().details_json["reason"] == "expired"
    assert _create(client, bot_token, name="second").status_code == 201


def test_every_successful_read_is_audited_without_the_key_and_marks_the_key_as_used(client, db_session, api_key):
    client.get("/api/integration/whoami", headers=_by_key(api_key))
    client.get("/api/integration/kpi-summary?filter_region=Dodoma", headers=_by_key(api_key))
    reads = db_session.query(AuditLog).filter_by(action="INTEGRATION_READ").all()
    row = db_session.query(ApiClient).one()
    assert len(reads) == 2 and all(r.entity_id == row.id for r in reads)
    assert any("filter_region=Dodoma" in (r.details or "") for r in reads)
    secret = api_key.split("_", 2)[2]
    assert all(secret not in (r.details or "") and secret not in str(r.details_json) for r in reads)
    assert row.last_used_at is not None


def test_creating_and_revoking_a_key_are_audited_with_the_acting_user(client, db_session, bot_token):
    made = _create(client, bot_token).json()
    client.post(f"/api/integration-clients/{made['id']}/revoke", headers=auth_header(bot_token))
    actions = {a.action: a for a in db_session.query(AuditLog).filter(AuditLog.action.like("INTEGRATION_CLIENT_%")).all()}
    assert set(actions) == {"INTEGRATION_CLIENT_CREATED", "INTEGRATION_CLIENT_REVOKED"}
    assert all(a.user_id is not None and made["api_key"] not in str(a.details_json) + (a.details or "") for a in actions.values())


# ------------------------------------------------------------------ the database protects the table itself
def _row(db, **over):
    user = make_user(db, role=RoleEnum.BOT_USER, username=over.pop("username", "bot_db"))
    now = datetime.utcnow()
    values = dict(name="n", key_prefix="aaaaaaaaaa", key_hash="0" * 64, created_by_user_id=user.id,
                  created_at=now, expires_at=now + timedelta(days=1))
    values.update(over)
    db.add(ApiClient(**values))
    db.commit()


@pytest.mark.parametrize("override", [
    dict(expires_at=datetime.utcnow() - timedelta(days=1)),          # expires before it was created
    dict(name="   "),                                                # blank name
    dict(key_hash="short"),                                          # not a SHA-256 hex digest
    dict(revoked_by_user_id="someone"),                              # a revoker without a revocation
])
def test_the_database_refuses_a_row_that_breaks_its_rules(db_session, override):
    if override.get("revoked_by_user_id"):
        override = dict(revoked_by_user_id=make_user(db_session, role=RoleEnum.BOT_USER, username="other_bot").id)
    with pytest.raises(IntegrityError):
        _row(db_session, **override)
    db_session.rollback()


def test_the_database_refuses_a_second_row_with_the_same_prefix_or_the_same_live_name(db_session):
    _row(db_session)
    with pytest.raises(IntegrityError):
        _row(db_session, username="bot_db2", name="other")             # same prefix
    db_session.rollback()
    with pytest.raises(IntegrityError):
        _row(db_session, username="bot_db3", key_prefix="bbbbbbbbbb")  # same live name
    db_session.rollback()
    _row(db_session, username="bot_db4", key_prefix="cccccccccc", revoked_at=datetime.utcnow())   # a revoked row never clashes
    _row(db_session, username="bot_db5", key_prefix="dddddddddd", revoked_at=datetime.utcnow())
