"""scope submission_records loan-id uniqueness to valid rows only

Revision ID: e7a1f4c9b382
Revises: c3e4f8a7b901

Why (twentieth SRS item, found by actually running the test suite - not by
inspection): `uq_submission_records_submission_loan`
(b7f2c91d4e60) was a plain unique index on (submission_id, loan_id) for
SQLite, and partial only on `loan_id IS NOT NULL` for PostgreSQL - not scoped
to valid rows on either engine. A file with a duplicate loan_id is meant to
be storable as an INVALID submission: the application already flags the
repeated row (validation_service.py's seen_loan_ids check), and FR-SUB-07
requires every submitted row to be persisted for the reviewer to see,
including that one. Storing that already-correctly-flagged-invalid row hit
this index and raised a raw IntegrityError -> HTTP 409, with no row-level
feedback at all, on every duplicate-loan-id upload - not only a genuine data
bug. Confirmed directly:
`tests/test_upload_and_workflow.py::test_duplicate_loan_id_within_same_file_flagged`
failed with `KeyError: 'status'` because the response was 409, not the
intended 201-with-INVALID-status.

Fix: rebuild the index scoped to `loan_id IS NOT NULL AND is_valid = true`
(both engines). This keeps the constraint doing its real job - catching a
defect that lets two rows BOTH marked valid share a loan_id, which
validation is supposed to prevent and never should happen - while allowing
an intentionally-flagged-invalid duplicate row to be stored.

Uses `op.batch_alter_table()`-free direct index drop/create rather than
`b7f2c91d4e60`'s `_has_index` no-op guard: that guard only ever CREATES a
missing index, it has no equivalent for replacing one that already exists
with a differently-scoped version, so it cannot be reused here - a database
that already applied b7f2c91d4e60 already has the unscoped index and needs
it dropped and recreated, not skipped.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect, text

revision = "e7a1f4c9b382"
down_revision = "c3e4f8a7b901"
branch_labels = None
depends_on = None

INDEX_NAME = "uq_submission_records_submission_loan"


def upgrade() -> None:
    bind = op.get_bind()
    if "submission_records" not in inspect(bind).get_table_names():
        return
    existing = {i["name"] for i in inspect(bind).get_indexes("submission_records")}
    if INDEX_NAME in existing:
        op.drop_index(INDEX_NAME, table_name="submission_records")

    if bind.dialect.name == "postgresql":
        op.execute(
            f"CREATE UNIQUE INDEX {INDEX_NAME} ON submission_records (submission_id, loan_id) "
            f"WHERE loan_id IS NOT NULL AND is_valid = true"
        )
    else:
        op.execute(
            f"CREATE UNIQUE INDEX {INDEX_NAME} ON submission_records (submission_id, loan_id) "
            f"WHERE loan_id IS NOT NULL AND is_valid = 1"
        )


def downgrade() -> None:
    bind = op.get_bind()
    existing = {i["name"] for i in inspect(bind).get_indexes("submission_records")}
    if INDEX_NAME in existing:
        op.drop_index(INDEX_NAME, table_name="submission_records")
    if bind.dialect.name == "postgresql":
        op.execute(
            f"CREATE UNIQUE INDEX {INDEX_NAME} ON submission_records (submission_id, loan_id) "
            f"WHERE loan_id IS NOT NULL"
        )
    else:
        op.create_index(INDEX_NAME, "submission_records", ["submission_id", "loan_id"], unique=True)
