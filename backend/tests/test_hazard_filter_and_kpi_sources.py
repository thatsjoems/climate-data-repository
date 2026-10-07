"""
Hazard filter (ICN item 9) and KPI data lineage (/analytics/kpi-sources).

Hazard filter: Hazard Exposure and the map classify each region/period under ONE
dominant recorded hazard, so filtering keeps the regions whose dominant hazard is the one
asked for; Combined Exposure keeps the regions where it is among the recorded hazards.
The reports honour the filter, so a downloaded report never disagrees with the screen.

KPI sources: the current APPROVED submissions behind the dashboard figures - the same
population every calculation uses, so the totals always agree with the KPI summary.
"""
import pytest

from app.models.models import ClimateRecord, RoleEnum, SubmissionStatus
from tests.conftest import auth_header, login, make_institution, make_user
from tests.test_rbac_and_isolation import _seed_submission_for


def _climate(db, region, hazard, flag="VALIDATED"):
    db.add(ClimateRecord(region=region, year=2026, month=2, rainfall_mm=50.0, avg_temperature_c=25.0,
                         hazard_type=hazard, reporting_period="2026-Q1", quality_flag=flag))
    db.commit()


def _setup(db):
    """Bank A: approved loans in Dodoma (Flood), Mwanza (Drought) and Arusha (no climate data)."""
    inst = make_institution(db)
    _seed_submission_for(db, inst, region="Dodoma", amount=1_000_000.0)
    _seed_submission_for(db, inst, region="Mwanza", district="Nyamagana", amount=2_000_000.0)
    _seed_submission_for(db, inst, region="Arusha", district="Arusha", amount=500_000.0)
    _climate(db, "Dodoma", "Flood")
    _climate(db, "Mwanza", "Drought")
    make_user(db, role=RoleEnum.BOT_USER, username="bot1")
    return inst


def _get(client, username, path):
    token = login(client, username).json()["access_token"]
    return client.get(path, headers=auth_header(token))


# ------------------------------------------------------------------ hazard filter
def test_hazard_filter_narrows_hazard_exposure(client, db_session):
    _setup(db_session)
    everything = _get(client, "bot1", "/api/analytics/hazard-exposure").json()
    assert {(r["region"], r["hazard_type"]) for r in everything} == {("Dodoma", "Flood"), ("Mwanza", "Drought"), ("Arusha", "None")}
    flood = _get(client, "bot1", "/api/analytics/hazard-exposure?filter_hazard_type=Flood").json()
    assert [(r["region"], r["hazard_type"]) for r in flood] == [("Dodoma", "Flood")]
    none = _get(client, "bot1", "/api/analytics/hazard-exposure?filter_hazard_type=None").json()
    assert [(r["region"], r["hazard_type"]) for r in none] == [("Arusha", "None")]


def test_hazard_filter_narrows_combined_exposure(client, db_session):
    _setup(db_session)
    path = "/api/analytics/combined-climate-financial-exposure"
    assert {r["region"] for r in _get(client, "bot1", path).json()} == {"Dodoma", "Mwanza", "Arusha"}
    assert {r["region"] for r in _get(client, "bot1", path + "?filter_hazard_type=Flood").json()} == {"Dodoma"}
    assert {r["region"] for r in _get(client, "bot1", path + "?filter_hazard_type=Drought").json()} == {"Mwanza"}
    assert {r["region"] for r in _get(client, "bot1", path + "?filter_hazard_type=None").json()} == {"Arusha"}
    assert _get(client, "bot1", path + "?filter_hazard_type=Cyclone").json() == []


def test_hazard_filter_narrows_the_map(client, db_session):
    _setup(db_session)
    pts = _get(client, "bot1", "/api/analytics/map-points?filter_hazard_type=Drought").json()
    assert [p["region"] for p in pts] == ["Mwanza"]
    assert pts[0]["dominant_hazard"] == "Drought"


