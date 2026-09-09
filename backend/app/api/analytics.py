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
from app.schemas.schemas import KPISummary, ClimateTrendPoint, HazardExposurePoint, CombinedExposurePoint
from app.services import analytics_service

router = APIRouter(prefix="/analytics", tags=["Analytics & Dashboard"])


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
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(RoleEnum.INSTITUTION_USER, RoleEnum.BOT_USER)),
):
    return analytics_service.get_kpi_summary(db, institution_id=_scope_for(current_user))


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
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(RoleEnum.INSTITUTION_USER, RoleEnum.BOT_USER)),
):
    return analytics_service.get_hazard_exposure(db, institution_id=_scope_for(current_user))


@router.get("/combined-climate-financial-exposure", response_model=list[CombinedExposurePoint])
def combined_climate_financial_exposure(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(RoleEnum.INSTITUTION_USER, RoleEnum.BOT_USER)),
):
    """
    THE core ICN aim: real meteorological readings (rainfall/temperature/hazard)
    combined with real financial exposure (loans/collateral) for the same
    region and reporting period - see analytics_service docstring for method.
    """
    return analytics_service.get_combined_climate_financial_exposure(db, institution_id=_scope_for(current_user))
