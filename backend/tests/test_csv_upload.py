"""CSV upload (the Concept Note's upload panel lists Excel and CSV): the same validation as an Excel file."""
import csv
import io

import pytest

from app.services.template_generator import COLUMNS
from app.services.validation_service import _clean_float, read_csv_as_frame
from tests.conftest import auth_header, login
from tests.test_upload_and_workflow import VALID_ROW, _setup_institution_user

FIELDS = [f for f, _ in COLUMNS]
LABELS = dict(COLUMNS)


def build_csv(rows, delimiter=",", bom=False, title_lines=0, encoding="utf-8") -> bytes:
    """A CSV laid out like the template saved from Excel: optional short title lines, then the header row, then the data."""
    buf = io.StringIO()
    writer = csv.writer(buf, delimiter=delimiter, lineterminator="\r\n")
    for i in range(title_lines):
        writer.writerow([f"LOAN AND COLLATERAL DATA AS AT 2026-Q1 (line {i})"])   # rows much shorter than the header
    writer.writerow([LABELS[f] for f in FIELDS])
    for row in rows:
        writer.writerow(["" if row.get(f) is None else row.get(f) for f in FIELDS])
    data = buf.getvalue().encode(encoding)
    return (b"\xef\xbb\xbf" + data) if bom else data


def _upload(client, token, content: bytes, filename="data.csv", content_type="text/csv", period="2026-Q1"):
    return client.post(
        "/api/submissions/upload", data={"reporting_period": period},
        files={"file": (filename, content, content_type)}, headers=auth_header(token),
    )


@pytest.fixture()
def token(client, db_session):
    _setup_institution_user(db_session)
    return login(client, "inst_user").json()["access_token"]


def test_a_valid_csv_is_accepted_like_an_excel_file(client, token):
    res = _upload(client, token, build_csv([VALID_ROW]))
    assert res.status_code == 201
    assert res.json()["status"] == "VALID" and res.json()["valid_records"] == 1


@pytest.mark.parametrize("kwargs", [
    {"delimiter": ";"}, {"delimiter": "\t"}, {"bom": True}, {"title_lines": 3},
    {"delimiter": ";", "bom": True, "title_lines": 2},
])
def test_separators_byte_order_mark_and_title_lines_are_handled(client, token, kwargs):
    res = _upload(client, token, build_csv([VALID_ROW], **kwargs))
    assert res.status_code == 201
    assert res.json()["status"] == "VALID", res.json()


def test_windows_1252_text_is_read(client, token):
    row = dict(VALID_ROW, customer_id="CUST-é")
    res = _upload(client, token, build_csv([row], encoding="cp1252"))
    assert res.status_code == 201 and res.json()["status"] == "VALID"


def test_amounts_written_with_thousands_separators_are_accepted(client, token):
    row = dict(VALID_ROW, loan_amount_tzs="5,000,000", collateral_value_tzs="8,000,000.50")
    res = _upload(client, token, build_csv([row]))
    assert res.status_code == 201 and res.json()["status"] == "VALID"


def test_a_bad_value_in_a_csv_is_flagged_row_by_row_not_rejected(client, token):
    bad = dict(VALID_ROW, loan_id="LN-2", region="Narnia")
    res = _upload(client, token, build_csv([VALID_ROW, bad]))
    assert res.status_code == 201
    assert res.json()["status"] == "INVALID" and res.json()["invalid_records"] == 1


def test_a_csv_without_the_template_header_is_invalid_with_a_clear_message(client, token):
    res = _upload(client, token, b"a,b,c\r\n1,2,3\r\n")
    assert res.status_code == 201 and res.json()["status"] == "INVALID"


def test_an_empty_csv_does_not_crash(client, token):
    res = _upload(client, token, b"")
    assert res.status_code == 201 and res.json()["status"] == "INVALID"


def test_other_file_types_are_still_refused(client, token):
    assert _upload(client, token, b"x", filename="data.txt", content_type="text/plain").status_code == 400
    assert _upload(client, token, b"x", filename="data.csv", content_type="application/x-msdownload").status_code == 400


def test_windows_browsers_send_excel_content_type_for_csv(client, token):
    res = _upload(client, token, build_csv([VALID_ROW]), content_type="application/vnd.ms-excel")
    assert res.status_code == 201 and res.json()["status"] == "VALID"


def test_the_original_csv_can_be_downloaded_as_csv(client, token):
    sid = _upload(client, token, build_csv([VALID_ROW])).json()["id"]
    res = client.get(f"/api/submissions/{sid}/download", headers=auth_header(token))
    assert res.status_code == 200 and res.headers["content-type"].startswith("text/csv")
    assert LABELS["loan_id"].encode() in res.content


@pytest.mark.parametrize("value,expected", [
    ("5,000,000", 5_000_000.0), ("1,250,000.50", 1_250_000.5), ("-1,000", -1000.0), ("1500", 1500.0), (1500, 1500.0), ("", None),
])
def test_grouped_numbers(value, expected):
    assert _clean_float(value) == expected


@pytest.mark.parametrize("value", ["5,00,0", "1,5", "12,34", "1,000,", ",100", "abc"])
def test_other_comma_shapes_are_still_refused_not_guessed(value):
    assert _clean_float(value) == "INVALID"


def test_the_frame_pads_short_rows_and_turns_blanks_into_none():
    frame = read_csv_as_frame(b"title\r\na,b,c\r\n1,,3\r\n")
    assert frame.shape == (3, 3)
    assert frame.iloc[0, 1] is None and frame.iloc[2, 1] is None
