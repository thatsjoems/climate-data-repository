"""
MODULE: Risk Advisory Reports (Climate Risk Assessment & Supervisory Reporting).

Direct implementation of the ICN's stated purpose: "strengthen climate risk
assessment", "support climate risk assessment and reporting", and "support
supervisory activities and evidence-based decision-making".

Deliberately exclusive to BOT_USER (the Analyst role) for AUTHORING - this is
the Analyst's distinctive professional function, separate from SYSTEM_ADMIN's
identity/access-management function. SYSTEM_ADMIN may read notes for oversight
but cannot author them, giving each internal role a genuinely separate duty.
"""
import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import require_roles
from app.models.models import RiskAdvisoryNote, User, RoleEnum
from app.schemas.schemas import RiskAdvisoryCreate, RiskAdvisoryOut
from app.services.analytics_service import get_exposure_snapshot
from app.services.audit_service import record_audit
from app.services.notification_service import notify_roles

router = APIRouter(prefix="/risk-advisories", tags=["Risk Advisory Reports"])


@router.get("", response_model=list[RiskAdvisoryOut])
def list_risk_advisories(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(RoleEnum.BOT_USER, RoleEnum.SYSTEM_ADMIN)),
):
    return db.query(RiskAdvisoryNote).order_by(RiskAdvisoryNote.created_at.desc()).all()


@router.get("/{note_id}", response_model=RiskAdvisoryOut)
def get_risk_advisory(
    note_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(RoleEnum.BOT_USER, RoleEnum.SYSTEM_ADMIN)),
):
    note = db.query(RiskAdvisoryNote).filter(RiskAdvisoryNote.id == note_id).first()
    if not note:
        raise HTTPException(status_code=404, detail="Risk advisory note not found")
    return note


@router.post("", response_model=RiskAdvisoryOut, status_code=201)
def create_risk_advisory(
    payload: RiskAdvisoryCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(RoleEnum.BOT_USER)),
):
    """Only BOT_USER (Analyst) may author a risk advisory - see module docstring."""
    snapshot = get_exposure_snapshot(db, region=payload.region, hazard_type=payload.hazard_type)

    note = RiskAdvisoryNote(
        title=payload.title,
        region=payload.region,
        hazard_type=payload.hazard_type,
        risk_level=payload.risk_level,
        narrative=payload.narrative,
        recommendation=payload.recommendation,
        data_snapshot=json.dumps(snapshot),
        created_by_user_id=current_user.id,
    )
    db.add(note)
    db.commit()
    db.refresh(note)

    record_audit(
        db, current_user.id, "RISK_ADVISORY_CREATED", "RiskAdvisoryNote", note.id,
        f"{note.title} - {note.risk_level.value}"
    )
    notify_roles(
        db, [RoleEnum.SYSTEM_ADMIN],
        message=f"{current_user.full_name} published a {note.risk_level.value} risk advisory: '{note.title}'.",
        notif_type="RISK_ADVISORY_CREATED",
        related_entity_type="RiskAdvisoryNote",
        related_entity_id=note.id,
    )
    return note
