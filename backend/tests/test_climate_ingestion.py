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
        data={"source": "MANUAL_TMA_FILE"},
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
        data={"source": "MANUAL_TMA_FILE"},
        files={"file": ("data.csv", csv_bytes, "text/csv")},
        headers=auth_header(token),
    )
    assert res.status_code == 403


def test_valid_climate_csv_is_ingested(client, db_session):
    make_user(db_session, role=RoleEnum.BOT_USER, username="analyst1")
    token = login(client, "analyst1").json()["access_token"]
    csv_bytes = _csv_bytes([
        "Dodoma,Chamwino,2026,7,45.2,28.5,Drought,MEDIUM,REC-1",
        "Mwanza,,2026,7,120.0,25.1,Flood,HIGH,REC-2",
    ])
    res = client.post(
        "/api/climate-data/ingest",
        data={"source": "MANUAL_TMA_FILE", "dataset_name": "Test Batch"},
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
    assert stored[0].source == "MANUAL_TMA_FILE"


def test_invalid_region_is_rejected_not_guessed(client, db_session):
    """Acceptance criterion: an unresolved region must never be silently mapped anywhere."""
    make_user(db_session, role=RoleEnum.BOT_USER, username="analyst1")
    token = login(client, "analyst1").json()["access_token"]
    csv_bytes = _csv_bytes(["Narnia,,2026,7,45.2,28.5,,,REC-1"])
    res = client.post(
        "/api/climate-data/ingest",
        data={"source": "MANUAL_TMA_FILE"},
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
        data={"source": "MANUAL_TMA_FILE"},
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
        "/api/climate-data/ingest", data={"source": "MANUAL_TMA_FILE"},
        files={"file": ("data.csv", csv_bytes, "text/csv")}, headers=auth_header(token),
    )
    assert first.json()["records_accepted"] == 1

    second = client.post(
        "/api/climate-data/ingest", data={"source": "MANUAL_TMA_FILE"},
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
        "/api/climate-data/ingest", data={"source": "MANUAL_TMA_FILE"},
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
    _seed_submission_for(db_session, inst, region="Kigoma", district="Kigoma")

    make_user(db_session, role=RoleEnum.BOT_USER, username="analyst1")
    token = login(client, "analyst1").json()["access_token"]

    res = client.get("/api/analytics/combined-climate-financial-exposure", headers=auth_header(token))
    assert res.status_code == 200
    rows = [r for r in res.json() if r["region"] == "Kigoma"]
    assert len(rows) == 1
    assert rows[0]["avg_rainfall_mm"] is None
    assert rows[0]["avg_temperature_c"] is None


# ---------------------------------------------------------------------------
# Climate QC promotion (Module: closing the "VALIDATED is unreachable" gap
# identified via external review) - the one action that lets a human move a
# reading from UNVALIDATED to VALIDATED or FLAGGED.
# ---------------------------------------------------------------------------

def test_only_bot_user_can_promote_climate_records(client, db_session):
    make_user(db_session, role=RoleEnum.INSTITUTION_USER, username="inst_user")
    token = login(client, "inst_user").json()["access_token"]
    res = client.post(
        "/api/climate-data/promote",
        json={"region": "Dodoma", "reporting_period": "2026-Q1", "new_quality_flag": "VALIDATED"},
        headers=auth_header(token),
    )
    assert res.status_code == 403


def test_promote_moves_unvalidated_to_validated(client, db_session):
    make_user(db_session, role=RoleEnum.BOT_USER, username="analyst1")
    token = login(client, "analyst1").json()["access_token"]

    db_session.add(ClimateRecord(region="Dodoma", year=2026, month=2, rainfall_mm=50.0,
                                  reporting_period="2026-Q1", quality_flag="UNVALIDATED"))
    db_session.add(ClimateRecord(region="Dodoma", year=2026, month=3, rainfall_mm=60.0,
                                  reporting_period="2026-Q1", quality_flag="UNVALIDATED"))
    db_session.commit()

    res = client.post(
        "/api/climate-data/promote",
        json={"region": "Dodoma", "reporting_period": "2026-Q1", "new_quality_flag": "VALIDATED"},
        headers=auth_header(token),
    )
    assert res.status_code == 200
    assert res.json()["records_updated"] == 2

    still_unvalidated = db_session.query(ClimateRecord).filter(ClimateRecord.quality_flag == "UNVALIDATED").count()
    validated = db_session.query(ClimateRecord).filter(ClimateRecord.quality_flag == "VALIDATED").count()
    assert still_unvalidated == 0
    assert validated == 2


def test_promote_never_touches_synthetic_or_already_decided_records(client, db_session):
    """SYNTHETIC demo data must never be silently reclassified as if a human reviewed real TMA data."""
    make_user(db_session, role=RoleEnum.BOT_USER, username="analyst1")
    token = login(client, "analyst1").json()["access_token"]

    db_session.add(ClimateRecord(region="Dodoma", year=2026, month=2, rainfall_mm=50.0,
                                  reporting_period="2026-Q1", quality_flag="SYNTHETIC"))
    db_session.add(ClimateRecord(region="Dodoma", year=2026, month=3, rainfall_mm=999.0,
                                  reporting_period="2026-Q1", quality_flag="FLAGGED"))
    db_session.commit()

    res = client.post(
        "/api/climate-data/promote",
        json={"region": "Dodoma", "reporting_period": "2026-Q1", "new_quality_flag": "VALIDATED"},
        headers=auth_header(token),
    )
    assert res.status_code == 200
    assert res.json()["records_updated"] == 0  # nothing was UNVALIDATED, so nothing changed

    assert db_session.query(ClimateRecord).filter(ClimateRecord.quality_flag == "SYNTHETIC").count() == 1
    assert db_session.query(ClimateRecord).filter(ClimateRecord.quality_flag == "FLAGGED").count() == 1


def test_unvalidated_groups_lists_regions_awaiting_review(client, db_session):
    make_user(db_session, role=RoleEnum.BOT_USER, username="analyst1")
    token = login(client, "analyst1").json()["access_token"]

    db_session.add(ClimateRecord(region="Mbeya", year=2026, month=2, rainfall_mm=50.0,
                                  reporting_period="2026-Q1", quality_flag="UNVALIDATED"))
    db_session.add(ClimateRecord(region="Mbeya", year=2026, month=3, rainfall_mm=55.0,
                                  reporting_period="2026-Q1", quality_flag="UNVALIDATED"))
    db_session.commit()

    res = client.get("/api/climate-data/unvalidated-groups", headers=auth_header(token))
    assert res.status_code == 200
    groups = res.json()
    match = next(g for g in groups if g["region"] == "Mbeya" and g["reporting_period"] == "2026-Q1")
    assert match["count"] == 2


# ---------------------------------------------------------------------------
# Source provenance control (Module: source integrity) - found via external
# review: an unrestricted free-text "source" field let an analyst label any
# file "TMA_FILE", indistinguishable from a genuinely verified feed.
# ---------------------------------------------------------------------------

def test_ingest_rejects_unrecognized_source_value(client, db_session):
    make_user(db_session, role=RoleEnum.BOT_USER, username="analyst1")
    token = login(client, "analyst1").json()["access_token"]
    csv_bytes = _csv_bytes(["Dodoma,,2026,7,45.2,28.5,Drought,MEDIUM,REC-1"])
    res = client.post(
        "/api/climate-data/ingest",
        data={"source": "TMA_FILE"},  # sounds official but is not an allowed value
        files={"file": ("data.csv", csv_bytes, "text/csv")},
        headers=auth_header(token),
    )
    assert res.status_code == 400


def test_ingest_accepts_manual_tma_file_source(client, db_session):
    make_user(db_session, role=RoleEnum.BOT_USER, username="analyst1")
    token = login(client, "analyst1").json()["access_token"]
    csv_bytes = _csv_bytes(["Dodoma,,2026,7,45.2,28.5,Drought,MEDIUM,REC-1"])
    res = client.post(
        "/api/climate-data/ingest",
        data={"source": "MANUAL_TMA_FILE"},
        files={"file": ("data.csv", csv_bytes, "text/csv")},
        headers=auth_header(token),
    )
    assert res.status_code == 201


# ---------------------------------------------------------------------------
# Climate physical plausibility (Module: climate data quality) - found via
# external review: negative rainfall, out-of-range temperatures, and invalid
# GPS coordinates could previously pass validation as long as they were
# numeric.
# ---------------------------------------------------------------------------

def test_ingest_rejects_negative_rainfall(client, db_session):
    make_user(db_session, role=RoleEnum.BOT_USER, username="analyst1")
    token = login(client, "analyst1").json()["access_token"]
    csv_bytes = _csv_bytes(["Dodoma,,2026,7,-50.0,28.5,,,REC-1"])
    res = client.post(
        "/api/climate-data/ingest", data={"source": "MANUAL_TMA_FILE"},
        files={"file": ("data.csv", csv_bytes, "text/csv")}, headers=auth_header(token),
    )
    assert res.status_code == 201
    assert res.json()["records_rejected"] == 1


def test_ingest_rejects_implausible_temperature(client, db_session):
    make_user(db_session, role=RoleEnum.BOT_USER, username="analyst1")
    token = login(client, "analyst1").json()["access_token"]
    csv_bytes = _csv_bytes(["Dodoma,,2026,7,45.2,500.0,,,REC-1"])
    res = client.post(
        "/api/climate-data/ingest", data={"source": "MANUAL_TMA_FILE"},
        files={"file": ("data.csv", csv_bytes, "text/csv")}, headers=auth_header(token),
    )
    assert res.status_code == 201
    assert res.json()["records_rejected"] == 1


def test_ingest_rejects_invalid_gps_coordinates(client, db_session):
    make_user(db_session, role=RoleEnum.BOT_USER, username="analyst1")
    token = login(client, "analyst1").json()["access_token"]
    header = "region,district,year,month,rainfall_mm,avg_temperature_c,hazard_type,hazard_severity,latitude,longitude,source_record_id"
    csv_bytes = (header + "\nDodoma,,2026,7,45.2,28.5,,,999,35.0,REC-1\n").encode()
    res = client.post(
        "/api/climate-data/ingest", data={"source": "MANUAL_TMA_FILE"},
        files={"file": ("data.csv", csv_bytes, "text/csv")}, headers=auth_header(token),
    )
    assert res.status_code == 201
    assert res.json()["records_rejected"] == 1


# ---------------------------------------------------------------------------
# Hazard normalization (Module: hazard taxonomy) - found via external
# review: "Flood", "flood", "FLOOD", "Flooding" could each count as a
# different hazard in analytics, fragmenting hazard counts.
# ---------------------------------------------------------------------------

def test_ingest_normalizes_hazard_case_and_synonyms(client, db_session):
    make_user(db_session, role=RoleEnum.BOT_USER, username="analyst1")
    token = login(client, "analyst1").json()["access_token"]
    csv_bytes = _csv_bytes([
        "Dodoma,,2026,7,45.2,28.5,flooding,MEDIUM,REC-1",
        "Dodoma,,2026,8,50.0,27.0,FLOOD,MEDIUM,REC-2",
    ])
    res = client.post(
        "/api/climate-data/ingest", data={"source": "MANUAL_TMA_FILE"},
        files={"file": ("data.csv", csv_bytes, "text/csv")}, headers=auth_header(token),
    )
    assert res.status_code == 201
    assert res.json()["records_accepted"] == 2
    hazards = {r.hazard_type for r in db_session.query(ClimateRecord).all()}
    assert hazards == {"Flood"}  # both synonyms normalized to the same canonical form


def test_ingest_rejects_unrecognized_hazard_type(client, db_session):
    make_user(db_session, role=RoleEnum.BOT_USER, username="analyst1")
    token = login(client, "analyst1").json()["access_token"]
    csv_bytes = _csv_bytes(["Dodoma,,2026,7,45.2,28.5,Earthquake,MEDIUM,REC-1"])
    res = client.post(
        "/api/climate-data/ingest", data={"source": "MANUAL_TMA_FILE"},
        files={"file": ("data.csv", csv_bytes, "text/csv")}, headers=auth_header(token),
    )
    assert res.status_code == 201
    assert res.json()["records_rejected"] == 1


def test_promote_reason_is_recorded_in_audit_log(client, db_session):
    from app.models.models import AuditLog
    make_user(db_session, role=RoleEnum.BOT_USER, username="analyst1")
    token = login(client, "analyst1").json()["access_token"]

    db_session.add(ClimateRecord(region="Dodoma", year=2026, month=2, rainfall_mm=9999.0,
                                  reporting_period="2026-Q1", quality_flag="UNVALIDATED"))
    db_session.commit()

    res = client.post(
        "/api/climate-data/promote",
        json={"region": "Dodoma", "reporting_period": "2026-Q1", "new_quality_flag": "FLAGGED",
              "reason": "Rainfall value inconsistent with source station record."},
        headers=auth_header(token),
    )
    assert res.status_code == 200

    entry = db_session.query(AuditLog).filter(AuditLog.action == "CLIMATE_DATA_QC_PROMOTED").order_by(AuditLog.created_at.desc()).first()
    assert entry is not None
    assert "Rainfall value inconsistent with source station record." in entry.details


def test_flagged_qc_requires_reason(client, db_session):
    make_user(db_session, role=RoleEnum.BOT_USER, username="analyst_flag_reason")
    token = login(client, "analyst_flag_reason").json()["access_token"]

    db_session.add(ClimateRecord(region="Dodoma", year=2026, month=2, rainfall_mm=100.0,
                                  reporting_period="2026-Q1", quality_flag="UNVALIDATED"))
    db_session.commit()

    res = client.post(
        "/api/climate-data/promote",
        json={"region": "Dodoma", "reporting_period": "2026-Q1", "new_quality_flag": "FLAGGED"},
        headers=auth_header(token),
    )
    assert res.status_code == 400
    assert "reason is required" in res.json()["detail"]


def test_ingested_records_are_linked_to_their_batch(client, db_session):
    """
    Regression test: every ClimateRecord created by a file ingestion must
    carry the FK of the ClimateIngestionBatch that created it (provenance -
    "which file/batch did this observation come from?" must be answerable
    directly from the database, not just from source/dataset_name text).
    """
    from app.models.models import ClimateIngestionBatch

    make_user(db_session, role=RoleEnum.BOT_USER, username="analyst_prov")
    token = login(client, "analyst_prov").json()["access_token"]
    csv_bytes = _csv_bytes([
        "Dodoma,Chamwino,2026,7,45.2,28.5,Drought,MEDIUM,REC-PROV-1",
        "Mwanza,,2026,7,120.0,25.1,Flood,HIGH,REC-PROV-2",
    ])
    res = client.post(
        "/api/climate-data/ingest",
        data={"source": "MANUAL_TMA_FILE", "dataset_name": "Provenance Test Batch"},
        files={"file": ("data.csv", csv_bytes, "text/csv")},
        headers=auth_header(token),
    )
    assert res.status_code == 201
    batch_id = res.json()["id"]

    batch = db_session.query(ClimateIngestionBatch).filter_by(id=batch_id).first()
    assert batch is not None

    records = db_session.query(ClimateRecord).filter_by(batch_id=batch_id).all()
    assert len(records) == 2
    assert all(r.batch_id == batch.id for r in records)
