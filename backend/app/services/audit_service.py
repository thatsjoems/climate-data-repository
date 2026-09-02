"""
MODULE: Audit Logging - recording important system events.
"""
from sqlalchemy.orm import Session
from app.models.models import AuditLog


def record_audit(
    db: Session,
    user_id: str | None,
    action: str,
    entity_type: str | None = None,
    entity_id: str | None = None,
    details: str | None = None,
):
    log = AuditLog(
        user_id=user_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        details=details,
    )
    db.add(log)
    db.commit()
