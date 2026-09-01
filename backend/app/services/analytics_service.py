"""
MODULE: Climate & Financial Analytics - hesabu za KPI, mielekeo (trends), na exposure.
Hesabu zote hapa ni descriptive statistics (jumla, wastani) zinazotokana moja kwa moja
na data zilizopo kwenye database - hakuna 'climate risk score' ya kubuni.
"""
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.models.models import (
    Institution, Submission, SubmissionRecord, ClimateRecord, SubmissionStatus
)


def get_kpi_summary(db: Session) -> dict:
    total_institutions = db.query(Institution).filter(Institution.is_active == True).count()  # noqa: E712
    total_submissions = db.query(Submission).count()

    def count_status(status: SubmissionStatus) -> int:
        return db.query(Submission).filter(Submission.status == status).count()

    total_loan = db.query(func.coalesce(func.sum(SubmissionRecord.loan_amount_tzs), 0.0)).filter(
        SubmissionRecord.is_valid == True  # noqa: E712
    ).scalar()
    total_collateral = db.query(func.coalesce(func.sum(SubmissionRecord.collateral_value_tzs), 0.0)).filter(
        SubmissionRecord.is_valid == True  # noqa: E712
    ).scalar()

    return {
        "total_institutions": total_institutions,
        "total_submissions": total_submissions,
        "valid_submissions": count_status(SubmissionStatus.VALID),
        "invalid_submissions": count_status(SubmissionStatus.INVALID),
        "pending_submissions": count_status(SubmissionStatus.PENDING),
        "approved_submissions": count_status(SubmissionStatus.APPROVED),
        "rejected_submissions": count_status(SubmissionStatus.REJECTED),
        "total_loan_exposure_tzs": float(total_loan or 0.0),
        "total_collateral_value_tzs": float(total_collateral or 0.0),
    }


def get_climate_trends(db: Session, region: str | None = None) -> list[dict]:
    query = db.query(
        ClimateRecord.year,
        ClimateRecord.month,
        func.avg(ClimateRecord.rainfall_mm).label("avg_rainfall_mm"),
        func.avg(ClimateRecord.avg_temperature_c).label("avg_temperature_c"),
    )
    if region:
        query = query.filter(ClimateRecord.region == region)
    query = query.group_by(ClimateRecord.year, ClimateRecord.month).order_by(
        ClimateRecord.year, ClimateRecord.month
    )
    return [
        {
            "year": r.year,
            "month": r.month,
            "avg_rainfall_mm": round(r.avg_rainfall_mm, 2) if r.avg_rainfall_mm is not None else None,
            "avg_temperature_c": round(r.avg_temperature_c, 2) if r.avg_temperature_c is not None else None,
        }
        for r in query.all()
    ]


def get_hazard_exposure(db: Session) -> list[dict]:
    """
    Inaunganisha SubmissionRecord (loan exposure) na eneo (region) kuonyesha
    ni kiasi gani cha mikopo kipo kwenye maeneo yenye hatari za kimazingira zilizoripotiwa.
    """
    results = (
        db.query(
            SubmissionRecord.region,
            SubmissionRecord.climate_hazard_exposure,
            func.coalesce(func.sum(SubmissionRecord.loan_amount_tzs), 0.0).label("exposed_amount"),
            func.count(SubmissionRecord.id).label("record_count"),
        )
        .filter(SubmissionRecord.is_valid == True)  # noqa: E712
        .group_by(SubmissionRecord.region, SubmissionRecord.climate_hazard_exposure)
        .all()
    )
    return [
        {
            "region": r.region,
            "hazard_type": r.climate_hazard_exposure,
            "exposed_loan_amount_tzs": float(r.exposed_amount or 0.0),
            "record_count": r.record_count,
        }
        for r in results
    ]
