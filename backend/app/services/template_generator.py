"""
Generates the standardized Excel data-submission template - MODULE D.
Institutions download this template, fill it in, then upload it back into the system.
"""
import io
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.worksheet.datavalidation import DataValidation
from openpyxl.workbook.defined_name import DefinedName
from openpyxl.utils import get_column_letter

TEMPLATE_VERSION = "v1.1"

REQUIRED_COLUMNS = [
    "loan_id", "borrower_name", "loan_amount_tzs", "collateral_type",
    "collateral_value_tzs", "region", "district", "reporting_period",
]
OPTIONAL_COLUMNS = ["climate_hazard_exposure"]

ALL_COLUMNS = REQUIRED_COLUMNS + OPTIONAL_COLUMNS

# Source: Wikipedia "Districts of Tanzania" / "Regions of Tanzania" (verified via
# web search), listing all 31 regions and their district/city/town councils as of
# the most recent administrative boundaries (Songwe Region created 2016).
REGION_DISTRICTS: dict[str, list[str]] = {
    "Dodoma": ["Dodoma City", "Kondoa Urban", "Bahi District", "Chamwino District", "Chemba District", "Kondoa District", "Kongwa District", "Mpwapwa District"],
    "Singida": ["Singida Urban", "Ikungi District", "Iramba District", "Itigi District", "Manyoni District", "Mkalama District", "Singida District"],
    "Tabora": ["Tabora Urban", "Nzega Urban", "Igunga District", "Kaliua District", "Nzega District", "Sikonge District", "Urambo District", "Uyui District"],
    "Dar es Salaam": ["Ilala", "Kigamboni", "Kinondoni", "Temeke", "Ubungo"],
    "Lindi": ["Lindi City", "Kilwa District", "Lindi District", "Liwale District", "Nachingwea District", "Ruangwa District"],
    "Morogoro": ["Morogoro City", "Ifakara Urban", "Gairo District", "Kilombero District", "Kilosa District", "Malinyi District", "Morogoro District", "Mvomero District", "Ulanga District"],
    "Mtwara": ["Mtwara City", "Masasi Urban", "Nanyumbu Urban", "Newala Urban", "Masasi District", "Mtwara District", "Nanyumbu District", "Newala District", "Tandahimba District"],
    "Pwani": ["Kibaha Urban", "Bagamoyo District", "Chalinze District", "Kibaha District", "Kisarawe District", "Mafia District", "Mkuranga District", "Rufiji District"],
    "Kagera": ["Bukoba City", "Biharamulo District", "Bukoba District", "Karagwe District", "Kyerwa District", "Missenyi District", "Muleba District", "Ngara District"],
    "Kigoma": ["Kigoma-Ujiji", "Kasulu Urban", "Buhigwe District", "Kakonko District", "Kasulu District", "Kibondo District", "Kigoma District", "Uvinza District"],
    "Geita": ["Geita Urban", "Bukombe District", "Chato District", "Geita District", "Mbogwe District", "Nyanghwale District"],
    "Mara": ["Musoma City", "Bunda Urban", "Tarime Urban", "Bunda District", "Butiama District", "Musoma District", "Rorya District", "Serengeti District", "Tarime District"],
    "Mwanza": ["Mwanza City", "Ilemela Urban", "Buchosa District", "Kwimba District", "Magu District", "Misungwi District", "Sengerema District", "Ukerewe District"],
    "Shinyanga": ["Shinyanga City", "Kahama City", "Kishapu District", "Msalala District", "Shinyanga District", "Ushetu District"],
    "Simiyu": ["Bariadi Urban", "Bariadi District", "Busega District", "Itilima District", "Maswa District", "Meatu District"],
    "Arusha": ["Arusha City", "Arusha District", "Karatu District", "Longido District", "Meru District", "Monduli District", "Ngorongoro District"],
    "Kilimanjaro": ["Moshi City", "Hai District", "Moshi District", "Mwanga District", "Rombo District", "Same District", "Siha District"],
    "Manyara": ["Babati Urban", "Mbulu Urban", "Babati District", "Hanang District", "Kiteto District", "Mbulu District", "Simanjiro District"],
    "Tanga": ["Tanga City", "Handeni Urban", "Korogwe Urban", "Bumbuli District", "Handeni District", "Kilindi District", "Korogwe District", "Lushoto District", "Mkinga District", "Muheza District", "Pangani District"],
    "Iringa": ["Iringa City", "Mafinga Urban", "Iringa District", "Kilolo District", "Mufindi District"],
    "Katavi": ["Mpanda Urban", "Mlele District", "Mpanda District", "Mpimbwe District", "Nsimbo District"],
    "Mbeya": ["Mbeya City", "Busokelo District", "Chunya District", "Kyela District", "Mbarali District", "Mbeya District", "Rungwe District"],
    "Njombe": ["Njombe Urban", "Makambako Urban", "Ludewa District", "Makete District", "Njombe Rural District", "Wangingombe District"],
    "Rukwa": ["Sumbawanga City", "Kalambo District", "Nkasi District", "Sumbawanga District"],
    "Ruvuma": ["Songea City", "Mbinga Urban", "Madaba District", "Mbinga District", "Namtumbo District", "Nyasa District", "Songea District", "Tunduru District"],
    "Songwe": ["Tunduma Urban", "Ileje District", "Mbozi District", "Momba District", "Songwe District"],
    "Mjini Magharibi": ["Zanzibar City", "Zanzibar West District"],
    "Kaskazini Unguja": ["Kaskazini A District", "Kaskazini B District"],
    "Kusini Unguja": ["Kati District", "Kusini District"],
    "Kaskazini Pemba": ["Micheweni District", "Wete District"],
    "Kusini Pemba": ["Chake Chake District", "Mkoani District"],
}

