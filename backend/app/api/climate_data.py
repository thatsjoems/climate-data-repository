"""
MODULE: Climate Data Ingestion & Data Quality (Sections 8 & 19).

Exclusive to BOT_USER (Analyst) - climate data is analytical/data content,
consistent with the rest of this project's strict role separation. Not
available to SYSTEM_ADMIN or INSTITUTION_USER.
"""
import os
import uuid

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.core.database import get_db
from app.core.deps import require_roles
from app.core.config import settings
from app.models.models import (
    ClimateRecord, ClimateIngestionBatch, ClimateIngestionError, User, RoleEnum,
)
from app.schemas.schemas import (
    ClimateIngestionBatchOut, ClimateIngestionDetailOut, DataQualitySummary,
)
from app.services.climate_ingestion_service import parse_and_validate_climate_file
from app.services.template_generator import TANZANIA_REGIONS
from app.services.audit_service import record_audit

router = APIRouter(prefix="/climate-data", tags=["Climate Data Ingestion"])

MAX_CLIMATE_FILE_SIZE_MB = settings.MAX_UPLOAD_SIZE_MB  # reuse the same configured ceiling as submissions


@router.post("/ingest", response_model=ClimateIngestionDetailOut, status_code=201)
async def ingest_climate_file(
    source: str = Form(..., description='e.g. "TMA_FILE" or "MANUAL_UPLOAD" - never invent "TMA_API" unless real'),
    dataset_name: str = Form(default=None),
    dataset_version: str = Form(default=None),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(RoleEnum.BOT_USER)),
):
    """
    Validates and loads a CSV/XLSX of climate observations. This is the
    file-upload adapter of the TMA ingestion architecture (see
    docs/TMA_INGESTION.md) - the same validation pipeline a future real TMA
    feed (API/SFTP/DB) would also go through.
    """
    if not (file.filename.lower().endswith(".csv") or file.filename.lower().endswith((".xlsx", ".xls"))):
        raise HTTPException(status_code=400, detail="Only .csv or .xlsx files are accepted")

    contents = await file.read()
    size_mb = len(contents) / (1024 * 1024)
    if size_mb > MAX_CLIMATE_FILE_SIZE_MB:
        raise HTTPException(status_code=400, detail=f"File exceeds the {MAX_CLIMATE_FILE_SIZE_MB}MB limit ({size_mb:.1f}MB)")

    # Build the existing-observation key set for duplicate detection (never overwrite silently)
    existing_rows = db.query(
        ClimateRecord.region, ClimateRecord.district, ClimateRecord.year,
        ClimateRecord.month, ClimateRecord.source_record_id,
    ).all()
    existing_keys = set(existing_rows)

    result = parse_and_validate_climate_file(contents, file.filename, existing_keys)

    batch = ClimateIngestionBatch(
        source=source,
        dataset_name=dataset_name,
        dataset_version=dataset_version,
        file_name=file.filename,
        uploaded_by_user_id=current_user.id,
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
            source=source,
            quality_flag="UNVALIDATED",  # a human/automated QC pass can promote this later - never assumed valid on arrival
            processing_method="FILE_INGESTION",
        ))

    for issue in result.issues:
        db.add(ClimateIngestionError(
            batch_id=batch.id, row_number=issue.row_number,
            column_name=issue.column_name, error_description=issue.error_description,
        ))

    db.commit()
    db.refresh(batch)

    record_audit(
        db, current_user.id, "CLIMATE_DATA_INGESTED", "ClimateIngestionBatch", batch.id,
        f"{file.filename}: {batch.records_accepted} accepted, {batch.records_rejected} rejected, "
        f"{batch.records_duplicate} duplicate"
    )

    return batch


@router.get("/ingestions", response_model=list[ClimateIngestionBatchOut])
def list_ingestion_batches(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(RoleEnum.BOT_USER)),
):
    return db.query(ClimateIngestionBatch).order_by(ClimateIngestionBatch.created_at.desc()).limit(100).all()


@router.get("/ingestions/{batch_id}", response_model=ClimateIngestionDetailOut)
def get_ingestion_batch(
    batch_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(RoleEnum.BOT_USER)),
):
    batch = db.query(ClimateIngestionBatch).filter(ClimateIngestionBatch.id == batch_id).first()
    if not batch:
        raise HTTPException(status_code=404, detail="Ingestion batch not found")
    return batch


@router.get("/quality-summary", response_model=DataQualitySummary)
def data_quality_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(RoleEnum.BOT_USER)),
):
    """
    Answers: is the climate data complete and trustworthy? (Section 19)
    Every figure here is a direct count from ClimateRecord/ClimateIngestionBatch -
    nothing derived or estimated.
    """
    total = db.query(func.count(ClimateRecord.id)).scalar() or 0
    synthetic = db.query(func.count(ClimateRecord.id)).filter(ClimateRecord.quality_flag == "SYNTHETIC").scalar() or 0
    validated = db.query(func.count(ClimateRecord.id)).filter(ClimateRecord.quality_flag == "VALIDATED").scalar() or 0
    unvalidated = db.query(func.count(ClimateRecord.id)).filter(ClimateRecord.quality_flag == "UNVALIDATED").scalar() or 0
    flagged = db.query(func.count(ClimateRecord.id)).filter(ClimateRecord.quality_flag == "FLAGGED").scalar() or 0

    regions_present = {r[0] for r in db.query(ClimateRecord.region).distinct().all()}
    regions_missing = sorted(set(TANZANIA_REGIONS) - regions_present)

    latest_batch = db.query(ClimateIngestionBatch).order_by(ClimateIngestionBatch.created_at.desc()).first()
    total_batches = db.query(func.count(ClimateIngestionBatch.id)).scalar() or 0
    total_rejected = db.query(func.sum(ClimateIngestionBatch.records_rejected)).scalar() or 0
    total_duplicate = db.query(func.sum(ClimateIngestionBatch.records_duplicate)).scalar() or 0

    return DataQualitySummary(
        total_observations=total,
        synthetic_observations=synthetic,
        validated_observations=validated,
        unvalidated_observations=unvalidated,
        flagged_observations=flagged,
        regions_with_data=len(regions_present),
        regions_missing_data=regions_missing,
        latest_ingestion_at=latest_batch.created_at if latest_batch else None,
        total_ingestion_batches=total_batches,
        total_records_rejected_all_time=int(total_rejected),
        total_records_duplicate_all_time=int(total_duplicate),
    )
