"""
The reader of uploaded .xlsx files (app/services/excel_reader.py): the fast reader (calamine) must give the SAME cells as the old one (openpyxl), the old one
must take over when the fast one fails, and EXCEL_READER=openpyxl must be a complete way back.

The tests that need calamine are skipped where it is not installed (it is in requirements.txt, so it is there in the Docker image).
"""
import datetime as dt
import io

import pandas as pd
import pytest
from openpyxl import Workbook

from app.core.config import settings
from app.services import excel_reader
from app.services import template_generator as tg
from app.services.date_rules import OK, read_date
from app.services.excel_reader import engines_for, read_excel_grid
from app.services.validation_service import validate_excel_file
from tests.test_upload_and_workflow import VALID_ROW, build_test_excel

XLSX_BYTES = b"PK\x03\x04 pretend package"
SHEET = "Loan_Collateral_Data"


def _same(a, b) -> bool:
    if pd.isna(a) and pd.isna(b):
        return True
    if isinstance(a, dt.datetime) and isinstance(b, dt.datetime):          # a pandas Timestamp is a datetime: one reader may hand over either
        return pd.Timestamp(a) == pd.Timestamp(b)
    return type(a) is type(b) and a == b


def _assert_same_cells(first: pd.DataFrame, second: pd.DataFrame):
    assert first.shape == second.shape
    for r in range(first.shape[0]):
        for c in range(first.shape[1]):
            a, b = first.iat[r, c], second.iat[r, c]
            assert _same(a, b), f"row {r + 1}, column {c + 1}: {a!r} ({type(a).__name__}) against {b!r} ({type(b).__name__})"


def _messy_workbook() -> bytes:
    """Every kind of cell an institution might produce, in one sheet, with blank rows and columns between them."""
    wb = Workbook()
    ws = wb.active
    ws.title = SHEET
    ws.cell(1, 1, "Customer"); ws.cell(1, 2, "Number"); ws.cell(1, 3, "Decimal"); ws.cell(1, 4, "Date cell"); ws.cell(1, 5, "Date only")
    ws.cell(1, 6, "Date and time"); ws.cell(1, 7, "Date as text"); ws.cell(1, 8, "Yes/no"); ws.cell(1, 10, "After a blank column"); ws.cell(1, 11, "Serial number")
    ws.cell(2, 1, "CUST-1"); ws.cell(2, 2, 5_000_000); ws.cell(2, 3, 16.5); ws.cell(2, 4, dt.datetime(2026, 3, 15)); ws.cell(2, 5, dt.date(2026, 3, 15))
    ws.cell(2, 6, dt.datetime(2026, 3, 15, 14, 30)); ws.cell(2, 7, "2026-03-15"); ws.cell(2, 8, True); ws.cell(2, 10, "x"); ws.cell(2, 11, 46337)
    ws["D2"].number_format = "yyyy-mm-dd"
    ws["E2"].number_format = "dd/mm/yyyy"
    ws["F2"].number_format = "yyyy-mm-dd hh:mm"
    # a row of nothing, then a row with gaps, a long text, a negative number, a whole number written as a float, and a very large number
    ws.cell(4, 1, "A very long text " * 40); ws.cell(4, 2, -12); ws.cell(4, 3, 3.0); ws.cell(4, 4, dt.datetime(2030, 12, 31)); ws["D4"].number_format = "m/d/yyyy"
    ws.cell(4, 7, "04/05/2026"); ws.cell(4, 8, False); ws.cell(4, 11, 20260101)
    ws.cell(5, 2, 0); ws.cell(5, 3, 0.1); ws.cell(5, 11, 0.5)
    other = wb.create_sheet("Notes")
    other.cell(1, 1, "not the data")
    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


# ---------------------------------------------------------------- which reader is used

