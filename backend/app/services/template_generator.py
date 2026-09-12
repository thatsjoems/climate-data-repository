"""
Generates the standardized Excel data-submission template - MODULE D.

Rebuilt to mirror Bank of Tanzania's own official "Climate Data Template"
exactly (38 columns, same headers, same dropdown option lists) - provided
directly by the user, not a simplified prototype approximation. The
Region -> District -> Ward -> Village cascading dropdowns use the official
2022 Census village/mtaa list (mainland) + the Zanzibar Frame (also
user-provided) via app.services.geo_lookup - the single source of truth for
Tanzania's administrative geography used throughout this system.
"""
import io
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.worksheet.datavalidation import DataValidation
from openpyxl.workbook.defined_name import DefinedName
from openpyxl.utils import get_column_letter

from app.services import geo_lookup as geo

TEMPLATE_VERSION = "v2.0-official"

# ---------------------------------------------------------------------------
# Official dropdown option lists - transcribed exactly from BOT's own
# "DROP DOWN" reference sheet in the template they provided.
# ---------------------------------------------------------------------------
CLIENT_TYPES = ["Corporations", "Individuals", "Non-salaried", "Staff"]
BUSINESS_SIZES = ["Large", "Medium", "Micro", "Small"]
LOAN_TYPES = ["Business", "Mortgage", "Personal"]
CURRENCIES = ["TZS", "USD", "Other"]
LOAN_ECONOMIC_ACTIVITIES = [
    "Agriculture", "Real estate/Mortgage", "Communication and transportation",
    "Tourism", "Trade", "Government", "Gas", "Other",
]
ASSET_CLASSIFICATIONS = ["Current", "Doubtful", "Sub-standard"]
COLLATERAL_TYPES = [
    "Gold", "Cash", "Deposits", "Government Securities",
    "Central Government Guarantee", "Guarantee from Revolutionary Government of Zanzibar",
    "Terminal Benefits",
    "Guarantee of Unconditional and irrevocable guarantee of a first class international bank or a first class international financial institution.",
    "Residential mortgage", "Commercial real estate", "agricultural land",
    "Guarantee from Local government units", "Parastatals Guarantee",
    "Other mortgages eg chattels", "Compulsory savings", "Stocks", "Equipment",
    "MotorVehicle", "Letter of Hypothecation", "Debenture", "Unsecured",
]
YES_NO = ["YES", "NO"]

# Backward-compatible exports (other modules import these names)
TANZANIA_REGIONS: list[str] = geo.all_regions()
REGION_DISTRICTS: dict[str, list[str]] = {r: geo.districts_for_region(r) for r in TANZANIA_REGIONS}
HAZARD_OPTIONS = ["None", "Drought", "Flood", "Cyclone", "Landslide"]

