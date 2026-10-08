"""
Two-step sign-in, end to end: who must enrol, enrolment, the second step, recovery codes, lock-out, and the administrator's reset.

Time is controlled (the 30-second step is set by the test), so nothing here depends on how fast the tests run.
"""
import pytest
from sqlalchemy.exc import IntegrityError

from app.core import mfa
from app.core.config import settings
from app.core.mfa import totp_at
from app.models.models import AuditLog, Notification, RefreshToken, RoleEnum, User
from tests.conftest import auth_header, login, make_user

START = 5_000_000


class _Clock:
    step = START


@pytest.fixture
def clock(monkeypatch):
    c = _Clock()
    monkeypatch.setattr(mfa, "current_step", lambda now=None: c.step)
    return c


@pytest.fixture
def required(monkeypatch):
    monkeypatch.setattr(settings, "MFA_REQUIRED", True)


def _bot(db, name="analyst1"):
    make_user(db, role=RoleEnum.BOT_USER, username=name)
    return name


def _enrol(client, username, clock):
    """Password step, then enrolment. Returns (secret, the confirm response)."""
    token = login(client, username).json()["mfa_token"]
    secret = client.post("/api/auth/mfa/setup/begin", json={"mfa_token": token}).json()["secret"]
    return secret, client.post("/api/auth/mfa/setup/confirm", json={"mfa_token": token, "code": totp_at(secret, clock.step)})


def _verify(client, token, **body):
    return client.post("/api/auth/mfa/verify", json={"mfa_token": token, **body})


def _actions(db):
    return [a.action for a in db.query(AuditLog).all()]


def _wrong_code(secret, clock):
    valid = {totp_at(secret, clock.step + d) for d in (-1, 0, 1)}
    return next(c for c in ("000000", "111111", "222222", "333333") if c not in valid)


# ------------------------------------------------------------------ who has to use it
def test_without_the_requirement_a_bot_analyst_signs_in_as_before(client, db_session):
    body = login(client, _bot(db_session)).json()
    assert body["access_token"] and body["refresh_token"] and not body["mfa_required"] and not body["mfa_setup_required"]


@pytest.mark.parametrize("role", [RoleEnum.BOT_USER, RoleEnum.SYSTEM_ADMIN])
def test_when_required_the_banks_staff_must_enrol_before_they_get_any_token(client, db_session, required, role):
    make_user(db_session, role=role, username="staff1")
    body = login(client, "staff1").json()
    assert body["mfa_setup_required"] is True and body["mfa_token"] and body["access_token"] is None and body["refresh_token"] is None


def test_when_required_an_institution_user_is_not_asked(client, db_session, required):
    make_user(db_session, role=RoleEnum.INSTITUTION_USER, username="inst1")
    body = login(client, "inst1").json()
    assert body["access_token"] and not body["mfa_setup_required"]


def test_a_step_token_is_not_an_access_token(client, db_session, required):
    token = login(client, _bot(db_session)).json()["mfa_token"]
    assert client.get("/api/auth/me", headers=auth_header(token)).status_code == 401


# ------------------------------------------------------------------ enrolment
def test_enrolment_turns_it_on_stores_the_secret_encrypted_and_gives_ten_recovery_codes(client, db_session, required, clock):
    name = _bot(db_session)
    token = login(client, name).json()["mfa_token"]
    begin = client.post("/api/auth/mfa/setup/begin", json={"mfa_token": token}).json()
    secret = begin["secret"]
    assert begin["account"] == name and secret in begin["otpauth_uri"]

    assert client.post("/api/auth/mfa/setup/confirm", json={"mfa_token": token, "code": _wrong_code(secret, clock)}).status_code == 401
    assert db_session.query(User).filter_by(username=name).one().mfa_enabled is False        # a wrong code enrols nobody

    done = client.post("/api/auth/mfa/setup/confirm", json={"mfa_token": token, "code": totp_at(secret, clock.step)})
    body = done.json()
    assert done.status_code == 200 and body["access_token"] and len(body["recovery_codes"]) == 10 and body["user"]["mfa_enabled"] is True
    row = db_session.query(User).filter_by(username=name).one()
    assert row.mfa_enabled and row.mfa_last_step == clock.step and row.mfa_enrolled_at is not None
    assert secret not in row.mfa_secret_encrypted and mfa.decrypt_secret(row.mfa_secret_encrypted) == secret
    assert not any(code in row.mfa_recovery_hashes or code.replace("-", "") in row.mfa_recovery_hashes for code in body["recovery_codes"])
    assert "MFA_ENABLED" in _actions(db_session)
    assert client.post("/api/auth/mfa/setup/begin", json={"mfa_token": token}).status_code == 409   # already set up


