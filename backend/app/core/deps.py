"""
Dependencies za FastAPI: kupata mtumiaji aliyeingia (current user) na
kuzuia (guard) ufikiaji kulingana na role - Role Based Access Control (RBAC).
"""
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import decode_access_token
from app.models.models import User, RoleEnum

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Huwezi kutambuliwa - tafadhali ingia (login) tena",
        headers={"WWW-Authenticate": "Bearer"},
    )
    payload = decode_access_token(token)
    if payload is None:
        raise credentials_exception
    user_id = payload.get("sub")
    if user_id is None:
        raise credentials_exception
    user = db.query(User).filter(User.id == user_id).first()
    if user is None or not user.is_active:
        raise credentials_exception
    return user


def require_roles(*allowed_roles: RoleEnum):
    """Guard: inaruhusu tu watumiaji wenye role zilizoorodheshwa kufikia endpoint husika."""
    def checker(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Huna ruhusa ya kufikia rasilimali hii (insufficient permissions)",
            )
        return current_user
    return checker
