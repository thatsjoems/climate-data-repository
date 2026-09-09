"""
MODULE: Risk Advisory Reports (Climate Risk Assessment & Supervisory Reporting).

Direct implementation of the ICN's stated purpose: "strengthen climate risk
assessment", "support climate risk assessment and reporting", and "support
supervisory activities and evidence-based decision-making".

Exclusive to BOT_USER (the Analyst role) for both reading and authoring - this
is the Analyst's distinctive professional function, entirely separate from
SYSTEM_ADMIN's identity/access-management function. SYSTEM_ADMIN's dashboard
deliberately has no visibility into climate/submission data at all.
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


def _to_out(db: Session, note: RiskAdvisoryNote) -> RiskAdvisoryOut:
    author = db.query(User).filter(User.id == note.created_by_user_id).first()
    return RiskAdvisoryOut(
        id=note.id,
        title=note.title,
        region=note.region,
        hazard_type=note.hazard_type,
        risk_level=note.risk_level,
        narrative=note.narrative,
        recommendation=note.recommendation,
        data_snapshot=note.data_snapshot,
        created_by_user_id=note.created_by_user_id,
        created_by_name=author.full_name if author else "Analyst",
        created_at=note.created_at,
    )


@router.get("", response_model=list[RiskAdvisoryOut])
def list_risk_advisories(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(RoleEnum.BOT_USER)),
):
    notes = db.query(RiskAdvisoryNote).order_by(RiskAdvisoryNote.created_at.desc()).all()
    return [_to_out(db, n) for n in notes]


@router.get("/{note_id}", response_model=RiskAdvisoryOut)
def get_risk_advisory(
    note_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(RoleEnum.BOT_USER)),
):
    note = db.query(RiskAdvisoryNote).filter(RiskAdvisoryNote.id == note_id).first()
    if not note:
        raise HTTPException(status_code=404, detail="Risk advisory note not found")
    return _to_out(db, note)


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
    # Peer analysts (not System Admin) are the intended audience - risk analysis
    # is entirely the Analyst side's domain.
    notify_roles(
        db, [RoleEnum.BOT_USER],
        message=f"{current_user.full_name} published a {note.risk_level.value} risk advisory: '{note.title}'.",
        notif_type="RISK_ADVISORY_CREATED",
        related_entity_type="RiskAdvisoryNote",
        related_entity_id=note.id,
        exclude_user_id=current_user.id,
    )
    return _to_out(db, note)
