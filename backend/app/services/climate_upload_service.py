"""
Stores one uploaded climate file: validate every row, record the batch, keep the accepted observations as
UNVALIDATED, keep the findings, write the audit event. ONE implementation used by both ways a file can arrive,
so they can never validate differently:

    - a BOT analyst uploading by hand        (POST /api/climate-data/ingest)
    - a system sending with a TMA/PMO key    (POST /api/integration/climate-data)

Nothing is overwritten (an observation already stored is reported as a duplicate), nothing is marked validated
on arrival, and the audit event is written in the same transaction as the data.
"""
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.models import ClimateIngestionBatch, ClimateIngestionError, ClimateRecord
from app.schemas.schemas import ClimateIngestionBatchOut, ClimateIngestionDetailOut, ClimateIngestionErrorOut
from app.services.audit_service import record_audit
from app.services.climate_ingestion_service import parse_and_validate_climate_file


class ConcurrentUploadError(Exception):
    """Another upload inserted the same observation between our duplicate check and our commit."""


def store_climate_upload(
    db: Session, *, source: str, dataset_name: str | None, dataset_version: str | None, file_name: str, contents: bytes,
    uploaded_by_user_id: str | None = None, uploaded_by_api_client_id: str | None = None,
    audit_user_id: str | None = None, audit_action: str = "CLIMATE_DATA_INGESTED",
    audit_prefix: str = "", audit_details_json: dict | None = None,
) -> ClimateIngestionBatch:
    # The observations already stored, for duplicate detection (never overwrite silently)
    existing_rows = db.query(
        ClimateRecord.region, ClimateRecord.district, ClimateRecord.year,
        ClimateRecord.month, ClimateRecord.source_record_id, ClimateRecord.station_id,
    ).all()
    existing_keys = set(existing_rows)

    result = parse_and_validate_climate_file(contents, file_name, existing_keys, max_rows=settings.MAX_UPLOAD_ROWS)

    batch = ClimateIngestionBatch(
        source=source,
        dataset_name=dataset_name,
        dataset_version=dataset_version,
        file_name=file_name,
        uploaded_by_user_id=uploaded_by_user_id,
        uploaded_by_api_client_id=uploaded_by_api_client_id,
        records_received=result.total_rows,
        records_accepted=len(result.accepted_records),
        records_rejected=result.rejected_count,
        records_duplicate=result.duplicate_count,
        status="COMPLETED",
        error_summary=(
            f"{result.rejected_count} rejected, {result.duplicate_count} duplicate "
            f"out of {result.total_rows} rows" if (result.rejected_count or result.duplicate_count) else None
        ),
    )
    db.add(batch)
    db.flush()

    for record in result.accepted_records:
        db.add(ClimateRecord(
            **record,
            batch_id=batch.id,
            source=source,
            quality_flag="UNVALIDATED",  # a human/automated QC pass can promote this later - never assumed valid on arrival
            processing_method="FILE_INGESTION",
        ))

    for issue in result.issues:
        db.add(ClimateIngestionError(
            batch_id=batch.id, row_number=issue.row_number,
            column_name=issue.column_name, error_description=issue.error_description,
        ))

    # Write the audit event in the same transaction as the batch and records.
    # If anything fails before this commit, neither data nor its audit event is persisted.
    record_audit(
        db, audit_user_id, audit_action, "ClimateIngestionBatch", batch.id,
        f"{audit_prefix}{file_name}: {batch.records_accepted} accepted, {batch.records_rejected} rejected, "
        f"{batch.records_duplicate} duplicate",
        details_json=audit_details_json,
        commit=False,
    )
    try:
        db.commit()
    except IntegrityError:
        # The database's own uniqueness guarantee (Alembic migration 8b2f5c1e9a44) is the final backstop.
        db.rollback()
        raise ConcurrentUploadError()
    db.refresh(batch)
    return batch


ERROR_PAGE = 500   # rejected rows returned in one reply; the reply also says how many there are in all


def batch_with_errors(db: Session, batch: ClimateIngestionBatch, offset: int = 0, limit: int = ERROR_PAGE) -> ClimateIngestionDetailOut:
    """
    The batch plus one page of its rejected rows (row, column, reason) and the total. Used by every reply that returns a
    batch, so a sender or an analyst always learns WHICH rows were rejected and why, not just how many. A page, not the lot:
    a file of 100,000 bad rows must not become a 100,000-item reply.
    """
    query = db.query(ClimateIngestionError).filter(ClimateIngestionError.batch_id == batch.id)
    total = query.count()
    rows = query.order_by(ClimateIngestionError.row_number, ClimateIngestionError.id).offset(offset).limit(limit).all()
    return ClimateIngestionDetailOut(
        **ClimateIngestionBatchOut.model_validate(batch).model_dump(),
        errors=[ClimateIngestionErrorOut.model_validate(r) for r in rows], errors_total=total,
    )
