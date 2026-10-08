"""
Setting a new password from the server (app/services/account_recovery.py, scripts/reset_password.py).

For an administrator who forgot their password with no second administrator to help. It must let the person in with the new password and nobody in with
the old one, undo a lock-out, end the sessions they already had, require a new password of their own by default, respect the password policy, leave the
two-step sign-in alone, and record who did what without ever recording the password.
"""
import pytest

from app.core.timeutil import utcnow
from app.models.models import AuditLog, RoleEnum, User
from app.services.account_recovery import RecoveryError, reset_password
from tests.conftest import DEFAULT_PASSWORD, login, make_user

NEW = "N3w!Passw0rd-Chosen"


def _admin(db, username="forgotten_admin"):
    return make_user(db, role=RoleEnum.SYSTEM_ADMIN, username=username)


def test_the_new_password_works_and_the_old_one_no_longer_does(client, db_session):
    _admin(db_session)
    assert login(client, "forgotten_admin").status_code == 200
    reset_password(db_session, "forgotten_admin", NEW)
    assert login(client, "forgotten_admin", DEFAULT_PASSWORD).status_code == 401
    assert login(client, "forgotten_admin", NEW).status_code == 200


def test_the_password_is_stored_hashed(db_session):
    _admin(db_session)
    user = reset_password(db_session, "forgotten_admin", NEW)
    assert user.hashed_password and NEW not in user.hashed_password


def test_a_locked_account_is_unlocked_and_its_count_cleared(client, db_session):
    user = _admin(db_session)
    user.failed_login_attempts = 5
    user.locked_until = utcnow().replace(year=utcnow().year + 1)
    db_session.commit()
    reset_password(db_session, "forgotten_admin", NEW)
    db_session.refresh(user)
    assert user.failed_login_attempts == 0 and user.locked_until is None
    assert login(client, "forgotten_admin", NEW).status_code == 200


def test_sessions_the_person_already_had_are_ended(client, db_session):
    _admin(db_session)
    old_refresh = login(client, "forgotten_admin").json()["refresh_token"]
    reset_password(db_session, "forgotten_admin", NEW)
    assert client.post("/api/auth/refresh", json={"refresh_token": old_refresh}).status_code == 401


@pytest.mark.parametrize("must_change", [True, False])
def test_a_new_password_of_their_own_is_required_unless_told_otherwise(db_session, must_change):
    user = _admin(db_session)
    reset_password(db_session, "forgotten_admin", NEW, must_change=must_change)
    db_session.refresh(user)
    assert user.must_change_password is must_change


def test_the_default_is_to_require_a_change(db_session):
    user = _admin(db_session)
    reset_password(db_session, "forgotten_admin", NEW)
    db_session.refresh(user)
    assert user.must_change_password is True


@pytest.mark.parametrize("weak", ["short1!", "alllettersandsymbols!!!", "NoSpecialChar12345", "", None])
def test_a_password_that_breaks_the_policy_is_refused_and_nothing_changes(client, db_session, weak):
    user = _admin(db_session)
    before = user.hashed_password
    with pytest.raises(RecoveryError, match="must"):
        reset_password(db_session, "forgotten_admin", weak)
    db_session.refresh(user)
    assert user.hashed_password == before
    assert login(client, "forgotten_admin").status_code == 200       # the old password still works


def test_an_unknown_user_is_refused(db_session):
    with pytest.raises(RecoveryError, match="No user named"):
        reset_password(db_session, "nobody_here", NEW)


def test_the_two_step_sign_in_is_left_as_it_is(db_session):
    user = _admin(db_session)
    user.mfa_enabled = True
    user.mfa_secret_encrypted = "not-a-real-secret"
    db_session.commit()
    reset_password(db_session, "forgotten_admin", NEW)
    db_session.refresh(user)
    assert user.mfa_enabled is True and user.mfa_secret_encrypted == "not-a-real-secret"


def test_the_reset_is_audited_as_made_from_the_command_line_and_the_password_is_not_recorded(db_session):
    user = _admin(db_session)
    reset_password(db_session, "forgotten_admin", NEW)
    entry = db_session.query(AuditLog).filter(AuditLog.action == "PASSWORD_RESET_CLI").one()
    assert entry.entity_id == user.id and entry.user_id is None          # nobody was signed in to be the actor
    assert NEW not in (entry.details or "") and NEW not in str(entry.details_json or "")


def test_only_the_named_person_is_changed(client, db_session):
    _admin(db_session, "forgotten_admin")
    _admin(db_session, "other_admin")
    reset_password(db_session, "forgotten_admin", NEW)
    assert login(client, "other_admin", DEFAULT_PASSWORD).status_code == 200
