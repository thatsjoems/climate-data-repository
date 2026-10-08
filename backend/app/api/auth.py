"""
MODULE A: Authentication.

Session security (Module: token lifecycle): access tokens are short-lived
JWTs (see settings.ACCESS_TOKEN_EXPIRE_MINUTES); a separate, longer-lived
refresh token (stored hashed, revocable, rotated on every use) is what keeps
the user signed in without requiring a long-lived JWT that could never be
revoked before its own expiry if stolen.
"""
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session

from app.core.account_status import authentication_block_reason, ACCOUNT_DEACTIVATED, INSTITUTION_DEACTIVATED
from app.core.database import get_db
from app.core.config import settings
from app.core.rate_limit import limiter
from app.core.security import (
    verify_password, create_access_token, hash_password,
    generate_refresh_token, hash_refresh_token,
)
from app.core.deps import get_current_user
from app.core.password_policy import validate_password_strength
from app.models.models import User, RefreshToken
from app.schemas.schemas import (
    LoginRequest, TokenResponse, UserOut, ChangePasswordRequest,
    RefreshRequest, AccessTokenResponse,
)
from app.services.audit_service import record_audit
from app.services.notification_service import notify_user
from app.core.timeutil import utcnow
from app.core.mfa import make_step_token, mfa_required_for

router = APIRouter(prefix="/auth", tags=["Authentication"])


def _issue_token_pair(db: Session, user: User) -> tuple[str, str]:
    """Creates a new access token (JWT) + refresh token (opaque, stored hashed) for this user."""
    access_token = create_access_token({"sub": user.id, "role": user.role.value})

    raw_refresh = generate_refresh_token()
    db.add(RefreshToken(
        user_id=user.id,
        token_hash=hash_refresh_token(raw_refresh),
        expires_at=utcnow() + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
    ))
    db.commit()
    return access_token, raw_refresh


@router.post("/login", response_model=TokenResponse)
@limiter.limit("10/minute")
def login(request: Request, payload: LoginRequest, db: Session = Depends(get_db)):
    # Generic message for "no such user" vs "wrong password" - never reveal which one it was
    # (prevents username enumeration).
    generic_error = HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect username or password")

    user = db.query(User).filter(User.username == payload.username).first()
    if not user:
        raise generic_error

    is_locked = bool(user.locked_until and user.locked_until > utcnow())

    # Password is checked BEFORE the lockout status is revealed (item 8 of the
    # September 2026 external review). The lockout message used to be raised
    # here, before the password was even looked at - so a caller who supplied
    # any password at all for a locked-but-otherwise-unknown-to-them username
    # got a distinct 403 "this account is locked" response, while an unknown
    # username always got the generic 401. That difference told an attacker
    # a username was valid without ever supplying its correct password,
    # defeating the "never reveal which one it was" comment above. Checking
    # the password FIRST means only someone who already knows the correct
    # password can learn that the account is currently locked.
    if not verify_password(payload.password, user.hashed_password):
        if not is_locked:
            user.failed_login_attempts = (user.failed_login_attempts or 0) + 1
            if user.failed_login_attempts >= settings.MAX_FAILED_LOGIN_ATTEMPTS:
                user.locked_until = utcnow() + timedelta(minutes=settings.LOGIN_LOCKOUT_MINUTES)
                record_audit(db, user.id, "LOGIN_LOCKED", "User", user.id,
                             f"Account locked after {user.failed_login_attempts} failed attempts")
            else:
                record_audit(db, user.id, "LOGIN_FAILED", "User", user.id,
                             f"Failed attempt {user.failed_login_attempts}/{settings.MAX_FAILED_LOGIN_ATTEMPTS}")
            db.commit()
        # Wrong password: always the same generic message, locked or not -
        # nothing here may differ based on lock status.
        raise generic_error

    if is_locked:
        minutes_left = max(1, int((user.locked_until - utcnow()).total_seconds() // 60) + 1)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"This account is temporarily locked due to repeated failed login attempts. "
                   f"Try again in about {minutes_left} minute(s), or use Forgot Password.",
        )

    # Reached only after the password has been verified, so telling the user WHY they
    # are blocked cannot be used to discover which usernames exist.
    block = authentication_block_reason(user)
    if block == ACCOUNT_DEACTIVATED:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="This account has been deactivated")
    if block == INSTITUTION_DEACTIVATED:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access for your institution has been deactivated. "
                   "Please contact the Bank of Tanzania administrator.",
        )

    # Two-step sign-in. The password alone is not enough for someone who has enrolled, or whom the Bank requires to enrol: they get a short
    # step token instead of tokens. The failed-attempt counter is NOT reset here, so wrong codes after a right password still run into the lock-out.
    if user.mfa_enabled:
        return TokenResponse(mfa_required=True, mfa_token=make_step_token(user.id, "mfa"))
    if mfa_required_for(user):
        return TokenResponse(mfa_setup_required=True, mfa_token=make_step_token(user.id, "mfa_setup"))

    # Successful login: reset lockout counters
    user.failed_login_attempts = 0
    user.locked_until = None
    user.last_login_at = utcnow()
    db.commit()

    access_token, refresh_token = _issue_token_pair(db, user)
    record_audit(db, user.id, "LOGIN", "User", user.id, f"User {user.username} logged in")

    return TokenResponse(access_token=access_token, refresh_token=refresh_token, user=UserOut.model_validate(user))


