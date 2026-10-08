"""
How dates in an uploaded file are read (app/services/date_rules.py), the KG-06 decision.

Text dates were read month-first without saying so (04/05/2026 became 5 April when the writer meant 4 May), and a NUMBER in a date column became a date of 1970.
Nothing showed the data was wrong. Now a date is accepted only when it can mean one thing, and a doubtful one is refused with the reason and the way to write it.
"""
from datetime import date, datetime

import numpy as np
import pandas as pd
import pytest

from app.models.models import SubmissionRecord
from app.services.date_rules import AMBIGUOUS, EMPTY, INVALID, OK, date_problem_hint, read_date
from tests.conftest import auth_header, login
from tests.test_upload_and_workflow import VALID_ROW, _setup_institution_user, _upload


@pytest.mark.parametrize("value,expected", [
    (datetime(2026, 3, 15, 10, 30), date(2026, 3, 15)), (pd.Timestamp("2026-03-15"), date(2026, 3, 15)), (date(2026, 3, 15), date(2026, 3, 15)),
    ("2026-03-15", date(2026, 3, 15)), ("2026/03/15", date(2026, 3, 15)), ("2026.3.5", date(2026, 3, 5)), ("2026-03-15 00:00:00", date(2026, 3, 15)),
    ("20260315", date(2026, 3, 15)), (" 2026-03-15 ", date(2026, 3, 15)),
    ("25/03/2026", date(2026, 3, 25)), ("25-03-2026", date(2026, 3, 25)), ("03/25/2026", date(2026, 3, 25)), ("03/03/2026", date(2026, 3, 3)), ("12/12/2026", date(2026, 12, 12)),
    ("4 March 2026", date(2026, 3, 4)), ("March 4, 2026", date(2026, 3, 4)), ("04-Mar-2026", date(2026, 3, 4)),
])
def test_a_date_that_can_mean_only_one_thing_is_accepted(value, expected):
    assert read_date(value) == (expected, OK)


@pytest.mark.parametrize("text", ["04/05/2026", "01.02.2026", "1-2-2026", "12/11/2026"])
def test_a_date_that_can_mean_two_things_is_refused_not_guessed(text):
    assert read_date(text) == (None, AMBIGUOUS)


@pytest.mark.parametrize("value", [
    45000, 20250101, 2026.0, np.int64(45000), np.float64(45000.5), True,                  # numbers and flags are not dates, whatever they look like
    "04/05/26", "March 4", "soon", "2026-02-30", "31/04/2026", "2026-13-01",              # two-digit year, no year, words, days that do not exist
    datetime(1899, 12, 30), "3026-01-01", "1850-05-05",                                    # years that cannot be a loan date
])
def test_anything_else_is_refused(value):
    assert read_date(value) == (None, INVALID)


@pytest.mark.parametrize("value", [None, "", "   ", "nan", float("nan"), pd.NaT])
def test_an_empty_cell_is_empty_not_wrong(value):
    assert read_date(value) == (None, EMPTY)


def test_the_hint_names_both_readings_and_the_way_to_write_it():
    hint = date_problem_hint("04/05/2026")
    assert "4 May 2026" in hint and "5 April 2026" in hint and "YYYY-MM-DD" in hint and "2026-05-04" in hint and "2026-04-05" in hint


def test_the_hint_for_a_number_says_it_is_a_number():
    assert "a number (45000)" in date_problem_hint(45000) and "date cell" in date_problem_hint(45000)


def test_there_is_no_hint_for_a_date_that_is_fine_or_absent():
    assert date_problem_hint("2026-03-15") == "" and date_problem_hint(None) == ""


# ------------------------------------------------------------------ through the application
def _rows(*pairs):
    return [dict(VALID_ROW, loan_id=f"LN-{i}", customer_id=f"C-{i}", disbursement_date=d, maturity_date=m) for i, (d, m) in enumerate(pairs)]


def test_an_upload_keeps_the_good_dates_and_refuses_the_doubtful_ones_with_the_reason(client, db_session):
    _setup_institution_user(db_session)
    token = login(client, "inst_user").json()["access_token"]
    body = _upload(client, token, _rows(
        ("2026-01-15", "2029-01-15"),                 # fine
        ("04/05/2026", "2029-05-04"),                 # ambiguous: refused
        (datetime(2026, 2, 1), "25/03/2029"),         # a date cell and a day-first date that cannot be anything else: fine
        (45000, "2029-01-01"),                        # a number: refused
    )).json()
    assert body["total_records"] == 4 and body["valid_records"] == 2 and body["invalid_records"] == 2

    detail = client.get(f"/api/submissions/{body['id']}", headers=auth_header(token)).json()
    findings = [e["error_description"] for e in detail["errors"] if e["column_name"] == "disbursement_date"]
    assert any("could be 4 May 2026 or 5 April 2026" in m for m in findings)
    assert any("a number (45000)" in m for m in findings)

    stored = db_session.query(SubmissionRecord).filter_by(submission_id=body["id"]).order_by(SubmissionRecord.row_number).all()
    assert [r.disbursement_date_value for r in stored] == [date(2026, 1, 15), None, date(2026, 2, 1), None]       # a refused date is never stored
    assert stored[2].maturity_date_value == date(2029, 3, 25)                                                         # 25/03/2029 read day first, the only possible reading
    assert [r.is_valid for r in stored] == [True, False, True, False]


def test_the_rule_that_maturity_cannot_precede_disbursement_still_applies(client, db_session):
    _setup_institution_user(db_session)
    token = login(client, "inst_user").json()["access_token"]
    body = _upload(client, token, _rows(("2027-06-01", "2026-06-01"))).json()
    detail = client.get(f"/api/submissions/{body['id']}", headers=auth_header(token)).json()
    assert body["invalid_records"] == 1 and any("earlier than disbursement" in e["error_description"] for e in detail["errors"])
