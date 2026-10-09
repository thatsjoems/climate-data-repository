"""
MODULE: Climate Data Analytics & Dashboard KPIs.

TENANT ISOLATION (critical): institution_id is NEVER accepted from the client.
It is always derived server-side from the authenticated user's own record.
An INSTITUTION_USER's scope is hard-coded to their own institution_id; there is
no code path that lets them widen it, even by manipulating query parameters.
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import require_roles
from app.models.models import User, RoleEnum
from app.schemas.schemas import KPISummary, ClimateTrendPoint, HazardExposurePoint, CombinedExposurePoint, RegionMapPoint, ExposurePointsOut, KPISourceOut, PortfolioBreakdownItem
from app.services import analytics_service

router = APIRouter(prefix="/analytics", tags=["Analytics & Dashboard"])

# The hazard types the system knows (the same list the map layer offers); "None" = no hazard recorded.
HAZARD_PATTERN = r"^(Flood|Drought|Landslide|Cyclone|None)$"


def _scope_for(current_user: User) -> str | None:
    """
    Returns the institution_id this user's analytics must be scoped to, or None
    for sector-wide access. This is the ONLY place that decision is made for
    analytics endpoints - every query below routes through it.
    """
    if current_user.role == RoleEnum.INSTITUTION_USER:
        return current_user.institution_id
    return None  # SYSTEM_ADMIN / BOT_USER: full supervisory visibility


@router.get("/kpi-summary", response_model=KPISummary)
def kpi_summary(
    filter_institution_id: str | None = Query(default=None, description="Advanced filter: narrow to one institution (BOT view only)"),
    filter_region: str | None = Query(default=None, description="Advanced filter: narrow to one region"),
    filter_reporting_period: str | None = Query(default=None, description="Advanced filter: narrow to one reporting period"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(RoleEnum.INSTITUTION_USER, RoleEnum.BOT_USER)),
):
    return analytics_service.get_kpi_summary(
        db, institution_id=_scope_for(current_user), filter_institution_id=filter_institution_id,
        filter_region=filter_region, filter_reporting_period=filter_reporting_period,
    )


# The closed lists mirror analytics_service.BREAKDOWN_DIMENSIONS / BREAKDOWN_METRICS.
BREAKDOWN_GROUP_PATTERN = (
    r"^(borrower_type|business_size|currency|loan_type|sector|asset_classification|region|district|ward"
    r"|collateral_type|collateral_sector|collateral_region|institution)$"
)
BREAKDOWN_METRIC_PATTERN = r"^(loan|outstanding|collateral|records|borrowers)$"


@router.get("/portfolio-breakdown", response_model=list[PortfolioBreakdownItem])
def portfolio_breakdown(
    group_by: str = Query(pattern=BREAKDOWN_GROUP_PATTERN, description="Dimension to group by, e.g. sector, region, institution, collateral_type"),
    metric: str = Query(default="loan", pattern=BREAKDOWN_METRIC_PATTERN),
    limit: int = Query(default=6, ge=1, le=25, description="Largest groups to return; the rest are folded into 'Others'"),
    filter_institution_id: str | None = Query(default=None),
    filter_region: str | None = Query(default=None),
    filter_district: str | None = Query(default=None, description="Drill-down below a region"),
    filter_reporting_period: str | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(RoleEnum.INSTITUTION_USER, RoleEnum.BOT_USER)),
):
    """Chart data for the dashboard (loan by sector, by region, by bank; collateral by type ...)."""
    return analytics_service.get_portfolio_breakdown(
        db, group_by=group_by, metric=metric, limit=limit, institution_id=_scope_for(current_user),
        filter_institution_id=filter_institution_id, filter_region=filter_region,
        filter_district=filter_district, filter_reporting_period=filter_reporting_period,
    )


@router.get("/climate-trends", response_model=list[ClimateTrendPoint])
def climate_trends(
    region: str | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(RoleEnum.INSTITUTION_USER, RoleEnum.BOT_USER)),
):
    # Pure meteorological data (not institution-specific) - no tenant scoping needed.
    return analytics_service.get_climate_trends(db, region)


@router.get("/hazard-exposure", response_model=list[HazardExposurePoint])
def hazard_exposure(
    validated_only: bool = Query(default=True, description="Restrict to fully human-reviewed climate readings only"),
    filter_institution_id: str | None = Query(default=None),
    filter_region: str | None = Query(default=None),
    filter_reporting_period: str | None = Query(default=None),
    filter_hazard_type: str | None = Query(default=None, pattern=HAZARD_PATTERN, description="Narrow to regions with this recorded hazard (Flood, Drought, Landslide, Cyclone, None)"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(RoleEnum.INSTITUTION_USER, RoleEnum.BOT_USER)),
):
    return analytics_service.get_hazard_exposure(
        db, institution_id=_scope_for(current_user), validated_only=validated_only,
        filter_institution_id=filter_institution_id, filter_region=filter_region,
        filter_reporting_period=filter_reporting_period, filter_hazard_type=filter_hazard_type,
    )


@router.get("/combined-climate-financial-exposure", response_model=list[CombinedExposurePoint])
def combined_climate_financial_exposure(
    validated_only: bool = Query(default=True, description="Restrict to fully human-reviewed climate readings only"),
    filter_institution_id: str | None = Query(default=None),
    filter_region: str | None = Query(default=None),
    filter_reporting_period: str | None = Query(default=None),
    filter_hazard_type: str | None = Query(default=None, pattern=HAZARD_PATTERN, description="Narrow to regions with this recorded hazard (Flood, Drought, Landslide, Cyclone, None)"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(RoleEnum.INSTITUTION_USER, RoleEnum.BOT_USER)),
):
    """
    THE core ICN aim: real meteorological readings (rainfall/temperature/hazard)
    combined with real financial exposure (loans/collateral) for the same
    region and reporting period - see analytics_service docstring for method.
    """
    return analytics_service.get_combined_climate_financial_exposure(
        db, institution_id=_scope_for(current_user), validated_only=validated_only,
        filter_institution_id=filter_institution_id, filter_region=filter_region,
        filter_reporting_period=filter_reporting_period, filter_hazard_type=filter_hazard_type,
    )


@router.get("/map-points", response_model=list[RegionMapPoint])
def region_map_points(
    validated_only: bool = Query(default=True),
    filter_institution_id: str | None = Query(default=None),
    filter_region: str | None = Query(default=None),
    filter_reporting_period: str | None = Query(default=None),
    filter_hazard_type: str | None = Query(default=None, pattern=HAZARD_PATTERN, description="Narrow to regions with this recorded hazard (Flood, Drought, Landslide, Cyclone, None)"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(RoleEnum.INSTITUTION_USER, RoleEnum.BOT_USER)),
):
    """
    Region-level points for the Geospatial Overview map: real hazard exposure
    from submitted data, attached to real region centroid coordinates. See
    analytics_service.get_region_map_points() for how this is built. Honors
    the same Dashboard Filters/validated_only as KPI, Hazard Exposure, and
    Combined Exposure - the map must never silently show a different scope
    than the rest of the screen.
    """
    return analytics_service.get_region_map_points(
        db, institution_id=_scope_for(current_user), validated_only=validated_only,
        filter_institution_id=filter_institution_id, filter_region=filter_region,
        filter_reporting_period=filter_reporting_period, filter_hazard_type=filter_hazard_type,
    )


@router.get("/exposure-points", response_model=ExposurePointsOut)
def exposure_points(
    filter_institution_id: str | None = Query(default=None),
    filter_region: str | None = Query(default=None),
    filter_reporting_period: str | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(RoleEnum.INSTITUTION_USER, RoleEnum.BOT_USER)),
):
    """
    The ACTUAL per-record latitude/longitude an institution entered on the
    official template - not a region centroid. Same tenant scoping and
    Dashboard Filters as every other analytics endpoint on this screen - see
    analytics_service.get_exposure_points() for the full reasoning.
    """
    return analytics_service.get_exposure_points(
        db, institution_id=_scope_for(current_user),
        filter_institution_id=filter_institution_id, filter_region=filter_region,
        filter_reporting_period=filter_reporting_period,
    )


@router.get("/kpi-sources", response_model=list[KPISourceOut])
def kpi_sources(
    filter_institution_id: str | None = Query(default=None),
    filter_region: str | None = Query(default=None),
    filter_reporting_period: str | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(RoleEnum.INSTITUTION_USER, RoleEnum.BOT_USER)),
):
    """
    Data lineage: the current APPROVED submissions behind the dashboard figures, with the
    institution, reporting period, file, version and loan/collateral totals each one
    contributes. Same tenant scoping and filters as every other analytics endpoint; the
    hazard filter does not apply here (KPI totals are not narrowed by hazard).
    """
    return analytics_service.get_kpi_sources(
        db, institution_id=_scope_for(current_user), filter_institution_id=filter_institution_id,
        filter_region=filter_region, filter_reporting_period=filter_reporting_period,
    )
