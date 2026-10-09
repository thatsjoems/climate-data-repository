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
import logging
import os
import re
import resource
import time
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Response, Query
from sqlalchemy import func, insert
from sqlalchemy.orm import Session, joinedload
from sqlalchemy.exc import IntegrityError

from app.core.database import get_db
from app.core.export_safety import csv_safe_row
from app.core.config import settings
from app.core.deps import get_current_user, require_roles
from app.models.models import (
    Submission, SubmissionRecord, ValidationError as VErrorModel,
    User, RoleEnum, SubmissionStatus,
)
from app.schemas.schemas import SubmissionOut, SubmissionDetailOut, ReviewRequest, ValidationErrorOut, SubmissionRecordOut
from app.services.validation_service import validate_excel_file
from app.services.template_generator import FIELD_NAMES
from app.services.audit_service import record_audit
from app.services.notification_service import notify_roles, notify_user
from app.services.storage_service import storage
from app.core.timeutil import utcnow

router = APIRouter(prefix="/submissions", tags=["Submissions"])
upload_log = logging.getLogger("cdr.upload")

# The loans and findings of an upload are stored in blocks of this many rows, with bulk INSERTs. One ORM object per loan, 100,000 of them held in
# the session until the commit, was slow and used about a gigabyte (docs/LOAD_TESTING.md). A block is also the unit of memory while storing.
STORE_BLOCK = 5000

# Statuses that are still "active" for a given institution+reporting_period -
# i.e. eligible to be superseded by a newer upload, and eligible to block a
# duplicate loan_id. Already-superseded or already-rejected submissions don't
# block anything further.
ACTIVE_STATUSES = (
    SubmissionStatus.PENDING, SubmissionStatus.VALID, SubmissionStatus.INVALID,
)

# APPROVED is intentionally excluded from automatic superseding. An approved
# version remains the authoritative fallback until a replacement itself passes
# validation and review. This prevents an invalid correction from erasing a
# previously approved dataset from analytics.


def detail_page(db: Session, submission: Submission, record_offset: int = 0, record_limit: int = 100,
                error_offset: int = 0, error_limit: int = 100) -> SubmissionDetailOut:
    """
    One submission with ONE PAGE of its rows and ONE PAGE of its findings, and the totals of all of them.

    Used by the detail endpoint and by the answers to an upload and to a review. Those two used to return the submission object itself, whose `records`
    and `errors` are ALL of its rows and findings: for a file of 100,000 loans the application then loaded every loan into memory and wrote them all
    into the answer (about a gigabyte and ten seconds, and an answer far too large for a browser). Found by a load test (docs/LOAD_TESTING.md).
    """
    records_total = db.query(func.count(SubmissionRecord.id)).filter(SubmissionRecord.submission_id == submission.id).scalar() or 0
    errors_total = db.query(func.count(VErrorModel.id)).filter(VErrorModel.submission_id == submission.id).scalar() or 0
    records = (
        db.query(SubmissionRecord).filter(SubmissionRecord.submission_id == submission.id)
        .order_by(SubmissionRecord.row_number, SubmissionRecord.id).offset(record_offset).limit(record_limit).all()
    )
    errors = (
        db.query(VErrorModel).filter(VErrorModel.submission_id == submission.id)
        .order_by(VErrorModel.row_number, VErrorModel.id).offset(error_offset).limit(error_limit).all()
    )
    return SubmissionDetailOut(
        **SubmissionOut.model_validate(submission).model_dump(),
        errors=[ValidationErrorOut.model_validate(e) for e in errors],
        records=[SubmissionRecordOut.model_validate(r) for r in records],
        records_total=records_total, errors_total=errors_total,
    )


