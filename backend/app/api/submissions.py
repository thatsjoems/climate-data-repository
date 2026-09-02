"""
MODULES E, F, G: Data Upload/Submission, Validation, Review.
"""
import os
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.config import settings
from app.core.deps import get_current_user, require_roles
from app.models.models import (
    Submission, SubmissionRecord, ValidationError as VErrorModel,
    User, RoleEnum, SubmissionStatus,
)
from app.schemas.schemas import SubmissionOut, SubmissionDetailOut, ReviewRequest
from app.services.validation_service import validate_excel_file
from app.services.audit_service import record_audit

router = APIRouter(prefix="/submissions", tags=["Submissions"])


@router.post("/upload", response_model=SubmissionDetailOut, status_code=201)
def upload_submission(
    reporting_period: str = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(RoleEnum.INSTITUTION_USER, RoleEnum.SYSTEM_ADMIN)),
):
    if not current_user.institution_id:
        raise HTTPException(status_code=400, detail="This user is not linked to any institution")

    file_bytes = file.file.read()

    # Persist the raw file to disk (uploads/)
    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
    safe_name = f"{uuid.uuid4()}_{file.filename}"
    saved_path = os.path.join(settings.UPLOAD_DIR, safe_name)
    with open(saved_path, "wb") as f:
        f.write(file_bytes)

    records, issues = validate_excel_file(file_bytes, file.filename)

    total = len(records)
    valid_count = sum(1 for r in records if r.get("is_valid"))
    invalid_count = total - valid_count
    overall_status = SubmissionStatus.VALID if (total > 0 and invalid_count == 0) else SubmissionStatus.INVALID
    if total == 0:
        overall_status = SubmissionStatus.INVALID

    submission = Submission(
        institution_id=current_user.institution_id,
        submitted_by_user_id=current_user.id,
        file_name=file.filename,
        file_path=saved_path,
        reporting_period=reporting_period,
        status=overall_status,
        total_records=total,
        valid_records=valid_count,
        invalid_records=invalid_count,
    )
    db.add(submission)
    db.flush()  # obtain submission.id before commit

    for r in records:
        db.add(SubmissionRecord(
            submission_id=submission.id,
            row_number=r["row_number"],
            loan_id=r.get("loan_id"),
            borrower_name=r.get("borrower_name"),
            loan_amount_tzs=r.get("loan_amount_tzs"),
            collateral_type=r.get("collateral_type"),
            collateral_value_tzs=r.get("collateral_value_tzs"),
            region=r.get("region"),
            district=r.get("district"),
            climate_hazard_exposure=r.get("climate_hazard_exposure"),
            is_valid=r.get("is_valid", False),
        ))

    for issue in issues:
        db.add(VErrorModel(
            submission_id=submission.id,
            row_number=issue.row_number,
            column_name=issue.column_name,
            error_description=issue.description,
            severity=issue.severity,
        ))

    db.commit()
    db.refresh(submission)

    record_audit(
        db, current_user.id, "SUBMISSION_CREATED", "Submission", submission.id,
        f"File '{file.filename}' - status: {overall_status.value}"
    )
    return submission


@router.get("", response_model=list[SubmissionOut])
def list_submissions(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = db.query(Submission)
    # Data isolation: an institution user only sees submissions belonging to their own institution
    if current_user.role == RoleEnum.INSTITUTION_USER:
        query = query.filter(Submission.institution_id == current_user.institution_id)
    return query.order_by(Submission.created_at.desc()).all()


@router.get("/{submission_id}", response_model=SubmissionDetailOut)
def get_submission(
    submission_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    submission = db.query(Submission).filter(Submission.id == submission_id).first()
    if not submission:
        raise HTTPException(status_code=404, detail="Submission not found")
    if current_user.role == RoleEnum.INSTITUTION_USER and submission.institution_id != current_user.institution_id:
        raise HTTPException(status_code=403, detail="You do not have permission to view this submission")
    return submission


@router.post("/{submission_id}/review", response_model=SubmissionDetailOut)
def review_submission(
    submission_id: str,
    payload: ReviewRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(RoleEnum.BOT_USER, RoleEnum.SYSTEM_ADMIN)),
):
    submission = db.query(Submission).filter(Submission.id == submission_id).first()
    if not submission:
        raise HTTPException(status_code=404, detail="Submission not found")

    if payload.decision.upper() == "APPROVE":
        submission.status = SubmissionStatus.APPROVED
    elif payload.decision.upper() == "REJECT":
        submission.status = SubmissionStatus.REJECTED
    else:
        raise HTTPException(status_code=400, detail="decision must be APPROVE or REJECT")

    submission.review_notes = payload.notes
    submission.reviewed_by_user_id = current_user.id
    submission.reviewed_at = datetime.utcnow()
    db.commit()
    db.refresh(submission)

    record_audit(
        db, current_user.id, f"SUBMISSION_{payload.decision.upper()}D", "Submission",
        submission.id, payload.notes or ""
    )
    return submission
