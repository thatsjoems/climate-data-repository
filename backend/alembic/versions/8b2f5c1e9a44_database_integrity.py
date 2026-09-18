"""database integrity hardening

Revision ID: 8b2f5c1e9a44
Revises: d2616a6f36ac
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "8b2f5c1e9a44"
down_revision = "d2616a6f36ac"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = set(inspector.get_table_names())

    if "climate_records" in tables and "climate_ingestion_batches" in tables:
        columns = {c["name"] for c in inspector.get_columns("climate_records")}
        if "batch_id" not in columns:
            op.add_column("climate_records", sa.Column("batch_id", sa.String(), nullable=True))
            op.create_foreign_key("fk_climate_records_batch_id", "climate_records", "climate_ingestion_batches", ["batch_id"], ["id"])

    existing_indexes = {(table, idx["name"]) for table in tables for idx in inspector.get_indexes(table)}
    for name, table, cols in [
        ("ix_users_institution_id", "users", ["institution_id"]),
        ("ix_submissions_submitted_by_user", "submissions", ["submitted_by_user_id"]),
        ("ix_submissions_reviewed_by_user", "submissions", ["reviewed_by_user_id"]),
        ("ix_submission_records_submission_valid_loan", "submission_records", ["submission_id", "is_valid", "loan_id"]),
        ("ix_climate_records_batch_id", "climate_records", ["batch_id"]),
        ("ix_audit_logs_user_created", "audit_logs", ["user_id", "created_at"]),
        ("ix_password_reset_requests_reviewer", "password_reset_requests", ["reviewed_by_user_id"]),
    ]:
        if table in tables and (table, name) not in existing_indexes:
            op.create_index(name, table, cols, unique=False)

    if "climate_records" in tables:
        duplicate_queries = [
            """SELECT 1 FROM climate_records WHERE source_record_id IS NOT NULL GROUP BY region, COALESCE(district, ''), year, COALESCE(month, 0), source_record_id, COALESCE(station_id, '') HAVING COUNT(*) > 1 LIMIT 1""",
            """SELECT 1 FROM climate_records WHERE source_record_id IS NULL AND station_id IS NOT NULL GROUP BY region, COALESCE(district, ''), year, COALESCE(month, 0), station_id HAVING COUNT(*) > 1 LIMIT 1""",
        ]
        for sql in duplicate_queries:
            if bind.execute(sa.text(sql)).first() is not None:
                raise RuntimeError("Existing duplicate climate observations prevent the uniqueness migration. Resolve duplicates explicitly; no rows are deleted automatically.")

        dialect = bind.dialect.name
        if dialect in {"postgresql", "sqlite"}:
            op.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_climate_observation_source_identity ON climate_records (region, COALESCE(district, ''), year, COALESCE(month, 0), source_record_id, COALESCE(station_id, '')) WHERE source_record_id IS NOT NULL")
            op.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_climate_observation_station_identity ON climate_records (region, COALESCE(district, ''), year, COALESCE(month, 0), station_id) WHERE source_record_id IS NULL AND station_id IS NOT NULL")


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name in {"postgresql", "sqlite"}:
        op.execute("DROP INDEX IF EXISTS uq_climate_observation_station_identity")
        op.execute("DROP INDEX IF EXISTS uq_climate_observation_source_identity")
    for name, table in [
        ("ix_password_reset_requests_reviewer", "password_reset_requests"),
        ("ix_audit_logs_user_created", "audit_logs"),
        ("ix_climate_records_batch_id", "climate_records"),
        ("ix_submission_records_submission_valid_loan", "submission_records"),
        ("ix_submissions_reviewed_by_user", "submissions"),
        ("ix_submissions_submitted_by_user", "submissions"),
        ("ix_users_institution_id", "users"),
    ]:
        try:
            op.drop_index(name, table_name=table)
        except Exception:
            pass
