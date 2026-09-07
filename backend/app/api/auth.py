"""
MODULE A: Authentication.
"""
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
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
    user = db.query(User).filter(User.username == payload.username).first()
    if not user or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect username or password")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="This account has been deactivated")

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
    db.commit()

    record_audit(db, current_user.id, "PASSWORD_CHANGED", "User", current_user.id, "Self-service password change")
    notify_user(
        db, current_user.id,
        message="Your password was changed successfully. If you did not make this change, contact a System Administrator immediately.",
        notif_type="PASSWORD_CHANGED",
    )
    return {"status": "ok"}
