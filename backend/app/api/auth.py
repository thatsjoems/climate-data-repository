"""
MODULE A: Authentication.
"""
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.config import settings
from app.core.security import verify_password, create_access_token, hash_password
from app.core.deps import get_current_user
from app.core.password_policy import validate_password_strength
from app.models.models import User
from app.schemas.schemas import LoginRequest, TokenResponse, UserOut, ChangePasswordRequest
from app.services.audit_service import record_audit
from app.services.notification_service import notify_user

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    # Generic message for "no such user" vs "wrong password" - never reveal which one it was
    # (prevents username enumeration).
    generic_error = HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect username or password")

    user = db.query(User).filter(User.username == payload.username).first()
    if not user:
        raise generic_error

    # ---- Brute-force lockout ----
    if user.locked_until and user.locked_until > datetime.utcnow():
        minutes_left = max(1, int((user.locked_until - datetime.utcnow()).total_seconds() // 60) + 1)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"This account is temporarily locked due to repeated failed login attempts. "
                   f"Try again in about {minutes_left} minute(s), or use Forgot Password.",
        )

    if not verify_password(payload.password, user.hashed_password):
        user.failed_login_attempts = (user.failed_login_attempts or 0) + 1
        if user.failed_login_attempts >= settings.MAX_FAILED_LOGIN_ATTEMPTS:
            user.locked_until = datetime.utcnow() + timedelta(minutes=settings.LOGIN_LOCKOUT_MINUTES)
            record_audit(db, user.id, "LOGIN_LOCKED", "User", user.id,
                         f"Account locked after {user.failed_login_attempts} failed attempts")
        else:
            record_audit(db, user.id, "LOGIN_FAILED", "User", user.id,
                         f"Failed attempt {user.failed_login_attempts}/{settings.MAX_FAILED_LOGIN_ATTEMPTS}")
        db.commit()
        raise generic_error

    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="This account has been deactivated")

    # Successful login: reset lockout counters
    user.failed_login_attempts = 0
    user.locked_until = None
    user.last_login_at = datetime.utcnow()
    db.commit()

    token = create_access_token({"sub": user.id, "role": user.role.value})
    record_audit(db, user.id, "LOGIN", "User", user.id, f"User {user.username} logged in")

    return TokenResponse(access_token=token, user=UserOut.model_validate(user))


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

    problems = validate_password_strength(payload.new_password)
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
