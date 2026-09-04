"""
MODULE: Climate & Financial Analytics - KPI, trend, and exposure calculations.
All figures here are descriptive statistics (totals, averages) computed directly
from the data stored in the database - there is no invented "climate risk score".
"""
from sqlalchemy.orm import Session
from sqlalchemy import func
import re
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

    total_borrowers = db.query(func.count(func.distinct(SubmissionRecord.borrower_name))).filter(
        SubmissionRecord.is_valid == True,  # noqa: E712
        SubmissionRecord.borrower_name.isnot(None),
        SubmissionRecord.borrower_name != "",
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
        "total_borrowers": int(total_borrowers or 0),
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
    Joins SubmissionRecord (loan exposure) with region to show how much loan
    value sits in areas with reported climate hazard exposure.
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


def get_exposure_snapshot(db: Session, region: str | None = None, hazard_type: str | None = None) -> dict:
    """
    Real, queryable figures for a given region/hazard combination (or overall if
    both are omitted) - captured at the moment a Risk Advisory Note is authored,
    so the note stays defensible and auditable. Returns only actual data; never
    fabricates or infers a figure.
    """
    query = db.query(SubmissionRecord).filter(SubmissionRecord.is_valid == True)  # noqa: E712
    if region:
        query = query.filter(SubmissionRecord.region == region)
    if hazard_type:
        query = query.filter(SubmissionRecord.climate_hazard_exposure == hazard_type)

    total_exposure = query.with_entities(
        func.coalesce(func.sum(SubmissionRecord.loan_amount_tzs), 0.0)
    ).scalar() or 0.0
    total_collateral = query.with_entities(
        func.coalesce(func.sum(SubmissionRecord.collateral_value_tzs), 0.0)
    ).scalar() or 0.0
    record_count = query.count()

    snapshot = {
        "region": region,
        "hazard_type": hazard_type,
        "total_loan_exposure_tzs": float(total_exposure),
        "total_collateral_value_tzs": float(total_collateral),
        "matching_record_count": record_count,
    }

    # Attach the most recent real meteorological reading for this region, if any exists -
    # this is what actually lets the analyst combine financial exposure with climate data
    # in a single advisory note, instead of the two datasets living in isolation.
    if region:
        latest_climate = (
            db.query(ClimateRecord)
            .filter(ClimateRecord.region == region)
            .order_by(ClimateRecord.year.desc(), ClimateRecord.month.desc())
            .first()
        )
        if latest_climate:
            snapshot["latest_climate_reading"] = {
                "year": latest_climate.year,
                "month": latest_climate.month,
                "rainfall_mm": latest_climate.rainfall_mm,
                "avg_temperature_c": latest_climate.avg_temperature_c,
                "hazard_type": latest_climate.hazard_type,
                "hazard_severity": latest_climate.hazard_severity,
                "source": latest_climate.source,
            }

    return snapshot


def _quarter_to_months(reporting_period: str) -> tuple[int, list[int]] | None:
    """Parses 'YYYY-Qn' into (year, [month numbers in that quarter]). Returns None if unparseable."""
    match = re.match(r"^(\d{4})-Q([1-4])$", reporting_period.strip())
    if not match:
        return None
    year = int(match.group(1))
    quarter = int(match.group(2))
    start_month = (quarter - 1) * 3 + 1
    return year, [start_month, start_month + 1, start_month + 2]


def get_combined_climate_financial_exposure(db: Session) -> list[dict]:
    """
    THE core ICN aim: combine financial sector data with climate/meteorological data
    so climate impact on financial stability can actually be assessed together,
    rather than the two datasets living in separate, unrelated tables.

    For every (region, reporting_period) pair that has valid submitted loan data,
    this looks up the REAL meteorological readings (rainfall, temperature, hazard)
    recorded for that same region during the matching months/year, and returns
    both sets of figures side by side. No figure here is invented - a null/absent
    climate reading is honestly represented as null, not backfilled with a guess.
    """
    combos = (
        db.query(
            SubmissionRecord.region,
            Submission.reporting_period,
            func.coalesce(func.sum(SubmissionRecord.loan_amount_tzs), 0.0).label("total_loan"),
            func.coalesce(func.sum(SubmissionRecord.collateral_value_tzs), 0.0).label("total_collateral"),
            func.count(SubmissionRecord.id).label("record_count"),
        )
        .join(Submission, Submission.id == SubmissionRecord.submission_id)
        .filter(SubmissionRecord.is_valid == True)  # noqa: E712
        .group_by(SubmissionRecord.region, Submission.reporting_period)
        .all()
    )

    results = []
    for combo in combos:
        parsed = _quarter_to_months(combo.reporting_period)
        avg_rainfall = None
        avg_temp = None
        hazard_types_present: list[str] = []

        if parsed:
            year, months = parsed
            climate_rows = (
                db.query(ClimateRecord)
                .filter(
                    ClimateRecord.region == combo.region,
                    ClimateRecord.year == year,
                    ClimateRecord.month.in_(months),
                )
                .all()
            )
            if climate_rows:
                rainfall_values = [c.rainfall_mm for c in climate_rows if c.rainfall_mm is not None]
                temp_values = [c.avg_temperature_c for c in climate_rows if c.avg_temperature_c is not None]
                avg_rainfall = round(sum(rainfall_values) / len(rainfall_values), 1) if rainfall_values else None
                avg_temp = round(sum(temp_values) / len(temp_values), 1) if temp_values else None
                hazard_types_present = sorted({
                    c.hazard_type for c in climate_rows if c.hazard_type and c.hazard_type != "None"
                })

        results.append({
            "region": combo.region,
            "reporting_period": combo.reporting_period,
            "avg_rainfall_mm": avg_rainfall,
            "avg_temperature_c": avg_temp,
            "hazard_types_recorded": hazard_types_present,
            "total_loan_exposure_tzs": float(combo.total_loan or 0.0),
            "total_collateral_value_tzs": float(combo.total_collateral or 0.0),
            "record_count": combo.record_count,
        })

    return results
