"""
Role/institution consistency on user creation (found during an admin-side
review). UserCreate previously accepted any combination: an INSTITUTION_USER
with no institution (a silently broken account with no tenant scope) or a
BOT_USER/SYSTEM_ADMIN carrying an institution (never used, but misleading).
"""
from app.models.models import RoleEnum
from tests.conftest import make_institution, make_user, login, auth_header


def _admin_token(client, db_session):
    make_user(db_session, role=RoleEnum.SYSTEM_ADMIN, username="admin1")
    return login(client, "admin1").json()["access_token"]


def test_institution_user_without_an_institution_is_rejected(client, db_session):
    token = _admin_token(client, db_session)
    res = client.post(
        "/api/users",
        json={"full_name": "New Person", "username": "newperson", "email": "n@example.com",
              "password": "Passw0rd!23", "role": "INSTITUTION_USER"},
        headers=auth_header(token),
    )
    assert res.status_code == 400
    assert "must be assigned an institution" in res.json()["detail"].lower()


def test_bot_user_with_an_institution_is_rejected(client, db_session):
    inst = make_institution(db_session)
    token = _admin_token(client, db_session)
    res = client.post(
        "/api/users",
        json={"full_name": "New Analyst", "username": "newanalyst", "email": "a@example.com",
              "password": "Passw0rd!23", "role": "BOT_USER", "institution_id": inst.id},
        headers=auth_header(token),
    )
    assert res.status_code == 400
    assert "only an institution user" in res.json()["detail"].lower()


def test_system_admin_with_an_institution_is_rejected(client, db_session):
    inst = make_institution(db_session)
    token = _admin_token(client, db_session)
    res = client.post(
        "/api/users",
        json={"full_name": "New Admin", "username": "newadmin", "email": "ad@example.com",
              "password": "Passw0rd!23", "role": "SYSTEM_ADMIN", "institution_id": inst.id},
        headers=auth_header(token),
    )
    assert res.status_code == 400


def test_institution_user_with_a_nonexistent_institution_is_rejected(client, db_session):
    token = _admin_token(client, db_session)
    res = client.post(
        "/api/users",
        json={"full_name": "New Person", "username": "newperson", "email": "n@example.com",
              "password": "Passw0rd!23", "role": "INSTITUTION_USER", "institution_id": "does-not-exist"},
        headers=auth_header(token),
    )
    assert res.status_code == 400


def test_institution_user_with_a_valid_institution_is_accepted(client, db_session):
    inst = make_institution(db_session)
    token = _admin_token(client, db_session)
    res = client.post(
        "/api/users",
        json={"full_name": "New Person", "username": "newperson", "email": "n@example.com",
              "password": "Passw0rd!23", "role": "INSTITUTION_USER", "institution_id": inst.id},
        headers=auth_header(token),
    )
    assert res.status_code == 201
    assert res.json()["institution_id"] == inst.id


def test_bot_user_with_no_institution_is_accepted(client, db_session):
    token = _admin_token(client, db_session)
    res = client.post(
        "/api/users",
        json={"full_name": "New Analyst", "username": "newanalyst", "email": "a@example.com",
              "password": "Passw0rd!23", "role": "BOT_USER"},
        headers=auth_header(token),
    )
    assert res.status_code == 201
    assert res.json()["institution_id"] is None
