"""
MODULE C: Institution / Reporting Entity Management.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import require_roles, get_current_user
from app.models.models import Institution, User, RoleEnum
from app.schemas.schemas import InstitutionCreate, InstitutionOut
from app.services.audit_service import record_audit

router = APIRouter(prefix="/institutions", tags=["Institutions"])


@router.get("", response_model=list[InstitutionOut])
def list_institutions(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Watumiaji wote walioingia wanaweza kuona orodha ya taasisi (kwa ajili ya dropdowns n.k.)
    return db.query(Institution).order_by(Institution.name).all()


@router.post("", response_model=InstitutionOut, status_code=201)
def create_institution(
    payload: InstitutionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(RoleEnum.SYSTEM_ADMIN)),
):
    if db.query(Institution).filter(Institution.code == payload.code).first():
        raise HTTPException(status_code=400, detail="Institution code hii tayari ipo")
    inst = Institution(**payload.model_dump())
    db.add(inst)
    db.commit()
    db.refresh(inst)
    record_audit(db, current_user.id, "INSTITUTION_CREATED", "Institution", inst.id, inst.name)
    return inst


@router.patch("/{institution_id}/deactivate", response_model=InstitutionOut)
def deactivate_institution(
    institution_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(RoleEnum.SYSTEM_ADMIN)),
):
    inst = db.query(Institution).filter(Institution.id == institution_id).first()
    if not inst:
        raise HTTPException(status_code=404, detail="Taasisi haijapatikana")
    inst.is_active = False
    db.commit()
    db.refresh(inst)
    record_audit(db, current_user.id, "INSTITUTION_DEACTIVATED", "Institution", inst.id)
    return inst
