"""
A reply that returns an ingestion batch lists the rejected rows and the reason for each.

Found when the first key delivery was tried by hand: the reply said 1 row was rejected and `errors` was an empty list.
The batch object has no `errors` relationship, so the field always fell back to its default. A sender (and an analyst)
could learn how many rows were rejected but never which, or why. The reasons were stored all along.
"""
import pytest

from app.models.models import RoleEnum
from tests.conftest import auth_header, login, make_user
from tests.test_climate_ingestion import _csv_bytes
from tests.test_integration_ingest import GOOD, _make_key, _send

BAD = "Nowhere,,2026,7,10,20,,,REC-{n}"


@pytest.fixture
def bot_token(client, db_session):
    make_user(db_session, role=RoleEnum.BOT_USER, username="bot_errors")
    return login(client, "bot_errors").json()["access_token"]


def _manual(client, token, rows):
    return client.post("/api/climate-data/ingest", data={"source": "MANUAL_TMA_FILE"},
                       files={"file": ("manual.csv", _csv_bytes(rows), "text/csv")}, headers=auth_header(token))


def test_a_delivery_reply_lists_each_rejected_row_with_its_reason(client, bot_token):
    key = _make_key(client, bot_token, "INGEST_TMA")["api_key"]
    body = _send(client, key, rows=GOOD + [BAD.format(n=3)]).json()
    assert body["records_accepted"] == 2 and body["records_rejected"] == 1 and body["errors_total"] == 1
    assert len(body["errors"]) == 1 and body["errors"][0]["error_description"] and body["errors"][0]["row_number"] is not None


def test_a_manual_upload_reply_does_the_same(client, bot_token):
    body = _manual(client, bot_token, GOOD + [BAD.format(n=3)]).json()
    assert body["records_rejected"] == 1 and body["errors_total"] == 1 and len(body["errors"]) == 1


def test_a_clean_file_has_no_errors(client, bot_token):
    body = _manual(client, bot_token, GOOD).json()
    assert body["errors"] == [] and body["errors_total"] == 0


def test_the_detail_endpoint_pages_through_the_rejected_rows(client, bot_token):
    batch = _manual(client, bot_token, GOOD + [BAD.format(n=i) for i in range(3, 6)]).json()
    full = client.get(f"/api/climate-data/ingestions/{batch['id']}", headers=auth_header(bot_token)).json()
    assert full["errors_total"] == 3 and len(full["errors"]) == 3
    rows = [e["row_number"] for e in full["errors"]]
    assert rows == sorted(rows)
    second = client.get(f"/api/climate-data/ingestions/{batch['id']}?error_offset=1&error_limit=1", headers=auth_header(bot_token)).json()
    assert second["errors_total"] == 3 and second["errors"] == [full["errors"][1]]


def test_the_reply_lists_at_most_500_rows_and_says_how_many_there_are(client, bot_token):
    body = _manual(client, bot_token, [BAD.format(n=i) for i in range(600)]).json()
    assert body["records_rejected"] == 600 and body["errors_total"] == 600 and len(body["errors"]) == 500


@pytest.mark.parametrize("query", ["error_limit=0", "error_limit=2001", "error_offset=-1"])
def test_unreasonable_error_paging_is_refused(client, bot_token, query):
    batch = _manual(client, bot_token, GOOD).json()
    assert client.get(f"/api/climate-data/ingestions/{batch['id']}?{query}", headers=auth_header(bot_token)).status_code == 422