def test_auto_tries_the_fast_reader_first_and_keeps_the_old_one_as_the_fallback(monkeypatch):
    monkeypatch.setattr(settings, "EXCEL_READER", "auto")
    assert engines_for(XLSX_BYTES) == ["calamine", "openpyxl"]


def test_openpyxl_setting_is_a_complete_way_back(monkeypatch):
    monkeypatch.setattr(settings, "EXCEL_READER", "openpyxl")
    assert engines_for(XLSX_BYTES) == ["openpyxl"]


def test_calamine_setting_uses_only_the_fast_reader(monkeypatch):
    monkeypatch.setattr(settings, "EXCEL_READER", "calamine")
    assert engines_for(XLSX_BYTES) == ["calamine"]


@pytest.mark.parametrize("setting", ["auto", "calamine", "openpyxl", "AUTO", " Auto ", "", "nonsense"])
def test_anything_that_is_not_a_zip_package_keeps_the_old_reader(monkeypatch, setting):
    monkeypatch.setattr(settings, "EXCEL_READER", setting)
    assert engines_for(b"\xd0\xcf\x11\xe0 an old .xls file") == ["openpyxl"]       # the old binary Excel format is not sent to the fast reader
    assert engines_for(b"") == ["openpyxl"]


def test_an_unknown_setting_behaves_like_auto(monkeypatch):
    monkeypatch.setattr(settings, "EXCEL_READER", "nonsense")
    assert engines_for(XLSX_BYTES) == ["calamine", "openpyxl"]


# ---------------------------------------------------------------- the fallback

def test_when_the_fast_reader_fails_the_old_one_reads_the_file(monkeypatch):
    monkeypatch.setattr(settings, "EXCEL_READER", "auto")
    real_read, calls = excel_reader._read, []

    def broken_calamine(engine, file_bytes, sheet_name):
        calls.append(engine)
        if engine == "calamine":
            raise RuntimeError("the fast reader broke")
        return real_read(engine, file_bytes, sheet_name)

    monkeypatch.setattr(excel_reader, "_read", broken_calamine)
    frame = read_excel_grid(_messy_workbook(), sheet_name=SHEET)
    assert calls == ["calamine", "openpyxl"]
    assert frame.iat[1, 0] == "CUST-1"


def test_when_the_fast_reader_is_not_installed_the_old_one_reads_the_file(monkeypatch):
    monkeypatch.setattr(settings, "EXCEL_READER", "auto")
    real_read = excel_reader._read

    def not_installed(engine, file_bytes, sheet_name):
        if engine == "calamine":
            raise ImportError("Missing optional dependency 'python-calamine'")
        return real_read(engine, file_bytes, sheet_name)

    monkeypatch.setattr(excel_reader, "_read", not_installed)
    records, issues = validate_excel_file(build_test_excel([VALID_ROW]), "data.xlsx")
    assert len(records) == 1 and not [i for i in issues if i.severity == "ERROR"]


def test_the_way_back_never_touches_the_fast_reader(monkeypatch):
    monkeypatch.setattr(settings, "EXCEL_READER", "openpyxl")
    real_read, calls = excel_reader._read, []

    def recording(engine, file_bytes, sheet_name):
        calls.append(engine)
        return real_read(engine, file_bytes, sheet_name)

    monkeypatch.setattr(excel_reader, "_read", recording)
    read_excel_grid(_messy_workbook(), sheet_name=SHEET)
    assert calls == ["openpyxl"]


def test_a_damaged_file_still_ends_in_an_error_the_caller_can_report(monkeypatch):
    monkeypatch.setattr(settings, "EXCEL_READER", "auto")
    with pytest.raises(Exception):
        read_excel_grid(b"PK this is not a workbook", sheet_name=SHEET)


def test_a_missing_sheet_raises_and_the_first_sheet_can_be_read_instead(monkeypatch):
    monkeypatch.setattr(settings, "EXCEL_READER", "auto")
    data = _messy_workbook()
    with pytest.raises(Exception):
        read_excel_grid(data, sheet_name="No such sheet")
    assert read_excel_grid(data).iat[1, 0] == "CUST-1"       # what validate_excel_file does when the sheet is not called Loan_Collateral_Data


