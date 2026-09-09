"""
MODULE C: Institution / Reporting Entity Management.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import require_roles, get_current_user
from app.models.models import Institution, User, RoleEnum
from app.schemas.schemas import InstitutionCreate, InstitutionOut, InstitutionPublicOut
from app.services.audit_service import record_audit
from app.services.notification_service import notify_roles

router = APIRouter(prefix="/institutions", tags=["Institutions"])


@router.get("")
def list_institutions(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Least privilege: INSTITUTION_USER gets a reduced view (no other
    institutions' contact emails/phones) - full detail is reserved for
    SYSTEM_ADMIN and BOT_USER, who need it for supervisory purposes.
    No response_model here (deliberately) - the two shapes are already
    correctly constructed below, so we return them as-is rather than
    risking Pydantic's Union matching silently coercing one into the other.
    """
    institutions = db.query(Institution).order_by(Institution.name).all()
    if current_user.role == RoleEnum.INSTITUTION_USER:
        return [InstitutionPublicOut.model_validate(i) for i in institutions]
    return [InstitutionOut.model_validate(i) for i in institutions]


@router.post("", response_model=InstitutionOut, status_code=201)
def create_institution(
    payload: InstitutionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(RoleEnum.SYSTEM_ADMIN)),
):
    if db.query(Institution).filter(Institution.code == payload.code).first():
        raise HTTPException(status_code=400, detail="This institution code already exists")
    inst = Institution(**payload.model_dump())
    db.add(inst)
    db.commit()
    db.refresh(inst)
    record_audit(db, current_user.id, "INSTITUTION_CREATED", "Institution", inst.id, inst.name)
    notify_roles(
        db, [RoleEnum.SYSTEM_ADMIN],
        message=f"{current_user.full_name} added a new institution: {inst.name}.",
        notif_type="INSTITUTION_CREATED",
        related_entity_type="Institution",
        related_entity_id=inst.id,
        exclude_user_id=current_user.id,
    )
    return inst


@router.patch("/{institution_id}/deactivate", response_model=InstitutionOut)
def deactivate_institution(
    institution_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(RoleEnum.SYSTEM_ADMIN)),
):
    inst = db.query(Institution).filter(Institution.id == institution_id).first()
    if not inst:
        raise HTTPException(status_code=404, detail="Institution not found")
    inst.is_active = False
    db.commit()
    db.refresh(inst)
    record_audit(db, current_user.id, "INSTITUTION_DEACTIVATED", "Institution", inst.id)
    notify_roles(
        db, [RoleEnum.SYSTEM_ADMIN],
        message=f"{current_user.full_name} deactivated institution: {inst.name}.",
        notif_type="INSTITUTION_DEACTIVATED",
        related_entity_type="Institution",
        related_entity_id=inst.id,
        exclude_user_id=current_user.id,
    )
    return inst
