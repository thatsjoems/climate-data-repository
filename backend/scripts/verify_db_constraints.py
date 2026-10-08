"""
Verify the REAL, deployed database actually has every CHECK constraint and
duplicate-prevention index this project's models.py declares.

Why this script exists: the eighth review's own SQLite-based tests, and
Alembic reporting "upgrade OK", both passed while this project's actual
real database was silently missing every CHECK constraint - because
`alembic stamp` (used for a pre-Alembic legacy database) records a
revision as applied without running its DDL. That gap was only caught by
manually running `\\d climate_records` in psql. This script is that same
check, made repeatable instead of manual - so the next time a migration
changes, this can be re-run rather than re-discovered by chance.

Usage (run inside the backend container, or anywhere DATABASE_URL points
at the real database):
    python scripts/verify_db_constraints.py

Exits 0 and prints a clean summary if everything expected is present.
Exits 1 and lists exactly what's missing otherwise.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import create_engine, inspect  # noqa: E402
from app.core.config import settings  # noqa: E402

EXPECTED_CHECK_CONSTRAINTS = {
    "api_clients": {
        "ck_api_clients_expiry_after_creation", "ck_api_clients_name_not_blank",
        "ck_api_clients_key_hash_length", "ck_api_clients_revoker_needs_revocation", "ck_api_clients_scope_valid", "ck_api_clients_allowed_networks_not_blank",
    },
    "climate_ingestion_batches": {"ck_climate_ingestion_batches_one_uploader"},
    "users": {"ck_users_institution_user_has_institution", "ck_users_mfa_enabled_has_secret"},
    "submissions": {
        "ck_submissions_reporting_period_format",
        "ck_submissions_version_number_positive",
        "ck_submissions_record_counts_consistent",
        "ck_submissions_current_only_valid_or_approved",
        "ck_submissions_reviewer_not_submitter",
    },
    "climate_records": {
        "ck_climate_records_reporting_period_format",
        "ck_climate_records_hazard_severity", "ck_climate_records_period_type",
        "ck_climate_records_quality_flag", "ck_climate_records_avg_temperature_plausible",
        "ck_climate_records_latitude", "ck_climate_records_longitude",
        "ck_climate_records_month", "ck_climate_records_rainfall_nonnegative",
        "ck_climate_records_max_temperature_plausible", "ck_climate_records_avg_le_max",
        "ck_climate_records_min_temperature_plausible", "ck_climate_records_min_le_avg",
        "ck_climate_records_min_le_max",
    },
    "submission_records": {
        "ck_submission_records_interest_rate", "ck_submission_records_turnover_nonnegative",
        "ck_submission_records_forced_sale_nonnegative", "ck_submission_records_collateral_latitude",
        "ck_submission_records_collateral_longitude", "ck_submission_records_collateral_value_nonnegative",
        "ck_submission_records_insurance_nonnegative", "ck_submission_records_loan_amount_nonnegative",
        "ck_submission_records_loan_latitude", "ck_submission_records_loan_longitude",
        "ck_submission_records_outstanding_nonnegative", "ck_submission_records_outstanding_le_loan",
    },
}

EXPECTED_UNIQUE_INDEXES = {
    "api_clients": {"uq_api_clients_key_prefix", "uq_api_clients_active_name"},
    "climate_records": {"uq_climate_observation_source_identity", "uq_climate_observation_station_identity"},
    "submissions": {"uq_submissions_one_current_per_institution_period"},
    "submission_records": {"uq_submission_records_submission_loan"},
}

EXPECTED_COLUMNS = {
    "audit_logs": {"details_json"},
}


def main() -> int:
    engine = create_engine(settings.DATABASE_URL)
    inspector = inspect(engine)
    missing = []

    for table, expected_names in EXPECTED_CHECK_CONSTRAINTS.items():
        actual = {c["name"] for c in inspector.get_check_constraints(table)}
        gap = expected_names - actual
        for name in sorted(gap):
            missing.append(f"CHECK constraint '{name}' missing on table '{table}'")

    for table, expected_names in EXPECTED_UNIQUE_INDEXES.items():
        actual = {idx["name"] for idx in inspector.get_indexes(table) if idx.get("unique")}
        # SQLite SQLAlchemy reflection skips some expression/partial indexes.
        # Fall back to PRAGMA so the verifier checks the real database object.
        if inspector.bind.dialect.name == "sqlite":
            with inspector.bind.connect() as conn:
                rows = conn.exec_driver_sql(f"PRAGMA index_list('{table}')").fetchall()
            actual |= {row[1] for row in rows if len(row) > 2 and row[2] == 1}
        gap = expected_names - actual
        for name in sorted(gap):
            missing.append(f"UNIQUE index '{name}' missing on table '{table}'")

    for table, expected_names in EXPECTED_COLUMNS.items():
        actual = {c["name"] for c in inspector.get_columns(table)}
        gap = expected_names - actual
        for name in sorted(gap):
            missing.append(f"Column '{name}' missing on table '{table}'")

    unvalidated = []
    if engine.dialect.name == "postgresql":
        with engine.connect() as conn:
            unvalidated = [
                row[0] for row in conn.exec_driver_sql(
                    "SELECT conname FROM pg_constraint WHERE contype = 'c' AND NOT convalidated ORDER BY conname"
                )
            ]

    total_expected = (
        sum(len(v) for v in EXPECTED_CHECK_CONSTRAINTS.values())
        + sum(len(v) for v in EXPECTED_UNIQUE_INDEXES.values())
        + sum(len(v) for v in EXPECTED_COLUMNS.values())
    )

    if missing:
        print(f"FAILED: {len(missing)} of {total_expected} expected database-level protections are missing:")
        for m in missing:
            print(f"  - {m}")
        print("\nLikely cause: migrations have not been upgraded on this database yet.")
        print("Run: alembic upgrade head")
        return 1

    print(f"OK: all {total_expected} expected CHECK constraints and unique indexes are present on the real database.")
    if unvalidated:
        print("\nWARNING: these CHECK constraints exist and are enforced for new rows, but were added NOT VALID")
        print("because older rows break them. Find and fix those rows, then run for each:")
        print("  ALTER TABLE <table> VALIDATE CONSTRAINT <name>;")
        for name in unvalidated:
            print(f"  - {name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
