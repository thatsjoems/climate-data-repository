"""
The template an institution downloads (app/data/BOT-CDR-Loan_Collateral-Template.xlsx) and the download itself.

The file is supplied as it is, not generated, so these tests are what keeps it in agreement with the code: the 38 headers in the order the upload
reads them, the option lists the upload accepts, dropdowns and checks all the way down to row 100,009, the Excel check of a coordinate against the
chosen ward, the thousands separators, and an example row that the upload itself accepts. The upload's own validation is covered by the other test files.
"""
import io
import re

import pytest
from openpyxl import load_workbook

from app.services import boundary_service as bs
from app.services import geo_lookup as geo
from app.services import template_generator as tg
from app.services.validation_service import validate_excel_file
from tests.conftest import auth_header, login, make_user

BEREKO = (-4.4566, 35.7547)
GOBA_DAR_ES_SALAAM = (-6.7667, 39.15)


@pytest.fixture(scope="module")
def wb():
    return load_workbook(io.BytesIO(tg.load_loan_collateral_template()))


def _named_values(wb, name):
    m = re.match(r"Lists!\$A\$(\d+):\$A\$(\d+)", wb.defined_names[name].attr_text)
    col = [c.value for c in wb["Lists"]["A"]]
    return [v for v in col[int(m[1]) - 1:int(m[2])] if v]


# ------------------------------------------------------------------------------------------------ structure
def test_the_file_has_the_expected_sheets_and_the_helper_sheets_are_hidden(wb):
    assert wb.sheetnames == ["Instructions", "Loan_Collateral_Data", "Lists", "WardBox"]
    assert [wb[s].sheet_state for s in wb.sheetnames] == ["visible", "visible", "hidden", "hidden"]


def test_the_headers_are_the_38_columns_in_the_order_the_upload_reads(wb):
    ws = wb["Loan_Collateral_Data"]
    assert [c.value for c in ws[9]][:38] == [label for _, label in tg.COLUMNS]
    assert len(tg.COLUMNS) == 38


def test_the_instructions_state_the_limit_of_100000_loans_and_where_it_ends(wb):
    text = " ".join(str(c.value) for c in wb["Instructions"]["A"] if c.value)
    assert "100,000" in text and str(tg.LAST_LOAN_ROW) in text.replace(",", "")


def test_the_example_row_is_accepted_by_the_upload_itself():
    records, issues = validate_excel_file(tg.load_loan_collateral_template(), "template.xlsx")
    assert len(records) == 1 and records[0]["is_valid"] is True
    assert [i for i in issues if i.severity == "ERROR"] == []


# ------------------------------------------------------------------------------------------------ the lists
def test_the_dropdown_lists_are_the_ones_the_upload_accepts(wb):
    expected = {
        "LIST_CLIENT_TYPE": tg.CLIENT_TYPES, "LIST_BUSINESS_SIZE": tg.BUSINESS_SIZES, "LIST_LOAN_TYPE": tg.LOAN_TYPES,
        "LIST_CURRENCY": tg.CURRENCIES, "LIST_LOAN_ECON_ACTIVITY": tg.LOAN_ECONOMIC_ACTIVITIES,
        "LIST_ASSET_CLASS": tg.ASSET_CLASSIFICATIONS, "LIST_COLLATERAL_TYPE": tg.COLLATERAL_TYPES, "LIST_YES_NO": tg.YES_NO,
    }
    for name, values in expected.items():
        assert _named_values(wb, name) == list(values), name


def test_the_regions_and_their_districts_are_the_ones_the_upload_accepts(wb):
    assert sorted(_named_values(wb, "ALL_REGIONS")) == sorted(tg.TANZANIA_REGIONS)
    safe = lambda s: re.sub(r"[ .\-/'\"()]", "_", s)
    for region in tg.TANZANIA_REGIONS:
        assert sorted(_named_values(wb, "REG_" + safe(region))) == sorted(tg.REGION_DISTRICTS[region]), region


# ------------------------------------------------------------------------------------------------ rows 10 to 100,009
def test_every_dropdown_and_check_reaches_the_last_row(wb):
    ws = wb["Loan_Collateral_Data"]
    validations = ws.data_validations.dataValidation
    assert len(validations) == 20
    for v in validations:
        for rng in str(v.sqref).split():
            first, last = rng.split(":")
            assert first.lstrip("ABCDEFGHIJKLMNOPQRSTUVWXYZ") == str(tg.FIRST_LOAN_ROW), rng
            assert last.lstrip("ABCDEFGHIJKLMNOPQRSTUVWXYZ") == str(tg.LAST_LOAN_ROW), rng