@router.post("/upload", response_model=SubmissionDetailOut, status_code=201)
def upload_submission(
    reporting_period: str = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(RoleEnum.INSTITUTION_USER)),
):
    if not current_user.institution_id:
        raise HTTPException(status_code=400, detail="This user is not linked to any institution")

    # Defense-in-depth (Module: reporting period as dropdown): the frontend now
    # offers this as a dropdown, but the API itself must never trust that -
    # anyone calling it directly (a script, a test, a future client) could
    # send anything.
    if not re.match(r"^\d{4}-Q[1-4]$", reporting_period.strip()):
        raise HTTPException(status_code=400, detail=f"Invalid reporting period format '{reporting_period}' - expected YYYY-Qn, e.g. 2026-Q3")

    started = time.perf_counter()
    file_bytes = file.file.read()

    # ---- Secure upload: hard size ceiling before any parsing happens ----
    max_bytes = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
    if len(file_bytes) > max_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"File is too large ({len(file_bytes) / (1024*1024):.1f} MB). "
                   f"Maximum allowed is {settings.MAX_UPLOAD_SIZE_MB} MB.",
        )
    if not file.filename or not file.filename.lower().endswith((".xlsx", ".xls", ".csv")):
        raise HTTPException(status_code=400, detail="Only .xlsx, .xls or .csv files are accepted")
    # Content-type check in addition to extension - a mismatched declared type
    # (e.g. a renamed .exe claiming .xlsx) is rejected before it ever touches disk.
    allowed_content_types = {
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",  # .xlsx
        "application/vnd.ms-excel",  # .xls (Windows browsers also send this for a .csv)
        "text/csv", "application/csv",  # .csv
        "application/octet-stream",  # some browsers/clients send this generically - extension check above still applies
    }
    if file.content_type and file.content_type not in allowed_content_types:
        raise HTTPException(status_code=400, detail=f"Unexpected file content-type: {file.content_type}")

    # Persist the raw file via the storage abstraction (never trust the
    # client's filename for the path) - see app/services/storage_service.py
    # for why this is a single narrow call rather than direct os.* here.
    saved_path = storage.save(file_bytes, "csv" if file.filename.lower().endswith(".csv") else "xlsx")

    try:
        records, issues = validate_excel_file(
            file_bytes, file.filename,
            form_reporting_period=reporting_period,
            max_rows=settings.MAX_UPLOAD_ROWS,
        )
    except Exception as exc:
        # A corrupt/malformed file must never crash the request or take the server down with it.
        # Clean up the orphaned file on disk - a failed upload must not leave permanent debris.
        storage.delete(saved_path)
        raise HTTPException(status_code=400, detail=f"This file could not be processed: {exc}")
    validated = time.perf_counter()

    # Cross-version loan IDs are intentionally allowed here: a new upload for
    # the same institution + reporting period is a correction/replacement
    # version, not a second exposure. Database-level uniqueness is enforced
    # within a single submission (submission_id + loan_id), while the
    # version lineage below determines which version is analytically current.

    total = len(records)
    valid_count = sum(1 for r in records if r.get("is_valid"))
    invalid_count = total - valid_count
    overall_status = SubmissionStatus.VALID if (total > 0 and invalid_count == 0) else SubmissionStatus.INVALID
    if total == 0:
        overall_status = SubmissionStatus.INVALID

    # Build an explicit version chain for this institution/reporting period.
    previous = (
        db.query(Submission)
        .filter(
            Submission.institution_id == current_user.institution_id,
            Submission.reporting_period == reporting_period,
        )
        .order_by(Submission.version_number.desc(), Submission.created_at.desc())
        .first()
    )
    next_version = (previous.version_number + 1) if previous else 1

    # ---- Versioning / authoritative-current selection ----
    # A VALID submission is immediately current only when no APPROVED baseline
    # exists. If an approved baseline exists, a correction remains provisional
    # until a reviewer approves it. This prevents an invalid/unapproved
    # correction from silently replacing authoritative financial exposure.
    #
    # Computed and (where it demotes an existing current version) FLUSHED
    # before the new submission itself is created below - not after, as an
    # earlier version of this function did. The database enforces "at most
    # one current submission per institution+period" with a partial unique
    # index; creating the new is_current=True row before demoting the old
    # one made both rows current at once for the instant between the two
    # writes, which that constraint correctly rejected with an
    # IntegrityError - turning the system's own core "a new correction
    # supersedes the old one" workflow into a 409 on every second VALID
    # upload for the same institution+period. Demoting first, in its own
    # flush, means the new row is never inserted while an old one still
    # claims to be current.
    approved_current = (
        db.query(Submission)
        .filter(
            Submission.institution_id == current_user.institution_id,
            Submission.reporting_period == reporting_period,
            Submission.status == SubmissionStatus.APPROVED,
            Submission.is_current == True,  # noqa: E712
        )
        .first()
    )
    will_be_current = overall_status == SubmissionStatus.VALID and approved_current is None

    if will_be_current:
        current_versions = (
            db.query(Submission)
            .filter(
                Submission.institution_id == current_user.institution_id,
                Submission.reporting_period == reporting_period,
                Submission.is_current == True,  # noqa: E712
            )
            .all()
        )
        for old in current_versions:
            old.is_current = False
            record_audit(
                db, current_user.id, "SUBMISSION_VERSION_REPLACED", "Submission", old.id,
                f"Version {old.version_number} replaced by version {next_version} for {reporting_period}",
                details_json={
                    "old_version": old.version_number,
                    "new_version": next_version,
                    "reporting_period": reporting_period,
                },
                commit=False,
            )
        if current_versions:
            db.flush()  # demote the old current version(s) before the new one is ever inserted

    submission = Submission(
        institution_id=current_user.institution_id,
        submitted_by_user_id=current_user.id,
        file_name=file.filename,
        file_path=saved_path,
        reporting_period=reporting_period,
        status=overall_status,
        version_number=next_version,
        previous_submission_id=previous.id if previous else None,
        is_current=will_be_current,
        total_records=total,
        valid_records=valid_count,
        invalid_records=invalid_count,
    )
    db.add(submission)
    try:
        db.flush()  # obtain submission.id before commit
    except IntegrityError:
        db.rollback()
        storage.delete(saved_path)
        raise HTTPException(status_code=409, detail="This submission conflicts with another submission already being processed. Please retry.")

    try:
        for start in range(0, len(records), STORE_BLOCK):
            db.execute(insert(SubmissionRecord), [
                dict(
                    submission_id=submission.id,
                    row_number=r["row_number"],
                    is_valid=r.get("is_valid", False),
                    **{field: r.get(field) for field in FIELD_NAMES},
                    disbursement_date_value=r.get("disbursement_date_value"),
                    maturity_date_value=r.get("maturity_date_value"),
                    collateral_pledged_date_value=r.get("collateral_pledged_date_value"),
                )
                for r in records[start:start + STORE_BLOCK]
            ])
        for start in range(0, len(issues), STORE_BLOCK):
            db.execute(insert(VErrorModel), [
                dict(
                    submission_id=submission.id,
                    row_number=issue.row_number,
                    column_name=issue.column_name,
                    error_description=issue.description,
                    severity=issue.severity,
                )
                for issue in issues[start:start + STORE_BLOCK]
            ])
    except IntegrityError:
        db.rollback()
        storage.delete(saved_path)
        raise HTTPException(status_code=409, detail="This submission conflicts with another submission already being processed. Please retry.")
    stored = time.perf_counter()

    # Supersede only earlier non-final attempts. An APPROVED baseline is never
    # automatically superseded by an upload; it is superseded only inside the
    # successful APPROVE transaction below.
    if overall_status == SubmissionStatus.VALID:
        stale_attempts = (
            db.query(Submission)
            .filter(
                Submission.institution_id == current_user.institution_id,
                Submission.reporting_period == reporting_period,
                Submission.id != submission.id,
                Submission.status.in_(ACTIVE_STATUSES),
            )
            .all()
        )
        for old in stale_attempts:
            old.status = SubmissionStatus.SUPERSEDED
            old.is_current = False
            record_audit(
                db, current_user.id, "SUBMISSION_SUPERSEDED", "Submission", old.id,
                f"Superseded by version {submission.version_number} for {reporting_period}",
                details_json={
                    "old_version": old.version_number,
                    "new_version": submission.version_number,
                    "reporting_period": reporting_period,
                },
                commit=False,
            )

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        storage.delete(saved_path)
        raise HTTPException(status_code=409, detail="This submission conflicts with another submission already being processed. Please retry.")
    db.refresh(submission)
    committed = time.perf_counter()
    upload_log.info(
        "upload stored: rows=%d findings=%d status=%s validate_s=%.1f store_s=%.1f commit_s=%.1f total_s=%.1f process_peak_mb=%.0f",
        total, len(issues), overall_status.value, validated - started, stored - validated, committed - stored, committed - started,
        resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024,
    )

    record_audit(
        db, current_user.id, "SUBMISSION_CREATED", "Submission", submission.id,
        f"File '{file.filename}' - status: {overall_status.value}"
    )

    institution_name = current_user.institution.name if current_user.institution else "An institution"
    notify_roles(
        db, [RoleEnum.BOT_USER],
        message=f"{institution_name} submitted '{file.filename}' for {reporting_period} "
                 f"({overall_status.value.title()} - {valid_count}/{total} valid records).",
        notif_type="SUBMISSION_UPLOADED",
        related_entity_type="Submission",
        related_entity_id=submission.id,
    )
    return detail_page(db, submission)