# The 38 official columns, in the official template's own order. Internal
# field names (used by validation_service.py / SubmissionRecord) are the
# dict keys; the display header is what a human filling the sheet sees.
COLUMNS: list[tuple[str, str]] = [
    ("customer_id", "Customer Identification Number"),
    ("branch_code", "Branch Code"),
    ("branch_name", "Branch name"),
    ("client_type", "Client Type"),
    ("business_size", "Size of the business"),
    ("annual_turnover_tzs", "Annual turn-over of the borrower"),
    ("loan_id", "Loan number"),
    ("disbursement_date", "Disbursement Date (Date/Month/Year)"),
    ("maturity_date", "Maturity Date (Date/Month/Year)"),
    ("currency", "Currency"),
    ("loan_amount_tzs", "TZS Disbursed Amount"),
    ("outstanding_principal_tzs", "TZS Outstanding Principal Amount"),
    ("annual_interest_rate", "Annual Interest Rate"),
    ("loan_type", "loan Type/ General Category"),
    ("loan_economic_activity", "Loan Economic Activity"),
    ("loan_purpose", "Purpose of the loan"),
    ("asset_classification", "Asset Classification Category"),
    ("region", "Location of invested loan (Region)"),
    ("district", "Location of invested loan (District)"),
    ("ward", "Location of invested loan (Ward)"),
    ("village", "Location of invested loan (Street/village)"),
    ("loan_latitude", "Invested Loan Geographical coordinates (Latitude)"),
    ("loan_longitude", "Invested Loan Geographical coordinates (Longitude)"),
    ("collateral_type", "Collateral Pledged"),
    ("collateral_pledged_date", "Collateral Pledged Date"),
    ("collateral_value_tzs", "TZS Market value of the collateral"),
    ("collateral_forced_sale_value_tzs", "TZS Forced Sale Value of the collateral"),
    ("collateral_economic_activity", "Collateral Economic activity"),
    ("collateral_region", "Location of the collateral (Region)"),
    ("collateral_district", "Location of the collateral (District)"),
    ("collateral_ward", "Location of the collateral (Ward)"),
    ("collateral_village", "Location of the collateral (Street)"),
    ("collateral_latitude", "Collateral Geographical Coordinates (Latitude)"),
    ("collateral_longitude", "Collateral Geographical Coordinates (Longitude)"),
    ("insurance_coverage", "Insurance coverage of the collateral against climate risks"),
    ("insurance_policy_type", "Type of insurance policy"),
    ("insurance_provider_name", "Name of insurance provider"),
    ("insurance_value_protected_tzs", "Value of Collateral Protected"),
]
FIELD_NAMES = [f for f, _ in COLUMNS]
REQUIRED_COLUMNS = ["customer_id", "loan_id", "loan_amount_tzs", "collateral_type", "collateral_value_tzs", "region", "district"]
OPTIONAL_COLUMNS = [f for f in FIELD_NAMES if f not in REQUIRED_COLUMNS]
ALL_COLUMNS = FIELD_NAMES

# Excel special characters that appear in real region/district/ward names and
# must be sanitized identically on both sides: when the Python side builds a
# named range's NAME, and when an Excel formula reconstructs that same name
# via INDIRECT() from a cell's value.
_SPECIAL_CHARS = [" ", ".", "-", "/", "'", '"', "(", ")"]


def _excel_sanitize_formula(cell_ref: str) -> str:
    """Builds the nested-SUBSTITUTE Excel formula fragment matching geo.safe_excel_name()."""
    expr = cell_ref
    for ch in _SPECIAL_CHARS:
        if ch == '"':
            expr = f'SUBSTITUTE({expr},CHAR(34),"_")'
        else:
            expr = f'SUBSTITUTE({expr},"{ch}","_")'
    return expr


