"""
Script to initialize the database and load initial SEED DATA (for demo/testing purposes).

IMPORTANT: All data here (users, institutions, climate records) is SAMPLE/DEMO
data used to demonstrate how the system works. It is NOT real financial or
climate data for Tanzania.

Run with: python init_db.py
"""
import random
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from sqlalchemy import inspect
from app.core.config import settings
from app.core.database import engine, SessionLocal
from app.core.security import hash_password
from app.models.models import User, Institution, RoleEnum, InstitutionType, ClimateRecord, ClimateIngestionBatch

def ensure_schema():
    """Bring the database to the latest Alembic revision without deleting data.

    Fresh databases are migrated normally. A legacy CDR database that predates
    Alembic is stamped at the initial baseline only after a preflight check
    confirms its actual columns - not just its table names - match what
    revision d2616a6f36ac's own CREATE TABLE statements expect. Table-name
    matching alone cannot tell a fully-caught-up legacy database (which is
    what every real deployment of this project actually is, since the prior
    ensure_postgres_compatibility() bridge already added columns like
    climate_records.batch_id before Alembic existed) apart from an older,
    partially-migrated one for which stamping at this baseline would be
    silently wrong. Blindly stamping a mismatched database is worse than
    refusing to guess - it would make Alembic believe columns already exist
    that don't, and every later migration would then build on a false premise.
    """
    backend_dir = Path(__file__).resolve().parent
    with engine.connect() as conn:
        insp = inspect(conn)
        tables = set(insp.get_table_names())
        climate_columns = (
            {c["name"] for c in insp.get_columns("climate_records")}
            if "climate_records" in tables else set()
        )
    expected = {
        "institutions", "users", "refresh_tokens", "submissions",
        "submission_records", "validation_errors", "climate_records",
        "risk_advisory_notes", "password_reset_requests", "notifications",
        "climate_ingestion_batches", "climate_ingestion_errors", "audit_logs",
    }
    if "alembic_version" not in tables and expected.issubset(tables):
        if "batch_id" in climate_columns:
            # Matches revision d2616a6f36ac's own snapshot exactly (that
            # migration's climate_records already includes batch_id) - safe
            # to baseline here and let subsequent migrations build on it.
            subprocess.run([sys.executable, "-m", "alembic", "stamp", "d2616a6f36ac"], cwd=backend_dir, check=True)
        else:
            # Every table this project has ever created is here, but this
            # specific database predates even the batch_id bridge - an older
            # shape than any baseline this project's migrations assume. Stop
            # rather than guess: an incorrect stamp cannot be safely undone
            # once later migrations have built on it.
            raise RuntimeError(
                "Found the CDR tables, but climate_records is missing the "
                "batch_id column expected by every Alembic baseline this "
                "project ships. Refusing to guess which revision this "
                "database actually matches - back it up, then either add "
                "batch_id manually to match d2616a6f36ac before retrying, "
                "or start from a fresh database."
            )
    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=backend_dir, check=True)

print("Applying database migrations...")
ensure_schema()

# Production must never auto-create demo users with published credentials
# (every one of them is documented in this project's own README/presentations).
# Seeding is intentionally limited to development/training environments.
if settings.ENVIRONMENT == "production":
    print("Production environment detected: skipping demo seed data and demo credentials.")
    raise SystemExit(0)

db = SessionLocal()

