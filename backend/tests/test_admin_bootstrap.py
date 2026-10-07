"""
First-administrator bootstrap (app/services/admin_bootstrap.py, scripts/create_admin.py).

Production seeds no users (the demo accounts have published passwords), and the only
user-creation endpoint requires an administrator to be signed in - so a fresh production
database had no way to get its first administrator. These tests cover the service the
command-line script wraps.
"""
import pytest

from app.models.models import AuditLog, RoleEnum, User
from app.services.admin_bootstrap import BootstrapError, create_first_admin
from tests.conftest import login, make_user

GOOD = dict(
    full_name="First Admin",
    username="first_admin",
    email="first.admin@example.com",
    password="Str0ng!Passw0rd",
)


def test_creates_a_system_administrator_who_can_sign_in(client, db_session):
    user = create_first_admin(db_session, **GOOD)
    assert user.role == RoleEnum.SYSTEM_ADMIN
    assert user.institution_id is None
    assert user.hashed_password != GOOD["password"]  # stored hashed, never as typed
    res = login(client, "first_admin", GOOD["password"])
    assert res.status_code == 200
    assert res.json()["access_token"]


def test_a_password_change_is_not_forced_unless_asked(db_session):
    assert create_first_admin(db_session, **GOOD).must_change_password is False


def test_a_password_change_can_be_required(db_session):
    assert create_first_admin(db_session, must_change_password=True, **GOOD).must_change_password is True


def test_the_creation_is_audited_and_the_password_is_not_recorded(db_session):
    user = create_first_admin(db_session, **GOOD)
    entry = db_session.query(AuditLog).filter(AuditLog.action == "ADMIN_BOOTSTRAPPED").one()
    assert entry.entity_id == user.id
    assert entry.user_id is None  # nobody was signed in to be the actor
    assert GOOD["password"] not in (entry.details or "")
    assert GOOD["password"] not in str(entry.details_json or "")


def test_a_weak_password_is_refused_and_nothing_is_created(db_session):
    with pytest.raises(BootstrapError, match="Password must"):
        create_first_admin(db_session, **dict(GOOD, password="short"))
    assert db_session.query(User).count() == 0


def test_an_invalid_email_is_refused(db_session):
    with pytest.raises(BootstrapError, match="Invalid input"):
        create_first_admin(db_session, **dict(GOOD, email="not-an-email"))
    assert db_session.query(User).count() == 0


def test_empty_names_are_refused(db_session):
    with pytest.raises(BootstrapError):
        create_first_admin(db_session, **dict(GOOD, full_name="   "))
    assert db_session.query(User).count() == 0


def test_it_refuses_when_an_active_administrator_already_exists(db_session):
    make_user(db_session, role=RoleEnum.SYSTEM_ADMIN, username="existing_admin")
    with pytest.raises(BootstrapError, match="already exists"):
        create_first_admin(db_session, **GOOD)
    assert db_session.query(User).count() == 1


def test_allow_additional_overrides_that_refusal(db_session):
    make_user(db_session, role=RoleEnum.SYSTEM_ADMIN, username="existing_admin")
    user = create_first_admin(db_session, allow_additional=True, **GOOD)
    assert user.username == "first_admin"
    assert db_session.query(User).count() == 2


def test_a_deactivated_administrator_does_not_block_the_bootstrap(db_session):
    # The recovery case: the only administrator was deactivated, so nobody can create another.
    admin = make_user(db_session, role=RoleEnum.SYSTEM_ADMIN, username="old_admin")
    admin.is_active = False
    db_session.commit()
    assert create_first_admin(db_session, **GOOD).username == "first_admin"


def test_a_username_that_is_taken_is_refused(db_session):
    make_user(db_session, role=RoleEnum.BOT_USER, username="first_admin")
    with pytest.raises(BootstrapError, match="username"):
        create_first_admin(db_session, **GOOD)


def test_an_email_that_is_in_use_is_refused(db_session):
    make_user(db_session, role=RoleEnum.BOT_USER, username="bot1")  # make_user gives it bot1@example.com
    with pytest.raises(BootstrapError, match="e-mail"):
        create_first_admin(db_session, **dict(GOOD, email="bot1@example.com"))


def test_the_returned_user_is_still_readable_after_the_session_is_closed(db_session):
    """The command-line script closes its session and then prints the username; that used to raise
    DetachedInstanceError (found when the first production administrator was created)."""
    user = create_first_admin(db_session, **GOOD)
    db_session.close()
    assert user.username == "first_admin" and user.id and user.role == RoleEnum.SYSTEM_ADMIN
