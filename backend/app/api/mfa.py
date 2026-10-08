"""
MODULE: Two-step sign-in (the code from an authenticator app). See app/core/mfa.py for how the codes and secrets are handled.

Sign-in with a password (POST /auth/login) answers one of three ways:
  - tokens, exactly as before (the person does not use MFA and the Bank does not require it of them);
  - `mfa_required` plus a short `mfa_token`: send the 6-digit code (or a recovery code) to POST /auth/mfa/verify;
  - `mfa_setup_required` plus a short `mfa_token`: the person must enrol first (POST /auth/mfa/setup/begin, then /setup/confirm).
Wrong codes count towards the same lock-out as wrong passwords, so the second step cannot be guessed either.
"""
from datetime import timedelta

from cryptography.fernet import InvalidToken
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.api.auth import _issue_token_pair
from app.core.account_status import authentication_block_reason
from app.core.config import settings
from app.core.database import get_db
from app.core.deps import get_current_user
from app.core.mfa import (
    decrypt_secret, encrypt_secret, generate_secret, make_step_token, new_recovery_codes, otpauth_uri, read_step_token,
    qr_svg, recovery_codes_left, use_recovery_code, verify_totp,
)
from app.core.rate_limit import limiter
from app.core.timeutil import utcnow
from app.models.models import User
from app.schemas.schemas import (
    MfaBeginResponse, MfaCodeRequest, MfaConfirmRequest, MfaSetupRequest, MfaVerifyRequest, RecoveryCodesResponse,
    TokenResponse, UserOut,
)
from app.services.audit_service import record_audit
from app.services.notification_service import notify_user

router = APIRouter(prefix="/auth/mfa", tags=["Two-step sign-in"])

EXPIRED = "Your sign-in has expired. Please sign in again."
WRONG_CODE = "Incorrect or expired code"


def _user_for(db: Session, token: str, purpose: str) -> User:
    user_id = read_step_token(token, purpose)
    user = db.query(User).filter(User.id == user_id).first() if user_id else None
    if user is None or authentication_block_reason(user) is not None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=EXPIRED)
    if user.locked_until and user.locked_until > utcnow():
        minutes = max(1, int((user.locked_until - utcnow()).total_seconds() // 60) + 1)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"This account is temporarily locked due to repeated failed attempts. Try again in about {minutes} minute(s).",
        )
    return user


def _count_failure(db: Session, user: User, what: str) -> None:
    """A wrong code counts like a wrong password: the same counter and the same lock-out."""
    user.failed_login_attempts = (user.failed_login_attempts or 0) + 1
    if user.failed_login_attempts >= settings.MAX_FAILED_LOGIN_ATTEMPTS:
        user.locked_until = utcnow() + timedelta(minutes=settings.LOGIN_LOCKOUT_MINUTES)
        record_audit(db, user.id, "LOGIN_LOCKED", "User", user.id, f"Account locked after {user.failed_login_attempts} failed attempts ({what})")
    else:
        record_audit(db, user.id, "MFA_FAILED", "User", user.id, f"Wrong {what} ({user.failed_login_attempts}/{settings.MAX_FAILED_LOGIN_ATTEMPTS})")
    db.commit()


def _finish(db: Session, user: User, **extra) -> TokenResponse:
    user.failed_login_attempts = 0
    user.locked_until = None
    user.last_login_at = utcnow()
    db.commit()
    access, refresh = _issue_token_pair(db, user)
    return TokenResponse(access_token=access, refresh_token=refresh, user=UserOut.model_validate(user), **extra)


def _secret_of(user: User) -> str:
    try:
        return decrypt_secret(user.mfa_secret_encrypted)
    except (InvalidToken, AttributeError):
        # The key changed or the value is damaged: nobody can be let in on a guess; an administrator resets this person's MFA.
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=WRONG_CODE)


