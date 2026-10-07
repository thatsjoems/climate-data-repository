"""
MODULE: Integration endpoints for external systems, authenticated by an API key (see
app/core/integration_auth.py and app/api/integration_clients.py). A key has ONE scope:

  READ         read APPROVED data, sector-wide, exactly as a BOT analyst sees it on the dashboard. These endpoints call
               the SAME analytics functions as the dashboard, so a figure here can never differ from the screen.
  INGEST_TMA / INGEST_PMO
               send climate files to POST /integration/climate-data and do nothing else. The data goes through the same
               checks as a manual upload (one shared implementation) and is stored UNVALIDATED.

A key can never do the other scope's thing, use any other endpoint, or read a draft or rejected submission. Every
successful call is written to the audit log with the client's name and the path; refusals are audited with their reason.
"""
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.api.analytics import HAZARD_PATTERN
from app.core.database import get_db
from app.core.config import settings
from app.core.integration_auth import (
    INGEST_SOURCES, audit_integration_read, get_api_client, ingest_key, key_rate_limit_id, read_key,
)
from app.core.rate_limit import limiter
from app.models.models import ApiClient, RoleEnum
from app.schemas.schemas import (
    ClimateIngestionDetailOut, CombinedExposurePoint, ExposurePointsOut, HazardExposurePoint, IntegrationWhoAmI, KPISummary,
    RegionMapPoint,
)
from app.services import analytics_service
from app.services.climate_upload_service import ConcurrentUploadError, batch_with_errors, store_climate_upload
from app.services.notification_service import notify_roles

router = APIRouter(prefix="/integration", tags=["Integration (API key)"])
LIMIT = "120/minute"   # per key


@router.get("/whoami", response_model=IntegrationWhoAmI)
@limiter.limit(LIMIT, key_func=key_rate_limit_id)
def whoami(request: Request, db: Session = Depends(get_db), client: ApiClient = Depends(get_api_client)):
    """A harmless call to test a connection: shows which key this is and when it expires."""
    audit_integration_read(db, client, request)
    access = (
        "read-only access to approved data" if client.scope == "READ"
        else f"may only send climate data files, which are stored as UNVALIDATED (label {INGEST_SOURCES[client.scope]})"
    )
    return IntegrationWhoAmI(
        name=client.name, key_prefix=client.key_prefix, scope=client.scope, expires_at=client.expires_at, access=access,
    )


@router.get("/kpi-summary", response_model=KPISummary)
@limiter.limit(LIMIT, key_func=key_rate_limit_id)
def kpi_summary(
    request: Request,
    filter_institution_id: str | None = Query(default=None),
    filter_region: str | None = Query(default=None),
    filter_reporting_period: str | None = Query(default=None),
    db: Session = Depends(get_db),
    client: ApiClient = Depends(read_key),
):
    result = analytics_service.get_kpi_summary(
        db, institution_id=None, filter_institution_id=filter_institution_id,
        filter_region=filter_region, filter_reporting_period=filter_reporting_period,
    )
    audit_integration_read(db, client, request)
    return result


@router.get("/hazard-exposure", response_model=list[HazardExposurePoint])
@limiter.limit(LIMIT, key_func=key_rate_limit_id)
def hazard_exposure(
    request: Request,
    validated_only: bool = Query(default=True, description="Restrict to fully human-reviewed climate readings only"),
    filter_institution_id: str | None = Query(default=None),
    filter_region: str | None = Query(default=None),
    filter_reporting_period: str | None = Query(default=None),
    filter_hazard_type: str | None = Query(default=None, pattern=HAZARD_PATTERN),
    db: Session = Depends(get_db),
    client: ApiClient = Depends(read_key),
):
    result = analytics_service.get_hazard_exposure(
        db, institution_id=None, validated_only=validated_only,
        filter_institution_id=filter_institution_id, filter_region=filter_region,
        filter_reporting_period=filter_reporting_period, filter_hazard_type=filter_hazard_type,
    )
    audit_integration_read(db, client, request, rows=len(result))
    return result


@router.get("/combined-climate-financial-exposure", response_model=list[CombinedExposurePoint])
@limiter.limit(LIMIT, key_func=key_rate_limit_id)
def combined_climate_financial_exposure(
    request: Request,
    validated_only: bool = Query(default=True, description="Restrict to fully human-reviewed climate readings only"),
    filter_institution_id: str | None = Query(default=None),
    filter_region: str | None = Query(default=None),
    filter_reporting_period: str | None = Query(default=None),
    filter_hazard_type: str | None = Query(default=None, pattern=HAZARD_PATTERN),
    db: Session = Depends(get_db),
    client: ApiClient = Depends(read_key),
):
    result = analytics_service.get_combined_climate_financial_exposure(
        db, institution_id=None, validated_only=validated_only,
        filter_institution_id=filter_institution_id, filter_region=filter_region,
        filter_reporting_period=filter_reporting_period, filter_hazard_type=filter_hazard_type,
    )
    audit_integration_read(db, client, request, rows=len(result))
    return result


