"""
The audit action of a review decision is spelled out in full (KG-04).

It used to be built as "SUBMISSION_" + the decision + "D", which gave SUBMISSION_APPROVED for an approval but SUBMISSION_REJECTD
(sic) for a rejection. The audit log is append-only, so entries written before this fix keep the old spelling; every new one is correct.
"""
import pytest

from app.models.models import AuditLog, RoleEnum
from tests.conftest import auth_header, login, make_user
from tests.test_upload_and_workflow import VALID_ROW, _setup_institution_user, _upload


@pytest.mark.parametrize("decision, action", [("APPROVE", "SUBMISSION_APPROVED"), ("REJECT", "SUBMISSION_REJECTED")])
def test_a_review_decision_is_audited_under_its_correct_name(client, db_session, decision, action):
    _setup_institution_user(db_session)
    submission_id = _upload(client, login(client, "inst_user").json()["access_token"], [VALID_ROW]).json()["id"]
    make_user(db_session, role=RoleEnum.BOT_USER, username="reviewer_audit")
    token = login(client, "reviewer_audit").json()["access_token"]
    assert client.post(f"/api/submissions/{submission_id}/review", json={"decision": decision}, headers=auth_header(token)).status_code == 200
    actions = {a.action for a in db_session.query(AuditLog).filter(AuditLog.action.like("SUBMISSION_%")).all()}
    assert action in actions and "SUBMISSION_REJECTD" not in actions