@router.get("", response_model=list[SubmissionOut])
def list_submissions(
    response: Response,
    page: int | None = None,
    page_size: int = 50,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(RoleEnum.INSTITUTION_USER, RoleEnum.BOT_USER)),
):
    """
    Without `page`, returns every matching submission (unchanged behaviour -
    the frontend's own history screens call it this way, and today's data
    volumes make that fine). Pass `page` (1-based) to get a bounded slice
    instead, with the true total in the X-Total-Count response header -
    this keeps the response body a plain array either way, so no existing
    caller breaks, while a future/high-volume caller can opt into paging
    without a new endpoint.
    """
    query = db.query(Submission).options(joinedload(Submission.institution))
    # Data isolation: an institution user only sees submissions belonging to their own institution.
    # institution_id is never taken from the request - only from the authenticated user's own record.
    if current_user.role == RoleEnum.INSTITUTION_USER:
        query = query.filter(Submission.institution_id == current_user.institution_id)
    query = query.order_by(Submission.created_at.desc())

    if page is None:
        return query.all()

    page = max(page, 1)
    page_size = max(1, min(page_size, 200))
    total = query.count()
    response.headers["X-Total-Count"] = str(total)
    return query.offset((page - 1) * page_size).limit(page_size).all()


@router.get("/export.csv")
def export_submission_history_csv(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(RoleEnum.INSTITUTION_USER, RoleEnum.BOT_USER)),
):
    """
    CSV export of submission history (Section 20: Reporting - Export
    Dashboard). INSTITUTION_USER gets only their own institution's
    submissions (same isolation rule as list_submissions); BOT_USER gets all.
    Placed before /{submission_id} so "export.csv" is never matched as a
    submission ID by the dynamic route below.
    """
    import csv
    import io as _io
    from fastapi.responses import StreamingResponse
    from datetime import datetime as _dt

    query = db.query(Submission)
    if current_user.role == RoleEnum.INSTITUTION_USER:
        query = query.filter(Submission.institution_id == current_user.institution_id)
    rows = query.order_by(Submission.created_at.desc()).all()

    buffer = _io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow([
        "file_name", "reporting_period", "status", "total_records",
        "valid_records", "invalid_records", "review_notes", "created_at",
    ])
    for s in rows:
        writer.writerow(csv_safe_row([
            s.file_name, s.reporting_period, s.status.value, s.total_records,
            s.valid_records, s.invalid_records, s.review_notes or "", s.created_at.isoformat(),
        ]))

    filename = f"CDR_Submission_History_{utcnow().strftime('%Y%m%d_%H%M')}.csv"
    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.get("/{submission_id}", response_model=SubmissionDetailOut)
