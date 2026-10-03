from app.models.models import RoleEnum, Submission, SubmissionRecord, SubmissionStatus
from app.services.analytics_service import get_hazard_exposure
from tests.conftest import make_institution, make_user


def _seed_status_submission(db, institution, status, loan_id, amount, period="2026-Q1"):
    user = make_user(db, role=RoleEnum.INSTITUTION_USER, institution=institution, username=f"user_{loan_id}")
    sub = Submission(
        institution_id=institution.id, submitted_by_user_id=user.id,
        file_name="test.xlsx", file_path="uploads/test.xlsx",
        reporting_period=period, status=status,
        total_records=1, valid_records=1, invalid_records=0,
        # Matches the real upload endpoint's rule (BR-06 in the SRS): only a
        # VALID or APPROVED submission is ever current. Built directly here
        # rather than through the API, so this has to be set explicitly -
        # is_current defaults to False on the model, and this test exists
        # specifically to prove PENDING/INVALID stay out of analytics, so a
        # wrong default here would have hidden that rather than exposed it.
        is_current=status in (SubmissionStatus.VALID, SubmissionStatus.APPROVED),
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


def test_only_approved_submissions_enter_exposure_analytics(db_session):
    """
    Design decision confirmed here: a submission's figures are never
    aggregated, charted, or reported on until a BOT Analyst approves it -
    PENDING, INVALID and even VALID (validation-passed but not yet reviewed)
    submissions must all stay out of exposure analytics; only APPROVED
    contributes.

    Each status is seeded for its OWN reporting period: VALID and APPROVED
    are both eligible to be `is_current` (BR-06), and the database allows at
    most one current submission per institution+period, so a real
    institution could never have a current VALID and a current APPROVED
    submission for the SAME period at once - this test does not try to force
    that impossible state, it simply confirms the aggregate result across an
    institution's several periods correctly includes only the approved one.
    """
    inst = make_institution(db_session, code="BANK-X", name="Bank X")
    _seed_status_submission(db_session, inst, SubmissionStatus.PENDING, "PENDING-1", 2_000_000.0, period="2026-Q1")
    _seed_status_submission(db_session, inst, SubmissionStatus.INVALID, "INVALID-1", 3_000_000.0, period="2026-Q2")
    _seed_status_submission(db_session, inst, SubmissionStatus.VALID, "VALID-1", 1_000_000.0, period="2026-Q3")
    _seed_status_submission(db_session, inst, SubmissionStatus.APPROVED, "APPROVED-1", 5_000_000.0, period="2026-Q4")

    rows = get_hazard_exposure(db_session)
    assert sum(r["exposed_loan_amount_tzs"] for r in rows) == 5_000_000.0
