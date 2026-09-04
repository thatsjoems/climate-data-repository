"""
MODULE: Climate Data Analytics & Dashboard KPIs.
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.models import User
from app.schemas.schemas import KPISummary, ClimateTrendPoint, HazardExposurePoint, CombinedExposurePoint
from app.services import analytics_service

router = APIRouter(prefix="/analytics", tags=["Analytics & Dashboard"])


@router.get("/kpi-summary", response_model=KPISummary)
def kpi_summary(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return analytics_service.get_kpi_summary(db)


@router.get("/climate-trends", response_model=list[ClimateTrendPoint])
def climate_trends(
    region: str | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return analytics_service.get_climate_trends(db, region)


@router.get("/hazard-exposure", response_model=list[HazardExposurePoint])
def hazard_exposure(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return analytics_service.get_hazard_exposure(db)


@router.get("/combined-climate-financial-exposure", response_model=list[CombinedExposurePoint])
def combined_climate_financial_exposure(
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
):
    """
    THE core ICN aim: real meteorological readings (rainfall/temperature/hazard)
    combined with real financial exposure (loans/collateral) for the same
    region and reporting period - see analytics_service docstring for method.
    """
    return analytics_service.get_combined_climate_financial_exposure(db)
