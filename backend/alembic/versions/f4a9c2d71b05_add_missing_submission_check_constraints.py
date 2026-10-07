"""enforce three submission rules that models.py declared but no migration created

Revision ID: f4a9c2d71b05
Revises: e7a1f4c9b382

Why this migration exists. models.py declares three CHECK constraints that no
earlier migration ever created - found by comparing every constraint name in
models.py against the migrations (searched by name AND by the rule's own text):

    ck_submission_records_outstanding_le_loan   outstanding principal <= loan amount
    ck_submissions_record_counts_consistent     counts >= 0 and valid + invalid <= total
    ck_submissions_version_number_positive      version_number >= 1

The test suite builds its throw-away SQLite database from models.py
(Base.metadata.create_all), so it HAD these rules and passed; the real PostgreSQL
database is built only by migrations, so it did NOT. That is the same class of drift
as 9c1852419557 (see its docstring) - and scripts/verify_db_constraints.py did not
list these three either, so it could not have caught it.

Safe on a database that already holds data. A plain ADD CONSTRAINT would scan every
existing row and fail the whole upgrade - and init_db.py runs this at container start,
so a single bad historical row would stop the backend from booting. On PostgreSQL the
constraint is therefore added NOT VALID (enforced for every new or updated row, not
re-checked against old ones) and then VALIDATEd immediately if no existing row breaks
it. If some do, the migration logs how many and leaves the constraint NOT VALID; fix
those rows and run  ALTER TABLE <t> VALIDATE CONSTRAINT <name>;  Nothing is ever
deleted or rewritten here. (SQLite cannot add an unvalidated CHECK, so there - a
legacy or development database only - existing violations stop the migration.)

Companion change: validation_service.py now flags the matching values before they are
stored. Without that, enabling these rules would turn an upload that should show a
visible row error into an unexplained HTTP 409.

Idempotent: a constraint that already exists (by name) is skipped.
"""
import logging

from alembic import op
from sqlalchemy import inspect, text

revision = "f4a9c2d71b05"
down_revision = "e7a1f4c9b382"
branch_labels = None
depends_on = None

log = logging.getLogger("alembic.runtime.migration")

# (table, constraint name, condition exactly as in models.py, SQL selecting rows that break it)
CONSTRAINTS = [
    (
        "submission_records",
        "ck_submission_records_outstanding_le_loan",
        "loan_amount_tzs IS NULL OR outstanding_principal_tzs IS NULL OR outstanding_principal_tzs <= loan_amount_tzs",
        "loan_amount_tzs IS NOT NULL AND outstanding_principal_tzs IS NOT NULL AND outstanding_principal_tzs > loan_amount_tzs",
    ),
    (
        "submissions",
        "ck_submissions_record_counts_consistent",
        "valid_records >= 0 AND invalid_records >= 0 AND total_records >= 0 AND valid_records + invalid_records <= total_records",
        # NOT (...) is NULL - so the row is not selected - when a count is NULL, exactly as a CHECK treats NULL as passing.
        "NOT (valid_records >= 0 AND invalid_records >= 0 AND total_records >= 0 AND valid_records + invalid_records <= total_records)",
    ),
    (
        "submissions",
        "ck_submissions_version_number_positive",
        "version_number >= 1",
        "version_number < 1",
    ),
]


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = set(inspector.get_table_names())

    for table, name, condition, violation in CONSTRAINTS:
        if table not in tables:
            continue
        if name in {c["name"] for c in inspector.get_check_constraints(table)}:
            continue

        violators = bind.execute(text(f"SELECT COUNT(*) FROM {table} WHERE {violation}")).scalar() or 0

        if bind.dialect.name == "postgresql":
            op.execute(f"ALTER TABLE {table} ADD CONSTRAINT {name} CHECK ({condition}) NOT VALID")
            if violators == 0:
                op.execute(f"ALTER TABLE {table} VALIDATE CONSTRAINT {name}")
            else:
                log.warning(
                    "%s: %d existing row(s) in %s break this rule. The constraint is enforced for new and "
                    "updated rows but left NOT VALID. Find them with: SELECT * FROM %s WHERE %s; then fix "
                    "them and run: ALTER TABLE %s VALIDATE CONSTRAINT %s;",
                    name, violators, table, table, violation, table, name,
                )
        else:
            if violators:
                raise RuntimeError(
                    f"{violators} existing row(s) in {table} break {name} ({condition}). This database "
                    f"engine cannot add an unvalidated CHECK constraint; correct those rows explicitly "
                    f"and re-run - no rows are changed or deleted automatically."
                )
            with op.batch_alter_table(table) as batch_op:
                batch_op.create_check_constraint(name, condition)


def downgrade() -> None:
    bind = op.get_bind()
    tables = set(inspect(bind).get_table_names())
    for table, name, _condition, _violation in CONSTRAINTS:
        if table not in tables:
            continue
        if bind.dialect.name == "postgresql":
            op.execute(f"ALTER TABLE {table} DROP CONSTRAINT IF EXISTS {name}")
        else:
            with op.batch_alter_table(table) as batch_op:
                try:
                    batch_op.drop_constraint(name, type_="check")
                except Exception:
                    pass
