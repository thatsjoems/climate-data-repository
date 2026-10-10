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

DOUBLE-COUNTING: every monetary/record aggregate excludes invalid rows and
uses only Submission.is_current versions with VALID or APPROVED status. A new
VALID correction becomes current; an INVALID/REJECTED correction does not erase
an older APPROVED baseline, which is restored automatically after rejection.
This explicit version-selection rule prevents duplicate exposure across
correction attempts.
"""
from sqlalchemy.orm import Session
from sqlalchemy import func, text, literal_column
import re
from app.models.models import (
    Institution, Submission, SubmissionRecord, ClimateRecord, SubmissionStatus
)

# Working memory PostgreSQL may use, for THIS statement only, to count the distinct borrowers of the current approved loans. With its default (4 MB) it
# sorted 212,000 of them on disk, which was most of the second a dashboard needed (docs/LOAD_TESTING.md). A value only for the transaction (SET LOCAL),
# used only as much as needed: about 13 MB for that many borrowers.
KPI_WORK_MEM = "32MB"

# Submission statuses whose records must NEVER contribute to analytics totals.
EXCLUDED_STATUSES = (
    SubmissionStatus.PENDING,
    SubmissionStatus.INVALID,
    SubmissionStatus.REJECTED,
    SubmissionStatus.SUPERSEDED,
)


def _active_records_query(
    db: Session, institution_id: str | None = None,
    filter_institution_id: str | None = None, filter_region: str | None = None,
    filter_reporting_period: str | None = None,
):
    """
    Base query: valid rows belonging to the current, BOT-APPROVED submission for
    their institution and reporting period. Pending, invalid, rejected,
    superseded, and merely-VALID-but-not-yet-approved submissions never
    contribute to any exposure analytics - approval is the single, explicit
    decision that promotes an institution's reported figures into anything
    this system calculates, displays, or exports (design decision: financial
    figures may appear in submission tracking as soon as they are VALID, but
    are never aggregated, charted, or reported on until a BOT Analyst has
    approved them - there is no separate "provisional analytics" mode).
    Always joins Submission so institution scoping and status exclusion are
    enforced in exactly one place.

    `is_current` is still required alongside `status == APPROVED`: approving a
    corrected version retires the previous version (`is_current = False`) but
    does not change that previous version's own status away from APPROVED, so
    without this check a superseded-but-still-APPROVED submission would be
    double-counted alongside the new current one for the same institution and
    period.

    `institution_id` is the mandatory SECURITY scope (an INSTITUTION_USER's own
    tenant - enforced by the API layer, never optional for that role).
    `filter_institution_id`/`filter_region`/`filter_reporting_period` are
    OPTIONAL analytical narrowing (Module: advanced filtering) - e.g. a BOT
    Analyst voluntarily narrowing a sector-wide view to one institution/region/
    period. These never widen access beyond what `institution_id` already
    allows - they can only narrow further.
    """
    query = (
        db.query(SubmissionRecord)
        .join(Submission, Submission.id == SubmissionRecord.submission_id)
        .filter(
            SubmissionRecord.is_valid == True,  # noqa: E712
            Submission.is_current == True,  # noqa: E712
            Submission.status == SubmissionStatus.APPROVED,
        )
    )
    if institution_id:
        query = query.filter(Submission.institution_id == institution_id)
    if filter_institution_id:
        query = query.filter(Submission.institution_id == filter_institution_id)
    if filter_region:
        query = query.filter(SubmissionRecord.region == filter_region)
    if filter_reporting_period:
        query = query.filter(Submission.reporting_period == filter_reporting_period)
    return query


def get_kpi_summary(
    db: Session, institution_id: str | None = None,
    filter_institution_id: str | None = None, filter_region: str | None = None,
    filter_reporting_period: str | None = None,
) -> dict:
    # Security scope always wins over an analyst-supplied institution filter.
    # An INSTITUTION_USER can never turn a filter parameter into a different
    # tenant, even for KPI submission counts.
    effective_institution = institution_id if institution_id else filter_institution_id
    effective_filter_institution_id = None if institution_id else filter_institution_id

    if effective_institution:
        total_institutions = 1
        submission_base = db.query(Submission).filter(
            Submission.institution_id == effective_institution
        )
    else:
        total_institutions = db.query(Institution).filter(Institution.is_active == True).count()  # noqa: E712
        submission_base = db.query(Submission)

    if filter_reporting_period:
        submission_base = submission_base.filter(Submission.reporting_period == filter_reporting_period)

    # Region is a record-level filter, not a Submission column. Join the
    # records so the KPI submission counts obey the same dashboard scope as
    # loan/collateral totals. DISTINCT prevents one submission with many
    # records in the region from being counted multiple times.
    if filter_region:
        submission_base = (
            submission_base
            .join(SubmissionRecord, SubmissionRecord.submission_id == Submission.id)
            .filter(SubmissionRecord.region == filter_region)
            .distinct()
        )

    total_submissions = submission_base.count()

    def count_status(status: SubmissionStatus) -> int:
        return submission_base.filter(Submission.status == status).count()

    records_query = _active_records_query(
        db, institution_id,
        filter_institution_id=effective_filter_institution_id,
        filter_region=filter_region, filter_reporting_period=filter_reporting_period,
    )

    # Both totals in ONE pass over the loans (they were two passes), then the distinct borrowers as the count of a DISTINCT list, which the database
    # can hash instead of sorting (the same number as count(distinct ...), measured against it in scripts/db_diagnose.py).
    total_loan, total_collateral = records_query.with_entities(
        func.coalesce(func.sum(SubmissionRecord.loan_amount_tzs), 0.0),
        func.coalesce(func.sum(SubmissionRecord.collateral_value_tzs), 0.0),
    ).one()
    if db.get_bind().dialect.name == "postgresql":
        db.execute(text(f"SET LOCAL work_mem = '{KPI_WORK_MEM}'"))
    borrowers = records_query.filter(
        SubmissionRecord.customer_id.isnot(None), SubmissionRecord.customer_id != ""
    ).with_entities(SubmissionRecord.customer_id).distinct().subquery()
    total_borrowers = db.query(func.count()).select_from(borrowers).scalar()

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


def get_hazard_exposure(
    db: Session, institution_id: str | None = None, validated_only: bool = False,
    filter_institution_id: str | None = None, filter_region: str | None = None,
    filter_reporting_period: str | None = None,
    filter_hazard_type: str | None = None,
) -> list[dict]:
    """
    Shows how much loan value sits in areas with a REAL recorded climate
    hazard - derived from actual TMA/PMO-sourced ClimateRecord entries for
    the matching region and reporting period, exactly like Combined
    Climate-Financial Exposure does it (see that function's docstring for
    the full reasoning: FLAGGED readings excluded, reporting_period matched
    directly with a legacy year/month fallback).

    This does NOT read a self-reported hazard field from the institution's
    own submission - BOT's official template has no such column (hazard
    exposure is meant to come from TMA/PMO data, not institutions
    self-declaring their own risk). A region/period with no climate data at
    all correctly shows hazard "None" here - never guessed.

    validated_only: when True, only fully human-reviewed (quality_flag=
    VALIDATED) climate readings count toward the dominant hazard - for a
    supervisory/official view where SYNTHETIC and UNVALIDATED readings
    should not influence a hazard classification presented as authoritative.
    The service-layer default remains False for backward compatibility with
    direct/internal callers; the public API/report default is True, so the
    supervisory dashboard opens in VALIDATED-only mode.
    """
    combos = (
        _active_records_query(
            db, institution_id, filter_institution_id=filter_institution_id,
            filter_region=filter_region, filter_reporting_period=filter_reporting_period,
        )
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

    # Aggregate loan exposure by (region, dominant hazard for that region+period)
    aggregated: dict[tuple[str, str], dict] = {}
    for combo in combos:
        dominant_hazard = "None"
        parsed = _quarter_to_months(combo.reporting_period)
        if validated_only:
            filters = [ClimateRecord.region == combo.region, ClimateRecord.quality_flag == "VALIDATED"]
        else:
            filters = [ClimateRecord.region == combo.region, ClimateRecord.quality_flag != "FLAGGED"]
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

        climate_rows = db.query(ClimateRecord).filter(*filters).all()
        hazard_counts: dict[str, int] = {}
        for c in climate_rows:
            if c.hazard_type and c.hazard_type != "None":
                hazard_counts[c.hazard_type] = hazard_counts.get(c.hazard_type, 0) + 1
        if hazard_counts:
            # The most-frequently recorded hazard for this region/period - a
            # description of the region's recorded climate pattern, NOT a claim
            # that every individual loan below was itself directly affected by
            # this specific hazard (Module: hazard terminology precision).
            dominant_hazard = max(hazard_counts, key=hazard_counts.get)

        key = (combo.region, dominant_hazard)
        if key not in aggregated:
            aggregated[key] = {"region": combo.region, "hazard_type": dominant_hazard, "exposed_loan_amount_tzs": 0.0, "exposed_collateral_value_tzs": 0.0, "record_count": 0}
        aggregated[key]["exposed_loan_amount_tzs"] += float(combo.total_loan or 0.0)
        aggregated[key]["exposed_collateral_value_tzs"] += float(combo.total_collateral or 0.0)
        aggregated[key]["record_count"] += combo.record_count

    rows = list(aggregated.values())
    # Hazard filter (ICN item 9). Each (region, period) is classified under ONE dominant
    # recorded hazard, so a loan is never counted under two hazards. Filtering keeps only
    # the regions whose dominant recorded hazard is the one asked for ("None" = no
    # hazard recorded). It narrows what is shown; it never widens access.
    if filter_hazard_type:
        rows = [r for r in rows if r["hazard_type"] == filter_hazard_type]
    return rows


_SEVERITY_RANK = {"LOW": 1, "MEDIUM": 2, "HIGH": 3}


def get_hazard_summary(
    db: Session, hazard_type: str, reporting_period: str | None = None,
    region: str | None = None, validated_only: bool = True,
) -> dict:
    """
    The climate side of one hazard: in which districts it was recorded, and how severe.
    Only recorded readings are counted (TMA/PMO or manual climate ingestion); nothing is
    estimated, and a district with no reading of the hazard is simply absent - never shown
    as "normal". It does not look at any institution's loans, so it needs no tenant scope
    (like the climate trends) and does not depend on any submission being approved.

    validated_only: only fully reviewed readings (quality_flag VALIDATED), the supervisory
    default used by Hazard Exposure; when False every reading that is not FLAGGED counts.
    Period matching is the same as Hazard Exposure: the reading's own reporting_period, or,
    for older readings that have none, its year and month.
    """
    if validated_only:
        quality = ClimateRecord.quality_flag == "VALIDATED"
    else:
        quality = ClimateRecord.quality_flag != "FLAGGED"

    filters = [quality, ClimateRecord.hazard_type == hazard_type]
    if region:
        filters.append(ClimateRecord.region == region)
    if reporting_period:
        period_filter = ClimateRecord.reporting_period == reporting_period
        parsed = _quarter_to_months(reporting_period)
        if parsed:
            year, months = parsed
            period_filter = period_filter | (
                (ClimateRecord.reporting_period.is_(None))
                & (ClimateRecord.year == year)
                & (ClimateRecord.month.in_(months))
            )
        filters.append(period_filter)

    rows = db.query(ClimateRecord.region, ClimateRecord.district, ClimateRecord.hazard_severity).filter(*filters).all()

    per_district: dict[tuple[str, str], dict] = {}
    regions: set[str] = set()
    without_district = 0
    highest: str | None = None
    for row_region, row_district, severity in rows:
        regions.add(row_region)
        if _SEVERITY_RANK.get(severity, 0) > _SEVERITY_RANK.get(highest, 0):
            highest = severity
        district = (row_district or "").strip()
        if not district:
            without_district += 1
            continue
        entry = per_district.setdefault(
            (row_region, district),
            {"region": row_region, "district": district, "readings": 0, "highest_severity": None},
        )
        entry["readings"] += 1
        if _SEVERITY_RANK.get(severity, 0) > _SEVERITY_RANK.get(entry["highest_severity"], 0):
            entry["highest_severity"] = severity

    districts = sorted(
        per_district.values(),
        key=lambda d: (-_SEVERITY_RANK.get(d["highest_severity"], 0), -d["readings"], d["region"], d["district"]),
    )
    by_severity = {"HIGH": 0, "MEDIUM": 0, "LOW": 0, "NOT_GRADED": 0}
    for d in districts:
        by_severity[d["highest_severity"] or "NOT_GRADED"] += 1

    # What the pickers may offer: the periods and regions that have readings of the chosen quality, whatever else is chosen.
    periods = [
        p for (p,) in db.query(ClimateRecord.reporting_period).filter(quality, ClimateRecord.reporting_period.isnot(None))
        .distinct().all()
    ]
    available_regions = [r for (r,) in db.query(ClimateRecord.region).filter(quality).distinct().all()]

    return {
        "hazard_type": hazard_type,
        "reporting_period": reporting_period,
        "region": region,
        "validated_only": validated_only,
        "districts_affected": len(districts),
        "regions_affected": len(regions),
        "readings": len(rows),
        "readings_without_district": without_district,
        "highest_severity": highest,
        "districts_by_severity": by_severity,
        "districts": districts,
        "available_periods": sorted(periods, reverse=True),
        "available_regions": sorted(available_regions),
    }


def get_exposure_points(
    db: Session, institution_id: str | None = None,
    filter_institution_id: str | None = None, filter_region: str | None = None,
    filter_reporting_period: str | None = None, limit: int = 20000,
) -> dict:
    """
    Individual loan/collateral point coordinates - the ACTUAL latitude/
    longitude an institution entered on each row of the official template
    (loan_latitude/loan_longitude, collateral_latitude/collateral_longitude
    on submission_records), not the region-level centroid every other map
    layer uses. Uses the exact same institution/tenant scoping and status
    filtering as every other analytics function (_active_records_query) - a
    point never appears here that would not also count in the Combined
    Exposure figures.

    Returns two separate lists (loan, collateral) rather than one combined
    list, since a single record legitimately has TWO different locations
    (the loan's own location and, often elsewhere, its collateral's
    location) - collapsing them into one list would either lose one
    location per record or wrongly imply they are always the same place.

    `limit` caps each list independently - a genuine map, not a data
    export; this is a safety bound against an unbounded response, not a
    claim about how much exposure exists (Combined Exposure's totals are
    the authoritative figures either way).
    """
    query = _active_records_query(
        db, institution_id, filter_institution_id=filter_institution_id,
        filter_region=filter_region, filter_reporting_period=filter_reporting_period,
    )
    loan_rows = (
        query.filter(SubmissionRecord.loan_latitude.isnot(None), SubmissionRecord.loan_longitude.isnot(None))
        .with_entities(SubmissionRecord.loan_latitude, SubmissionRecord.loan_longitude, SubmissionRecord.loan_amount_tzs)
        .limit(limit)
        .all()
    )
    collateral_rows = (
        query.filter(SubmissionRecord.collateral_latitude.isnot(None), SubmissionRecord.collateral_longitude.isnot(None))
        .with_entities(SubmissionRecord.collateral_latitude, SubmissionRecord.collateral_longitude, SubmissionRecord.collateral_value_tzs)
        .limit(limit)
        .all()
    )
    return {
        "loan_points": [{"latitude": r[0], "longitude": r[1], "amount_tzs": float(r[2] or 0.0)} for r in loan_rows],
        "collateral_points": [{"latitude": r[0], "longitude": r[1], "amount_tzs": float(r[2] or 0.0)} for r in collateral_rows],
    }


def get_region_map_points(
    db: Session, institution_id: str | None = None, validated_only: bool = False,
    filter_institution_id: str | None = None, filter_region: str | None = None,
    filter_reporting_period: str | None = None,
    filter_hazard_type: str | None = None,
) -> list[dict]:
    """
    Region-level map points for the Geospatial Overview: real hazard-exposure
    figures (from get_hazard_exposure) attached to real region centroid
    coordinates (from geo_reference.py). This is region-level, not exact
    per-loan location - no per-loan coordinates are collected yet.

    A region is only included if we actually have a known centroid for it,
    so an unrecognized/misspelled region name is silently excluded rather
    than plotted at a wrong or default location.

    Accepts the exact same filters as the dashboard's other analytical
    views (Module: map/dashboard filter consistency - found via external
    review: without this, an analyst could narrow the dashboard to one
    institution/region/period/VALIDATED-only, while the map kept silently
    showing the unfiltered sector-wide picture. A supervisory tool must
    never let two parts of the same screen silently disagree about scope.
    """
    from app.services.geo_reference import get_region_coordinates

    exposure_rows = get_hazard_exposure(
        db, institution_id, validated_only=validated_only,
        filter_institution_id=filter_institution_id, filter_region=filter_region,
        filter_reporting_period=filter_reporting_period, filter_hazard_type=filter_hazard_type,
    )

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
                "total_collateral_tzs": 0.0,
                "record_count": 0,
                "hazards": {},
            }
        entry = by_region.get(region)
        if entry is None:
            continue
        entry["total_exposure_tzs"] += row["exposed_loan_amount_tzs"]
        entry["total_collateral_tzs"] += row.get("exposed_collateral_value_tzs", 0.0)
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
            "total_collateral_tzs": entry["total_collateral_tzs"],
            "record_count": entry["record_count"],
            "dominant_hazard": dominant_hazard,
        })
    return points


def get_exposure_snapshot(
    db: Session, region: str | None = None, hazard_type: str | None = None,
    institution_id: str | None = None, reporting_period: str | None = None,
) -> dict:
    """
    Real, queryable figures for a given region/hazard combination (or overall if
    both are omitted) - captured at the moment a Risk Advisory Note is authored,
    so the note stays defensible and auditable. Returns only actual data; never
    fabricates or infers a figure. Risk Advisory Reports are a BOT_USER-only
    feature, so institution_id is normally None (sector-wide view) here, but the
    parameter exists for consistency and future institution-specific advisories.

    Unlike the exploratory dashboard views (Hazard Exposure, Combined Exposure,
    which default to "everything except FLAGGED" with an optional VALIDATED-
    only toggle), a Risk Advisory Note is a formal, archived document - so
    climate data here is ALWAYS restricted to quality_flag == VALIDATED, with
    no toggle. Financial data is restricted to APPROVED submissions only, the
    same as every other analytics function now that dashboards no longer have
    a separate provisional/"early signal" mode - so a published advisory's
    snapshot rests on numbers a human has actually confirmed, exactly as the
    dashboard the analyst was looking at when they wrote it did. If no
    VALIDATED reading exists, `climate_data_note`
    explains this plainly instead of silently attaching a SYNTHETIC/UNVALIDATED one.

    reporting_period (optional): when the analyst scopes the advisory to a
    specific period, financial exposure AND the attached climate reading are
    BOTH restricted to that exact period - never "whatever the latest reading
    happens to be", which could silently be a different quarter than the
    financial figures the advisory is actually about (found via external
    review). When omitted, the advisory is a general/undated note and the
    prior behaviour (latest available reading) applies.
    """
    query = _active_records_query(db, institution_id, filter_reporting_period=reporting_period)
    if region:
        query = query.filter(SubmissionRecord.region == region)
    if hazard_type:
        hazard_climate_filters = [ClimateRecord.hazard_type == hazard_type, ClimateRecord.quality_flag == "VALIDATED"]
        if reporting_period:
            hazard_climate_filters.append(ClimateRecord.reporting_period == reporting_period)
        regions_with_hazard = (
            db.query(ClimateRecord.region)
            .filter(*hazard_climate_filters)
            .distinct()
            .all()
        )
        query = query.filter(SubmissionRecord.region.in_([r[0] for r in regions_with_hazard]))

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
        "reporting_period": reporting_period,
        "total_loan_exposure_tzs": float(total_exposure),
        "total_collateral_value_tzs": float(total_collateral),
        "matching_record_count": record_count,
    }

    # Attach a real meteorological reading for this region, if any exists -
    # this is what actually lets the analyst combine financial exposure with
    # climate data in a single advisory note, instead of the two datasets
    # living in isolation.
    if region:
        # A Risk Advisory Note is a formal, archived supervisory document -
        # held to a stricter standard than the exploratory dashboard views
        # above. Only a fully human-reviewed (VALIDATED) reading may be
        # attached; SYNTHETIC/UNVALIDATED readings are never silently
        # attached to something presented as informing a real decision.
        climate_filters = [ClimateRecord.region == region, ClimateRecord.quality_flag == "VALIDATED"]
        if reporting_period:
            parsed = _quarter_to_months(reporting_period)
            period_filter = ClimateRecord.reporting_period == reporting_period
            if parsed:
                year, months = parsed
                legacy_filter = (
                    (ClimateRecord.reporting_period.is_(None))
                    & (ClimateRecord.year == year)
                    & (ClimateRecord.month.in_(months))
                )
                climate_filters.append(period_filter | legacy_filter)
            else:
                climate_filters.append(period_filter)
        latest_climate = (
            db.query(ClimateRecord)
            .filter(*climate_filters)
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
                "quality_flag": latest_climate.quality_flag,
            }
        else:
            scope = f"{region} / {reporting_period}" if reporting_period else region
            snapshot["climate_data_note"] = (
                f"No VALIDATED climate observation is available for {scope} - "
                f"this advisory is based on financial exposure data only."
            )

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


def get_combined_climate_financial_exposure(
    db: Session, institution_id: str | None = None, validated_only: bool = False,
    filter_institution_id: str | None = None, filter_region: str | None = None,
    filter_reporting_period: str | None = None,
    filter_hazard_type: str | None = None,
) -> list[dict]:
    """
    THE core ICN aim: combine financial sector data with climate/meteorological data
    so climate impact on financial stability can actually be assessed together,
    rather than the two datasets living in separate, unrelated tables.

    For every (region, reporting_period) pair that has valid submitted loan data,
    this looks up the REAL meteorological readings (rainfall, temperature, hazard)
    recorded for that same region during the matching months/year, and returns
    both sets of figures side by side. No figure here is invented - a null/absent
    climate reading is honestly represented as null, not backfilled with a guess.

    validated_only: when True, restricts to fully human-reviewed (quality_flag=
    VALIDATED) readings only - for an official/supervisory view where SYNTHETIC
    and UNVALIDATED readings should not silently inform a figure presented as
    authoritative. The service-layer default remains False for backward compatibility with
    direct/internal callers. The public API/report default is True, so the
    supervisory dashboard opens in VALIDATED-only mode.
    """
    combos = (
        _active_records_query(
            db, institution_id, filter_institution_id=filter_institution_id,
            filter_region=filter_region, filter_reporting_period=filter_reporting_period,
        )
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
            .filter(ClimateRecord.quality_flag == "VALIDATED" if validated_only else
                    # FLAGGED means an analyst has already judged this specific reading
                    # unreliable - it must never be blended into a figure presented as
                    # informing financial-stability decisions, regardless of source.
                    ClimateRecord.quality_flag != "FLAGGED")
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
            elif len(flags_present) == 1:
                # A single uniform quality that isn't VALIDATED (e.g. every
                # contributing reading is UNVALIDATED, or every one is
                # SYNTHETIC) - "MIXED" would be misleading here since nothing
                # is actually blended together.
                climate_data_quality = flags_present[0]
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

    # Hazard filter (ICN item 9): keep the region/period rows where the hazard is among
    # those recorded in the climate data used for the row ("None" = none recorded).
    if filter_hazard_type:
        if filter_hazard_type == "None":
            results = [r for r in results if not r["hazard_types_recorded"]]
        else:
            results = [r for r in results if filter_hazard_type in r["hazard_types_recorded"]]
    return results


def get_kpi_sources(
    db: Session, institution_id: str | None = None,
    filter_institution_id: str | None = None, filter_region: str | None = None,
    filter_reporting_period: str | None = None,
) -> list[dict]:
    """
    Data lineage for the KPI figures: which submissions the numbers come from.

    Returns one row per current, BOT-APPROVED submission that contributes valid rows
    under the given scope and filters - exactly the population get_kpi_summary(),
    get_hazard_exposure() and every other calculation draws on (it reuses the same
    base query, so the two can never disagree). Each row says whose data it is, for
    which reporting period, from which uploaded file and version, how many valid rows
    it contributes under the active filters, and their loan and collateral totals;
    the rows themselves are opened from the existing submission detail view.

    row_validity_pct is valid rows / total rows of the whole file (a descriptive
    ratio, not a risk score). It is None when the file has no rows.
    """
    rows = (
        _active_records_query(
            db, institution_id, filter_institution_id=filter_institution_id,
            filter_region=filter_region, filter_reporting_period=filter_reporting_period,
        )
        .join(Institution, Institution.id == Submission.institution_id)
        .with_entities(
            Submission.id, Submission.institution_id, Institution.name, Submission.reporting_period,
            Submission.file_name, Submission.version_number, Submission.reviewed_at,
            Submission.total_records, Submission.valid_records, Submission.invalid_records,
            func.count(SubmissionRecord.id).label("contributing_records"),
            func.coalesce(func.sum(SubmissionRecord.loan_amount_tzs), 0.0).label("loan_total"),
            func.coalesce(func.sum(SubmissionRecord.collateral_value_tzs), 0.0).label("collateral_total"),
        )
        .group_by(
            Submission.id, Submission.institution_id, Institution.name, Submission.reporting_period,
            Submission.file_name, Submission.version_number, Submission.reviewed_at,
            Submission.total_records, Submission.valid_records, Submission.invalid_records,
        )
        .order_by(Submission.reporting_period.desc(), Institution.name)
        .all()
    )
    out = []
    for r in rows:
        total = r.total_records or 0
        out.append({
            "submission_id": r.id,
            "institution_id": r.institution_id,
            "institution_name": r.name,
            "reporting_period": r.reporting_period,
            "file_name": r.file_name,
            "version_number": r.version_number or 1,
            "reviewed_at": r.reviewed_at,
            "total_records": total,
            "valid_records": r.valid_records or 0,
            "invalid_records": r.invalid_records or 0,
            "contributing_records": r.contributing_records,
            "loan_total_tzs": float(r.loan_total or 0.0),
            "collateral_total_tzs": float(r.collateral_total or 0.0),
            "row_validity_pct": round(100.0 * (r.valid_records or 0) / total, 1) if total else None,
        })
    return out


# ---------------------------------------------------------------------------
# Portfolio breakdown (dashboard charts: loan by sector / region / bank, collateral by type ...)
# ---------------------------------------------------------------------------

# group_by name -> the column to group on. A closed list: the client never supplies a column name.
BREAKDOWN_DIMENSIONS = {
    "borrower_type": SubmissionRecord.client_type,
    "business_size": SubmissionRecord.business_size,
    "currency": SubmissionRecord.currency,
    "loan_type": SubmissionRecord.loan_type,
    "sector": SubmissionRecord.loan_economic_activity,
    "asset_classification": SubmissionRecord.asset_classification,
    "region": SubmissionRecord.region,
    "district": SubmissionRecord.district,
    "ward": SubmissionRecord.ward,
    "collateral_type": SubmissionRecord.collateral_type,
    "collateral_sector": SubmissionRecord.collateral_economic_activity,
    "collateral_region": SubmissionRecord.collateral_region,
    "institution": Institution.name,
}
BREAKDOWN_METRICS = ("loan", "outstanding", "collateral", "records", "borrowers")
UNSPECIFIED_LABEL = "Unspecified"
OTHERS_LABEL = "Others"


def get_portfolio_breakdown(
    db: Session, group_by: str, metric: str = "loan", limit: int = 6,
    institution_id: str | None = None, filter_institution_id: str | None = None,
    filter_region: str | None = None, filter_district: str | None = None,
    filter_reporting_period: str | None = None,
) -> list[dict]:
    """
    Totals of one measure grouped by one dimension, over the same population as every other
    dashboard figure (current, APPROVED, valid rows; tenant scope applied first).

    Returns at most `limit` groups, largest first; the rest are folded into one "Others" group so
    the shares always add up to 100%. Rows with no value in the dimension form "Unspecified".
    `filter_district` drills one level below a region filter (region -> district -> ward).
    """
    if group_by not in BREAKDOWN_DIMENSIONS:
        raise ValueError(f"Unknown group_by: {group_by}")
    if metric not in BREAKDOWN_METRICS:
        raise ValueError(f"Unknown metric: {metric}")

    column = BREAKDOWN_DIMENSIONS[group_by]
    # Inline literals (not bind parameters): PostgreSQL must see the SELECT and GROUP BY expressions as identical.
    label = func.coalesce(func.nullif(func.trim(column), literal_column("''")), literal_column(f"'{UNSPECIFIED_LABEL}'")).label("label")
    if metric == "loan":
        measure = func.coalesce(func.sum(SubmissionRecord.loan_amount_tzs), 0.0)
    elif metric == "outstanding":
        measure = func.coalesce(func.sum(SubmissionRecord.outstanding_principal_tzs), 0.0)
    elif metric == "collateral":
        measure = func.coalesce(func.sum(SubmissionRecord.collateral_value_tzs), 0.0)
    elif metric == "borrowers":
        measure = func.count(func.distinct(SubmissionRecord.customer_id))
    else:
        measure = func.count(SubmissionRecord.id)

    query = _active_records_query(
        db, institution_id, filter_institution_id=filter_institution_id,
        filter_region=filter_region, filter_reporting_period=filter_reporting_period,
    )
    if group_by == "institution":
        query = query.join(Institution, Institution.id == Submission.institution_id)
    if filter_district:
        query = query.filter(SubmissionRecord.district == filter_district)

    rows = (
        query.with_entities(label, measure.label("value"), func.count(SubmissionRecord.id).label("records"))
        .group_by(label)
        .all()
    )
    groups = sorted(
        ({"label": r.label, "value": float(r.value or 0), "record_count": int(r.records)} for r in rows),
        key=lambda g: (-g["value"], g["label"]),
    )
    limit = max(1, limit)
    if len(groups) > limit:
        head, tail = groups[: limit - 1], groups[limit - 1:]
        groups = head + [{
            "label": OTHERS_LABEL, "value": sum(g["value"] for g in tail),
            "record_count": sum(g["record_count"] for g in tail),
        }]
    total = sum(g["value"] for g in groups)
    for g in groups:
        g["share_pct"] = round(100.0 * g["value"] / total, 1) if total > 0 else 0.0
    return groups