def generate_loan_collateral_template() -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Loan_Collateral_Data"

    header_font = Font(bold=True, size=11)
    title_font = Font(bold=True, size=13)
    col_header_fill = PatternFill(start_color="1F4E78", end_color="1F4E78", fill_type="solid")
    col_header_font = Font(bold=True, color="FFFFFF", size=9)
    example_fill = PatternFill(start_color="FFF3D6", end_color="FFF3D6", fill_type="solid")

    # ---- Header block, matching BOT's own template layout exactly ----
    ws["A2"] = "NAME OF THE INSTITUTION:"
    ws["A2"].font = header_font
    ws["A4"] = "BANK CODE:"
    ws["A4"].font = header_font
    ws["A6"] = "LOAN AND COLLATERAL DATA AS AT "
    ws["A6"].font = title_font

    HEADER_ROW = 9
    EXAMPLE_ROW = 10
    DATA_START_ROW = 11
    DATA_END_ROW = 1010  # ~1000 data-entry rows with dropdowns pre-applied

    for idx, (field, label) in enumerate(COLUMNS, start=1):
        cell = ws.cell(row=HEADER_ROW, column=idx, value=label)
        cell.fill = col_header_fill
        cell.font = col_header_font
        cell.alignment = Alignment(wrap_text=True, vertical="center", horizontal="center")
        ws.column_dimensions[get_column_letter(idx)].width = 22

    ws.freeze_panes = ws.cell(row=DATA_START_ROW, column=1)

    # ---- One example row, clearly marked, showing the expected format ----
    example_values = {
        "customer_id": "9178345", "branch_code": "1", "branch_name": "Head Office",
        "client_type": "Corporations", "business_size": "Medium",
        "annual_turnover_tzs": 500000000, "loan_id": "LN-2026-0001",
        "disbursement_date": "2026-03-15", "maturity_date": "2029-03-15",
        "currency": "TZS", "loan_amount_tzs": 80000000, "outstanding_principal_tzs": 65000000,
        "annual_interest_rate": 16.5, "loan_type": "Business",
        "loan_economic_activity": "Agriculture", "loan_purpose": "Working capital",
        "asset_classification": "Current",
        "region": "Dodoma", "district": "Kondoa", "ward": "Bereko", "village": "Bereko",
        "loan_latitude": -4.9, "loan_longitude": 35.78,
        "collateral_type": "Residential mortgage", "collateral_pledged_date": "2026-03-15",
        "collateral_value_tzs": 120000000, "collateral_forced_sale_value_tzs": 95000000,
        "collateral_economic_activity": "Real estate/Mortgage",
        "collateral_region": "Dodoma", "collateral_district": "Kondoa",
        "collateral_ward": "Bereko", "collateral_village": "Bereko",
        "collateral_latitude": -4.9, "collateral_longitude": 35.78,
        "insurance_coverage": "YES", "insurance_policy_type": "Property climate cover",
        "insurance_provider_name": "Example Insurance Co.", "insurance_value_protected_tzs": 100000000,
    }
    for idx, (field, _) in enumerate(COLUMNS, start=1):
        cell = ws.cell(row=EXAMPLE_ROW, column=idx, value=example_values.get(field))
        cell.fill = example_fill

    field_to_col = {f: i + 1 for i, (f, _) in enumerate(COLUMNS)}

    def col_letter(field: str) -> str:
        return get_column_letter(field_to_col[field])

    # =========================================================================
    # LISTS sheet - all dropdown source data lives here (hidden from the user)
    # =========================================================================
    lists_ws = wb.create_sheet("Lists")
    lists_ws.sheet_state = "hidden"
    cursor = 1

    def write_flat_list(name: str, values: list[str]) -> str:
        nonlocal cursor
        start = cursor
        for v in values:
            lists_ws.cell(row=cursor, column=1, value=v)
            cursor += 1
        end = cursor - 1
        cursor += 1  # blank separator row
        ref = f"Lists!$A${start}:$A${end}"
        wb.defined_names[name] = DefinedName(name, attr_text=ref)
        return name

    write_flat_list("LIST_CLIENT_TYPE", CLIENT_TYPES)
    write_flat_list("LIST_BUSINESS_SIZE", BUSINESS_SIZES)
    write_flat_list("LIST_LOAN_TYPE", LOAN_TYPES)
    write_flat_list("LIST_CURRENCY", CURRENCIES)
    write_flat_list("LIST_LOAN_ECON_ACTIVITY", LOAN_ECONOMIC_ACTIVITIES)
    write_flat_list("LIST_ASSET_CLASS", ASSET_CLASSIFICATIONS)
    write_flat_list("LIST_COLLATERAL_TYPE", COLLATERAL_TYPES)
    write_flat_list("LIST_YES_NO", YES_NO)
    write_flat_list("ALL_REGIONS", TANZANIA_REGIONS)

    # Region -> District cascading source ranges (one named range per region)
    geo_data = geo._load()
    for region in TANZANIA_REGIONS:
        districts = geo.districts_for_region(region)
        write_flat_list(f"REG_{geo.safe_excel_name(region)}", districts)

    # District -> Ward cascading source ranges (one named range per district -
    # district names are globally unique across all 31 regions, verified)
    for region, districts in geo_data.items():
        for district, wards in districts.items():
            write_flat_list(f"DIST_{geo.safe_excel_name(district)}", sorted(wards.keys()))

    # District+Ward -> Village cascading source ranges
    for region, districts in geo_data.items():
        for district, wards in districts.items():
            for ward, villages in wards.items():
                if villages:
                    key = f"WD_{geo.safe_excel_name(district)}_{geo.safe_excel_name(ward)}"
                    write_flat_list(key, sorted(villages))

    # =========================================================================
    # Data validations on the main sheet
    # =========================================================================
    def add_flat_dv(field: str, list_name: str):
        dv = DataValidation(type="list", formula1=f"={list_name}", allow_blank=True, showErrorMessage=True)
        dv.error = f"Please select a value from the official list."
        col = col_letter(field)
        dv.add(f"{col}{DATA_START_ROW}:{col}{DATA_END_ROW}")
        ws.add_data_validation(dv)

    add_flat_dv("client_type", "LIST_CLIENT_TYPE")
    add_flat_dv("business_size", "LIST_BUSINESS_SIZE")
    add_flat_dv("loan_type", "LIST_LOAN_TYPE")
    add_flat_dv("currency", "LIST_CURRENCY")
    add_flat_dv("loan_economic_activity", "LIST_LOAN_ECON_ACTIVITY")
    add_flat_dv("asset_classification", "LIST_ASSET_CLASS")
    add_flat_dv("collateral_type", "LIST_COLLATERAL_TYPE")
    add_flat_dv("insurance_coverage", "LIST_YES_NO")
    add_flat_dv("region", "ALL_REGIONS")
    add_flat_dv("collateral_region", "ALL_REGIONS")

    def add_cascading_dv(field: str, parent_field: str, prefix: str, extra_parent_field: str | None = None, extra_prefix: str = ""):
        """
        District depends on Region; Ward depends on District; Village depends
        on District+Ward. The formula is defined ONCE using a relative
        reference to the parent cell in the SAME row - Excel auto-adjusts
        this per row across the whole applied range, exactly like a filled-
        down formula.
        """
        parent_ref = f"{col_letter(parent_field)}{DATA_START_ROW}"
        parent_expr = _excel_sanitize_formula(parent_ref)
        if extra_parent_field:
            extra_ref = f"{col_letter(extra_parent_field)}{DATA_START_ROW}"
            extra_expr = _excel_sanitize_formula(extra_ref)
            formula = f'=INDIRECT("{prefix}"&{parent_expr}&"{extra_prefix}"&{extra_expr})'
        else:
            formula = f'=INDIRECT("{prefix}"&{parent_expr})'
        dv = DataValidation(type="list", formula1=formula, allow_blank=True, showErrorMessage=True)
        dv.error = "Please select the region/district/ward above first, then choose from its list here."
        col = col_letter(field)
        dv.add(f"{col}{DATA_START_ROW}:{col}{DATA_END_ROW}")
        ws.add_data_validation(dv)

    # Loan location cascade
    add_cascading_dv("district", "region", "REG_")
    add_cascading_dv("ward", "district", "DIST_")
    add_cascading_dv("village", "district", "WD_", extra_parent_field="ward", extra_prefix="_")

    # Collateral location cascade (independent - collateral can be in a different place than the loan)
    add_cascading_dv("collateral_district", "collateral_region", "REG_")
    add_cascading_dv("collateral_ward", "collateral_district", "DIST_")
    add_cascading_dv("collateral_village", "collateral_district", "WD_", extra_parent_field="collateral_ward", extra_prefix="_")

    # ---- Legend / instructions sheet ----
    legend = wb.create_sheet("Instructions", 0)
    legend["A1"] = f"CDR Loan & Collateral Data Template ({TEMPLATE_VERSION})"
    legend["A1"].font = Font(bold=True, size=14)
    legend["A3"] = "This template mirrors Bank of Tanzania's own official Climate Data Template."
    legend["A4"] = "Fill in the 'Loan_Collateral_Data' sheet. Row 10 (highlighted) is an EXAMPLE - replace or delete it."
    legend["A5"] = "Dropdowns: Region -> District -> Ward -> Street/Village are linked - select Region first, then District, then Ward."
    legend["A6"] = "This applies separately to the loan's own location AND the collateral's location - they are independent."
    legend["A7"] = "Latitude/Longitude should be within the selected region - large mismatches will be flagged on upload."
    legend["A8"] = "Required fields: " + ", ".join(REQUIRED_COLUMNS)
    for row in range(3, 9):
        legend[f"A{row}"].font = Font(size=10, italic=(row != 8))
    legend.column_dimensions["A"].width = 110

    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    return buffer.read()
