"""
MODULE F: Automated Data Validation.

Rebuilt against BOT's own official 38-column Climate Data Template (see
template_generator.py). Reads an uploaded Excel file and validates it against
that exact structure. Returns: (list of parsed records, list of validation
issues found).
"""
import io
import math
import pandas as pd
from app.services.template_generator import (
    REQUIRED_COLUMNS, TANZANIA_REGIONS, HAZARD_OPTIONS, COLUMNS, FIELD_NAMES,
    CLIENT_TYPES, BUSINESS_SIZES, LOAN_TYPES, CURRENCIES, LOAN_ECONOMIC_ACTIVITIES,
    ASSET_CLASSIFICATIONS, COLLATERAL_TYPES, YES_NO,
)
from app.services import geo_lookup as geo
from app.services.geo_reference import get_region_coordinates

# A row's GPS coordinates are flagged (not rejected outright - see the
# reasoning in docs/ASSUMPTIONS_AND_LIMITATIONS.md) when they fall further
# than this from the SELECTED region's own centroid. This is a real, honest
# limitation: we have region centroids, not district/ward boundary polygons,
# so this catches gross mismatches (e.g. Mbeya's coordinates entered under
# Morogoro) without false-flagging correct points in Tanzania's largest
# regions, which can legitimately span more than this from their centroid.
GPS_MISMATCH_WARNING_KM = 300

# Header row layout in the generated template (see template_generator.py) -
# used only to compute the correct display row number for error messages.
HEADER_ROW_IN_TEMPLATE = 9
EXAMPLE_ROW_IN_TEMPLATE = 10


class ValidationIssue:
    def __init__(self, row_number, column_name, description, severity="ERROR"):
        self.row_number = row_number
        self.column_name = column_name
        self.description = description
        self.severity = severity


def _haversine_km(lat1, lon1, lat2, lon2) -> float:
    R = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlambda / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def _clean_str(val) -> str:
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return ""
    s = str(val).strip()
    return "" if s.lower() == "nan" else s


def _clean_float(val):
    if val is None or (isinstance(val, float) and pd.isna(val)) or _clean_str(val) == "":
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return "INVALID"


