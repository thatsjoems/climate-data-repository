"""
MODULE: Climate & Financial Analytics - KPI, trend, and exposure calculations.
All figures here are descriptive statistics (totals, averages) computed directly
from the data stored in the database - there is no invented "climate risk score".

TENANT ISOLATION: every function accepts an optional `institution_id`. The API
layer (app/api/analytics.py) is responsible for passing the caller's own
institution_id when the caller is an INSTITUTION_USER, and None (no restriction)
for SYSTEM_ADMIN/BOT_USER. This module never decides who is allowed to see what -
it only applies whatever scope it is given - so the actual authorization
decision lives in one place (the API layer) rather than being duplicated here.

DOUBLE-COUNTING: every monetary/record aggregate excludes SubmissionRecord rows
that failed row-level validation (is_valid == False) AND rows belonging to a
Submission that is REJECTED or SUPERSEDED. A submission is marked SUPERSEDED
automatically when the same institution uploads a newer submission for the same
reporting_period (see app/api/submissions.py) - so only the latest attempt per
institution+period ever contributes to analytics, preventing the same loan from
being counted twice because of a resubmission or correction.
"""
from sqlalchemy.orm import Session
from sqlalchemy import func
import re
from app.models.models import (
    Institution, Submission, SubmissionRecord, ClimateRecord, SubmissionStatus
)

# Submission statuses whose records must NEVER contribute to analytics totals.
EXCLUDED_STATUSES = (SubmissionStatus.REJECTED, SubmissionStatus.SUPERSEDED)


def _active_records_query(db: Session, institution_id: str | None = None):
    """
    Base query: valid rows belonging to a non-rejected, non-superseded submission.
    Always joins Submission so institution scoping and status exclusion are
    enforced in exactly one place.
    """
    query = (
        db.query(SubmissionRecord)
        .join(Submission, Submission.id == SubmissionRecord.submission_id)
        .filter(SubmissionRecord.is_valid == True)  # noqa: E712
        .filter(Submission.status.notin_(EXCLUDED_STATUSES))
    )
    if institution_id:
        query = query.filter(Submission.institution_id == institution_id)
    return query


def get_kpi_summary(db: Session, institution_id: str | None = None) -> dict:
    if institution_id:
        total_institutions = 1
        submission_base = db.query(Submission).filter(Submission.institution_id == institution_id)
    else:
        total_institutions = db.query(Institution).filter(Institution.is_active == True).count()  # noqa: E712
        submission_base = db.query(Submission)

    total_submissions = submission_base.count()

    def count_status(status: SubmissionStatus) -> int:
        return submission_base.filter(Submission.status == status).count()

    records_query = _active_records_query(db, institution_id)

    total_loan = records_query.with_entities(
        func.coalesce(func.sum(SubmissionRecord.loan_amount_tzs), 0.0)
    ).scalar()
    total_collateral = records_query.with_entities(
        func.coalesce(func.sum(SubmissionRecord.collateral_value_tzs), 0.0)
    ).scalar()
    total_borrowers = records_query.filter(
        SubmissionRecord.borrower_name.isnot(None), SubmissionRecord.borrower_name != ""
    ).with_entities(func.count(func.distinct(SubmissionRecord.borrower_name))).scalar()

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
    # Pure meteorological data - not institution-specific, so no tenant scoping applies.
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