# ------------------------------------------------------------------ the second step
def test_after_enrolment_the_password_alone_gives_no_token_and_the_code_does(client, db_session, required, clock):
    name = _bot(db_session)
    secret, _ = _enrol(client, name, clock)
    logins_before = _actions(db_session).count("LOGIN")

    first = login(client, name).json()
    assert first["mfa_required"] is True and first["access_token"] is None
    assert _actions(db_session).count("LOGIN") == logins_before          # nothing is logged as a sign-in until the second step is done

    clock.step += 1
    done = _verify(client, first["mfa_token"], code=totp_at(secret, clock.step))
    assert done.status_code == 200 and done.json()["access_token"]
    assert _actions(db_session).count("LOGIN") == logins_before + 1
    assert client.get("/api/auth/me", headers=auth_header(done.json()["access_token"])).json()["mfa_enabled"] is True


def test_a_code_cannot_be_used_twice(client, db_session, required, clock):
    name = _bot(db_session)
    secret, _ = _enrol(client, name, clock)
    clock.step += 1
    code = totp_at(secret, clock.step)
    assert _verify(client, login(client, name).json()["mfa_token"], code=code).status_code == 200
    assert _verify(client, login(client, name).json()["mfa_token"], code=code).status_code == 401


def test_wrong_codes_run_into_the_same_lock_out_as_wrong_passwords(client, db_session, required, clock):
    name = _bot(db_session)
    secret, _ = _enrol(client, name, clock)
    token = login(client, name).json()["mfa_token"]
    for _ in range(settings.MAX_FAILED_LOGIN_ATTEMPTS):
        assert _verify(client, token, code=_wrong_code(secret, clock)).status_code == 401
    clock.step += 1
    assert _verify(client, token, code=totp_at(secret, clock.step)).status_code == 403            # even the right code, while locked
    assert {"MFA_FAILED", "LOGIN_LOCKED"} <= set(_actions(db_session))


def test_a_right_password_does_not_reset_the_count_of_wrong_codes(client, db_session, required, clock):
    name = _bot(db_session)
    secret, _ = _enrol(client, name, clock)
    for _ in range(settings.MAX_FAILED_LOGIN_ATTEMPTS - 1):
        assert _verify(client, login(client, name).json()["mfa_token"], code=_wrong_code(secret, clock)).status_code == 401
    assert db_session.query(User).filter_by(username=name).one().failed_login_attempts == settings.MAX_FAILED_LOGIN_ATTEMPTS - 1


def test_a_missing_code_is_a_clear_error(client, db_session, required, clock):
    name = _bot(db_session)
    _enrol(client, name, clock)
    assert _verify(client, login(client, name).json()["mfa_token"]).status_code == 422


# ------------------------------------------------------------------ recovery codes
def test_a_recovery_code_signs_in_once_and_the_person_is_told(client, db_session, required, clock):
    name = _bot(db_session)
    _, done = _enrol(client, name, clock)
    codes = done.json()["recovery_codes"]
    assert _verify(client, login(client, name).json()["mfa_token"], recovery_code=codes[0]).status_code == 200
    assert _verify(client, login(client, name).json()["mfa_token"], recovery_code=codes[0]).status_code == 401
    assert _verify(client, login(client, name).json()["mfa_token"], recovery_code=codes[1].lower()).status_code == 200
    assert "MFA_RECOVERY_CODE_USED" in _actions(db_session)
    uid = db_session.query(User).filter_by(username=name).one().id
    assert db_session.query(Notification).filter_by(user_id=uid, type="SECURITY").count() == 2


def test_new_recovery_codes_need_a_current_code_and_replace_the_old_ones(client, db_session, required, clock):
    name = _bot(db_session)
    secret, done = _enrol(client, name, clock)
    old_codes, access = done.json()["recovery_codes"], done.json()["access_token"]
    assert client.post("/api/auth/mfa/recovery-codes", json={"code": _wrong_code(secret, clock)}, headers=auth_header(access)).status_code == 401
    clock.step += 1
    res = client.post("/api/auth/mfa/recovery-codes", json={"code": totp_at(secret, clock.step)}, headers=auth_header(access))
    new_codes = res.json()["recovery_codes"]
    assert res.status_code == 200 and len(new_codes) == 10 and not set(new_codes) & set(old_codes)
    assert _verify(client, login(client, name).json()["mfa_token"], recovery_code=old_codes[0]).status_code == 401
    assert _verify(client, login(client, name).json()["mfa_token"], recovery_code=new_codes[0]).status_code == 200
    assert "MFA_RECOVERY_CODES_REGENERATED" in _actions(db_session)


def test_new_recovery_codes_cannot_be_asked_for_without_two_step_sign_in(client, db_session):
    token = login(client, _bot(db_session)).json()["access_token"]
    assert client.post("/api/auth/mfa/recovery-codes", json={"code": "123456"}, headers=auth_header(token)).status_code == 409


# ------------------------------------------------------------------ tokens and stored values
def test_a_step_token_works_only_for_its_own_step(client, db_session, required, clock):
    enrolled = _bot(db_session, "enrolled1")
    _enrol(client, enrolled, clock)
    code_token = login(client, enrolled).json()["mfa_token"]
    assert client.post("/api/auth/mfa/setup/begin", json={"mfa_token": code_token}).status_code == 401      # a code token cannot start enrolment
    fresh = _bot(db_session, "fresh1")
    setup_token = login(client, fresh).json()["mfa_token"]
    assert _verify(client, setup_token, code="123456").status_code == 401                                    # a setup token cannot answer a code


