"""
MODULE: Audit Log viewing (SYSTEM_ADMIN, BOT_USER only).
"""
from datetime import datetime
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import require_roles
from app.models.models import AuditLog, User, RoleEnum
from app.schemas.schemas import AuditLogPage

router = APIRouter(prefix="/audit-logs", tags=["Audit Log"])


@router.get("", response_model=AuditLogPage)
def list_audit_logs(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(RoleEnum.SYSTEM_ADMIN)),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    action: str | None = Query(default=None, description="Exact action name, e.g. LOGIN"),
    entity_type: str | None = Query(default=None),
    user_id: str | None = Query(default=None),
    date_from: datetime | None = Query(default=None),
    date_to: datetime | None = Query(default=None),
):
    """
    Paginated + filterable, so the audit trail stays usable as it grows -
    previously this hard-capped at the first 500 records with no way to see
    anything older or to narrow the search.
    """
    query = db.query(AuditLog)
    if action:
        query = query.filter(AuditLog.action == action)
    if entity_type:
        query = query.filter(AuditLog.entity_type == entity_type)
    if user_id:
        query = query.filter(AuditLog.user_id == user_id)
    if date_from:
        query = query.filter(AuditLog.created_at >= date_from)
    if date_to:
        query = query.filter(AuditLog.created_at <= date_to)

    total = query.count()
    items = query.order_by(AuditLog.created_at.desc()).offset(offset).limit(limit).all()
    return AuditLogPage(items=items, total=total, limit=limit, offset=offset)
