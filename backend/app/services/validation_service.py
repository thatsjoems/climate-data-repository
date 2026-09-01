"""
MODULE F: Automated Data Validation.
Inasoma faili ya Excel iliyopakiwa (uploaded) na kuithibitisha dhidi ya template sanifu.
Inarudisha: (list ya records zilizosomwa, list ya errors zilizopatikana).
"""
import io
import re
import pandas as pd
from app.services.template_generator import REQUIRED_COLUMNS, TANZANIA_REGIONS, HAZARD_OPTIONS


class ValidationIssue:
    def __init__(self, row_number, column_name, description, severity="ERROR"):
        self.row_number = row_number
        self.column_name = column_name
        self.description = description
        self.severity = severity


def validate_excel_file(file_bytes: bytes, filename: str):
    issues: list[ValidationIssue] = []
    records: list[dict] = []

    # ---- 1. File-level validation ----
    if not (filename.lower().endswith(".xlsx") or filename.lower().endswith(".xls")):
        issues.append(ValidationIssue(None, None, "Aina ya faili si sahihi - lazima iwe .xlsx au .xls"))
        return records, issues

    try:
        df = pd.read_excel(io.BytesIO(file_bytes), sheet_name="Loan_Collateral_Data")
    except Exception:
        try:
            df = pd.read_excel(io.BytesIO(file_bytes))  # jaribu sheet ya kwanza kama jina halifanani
        except Exception as exc:
            issues.append(ValidationIssue(None, None, f"Imeshindikana kusoma faili ya Excel: {exc}"))
            return records, issues

    # ---- 2. Template structure validation ----
    missing_cols = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing_cols:
        issues.append(ValidationIssue(
            None, None,
            f"Column zifuatazo za lazima hazipo kwenye faili: {', '.join(missing_cols)}. "
            f"Tafadhali tumia template sanifu."
        ))
        return records, issues

    seen_loan_ids = set()

    # ---- 3. Row-level data validation ----
    for idx, row in df.iterrows():
        row_number = idx + 2  # +2 kwa sababu row 1 ni header, na pandas huanza na 0
        row_is_valid = True
        record = {}

        loan_id = str(row.get("loan_id", "")).strip()
        if not loan_id or loan_id.lower() == "nan":
            issues.append(ValidationIssue(row_number, "loan_id", "loan_id haipo (mandatory field)"))
            row_is_valid = False
        elif loan_id in seen_loan_ids:
            issues.append(ValidationIssue(row_number, "loan_id", f"loan_id '{loan_id}' imerudiwa (duplicate)"))
            row_is_valid = False
        else:
            seen_loan_ids.add(loan_id)
        record["loan_id"] = loan_id

        borrower_name = str(row.get("borrower_name", "")).strip()
        if not borrower_name or borrower_name.lower() == "nan":
            issues.append(ValidationIssue(row_number, "borrower_name", "borrower_name haipo (mandatory field)"))
            row_is_valid = False
        record["borrower_name"] = borrower_name

        for amount_col in ["loan_amount_tzs", "collateral_value_tzs"]:
            raw_val = row.get(amount_col)
            try:
                val = float(raw_val)
                if val <= 0:
                    issues.append(ValidationIssue(row_number, amount_col, f"{amount_col} lazima iwe zaidi ya 0"))
                    row_is_valid = False
                record[amount_col] = val
            except (TypeError, ValueError):
                issues.append(ValidationIssue(row_number, amount_col, f"{amount_col} si namba sahihi"))
                row_is_valid = False
                record[amount_col] = None

        region = str(row.get("region", "")).strip()
        if region not in TANZANIA_REGIONS:
            issues.append(ValidationIssue(row_number, "region", f"'{region}' si mkoa sahihi wa Tanzania"))
            row_is_valid = False
        record["region"] = region

        record["district"] = str(row.get("district", "")).strip()
        record["collateral_type"] = str(row.get("collateral_type", "")).strip()

        reporting_period = str(row.get("reporting_period", "")).strip()
        if not re.match(r"^\d{4}-Q[1-4]$", reporting_period):
            issues.append(ValidationIssue(
                row_number, "reporting_period",
                f"'{reporting_period}' si muundo sahihi - tumia YYYY-Qn (mfano 2026-Q3)"
            ))
            row_is_valid = False
        record["reporting_period"] = reporting_period

        hazard = row.get("climate_hazard_exposure")
        hazard = str(hazard).strip() if pd.notna(hazard) else "None"
        if hazard not in HAZARD_OPTIONS:
            issues.append(ValidationIssue(
                row_number, "climate_hazard_exposure",
                f"'{hazard}' si chaguo sahihi", severity="WARNING"
            ))
            hazard = "None"
        record["climate_hazard_exposure"] = hazard

        record["row_number"] = row_number
        record["is_valid"] = row_is_valid
        records.append(record)

    return records, issues