try:
    if db.query(User).count() > 0:
        print("The database already contains data. Skipping seed data to avoid duplicates.")
    else:
        print("Loading SEED DATA (demo)...")

        # ---- Sample institutions ----
        bot = Institution(
            code="BOT-HQ", name="Bank of Tanzania (Headquarters)",
            type=InstitutionType.GOVERNMENT_AGENCY, contact_email="info@bot.go.tz",
        )
        bank_a = Institution(
            code="BANK-A", name="Sample Commercial Bank Ltd",
            type=InstitutionType.BANK, contact_email="reports@bankA-sample.co.tz",
        )
        bank_b = Institution(
            code="BANK-B", name="Sample National Bank Ltd",
            type=InstitutionType.BANK, contact_email="reports@bankB-sample.co.tz",
        )
        tma = Institution(
            code="TMA-01", name="Tanzania Meteorological Authority",
            type=InstitutionType.METEOROLOGICAL_AUTHORITY, contact_email="data@tma-sample.go.tz",
        )
        db.add_all([bot, bank_a, bank_b, tma])
        db.flush()

        # ---- Sample users ----
        users = [
            User(
                full_name="System Administrator", username="admin", email="admin@cdr-demo.local",
                hashed_password=hash_password("Admin@123"), role=RoleEnum.SYSTEM_ADMIN,
                institution_id=bot.id,
            ),
            User(
                full_name="BOT Analyst (Internal)", username="bot_analyst", email="analyst@cdr-demo.local",
                hashed_password=hash_password("Analyst@123"), role=RoleEnum.BOT_USER,
                institution_id=bot.id,
            ),
            User(
                full_name="Bank A - Reporting Officer", username="bankA_user", email="user@bankA-sample.local",
                hashed_password=hash_password("BankA@123"), role=RoleEnum.INSTITUTION_USER,
                institution_id=bank_a.id,
            ),
            User(
                full_name="Bank B - Reporting Officer", username="bankB_user", email="user@bankB-sample.local",
                hashed_password=hash_password("BankB@123"), role=RoleEnum.INSTITUTION_USER,
                institution_id=bank_b.id,
            ),
        ]
        db.add_all(users)

        # ---- Climate records - SYNTHETIC SAMPLE DATA only ----
        # quality_flag="SYNTHETIC" and source="SYNTHETIC_SAMPLE" make this unmistakable
        # everywhere the record is displayed or exported - never presentable as real TMA data.
        regions = ["Dodoma", "Morogoro", "Mwanza", "Mbeya", "Dar es Salaam", "Singida"]
        hazards = [None, None, "Drought", "Flood", None, "Cyclone"]
        random.seed(42)  # fixed seed for reproducible demo output
        seed_run_time = datetime.utcnow()
        synthetic_batch = ClimateIngestionBatch(
            source="SYNTHETIC_SEED",
            dataset_name="CDR Synthetic Demo Dataset",
            dataset_version="v1",
            file_name="synthetic_seed",
            records_received=0, records_accepted=0, records_rejected=0, records_duplicate=0,
            status="COMPLETED",
            error_summary="Synthetic demonstration data; not an external climate feed.",
        )
        db.add(synthetic_batch)
        db.flush()
        synthetic_count = 0
        for year in [2024, 2025, 2026]:
            for month in range(1, 13):
                quarter = (month - 1) // 3 + 1
                for region in regions:
                    db.add(ClimateRecord(
                        region=region,
                        district=None,
                        year=year,
                        month=month,
                        rainfall_mm=round(random.uniform(10, 250), 1),
                        avg_temperature_c=round(random.uniform(18, 33), 1),
                        hazard_type=random.choice(hazards),
                        hazard_severity=random.choice(["LOW", "MEDIUM", "HIGH", None]),
                        source="SYNTHETIC_SAMPLE",
                        reporting_period=f"{year}-Q{quarter}",
                        period_type="MONTHLY",
                        dataset_name="CDR Synthetic Demo Dataset",
                        dataset_version="v1",
                        quality_flag="SYNTHETIC",
                        processing_method="SYNTHETIC_SEED",
                        ingestion_timestamp=seed_run_time,
                        batch_id=synthetic_batch.id,
                    ))
                    synthetic_count += 1
        synthetic_batch.records_received = synthetic_count
        synthetic_batch.records_accepted = synthetic_count

        # Synthetic seed data remains SYNTHETIC throughout. Real VALIDATED/FLAGGED
        # states are created only by the climate ingestion + human QC workflow.
        db.commit()
        print("Seed data loaded successfully.")
        print("")
        print("========== DEMO LOGIN CREDENTIALS ==========")
        print("System Admin   -> username: admin        password: Admin@123")
        print("BOT Analyst    -> username: bot_analyst   password: Analyst@123")
        print("Bank A User    -> username: bankA_user    password: BankA@123")
        print("Bank B User    -> username: bankB_user    password: BankB@123")
        print("=============================================")
        print("IMPORTANT: Change these passwords before any real/production use.")

finally:
    db.close()
