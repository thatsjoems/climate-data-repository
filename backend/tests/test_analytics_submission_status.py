from app.models.models import RoleEnum, Submission, SubmissionRecord, SubmissionStatus
from app.services.analytics_service import get_hazard_exposure
from tests.conftest import make_institution, make_user


def _seed_status_submission(db, institution, status, loan_id, amount):
    user = make_user(db, role=RoleEnum.INSTITUTION_USER, institution=institution, username=f"user_{loan_id}")
    sub = Submission(
        institution_id=institution.id, submitted_by_user_id=user.id,
        file_name="test.xlsx", file_path="uploads/test.xlsx",
        reporting_period="2026-Q1", status=status,
        total_records=1, valid_records=1, invalid_records=0,
    )
    db.add(sub)
    db.flush()
    db.add(SubmissionRecord(
        submission_id=sub.id, row_number=2, loan_id=loan_id,
        customer_id=f"C-{loan_id}", loan_amount_tzs=amount,
        collateral_value_tzs=amount, region="Dodoma", district="Chamwino",
        is_valid=True,
    ))
    db.commit()


def test_pending_and_invalid_submissions_do_not_enter_exposure_analytics(db_session):
    inst = make_institution(db_session, code="BANK-X", name="Bank X")
    _seed_status_submission(db_session, inst, SubmissionStatus.PENDING, "PENDING-1", 2_000_000.0)
    _seed_status_submission(db_session, inst, SubmissionStatus.INVALID, "INVALID-1", 3_000_000.0)
    _seed_status_submission(db_session, inst, SubmissionStatus.VALID, "VALID-1", 1_000_000.0)

    rows = get_hazard_exposure(db_session)
    assert sum(r["exposed_loan_amount_tzs"] for r in rows) == 1_000_000.0
