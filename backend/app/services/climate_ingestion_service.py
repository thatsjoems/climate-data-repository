"""
MODULE: Climate Data Ingestion Adapter (Section 8 - TMA ingestion pipeline).

This is the FILE-UPLOAD adapter of the ingestion architecture: an analyst
uploads a CSV/XLSX of climate observations (from TMA or any other approved
source) and this module validates it before it becomes canonical data.

No TMA API is invented here - TMA has not agreed on an integration mechanism
yet. When they do (API, SFTP, DB feed, etc.), that mechanism plugs into the
SAME validation/parsing logic below and produces the same ClimateIngestionBatch
record - only the "how the bytes arrived" step changes.

Pipeline (matches the documented architecture):
  Raw ingestion -> schema mapping -> data-quality checks -> duplicate
  detection -> geographic validation -> canonical ClimateRecord rows
"""
import io
from dataclasses import dataclass, field
from datetime import datetime

import pandas as pd

from app.services.template_generator import REGION_DISTRICTS

EXPECTED_COLUMNS = [
    "region", "district", "year", "month", "rainfall_mm",
    "temperature_min_c", "temperature_max_c", "avg_temperature_c",
    "hazard_type", "hazard_severity", "station_id", "station_name",
    "latitude", "longitude", "source_record_id",
]
REQUIRED_COLUMNS = ["region", "year"]

VALID_HAZARD_SEVERITY = {"LOW", "MEDIUM", "HIGH", None}
CURRENT_YEAR = datetime.utcnow().year


@dataclass
class IngestionIssue:
    row_number: int | None
    column_name: str | None
    error_description: str


@dataclass
class IngestionResult:
    accepted_records: list[dict] = field(default_factory=list)
    rejected_count: int = 0
    duplicate_count: int = 0
    issues: list[IngestionIssue] = field(default_factory=list)
    total_rows: int = 0


def _quarter_for_month(month: int | None) -> int | None:
    if not month or not (1 <= month <= 12):
        return None
    return (month - 1) // 3 + 1


