"""
Uploads store the loans and the findings in blocks with bulk INSERTs (app/api/submissions.py, STORE_BLOCK).

A load test showed one ORM object per loan, 100,000 of them in the session at once, was the slowest and the most memory-hungry step of an upload.
The risk of storing in blocks is a mistake at a block boundary (a loan stored twice or lost, a finding dropped). These tests upload a file that is
partly invalid with block sizes chosen to land on and around every boundary, including a block of 1, and compare what is stored with what was sent.
"""
import logging

import pytest

from app.api import submissions as submissions_api
from app.models.models import SubmissionRecord, ValidationError as VError
from tests.conftest import auth_header, login
from tests.test_upload_and_workflow import VALID_ROW, _setup_institution_user, _upload

LOANS = 23


def _rows():
    rows = [dict(VALID_ROW, loan_id=f"LN-{i}", customer_id=f"C-{i}") for i in range(LOANS)]
    rows[5]["region"] = "Atlantis"                    # an unknown region
    rows[11]["loan_amount_tzs"] = -1                  # a negative amount
    rows[13]["loan_id"] = rows[12]["loan_id"]         # a loan number repeated within the file
    return rows


@pytest.mark.parametrize("block", [1, 4, 7, 22, 23, 24, 5000])
def test_every_loan_and_finding_is_stored_once_whatever_the_block_size(client, db_session, monkeypatch, block):
    monkeypatch.setattr(submissions_api, "STORE_BLOCK", block)
    _setup_institution_user(db_session)
    token = login(client, "inst_user").json()["access_token"]
    res = _upload(client, token, _rows())
    assert res.status_code == 201
    body = res.json()
    assert body["total_records"] == LOANS and body["valid_records"] == LOANS - 3 and body["invalid_records"] == 3 and body["status"] == "INVALID"

    stored = db_session.query(SubmissionRecord).filter_by(submission_id=body["id"]).order_by(SubmissionRecord.row_number).all()
    assert len(stored) == LOANS and len({r.id for r in stored}) == LOANS                  # each loan once, each with its own generated id
    assert len({r.row_number for r in stored}) == LOANS
    assert [r.loan_id for r in stored if not r.is_valid] == ["LN-5", "LN-11", "LN-12"]     # the three bad rows, and no others

    findings = db_session.query(VError).filter_by(submission_id=body["id"]).count()
    assert findings >= 3
    detail = client.get(f"/api/submissions/{body['id']}", headers=auth_header(token)).json()
    assert detail["errors_total"] == findings and detail["records_total"] == LOANS


def test_a_clean_file_stores_every_loan_and_no_finding_across_blocks(client, db_session, monkeypatch):
    monkeypatch.setattr(submissions_api, "STORE_BLOCK", 10)
    _setup_institution_user(db_session)
    token = login(client, "inst_user").json()["access_token"]
    rows = [dict(VALID_ROW, loan_id=f"LN-{i}", customer_id=f"C-{i}") for i in range(35)]
    body = _upload(client, token, rows).json()
    assert body["status"] == "VALID" and body["valid_records"] == 35
    assert db_session.query(SubmissionRecord).filter_by(submission_id=body["id"]).count() == 35
    assert db_session.query(VError).filter_by(submission_id=body["id"]).count() == 0


def test_the_stages_of_an_upload_are_logged_without_any_loan_data(client, db_session):
    seen = []

    class Catch(logging.Handler):
        def emit(self, record):
            seen.append(record.getMessage())

    logger, handler, level = logging.getLogger("cdr.upload"), Catch(), logging.getLogger("cdr.upload").level
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    try:
        _setup_institution_user(db_session)
        token = login(client, "inst_user").json()["access_token"]
        assert _upload(client, token, [dict(VALID_ROW, loan_id=f"LN-{i}", customer_id=f"C-{i}") for i in range(3)]).status_code == 201
    finally:
        logger.removeHandler(handler)
        logger.setLevel(level)
    stage = [m for m in seen if m.startswith("upload stored:")]
    assert len(stage) == 1 and "rows=3 " in stage[0] and all(k in stage[0] for k in ("validate_s=", "store_s=", "commit_s=", "total_s=", "process_peak_mb="))
    assert not any("LN-" in m or "C-" in m or "Residential" in m for m in seen)           # a count and times, never the data


# ---------------------------------------------------------------------------------------------------------------------
# The answers to an upload and to a review carry ONE PAGE of rows and findings, not all of them (found by a load test: for a file of 100,000
# loans the application loaded every loan to write the answer: about a gigabyte, ten seconds, and an answer far too large for a browser).
def test_the_answer_to_an_upload_is_one_page_with_the_totals(client, db_session):
    _setup_institution_user(db_session)
    token = login(client, "inst_user").json()["access_token"]
    rows = [dict(VALID_ROW, loan_id=f"LN-{i}", customer_id=f"C-{i}", region="Atlantis") for i in range(130)]       # every row has a finding
    body = _upload(client, token, rows).json()
    assert body["total_records"] == 130 and body["records_total"] == 130 and len(body["records"]) == 100
    assert body["errors_total"] >= 130 and len(body["errors"]) == 100
    assert [r["row_number"] for r in body["records"]] == sorted(r["row_number"] for r in body["records"])           # in row order, the first page


def test_a_small_upload_still_answers_with_all_its_rows_and_findings(client, db_session):
    _setup_institution_user(db_session)
    token = login(client, "inst_user").json()["access_token"]
    body = _upload(client, token, [dict(VALID_ROW, loan_id=f"LN-{i}", customer_id=f"C-{i}") for i in range(5)]).json()
    assert len(body["records"]) == 5 and body["records_total"] == 5 and body["errors"] == [] and body["errors_total"] == 0


def test_the_answer_to_a_review_is_one_page_too(client, db_session):
    from app.models.models import RoleEnum
    from tests.conftest import make_user
    _setup_institution_user(db_session)
    token = login(client, "inst_user").json()["access_token"]
    submission = _upload(client, token, [dict(VALID_ROW, loan_id=f"LN-{i}", customer_id=f"C-{i}") for i in range(120)]).json()
    make_user(db_session, role=RoleEnum.BOT_USER, username="reviewer_page")
    reviewer = login(client, "reviewer_page").json()["access_token"]
    res = client.post(f"/api/submissions/{submission['id']}/review", json={"decision": "APPROVE"}, headers=auth_header(reviewer))
    body = res.json()
    assert res.status_code == 200 and body["status"] == "APPROVED"
    assert body["records_total"] == 120 and len(body["records"]) == 100