# ---------------------------------------------------------------- the two readers give the same cells (need calamine)

@pytest.fixture
def calamine():
    pytest.importorskip("python_calamine")


def test_both_readers_give_the_same_cells_for_every_kind_of_cell(calamine):
    data = _messy_workbook()
    _assert_same_cells(excel_reader._read("openpyxl", data, SHEET), excel_reader._read("calamine", data, SHEET))


def test_both_readers_give_the_same_cells_for_the_official_template(calamine):
    data = tg.load_loan_collateral_template()
    _assert_same_cells(excel_reader._read("openpyxl", data, SHEET), excel_reader._read("calamine", data, SHEET))


def test_both_readers_give_the_same_first_sheet_when_no_sheet_is_named(calamine):
    data = _messy_workbook()
    _assert_same_cells(excel_reader._read("openpyxl", data, None), excel_reader._read("calamine", data, None))


def test_a_date_cell_is_a_date_for_both_readers_and_a_serial_number_stays_a_number(calamine):
    data = _messy_workbook()
    for engine in ("openpyxl", "calamine"):
        frame = excel_reader._read(engine, data, SHEET)
        assert read_date(frame.iat[1, 3]) == (dt.date(2026, 3, 15), OK), engine          # a real date cell
        assert read_date(frame.iat[1, 4]) == (dt.date(2026, 3, 15), OK), engine
        assert read_date(frame.iat[1, 5]) == (dt.date(2026, 3, 15), OK), engine          # the time of day is dropped
        assert read_date(frame.iat[1, 6]) == (dt.date(2026, 3, 15), OK), engine          # year-first text
        assert read_date(frame.iat[1, 10])[1] != OK, engine                              # 46337 in a General cell is a number: refused, as the rules say


def _file_with_every_kind_of_date() -> bytes:
    rows = [
        VALID_ROW,
        dict(VALID_ROW, loan_id="LN-2", disbursement_date=dt.datetime(2026, 3, 15), maturity_date="2029-03-15", collateral_pledged_date=dt.date(2026, 3, 15)),
        dict(VALID_ROW, loan_id="LN-3", disbursement_date="04/05/2026", maturity_date=46337, collateral_pledged_date="25/03/2026"),
        dict(VALID_ROW, loan_id="LN-4", region="Nowhere", district="Nowhere"),
        dict(VALID_ROW, loan_id="LN-1"),                                                  # a duplicate loan number
        dict(VALID_ROW, loan_id="LN-6", loan_amount_tzs="not a number"),
    ]
    return build_test_excel(rows)


def _summary(records, issues):
    return ([sorted((k, str(v)) for k, v in r.items()) for r in records],
            [(i.row_number, i.column_name, i.description, i.severity) for i in issues])


def test_checking_a_file_gives_the_same_records_and_findings_with_either_reader(calamine, monkeypatch):
    data = _file_with_every_kind_of_date()
    answers = {}
    for setting in ("openpyxl", "calamine", "auto"):
        monkeypatch.setattr(settings, "EXCEL_READER", setting)
        answers[setting] = _summary(*validate_excel_file(data, "data.xlsx"))
    assert answers["calamine"] == answers["openpyxl"]
    assert answers["auto"] == answers["openpyxl"]
    assert answers["openpyxl"][1], "the test file should have findings, otherwise it proves little"


def test_the_official_template_is_checked_the_same_way_with_either_reader(calamine, monkeypatch):
    data = tg.load_loan_collateral_template()
    answers = {}
    for setting in ("openpyxl", "calamine"):
        monkeypatch.setattr(settings, "EXCEL_READER", setting)
        answers[setting] = _summary(*validate_excel_file(data, "template.xlsx"))
    assert answers["calamine"] == answers["openpyxl"]
