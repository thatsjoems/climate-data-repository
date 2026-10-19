"""
The memory of the dashboard totals (app/services/analytics_service.py, _remembered).

What matters, in order: an answer is never older than the data (an approval, a rejection, a new loan in an approved submission all change it), one scope's
answer is never given to another (an institution's own figures against the whole sector), the second identical request really does skip the loans, and
with the memory switched off nothing is kept.

The suite switches the memory off for every other test (tests/conftest.py); here it is switched on for each test and emptied before and after.
"""
from contextlib import contextmanager

import pytest
from sqlalchemy import event

from app.core.config import settings
from app.models.models import SubmissionStatus
from app.services import analytics_service
from app.services.analytics_service import (
    clear_analytics_cache, get_combined_climate_financial_exposure, get_hazard_exposure, get_kpi_summary)
from tests.conftest import TEST_ENGINE, make_institution
from tests.test_rbac_and_isolation import _seed_submission_for


@pytest.fixture(autouse=True)
def memory_on():
    settings.ANALYTICS_CACHE_ENABLED = True
    clear_analytics_cache()
    yield
    clear_analytics_cache()
    settings.ANALYTICS_CACHE_ENABLED = False


@contextmanager
def loan_queries():
    """Collects every statement that reads the table of loans while the block runs."""
    seen: list[str] = []

    def before(conn, cursor, statement, parameters, context, executemany):
        if "FROM submission_records" in statement:
            seen.append(statement)

    event.listen(TEST_ENGINE, "before_cursor_execute", before)
    try:
        yield seen
    finally:
        event.remove(TEST_ENGINE, "before_cursor_execute", before)


def _total(db, institution_id=None, region="Dodoma"):
    rows = get_combined_climate_financial_exposure(db, institution_id)
    return sum(r["total_loan_exposure_tzs"] for r in rows if r["region"] == region)


def test_the_second_identical_request_does_not_read_the_loans(db_session):
    inst = make_institution(db_session)
    _seed_submission_for(db_session, inst)
    with loan_queries() as first:
        a = get_combined_climate_financial_exposure(db_session)
    with loan_queries() as second:
        b = get_combined_climate_financial_exposure(db_session)
    assert first, "the first request must read the loans"
    assert not second, "the second identical request must be answered from memory"
    assert a == b


def test_the_exposure_pages_share_one_remembered_answer(db_session):
    inst = make_institution(db_session)
    _seed_submission_for(db_session, inst)
    get_combined_climate_financial_exposure(db_session)
    with loan_queries() as seen:
        get_hazard_exposure(db_session)          # the same sums over the same loans: no second pass
    assert not seen


def test_a_newly_approved_submission_is_counted_at_once(db_session):
    inst_a = make_institution(db_session, code="BANK-A", name="Bank A")
    inst_b = make_institution(db_session, code="BANK-B", name="Bank B")
    _seed_submission_for(db_session, inst_a, amount=1_000_000.0)
    assert _total(db_session) == 1_000_000.0
    _seed_submission_for(db_session, inst_b, amount=2_000_000.0)       # another institution's approved file appears
    assert _total(db_session) == 3_000_000.0


def test_a_rejected_submission_leaves_the_figures_at_once(db_session):
    inst_a = make_institution(db_session, code="BANK-A", name="Bank A")
    inst_b = make_institution(db_session, code="BANK-B", name="Bank B")
    _seed_submission_for(db_session, inst_a, amount=1_000_000.0)
    sub_b = _seed_submission_for(db_session, inst_b, amount=2_000_000.0)
    assert _total(db_session) == 3_000_000.0
    sub_b.status = SubmissionStatus.REJECTED
    sub_b.is_current = False
    db_session.commit()
    assert _total(db_session) == 1_000_000.0


def test_a_loan_added_to_an_approved_submission_changes_the_answer(db_session):
    inst = make_institution(db_session)
    _seed_submission_for(db_session, inst, amount=1_000_000.0)
    assert _total(db_session) == 1_000_000.0
    _seed_submission_for(db_session, inst, amount=500_000.0)           # same submission, one more loan (its loan counts change)
    assert _total(db_session) == 1_500_000.0