def test_the_four_coordinate_checks_use_the_ward_boxes(wb):
    ws = wb["Loan_Collateral_Data"]
    custom = {str(v.sqref).split(":")[0]: v for v in ws.data_validations.dataValidation if v.type == "custom"}
    assert sorted(custom) == ["AG10", "AH10", "V10", "W10"]
    for cell, v in custom.items():
        assert "WBK" in v.formula1 and "MATCH" in v.formula1
        assert len(v.formula1) < 255                      # Excel's limit for a validation formula
        assert v.errorStyle == "stop" and v.showErrorMessage and v.allow_blank
    # the loan pair reads columns R, S, T; the collateral pair AC, AD, AE
    assert "R10" in custom["V10"].formula1 and "T10" in custom["W10"].formula1
    assert "AC10" in custom["AG10"].formula1 and "AE10" in custom["AH10"].formula1


def test_the_ward_boxes_are_real_wards_and_hold_their_own_points(wb):
    box = wb["WardBox"]
    rows = [[c.value for c in r] for r in box.iter_rows(min_row=2)]
    assert len(rows) > 4300
    for key, la0, la1, lo0, lo1 in rows:
        region, district, ward = key.split("|")
        assert geo.is_valid_ward(region, district, ward), key
        assert -12.5 < la0 < la1 < 0 and 29 < lo0 < lo1 < 41, key
    keyed = {r[0]: r for r in rows}
    _, la0, la1, lo0, lo1 = keyed["Dodoma|Kondoa|Bereko"]
    assert la0 <= BEREKO[0] <= la1 and lo0 <= BEREKO[1] <= lo1
    assert not (la0 <= GOBA_DAR_ES_SALAAM[0] <= la1 and lo0 <= GOBA_DAR_ES_SALAAM[1] <= lo1)


def test_every_ward_box_contains_the_boundary_of_a_ward_of_that_name(wb):
    """The boxes were derived from the same boundary data the upload uses: each one must hold the whole of at least one ward with that place name."""
    b = bs._load()
    n = bs._norm
    checked = 0
    for r in wb["WardBox"].iter_rows(min_row=2):
        key, la0, la1, lo0, lo1 = [c.value for c in r]
        region, district, ward = (n(p) for p in key.split("|"))
        wards = b.by_ward.get((region, district, ward))
        if not wards:                       # a few names are matched by similarity in the upload; the boxes were built the same way
            continue
        checked += 1
        assert any(la0 <= w.bbox[1] / b.scale and w.bbox[3] / b.scale <= la1 and lo0 <= w.bbox[0] / b.scale and w.bbox[2] / b.scale <= lo1
                   for w in wards), key
    assert checked > 4200


# ------------------------------------------------------------------------------------------------ money columns
def test_the_money_columns_show_thousands_separators(wb):
    ws = wb["Loan_Collateral_Data"]
    for col in ("F", "K", "L", "Z", "AA", "AL"):
        assert ws[f"{col}10"].number_format == "#,##0", col
        assert ws.column_dimensions[col].number_format == "#,##0", col
    assert ws["M10"].number_format == "General"       # the interest rate is not money


# ------------------------------------------------------------------------------------------------ date columns
def test_the_date_columns_show_dates_as_year_month_day(wb):
    """A date typed into a General cell is shown in the computer's own order (11/11/2026), which is confusing next to the header and the example
    (2026-03-15). The three date columns carry the format yyyy-mm-dd, so a typed date is a real date cell that is shown the way the upload reads it."""
    ws = wb["Loan_Collateral_Data"]
    for col in ("H", "I", "Y"):                       # disbursement, maturity, collateral pledged
        assert ws.column_dimensions[col].number_format.replace("\\", "") == "yyyy-mm-dd", col
    assert ws["H10"].value == "2026-03-15"            # the example row is unchanged


# ------------------------------------------------------------------------------------------------ the download
def test_the_download_needs_a_login(client):
    assert client.get("/api/templates/loan-collateral/download").status_code in (401, 403)


def test_the_download_is_the_file_under_its_official_name(client, db_session):
    make_user(db_session, username="downloader")
    token = login(client, "downloader").json()["access_token"]
    res = client.get("/api/templates/loan-collateral/download", headers=auth_header(token))
    assert res.status_code == 200
    assert "BOT-CDR-Loan_Collateral-Template.xlsx" in res.headers["content-disposition"]
    assert res.content == tg.load_loan_collateral_template()


def test_every_message_in_the_template_is_within_excels_limits(wb):
    """Excel repairs ("We found a problem with some content") a file whose validation titles exceed 32 characters or whose messages exceed 255."""
    ws = wb["Loan_Collateral_Data"]
    for v in ws.data_validations.dataValidation:
        for attr, limit in (("errorTitle", 32), ("promptTitle", 32), ("error", 255), ("prompt", 255)):
            assert len(getattr(v, attr) or "") <= limit, (str(v.sqref), attr)
