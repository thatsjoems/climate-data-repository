"""Shapefile ZIP upload (the Concept Note's upload panel): read safely, in memory, into the same validation as an Excel file."""
import io
import struct
import zipfile

import pytest

from app.services.shapefile_service import (
    MAX_MEMBERS, SHORT_NAMES, ShapefileError, shapefile_zip_as_frame,
)
from app.services.template_generator import COLUMNS
from app.services.validation_service import validate_excel_file
from tests.shapefile_builder import build_shapefile_zip
from tests.test_csv_upload import _upload
from tests.test_upload_and_workflow import _setup_institution_user
from tests.conftest import auth_header, login

ROW = {
    "customer_id": "CUST-1", "loan_id": "LN-1", "loan_amount_tzs": "5000000", "collateral_type": "Residential mortgage",
    "collateral_value_tzs": "8000000", "region": "Dodoma", "district": "Dodoma",
}
POINT = (35.75, -6.18)   # inside Dodoma district (longitude, latitude)
FIELDS = [f for f, _ in COLUMNS]


def _frame(zip_bytes, **kw):
    return shapefile_zip_as_frame(zip_bytes, **kw)


def test_every_template_column_has_one_unique_dbf_name_of_at_most_ten_characters():
    assert set(SHORT_NAMES) == set(FIELDS)
    assert all(len(name) <= 10 for name in SHORT_NAMES.values())
    assert len(set(SHORT_NAMES.values())) == len(SHORT_NAMES)


def test_a_point_layer_becomes_the_template_grid_with_the_point_as_the_loan_location():
    frame = _frame(build_shapefile_zip([ROW], [POINT]))
    assert list(frame.iloc[0]) == [label for _f, label in COLUMNS]
    row = dict(zip(FIELDS, frame.iloc[1]))
    assert row["customer_id"] == "CUST-1" and row["district"] == "Dodoma"
    assert row["loan_longitude"] == POINT[0] and row["loan_latitude"] == POINT[1]


def test_full_template_names_are_accepted_when_the_table_has_them():
    frame = _frame(build_shapefile_zip([{"customer_id": "C9", "loan_id": "L9"}], [POINT], short_names=False))
    assert dict(zip(FIELDS, frame.iloc[1]))["customer_id"] == "C9"


def test_the_point_wins_over_coordinate_columns_and_a_record_without_a_shape_keeps_its_columns():
    rows = [dict(ROW, loan_lat="1", loan_lon="2"), dict(ROW, loan_id="LN-2", loan_lat="-6.2", loan_lon="35.7")]
    rows = [{("loan_latitude" if k == "loan_lat" else "loan_longitude" if k == "loan_lon" else k): v for k, v in r.items()} for r in rows]
    frame = _frame(build_shapefile_zip(rows, [POINT, None]))
    first, second = (dict(zip(FIELDS, frame.iloc[i])) for i in (1, 2))
    assert first["loan_latitude"] == POINT[1]
    assert second["loan_latitude"] == "-6.2"


def test_a_valid_shapefile_passes_the_same_validation_as_an_excel_file():
    records, issues = validate_excel_file(build_shapefile_zip([ROW], [POINT]), "loans.zip", form_reporting_period="2026-Q1")
    assert issues == [] and len(records) == 1 and records[0]["is_valid"]
    assert records[0]["loan_latitude"] == POINT[1]


def test_a_wrong_value_in_a_shapefile_is_flagged_on_its_row_like_any_other_file():
    records, _ = validate_excel_file(build_shapefile_zip([dict(ROW, region="Narnia")], [POINT]), "loans.zip", form_reporting_period="2026-Q1")
    assert len(records) == 1 and not records[0]["is_valid"]


def test_windows_1252_text_is_read_with_the_cpg_encoding():
    frame = _frame(build_shapefile_zip([dict(ROW, branch_name="Ubungo Café")], [POINT], encoding="cp1252", cpg="cp1252"))
    assert dict(zip(FIELDS, frame.iloc[1]))["branch_name"] == "Ubungo Café"


@pytest.mark.parametrize("make, message", [
    (lambda: b"this is not a zip", "not a valid ZIP"),
    (lambda: build_shapefile_zip([ROW], [POINT], extra_members={"run.exe": b"MZ"}), "not part of a shapefile"),
    (lambda: build_shapefile_zip([ROW], [POINT], extra_members={"../../etc/x.dbf": b"x"}), "unsafe name"),
    (lambda: build_shapefile_zip([ROW], [POINT], extra_members={"/abs/x.dbf": b"x"}), "unsafe name"),
    (lambda: build_shapefile_zip([ROW], [POINT], extra_members={"inner.zip": b"PK"}), "not part of a shapefile"),
    (lambda: build_shapefile_zip([ROW], [POINT], extra_members={"other.shp": b"x", "other.dbf": b"x"}), "exactly ONE"),
    (lambda: build_shapefile_zip([ROW], [POINT], prj='PROJCS["WGS_1984_UTM_Zone_36S"]'), "projected"),
    (lambda: build_shapefile_zip([ROW], [POINT], shape_type=5), "does not hold points"),
    (lambda: build_shapefile_zip([ROW, ROW], [POINT]), "Export the layer again"),
])
def test_refused_zips_say_why(make, message):
    with pytest.raises(ShapefileError) as err:
        _frame(make())
    assert message in str(err.value)