def validate_excel_file(
    file_bytes: bytes,
    filename: str,
    form_reporting_period: str | None = None,
    max_rows: int = 100000,
):
    """
    form_reporting_period: the single reporting date/period entered on the
    upload form - matching BOT's own template, which states this ONCE per
    file ("LOAN AND COLLATERAL DATA AS AT ___") rather than as a per-row
    column. It is attached to the Submission as a whole, not validated
    per-row here (there is no per-row column to check it against anymore).
    """
    issues: list[ValidationIssue] = []
    records: list[dict] = []

    # ---- 1. File-level validation ----
    if not (filename.lower().endswith(".xlsx") or filename.lower().endswith(".xls")):
        issues.append(ValidationIssue(None, None, "Invalid file type - must be .xlsx or .xls"))
        return records, issues

    try:
        raw = pd.read_excel(io.BytesIO(file_bytes), sheet_name="Loan_Collateral_Data", header=None)
    except Exception:
        try:
            raw = pd.read_excel(io.BytesIO(file_bytes), header=None)
        except Exception as exc:
            issues.append(ValidationIssue(None, None, f"Could not read the Excel file: {exc}"))
            return records, issues

    # The template's header row is fixed (row 9, 1-indexed) with an example
    # row directly below it (row 10) - locate it defensively in case a user
    # inserted/removed rows, by finding the row containing our known first
    # header label, rather than assuming a hardcoded position.
    header_label = COLUMNS[0][1]
    header_row_idx = None
    for i in range(min(20, len(raw))):
        if _clean_str(raw.iloc[i, 0]) == header_label:
            header_row_idx = i
            break
    if header_row_idx is None:
        issues.append(ValidationIssue(
            None, None,
            "Could not find the expected column headers (starting with "
            f"'{header_label}'). Please use the official standardized template without "
            "renaming or removing the header row."
        ))
        return records, issues

    col_map = {}  # field_name -> dataframe column index
    header_values = raw.iloc[header_row_idx]
    label_to_field = {label: field for field, label in COLUMNS}
    for col_idx, label in enumerate(header_values):
        label_clean = _clean_str(label)
        if label_clean in label_to_field:
            col_map[label_to_field[label_clean]] = col_idx

    missing_cols = [f for f in REQUIRED_COLUMNS if f not in col_map]
    if missing_cols:
        missing_labels = [dict(COLUMNS)[f] for f in missing_cols]
        issues.append(ValidationIssue(
            None, None,
            f"The following required columns are missing from the file: {', '.join(missing_labels)}. "
            f"Please use the standardized template without renaming its headers."
        ))
        return records, issues

    data_rows = raw.iloc[header_row_idx + 1:].reset_index(drop=True)

    # ---- 2. Row-count limit ----
    if len(data_rows) > max_rows:
        issues.append(ValidationIssue(
            None, None,
            f"This file has {len(data_rows)} data rows, which exceeds the maximum of {max_rows} "
            f"allowed per submission. Please split it into smaller files."
        ))
        return records, issues

    def get(row, field):
        idx = col_map.get(field)
        return row.iloc[idx] if idx is not None else None

    def validate_location(row, row_number, region_field, district_field, ward_field, village_field,
                           lat_field, lon_field, label_prefix, required):
        """Shared cascading Region->District->Ward->Village + GPS check, used
        identically for the loan's own location and the collateral's location."""
        region = _clean_str(get(row, region_field))
        district = _clean_str(get(row, district_field))
        ward = _clean_str(get(row, ward_field)) if ward_field in col_map else ""
        village = _clean_str(get(row, village_field)) if village_field in col_map else ""
        ok = True

        if not region:
            if required:
                issues.append(ValidationIssue(row_number, region_field, f"{label_prefix} region is missing (mandatory field)"))
                ok = False
        elif not geo.is_valid_region(region):
            issues.append(ValidationIssue(row_number, region_field, f"'{region}' is not a valid Tanzanian region ({label_prefix})"))
            ok = False

        if region and geo.is_valid_region(region):
            if not district:
                if required:
                    issues.append(ValidationIssue(row_number, district_field, f"{label_prefix} district is missing (mandatory field)"))
                    ok = False
            elif not geo.is_valid_district(region, district):
                issues.append(ValidationIssue(
                    row_number, district_field,
                    f"'{district}' is not a valid district within the region '{region}' ({label_prefix})"
                ))
                ok = False

            if district and ward and geo.is_valid_district(region, district):
                if not geo.is_valid_ward(region, district, ward):
                    issues.append(ValidationIssue(
                        row_number, ward_field,
                        f"'{ward}' is not a valid ward within the district '{district}' ({label_prefix})",
                        severity="WARNING",
                    ))
            if ward and village and geo.is_valid_ward(region, district, ward):
                if not geo.is_valid_village(region, district, ward, village):
                    issues.append(ValidationIssue(
                        row_number, village_field,
                        f"'{village}' is not a recognized village/street within '{ward}' ({label_prefix})",
                        severity="WARNING",
                    ))

        lat = _clean_float(get(row, lat_field)) if lat_field in col_map else None
        lon = _clean_float(get(row, lon_field)) if lon_field in col_map else None
        if lat == "INVALID":
            issues.append(ValidationIssue(row_number, lat_field, f"{label_prefix} latitude is not a valid number"))
            lat = None
        if lon == "INVALID":
            issues.append(ValidationIssue(row_number, lon_field, f"{label_prefix} longitude is not a valid number"))
            lon = None
        if lat is not None and lon is not None and region and geo.is_valid_region(region):
            centroid = get_region_coordinates(region)
            if centroid:
                dist = _haversine_km(lat, lon, centroid[0], centroid[1])
                if dist > GPS_MISMATCH_WARNING_KM:
                    issues.append(ValidationIssue(
                        row_number, lat_field,
                        f"{label_prefix} coordinates ({lat}, {lon}) are {dist:.0f} km from the centre of "
                        f"'{region}' - please double check they belong to this region",
                        severity="WARNING",
                    ))

        return region, district, ward, village, lat, lon, ok

    def validate_dropdown(row, field, options, row_number, required, severity="ERROR"):
        val = _clean_str(get(row, field))
        if not val:
            if required:
                issues.append(ValidationIssue(row_number, field, f"{dict(COLUMNS)[field]} is missing (mandatory field)"))
                return val, False
            return val, True
        if val not in options:
            issues.append(ValidationIssue(
                row_number, field,
                f"'{val}' is not a recognized option for {dict(COLUMNS)[field]} - choose from the template dropdown",
                severity=severity,
            ))
            return val, severity == "WARNING"
        return val, True

    seen_loan_ids = set()

    # ---- 3. Row-level validation ----
    for idx, row in data_rows.iterrows():
        row_number = header_row_idx + 2 + idx  # +1 header->1-indexed row, +1 for pandas 0-index -> next row
        row_is_valid = True
        record = {}

        customer_id = _clean_str(get(row, "customer_id"))
        if not customer_id:
            issues.append(ValidationIssue(row_number, "customer_id", "Customer Identification Number is missing (mandatory field)"))
            row_is_valid = False
        record["customer_id"] = customer_id or None

        # Stop processing a row that is entirely blank (trailing empty rows in the sheet)
        if not customer_id and all(_clean_str(get(row, f)) == "" for f in FIELD_NAMES if f != "customer_id"):
            continue

        loan_id = _clean_str(get(row, "loan_id"))
        if not loan_id:
            issues.append(ValidationIssue(row_number, "loan_id", "Loan number is missing (mandatory field)"))
            row_is_valid = False
        elif loan_id in seen_loan_ids:
            issues.append(ValidationIssue(row_number, "loan_id", f"Loan number '{loan_id}' is duplicated within this file"))
            row_is_valid = False
        else:
            seen_loan_ids.add(loan_id)
        record["loan_id"] = loan_id or None

        record["branch_code"] = _clean_str(get(row, "branch_code")) or None
        record["branch_name"] = _clean_str(get(row, "branch_name")) or None

        val, ok = validate_dropdown(row, "client_type", CLIENT_TYPES, row_number, required=False, severity="WARNING")
        record["client_type"] = val or None
        val, ok = validate_dropdown(row, "business_size", BUSINESS_SIZES, row_number, required=False, severity="WARNING")
        record["business_size"] = val or None

        turnover = _clean_float(get(row, "annual_turnover_tzs"))
        if turnover == "INVALID":
            issues.append(ValidationIssue(row_number, "annual_turnover_tzs", "Annual turnover is not a valid number", severity="WARNING"))
            turnover = None
        record["annual_turnover_tzs"] = turnover

        record["disbursement_date"] = _clean_str(get(row, "disbursement_date")) or None
        record["maturity_date"] = _clean_str(get(row, "maturity_date")) or None

        val, ok = validate_dropdown(row, "currency", CURRENCIES, row_number, required=False, severity="WARNING")
        record["currency"] = val or None

        for amount_field, required_field in [("loan_amount_tzs", True), ("collateral_value_tzs", True),
                                              ("outstanding_principal_tzs", False), ("collateral_forced_sale_value_tzs", False),
                                              ("insurance_value_protected_tzs", False)]:
            v = _clean_float(get(row, amount_field))
            if v is None:
                if required_field:
                    issues.append(ValidationIssue(row_number, amount_field, f"{dict(COLUMNS)[amount_field]} is missing (mandatory field)"))
                    row_is_valid = False
            elif v == "INVALID":
                issues.append(ValidationIssue(row_number, amount_field, f"{dict(COLUMNS)[amount_field]} is not a valid number"))
                row_is_valid = False
                v = None
            elif required_field and v <= 0:
                issues.append(ValidationIssue(row_number, amount_field, f"{dict(COLUMNS)[amount_field]} must be greater than 0"))
                row_is_valid = False
            record[amount_field] = v

        interest = _clean_float(get(row, "annual_interest_rate"))
        record["annual_interest_rate"] = None if interest == "INVALID" else interest

        val, ok = validate_dropdown(row, "loan_type", LOAN_TYPES, row_number, required=False, severity="WARNING")
        record["loan_type"] = val or None
        val, ok = validate_dropdown(row, "loan_economic_activity", LOAN_ECONOMIC_ACTIVITIES, row_number, required=False, severity="WARNING")
        record["loan_economic_activity"] = val or None
        record["loan_purpose"] = _clean_str(get(row, "loan_purpose")) or None
        val, ok = validate_dropdown(row, "asset_classification", ASSET_CLASSIFICATIONS, row_number, required=False, severity="WARNING")
        record["asset_classification"] = val or None

        region, district, ward, village, lat, lon, loc_ok = validate_location(
            row, row_number, "region", "district", "ward", "village",
            "loan_latitude", "loan_longitude", "Loan location", required=True,
        )
        record.update(region=region or None, district=district or None, ward=ward or None, village=village or None,
                       loan_latitude=lat, loan_longitude=lon)
        row_is_valid = row_is_valid and loc_ok

        val, ok = validate_dropdown(row, "collateral_type", COLLATERAL_TYPES, row_number, required=True)
        record["collateral_type"] = val or None
        row_is_valid = row_is_valid and ok
        record["collateral_pledged_date"] = _clean_str(get(row, "collateral_pledged_date")) or None
        record["collateral_economic_activity"] = _clean_str(get(row, "collateral_economic_activity")) or None

        c_region, c_district, c_ward, c_village, c_lat, c_lon, coll_loc_ok = validate_location(
            row, row_number, "collateral_region", "collateral_district", "collateral_ward", "collateral_village",
            "collateral_latitude", "collateral_longitude", "Collateral location", required=False,
        )
        record.update(collateral_region=c_region or None, collateral_district=c_district or None,
                       collateral_ward=c_ward or None, collateral_village=c_village or None,
                       collateral_latitude=c_lat, collateral_longitude=c_lon)
        # Collateral location is optional (a row may have none at all), but if
        # ANY of it was provided, it must be internally consistent - a wrong
        # region/district pairing is not silently accepted just because the
        # whole block wasn't mandatory.
        row_is_valid = row_is_valid and coll_loc_ok

        val, ok = validate_dropdown(row, "insurance_coverage", YES_NO, row_number, required=False, severity="WARNING")
        record["insurance_coverage"] = val or None
        record["insurance_policy_type"] = _clean_str(get(row, "insurance_policy_type")) or None
        record["insurance_provider_name"] = _clean_str(get(row, "insurance_provider_name")) or None

        hazard = _clean_str(get(row, "climate_hazard_exposure")) if "climate_hazard_exposure" in col_map else "None"
        if hazard and hazard not in HAZARD_OPTIONS:
            issues.append(ValidationIssue(row_number, "climate_hazard_exposure", f"'{hazard}' is not a valid option", severity="WARNING"))
            hazard = "None"
        record["climate_hazard_exposure"] = hazard or "None"

        record["row_number"] = row_number
        record["is_valid"] = row_is_valid
        records.append(record)

    return records, issues
