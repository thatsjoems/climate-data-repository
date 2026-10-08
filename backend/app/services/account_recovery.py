"""
Recovery of an account from the server (scripts/reset_password.py).

The application lets an administrator set a new password for someone else, but an administrator who has forgotten their own password, with no second
administrator to help, has no way back in through the web page. This is the Bank's own control for that case: it needs access to the server, which is
the point. The two-step sign-in is NOT touched here (scripts/reset_mfa.py is for that).
"""
from sqlalchemy.orm import Session

from app.core.password_policy import validate_password_strength
from app.core.security import hash_password
from app.core.timeutil import utcnow
from app.models.models import RefreshToken, User
from app.services.audit_service import record_audit


class RecoveryError(Exception):
    """The reset was refused; the message says why and is safe to show."""


def reset_password(db: Session, username: str, password: str, *, must_change: bool = True) -> User:
    user = db.query(User).filter(User.username == username).first()
    if user is None:
        raise RecoveryError(f"No user named {username!r}.")
    problems = validate_password_strength(password or "", role=user.role, username=user.username)
    if problems:
        raise RecoveryError("The password must " + "; ".join(problems) + ".")
    user.hashed_password = hash_password(password)
    user.failed_login_attempts = 0
    user.locked_until = None
    user.must_change_password = bool(must_change)
    # Every session the person already had ends: whoever held them (including someone who should not have) must sign in again with the new password.
    db.query(RefreshToken).filter(RefreshToken.user_id == user.id, RefreshToken.revoked_at.is_(None)).update({"revoked_at": utcnow()})
    db.commit()
    record_audit(
        db, None, "PASSWORD_RESET_CLI", "User", user.id,
        f"Password of {user.username} reset from the command line; "
        + ("a new one must be chosen at the next sign-in" if must_change else "no change is required at the next sign-in"),
    )
    return user
