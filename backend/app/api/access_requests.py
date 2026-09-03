"""
MODULE: Institution Access Requests ("Request Access").

This is intentionally NOT self-registration. A prospective reporting institution
submits a request describing who they are; no login is created at this point.
Only a SYSTEM_ADMIN, after verifying the institution out-of-band, may approve the
request - which is the single point where an Institution + User account get created.
"""
import random
import string
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import require_roles
from app.core.security import hash_password
from app.models.models import (
    InstitutionAccessRequest, AccessRequestStatus, Institution, User, RoleEnum,
)
from app.schemas.schemas import (
    AccessRequestCreate, AccessRequestOut, AccessRequestDecision, AccessRequestApprovalOut,
)
from app.services.audit_service import record_audit
from app.services.notification_service import notify_roles, notify_user
from app.services.email_service import send_email

router = APIRouter(prefix="/access-requests", tags=["Institution Access Requests"])


def _generate_username(base: str, db: Session) -> str:
    slug = "".join(ch for ch in base.lower().replace(" ", "_") if ch.isalnum() or ch == "_")[:24] or "user"
    candidate = slug
    suffix = 1
    while db.query(User).filter(User.username == candidate).first():
        suffix += 1
        candidate = f"{slug}{suffix}"
    return candidate


def _generate_temp_password() -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(random.choice(alphabet) for _ in range(10)) + "!1"


@router.post("", response_model=AccessRequestOut, status_code=201)
def submit_access_request(payload: AccessRequestCreate, db: Session = Depends(get_db)):
    """Public endpoint - no authentication required. Only creates a pending request."""
    req = InstitutionAccessRequest(**payload.model_dump())
    db.add(req)
    db.commit()
    db.refresh(req)

    notify_roles(
        db, [RoleEnum.SYSTEM_ADMIN],
        message=f"New access request from '{req.institution_name}' ({req.contact_full_name}).",
        notif_type="ACCESS_REQUEST_SUBMITTED",
        related_entity_type="InstitutionAccessRequest",
        related_entity_id=req.id,
    )
    return req


@router.get("", response_model=list[AccessRequestOut])
def list_access_requests(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(RoleEnum.SYSTEM_ADMIN)),
):
    return db.query(InstitutionAccessRequest).order_by(InstitutionAccessRequest.created_at.desc()).all()


@router.post("/{request_id}/approve", response_model=AccessRequestApprovalOut)
def approve_access_request(
    request_id: str,
    payload: AccessRequestDecision,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(RoleEnum.SYSTEM_ADMIN)),
):
    req = db.query(InstitutionAccessRequest).filter(InstitutionAccessRequest.id == request_id).first()
    if not req:
        raise HTTPException(status_code=404, detail="Access request not found")
    if req.status != AccessRequestStatus.PENDING:
        raise HTTPException(status_code=400, detail="This request has already been reviewed")

    # Reuse an existing institution if the code matches; otherwise create a new one.
    institution = None
    if req.institution_code:
        institution = db.query(Institution).filter(Institution.code == req.institution_code).first()
    if not institution:
        code = req.institution_code or _generate_username(req.institution_name, db).upper()[:20]
        institution = Institution(
            code=code,
            name=req.institution_name,
            type=req.institution_type,
            contact_email=req.contact_email,
            contact_phone=req.contact_phone,
        )
        db.add(institution)
        db.flush()

    username = _generate_username(req.contact_email.split("@")[0], db)
    temp_password = _generate_temp_password()

    user = User(
        full_name=req.contact_full_name,
        username=username,
        email=req.contact_email,
        hashed_password=hash_password(temp_password),
        role=RoleEnum.INSTITUTION_USER,
        institution_id=institution.id,
    )
    db.add(user)
    db.flush()

    req.status = AccessRequestStatus.APPROVED
    req.review_notes = payload.notes
    req.reviewed_by_user_id = current_user.id
    req.reviewed_at = datetime.utcnow()
    req.created_institution_id = institution.id
    req.created_user_id = user.id
    db.commit()
    db.refresh(req)

    record_audit(
        db, current_user.id, "ACCESS_REQUEST_APPROVED", "InstitutionAccessRequest", req.id,
        f"Created institution '{institution.name}' and user '{username}'"
    )
    notify_user(
        db, user.id,
        message=f"Welcome to the Climate Data Repository. Your account for "
                 f"{institution.name} has been created.",
        notif_type="ACCOUNT_CREATED",
    )
    notify_roles(
        db, [RoleEnum.SYSTEM_ADMIN, RoleEnum.BOT_USER],
        message=f"Access request from '{req.institution_name}' was approved by {current_user.full_name}.",
        notif_type="ACCESS_REQUEST_APPROVED",
        related_entity_type="InstitutionAccessRequest",
        related_entity_id=req.id,
        exclude_user_id=current_user.id,
    )

    email_sent = send_email(
        to_email=req.contact_email,
        subject="Your Climate Data Repository Access - Bank of Tanzania",
        body=(
            f"Dear {req.contact_full_name},\n\n"
            f"Your access request on behalf of {institution.name} has been approved.\n\n"
            f"Username: {username}\n"
            f"Temporary Password: {temp_password}\n\n"
            f"Please log in and note this password is temporary. If you did not request this, "
            f"please contact the Bank of Tanzania immediately.\n\n"
            f"Regards,\nClimate Data Repository - Bank of Tanzania"
        ),
    )

    return AccessRequestApprovalOut(
        request=req,
        generated_username=username,
        generated_temporary_password=temp_password,
        email_sent=email_sent,
    )


@router.post("/{request_id}/reject", response_model=AccessRequestOut)
def reject_access_request(
    request_id: str,
    payload: AccessRequestDecision,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(RoleEnum.SYSTEM_ADMIN)),
):
    req = db.query(InstitutionAccessRequest).filter(InstitutionAccessRequest.id == request_id).first()
    if not req:
        raise HTTPException(status_code=404, detail="Access request not found")
    if req.status != AccessRequestStatus.PENDING:
        raise HTTPException(status_code=400, detail="This request has already been reviewed")

    req.status = AccessRequestStatus.REJECTED
    req.review_notes = payload.notes
    req.reviewed_by_user_id = current_user.id
    req.reviewed_at = datetime.utcnow()
    db.commit()
    db.refresh(req)

    record_audit(db, current_user.id, "ACCESS_REQUEST_REJECTED", "InstitutionAccessRequest", req.id, payload.notes or "")
    notify_roles(
        db, [RoleEnum.SYSTEM_ADMIN, RoleEnum.BOT_USER],
        message=f"Access request from '{req.institution_name}' was rejected by {current_user.full_name}.",
        notif_type="ACCESS_REQUEST_REJECTED",
        related_entity_type="InstitutionAccessRequest",
        related_entity_id=req.id,
        exclude_user_id=current_user.id,
    )
    send_email(
        to_email=req.contact_email,
        subject="Update on your Climate Data Repository Access Request",
        body=(
            f"Dear {req.contact_full_name},\n\n"
            f"Your access request on behalf of {req.institution_name} was not approved at this time."
            + (f"\n\nReason: {payload.notes}" if payload.notes else "")
            + "\n\nIf you have questions, please contact the Bank of Tanzania.\n\n"
              "Regards,\nClimate Data Repository - Bank of Tanzania"
        ),
    )
    return req
