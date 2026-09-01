"""
Script ya kuanzisha database na kuweka SEED DATA ya awali (kwa ajili ya demo/majaribio).

MUHIMU: Data zote hapa (watumiaji, taasisi, climate records) ni za SAMPLE/DEMO
kwa ajili ya kuonyesha mfumo unavyofanya kazi. SIYO data halisi za kiuchumi
au za hali ya hewa za Tanzania.

Endesha kwa: python init_db.py
"""
import random
from datetime import datetime

from app.core.database import Base, engine, SessionLocal
from app.core.security import hash_password
from app.models.models import User, Institution, RoleEnum, InstitutionType, ClimateRecord

print("Inatengeneza majedwali ya database...")
Base.metadata.create_all(bind=engine)

db = SessionLocal()

try:
    if db.query(User).count() > 0:
        print("Database tayari ina data. Sitaongeza tena seed data (epuka duplicate).")
    else:
        print("Inaweka SEED DATA (demo)...")

        # ---- Taasisi za mfano ----
        bot = Institution(
            code="BOT-HQ", name="Bank of Tanzania (Headquarters)",
            type=InstitutionType.GOVERNMENT_AGENCY, contact_email="info@bot.go.tz",
        )
        bank_a = Institution(
            code="BANK-A", name="Mfano Commercial Bank Ltd",
            type=InstitutionType.BANK, contact_email="reports@bankA-sample.co.tz",
        )
        bank_b = Institution(
            code="BANK-B", name="Sampuli National Bank Ltd",
            type=InstitutionType.BANK, contact_email="reports@bankB-sample.co.tz",
        )
        tma = Institution(
            code="TMA-01", name="Tanzania Meteorological Authority",
            type=InstitutionType.METEOROLOGICAL_AUTHORITY, contact_email="data@tma-sample.go.tz",
        )
        db.add_all([bot, bank_a, bank_b, tma])
        db.flush()

        # ---- Watumiaji wa mfano ----
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

        # ---- Climate records - SYNTHETIC SAMPLE DATA pekee ----
        regions = ["Dodoma", "Morogoro", "Mwanza", "Mbeya", "Dar es Salaam", "Singida"]
        hazards = [None, None, "Drought", "Flood", None, "Cyclone"]
        random.seed(42)  # matokeo yanayorudiwa (reproducible) - kwa ajili ya demo tu
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
        print("Seed data imewekwa kikamilifu.")
        print("")
        print("========== TAARIFA ZA KUINGIA (LOGIN) ZA DEMO ==========")
        print("System Admin   -> username: admin        password: Admin@123")
        print("BOT Analyst    -> username: bot_analyst   password: Analyst@123")
        print("Bank A User    -> username: bankA_user    password: BankA@123")
        print("Bank B User    -> username: bankB_user    password: BankB@123")
        print("=========================================================")
        print("MUHIMU: Badilisha password hizi kabla ya matumizi halisi (production).")

finally:
    db.close()
