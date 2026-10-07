"""
The audit viewer offers drop-down filters. Their values come from the audit log itself, so a
filter can only ever name something that exists (a typed filter that matches nothing looks
exactly like an empty log).
"""
from app.models.models import RoleEnum
from app.services.audit_service import record_audit
from tests.conftest import auth_header, login, make_user


def _seed(db):
    admin = make_user(db, role=RoleEnum.SYSTEM_ADMIN, username="adm_opts")
    bot = make_user(db, role=RoleEnum.BOT_USER, username="bot_opts")
    record_audit(db, admin.id, "USER_CREATED", "User", bot.id, "created")
    record_audit(db, bot.id, "SUBMISSION_CREATED", "Submission", "s1", "uploaded")
    record_audit(db, bot.id, "SUBMISSION_CREATED", "Submission", "s2", "uploaded")
    record_audit(db, None, "LOGIN_FAILED", None, None, "unknown user")
    return admin, bot


def _admin_get(client, path):
    token = login(client, "adm_opts").json()["access_token"]
    return client.get(path, headers=auth_header(token))


def test_options_list_each_value_once_and_in_order(client, db_session):
    _seed(db_session)
    body = _admin_get(client, "/api/audit-logs/filter-options").json()
    assert {"USER_CREATED", "SUBMISSION_CREATED", "LOGIN_FAILED"} <= set(body["actions"])
    assert body["actions"] == sorted(set(body["actions"]))
    assert {"User", "Submission"} <= set(body["entity_types"]) and body["entity_types"] == sorted(set(body["entity_types"]))
    names = [u["username"] for u in body["users"]]
    assert {"adm_opts", "bot_opts"} <= set(names) and names == sorted(set(names))


def test_no_empty_values_are_offered(client, db_session):
    _seed(db_session)
    body = _admin_get(client, "/api/audit-logs/filter-options").json()
    assert all(body["actions"]) and all(body["entity_types"])        # the entry with no entity adds none
    assert all(u["id"] for u in body["users"])                       # the entry with no user adds none


def test_every_offered_value_works_as_a_filter(client, db_session):
    _, bot = _seed(db_session)
    body = _admin_get(client, "/api/audit-logs/filter-options").json()
    assert "SUBMISSION_CREATED" in body["actions"] and any(u["id"] == bot.id for u in body["users"])
    page = _admin_get(client, f"/api/audit-logs?action=SUBMISSION_CREATED&entity_type=Submission&user_id={bot.id}").json()
    assert page["total"] == 2


def test_only_the_administrator_may_read_the_options(client, db_session):
    _seed(db_session)
    token = login(client, "bot_opts").json()["access_token"]
    assert client.get("/api/audit-logs/filter-options", headers=auth_header(token)).status_code == 403
    assert client.get("/api/audit-logs/filter-options").status_code == 401
