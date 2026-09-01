"""
MODULE: Audit Log viewing (SYSTEM_ADMIN, BOT_USER only).
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import require_roles
from app.models.models import AuditLog, User, RoleEnum
from app.schemas.schemas import AuditLogOut

router = APIRouter(prefix="/audit-logs", tags=["Audit Log"])


@router.get("", response_model=list[AuditLogOut])
def list_audit_logs(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(RoleEnum.SYSTEM_ADMIN, RoleEnum.BOT_USER)),
):
    return db.query(AuditLog).order_by(AuditLog.created_at.desc()).limit(500).all()
