"""Export Dashboard: the image and PDF exports carry the dashboard's loan and collateral charts."""
import io

import pytest
from PIL import Image

from app.models.models import RoleEnum
from app.services import report_service
from tests.conftest import auth_header, login, make_institution, make_user
from tests.test_rbac_and_isolation import _seed_submission_for


def _bot_token(client, db):
    make_user(db, role=RoleEnum.BOT_USER, username="bot1")
    return login(client, "bot1").json()["access_token"]


@pytest.mark.parametrize("value,expected", [
    (55_660_000_000_000, "55.66 T"), (8_420_000_000, "8.42 B"), (2_500_000, "2.50 M"), (1_500, "1.5 K"), (12, "12"),
])
def test_compact_matches_the_dashboard(value, expected):
    assert report_service._compact(value) == expected


def test_image_export_without_data_still_builds_with_empty_panels(client, db_session):
    token = _bot_token(client, db_session)
    res = client.get("/api/reports/summary.png", headers=auth_header(token))
    assert res.status_code == 200
    img = Image.open(io.BytesIO(res.content))
    assert img.size[0] == 1200 and img.size[1] > 900


def test_image_export_with_data_is_taller_than_the_old_hazard_only_image(client, db_session):
    a = make_institution(db_session, code="BANK-A", name="Bank A Ltd")
    b = make_institution(db_session, code="BANK-B", name="Bank B Ltd")
    _seed_submission_for(db_session, a, region="Dodoma", amount=1_000_000.0)
    _seed_submission_for(db_session, b, region="Mwanza", district="Nyamagana", amount=3_000_000.0)
    token = _bot_token(client, db_session)
    res = client.get("/api/reports/summary.png", headers=auth_header(token))
    assert res.status_code == 200
    img = Image.open(io.BytesIO(res.content))
    # Header + KPI + hazard chart alone were under ~560 px; the eight chart panels add four rows of panels.
    assert img.size[1] > 900
    # The image honours the dashboard filters (same query parameters as the screen).
    filtered = client.get("/api/reports/summary.png?filter_region=Dodoma", headers=auth_header(token))
    assert filtered.status_code == 200


def test_pdf_export_with_data_builds(client, db_session):
    a = make_institution(db_session, code="BANK-A", name="Bank A Ltd")
    _seed_submission_for(db_session, a, region="Dodoma", amount=1_000_000.0)
    token = _bot_token(client, db_session)
    res = client.get("/api/reports/summary.pdf", headers=auth_header(token))
    assert res.status_code == 200 and res.content.startswith(b"%PDF")


def test_bar_drawing_handles_no_rows_and_long_labels():
    assert report_service._bar_drawing([]).height > 0
    d = report_service._bar_drawing([("x" * 80, 5.0, 100.0)])
    assert d.width > 0