def get_submission(
    submission_id: str,
    record_offset: int = Query(0, ge=0, description="First row to return (0-based)"),
    record_limit: int = Query(100, ge=1, le=500, description="Rows per page"),
    error_offset: int = Query(0, ge=0, description="First finding to return (0-based)"),
    error_limit: int = Query(100, ge=1, le=500, description="Findings per page"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(RoleEnum.INSTITUTION_USER, RoleEnum.BOT_USER)),
):
    """
    One submission with ONE PAGE of its rows and ONE PAGE of its findings.

    A file may hold up to 100,000 rows and, if it is badly wrong, as many findings. Returning
    and drawing all of them froze the browser ("Page unresponsive"), so the rows and findings
    are paged: `records` / `errors` hold the requested page in a stable order (row number),
    and `records_total` / `errors_total` give the full counts so the page can show "1-50 of N".
    Authorisation is unchanged and is checked before any row is read.
    """
    submission = db.query(Submission).filter(Submission.id == submission_id).first()
    if not submission:
        raise HTTPException(status_code=404, detail="Submission not found")
    if current_user.role == RoleEnum.INSTITUTION_USER and submission.institution_id != current_user.institution_id:
        raise HTTPException(status_code=403, detail="You do not have permission to view this submission")

    return detail_page(db, submission, record_offset, record_limit, error_offset, error_limit)


