"""
Climate data ingestion tests - Sections 8, 9, 19 of the hardening request.
"""
import io

from app.models.models import RoleEnum, ClimateRecord
from tests.conftest import make_user, login, auth_header


def _csv_bytes(rows: list[str]) -> bytes:
    header = "region,district,year,month,rainfall_mm,avg_temperature_c,hazard_type,hazard_severity,source_record_id"
    return ("\n".join([header] + rows) + "\n").encode()


def test_only_bot_user_can_ingest_climate_data(client, db_session):
    make_user(db_session, role=RoleEnum.INSTITUTION_USER, username="inst_user")
    token = login(client, "inst_user").json()["access_token"]
    csv_bytes = _csv_bytes(["Dodoma,,2026,7,45.2,28.5,Drought,MEDIUM,REC-1"])
    res = client.post(
        "/api/climate-data/ingest",
        data={"source": "MANUAL_UPLOAD"},
        files={"file": ("data.csv", csv_bytes, "text/csv")},
        headers=auth_header(token),
    )
    assert res.status_code == 403


def test_system_admin_cannot_ingest_climate_data(client, db_session):
    make_user(db_session, role=RoleEnum.SYSTEM_ADMIN, username="admin1")
    token = login(client, "admin1").json()["access_token"]
    csv_bytes = _csv_bytes(["Dodoma,,2026,7,45.2,28.5,Drought,MEDIUM,REC-1"])
    res = client.post(
        "/api/climate-data/ingest",
        data={"source": "MANUAL_UPLOAD"},
        files={"file": ("data.csv", csv_bytes, "text/csv")},
        headers=auth_header(token),
    )
    assert res.status_code == 403


def test_valid_climate_csv_is_ingested(client, db_session):
    make_user(db_session, role=RoleEnum.BOT_USER, username="analyst1")
    token = login(client, "analyst1").json()["access_token"]
    csv_bytes = _csv_bytes([
        "Dodoma,Chamwino District,2026,7,45.2,28.5,Drought,MEDIUM,REC-1",
        "Mwanza,,2026,7,120.0,25.1,Flood,HIGH,REC-2",
    ])
    res = client.post(
        "/api/climate-data/ingest",
        data={"source": "MANUAL_UPLOAD", "dataset_name": "Test Batch"},
        files={"file": ("data.csv", csv_bytes, "text/csv")},
        headers=auth_header(token),
    )
    assert res.status_code == 201
    body = res.json()
    assert body["records_accepted"] == 2
    assert body["records_rejected"] == 0

    stored = db_session.query(ClimateRecord).all()
    assert len(stored) == 2
    assert stored[0].quality_flag == "UNVALIDATED"
    assert stored[0].source == "MANUAL_UPLOAD"


def test_invalid_region_is_rejected_not_guessed(client, db_session):
    """Acceptance criterion: an unresolved region must never be silently mapped anywhere."""
    make_user(db_session, role=RoleEnum.BOT_USER, username="analyst1")
    token = login(client, "analyst1").json()["access_token"]
    csv_bytes = _csv_bytes(["Narnia,,2026,7,45.2,28.5,,,REC-1"])
    res = client.post(
        "/api/climate-data/ingest",
        data={"source": "MANUAL_UPLOAD"},
        files={"file": ("data.csv", csv_bytes, "text/csv")},
        headers=auth_header(token),
    )
    assert res.status_code == 201
    body = res.json()
    assert body["records_accepted"] == 0
    assert body["records_rejected"] == 1
    assert db_session.query(ClimateRecord).count() == 0


def test_row_with_no_measurement_is_rejected(client, db_session):
    make_user(db_session, role=RoleEnum.BOT_USER, username="analyst1")
    token = login(client, "analyst1").json()["access_token"]
    csv_bytes = _csv_bytes(["Dodoma,,2026,7,,,,,REC-1"])
    res = client.post(
        "/api/climate-data/ingest",
        data={"source": "MANUAL_UPLOAD"},
        files={"file": ("data.csv", csv_bytes, "text/csv")},
        headers=auth_header(token),
    )
    assert res.json()["records_accepted"] == 0
    assert res.json()["records_rejected"] == 1


def test_duplicate_observation_across_two_uploads_is_rejected_not_overwritten(client, db_session):
    """Acceptance criterion: never automatically overwrite previous source data."""
    make_user(db_session, role=RoleEnum.BOT_USER, username="analyst1")
    token = login(client, "analyst1").json()["access_token"]
    csv_bytes = _csv_bytes(["Dodoma,,2026,7,45.2,28.5,Drought,MEDIUM,REC-1"])

    first = client.post(
        "/api/climate-data/ingest", data={"source": "MANUAL_UPLOAD"},
        files={"file": ("data.csv", csv_bytes, "text/csv")}, headers=auth_header(token),
    )
    assert first.json()["records_accepted"] == 1

    second = client.post(
        "/api/climate-data/ingest", data={"source": "MANUAL_UPLOAD"},
        files={"file": ("data2.csv", csv_bytes, "text/csv")}, headers=auth_header(token),
    )
    assert second.json()["records_accepted"] == 0
    assert second.json()["records_duplicate"] == 1
    # Still only one row in the database - not overwritten, not duplicated
    assert db_session.query(ClimateRecord).count() == 1


def test_data_quality_summary_reflects_real_counts(client, db_session):
    make_user(db_session, role=RoleEnum.BOT_USER, username="analyst1")
    token = login(client, "analyst1").json()["access_token"]
    csv_bytes = _csv_bytes([
        "Dodoma,,2026,7,45.2,28.5,Drought,MEDIUM,REC-1",
        "Narnia,,2026,7,45.2,28.5,,,REC-2",
    ])
    client.post(
        "/api/climate-data/ingest", data={"source": "MANUAL_UPLOAD"},
        files={"file": ("data.csv", csv_bytes, "text/csv")}, headers=auth_header(token),
    )

    res = client.get("/api/climate-data/quality-summary", headers=auth_header(token))
    assert res.status_code == 200
    body = res.json()
    assert body["total_observations"] == 1
    assert body["unvalidated_observations"] == 1
    assert body["total_records_rejected_all_time"] == 1
    assert "Dodoma" not in body["regions_missing_data"]


def test_missing_climate_data_shown_as_none_never_fabricated(client, db_session):
    """
    Acceptance criterion G: missing TMA observations remain missing. A region
    with no climate observations must return null/None in combined exposure,
    never an estimated or copied-from-elsewhere value.
    """
    from tests.test_rbac_and_isolation import _seed_submission_for
    from tests.conftest import make_institution

    inst = make_institution(db_session)
    # Seed a submission for a region with NO climate data at all
    _seed_submission_for(db_session, inst, region="Kigoma", district="Kigoma District")

    make_user(db_session, role=RoleEnum.BOT_USER, username="analyst1")
    token = login(client, "analyst1").json()["access_token"]

    res = client.get("/api/analytics/combined-climate-financial-exposure", headers=auth_header(token))
    assert res.status_code == 200
    rows = [r for r in res.json() if r["region"] == "Kigoma"]
    assert len(rows) == 1
    assert rows[0]["avg_rainfall_mm"] is None
    assert rows[0]["avg_temperature_c"] is None