TANZANIA_REGIONS = list(REGION_DISTRICTS.keys())

HAZARD_OPTIONS = ["None", "Drought", "Flood", "Cyclone", "Landslide"]

# Source: Bank of Tanzania "Report on Climate Risk Analysis in the Banking Sector"
# (March 2026), Chart 5/6/7/8 - the real collateral categories used in BOT's own
# Climate Data Repository. Not invented - taken directly from that published report.
COLLATERAL_TYPES = ["Mortgage", "Landed Property", "Financial Assets", "Cash", "Equipment", "Land", "Others"]


def generate_loan_collateral_template() -> bytes:
    """Generates an Excel (.xlsx) file with the standardized loan/collateral data layout."""
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

    # Example row showing how to fill in the template
    example = {
        "loan_id": "LN-2026-0001",
        "borrower_name": "Example Company Ltd",
        "loan_amount_tzs": 50000000,
        "collateral_type": "Landed Property",
        "collateral_value_tzs": 80000000,
        "region": "Dodoma",
        "district": "Chamwino District",
        "reporting_period": "2026-Q3",
        "climate_hazard_exposure": "Drought",
    }
    for col_idx, col_name in enumerate(ALL_COLUMNS, start=1):
        ws.cell(row=2, column=col_idx, value=example[col_name])

    region_col_idx = ALL_COLUMNS.index("region") + 1
    district_col_idx = ALL_COLUMNS.index("district") + 1
    region_col_letter = get_column_letter(region_col_idx)
    district_col_letter = get_column_letter(district_col_idx)

    # Region dropdown - all 31 regions
    region_list = ",".join(TANZANIA_REGIONS)
    dv_region = DataValidation(type="list", formula1=f'"{region_list}"', allow_blank=False)
    ws.add_data_validation(dv_region)
    dv_region.add(f"{region_col_letter}2:{region_col_letter}1000")

    # Hidden "Lists" sheet holding each region's districts, referenced by named ranges,
    # so the District dropdown automatically narrows to match whichever Region was chosen
    # on the same row (a "cascading dropdown") - this is what prevents typing errors.
    lists_ws = wb.create_sheet("Lists")
    for col_idx, region in enumerate(TANZANIA_REGIONS, start=1):
        districts = REGION_DISTRICTS[region]
        col_letter = get_column_letter(col_idx)
        for row_idx, district_name in enumerate(districts, start=1):
            lists_ws.cell(row=row_idx, column=col_idx, value=district_name)
        safe_name = region.replace(" ", "_")
        ref = f"Lists!${col_letter}$1:${col_letter}${len(districts)}"
        wb.defined_names[safe_name] = DefinedName(safe_name, attr_text=ref)
    lists_ws.sheet_state = "hidden"

    dv_district = DataValidation(
        type="list",
        formula1=f'INDIRECT(SUBSTITUTE(${region_col_letter}2," ","_"))',
        allow_blank=True,
        showErrorMessage=True,
        errorTitle="Select a Region first",
        error="Please choose a Region in this row before selecting a District.",
    )
    ws.add_data_validation(dv_district)
    dv_district.add(f"{district_col_letter}2:{district_col_letter}1000")

    hazard_list = ",".join(HAZARD_OPTIONS)
    dv_hazard = DataValidation(type="list", formula1=f'"{hazard_list}"', allow_blank=True)
    ws.add_data_validation(dv_hazard)
    dv_hazard.add(f"{ws.cell(row=2, column=ALL_COLUMNS.index('climate_hazard_exposure')+1).column_letter}2:"
                  f"{ws.cell(row=2, column=ALL_COLUMNS.index('climate_hazard_exposure')+1).column_letter}1000")

    collateral_type_list = ",".join(COLLATERAL_TYPES)
    dv_collateral_type = DataValidation(type="list", formula1=f'"{collateral_type_list}"', allow_blank=False)
    ws.add_data_validation(dv_collateral_type)
    dv_collateral_type.add(f"{ws.cell(row=2, column=ALL_COLUMNS.index('collateral_type')+1).column_letter}2:"
                            f"{ws.cell(row=2, column=ALL_COLUMNS.index('collateral_type')+1).column_letter}1000")

    # Instructions sheet
    ws2 = wb.create_sheet("Instructions")
    instructions = [
        [f"CDR Standardized Data Template - {TEMPLATE_VERSION}"],
        [""],
        ["1. Do not change the column header names (row 1)."],
        ["2. Delete the example row (row 2) before submitting your real data."],
        ["3. Columns marked as mandatory below must always be filled in."],
        ["4. reporting_period must follow the format: YYYY-Qn (e.g. 2026-Q3)."],
        ["5. loan_amount_tzs and collateral_value_tzs must be numbers only (no letters or symbols)."],
        ["6. region must be chosen from the dropdown (all 31 official Tanzanian regions)."],
        ["7. district must be chosen from the dropdown - it automatically narrows to match the"],
        ["   region you selected in that row. Select the Region first, then the District."],
        ["8. collateral_type must be chosen from the dropdown (Mortgage, Landed Property,"],
        ["   Financial Assets, Cash, Equipment, Land, Others) - matching the categories used"],
        ["   in BOT's own Climate Data Repository (Report on Climate Risk Analysis, March 2026)."],
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
