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

from app.services.template_generator import REGION_DISTRICTS, HAZARD_OPTIONS

EXPECTED_COLUMNS = [
    "region", "district", "year", "month", "rainfall_mm",
    "temperature_min_c", "temperature_max_c", "avg_temperature_c",
    "hazard_type", "hazard_severity", "station_id", "station_name",
    "latitude", "longitude", "source_record_id",
]

# Canonical hazard taxonomy (Module: hazard normalization) - matches
# HAZARD_OPTIONS used everywhere else in the system (the loan template's own
# dropdown, analytics grouping). Without this, "Flood", "flood", "FLOOD",
# and "Flooding" would each count as a DIFFERENT hazard in analytics -
# silently fragmenting hazard counts, the dominant-hazard calculation, and
# the Hazard Exposure pie chart. A free-text value not recognized here is
# rejected rather than silently coerced to something that might not be what
# was meant.
_HAZARD_SYNONYMS = {
    "drought": "Drought", "flood": "Flood", "flooding": "Flood", "floods": "Flood",
    "cyclone": "Cyclone", "cyclones": "Cyclone",
    "landslide": "Landslide", "landslides": "Landslide", "mudslide": "Landslide",
    "none": "None", "n/a": "None", "": "None",
}

# Generous but real physical bounds (Module: climate physical plausibility) -
# wide enough to never reject a genuine extreme reading, tight enough to
# catch obvious data-entry errors (a negative rainfall, a 500C temperature,
# GPS coordinates outside Earth's valid range).
_MIN_RAINFALL_MM = 0.0
_MAX_RAINFALL_MM = 5000.0  # generous - the wettest single-month totals on Earth are under this
_MIN_TEMPERATURE_C = -20.0
_MAX_TEMPERATURE_C = 55.0
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
    `existing_keys` is the set of (region, district, year, month, source_record_id, station_id
    (with nullable source/station identifiers handled consistently) tuples already in the database, used for duplicate detection -
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
        elif rainfall_mm is not None and not (_MIN_RAINFALL_MM <= rainfall_mm <= _MAX_RAINFALL_MM):
            row_issues.append(IngestionIssue(row_number, "rainfall_mm", f"'{rainfall_mm}' is outside a physically plausible range (0-{_MAX_RAINFALL_MM:.0f} mm)"))

        avg_temp, err = _optional_float("avg_temperature_c")
        if err:
            row_issues.append(err)
        elif avg_temp is not None and not (_MIN_TEMPERATURE_C <= avg_temp <= _MAX_TEMPERATURE_C):
            row_issues.append(IngestionIssue(row_number, "avg_temperature_c", f"'{avg_temp}' is outside a physically plausible range ({_MIN_TEMPERATURE_C:.0f} to {_MAX_TEMPERATURE_C:.0f} °C)"))

        temp_min, err = _optional_float("temperature_min_c")
        if err:
            row_issues.append(err)
        elif temp_min is not None and not (_MIN_TEMPERATURE_C <= temp_min <= _MAX_TEMPERATURE_C):
            row_issues.append(IngestionIssue(row_number, "temperature_min_c", f"'{temp_min}' is outside a physically plausible range ({_MIN_TEMPERATURE_C:.0f} to {_MAX_TEMPERATURE_C:.0f} °C)"))

        temp_max, err = _optional_float("temperature_max_c")
        if err:
            row_issues.append(err)
        elif temp_max is not None and not (_MIN_TEMPERATURE_C <= temp_max <= _MAX_TEMPERATURE_C):
            row_issues.append(IngestionIssue(row_number, "temperature_max_c", f"'{temp_max}' is outside a physically plausible range ({_MIN_TEMPERATURE_C:.0f} to {_MAX_TEMPERATURE_C:.0f} °C)"))

        # Internal consistency: when all three exist, min <= avg <= max must hold -
        # a row where they contradict each other points to a data-entry error,
        # not a real reading.
        if temp_min is not None and temp_max is not None and temp_min > temp_max:
            row_issues.append(IngestionIssue(row_number, "temperature_min_c", f"temperature_min_c ({temp_min}) is greater than temperature_max_c ({temp_max})"))
        if avg_temp is not None and temp_min is not None and avg_temp < temp_min:
            row_issues.append(IngestionIssue(row_number, "avg_temperature_c", f"avg_temperature_c ({avg_temp}) is below temperature_min_c ({temp_min})"))
        if avg_temp is not None and temp_max is not None and avg_temp > temp_max:
            row_issues.append(IngestionIssue(row_number, "avg_temperature_c", f"avg_temperature_c ({avg_temp}) is above temperature_max_c ({temp_max})"))

        latitude, err = _optional_float("latitude")
        if err:
            row_issues.append(err)
        elif latitude is not None and not (-90.0 <= latitude <= 90.0):
            row_issues.append(IngestionIssue(row_number, "latitude", f"'{latitude}' is not a valid latitude (-90 to 90)"))

        longitude, err = _optional_float("longitude")
        if err:
            row_issues.append(err)
        elif longitude is not None and not (-180.0 <= longitude <= 180.0):
            row_issues.append(IngestionIssue(row_number, "longitude", f"'{longitude}' is not a valid longitude (-180 to 180)"))

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

        hazard_type = row.get("hazard_type")
        hazard_type = str(hazard_type).strip() if pd.notna(hazard_type) else None
        if hazard_type:
            _canonical_hazard = _HAZARD_SYNONYMS.get(hazard_type.lower())
            if _canonical_hazard is None:
                row_issues.append(IngestionIssue(
                    row_number, "hazard_type",
                    f"'{hazard_type}' is not a recognized hazard type - use one of: {', '.join(HAZARD_OPTIONS)}"
                ))
            else:
                hazard_type = _canonical_hazard if _canonical_hazard != "None" else None

        source_record_id_raw = row.get("source_record_id")
        source_record_id = str(source_record_id_raw).strip() if pd.notna(source_record_id_raw) else None
        station_id = row.get("station_id")
        station_id = str(station_id).strip() if pd.notna(station_id) else None
        station_name = row.get("station_name")
        station_name = str(station_name).strip() if pd.notna(station_name) else None

        if row_issues:
            result.issues.extend(row_issues)
            result.rejected_count += 1
            continue

        # ---- Duplicate detection (never silently overwrite - Section 8) ----
        # Includes station_id (Module: duplicate identity precision) - without
        # it, two genuinely different stations in the same district/month
        # would collide on a single (region, district, year, month, None) key
        # whenever source_record_id is blank, and the second station's real
        # observation would be wrongly rejected as a duplicate of the first.
        dedup_key = (region, district, year, month, source_record_id, station_id)
        if dedup_key in existing_keys or dedup_key in batch_seen_keys:
            result.issues.append(IngestionIssue(
                row_number, None,
                f"Duplicate observation for {region}/{district or '-'} {year}-{month or '-'} "
                f"(source_record_id={source_record_id or 'none'}, station_id={station_id or 'none'}) - already ingested, skipped"
            ))
            result.duplicate_count += 1
            continue
        batch_seen_keys.add(dedup_key)

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