def test_one_scopes_answer_is_never_given_to_another(db_session):
    inst_a = make_institution(db_session, code="BANK-A", name="Bank A")
    inst_b = make_institution(db_session, code="BANK-B", name="Bank B")
    _seed_submission_for(db_session, inst_a, amount=1_000_000.0)
    _seed_submission_for(db_session, inst_b, amount=2_000_000.0)
    # Whole sector first, so its answer is already remembered when an institution asks.
    assert _total(db_session, None) == 3_000_000.0
    assert _total(db_session, inst_a.id) == 1_000_000.0
    assert _total(db_session, inst_b.id) == 2_000_000.0
    # And the other way round: the institutions' answers are held now, the sector's must still be the sum.
    assert _total(db_session, None) == 3_000_000.0


def test_the_filters_are_part_of_what_is_remembered(db_session):
    inst = make_institution(db_session)
    _seed_submission_for(db_session, inst, region="Dodoma", amount=1_000_000.0)
    _seed_submission_for(db_session, inst, region="Arusha", amount=4_000_000.0)
    everything = get_combined_climate_financial_exposure(db_session)
    only_arusha = get_combined_climate_financial_exposure(db_session, filter_region="Arusha")
    assert {r["region"] for r in everything} == {"Dodoma", "Arusha"}
    assert {r["region"] for r in only_arusha} == {"Arusha"}


def test_the_summary_is_the_same_with_and_without_the_memory(db_session):
    inst_a = make_institution(db_session, code="BANK-A", name="Bank A")
    inst_b = make_institution(db_session, code="BANK-B", name="Bank B")
    _seed_submission_for(db_session, inst_a, amount=1_000_000.0)
    _seed_submission_for(db_session, inst_b, amount=2_000_000.0)
    remembered_first = get_kpi_summary(db_session)
    remembered_again = get_kpi_summary(db_session)
    settings.ANALYTICS_CACHE_ENABLED = False
    fresh = get_kpi_summary(db_session)
    assert remembered_first == remembered_again == fresh
    assert fresh["total_loan_exposure_tzs"] == 3_000_000.0


def test_an_institutions_summary_is_not_the_sectors(db_session):
    inst_a = make_institution(db_session, code="BANK-A", name="Bank A")
    inst_b = make_institution(db_session, code="BANK-B", name="Bank B")
    _seed_submission_for(db_session, inst_a, amount=1_000_000.0)
    _seed_submission_for(db_session, inst_b, amount=2_000_000.0)
    assert get_kpi_summary(db_session)["total_loan_exposure_tzs"] == 3_000_000.0
    assert get_kpi_summary(db_session, institution_id=inst_a.id)["total_loan_exposure_tzs"] == 1_000_000.0
    assert get_kpi_summary(db_session)["total_loan_exposure_tzs"] == 3_000_000.0


def test_the_summary_counts_of_submissions_stay_live(db_session):
    """Only the sums over the loans are remembered; the counts of submissions by status are always read afresh."""
    inst = make_institution(db_session)
    sub = _seed_submission_for(db_session, inst)
    assert get_kpi_summary(db_session)["approved_submissions"] == 1
    sub.status = SubmissionStatus.REJECTED
    sub.is_current = False
    db_session.commit()
    after = get_kpi_summary(db_session)
    assert after["approved_submissions"] == 0 and after["rejected_submissions"] == 1
    assert after["total_loan_exposure_tzs"] == 0.0


def test_switched_off_nothing_is_kept(db_session):
    inst = make_institution(db_session)
    _seed_submission_for(db_session, inst)
    settings.ANALYTICS_CACHE_ENABLED = False
    get_combined_climate_financial_exposure(db_session)
    with loan_queries() as seen:
        get_combined_climate_financial_exposure(db_session)
    assert seen, "with the memory off every request reads the loans"
    assert not analytics_service._cache


def test_the_memory_is_bounded(db_session):
    inst = make_institution(db_session)
    _seed_submission_for(db_session, inst)
    for i in range(analytics_service._CACHE_MAX_ENTRIES + 20):
        get_combined_climate_financial_exposure(db_session, filter_reporting_period=f"2030-Q{i}")
    assert len(analytics_service._cache) <= analytics_service._CACHE_MAX_ENTRIES