def get_hazard_exposure(db: Session, institution_id: str | None = None) -> list[dict]:
    """
    Shows how much loan value sits in areas with reported climate hazard exposure.
    Scoped to a single institution's own data when institution_id is given.
    """
    results = (
        _active_records_query(db, institution_id)
        .with_entities(
            SubmissionRecord.region,
            SubmissionRecord.climate_hazard_exposure,
            func.coalesce(func.sum(SubmissionRecord.loan_amount_tzs), 0.0).label("exposed_amount"),
            func.count(SubmissionRecord.id).label("record_count"),
        )
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


def get_region_map_points(db: Session, institution_id: str | None = None) -> list[dict]:
    """
    Region-level map points for the Geospatial Overview: real hazard-exposure
    figures (from get_hazard_exposure) attached to real region centroid
    coordinates (from geo_reference.py). This is region-level, not exact
    per-loan location - no per-loan coordinates are collected yet.

    A region is only included if we actually have a known centroid for it,
    so an unrecognized/misspelled region name is silently excluded rather
    than plotted at a wrong or default location.
    """
    from app.services.geo_reference import get_region_coordinates

    exposure_rows = get_hazard_exposure(db, institution_id)

    # Collapse per-hazard rows into one point per region (a region may have
    # several hazard types recorded across its submissions).
    by_region: dict[str, dict] = {}
    for row in exposure_rows:
        region = row["region"]
        if region not in by_region:
            coords = get_region_coordinates(region)
            if not coords:
                continue  # unknown region name - do not guess a location
            by_region[region] = {
                "region": region,
                "latitude": coords[0],
                "longitude": coords[1],
                "total_exposure_tzs": 0.0,
                "record_count": 0,
                "hazards": {},
            }
        entry = by_region.get(region)
        if entry is None:
            continue
        entry["total_exposure_tzs"] += row["exposed_loan_amount_tzs"]
        entry["record_count"] += row["record_count"]
        hazard_label = row["hazard_type"] or "None"
        entry["hazards"][hazard_label] = entry["hazards"].get(hazard_label, 0.0) + row["exposed_loan_amount_tzs"]

    points = []
    for entry in by_region.values():
        # The single hazard type with the largest exposure in this region, for marker coloring.
        dominant_hazard = max(entry["hazards"], key=entry["hazards"].get) if entry["hazards"] else "None"
        points.append({
            "region": entry["region"],
            "latitude": entry["latitude"],
            "longitude": entry["longitude"],
            "total_exposure_tzs": entry["total_exposure_tzs"],
            "record_count": entry["record_count"],
            "dominant_hazard": dominant_hazard,
        })
    return points


def get_exposure_snapshot(
    db: Session, region: str | None = None, hazard_type: str | None = None,
    institution_id: str | None = None,
) -> dict:
    """
    Real, queryable figures for a given region/hazard combination (or overall if
    both are omitted) - captured at the moment a Risk Advisory Note is authored,
    so the note stays defensible and auditable. Returns only actual data; never
    fabricates or infers a figure. Risk Advisory Reports are a BOT_USER-only
    feature, so institution_id is normally None (sector-wide view) here, but the
    parameter exists for consistency and future institution-specific advisories.
    """
    query = _active_records_query(db, institution_id)
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


def get_combined_climate_financial_exposure(db: Session, institution_id: str | None = None) -> list[dict]:
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
        _active_records_query(db, institution_id)
        .with_entities(
            SubmissionRecord.region,
            Submission.reporting_period,
            func.coalesce(func.sum(SubmissionRecord.loan_amount_tzs), 0.0).label("total_loan"),
            func.coalesce(func.sum(SubmissionRecord.collateral_value_tzs), 0.0).label("total_collateral"),
            func.count(SubmissionRecord.id).label("record_count"),
        )
        .group_by(SubmissionRecord.region, Submission.reporting_period)
        .all()
    )

    results = []
    for combo in combos:
        parsed = _quarter_to_months(combo.reporting_period)
        avg_rainfall = None
        avg_temp = None
        hazard_types_present: list[str] = []
        climate_data_quality = None

        # Match climate observations two ways, unioned: (a) records that explicitly
        # carry this exact reporting_period (the reliable path, once TMA data is
        # tagged that way), and (b) older/legacy records with no reporting_period
        # set, matched by reconstructing the year/months the quarter covers - a
        # fallback, not the primary path, so this never silently misses data that
        # IS properly tagged.
        filters = [ClimateRecord.region == combo.region]
        period_filter = ClimateRecord.reporting_period == combo.reporting_period
        if parsed:
            year, months = parsed
            legacy_filter = (
                (ClimateRecord.reporting_period.is_(None))
                & (ClimateRecord.year == year)
                & (ClimateRecord.month.in_(months))
            )
            filters.append(period_filter | legacy_filter)
        else:
            filters.append(period_filter)

        climate_rows = (
            db.query(ClimateRecord)
            .filter(*filters)
            # FLAGGED means an analyst has already judged this specific reading
            # unreliable - it must never be blended into a figure presented as
            # informing financial-stability decisions, regardless of source.
            .filter(ClimateRecord.quality_flag != "FLAGGED")
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
            # Honesty rule: never let a blend of SYNTHETIC/UNVALIDATED/VALIDATED
            # readings present itself as one uniform, trustworthy figure - the
            # composition actually used must always be visible alongside it.
            flags_present = sorted({c.quality_flag or "UNVALIDATED" for c in climate_rows})
            if flags_present == ["VALIDATED"]:
                climate_data_quality = "VALIDATED"
            else:
                climate_data_quality = "MIXED (" + ", ".join(flags_present) + ")"

        results.append({
            "region": combo.region,
            "reporting_period": combo.reporting_period,
            "avg_rainfall_mm": avg_rainfall,
            "avg_temperature_c": avg_temp,
            "hazard_types_recorded": hazard_types_present,
            "climate_data_quality": climate_data_quality,
            "total_loan_exposure_tzs": float(combo.total_loan or 0.0),
            "total_collateral_value_tzs": float(combo.total_collateral or 0.0),
            "record_count": combo.record_count,
        })

    return results
