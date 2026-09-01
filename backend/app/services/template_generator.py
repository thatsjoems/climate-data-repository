"""
Kutengeneza template ya Excel (kiwango sanifu cha uwasilishaji data) - MODULE D.
Taasisi zinapakua template hii, wanajaza, kisha wanapakia (upload) tena mfumo.
"""
import io
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.worksheet.datavalidation import DataValidation

TEMPLATE_VERSION = "v1.0"

REQUIRED_COLUMNS = [
    "loan_id", "borrower_name", "loan_amount_tzs", "collateral_type",
    "collateral_value_tzs", "region", "district", "reporting_period",
]
OPTIONAL_COLUMNS = ["climate_hazard_exposure"]

ALL_COLUMNS = REQUIRED_COLUMNS + OPTIONAL_COLUMNS

TANZANIA_REGIONS = [
    "Arusha", "Dar es Salaam", "Dodoma", "Geita", "Iringa", "Kagera", "Katavi",
    "Kigoma", "Kilimanjaro", "Lindi", "Manyara", "Mara", "Mbeya", "Morogoro",
    "Mtwara", "Mwanza", "Njombe", "Pwani", "Rukwa", "Ruvuma", "Shinyanga",
    "Simiyu", "Singida", "Songwe", "Tabora", "Tanga",
]

HAZARD_OPTIONS = ["None", "Drought", "Flood", "Cyclone", "Landslide"]


def generate_loan_collateral_template() -> bytes:
    """Inatengeneza faili ya Excel (.xlsx) yenye muundo sanifu wa data za mikopo/collateral."""
    wb = Workbook()
    ws = wb.active
    ws.title = "Loan_Collateral_Data"

    header_fill = PatternFill(start_color="1F4E78", end_color="1F4E78", fill_type="solid")
    header_font = Font(color="FFFFFF", bold=True)

    for col_idx, col_name in enumerate(ALL_COLUMNS, start=1):
        cell = ws.cell(row=1, column=col_idx, value=col_name)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center")
        ws.column_dimensions[cell.column_letter].width = 22

    # Mfano wa safu (mfano row) kuonyesha jinsi ya kujaza
    example = {
        "loan_id": "LN-2026-0001",
        "borrower_name": "Mfano Kampuni Ltd",
        "loan_amount_tzs": 50000000,
        "collateral_type": "Land Title",
        "collateral_value_tzs": 80000000,
        "region": "Dodoma",
        "district": "Chamwino",
        "reporting_period": "2026-Q3",
        "climate_hazard_exposure": "Drought",
    }
    for col_idx, col_name in enumerate(ALL_COLUMNS, start=1):
        ws.cell(row=2, column=col_idx, value=example[col_name])

    # Dropdown validation kwa region na hazard, kusaidia kuepuka makosa ya uandishi
    region_list = ",".join(TANZANIA_REGIONS)
    dv_region = DataValidation(type="list", formula1=f'"{region_list}"', allow_blank=False)
    ws.add_data_validation(dv_region)
    dv_region.add(f"{ws.cell(row=2, column=ALL_COLUMNS.index('region')+1).column_letter}2:"
                  f"{ws.cell(row=2, column=ALL_COLUMNS.index('region')+1).column_letter}1000")

    hazard_list = ",".join(HAZARD_OPTIONS)
    dv_hazard = DataValidation(type="list", formula1=f'"{hazard_list}"', allow_blank=True)
    ws.add_data_validation(dv_hazard)
    dv_hazard.add(f"{ws.cell(row=2, column=ALL_COLUMNS.index('climate_hazard_exposure')+1).column_letter}2:"
                  f"{ws.cell(row=2, column=ALL_COLUMNS.index('climate_hazard_exposure')+1).column_letter}1000")

    # Ukurasa wa maelekezo
    ws2 = wb.create_sheet("Maelekezo_Instructions")
    instructions = [
        [f"CDR Standardized Data Template - {TEMPLATE_VERSION}"],
        [""],
        ["1. Usibadilishe majina ya vichwa vya column (row ya kwanza)."],
        ["2. Futa mfano (row ya 2) kabla ya kutuma data zako halisi."],
        ["3. Column zenye alama ya * ni LAZIMA zijazwe (mandatory)."],
        ["4. reporting_period lazima iwe kwa muundo: YYYY-Qn (mfano 2026-Q3)."],
        ["5. loan_amount_tzs na collateral_value_tzs lazima ziwe namba pekee (bila herufi)."],
        ["6. region lazima iwe mkoa halisi wa Tanzania (chagua kwenye dropdown)."],
        [""],
        ["Required columns: " + ", ".join(REQUIRED_COLUMNS)],
        ["Optional columns: " + ", ".join(OPTIONAL_COLUMNS)],
    ]
    for row in instructions:
        ws2.append(row)
    ws2.column_dimensions["A"].width = 90

    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    return buffer.read()
