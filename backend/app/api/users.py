"""
MODULE B: User Management (SYSTEM_ADMIN only).
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import require_roles, get_current_user
from app.core.security import hash_password
from app.models.models import User, RoleEnum
from app.schemas.schemas import UserCreate, UserOut
from app.services.audit_service import record_audit

router = APIRouter(prefix="/users", tags=["User Management"])


@router.get("", response_model=list[UserOut])
def list_users(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(RoleEnum.SYSTEM_ADMIN, RoleEnum.BOT_USER)),
):
    return db.query(User).order_by(User.created_at.desc()).all()


@router.post("", response_model=UserOut, status_code=201)
def create_user(
    payload: UserCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(RoleEnum.SYSTEM_ADMIN)),
):
    if db.query(User).filter(User.username == payload.username).first():
        raise HTTPException(status_code=400, detail="Username hii tayari inatumika")
    if db.query(User).filter(User.email == payload.email).first():
        raise HTTPException(status_code=400, detail="Email hii tayari inatumika")

    user = User(
        full_name=payload.full_name,
        username=payload.username,
        email=payload.email,
        hashed_password=hash_password(payload.password),
        role=payload.role,
        institution_id=payload.institution_id,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    record_audit(db, current_user.id, "USER_CREATED", "User", user.id, f"Aliundwa mtumiaji {user.username}")
    return user


@router.patch("/{user_id}/deactivate", response_model=UserOut)
def deactivate_user(
    user_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(RoleEnum.SYSTEM_ADMIN)),
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Mtumiaji hajapatikana")
    user.is_active = False
    db.commit()
    db.refresh(user)
    record_audit(db, current_user.id, "USER_DEACTIVATED", "User", user.id)
    return user


@router.patch("/{user_id}/activate", response_model=UserOut)
def activate_user(
    user_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(RoleEnum.SYSTEM_ADMIN)),
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Mtumiaji hajapatikana")
    user.is_active = True
    db.commit()
    db.refresh(user)
    record_audit(db, current_user.id, "USER_ACTIVATED", "User", user.id)
    return user
