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


# ---------------------------------------------------------------------------------------------------------------------------------------------------
# Stricter policy for the Bank's staff and a refusal of common passwords (app/core/password_policy.py). Found by the penetration-test preparation
# (docs/PENTEST_CHECKLIST.md, O4): the minimum was 8 characters for everyone and "Admin1234!" met every rule.
import pytest

from app.core.password_policy import generate_secure_temp_password, min_length_for, validate_password_strength
from app.services.account_recovery import RecoveryError, reset_password

STAFF = "BOT_USER"
INSTITUTION = "INSTITUTION_USER"


def test_the_minimum_length_depends_on_whose_account_it_is():
    assert min_length_for("INSTITUTION_USER") == 8
    assert min_length_for("BOT_USER") == min_length_for("SYSTEM_ADMIN") == 12
    assert min_length_for(None) == 12                                   # an unknown role gets the stricter rule


@pytest.mark.parametrize("password,role", [
    ("lantern-river-orange-road-72", STAFF), ("Quiet-Lake!2026", STAFF), ("Str0ng!Passw0rd", STAFF), ("N3w!Passw0rd-Chosen", STAFF),
    ("Dodoma-Rain-Season-2026", STAFF), ("correct horse battery staple 7!", STAFF), ("Tanzania-Bank-Climate-Data-9!", STAFF), ("Quiet-Lake!2", STAFF),
    ("Rain!4Tz", INSTITUTION),
])
def test_good_passwords_are_accepted(password, role):
    assert validate_password_strength(password, role=role) == []


@pytest.mark.parametrize("password,role", [
    ("Admin1234!", INSTITUTION), ("Admin1234!", STAFF), ("Password2026!", STAFF), ("P@ssw0rd!2026", STAFF), ("Passw0rd!23", INSTITUTION), ("Welcome@123", INSTITUTION),
    ("Qwerty123456!", STAFF), ("Tanzania2026!", STAFF), ("Bank0fTanzania!1", STAFF), ("MyPassword2026!", STAFF), ("Adm1n2026!", INSTITUTION),
    ("1Password!", INSTITUTION), ("pass-word-1!", INSTITUTION), ("aaaaaaaaaaaa1!", STAFF),
])
def test_a_common_password_is_refused_even_when_it_has_a_letter_a_digit_and_a_symbol(password, role):
    assert any("common" in p for p in validate_password_strength(password, role=role))


@pytest.mark.parametrize("password,role,needle", [
    ("Quiet-Lk!26", STAFF, "at least 12"), ("short1!", INSTITUTION, "at least 8"), ("NoDigitsHere!!", STAFF, "number"), ("NoSymbols12345", STAFF, "special"),
    ("1234567890!!", STAFF, "letter"),
])
def test_each_unmet_rule_is_named(password, role, needle):
    assert any(needle in p for p in validate_password_strength(password, role=role))


def test_the_username_may_not_be_in_the_password_unless_it_is_too_short_to_matter():
    assert any("username" in p for p in validate_password_strength("Analyst1-Secure-2026", role=STAFF, username="analyst1"))
    assert validate_password_strength("Quiet-Lake!2026", role=STAFF, username="adm") == []        # under 4 characters: not compared


def test_temporary_passwords_always_meet_the_strictest_rule():
    assert all(validate_password_strength(generate_secure_temp_password(), role=STAFF) == [] for _ in range(500))


def _create(client, token, **overrides):
    body = {"full_name": "New Person", "username": "newperson", "email": "n@example.com", "password": "Quiet-Lake!2026", "role": "BOT_USER"}
    body.update(overrides)
    return client.post("/api/users", json=body, headers=auth_header(token))


def test_a_staff_account_needs_12_characters_but_an_institution_account_keeps_8(client, db_session):
    inst = make_institution(db_session)
    make_user(db_session, role=RoleEnum.SYSTEM_ADMIN, username="admin1")
    token = login(client, "admin1").json()["access_token"]
    short_staff = _create(client, token, password="Quiet-Lk!26")                                     # 11 characters
    assert short_staff.status_code == 400 and "at least 12" in short_staff.json()["detail"]
    assert _create(client, token, password="Quiet-Lake!26").status_code == 201                       # 13 characters
    assert _create(client, token, username="bankuser", email="b@example.com", password="Rain!4Tz", role="INSTITUTION_USER", institution_id=inst.id).status_code == 201


def test_a_common_password_is_refused_when_creating_an_account(client, db_session):
    inst = make_institution(db_session)
    make_user(db_session, role=RoleEnum.SYSTEM_ADMIN, username="admin1")
    token = login(client, "admin1").json()["access_token"]
    res = _create(client, token, password="Admin1234!", role="INSTITUTION_USER", institution_id=inst.id)
    assert res.status_code == 400 and "common" in res.json()["detail"]


def test_a_staff_member_changing_their_own_password_meets_the_same_rule(client, db_session):
    make_user(db_session, role=RoleEnum.BOT_USER, username="analyst_pw")
    token = login(client, "analyst_pw").json()["access_token"]

    def change(new):
        return client.post("/api/auth/change-password", json={"current_password": DEFAULT_PASSWORD, "new_password": new}, headers=auth_header(token))
    short = change("Short1!pw")
    assert short.status_code == 400 and "at least 12" in short.json()["detail"]
    common = change("Password2026!")
    assert common.status_code == 400 and "common" in common.json()["detail"]
    assert change("Quiet-Lake!2026").status_code == 200


def test_a_password_set_from_the_server_meets_the_rule_for_that_persons_role(db_session):
    make_user(db_session, role=RoleEnum.SYSTEM_ADMIN, username="forgetful_admin")
    with pytest.raises(RecoveryError, match="at least 12"):
        reset_password(db_session, "forgetful_admin", "Quiet-Lk!26")
    with pytest.raises(RecoveryError, match="common"):
        reset_password(db_session, "forgetful_admin", "Welcome@2026")
    reset_password(db_session, "forgetful_admin", "Quiet-Lake!2026")
