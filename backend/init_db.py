"""
Script to initialize the database and load initial SEED DATA (for demo/testing purposes).

IMPORTANT: All data here (users, institutions, climate records) is SAMPLE/DEMO
data used to demonstrate how the system works. It is NOT real financial or
climate data for Tanzania.

Run with: python init_db.py
"""
import random
from datetime import datetime

from app.core.database import Base, engine, SessionLocal
from app.core.security import hash_password
from app.models.models import User, Institution, RoleEnum, InstitutionType, ClimateRecord

print("Creating database tables...")
Base.metadata.create_all(bind=engine)

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
        regions = ["Dodoma", "Morogoro", "Mwanza", "Mbeya", "Dar es Salaam", "Singida"]
        hazards = [None, None, "Drought", "Flood", None, "Cyclone"]
        random.seed(42)  # fixed seed for reproducible demo output
        for year in [2024, 2025, 2026]:
            for month in range(1, 13):
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
                    ))

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
