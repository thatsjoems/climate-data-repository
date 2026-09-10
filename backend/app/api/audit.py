"""
MODULE: Audit Log viewing (SYSTEM_ADMIN, BOT_USER only).
"""
import csv
import io
from datetime import datetime
from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import require_roles
from app.models.models import AuditLog, User, RoleEnum
from app.schemas.schemas import AuditLogPage

router = APIRouter(prefix="/audit-logs", tags=["Audit Log"])


def _filtered_query(
    db: Session, action: str | None, entity_type: str | None, user_id: str | None,
    date_from: datetime | None, date_to: datetime | None,
):
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
    return query


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
    query = _filtered_query(db, action, entity_type, user_id, date_from, date_to)
    total = query.count()
    items = query.order_by(AuditLog.created_at.desc()).offset(offset).limit(limit).all()
    return AuditLogPage(items=items, total=total, limit=limit, offset=offset)


@router.get("/export.csv")
def export_audit_logs_csv(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(RoleEnum.SYSTEM_ADMIN)),
    action: str | None = Query(default=None),
    entity_type: str | None = Query(default=None),
    user_id: str | None = Query(default=None),
    date_from: datetime | None = Query(default=None),
    date_to: datetime | None = Query(default=None),
):
    """
    CSV export of the audit log (Section 20: Reporting - Export Dashboard),
    honoring the same filters as the on-screen list - no separate/hidden
    export scope. No hard row cap; this is a deliberate full export.
    """
    query = _filtered_query(db, action, entity_type, user_id, date_from, date_to)
    rows = query.order_by(AuditLog.created_at.desc()).all()

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["created_at", "user_id", "action", "entity_type", "entity_id", "details"])
    for r in rows:
        writer.writerow([r.created_at.isoformat(), r.user_id or "", r.action, r.entity_type or "", r.entity_id or "", r.details or ""])

    filename = f"CDR_Audit_Log_{datetime.utcnow().strftime('%Y%m%d_%H%M')}.csv"
    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
