"""
MODULES E, F, G: Data Upload/Submission, Validation, Review.

WORKFLOW / VERSIONING RULES (see docs/SUBMISSION_LIFECYCLE.md for full detail):
- A submission's status moves PENDING -> VALID/INVALID -> APPROVED/REJECTED.
- Only a VALID submission may be APPROVED. INVALID can only be REJECTED or
  corrected via a brand-new upload - it can never become APPROVED directly.
- Once APPROVED or REJECTED, a submission is final and cannot be re-reviewed.
- Uploading a new submission for the same institution + reporting_period marks
  every earlier, still-active submission for that pair as SUPERSEDED, so
  analytics only ever count the latest attempt (see analytics_service.py).
- A reviewer can never approve/reject their own upload (maker-checker).
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
from app.services.notification_service import notify_roles, notify_user

router = APIRouter(prefix="/submissions", tags=["Submissions"])

# Statuses that are still "active" for a given institution+reporting_period -
# i.e. eligible to be superseded by a newer upload, and eligible to block a
# duplicate loan_id. Already-superseded or already-rejected submissions don't
# block anything further.
ACTIVE_STATUSES = (
    SubmissionStatus.PENDING, SubmissionStatus.VALID, SubmissionStatus.INVALID, SubmissionStatus.APPROVED,
)


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

    # ---- Secure upload: hard size ceiling before any parsing happens ----
    max_bytes = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
    if len(file_bytes) > max_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"File is too large ({len(file_bytes) / (1024*1024):.1f} MB). "
                   f"Maximum allowed is {settings.MAX_UPLOAD_SIZE_MB} MB.",
        )
    if not file.filename or not file.filename.lower().endswith((".xlsx", ".xls")):
        raise HTTPException(status_code=400, detail="Only .xlsx or .xls files are accepted")

    # Persist the raw file to disk with a generated name (never trust the client's filename for the path)
    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
    safe_name = f"{uuid.uuid4()}.xlsx"
    saved_path = os.path.join(settings.UPLOAD_DIR, safe_name)
    with open(saved_path, "wb") as f:
        f.write(file_bytes)

    try:
        records, issues = validate_excel_file(
            file_bytes, file.filename,
            form_reporting_period=reporting_period,
            max_rows=settings.MAX_UPLOAD_ROWS,
        )
    except Exception as exc:
        # A corrupt/malformed file must never crash the request or take the server down with it.
        raise HTTPException(status_code=400, detail=f"This file could not be processed: {exc}")

    # ---- Cross-submission duplicate loan_id check (institution + reporting_period + loan_id) ----
    # Catches a loan re-appearing in a *different* upload for the same period, which an
    # in-file-only check can never see.
    incoming_loan_ids = {r["loan_id"] for r in records if r.get("loan_id") and r.get("is_valid")}
    existing_loan_ids: set[str] = set()
    if incoming_loan_ids:
        existing_loan_ids = {
            row[0] for row in (
                db.query(SubmissionRecord.loan_id)
                .join(Submission, Submission.id == SubmissionRecord.submission_id)
                .filter(
                    Submission.institution_id == current_user.institution_id,
                    Submission.reporting_period == reporting_period,
                    Submission.status.in_(ACTIVE_STATUSES),
                    SubmissionRecord.is_valid == True,  # noqa: E712
                    SubmissionRecord.loan_id.in_(incoming_loan_ids),
                )
                .all()
            )
        }
    if existing_loan_ids:
        from app.services.validation_service import ValidationIssue
        for r in records:
            if r.get("loan_id") in existing_loan_ids:
                r["is_valid"] = False
                issues.append(ValidationIssue(
                    r["row_number"], "loan_id",
                    f"loan_id '{r['loan_id']}' was already submitted for {reporting_period} "
                    f"in an earlier active submission from your institution."
                ))

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

    # ---- Versioning: supersede any earlier active submission for the same institution+period ----
    superseded = (
        db.query(Submission)
        .filter(
            Submission.institution_id == current_user.institution_id,
            Submission.reporting_period == reporting_period,
            Submission.id != submission.id,
            Submission.status.in_(ACTIVE_STATUSES),
        )
        .all()
    )
    for old in superseded:
        was_approved = old.status == SubmissionStatus.APPROVED
        old.status = SubmissionStatus.SUPERSEDED
        record_audit(
            db, current_user.id, "SUBMISSION_SUPERSEDED", "Submission", old.id,
            f"Superseded by newer upload '{file.filename}' for {reporting_period}"
        )
        if was_approved:
            notify_roles(
                db, [RoleEnum.BOT_USER, RoleEnum.SYSTEM_ADMIN],
                message=f"An approved submission for {reporting_period} was superseded by a new upload "
                        f"and needs re-review.",
                notif_type="SUBMISSION_SUPERSEDED",
                related_entity_type="Submission",
                related_entity_id=old.id,
            )

    db.commit()
    db.refresh(submission)

    record_audit(
        db, current_user.id, "SUBMISSION_CREATED", "Submission", submission.id,
        f"File '{file.filename}' - status: {overall_status.value}"
    )

    institution_name = current_user.institution.name if current_user.institution else "An institution"
    notify_roles(
        db, [RoleEnum.BOT_USER, RoleEnum.SYSTEM_ADMIN],
        message=f"{institution_name} submitted '{file.filename}' for {reporting_period} "
                 f"({overall_status.value.title()} - {valid_count}/{total} valid records).",
        notif_type="SUBMISSION_UPLOADED",
        related_entity_type="Submission",
        related_entity_id=submission.id,
    )
    return submission


@router.get("", response_model=list[SubmissionOut])
def list_submissions(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = db.query(Submission)
    # Data isolation: an institution user only sees submissions belonging to their own institution.
    # institution_id is never taken from the request - only from the authenticated user's own record.
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

    # ---- Maker-checker: a reviewer can never approve/reject their own upload ----
    if submission.submitted_by_user_id == current_user.id:
        raise HTTPException(
            status_code=403,
            detail="You cannot review a submission you uploaded yourself. Ask another authorized reviewer.",
        )

    # ---- Strict state-transition guard ----
    if submission.status in (SubmissionStatus.APPROVED, SubmissionStatus.REJECTED, SubmissionStatus.SUPERSEDED):
        raise HTTPException(
            status_code=400,
            detail=f"This submission is already {submission.status.value} and cannot be reviewed again.",
        )

    decision = payload.decision.upper()
    if decision == "APPROVE":
        if submission.status != SubmissionStatus.VALID:
            raise HTTPException(
                status_code=400,
                detail=f"Only a VALID submission can be approved (current status: {submission.status.value}). "
                       f"An INVALID submission must be corrected and resubmitted instead.",
            )
        submission.status = SubmissionStatus.APPROVED
    elif decision == "REJECT":
        submission.status = SubmissionStatus.REJECTED
    else:
        raise HTTPException(status_code=400, detail="decision must be APPROVE or REJECT")

    submission.review_notes = payload.notes
    submission.reviewed_by_user_id = current_user.id
    submission.reviewed_at = datetime.utcnow()
    db.commit()
    db.refresh(submission)

    record_audit(
        db, current_user.id, f"SUBMISSION_{decision}D", "Submission",
        submission.id, payload.notes or ""
    )

    decision_word = "approved" if decision == "APPROVE" else "rejected"
    notify_user(
        db, submission.submitted_by_user_id,
        message=f"Your submission '{submission.file_name}' for {submission.reporting_period} "
                 f"was {decision_word}." + (f" Note: {payload.notes}" if payload.notes else ""),
        notif_type="SUBMISSION_REVIEWED",
        related_entity_type="Submission",
        related_entity_id=submission.id,
    )
    return submission