@router.post("/refresh", response_model=AccessTokenResponse)
@limiter.limit("30/minute")
def refresh_access_token(request: Request, payload: RefreshRequest, db: Session = Depends(get_db)):
    """
    Exchanges a still-valid refresh token for a new short-lived access token.
    Rotation: the presented refresh token is revoked and a brand new one is
    issued alongside the new access token - a refresh token can only ever be
    used once. Reuse of an already-rotated token (e.g. a stolen copy used
    after the legitimate client already rotated it) is rejected outright.
    """
    invalid_error = HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired refresh token")

    token_hash = hash_refresh_token(payload.refresh_token)
    stored = db.query(RefreshToken).filter(RefreshToken.token_hash == token_hash).first()

    if not stored or stored.revoked_at is not None or stored.expires_at < utcnow():
        raise invalid_error

    user = db.query(User).filter(User.id == stored.user_id).first()
    if not user or authentication_block_reason(user) is not None:
        raise invalid_error

    # Rotate: consume this token, issue a new pair
    stored.revoked_at = utcnow()
    db.commit()

    access_token, new_refresh_token = _issue_token_pair(db, user)
    return AccessTokenResponse(access_token=access_token, refresh_token=new_refresh_token)


@router.post("/logout")
def logout(payload: RefreshRequest, db: Session = Depends(get_db)):
    """
    Revokes the refresh token server-side - this is what makes "Log Out"
    actually mean something beyond deleting the local copy. The short-lived
    access token already in flight will still work until it naturally
    expires (at most a few minutes), but no new access token can be minted
    from this session afterward.
    """
    token_hash = hash_refresh_token(payload.refresh_token)
    stored = db.query(RefreshToken).filter(RefreshToken.token_hash == token_hash).first()
    if stored and stored.revoked_at is None:
        stored.revoked_at = utcnow()
        db.commit()
        record_audit(db, stored.user_id, "LOGOUT", "User", stored.user_id, "User logged out")
    return {"status": "ok"}


@router.get("/me", response_model=UserOut)
def read_me(current_user: User = Depends(get_current_user)):
    return current_user


@router.post("/change-password")
def change_password(
    payload: ChangePasswordRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Self-service password change for the logged-in user (any role). Different
    from the admin-reviewed 'Forgot Password' flow - this is for a user who
    remembers their current password but wants to set their own new one.
    Also clears must_change_password, so this is how a user "graduates" off
    an admin-issued temporary password.
    """
    if not verify_password(payload.current_password, current_user.hashed_password):
        raise HTTPException(status_code=400, detail="Your current password is incorrect")

    problems = validate_password_strength(payload.new_password, role=current_user.role, username=current_user.username)
    if problems:
        raise HTTPException(
            status_code=400,
            detail="Your new password must " + "; ".join(problems) + ".",
        )

    if verify_password(payload.new_password, current_user.hashed_password):
        raise HTTPException(status_code=400, detail="Your new password must be different from your current password")

    current_user.hashed_password = hash_password(payload.new_password)
    current_user.must_change_password = False
    db.commit()

    record_audit(db, current_user.id, "PASSWORD_CHANGED", "User", current_user.id, "Self-service password change")
    notify_user(
        db, current_user.id,
        message="Your password was changed successfully. If you did not make this change, contact a System Administrator immediately.",
        notif_type="PASSWORD_CHANGED",
    )
    return {"status": "ok"}
