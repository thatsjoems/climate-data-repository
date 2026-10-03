"""
Password policy tests - Solution 2 (secure authentication, strong passwords).
"""
from app.models.models import RoleEnum
from tests.conftest import make_institution, make_user, login, auth_header, DEFAULT_PASSWORD


def test_weak_password_rejected_on_user_creation(client, db_session):
    inst = make_institution(db_session)
    make_user(db_session, role=RoleEnum.SYSTEM_ADMIN, username="admin1")
    token = login(client, "admin1").json()["access_token"]

    res = client.post(
        "/api/users",
        json={
            "full_name": "New Person", "username": "newperson", "email": "n@example.com",
            "password": "short", "role": "INSTITUTION_USER", "institution_id": inst.id,
        },
        headers=auth_header(token),
    )
    assert res.status_code == 400
    # A valid institution is supplied above specifically so this 400 can only
    # be the password-strength check - not the separate (and separately
    # tested, in test_user_creation_validation.py) role/institution check,
    # which runs first in create_user() and would otherwise produce the same
    # status code for an unrelated reason, masking a real regression here.
    assert "password" in res.json()["detail"].lower()


def test_strong_password_accepted_on_user_creation(client, db_session):
    inst = make_institution(db_session)
    make_user(db_session, role=RoleEnum.SYSTEM_ADMIN, username="admin1")
    token = login(client, "admin1").json()["access_token"]

    res = client.post(
        "/api/users",
        json={
            "full_name": "New Person", "username": "newperson", "email": "n@example.com",
            "password": "Str0ng!Passw0rd", "role": "INSTITUTION_USER", "institution_id": inst.id,
        },
        headers=auth_header(token),
    )
    assert res.status_code == 201
    # Admin-issued credentials must force a change on first login
    assert res.json()["must_change_password"] is True


def test_change_password_requires_correct_current_password(client, db_session):
    make_user(db_session, username="alice")
    token = login(client, "alice").json()["access_token"]

    res = client.post(
        "/api/auth/change-password",
        json={"current_password": "wrong-password", "new_password": "NewStr0ng!Pass"},
        headers=auth_header(token),
    )
    assert res.status_code == 400


def test_change_password_rejects_weak_new_password(client, db_session):
    make_user(db_session, username="alice")
    token = login(client, "alice").json()["access_token"]

    res = client.post(
        "/api/auth/change-password",
        json={"current_password": DEFAULT_PASSWORD, "new_password": "weak"},
        headers=auth_header(token),
    )
    assert res.status_code == 400


def test_change_password_succeeds_with_strong_new_password(client, db_session):
    make_user(db_session, username="alice")
    token = login(client, "alice").json()["access_token"]

    res = client.post(
        "/api/auth/change-password",
        json={"current_password": DEFAULT_PASSWORD, "new_password": "NewStr0ng!Pass"},
        headers=auth_header(token),
    )
    assert res.status_code == 200

    # Old password must no longer work; new one must
    assert login(client, "alice", password=DEFAULT_PASSWORD).status_code == 401
    assert login(client, "alice", password="NewStr0ng!Pass").status_code == 200
