"""
Creating the first System Administrator from the command line.

Why this exists. With ENVIRONMENT=production, init_db.py deliberately seeds nothing - the demo
accounts have published passwords. That left a production database with its tables but no
users, and nothing in the project said how to create the first administrator: the only
account-creation endpoint requires an administrator to already be signed in. This is that
missing bootstrap, run by someone who already has shell access to the backend container.

The logic lives here, not in the script, so it can be tested without a terminal.

By default it refuses when an active System Administrator already exists: the bootstrap is
for an EMPTY system, and further users belong in the app, where creating them is permission-
checked and audited. allow_additional=True is the recovery path for a system whose only
administrator is locked out or deactivated and has nobody left to sign in as.
"""
from sqlalchemy.orm import Session

from app.core.password_policy import validate_password_strength
from app.core.security import hash_password
from app.models.models import RoleEnum, User
from app.schemas.schemas import UserCreate
from app.services.audit_service import record_audit


class BootstrapError(Exception):
    """The administrator was not created; the message says why and is safe to show the operator."""


def create_first_admin(
    db: Session,
    *,
    full_name: str,
    username: str,
    email: str,
    password: str,
    allow_additional: bool = False,
    must_change_password: bool = False,
) -> User:
    full_name, username, email = full_name.strip(), username.strip(), email.strip()
    if not full_name or not username:
        raise BootstrapError("Full name and username must not be empty.")

    existing = (
        db.query(User)
        .filter(User.role == RoleEnum.SYSTEM_ADMIN, User.is_active == True)  # noqa: E712
        .first()
    )
    if existing and not allow_additional:
        raise BootstrapError(
            f"An active System Administrator already exists ('{existing.username}'). Sign in as that "
            "administrator and create further users in the application. If nobody can sign in as an "
            "administrator any more, run this again with --allow-additional."
        )

    # The same validation the API's user-creation endpoint applies (including a real e-mail check).
    try:
        UserCreate(
            full_name=full_name, username=username, email=email,
            password=password, role=RoleEnum.SYSTEM_ADMIN,
        )
    except ValueError as exc:
        raise BootstrapError(f"Invalid input: {exc}") from exc

    problems = validate_password_strength(password, role=RoleEnum.SYSTEM_ADMIN, username=username)
    if problems:
        raise BootstrapError("Password must " + "; ".join(problems) + ".")

    if db.query(User).filter(User.username == username).first():
        raise BootstrapError(f"The username '{username}' is already taken.")
    if db.query(User).filter(User.email == email).first():
        raise BootstrapError(f"The e-mail address '{email}' is already in use.")

    user = User(
        full_name=full_name,
        username=username,
        email=email,
        hashed_password=hash_password(password),
        role=RoleEnum.SYSTEM_ADMIN,
        institution_id=None,
        must_change_password=must_change_password,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    # No acting user exists yet, so the audit entry has none; the password is never recorded.
    record_audit(
        db, None, "ADMIN_BOOTSTRAPPED", "User", user.id,
        f"System Administrator '{user.username}' created from the command line",
        details_json={"allow_additional": allow_additional, "must_change_password": must_change_password},
    )
    # record_audit commits, which expires the user's fields; load them again so the returned user is still
    # readable after the caller closes the session (the command-line script does exactly that).
    db.refresh(user)
    return user