def parse_and_validate_climate_file(
    file_bytes: bytes,
    filename: str,
    existing_keys: set[tuple],
) -> IngestionResult:
    """
    Parses a CSV or XLSX of climate observations and validates every row.
    `existing_keys` is the set of (region, district, year, month, source_record_id
    or None) tuples already in the database, used for duplicate detection -
    duplicates are rejected, never silently overwritten (per Section 8).

    Never fabricates a value: a row with an unusable region/year is rejected
    outright rather than guessed at.
    """
    result = IngestionResult()

    try:
        if filename.lower().endswith(".csv"):
            df = pd.read_csv(io.BytesIO(file_bytes))
        else:
            df = pd.read_excel(io.BytesIO(file_bytes))
    except Exception as exc:
        result.issues.append(IngestionIssue(None, None, f"Could not read the file: {exc}"))
        result.rejected_count = 1
        return result

    missing_cols = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing_cols:
        result.issues.append(IngestionIssue(
            None, None,
            f"Missing required column(s): {', '.join(missing_cols)}. "
            f"Expected columns include: {', '.join(EXPECTED_COLUMNS)}"
        ))
        result.rejected_count = 1
        return result

    result.total_rows = len(df)
    batch_seen_keys: set[tuple] = set()  # catches duplicates *within* this same file too

    for idx, row in df.iterrows():
        row_number = idx + 2  # +1 for header, +1 for 0-index
        row_issues: list[IngestionIssue] = []

        region = str(row.get("region", "")).strip()
        if region not in REGION_DISTRICTS:
            row_issues.append(IngestionIssue(row_number, "region", f"'{region}' is not a recognized Tanzania region"))

        district_raw = row.get("district")
        district = str(district_raw).strip() if pd.notna(district_raw) else None
        if district and region in REGION_DISTRICTS and district not in REGION_DISTRICTS[region]:
            row_issues.append(IngestionIssue(row_number, "district", f"'{district}' does not belong to region '{region}'"))

        year_raw = row.get("year")
        try:
            year = int(year_raw)
            if not (1990 <= year <= CURRENT_YEAR + 1):
                row_issues.append(IngestionIssue(row_number, "year", f"'{year}' is outside a plausible range (1990-{CURRENT_YEAR + 1})"))
        except (ValueError, TypeError):
            year = None
            row_issues.append(IngestionIssue(row_number, "year", f"'{year_raw}' is not a valid year"))

        month_raw = row.get("month")
        month = None
        if pd.notna(month_raw):
            try:
                month = int(month_raw)
                if not (1 <= month <= 12):
                    row_issues.append(IngestionIssue(row_number, "month", f"'{month}' must be between 1 and 12"))
                    month = None
            except (ValueError, TypeError):
                row_issues.append(IngestionIssue(row_number, "month", f"'{month_raw}' is not a valid month"))

        def _optional_float(col):
            val = row.get(col)
            if pd.isna(val) if hasattr(pd, "isna") else val is None:
                return None, None
            try:
                return float(val), None
            except (ValueError, TypeError):
                return None, IngestionIssue(row_number, col, f"'{val}' is not a valid number")

        rainfall_mm, err = _optional_float("rainfall_mm")
        if err:
            row_issues.append(err)
        avg_temp, err = _optional_float("avg_temperature_c")
        if err:
            row_issues.append(err)
        temp_min, err = _optional_float("temperature_min_c")
        if err:
            row_issues.append(err)
        temp_max, err = _optional_float("temperature_max_c")
        if err:
            row_issues.append(err)
        latitude, err = _optional_float("latitude")
        if err:
            row_issues.append(err)
        longitude, err = _optional_float("longitude")
        if err:
            row_issues.append(err)

        if rainfall_mm is None and avg_temp is None and temp_min is None and temp_max is None:
            row_issues.append(IngestionIssue(
                row_number, None,
                "Row has no measurement at all (rainfall_mm, avg_temperature_c, temperature_min_c, "
                "temperature_max_c are all empty) - nothing to record"
            ))

        hazard_severity = row.get("hazard_severity")
        hazard_severity = str(hazard_severity).strip().upper() if pd.notna(hazard_severity) else None
        if hazard_severity not in VALID_HAZARD_SEVERITY:
            row_issues.append(IngestionIssue(row_number, "hazard_severity", f"'{hazard_severity}' must be LOW, MEDIUM, HIGH, or blank"))

        source_record_id_raw = row.get("source_record_id")
        source_record_id = str(source_record_id_raw).strip() if pd.notna(source_record_id_raw) else None

        if row_issues:
            result.issues.extend(row_issues)
            result.rejected_count += 1
            continue

        # ---- Duplicate detection (never silently overwrite - Section 8) ----
        dedup_key = (region, district, year, month, source_record_id)
        if dedup_key in existing_keys or dedup_key in batch_seen_keys:
            result.issues.append(IngestionIssue(
                row_number, None,
                f"Duplicate observation for {region}/{district or '-'} {year}-{month or '-'} "
                f"(source_record_id={source_record_id or 'none'}) - already ingested, skipped"
            ))
            result.duplicate_count += 1
            continue
        batch_seen_keys.add(dedup_key)

        hazard_type = row.get("hazard_type")
        hazard_type = str(hazard_type).strip() if pd.notna(hazard_type) else None
        station_id = row.get("station_id")
        station_id = str(station_id).strip() if pd.notna(station_id) else None
        station_name = row.get("station_name")
        station_name = str(station_name).strip() if pd.notna(station_name) else None

        result.accepted_records.append({
            "region": region,
            "district": district,
            "year": year,
            "month": month,
            "rainfall_mm": rainfall_mm,
            "avg_temperature_c": avg_temp,
            "temperature_min_c": temp_min,
            "temperature_max_c": temp_max,
            "hazard_type": hazard_type,
            "hazard_severity": hazard_severity,
            "station_id": station_id,
            "station_name": station_name,
            "latitude": latitude,
            "longitude": longitude,
            "source_record_id": source_record_id,
            "reporting_period": f"{year}-Q{_quarter_for_month(month)}" if month else None,
            "period_type": "MONTHLY" if month else "ANNUAL",
        })

    return result
