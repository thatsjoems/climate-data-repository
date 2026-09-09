"""
MODULE F: Automated Data Validation.
Reads an uploaded Excel file and validates it against the standardized template.
Returns: (list of parsed records, list of validation issues found).
"""
import io
import re
import pandas as pd
from app.services.template_generator import REQUIRED_COLUMNS, TANZANIA_REGIONS, HAZARD_OPTIONS, REGION_DISTRICTS, COLLATERAL_TYPES

REPORTING_PERIOD_PATTERN = re.compile(r"^\d{4}-Q[1-4]$")


class ValidationIssue:
    def __init__(self, row_number, column_name, description, severity="ERROR"):
        self.row_number = row_number
        self.column_name = column_name
        self.description = description
        self.severity = severity


def validate_excel_file(
    file_bytes: bytes,
    filename: str,
    form_reporting_period: str | None = None,
    max_rows: int = 100000,
):
    """
    form_reporting_period: the Reporting Period the user typed into the upload form.
    When provided, every row's own reporting_period column must match it exactly -
    a mismatch rejects the whole submission rather than silently keeping ambiguous
    data (Data Quality & Validation: reporting-period consistency).
    """
    issues: list[ValidationIssue] = []
    records: list[dict] = []

    # ---- 1. File-level validation ----
    if not (filename.lower().endswith(".xlsx") or filename.lower().endswith(".xls")):
        issues.append(ValidationIssue(None, None, "Invalid file type - must be .xlsx or .xls"))
        return records, issues

    try:
        df = pd.read_excel(io.BytesIO(file_bytes), sheet_name="Loan_Collateral_Data")
    except Exception:
        try:
            df = pd.read_excel(io.BytesIO(file_bytes))  # fall back to the first sheet if the name doesn't match
        except Exception as exc:
            issues.append(ValidationIssue(None, None, f"Could not read the Excel file: {exc}"))
            return records, issues

    # ---- 2. Template structure validation ----
    missing_cols = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing_cols:
        issues.append(ValidationIssue(
            None, None,
            f"The following required columns are missing from the file: {', '.join(missing_cols)}. "
            f"Please use the standardized template."
        ))
        return records, issues

    # ---- 3. Row-count limit (prevents an oversized file exhausting server resources) ----
    if len(df) > max_rows:
        issues.append(ValidationIssue(
            None, None,
            f"This file has {len(df)} data rows, which exceeds the maximum of {max_rows} allowed "
            f"per submission. Please split it into smaller files."
        ))
        return records, issues

    # ---- 4. Reporting-period consistency (form value vs each row's own column) ----
    if form_reporting_period:
        mismatched_rows = []
        for idx, row in df.iterrows():
            row_period = str(row.get("reporting_period", "")).strip()
            if row_period != form_reporting_period.strip():
                mismatched_rows.append((idx + 2, row_period or "(blank)"))
        if mismatched_rows:
            sample = ", ".join(f"row {r} has '{p}'" for r, p in mismatched_rows[:5])
            more = f" and {len(mismatched_rows) - 5} more row(s)" if len(mismatched_rows) > 5 else ""
            issues.append(ValidationIssue(
                None, "reporting_period",
                f"The reporting period you entered on the upload form ('{form_reporting_period}') does not "
                f"match the reporting_period column inside the file for {len(mismatched_rows)} row(s): "
                f"{sample}{more}. Please correct the file or the form value and resubmit - the whole "
                f"submission is rejected to avoid saving misleading data."
            ))
            return records, issues

    seen_loan_ids = set()

    # ---- 5. Row-level data validation ----
    for idx, row in df.iterrows():
        row_number = idx + 2  # +2 because row 1 is the header, and pandas is 0-indexed
        row_is_valid = True
        record = {}

        loan_id = str(row.get("loan_id", "")).strip()
        if not loan_id or loan_id.lower() == "nan":
            issues.append(ValidationIssue(row_number, "loan_id", "loan_id is missing (mandatory field)"))
            row_is_valid = False
        elif loan_id in seen_loan_ids:
            issues.append(ValidationIssue(row_number, "loan_id", f"loan_id '{loan_id}' is duplicated"))
            row_is_valid = False
        else:
            seen_loan_ids.add(loan_id)
        record["loan_id"] = loan_id

        borrower_name = str(row.get("borrower_name", "")).strip()
        if not borrower_name or borrower_name.lower() == "nan":
            issues.append(ValidationIssue(row_number, "borrower_name", "borrower_name is missing (mandatory field)"))
            row_is_valid = False
        record["borrower_name"] = borrower_name

        for amount_col in ["loan_amount_tzs", "collateral_value_tzs"]:
            raw_val = row.get(amount_col)
            try:
                val = float(raw_val)
                if val <= 0:
                    issues.append(ValidationIssue(row_number, amount_col, f"{amount_col} must be greater than 0"))
                    row_is_valid = False
                record[amount_col] = val
            except (TypeError, ValueError):
                issues.append(ValidationIssue(row_number, amount_col, f"{amount_col} is not a valid number"))
                row_is_valid = False
                record[amount_col] = None

        region = str(row.get("region", "")).strip()
        if region not in TANZANIA_REGIONS:
            issues.append(ValidationIssue(row_number, "region", f"'{region}' is not a valid Tanzanian region"))
            row_is_valid = False
        record["region"] = region

        district = str(row.get("district", "")).strip()
        if not district or district.lower() == "nan":
            issues.append(ValidationIssue(row_number, "district", "district is missing (mandatory field)"))
            row_is_valid = False
        elif region in REGION_DISTRICTS and district not in REGION_DISTRICTS[region]:
            issues.append(ValidationIssue(
                row_number, "district",
                f"'{district}' is not a valid district within the region '{region}'"
            ))
            row_is_valid = False
        record["district"] = district
        collateral_type = str(row.get("collateral_type", "")).strip()
        # Matches the real collateral categories used in BOT's own Climate Data Repository
        # (Report on Climate Risk Analysis in the Banking Sector, March 2026) - controlled
        # so "Land Title", "Real Estate", "House" etc. don't fragment into separate categories.
        if collateral_type not in COLLATERAL_TYPES:
            issues.append(ValidationIssue(
                row_number, "collateral_type",
                f"'{collateral_type}' is not a recognized collateral type - choose from the "
                f"template dropdown ({', '.join(COLLATERAL_TYPES)})"
            ))
            row_is_valid = False
        record["collateral_type"] = collateral_type

        reporting_period = str(row.get("reporting_period", "")).strip()
        if not REPORTING_PERIOD_PATTERN.match(reporting_period):
            issues.append(ValidationIssue(
                row_number, "reporting_period",
                f"'{reporting_period}' is not a valid format - use YYYY-Qn (e.g. 2026-Q3)"
            ))
            row_is_valid = False
        record["reporting_period"] = reporting_period

        hazard = row.get("climate_hazard_exposure")
        hazard = str(hazard).strip() if pd.notna(hazard) else "None"
        if hazard not in HAZARD_OPTIONS:
            issues.append(ValidationIssue(
                row_number, "climate_hazard_exposure",
                f"'{hazard}' is not a valid option", severity="WARNING"
            ))
            hazard = "None"
        record["climate_hazard_exposure"] = hazard

        record["row_number"] = row_number
        record["is_valid"] = row_is_valid
        records.append(record)

    return records, issues
