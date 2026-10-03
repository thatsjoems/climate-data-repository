"""add missing check constraints for stamped legacy databases

Revision ID: 9c1852419557
Revises: 8b2f5c1e9a44

Why this migration exists, and why it is NOT a fix folded into
8b2f5c1e9a44 or d2616a6f36ac: both of those migrations have already run
against real deployments of this project (confirmed via \\d climate_records
on a live database showing zero "Check constraints:" entries). Editing an
already-applied migration's file changes nothing for a database that
already recorded that revision as done - Alembic tracks "have I run
migration X" by revision ID, not by re-diffing the file's contents. The
only correct way to deliver a fix to an environment that already has an
earlier revision applied is a new migration that runs on top of it.

Root cause: d2616a6f36ac's CHECK constraints are declared as part of its
own op.create_table() calls. That runs its DDL for a genuinely fresh
database. But init_db.py's legacy-database path calls `alembic stamp
d2616a6f36ac` for a database whose tables already existed before Alembic
did - stamping only records "this revision is considered applied," it
never executes that revision's create_table() (the tables already exist,
so there's nothing to create). The result: every CHECK constraint that
migration was supposed to add via CREATE TABLE was silently skipped on
every database that reached this schema by that legacy path - which is
every real deployment of this project to date.

Idempotent by construction (checks each constraint's existence by name
before adding it), so this is equally correct whether run against a
legacy database missing these constraints, or a hypothetical fresh
database where d2616a6f36ac's own create_table() already added them.
"""
from alembic import op
from sqlalchemy import inspect

revision = "9c1852419557"
down_revision = "8b2f5c1e9a44"
branch_labels = None
depends_on = None

CHECK_CONSTRAINTS = [
    ("submissions", "ck_submissions_reporting_period_format",
     "length(reporting_period) = 7 AND substr(reporting_period, 5, 2) = '-Q' AND substr(reporting_period, 7, 1) IN ('1','2','3','4')"),
    ("climate_records", "ck_climate_records_hazard_severity",
     "hazard_severity IS NULL OR hazard_severity IN ('LOW','MEDIUM','HIGH')"),
    ("climate_records", "ck_climate_records_period_type",
     "period_type IS NULL OR period_type IN ('DAILY','MONTHLY','QUARTERLY','ANNUAL')"),
    ("climate_records", "ck_climate_records_quality_flag",
     "quality_flag IN ('UNVALIDATED','VALIDATED','FLAGGED','SYNTHETIC')"),
    ("climate_records", "ck_climate_records_avg_temperature_plausible",
     "avg_temperature_c IS NULL OR (avg_temperature_c >= -90 AND avg_temperature_c <= 70)"),
    ("climate_records", "ck_climate_records_latitude",
     "latitude IS NULL OR (latitude >= -90 AND latitude <= 90)"),
    ("climate_records", "ck_climate_records_longitude",
     "longitude IS NULL OR (longitude >= -180 AND longitude <= 180)"),
    ("climate_records", "ck_climate_records_month",
     "month IS NULL OR (month >= 1 AND month <= 12)"),
    ("climate_records", "ck_climate_records_rainfall_nonnegative",
     "rainfall_mm IS NULL OR rainfall_mm >= 0"),
    ("climate_records", "ck_climate_records_max_temperature_plausible",
     "temperature_max_c IS NULL OR (temperature_max_c >= -90 AND temperature_max_c <= 70)"),
    ("climate_records", "ck_climate_records_avg_le_max",
     "temperature_max_c IS NULL OR avg_temperature_c IS NULL OR avg_temperature_c <= temperature_max_c"),
    ("climate_records", "ck_climate_records_min_temperature_plausible",
     "temperature_min_c IS NULL OR (temperature_min_c >= -90 AND temperature_min_c <= 70)"),
    ("climate_records", "ck_climate_records_min_le_avg",
     "temperature_min_c IS NULL OR avg_temperature_c IS NULL OR temperature_min_c <= avg_temperature_c"),
    ("climate_records", "ck_climate_records_min_le_max",
     "temperature_min_c IS NULL OR temperature_max_c IS NULL OR temperature_min_c <= temperature_max_c"),
    ("submission_records", "ck_submission_records_interest_rate",
     "annual_interest_rate IS NULL OR (annual_interest_rate >= 0 AND annual_interest_rate <= 100)"),
    ("submission_records", "ck_submission_records_turnover_nonnegative",
     "annual_turnover_tzs IS NULL OR annual_turnover_tzs >= 0"),
    ("submission_records", "ck_submission_records_forced_sale_nonnegative",
     "collateral_forced_sale_value_tzs IS NULL OR collateral_forced_sale_value_tzs >= 0"),
    ("submission_records", "ck_submission_records_collateral_latitude",
     "collateral_latitude IS NULL OR (collateral_latitude >= -90 AND collateral_latitude <= 90)"),
    ("submission_records", "ck_submission_records_collateral_longitude",
     "collateral_longitude IS NULL OR (collateral_longitude >= -180 AND collateral_longitude <= 180)"),
    ("submission_records", "ck_submission_records_collateral_value_nonnegative",
     "collateral_value_tzs IS NULL OR collateral_value_tzs >= 0"),
    ("submission_records", "ck_submission_records_insurance_nonnegative",
     "insurance_value_protected_tzs IS NULL OR insurance_value_protected_tzs >= 0"),
    ("submission_records", "ck_submission_records_loan_amount_nonnegative",
     "loan_amount_tzs IS NULL OR loan_amount_tzs >= 0"),
    ("submission_records", "ck_submission_records_loan_latitude",
     "loan_latitude IS NULL OR (loan_latitude >= -90 AND loan_latitude <= 90)"),
    ("submission_records", "ck_submission_records_loan_longitude",
     "loan_longitude IS NULL OR (loan_longitude >= -180 AND loan_longitude <= 180)"),
    ("submission_records", "ck_submission_records_outstanding_nonnegative",
     "outstanding_principal_tzs IS NULL OR outstanding_principal_tzs >= 0"),
]


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = set(inspector.get_table_names())
    existing_checks = {
        table: {c["name"] for c in inspector.get_check_constraints(table)}
        for table in tables
        if table in {"submissions", "climate_records", "submission_records"}
    }
    # Grouped by table and applied inside op.batch_alter_table(): PostgreSQL
    # supports ALTER TABLE ADD CONSTRAINT directly and batch mode is a no-op
    # wrapper for it there, but SQLite does NOT support adding a CHECK
    # constraint to an existing table via ALTER TABLE at all - Alembic's
    # batch mode is what makes this migration actually run against a legacy
    # SQLite database (it recreates the table with the constraint included,
    # copies the data across, and swaps it in), rather than only working
    # against this project's production PostgreSQL target.
    by_table: dict[str, list[tuple[str, str]]] = {}
    for table, name, condition in CHECK_CONSTRAINTS:
        by_table.setdefault(table, []).append((name, condition))

    for table, constraints in by_table.items():
        if table not in tables:
            continue
        to_add = [(name, cond) for name, cond in constraints if name not in existing_checks.get(table, set())]
        if not to_add:
            continue
        with op.batch_alter_table(table) as batch_op:
            for name, condition in to_add:
                batch_op.create_check_constraint(name, condition)


def downgrade() -> None:
    by_table: dict[str, list[str]] = {}
    for table, name, _ in CHECK_CONSTRAINTS:
        by_table.setdefault(table, []).append(name)
    for table, names in by_table.items():
        with op.batch_alter_table(table) as batch_op:
            for name in names:
                try:
                    batch_op.drop_constraint(name, type_="check")
                except Exception:
                    pass