@router.get("/{submission_id}/download")
def download_submission_file(
    submission_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(RoleEnum.INSTITUTION_USER, RoleEnum.BOT_USER)),
):
    """
    Lets an institution re-download the exact file they originally uploaded
    (for their own records), and lets a BOT Analyst pull the original file
    while reviewing. Not available to SYSTEM_ADMIN - submission data is a
    BOT Analyst / institution concern, not an administration one.
    """
    submission = db.query(Submission).filter(Submission.id == submission_id).first()
    if not submission:
        raise HTTPException(status_code=404, detail="Submission not found")
    if current_user.role == RoleEnum.INSTITUTION_USER and submission.institution_id != current_user.institution_id:
        raise HTTPException(status_code=403, detail="You do not have permission to download this submission")
    if not os.path.exists(submission.file_path):
        raise HTTPException(status_code=404, detail="The original file is no longer available on the server")

    from fastapi.responses import FileResponse
    is_csv = (submission.file_name or "").lower().endswith(".csv")
    return FileResponse(
        submission.file_path,
        media_type="text/csv" if is_csv else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=submission.file_name,
    )


@router.post("/{submission_id}/review", response_model=SubmissionDetailOut)
def review_submission(
    submission_id: str,
    payload: ReviewRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(RoleEnum.BOT_USER)),
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
        # Approving this version atomically makes it the authoritative current
        # version and retires any prior current version (including an older
        # approved baseline). The historical rows remain untouched.
        #
        # The demotion below is flushed BEFORE this submission's own is_current
        # is set to True - not combined into one flush at commit time. Without
        # this, SQLAlchemy's unit-of-work does not guarantee which UPDATE it
        # emits first: if it happened to write this submission's is_current=True
        # before writing the old version's is_current=False, both rows would be
        # is_current=True at once, which the same partial unique index that
        # protects the upload path (twentieth SRS item) correctly rejects -
        # turning a routine second approval for an institution+period that
        # already had an approved baseline into an IntegrityError. Confirmed
        # by a test that approves two versions of the same submission in
        # sequence, the first genuine exercise of this exact path.
        previous_current = (
            db.query(Submission)
            .filter(
                Submission.institution_id == submission.institution_id,
                Submission.reporting_period == submission.reporting_period,
                Submission.id != submission.id,
                Submission.is_current == True,  # noqa: E712
            )
            .all()
        )
        for old in previous_current:
            old.is_current = False
        if previous_current:
            db.flush()
        submission.status = SubmissionStatus.APPROVED
        submission.is_current = True
    elif decision == "REJECT":
        submission.status = SubmissionStatus.REJECTED
        was_current = submission.is_current
        submission.is_current = False
        if was_current:
            db.flush()  # write this demotion before any fallback is promoted (same ordering hazard as the APPROVE branch above)
            # Restore the newest approved historical version as the fallback
            # authoritative dataset. This is what prevents a rejected
            # correction from making analytics empty or double-counted.
            fallback = (
                db.query(Submission)
                .filter(
                    Submission.institution_id == submission.institution_id,
                    Submission.reporting_period == submission.reporting_period,
                    Submission.status == SubmissionStatus.APPROVED,
                    Submission.id != submission.id,
                )
                .order_by(Submission.version_number.desc(), Submission.created_at.desc())
                .first()
            )
            if fallback:
                fallback.is_current = True
    else:
        raise HTTPException(status_code=400, detail="decision must be APPROVE or REJECT")

    submission.review_notes = payload.notes
    submission.reviewed_by_user_id = current_user.id
    submission.reviewed_at = utcnow()
    db.commit()
    db.refresh(submission)

    record_audit(
        db, current_user.id, "SUBMISSION_APPROVED" if decision == "APPROVE" else "SUBMISSION_REJECTED", "Submission",
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
    return detail_page(db, submission)
