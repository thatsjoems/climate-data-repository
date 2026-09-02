"""
MODULE: Password Recovery ("Forgot Password").

Explicitly required by the Concept Note ("secure user authentication,
including login and password recovery functionality"). Implemented as a
request/review flow rather than an emailed reset link, since no SMTP
integration was available in this training environment - the same pattern
already used for institution access requests.
"""
import random
import string
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import or_

from app.core.database import get_db
from app.core.deps import require_roles
from app.core.security import hash_password
from app.models.models import PasswordResetRequest, AccessRequestStatus, User, RoleEnum
from app.schemas.schemas import (
    PasswordResetRequestCreate, PasswordResetRequestOut, PasswordResetApprovalOut,
    AccessRequestDecision,
)
from app.services.audit_service import record_audit
from app.services.notification_service import notify_roles, notify_user

router = APIRouter(prefix="/password-reset-requests", tags=["Password Recovery"])


def _generate_temp_password() -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(random.choice(alphabet) for _ in range(10)) + "!1"


def _to_out(req: PasswordResetRequest, user: User) -> PasswordResetRequestOut:
    return PasswordResetRequestOut(
        id=req.id,
        username=user.username,
        full_name=user.full_name,
        status=req.status.value if hasattr(req.status, "value") else req.status,
        review_notes=req.review_notes,
        created_at=req.created_at,
    )


@router.post("", status_code=202)
def submit_password_reset_request(payload: PasswordResetRequestCreate, db: Session = Depends(get_db)):
    """
    Public endpoint - no authentication required.
    Always returns the same generic message, whether or not the account
    exists, so the endpoint cannot be used to discover valid usernames/emails.
    """
    identifier = payload.username_or_email.strip()
    user = db.query(User).filter(
        or_(User.username == identifier, User.email == identifier)
    ).first()

    if user and user.is_active:
        existing_pending = db.query(PasswordResetRequest).filter(
            PasswordResetRequest.user_id == user.id,
            PasswordResetRequest.status == AccessRequestStatus.PENDING,
        ).first()
        if not existing_pending:
            req = PasswordResetRequest(user_id=user.id)
            db.add(req)
            db.commit()
            db.refresh(req)
            notify_roles(
                db, [RoleEnum.SYSTEM_ADMIN],
                message=f"{user.full_name} ({user.username}) requested a password reset.",
                notif_type="PASSWORD_RESET_REQUESTED",
                related_entity_type="PasswordResetRequest",
                related_entity_id=req.id,
            )

    return {"message": "If this account exists, your request has been sent to a System Administrator for review."}


@router.get("", response_model=list[PasswordResetRequestOut])
def list_password_reset_requests(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(RoleEnum.SYSTEM_ADMIN)),
):
    requests = db.query(PasswordResetRequest).order_by(PasswordResetRequest.created_at.desc()).all()
    return [_to_out(r, db.query(User).filter(User.id == r.user_id).first()) for r in requests]


@router.post("/{request_id}/approve", response_model=PasswordResetApprovalOut)
def approve_password_reset(
    request_id: str,
    payload: AccessRequestDecision,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(RoleEnum.SYSTEM_ADMIN)),
):
    req = db.query(PasswordResetRequest).filter(PasswordResetRequest.id == request_id).first()
    if not req:
        raise HTTPException(status_code=404, detail="Password reset request not found")
    if req.status != AccessRequestStatus.PENDING:
        raise HTTPException(status_code=400, detail="This request has already been reviewed")

    user = db.query(User).filter(User.id == req.user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="The associated user no longer exists")

    temp_password = _generate_temp_password()
    user.hashed_password = hash_password(temp_password)

    req.status = AccessRequestStatus.APPROVED
    req.review_notes = payload.notes
    req.reviewed_by_user_id = current_user.id
    req.reviewed_at = datetime.utcnow()
    db.commit()
    db.refresh(req)

    record_audit(db, current_user.id, "PASSWORD_RESET_APPROVED", "User", user.id, f"Reset password for {user.username}")
    notify_user(
        db, user.id,
        message="Your password has been reset. A System Administrator will share your new "
                 "temporary password with you through a verified channel.",
        notif_type="PASSWORD_RESET_APPROVED",
    )
    notify_roles(
        db, [RoleEnum.SYSTEM_ADMIN, RoleEnum.BOT_USER],
        message=f"{current_user.full_name} reset the password for {user.full_name} ({user.username}).",
        notif_type="PASSWORD_RESET_APPROVED",
        related_entity_type="User",
        related_entity_id=user.id,
        exclude_user_id=current_user.id,
    )

    return PasswordResetApprovalOut(request=_to_out(req, user), new_temporary_password=temp_password)


@router.post("/{request_id}/reject", response_model=PasswordResetRequestOut)
def reject_password_reset(
    request_id: str,
    payload: AccessRequestDecision,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(RoleEnum.SYSTEM_ADMIN)),
):
    req = db.query(PasswordResetRequest).filter(PasswordResetRequest.id == request_id).first()
    if not req:
        raise HTTPException(status_code=404, detail="Password reset request not found")
    if req.status != AccessRequestStatus.PENDING:
        raise HTTPException(status_code=400, detail="This request has already been reviewed")

    user = db.query(User).filter(User.id == req.user_id).first()

    req.status = AccessRequestStatus.REJECTED
    req.review_notes = payload.notes
    req.reviewed_by_user_id = current_user.id
    req.reviewed_at = datetime.utcnow()
    db.commit()
    db.refresh(req)

    record_audit(db, current_user.id, "PASSWORD_RESET_REJECTED", "User", req.user_id, payload.notes or "")
    if user:
        notify_roles(
            db, [RoleEnum.SYSTEM_ADMIN, RoleEnum.BOT_USER],
            message=f"{current_user.full_name} rejected a password reset request for {user.full_name}.",
            notif_type="PASSWORD_RESET_REJECTED",
            related_entity_type="User",
            related_entity_id=user.id,
            exclude_user_id=current_user.id,
        )

    return _to_out(req, user)
