"""
Submission details are paged (rows and findings).

Found when "View Details" froze the browser ("Page unresponsive - Exit page / Wait") on a large
file: the endpoint returned every row and every finding and the page drew them all at once
(a 15,000-row file is about 165,000 table cells). The server now sends one page of each, in a
stable order, with the full totals, and the pages together are exactly the whole submission.
"""
from app.models.models import RoleEnum, SubmissionRecord, ValidationError
from tests.conftest import auth_header, login, make_institution, make_user
from tests.test_rbac_and_isolation import _seed_submission_for

ROWS, FINDINGS = 250, 130


def _big_submission(db):
    inst = make_institution(db)
    sub = _seed_submission_for(db, inst)            # already holds row 2
    for n in range(3, ROWS + 2):
        db.add(SubmissionRecord(submission_id=sub.id, row_number=n, loan_id=f"BIG-{n}", borrower_name="B",
                                loan_amount_tzs=1.0, collateral_value_tzs=1.0, region="Dodoma", district="Chamwino", is_valid=True))
    for n in range(FINDINGS):
        db.add(ValidationError(submission_id=sub.id, row_number=n + 2, column_name="loan_id", error_description=f"finding {n}", severity="ERROR"))
    db.commit()
    make_user(db, role=RoleEnum.BOT_USER, username="bot_page")
    make_user(db, role=RoleEnum.INSTITUTION_USER, institution=inst, username="owner_page")
    return inst, sub


def _get(client, username, sub_id, query=""):
    token = login(client, username).json()["access_token"]
    return client.get(f"/api/submissions/{sub_id}{query}", headers=auth_header(token))


def test_the_default_response_is_one_page_with_the_full_totals(client, db_session):
    _, sub = _big_submission(db_session)
    body = _get(client, "bot_page", sub.id).json()
    assert body["records_total"] == ROWS and body["errors_total"] == FINDINGS
    assert len(body["records"]) == 100 and len(body["errors"]) == 100


def test_pages_are_ordered_and_together_are_the_whole_submission(client, db_session):
    _, sub = _big_submission(db_session)
    seen = []
    for offset in (0, 100, 200):
        page = _get(client, "bot_page", sub.id, f"?record_offset={offset}&record_limit=100").json()["records"]
        seen += [r["row_number"] for r in page]
    assert seen == sorted(seen) and len(seen) == len(set(seen)) == ROWS


def test_findings_are_paged_independently_of_rows(client, db_session):
    _, sub = _big_submission(db_session)
    body = _get(client, "bot_page", sub.id, "?error_offset=100&error_limit=100&record_limit=10").json()
    assert len(body["errors"]) == FINDINGS - 100 and len(body["records"]) == 10


def test_a_page_beyond_the_end_is_empty_not_an_error(client, db_session):
    _, sub = _big_submission(db_session)
    body = _get(client, "bot_page", sub.id, "?record_offset=100000").json()
    assert body["records"] == [] and body["records_total"] == ROWS


def test_unreasonable_page_parameters_are_refused(client, db_session):
    _, sub = _big_submission(db_session)
    for q in ("?record_limit=501", "?record_limit=0", "?record_offset=-1", "?error_limit=100000"):
        assert _get(client, "bot_page", sub.id, q).status_code == 422, q


def test_the_owning_institution_can_page_and_another_cannot(client, db_session):
    inst, sub = _big_submission(db_session)
    assert _get(client, "owner_page", sub.id, "?record_limit=5").status_code == 200
    other = make_institution(db_session, code="OTHER", name="Other Bank")
    make_user(db_session, role=RoleEnum.INSTITUTION_USER, institution=other, username="other_page")
    assert _get(client, "other_page", sub.id, "?record_limit=5").status_code == 403
