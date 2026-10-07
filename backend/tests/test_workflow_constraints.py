"""
Three workflow rules are enforced by the database as well as by the application (migration b5d8a3c6e102):
  - only a VALID or APPROVED submission can be the current one,
  - the reviewer is never the person who uploaded the submission (maker-checker, BR-03),
  - an institution user always belongs to an institution (tenant isolation, BR-15).
These tests check the conditions themselves on the test suite's database (built from models.py);
scripts/verify_db_constraints.py checks that the REAL database has them.
"""
import pytest
from sqlalchemy.exc import IntegrityError

from app.models.models import RoleEnum, Submission, SubmissionStatus, User
from tests.conftest import hash_password, make_institution, make_user


def _submission(db, inst, submitter, period="2026-Q1", status=SubmissionStatus.VALID, **kw):
    sub = Submission(institution_id=inst.id, submitted_by_user_id=submitter.id, file_name="t.xlsx", file_path="uploads/t.xlsx",
                     reporting_period=period, status=status, total_records=1, valid_records=1, invalid_records=0, **kw)
    db.add(sub)
    return sub


def test_an_institution_user_without_an_institution_is_rejected(db_session):
    db_session.add(User(full_name="No Bank", username="nobank", email="nobank@example.com", hashed_password=hash_password("x"),
                        role=RoleEnum.INSTITUTION_USER, institution_id=None))
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_an_institution_user_with_an_institution_is_accepted(db_session):
    inst = make_institution(db_session)
    assert make_user(db_session, role=RoleEnum.INSTITUTION_USER, institution=inst, username="withbank").id


def test_staff_without_an_institution_are_accepted(db_session):
    assert make_user(db_session, role=RoleEnum.BOT_USER, username="staff1").id
    assert make_user(db_session, role=RoleEnum.SYSTEM_ADMIN, username="staff2").id


def test_staff_with_an_institution_are_still_accepted_because_the_reverse_rule_is_deliberately_not_enforced(db_session):
    """The demonstration seed attaches the administrator and the BOT analyst to the BOT institution record."""
    inst = make_institution(db_session)
    assert make_user(db_session, role=RoleEnum.BOT_USER, institution=inst, username="seeded_staff").id


@pytest.mark.parametrize("status", [SubmissionStatus.REJECTED, SubmissionStatus.SUPERSEDED, SubmissionStatus.INVALID])
def test_a_submission_that_is_not_valid_or_approved_cannot_be_current(db_session, status):
    inst = make_institution(db_session)
    submitter = make_user(db_session, role=RoleEnum.INSTITUTION_USER, institution=inst, username="up1")
    _submission(db_session, inst, submitter, status=status, is_current=True)
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_valid_and_approved_submissions_can_be_current(db_session):
    inst = make_institution(db_session)
    submitter = make_user(db_session, role=RoleEnum.INSTITUTION_USER, institution=inst, username="up2")
    _submission(db_session, inst, submitter, period="2026-Q1", status=SubmissionStatus.VALID, is_current=True)
    _submission(db_session, inst, submitter, period="2026-Q2", status=SubmissionStatus.APPROVED, is_current=True)
    db_session.commit()  # must not raise


def test_a_non_current_submission_may_have_any_status(db_session):
    inst = make_institution(db_session)
    submitter = make_user(db_session, role=RoleEnum.INSTITUTION_USER, institution=inst, username="up3")
    _submission(db_session, inst, submitter, status=SubmissionStatus.REJECTED, is_current=False)
    db_session.commit()  # must not raise


def test_the_reviewer_cannot_be_the_person_who_uploaded(db_session):
    inst = make_institution(db_session)
    submitter = make_user(db_session, role=RoleEnum.INSTITUTION_USER, institution=inst, username="up4")
    _submission(db_session, inst, submitter, status=SubmissionStatus.APPROVED, reviewed_by_user_id=submitter.id)
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_a_different_reviewer_is_accepted(db_session):
    inst = make_institution(db_session)
    submitter = make_user(db_session, role=RoleEnum.INSTITUTION_USER, institution=inst, username="up5")
    reviewer = make_user(db_session, role=RoleEnum.BOT_USER, username="rev5")
    _submission(db_session, inst, submitter, status=SubmissionStatus.APPROVED, reviewed_by_user_id=reviewer.id)
    db_session.commit()  # must not raise