@router.post("/verify", response_model=TokenResponse)
@limiter.limit("10/minute")
def verify(request: Request, payload: MfaVerifyRequest, db: Session = Depends(get_db)):
    user = _user_for(db, payload.mfa_token, "mfa")
    if not user.mfa_enabled:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=EXPIRED)

    used_recovery = False
    if payload.code:
        step = verify_totp(_secret_of(user), payload.code, user.mfa_last_step)
        if step is None:
            _count_failure(db, user, "code")
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=WRONG_CODE)
        user.mfa_last_step = step
    elif payload.recovery_code:
        remaining = use_recovery_code(user.mfa_recovery_hashes, payload.recovery_code)
        if remaining is None:
            _count_failure(db, user, "recovery code")
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=WRONG_CODE)
        user.mfa_recovery_hashes = remaining
        used_recovery = True
    else:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Enter the 6-digit code or a recovery code")

    response = _finish(db, user)
    record_audit(db, user.id, "LOGIN", "User", user.id, f"User {user.username} logged in (two-step)")
    if used_recovery:
        left = recovery_codes_left(user.mfa_recovery_hashes)
        record_audit(db, user.id, "MFA_RECOVERY_CODE_USED", "User", user.id, f"A recovery code was used; {left} left")
        notify_user(db, user.id, message=f"A recovery code was used to sign in to your account. {left} recovery code(s) remain. "
                    "If this was not you, tell the System Administrator now.", notif_type="SECURITY")
    return response


@router.post("/setup/begin", response_model=MfaBeginResponse)
@limiter.limit("10/minute")
def begin_setup(request: Request, payload: MfaSetupRequest, db: Session = Depends(get_db)):
    """Starts enrolment: a new secret to type into the authenticator app. It does nothing until /setup/confirm proves the app shows the right code."""
    user = _user_for(db, payload.mfa_token, "mfa_setup")
    if user.mfa_enabled:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Two-step sign-in is already set up for this account")
    secret = generate_secret()
    user.mfa_secret_encrypted = encrypt_secret(secret)     # kept, but not active (mfa_enabled stays false) until confirmed
    db.commit()
    uri = otpauth_uri(secret, user.username)
    return MfaBeginResponse(secret=secret, otpauth_uri=uri, issuer=settings.MFA_ISSUER, account=user.username, qr_svg=qr_svg(uri))


@router.post("/setup/confirm", response_model=TokenResponse)
@limiter.limit("10/minute")
def confirm_setup(request: Request, payload: MfaConfirmRequest, db: Session = Depends(get_db)):
    user = _user_for(db, payload.mfa_token, "mfa_setup")
    if user.mfa_enabled or not user.mfa_secret_encrypted:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Start the set-up again")
    step = verify_totp(_secret_of(user), payload.code)
    if step is None:
        _count_failure(db, user, "code")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=WRONG_CODE)
    codes, hashes = new_recovery_codes()
    user.mfa_enabled = True
    user.mfa_last_step = step
    user.mfa_enrolled_at = utcnow()
    user.mfa_recovery_hashes = hashes
    response = _finish(db, user, recovery_codes=codes)
    record_audit(db, user.id, "MFA_ENABLED", "User", user.id, f"Two-step sign-in set up for {user.username}")
    record_audit(db, user.id, "LOGIN", "User", user.id, f"User {user.username} logged in (two-step, first time)")
    return response


@router.post("/recovery-codes", response_model=RecoveryCodesResponse)
@limiter.limit("10/minute")
def new_codes(request: Request, payload: MfaCodeRequest, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Replaces the recovery codes (the old ones stop working). Needs the current 6-digit code, so a stolen session cannot do it."""
    if not current_user.mfa_enabled:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Two-step sign-in is not set up for this account")
    step = verify_totp(_secret_of(current_user), payload.code, current_user.mfa_last_step)
    if step is None:
        _count_failure(db, current_user, "code")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=WRONG_CODE)
    codes, hashes = new_recovery_codes()
    current_user.mfa_last_step = step
    current_user.mfa_recovery_hashes = hashes
    db.commit()
    record_audit(db, current_user.id, "MFA_RECOVERY_CODES_REGENERATED", "User", current_user.id, "New recovery codes issued; the old ones no longer work")
    return RecoveryCodesResponse(recovery_codes=codes)