def test_a_zip_without_a_dbf_table_is_refused():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("a.shp", b"x")
    with pytest.raises(ShapefileError, match="no .dbf"):
        _frame(buf.getvalue())


def test_too_many_members_are_refused():
    extra = {f"n{i}.xml": b"<a/>" for i in range(MAX_MEMBERS + 1)}
    with pytest.raises(ShapefileError, match="at most"):
        _frame(build_shapefile_zip([ROW], [POINT], extra_members=extra))


def test_more_records_than_the_row_limit_are_refused_before_any_record_is_read():
    with pytest.raises(ShapefileError, match="exceeds the maximum"):
        _frame(build_shapefile_zip([ROW] * 3, [POINT] * 3), max_rows=2)


def test_a_zip_that_unpacks_to_far_more_than_it_says_is_refused(monkeypatch):
    """A 'ZIP bomb': a tiny file that unpacks to a huge one. The limits are lowered here so the test stays small."""
    from app.services import shapefile_service as svc
    monkeypatch.setattr(svc, "MAX_MEMBER_BYTES", 1024 * 1024)
    bomb = build_shapefile_zip([ROW], [POINT], prj='GEOGCS["' + "x" * (5 * 1024 * 1024))
    assert len(bomb) < 100 * 1024
    with pytest.raises(ShapefileError, match="too large once unpacked"):
        _frame(bomb)


def test_a_cut_short_shp_is_refused_not_a_crash():
    good = build_shapefile_zip([ROW], [POINT])
    buf = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(good)) as src, zipfile.ZipFile(buf, "w") as dst:
        for info in src.infolist():
            data = src.read(info)
            dst.writestr(info.filename, data[:-10] if info.filename.endswith(".shp") else data)
    with pytest.raises(ShapefileError):
        _frame(buf.getvalue())


def test_a_garbage_dbf_header_is_refused_not_a_crash():
    good = build_shapefile_zip([ROW], [POINT])
    buf = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(good)) as src, zipfile.ZipFile(buf, "w") as dst:
        for info in src.infolist():
            data = src.read(info)
            dst.writestr(info.filename, struct.pack("<IHH", 4_000_000_000, 7, 9).join([data[:4], data[12:]]) if info.filename.endswith(".dbf") else data)
    with pytest.raises(ShapefileError):
        _frame(buf.getvalue(), max_rows=100000)


# ---- through the API ----

@pytest.fixture()
def token(client, db_session):
    _setup_institution_user(db_session)
    return login(client, "inst_user").json()["access_token"]


def test_a_shapefile_zip_is_uploaded_stored_and_downloadable(client, token):
    content = build_shapefile_zip([ROW], [POINT])
    res = _upload(client, token, content, filename="loans.zip", content_type="application/zip")
    assert res.status_code == 201, res.text
    assert res.json()["status"] == "VALID" and res.json()["total_records"] == 1
    download = client.get(f"/api/submissions/{res.json()['id']}/download", headers=auth_header(token))
    assert download.status_code == 200 and download.content == content
    assert download.headers["content-type"].startswith("application/zip")


def test_a_refused_zip_is_an_invalid_submission_with_the_reason_and_leaves_no_file_behind(client, token):
    res = _upload(client, token, build_shapefile_zip([ROW], [POINT], extra_members={"run.exe": b"MZ"}), filename="loans.zip", content_type="application/zip")
    assert res.status_code == 201 and res.json()["status"] == "INVALID"
    assert "not part of a shapefile" in str(res.json())


def test_the_limit_for_loan_files_is_50_mb_and_for_climate_files_20_mb():
    from app.core.config import settings
    assert settings.MAX_UPLOAD_SIZE_MB == 50 and settings.MAX_CLIMATE_UPLOAD_SIZE_MB == 20


def test_a_file_over_the_limit_is_refused_with_413(client, token, monkeypatch):
    from app.api import submissions
    monkeypatch.setattr(submissions.settings, "MAX_UPLOAD_SIZE_MB", 0)
    res = _upload(client, token, build_shapefile_zip([ROW], [POINT]), filename="loans.zip", content_type="application/zip")
    assert res.status_code == 413