def test_an_expired_step_token_is_refused(client, db_session, required, monkeypatch):
    monkeypatch.setattr(mfa, "STEP_TOKEN_MINUTES", -1)
    token = login(client, _bot(db_session)).json()["mfa_token"]
    assert client.post("/api/auth/mfa/setup/begin", json={"mfa_token": token}).status_code == 401


def test_someone_who_enrolled_keeps_using_it_even_if_the_requirement_is_switched_off(client, db_session, required, clock, monkeypatch):
    name = _bot(db_session)
    _enrol(client, name, clock)
    monkeypatch.setattr(settings, "MFA_REQUIRED", False)
    assert login(client, name).json()["mfa_required"] is True


def test_a_damaged_secret_refuses_the_sign_in_it_does_not_crash(client, db_session, required, clock):
    name = _bot(db_session)
    _enrol(client, name, clock)
    row = db_session.query(User).filter_by(username=name).one()
    row.mfa_secret_encrypted = "garbage"
    db_session.commit()
    assert _verify(client, login(client, name).json()["mfa_token"], code="123456").status_code == 401


def test_nothing_secret_is_ever_returned(client, db_session, required, clock, monkeypatch):
    make_user(db_session, role=RoleEnum.SYSTEM_ADMIN, username="admin_x")
    name = _bot(db_session)
    _, done = _enrol(client, name, clock)
    me = client.get("/api/auth/me", headers=auth_header(done.json()["access_token"])).json()
    monkeypatch.setattr(settings, "MFA_REQUIRED", False)      # the administrator would have to enrol too; this check is about what is returned
    admin_token = login(client, "admin_x").json()["access_token"]
    users = client.get("/api/users", headers=auth_header(admin_token)).json()
    for blob in [me] + users:
        assert not [k for k in blob if any(w in k for w in ("secret", "recovery", "hash", "last_step"))]


def test_the_database_requires_a_secret_for_an_enrolled_user(db_session):
    make_user(db_session, role=RoleEnum.BOT_USER, username="plain1")
    row = db_session.query(User).filter_by(username="plain1").one()
    row.mfa_enabled, row.mfa_secret_encrypted = True, None
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


# ------------------------------------------------------------------ the administrator's reset
def _admin_token(client, db_session):
    make_user(db_session, role=RoleEnum.SYSTEM_ADMIN, username="admin_r")
    return login(client, "admin_r").json()["access_token"]


def test_an_administrator_can_reset_someones_two_step_sign_in_and_it_is_recorded(client, db_session, required, clock, monkeypatch):
    name = _bot(db_session)
    _enrol(client, name, clock)
    monkeypatch.setattr(settings, "MFA_REQUIRED", False)
    admin_token = _admin_token(client, db_session)
    monkeypatch.setattr(settings, "MFA_REQUIRED", True)
    row = db_session.query(User).filter_by(username=name).one()

    res = client.post(f"/api/users/{row.id}/mfa/reset", headers=auth_header(admin_token))
    assert res.status_code == 200 and res.json()["mfa_enabled"] is False
    db_session.refresh(row)
    assert not row.mfa_enabled and row.mfa_secret_encrypted is None and row.mfa_recovery_hashes is None and row.mfa_last_step is None
    assert all(t.revoked_at is not None for t in db_session.query(RefreshToken).filter_by(user_id=row.id).all())
    admin = db_session.query(User).filter_by(username="admin_r").one()
    assert db_session.query(AuditLog).filter_by(action="MFA_RESET", user_id=admin.id).count() == 1
    assert db_session.query(Notification).filter_by(user_id=row.id, type="SECURITY").count() == 1
    assert login(client, name).json()["mfa_setup_required"] is True                          # asked to enrol again


def test_the_reset_has_safeguards(client, db_session, monkeypatch):
    admin_token = _admin_token(client, db_session)
    admin = db_session.query(User).filter_by(username="admin_r").one()
    assert client.post(f"/api/users/{admin.id}/mfa/reset", headers=auth_header(admin_token)).status_code == 400    # not your own
    assert client.post("/api/users/does-not-exist/mfa/reset", headers=auth_header(admin_token)).status_code == 404
    make_user(db_session, role=RoleEnum.BOT_USER, username="analyst_z")
    analyst = login(client, "analyst_z").json()["access_token"]
    assert client.post(f"/api/users/{admin.id}/mfa/reset", headers=auth_header(analyst)).status_code == 403
    make_user(db_session, role=RoleEnum.INSTITUTION_USER, username="inst_z")
    inst = login(client, "inst_z").json()["access_token"]
    assert client.post(f"/api/users/{admin.id}/mfa/reset", headers=auth_header(inst)).status_code == 403