@router.get("/map-points", response_model=list[RegionMapPoint])
@limiter.limit(LIMIT, key_func=key_rate_limit_id)
def region_map_points(
    request: Request,
    validated_only: bool = Query(default=True, description="Restrict to fully human-reviewed climate readings only"),
    filter_institution_id: str | None = Query(default=None),
    filter_region: str | None = Query(default=None),
    filter_reporting_period: str | None = Query(default=None),
    filter_hazard_type: str | None = Query(default=None, pattern=HAZARD_PATTERN),
    db: Session = Depends(get_db),
    client: ApiClient = Depends(read_key),
):
    result = analytics_service.get_region_map_points(
        db, institution_id=None, validated_only=validated_only,
        filter_institution_id=filter_institution_id, filter_region=filter_region,
        filter_reporting_period=filter_reporting_period, filter_hazard_type=filter_hazard_type,
    )
    audit_integration_read(db, client, request, rows=len(result))
    return result


@router.get("/exposure-points", response_model=ExposurePointsOut)
@limiter.limit(LIMIT, key_func=key_rate_limit_id)
def exposure_points(
    request: Request,
    filter_institution_id: str | None = Query(default=None),
    filter_region: str | None = Query(default=None),
    filter_reporting_period: str | None = Query(default=None),
    db: Session = Depends(get_db),
    client: ApiClient = Depends(read_key),
):
    result = analytics_service.get_exposure_points(
        db, institution_id=None, filter_institution_id=filter_institution_id,
        filter_region=filter_region, filter_reporting_period=filter_reporting_period,
    )
    audit_integration_read(db, client, request, rows=len(result["loan_points"]) + len(result["collateral_points"]))
    return result


@router.get("/exposure-points.geojson")
@limiter.limit(LIMIT, key_func=key_rate_limit_id)
def exposure_points_geojson(
    request: Request,
    filter_institution_id: str | None = Query(default=None),
    filter_region: str | None = Query(default=None),
    filter_reporting_period: str | None = Query(default=None),
    db: Session = Depends(get_db),
    client: ApiClient = Depends(read_key),
):
    """
    The same loan and collateral points as /exposure-points, as GeoJSON (WGS 84, longitude then latitude), which
    QGIS and ArcGIS open directly. Each feature says whether it is a loan or a collateral location and its amount.
    """
    points = ExposurePointsOut.model_validate(analytics_service.get_exposure_points(
        db, institution_id=None, filter_institution_id=filter_institution_id,
        filter_region=filter_region, filter_reporting_period=filter_reporting_period,
    ))
    features = [
        {
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [p.longitude, p.latitude]},
            "properties": {"kind": kind, "amount_tzs": p.amount_tzs},
        }
        for kind, items in (("loan", points.loan_points), ("collateral", points.collateral_points))
        for p in items
    ]
    audit_integration_read(db, client, request, rows=len(features))
    return JSONResponse({"type": "FeatureCollection", "features": features}, media_type="application/geo+json")


@router.post("/climate-data", response_model=ClimateIngestionDetailOut, status_code=201)
@limiter.limit("30/minute", key_func=key_rate_limit_id)
async def send_climate_data(
    request: Request,
    dataset_name: str | None = Form(default=None, max_length=255),
    dataset_version: str | None = Form(default=None, max_length=50),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    client: ApiClient = Depends(ingest_key),
):
    """
    A TMA or PMO key sends a climate file (CSV or Excel). It goes through exactly the checks of a manual upload and is
    stored as UNVALIDATED: it reaches the analysis only after a BOT analyst promotes it. The source label comes from the
    key (API_KEY_TMA or API_KEY_PMO) and cannot be chosen by the sender. Sending the same file again is safe: what is
    already stored comes back as duplicates, nothing is overwritten. The reply lists the first 500 rejected rows and why, and says how many there are in all.
    """
    name = file.filename or ""
    if not name.lower().endswith((".csv", ".xlsx", ".xls")):
        raise HTTPException(status_code=400, detail="Only .csv or .xlsx files are accepted")
    contents = await file.read()
    size_mb = len(contents) / (1024 * 1024)
    if size_mb > settings.MAX_UPLOAD_SIZE_MB:
        raise HTTPException(status_code=400, detail=f"File exceeds the {settings.MAX_UPLOAD_SIZE_MB}MB limit ({size_mb:.1f}MB)")

    source = INGEST_SOURCES[client.scope]
    try:
        batch = store_climate_upload(
            db, source=source, dataset_name=dataset_name, dataset_version=dataset_version,
            file_name=name, contents=contents, uploaded_by_api_client_id=client.id,
            audit_user_id=None, audit_action="INTEGRATION_INGEST", audit_prefix=f"{client.name}: ",
            audit_details_json={"api_client_id": client.id, "source": source, "scope": client.scope},
        )
    except ConcurrentUploadError:
        raise HTTPException(
            status_code=409,
            detail="One or more observations in this file were inserted by a concurrent upload just now. Send the file again.",
        )
    notify_roles(
        db, [RoleEnum.BOT_USER],
        f"{client.name} delivered {batch.records_accepted} climate record(s) ({source}); they await validation.",
        "INFO", "ClimateIngestionBatch", batch.id,
    )
    return batch_with_errors(db, batch)
