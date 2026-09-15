"""
MODULE: Climate Data Ingestion & Data Quality (Sections 8 & 19).

Exclusive to BOT_USER (Analyst) - climate data is analytical/data content,
consistent with the rest of this project's strict role separation. Not
available to SYSTEM_ADMIN or INSTITUTION_USER.

NOTE: the /ingest endpoint is an INTERIM MANUAL BRIDGE, not the intended
final architecture - see docs/TMA_INGESTION.md. Once TMA agrees on a real
feed mechanism, this manual step is meant to disappear; only the underlying
validation logic in climate_ingestion_service.py is expected to persist.
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
    ClimateQCPromoteRequest, ClimateQCPromoteResult,
)
from app.services.climate_ingestion_service import parse_and_validate_climate_file
from app.services.template_generator import TANZANIA_REGIONS
from app.services.audit_service import record_audit

router = APIRouter(prefix="/climate-data", tags=["Climate Data Ingestion"])

MAX_CLIMATE_FILE_SIZE_MB = settings.MAX_UPLOAD_SIZE_MB  # reuse the same configured ceiling as submissions

# Provenance control (Module: source integrity) - found via external review:
# an unrestricted free-text "source" field let an analyst label ANY file
# "TMA_FILE", making it indistinguishable from a genuinely verified feed once
# stored. Every option here is honest about what this pipeline actually is:
# a human manually uploading a file and asserting where they believe it came
# from - not a cryptographically or systematically verified integration.
# There is deliberately no "TMA_OFFICIAL"/"TMA_API" option: that would only
# become truthful once a real, authenticated TMA integration exists.
ALLOWED_CLIMATE_SOURCES = {"MANUAL_TMA_FILE", "MANUAL_PMO_FILE", "MANUAL_OTHER_FILE"}


@router.post("/ingest", response_model=ClimateIngestionDetailOut, status_code=201)
async def ingest_climate_file(
    source: str = Form(..., description=f"One of: {', '.join(sorted(ALLOWED_CLIMATE_SOURCES))} - self-declared by the uploading analyst, not independently verified"),
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

    if source not in ALLOWED_CLIMATE_SOURCES:
        raise HTTPException(
            status_code=400,
            detail=f"'{source}' is not a recognized source - must be one of: {', '.join(sorted(ALLOWED_CLIMATE_SOURCES))}",
        )

    contents = await file.read()
    size_mb = len(contents) / (1024 * 1024)
    if size_mb > MAX_CLIMATE_FILE_SIZE_MB:
        raise HTTPException(status_code=400, detail=f"File exceeds the {MAX_CLIMATE_FILE_SIZE_MB}MB limit ({size_mb:.1f}MB)")

    # Build the existing-observation key set for duplicate detection (never overwrite silently)
    existing_rows = db.query(
        ClimateRecord.region, ClimateRecord.district, ClimateRecord.year,
        ClimateRecord.month, ClimateRecord.source_record_id, ClimateRecord.station_id,
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


@router.post("/promote", response_model=ClimateQCPromoteResult)
def promote_climate_records(
    payload: ClimateQCPromoteRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(RoleEnum.BOT_USER)),
):
    """
    Human QC action: an Analyst who has reviewed the readings for a specific
    region + reporting period marks them VALIDATED (fit to inform official
    analytics and Risk Advisory Notes) or FLAGGED (rejected - excluded from
    every calculation that uses climate data). Only currently-UNVALIDATED
    records are affected - SYNTHETIC demo data is never silently reclassified
    as if a human had reviewed real TMA data, and an already-decided record
    is not re-decided by a second promote call (re-run the ingestion or
    contact an admin if a correction is genuinely needed).

    This is deliberately scoped to (region, reporting_period) rather than a
    single row or a whole ingestion batch: ClimateRecord has no batch foreign
    key (see ClimateIngestionBatch's own docstring), and per-row promotion
    would not scale to real TMA data volumes. Region+period matches exactly
    how climate data is already looked up everywhere else in this system
    (Combined Exposure, Hazard Exposure, Risk Advisory).
    """
    if payload.new_quality_flag not in ("VALIDATED", "FLAGGED"):
        raise HTTPException(status_code=400, detail="new_quality_flag must be 'VALIDATED' or 'FLAGGED'")

    records = (
        db.query(ClimateRecord)
        .filter(
            ClimateRecord.region == payload.region,
            ClimateRecord.reporting_period == payload.reporting_period,
            ClimateRecord.quality_flag == "UNVALIDATED",
        )
        .all()
    )
    for r in records:
        r.quality_flag = payload.new_quality_flag
        r.processing_method = f"QC_PROMOTED_BY_{current_user.username}"
    db.commit()

    record_audit(
        db, current_user.id, "CLIMATE_DATA_QC_PROMOTED", "ClimateRecord", None,
        f"{len(records)} UNVALIDATED reading(s) for {payload.region}/{payload.reporting_period} "
        f"marked {payload.new_quality_flag} by {current_user.username}"
        + (f" - Reason: {payload.reason}" if payload.reason else ""),
    )

    return ClimateQCPromoteResult(
        region=payload.region, reporting_period=payload.reporting_period,
        new_quality_flag=payload.new_quality_flag, records_updated=len(records),
    )


@router.get("/unvalidated-groups")
def list_unvalidated_groups(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(RoleEnum.BOT_USER)),
):
    """
    Lists every (region, reporting_period) combination that currently has at
    least one UNVALIDATED reading, with a count - so the Climate QC screen
    can show the Analyst exactly what is waiting for review without them
    needing to already know which regions/periods to check.
    """
    rows = (
        db.query(
            ClimateRecord.region, ClimateRecord.reporting_period,
            func.count(ClimateRecord.id).label("count"),
        )
        .filter(ClimateRecord.quality_flag == "UNVALIDATED", ClimateRecord.reporting_period.isnot(None))
        .group_by(ClimateRecord.region, ClimateRecord.reporting_period)
        .order_by(ClimateRecord.region, ClimateRecord.reporting_period)
        .all()
    )
    return [{"region": r.region, "reporting_period": r.reporting_period, "count": r.count} for r in rows]
