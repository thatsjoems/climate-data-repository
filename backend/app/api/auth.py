"""
MODULE A: Authentication.
"""
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import verify_password, create_access_token
from app.core.deps import get_current_user
from app.models.models import User
from app.schemas.schemas import LoginRequest, TokenResponse, UserOut
from app.services.audit_service import record_audit

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == payload.username).first()
    if not user or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Username au password si sahihi")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Akaunti hii imezimwa (deactivated)")

    user.last_login_at = datetime.utcnow()
    db.commit()

    token = create_access_token({"sub": user.id, "role": user.role.value})
    record_audit(db, user.id, "LOGIN", "User", user.id, f"Mtumiaji {user.username} ameingia")

    return TokenResponse(access_token=token, user=UserOut.model_validate(user))


@router.get("/me", response_model=UserOut)
def read_me(current_user: User = Depends(get_current_user)):
    return current_user