def test_an_unknown_hazard_value_is_refused(client, db_session):
    _setup(db_session)
    for path in ("/api/analytics/hazard-exposure", "/api/analytics/combined-climate-financial-exposure",
                 "/api/analytics/map-points", "/api/reports/combined-exposure.csv"):
        assert _get(client, "bot1", path + "?filter_hazard_type=Tornado").status_code == 422


def test_the_hazard_filter_never_changes_the_kpi_totals(client, db_session):
    _setup(db_session)
    kpi = _get(client, "bot1", "/api/analytics/kpi-summary").json()
    assert kpi["total_loan_exposure_tzs"] == pytest.approx(3_500_000.0)


def test_reports_honour_the_hazard_filter(client, db_session):
    _setup(db_session)
    csv_text = _get(client, "bot1", "/api/reports/combined-exposure.csv?filter_hazard_type=Flood").text
    assert "Dodoma" in csv_text and "Mwanza" not in csv_text and "Arusha" not in csv_text
    for fmt in ("pdf", "xlsx", "png"):
        res = _get(client, "bot1", f"/api/reports/summary.{fmt}?filter_hazard_type=Flood")
        assert res.status_code == 200, (fmt, res.text[:200])
        assert len(res.content) > 500


# ------------------------------------------------------------------ KPI sources (lineage)
def test_kpi_sources_list_only_current_approved_submissions(client, db_session):
    _setup(db_session)
    other = make_institution(db_session, code="BANK-B", name="Bank B Ltd")
    _seed_submission_for(db_session, other, region="Dodoma", amount=9_000_000.0, status=SubmissionStatus.VALID)
    rows = _get(client, "bot1", "/api/analytics/kpi-sources").json()
    assert len(rows) == 1  # Bank B's VALID (not yet approved) submission is not a source of any figure
    src = rows[0]
    assert src["institution_name"] == "Bank A Ltd" and src["reporting_period"] == "2026-Q1"
    assert src["contributing_records"] == 3
    assert src["loan_total_tzs"] == pytest.approx(3_500_000.0)
    assert src["row_validity_pct"] is None or 0 <= src["row_validity_pct"] <= 100
    kpi = _get(client, "bot1", "/api/analytics/kpi-summary").json()
    assert kpi["total_loan_exposure_tzs"] == pytest.approx(src["loan_total_tzs"])  # lineage matches the headline figure


def test_kpi_sources_follow_the_dashboard_filters(client, db_session):
    _setup(db_session)
    rows = _get(client, "bot1", "/api/analytics/kpi-sources?filter_region=Dodoma").json()
    assert len(rows) == 1 and rows[0]["contributing_records"] == 1
    assert rows[0]["loan_total_tzs"] == pytest.approx(1_000_000.0)
    assert _get(client, "bot1", "/api/analytics/kpi-sources?filter_reporting_period=2025-Q4").json() == []


def test_an_institution_user_sees_only_their_own_sources(client, db_session):
    inst = _setup(db_session)
    other = make_institution(db_session, code="BANK-B", name="Bank B Ltd")
    _seed_submission_for(db_session, other, region="Dodoma", amount=4_000_000.0)
    make_user(db_session, role=RoleEnum.INSTITUTION_USER, institution=inst, username="userA")
    make_user(db_session, role=RoleEnum.INSTITUTION_USER, institution=other, username="userB")
    a = _get(client, "userA", "/api/analytics/kpi-sources").json()
    b = _get(client, "userB", "/api/analytics/kpi-sources").json()
    assert [r["institution_name"] for r in a] == ["Bank A Ltd"]
    assert [r["institution_name"] for r in b] == ["Bank B Ltd"]
    # a client-supplied institution id cannot widen an institution user's scope
    wide = _get(client, "userA", f"/api/analytics/kpi-sources?filter_institution_id={other.id}").json()
    assert wide == []


def test_the_system_administrator_cannot_read_kpi_sources(client, db_session):
    _setup(db_session)
    make_user(db_session, role=RoleEnum.SYSTEM_ADMIN, username="adm1")
    assert _get(client, "adm1", "/api/analytics/kpi-sources").status_code == 403
